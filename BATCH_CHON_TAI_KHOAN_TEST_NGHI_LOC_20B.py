# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(r"C:\PhoCap")
DB = ROOT / "data" / "phocap.db"
EXPORT_DIR = ROOT / "exports"

OUT = EXPORT_DIR / "BATCH_CHON_TAI_KHOAN_TEST_NGHI_LOC_20B.txt"
JSON_OUT = EXPORT_DIR / "BATCH_20B_TAI_KHOAN_TEST_NGHI_LOC.json"

EXPECTED_DB_SHA = "2a43e36ff8f192abb46668faa1366ed7242984bfd876f90572cd83b90ee7837e"

BATCH_ID = 114
COMMUNE_ID = 114
ASSIGNED_SCHOOL_ID = 1606

LOG = None


def log(*args):
    s = " ".join(str(x) for x in args)
    print(s)
    if LOG:
        LOG.write(s + "\n")
        LOG.flush()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def table_exists(conn, table):
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone() is not None


def cols(conn, table):
    if not table_exists(conn, table):
        return []
    return [str(r[1]) for r in conn.execute(f'PRAGMA table_info("{table}")').fetchall()]


def rows_as_dicts(cur):
    names = [d[0] for d in cur.description]
    return [dict(zip(names, r)) for r in cur.fetchall()]


def role_code_column(conn):
    rc = cols(conn, "roles")
    if "code" in rc:
        return "code"
    if "role_code" in rc:
        return "role_code"
    return "name"


def user_rows(conn, where_sql, params):
    code_col = role_code_column(conn)
    uc = cols(conn, "users")
    active = " AND u.is_active=1" if "is_active" in uc else ""
    return rows_as_dicts(conn.execute(
        f"""
        SELECT
            u.id,u.username,u.full_name,u.commune_id,u.school_id,
            r."{code_col}" AS role_code
        FROM users u
        LEFT JOIN roles r ON r.id=u.role_id
        WHERE {where_sql} {active}
        ORDER BY u.id
        """,
        params,
    ))


def related_team_tables(conn):
    result = {}
    candidates = [
        "survey_investigation_participants",
        "survey_investigation_teams",
        "survey_investigation_team_members",
        "survey_investigation_team_forms",
        "survey_participant_submissions",
        "survey_team_area_assignments",
        "survey_team_generation_logs",
        "survey_team_registration_logs",
        "survey_form_investigators",
        "survey_assignment_logs",
    ]

    for table in candidates:
        if not table_exists(conn, table):
            result[table] = {"exists": False}
            continue

        c = cols(conn, table)
        filters = []
        params = []

        if "survey_batch_id" in c:
            filters.append("survey_batch_id=?")
            params.append(BATCH_ID)
        elif "batch_id" in c:
            filters.append("batch_id=?")
            params.append(BATCH_ID)

        if filters:
            sql = f'SELECT * FROM "{table}" WHERE ' + " AND ".join(filters) + " ORDER BY id"
        else:
            sql = f'SELECT * FROM "{table}" ORDER BY id'

        rows = rows_as_dicts(conn.execute(sql, tuple(params)))
        result[table] = {
            "exists": True,
            "columns": c,
            "row_count": len(rows),
            "rows": rows[:200],
        }

    return result


