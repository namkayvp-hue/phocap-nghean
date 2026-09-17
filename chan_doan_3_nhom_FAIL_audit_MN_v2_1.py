from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from collections import Counter, defaultdict
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


EXPECTED = {
    "db":
        "882e4925fd3e39d7e097ce127612c093"
        "852075e608d3f937294135282afec75a",

    "service":
        "963b8d6a280d8abef8e96486abd87d77"
        "cea289b08d2edb497647f250ed1b2af8",

    "lock":
        "ad310048a4c5b239404e0902cc04fda1"
        "d73474d11a739a2ca009d2727e4390c3",

    "resolution":
        "22ca7931ec40408ced25a3bde14a9672c"
        "04e12a760a077a44bb9d65b709b1163",

    "roster":
        "ef865f74aa51c2700ceb7746d5433b63"
        "fc6a52a4e3169014ebe0e446ac441120",
}


YEAR_PREVIOUS = 1
YEAR_CURRENT = 2


def sha256(path):
    h = hashlib.sha256()

    with path.open("rb") as f:
        for block in iter(
            lambda: f.read(1024 * 1024),
            b"",
        ):
            h.update(block)

    return h.hexdigest()


def connect_ro():
    con = sqlite3.connect(
        DB.resolve().as_uri()
        + "?mode=ro",
        uri=True,
        timeout=90,
    )

    con.row_factory = sqlite3.Row
    con.execute("PRAGMA query_only=ON")
    con.execute("PRAGMA foreign_keys=ON")

    return con


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


def active_staff_ids(
    con,
    schools,
    year_id,
):

    if not schools:
        return set()

    marks = ",".join(
        "?"
        for _ in schools
    )

    rows = con.execute(
        f"""
        SELECT DISTINCT staff_member_id
        FROM staff_year_records
        WHERE school_year_id=?
          AND school_id IN ({marks})
          AND is_active=1
          AND staff_member_id IS NOT NULL
        """,
        [
            year_id,
            *schools,
        ],
    ).fetchall()

    return {
        int(x["staff_member_id"])
        for x in rows
    }


def parse_ids(value):

    if value is None:
        return []

    try:
        raw = json.loads(
            str(value)
        )
    except Exception:
        raw = []

    if not isinstance(raw, list):
        raw = [raw]

    result = []

    for x in raw:

        try:
            n = int(x)

            if n:
                result.append(n)

        except Exception:
            pass

    return sorted(
        set(result)
    )


def find_operation_paths(
    value,
    wanted,
    path="$",
):

    result = []

    if isinstance(value, dict):

        if (
            str(
                value.get(
                    "operation_id"
                )
                or ""
            )
            == wanted
        ):
            result.append({
                "path":
                    path,

                "item":
                    value,
            })


        for key, child in value.items():

            result.extend(
                find_operation_paths(
                    child,
                    wanted,
                    path
                    + "."
                    + str(key),
                )
            )


    elif isinstance(value, list):

        for index, child in enumerate(
            value
        ):

            result.extend(
                find_operation_paths(
                    child,
                    wanted,
                    path
                    + "["
                    + str(index)
                    + "]",
                )
            )


    return result


print("=" * 128)
print(
    "CHAN DOAN 3 NHOM FAIL CUA AUDIT MN V2.1"
)
print(
    "CHI DOC - KHONG SUA DATABASE / SOURCE / REGISTRY"
)
print("=" * 128)


# ============================================================
# 1. HASH GATE
# ============================================================

paths = {
    "db": DB,
    "service": SERVICE,
    "lock": LOCK,
    "resolution": RESOLUTION,
    "roster": ROSTER,
}

before = {}


print()
print("=" * 128)
print("1. HASH GATE")
print("=" * 128)


for key, path in paths.items():

    value = sha256(path)

    before[key] = value

    print(
        f"{key:12s} = {value}"
    )

    if value != EXPECTED[key]:

        raise RuntimeError(
            "DUNG: "
            + key
            + " khong dung nen da khoa."
        )


# ============================================================
# 2. STATE ROWS
# ============================================================

from app.services import (
    school_merger_level_batch_service
    as svc
)


ctx = svc._registry_level_context(
    "MN"
)

rows, counts, candidates, meta = (
    svc._state_rows(
        2,
        "MN",
    )
)


pure_ids = {
    str(
        x.get("operation_id")
        or ""
    )
    for x in (
        ctx.get(
            "pure_actions"
        )
        or []
    )
}


row_map = {
    str(
        x.get(
            "qd3805_operation_id"
        )
        or ""
    ):
        dict(x)
    for x in rows
    if str(
        x.get(
            "qd3805_operation_id"
        )
        or ""
    )
}


