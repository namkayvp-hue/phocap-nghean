# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import sys
import unicodedata
from collections import Counter
from pathlib import Path

try:
    sys.stdout.reconfigure(
        encoding="utf-8",
        errors="replace",
    )
except Exception:
    pass


ROOT = Path(r"C:\PhoCap")

DB = ROOT / "data" / "phocap.db"

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
        "c6a0f2f1a08e7e80a6e89cd0edfd83961f4d87930d5b8b1f3cdae8e770f4deee",

    "resolution":
        "d9d347b19de0795553c8f047cb91a430ded63d9232ac7eda7ea069b716c2c0f4",

    "history":
        "4e2c5f044c48c57dda40fecc11f4e9f466f236aacc082f224536b1685cadb1fc",
}


CASES = [
    {
        "operation_id":
            "QD3805-OP-0399",

        "target":
            "THCS Mường Quàng",

        "sources": [
            "THCS Quang Phong",
            "THCS Cắm Muộn",
        ],
    },

    {
        "operation_id":
            "QD3805-OP-0424",

        "target":
            "THCS Châu Tiến",

        "sources": [
            "THCS Tiến Thắng",
            "PTDTBT THCS Bính Thuận",
        ],
    },

    {
        "operation_id":
            "QD3805-OP-0434",

        "target":
            "THCS Quỳ Châu",

        "sources": [
            "PTDTBT THCS Hội Nga",
            "THCS Hạnh Thiết",
        ],
    },

    {
        "operation_id":
            "QD3805-OP-0451",

        "target":
            "THCS Mường Ham",

        "sources": [
            "THCS Châu Thái",
            "THCS Châu Cường",
        ],
    },
]


def sha256(path: Path) -> str:

    h = hashlib.sha256()

    with path.open("rb") as f:

        for block in iter(
            lambda: f.read(1024 * 1024),
            b"",
        ):
            h.update(block)

    return h.hexdigest()


def norm(value) -> str:

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

    text = re.sub(
        r"[^A-Z0-9]+",
        " ",
        text,
    )

    return " ".join(
        text.split()
    )


def canon_group(value) -> str:

    x = norm(
        value
    ).replace(
        " ",
        "_",
    )

    if x in {
        "CBQL",
        "CAN_BO_QUAN_LY",
        "QUAN_LY",
    }:
        return "CBQL"

    if x in {
        "GV",
        "GIAO_VIEN",
        "GIAOVIEN",
    }:
        return "GIAO_VIEN"

    if x in {
        "NV",
        "NHAN_VIEN",
        "NHANVIEN",
    }:
        return "NHAN_VIEN"

    return x or "KHAC"


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
    con,
    table: str,
) -> bool:

    return (
        con.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type='table'
              AND name=?
            LIMIT 1
            """,
            (table,),
        ).fetchone()
        is not None
    )


def school_years(
    con,
):

    rows = con.execute(
        """
        SELECT id,code,name
        FROM school_years
        WHERE code IN (
            '2025-2026',
            '2026-2027',
            '2027-2028'
        )
        ORDER BY code
        """
    ).fetchall()

    return {
        str(x["code"]):
            int(x["id"])
        for x in rows
    }


def staff_state(
    con,
    school_id: int,
    year_id: int,
):

    if not table_exists(
        con,
        "staff_year_records",
    ):

        return {
            "TOTAL": 0,
            "CBQL": 0,
            "GIAO_VIEN": 0,
            "NHAN_VIEN": 0,
            "OTHER": {},
        }


    rows = con.execute(
        """
        SELECT
            staff_member_id,
            position_group
        FROM staff_year_records
        WHERE school_id=?
          AND school_year_id=?
          AND is_active=1
        """,
        (
            int(school_id),
            int(year_id),
        ),
    ).fetchall()


    groups = Counter(
        canon_group(
            x["position_group"]
        )
        for x in rows
    )


    return {
        "TOTAL":
            len(rows),

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
            key:
                int(value)

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


def user_state(
    con,
    school_id: int,
):

    if not table_exists(
        con,
        "users",
    ):

        return {}


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
                row["active_school_login"]
                or 0
            ),
    }


def residual(
    con,
    school_id: int,
    move_year_ids: list[int],
):

    result = {}


    tables = con.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type='table'
          AND name NOT LIKE 'sqlite_%'
        ORDER BY name
        """
    ).fetchall()


    for table_row in tables:

        table = str(
            table_row["name"]
        )


        cols = {
            str(x["name"])
            for x in con.execute(
                f"PRAGMA table_info({qident(table)})"
            ).fetchall()
        }


        if not {
            "school_id",
            "school_year_id",
        }.issubset(cols):

            continue


        if not move_year_ids:

            continue


        marks = ",".join(
            "?"
            for _ in move_year_ids
        )


        n = int(
            con.execute(
                f"""
                SELECT COUNT(*)
                FROM {qident(table)}
                WHERE school_id=?
                  AND school_year_id
                      IN ({marks})
                """,
                [
                    int(school_id),
                    *move_year_ids,
                ],
            ).fetchone()[0]
            or 0
        )


        if n:

            result[
                table
            ] = n


    return result


