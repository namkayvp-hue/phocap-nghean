# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


ROOT = Path(r"C:\PhoCap")

DB = ROOT / "data" / "phocap.db"

BACKUP_NAME = (
    "backup_truoc_sap_nhap_toan_cap_"
    "20260911_024023_315667_THCS"
)

EXPECTED_CURRENT_DB_SHA = (
    "c6a0f2f1a08e7e80a6e89cd0edfd83961f4d87930d5b8b1f3cdae8e770f4deee"
)

PAST_YEAR_IDS = [
    1, 3, 4, 5, 6, 7
]

SOURCE_IDS = [
    1432,
    1425,
    1428,
    1436,
    1438,
    1435,
    1452,
    1451,
    1446,
    1448,
    1447,
    1405,
    1458,
    1442,
    1440,
]

TARGET_IDS = [
    1430,
    1427,
    1429,
    1434,
    1437,
    1449,
    1450,
    1445,
    1444,
    1406,
    1457,
    1441,
    1443,
]

INVOLVED_IDS = sorted(
    set(
        SOURCE_IDS
        + TARGET_IDS
    )
)


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


def db_health(path: Path):

    con = connect_ro(
        path
    )

    try:

        integrity = str(
            con.execute(
                "PRAGMA integrity_check"
            ).fetchone()[0]
        )

        fk = con.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()

        return (
            integrity,
            len(fk),
        )

    finally:
        con.close()


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


def past_snapshot(
    path: Path,
):

    con = connect_ro(
        path
    )

    try:

        payload = {}

        counts = {}


        for table in year_tables(
            con
        ):

            info = con.execute(
                f"PRAGMA table_info({qident(table)})"
            ).fetchall()


            columns = [
                str(x["name"])
                for x in info
            ]


            sql = (
                "SELECT * FROM "
                + qident(table)
                + " WHERE school_id IN ("
                + marks(
                    len(
                        INVOLVED_IDS
                    )
                )
                + ")"
                + " AND school_year_id IN ("
                + marks(
                    len(
                        PAST_YEAR_IDS
                    )
                )
                + ")"
            )


            rows = con.execute(
                sql,
                [
                    *INVOLVED_IDS,
                    *PAST_YEAR_IDS,
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
                "columns":
                    columns,

                "rows":
                    normalized,
            }


            counts[
                table
            ] = len(
                normalized
            )


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


        return (
            hashlib.sha256(
                raw
            ).hexdigest(),
            counts,
            payload,
        )


    finally:
        con.close()


print("=" * 148)
print(
    "KIEM TOAN PAST THCS - SUA KIEM TRA BACKUP"
)
print(
    "CHI DOC - KHONG SUA DATABASE - KHONG SAP NHAP"
)
print("=" * 148)


# ============================================================
# 1. CURRENT DB GATE
# ============================================================

print()
print("1. CURRENT DATABASE")
print("-" * 148)


current_sha = sha256(
    DB
)


print(
    "DB SHA =",
    current_sha,
)


if current_sha != EXPECTED_CURRENT_DB_SHA:

    raise RuntimeError(
        "DUNG: database hien tai da thay doi "
        "ke tu lan hau kiem truoc."
    )


# ============================================================
# 2. LOCATE EXACT BACKUP FOLDER
# ============================================================

print()
print("2. TIM BACKUP FOLDER")
print("-" * 148)


roots = [
    ROOT / "exports",
    ROOT / "backups",
    ROOT / "data",
]


folders = []


for base in roots:

    if not base.exists():
        continue


    direct = (
        base
        / BACKUP_NAME
    )


    if (
        direct.exists()
        and direct.is_dir()
    ):

        folders.append(
            direct.resolve()
        )


    for path in base.rglob(
        BACKUP_NAME
    ):

        if path.is_dir():

            resolved = (
                path.resolve()
            )

            if resolved not in folders:

                folders.append(
                    resolved
                )


print(
    "folder count =",
    len(folders),
)


for folder in folders:

    print(
        " -",
        folder,
    )


if len(folders) != 1:

    raise RuntimeError(
        "DUNG: phai tim thay dung 1 folder backup."
    )


folder = folders[0]


# ============================================================
# 3. READ METADATA
# ============================================================

print()
print("3. BACKUP METADATA")
print("-" * 148)


meta_file = (
    folder
    / "thong_tin_sap_nhap_toan_cap.json"
)


if not meta_file.exists():

    raise RuntimeError(
        "DUNG: backup folder thieu "
        "thong_tin_sap_nhap_toan_cap.json"
    )


meta = json.loads(
    meta_file.read_text(
        encoding="utf-8-sig"
    )
)


print(
    json.dumps(
        meta,
        ensure_ascii=False,
        indent=2,
        default=str,
    )
)


status = str(
    meta.get(
        "status"
    )
    or ""
)


if status != (
    "CREATED_BEFORE_TRANSACTION_MUTATION"
):

    raise RuntimeError(
        "DUNG: metadata khong xac nhan "
        "backup truoc transaction."
    )


db_text = str(
    meta.get(
        "database_backup"
    )
    or ""
).strip()


backup_db = (
    Path(db_text)
    if db_text
    else folder / "phocap.db"
)


if not backup_db.exists():

    fallback = (
        folder
        / "phocap.db"
    )

    if fallback.exists():

        backup_db = fallback

    else:

        raise RuntimeError(
            "DUNG: khong tim thay file "
            "database backup."
        )


print()
print(
    "BACKUP DB =",
    backup_db,
)

print(
    "BACKUP PHYSICAL SHA =",
    sha256(
        backup_db
    ),
)


# ============================================================
# 4. BACKUP HEALTH
# ============================================================

print()
print("4. BACKUP DATABASE HEALTH")
print("-" * 148)


backup_integrity, backup_fk = (
    db_health(
        backup_db
    )
)


print(
    "integrity =",
    backup_integrity,
)

print(
    "FK        =",
    backup_fk,
)


if (
    backup_integrity.lower()
    != "ok"
    or backup_fk != 0
):

    raise RuntimeError(
        "DUNG: backup database health FAIL."
    )


# ============================================================
# 5. CURRENT HEALTH
# ============================================================

current_integrity, current_fk = (
    db_health(
        DB
    )
)


print()
print("5. CURRENT DATABASE HEALTH")
print("-" * 148)


print(
    "integrity =",
    current_integrity,
)

print(
    "FK        =",
    current_fk,
)


if (
    current_integrity.lower()
    != "ok"
    or current_fk != 0
):

    raise RuntimeError(
        "DUNG: current database health FAIL."
    )


# ============================================================
# 6. LOGICAL PAST COMPARISON
# ============================================================

print()
print("6. SO SANH LOGIC PAST")
print("-" * 148)


before_hash, before_counts, before_payload = (
    past_snapshot(
        backup_db
    )
)


after_hash, after_counts, after_payload = (
    past_snapshot(
        DB
    )
)


print(
    "PAST BACKUP HASH =",
    before_hash,
)

print(
    "PAST CURRENT HASH=",
    after_hash,
)

print(
    "PAST EXACT       =",
    before_hash
    == after_hash,
)


if (
    before_hash
    != after_hash
):

    changed_tables = []


    all_tables = sorted(
        set(
            before_payload
        )
        | set(
            after_payload
        )
    )


    for table in all_tables:

        old = before_payload.get(
            table
        )

        new = after_payload.get(
            table
        )


        if old != new:

            changed_tables.append({
                "table":
                    table,

                "backup_rows":
                    before_counts.get(
                        table,
                        0,
                    ),

                "current_rows":
                    after_counts.get(
                        table,
                        0,
                    ),
            })


    print()
    print(
        "PAST TABLE KHAC NHAU:"
    )

    print(
        json.dumps(
            changed_tables,
            ensure_ascii=False,
            indent=2,
        )
    )


    raise RuntimeError(
        "DUNG: PAST khong con giong "
        "backup truoc transaction."
    )


# ============================================================
# 7. CURRENT/FUTURE SOURCE STILL ZERO
# ============================================================

print()
print("7. KIEM TRA LAI 15 SOURCE")
print("-" * 148)


con = connect_ro(
    DB
)


try:

    active_sources = int(
        con.execute(
            (
                "SELECT COUNT(*) "
                "FROM schools "
                "WHERE id IN ("
                + marks(
                    len(
                        SOURCE_IDS
                    )
                )
                + ") "
                "AND is_active=1"
            ),
            SOURCE_IDS,
        ).fetchone()[0]
        or 0
    )


    residual = {}


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
                            SOURCE_IDS
                        )
                    )
                    + ")"
                    + " AND school_year_id IN (2,8)"
                ),
                SOURCE_IDS,
            ).fetchone()[0]
            or 0
        )


        if n:

            residual[
                table
            ] = n


