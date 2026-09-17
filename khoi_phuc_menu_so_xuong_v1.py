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
    project = PROJECT
    if len(sys.argv) >= 2:
        project = Path(sys.argv[1]).expanduser().resolve()

    latest = project / "exports" / "menu_so_xuong_v1_backup_moi_nhat.txt"
    if not latest.exists():
        print("KHONG TIM THAY THONG TIN BAN SAO MENU V1.")
        return 1

    backup = Path(latest.read_text(encoding="utf-8-sig").strip())
    manifest_path = backup / "MENU_V1_MANIFEST.json"
    if not manifest_path.exists():
        print(f"KHONG TIM THAY MANIFEST: {manifest_path}")
        return 1

    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    created = set(manifest.get("created_files") or [])

    print("\nKHOI PHUC MENU SO XUONG V1")
    print(f"Ban sao: {backup}")

    # Khôi phục tất cả file đã backup TRỪ database để không làm mất dữ liệu phát sinh sau cài menu.
    for rel in manifest.get("backed_up") or []:
        if rel.replace("\\", "/") == "data/phocap.db":
            continue
        source = backup / rel
        destination = project / rel
        if source.exists():
            copy_with_parent(source, destination)
            print(f"Da khoi phuc: {rel}")

    for rel in created:
        destination = project / rel
        source = backup / rel
        if not source.exists() and destination.exists():
            destination.unlink()
            print(f"Da xoa tep moi cua V1: {rel}")

    print("\nKHOI PHUC GIAO DIEN CU THANH CONG")
    print("Luu y: data/phocap.db KHONG bi phuc hoi/ghi de.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
