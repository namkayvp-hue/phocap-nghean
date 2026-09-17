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

OP = "QD3805-OP-0338"

EXPECTED_DB_SHA = (
    "44b1aa841cdd76301c57d9fc601121ae"
    "96f9312084ef05959eaae54acf17c8c9"
)

EXPECTED_SERVICE_SHA = (
    "2860998dbd6d14e5110e7bc64316845"
    "a9dc2aad084b36a0a09f38b79056161bc"
)

EXPECTED_RESOLUTION_SHA = (
    "eb68a6593b551b96a5112ce3a647ffe3"
    "4f55913007885f9bc541e56170291755"
)

EXPECTED_ROSTER_SHA = (
    "ef865f74aa51c2700ceb7746d5433b63"
    "fc6a52a4e3169014ebe0e446ac441120"
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
print("DRY-RUN OP-0338 PRECOMPLETED - LAN 2")
print("CHI TRONG RAM - KHONG SUA SOURCE / JSON / DATABASE")
print("=" * 120)

for key, value in before.items():
    print(key, "=", value)


if before["db"] != EXPECTED_DB_SHA:
    raise RuntimeError(
        "DUNG: DB khong dung nen da khoa."
    )

if before["service"] != EXPECTED_SERVICE_SHA:
    raise RuntimeError(
        "DUNG: batch service da thay doi."
    )

if before["resolution"] != EXPECTED_RESOLUTION_SHA:
    raise RuntimeError(
        "DUNG: MN resolution da thay doi."
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
    "DONE": 183,
    "READY": 5,
    "BLOCK": 1,
}:
    raise RuntimeError(
        "DUNG: baseline MN khong con dung."
    )


# ============================================================
# 2. XAC NHAN OP-0338 THUOC PURE_ACTIONS
# ============================================================

ctx = batch_svc._registry_level_context(
    "MN"
)

pure_ids = {
    str(x.get("operation_id") or "")
    for x in (
        ctx.get("pure_actions")
        or []
    )
}

special_ids = {
    str(x.get("operation_id") or "")
    for x in (
        ctx.get("special_ops")
        or []
    )
}


print()
print("=" * 120)
print("2. PHAN LOAI NOI BO")
print("=" * 120)

print(
    "OP-0338 trong pure_actions =",
    OP in pure_ids,
)

print(
    "OP-0338 trong special_ops  =",
    OP in special_ids,
)


if OP not in pure_ids:
    raise RuntimeError(
        "DUNG: OP-0338 khong nam trong pure_actions."
    )


# ============================================================
# 3. RULE PRECOMPLETED TAM TRONG RAM
# ============================================================

RULE = {
    "operation_id":
        "QD3805-OP-0338",

    "source_school_code":
        "40429323",

    "target_school_code":
        "40429301",

    "previous_year_code":
        "2025-2026",

    "current_year_code":
        "2026-2027",

    "expected_previous_target_active":
        31,

    "expected_previous_source_active":
        41,

    "expected_current_target_active":
        72,

    "expected_current_source_active":
        0,

    "expected_previous_identity_count":
        72,

    "require_identity_exact":
        True,

    "allow_special_audit_gate":
        True,

    "reason": (
        "MN Nghi Trung da inactive; "
        "MN TT Quan Hanh active; "
        "31 + 41 = 72; "
        "72 staff_member_id hien hanh tai dich "
        "khop 100% union eligible 2025-2026. "
        "Da hoan tat truoc, khong chay lai."
    ),
}


original_resolution_context = (
    batch_svc._resolution_context
)

original_precompleted = (
    batch_svc._precompleted_resolution_status
)


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

    precompleted = [
        dict(x)
        for x in (
            payload.get("precompleted")
            or []
        )
        if isinstance(x, dict)
    ]

    if any(
        str(
            x.get("operation_id")
            or ""
        ) == OP
        for x in precompleted
    ):
        raise RuntimeError(
            "OP-0338 da ton tai trong resolution that."
        )

    precompleted.append(
        dict(RULE)
    )

    payload["precompleted"] = (
        precompleted
    )

    result["payload"] = payload

    result["precompleted"] = (
        precompleted
    )

    return result


def patched_precompleted(
    *,
    operation_id,
    resolution,
    audit_item=None,
):

    if str(operation_id or "") != OP:
        return original_precompleted(
            operation_id=operation_id,
            resolution=resolution,
            audit_item=audit_item,
        )

    audit = dict(
        audit_item or {}
    )

    school_checks = [
        dict(x)
        for x in (
            audit.get("school_checks")
            or []
        )
        if isinstance(x, dict)
    ]

    blockers = [
        str(x or "").strip()
        for x in (
            audit.get("blockers")
            or []
        )
        if str(x or "").strip()
    ]

    print()
    print("=" * 120)
    print("3. AUDIT GATE OP-0338")
    print("=" * 120)

    print(
        "audit.pass goc =",
        audit.get("pass"),
    )

    print(
        "blockers goc   =",
        blockers,
    )

    print(
        "school checks  =",
        [
            {
                "role":
                    x.get("role"),

                "code":
                    x.get("school_code"),

                "status":
                    x.get("status"),

                "eligible":
                    x.get(
                        "active_db_eligible"
                    ),
            }
            for x in school_checks
        ],
    )

    # --------------------------------------------------------
    # Khóa rất chặt:
    # chỉ cho phép bypass nếu đúng duy nhất
    # blocker MAPPED cũ và mọi trường đều PASS.
    # --------------------------------------------------------

    all_school_pass = (
        len(school_checks) == 2
        and all(
            str(
                x.get("status")
                or ""
            ).upper()
            == "PASS"
            for x in school_checks
        )
    )

    eligible_by_code = {
        str(
            x.get("school_code")
            or ""
        ).strip():
            int(
                x.get(
                    "active_db_eligible"
                )
                or 0
            )
        for x in school_checks
    }

    exact_eligible = (
        eligible_by_code.get(
            "40429301"
        ) == 31
        and eligible_by_code.get(
            "40429323"
        ) == 41
    )

    exact_old_gate = (
        len(blockers) == 1
        and blockers[0]
        == (
            "V4.3 chỉ mở thực hiện cho phương án "
            "MAPPED có nguồn → đích rõ ràng."
        )
    )

    if not all_school_pass:
        return {
            "pass": False,
            "operation_id": OP,
            "reason": (
                "Khong bypass: "
                "school_checks chua PASS het."
            ),
        }

    if not exact_eligible:
        return {
            "pass": False,
            "operation_id": OP,
            "reason": (
                "Khong bypass: "
                "31/41 eligible khong dung."
            ),
        }

    if not exact_old_gate:
        return {
            "pass": False,
            "operation_id": OP,
            "reason": (
                "Khong bypass: "
                "blocker khong phai duy nhat "
                "gate MAPPED cu."
            ),
        }

    # --------------------------------------------------------
    # Chỉ trong RAM:
    # đổi audit.pass thành True để dùng NGUYÊN
    # checker precompleted chính thức hiện tại.
    # Không bỏ qua bất kỳ check DB/identity nào.
    # --------------------------------------------------------

    audit_for_precompleted = dict(
        audit
    )

    audit_for_precompleted[
        "pass"
    ] = True

    result = original_precompleted(
        operation_id=operation_id,
        resolution=resolution,
        audit_item=audit_for_precompleted,
    )

    result = dict(
        result or {}
    )

    evidence = dict(
        result.get("evidence")
        or {}
    )

    evidence.update({
        "original_audit_pass":
            bool(
                audit.get("pass")
            ),

        "special_gate_bypassed":
            True,

        "original_audit_blockers":
            blockers,

        "all_school_checks_pass":
            all_school_pass,

        "eligible_40429301":
            eligible_by_code.get(
                "40429301"
            ),

        "eligible_40429323":
            eligible_by_code.get(
                "40429323"
            ),
    })

    result["evidence"] = evidence

    result["reason"] = (
        "OP-0338 đã hoàn tất trước. "
        "Hai school-check V4.3 đều PASS; "
        "block duy nhất là gate action_type MAPPED cũ; "
        "toàn bộ kiểm tra DB và identity "
        "của precompleted chính thức vẫn phải PASS."
    )

    return result


batch_svc._resolution_context = (
    patched_resolution_context
)

batch_svc._precompleted_resolution_status = (
    patched_precompleted
)


# ============================================================
# 4. PREVIEW TRONG RAM
# ============================================================

preview = batch_svc.build_level_batch_preview(
    school_year_id=2,
    level_code="MN",
)


states = {}

op_row = None

for row in (
    preview.get("rows")
    or []
):
    if not isinstance(row, dict):
        continue

    op_id = str(
        row.get(
            "qd3805_operation_id"
        )
        or ""
    )

    if op_id:
        states[op_id] = str(
            row.get(
                "batch_state"
            )
            or ""
        ).upper()

    if op_id == OP:
        op_row = row


print()
print("=" * 120)
print("4. KPI SAU DRY-RUN")
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
    "OP-0338 =",
    states.get(OP),
)


