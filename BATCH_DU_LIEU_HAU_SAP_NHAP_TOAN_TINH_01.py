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
EXPORT_DIR = ROOT / "exports"
OUT = EXPORT_DIR / "BATCH_DU_LIEU_HAU_SAP_NHAP_TOAN_TINH_01.txt"
PLAN_OUT = EXPORT_DIR / "BATCH_DU_LIEU_HAU_SAP_NHAP_TOAN_TINH_01_PLAN.json"

# Nền đã kiểm toán đóng engine THCS.
EXPECTED_DB_SHA = "164620f214a0820a07b93d35f877b917c4cc66ca54e0326e7265a7a3b3b8ee01"

BASE_YEAR_ID = 1      # 2025-2026
CURRENT_YEAR_ID = 2   # 2026-2027
FUTURE_YEAR_ID = 8    # 2027-2028 - chỉ quan sát, không động vào

# 5 ca tách điểm cần xử lý bằng nghiệp vụ dữ liệu thông thường, KHÔNG dùng merger engine.
MANUAL_SPLIT_CASES = {
    "QD3805-OP-0132": {
        "target_ids": [1521],
        "source_ids": [1522],
        "note": "Điểm Diễn Vạn của THCS Vạn Phong -> THCS Diễn Kỷ",
    },
    "QD3805-OP-0133": {
        "target_ids": [1523],
        "source_ids": [1522],
        "note": "Điểm Diễn Phong của THCS Vạn Phong -> THCS Diễn Hồng",
    },
    "QD3805-OP-0153": {
        "target_ids": [1579],
        "source_ids": [1583, 1580],
        "note": "THCS Diễn Hạnh nhận phần/điểm từ Hoa Quảng và Thái Nguyên",
    },
    "QD3805-OP-0191": {
        "target_ids": [1509],
        "source_ids": [1510],
        "note": "THCS Nguyễn Thái Nhự nhận phần còn lại từ Nguyễn Văn Trỗi (Thịnh Sơn)",
    },
    "QD3805-OP-0489": {
        "target_ids": [1660, 1657],
        "source_ids": [1658],
        "note": "Giải thể THCS Bá-Ngọc, tách điểm Quỳnh Bá/Quỳnh Ngọc về 2 đích",
    },
}

KEEP_CASES = {
    "QD3805-OP-0486": {"school_ids": [1660], "note": "THCS Quỳnh Hậu chỉ tiếp nhận điểm Quỳnh Bá"},
    "QD3805-OP-0490": {"school_ids": [1657], "note": "THCS Quỳnh Hưng chỉ tiếp nhận điểm Quỳnh Ngọc"},
}

BUSINESS_KEYWORDS = (
    "staff", "student", "pupil", "class", "lop", "household", "member",
    "facility", "equipment", "finance", "standard", "survey", "investigation",
    "attendance", "enrollment", "teacher"
)
EXCLUDE_KEYWORDS = (
    "merger", "audit", "log", "history", "official", "backup", "password",
    "session", "token"
)

