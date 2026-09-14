from __future__ import annotations

import sys
import json
import hashlib
from pathlib import Path

sys.dont_write_bytecode = True

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

EXPECTED_DB_SHA = (
    "44b1aa841cdd76301c57d9fc601121ae"
    "96f9312084ef05959eaae54acf17c8c9"
)

EXPECTED_SERVICE_SHA = (
    "963b8d6a280d8abef8e96486abd87d77"
    "cea289b08d2edb497647f250ed1b2af8"
)

EXPECTED_ROSTER_SHA = (
    "ef865f74aa51c2700ceb7746d5433b63"
    "fc6a52a4e3169014ebe0e446ac441120"
)

READY_EXPECTED = {
    "QD3805-OP-0175",
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


before = {
    "db": sha256(DB),
    "service": sha256(SERVICE),
    "resolution": sha256(RESOLUTION),
    "roster": sha256(ROSTER),
}


print("=" * 120)
print("XAC NHAN TRANG THAI MN SAU DEFER LUONG MINH")
print("CHI DOC - KHONG SUA DB / SOURCE / JSON")
print("=" * 120)

for key, value in before.items():
    print(
        f"{key:10s} = {value}"
    )


if before["db"] != EXPECTED_DB_SHA:
    raise RuntimeError(
        "DUNG: DB SHA khong con dung nen da khoa."
    )

if before["service"] != EXPECTED_SERVICE_SHA:
    raise RuntimeError(
        "DUNG: batch service da thay doi ngoai du kien."
    )

if before["roster"] != EXPECTED_ROSTER_SHA:
    raise RuntimeError(
        "DUNG: MN roster da thay doi ngoai du kien."
    )


# ============================================================
# 1. DOC RESOLUTION
# ============================================================

resolution = json.loads(
    RESOLUTION.read_text(
        encoding="utf-8-sig",
    )
)

deferred = [
    dict(x)
    for x in (
        resolution.get(
            "deferred_orphans"
        )
        or []
    )
    if isinstance(x, dict)
]

precompleted = [
    dict(x)
    for x in (
        resolution.get(
            "precompleted"
        )
        or []
    )
    if isinstance(x, dict)
]


print()
print("=" * 120)
print("1. RESOLUTION")
print("=" * 120)

print(
    "Resolution SHA =",
    before["resolution"],
)

print(
    "Precompleted IDs =",
    [
        x.get("operation_id")
        for x in precompleted
    ],
)

print()
print("Deferred orphans:")

print(
    json.dumps(
        deferred,
        ensure_ascii=False,
        indent=2,
    )
)


lm = next(
    (
        x
        for x in deferred
        if int(
            x.get("stt")
            or 0
        ) == 1211
    ),
    None,
)


# ============================================================
# 2. PREVIEW MN
# ============================================================

from app.services.school_merger_level_batch_service import (
    build_level_batch_preview,
)

mn = build_level_batch_preview(
    school_year_id=2,
    level_code="MN",
)

states = {}
ready_ops = []

for row in (
    mn.get("rows")
    or []
):
    if not isinstance(row, dict):
        continue

    op = str(
        row.get(
            "qd3805_operation_id"
        )
        or ""
    ).strip()

    state = str(
        row.get(
            "batch_state"
        )
        or ""
    ).upper().strip()

    if op:
        states[op] = state

    if state == "READY":
        ready_ops.append(op)


print()
print("=" * 120)
print("2. TRANG THAI BATCH MN")
print("=" * 120)

print(
    "counts                =",
    mn.get("counts"),
)

print(
    "candidate_count       =",
    mn.get("candidate_count"),
)

print(
    "effective_block_count =",
    mn.get(
        "effective_block_count"
    ),
)

print(
    "ready_for_execution   =",
    mn.get(
        "ready_for_execution"
    ),
)

print(
    "all_done              =",
    mn.get("all_done"),
)

print()
print(
    "OP-0337 =",
    states.get(
        "QD3805-OP-0337"
    ),
)

print(
    "OP-0338 =",
    states.get(
        "QD3805-OP-0338"
    ),
)

print()
print(
    "READY OPS =",
    sorted(ready_ops),
)

print()
print(
    "EXTRA BLOCKERS =",
    json.dumps(
        mn.get(
            "extra_blockers"
        )
        or [],
        ensure_ascii=False,
    ),
)


# ============================================================
# 3. EXACT VERIFY
# ============================================================

print()
print("=" * 120)
print("3. KIEM TRA DIEU KIEN")
print("=" * 120)

checks = {
    "Luong_Minh_deferred":
        lm is not None,

    "Luong_Minh_code":
        (
            lm is not None
            and str(
                lm.get(
                    "school_code"
                )
                or ""
            )
            == "40418311"
        ),

    "OP0337_DONE":
        states.get(
            "QD3805-OP-0337"
        )
        == "DONE",

    "OP0338_DONE":
        states.get(
            "QD3805-OP-0338"
        )
        == "DONE",

    "KPI_exact":
        mn.get("counts")
        == {
            "KEEP": 51,
            "DONE": 184,
            "READY": 5,
            "BLOCK": 0,
        },

    "candidate_5":
        mn.get(
            "candidate_count"
        )
        == 5,

    "effective_block_0":
        mn.get(
            "effective_block_count"
        )
        == 0,

    "ready_true":
        mn.get(
            "ready_for_execution"
        )
        is True,

    "extra_blockers_empty":
        not (
            mn.get(
                "extra_blockers"
            )
            or []
        ),

    "ready_ops_exact":
        set(ready_ops)
        == READY_EXPECTED,
}


for key, value in checks.items():
    print(
        f"{key:25s} = {value}"
    )


if not all(checks.values()):
    raise RuntimeError(
        "CHUA DU DIEU KIEN DE SANG "
        "DRY-RUN 5 PHUONG AN READY."
    )


# ============================================================
# 4. TH CHECK
# ============================================================

th = build_level_batch_preview(
    school_year_id=2,
    level_code="TH",
)

print()
print("=" * 120)
print("4. TIEU HOC")
print("=" * 120)

print(
    "TH counts =",
    th.get("counts"),
)

if th.get("counts") != {
    "KEEP": 67,
    "DONE": 160,
    "READY": 0,
    "BLOCK": 0,
}:
    raise RuntimeError(
        "TH thay doi ngoai du kien."
    )


# ============================================================
# 5. SAFETY
# ============================================================

after = {
    "db": sha256(DB),
    "service": sha256(SERVICE),
    "resolution": sha256(RESOLUTION),
    "roster": sha256(ROSTER),
}


print()
print("=" * 120)
print("5. KIEM TRA AN TOAN")
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
        "DUNG: file that bi thay doi."
    )


print()
print("=" * 120)
print("SAN SANG CHO DRY-RUN TONG CUOI 5 PHUONG AN MN")
print("=" * 120)

print(
    "Luong Minh : DEFERRED - KHONG TU DONG SAP NHAP"
)

print(
    "OP-0337    : DONE - KHONG CHAY LAI"
)

print(
    "OP-0338    : DONE - KHONG CHAY LAI"
)

print(
    "5 READY    :",
    sorted(READY_EXPECTED),
)

print(
    "Database   : KHONG THAY DOI"
)

print(
    "Source/JSON: KHONG THAY DOI"
)

print("=" * 120)