def main():
    global LOG

    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    LOG = OUT.open("w", encoding="utf-8-sig", newline="\n")

    log("=" * 160)
    log("BATCH 20B - CHỌN ĐÚNG TÀI KHOẢN TEST XÃ NGHI LỘC / THCS NGHI TRUNG")
    log("CHỈ ĐỌC DATABASE - KHÔNG ĐỔI MẬT KHẨU, KHÔNG GHI DỮ LIỆU")
    log("=" * 160)

    sha = sha256_file(DB)
    log("DB_SHA =", sha)
    log("EXPECTED_DB_SHA =", EXPECTED_DB_SHA)
    if sha != EXPECTED_DB_SHA:
        raise RuntimeError("DB SHA khác nền đã chốt.")

    conn = sqlite3.connect(
        f"file:{DB.as_posix()}?mode=ro",
        uri=True,
        timeout=60,
    )
    conn.row_factory = sqlite3.Row

    try:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        fk = conn.execute("PRAGMA foreign_key_check").fetchall()

        log("INTEGRITY =", integrity)
        log("FK =", len(fk))
        if integrity != "ok" or fk:
            raise RuntimeError("Database health không đạt.")

        batch = conn.execute(
            """
            SELECT id,code,name,school_year_id,commune_id,status,is_locked
            FROM survey_batches
            WHERE id=?
            """,
            (BATCH_ID,),
        ).fetchone()

        school = conn.execute(
            """
            SELECT id,code,name,commune_id,is_active
            FROM schools
            WHERE id=?
            """,
            (ASSIGNED_SCHOOL_ID,),
        ).fetchone()

        assignment = conn.execute(
            """
            SELECT *
            FROM survey_school_assignments
            WHERE survey_batch_id=? AND school_id=?
            ORDER BY id
            """,
            (BATCH_ID, ASSIGNED_SCHOOL_ID),
        )
        assignment_rows = rows_as_dicts(assignment)

        commune_accounts = user_rows(
            conn,
            "u.commune_id=?",
            (COMMUNE_ID,),
        )
        commune_xa = [
            x for x in commune_accounts
            if "XA" in str(x.get("role_code") or "").upper()
            or "COMMUNE" in str(x.get("role_code") or "").upper()
        ]

        school_accounts_all = user_rows(
            conn,
            "u.school_id=?",
            (ASSIGNED_SCHOOL_ID,),
        )
        school_accounts = [
            x for x in school_accounts_all
            if "TRUONG" in str(x.get("role_code") or "").upper()
            or "SCHOOL" in str(x.get("role_code") or "").upper()
        ]
        teacher_accounts = [
            x for x in school_accounts_all
            if "GIAO_VIEN" in str(x.get("role_code") or "").upper()
            or "TEACH" in str(x.get("role_code") or "").upper()
            or str(x.get("role_code") or "").upper() == "GV"
        ]

        forms = rows_as_dicts(conn.execute(
            """
            SELECT sf.id,sf.form_number,sf.status,sf.household_id,
                   h.code AS household_code,h.head_name,h.hamlet_name
            FROM survey_forms sf
            LEFT JOIN households h ON h.id=sf.household_id
            WHERE sf.survey_batch_id=?
            ORDER BY sf.id
            """,
            (BATCH_ID,),
        ))

        team_tables = related_team_tables(conn)

        log("BATCH =", json.dumps(dict(batch) if batch else None, ensure_ascii=False, default=str))
        log("SCHOOL =", json.dumps(dict(school) if school else None, ensure_ascii=False, default=str))
        log("ASSIGNMENT =", json.dumps(assignment_rows, ensure_ascii=False, default=str))
        log("COMMUNE_XA_ACCOUNTS =", json.dumps(commune_xa, ensure_ascii=False, default=str))
        log("SCHOOL_ACCOUNTS =", json.dumps(school_accounts, ensure_ascii=False, default=str))
        log("TEACHER_ACCOUNTS =", json.dumps(teacher_accounts, ensure_ascii=False, default=str))
        log("FORMS =", json.dumps(forms, ensure_ascii=False, default=str))

        log("\nTEAM / PARTICIPANT TABLES")
        for table, info in team_tables.items():
            if not info.get("exists"):
                log(table, "= MISSING")
                continue
            log(
                table,
                "=",
                json.dumps(
                    {
                        "row_count": info["row_count"],
                        "columns": info["columns"],
                        "rows": info["rows"],
                    },
                    ensure_ascii=False,
                    default=str,
                ),
            )

        chosen_school_account = school_accounts[0] if school_accounts else None
        chosen_teacher = teacher_accounts[0] if teacher_accounts else None

        summary = {
            "db_sha": sha,
            "batch": dict(batch) if batch else None,
            "school": dict(school) if school else None,
            "assignment": assignment_rows,
            "commune_xa_accounts": commune_xa,
            "school_accounts": school_accounts,
            "teacher_accounts": teacher_accounts,
            "chosen_school_account": chosen_school_account,
            "chosen_teacher_account": chosen_teacher,
            "forms": forms,
            "team_tables": team_tables,
            "ready_for_login_test": bool(
                batch and school and assignment_rows and commune_xa and school_accounts
            ),
            "note": (
                "Mật khẩu không được in ra. Dùng mật khẩu hiện có/đã cấp. "
                "Nếu không nhớ mật khẩu, dùng chức năng quản lý tài khoản để cấp lại theo luồng bình thường."
            ),
        }

        JSON_OUT.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8-sig",
        )

        log("\n" + "=" * 160)
        log("KẾT LUẬN BATCH 20B")
        log("=" * 160)
        log("XA_USERNAME =", commune_xa[0]["username"] if commune_xa else "NONE")
        log("SCHOOL_USERNAME =", chosen_school_account["username"] if chosen_school_account else "NONE")
        log("TEACHER_USERNAME =", chosen_teacher["username"] if chosen_teacher else "NONE")
        log("READY_FOR_LOGIN_TEST =", "YES" if summary["ready_for_login_test"] else "NO")
        log("DATABASE_WRITES_THIS_RUN = 0")
        log("DB_SHA_AFTER_READ_ONLY =", sha256_file(DB))
        log("BATCH_20B_SUCCESS = YES")
        log("=" * 160)

    finally:
        conn.close()
        if LOG:
            LOG.close()

    return 0


if __name__ == "__main__":
    try:
        rc = main()
    except Exception as exc:
        try:
            log("\n" + "=" * 160)
            log("BATCH_20B_SUCCESS = NO")
            log("ERROR =", repr(exc))
            if DB.exists():
                log("DB_SHA_CURRENT =", sha256_file(DB))
            log("DỪNG AN TOÀN.")
            log("=" * 160)
        finally:
            if LOG and not LOG.closed:
                LOG.close()
        rc = 1

    sys.exit(rc)
