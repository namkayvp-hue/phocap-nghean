from __future__ import annotations

import hashlib
import inspect
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
    ROOT
    / "app"
    / "services"
    / "school_merger_level_batch_service.py"
)

RESOLUTION = (
    ROOT
    / "data"
    / "school_merger_registry"
    / "qd3805_mn_resolution.json"
)

ROSTER = (
    ROOT
    / "data"
    / "school_merger_source_rosters"
    / "MN_2025_2026.json"
)


def sha256(path):
    h = hashlib.sha256()

    with path.open("rb") as f:
        for block in iter(
            lambda: f.read(1024 * 1024),
            b"",
        ):
            h.update(block)

    return h.hexdigest()


print("=" * 120)
print("CHAN DOAN TRUOC KHI SUA LUONG MINH = GIU NGUYEN")
print("CHI DOC - KHONG SUA DB / SOURCE / JSON")
print("=" * 120)

print("DB SHA         =", sha256(DB))
print("Service SHA    =", sha256(SERVICE))
print("Resolution SHA =", sha256(RESOLUTION))
print("Roster SHA     =", sha256(ROSTER))


# ============================================================
# 1. XAC NHAN CHUA CO BATCH MN
# ============================================================

con = sqlite3.connect(str(DB))
con.row_factory = sqlite3.Row

try:
    print()
    print("=" * 120)
    print("1. KIEM TRA DATABASE CHUA BI GHI BATCH MN")
    print("=" * 120)

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

    print("integrity =", integrity)
    print("FK        =", fk)

    tables = {
        str(x["name"])
        for x in con.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type='table'
            """
        ).fetchall()
    }

    if "school_merger_level_batches" in tables:
        rows = con.execute(
            """
            SELECT *
            FROM school_merger_level_batches
            WHERE school_year_id=2
              AND UPPER(TRIM(level_code))='MN'
            """
        ).fetchall()

        print(
            "MN batch logs =",
            len(rows),
        )

        for row in rows:
            print(dict(row))
    else:
        print(
            "MN batch logs = 0 "
            "(bang chua ton tai)"
        )

    plan_ids = [
        "PA2026-43804C58D423",
        "PA2026-4AB75BCD93EB",
        "PA2026-785CDDA8D8CC",
        "PA2026-7802B1BD1912",
        "PA2026-1E90C6AAFD47",
    ]

    if (
        "school_merger_official_executions"
        in tables
    ):
        marks = ",".join(
            "?"
            for _ in plan_ids
        )

        rows = con.execute(
            f"""
            SELECT
                id,
                plan_id,
                operation_id,
                target_school_id,
                source_school_ids_json
            FROM school_merger_official_executions
            WHERE plan_id IN ({marks})
            ORDER BY id
            """,
            plan_ids,
        ).fetchall()

        print(
            "5 READY execution logs =",
            len(rows),
        )

        for row in rows:
            print(dict(row))
    else:
        print(
            "5 READY execution logs = 0"
        )

    lm = con.execute(
        """
        SELECT
            id,
            code,
            name,
            is_active,
            commune_id
        FROM schools
        WHERE code='40418311'
        LIMIT 1
        """
    ).fetchone()

    print()
    print("Mầm non Lượng Minh trong DB:")
    print(
        dict(lm)
        if lm is not None
        else None
    )

finally:
    con.close()


# ============================================================
# 2. RESOLUTION LUONG MINH
# ============================================================

payload = json.loads(
    RESOLUTION.read_text(
        encoding="utf-8-sig"
    )
)

print()
print("=" * 120)
print("2. LUONG MINH TRONG RESOLUTION HIEN TAI")
print("=" * 120)

for item in (
    payload.get("deferred_orphans")
    or []
):
    if int(
        item.get("stt")
        or 0
    ) == 1211:
        print(
            json.dumps(
                item,
                ensure_ascii=False,
                indent=2,
            )
        )


# ============================================================
# 3. EXECUTOR VA CAC HANG CONFIRM
# ============================================================

from app.services import (
    school_merger_level_batch_service
    as svc
)

fn = svc.execute_level_batch

print()
print("=" * 120)
print("3. EXECUTOR")
print("=" * 120)

print(
    "Signature =",
    inspect.signature(fn),
)


print()
print("=" * 120)
print("4. CAC HANG / BIEN LIEN QUAN CONFIRM")
print("=" * 120)

for name in sorted(dir(svc)):

    upper = name.upper()

    if (
        "CONFIRM" in upper
        or "SCOPE" in upper
    ):
        try:
            value = getattr(
                svc,
                name,
            )

            if isinstance(
                value,
                (
                    str,
                    int,
                    bool,
                    type(None),
                ),
            ):
                print(
                    name,
                    "=",
                    repr(value),
                )
        except Exception:
            pass


print()
print("=" * 120)
print("5. CAC DONG TRONG execute_level_batch CO confirmation")
print("=" * 120)

source = inspect.getsource(fn)

for n, line in enumerate(
    source.splitlines(),
    start=1,
):
    low = line.lower()

    if (
        "confirmation" in low
        or "confirm" in low
        or "scope" in low
    ):
        print(
            f"{n:03d}: {line}"
        )


print()
print("=" * 120)
print("KET LUAN")
print("=" * 120)

print(
    "SCRIPT NAY KHONG GHI DATABASE."
)

print(
    "LUONG MINH SE DUOC SUA TU "
    "DEFERRED -> GIU NGUYEN "
    "TRUOC KHI CHAY BATCH MN."
)

print("=" * 120)
