from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import sys
import unicodedata
from collections import Counter
from pathlib import Path


sys.dont_write_bytecode = True

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


ROOT = Path(r"C:\PhoCap")

DB = ROOT / "data" / "phocap.db"

LEVEL_SERVICE = (
    ROOT
    / "app"
    / "services"
    / "school_merger_level_batch_service.py"
)

ENGINE_FILE = (
    ROOT
    / "app"
    / "services"
    / "school_merger_service.py"
)

LOCK = (
    ROOT
    / "data"
    / "school_merger_registry"
    / "qd3805_level_lock.json"
)

ROSTER = (
    ROOT
    / "data"
    / "school_merger_source_rosters"
    / "THCS_2025_2026.json"
)

RESOLUTION = (
    ROOT
    / "data"
    / "school_merger_registry"
    / "qd3805_thcs_resolution.json"
)

HISTORY = (
    ROOT
    / "data"
    / "school_merger_approved_plans.json"
)


EXPECTED = {
    "db":
        "882e4925fd3e39d7e097ce127612c093"
        "852075e608d3f937294135282afec75a",

    "level_service":
        "9104fb99c78755e9eec86d090659b3a9"
        "22834ff097d7292aa4d4b29e360a27f9",

    # Engine CURRENT + FUTURE đã khóa từ V13.5.2.
    "engine":
        "414fb49a4c5f4fed7b571cc55df381678"
        "fe660cd8a675ecaa2f6fd70ebd7827a",

    "lock":
        "ad310048a4c5b239404e0902cc04fda1"
        "d73474d11a739a2ca009d2727e4390c3",

    "roster":
        "926528e0ae600a6b950b459c6f8ec5c"
        "6810e69d49158d1ff3c9a3d76c0bca657",

    "resolution":
        "d9d347b19de0795553c8f047cb91a430"
        "ded63d9232ac7eda7ea069b716c2c0f4",

    "history":
        "4e2c5f044c48c57dda40fecc11f4e9f"
        "466f236aacc082f224536b1685cadb1fc",
}


EXPECTED_READY_OPS = {
    "QD3805-OP-0011",
    "QD3805-OP-0014",
    "QD3805-OP-0026",
    "QD3805-OP-0027",
    "QD3805-OP-0028",
    "QD3805-OP-0034",
    "QD3805-OP-0035",
    "QD3805-OP-0042",
    "QD3805-OP-0043",
    "QD3805-OP-0050",
    "QD3805-OP-0051",
    "QD3805-OP-0061",
    "QD3805-OP-0068",
}


