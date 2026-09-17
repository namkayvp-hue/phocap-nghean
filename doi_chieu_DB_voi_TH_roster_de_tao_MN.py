import sys
import json
import sqlite3
import hashlib
import unicodedata
from pathlib import Path
from collections import Counter, defaultdict

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(r"C:\PhoCap")
DB = ROOT / "data" / "phocap.db"
TH_JSON = ROOT / "data" / "school_merger_source_rosters" / "TH_2025_2026.json"

def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            b = f.read(1024 * 1024)
            if not b:
                break
            h.update(b)
    return h.hexdigest()

def norm(v):
    s = str(v or "").strip().lower()
    s = "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )
    s = s.replace("đ", "d")
    return " ".join(s.split())

def fmt_date(v):
    s = str(v or "").strip()
    if not s:
        return ""
    # DB thường YYYY-MM-DD
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        return f"{s[8:10]}/{s[5:7]}/{s[0:4]}"
    return s

db_before = sha256(DB)

th = json.loads(
    TH_JSON.read_text(encoding="utf-8")
)
th_rows = th.get("rows") or []

con = sqlite3.connect(
    DB.resolve().as_uri() + "?mode=ro",
    uri=True,
    timeout=30,
)
con.row_factory = sqlite3.Row
con.execute("PRAGMA query_only=ON")

year = con.execute(
    "SELECT id,code FROM school_years WHERE code='2025-2026' LIMIT 1"
).fetchone()

if not year:
    raise RuntimeError("Không tìm thấy năm 2025-2026.")

year_id = int(year["id"])

rows = con.execute(
    """
    SELECT
        syr.id AS year_record_id,
        syr.staff_member_id,
        syr.school_id,
        syr.status_code,
        syr.position_group,
        syr.position_title,
        syr.teaching_level,
        syr.source_level,
        syr.source_status_label,
        syr.is_active AS year_is_active,

        sm.ministry_staff_code,
        sm.full_name,
        sm.date_of_birth,
        sm.gender,
        sm.is_active AS member_is_active,

        s.code AS school_code,
        s.name AS school_name,
        c.name AS commune_name

    FROM staff_year_records syr
    JOIN staff_members sm
      ON sm.id = syr.staff_member_id
    JOIN schools s
      ON s.id = syr.school_id
    JOIN communes c
      ON c.id = s.commune_id

    WHERE syr.school_year_id=?
    """,
    (year_id,),
).fetchall()

data = [dict(r) for r in rows]

print("=" * 120)
print("ĐỐI CHIẾU CÔNG THỨC DB -> SOURCE ROSTER")
print("CHỈ ĐỌC - KHÔNG TẠO JSON - KHÔNG GHI DB")
print("=" * 120)

print()
print("Tổng staff_year_records 2025-2026:", len(data))
print("Tổng row TH JSON                  :", len(th_rows))

# ============================================================
# 1. Phân bố source_level / teaching_level
# ============================================================

print()
print("=" * 120)
print("1. PHÂN BỐ SOURCE_LEVEL")
print("=" * 120)

source_level_counts = Counter(
    str(x.get("source_level") or "<RỖNG>").strip()
    for x in data
)

for k, v in source_level_counts.most_common():
    print(f"{k!r}: {v}")

print()
print("=" * 120)
print("2. PHÂN BỐ TEACHING_LEVEL")
print("=" * 120)

teaching_level_counts = Counter(
    str(x.get("teaching_level") or "<RỖNG>").strip()
    for x in data
)

for k, v in teaching_level_counts.most_common():
    print(f"{k!r}: {v}")

# ============================================================
# 2. Kiểm tra TH JSON có khớp DB source_level=TH không
# ============================================================

db_th = [
    x for x in data
    if str(x.get("source_level") or "").strip().upper() == "TH"
]

print()
print("=" * 120)
print("3. SO SÁNH TH JSON VỚI DB source_level=TH")
print("=" * 120)

print("DB source_level=TH:", len(db_th))
print("TH JSON           :", len(th_rows))
print("Chênh lệch        :", len(db_th) - len(th_rows))

# Index DB theo mã cán bộ
by_code = defaultdict(list)

for x in db_th:
    code = str(x.get("ministry_staff_code") or "").strip()
    if code:
        by_code[code].append(x)

matched = 0
missing_code_in_db = []
multi_db = []
school_name_match = 0
commune_match = 0
status_exact = 0
dob_exact = 0
gender_exact = 0

position_pairs = Counter()
status_pairs = Counter()

