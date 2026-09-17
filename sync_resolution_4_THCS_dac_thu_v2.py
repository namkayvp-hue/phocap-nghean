# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import importlib
import json
import os
import shutil
import sqlite3
import sys
from collections import Counter
from datetime import datetime
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

EXPORTS = ROOT / "exports"


EXPECTED_SHA = {
    "db":
        "706279fe9cd63f9f01c4c3d7637f955534280b7b745e333b0b6943c2e64aed89",

    "engine":
        "414fb49a4c5f4fed7b571cc55df381678fe660cd8a675ecaa2f6fd70ebd7827a",

    "service":
        "9104fb99c78755e9eec86d090659b3a922834ff097d7292aa4d4b29e360a27f9",

    "resolution":
        "d9d347b19de0795553c8f047cb91a430ded63d9232ac7eda7ea069b716c2c0f4",

    "plans":
        "4e2c5f044c48c57dda40fecc11f4e9f466f236aacc082f224536b1685cadb1fc",
}


YEAR_ID = 2

CASES = [
    {
        "operation_id": "QD3805-OP-0399",
        "plan_id": "PA2026-35F6C2558FC4",
        "source_id": 1592,
        "source_code": "40415505",
        "target_id": 1594,
        "target_code": "40415510",
        "target_name": "THCS Mường Quàng",
        "previous_target": 23,
        "previous_source": 27,
        "current_target": 50,
    },
    {
        "operation_id": "QD3805-OP-0424",
        "plan_id": "PA2026-F228D672FCAC",
        "source_id": 1485,
        "source_code": "40416506",
        "target_id": 1486,
        "target_code": "40416507",
        "target_name": "THCS Châu Tiến",
        "previous_target": 30,
        "previous_source": 30,
        "current_target": 60,
    },
    {
        "operation_id": "QD3805-OP-0434",
        "plan_id": "PA2026-6948B60DF298",
        "source_id": 1647,
        "source_code": "40416504",
        "target_id": 1646,
        "target_code": "40416501",
        "target_name": "THCS Quỳ Châu",
        "previous_target": 45,
        "previous_source": 32,
        "current_target": 77,
    },
    {
        "operation_id": "QD3805-OP-0451",
        "plan_id": "PA2026-CC0F70262554",
        "source_id": 1589,
        "source_code": "40420509",
        "target_id": 1590,
        "target_code": "40420518",
        "target_name": "THCS Mường Ham",
        "previous_target": 25,
        "previous_source": 32,
        "current_target": 57,
    },
]

