from __future__ import annotations

import ast
import hashlib
import json
import os
import py_compile
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

OP0337 = "QD3805-OP-0337"
OP0338 = "QD3805-OP-0338"

EXPECTED_READY = {
    "QD3805-OP-0175",
    "QD3805-OP-0410",
    "QD3805-OP-0449",
    "QD3805-OP-0592",
    "QD3805-OP-0600",
}

EXPECTED_DB_SHA = (
    "44b1aa841cdd76301c57d9fc601121ae"
    "96f9312084ef05959eaae54acf17c8c9"
)

EXPECTED_SERVICE_SHA = (
    "2860998dbd6d14e5110e7bc64316845"
    "a9dc2aad084b36a0a09f38b79056161bc"
)

EXPECTED_RESOLUTION_SHA = (
    "eb68a6593b551b96a5112ce3a647ffe3"
    "4f55913007885f9bc541e56170291755"
)

EXPECTED_ROSTER_SHA = (
    "ef865f74aa51c2700ceb7746d5433b63"
    "fc6a52a4e3169014ebe0e446ac441120"
)

MARKER_START = (
    "# === QD3805_OP0338_PRECOMPLETED_"
    "AUDIT_GATE_START ==="
)

MARKER_END = (
    "# === QD3805_OP0338_PRECOMPLETED_"
    "AUDIT_GATE_END ==="
)


OLD_BLOCK = '''    evidence["source_audit_pass"] = bool(
        audit.get("pass")
    )

    evidence[
        "previous_target_eligible"
    ] = previous_target_eligible
'''


NEW_BLOCK = '''    # === QD3805_OP0338_PRECOMPLETED_AUDIT_GATE_START ===
    original_audit_pass = bool(
        audit.get("pass")
    )

    audit_pass_for_precompleted = (
        original_audit_pass
    )

    audit_gate_bypassed = False

    audit_blockers = [
        str(x or "").strip()
        for x in (
            audit.get("blockers")
            or []
        )
        if str(x or "").strip()
    ]

    if (
        not audit_pass_for_precompleted
        and bool(
            rule.get(
                "allow_special_audit_gate"
            )
        )
    ):
        all_school_checks_pass = (
            bool(school_checks)
            and all(
                str(
                    x.get("status")
                    or ""
                ).upper()
                == "PASS"
                for x in school_checks
            )
        )

        exact_old_mapped_gate = (
            audit_blockers
            == [
                (
                    "V4.3 chỉ mở thực hiện cho phương án "
                    "MAPPED có nguồn → đích rõ ràng."
                )
            ]
        )

        if (
            all_school_checks_pass
            and exact_old_mapped_gate
        ):
            audit_pass_for_precompleted = True
            audit_gate_bypassed = True

    evidence["source_audit_pass"] = (
        audit_pass_for_precompleted
    )

    evidence[
        "original_source_audit_pass"
    ] = original_audit_pass

    evidence[
        "special_gate_bypassed"
    ] = audit_gate_bypassed

    evidence[
        "original_audit_blockers"
    ] = audit_blockers
    # === QD3805_OP0338_PRECOMPLETED_AUDIT_GATE_END ===

    evidence[
        "previous_target_eligible"
    ] = previous_target_eligible
'''


