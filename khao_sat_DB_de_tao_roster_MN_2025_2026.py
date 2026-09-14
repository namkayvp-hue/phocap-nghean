import sys
import json
import sqlite3
import hashlib
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(r"C:\PhoCap")
DB = ROOT / "data" / "phocap.db"

TH_JSON = (
    ROOT
    / "data"
    / "school_merger_source_rosters"
    / "TH_2025_2026.json"
)

IGNORE = {
    ".venv",
    ".git",
    "__pycache__",
    "backups",
}

SEARCH_TERMS = (
    "TH-2025-2026-DANH-SACH-GIAO-VIEN",
    "TH_2025_2026.json",
    "school_merger_source_rosters",
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

def skip(path):
    parts = {x.lower() for x in path.parts}
    return any(x.lower() in parts for x in IGNORE)

def qid(name):
    return '"' + str(name).replace('"', '""') + '"'

db_before = sha256(DB)

print("=" * 120)
print("KHẢO SÁT NGUỒN TẠO ROSTER MN 2025-2026")
print("CHỈ ĐỌC - KHÔNG TẠO JSON - KHÔNG GHI DATABASE")
print("=" * 120)

# ==========================================================
# 1. TÌM CHƯƠNG TRÌNH ĐÃ TẠO TH_2025_2026.json
# ==========================================================

print()
print("=" * 120)
print("1. FILE MÃ NGUỒN LIÊN QUAN ROSTER TH 2025-2026")
print("=" * 120)

hits = []

for ext in ("*.py", "*.ps1", "*.json", "*.txt"):
    for p in ROOT.rglob(ext):
        if skip(p):
            continue

        try:
            text = p.read_text(
                encoding="utf-8",
                errors="replace",
            )
        except Exception:
            continue

        lines = text.splitlines()

        for no, line in enumerate(lines, 1):
            if any(term in line for term in SEARCH_TERMS):
                hits.append(
                    (str(p), no, line.strip())
                )

for path, no, line in hits[:300]:
    print()
    print(path)
    print(f"  dòng {no}: {line}")

print()
print("Tổng match:", len(hits))

# ==========================================================
# 2. CẤU TRÚC ROSTER TH ĐANG HOẠT ĐỘNG
# ==========================================================

print()
print("=" * 120)
print("2. SCHEMA TH_2025_2026.json")
print("=" * 120)

th = json.loads(
    TH_JSON.read_text(encoding="utf-8")
)

print("Top-level keys:")
for k in sorted(th.keys()):
    if k != "rows":
        print(
            f"  {k} =",
            th.get(k),
        )

rows = th.get("rows") or []

print()
print("Số row:", len(rows))

if rows:
    print("Row keys:", sorted(rows[0].keys()))

# ==========================================================
# 3. DB SCHEMA
# ==========================================================

print()
print("=" * 120)
print("3. XÁC ĐỊNH NĂM HỌC 2025-2026")
print("=" * 120)

con = sqlite3.connect(
    DB.resolve().as_uri() + "?mode=ro",
    uri=True,
    timeout=30,
)

con.row_factory = sqlite3.Row
con.execute("PRAGMA query_only=ON")

years = con.execute(
    "SELECT * FROM school_years"
).fetchall()

year_id = None

for r in years:
    d = dict(r)

    print(d)

    code = str(d.get("code") or "")
    code = (
        code
        .replace("–", "-")
        .replace("—", "-")
        .strip()
    )

    if code == "2025-2026":
        year_id = d.get("id")

print()
print("school_year_id 2025-2026 =", year_id)

if year_id is None:
    raise RuntimeError(
        "Không xác định được ID năm học 2025-2026."
    )

# ==========================================================
# 4. TÌM CÁC BẢNG CÓ KHẢ NĂNG CHỨA ĐỘI NGŨ
# ==========================================================

print()
print("=" * 120)
print("4. CÁC BẢNG DB CÓ KHẢ NĂNG CHỨA ĐỘI NGŨ")
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

candidate_tables = []

keywords = (
    "staff",
    "teacher",
    "employee",
    "personnel",
    "giao_vien",
    "giaovien",
    "can_bo",
    "canbo",
    "nhan_vien",
    "nhanvien",
)

for table in tables:

    cols = [
        dict(r)
        for r in con.execute(
            f"PRAGMA table_info({qid(table)})"
        ).fetchall()
    ]

    col_names = [
        str(x.get("name") or "")
        for x in cols
    ]

    joined = (
        table.lower()
        + " "
        + " ".join(x.lower() for x in col_names)
    )

    likely = (
        any(k in joined for k in keywords)
        or (
            "school_id" in col_names
            and "school_year_id" in col_names
            and any(
                x in col_names
                for x in (
                    "full_name",
                    "position",
                    "position_code",
                    "staff_code",
                )
            )
        )
    )

    if not likely:
        continue

    candidate_tables.append(
        (table, col_names)
    )

    try:
        total = con.execute(
            f"SELECT COUNT(*) AS n "
            f"FROM {qid(table)}"
        ).fetchone()["n"]
    except Exception:
        total = "<LỖI>"

    print()
    print("TABLE:", table)
    print("Total rows:", total)
    print("Columns:")

    for c in cols:
        print(
            "  -",
            c.get("name"),
            c.get("type"),
        )

    if "school_year_id" in col_names:
        try:
            n2526 = con.execute(
                f"""
                SELECT COUNT(*) AS n
                FROM {qid(table)}
                WHERE school_year_id=?
                """,
                (year_id,),
            ).fetchone()["n"]

            print(
                "Rows năm 2025-2026:",
                n2526,
            )
        except Exception as exc:
            print(
                "Không đếm được theo năm:",
                exc,
            )

# ==========================================================
# 5. SCHEMA BẢNG SCHOOLS
# ==========================================================

print()
print("=" * 120)
print("5. SCHEMA BẢNG SCHOOLS")
print("=" * 120)

if "schools" in tables:

    school_cols = [
        dict(r)
        for r in con.execute(
            "PRAGMA table_info(schools)"
        ).fetchall()
    ]

    for c in school_cols:
        print(
            c.get("name"),
            c.get("type"),
        )

    print()
    print("10 trường đầu:")

    sample = con.execute(
        "SELECT * FROM schools LIMIT 10"
    ).fetchall()

    for r in sample:
        print(dict(r))

else:
    print("<KHÔNG CÓ BẢNG schools>")

# ==========================================================
# 6. TÌM SQL TRONG SOURCE AUDIT ĐỂ BIẾT BẢNG DB NÓ ĐANG ĐẾM
# ==========================================================

print()
print("=" * 120)
print("6. SQL / TÊN BẢNG TRONG SOURCE AUDIT SERVICE")
print("=" * 120)

AUDIT = (
    ROOT
    / "app"
    / "services"
    / "school_merger_source_audit_service.py"
)

text = AUDIT.read_text(
    encoding="utf-8",
    errors="replace",
)

for no, line in enumerate(
    text.splitlines(),
    1,
):
    low = line.lower()

    if any(
        x in low
        for x in (
            "select ",
            " from ",
            " join ",
            "staff",
            "teacher",
            "school_year_id",
            "db_previous",
        )
    ):
        print(
            f"{no:5}: {line}"
        )

con.close()

# ==========================================================
# 7. AN TOÀN
# ==========================================================

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
