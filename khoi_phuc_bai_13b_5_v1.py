from __future__ import annotations

import shutil
from pathlib import Path

PROJECT = Path(r"C:\PhoCap").resolve()
EXPORTS = PROJECT / "exports"
MENU = PROJECT / "app" / "templates" / "partials" / "dropdown_menu_v1.html"

def main():
    backups = sorted(
        [p for p in EXPORTS.glob("backup_bai_13b_5_v1_*") if p.is_dir()],
        reverse=True,
    )
    if not backups:
        raise RuntimeError("Không tìm thấy backup Bài 13B-5 V1.")
    backup = backups[0]
    src = backup / "app" / "templates" / "partials" / "dropdown_menu_v1.html"
    if not src.exists():
        raise RuntimeError(f"Không tìm thấy: {src}")
    shutil.copy2(src, MENU)
    print("ĐÃ KHÔI PHỤC BÀI 13B-5 V1")
    print("Từ backup:", backup)

if __name__ == "__main__":
    main()
