from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

PROJECT = Path(r"C:\PhoCap")
PARTIAL_REL = Path("app/templates/partials/dropdown_menu_v1.html")

def copy_with_parent(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)

def main() -> int:
    project = PROJECT
    if len(sys.argv) >= 2:
        project = Path(sys.argv[1]).expanduser().resolve()
    latest = project / "exports" / "menu_so_xuong_v1_4_backup_moi_nhat.txt"
    if not latest.exists():
        print("KHONG TIM THAY THONG TIN BAN SAO V1.4.")
        return 1
    backup = Path(latest.read_text(encoding="utf-8").strip())
    manifest_path = backup / "MENU_V1_4_MANIFEST.json"
    if not manifest_path.exists():
        print(f"KHONG TIM THAY MANIFEST: {manifest_path}")
        return 1
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    print("\nKHOI PHUC MENU VE TRANG THAI TRUOC V1.4")
    print(f"Ban sao: {backup}")
    backup_templates = backup / "app" / "templates"
    if backup_templates.exists():
        for source in backup_templates.rglob("*.html"):
            rel = source.relative_to(backup)
            copy_with_parent(source, project / rel)
    partial_path = project / PARTIAL_REL
    saved_partial = backup / PARTIAL_REL
    if saved_partial.exists():
        copy_with_parent(saved_partial, partial_path)
    elif PARTIAL_REL.as_posix() in set(manifest.get("created_files", [])) and partial_path.exists():
        partial_path.unlink()
    print("DA KHOI PHUC GIAO DIEN TRUOC V1.4.")
    print("KHONG KHOI PHUC / GHI DE CO SO DU LIEU.")
    print("KHONG THAY DOI app/main.py HOAC app/routers.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
