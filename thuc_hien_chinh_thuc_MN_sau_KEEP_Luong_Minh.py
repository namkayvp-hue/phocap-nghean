from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import sys
import traceback
from datetime import datetime
from pathlib import Path


try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


ROOT = Path(r"C:\PhoCap").resolve()

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


YEAR_ID = 2
LEVEL = "MN"

EXPECTED_DB_SHA = (
    "44b1aa841cdd76301c57d9fc601121ae"
    "96f9312084ef05959eaae54acf17c8c9"
)

EXPECTED_SERVICE_SHA = (
    "963b8d6a280d8abef8e96486abd87d77"
    "cea289b08d2edb497647f250ed1b2af8"
)

EXPECTED_LOCK_SHA = (
    "ad310048a4c5b239404e0902cc04fda1"
    "d73474d11a739a2ca009d2727e4390c3"
)

EXPECTED_RESOLUTION_SHA = (
    "22ca7931ec40408ced25a3bde14a9672c"
    "04e12a760a077a44bb9d65b709b1163"
)

EXPECTED_ROSTER_SHA = (
    "ef865f74aa51c2700ceb7746d5433b63"
    "fc6a52a4e3169014ebe0e446ac441120"
)

EXPECTED_BATCH_FP = (
    "3ff70145c42c255075bb1430ea4bc4fde"
    "8da38521f7cb344b51349a75875cd60"
)


PLANS = {
    "QD3805-OP-0410": {
        "plan_id": "PA2026-43804C58D423",
        "source": 206,
        "target": 205,
        "staff_after": 66,
        "structure": {
            "CBQL": 6,
            "GIAO_VIEN": 58,
            "NHAN_VIEN": 2,
        },
    },

    "QD3805-OP-0449": {
        "plan_id": "PA2026-4AB75BCD93EB",
        "source": 325,
        "target": 326,
        "staff_after": 67,
        "structure": {
            "CBQL": 6,
            "GIAO_VIEN": 46,
            "NHAN_VIEN": 15,
        },
    },

    "QD3805-OP-0175": {
        "plan_id": "PA2026-785CDDA8D8CC",
        "source": 654,
        "target": 653,
        "staff_after": 61,
        "structure": {
            "CBQL": 5,
            "GIAO_VIEN": 40,
            "NHAN_VIEN": 16,
        },
    },

    "QD3805-OP-0592": {
        "plan_id": "PA2026-7802B1BD1912",
        "source": 713,
        "target": 712,
        "staff_after": 71,
        "structure": {
            "CBQL": 3,
            "GIAO_VIEN": 47,
            "NHAN_VIEN": 21,
        },
    },

    "QD3805-OP-0600": {
        "plan_id": "PA2026-1E90C6AAFD47",
        "source": 736,
        "target": 735,
        "staff_after": 45,
        "structure": {
            "CBQL": 5,
            "GIAO_VIEN": 27,
            "NHAN_VIEN": 13,
        },
    },
}


SOURCE_IDS = sorted({
    x["source"]
    for x in PLANS.values()
})

TARGET_IDS = sorted({
    x["target"]
    for x in PLANS.values()
})

PLAN_IDS = {
    x["plan_id"]
    for x in PLANS.values()
}

