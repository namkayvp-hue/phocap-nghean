# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import json
import os
import py_compile
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unicodedata
import re
from datetime import datetime
from pathlib import Path

ROOT = Path(r"C:\PhoCap")
HERE = Path(__file__).resolve().parent

DB = ROOT / "data" / "phocap.db"
LEVEL_BATCH_SERVICE = ROOT / "app" / "services" / "school_merger_level_batch_service.py"
SOURCE_AUDIT_SERVICE = ROOT / "app" / "services" / "school_merger_source_audit_service.py"
RAW_REGISTRY = ROOT / "data" / "school_merger_source_rosters" / "TH_2025_2026.json"
CORRECTIONS = ROOT / "data" / "school_merger_source_corrections.json"
RESOLUTION = ROOT / "data" / "school_merger_registry" / "qd3805_th_resolution.json"

NEW_SERVICE = HERE / "school_merger_level_batch_service.py"
NEW_RESOLUTION = HERE / "qd3805_th_resolution.json"

BASE_SERVICE_HASH = "9492f03ba7d69de14f448731cec178e7fb1850cd621d061f101b5fa3bcba8dd5"
PATCHED_SERVICE_HASH = "fee73378f9f32903cc562f783375fcf66c61ffbed0ba8bc3a6b18c9d964a12ad"
RAW_REGISTRY_HASH = "26b4356ffd9098ac682b1ed74432c443022fcecbe68724336b2adbfd5f053f98"

DATASET_ID = "TH-2025-2026-DANH-SACH-GIAO-VIEN"
PAST_YEAR = "2025-2026"

CORRECTION_SPECS = [
    {
        "correction_id": "QD3805-TH-2025-2026-4000679209-THANH-LINH",
        "staff_code": "4000679209",
        "wrong_name": "Võ Xuân Nguyên",
        "wrong_school_contains": "Thanh Lĩnh",
        "canonical_name": "Lê Văn Hạnh",
        "canonical_dob": "1974-10-15",
        "canonical_school_code": "40428456",
        "canonical_school_contains": "Hương Tiến",
        "reason": (
            "Mã 4000679209 thuộc Lê Văn Hạnh trong DB 2025-2026 tại Tiểu học Hương Tiến. "
            "Dòng Võ Xuân Nguyên tại Thanh Lĩnh dùng nhầm cùng mã nên chỉ loại dòng đó khỏi registry đối chiếu; "
            "không sửa Excel gốc và không sửa hồ sơ DB."
        ),
    },
    {
        "correction_id": "QD3805-TH-2025-2026-4002555491-HUNG-DONG",
        "staff_code": "4002555491",
        "wrong_name": "Tô Thị Thuỷ",
        "wrong_school_contains": "Hưng Đông",
        "canonical_name": "Lê Sĩ Bản",
        "canonical_dob": "1979-07-16",
        "canonical_school_code": "40412428",
        "canonical_school_contains": "Nghi Liên",
        "reason": (
            "Mã 4002555491 thuộc Lê Sĩ Bản trong DB 2025-2026 tại Tiểu học Nghi Liên. "
            "Dòng Tô Thị Thuỷ tại Hưng Đông dùng nhầm cùng mã nên chỉ loại dòng đó khỏi registry đối chiếu; "
            "không sửa Excel gốc và không sửa hồ sơ DB."
        ),
    },
]


def norm(v):
    s = str(v or "").strip().lower().replace("đ", "d")
    s = "".join(
        ch for ch in unicodedata.normalize("NFD", s)
        if unicodedata.category(ch) != "Mn"
    )
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except Exception:
            pass
        raise


def ro_connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB.resolve().as_uri() + "?mode=ro", uri=True, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA query_only=ON")
    con.execute("PRAGMA foreign_keys=ON")
    return con


def active_source_row(row: dict) -> bool:
    return norm(row.get("status_label")) in {"dang lam viec", "chuyen den"}


