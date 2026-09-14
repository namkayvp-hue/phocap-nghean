# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(r"C:\PhoCap")
DB = ROOT / "data" / "phocap.db"
EXPORT_DIR = ROOT / "exports"

OUT = EXPORT_DIR / "BATCH_CHON_DIEM_TEST_DIEU_TRA_HO_DAN_20A.txt"
JSON_OUT = EXPORT_DIR / "BATCH_20A_DIEM_TEST_DIEU_TRA.json"

EXPECTED_DB_SHA = "2a43e36ff8f192abb46668faa1366ed7242984bfd876f90572cd83b90ee7837e"
CURRENT_YEAR_ID = 2

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


def count_group(conn, table, col):
    if not table_exists(conn, table) or col not in cols(conn, table):
        return {}
    return {
        int(r[0]): int(r[1])
        for r in conn.execute(
            f'SELECT "{col}",COUNT(*) FROM "{table}" '
            f'WHERE "{col}" IS NOT NULL GROUP BY "{col}"'
        ).fetchall()
    }


def batch_rows(conn):
    c = cols(conn, "survey_batches")
    wanted = [x for x in (
        "id", "code", "name", "school_year_id", "commune_id",
        "status", "is_locked", "start_date", "end_date"
    ) if x in c]
    return rows_as_dicts(conn.execute(
        "SELECT " + ",".join(f'"{x}"' for x in wanted) +
        ' FROM survey_batches WHERE school_year_id=? ORDER BY id',
        (CURRENT_YEAR_ID,)
    ))


def commune_name(conn, commune_id):
    if commune_id is None:
        return None
    r = conn.execute(
        "SELECT code,name,is_active FROM communes WHERE id=?",
        (int(commune_id),)
    ).fetchone()
    if not r:
        return None
    return {"code": r[0], "name": r[1], "is_active": r[2]}


def batch_households(conn, batch_id):
    if not table_exists(conn, "survey_forms"):
        return []
    return rows_as_dicts(conn.execute(
        """
        SELECT DISTINCT
            h.id AS household_id,
            h.code AS household_code,
            h.head_name,
            h.hamlet_name,
            h.commune_id,
            sf.id AS form_id,
            sf.form_number,
            sf.status AS form_status
        FROM survey_forms sf
        JOIN households h ON h.id=sf.household_id
        WHERE sf.survey_batch_id=?
        ORDER BY h.id
        """,
        (batch_id,)
    ))


def school_assignments(conn, batch_id):
    if not table_exists(conn, "survey_school_assignments"):
        return []
    return rows_as_dicts(conn.execute(
        """
        SELECT
            a.id,
            a.survey_batch_id,
            a.school_id,
            s.code AS school_code,
            s.name AS school_name,
            s.commune_id,
            a.status,
            a.is_locked,
            a.assigned_at,
            a.submitted_at,
            a.reviewed_at
        FROM survey_school_assignments a
        LEFT JOIN schools s ON s.id=a.school_id
        WHERE a.survey_batch_id=?
        ORDER BY a.id
        """,
        (batch_id,)
    ))