WANTED = {
    x["operation_id"]
    for x in CASES
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()

    with path.open("rb") as f:
        for chunk in iter(
            lambda: f.read(1024 * 1024),
            b"",
        ):
            h.update(chunk)

    return h.hexdigest()


def connect_ro():
    con = sqlite3.connect(
        DB.resolve().as_uri()
        + "?mode=ro",
        uri=True,
        timeout=120,
    )

    con.row_factory = sqlite3.Row
    con.execute("PRAGMA query_only=ON")
    con.execute("PRAGMA foreign_keys=ON")

    return con


def atomic_json_write(
    path: Path,
    data: dict,
):
    text = json.dumps(
        data,
        ensure_ascii=False,
        indent=2,
    )

    # Tự kiểm JSON.
    json.loads(text)

    tmp = path.with_suffix(
        path.suffix + ".tmp"
    )

    tmp.write_text(
        text,
        encoding="utf-8",
    )

    os.replace(
        tmp,
        path,
    )


def restore_file(
    backup: Path,
):
    tmp = RESOLUTION.with_suffix(
        RESOLUTION.suffix
        + ".restore.tmp"
    )

    shutil.copy2(
        backup,
        tmp,
    )

    os.replace(
        tmp,
        RESOLUTION,
    )


def op_ids(items):
    return [
        str(
            (x or {}).get(
                "operation_id"
            )
            or ""
        )
        for x in (items or [])
        if isinstance(x, dict)
    ]


print("=" * 145)
print(
    "THCS - SYNC RESOLUTION 4 OP "
    "- BAN SUA DIEU KIEN HAU KIEM"
)
print(
    "KHONG SUA DATABASE - "
    "KHONG CHAY SAP NHAP"
)
print("=" * 145)


# ============================================================
# 1. HASH GATE
# ============================================================

print()
print("1. HASH GATE")
print("-" * 145)

paths = {
    "db": DB,
    "engine": ENGINE,
    "service": SERVICE,
    "resolution": RESOLUTION,
    "plans": PLANS,
}

for key, path in paths.items():

    if not path.exists():
        raise RuntimeError(
            f"Không tìm thấy: {path}"
        )

    actual = sha256(path)

    print(
        f"{key:12s} = {actual}"
    )

    if actual != EXPECTED_SHA[key]:
        raise RuntimeError(
            f"DUNG: SHA {key} "
            "không đúng nền đã khóa."
        )


for suffix in (
    "-wal",
    "-journal",
):
    path = Path(
        str(DB) + suffix
    )

    size = (
        path.stat().st_size
        if path.exists()
        else 0
    )

    print(
        path.name,
        "=",
        size,
    )

    if size != 0:
        raise RuntimeError(
            "DUNG: server hoặc tiến trình "
            "đang ghi database."
        )


# ============================================================
# 2. DATABASE READ-ONLY GATE
# ============================================================

print()
print("2. KIEM TRA DATABASE")
print("-" * 145)

sys.path.insert(
    0,
    str(ROOT),
)

from app.services import (
    school_merger_level_batch_service
    as levelsvc
)


OFFICIAL_TABLE = str(
    levelsvc.OFFICIAL_EXECUTION_TABLE
)

BATCH_TABLE = str(
    levelsvc.BATCH_TABLE
)


with connect_ro() as con:

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

    print(
        "integrity =",
        integrity,
    )

    print(
        "FK        =",
        fk,
    )

    if (
        integrity.lower() != "ok"
        or fk != 0
    ):
        raise RuntimeError(
            "DUNG: database health FAIL."
        )


    batch_count = int(
        con.execute(
            f"""
            SELECT COUNT(*)
            FROM "{BATCH_TABLE}"
            WHERE school_year_id=?
              AND level_code='THCS'
            """,
            (YEAR_ID,),
        ).fetchone()[0]
        or 0
    )

    print(
        "THCS batch count =",
        batch_count,
    )

    if batch_count != 1:
        raise RuntimeError(
            "DUNG: THCS phải có "
            "đúng 1 batch."
        )


    for case in CASES:

        op = case[
            "operation_id"
        ]

        source = con.execute(
            """
            SELECT
                id,
                code,
                name,
                is_active
            FROM schools
            WHERE id=?
            """,
            (
                case["source_id"],
            ),
        ).fetchone()

        target = con.execute(
            """
            SELECT
                id,
                code,
                name,
                is_active
            FROM schools
            WHERE id=?
            """,
            (
                case["target_id"],
            ),
        ).fetchone()


        if (
            source is None
            or target is None
        ):
            raise RuntimeError(
                op
                + ": thiếu source/target."
            )


        if (
            str(source["code"])
            != case["source_code"]
        ):
            raise RuntimeError(
                op
                + ": sai source code."
            )


        if int(
            source["is_active"]
            or 0
        ) != 0:
            raise RuntimeError(
                op
                + ": source chưa inactive."
            )


        if (
            str(target["code"])
            != case["target_code"]
        ):
            raise RuntimeError(
                op
                + ": sai target code."
            )


        if (
            str(target["name"])
            != case["target_name"]
        ):
            raise RuntimeError(
                op
                + ": sai tên target."
            )


        if int(
            target["is_active"]
            or 0
        ) != 1:
            raise RuntimeError(
                op
                + ": target không active."
            )


        official = con.execute(
            f"""
            SELECT
                plan_id,
                target_school_id,
                source_school_ids_json
            FROM "{OFFICIAL_TABLE}"
            WHERE plan_id=?
              AND school_year_id=?
            """,
            (
                case["plan_id"],
                YEAR_ID,
            ),
        ).fetchall()


        if len(official) != 1:
            raise RuntimeError(
                op
                + ": official execution "
                  "không đúng 1."
            )


        row = official[0]

        source_ids = json.loads(
            str(
                row[
                    "source_school_ids_json"
                ]
                or "[]"
            )
        )


        if (
            int(
                row[
                    "target_school_id"
                ]
            )
            != case["target_id"]

            or source_ids
            != [case["source_id"]]
        ):
            raise RuntimeError(
                op
                + ": official mapping sai."
            )


        source_current = int(
            con.execute(
                """
                SELECT COUNT(*)
                FROM staff_year_records
                WHERE school_year_id=?
                  AND school_id=?
                  AND is_active=1
                """,
                (
                    YEAR_ID,
                    case["source_id"],
                ),
            ).fetchone()[0]
            or 0
        )


        target_current = int(
            con.execute(
                """
                SELECT COUNT(
                    DISTINCT staff_member_id
                )
                FROM staff_year_records
                WHERE school_year_id=?
                  AND school_id=?
                  AND is_active=1
                """,
                (
                    YEAR_ID,
                    case["target_id"],
                ),
            ).fetchone()[0]
            or 0
        )


        if source_current != 0:
            raise RuntimeError(
                op
                + ": source vẫn còn "
                  "staff hiện hành."
            )


        if (
            target_current
            != case["current_target"]
        ):
            raise RuntimeError(
                op
                + ": số staff target "
                  "không còn đúng."
            )


        print(
            op,
            "| official=1",
            "| source current=0",
            "| target current=",
            target_current,
            "| PASS",
        )


# ============================================================
# 3. CURRENT RESOLUTION GATE
# ============================================================

print()
print("3. RESOLUTION HIEN TAI")
print("-" * 145)

payload = json.loads(
    RESOLUTION.read_text(
        encoding="utf-8-sig"
    )
)


special = payload.get(
    "special_same_level"
)

precompleted = payload.get(
    "precompleted"
)

deferred = payload.get(
    "deferred_orphans"
)


if not isinstance(
    special,
    list,
):
    raise RuntimeError(
        "Thiếu special_same_level."
    )


if not isinstance(
    precompleted,
    list,
):
    raise RuntimeError(
        "Thiếu precompleted."
    )


if not isinstance(
    deferred,
    list,
):
    raise RuntimeError(
        "Thiếu deferred_orphans."
    )


special_count = Counter(
    op_ids(special)
)

pre_count = Counter(
    op_ids(precompleted)
)


for op in sorted(WANTED):

    print(
        op,
        "| special=",
        special_count[op],
        "| precompleted=",
        pre_count[op],
    )

    if special_count[op] != 1:
        raise RuntimeError(
            op
            + ": cần đúng 1 special."
        )

    if pre_count[op] != 0:
        raise RuntimeError(
            op
            + ": precompleted đã tồn tại."
        )


# Nghi Hương giữ nguyên.
nghi_huong = [
    x
    for x in deferred
    if isinstance(x, dict)
    and str(
        x.get("operation_id")
        or ""
    )
    == "QD3805-ORPHAN-R116"
]


if len(nghi_huong) != 1:
    raise RuntimeError(
        "DUNG: Nghi Hương R116 "
        "không đúng 1 bản ghi."
    )


if (
    "GIỮ NGUYÊN"
    not in str(
        nghi_huong[0].get(
            "status"
        )
        or ""
    ).upper()
):
    raise RuntimeError(
        "DUNG: Nghi Hương "
        "không còn GIỮ NGUYÊN."
    )


existing_pre = set(
    op_ids(precompleted)
)


for op in (
    "QD3805-OP-0342",
    "QD3805-OP-0343",
):
    if op not in existing_pre:
        raise RuntimeError(
            "DUNG: mất "
            + op
            + " precompleted."
        )


# ============================================================
# 4. TẠO RESOLUTION MỚI
# ============================================================

print()
print("4. TAO RESOLUTION MOI")
print("-" * 145)

proposed = json.loads(
    json.dumps(
        payload,
        ensure_ascii=False,
    )
)


old_special = proposed[
    "special_same_level"
]


proposed[
    "special_same_level"
] = [
    x
    for x in old_special
    if not (
        isinstance(x, dict)
        and str(
            x.get(
                "operation_id"
            )
            or ""
        )
        in WANTED
    )
]


removed = (
    len(old_special)
    - len(
        proposed[
            "special_same_level"
        ]
    )
)


if removed != 4:
    raise RuntimeError(
        "DUNG: phải loại đúng "
        "4 special."
    )


for case in CASES:

    proposed[
        "precompleted"
    ].append(
        {
            "operation_id":
                case[
                    "operation_id"
                ],

            "source_school_code":
                case[
                    "source_code"
                ],

            "target_school_code":
                case[
                    "target_code"
                ],

            "previous_year_code":
                "2025-2026",

            "current_year_code":
                "2026-2027",

            "expected_previous_target_active":
                case[
                    "previous_target"
                ],

            "expected_previous_source_active":
                case[
                    "previous_source"
                ],

            "expected_current_target_active":
                case[
                    "current_target"
                ],

            "expected_current_source_active":
                0,

            "expected_previous_identity_count":
                case[
                    "current_target"
                ],

            "require_identity_exact":
                True,

            "allow_special_audit_gate":
                True,

            "completion_evidence": {
                "plan_id":
                    case["plan_id"],

                "source_school_id":
                    case["source_id"],

                "target_school_id":
                    case["target_id"],

                "target_name_2026_2027":
                    case[
                        "target_name"
                    ],

                "policy":
                    "SOURCE_2_IS_TARGET",

                "database_sha_after_commit":
                    EXPECTED_SHA["db"],

                "post_audit":
                    "PASS",
            },

            "reason": (
                "Đã thực hiện chính thức riêng sau batch THCS; "
                "có đúng 1 official execution và audit PASS. "
                "Nguồn đã inactive, dữ liệu hiện hành tại nguồn bằng 0; "
                "đích giữ nguyên school_id/mã và đổi tên theo QĐ3805. "
                "Đội ngũ 2026-2027 đã được hậu kiểm khớp nguồn + đích "
                "năm 2025-2026. Tuyệt đối không chạy lại."
            ),
        }
    )


final_special_ids = set(
    op_ids(
        proposed[
            "special_same_level"
        ]
    )
)

final_pre_ids = Counter(
    op_ids(
        proposed[
            "precompleted"
        ]
    )
)


for op in WANTED:

    if op in final_special_ids:
        raise RuntimeError(
            op
            + ": vẫn còn special."
        )

    if final_pre_ids[op] != 1:
        raise RuntimeError(
            op
            + ": precompleted "
              "không đúng 1."
        )


print(
    "special removed =",
    removed,
)

print(
    "precompleted added =",
    4,
)


# ============================================================
# 5. BACKUP
# ============================================================

stamp = datetime.now().strftime(
    "%Y%m%d_%H%M%S"
)

backup_dir = (
    EXPORTS
    / (
        "backup_truoc_sync_"
        "THCS_4_v2_"
        + stamp
    )
)

backup_dir.mkdir(
    parents=True,
    exist_ok=False,
)

backup_resolution = (
    backup_dir
    / RESOLUTION.name
)

shutil.copy2(
    RESOLUTION,
    backup_resolution,
)


print()
print("5. BACKUP")
print("-" * 145)

print(
    "BACKUP =",
    backup_dir,
)


# ============================================================
# 6. GHI RESOLUTION
# ============================================================

written = False

try:

    atomic_json_write(
        RESOLUTION,
        proposed,
    )

    written = True

    print()
    print("6. RESOLUTION DA GHI")
    print("-" * 145)

    print(
        "NEW SHA =",
        sha256(
            RESOLUTION
        ),
    )


    # ========================================================
    # 7. SERVICE VALIDATION
    # ========================================================

    levelsvc = importlib.reload(
        levelsvc
    )

    preview = (
        levelsvc.build_level_batch_preview(
            school_year_id=YEAR_ID,
            level_code="THCS",
        )
    )


    counts = dict(
        preview.get(
            "counts"
        )
        or {}
    )


    candidate_count = len(
        preview.get(
            "candidates"
        )
        or []
    )


    effective_block = int(
        preview.get(
            "effective_block_count"
        )
        or 0
    )


    previous_batch = bool(
        preview.get(
            "previous_batch"
        )
    )


    ready = bool(
        preview.get(
            "ready_for_execution"
        )
    )


    special_ops = set(
        str(x)
        for x in (
            preview.get(
                "special_ops"
            )
            or []
        )
    )


    print()
    print("7. SERVICE PREVIEW")
    print("-" * 145)

    print(
        "counts =",
        counts,
    )

    print(
        "candidate_count =",
        candidate_count,
    )

    print(
        "effective_block_count =",
        effective_block,
    )

    print(
        "previous_batch =",
        previous_batch,
    )

    print(
        "ready_for_execution =",
        ready,
    )

    print(
        "4 OP con trong special =",
        sorted(
            WANTED
            & special_ops
        ),
    )


    # ĐIỀU KIỆN ĐÚNG:
    # Sau khi 4 precompleted được service công nhận:
    # DONE phải tăng 97 -> 101.
    expected_counts = {
        "KEEP": 36,
        "DONE": 101,
        "READY": 0,
        "BLOCK": 0,
    }


    if counts != expected_counts:
        raise RuntimeError(
            "DUNG: counts sau sync "
            f"không đúng {expected_counts}; "
            f"thực tế={counts}"
        )


    if candidate_count != 0:
        raise RuntimeError(
            "DUNG: phát sinh candidate."
        )


    if effective_block != 0:
        raise RuntimeError(
            "DUNG: phát sinh BLOCK."
        )


    if not previous_batch:
        raise RuntimeError(
            "DUNG: mất dấu batch "
            "THCS đã thực hiện."
        )


    if ready:
        raise RuntimeError(
            "DUNG: service lại mở "
            "thực hiện batch THCS."
        )


    if WANTED & special_ops:
        raise RuntimeError(
            "DUNG: 4 OP vẫn còn "
            "trong special."
        )


    # ========================================================
    # 8. FINAL FILE + DB SAFETY
    # ========================================================

    if sha256(DB) != EXPECTED_SHA[
        "db"
    ]:
        raise RuntimeError(
            "DUNG: database bị thay đổi."
        )


    if sha256(
        ENGINE
    ) != EXPECTED_SHA[
        "engine"
    ]:
        raise RuntimeError(
            "DUNG: engine bị thay đổi."
        )


    if sha256(
        SERVICE
    ) != EXPECTED_SHA[
        "service"
    ]:
        raise RuntimeError(
            "DUNG: service bị thay đổi."
        )


    if sha256(
        PLANS
    ) != EXPECTED_SHA[
        "plans"
    ]:
        raise RuntimeError(
            "DUNG: approved plans "
            "bị thay đổi."
        )


    # Đọc lại JSON vừa ghi.
    check = json.loads(
        RESOLUTION.read_text(
            encoding="utf-8-sig"
        )
    )


    special_after = set(
        op_ids(
            check.get(
                "special_same_level"
            )
        )
    )


    pre_after = Counter(
        op_ids(
            check.get(
                "precompleted"
            )
        )
    )


    for op in WANTED:

        if op in special_after:
            raise RuntimeError(
                op
                + ": vẫn còn special "
                  "sau ghi."
            )

        if pre_after[op] != 1:
            raise RuntimeError(
                op
                + ": không có đúng "
                  "1 precompleted."
            )


    with connect_ro() as con:

        batch_after = int(
            con.execute(
                f"""
                SELECT COUNT(*)
                FROM "{BATCH_TABLE}"
                WHERE school_year_id=?
                  AND level_code='THCS'
                """,
                (YEAR_ID,),
            ).fetchone()[0]
            or 0
        )


    if batch_after != 1:
        raise RuntimeError(
            "DUNG: THCS batch "
            "không còn đúng 1."
        )


except Exception as exc:

    if written:

        print()
        print(
            "HAU KIEM KHONG DAT."
        )

        print(
            "TU DONG KHOI PHUC "
            "RESOLUTION CU..."
        )

        restore_file(
            backup_resolution
        )


        restored = sha256(
            RESOLUTION
        )

        print(
            "RESTORED SHA =",
            restored,
        )


        if (
            restored
            != EXPECTED_SHA[
                "resolution"
            ]
        ):
            raise RuntimeError(
                "NGUY HIEM: restore "
                "resolution không đúng."
            ) from exc


    print()
    print("=" * 145)
    print(
        "DUNG AN TOAN - "
        "KHONG CO THAY DOI DB"
    )
    print("=" * 145)

    print(
        repr(exc)
    )

    raise SystemExit(2)


print()
print("=" * 145)
print(
    "SYNC_THCS_SPECIAL_4_V2: PASS"
)
print("=" * 145)

print(
    "QD3805-OP-0399 = DONE"
)

print(
    "QD3805-OP-0424 = DONE"
)

print(
    "QD3805-OP-0434 = DONE"
)

print(
    "QD3805-OP-0451 = DONE"
)

print(
    "COUNTS = KEEP 36 | DONE 101 | READY 0 | BLOCK 0"
)

print(
    "SPECIAL 4 OP = DA LOAI"
)

print(
    "DATABASE = KHONG THAY DOI"
)

print(
    "ENGINE = KHONG THAY DOI"
)

print(
    "SERVICE = KHONG THAY DOI"
)

print(
    "APPROVED PLANS = KHONG THAY DOI"
)

print(
    "THCS BATCH COUNT = 1"
)

print(
    "KHONG DUOC CHAY LAI BATCH THCS"
)

print()
print(
    "CON LAI 15 TRUONG HOP THCS "
    "CAN XU LY RIENG."
)

print(
    "READY_FOR_NEXT_THCS_SPECIAL_GROUP=YES"
)

print("=" * 145)
