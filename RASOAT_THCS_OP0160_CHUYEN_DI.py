# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(r"C:\PhoCap")
DB = ROOT / "data" / "phocap.db"
REGISTRY = ROOT / "school_merger_official_registry_v2.json"
EXPORT_DIR = ROOT / "exports"
OUT = EXPORT_DIR / "RASOAT_THCS_OP0160_CHUYEN_DI.txt"

EXPECTED_DB_SHA = "03064473588592fa51aa807bf3ccfb7f8d8f59d52c0c4b67e54d3d793a8a2b4e"

PLAN_ID = "PA2026-B80F91FB9CD3"
OP_CODE = "QD3805-OP-0160"

TARGET_ID = 1639
SOURCE_IDS = [1640, 1641]
UNTOUCHED_ID = 1580
SPECIAL_MEMBER_ID = 34486

BASE_YEAR_ID = 1
CURRENT_YEAR_ID = 2

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def load_json(path: Path):
    for enc in ("utf-8-sig", "utf-8"):
        try:
            return json.loads(path.read_text(encoding=enc))
        except Exception:
            pass
    return None

def find_plan(reg):
    if isinstance(reg, dict):
        for p in reg.get("plans") or []:
            if isinstance(p, dict) and p.get("id") == PLAN_ID:
                return p
    return None

def table_exists(conn, name):
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,)
    ).fetchone() is not None

def columns(conn, table):
    return [r[1] for r in conn.execute(f'PRAGMA table_info("{table}")').fetchall()]

def school(conn, sid):
    return conn.execute(
        "SELECT id,commune_id,code,name,is_active FROM schools WHERE id=?",
        (sid,)
    ).fetchone()

def staff_rows(conn, sid, year_id):
    cur = conn.execute(
        """
        SELECT *
        FROM staff_year_records
        WHERE school_id=? AND school_year_id=?
        ORDER BY staff_member_id,id
        """,
        (sid, year_id),
    )
    names = [d[0] for d in cur.description]
    return [dict(zip(names, r)) for r in cur.fetchall()]

def summary(rows):
    c = Counter(str(r.get("position_group") or "NULL") for r in rows)
    return {
        "TOTAL": len(rows),
        "CBQL": c.get("CBQL", 0),
        "GIAO_VIEN": c.get("GIAO_VIEN", 0),
        "NHAN_VIEN": c.get("NHAN_VIEN", 0),
    }

def eligible(row):
    excluded_codes = {"NGHI_HUU", "CHUYEN_DI", "THOI_VIEC", "DA_NGHI"}
    excluded_labels = {"Đã nghỉ hưu", "Đã chuyển đi", "Nghỉ hưu", "Chuyển đi"}
    if int(row.get("is_active") or 0) != 1:
        return False, "is_active != 1"
    status = str(row.get("status_code") or "").strip().upper()
    label = str(row.get("source_status_label") or "").strip()
    if status in excluded_codes:
        return False, f"status_code={status}"
    if label in excluded_labels:
        return False, f"source_status_label={label}"
    return True, ""

def safe_dict(d):
    banned = {"password", "password_hash", "hashed_password", "salt"}
    return {k: v for k, v in d.items() if k.lower() not in banned}

def rows_as_dicts(cur):
    names = [d[0] for d in cur.description]
    return [safe_dict(dict(zip(names, r))) for r in cur.fetchall()]

