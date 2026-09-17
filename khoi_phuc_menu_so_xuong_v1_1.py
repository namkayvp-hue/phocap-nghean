from __future__ import annotations

import shutil
import sys
from pathlib import Path

PROJECT = Path(r"C:\PhoCap")


def copy_with_parent(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def main() -> int:
    project = PROJECT
    if len(sys.argv) >= 2:
        project = Path(sys.argv[1]).expanduser().resolve()

    latest = project / "exports" / "menu_so_xuong_v1_1_backup_moi_nhat.txt"
    if not latest.exists():
        print("KHONG TIM THAY THONG TIN BAN SAO MENU V1.1")
        return 1

    backup = Path(latest.read_text(encoding="utf-8-sig").strip())
    targets = [
        "app/templates/partials/dropdown_menu_v1.html",
        "app/static/css/style.css",
    ]

    print("\nKHOI PHUC MENU SO XUONG TRUOC V1.1")
    print(f"Ban sao: {backup}")
    for rel in targets:
        src = backup / rel
        dst = project / rel
        if not src.exists():
            print(f"THIEU TEP BACKUP: {src}")
            return 1
        copy_with_parent(src, dst)
        print(f"Da khoi phuc: {rel}")

    print("\nKHOI PHUC GIAO DIEN TRUOC V1.1 THANH CONG")
    print("app/main.py va data/phocap.db KHONG BI THAY DOI.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
