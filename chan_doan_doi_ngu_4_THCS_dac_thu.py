# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(r"C:\PhoCap")
DB = ROOT / "data" / "phocap.db"
ENGINE_FILE = ROOT / "app" / "services" / "school_merger_service.py"

EXPECTED_DB_SHA = (
    "c6a0f2f1a08e7e80a6e89cd0edfd83961f4d87930d5b8b1f3cdae8e770f4deee"
)

EXPECTED_ENGINE_SHA = (
    "414fb49a4c5f4fed7b571cc55df381678fe660cd8a675ecaa2f6fd70ebd7827a"
)

CASES = [
    {
        "op": "QD3805-OP-0399",
        "source_id": 1592,
        "target_id": 1594,
        "label": "THCS Quang Phong + THCS Cắm Muộn -> THCS Mường Quàng",
    },
    {
        "op": "QD3805-OP-0424",
        "source_id": 1485,
        "target_id": 1486,
        "label": "THCS Tiến Thắng + PTDTBT THCS Bính Thuận -> THCS Châu Tiến",
    },
    {
        "op": "QD3805-OP-0434",
        "source_id": 1647,
        "target_id": 1646,
        "label": "PTDTBT THCS Hội Nga + THCS Hạnh Thiết -> THCS Quỳ Châu",
    },
    {
        "op": "QD3805-OP-0451",
        "source_id": 1589,
        "target_id": 1590,
        "label": "THCS Châu Thái + THCS Châu Cường -> THCS Mường Ham",
    },
]

PREVIOUS_YEAR_ID = 1
CURRENT_YEAR_ID = 2


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def connect_ro():
    con = sqlite3.connect(
        DB.resolve().as_uri() + "?mode=ro",
        uri=True,
        timeout=120,
    )
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA query_only=ON")
    con.execute("PRAGMA foreign_keys=ON")
    return con


def table_columns(con, table):
    return [
        str(x["name"])
        for x in con.execute(
            f'PRAGMA table_info("{table}")'
        ).fetchall()
    ]


print("=" * 150)
print("THCS - CHAN DOAN DOI NGU 4 PHUONG AN DAC THU")
print("CHI DOC - KHONG SUA DATABASE - KHONG SAP NHAP")
print("=" * 150)

print()
print("1. HASH GATE")
print("-" * 150)

db_sha = sha256(DB)
engine_sha = sha256(ENGINE_FILE)

print("db     =", db_sha)
print("engine =", engine_sha)

if db_sha != EXPECTED_DB_SHA:
    raise RuntimeError(
        "DUNG: DB da thay doi so voi nen ngay sau THCS thuan."
    )

if engine_sha != EXPECTED_ENGINE_SHA:
    raise RuntimeError(
        "DUNG: merger engine da thay doi."
    )

for suffix in ("-wal", "-journal"):
    p = Path(str(DB) + suffix)
    size = p.stat().st_size if p.exists() else 0
    print(p.name, "=", size)
    if size:
        raise RuntimeError(
            "DUNG: database dang co WAL/JOURNAL."
        )


sys.path.insert(0, str(ROOT))

