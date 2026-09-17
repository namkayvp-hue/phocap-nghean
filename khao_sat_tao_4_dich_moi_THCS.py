# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
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

SERVICE = (
    ROOT
    / "app"
    / "services"
    / "school_merger_level_batch_service.py"
)

ENGINE = (
    ROOT
    / "app"
    / "services"
    / "school_merger_service.py"
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

    "service":
        "9104fb99c78755e9eec86d090659b3a922834ff097d7292aa4d4b29e360a27f9",

    "engine":
        "414fb49a4c5f4fed7b571cc55df381678fe660cd8a675ecaa2f6fd70ebd7827a",

    "resolution":
        "d9d347b19de0795553c8f047cb91a430ded63d9232ac7eda7ea069b716c2c0f4",
}


CASES = {
    "QD3805-OP-0399": {
        "commune_id": 10,
        "target_name": "THCS Mường Quàng",
        "source_ids": [1592, 1594],
    },

    "QD3805-OP-0424": {
        "commune_id": 12,
        "target_name": "THCS Châu Tiến",
        "source_ids": [1485, 1486],
    },

    "QD3805-OP-0434": {
        "commune_id": 11,
        "target_name": "THCS Quỳ Châu",
        "source_ids": [1647, 1646],
    },

    "QD3805-OP-0451": {
        "commune_id": 51,
        "target_name": "THCS Mường Ham",
        "source_ids": [1589, 1590],
    },
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
        + str(value).replace('"', '""')
        + '"'
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


print("=" * 150)
print(
    "THCS - KHAO SAT KHA NANG TAO 4 TRUONG DICH MOI"
)
print(
    "CHI DOC - KHONG SUA DB - KHONG SUA SOURCE - KHONG SAP NHAP"
)
print("=" * 150)


# ============================================================
# 1. HASH / SERVER GATE
# ============================================================

print()
print("1. HASH / SERVER GATE")
print("-" * 150)


for key, path in {
    "db": DB,
    "service": SERVICE,
    "engine": ENGINE,
    "resolution": RESOLUTION,
}.items():

    value = sha256(path)

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
            "DUNG: database dang co WAL/JOURNAL."
        )


