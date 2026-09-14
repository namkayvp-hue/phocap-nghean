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

TARGET_ID = 747
SOURCE_ID = 749

EXPECTED_DB_SHA = (
    "44b1aa841cdd76301c57d9fc601121ae"
    "96f9312084ef05959eaae54acf17c8c9"
)

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

print("=" * 120)
print("KIEM CHUNG OP-0338 DA HOAN TAT TRUOC HAY CHUA")
print("MN NGHI TRUNG 749 -> MN TT QUAN HANH 747")
print("CHI DOC - KHONG MO KHOA - KHONG GHI DATABASE")
print("=" * 120)

print("DB SHA:", db_before)

if db_before != EXPECTED_DB_SHA:
    raise RuntimeError(
        "DUNG: DB khong con dung nen vua cai dat."
    )

con = sqlite3.connect(
    DB.resolve().as_uri() + "?mode=ro",
    uri=True,
    timeout=30,
)
con.row_factory = sqlite3.Row
con.execute("PRAGMA query_only=ON")

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
        "Khong tim thay du 2025-2026 / 2026-2027."
    )

# ============================================================
# 1. SCHOOL STATE
# ============================================================

print()
print("=" * 120)
print("1. TRANG THAI TRUONG")
print("=" * 120)

schools = con.execute(
    """
    SELECT
        s.id,
        s.code,
        s.name,
        s.is_active,
        c.name AS commune_name
    FROM schools s
    LEFT JOIN communes c
      ON c.id=s.commune_id
    WHERE s.id IN (747,749)
    ORDER BY s.id
    """
).fetchall()

for r in schools:
    print(dict(r))

school_map = {
    int(r["id"]): dict(r)
    for r in schools
}

# ============================================================
# 2. PREVIOUS ELIGIBLE
# ============================================================

print()
print("=" * 120)
print("2. PREVIOUS ELIGIBLE 2025-2026")
print("=" * 120)

previous_rows = con.execute(
    """
    SELECT
        syr.staff_member_id,
        syr.school_id,
        syr.status_code,
        syr.source_status_label,
        syr.position_group,
        syr.is_active,
        sm.ministry_staff_code,
        sm.full_name
    FROM staff_year_records syr
    JOIN staff_members sm
      ON sm.id=syr.staff_member_id
    WHERE syr.school_year_id=?
      AND syr.school_id IN (747,749)
    ORDER BY syr.school_id,syr.staff_member_id
    """,
    (prev_id,),
).fetchall()

eligible = [
    dict(r)
    for r in previous_rows
    if int(r["is_active"] or 0) == 1
    and str(r["status_code"] or "") == "DANG_LAM_VIEC"
]

by_school = {}

for r in eligible:
    sid = int(r["school_id"])
    by_school[sid] = by_school.get(sid, 0) + 1

print("747 previous eligible =", by_school.get(747, 0))
print("749 previous eligible =", by_school.get(749, 0))
print("Union previous        =", len(eligible))

previous_ids = {
    int(r["staff_member_id"])
    for r in eligible
}

print(
    "Unique staff_member_id previous =",
    len(previous_ids),
)

# ============================================================
# 3. CURRENT TARGET
# ============================================================

print()
print("=" * 120)
print("3. CURRENT 2026-2027")
print("=" * 120)

current_target = con.execute(
    """
    SELECT
        syr.staff_member_id,
        syr.position_group,
        syr.status_code,
        syr.is_active,
        sm.ministry_staff_code,
        sm.full_name
    FROM staff_year_records syr
    JOIN staff_members sm
      ON sm.id=syr.staff_member_id
    WHERE syr.school_year_id=?
      AND syr.school_id=747
      AND syr.is_active=1
    ORDER BY syr.staff_member_id
    """,
    (curr_id,),
).fetchall()

current_ids = {
    int(r["staff_member_id"])
    for r in current_target
}

print(
    "Current target active =",
    len(current_target),
)

print(
    "Unique current IDs    =",
    len(current_ids),
)

# ============================================================
# 4. CURRENT SOURCE RESIDUAL
# ============================================================

print()
print("=" * 120)
print("4. CURRENT SOURCE RESIDUAL")
print("=" * 120)

source_current = con.execute(
    """
    SELECT COUNT(*) AS n
    FROM staff_year_records
    WHERE school_year_id=?
      AND school_id=749
    """,
    (curr_id,),
).fetchone()

source_current_total = int(
    source_current["n"] or 0
)

print(
    "staff_year_records tai source 749 =",
    source_current_total,
)

# ============================================================
# 5. IDENTITY EXACT
# ============================================================

print()
print("=" * 120)
print("5. DOI CHIEU IDENTITY")
print("=" * 120)

extra = sorted(
    current_ids - previous_ids
)

missing = sorted(
    previous_ids - current_ids
)

print("Extra current  =", extra)
print("Missing current=", missing)
print(
    "Identity exact =",
    current_ids == previous_ids,
)

# ============================================================
# 6. CO CAU
# ============================================================

print()
print("=" * 120)
print("6. CO CAU CURRENT TARGET")
print("=" * 120)

structure = {}

for r in current_target:
    key = str(
        r["position_group"] or ""
    )
    structure[key] = (
        structure.get(key, 0) + 1
    )

print(
    json.dumps(
        structure,
        ensure_ascii=False,
    )
)

# ============================================================
# 7. USERS SOURCE/TARGET
# ============================================================

print()
print("=" * 120)
print("7. USERS TRUONG")
print("=" * 120)

users = con.execute(
    """
    SELECT
        id,
        username,
        full_name,
        school_id,
        is_active
    FROM users
    WHERE school_id IN (747,749)
      AND username LIKE 'truong_%'
    ORDER BY school_id,id
    """
).fetchall()

for r in users:
    print(dict(r))

# ============================================================
# 8. KET LUAN
# ============================================================

target_active = (
    int(
        school_map.get(747, {})
        .get("is_active") or 0
    )
    == 1
)

source_inactive = (
    int(
        school_map.get(749, {})
        .get("is_active") or 0
    )
    == 0
)

identity_exact = (
    current_ids == previous_ids
)

print()
print("=" * 120)
print("8. KET LUAN CO HOC")
print("=" * 120)

print("Target 747 active        =", target_active)
print("Source 749 inactive      =", source_inactive)
print("Source current residual  =", source_current_total)
print("Previous union           =", len(previous_ids))
print("Current target           =", len(current_ids))
print("Identity exact           =", identity_exact)

if (
    target_active
    and source_inactive
    and source_current_total == 0
    and identity_exact
    and len(previous_ids) > 0
):
    print()
    print(
        "KET LUAN: OP-0338 CO DU DAU VET "
        "DA HOAN TAT TRUOC."
    )
    print(
        "KHONG DUOC MO KHOA 749 VA KHONG "
        "DUOC CHAY LAI 749 -> 747."
    )
else:
    print()
    print(
        "CHUA DU BANG CHUNG DE DANH DAU DONE."
    )

con.close()

db_after = sha256(DB)

print()
print("=" * 120)
print("KIEM TRA AN TOAN")
print("=" * 120)

print("DB SHA truoc:", db_before)
print("DB SHA sau  :", db_after)

if db_before != db_after:
    raise RuntimeError(
        "DUNG: database da thay doi."
    )

print("Database     : KHONG THAY DOI")
print("=" * 120)
