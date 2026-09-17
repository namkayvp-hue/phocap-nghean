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

EXPECTED_SHA = "3837441007286585e4eb28e9e9246a9f33fe339efc09c4b1e8f4fb048db89e70"
PLAN_ID = "PA2026-C1BD6766C723"
OPERATION_ID = 461
SOURCE_ID = 1578
TARGET_ID = 1577
BASE_YEAR_ID = 1
CURRENT_YEAR_IDS = [2, 8]

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            b = f.read(1024 * 1024)
            if not b:
                break
            h.update(b)
    return h.hexdigest()

def qi(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'

def tables(conn):
    return [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()]

def cols(conn, table):
    return [r[1] for r in conn.execute(f"PRAGMA table_info({qi(table)})").fetchall()]

def dict_rows(cur):
    names = [d[0] for d in cur.description]
    return [dict(zip(names, r)) for r in cur.fetchall()]

def staff_summary(conn, school_id, year_id):
    cur = conn.execute(
        """
        SELECT position_group, COUNT(*)
        FROM staff_year_records
        WHERE school_id=? AND school_year_id=?
        GROUP BY position_group
        ORDER BY position_group
        """,
        (school_id, year_id),
    )
    c = {str(k): int(v) for k, v in cur.fetchall()}
    total = sum(c.values())
    return {
        "TOTAL": total,
        "CBQL": c.get("CBQL", 0),
        "GIAO_VIEN": c.get("GIAO_VIEN", 0),
        "NHAN_VIEN": c.get("NHAN_VIEN", 0),
    }

def member_set(conn, school_id, year_id):
    return {
        int(r[0])
        for r in conn.execute(
            """
            SELECT DISTINCT staff_member_id
            FROM staff_year_records
            WHERE school_id=? AND school_year_id=?
            """,
            (school_id, year_id),
        ).fetchall()
    }

def footprint(conn, school_id):
    out = []
    for t in tables(conn):
        c = cols(conn, t)
        if "school_id" not in c:
            continue
        try:
            if "school_year_id" in c:
                rows = conn.execute(
                    f"""
                    SELECT school_year_id, COUNT(*)
                    FROM {qi(t)}
                    WHERE school_id=?
                    GROUP BY school_year_id
                    ORDER BY school_year_id
                    """,
                    (school_id,),
                ).fetchall()
                if rows:
                    out.append({"table": t, "by_year": rows, "total": sum(x[1] for x in rows)})
            else:
                n = conn.execute(
                    f"SELECT COUNT(*) FROM {qi(t)} WHERE school_id=?",
                    (school_id,),
                ).fetchone()[0]
                if n:
                    out.append({"table": t, "total": n})
        except sqlite3.Error:
            pass
    return out

def source_current_residual(conn):
    residual = []
    for t in tables(conn):
        c = cols(conn, t)
        if "school_id" not in c or "school_year_id" not in c:
            continue
        for y in CURRENT_YEAR_IDS:
            try:
                n = conn.execute(
                    f"SELECT COUNT(*) FROM {qi(t)} WHERE school_id=? AND school_year_id=?",
                    (SOURCE_ID, y),
                ).fetchone()[0]
                if n:
                    residual.append((t, y, n))
            except sqlite3.Error:
                pass
    return residual

def main():
    print("=" * 150)
    print("HẬU KIỂM THCS MẬU ĐÔN - SAU COMMIT - CHỈ ĐỌC")
    print("=" * 150)

    if not DB.exists():
        print("DỪNG: không tìm thấy DB")
        sys.exit(2)

    sha = sha256_file(DB)
    print("DATABASE =", DB)
    print("DB_SHA =", sha)
    print("EXPECTED_SHA =", EXPECTED_SHA)

    wal = DB.parent / "phocap.db-wal"
    journal = DB.parent / "phocap.db-journal"
    print("WAL_SIZE =", wal.stat().st_size if wal.exists() else 0)
    print("JOURNAL_SIZE =", journal.stat().st_size if journal.exists() else 0)

    conn = sqlite3.connect(DB.resolve().as_uri() + "?mode=ro", uri=True, timeout=30)
    conn.execute("PRAGMA query_only=ON")

    try:
        print("\n1. DATABASE HEALTH")
        print("-" * 150)
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        fk = conn.execute("PRAGMA foreign_key_check").fetchall()
        print("integrity =", integrity)
        print("FK =", len(fk))

        print("\n2. SCHOOL YEARS")
        print("-" * 150)
        if "school_years" in tables(conn):
            cur = conn.execute("SELECT * FROM school_years ORDER BY id")
            print(json.dumps(dict_rows(cur), ensure_ascii=False, indent=2, default=str))
        else:
            print("Không có bảng school_years.")

        print("\n3. SOURCE / TARGET SCHOOL")
        print("-" * 150)
        cur = conn.execute(
            "SELECT * FROM schools WHERE id IN (?,?) ORDER BY id",
            (SOURCE_ID, TARGET_ID),
        )
        print(json.dumps(dict_rows(cur), ensure_ascii=False, indent=2, default=str))

        print("\n4. TÀI KHOẢN SOURCE / TARGET")
        print("-" * 150)
        cur = conn.execute(
            """
            SELECT id, username, full_name, role_id, commune_id, school_id, is_active, created_at
            FROM users
            WHERE school_id IN (?,?)
            ORDER BY school_id, id
            """,
            (SOURCE_ID, TARGET_ID),
        )
        print(json.dumps(dict_rows(cur), ensure_ascii=False, indent=2, default=str))

        print("\n5. STAFF HISTORY + CURRENT")
        print("-" * 150)
        for sid, label in ((SOURCE_ID, "SOURCE"), (TARGET_ID, "TARGET")):
            years = conn.execute(
                """
                SELECT school_year_id, COUNT(*)
                FROM staff_year_records
                WHERE school_id=?
                GROUP BY school_year_id
                ORDER BY school_year_id
                """,
                (sid,),
            ).fetchall()
            print(label, "BY_YEAR =", years)
            for y, _ in years:
                print(label, f"YEAR {y} =", json.dumps(staff_summary(conn, sid, y), ensure_ascii=False))

        src_base = member_set(conn, SOURCE_ID, BASE_YEAR_ID)
        tgt_base = member_set(conn, TARGET_ID, BASE_YEAR_ID)
        tgt_y2 = member_set(conn, TARGET_ID, 2)
        union_base = src_base | tgt_base

        print("\n6. ĐỐI CHIẾU 61 NHÂN SỰ")
        print("-" * 150)
        print("SOURCE_BASE_UNIQUE =", len(src_base))
        print("TARGET_BASE_UNIQUE =", len(tgt_base))
        print("UNION_BASE_UNIQUE =", len(union_base))
        print("TARGET_YEAR2_UNIQUE =", len(tgt_y2))
        print("MISSING_FROM_TARGET_YEAR2 =", sorted(union_base - tgt_y2))
        print("EXTRA_IN_TARGET_YEAR2 =", sorted(tgt_y2 - union_base))

        print("\n7. DẤU VẾT TOÀN BỘ BẢNG")
        print("-" * 150)
        print("SOURCE FOOTPRINT:")
        print(json.dumps(footprint(conn, SOURCE_ID), ensure_ascii=False, indent=2, default=str))
        print("TARGET FOOTPRINT:")
        print(json.dumps(footprint(conn, TARGET_ID), ensure_ascii=False, indent=2, default=str))

        print("\n8. CURRENT-YEAR RESIDUAL TẠI SOURCE (YEAR 2/8)")
        print("-" * 150)
        residual = source_current_residual(conn)
        print("RESIDUAL =", residual)

        print("\n9. MERGER OPERATION + OFFICIAL EXECUTION")
        print("-" * 150)
        if "school_merger_operations" in tables(conn):
            cur = conn.execute(
                "SELECT * FROM school_merger_operations WHERE id=?",
                (OPERATION_ID,),
            )
            print("OPERATION:")
            print(json.dumps(dict_rows(cur), ensure_ascii=False, indent=2, default=str))
        if "school_merger_official_executions" in tables(conn):
            cur = conn.execute(
                "SELECT * FROM school_merger_official_executions WHERE plan_id=?",
                (PLAN_ID,),
            )
            official = dict_rows(cur)
            print("OFFICIAL:")
            print(json.dumps(official, ensure_ascii=False, indent=2, default=str))
        else:
            official = []

        print("\n10. KẾT LUẬN HẬU KIỂM")
        print("-" * 150)

        problems = []

        if sha != EXPECTED_SHA:
            problems.append("SHA DB khác SHA sau COMMIT")
        if integrity != "ok" or fk:
            problems.append("Database health lỗi")

        src_school = conn.execute("SELECT is_active FROM schools WHERE id=?", (SOURCE_ID,)).fetchone()
        tgt_school = conn.execute("SELECT is_active FROM schools WHERE id=?", (TARGET_ID,)).fetchone()
        if not src_school or int(src_school[0]) != 0:
            problems.append("SOURCE chưa inactive")
        if not tgt_school or int(tgt_school[0]) != 1:
            problems.append("TARGET không active")

        src_login_active = conn.execute(
            "SELECT COUNT(*) FROM users WHERE school_id=? AND role_id=3 AND is_active=1",
            (SOURCE_ID,),
        ).fetchone()[0]
        if src_login_active != 0:
            problems.append("Tài khoản trường nguồn còn active")

        if staff_summary(conn, SOURCE_ID, 1) != {"TOTAL":35,"CBQL":3,"GIAO_VIEN":30,"NHAN_VIEN":2}:
            problems.append("Lịch sử staff SOURCE năm 1 không còn đúng")
        if staff_summary(conn, TARGET_ID, 1) != {"TOTAL":26,"CBQL":3,"GIAO_VIEN":20,"NHAN_VIEN":3}:
            problems.append("Lịch sử staff TARGET năm 1 không còn đúng")
        if staff_summary(conn, TARGET_ID, 2) != {"TOTAL":61,"CBQL":6,"GIAO_VIEN":50,"NHAN_VIEN":5}:
            problems.append("Staff TARGET năm 2 không đúng 61")
        if union_base != tgt_y2:
            problems.append("Tập staff năm 2 không khớp union lịch sử SOURCE+TARGET")
        if residual:
            problems.append("SOURCE còn residual ở year 2/8")
        if len(official) != 1:
            problems.append("Official execution không đúng 1 dòng")

        # Year 8 is reported explicitly so we do not silently assume what it means.
        y8_target = staff_summary(conn, TARGET_ID, 8)
        print("TARGET_YEAR8_STAFF =", json.dumps(y8_target, ensure_ascii=False))
        if y8_target["TOTAL"] == 0:
            print("LƯU Ý_YEAR8 = 0. CẦN ĐỐI CHIẾU BẢNG school_years ĐỂ XÁC ĐỊNH YEAR 8 CÓ PHẢI 2026-2027 HỢP LỆ HAY KHÔNG.")

        if problems:
            print("POST_AUDIT_READY = NO")
            for p in problems:
                print("PROBLEM =", p)
        else:
            print("POST_AUDIT_READY = YES")
            print("LỊCH SỬ 2025-2026 ĐƯỢC GIỮ NGUYÊN.")
            print("TARGET NĂM 2 CÓ ĐỦ 61 NHÂN SỰ.")
            print("SOURCE KHÔNG CÒN RESIDUAL YEAR 2/8.")
            print("OFFICIAL EXECUTION = ĐÚNG 1 DÒNG.")

        print("\nKHÔNG GHI DATABASE. KHÔNG SỬA DỮ LIỆU.")

    finally:
        conn.close()

if __name__ == "__main__":
    main()