# ============================================================
# 2. DATABASE HEALTH
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
    print("2. DATABASE HEALTH")
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


    # ========================================================
    # 3. SCHOOLS SCHEMA
    # ========================================================

    print()
    print("3. SCHOOLS TABLE SCHEMA")
    print("-" * 150)


    schema = [
        dict(x)
        for x in con.execute(
            "PRAGMA table_info(schools)"
        ).fetchall()
    ]


    for row in schema:
        print(
            json.dumps(
                row,
                ensure_ascii=False,
                default=str,
            )
        )


    column_names = {
        str(x["name"])
        for x in schema
    }


    required_no_default = [
        {
            "name": x["name"],
            "type": x["type"],
            "notnull": x["notnull"],
            "default": x["dflt_value"],
            "pk": x["pk"],
        }
        for x in schema
        if int(x["notnull"] or 0) == 1
        and x["dflt_value"] is None
        and int(x["pk"] or 0) == 0
    ]


    print()
    print(
        "REQUIRED WITHOUT DEFAULT ="
    )

    print(
        json.dumps(
            required_no_default,
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )


    # ========================================================
    # 4. INDEX / UNIQUE CODE
    # ========================================================

    print()
    print("4. INDEXES OF schools")
    print("-" * 150)


    indexes = con.execute(
        "PRAGMA index_list(schools)"
    ).fetchall()


    for index in indexes:

        item = dict(index)

        print()
        print(
            json.dumps(
                item,
                ensure_ascii=False,
                default=str,
            )
        )


        index_name = str(
            index["name"]
        )


        detail = [
            dict(x)
            for x in con.execute(
                "PRAGMA index_info("
                + qident(index_name)
                + ")"
            ).fetchall()
        ]


        print(
            " columns =",
            json.dumps(
                detail,
                ensure_ascii=False,
                default=str,
            )
        )


    # ========================================================
    # 5. CODE NULL / EMPTY
    # ========================================================

    print()
    print("5. SCHOOL CODE POLICY HIEN CO")
    print("-" * 150)


    if "code" not in column_names:
        raise RuntimeError(
            "DUNG: schools khong co cot code."
        )


    total = int(
        con.execute(
            "SELECT COUNT(*) FROM schools"
        ).fetchone()[0]
        or 0
    )


    null_code = int(
        con.execute(
            """
            SELECT COUNT(*)
            FROM schools
            WHERE code IS NULL
            """
        ).fetchone()[0]
        or 0
    )


    empty_code = int(
        con.execute(
            """
            SELECT COUNT(*)
            FROM schools
            WHERE code IS NOT NULL
              AND TRIM(code)=''
            """
        ).fetchone()[0]
        or 0
    )


    print(
        "schools total =",
        total,
    )

    print(
        "code NULL     =",
        null_code,
    )

    print(
        "code EMPTY    =",
        empty_code,
    )


    examples = con.execute(
        """
        SELECT *
        FROM schools
        WHERE code IS NULL
           OR TRIM(COALESCE(code,''))=''
        ORDER BY id
        LIMIT 30
        """
    ).fetchall()


    print()
    print(
        "EXAMPLES WITHOUT CODE =",
        len(examples),
    )


    for row in examples:

        print(
            json.dumps(
                dict(row),
                ensure_ascii=False,
                default=str,
            )
        )


    # ========================================================
    # 6. 8 SOURCES - FULL ROW
    # ========================================================

    print()
    print("6. 8 SOURCE SCHOOLS - FULL ROW")
    print("=" * 150)


    all_source_ids = sorted(
        {
            sid
            for case in CASES.values()
            for sid in case["source_ids"]
        }
    )


    marks = ",".join(
        "?"
        for _ in all_source_ids
    )


    source_rows = con.execute(
        f"""
        SELECT *
        FROM schools
        WHERE id IN ({marks})
        ORDER BY id
        """,
        all_source_ids,
    ).fetchall()


    if len(source_rows) != 8:
        raise RuntimeError(
            "DUNG: khong tim du 8 source."
        )


    for row in source_rows:

        print(
            json.dumps(
                dict(row),
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        )


    # ========================================================
    # 7. 4 COMMUNES - ALL SCHOOLS
    # ========================================================

    print()
    print("7. TOAN BO TRUONG TRONG 4 XA")
    print("=" * 150)


    for op, case in CASES.items():

        print()
        print("#" * 150)

        print(
            op,
            "| target =",
            case["target_name"],
            "| commune_id =",
            case["commune_id"],
        )


        rows = con.execute(
            """
            SELECT *
            FROM schools
            WHERE commune_id=?
            ORDER BY id
            """,
            (
                case["commune_id"],
            ),
        ).fetchall()


        print(
            "school count =",
            len(rows),
        )


        for row in rows:

            print(
                json.dumps(
                    dict(row),
                    ensure_ascii=False,
                    default=str,
                )
            )


    # ========================================================
    # 8. SCHOOL NAME HISTORY SCHEMA
    # ========================================================

    print()
    print("8. SCHOOL NAME HISTORY")
    print("-" * 150)


    if table_exists(
        con,
        "school_name_histories",
    ):

        print(
            "school_name_histories = EXISTS"
        )


        history_schema = [
            dict(x)
            for x in con.execute(
                """
                PRAGMA table_info(
                    school_name_histories
                )
                """
            ).fetchall()
        ]


        for row in history_schema:
            print(
                json.dumps(
                    row,
                    ensure_ascii=False,
                    default=str,
                )
            )


        history_cols = {
            str(x["name"])
            for x in history_schema
        }


        if "school_id" in history_cols:

            marks8 = ",".join(
                "?"
                for _ in all_source_ids
            )


            history_rows = con.execute(
                f"""
                SELECT *
                FROM school_name_histories
                WHERE school_id IN ({marks8})
                ORDER BY id
                """,
                all_source_ids,
            ).fetchall()


            print(
                "history rows for 8 sources =",
                len(history_rows),
            )


            for row in history_rows:

                print(
                    json.dumps(
                        dict(row),
                        ensure_ascii=False,
                        default=str,
                    )
                )

    else:

        print(
            "school_name_histories = NOT FOUND"
        )


    # ========================================================
    # 9. TABLES REFERENCING SCHOOLS
    # ========================================================

    print()
    print("9. FOREIGN KEYS REFERENCING schools")
    print("-" * 150)


    refs = []


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


        for fk_row in con.execute(
            "PRAGMA foreign_key_list("
            + qident(table)
            + ")"
        ).fetchall():

            fk_dict = dict(
                fk_row
            )


            if str(
                fk_dict.get("table")
                or ""
            ) != "schools":

                continue


            refs.append({
                "table":
                    table,

                "from":
                    fk_dict.get(
                        "from"
                    ),

                "to":
                    fk_dict.get(
                        "to"
                    ),

                "on_update":
                    fk_dict.get(
                        "on_update"
                    ),

                "on_delete":
                    fk_dict.get(
                        "on_delete"
                    ),
            })


    print(
        "reference count =",
        len(refs),
    )


    for item in refs:

        print(
            json.dumps(
                item,
                ensure_ascii=False,
                default=str,
            )
        )


    # ========================================================
    # 10. SUMMARY
    # ========================================================

    print()
    print("=" * 150)
    print("10. KET LUAN KY THUAT SO BO")
    print("=" * 150)


    code_column = next(
        x
        for x in schema
        if str(
            x["name"]
        ) == "code"
    )


    code_notnull = bool(
        code_column[
            "notnull"
        ]
    )


    print(
        "code NOT NULL =",
        code_notnull,
    )

    print(
        "existing NULL/EMPTY code =",
        null_code
        + empty_code,
    )


    if not code_notnull:

        print(
            "SCHEMA_ALLOW_NULL_CODE = YES"
        )

    else:

        print(
            "SCHEMA_ALLOW_NULL_CODE = NO"
        )


    if (
        null_code
        + empty_code
        > 0
    ):

        print(
            "DATABASE_HAS_CODELESS_SCHOOLS = YES"
        )

    else:

        print(
            "DATABASE_HAS_CODELESS_SCHOOLS = NO"
        )


finally:

    con.close()


# ============================================================
# 11. FILE SAFETY
# ============================================================

print()
print("=" * 150)
print("11. FILE SAFETY")
print("=" * 150)


for key, path in {
    "db": DB,
    "service": SERVICE,
    "engine": ENGINE,
    "resolution": RESOLUTION,
}.items():

    value = sha256(
        path
    )

    print(
        key,
        "=",
        value,
    )

    if value != EXPECTED[key]:

        raise RuntimeError(
            "DUNG: "
            + key
            + " bi thay doi."
        )


print()
print("=" * 150)
print(
    "KHAO SAT KHA NANG TAO DICH MOI: HOAN TAT"
)
print(
    "DATABASE = KHONG THAY DOI"
)
print(
    "CHUA TAO TRUONG MOI"
)
print(
    "CHUA SAP NHAP 4 PHUONG AN"
)
print("=" * 150)
