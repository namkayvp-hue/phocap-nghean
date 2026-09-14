# -*- coding: utf-8 -*-
r"""
ĐÓNG GÓI MÃ NGUỒN SAU V9.3.1 TRƯỚC KHI LÀM V9.4
==================================================

Mục tiêu:
- Đóng gói đúng C:\PhoCap hiện tại sau V9.3.1.
- GIỮ file cấu hình:
    data\school_merger_approved_plans.json
- KHÔNG đưa database thật vào ZIP.
- KHÔNG đưa .venv, backups, __pycache__, ZIP/report cũ.
- KHÔNG sửa bất kỳ file nào.

Chạy:
    cd C:\PhoCap
    .\.venv\Scripts\python.exe .\dong_goi_ma_nguon_sau_v9_3_1_truoc_v9_4.py

Kết quả:
    C:\PhoCap\ma_nguon_sau_v9_3_1_truoc_v9_4_<timestamp>.zip
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
    ".log",
}


def exclude_dir(name: str) -> bool:
    if name in EXCLUDE_DIR_NAMES:
        return True
    prefixes = (
        "dry_run_",
        "V5_",
        "V7_",
        "backup_sap_nhap_",
        "backup_ma_nguon_",
    )
    return name.startswith(prefixes)


def exclude_file(path: Path, output_zip: Path) -> bool:
    try:
        if path.resolve() == output_zip.resolve():
            return True
    except OSError:
        pass

    if path.name in EXCLUDE_FILE_NAMES:
        return True

    if path.suffix.lower() in EXCLUDE_SUFFIXES:
        return True

    # Loại tất cả ZIP cũ; file JSON phương án vẫn được giữ.
    if path.suffix.lower() == ".zip":
        return True

    return False


def main() -> None:
    if not ROOT.exists():
        raise SystemExit(f"Không tìm thấy thư mục dự án: {ROOT}")

    plan_file = ROOT / "data" / "school_merger_approved_plans.json"

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_zip = ROOT / f"ma_nguon_sau_v9_3_1_truoc_v9_4_{ts}.zip"

    included = 0
    skipped = 0
    total_bytes = 0
    plan_included = False

    with zipfile.ZipFile(
        output_zip,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=6,
    ) as zf:
        for dirpath, dirnames, filenames in os.walk(ROOT):
            current = Path(dirpath)

            dirnames[:] = [
                d for d in dirnames
                if not exclude_dir(d)
            ]

            for filename in filenames:
                path = current / filename

                if exclude_file(path, output_zip):
                    skipped += 1
                    continue

                try:
                    rel = path.relative_to(ROOT)
                    zf.write(path, arcname=str(rel))
                    included += 1
                    total_bytes += path.stat().st_size

                    if path == plan_file:
                        plan_included = True

                except (PermissionError, OSError) as exc:
                    print(f"BỎ QUA do không đọc được: {path} -> {exc}")
                    skipped += 1

        manifest = (
            "GÓI MÃ NGUỒN SAU V9.3.1 TRƯỚC V9.4\n"
            f"Thời điểm: {datetime.now().isoformat(timespec='seconds')}\n"
            f"Project root: {ROOT}\n"
            f"Số file đưa vào: {included}\n"
            f"Số file bỏ qua: {skipped}\n"
            f"Tổng dung lượng nguồn trước nén: {total_bytes:,} bytes\n"
            f"File phương án có trong gói: {'YES' if plan_included else 'NO'}\n"
            "\n"
            "Đã loại trừ:\n"
            "- .venv / venv\n"
            "- backups\n"
            "- __pycache__\n"
            "- database *.db/*.sqlite*\n"
            "- các ZIP cũ\n"
            "- log runtime\n"
            "\n"
            "File cần giữ để làm V9.4:\n"
            "- data/school_merger_approved_plans.json (nếu đã tồn tại)\n"
        )
        zf.writestr("00_MANIFEST_TRUOC_V9_4.txt", manifest)

    print("=" * 104)
    print("ĐÓNG GÓI MÃ NGUỒN SAU V9.3.1 THÀNH CÔNG")
    print("=" * 104)
    print(f"Số file mã nguồn: {included}")
    print(f"Số file bỏ qua: {skipped}")
    print(
        "File phương án school_merger_approved_plans.json: "
        + ("ĐÃ CÓ TRONG GÓI" if plan_included else "CHƯA TỒN TẠI / KHÔNG TÌM THẤY")
    )
    print(f"ZIP: {output_zip}")
    print()
    print("GỬI LẠI ZIP NÀY ĐỂ LÀM V9.4 - QUẢN LÝ PHƯƠNG ÁN THEO VĂN BẢN.")


if __name__ == "__main__":
    main()
