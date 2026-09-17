from __future__ import annotations

import hashlib
import json
import sys
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

LOCK = (
    ROOT
    / "data"
    / "school_merger_registry"
    / "qd3805_level_lock.json"
)

ROSTER_DIR = (
    ROOT
    / "data"
    / "school_merger_source_rosters"
)


EXPECTED_DB_SHA = (
    "882e4925fd3e39d7e097ce127612c093"
    "852075e608d3f937294135282afec75a"
)

EXPECTED_SERVICE_SHA = (
    "963b8d6a280d8abef8e96486abd87d77"
    "cea289b08d2edb497647f250ed1b2af8"
)

EXPECTED_LOCK_SHA = (
    "ad310048a4c5b239404e0902cc04fda1"
    "d73474d11a739a2ca009d2727e4390c3"
)


PRECOMPLETED = {
    "QD3805-OP-0342",
    "QD3805-OP-0343",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()

    with path.open("rb") as f:
        for block in iter(
            lambda: f.read(1024 * 1024),
            b"",
        ):
            h.update(block)

    return h.hexdigest()


def school_ids(items):
    result = []

    for item in items or []:

        if not isinstance(item, dict):
            continue

        try:
            sid = int(
                item.get("id")
                or 0
            )

            if sid:
                result.append(sid)

        except Exception:
            pass

    return sorted(
        set(result)
    )


def target_id(item):
    if not isinstance(item, dict):
        return None

    try:
        value = int(
            item.get("id")
            or 0
        )

        return value or None

    except Exception:
        return None


print("=" * 132)
print("CHAN DOAN MO KHOA THCS - V2")
print("CHI DOC - KHONG SUA DATABASE / SERVICE / REGISTRY / ROSTER")
print("=" * 132)


# ============================================================
# 1. HASH GATE
# ============================================================

before = {
    "db": sha256(DB),
    "service": sha256(SERVICE),
    "lock": sha256(LOCK),
}


print()
print("=" * 132)
print("1. HASH GATE")
print("=" * 132)


for key, value in before.items():
    print(
        f"{key:12s} = {value}"
    )


if before["db"] != EXPECTED_DB_SHA:
    raise RuntimeError(
        "DUNG: DB khong dung snapshot sau MN."
    )

if before["service"] != EXPECTED_SERVICE_SHA:
    raise RuntimeError(
        "DUNG: service da thay doi."
    )

if before["lock"] != EXPECTED_LOCK_SHA:
    raise RuntimeError(
        "DUNG: level lock da thay doi."
    )


# ============================================================
# 2. KIỂM TRA ROSTER HIỆN CÓ
# ============================================================

print()
print("=" * 132)
print("2. SOURCE ROSTER HIEN CO")
print("=" * 132)


if not ROSTER_DIR.exists():

    print(
        "KHONG TON TAI THU MUC:",
        ROSTER_DIR,
    )

else:

    files = sorted(
        x
        for x in ROSTER_DIR.iterdir()
        if x.is_file()
    )

    print(
        "roster file count =",
        len(files),
    )

    for path in files:

        print(
            path.name,
            "| sha256=",
            sha256(path),
            "| bytes=",
            path.stat().st_size,
        )


thcs_roster = (
    ROSTER_DIR
    / "THCS_2025_2026.json"
)


print()
print(
    "THCS_2025_2026.json exists =",
    thcs_roster.exists(),
)


if thcs_roster.exists():

    try:

        payload = json.loads(
            thcs_roster.read_text(
                encoding="utf-8-sig"
            )
        )

        print(
            "THCS roster header =",
            json.dumps(
                {
                    "dataset_id":
                        payload.get(
                            "dataset_id"
                        ),

                    "level_code":
                        payload.get(
                            "level_code"
                        ),

                    "school_year_code":
                        payload.get(
                            "school_year_code"
                        ),

                    "row_count":
                        payload.get(
                            "row_count"
                        ),

                    "school_count":
                        payload.get(
                            "school_count"
                        ),
                },
                ensure_ascii=False,
            ),
        )

    except Exception as exc:

        print(
            "THCS roster READ ERROR =",
            repr(exc),
        )


# ============================================================
# 3. LOAD SERVICE
# ============================================================

from app.services import (
    school_merger_level_batch_service
    as svc
)


ctx = svc._registry_level_context(
    "THCS"
)

rows, counts, candidates, meta = (
    svc._state_rows(
        2,
        "THCS",
    )
)


pure_ops = [
    dict(x)
    for x in (
        ctx.get("pure_actions")
        or []
    )
]


pure_by_id = {
    str(
        x.get("operation_id")
        or ""
    ): x

    for x in pure_ops
}


block_rows = [
    dict(x)
    for x in rows

    if str(
        x.get(
            "batch_state"
        )
        or ""
    ).upper()
    == "BLOCK"
]


print()
print("=" * 132)
print("3. THCS STATE")
print("=" * 132)

print(
    "counts =",
    counts,
)

print(
    "pure_actions =",
    len(pure_ops),
)

print(
    "BLOCK rows =",
    len(block_rows),
)


# ============================================================
# 4. HAI PRECOMPLETED
# ============================================================

print()
print("=" * 132)
print("4. PRECOMPLETED DA XAC NHAN")
print("=" * 132)


for row in block_rows:

    op = str(
        row.get(
            "qd3805_operation_id"
        )
        or ""
    )

    if op not in PRECOMPLETED:
        continue

    print(
        json.dumps(
            {
                "operation_id":
                    op,

                "plan_id":
                    row.get("id"),

                "state":
                    row.get(
                        "batch_state"
                    ),

                "execution_status":
                    row.get(
                        "execution_status"
                    ),

                "sources":
                    row.get(
                        "source_schools"
                    ),

                "target":
                    row.get(
                        "target_school"
                    ),
            },
            ensure_ascii=False,
            default=str,
        )
    )


# ============================================================
# 5. 18 MAPPED / NO HISTORY
# ============================================================

print()
print("=" * 132)
print("5. CAC BLOCK DA CO SOURCE -> TARGET")
print("=" * 132)


mapped_count = 0


for row in block_rows:

    op = str(
        row.get(
            "qd3805_operation_id"
        )
        or ""
    )

    if op in PRECOMPLETED:
        continue


    source_ids = school_ids(
        row.get(
            "source_schools"
        )
    )

    tid = target_id(
        row.get(
            "target_school"
        )
    )


    if (
        not source_ids
        or tid is None
    ):
        continue


    mapped_count += 1

    audit = (
        row.get(
            "source_audit"
        )
        or {}
    )


    school_checks = []


    for check in (
        audit.get(
            "school_checks"
        )
        or []
    ):

        if not isinstance(
            check,
            dict,
        ):
            continue


        school_checks.append({
            "role":
                check.get("role"),

            "school_id":
                check.get(
                    "school_id"
                ),

            "school_code":
                check.get(
                    "school_code"
                ),

            "school_name":
                check.get(
                    "school_name"
                ),

            "source_roster_found":
                check.get(
                    "source_roster_found"
                ),

            "source_total_rows":
                check.get(
                    "source_total_rows"
                ),

            "source_active_rows":
                check.get(
                    "source_active_rows"
                ),

            "db_previous_total_rows":
                check.get(
                    "db_previous_total_rows"
                ),

            "active_identity_matched":
                check.get(
                    "active_identity_matched"
                ),

            "active_at_expected_school":
                check.get(
                    "active_at_expected_school"
                ),

            "active_db_eligible":
                check.get(
                    "active_db_eligible"
                ),

            "issues":
                check.get(
                    "issues"
                )
                or [],

            "warnings":
                check.get(
                    "warnings"
                )
                or [],

            "dataset_ids":
                check.get(
                    "dataset_ids"
                )
                or [],
        })


    print()
    print(
        json.dumps(
            {
                "operation_id":
                    op,

                "plan_id":
                    row.get("id"),

                "commune":
                    row.get(
                        "commune_name"
                    ),

                "match_status":
                    row.get(
                        "match_status"
                    ),

                "source_ids":
                    source_ids,

                "target_id":
                    tid,

                "source_audit_status":
                    audit.get(
                        "status"
                    ),

                "source_audit_pass":
                    audit.get(
                        "pass"
                    ),

                "school_checks":
                    school_checks,

                "blockers":
                    audit.get(
                        "blockers"
                    )
                    or row.get(
                        "blockers"
                    )
                    or [],
            },
            ensure_ascii=False,
            default=str,
        )
    )


print()
print(
    "mapped BLOCK excluding precompleted =",
    mapped_count,
)


# ============================================================
# 6. 14 UNMAPPED
# ============================================================

print()
print("=" * 132)
print("6. CAC BLOCK CHUA KHOA DUOC SOURCE -> TARGET")
print("=" * 132)


unmapped_count = 0


for row in block_rows:

    op = str(
        row.get(
            "qd3805_operation_id"
        )
        or ""
    )

    if op in PRECOMPLETED:
        continue


    source_ids = school_ids(
        row.get(
            "source_schools"
        )
    )

    tid = target_id(
        row.get(
            "target_school"
        )
    )


    if (
        source_ids
        and tid is not None
    ):
        continue


    unmapped_count += 1

    registry_op = (
        pure_by_id.get(op)
        or {}
    )


    print()
    print(
        json.dumps(
            {
                "operation_id":
                    op,

                "plan_id":
                    row.get("id"),

                "commune":
                    row.get(
                        "commune_name"
                    ),

                "match_status":
                    row.get(
                        "match_status"
                    ),

                "action_type":
                    row.get(
                        "action_type"
                    ),

                "member_schools":
                    row.get(
                        "member_schools"
                    ),

                "current_sources":
                    row.get(
                        "source_schools"
                    ),

                "current_target":
                    row.get(
                        "target_school"
                    ),

                "registry": {
                    "excel_plan_range":
                        registry_op.get(
                            "excel_plan_range"
                        ),

                    "stt_members":
                        registry_op.get(
                            "stt_members"
                        ),

                    "commune":
                        registry_op.get(
                            "commune"
                        ),

                    "source_schools":
                        registry_op.get(
                            "source_schools"
                        ),

                    "source_levels":
                        registry_op.get(
                            "source_levels"
                        ),

                    "official_plan":
                        registry_op.get(
                            "official_plan"
                        ),

                    "target_text":
                        registry_op.get(
                            "target_text"
                        ),

                    "target_codes":
                        registry_op.get(
                            "target_codes"
                        ),

                    "target_levels":
                        registry_op.get(
                            "target_levels"
                        ),

                    "relation_type":
                        registry_op.get(
                            "relation_type"
                        ),

                    "batch":
                        registry_op.get(
                            "batch"
                        ),
                },

                "blockers":
                    row.get(
                        "blockers"
                    )
                    or (
                        row.get(
                            "source_audit"
                        )
                        or {}
                    ).get(
                        "blockers"
                    )
                    or [],
            },
            ensure_ascii=False,
            default=str,
        )
    )


print()
print(
    "unmapped BLOCK excluding precompleted =",
    unmapped_count,
)


# ============================================================
# 7. ISSUE CODE SUMMARY
# ============================================================

print()
print("=" * 132)
print("7. SOURCE AUDIT ISSUE CODE SUMMARY")
print("=" * 132)


issue_counts = {}


for row in block_rows:

    op = str(
        row.get(
            "qd3805_operation_id"
        )
        or ""
    )

    if op in PRECOMPLETED:
        continue


    source_ids = school_ids(
        row.get(
            "source_schools"
        )
    )

    tid = target_id(
        row.get(
            "target_school"
        )
    )


    if (
        not source_ids
        or tid is None
    ):
        continue


    audit = (
        row.get(
            "source_audit"
        )
        or {}
    )


    for check in (
        audit.get(
            "school_checks"
        )
        or []
    ):

        if not isinstance(
            check,
            dict,
        ):
            continue

        for issue in (
            check.get(
                "issues"
            )
            or []
        ):

            if not isinstance(
                issue,
                dict,
            ):
                continue

            code = str(
                issue.get(
                    "code"
                )
                or "NO_CODE"
            )

            issue_counts[
                code
            ] = (
                issue_counts.get(
                    code,
                    0,
                )
                + 1
            )


print(
    json.dumps(
        issue_counts,
        ensure_ascii=False,
        indent=2,
    )
)


# ============================================================
# 8. IMMUTABILITY
# ============================================================

print()
print("=" * 132)
print("8. FILE IMMUTABILITY")
print("=" * 132)


after = {
    "db": sha256(DB),
    "service": sha256(SERVICE),
    "lock": sha256(LOCK),
}


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
        "DUNG: co file bi thay doi "
        "trong luc chan doan."
    )


print()
print("=" * 132)
print("CHAN DOAN MO KHOA THCS V2: HOAN TAT")
print("=" * 132)

print(
    "KHONG SUA DATABASE."
)

print(
    "KHONG TAO / SUA ROSTER."
)

print(
    "KHONG SUA SERVICE / REGISTRY."
)

print(
    "KHONG CHAY SAP NHAP THCS."
)

print("=" * 132)
