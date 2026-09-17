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
    ROOT
    / "app"
    / "services"
    / "school_merger_level_batch_service.py"
)

LOCK = (
    ROOT
    / "data"
    / "school_merger_registry"
    / "qd3805_level_lock.json"
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

APPROVED_PLAN = (
    ROOT
    / "data"
    / "school_merger_approved_plans.json"
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


TEST_OPS = [
    "QD3805-OP-0001",   # DONE cũ
    "QD3805-OP-0044",   # KEEP
    "QD3805-OP-0410",   # DONE vừa ghi
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


def short(value):
    if isinstance(value, dict):
        return {
            k: short(v)
            for k, v in value.items()
        }

    if isinstance(value, list):
        return [
            short(v)
            for v in value[:20]
        ]

    return value


def connect_ro():
    con = sqlite3.connect(
        DB.resolve().as_uri() + "?mode=ro",
        uri=True,
        timeout=60,
    )

    con.row_factory = sqlite3.Row
    con.execute("PRAGMA query_only=ON")

    return con


print("=" * 126)
print("CHAN DOAN CAU TRUC THAT CHO AUDIT MN V2")
print("CHI DOC - KHONG SUA DB / SOURCE / JSON")
print("=" * 126)


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


print()
print("=" * 126)
print("1. HASH GATE")
print("=" * 126)


before = {}

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
            + " khong dung nen sau batch MN."
        )


# ============================================================
# 2. STATE ROW THẬT
# ============================================================

from app.services import (
    school_merger_level_batch_service
    as svc
)


rows, counts, candidates, meta = (
    svc._state_rows(
        2,
        "MN",
    )
)


state_by_op = {}

for raw in rows:

    row = dict(raw)

    op = str(
        row.get(
            "qd3805_operation_id"
        )
        or ""
    )

    if op:
        state_by_op[op] = row


print()
print("=" * 126)
print("2. CAU TRUC _state_rows THAT")
print("=" * 126)

print(
    "counts =",
    counts,
)

print(
    "rows   =",
    len(rows),
)


for op in TEST_OPS:

    print()
    print("-" * 126)
    print("OP =", op)

    row = state_by_op.get(op)

    if row is None:
        print("KHONG TIM THAY")
        continue

    print(
        "KEYS =",
        sorted(row.keys()),
    )

    print(
        "FULL ROW ="
    )

    print(
        json.dumps(
            short(row),
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )


# ============================================================
# 3. APPROVED PLAN JSON
# ============================================================

print()
print("=" * 126)
print("3. SCHOOL_MERGER_APPROVED_PLANS.JSON")
print("=" * 126)


if not APPROVED_PLAN.exists():

    print(
        "FILE KHONG TON TAI:",
        APPROVED_PLAN,
    )

else:

    payload = json.loads(
        APPROVED_PLAN.read_text(
            encoding="utf-8-sig"
        )
    )

    plans = [
        dict(x)
        for x in (
            payload.get("plans")
            or []
        )
        if isinstance(x, dict)
    ]

    by_id = {
        str(
            x.get("id")
            or ""
        ):
            x
        for x in plans
    }


    print(
        "Tong plans =",
        len(plans),
    )

    for op in TEST_OPS:

        row = state_by_op.get(op) or {}

        pid = str(
            row.get("id")
            or ""
        )

        print()
        print("-" * 126)
        print(
            "OP      =",
            op,
        )

        print(
            "PLAN ID =",
            pid,
        )

        p = by_id.get(pid)

        if p is None:

            print(
                "KHONG TIM THAY TRONG APPROVED PLAN JSON"
            )

            continue


        print(
            "KEYS =",
            sorted(p.keys()),
        )

        print(
            "source_school_ids =",
            p.get(
                "source_school_ids"
            ),
        )

        print(
            "target_school_id  =",
            p.get(
                "target_school_id"
            ),
        )

        print(
            "action_type       =",
            p.get(
                "action_type"
            ),
        )

        print(
            "execution_status  =",
            p.get(
                "execution_status"
            ),
        )

        print(
            "PLAN ="
        )

        print(
            json.dumps(
                short(p),
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        )


# ============================================================
# 4. PREVIEW DETAIL THẬT
# ============================================================

from app.services.school_merger_preview_service import (
    build_official_plan_impact_preview,
)


print()
print("=" * 126)
print("4. BUILD_OFFICIAL_PLAN_IMPACT_PREVIEW")
print("=" * 126)


for op in TEST_OPS:

    row = state_by_op.get(op) or {}

    pid = str(
        row.get("id")
        or ""
    )

    print()
    print("-" * 126)

    print(
        op,
        "|",
        pid,
    )

    if not pid:
        continue

    try:

        detail = (
            build_official_plan_impact_preview(
                pid
            )
        )

        print(
            "DETAIL KEYS =",
            sorted(
                detail.keys()
            ),
        )

        print(
            "source_schools ="
        )

        print(
            json.dumps(
                detail.get(
                    "source_schools"
                ),
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        )

        print(
            "target_school ="
        )

        print(
            json.dumps(
                detail.get(
                    "target_school"
                ),
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        )

        print(
            "keep_only =",
            detail.get(
                "keep_only"
            ),
        )

        print(
            "simulation_ok =",
            detail.get(
                "simulation_ok"
            ),
        )

    except Exception as exc:

        print(
            "PREVIEW ERROR =",
            type(exc).__name__,
            ":",
            str(exc),
        )


# ============================================================
# 5. DB LOG SCHEMA
# ============================================================

print()
print("=" * 126)
print("5. DB LOG SCHEMA")
print("=" * 126)


con = connect_ro()

try:

    for table in (
        "school_merger_operations",
        "school_merger_official_executions",
        "school_merger_level_batches",
    ):

        print()
        print("-" * 126)
        print(
            "TABLE =",
            table,
        )

        exists = (
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

        print(
            "exists =",
            exists,
        )

        if not exists:
            continue

        cols = [
            dict(x)
            for x in con.execute(
                f'PRAGMA table_info("{table}")'
            ).fetchall()
        ]

        print(
            "columns ="
        )

        print(
            json.dumps(
                cols,
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        )


    # 5 plan vừa ghi phải có official execution.
    print()
    print("-" * 126)
    print("OFFICIAL EXECUTION - OP0410")

    row0410 = (
        state_by_op.get(
            "QD3805-OP-0410"
        )
        or {}
    )

    pid0410 = str(
        row0410.get("id")
        or ""
    )

    if pid0410:

        rows0410 = con.execute(
            """
            SELECT *
            FROM school_merger_official_executions
            WHERE plan_id=?
            """,
            (pid0410,),
        ).fetchall()

        print(
            json.dumps(
                [
                    dict(x)
                    for x in rows0410
                ],
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        )


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
    print(
        "integrity =",
        integrity,
    )

    print(
        "FK        =",
        fk,
    )


finally:
    con.close()


# ============================================================
# 6. IMMUTABILITY
# ============================================================

print()
print("=" * 126)
print("6. KIEM TRA KHONG THAY DOI")
print("=" * 126)


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
print("=" * 126)
print("CHAN DOAN HOAN TAT")
print("=" * 126)

print(
    "SCRIPT CHI DOC: PASS"
)

print(
    "DB / SERVICE / REGISTRY / ROSTER: KHONG THAY DOI"
)

print(
    "BUOC TIEP THEO: SUA AUDIT V2 THEO DUNG FIELD THAT."
)

print("=" * 126)
