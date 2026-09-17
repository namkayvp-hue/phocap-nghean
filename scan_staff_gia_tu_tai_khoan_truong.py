import sys
import sqlite3
import hashlib
import json
from pathlib import Path
from collections import Counter

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(r"C:\PhoCap")
DB = ROOT / "data" / "phocap.db"

def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            b = f.read(1024 * 1024)
            if not b:
                break
            h.update(b)
    return h.hexdigest()

db_before = sha256(DB)

con = sqlite3.connect(
    DB.resolve().as_uri() + "?mode=ro",
    uri=True,
    timeout=30,
)
con.row_factory = sqlite3.Row
con.execute("PRAGMA query_only=ON")

print("=" * 120)
print("SCAN HO SO NHAN SU PHAT SINH TU TAI KHOAN/TRUONG")
print("READ ONLY - KHONG SUA DATABASE")
print("=" * 120)

# ============================================================
# 1. Staff co ten trung chinh xac ten truong
# ============================================================

rows_school_name = con.execute(
    """
    SELECT
        sm.id AS staff_member_id,
        sm.code AS staff_code,
        sm.ministry_staff_code,
        sm.full_name,
        sm.date_of_birth,
        sm.gender,
        sm.is_active AS staff_is_active,
        sm.created_at,

        s.id AS matched_school_id,
        s.code AS matched_school_code,
        s.name AS matched_school_name,
        s.is_active AS matched_school_active

    FROM staff_members sm
    JOIN schools s
      ON LOWER(TRIM(sm.full_name))
       = LOWER(TRIM(s.name))

    ORDER BY sm.id
    """
).fetchall()

print()
print("=" * 120)
print("1. STAFF_MEMBER CO TEN TRUNG TEN TRUONG")
print("=" * 120)
print("So luong:", len(rows_school_name))

for r in rows_school_name:
    print(
        json.dumps(
            dict(r),
            ensure_ascii=True,
            default=str,
        )
    )

# ============================================================
# 2. Staff thieu ma Bo + ten trung ten truong
# ============================================================

suspect_school = [
    dict(r)
    for r in rows_school_name
    if not str(r["ministry_staff_code"] or "").strip()
]

print()
print("=" * 120)
print("2. NGHI NGO CAO: TEN TRUNG TEN TRUONG + THIEU MA BO")
print("=" * 120)
print("So luong:", len(suspect_school))

for r in suspect_school:
    print(
        json.dumps(
            r,
            ensure_ascii=True,
            default=str,
        )
    )

# ============================================================
# 3. Staff co ten trung user truong_*
# ============================================================

rows_users = con.execute(
    """
    SELECT
        sm.id AS staff_member_id,
        sm.code AS staff_code,
        sm.ministry_staff_code,
        sm.full_name AS staff_full_name,
        sm.date_of_birth,
        sm.gender,
        sm.is_active AS staff_is_active,
        sm.created_at,

        u.id AS user_id,
        u.username,
        u.full_name AS user_full_name,
        u.school_id AS user_school_id,
        u.is_active AS user_is_active

    FROM staff_members sm
    JOIN users u
      ON LOWER(TRIM(sm.full_name))
       = LOWER(TRIM(u.full_name))

    WHERE u.username LIKE 'truong_%'

    ORDER BY sm.id,u.id
    """
).fetchall()

print()
print("=" * 120)
print("3. STAFF_MEMBER CO TEN TRUNG TAI KHOAN TRUONG")
print("=" * 120)
print("So luong:", len(rows_users))

for r in rows_users:
    print(
        json.dumps(
            dict(r),
            ensure_ascii=True,
            default=str,
        )
    )

# ============================================================
# 4. Ho so nghi ngo dang co year_record
# ============================================================

suspect_ids = sorted({
    int(r["staff_member_id"])
    for r in suspect_school
} | {
    int(r["staff_member_id"])
    for r in rows_users
    if not str(r["ministry_staff_code"] or "").strip()
})

print()
print("=" * 120)
print("4. YEAR RECORD CUA CAC HO SO NGHI NGO")
print("=" * 120)

all_year_rows = []

for staff_id in suspect_ids:

    records = con.execute(
        """
        SELECT
            syr.id AS year_record_id,
            syr.staff_member_id,
            sy.code AS school_year,
            syr.school_id,
            s.code AS school_code,
            s.name AS school_name,
            syr.status_code,
            syr.source_status_label,
            syr.position_group,
            syr.position_title,
            syr.is_active
        FROM staff_year_records syr

        JOIN school_years sy
          ON sy.id=syr.school_year_id

        JOIN schools s
          ON s.id=syr.school_id

        WHERE syr.staff_member_id=?

        ORDER BY sy.code,syr.id
        """,
        (staff_id,),
    ).fetchall()

    print()
    print("staff_member_id =", staff_id)

    for r in records:
        d = dict(r)
        all_year_rows.append(d)

        print(
            json.dumps(
                d,
                ensure_ascii=True,
                default=str,
            )
        )

# ============================================================
# 5. Rieng nam 2026-2027
# ============================================================

current_suspects = [
    r
    for r in all_year_rows
    if str(r.get("school_year") or "") == "2026-2027"
    and int(r.get("is_active") or 0) == 1
]

print()
print("=" * 120)
print("5. HO SO NGHI NGO DANG ACTIVE NAM 2026-2027")
print("=" * 120)

print("So luong:", len(current_suspects))

for r in current_suspects:
    print(
        json.dumps(
            r,
            ensure_ascii=True,
            default=str,
        )
    )

# ============================================================
# 6. Cum created_at
# ============================================================

print()
print("=" * 120)
print("6. THONG KE THOI DIEM TAO STAFF NGHI NGO")
print("=" * 120)

created = Counter()

for r in suspect_school:
    value = str(r.get("created_at") or "")
    created[value[:19]] += 1

for k, v in created.most_common():
    print(k, "=", v)

# ============================================================
# 7. Kiem tra rieng 51394
# ============================================================

print()
print("=" * 120)
print("7. KIEM TRA RIENG STAFF_MEMBER_ID 51394")
print("=" * 120)

row = con.execute(
    """
    SELECT *
    FROM staff_members
    WHERE id=51394
    """
).fetchone()

print(
    json.dumps(
        dict(row) if row else None,
        ensure_ascii=True,
        default=str,
    )
)

# ============================================================
# 8. Tong ket
# ============================================================

print()
print("=" * 120)
print("8. TONG KET")
print("=" * 120)

print(
    "staff ten trung ten truong              =",
    len(rows_school_name),
)

print(
    "staff ten trung ten truong + thieu ma Bo=",
    len(suspect_school),
)

print(
    "staff ten trung tai khoan truong        =",
    len(rows_users),
)

print(
    "ho so nghi ngo active 2026-2027        =",
    len(current_suspects),
)

if len(suspect_school) == 1 and suspect_ids == [51394]:
    print()
    print(
        "KET QUA: 51394 co dau hieu la loi DON LE."
    )
else:
    print()
    print(
        "KET QUA: Co NHIEU hon 1 ho so cung mau loi; "
        "khong duoc sua rieng 51394."
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
        "DUNG: database da thay doi ngoai du kien."
    )

print("Database     : KHONG THAY DOI")
print("=" * 120)
