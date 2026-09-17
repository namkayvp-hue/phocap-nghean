from __future__ import annotations

import hashlib
import inspect
import json
import sqlite3
import sys
from collections import Counter
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

EXPECTED_RESOLUTION_SHA = (
    "bf991e2ebb10a5952f07ca81caa24ead"
    "e98bca5f9e44beded54ae17c68fc373a"
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

CURRENT_YEAR_ID = 2
FUTURE_YEAR_ID = 8

MOVE_YEAR_IDS = [
    CURRENT_YEAR_ID,
    FUTURE_YEAR_ID,
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()

    with path.open("rb") as f:
        while True:
            block = f.read(
                1024 * 1024
            )

            if not block:
                break

            h.update(block)

    return h.hexdigest()


def qident(name: str) -> str:
    return (
        '"'
        + str(name).replace(
            '"',
            '""',
        )
        + '"'
    )


def table_exists(
    con: sqlite3.Connection,
    table: str,
) -> bool:

    return (
        con.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type='table'
              AND name=?
            """,
            (table,),
        ).fetchone()
        is not None
    )


def table_columns(
    con: sqlite3.Connection,
    table: str,
) -> list[str]:

    return [
        str(x["name"])
        for x in con.execute(
            f"PRAGMA table_info({qident(table)})"
        ).fetchall()
    ]


def direct_year_tables(
    con: sqlite3.Connection,
) -> list[str]:

    result = []

    rows = con.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type='table'
          AND name NOT LIKE 'sqlite_%'
        ORDER BY name
        """
    ).fetchall()

    for row in rows:
        table = str(
            row["name"]
        )

        cols = set(
            table_columns(
                con,
                table,
            )
        )

        if {
            "school_id",
            "school_year_id",
        }.issubset(cols):
            result.append(
                table
            )

    return result


def count_direct_residual(
    con: sqlite3.Connection,
    *,
    tables: list[str],
    source_ids: list[int],
    year_ids: list[int],
) -> dict[str, int]:

    if not source_ids:
        return {}

    src_marks = ",".join(
        "?"
        for _ in source_ids
    )

    year_marks = ",".join(
        "?"
        for _ in year_ids
    )

    out = {}

    for table in tables:
        n = int(
            con.execute(
                f"""
                SELECT COUNT(*)
                FROM {qident(table)}
                WHERE school_id IN ({src_marks})
                  AND school_year_id IN ({year_marks})
                """,
                [
                    *source_ids,
                    *year_ids,
                ],
            ).fetchone()[0]
            or 0
        )

        if n:
            out[table] = n

    return out


def snapshot_past(
    con: sqlite3.Connection,
    *,
    tables: list[str],
    source_ids: list[int],
    past_year_ids: list[int],
) -> dict[str, dict]:

    result = {}

    if not source_ids:
        return result

    src_marks = ",".join(
        "?"
        for _ in source_ids
    )

    year_marks = ",".join(
        "?"
        for _ in past_year_ids
    )

    for table in tables:

        rows = con.execute(
            f"""
            SELECT *
            FROM {qident(table)}
            WHERE school_id IN ({src_marks})
              AND school_year_id IN ({year_marks})
            """,
            [
                *source_ids,
                *past_year_ids,
            ],
        ).fetchall()

        serialized = []

        for row in rows:
            item = {
                key: row[key]
                for key in row.keys()
            }

            serialized.append(
                json.dumps(
                    item,
                    ensure_ascii=False,
                    sort_keys=True,
                    default=str,
                )
            )

        serialized.sort()

        h = hashlib.sha256()

        for item in serialized:
            h.update(
                item.encode("utf-8")
            )
            h.update(b"\n")

        result[table] = {
            "rows":
                len(serialized),

            "sha256":
                h.hexdigest(),
        }

    return result


def active_staff_count(
    con: sqlite3.Connection,
    school_id: int,
    year_id: int,
) -> int:

    if not table_exists(
        con,
        "staff_year_records",
    ):
        return 0

    return int(
        con.execute(
            """
            SELECT COUNT(*)
            FROM staff_year_records
            WHERE school_id=?
              AND school_year_id=?
              AND is_active=1
            """,
            (
                school_id,
                year_id,
            ),
        ).fetchone()[0]
        or 0
    )


def staff_structure(
    con: sqlite3.Connection,
    school_id: int,
    year_id: int,
) -> dict[str, int]:

    if not table_exists(
        con,
        "staff_year_records",
    ):
        return {}

    rows = con.execute(
        """
        SELECT
            COALESCE(position_group,'') AS position_group,
            COUNT(*) AS n
        FROM staff_year_records
        WHERE school_id=?
          AND school_year_id=?
          AND is_active=1
        GROUP BY
            COALESCE(position_group,'')
        ORDER BY
            COALESCE(position_group,'')
        """,
        (
            school_id,
            year_id,
        ),
    ).fetchall()

    return {
        str(x["position_group"]):
            int(x["n"] or 0)
        for x in rows
    }


def staff_duplicate_ids(
    con: sqlite3.Connection,
    school_id: int,
    year_id: int,
) -> list[dict]:

    if not table_exists(
        con,
        "staff_year_records",
    ):
        return []

    rows = con.execute(
        """
        SELECT
            staff_member_id,
            COUNT(*) AS n
        FROM staff_year_records
        WHERE school_id=?
          AND school_year_id=?
          AND is_active=1
        GROUP BY staff_member_id
        HAVING COUNT(*) > 1
        ORDER BY staff_member_id
        """,
        (
            school_id,
            year_id,
        ),
    ).fetchall()

    return [
        {
            "staff_member_id":
                int(x["staff_member_id"]),

            "count":
                int(x["n"]),
        }
        for x in rows
    ]


def school_state(
    con: sqlite3.Connection,
    ids: list[int],
) -> list[dict]:

    if not ids:
        return []

    marks = ",".join(
        "?"
        for _ in ids
    )

    rows = con.execute(
        f"""
        SELECT
            id,
            code,
            name,
            is_active
        FROM schools
        WHERE id IN ({marks})
        ORDER BY id
        """,
        ids,
    ).fetchall()

    return [
        dict(x)
        for x in rows
    ]


def active_users_at_sources(
    con: sqlite3.Connection,
    source_ids: list[int],
) -> int:

    if (
        not source_ids
        or not table_exists(
            con,
            "users",
        )
    ):
        return 0

    marks = ",".join(
        "?"
        for _ in source_ids
    )

    return int(
        con.execute(
            f"""
            SELECT COUNT(*)
            FROM users
            WHERE school_id IN ({marks})
              AND is_active=1
            """,
            source_ids,
        ).fetchone()[0]
        or 0
    )


# ============================================================
# 0. HASH GATE
# ============================================================

before_hash = {
    "db":
        sha256(DB),

    "service":
        sha256(SERVICE),

    "resolution":
        sha256(RESOLUTION),

    "roster":
        sha256(ROSTER),
}


print("=" * 126)
print("DRY-RUN TONG CUOI 5 PHUONG AN MAM NON READY")
print("MO PHONG TUAN TU TREN 1 BAN SAO SQLITE TRONG RAM")
print("KHONG GHI DB THAT - KHONG SUA SOURCE - KHONG SUA REGISTRY")
print("=" * 126)

for key, value in (
    before_hash.items()
):
    print(
        f"{key:10s} = {value}"
    )


expected_hash = {
    "db":
        EXPECTED_DB_SHA,

    "service":
        EXPECTED_SERVICE_SHA,

    "resolution":
        EXPECTED_RESOLUTION_SHA,

    "roster":
        EXPECTED_ROSTER_SHA,
}


for key in expected_hash:
    if (
        before_hash[key]
        != expected_hash[key]
    ):
        raise RuntimeError(
            "DUNG: "
            + key
            + " khong dung nen da khoa."
        )


# ============================================================
# 1. IMPORT SERVICE
# ============================================================

from app.services.school_merger_level_batch_service import (
    build_level_batch_preview,
)

from app.services.school_merger_preview_service import (
    build_official_plan_impact_preview,
)

from app.services import (
    school_merger_service
    as merger_engine
)


# ============================================================
# 2. BATCH PREVIEW 2 LAN
# ============================================================

batch1 = build_level_batch_preview(
    school_year_id=2,
    level_code="MN",
)

batch2 = build_level_batch_preview(
    school_year_id=2,
    level_code="MN",
)


print()
print("=" * 126)
print("1. BATCH GATE")
print("=" * 126)

print(
    "counts                =",
    batch1.get("counts"),
)

print(
    "candidate_count       =",
    batch1.get(
        "candidate_count"
    ),
)

print(
    "effective_block_count =",
    batch1.get(
        "effective_block_count"
    ),
)

print(
    "ready_for_execution   =",
    batch1.get(
        "ready_for_execution"
    ),
)

print(
    "overlap_items         =",
    batch1.get(
        "overlap_items"
    ),
)

print(
    "extra_blockers        =",
    batch1.get(
        "extra_blockers"
    ),
)

print(
    "batch_fingerprint     =",
    batch1.get(
        "batch_fingerprint"
    ),
)

print(
    "fingerprint stable    =",
    (
        batch1.get(
            "batch_fingerprint"
        )
        == batch2.get(
            "batch_fingerprint"
        )
    ),
)


if batch1.get("counts") != {
    "KEEP": 51,
    "DONE": 184,
    "READY": 5,
    "BLOCK": 0,
}:
    raise RuntimeError(
        "DUNG: KPI batch khong dung."
    )


if (
    batch1.get(
        "candidate_count"
    )
    != 5
):
    raise RuntimeError(
        "DUNG: candidate_count != 5."
    )


if (
    batch1.get(
        "effective_block_count"
    )
    != 0
):
    raise RuntimeError(
        "DUNG: con blocker."
    )


if (
    batch1.get(
        "ready_for_execution"
    )
    is not True
):
    raise RuntimeError(
        "DUNG: batch chua san sang."
    )


if (
    batch1.get(
        "overlap_items"
    )
    or []
):
    raise RuntimeError(
        "DUNG: batch co overlap."
    )


if (
    batch1.get(
        "extra_blockers"
    )
    or []
):
    raise RuntimeError(
        "DUNG: batch con extra blocker."
    )


if (
    not batch1.get(
        "batch_fingerprint"
    )
):
    raise RuntimeError(
        "DUNG: thieu batch_fingerprint."
    )


if (
    batch1.get(
        "batch_fingerprint"
    )
    != batch2.get(
        "batch_fingerprint"
    )
):
    raise RuntimeError(
        "DUNG: batch fingerprint "
        "khong on dinh."
    )


# ============================================================
# 3. EXACT 5 CANDIDATES
# ============================================================

candidates = [
    dict(x)
    for x in (
        batch1.get(
            "candidates"
        )
        or []
    )
    if isinstance(x, dict)
]


candidate_ops = {
    str(
        x.get(
            "qd3805_operation_id"
        )
        or ""
    )
    for x in candidates
}


print()
print("=" * 126)
print("2. DANH SACH 5 READY")
print("=" * 126)

for item in candidates:
    print(
        item.get(
            "qd3805_operation_id"
        ),
        "|",
        item.get(
            "plan_id"
        ),
        "|",
        item.get(
            "commune"
        ),
        "|",
        item.get(
            "title"
        ),
    )


if len(candidates) != 5:
    raise RuntimeError(
        "DUNG: candidates khong dung 5."
    )


if candidate_ops != READY_EXPECTED:
    raise RuntimeError(
        "DUNG: danh sach READY "
        "khong dung 5 operation da khoa."
    )


# ============================================================
# 4. DETAIL PREVIEW TUNG PHUONG AN
# ============================================================

details = []

all_plan_school_ids = []


print()
print("=" * 126)
print("3. KIEM TRA CHI TIET TUNG PHUONG AN")
print("=" * 126)


for index, candidate in enumerate(
    candidates,
    start=1,
):

    pid = str(
        candidate.get(
            "plan_id"
        )
        or ""
    )

    op = str(
        candidate.get(
            "qd3805_operation_id"
        )
        or ""
    )

    if not pid:
        raise RuntimeError(
            f"{op}: thieu plan_id."
        )

    p1 = (
        build_official_plan_impact_preview(
            pid
        )
    )

    p2 = (
        build_official_plan_impact_preview(
            pid
        )
    )

    sources = [
        dict(x)
        for x in (
            p1.get(
                "source_schools"
            )
            or []
        )
    ]

    target = dict(
        p1.get(
            "target_school"
        )
        or {}
    )

    source_ids = [
        int(x["id"])
        for x in sources
        if x.get("id") is not None
    ]

    target_id = int(
        target.get("id")
        or 0
    )

    if (
        not source_ids
        or target_id <= 0
    ):
        raise RuntimeError(
            f"{op}: thieu source/target."
        )

    if target_id in source_ids:
        raise RuntimeError(
            f"{op}: target trung source."
        )

    source_audit = dict(
        p1.get(
            "source_audit"
        )
        or {}
    )

    school_checks = [
        dict(x)
        for x in (
            source_audit.get(
                "school_checks"
            )
            or []
        )
        if isinstance(
            x,
            dict,
        )
    ]

    false_school_checks = [
        x
        for x in school_checks
        if str(
            x.get("status")
            or ""
        ).upper()
        != "PASS"
    ]

    blockers = [
        str(x)
        for x in (
            p1.get("blockers")
            or []
        )
        if str(x).strip()
    ]

    simulation_result = dict(
        p1.get(
            "simulation_result"
        )
        or {}
    )

    summary = dict(
        p1.get("summary")
        or {}
    )

    state_summary = dict(
        p1.get(
            "impact_state_summary"
        )
        or {}
    )

    detail_checks = {
        "blockers_empty":
            not blockers,

        "simulation_ok":
            bool(
                p1.get(
                    "simulation_ok"
                )
            ),

        "safe":
            bool(
                p1.get(
                    "safe_for_future_execution"
                )
            ),

        "v41_state":
            bool(
                p1.get(
                    "v41_state_check_ok"
                )
            ),

        "v43_source":
            bool(
                p1.get(
                    "v43_source_check_ok"
                )
            ),

        "not_completed":
            not bool(
                p1.get(
                    "completed_operation"
                )
            ),

        "source_audit_pass":
            bool(
                source_audit.get(
                    "pass"
                )
            ),

        "school_checks_pass":
            (
                bool(school_checks)
                and not false_school_checks
            ),

        "impact_fp":
            bool(
                p1.get(
                    "impact_state_fingerprint"
                )
            ),

        "impact_fp_stable":
            (
                p1.get(
                    "impact_state_fingerprint"
                )
                == p2.get(
                    "impact_state_fingerprint"
                )
            ),

        "preview_fp_stable":
            (
                p1.get(
                    "fingerprint"
                )
                == p2.get(
                    "fingerprint"
                )
            ),

        "source_fp_stable":
            (
                (
                    p1.get(
                        "source_audit"
                    )
                    or {}
                ).get(
                    "fingerprint"
                )
                == (
                    p2.get(
                        "source_audit"
                    )
                    or {}
                ).get(
                    "fingerprint"
                )
            ),
    }


    print()
    print("-" * 126)

    print(
        f"[{index}/5] {op} | {pid}"
    )

    print(
        "Xã/phường:",
        candidate.get(
            "commune"
        ),
    )

    print("Nguồn:")

    for s in sources:
        print(
            "  -",
            f"id={s.get('id')}",
            f"| mã={s.get('code')}",
            f"| {s.get('name') or s.get('excel_name')}",
        )

    print(
        "Đích:",
        f"id={target_id}",
        f"| mã={target.get('code')}",
        f"| {target.get('name')}",
    )

    print()
    print(
        "Source audit:"
    )

    for check in school_checks:
        print(
            "  -",
            check.get(
                "role"
            ),
            "|",
            check.get(
                "school_name"
            ),
            "|",
            check.get(
                "school_code"
            ),
            "| PASS="
            + str(
                check.get(
                    "status"
                )
            ),
            "| eligible="
            + str(
                check.get(
                    "active_db_eligible"
                )
            ),
            "| source_active="
            + str(
                check.get(
                    "source_active_rows"
                )
            ),
        )

    print()
    print(
        "Preview:"
    )

    print(
        "  direct_move_rows         =",
        summary.get(
            "direct_move_rows"
        ),
    )

    print(
        "  historical_preserve_rows =",
        summary.get(
            "historical_preserve_rows"
        ),
    )

    print(
        "  staff_rollover_candidates=",
        summary.get(
            "staff_rollover_candidates"
        ),
    )

    print(
        "  simulation staff created =",
        simulation_result.get(
            "staff_rollover_created"
        ),
    )

    print(
        "  users moved              =",
        simulation_result.get(
            "users_moved"
        ),
    )

    print(
        "  source logins disabled   =",
        simulation_result.get(
            "source_school_logins_disabled"
        ),
    )

    print(
        "  sources deactivated      =",
        simulation_result.get(
            "sources_deactivated"
        ),
    )

    print(
        "  impact rows hashed       =",
        state_summary.get(
            "rows_hashed"
        ),
    )

    print()
    print(
        "Checks:",
        json.dumps(
            detail_checks,
            ensure_ascii=False,
        ),
    )


    if not all(
        detail_checks.values()
    ):
        raise RuntimeError(
            f"DUNG: {op} chua PASS "
            "toan bo gate chi tiet."
        )


    all_plan_school_ids.extend(
        source_ids
    )

    all_plan_school_ids.append(
        target_id
    )


    details.append({
        "index":
            index,

        "operation_id":
            op,

        "plan_id":
            pid,

        "candidate":
            candidate,

        "preview":
            p1,

        "source_ids":
            source_ids,

        "target_id":
            target_id,

        "source_names": [
            str(
                x.get("name")
                or x.get(
                    "excel_name"
                )
                or ""
            )
            for x in sources
        ],

        "target_name":
            str(
                target.get(
                    "name"
                )
                or ""
            ),
    })


# ============================================================
# 5. OVERLAP MANUAL
# ============================================================

duplicates = {
    sid: n
    for sid, n in Counter(
        all_plan_school_ids
    ).items()
    if n > 1
}


print()
print("=" * 126)
print("4. KIEM TRA OVERLAP THU CONG")
print("=" * 126)

print(
    "Tong school_id trong 5 plan =",
    len(
        all_plan_school_ids
    ),
)

print(
    "School_id trung lap         =",
    duplicates,
)


if duplicates:
    raise RuntimeError(
        "DUNG: 5 plan co school_id "
        "chong lan."
    )


# ============================================================
# 6. MO SOURCE DB CHI DOC + COPY RAM
# ============================================================

source_con = sqlite3.connect(
    DB.resolve().as_uri()
    + "?mode=ro",
    uri=True,
    timeout=30,
)

source_con.row_factory = (
    sqlite3.Row
)

source_con.execute(
    "PRAGMA query_only=ON"
)


integrity_before = str(
    source_con.execute(
        "PRAGMA integrity_check"
    ).fetchone()[0]
)

fk_before = len(
    source_con.execute(
        "PRAGMA foreign_key_check"
    ).fetchall()
)


print()
print("=" * 126)
print("5. DATABASE TRUOC MO PHONG")
print("=" * 126)

print(
    "integrity_check   =",
    integrity_before,
)

print(
    "foreign_key_check =",
    fk_before,
)


if (
    integrity_before.lower()
    != "ok"
    or fk_before != 0
):
    raise RuntimeError(
        "DUNG: DB that chua dat "
        "integrity/FK."
    )


mem = sqlite3.connect(
    ":memory:"
)

mem.row_factory = sqlite3.Row

source_con.backup(
    mem
)

source_con.close()

mem.execute(
    "PRAGMA foreign_keys=ON"
)


# ============================================================
# 7. XAC DINH NAM PAST
# ============================================================

year_rows = mem.execute(
    """
    SELECT id,code
    FROM school_years
    ORDER BY id
    """
).fetchall()

years = {
    int(x["id"]):
        str(x["code"] or "")
    for x in year_rows
}

past_year_ids = [
    int(year_id)
    for year_id in years
    if year_id
    not in MOVE_YEAR_IDS
]


print(
    "MOVE years =",
    {
        x: years.get(x)
        for x in MOVE_YEAR_IDS
    },
)

print(
    "PAST years =",
    {
        x: years.get(x)
        for x in past_year_ids
    },
)


direct_tables = (
    direct_year_tables(
        mem
    )
)


all_source_ids = sorted({
    sid
    for detail in details
    for sid in detail[
        "source_ids"
    ]
})


# Snapshot lịch sử của TOÀN BỘ nguồn
# trước khi mô phỏng.
past_before = snapshot_past(
    mem,
    tables=direct_tables,
    source_ids=all_source_ids,
    past_year_ids=past_year_ids,
)


# ============================================================
# 8. TRANG THAI NHAN SU TRUOC MO PHONG
# ============================================================

print()
print("=" * 126)
print("6. NHAN SU CURRENT TRUOC MO PHONG")
print("=" * 126)


for detail in details:

    target_before = (
        active_staff_count(
            mem,
            detail[
                "target_id"
            ],
            CURRENT_YEAR_ID,
        )
    )

    source_before = {
        sid:
            active_staff_count(
                mem,
                sid,
                CURRENT_YEAR_ID,
            )
        for sid in detail[
            "source_ids"
        ]
    }

    detail[
        "staff_before_target"
    ] = target_before

    detail[
        "staff_before_sources"
    ] = source_before

    print(
        detail[
            "operation_id"
        ],
        "| đích=",
        target_before,
        "| nguồn=",
        source_before,
    )


# ============================================================
# 9. MO PHONG 5 PHEP TUAN TU TREN CUNG RAM DB
# ============================================================

sig = inspect.signature(
    merger_engine._apply_merge
)

previous_year_id = (
    merger_engine._previous_year_id(
        mem,
        CURRENT_YEAR_ID,
    )
)


print()
print("=" * 126)
print("7. MO PHONG TUAN TU 5 PHEP TREN RAM")
print("=" * 126)

print(
    "previous_year_id =",
    previous_year_id,
)


mem.execute(
    "BEGIN"
)


simulation_results = []


try:

    for detail in details:

        kwargs = {
            "selected_year_id":
                CURRENT_YEAR_ID,

            "previous_year_id":
                previous_year_id,

            "target_school_id":
                detail[
                    "target_id"
                ],

            "source_ids":
                detail[
                    "source_ids"
                ],

            "actor_user_id":
                None,
        }


        if (
            "backup_name"
            in sig.parameters
        ):
            kwargs[
                "backup_name"
            ] = (
                "DRY_RUN_TONG_CUOI_MN_"
                + detail[
                    "operation_id"
                ]
            )


        if (
            "record_audit"
            in sig.parameters
        ):
            kwargs[
                "record_audit"
            ] = False


        result = (
            merger_engine._apply_merge(
                mem,
                **kwargs,
            )
        )


        source_states = (
            school_state(
                mem,
                detail[
                    "source_ids"
                ],
            )
        )

        target_states = (
            school_state(
                mem,
                [
                    detail[
                        "target_id"
                    ]
                ],
            )
        )


        target_staff_after = (
            active_staff_count(
                mem,
                detail[
                    "target_id"
                ],
                CURRENT_YEAR_ID,
            )
        )

        target_structure_after = (
            staff_structure(
                mem,
                detail[
                    "target_id"
                ],
                CURRENT_YEAR_ID,
            )
        )

        duplicate_staff = (
            staff_duplicate_ids(
                mem,
                detail[
                    "target_id"
                ],
                CURRENT_YEAR_ID,
            )
        )


        residual_after = (
            count_direct_residual(
                mem,
                tables=direct_tables,
                source_ids=detail[
                    "source_ids"
                ],
                year_ids=MOVE_YEAR_IDS,
            )
        )


        active_source_users = (
            active_users_at_sources(
                mem,
                detail[
                    "source_ids"
                ],
            )
        )


        all_source_inactive = all(
            int(
                x.get(
                    "is_active"
                )
                or 0
            )
            == 0
            for x in source_states
        )


        target_active = (
            len(target_states)
            == 1
            and int(
                target_states[0].get(
                    "is_active"
                )
                or 0
            )
            == 1
        )


        result_check = {
            "source_inactive":
                all_source_inactive,

            "target_active":
                target_active,

            "current_future_residual_zero":
                not residual_after,

            "active_users_source_zero":
                active_source_users
                == 0,

            "staff_duplicate_zero":
                not duplicate_staff,
        }


        print()
        print(
            detail[
                "operation_id"
            ],
            "|",
            ", ".join(
                detail[
                    "source_names"
                ]
            ),
            "->",
            detail[
                "target_name"
            ],
        )

        print(
            "  staff trước đích    =",
            detail[
                "staff_before_target"
            ],
        )

        print(
            "  staff trước nguồn   =",
            detail[
                "staff_before_sources"
            ],
        )

        print(
            "  staff sau tại đích  =",
            target_staff_after,
        )

        print(
            "  cơ cấu sau          =",
            target_structure_after,
        )

        print(
            "  staff rollover tạo  =",
            result.get(
                "staff_rollover_created"
            ),
        )

        print(
            "  users moved         =",
            result.get(
                "users_moved"
            ),
        )

        print(
            "  source login khóa   =",
            result.get(
                "source_school_logins_disabled"
            ),
        )

        print(
            "  source inactive     =",
            result.get(
                "sources_deactivated"
            ),
        )

        print(
            "  residual sau        =",
            residual_after,
        )

        print(
            "  active users source =",
            active_source_users,
        )

        print(
            "  duplicate staff     =",
            duplicate_staff,
        )

        print(
            "  CHECK               =",
            result_check,
        )


        if not all(
            result_check.values()
        ):
            raise RuntimeError(
                "MO PHONG FAIL TAI "
                + detail[
                    "operation_id"
                ]
            )


        simulation_results.append({
            "operation_id":
                detail[
                    "operation_id"
                ],

            "plan_id":
                detail[
                    "plan_id"
                ],

            "source_ids":
                detail[
                    "source_ids"
                ],

            "target_id":
                detail[
                    "target_id"
                ],

            "staff_before_target":
                detail[
                    "staff_before_target"
                ],

            "staff_before_sources":
                detail[
                    "staff_before_sources"
                ],

            "staff_after_target":
                target_staff_after,

            "staff_structure_after":
                target_structure_after,

            "staff_rollover_created":
                int(
                    result.get(
                        "staff_rollover_created"
                    )
                    or 0
                ),

            "direct_moves":
                result.get(
                    "direct_moves"
                )
                or [],

            "no_year_moves":
                result.get(
                    "no_year_moves"
                )
                or [],

            "users_moved":
                int(
                    result.get(
                        "users_moved"
                    )
                    or 0
                ),

            "source_logins_disabled":
                int(
                    result.get(
                        "source_school_logins_disabled"
                    )
                    or 0
                ),

            "sources_deactivated":
                int(
                    result.get(
                        "sources_deactivated"
                    )
                    or 0
                ),

            "residual_after":
                residual_after,

            "checks":
                result_check,
        })


    # ========================================================
    # 10. HAU KIEM TONG CUOI TRONG RAM
    # ========================================================

    integrity_ram = str(
        mem.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]
    )

    fk_ram = len(
        mem.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()
    )


    total_residual = (
        count_direct_residual(
            mem,
            tables=direct_tables,
            source_ids=all_source_ids,
            year_ids=MOVE_YEAR_IDS,
        )
    )


    past_after = snapshot_past(
        mem,
        tables=direct_tables,
        source_ids=all_source_ids,
        past_year_ids=past_year_ids,
    )


    past_exact = (
        past_before
        == past_after
    )


    source_states_final = (
        school_state(
            mem,
            all_source_ids,
        )
    )


    all_sources_inactive = all(
        int(
            x.get(
                "is_active"
            )
            or 0
        )
        == 0
        for x in source_states_final
    )


    active_source_users_final = (
        active_users_at_sources(
            mem,
            all_source_ids,
        )
    )


    print()
    print("=" * 126)
    print("8. HAU KIEM TONG CUOI TREN RAM")
    print("=" * 126)

    print(
        "5 simulation              =",
        len(
            simulation_results
        ),
    )

    print(
        "CURRENT/FUTURE residual   =",
        total_residual,
    )

    print(
        "PAST hash exact           =",
        past_exact,
    )

    print(
        "All sources inactive      =",
        all_sources_inactive,
    )

    print(
        "Active users at sources   =",
        active_source_users_final,
    )

    print(
        "RAM integrity_check       =",
        integrity_ram,
    )

    print(
        "RAM foreign_key_check     =",
        fk_ram,
    )


    if len(
        simulation_results
    ) != 5:
        raise RuntimeError(
            "RAM simulation khong du 5."
        )


    if total_residual:
        raise RuntimeError(
            "RAM con CURRENT/FUTURE "
            "residual tai source."
        )


    if not past_exact:
        raise RuntimeError(
            "PAST bi thay doi trong RAM."
        )


    if not all_sources_inactive:
        raise RuntimeError(
            "Con source active sau simulation."
        )


    if (
        active_source_users_final
        != 0
    ):
        raise RuntimeError(
            "Con active user tai source."
        )


    if (
        integrity_ram.lower()
        != "ok"
        or fk_ram != 0
    ):
        raise RuntimeError(
            "RAM integrity/FK FAIL."
        )


finally:

    # RAM duy nhất: tuyệt đối không commit.
    try:
        mem.rollback()
    except Exception:
        pass

    mem.close()


# ============================================================
# 11. MAIN DB MUST STILL BE EXACT
# ============================================================

after_hash = {
    "db":
        sha256(DB),

    "service":
        sha256(SERVICE),

    "resolution":
        sha256(RESOLUTION),

    "roster":
        sha256(ROSTER),
}


print()
print("=" * 126)
print("9. KIEM TRA AN TOAN FILE THAT")
print("=" * 126)


for key in before_hash:
    print(
        key,
        ":",
        before_hash[key],
        "->",
        after_hash[key],
    )


if before_hash != after_hash:
    raise RuntimeError(
        "DUNG: file that da thay doi."
    )


# ============================================================
# 12. BATCH PREVIEW AGAIN ON REAL DB
# ============================================================

batch3 = build_level_batch_preview(
    school_year_id=2,
    level_code="MN",
)


print()
print("=" * 126)
print("10. BATCH THAT SAU DRY-RUN")
print("=" * 126)

print(
    "counts                =",
    batch3.get("counts"),
)

print(
    "candidate_count       =",
    batch3.get(
        "candidate_count"
    ),
)

print(
    "effective_block_count =",
    batch3.get(
        "effective_block_count"
    ),
)

print(
    "ready_for_execution   =",
    batch3.get(
        "ready_for_execution"
    ),
)

print(
    "batch fingerprint same=",
    (
        batch1.get(
            "batch_fingerprint"
        )
        == batch3.get(
            "batch_fingerprint"
        )
    ),
)


if (
    batch1.get(
        "batch_fingerprint"
    )
    != batch3.get(
        "batch_fingerprint"
    )
):
    raise RuntimeError(
        "DUNG: batch fingerprint that "
        "da thay doi."
    )


if (
    batch3.get(
        "ready_for_execution"
    )
    is not True
):
    raise RuntimeError(
        "DUNG: batch that khong con READY."
    )


print()
print("=" * 126)
print("DRY-RUN TONG CUOI 5 PHUONG AN MN: PASS")
print("=" * 126)

print(
    "Mo phong RAM          : 5/5 PASS"
)

print(
    "Overlap               : 0"
)

print(
    "CURRENT/FUTURE source : residual = 0 sau mo phong"
)

print(
    "PAST                  : GIU NGUYEN 100%"
)

print(
    "Source schools        : INACTIVE sau mo phong"
)

print(
    "Active users source   : 0 sau mo phong"
)

print(
    "Integrity RAM         : OK"
)

print(
    "Foreign key RAM       : 0"
)

print(
    "Database that         : KHONG THAY DOI"
)

print(
    "Source/Registry       : KHONG THAY DOI"
)

print(
    "Batch fingerprint     : ON DINH"
)

print(
    "5 READY               : CHUA THUC HIEN THAT"
)

print()
print(
    "BATCH_FINGERPRINT =",
    batch1.get(
        "batch_fingerprint"
    ),
)

print("=" * 126)
