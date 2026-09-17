# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
import unicodedata
from collections import Counter
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


ROOT = Path(r"C:\PhoCap")

DB = ROOT / "data" / "phocap.db"

ENGINE = (
    ROOT
    / "app"
    / "services"
    / "school_merger_service.py"
)

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
    / "qd3805_thcs_resolution.json"
)


EXPECTED = {
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
        "operation_id": "QD3805-OP-0399",

        "source_id": 1592,
        "source_code": "40415505",
        "source_name": "THCS Quang Phong",

        "target_id": 1594,
        "target_code": "40415510",
        "target_old_name": "Trường THCS Cắm Muộn",

        "target_new_name": "THCS Mường Quàng",

        "commune_id": 10,
    },

    {
        "operation_id": "QD3805-OP-0424",

        "source_id": 1485,
        "source_code": "40416506",
        "source_name": "Trường THCS Tiến Thắng",

        "target_id": 1486,
        "target_code": "40416507",
        "target_old_name": "PTDTBT THCS Bính Thuận",

        "target_new_name": "THCS Châu Tiến",

        "commune_id": 12,
    },

    {
        "operation_id": "QD3805-OP-0434",

        "source_id": 1647,
        "source_code": "40416504",
        "source_name": "PTDTBT THCS Hội Nga",

        "target_id": 1646,
        "target_code": "40416501",
        "target_old_name": "THCS Hạnh Thiết",

        "target_new_name": "THCS Quỳ Châu",

        "commune_id": 11,
    },

    {
        "operation_id": "QD3805-OP-0451",

        "source_id": 1589,
        "source_code": "40420509",
        "source_name": "THCS Châu Thái",

        "target_id": 1590,
        "target_code": "40420518",
        "target_old_name": "THCS Châu Cường",

        "target_new_name": "THCS Mường Ham",

        "commune_id": 51,
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


def qident(value: str) -> str:

    return (
        '"'
        + str(value).replace(
            '"',
            '""',
        )
        + '"'
    )


def marks(n: int) -> str:

    return ",".join(
        "?"
        for _ in range(n)
    )


def canon(value) -> str:

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
        ch
        for ch in text
        if unicodedata.category(ch)
        != "Mn"
    )

    text = (
        text.replace(" ", "_")
        .replace("-", "_")
        .replace("/", "_")
    )

    if text in {
        "CBQL",
        "CAN_BO_QUAN_LY",
        "QUAN_LY",
    }:
        return "CBQL"

    if text in {
        "GV",
        "GIAO_VIEN",
        "GIAOVIEN",
    }:
        return "GIAO_VIEN"

    if text in {
        "NV",
        "NHAN_VIEN",
        "NHANVIEN",
    }:
        return "NHAN_VIEN"

    return text or "KHAC"


def year_aware_tables(con):

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

            result.append(
                table
            )

    return result


def encode(value):

    if isinstance(
        value,
        bytes,
    ):

        return {
            "__bytes__":
                value.hex()
        }

    return value


def snapshot_past(
    con,
    school_ids,
    past_year_ids,
):

    payload = {}

    for table in year_aware_tables(
        con
    ):

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
                + marks(
                    len(school_ids)
                )
                + ")"
                + " AND school_year_id IN ("
                + marks(
                    len(past_year_ids)
                )
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
                    encode(
                        row[col]
                    )
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

        payload[
            table
        ] = {
            "columns": columns,
            "rows": normalized,
        }

    raw = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode(
        "utf-8"
    )

    return hashlib.sha256(
        raw
    ).hexdigest()