print()
print("=" * 120)
print("5. BANG CHUNG PRECOMPLETED OP-0338")
print("=" * 120)

if op_row is None:
    print(
        "<KHONG TIM THAY OP-0338>"
    )

else:
    print(
        json.dumps(
            op_row.get(
                "qd3805_precompleted"
            ),
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )


print()
print("=" * 120)
print("6. EXTRA BLOCKERS")
print("=" * 120)

for item in (
    preview.get("extra_blockers")
    or []
):
    print(
        json.dumps(
            item,
            ensure_ascii=False,
            default=str,
        )
    )


# ============================================================
# 5. EXPECTED
# ============================================================

expected_counts = {
    "KEEP": 51,
    "DONE": 184,
    "READY": 5,
    "BLOCK": 0,
}

if (
    preview.get("counts")
    != expected_counts
):
    raise RuntimeError(
        "KPI sau dry-run khong dung ky vong: "
        + repr(
            preview.get("counts")
        )
    )

if states.get(OP) != "DONE":
    raise RuntimeError(
        "OP-0338 chua thanh DONE."
    )

if (
    preview.get("candidate_count")
    != 5
):
    raise RuntimeError(
        "candidate_count != 5."
    )

if (
    preview.get(
        "effective_block_count"
    )
    != 1
):
    raise RuntimeError(
        "effective_block_count != 1."
    )

if (
    preview.get(
        "ready_for_execution"
    )
    is not False
):
    raise RuntimeError(
        "ready_for_execution phai van False "
        "vi con Luong Minh."
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
print("7. KIEM TRA AN TOAN")
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
print("DRY-RUN           : PASS")
print("Database          : KHONG THAY DOI")
print("Batch service     : KHONG THAY DOI")
print("MN resolution     : KHONG THAY DOI")
print("MN roster         : KHONG THAY DOI")
print("OP-0338           : DONE TRONG MO PHONG")
print("5 phuong an READY : CHUA THUC HIEN")
print("Luong Minh        : VAN LA BLOCKER DUY NHAT")
print("=" * 120)
