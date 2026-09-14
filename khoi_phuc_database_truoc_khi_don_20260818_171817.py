from __future__ import annotations

import shutil
import sqlite3
import traceback
from datetime import datetime
from pathlib import Path

PROJECT = Path(r"C:\PhoCap")
CURRENT_DB = PROJECT / "data" / "phocap.db"

BACKUP_DIR = PROJECT / "exports" / "backup_truoc_don_du_lieu_2026_2027_20260818_171817"
BACKUP_DB = BACKUP_DIR / "phocap.db"

EXPORTS = PROJECT / "exports"
STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
SAFETY_DIR = EXPORTS / f"backup_sau_khi_da_don_truoc_khi_khoi_phuc_{STAMP}"
SAFETY_DB = SAFETY_DIR / "phocap.db"


def integrity_check(path: Path) -> str:
    con = sqlite3.connect(str(path))
    try:
        row = con.execute("PRAGMA integrity_check").fetchone()
        return str(row[0] if row else "")
    finally:
        con.close()


def scalar(path: Path, sql: str, params=()):
    con = sqlite3.connect(str(path))
    try:
        row = con.execute(sql, params).fetchone()
        return row[0] if row else None
    finally:
        con.close()


def main() -> int:
    print("=" * 100)
    print("KHÔI PHỤC DATABASE TRƯỚC KHI DỌN DỮ LIỆU 2026-2027")
    print("=" * 100)
    print()
    print("Nguồn backup:")
    print(BACKUP_DB)
    print()
    print("Database hiện tại:")
    print(CURRENT_DB)
    print()
    print("LƯU Ý: hãy DỪNG Uvicorn trước khi chạy script này.")
    print()

    if not BACKUP_DB.exists():
        raise RuntimeError(
            f"Không tìm thấy backup bắt buộc: {BACKUP_DB}"
        )

    if not CURRENT_DB.exists():
        raise RuntimeError(
            f"Không tìm thấy database hiện tại: {CURRENT_DB}"
        )

    source_integrity = integrity_check(BACKUP_DB)
    print("Integrity backup nguồn:", source_integrity)

    if source_integrity.lower() != "ok":
        raise RuntimeError(
            "Backup nguồn không đạt integrity_check. Không khôi phục."
        )

    # Giữ lại database sau khi đã dọn để có đường lui.
    SAFETY_DIR.mkdir(parents=True, exist_ok=False)
    shutil.copy2(CURRENT_DB, SAFETY_DB)

    print()
    print("Đã lưu database hiện tại trước khi khôi phục:")
    print(SAFETY_DB)

    # Loại WAL/SHM cũ sau khi server đã dừng.
    for suffix in ("-wal", "-shm"):
        sidecar = Path(str(CURRENT_DB) + suffix)
        if sidecar.exists():
            sidecar.unlink()

    # Khôi phục nguyên database trước khi dọn.
    shutil.copy2(BACKUP_DB, CURRENT_DB)

    restored_integrity = integrity_check(CURRENT_DB)
    print()
    print("Integrity database sau khôi phục:", restored_integrity)

    if restored_integrity.lower() != "ok":
        print("Khôi phục không đạt. Đang trả lại database sau khi dọn...")
        shutil.copy2(SAFETY_DB, CURRENT_DB)
        raise RuntimeError(
            "Database sau khôi phục không đạt integrity_check."
        )

    # Kiểm tra nhanh dữ liệu 2026-2027 nếu các bảng tồn tại.
    try:
        batch_count = scalar(
            CURRENT_DB,
            """
            SELECT COUNT(*)
            FROM survey_batches sb
            JOIN school_years sy ON sy.id = sb.school_year_id
            WHERE sy.code = '2026-2027'
            """
        )
        form_count = scalar(
            CURRENT_DB,
            """
            SELECT COUNT(*)
            FROM survey_forms sf
            JOIN survey_batches sb ON sb.id = sf.survey_batch_id
            JOIN school_years sy ON sy.id = sb.school_year_id
            WHERE sy.code = '2026-2027'
            """
        )

        print()
        print("Kiểm tra nhanh sau khôi phục:")
        print(" - Đợt 2026-2027:", batch_count)
        print(" - Phiếu điều tra 2026-2027:", form_count)
    except Exception:
        pass

    print()
    print("=" * 100)
    print("KHÔI PHỤC THÀNH CÔNG")
    print("=" * 100)
    print()
    print("Bây giờ có thể chạy lại Uvicorn.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        raise SystemExit(1)