# Các trường tuyệt đối không được xuất hiện
# trong 13 phương án dry-run.
FORBIDDEN_SCHOOL_IDS = {
    1408,  # THCS Nghi Hương - GIỮ NGUYÊN
    1607,  # THCS Nghi Hoa - đã hoàn tất trước
    1608,  # THCS Nghi Vạn - đã hoàn tất trước
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


def qident(value: str) -> str:

    return (
        '"'
        + str(value).replace(
            '"',
            '""',
        )
        + '"'
    )


def markers(n: int) -> str:

    return ",".join(
        "?"
        for _ in range(n)
    )


def clean_group(value) -> str:

    text = str(
        value or ""
    ).strip().upper()

    text = text.replace(
        "Đ",
        "D",
    )

    text = unicodedata.normalize(
        "NFD",
        text,
    )

    text = "".join(
        c
        for c in text
        if unicodedata.category(c)
        != "Mn"
    )

    text = (
        text.replace(" ", "_")
        .replace("-", "_")
        .replace("/", "_")
    )

    while "__" in text:
        text = text.replace(
            "__",
            "_",
        )

    return text


def canonical_staff_group(value) -> str:

    code = clean_group(
        value
    )

    if code in {
        "CBQL",
        "QUAN_LY",
        "CAN_BO_QUAN_LY",
        "CANBO_QUANLY",
    }:
        return "CBQL"

    if code in {
        "GIAO_VIEN",
        "GIAOVIEN",
        "GV",
    }:
        return "GIAO_VIEN"

    if code in {
        "NHAN_VIEN",
        "NHANVIEN",
        "NV",
    }:
        return "NHAN_VIEN"

    return (
        code
        if code
        else "CHUA_XAC_DINH"
    )


def connect_read_only():

    con = sqlite3.connect(
        DB.resolve().as_uri()
        + "?mode=ro",
        uri=True,
        timeout=120,
    )

    con.row_factory = sqlite3.Row

    con.execute(
        "PRAGMA query_only=ON"
    )

    con.execute(
        "PRAGMA foreign_keys=ON"
    )

    return con


class _FakeCursor:

    def __init__(self, rows):

        self._rows = list(
            rows
        )

        self.rowcount = -1


    def fetchone(self):

        return (
            self._rows[0]
            if self._rows
            else None
        )


    def fetchall(self):

        return list(
            self._rows
        )


class SimulationConnection(
    sqlite3.Connection
):

    """
    Chỉ hoãn hai full-scan PRAGMA
    trong từng _apply_merge.

    SQL nghiệp vụ, residual,
    users, staff và post-check
    vẫn chạy thật trên DB RAM.
    """

    defer_heavy_pragmas = True


    def execute(
        self,
        sql,
        parameters=(),
        /,
    ):

        normalized = " ".join(
            str(sql)
            .strip()
            .lower()
            .split()
        )


        if self.defer_heavy_pragmas:

            if (
                normalized
                == "pragma foreign_key_check"
            ):

                return _FakeCursor(
                    []
                )


            if (
                normalized
                == "pragma integrity_check"
            ):

                return _FakeCursor(
                    [
                        ("ok",)
                    ]
                )


        return super().execute(
            sql,
            parameters,
        )


def real_integrity(
    con: SimulationConnection,
) -> str:

    old = (
        con.defer_heavy_pragmas
    )

    con.defer_heavy_pragmas = False

    try:

        return str(
            con.execute(
                "PRAGMA integrity_check"
            ).fetchone()[0]
        )

    finally:

        con.defer_heavy_pragmas = old


def real_fk(
    con: SimulationConnection,
):

    old = (
        con.defer_heavy_pragmas
    )

    con.defer_heavy_pragmas = False

    try:

        return con.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()

    finally:

        con.defer_heavy_pragmas = old


def year_aware_tables(
    con,
) -> list[str]:

    result = []


    tables = con.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type='table'
          AND name NOT LIKE 'sqlite_%'
        ORDER BY name
        """
    ).fetchall()


    for row in tables:

        table = str(
            row[0]
        )


        cols = {
            str(x[1])
            for x in con.execute(
                "PRAGMA table_info("
                + qident(table)
                + ")"
            ).fetchall()
        }


        if {
            "school_id",
            "school_year_id",
        }.issubset(cols):

            result.append(
                table
            )


    return result


def encode_value(value):

    if isinstance(
        value,
        bytes,
    ):

        return {
            "__bytes__":
                value.hex()
        }

    return value


def snapshot_year_rows(
    con,
    *,
    tables: list[str],
    school_ids: list[int],
    year_ids: list[int],
):

    payload = {}

    counts = {}


    if (
        not school_ids
        or not year_ids
    ):

        raw = json.dumps(
            {},
            sort_keys=True,
        )

        return (
            hashlib.sha256(
                raw.encode()
            ).hexdigest(),
            {},
        )


    for table in tables:

        info = con.execute(
            "PRAGMA table_info("
            + qident(table)
            + ")"
        ).fetchall()


        columns = [
            str(x[1])
            for x in info
        ]


        sql = (
            "SELECT * FROM "
            + qident(table)
            + " WHERE school_id IN ("
            + markers(
                len(school_ids)
            )
            + ")"
            + " AND school_year_id IN ("
            + markers(
                len(year_ids)
            )
            + ")"
        )


        rows = con.execute(
            sql,
            [
                *school_ids,
                *year_ids,
            ],
        ).fetchall()


        normalized_rows = []


        for row in rows:

            values = [
                encode_value(
                    row[col]
                )
                for col in columns
            ]

            normalized_rows.append(
                values
            )


        normalized_rows.sort(
            key=lambda x:
                json.dumps(
                    x,
                    ensure_ascii=False,
                    sort_keys=True,
                    default=str,
                )
        )


        payload[
            table
        ] = {
            "columns":
                columns,

            "rows":
                normalized_rows,
        }


        counts[
            table
        ] = len(
            normalized_rows
        )


    raw = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(
            ",",
            ":",
        ),
        default=str,
    ).encode(
        "utf-8"
    )


    return (
        hashlib.sha256(
            raw
        ).hexdigest(),
        counts,
    )


def residual_by_table(
    con,
    *,
    tables: list[str],
    source_ids: list[int],
    move_year_ids: list[int],
):

    result = {}


    if (
        not source_ids
        or not move_year_ids
    ):

        return result


    for table in tables:

        count = int(
            con.execute(
                (
                    "SELECT COUNT(*) FROM "
                    + qident(table)
                    + " WHERE school_id IN ("
                    + markers(
                        len(source_ids)
                    )
                    + ")"
                    + " AND school_year_id IN ("
                    + markers(
                        len(move_year_ids)
                    )
                    + ")"
                ),
                [
                    *source_ids,
                    *move_year_ids,
                ],
            ).fetchone()[0]
            or 0
        )


        if count:

            result[
                table
            ] = count


    return result


def school_rows(
    con,
    ids: list[int],
):

    if not ids:
        return []


    return [
        dict(x)
        for x in con.execute(
            (
                "SELECT "
                "id,code,name,commune_id,is_active "
                "FROM schools "
                "WHERE id IN ("
                + markers(
                    len(ids)
                )
                + ") "
                "ORDER BY id"
            ),
            ids,
        ).fetchall()
    ]


def active_source_count(
    con,
    source_ids: list[int],
) -> int:

    if not source_ids:
        return 0


    return int(
        con.execute(
            (
                "SELECT COUNT(*) "
                "FROM schools "
                "WHERE id IN ("
                + markers(
                    len(source_ids)
                )
                + ") "
                "AND is_active=1"
            ),
            source_ids,
        ).fetchone()[0]
        or 0
    )


def active_target_count(
    con,
    target_ids: list[int],
) -> int:

    if not target_ids:
        return 0


    return int(
        con.execute(
            (
                "SELECT COUNT(*) "
                "FROM schools "
                "WHERE id IN ("
                + markers(
                    len(target_ids)
                )
                + ") "
                "AND is_active=1"
            ),
            target_ids,
        ).fetchone()[0]
        or 0
    )


def source_user_counts(
    con,
    source_ids: list[int],
):

    if not source_ids:

        return {
            "all_users":
                0,

            "active_users":
                0,

            "regular_users":
                0,

            "active_school_logins":
                0,
        }


    sql_base = (
        " FROM users "
        "WHERE school_id IN ("
        + markers(
            len(source_ids)
        )
        + ")"
    )


    all_users = int(
        con.execute(
            "SELECT COUNT(*)"
            + sql_base,
            source_ids,
        ).fetchone()[0]
        or 0
    )


    active_users = int(
        con.execute(
            "SELECT COUNT(*)"
            + sql_base
            + " AND is_active=1",
            source_ids,
        ).fetchone()[0]
        or 0
    )


    regular_users = int(
        con.execute(
            "SELECT COUNT(*)"
            + sql_base
            + " AND username NOT LIKE 'truong_%'",
            source_ids,
        ).fetchone()[0]
        or 0
    )


    active_school_logins = int(
        con.execute(
            "SELECT COUNT(*)"
            + sql_base
            + " AND username LIKE 'truong_%'"
              " AND is_active=1",
            source_ids,
        ).fetchone()[0]
        or 0
    )


    return {
        "all_users":
            all_users,

        "active_users":
            active_users,

        "regular_users":
            regular_users,

        "active_school_logins":
            active_school_logins,
    }


def staff_breakdown(
    con,
    *,
    school_id: int,
    year_id: int = 2,
):

    rows = con.execute(
        """
        SELECT
            staff_member_id,
            position_group
        FROM staff_year_records
        WHERE school_id=?
          AND school_year_id=?
          AND is_active=1
        ORDER BY id
        """,
        (
            int(school_id),
            int(year_id),
        ),
    ).fetchall()


    groups = Counter(
        canonical_staff_group(
            row["position_group"]
        )
        for row in rows
    )


    distinct_staff = {
        int(row["staff_member_id"])
        for row in rows
        if row[
            "staff_member_id"
        ] is not None
    }


    return {
        "TOTAL_ROWS":
            len(rows),

        "DISTINCT_STAFF":
            len(
                distinct_staff
            ),

        "CBQL":
            int(
                groups.get(
                    "CBQL",
                    0,
                )
            ),

        "GIAO_VIEN":
            int(
                groups.get(
                    "GIAO_VIEN",
                    0,
                )
            ),

        "NHAN_VIEN":
            int(
                groups.get(
                    "NHAN_VIEN",
                    0,
                )
            ),

        "OTHER": {
            key: int(value)
            for key, value
            in sorted(
                groups.items()
            )
            if key not in {
                "CBQL",
                "GIAO_VIEN",
                "NHAN_VIEN",
            }
        },
    }


def duplicate_staff(
    con,
    *,
    school_id: int,
    year_id: int = 2,
):

    rows = con.execute(
        """
        SELECT
            staff_member_id,
            COUNT(*) AS n
        FROM staff_year_records
        WHERE school_id=?
          AND school_year_id=?
          AND is_active=1
          AND staff_member_id IS NOT NULL
        GROUP BY staff_member_id
        HAVING COUNT(*) > 1
        ORDER BY staff_member_id
        """,
        (
            int(school_id),
            int(year_id),
        ),
    ).fetchall()


    return [
        {
            "staff_member_id":
                int(
                    x["staff_member_id"]
                ),

            "rows":
                int(
                    x["n"]
                ),
        }
        for x in rows
    ]


def cross_target_staff_duplicates(
    con,
    target_ids: list[int],
):

    if not target_ids:
        return {}


    rows = con.execute(
        (
            "SELECT "
            "staff_member_id,"
            "GROUP_CONCAT(DISTINCT school_id) AS schools,"
            "COUNT(DISTINCT school_id) AS school_count "
            "FROM staff_year_records "
            "WHERE school_year_id=2 "
            "AND is_active=1 "
            "AND staff_member_id IS NOT NULL "
            "AND school_id IN ("
            + markers(
                len(target_ids)
            )
            + ") "
            "GROUP BY staff_member_id "
            "HAVING COUNT(DISTINCT school_id)>1 "
            "ORDER BY staff_member_id"
        ),
        target_ids,
    ).fetchall()


    return {
        str(
            int(
                row["staff_member_id"]
            )
        ):
        sorted(
            int(x)
            for x in str(
                row["schools"]
                or ""
            ).split(",")
            if str(x).strip()
        )
        for row in rows
    }


# ============================================================
# START
# ============================================================

print("=" * 148)
print(
    "THCS - DRY-RUN RAM 13 PHUONG AN READY"
)
print(
    "MO PHONG TUAN TU - KHONG GHI DATABASE THAT"
)
print("=" * 148)

print(
    "DB THAT       : READ-ONLY"
)

print(
    "DB RAM        : DUOC MO PHONG"
)

print(
    "SOURCE/LOCK   : KHONG SUA"
)

print(
    "RESOLUTION    : KHONG SUA"
)

print(
    "BATCH LOG     : KHONG TAO"
)

print(
    "SAP NHAP THAT : CHUA CHAY"
)


# ============================================================
# 1. FILE HASH GATE
# ============================================================

print()
print("=" * 148)
print("1. HASH + SERVER GATE")
print("=" * 148)


PATHS = {
    "db":
        DB,

    "level_service":
        LEVEL_SERVICE,

    "engine":
        ENGINE_FILE,

    "lock":
        LOCK,

    "roster":
        ROSTER,

    "resolution":
        RESOLUTION,

    "history":
        HISTORY,
}


before_hashes = {}


for key, path in PATHS.items():

    if not path.exists():

        raise RuntimeError(
            "DUNG: khong tim thay "
            + str(path)
        )


    value = sha256(
        path
    )

    before_hashes[
        key
    ] = value


    print(
        f"{key:14s} = {value}"
    )


    if value != EXPECTED[key]:

        raise RuntimeError(
            "DUNG: "
            + key
            + " khong dung nen da khoa."
        )


for suffix in (
    "-wal",
    "-journal",
):

    path = Path(
        str(DB)
        + suffix
    )


    size = (
        path.stat().st_size
        if path.exists()
        else 0
    )


    print(
        path.name,
        "=",
        size,
    )


    if size > 0:

        raise RuntimeError(
            "DUNG: Uvicorn/server chua dung."
        )


# ============================================================
# 2. IMPORT ENGINE / BATCH
# ============================================================

from app.services import (
    school_merger_level_batch_service
    as svc
)

from app.services import (
    school_merger_service
    as engine
)


if svc.engine is not engine:

    raise RuntimeError(
        "DUNG: level batch service "
        "khong dung cung merger engine."
    )


# ============================================================
# 3. BATCH GATE
# ============================================================

print()
print("=" * 148)
print("2. BATCH GATE")
print("=" * 148)


preview = (
    svc.build_level_batch_preview(
        school_year_id=2,
        level_code="THCS",
    )
)


print(
    "counts                =",
    preview.get(
        "counts"
    ),
)

print(
    "candidate_count       =",
    preview.get(
        "candidate_count"
    ),
)

print(
    "effective_block_count =",
    preview.get(
        "effective_block_count"
    ),
)

print(
    "ready_for_execution   =",
    preview.get(
        "ready_for_execution"
    ),
)

print(
    "overlap_items         =",
    preview.get(
        "overlap_items"
    ),
)

print(
    "extra_blockers        =",
    preview.get(
        "extra_blockers"
    ),
)

print(
    "previous_batch        =",
    bool(
        preview.get(
            "previous_batch"
        )
    ),
)

print(
    "batch_fingerprint     =",
    preview.get(
        "batch_fingerprint"
    ),
)


if (
    preview.get(
        "counts"
    )
    != {
        "KEEP": 36,
        "DONE": 84,
        "READY": 13,
        "BLOCK": 0,
    }
):

    raise RuntimeError(
        "DUNG: counts khong con "
        "36/84/13/0."
    )


if int(
    preview.get(
        "candidate_count"
    )
    or 0
) != 13:

    raise RuntimeError(
        "DUNG: candidate_count != 13."
    )


if int(
    preview.get(
        "effective_block_count"
    )
    or 0
) != 0:

    raise RuntimeError(
        "DUNG: van con blocker."
    )


if (
    preview.get(
        "ready_for_execution"
    )
    is not True
):

    raise RuntimeError(
        "DUNG: batch chua READY."
    )


if (
    preview.get(
        "previous_batch"
    )
    is not None
):

    raise RuntimeError(
        "DUNG: THCS da co batch log truoc do."
    )


if (
    preview.get(
        "overlap_items"
    )
    or []
):

    raise RuntimeError(
        "DUNG: 13 READY co overlap."
    )


if (
    preview.get(
        "extra_blockers"
    )
    or []
):

    raise RuntimeError(
        "DUNG: preview co extra blocker."
    )


candidates = [
    dict(x)
    for x in (
        preview.get(
            "candidates"
        )
        or []
    )
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


if candidate_ops != EXPECTED_READY_OPS:

    print(
        "EXPECTED =",
        sorted(
            EXPECTED_READY_OPS
        ),
    )

    print(
        "CURRENT  =",
        sorted(
            candidate_ops
        ),
    )

    raise RuntimeError(
        "DUNG: tap 13 READY operation "
        "khong khop tuyet doi."
    )


# ============================================================
# 4. LOCK DETAIL 13 CANDIDATES
# ============================================================

print()
print("=" * 148)
print("3. KHOA CHI TIET 13 READY")
print("=" * 148)


details = []

database_fingerprints = set()


for index, item in enumerate(
    candidates,
    start=1,
):

    pid = str(
        item.get(
            "plan_id"
        )
        or ""
    )

    op = str(
        item.get(
            "qd3805_operation_id"
        )
        or ""
    )


    detail = (
        svc.build_official_plan_impact_preview(
            pid
        )
    )


    source_schools = [
        dict(x)
        for x in (
            detail.get(
                "source_schools"
            )
            or []
        )
    ]


    target_school = dict(
        detail.get(
            "target_school"
        )
        or {}
    )


    source_ids = sorted(
        int(x["id"])
        for x in source_schools
        if x.get("id")
        is not None
    )


    target_id = int(
        target_school.get(
            "id"
        )
        or 0
    )


    detail_checks = {
        "keep_only_false":
            not bool(
                detail.get(
                    "keep_only"
                )
            ),

        "safe_for_future_execution":
            bool(
                detail.get(
                    "safe_for_future_execution"
                )
            ),

        "simulation_ok":
            bool(
                detail.get(
                    "simulation_ok"
                )
            ),

        "v41_state_check_ok":
            bool(
                detail.get(
                    "v41_state_check_ok"
                )
            ),

        "v43_source_check_ok":
            bool(
                detail.get(
                    "v43_source_check_ok"
                )
            ),

        "completed_operation_false":
            not bool(
                detail.get(
                    "completed_operation"
                )
            ),

        "blockers_zero":
            not bool(
                detail.get(
                    "blockers"
                )
                or []
            ),

        "source_present":
            bool(
                source_ids
            ),

        "target_present":
            target_id > 0,
    }


    if not all(
        detail_checks.values()
    ):

        print(
            json.dumps(
                {
                    "operation":
                        op,

                    "plan_id":
                        pid,

                    "checks":
                        detail_checks,

                    "blockers":
                        detail.get(
                            "blockers"
                        ),

                    "warnings":
                        detail.get(
                            "warnings"
                        ),
                },
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        )

        raise RuntimeError(
            "DUNG: candidate "
            + op
            + " khong dat detail gate."
        )


    if (
        set(
            source_ids
            + [target_id]
        )
        & FORBIDDEN_SCHOOL_IDS
    ):

        raise RuntimeError(
            "DUNG: "
            + op
            + " cham vao Nghi Huong/"
              "Nghi Hoa/Nghi Van da khoa."
        )


    database_fingerprints.add(
        str(
            detail.get(
                "database_fingerprint"
            )
            or ""
        )
    )


    audit = dict(
        detail.get(
            "source_audit"
        )
        or {}
    )


    if (
        audit
        and audit.get(
            "pass"
        )
        is not True
    ):

        raise RuntimeError(
            "DUNG: source audit "
            + op
            + " khong PASS."
        )


    print()
    print(
        "-" * 148
    )

    print(
        f"[{index}/13] {op} | {pid}"
    )

    print(
        "Xa/phuong:",
        item.get(
            "commune"
        ),
    )


    print("Nguon:")

    for school in source_schools:

        print(
            "  - id=",
            school.get("id"),
            "| ma=",
            school.get("code"),
            "|",
            school.get("name"),
        )


    print(
        "Dich:",
        "id=",
        target_school.get("id"),
        "| ma=",
        target_school.get("code"),
        "|",
        target_school.get("name"),
    )


    print(
        "Detail checks =",
        detail_checks,
    )


    print(
        "Preview summary =",
        detail.get(
            "summary"
        ),
    )


    print(
        "Preview fingerprint =",
        detail.get(
            "fingerprint"
        ),
    )


    if audit:

        print(
            "Source audit:"
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
                "| eligible=",
                check.get(
                    "active_db_eligible"
                ),
                "| PASS=",
                check.get(
                    "pass"
                ),
            )


    details.append({
        "index":
            index,

        "operation_id":
            op,

        "plan_id":
            pid,

        "source_ids":
            source_ids,

        "source_schools":
            source_schools,

        "target_id":
            target_id,

        "target_school":
            target_school,

        "detail":
            detail,
    })


if len(
    database_fingerprints
) != 1:

    raise RuntimeError(
        "DUNG: 13 detail khong cung "
        "mot database fingerprint."
    )


# ============================================================
# 5. INDEPENDENT OVERLAP GATE
# ============================================================

used_school = {}

all_source_ids = []

all_target_ids = []


for item in details:

    pid = item[
        "plan_id"
    ]


    ids = [
        *item[
            "source_ids"
        ],
        item[
            "target_id"
        ],
    ]


    for sid in ids:

        used_school.setdefault(
            int(sid),
            [],
        ).append(
            pid
        )


    all_source_ids.extend(
        item[
            "source_ids"
        ]
    )

    all_target_ids.append(
        item[
            "target_id"
        ]
    )


overlap = {
    sid: pids
    for sid, pids
    in used_school.items()
    if len(
        set(pids)
    ) > 1
}


if overlap:

    raise RuntimeError(
        "DUNG: independent overlap = "
        + repr(
            overlap
        )
    )


all_source_ids = sorted(
    set(
        all_source_ids
    )
)

all_target_ids = sorted(
    set(
        all_target_ids
    )
)

all_involved_ids = sorted(
    set(
        all_source_ids
        + all_target_ids
    )
)


print()
print("=" * 148)
print("4. PHAM VI 13 PHUONG AN")
print("=" * 148)

print(
    "unique sources =",
    len(
        all_source_ids
    ),
)

print(
    "unique targets =",
    len(
        all_target_ids
    ),
)

print(
    "overlap        =",
    overlap,
)

print(
    "forbidden hit  =",
    sorted(
        set(
            all_involved_ids
        )
        & FORBIDDEN_SCHOOL_IDS
    ),
)


# ============================================================
# 6. REAL DB READ-ONLY HEALTH
# ============================================================

real = connect_read_only()


try:

    year = real.execute(
        """
        SELECT
            id,
            code,
            name
        FROM school_years
        WHERE id=2
        """
    ).fetchone()


    if (
        year is None
        or str(
            year["code"]
            or ""
        ).strip()
        != "2026-2027"
    ):

        raise RuntimeError(
            "DUNG: school_year_id=2 "
            "khong phai 2026-2027."
        )


    integrity_before = str(
        real.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]
    )


    fk_before = real.execute(
        "PRAGMA foreign_key_check"
    ).fetchall()


    print()
    print("=" * 148)
    print("5. DATABASE THAT - READ ONLY")
    print("=" * 148)

    print(
        "year      =",
        dict(year),
    )

    print(
        "integrity =",
        integrity_before,
    )

    print(
        "FK        =",
        len(
            fk_before
        ),
    )


    if (
        integrity_before.lower()
        != "ok"
        or fk_before
    ):

        raise RuntimeError(
            "DUNG: DB that integrity/FK FAIL."
        )


    # ========================================================
    # 7. COPY TO RAM ONCE
    # ========================================================

    print()
    print("=" * 148)
    print("6. SAO CHEP DB VAO RAM")
    print("=" * 148)


    mem = sqlite3.connect(
        ":memory:",
        factory=SimulationConnection,
    )

    mem.row_factory = sqlite3.Row


    real.backup(
        mem
    )


finally:

    real.close()


mem.execute(
    "PRAGMA foreign_keys=ON"
)


move_year_ids, past_year_ids = (
    engine._year_scope_ids(
        mem,
        2,
    )
)


previous_year_id = (
    engine._previous_year_id(
        mem,
        2,
    )
)


print(
    "MOVE years =",
    move_year_ids,
)

print(
    "PAST years =",
    past_year_ids,
)

print(
    "PREVIOUS   =",
    previous_year_id,
)


if (
    move_year_ids
    != [2, 8]
):

    mem.close()

    raise RuntimeError(
        "DUNG: CURRENT+FUTURE "
        "khong dung [2,8]."
    )


if (
    previous_year_id
    != 1
):

    mem.close()

    raise RuntimeError(
        "DUNG: previous year "
        "khong phai id=1."
    )


tables = year_aware_tables(
    mem
)


past_hash_before, past_counts_before = (
    snapshot_year_rows(
        mem,
        tables=tables,
        school_ids=all_involved_ids,
        year_ids=past_year_ids,
    )
)


cross_target_before = (
    cross_target_staff_duplicates(
        mem,
        all_target_ids,
    )
)


print(
    "year-aware tables =",
    len(tables),
)

print(
    "PAST hash before  =",
    past_hash_before,
)

print(
    "cross-target staff duplicates before =",
    cross_target_before,
)


# ============================================================
# 8. SIMULATE 13 SEQUENTIALLY
# ============================================================

print()
print("=" * 148)
print("7. MO PHONG TUAN TU 13 PHUONG AN")
print("=" * 148)


result_rows = []

error_rows = []


mem.execute(
    "BEGIN"
)


try:

    for item in details:

        idx = int(
            item[
                "index"
            ]
        )

        op = item[
            "operation_id"
        ]

        pid = item[
            "plan_id"
        ]

        source_ids = list(
            item[
                "source_ids"
            ]
        )

        target_id = int(
            item[
                "target_id"
            ]
        )


        print()
        print(
            "-" * 148
        )

        print(
            f"[{idx}/13] {op} | {pid}"
        )


        source_staff_before = {
            str(sid):
                staff_breakdown(
                    mem,
                    school_id=sid,
                    year_id=2,
                )
            for sid in source_ids
        }


        target_staff_before = (
            staff_breakdown(
                mem,
                school_id=target_id,
                year_id=2,
            )
        )


        print(
            "staff truoc - sources =",
            json.dumps(
                source_staff_before,
                ensure_ascii=False,
            ),
        )


        print(
            "staff truoc - target  =",
            json.dumps(
                target_staff_before,
                ensure_ascii=False,
            ),
        )


        savepoint = (
            "thcs13_"
            + str(idx)
        )


        mem.execute(
            "SAVEPOINT "
            + savepoint
        )


        try:

            (
                checked_target,
                checked_sources,
                selection_blockers,
                selection_warnings,
            ) = engine._validate_selection(
                mem,
                selected_year_id=2,
                target_school_id=target_id,
                source_ids=source_ids,
                require_active_sources=True,
            )


            if selection_blockers:

                raise RuntimeError(
                    "Selection blocker: "
                    + " | ".join(
                        str(x)
                        for x
                        in selection_blockers
                    )
                )


            result = engine._apply_merge(
                mem,
                selected_year_id=2,
                previous_year_id=1,
                target_school_id=target_id,
                source_ids=source_ids,
                actor_user_id=None,
                backup_name=(
                    "THCS-13-RAM-DRY-RUN"
                ),
                record_audit=False,
            )


            residual = (
                residual_by_table(
                    mem,
                    tables=tables,
                    source_ids=source_ids,
                    move_year_ids=move_year_ids,
                )
            )


            active_sources = (
                active_source_count(
                    mem,
                    source_ids,
                )
            )


            active_target = (
                active_target_count(
                    mem,
                    [target_id],
                )
            )


            users_after = (
                source_user_counts(
                    mem,
                    source_ids,
                )
            )


            staff_after = (
                staff_breakdown(
                    mem,
                    school_id=target_id,
                    year_id=2,
                )
            )


            staff_dups = (
                duplicate_staff(
                    mem,
                    school_id=target_id,
                    year_id=2,
                )
            )


            checks = {
                "source_inactive":
                    active_sources == 0,

                "target_active":
                    active_target == 1,

                "current_future_residual_zero":
                    not bool(
                        residual
                    ),

                "active_users_source_zero":
                    int(
                        users_after[
                            "active_users"
                        ]
                    )
                    == 0,

                "regular_users_source_zero":
                    int(
                        users_after[
                            "regular_users"
                        ]
                    )
                    == 0,

                "active_school_login_zero":
                    int(
                        users_after[
                            "active_school_logins"
                        ]
                    )
                    == 0,

                "staff_duplicate_zero":
                    not bool(
                        staff_dups
                    ),
            }


            if not all(
                checks.values()
            ):

                raise RuntimeError(
                    "Post-check FAIL: "
                    + json.dumps(
                        {
                            "checks":
                                checks,

                            "residual":
                                residual,

                            "users":
                                users_after,

                            "staff_duplicates":
                                staff_dups,
                        },
                        ensure_ascii=False,
                        default=str,
                    )
                )


            # Chỉ release sau khi hậu kiểm riêng đã PASS.
            mem.execute(
                "RELEASE SAVEPOINT "
                + savepoint
            )


            direct_rows = sum(
                int(
                    x.get(
                        "rows"
                    )
                    or 0
                )
                for x in (
                    result.get(
                        "direct_moves"
                    )
                    or []
                )
            )


            no_year_rows = sum(
                int(
                    x.get(
                        "rows"
                    )
                    or 0
                )
                for x in (
                    result.get(
                        "no_year_moves"
                    )
                    or []
                )
            )


            print(
                "staff sau - target   =",
                json.dumps(
                    staff_after,
                    ensure_ascii=False,
                ),
            )


            print(
                "direct rows moved    =",
                direct_rows,
            )

            print(
                "no-year rows moved   =",
                no_year_rows,
            )

            print(
                "staff rollover tao   =",
                int(
                    result.get(
                        "staff_rollover_created"
                    )
                    or 0
                ),
            )

            print(
                "users moved          =",
                int(
                    result.get(
                        "users_moved"
                    )
                    or 0
                ),
            )

            print(
                "source login khoa    =",
                int(
                    result.get(
                        "source_school_logins_disabled"
                    )
                    or 0
                ),
            )

            print(
                "source inactive      =",
                int(
                    result.get(
                        "sources_deactivated"
                    )
                    or 0
                ),
            )

            print(
                "residual sau         =",
                residual,
            )

            print(
                "users tai source sau =",
                users_after,
            )

            print(
                "duplicate staff      =",
                staff_dups,
            )

            print(
                "CHECK                =",
                checks,
            )


            result_rows.append({
                "operation_id":
                    op,

                "plan_id":
                    pid,

                "sources":
                    source_ids,

                "target":
                    target_id,

                "result":
                    "PASS",

                "direct_rows":
                    direct_rows,

                "no_year_rows":
                    no_year_rows,

                "staff_rollover_created":
                    int(
                        result.get(
                            "staff_rollover_created"
                        )
                        or 0
                    ),

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

                "staff_after":
                    staff_after,
            })


        except Exception as exc:

            try:

                mem.execute(
                    "ROLLBACK TO SAVEPOINT "
                    + savepoint
                )

            finally:

                mem.execute(
                    "RELEASE SAVEPOINT "
                    + savepoint
                )


            error_rows.append({
                "operation_id":
                    op,

                "plan_id":
                    pid,

                "error":
                    repr(
                        exc
                    ),
            })


            print(
                "FAIL =",
                repr(
                    exc
                ),
            )


    # ========================================================
    # 9. GLOBAL RAM POSTCHECK
    # ========================================================

    print()
    print("=" * 148)
    print("8. HAU KIEM TONG CUOI TREN RAM")
    print("=" * 148)


    past_hash_after, past_counts_after = (
        snapshot_year_rows(
            mem,
            tables=tables,
            school_ids=all_involved_ids,
            year_ids=past_year_ids,
        )
    )


    global_residual = (
        residual_by_table(
            mem,
            tables=tables,
            source_ids=all_source_ids,
            move_year_ids=move_year_ids,
        )
    )


    active_sources_after = (
        active_source_count(
            mem,
            all_source_ids,
        )
    )


    active_targets_after = (
        active_target_count(
            mem,
            all_target_ids,
        )
    )


    all_source_users_after = (
        source_user_counts(
            mem,
            all_source_ids,
        )
    )


    target_staff_duplicates = {}


    for target_id in all_target_ids:

        duplicates = (
            duplicate_staff(
                mem,
                school_id=target_id,
                year_id=2,
            )
        )

        if duplicates:

            target_staff_duplicates[
                str(target_id)
            ] = duplicates


    cross_target_after = (
        cross_target_staff_duplicates(
            mem,
            all_target_ids,
        )
    )


    new_cross_target_duplicates = {
        staff_id:
            schools
        for staff_id, schools
        in cross_target_after.items()
        if (
            staff_id
            not in cross_target_before
            or cross_target_before[
                staff_id
            ] != schools
        )
    }


    ram_integrity = (
        real_integrity(
            mem
        )
    )


    ram_fk = (
        real_fk(
            mem
        )
    )


    pass_count = sum(
        1
        for x in result_rows
        if x[
            "result"
        ] == "PASS"
    )


    past_exact = (
        past_hash_before
        == past_hash_after
        and past_counts_before
        == past_counts_after
    )


    print(
        "simulation PASS       =",
        str(
            pass_count
        )
        + "/13",
    )

    print(
        "simulation errors     =",
        len(
            error_rows
        ),
    )

    print(
        "CURRENT/FUTURE source =",
        global_residual,
    )

    print(
        "PAST hash before      =",
        past_hash_before,
    )

    print(
        "PAST hash after       =",
        past_hash_after,
    )

    print(
        "PAST exact            =",
        past_exact,
    )

    print(
        "active sources after  =",
        active_sources_after,
    )

    print(
        "active targets after  =",
        str(
            active_targets_after
        )
        + "/"
        + str(
            len(
                all_target_ids
            )
        ),
    )

    print(
        "source users after    =",
        all_source_users_after,
    )

    print(
        "target staff duplicate=",
        target_staff_duplicates,
    )

    print(
        "cross-target before   =",
        cross_target_before,
    )

    print(
        "cross-target after    =",
        cross_target_after,
    )

    print(
        "NEW cross-target dup  =",
        new_cross_target_duplicates,
    )

    print(
        "RAM integrity         =",
        ram_integrity,
    )

    print(
        "RAM FK                =",
        len(
            ram_fk
        ),
    )


    ram_pass = (
        pass_count == 13
        and not error_rows
        and not global_residual
        and past_exact
        and active_sources_after == 0
        and active_targets_after
            == len(
                all_target_ids
            )
        and int(
            all_source_users_after[
                "active_users"
            ]
        ) == 0
        and int(
            all_source_users_after[
                "regular_users"
            ]
        ) == 0
        and int(
            all_source_users_after[
                "active_school_logins"
            ]
        ) == 0
        and not target_staff_duplicates
        and not new_cross_target_duplicates
        and ram_integrity.lower()
            == "ok"
        and len(
            ram_fk
        ) == 0
    )


finally:

    # Không bao giờ commit bản RAM.
    try:

        mem.rollback()

    except Exception:
        pass


    try:

        mem.close()

    except Exception:
        pass


# ============================================================
# 10. REAL FILE IMMUTABILITY
# ============================================================

print()
print("=" * 148)
print("9. KIEM TRA FILE THAT SAU DRY-RUN")
print("=" * 148)


after_hashes = {
    key:
        sha256(path)
    for key, path
    in PATHS.items()
}


for key in PATHS:

    print(
        key,
        ":",
        before_hashes[
            key
        ],
        "->",
        after_hashes[
            key
        ],
    )


    if (
        before_hashes[
            key
        ]
        != after_hashes[
            key
        ]
    ):

        raise RuntimeError(
            "DUNG: file that "
            + key
            + " bi thay doi."
        )


# ============================================================
# 11. REAL BATCH STILL SAME
# ============================================================

print()
print("=" * 148)
print("10. BATCH THAT SAU DRY-RUN")
print("=" * 148)


preview_after = (
    svc.build_level_batch_preview(
        school_year_id=2,
        level_code="THCS",
    )
)


fingerprint_before = str(
    preview.get(
        "batch_fingerprint"
    )
    or ""
)


fingerprint_after = str(
    preview_after.get(
        "batch_fingerprint"
    )
    or ""
)


print(
    "counts                =",
    preview_after.get(
        "counts"
    ),
)

print(
    "candidate_count       =",
    preview_after.get(
        "candidate_count"
    ),
)

print(
    "effective_block_count =",
    preview_after.get(
        "effective_block_count"
    ),
)

print(
    "ready_for_execution   =",
    preview_after.get(
        "ready_for_execution"
    ),
)

print(
    "previous_batch        =",
    bool(
        preview_after.get(
            "previous_batch"
        )
    ),
)

print(
    "batch fingerprint same=",
    fingerprint_before
    == fingerprint_after,
)


batch_stable = (
    preview_after.get(
        "counts"
    )
    == {
        "KEEP": 36,
        "DONE": 84,
        "READY": 13,
        "BLOCK": 0,
    }
    and int(
        preview_after.get(
            "candidate_count"
        )
        or 0
    ) == 13
    and int(
        preview_after.get(
            "effective_block_count"
        )
        or 0
    ) == 0
    and preview_after.get(
        "ready_for_execution"
    )
    is True
    and preview_after.get(
        "previous_batch"
    )
    is None
    and fingerprint_before
        == fingerprint_after
)


# ============================================================
# FINAL
# ============================================================

print()
print("=" * 148)


if (
    ram_pass
    and batch_stable
):

    print(
        "DRY-RUN 13 PHUONG AN THCS: PASS"
    )

    print("=" * 148)

    print(
        "Mo phong RAM          : 13/13 PASS"
    )

    print(
        "CURRENT/FUTURE source : residual = 0"
    )

    print(
        "PAST                  : GIU NGUYEN EXACT"
    )

    print(
        "Source schools        : INACTIVE tren RAM"
    )

    print(
        "Target schools        : ACTIVE tren RAM"
    )

    print(
        "Active users source   : 0 tren RAM"
    )

    print(
        "Duplicate staff target: 0"
    )

    print(
        "New cross-target dup  : 0"
    )

    print(
        "RAM integrity         : OK"
    )

    print(
        "RAM foreign key       : 0"
    )

    print(
        "Database that         : KHONG THAY DOI"
    )

    print(
        "Service/Resolution    : KHONG THAY DOI"
    )

    print(
        "Batch fingerprint     : ON DINH"
    )

    print(
        "13 READY              : CHUA THUC HIEN THAT"
    )

    print(
        "19 XU LY RIENG        : KHONG TAC DONG"
    )

    print(
        "Nghi Huong            : GIU NGUYEN"
    )

    print()

    print(
        "READY_FOR_OFFICIAL_THCS_13=YES"
    )

    print(
        "BATCH_FINGERPRINT="
        + fingerprint_after
    )

else:

    print(
        "DRY-RUN 13 PHUONG AN THCS: FAIL"
    )

    print("=" * 148)

    print(
        "ram_pass     =",
        ram_pass,
    )

    print(
        "batch_stable =",
        batch_stable,
    )

    print(
        "errors       =",
        json.dumps(
            error_rows,
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
    )

    print()

    print(
        "READY_FOR_OFFICIAL_THCS_13=NO"
    )


print("=" * 148)


if not (
    ram_pass
    and batch_stable
):

    raise SystemExit(2)
