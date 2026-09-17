from __future__ import annotations

import sys
import json
import sqlite3
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


before_hash = {
    "db": sha256(DB),
    "service": sha256(SERVICE),
    "resolution": sha256(RESOLUTION),
    "roster": sha256(ROSTER),
}

print("=" * 120)
print("DRY-RUN OP-0338 -> PRECOMPLETED DONE")
print("CHI TRONG RAM - KHONG SUA SOURCE/JSON/DB")
print("=" * 120)

for k, v in before_hash.items():
    print(k, "=", v)

if before_hash["db"] != EXPECTED_DB_SHA:
    raise RuntimeError(
        "DUNG: DB khong dung nen da khoa."
    )

if before_hash["service"] != EXPECTED_SERVICE_SHA:
    raise RuntimeError(
        "DUNG: batch service da thay doi."
    )

if before_hash["resolution"] != EXPECTED_RESOLUTION_SHA:
    raise RuntimeError(
        "DUNG: MN resolution da thay doi."
    )

if before_hash["roster"] != EXPECTED_ROSTER_SHA:
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

print("counts                =", baseline.get("counts"))
print("candidate_count       =", baseline.get("candidate_count"))
print("effective_block_count =", baseline.get("effective_block_count"))

if baseline.get("counts") != {
    "KEEP": 51,
    "DONE": 183,
    "READY": 5,
    "BLOCK": 1,
}:
    raise RuntimeError(
        "DUNG: KPI baseline khong con dung."
    )

# ============================================================
# 2. KIEM TRA PHAN LOAI NOI BO
# ============================================================

original_context = (
    batch_svc._registry_level_context
)

original_precompleted = (
    batch_svc._precompleted_resolution_status
)

ctx = original_context("MN")

pure_ids = {
    str(x.get("operation_id") or "")
    for x in (ctx.get("pure_actions") or [])
}

special_ids = {
    str(x.get("operation_id") or "")
    for x in (ctx.get("special_ops") or [])
}

print()
print("=" * 120)
print("2. PHAN LOAI NOI BO OP-0338")
print("=" * 120)

print("OP-0338 trong pure_actions =", OP in pure_ids)
print("OP-0338 trong special_ops  =", OP in special_ids)

# Đây là trạng thái ta đã dự đoán:
# operation cùng cấp MN nhưng đồng thời bị cờ SPECIAL cũ chặn.
if OP not in pure_ids:
    raise RuntimeError(
        "DUNG: OP-0338 khong nam trong pure_actions. "
        "Khong tu dong sua."
    )

if OP not in special_ids:
    raise RuntimeError(
        "DUNG: OP-0338 khong nam trong special_ops nhu du kien."
    )

# ============================================================
# 3. PATCH CONTEXT CHI TRONG RAM
# ============================================================

RULE = {
    "operation_id": OP,
    "source_school_code": "40429323",
    "target_school_code": "40429301",
    "previous_year_code": "2025-2026",
    "current_year_code": "2026-2027",
    "expected_previous_target_active": 31,
    "expected_previous_source_active": 41,
    "expected_current_target_active": 72,
    "expected_current_source_active": 0,
    "expected_previous_identity_count": 72,
    "require_identity_exact": True,
    "allow_special_audit_gate": True,
    "reason": (
        "MN Nghi Trung đã inactive; "
        "MN TT Quán Hành active; "
        "31 + 41 = 72; "
        "72 staff_member_id hiện hành tại đích "
        "khớp 100% union eligible 2025-2026. "
        "Đã hoàn tất trước, không chạy lại."
    ),
}

def patched_context(level_code):
    result = original_context(level_code)

    if str(level_code or "").upper() != "MN":
        return result

    result = dict(result)

    resolution = dict(
        result.get("resolution") or {}
    )

    precompleted = [
        dict(x)
        for x in (
            resolution.get("precompleted")
            or []
        )
        if isinstance(x, dict)
    ]

    if not any(
        str(x.get("operation_id") or "") == OP
        for x in precompleted
    ):
        precompleted.append(
            dict(RULE)
        )

    resolution["precompleted"] = (
        precompleted
    )

    result["resolution"] = resolution

    # Chỉ bỏ cờ SPECIAL cũ của riêng OP-0338.
    # Không đụng OP-0141 / OP-0244 / OP-0704.
    result["special_ops"] = [
        dict(x)
        for x in (
            result.get("special_ops")
            or []
        )
        if str(
            x.get("operation_id")
            or ""
        ) != OP
    ]

    return result


