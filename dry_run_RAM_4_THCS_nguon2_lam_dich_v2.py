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
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
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


EXPECTED_HASH = {
    "db":
        "c6a0f2f1a08e7e80a6e89cd0edfd83961f4d87930d5b8b1f3cdae8e770f4deee",

    "engine":
        "414fb49a4c5f4fed7b571cc55df381678fe660cd8a675ecaa2f6fd70ebd7827a",

    "service":
        "9104fb99c78755e9eec86d090659b3a922834ff097d7292aa4d4b29e360a27f9",

    "resolution":
        "d9d347b19de0795553c8f047cb91a430ded63d9232ac7eda7ea069b716c2c0f4",
}


CASES = [
    {
        "op": "QD3805-OP-0399",

        "source_id": 1592,
        "source_code": "40415505",
        "source_name": "THCS Quang Phong",

        "target_id": 1594,
        "target_code": "40415510",
        "target_old_name": "Trường THCS Cắm Muộn",
        "target_new_name": "THCS Mường Quàng",

        "commune_id": 10,

        "expected": {
            "TOTAL": 50,
            "QUAN_LY": 4,
            "GIAO_VIEN": 41,
            "NHAN_VIEN": 5,
            "EXCLUDED": 1,
        },
    },

    {
        "op": "QD3805-OP-0424",

        "source_id": 1485,
        "source_code": "40416506",
        "source_name": "Trường THCS Tiến Thắng",

        "target_id": 1486,
        "target_code": "40416507",
        "target_old_name": "PTDTBT THCS Bính Thuận",
        "target_new_name": "THCS Châu Tiến",

        "commune_id": 12,

        "expected": {
            "TOTAL": 60,
            "QUAN_LY": 6,
            "GIAO_VIEN": 49,
            "NHAN_VIEN": 5,
            "EXCLUDED": 1,
        },
    },

    {
        "op": "QD3805-OP-0434",

        "source_id": 1647,
        "source_code": "40416504",
        "source_name": "PTDTBT THCS Hội Nga",

        "target_id": 1646,
        "target_code": "40416501",
        "target_old_name": "THCS Hạnh Thiết",
        "target_new_name": "THCS Quỳ Châu",

        "commune_id": 11,

        "expected": {
            "TOTAL": 77,
            "QUAN_LY": 6,
            "GIAO_VIEN": 65,
            "NHAN_VIEN": 6,
            "EXCLUDED": 0,
        },
    },

    {
        "op": "QD3805-OP-0451",

        "source_id": 1589,
        "source_code": "40420509",
        "source_name": "THCS Châu Thái",

        "target_id": 1590,
        "target_code": "40420518",
        "target_old_name": "THCS Châu Cường",
        "target_new_name": "THCS Mường Ham",

        "commune_id": 51,

        "expected": {
            "TOTAL": 57,
            "QUAN_LY": 3,
            "GIAO_VIEN": 46,
            "NHAN_VIEN": 8,
            "EXCLUDED": 0,
        },
    },
]


YEAR_ID = 2
PREVIOUS_YEAR_ID = 1


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
        + str(value).replace('"', '""')
        + '"'
    )


def marks(n: int) -> str:

    return ",".join(
        "?"
        for _ in range(n)
    )


def connect_real_ro():

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


def year_tables(con):

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

        columns = {
            str(x["name"])
            for x in con.execute(
                f"PRAGMA table_info({qident(table)})"
            ).fetchall()
        }

        if {
            "school_id",
            "school_year_id",
        }.issubset(columns):

            result.append(table)

    return result


def encode(value):

    if isinstance(value, bytes):
        return {
            "__bytes__": value.hex()
        }

    return value


