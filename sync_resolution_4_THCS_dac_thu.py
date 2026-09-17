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

ENGINE_FILE = (
    ROOT
    / "app"
    / "services"
    / "school_merger_service.py"
)

SERVICE_FILE = (
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


EXPECTED = {
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
PREVIOUS_YEAR_ID = 1


CASES = [
    {
        "operation_id":
            "QD3805-OP-0399",

        "plan_id":
            "PA2026-35F6C2558FC4",

        "source_id":
            1592,

        "source_code":
            "40415505",

        "target_id":
            1594,

        "target_code":
            "40415510",

        "target_name":
            "THCS Mường Quàng",

        "previous_source_eligible":
            27,

        "previous_target_eligible":
            23,

        "current_target":
            50,

        "excluded":
            1,
    },

    {
        "operation_id":
            "QD3805-OP-0424",

        "plan_id":
            "PA2026-F228D672FCAC",

        "source_id":
            1485,

        "source_code":
            "40416506",

        "target_id":
            1486,

        "target_code":
            "40416507",

        "target_name":
            "THCS Châu Tiến",

        "previous_source_eligible":
            30,

        "previous_target_eligible":
            30,

        "current_target":
            60,

        "excluded":
            1,
    },

    {
        "operation_id":
            "QD3805-OP-0434",

        "plan_id":
            "PA2026-6948B60DF298",

        "source_id":
            1647,

        "source_code":
            "40416504",

        "target_id":
            1646,

        "target_code":
            "40416501",

        "target_name":
            "THCS Quỳ Châu",

        "previous_source_eligible":
            32,

        "previous_target_eligible":
            45,

        "current_target":
            77,

        "excluded":
            0,
    },

    {
        "operation_id":
            "QD3805-OP-0451",

        "plan_id":
            "PA2026-CC0F70262554",

        "source_id":
            1589,

        "source_code":
            "40420509",

        "target_id":
            1590,

        "target_code":
            "40420518",

        "target_name":
            "THCS Mường Ham",

        "previous_source_eligible":
            32,

        "previous_target_eligible":
            25,

        "current_target":
            57,

        "excluded":
            0,
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
            lambda: f.read(
                1024 * 1024
            ),
            b"",
        ):
            h.update(chunk)

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


def connect_ro():

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

    return con


def atomic_write_json(
    path: Path,
    payload: dict,
):

    raw = json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
    )

    # Tự kiểm JSON trước khi ghi.
    json.loads(raw)

    tmp = path.with_name(
        path.name
        + ".sync4.tmp"
    )

    tmp.write_text(
        raw,
        encoding="utf-8",
    )

    os.replace(
        tmp,
        path,
    )


def restore_resolution(
    backup_file: Path,
):

    tmp = RESOLUTION.with_name(
        RESOLUTION.name
        + ".restore.tmp"
    )

    shutil.copy2(
        backup_file,
        tmp,
    )

    os.replace(
        tmp,
        RESOLUTION,
    )


def eligible_ids(
    con,
    merger,
    school_id,
):

    rows = con.execute(
        """
        SELECT *
        FROM staff_year_records
        WHERE school_id=?
          AND school_year_id=?
        ORDER BY id
        """,
        (
            school_id,
            PREVIOUS_YEAR_ID,
        ),
    ).fetchall()

    result = set()
    excluded = 0

    seen = Counter()

    for row in rows:

        staff_id = int(
            row["staff_member_id"]
        )

        seen[staff_id] += 1

        if (
            merger._classify_staff(row)
            == "CHUA_XAC_DINH"
        ):
            raise RuntimeError(
                f"school_id={school_id}: "
                "có nhân sự chưa phân loại."
            )

        if merger._staff_inactive(
            row
        ):
            excluded += 1
            continue

        result.add(
            staff_id
        )

    dup = {
        k: v
        for k, v
        in seen.items()
        if v > 1
    }

    if dup:
        raise RuntimeError(
            f"school_id={school_id}: "
            f"trùng staff_member_id {dup}"
        )

    return result, excluded


def current_active_ids(
    con,
    school_id,
):

    rows = con.execute(
        """
        SELECT staff_member_id
        FROM staff_year_records
        WHERE school_id=?
          AND school_year_id=?
          AND is_active=1
          AND staff_member_id IS NOT NULL
        ORDER BY staff_member_id
        """,
        (
            school_id,
            YEAR_ID,
        ),
    ).fetchall()

    values = [
        int(x["staff_member_id"])
        for x in rows
    ]

    if len(values) != len(
        set(values)
    ):
        raise RuntimeError(
            f"school_id={school_id}: "
            "trùng nhân sự hiện hành."
        )

    return set(values)


def find_operation_states(
    obj,
    wanted,
):

    found = {}

    def walk(value):

        if isinstance(
            value,
            dict,
        ):

            op = str(
                value.get(
                    "operation_id"
                )
                or ""
            )

            if op in wanted:

                found.setdefault(
                    op,
                    [],
                ).append(
                    dict(value)
                )

            for child in value.values():
                walk(child)

        elif isinstance(
            value,
            list,
        ):

            for child in value:
                walk(child)

    walk(obj)

    return found


print("=" * 150)
print(
    "THCS - DONG BO RESOLUTION "
    "4 PHUONG AN DA COMMIT"
)
print(
    "CHI SUA qd3805_thcs_resolution.json"
)
print(
    "KHONG SUA DATABASE - KHONG SAP NHAP"
)
print("=" * 150)


# ============================================================
# 1. HASH GATE
# ============================================================

print()
print("1. HASH GATE")
print("-" * 150)


PATHS = {
    "db":
        DB,

    "engine":
        ENGINE_FILE,

    "service":
        SERVICE_FILE,

    "resolution":
        RESOLUTION,

    "plans":
        PLANS,
}


before_hash = {}


for key, path in PATHS.items():

    if not path.exists():

        raise RuntimeError(
            f"Không tìm thấy: {path}"
        )

    value = sha256(
        path
    )

    before_hash[key] = value

    print(
        f"{key:12s} = {value}"
    )

    if value != EXPECTED[key]:

        raise RuntimeError(
            "DUNG: hash "
            + key
            + " không đúng nền đã khóa."
        )


for suffix in (
    "-wal",
    "-journal",
):

    p = Path(
        str(DB) + suffix
    )

    size = (
        p.stat().st_size
        if p.exists()
        else 0
    )

    print(
        p.name,
        "=",
        size,
    )

    if size:

        raise RuntimeError(
            "DUNG: hãy dừng server/Uvicorn."
        )


# ============================================================
# 2. IMPORT ENGINE + SERVICE
# ============================================================

sys.path.insert(
    0,
    str(ROOT),
)

from app.services import (
    school_merger_service
    as merger
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


# ============================================================
# 3. DB EVIDENCE GATE - CHỈ ĐỌC
# ============================================================

print()
print("2. KIEM TRA BANG CHUNG DATABASE")
print("-" * 150)


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
            "DUNG: DB health FAIL."
        )


    batch_count = int(
        con.execute(
            (
                "SELECT COUNT(*) "
                "FROM "
                + qident(BATCH_TABLE)
                + " WHERE school_year_id=? "
                  "AND level_code='THCS'"
            ),
            (
                YEAR_ID,
            ),
        ).fetchone()[0]
        or 0
    )

    if batch_count != 1:

        raise RuntimeError(
            "DUNG: THCS batch count="
            + str(batch_count)
            + "; cần đúng 1."
        )


    for case in CASES:

        op = case[
            "operation_id"
        ]

        source = con.execute(
            """
            SELECT
                id,code,name,is_active
            FROM schools
            WHERE id=?
            """,
            (
                case[
                    "source_id"
                ],
            ),
        ).fetchone()

        target = con.execute(
            """
            SELECT
                id,code,name,is_active
            FROM schools
            WHERE id=?
            """,
            (
                case[
                    "target_id"
                ],
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

            or int(
                source["is_active"]
                or 0
            ) != 0

            or str(target["code"])
            != case["target_code"]

            or str(target["name"])
            != case["target_name"]

            or int(
                target["is_active"]
                or 0
            ) != 1
        ):
            raise RuntimeError(
                op
                + ": trạng thái trường "
                  "không đúng hậu kiểm."
            )


        official = con.execute(
            (
                "SELECT "
                "plan_id,"
                "target_school_id,"
                "source_school_ids_json,"
                "backup_name "
                "FROM "
                + qident(OFFICIAL_TABLE)
                + " WHERE "
                "plan_id=? "
                "AND school_year_id=?"
            ),
            (
                case["plan_id"],
                YEAR_ID,
            ),
        ).fetchall()

        if len(official) != 1:

            raise RuntimeError(
                op
                + ": official execution != 1."
            )

        row = official[0]

        source_json = json.loads(
            str(
                row[
                    "source_school_ids_json"
                ]
                or "[]"
            )
        )

        if (
            int(
                row["target_school_id"]
            )
            != case["target_id"]

            or source_json
            != [
                case["source_id"]
            ]
        ):
            raise RuntimeError(
                op
                + ": official mapping sai."
            )


        src_ids, src_excluded = (
            eligible_ids(
                con,
                merger,
                case["source_id"],
            )
        )

        tgt_ids, tgt_excluded = (
            eligible_ids(
                con,
                merger,
                case["target_id"],
            )
        )

        current_ids = (
            current_active_ids(
                con,
                case["target_id"],
            )
        )


        if (
            len(src_ids)
            != case[
                "previous_source_eligible"
            ]

            or len(tgt_ids)
            != case[
                "previous_target_eligible"
            ]

            or len(current_ids)
            != case[
                "current_target"
            ]

            or src_excluded
               + tgt_excluded
            != case["excluded"]

            or src_ids & tgt_ids

            or (
                src_ids
                | tgt_ids
            )
            != current_ids
        ):
            raise RuntimeError(
                op
                + ": identity rollover "
                  "không còn khớp 100%."
            )


        current_source = int(
            con.execute(
                """
                SELECT COUNT(*)
                FROM staff_year_records
                WHERE school_id=?
                  AND school_year_id=?
                  AND is_active=1
                """,
                (
                    case["source_id"],
                    YEAR_ID,
                ),
            ).fetchone()[0]
            or 0
        )

        if current_source != 0:

            raise RuntimeError(
                op
                + ": source còn đội ngũ "
                  "2026-2027."
            )


        print(
            op,
            "| official=1",
            "| previous=",
            len(tgt_ids),
            "+",
            len(src_ids),
            "| current=",
            len(current_ids),
            "| identity exact=PASS",
        )


print(
    "THCS batch count =",
    batch_count,
)


# ============================================================
# 4. LOAD CURRENT RESOLUTION
# ============================================================

print()
print("3. KIEM TRA RESOLUTION HIEN TAI")
print("-" * 150)


payload = json.loads(
    RESOLUTION.read_text(
        encoding="utf-8-sig"
    )
)


if not isinstance(
    payload,
    dict,
):
    raise RuntimeError(
        "Resolution không phải object JSON."
    )


special = payload.get(
    "special_same_level"
)

precompleted = payload.get(
    "precompleted"
)


if not isinstance(
    special,
    list,
):
    raise RuntimeError(
        "Thiếu mảng special_same_level."
    )


if not isinstance(
    precompleted,
    list,
):
    raise RuntimeError(
        "Thiếu mảng precompleted."
    )


special_counter = Counter(
    str(
        (x or {}).get(
            "operation_id"
        )
        or ""
    )
    for x in special
    if isinstance(x, dict)
)


pre_counter = Counter(
    str(
        (x or {}).get(
            "operation_id"
        )
        or ""
    )
    for x in precompleted
    if isinstance(x, dict)
)


for op in sorted(WANTED):

    print(
        op,
        "| special=",
        special_counter[op],
        "| precompleted=",
        pre_counter[op],
    )

    if special_counter[op] != 1:

        raise RuntimeError(
            op
            + ": phải có đúng 1 "
              "bản ghi special hiện tại."
        )

    if pre_counter[op] != 0:

        raise RuntimeError(
            op
            + ": đã có precompleted; "
              "không ghi lặp."
        )


# Nghi Hương phải còn nguyên trong deferred_orphans.
deferred = payload.get(
    "deferred_orphans"
) or []


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
        "DUNG: không còn đúng "
        "1 Nghi Hương R116."
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


# OP0342/0343 đã khóa trước phải giữ nguyên.
existing_pre_ids = {
    str(
        x.get(
            "operation_id"
        )
        or ""
    )
    for x in precompleted
    if isinstance(x, dict)
}


for op in (
    "QD3805-OP-0342",
    "QD3805-OP-0343",
):

    if op not in existing_pre_ids:

        raise RuntimeError(
            "DUNG: mất precompleted "
            + op
        )


# ============================================================
# 5. BUILD PROPOSED RESOLUTION
# ============================================================

print()
print("4. TAO PHUONG AN DONG BO")
print("-" * 150)


proposed = json.loads(
    json.dumps(
        payload,
        ensure_ascii=False,
    )
)


old_special = (
    proposed[
        "special_same_level"
    ]
)


new_special = [
    item
    for item in old_special
    if not (
        isinstance(item, dict)
        and str(
            item.get(
                "operation_id"
            )
            or ""
        )
        in WANTED
    )
]


if (
    len(old_special)
    - len(new_special)
    != 4
):

    raise RuntimeError(
        "DUNG: số special bị loại "
        "không đúng 4."
    )


proposed[
    "special_same_level"
] = new_special


new_rules = []


for case in CASES:

    rule = {
        "operation_id":
            case["operation_id"],

        "source_school_code":
            case["source_code"],

        "target_school_code":
            case["target_code"],

        "previous_year_code":
            "2025-2026",

        "current_year_code":
            "2026-2027",

        # Đây là số ĐỦ ĐIỀU KIỆN rollover,
        # không phải tổng raw is_active.
        "expected_previous_target_active":
            case[
                "previous_target_eligible"
            ],

        "expected_previous_source_active":
            case[
                "previous_source_eligible"
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

        # Các OP này từng nằm trong special do QĐ
        # không cung cấp target code mới.
        # Bằng chứng official execution đã khóa
        # source2 làm target.
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
                case["target_name"],

            "policy":
                "SOURCE_2_IS_TARGET",

            "database_sha_after_commit":
                EXPECTED["db"],

            "post_audit":
                "PASS",
        },

        "reason": (
            "Đã thực hiện chính thức riêng sau batch THCS theo "
            "nguyên tắc nguồn 2 làm đích; có đúng 1 official execution "
            "và audit operation. Source đã inactive, CURRENT/FUTURE "
            "tại source bằng 0; target giữ nguyên school_id/mã, đổi tên "
            "theo QĐ3805; đội ngũ 2026-2027 khớp 100% identity với tập "
            "đủ điều kiện rollover của source + target năm 2025-2026. "
            "Hậu kiểm độc lập PASS. Tuyệt đối không chạy lại."
        ),
    }

    new_rules.append(
        rule
    )


proposed[
    "precompleted"
].extend(
    new_rules
)


# Kiểm trùng operation_id sau biến đổi.
for key in (
    "special_same_level",
    "precompleted",
):

    ids = [
        str(
            x.get(
                "operation_id"
            )
            or ""
        )
        for x in proposed.get(
            key
        ) or []
        if isinstance(x, dict)
        and str(
            x.get(
                "operation_id"
            )
            or ""
        )
    ]

    dup = {
        k: v
        for k, v
        in Counter(ids).items()
        if v > 1
    }

    if dup:

        raise RuntimeError(
            "DUNG: trùng operation_id "
            f"trong {key}: {dup}"
        )


for op in sorted(WANTED):

    special_n = sum(
        1
        for x in proposed[
            "special_same_level"
        ]
        if isinstance(x, dict)
        and str(
            x.get(
                "operation_id"
            )
            or ""
        )
        == op
    )

    pre_n = sum(
        1
        for x in proposed[
            "precompleted"
        ]
        if isinstance(x, dict)
        and str(
            x.get(
                "operation_id"
            )
            or ""
        )
        == op
    )

    if (
        special_n != 0
        or pre_n != 1
    ):

        raise RuntimeError(
            op
            + ": proposed resolution sai."
        )


print(
    "special removed = 4"
)

print(
    "precompleted added = 4"
)


# ============================================================
# 6. BACKUP RESOLUTION
# ============================================================

stamp = datetime.now().strftime(
    "%Y%m%d_%H%M%S"
)


backup_dir = (
    EXPORTS
    / (
        "backup_truoc_sync_"
        "THCS_special_4_"
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


manifest = {
    "created_at":
        datetime.now().isoformat(
            timespec="seconds"
        ),

    "operation":
        "SYNC_THCS_SPECIAL_4_TO_PRECOMPLETED",

    "database_changed":
        False,

    "source_changed":
        False,

    "approved_plans_changed":
        False,

    "resolution_before_sha":
        EXPECTED["resolution"],

    "database_sha":
        EXPECTED["db"],

    "operation_ids":
        sorted(WANTED),

    "backup_resolution":
        str(
            backup_resolution
        ),
}


(
    backup_dir
    / "metadata.json"
).write_text(
    json.dumps(
        manifest,
        ensure_ascii=False,
        indent=2,
    ),
    encoding="utf-8",
)


print()
print("5. BACKUP")
print("-" * 150)

print(
    "BACKUP =",
    backup_dir,
)


# ============================================================
# 7. WRITE RESOLUTION ONLY
# ============================================================

print()
print("6. GHI RESOLUTION")
print("-" * 150)


written = False


try:

    atomic_write_json(
        RESOLUTION,
        proposed,
    )

    written = True

    new_sha = sha256(
        RESOLUTION
    )

    print(
        "resolution new SHA =",
        new_sha,
    )


    # ========================================================
    # 8. SERVICE PREVIEW AFTER SYNC
    # ========================================================

    # Reload để service đọc đúng resolution mới.
    levelsvc = importlib.reload(
        levelsvc
    )


    preview = (
        levelsvc.build_level_batch_preview(
            school_year_id=YEAR_ID,
            level_code="THCS",
        )
    )


    print()
    print("7. SERVICE PREVIEW SAU SYNC")
    print("-" * 150)

    print(
        "counts =",
        preview.get(
            "counts"
        ),
    )

    print(
        "candidate_count =",
        len(
            preview.get(
                "candidates"
            )
            or []
        ),
    )

    print(
        "effective_block_count =",
        preview.get(
            "effective_block_count"
        ),
    )

    print(
        "previous_batch =",
        bool(
            preview.get(
                "previous_batch"
            )
        ),
    )

    print(
        "ready_for_execution =",
        preview.get(
            "ready_for_execution"
        ),
    )


    done_precompleted = set(
        str(x)
        for x in (
            preview.get(
                "done_precompleted"
            )
            or []
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


    print(
        "done_precompleted target =",
        sorted(
            WANTED
            & done_precompleted
        ),
    )

    print(
        "special target con lai =",
        sorted(
            WANTED
            & special_ops
        ),
    )


    # Nếu service không trả trực tiếp hai list trên,
    # in toàn bộ các object liên quan để chẩn đoán.
    found_states = (
        find_operation_states(
            preview,
            WANTED,
        )
    )


    for op in sorted(
        WANTED
    ):

        print()
        print(
            "SERVICE STATE",
            op,
        )

        rows = found_states.get(
            op,
            []
        )

        for row in rows[:6]:

            print(
                json.dumps(
                    row,
                    ensure_ascii=False,
                    default=str,
                )[:5000]
            )


    # Chấp nhận DONE theo một trong hai bằng chứng:
    # 1) done_precompleted của service;
    # 2) object của operation mang state/status DONE.
    recognized_done = set(
        done_precompleted
    )


    for op, rows in (
        found_states.items()
    ):

        for row in rows:

            values = {
                str(
                    row.get(key)
                    or ""
                ).upper()

                for key in (
                    "state",
                    "status",
                    "batch_state",
                    "execution_state",
                )
            }

            if (
                "DONE" in values
                or
                "COMPLETED" in values
                or
                "PRECOMPLETED" in values
            ):

                recognized_done.add(
                    op
                )


    if not bool(
        preview.get(
            "previous_batch"
        )
    ):

        raise RuntimeError(
            "Service không còn nhận "
            "THCS batch đã thực hiện."
        )


    if (
        WANTED
        & special_ops
    ):

        raise RuntimeError(
            "4 OP vẫn còn bị service "
            "xem là special: "
            + repr(
                sorted(
                    WANTED
                    & special_ops
                )
            )
        )


    if not WANTED.issubset(
        recognized_done
    ):

        missing = sorted(
            WANTED
            - recognized_done
        )

        raise RuntimeError(
            "Service CHƯA công nhận đủ "
            "4 OP là DONE/PRECOMPLETED: "
            + repr(
                missing
            )
        )


    # Không được xuất hiện candidate mới.
    candidate_ids = {
        str(
            x.get(
                "operation_id"
            )
            or ""
        )
        for x in (
            preview.get(
                "candidates"
            )
            or []
        )
        if isinstance(x, dict)
    }


    if WANTED & candidate_ids:

        raise RuntimeError(
            "DUNG: một trong 4 OP "
            "trở thành candidate chạy lại."
        )


    # ========================================================
    # 9. FINAL SAFETY
    # ========================================================

    print()
    print("8. FINAL SAFETY")
    print("-" * 150)


    if sha256(DB) != EXPECTED[
        "db"
    ]:

        raise RuntimeError(
            "DUNG: database đã thay đổi."
        )


    if sha256(
        ENGINE_FILE
    ) != EXPECTED[
        "engine"
    ]:

        raise RuntimeError(
            "DUNG: engine đã thay đổi."
        )


    if sha256(
        SERVICE_FILE
    ) != EXPECTED[
        "service"
    ]:

        raise RuntimeError(
            "DUNG: service đã thay đổi."
        )


    if sha256(
        PLANS
    ) != EXPECTED[
        "plans"
    ]:

        raise RuntimeError(
            "DUNG: Approved Plans đã thay đổi."
        )


    final_payload = json.loads(
        RESOLUTION.read_text(
            encoding="utf-8-sig"
        )
    )


    final_special = {
        str(
            x.get(
                "operation_id"
            )
            or ""
        )
        for x in (
            final_payload.get(
                "special_same_level"
            )
            or []
        )
        if isinstance(x, dict)
    }


    final_pre = {
        str(
            x.get(
                "operation_id"
            )
            or ""
        )
        for x in (
            final_payload.get(
                "precompleted"
            )
            or []
        )
        if isinstance(x, dict)
    }


    if WANTED & final_special:

        raise RuntimeError(
            "DUNG: final special vẫn "
            "còn 4 OP."
        )


    if not WANTED.issubset(
        final_pre
    ):

        raise RuntimeError(
            "DUNG: final precompleted "
            "chưa đủ 4 OP."
        )


    with connect_ro() as con:

        batch_count_after = int(
            con.execute(
                (
                    "SELECT COUNT(*) "
                    "FROM "
                    + qident(
                        BATCH_TABLE
                    )
                    + " WHERE "
                    "school_year_id=? "
                    "AND level_code='THCS'"
                ),
                (
                    YEAR_ID,
                ),
            ).fetchone()[0]
            or 0
        )


    if batch_count_after != 1:

        raise RuntimeError(
            "DUNG: THCS batch không còn 1."
        )


    print(
        "DB SHA              =",
        sha256(DB),
    )

    print(
        "SERVICE SHA         =",
        sha256(
            SERVICE_FILE
        ),
    )

    print(
        "PLANS SHA           =",
        sha256(
            PLANS
        ),
    )

    print(
        "RESOLUTION NEW SHA  =",
        sha256(
            RESOLUTION
        ),
    )

    print(
        "THCS BATCH COUNT    =",
        batch_count_after,
    )


except Exception as exc:

    if written:

        print()
        print(
            "VALIDATE SAU GHI KHONG DAT."
        )

        print(
            "DANG TU DONG KHOI PHUC "
            "RESOLUTION CU..."
        )

        restore_resolution(
            backup_resolution
        )

        restored_sha = sha256(
            RESOLUTION
        )

        print(
            "RESTORED SHA =",
            restored_sha,
        )

        if (
            restored_sha
            != EXPECTED[
                "resolution"
            ]
        ):

            raise RuntimeError(
                "NGUY HIEM: không khôi phục "
                "được resolution đúng SHA cũ."
            ) from exc

    print()
    print("=" * 150)
    print(
        "SYNC DUNG AN TOAN - "
        "RESOLUTION DA KHOI PHUC"
    )
    print("=" * 150)

    print(
        repr(exc)
    )

    print(
        "DATABASE KHONG BI THAY DOI."
    )

    print(
        "KHONG CHAY LAI SAP NHAP."
    )

    raise SystemExit(2)


print()
print("=" * 150)
print(
    "SYNC_THCS_SPECIAL_4: PASS"
)
print("=" * 150)

print(
    "QD3805-OP-0399 = DONE / PRECOMPLETED"
)

print(
    "QD3805-OP-0424 = DONE / PRECOMPLETED"
)

print(
    "QD3805-OP-0434 = DONE / PRECOMPLETED"
)

print(
    "QD3805-OP-0451 = DONE / PRECOMPLETED"
)

print(
    "SPECIAL_SAME_LEVEL    = DA LOAI 4 OP"
)

print(
    "DATABASE              = KHONG THAY DOI"
)

print(
    "ENGINE                = KHONG THAY DOI"
)

print(
    "LEVEL SERVICE         = KHONG THAY DOI"
)

print(
    "APPROVED PLANS        = KHONG THAY DOI"
)

print(
    "THCS BATCH            = VAN CHI 1"
)

print(
    "NGHI HUONG            = GIU NGUYEN"
)

print(
    "OP0342 / OP0343       = GIU PRECOMPLETED"
)

print()
print(
    "CON LAI 15 TRUONG HOP "
    "THCS DANG XU LY RIENG."
)

print(
    "READY_FOR_NEXT_THCS_SPECIAL_GROUP=YES"
)

print("=" * 150)
