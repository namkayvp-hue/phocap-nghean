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
LEVEL_LOCK = ROOT / "data" / "school_merger_registry" / "qd3805_level_lock.json"
RESOLUTION = ROOT / "data" / "school_merger_registry" / "qd3805_thcs_resolution.json"
EXPORT_DIR = ROOT / "exports"
OUT = EXPORT_DIR / "BATCH_THCS_KHOA_7_DAC_THU_VA_KIEM_TOAN_CUOI.txt"

# Nền ngay sau COMMIT OP-0203
EXPECTED_DB_SHA = "164620f214a0820a07b93d35f877b917c4cc66ca54e0326e7265a7a3b3b8ee01"

CASES = {
    "QD3805-OP-0132": {
        "policy": "MANUAL_SPLIT_NO_ENGINE_WRITE",
        "title": "Điểm Diễn Vạn của THCS Vạn Phong -> THCS Diễn Kỷ",
        "exact_codes": ["40425507"],
        "name_terms": ["Vạn Phong", "Diễn Kỷ"],
        "note": "Đích chỉ nhận một phần/điểm trường; không chuyển toàn bộ THCS Vạn Phong."
    },
    "QD3805-OP-0133": {
        "policy": "MANUAL_SPLIT_NO_ENGINE_WRITE",
        "title": "Điểm Diễn Phong của THCS Vạn Phong -> THCS Diễn Hồng",
        "exact_codes": ["40425522"],
        "name_terms": ["Vạn Phong", "Diễn Hồng"],
        "note": "Đích chỉ nhận một phần/điểm trường; không chuyển toàn bộ THCS Vạn Phong."
    },
    "QD3805-OP-0153": {
        "policy": "MANUAL_SPLIT_NO_ENGINE_WRITE",
        "title": "THCS Diễn Hạnh – Hoa Quảng (Diễn Quảng) – Thái Nguyên (Diễn Nguyên)",
        "exact_codes": ["40425504"],
        "name_terms": ["Diễn Hạnh", "Hoa Quảng", "Thái Nguyên"],
        "note": "Các tên nguồn biểu diễn phần còn lại sau tách điểm; không dùng whole-school engine."
    },
    "QD3805-OP-0191": {
        "policy": "MANUAL_SPLIT_NO_ENGINE_WRITE",
        "title": "THCS Nguyễn Thái Nhự – Nguyễn Văn Trỗi (Thịnh Sơn)",
        "exact_codes": ["40427507"],
        "name_terms": ["Nguyễn Thái Nhự", "Nguyễn Văn Trỗi"],
        "note": "Nguyễn Văn Trỗi đã tách điểm Hòa Sơn sang Văn Hiến; không chuyển toàn bộ school_id."
    },
    "QD3805-OP-0489": {
        "policy": "MANUAL_SPLIT_NO_ENGINE_WRITE",
        "title": "Giải thể THCS Bá-Ngọc – tách hai điểm",
        "exact_codes": ["40421524", "40421529", "40421512"],
        "name_terms": ["Bá", "Ngọc", "Quỳnh Hậu", "Quỳnh Hưng"],
        "note": "Một nguồn giải thể chia hai điểm về hai đích; không có một đích duy nhất để chạy whole-school engine."
    },
    "QD3805-OP-0486": {
        "policy": "KEEP_NO_DB_WRITE",
        "title": "THCS Quỳnh Hậu tiếp nhận điểm Quỳnh Bá",
        "exact_codes": ["40421529"],
        "name_terms": ["Quỳnh Hậu"],
        "note": "Theo quy tắc đã chốt: trường chỉ nhận thêm điểm/lớp => GIỮ NGUYÊN, không tự động chuyển dữ liệu."
    },
    "QD3805-OP-0490": {
        "policy": "KEEP_NO_DB_WRITE",
        "title": "THCS Quỳnh Hưng tiếp nhận điểm Quỳnh Ngọc",
        "exact_codes": ["40421512"],
        "name_terms": ["Quỳnh Hưng"],
        "note": "Theo quy tắc đã chốt: trường chỉ nhận thêm điểm/lớp => GIỮ NGUYÊN, không tự động chuyển dữ liệu."
    },
}