def validate_db_identity(spec: dict) -> dict:
    con = ro_connect()
    try:
        members = con.execute(
            "SELECT id,ministry_staff_code,full_name,date_of_birth,is_active "
            "FROM staff_members WHERE ministry_staff_code=?",
            (spec["staff_code"],),
        ).fetchall()
        if len(members) != 1:
            raise RuntimeError(
                f"Mã {spec['staff_code']} trong DB có {len(members)} staff_member; cần đúng 1."
            )
        member = dict(members[0])
        if norm(member.get("full_name")) != norm(spec["canonical_name"]):
            raise RuntimeError(
                f"Mã {spec['staff_code']} trong DB đang thuộc '{member.get('full_name')}', "
                f"không phải '{spec['canonical_name']}'."
            )
        if str(member.get("date_of_birth") or "")[:10] != spec["canonical_dob"]:
            raise RuntimeError(
                f"Ngày sinh DB của {spec['staff_code']} không còn đúng {spec['canonical_dob']}."
            )

        year = con.execute(
            "SELECT id FROM school_years "
            "WHERE REPLACE(REPLACE(code,'–','-'),'—','-')=? LIMIT 1",
            (PAST_YEAR,),
        ).fetchone()
        school = con.execute(
            "SELECT id,code,name,is_active FROM schools WHERE code=? LIMIT 1",
            (spec["canonical_school_code"],),
        ).fetchone()
        if year is None or school is None:
            raise RuntimeError("Không tìm thấy năm nguồn hoặc trường canonical trong DB.")

        recs = con.execute(
            "SELECT id,staff_member_id,school_year_id,school_id,is_active,status_code,source_status_label "
            "FROM staff_year_records WHERE staff_member_id=? AND school_year_id=? AND school_id=?",
            (int(member["id"]), int(year["id"]), int(school["id"])),
        ).fetchall()
        if len(recs) != 1:
            raise RuntimeError(
                f"Không khóa được đúng một staff_year_record canonical cho mã {spec['staff_code']}."
            )
        rec = dict(recs[0])
        if int(rec.get("is_active") or 0) != 1:
            raise RuntimeError(f"Hồ sơ năm canonical của {spec['staff_code']} không còn active.")
        return {
            "staff_member": member,
            "staff_year_record": rec,
            "canonical_school": dict(school),
        }
    finally:
        con.close()


def find_source_rows(payload: dict, spec: dict) -> tuple[dict, dict]:
    rows = [
        dict(x) for x in (payload.get("rows") or [])
        if str((x or {}).get("staff_code") or "").strip() == spec["staff_code"]
    ]
    active = [x for x in rows if active_source_row(x)]
    if len(active) != 2:
        raise RuntimeError(
            f"Nguồn mã {spec['staff_code']} hiện có {len(active)} dòng hoạt động; cần đúng 2 để xử lý có kiểm soát."
        )

    wrong = [
        x for x in active
        if norm(x.get("full_name")) == norm(spec["wrong_name"])
        and norm(spec["wrong_school_contains"]) in norm(x.get("school_name"))
    ]
    canonical = [
        x for x in active
        if norm(x.get("full_name")) == norm(spec["canonical_name"])
        and norm(spec["canonical_school_contains"]) in norm(x.get("school_name"))
    ]
    if len(wrong) != 1 or len(canonical) != 1:
        raise RuntimeError(
            f"Không nhận diện duy nhất dòng sai/canonical cho mã {spec['staff_code']}: "
            f"wrong={len(wrong)}, canonical={len(canonical)}."
        )
    if int(wrong[0].get("excel_row") or 0) == int(canonical[0].get("excel_row") or 0):
        raise RuntimeError("Dòng sai và canonical trùng excel_row.")
    return wrong[0], canonical[0]


