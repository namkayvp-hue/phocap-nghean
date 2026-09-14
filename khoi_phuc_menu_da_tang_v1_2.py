from __future__ import annotations

import shutil
import sys
from pathlib import Path

PROJECT = Path(r"C:\PhoCap")
PARTIAL_REL = Path("app/templates/partials/dropdown_menu_v1.html")


def main() -> int:
    project = PROJECT
    if len(sys.argv) >= 2:
        project = Path(sys.argv[1]).expanduser().resolve()

    latest = project / "exports" / "menu_so_xuong_v1_2_backup_moi_nhat.txt"
    if not latest.exists():
        print("KHONG TIM THAY THONG TIN BAN SAO V1.2.")
        return 1

    backup = Path(latest.read_text(encoding="utf-8-sig").strip())
    saved = backup / PARTIAL_REL
    target = project / PARTIAL_REL

    if not saved.exists():
        print(f"KHONG TIM THAY TEP MENU TRONG BAN SAO: {saved}")
        return 1

    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(saved, target)
    print("DA KHOI PHUC MENU VE TRANG THAI TRUOC V1.2.")
    print(f"Nguon khoi phuc: {backup}")
    print("KHONG THAY DOI app/main.py HOAC data/phocap.db.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