def active_users_for_scope(conn, commune_id, school_ids):
    result = {"commune_accounts": [], "school_accounts": [], "teacher_accounts": []}
    if not table_exists(conn, "users") or not table_exists(conn, "roles"):
        return result

    rc = cols(conn, "roles")
    role_code_col = "code" if "code" in rc else ("role_code" if "role_code" in rc else "name")
    uc = cols(conn, "users")
    active_filter = " AND u.is_active=1" if "is_active" in uc else ""

    if commune_id is not None:
        cur = conn.execute(
            f"""
            SELECT u.id,u.username,u.full_name,u.commune_id,u.school_id,
                   r."{role_code_col}" AS role_code
            FROM users u
            LEFT JOIN roles r ON r.id=u.role_id
            WHERE u.commune_id=? {active_filter}
            ORDER BY u.id
            """,
            (int(commune_id),)
        )
        all_rows = rows_as_dicts(cur)
        for x in all_rows:
            role = str(x.get("role_code") or "").upper()
            if "XA" in role or "COMMUNE" in role:
                result["commune_accounts"].append(x)
            elif "TRUONG" in role or "SCHOOL" in role:
                result["school_accounts"].append(x)
            elif "GIAO_VIEN" in role or "TEACH" in role or role == "GV":
                result["teacher_accounts"].append(x)

    # Bổ sung theo school_id nếu commune_id trên user không được set.
    if school_ids:
        placeholders = ",".join("?" for _ in school_ids)
        cur = conn.execute(
            f"""
            SELECT u.id,u.username,u.full_name,u.commune_id,u.school_id,
                   r."{role_code_col}" AS role_code
            FROM users u
            LEFT JOIN roles r ON r.id=u.role_id
            WHERE u.school_id IN ({placeholders}) {active_filter}
            ORDER BY u.id
            """,
            tuple(school_ids)
        )
        for x in rows_as_dicts(cur):
            role = str(x.get("role_code") or "").upper()
            target = None
            if "TRUONG" in role or "SCHOOL" in role:
                target = "school_accounts"
            elif "GIAO_VIEN" in role or "TEACH" in role or role == "GV":
                target = "teacher_accounts"
            if target is not None and not any(y["id"] == x["id"] for y in result[target]):
                result[target].append(x)

    return result