BASE_YEAR_ID = 1
CURRENT_YEAR_ID = 2

def sha256_file(path: Path) -> str:
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

def find_level_op(data, opid):
    if not isinstance(data, dict):
        return None
    for obj in data.get("operations") or []:
        if isinstance(obj, dict) and obj.get("operation_id") == opid:
            return obj
    return None

def find_resolution(data, opid):
    if not isinstance(data, dict):
        return None
    for key in ("special_same_level", "precompleted", "rename_only", "deferred_orphans"):
        for obj in data.get(key) or []:
            if isinstance(obj, dict) and obj.get("operation_id") == opid:
                return obj
    return None

def school_by_code(conn, code):
    return conn.execute(
        "SELECT id,commune_id,code,name,is_active,created_at FROM schools WHERE code=? ORDER BY id",
        (code,)
    ).fetchall()

def school_by_name_term(conn, term):
    return conn.execute(
        "SELECT id,commune_id,code,name,is_active,created_at FROM schools "
        "WHERE name LIKE ? ORDER BY commune_id,id",
        (f"%{term}%",)
    ).fetchall()

def staff_summary(conn, sid):
    return conn.execute(
        "SELECT school_year_id,position_group,COUNT(*) "
        "FROM staff_year_records WHERE school_id=? "
        "GROUP BY school_year_id,position_group ORDER BY school_year_id,position_group",
        (sid,)
    ).fetchall()

def role3(conn, sid):
    return conn.execute(
        "SELECT id,username,is_active FROM users WHERE school_id=? AND role_id=3 ORDER BY id",
        (sid,)
    ).fetchall()

def official_related(conn, ids):
    ids = set(ids)
    out = []
    for r in conn.execute(
        "SELECT id,plan_id,operation_id,target_school_id,source_school_ids_json,created_at "
        "FROM school_merger_official_executions ORDER BY id"
    ).fetchall():
        try:
            src = {int(x) for x in json.loads(r[4] or "[]")}
        except Exception:
            src = set()
        if int(r[3]) in ids or bool(src & ids):
            out.append(r)
    return out

def compact_school(conn, row):
    sid = int(row[0])
    return {
        "school": row[:5],
        "staff": staff_summary(conn, sid),
        "role3": role3(conn, sid),
    }