# ============================================================
# 4. PRECOMPLETED CHECK RIENG OP-0338 TRONG RAM
# ============================================================

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

    rule = next(
        (
            dict(x)
            for x in (
                resolution.get("precompleted")
                or []
            )
            if str(
                x.get("operation_id")
                or ""
            ) == OP
        ),
        None,
    )

    if rule is None:
        return {
            "pass": False,
            "operation_id": OP,
            "reason": "Khong co rule OP-0338.",
        }

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

    target_audit = next(
        (
            x
            for x in school_checks
            if (
                str(
                    x.get("role")
                    or ""
                ).upper()
                == "TARGET"
                and str(
                    x.get("school_code")
                    or ""
                ).strip()
                == "40429301"
            )
        ),
        None,
    )

    source_audit = next(
        (
            x
            for x in school_checks
            if (
                str(
                    x.get("role")
                    or ""
                ).upper()
                == "SOURCE"
                and str(
                    x.get("school_code")
                    or ""
                ).strip()
                == "40429323"
            )
        ),
        None,
    )

    blockers = [
        str(x or "").strip()
        for x in (
            audit.get("blockers")
            or []
        )
        if str(x or "").strip()
    ]

    mapped_gate_only = (
        len(blockers) == 1
        and (
            "V4.3 chỉ mở thực hiện cho phương án MAPPED"
            in blockers[0]
        )
    )

    con = batch_svc.engine._connect(
        read_only=True
    )

    try:
        target = con.execute(
            """
            SELECT id,code,name,is_active
            FROM schools
            WHERE code='40429301'
            LIMIT 1
            """
        ).fetchone()

        source = con.execute(
            """
            SELECT id,code,name,is_active
            FROM schools
            WHERE code='40429323'
            LIMIT 1
            """
        ).fetchone()

        if target is None or source is None:
            return {
                "pass": False,
                "operation_id": OP,
                "reason": "Khong tim thay source/target.",
            }

        years = {
            str(x["code"]): int(x["id"])
            for x in con.execute(
                """
                SELECT id,code
                FROM school_years
                WHERE code IN (
                    '2025-2026',
                    '2026-2027'
                )
                """
            ).fetchall()
        }

        py = years.get("2025-2026")
        cy = years.get("2026-2027")

        if py is None or cy is None:
            raise RuntimeError(
                "Khong tim thay du nam hoc."
            )

        previous_rows = con.execute(
            """
            SELECT staff_member_id
            FROM staff_year_records
            WHERE school_year_id=?
              AND school_id IN (747,749)
              AND is_active=1
              AND status_code='DANG_LAM_VIEC'
            """,
            (py,),
        ).fetchall()

        current_rows = con.execute(
            """
            SELECT staff_member_id
            FROM staff_year_records
            WHERE school_year_id=?
              AND school_id=747
              AND is_active=1
            """,
            (cy,),
        ).fetchall()

        previous_ids = {
            int(x["staff_member_id"])
            for x in previous_rows
        }

        current_ids = {
            int(x["staff_member_id"])
            for x in current_rows
        }

        current_source_total = int(
            con.execute(
                """
                SELECT COUNT(*)
                FROM staff_year_records
                WHERE school_year_id=?
                  AND school_id=749
                """,
                (cy,),
            ).fetchone()[0]
        )

    finally:
        con.close()

    checks = {
        "target_audit_pass":
            target_audit is not None
            and str(
                target_audit.get("status")
                or ""
            ).upper() == "PASS"
            and int(
                target_audit.get(
                    "active_db_eligible"
                )
                or 0
            ) == 31,

        "source_audit_pass":
            source_audit is not None
            and str(
                source_audit.get("status")
                or ""
            ).upper() == "PASS"
            and int(
                source_audit.get(
                    "active_db_eligible"
                )
                or 0
            ) == 41,

        "audit_only_blocked_by_old_mapped_gate":
            (
                bool(audit.get("pass"))
                or mapped_gate_only
            ),

        "target_active":
            bool(target["is_active"])
            is True,

        "source_inactive":
            bool(source["is_active"])
            is False,

        "previous_union_72":
            len(previous_ids) == 72,

        "current_target_72":
            len(current_ids) == 72,

        "identity_exact":
            previous_ids == current_ids,

        "current_source_zero":
            current_source_total == 0,
    }

    return {
        "pass": all(checks.values()),
        "operation_id": OP,
        "rule": rule,
        "evidence": {
            "previous_target_eligible":
                31,

            "previous_source_eligible":
                41,

            "previous_union_count":
                len(previous_ids),

            "current_target_count":
                len(current_ids),

            "current_source_total":
                current_source_total,

            "identity_exact":
                previous_ids
                == current_ids,

            "audit_original_pass":
                bool(
                    audit.get("pass")
                ),

            "audit_blockers":
                blockers,
        },
        "checks": checks,
        "reason": (
            "OP-0338 đã hoàn tất trước; "
            "chỉ bị cờ SPECIAL/MAPPED cũ chặn."
            if all(checks.values())
            else
            "Chưa đủ bằng chứng."
        ),
    }


