import sqlite3
import unicodedata
import re
from pathlib import Path

DB = Path(r"C:\PhoCap\data\phocap.db")

def norm(v):
    s = str(v or "").strip().lower()
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    s = s.replace("đ", "d")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()

con = sqlite3.connect(DB.resolve().as_uri() + "?mode=ro", uri=True)
con.row_factory = sqlite3.Row
con.execute("PRAGMA query_only=ON")

year = con.execute("""
SELECT id, code
FROM school_years
WHERE REPLACE(REPLACE(code,'–','-'),'—','-')='2025-2026'
LIMIT 1
""").fetchone()

print("=" * 110)
print("QD3805-OP-0282 - MN THỊ TRẤN MƯỜNG XÉN")
print("READ-ONLY - KHÔNG GHI DATABASE")
print("DB:", DB)
print("Năm:", dict(year) if year else None)
print("=" * 110)

if not year:
    raise SystemExit("Không tìm thấy năm 2025-2026")

rows = con.execute("""
SELECT
    s.id AS school_id,
    s.code AS school_code,
    s.name AS school_name,
    c.id AS commune_id,
    c.name AS commune_name,
    sny.school_year_id,
    sny.level_code,
    sny.source_name
FROM school_network_year_data sny
JOIN schools s ON s.id=sny.school_id
LEFT JOIN communes c ON c.id=s.commune_id
WHERE sny.school_year_id=?
  AND UPPER(TRIM(sny.level_code))='MN'
ORDER BY s.id
""", (year["id"],)).fetchall()

print("\n--- TRONG MẠNG LƯỚI MN 2025-2026 ---")

count = 0
for r in rows:
    text = " | ".join([
        norm(r["school_name"]),
        norm(r["source_name"]),
        norm(r["commune_name"])
    ])

    if (
        "muong xen" in text
        or ("muong" in text and "xen" in text)
    ):
        count += 1
        print("\n" + "-" * 100)
        for k in r.keys():
            print(f"{k} = {r[k]}")

print("\nSố bản ghi mạng lưới khớp:", count)

print("\n" + "=" * 110)
print("--- KIỂM TRA TOÀN BỘ BẢNG schools ---")
print("=" * 110)

rows2 = con.execute("""
SELECT
    s.id AS school_id,
    s.code AS school_code,
    s.name AS school_name,
    c.id AS commune_id,
    c.name AS commune_name
FROM schools s
LEFT JOIN communes c ON c.id=s.commune_id
ORDER BY s.id
""").fetchall()

count2 = 0
for r in rows2:
    text = norm(r["school_name"]) + " | " + norm(r["commune_name"])

    if (
        "muong xen" in text
        or ("muong" in text and "xen" in text)
    ):
        count2 += 1
        print("\n" + "-" * 100)
        for k in r.keys():
            print(f"{k} = {r[k]}")

print("\nSố bản ghi schools khớp:", count2)

con.close()