OP0338_RULE = {
    "operation_id":
        "QD3805-OP-0338",

    "source_school_code":
        "40429323",

    "target_school_code":
        "40429301",

    "previous_year_code":
        "2025-2026",

    "current_year_code":
        "2026-2027",

    "expected_previous_target_active":
        31,

    "expected_previous_source_active":
        41,

    "expected_current_target_active":
        72,

    "expected_current_source_active":
        0,

    "expected_previous_identity_count":
        72,

    "require_identity_exact":
        True,

    "allow_special_audit_gate":
        True,

    "reason": (
        "Trường MN Nghi Trung (40429323) "
        "đã inactive; Trường Mầm non TT "
        "Quán Hành (40429301) đang active. "
        "Source audit 2025-2026 xác nhận "
        "31 hồ sơ đủ điều kiện tại đích và "
        "41 hồ sơ đủ điều kiện tại nguồn. "
        "Năm 2026-2027 tại đích có đúng "
        "72 staff_member_id và khớp 100% "
        "với union 31+41 năm trước; nguồn "
        "hiện hành bằng 0. Phương án đã "
        "hoàn tất trước, tuyệt đối không "
        "chạy lại."
    ),
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()

    with path.open("rb") as f:
        while True:
            b = f.read(
                1024 * 1024
            )

            if not b:
                break

            h.update(b)

    return h.hexdigest()


def atomic_write_text(
    path: Path,
    text: str,
) -> None:

    tmp = path.with_name(
        path.name
        + ".tmp_op0338"
    )

    tmp.write_text(
        text,
        encoding="utf-8",
    )

    os.replace(
        tmp,
        path,
    )


def atomic_write_json(
    path: Path,
    data,
) -> None:

    atomic_write_text(
        path,
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
    )


def run_preview(
    level: str,
) -> dict:

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

precompleted = {}

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

    if not op:
        continue

    states[op] = str(
        row.get(
            "batch_state"
        )
        or ""
    ).upper().strip()

    if row.get(
        "qd3805_precompleted"
    ):
        precompleted[op] = (
            row.get(
                "qd3805_precompleted"
            )
        )

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

            "states":
                states,

            "precompleted":
                precompleted,

            "extra_blockers":
                preview.get(
                    "extra_blockers"
                )
                or [],
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


def main():

    print("=" * 120)
    print(
        "CAI CHINH THUC OP-0338 = "
        "DONE - KHONG CHAY LAI"
    )
    print("=" * 120)

    print()
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
        " - MN roster"
    )
    print(
        " - truong 747 / 749"
    )
    print(
        " - tai khoan"
    )
    print(
        " - 5 phuong an READY"
    )
    print("=" * 120)

    # ========================================================
    # 1. HASH GATE
    # ========================================================

    hashes_before = {
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
        hashes_before["db"],
    )

    print(
        "Service SHA    :",
        hashes_before["service"],
    )

    print(
        "Resolution SHA :",
        hashes_before["resolution"],
    )

    print(
        "Roster SHA     :",
        hashes_before["roster"],
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
        if (
            hashes_before[key]
            != expected[key]
        ):
            raise RuntimeError(
                "DUNG: "
                + key
                + " da thay doi ngoai du kien."
            )

    # ========================================================
    # 2. BASELINE
    # ========================================================

    print()
    print("=" * 120)
    print("PREVIEW TRUOC CAI")
    print("=" * 120)

    mn_before = run_preview(
        "MN"
    )

    th_before = run_preview(
        "TH"
    )

    print(
        "MN =",
        mn_before["counts"],
    )

    print(
        "TH =",
        th_before["counts"],
    )

    if mn_before["counts"] != {
        "KEEP": 51,
        "DONE": 183,
        "READY": 5,
        "BLOCK": 1,
    }:
        raise RuntimeError(
            "DUNG: MN baseline sai."
        )

    if (
        mn_before["states"].get(
            OP0337
        )
        != "DONE"
    ):
        raise RuntimeError(
            "DUNG: OP-0337 khong con DONE."
        )

    if (
        mn_before["states"].get(
            OP0338
        )
        != "BLOCK"
    ):
        raise RuntimeError(
            "DUNG: OP-0338 khong con BLOCK "
            "tai baseline."
        )

    # ========================================================
    # 3. BUILD PATCH SERVICE
    # ========================================================

    source = SERVICE.read_text(
        encoding="utf-8-sig",
    )

    ast.parse(
        source
    )

    if MARKER_START in source:
        raise RuntimeError(
            "DUNG: marker OP-0338 "
            "da ton tai trong service."
        )

    if source.count(
        OLD_BLOCK
    ) != 1:
        raise RuntimeError(
            "DUNG: khong tim thay dung "
            "1 block source_audit_pass "
            "tren nen da kiem tra."
        )

    patched_source = source.replace(
        OLD_BLOCK,
        NEW_BLOCK,
        1,
    )

    ast.parse(
        patched_source
    )

    if (
        MARKER_START
        not in patched_source
        or MARKER_END
        not in patched_source
    ):
        raise RuntimeError(
            "Patch service thieu marker."
        )

    # ========================================================
    # 4. BUILD RESOLUTION
    # ========================================================

    resolution = json.loads(
        RESOLUTION.read_text(
            encoding="utf-8-sig",
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
            "MN resolution sai schema."
        )

    precompleted = [
        dict(x)
        for x in (
            resolution.get(
                "precompleted"
            )
            or []
        )
        if isinstance(
            x,
            dict,
        )
    ]

    existing_ids = {
        str(
            x.get(
                "operation_id"
            )
            or ""
        )
        for x in precompleted
    }

    if OP0337 not in existing_ids:
        raise RuntimeError(
            "DUNG: OP-0337 bi mat "
            "khoi precompleted."
        )

    if OP0338 in existing_ids:
        raise RuntimeError(
            "DUNG: OP-0338 da ton tai "
            "trong resolution."
        )

    precompleted.append(
        dict(OP0338_RULE)
    )

    resolution[
        "precompleted"
    ] = precompleted

    principles = list(
        resolution.get(
            "principles"
        )
        or []
    )

    principle = (
        "Phương án đã hoàn tất trước "
        "nhưng action_type nguồn cũ là SPECIAL "
        "chỉ được nhận DONE khi từng school-check "
        "PASS, blocker duy nhất là gate MAPPED cũ "
        "và toàn bộ kiểm tra số lượng/identity "
        "precompleted đều PASS."
    )

    if principle not in principles:
        principles.append(
            principle
        )

    resolution[
        "principles"
    ] = principles

    # ========================================================
    # 5. BACKUP
    # ========================================================

    stamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    backup_dir = (
        ROOT
        / "backups"
        / (
            "backup_truoc_done_OP0338_"
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
    print(
        "Backup:",
        backup_dir,
    )

    # ========================================================
    # 6. INSTALL + ROLLBACK GUARD
    # ========================================================

    try:
        atomic_write_text(
            SERVICE,
            patched_source,
        )

        py_compile.compile(
            str(SERVICE),
            doraise=True,
        )

        atomic_write_json(
            RESOLUTION,
            resolution,
        )

        # DB + roster must remain exact.
        if (
            sha256(DB)
            != EXPECTED_DB_SHA
        ):
            raise RuntimeError(
                "DB thay doi trong luc cai."
            )

        if (
            sha256(ROSTER)
            != EXPECTED_ROSTER_SHA
        ):
            raise RuntimeError(
                "MN roster thay doi."
            )

        # ====================================================
        # 7. FRESH PROCESS HAU KIEM
        # ====================================================

        print()
        print("=" * 120)
        print("HAU KIEM SAU CAI")
        print("=" * 120)

        mn_after = run_preview(
            "MN"
        )

        th_after = run_preview(
            "TH"
        )

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
            ].get(
                OP0337
            ),
        )

        print(
            "OP-0338 =",
            mn_after[
                "states"
            ].get(
                OP0338
            ),
        )

        for op in sorted(
            EXPECTED_READY
        ):
            print(
                op,
                "=",
                mn_after[
                    "states"
                ].get(op),
            )

        # ====================================================
        # 8. EXACT EXPECTED KPI
        # ====================================================

        expected_mn = {
            "KEEP": 51,
            "DONE": 184,
            "READY": 5,
            "BLOCK": 0,
        }

        if (
            mn_after["counts"]
            != expected_mn
        ):
            raise RuntimeError(
                "MN KPI sau cai sai: "
                + repr(
                    mn_after[
                        "counts"
                    ]
                )
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
            != 1
        ):
            raise RuntimeError(
                "effective_block_count != 1."
            )

        if (
            mn_after[
                "ready_for_execution"
            ]
            is not False
        ):
            raise RuntimeError(
                "ready_for_execution phai False "
                "vi con Luong Minh."
            )

        if (
            mn_after["states"].get(
                OP0337
            )
            != "DONE"
        ):
            raise RuntimeError(
                "OP-0337 khong con DONE."
            )

        if (
            mn_after["states"].get(
                OP0338
            )
            != "DONE"
        ):
            raise RuntimeError(
                "OP-0338 chua DONE."
            )

        for op in (
            EXPECTED_READY
        ):
            if (
                mn_after[
                    "states"
                ].get(op)
                != "READY"
            ):
                raise RuntimeError(
                    f"{op} khong READY."
                )

        # ====================================================
        # 9. OP0338 EVIDENCE
        # ====================================================

        evidence = (
            mn_after[
                "precompleted"
            ].get(
                OP0338
            )
        )

        if not isinstance(
            evidence,
            dict,
        ):
            raise RuntimeError(
                "Khong co evidence "
                "precompleted OP-0338."
            )

        if not bool(
            evidence.get("pass")
        ):
            raise RuntimeError(
                "OP-0338 evidence PASS=False."
            )

        ev = dict(
            evidence.get(
                "evidence"
            )
            or {}
        )

        checks = dict(
            evidence.get(
                "checks"
            )
            or {}
        )

        if not bool(
            ev.get(
                "special_gate_bypassed"
            )
        ):
            raise RuntimeError(
                "OP-0338 chua bypass dung "
                "gate MAPPED cu."
            )

        if not all(
            bool(x)
            for x in checks.values()
        ):
            raise RuntimeError(
                "OP-0338 co check "
                "precompleted FALSE."
            )

        # ====================================================
        # 10. LUONG MINH MUST STILL BLOCK
        # ====================================================

        blocker_text = json.dumps(
            mn_after.get(
                "extra_blockers"
            )
            or [],
            ensure_ascii=False,
        )

        if (
            "Lượng Minh"
            not in blocker_text
        ):
            raise RuntimeError(
                "Khong con blocker Luong Minh "
                "ngoai du kien."
            )

        # ====================================================
        # 11. TH MUST NOT CHANGE
        # ====================================================

        th_keys = (
            "counts",
            "candidate_count",
            "effective_block_count",
            "ready_for_execution",
        )

        for key in th_keys:
            if (
                th_before.get(key)
                != th_after.get(key)
            ):
                raise RuntimeError(
                    "TH thay doi tai "
                    + key
                    + ": "
                    + repr(
                        th_before.get(key)
                    )
                    + " -> "
                    + repr(
                        th_after.get(key)
                    )
                )

        # ====================================================
        # 12. FINAL SAFETY
        # ====================================================

        db_after = sha256(
            DB
        )

        roster_after = sha256(
            ROSTER
        )

        if (
            db_after
            != EXPECTED_DB_SHA
        ):
            raise RuntimeError(
                "DB SHA bi thay doi."
            )

        if (
            roster_after
            != EXPECTED_ROSTER_SHA
        ):
            raise RuntimeError(
                "Roster SHA bi thay doi."
            )

        # ====================================================
        # 13. REPORT
        # ====================================================

        report_dir = (
            ROOT
            / "exports"
            / "Done_OP0338"
        )

        report_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        report_path = (
            report_dir
            / (
                "ket_qua_done_OP0338_"
                + stamp
                + ".json"
            )
        )

        report = {
            "status":
                "SUCCESS",

            "operation_id":
                OP0338,

            "result":
                "DONE_PRECOMPLETED",

            "executed_merger":
                False,

            "database_changed":
                False,

            "database_sha256":
                db_after,

            "service_sha256_before":
                hashes_before[
                    "service"
                ],

            "service_sha256_after":
                sha256(
                    SERVICE
                ),

            "resolution_sha256_before":
                hashes_before[
                    "resolution"
                ],

            "resolution_sha256_after":
                sha256(
                    RESOLUTION
                ),

            "roster_sha256":
                roster_after,

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
                    "OP-0338 chỉ được đánh dấu "
                    "DONE theo bằng chứng "
                    "precompleted. Không chạy "
                    "lại 749 -> 747."
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
            "OP-0337 : DONE - KHONG CHAY LAI"
        )

        print(
            "OP-0338 : DONE - KHONG CHAY LAI"
        )

        print()
        print(
            "MN KPI  :",
            mn_after[
                "counts"
            ],
        )

        print(
            "Candidate:",
            mn_after[
                "candidate_count"
            ],
        )

        print(
            "Eff block:",
            mn_after[
                "effective_block_count"
            ],
        )

        print(
            "Ready execution:",
            mn_after[
                "ready_for_execution"
            ],
        )

        print()
        print(
            "5 READY : CHUA THUC HIEN"
        )

        print(
            "Luong Minh: BLOCKER DUY NHAT"
        )

        print(
            "TH       : KHONG THAY DOI"
        )

        print(
            "Database : KHONG THAY DOI"
        )

        print(
            "DB SHA   :",
            db_after,
        )

        print()
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
            "CAI DAT LOI - KHOI PHUC FILE"
        )
        print("=" * 120)

        shutil.copy2(
            backup_service,
            SERVICE,
        )

        shutil.copy2(
            backup_resolution,
            RESOLUTION,
        )

        try:
            py_compile.compile(
                str(SERVICE),
                doraise=True,
            )
        except Exception:
            pass

        print(
            "Source/Resolution: "
            "DA KHOI PHUC"
        )

        print(
            "DB SHA:",
            sha256(DB),
        )

        if (
            sha256(DB)
            == EXPECTED_DB_SHA
        ):
            print(
                "Database: KHONG THAY DOI"
            )

        else:
            print(
                "CANH BAO: DB SHA "
                "KHONG CON DUNG."
            )

        raise


if __name__ == "__main__":
    main()
