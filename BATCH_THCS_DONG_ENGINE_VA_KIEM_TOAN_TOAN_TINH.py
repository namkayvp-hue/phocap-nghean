# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(r"C:\PhoCap")
DB = ROOT / "data" / "phocap.db"
RESOLUTION = ROOT / "data" / "school_merger_registry" / "qd3805_thcs_resolution.json"
EXPORT_DIR = ROOT / "exports"
OUT = EXPORT_DIR / "BATCH_THCS_DONG_ENGINE_VA_KIEM_TOAN_TOAN_TINH.txt"

EXPECTED_DB_SHA = "164620f214a0820a07b93d35f877b917c4cc66ca54e0326e7265a7a3b3b8ee01"

CURRENT_YEAR_ID = 2
BASE_YEAR_ID = 1
FUTURE_YEAR_ID = 8

# 7 ca đã khóa nghiệp vụ ở bước trước:
POLICY_CLOSED = {
    "QD3805-OP-0132": "MANUAL_SPLIT_NO_ENGINE_WRITE",
    "QD3805-OP-0133": "MANUAL_SPLIT_NO_ENGINE_WRITE",
    "QD3805-OP-0153": "MANUAL_SPLIT_NO_ENGINE_WRITE",
    "QD3805-OP-0191": "MANUAL_SPLIT_NO_ENGINE_WRITE",
    "QD3805-OP-0489": "MANUAL_SPLIT_NO_ENGINE_WRITE",
    "QD3805-OP-0486": "KEEP_NO_DB_WRITE",
    "QD3805-OP-0490": "KEEP_NO_DB_WRITE",
}