def main():
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 150)
    print("RÀ SOÁT RIÊNG OP-0160 - NHÂN SỰ CHUYỂN ĐI")
    print("CHỈ ĐỌC - KHÔNG GHI DATABASE")
    print("=" * 150)

    if not DB.exists():
        print("DỪNG: Không tìm thấy", DB)
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
            print("STOP = DB SHA đã khác nền sau OP-0126.")
            return 1
        if integ != "ok" or fk:
            print("STOP = Database health không đạt.")
            return 1

        print("\nPLAN")
        plan = find_plan(load_json(REGISTRY))
        print(json.dumps(plan, ensure_ascii=False, indent=2, default=str))

        print("\nSCHOOLS")
        for sid in [TARGET_ID] + SOURCE_IDS + [UNTOUCHED_ID]:
            print("SCHOOL =", school(conn, sid))

        print("\nSPECIAL STAFF_MEMBER_ID =", SPECIAL_MEMBER_ID)

        # staff_year_records của đúng người qua mọi năm/mọi trường.
        cur = conn.execute(
            """
            SELECT *
            FROM staff_year_records
            WHERE staff_member_id=?
            ORDER BY school_year_id,school_id,id
            """,
            (SPECIAL_MEMBER_ID,),
        )
        yr = rows_as_dicts(cur)
        print("STAFF_YEAR_RECORDS =", json.dumps(yr, ensure_ascii=False, indent=2, default=str))

        # staff master nếu có.
        for table in ("staff_members", "staff"):
            if table_exists(conn, table):
                c = columns(conn, table)
                if "id" in c:
                    cur = conn.execute(f'SELECT * FROM "{table}" WHERE id=?', (SPECIAL_MEMBER_ID,))
                    rows = rows_as_dicts(cur)
                    print(f"{table.upper()} =", json.dumps(rows, ensure_ascii=False, indent=2, default=str))

        # Nhìn xem cùng người có bản ghi ở trường khác trong năm nền/current.
        print("\nEXACT MEMBER FOOTPRINT")
        footprint = conn.execute(
            """
            SELECT id,staff_member_id,school_year_id,school_id,position_group,status_code,source_status_label,is_active
            FROM staff_year_records
            WHERE staff_member_id=?
            ORDER BY school_year_id,school_id,id
            """,
            (SPECIAL_MEMBER_ID,),
        ).fetchall()
        print("FOOTPRINT =", footprint)

        target_rows = staff_rows(conn, TARGET_ID, BASE_YEAR_ID)
        source_rows = []
        for sid in SOURCE_IDS:
            source_rows.extend(staff_rows(conn, sid, BASE_YEAR_ID))

        print("\nBASE SUMMARIES")
        print("TARGET_BASE =", json.dumps(summary(target_rows), ensure_ascii=False))
        print("SOURCES_BASE =", json.dumps(summary(source_rows), ensure_ascii=False))

        excluded = []
        eligible_rows = []
        for r in target_rows + source_rows:
            ok, why = eligible(r)
            if ok:
                eligible_rows.append(r)
            else:
                excluded.append({
                    "staff_member_id": r.get("staff_member_id"),
                    "school_id": r.get("school_id"),
                    "position_group": r.get("position_group"),
                    "status_code": r.get("status_code"),
                    "source_status_label": r.get("source_status_label"),
                    "is_active": r.get("is_active"),
                    "reason": why,
                })

        print("EXCLUDED =", json.dumps(excluded, ensure_ascii=False, indent=2, default=str))
        print("FINAL_IF_INCLUDE_ALL =", json.dumps(summary(target_rows + source_rows), ensure_ascii=False))
        print("FINAL_IF_EXCLUDE_RULES =", json.dumps(summary(eligible_rows), ensure_ascii=False))

        # Kiểm tra chính xác người này có nằm trong current year ở nơi nào chưa.
        current = conn.execute(
            """
            SELECT id,staff_member_id,school_id,school_year_id,position_group,status_code,is_active
            FROM staff_year_records
            WHERE staff_member_id=? AND school_year_id=?
            ORDER BY school_id,id
            """,
            (SPECIAL_MEMBER_ID, CURRENT_YEAR_ID),
        ).fetchall()
        print("SPECIAL_MEMBER_CURRENT_YEAR =", current)

        # Kiểm tra execution liên quan OP0160.
        official = conn.execute(
            """
            SELECT id,plan_id,operation_id,target_school_id,source_school_ids_json,created_at
            FROM school_merger_official_executions
            WHERE plan_id=?
            ORDER BY id
            """,
            (PLAN_ID,),
        ).fetchall()
        print("OFFICIAL_EXECUTION_FOR_PLAN =", official)

        print("\n" + "=" * 150)
        print("KẾT LUẬN KỸ THUẬT")
        print("=" * 150)
        if len(excluded) == 1 and int(excluded[0].get("staff_member_id") or 0) == SPECIAL_MEMBER_ID:
            print("ONLY_EXCLUDED_MEMBER = YES")
            print("STAFF_MEMBER_ID =", SPECIAL_MEMBER_ID)
            print("POSITION_GROUP =", excluded[0].get("position_group"))
            print("STATUS_CODE =", excluded[0].get("status_code"))
            print("RECOMMENDED_NEXT_STEP = Nếu đúng là đã chuyển đi trước năm 2026-2027, LOẠI người này khỏi rollover OP-0160.")
        else:
            print("ONLY_EXCLUDED_MEMBER = NO")
            print("RECOMMENDED_NEXT_STEP = Chưa commit; cần rà thêm.")
        print("DATABASE = KHÔNG THAY ĐỔI")
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
