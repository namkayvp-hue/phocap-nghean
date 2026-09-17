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

BACKUP_DIR = Path(
    r"C:\PhoCap\exports"
    r"\backup_truoc_THCS_dac_thu_4_20260911_033631"
)

BACKUP_DB = (
    BACKUP_DIR
    / "phocap.db"
)

BACKUP_META = (
    BACKUP_DIR
    / "metadata.json"
)

RESULT_FILE = (
    BACKUP_DIR
    / "KET_QUA_THCS_DAC_THU_4.json"
)


EXPECTED_HASH = {
    "db":
        "706279fe9cd63f9f01c4c3d7637f955534280b7b745e333b0b6943c2e64aed89",

    "engine":
        "414fb49a4c5f4fed7b571cc55df381678fe660cd8a675ecaa2f6fd70ebd7827a",

    "level_service":
        "9104fb99c78755e9eec86d090659b3a922834ff097d7292aa4d4b29e360a27f9",

    "resolution":
        "d9d347b19de0795553c8f047cb91a430ded63d9232ac7eda7ea069b716c2c0f4",

    "plans":
        "4e2c5f044c48c57dda40fecc11f4e9f466f236aacc082f224536b1685cadb1fc",
}


YEAR_ID = 2
PREVIOUS_YEAR_ID = 1


CASES = [
    {
        "operation_id":
            "QD3805-OP-0399",

        "plan_id":
            "PA2026-35F6C2558FC4",

        "source_id":
            1592,

        "source_code":
            "40415505",

        "source_old_name":
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
        },
    },

    {
        "operation_id":
            "QD3805-OP-0424",

        "plan_id":
            "PA2026-F228D672FCAC",

        "source_id":
            1485,

        "source_code":
            "40416506",

        "source_old_name":
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
        },
    },

    {
        "operation_id":
            "QD3805-OP-0434",

        "plan_id":
            "PA2026-6948B60DF298",

        "source_id":
            1647,

        "source_code":
            "40416504",

        "source_old_name":
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
        },
    },

    {
        "operation_id":
            "QD3805-OP-0451",

        "plan_id":
            "PA2026-CC0F70262554",

        "source_id":
            1589,

        "source_code":
            "40420509",

        "source_old_name":
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
        },
    },
]


