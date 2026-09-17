from __future__ import annotations

import os
import shutil
from pathlib import Path

PROJECT = Path(
    os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")
).resolve()

EXPORTS = PROJECT / "exports"
YEAR = PROJECT / "app" / "templates" / "surveys" / "year_records.html"
QUICK = PROJECT / "app" / "templates" / "surveys" / "quick_entry.html"

def main():
    backups = sorted(
        [
            p for p in EXPORTS.glob("backup_giao_vien_mobile_v1_8d_*")
            if p.is_dir()
        ],
        reverse=True,
    )
    if not backups:
        raise RuntimeError("Không tìm thấy backup V1.8D.")

    backup = backups[0]
    src_year = backup / "app" / "templates" / "surveys" / "year_records.html"
    src_quick = backup / "app" / "templates" / "surveys" / "quick_entry.html"

    shutil.copy2(src_year, YEAR)
    shutil.copy2(src_quick, QUICK)

    print("ĐÃ KHÔI PHỤC V1.8D")
    print("Từ backup:", backup)

if __name__ == "__main__":
    main()
