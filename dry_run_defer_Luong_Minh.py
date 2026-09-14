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

EXPECTED_ROSTER_SHA = (
    "ef865f74aa51c2700ceb7746d5433b63"
    "fc6a52a4e3169014ebe0e446ac441120"
)

READY_OPS = {
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
print("DRY-RUN DEFER MAM NON LUONG MINH")
print("STT 1211 / QD3805-ORPHAN-R1216")
print("KHONG SUA DB - KHONG SUA SOURCE - KHONG SUA JSON")
print("=" * 120)

for key, value in before.items():
    print(key, "=", value)


if before["db"] != EXPECTED_DB_SHA:
    raise RuntimeError(
        "DUNG: DB khong con dung nen da khoa."
    )

if before["roster"] != EXPECTED_ROSTER_SHA:
    raise RuntimeError(
        "DUNG: MN roster da thay doi."
    )


from app.services import (
    school_merger_level_batch_service
    as batch_svc
)


# ============================================================
# 1. BASELINE
# ============================================================

baseline = batch_svc.build_level_batch_preview(
    school_year_id=2,
    level_code="MN",
)

print()
print("=" * 120)
print("1. BASELINE")
print("=" * 120)

print(
    "counts                =",
    baseline.get("counts"),
)

print(
    "candidate_count       =",
    baseline.get("candidate_count"),
)

print(
    "effective_block_count =",
    baseline.get("effective_block_count"),
)

print(
    "ready_for_execution   =",
    baseline.get("ready_for_execution"),
)


if baseline.get("counts") != {
    "KEEP": 51,
    "DONE": 184,
    "READY": 5,
    "BLOCK": 0,
}:
    raise RuntimeError(
        "DUNG: KPI baseline MN khong con dung."
    )

if baseline.get("candidate_count") != 5:
    raise RuntimeError(
        "DUNG: baseline candidate_count != 5."
    )

if baseline.get("effective_block_count") != 1:
    raise RuntimeError(
        "DUNG: baseline effective_block_count != 1."
    )

if baseline.get("ready_for_execution") is not False:
    raise RuntimeError(
        "DUNG: baseline dang khong bi khoa nhu du kien."
    )


baseline_text = json.dumps(
    baseline.get("extra_blockers") or [],
    ensure_ascii=False,
)

if "Lượng Minh" not in baseline_text:
    raise RuntimeError(
        "DUNG: blocker Luong Minh khong con ton tai."
    )


# ============================================================
# 2. KIEM TRA RESOLUTION HIEN TAI
# ============================================================

original_resolution_context = (
    batch_svc._resolution_context
)

current_ctx = original_resolution_context(
    "MN"
)

existing_deferred = [
    dict(x)
    for x in (
        current_ctx.get("deferred_orphans")
        or []
    )
    if isinstance(x, dict)
]


print()
print("=" * 120)
print("2. DEFERRED HIEN TAI")
print("=" * 120)

print(
    json.dumps(
        existing_deferred,
        ensure_ascii=False,
        indent=2,
    )
)


if any(
    int(x.get("stt") or 0) == 1211
    for x in existing_deferred
):
    raise RuntimeError(
        "DUNG: STT 1211 da co trong deferred_orphans."
    )


# ============================================================
# 3. RULE TAM TRONG RAM
# ============================================================

LUONG_MINH_RULE = {
    "stt": 1211,

    "excel_row": 1216,

    "operation_id":
        "QD3805-ORPHAN-R1216",

    "commune":
        "Lượng Minh",

    "school":
        "Mầm non Lượng Minh",

    "school_code":
        "40418311",

    "status":
        (
            "CHỜ XÁC NHẬN – KHÔNG TÁC ĐỘNG "
            "TRONG SÁP NHẬP TOÀN CẤP"
        ),

    "display_title":
        (
            "STT 1211 – Mầm non Lượng Minh – "
            "chưa có phương án/ghi chú đủ rõ"
        ),

    "reason":
        (
            "Dòng QĐ3805/nguồn phương án không có "
            "phương án hoặc ghi chú đủ rõ để xác định "
            "nguồn → đích. Không tự suy đoán. "
            "Giữ nguyên dữ liệu hiện có, không đưa "
            "trường này vào batch sáp nhập tự động; "
            "chờ xác nhận nghiệp vụ riêng nếu có."
        ),
}


def patched_resolution_context(level_code):

    result = original_resolution_context(
        level_code
    )

    if str(level_code or "").upper() != "MN":
        return result

    result = dict(result)

    payload = dict(
        result.get("payload")
        or {}
    )

    deferred = [
        dict(x)
        for x in (
            payload.get("deferred_orphans")
            or []
        )
        if isinstance(x, dict)
    ]

    deferred.append(
        dict(LUONG_MINH_RULE)
    )

    payload["deferred_orphans"] = deferred

    result["payload"] = payload
    result["deferred_orphans"] = deferred

    return result


batch_svc._resolution_context = (
    patched_resolution_context
)


# ============================================================
# 4. PREVIEW SAU DEFER TRONG RAM
# ============================================================

preview = batch_svc.build_level_batch_preview(
    school_year_id=2,
    level_code="MN",
)


states = {}

candidate_ops = set()

for row in (
    preview.get("rows")
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
        candidate_ops.add(op)


print()
print("=" * 120)
print("3. KPI SAU DEFER TRONG RAM")
print("=" * 120)

print(
    "counts                =",
    preview.get("counts"),
)

print(
    "candidate_count       =",
    preview.get("candidate_count"),
)

print(
    "effective_block_count =",
    preview.get("effective_block_count"),
)

print(
    "ready_for_execution   =",
    preview.get("ready_for_execution"),
)

print()
print(
    "OP-0337 =",
    states.get("QD3805-OP-0337"),
)

print(
    "OP-0338 =",
    states.get("QD3805-OP-0338"),
)

print(
    "READY OPS =",
    sorted(candidate_ops),
)


print()
print("=" * 120)
print("4. EXTRA BLOCKERS SAU DEFER")
print("=" * 120)

print(
    json.dumps(
        preview.get("extra_blockers")
        or [],
        ensure_ascii=False,
        indent=2,
    )
)


print()
print("=" * 120)
print("5. RESOLUTION TRONG RAM")
print("=" * 120)

resolution_after = (
    preview.get("resolution")
    or {}
)

print(
    json.dumps(
        resolution_after.get(
            "deferred_orphans"
        )
        or [],
        ensure_ascii=False,
        indent=2,
    )
)


# ============================================================
# 5. EXPECTED RESULT
# ============================================================

if preview.get("counts") != {
    "KEEP": 51,
    "DONE": 184,
    "READY": 5,
    "BLOCK": 0,
}:
    raise RuntimeError(
        "KPI thay doi ngoai du kien."
    )

if preview.get("candidate_count") != 5:
    raise RuntimeError(
        "candidate_count != 5."
    )

if preview.get("effective_block_count") != 0:
    raise RuntimeError(
        "effective_block_count != 0."
    )

if preview.get("ready_for_execution") is not True:
    raise RuntimeError(
        "ready_for_execution chua True."
    )

if states.get("QD3805-OP-0337") != "DONE":
    raise RuntimeError(
        "OP-0337 khong con DONE."
    )

if states.get("QD3805-OP-0338") != "DONE":
    raise RuntimeError(
        "OP-0338 khong con DONE."
    )

if candidate_ops != READY_OPS:
    raise RuntimeError(
        "Danh sach 5 READY bi thay doi: "
        + repr(sorted(candidate_ops))
    )

extra_text = json.dumps(
    preview.get("extra_blockers") or [],
    ensure_ascii=False,
)

if "Lượng Minh" in extra_text:
    raise RuntimeError(
        "Luong Minh van con trong extra_blockers."
    )


# ============================================================
# 6. SAFETY
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
        "DUNG: file that da thay doi."
    )


print()
print("DRY-RUN             : PASS")
print("Database            : KHONG THAY DOI")
print("Batch service       : KHONG THAY DOI")
print("MN resolution       : KHONG THAY DOI")
print("MN roster           : KHONG THAY DOI")
print("Luong Minh          : DEFERRED TRONG MO PHONG")
print("Tu dong sap nhap LM : KHONG")
print("5 READY             : CHUA THUC HIEN")
print("Batch MN            : SAN SANG TRONG MO PHONG")
print("=" * 120)
