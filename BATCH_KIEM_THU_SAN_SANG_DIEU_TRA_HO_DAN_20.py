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

OUT = EXPORT_DIR / "BATCH_KIEM_THU_SAN_SANG_DIEU_TRA_HO_DAN_20.txt"
JSON_OUT = EXPORT_DIR / "BATCH_20_DIEU_TRA_HO_DAN_READINESS.json"

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


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone() is not None


def cols(conn: sqlite3.Connection, table: str) -> list[str]:
    if not table_exists(conn, table):
        return []
    return [str(r[1]) for r in conn.execute(f'PRAGMA table_info("{table}")').fetchall()]


def row_count(conn, table):
    if not table_exists(conn, table):
        return None
    return int(conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])


def table_profile(conn, table):
    if not table_exists(conn, table):
        return {"exists": False}
    c = cols(conn, table)
    result = {"exists": True, "columns": c, "total": row_count(conn, table)}
    if "school_year_id" in c:
        result["current_year"] = int(conn.execute(
            f'SELECT COUNT(*) FROM "{table}" WHERE school_year_id=?',
            (CURRENT_YEAR_ID,)
        ).fetchone()[0])
    return result


def survey_batches(conn):
    if not table_exists(conn, "survey_batches"):
        return []

    c = cols(conn, "survey_batches")
    select_cols = [x for x in (
        "id", "code", "name", "school_year_id", "commune_id",
        "status", "is_active", "is_locked", "created_at"
    ) if x in c]

    cur = conn.execute(
        "SELECT " + ",".join(f'"{x}"' for x in select_cols) +
        ' FROM "survey_batches" ORDER BY id DESC'
    )
    names = [d[0] for d in cur.description]
    return [dict(zip(names, r)) for r in cur.fetchall()]


def count_by_batch(conn, table, batch_col="batch_id"):
    if not table_exists(conn, table):
        return {}
    c = cols(conn, table)
    if batch_col not in c:
        return {}
    return {
        int(r[0]): int(r[1])
        for r in conn.execute(
            f'SELECT "{batch_col}", COUNT(*) FROM "{table}" '
            f'WHERE "{batch_col}" IS NOT NULL GROUP BY "{batch_col}"'
        ).fetchall()
    }


def role_summary(conn):
    if not table_exists(conn, "users"):
        return {}

    c = cols(conn, "users")
    result = defaultdict(int)

    if "role_code" in c:
        sql = 'SELECT COALESCE(role_code,""), COUNT(*) FROM users'
        if "is_active" in c:
            sql += " WHERE is_active=1"
        sql += " GROUP BY COALESCE(role_code,'')"
        for role, n in conn.execute(sql).fetchall():
            result[str(role)] += int(n)
        return dict(result)

    if "role_id" in c and table_exists(conn, "roles"):
        rc = cols(conn, "roles")
        code_col = "code" if "code" in rc else ("role_code" if "role_code" in rc else "name")
        sql = (
            f'SELECT COALESCE(r."{code_col}",""), COUNT(*) '
            'FROM users u LEFT JOIN roles r ON r.id=u.role_id'
        )
        if "is_active" in c:
            sql += " WHERE u.is_active=1"
        sql += f' GROUP BY COALESCE(r."{code_col}","")'
        for role, n in conn.execute(sql).fetchall():
            result[str(role)] += int(n)

    return dict(result)


def school_level_summary(conn):
    if not table_exists(conn, "school_network_year_data"):
        return {}
    rows = conn.execute(
        """
        SELECT UPPER(TRIM(level_code)), COUNT(DISTINCT school_id)
        FROM school_network_year_data
        WHERE TRIM(COALESCE(level_code,''))<>''
        GROUP BY UPPER(TRIM(level_code))
        ORDER BY 1
        """
    ).fetchall()
    return {str(level): int(n) for level, n in rows}


def source_route_presence():
    router_dir = ROOT / "app" / "routers"
    matches = []
    if router_dir.exists():
        for p in router_dir.glob("*.py"):
            name = p.name.lower()
            if "survey" in name or "house" in name or "assignment" in name:
                matches.append(p.name)
    return {"matching_router_files": sorted(matches)}


