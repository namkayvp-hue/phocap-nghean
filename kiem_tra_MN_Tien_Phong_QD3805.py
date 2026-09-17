import sqlite3
import unicodedata
import re
from pathlib import Path

DB = Path(r"C:\PhoCap\phocap.db")

def norm(v):
    if v is None:
        return ""
    s = str(v).strip().lower()
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    s = s.replace("đ", "d")
    s = re.sub(r"\s+", " ", s)
    return s

def match_row(row):
    text = " | ".join(norm(v) for v in row)
    return (
        "tien phong" in text
        or "hanh dich" in text
        or ("tien" in text and "phong" in text)
    )

if not DB.exists():
    raise SystemExit(f"KHÔNG TÌM THẤY DB: {DB}")

uri = "file:" + DB.as_posix() + "?mode=ro"

conn = sqlite3.connect(uri, uri=True)
conn.execute("PRAGMA query_only = ON")

tables = [
    r[0]
    for r in conn.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type='table'
          AND name NOT LIKE 'sqlite_%'
        ORDER BY name
        """
    ).fetchall()
]

print("=" * 110)
print("KIỂM TRA READ-ONLY: MẦM NON TIỀN PHONG / HẠNH DỊCH")
print("DB:", DB)
print("KHÔNG GHI DATABASE")
print("=" * 110)

found = 0

for table in tables:
    try:
        cols_info = conn.execute(f'PRAGMA table_info("{table}")').fetchall()
        cols = [c[1] for c in cols_info]

        if not cols:
            continue

        rows = conn.execute(f'SELECT * FROM "{table}"').fetchall()

        matches = [row for row in rows if match_row(row)]

        if not matches:
            continue

        found += len(matches)

        print()
        print("#" * 110)
        print("TABLE:", table)
        print("CỘT :", cols)
        print("#" * 110)

        for i, row in enumerate(matches, 1):
            print(f"\n--- MATCH {i} ---")

            for col, val in zip(cols, row):
                if val is not None and str(val).strip() != "":
                    print(f"{col} = {val}")

    except Exception as e:
        print(f"[BỎ QUA TABLE {table}] {e}")

print()
print("=" * 110)
print("TỔNG SỐ DÒNG KHỚP:", found)
print("=" * 110)

conn.close()
