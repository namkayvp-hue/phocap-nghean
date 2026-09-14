# -*- coding: utf-8 -*-
"""
KHẢO SÁT RIÊNG THCS MẬU ĐÔN - CHỈ ĐỌC

Mục tiêu:
- Khóa đúng trường nguồn THCS Mậu Đôn: school_id=1578, code=40422510.
- Tìm mọi dấu vết có thể xác định phương án/đích sáp nhập.
- Liệt kê các trường cùng xã/phường và các bảng liên quan merger/plan/operation.
- KHÔNG INSERT / UPDATE / DELETE.
- KHÔNG sáp nhập.
- Kiểm tra SHA database trước/sau.
"""

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

SOURCE_SCHOOL_ID = 1578
SOURCE_COMMUNE_ID = 64
SOURCE_NAME = "Trường THCS Mậu Đôn"
SOURCE_CODE = "40422510"

OP_CODES = [
    "QD3805-OP-0108",
    "QD3805-OP-0210",
    "QD3805-OP-0644",
]

def qi(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            b = f.read(1024 * 1024)
            if not b:
                break
            h.update(b)
    return h.hexdigest()

def find_db() -> Path:
    root = Path(__file__).resolve().parent
    candidates = [
        root / "data" / "phocap.db",
        root / "phocap.db",
        Path(r"C:\PhoCap\data\phocap.db"),
        Path(r"C:\PhoCap\phocap.db"),
    ]
    for p in candidates:
        if p.exists():
            return p
    print("DỪNG AN TOÀN: không tìm thấy phocap.db")
    sys.exit(2)

def get_tables(conn):
    return [r[0] for r in conn.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type='table' AND name NOT LIKE 'sqlite_%'
        ORDER BY name
        """
    ).fetchall()]

def get_columns(conn, table):
    return conn.execute(f"PRAGMA table_info({qi(table)})").fetchall()

def row_dict(cur, row):
    names = [d[0] for d in cur.description]
    result = {}
    for i, name in enumerate(names):
        v = row[i]
        if isinstance(v, (bytes, bytearray)):
            v = f"<BLOB {len(v)} bytes>"
        elif isinstance(v, str) and len(v) > 3500:
            v = v[:3500] + "...<CUT>"
        result[name] = v
    return result

def print_rows(cur, rows, limit=50):
    if not rows:
        print("  Không có.")
        return
    for idx, row in enumerate(rows[:limit], 1):
        print(f"\n  [{idx}]")
        print(json.dumps(row_dict(cur, row), ensure_ascii=False, indent=2, default=str))

def is_text_type(col_type: str) -> bool:
    t = (col_type or "").upper()
    return (not t) or any(x in t for x in ("TEXT", "CHAR", "CLOB", "JSON", "VARCHAR"))

def main():
    print("=" * 150)
    print("KHẢO SÁT THCS MẬU ĐÔN 1578 - TÌM ĐÚNG TRƯỜNG ĐÍCH - CHỈ ĐỌC")
    print("=" * 150)

    db = find_db()
    sha_before = sha256_file(db)
    print("DATABASE =", db)
    print("SHA BEFORE =", sha_before)
    print("phocap.db-wal =", (db.parent / "phocap.db-wal").stat().st_size if (db.parent / "phocap.db-wal").exists() else 0)
    print("phocap.db-journal =", (db.parent / "phocap.db-journal").stat().st_size if (db.parent / "phocap.db-journal").exists() else 0)

    conn = sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True, timeout=30)
    conn.execute("PRAGMA query_only = ON")

    try:
        print("\n1. DATABASE HEALTH")
        print("-" * 150)
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        fk = conn.execute("PRAGMA foreign_key_check").fetchall()
        print("integrity =", integrity)
        print("FK =", len(fk))
        if integrity != "ok" or fk:
            print("DỪNG AN TOÀN: database health không đạt.")
            return

        tables = get_tables(conn)

        print("\n2. KHÓA NGUỒN THCS MẬU ĐÔN")
        print("-" * 150)
        cur = conn.execute("SELECT * FROM schools WHERE id = ?", (SOURCE_SCHOOL_ID,))
        rows = cur.fetchall()
        print_rows(cur, rows)
        if len(rows) != 1:
            print("DỪNG AN TOÀN: không khóa được duy nhất school_id=1578.")
            return
        rd = row_dict(cur, rows[0])
        if str(rd.get("code")) != SOURCE_CODE or "Mậu Đôn" not in str(rd.get("name", "")):
            print("DỪNG AN TOÀN: school_id=1578 không khớp mã/tên Mậu Đôn.")
            return

        print("\n3. TOÀN BỘ TRƯỜNG CÙNG COMMUNE_ID = 64")
        print("-" * 150)
        cur = conn.execute("SELECT * FROM schools WHERE commune_id = ? ORDER BY id", (SOURCE_COMMUNE_ID,))
        same_commune = cur.fetchall()
        print("SỐ TRƯỜNG =", len(same_commune))
        print_rows(cur, same_commune, 100)

        print("\n4. CÁC BẢNG CÓ TÊN LIÊN QUAN SÁP NHẬP / KẾ HOẠCH / AUDIT")
        print("-" * 150)
        keywords = ("merger", "merge", "official", "operation", "plan", "audit")
        merger_tables = []
        for table in tables:
            low = table.lower()
            if any(k in low for k in keywords):
                merger_tables.append(table)
                print(f"\nTABLE = {table}")
                for c in get_columns(conn, table):
                    print(f"  {c[1]} | {c[2]}")
        if not merger_tables:
            print("Không thấy bảng tên liên quan.")

        print("\n5. TÌM SOURCE SCHOOL_ID=1578 TRONG TOÀN DATABASE")
        print("-" * 150)
        total_hits = 0
        for table in tables:
            cols = get_columns(conn, table)
            for c in cols:
                col_name = c[1]
                col_type = (c[2] or "").upper()
                low = col_name.lower()

                if not any(k in low for k in ("school", "source", "target", "json", "summary", "plan", "operation")):
                    continue
                try:
                    if any(x in col_type for x in ("INT", "REAL", "NUM")):
                        cur = conn.execute(
                            f"SELECT * FROM {qi(table)} WHERE {qi(col_name)} = ? LIMIT 30",
                            (SOURCE_SCHOOL_ID,)
                        )
                    else:
                        cur = conn.execute(
                            f"SELECT * FROM {qi(table)} WHERE CAST({qi(col_name)} AS TEXT) LIKE ? LIMIT 30",
                            (f"%{SOURCE_SCHOOL_ID}%",)
                        )
                    found = cur.fetchall()
                    if found:
                        total_hits += len(found)
                        print(f"\nTABLE={table} | COLUMN={col_name} | ROWS={len(found)}")
                        print_rows(cur, found, 30)
                except sqlite3.Error:
                    pass
        print("\nTOTAL HITS FOR 1578 =", total_hits)

        print("\n6. TÌM TÊN / MÃ MẬU ĐÔN TRONG TOÀN DATABASE")
        print("-" * 150)
        for term in (SOURCE_NAME, "Mậu Đôn", SOURCE_CODE):
            print(f"\n# SEARCH = {term}")
            hits = 0
            for table in tables:
                for c in get_columns(conn, table):
                    col_name, col_type = c[1], c[2] or ""
                    if not is_text_type(col_type):
                        continue
                    try:
                        cur = conn.execute(
                            f"SELECT * FROM {qi(table)} WHERE CAST({qi(col_name)} AS TEXT) LIKE ? LIMIT 20",
                            (f"%{term}%",)
                        )
                        found = cur.fetchall()
                        if found:
                            hits += len(found)
                            print(f"\nTABLE={table} | COLUMN={col_name} | ROWS={len(found)}")
                            print_rows(cur, found, 20)
                    except sqlite3.Error:
                        pass
            print("HITS =", hits)

        print("\n7. TÌM 3 OPERATION TRONG TOÀN DATABASE")
        print("-" * 150)
        for op in OP_CODES:
            print(f"\n# {op}")
            total = 0
            for table in tables:
                for c in get_columns(conn, table):
                    col_name, col_type = c[1], c[2] or ""
                    if not is_text_type(col_type):
                        continue
                    try:
                        cur = conn.execute(
                            f"SELECT * FROM {qi(table)} WHERE CAST({qi(col_name)} AS TEXT) LIKE ? LIMIT 20",
                            (f"%{op}%",)
                        )
                        found = cur.fetchall()
                        if found:
                            total += len(found)
                            print(f"\nTABLE={table} | COLUMN={col_name} | ROWS={len(found)}")
                            print_rows(cur, found, 20)
                    except sqlite3.Error:
                        pass
            print("TOTAL =", total)

        print("\n8. TÀI KHOẢN THCS MẬU ĐÔN")
        print("-" * 150)
        cur = conn.execute(
            """
            SELECT id, username, full_name, role_id, commune_id, school_id, is_active, created_at
            FROM users
            WHERE school_id = ?
            ORDER BY id
            """,
            (SOURCE_SCHOOL_ID,)
        )
        print_rows(cur, cur.fetchall(), 30)

        print("\n9. NHÂN SỰ THCS MẬU ĐÔN THEO NĂM")
        print("-" * 150)
        try:
            rows = conn.execute(
                """
                SELECT school_year_id, COUNT(*)
                FROM staff_year_records
                WHERE school_id = ?
                GROUP BY school_year_id
                ORDER BY school_year_id
                """,
                (SOURCE_SCHOOL_ID,)
            ).fetchall()
            for y, c in rows:
                print(f"school_year_id={y} -> {c}")
        except sqlite3.Error as e:
            print("Không đọc được staff_year_records:", e)

        print("\n" + "=" * 150)
        print("KẾT LUẬN KHẢO SÁT")
        print("=" * 150)
        print(f"SOURCE ĐÃ KHÓA: school_id={SOURCE_SCHOOL_ID} | code={SOURCE_CODE} | {SOURCE_NAME}")
        print("CHƯA GHI DATABASE.")
        print("CHƯA SÁP NHẬP.")
        print("MỤC TIÊU: XÁC ĐỊNH ĐÚNG TARGET TRƯỚC KHI PREVIEW/COMMIT.")
    finally:
        conn.close()

    sha_after = sha256_file(db)
    print("\n" + "=" * 150)
    print("FILE SAFETY")
    print("=" * 150)
    print("DB:", sha_before, "->", sha_after)
    if sha_before != sha_after:
        print("CẢNH BÁO: DATABASE ĐÃ THAY ĐỔI")
        sys.exit(3)

    print("\n" + "=" * 150)
    print("KHẢO SÁT MẬU ĐÔN HOÀN TẤT")
    print("DATABASE = KHÔNG THAY ĐỔI")
    print("KHÔNG SÁP NHẬP")
    print("=" * 150)

if __name__ == "__main__":
    main()
