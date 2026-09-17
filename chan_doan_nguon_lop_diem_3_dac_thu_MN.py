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

FILES = {
    "db": DB,
    "service": ROOT / "app" / "services" / "school_merger_level_batch_service.py",
    "lock": ROOT / "data" / "school_merger_registry" / "qd3805_level_lock.json",
    "resolution": ROOT / "data" / "school_merger_registry" / "qd3805_mn_resolution.json",
    "roster": ROOT / "data" / "school_merger_source_rosters" / "MN_2025_2026.json",
}

EXPECTED = {
    "db": "882e4925fd3e39d7e097ce127612c093852075e608d3f937294135282afec75a",
    "service": "963b8d6a280d8abef8e96486abd87d77cea289b08d2edb497647f250ed1b2af8",
    "lock": "ad310048a4c5b239404e0902cc04fda1d73474d11a739a2ca009d2727e4390c3",
    "resolution": "22ca7931ec40408ced25a3bde14a9672c04e12a760a077a44bb9d65b709b1163",
    "roster": "ef865f74aa51c2700ceb7746d5433b63fc6a52a4e3169014ebe0e446ac441120",
}


# Các school_id đã xác định từ chẩn đoán trước.
SCHOOLS = {
    524: "MN Diễn Yên",
    525: "MN Diễn Trường",
    528: "MN Diễn Đoài",

    885: "MN Long Xá",
    883: "MN Hưng Lĩnh",
    881: "MN Xuân Lam - mã 40431307",
    847: "MN Xuân Lâm - mã 40430323",

    1: "MN Hoa Sen - mã 40000301",
    274: "MN Hoa Sen - mã 40419336",
    1761: "PT Hermann Gmeiner Vinh",
}


