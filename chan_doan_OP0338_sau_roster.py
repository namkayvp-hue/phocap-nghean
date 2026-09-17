import sys
import json
import hashlib
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(r"C:\PhoCap")
DB = ROOT / "data" / "phocap.db"

SERVICE = (
    ROOT
    / "app"
    / "services"
    / "school_merger_level_batch_service.py"
)

RESOLUTION = (
    ROOT
    / "data"
    / "school_merger_registry"
    / "qd3805_mn_resolution.json"
)

ROSTER = (
    ROOT
    / "data"
    / "school_merger_source_rosters"
    / "MN_2025_2026.json"
)

PLAN_ID = "PA2026-63A88A615526"

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

before = {
    "db": sha256(DB),
    "service": sha256(SERVICE),
    "resolution": sha256(RESOLUTION),
    "roster": sha256(ROSTER),
}

print("=" * 120)
print("CHAN DOAN OP-0338 SAU KHI DA CAI ROSTER MN")
print("CHI DOC - KHONG SUA DB - KHONG SUA SOURCE/JSON")
print("=" * 120)

print("DB SHA:", before["db"])

if before["db"] != EXPECTED_DB_SHA:
    raise RuntimeError(
        "DUNG: DB khong con dung nen da khoa."
    )

from app.services.school_merger_official_registry import (
    list_official_registry_plans,
)

from app.services.school_merger_source_audit_service import (
    audit_official_plans,
    source_registry_summary,
)

from app.services.school_merger_level_batch_service import (
    build_level_batch_preview,
)

# ============================================================
# 1. OFFICIAL PLAN
# ============================================================

plans = list_official_registry_plans(
    school_year_id=2,
    commune_id=None,
    level_code="MN",
    display_mode="all",
)

plan = next(
    (
        dict(x)
        for x in plans
        if str(x.get("id") or "") == PLAN_ID
    ),
    None,
)

print()
print("=" * 120)
print("1. OFFICIAL PLAN OP-0338")
print("=" * 120)

if plan is None:
    print("<KHONG TIM THAY>")
else:
    print(
        json.dumps(
            plan,
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )

# ============================================================
# 2. SOURCE AUDIT SAU ROSTER
# ============================================================

audit_all = audit_official_plans(
    school_year_id=2,
    commune_id=None,
    level_code="MN",
)

audit_row = next(
    (
        dict(x)
        for x in (audit_all.get("rows") or [])
        if str(
            (x.get("plan") or {}).get("id") or ""
        ) == PLAN_ID
    ),
    None,
)

print()
print("=" * 120)
print("2. SOURCE AUDIT OP-0338")
print("=" * 120)

if audit_row is None:
    print("<KHONG TIM THAY>")
else:
    print(
        json.dumps(
            audit_row,
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )

# ============================================================
# 3. BATCH ROW HIEN TAI
# ============================================================

preview = build_level_batch_preview(
    school_year_id=2,
    level_code="MN",
)

batch_rows = [
    dict(x)
    for x in (preview.get("rows") or [])
    if str(x.get("id") or "") == PLAN_ID
    or str(
        x.get("qd3805_operation_id") or ""
    ) == "QD3805-OP-0338"
]

print()
print("=" * 120)
print("3. BATCH ROW OP-0338")
print("=" * 120)

if not batch_rows:
    print("<KHONG CO ROW>")
else:
    for row in batch_rows:
        print(
            json.dumps(
                row,
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        )

# ============================================================
# 4. KPI HIEN TAI
# ============================================================

print()
print("=" * 120)
print("4. KPI HIEN TAI")
print("=" * 120)

print("counts                =", preview.get("counts"))
print("candidate_count       =", preview.get("candidate_count"))
print("effective_block_count =", preview.get("effective_block_count"))
print("ready_for_execution   =", preview.get("ready_for_execution"))

print()
print("EXTRA BLOCKERS:")

for item in preview.get("extra_blockers") or []:
    print(
        json.dumps(
            item,
            ensure_ascii=False,
            default=str,
        )
    )

# ============================================================
# 5. SOURCE REGISTRY
# ============================================================

print()
print("=" * 120)
print("5. SOURCE REGISTRY SUMMARY")
print("=" * 120)

print(
    json.dumps(
        source_registry_summary(),
        ensure_ascii=False,
        indent=2,
        default=str,
    )
)

# ============================================================
# 6. AN TOAN
# ============================================================

after = {
    "db": sha256(DB),
    "service": sha256(SERVICE),
    "resolution": sha256(RESOLUTION),
    "roster": sha256(ROSTER),
}

print()
print("=" * 120)
print("6. KIEM TRA AN TOAN")
print("=" * 120)

for key in before:
    print(
        key,
        ":",
        before[key],
        "->",
        after[key],
    )

if before != after:
    raise RuntimeError(
        "DUNG: co file bi thay doi ngoai du kien."
    )

print()
print("Database   : KHONG THAY DOI")
print("Source     : KHONG THAY DOI")
print("Resolution : KHONG THAY DOI")
print("Roster     : KHONG THAY DOI")
print("=" * 120)