def make_correction(spec: dict, wrong: dict, canonical: dict, evidence: dict) -> dict:
    return {
        "correction_id": spec["correction_id"],
        "action": "EXCLUDE_ROW",
        "dataset_id": DATASET_ID,
        "excel_row": int(wrong.get("excel_row")),
        "staff_code": spec["staff_code"],
        "full_name": str(wrong.get("full_name") or ""),
        "date_of_birth": str(wrong.get("date_of_birth") or ""),
        "excluded_commune_name": str(wrong.get("commune_name") or ""),
        "excluded_school_name": str(wrong.get("school_name") or ""),
        "kept_excel_row": int(canonical.get("excel_row")),
        "canonical_commune_name": str(canonical.get("commune_name") or ""),
        "canonical_school_name": str(canonical.get("school_name") or ""),
        "canonical_school_code": spec["canonical_school_code"],
        "reason": spec["reason"],
        "evidence": {
            "db_staff_member_id": int(evidence["staff_member"]["id"]),
            "db_full_name": str(evidence["staff_member"]["full_name"]),
            "db_date_of_birth": str(evidence["staff_member"]["date_of_birth"]),
            "db_expected_school_id": int(evidence["canonical_school"]["id"]),
            "db_expected_school_code": str(evidence["canonical_school"]["code"]),
            "db_expected_school_name": str(evidence["canonical_school"]["name"]),
            "wrong_source_excel_row": int(wrong.get("excel_row")),
            "canonical_source_excel_row": int(canonical.get("excel_row")),
            "source_status_wrong": str(wrong.get("status_label") or ""),
            "source_status_canonical": str(canonical.get("status_label") or ""),
        },
    }


def load_corrections() -> dict:
    if not CORRECTIONS.exists():
        return {"version": 1, "corrections": []}
    payload = json.loads(CORRECTIONS.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("corrections"), list):
        raise RuntimeError("school_merger_source_corrections.json không đúng cấu trúc.")
    return payload


def merge_corrections(payload: dict, additions: list[dict]) -> dict:
    existing = [dict(x) for x in (payload.get("corrections") or [])]
    by_id = {str(x.get("correction_id") or ""): x for x in existing}
    for item in additions:
        cid = item["correction_id"]
        if cid in by_id:
            old = by_id[cid]
            for key in ("action", "dataset_id", "excel_row", "staff_code", "kept_excel_row"):
                if str(old.get(key)) != str(item.get(key)):
                    raise RuntimeError(f"Correction {cid} đã tồn tại nhưng khác khóa {key}.")
            continue
        existing.append(item)
    return {
        "version": int(payload.get("version") or 1),
        "corrections": existing,
    }


def validate_resolution_file() -> dict:
    payload = json.loads(NEW_RESOLUTION.read_text(encoding="utf-8"))
    if str(payload.get("schema") or "") != "QD3805_TH_RESOLUTION_2026":
        raise RuntimeError("Payload resolution sai schema.")
    if len(payload.get("rename_only") or []) != 1:
        raise RuntimeError("Resolution phải có đúng 1 trường hợp đổi tên Tri Lễ.")
    if len(payload.get("precompleted") or []) != 2:
        raise RuntimeError("Resolution phải có đúng 2 phương án đã hoàn tất trước.")
    if len(payload.get("deferred_orphans") or []) != 1:
        raise RuntimeError("Resolution phải có đúng 1 dòng chờ xác nhận.")
    return payload


def smoke_audit() -> dict:
    code = r"""
import json
from app.services.school_merger_service import list_school_years
from app.services.school_merger_level_batch_service import build_level_batch_preview

year_id = None
for y in list_school_years():
    code = str(y.get("code") or y.get("name") or "").replace("–","-").replace("—","-")
    if code == "2026-2027":
        year_id = int(y["id"])
        break
if year_id is None:
    raise RuntimeError("Không tìm thấy năm 2026-2027.")

p = build_level_batch_preview(school_year_id=year_id, level_code="TH")
print(json.dumps({
    "counts": p.get("counts"),
    "expected_actions": p.get("registry_action_expected_count"),
    "mapped_actions": p.get("registry_action_mapped_count"),
    "expected_keep": p.get("registry_keep_expected_count"),
    "unresolved": p.get("registry_unresolved_count"),
    "deferred_unresolved": p.get("registry_deferred_unresolved_count"),
    "excluded": p.get("excluded_cross_level_count"),
    "effective_block_count": p.get("effective_block_count"),
    "candidate_count": p.get("candidate_count"),
    "ready_for_execution": p.get("ready_for_execution"),
    "all_done": p.get("all_done"),
    "previous_batch": bool(p.get("previous_batch")),
}, ensure_ascii=False))
"""
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=180,
    )
    if proc.returncode != 0:
        raise RuntimeError("Smoke audit lỗi:\n" + (proc.stderr or proc.stdout))
    line = (proc.stdout or "").strip().splitlines()[-1]
    return json.loads(line)


