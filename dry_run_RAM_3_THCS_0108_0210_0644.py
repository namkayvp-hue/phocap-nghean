# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

sys.dont_write_bytecode = True

try:
    sys.stdout.reconfigure(
        encoding="utf-8",
        errors="replace",
    )
except Exception:
    pass


ROOT = Path(r"C:\PhoCap")

DB = ROOT / "data" / "phocap.db"

ENGINE_FILE = (
    ROOT
    / "app"
    / "services"
    / "school_merger_service.py"
)

SERVICE_FILE = (
    ROOT
    / "app"
    / "services"
    / "school_merger_level_batch_service.py"
)

RESOLUTION_FILE = (
    ROOT
    / "data"
    / "school_merger_registry"
    / "qd3805_thcs_resolution.json"
)

PLANS_FILE = (
    ROOT
    / "data"
    / "school_merger_approved_plans.json"
)


EXPECTED_SHA = {
    "db":
        "706279fe9cd63f9f01c4c3d7637f955534280b7b745e333b0b6943c2e64aed89",

    "engine":
        "414fb49a4c5f4fed7b571cc55df381678fe660cd8a675ecaa2f6fd70ebd7827a",

    "service":
        "9104fb99c78755e9eec86d090659b3a922834ff097d7292aa4d4b29e360a27f9",

    "resolution":
        "80469cbc9b118ee1ff54b95eb6af275704b0beb21107363ee63f5318b7b3c5f3",

    "plans":
        "4e2c5f044c48c57dda40fecc11f4e9f466f236aacc082f224536b1685cadb1fc",
}


YEAR_ID = 2
PREVIOUS_YEAR_ID = 1


CASES = [
    {
        "op":
            "QD3805-OP-0108",

        "source_id":
            1578,

        "source_code":
            "40422510",

        "source_name":
            "Trường THCS Mậu Đôn",

        "target_id":
            1577,

        "target_code":
            "40422504",

        "target_name":
            "PTDT Bán trú THCS Thạch Ngàn",

        "expected": {
            "TOTAL": 61,
            "QUAN_LY": 6,
            "GIAO_VIEN": 50,
            "NHAN_VIEN": 5,
            "EXCLUDED": 0,
        },

        "business_note":
            "QĐ3805 có ghi 'Tách: Trường THCS Mậu Đôn'; "
            "dry-run này chỉ mô phỏng kỹ thuật toàn trường.",
    },

    {
        "op":
            "QD3805-OP-0210",

        "source_id":
            1733,

        "source_code":
            "40427505",

        "source_name":
            "THCS Thượng Sơn",

        "target_id":
            1734,

        "target_code":
            "40427510",

        "target_name":
            "THCS Trần Phú",

        "expected": {
            "TOTAL": 89,
            "QUAN_LY": 4,
            "GIAO_VIEN": 74,
            "NHAN_VIEN": 11,
            "EXCLUDED": 0,
        },

        "business_note":
            "Chỉ Trần Phú + Thượng Sơn; "
            "không bao gồm orphan THCS Văn Hiến.",
    },

    {
        "op":
            "QD3805-OP-0644",

        "source_id":
            1748,

        "source_code":
            "40418519",

        "source_name":
            "THCS Yên Hòa",

        "target_id":
            1747,

        "target_code":
            "40418511",

        "target_name":
            "PTDTBT THCS Yên Thắng",

        "expected": {
            "TOTAL": 43,
            "QUAN_LY": 5,
            "GIAO_VIEN": 32,
            "NHAN_VIEN": 6,
            "EXCLUDED": 0,
        },

        "business_note":
            "Khóa alias PT DTBT Yên Hòa = THCS Yên Hòa id 1748.",
    },
]


WANTED = {
    x["op"]
    for x in CASES
}


def sha256(path: Path) -> str:

    h = hashlib.sha256()

    with path.open("rb") as f:

        for chunk in iter(
            lambda: f.read(1024 * 1024),
            b"",
        ):
            h.update(chunk)

    return h.hexdigest()


def qident(name: str) -> str:

    return (
        '"'
        + str(name).replace('"', '""')
        + '"'
    )


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


def school_row(
    con,
    school_id,
):

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
        (
            int(school_id),
        ),
    ).fetchone()

    return (
        dict(row)
        if row is not None
        else None
    )


