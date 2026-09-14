from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path


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


EXPECTED_DB_SHA = (
    "44b1aa841cdd76301c57d9fc601121ae"
    "96f9312084ef05959eaae54acf17c8c9"
)

EXPECTED_SERVICE_SHA = (
    "963b8d6a280d8abef8e96486abd87d77"
    "cea289b08d2edb497647f250ed1b2af8"
)

EXPECTED_LOCK_SHA = (
    "51d7c3eff12c1d8732a10008c85fc7c"
    "823db1f84736837578864ccd9edb823a5"
)

EXPECTED_RESOLUTION_SHA = (
    "bf991e2ebb10a5952f07ca81caa24ead"
    "e98bca5f9e44beded54ae17c68fc373a"
)

EXPECTED_ROSTER_SHA = (
    "ef865f74aa51c2700ceb7746d5433b63"
    "fc6a52a4e3169014ebe0e446ac441120"
)

OLD_BATCH_FP = (
    "30995a02ca8fd39d9bc6aea92de01cef"
    "85a912d0644a7d9bf409e80c615c712a"
)


LM_OP = "QD3805-ORPHAN-R1216"
LM_STT = 1211
LM_ROW = 1216
LM_CODE = "40418311"
LM_NAME = "Mầm non Lượng Minh"
LM_COMMUNE = "Lượng Minh"


READY_EXPECTED = {
    "QD3805-OP-0175",
    "QD3805-OP-0410",
    "QD3805-OP-0449",
    "QD3805-OP-0592",
    "QD3805-OP-0600",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()

    with path.open("rb") as f:
        for block in iter(
            lambda: f.read(1024 * 1024),
            b"",
        ):
            h.update(block)

    return h.hexdigest()


def atomic_json(path: Path, payload: dict) -> None:
    tmp = path.with_name(
        path.name + ".tmp_luong_minh_keep"
    )

    tmp.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    os.replace(
        tmp,
        path,
    )


def first_stt(op: dict) -> int:
    values = []

    for value in (
        op.get("stt_members")
        or []
    ):
        try:
            values.append(
                int(value)
            )
        except Exception:
            pass

    return (
        min(values)
        if values
        else 999999
    )


def fresh_state() -> dict:

    code = r'''
import json

from app.services import (
    school_merger_level_batch_service
    as svc
)

p = svc.build_level_batch_preview(
    school_year_id=2,
    level_code="MN",
)

s = svc.registry_level_summary(
    "MN"
)

rows, counts2, candidates2, meta = (
    svc._state_rows(
        2,
        "MN",
    )
)

states = {}
ready = []

for row in p.get("rows") or []:
    if not isinstance(row, dict):
        continue

    op = str(
        row.get(
            "qd3805_operation_id"
        )
        or ""
    )

    state = str(
        row.get(
            "batch_state"
        )
        or ""
    ).upper()

    if op:
        states[op] = state

    if state == "READY":
        ready.append(op)

print(json.dumps({
    "counts":
        p.get("counts"),

    "candidate_count":
        p.get("candidate_count"),

    "effective_block_count":
        p.get("effective_block_count"),

    "ready_for_execution":
        p.get("ready_for_execution"),

    "previous_batch":
        p.get("previous_batch"),

    "extra_blockers":
        p.get("extra_blockers") or [],

    "overlap_items":
        p.get("overlap_items") or [],

    "batch_fingerprint":
        p.get("batch_fingerprint"),

    "registry_summary":
        s,

    "states":
        states,

    "ready_ops":
        sorted(ready),

    "missing_action_ops":
        meta.get("missing_action_ops") or [],

    "missing_keep_ops":
        meta.get("missing_keep_ops") or [],

    "mapped_keep_count":
        meta.get("mapped_keep_count"),

    "expected_keep_count":
        meta.get("expected_keep_count"),
}, ensure_ascii=False, default=str))
'''

    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            code,
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr)

        raise RuntimeError(
            "Fresh preview FAIL."
        )

    return json.loads(
        proc.stdout.strip()
    )


