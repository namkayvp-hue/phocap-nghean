import sys
import sqlite3
import hashlib
from pathlib import Path
from collections import Counter, defaultdict

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(r"C:\PhoCap")
DB = ROOT / "data" / "phocap.db"

PREVIOUS_IDS = (748, 750, 751)
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
print("XÁC ĐỊNH HỒ SƠ THỨ 88 - OP-0337")
print("CHỈ ĐỌC - KHÔNG SỬA DB")
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
        "Không tìm thấy đủ năm 2025-2026 / 2026-2027."
    )

# ============================================================
# 1. XÁC ĐỊNH TẬP ELIGIBLE NĂM 2025-2026
# ============================================================

previous = con.execute(
    """
    SELECT
        syr.school_id,
        syr.staff_member_id,
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
    ORDER BY syr.school_id, sm.full_name
    """,
    (prev_id,),
).fetchall()

eligible = [
    dict(r)
    for r in previous
    if int(r["is_active"] or 0) == 1
    and str(r["status_code"] or "") == "DANG_LAM_VIEC"
]

print()
print("=" * 120)
print("1. KIỂM TRA SỐ ĐỦ ĐIỀU KIỆN NĂM TRƯỚC")
print("=" * 120)

by_school = Counter(
    int(r["school_id"])
    for r in eligible
)

for sid in PREVIOUS_IDS:
    print(
        sid,
        "=",
        by_school.get(sid, 0),
        "| kỳ vọng =",
        EXPECTED_PREVIOUS[sid],
    )

if any(
    by_school.get(sid, 0) != expected
    for sid, expected in EXPECTED_PREVIOUS.items()
):
    raise RuntimeError(
        "Cách xác định eligible chưa khớp V4.3. "
        "DỪNG để không suy diễn."
    )

previous_by_code = defaultdict(list)

for r in eligible:
    code = str(
        r["ministry_staff_code"] or ""
    ).strip()

    if not code:
        raise RuntimeError(
            "Có hồ sơ eligible năm trước thiếu mã Bộ."
        )

    previous_by_code[code].append(r)

duplicate_previous = {
    code: rows
    for code, rows in previous_by_code.items()
    if len(rows) > 1
}

print(
    "Tổng eligible năm trước :",
    len(eligible),
)
print(
    "Mã Bộ duy nhất          :",
    len(previous_by_code),
)
print(
    "Trùng mã giữa 3 trường  :",
    len(duplicate_previous),
)

if duplicate_previous:
    print()
    print("CÁC MÃ TRÙNG:")

    for code, rows in duplicate_previous.items():
        print(code)

        for r in rows:
            print("   ", r)

# ============================================================
# 2. ACTIVE 2026-2027 TẠI NGHI DIÊN
# ============================================================

current_rows = con.execute(
    """
    SELECT
        syr.id AS year_record_id,
        syr.school_id,
        syr.staff_member_id,
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
      AND syr.school_id=?
      AND syr.is_active=1
    ORDER BY sm.full_name, sm.ministry_staff_code
    """,
    (curr_id, TARGET_ID),
).fetchall()

current = [
    dict(r)
    for r in current_rows
]

current_by_code = defaultdict(list)

for r in current:
    code = str(
        r["ministry_staff_code"] or ""
    ).strip()

    if not code:
        raise RuntimeError(
            "Có hồ sơ hiện tại thiếu mã Bộ."
        )

    current_by_code[code].append(r)

print()
print("=" * 120)
print("2. NĂM 2026-2027 TẠI MN NGHI DIÊN")
print("=" * 120)

print(
    "Active rows        :",
    len(current),
)
print(
    "Mã Bộ duy nhất     :",
    len(current_by_code),
)

# ============================================================
# 3. SO SÁNH
# ============================================================

prev_codes = set(previous_by_code)
curr_codes = set(current_by_code)

extra = sorted(
    curr_codes - prev_codes
)

missing = sorted(
    prev_codes - curr_codes
)

print()
print("=" * 120)
print("3. SO SÁNH 87 NĂM TRƯỚC VỚI 88 HIỆN TẠI")
print("=" * 120)

print(
    "Có ở CURRENT nhưng không ở PREVIOUS eligible:",
    len(extra),
)

print(
    "Có ở PREVIOUS eligible nhưng thiếu CURRENT   :",
    len(missing),
)

print()
print("EXTRA CURRENT:")

if not extra:
    print("<KHÔNG CÓ>")
else:
    for code in extra:
        for r in current_by_code[code]:
            print(r)

print()
print("MISSING CURRENT:")

if not missing:
    print("<KHÔNG CÓ>")
else:
    for code in missing:
        for r in previous_by_code[code]:
            print(r)

# ============================================================
# 4. LỊCH SỬ CÁC MÃ CHÊNH
# ============================================================

trace_codes = sorted(
    set(extra + missing)
)

print()
print("=" * 120)
print("4. LỊCH SỬ CÁC HỒ SƠ CHÊNH")
print("=" * 120)

if not trace_codes:
    print("<KHÔNG CÓ MÃ CHÊNH>")
else:
    for code in trace_codes:

        print()
        print("-" * 120)
        print("MÃ BỘ:", code)

        rows = con.execute(
            """
            SELECT
                sy.code AS school_year,
                syr.id AS year_record_id,
                syr.school_id,
                s.code AS school_code,
                s.name AS school_name,
                syr.status_code,
                syr.source_status_label,
                syr.position_group,
                syr.position_title,
                syr.is_active,
                sm.id AS staff_member_id,
                sm.full_name,
                sm.date_of_birth,
                sm.gender
            FROM staff_members sm
            LEFT JOIN staff_year_records syr
              ON syr.staff_member_id=sm.id
            LEFT JOIN school_years sy
              ON sy.id=syr.school_year_id
            LEFT JOIN schools s
              ON s.id=syr.school_id
            WHERE sm.ministry_staff_code=?
            ORDER BY sy.code, syr.id
            """,
            (code,),
        ).fetchall()

        for r in rows:
            print(dict(r))

        user_rows = con.execute(
            """
            SELECT
                id,
                username,
                full_name,
                school_id,
                role_id,
                is_active
            FROM users
            WHERE username LIKE ?
               OR full_name IN (
                    SELECT full_name
                    FROM staff_members
                    WHERE ministry_staff_code=?
               )
            ORDER BY id
            """,
            (
                "%" + code + "%",
                code,
            ),
        ).fetchall()

        if user_rows:
            print("USERS:")

            for r in user_rows:
                print(
                    "   ",
                    dict(r),
                )

# ============================================================
# 5. CƠ CẤU
# ============================================================

print()
print("=" * 120)
print("5. CƠ CẤU 87 PREVIOUS ELIGIBLE / 88 CURRENT")
print("=" * 120)

print("PREVIOUS:")

for k, v in Counter(
    str(r.get("position_group") or "")
    for r in eligible
).items():
    print(
        " ",
        k,
        "=",
        v,
    )

print("CURRENT:")

for k, v in Counter(
    str(r.get("position_group") or "")
    for r in current
).items():
    print(
        " ",
        k,
        "=",
        v,
    )

con.close()

db_after = sha256(DB)

print()
print("=" * 120)
print("KIỂM TRA AN TOÀN")
print("=" * 120)

print(
    "DB hash trước:",
    db_before,
)

print(
    "DB hash sau  :",
    db_after,
)

if db_before != db_after:
    raise RuntimeError(
        "DỪNG: database thay đổi ngoài dự kiến."
    )

print(
    "Database     : KHÔNG THAY ĐỔI"
)

print("=" * 120)
