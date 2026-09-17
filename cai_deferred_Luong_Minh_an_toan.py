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

EXPECTED_RESOLUTION_SHA = (
    "f1e84b3c1045171bccd1265989fbe7ad"
    "2b9719b84f27d71792670633e796b798"
)

EXPECTED_ROSTER_SHA = (
    "ef865f74aa51c2700ceb7746d5433b63"
    "fc6a52a4e3169014ebe0e446ac441120"
)

READY_OPS = {
    "QD3805-OP-0175",
    "QD3805-OP-0410",
    "QD3805-OP-0449",
    "QD3805-OP-0592",
    "QD3805-OP-0600",
}

OP0337 = "QD3805-OP-0337"
OP0338 = "QD3805-OP-0338"


LUONG_MINH_RULE = {
    "stt": 1211,

    "excel_row": 1216,

    "operation_id":
        "QD3805-ORPHAN-R1216",

    "commune":
        "Lượng Minh",

    "school":
        "Mầm non Lượng Minh",

    "school_code":
        "40418311",

    "status":
        (
            "CHỜ XÁC NHẬN – KHÔNG TÁC ĐỘNG "
            "TRONG SÁP NHẬP TOÀN CẤP"
        ),

    "display_title":
        (
            "STT 1211 – Mầm non Lượng Minh – "
            "chưa có phương án/ghi chú đủ rõ"
        ),

    "reason":
        (
            "Dòng QĐ3805/nguồn phương án không có "
            "phương án hoặc ghi chú đủ rõ để xác định "
            "nguồn → đích. Không tự suy đoán. "
            "Giữ nguyên dữ liệu hiện có, không đưa "
            "trường này vào batch sáp nhập tự động; "
            "chờ xác nhận nghiệp vụ riêng nếu có."
        ),
}


def sha256(path):
    h = hashlib.sha256()

    with path.open("rb") as f:
        while True:
            b = f.read(1024 * 1024)

            if not b:
                break

            h.update(b)

    return h.hexdigest()


def atomic_write_json(
    path,
    payload,
):

    tmp = path.with_name(
        path.name
        + ".tmp_luong_minh"
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


def run_preview(level):

    child = r'''
import json
import sys

from app.services.school_merger_level_batch_service import (
    build_level_batch_preview,
)

level = sys.argv[1]

preview = build_level_batch_preview(
    school_year_id=2,
    level_code=level,
)

states = {}

ready_ops = []

for row in (
    preview.get("rows")
    or []
):
    if not isinstance(row, dict):
        continue

    op = str(
        row.get(
            "qd3805_operation_id"
        )
        or ""
    ).strip()

    state = str(
        row.get(
            "batch_state"
        )
        or ""
    ).upper().strip()

    if op:
        states[op] = state

    if state == "READY":
        ready_ops.append(op)

print(
    json.dumps(
        {
            "counts":
                preview.get("counts")
                or {},

            "candidate_count":
                preview.get(
                    "candidate_count"
                ),

            "effective_block_count":
                preview.get(
                    "effective_block_count"
                ),

            "ready_for_execution":
                preview.get(
                    "ready_for_execution"
                ),

            "all_done":
                preview.get(
                    "all_done"
                ),

            "states":
                states,

            "ready_ops":
                sorted(ready_ops),

            "extra_blockers":
                preview.get(
                    "extra_blockers"
                )
                or [],

            "resolution":
                preview.get(
                    "resolution"
                )
                or {},
        },
        ensure_ascii=True,
        default=str,
    )
)
'''

    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            child,
            level,
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
            f"Preview {level} bi loi."
        )

    return json.loads(
        proc.stdout.strip()
    )


print("=" * 120)
print("CAI CHINH THUC DEFERRED - MAM NON LUONG MINH")
print("STT 1211 / QD3805-ORPHAN-R1216")
print("=" * 120)

print()
print("CHI SUA:")
print(" - qd3805_mn_resolution.json")

print()
print("KHONG SUA:")
print(" - phocap.db")
print(" - school_merger_level_batch_service.py")
print(" - MN_2025_2026.json")
print(" - du lieu Mầm non Lượng Minh")
print(" - 5 phuong an READY")
print("=" * 120)


# ============================================================
# 1. HASH GATE
# ============================================================