from app.services import school_merger_service as engine


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
    print("integrity =", integrity)
    print("FK        =", len(fk))

    if integrity.lower() != "ok" or fk:
        raise RuntimeError("DUNG: database health FAIL.")

    cols = table_columns(
        con,
        "staff_year_records",
    )

    print()
    print("3. CAC COT DOI NGU LIEN QUAN")
    print("-" * 150)

    interesting = [
        x for x in cols
        if x in {
            "id",
            "staff_member_id",
            "school_id",
            "school_year_id",
            "is_active",
            "position_group",
            "position_title",
            "status_code",
            "source_status_label",
            "notes",
            "source_level",
            "teaching_level",
        }
    ]

    print(interesting)

    summaries = []

    for index, case in enumerate(CASES, start=1):
        print()
        print("=" * 150)
        print(f"4.{index}. {case['op']}")
        print(case["label"])
        print("=" * 150)

        origin_ids = [
            int(case["source_id"]),
            int(case["target_id"]),
        ]

        marks = ",".join("?" for _ in origin_ids)

        rows = con.execute(
            f"""
            SELECT *
            FROM staff_year_records
            WHERE school_year_id=?
              AND school_id IN ({marks})
            ORDER BY school_id,id
            """,
            [
                PREVIOUS_YEAR_ID,
                *origin_ids,
            ],
        ).fetchall()

        print(
            "RAW ROWS 2025-2026 =",
            len(rows),
        )

        all_counter = Counter()
        eligible_counter = Counter()
        excluded_counter = Counter()

        excluded = []
        eligible_ids = []
        duplicate_source_staff = Counter()

        for row in rows:
            data = dict(row)

            staff_id = int(
                row["staff_member_id"]
            )

            duplicate_source_staff[
                staff_id
            ] += 1

            category = engine._classify_staff(
                row
            )

            inactive = bool(
                engine._staff_inactive(
                    row
                )
            )

            all_counter[
                category
            ] += 1

            if inactive:
                excluded_counter[
                    category
                ] += 1

                excluded.append({
                    "record_id":
                        int(row["id"]),

                    "staff_member_id":
                        staff_id,

                    "school_id":
                        int(row["school_id"]),

                    "category":
                        category,

                    "is_active":
                        data.get("is_active"),

                    "position_group":
                        data.get("position_group"),

                    "position_title":
                        data.get("position_title"),

                    "status_code":
                        data.get("status_code"),

                    "source_status_label":
                        data.get(
                            "source_status_label"
                        ),

                    "notes":
                        data.get("notes"),

                    "source_level":
                        data.get("source_level"),

                    "teaching_level":
                        data.get(
                            "teaching_level"
                        ),
                })

            else:
                eligible_counter[
                    category
                ] += 1

                eligible_ids.append(
                    staff_id
                )

        duplicate_ids = {
            staff_id: n
            for staff_id, n
            in duplicate_source_staff.items()
            if n > 1
        }

        existing_current_elsewhere = []

        for staff_id in eligible_ids:
            existing = con.execute(
                """
                SELECT
                    id,
                    staff_member_id,
                    school_id,
                    school_year_id,
                    is_active
                FROM staff_year_records
                WHERE staff_member_id=?
                  AND school_year_id=?
                ORDER BY id
                """,
                (
                    staff_id,
                    CURRENT_YEAR_ID,
                ),
            ).fetchall()

            for x in existing:
                if int(x["school_id"]) not in origin_ids:
                    existing_current_elsewhere.append(
                        dict(x)
                    )

        print()
        print("PHAN LOAI TAT CA =")
        print(
            json.dumps(
                dict(all_counter),
                ensure_ascii=False,
                indent=2,
            )
        )

        print()
        print("ENGINE ELIGIBLE =")
        print(
            json.dumps(
                dict(eligible_counter),
                ensure_ascii=False,
                indent=2,
            )
        )

        print()
        print("ENGINE EXCLUDED =")
        print(
            json.dumps(
                dict(excluded_counter),
                ensure_ascii=False,
                indent=2,
            )
        )

        print()
        print(
            "ELIGIBLE TOTAL =",
            sum(
                eligible_counter.values()
            ),
        )

        print(
            "EXCLUDED TOTAL =",
            len(excluded),
        )

        print(
            "DUPLICATE STAFF_MEMBER_ID =",
            duplicate_ids,
        )

        print(
            "CURRENT ELSEWHERE =",
            len(
                existing_current_elsewhere
            ),
        )

        if excluded:
            print()
            print("CAC HO SO BI ENGINE LOAI:")
            print(
                json.dumps(
                    excluded,
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                )
            )
        else:
            print()
            print(
                "CAC HO SO BI ENGINE LOAI: []"
            )

        if existing_current_elsewhere:
            print()
            print(
                "HO SO DA CO 2026-2027 O TRUONG KHAC:"
            )
            print(
                json.dumps(
                    existing_current_elsewhere,
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                )
            )

        if duplicate_ids:
            raise RuntimeError(
                case["op"]
                + ": co duplicate staff_member_id "
                  "trong nhom 2025-2026."
            )

        if any(
            engine._classify_staff(row)
            == "CHUA_XAC_DINH"
            for row in rows
        ):
            raise RuntimeError(
                case["op"]
                + ": co nhan su CHUA_XAC_DINH."
            )

        summaries.append({
            "operation_id":
                case["op"],

            "raw_total":
                len(rows),

            "eligible_total":
                sum(
                    eligible_counter.values()
                ),

            "excluded_total":
                len(excluded),

            "excluded":
                excluded,

            "eligible_by_group":
                dict(
                    eligible_counter
                ),

            "current_elsewhere":
                len(
                    existing_current_elsewhere
                ),
        })

    print()
    print("=" * 150)
    print("5. TONG KET")
    print("=" * 150)

    for item in summaries:
        print(
            item["operation_id"],
            "| RAW=",
            item["raw_total"],
            "| ELIGIBLE=",
            item["eligible_total"],
            "| EXCLUDED=",
            item["excluded_total"],
            "| CURRENT_ELSEWHERE=",
            item["current_elsewhere"],
            "| GROUP=",
            item["eligible_by_group"],
        )

finally:
    con.close()


print()
print("=" * 150)
print("6. FILE SAFETY")
print("=" * 150)

db_after = sha256(DB)
engine_after = sha256(ENGINE_FILE)

print("db     :", db_sha, "->", db_after)
print("engine :", engine_sha, "->", engine_after)

if db_after != db_sha:
    raise RuntimeError(
        "DUNG: DB bi thay doi trong luc chan doan."
    )

if engine_after != engine_sha:
    raise RuntimeError(
        "DUNG: engine bi thay doi."
    )

print()
print("=" * 150)
print("CHAN DOAN DOI NGU 4 PHUONG AN: HOAN TAT")
print("DATABASE = KHONG THAY DOI")
print("CHUA SAP NHAP 4 PHUONG AN")
print("=" * 150)
