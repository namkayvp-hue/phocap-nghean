# -*- coding: utf-8 -*-
from __future__ import annotations
import sqlite3
from pathlib import Path

ROOT = Path(r"C:\PhoCap")
DB = ROOT / "data" / "phocap.db"

CASES = [
    ("Nghi Vạn -> Nghi Diên", "40429436", "40429412", 47, 45, 92),
    ("Nghi Hoa -> Nghi Trung", "40429429", "40429427", 39, 43, 82),
]

def con_ro():
    con = sqlite3.connect(DB.resolve().as_uri() + "?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA query_only=ON")
    return con

def year_id(con, code):
    r = con.execute(
        "SELECT id FROM school_years "
        "WHERE REPLACE(REPLACE(code,'–','-'),'—','-')=? LIMIT 1", (code,)
    ).fetchone()
    return int(r["id"]) if r else None

def active_count(con, school_code, year_code):
    r = con.execute(
        "SELECT COUNT(*) AS n "
        "FROM staff_year_records syr "
        "JOIN staff_members sm ON sm.id=syr.staff_member_id "
        "JOIN schools s ON s.id=syr.school_id "
        "JOIN school_years sy ON sy.id=syr.school_year_id "
        "WHERE s.code=? "
        "AND REPLACE(REPLACE(sy.code,'–','-'),'—','-')=? "
        "AND COALESCE(syr.is_active,1)=1 "
        "AND COALESCE(sm.is_active,1)=1",
        (school_code, year_code),
    ).fetchone()
    return int(r["n"] or 0)

print("="*105)
print("KIỂM TRA 2 PHƯƠNG ÁN ĐÃ HOÀN TẤT TRƯỚC - CHỈ ĐỌC")
print("Database:", DB)
print("="*105)

with con_ro() as con:
    for title, src_code, dst_code, exp_prev_src, exp_prev_dst, exp_cur_dst in CASES:
        src = con.execute("SELECT id,code,name,is_active FROM schools WHERE code=? LIMIT 1", (src_code,)).fetchone()
        dst = con.execute("SELECT id,code,name,is_active FROM schools WHERE code=? LIMIT 1", (dst_code,)).fetchone()

        prev_src = active_count(con, src_code, "2025-2026")
        prev_dst = active_count(con, dst_code, "2025-2026")
        cur_src = active_count(con, src_code, "2026-2027")
        cur_dst = active_count(con, dst_code, "2026-2027")

        print(title)
        print("  nguồn:", dict(src) if src else None)
        print("  đích :", dict(dst) if dst else None)
        print(f"  2025-2026 nguồn: {prev_src} (dự kiến {exp_prev_src})")
        print(f"  2025-2026 đích : {prev_dst} (dự kiến {exp_prev_dst})")
        print(f"  2026-2027 nguồn: {cur_src} (dự kiến 0)")
        print(f"  2026-2027 đích : {cur_dst} (dự kiến {exp_cur_dst})")
        print(f"  phép cộng: {prev_src}+{prev_dst}={prev_src+prev_dst}")
        print("-"*105)

print("Database: KHÔNG THAY ĐỔI")
print("="*105)
