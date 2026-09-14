# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import sys
from collections import Counter
from datetime import datetime
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

LEVEL_SERVICE_FILE = (
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

PLAN_FILE = (
    ROOT
    / "data"
    / "school_merger_approved_plans.json"
)

EXPORTS = ROOT / "exports"


YEAR_ID = 2
YEAR_CODE = "2026-2027"
PREVIOUS_YEAR_ID = 1


EXPECTED_HASH = {
    "db":
        "c6a0f2f1a08e7e80a6e89cd0edfd83961f4d87930d5b8b1f3cdae8e770f4deee",

    "engine":
        "414fb49a4c5f4fed7b571cc55df381678fe660cd8a675ecaa2f6fd70ebd7827a",

    "level_service":
        "9104fb99c78755e9eec86d090659b3a922834ff097d7292aa4d4b29e360a27f9",

    "resolution":
        "d9d347b19de0795553c8f047cb91a430ded63d9232ac7eda7ea069b716c2c0f4",
}


CONFIRM = (
    "THUC HIEN 4 THCS DAC THU NGUON 2 LAM DICH"
)


ACTOR = {
    "id": 1,
    "username": "admin.sogddt",
    "full_name": "Đậu Hồng Nam",
}


CASES = [
    {
        "operation_id":
            "QD3805-OP-0399",

        "plan_id":
            "PA2026-35F6C2558FC4",

        "commune_id":
            10,

        "source_id":
            1592,

        "source_code":
            "40415505",

        "source_name":
            "THCS Quang Phong",

        "target_id":
            1594,

        "target_code":
            "40415510",

        "target_old_name":
            "Trường THCS Cắm Muộn",

        "target_new_name":
            "THCS Mường Quàng",

        "expected": {
            "TOTAL": 50,
            "QUAN_LY": 4,
            "GIAO_VIEN": 41,
            "NHAN_VIEN": 5,
            "EXCLUDED": 1,
        },
    },

    {
        "operation_id":
            "QD3805-OP-0424",

        "plan_id":
            "PA2026-F228D672FCAC",

        "commune_id":
            12,

        "source_id":
            1485,

        "source_code":
            "40416506",

        "source_name":
            "Trường THCS Tiến Thắng",

        "target_id":
            1486,

        "target_code":
            "40416507",

        "target_old_name":
            "PTDTBT THCS Bính Thuận",

        "target_new_name":
            "THCS Châu Tiến",

        "expected": {
            "TOTAL": 60,
            "QUAN_LY": 6,
            "GIAO_VIEN": 49,
            "NHAN_VIEN": 5,
            "EXCLUDED": 1,
        },
    },

    {
        "operation_id":
            "QD3805-OP-0434",

        "plan_id":
            "PA2026-6948B60DF298",

        "commune_id":
            11,

        "source_id":
            1647,

        "source_code":
            "40416504",

        "source_name":
            "PTDTBT THCS Hội Nga",

        "target_id":
            1646,

        "target_code":
            "40416501",

        "target_old_name":
            "THCS Hạnh Thiết",

        "target_new_name":
            "THCS Quỳ Châu",

        "expected": {
            "TOTAL": 77,
            "QUAN_LY": 6,
            "GIAO_VIEN": 65,
            "NHAN_VIEN": 6,
            "EXCLUDED": 0,
        },
    },

    {
        "operation_id":
            "QD3805-OP-0451",

        "plan_id":
            "PA2026-CC0F70262554",

        "commune_id":
            51,

        "source_id":
            1589,

        "source_code":
            "40420509",

        "source_name":
            "THCS Châu Thái",

        "target_id":
            1590,

        "target_code":
            "40420518",

        "target_old_name":
            "THCS Châu Cường",

        "target_new_name":
            "THCS Mường Ham",

        "expected": {
            "TOTAL": 57,
            "QUAN_LY": 3,
            "GIAO_VIEN": 46,
            "NHAN_VIEN": 8,
            "EXCLUDED": 0,
        },
    },
]


def sha256(path: Path) -> str:

    h = hashlib.sha256()

    with path.open("rb") as f:

        for block in iter(
            lambda: f.read(
                1024 * 1024
            ),
            b"",
        ):
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


def marks(n: int) -> str:

    return ",".join(
        "?"
        for _ in range(n)
    )


def connect_ro(
    path: Path = DB,
):

    con = sqlite3.connect(
        path.resolve().as_uri()
        + "?mode=ro",
        uri=True,
        timeout=120,
    )

    con.row_factory = (
        sqlite3.Row
    )

    con.execute(
        "PRAGMA query_only=ON"
    )

    con.execute(
        "PRAGMA foreign_keys=ON"
    )

    return con


def db_health(con):

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

    return (
        integrity,
        fk,
    )


def sqlite_backup(
    source: Path,
    target: Path,
):

    src = sqlite3.connect(
        str(source),
        timeout=120,
    )

    dst = sqlite3.connect(
        str(target),
        timeout=120,
    )

    try:

        src.backup(
            dst
        )

        dst.commit()

    finally:

        dst.close()

        src.close()


def sqlite_restore(
    source: Path,
    target: Path,
):

    src = sqlite3.connect(
        str(source),
        timeout=120,
    )

    dst = sqlite3.connect(
        str(target),
        timeout=120,
    )

    try:

        src.backup(
            dst
        )

        dst.commit()

    finally:

        dst.close()

        src.close()


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
            row[0]
        )

        cols = {
            str(x[1])
            for x in con.execute(
                f"""
                PRAGMA table_info(
                    {qident(table)}
                )
                """
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


def past_snapshot(
    con,
    school_ids,
    year_ids,
):

    payload = {}

    for table in year_tables(
        con
    ):

        cols = [
            str(x[1])
            for x in con.execute(
                f"""
                PRAGMA table_info(
                    {qident(table)}
                )
                """
            ).fetchall()
        ]

        rows = con.execute(
            (
                "SELECT * FROM "
                + qident(table)
                + " WHERE school_id IN ("
                + marks(
                    len(
                        school_ids
                    )
                )
                + ") "
                + "AND school_year_id IN ("
                + marks(
                    len(
                        year_ids
                    )
                )
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
                    encode(
                        row[col]
                    )
                    for col in cols
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
            "columns":
                cols,

            "rows":
                normalized,
        }

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

    return hashlib.sha256(
        raw
    ).hexdigest()


def residual(
    con,
    school_ids,
    year_ids,
):

    out = {}

    for table in year_tables(
        con
    ):

        n = int(
            con.execute(
                (
                    "SELECT COUNT(*) FROM "
                    + qident(table)
                    + " WHERE school_id IN ("
                    + marks(
                        len(
                            school_ids
                        )
                    )
                    + ") "
                    + "AND school_year_id IN ("
                    + marks(
                        len(
                            year_ids
                        )
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

            out[
                table
            ] = n

    return out


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
            int(
                school_id
            ),
        ),
    ).fetchone()

    return (
        dict(row)
        if row
        else None
    )


def engine_expected(
    con,
    merger,
    case,
):

    origin_ids = [
        int(
            case[
                "source_id"
            ]
        ),
        int(
            case[
                "target_id"
            ]
        ),
    ]

    rows = con.execute(
        (
            "SELECT * "
            "FROM staff_year_records "
            "WHERE school_year_id=? "
            "AND school_id IN ("
            + marks(
                len(
                    origin_ids
                )
            )
            + ") "
            "ORDER BY school_id,id"
        ),
        [
            PREVIOUS_YEAR_ID,
            *origin_ids,
        ],
    ).fetchall()

    groups = Counter()

    excluded = []

    seen = Counter()

    for row in rows:

        staff_id = int(
            row[
                "staff_member_id"
            ]
        )

        seen[
            staff_id
        ] += 1

        category = (
            merger._classify_staff(
                row
            )
        )

        if (
            category
            == "CHUA_XAC_DINH"
        ):

            raise RuntimeError(
                case[
                    "operation_id"
                ]
                + ": không phân loại được "
                + f"staff_member_id={staff_id}"
            )

        if merger._staff_inactive(
            row
        ):

            excluded.append({
                "record_id":
                    int(
                        row["id"]
                    ),

                "staff_member_id":
                    staff_id,

                "school_id":
                    int(
                        row["school_id"]
                    ),

                "category":
                    category,

                "status_code":
                    (
                        row[
                            "status_code"
                        ]
                        if "status_code"
                        in row.keys()
                        else None
                    ),

                "source_status_label":
                    (
                        row[
                            "source_status_label"
                        ]
                        if "source_status_label"
                        in row.keys()
                        else None
                    ),
            })

            continue

        groups[
            category
        ] += 1

    duplicate = {
        key:
            value

        for key, value
        in seen.items()

        if value > 1
    }

    if duplicate:

        raise RuntimeError(
            case[
                "operation_id"
            ]
            + ": trùng staff_member_id "
            + repr(
                duplicate
            )
        )

    return {
        "TOTAL":
            sum(
                groups.values()
            ),

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

        "EXCLUDED":
            len(
                excluded
            ),

        "excluded_rows":
            excluded,
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
            int(
                school_id
            ),
            YEAR_ID,
        ),
    ).fetchall()

    groups = Counter()

    staff_ids = []

    for row in rows:

        category = (
            merger._classify_staff(
                row
            )
        )

        groups[
            category
        ] += 1

        if (
            row[
                "staff_member_id"
            ]
            is not None
        ):

            staff_ids.append(
                int(
                    row[
                        "staff_member_id"
                    ]
                )
            )

    duplicate = {
        key:
            value

        for key, value
        in Counter(
            staff_ids
        ).items()

        if value > 1
    }

    return {
        "TOTAL":
            len(
                rows
            ),

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
            int(
                school_id
            ),
        ),
    ).fetchone()

    return {
        "total":
            int(
                row[
                    "total"
                ]
                or 0
            ),

        "active":
            int(
                row[
                    "active"
                ]
                or 0
            ),

        "school_login":
            int(
                row[
                    "school_login"
                ]
                or 0
            ),
    }


def case_fingerprint(
    case,
):

    payload = {
        "base_db_sha":
            EXPECTED_HASH[
                "db"
            ],

        "operation_id":
            case[
                "operation_id"
            ],

        "plan_id":
            case[
                "plan_id"
            ],

        "school_year_id":
            YEAR_ID,

        "source_id":
            case[
                "source_id"
            ],

        "target_id":
            case[
                "target_id"
            ],

        "target_code":
            case[
                "target_code"
            ],

        "target_old_name":
            case[
                "target_old_name"
            ],

        "target_new_name":
            case[
                "target_new_name"
            ],

        "expected":
            case[
                "expected"
            ],

        "policy":
            "SOURCE_2_IS_TARGET",
    }

    raw = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(
            ",",
            ":",
        ),
    ).encode(
        "utf-8"
    )

    return hashlib.sha256(
        raw
    ).hexdigest()


def verify_identity_and_pending(
    con,
    official_table,
):

    actor = con.execute(
        """
        SELECT
            id,
            username,
            is_active
        FROM users
        WHERE id=?
        """,
        (
            ACTOR["id"],
        ),
    ).fetchone()

    if (
        actor is None
        or str(
            actor["username"]
            or ""
        )
        != ACTOR["username"]
        or int(
            actor["is_active"]
            or 0
        )
        != 1
    ):

        raise RuntimeError(
            "Actor admin.sogddt "
            "không còn đúng/active."
        )

    for case in CASES:

        source = school_row(
            con,
            case[
                "source_id"
            ],
        )

        target = school_row(
            con,
            case[
                "target_id"
            ],
        )

        if (
            source is None
            or target is None
        ):

            raise RuntimeError(
                case[
                    "operation_id"
                ]
                + ": thiếu source/target."
            )

        valid = (
            int(
                source[
                    "commune_id"
                ]
            )
            == case[
                "commune_id"
            ]

            and int(
                target[
                    "commune_id"
                ]
            )
            == case[
                "commune_id"
            ]

            and str(
                source[
                    "code"
                ]
            )
            == case[
                "source_code"
            ]

            and str(
                target[
                    "code"
                ]
            )
            == case[
                "target_code"
            ]

            and str(
                source[
                    "name"
                ]
            )
            == case[
                "source_name"
            ]

            and str(
                target[
                    "name"
                ]
            )
            == case[
                "target_old_name"
            ]

            and int(
                source[
                    "is_active"
                ]
                or 0
            )
            == 1

            and int(
                target[
                    "is_active"
                ]
                or 0
            )
            == 1
        )

        if not valid:

            raise RuntimeError(
                case[
                    "operation_id"
                ]
                + ": danh tính/trạng thái "
                  "không còn đúng."
                + "\nSOURCE="
                + repr(
                    source
                )
                + "\nTARGET="
                + repr(
                    target
                )
            )

        hist = int(
            con.execute(
                """
                SELECT COUNT(*)
                FROM school_name_histories
                WHERE school_id=?
                  AND effective_school_year_id=?
                """,
                (
                    case[
                        "target_id"
                    ],
                    YEAR_ID,
                ),
            ).fetchone()[0]
            or 0
        )

        if hist != 0:

            raise RuntimeError(
                case[
                    "operation_id"
                ]
                + ": target đã có lịch sử "
                  "đổi tên 2026-2027; "
                  "không chạy lại."
            )

        official = int(
            con.execute(
                (
                    "SELECT COUNT(*) "
                    "FROM "
                    + qident(
                        official_table
                    )
                    + " WHERE plan_id=? "
                      "AND school_year_id=?"
                ),
                (
                    case[
                        "plan_id"
                    ],
                    YEAR_ID,
                ),
            ).fetchone()[0]
            or 0
        )

        if official != 0:

            raise RuntimeError(
                case[
                    "operation_id"
                ]
                + ": đã có official execution; "
                  "không chạy lại."
            )

        old_audit = int(
            con.execute(
                """
                SELECT COUNT(*)
                FROM school_merger_operations
                WHERE school_year_id=?
                  AND summary_json LIKE ?
                """,
                (
                    YEAR_ID,
                    "%"
                    + case[
                        "operation_id"
                    ]
                    + "%",
                ),
            ).fetchone()[0]
            or 0
        )

        if old_audit != 0:

            raise RuntimeError(
                case[
                    "operation_id"
                ]
                + ": đã có audit operation; "
                  "không chạy lại."
            )


def global_postcheck(
    con,
    merger,
    official_table,
    batch_table,
    move_year_ids,
    past_year_ids,
    past_before,
    backup_name,
):

    source_ids = [
        int(
            case[
                "source_id"
            ]
        )
        for case in CASES
    ]

    target_ids = [
        int(
            case[
                "target_id"
            ]
        )
        for case in CASES
    ]

    involved_ids = sorted(
        set(
            source_ids
            + target_ids
        )
    )

    active_sources = int(
        con.execute(
            (
                "SELECT COUNT(*) "
                "FROM schools "
                "WHERE id IN ("
                + marks(
                    len(
                        source_ids
                    )
                )
                + ") "
                "AND is_active=1"
            ),
            source_ids,
        ).fetchone()[0]
        or 0
    )

    active_targets = int(
        con.execute(
            (
                "SELECT COUNT(*) "
                "FROM schools "
                "WHERE id IN ("
                + marks(
                    len(
                        target_ids
                    )
                )
                + ") "
                "AND is_active=1"
            ),
            target_ids,
        ).fetchone()[0]
        or 0
    )

    source_residual = residual(
        con,
        source_ids,
        move_year_ids,
    )

    past_after = past_snapshot(
        con,
        involved_ids,
        past_year_ids,
    )

    target_results = []

    for case in CASES:

        source = school_row(
            con,
            case[
                "source_id"
            ],
        )

        target = school_row(
            con,
            case[
                "target_id"
            ],
        )

        staff = current_staff_state(
            con,
            merger,
            case[
                "target_id"
            ],
        )

        users = source_user_state(
            con,
            case[
                "source_id"
            ],
        )

        history_rows = con.execute(
            """
            SELECT
                old_name,
                new_name
            FROM school_name_histories
            WHERE school_id=?
              AND effective_school_year_id=?
            """,
            (
                case[
                    "target_id"
                ],
                YEAR_ID,
            ),
        ).fetchall()

        expected = case[
            "expected"
        ]

        ok = (
            source
            is not None

            and target
            is not None

            and int(
                source[
                    "is_active"
                ]
                or 0
            )
            == 0

            and int(
                target[
                    "is_active"
                ]
                or 0
            )
            == 1

            and str(
                target[
                    "code"
                ]
            )
            == case[
                "target_code"
            ]

            and str(
                target[
                    "name"
                ]
            )
            == case[
                "target_new_name"
            ]

            and users[
                "active"
            ]
            == 0

            and users[
                "school_login"
            ]
            == 0

            and staff[
                "TOTAL"
            ]
            == expected[
                "TOTAL"
            ]

            and staff[
                "QUAN_LY"
            ]
            == expected[
                "QUAN_LY"
            ]

            and staff[
                "GIAO_VIEN"
            ]
            == expected[
                "GIAO_VIEN"
            ]

            and staff[
                "NHAN_VIEN"
            ]
            == expected[
                "NHAN_VIEN"
            ]

            and not staff[
                "DUPLICATE"
            ]

            and len(
                history_rows
            )
            == 1

            and str(
                history_rows[0][
                    "old_name"
                ]
            )
            == case[
                "target_old_name"
            ]

            and str(
                history_rows[0][
                    "new_name"
                ]
            )
            == case[
                "target_new_name"
            ]
        )

        target_results.append({
            "operation_id":
                case[
                    "operation_id"
                ],

            "source_id":
                case[
                    "source_id"
                ],

            "target_id":
                case[
                    "target_id"
                ],

            "target_code":
                (
                    target[
                        "code"
                    ]
                    if target
                    else None
                ),

            "target_name":
                (
                    target[
                        "name"
                    ]
                    if target
                    else None
                ),

            "staff":
                staff,

            "source_users":
                users,

            "rename_history_count":
                len(
                    history_rows
                ),

            "pass":
                ok,
        })

    target_staff_ids = [
        int(
            x[0]
        )
        for x in con.execute(
            (
                "SELECT DISTINCT "
                "staff_member_id "
                "FROM staff_year_records "
                "WHERE school_year_id=? "
                "AND is_active=1 "
                "AND staff_member_id "
                "IS NOT NULL "
                "AND school_id IN ("
                + marks(
                    len(
                        target_ids
                    )
                )
                + ")"
            ),
            [
                YEAR_ID,
                *target_ids,
            ],
        ).fetchall()
    ]

    duplicate_anywhere = []

    if target_staff_ids:

        duplicate_anywhere = [
            dict(x)
            for x in con.execute(
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

    plan_ids = [
        case[
            "plan_id"
        ]
        for case in CASES
    ]

    official_count = int(
        con.execute(
            (
                "SELECT COUNT(*) FROM "
                + qident(
                    official_table
                )
                + " WHERE school_year_id=? "
                + "AND plan_id IN ("
                + marks(
                    len(
                        plan_ids
                    )
                )
                + ")"
            ),
            [
                YEAR_ID,
                *plan_ids,
            ],
        ).fetchone()[0]
        or 0
    )

    audit_count = int(
        con.execute(
            """
            SELECT COUNT(*)
            FROM school_merger_operations
            WHERE backup_name=?
            """,
            (
                backup_name,
            ),
        ).fetchone()[0]
        or 0
    )

    thcs_batch_count = int(
        con.execute(
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

    integrity, fk = db_health(
        con
    )

    total_staff = sum(
        x[
            "staff"
        ][
            "TOTAL"
        ]
        for x in target_results
    )

    total_ql = sum(
        x[
            "staff"
        ][
            "QUAN_LY"
        ]
        for x in target_results
    )

    total_gv = sum(
        x[
            "staff"
        ][
            "GIAO_VIEN"
        ]
        for x in target_results
    )

    total_nv = sum(
        x[
            "staff"
        ][
            "NHAN_VIEN"
        ]
        for x in target_results
    )

    passed = (
        active_sources
        == 0

        and active_targets
        == 4

        and not source_residual

        and past_before
        == past_after

        and all(
            x[
                "pass"
            ]
            for x in target_results
        )

        and not duplicate_anywhere

        and official_count
        == 4

        and audit_count
        == 4

        and thcs_batch_count
        == 1

        and integrity.lower()
        == "ok"

        and fk
        == 0

        and (
            total_staff,
            total_ql,
            total_gv,
            total_nv,
        )
        == (
            244,
            19,
            201,
            24,
        )
    )

    return {
        "passed":
            passed,

        "active_sources":
            active_sources,

        "active_targets":
            active_targets,

        "source_residual":
            source_residual,

        "past_before":
            past_before,

        "past_after":
            past_after,

        "past_exact":
            past_before
            == past_after,

        "target_results":
            target_results,

        "duplicate_staff_anywhere":
            duplicate_anywhere,

        "official_count":
            official_count,

        "audit_count":
            audit_count,

        "thcs_batch_count":
            thcs_batch_count,

        "integrity":
            integrity,

        "fk":
            fk,

        "total_staff":
            total_staff,

        "total_quan_ly":
            total_ql,

        "total_giao_vien":
            total_gv,

        "total_nhan_vien":
            total_nv,
    }


def main():

    parser = (
        argparse.ArgumentParser()
    )

    parser.add_argument(
        "--apply",
        action="store_true",
    )

    parser.add_argument(
        "--confirm",
        default="",
    )

    args = parser.parse_args()

    print("=" * 150)
    print(
        "THCS - 4 PHUONG AN DAC THU - "
        "NGUON 2 LAM DICH"
    )
    print(
        "CHE DO =",
        (
            "GHI DATABASE THAT"
            if args.apply
            else "PREFLIGHT CHI DOC"
        ),
    )
    print("=" * 150)

    paths = {
        "db":
            DB,

        "engine":
            ENGINE_FILE,

        "level_service":
            LEVEL_SERVICE_FILE,

        "resolution":
            RESOLUTION_FILE,
    }

    for key, path in paths.items():

        if not path.exists():

            raise RuntimeError(
                f"Không tìm thấy {path}"
            )

        value = sha256(
            path
        )

        print(
            f"{key:14s} = {value}"
        )

        if (
            value
            != EXPECTED_HASH[
                key
            ]
        ):

            raise RuntimeError(
                "DUNG: hash "
                + key
                + " không còn đúng "
                  "nền dry-run."
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
                "DUNG: WAL/JOURNAL "
                "khác 0. "
                "Hãy dừng Uvicorn/server."
            )

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

    official_table = str(
        levelsvc.OFFICIAL_EXECUTION_TABLE
    )

    batch_table = str(
        levelsvc.BATCH_TABLE
    )

    with connect_ro() as con:

        integrity, fk = (
            db_health(
                con
            )
        )

        if (
            integrity.lower()
            != "ok"
            or fk
        ):

            raise RuntimeError(
                "DB health FAIL: "
                + f"integrity={integrity}, "
                + f"FK={fk}"
            )

        year = con.execute(
            """
            SELECT
                id,
                code
            FROM school_years
            WHERE id=?
            """,
            (
                YEAR_ID,
            ),
        ).fetchone()

        if (
            year is None
            or str(
                year["code"]
                or ""
            )
            != YEAR_CODE
        ):

            raise RuntimeError(
                "school_year_id=2 "
                "không còn là 2026-2027."
            )

        batch_count = int(
            con.execute(
                (
                    "SELECT COUNT(*) "
                    "FROM "
                    + qident(
                        batch_table
                    )
                    + " WHERE "
                    "school_year_id=? "
                    "AND level_code='THCS'"
                ),
                (
                    YEAR_ID,
                ),
            ).fetchone()[0]
            or 0
        )

        if batch_count != 1:

            raise RuntimeError(
                "THCS batch count="
                + str(
                    batch_count
                )
                + "; cần đúng 1 "
                  "batch đã hoàn tất."
            )

        verify_identity_and_pending(
            con,
            official_table,
        )

        (
            move_year_ids,
            past_year_ids,
        ) = merger._year_scope_ids(
            con,
            YEAR_ID,
        )

        previous_year_id = (
            merger._previous_year_id(
                con,
                YEAR_ID,
            )
        )

        if move_year_ids != [
            2,
            8,
        ]:

            raise RuntimeError(
                "CURRENT/FUTURE="
                + repr(
                    move_year_ids
                )
                + "; cần [2,8]."
            )

        if (
            previous_year_id
            != PREVIOUS_YEAR_ID
        ):

            raise RuntimeError(
                "previous_year_id="
                + str(
                    previous_year_id
                )
                + "; cần 1."
            )

        for case in CASES:

            expected = (
                engine_expected(
                    con,
                    merger,
                    case,
                )
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

                if (
                    expected[key]
                    != hard[key]
                ):

                    raise RuntimeError(
                        case[
                            "operation_id"
                        ]
                        + ": expected "
                        + key
                        + "="
                        + str(
                            expected[key]
                        )
                        + ", cần "
                        + str(
                            hard[key]
                        )
                    )

            current_source = (
                current_staff_state(
                    con,
                    merger,
                    case[
                        "source_id"
                    ],
                )
            )

            current_target = (
                current_staff_state(
                    con,
                    merger,
                    case[
                        "target_id"
                    ],
                )
            )

            if (
                current_source[
                    "TOTAL"
                ]
                != 0

                or current_target[
                    "TOTAL"
                ]
                != 0
            ):

                raise RuntimeError(
                    case[
                        "operation_id"
                    ]
                    + ": đã có đội ngũ "
                      "2026-2027 tại "
                      "source/target."
                )

        print()
        print("PREFLIGHT PASS")
        print(
            " - THCS batch hiện có: 1"
        )
        print(
            " - Script KHÔNG tạo "
            "batch THCS mới"
        )
        print(
            " - 4 official plan "
            "chưa có execution"
        )
        print(
            " - Đội ngũ dự kiến: "
            "244 = QL 19 + "
            "GV 201 + NV 24"
        )
        print(
            " - 2 hồ sơ nghỉ/chuyển "
            "chỉ giữ lịch sử"
        )

    if not args.apply:

        print()
        print(
            "DATABASE = CHUA THAY DOI"
        )

        return 0

    if (
        args.confirm.strip()
        != CONFIRM
    ):

        raise RuntimeError(
            "Sai câu xác nhận; "
            "chưa ghi gì."
        )

    stamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    backup_dir = (
        EXPORTS
        / (
            "backup_truoc_"
            "THCS_dac_thu_4_"
            + stamp
        )
    )

    backup_dir.mkdir(
        parents=True,
        exist_ok=False,
    )

    backup_db = (
        backup_dir
        / "phocap.db"
    )

    backup_resolution = (
        backup_dir
        / RESOLUTION_FILE.name
    )

    backup_plan = (
        backup_dir
        / PLAN_FILE.name
    )

    print()
    print(
        "TAO BACKUP "
        "TRUOC KHI GHI..."
    )

    sqlite_backup(
        DB,
        backup_db,
    )

    shutil.copy2(
        RESOLUTION_FILE,
        backup_resolution,
    )

    if PLAN_FILE.exists():

        shutil.copy2(
            PLAN_FILE,
            backup_plan,
        )

    with connect_ro(
        backup_db
    ) as chk:

        bi, bf = db_health(
            chk
        )

        if (
            bi.lower()
            != "ok"
            or bf
        ):

            raise RuntimeError(
                "Backup DB lỗi: "
                + f"integrity={bi}, "
                + f"FK={bf}"
            )

    metadata = {
        "backup_type":
            "before_THCS_special_4_"
            "source2_target",

        "created_at":
            datetime.now().isoformat(
                timespec="seconds"
            ),

        "base_db_sha":
            EXPECTED_HASH[
                "db"
            ],

        "school_year_id":
            YEAR_ID,

        "policy":
            "SOURCE_2_IS_TARGET",

        "cases":
            CASES,

        "status":
            "CREATED_BEFORE_"
            "TRANSACTION_MUTATION",
    }

    (
        backup_dir
        / "metadata.json"
    ).write_text(
        json.dumps(
            metadata,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    backup_name = (
        backup_dir.name
    )

    con = sqlite3.connect(
        str(DB),
        timeout=120,
    )

    con.row_factory = (
        sqlite3.Row
    )

    con.execute(
        "PRAGMA foreign_keys=ON"
    )

    committed = False
    post_verified = False
    past_before = ""
    operation_results = []

    try:

        con.execute(
            "BEGIN IMMEDIATE"
        )

        verify_identity_and_pending(
            con,
            official_table,
        )

        (
            move_year_ids,
            past_year_ids,
        ) = merger._year_scope_ids(
            con,
            YEAR_ID,
        )

        previous_year_id = (
            merger._previous_year_id(
                con,
                YEAR_ID,
            )
        )

        if (
            move_year_ids
            != [
                2,
                8,
            ]
            or previous_year_id
            != PREVIOUS_YEAR_ID
        ):

            raise RuntimeError(
                "Year scope thay đổi "
                "trong transaction."
            )

        source_ids = [
            int(
                case[
                    "source_id"
                ]
            )
            for case in CASES
        ]

        target_ids = [
            int(
                case[
                    "target_id"
                ]
            )
            for case in CASES
        ]

        involved_ids = sorted(
            set(
                source_ids
                + target_ids
            )
        )

        past_before = past_snapshot(
            con,
            involved_ids,
            past_year_ids,
        )

        for index, case in enumerate(
            CASES,
            start=1,
        ):

            print()
            print(
                "THUC HIEN "
                + str(index)
                + "/4: "
                + case[
                    "operation_id"
                ]
            )

            print(
                "  "
                + str(
                    case[
                        "source_id"
                    ]
                )
                + " -> "
                + str(
                    case[
                        "target_id"
                    ]
                )
                + " | "
                + case[
                    "target_old_name"
                ]
                + " -> "
                + case[
                    "target_new_name"
                ]
            )

            expected = (
                engine_expected(
                    con,
                    merger,
                    case,
                )
            )

            for key in (
                "TOTAL",
                "QUAN_LY",
                "GIAO_VIEN",
                "NHAN_VIEN",
                "EXCLUDED",
            ):

                if (
                    expected[key]
                    != case[
                        "expected"
                    ][key]
                ):

                    raise RuntimeError(
                        case[
                            "operation_id"
                        ]
                        + ": engine expected "
                          "thay đổi trước apply."
                    )

            (
                _target,
                _sources,
                blockers,
                warnings,
            ) = merger._validate_selection(
                con,
                selected_year_id=(
                    YEAR_ID
                ),
                target_school_id=(
                    case[
                        "target_id"
                    ]
                ),
                source_ids=[
                    case[
                        "source_id"
                    ]
                ],
                require_active_sources=(
                    True
                ),
            )

            if blockers:

                raise RuntimeError(
                    case[
                        "operation_id"
                    ]
                    + ": selection blocker: "
                    + " | ".join(
                        map(
                            str,
                            blockers,
                        )
                    )
                )

            result = merger._apply_merge(
                con,
                selected_year_id=(
                    YEAR_ID
                ),
                previous_year_id=(
                    previous_year_id
                ),
                target_school_id=(
                    case[
                        "target_id"
                    ]
                ),
                source_ids=[
                    case[
                        "source_id"
                    ]
                ],
                actor_user_id=(
                    ACTOR[
                        "id"
                    ]
                ),
                backup_name=(
                    backup_name
                ),
                record_audit=False,
            )

            if (
                int(
                    result.get(
                        "staff_rollover_created"
                    )
                    or 0
                )
                != expected[
                    "TOTAL"
                ]
            ):

                raise RuntimeError(
                    case[
                        "operation_id"
                    ]
                    + ": rollover sai."
                )

            if (
                int(
                    result.get(
                        "staff_existing_elsewhere_skipped"
                    )
                    or 0
                )
                != 0
            ):

                raise RuntimeError(
                    case[
                        "operation_id"
                    ]
                    + ": xuất hiện "
                      "staff_existing_"
                      "elsewhere_skipped."
                )

            if (
                int(
                    result.get(
                        "source_school_logins_disabled"
                    )
                    or 0
                )
                != 1
            ):

                raise RuntimeError(
                    case[
                        "operation_id"
                    ]
                    + ": số login nguồn "
                      "bị khóa khác 1."
                )

            if (
                int(
                    result.get(
                        "sources_deactivated"
                    )
                    or 0
                )
                != 1
            ):

                raise RuntimeError(
                    case[
                        "operation_id"
                    ]
                    + ": nguồn deactivated "
                      "khác 1."
                )

            now_text = (
                datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
            )

            hist = int(
                con.execute(
                    """
                    SELECT COUNT(*)
                    FROM school_name_histories
                    WHERE school_id=?
                      AND effective_school_year_id=?
                    """,
                    (
                        case[
                            "target_id"
                        ],
                        YEAR_ID,
                    ),
                ).fetchone()[0]
                or 0
            )

            if hist != 0:

                raise RuntimeError(
                    case[
                        "operation_id"
                    ]
                    + ": rename history "
                      "xuất hiện bất ngờ."
                )

            target_now = school_row(
                con,
                case[
                    "target_id"
                ],
            )

            if (
                target_now is None
                or str(
                    target_now[
                        "name"
                    ]
                )
                != case[
                    "target_old_name"
                ]
            ):

                raise RuntimeError(
                    case[
                        "operation_id"
                    ]
                    + ": tên target "
                      "trước rename sai."
                )

            duplicate_name = (
                con.execute(
                    """
                    SELECT id,name
                    FROM schools
                    WHERE commune_id=?
                      AND is_active=1
                      AND id<>?
                      AND lower(trim(name))
                          =lower(trim(?))
                    LIMIT 1
                    """,
                    (
                        case[
                            "commune_id"
                        ],
                        case[
                            "target_id"
                        ],
                        case[
                            "target_new_name"
                        ],
                    ),
                ).fetchone()
            )

            if (
                duplicate_name
                is not None
            ):

                raise RuntimeError(
                    case[
                        "operation_id"
                    ]
                    + ": tên đích mới "
                      "đang trùng school_id="
                    + str(
                        duplicate_name[
                            "id"
                        ]
                    )
                )

            con.execute(
                """
                INSERT INTO
                    school_name_histories (
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
                    case[
                        "target_id"
                    ],
                    YEAR_ID,
                    case[
                        "target_old_name"
                    ],
                    case[
                        "target_new_name"
                    ],
                    now_text,
                    ACTOR[
                        "id"
                    ],
                ),
            )

            cur = con.execute(
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
                    case[
                        "target_id"
                    ],
                ),
            )

            if cur.rowcount != 1:

                raise RuntimeError(
                    case[
                        "operation_id"
                    ]
                    + ": rename không "
                      "cập nhật đúng 1 target."
                )

            result.update({
                "official_operation_id":
                    case[
                        "operation_id"
                    ],

                "official_plan_id":
                    case[
                        "plan_id"
                    ],

                "special_execution_type":
                    "THCS_SAME_LEVEL_"
                    "SOURCE2_IS_TARGET",

                "school_year_id":
                    YEAR_ID,

                "source_school_ids": [
                    case[
                        "source_id"
                    ]
                ],

                "source_school_names": [
                    case[
                        "source_name"
                    ]
                ],

                "target_school_id":
                    case[
                        "target_id"
                    ],

                "target_school_code":
                    case[
                        "target_code"
                    ],

                "target_school_old_name":
                    case[
                        "target_old_name"
                    ],

                "target_school_name":
                    case[
                        "target_new_name"
                    ],

                "rename_effective_"
                "school_year_id":
                    YEAR_ID,

                "engine_expected_staff": {
                    key:
                        expected[key]

                    for key in (
                        "TOTAL",
                        "QUAN_LY",
                        "GIAO_VIEN",
                        "NHAN_VIEN",
                        "EXCLUDED",
                    )
                },

                "excluded_historical_staff":
                    expected[
                        "excluded_rows"
                    ],

                "preview_fingerprint":
                    case_fingerprint(
                        case
                    ),

                "backup_name":
                    backup_name,

                "actor":
                    ACTOR,
            })

            summary_json = (
                json.dumps(
                    result,
                    ensure_ascii=False,
                    default=str,
                )
            )

            cur = con.execute(
                """
                INSERT INTO
                    school_merger_operations (
                        school_year_id,
                        target_school_id,
                        source_school_ids_json,
                        actor_user_id,
                        backup_name,
                        summary_json,
                        created_at
                    )
                VALUES (?,?,?,?,?,?,?)
                """,
                (
                    YEAR_ID,
                    case[
                        "target_id"
                    ],
                    json.dumps(
                        [
                            case[
                                "source_id"
                            ]
                        ],
                        ensure_ascii=False,
                    ),
                    ACTOR[
                        "id"
                    ],
                    backup_name,
                    summary_json,
                    now_text,
                ),
            )

            operation_db_id = int(
                cur.lastrowid
            )

            con.execute(
                (
                    "INSERT INTO "
                    + qident(
                        official_table
                    )
                    + " ("
                    "plan_id,"
                    "operation_id,"
                    "school_year_id,"
                    "target_school_id,"
                    "source_school_ids_json,"
                    "actor_user_id,"
                    "actor_username,"
                    "actor_full_name,"
                    "backup_name,"
                    "preview_fingerprint,"
                    "summary_json,"
                    "created_at"
                    ") "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)"
                ),
                (
                    case[
                        "plan_id"
                    ],
                    operation_db_id,
                    YEAR_ID,
                    case[
                        "target_id"
                    ],
                    json.dumps(
                        [
                            case[
                                "source_id"
                            ]
                        ],
                        ensure_ascii=False,
                    ),
                    ACTOR[
                        "id"
                    ],
                    ACTOR[
                        "username"
                    ],
                    ACTOR[
                        "full_name"
                    ],
                    backup_name,
                    case_fingerprint(
                        case
                    ),
                    summary_json,
                    now_text,
                ),
            )

            operation_results.append({
                "operation_id":
                    case[
                        "operation_id"
                    ],

                "plan_id":
                    case[
                        "plan_id"
                    ],

                "operation_db_id":
                    operation_db_id,

                "source_id":
                    case[
                        "source_id"
                    ],

                "target_id":
                    case[
                        "target_id"
                    ],

                "target_code":
                    case[
                        "target_code"
                    ],

                "target_name":
                    case[
                        "target_new_name"
                    ],

                "staff_rollover_created":
                    int(
                        result.get(
                            "staff_rollover_created"
                        )
                        or 0
                    ),

                "excluded_historical":
                    expected[
                        "EXCLUDED"
                    ],
            })

        precommit = global_postcheck(
            con,
            merger,
            official_table,
            batch_table,
            move_year_ids,
            past_year_ids,
            past_before,
            backup_name,
        )

        print()
        print(
            "PRE-COMMIT CHECK:"
        )

        print(
            json.dumps(
                precommit,
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        )

        if not precommit[
            "passed"
        ]:

            raise RuntimeError(
                "PRE-COMMIT CHECK FAIL; "
                "rollback toàn bộ 4 "
                "phương án."
            )

        con.commit()

        committed = True

        post = global_postcheck(
            con,
            merger,
            official_table,
            batch_table,
            move_year_ids,
            past_year_ids,
            past_before,
            backup_name,
        )

        if not post[
            "passed"
        ]:

            raise RuntimeError(
                "POST-COMMIT CHECK FAIL."
            )

        post_verified = True

    except Exception:

        if not committed:

            try:
                con.rollback()
            except Exception:
                pass

        elif not post_verified:

            con.close()
            con = None

            print(
                "POST-COMMIT FAIL: "
                "đang khôi phục DB "
                "từ backup...",
                flush=True,
            )

            sqlite_restore(
                backup_db,
                DB,
            )

            with connect_ro() as restored:

                ri, rf = db_health(
                    restored
                )

                if (
                    ri.lower()
                    != "ok"
                    or rf
                ):

                    raise RuntimeError(
                        "RESTORE cũng "
                        "không đạt: "
                        + f"integrity={ri}, "
                        + f"FK={rf}"
                    )

            print(
                "DA KHOI PHUC DB "
                "VE TRUOC 4 PHUONG AN."
            )

        raise

    finally:

        if con is not None:
            con.close()

    with connect_ro() as final_con:

        final = global_postcheck(
            final_con,
            merger,
            official_table,
            batch_table,
            move_year_ids,
            past_year_ids,
            past_before,
            backup_name,
        )

    if not final[
        "passed"
    ]:

        raise RuntimeError(
            "DB đã commit nhưng "
            "audit cuối chưa đạt. "
            "KHÔNG chạy lại script."
        )

    db_after_sha = sha256(
        DB
    )

    result_payload = {
        "status":
            "SUCCESS",

        "completed_at":
            datetime.now().isoformat(
                timespec="seconds"
            ),

        "backup":
            str(
                backup_dir
            ),

        "db_before_sha":
            EXPECTED_HASH[
                "db"
            ],

        "db_after_sha":
            db_after_sha,

        "operations":
            operation_results,

        "final_audit":
            final,

        "resolution_file_changed":
            False,

        "approved_plans_file_changed":
            False,

        "note":
            (
                "4 phương án đặc thù THCS "
                "đã thực hiện riêng sau "
                "batch THCS. Không tạo "
                "batch THCS thứ hai."
            ),
    }

    result_file = (
        backup_dir
        / "KET_QUA_THCS_DAC_THU_4.json"
    )

    result_file.write_text(
        json.dumps(
            result_payload,
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )

    print()
    print("=" * 150)
    print(
        "THUC HIEN CHINH THUC "
        "4 THCS DAC THU: COMMITTED"
    )
    print("=" * 150)

    for item in operation_results:

        print(
            item[
                "operation_id"
            ],
            "|",
            item[
                "source_id"
            ],
            "->",
            item[
                "target_id"
            ],
            "|",
            item[
                "target_name"
            ],
            "| staff=",
            item[
                "staff_rollover_created"
            ],
            "| PASS",
        )

    print()

    print(
        "TONG DOI NGU          =",
        final[
            "total_staff"
        ],
    )

    print(
        "CBQL                  =",
        final[
            "total_quan_ly"
        ],
    )

    print(
        "GIAO VIEN             =",
        final[
            "total_giao_vien"
        ],
    )

    print(
        "NHAN VIEN             =",
        final[
            "total_nhan_vien"
        ],
    )

    print(
        "PAST EXACT            =",
        final[
            "past_exact"
        ],
    )

    print(
        "CURRENT/FUTURE SOURCE =",
        final[
            "source_residual"
        ],
    )

    print(
        "ACTIVE SOURCES        =",
        final[
            "active_sources"
        ],
    )

    print(
        "ACTIVE TARGETS        =",
        final[
            "active_targets"
        ],
    )

    print(
        "DUPLICATE STAFF       =",
        len(
            final[
                "duplicate_staff_anywhere"
            ]
        ),
    )

    print(
        "OFFICIAL EXECUTIONS   =",
        final[
            "official_count"
        ],
    )

    print(
        "AUDIT OPERATIONS      =",
        final[
            "audit_count"
        ],
    )

    print(
        "THCS BATCH COUNT      =",
        final[
            "thcs_batch_count"
        ],
        "(giu nguyen, "
        "khong tao batch 2)",
    )

    print(
        "INTEGRITY             =",
        final[
            "integrity"
        ],
    )

    print(
        "FK                    =",
        final[
            "fk"
        ],
    )

    print(
        "DB SHA SAU            =",
        db_after_sha,
    )

    print(
        "BACKUP                =",
        backup_dir,
    )

    print(
        "RESULT                =",
        result_file,
    )

    print(
        "RESOLUTION            = CHUA DOI"
    )

    print(
        "APPROVED PLANS        = CHUA DOI"
    )

    print()

    print(
        "KHONG CHAY LAI SCRIPT NAY."
    )

    print(
        "READY_FOR_POST_AUDIT_"
        "THCS_SPECIAL_4=YES"
    )

    print("=" * 150)

    return 0


if __name__ == "__main__":

    try:

        raise SystemExit(
            main()
        )

    except Exception as exc:

        print()
        print("=" * 150)
        print(
            "DUNG AN TOAN"
        )
        print("=" * 150)

        print(
            repr(
                exc
            )
        )

        print(
            "Nếu output đã có COMMITTED "
            "thì KHÔNG chạy lại."
        )

        raise SystemExit(2)