def find_related_tables(conn):
    rows = conn.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type='table'
          AND name NOT LIKE 'sqlite_%'
        ORDER BY name
        """
    ).fetchall()
    names = [str(r[0]) for r in rows]
    return [
        n for n in names
        if any(k in n.lower() for k in (
            "survey", "team", "assignment", "teacher", "household", "investigator"
        ))
    ]


def main():
    global LOG
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    LOG = OUT.open("w", encoding="utf-8-sig", newline="\n")

    log("=" * 160)
    log("BATCH 20A - CHỌN ĐIỂM TEST THỰC TẾ ĐIỀU TRA HỘ DÂN")
    log("SỬA LOGIC BATCH 20: survey_forms và survey_school_assignments dùng survey_batch_id, không phải batch_id")
    log("CHỈ ĐỌC DATABASE")
    log("=" * 160)

    sha = sha256_file(DB)
    log("DB_SHA =", sha)
    log("EXPECTED_DB_SHA =", EXPECTED_DB_SHA)
    if sha != EXPECTED_DB_SHA:
        raise RuntimeError("DB SHA khác nền đã chốt.")

    conn = sqlite3.connect(
        f"file:{DB.as_posix()}?mode=ro",
        uri=True,
        timeout=60
    )
    conn.row_factory = sqlite3.Row

    try:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        fk = conn.execute("PRAGMA foreign_key_check").fetchall()
        log("INTEGRITY =", integrity)
        log("FK =", len(fk))
        if integrity != "ok" or fk:
            raise RuntimeError("Database health không đạt.")

        forms_by_batch = count_group(conn, "survey_forms", "survey_batch_id")
        assignments_by_batch = count_group(
            conn, "survey_school_assignments", "survey_batch_id"
        )
        workflow_by_batch = count_group(
            conn, "survey_execution_workflow_logs", "survey_batch_id"
        )
        states_by_batch = count_group(
            conn, "survey_commune_execution_states", "survey_batch_id"
        )

        candidates = []
        for b in batch_rows(conn):
            bid = int(b["id"])
            households = batch_households(conn, bid)
            assignments = school_assignments(conn, bid)
            commune = commune_name(conn, b.get("commune_id"))

            score = 0
            if forms_by_batch.get(bid, 0) > 0:
                score += 50
            if assignments_by_batch.get(bid, 0) > 0:
                score += 30
            if workflow_by_batch.get(bid, 0) > 0:
                score += 15
            if str(b.get("status") or "") not in {"DA_KET_THUC"}:
                score += 5

            school_ids = sorted({
                int(x["school_id"]) for x in assignments
                if x.get("school_id") is not None
            })
            accounts = active_users_for_scope(
                conn, b.get("commune_id"), school_ids
            )

            candidates.append({
                **b,
                "commune": commune,
                "form_count": forms_by_batch.get(bid, 0),
                "household_count": len(households),
                "assignment_count": assignments_by_batch.get(bid, 0),
                "workflow_log_count": workflow_by_batch.get(bid, 0),
                "state_count": states_by_batch.get(bid, 0),
                "households": households,
                "assignments": assignments,
                "account_counts": {
                    "commune": len(accounts["commune_accounts"]),
                    "school": len(accounts["school_accounts"]),
                    "teacher": len(accounts["teacher_accounts"]),
                },
                "account_examples": {
                    "commune": accounts["commune_accounts"][:3],
                    "school": accounts["school_accounts"][:5],
                    "teacher": accounts["teacher_accounts"][:5],
                },
                "score": score,
            })

        candidates.sort(
            key=lambda x: (
                -x["score"],
                -x["form_count"],
                -x["assignment_count"],
                int(x["id"]),
            )
        )

        log("RELATED_TABLES =", json.dumps(
            find_related_tables(conn), ensure_ascii=False
        ))
        log("FORMS_BY_BATCH =", json.dumps(forms_by_batch, ensure_ascii=False))
        log("ASSIGNMENTS_BY_BATCH =", json.dumps(
            assignments_by_batch, ensure_ascii=False
        ))
        log("WORKFLOW_BY_BATCH =", json.dumps(
            workflow_by_batch, ensure_ascii=False
        ))

        log("\nTOP CANDIDATES")
        for c in candidates[:10]:
            printable = {
                k: v for k, v in c.items()
                if k not in {"households", "assignments", "account_examples"}
            }
            log(" CANDIDATE =", json.dumps(
                printable, ensure_ascii=False, default=str
            ))
            if c["households"]:
                log("  HOUSEHOLDS =", json.dumps(
                    c["households"][:10], ensure_ascii=False, default=str
                ))
            if c["assignments"]:
                log("  ASSIGNMENTS =", json.dumps(
                    c["assignments"], ensure_ascii=False, default=str
                ))
            log("  ACCOUNT_EXAMPLES =", json.dumps(
                c["account_examples"], ensure_ascii=False, default=str
            ))

        chosen = candidates[0] if candidates else None
        ready = bool(
            chosen
            and chosen["form_count"] > 0
            and chosen["household_count"] > 0
            and chosen["assignment_count"] > 0
        )

        summary = {
            "db_sha": sha,
            "chosen": chosen,
            "ready_for_real_flow_test": ready,
            "test_order": [
                "Đăng nhập tài khoản Xã của commune được chọn và mở đợt",
                "Kiểm tra trường đã được giao",
                "Đăng nhập trường được giao",
                "Kiểm tra/gửi danh sách giáo viên tham gia điều tra",
                "Đăng nhập lại Xã, kiểm tra ghép tổ và phân hộ",
                "Đăng nhập một Giáo viên, mở Phiếu phân công",
                "Nhập nhanh 1 hộ có sẵn, không tạo dữ liệu giả",
                "Kiểm tra tiến độ tại Trường và Xã",
            ],
        }

        JSON_OUT.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8-sig"
        )

        log("\n" + "=" * 160)
        log("KẾT LUẬN BATCH 20A")
        log("=" * 160)
        if chosen:
            log("CHOSEN_BATCH_ID =", chosen["id"])
            log("CHOSEN_BATCH_CODE =", chosen.get("code"))
            log("CHOSEN_COMMUNE =", json.dumps(
                chosen.get("commune"), ensure_ascii=False
            ))
            log("CHOSEN_FORM_COUNT =", chosen["form_count"])
            log("CHOSEN_HOUSEHOLD_COUNT =", chosen["household_count"])
            log("CHOSEN_ASSIGNMENT_COUNT =", chosen["assignment_count"])
            log("CHOSEN_ACCOUNT_COUNTS =", json.dumps(
                chosen["account_counts"], ensure_ascii=False
            ))
        log("READY_FOR_REAL_FLOW_TEST =", "YES" if ready else "NO")
        log("DATABASE_WRITES_THIS_RUN = 0")
        log("DB_SHA_AFTER_READ_ONLY =", sha256_file(DB))
        log("BATCH_20A_SUCCESS = YES")
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
            log("BATCH_20A_SUCCESS = NO")
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