def sha256_file(path: Path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()

def load_json(path: Path):
    for enc in ("utf-8-sig", "utf-8"):
        try:
            return json.loads(path.read_text(encoding=enc))
        except Exception:
            pass
    return None

def table_names(conn):
    return [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()]

def columns(conn, table):
    safe = table.replace('"', '""')
    return [r[1] for r in conn.execute(f'PRAGMA table_info("{safe}")').fetchall()]

def school(conn, sid):
    return conn.execute(
        "SELECT id,commune_id,code,name,is_active FROM schools WHERE id=?",
        (sid,)
    ).fetchone()

def role3(conn, sid):
    return conn.execute(
        "SELECT id,username,is_active FROM users WHERE school_id=? AND role_id=3 ORDER BY id",
        (sid,)
    ).fetchall()

def current_footprint(conn, sid):
    out = []
    for t in table_names(conn):
        c = columns(conn, t)
        if "school_id" not in c or "school_year_id" not in c:
            continue
        safe = t.replace('"', '""')
        try:
            n = conn.execute(
                f'SELECT COUNT(*) FROM "{safe}" WHERE school_id=? AND school_year_id=?',
                (sid, CURRENT_YEAR_ID)
            ).fetchone()[0]
            if n:
                out.append((t, n))
        except sqlite3.Error:
            pass
    return out

def future_footprint(conn, sid):
    out = []
    for t in table_names(conn):
        c = columns(conn, t)
        if "school_id" not in c or "school_year_id" not in c:
            continue
        safe = t.replace('"', '""')
        try:
            n = conn.execute(
                f'SELECT COUNT(*) FROM "{safe}" WHERE school_id=? AND school_year_id=?',
                (sid, FUTURE_YEAR_ID)
            ).fetchone()[0]
            if n:
                out.append((t, n))
        except sqlite3.Error:
            pass
    return out

def staff_summary(conn, sid, year_id):
    return conn.execute(
        "SELECT position_group,COUNT(*) FROM staff_year_records "
        "WHERE school_id=? AND school_year_id=? "
        "GROUP BY position_group ORDER BY position_group",
        (sid, year_id)
    ).fetchall()

def official_rows(conn):
    cur = conn.execute(
        "SELECT id,plan_id,operation_id,school_year_id,target_school_id,"
        "source_school_ids_json,summary_json,created_at "
        "FROM school_merger_official_executions ORDER BY id"
    )
    rows = []
    for r in cur.fetchall():
        try:
            src = [int(x) for x in json.loads(r[5] or "[]")]
        except Exception:
            src = []
        try:
            summary = json.loads(r[6] or "{}")
        except Exception:
            summary = {}
        rows.append({
            "id": r[0],
            "plan_id": r[1],
            "operation_id": r[2],
            "school_year_id": r[3],
            "target_school_id": int(r[4]),
            "source_school_ids": src,
            "summary": summary,
            "created_at": r[7],
        })
    return rows

def operation_code_from_summary(summary):
    if not isinstance(summary, dict):
        return None
    return (
        summary.get("official_operation_code")
        or summary.get("official_operation_id")
        or summary.get("operation_id")
    )

def main():
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 150)
    print("BATCH THCS - ĐÓNG ENGINE TỰ ĐỘNG + KIỂM TOÁN TOÀN TỈNH SAU CÁC BỔ SUNG")
    print("CHỈ ĐỌC - KHÔNG GHI DATABASE")
    print("=" * 150)

    if not DB.exists():
        print("STOP = Không tìm thấy DB")
        return 2

    sha = sha256_file(DB)
    print("DB_SHA =", sha)
    print("EXPECTED_DB_SHA =", EXPECTED_DB_SHA)

    conn = sqlite3.connect(DB.resolve().as_uri() + "?mode=ro", uri=True, timeout=30)
    conn.execute("PRAGMA query_only=ON")
    try:
        integ = conn.execute("PRAGMA integrity_check").fetchone()[0]
        fk = conn.execute("PRAGMA foreign_key_check").fetchall()
        print("integrity =", integ)
        print("FK =", len(fk))

        if sha != EXPECTED_DB_SHA:
            print("STOP = DB SHA khác nền sau OP-0203.")
            return 1
        if integ != "ok" or fk:
            print("STOP = Database health không đạt.")
            return 1

        officials = official_rows(conn)

        print("\n" + "=" * 150)
        print("1. KIỂM TOÁN OFFICIAL EXECUTIONS")
        print("=" * 150)

        plan_counts = Counter(x["plan_id"] for x in officials)
        op_log_counts = Counter(x["operation_id"] for x in officials)
        duplicate_plans = sorted((k, v) for k, v in plan_counts.items() if k and v > 1)
        duplicate_operation_logs = sorted((k, v) for k, v in op_log_counts.items() if k is not None and v > 1)

        print("OFFICIAL_EXECUTION_COUNT =", len(officials))
        print("DUPLICATE_PLAN_IDS =", duplicate_plans)
        print("DUPLICATE_OPERATION_LOG_IDS =", duplicate_operation_logs)

        all_sources = []
        source_to_execs = defaultdict(list)
        for e in officials:
            for sid in e["source_school_ids"]:
                all_sources.append(sid)
                source_to_execs[sid].append(e["id"])

        duplicate_sources = {
            sid: ids for sid, ids in source_to_execs.items() if len(ids) > 1
        }
        print("UNIQUE_OFFICIAL_SOURCE_IDS =", len(set(all_sources)))
        print("DUPLICATE_SOURCE_REFERENCES =", json.dumps(duplicate_sources, ensure_ascii=False, sort_keys=True))

        print("\n" + "=" * 150)
        print("2. KIỂM TOÁN TẤT CẢ NGUỒN ĐÃ THỰC HIỆN CHÍNH THỨC")
        print("=" * 150)

        source_anomalies = []
        active_source_logins = []
        source_current_residuals = []
        source_future_residuals = []

        for sid in sorted(set(all_sources)):
            s = school(conn, sid)
            users = role3(conn, sid)
            current_fp = current_footprint(conn, sid)
            future_fp = future_footprint(conn, sid)

            active_users = [u for u in users if int(u[2] or 0) == 1]

            if not s:
                source_anomalies.append((sid, "MISSING_SCHOOL"))
            elif int(s[4]) != 0:
                source_anomalies.append((sid, "SOURCE_STILL_ACTIVE", s))

            if active_users:
                active_source_logins.append((sid, active_users))

            if current_fp:
                source_current_residuals.append((sid, current_fp))

            # Chỉ báo cáo year=8, không coi đây là lỗi để tránh tự suy diễn dữ liệu FUTURE lịch sử.
            if future_fp:
                source_future_residuals.append((sid, future_fp))

        print("SOURCE_SCHOOL_ANOMALIES =", source_anomalies)
        print("ACTIVE_SOURCE_LOGINS =", active_source_logins)
        print("CURRENT_YEAR_SOURCE_RESIDUALS =", source_current_residuals)
        print("FUTURE_YEAR_SOURCE_FOOTPRINTS_INFO_ONLY =", source_future_residuals)

        print("\n" + "=" * 150)
        print("3. KIỂM TOÁN 15 CA THCS ĐẶC THÙ")
        print("=" * 150)

        resolution = load_json(RESOLUTION)
        special = []
        if isinstance(resolution, dict):
            special = [
                x for x in (resolution.get("special_same_level") or [])
                if isinstance(x, dict)
            ]

        completed_codes = {}
        for e in officials:
            code = operation_code_from_summary(e["summary"])
            if code:
                completed_codes[str(code)] = e["id"]

        unresolved_special = []
        special_status_rows = []

        for item in special:
            opid = str(item.get("operation_id") or "")
            if opid in completed_codes:
                status = f"COMMITTED_OFFICIAL_ID_{completed_codes[opid]}"
            elif opid in POLICY_CLOSED:
                status = POLICY_CLOSED[opid]
            else:
                status = "UNRESOLVED"
                unresolved_special.append(opid)

            special_status_rows.append((
                opid,
                item.get("display_title"),
                item.get("relation_type"),
                status
            ))

        for row in special_status_rows:
            print("SPECIAL_STATUS =", row)

        print("SPECIAL_CASE_COUNT =", len(special_status_rows))
        print("UNRESOLVED_SPECIAL_CASES =", unresolved_special)
        print("POLICY_CLOSED_CASES =", json.dumps(POLICY_CLOSED, ensure_ascii=False, sort_keys=True))

        print("\n" + "=" * 150)
        print("4. KIỂM TRA OP-0203 SAU ĐỔI TÊN")
        print("=" * 150)

        op0203 = [e for e in officials if e["plan_id"] == "PA2026-16141F34ACBC"]
        survivor = school(conn, 1712)
        survivor_users = role3(conn, 1712)
        y1_staff = staff_summary(conn, 1712, BASE_YEAR_ID)
        y2_staff = staff_summary(conn, 1712, CURRENT_YEAR_ID)
        history = conn.execute(
            "SELECT id,school_id,effective_school_year_id,old_name,new_name,changed_at,changed_by_user_id "
            "FROM school_name_histories WHERE school_id=1712 ORDER BY id"
        ).fetchall()

        print("OP0203_OFFICIAL =", json.dumps(op0203, ensure_ascii=False, default=str))
        print("OP0203_SURVIVOR =", survivor)
        print("OP0203_USERS =", survivor_users)
        print("OP0203_STAFF_YEAR1 =", y1_staff)
        print("OP0203_STAFF_YEAR2 =", y2_staff)
        print("OP0203_NAME_HISTORY =", history)

        print("\n" + "=" * 150)
        print("5. KẾT LUẬN")
        print("=" * 150)

        hard_failures = []
        if duplicate_plans:
            hard_failures.append("DUPLICATE_PLAN_IDS")
        if duplicate_operation_logs:
            hard_failures.append("DUPLICATE_OPERATION_LOG_IDS")
        if duplicate_sources:
            hard_failures.append("DUPLICATE_SOURCE_REFERENCES")
        if source_anomalies:
            hard_failures.append("SOURCE_SCHOOL_ANOMALIES")
        if active_source_logins:
            hard_failures.append("ACTIVE_SOURCE_LOGINS")
        if source_current_residuals:
            hard_failures.append("CURRENT_YEAR_SOURCE_RESIDUALS")
        if unresolved_special:
            hard_failures.append("UNRESOLVED_SPECIAL_CASES")

        op0203_ok = (
            len(op0203) == 1
            and survivor is not None
            and int(survivor[0]) == 1712
            and int(survivor[1]) == 103
            and str(survivor[2]) == "40427524"
            and str(survivor[3]) == "THCS Lê Hồng Phong"
            and int(survivor[4]) == 1
            and len([u for u in survivor_users if int(u[2] or 0) == 1]) == 1
            and ("CBQL", 1) in y2_staff
            and ("GIAO_VIEN", 49) in y2_staff
            and ("NHAN_VIEN", 7) in y2_staff
            and len(history) == 1
        )
        print("OP0203_POST_AUDIT_OK =", "YES" if op0203_ok else "NO")
        if not op0203_ok:
            hard_failures.append("OP0203_POST_AUDIT")

        print("HARD_FAILURES =", hard_failures)
        print("MANUAL_DATA_UPDATE_CASES =", [
            "QD3805-OP-0132",
            "QD3805-OP-0133",
            "QD3805-OP-0153",
            "QD3805-OP-0191",
            "QD3805-OP-0489",
        ])
        print("KEEP_NO_ACTION_CASES =", ["QD3805-OP-0486", "QD3805-OP-0490"])
        print("DATABASE_WRITES_THIS_RUN = 0")
        print("DATABASE = KHÔNG THAY ĐỔI")

        if not hard_failures:
            print("THCS_AUTOMATIC_ENGINE_CLOSED = YES")
            print("STATEWIDE_OFFICIAL_SOURCE_AUDIT = PASS")
            print("NEXT_STAGE = Chuyển sang xử lý/kiểm tra dữ liệu nghiệp vụ còn lại; 5 ca tách điểm xử lý bằng cập nhật thông thường, không dùng engine sáp nhập.")
        else:
            print("THCS_AUTOMATIC_ENGINE_CLOSED = NO")
            print("STATEWIDE_OFFICIAL_SOURCE_AUDIT = FAIL")
            print("NEXT_STAGE = Cần xử lý các HARD_FAILURES trước khi đóng engine.")

        print("=" * 150)
        return 0
    finally:
        conn.close()

if __name__ == "__main__":
    class Tee:
        def __init__(self, *streams):
            self.streams = streams
        def write(self, data):
            for s in self.streams:
                s.write(data)
                s.flush()
        def flush(self):
            for s in self.streams:
                s.flush()

    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8-sig", newline="\n") as f:
        old = sys.stdout
        sys.stdout = Tee(old, f)
        try:
            code = main()
        finally:
            sys.stdout = old
    sys.exit(code)
