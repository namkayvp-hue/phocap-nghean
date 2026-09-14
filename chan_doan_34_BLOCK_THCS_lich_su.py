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

HISTORY_PLAN = (
    ROOT
    / "data"
    / "school_merger_approved_plans.json"
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

EXPECTED_HISTORY_PLANS = 422
EXPECTED_HISTORY_SOURCES = 495

YEAR_ID = 2
MOVE_YEARS = [2, 8]

NGHI_HUONG_CODE = "40413505"


def sha256(path: Path) -> str:
    h = hashlib.sha256()

    with path.open("rb") as f:
        for block in iter(
            lambda: f.read(1024 * 1024),
            b"",
        ):
            h.update(block)

    return h.hexdigest()


def qident(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def marks(n: int) -> str:
    return ",".join(
        "?"
        for _ in range(n)
    )


def connect_ro():
    con = sqlite3.connect(
        DB.resolve().as_uri()
        + "?mode=ro",
        uri=True,
        timeout=90,
    )

    con.row_factory = sqlite3.Row

    con.execute(
        "PRAGMA query_only=ON"
    )

    con.execute(
        "PRAGMA foreign_keys=ON"
    )

    return con


def table_names(con):
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


def one_school_id(item):
    if not isinstance(item, dict):
        return None

    try:
        sid = int(
            item.get("id")
            or 0
        )

        return sid if sid else None

    except Exception:
        return None


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
            raw = []

    if not isinstance(
        raw,
        (list, tuple),
    ):
        raw = [raw]

    result = []

    for value in raw:

        try:
            sid = int(value)

            if sid:
                result.append(sid)

        except Exception:
            pass

    return sorted(
        set(result)
    )


def school_row(con, school_id):

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
        (school_id,),
    ).fetchone()

    return (
        dict(row)
        if row
        else None
    )


def current_future_residual(
    con,
    school_ids_value,
):

    ids = sorted(
        set(
            int(x)
            for x in school_ids_value
            if int(x)
        )
    )

    if not ids:
        return {}

    result = {}

    sm = marks(len(ids))
    ym = marks(len(MOVE_YEARS))

    for table in table_names(con):

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
                    *ids,
                    *MOVE_YEARS,
                ],
            ).fetchone()[0]
            or 0
        )

        if n:
            result[table] = n

    return result


def active_users_at(
    con,
    school_ids_value,
):

    ids = sorted(
        set(
            int(x)
            for x in school_ids_value
            if int(x)
        )
    )

    if not ids:
        return 0

    return int(
        con.execute(
            f"""
            SELECT COUNT(*)
            FROM users
            WHERE school_id IN (
                {marks(len(ids))}
            )
              AND is_active=1
            """,
            ids,
        ).fetchone()[0]
        or 0
    )


def relevant_history_plan(plan):

    if str(
        plan.get("status")
        or ""
    ).upper() != "COMPLETED":
        return False

    pid = str(
        plan.get("id")
        or ""
    )

    doc = str(
        plan.get("document_code")
        or ""
    )

    return (
        pid.startswith("QD3805-")
        or "3805" in doc
        or doc
        == "NGUON-SAP-NHAP-TOAN-TINH"
        or pid.startswith(
            "V13.8-QUANG-DONG-"
        )
        or pid.startswith(
            "V13.10-"
        )
    )


print("=" * 132)
print(
    "CHAN DOAN 34 BLOCK THCS DOI CHIEU LICH SU SAP NHAP TOAN TINH"
)
print(
    "CHI DOC - KHONG SUA DATABASE / SERVICE / REGISTRY"
)
print("=" * 132)


# ============================================================
# 1. HASH GATE
# ============================================================

print()
print("=" * 132)
print("1. HASH GATE")
print("=" * 132)


before = {
    "db":
        sha256(DB),

    "service":
        sha256(SERVICE),

    "lock":
        sha256(LOCK),

    "history":
        sha256(HISTORY_PLAN),
}


for key, value in before.items():
    print(
        f"{key:12s} = {value}"
    )


if before["db"] != EXPECTED_DB_SHA:
    raise RuntimeError(
        "DUNG: DB khong dung snapshot "
        "sau khi hoan tat MN."
    )


if (
    before["service"]
    != EXPECTED_SERVICE_SHA
):
    raise RuntimeError(
        "DUNG: service da thay doi."
    )


if before["lock"] != EXPECTED_LOCK_SHA:
    raise RuntimeError(
        "DUNG: level lock da thay doi."
    )


