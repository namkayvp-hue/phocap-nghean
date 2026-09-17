# -*- coding: utf-8 -*-

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

EXPECTED_DB = (
    "706279fe9cd63f9f01c4c3d7637f955534280b7b745e333b0b6943c2e64aed89"
)


def sha256(path):
    h = hashlib.sha256()

    with open(path, "rb") as f:
        for block in iter(
            lambda: f.read(1024 * 1024),
            b"",
        ):
            h.update(block)

    return h.hexdigest()


print("=" * 140)
print("KHAO SAT CACH GHI NHAT KY 3 THCS DAC THU - CHI DOC")
print("=" * 140)

before = sha256(DB)

print("DB SHA =", before)

if before != EXPECTED_DB:
    raise RuntimeError(
        "DUNG: database khong dung nen da khoa."
    )

for suffix in ("-wal", "-journal"):

    p = Path(str(DB) + suffix)

    size = (
        p.stat().st_size
        if p.exists()
        else 0
    )

    print(p.name, "=", size)

    if size:
        raise RuntimeError(
            "DUNG: hay dung server."
        )


sys.path.insert(
    0,
    str(ROOT),
)

from app.services import (
    school_merger_level_batch_service
    as levelsvc
)


OFFICIAL = str(
    levelsvc.OFFICIAL_EXECUTION_TABLE
)

BATCH = str(
    levelsvc.BATCH_TABLE
)


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


try:

    print()
    print("1. DATABASE HEALTH")
    print("-" * 140)

    print(
        "integrity =",
        con.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0],
    )

    fk = con.execute(
        "PRAGMA foreign_key_check"
    ).fetchall()

    print(
        "FK =",
        len(fk),
    )


    print()
    print("2. OFFICIAL TABLE")
    print("-" * 140)

    print(
        "TABLE =",
        OFFICIAL,
    )


    info = con.execute(
        f'PRAGMA table_info("{OFFICIAL}")'
    ).fetchall()


    for row in info:

        print(
            dict(row)
        )


    print()
    print("INDEXES:")

    indexes = con.execute(
        f'PRAGMA index_list("{OFFICIAL}")'
    ).fetchall()


    for idx in indexes:

        print(
            dict(idx)
        )

        idx_name = str(
            idx["name"]
        )

        details = con.execute(
            f'PRAGMA index_info("{idx_name}")'
        ).fetchall()

        print(
            "  columns =",
            [
                dict(x)
                for x in details
            ],
        )


    print()
    print("3. 4 SPECIAL EXECUTIONS DA COMMIT TRUOC")
    print("-" * 140)


    known_plan_ids = [
        "PA2026-35F6C2558FC4",
        "PA2026-F228D672FCAC",
        "PA2026-6948B60DF298",
        "PA2026-CC0F70262554",
    ]


    marks = ",".join(
        "?"
        for _ in known_plan_ids
    )


    rows = con.execute(
        (
            f'SELECT * FROM "{OFFICIAL}" '
            f'WHERE plan_id IN ({marks}) '
            f'ORDER BY id'
        ),
        known_plan_ids,
    ).fetchall()


    print(
        "ROWS =",
        len(rows),
    )


    for row in rows:

        data = dict(row)

        print()
        print(
            json.dumps(
                data,
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        )


    print()
    print("4. AUDIT OPERATIONS CUA 4 SPECIAL CU")
    print("-" * 140)


    audits = con.execute(
        """
        SELECT
            id,
            school_year_id,
            target_school_id,
            source_school_ids_json,
            actor_user_id,
            backup_name,
            summary_json,
            created_at
        FROM school_merger_operations
        WHERE summary_json LIKE '%QD3805-OP-0399%'
           OR summary_json LIKE '%QD3805-OP-0424%'
           OR summary_json LIKE '%QD3805-OP-0434%'
           OR summary_json LIKE '%QD3805-OP-0451%'
        ORDER BY id
        """
    ).fetchall()


    print(
        "ROWS =",
        len(audits),
    )


    for row in audits:

        data = dict(row)

        try:
            summary = json.loads(
                str(
                    data.get(
                        "summary_json"
                    )
                    or "{}"
                )
            )
        except Exception:
            summary = {
                "RAW":
                    data.get(
                        "summary_json"
                    )
            }

        print()
        print(
            "AUDIT ID =",
            data["id"],
        )

        print(
            "target =",
            data[
                "target_school_id"
            ],
        )

        print(
            "sources =",
            data[
                "source_school_ids_json"
            ],
        )

        print(
            "backup =",
            data[
                "backup_name"
            ],
        )

        print(
            "SUMMARY =",
        )

        print(
            json.dumps(
                summary,
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        )


    print()
    print("5. KIEM TRA 3 OP MOI")
    print("-" * 140)


    for op in (
        "QD3805-OP-0108",
        "QD3805-OP-0210",
        "QD3805-OP-0644",
    ):

        audit_n = int(
            con.execute(
                """
                SELECT COUNT(*)
                FROM school_merger_operations
                WHERE summary_json LIKE ?
                """,
                (
                    "%" + op + "%",
                ),
            ).fetchone()[0]
            or 0
        )

        print(
            op,
            "| audit rows =",
            audit_n,
        )


    batch_count = int(
        con.execute(
            (
                f'SELECT COUNT(*) '
                f'FROM "{BATCH}" '
                f"WHERE school_year_id=2 "
                f"AND level_code='THCS'"
            )
        ).fetchone()[0]
        or 0
    )


    print()
    print(
        "THCS BATCH COUNT =",
        batch_count,
    )


finally:

    con.close()


after = sha256(DB)

print()
print("6. FILE SAFETY")
print("-" * 140)

print(
    "DB:",
    before,
    "->",
    after,
)

if after != before:
    raise RuntimeError(
        "DUNG: database bi thay doi."
    )


print()
print("=" * 140)
print("KHAO SAT NHAT KY DAC THU: HOAN TAT")
print("DATABASE = KHONG THAY DOI")
print("KHONG SAP NHAP BAT KY TRUONG NAO")
print("=" * 140)