def candidate_test_batches(conn):
    batches = survey_batches(conn)
    household_by_batch = count_by_batch(conn, "households")
    forms_by_batch = count_by_batch(conn, "survey_forms")
    assignments_by_batch = count_by_batch(conn, "survey_school_assignments")

    candidates = []
    for b in batches:
        bid = int(b["id"])
        score = 0
        households = household_by_batch.get(bid, 0)
        forms = forms_by_batch.get(bid, 0)
        assignments = assignments_by_batch.get(bid, 0)

        if int(b.get("school_year_id") or 0) == CURRENT_YEAR_ID:
            score += 50
        if households > 0:
            score += 20
        if assignments > 0:
            score += 20
        if forms > 0:
            score += 10

        candidates.append({
            **b,
            "households": households,
            "survey_forms": forms,
            "school_assignments": assignments,
            "score": score,
        })

    candidates.sort(key=lambda x: (-x["score"], -int(x["id"])))
    return candidates


def main():
    global LOG
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    LOG = OUT.open("w", encoding="utf-8-sig", newline="\n")

    log("=" * 160)
    log("BATCH 20 - KIỂM THỬ SẴN SÀNG NGHIỆP VỤ ĐIỀU TRA HỘ DÂN")
    log("SAU KHI CHỐT SÁP NHẬP - CHỈ ĐỌC DB + SOURCE")
    log("=" * 160)

    sha = sha256_file(DB)
    log("DB_SHA =", sha)
    log("EXPECTED_DB_SHA =", EXPECTED_DB_SHA)
    if sha != EXPECTED_DB_SHA:
        raise RuntimeError("DB SHA khác nền đã chốt sau sáp nhập.")

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

        table_names = [
            "survey_batches",
            "households",
            "survey_people",
            "survey_person_year_records",
            "survey_forms",
            "survey_school_assignments",
            "survey_team_registrations",
            "survey_commune_execution_states",
            "survey_execution_workflow_logs",
            "users",
            "schools",
            "communes",
        ]

        profiles = {t: table_profile(conn, t) for t in table_names}
        roles = role_summary(conn)
        levels = school_level_summary(conn)
        candidates = candidate_test_batches(conn)
        routes = source_route_presence()

        log("\n1. TABLE PROFILES")
        for t, p in profiles.items():
            log(t, "=", json.dumps(p, ensure_ascii=False))

        log("\n2. ACTIVE ROLE SUMMARY")
        log(json.dumps(roles, ensure_ascii=False))

        log("\n3. SCHOOL LEVEL SUMMARY")
        log(json.dumps(levels, ensure_ascii=False))

        log("\n4. ROUTER PRESENCE")
        log(json.dumps(routes, ensure_ascii=False))

        log("\n5. TOP TEST BATCH CANDIDATES")
        for item in candidates[:20]:
            log(" CANDIDATE =", json.dumps(item, ensure_ascii=False, default=str))

        minimum_ready = (
            profiles["survey_batches"].get("exists") is True
            and profiles["households"].get("exists") is True
            and profiles["survey_people"].get("exists") is True
            and profiles["survey_forms"].get("exists") is True
            and len(candidates) > 0
            and any(x["score"] >= 50 for x in candidates)
        )

        summary = {
            "db_sha": sha,
            "integrity": integrity,
            "fk_count": len(fk),
            "profiles": profiles,
            "active_roles": roles,
            "school_levels": levels,
            "routes": routes,
            "candidate_batches": candidates[:20],
            "minimum_ready_for_ui_test": minimum_ready,
            "recommended_next_test_order": [
                "SO: mở/xem đợt 2026-2027",
                "XA: xem giao trường và trạng thái",
                "TRUONG: xem/gửi danh sách GV tham gia điều tra",
                "XA: kiểm tra ghép tổ 3 cấp và giao hộ",
                "GV: mở Phiếu phân công trên điện thoại",
                "GV: Nhập nhanh 1 hộ và hoàn thành",
                "TRUONG: kiểm tra nhận kết quả và gửi xã",
                "XA: kiểm tra tiến độ/khóa trường",
                "SO: kiểm tra tổng hợp/khóa xã",
            ],
        }

        JSON_OUT.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8-sig",
        )

        log("\n" + "=" * 160)
        log("KẾT LUẬN BATCH 20")
        log("=" * 160)
        log("MINIMUM_READY_FOR_UI_TEST =", "YES" if minimum_ready else "NO")
        log("JSON_OUT =", JSON_OUT)
        log("DATABASE_WRITES_THIS_RUN = 0")
        log("DB_SHA_AFTER_READ_ONLY =", sha256_file(DB))
        log("BATCH_20_SUCCESS = YES")
        log("NEXT_STAGE = Chọn 1 đợt/1 xã có dữ liệu để chạy test thật theo vai trò Sở -> Xã -> Trường -> Giáo viên; sửa ngay lỗi nào cản luồng.")
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
            log("BATCH_20_SUCCESS = NO")
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