EXCLUDED_HISTORICAL = [
    {
        "record_id": 39473,
        "staff_member_id": 39468,
        "school_id": 1592,
        "status_code": "CHUYEN_DI",
        "source_status_label": "Đã chuyển đi",
    },

    {
        "record_id": 37890,
        "staff_member_id": 37885,
        "school_id": 1486,
        "status_code": "NGHI_HUU",
        "source_status_label": "Đã nghỉ hưu",
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


def connect_ro(path: Path):

    con = sqlite3.connect(
        path.resolve().as_uri()
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

    return integrity, fk


def year_tables(con):

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
            row["name"]
        )

        cols = {
            str(x["name"])
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

        columns = [
            str(x["name"])
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
                    len(school_ids)
                )
                + ") "
                + "AND school_year_id IN ("
                + marks(
                    len(year_ids)
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
    year_ids,
):

    result = {}

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
                        len(school_ids)
                    )
                    + ") "
                    + "AND school_year_id IN ("
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


def current_staff(
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

        category = (
            merger._classify_staff(
                row
            )
        )

        groups[category] += 1

        if (
            row["staff_member_id"]
            is not None
        ):

            ids.append(
                int(
                    row[
                        "staff_member_id"
                    ]
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

        "DUPLICATE":
            duplicate,
    }


def source_users(
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
            ) AS active_school_login

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

        "active_school_login":
            int(
                row[
                    "active_school_login"
                ]
                or 0
            ),
    }


print("=" * 150)
print(
    "HAU KIEM DOC LAP SAU COMMIT "
    "4 THCS DAC THU"
)
print(
    "CHI DOC - KHONG SUA DB - "
    "KHONG SUA RESOLUTION"
)
print("=" * 150)


# ============================================================
# 1. FILE / HASH GATE
# ============================================================

print()
print("1. HASH GATE")
print("-" * 150)


PATHS = {
    "db":
        DB,

    "engine":
        ENGINE_FILE,

    "level_service":
        LEVEL_SERVICE_FILE,

    "resolution":
        RESOLUTION_FILE,

    "plans":
        PLAN_FILE,
}


before_hash = {}


for key, path in PATHS.items():

    if not path.exists():

        raise RuntimeError(
            f"DUNG: khong tim thay {path}"
        )

    value = sha256(
        path
    )

    before_hash[key] = value

    print(
        f"{key:14s} = {value}"
    )

    if value != EXPECTED_HASH[key]:

        raise RuntimeError(
            "DUNG: "
            + key
            + " khong dung nen "
              "sau commit da khoa."
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
            "DUNG: hay dung server."
        )


# ============================================================
# 2. BACKUP
# ============================================================

print()
print("2. BACKUP TRUOC COMMIT")
print("-" * 150)


for path in (
    BACKUP_DIR,
    BACKUP_DB,
    BACKUP_META,
    RESULT_FILE,
):

    print(
        path,
        "=",
        path.exists(),
    )

    if not path.exists():

        raise RuntimeError(
            "DUNG: thieu "
            + str(path)
        )


metadata = json.loads(
    BACKUP_META.read_text(
        encoding="utf-8-sig"
    )
)


print(
    "backup status =",
    metadata.get("status"),
)


if (
    metadata.get("status")
    !=
    "CREATED_BEFORE_TRANSACTION_MUTATION"
):

    raise RuntimeError(
        "DUNG: metadata backup "
        "khong xac nhan pre-transaction."
    )


with connect_ro(
    BACKUP_DB
) as backup_con:

    bi, bf = db_health(
        backup_con
    )

    print(
        "backup integrity =",
        bi,
    )

    print(
        "backup FK        =",
        bf,
    )

    if (
        bi.lower() != "ok"
        or bf != 0
    ):

        raise RuntimeError(
            "DUNG: backup health FAIL."
        )


# ============================================================
# 3. IMPORT ENGINE / SERVICE
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


OFFICIAL_TABLE = str(
    levelsvc.OFFICIAL_EXECUTION_TABLE
)

BATCH_TABLE = str(
    levelsvc.BATCH_TABLE
)


# ============================================================
# 4. CURRENT HEALTH / YEAR SCOPE
# ============================================================

con = connect_ro(
    DB
)

try:

    integrity, fk = db_health(
        con
    )

    print()
    print("3. CURRENT DATABASE HEALTH")
    print("-" * 150)

    print(
        "integrity =",
        integrity,
    )

    print(
        "FK        =",
        fk,
    )

    if (
        integrity.lower() != "ok"
        or fk != 0
    ):

        raise RuntimeError(
            "DUNG: current DB health FAIL."
        )


    move_year_ids, past_year_ids = (
        merger._year_scope_ids(
            con,
            YEAR_ID,
        )
    )

    previous_year_id = (
        merger._previous_year_id(
            con,
            YEAR_ID,
        )
    )


    print()
    print("4. YEAR SCOPE")
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


    if (
        move_year_ids != [2, 8]
        or previous_year_id != 1
    ):

        raise RuntimeError(
            "DUNG: year scope thay doi."
        )


    source_ids = [
        x["source_id"]
        for x in CASES
    ]

    target_ids = [
        x["target_id"]
        for x in CASES
    ]

    involved_ids = sorted(
        set(
            source_ids
            + target_ids
        )
    )


    # ========================================================
    # 5. BACKUP PRE-STATE
    # ========================================================

    print()
    print("5. SO SANH TRANG THAI TRUOC / SAU")
    print("=" * 150)


    with connect_ro(
        BACKUP_DB
    ) as backup_con:

        for case in CASES:

            source_before = school_row(
                backup_con,
                case["source_id"],
            )

            target_before = school_row(
                backup_con,
                case["target_id"],
            )

            source_after = school_row(
                con,
                case["source_id"],
            )

            target_after = school_row(
                con,
                case["target_id"],
            )


            print()
            print(
                case["operation_id"]
            )

            print(
                "SOURCE BEFORE =",
                source_before,
            )

            print(
                "SOURCE AFTER  =",
                source_after,
            )

            print(
                "TARGET BEFORE =",
                target_before,
            )

            print(
                "TARGET AFTER  =",
                target_after,
            )


            if (
                source_before is None
                or target_before is None
                or source_after is None
                or target_after is None
            ):

                raise RuntimeError(
                    case["operation_id"]
                    + ": thieu school."
                )


            if (
                int(
                    source_before["is_active"]
                    or 0
                ) != 1

                or str(
                    source_before["code"]
                )
                != case["source_code"]

                or str(
                    source_before["name"]
                )
                != case["source_old_name"]

                or int(
                    target_before["is_active"]
                    or 0
                ) != 1

                or str(
                    target_before["code"]
                )
                != case["target_code"]

                or str(
                    target_before["name"]
                )
                != case["target_old_name"]
            ):

                raise RuntimeError(
                    case["operation_id"]
                    + ": backup pre-state sai."
                )


            if (
                int(
                    source_after["is_active"]
                    or 0
                ) != 0

                or int(
                    target_after["is_active"]
                    or 0
                ) != 1

                or str(
                    target_after["code"]
                )
                != case["target_code"]

                or str(
                    target_after["name"]
                )
                != case["target_new_name"]
            ):

                raise RuntimeError(
                    case["operation_id"]
                    + ": post-state sai."
                )


    # ========================================================
    # 6. PAST EXACT
    # ========================================================

    print()
    print("6. PAST EXACT TU BACKUP")
    print("-" * 150)


    with connect_ro(
        BACKUP_DB
    ) as backup_con:

        past_before = past_snapshot(
            backup_con,
            involved_ids,
            past_year_ids,
        )


    past_after = past_snapshot(
        con,
        involved_ids,
        past_year_ids,
    )


    print(
        "PAST BACKUP =",
        past_before,
    )

    print(
        "PAST CURRENT=",
        past_after,
    )

    print(
        "PAST EXACT  =",
        past_before == past_after,
    )


    if past_before != past_after:

        raise RuntimeError(
            "DUNG: PAST da thay doi."
        )


    # ========================================================
    # 7. SOURCE RESIDUAL / USERS
    # ========================================================

    print()
    print("7. SOURCE SAU SAP NHAP")
    print("-" * 150)


    source_residual = residual(
        con,
        source_ids,
        move_year_ids,
    )


    active_sources = int(
        con.execute(
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


    print(
        "active sources =",
        active_sources,
    )

    print(
        "CURRENT/FUTURE residual =",
        source_residual,
    )


    if (
        active_sources != 0
        or source_residual
    ):

        raise RuntimeError(
            "DUNG: source chua dong sach."
        )


    for source_id in source_ids:

        users = source_users(
            con,
            source_id,
        )

        print(
            "source",
            source_id,
            "users =",
            users,
        )

        if (
            users["active"] != 0
            or users[
                "active_school_login"
            ] != 0
        ):

            raise RuntimeError(
                f"DUNG: source {source_id} "
                "con active user."
            )


    # ========================================================
    # 8. TARGET STAFF
    # ========================================================

    print()
    print("8. DOI NGU 4 TRUONG DICH")
    print("=" * 150)


    totals = Counter()

    all_target_staff_ids = []


    for case in CASES:

        state = current_staff(
            con,
            merger,
            case["target_id"],
        )

        expected = case[
            "expected"
        ]


        print(
            case["operation_id"],
            "|",
            case["target_new_name"],
            "|",
            state,
        )


        if (
            state["TOTAL"]
            != expected["TOTAL"]

            or state["QUAN_LY"]
            != expected["QUAN_LY"]

            or state["GIAO_VIEN"]
            != expected["GIAO_VIEN"]

            or state["NHAN_VIEN"]
            != expected["NHAN_VIEN"]

            or state["DUPLICATE"]
        ):

            raise RuntimeError(
                case["operation_id"]
                + ": doi ngu sai."
            )


        totals["TOTAL"] += (
            state["TOTAL"]
        )

        totals["QUAN_LY"] += (
            state["QUAN_LY"]
        )

        totals["GIAO_VIEN"] += (
            state["GIAO_VIEN"]
        )

        totals["NHAN_VIEN"] += (
            state["NHAN_VIEN"]
        )


        ids = con.execute(
            """
            SELECT staff_member_id
            FROM staff_year_records
            WHERE school_id=?
              AND school_year_id=?
              AND is_active=1
              AND staff_member_id IS NOT NULL
            """,
            (
                case["target_id"],
                YEAR_ID,
            ),
        ).fetchall()


        all_target_staff_ids.extend(
            int(x[0])
            for x in ids
        )


    print()
    print(
        "TOTAL =",
        dict(totals),
    )


    if dict(totals) != {
        "TOTAL": 244,
        "QUAN_LY": 19,
        "GIAO_VIEN": 201,
        "NHAN_VIEN": 24,
    }:

        raise RuntimeError(
            "DUNG: tong doi ngu sai."
        )


    # ========================================================
    # 9. DUPLICATE STAFF GLOBALLY
    # ========================================================

    print()
    print("9. DUPLICATE STAFF TOAN DB 2026-2027")
    print("-" * 150)


    duplicate_anywhere = []


    staff_ids_unique = sorted(
        set(
            all_target_staff_ids
        )
    )


    if staff_ids_unique:

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
                            staff_ids_unique
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
                    *staff_ids_unique,
                ],
            ).fetchall()
        ]


    print(
        "duplicate anywhere =",
        duplicate_anywhere,
    )


    if duplicate_anywhere:

        raise RuntimeError(
            "DUNG: co nhan su trung "
            "voi truong khac."
        )


    # ========================================================
    # 10. 2 EXCLUDED HISTORICAL STAFF
    # ========================================================

    print()
    print("10. HAI HO SO NGHI / CHUYEN")
    print("=" * 150)


    with connect_ro(
        BACKUP_DB
    ) as backup_con:

        for item in EXCLUDED_HISTORICAL:

            old_row = backup_con.execute(
                """
                SELECT *
                FROM staff_year_records
                WHERE id=?
                  AND staff_member_id=?
                  AND school_id=?
                  AND school_year_id=?
                """,
                (
                    item["record_id"],
                    item["staff_member_id"],
                    item["school_id"],
                    PREVIOUS_YEAR_ID,
                ),
            ).fetchone()


            new_row = con.execute(
                """
                SELECT *
                FROM staff_year_records
                WHERE id=?
                  AND staff_member_id=?
                  AND school_id=?
                  AND school_year_id=?
                """,
                (
                    item["record_id"],
                    item["staff_member_id"],
                    item["school_id"],
                    PREVIOUS_YEAR_ID,
                ),
            ).fetchone()


            if (
                old_row is None
                or new_row is None
            ):

                raise RuntimeError(
                    "DUNG: thieu ho so lich su "
                    + str(
                        item[
                            "staff_member_id"
                        ]
                    )
                )


            old_dict = {
                key:
                    encode(
                        old_row[key]
                    )
                for key in old_row.keys()
            }

            new_dict = {
                key:
                    encode(
                        new_row[key]
                    )
                for key in new_row.keys()
            }


            current_count = int(
                con.execute(
                    """
                    SELECT COUNT(*)
                    FROM staff_year_records
                    WHERE staff_member_id=?
                      AND school_year_id=?
                    """,
                    (
                        item[
                            "staff_member_id"
                        ],
                        YEAR_ID,
                    ),
                ).fetchone()[0]
                or 0
            )


            print()
            print(
                "staff_member_id =",
                item[
                    "staff_member_id"
                ],
            )

            print(
                "status =",
                new_row[
                    "status_code"
                ],
                "|",
                new_row[
                    "source_status_label"
                ],
            )

            print(
                "PAST ROW EXACT =",
                old_dict == new_dict,
            )

            print(
                "CURRENT ROWS =",
                current_count,
            )


            if old_dict != new_dict:

                raise RuntimeError(
                    "DUNG: ho so lich su "
                    + str(
                        item[
                            "staff_member_id"
                        ]
                    )
                    + " bi thay doi."
                )


            if (
                str(
                    new_row[
                        "status_code"
                    ]
                    or ""
                )
                != item[
                    "status_code"
                ]
            ):

                raise RuntimeError(
                    "DUNG: status_code lich su sai."
                )


            if (
                str(
                    new_row[
                        "source_status_label"
                    ]
                    or ""
                )
                != item[
                    "source_status_label"
                ]
            ):

                raise RuntimeError(
                    "DUNG: source_status_label sai."
                )


            if current_count != 0:

                raise RuntimeError(
                    "DUNG: ho so nghi/chuyen "
                    "bi rollover sang 2026-2027."
                )


    # ========================================================
    # 11. RENAME HISTORY
    # ========================================================

    print()
    print("11. LICH SU DOI TEN")
    print("=" * 150)


    for case in CASES:

        rows = con.execute(
            """
            SELECT
                school_id,
                effective_school_year_id,
                old_name,
                new_name,
                changed_by_user_id
            FROM school_name_histories
            WHERE school_id=?
              AND effective_school_year_id=?
            """,
            (
                case["target_id"],
                YEAR_ID,
            ),
        ).fetchall()


        print(
            case["operation_id"],
            "=",
            [
                dict(x)
                for x in rows
            ],
        )


        if len(rows) != 1:

            raise RuntimeError(
                case["operation_id"]
                + ": rename history count != 1."
            )


        row = rows[0]


        if (
            str(row["old_name"])
            != case["target_old_name"]

            or str(row["new_name"])
            != case["target_new_name"]

            or int(
                row["changed_by_user_id"]
                or 0
            ) != 1
        ):

            raise RuntimeError(
                case["operation_id"]
                + ": rename history sai."
            )


    # ========================================================
    # 12. OFFICIAL EXECUTION / AUDIT
    # ========================================================

    print()
    print("12. OFFICIAL EXECUTIONS / AUDIT")
    print("=" * 150)


    backup_name = (
        BACKUP_DIR.name
    )


    for case in CASES:

        rows = con.execute(
            (
                "SELECT * FROM "
                + qident(
                    OFFICIAL_TABLE
                )
                + " WHERE plan_id=? "
                  "AND school_year_id=?"
            ),
            (
                case["plan_id"],
                YEAR_ID,
            ),
        ).fetchall()


        print(
            case["operation_id"],
            "| official rows =",
            len(rows),
        )


        if len(rows) != 1:

            raise RuntimeError(
                case["operation_id"]
                + ": official execution != 1."
            )


        row = rows[0]


        source_json = json.loads(
            str(
                row[
                    "source_school_ids_json"
                ]
                or "[]"
            )
        )


        if (
            int(
                row[
                    "target_school_id"
                ]
            )
            != case["target_id"]

            or source_json
            != [
                case["source_id"]
            ]

            or str(
                row[
                    "backup_name"
                ]
            )
            != backup_name
        ):

            raise RuntimeError(
                case["operation_id"]
                + ": official execution mapping sai."
            )


    official_total = int(
        con.execute(
            (
                "SELECT COUNT(*) FROM "
                + qident(
                    OFFICIAL_TABLE
                )
                + " WHERE school_year_id=? "
                + "AND plan_id IN ("
                + marks(
                    len(CASES)
                )
                + ")"
            ),
            [
                YEAR_ID,
                *[
                    x["plan_id"]
                    for x in CASES
                ],
            ],
        ).fetchone()[0]
        or 0
    )


    audit_total = int(
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


    print(
        "official total =",
        official_total,
    )

    print(
        "audit total    =",
        audit_total,
    )


    if (
        official_total != 4
        or audit_total != 4
    ):

        raise RuntimeError(
            "DUNG: official/audit count sai."
        )


    # ========================================================
    # 13. THCS BATCH MUST STILL BE EXACTLY ONE
    # ========================================================

    print()
    print("13. THCS BATCH CU")
    print("-" * 150)


    batches = con.execute(
        (
            "SELECT * FROM "
            + qident(
                BATCH_TABLE
            )
            + " WHERE school_year_id=? "
              "AND level_code='THCS' "
              "ORDER BY id"
        ),
        (
            YEAR_ID,
        ),
    ).fetchall()


    print(
        "THCS batch count =",
        len(batches),
    )


    for row in batches:

        print(
            "batch id=",
            row["id"],
            "| executed_count=",
            row["executed_count"],
            "| fingerprint=",
            row[
                "batch_fingerprint"
            ],
        )


    if len(batches) != 1:

        raise RuntimeError(
            "DUNG: da xuat hien "
            "batch THCS thu hai."
        )


    if int(
        batches[0][
            "executed_count"
        ]
        or 0
    ) != 13:

        raise RuntimeError(
            "DUNG: batch THCS cu "
            "bi thay doi executed_count."
        )


    print()
    print("=" * 150)
    print("14. KET LUAN")
    print("=" * 150)


    print(
        "PAST EXACT              =",
        past_before == past_after,
    )

    print(
        "ACTIVE SOURCES          =",
        active_sources,
    )

    print(
        "CURRENT/FUTURE SOURCE   =",
        source_residual,
    )

    print(
        "TOTAL STAFF             =",
        totals["TOTAL"],
    )

    print(
        "CBQL                    =",
        totals["QUAN_LY"],
    )

    print(
        "GIAO VIEN               =",
        totals["GIAO_VIEN"],
    )

    print(
        "NHAN VIEN               =",
        totals["NHAN_VIEN"],
    )

    print(
        "DUPLICATE STAFF         =",
        len(
            duplicate_anywhere
        ),
    )

    print(
        "OFFICIAL EXECUTIONS     =",
        official_total,
    )

    print(
        "AUDIT OPERATIONS        =",
        audit_total,
    )

    print(
        "THCS BATCH COUNT        =",
        len(batches),
    )

    print(
        "INTEGRITY               =",
        integrity,
    )

    print(
        "FK                      =",
        fk,
    )


finally:

    con.close()


# ============================================================
# 15. FILE IMMUTABILITY
# ============================================================

print()
print("=" * 150)
print("15. FILE IMMUTABILITY")
print("=" * 150)


for key, path in PATHS.items():

    after = sha256(
        path
    )

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
            + " bi thay doi "
              "trong luc audit."
        )


print()
print("=" * 150)
print(
    "HAU KIEM 4 THCS DAC THU: PASS"
)
print("=" * 150)

print(
    "4 PHUONG AN             = COMMITTED"
)

print(
    "4 SOURCE 1              = INACTIVE"
)

print(
    "4 SOURCE 2 / TARGET     = ACTIVE"
)

print(
    "TARGET ID/CODE          = GIU NGUYEN"
)

print(
    "TARGET NAME             = DUNG QD3805"
)

print(
    "PAST                    = GIU NGUYEN EXACT"
)

print(
    "CURRENT/FUTURE SOURCE   = 0"
)

print(
    "TONG DOI NGU            = 244"
)

print(
    "CBQL                    = 19"
)

print(
    "GIAO VIEN               = 201"
)

print(
    "NHAN VIEN               = 24"
)

print(
    "2 HO SO NGHI/CHUYEN     = CHI GIU LICH SU"
)

print(
    "DUPLICATE STAFF         = 0"
)

print(
    "OFFICIAL EXECUTIONS     = 4"
)

print(
    "AUDIT OPERATIONS        = 4"
)

print(
    "THCS BATCH              = VAN CHI 1"
)

print(
    "RESOLUTION              = CHUA DOI"
)

print(
    "APPROVED PLANS          = CHUA DOI"
)

print(
    "DATABASE                = KHONG THAY DOI TRONG AUDIT"
)

print()
print(
    "READY_TO_SYNC_THCS_SPECIAL_4=YES"
)

print("=" * 150)