def validate_smoke(s: dict) -> None:
    counts = s.get("counts") or {}
    expected = {
        "DONE": 141,
        "READY": 19,
        "BLOCK": 0,
        "KEEP": 67,
    }
    for key, value in expected.items():
        if int(counts.get(key) or 0) != value:
            raise RuntimeError(
                f"Smoke audit: {key}={counts.get(key)}; dự kiến {value}."
            )
    checks = {
        "expected_actions": 160,
        "mapped_actions": 160,
        "expected_keep": 67,
        "unresolved": 1,
        "deferred_unresolved": 1,
        "excluded": 75,
        "effective_block_count": 0,
        "candidate_count": 19,
    }
    for key, value in checks.items():
        if int(s.get(key) or 0) != value:
            raise RuntimeError(
                f"Smoke audit: {key}={s.get(key)}; dự kiến {value}."
            )
    if s.get("previous_batch"):
        raise RuntimeError("Đã tồn tại nhật ký SÁP NHẬP TOÀN CẤP Tiểu học; không cài chồng.")
    if not bool(s.get("ready_for_execution")):
        raise RuntimeError("Sau xử lý, cổng SÁP NHẬP TOÀN CẤP vẫn chưa READY.")


def main():
    print("=" * 118)
    print("HOÀN TẤT CỔNG TIỂU HỌC QĐ3805 – SỬA NHẬN DIỆN 2 PHƯƠNG ÁN ĐÃ HOÀN TẤT TRƯỚC")
    print("Dự án:", ROOT)
    print("Database:", DB)
    print("Nguyên tắc: KHÔNG thực hiện sáp nhập; KHÔNG ghi phocap.db; KHÔNG sửa Excel nguồn.")
    print("=" * 118)

    required = [DB, LEVEL_BATCH_SERVICE, SOURCE_AUDIT_SERVICE, RAW_REGISTRY, NEW_SERVICE, NEW_RESOLUTION]
    missing = [str(x) for x in required if not x.exists()]
    if missing:
        raise SystemExit("Thiếu file bắt buộc:\n" + "\n".join(missing))

    current_service_hash = sha256(LEVEL_BATCH_SERVICE)
    if current_service_hash not in {BASE_SERVICE_HASH, PATCHED_SERVICE_HASH}:
        raise SystemExit(
            "school_merger_level_batch_service.py không đúng nền đã khóa. "
            + "Hash hiện tại: " + current_service_hash
        )
    if sha256(RAW_REGISTRY) != RAW_REGISTRY_HASH:
        raise SystemExit(
            "TH_2025_2026.json đã khác registry nguồn được kiểm thử; dừng để tránh sửa nhầm."
        )
    audit_text = SOURCE_AUDIT_SERVICE.read_text(encoding="utf-8")
    if "school_merger_source_corrections.json" not in audit_text or "EXCLUDE_ROW" not in audit_text:
        raise SystemExit("Source audit service hiện tại chưa có cơ chế correction V4.4.")

    validate_resolution_file()
    raw_payload = json.loads(RAW_REGISTRY.read_text(encoding="utf-8"))
    if str(raw_payload.get("dataset_id") or "") != DATASET_ID:
        raise SystemExit("TH_2025_2026.json không đúng dataset Tiểu học.")

    additions = []
    evidence_report = []
    for spec in CORRECTION_SPECS:
        evidence = validate_db_identity(spec)
        wrong, canonical = find_source_rows(raw_payload, spec)
        correction = make_correction(spec, wrong, canonical, evidence)
        additions.append(correction)
        evidence_report.append({
            "staff_code": spec["staff_code"],
            "excluded_excel_row": correction["excel_row"],
            "excluded_name": correction["full_name"],
            "excluded_school": correction["excluded_school_name"],
            "kept_excel_row": correction["kept_excel_row"],
            "canonical_name": correction["canonical_school_name"],
            "canonical_school_code": correction["canonical_school_code"],
        })

    merged_corrections = merge_corrections(load_corrections(), additions)

    db_before = sha256(DB)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = ROOT / "backups" / f"backup_truoc_hoan_tat_cong_TH_QD3805_{stamp}"
    backup_dir.mkdir(parents=True, exist_ok=True)

    backups = {}
    for path in (LEVEL_BATCH_SERVICE, CORRECTIONS, RESOLUTION):
        if path.exists():
            bp = backup_dir / path.name
            shutil.copy2(path, bp)
            backups[path] = bp
        else:
            backups[path] = None

    def rollback():
        for path, bp in backups.items():
            try:
                if bp is None:
                    if path.exists():
                        path.unlink()
                elif bp.exists():
                    shutil.copy2(bp, path)
            except Exception:
                pass

    try:
        atomic_write(
            CORRECTIONS,
            json.dumps(merged_corrections, ensure_ascii=False, indent=2).encode("utf-8"),
        )
        atomic_write(RESOLUTION, NEW_RESOLUTION.read_bytes())
        atomic_write(LEVEL_BATCH_SERVICE, NEW_SERVICE.read_bytes())
        py_compile.compile(str(LEVEL_BATCH_SERVICE), doraise=True)

        smoke = smoke_audit()
        validate_smoke(smoke)

        db_after = sha256(DB)
        if db_after != db_before:
            raise RuntimeError("Hash phocap.db đã thay đổi dù bộ cài chỉ được phép đọc.")

        export_dir = ROOT / "exports" / "Hoan_Tat_Cong_TH_QD3805"
        export_dir.mkdir(parents=True, exist_ok=True)
        report = export_dir / f"bao_cao_hoan_tat_cong_TH_QD3805_{stamp}.json"
        report.write_text(
            json.dumps({
                "generated_at": datetime.now().isoformat(timespec="seconds"),
                "database_unchanged": True,
                "source_corrections_added_or_verified": evidence_report,
                "resolution_file": str(RESOLUTION),
                "smoke": smoke,
                "backup_dir": str(backup_dir),
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        print()
        print("=" * 118)
        print("CÀI ĐẶT THÀNH CÔNG – CỔNG TIỂU HỌC QĐ3805 ĐÃ SẴN SÀNG XEM TRƯỚC")
        print("Đã khóa 2 điều chỉnh nguồn:")
        for x in evidence_report:
            print(
                f" - {x['staff_code']}: loại Excel row {x['excluded_excel_row']} "
                f"({x['excluded_name']} / {x['excluded_school']}), "
                f"giữ row {x['kept_excel_row']}."
            )
        print("Tri Lễ: tách khỏi batch sáp nhập, chờ xử lý Đổi tên trường.")
        print("Nghi Vạn -> Nghi Diên: nhận ĐÃ HOÀN TẤT TRƯỚC nếu dấu vết dữ liệu khớp.")
        print("Nghi Hoa -> Nghi Trung: nhận ĐÃ HOÀN TẤT TRƯỚC nếu dấu vết dữ liệu khớp.")
        print("STT 1325 Đồng Thành: vẫn CHƯA XÁC ĐỊNH – KHÔNG CHẠY, nhưng không chặn 160 phương án đã rõ.")
        print("Smoke audit:", json.dumps(smoke, ensure_ascii=False))
        print("Database: KHÔNG THAY ĐỔI")
        print("Bộ cài KHÔNG thực hiện sáp nhập.")
        print("Backup:", backup_dir)
        print("Báo cáo:", report)
        print("=" * 118)

    except Exception as exc:
        rollback()
        print("=" * 118)
        print("DỪNG AN TOÀN – ĐÃ KHÔI PHỤC FILE NẾU CÓ THAY ĐỔI")
        print("Lỗi:", exc)
        print("Database: KHÔNG CHỦ ĐỘNG GHI")
        print("=" * 118)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
