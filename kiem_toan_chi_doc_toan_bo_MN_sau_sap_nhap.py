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

LAST5_BACKUP_DB = (
    ROOT
    / "backups"
    / "backup_ngoai_truoc_MN_chinh_thuc_20260910_113831"
    / "phocap.db"
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

EXPECTED_RESOLUTION_SHA = (
    "22ca7931ec40408ced25a3bde14a9672c"
    "04e12a760a077a44bb9d65b709b1163"
)

EXPECTED_ROSTER_SHA = (
    "ef865f74aa51c2700ceb7746d5433b63"
    "fc6a52a4e3169014ebe0e446ac441120"
)

EXPECTED_BATCH_FP = (
    "3ff70145c42c255075bb1430ea4bc4fde"
    "8da38521f7cb344b51349a75875cd60"
)

EXPECTED_LAST5_BACKUP_SHA = (
    "44b1aa841cdd76301c57d9fc601121ae"
    "96f9312084ef05959eaae54acf17c8c9"
)

YEAR_ID = 2
PREVIOUS_YEAR_ID = 1
MOVE_YEAR_IDS = [2, 8]
PAST_YEAR_IDS = [1, 3, 4, 5, 6, 7]

EXPECTED_PURE = 189
EXPECTED_KEEP = 52
EXPECTED_SPECIAL = 3

EXPECTED_SPECIAL_IDS = {
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

LM_OPERATION = "QD3805-ORPHAN-R1216"
LM_ID = 256
LM_CODE = "40418311"


FAILURES: list[str] = []
WARNINGS: list[str] = []


def fail(message: str) -> None:
    FAILURES.append(str(message))


def warn(message: str) -> None:
    WARNINGS.append(str(message))


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


def markers(n: int) -> str:
    return ",".join("?" for _ in range(n))


def connect_ro(path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(
        path.resolve().as_uri() + "?mode=ro",
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


def all_tables(
    con: sqlite3.Connection,
) -> list[str]:

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


def table_columns(
    con: sqlite3.Connection,
    table: str,
) -> list[str]:

    return [
        str(x["name"])
        for x in con.execute(
            f"""
            PRAGMA table_info(
                {qident(table)}
            )
            """
        ).fetchall()
    ]


def health(
    con: sqlite3.Connection,
) -> tuple[str, int]:

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


def parse_ids(value: Any) -> list[int]:

    if value is None:
        return []

    if isinstance(
        value,
        (list, tuple, set),
    ):
        raw = list(value)

    elif isinstance(value, str):

        text = value.strip()

        if not text:
            return []

        try:
            parsed = json.loads(text)

            if isinstance(parsed, list):
                raw = parsed
            else:
                raw = [parsed]

        except Exception:
            raw = [
                x.strip()
                for x in text.split(",")
                if x.strip()
            ]

    else:
        raw = [value]

    result = []

    for item in raw:
        try:
            value_int = int(item)

            if value_int:
                result.append(
                    value_int
                )
        except Exception:
            continue

    return sorted(
        set(result)
    )


def plan_id(row: dict) -> str:
    return str(
        row.get("id")
        or row.get("plan_id")
        or ""
    )


def operation_id(row: dict) -> str:
    return str(
        row.get(
            "qd3805_operation_id"
        )
        or ""
    )


def source_ids(row: dict) -> list[int]:
    return parse_ids(
        row.get(
            "source_school_ids"
        )
        if "source_school_ids" in row
        else row.get(
            "source_ids"
        )
    )


def target_id(row: dict) -> int | None:

    value = row.get(
        "target_school_id"
    )

    try:
        result = int(value)

        return (
            result
            if result > 0
            else None
        )

    except Exception:
        return None


def school_row(
    con: sqlite3.Connection,
    school_id: int,
):

    return con.execute(
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


def active_staff_ids(
    con: sqlite3.Connection,
    school_ids: list[int],
    year_id: int,
) -> set[int]:

    if not school_ids:
        return set()

    sql_marks = markers(
        len(school_ids)
    )

    rows = con.execute(
        f"""
        SELECT DISTINCT staff_member_id
        FROM staff_year_records
        WHERE school_year_id=?
          AND school_id IN ({sql_marks})
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


def duplicate_staff_at_school(
    con: sqlite3.Connection,
    school_id: int,
) -> list[dict]:

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
        ORDER BY staff_member_id
        """,
        (school_id,),
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


def current_future_residual(
    con: sqlite3.Connection,
    source_school_ids: list[int],
) -> dict[str, int]:

    if not source_school_ids:
        return {}

    result = {}

    sm = markers(
        len(source_school_ids)
    )

    ym = markers(
        len(MOVE_YEAR_IDS)
    )

    for table in all_tables(con):

        cols = set(
            table_columns(
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
                    *source_school_ids,
                    *MOVE_YEAR_IDS,
                ],
            ).fetchone()[0]
            or 0
        )

        if n:
            result[table] = n

    return result


def canonical_value(value: Any):

    if isinstance(
        value,
        bytes,
    ):
        return {
            "__bytes__":
                value.hex()
        }

    return value


def row_hash(
    con: sqlite3.Connection,
    table: str,
    columns: list[str],
    school_ids: list[int],
    year_ids: list[int],
) -> tuple[int, str]:

    if not school_ids:
        return 0, hashlib.sha256(
            b""
        ).hexdigest()

    sm = markers(
        len(school_ids)
    )

    ym = markers(
        len(year_ids)
    )

    col_sql = ",".join(
        qident(x)
        for x in columns
    )

    rows = con.execute(
        f"""
        SELECT {col_sql}
        FROM {qident(table)}
        WHERE school_id IN ({sm})
          AND school_year_id IN ({ym})
        """,
        [
            *school_ids,
            *year_ids,
        ],
    ).fetchall()

    encoded = []

    for row in rows:

        item = [
            canonical_value(
                row[col]
            )
            for col in columns
        ]

        encoded.append(
            json.dumps(
                item,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            )
        )

    encoded.sort()

    h = hashlib.sha256()

    for item in encoded:
        h.update(
            item.encode("utf-8")
        )
        h.update(b"\n")

    return len(encoded), h.hexdigest()


def operation_signatures(
    con: sqlite3.Connection,
) -> dict[tuple, list[int]]:

    result: dict[
        tuple,
        list[int],
    ] = defaultdict(list)

    rows = con.execute(
        """
        SELECT
            id,
            school_year_id,
            target_school_id,
            source_school_ids_json
        FROM school_merger_operations
        WHERE school_year_id=2
        ORDER BY id
        """
    ).fetchall()

    for row in rows:

        src = tuple(
            parse_ids(
                row[
                    "source_school_ids_json"
                ]
            )
        )

        signature = (
            int(
                row[
                    "target_school_id"
                ]
            ),
            src,
        )

        result[
            signature
        ].append(
            int(row["id"])
        )

    return result


# ============================================================
# HEADER
# ============================================================

print("=" * 128)
print(
    "KIEM TOAN CHI DOC TOAN BO CAP MAM NON SAU SAP NHAP"
)
print("=" * 128)

print(
    "Pham vi chuan:"
)
print(
    "  189 SAP NHAP + 52 GIU NGUYEN"
)

print(
    "Dac thu tach rieng:"
)
print(
    "  OP-0141 / OP-0244 / OP-0704"
)

print(
    "KHONG INSERT / UPDATE / DELETE"
)

print(
    "KHONG CHAY LAI SAP NHAP"
)

print("=" * 128)


# ============================================================
# 0. WAL GATE
# ============================================================

for suffix in (
    "-wal",
    "-journal",
):

    sidecar = Path(
        str(DB) + suffix
    )

    if (
        sidecar.exists()
        and sidecar.stat().st_size > 0
    ):
        raise RuntimeError(
            "DUNG: "
            + sidecar.name
            + " dang co du lieu. "
            "Hay dung Uvicorn/server hoan toan "
            "roi chay lai audit."
        )


# ============================================================
# 1. HASH GATE
# ============================================================

before_hash = {
    "db":
        sha256(DB),

    "service":
        sha256(SERVICE),

    "lock":
        sha256(LOCK),

    "resolution":
        sha256(RESOLUTION),

    "roster":
        sha256(ROSTER),
}

expected_hash = {
    "db":
        EXPECTED_DB_SHA,

    "service":
        EXPECTED_SERVICE_SHA,

    "lock":
        EXPECTED_LOCK_SHA,

    "resolution":
        EXPECTED_RESOLUTION_SHA,

    "roster":
        EXPECTED_ROSTER_SHA,
}


print()
print("=" * 128)
print("1. HASH GATE")
print("=" * 128)


for key in before_hash:

    print(
        f"{key:12s} = "
        f"{before_hash[key]}"
    )

    if (
        before_hash[key]
        != expected_hash[key]
    ):
        raise RuntimeError(
            "DUNG: "
            + key
            + " khong dung snapshot "
              "sau batch MN da khoa."
        )


# ============================================================
# 2. BACKUP BASELINE
# ============================================================

print()
print("=" * 128)
print("2. BACKUP DOI CHIEU")
print("=" * 128)


if not BASELINE_DB.exists():
    raise RuntimeError(
        "DUNG: khong tim thay backup truoc V13.6:\n"
        + str(BASELINE_DB)
    )


if not LAST5_BACKUP_DB.exists():
    raise RuntimeError(
        "DUNG: khong tim thay backup truoc 5 MN cuoi:\n"
        + str(LAST5_BACKUP_DB)
    )


print(
    "Baseline V13.6 =",
    BASELINE_DB,
)

print(
    "Backup 5 MN    =",
    LAST5_BACKUP_DB,
)


last5_backup_sha = (
    sha256(
        LAST5_BACKUP_DB
    )
)

print(
    "SHA backup 5   =",
    last5_backup_sha,
)


if (
    last5_backup_sha
    != EXPECTED_LAST5_BACKUP_SHA
):
    raise RuntimeError(
        "DUNG: backup 5 MN cuoi "
        "khong dung snapshot 44b1aa..."
    )


with connect_ro(
    BASELINE_DB
) as b6:

    b6_integrity, b6_fk = (
        health(b6)
    )


with connect_ro(
    LAST5_BACKUP_DB
) as b5:

    b5_integrity, b5_fk = (
        health(b5)
    )


print(
    "V13.6 integrity/FK =",
    b6_integrity,
    "/",
    b6_fk,
)

print(
    "5MN integrity/FK   =",
    b5_integrity,
    "/",
    b5_fk,
)


if (
    b6_integrity.lower()
    != "ok"
    or b6_fk != 0
):
    raise RuntimeError(
        "DUNG: backup V13.6 "
        "khong dat integrity/FK."
    )


if (
    b5_integrity.lower()
    != "ok"
    or b5_fk != 0
):
    raise RuntimeError(
        "DUNG: backup 5 MN "
        "khong dat integrity/FK."
    )


# ============================================================
# 3. SERVICE / REGISTRY
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

rows, raw_counts, candidates, meta = (
    svc._state_rows(
        2,
        "MN",
    )
)


pure_ops = list(
    ctx.get(
        "pure_actions"
    )
    or []
)

keep_ops = list(
    ctx.get(
        "keep_ops"
    )
    or []
)

special_ops = list(
    ctx.get(
        "special_ops"
    )
    or []
)

unresolved = list(
    ctx.get(
        "unresolved"
    )
    or []
)


pure_ids = {
    str(
        x.get("operation_id")
        or ""
    )
    for x in pure_ops
}

keep_ids = {
    str(
        x.get("operation_id")
        or ""
    )
    for x in keep_ops
}

special_ids = {
    str(
        x.get("operation_id")
        or ""
    )
    for x in special_ops
}


print()
print("=" * 128)
print("3. REGISTRY / BATCH")
print("=" * 128)

print(
    "pure_actions      =",
    len(pure_ops),
)

print(
    "keep_ops          =",
    len(keep_ops),
)

print(
    "special_ops       =",
    len(special_ops),
)

print(
    "unresolved        =",
    len(unresolved),
)

print(
    "counts            =",
    preview.get(
        "counts"
    ),
)

print(
    "candidate_count   =",
    preview.get(
        "candidate_count"
    ),
)

print(
    "all_done          =",
    preview.get(
        "all_done"
    ),
)

print(
    "previous_batch    =",
    preview.get(
        "previous_batch"
    )
    is not None,
)

print(
    "batch_fingerprint =",
    preview.get(
        "batch_fingerprint"
    ),
)


if len(
    pure_ops
) != EXPECTED_PURE:
    fail(
        "pure_actions != 189"
    )


if len(
    keep_ops
) != EXPECTED_KEEP:
    fail(
        "keep_ops != 52"
    )


if len(
    special_ops
) != EXPECTED_SPECIAL:
    fail(
        "special_ops != 3"
    )


if unresolved:
    fail(
        "Van con unresolved operation."
    )


if (
    special_ids
    != EXPECTED_SPECIAL_IDS
):
    fail(
        "3 operation dac thu khong dung "
        "0141/0244/0704."
    )


if preview.get("counts") != {
    "KEEP": 52,
    "DONE": 189,
    "READY": 0,
    "BLOCK": 0,
}:
    fail(
        "Batch KPI khong dung "
        "52/189/0/0."
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


if (
    preview.get(
        "previous_batch"
    )
    is None
):
    fail(
        "Khong co MN batch log."
    )


# Sau khi đã commit, fingerprint preview
# có thể thay đổi theo trạng thái DONE.
# Fingerprint chuẩn phải tồn tại trong batch log,
# kiểm tra ở phần DB bên dưới.


# ============================================================
# 4. ROW MAPPING
# ============================================================

row_map: dict[
    str,
    list[dict],
] = defaultdict(list)


for raw in rows:

    row = dict(raw)

    op = operation_id(
        row
    )

    if op:
        row_map[op].append(
            row
        )


duplicate_mapping = {
    op: [
        plan_id(x)
        for x in group
    ]
    for op, group in row_map.items()
    if len(group) != 1
    and op in (
        pure_ids
        | keep_ids
    )
}


print()
print("=" * 128)
print("4. MAPPING 189 DONE + 52 KEEP")
print("=" * 128)

print(
    "row operation IDs =",
    len(row_map),
)

print(
    "duplicate mapping =",
    duplicate_mapping,
)


if duplicate_mapping:
    fail(
        "Co operation mapping "
        "khong duy nhat."
    )


missing_pure = sorted(
    pure_ids
    - set(row_map)
)

missing_keep = sorted(
    keep_ids
    - set(row_map)
)


print(
    "missing pure =",
    len(missing_pure),
)

print(
    "missing keep =",
    len(missing_keep),
)


if missing_pure:
    fail(
        "Co pure operation "
        "khong map duoc plan: "
        + repr(
            missing_pure[:20]
        )
    )


if missing_keep:
    fail(
        "Co KEEP operation "
        "khong map duoc plan: "
        + repr(
            missing_keep[:20]
        )
    )


# ============================================================
# 5. DB CURRENT
# ============================================================

con = connect_ro(
    DB
)

baseline = connect_ro(
    BASELINE_DB
)


try:

    integrity, fk = health(
        con
    )


    print()
    print("=" * 128)
    print("5. DATABASE CURRENT")
    print("=" * 128)

    print(
        "integrity_check   =",
        integrity,
    )

    print(
        "foreign_key_check =",
        fk,
    )


    if (
        integrity.lower()
        != "ok"
        or fk != 0
    ):
        fail(
            "Current DB khong dat "
            "integrity/FK."
        )


    years = {
        int(x["id"]):
            str(x["code"])
        for x in con.execute(
            """
            SELECT id,code
            FROM school_years
            """
        ).fetchall()
    }


    print(
        "MOVE years =",
        {
            y: years.get(y)
            for y in MOVE_YEAR_IDS
        },
    )

    print(
        "PAST years =",
        {
            y: years.get(y)
            for y in PAST_YEAR_IDS
        },
    )


    if (
        years.get(2)
        != "2026-2027"
        or years.get(8)
        != "2027-2028"
        or years.get(1)
        != "2025-2026"
    ):
        fail(
            "Mapping nam hoc khong dung."
        )


    # ========================================================
    # 6. BATCH LOG
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
    print("6. BATCH LOG MN")
    print("=" * 128)

    print(
        "MN batch rows =",
        len(batch_rows),
    )


    if len(
        batch_rows
    ) != 1:

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


        if int(
            batch.get(
                "keep_count"
            )
            or 0
        ) != 52:
            fail(
                "Batch keep_count != 52."
            )


        if int(
            batch.get(
                "done_before_count"
            )
            or 0
        ) != 184:
            fail(
                "Batch done_before_count != 184."
            )


        if int(
            batch.get(
                "executed_count"
            )
            or 0
        ) != 5:
            fail(
                "Batch executed_count != 5."
            )


        if str(
            batch.get(
                "batch_fingerprint"
            )
            or ""
        ) != EXPECTED_BATCH_FP:
            fail(
                "Batch fingerprint "
                "khong dung 3ff70145..."
            )


    # ========================================================
    # 7. 189 PURE OPERATIONS
    # ========================================================

    operation_log_map = (
        operation_signatures(
            con
        )
    )

    absorbed_owner: dict[
        int,
        str,
    ] = {}

    target_owner: dict[
        int,
        list[str],
    ] = defaultdict(list)

    all_absorbed: set[int] = set()
    all_targets: set[int] = set()
    all_involved: set[int] = set()

    source_state_errors = []
    target_state_errors = []
    plan_shape_errors = []
    log_missing = []
    log_duplicate = []
    staff_mismatch = []
    staff_duplicate = []
    baseline_user_errors = []


    for op in sorted(
        pure_ids
    ):

        group = row_map.get(
            op,
            [],
        )

        if len(group) != 1:
            continue

        row = group[0]

        state = str(
            row.get(
                "batch_state"
            )
            or ""
        ).upper()

        if state != "DONE":
            fail(
                op
                + " state != DONE."
            )

        src = source_ids(
            row
        )

        tgt = target_id(
            row
        )


        if (
            not src
            or tgt is None
            or tgt in src
        ):
            plan_shape_errors.append({
                "operation_id":
                    op,

                "plan_id":
                    plan_id(row),

                "source_ids":
                    src,

                "target_id":
                    tgt,
            })

            continue


        all_absorbed.update(
            src
        )

        all_targets.add(
            tgt
        )

        all_involved.update(
            src
        )

        all_involved.add(
            tgt
        )

        target_owner[
            tgt
        ].append(
            op
        )


        for sid in src:

            if sid in absorbed_owner:
                fail(
                    "Source school "
                    + str(sid)
                    + " bi dung boi ca "
                    + absorbed_owner[sid]
                    + " va "
                    + op
                )

            else:
                absorbed_owner[
                    sid
                ] = op


        # Current school states.
        for sid in src:

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
                source_state_errors.append({
                    "operation_id":
                        op,

                    "school_id":
                        sid,

                    "school":
                        (
                            dict(s)
                            if s is not None
                            else None
                        ),
                })


        t = school_row(
            con,
            tgt,
        )

        if (
            t is None
            or not bool(
                t["is_active"]
            )
        ):
            target_state_errors.append({
                "operation_id":
                    op,

                "school_id":
                    tgt,

                "school":
                    (
                        dict(t)
                        if t is not None
                        else None
                    ),
            })


        # Operation log signature.
        signature = (
            tgt,
            tuple(src),
        )

        log_ids = (
            operation_log_map.get(
                signature
            )
            or []
        )

        if not log_ids:
            log_missing.append({
                "operation_id":
                    op,

                "plan_id":
                    plan_id(row),

                "source_ids":
                    src,

                "target_id":
                    tgt,
            })

        elif len(log_ids) > 1:
            log_duplicate.append({
                "operation_id":
                    op,

                "source_ids":
                    src,

                "target_id":
                    tgt,

                "operation_log_ids":
                    log_ids,
            })


        # Staff:
        # 2026-2027 target phải bằng union
        # nhân sự active 2025-2026
        # của target + toàn bộ source.
        prev_staff = active_staff_ids(
            con,
            [
                tgt,
                *src,
            ],
            PREVIOUS_YEAR_ID,
        )

        cur_staff = active_staff_ids(
            con,
            [tgt],
            YEAR_ID,
        )


        if prev_staff != cur_staff:

            staff_mismatch.append({
                "operation_id":
                    op,

                "plan_id":
                    plan_id(row),

                "target_id":
                    tgt,

                "source_ids":
                    src,

                "previous_union":
                    len(prev_staff),

                "current_target":
                    len(cur_staff),

                "missing_at_target":
                    sorted(
                        prev_staff
                        - cur_staff
                    )[:20],

                "extra_at_target":
                    sorted(
                        cur_staff
                        - prev_staff
                    )[:20],
            })


        dup = duplicate_staff_at_school(
            con,
            tgt,
        )

        if dup:
            staff_duplicate.append({
                "operation_id":
                    op,

                "target_id":
                    tgt,

                "duplicates":
                    dup[:20],
            })


        # User baseline V13.6 -> current.
        # truong_* ở source phải inactive tại source.
        # User khác đã gắn source thì phải về target.
        for sid in src:

            pre_users = baseline.execute(
                """
                SELECT
                    id,
                    username,
                    school_id,
                    is_active
                FROM users
                WHERE school_id=?
                ORDER BY id
                """,
                (sid,),
            ).fetchall()


            for pre_user in pre_users:

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
                            pre_user["id"]
                        ),
                    ),
                ).fetchone()


                if cur is None:

                    baseline_user_errors.append({
                        "operation_id":
                            op,

                        "user_id":
                            int(
                                pre_user["id"]
                            ),

                        "username":
                            str(
                                pre_user[
                                    "username"
                                ]
                            ),

                        "error":
                            "USER_MISSING_CURRENT",
                    })

                    continue


                username = str(
                    pre_user[
                        "username"
                    ]
                    or ""
                )


                if username.lower().startswith(
                    "truong_"
                ):

                    if (
                        int(
                            cur[
                                "school_id"
                            ]
                            or 0
                        )
                        != sid
                        or bool(
                            cur[
                                "is_active"
                            ]
                        )
                    ):
                        baseline_user_errors.append({
                            "operation_id":
                                op,

                            "user_id":
                                int(
                                    cur["id"]
                                ),

                            "username":
                                username,

                            "expected":
                                (
                                    "source + inactive"
                                ),

                            "actual_school_id":
                                cur[
                                    "school_id"
                                ],

                            "actual_active":
                                cur[
                                    "is_active"
                                ],
                        })

                else:

                    if int(
                        cur[
                            "school_id"
                        ]
                        or 0
                    ) != tgt:

                        baseline_user_errors.append({
                            "operation_id":
                                op,

                            "user_id":
                                int(
                                    cur["id"]
                                ),

                            "username":
                                username,

                            "expected_target":
                                tgt,

                            "actual_school_id":
                                cur[
                                    "school_id"
                                ],
                        })


    print()
    print("=" * 128)
    print("7. KET QUA 189 PHUONG AN DONE")
    print("=" * 128)

    print(
        "Pure operation       =",
        len(pure_ids),
    )

    print(
        "Unique absorbed src  =",
        len(all_absorbed),
    )

    print(
        "Unique target        =",
        len(all_targets),
    )

    print(
        "Plan shape errors    =",
        len(plan_shape_errors),
    )

    print(
        "Source state errors  =",
        len(source_state_errors),
    )

    print(
        "Target state errors  =",
        len(target_state_errors),
    )

    print(
        "Missing op logs      =",
        len(log_missing),
    )

    print(
        "Duplicate op logs    =",
        len(log_duplicate),
    )

    print(
        "Staff union mismatch =",
        len(staff_mismatch),
    )

    print(
        "Staff duplicates     =",
        len(staff_duplicate),
    )

    print(
        "Baseline user errors =",
        len(baseline_user_errors),
    )


    if plan_shape_errors:
        fail(
            "Co plan source/target "
            "khong dung hinh dang."
        )


    if source_state_errors:
        fail(
            "Co source cua 189 plan "
            "van active/khong ton tai."
        )


    if target_state_errors:
        fail(
            "Co target cua 189 plan "
            "khong active."
        )


    if log_missing:
        fail(
            "Co pure plan khong tim thay "
            "school_merger_operations log."
        )


    if log_duplicate:
        fail(
            "Co pure plan co nhieu "
            "operation log cung signature."
        )


    if staff_mismatch:
        fail(
            "Co target co nhan su current "
            "khong bang union 2025-2026."
        )


    if staff_duplicate:
        fail(
            "Co duplicate active staff "
            "tai target."
        )


    if baseline_user_errors:
        fail(
            "Co user baseline V13.6 "
            "khong ve dung target/khong khoa."
        )


    # ========================================================
    # 8. GLOBAL SOURCE / CURRENT-FUTURE
    # ========================================================

    residual = current_future_residual(
        con,
        sorted(
            all_absorbed
        ),
    )


    if all_absorbed:

        sm = markers(
            len(all_absorbed)
        )

        active_users_at_sources = int(
            con.execute(
                f"""
                SELECT COUNT(*)
                FROM users
                WHERE school_id IN ({sm})
                  AND is_active=1
                """,
                sorted(
                    all_absorbed
                ),
            ).fetchone()[0]
            or 0
        )

    else:
        active_users_at_sources = 0


    print()
    print("=" * 128)
    print("8. GLOBAL SOURCE GATE")
    print("=" * 128)

    print(
        "CURRENT/FUTURE residual =",
        residual,
    )

    print(
        "Active users at source  =",
        active_users_at_sources,
    )


    if residual:
        fail(
            "CURRENT/FUTURE van con "
            "tai absorbed source."
        )


    if (
        active_users_at_sources
        != 0
    ):
        fail(
            "Van con active user "
            "tai absorbed source."
        )


    # ========================================================
    # 9. PAST HASH VS BACKUP V13.6
    # ========================================================

    current_tables = set(
        all_tables(con)
    )

    baseline_tables = set(
        all_tables(baseline)
    )

    common_tables = sorted(
        current_tables
        & baseline_tables
    )

    past_mismatch = []
    past_checked = 0


    for table in common_tables:

        cur_cols = set(
            table_columns(
                con,
                table,
            )
        )

        old_cols = set(
            table_columns(
                baseline,
                table,
            )
        )

        if not {
            "school_id",
            "school_year_id",
        }.issubset(
            cur_cols
            & old_cols
        ):
            continue


        columns = [
            x
            for x in table_columns(
                baseline,
                table,
            )
            if x in cur_cols
        ]


        old_count, old_hash = row_hash(
            baseline,
            table,
            columns,
            sorted(
                all_involved
            ),
            PAST_YEAR_IDS,
        )

        new_count, new_hash = row_hash(
            con,
            table,
            columns,
            sorted(
                all_involved
            ),
            PAST_YEAR_IDS,
        )


        past_checked += 1


        if (
            old_count != new_count
            or old_hash != new_hash
        ):
            past_mismatch.append({
                "table":
                    table,

                "baseline_rows":
                    old_count,

                "current_rows":
                    new_count,

                "baseline_hash":
                    old_hash,

                "current_hash":
                    new_hash,
            })


    print()
    print("=" * 128)
    print("9. PAST DOI CHIEU BACKUP TRUOC V13.6")
    print("=" * 128)

    print(
        "Common year-aware tables checked =",
        past_checked,
    )

    print(
        "PAST mismatch tables             =",
        len(past_mismatch),
    )


    if past_mismatch:
        fail(
            "PAST khong con exact "
            "voi baseline V13.6."
        )


    # ========================================================
    # 10. 52 KEEP
    # ========================================================

    keep_school_ids: set[int] = set()
    keep_errors = []


    for op in sorted(
        keep_ids
    ):

        group = row_map.get(
            op,
            [],
        )

        if len(group) != 1:
            continue

        row = group[0]

        if str(
            row.get(
                "batch_state"
            )
            or ""
        ).upper() != "KEEP":

            keep_errors.append({
                "operation_id":
                    op,

                "error":
                    "STATE_NOT_KEEP",
            })

            continue


        ids = set(
            source_ids(
                row
            )
        )

        tgt = target_id(
            row
        )

        if tgt is not None:
            ids.add(tgt)


        if not ids:

            keep_errors.append({
                "operation_id":
                    op,

                "plan_id":
                    plan_id(row),

                "error":
                    "NO_SCHOOL_ID",
            })

            continue


        for sid in ids:

            keep_school_ids.add(
                sid
            )

            school = school_row(
                con,
                sid,
            )

            if (
                school is None
                or not bool(
                    school["is_active"]
                )
            ):
                keep_errors.append({
                    "operation_id":
                        op,

                    "school_id":
                        sid,

                    "error":
                        "KEEP_SCHOOL_NOT_ACTIVE",
                })


    overlap_keep_source = (
        keep_school_ids
        & all_absorbed
    )


    print()
    print("=" * 128)
    print("10. KIEM TRA 52 GIU NGUYEN")
    print("=" * 128)

    print(
        "KEEP operations     =",
        len(keep_ids),
    )

    print(
        "KEEP school IDs     =",
        len(keep_school_ids),
    )

    print(
        "KEEP errors         =",
        len(keep_errors),
    )

    print(
        "KEEP/source overlap =",
        sorted(
            overlap_keep_source
        ),
    )


    if keep_errors:
        fail(
            "Co KEEP school "
            "khong active/khong map dung."
        )


    if overlap_keep_source:
        fail(
            "KEEP school bi trung "
            "absorbed source."
        )


    # ========================================================
    # 11. LƯỢNG MINH
    # ========================================================

    lm_school = school_row(
        con,
        LM_ID,
    )

    lm_in_keep = (
        LM_OPERATION in keep_ids
    )

    lm_in_unresolved = any(
        str(
            x.get("operation_id")
            or ""
        )
        == LM_OPERATION
        for x in unresolved
    )


    lm_bad_merger_logs = []


    rows_ops = con.execute(
        """
        SELECT
            id,
            target_school_id,
            source_school_ids_json
        FROM school_merger_operations
        WHERE school_year_id=2
        ORDER BY id
        """
    ).fetchall()


    for row in rows_ops:

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
            lm_bad_merger_logs.append(
                int(row["id"])
            )


    print()
    print("=" * 128)
    print("11. MAM NON LUONG MINH")
    print("=" * 128)

    print(
        "LM in KEEP        =",
        lm_in_keep,
    )

    print(
        "LM in unresolved  =",
        lm_in_unresolved,
    )

    print(
        "LM school         =",
        (
            dict(lm_school)
            if lm_school is not None
            else None
        ),
    )

    print(
        "LM merger logs    =",
        lm_bad_merger_logs,
    )


    if not lm_in_keep:
        fail(
            "Luong Minh khong con "
            "nam trong KEEP."
        )


    if lm_in_unresolved:
        fail(
            "Luong Minh quay lai unresolved."
        )


    if (
        lm_school is None
        or str(
            lm_school["code"]
        )
        != LM_CODE
        or not bool(
            lm_school["is_active"]
        )
    ):
        fail(
            "Luong Minh khong active/"
            "sai school code."
        )


    if lm_bad_merger_logs:
        fail(
            "Luong Minh bi ghi "
            "vao merger operation."
        )


    # ========================================================
    # 12. DUPLICATE STAFF TOAN TARGET
    # ========================================================

    cross_target_dups = []


    if all_targets:

        tm = markers(
            len(all_targets)
        )

        rows_dup = con.execute(
            f"""
            SELECT
                staff_member_id,
                COUNT(DISTINCT school_id)
                    AS school_count,
                GROUP_CONCAT(
                    DISTINCT school_id
                ) AS schools
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
                all_targets
            ),
        ).fetchall()


        cross_target_dups = [
            dict(x)
            for x in rows_dup
        ]


    print()
    print("=" * 128)
    print("12. DUPLICATE NHAN SU GIUA CAC TARGET")
    print("=" * 128)

    print(
        "Cross-target duplicate =",
        len(
            cross_target_dups
        ),
    )


    if cross_target_dups:
        warn(
            "Co staff_member_id active "
            "tai hon 1 target. "
            "Can xem chi tiet; co the la "
            "truong hop kiem nhiem hop le."
        )


    # ========================================================
    # 13. 5 PHƯƠNG ÁN VỪA EXECUTE
    # ========================================================

    new_exec_rows = con.execute(
        """
        SELECT
            id,
            plan_id,
            operation_id,
            target_school_id,
            source_school_ids_json,
            backup_name
        FROM school_merger_official_executions
        WHERE school_year_id=2
        ORDER BY id
        """
    ).fetchall()


    new_plan_ids = {
        plan_id(row_map[op][0])
        for op in EXPECTED_LAST5
        if op in row_map
        and len(
            row_map[op]
        ) == 1
    }


    exact_last5_logs = [
        dict(x)
        for x in new_exec_rows
        if str(
            x["plan_id"]
        )
        in new_plan_ids
    ]


    print()
    print("=" * 128)
    print("13. 5 PHUONG AN MN VUA GHI THAT")
    print("=" * 128)

    print(
        "Expected plan IDs =",
        len(new_plan_ids),
    )

    print(
        "Execution rows    =",
        len(exact_last5_logs),
    )


    if len(
        new_plan_ids
    ) != 5:
        fail(
            "Khong xac dinh du "
            "5 plan ID cuoi."
        )


    if len(
        exact_last5_logs
    ) != 5:
        fail(
            "5 MN cuoi khong co "
            "dung 5 official execution logs."
        )


    # ========================================================
    # 14. 3 ĐẶC THÙ
    # ========================================================

    print()
    print("=" * 128)
    print("14. 3 PHUONG AN DAC THU CUNG CAP")
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

        print()

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

        print(
            "  reason   =",
            item.get(
                "reason"
            ),
        )


    print()
    print(
        "LUU Y: 3 operation tren chi tiep nhan diem/lop,"
    )

    print(
        "khong duoc coi la sap nhap toan bo truong."
    )

    print(
        "Audit nay KHONG tu suy doan ket qua chuyen lop/diem."
    )


finally:

    try:
        con.close()
    except Exception:
        pass

    try:
        baseline.close()
    except Exception:
        pass


# ============================================================
# 15. IMMUTABILITY
# ============================================================

after_hash = {
    "db":
        sha256(DB),

    "service":
        sha256(SERVICE),

    "lock":
        sha256(LOCK),

    "resolution":
        sha256(RESOLUTION),

    "roster":
        sha256(ROSTER),
}


print()
print("=" * 128)
print("15. KIEM TRA FILE KHONG THAY DOI")
print("=" * 128)


for key in before_hash:

    print(
        key,
        ":",
        before_hash[key],
        "->",
        after_hash[key],
    )


if (
    before_hash
    != after_hash
):
    fail(
        "File that bi thay doi "
        "trong luc audit."
    )


# ============================================================
# 16. CHI TIET LOI
# ============================================================

print()
print("=" * 128)
print("16. TONG HOP LOI / CANH BAO")
print("=" * 128)

print(
    "FAILURES =",
    len(FAILURES),
)

for i, item in enumerate(
    FAILURES,
    start=1,
):
    print(
        f"  FAIL {i}: {item}"
    )


print(
    "WARNINGS =",
    len(WARNINGS),
)

for i, item in enumerate(
    WARNINGS,
    start=1,
):
    print(
        f"  WARN {i}: {item}"
    )


# Nếu có lỗi, in vài mẫu để gửi lại.
DETAIL_GROUPS = [
    (
        "PLAN SHAPE",
        locals().get(
            "plan_shape_errors",
            [],
        ),
    ),

    (
        "SOURCE STATE",
        locals().get(
            "source_state_errors",
            [],
        ),
    ),

    (
        "TARGET STATE",
        locals().get(
            "target_state_errors",
            [],
        ),
    ),

    (
        "LOG MISSING",
        locals().get(
            "log_missing",
            [],
        ),
    ),

    (
        "LOG DUPLICATE",
        locals().get(
            "log_duplicate",
            [],
        ),
    ),

    (
        "STAFF MISMATCH",
        locals().get(
            "staff_mismatch",
            [],
        ),
    ),

    (
        "STAFF DUPLICATE",
        locals().get(
            "staff_duplicate",
            [],
        ),
    ),

    (
        "USER ERROR",
        locals().get(
            "baseline_user_errors",
            [],
        ),
    ),

    (
        "PAST MISMATCH",
        locals().get(
            "past_mismatch",
            [],
        ),
    ),

    (
        "KEEP ERROR",
        locals().get(
            "keep_errors",
            [],
        ),
    ),

    (
        "CROSS TARGET DUP",
        locals().get(
            "cross_target_dups",
            [],
        ),
    ),
]


for title, items in DETAIL_GROUPS:

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

if not FAILURES:

    print(
        "KIEM TOAN SAP NHAP CHUAN CAP MAM NON: PASS"
    )

    print("=" * 128)

    print(
        "189 operation       : DONE"
    )

    print(
        "52 KEEP             : PASS"
    )

    print(
        "Unresolved          : 0"
    )

    print(
        "CURRENT/FUTURE src  : 0"
    )

    print(
        "Active users src    : 0"
    )

    print(
        "PAST vs V13.6       : EXACT"
    )

    print(
        "Staff union         : PASS"
    )

    print(
        "Batch MN            : PASS"
    )

    print(
        "Lượng Minh          : GIU NGUYEN"
    )

    print(
        "DB integrity/FK     : PASS"
    )

    print(
        "Database/Source     : KHONG THAY DOI"
    )

    print()
    print(
        "MN_STANDARD_POST_MERGER_AUDIT=PASS"
    )

    print(
        "MN_SPECIAL_CASES_TO_AUDIT=3"
    )

    print()
    print(
        "CHUA KET LUAN TOAN BO MN CLOSED "
        "CHO DEN KHI KIEM TOAN RIENG "
        "OP-0141 / OP-0244 / OP-0704."
    )

else:

    print(
        "KIEM TOAN SAP NHAP CHUAN CAP MAM NON: FAIL"
    )

    print(
        "KHONG CHUYEN SANG CAP HOC TIEP THEO."
    )

    print(
        "GUI KET QUA AUDIT DE DOI CHIEU."
    )


print("=" * 128)