for r in th_rows:
    code = str(r.get("staff_code") or "").strip()
    candidates = by_code.get(code) or []

    if not candidates:
        missing_code_in_db.append(r)
        continue

    # Ưu tiên đúng trường theo tên chuẩn hóa
    expected_school = norm(r.get("school_name"))
    expected_commune = norm(r.get("commune_name"))

    exact_school = [
        x for x in candidates
        if norm(x.get("school_name")) == expected_school
    ]

    if exact_school:
        x = exact_school[0]
    elif len(candidates) == 1:
        x = candidates[0]
    else:
        multi_db.append({
            "staff_code": code,
            "json_school": r.get("school_name"),
            "db_schools": [
                y.get("school_name")
                for y in candidates
            ],
        })
        continue

    matched += 1

    if norm(x.get("school_name")) == expected_school:
        school_name_match += 1

    if norm(x.get("commune_name")) == expected_commune:
        commune_match += 1

    src_status = str(
        x.get("source_status_label") or ""
    ).strip()

    json_status = str(
        r.get("status_label") or ""
    ).strip()

    if src_status == json_status:
        status_exact += 1

    status_pairs[
        (
            str(x.get("status_code") or ""),
            src_status,
            json_status,
        )
    ] += 1

    db_dob = fmt_date(x.get("date_of_birth"))
    json_dob = str(r.get("date_of_birth") or "").strip()

    if db_dob == json_dob:
        dob_exact += 1

    if str(x.get("gender") or "").strip() == str(r.get("gender") or "").strip():
        gender_exact += 1

    position_pairs[
        (
            str(x.get("position_group") or ""),
            str(x.get("position_title") or ""),
            str(r.get("position_label") or ""),
        )
    ] += 1

print("Matched theo mã/trường :", matched)
print("Tên trường khớp        :", school_name_match)
print("Tên xã khớp            :", commune_match)
print("Status label khớp      :", status_exact)
print("Ngày sinh khớp         :", dob_exact)
print("Giới tính khớp         :", gender_exact)
print("Mã TH JSON không có DB :", len(missing_code_in_db))
print("Mã có nhiều DB record  :", len(multi_db))

print()
print("10 mapping STATUS phổ biến nhất:")

for k, n in status_pairs.most_common(10):
    print(
        " ",
        n,
        "| status_code =", repr(k[0]),
        "| source_status_label =", repr(k[1]),
        "| JSON =", repr(k[2]),
    )

print()
print("15 mapping POSITION phổ biến nhất:")

for k, n in position_pairs.most_common(15):
    print(
        " ",
        n,
        "| position_group =", repr(k[0]),
        "| position_title =", repr(k[1]),
        "| JSON =", repr(k[2]),
    )

# ============================================================
# 3. Khảo sát MN nếu source_level=MN tồn tại
# ============================================================

db_mn = [
    x for x in data
    if str(x.get("source_level") or "").strip().upper() == "MN"
]

print()
print("=" * 120)
print("4. KHẢO SÁT DB source_level=MN")
print("=" * 120)

print("Số dòng MN:", len(db_mn))

mn_school_ids = {
    int(x["school_id"])
    for x in db_mn
    if x.get("school_id") is not None
}

print("Số trường MN:", len(mn_school_ids))

missing_staff_code = [
    x for x in db_mn
    if not str(x.get("ministry_staff_code") or "").strip()
]

print("Thiếu ministry_staff_code:", len(missing_staff_code))

print()
print("Phân bố source_status_label MN:")

for k, v in Counter(
    str(x.get("source_status_label") or "<RỖNG>").strip()
    for x in db_mn
).most_common():
    print(f"  {k!r}: {v}")

print()
print("Phân bố position_group MN:")

for k, v in Counter(
    str(x.get("position_group") or "<RỖNG>").strip()
    for x in db_mn
).most_common():
    print(f"  {k!r}: {v}")

print()
print("10 dòng MN mẫu:")

for x in db_mn[:10]:
    print(
        {
            "school_id": x.get("school_id"),
            "school_name": x.get("school_name"),
            "commune_name": x.get("commune_name"),
            "staff_code": x.get("ministry_staff_code"),
            "full_name": x.get("full_name"),
            "status_code": x.get("status_code"),
            "source_status_label": x.get("source_status_label"),
            "position_group": x.get("position_group"),
            "position_title": x.get("position_title"),
        }
    )

con.close()

db_after = sha256(DB)

print()
print("=" * 120)
print("KIỂM TRA AN TOÀN")
print("=" * 120)

print("DB hash trước:", db_before)
print("DB hash sau  :", db_after)

if db_before != db_after:
    raise RuntimeError(
        "DỪNG: phocap.db thay đổi ngoài dự kiến."
    )

print("Database     : KHÔNG THAY ĐỔI")
print("=" * 120)
