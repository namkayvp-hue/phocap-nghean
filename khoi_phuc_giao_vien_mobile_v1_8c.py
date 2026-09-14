from __future__ import annotations

import os
import shutil
from pathlib import Path

PROJECT = Path(
    os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")
).resolve()

EXPORTS = PROJECT / "exports"
TARGET = PROJECT / "app" / "templates" / "surveys" / "index.html"

def main():
    backups = sorted(
        [
            p for p in EXPORTS.glob("backup_giao_vien_mobile_v1_8c_*")
            if p.is_dir()
        ],
        reverse=True,
    )
    if not backups:
        raise RuntimeError("Không tìm thấy backup V1.8C.")

    backup = backups[0]
    src = backup / "app" / "templates" / "surveys" / "index.html"
    if not src.exists():
        raise RuntimeError(f"Không tìm thấy: {src}")

    shutil.copy2(src, TARGET)
    print("ĐÃ KHÔI PHỤC V1.8C")
    print("Từ backup:", backup)

if __name__ == "__main__":
    main()
