import sys
import sqlite3
import hashlib
import json
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(r"C:\PhoCap")
DB = ROOT / "data" / "phocap.db"

STAFF_ID = 51394
YEAR_RECORD_ID = 63788

def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            b = f.read(1024 * 1024)
            if not b:
                break
            h.update(b)
    return h.hexdigest()

def qi(name):
    return '"' + str(name).replace('"', '""') + '"'

db_before = sha256(DB)

con = sqlite3.connect(
    DB.resolve().as_uri() + "?mode=ro",
    uri=True,
    timeout=30,
)
con.row_factory = sqlite3.Row
con.execute("PRAGMA query_only=ON")

print("=" * 120)
print("KIEM TRA TOAN BO THAM CHIEU STAFF_MEMBER_ID 51394")
print("CHI DOC - KHONG XOA - KHONG SUA DATABASE")
print("=" * 120)

# ============================================================
# 1. MASTER
# ============================================================

print()
print("=" * 120)
print("1. STAFF_MEMBERS")
print("=" * 120)

r = con.execute(
    "SELECT * FROM staff_members WHERE id=?",
    (STAFF_ID,),
).fetchone()

print(
    json.dumps(
        dict(r) if r else None,
        ensure_ascii=False,
        default=str,
    )
)

# ============================================================
# 2. FULL YEAR RECORD 63788
# ============================================================

print()
print("=" * 120)
print("2. FULL STAFF_YEAR_RECORD 63788")
print("=" * 120)

r = con.execute(
    """
    SELECT
        syr.*,
        sy.code AS school_year_code,
        s.code AS school_code,
        s.name AS school_name
    FROM staff_year_records syr
    LEFT JOIN school_years sy
      ON sy.id=syr.school_year_id
    LEFT JOIN schools s
      ON s.id=syr.school_id
    WHERE syr.id=?
    """,
    (YEAR_RECORD_ID,),
).fetchone()

print(
    json.dumps(
        dict(r) if r else None,
        ensure_ascii=False,
        default=str,
    )
)

# ============================================================
# 3. FOREIGN KEY TRUC TIEP DEN staff_members
# ============================================================

print()
print("=" * 120)
print("3. CAC FOREIGN KEY THAM CHIEU STAFF_MEMBERS")
print("=" * 120)

tables = [
    str(r["name"])
    for r in con.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type='table'
          AND name NOT LIKE 'sqlite_%'
        ORDER BY name
        """
    ).fetchall()
]

fk_refs = []

for table in tables:
    try:
        fks = con.execute(
            f"PRAGMA foreign_key_list({qi(table)})"
        ).fetchall()
    except Exception:
        continue

    for fk in fks:
        # SQLite foreign_key_list:
        # id,seq,table,from,to,on_update,on_delete,match
        target_table = str(fk[2] or "")
        from_col = str(fk[3] or "")
        to_col = str(fk[4] or "")

        if target_table != "staff_members":
            continue

        item = {
            "table": table,
            "from_column": from_col,
            "to_column": to_col,
        }
        fk_refs.append(item)

        print(item)

# ============================================================
# 4. DU LIEU THUC TE DANG THAM CHIEU 51394
# ============================================================

print()
print("=" * 120)
print("4. CAC DONG DANG THAM CHIEU 51394")
print("=" * 120)

actual_refs = []

for item in fk_refs:
    table = item["table"]
    col = item["from_column"]

    try:
        rows = con.execute(
            f"""
            SELECT *
            FROM {qi(table)}
            WHERE {qi(col)}=?
            """,
            (STAFF_ID,),
        ).fetchall()
    except Exception as exc:
        print(
            table,
            "<QUERY ERROR>",
            repr(exc),
        )
        continue

    if not rows:
        continue

    print()
    print(
        table,
        "| column =",
        col,
        "| rows =",
        len(rows),
    )

    for row in rows:
        d = dict(row)
        actual_refs.append({
            "table": table,
            "column": col,
            "row": d,
        })

        print(
            json.dumps(
                d,
                ensure_ascii=False,
                default=str,
            )
        )

# ============================================================
# 5. SCAN TEN COT staff_member_id KE CA KHONG CO FK
# ============================================================

print()
print("=" * 120)
print("5. SCAN CAC COT TEN staff_member_id")
print("=" * 120)

manual_refs = []

for table in tables:
    try:
        cols = [
            str(r["name"])
            for r in con.execute(
                f"PRAGMA table_info({qi(table)})"
            ).fetchall()
        ]
    except Exception:
        continue

    candidate_cols = [
        c for c in cols
        if c.lower() == "staff_member_id"
    ]

    for col in candidate_cols:
        try:
            rows = con.execute(
                f"""
                SELECT *
                FROM {qi(table)}
                WHERE {qi(col)}=?
                """,
                (STAFF_ID,),
            ).fetchall()
        except Exception:
            continue

        if not rows:
            continue

        key = (table, col)

        print()
        print(
            table,
            "|",
            col,
            "| rows =",
            len(rows),
        )

        for row in rows:
            d = dict(row)
            manual_refs.append({
                "table": table,
                "column": col,
                "row": d,
            })

            print(
                json.dumps(
                    d,
                    ensure_ascii=False,
                    default=str,
                )
            )

# ============================================================
# 6. DOI CHIEU USER TRUONG NGHI HOA
# ============================================================

print()
print("=" * 120)
print("6. USER TRUONG NGHI HOA")
print("=" * 120)

rows = con.execute(
    """
    SELECT *
    FROM users
    WHERE id=12933
       OR username='truong_40429325'
    ORDER BY id
    """
).fetchall()

for r in rows:
    print(
        json.dumps(
            dict(r),
            ensure_ascii=False,
            default=str,
        )
    )

# ============================================================
# 7. TONG KET
# ============================================================

unique_ref_tables = sorted({
    x["table"]
    for x in actual_refs + manual_refs
})

print()
print("=" * 120)
print("7. TONG KET")
print("=" * 120)

print(
    "So bang FK den staff_members =",
    len(fk_refs),
)

print(
    "Bang dang co du lieu tham chieu 51394 =",
    unique_ref_tables,
)

print(
    "Tong dong FK tim thay =",
    len(actual_refs),
)

if unique_ref_tables == ["staff_year_records"]:
    print()
    print(
        "KET QUA: 51394 chi dang duoc su dung "
        "trong staff_year_records."
    )
    print(
        "=> Co the chuan bi phuong an don sach "
        "rieng co backup, nhung CHUA XOA trong buoc nay."
    )
else:
    print()
    print(
        "KET QUA: 51394 con tham chieu o bang khac."
    )
    print(
        "=> CHUA DUOC XOA; can xu ly cac tham chieu truoc."
    )

con.close()

db_after = sha256(DB)

print()
print("=" * 120)
print("KIEM TRA AN TOAN")
print("=" * 120)

print("DB hash truoc:", db_before)
print("DB hash sau  :", db_after)

if db_before != db_after:
    raise RuntimeError(
        "DUNG: database thay doi ngoai du kien."
    )

print("Database     : KHONG THAY DOI")
print("=" * 120)
