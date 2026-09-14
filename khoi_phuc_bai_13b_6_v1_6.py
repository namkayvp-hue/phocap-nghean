from __future__ import annotations
import shutil
from pathlib import Path

PROJECT = Path(r"C:\PhoCap")
EXPORTS = PROJECT / "exports"

def main():
    backups = sorted(
        [p for p in EXPORTS.glob("backup_bai_13b_6_v1_6_hien_day_du_ten_truong_*") if p.is_dir()],
        reverse=True,
    )
    if not backups:
        raise RuntimeError("Không tìm thấy backup V1.6.")
    backup = backups[0]
    src = backup / "app" / "templates" / "schools" / "list.html"
    dst = PROJECT / "app" / "templates" / "schools" / "list.html"
    shutil.copy2(src, dst)
    print("ĐÃ KHÔI PHỤC BÀI 13B-6 V1.6")
    print("Từ backup:", backup)

if __name__ == "__main__":
    main()