print("=" * 126)
print(
    "CHUYEN MAM NON LUONG MINH SANG GIU NGUYEN"
)
print("=" * 126)

print(
    "CHI SUA:"
)
print(
    " - qd3805_level_lock.json"
)
print(
    " - qd3805_mn_resolution.json"
)

print()
print(
    "KHONG SUA:"
)
print(
    " - phocap.db"
)
print(
    " - school_merger_level_batch_service.py"
)
print(
    " - MN roster"
)
print(
    " - du lieu truong Mầm non Lượng Minh"
)
print(
    " - 5 phuong an READY"
)
print("=" * 126)


# ============================================================
# 1. HASH GATE
# ============================================================

before = {
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


print()
print("=" * 126)
print("1. HASH GATE")
print("=" * 126)

for key, value in before.items():
    print(
        f"{key:12s} = {value}"
    )


expected = {
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


for key in expected:
    if before[key] != expected[key]:
        raise RuntimeError(
            "DUNG AN TOAN: "
            + key
            + " khong dung nen da khoa."
        )


# ============================================================
# 2. BASELINE
# ============================================================

baseline = fresh_state()


print()
print("=" * 126)
print("2. BASELINE")
print("=" * 126)

print(
    "counts                =",
    baseline["counts"],
)

print(
    "candidate_count       =",
    baseline[
        "candidate_count"
    ],
)

print(
    "effective_block_count =",
    baseline[
        "effective_block_count"
    ],
)

print(
    "ready_for_execution   =",
    baseline[
        "ready_for_execution"
    ],
)

print(
    "batch_fingerprint     =",
    baseline[
        "batch_fingerprint"
    ],
)

print(
    "registry summary      =",
    baseline[
        "registry_summary"
    ],
)


if baseline["counts"] != {
    "KEEP": 51,
    "DONE": 184,
    "READY": 5,
    "BLOCK": 0,
}:
    raise RuntimeError(
        "DUNG: baseline KPI sai."
    )

if (
    baseline[
        "batch_fingerprint"
    ]
    != OLD_BATCH_FP
):
    raise RuntimeError(
        "DUNG: fingerprint baseline sai."
    )

if baseline[
    "previous_batch"
] is not None:
    raise RuntimeError(
        "DUNG: MN da co batch log."
    )


# ============================================================
# 3. DOC LEVEL LOCK
# ============================================================

lock = json.loads(
    LOCK.read_text(
        encoding="utf-8-sig"
    )
)

if (
    str(
        lock.get("schema")
        or ""
    )
    != "QD3805_LEVEL_LOCK_2026"
):
    raise RuntimeError(
        "DUNG: schema level lock sai."
    )


operations = [
    dict(x)
    for x in (
        lock.get("operations")
        or []
    )
    if isinstance(x, dict)
]

orphans = [
    dict(x)
    for x in (
        lock.get("orphans")
        or []
    )
    if isinstance(x, dict)
]


lm_orphans = [
    x
    for x in orphans
    if (
        str(
            x.get("operation_id")
            or ""
        )
        == LM_OP
        and int(
            x.get("stt")
            or 0
        )
        == LM_STT
        and str(
            (
                x.get("source_codes")
                or [""]
            )[0]
        )
        == LM_CODE
    )
]


if len(lm_orphans) != 1:
    raise RuntimeError(
        "DUNG: phai tim thay dung "
        "1 orphan Luong Minh."
    )


if any(
    str(
        x.get("operation_id")
        or ""
    )
    == LM_OP
    for x in operations
):
    raise RuntimeError(
        "DUNG: operation Luong Minh "
        "da ton tai trong operations."
    )


print()
print("=" * 126)
print("3. LUONG MINH TRUOC SUA")
print("=" * 126)

print(
    json.dumps(
        lm_orphans[0],
        ensure_ascii=False,
        indent=2,
    )
)


# ============================================================
# 4. TAO OPERATION KEEP DUNG MAU THAT
# ============================================================

keep_op = {
    "operation_id":
        LM_OP,

    "excel_plan_range":
        "F1216",

    "stt_members":
        [LM_STT],

    "commune":
        LM_COMMUNE,

    "source_schools": [
        {
            "excel_row":
                LM_ROW,

            "stt":
                LM_STT,

            "name":
                LM_NAME,

            "codes":
                [LM_CODE],

            "levels":
                ["MN"],
        }
    ],

    "source_levels":
        ["MN"],

    "official_plan":
        "Giữ nguyên",

    "target_text":
        "Giữ nguyên",

    "target_codes":
        [LM_CODE],

    "target_levels":
        ["MN"],

    "relation_type":
        "GIỮ NGUYÊN",

    "batch":
        "GIỮ NGUYÊN",
}


print()
print("=" * 126)
print("4. OPERATION KEEP SE GHI")
print("=" * 126)

print(
    json.dumps(
        keep_op,
        ensure_ascii=False,
        indent=2,
    )
)


# ============================================================
# 5. CHUYEN ORPHAN -> OPERATIONS
# ============================================================

new_orphans = [
    x
    for x in orphans
    if not (
        str(
            x.get("operation_id")
            or ""
        )
        == LM_OP
        and int(
            x.get("stt")
            or 0
        )
        == LM_STT
    )
]


insert_at = len(
    operations
)

for i, op in enumerate(
    operations
):
    if first_stt(op) > LM_STT:
        insert_at = i
        break


new_operations = (
    operations[:insert_at]
    + [keep_op]
    + operations[insert_at:]
)


lock_new = dict(lock)

lock_new[
    "operations"
] = new_operations

lock_new[
    "orphans"
] = new_orphans


# ============================================================
# 6. SUA RESOLUTION
# ============================================================

resolution = json.loads(
    RESOLUTION.read_text(
        encoding="utf-8-sig"
    )
)

if (
    str(
        resolution.get("schema")
        or ""
    )
    != "QD3805_MN_RESOLUTION_2026"
):
    raise RuntimeError(
        "DUNG: schema MN resolution sai."
    )


deferred = [
    dict(x)
    for x in (
        resolution.get(
            "deferred_orphans"
        )
        or []
    )
    if isinstance(x, dict)
]


lm_deferred = [
    x
    for x in deferred
    if (
        str(
            x.get("operation_id")
            or ""
        )
        == LM_OP
        and int(
            x.get("stt")
            or 0
        )
        == LM_STT
    )
]


if len(lm_deferred) != 1:
    raise RuntimeError(
        "DUNG: phai co dung "
        "1 deferred Luong Minh."
    )


resolution[
    "deferred_orphans"
] = [
    x
    for x in deferred
    if not (
        str(
            x.get("operation_id")
            or ""
        )
        == LM_OP
        and int(
            x.get("stt")
            or 0
        )
        == LM_STT
    )
]


confirmed = [
    dict(x)
    for x in (
        resolution.get(
            "confirmed_keep_orphans"
        )
        or []
    )
    if isinstance(x, dict)
]


if any(
    str(
        x.get("operation_id")
        or ""
    )
    == LM_OP
    for x in confirmed
):
    raise RuntimeError(
        "DUNG: confirmed KEEP "
        "Luong Minh da ton tai."
    )


confirmed.append({
    "operation_id":
        LM_OP,

    "excel_row":
        LM_ROW,

    "stt":
        LM_STT,

    "commune":
        LM_COMMUNE,

    "school":
        LM_NAME,

    "school_code":
        LM_CODE,

    "status":
        "GIỮ NGUYÊN",

    "reason":
        (
            "Đã xác nhận nghiệp vụ: "
            "ô phương án tại STT 1211 "
            "bị thiếu chữ 'Giữ nguyên'. "
            "Mầm non Lượng Minh giữ nguyên, "
            "không tham gia sáp nhập."
        ),
})


resolution[
    "confirmed_keep_orphans"
] = confirmed


# ============================================================
# 7. BACKUP
# ============================================================

stamp = datetime.now().strftime(
    "%Y%m%d_%H%M%S"
)

backup_dir = (
    ROOT
    / "backups"
    / (
        "backup_truoc_chuyen_"
        "Luong_Minh_KEEP_"
        + stamp
    )
)

backup_dir.mkdir(
    parents=True,
    exist_ok=False,
)

backup_lock = (
    backup_dir
    / LOCK.name
)

backup_resolution = (
    backup_dir
    / RESOLUTION.name
)


shutil.copy2(
    LOCK,
    backup_lock,
)

shutil.copy2(
    RESOLUTION,
    backup_resolution,
)


print()
print("=" * 126)
print("5. BACKUP")
print("=" * 126)

print(
    backup_dir
)


# ============================================================
# 8. GHI 2 JSON
# ============================================================

try:

    atomic_json(
        LOCK,
        lock_new,
    )

    atomic_json(
        RESOLUTION,
        resolution,
    )


    # Tuyệt đối không được thay DB/service/roster.
    if (
        sha256(DB)
        != EXPECTED_DB_SHA
    ):
        raise RuntimeError(
            "DB da thay doi."
        )

    if (
        sha256(SERVICE)
        != EXPECTED_SERVICE_SHA
    ):
        raise RuntimeError(
            "Service da thay doi."
        )

    if (
        sha256(ROSTER)
        != EXPECTED_ROSTER_SHA
    ):
        raise RuntimeError(
            "Roster da thay doi."
        )


    # ========================================================
    # 9. HAU KIEM FRESH PROCESS
    # ========================================================

    post = fresh_state()


    print()
    print("=" * 126)
    print("6. HAU KIEM SAU SUA")
    print("=" * 126)

    print(
        "counts                =",
        post["counts"],
    )

    print(
        "candidate_count       =",
        post[
            "candidate_count"
        ],
    )

    print(
        "effective_block_count =",
        post[
            "effective_block_count"
        ],
    )

    print(
        "ready_for_execution   =",
        post[
            "ready_for_execution"
        ],
    )

    print(
        "previous_batch        =",
        post[
            "previous_batch"
        ],
    )

    print(
        "extra_blockers        =",
        post[
            "extra_blockers"
        ],
    )

    print(
        "overlap_items         =",
        post[
            "overlap_items"
        ],
    )

    print(
        "registry summary      =",
        post[
            "registry_summary"
        ],
    )

    print(
        "mapped_keep_count     =",
        post[
            "mapped_keep_count"
        ],
    )

    print(
        "expected_keep_count   =",
        post[
            "expected_keep_count"
        ],
    )

    print(
        "missing_keep_ops      =",
        [
            x.get(
                "operation_id"
            )
            for x in (
                post[
                    "missing_keep_ops"
                ]
                or []
            )
        ],
    )

    print(
        "READY OPS             =",
        post[
            "ready_ops"
        ],
    )

    print(
        "batch_fingerprint MOI =",
        post[
            "batch_fingerprint"
        ],
    )


    # ========================================================
    # 10. EXACT GATES
    # ========================================================

    if post["counts"] != {
        "KEEP": 52,
        "DONE": 184,
        "READY": 5,
        "BLOCK": 0,
    }:
        raise RuntimeError(
            "KPI sau sua khong dung "
            "52/184/5/0."
        )


    summary = (
        post[
            "registry_summary"
        ]
        or {}
    )


    if (
        int(
            summary.get(
                "action_count"
            )
            or 0
        )
        != 189
    ):
        raise RuntimeError(
            "action_count != 189."
        )


    if (
        int(
            summary.get(
                "keep_count"
            )
            or 0
        )
        != 52
    ):
        raise RuntimeError(
            "keep_count != 52."
        )


    if (
        int(
            summary.get(
                "special_count"
            )
            or 0
        )
        != 3
    ):
        raise RuntimeError(
            "special_count != 3."
        )


    if (
        int(
            summary.get(
                "unresolved_count"
            )
            or 0
        )
        != 0
    ):
        raise RuntimeError(
            "unresolved_count != 0."
        )


    if (
        post[
            "candidate_count"
        ]
        != 5
    ):
        raise RuntimeError(
            "candidate_count != 5."
        )


    if (
        post[
            "effective_block_count"
        ]
        != 0
    ):
        raise RuntimeError(
            "effective_block_count != 0."
        )


    if (
        post[
            "ready_for_execution"
        ]
        is not True
    ):
        raise RuntimeError(
            "ready_for_execution != True."
        )


    if (
        post[
            "previous_batch"
        ]
        is not None
    ):
        raise RuntimeError(
            "Da phat sinh batch log."
        )


    if post[
        "extra_blockers"
    ]:
        raise RuntimeError(
            "Con extra blocker."
        )


    if post[
        "overlap_items"
    ]:
        raise RuntimeError(
            "Co overlap."
        )


    if (
        set(
            post[
                "ready_ops"
            ]
        )
        != READY_EXPECTED
    ):
        raise RuntimeError(
            "Danh sach 5 READY "
            "da thay doi."
        )


    if (
        post[
            "states"
        ].get(
            "QD3805-OP-0337"
        )
        != "DONE"
    ):
        raise RuntimeError(
            "OP-0337 khong con DONE."
        )


    if (
        post[
            "states"
        ].get(
            "QD3805-OP-0338"
        )
        != "DONE"
    ):
        raise RuntimeError(
            "OP-0338 khong con DONE."
        )


    if post[
        "missing_action_ops"
    ]:
        raise RuntimeError(
            "Phat sinh missing action."
        )


    # KEEP Lượng Minh có thể không có plan nội bộ riêng
    # vì dòng gốc bị thiếu ô phương án.
    # Chấp nhận:
    #  - không missing KEEP;
    #  - hoặc chỉ duy nhất Lượng Minh missing KEEP.
    missing_keep_ids = {
        str(
            x.get(
                "operation_id"
            )
            or ""
        )
        for x in (
            post[
                "missing_keep_ops"
            ]
            or []
        )
    }


    if missing_keep_ids not in (
        set(),
        {LM_OP},
    ):
        raise RuntimeError(
            "Phat sinh missing KEEP "
            "ngoai Luong Minh: "
            + repr(
                missing_keep_ids
            )
        )


    new_fp = str(
        post[
            "batch_fingerprint"
        ]
        or ""
    )


    if (
        not new_fp
        or new_fp
        == OLD_BATCH_FP
    ):
        raise RuntimeError(
            "Batch fingerprint "
            "chua doi."
        )


    # ========================================================
    # 11. KIEM TRA JSON THAT
    # ========================================================

    lock_check = json.loads(
        LOCK.read_text(
            encoding="utf-8-sig"
        )
    )


    ops_check = [
        x
        for x in (
            lock_check.get(
                "operations"
            )
            or []
        )
        if isinstance(x, dict)
        and str(
            x.get(
                "operation_id"
            )
            or ""
        )
        == LM_OP
    ]


    orphan_check = [
        x
        for x in (
            lock_check.get(
                "orphans"
            )
            or []
        )
        if isinstance(x, dict)
        and str(
            x.get(
                "operation_id"
            )
            or ""
        )
        == LM_OP
    ]


    if len(
        ops_check
    ) != 1:
        raise RuntimeError(
            "Luong Minh khong co "
            "dung 1 KEEP operation."
        )


    if orphan_check:
        raise RuntimeError(
            "Luong Minh van con "
            "trong orphans."
        )


    op = ops_check[0]


    if (
        op.get("batch")
        != "GIỮ NGUYÊN"
        or op.get(
            "relation_type"
        )
        != "GIỮ NGUYÊN"
        or op.get(
            "official_plan"
        )
        != "Giữ nguyên"
        or op.get(
            "target_codes"
        )
        != [LM_CODE]
    ):
        raise RuntimeError(
            "KEEP operation Luong Minh "
            "khong dung schema."
        )


    # ========================================================
    # 12. FINAL HASH
    # ========================================================

    after = {
        "db":
            sha256(DB),

        "service":
            sha256(SERVICE),

        "lock":
            sha256(LOCK),

        "resolution":
            sha256(
                RESOLUTION
            ),

        "roster":
            sha256(ROSTER),
    }


    if (
        after["db"]
        != EXPECTED_DB_SHA
    ):
        raise RuntimeError(
            "DB SHA da doi."
        )


    if (
        after["service"]
        != EXPECTED_SERVICE_SHA
    ):
        raise RuntimeError(
            "Service SHA da doi."
        )


    if (
        after["roster"]
        != EXPECTED_ROSTER_SHA
    ):
        raise RuntimeError(
            "Roster SHA da doi."
        )


    # ========================================================
    # 13. REPORT
    # ========================================================

    report_dir = (
        ROOT
        / "exports"
        / "Sua_Luong_Minh_KEEP"
    )

    report_dir.mkdir(
        parents=True,
        exist_ok=True,
    )


    report_path = (
        report_dir
        / (
            "ket_qua_sua_Luong_Minh_KEEP_"
            + stamp
            + ".json"
        )
    )


    report = {
        "status":
            "SUCCESS",

        "decision":
            "GIU_NGUYEN",

        "operation_id":
            LM_OP,

        "stt":
            LM_STT,

        "school_code":
            LM_CODE,

        "database_changed":
            False,

        "service_changed":
            False,

        "old_batch_fingerprint":
            OLD_BATCH_FP,

        "new_batch_fingerprint":
            new_fp,

        "before_hash":
            before,

        "after_hash":
            after,

        "preview_before":
            baseline,

        "preview_after":
            post,

        "backup":
            str(
                backup_dir
            ),
    }


    atomic_json(
        report_path,
        report,
    )


    print()
    print("=" * 126)
    print(
        "LUONG MINH = GIU NGUYEN: THANH CONG"
    )
    print("=" * 126)

    print(
        "KEEP           : 51 -> 52"
    )

    print(
        "DONE           : 184"
    )

    print(
        "READY          : 5"
    )

    print(
        "BLOCK          : 0"
    )

    print(
        "Unresolved     : 1 -> 0"
    )

    print(
        "Special        : 4 -> 3"
    )

    print(
        "Luong Minh     : GIU NGUYEN"
    )

    print(
        "5 READY        : CHUA THUC HIEN"
    )

    print(
        "OP-0337/0338   : DONE"
    )

    print(
        "Database       : KHONG THAY DOI"
    )

    print(
        "Service        : KHONG THAY DOI"
    )

    print(
        "Roster         : KHONG THAY DOI"
    )

    print(
        "Level lock SHA moi   :",
        after["lock"],
    )

    print(
        "Resolution SHA moi   :",
        after[
            "resolution"
        ],
    )

    print(
        "Batch fingerprint moi:",
        new_fp,
    )

    print(
        "Backup:",
        backup_dir,
    )

    print(
        "Report:",
        report_path,
    )

    print("=" * 126)


except Exception:

    print()
    print("=" * 126)
    print(
        "LOI - TU DONG KHOI PHUC 2 JSON"
    )
    print("=" * 126)

    shutil.copy2(
        backup_lock,
        LOCK,
    )

    shutil.copy2(
        backup_resolution,
        RESOLUTION,
    )

    print(
        "Level lock : DA KHOI PHUC"
    )

    print(
        "Resolution : DA KHOI PHUC"
    )

    print(
        "DB SHA     :",
        sha256(DB),
    )

    print(
        "Service SHA:",
        sha256(SERVICE),
    )

    print(
        "Lock SHA   :",
        sha256(LOCK),
    )

    print(
        "Resolution :",
        sha256(RESOLUTION),
    )

    raise