def commune_map(
    con,
):

    for table in (
        "communes",
        "administrative_units",
    ):

        if not table_exists(
            con,
            table,
        ):
            continue


        cols = {
            str(x["name"])
            for x in con.execute(
                f"PRAGMA table_info({qident(table)})"
            )
        }


        if {
            "id",
            "name",
        }.issubset(cols):

            rows = con.execute(
                f"""
                SELECT id,name
                FROM {qident(table)}
                """
            ).fetchall()

            return {
                int(x["id"]):
                    str(
                        x["name"]
                        or ""
                    )
                for x in rows
            }


    return {}


def find_name(
    all_schools,
    wanted: str,
):

    wanted_norm = norm(
        wanted
    )


    exact = [
        x
        for x in all_schools
        if norm(
            x["name"]
        )
        == wanted_norm
    ]


    if exact:

        return (
            exact,
            [],
        )


    tokens = [
        x
        for x in wanted_norm.split()
        if x not in {
            "TRUONG",
            "THCS",
            "PTDTBT",
            "PTDT",
            "BAN",
            "TRU",
        }
    ]


    near = []


    for row in all_schools:

        name_norm = norm(
            row["name"]
        )


        hit = sum(
            1
            for token in tokens
            if token in name_norm
        )


        if (
            tokens
            and hit
            == len(tokens)
        ):

            near.append(
                row
            )


    return (
        [],
        near,
    )


def history_for_ids(
    payload,
    school_ids: set[int],
):

    result = []


    plans = (
        payload.get(
            "plans"
        )
        or []
    )


    for raw in plans:

        if not isinstance(
            raw,
            dict,
        ):
            continue


        sources = {
            int(x)
            for x in (
                raw.get(
                    "source_school_ids"
                )
                or []
            )
            if str(x).isdigit()
        }


        target = int(
            raw.get(
                "target_school_id"
            )
            or 0
        )


        if (
            sources
            & school_ids
            or target
            in school_ids
        ):

            result.append({
                "id":
                    raw.get(
                        "id"
                    ),

                "status":
                    raw.get(
                        "status"
                    ),

                "source_school_ids":
                    sorted(
                        sources
                    ),

                "target_school_id":
                    target,
            })


    return result


print("=" * 150)
print(
    "THCS - KHAO SAT 4 PHUONG AN CUNG CAP CO DICH TEN MOI"
)
print(
    "CHI DOC - KHONG SUA DATABASE - KHONG SAP NHAP"
)
print("=" * 150)


# ============================================================
# 1. HASH GATE
# ============================================================

print()
print("1. HASH GATE")
print("-" * 150)


for key, path in {
    "db":
        DB,

    "resolution":
        RESOLUTION,

    "history":
        HISTORY,
}.items():

    value = sha256(
        path
    )


    print(
        f"{key:12s} = {value}"
    )


    if value != EXPECTED[key]:

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
            "DUNG: server/Uvicorn dang mo "
            "hoac database co transaction."
        )