print()
print("=" * 128)
print("2. NEN 189 PURE")
print("=" * 128)

print(
    "pure operation =",
    len(pure_ids),
)

print(
    "counts         =",
    counts,
)


# ============================================================
# 3. SO SANH RAW UNION VS ELIGIBLE AUDIT
# ============================================================

con = connect_ro()

try:

    raw_exact = 0
    eligible_exact = 0

    raw_mismatch = []
    eligible_mismatch = []

    no_eligible_measure = []

    eligible_explains_raw_fail = 0


    for op in sorted(
        pure_ids
    ):

        row = row_map[
            op
        ]


        src = school_ids(
            row.get(
                "source_schools"
            )
        )


        target_obj = (
            row.get(
                "target_school"
            )
            or {}
        )


        try:
            tgt = int(
                target_obj.get("id")
                or 0
            )
        except Exception:
            tgt = 0


        previous_raw = (
            active_staff_ids(
                con,
                [
                    tgt,
                    *src,
                ],
                YEAR_PREVIOUS,
            )
        )

        current = (
            active_staff_ids(
                con,
                [tgt],
                YEAR_CURRENT,
            )
        )


        raw_n = len(
            previous_raw
        )

        current_n = len(
            current
        )


        if previous_raw == current:

            raw_exact += 1

        else:

            raw_mismatch.append({
                "operation_id":
                    op,

                "plan_id":
                    row.get("id"),

                "target_id":
                    tgt,

                "source_ids":
                    src,

                "raw_previous_union":
                    raw_n,

                "current_target":
                    current_n,

                "raw_missing":
                    len(
                        previous_raw
                        - current
                    ),

                "raw_extra":
                    len(
                        current
                        - previous_raw
                    ),
            })


        audit = (
            row.get(
                "source_audit"
            )
            or {}
        )


        checks = (
            audit.get(
                "school_checks"
            )
            or []
        )


        eligible_values = []

        for check in checks:

            if not isinstance(
                check,
                dict,
            ):
                continue

            if (
                check.get(
                    "active_db_eligible"
                )
                is None
            ):
                continue

            eligible_values.append(
                int(
                    check.get(
                        "active_db_eligible"
                    )
                    or 0
                )
            )


        if not eligible_values:

            no_eligible_measure.append(
                op
            )

            continue


        eligible_n = sum(
            eligible_values
        )


        if eligible_n == current_n:

            eligible_exact += 1

            if (
                previous_raw
                != current
            ):
                eligible_explains_raw_fail += 1

        else:

            eligible_mismatch.append({
                "operation_id":
                    op,

                "plan_id":
                    row.get("id"),

                "audit_status":
                    audit.get(
                        "status"
                    ),

                "audit_pass":
                    audit.get(
                        "pass"
                    ),

                "target_id":
                    tgt,

                "source_ids":
                    src,

                "raw_previous_union":
                    raw_n,

                "eligible_sum":
                    eligible_n,

                "current_target":
                    current_n,

                "eligible_delta":
                    current_n
                    - eligible_n,

                "blockers":
                    audit.get(
                        "blockers"
                    )
                    or [],
            })


    print()
    print("=" * 128)
    print(
        "3. NHAN SU: RAW UNION VS ACTIVE_DB_ELIGIBLE"
    )
    print("=" * 128)

    print(
        "189 operations                =",
        len(pure_ids),
    )

    print(
        "raw union EXACT               =",
        raw_exact,
    )

    print(
        "raw union mismatch            =",
        len(raw_mismatch),
    )

    print(
        "eligible count EXACT current  =",
        eligible_exact,
    )

    print(
        "raw FAIL duoc eligible giai thich =",
        eligible_explains_raw_fail,
    )

    print(
        "eligible mismatch             =",
        len(
            eligible_mismatch
        ),
    )

    print(
        "khong co eligible measure     =",
        len(
            no_eligible_measure
        ),
    )


    print()
    print(
        "20 RAW MISMATCH DAU:"
    )

    for item in raw_mismatch[:20]:

        print(
            json.dumps(
                item,
                ensure_ascii=False,
            )
        )


    print()
    print(
        "CAC ELIGIBLE MISMATCH:"
    )

    for item in eligible_mismatch[:30]:

        print(
            json.dumps(
                item,
                ensure_ascii=False,
            )
        )


    print()
    print(
        "NO ELIGIBLE MEASURE:"
    )

    print(
        no_eligible_measure
    )


    # ========================================================
    # 4. SOURCE AUDIT BLOCK
    # ========================================================

    source_block = []


    for op in sorted(
        pure_ids
    ):

        row = row_map[
            op
        ]

        audit = (
            row.get(
                "source_audit"
            )
            or {}
        )


        if (
            audit
            and audit.get(
                "pass"
            )
            is False
        ):

            source_block.append(
                op
            )


    print()
    print("=" * 128)
    print("4. 7 SOURCE AUDIT BLOCK")
    print("=" * 128)

    print(
        "count =",
        len(
            source_block
        ),
    )


    resolution_payload = json.loads(
        RESOLUTION.read_text(
            encoding="utf-8-sig"
        )
    )


    for op in source_block:

        row = row_map[
            op
        ]

        audit = (
            row.get(
                "source_audit"
            )
            or {}
        )


        print()
        print("-" * 128)

        print(
            "OP =",
            op,
        )

        print(
            "plan_id          =",
            row.get("id"),
        )

        print(
            "batch_state      =",
            row.get(
                "batch_state"
            ),
        )

        print(
            "execution_status =",
            row.get(
                "execution_status"
            ),
        )

        print(
            "execution_label  =",
            row.get(
                "execution_label"
            ),
        )

        print(
            "source_ids       =",
            school_ids(
                row.get(
                    "source_schools"
                )
            ),
        )

        print(
            "target_id        =",
            (
                row.get(
                    "target_school"
                )
                or {}
            ).get("id"),
        )

        print(
            "audit status/pass=",
            audit.get(
                "status"
            ),
            "/",
            audit.get(
                "pass"
            ),
        )

        print(
            "blockers =",
            json.dumps(
                audit.get(
                    "blockers"
                )
                or [],
                ensure_ascii=False,
            ),
        )


        print(
            "school_checks:"
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

            print(
                json.dumps(
                    {
                        "role":
                            check.get(
                                "role"
                            ),

                        "school_id":
                            check.get(
                                "school_id"
                            ),

                        "status":
                            check.get(
                                "status"
                            ),

                        "source_total":
                            check.get(
                                "source_total_rows"
                            ),

                        "source_active":
                            check.get(
                                "source_active_rows"
                            ),

                        "db_previous":
                            check.get(
                                "db_previous_total_rows"
                            ),

                        "eligible":
                            check.get(
                                "active_db_eligible"
                            ),

                        "issues":
                            check.get(
                                "issues"
                            )
                            or [],
                    },
                    ensure_ascii=False,
                )
            )


        paths_found = (
            find_operation_paths(
                resolution_payload,
                op,
            )
        )


        print(
            "resolution paths =",
            [
                x["path"]
                for x in paths_found
            ],
        )


        if paths_found:

            for found in paths_found:

                print(
                    json.dumps(
                        found,
                        ensure_ascii=False,
                        default=str,
                    )
                )


    # ========================================================
    # 5. MISSING MERGER LOG
    # ========================================================

    operation_log_map = defaultdict(
        list
    )


    for log in con.execute(
        """
        SELECT *
        FROM school_merger_operations
        WHERE school_year_id=2
        ORDER BY id
        """
    ).fetchall():

        signature = (
            int(
                log[
                    "target_school_id"
                ]
            ),

            tuple(
                parse_ids(
                    log[
                        "source_school_ids_json"
                    ]
                )
            ),
        )


        operation_log_map[
            signature
        ].append(
            dict(log)
        )


    missing_log_ops = []


    for op in sorted(
        pure_ids
    ):

        row = row_map[
            op
        ]

        src = school_ids(
            row.get(
                "source_schools"
            )
        )

        tgt = int(
            (
                row.get(
                    "target_school"
                )
                or {}
            ).get("id")
            or 0
        )


        signature = (
            tgt,
            tuple(src),
        )


        if not (
            operation_log_map.get(
                signature
            )
            or []
        ):
            missing_log_ops.append(
                op
            )


    print()
    print("=" * 128)
    print("5. MISSING MERGER LOG")
    print("=" * 128)

    print(
        "count =",
        len(
            missing_log_ops
        ),
    )


    for op in missing_log_ops:

        row = row_map[
            op
        ]


        print()
        print("-" * 128)

        print(
            "OP =",
            op,
        )

        print(
            "plan_id          =",
            row.get("id"),
        )

        print(
            "execution_status =",
            row.get(
                "execution_status"
            ),
        )

        print(
            "execution_label  =",
            row.get(
                "execution_label"
            ),
        )

        print(
            "execution_record =",
            json.dumps(
                row.get(
                    "execution_record"
                ),
                ensure_ascii=False,
                default=str,
            ),
        )


        found = (
            find_operation_paths(
                resolution_payload,
                op,
            )
        )


        print(
            "resolution paths =",
            [
                x["path"]
                for x in found
            ],
        )


        for item in found:

            print(
                json.dumps(
                    item,
                    ensure_ascii=False,
                    default=str,
                )
            )


    # ========================================================
    # 6. PHAN TICH CAC STAFF MEMBER RAW BI THIEU
    # ========================================================

    category = Counter()

    example_rows = []


    for raw_item in raw_mismatch:

        op = raw_item[
            "operation_id"
        ]

        row = row_map[
            op
        ]

        src = school_ids(
            row.get(
                "source_schools"
            )
        )

        tgt = int(
            (
                row.get(
                    "target_school"
                )
                or {}
            ).get("id")
            or 0
        )


        previous = active_staff_ids(
            con,
            [
                tgt,
                *src,
            ],
            YEAR_PREVIOUS,
        )

        current = active_staff_ids(
            con,
            [tgt],
            YEAR_CURRENT,
        )


        missing_ids = sorted(
            previous
            - current
        )


        for staff_id in missing_ids:

            member = con.execute(
                """
                SELECT
                    id,
                    ministry_staff_code,
                    full_name,
                    is_active
                FROM staff_members
                WHERE id=?
                """,
                (staff_id,),
            ).fetchone()


            current_rows = con.execute(
                """
                SELECT
                    school_id,
                    status_code,
                    is_active,
                    source_status_label
                FROM staff_year_records
                WHERE staff_member_id=?
                  AND school_year_id=2
                ORDER BY school_id,id
                """,
                (staff_id,),
            ).fetchall()


            active_elsewhere = [
                int(x["school_id"])
                for x in current_rows
                if bool(
                    x["is_active"]
                )
                and int(
                    x["school_id"]
                )
                != tgt
            ]


            inactive_current = any(
                not bool(
                    x["is_active"]
                )
                for x in current_rows
            )


            master_active = (
                bool(
                    member[
                        "is_active"
                    ]
                )
                if member
                is not None
                else None
            )


            if master_active is False:

                reason = (
                    "STAFF_MEMBER_MASTER_INACTIVE"
                )

            elif active_elsewhere:

                reason = (
                    "CURRENT_ACTIVE_AT_OTHER_SCHOOL"
                )

            elif inactive_current:

                reason = (
                    "CURRENT_RECORD_INACTIVE"
                )

            elif not current_rows:

                reason = (
                    "NO_CURRENT_YEAR_RECORD"
                )

            else:

                reason = (
                    "OTHER"
                )


            category[
                reason
            ] += 1


            if len(
                example_rows
            ) < 30:

                example_rows.append({
                    "operation_id":
                        op,

                    "target_id":
                        tgt,

                    "staff_member_id":
                        staff_id,

                    "ministry_staff_code":
                        (
                            member[
                                "ministry_staff_code"
                            ]
                            if member
                            else None
                        ),

                    "full_name":
                        (
                            member[
                                "full_name"
                            ]
                            if member
                            else None
                        ),

                    "master_active":
                        master_active,

                    "reason":
                        reason,

                    "current_rows":
                        [
                            dict(x)
                            for x in current_rows
                        ],
                })


    print()
    print("=" * 128)
    print("6. PHAN LOAI RAW STAFF KHONG CO TAI TARGET")
    print("=" * 128)

    print(
        "CATEGORY =",
        dict(
            category
        ),
    )


    print()
    print(
        "30 MAU DAU:"
    )

    for item in example_rows:

        print(
            json.dumps(
                item,
                ensure_ascii=False,
                default=str,
            )
        )


    # ========================================================
    # 7. DB HEALTH
    # ========================================================

    integrity = str(
        con.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]
    )

    fk = len(
        con.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()
    )


    print()
    print("=" * 128)
    print("7. DATABASE HEALTH")
    print("=" * 128)

    print(
        "integrity =",
        integrity,
    )

    print(
        "FK        =",
        fk,
    )


finally:

    con.close()


# ============================================================
# 8. IMMUTABILITY
# ============================================================

print()
print("=" * 128)
print("8. FILE IMMUTABILITY")
print("=" * 128)


for key, path in paths.items():

    after = sha256(path)

    print(
        key,
        ":",
        before[key],
        "->",
        after,
    )

    if after != before[key]:

        raise RuntimeError(
            "DUNG: file "
            + key
            + " da thay doi."
        )


print()
print("=" * 128)
print("CHAN DOAN V2.1 HOAN TAT")
print("=" * 128)

print(
    "KHONG SUA DATABASE."
)

print(
    "KHONG SUA SERVICE / REGISTRY / ROSTER."
)

print(
    "KHONG ROLLBACK."
)

print(
    "KHONG CHAY LAI SAP NHAP."
)

print("=" * 128)
