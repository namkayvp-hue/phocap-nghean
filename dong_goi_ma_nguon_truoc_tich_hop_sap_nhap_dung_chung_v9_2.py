# -*- coding: utf-8 -*-
r"""
ĐÓNG GÓI MÃ NGUỒN C:\PhoCap TRƯỚC KHI TÍCH HỢP CHỨC NĂNG SÁP NHẬP DÙNG CHUNG V9.2

Mục tiêu:
- Tạo ZIP mã nguồn hiện tại để gửi kiểm tra/tích hợp.
- KHÔNG sửa bất kỳ file nào.
- KHÔNG đưa database thật vào ZIP.
- KHÔNG đưa .venv, backups, __pycache__, ZIP/report sinh ra trước đó.

Chạy:
    cd C:\PhoCap
    .\.venv\Scripts\python.exe .\dong_goi_ma_nguon_truoc_tich_hop_sap_nhap_dung_chung_v9_2.py

Kết quả:
    C:\PhoCap\ma_nguon_hien_tai_truoc_tich_hop_sap_nhap_v9_2_<timestamp>.zip
"""

from __future__ import annotations

import os
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(r"C:\PhoCap")

EXCLUDE_DIR_NAMES = {
    ".venv",
    "venv",
    "__pycache__",
    ".git",
    ".idea",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "node_modules",
    "backups",
}

EXCLUDE_FILE_NAMES = {
    "phocap.db",
    "phocap.db-shm",
    "phocap.db-wal",
}

EXCLUDE_SUFFIXES = {
    ".pyc",
    ".pyo",
    ".db",
    ".sqlite",
    ".sqlite3",
}

# Báo cáo/ZIP sinh từ các bước dry-run hoặc migration không cần đóng lại.
EXCLUDE_NAME_PREFIXES = (
    "dry_run_",
    "V5_",
    "V7_",
    "backup_",
    "phocap_truoc_",
)

# Giữ các file mã nguồn .py kể cả tên bài cài đặt; chỉ bỏ ZIP/report lớn.
def should_exclude_file(path: Path) -> bool:
    name = path.name

    if name in EXCLUDE_FILE_NAMES:
        return True

    if path.suffix.lower() in EXCLUDE_SUFFIXES:
        return True

    if path.suffix.lower() == ".zip":
        return True

    # Bỏ file log runtime.
    if path.suffix.lower() in {".log"}:
        return True

    return False


def main() -> None:
    if not ROOT.exists():
        raise SystemExit(f"Không tìm thấy thư mục dự án: {ROOT}")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_path = ROOT / f"ma_nguon_hien_tai_truoc_tich_hop_sap_nhap_v9_2_{ts}.zip"

    included = 0
    skipped = 0
    total_bytes = 0

    with zipfile.ZipFile(
        zip_path,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=6,
    ) as zf:
        for dirpath, dirnames, filenames in os.walk(ROOT):
            current = Path(dirpath)

            # Không đi vào các thư mục loại trừ.
            dirnames[:] = [
                d for d in dirnames
                if d not in EXCLUDE_DIR_NAMES
                and not d.startswith("V5_")
                and not d.startswith("V7_")
                and not d.startswith("dry_run_")
            ]

            for filename in filenames:
                p = current / filename

                # Không tự đóng chính ZIP đầu ra.
                if p.resolve() == zip_path.resolve():
                    continue

                if should_exclude_file(p):
                    skipped += 1
                    continue

                try:
                    rel = p.relative_to(ROOT)
                    zf.write(p, arcname=str(rel))
                    included += 1
                    total_bytes += p.stat().st_size
                except (PermissionError, OSError) as e:
                    print(f"BỎ QUA do không đọc được: {p} -> {e}")
                    skipped += 1

        # Thêm manifest để biết gói được tạo khi nào.
        manifest = (
            "GÓI MÃ NGUỒN TRƯỚC TÍCH HỢP SÁP NHẬP DÙNG CHUNG V9.2\n"
            f"Thời điểm: {datetime.now().isoformat(timespec='seconds')}\n"
            f"Project root: {ROOT}\n"
            f"Số file đưa vào: {included}\n"
            f"Số file bỏ qua: {skipped}\n"
            f"Tổng dung lượng nguồn trước nén: {total_bytes:,} bytes\n"
            "\n"
            "Đã loại trừ:\n"
            "- .venv / venv\n"
            "- backups\n"
            "- __pycache__\n"
            "- database *.db/*.sqlite*\n"
            "- các ZIP cũ\n"
            "- log runtime\n"
        )
        zf.writestr("00_MANIFEST_DONG_GOI_V9_2.txt", manifest)

    print("=" * 100)
    print("ĐÓNG GÓI MÃ NGUỒN THÀNH CÔNG")
    print("=" * 100)
    print(f"Số file mã nguồn: {included}")
    print(f"Số file bỏ qua: {skipped}")
    print(f"ZIP: {zip_path}")
    print()
    print("GỬI LẠI ZIP NÀY ĐỂ TÍCH HỢP CHỨC NĂNG SÁP NHẬP TRƯỜNG DÙNG CHUNG.")


if __name__ == "__main__":
    main()
