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
OUT = EXPORT_DIR / "RASOAT_THCS_OP0203_NGHI_HUU_42021.txt"

EXPECTED_DB_SHA = "1723e12a3d06d8f52b7b899174d5040bc4937ab84564e0f4d51b009586d8ce22"

PLAN_ID = "PA2026-16141F34ACBC"
SCHOOL_ID = 1712
SCHOOL_CODE = "40427524"
OLD_NAME = "THCS Kim Đồng"
NEW_NAME = "THCS Lê Hồng Phong"
COMMUNE_ID = 103
SPECIAL_MEMBER_ID = 42021

BASE_YEAR_ID = 1
CURRENT_YEAR_ID = 2

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
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

def main():
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 150)
    print("RÀ SOÁT OP-0203 - NHÂN SỰ NGHỈ HƯU 42021 + KHÓA SURVIVOR THCS KIM ĐỒNG")
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
            print("STOP = DB SHA đã khác nền sau OP-0172.")
            return 1
        if integ != "ok" or fk:
            print("STOP = Database health không đạt.")
            return 1

        print("\nSURVIVOR SCHOOL")
        school = conn.execute(
            "SELECT id,commune_id,code,name,is_active,created_at FROM schools WHERE id=?",
            (SCHOOL_ID,)
        ).fetchone()
        print("SCHOOL =", school)

        users = conn.execute(
            "SELECT id,username,is_active FROM users WHERE school_id=? AND role_id=3 ORDER BY id",
            (SCHOOL_ID,)
        ).fetchall()
        print("ROLE3_USERS =", users)

        same_name_commune = conn.execute(
            """
            SELECT id,commune_id,code,name,is_active
            FROM schools
            WHERE commune_id=? AND name=?
            ORDER BY id
            """,
            (COMMUNE_ID, NEW_NAME)
        ).fetchall()
        print("EXISTING_NEW_NAME_IN_COMMUNE =", same_name_commune)

        print("\nSPECIAL MEMBER")
        cur = conn.execute(
            "SELECT * FROM staff_year_records WHERE staff_member_id=? ORDER BY school_year_id,school_id,id",
            (SPECIAL_MEMBER_ID,)
        )
        records = rows_as_dicts(cur)
        print("STAFF_YEAR_RECORDS =")
        print(json.dumps(records, ensure_ascii=False, indent=2, default=str))

        if table_exists(conn, "staff_members"):
            cur = conn.execute(
                "SELECT * FROM staff_members WHERE id=?",
                (SPECIAL_MEMBER_ID,)
            )
            print("STAFF_MASTER =")
            print(json.dumps(rows_as_dicts(cur), ensure_ascii=False, indent=2, default=str))

        year2 = conn.execute(
            """
            SELECT id,staff_member_id,school_id,school_year_id,position_group,status_code,
                   source_status_label,is_active
            FROM staff_year_records
            WHERE staff_member_id=? AND school_year_id=?
            ORDER BY school_id,id
            """,
            (SPECIAL_MEMBER_ID, CURRENT_YEAR_ID)
        ).fetchall()
        print("CURRENT_YEAR_RECORDS =", year2)

        base = conn.execute(
            """
            SELECT id,staff_member_id,school_id,school_year_id,position_group,status_code,
                   source_status_label,is_active
            FROM staff_year_records
            WHERE staff_member_id=? AND school_id=? AND school_year_id=?
            ORDER BY id
            """,
            (SPECIAL_MEMBER_ID, SCHOOL_ID, BASE_YEAR_ID)
        ).fetchall()
        print("EXACT_BASE_RECORD =", base)

        print("\nSCHOOL NAME HISTORY")
        if table_exists(conn, "school_name_histories"):
            history = conn.execute(
                """
                SELECT id,school_id,effective_school_year_id,old_name,new_name,changed_at,changed_by_user_id
                FROM school_name_histories
                WHERE school_id=?
                ORDER BY id
                """,
                (SCHOOL_ID,)
            ).fetchall()
            print("HISTORY_FOR_1712 =", history)

            collision = conn.execute(
                """
                SELECT id,school_id,effective_school_year_id,old_name,new_name,changed_at
                FROM school_name_histories
                WHERE new_name=?
                ORDER BY id
                """,
                (NEW_NAME,)
            ).fetchall()
            print("HISTORY_NEW_NAME_COLLISIONS =", collision)

        official = conn.execute(
            """
            SELECT id,plan_id,operation_id,target_school_id,source_school_ids_json,created_at
            FROM school_merger_official_executions
            WHERE plan_id=? OR target_school_id=?
            ORDER BY id
            """,
            (PLAN_ID, SCHOOL_ID)
        ).fetchall()
        print("\nRELATED_OFFICIAL =", official)

        only_expected = (
            len(base) == 1
            and str(base[0][5] or "").strip().upper() == "NGHI_HUU"
            and str(base[0][6] or "").strip() == "Đã nghỉ hưu"
            and len(year2) == 0
        )

        print("\n" + "=" * 150)
        print("KẾT LUẬN KỸ THUẬT")
        print("=" * 150)
        print("SPECIAL_MEMBER_CONFIRMED_NGHI_HUU =", "YES" if only_expected else "NO")
        print("SURVIVOR_CANDIDATE =", school)
        print("RENAME_TARGET =", NEW_NAME)
        print("RECOMMENDED_NEXT_STEP = Nếu YES và không có collision tên trong commune 103, PREVIEW survivor id=1712 đổi tên sang THCS Lê Hồng Phong; loại 42021 khỏi rollover.")
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
