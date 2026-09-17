# -*- coding: utf-8 -*-
from __future__ import annotations

import difflib
import hashlib
import json
import re
import sqlite3
import sys
import unicodedata
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

PLANS = (
    ROOT
    / "data"
    / "school_merger_approved_plans.json"
)


EXPECTED = {
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


YEAR_PREVIOUS = 1
YEAR_CURRENT = 2
MOVE_YEARS = [2, 8]


CASES = [
    {
        "op": "QD3805-OP-0025",
        "commune": "Thành Vinh",
        "aliases": [
            "THCS Quang Trung",
            "THCS Đội Cung",
        ],
        "official_codes": [
            "40412512",
            "40431506",
            "40412505",
            "40427502",
        ],
        "target_codes": [
            "40412512",
            "40431506",
        ],
        "official_target":
            "THCS Quang Trung",
    },

    {
        "op": "QD3805-OP-0108",
        "commune": "Mậu Thạch",
        "aliases": [
            "PTDT BT THCS Thạch Ngàn",
            "PTDT Bán trú THCS Thạch Ngàn",
            "THCS Mậu Đôn",
        ],
        "official_codes": [
            "40422504",
            "40422510",
        ],
        "target_codes": [
            "40422504",
        ],
        "official_target":
            "PTDT Bán trú THCS Thạch Ngàn",
    },

    {
        "op": "QD3805-OP-0172",
        "commune": "Bạch Hà",
        "aliases": [
            "THCS Đại Sơn",
            "THCS Lê Hồng Phong (Mỹ Sơn)",
            "THCS Trù Sơn",
        ],
        "official_codes": [
            "40427513",
            "40427521",
        ],
        "target_codes": [
            "40427513",
        ],
        "official_target":
            "THCS Đại Sơn",
    },

    {
        "op": "QD3805-OP-0203",
        "commune": "Thuần Trung",
        "aliases": [
            "THCS Kim Đồng (Minh Sơn)",
            "THCS Lê Hồng Phong (Nhân Sơn)",
            "THCS Lê Hồng Phong",
        ],
        "official_codes": [
            "40427522",
            "40431501",
        ],
        "target_codes": [
            "40427522",
            "40431501",
        ],
        "official_target":
            "THCS Lê Hồng Phong",
    },

    {
        "op": "QD3805-OP-0210",
        "commune": "Văn Hiến",
        "aliases": [
            "THCS Trần Phú",
            "THCS Thượng Sơn",
        ],
        "official_codes": [
            "40427510",
            "40427505",
        ],
        "target_codes": [
            "40427510",
        ],
        "official_target":
            "THCS Trần Phú",
    },

    {
        "op": "QD3805-OP-0644",
        "commune": "Yên Hòa",
        "aliases": [
            "PTDTBT THCS Yên Thắng",
            "PT DTBT Yên Hòa",
            "THCS Yên Hòa",
        ],
        "official_codes": [
            "40418511",
        ],
        "target_codes": [
            "40418511",
        ],
        "official_target":
            "PTDTBT THCS Yên Thắng",
    },
]


WANTED = {
    x["op"]
    for x in CASES
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

    return re.sub(
        r"\s+",
        " ",
        text,
    ).strip()


def simple_school_name(value) -> str:

    text = norm(value)

    prefixes = [
        "TRUONG ",
        "PTDTBT ",
        "PT DTBT ",
        "PTDT BT ",
        "BAN TRU ",
    ]

    changed = True

    while changed:

        changed = False

        for prefix in prefixes:

            if text.startswith(prefix):

                text = text[
                    len(prefix):
                ].strip()

                changed = True

    return text


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
    name,
):

    return (
        con.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type='table'
              AND name=?
            """,
            (name,),
        ).fetchone()
        is not None
    )


def columns(
    con,
    table,
):

    return {
        str(x["name"])
        for x in con.execute(
            f"""
            PRAGMA table_info(
                {qident(table)}
            )
            """
        ).fetchall()
    }


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

        cols = columns(
            con,
            table,
        )

        if {
            "school_id",
            "school_year_id",
        }.issubset(cols):

            result.append(
                table
            )

    return result


def residual(
    con,
    school_id,
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
                    + " WHERE school_id=? "
                    + "AND school_year_id IN ("
                    + marks(len(MOVE_YEARS))
                    + ")"
                ),
                [
                    int(school_id),
                    *MOVE_YEARS,
                ],
            ).fetchone()[0]
            or 0
        )

        if n:
            result[table] = n

    return result


def user_state(
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


def staff_state(
    con,
    merger,
    school_id,
    year_id,
):

    rows = con.execute(
        """
        SELECT *
        FROM staff_year_records
        WHERE school_id=?
          AND school_year_id=?
        ORDER BY id
        """,
        (
            int(school_id),
            int(year_id),
        ),
    ).fetchall()

    groups = Counter()

    eligible = 0
    excluded = 0
    ids = []

    for row in rows:

        staff_id = row[
            "staff_member_id"
        ]

        if staff_id is not None:
            ids.append(
                int(staff_id)
            )

        category = (
            merger._classify_staff(
                row
            )
        )

        if year_id == YEAR_PREVIOUS:

            if merger._staff_inactive(
                row
            ):
                excluded += 1
                continue

        else:

            if (
                "is_active" in row.keys()
                and int(
                    row["is_active"]
                    or 0
                )
                != 1
            ):
                continue

        eligible += 1
        groups[category] += 1

    duplicate = {
        k: v
        for k, v
        in Counter(ids).items()
        if v > 1
    }

    return {
        "raw": len(rows),
        "eligible": eligible,
        "excluded": excluded,
        "groups": dict(groups),
        "duplicates": duplicate,
    }


def walk_operation(
    obj,
    op,
):

    found = []

    def walk(value, path="$"):

        if isinstance(
            value,
            dict,
        ):

            if str(
                value.get(
                    "operation_id"
                )
                or ""
            ) == op:

                found.append({
                    "path": path,
                    "item": dict(value),
                })

            for key, child in value.items():

                walk(
                    child,
                    path
                    + "."
                    + str(key),
                )

        elif isinstance(
            value,
            list,
        ):

            for i, child in enumerate(
                value
            ):

                walk(
                    child,
                    path
                    + f"[{i}]",
                )

    walk(obj)

    return found


def commune_map(con):

    if not table_exists(
        con,
        "communes",
    ):
        return {}

    cols = columns(
        con,
        "communes",
    )

    if not {
        "id",
        "name",
    }.issubset(cols):
        return {}

    return {
        int(x["id"]):
            str(x["name"] or "")

        for x in con.execute(
            """
            SELECT id,name
            FROM communes
            """
        )
    }


def school_rows(con):

    cols = columns(
        con,
        "schools",
    )

    extra = []

    for candidate in (
        "level_code",
        "education_level",
        "level",
        "school_level",
    ):

        if candidate in cols:
            extra.append(candidate)

    sql = (
        "SELECT "
        "id,code,name,commune_id,is_active"
    )

    for col in extra:
        sql += "," + qident(col)

    sql += " FROM schools ORDER BY id"

    return [
        dict(x)
        for x in con.execute(sql)
    ]


def school_level_text(row):

    for key in (
        "level_code",
        "education_level",
        "level",
        "school_level",
    ):

        if key in row:
            return str(
                row.get(key)
                or ""
            )

    return ""


def candidate_schools(
    rows,
    communes,
    case,
):

    official_codes = set(
        case["official_codes"]
    )

    commune_norm = norm(
        case["commune"]
    )

    results = {}

    # 1. Code exact.
    for row in rows:

        code = str(
            row.get("code")
            or ""
        ).strip()

        if code in official_codes:

            item = dict(row)

            item[
                "match_reason"
            ] = "CODE_EXACT"

            results[
                int(row["id"])
            ] = item

    # 2. Name similarity.
    for row in rows:

        level_text = norm(
            school_level_text(row)
        )

        if (
            level_text
            and "THCS" not in level_text
        ):
            continue

        commune_name = str(
            communes.get(
                int(
                    row.get(
                        "commune_id"
                    )
                    or 0
                ),
                "",
            )
        )

        cn = norm(
            commune_name
        )

        commune_ok = (
            not commune_norm
            or not cn
            or commune_norm in cn
            or cn in commune_norm
        )

        if not commune_ok:
            continue

        db_name = simple_school_name(
            row.get("name")
        )

        best = 0.0
        best_alias = None

        for alias in case[
            "aliases"
        ]:

            score = (
                difflib.SequenceMatcher(
                    None,
                    db_name,
                    simple_school_name(
                        alias
                    ),
                ).ratio()
            )

            if score > best:

                best = score
                best_alias = alias

        if best >= 0.58:

            item = dict(row)

            item[
                "match_reason"
            ] = (
                "NAME_SIMILAR "
                + f"{best:.3f} "
                + str(best_alias)
            )

            if int(
                row["id"]
            ) not in results:

                results[
                    int(row["id"])
                ] = item

    return [
        results[key]
        for key in sorted(results)
    ]


print("=" * 150)
print(
    "THCS - KHAO SAT 6 PHUONG AN "
    "MAPPING / ALIAS CON LAI"
)
print(
    "CHI DOC - KHONG SUA DB - "
    "KHONG SUA RESOLUTION - KHONG SAP NHAP"
)
print("=" * 150)


# ============================================================
# 1. HASH GATE
# ============================================================

print()
print("1. HASH GATE")
print("-" * 150)


PATHS = {
    "db": DB,
    "engine": ENGINE,
    "service": SERVICE,
    "resolution": RESOLUTION,
    "plans": PLANS,
}

before = {}

for key, path in PATHS.items():

    value = sha256(
        path
    )

    before[key] = value

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

    p = Path(
        str(DB)
        + suffix
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
            "DUNG: hay dung server."
        )


# ============================================================
# 2. IMPORT
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
# 3. SERVICE / RESOLUTION GATE
# ============================================================

preview = (
    levelsvc.build_level_batch_preview(
        school_year_id=YEAR_CURRENT,
        level_code="THCS",
    )
)


print()
print("2. SERVICE STATE")
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
    preview.get(
        "counts"
    )
    or {}
) != {
    "KEEP": 36,
    "DONE": 101,
    "READY": 0,
    "BLOCK": 0,
}:

    raise RuntimeError(
        "DUNG: service counts da thay doi."
    )


if len(
    preview.get(
        "candidates"
    )
    or []
) != 0:

    raise RuntimeError(
        "DUNG: xuat hien candidate."
    )


if not bool(
    preview.get(
        "previous_batch"
    )
):

    raise RuntimeError(
        "DUNG: mat previous THCS batch."
    )


resolution = json.loads(
    RESOLUTION.read_text(
        encoding="utf-8-sig"
    )
)

plans = json.loads(
    PLANS.read_text(
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


precompleted = [
    x
    for x in (
        resolution.get(
            "precompleted"
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

pre_counter = Counter(
    str(
        x.get(
            "operation_id"
        )
        or ""
    )
    for x in precompleted
)


for op in sorted(WANTED):

    if special_counter[op] != 1:

        raise RuntimeError(
            op
            + ": khong con dung 1 special."
        )

    if pre_counter[op] != 0:

        raise RuntimeError(
            op
            + ": da co precompleted."
        )


# ============================================================
# 4. DATABASE HEALTH
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
        integrity.lower() != "ok"
        or fk
    ):
        raise RuntimeError(
            "DUNG: DB health FAIL."
        )


    schools = school_rows(
        con
    )

    communes = commune_map(
        con
    )


    # ========================================================
    # 5. SIX CASES
    # ========================================================

    print()
    print("=" * 150)
    print("4. CHI TIET 6 PHUONG AN")
    print("=" * 150)


    summaries = []


    for index, case in enumerate(
        CASES,
        start=1,
    ):

        op = case["op"]

        print()
        print("#" * 150)

        print(
            f"[{index}/6] {op}"
        )

        print(
            "COMMUNE =",
            case["commune"],
        )

        print(
            "OFFICIAL TARGET =",
            case[
                "official_target"
            ],
        )

        print(
            "OFFICIAL CODES =",
            case[
                "official_codes"
            ],
        )

        print(
            "TARGET CODES =",
            case[
                "target_codes"
            ],
        )


        # ---------------------------
        # Resolution rule
        # ---------------------------

        rules = [
            x
            for x in special
            if str(
                x.get(
                    "operation_id"
                )
                or ""
            ) == op
        ]


        print()
        print(
            "RESOLUTION RULE ="
        )

        print(
            json.dumps(
                rules[0],
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        )


        # ---------------------------
        # Approved plan object
        # ---------------------------

        plan_hits = walk_operation(
            plans,
            op,
        )


        print()
        print(
            "APPROVED PLAN HIT COUNT =",
            len(plan_hits),
        )


        for hit in plan_hits[:5]:

            print(
                "PATH =",
                hit["path"],
            )

            print(
                json.dumps(
                    hit["item"],
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                )
            )


        # ---------------------------
        # Current DB candidates
        # ---------------------------

        candidates = candidate_schools(
            schools,
            communes,
            case,
        )


        print()
        print(
            "DB CANDIDATES =",
            len(candidates),
        )


        candidate_output = []


        for row in candidates:

            school_id = int(
                row["id"]
            )

            previous = staff_state(
                con,
                merger,
                school_id,
                YEAR_PREVIOUS,
            )

            current = staff_state(
                con,
                merger,
                school_id,
                YEAR_CURRENT,
            )

            users = user_state(
                con,
                school_id,
            )

            move_residual = residual(
                con,
                school_id,
            )

            commune_name = communes.get(
                int(
                    row.get(
                        "commune_id"
                    )
                    or 0
                ),
                "",
            )


            item = {
                "school_id":
                    school_id,

                "code":
                    row.get("code"),

                "name":
                    row.get("name"),

                "commune":
                    commune_name,

                "level":
                    school_level_text(
                        row
                    ),

                "is_active":
                    row.get(
                        "is_active"
                    ),

                "match_reason":
                    row.get(
                        "match_reason"
                    ),

                "staff_2025_2026":
                    previous,

                "staff_2026_2027":
                    current,

                "users":
                    users,

                "current_future_residual":
                    move_residual,
            }


            candidate_output.append(
                item
            )


            print()
            print(
                json.dumps(
                    item,
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                )
            )


        # ---------------------------
        # Existing merger evidence
        # ---------------------------

        audit_count = int(
            con.execute(
                """
                SELECT COUNT(*)
                FROM school_merger_operations
                WHERE summary_json LIKE ?
                """,
                (
                    "%"
                    + op
                    + "%",
                ),
            ).fetchone()[0]
            or 0
        )


        print()
        print(
            "EXISTING AUDIT ROWS FOR OP =",
            audit_count,
        )


        target_code_matches = [
            x
            for x in candidate_output
            if str(
                x.get("code")
                or ""
            )
            in set(
                case[
                    "target_codes"
                ]
            )
        ]


        active_candidates = [
            x
            for x in candidate_output
            if int(
                x.get(
                    "is_active"
                )
                or 0
            ) == 1
        ]


        summary = {
            "operation_id":
                op,

            "candidate_count":
                len(
                    candidate_output
                ),

            "active_candidate_count":
                len(
                    active_candidates
                ),

            "target_code_match_count":
                len(
                    target_code_matches
                ),

            "target_code_matches": [
                {
                    "id":
                        x[
                            "school_id"
                        ],

                    "code":
                        x[
                            "code"
                        ],

                    "name":
                        x[
                            "name"
                        ],

                    "active":
                        x[
                            "is_active"
                        ],
                }

                for x in target_code_matches
            ],

            "audit_rows":
                audit_count,

            "status":
                (
                    "CAN_REVIEW_MAPPING"
                    if candidate_output
                    else
                    "NO_DB_CANDIDATE"
                ),
        }


        summaries.append(
            summary
        )


    # ========================================================
    # 6. SUMMARY
    # ========================================================

    print()
    print("=" * 150)
    print("5. TONG KET 6 PHUONG AN")
    print("=" * 150)


    for item in summaries:

        print(
            json.dumps(
                item,
                ensure_ascii=False,
                default=str,
            )
        )


finally:

    con.close()


# ============================================================
# 7. FILE SAFETY
# ============================================================

print()
print("=" * 150)
print("6. FILE SAFETY")
print("=" * 150)


for key, path in PATHS.items():

    after = sha256(
        path
    )

    print(
        key,
        ":",
        before[key],
        "->",
        after,
    )

    if after != before[key]:

        raise RuntimeError(
            "DUNG: "
            + key
            + " bi thay doi."
        )


print()
print("=" * 150)

print(
    "KHAO SAT 6 THCS MAPPING/ALIAS: HOAN TAT"
)

print(
    "DATABASE = KHONG THAY DOI"
)

print(
    "RESOLUTION = KHONG THAY DOI"
)

print(
    "APPROVED PLANS = KHONG THAY DOI"
)

print(
    "KHONG SAP NHAP BAT KY TRUONG NAO"
)

print()
print(
    "READY_FOR_REVIEW_6_THCS_MAPPING_ALIAS=YES"
)

print("=" * 150)