def residual(
    con,
    school_ids,
    year_ids,
):

    result = {}

    for table in year_aware_tables(
        con
    ):

        n = int(
            con.execute(
                (
                    "SELECT COUNT(*) FROM "
                    + qident(table)
                    + " WHERE school_id IN ("
                    + marks(
                        len(school_ids)
                    )
                    + ")"
                    + " AND school_year_id IN ("
                    + marks(
                        len(year_ids)
                    )
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

            result[
                table
            ] = n

    return result


def staff_rows(
    con,
    school_id,
    year_id,
):

    return con.execute(
        """
        SELECT
            staff_member_id,
            position_group
        FROM staff_year_records
        WHERE school_id=?
          AND school_year_id=?
          AND is_active=1
        ORDER BY staff_member_id,id
        """,
        (
            int(school_id),
            int(year_id),
        ),
    ).fetchall()


def staff_state(
    con,
    school_id,
    year_id,
):

    rows = staff_rows(
        con,
        school_id,
        year_id,
    )

    counter = Counter(
        canon(
            x["position_group"]
        )
        for x in rows
    )

    ids = [
        int(x["staff_member_id"])
        for x in rows
        if x["staff_member_id"]
        is not None
    ]

    duplicate_ids = [
        staff_id
        for staff_id, n
        in Counter(ids).items()
        if n > 1
    ]

    return {
        "TOTAL": len(rows),

        "DISTINCT":
            len(
                set(ids)
            ),

        "CBQL":
            int(
                counter.get(
                    "CBQL",
                    0,
                )
            ),

        "GIAO_VIEN":
            int(
                counter.get(
                    "GIAO_VIEN",
                    0,
                )
            ),

        "NHAN_VIEN":
            int(
                counter.get(
                    "NHAN_VIEN",
                    0,
                )
            ),

        "DUPLICATE_IDS":
            duplicate_ids,
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
            int(
                row["total"]
                or 0
            ),

        "active":
            int(
                row["active"]
                or 0
            ),

        "school_login":
            int(
                row["school_login"]
                or 0
            ),
    }


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


# ============================================================
# START
# ============================================================

print("=" * 150)
print(
    "THCS - DRY-RUN RAM 4 PHUONG AN NGUON 2 LAM DICH"
)
print(
    "KHONG GHI DATABASE THAT - KHONG SUA SOURCE - KHONG SAP NHAP THAT"
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
    "engine": ENGINE,
    "service": SERVICE,
    "resolution": RESOLUTION,
}


before_hash = {}


for key, path in PATHS.items():

    value = sha256(
        path
    )

    before_hash[
        key
    ] = value

    print(
        f"{key:12s} = {value}"
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

    if size:

        raise RuntimeError(
            "DUNG: hay dung Uvicorn/server truoc."
        )


# ============================================================
# 2. RESOLUTION GATE
# ============================================================

print()
print("2. RESOLUTION GATE")
print("-" * 150)


resolution = json.loads(
    RESOLUTION.read_text(
        encoding="utf-8-sig"
    )
)


special = {
    str(
        x.get(
            "operation_id"
        )
        or ""
    ):
        x

    for x in (
        resolution.get(
            "special_same_level"
        )
        or []
    )

    if isinstance(
        x,
        dict,
    )
}


for case in CASES:

    op = case[
        "operation_id"
    ]

    if op not in special:

        raise RuntimeError(
            "DUNG: "
            + op
            + " khong con nam trong xu ly rieng."
        )

    print(
        op,
        "= PASS"
    )


# ============================================================
# 3. REAL DB READ-ONLY
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
    print("3. DATABASE THAT - READ ONLY")
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
        integrity.lower()
        != "ok"
        or fk
    ):

        raise RuntimeError(
            "DUNG: database health FAIL."
        )


    years = real.execute(
        """
        SELECT id,code,name
        FROM school_years
        ORDER BY id
        """
    ).fetchall()


    print()
    print(
        "SCHOOL YEARS:"
    )

    for y in years:
        print(
            dict(y)
        )


    year2 = real.execute(
        """
        SELECT id,code
        FROM school_years
        WHERE id=2
        """
    ).fetchone()


    if (
        year2 is None
        or str(
            year2["code"]
            or ""
        ).strip()
        != "2026-2027"
    ):

        raise RuntimeError(
            "DUNG: school_year_id=2 "
            "khong phai 2026-2027."
        )


    # ========================================================
    # 4. VERIFY 8 SCHOOL IDENTITIES
    # ========================================================

    print()
    print("4. KHOA DANH TINH 8 TRUONG")
    print("=" * 150)


    involved_ids = []


    for case in CASES:

        source = school_row(
            real,
            case[
                "source_id"
            ],
        )

        target = school_row(
            real,
            case[
                "target_id"
            ],
        )


        print()
        print(
            case[
                "operation_id"
            ]
        )

        print(
            "SOURCE =",
            source,
        )

        print(
            "TARGET =",
            target,
        )


        if source is None or target is None:

            raise RuntimeError(
                "DUNG: thieu source/target."
            )


        checks = (
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
                is True

            and bool(target["is_active"])
                is True
        )


        if not checks:

            raise RuntimeError(
                "DUNG: danh tinh/trang thai "
                + case[
                    "operation_id"
                ]
                + " khong con dung."
            )


        involved_ids.extend([
            case[
                "source_id"
            ],
            case[
                "target_id"
            ],
        ])


    involved_ids = sorted(
        set(
            involved_ids
        )
    )


    # ========================================================
    # 5. COPY REAL DB TO RAM
    # ========================================================

    print()
    print("5. COPY DATABASE VAO RAM")
    print("-" * 150)


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


sys.path.insert(
    0,
    str(ROOT),
)


from app.services import (
    school_merger_service
    as engine
)


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


if previous_year_id != PREVIOUS_YEAR_ID:

    raise RuntimeError(
        "DUNG: previous year khong phai id=1."
    )


if YEAR_ID not in move_year_ids:

    raise RuntimeError(
        "DUNG: 2026-2027 khong nam trong move scope."
    )


# ============================================================
# 6. PRE-SNAPSHOT
# ============================================================

print()
print("6. PRE-SNAPSHOT")
print("-" * 150)


past_hash_before = snapshot_past(
    mem,
    involved_ids,
    past_year_ids,
)


print(
    "PAST HASH BEFORE =",
    past_hash_before,
)


expected_staff = {}


for case in CASES:

    source_id = case[
        "source_id"
    ]

    target_id = case[
        "target_id"
    ]


    source_prev = staff_state(
        mem,
        source_id,
        PREVIOUS_YEAR_ID,
    )

    target_prev = staff_state(
        mem,
        target_id,
        PREVIOUS_YEAR_ID,
    )


    source_current = staff_state(
        mem,
        source_id,
        YEAR_ID,
    )

    target_current = staff_state(
        mem,
        target_id,
        YEAR_ID,
    )


    source_ids = {
        int(x["staff_member_id"])
        for x in staff_rows(
            mem,
            source_id,
            PREVIOUS_YEAR_ID,
        )
        if x["staff_member_id"]
        is not None
    }


    target_ids = {
        int(x["staff_member_id"])
        for x in staff_rows(
            mem,
            target_id,
            PREVIOUS_YEAR_ID,
        )
        if x["staff_member_id"]
        is not None
    }


    staff_overlap = sorted(
        source_ids
        & target_ids
    )


    print()
    print(
        case[
            "operation_id"
        ]
    )

    print(
        "SOURCE 2025-2026 =",
        source_prev,
    )

    print(
        "TARGET 2025-2026 =",
        target_prev,
    )

    print(
        "SOURCE 2026-2027 =",
        source_current,
    )

    print(
        "TARGET 2026-2027 =",
        target_current,
    )

    print(
        "STAFF OVERLAP PREVIOUS =",
        staff_overlap,
    )


    if (
        source_prev[
            "DUPLICATE_IDS"
        ]
        or target_prev[
            "DUPLICATE_IDS"
        ]
    ):

        raise RuntimeError(
            "DUNG: du lieu 2025-2026 "
            "co staff duplicate noi bo."
        )


    if staff_overlap:

        raise RuntimeError(
            "DUNG: cung mot staff_member_id "
            "dang nam o ca 2 truong nguon."
        )


    # Để đúng logic rollover hiện tại,
    # 4 trường hợp này phải chưa có đội ngũ
    # 2026-2027 trước khi sáp nhập.
    if (
        source_current[
            "TOTAL"
        ] != 0
        or target_current[
            "TOTAL"
        ] != 0
    ):

        raise RuntimeError(
            "DUNG: da co staff 2026-2027 "
            "tai source/target; can chan doan rieng."
        )


    expected_staff[
        case[
            "operation_id"
        ]
    ] = {
        "TOTAL":
            source_prev["TOTAL"]
            + target_prev["TOTAL"],

        "CBQL":
            source_prev["CBQL"]
            + target_prev["CBQL"],

        "GIAO_VIEN":
            source_prev["GIAO_VIEN"]
            + target_prev["GIAO_VIEN"],

        "NHAN_VIEN":
            source_prev["NHAN_VIEN"]
            + target_prev["NHAN_VIEN"],
    }


# ============================================================
# 7. SIMULATION
# ============================================================

print()
print("=" * 150)
print("7. MO PHONG 4 PHUONG AN")
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

        op = case[
            "operation_id"
        ]

        source_id = case[
            "source_id"
        ]

        target_id = case[
            "target_id"
        ]


        print()
        print("#" * 150)

        print(
            f"[{index}/4] {op}"
        )

        print(
            "SOURCE 1 -> TARGET NGUON 2"
        )

        print(
            source_id,
            "->",
            target_id,
        )

        print(
            "DOI TEN:",
            case[
                "target_old_name"
            ],
            "->",
            case[
                "target_new_name"
            ],
        )


        pre_residual_source = residual(
            mem,
            [source_id],
            move_year_ids,
        )


        pre_residual_target = residual(
            mem,
            [target_id],
            move_year_ids,
        )


        print(
            "residual source truoc =",
            pre_residual_source,
        )

        print(
            "residual target truoc =",
            pre_residual_target,
        )


        (
            checked_target,
            checked_sources,
            selection_blockers,
            selection_warnings,
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
            "selection blockers =",
            selection_blockers,
        )

        print(
            "selection warnings =",
            selection_warnings,
        )


        if selection_blockers:

            raise RuntimeError(
                op
                + ": selection blocker = "
                + repr(
                    selection_blockers
                )
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
                "THCS-4-SPECIAL-RAM-DRY-RUN"
            ),
            record_audit=False,
        )


        # ====================================================
        # RENAME ON RAM
        # ====================================================

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
                + ": target da co history doi ten 2026-2027."
            )


        old_name_now = str(
            mem.execute(
                """
                SELECT name
                FROM schools
                WHERE id=?
                """,
                (
                    target_id,
                ),
            ).fetchone()[0]
        )


        if (
            old_name_now
            != case[
                "target_old_name"
            ]
        ):

            raise RuntimeError(
                op
                + ": ten target truoc rename khong dung."
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
            VALUES (
                ?,?,?,?,?,?
            )
            """,
            (
                target_id,
                YEAR_ID,
                old_name_now,
                case[
                    "target_new_name"
                ],
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
                case[
                    "target_new_name"
                ],
                target_id,
            ),
        )


        if cur.rowcount != 1:

            raise RuntimeError(
                op
                + ": rename RAM khong cap nhat dung 1 target."
            )


        # ====================================================
        # POSTCHECK
        # ====================================================

        source_after = school_row(
            mem,
            source_id,
        )

        target_after = school_row(
            mem,
            target_id,
        )


        staff_after = staff_state(
            mem,
            target_id,
            YEAR_ID,
        )


        expected = expected_staff[
            op
        ]


        post_residual = residual(
            mem,
            [
                source_id
            ],
            move_year_ids,
        )


        source_users = source_user_state(
            mem,
            source_id,
        )


        history = mem.execute(
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
                    target_after[
                        "id"
                    ]
                )
                == target_id,

            "target_code_preserved":
                str(
                    target_after[
                        "code"
                    ]
                )
                == case[
                    "target_code"
                ],

            "target_name_new":
                str(
                    target_after[
                        "name"
                    ]
                )
                == case[
                    "target_new_name"
                ],

            "source_residual_zero":
                not bool(
                    post_residual
                ),

            "source_active_user_zero":
                source_users[
                    "active"
                ]
                == 0,

            "source_school_login_zero":
                source_users[
                    "school_login"
                ]
                == 0,

            "staff_total":
                staff_after[
                    "TOTAL"
                ]
                == expected[
                    "TOTAL"
                ],

            "staff_cbql":
                staff_after[
                    "CBQL"
                ]
                == expected[
                    "CBQL"
                ],

            "staff_gv":
                staff_after[
                    "GIAO_VIEN"
                ]
                == expected[
                    "GIAO_VIEN"
                ],

            "staff_nv":
                staff_after[
                    "NHAN_VIEN"
                ]
                == expected[
                    "NHAN_VIEN"
                ],

            "staff_duplicate_zero":
                not bool(
                    staff_after[
                        "DUPLICATE_IDS"
                    ]
                ),

            "rename_history_one":
                len(history)
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
            expected,
        )

        print(
            "ACTUAL STAFF   =",
            staff_after,
        )

        print(
            "SOURCE AFTER   =",
            source_after,
        )

        print(
            "TARGET AFTER   =",
            target_after,
        )

        print(
            "SOURCE USERS   =",
            source_users,
        )

        print(
            "RESIDUAL AFTER =",
            post_residual,
        )

        print(
            "RENAME HISTORY =",
            [
                dict(x)
                for x in history
            ],
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
                case[
                    "target_code"
                ],

            "new_name":
                case[
                    "target_new_name"
                ],

            "expected_staff":
                expected,

            "actual_staff":
                staff_after,

            "status":
                "PASS",
        })


    # ========================================================
    # 8. GLOBAL CHECK
    # ========================================================

    print()
    print("=" * 150)
    print("8. HAU KIEM TONG TREN RAM")
    print("=" * 150)


    source_ids = [
        x[
            "source_id"
        ]
        for x in CASES
    ]


    target_ids = [
        x[
            "target_id"
        ]
        for x in CASES
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
            + marks(
                len(target_ids)
            )
            + ") "
            "GROUP BY staff_member_id "
            "HAVING COUNT(DISTINCT school_id)>1 "
            "ORDER BY staff_member_id"
        ),
        [
            YEAR_ID,
            *target_ids,
        ],
    ).fetchall()


    past_hash_after = snapshot_past(
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


    print(
        "PASS COUNT        =",
        len(results),
        "/ 4",
    )

    print(
        "ACTIVE SOURCES    =",
        active_sources,
    )

    print(
        "ACTIVE TARGETS    =",
        active_targets,
        "/ 4",
    )

    print(
        "SOURCE RESIDUAL   =",
        global_residual,
    )

    print(
        "CROSS STAFF DUP   =",
        [
            dict(x)
            for x in cross_duplicate
        ],
    )

    print(
        "PAST HASH BEFORE  =",
        past_hash_before,
    )

    print(
        "PAST HASH AFTER   =",
        past_hash_after,
    )

    print(
        "PAST EXACT        =",
        past_hash_before
        == past_hash_after,
    )

    print(
        "RAM INTEGRITY     =",
        integrity_ram,
    )

    print(
        "RAM FK            =",
        len(
            fk_ram
        ),
    )


    global_pass = (
        len(results) == 4

        and active_sources == 0

        and active_targets == 4

        and not global_residual

        and not cross_duplicate

        and past_hash_before
            == past_hash_after

        and integrity_ram.lower()
            == "ok"

        and len(fk_ram)
            == 0
    )


finally:

    try:
        mem.rollback()
    except Exception:
        pass

    mem.close()


# ============================================================
# 9. VERIFY REAL FILES UNCHANGED
# ============================================================

print()
print("=" * 150)
print("9. FILE THAT SAU DRY-RUN")
print("=" * 150)


for key, path in PATHS.items():

    after = sha256(
        path
    )

    print(
        key,
        ":",
        before_hash[
            key
        ],
        "->",
        after,
    )

    if (
        after
        != before_hash[
            key
        ]
    ):

        raise RuntimeError(
            "DUNG: "
            + key
            + " bi thay doi."
        )


print()
print("=" * 150)


if global_pass:

    print(
        "DRY-RUN 4 PHUONG AN THCS: PASS"
    )

    print("=" * 150)

    for row in results:

        print(
            row[
                "operation_id"
            ],
            "|",
            row[
                "source_id"
            ],
            "->",
            row[
                "target_id"
            ],
            "| code=",
            row[
                "target_code"
            ],
            "| name=",
            row[
                "new_name"
            ],
            "| staff=",
            row[
                "actual_staff"
            ][
                "TOTAL"
            ],
            "| PASS"
        )

    print()
    print(
        "4 SOURCE 1            = INACTIVE TREN RAM"
    )

    print(
        "4 SOURCE 2 / TARGET    = ACTIVE TREN RAM"
    )

    print(
        "TARGET SCHOOL_ID       = GIU NGUYEN"
    )

    print(
        "TARGET CODE            = GIU NGUYEN"
    )

    print(
        "TARGET NAME            = DOI THEO QD3805"
    )

    print(
        "CURRENT/FUTURE SOURCE  = 0"
    )

    print(
        "PAST                    = GIU NGUYEN EXACT"
    )

    print(
        "DUPLICATE STAFF         = 0"
    )

    print(
        "RAM INTEGRITY           = OK"
    )

    print(
        "RAM FOREIGN KEY         = 0"
    )

    print(
        "DATABASE THAT           = KHONG THAY DOI"
    )

    print(
        "SAP NHAP THAT           = CHUA CHAY"
    )

    print()
    print(
        "READY_FOR_OFFICIAL_THCS_SPECIAL_4=YES"
    )

else:

    print(
        "DRY-RUN 4 PHUONG AN THCS: FAIL"
    )

    print()
    print(
        "READY_FOR_OFFICIAL_THCS_SPECIAL_4=NO"
    )


print("=" * 150)


if not global_pass:

    raise SystemExit(2)
