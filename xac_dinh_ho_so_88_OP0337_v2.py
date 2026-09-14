import sys
import sqlite3
import hashlib
from pathlib import Path
from collections import Counter

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(r"C:\PhoCap")
DB = ROOT / "data" / "phocap.db"

SCHOOL_IDS = (748, 750, 751)
TARGET_ID = 748

EXPECTED_PREVIOUS = {
    748: 29,
    750: 25,
    751: 33,
}

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
print("XAC DINH HO SO THU 88 - OP-0337 - V2")
print("CHI DOC - KHONG SUA DATABASE")
print("=" * 120)

years = {
    str(r["code"] or "")
    .replace("–", "-")
    .replace("—", "-")
    .strip(): int(r["id"])
    for r in con.execute(
        "SELECT id,code FROM school_years"
    ).fetchall()
}

prev_id = years.get("2025-2026")
curr_id = years.get("2026-2027")

if prev_id is None or curr_id is None:
    raise RuntimeError(
        "Khong tim thay nam hoc 2025-2026 / 2026-2027."
    )

# ============================================================
# 1. PREVIOUS ELIGIBLE
# ============================================================

previous = [
    dict(r)
    for r in con.execute(
        """
        SELECT
            syr.id AS year_record_id,
            syr.staff_member_id,
            syr.school_id,
            syr.status_code,
            syr.source_status_label,
            syr.position_group,
            syr.position_title,
            syr.is_active,

            sm.ministry_staff_code,
            sm.full_name,
            sm.date_of_birth,
            sm.gender,

            s.code AS school_code,
            s.name AS school_name

        FROM staff_year_records syr

        JOIN staff_members sm
          ON sm.id=syr.staff_member_id

        JOIN schools s
          ON s.id=syr.school_id

        WHERE syr.school_year_id=?
          AND syr.school_id IN (748,750,751)

        ORDER BY
            syr.school_id,
            syr.staff_member_id
        """,
        (prev_id,),
    ).fetchall()
]

eligible = [
    r
    for r in previous
    if int(r.get("is_active") or 0) == 1
    and str(r.get("status_code") or "") == "DANG_LAM_VIEC"
]

counts = Counter(
    int(r["school_id"])
    for r in eligible
)

print()
print("=" * 120)
print("1. PREVIOUS ELIGIBLE 2025-2026")
print("=" * 120)

for sid in SCHOOL_IDS:
    print(
        sid,
        "=",
        counts.get(sid, 0),
        "| expected =",
        EXPECTED_PREVIOUS[sid],
    )

if any(
    counts.get(sid, 0) != expected
    for sid, expected in EXPECTED_PREVIOUS.items()
):
    raise RuntimeError(
        "Previous eligible khong khop V4.3."
    )

prev_member_ids = {
    int(r["staff_member_id"])
    for r in eligible
}

prev_codes = {
    str(r.get("ministry_staff_code") or "").strip()
    for r in eligible
    if str(r.get("ministry_staff_code") or "").strip()
}

print("Previous eligible rows =", len(eligible))
print("Previous member_ids    =", len(prev_member_ids))
print("Previous ma Bo         =", len(prev_codes))

# ============================================================
# 2. CURRENT ACTIVE 2026-2027
# ============================================================

current = [
    dict(r)
    for r in con.execute(
        """
        SELECT
            syr.id AS year_record_id,
            syr.staff_member_id,
            syr.school_id,
            syr.status_code,
            syr.source_status_label,
            syr.position_group,
            syr.position_title,
            syr.is_active,

            sm.ministry_staff_code,
            sm.full_name,
            sm.date_of_birth,
            sm.gender,

            s.code AS school_code,
            s.name AS school_name

        FROM staff_year_records syr

        JOIN staff_members sm
          ON sm.id=syr.staff_member_id

        JOIN schools s
          ON s.id=syr.school_id

        WHERE syr.school_year_id=?
          AND syr.school_id=748
          AND syr.is_active=1

        ORDER BY
            syr.staff_member_id
        """,
        (curr_id,),
    ).fetchall()
]

curr_member_ids = {
    int(r["staff_member_id"])
    for r in current
}

curr_codes = {
    str(r.get("ministry_staff_code") or "").strip()
    for r in current
    if str(r.get("ministry_staff_code") or "").strip()
}

missing_code_rows = [
    r
    for r in current
    if not str(r.get("ministry_staff_code") or "").strip()
]

print()
print("=" * 120)
print("2. CURRENT ACTIVE 2026-2027 - SCHOOL 748")
print("=" * 120)

