from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

PROJECT = Path(r"C:\PhoCap")


def copy_with_parent(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def main() -> int:
    project = PROJECT if len(sys.argv) < 2 else Path(sys.argv[1]).expanduser().resolve()
    latest = project / "exports" / "pcgd_xmc_v1_5_backup_moi_nhat.txt"
    if not latest.exists():
        print("KHONG TIM THAY THONG TIN BAN SAO V1.5.")
        return 1
    backup = Path(latest.read_text(encoding="utf-8-sig").strip())
    manifest_path = backup / "PCGD_XMC_V1_5_MANIFEST.json"
    if not manifest_path.exists():
        print(f"KHONG TIM THAY MANIFEST: {manifest_path}")
        return 1
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    changed = manifest.get("changed_files", [])
    created = set(manifest.get("created_files", []))

    print("\nDANG KHOI PHUC TRANG THAI TRUOC PCGD & XMC V1.5...")
    for rel in reversed(changed):
        current = project / rel
        saved = backup / rel
        if saved.exists():
            copy_with_parent(saved, current)
            print("Da khoi phuc:", rel)
        elif rel in created and current.exists() and current.is_file():
            current.unlink()
            print("Da xoa tep V1.5 tao moi:", rel)

    print("\nKHOI PHUC PCGD & XMC V1.5 THANH CONG")
    print("app/main.py, route va data/phocap.db khong bi thay doi boi V1.5.")
    print("Ban sao da dung:", backup)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
