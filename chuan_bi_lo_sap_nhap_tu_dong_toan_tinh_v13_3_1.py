# -*- coding: utf-8 -*-
r"""
V13.3.1 - CHUẨN BỊ LÔ SÁP NHẬP TỰ ĐỘNG TOÀN TỈNH
================================================

Nguồn đầu vào đã khóa từ báo cáo V13.2.2:
- 421 nhóm MERGE_EXISTING_TARGET đã khớp duy nhất database ở bước V13.2.2.
- V13.3 kiểm tra lại trực tiếp với database HIỆN TẠI trên máy người dùng.

V13.3 CHỈ ĐỌC:
- KHÔNG sửa database.
- KHÔNG sửa school_merger_approved_plans.json.
- KHÔNG thực hiện sáp nhập.
- KHÔNG đổi tên trường.

V13.3 sẽ:
1. Xác định năm học đang hoạt động.
2. Bỏ qua chính xác các phương án đã có trong sổ (ví dụ QĐ3805 đã COMPLETED).
3. Kiểm tra source/target tồn tại, đúng xã, trạng thái active.
4. Kiểm tra cấp học chung của cả nhóm.
5. Chặn xung đột với APPROVED/COMPLETED hiện có.
6. Tạo CSV READY dùng đúng importer V13.
7. Tự chạy importer V13 ở chế độ DRY-RUN để mô phỏng kỹ thuật toàn bộ lô.
8. Tạo 1 ZIP kết quả.

Nếu cuối màn hình có:
    READY_FOR_PLAN_IMPORT: YES
thì bước kế tiếp có thể ghi hàng loạt các plan READY vào sổ phương án.
"""

from __future__ import annotations

import base64
import csv
import json
import re
import sqlite3
import subprocess
import sys
import zlib
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(r"C:\PhoCap")
DB_PATH = ROOT / "data" / "phocap.db"
PLAN_FILE = ROOT / "data" / "school_merger_approved_plans.json"
IMPORTER = ROOT / "tools" / "import_official_school_merger_plans_v13.py"
UPLOADS = ROOT / "uploads"
EXPORTS = ROOT / "exports"

DOCUMENT_CODE = "NGUON-SAP-NHAP-TOAN-TINH"
DOCUMENT_TITLE = "Nguồn sáp nhập toàn tỉnh (tệp nguồn)"
DOCUMENT_DATE = ""

CANDIDATES_ZLIB_B64 = """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"""