finally:
    con.close()


print(
    "active source =",
    active_sources,
)

print(
    "CURRENT/FUTURE residual =",
    residual,
)


if active_sources != 0:

    raise RuntimeError(
        "DUNG: co source bi active tro lai."
    )


if residual:

    raise RuntimeError(
        "DUNG: CURRENT/FUTURE xuat hien lai "
        "tai source."
    )


# ============================================================
# 8. FILE IMMUTABILITY
# ============================================================

print()
print("8. FILE IMMUTABILITY")
print("-" * 148)


current_sha_after = (
    sha256(
        DB
    )
)


print(
    current_sha,
    "->",
    current_sha_after,
)


if (
    current_sha_after
    != current_sha
):

    raise RuntimeError(
        "DUNG: DB bi thay doi trong luc audit."
    )


print()
print("=" * 148)
print(
    "KIEM TOAN PAST THCS: PASS"
)
print("=" * 148)

print(
    "BACKUP METADATA        = PASS"
)

print(
    "BACKUP HEALTH          = OK"
)

print(
    "CURRENT HEALTH         = OK"
)

print(
    "PAST                   = GIU NGUYEN EXACT"
)

print(
    "15 SOURCE ACTIVE       = 0"
)

print(
    "CURRENT/FUTURE SOURCE  = 0"
)

print(
    "DATABASE               = KHONG THAY DOI"
)

print()
print(
    "THCS THUAN             = HOAN TAT"
)

print(
    "KHONG CHAY LAI BATCH THCS"
)

print("=" * 148)
