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
EXPORT_DIR = ROOT / "exports"
OUT = EXPORT_DIR / "RASOAT_THCS_OP0172_CHUYEN_DI.txt"

EXPECTED_DB_SHA = "9cd85770ad9f6743c6a96d54d2cd5d3e706466433acc287f3664d0e4e44b4d5d"

PLAN_ID = "PA2026-98173E42E1D0"
TARGET_ID = 1463
SOURCE_IDS = [1464, 1465]
SPECIAL_MEMBERS = [31442, 31566]

BASE_YEAR_ID = 1
CURRENT_YEAR_ID = 2

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def table_exists(conn, table):
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,)
    ).fetchone() is not None

def rows_as_dicts(cur):
    names = [d[0] for d in cur.description]
    banned = {"password", "password_hash", "hashed_password", "salt"}
    out = []
    for row in cur.fetchall():
        d = dict(zip(names, row))
        out.append({k:v for k,v in d.items() if k.lower() not in banned})
    return out

def staff_rows(conn, sid, year_id):
    cur = conn.execute(
        "SELECT * FROM staff_year_records WHERE school_id=? AND school_year_id=? ORDER BY staff_member_id,id",
        (sid, year_id)
    )
    names = [d[0] for d in cur.description]
    return [dict(zip(names, r)) for r in cur.fetchall()]

def summary(rows):
    c = Counter(str(r.get("position_group") or "NULL") for r in rows)
    return {
        "TOTAL": len(rows),
        "CBQL": c.get("CBQL",0),
        "GIAO_VIEN": c.get("GIAO_VIEN",0),
        "NHAN_VIEN": c.get("NHAN_VIEN",0),
    }

def eligible(row):
    excluded_codes = {"NGHI_HUU","CHUYEN_DI","THOI_VIEC","DA_NGHI"}
    excluded_labels = {"Đã nghỉ hưu","Đã chuyển đi","Nghỉ hưu","Chuyển đi"}
    if int(row.get("is_active") or 0) != 1:
        return False, "is_active != 1"
    status = str(row.get("status_code") or "").strip().upper()
    label = str(row.get("source_status_label") or "").strip()
    if status in excluded_codes:
        return False, f"status_code={status}"
    if label in excluded_labels:
        return False, f"source_status_label={label}"
    return True, ""

def main():
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)

    print("="*150)
    print("RÀ SOÁT OP-0172 - 2 NHÂN SỰ CHUYỂN ĐI")
    print("CHỈ ĐỌC - KHÔNG GHI DATABASE")
    print("="*150)

    if not DB.exists():
        print("DỪNG: Không tìm thấy", DB)
        return 2

    sha = sha256_file(DB)
    print("DB_SHA =", sha)
    print("EXPECTED_DB_SHA =", EXPECTED_DB_SHA)

    conn = sqlite3.connect(DB.resolve().as_uri()+"?mode=ro", uri=True, timeout=30)
    conn.execute("PRAGMA query_only=ON")

    try:
        integ = conn.execute("PRAGMA integrity_check").fetchone()[0]
        fk = conn.execute("PRAGMA foreign_key_check").fetchall()
        print("integrity =", integ)
        print("FK =", len(fk))

        if sha != EXPECTED_DB_SHA:
            print("STOP = DB SHA đã khác nền sau OP-0025.")
            return 1
        if integ != "ok" or fk:
            print("STOP = Database health không đạt.")
            return 1

        print("\nSCHOOLS")
        for sid in [TARGET_ID] + SOURCE_IDS:
            row = conn.execute(
                "SELECT id,commune_id,code,name,is_active FROM schools WHERE id=?",
                (sid,)
            ).fetchone()
            print("SCHOOL =", row)

        print("\nSPECIAL MEMBERS")
        for mid in SPECIAL_MEMBERS:
            print("\n" + "-"*120)
            print("STAFF_MEMBER_ID =", mid)

            cur = conn.execute(
                "SELECT * FROM staff_year_records WHERE staff_member_id=? ORDER BY school_year_id,school_id,id",
                (mid,)
            )
            print("STAFF_YEAR_RECORDS =")
            print(json.dumps(rows_as_dicts(cur), ensure_ascii=False, indent=2, default=str))

            if table_exists(conn, "staff_members"):
                cur = conn.execute("SELECT * FROM staff_members WHERE id=?", (mid,))
                print("STAFF_MASTER =")
                print(json.dumps(rows_as_dicts(cur), ensure_ascii=False, indent=2, default=str))

            current = conn.execute(
                "SELECT id,staff_member_id,school_id,school_year_id,position_group,status_code,is_active "
                "FROM staff_year_records WHERE staff_member_id=? AND school_year_id=? ORDER BY school_id,id",
                (mid, CURRENT_YEAR_ID)
            ).fetchall()
            print("CURRENT_YEAR =", current)

        target_rows = staff_rows(conn, TARGET_ID, BASE_YEAR_ID)
        source_rows = []
        for sid in SOURCE_IDS:
            source_rows.extend(staff_rows(conn, sid, BASE_YEAR_ID))

        all_rows = target_rows + source_rows
        excluded = []
        eligible_rows = []
        for r in all_rows:
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

        print("\nBASE_SUMMARIES")
        print("TARGET_BASE =", json.dumps(summary(target_rows), ensure_ascii=False))
        print("SOURCES_BASE =", json.dumps(summary(source_rows), ensure_ascii=False))
        print("ALL_BASE =", json.dumps(summary(all_rows), ensure_ascii=False))
        print("EXCLUDED =", json.dumps(excluded, ensure_ascii=False, indent=2, default=str))
        print("FINAL_IF_EXCLUDE_RULES =", json.dumps(summary(eligible_rows), ensure_ascii=False))

        official = conn.execute(
            "SELECT id,plan_id,operation_id,target_school_id,source_school_ids_json,created_at "
            "FROM school_merger_official_executions WHERE plan_id=? ORDER BY id",
            (PLAN_ID,)
        ).fetchall()
        print("OFFICIAL_EXECUTION_FOR_PLAN =", official)

        only_expected = (
            len(excluded) == 2
            and {int(x["staff_member_id"]) for x in excluded} == set(SPECIAL_MEMBERS)
        )

        print("\n" + "="*150)
        print("KẾT LUẬN KỸ THUẬT")
        print("="*150)
        print("ONLY_EXPECTED_EXCLUDED_MEMBERS =", "YES" if only_expected else "NO")
        if only_expected:
            print("RECOMMENDED_NEXT_STEP = Nếu đúng là cả 2 người đã chuyển đi trước năm 2026-2027, loại cả 2 khỏi rollover OP-0172.")
        else:
            print("RECOMMENDED_NEXT_STEP = Chưa commit; cần rà thêm.")
        print("DATABASE = KHÔNG THAY ĐỔI")
        print("="*150)
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
