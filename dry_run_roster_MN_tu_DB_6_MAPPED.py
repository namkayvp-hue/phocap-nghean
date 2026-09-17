import sys
import json
import sqlite3
import hashlib
import shutil
import tempfile
from pathlib import Path
from collections import Counter

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

TARGETS = {
    "QD3805-OP-0175",
    "QD3805-OP-0337",
    "QD3805-OP-0410",
    "QD3805-OP-0449",
    "QD3805-OP-0592",
    "QD3805-OP-0600",
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

def fmt_date(v):
    s = str(v or "").strip()

    if not s:
        return ""

    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        return f"{s[8:10]}/{s[5:7]}/{s[0:4]}"

    return s

def position_label(group, title):
    g = str(group or "").strip().upper()

    if g == "CBQL":
        return "Cán bộ quản lý"

    if g == "GIAO_VIEN":
        return "Giáo viên"

    if g == "NHAN_VIEN":
        return "Nhân viên"

    return str(title or group or "").strip()

db_before = sha256(DB)

print("=" * 120)
print("DRY-RUN ROSTER MN 2025-2026 TỪ DB")
print("CHỈ MÔ PHỎNG - KHÔNG CÀI REGISTRY - KHÔNG GHI DATABASE")
print("=" * 120)

# ============================================================
# 1. Lấy năm học
# ============================================================

con = sqlite3.connect(
    DB.resolve().as_uri() + "?mode=ro",
    uri=True,
    timeout=30,
)

con.row_factory = sqlite3.Row
con.execute("PRAGMA query_only=ON")

years = con.execute(
    "SELECT id,code FROM school_years"
).fetchall()

year_2526 = next(
    (
        r for r in years
        if str(r["code"] or "")
        .replace("–", "-")
        .replace("—", "-")
        .strip()
        == "2025-2026"
    ),
    None,
)

year_2627 = next(
    (
        r for r in years
        if str(r["code"] or "")
        .replace("–", "-")
        .replace("—", "-")
        .strip()
        == "2026-2027"
    ),
    None,
)

if year_2526 is None or year_2627 is None:
    raise RuntimeError(
        "Không xác định được đủ năm 2025-2026 / 2026-2027."
    )

# ============================================================
# 2. Dựng roster MN từ staff_year_records năm 2025-2026
# ============================================================

rows = con.execute(
    """
    SELECT
        syr.id AS year_record_id,
        syr.school_id,
        syr.status_code,
        syr.position_group,
        syr.position_title,
        syr.source_level,
        syr.source_status_label,

        sm.ministry_staff_code,
        sm.full_name,
        sm.date_of_birth,
        sm.gender,

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
      AND UPPER(TRIM(COALESCE(syr.source_level,'')))='MN'

    ORDER BY
        syr.school_id,
        syr.id
    """,
    (int(year_2526["id"]),),
).fetchall()

con.close()

mn_rows = []

for idx, raw in enumerate(rows, 1):
    r = dict(raw)

    code = str(
        r.get("ministry_staff_code") or ""
    ).strip()

    if not code:
        raise RuntimeError(
            "Có dòng MN thiếu ministry_staff_code: "
            + json.dumps(r, ensure_ascii=False, default=str)
        )

    mn_rows.append({
        # Chỉ là số dòng kỹ thuật của snapshot DRY-RUN.
        "excel_row": idx,

        "commune_name": str(
            r.get("commune_name") or ""
        ).strip(),

        "school_name": str(
            r.get("school_name") or ""
        ).strip(),

        "staff_code": code,

        "full_name": str(
            r.get("full_name") or ""
        ).strip(),

        "date_of_birth": fmt_date(
            r.get("date_of_birth")
        ),

        "gender": str(
            r.get("gender") or ""
        ).strip(),

        "status_label": str(
            r.get("source_status_label")
            or r.get("status_code")
            or ""
        ).strip(),

        "position_label": position_label(
            r.get("position_group"),
            r.get("position_title"),
        ),
    })

school_count = len({
    (
        x["commune_name"],
        x["school_name"],
    )
    for x in mn_rows
})

print("MN rows dựng tạm :", len(mn_rows))
print("MN schools       :", school_count)

print()
print("Position:")
for k, v in Counter(
    x["position_label"] for x in mn_rows
).most_common():
    print(" ", repr(k), ":", v)

print()
print("Status:")
for k, v in Counter(
    x["status_label"] for x in mn_rows
).most_common():
    print(" ", repr(k), ":", v)

# ============================================================
# 3. Tạo dataset TẠM trong TemporaryDirectory
#    Không đặt vào data\school_merger_source_rosters
# ============================================================

dataset = {
    "dataset_id": "MN-2025-2026-DB-SNAPSHOT-DRYRUN",
    "level_code": "MN",
    "school_year_code": "2025-2026",

    # Ghi rõ nguồn để không giả là Excel độc lập.
    "source_file": (
        "INTERNAL_DB_SNAPSHOT:"
        "phocap.db/staff_year_records"
    ),

    "source_sha256": db_before,

    "row_count": len(mn_rows),
    "school_count": school_count,

    "rows": mn_rows,
}

import app.services.school_merger_source_audit_service as svc

original_dir = svc.SOURCE_ROSTER_DIR

with tempfile.TemporaryDirectory(
    prefix="MN_QD3805_DRYRUN_"
) as tmp:

    tmpdir = Path(tmp)

    # Giữ TH dataset hiện tại để các correction TH vẫn có đối tượng đối chiếu.
    shutil.copy2(
        TH_JSON,
        tmpdir / "TH_2025_2026.json",
    )

    temp_mn = tmpdir / "MN_2025_2026_DRYRUN.json"

    temp_mn.write_text(
        json.dumps(
            dataset,
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )

    # Chỉ đổi biến module trong tiến trình Python hiện tại.
    # Không sửa source code trên ổ đĩa.
    svc.SOURCE_ROSTER_DIR = tmpdir

    try:
        result = svc.audit_official_plans(
            school_year_id=int(year_2627["id"]),
            commune_id=None,
            level_code="MN",
        )
    finally:
        svc.SOURCE_ROSTER_DIR = original_dir

# TemporaryDirectory đã tự xóa ở đây.

# ============================================================
# 4. In riêng 6 MAPPED
# ============================================================

print()
print("=" * 120)
print("KẾT QUẢ DRY-RUN 6 OPERATION MAPPED")
print("=" * 120)

found = {}

for raw in result.get("rows") or []:
    if not isinstance(raw, dict):
        continue

    plan = dict(raw.get("plan") or {})
    audit = dict(raw.get("audit") or {})

    op_id = str(
        plan.get("qd3805_operation_id")
        or plan.get("operation_id")
        or ""
    ).strip()

    # Một số service không gắn operation_id ở lớp audit.
    # Fallback theo plan_id đã biết.
    if not op_id:
        pid = str(plan.get("id") or "")

        PLAN_TO_OP = {
            "PA2026-785CDDA8D8CC": "QD3805-OP-0175",
            "PA2026-E494BD00A794": "QD3805-OP-0337",
            "PA2026-43804C58D423": "QD3805-OP-0410",
            "PA2026-4AB75BCD93EB": "QD3805-OP-0449",
            "PA2026-7802B1BD1912": "QD3805-OP-0592",
            "PA2026-1E90C6AAFD47": "QD3805-OP-0600",
        }

        op_id = PLAN_TO_OP.get(pid, "")

    if op_id not in TARGETS:
        continue

    found[op_id] = audit

for op_id in sorted(TARGETS):

    print()
    print("-" * 120)
    print(op_id)

    audit = found.get(op_id)

    if audit is None:
        print("  <KHÔNG TÌM THẤY AUDIT>")
        continue

    print("  audit pass :", audit.get("pass"))
    print("  status     :", audit.get("status"))
    print("  message    :", audit.get("message"))

    blockers = audit.get("blockers") or []
    warnings = audit.get("warnings") or []

    if blockers:
        print("  BLOCKERS:")
        for x in blockers:
            print("    -", x)

    if warnings:
        print("  WARNINGS:")
        for x in warnings:
            print("    -", x)

    print("  SCHOOL CHECKS:")

    for sc in audit.get("school_checks") or []:

        print(
            "    *",
            sc.get("role"),
            "|",
            sc.get("school_name"),
        )

        print(
            "      source_roster_found =",
            sc.get("source_roster_found"),
        )

        print(
            "      source_total_rows   =",
            sc.get("source_total_rows"),
        )

        print(
            "      db_previous_rows    =",
            sc.get("db_previous_total_rows"),
        )

        print(
            "      active_matched      =",
            sc.get("active_identity_matched"),
        )

        print(
            "      active_at_school    =",
            sc.get("active_at_expected_school"),
        )

        print(
            "      active_db_eligible  =",
            sc.get("active_db_eligible"),
        )

        issues = sc.get("issues") or []

        if issues:
            print("      ISSUES:")

            for issue in issues:
                print(
                    "        -",
                    issue.get("code"),
                    ":",
                    issue.get("message"),
                )

# ============================================================
# 5. Tổng kết
# ============================================================

passes = [
    op
    for op in TARGETS
    if found.get(op, {}).get("pass") is True
]

fails = [
    op
    for op in TARGETS
    if found.get(op, {}).get("pass") is not True
]

print()
print("=" * 120)
print("TỔNG KẾT DRY-RUN")
print("=" * 120)

print("PASS:", len(passes))
for x in sorted(passes):
    print("  +", x)

print("BLOCK:", len(fails))
for x in sorted(fails):
    print("  -", x)

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
print("Registry thật: KHÔNG THAY ĐỔI")
print("File MN tạm  : ĐÃ TỰ XÓA")
print("=" * 120)