def main():
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 150)
    print("BATCH THCS - KHÓA 7 PHƯƠNG ÁN ĐẶC THÙ + KIỂM TOÁN CUỐI")
    print("CHỈ ĐỌC DATABASE - KHÔNG GHI DB")
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

        level_data = load_json(LEVEL_LOCK)
        res_data = load_json(RESOLUTION)

        keep_count = 0
        manual_count = 0
        exact_lock_ok = 0
        all_ids = set()

        for opid, cfg in CASES.items():
            print("\n" + "-" * 150)
            print("OP =", opid)
            print("TITLE =", cfg["title"])
            print("POLICY =", cfg["policy"])
            print("BUSINESS_NOTE =", cfg["note"])

            lock = find_level_op(level_data, opid)
            res = find_resolution(res_data, opid)

            print("LEVEL_LOCK =", json.dumps(lock, ensure_ascii=False, default=str))
            print("RESOLUTION =", json.dumps(res, ensure_ascii=False, default=str))

            if lock and res:
                exact_lock_ok += 1

            ids = set()

            print("EXACT_CODE_MATCHES")
            for code in cfg["exact_codes"]:
                rows = school_by_code(conn, code)
                print(" CODE", code, "=>", rows)
                for r in rows:
                    ids.add(int(r[0]))

            print("NAME_TERM_MATCHES")
            for term in cfg["name_terms"]:
                rows = school_by_name_term(conn, term)
                print(" TERM", repr(term), "=>", rows)
                for r in rows:
                    ids.add(int(r[0]))

            # Ưu tiên bổ sung code khóa trực tiếp từ QĐ3805.
            if isinstance(lock, dict):
                for x in lock.get("source_schools") or []:
                    for code in x.get("codes") or []:
                        for r in school_by_code(conn, str(code)):
                            ids.add(int(r[0]))
                for code in lock.get("target_codes") or []:
                    for r in school_by_code(conn, str(code)):
                        ids.add(int(r[0]))

            print("RESOLVED_SCHOOL_IDS =", sorted(ids))
            for sid in sorted(ids):
                row = conn.execute(
                    "SELECT id,commune_id,code,name,is_active,created_at FROM schools WHERE id=?",
                    (sid,)
                ).fetchone()
                print(" SCHOOL_DETAIL", sid, "=", json.dumps(compact_school(conn, row), ensure_ascii=False, default=str))

            related = official_related(conn, ids) if ids else []
            print("RELATED_OFFICIAL =", related)

            all_ids |= ids

            if cfg["policy"] == "KEEP_NO_DB_WRITE":
                keep_count += 1
                print("FINAL_POLICY = KEEP / NO DB WRITE / NO LOGIN DISABLE / NO DEACTIVATE / NO AUTO TRANSFER")
            else:
                manual_count += 1
                print("FINAL_POLICY = MANUAL SPLIT / NO WHOLE-SCHOOL ENGINE / NO AUTO DATA TRANSFER")
                print("SOURCE_CLOSURE_POLICY = chỉ xem xét trạng thái nguồn sau khi dữ liệu điểm/lớp đã được cập nhật thủ công; batch này KHÔNG deactivate.")

        print("\n" + "=" * 150)
        print("KIỂM TOÁN CUỐI THCS")
        print("=" * 150)

        official_count = conn.execute(
            "SELECT COUNT(*) FROM school_merger_official_executions"
        ).fetchone()[0]
        operation_count = conn.execute(
            "SELECT COUNT(*) FROM school_merger_operations"
        ).fetchone()[0]
        max_official = conn.execute(
            "SELECT COALESCE(MAX(id),0) FROM school_merger_official_executions"
        ).fetchone()[0]
        max_operation = conn.execute(
            "SELECT COALESCE(MAX(id),0) FROM school_merger_operations"
        ).fetchone()[0]

        recent = conn.execute(
            "SELECT id,plan_id,operation_id,target_school_id,source_school_ids_json,created_at "
            "FROM school_merger_official_executions ORDER BY id DESC LIMIT 15"
        ).fetchall()

        print("OFFICIAL_EXECUTION_COUNT =", official_count)
        print("MERGER_OPERATION_COUNT =", operation_count)
        print("MAX_OFFICIAL_ID =", max_official)
        print("MAX_OPERATION_ID =", max_operation)
        print("RECENT_OFFICIAL_EXECUTIONS =", recent)

        op0203 = conn.execute(
            "SELECT id,plan_id,operation_id,target_school_id,source_school_ids_json,created_at "
            "FROM school_merger_official_executions WHERE plan_id=?",
            ("PA2026-16141F34ACBC",)
        ).fetchall()
        print("OP0203_OFFICIAL =", op0203)

        survivor = conn.execute(
            "SELECT id,commune_id,code,name,is_active FROM schools WHERE id=1712"
        ).fetchone()
        survivor_staff = staff_summary(conn, 1712)
        print("OP0203_SURVIVOR =", survivor)
        print("OP0203_SURVIVOR_STAFF =", survivor_staff)

        print("SEVEN_CASES_EXACT_LOCK_OK =", exact_lock_ok, "/ 7")
        print("KEEP_CASES =", keep_count)
        print("MANUAL_SPLIT_CASES =", manual_count)
        print("AUTOMATIC_ENGINE_DB_WRITE_REMAINING_FOR_THESE_7 = 0")
        print("DATABASE_WRITES_THIS_RUN = 0")
        print("DATABASE = KHÔNG THAY ĐỔI")

        if exact_lock_ok == 7:
            print("BATCH_AUDIT_READY = YES")
            print("NEXT_STAGE = Có thể coi phần engine tự động THCS đã đóng; các ca tách/tiếp nhận điểm xử lý bằng nhập/cập nhật thông thường theo quy tắc đã chốt.")
        else:
            print("BATCH_AUDIT_READY = NO")
            print("NEXT_STAGE = Có operation chưa khóa đủ trong registry; cần rà riêng.")

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
