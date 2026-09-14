from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from pathlib import Path


sys.dont_write_bytecode = True

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


ROOT = Path(r"C:\PhoCap")

DB = ROOT / "data" / "phocap.db"

SERVICE = (
    ROOT / "app" / "services"
    / "school_merger_level_batch_service.py"
)

LOCK = (
    ROOT / "data" / "school_merger_registry"
    / "qd3805_level_lock.json"
)

RESOLUTION = (
    ROOT / "data" / "school_merger_registry"
    / "qd3805_mn_resolution.json"
)

ROSTER = (
    ROOT / "data" / "school_merger_source_rosters"
    / "MN_2025_2026.json"
)


EXPECTED = {
    "db":
        "882e4925fd3e39d7e097ce127612c093"
        "852075e608d3f937294135282afec75a",

    "service":
        "963b8d6a280d8abef8e96486abd87d77"
        "cea289b08d2edb497647f250ed1b2af8",

    "lock":
        "ad310048a4c5b239404e0902cc04fda1"
        "d73474d11a739a2ca009d2727e4390c3",

    "resolution":
        "22ca7931ec40408ced25a3bde14a9672c"
        "04e12a760a077a44bb9d65b709b1163",

    "roster":
        "ef865f74aa51c2700ceb7746d5433b63"
        "fc6a52a4e3169014ebe0e446ac441120",
}


CODES = {
    "DIEN_DOAI": ["40425339"],
    "DIEN_TRUONG": ["40425311"],
    "DIEN_YEN": ["40425303"],

    "HUNG_LINH": ["40431310"],
    "LONG_XA": ["40431317"],
    "XUAN_LAM": ["40430323", "40431307"],

    "HOA_SEN": ["40000301", "40419336"],
}