def clean(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def qident(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def load_candidates() -> list[dict[str, Any]]:
    raw = zlib.decompress(
        base64.b64decode(CANDIDATES_ZLIB_B64.encode("ascii"))
    )
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, list) or len(data) != 421:
        raise RuntimeError(
            f"Danh sách V13.2.2 phải có đúng 421 nhóm; hiện={len(data) if isinstance(data,list) else 'INVALID'}"
        )
    return data


def db_connect(read_only: bool = True) -> sqlite3.Connection:
    if read_only:
        uri = DB_PATH.resolve().as_uri() + "?mode=ro"
        con = sqlite3.connect(uri, uri=True, timeout=30)
        con.execute("PRAGMA query_only=ON")
    else:
        con = sqlite3.connect(str(DB_PATH), timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    return con


def exact_signature(plan: dict[str, Any]) -> tuple:
    return (
        int(plan.get("school_year_id") or 0),
        int(plan.get("commune_id") or 0),
        str(plan.get("level_code") or "").upper(),
        tuple(sorted(int(x) for x in plan.get("source_school_ids") or [])),
        int(plan.get("target_school_id") or 0),
    )


def signature_no_level(
    year_id: int,
    commune_id: int,
    source_ids: list[int],
    target_id: int,
) -> tuple:
    return (
        int(year_id),
        int(commune_id),
        tuple(sorted(int(x) for x in source_ids)),
        int(target_id),
    )


def plan_signature_no_level(plan: dict[str, Any]) -> tuple:
    return signature_no_level(
        int(plan.get("school_year_id") or 0),
        int(plan.get("commune_id") or 0),
        [int(x) for x in plan.get("source_school_ids") or []],
        int(plan.get("target_school_id") or 0),
    )


def write_csv(path: Path, headers: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def school_token(row: sqlite3.Row) -> str:
    code = clean(row["code"]) if "code" in row.keys() else ""
    return code or clean(row["name"])


def main() -> int:
    print("=" * 126)
    print("V13.3.1 - CHUẨN BỊ LÔ SÁP NHẬP TỰ ĐỘNG TOÀN TỈNH")
    print("=" * 126)
    print("CHẾ ĐỘ: CHỈ ĐỌC / KHÔNG SỬA DB / KHÔNG GHI PLAN")

    for p in (DB_PATH, PLAN_FILE, IMPORTER):
        if not p.exists():
            raise RuntimeError(f"Không tìm thấy tệp bắt buộc: {p}")

    sys.path.insert(0, str(ROOT))
    from app.services import school_merger_service as merger

    candidates = load_candidates()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = ROOT / f"bao_cao_v13_3_1_chuan_bi_lo_{stamp}"
    zip_path = ROOT / f"bao_cao_v13_3_1_chuan_bi_lo_{stamp}.zip"
    out_dir.mkdir(parents=True, exist_ok=False)
    UPLOADS.mkdir(parents=True, exist_ok=True)
    EXPORTS.mkdir(parents=True, exist_ok=True)

    ready_csv = UPLOADS / "phuong_an_sap_nhap_toan_tinh_v13_3_READY.csv"

    payload = json.loads(PLAN_FILE.read_text(encoding="utf-8"))
    existing_raw = [
        x for x in payload.get("plans") or []
        if isinstance(x, dict)
    ]
    existing = [merger._normalize_plan(x) for x in existing_raw]

    with db_connect(True) as con:
        integrity = str(con.execute("PRAGMA integrity_check").fetchone()[0])
        fk = con.execute("PRAGMA foreign_key_check").fetchall()
        if integrity.lower() != "ok" or fk:
            raise RuntimeError(
                f"Database không an toàn: integrity={integrity}; FK={len(fk)}"
            )

        years = merger._school_year_rows(con)

        # V13.3.1:
        # school_years.is_active trong DB hiện tại là cờ "được sử dụng",
        # KHÔNG phải cờ "năm hiện hành duy nhất"; thực tế cả 8 năm đều active.
        # Xác định năm sáp nhập toàn tỉnh từ chính 6 phương án QĐ3805
        # đã COMPLETED. Đây là mốc nghiệp vụ đã được thực hiện/chốt.
        qd3805_plans = [
            p for p in existing
            if (
                str(p.get("id") or "").startswith("QD3805-")
                or "3805" in str(p.get("document_code") or "")
            )
            and merger._effective_plan_status(con, p) == "COMPLETED"
        ]

        qd_year_ids = sorted({
            int(p.get("school_year_id") or 0)
            for p in qd3805_plans
            if int(p.get("school_year_id") or 0) > 0
        })

        if len(qd3805_plans) != 6:
            raise RuntimeError(
                f"Phải còn đúng 6 phương án QĐ3805 COMPLETED; "
                f"hiện={len(qd3805_plans)}"
            )

        if len(qd_year_ids) != 1:
            raise RuntimeError(
                f"6 phương án QĐ3805 phải cùng một school_year_id; "
                f"hiện={qd_year_ids}"
            )

        year_id = int(qd_year_ids[0])

        year_matches = [
            x for x in years
            if int(x.get("id") or 0) == year_id
        ]
        if len(year_matches) != 1:
            raise RuntimeError(
                f"Không xác định được school_year_id={year_id} trong school_years."
            )

        active_year = year_matches[0]
        year_code = clean(
            active_year.get("code")
            or active_year.get("name")
        )

        if year_code != "2026-2027":
            raise RuntimeError(
                f"Năm của QĐ3805 phải là 2026-2027; thực tế={year_code!r}, "
                f"id={year_id}"
            )

        print(
            "Năm sáp nhập được khóa theo QĐ3805: "
            f"{year_code} (id={year_id}). "
            "Không dùng school_years.is_active để suy ra năm hiện hành."
        )

        existing_by_sig_no_level = {
            plan_signature_no_level(p): p
            for p in existing
            if int(p.get("school_year_id") or 0) == year_id
        }

        existing_involved: list[tuple[set[int], dict[str, Any], str]] = []
        for p in existing:
            if int(p.get("school_year_id") or 0) != year_id:
                continue
            status = merger._effective_plan_status(con, p)
            if status not in {"APPROVED", "COMPLETED"}:
                continue
            involved = {
                int(p.get("target_school_id") or 0),
                *[int(x) for x in p.get("source_school_ids") or []],
            }
            involved.discard(0)
            existing_involved.append((involved, p, status))

        ready = []
        already = []
        blocked = []
        warnings = []

        # xác nhận không có trường xuất hiện trong nhiều candidate V13.2.2
        seen_school: dict[int, int] = {}
        internal_overlap = []
        for c in candidates:
            ids = [int(c["target_id"])] + [int(x) for x in c["source_ids"]]
            for sid in ids:
                if sid in seen_school:
                    internal_overlap.append({
                        "school_id": sid,
                        "group_a": seen_school[sid],
                        "group_b": int(c["group_no"]),
                    })
                else:
                    seen_school[sid] = int(c["group_no"])

        if internal_overlap:
            raise RuntimeError(
                f"Danh sách 421 nhóm có {len(internal_overlap)} school overlap nội bộ."
            )

        for c in candidates:
            group_no = int(c["group_no"])
            commune_id = int(c["commune_id"])
            source_ids = sorted({int(x) for x in c["source_ids"]})
            target_id = int(c["target_id"])
            sig0 = signature_no_level(
                year_id, commune_id, source_ids, target_id
            )

            old = existing_by_sig_no_level.get(sig0)
            if old is not None:
                effective = merger._effective_plan_status(con, old)
                already.append({
                    "group_no": group_no,
                    "commune": c["commune"],
                    "source_ids": ",".join(map(str, source_ids)),
                    "target_id": target_id,
                    "existing_plan_id": old.get("id"),
                    "existing_status": effective,
                    "reason": "EXACT_PLAN_ALREADY_EXISTS",
                })
                continue

            ids = source_ids + [target_id]
            rows = con.execute(
                f"SELECT id,code,name,commune_id,is_active "
                f"FROM schools WHERE id IN ({','.join('?' for _ in ids)})",
                ids,
            ).fetchall()
            by_id = {int(r["id"]): r for r in rows}

            missing = [sid for sid in ids if sid not in by_id]
            if missing:
                blocked.append({
                    "group_no": group_no,
                    "commune": c["commune"],
                    "source_ids": ",".join(map(str, source_ids)),
                    "target_id": target_id,
                    "reason": f"Thiếu school_id trong DB: {missing}",
                })
                continue

            wrong_commune = [
                sid for sid in ids
                if int(by_id[sid]["commune_id"] or 0) != commune_id
            ]
            if wrong_commune:
                blocked.append({
                    "group_no": group_no,
                    "commune": c["commune"],
                    "source_ids": ",".join(map(str, source_ids)),
                    "target_id": target_id,
                    "reason": f"School khác commune_id nguồn: {wrong_commune}",
                })
                continue

            inactive_sources = [
                sid for sid in source_ids
                if int(by_id[sid]["is_active"] or 0) != 1
            ]
            if inactive_sources:
                blocked.append({
                    "group_no": group_no,
                    "commune": c["commune"],
                    "source_ids": ",".join(map(str, source_ids)),
                    "target_id": target_id,
                    "reason": f"Trường nguồn đã inactive nhưng chưa có exact plan: {inactive_sources}",
                })
                continue

            if int(by_id[target_id]["is_active"] or 0) != 1:
                blocked.append({
                    "group_no": group_no,
                    "commune": c["commune"],
                    "source_ids": ",".join(map(str, source_ids)),
                    "target_id": target_id,
                    "reason": "Trường đích không active.",
                })
                continue

            involved = set(ids)
            conflict = None
            for old_involved, p, status in existing_involved:
                overlap = involved & old_involved
                if overlap:
                    conflict = (p, status, sorted(overlap))
                    break

            if conflict:
                p, status, overlap = conflict
                blocked.append({
                    "group_no": group_no,
                    "commune": c["commune"],
                    "source_ids": ",".join(map(str, source_ids)),
                    "target_id": target_id,
                    "reason": (
                        f"Xung đột plan {status}={p.get('id')}; "
                        f"school overlap={overlap}"
                    ),
                })
                continue

            level_sets = []
            for sid in ids:
                levels = set(
                    x for x in merger._school_levels(con, sid, year_id)
                    if x in {"MN","TH","THCS","THPT"}
                )
                level_sets.append(levels)

            if any(not x for x in level_sets):
                blocked.append({
                    "group_no": group_no,
                    "commune": c["commune"],
                    "source_ids": ",".join(map(str, source_ids)),
                    "target_id": target_id,
                    "reason": (
                        "Không xác định được cấp học hiện hành cho ít nhất một trường: "
                        + " | ".join(
                            f"{sid}={sorted(levels)}"
                            for sid, levels in zip(ids, level_sets)
                        )
                    ),
                })
                continue

            common = set.intersection(*level_sets)
            if len(common) != 1:
                blocked.append({
                    "group_no": group_no,
                    "commune": c["commune"],
                    "source_ids": ",".join(map(str, source_ids)),
                    "target_id": target_id,
                    "reason": (
                        f"Cấp học chung không duy nhất: {sorted(common)}; "
                        + " | ".join(
                            f"{sid}={sorted(levels)}"
                            for sid, levels in zip(ids, level_sets)
                        )
                    ),
                })
                continue

            level = next(iter(common))

            blockers, plan_warnings = merger._validate_plan_definition(
                school_year_id=year_id,
                commune_id=commune_id,
                level_code=level,
                source_school_ids=source_ids,
                target_school_id=target_id,
                current_plan_id=None,
                for_approval=True,
            )
            if blockers:
                blocked.append({
                    "group_no": group_no,
                    "commune": c["commune"],
                    "source_ids": ",".join(map(str, source_ids)),
                    "target_id": target_id,
                    "reason": " | ".join(blockers),
                })
                continue

            commune_row = con.execute(
                "SELECT id,code,name FROM communes WHERE id=?",
                (commune_id,),
            ).fetchone()

            source_tokens = [
                school_token(by_id[sid])
                for sid in source_ids
            ]
            target_token = school_token(by_id[target_id])
            commune_token = (
                clean(commune_row["code"])
                if commune_row and clean(commune_row["code"])
                else clean(commune_row["name"]) if commune_row else c["commune"]
            )

            ready.append({
                "group_no": group_no,
                "document_code": DOCUMENT_CODE,
                "document_title": DOCUMENT_TITLE,
                "document_date": DOCUMENT_DATE,
                "school_year_code": year_code,
                "commune": commune_token,
                "level_code": level,
                "source_schools": ";".join(source_tokens),
                "target_school": target_token,
                "note": f"Nhóm {group_no} từ Nguồn sáp nhập.xlsx",
            })

            for w in plan_warnings:
                warnings.append({
                    "group_no": group_no,
                    "warning": str(w),
                })

    ready_headers = [
        "group_no",
        "document_code",
        "document_title",
        "document_date",
        "school_year_code",
        "commune",
        "level_code",
        "source_schools",
        "target_school",
        "note",
    ]
    write_csv(ready_csv, ready_headers, ready)
    write_csv(out_dir / "710_READY_PRECHECK.csv", ready_headers, ready)
    write_csv(
        out_dir / "711_ALREADY_IN_REGISTRY.csv",
        [
            "group_no","commune","source_ids","target_id",
            "existing_plan_id","existing_status","reason"
        ],
        already,
    )
    write_csv(
        out_dir / "712_BLOCKED_PRECHECK.csv",
        ["group_no","commune","source_ids","target_id","reason"],
        blocked,
    )
    write_csv(
        out_dir / "713_PRECHECK_WARNINGS.csv",
        ["group_no","warning"],
        warnings,
    )

    # Chạy đúng importer V13 một lần ở DRY-RUN để mô phỏng kỹ thuật toàn bộ READY.
    importer_return = None
    importer_stdout = ""
    importer_stderr = ""
    importer_report_copy = None

    before_reports = set(EXPORTS.glob(
        "kiem_tra_phuong_an_sap_nhap_toan_tinh_v13_*.json"
    ))

    if ready:
        proc = subprocess.run(
            [
                sys.executable,
                str(IMPORTER),
                "--file",
                str(ready_csv),
            ],
            cwd=str(ROOT),
            text=True,
            capture_output=True,
        )
        importer_return = int(proc.returncode)
        importer_stdout = proc.stdout or ""
        importer_stderr = proc.stderr or ""

        after_reports = set(EXPORTS.glob(
            "kiem_tra_phuong_an_sap_nhap_toan_tinh_v13_*.json"
        ))
        new_reports = sorted(
            after_reports - before_reports,
            key=lambda p: p.stat().st_mtime_ns,
        )
        if new_reports:
            src = new_reports[-1]
            importer_report_copy = out_dir / "714_IMPORTER_DRY_RUN.json"
            importer_report_copy.write_bytes(src.read_bytes())

    (out_dir / "715_IMPORTER_STDOUT.txt").write_text(
        importer_stdout,
        encoding="utf-8",
    )
    (out_dir / "716_IMPORTER_STDERR.txt").write_text(
        importer_stderr,
        encoding="utf-8",
    )

    importer_errors = []
    proposed_count = 0
    skipped_count = 0
    if importer_report_copy and importer_report_copy.exists():
        rep = json.loads(importer_report_copy.read_text(encoding="utf-8"))
        importer_errors = list(rep.get("errors") or [])
        proposed_count = int(len(rep.get("proposed") or []))
        skipped_count = int(len(rep.get("skipped") or []))

    ready_for_import = (
        bool(ready)
        and importer_return == 0
        and not importer_errors
        and proposed_count == len(ready)
    )

    gate = [
        {
            "check": "database_integrity",
            "result": "PASS",
            "detail": integrity,
        },
        {
            "check": "database_fk",
            "result": "PASS",
            "detail": str(len(fk)),
        },
        {
            "check": "merger_school_year_from_QD3805",
            "result": "PASS",
            "detail": f"{year_code} / id={year_id}",
        },
        {
            "check": "v13_2_2_candidate_groups",
            "result": "PASS",
            "detail": str(len(candidates)),
        },
        {
            "check": "already_in_registry",
            "result": "INFO",
            "detail": str(len(already)),
        },
        {
            "check": "precheck_blocked",
            "result": "PASS" if not blocked else "REVIEW",
            "detail": str(len(blocked)),
        },
        {
            "check": "ready_precheck",
            "result": "INFO",
            "detail": str(len(ready)),
        },
        {
            "check": "importer_dry_run_return",
            "result": "PASS" if importer_return == 0 else "FAIL",
            "detail": str(importer_return),
        },
        {
            "check": "importer_proposed",
            "result": "PASS" if proposed_count == len(ready) else "REVIEW",
            "detail": f"proposed={proposed_count} / ready={len(ready)}",
        },
        {
            "check": "importer_errors",
            "result": "PASS" if not importer_errors else "FAIL",
            "detail": str(len(importer_errors)),
        },
        {
            "check": "READY_FOR_PLAN_IMPORT",
            "result": "YES" if ready_for_import else "NO",
            "detail": (
                "Có thể ghi lô READY vào sổ phương án V13."
                if ready_for_import
                else "Chưa được ghi plan; xem 712/714/715."
            ),
        },
    ]

    write_csv(
        out_dir / "717_GATE_V13_3_1.csv",
        ["check","result","detail"],
        gate,
    )

    summary = f"""V13.3.1 - CHUẨN BỊ LÔ SÁP NHẬP TỰ ĐỘNG TOÀN TỈNH
======================================================================

Năm học active: {year_code} (id={year_id})
Candidate từ V13.2.2: {len(candidates)}

Đã có trong sổ phương án: {len(already)}
Bị chặn ở precheck: {len(blocked)}
READY đưa qua importer: {len(ready)}

Importer dry-run return: {importer_return}
Importer proposed: {proposed_count}
Importer skipped: {skipped_count}
Importer errors: {len(importer_errors)}

READY_FOR_PLAN_IMPORT: {'YES' if ready_for_import else 'NO'}

CSV READY:
{ready_csv}

Database: KHÔNG THAY ĐỔI
Plan JSON: KHÔNG THAY ĐỔI
"""
    (out_dir / "00_TONG_QUAN_V13_3_1.txt").write_text(
        summary,
        encoding="utf-8",
    )

    with zipfile.ZipFile(
        zip_path,
        "w",
        compression=zipfile.ZIP_DEFLATED,
    ) as zf:
        for p in sorted(out_dir.iterdir()):
            if p.is_file():
                zf.write(p, arcname=p.name)
        if ready_csv.exists():
            zf.write(
                ready_csv,
                arcname=ready_csv.name,
            )

    print()
    print("=" * 126)
    print("HOÀN THÀNH V13.3.1")
    print("=" * 126)
    print(f"Năm học active: {year_code} (id={year_id})")
    print(f"Candidate V13.2.2: {len(candidates)}")
    print(f"Đã có trong registry: {len(already)}")
    print(f"Precheck blocked: {len(blocked)}")
    print(f"READY precheck: {len(ready)}")
    print(f"Importer proposed: {proposed_count}")
    print(f"Importer errors: {len(importer_errors)}")
    print(f"READY_FOR_PLAN_IMPORT: {'YES' if ready_for_import else 'NO'}")
    print("Database: KHÔNG THAY ĐỔI")
    print("Plan JSON: KHÔNG THAY ĐỔI")
    print(f"CSV READY: {ready_csv}")
    print(f"ZIP: {zip_path}")
    return 0 if ready_for_import else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print()
        print("=" * 126)
        print("V13.3.1 DỪNG AN TOÀN")
        print("=" * 126)
        print(repr(exc))
        print("Database: KHÔNG THAY ĐỔI")
        print("Plan JSON: KHÔNG THAY ĐỔI")
        raise SystemExit(2)
