import sqlite3
import unicodedata
import re
from pathlib import Path
from difflib import SequenceMatcher

DB = Path(r"C:\PhoCap\data\phocap.db")

def norm(v):
    s = str(v or "").strip().lower()
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    s = s.replace("đ", "d")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()

EXPECTED = "Mầm non Tiền Phong"
expected_norm = norm(EXPECTED)

print("=" * 110)
print("KIỂM TRA ĐÚNG DB QD3805-OP-0410")
print("DB:", DB)
print("READ-ONLY - KHÔNG GHI DATABASE")
print("=" * 110)

uri = DB.resolve().as_uri() + "?mode=ro"

con = sqlite3.connect(uri, uri=True)
con.row_factory = sqlite3.Row
con.execute("PRAGMA query_only=ON")

year = con.execute("""
    SELECT id, code
    FROM school_years
    WHERE REPLACE(REPLACE(code,'–','-'),'—','-')='2025-2026'
    LIMIT 1
""").fetchone()

print("\nNĂM HỌC:")
print(dict(year) if year else "KHÔNG TÌM THẤY 2025-2026")

if not year:
    raise SystemExit()

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
    JOIN schools s ON s.id = sny.school_id
    LEFT JOIN communes c ON c.id = s.commune_id
    WHERE sny.school_year_id = ?
      AND UPPER(TRIM(sny.level_code)) = 'MN'
    ORDER BY s.id
""", (year["id"],)).fetchall()

print("\nTỔNG BẢN GHI MN 2025-2026:", len(rows))

matches = []

for r in rows:
    school_name = norm(r["school_name"])
    source_name = norm(r["source_name"])
    commune_name = norm(r["commune_name"])

    combined = " | ".join([
        school_name,
        source_name,
        commune_name,
    ])

    score = max(
        SequenceMatcher(None, expected_norm, school_name).ratio(),
        SequenceMatcher(None, expected_norm, source_name).ratio(),
    )

    interesting = (
        "tien phong" in combined
        or "hanh dich" in combined
        or ("tien" in combined and "phong" in combined)
        or score >= 0.60
    )

    if interesting:
        matches.append((score, r))

matches.sort(key=lambda x: x[0], reverse=True)

print("\n" + "=" * 110)
print("CÁC BẢN GHI CÓ KHẢ NĂNG KHỚP")
print("=" * 110)

for i, (score, r) in enumerate(matches[:50], 1):
    print(f"\n--- {i} | similarity={score:.3f} ---")
    print("school_id      =", r["school_id"])
    print("school_code    =", r["school_code"])
    print("school_name    =", r["school_name"])
    print("source_name    =", r["source_name"])
    print("commune_id     =", r["commune_id"])
    print("commune_name   =", r["commune_name"])
    print("school_year_id =", r["school_year_id"])
    print("level_code     =", r["level_code"])
    print("norm school    =", norm(r["school_name"]))
    print("norm source    =", norm(r["source_name"]))

print("\n" + "=" * 110)
print("KIỂM TRA RIÊNG TRƯỜNG CÓ CHỮ TIỀN / PHONG TRONG BẢNG schools")
print("=" * 110)

all_schools = con.execute("""
    SELECT
        s.id AS school_id,
        s.code AS school_code,
        s.name AS school_name,
        c.name AS commune_name
    FROM schools s
    LEFT JOIN communes c ON c.id=s.commune_id
    ORDER BY s.id
""").fetchall()

count = 0
for r in all_schools:
    txt = norm(r["school_name"]) + " | " + norm(r["commune_name"])
    if "tien phong" in txt or ("tien" in txt and "phong" in txt):
        count += 1
        print()
        print("school_id    =", r["school_id"])
        print("school_code  =", r["school_code"])
        print("school_name  =", r["school_name"])
        print("commune_name =", r["commune_name"])

print("\nSố bản ghi schools liên quan Tiền Phong:", count)

con.close()