NAME_SEARCHES = [
    "Diễn Đoài",
    "Diễn Trường",
    "Diễn Yên",
    "Hưng Lĩnh",
    "Long Xá",
    "Xuân Lam",
    "Hoa Sen",
    "Hermann",
    "Gmeiner",
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


def qident(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def connect_ro():
    con = sqlite3.connect(
        DB.resolve().as_uri() + "?mode=ro",
        uri=True,
        timeout=90,
    )

    con.row_factory = sqlite3.Row
    con.execute("PRAGMA query_only=ON")
    con.execute("PRAGMA foreign_keys=ON")

    return con


def table_exists(con, table):
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


def columns(con, table):
    return [
        str(x["name"])
        for x in con.execute(
            f"PRAGMA table_info({qident(table)})"
        ).fetchall()
    ]


def school_by_code(con, code):
    rows = con.execute(
        """
        SELECT
            id,
            code,
            name,
            commune_id,
            is_active
        FROM schools
        WHERE TRIM(code)=?
        ORDER BY id
        """,
        (code,),
    ).fetchall()

    return [dict(x) for x in rows]


def school_by_name(con, text):
    rows = con.execute(
        """
        SELECT
            id,
            code,
            name,
            commune_id,
            is_active
        FROM schools
        WHERE LOWER(name) LIKE LOWER(?)
        ORDER BY id
        """,
        ("%" + text + "%",),
    ).fetchall()

    return [dict(x) for x in rows]


def class_count(con, school_id, year_id):
    if not table_exists(con, "classes"):
        return None

    cols = set(columns(con, "classes"))

    if not {
        "school_id",
        "school_year_id",
    }.issubset(cols):
        return None

    return int(
        con.execute(
            """
            SELECT COUNT(*)
            FROM classes
            WHERE school_id=?
              AND school_year_id=?
            """,
            (school_id, year_id),
        ).fetchone()[0]
        or 0
    )


def class_rows(con, school_id, year_id):
    if not table_exists(con, "classes"):
        return []

    cols = columns(con, "classes")

    wanted = [
        x
        for x in (
            "id",
            "school_id",
            "school_year_id",
            "code",
            "name",
            "class_name",
            "grade",
            "grade_level",
            "age_group",
            "campus",
            "campus_name",
            "site",
            "site_name",
            "branch",
            "branch_name",
            "location",
            "note",
            "notes",
            "is_active",
        )
        if x in cols
    ]

    if not wanted:
        wanted = cols

    select_cols = ", ".join(
        qident(x)
        for x in wanted
    )

    rows = con.execute(
        f"""
        SELECT {select_cols}
        FROM classes
        WHERE school_id=?
          AND school_year_id=?
        ORDER BY id
        """,
        (school_id, year_id),
    ).fetchall()

    return [dict(x) for x in rows]


def enrollment_count(con, school_id, year_id):
    if not table_exists(
        con,
        "student_enrollments",
    ):
        return None

    cols = set(
        columns(
            con,
            "student_enrollments",
        )
    )

    if not {
        "school_id",
        "school_year_id",
    }.issubset(cols):
        return None

    return int(
        con.execute(
            """
            SELECT COUNT(*)
            FROM student_enrollments
            WHERE school_id=?
              AND school_year_id=?
            """,
            (school_id, year_id),
        ).fetchone()[0]
        or 0
    )


print("=" * 128)
print("KIEM TOAN 3 TRUONG HOP DAC THU MN - BUOC CHAN DOAN")
print("CHI DOC - KHONG SUA DATABASE / SOURCE / REGISTRY")
print("=" * 128)


# ============================================================
# 1. HASH GATE
# ============================================================

paths = {
    "db": DB,
    "service": SERVICE,
    "lock": LOCK,
    "resolution": RESOLUTION,
    "roster": ROSTER,
}

before = {}


print()
print("=" * 128)
print("1. HASH GATE")
print("=" * 128)


for key, path in paths.items():

    value = sha256(path)

    before[key] = value

    print(
        f"{key:12s} = {value}"
    )

    if value != EXPECTED[key]:
        raise RuntimeError(
            "DUNG: "
            + key
            + " khong dung snapshot sau batch MN."
        )


con = connect_ro()

try:

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


    print()
    print("=" * 128)
    print("2. DATABASE HEALTH")
    print("=" * 128)

    print("integrity =", integrity)
    print("FK        =", fk)


    # ========================================================
    # 3. SCHOOL CANDIDATES
    # ========================================================

    print()
    print("=" * 128)
    print("3. TIM TRUONG THEO MA")
    print("=" * 128)


    resolved = {}


    for label, code_list in CODES.items():

        print()
        print("---", label, "---")

        found = []

        for code in code_list:

            rows = school_by_code(
                con,
                code,
            )

            print(
                "CODE",
                code,
                "=",
                json.dumps(
                    rows,
                    ensure_ascii=False,
                ),
            )

            found.extend(rows)

        resolved[label] = {
            int(x["id"]): x
            for x in found
        }


    print()
    print("=" * 128)
    print("4. TIM TRUONG THEO TEN")
    print("=" * 128)


    name_found = {}


    for text in NAME_SEARCHES:

        rows = school_by_name(
            con,
            text,
        )

        name_found[text] = rows

        print()
        print(
            text,
            "=",
            json.dumps(
                rows,
                ensure_ascii=False,
            ),
        )


    # ========================================================
    # 5. CLASS SCHEMA
    # ========================================================

    print()
    print("=" * 128)
    print("5. SCHEMA CLASSES")
    print("=" * 128)


    if table_exists(
        con,
        "classes",
    ):

        print(
            columns(
                con,
                "classes",
            )
        )

    else:

        print(
            "KHONG CO TABLE classes"
        )


    # ========================================================
    # 6. COUNTS 2025-26 / 2026-27
    # ========================================================

    all_schools = {}


    for group in resolved.values():
        all_schools.update(group)


    for search_rows in name_found.values():

        for row in search_rows:
            all_schools[
                int(row["id"])
            ] = row


    print()
    print("=" * 128)
    print("6. SO LOP / HOC SINH THEO TRUONG")
    print("=" * 128)


    for sid in sorted(all_schools):

        s = all_schools[sid]

        print()
        print("-" * 128)

        print(
            "SCHOOL =",
            json.dumps(
                s,
                ensure_ascii=False,
            ),
        )

        for year_id, year_label in (
            (1, "2025-2026"),
            (2, "2026-2027"),
        ):

            print(
                year_label,
                "| classes =",
                class_count(
                    con,
                    sid,
                    year_id,
                ),
                "| enrollments =",
                enrollment_count(
                    con,
                    sid,
                    year_id,
                ),
            )


    # ========================================================
    # 7. OP0141
    # ========================================================

    print()
    print("=" * 128)
    print("7. OP-0141 - DIEN YEN / DIEN DOAI / DIEN TRUONG")
    print("=" * 128)


    ids_0141 = []


    for key in (
        "DIEN_YEN",
        "DIEN_DOAI",
        "DIEN_TRUONG",
    ):
        ids_0141.extend(
            resolved.get(
                key,
                {},
            ).keys()
        )


    for sid in sorted(set(ids_0141)):

        s = all_schools[sid]

        print()
        print(
            "###",
            s["id"],
            s["code"],
            s["name"],
            "| active=",
            s["is_active"],
        )

        for year_id, label in (
            (1, "2025-2026"),
            (2, "2026-2027"),
        ):

            rows = class_rows(
                con,
                sid,
                year_id,
            )

            print(
                label,
                "COUNT=",
                len(rows),
            )

            for row in rows:
                print(
                    json.dumps(
                        row,
                        ensure_ascii=False,
                        default=str,
                    )
                )


    # ========================================================
    # 8. OP0244
    # ========================================================

    print()
    print("=" * 128)
    print("8. OP-0244 - LONG XA / HUNG LINH / XUAN LAM")
    print("=" * 128)


    ids_0244 = []


    for key in (
        "LONG_XA",
        "HUNG_LINH",
        "XUAN_LAM",
    ):
        ids_0244.extend(
            resolved.get(
                key,
                {},
            ).keys()
        )


    for sid in sorted(set(ids_0244)):

        s = all_schools[sid]

        print()
        print(
            "###",
            s["id"],
            s["code"],
            s["name"],
            "| active=",
            s["is_active"],
        )

        for year_id, label in (
            (1, "2025-2026"),
            (2, "2026-2027"),
        ):

            rows = class_rows(
                con,
                sid,
                year_id,
            )

            print(
                label,
                "COUNT=",
                len(rows),
            )

            for row in rows:
                print(
                    json.dumps(
                        row,
                        ensure_ascii=False,
                        default=str,
                    )
                )


    # ========================================================
    # 9. OP0704
    # ========================================================

    print()
    print("=" * 128)
    print("9. OP-0704 - HOA SEN / HERMANN GMEINER")
    print("=" * 128)


    ids_0704 = set(
        resolved.get(
            "HOA_SEN",
            {},
        ).keys()
    )


    for text in (
        "Hoa Sen",
        "Hermann",
        "Gmeiner",
    ):

        for s in name_found.get(
            text,
            [],
        ):
            ids_0704.add(
                int(s["id"])
            )


    for sid in sorted(ids_0704):

        s = all_schools[sid]

        print()
        print(
            "###",
            s["id"],
            s["code"],
            s["name"],
            "| active=",
            s["is_active"],
        )

        for year_id, label in (
            (1, "2025-2026"),
            (2, "2026-2027"),
        ):

            rows = class_rows(
                con,
                sid,
                year_id,
            )

            print(
                label,
                "COUNT=",
                len(rows),
            )

            for row in rows:
                print(
                    json.dumps(
                        row,
                        ensure_ascii=False,
                        default=str,
                    )
                )


    # ========================================================
    # 10. MERGER LOGS LIEN QUAN
    # ========================================================

    print()
    print("=" * 128)
    print("10. MERGER LOGS LIEN QUAN")
    print("=" * 128)


    candidate_ids = sorted(
        set(all_schools)
    )


    if candidate_ids:

        for row in con.execute(
            """
            SELECT *
            FROM school_merger_operations
            WHERE school_year_id=2
            ORDER BY id
            """
        ).fetchall():

            d = dict(row)

            try:
                sources = json.loads(
                    d.get(
                        "source_school_ids_json"
                    )
                    or "[]"
                )
            except Exception:
                sources = []

            target = d.get(
                "target_school_id"
            )

            involved = set()

            for x in sources:
                try:
                    involved.add(int(x))
                except Exception:
                    pass

            try:
                involved.add(int(target))
            except Exception:
                pass


            if involved.intersection(
                candidate_ids
            ):

                print(
                    json.dumps(
                        d,
                        ensure_ascii=False,
                        default=str,
                    )
                )


finally:
    con.close()


# ============================================================
# 11. IMMUTABILITY
# ============================================================

print()
print("=" * 128)
print("11. FILE IMMUTABILITY")
print("=" * 128)


for key, path in paths.items():

    after = sha256(path)

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
print("=" * 128)
print("CHAN DOAN 3 DAC THU MN: HOAN TAT")
print("=" * 128)

print("KHONG SUA DATABASE.")
print("KHONG SUA SERVICE / REGISTRY / ROSTER.")
print("KHONG CHAY LAI SAP NHAP.")
print()
print(
    "BUOC TIEP THEO: DOI CHIEU CHINH XAC "
    "OP-0141 / OP-0244 / OP-0704."
)

print("=" * 128)