# ============================================================
# 2. LOAD HISTORY 422
# ============================================================

payload = json.loads(
    HISTORY_PLAN.read_text(
        encoding="utf-8-sig"
    )
)

all_plans = [
    dict(x)
    for x in (
        payload.get("plans")
        or []
    )
    if isinstance(x, dict)
]

history_plans = [
    x
    for x in all_plans
    if relevant_history_plan(x)
]


history_map = {}

history_plan_by_source = {}

conflicts = []


for plan in history_plans:

    target = int(
        plan.get(
            "target_school_id"
        )
        or 0
    )

    for source in (
        plan.get(
            "source_school_ids"
        )
        or []
    ):

        sid = int(source)

        if (
            sid in history_map
            and history_map[sid]
            != target
        ):

            conflicts.append({
                "school_id":
                    sid,

                "target_1":
                    history_map[sid],

                "target_2":
                    target,
            })

        history_map[
            sid
        ] = target

        history_plan_by_source[
            sid
        ] = {
            "id":
                plan.get("id"),

            "document_code":
                plan.get(
                    "document_code"
                ),

            "target_school_id":
                target,

            "source_school_ids":
                parse_ids(
                    plan.get(
                        "source_school_ids"
                    )
                ),
        }


print()
print("=" * 132)
print("2. LICH SU DA THUC HIEN")
print("=" * 132)

print(
    "completed plans =",
    len(history_plans),
)

print(
    "unique sources  =",
    len(history_map),
)

print(
    "mapping conflict=",
    len(conflicts),
)


if conflicts:
    raise RuntimeError(
        "DUNG: historical source map co xung dot."
    )


if (
    len(history_plans)
    != EXPECTED_HISTORY_PLANS
):
    raise RuntimeError(
        "DUNG: lich su khong con dung "
        "422 completed plans."
    )


if (
    len(history_map)
    != EXPECTED_HISTORY_SOURCES
):
    raise RuntimeError(
        "DUNG: lich su khong con dung "
        "495 unique source schools."
    )


def final_history_target(
    school_id,
):

    current = int(
        school_id
    )

    seen = set()

    while current in history_map:

        if current in seen:
            raise RuntimeError(
                "Historical chain cycle "
                f"tai school_id={current}"
            )

        seen.add(current)

        current = int(
            history_map[
                current
            ]
        )

    return current


# ============================================================
# 3. CURRENT THCS STATE
# ============================================================

from app.services import (
    school_merger_level_batch_service
    as svc
)


rows, counts, candidates, meta = (
    svc._state_rows(
        YEAR_ID,
        "THCS",
    )
)


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
print("3. CURRENT THCS")
print("=" * 132)

print(
    "counts      =",
    counts,
)

print(
    "BLOCK rows  =",
    len(block_rows),
)


if len(block_rows) != 34:
    raise RuntimeError(
        "DUNG: so BLOCK THCS "
        "khong con bang 34."
    )


con = connect_ro()


