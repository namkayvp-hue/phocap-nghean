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

TARGET = 748
SOURCES = (750, 751)
ALL_IDS = (748, 750, 751)

CURRENT_PLAN = "PA2026-E494BD00A794"

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
print("KIỂM CHỨNG OP-0337 ĐÃ HOÀN TẤT TRƯỚC HAY CHƯA")
print("MN Nghi Hoa + MN Nghi Vạn -> MN Nghi Diên")
print("CHỈ ĐỌC - KHÔNG MỞ KHÓA TRƯỜNG - KHÔNG GHI DATABASE")
print("=" * 120)

# ============================================================
# 1. TRẠNG THÁI 3 TRƯỜNG
# ============================================================

print()
print("=" * 120)
print("1. TRẠNG THÁI SCHOOLS")
print("=" * 120)

schools = con.execute(
    """
    SELECT
        s.id,
        s.code,
        s.name,
        s.commune_id,
        s.is_active,
        c.name AS commune_name
    FROM schools s
    LEFT JOIN communes c ON c.id=s.commune_id
    WHERE s.id IN (748,750,751)
    ORDER BY s.id
    """
).fetchall()

for r in schools:
    print(dict(r))

# ============================================================
# 2. XÁC ĐỊNH CURRENT/FUTURE
# ============================================================

print()
print("=" * 120)
print("2. NĂM CURRENT / FUTURE")
print("=" * 120)

years = con.execute(
    "SELECT id,code,name FROM school_years ORDER BY id"
).fetchall()

future_year_ids = []

for r in years:
    d = dict(r)

    code = (
        str(d.get("code") or "")
        .replace("–", "-")
        .replace("—", "-")
        .strip()
    )

    try:
        start_year = int(code[:4])
    except Exception:
        start_year = -1

    if start_year >= 2026:
        future_year_ids.append(int(d["id"]))
        print(d)

if not future_year_ids:
    raise RuntimeError(
        "Không xác định được năm CURRENT/FUTURE."
    )

# ============================================================
# 3. KIỂM TRA MỌI BẢNG CÓ school_id + school_year_id
# ============================================================

print()
print("=" * 120)
print("3. CURRENT/FUTURE RESIDUAL TẠI SOURCE")
print("=" * 120)

