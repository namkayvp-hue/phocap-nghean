from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

PROJECT = Path(r"C:\PhoCap")


def copy_with_parent(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def main() -> int:
    project = PROJECT if len(sys.argv) < 2 else Path(sys.argv[1]).expanduser().resolve()
    latest = project / "exports" / "bai_13c_1_th_m1_v2_backup_moi_nhat.txt"
    if not latest.exists():
        print("KHONG TIM THAY THONG TIN BAN SAO V2.")
        return 1

    backup = Path(latest.read_text(encoding="utf-8-sig").strip())
    manifest_path = backup / "BAI_13C_1_TH_M1_V2_MANIFEST.json"
    if not manifest_path.exists():
        print("KHONG TIM THAY MANIFEST:", manifest_path)
        return 1

    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    print("\nDANG KHOI PHUC TRANG THAI TRUOC TH-M1 V2...")
    for rel in reversed(manifest.get("changed_files", [])):
        saved = backup / rel
        current = project / rel
        if saved.exists():
            copy_with_parent(saved, current)
            print("Da khoi phuc:", rel)

    print("\nKHOI PHUC TH-M1 V2 THANH CONG")
    print("Route, app/main.py va data/phocap.db khong bi thay doi.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