def sha256_file(path: Path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()

def qi(name):
    return '"' + str(name).replace('"', '""') + '"'

def table_names(conn):
    return [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()]

def columns(conn, table):
    return [r[1] for r in conn.execute(f"PRAGMA table_info({qi(table)})").fetchall()]

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

def staff_summary(conn, sid, year_id):
    rows = conn.execute(
        "SELECT position_group,COUNT(*) FROM staff_year_records "
        "WHERE school_id=? AND school_year_id=? "
        "GROUP BY position_group ORDER BY position_group",
        (sid, year_id)
    ).fetchall()
    return rows

def safe_count(conn, table, where="", params=()):
    try:
        sql = f"SELECT COUNT(*) FROM {qi(table)}"
        if where:
            sql += " WHERE " + where
        return int(conn.execute(sql, params).fetchone()[0])
    except sqlite3.Error:
        return None

def business_school_year_tables(conn):
    out = []
    for t in table_names(conn):
        low = t.lower()
        c = columns(conn, t)
        if "school_id" not in c or "school_year_id" not in c:
            continue
        if any(k in low for k in EXCLUDE_KEYWORDS):
            continue
        if any(k in low for k in BUSINESS_KEYWORDS):
            out.append(t)
    return out

def commune_year_tables(conn):
    out = []
    for t in table_names(conn):
        low = t.lower()
        c = columns(conn, t)
        if "commune_id" not in c:
            continue
        year_col = None
        for cand in ("school_year_id", "year_id"):
            if cand in c:
                year_col = cand
                break
        if not year_col:
            continue
        if any(k in low for k in EXCLUDE_KEYWORDS):
            continue
        if any(k in low for k in BUSINESS_KEYWORDS):
            out.append((t, year_col))
    return out

def table_counts_by_school(conn, table, sid):
    return {
        "y1": safe_count(conn, table, "school_id=? AND school_year_id=?", (sid, BASE_YEAR_ID)),
        "y2": safe_count(conn, table, "school_id=? AND school_year_id=?", (sid, CURRENT_YEAR_ID)),
        "y8": safe_count(conn, table, "school_id=? AND school_year_id=?", (sid, FUTURE_YEAR_ID)),
    }

def active_school_ids(conn):
    return [int(r[0]) for r in conn.execute(
        "SELECT id FROM schools WHERE is_active=1 ORDER BY id"
    ).fetchall()]

def inactive_school_ids(conn):
    return [int(r[0]) for r in conn.execute(
        "SELECT id FROM schools WHERE is_active=0 ORDER BY id"
    ).fetchall()]

def duplicate_staff_current(conn):
    return conn.execute(
        """
        SELECT staff_member_id,COUNT(*) AS c,GROUP_CONCAT(school_id)
        FROM staff_year_records
        WHERE school_year_id=?
        GROUP BY staff_member_id
        HAVING COUNT(*)>1
        ORDER BY c DESC,staff_member_id
        """,
        (CURRENT_YEAR_ID,)
    ).fetchall()

def staff_statewide(conn, year_id):
    return conn.execute(
        """
        SELECT position_group,COUNT(*)
        FROM staff_year_records
        WHERE school_year_id=?
        GROUP BY position_group
        ORDER BY position_group
        """,
        (year_id,)
    ).fetchall()

def main():
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 160)
    print("BATCH DỮ LIỆU HẬU SÁP NHẬP TOÀN TỈNH 01")
    print("MỤC TIÊU: gom toàn bộ khoảng trống dữ liệu năm 2026-2027 + 5 ca tách điểm + tài khoản/đội ngũ/lớp/học sinh")
    print("CHỈ ĐỌC DATABASE - KHÔNG GHI DB")
    print("=" * 160)

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
            print("STOP = DB SHA khác nền đã khóa sau OP-0203.")
            return 1
        if integ != "ok" or fk:
            print("STOP = Database health không đạt.")
            return 1

        business_tables = business_school_year_tables(conn)
        commune_tables = commune_year_tables(conn)
        active_ids = active_school_ids(conn)
        inactive_ids = inactive_school_ids(conn)

        print("\n" + "=" * 160)
        print("1. CÁC BẢNG NGHIỆP VỤ CÓ school_id + school_year_id")
        print("=" * 160)
        print("BUSINESS_TABLES =", business_tables)

        table_statewide = {}
        for t in business_tables:
            y1 = safe_count(conn, t, "school_year_id=?", (BASE_YEAR_ID,))
            y2 = safe_count(conn, t, "school_year_id=?", (CURRENT_YEAR_ID,))
            y8 = safe_count(conn, t, "school_year_id=?", (FUTURE_YEAR_ID,))
            table_statewide[t] = {"y1": y1, "y2": y2, "y8": y8}
            print("TABLE_TOTAL", t, "=", table_statewide[t])

        print("\n" + "=" * 160)
        print("2. KHOẢNG TRỐNG DỮ LIỆU 2026-2027 THEO TRƯỜNG ĐANG HOẠT ĐỘNG")
        print("=" * 160)

        missing_by_table = {}
        present_without_base = {}
        for t in business_tables:
            missing = []
            y2_without_y1 = []
            for sid in active_ids:
                c = table_counts_by_school(conn, t, sid)
                if (c["y1"] or 0) > 0 and (c["y2"] or 0) == 0:
                    missing.append((sid, c["y1"], school(conn, sid)))
                if (c["y1"] or 0) == 0 and (c["y2"] or 0) > 0:
                    y2_without_y1.append((sid, c["y2"], school(conn, sid)))
            missing_by_table[t] = missing
            present_without_base[t] = y2_without_y1
            print("MISSING_Y2_FROM_Y1", t, "COUNT =", len(missing))
            for row in missing[:120]:
                print(" ", row)
            if len(missing) > 120:
                print(" ... TRUNCATED", len(missing) - 120)
            print("Y2_WITHOUT_Y1", t, "COUNT =", len(y2_without_y1))
            for row in y2_without_y1[:50]:
                print(" ", row)
            if len(y2_without_y1) > 50:
                print(" ... TRUNCATED", len(y2_without_y1) - 50)

        print("\n" + "=" * 160)
        print("3. DỮ LIỆU NĂM 2026-2027 CÒN Ở TRƯỜNG INACTIVE")
        print("=" * 160)

        inactive_residuals = {}
        for t in business_tables:
            rows = []
            for sid in inactive_ids:
                n = safe_count(conn, t, "school_id=? AND school_year_id=?", (sid, CURRENT_YEAR_ID))
                if (n or 0) > 0:
                    rows.append((sid, n, school(conn, sid)))
            inactive_residuals[t] = rows
            print("INACTIVE_Y2_RESIDUAL", t, "COUNT =", len(rows))
            for row in rows[:100]:
                print(" ", row)

        print("\n" + "=" * 160)
        print("4. TÀI KHOẢN TRƯỜNG ĐANG HOẠT ĐỘNG")
        print("=" * 160)

        account_anomalies = []
        for sid in active_ids:
            users = role3(conn, sid)
            active_users = [u for u in users if int(u[2] or 0) == 1]
            if len(active_users) != 1:
                account_anomalies.append((sid, school(conn, sid), users))
        print("ACTIVE_SCHOOL_ACCOUNT_ANOMALIES =", len(account_anomalies))
        for row in account_anomalies[:200]:
            print(" ", row)

        print("\n" + "=" * 160)
        print("5. ĐỘI NGŨ - KIỂM TOÁN TOÀN TỈNH")
        print("=" * 160)

        print("STAFF_STATEWIDE_Y1 =", staff_statewide(conn, BASE_YEAR_ID))
        print("STAFF_STATEWIDE_Y2 =", staff_statewide(conn, CURRENT_YEAR_ID))
        dup_staff = duplicate_staff_current(conn)
        print("DUPLICATE_STAFF_MEMBER_CURRENT_YEAR =", len(dup_staff))
        for row in dup_staff[:200]:
            print(" ", row)

        print("\n" + "=" * 160)
        print("6. 5 CA TÁCH ĐIỂM - KHÓA DỮ LIỆU THỰC TẾ ĐỂ CHUẨN BỊ BATCH NGHIỆP VỤ")
        print("=" * 160)

        manual_case_report = {}
        for opid, cfg in MANUAL_SPLIT_CASES.items():
            print("\n" + "-" * 140)
            print("OP =", opid)
            print("NOTE =", cfg["note"])
            case = {"targets": [], "sources": []}
            for role, ids in (("targets", cfg["target_ids"]), ("sources", cfg["source_ids"])):
                for sid in ids:
                    s = school(conn, sid)
                    info = {
                        "school": s,
                        "role3": role3(conn, sid),
                        "staff_y1": staff_summary(conn, sid, BASE_YEAR_ID),
                        "staff_y2": staff_summary(conn, sid, CURRENT_YEAR_ID),
                        "tables": {t: table_counts_by_school(conn, t, sid) for t in business_tables},
                    }
                    case[role].append(info)
                    print(role.upper(), sid, "=", json.dumps(info, ensure_ascii=False, default=str))
            manual_case_report[opid] = case

        print("\n" + "=" * 160)
        print("7. 2 CA KEEP - XÁC NHẬN KHÔNG TỰ ĐỘNG GHI DB")
        print("=" * 160)

        keep_report = {}
        for opid, cfg in KEEP_CASES.items():
            rows = []
            for sid in cfg["school_ids"]:
                info = {
                    "school": school(conn, sid),
                    "role3": role3(conn, sid),
                    "staff_y1": staff_summary(conn, sid, BASE_YEAR_ID),
                    "staff_y2": staff_summary(conn, sid, CURRENT_YEAR_ID),
                    "tables": {t: table_counts_by_school(conn, t, sid) for t in business_tables},
                }
                rows.append(info)
            keep_report[opid] = rows
            print("KEEP", opid, cfg["note"], "=", json.dumps(rows, ensure_ascii=False, default=str))

        print("\n" + "=" * 160)
        print("8. CÁC BẢNG NGHIỆP VỤ THEO XÃ/PHƯỜNG")
        print("=" * 160)

        commune_report = {}
        for t, year_col in commune_tables:
            y1 = safe_count(conn, t, f"{qi(year_col)}=?", (BASE_YEAR_ID,))
            y2 = safe_count(conn, t, f"{qi(year_col)}=?", (CURRENT_YEAR_ID,))
            y8 = safe_count(conn, t, f"{qi(year_col)}=?", (FUTURE_YEAR_ID,))
            commune_report[t] = {"year_col": year_col, "y1": y1, "y2": y2, "y8": y8}
            print("COMMUNE_TABLE", t, "=", commune_report[t])

        action_plan = {
            "db_sha": sha,
            "base_year_id": BASE_YEAR_ID,
            "current_year_id": CURRENT_YEAR_ID,
            "future_year_id": FUTURE_YEAR_ID,
            "business_tables": business_tables,
            "table_statewide": table_statewide,
            "missing_y2_count_by_table": {k: len(v) for k, v in missing_by_table.items()},
            "y2_without_y1_count_by_table": {k: len(v) for k, v in present_without_base.items()},
            "inactive_y2_residual_count_by_table": {k: len(v) for k, v in inactive_residuals.items()},
            "active_school_account_anomalies": len(account_anomalies),
            "duplicate_staff_member_current_year": len(dup_staff),
            "manual_split_cases": manual_case_report,
            "keep_cases": keep_report,
            "commune_tables": commune_report,
        }
        PLAN_OUT.write_text(
            json.dumps(action_plan, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8-sig"
        )

        print("\n" + "=" * 160)
        print("9. KẾT LUẬN BATCH")
        print("=" * 160)

        hard_failures = []
        if account_anomalies:
            hard_failures.append("ACTIVE_SCHOOL_ACCOUNT_ANOMALIES")
        if dup_staff:
            hard_failures.append("DUPLICATE_STAFF_MEMBER_CURRENT_YEAR")
        if any(inactive_residuals.values()):
            hard_failures.append("INACTIVE_SCHOOL_CURRENT_YEAR_RESIDUALS")

        print("HARD_FAILURES =", hard_failures)
        print("ACTION_PLAN_JSON =", PLAN_OUT)
        print("DATABASE_WRITES_THIS_RUN = 0")
        print("DATABASE = KHÔNG THAY ĐỔI")

        if not hard_failures:
            print("POST_MERGER_DATA_AUDIT_READY = YES")
            print("SAFE_TO_PREPARE_LARGE_DATA_BATCH = YES")
            print("NEXT_BATCH = Tự động xử lý các khoảng trống dữ liệu có quy tắc an toàn; 5 ca tách điểm chỉ xử lý phần dữ liệu đã khóa được, không deactivate nguồn bằng suy đoán.")
        else:
            print("POST_MERGER_DATA_AUDIT_READY = PARTIAL")
            print("SAFE_TO_PREPARE_LARGE_DATA_BATCH = YES_WITH_GATES")
            print("NEXT_BATCH = Tách các lỗi cứng khỏi các khoảng trống dữ liệu an toàn; xử lý song song trong một script có transaction riêng.")

        print("=" * 160)
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