def past_snapshot(
    con,
    school_ids,
    year_ids,
):

    payload = {}

    for table in year_tables(con):

        info = con.execute(
            f"PRAGMA table_info({qident(table)})"
        ).fetchall()

        columns = [
            str(x["name"])
            for x in info
        ]

        rows = con.execute(
            (
                "SELECT * FROM "
                + qident(table)
                + " WHERE school_id IN ("
                + marks(len(school_ids))
                + ")"
                + " AND school_year_id IN ("
                + marks(len(year_ids))
                + ")"
            ),
            [
                *school_ids,
                *year_ids,
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
            key=lambda row:
                json.dumps(
                    row,
                    ensure_ascii=False,
                    sort_keys=True,
                    default=str,
                )
        )

        payload[table] = {
            "columns": columns,
            "rows": normalized,
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
    year_ids,
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
                    + ")"
                    + " AND school_year_id IN ("
                    + marks(len(year_ids))
                    + ")"
                ),
                [
                    *school_ids,
                    *year_ids,
                ],
            ).fetchone()[0]
            or 0
        )

        if n:
            result[table] = n

    return result


def school_row(
    con,
    school_id,
):

    row = con.execute(
        """
        SELECT
            id,
            commune_id,
            code,
            name,
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


def staff_rows(
    con,
    school_ids,
    year_id,
):

    return con.execute(
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
            int(year_id),
            *school_ids,
        ],
    ).fetchall()


def engine_expected(
    con,
    engine,
    school_ids,
):

    rows = staff_rows(
        con,
        school_ids,
        PREVIOUS_YEAR_ID,
    )

    eligible = Counter()
    excluded = []
    seen = Counter()

    for row in rows:

        staff_id = int(
            row["staff_member_id"]
        )

        seen[staff_id] += 1

        category = engine._classify_staff(
            row
        )

        if category == "CHUA_XAC_DINH":

            raise RuntimeError(
                "Khong phan loai duoc "
                f"staff_member_id={staff_id}"
            )

        if engine._staff_inactive(row):

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
                    row["status_code"]
                    if "status_code" in row.keys()
                    else None,

                "source_status_label":
                    row["source_status_label"]
                    if "source_status_label" in row.keys()
                    else None,
            })

            continue

        eligible[category] += 1

    duplicate = {
        staff_id: n
        for staff_id, n
        in seen.items()
        if n > 1
    }

    if duplicate:
        raise RuntimeError(
            "Trung staff_member_id nam truoc: "
            + repr(duplicate)
        )

    return {
        "TOTAL":
            sum(eligible.values()),

        "QUAN_LY":
            int(
                eligible.get(
                    "QUAN_LY",
                    0,
                )
            ),

        "GIAO_VIEN":
            int(
                eligible.get(
                    "GIAO_VIEN",
                    0,
                )
            ),

        "NHAN_VIEN":
            int(
                eligible.get(
                    "NHAN_VIEN",
                    0,
                )
            ),

        "EXCLUDED":
            len(excluded),

        "excluded_rows":
            excluded,
    }


def current_staff_state(
    con,
    engine,
    school_id,
):

    rows = staff_rows(
        con,
        [school_id],
        YEAR_ID,
    )

    groups = Counter()

    staff_ids = []

    for row in rows:

        if (
            "is_active" in row.keys()
            and row["is_active"] in (
                0,
                False,
                "0",
            )
        ):
            continue

        category = engine._classify_staff(
            row
        )

        groups[category] += 1

        if row["staff_member_id"] is not None:
            staff_ids.append(
                int(
                    row["staff_member_id"]
                )
            )

    duplicate = {
        staff_id: n
        for staff_id, n
        in Counter(staff_ids).items()
        if n > 1
    }

    return {
        "TOTAL":
            sum(groups.values()),

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
                    THEN 1 ELSE 0
                END
            ) AS active,

            SUM(
                CASE
                    WHEN username LIKE 'truong_%'
                     AND is_active=1
                    THEN 1 ELSE 0
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


# ============================================================
# START
# ============================================================

print("=" * 150)
print(
    "THCS - DRY-RUN RAM 4 PHUONG AN DAC THU - ENGINE ELIGIBLE"
)
print(
    "NGUON 2 LAM DICH - KHONG GHI DATABASE THAT"
)
print("=" * 150)


# ============================================================
# 1. HASH GATE
# ============================================================

print()
print("1. HASH / SERVER GATE")
print("-" * 150)


PATHS = {
    "db": DB,
    "engine": ENGINE_FILE,
    "service": SERVICE_FILE,
    "resolution": RESOLUTION_FILE,
}

before_hash = {}

for key, path in PATHS.items():

    current = sha256(path)

    before_hash[key] = current

    print(
        f"{key:12s} = {current}"
    )

    if current != EXPECTED_HASH[key]:

        raise RuntimeError(
            "DUNG: "
            + key
            + " da thay doi."
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

    if size:

        raise RuntimeError(
            "DUNG: hay dung Uvicorn/server."
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
    as engine
)


# ============================================================
# 3. REAL DB GATE + COPY RAM
# ============================================================

real = connect_real_ro()

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
    print("2. DATABASE THAT")
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
            "DUNG: DB health FAIL."
        )


    # Khóa danh tính 8 trường.
    for case in CASES:

        source = school_row(
            real,
            case["source_id"],
        )

        target = school_row(
            real,
            case["target_id"],
        )

        if (
            source is None
            or target is None
        ):
            raise RuntimeError(
                case["op"]
                + ": thieu school."
            )

        valid = (
            int(source["commune_id"])
                == case["commune_id"]

            and int(target["commune_id"])
                == case["commune_id"]

            and str(source["code"])
                == case["source_code"]

            and str(target["code"])
                == case["target_code"]

            and str(source["name"])
                == case["source_name"]

            and str(target["name"])
                == case["target_old_name"]

            and bool(source["is_active"])

            and bool(target["is_active"])
        )

        if not valid:

            print(
                "SOURCE =",
                source,
            )

            print(
                "TARGET =",
                target,
            )

            raise RuntimeError(
                case["op"]
                + ": danh tinh 8 truong da thay doi."
            )


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


move_year_ids, past_year_ids = (
    engine._year_scope_ids(
        mem,
        YEAR_ID,
    )
)

previous_year_id = (
    engine._previous_year_id(
        mem,
        YEAR_ID,
    )
)


print()
print("3. YEAR SCOPE")
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
        "DUNG: CURRENT/FUTURE "
        "khong phai [2,8]."
    )


if previous_year_id != 1:

    raise RuntimeError(
        "DUNG: previous year != 1."
    )


# ============================================================
# 4. ENGINE EXPECTED GATE
# ============================================================

print()
print("=" * 150)
print("4. KHOA SO DOI NGU DUNG THEO ENGINE")
print("=" * 150)


expected_by_op = {}


for case in CASES:

    expected = engine_expected(
        mem,
        engine,
        [
            case["source_id"],
            case["target_id"],
        ],
    )

    expected_by_op[
        case["op"]
    ] = expected


    print()
    print(
        case["op"],
        "=",
        json.dumps(
            expected,
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
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

        if expected[key] != hard[key]:

            raise RuntimeError(
                case["op"]
                + ": engine expected "
                + key
                + " da thay doi."
            )


    current_source = current_staff_state(
        mem,
        engine,
        case["source_id"],
    )

    current_target = current_staff_state(
        mem,
        engine,
        case["target_id"],
    )


    if (
        current_source["TOTAL"] != 0
        or current_target["TOTAL"] != 0
    ):

        raise RuntimeError(
            case["op"]
            + ": da co staff 2026-2027 "
              "tai source/target."
        )


# ============================================================
# 5. PAST SNAPSHOT
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


print()
print("5. PAST BEFORE")
print("-" * 150)

print(
    "PAST HASH =",
    past_before,
)


# ============================================================
# 6. SIMULATION
# ============================================================

print()
print("=" * 150)
print("6. MO PHONG 4 PHUONG AN")
print("=" * 150)


results = []


mem.execute(
    "BEGIN"
)


try:

    for index, case in enumerate(
        CASES,
        start=1,
    ):

        op = case["op"]

        source_id = int(
            case["source_id"]
        )

        target_id = int(
            case["target_id"]
        )

        expected = expected_by_op[
            op
        ]


        print()
        print("#" * 150)

        print(
            f"[{index}/4] {op}"
        )

        print(
            source_id,
            "->",
            target_id,
        )

        print(
            case["target_old_name"],
            "->",
            case["target_new_name"],
        )


        (
            checked_target,
            checked_sources,
            blockers,
            warnings,
        ) = engine._validate_selection(
            mem,
            selected_year_id=YEAR_ID,
            target_school_id=target_id,
            source_ids=[
                source_id
            ],
            require_active_sources=True,
        )


        print(
            "blockers =",
            blockers,
        )

        print(
            "warnings =",
            warnings,
        )


        if blockers:

            raise RuntimeError(
                op
                + ": selection blocker = "
                + repr(blockers)
            )


        result = engine._apply_merge(
            mem,
            selected_year_id=YEAR_ID,
            previous_year_id=PREVIOUS_YEAR_ID,
            target_school_id=target_id,
            source_ids=[
                source_id
            ],
            actor_user_id=None,
            backup_name=(
                "THCS-SPECIAL-4-ENGINE-"
                "ELIGIBLE-RAM"
            ),
            record_audit=False,
        )


        # ----------------------------------------
        # Rename target trên RAM
        # ----------------------------------------

        existing_history = mem.execute(
            """
            SELECT 1
            FROM school_name_histories
            WHERE school_id=?
              AND effective_school_year_id=?
            LIMIT 1
            """,
            (
                target_id,
                YEAR_ID,
            ),
        ).fetchone()


        if existing_history is not None:

            raise RuntimeError(
                op
                + ": target da co lich su "
                  "doi ten 2026-2027."
            )


        target_before_rename = school_row(
            mem,
            target_id,
        )


        if (
            target_before_rename is None
            or str(
                target_before_rename["name"]
            )
            != case[
                "target_old_name"
            ]
        ):

            raise RuntimeError(
                op
                + ": ten target truoc rename sai."
            )


        mem.execute(
            """
            INSERT INTO school_name_histories (
                school_id,
                effective_school_year_id,
                old_name,
                new_name,
                changed_at,
                changed_by_user_id
            )
            VALUES (?,?,?,?,?,?)
            """,
            (
                target_id,
                YEAR_ID,
                case["target_old_name"],
                case["target_new_name"],
                "RAM-DRY-RUN",
                None,
            ),
        )


        cur = mem.execute(
            """
            UPDATE schools
            SET name=?
            WHERE id=?
              AND is_active=1
            """,
            (
                case["target_new_name"],
                target_id,
            ),
        )


        if cur.rowcount != 1:

            raise RuntimeError(
                op
                + ": rename khong dung 1 row."
            )


        # ----------------------------------------
        # Postcheck
        # ----------------------------------------

        source_after = school_row(
            mem,
            source_id,
        )

        target_after = school_row(
            mem,
            target_id,
        )

        staff_after = current_staff_state(
            mem,
            engine,
            target_id,
        )

        source_users = source_user_state(
            mem,
            source_id,
        )

        source_residual = residual(
            mem,
            [
                source_id
            ],
            move_year_ids,
        )

        history_rows = mem.execute(
            """
            SELECT
                school_id,
                effective_school_year_id,
                old_name,
                new_name
            FROM school_name_histories
            WHERE school_id=?
              AND effective_school_year_id=?
            """,
            (
                target_id,
                YEAR_ID,
            ),
        ).fetchall()


        checks = {
            "source_inactive":
                not bool(
                    source_after[
                        "is_active"
                    ]
                ),

            "target_active":
                bool(
                    target_after[
                        "is_active"
                    ]
                ),

            "target_id_preserved":
                int(
                    target_after["id"]
                )
                == target_id,

            "target_code_preserved":
                str(
                    target_after["code"]
                )
                == case["target_code"],

            "target_name_new":
                str(
                    target_after["name"]
                )
                == case[
                    "target_new_name"
                ],

            "source_residual_zero":
                not bool(
                    source_residual
                ),

            "source_active_users_zero":
                source_users[
                    "active"
                ] == 0,

            "source_school_login_zero":
                source_users[
                    "school_login"
                ] == 0,

            "staff_total":
                staff_after[
                    "TOTAL"
                ]
                == expected[
                    "TOTAL"
                ],

            "staff_management":
                staff_after[
                    "QUAN_LY"
                ]
                == expected[
                    "QUAN_LY"
                ],

            "staff_teacher":
                staff_after[
                    "GIAO_VIEN"
                ]
                == expected[
                    "GIAO_VIEN"
                ],

            "staff_employee":
                staff_after[
                    "NHAN_VIEN"
                ]
                == expected[
                    "NHAN_VIEN"
                ],

            "staff_duplicate_zero":
                not bool(
                    staff_after[
                        "DUPLICATE"
                    ]
                ),

            "rollover_total":
                int(
                    result.get(
                        "staff_rollover_created"
                    )
                    or 0
                )
                == expected[
                    "TOTAL"
                ],

            "rename_history_one":
                len(
                    history_rows
                ) == 1,
        }


        print(
            "ENGINE RESULT =",
            json.dumps(
                result,
                ensure_ascii=False,
                indent=2,
                default=str,
            ),
        )

        print(
            "EXPECTED =",
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
            "SOURCE AFTER =",
            source_after,
        )

        print(
            "TARGET AFTER =",
            target_after,
        )

        print(
            "SOURCE USERS =",
            source_users,
        )

        print(
            "SOURCE RESIDUAL =",
            source_residual,
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
            "op":
                op,

            "source_id":
                source_id,

            "target_id":
                target_id,

            "target_code":
                case["target_code"],

            "target_name":
                case["target_new_name"],

            "staff":
                staff_after,

            "excluded":
                expected["EXCLUDED"],

            "status":
                "PASS",
        })


    # ========================================================
    # 7. GLOBAL POSTCHECK
    # ========================================================

    print()
    print("=" * 150)
    print("7. HAU KIEM TONG TREN RAM")
    print("=" * 150)


    source_ids = [
        case["source_id"]
        for case in CASES
    ]

    target_ids = [
        case["target_id"]
        for case in CASES
    ]


    global_residual = residual(
        mem,
        source_ids,
        move_year_ids,
    )


    active_sources = int(
        mem.execute(
            (
                "SELECT COUNT(*) "
                "FROM schools "
                "WHERE id IN ("
                + marks(len(source_ids))
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
                + marks(len(target_ids))
                + ") "
                "AND is_active=1"
            ),
            target_ids,
        ).fetchone()[0]
        or 0
    )


    cross_duplicate = mem.execute(
        (
            "SELECT "
            "staff_member_id,"
            "COUNT(DISTINCT school_id) AS n,"
            "GROUP_CONCAT(DISTINCT school_id) AS schools "
            "FROM staff_year_records "
            "WHERE school_year_id=? "
            "AND is_active=1 "
            "AND staff_member_id IS NOT NULL "
            "AND school_id IN ("
            + marks(len(target_ids))
            + ") "
            "GROUP BY staff_member_id "
            "HAVING COUNT(DISTINCT school_id)>1"
        ),
        [
            YEAR_ID,
            *target_ids,
        ],
    ).fetchall()


    past_after = past_snapshot(
        mem,
        involved_ids,
        past_year_ids,
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
        row["staff"]["TOTAL"]
        for row in results
    )

    total_management = sum(
        row["staff"]["QUAN_LY"]
        for row in results
    )

    total_teacher = sum(
        row["staff"]["GIAO_VIEN"]
        for row in results
    )

    total_employee = sum(
        row["staff"]["NHAN_VIEN"]
        for row in results
    )


    print(
        "PASS COUNT          =",
        len(results),
        "/ 4",
    )

    print(
        "ACTIVE SOURCES      =",
        active_sources,
    )

    print(
        "ACTIVE TARGETS      =",
        active_targets,
        "/ 4",
    )

    print(
        "CURRENT/FUTURE SRC  =",
        global_residual,
    )

    print(
        "PAST BEFORE         =",
        past_before,
    )

    print(
        "PAST AFTER          =",
        past_after,
    )

    print(
        "PAST EXACT          =",
        past_before
        == past_after,
    )

    print(
        "CROSS STAFF DUP     =",
        [
            dict(x)
            for x in cross_duplicate
        ],
    )

    print(
        "TOTAL STAFF         =",
        total_staff,
    )

    print(
        "TOTAL QUAN LY       =",
        total_management,
    )

    print(
        "TOTAL GIAO VIEN     =",
        total_teacher,
    )

    print(
        "TOTAL NHAN VIEN     =",
        total_employee,
    )

    print(
        "RAM INTEGRITY       =",
        integrity_ram,
    )

    print(
        "RAM FK              =",
        len(fk_ram),
    )


    global_pass = (
        len(results) == 4

        and active_sources == 0

        and active_targets == 4

        and not global_residual

        and past_before == past_after

        and not cross_duplicate

        and total_staff == 244

        and total_management == 19

        and total_teacher == 201

        and total_employee == 24

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
# 8. REAL FILE SAFETY
# ============================================================

print()
print("=" * 150)
print("8. FILE THAT SAU DRY-RUN")
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
            + " bi thay doi."
        )


print()
print("=" * 150)


if global_pass:

    print(
        "DRY-RUN 4 THCS DAC THU: PASS"
    )

    print("=" * 150)

    for row in results:

        print(
            row["op"],
            "|",
            row["source_id"],
            "->",
            row["target_id"],
            "| code=",
            row["target_code"],
            "| name=",
            row["target_name"],
            "| staff=",
            row["staff"]["TOTAL"],
            "| excluded historical=",
            row["excluded"],
            "| PASS",
        )

    print()
    print(
        "MƯỜNG QUÀNG = 50 "
        "(QL=4, GV=41, NV=5)"
    )

    print(
        "CHÂU TIẾN   = 60 "
        "(QL=6, GV=49, NV=5)"
    )

    print(
        "QUỲ CHÂU    = 77 "
        "(QL=6, GV=65, NV=6)"
    )

    print(
        "MƯỜNG HAM   = 57 "
        "(QL=3, GV=46, NV=8)"
    )

    print()
    print(
        "TỔNG ĐỘI NGŨ = 244"
    )

    print(
        "CBQL          = 19"
    )

    print(
        "GIÁO VIÊN     = 201"
    )

    print(
        "NHÂN VIÊN     = 24"
    )

    print()
    print(
        "2 HỒ SƠ NGHỈ/CHUYỂN = "
        "CHỈ GIỮ LỊCH SỬ, KHÔNG ROLLOVER"
    )

    print(
        "PAST                = GIỮ NGUYÊN EXACT"
    )

    print(
        "CURRENT/FUTURE SRC  = 0"
    )

    print(
        "TARGET ID/CODE      = GIỮ NGUYÊN NGUỒN 2"
    )

    print(
        "TARGET NAME         = ĐỔI THEO QĐ3805"
    )

    print(
        "DATABASE THẬT       = KHÔNG THAY ĐỔI"
    )

    print(
        "SÁP NHẬP THẬT       = CHƯA CHẠY"
    )

    print()
    print(
        "READY_FOR_OFFICIAL_THCS_SPECIAL_4=YES"
    )

else:

    print(
        "DRY-RUN 4 THCS DAC THU: FAIL"
    )

    print(
        "READY_FOR_OFFICIAL_THCS_SPECIAL_4=NO"
    )


print("=" * 150)


if not global_pass:
    raise SystemExit(2)
