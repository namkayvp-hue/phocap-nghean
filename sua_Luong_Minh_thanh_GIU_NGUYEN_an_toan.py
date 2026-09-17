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

LEVEL_LOCK = (
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

EXPECTED_LEVEL_LOCK_SHA = (
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

READY_EXPECTED = {
    "QD3805-OP-0175",
    "QD3805-OP-0410",
    "QD3805-OP-0449",
    "QD3805-OP-0592",
    "QD3805-OP-0600",
}

LM_OP = "QD3805-ORPHAN-R1216"
LM_STT = 1211
LM_CODE = "40418311"


def sha256(path):
    h = hashlib.sha256()

    with path.open("rb") as f:
        for block in iter(
            lambda: f.read(1024 * 1024),
            b"",
        ):
            h.update(block)

    return h.hexdigest()


def atomic_write_text(path, text):
    tmp = path.with_name(
        path.name + ".tmp_luong_minh_keep"
    )

    tmp.write_text(
        text,
        encoding="utf-8",
    )

    os.replace(
        tmp,
        path,
    )


def atomic_write_json(path, payload):
    atomic_write_text(
        path,
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
    )


def fresh_preview():
    code = r'''
import json

from app.services.school_merger_level_batch_service import (
    build_level_batch_preview,
    registry_level_summary,
)

p = build_level_batch_preview(
    school_year_id=2,
    level_code="MN",
)

s = registry_level_summary("MN")

states = {}
ready = []

for row in p.get("rows") or []:
    if not isinstance(row, dict):
        continue

    op = str(
        row.get("qd3805_operation_id")
        or ""
    )

    state = str(
        row.get("batch_state")
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

    "all_done":
        p.get("all_done"),

    "previous_batch":
        p.get("previous_batch"),

    "extra_blockers":
        p.get("extra_blockers") or [],

    "overlap_items":
        p.get("overlap_items") or [],

    "batch_fingerprint":
        p.get("batch_fingerprint"),

    "states":
        states,

    "ready_ops":
        sorted(ready),

    "registry_summary":
        s,

    "resolution":
        p.get("resolution") or {},
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
            "Fresh preview bị lỗi."
        )

    return json.loads(
        proc.stdout.strip()
    )


print("=" * 126)
print(
    "SUA CHINH THUC MAM NON LUONG MINH = GIU NGUYEN"
)
print("=" * 126)

print(
    "CHI SUA:"
)
print(
    " - school_merger_level_batch_service.py"
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
    " - qd3805_level_lock.json"
)
print(
    " - MN roster"
)
print(
    " - truong Mầm non Lượng Minh"
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

    "level_lock":
        sha256(LEVEL_LOCK),

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

    "level_lock":
        EXPECTED_LEVEL_LOCK_SHA,

    "resolution":
        EXPECTED_RESOLUTION_SHA,

    "roster":
        EXPECTED_ROSTER_SHA,
}


for key in expected:
    if before[key] != expected[key]:
        raise RuntimeError(
            "DUNG: "
            + key
            + " khong dung nen da khoa."
        )


# ============================================================
# 2. BASELINE
# ============================================================

baseline = fresh_preview()


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
        "DUNG: baseline KPI khong dung."
    )

if (
    baseline[
        "batch_fingerprint"
    ]
    != OLD_BATCH_FP
):
    raise RuntimeError(
        "DUNG: fingerprint baseline "
        "khong dung."
    )

if baseline[
    "previous_batch"
] is not None:
    raise RuntimeError(
        "DUNG: MN da co batch log."
    )


# ============================================================
# 3. KIEM TRA LEVEL LOCK GOC
# ============================================================

lock_payload = json.loads(
    LEVEL_LOCK.read_text(
        encoding="utf-8-sig"
    )
)

orphans = [
    x
    for x in (
        lock_payload.get(
            "orphans"
        )
        or []
    )
    if isinstance(x, dict)
]


lm_lock = [
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


if len(lm_lock) != 1:
    raise RuntimeError(
        "DUNG: khong tim thay dung "
        "1 orphan Luong Minh."
    )


print()
print("=" * 126)
print("3. LEVEL LOCK GOC")
print("=" * 126)

print(
    json.dumps(
        lm_lock[0],
        ensure_ascii=False,
        indent=2,
    )
)

print()
print(
    "Level lock se GIU NGUYEN "
    "khong sua."
)


# ============================================================
# 4. PATCH RESOLUTION
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
        "DUNG: sai schema MN resolution."
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
        int(
            x.get("stt")
            or 0
        )
        == LM_STT
        and str(
            x.get("operation_id")
            or ""
        )
        == LM_OP
    )
]


if len(lm_deferred) != 1:
    raise RuntimeError(
        "DUNG: can dung 1 deferred "
        "Luong Minh truoc khi chuyen KEEP."
    )


deferred = [
    x
    for x in deferred
    if not (
        int(
            x.get("stt")
            or 0
        )
        == LM_STT
        and str(
            x.get("operation_id")
            or ""
        )
        == LM_OP
    )
]


confirmed_keep = [
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
    (
        int(
            x.get("stt")
            or 0
        )
        == LM_STT
        or str(
            x.get("operation_id")
            or ""
        )
        == LM_OP
    )
    for x in confirmed_keep
):
    raise RuntimeError(
        "DUNG: Luong Minh da co "
        "trong confirmed_keep_orphans."
    )


confirmed_keep.append({
    "stt":
        1211,

    "excel_row":
        1216,

    "operation_id":
        LM_OP,

    "commune":
        "Lượng Minh",

    "school":
        "Mầm non Lượng Minh",

    "school_code":
        LM_CODE,

    "source_levels":
        ["MN"],

    "batch":
        "GIỮ NGUYÊN",

    "status":
        "GIỮ NGUYÊN",

    "display_title":
        "Mầm non Lượng Minh – Giữ nguyên",

    "reason":
        (
            "Đã xác nhận nghiệp vụ: "
            "ô phương án của dòng STT 1211 "
            "bị thiếu chữ 'Giữ nguyên'. "
            "Xã Lượng Minh chỉ có một trường "
            "mầm non; trường này giữ nguyên, "
            "không tham gia sáp nhập."
        ),
})


resolution[
    "deferred_orphans"
] = deferred

resolution[
    "confirmed_keep_orphans"
] = confirmed_keep


principles = list(
    resolution.get(
        "principles"
    )
    or []
)

principle = (
    "STT 1211 – Mầm non Lượng Minh "
    "(mã 40418311) được xác nhận là GIỮ NGUYÊN; "
    "ô phương án nguồn bị thiếu chữ 'Giữ nguyên'. "
    "Không tác động dữ liệu trường."
)

if principle not in principles:
    principles.append(
        principle
    )

resolution[
    "principles"
] = principles


# ============================================================
# 5. PATCH SERVICE RẤT HẸP
# ============================================================

service_text = SERVICE.read_text(
    encoding="utf-8-sig"
)


MARK_START = (
    "# === QD3805_CONFIRMED_KEEP_ORPHANS_START ==="
)

MARK_END = (
    "# === QD3805_CONFIRMED_KEEP_ORPHANS_END ==="
)


if (
    MARK_START in service_text
    or MARK_END in service_text
):
    raise RuntimeError(
        "DUNG: marker confirmed KEEP "
        "da ton tai trong service."
    )


OLD = '''    operations = [dict(x) for x in (data.get("operations") or [])]
    orphans = [dict(x) for x in (data.get("orphans") or [])]

    rename_ids = {
'''


NEW = '''    operations = [dict(x) for x in (data.get("operations") or [])]
    orphans = [dict(x) for x in (data.get("orphans") or [])]

    # === QD3805_CONFIRMED_KEEP_ORPHANS_START ===
    # Một số dòng nguồn có ô phương án bị thiếu nội dung nhưng đã được
    # xác nhận nghiệp vụ riêng trong resolution. Chỉ các dòng được liệt kê
    # tường minh tại confirmed_keep_orphans mới được chuyển từ orphan sang
    # GIỮ NGUYÊN; tuyệt đối không suy đoán các orphan khác.
    confirmed_keep_rules = [
        dict(x)
        for x in (
            resolution.get("confirmed_keep_orphans")
            or []
        )
        if isinstance(x, dict)
    ]

    confirmed_keep_by_id = {
        str(x.get("operation_id") or ""): x
        for x in confirmed_keep_rules
        if str(x.get("operation_id") or "")
    }

    confirmed_keep_operations = []
    remaining_orphans = []

    for raw_orphan in orphans:
        orphan = dict(raw_orphan)
        orphan_id = str(
            orphan.get("operation_id")
            or ""
        )

        rule = confirmed_keep_by_id.get(
            orphan_id
        )

        if rule is None:
            remaining_orphans.append(
                orphan
            )
            continue

        if (
            _safe_int(orphan.get("stt"))
            != _safe_int(rule.get("stt"))
        ):
            raise SchoolMergerLevelBatchError(
                "Resolution GIỮ NGUYÊN không khớp STT "
                f"của {orphan_id}."
            )

        source_codes = [
            str(x or "").strip()
            for x in (
                orphan.get("source_codes")
                or []
            )
            if str(x or "").strip()
        ]

        expected_code = str(
            rule.get("school_code")
            or ""
        ).strip()

        if (
            expected_code
            and expected_code not in source_codes
        ):
            raise SchoolMergerLevelBatchError(
                "Resolution GIỮ NGUYÊN không khớp mã trường "
                f"của {orphan_id}."
            )

        source_levels = [
            str(x or "").strip().upper()
            for x in (
                orphan.get("source_levels")
                or []
            )
            if str(x or "").strip()
        ]

        if source_levels != [level]:
            raise SchoolMergerLevelBatchError(
                "Resolution GIỮ NGUYÊN không khớp cấp học "
                f"của {orphan_id}."
            )

        item = dict(orphan)

        item["batch"] = "GIỮ NGUYÊN"
        item["status"] = "GIỮ NGUYÊN"
        item["relation_type"] = "GIỮ NGUYÊN"
        item["official_plan"] = "Giữ nguyên"
        item["target_level"] = level
        item["target_code"] = expected_code
        item["resolution_note"] = str(
            rule.get("reason")
            or ""
        )

        confirmed_keep_operations.append(
            item
        )

    operations.extend(
        confirmed_keep_operations
    )

    orphans = remaining_orphans
    # === QD3805_CONFIRMED_KEEP_ORPHANS_END ===

    rename_ids = {
'''


if service_text.count(OLD) != 1:
    raise RuntimeError(
        "DUNG: khong tim thay dung 1 "
        "vi tri patch trong service."
    )


service_new = service_text.replace(
    OLD,
    NEW,
    1,
)


# ============================================================
# 6. BACKUP
# ============================================================

stamp = datetime.now().strftime(
    "%Y%m%d_%H%M%S"
)

backup_dir = (
    ROOT
    / "backups"
    / (
        "backup_truoc_sua_Luong_Minh_"
        "GIU_NGUYEN_"
        + stamp
    )
)

backup_dir.mkdir(
    parents=True,
    exist_ok=False,
)

backup_service = (
    backup_dir
    / SERVICE.name
)

backup_resolution = (
    backup_dir
    / RESOLUTION.name
)

shutil.copy2(
    SERVICE,
    backup_service,
)

shutil.copy2(
    RESOLUTION,
    backup_resolution,
)


print()
print("=" * 126)
print("4. BACKUP")
print("=" * 126)

print(
    backup_dir
)


# ============================================================
# 7. GHI SERVICE + RESOLUTION
# ============================================================

try:

    atomic_write_text(
        SERVICE,
        service_new,
    )

    atomic_write_json(
        RESOLUTION,
        resolution,
    )


    # Compile service.
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "py_compile",
            str(SERVICE),
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
            "py_compile service FAIL."
        )


    # Các file không được phép đổi.
    if sha256(DB) != EXPECTED_DB_SHA:
        raise RuntimeError(
            "DB da thay doi."
        )

    if (
        sha256(LEVEL_LOCK)
        != EXPECTED_LEVEL_LOCK_SHA
    ):
        raise RuntimeError(
            "Level lock da thay doi."
        )

    if (
        sha256(ROSTER)
        != EXPECTED_ROSTER_SHA
    ):
        raise RuntimeError(
            "MN roster da thay doi."
        )


    # ========================================================
    # 8. HAU KIEM FRESH PROCESS
    # ========================================================

    post = fresh_preview()

    print()
    print("=" * 126)
    print("5. HAU KIEM SAU SUA")
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
        "batch_fingerprint MOI =",
        post[
            "batch_fingerprint"
        ],
    )

    print(
        "registry summary      =",
        post[
            "registry_summary"
        ],
    )

    print(
        "READY OPS             =",
        post[
            "ready_ops"
        ],
    )


    # ========================================================
    # 9. EXACT GATES
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
            "Da phat sinh batch log "
            "ngoai du kien."
        )

    if post[
        "extra_blockers"
    ]:
        raise RuntimeError(
            "Van con extra blocker."
        )

    if post[
        "overlap_items"
    ]:
        raise RuntimeError(
            "Co overlap ngoai du kien."
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
            "5 READY bi thay doi."
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


    summary = (
        post[
            "registry_summary"
        ]
        or {}
    )

    if int(
        summary.get(
            "keep_count"
        )
        or 0
    ) != 52:
        raise RuntimeError(
            "Registry keep_count != 52."
        )

    if int(
        summary.get(
            "unresolved_count"
        )
        or 0
    ) != 0:
        raise RuntimeError(
            "Registry unresolved_count != 0."
        )


    # Resolution phải không còn deferred LM.
    r_after = (
        post.get(
            "resolution"
        )
        or {}
    )

    deferred_after = (
        r_after.get(
            "deferred_orphans"
        )
        or []
    )

    if any(
        int(
            x.get("stt")
            or 0
        )
        == LM_STT
        for x in deferred_after
        if isinstance(x, dict)
    ):
        raise RuntimeError(
            "Luong Minh van con deferred."
        )


    keep_after = (
        r_after.get(
            "confirmed_keep_orphans"
        )
        or []
    )

    if not any(
        (
            str(
                x.get("operation_id")
                or ""
            )
            == LM_OP
            and str(
                x.get("school_code")
                or ""
            )
            == LM_CODE
        )
        for x in keep_after
        if isinstance(x, dict)
    ):
        raise RuntimeError(
            "Resolution khong co "
            "confirmed KEEP Luong Minh."
        )


    # Fingerprint bắt buộc phải đổi.
    new_fp = str(
        post[
            "batch_fingerprint"
        ]
        or ""
    )

    if (
        not new_fp
        or new_fp == OLD_BATCH_FP
    ):
        raise RuntimeError(
            "Batch fingerprint chua doi "
            "sau thay doi nghiep vu."
        )


    # ========================================================
    # 10. FINAL HASH
    # ========================================================

    after = {
        "db":
            sha256(DB),

        "service":
            sha256(SERVICE),

        "level_lock":
            sha256(LEVEL_LOCK),

        "resolution":
            sha256(RESOLUTION),

        "roster":
            sha256(ROSTER),
    }


    if after["db"] != EXPECTED_DB_SHA:
        raise RuntimeError(
            "DB SHA da doi."
        )

    if (
        after[
            "level_lock"
        ]
        != EXPECTED_LEVEL_LOCK_SHA
    ):
        raise RuntimeError(
            "Level lock SHA da doi."
        )

    if (
        after[
            "roster"
        ]
        != EXPECTED_ROSTER_SHA
    ):
        raise RuntimeError(
            "Roster SHA da doi."
        )


    # ========================================================
    # 11. REPORT
    # ========================================================

    report_dir = (
        ROOT
        / "exports"
        / "Sua_Luong_Minh_Giu_Nguyen"
    )

    report_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    report_path = (
        report_dir
        / (
            "ket_qua_sua_Luong_Minh_Giu_Nguyen_"
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

        "level_lock_changed":
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

    atomic_write_json(
        report_path,
        report,
    )


    print()
    print("=" * 126)
    print(
        "SUA LUONG MINH = GIU NGUYEN: THANH CONG"
    )
    print("=" * 126)

    print(
        "Luong Minh     : GIU NGUYEN"
    )

    print(
        "KEEP           : 51 -> 52"
    )

    print(
        "Unresolved     : 1 -> 0"
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
        "5 READY        : CHUA THUC HIEN"
    )

    print(
        "OP-0337/0338   : DONE - KHONG CHAY LAI"
    )

    print(
        "Database       : KHONG THAY DOI"
    )

    print(
        "Level lock goc : KHONG THAY DOI"
    )

    print(
        "Batch FP CU    :",
        OLD_BATCH_FP,
    )

    print(
        "Batch FP MOI   :",
        new_fp,
    )

    print()
    print(
        "Service SHA moi   :",
        after[
            "service"
        ],
    )

    print(
        "Resolution SHA moi:",
        after[
            "resolution"
        ],
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
        "LOI - DANG KHOI PHUC SERVICE + RESOLUTION"
    )
    print("=" * 126)

    shutil.copy2(
        backup_service,
        SERVICE,
    )

    shutil.copy2(
        backup_resolution,
        RESOLUTION,
    )

    print(
        "Service    : DA KHOI PHUC"
    )

    print(
        "Resolution : DA KHOI PHUC"
    )

    print(
        "DB SHA     :",
        sha256(DB),
    )

    print(
        "Level lock :",
        sha256(LEVEL_LOCK),
    )

    print(
        "Roster     :",
        sha256(ROSTER),
    )

    raise