TABLES = [
    "school_network_year_data",
    "school_staff_year_summaries",
    "school_mn01_csvc_inputs",
    "school_site_year_records",
    "school_structured_report_inputs",
    "classes",
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
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
    return con.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type='table' AND name=?
        """,
        (table,),
    ).fetchone() is not None


def columns(con, table):
    return [
        str(x["name"])
        for x in con.execute(
            f"PRAGMA table_info({qident(table)})"
        ).fetchall()
    ]


def pretty_json_text(value):
    if value in (None, ""):
        return value

    try:
        obj = json.loads(str(value))
        return obj
    except Exception:
        return value


print("=" * 130)
print("CHAN DOAN NGUON NHOM/LOP - DIEM TRUONG CUA 3 DAC THU MN")
print("CHI DOC - KHONG SUA DATABASE / SOURCE / REGISTRY")
print("=" * 130)


# ==========================================================
# 1. HASH GATE
# ==========================================================

before = {}

print()
print("=" * 130)
print("1. HASH GATE")
print("=" * 130)

for key, path in FILES.items():
    got = sha256(path)
    before[key] = got

    print(f"{key:12s} = {got}")

    if got != EXPECTED[key]:
        raise RuntimeError(
            f"DUNG: hash {key} da khac nen da khoa."
        )


con = connect_ro()

try:

    print()
    print("=" * 130)
    print("2. DATABASE HEALTH")
    print("=" * 130)

    integrity = str(
        con.execute("PRAGMA integrity_check").fetchone()[0]
    )
    fk = len(
        con.execute("PRAGMA foreign_key_check").fetchall()
    )

    print("integrity =", integrity)
    print("FK        =", fk)


    # ======================================================
    # 3. SCHEMA
    # ======================================================

    print()
    print("=" * 130)
    print("3. SCHEMA CAC BANG NGUON")
    print("=" * 130)

    for table in TABLES:
        print()
        print("---", table, "---")

        if not table_exists(con, table):
            print("KHONG TON TAI")
            continue

        print(columns(con, table))


    # ======================================================
    # 4. DỮ LIỆU THEO SCHOOL + YEAR
    # ======================================================

    print()
    print("=" * 130)
    print("4. DU LIEU 2025-2026 / 2026-2027")
    print("=" * 130)

    for sid, label in SCHOOLS.items():

        print()
        print("#" * 130)
        print(
            f"SCHOOL {sid} | {label}"
        )
        print("#" * 130)

        school = con.execute(
            """
            SELECT id,code,name,commune_id,is_active
            FROM schools
            WHERE id=?
            """,
            (sid,),
        ).fetchone()

        print(
            "SCHOOL ROW =",
            json.dumps(
                dict(school) if school else None,
                ensure_ascii=False,
            ),
        )

        for table in TABLES:

            if not table_exists(con, table):
                continue

            cols = columns(con, table)

            if "school_id" not in cols:
                continue

            where = "school_id=?"
            params = [sid]

            if "school_year_id" in cols:
                where += " AND school_year_id IN (1,2)"

            rows = con.execute(
                f"""
                SELECT *
                FROM {qident(table)}
                WHERE {where}
                ORDER BY
                    {
                        'school_year_id, id'
                        if 'school_year_id' in cols
                        else 'id'
                    }
                """,
                params,
            ).fetchall()

            print()
            print(
                f"[{table}] rows={len(rows)}"
            )

            for raw in rows:

                d = dict(raw)

                for key in list(d.keys()):
                    if (
                        key.endswith("_json")
                        or key == "data_json"
                    ):
                        d[key] = pretty_json_text(
                            d[key]
                        )

                print(
                    json.dumps(
                        d,
                        ensure_ascii=False,
                        default=str,
                    )
                )


    # ======================================================
    # 5. SEARCH TOÀN BỘ SITE / NETWORK THEO TÊN
    # ======================================================

    print()
    print("=" * 130)
    print("5. TIM DAU VET TEN DIEM TRUONG / HERMANN / LONG XA / DIEN YEN")
    print("=" * 130)

    needles = [
        "Diễn Yên",
        "Diễn Đoài",
        "Diễn Trường",
        "Long Xá",
        "Xuân Lam",
        "Xuân Lâm",
        "Hưng Lĩnh",
        "Hermann",
        "Gmeiner",
        "Hoa Sen",
    ]

    for table in (
        "school_site_year_records",
        "school_network_year_data",
        "school_structured_report_inputs",
    ):

        if not table_exists(con, table):
            continue

        cols = columns(con, table)

        text_cols = []

        for col in cols:
            col_lower = col.lower()

            if (
                "name" in col_lower
                or "note" in col_lower
                or "json" in col_lower
                or "source" in col_lower
                or "address" in col_lower
            ):
                text_cols.append(col)

        if not text_cols:
            continue

        print()
        print("-" * 130)
        print("TABLE =", table)

        for needle in needles:

            conditions = " OR ".join(
                f"CAST({qident(c)} AS TEXT) LIKE ?"
                for c in text_cols
            )

            params = [
                "%" + needle + "%"
                for _ in text_cols
            ]

            rows = con.execute(
                f"""
                SELECT *
                FROM {qident(table)}
                WHERE {conditions}
                ORDER BY id
                LIMIT 100
                """,
                params,
            ).fetchall()

            if not rows:
                continue

            print()
            print(
                "SEARCH =",
                needle,
                "| rows=",
                len(rows),
            )

            for raw in rows:

                d = dict(raw)

                for key in list(d.keys()):
                    if (
                        key.endswith("_json")
                        or key == "data_json"
                    ):
                        d[key] = pretty_json_text(
                            d[key]
                        )

                print(
                    json.dumps(
                        d,
                        ensure_ascii=False,
                        default=str,
                    )
                )


    # ======================================================
    # 6. SCHOOL STAFF SUMMARY - TÓM TẮT SỐ LỚP
    # ======================================================

    print()
    print("=" * 130)
    print("6. TOM TAT SO NHOM/LOP TRONG STAFF SUMMARY")
    print("=" * 130)

    if table_exists(
        con,
        "school_staff_year_summaries",
    ):

        for sid, label in SCHOOLS.items():

            rows = con.execute(
                """
                SELECT
                    school_id,
                    school_year_id,
                    institution_group,
                    total_groups_classes,
                    preschool_classes_3_4,
                    preschool_classes_5,
                    notes
                FROM school_staff_year_summaries
                WHERE school_id=?
                  AND school_year_id IN (1,2)
                ORDER BY school_year_id
                """,
                (sid,),
            ).fetchall()

            print(
                sid,
                "|",
                label,
                "=",
                json.dumps(
                    [dict(x) for x in rows],
                    ensure_ascii=False,
                    default=str,
                ),
            )


    # ======================================================
    # 7. MN01-CSVC - TÓM TẮT SỐ LỚP / ĐIỂM
    # ======================================================

    print()
    print("=" * 130)
    print("7. MN01-CSVC SO LOP / DIEM TRUONG")
    print("=" * 130)

    if table_exists(
        con,
        "school_mn01_csvc_inputs",
    ):

        for sid, label in SCHOOLS.items():

            rows = con.execute(
                """
                SELECT *
                FROM school_mn01_csvc_inputs
                WHERE school_id=?
                  AND school_year_id IN (1,2)
                ORDER BY school_year_id
                """,
                (sid,),
            ).fetchall()

            print(
                sid,
                "|",
                label,
                "=",
                json.dumps(
                    [dict(x) for x in rows],
                    ensure_ascii=False,
                    default=str,
                ),
            )


finally:
    con.close()


# ==========================================================
# 8. FILE IMMUTABILITY
# ==========================================================

print()
print("=" * 130)
print("8. FILE IMMUTABILITY")
print("=" * 130)

for key, path in FILES.items():
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
            f"DUNG: {key} bi thay doi."
        )


print()
print("=" * 130)
print("CHAN DOAN NGUON NHOM/LOP - DIEM TRUONG: HOAN TAT")
print("=" * 130)

print("KHONG SUA DATABASE.")
print("KHONG SUA SERVICE / REGISTRY / ROSTER.")
print("KHONG CHAY LAI SAP NHAP.")

print("=" * 130)
