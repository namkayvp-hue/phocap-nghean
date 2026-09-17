from __future__ import annotations

import ast
import asyncio
import hashlib
import inspect
import json
import shutil
import sqlite3
import subprocess
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

MOVE_YEAR_IDS = [2, 8]

PAST_YEAR_IDS = [
    1,
    3,
    4,
    5,
    6,
    7,
]


EXPECTED_DB_SHA = (
    "44b1aa841cdd76301c57d9fc601121ae"
    "96f9312084ef05959eaae54acf17c8c9"
)

EXPECTED_SERVICE_SHA = (
    "963b8d6a280d8abef8e96486abd87d77"
    "cea289b08d2edb497647f250ed1b2af8"
)

EXPECTED_RESOLUTION_SHA = (
    "bf991e2ebb10a5952f07ca81caa24ead"
    "e98bca5f9e44beded54ae17c68fc373a"
)

EXPECTED_ROSTER_SHA = (
    "ef865f74aa51c2700ceb7746d5433b63"
    "fc6a52a4e3169014ebe0e446ac441120"
)

EXPECTED_BATCH_FP = (
    "30995a02ca8fd39d9bc6aea92de01cef"
    "85a912d0644a7d9bf409e80c615c712a"
)


PLAN_RULES = {
    "QD3805-OP-0410": {
        "plan_id":
            "PA2026-43804C58D423",

        "sources":
            [206],

        "target":
            205,

        "expected_staff_after":
            66,

        "label":
            "MN Hạnh Dịch -> MN Tiền Phong",
    },

    "QD3805-OP-0449": {
        "plan_id":
            "PA2026-4AB75BCD93EB",

        "sources":
            [325],

        "target":
            326,

        "expected_staff_after":
            67,

        "label":
            "MN Châu Thái -> MN Châu Cường",
    },

    "QD3805-OP-0175": {
        "plan_id":
            "PA2026-785CDDA8D8CC",

        "sources":
            [654],

        "target":
            653,

        "expected_staff_after":
            61,

        "label":
            "MN Giang Tây -> MN Giang Sơn Đông",
    },

    "QD3805-OP-0592": {
        "plan_id":
            "PA2026-7802B1BD1912",

        "sources":
            [713],

        "target":
            712,

        "expected_staff_after":
            71,

        "label":
            "MN Thanh Đức 1 -> MN Hạnh Lâm",
    },

    "QD3805-OP-0600": {
        "plan_id":
            "PA2026-1E90C6AAFD47",

        "sources":
            [736],

        "target":
            735,

        "expected_staff_after":
            45,

        "label":
            "MN Thanh Hà -> MN Thanh Long",
    },
}


EXPECTED_OPS = set(
    PLAN_RULES
)

EXPECTED_PLAN_IDS = {
    x["plan_id"]
    for x in PLAN_RULES.values()
}

ALL_SOURCE_IDS = sorted({
    sid
    for x in PLAN_RULES.values()
    for sid in x["sources"]
})

ALL_TARGET_IDS = sorted({
    int(x["target"])
    for x in PLAN_RULES.values()
})