tables = [
    r["name"]
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

source_residual_total = 0
target_current_total = 0
residual_detail = []

year_marks = ",".join(
    "?" for _ in future_year_ids
)

for table in tables:
    cols = [
        r["name"]
        for r in con.execute(
            f"PRAGMA table_info({qi(table)})"
        ).fetchall()
    ]

    if (
        "school_id" not in cols
        or "school_year_id" not in cols
    ):
        continue

    try:
        src_rows = con.execute(
            f"""
            SELECT
                school_id,
                school_year_id,
                COUNT(*) AS n
            FROM {qi(table)}
            WHERE school_id IN (?,?)
              AND school_year_id IN ({year_marks})
            GROUP BY school_id,school_year_id
            ORDER BY school_id,school_year_id
            """,
            (*SOURCES, *future_year_ids),
        ).fetchall()

        dst_rows = con.execute(
            f"""
            SELECT COUNT(*) AS n
            FROM {qi(table)}
            WHERE school_id=?
              AND school_year_id IN ({year_marks})
            """,
            (TARGET, *future_year_ids),
        ).fetchone()

    except Exception as exc:
        print(
            f"{table}: <không kiểm được> {exc}"
        )
        continue

    src_total = sum(
        int(x["n"] or 0)
        for x in src_rows
    )

    dst_total = int(
        (dst_rows or {"n": 0})["n"] or 0
    )

    source_residual_total += src_total
    target_current_total += dst_total

    if src_total or dst_total:
        print()
        print(
            table,
            "| SOURCE residual =",
            src_total,
            "| TARGET rows =",
            dst_total,
        )

        for x in src_rows:
            print(
                "   SOURCE:",
                dict(x),
            )

        residual_detail.append({
            "table": table,
            "source_residual": src_total,
            "target_rows": dst_total,
        })

print()
print(
    "TỔNG CURRENT/FUTURE residual tại 750+751 =",
    source_residual_total,
)

# ============================================================
# 4. ĐỘI NGŨ 2026-2027+ RIÊNG
# ============================================================

print()
print("=" * 120)
print("4. STAFF_YEAR_RECORDS CURRENT/FUTURE")
print("=" * 120)

staff_rows = con.execute(
    f"""
    SELECT
        syr.school_id,
        sy.code AS school_year,
        COUNT(*) AS total,
        SUM(
            CASE WHEN syr.is_active=1
                 THEN 1 ELSE 0 END
        ) AS active_count
    FROM staff_year_records syr
    JOIN school_years sy
      ON sy.id=syr.school_year_id
    WHERE syr.school_id IN (748,750,751)
      AND syr.school_year_id IN ({year_marks})
    GROUP BY syr.school_id,sy.code
    ORDER BY syr.school_id,sy.code
    """,
    tuple(future_year_ids),
).fetchall()

for r in staff_rows:
    print(dict(r))

# ============================================================
# 5. TÀI KHOẢN GẮN 3 TRƯỜNG
# ============================================================

print()
print("=" * 120)
print("5. USERS GẮN VỚI 748 / 750 / 751")
print("=" * 120)

user_cols = [
    r["name"]
    for r in con.execute(
        "PRAGMA table_info(users)"
    ).fetchall()
]

select_cols = [
    x for x in (
        "id",
        "username",
        "full_name",
        "role_id",
        "school_id",
        "is_active",
    )
    if x in user_cols
]

user_rows = con.execute(
    f"""
    SELECT {",".join(qi(x) for x in select_cols)}
    FROM users
    WHERE school_id IN (748,750,751)
    ORDER BY school_id,role_id,id
    """
).fetchall()

counts = {}

for r in user_rows:
    d = dict(r)

    sid = int(d.get("school_id") or 0)

    counts.setdefault(
        sid,
        {"total": 0, "active": 0}
    )

    counts[sid]["total"] += 1

    if int(d.get("is_active") or 0) == 1:
        counts[sid]["active"] += 1

    print(d)

print()
print("TỔNG HỢP USERS:")
for sid in ALL_IDS:
    print(
        sid,
        counts.get(
            sid,
            {"total": 0, "active": 0}
        )
    )

# ============================================================
# 6. TÌM DẤU VẾT TRONG CÁC BẢNG MERGER
# ============================================================

print()
print("=" * 120)
print("6. DẤU VẾT CÁC BẢNG SCHOOL_MERGER")
print("=" * 120)

merger_tables = [
    t for t in tables
    if (
        "merger" in t.lower()
        or "sap_nhap" in t.lower()
    )
]

print(
    "Các bảng liên quan:",
    merger_tables
)

for table in merger_tables:

    cols_info = [
        dict(r)
        for r in con.execute(
            f"PRAGMA table_info({qi(table)})"
        ).fetchall()
    ]

    cols = [
        str(x["name"])
        for x in cols_info
    ]

    print()
    print("-" * 120)
    print("TABLE:", table)
    print("COLUMNS:", cols)

    searchable = [
        c for c in cols
        if any(
            key in c.lower()
            for key in (
                "plan",
                "operation",
                "source",
                "target",
                "school",
                "summary",
                "detail",
                "status",
            )
        )
    ]

    if not searchable:
        continue

    conditions = []
    params = []

    for c in searchable:
        conditions.append(
            f"CAST({qi(c)} AS TEXT) LIKE ?"
        )
        params.append("%750%")

        conditions.append(
            f"CAST({qi(c)} AS TEXT) LIKE ?"
        )
        params.append("%751%")

        conditions.append(
            f"CAST({qi(c)} AS TEXT) LIKE ?"
        )
        params.append("%748%")

        conditions.append(
            f"CAST({qi(c)} AS TEXT) LIKE ?"
        )
        params.append(
            "%" + CURRENT_PLAN + "%"
        )

    try:
        rows = con.execute(
            f"""
            SELECT *
            FROM {qi(table)}
            WHERE {" OR ".join(conditions)}
            LIMIT 100
            """,
            params,
        ).fetchall()
    except Exception as exc:
        print("QUERY ERROR:", exc)
        continue

    print("MATCHED ROWS:", len(rows))

    for r in rows:
        print(
            json.dumps(
                dict(r),
                ensure_ascii=False,
                default=str,
            )
        )

# ============================================================
# 7. KẾT LUẬN CƠ HỌC
# ============================================================

print()
print("=" * 120)
print("7. KẾT LUẬN CƠ HỌC")
print("=" * 120)

school_map = {
    int(r["id"]): dict(r)
    for r in schools
}

target_active = (
    int(
        school_map
        .get(TARGET, {})
        .get("is_active")
        or 0
    )
    == 1
)

sources_inactive = all(
    int(
        school_map
        .get(sid, {})
        .get("is_active")
        or 0
    )
    == 0
    for sid in SOURCES
)

print(
    "Target 748 active             =",
    target_active,
)

print(
    "Sources 750/751 inactive      =",
    sources_inactive,
)

print(
    "CURRENT/FUTURE source residual=",
    source_residual_total,
)

if (
    target_active
    and sources_inactive
    and source_residual_total == 0
):
    print()
    print(
        "DẤU HIỆU MẠNH: OP-0337 ĐÃ ĐƯỢC "
        "THỰC HIỆN TRƯỚC."
    )
    print(
        "KHÔNG ĐƯỢC mở khóa 750/751 để chạy lại."
    )
else:
    print()
    print(
        "CHƯA ĐỦ BẰNG CHỨNG để coi OP-0337 "
        "là đã hoàn tất trước."
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
        "DỪNG: database thay đổi."
    )

print("Database: KHÔNG THAY ĐỔI")
print("=" * 120)
