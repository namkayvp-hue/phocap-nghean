# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import json
import py_compile
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(r"C:\PhoCap")
HERE = Path(__file__).resolve().parent

DB = ROOT / "data" / "phocap.db"
SERVICE = ROOT / "app" / "services" / "school_merger_level_batch_service.py"
NEW_SERVICE = HERE / "school_merger_level_batch_service.py"

EXPECTED_CURRENT_SERVICE_HASH = "fee73378f9f32903cc562f783375fcf66c61ffbed0ba8bc3a6b18c9d964a12ad"
EXPECTED_NEW_SERVICE_HASH = "ea5b86cf02395d960f53011352bc7dd4450c556710383c912b473dd21c7d5cf2"

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024*1024), b""):
            h.update(block)
    return h.hexdigest()

def db_integrity() -> tuple[str, int]:
    uri = DB.resolve().as_uri() + "?mode=ro"
    con = sqlite3.connect(uri, uri=True, timeout=30)
    try:
        con.execute("PRAGMA query_only=ON")
        con.execute("PRAGMA foreign_keys=ON")
        integrity = str(con.execute("PRAGMA integrity_check").fetchone()[0])
        fk = con.execute("PRAGMA foreign_key_check").fetchall()
        return integrity, len(fk)
    finally:
        con.close()

def existing_th_batch() -> int:
    uri = DB.resolve().as_uri() + "?mode=ro"
    con = sqlite3.connect(uri, uri=True, timeout=30)
    try:
        con.row_factory = sqlite3.Row
        row = con.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='school_merger_level_batches'"
        ).fetchone()
        if row is None:
            return 0
        return int(con.execute(
            "SELECT COUNT(*) FROM school_merger_level_batches "
            "WHERE school_year_id=2 AND level_code='TH'"
        ).fetchone()[0])
    finally:
        con.close()

def smoke_preview() -> dict:
    code = r"""
import json
from app.services.school_merger_level_batch_service import build_level_batch_preview
p = build_level_batch_preview(school_year_id=2, level_code="TH")
print(json.dumps({
    "counts": p.get("counts"),
    "effective_block_count": p.get("effective_block_count"),
    "candidate_count": p.get("candidate_count"),
    "ready_for_execution": p.get("ready_for_execution"),
    "previous_batch": bool(p.get("previous_batch")),
}, ensure_ascii=False))
"""
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=240,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr or proc.stdout)
    return json.loads((proc.stdout or "").strip().splitlines()[-1])

print("="*118)
print("SỬA LỖI 'database is locked' - SÁP NHẬP TOÀN CẤP TIỂU HỌC QĐ3805")
print("Dự án:", ROOT)
print("Database:", DB)
print("Bộ cài KHÔNG thực hiện sáp nhập và KHÔNG ghi dữ liệu nghiệp vụ.")
print("="*118)

if not ROOT.exists() or not DB.exists() or not SERVICE.exists() or not NEW_SERVICE.exists():
    raise SystemExit("Thiếu file bắt buộc.")
if sha256(SERVICE) != EXPECTED_CURRENT_SERVICE_HASH:
    raise SystemExit(
        "Service hiện tại không đúng nền đã khóa. Hash: " + sha256(SERVICE)
    )
if sha256(NEW_SERVICE) != EXPECTED_NEW_SERVICE_HASH:
    raise SystemExit("File service đi kèm ZIP không đúng hash.")

db_before = sha256(DB)
integrity, fk = db_integrity()
if integrity.lower() != "ok" or fk:
    raise SystemExit(f"Database không đạt hậu kiểm: integrity={integrity}, fk={fk}")

batch_count = existing_th_batch()
if batch_count != 0:
    raise SystemExit(
        f"Đã có {batch_count} nhật ký sáp nhập toàn cấp TH. Dừng để tránh chạy lặp."
    )

# Khi Uvicorn đã dừng, lỗi lock tạm phải biến mất và trạng thái phải trở lại 141/19/0.
before_preview = smoke_preview()
counts = before_preview.get("counts") or {}
if (
    int(counts.get("DONE") or 0) != 141
    or int(counts.get("READY") or 0) != 19
    or int(counts.get("BLOCK") or 0) != 0
    or int(before_preview.get("effective_block_count") or 0) != 0
    or not bool(before_preview.get("ready_for_execution"))
    or bool(before_preview.get("previous_batch"))
):
    raise SystemExit(
        "Trạng thái sau lần lỗi chưa trở về nền an toàn 141 DONE / 19 READY / 0 BLOCK. "
        "Dừng, không cài. Kết quả: " + json.dumps(before_preview, ensure_ascii=False)
    )

stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
backup_dir = ROOT / "backups" / f"backup_truoc_sua_database_locked_TH_{stamp}"
backup_dir.mkdir(parents=True, exist_ok=False)
backup_service = backup_dir / SERVICE.name
shutil.copy2(SERVICE, backup_service)

try:
    shutil.copy2(NEW_SERVICE, SERVICE)
    py_compile.compile(str(SERVICE), doraise=True)

    after_preview = smoke_preview()
    counts2 = after_preview.get("counts") or {}
    if (
        int(counts2.get("DONE") or 0) != 141
        or int(counts2.get("READY") or 0) != 19
        or int(counts2.get("BLOCK") or 0) != 0
        or int(after_preview.get("effective_block_count") or 0) != 0
        or not bool(after_preview.get("ready_for_execution"))
    ):
        raise RuntimeError(
            "Smoke preview sau cài không đạt: "
            + json.dumps(after_preview, ensure_ascii=False)
        )

    db_after = sha256(DB)
    if db_after != db_before:
        raise RuntimeError("Hash phocap.db thay đổi ngoài dự kiến.")

    report_dir = ROOT / "exports" / "Sua_Loi_Database_Locked_TH_QD3805"
    report_dir.mkdir(parents=True, exist_ok=True)
    report = report_dir / f"bao_cao_sua_database_locked_TH_{stamp}.json"
    report.write_text(json.dumps({
        "installed_at": datetime.now().isoformat(timespec="seconds"),
        "database_unchanged": True,
        "integrity": integrity,
        "foreign_key_errors": fk,
        "existing_th_batch_before": batch_count,
        "preview_before": before_preview,
        "preview_after": after_preview,
        "old_service_hash": EXPECTED_CURRENT_SERVICE_HASH,
        "new_service_hash": EXPECTED_NEW_SERVICE_HASH,
        "backup_service": str(backup_service),
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print()
    print("="*118)
    print("CÀI ĐẶT THÀNH CÔNG - ĐÃ SỬA LỖI database is locked")
    print("Nguyên nhân đã sửa: preview/mô phỏng SQLite không còn chạy bên trong BEGIN IMMEDIATE.")
    print("Backup được tạo trước write lock; sau khi lấy lock chỉ dùng một connection ghi duy nhất.")
    print("Trạng thái:", json.dumps(after_preview, ensure_ascii=False))
    print("Database: KHÔNG THAY ĐỔI")
    print("Bộ cài KHÔNG thực hiện sáp nhập.")
    print("Backup source:", backup_dir)
    print("Báo cáo:", report)
    print("="*118)

except Exception as exc:
    try:
        shutil.copy2(backup_service, SERVICE)
    except Exception:
        pass
    print("="*118)
    print("DỪNG AN TOÀN - ĐÃ KHÔI PHỤC SERVICE CŨ")
    print("Lỗi:", exc)
    print("Database: KHÔNG CHỦ ĐỘNG GHI")
    print("="*118)
    raise SystemExit(1)
