from __future__ import annotations

import shutil
from pathlib import Path

PROJECT = Path(r"C:\PhoCap").resolve()
EXPORTS = PROJECT / "exports"
HOME = PROJECT / "app" / "templates" / "index.html"

def main():
    backups = sorted(
        [p for p in EXPORTS.glob("backup_giao_vien_mobile_v1_8a_*") if p.is_dir()],
        reverse=True,
    )
    if not backups:
        raise RuntimeError("Khong tim thay backup V1.8A.")

    backup = backups[0]
    src = backup / "app" / "templates" / "index.html"
    if not src.exists():
        raise RuntimeError(f"Khong tim thay file backup: {src}")

    shutil.copy2(src, HOME)
    print("DA KHOI PHUC GIAO VIEN MOBILE V1.8A")
    print("Tu backup:", backup)

if __name__ == "__main__":
    main()