batch_svc._registry_level_context = (
    patched_context
)

batch_svc._precompleted_resolution_status = (
    patched_precompleted
)

# ============================================================
# 5. PREVIEW SAU PATCH TRONG RAM
# ============================================================

after = batch_svc.build_level_batch_preview(
    school_year_id=2,
    level_code="MN",
)

states = {}

op0338_row = None

for row in after.get("rows") or []:
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
        )

    if op_id == OP:
        op0338_row = row

print()
print("=" * 120)
print("3. KPI SAU DRY-RUN TRONG RAM")
print("=" * 120)

print(
    "counts                =",
    after.get("counts"),
)

print(
    "candidate_count       =",
    after.get("candidate_count"),
)

print(
    "effective_block_count =",
    after.get("effective_block_count"),
)

print(
    "ready_for_execution   =",
    after.get("ready_for_execution"),
)

print()
print("OP-0338 =", states.get(OP))

print()
print("=" * 120)
print("4. PRECOMPLETED OP-0338")
print("=" * 120)

if op0338_row is None:
    print("<KHONG TIM THAY ROW>")
else:
    print(
        json.dumps(
            op0338_row.get(
                "qd3805_precompleted"
            ),
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )

print()
print("=" * 120)
print("5. EXTRA BLOCKERS")
print("=" * 120)

for item in (
    after.get("extra_blockers")
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
# 6. EXPECTED RESULT
# ============================================================

expected = {
    "KEEP": 51,
    "DONE": 184,
    "READY": 5,
    "BLOCK": 0,
}

if after.get("counts") != expected:
    raise RuntimeError(
        "KPI sau dry-run khong dung ky vong: "
        + repr(after.get("counts"))
    )

if states.get(OP) != "DONE":
    raise RuntimeError(
        "OP-0338 chua thanh DONE."
    )

if after.get("candidate_count") != 5:
    raise RuntimeError(
        "candidate_count khong bang 5."
    )

if (
    after.get("effective_block_count")
    != 1
):
    raise RuntimeError(
        "effective_block_count khong bang 1."
    )

# ============================================================
# 7. SAFETY
# ============================================================

after_hash = {
    "db": sha256(DB),
    "service": sha256(SERVICE),
    "resolution": sha256(RESOLUTION),
    "roster": sha256(ROSTER),
}

print()
print("=" * 120)
print("6. KIEM TRA AN TOAN")
print("=" * 120)

for k in before_hash:
    print(
        k,
        ":",
        before_hash[k],
        "->",
        after_hash[k],
    )

if before_hash != after_hash:
    raise RuntimeError(
        "DUNG: file that da thay doi."
    )

print()
print("DRY-RUN            : PASS")
print("Database           : KHONG THAY DOI")
print("Batch service      : KHONG THAY DOI")
print("MN resolution      : KHONG THAY DOI")
print("MN roster          : KHONG THAY DOI")
print("OP-0338            : DONE TRONG MO PHONG")
print("5 phuong an READY  : CHUA THUC HIEN")
print("=" * 120)
