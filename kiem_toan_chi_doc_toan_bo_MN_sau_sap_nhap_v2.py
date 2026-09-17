from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


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

BASELINE_DB = (
    ROOT
    / "exports"
    / "backup_truoc_sap_nhap_toan_tinh_v13_6_20260904_161006"
    / "phocap.db"
)


EXPECTED_HASH = {
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


EXPECTED_BATCH_FP = (
    "3ff70145c42c255075bb1430ea4bc4fde"
    "8da38521f7cb344b51349a75875cd60"
)

EXPECTED_PURE = 189
EXPECTED_KEEP = 52

EXPECTED_SPECIAL = {
    "QD3805-OP-0141",
    "QD3805-OP-0244",
    "QD3805-OP-0704",
}

EXPECTED_LAST5 = {
    "QD3805-OP-0175",
    "QD3805-OP-0410",
    "QD3805-OP-0449",
    "QD3805-OP-0592",
    "QD3805-OP-0600",
}

LM_OP = "QD3805-ORPHAN-R1216"
LM_ID = 256
LM_CODE = "40418311"

YEAR_ID = 2
PREVIOUS_YEAR_ID = 1
MOVE_YEARS = [2, 8]
PAST_YEARS = [1, 3, 4, 5, 6, 7]


FAILURES = []
WARNINGS = []


def fail(msg):
    FAILURES.append(str(msg))


def warn(msg):
    WARNINGS.append(str(msg))


def sha256(path: Path):
    h = hashlib.sha256()

    with path.open("rb") as f:
        for block in iter(
            lambda: f.read(1024 * 1024),
            b"",
        ):
            h.update(block)

    return h.hexdigest()


def qident(name: str):
    return (
        '"'
        + str(name).replace('"', '""')
        + '"'
    )


def marks(n: int):
    return ",".join(
        "?"
        for _ in range(n)
    )


def connect_ro(path: Path):
    con = sqlite3.connect(
        path.resolve().as_uri()
        + "?mode=ro",
        uri=True,
        timeout=90,
    )

    con.row_factory = sqlite3.Row
    con.execute("PRAGMA query_only=ON")
    con.execute("PRAGMA foreign_keys=ON")

    return con


def tables(con):
    return [
        str(x["name"])
        for x in con.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type='table'
              AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """
        ).fetchall()
    ]


def columns(con, table):
    return [
        str(x["name"])
        for x in con.execute(
            f"PRAGMA table_info({qident(table)})"
        ).fetchall()
    ]


def health(con):
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

    return integrity, fk


def int_id(value):
    try:
        value = int(value)
        return value if value > 0 else None
    except Exception:
        return None


def ids_from_school_objects(items):
    result = []

    for item in items or []:

        if not isinstance(item, dict):
            continue

        sid = int_id(
            item.get("id")
        )

        if sid is not None:
            result.append(sid)

    return sorted(
        set(result)
    )


def source_ids(row):
    return ids_from_school_objects(
        row.get(
            "source_schools"
        )
    )


def target_id(row):

    target = (
        row.get(
            "target_school"
        )
        or {}
    )

    if not isinstance(
        target,
        dict,
    ):
        return None

    return int_id(
        target.get("id")
    )


def keep_school_ids(row):
    return ids_from_school_objects(
        row.get(
            "member_schools"
        )
    )


def parse_ids(value):

    if value is None:
        return []

    if isinstance(
        value,
        (list, tuple),
    ):
        raw = value

    else:
        try:
            raw = json.loads(
                str(value)
            )
        except Exception:
            raw = [
                x.strip()
                for x in str(
                    value
                ).split(",")
                if x.strip()
            ]

    if not isinstance(
        raw,
        (list, tuple),
    ):
        raw = [raw]

    result = []

    for item in raw:
        sid = int_id(item)

        if sid is not None:
            result.append(sid)

    return sorted(
        set(result)
    )


def school(con, sid):

    row = con.execute(
        """
        SELECT
            id,
            code,
            name,
            commune_id,
            is_active
        FROM schools
        WHERE id=?
        """,
        (sid,),
    ).fetchone()

    return (
        dict(row)
        if row is not None
        else None
    )


def staff_ids(
    con,
    school_ids,
    year_id,
):

    if not school_ids:
        return set()

    rows = con.execute(
        f"""
        SELECT DISTINCT
            staff_member_id
        FROM staff_year_records
        WHERE school_year_id=?
          AND school_id IN (
              {marks(len(school_ids))}
          )
          AND is_active=1
          AND staff_member_id IS NOT NULL
        """,
        [
            year_id,
            *school_ids,
        ],
    ).fetchall()

    return {
        int(x["staff_member_id"])
        for x in rows
    }


def duplicate_staff(
    con,
    school_id,
):

    rows = con.execute(
        """
        SELECT
            staff_member_id,
            COUNT(*) AS n
        FROM staff_year_records
        WHERE school_year_id=2
          AND school_id=?
          AND is_active=1
          AND staff_member_id IS NOT NULL
        GROUP BY staff_member_id
        HAVING COUNT(*) > 1
        """,
        (school_id,),
    ).fetchall()

    return [
        dict(x)
        for x in rows
    ]


def encoded_value(value):

    if isinstance(value, bytes):
        return {
            "__bytes__":
                value.hex()
        }

    return value


def hash_query_rows(
    con,
    sql,
    params,
    cols,
):

    rows = con.execute(
        sql,
        params,
    ).fetchall()

    values = []

    for row in rows:

        item = [
            encoded_value(
                row[col]
            )
            for col in cols
        ]

        values.append(
            json.dumps(
                item,
                ensure_ascii=False,
                default=str,
                separators=(",", ":"),
            )
        )

    values.sort()

    h = hashlib.sha256()

    for value in values:
        h.update(
            value.encode(
                "utf-8"
            )
        )

        h.update(b"\n")

    return (
        len(values),
        h.hexdigest(),
    )


def hash_school_year_rows(
    con,
    table,
    cols,
    school_ids,
    year_ids,
):

    if not school_ids:
        return (
            0,
            hashlib.sha256(
                b""
            ).hexdigest(),
        )

    col_sql = ",".join(
        qident(x)
        for x in cols
    )

    sql = f"""
        SELECT {col_sql}
        FROM {qident(table)}
        WHERE school_id IN (
            {marks(len(school_ids))}
        )
          AND school_year_id IN (
            {marks(len(year_ids))}
        )
    """

    return hash_query_rows(
        con,
        sql,
        [
            *school_ids,
            *year_ids,
        ],
        cols,
    )


def hash_school_rows(
    con,
    table,
    cols,
    school_ids,
):

    if not school_ids:
        return (
            0,
            hashlib.sha256(
                b""
            ).hexdigest(),
        )

    col_sql = ",".join(
        qident(x)
        for x in cols
    )

    sql = f"""
        SELECT {col_sql}
        FROM {qident(table)}
        WHERE school_id IN (
            {marks(len(school_ids))}
        )
    """

    return hash_query_rows(
        con,
        sql,
        school_ids,
        cols,
    )


print("=" * 128)
print(
    "KIEM TOAN MN SAU SAP NHAP - V2"
)
print(
    "CHI DOC - KHONG GHI DATABASE / SOURCE / REGISTRY"
)
print("=" * 128)


# ============================================================
# 1. HASH
# ============================================================

paths = {
    "db": DB,
    "service": SERVICE,
    "lock": LOCK,
    "resolution": RESOLUTION,
    "roster": ROSTER,
}

before_hash = {}


print()
print("=" * 128)
print("1. HASH GATE")
print("=" * 128)


for key, path in paths.items():

    got = sha256(path)

    before_hash[key] = got

    print(
        f"{key:12s} = {got}"
    )

    if got != EXPECTED_HASH[key]:
        raise RuntimeError(
            "DUNG: "
            + key
            + " khong dung nen da khoa."
        )


if not BASELINE_DB.exists():
    raise RuntimeError(
        "DUNG: thieu baseline V13.6:\n"
        + str(BASELINE_DB)
    )


# ============================================================
# 2. REGISTRY STATE
# ============================================================

from app.services import (
    school_merger_level_batch_service
    as svc
)


ctx = svc._registry_level_context(
    "MN"
)

preview = (
    svc.build_level_batch_preview(
        school_year_id=2,
        level_code="MN",
    )
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

keep_ids = {
    str(
        x.get("operation_id")
        or ""
    )
    for x in (
        ctx.get(
            "keep_ops"
        )
        or []
    )
}

special_ops = list(
    ctx.get(
        "special_ops"
    )
    or []
)

special_ids = {
    str(
        x.get("operation_id")
        or ""
    )
    for x in special_ops
}

unresolved = list(
    ctx.get(
        "unresolved"
    )
    or []
)


row_map = {}

duplicate_op_rows = []


for raw in rows:

    row = dict(raw)

    op = str(
        row.get(
            "qd3805_operation_id"
        )
        or ""
    )

    if not op:
        continue

    if op in row_map:
        duplicate_op_rows.append(
            op
        )

    row_map[op] = row


print()
print("=" * 128)
print("2. REGISTRY / STATE ROWS")
print("=" * 128)

print(
    "pure       =",
    len(pure_ids),
)

print(
    "keep       =",
    len(keep_ids),
)

print(
    "special    =",
    len(special_ids),
)

print(
    "unresolved =",
    len(unresolved),
)

print(
    "state rows =",
    len(rows),
)

print(
    "counts     =",
    counts,
)

print(
    "preview    =",
    preview.get(
        "counts"
    ),
)

print(
    "all_done   =",
    preview.get(
        "all_done"
    ),
)


if len(pure_ids) != 189:
    fail("Pure operations != 189.")

if len(keep_ids) != 52:
    fail("KEEP operations != 52.")

if special_ids != EXPECTED_SPECIAL:
    fail(
        "3 special operation IDs khong dung."
    )

if unresolved:
    fail(
        "Van con unresolved MN."
    )

if duplicate_op_rows:
    fail(
        "Co duplicate operation trong state rows."
    )

if set(row_map) != (
    pure_ids | keep_ids
):
    fail(
        "State rows khong bang dung "
        "189 pure + 52 KEEP."
    )

if counts != {
    "KEEP": 52,
    "DONE": 189,
    "READY": 0,
    "BLOCK": 0,
}:
    fail(
        "State counts khong dung 52/189/0/0."
    )

if preview.get("counts") != {
    "KEEP": 52,
    "DONE": 189,
    "READY": 0,
    "BLOCK": 0,
}:
    fail(
        "Preview counts khong dung."
    )

if (
    preview.get(
        "candidate_count"
    )
    != 0
):
    fail(
        "candidate_count != 0."
    )

if (
    preview.get(
        "effective_block_count"
    )
    != 0
):
    fail(
        "effective_block_count != 0."
    )

if (
    preview.get(
        "all_done"
    )
    is not True
):
    fail(
        "all_done != True."
    )


# ============================================================
# 3. EXTRACT SOURCE/TARGET THẬT
# ============================================================

pure_map = {}

shape_errors = []
source_audit_errors = []


for op in sorted(
    pure_ids
):

    row = row_map.get(op)

    if row is None:
        shape_errors.append({
            "operation_id":
                op,

            "error":
                "MISSING_STATE_ROW",
        })
        continue


    state = str(
        row.get(
            "batch_state"
        )
        or ""
    ).upper()


    src = source_ids(row)

    tgt = target_id(row)


    if (
        state != "DONE"
        or not src
        or tgt is None
        or tgt in src
    ):
        shape_errors.append({
            "operation_id":
                op,

            "plan_id":
                row.get("id"),

            "state":
                state,

            "source_ids":
                src,

            "target_id":
                tgt,
        })

        continue


    pure_map[op] = {
        "plan_id":
            str(
                row.get("id")
                or ""
            ),

        "source_ids":
            src,

        "target_id":
            tgt,

        "row":
            row,
    }


    source_audit = (
        row.get(
            "source_audit"
        )
        or {}
    )


    if (
        isinstance(
            source_audit,
            dict,
        )
        and source_audit
        and source_audit.get(
            "pass"
        )
        is False
    ):
        source_audit_errors.append({
            "operation_id":
                op,

            "plan_id":
                row.get("id"),

            "status":
                source_audit.get(
                    "status"
                ),

            "message":
                source_audit.get(
                    "message"
                ),
        })


print()
print("=" * 128)
print("3. SOURCE / TARGET CUA 189 DONE")
print("=" * 128)

print(
    "valid mappings      =",
    len(pure_map),
)

print(
    "shape errors        =",
    len(shape_errors),
)

print(
    "source audit errors =",
    len(source_audit_errors),
)


if shape_errors:
    fail(
        "Co pure operation khong doc duoc "
        "source_schools/target_school."
    )

if source_audit_errors:
    fail(
        "Co source audit hien tai FAIL."
    )


# ============================================================
# 4. BUILD CHAIN / FINAL TARGET
# ============================================================

source_to_target = {}

source_owner = {}

duplicate_source = []


for op, item in pure_map.items():

    tgt = item[
        "target_id"
    ]

    for sid in item[
        "source_ids"
    ]:

        if sid in source_to_target:

            duplicate_source.append({
                "school_id":
                    sid,

                "operation_1":
                    source_owner[sid],

                "operation_2":
                    op,
            })

        else:

            source_to_target[
                sid
            ] = tgt

            source_owner[
                sid
            ] = op


all_sources = set(
    source_to_target
)

all_plan_targets = {
    item[
        "target_id"
    ]
    for item in pure_map.values()
}


def resolve_final(start):

    seen = set()

    current = start

    while current in source_to_target:

        if current in seen:
            raise RuntimeError(
                "CHAIN CYCLE tai school_id="
                + str(current)
            )

        seen.add(current)

        current = source_to_target[
            current
        ]

    return current


final_for_source = {}

chain_errors = []


for sid in sorted(
    all_sources
):

    try:
        final_for_source[
            sid
        ] = resolve_final(
            sid
        )

    except Exception as exc:
        chain_errors.append({
            "school_id":
                sid,

            "error":
                str(exc),
        })


final_targets = set(
    final_for_source.values()
)

intermediate_targets = (
    all_plan_targets
    & all_sources
)


print()
print("=" * 128)
print("4. CHAIN / FINAL TARGET")
print("=" * 128)

print(
    "unique sources       =",
    len(all_sources),
)

print(
    "plan targets         =",
    len(all_plan_targets),
)

print(
    "intermediate targets =",
    len(intermediate_targets),
)

print(
    "final targets        =",
    len(final_targets),
)

print(
    "duplicate source     =",
    len(duplicate_source),
)

print(
    "chain errors         =",
    len(chain_errors),
)


if duplicate_source:
    fail(
        "Co source school thuoc nhieu pure operation."
    )

if chain_errors:
    fail(
        "Co chain cycle/chain khong hop le."
    )


# ============================================================
# 5. DB + BASELINE
# ============================================================

con = connect_ro(DB)
old = connect_ro(BASELINE_DB)


try:

    integrity, fk = health(con)

    old_integrity, old_fk = health(old)


    print()
    print("=" * 128)
    print("5. DATABASE HEALTH")
    print("=" * 128)

    print(
        "Current integrity/FK =",
        integrity,
        "/",
        fk,
    )

    print(
        "Baseline integrity/FK =",
        old_integrity,
        "/",
        old_fk,
    )


    if (
        integrity.lower() != "ok"
        or fk != 0
    ):
        fail(
            "Current DB integrity/FK FAIL."
        )


    if (
        old_integrity.lower()
        != "ok"
        or old_fk != 0
    ):
        fail(
            "Baseline V13.6 integrity/FK FAIL."
        )


    # ========================================================
    # 6. SOURCE INACTIVE / FINAL TARGET ACTIVE
    # ========================================================

    source_state_errors = []

    final_target_errors = []


    for sid in sorted(
        all_sources
    ):

        s = school(
            con,
            sid,
        )

        if (
            s is None
            or bool(
                s["is_active"]
            )
        ):
            source_state_errors.append({
                "school_id":
                    sid,

                "operation_id":
                    source_owner.get(
                        sid
                    ),

                "school":
                    s,
            })


    for tid in sorted(
        final_targets
    ):

        s = school(
            con,
            tid,
        )

        if (
            s is None
            or not bool(
                s["is_active"]
            )
        ):
            final_target_errors.append({
                "school_id":
                    tid,

                "school":
                    s,
            })


    print()
    print("=" * 128)
    print("6. TRANG THAI TRUONG")
    print("=" * 128)

    print(
        "absorbed source errors =",
        len(source_state_errors),
    )

    print(
        "final target errors    =",
        len(final_target_errors),
    )


    if source_state_errors:
        fail(
            "Co source sau sap nhap "
            "van ACTIVE/khong ton tai."
        )

    if final_target_errors:
        fail(
            "Co final target khong ACTIVE."
        )


    # ========================================================
    # 7. OPERATION LOG SIGNATURE
    # ========================================================

    operation_logs = defaultdict(
        list
    )


    for row in con.execute(
        """
        SELECT
            id,
            target_school_id,
            source_school_ids_json,
            backup_name,
            created_at
        FROM school_merger_operations
        WHERE school_year_id=2
        ORDER BY id
        """
    ).fetchall():

        signature = (
            int(
                row[
                    "target_school_id"
                ]
            ),

            tuple(
                parse_ids(
                    row[
                        "source_school_ids_json"
                    ]
                )
            ),
        )

        operation_logs[
            signature
        ].append(
            dict(row)
        )


    missing_logs = []
    duplicate_logs = []


    for op, item in pure_map.items():

        sig = (
            item[
                "target_id"
            ],
            tuple(
                item[
                    "source_ids"
                ]
            ),
        )

        found = (
            operation_logs.get(
                sig
            )
            or []
        )

        if not found:

            missing_logs.append({
                "operation_id":
                    op,

                "plan_id":
                    item[
                        "plan_id"
                    ],

                "source_ids":
                    item[
                        "source_ids"
                    ],

                "target_id":
                    item[
                        "target_id"
                    ],
            })

        elif len(found) > 1:

            duplicate_logs.append({
                "operation_id":
                    op,

                "operation_log_ids":
                    [
                        x["id"]
                        for x in found
                    ],
            })


    print()
    print("=" * 128)
    print("7. SCHOOL_MERGER_OPERATIONS LOG")
    print("=" * 128)

    print(
        "missing logs   =",
        len(missing_logs),
    )

    print(
        "duplicate logs =",
        len(duplicate_logs),
    )


    if missing_logs:
        fail(
            "Co pure operation khong co merger log."
        )

    if duplicate_logs:
        fail(
            "Co source->target bi ghi merger log lap."
        )


    # ========================================================
    # 8. CURRENT/FUTURE RESIDUAL
    # ========================================================

    residual = {}


    if all_sources:

        sm = marks(
            len(all_sources)
        )

        ym = marks(
            len(MOVE_YEARS)
        )


        for table in tables(con):

            cols = set(
                columns(
                    con,
                    table,
                )
            )

            if not {
                "school_id",
                "school_year_id",
            }.issubset(cols):
                continue


            n = int(
                con.execute(
                    f"""
                    SELECT COUNT(*)
                    FROM {qident(table)}
                    WHERE school_id IN ({sm})
                      AND school_year_id IN ({ym})
                    """,
                    [
                        *sorted(
                            all_sources
                        ),
                        *MOVE_YEARS,
                    ],
                ).fetchone()[0]
                or 0
            )


            if n:
                residual[
                    table
                ] = n


    print()
    print("=" * 128)
    print("8. CURRENT / FUTURE SOURCE RESIDUAL")
    print("=" * 128)

    print(
        "residual =",
        residual,
    )


    if residual:
        fail(
            "CURRENT/FUTURE van con "
            "tai absorbed source."
        )


    # ========================================================
    # 9. USER ACCOUNT
    # ========================================================

    active_user_source = 0
    user_move_errors = []


    if all_sources:

        sm = marks(
            len(all_sources)
        )


        active_user_source = int(
            con.execute(
                f"""
                SELECT COUNT(*)
                FROM users
                WHERE school_id IN ({sm})
                  AND is_active=1
                """,
                sorted(
                    all_sources
                ),
            ).fetchone()[0]
            or 0
        )


        baseline_users = old.execute(
            f"""
            SELECT
                id,
                username,
                school_id,
                is_active
            FROM users
            WHERE school_id IN ({sm})
            ORDER BY id
            """,
            sorted(
                all_sources
            ),
        ).fetchall()


        for bu in baseline_users:

            sid = int(
                bu["school_id"]
            )

            username = str(
                bu["username"]
                or ""
            )

            cur = con.execute(
                """
                SELECT
                    id,
                    username,
                    school_id,
                    is_active
                FROM users
                WHERE id=?
                """,
                (
                    int(
                        bu["id"]
                    ),
                ),
            ).fetchone()


            if cur is None:

                user_move_errors.append({
                    "user_id":
                        int(
                            bu["id"]
                        ),

                    "username":
                        username,

                    "error":
                        "MISSING_CURRENT",
                })

                continue


            if username.lower().startswith(
                "truong_"
            ):

                if (
                    int(
                        cur["school_id"]
                        or 0
                    )
                    != sid
                    or bool(
                        cur["is_active"]
                    )
                ):
                    user_move_errors.append({
                        "user_id":
                            int(
                                cur["id"]
                            ),

                        "username":
                            username,

                        "expected":
                            "SOURCE + INACTIVE",

                        "actual_school":
                            cur[
                                "school_id"
                            ],

                        "actual_active":
                            cur[
                                "is_active"
                            ],
                    })

            else:

                final_target = (
                    final_for_source.get(
                        sid
                    )
                )

                if (
                    final_target is not None
                    and int(
                        cur["school_id"]
                        or 0
                    )
                    != final_target
                ):
                    user_move_errors.append({
                        "user_id":
                            int(
                                cur["id"]
                            ),

                        "username":
                            username,

                        "source":
                            sid,

                        "expected_target":
                            final_target,

                        "actual_school":
                            cur[
                                "school_id"
                            ],
                    })


    print()
    print("=" * 128)
    print("9. USER ACCOUNT")
    print("=" * 128)

    print(
        "active users at sources =",
        active_user_source,
    )

    print(
        "user move errors        =",
        len(user_move_errors),
    )


    if active_user_source != 0:
        fail(
            "Van con active user tai source."
        )

    if user_move_errors:
        fail(
            "Co user baseline khong ve dung "
            "final target/khong khoa login truong."
        )


    # ========================================================
    # 10. STAFF UNION THEO FINAL TARGET
    # ========================================================

    groups = defaultdict(
        set
    )


    for sid, final in (
        final_for_source.items()
    ):
        groups[
            final
        ].add(
            sid
        )

        groups[
            final
        ].add(
            final
        )


    staff_errors = []
    duplicate_staff_errors = []


    for final, members in sorted(
        groups.items()
    ):

        previous = staff_ids(
            con,
            sorted(members),
            PREVIOUS_YEAR_ID,
        )

        current = staff_ids(
            con,
            [final],
            YEAR_ID,
        )


        if previous != current:

            staff_errors.append({
                "final_target":
                    final,

                "member_schools":
                    sorted(
                        members
                    ),

                "previous_union":
                    len(previous),

                "current_target":
                    len(current),

                "missing":
                    sorted(
                        previous
                        - current
                    )[:20],

                "extra":
                    sorted(
                        current
                        - previous
                    )[:20],
            })


        dup = duplicate_staff(
            con,
            final,
        )


        if dup:
            duplicate_staff_errors.append({
                "final_target":
                    final,

                "duplicates":
                    dup[:20],
            })


    print()
    print("=" * 128)
    print("10. NHAN SU SAU SAP NHAP")
    print("=" * 128)

    print(
        "consolidation groups  =",
        len(groups),
    )

    print(
        "staff union mismatch =",
        len(staff_errors),
    )

    print(
        "duplicate staff rows =",
        len(
            duplicate_staff_errors
        ),
    )


    if staff_errors:
        fail(
            "Co final target khong khop "
            "union nhan su 2025-2026."
        )

    if duplicate_staff_errors:
        fail(
            "Co duplicate staff_member_id "
            "tai final target."
        )


    # ========================================================
    # 11. PAST EXACT VS V13.6
    # ========================================================

    all_pure_involved = sorted(
        all_sources
        | all_plan_targets
    )


    common_tables = sorted(
        set(
            tables(con)
        )
        & set(
            tables(old)
        )
    )


    past_checked = 0
    past_mismatch = []


    for table in common_tables:

        cur_cols = set(
            columns(
                con,
                table,
            )
        )

        old_cols_list = columns(
            old,
            table,
        )

        old_cols = set(
            old_cols_list
        )


        if not {
            "school_id",
            "school_year_id",
        }.issubset(
            cur_cols
            & old_cols
        ):
            continue


        shared_cols = [
            x
            for x in old_cols_list
            if x in cur_cols
        ]


        old_sig = (
            hash_school_year_rows(
                old,
                table,
                shared_cols,
                all_pure_involved,
                PAST_YEARS,
            )
        )

        new_sig = (
            hash_school_year_rows(
                con,
                table,
                shared_cols,
                all_pure_involved,
                PAST_YEARS,
            )
        )


        past_checked += 1


        if old_sig != new_sig:

            past_mismatch.append({
                "table":
                    table,

                "baseline":
                    old_sig,

                "current":
                    new_sig,
            })


    print()
    print("=" * 128)
    print("11. PAST EXACT VS BACKUP V13.6")
    print("=" * 128)

    print(
        "tables checked =",
        past_checked,
    )

    print(
        "mismatches     =",
        len(
            past_mismatch
        ),
    )


    if past_mismatch:
        fail(
            "PAST data cua pure plans "
            "khong exact voi baseline V13.6."
        )


    # ========================================================
    # 12. 52 KEEP - MEMBER_SCHOOLS
    # ========================================================

    keep_owner = {}

    keep_mapping_errors = []

    keep_school_set = set()


    for op in sorted(
        keep_ids
    ):

        row = row_map.get(op)

        if row is None:
            keep_mapping_errors.append({
                "operation_id":
                    op,

                "error":
                    "MISSING_ROW",
            })

            continue


        state = str(
            row.get(
                "batch_state"
            )
            or ""
        ).upper()

        member_ids = (
            keep_school_ids(
                row
            )
        )


        if (
            state != "KEEP"
            or not member_ids
        ):
            keep_mapping_errors.append({
                "operation_id":
                    op,

                "state":
                    state,

                "member_ids":
                    member_ids,
            })

            continue


        for sid in member_ids:

            if sid in keep_owner:

                keep_mapping_errors.append({
                    "school_id":
                        sid,

                    "operation_1":
                        keep_owner[
                            sid
                        ],

                    "operation_2":
                        op,

                    "error":
                        "DUPLICATE_KEEP_SCHOOL",
                })

            else:
                keep_owner[
                    sid
                ] = op


            keep_school_set.add(
                sid
            )


            s = school(
                con,
                sid,
            )


            if (
                s is None
                or not bool(
                    s["is_active"]
                )
            ):
                keep_mapping_errors.append({
                    "operation_id":
                        op,

                    "school_id":
                        sid,

                    "school":
                        s,

                    "error":
                        "KEEP_NOT_ACTIVE",
                })


    keep_pure_overlap = (
        keep_school_set
        & (
            all_sources
            | all_plan_targets
        )
    )


    print()
    print("=" * 128)
    print("12. 52 GIU NGUYEN")
    print("=" * 128)

    print(
        "KEEP operations      =",
        len(keep_ids),
    )

    print(
        "KEEP schools         =",
        len(keep_school_set),
    )

    print(
        "KEEP mapping errors  =",
        len(
            keep_mapping_errors
        ),
    )

    print(
        "KEEP / pure overlap  =",
        sorted(
            keep_pure_overlap
        ),
    )


    if keep_mapping_errors:
        fail(
            "Co KEEP operation khong map "
            "dung member_schools/ACTIVE."
        )

    if keep_pure_overlap:
        fail(
            "Co KEEP school dong thoi "
            "tham gia pure merger."
        )


    # ========================================================
    # 13. KEEP DATABASE EXACT VS BASELINE
    # ========================================================

    keep_exact_mismatch = []
    keep_tables_checked = 0


    for table in common_tables:

        if table == "schools":
            continue


        cur_cols = set(
            columns(
                con,
                table,
            )
        )

        old_cols_list = columns(
            old,
            table,
        )

        old_cols = set(
            old_cols_list
        )


        if "school_id" not in (
            cur_cols
            & old_cols
        ):
            continue


        shared_cols = [
            x
            for x in old_cols_list
            if x in cur_cols
        ]


        old_sig = hash_school_rows(
            old,
            table,
            shared_cols,
            sorted(
                keep_school_set
            ),
        )

        new_sig = hash_school_rows(
            con,
            table,
            shared_cols,
            sorted(
                keep_school_set
            ),
        )


        keep_tables_checked += 1


        if old_sig != new_sig:

            keep_exact_mismatch.append({
                "table":
                    table,

                "baseline":
                    old_sig,

                "current":
                    new_sig,
            })


    # schools table: stable fields.
    stable_school_fields = [
        "id",
        "code",
        "name",
        "commune_id",
        "is_active",
    ]


    if keep_school_set:

        sm = marks(
            len(
                keep_school_set
            )
        )

        old_school_sig = hash_query_rows(
            old,
            f"""
            SELECT
                id,code,name,commune_id,is_active
            FROM schools
            WHERE id IN ({sm})
            """,
            sorted(
                keep_school_set
            ),
            stable_school_fields,
        )

        new_school_sig = hash_query_rows(
            con,
            f"""
            SELECT
                id,code,name,commune_id,is_active
            FROM schools
            WHERE id IN ({sm})
            """,
            sorted(
                keep_school_set
            ),
            stable_school_fields,
        )


        if (
            old_school_sig
            != new_school_sig
        ):
            keep_exact_mismatch.append({
                "table":
                    "schools",

                "baseline":
                    old_school_sig,

                "current":
                    new_school_sig,
            })


    print()
    print("=" * 128)
    print("13. KEEP EXACT VS BASELINE V13.6")
    print("=" * 128)

    print(
        "school-scoped tables checked =",
        keep_tables_checked,
    )

    print(
        "KEEP exact mismatches         =",
        len(
            keep_exact_mismatch
        ),
    )


    if keep_exact_mismatch:
        fail(
            "Du lieu cua KEEP schools "
            "da khac baseline V13.6."
        )


    # ========================================================
    # 14. LƯỢNG MINH
    # ========================================================

    lm_row = row_map.get(
        LM_OP
    )

    lm_members = (
        keep_school_ids(
            lm_row
        )
        if lm_row
        else []
    )

    lm_school = school(
        con,
        LM_ID,
    )


    lm_bad_logs = []

    for row in con.execute(
        """
        SELECT
            id,
            target_school_id,
            source_school_ids_json
        FROM school_merger_operations
        WHERE school_year_id=2
        ORDER BY id
        """
    ).fetchall():

        src = parse_ids(
            row[
                "source_school_ids_json"
            ]
        )

        tgt = int(
            row[
                "target_school_id"
            ]
        )

        if (
            LM_ID in src
            and tgt != LM_ID
        ):
            lm_bad_logs.append(
                int(row["id"])
            )


    print()
    print("=" * 128)
    print("14. MAM NON LUONG MINH")
    print("=" * 128)

    print(
        "operation in KEEP =",
        LM_OP in keep_ids,
    )

    print(
        "member school IDs =",
        lm_members,
    )

    print(
        "school            =",
        lm_school,
    )

    print(
        "bad merger logs   =",
        lm_bad_logs,
    )


    if (
        LM_OP not in keep_ids
        or LM_ID not in lm_members
        or lm_school is None
        or str(
            lm_school[
                "code"
            ]
        )
        != LM_CODE
        or not bool(
            lm_school[
                "is_active"
            ]
        )
        or lm_bad_logs
    ):
        fail(
            "Luong Minh khong dat "
            "GIU NGUYEN."
        )


    # ========================================================
    # 15. BATCH LOG
    # ========================================================

    batch_rows = con.execute(
        """
        SELECT *
        FROM school_merger_level_batches
        WHERE school_year_id=2
          AND UPPER(TRIM(level_code))='MN'
        ORDER BY id
        """
    ).fetchall()


    print()
    print("=" * 128)
    print("15. BATCH LOG MN")
    print("=" * 128)

    print(
        "batch rows =",
        len(batch_rows),
    )


    if len(batch_rows) != 1:

        fail(
            "MN phai co dung 1 batch log."
        )

        batch = {}

    else:

        batch = dict(
            batch_rows[0]
        )

        print(
            "batch_id          =",
            batch.get("id"),
        )

        print(
            "keep_count        =",
            batch.get(
                "keep_count"
            ),
        )

        print(
            "done_before_count =",
            batch.get(
                "done_before_count"
            ),
        )

        print(
            "executed_count    =",
            batch.get(
                "executed_count"
            ),
        )

        print(
            "fingerprint       =",
            batch.get(
                "batch_fingerprint"
            ),
        )


        if (
            int(
                batch.get(
                    "keep_count"
                )
                or 0
            )
            != 52
            or int(
                batch.get(
                    "done_before_count"
                )
                or 0
            )
            != 184
            or int(
                batch.get(
                    "executed_count"
                )
                or 0
            )
            != 5
            or str(
                batch.get(
                    "batch_fingerprint"
                )
                or ""
            )
            != EXPECTED_BATCH_FP
        ):
            fail(
                "MN batch log khong dung."
            )


    # ========================================================
    # 16. 5 OFFICIAL EXECUTIONS
    # ========================================================

    last5_plan_map = {
        op:
            pure_map[op][
                "plan_id"
            ]
        for op in EXPECTED_LAST5
        if op in pure_map
    }


    official_rows = []

    if last5_plan_map:

        pm = marks(
            len(
                last5_plan_map
            )
        )

        official_rows = [
            dict(x)
            for x in con.execute(
                f"""
                SELECT *
                FROM school_merger_official_executions
                WHERE school_year_id=2
                  AND plan_id IN ({pm})
                ORDER BY id
                """,
                list(
                    last5_plan_map.values()
                ),
            ).fetchall()
        ]


    official_errors = []


    by_plan = {
        str(
            x.get(
                "plan_id"
            )
            or ""
        ):
            x
        for x in official_rows
    }


    for op, pid in (
        last5_plan_map.items()
    ):

        row = by_plan.get(pid)

        expected_item = pure_map[
            op
        ]

        if row is None:

            official_errors.append({
                "operation_id":
                    op,

                "error":
                    "MISSING_OFFICIAL_EXECUTION",
            })

            continue


        actual_src = parse_ids(
            row.get(
                "source_school_ids_json"
            )
        )

        actual_tgt = int_id(
            row.get(
                "target_school_id"
            )
        )


        if (
            actual_src
            != expected_item[
                "source_ids"
            ]
            or actual_tgt
            != expected_item[
                "target_id"
            ]
        ):
            official_errors.append({
                "operation_id":
                    op,

                "expected_source":
                    expected_item[
                        "source_ids"
                    ],

                "actual_source":
                    actual_src,

                "expected_target":
                    expected_item[
                        "target_id"
                    ],

                "actual_target":
                    actual_tgt,
            })


    print()
    print("=" * 128)
    print("16. 5 OFFICIAL EXECUTIONS CUOI")
    print("=" * 128)

    print(
        "expected plans =",
        len(
            last5_plan_map
        ),
    )

    print(
        "execution rows =",
        len(
            official_rows
        ),
    )

    print(
        "errors         =",
        len(
            official_errors
        ),
    )


    if (
        len(last5_plan_map)
        != 5
        or len(official_rows)
        != 5
        or official_errors
    ):
        fail(
            "5 official executions cuoi "
            "khong exact."
        )


    # ========================================================
    # 17. CROSS FINAL TARGET STAFF
    # ========================================================

    cross_target_duplicates = []


    if final_targets:

        tm = marks(
            len(final_targets)
        )

        cross_target_duplicates = [
            dict(x)
            for x in con.execute(
                f"""
                SELECT
                    staff_member_id,
                    COUNT(
                        DISTINCT school_id
                    ) AS school_count,
                    GROUP_CONCAT(
                        DISTINCT school_id
                    ) AS school_ids
                FROM staff_year_records
                WHERE school_year_id=2
                  AND is_active=1
                  AND staff_member_id IS NOT NULL
                  AND school_id IN ({tm})
                GROUP BY staff_member_id
                HAVING COUNT(
                    DISTINCT school_id
                ) > 1
                ORDER BY staff_member_id
                """,
                sorted(
                    final_targets
                ),
            ).fetchall()
        ]


    print()
    print("=" * 128)
    print("17. CROSS-TARGET STAFF")
    print("=" * 128)

    print(
        "duplicate identities =",
        len(
            cross_target_duplicates
        ),
    )


    if cross_target_duplicates:
        warn(
            "Co staff identity active tai "
            "nhieu final target; can xem "
            "truong hop kiem nhiem."
        )


finally:

    con.close()
    old.close()


# ============================================================
# 18. SPECIAL CASES
# ============================================================

print()
print("=" * 128)
print("18. 3 PHUONG AN DAC THU CHUA AUDIT CHUYEN DIEM/LOP")
print("=" * 128)


for item in sorted(
    special_ops,
    key=lambda x:
        str(
            x.get(
                "operation_id"
            )
            or ""
        ),
):

    print(
        item.get(
            "operation_id"
        ),
        "|",
        item.get(
            "display_title"
        )
        or item.get(
            "official_plan"
        )
        or "",
    )

    print(
        "  relation =",
        item.get(
            "relation_type"
        ),
    )


print()
print(
    "3 operation dac thu KHONG tinh vao "
    "189 sap nhap toan truong."
)


# ============================================================
# 19. IMMUTABILITY
# ============================================================

print()
print("=" * 128)
print("19. FILE IMMUTABILITY")
print("=" * 128)


after_hash = {}


for key, path in paths.items():

    got = sha256(path)

    after_hash[key] = got

    print(
        key,
        ":",
        before_hash[key],
        "->",
        got,
    )


if after_hash != before_hash:
    fail(
        "Co file that bi thay doi "
        "trong luc audit."
    )


# ============================================================
# 20. DETAILS
# ============================================================

print()
print("=" * 128)
print("20. TONG HOP")
print("=" * 128)

print(
    "FAILURES =",
    len(FAILURES),
)

for i, message in enumerate(
    FAILURES,
    start=1,
):

    print(
        f"  FAIL {i}: {message}"
    )


print(
    "WARNINGS =",
    len(WARNINGS),
)

for i, message in enumerate(
    WARNINGS,
    start=1,
):

    print(
        f"  WARN {i}: {message}"
    )


DETAILS = [
    (
        "SHAPE ERROR",
        shape_errors,
    ),

    (
        "SOURCE AUDIT ERROR",
        source_audit_errors,
    ),

    (
        "DUPLICATE SOURCE",
        duplicate_source,
    ),

    (
        "CHAIN ERROR",
        chain_errors,
    ),

    (
        "SOURCE STATE ERROR",
        source_state_errors,
    ),

    (
        "FINAL TARGET ERROR",
        final_target_errors,
    ),

    (
        "MISSING LOG",
        missing_logs,
    ),

    (
        "DUPLICATE LOG",
        duplicate_logs,
    ),

    (
        "USER MOVE ERROR",
        user_move_errors,
    ),

    (
        "STAFF UNION ERROR",
        staff_errors,
    ),

    (
        "STAFF DUPLICATE",
        duplicate_staff_errors,
    ),

    (
        "PAST MISMATCH",
        past_mismatch,
    ),

    (
        "KEEP MAPPING ERROR",
        keep_mapping_errors,
    ),

    (
        "KEEP EXACT MISMATCH",
        keep_exact_mismatch,
    ),

    (
        "OFFICIAL EXEC ERROR",
        official_errors,
    ),

    (
        "CROSS TARGET DUP",
        cross_target_duplicates,
    ),
]


for title, items in DETAILS:

    if not items:
        continue

    print()
    print(
        "---",
        title,
        "| total=",
        len(items),
        "---",
    )

    for item in items[:20]:

        print(
            json.dumps(
                item,
                ensure_ascii=False,
                default=str,
            )
        )


# ============================================================
# FINAL
# ============================================================

print()
print("=" * 128)


if FAILURES:

    print(
        "KIEM TOAN CHUAN CAP MN V2: FAIL"
    )

    print(
        "KHONG CHUYEN SANG CAP HOC TIEP THEO."
    )

    print(
        "KHONG ROLLBACK / KHONG CHAY LAI SAP NHAP."
    )

else:

    print(
        "KIEM TOAN CHUAN CAP MN V2: PASS"
    )

    print()
    print(
        "189 pure operations       : PASS"
    )

    print(
        "52 KEEP                   : PASS"
    )

    print(
        "Source schools inactive   : PASS"
    )

    print(
        "Final targets active      : PASS"
    )

    print(
        "CURRENT/FUTURE residual   : 0"
    )

    print(
        "Active users at source    : 0"
    )

    print(
        "User movement             : PASS"
    )

    print(
        "Staff union               : PASS"
    )

    print(
        "PAST vs V13.6             : EXACT"
    )

    print(
        "KEEP vs V13.6             : EXACT"
    )

    print(
        "Batch MN                  : PASS"
    )

    print(
        "5 official executions     : PASS"
    )

    print(
        "Mầm non Lượng Minh        : GIU NGUYEN"
    )

    print(
        "DB integrity/FK           : PASS"
    )

    print(
        "Database/Source/Registry  : KHONG THAY DOI"
    )

    print()
    print(
        "MN_STANDARD_POST_MERGER_AUDIT_V2=PASS"
    )

    print(
        "MN_SPECIAL_CASES_PENDING=3"
    )


print("=" * 128)
