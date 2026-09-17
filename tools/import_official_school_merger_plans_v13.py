# -*- coding: utf-8 -*-
r"""
V13 - NẠP SỔ PHƯƠNG ÁN SÁP NHẬP TOÀN TỈNH TỪ VĂN BẢN CHÍNH THỨC
=================================================================

Mặc định chỉ KIỂM TRA. Muốn ghi file phương án phải thêm:
    --apply --confirm "NAP PHUONG AN SAP NHAP TOAN TINH"

File CSV mặc định:
    C:\PhoCap\uploads\phuong_an_sap_nhap_toan_tinh_v13.csv

Cột:
- document_code
- document_title
- document_date
- school_year_code
- commune
- level_code
- source_schools       (nhiều trường, ngăn bằng ;)
- target_school
- note

Trường/xã có thể ghi bằng MÃ hoặc TÊN chính xác.
Không cho ghép tự do trên UI; file CSV này phải được lập từ văn bản chính thức.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
import sqlite3
import sys
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(r"C:\PhoCap")
DEFAULT_CSV = ROOT / "uploads" / "phuong_an_sap_nhap_toan_tinh_v13.csv"
PLAN_FILE = ROOT / "data" / "school_merger_approved_plans.json"
BACKUP_DIR = ROOT / "backups"
EXPORT_DIR = ROOT / "exports"
CONFIRM = "NAP PHUONG AN SAP NHAP TOAN TINH"

sys.path.insert(0, str(ROOT))

from app.services import school_merger_service as merger  # noqa: E402


def norm(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = text.replace("đ", "d")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def clean(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def load_payload() -> dict[str, Any]:
    if not PLAN_FILE.exists():
        return {
            "version": 3,
            "policy": (
                "Chỉ phương án từ văn bản chính thức được nạp bằng bộ V13; "
                "không cho ghép nguồn/đích tự do."
            ),
            "plans": [],
        }
    payload = json.loads(PLAN_FILE.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("plans"), list):
        raise RuntimeError("File phương án hiện có không đúng cấu trúc.")
    return payload


def school_year_by_code(con: sqlite3.Connection, value: str) -> int:
    wanted = norm(value)
    rows = con.execute("SELECT * FROM school_years ORDER BY id").fetchall()
    matches = []
    for row in rows:
        text = " ".join(str(row[k] or "") for k in row.keys() if k in {"code", "name"})
        if norm(text) == wanted or wanted in norm(text):
            matches.append(int(row["id"]))
    if len(matches) != 1:
        raise RuntimeError(
            f"Năm học {value!r} không khớp duy nhất. Matches={matches}"
        )
    return matches[0]


def commune_maps(con: sqlite3.Connection):
    rows = con.execute(
        "SELECT id,code,name,is_active FROM communes ORDER BY name"
    ).fetchall()
    by_code = {}
    by_name = {}
    for r in rows:
        if clean(r["code"]):
            by_code.setdefault(norm(r["code"]), []).append(r)
        by_name.setdefault(norm(r["name"]), []).append(r)
    return rows, by_code, by_name


def resolve_commune(con: sqlite3.Connection, token: str) -> sqlite3.Row:
    rows, by_code, by_name = commune_maps(con)
    key = norm(token)
    matches = list(by_code.get(key, [])) or list(by_name.get(key, []))
    if len(matches) != 1:
        raise RuntimeError(
            f"Xã/phường {token!r} không khớp duy nhất; số khớp={len(matches)}."
        )
    return matches[0]


def resolve_school(
    con: sqlite3.Connection,
    *,
    commune_id: int,
    token: str,
) -> sqlite3.Row:
    key = norm(token)
    rows = con.execute(
        "SELECT id,code,name,commune_id,is_active FROM schools WHERE commune_id=?",
        (int(commune_id),),
    ).fetchall()
    code_matches = [r for r in rows if clean(r["code"]) and norm(r["code"]) == key]
    name_matches = [r for r in rows if norm(r["name"]) == key]
    matches = code_matches or name_matches
    if len(matches) != 1:
        raise RuntimeError(
            f"Trường {token!r} trong commune_id={commune_id} "
            f"không khớp duy nhất; số khớp={len(matches)}."
        )
    return matches[0]


def stable_plan_id(
    *,
    document_code: str,
    school_year_id: int,
    commune_id: int,
    level_code: str,
    source_ids: list[int],
    target_id: int,
) -> str:
    raw = (
        f"{document_code}|{school_year_id}|{commune_id}|{level_code}|"
        f"{','.join(map(str, sorted(source_ids)))}|{target_id}"
    )
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12].upper()
    return f"VB-{school_year_id}-{commune_id}-{level_code}-{digest}"


def exact_signature(plan: dict[str, Any]):
    return (
        int(plan.get("school_year_id") or 0),
        int(plan.get("commune_id") or 0),
        str(plan.get("level_code") or "").upper(),
        tuple(sorted(int(x) for x in plan.get("source_school_ids") or [])),
        int(plan.get("target_school_id") or 0),
    )


def parse_rows(csv_path: Path) -> list[dict[str, str]]:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        required = {
            "document_code", "document_title", "document_date",
            "school_year_code", "commune", "level_code",
            "source_schools", "target_school", "note",
        }
        actual = set(reader.fieldnames or [])
        missing = required - actual
        if missing:
            raise RuntimeError(
                "CSV thiếu cột: " + ", ".join(sorted(missing))
            )
        return [
            {k: clean(v) for k, v in row.items()}
            for row in reader
            if any(clean(v) for v in row.values())
        ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", default=str(DEFAULT_CSV))
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm", default="")
    args = parser.parse_args()

    csv_path = Path(args.file)
    if not csv_path.exists():
        raise RuntimeError(f"Không tìm thấy CSV: {csv_path}")

    source_rows = parse_rows(csv_path)
    if not source_rows:
        raise RuntimeError("CSV không có dòng phương án.")

    now = datetime.now().isoformat(timespec="seconds")
    payload = load_payload()
    existing = [
        merger._normalize_plan(x)
        for x in payload.get("plans") or []
        if isinstance(x, dict)
    ]
    existing_signatures = {exact_signature(x): x for x in existing}

    proposed: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    errors: list[str] = []
    warnings: list[str] = []

    with merger._connect(read_only=True) as con:
        integrity = str(con.execute("PRAGMA integrity_check").fetchone()[0])
        fk = con.execute("PRAGMA foreign_key_check").fetchall()
        if integrity.lower() != "ok":
            raise RuntimeError(f"integrity_check={integrity}")
        if fk:
            raise RuntimeError(f"foreign_key_check={len(fk)} lỗi")

        for line_no, row in enumerate(source_rows, start=2):
            try:
                level = row["level_code"].upper()
                if level not in {"MN", "TH", "THCS", "THPT"}:
                    raise RuntimeError(f"Cấp học không hợp lệ: {level}")

                year_id = school_year_by_code(con, row["school_year_code"])
                commune = resolve_commune(con, row["commune"])
                commune_id = int(commune["id"])

                source_tokens = [
                    clean(x)
                    for x in row["source_schools"].split(";")
                    if clean(x)
                ]
                if not source_tokens:
                    raise RuntimeError("Phải có ít nhất một trường nguồn.")

                source_rows_db = [
                    resolve_school(
                        con,
                        commune_id=commune_id,
                        token=token,
                    )
                    for token in source_tokens
                ]
                target_row = resolve_school(
                    con,
                    commune_id=commune_id,
                    token=row["target_school"],
                )

                source_ids = sorted({int(x["id"]) for x in source_rows_db})
                target_id = int(target_row["id"])

                if target_id in source_ids:
                    raise RuntimeError("Trường đích trùng trường nguồn.")

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
                    raise RuntimeError(" | ".join(blockers))

                candidate = {
                    "id": stable_plan_id(
                        document_code=row["document_code"],
                        school_year_id=year_id,
                        commune_id=commune_id,
                        level_code=level,
                        source_ids=source_ids,
                        target_id=target_id,
                    ),
                    "document_code": row["document_code"],
                    "document_title": row["document_title"],
                    "document_date": row["document_date"],
                    "school_year_id": year_id,
                    "commune_id": commune_id,
                    "level_code": level,
                    "source_school_ids": source_ids,
                    "target_school_id": target_id,
                    "status": "APPROVED",
                    "note": row["note"],
                    "created_at": now,
                    "created_by": {
                        "source": "V13_OFFICIAL_DOCUMENT_IMPORT",
                    },
                    "approved_at": now,
                    "approved_by": {
                        "source": "V13_OFFICIAL_DOCUMENT_IMPORT",
                    },
                    "updated_at": now,
                    "updated_by": {
                        "source": "V13_OFFICIAL_DOCUMENT_IMPORT",
                    },
                    "approval_warnings": sorted(set(plan_warnings)),
                }

                sig = exact_signature(candidate)
                if sig in existing_signatures:
                    old = existing_signatures[sig]
                    skipped.append({
                        "line": line_no,
                        "reason": "EXACT_PLAN_ALREADY_EXISTS",
                        "existing_id": old.get("id"),
                        "document_code": row["document_code"],
                    })
                    continue

                # Chặn một trường tham gia nhiều phương án đang hiệu lực cùng năm.
                candidate_involved = set(source_ids + [target_id])
                for old in existing + proposed:
                    old_status = str(old.get("status") or "").upper()
                    if old_status not in {"APPROVED", "COMPLETED"}:
                        continue
                    if int(old.get("school_year_id") or 0) != year_id:
                        continue
                    old_involved = set(
                        [int(old.get("target_school_id") or 0)]
                        + [int(x) for x in old.get("source_school_ids") or []]
                    )
                    overlap = candidate_involved & old_involved
                    if overlap:
                        raise RuntimeError(
                            "Có trường đã nằm trong phương án APPROVED/COMPLETED "
                            f"cùng năm: {sorted(overlap)}; plan={old.get('id')}"
                        )

                technical = merger._technical_check_plan_for_approval(candidate)
                if technical.get("blockers"):
                    raise RuntimeError(
                        "Mô phỏng kỹ thuật chưa đạt: "
                        + " | ".join(technical["blockers"])
                    )
                if not technical.get("safe_to_approve"):
                    raise RuntimeError("Mô phỏng kỹ thuật không xác nhận an toàn.")

                if technical.get("warnings"):
                    candidate["approval_warnings"] = sorted(
                        set(candidate["approval_warnings"])
                        | set(technical["warnings"])
                    )

                proposed.append(candidate)

            except Exception as exc:
                errors.append(f"Dòng {line_no}: {exc}")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = EXPORT_DIR / f"kiem_tra_phuong_an_sap_nhap_toan_tinh_v13_{stamp}.json"
    report = {
        "source_file": str(csv_path),
        "apply_requested": bool(args.apply),
        "existing_plans": len(existing),
        "proposed_plans": len(proposed),
        "skipped": skipped,
        "errors": errors,
        "warnings": warnings,
        "proposed": proposed,
    }
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("=" * 118)
    print("V13 - KIỂM TRA SỔ PHƯƠNG ÁN SÁP NHẬP TOÀN TỈNH")
    print("=" * 118)
    print(f"CSV: {csv_path}")
    print(f"Existing plans: {len(existing)}")
    print(f"Proposed new plans: {len(proposed)}")
    print(f"Skipped exact existing: {len(skipped)}")
    print(f"Errors: {len(errors)}")
    print(f"Report: {report_path}")

    if errors:
        print()
        print("KHÔNG GHI FILE PHƯƠNG ÁN.")
        for msg in errors[:30]:
            print(" -", msg)
        return 2

    if not args.apply:
        print()
        print("DRY-RUN PASS. Chưa ghi file phương án.")
        print(
            'Muốn ghi thật: thêm --apply --confirm "'
            + CONFIRM
            + '"'
        )
        return 0

    if args.confirm.strip() != CONFIRM:
        print("Sai câu xác nhận; không ghi.")
        return 2

    if not proposed:
        print("Không có phương án mới cần ghi.")
        return 0

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backup_path = BACKUP_DIR / f"school_merger_approved_plans_truoc_v13_{stamp}.json"
    if PLAN_FILE.exists():
        shutil.copy2(PLAN_FILE, backup_path)

    payload["version"] = max(int(payload.get("version") or 1), 3)
    payload["policy"] = (
        "Sổ phương án sáp nhập toàn tỉnh: chỉ nạp từ văn bản chính thức bằng V13; "
        "không ghép nguồn/đích tự do. Chỉ APPROVED được thực hiện; COMPLETED không chạy lại."
    )
    payload.setdefault("plans", []).extend(proposed)
    payload["updated_at"] = now

    tmp = PLAN_FILE.with_suffix(".json.v13.tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    json.loads(tmp.read_text(encoding="utf-8"))
    tmp.replace(PLAN_FILE)

    print()
    print("ĐÃ GHI SỔ PHƯƠNG ÁN CHÍNH THỨC.")
    print(f"New plans: {len(proposed)}")
    print(f"Backup: {backup_path}")
    print(f"Plan file: {PLAN_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