print("Current active rows    =", len(current))
print("Current member_ids     =", len(curr_member_ids))
print("Current ma Bo co gia tri =", len(curr_codes))
print("Current thieu ma Bo    =", len(missing_code_rows))

print()
print("HO SO THIEU MA BO:")

if not missing_code_rows:
    print("<KHONG CO>")
else:
    for r in missing_code_rows:
        print(r)

# ============================================================
# 3. SO SANH BANG STAFF_MEMBER_ID
# ============================================================

extra_member_ids = sorted(
    curr_member_ids - prev_member_ids
)

missing_member_ids = sorted(
    prev_member_ids - curr_member_ids
)

print()
print("=" * 120)
print("3. SO SANH BANG STAFF_MEMBER_ID")
print("=" * 120)

print(
    "Current co them member_id =",
    len(extra_member_ids),
    extra_member_ids,
)

print(
    "Previous bi thieu current =",
    len(missing_member_ids),
    missing_member_ids,
)

# ============================================================
# 4. SO SANH MA BO KHONG RONG
# ============================================================

extra_codes = sorted(
    curr_codes - prev_codes
)

missing_codes = sorted(
    prev_codes - curr_codes
)

print()
print("=" * 120)
print("4. SO SANH MA BO")
print("=" * 120)

print(
    "Ma Bo moi trong current =",
    len(extra_codes),
    extra_codes,
)

print(
    "Ma Bo previous thieu current =",
    len(missing_codes),
    missing_codes,
)

# ============================================================
# 5. CHI TIET CAC MEMBER_ID CHENH
# ============================================================

diff_ids = sorted(
    set(extra_member_ids + missing_member_ids)
)

# Luon them member_id cua ho so thieu ma Bo de truy vet.
for r in missing_code_rows:
    sid = int(r["staff_member_id"])
    if sid not in diff_ids:
        diff_ids.append(sid)

diff_ids = sorted(set(diff_ids))

print()
print("=" * 120)
print("5. LICH SU CAC HO SO CHENH / THIEU MA BO")
print("=" * 120)

if not diff_ids:
    print("<KHONG CO>")
else:
    for staff_member_id in diff_ids:

        print()
        print("-" * 120)
        print("staff_member_id =", staff_member_id)

        master = con.execute(
            """
            SELECT *
            FROM staff_members
            WHERE id=?
            """,
            (staff_member_id,),
        ).fetchone()

        if master is not None:
            print("STAFF_MEMBER:")
            print(dict(master))

        history = con.execute(
            """
            SELECT
                sy.code AS school_year,
                syr.id AS year_record_id,
                syr.staff_member_id,
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

            ORDER BY
                sy.code,
                syr.id
            """,
            (staff_member_id,),
        ).fetchall()

        print("YEAR RECORDS:")

        for r in history:
            print(dict(r))

        users = con.execute(
            """
            SELECT
                id,
                username,
                full_name,
                school_id,
                role_id,
                is_active
            FROM users
            WHERE full_name=(
                SELECT full_name
                FROM staff_members
                WHERE id=?
            )
            ORDER BY id
            """,
            (staff_member_id,),
        ).fetchall()

        if users:
            print("USERS:")

            for r in users:
                print(dict(r))

# ============================================================
# 6. KET LUAN CO HOC
# ============================================================

print()
print("=" * 120)
print("6. KET LUAN CO HOC")
print("=" * 120)

print("Previous eligible =", len(prev_member_ids))
print("Current active     =", len(curr_member_ids))

if (
    len(prev_member_ids) == 87
    and len(curr_member_ids) == 88
    and len(extra_member_ids) == 1
    and len(missing_member_ids) == 0
):
    extra_id = extra_member_ids[0]

    print()
    print(
        "DUNG 1 STAFF_MEMBER_ID PHAT SINH THEM:",
        extra_id,
    )

    missing_code_ids = {
        int(r["staff_member_id"])
        for r in missing_code_rows
    }

    if extra_id in missing_code_ids:
        print(
            "HO SO PHAT SINH THEM CHINH LA HO SO "
            "DANG THIEU MA BO."
        )
    else:
        print(
            "HO SO PHAT SINH THEM KHONG PHAI "
            "HO SO THIEU MA BO."
        )

elif len(extra_member_ids) == 0 and len(missing_member_ids) == 0:
    print(
        "88 rows nhung identity member_id khong tang; "
        "can kiem tra duplicate."
    )

else:
    print(
        "CO BIEN DONG PHUC TAP HON +1; "
        "CHUA DUOC KET LUAN OP-0337."
    )

# ============================================================
# SAFETY
# ============================================================

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