try:

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


    print(
        "integrity   =",
        integrity,
    )

    print(
        "FK          =",
        fk,
    )


    if (
        integrity.lower()
        != "ok"
        or fk != 0
    ):
        raise RuntimeError(
            "DUNG: database integrity/FK FAIL."
        )


    # ========================================================
    # 4. ANALYSE 34 BLOCK
    # ========================================================

    results = []

    category = Counter()


    for row in block_rows:

        op = str(
            row.get(
                "qd3805_operation_id"
            )
            or ""
        )

        pid = str(
            row.get("id")
            or ""
        )

        members = school_ids(
            row.get(
                "member_schools"
            )
        )

        direct_sources = school_ids(
            row.get(
                "source_schools"
            )
        )

        direct_target = one_school_id(
            row.get(
                "target_school"
            )
        )


        member_final = {}

        for sid in members:

            member_final[
                sid
            ] = (
                final_history_target(
                    sid
                )
            )


        final_set = set(
            member_final.values()
        )


        direct_exact = False

        direct_chain_exact = False

        expected_final = None


        if (
            direct_sources
            and direct_target
        ):

            direct_exact = all(
                history_map.get(sid)
                == direct_target
                for sid
                in direct_sources
            )


            expected_final = (
                final_history_target(
                    direct_target
                )
            )


            direct_chain_exact = all(
                final_history_target(
                    sid
                )
                == expected_final
                for sid
                in direct_sources
            )


        member_chain_converged = (
            bool(members)
            and len(final_set) == 1
            and any(
                sid in history_map
                for sid in members
            )
        )


        if member_chain_converged:
            final_target = next(
                iter(final_set)
            )

        elif expected_final:
            final_target = (
                expected_final
            )

        else:
            final_target = None


        absorbed_ids = sorted(
            sid
            for sid in members
            if (
                sid in history_map
                and final_history_target(
                    sid
                )
                != sid
            )
        )


        # Nếu member_schools thiếu một số source,
        # vẫn đưa source trực tiếp vào kiểm tra.
        for sid in direct_sources:

            if (
                sid in history_map
                and final_history_target(
                    sid
                )
                != sid
                and sid
                not in absorbed_ids
            ):
                absorbed_ids.append(
                    sid
                )


        absorbed_ids = sorted(
            set(absorbed_ids)
        )


        inactive_errors = []

        for sid in absorbed_ids:

            s = school_row(
                con,
                sid,
            )

            if (
                s is None
                or bool(
                    s["is_active"]
                )
            ):

                inactive_errors.append({
                    "school_id":
                        sid,

                    "school":
                        s,
                })


        final_school = (
            school_row(
                con,
                final_target,
            )
            if final_target
            else None
        )


        final_active = (
            final_school is not None
            and bool(
                final_school[
                    "is_active"
                ]
            )
        )


        residual = (
            current_future_residual(
                con,
                absorbed_ids,
            )
        )

        active_users = (
            active_users_at(
                con,
                absorbed_ids,
            )
        )


        audit = (
            row.get(
                "source_audit"
            )
            or {}
        )


        history_covered = (
            direct_exact
            or direct_chain_exact
            or member_chain_converged
        )


        state_closed = (
            bool(
                absorbed_ids
            )
            and not inactive_errors
            and final_active
            and not residual
            and active_users == 0
        )


        if (
            history_covered
            and state_closed
        ):

            classification = (
                "PRECOMPLETED_STRONG"
            )

        elif history_covered:

            classification = (
                "HISTORY_MATCH_STATE_NOT_CLOSED"
            )

        elif (
            not direct_sources
            or direct_target is None
        ):

            classification = (
                "UNMAPPED_NEEDS_RESOLUTION"
            )

        else:

            classification = (
                "NO_HISTORY_MATCH"
            )


        category[
            classification
        ] += 1


        history_records = []

        for sid in sorted(
            set(
                members
                + direct_sources
            )
        ):

            if sid not in history_map:
                continue

            history_records.append({
                "source_school_id":
                    sid,

                "immediate_target":
                    history_map[
                        sid
                    ],

                "final_target":
                    final_history_target(
                        sid
                    ),

                "history_plan":
                    history_plan_by_source.get(
                        sid
                    ),
            })


        results.append({
            "classification":
                classification,

            "operation_id":
                op,

            "plan_id":
                pid,

            "commune":
                row.get(
                    "commune_name"
                ),

            "execution_status":
                row.get(
                    "execution_status"
                ),

            "match_status":
                row.get(
                    "match_status"
                ),

            "member_ids":
                members,

            "direct_source_ids":
                direct_sources,

            "direct_target_id":
                direct_target,

            "direct_history_exact":
                direct_exact,

            "direct_chain_exact":
                direct_chain_exact,

            "member_chain_converged":
                member_chain_converged,

            "member_final_targets":
                member_final,

            "absorbed_ids":
                absorbed_ids,

            "final_target_id":
                final_target,

            "final_target":
                final_school,

            "inactive_errors":
                inactive_errors,

            "current_future_residual":
                residual,

            "active_users_at_absorbed":
                active_users,

            "source_audit_status":
                audit.get(
                    "status"
                ),

            "source_audit_pass":
                audit.get(
                    "pass"
                ),

            "blockers":
                row.get(
                    "blockers"
                )
                or audit.get(
                    "blockers"
                )
                or [],

            "history_records":
                history_records,
        })


    print()
    print("=" * 132)
    print("4. CHI TIET 34 BLOCK")
    print("=" * 132)


    for item in results:

        print(
            json.dumps(
                item,
                ensure_ascii=False,
                default=str,
            )
        )


    print()
    print("=" * 132)
    print("5. TONG HOP PHAN LOAI")
    print("=" * 132)

    print(
        json.dumps(
            dict(category),
            ensure_ascii=False,
        )
    )


    print()
    print(
        "PRECOMPLETED_STRONG:"
    )

    for item in results:

        if (
            item[
                "classification"
            ]
            == "PRECOMPLETED_STRONG"
        ):

            print(
                item[
                    "operation_id"
                ],
                "|",
                item[
                    "plan_id"
                ],
                "|",
                item[
                    "commune"
                ],
                "| src=",
                item[
                    "direct_source_ids"
                ],
                "| target=",
                item[
                    "direct_target_id"
                ],
                "| final=",
                item[
                    "final_target_id"
                ],
            )


    print()
    print(
        "CON LAI CAN XU LY:"
    )

    for item in results:

        if (
            item[
                "classification"
            ]
            != "PRECOMPLETED_STRONG"
        ):

            print(
                json.dumps(
                    item,
                    ensure_ascii=False,
                    default=str,
                )
            )


    # ========================================================
    # 6. NGHI HUONG - STT 110
    # ========================================================

    print()
    print("=" * 132)
    print(
        "6. ORPHAN STT 110 - THCS NGHI HUONG"
    )
    print("=" * 132)


    nghi_huong = con.execute(
        """
        SELECT
            id,
            code,
            name,
            commune_id,
            is_active
        FROM schools
        WHERE TRIM(code)=?
        ORDER BY id
        """,
        (NGHI_HUONG_CODE,),
    ).fetchall()


    if not nghi_huong:

        print(
            "KHONG TIM THAY MA",
            NGHI_HUONG_CODE,
        )

    else:

        for raw in nghi_huong:

            s = dict(raw)

            sid = int(
                s["id"]
            )


            print(
                "SCHOOL =",
                json.dumps(
                    s,
                    ensure_ascii=False,
                ),
            )


            print(
                "historical_as_source =",
                (
                    history_plan_by_source.get(
                        sid
                    )
                ),
            )


            print(
                "historical_immediate_target =",
                history_map.get(
                    sid
                ),
            )


            print(
                "historical_final_target =",
                final_history_target(
                    sid
                ),
            )


            target_mentions = [
                {
                    "id":
                        p.get("id"),

                    "document_code":
                        p.get(
                            "document_code"
                        ),

                    "source_school_ids":
                        p.get(
                            "source_school_ids"
                        ),

                    "target_school_id":
                        p.get(
                            "target_school_id"
                        ),
                }
                for p in history_plans
                if int(
                    p.get(
                        "target_school_id"
                    )
                    or 0
                )
                == sid
            ]


            print(
                "historical_as_target =",
                json.dumps(
                    target_mentions,
                    ensure_ascii=False,
                    default=str,
                ),
            )


            print(
                "CURRENT/FUTURE rows =",
                current_future_residual(
                    con,
                    [sid],
                ),
            )


            print(
                "active users =",
                active_users_at(
                    con,
                    [sid],
                ),
            )


            staff = {}

            for year_id in (
                1,
                2,
            ):

                staff[
                    year_id
                ] = int(
                    con.execute(
                        """
                        SELECT COUNT(
                            DISTINCT staff_member_id
                        )
                        FROM staff_year_records
                        WHERE school_id=?
                          AND school_year_id=?
                          AND is_active=1
                          AND staff_member_id
                              IS NOT NULL
                        """,
                        (
                            sid,
                            year_id,
                        ),
                    ).fetchone()[0]
                    or 0
                )


            print(
                "active staff 2025-26 / 2026-27 =",
                staff,
            )


    print()
    print(
        "QD3805_ROW_STATUS = "
        "CHUA_CO_PHUONG_AN_RO_RANG"
    )

    print(
        "KHONG TU DONG COI LA GIU NGUYEN "
        "VA KHONG TU GHÉP SANG OP-0060/0061."
    )


finally:
    con.close()


# ============================================================
# 7. IMMUTABILITY
# ============================================================

print()
print("=" * 132)
print("7. FILE IMMUTABILITY")
print("=" * 132)


after = {
    "db":
        sha256(DB),

    "service":
        sha256(SERVICE),

    "lock":
        sha256(LOCK),

    "history":
        sha256(HISTORY_PLAN),
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
        "DUNG: co file that bi thay doi "
        "trong luc chan doan."
    )


print()
print("=" * 132)
print("CHAN DOAN 34 BLOCK THCS: HOAN TAT")
print("=" * 132)

print(
    "KHONG SUA DATABASE."
)

print(
    "KHONG SUA SERVICE / REGISTRY."
)

print(
    "KHONG CHAY SAP NHAP THCS."
)

print(
    "BUOC TIEP THEO: "
    "KHOA CAC PRECOMPLETED THAT, "
    "XU LY CAC BLOCK CON LAI, "
    "ROI MO DRY-RUN THCS."
)

print("=" * 132)