def year_tables(con):

    result = []

    for row in con.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type='table'
          AND name NOT LIKE 'sqlite_%'
        ORDER BY name
        """
    ):

        table = str(
            row["name"]
        )

        cols = {
            str(x["name"])
            for x in con.execute(
                f"PRAGMA table_info({qident(table)})"
            ).fetchall()
        }

        if {
            "school_id",
            "school_year_id",
        }.issubset(cols):

            result.append(table)

    return result


def encode(value):

    if isinstance(value, bytes):

        return {
            "__bytes__":
                value.hex()
        }

    return value


def past_snapshot(
    con,
    school_ids,
    past_year_ids,
):

    payload = {}

    for table in year_tables(con):

        columns = [
            str(x["name"])
            for x in con.execute(
                f"PRAGMA table_info({qident(table)})"
            ).fetchall()
        ]

        rows = con.execute(
            (
                "SELECT * FROM "
                + qident(table)
                + " WHERE school_id IN ("
                + marks(len(school_ids))
                + ") "
                + "AND school_year_id IN ("
                + marks(len(past_year_ids))
                + ")"
            ),
            [
                *school_ids,
                *past_year_ids,
            ],
        ).fetchall()

        normalized = []

        for row in rows:

            normalized.append(
                [
                    encode(row[col])
                    for col in columns
                ]
            )

        normalized.sort(
            key=lambda x:
                json.dumps(
                    x,
                    ensure_ascii=False,
                    sort_keys=True,
                    default=str,
                )
        )

        payload[table] = {
            "columns":
                columns,

            "rows":
                normalized,
        }

    raw = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")

    return hashlib.sha256(
        raw
    ).hexdigest()


def residual(
    con,
    school_ids,
    move_year_ids,
):

    result = {}

    for table in year_tables(con):

        n = int(
            con.execute(
                (
                    "SELECT COUNT(*) FROM "
                    + qident(table)
                    + " WHERE school_id IN ("
                    + marks(len(school_ids))
                    + ") "
                    + "AND school_year_id IN ("
                    + marks(len(move_year_ids))
                    + ")"
                ),
                [
                    *school_ids,
                    *move_year_ids,
                ],
            ).fetchone()[0]
            or 0
        )

        if n:
            result[table] = n

    return result


def previous_engine_state(
    con,
    merger,
    school_ids,
):

    rows = con.execute(
        (
            "SELECT * "
            "FROM staff_year_records "
            "WHERE school_year_id=? "
            "AND school_id IN ("
            + marks(len(school_ids))
            + ") "
            "ORDER BY school_id,id"
        ),
        [
            PREVIOUS_YEAR_ID,
            *school_ids,
        ],
    ).fetchall()

    eligible_groups = Counter()

    eligible_ids = []

    excluded = []

    raw_ids = Counter()


    for row in rows:

        staff_id = int(
            row["staff_member_id"]
        )

        raw_ids[staff_id] += 1

        category = merger._classify_staff(
            row
        )

        if category == "CHUA_XAC_DINH":

            raise RuntimeError(
                "Không phân loại được "
                f"staff_member_id={staff_id}"
            )

        if merger._staff_inactive(row):

            excluded.append({
                "record_id":
                    int(row["id"]),

                "staff_member_id":
                    staff_id,

                "school_id":
                    int(row["school_id"]),

                "category":
                    category,

                "status_code":
                    (
                        row["status_code"]
                        if "status_code"
                        in row.keys()
                        else None
                    ),

                "source_status_label":
                    (
                        row["source_status_label"]
                        if "source_status_label"
                        in row.keys()
                        else None
                    ),
            })

            continue

        eligible_ids.append(
            staff_id
        )

        eligible_groups[
            category
        ] += 1


    duplicate = {
        k: v
        for k, v
        in raw_ids.items()
        if v > 1
    }


    return {
        "RAW":
            len(rows),

        "TOTAL":
            len(eligible_ids),

        "QUAN_LY":
            int(
                eligible_groups.get(
                    "QUAN_LY",
                    0,
                )
            ),

        "GIAO_VIEN":
            int(
                eligible_groups.get(
                    "GIAO_VIEN",
                    0,
                )
            ),

        "NHAN_VIEN":
            int(
                eligible_groups.get(
                    "NHAN_VIEN",
                    0,
                )
            ),

        "EXCLUDED":
            len(excluded),

        "ELIGIBLE_IDS":
            eligible_ids,

        "EXCLUDED_ROWS":
            excluded,

        "DUPLICATE":
            duplicate,
    }


def current_staff_state(
    con,
    merger,
    school_id,
):

    rows = con.execute(
        """
        SELECT *
        FROM staff_year_records
        WHERE school_id=?
          AND school_year_id=?
          AND is_active=1
        ORDER BY id
        """,
        (
            int(school_id),
            YEAR_ID,
        ),
    ).fetchall()

    groups = Counter()

    ids = []


    for row in rows:

        category = merger._classify_staff(
            row
        )

        groups[category] += 1

        if (
            row["staff_member_id"]
            is not None
        ):

            ids.append(
                int(
                    row["staff_member_id"]
                )
            )


    duplicate = {
        k: v
        for k, v
        in Counter(ids).items()
        if v > 1
    }


    return {
        "TOTAL":
            len(rows),

        "QUAN_LY":
            int(
                groups.get(
                    "QUAN_LY",
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

        "IDS":
            ids,

        "DUPLICATE":
            duplicate,
    }


def source_user_state(
    con,
    school_id,
):

    row = con.execute(
        """
        SELECT
            COUNT(*) AS total,

            SUM(
                CASE
                    WHEN is_active=1
                    THEN 1
                    ELSE 0
                END
            ) AS active,

            SUM(
                CASE
                    WHEN username LIKE 'truong_%'
                     AND is_active=1
                    THEN 1
                    ELSE 0
                END
            ) AS school_login

        FROM users

        WHERE school_id=?
        """,
        (
            int(school_id),
        ),
    ).fetchone()


    return {
        "total":
            int(row["total"] or 0),

        "active":
            int(row["active"] or 0),

        "school_login":
            int(row["school_login"] or 0),
    }


print("=" * 150)

print(
    "THCS - DRY-RUN RAM 3 PHUONG AN "
    "OP0108 / OP0210 / OP0644"
)

print(
    "KHONG GHI DATABASE THAT - "
    "KHONG SUA RESOLUTION - "
    "KHONG TAO BATCH"
)

print("=" * 150)


# ============================================================
# 1. HASH GATE
# ============================================================

print()
print("1. HASH GATE")
print("-" * 150)


PATHS = {
    "db":
        DB,

    "engine":
        ENGINE_FILE,

    "service":
        SERVICE_FILE,

    "resolution":
        RESOLUTION_FILE,

    "plans":
        PLANS_FILE,
}


before_hash = {}


for key, path in PATHS.items():

    if not path.exists():

        raise RuntimeError(
            f"Không tìm thấy {path}"
        )

    actual = sha256(path)

    before_hash[key] = actual

    print(
        f"{key:12s} = {actual}"
    )

    if actual != EXPECTED_SHA[key]:

        raise RuntimeError(
            "DUNG: "
            + key
            + " không đúng nền đã khóa."
        )


for suffix in (
    "-wal",
    "-journal",
):

    p = Path(
        str(DB) + suffix
    )

    size = (
        p.stat().st_size
        if p.exists()
        else 0
    )

    print(
        p.name,
        "=",
        size,
    )

    if size:

        raise RuntimeError(
            "DUNG: hãy dừng Uvicorn/server."
        )


# ============================================================
# 2. IMPORT ENGINE
# ============================================================

sys.path.insert(
    0,
    str(ROOT),
)

from app.services import (
    school_merger_service
    as merger
)

from app.services import (
    school_merger_level_batch_service
    as levelsvc
)


# ============================================================
# 3. SERVICE GATE
# ============================================================

preview = (
    levelsvc.build_level_batch_preview(
        school_year_id=YEAR_ID,
        level_code="THCS",
    )
)


print()
print("2. SERVICE GATE")
print("-" * 150)

print(
    "counts =",
    preview.get("counts"),
)

print(
    "candidate_count =",
    len(
        preview.get(
            "candidates"
        )
        or []
    ),
)

print(
    "effective_block_count =",
    preview.get(
        "effective_block_count"
    ),
)

print(
    "previous_batch =",
    bool(
        preview.get(
            "previous_batch"
        )
    ),
)

print(
    "ready_for_execution =",
    preview.get(
        "ready_for_execution"
    ),
)


if dict(
    preview.get("counts")
    or {}
) != {
    "KEEP": 36,
    "DONE": 101,
    "READY": 0,
    "BLOCK": 0,
}:

    raise RuntimeError(
        "DUNG: trạng thái service đã thay đổi."
    )


if len(
    preview.get(
        "candidates"
    )
    or []
) != 0:

    raise RuntimeError(
        "DUNG: xuất hiện candidate batch."
    )


if not bool(
    preview.get(
        "previous_batch"
    )
):

    raise RuntimeError(
        "DUNG: mất previous THCS batch."
    )


if bool(
    preview.get(
        "ready_for_execution"
    )
):

    raise RuntimeError(
        "DUNG: batch THCS lại được mở chạy."
    )


# ============================================================
# 4. RESOLUTION GATE
# ============================================================

resolution = json.loads(
    RESOLUTION_FILE.read_text(
        encoding="utf-8-sig"
    )
)


special = [
    x
    for x in (
        resolution.get(
            "special_same_level"
        )
        or []
    )
    if isinstance(x, dict)
]


special_counter = Counter(
    str(
        x.get(
            "operation_id"
        )
        or ""
    )
    for x in special
)


print()
print("3. RESOLUTION GATE")
print("-" * 150)


for op in sorted(WANTED):

    print(
        op,
        "| special=",
        special_counter[op],
    )

    if special_counter[op] != 1:

        raise RuntimeError(
            op
            + ": không còn đúng 1 special."
        )


# ============================================================
# 5. REAL DB READ ONLY
# ============================================================

real = connect_ro()

try:

    integrity = str(
        real.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]
    )

    fk = real.execute(
        "PRAGMA foreign_key_check"
    ).fetchall()


    print()
    print("4. DATABASE THAT - READ ONLY")
    print("-" * 150)

    print(
        "integrity =",
        integrity,
    )

    print(
        "FK        =",
        len(fk),
    )


    if (
        integrity.lower() != "ok"
        or fk
    ):

        raise RuntimeError(
            "DUNG: database health FAIL."
        )


    batch_table = str(
        levelsvc.BATCH_TABLE
    )

    official_table = str(
        levelsvc.OFFICIAL_EXECUTION_TABLE
    )


    batch_before = int(
        real.execute(
            (
                "SELECT COUNT(*) FROM "
                + qident(batch_table)
                + " WHERE school_year_id=? "
                  "AND level_code='THCS'"
            ),
            (
                YEAR_ID,
            ),
        ).fetchone()[0]
        or 0
    )


    if batch_before != 1:

        raise RuntimeError(
            "DUNG: THCS batch count != 1."
        )


    # --------------------------------------------
    # Lock danh tính 6 trường.
    # --------------------------------------------

    for case in CASES:

        source = school_row(
            real,
            case["source_id"],
        )

        target = school_row(
            real,
            case["target_id"],
        )


        print()
        print(
            case["op"]
        )

        print(
            "SOURCE =",
            source,
        )

        print(
            "TARGET =",
            target,
        )


        if (
            source is None
            or target is None
        ):

            raise RuntimeError(
                case["op"]
                + ": thiếu source/target."
            )


        if (
            str(source["code"])
            != case["source_code"]

            or str(source["name"])
            != case["source_name"]

            or int(
                source["is_active"]
                or 0
            ) != 1

            or str(target["code"])
            != case["target_code"]

            or str(target["name"])
            != case["target_name"]

            or int(
                target["is_active"]
                or 0
            ) != 1

            or int(
                source["commune_id"]
            )
            != int(
                target["commune_id"]
            )
        ):

            raise RuntimeError(
                case["op"]
                + ": danh tính/trạng thái sai."
            )


    # --------------------------------------------
    # Copy database thật sang RAM.
    # --------------------------------------------

    mem = sqlite3.connect(
        ":memory:"
    )

    mem.row_factory = sqlite3.Row

    mem.execute(
        "PRAGMA foreign_keys=ON"
    )

    real.backup(
        mem
    )


finally:

    real.close()


# ============================================================
# 6. YEAR SCOPE
# ============================================================

move_year_ids, past_year_ids = (
    merger._year_scope_ids(
        mem,
        YEAR_ID,
    )
)

previous_year_id = (
    merger._previous_year_id(
        mem,
        YEAR_ID,
    )
)


print()
print("5. YEAR SCOPE")
print("-" * 150)

print(
    "MOVE YEARS =",
    move_year_ids,
)

print(
    "PAST YEARS =",
    past_year_ids,
)

print(
    "PREVIOUS   =",
    previous_year_id,
)


if move_year_ids != [2, 8]:

    raise RuntimeError(
        "DUNG: MOVE YEARS phải là [2,8]."
    )


if previous_year_id != 1:

    raise RuntimeError(
        "DUNG: previous year phải là id=1."
    )


# ============================================================
# 7. PRECHECK STAFF / RESIDUAL
# ============================================================

print()
print("=" * 150)
print("6. PRECHECK 3 PHUONG AN")
print("=" * 150)


expected_by_op = {}

all_previous_eligible_ids = []


for case in CASES:

    op = case["op"]

    source_id = case[
        "source_id"
    ]

    target_id = case[
        "target_id"
    ]


    source_prev = previous_engine_state(
        mem,
        merger,
        [source_id],
    )

    target_prev = previous_engine_state(
        mem,
        merger,
        [target_id],
    )

    combined = previous_engine_state(
        mem,
        merger,
        [
            source_id,
            target_id,
        ],
    )


    print()
    print(op)

    print(
        "SOURCE PREVIOUS =",
        {
            k: v
            for k, v
            in source_prev.items()
            if k not in {
                "ELIGIBLE_IDS",
                "EXCLUDED_ROWS",
            }
        },
    )

    print(
        "TARGET PREVIOUS =",
        {
            k: v
            for k, v
            in target_prev.items()
            if k not in {
                "ELIGIBLE_IDS",
                "EXCLUDED_ROWS",
            }
        },
    )

    print(
        "COMBINED ENGINE EXPECTED =",
        {
            k: v
            for k, v
            in combined.items()
            if k not in {
                "ELIGIBLE_IDS",
                "EXCLUDED_ROWS",
            }
        },
    )

    print(
        "BUSINESS NOTE =",
        case[
            "business_note"
        ],
    )


    if combined["DUPLICATE"]:

        raise RuntimeError(
            op
            + ": trùng staff_member_id "
              "giữa source/target."
        )


    hard = case[
        "expected"
    ]


    for key in (
        "TOTAL",
        "QUAN_LY",
        "GIAO_VIEN",
        "NHAN_VIEN",
        "EXCLUDED",
    ):

        if combined[key] != hard[key]:

            raise RuntimeError(
                op
                + ": expected "
                + key
                + "="
                + str(
                    combined[key]
                )
                + "; cần "
                + str(
                    hard[key]
                )
            )


    source_current = (
        current_staff_state(
            mem,
            merger,
            source_id,
        )
    )

    target_current = (
        current_staff_state(
            mem,
            merger,
            target_id,
        )
    )


    print(
        "SOURCE CURRENT STAFF =",
        source_current,
    )

    print(
        "TARGET CURRENT STAFF =",
        target_current,
    )


    if (
        source_current[
            "TOTAL"
        ] != 0

        or target_current[
            "TOTAL"
        ] != 0
    ):

        raise RuntimeError(
            op
            + ": đã có staff 2026-2027 "
              "tại source hoặc target."
        )


    source_move = residual(
        mem,
        [source_id],
        move_year_ids,
    )

    target_move = residual(
        mem,
        [target_id],
        move_year_ids,
    )


    print(
        "SOURCE CURRENT/FUTURE =",
        source_move,
    )

    print(
        "TARGET CURRENT/FUTURE =",
        target_move,
    )


    if source_move or target_move:

        raise RuntimeError(
            op
            + ": source/target đã có "
              "dữ liệu CURRENT/FUTURE; "
              "không đúng nền dry-run sạch."
        )


    expected_by_op[
        op
    ] = combined


    all_previous_eligible_ids.extend(
        combined[
            "ELIGIBLE_IDS"
        ]
    )


# Không được có cùng một người nằm trong hai
# phương án khác nhau của nhóm 3 này.
cross_previous_dup = {
    staff_id: n

    for staff_id, n
    in Counter(
        all_previous_eligible_ids
    ).items()

    if n > 1
}


print()
print(
    "CROSS-OP PREVIOUS STAFF DUP =",
    cross_previous_dup,
)


if cross_previous_dup:

    raise RuntimeError(
        "DUNG: có staff_member_id "
        "xuất hiện ở nhiều phương án."
    )


# ============================================================
# 8. PAST SNAPSHOT
# ============================================================

involved_ids = sorted(
    {
        school_id

        for case in CASES

        for school_id in (
            case["source_id"],
            case["target_id"],
        )
    }
)


past_before = past_snapshot(
    mem,
    involved_ids,
    past_year_ids,
)


audit_before = int(
    mem.execute(
        """
        SELECT COUNT(*)
        FROM school_merger_operations
        """
    ).fetchone()[0]
    or 0
)


official_before = int(
    mem.execute(
        (
            "SELECT COUNT(*) FROM "
            + qident(
                official_table
            )
        )
    ).fetchone()[0]
    or 0
)


batch_mem_before = int(
    mem.execute(
        (
            "SELECT COUNT(*) FROM "
            + qident(
                batch_table
            )
            + " WHERE school_year_id=? "
              "AND level_code='THCS'"
        ),
        (
            YEAR_ID,
        ),
    ).fetchone()[0]
    or 0
)


print()
print("7. PAST / AUDIT BEFORE")
print("-" * 150)

print(
    "PAST HASH =",
    past_before,
)

print(
    "AUDIT ROWS =",
    audit_before,
)

print(
    "OFFICIAL ROWS =",
    official_before,
)

print(
    "THCS BATCH COUNT =",
    batch_mem_before,
)


# ============================================================
# 9. SIMULATE
# ============================================================

print()
print("=" * 150)
print("8. MO PHONG TREN RAM")
print("=" * 150)


results = []


mem.execute("BEGIN")


try:

    for index, case in enumerate(
        CASES,
        start=1,
    ):

        op = case["op"]

        source_id = case[
            "source_id"
        ]

        target_id = case[
            "target_id"
        ]

        expected = expected_by_op[
            op
        ]


        print()
        print("#" * 150)

        print(
            f"[{index}/3] {op}"
        )

        print(
            source_id,
            "->",
            target_id,
            "|",
            case["source_name"],
            "->",
            case["target_name"],
        )


        (
            checked_target,
            checked_sources,
            blockers,
            warnings,
        ) = merger._validate_selection(
            mem,
            selected_year_id=YEAR_ID,
            target_school_id=target_id,
            source_ids=[
                source_id
            ],
            require_active_sources=True,
        )


        print(
            "selection blockers =",
            blockers,
        )

        print(
            "selection warnings =",
            warnings,
        )


        if blockers:

            raise RuntimeError(
                op
                + ": selection blockers = "
                + repr(blockers)
            )


        result = merger._apply_merge(
            mem,
            selected_year_id=YEAR_ID,
            previous_year_id=PREVIOUS_YEAR_ID,
            target_school_id=target_id,
            source_ids=[
                source_id
            ],
            actor_user_id=None,
            backup_name=(
                "RAM-DRY-RUN-"
                "THCS-0108-0210-0644"
            ),
            record_audit=False,
        )


        source_after = school_row(
            mem,
            source_id,
        )

        target_after = school_row(
            mem,
            target_id,
        )

        staff_after = (
            current_staff_state(
                mem,
                merger,
                target_id,
            )
        )

        users_after = (
            source_user_state(
                mem,
                source_id,
            )
        )

        residual_after = residual(
            mem,
            [source_id],
            move_year_ids,
        )


        checks = {
            "source_inactive":
                int(
                    source_after[
                        "is_active"
                    ]
                    or 0
                ) == 0,

            "target_active":
                int(
                    target_after[
                        "is_active"
                    ]
                    or 0
                ) == 1,

            "target_id_same":
                int(
                    target_after["id"]
                ) == target_id,

            "target_code_same":
                str(
                    target_after["code"]
                ) == case[
                    "target_code"
                ],

            "target_name_same":
                str(
                    target_after["name"]
                ) == case[
                    "target_name"
                ],

            "source_residual_zero":
                not residual_after,

            "source_active_users_zero":
                users_after[
                    "active"
                ] == 0,

            "source_school_login_zero":
                users_after[
                    "school_login"
                ] == 0,

            "staff_total":
                staff_after[
                    "TOTAL"
                ]
                == expected[
                    "TOTAL"
                ],

            "staff_quan_ly":
                staff_after[
                    "QUAN_LY"
                ]
                == expected[
                    "QUAN_LY"
                ],

            "staff_giao_vien":
                staff_after[
                    "GIAO_VIEN"
                ]
                == expected[
                    "GIAO_VIEN"
                ],

            "staff_nhan_vien":
                staff_after[
                    "NHAN_VIEN"
                ]
                == expected[
                    "NHAN_VIEN"
                ],

            "staff_duplicate_zero":
                not staff_after[
                    "DUPLICATE"
                ],

            "rollover_created":
                int(
                    result.get(
                        "staff_rollover_created"
                    )
                    or 0
                )
                == expected[
                    "TOTAL"
                ],

            "existing_elsewhere_skipped_zero":
                int(
                    result.get(
                        "staff_existing_elsewhere_skipped"
                    )
                    or 0
                )
                == 0,

            "one_source_deactivated":
                int(
                    result.get(
                        "sources_deactivated"
                    )
                    or 0
                )
                == 1,

            "one_school_login_disabled":
                int(
                    result.get(
                        "source_school_logins_disabled"
                    )
                    or 0
                )
                == 1,
        }


        print(
            "ENGINE RESULT ="
        )

        print(
            json.dumps(
                result,
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        )

        print(
            "EXPECTED STAFF =",
            {
                k: expected[k]

                for k in (
                    "TOTAL",
                    "QUAN_LY",
                    "GIAO_VIEN",
                    "NHAN_VIEN",
                    "EXCLUDED",
                )
            },
        )

        print(
            "ACTUAL STAFF =",
            staff_after,
        )

        print(
            "SOURCE USERS =",
            users_after,
        )

        print(
            "SOURCE RESIDUAL =",
            residual_after,
        )

        print(
            "CHECKS =",
            checks,
        )


        if not all(
            checks.values()
        ):

            raise RuntimeError(
                op
                + ": POSTCHECK FAIL."
            )


        results.append({
            "operation_id":
                op,

            "source_id":
                source_id,

            "target_id":
                target_id,

            "target_code":
                case["target_code"],

            "target_name":
                case["target_name"],

            "staff":
                staff_after,

            "business_note":
                case[
                    "business_note"
                ],

            "status":
                "PASS",
        })


    # ========================================================
    # 10. GLOBAL CHECK
    # ========================================================

    print()
    print("=" * 150)
    print("9. HAU KIEM TONG TREN RAM")
    print("=" * 150)


    source_ids = [
        x["source_id"]
        for x in CASES
    ]

    target_ids = [
        x["target_id"]
        for x in CASES
    ]


    active_sources = int(
        mem.execute(
            (
                "SELECT COUNT(*) "
                "FROM schools "
                "WHERE id IN ("
                + marks(
                    len(source_ids)
                )
                + ") "
                "AND is_active=1"
            ),
            source_ids,
        ).fetchone()[0]
        or 0
    )


    active_targets = int(
        mem.execute(
            (
                "SELECT COUNT(*) "
                "FROM schools "
                "WHERE id IN ("
                + marks(
                    len(target_ids)
                )
                + ") "
                "AND is_active=1"
            ),
            target_ids,
        ).fetchone()[0]
        or 0
    )


    global_residual = residual(
        mem,
        source_ids,
        move_year_ids,
    )


    past_after = past_snapshot(
        mem,
        involved_ids,
        past_year_ids,
    )


    # Kiểm staff của 3 target có đồng thời active
    # ở bất kỳ trường khác trong toàn DB hay không.
    target_staff_ids = sorted(
        {
            staff_id

            for row in results

            for staff_id in row[
                "staff"
            ][
                "IDS"
            ]
        }
    )


    duplicate_anywhere = []


    if target_staff_ids:

        duplicate_anywhere = [
            dict(x)

            for x in mem.execute(
                (
                    "SELECT "
                    "staff_member_id,"
                    "COUNT(DISTINCT school_id) "
                    "AS school_count,"
                    "GROUP_CONCAT("
                    "DISTINCT school_id"
                    ") AS schools "
                    "FROM staff_year_records "
                    "WHERE school_year_id=? "
                    "AND is_active=1 "
                    "AND staff_member_id IN ("
                    + marks(
                        len(
                            target_staff_ids
                        )
                    )
                    + ") "
                    "GROUP BY staff_member_id "
                    "HAVING COUNT("
                    "DISTINCT school_id"
                    ")>1 "
                    "ORDER BY staff_member_id"
                ),
                [
                    YEAR_ID,
                    *target_staff_ids,
                ],
            ).fetchall()
        ]


    audit_after = int(
        mem.execute(
            """
            SELECT COUNT(*)
            FROM school_merger_operations
            """
        ).fetchone()[0]
        or 0
    )


    official_after = int(
        mem.execute(
            (
                "SELECT COUNT(*) FROM "
                + qident(
                    official_table
                )
            )
        ).fetchone()[0]
        or 0
    )


    batch_after = int(
        mem.execute(
            (
                "SELECT COUNT(*) FROM "
                + qident(
                    batch_table
                )
                + " WHERE school_year_id=? "
                  "AND level_code='THCS'"
            ),
            (
                YEAR_ID,
            ),
        ).fetchone()[0]
        or 0
    )


    integrity_ram = str(
        mem.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]
    )


    fk_ram = mem.execute(
        "PRAGMA foreign_key_check"
    ).fetchall()


    total_staff = sum(
        x["staff"]["TOTAL"]
        for x in results
    )

    total_ql = sum(
        x["staff"]["QUAN_LY"]
        for x in results
    )

    total_gv = sum(
        x["staff"]["GIAO_VIEN"]
        for x in results
    )

    total_nv = sum(
        x["staff"]["NHAN_VIEN"]
        for x in results
    )


    print(
        "PASS COUNT            =",
        len(results),
        "/ 3",
    )

    print(
        "ACTIVE SOURCES        =",
        active_sources,
    )

    print(
        "ACTIVE TARGETS        =",
        active_targets,
        "/ 3",
    )

    print(
        "SOURCE RESIDUAL       =",
        global_residual,
    )

    print(
        "PAST BEFORE           =",
        past_before,
    )

    print(
        "PAST AFTER            =",
        past_after,
    )

    print(
        "PAST EXACT            =",
        past_before
        == past_after,
    )

    print(
        "DUPLICATE ANYWHERE    =",
        duplicate_anywhere,
    )

    print(
        "TOTAL STAFF           =",
        total_staff,
    )

    print(
        "TOTAL QUAN LY         =",
        total_ql,
    )

    print(
        "TOTAL GIAO VIEN       =",
        total_gv,
    )

    print(
        "TOTAL NHAN VIEN       =",
        total_nv,
    )

    print(
        "AUDIT ROWS BEFORE/AFTER =",
        audit_before,
        "/",
        audit_after,
    )

    print(
        "OFFICIAL BEFORE/AFTER =",
        official_before,
        "/",
        official_after,
    )

    print(
        "THCS BATCH BEFORE/AFTER =",
        batch_mem_before,
        "/",
        batch_after,
    )

    print(
        "RAM INTEGRITY         =",
        integrity_ram,
    )

    print(
        "RAM FK                =",
        len(fk_ram),
    )


    global_pass = (
        len(results) == 3

        and active_sources == 0

        and active_targets == 3

        and not global_residual

        and past_before == past_after

        and not duplicate_anywhere

        and total_staff == 193

        and total_ql == 15

        and total_gv == 156

        and total_nv == 22

        and audit_after == audit_before

        and official_after == official_before

        and batch_after == 1

        and batch_mem_before == 1

        and integrity_ram.lower()
            == "ok"

        and len(fk_ram) == 0
    )


finally:

    try:
        mem.rollback()
    except Exception:
        pass

    mem.close()


# ============================================================
# 11. REAL FILE SAFETY
# ============================================================

print()
print("=" * 150)
print("10. FILE THAT SAU DRY-RUN")
print("=" * 150)


for key, path in PATHS.items():

    after = sha256(path)

    print(
        key,
        ":",
        before_hash[key],
        "->",
        after,
    )

    if after != before_hash[key]:

        raise RuntimeError(
            "DUNG: "
            + key
            + " bị thay đổi."
        )


print()
print("=" * 150)


if global_pass:

    print(
        "DRY-RUN 3 THCS MAPPING/ALIAS: PASS"
    )

    print("=" * 150)


    for item in results:

        print(
            item["operation_id"],
            "|",
            item["source_id"],
            "->",
            item["target_id"],
            "|",
            item["target_name"],
            "| staff=",
            item["staff"]["TOTAL"],
            "| PASS",
        )


    print()
    print(
        "OP0108 THACH NGAN = 61 "
        "(QL=6, GV=50, NV=5)"
    )

    print(
        "OP0210 TRAN PHU   = 89 "
        "(QL=4, GV=74, NV=11)"
    )

    print(
        "OP0644 YEN THANG  = 43 "
        "(QL=5, GV=32, NV=6)"
    )


    print()
    print(
        "TONG DOI NGU      = 193"
    )

    print(
        "QUAN LY           = 15"
    )

    print(
        "GIAO VIEN         = 156"
    )

    print(
        "NHAN VIEN         = 22"
    )

    print()
    print(
        "PAST              = GIU NGUYEN EXACT"
    )

    print(
        "SOURCE RESIDUAL   = 0"
    )

    print(
        "DUPLICATE STAFF   = 0"
    )

    print(
        "AUDIT/OFFICIAL    = KHONG TAO TREN RAM"
    )

    print(
        "THCS BATCH        = VAN CHI 1"
    )

    print(
        "DATABASE THAT     = KHONG THAY DOI"
    )

    print(
        "RESOLUTION        = KHONG THAY DOI"
    )

    print()
    print(
        "LUU Y OP0108: PASS KY THUAT "
        "KHONG TU DONG CO NGHIA "
        "DA DU DIEU KIEN GHI THAT."
    )

    print()
    print(
        "READY_FOR_REVIEW_THCS_SPECIAL_3=YES"
    )

else:

    print(
        "DRY-RUN 3 THCS MAPPING/ALIAS: FAIL"
    )

    print(
        "READY_FOR_REVIEW_THCS_SPECIAL_3=NO"
    )


print("=" * 150)


if not global_pass:

    raise SystemExit(2)