# ============================================================
# 2. RESOLUTION GATE
# ============================================================

resolution = json.loads(
    RESOLUTION.read_text(
        encoding="utf-8-sig"
    )
)


rules = {
    str(
        x.get(
            "operation_id"
        )
        or ""
    ):
        dict(x)

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


    if op not in rules:

        raise RuntimeError(
            "DUNG: resolution thieu "
            + op
        )


print()
print(
    "2. RESOLUTION = PASS"
)


# ============================================================
# 3. DB HEALTH
# ============================================================

con = connect_ro()


try:

    integrity = str(
        con.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]
    )


    fk = con.execute(
        "PRAGMA foreign_key_check"
    ).fetchall()


    print()
    print("3. DATABASE HEALTH")
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


    years = school_years(
        con
    )


    print(
        "school years =",
        years,
    )


    previous_id = years.get(
        "2025-2026"
    )

    current_id = years.get(
        "2026-2027"
    )

    future_id = years.get(
        "2027-2028"
    )


    if (
        previous_id is None
        or current_id is None
    ):

        raise RuntimeError(
            "DUNG: thieu school year."
        )


    move_year_ids = [
        x
        for x in (
            current_id,
            future_id,
        )
        if x is not None
    ]


    communes = commune_map(
        con
    )


    all_schools = [
        dict(x)
        for x in con.execute(
            """
            SELECT
                id,
                code,
                name,
                commune_id,
                is_active
            FROM schools
            ORDER BY id
            """
        ).fetchall()
    ]


    history = json.loads(
        HISTORY.read_text(
            encoding="utf-8-sig"
        )
    )


    summaries = []


    # ========================================================
    # 4. FOUR CASES
    # ========================================================

    print()
    print("4. CHI TIET 4 PHUONG AN")
    print("=" * 150)


    for index, case in enumerate(
        CASES,
        start=1,
    ):

        op = case[
            "operation_id"
        ]


        print()
        print("#" * 150)

        print(
            f"[{index}/4] {op}"
        )

        print(
            "DICH QD3805 =",
            case[
                "target"
            ],
        )

        print(
            "NGUON QD3805 =",
            " + ".join(
                case[
                    "sources"
                ]
            ),
        )


        print()
        print(
            "RESOLUTION RULE:"
        )

        print(
            json.dumps(
                rules[
                    op
                ],
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        )


        case_ids = set()

        source_summary = []

        source_unique = True


        print()
        print(
            "TIM NGUON:"
        )


        for wanted in case[
            "sources"
        ]:

            exact, near = find_name(
                all_schools,
                wanted,
            )


            print()
            print(
                "Nguon can tim:",
                wanted,
            )

            print(
                "EXACT =",
                len(exact),
            )


            candidates = (
                exact
                if exact
                else near
            )


            if not exact:

                print(
                    "NEAR  =",
                    len(near),
                )


            if len(exact) != 1:

                source_unique = False


            for row in candidates:

                sid = int(
                    row["id"]
                )

                case_ids.add(
                    sid
                )


                previous_staff = (
                    staff_state(
                        con,
                        sid,
                        previous_id,
                    )
                )


                current_staff = (
                    staff_state(
                        con,
                        sid,
                        current_id,
                    )
                )


                data = {
                    "id":
                        sid,

                    "code":
                        str(
                            row["code"]
                            or ""
                        ),

                    "name":
                        str(
                            row["name"]
                            or ""
                        ),

                    "commune_id":
                        row[
                            "commune_id"
                        ],

                    "commune":
                        communes.get(
                            int(
                                row["commune_id"]
                            )
                            if row[
                                "commune_id"
                            ]
                            is not None
                            else -1,
                            "",
                        ),

                    "is_active":
                        bool(
                            row["is_active"]
                        ),

                    "staff_2025_2026":
                        previous_staff,

                    "staff_2026_2027":
                        current_staff,

                    "users":
                        user_state(
                            con,
                            sid,
                        ),

                    "current_future_residual":
                        residual(
                            con,
                            sid,
                            move_year_ids,
                        ),
                }


                source_summary.append(
                    data
                )


                print(
                    json.dumps(
                        data,
                        ensure_ascii=False,
                        indent=2,
                        default=str,
                    )
                )


        print()
        print(
            "TIM DICH:"
        )


        target_exact, target_near = (
            find_name(
                all_schools,
                case[
                    "target"
                ],
            )
        )


        print(
            "Target EXACT =",
            len(
                target_exact
            ),
        )


        if not target_exact:

            print(
                "Target NEAR  =",
                len(
                    target_near
                ),
            )


        target_candidates = (
            target_exact
            if target_exact
            else target_near
        )


        target_summary = []


        for row in target_candidates:

            sid = int(
                row["id"]
            )

            case_ids.add(
                sid
            )


            data = {
                "id":
                    sid,

                "code":
                    str(
                        row["code"]
                        or ""
                    ),

                "name":
                    str(
                        row["name"]
                        or ""
                    ),

                "commune_id":
                    row[
                        "commune_id"
                    ],

                "commune":
                    communes.get(
                        int(
                            row["commune_id"]
                        )
                        if row[
                            "commune_id"
                        ]
                        is not None
                        else -1,
                        "",
                    ),

                "is_active":
                    bool(
                        row["is_active"]
                    ),

                "staff_2025_2026":
                    staff_state(
                        con,
                        sid,
                        previous_id,
                    ),

                "staff_2026_2027":
                    staff_state(
                        con,
                        sid,
                        current_id,
                    ),

                "users":
                    user_state(
                        con,
                        sid,
                    ),

                "current_future_residual":
                    residual(
                        con,
                        sid,
                        move_year_ids,
                    ),
            }


            target_summary.append(
                data
            )


            print(
                json.dumps(
                    data,
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                )
            )


        print()
        print(
            "LICH SU LIEN QUAN:"
        )


        history_rows = (
            history_for_ids(
                history,
                case_ids,
            )
        )


        print(
            json.dumps(
                history_rows,
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        )


        if (
            source_unique
            and len(
                target_exact
            ) == 1
        ):

            status = (
                "SOURCE_UNIQUE_TARGET_EXISTING_UNIQUE"
            )

        elif (
            source_unique
            and len(
                target_exact
            ) == 0
        ):

            status = (
                "SOURCE_UNIQUE_TARGET_NOT_FOUND"
            )

        elif not source_unique:

            status = (
                "SOURCE_NOT_UNIQUE"
            )

        else:

            status = (
                "TARGET_AMBIGUOUS"
            )


        summaries.append({
            "operation_id":
                op,

            "target":
                case[
                    "target"
                ],

            "sources":
                case[
                    "sources"
                ],

            "source_exact_unique":
                source_unique,

            "target_exact_count":
                len(
                    target_exact
                ),

            "target_near_count":
                len(
                    target_near
                ),

            "status":
                status,
        })


    print()
    print("=" * 150)
    print("5. TONG KET 4 PHUONG AN")
    print("=" * 150)


    for row in summaries:

        print(
            row[
                "operation_id"
            ],
            "|",
            row[
                "status"
            ],
            "| target_exact=",
            row[
                "target_exact_count"
            ],
            "| target_near=",
            row[
                "target_near_count"
            ],
        )


finally:

    con.close()


# ============================================================
# 6. FILE SAFETY
# ============================================================

print()
print("=" * 150)
print("6. FILE SAFETY")
print("=" * 150)


for key, path in {
    "db":
        DB,

    "resolution":
        RESOLUTION,

    "history":
        HISTORY,
}.items():

    value = sha256(
        path
    )


    print(
        key,
        "=",
        value,
    )


    if value != EXPECTED[
        key
    ]:

        raise RuntimeError(
            "DUNG: "
            + key
            + " bi thay doi trong luc khao sat."
        )


print()
print("=" * 150)
print(
    "KHAO SAT 4 PHUONG AN THCS DICH TEN MOI: HOAN TAT"
)
print(
    "DATABASE = KHONG THAY DOI"
)
print(
    "CHUA THUC HIEN SAP NHAP DAC THU"
)
print("=" * 150)