before = {
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
print(
    "DB SHA         :",
    before["db"],
)

print(
    "Service SHA    :",
    before["service"],
)

print(
    "Resolution SHA :",
    before["resolution"],
)

print(
    "Roster SHA     :",
    before["roster"],
)


expected = {
    "db":
        EXPECTED_DB_SHA,

    "service":
        EXPECTED_SERVICE_SHA,

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
            + " da thay doi ngoai du kien."
        )


# ============================================================
# 2. BASELINE
# ============================================================

print()
print("=" * 120)
print("PREVIEW TRUOC CAI")
print("=" * 120)

mn_before = run_preview("MN")
th_before = run_preview("TH")

print(
    "MN:",
    mn_before["counts"],
)

print(
    "candidate_count       =",
    mn_before["candidate_count"],
)

print(
    "effective_block_count =",
    mn_before[
        "effective_block_count"
    ],
)

print(
    "ready_for_execution   =",
    mn_before[
        "ready_for_execution"
    ],
)

print(
    "TH:",
    th_before["counts"],
)


if mn_before["counts"] != {
    "KEEP": 51,
    "DONE": 184,
    "READY": 5,
    "BLOCK": 0,
}:
    raise RuntimeError(
        "DUNG: MN baseline khong dung."
    )

if (
    mn_before[
        "candidate_count"
    ]
    != 5
):
    raise RuntimeError(
        "DUNG: candidate_count baseline != 5."
    )

if (
    mn_before[
        "effective_block_count"
    ]
    != 1
):
    raise RuntimeError(
        "DUNG: effective_block_count baseline != 1."
    )

if (
    mn_before[
        "ready_for_execution"
    ]
    is not False
):
    raise RuntimeError(
        "DUNG: baseline phai chua san sang."
    )

block_text = json.dumps(
    mn_before.get(
        "extra_blockers"
    )
    or [],
    ensure_ascii=False,
)

if "Lượng Minh" not in block_text:
    raise RuntimeError(
        "DUNG: khong con blocker Luong Minh "
        "tai baseline."
    )


# ============================================================
# 3. DOC + KIEM TRA RESOLUTION
# ============================================================

payload = json.loads(
    RESOLUTION.read_text(
        encoding="utf-8-sig",
    )
)

if (
    str(
        payload.get("schema")
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
        payload.get(
            "deferred_orphans"
        )
        or []
    )
    if isinstance(x, dict)
]


if any(
    int(
        x.get("stt")
        or 0
    ) == 1211
    for x in deferred
):
    raise RuntimeError(
        "DUNG: STT 1211 da ton tai "
        "trong deferred_orphans."
    )


# Bảo vệ OP-0337 / OP-0338.
precompleted_ids = {
    str(
        x.get(
            "operation_id"
        )
        or ""
    )
    for x in (
        payload.get(
            "precompleted"
        )
        or []
    )
    if isinstance(x, dict)
}

if OP0337 not in precompleted_ids:
    raise RuntimeError(
        "DUNG: OP-0337 bi mat "
        "khoi precompleted."
    )

if OP0338 not in precompleted_ids:
    raise RuntimeError(
        "DUNG: OP-0338 bi mat "
        "khoi precompleted."
    )


# ============================================================
# 4. TAO PAYLOAD MOI
# ============================================================

deferred.append(
    dict(LUONG_MINH_RULE)
)

payload[
    "deferred_orphans"
] = deferred


principles = list(
    payload.get(
        "principles"
    )
    or []
)

principle = (
    "Dòng QĐ3805 chưa có phương án/ghi chú "
    "đủ rõ không được tự suy đoán nguồn → đích. "
    "Có thể đưa vào deferred_orphans để loại khỏi "
    "batch tự động nhưng vẫn giữ trạng thái chờ "
    "xác nhận nghiệp vụ riêng."
)

if principle not in principles:
    principles.append(
        principle
    )

payload[
    "principles"
] = principles


# ============================================================
# 5. BACKUP
# ============================================================

stamp = datetime.now().strftime(
    "%Y%m%d_%H%M%S"
)

backup_dir = (
    ROOT
    / "backups"
    / (
        "backup_truoc_defer_"
        "Luong_Minh_"
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
print(
    "Backup:",
    backup_dir,
)


# ============================================================
# 6. INSTALL
# ============================================================

try:

    atomic_write_json(
        RESOLUTION,
        payload,
    )

    # DB / service / roster must remain unchanged.
    if sha256(DB) != EXPECTED_DB_SHA:
        raise RuntimeError(
            "DB thay doi trong luc cai."
        )

    if (
        sha256(SERVICE)
        != EXPECTED_SERVICE_SHA
    ):
        raise RuntimeError(
            "Service thay doi trong luc cai."
        )

    if (
        sha256(ROSTER)
        != EXPECTED_ROSTER_SHA
    ):
        raise RuntimeError(
            "Roster thay doi trong luc cai."
        )


    # ========================================================
    # 7. HAU KIEM FRESH PROCESS
    # ========================================================

    print()
    print("=" * 120)
    print("HAU KIEM SAU CAI")
    print("=" * 120)

    mn_after = run_preview("MN")
    th_after = run_preview("TH")

    print(
        "MN:",
        mn_after["counts"],
    )

    print(
        "candidate_count       =",
        mn_after[
            "candidate_count"
        ],
    )

    print(
        "effective_block_count =",
        mn_after[
            "effective_block_count"
        ],
    )

    print(
        "ready_for_execution   =",
        mn_after[
            "ready_for_execution"
        ],
    )

    print()
    print(
        "OP-0337 =",
        mn_after[
            "states"
        ].get(OP0337),
    )

    print(
        "OP-0338 =",
        mn_after[
            "states"
        ].get(OP0338),
    )

    print(
        "READY OPS =",
        mn_after[
            "ready_ops"
        ],
    )

    print()
    print(
        "EXTRA BLOCKERS =",
        mn_after[
            "extra_blockers"
        ],
    )


    # ========================================================
    # 8. EXACT EXPECTED
    # ========================================================

    if mn_after["counts"] != {
        "KEEP": 51,
        "DONE": 184,
        "READY": 5,
        "BLOCK": 0,
    }:
        raise RuntimeError(
            "KPI MN sau cai sai."
        )

    if (
        mn_after[
            "candidate_count"
        ]
        != 5
    ):
        raise RuntimeError(
            "candidate_count != 5."
        )

    if (
        mn_after[
            "effective_block_count"
        ]
        != 0
    ):
        raise RuntimeError(
            "effective_block_count != 0."
        )

    if (
        mn_after[
            "ready_for_execution"
        ]
        is not True
    ):
        raise RuntimeError(
            "ready_for_execution chua True."
        )

    if (
        mn_after[
            "states"
        ].get(OP0337)
        != "DONE"
    ):
        raise RuntimeError(
            "OP-0337 khong con DONE."
        )

    if (
        mn_after[
            "states"
        ].get(OP0338)
        != "DONE"
    ):
        raise RuntimeError(
            "OP-0338 khong con DONE."
        )

    if (
        set(
            mn_after[
                "ready_ops"
            ]
        )
        != READY_OPS
    ):
        raise RuntimeError(
            "Danh sach 5 READY bi thay doi."
        )

    if mn_after[
        "extra_blockers"
    ]:
        raise RuntimeError(
            "Van con extra blocker."
        )


    # ========================================================
    # 9. XAC NHAN DEFERRED DA NAP
    # ========================================================

    resolution_after = (
        mn_after.get(
            "resolution"
        )
        or {}
    )

    deferred_after = [
        dict(x)
        for x in (
            resolution_after.get(
                "deferred_orphans"
            )
            or []
        )
        if isinstance(x, dict)
    ]

    lm = next(
        (
            x
            for x in deferred_after
            if int(
                x.get("stt")
                or 0
            ) == 1211
        ),
        None,
    )

    if lm is None:
        raise RuntimeError(
            "Resolution sau cai "
            "khong thay STT 1211."
        )

    if str(
        lm.get(
            "operation_id"
        )
        or ""
    ) != "QD3805-ORPHAN-R1216":
        raise RuntimeError(
            "Sai operation_id Luong Minh."
        )

    if str(
        lm.get(
            "school_code"
        )
        or ""
    ) != "40418311":
        raise RuntimeError(
            "Sai ma truong Luong Minh."
        )


    # ========================================================
    # 10. TH KHONG DUOC DOI
    # ========================================================

    for key in (
        "counts",
        "candidate_count",
        "effective_block_count",
        "ready_for_execution",
    ):
        if (
            th_before.get(key)
            != th_after.get(key)
        ):
            raise RuntimeError(
                "TH thay doi ngoai du kien "
                f"tai {key}."
            )


    # ========================================================
    # 11. FINAL HASH SAFETY
    # ========================================================

    final_db = sha256(DB)
    final_service = sha256(
        SERVICE
    )
    final_roster = sha256(
        ROSTER
    )
    final_resolution = sha256(
        RESOLUTION
    )

    if final_db != EXPECTED_DB_SHA:
        raise RuntimeError(
            "DB SHA thay doi."
        )

    if (
        final_service
        != EXPECTED_SERVICE_SHA
    ):
        raise RuntimeError(
            "Service SHA thay doi."
        )

    if (
        final_roster
        != EXPECTED_ROSTER_SHA
    ):
        raise RuntimeError(
            "Roster SHA thay doi."
        )


    # ========================================================
    # 12. REPORT
    # ========================================================

    report_dir = (
        ROOT
        / "exports"
        / "Defer_Luong_Minh"
    )

    report_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    report_path = (
        report_dir
        / (
            "ket_qua_defer_"
            "Luong_Minh_"
            + stamp
            + ".json"
        )
    )

    report = {
        "status":
            "SUCCESS",

        "operation_id":
            "QD3805-ORPHAN-R1216",

        "stt":
            1211,

        "school":
            "Mầm non Lượng Minh",

        "school_code":
            "40418311",

        "decision":
            "DEFERRED",

        "executed_merger":
            False,

        "database_changed":
            False,

        "database_sha256":
            final_db,

        "service_sha256":
            final_service,

        "roster_sha256":
            final_roster,

        "resolution_sha256_before":
            before[
                "resolution"
            ],

        "resolution_sha256_after":
            final_resolution,

        "mn_before":
            mn_before,

        "mn_after":
            mn_after,

        "th_before":
            th_before,

        "th_after":
            th_after,

        "backup":
            str(
                backup_dir
            ),

        "note":
            (
                "Không tự suy đoán phương án "
                "cho Mầm non Lượng Minh. "
                "Không tác động trường trong "
                "batch toàn cấp."
            ),
    }

    atomic_write_json(
        report_path,
        report,
    )


    print()
    print("=" * 120)
    print("CAI DAT THANH CONG")
    print("=" * 120)

    print()
    print(
        "Luong Minh : DEFERRED"
    )

    print(
        "Tu dong sap nhap Luong Minh : KHONG"
    )

    print()
    print(
        "MN KPI     :",
        mn_after[
            "counts"
        ],
    )

    print(
        "Candidate  :",
        mn_after[
            "candidate_count"
        ],
    )

    print(
        "Eff block  :",
        mn_after[
            "effective_block_count"
        ],
    )

    print(
        "Ready exec :",
        mn_after[
            "ready_for_execution"
        ],
    )

    print()
    print(
        "OP-0337    : DONE - KHONG CHAY LAI"
    )

    print(
        "OP-0338    : DONE - KHONG CHAY LAI"
    )

    print(
        "5 READY    : CHUA THUC HIEN"
    )

    print(
        "TH         : KHONG THAY DOI"
    )

    print(
        "Database   : KHONG THAY DOI"
    )

    print(
        "DB SHA     :",
        final_db,
    )

    print()
    print(
        "Resolution SHA moi:",
        final_resolution,
    )

    print(
        "Backup:",
        backup_dir,
    )

    print(
        "Report:",
        report_path,
    )

    print("=" * 120)


except Exception:

    print()
    print("=" * 120)
    print(
        "CAI DAT LOI - KHOI PHUC RESOLUTION"
    )
    print("=" * 120)

    shutil.copy2(
        backup_resolution,
        RESOLUTION,
    )

    print(
        "Resolution: DA KHOI PHUC"
    )

    print(
        "DB SHA:",
        sha256(DB),
    )

    print(
        "Service SHA:",
        sha256(SERVICE),
    )

    print(
        "Roster SHA:",
        sha256(ROSTER),
    )

    raise
