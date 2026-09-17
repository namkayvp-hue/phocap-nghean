import sqlite3
from pathlib import Path

DB = Path(r"C:\PhoCap\data\phocap.db")
con = sqlite3.connect(DB.resolve().as_uri() + "?mode=ro", uri=True)
con.row_factory = sqlite3.Row
con.execute("PRAGMA query_only=ON")

rows = con.execute("""
SELECT
    sy.code AS school_year,
    sny.school_year_id,
    sny.level_code,
    s.id AS school_id,
    s.code AS school_code,
    s.name AS school_name,
    c.name AS commune_name,
    sny.source_name
FROM school_network_year_data sny
JOIN schools s ON s.id=sny.school_id
JOIN school_years sy ON sy.id=sny.school_year_id
LEFT JOIN communes c ON c.id=s.commune_id
WHERE s.id IN (205,206)
ORDER BY sny.school_year_id,s.id
""").fetchall()

for r in rows:
    print("-" * 100)
    for k in r.keys():
        print(f"{k} = {r[k]}")

con.close()
