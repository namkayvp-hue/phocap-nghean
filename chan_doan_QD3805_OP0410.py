from pathlib import Path
import sqlite3
import os

ROOT = Path(r"C:\PhoCap")
INSTALLER = ROOT / "cai_dat_MN_QD3805_tach_3_dac_thu_va_khoa_ma_an_toan.py"

print("=" * 120)
print("CHẨN ĐOÁN READ-ONLY QD3805-OP-0410")
print("KHÔNG SỬA FILE - KHÔNG GHI DATABASE")
print("=" * 120)

# ----------------------------------------------------------------------
# 1. Xem bộ cài đang khai báo database thế nào
# ----------------------------------------------------------------------
print("\n[1] CÁC DÒNG LIÊN QUAN DATABASE TRONG BỘ CÀI")
print("-" * 120)

if INSTALLER.exists():
    lines = INSTALLER.read_text(encoding="utf-8", errors="replace").splitlines()

    keys = [
        "phocap.db",
        "sqlite3.connect",
        "db_path",
        "db_file",
        "database",
        "2025-2026",
        "resolve_missing_codes",
    ]

    for no, line in enumerate(lines, 1):
        low = line.lower()
        if any(k.lower() in low for k in keys):
            print(f"{no:04d}: {line}")
else:
    print("KHÔNG TÌM THẤY:", INSTALLER)


# ----------------------------------------------------------------------
# 2. Tìm mọi file có khả năng là SQLite DB
# ----------------------------------------------------------------------
print("\n[2] CÁC DATABASE TÌM THẤY TRONG C:\\PhoCap")
print("-" * 120)

candidates = []

for p in ROOT.rglob("*"):
    if not p.is_file():
        continue

    name = p.name.lower()
    suffix = p.suffix.lower()

    if suffix in {".db", ".sqlite", ".sqlite3"} or "phocap.db" in name:
        candidates.append(p)

if not candidates:
    print("KHÔNG TÌM THẤY FILE *.db / *.sqlite / *.sqlite3 TRONG C:\\PhoCap")
else:
    for i, p in enumerate(candidates, 1):
        st = p.stat()
        print(
            f"{i:02d}. {p}\n"
            f"    Size = {st.st_size:,} bytes"
        )


# ----------------------------------------------------------------------
# 3. Mở từng DB ở chế độ READ-ONLY và tìm Tiền Phong / Hạnh Dịch
# ----------------------------------------------------------------------
print("\n[3] TÌM BẢN GHI TIỀN PHONG / HẠNH DỊCH")
print("-" * 120)

patterns = [
    "%Tiền Phong%",
    "%Tiền%",
    "%Phong%",
    "%Tien Phong%",
    "%Hạnh Dịch%",
    "%Hạnh%",
    "%Dịch%",
    "%Hanh Dich%",
]

total_matches = 0
valid_db_count = 0

def qident(name):
    return '"' + name.replace('"', '""') + '"'

for db in candidates:
    print("\n" + "=" * 120)
    print("DATABASE:", db)
    print("=" * 120)

    try:
        uri = db.resolve().as_uri() + "?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
        conn.execute("PRAGMA query_only = ON")
        conn.execute("PRAGMA schema_version").fetchone()
        valid_db_count += 1
    except Exception as e:
        print("KHÔNG PHẢI SQLITE HỢP LỆ / KHÔNG MỞ ĐƯỢC:", e)
        continue

    try:
        tables = [
            r[0]
            for r in conn.execute("""
                SELECT name
                FROM sqlite_master
                WHERE type='table'
                  AND name NOT LIKE 'sqlite_%'
                ORDER BY name
            """).fetchall()
        ]

        print("Số bảng:", len(tables))

        db_matches = 0

        for table in tables:
            try:
                info = conn.execute(
                    f"PRAGMA table_info({qident(table)})"
                ).fetchall()

                cols = [r[1] for r in info]

                if not cols:
                    continue

                # Tìm trên tất cả các cột bằng CAST AS TEXT.
                clauses = []
                params = []

                for col in cols:
                    for pat in patterns:
                        clauses.append(
                            f"CAST({qident(col)} AS TEXT) LIKE ?"
                        )
                        params.append(pat)

                sql = (
                    f"SELECT * FROM {qident(table)} "
                    f"WHERE {' OR '.join(clauses)} "
                    f"LIMIT 50"
                )

                rows = conn.execute(sql, params).fetchall()

                if not rows:
                    continue

                print("\nTABLE:", table)
                print("COLUMNS:", cols)

                for idx, row in enumerate(rows, 1):
                    print(f"\n  --- MATCH {idx} ---")

                    for col, value in zip(cols, row):
                        if value is None:
                            continue

                        text = str(value).strip()

                        if text != "":
                            print(f"  {col} = {text}")

                    db_matches += 1
                    total_matches += 1

            except Exception as e:
                print(f"[BỎ QUA TABLE {table}] {e}")

        if db_matches == 0:
            print("\n>>> DB NÀY KHÔNG CÓ BẢN GHI KHỚP.")

    finally:
        conn.close()


print("\n" + "=" * 120)
print("KẾT QUẢ")
print("=" * 120)
print("SQLite DB hợp lệ :", valid_db_count)
print("Tổng bản ghi khớp:", total_matches)

if total_matches == 0:
    print("""
KHÔNG TÌM THẤY TIỀN PHONG/HẠNH DỊCH TRONG CÁC DB ĐÃ QUÉT.

Khi đó cần kiểm tra tiếp:
1. Bộ cài đang trỏ tới DB nằm ngoài C:\\PhoCap; hoặc
2. Tên trường lưu bằng cách viết hoàn toàn khác; hoặc
3. Bộ cài đang dùng một nguồn dữ liệu/bảng trung gian khác.
""")
else:
    print("""
ĐÃ TÌM THẤY BẢN GHI.
Hãy giữ nguyên toàn bộ kết quả phía trên để xác định:
- school_id
- mã trường
- tên trường thực tế
- năm học
- cấp học
- DB và bảng chứa dữ liệu
""")