# OP-0337 / OP-0338 + Lượng Minh
# tuyệt đối không được tác động.
PROTECTED_IDS = [
    256,    # Mầm non Lượng Minh
    747,
    748,
    749,
    750,
    751,
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
    return (
        '"'
        + str(name).replace('"', '""')
        + '"'
    )


def connect_ro() -> sqlite3.Connection:
    con = sqlite3.connect(
        DB.resolve().as_uri() + "?mode=ro",
        uri=True,
        timeout=30,
    )

    con.row_factory = sqlite3.Row
    con.execute("PRAGMA query_only=ON")

    return con


def health(path: Path) -> tuple[str, int]:
    con = sqlite3.connect(
        str(path),
        timeout=30,
    )

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

        return integrity, fk

    finally:
        con.close()


def table_columns(
    con: sqlite3.Connection,
    table: str,
) -> list[str]:

    return [
        str(x["name"])
        for x in con.execute(
            f"PRAGMA table_info({qident(table)})"
        ).fetchall()
    ]


def all_tables(
    con: sqlite3.Connection,
) -> list[str]:

    return [
        str(x["name"])
        for x in con.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type='table'
              AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """
        ).fetchall()
    ]


def serialize(rows) -> tuple[int, str]:
    values = []

    for row in rows:
        values.append(
            json.dumps(
                {
                    key: row[key]
                    for key in row.keys()
                },
                ensure_ascii=False,
                sort_keys=True,
                default=str,
            )
        )

    values.sort()

    h = hashlib.sha256()

    for value in values:
        h.update(
            value.encode("utf-8")
        )
        h.update(b"\n")

    return len(values), h.hexdigest()


def protected_snapshot(
    con: sqlite3.Connection,
) -> dict:

    result = {}

    marks = ",".join(
        "?"
        for _ in PROTECTED_IDS
    )

    rows = con.execute(
        f"""
        SELECT *
        FROM schools
        WHERE id IN ({marks})
        """,
        PROTECTED_IDS,
    ).fetchall()

    result["schools"] = serialize(rows)

    for table in all_tables(con):

        if table == "schools":
            continue

        cols = set(
            table_columns(
                con,
                table,
            )
        )

        if "school_id" not in cols:
            continue

        rows = con.execute(
            f"""
            SELECT *
            FROM {qident(table)}
            WHERE school_id IN ({marks})
            """,
            PROTECTED_IDS,
        ).fetchall()

        result[table] = serialize(
            rows
        )

    return result


def past_snapshot(
    con: sqlite3.Connection,
) -> dict:

    result = {}

    sm = ",".join(
        "?"
        for _ in SOURCE_IDS
    )

    past_ids = [
        1, 3, 4, 5, 6, 7
    ]

    ym = ",".join(
        "?"
        for _ in past_ids
    )

    for table in all_tables(con):

        cols = set(
            table_columns(
                con,
                table,
            )
        )

        if not {
            "school_id",
            "school_year_id",
        }.issubset(cols):
            continue

        rows = con.execute(
            f"""
            SELECT *
            FROM {qident(table)}
            WHERE school_id IN ({sm})
              AND school_year_id IN ({ym})
            """,
            [
                *SOURCE_IDS,
                *past_ids,
            ],
        ).fetchall()

        result[table] = serialize(
            rows
        )

    return result


def current_future_residual(
    con: sqlite3.Connection,
) -> dict:

    result = {}

    sm = ",".join(
        "?"
        for _ in SOURCE_IDS
    )

    for table in all_tables(con):

        cols = set(
            table_columns(
                con,
                table,
            )
        )

        if not {
            "school_id",
            "school_year_id",
        }.issubset(cols):
            continue

        n = int(
            con.execute(
                f"""
                SELECT COUNT(*)
                FROM {qident(table)}
                WHERE school_id IN ({sm})
                  AND school_year_id IN (2,8)
                """,
                SOURCE_IDS,
            ).fetchone()[0]
            or 0
        )

        if n:
            result[table] = n

    return result


def staff_count(
    con: sqlite3.Connection,
    school_id: int,
) -> int:

    return int(
        con.execute(
            """
            SELECT COUNT(*)
            FROM staff_year_records
            WHERE school_id=?
              AND school_year_id=2
              AND is_active=1
            """,
            (school_id,),
        ).fetchone()[0]
        or 0
    )


def staff_structure(
    con: sqlite3.Connection,
    school_id: int,
) -> dict:

    rows = con.execute(
        """
        SELECT
            COALESCE(position_group,'') AS g,
            COUNT(*) AS n
        FROM staff_year_records
        WHERE school_id=?
          AND school_year_id=2
          AND is_active=1
        GROUP BY
            COALESCE(position_group,'')
        ORDER BY g
        """,
        (school_id,),
    ).fetchall()

    return {
        str(x["g"]):
            int(x["n"])
        for x in rows
    }


def duplicate_staff(
    con: sqlite3.Connection,
    school_id: int,
) -> int:

    return int(
        con.execute(
            """
            SELECT COUNT(*)
            FROM (
                SELECT staff_member_id
                FROM staff_year_records
                WHERE school_id=?
                  AND school_year_id=2
                  AND is_active=1
                GROUP BY staff_member_id
                HAVING COUNT(*) > 1
            )
            """,
            (school_id,),
        ).fetchone()[0]
        or 0
    )


def restore_external_backup(
    backup_db: Path,
    backup_service: Path,
    backup_lock: Path,
    backup_resolution: Path,
    backup_roster: Path,
) -> None:

    print()
    print("=" * 126)
    print("KHOI PHUC BACKUP NGOAI")
    print("=" * 126)

    for suffix in (
        "-wal",
        "-shm",
        "-journal",
    ):
        p = Path(
            str(DB) + suffix
        )

        if p.exists():
            try:
                p.unlink()
            except Exception:
                pass

    shutil.copy2(
        backup_db,
        DB,
    )

    shutil.copy2(
        backup_service,
        SERVICE,
    )

    shutil.copy2(
        backup_lock,
        LOCK,
    )

    shutil.copy2(
        backup_resolution,
        RESOLUTION,
    )

    shutil.copy2(
        backup_roster,
        ROSTER,
    )

    integrity, fk = health(DB)

    print(
        "DB SHA restored =",
        sha256(DB),
    )

    print(
        "integrity       =",
        integrity,
    )

    print(
        "FK              =",
        fk,
    )

    if (
        sha256(DB)
        != EXPECTED_DB_SHA
        or integrity.lower()
        != "ok"
        or fk != 0
    ):
        raise RuntimeError(
            "KHOI PHUC BACKUP CHUA DAT."
        )

    print(
        "KHOI PHUC THANH CONG."
    )


print("=" * 126)
print(
    "THUC HIEN CHINH THUC TOAN CAP MAM NON"
)
print("=" * 126)

print(
    "KEEP             : 52"
)

print(
    "DONE TRUOC       : 184"
)

print(
    "THUC HIEN MOI    : 5"
)

print(
    "LUONG MINH       : GIU NGUYEN"
)

print(
    "CONFIRM SCOPE    : yes"
)

print(
    "CONFIRM TEXT     : SAP NHAP TOAN CAP"
)

print(
    "BATCH FINGERPRINT:",
    EXPECTED_BATCH_FP,
)

print("=" * 126)


# ============================================================
# 1. KHÔNG CHẠY KHI DB-WAL ĐANG CÓ DỮ LIỆU
# ============================================================

for suffix in (
    "-wal",
    "-journal",
):
    p = Path(
        str(DB) + suffix
    )

    if (
        p.exists()
        and p.stat().st_size > 0
    ):
        raise RuntimeError(
            "DUNG AN TOAN: "
            + p.name
            + " dang co du lieu. "
            "Hay dung Uvicorn/server hoan toan "
            "roi chay lai."
        )


# ============================================================
# 2. HASH GATE
# ============================================================

actual_hash = {
    "db":
        sha256(DB),

    "service":
        sha256(SERVICE),

    "lock":
        sha256(LOCK),

    "resolution":
        sha256(RESOLUTION),

    "roster":
        sha256(ROSTER),
}

expected_hash = {
    "db":
        EXPECTED_DB_SHA,

    "service":
        EXPECTED_SERVICE_SHA,

    "lock":
        EXPECTED_LOCK_SHA,

    "resolution":
        EXPECTED_RESOLUTION_SHA,

    "roster":
        EXPECTED_ROSTER_SHA,
}


print()
print("=" * 126)
print("1. HASH GATE")
print("=" * 126)

for key in actual_hash:

    print(
        f"{key:12s} = {actual_hash[key]}"
    )

    if (
        actual_hash[key]
        != expected_hash[key]
    ):
        raise RuntimeError(
            "DUNG: "
            + key
            + " khong dung nen da khoa."
        )


# ============================================================
# 3. IMPORT ENGINE + PREFLIGHT
# ============================================================

from app.services import (
    school_merger_level_batch_service
    as svc
)

from app.services.school_merger_preview_service import (
    build_official_plan_impact_preview,
)


pre = svc.build_level_batch_preview(
    school_year_id=YEAR_ID,
    level_code=LEVEL,
)


print()
print("=" * 126)
print("2. PREFLIGHT CUOI")
print("=" * 126)

print(
    "counts                =",
    pre.get("counts"),
)

print(
    "candidate_count       =",
    pre.get(
        "candidate_count"
    ),
)

print(
    "effective_block_count =",
    pre.get(
        "effective_block_count"
    ),
)

print(
    "ready_for_execution   =",
    pre.get(
        "ready_for_execution"
    ),
)

print(
    "previous_batch        =",
    pre.get(
        "previous_batch"
    ),
)

print(
    "extra_blockers        =",
    pre.get(
        "extra_blockers"
    ),
)

print(
    "overlap_items         =",
    pre.get(
        "overlap_items"
    ),
)

print(
    "batch_fingerprint     =",
    pre.get(
        "batch_fingerprint"
    ),
)


if pre.get("counts") != {
    "KEEP": 52,
    "DONE": 184,
    "READY": 5,
    "BLOCK": 0,
}:
    raise RuntimeError(
        "DUNG: KPI preflight sai."
    )


if (
    pre.get(
        "candidate_count"
    )
    != 5
    or pre.get(
        "effective_block_count"
    )
    != 0
    or pre.get(
        "ready_for_execution"
    )
    is not True
):
    raise RuntimeError(
        "DUNG: batch khong con san sang."
    )


if pre.get(
    "previous_batch"
) is not None:
    raise RuntimeError(
        "DUNG: MN da co batch log. "
        "KHONG CHAY LAN HAI."
    )


if (
    pre.get(
        "extra_blockers"
    )
    or []
):
    raise RuntimeError(
        "DUNG: con blocker."
    )


if (
    pre.get(
        "overlap_items"
    )
    or []
):
    raise RuntimeError(
        "DUNG: co overlap."
    )


if (
    str(
        pre.get(
            "batch_fingerprint"
        )
        or ""
    )
    != EXPECTED_BATCH_FP
):
    raise RuntimeError(
        "DUNG: fingerprint da thay doi."
    )


# ============================================================
# 4. EXACT 5 OPERATION
# ============================================================

candidates = [
    dict(x)
    for x in (
        pre.get("candidates")
        or []
    )
    if isinstance(x, dict)
]


candidate_ops = {
    str(
        x.get(
            "qd3805_operation_id"
        )
        or ""
    )
    for x in candidates
}


if candidate_ops != set(PLANS):
    raise RuntimeError(
        "DUNG: danh sach 5 READY "
        "khong con dung."
    )


print()
print("=" * 126)
print("3. EXACT 5 SOURCE -> TARGET")
print("=" * 126)


for candidate in candidates:

    op = str(
        candidate.get(
            "qd3805_operation_id"
        )
        or ""
    )

    rule = PLANS[op]

    if (
        str(
            candidate.get("plan_id")
            or ""
        )
        != rule["plan_id"]
    ):
        raise RuntimeError(
            f"{op}: sai plan_id."
        )

    detail = (
        build_official_plan_impact_preview(
            rule["plan_id"]
        )
    )

    sources = sorted(
        int(x["id"])
        for x in (
            detail.get(
                "source_schools"
            )
            or []
        )
    )

    target = int(
        (
            detail.get(
                "target_school"
            )
            or {}
        ).get("id")
        or 0
    )


    if sources != [
        rule["source"]
    ]:
        raise RuntimeError(
            f"{op}: sai source."
        )


    if target != rule["target"]:
        raise RuntimeError(
            f"{op}: sai target."
        )


    if (
        not detail.get(
            "simulation_ok"
        )
        or not detail.get(
            "safe_for_future_execution"
        )
        or (
            detail.get("blockers")
            or []
        )
    ):
        raise RuntimeError(
            f"{op}: preview khong con PASS."
        )


    print(
        op,
        "| source=",
        rule["source"],
        "-> target=",
        rule["target"],
    )


# ============================================================
# 5. DB TRƯỚC GHI
# ============================================================

con = connect_ro()

try:

    integrity_before = str(
        con.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]
    )

    fk_before = len(
        con.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()
    )


    if (
        integrity_before.lower()
        != "ok"
        or fk_before != 0
    ):
        raise RuntimeError(
            "DUNG: DB truoc ghi "
            "khong dat integrity/FK."
        )


    old_batch_count = int(
        con.execute(
            """
            SELECT COUNT(*)
            FROM school_merger_level_batches
            WHERE school_year_id=2
              AND UPPER(TRIM(level_code))='MN'
            """
        ).fetchone()[0]
        or 0
    )


    marks = ",".join(
        "?"
        for _ in PLAN_IDS
    )


    old_exec_count = int(
        con.execute(
            f"""
            SELECT COUNT(*)
            FROM school_merger_official_executions
            WHERE school_year_id=2
              AND plan_id IN ({marks})
            """,
            sorted(PLAN_IDS),
        ).fetchone()[0]
        or 0
    )


    if old_batch_count != 0:
        raise RuntimeError(
            "DUNG: MN batch log != 0."
        )


    if old_exec_count != 0:
        raise RuntimeError(
            "DUNG: 5 plan da co execution."
        )


    lm = con.execute(
        """
        SELECT
            id,
            code,
            name,
            is_active
        FROM schools
        WHERE id=256
        """
    ).fetchone()


    if (
        lm is None
        or str(lm["code"])
        != "40418311"
        or not bool(
            lm["is_active"]
        )
    ):
        raise RuntimeError(
            "DUNG: Mầm non Lượng Minh "
            "khong dung trang thai GIU NGUYEN."
        )


    protected_before = (
        protected_snapshot(con)
    )

    past_before = (
        past_snapshot(con)
    )


finally:
    con.close()


print()
print("=" * 126)
print("4. DB TRUOC GHI")
print("=" * 126)

print(
    "integrity =",
    integrity_before,
)

print(
    "FK        =",
    fk_before,
)

print(
    "MN batch logs       =",
    old_batch_count,
)

print(
    "5 execution logs    =",
    old_exec_count,
)

print(
    "Mầm non Lượng Minh  = ACTIVE / GIU NGUYEN"
)


# ============================================================
# 6. ACTOR
# ============================================================

con = connect_ro()

try:

    actor_row = con.execute(
        """
        SELECT *
        FROM users
        WHERE username='admin.sogddt'
        """
    ).fetchall()


    if len(actor_row) != 1:
        raise RuntimeError(
            "DUNG: phai co dung "
            "1 admin.sogddt."
        )


    actor_row = dict(
        actor_row[0]
    )


    if not bool(
        actor_row.get(
            "is_active"
        )
    ):
        raise RuntimeError(
            "DUNG: admin.sogddt inactive."
        )


    actor = {
        "id":
            int(
                actor_row["id"]
            ),

        "username":
            str(
                actor_row[
                    "username"
                ]
            ),

        "full_name":
            str(
                actor_row.get(
                    "full_name"
                )
                or ""
            ),
    }


finally:
    con.close()


print(
    "Actor =",
    actor,
)


# ============================================================
# 7. BACKUP NGOÀI
# ============================================================

stamp = datetime.now().strftime(
    "%Y%m%d_%H%M%S"
)

backup_dir = (
    ROOT
    / "backups"
    / (
        "backup_ngoai_truoc_MN_chinh_thuc_"
        + stamp
    )
)

backup_dir.mkdir(
    parents=True,
    exist_ok=False,
)


backup_db = (
    backup_dir
    / "phocap.db"
)

backup_service = (
    backup_dir
    / SERVICE.name
)

backup_lock = (
    backup_dir
    / LOCK.name
)

backup_resolution = (
    backup_dir
    / RESOLUTION.name
)

backup_roster = (
    backup_dir
    / ROSTER.name
)


shutil.copy2(
    DB,
    backup_db,
)

shutil.copy2(
    SERVICE,
    backup_service,
)

shutil.copy2(
    LOCK,
    backup_lock,
)

shutil.copy2(
    RESOLUTION,
    backup_resolution,
)

shutil.copy2(
    ROSTER,
    backup_roster,
)


if (
    sha256(backup_db)
    != EXPECTED_DB_SHA
):
    raise RuntimeError(
        "DUNG: backup DB khong "
        "byte-identical."
    )


bi, bfk = health(
    backup_db
)

if (
    bi.lower() != "ok"
    or bfk != 0
):
    raise RuntimeError(
        "DUNG: backup DB khong dat."
    )


print()
print("=" * 126)
print("5. BACKUP NGOAI")
print("=" * 126)

print(
    "Backup =",
    backup_dir,
)

print(
    "integrity =",
    bi,
)

print(
    "FK        =",
    bfk,
)


# ============================================================
# 8. NGAY TRƯỚC EXECUTOR
# ============================================================

last_pre = (
    svc.build_level_batch_preview(
        school_year_id=2,
        level_code="MN",
    )
)


if (
    str(
        last_pre.get(
            "batch_fingerprint"
        )
        or ""
    )
    != EXPECTED_BATCH_FP
    or last_pre.get(
        "counts"
    )
    != {
        "KEEP": 52,
        "DONE": 184,
        "READY": 5,
        "BLOCK": 0,
    }
    or last_pre.get(
        "previous_batch"
    )
    is not None
):
    raise RuntimeError(
        "DUNG: trang thai thay doi "
        "ngay truoc write."
    )


# ============================================================
# 9. GHI THẬT
# ============================================================

executor_called = False


try:

    print()
    print("=" * 126)
    print(
        "6. BAT DAU EXECUTOR - GHI THAT"
    )
    print("=" * 126)

    executor_called = True


    result = svc.execute_level_batch(
        school_year_id=2,
        level_code="MN",
        actor=actor,
        expected_batch_fingerprint=(
            EXPECTED_BATCH_FP
        ),
        confirmation_scope="yes",
        confirmation_text=(
            "SAP NHAP TOAN CAP"
        ),
    )


    print()
    print(
        "EXECUTOR RETURN:"
    )

    print(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )


    # ========================================================
    # 10. FILE CẤU HÌNH TUYỆT ĐỐI KHÔNG ĐƯỢC ĐỔI
    # ========================================================

    if sha256(SERVICE) != EXPECTED_SERVICE_SHA:
        raise RuntimeError(
            "Service bi thay doi."
        )

    if sha256(LOCK) != EXPECTED_LOCK_SHA:
        raise RuntimeError(
            "Level lock bi thay doi."
        )

    if (
        sha256(RESOLUTION)
        != EXPECTED_RESOLUTION_SHA
    ):
        raise RuntimeError(
            "Resolution bi thay doi."
        )

    if sha256(ROSTER) != EXPECTED_ROSTER_SHA:
        raise RuntimeError(
            "Roster bi thay doi."
        )


    # ========================================================
    # 11. PREVIEW SAU GHI
    # ========================================================

    post = (
        svc.build_level_batch_preview(
            school_year_id=2,
            level_code="MN",
        )
    )


    print()
    print("=" * 126)
    print("7. PREVIEW SAU GHI THAT")
    print("=" * 126)

    print(
        "counts                =",
        post.get("counts"),
    )

    print(
        "candidate_count       =",
        post.get(
            "candidate_count"
        ),
    )

    print(
        "effective_block_count =",
        post.get(
            "effective_block_count"
        ),
    )

    print(
        "all_done              =",
        post.get("all_done"),
    )

    print(
        "previous_batch exists =",
        post.get(
            "previous_batch"
        )
        is not None,
    )


    if post.get("counts") != {
        "KEEP": 52,
        "DONE": 189,
        "READY": 0,
        "BLOCK": 0,
    }:
        raise RuntimeError(
            "HAU KIEM FAIL: "
            "KPI khong dung 52/189/0/0."
        )


    if (
        post.get(
            "candidate_count"
        )
        != 0
    ):
        raise RuntimeError(
            "HAU KIEM FAIL: "
            "candidate_count != 0."
        )


    if (
        post.get(
            "effective_block_count"
        )
        != 0
    ):
        raise RuntimeError(
            "HAU KIEM FAIL: "
            "effective_block_count != 0."
        )


    if (
        post.get(
            "previous_batch"
        )
        is None
    ):
        raise RuntimeError(
            "HAU KIEM FAIL: "
            "thieu batch log."
        )


    # ========================================================
    # 12. HẬU KIỂM DB
    # ========================================================

    con = connect_ro()

    try:

        integrity_after = str(
            con.execute(
                "PRAGMA integrity_check"
            ).fetchone()[0]
        )

        fk_after = len(
            con.execute(
                "PRAGMA foreign_key_check"
            ).fetchall()
        )


        if (
            integrity_after.lower()
            != "ok"
            or fk_after != 0
        ):
            raise RuntimeError(
                "HAU KIEM FAIL: "
                "integrity/FK."
            )


        # Đúng 1 batch MN.
        batch_rows = con.execute(
            """
            SELECT *
            FROM school_merger_level_batches
            WHERE school_year_id=2
              AND UPPER(TRIM(level_code))='MN'
            ORDER BY id
            """
        ).fetchall()


        if len(batch_rows) != 1:
            raise RuntimeError(
                "HAU KIEM FAIL: "
                "phai co dung 1 batch MN."
            )


        batch = dict(
            batch_rows[0]
        )


        if (
            int(
                batch.get(
                    "keep_count"
                )
                or 0
            )
            != 52
            or int(
                batch.get(
                    "done_before_count"
                )
                or 0
            )
            != 184
            or int(
                batch.get(
                    "executed_count"
                )
                or 0
            )
            != 5
            or str(
                batch.get(
                    "batch_fingerprint"
                )
                or ""
            )
            != EXPECTED_BATCH_FP
        ):
            raise RuntimeError(
                "HAU KIEM FAIL: "
                "batch log sai."
            )


        # Đúng 5 execution.
        marks = ",".join(
            "?"
            for _ in PLAN_IDS
        )

        execution_rows = con.execute(
            f"""
            SELECT *
            FROM school_merger_official_executions
            WHERE school_year_id=2
              AND plan_id IN ({marks})
            ORDER BY plan_id
            """,
            sorted(PLAN_IDS),
        ).fetchall()


        if len(execution_rows) != 5:
            raise RuntimeError(
                "HAU KIEM FAIL: "
                "execution logs != 5."
            )


        actual_plan_ids = {
            str(x["plan_id"])
            for x in execution_rows
        }


        if actual_plan_ids != PLAN_IDS:
            raise RuntimeError(
                "HAU KIEM FAIL: "
                "sai plan IDs."
            )


        # Kiểm đúng source -> target từng plan.
        by_plan = {
            str(x["plan_id"]):
                dict(x)
            for x in execution_rows
        }


        for op, rule in PLANS.items():

            row = by_plan[
                rule["plan_id"]
            ]

            source_json = json.loads(
                str(
                    row[
                        "source_school_ids_json"
                    ]
                )
            )

            if (
                sorted(
                    int(x)
                    for x in source_json
                )
                != [rule["source"]]
                or int(
                    row[
                        "target_school_id"
                    ]
                )
                != rule["target"]
            ):
                raise RuntimeError(
                    "HAU KIEM FAIL: "
                    + op
                    + " source/target sai."
                )


        # Sources phải inactive.
        sm = ",".join(
            "?"
            for _ in SOURCE_IDS
        )

        source_rows = con.execute(
            f"""
            SELECT id,is_active
            FROM schools
            WHERE id IN ({sm})
            ORDER BY id
            """,
            SOURCE_IDS,
        ).fetchall()


        if (
            len(source_rows)
            != 5
            or any(
                bool(x["is_active"])
                for x in source_rows
            )
        ):
            raise RuntimeError(
                "HAU KIEM FAIL: "
                "con source active."
            )


        # Targets phải active.
        tm = ",".join(
            "?"
            for _ in TARGET_IDS
        )

        target_rows = con.execute(
            f"""
            SELECT id,is_active
            FROM schools
            WHERE id IN ({tm})
            ORDER BY id
            """,
            TARGET_IDS,
        ).fetchall()


        if (
            len(target_rows)
            != 5
            or any(
                not bool(
                    x["is_active"]
                )
                for x in target_rows
            )
        ):
            raise RuntimeError(
                "HAU KIEM FAIL: "
                "target inactive."
            )


        # Không còn active user tại nguồn.
        active_users_source = int(
            con.execute(
                f"""
                SELECT COUNT(*)
                FROM users
                WHERE school_id IN ({sm})
                  AND is_active=1
                """,
                SOURCE_IDS,
            ).fetchone()[0]
            or 0
        )


        if active_users_source != 0:
            raise RuntimeError(
                "HAU KIEM FAIL: "
                "active users source != 0."
            )


        # CURRENT/FUTURE residual = 0.
        residual = (
            current_future_residual(
                con
            )
        )


        if residual:
            raise RuntimeError(
                "HAU KIEM FAIL: "
                "con residual "
                + repr(residual)
            )


        # PAST 100% không đổi.
        past_after = (
            past_snapshot(con)
        )


        if past_after != past_before:
            raise RuntimeError(
                "HAU KIEM FAIL: "
                "PAST bi thay doi."
            )


        # OP0337 / OP0338 / Lượng Minh
        # tuyệt đối không đổi.
        protected_after = (
            protected_snapshot(con)
        )


        if (
            protected_after
            != protected_before
        ):
            raise RuntimeError(
                "HAU KIEM FAIL: "
                "Luong Minh hoac OP0337/0338 "
                "bi tac dong."
            )


        # Nhân sự tại 5 target.
        staff_results = {}


        for op, rule in PLANS.items():

            total = staff_count(
                con,
                rule["target"],
            )

            structure = (
                staff_structure(
                    con,
                    rule["target"],
                )
            )

            dup = duplicate_staff(
                con,
                rule["target"],
            )


            staff_results[op] = {
                "total":
                    total,

                "structure":
                    structure,

                "duplicate":
                    dup,
            }


            if (
                total
                != rule["staff_after"]
            ):
                raise RuntimeError(
                    "HAU KIEM FAIL: "
                    + op
                    + " staff total="
                    + str(total)
                )


            if structure != rule[
                "structure"
            ]:
                raise RuntimeError(
                    "HAU KIEM FAIL: "
                    + op
                    + " co cau staff sai: "
                    + repr(structure)
                )


            if dup != 0:
                raise RuntimeError(
                    "HAU KIEM FAIL: "
                    + op
                    + " duplicate staff."
                )


        # Lượng Minh vẫn active.
        lm_after = con.execute(
            """
            SELECT
                id,
                code,
                name,
                is_active
            FROM schools
            WHERE id=256
            """
        ).fetchone()


        if (
            lm_after is None
            or str(
                lm_after["code"]
            )
            != "40418311"
            or not bool(
                lm_after["is_active"]
            )
        ):
            raise RuntimeError(
                "HAU KIEM FAIL: "
                "Luong Minh khong con "
                "GIU NGUYEN."
            )


    finally:
        con.close()


    # ========================================================
    # 13. BÁO CÁO THÀNH CÔNG
    # ========================================================

    report_dir = (
        ROOT
        / "exports"
        / "Thuc_hien_chinh_thuc_MN"
    )

    report_dir.mkdir(
        parents=True,
        exist_ok=True,
    )


    report_path = (
        report_dir
        / (
            "ket_qua_MN_chinh_thuc_"
            + stamp
            + ".json"
        )
    )


    report = {
        "status":
            "SUCCESS_COMMITTED",

        "school_year_id":
            2,

        "level_code":
            "MN",

        "counts_after":
            post.get("counts"),

        "batch_fingerprint":
            EXPECTED_BATCH_FP,

        "batch_row":
            batch,

        "official_plan_ids":
            sorted(
                actual_plan_ids
            ),

        "staff":
            staff_results,

        "residual":
            residual,

        "past_exact":
            past_after
            == past_before,

        "protected_exact":
            protected_after
            == protected_before,

        "active_users_source":
            active_users_source,

        "integrity":
            integrity_after,

        "foreign_key_errors":
            fk_after,

        "database_sha_before":
            EXPECTED_DB_SHA,

        "database_sha_after":
            sha256(DB),

        "external_backup":
            str(backup_dir),

        "executor_result":
            result,
    }


    report_path.write_text(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )


    print()
    print("=" * 126)
    print("8. NHAN SU SAU SAP NHAP")
    print("=" * 126)


    for op in PLANS:

        print(
            op,
            "=",
            staff_results[op],
        )


    print()
    print("=" * 126)
    print(
        "THUC HIEN CHINH THUC CAP MAM NON: THANH CONG"
    )
    print("=" * 126)

    print(
        "KEEP / DONE / READY / BLOCK =",
        post.get("counts"),
    )

    print(
        "5 READY               : DONE"
    )

    print(
        "OP-0337               : KHONG CHAY LAI"
    )

    print(
        "OP-0338               : KHONG CHAY LAI"
    )

    print(
        "Mầm non Lượng Minh    : GIU NGUYEN"
    )

    print(
        "CURRENT/FUTURE source : residual = 0"
    )

    print(
        "PAST                  : GIU NGUYEN 100%"
    )

    print(
        "Active users source   :",
        active_users_source,
    )

    print(
        "Integrity             :",
        integrity_after,
    )

    print(
        "Foreign key errors    :",
        fk_after,
    )

    print(
        "Batch executed_count  :",
        batch.get(
            "executed_count"
        ),
    )

    print(
        "Batch fingerprint     :",
        batch.get(
            "batch_fingerprint"
        ),
    )

    print(
        "DB SHA sau            :",
        sha256(DB),
    )

    print(
        "Backup ngoai          :",
        backup_dir,
    )

    print(
        "Backup service        :",
        result.get(
            "backup_name"
        ),
    )

    print(
        "Bao cao               :",
        report_path,
    )

    print()
    print(
        "CAP MN DA CO BATCH LOG."
    )

    print(
        "KHONG DUOC CHAY LAI SCRIPT NAY LAN THU HAI."
    )

    print("=" * 126)


except Exception as exc:

    print()
    print("=" * 126)
    print(
        "LOI TRONG EXECUTOR / HAU KIEM"
    )
    print("=" * 126)

    print(
        type(exc).__name__
        + ": "
        + str(exc)
    )

    traceback.print_exc()


    if executor_called:

        print()
        print(
            "Executor da duoc goi -> "
            "khoi phuc backup ngoai."
        )

        restore_external_backup(
            backup_db,
            backup_service,
            backup_lock,
            backup_resolution,
            backup_roster,
        )

    else:

        print(
            "Executor chua duoc goi. "
            "DB khong bi ghi boi script."
        )


    print("=" * 126)

    raise