# OP-0337 / OP-0338 tuyệt đối không được động đến.
PROTECTED_OLD_IDS = [
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
            lambda: f.read(
                1024 * 1024
            ),
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


def connect_ro(
    path: Path = DB,
) -> sqlite3.Connection:

    con = sqlite3.connect(
        path.resolve().as_uri()
        + "?mode=ro",
        uri=True,
        timeout=30,
    )

    con.row_factory = (
        sqlite3.Row
    )

    con.execute(
        "PRAGMA query_only=ON"
    )

    return con


def db_health(
    path: Path,
) -> tuple[str, int]:

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


def table_exists(
    con: sqlite3.Connection,
    table: str,
) -> bool:

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


def table_columns(
    con: sqlite3.Connection,
    table: str,
) -> list[str]:

    return [
        str(x["name"])
        for x in con.execute(
            f"""
            PRAGMA table_info(
                {qident(table)}
            )
            """
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


def year_aware_tables(
    con: sqlite3.Connection,
) -> list[str]:

    result = []

    for table in all_tables(con):

        cols = set(
            table_columns(
                con,
                table,
            )
        )

        if {
            "school_id",
            "school_year_id",
        }.issubset(cols):

            result.append(
                table
            )

    return result


def serialize_rows(
    rows,
) -> tuple[int, str]:

    values = []

    for row in rows:

        item = {
            key: row[key]
            for key in row.keys()
        }

        values.append(
            json.dumps(
                item,
                ensure_ascii=False,
                sort_keys=True,
                separators=(
                    ",",
                    ":",
                ),
                default=str,
            )
        )

    values.sort()

    h = hashlib.sha256()

    for value in values:
        h.update(
            value.encode(
                "utf-8"
            )
        )

        h.update(b"\n")

    return (
        len(values),
        h.hexdigest(),
    )


def past_snapshot(
    con: sqlite3.Connection,
    source_ids: list[int],
) -> dict:

    result = {}

    sm = ",".join(
        "?"
        for _ in source_ids
    )

    ym = ",".join(
        "?"
        for _ in PAST_YEAR_IDS
    )

    for table in (
        year_aware_tables(con)
    ):

        rows = con.execute(
            f"""
            SELECT *
            FROM {qident(table)}
            WHERE school_id
                  IN ({sm})
              AND school_year_id
                  IN ({ym})
            """,
            [
                *source_ids,
                *PAST_YEAR_IDS,
            ],
        ).fetchall()

        result[table] = (
            serialize_rows(
                rows
            )
        )

    return result


def protected_snapshot(
    con: sqlite3.Connection,
    school_ids: list[int],
) -> dict:

    result = {}

    marks = ",".join(
        "?"
        for _ in school_ids
    )

    school_rows = con.execute(
        f"""
        SELECT *
        FROM schools
        WHERE id IN ({marks})
        """,
        school_ids,
    ).fetchall()

    result["__schools__"] = (
        serialize_rows(
            school_rows
        )
    )

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
            WHERE school_id
                  IN ({marks})
            """,
            school_ids,
        ).fetchall()

        result[table] = (
            serialize_rows(
                rows
            )
        )

    return result


def current_future_residual(
    con: sqlite3.Connection,
    source_ids: list[int],
) -> dict[str, int]:

    result = {}

    sm = ",".join(
        "?"
        for _ in source_ids
    )

    ym = ",".join(
        "?"
        for _ in MOVE_YEAR_IDS
    )

    for table in (
        year_aware_tables(con)
    ):

        n = int(
            con.execute(
                f"""
                SELECT COUNT(*)
                FROM {qident(table)}
                WHERE school_id
                      IN ({sm})
                  AND school_year_id
                      IN ({ym})
                """,
                [
                    *source_ids,
                    *MOVE_YEAR_IDS,
                ],
            ).fetchone()[0]
            or 0
        )

        if n:
            result[table] = n

    return result


def active_staff_count(
    con: sqlite3.Connection,
    school_id: int,
) -> int:

    return int(
        con.execute(
            """
            SELECT COUNT(*)
            FROM staff_year_records
            WHERE school_id=?
              AND school_year_id=?
              AND is_active=1
            """,
            (
                school_id,
                YEAR_ID,
            ),
        ).fetchone()[0]
        or 0
    )


def staff_structure(
    con: sqlite3.Connection,
    school_id: int,
) -> dict[str, int]:

    rows = con.execute(
        """
        SELECT
            COALESCE(
                position_group,
                ''
            ) AS position_group,
            COUNT(*) AS n
        FROM staff_year_records
        WHERE school_id=?
          AND school_year_id=?
          AND is_active=1
        GROUP BY
            COALESCE(
                position_group,
                ''
            )
        ORDER BY position_group
        """,
        (
            school_id,
            YEAR_ID,
        ),
    ).fetchall()

    return {
        str(x["position_group"]):
            int(x["n"])
        for x in rows
    }


def duplicate_staff(
    con: sqlite3.Connection,
    school_id: int,
) -> list[dict]:

    rows = con.execute(
        """
        SELECT
            staff_member_id,
            COUNT(*) AS n
        FROM staff_year_records
        WHERE school_id=?
          AND school_year_id=?
          AND is_active=1
        GROUP BY staff_member_id
        HAVING COUNT(*) > 1
        ORDER BY staff_member_id
        """,
        (
            school_id,
            YEAR_ID,
        ),
    ).fetchall()

    return [
        {
            "staff_member_id":
                int(x[
                    "staff_member_id"
                ]),

            "count":
                int(x["n"]),
        }
        for x in rows
    ]


def active_source_users(
    con: sqlite3.Connection,
) -> int:

    marks = ",".join(
        "?"
        for _ in ALL_SOURCE_IDS
    )

    return int(
        con.execute(
            f"""
            SELECT COUNT(*)
            FROM users
            WHERE school_id
                  IN ({marks})
              AND is_active=1
            """,
            ALL_SOURCE_IDS,
        ).fetchone()[0]
        or 0
    )


def load_actor() -> dict:

    con = connect_ro()

    try:

        user_cols = set(
            table_columns(
                con,
                "users",
            )
        )

        rows = con.execute(
            """
            SELECT *
            FROM users
            WHERE username=?
            """,
            ("admin.sogddt",),
        ).fetchall()

        if len(rows) != 1:
            raise RuntimeError(
                "DỪNG: phải tìm thấy đúng "
                "1 tài khoản admin.sogddt."
            )

        user = dict(
            rows[0]
        )

        if (
            "is_active"
            in user_cols
            and not bool(
                user.get(
                    "is_active"
                )
            )
        ):
            raise RuntimeError(
                "DỪNG: admin.sogddt "
                "không active."
            )

        role_code = str(
            user.get(
                "role_code"
            )
            or ""
        ).strip()

        if (
            not role_code
            and user.get(
                "role_id"
            ) is not None
            and table_exists(
                con,
                "roles",
            )
        ):

            role_cols = set(
                table_columns(
                    con,
                    "roles",
                )
            )

            role = con.execute(
                """
                SELECT *
                FROM roles
                WHERE id=?
                LIMIT 1
                """,
                (
                    user[
                        "role_id"
                    ],
                ),
            ).fetchone()

            if role is not None:

                role = dict(role)

                for key in (
                    "code",
                    "role_code",
                    "name",
                ):
                    if (
                        key
                        in role_cols
                        and str(
                            role.get(
                                key
                            )
                            or ""
                        ).strip()
                    ):
                        role_code = str(
                            role[key]
                        ).strip()
                        break

        if not role_code:
            raise RuntimeError(
                "DỪNG: không xác định được "
                "role_code của admin.sogddt."
            )

        return {
            "id":
                int(
                    user["id"]
                ),

            "username":
                str(
                    user.get(
                        "username"
                    )
                    or ""
                ),

            "full_name":
                str(
                    user.get(
                        "full_name"
                    )
                    or ""
                ),

            "role_code":
                role_code,

            "school_id":
                user.get(
                    "school_id"
                ),

            "commune_id":
                user.get(
                    "commune_id"
                ),
        }

    finally:
        con.close()


def restore_external_backup(
    backup_db: Path,
    backup_service: Path,
    backup_resolution: Path,
    backup_roster: Path,
) -> None:

    print()
    print("=" * 126)
    print("KHOI PHUC TU BACKUP NGOAI")
    print("=" * 126)

    # Server đã được yêu cầu dừng.
    # Xóa sidecar để tránh WAL cũ ghi đè
    # bản DB vừa phục hồi.
    for suffix in (
        "-wal",
        "-shm",
        "-journal",
    ):
        p = Path(
            str(DB)
            + suffix
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
        backup_resolution,
        RESOLUTION,
    )

    shutil.copy2(
        backup_roster,
        ROSTER,
    )

    for suffix in (
        "-wal",
        "-shm",
        "-journal",
    ):
        p = Path(
            str(DB)
            + suffix
        )

        if p.exists():
            try:
                p.unlink()
            except Exception:
                pass

    restored_sha = (
        sha256(DB)
    )

    integrity, fk = (
        db_health(DB)
    )

    print(
        "DB SHA restored =",
        restored_sha,
    )

    print(
        "integrity        =",
        integrity,
    )

    print(
        "FK               =",
        fk,
    )

    if (
        restored_sha
        != EXPECTED_DB_SHA
        or integrity.lower()
        != "ok"
        or fk != 0
    ):
        raise RuntimeError(
            "CẢNH BÁO NGHIÊM TRỌNG: "
            "khôi phục backup chưa đạt."
        )

    print(
        "KHOI PHUC: THANH CONG"
    )


# ============================================================
# 0. HEADER
# ============================================================

print("=" * 126)
print(
    "THUC HIEN CHINH THUC SAP NHAP "
    "TOAN CAP MAM NON"
)
print("=" * 126)

print(
    "NAM HOC           : 2026-2027 / id=2"
)

print(
    "SO PHUONG AN GHI  : 5"
)

print(
    "OP-0337 / OP-0338: KHONG CHAY LAI"
)

print(
    "LUONG MINH        : DEFERRED - KHONG TAC DONG"
)

print(
    "BATCH FINGERPRINT :",
    EXPECTED_BATCH_FP,
)

print("=" * 126)


# ============================================================
# 1. SERVER / SIDECAR GATE
# ============================================================

for suffix in (
    "-wal",
    "-journal",
):
    sidecar = Path(
        str(DB)
        + suffix
    )

    if (
        sidecar.exists()
        and sidecar.stat().st_size
        > 0
    ):
        raise RuntimeError(
            "DỪNG AN TOÀN: "
            f"{sidecar.name} đang tồn tại "
            "và có dữ liệu. "
            "Hãy dừng Uvicorn/server hoàn toàn "
            "rồi chạy lại."
        )


# ============================================================
# 2. HASH GATE
# ============================================================

before_hash = {
    "db":
        sha256(DB),

    "service":
        sha256(SERVICE),

    "resolution":
        sha256(RESOLUTION),

    "roster":
        sha256(ROSTER),
}

print()
print("=" * 126)
print("1. HASH GATE")
print("=" * 126)

for key, value in (
    before_hash.items()
):
    print(
        f"{key:10s} = {value}"
    )


expected_hash = {
    "db":
        EXPECTED_DB_SHA,

    "service":
        EXPECTED_SERVICE_SHA,

    "resolution":
        EXPECTED_RESOLUTION_SHA,

    "roster":
        EXPECTED_ROSTER_SHA,
}

for key in expected_hash:

    if (
        before_hash[key]
        != expected_hash[key]
    ):
        raise RuntimeError(
            "DỪNG AN TOÀN: "
            + key
            + " không đúng nền đã khóa."
        )


# ============================================================
# 3. IMPORT + PREVIEW GATE
# ============================================================

from app.services import (
    school_merger_level_batch_service
    as batch_svc
)

from app.services.school_merger_preview_service import (
    build_official_plan_impact_preview,
)


pre = (
    batch_svc.build_level_batch_preview(
        school_year_id=YEAR_ID,
        level_code=LEVEL,
    )
)


print()
print("=" * 126)
print("2. PREFLIGHT BATCH THAT")
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
    "overlap               =",
    pre.get(
        "overlap_items"
    ),
)

print(
    "extra blockers        =",
    pre.get(
        "extra_blockers"
    ),
)

print(
    "fingerprint           =",
    pre.get(
        "batch_fingerprint"
    ),
)


if pre.get("counts") != {
    "KEEP": 51,
    "DONE": 184,
    "READY": 5,
    "BLOCK": 0,
}:
    raise RuntimeError(
        "DỪNG: KPI trước ghi không đúng."
    )

if (
    pre.get(
        "candidate_count"
    )
    != 5
):
    raise RuntimeError(
        "DỪNG: candidate_count != 5."
    )

if (
    pre.get(
        "effective_block_count"
    )
    != 0
):
    raise RuntimeError(
        "DỪNG: vẫn còn blocker."
    )

if (
    pre.get(
        "ready_for_execution"
    )
    is not True
):
    raise RuntimeError(
        "DỪNG: batch không còn READY."
    )

if (
    pre.get(
        "previous_batch"
    )
    is not None
):
    raise RuntimeError(
        "DỪNG: cấp MN đã có batch trước đó; "
        "tuyệt đối không chạy lần hai."
    )

if (
    pre.get(
        "overlap_items"
    )
    or []
):
    raise RuntimeError(
        "DỪNG: có overlap."
    )

if (
    pre.get(
        "extra_blockers"
    )
    or []
):
    raise RuntimeError(
        "DỪNG: còn extra blocker."
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
        "DỪNG: batch fingerprint "
        "đã thay đổi."
    )


# ============================================================
# 4. EXACT 5 PLAN GATE
# ============================================================

candidates = [
    dict(x)
    for x in (
        pre.get(
            "candidates"
        )
        or []
    )
    if isinstance(
        x,
        dict,
    )
]

found_ops = {
    str(
        x.get(
            "qd3805_operation_id"
        )
        or ""
    )
    for x in candidates
}

if found_ops != EXPECTED_OPS:
    raise RuntimeError(
        "DỪNG: danh sách operation READY "
        "không đúng 5 operation đã khóa."
    )


print()
print("=" * 126)
print("3. KHOA DUNG 5 NGUON -> DICH")
print("=" * 126)


for candidate in candidates:

    op = str(
        candidate.get(
            "qd3805_operation_id"
        )
        or ""
    )

    rule = PLAN_RULES[op]

    pid = str(
        candidate.get(
            "plan_id"
        )
        or ""
    )

    if pid != rule["plan_id"]:
        raise RuntimeError(
            f"DỪNG: {op} sai plan_id."
        )

    detail = (
        build_official_plan_impact_preview(
            pid
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
        ).get(
            "id"
        )
        or 0
    )

    if (
        sources
        != sorted(
            rule["sources"]
        )
        or target
        != rule["target"]
    ):
        raise RuntimeError(
            f"DỪNG: {op} source/target "
            "không còn đúng."
        )

    if not bool(
        detail.get(
            "simulation_ok"
        )
    ):
        raise RuntimeError(
            f"DỪNG: {op} simulation FAIL."
        )

    if not bool(
        detail.get(
            "safe_for_future_execution"
        )
    ):
        raise RuntimeError(
            f"DỪNG: {op} safe=False."
        )

    if (
        detail.get(
            "blockers"
        )
        or []
    ):
        raise RuntimeError(
            f"DỪNG: {op} có blocker."
        )

    if not bool(
        (
            detail.get(
                "source_audit"
            )
            or {}
        ).get(
            "pass"
        )
    ):
        raise RuntimeError(
            f"DỪNG: {op} source audit FAIL."
        )

    print(
        op,
        "|",
        rule["label"],
        "| source=",
        sources,
        "| target=",
        target,
    )


# ============================================================
# 5. DB HEALTH + SNAPSHOT TRUOC GHI
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

    year_map = {
        int(x["id"]):
            str(
                x["code"]
                or ""
            )
        for x in con.execute(
            """
            SELECT id,code
            FROM school_years
            """
        ).fetchall()
    }

    if (
        year_map.get(2)
        != "2026-2027"
        or year_map.get(8)
        != "2027-2028"
        or year_map.get(1)
        != "2025-2026"
    ):
        raise RuntimeError(
            "DỪNG: ánh xạ năm học "
            "không đúng nền dry-run."
        )

    if (
        integrity_before.lower()
        != "ok"
        or fk_before != 0
    ):
        raise RuntimeError(
            "DỪNG: DB không đạt integrity/FK."
        )

    source_rows = con.execute(
        f"""
        SELECT id,code,name,is_active
        FROM schools
        WHERE id IN (
            {",".join("?" for _ in ALL_SOURCE_IDS)}
        )
        ORDER BY id
        """,
        ALL_SOURCE_IDS,
    ).fetchall()

    if (
        len(source_rows)
        != len(ALL_SOURCE_IDS)
        or any(
            not bool(
                x["is_active"]
            )
            for x in source_rows
        )
    ):
        raise RuntimeError(
            "DỪNG: có trường nguồn "
            "không còn active trước ghi."
        )

    target_rows = con.execute(
        f"""
        SELECT id,code,name,is_active
        FROM schools
        WHERE id IN (
            {",".join("?" for _ in ALL_TARGET_IDS)}
        )
        ORDER BY id
        """,
        ALL_TARGET_IDS,
    ).fetchall()

    if (
        len(target_rows)
        != len(ALL_TARGET_IDS)
        or any(
            not bool(
                x["is_active"]
            )
            for x in target_rows
        )
    ):
        raise RuntimeError(
            "DỪNG: có trường đích "
            "không active."
        )

    # Lượng Minh.
    lm = con.execute(
        """
        SELECT id,code,name,is_active
        FROM schools
        WHERE code='40418311'
        LIMIT 1
        """
    ).fetchone()

    if lm is None:
        raise RuntimeError(
            "DỪNG: không tìm thấy "
            "Mầm non Lượng Minh."
        )

    LM_ID = int(
        lm["id"]
    )

    protected_ids = (
        PROTECTED_OLD_IDS
        + [LM_ID]
    )

    past_before = (
        past_snapshot(
            con,
            ALL_SOURCE_IDS,
        )
    )

    protected_before = (
        protected_snapshot(
            con,
            protected_ids,
        )
    )

    staff_before = {}

    for op, rule in (
        PLAN_RULES.items()
    ):
        staff_before[op] = {
            "target":
                active_staff_count(
                    con,
                    rule[
                        "target"
                    ],
                ),

            "sources": {
                sid:
                    active_staff_count(
                        con,
                        sid,
                    )
                for sid in (
                    rule[
                        "sources"
                    ]
                )
            },
        }

    # 5 plan chưa được ghi execution.
    if table_exists(
        con,
        "school_merger_official_executions",
    ):

        marks = ",".join(
            "?"
            for _ in EXPECTED_PLAN_IDS
        )

        old_exec = int(
            con.execute(
                f"""
                SELECT COUNT(*)
                FROM school_merger_official_executions
                WHERE plan_id
                      IN ({marks})
                """,
                sorted(
                    EXPECTED_PLAN_IDS
                ),
            ).fetchone()[0]
            or 0
        )

        if old_exec != 0:
            raise RuntimeError(
                "DỪNG: một trong 5 plan "
                "đã có execution log."
            )

finally:
    con.close()


print()
print("=" * 126)
print("4. DB TRUOC GHI")
print("=" * 126)

print(
    "integrity_check =",
    integrity_before,
)

print(
    "FK              =",
    fk_before,
)

print(
    "staff trước:"
)

for op in PLAN_RULES:
    print(
        " ",
        op,
        "=",
        staff_before[op],
    )


# ============================================================
# 6. TIM CHINH XAC HAM EXECUTE
# ============================================================

service_text = (
    SERVICE.read_text(
        encoding="utf-8-sig"
    )
)

tree = ast.parse(
    service_text
)

matches = []

for node in tree.body:

    if not isinstance(
        node,
        (
            ast.FunctionDef,
            ast.AsyncFunctionDef,
        ),
    ):
        continue

    args = [
        x.arg
        for x in (
            list(
                node.args.posonlyargs
            )
            + list(
                node.args.args
            )
            + list(
                node.args.kwonlyargs
            )
        )
    ]

    required_signature = {
        "school_year_id",
        "level_code",
        "expected_batch_fingerprint",
        "actor",
    }

    if required_signature.issubset(
        set(args)
    ):
        matches.append(
            node.name
        )


if len(matches) != 1:
    raise RuntimeError(
        "DỪNG AN TOÀN: cần đúng 1 hàm "
        "thực hiện batch có các tham số "
        "school_year_id/level_code/"
        "expected_batch_fingerprint/actor; "
        f"tìm thấy={matches}"
    )


executor_name = (
    matches[0]
)

executor = getattr(
    batch_svc,
    executor_name,
    None,
)

if not callable(executor):
    raise RuntimeError(
        "DỪNG: không nạp được hàm "
        + executor_name
    )


sig = inspect.signature(
    executor
)


print()
print("=" * 126)
print("5. EXECUTOR")
print("=" * 126)

print(
    "Function =",
    executor_name,
)

print(
    "Signature=",
    sig,
)


values = {
    "school_year_id":
        YEAR_ID,

    "level_code":
        LEVEL,

    "expected_batch_fingerprint":
        EXPECTED_BATCH_FP,

    "actor":
        load_actor(),
}


for name, param in (
    sig.parameters.items()
):

    if (
        param.kind
        == inspect.Parameter.POSITIONAL_ONLY
    ):
        raise RuntimeError(
            "DỪNG: executor có "
            "positional-only parameter "
            "ngoài thiết kế wrapper."
        )

    if (
        name not in values
        and param.default
        is inspect.Parameter.empty
        and param.kind
        not in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        )
    ):
        raise RuntimeError(
            "DỪNG: executor có tham số bắt buộc "
            f"chưa biết cách cấp an toàn: {name}"
        )


kwargs = {
    name: values[name]
    for name in values
    if name in sig.parameters
}


print(
    "Actor    =",
    json.dumps(
        values["actor"],
        ensure_ascii=False,
        default=str,
    ),
)


# ============================================================
# 7. BACKUP NGOAI DOC LAP
# ============================================================

stamp = datetime.now().strftime(
    "%Y%m%d_%H%M%S"
)

external_backup_dir = (
    ROOT
    / "backups"
    / (
        "backup_ngoai_truoc_thuc_hien_"
        "chinh_thuc_MN_"
        + stamp
    )
)

external_backup_dir.mkdir(
    parents=True,
    exist_ok=False,
)

backup_db = (
    external_backup_dir
    / "phocap.db"
)

backup_service = (
    external_backup_dir
    / SERVICE.name
)

backup_resolution = (
    external_backup_dir
    / RESOLUTION.name
)

backup_roster = (
    external_backup_dir
    / ROSTER.name
)


# Byte-copy chỉ thực hiện sau khi đã bắt buộc
# server/WAL dừng ở đầu script.
shutil.copy2(
    DB,
    backup_db,
)

shutil.copy2(
    SERVICE,
    backup_service,
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
        "DỪNG: backup DB ngoài "
        "không byte-identical với DB nền."
    )


# DB không được thay đổi trong lúc backup.
if (
    sha256(DB)
    != EXPECTED_DB_SHA
):
    raise RuntimeError(
        "DỪNG: DB thay đổi trong lúc "
        "tạo backup. Không thực hiện."
    )


backup_integrity, backup_fk = (
    db_health(
        backup_db
    )
)

if (
    backup_integrity.lower()
    != "ok"
    or backup_fk != 0
):
    raise RuntimeError(
        "DỪNG: backup ngoài "
        "không đạt integrity/FK."
    )


manifest = {
    "created_at":
        datetime.now().isoformat(
            timespec="seconds"
        ),

    "purpose":
        (
            "Backup ngoài trước khi "
            "thực hiện chính thức "
            "5 phương án MN"
        ),

    "database_sha256":
        EXPECTED_DB_SHA,

    "service_sha256":
        EXPECTED_SERVICE_SHA,

    "resolution_sha256":
        EXPECTED_RESOLUTION_SHA,

    "roster_sha256":
        EXPECTED_ROSTER_SHA,

    "batch_fingerprint":
        EXPECTED_BATCH_FP,

    "operations":
        PLAN_RULES,

    "actor":
        values["actor"],
}


(
    external_backup_dir
    / "manifest.json"
).write_text(
    json.dumps(
        manifest,
        ensure_ascii=False,
        indent=2,
        default=str,
    ),
    encoding="utf-8",
)


print()
print("=" * 126)
print("6. BACKUP NGOAI DA TAO")
print("=" * 126)

print(
    external_backup_dir
)

print(
    "Backup DB integrity =",
    backup_integrity,
)

print(
    "Backup DB FK        =",
    backup_fk,
)


# ============================================================
# 8. PREFLIGHT LAN CUOI NGAY TRUOC WRITE
# ============================================================

last_pre = (
    batch_svc.build_level_batch_preview(
        school_year_id=YEAR_ID,
        level_code=LEVEL,
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
):
    raise RuntimeError(
        "DỪNG: fingerprint thay đổi "
        "ngay trước lúc gọi executor."
    )

if (
    last_pre.get(
        "ready_for_execution"
    )
    is not True
    or last_pre.get(
        "candidate_count"
    )
    != 5
    or last_pre.get(
        "previous_batch"
    )
    is not None
):
    raise RuntimeError(
        "DỪNG: batch thay đổi "
        "ngay trước write."
    )


# ============================================================
# 9. THUC HIEN THAT
# ============================================================

execution_started = False
execution_result = None


try:

    print()
    print("=" * 126)
    print("7. BAT DAU GHI THAT 5 PHUONG AN MN")
    print("=" * 126)

    execution_started = True

    if inspect.iscoroutinefunction(
        executor
    ):
        execution_result = (
            asyncio.run(
                executor(
                    **kwargs
                )
            )
        )
    else:
        execution_result = (
            executor(
                **kwargs
            )
        )


    if not isinstance(
        execution_result,
        dict,
    ):
        raise RuntimeError(
            "Executor không trả về dict "
            "kết quả như dự kiến."
        )


    print()
    print(
        "EXECUTOR RETURN:"
    )

    print(
        json.dumps(
            execution_result,
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )


    # ========================================================
    # 10. HASH SOURCE/JSON SAU EXECUTE
    # ========================================================

    if (
        sha256(SERVICE)
        != EXPECTED_SERVICE_SHA
    ):
        raise RuntimeError(
            "Service source bị thay đổi."
        )

    if (
        sha256(RESOLUTION)
        != EXPECTED_RESOLUTION_SHA
    ):
        raise RuntimeError(
            "MN resolution bị thay đổi."
        )

    if (
        sha256(ROSTER)
        != EXPECTED_ROSTER_SHA
    ):
        raise RuntimeError(
            "MN roster bị thay đổi."
        )


    # ========================================================
    # 11. PREVIEW SAU THUC HIEN
    # ========================================================

    post = (
        batch_svc.build_level_batch_preview(
            school_year_id=YEAR_ID,
            level_code=LEVEL,
        )
    )


    states = {}

    for row in (
        post.get("rows")
        or []
    ):
        if not isinstance(
            row,
            dict,
        ):
            continue

        op = str(
            row.get(
                "qd3805_operation_id"
            )
            or ""
        )

        if op:
            states[op] = str(
                row.get(
                    "batch_state"
                )
                or ""
            ).upper()


    print()
    print("=" * 126)
    print("8. PREVIEW SAU THUC HIEN THAT")
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
        "ready_for_execution   =",
        post.get(
            "ready_for_execution"
        ),
    )

    print(
        "all_done              =",
        post.get(
            "all_done"
        ),
    )

    print(
        "previous_batch exists =",
        post.get(
            "previous_batch"
        )
        is not None,
    )


    if post.get("counts") != {
        "KEEP": 51,
        "DONE": 189,
        "READY": 0,
        "BLOCK": 0,
    }:
        raise RuntimeError(
            "HẬU KIỂM FAIL: "
            "KPI sau batch không đúng "
            "51/189/0/0."
        )

    if (
        post.get(
            "candidate_count"
        )
        != 0
    ):
        raise RuntimeError(
            "HẬU KIỂM FAIL: "
            "vẫn còn candidate."
        )

    if (
        post.get(
            "effective_block_count"
        )
        != 0
    ):
        raise RuntimeError(
            "HẬU KIỂM FAIL: "
            "effective_block_count != 0."
        )

    if (
        post.get(
            "all_done"
        )
        is not True
    ):
        raise RuntimeError(
            "HẬU KIỂM FAIL: "
            "all_done chưa True."
        )

    if (
        post.get(
            "previous_batch"
        )
        is None
    ):
        raise RuntimeError(
            "HẬU KIỂM FAIL: "
            "chưa có nhật ký batch MN."
        )

    for op in EXPECTED_OPS:

        if (
            states.get(op)
            != "DONE"
        ):
            raise RuntimeError(
                "HẬU KIỂM FAIL: "
                f"{op} chưa DONE."
            )

    if (
        states.get(
            "QD3805-OP-0337"
        )
        != "DONE"
    ):
        raise RuntimeError(
            "OP-0337 không còn DONE."
        )

    if (
        states.get(
            "QD3805-OP-0338"
        )
        != "DONE"
    ):
        raise RuntimeError(
            "OP-0338 không còn DONE."
        )


    # ========================================================
    # 12. KIEM TRA DB SAU THUC HIEN
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
                "HẬU KIỂM FAIL: integrity/FK."
            )


        # ------------------------------------
        # 12A. Batch log duy nhất của MN
        # ------------------------------------

        batch_rows = con.execute(
            """
            SELECT *
            FROM school_merger_level_batches
            WHERE school_year_id=?
              AND UPPER(TRIM(level_code))='MN'
            """,
            (YEAR_ID,),
        ).fetchall()

        if len(batch_rows) != 1:
            raise RuntimeError(
                "HẬU KIỂM FAIL: "
                "MN phải có đúng 1 batch log."
            )

        batch_row = dict(
            batch_rows[0]
        )

        if (
            int(
                batch_row.get(
                    "executed_count"
                )
                or 0
            )
            != 5
        ):
            raise RuntimeError(
                "executed_count != 5."
            )

        if (
            int(
                batch_row.get(
                    "done_before_count"
                )
                or 0
            )
            != 184
        ):
            raise RuntimeError(
                "done_before_count != 184."
            )

        if (
            int(
                batch_row.get(
                    "keep_count"
                )
                or 0
            )
            != 51
        ):
            raise RuntimeError(
                "keep_count != 51."
            )

        if (
            str(
                batch_row.get(
                    "batch_fingerprint"
                )
                or ""
            )
            != EXPECTED_BATCH_FP
        ):
            raise RuntimeError(
                "Batch log fingerprint sai."
            )


        # ------------------------------------
        # 12B. Đúng 5 official execution
        # ------------------------------------

        marks = ",".join(
            "?"
            for _ in EXPECTED_PLAN_IDS
        )

        exec_rows = con.execute(
            f"""
            SELECT *
            FROM school_merger_official_executions
            WHERE school_year_id=?
              AND plan_id IN ({marks})
            ORDER BY plan_id
            """,
            [
                YEAR_ID,
                *sorted(
                    EXPECTED_PLAN_IDS
                ),
            ],
        ).fetchall()

        if len(exec_rows) != 5:
            raise RuntimeError(
                "HẬU KIỂM FAIL: "
                "không có đúng 5 "
                "official execution."
            )

        actual_plan_ids = {
            str(x["plan_id"])
            for x in exec_rows
        }

        if (
            actual_plan_ids
            != EXPECTED_PLAN_IDS
        ):
            raise RuntimeError(
                "HẬU KIỂM FAIL: "
                "plan execution không đúng."
            )


        # ------------------------------------
        # 12C. Source inactive
        # ------------------------------------

        marks_source = ",".join(
            "?"
            for _ in ALL_SOURCE_IDS
        )

        source_after = con.execute(
            f"""
            SELECT id,code,name,is_active
            FROM schools
            WHERE id IN ({marks_source})
            ORDER BY id
            """,
            ALL_SOURCE_IDS,
        ).fetchall()

        if (
            len(source_after)
            != len(ALL_SOURCE_IDS)
            or any(
                bool(
                    x["is_active"]
                )
                for x in source_after
            )
        ):
            raise RuntimeError(
                "HẬU KIỂM FAIL: "
                "còn source active."
            )


        # ------------------------------------
        # 12D. Target active
        # ------------------------------------

        marks_target = ",".join(
            "?"
            for _ in ALL_TARGET_IDS
        )

        target_after = con.execute(
            f"""
            SELECT id,code,name,is_active
            FROM schools
            WHERE id IN ({marks_target})
            ORDER BY id
            """,
            ALL_TARGET_IDS,
        ).fetchall()

        if (
            len(target_after)
            != len(ALL_TARGET_IDS)
            or any(
                not bool(
                    x["is_active"]
                )
                for x in target_after
            )
        ):
            raise RuntimeError(
                "HẬU KIỂM FAIL: "
                "có target không active."
            )


        # ------------------------------------
        # 12E. CURRENT/FUTURE residual = 0
        # ------------------------------------

        residual_after = (
            current_future_residual(
                con,
                ALL_SOURCE_IDS,
            )
        )

        if residual_after:
            raise RuntimeError(
                "HẬU KIỂM FAIL: "
                "còn CURRENT/FUTURE residual: "
                + repr(
                    residual_after
                )
            )


        # ------------------------------------
        # 12F. Active user source = 0
        # ------------------------------------

        source_users_after = (
            active_source_users(
                con
            )
        )

        if source_users_after != 0:
            raise RuntimeError(
                "HẬU KIỂM FAIL: "
                "còn active user ở source."
            )


        # ------------------------------------
        # 12G. PAST phải giữ nguyên 100%
        # ------------------------------------

        past_after = (
            past_snapshot(
                con,
                ALL_SOURCE_IDS,
            )
        )

        if past_after != past_before:
            raise RuntimeError(
                "HẬU KIỂM FAIL: "
                "PAST tại source đã thay đổi."
            )


        # ------------------------------------
        # 12H. OP0337/0338 + Lượng Minh
        #      không được thay đổi
        # ------------------------------------

        protected_after = (
            protected_snapshot(
                con,
                protected_ids,
            )
        )

        if (
            protected_after
            != protected_before
        ):
            raise RuntimeError(
                "HẬU KIỂM FAIL: "
                "OP-0337/OP-0338 hoặc "
                "Lượng Minh bị tác động."
            )


        # ------------------------------------
        # 12I. Nhân sự target đúng dry-run
        # ------------------------------------

        staff_after = {}

        for op, rule in (
            PLAN_RULES.items()
        ):

            count = (
                active_staff_count(
                    con,
                    rule["target"],
                )
            )

            structure = (
                staff_structure(
                    con,
                    rule["target"],
                )
            )

            dup = (
                duplicate_staff(
                    con,
                    rule["target"],
                )
            )

            staff_after[op] = {
                "count":
                    count,

                "structure":
                    structure,

                "duplicates":
                    dup,
            }

            if (
                count
                != rule[
                    "expected_staff_after"
                ]
            ):
                raise RuntimeError(
                    "HẬU KIỂM FAIL: "
                    f"{op} số nhân sự đích "
                    f"={count}, cần "
                    f"{rule['expected_staff_after']}."
                )

            if dup:
                raise RuntimeError(
                    "HẬU KIỂM FAIL: "
                    f"{op} có duplicate "
                    "staff_member_id."
                )

    finally:
        con.close()


    # ========================================================
    # 13. BAO CAO THANH CONG
    # ========================================================

    db_after_sha = (
        sha256(DB)
    )

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
            "ket_qua_thuc_hien_chinh_thuc_MN_"
            + stamp
            + ".json"
        )
    )

    report = {
        "status":
            "SUCCESS_COMMITTED",

        "school_year_id":
            YEAR_ID,

        "level_code":
            LEVEL,

        "batch_fingerprint":
            EXPECTED_BATCH_FP,

        "database_sha256_before":
            EXPECTED_DB_SHA,

        "database_sha256_after":
            db_after_sha,

        "service_sha256":
            sha256(
                SERVICE
            ),

        "resolution_sha256":
            sha256(
                RESOLUTION
            ),

        "roster_sha256":
            sha256(
                ROSTER
            ),

        "external_backup":
            str(
                external_backup_dir
            ),

        "service_batch_backup":
            batch_row.get(
                "backup_name"
            ),

        "batch_row":
            batch_row,

        "official_execution_plan_ids":
            sorted(
                actual_plan_ids
            ),

        "staff_before":
            staff_before,

        "staff_after":
            staff_after,

        "current_future_residual":
            residual_after,

        "active_users_at_sources":
            source_users_after,

        "past_exact":
            past_after
            == past_before,

        "protected_old_operations_exact":
            protected_after
            == protected_before,

        "integrity":
            integrity_after,

        "foreign_key_errors":
            fk_after,

        "executor":
            executor_name,

        "execution_result":
            execution_result,
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
    print("9. HAU KIEM NHAN SU 5 TRUONG DICH")
    print("=" * 126)

    for op in PLAN_RULES:

        print(
            op,
            "|",
            PLAN_RULES[op][
                "label"
            ],
        )

        print(
            "  Tổng =",
            staff_after[op][
                "count"
            ],
        )

        print(
            "  Cơ cấu =",
            staff_after[op][
                "structure"
            ],
        )

        print(
            "  Duplicate =",
            staff_after[op][
                "duplicates"
            ],
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
        "5 phuong an moi      : DONE"
    )

    print(
        "OP-0337              : DONE - KHONG CHAY LAI"
    )

    print(
        "OP-0338              : DONE - KHONG CHAY LAI"
    )

    print(
        "Luong Minh           : DEFERRED - KHONG TAC DONG"
    )

    print(
        "CURRENT/FUTURE       : residual = 0"
    )

    print(
        "PAST                 : GIU NGUYEN 100%"
    )

    print(
        "Active users source  : 0"
    )

    print(
        "Source schools       : INACTIVE"
    )

    print(
        "Target schools       : ACTIVE"
    )

    print(
        "Integrity            :",
        integrity_after,
    )

    print(
        "Foreign key errors   :",
        fk_after,
    )

    print(
        "Batch log executed   :",
        batch_row.get(
            "executed_count"
        ),
    )

    print(
        "Batch fingerprint    :",
        batch_row.get(
            "batch_fingerprint"
        ),
    )

    print(
        "DB SHA truoc         :",
        EXPECTED_DB_SHA,
    )

    print(
        "DB SHA sau           :",
        db_after_sha,
    )

    print()
    print(
        "Backup ngoai:",
        external_backup_dir,
    )

    print(
        "Backup cua service:",
        batch_row.get(
            "backup_name"
        ),
    )

    print(
        "Bao cao:",
        report_path,
    )

    print()
    print(
        "CAP MN DA CO NHAT KY BATCH. "
        "KHONG DUOC CHAY SCRIPT NAY LAN THU HAI."
    )

    print("=" * 126)


except Exception as exc:

    print()
    print("=" * 126)
    print("LOI TRONG THUC HIEN / HAU KIEM")
    print("=" * 126)

    print(
        type(exc).__name__
        + ": "
        + str(exc)
    )

    traceback.print_exc()

    if execution_started:

        print()
        print(
            "DA BAT DAU GOI EXECUTOR -> "
            "BAT BUOC KHOI PHUC BACKUP NGOAI."
        )

        restore_external_backup(
            backup_db,
            backup_service,
            backup_resolution,
            backup_roster,
        )

        print()
        print(
            "DB DA QUAY VE TRANG THAI "
            "TRUOC KHI THUC HIEN CAP MN."
        )

    else:

        print()
        print(
            "Executor CHUA duoc goi; "
            "database khong bi ghi boi script."
        )

    print("=" * 126)

    raise
