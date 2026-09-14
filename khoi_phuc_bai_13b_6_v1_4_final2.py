from __future__ import annotations

import json
import shutil
from pathlib import Path

PROJECT = Path(r"C:\PhoCap").resolve()
EXPORTS = PROJECT / "exports"


def restore_manifest(backup: Path) -> None:
    manifest_path = backup / "manifest.json"
    if not manifest_path.exists():
        raise RuntimeError(f"Không tìm thấy manifest: {manifest_path}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for item in reversed(manifest):
        target = PROJECT / item["path"]
        if item["existed"]:
            src = backup / item["path"]
            if src.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, target)
        elif target.exists() and target.is_file():
            target.unlink()


def main() -> None:
    extras = sorted(
        [
            p for p in EXPORTS.glob("backup_bai_13b_6_v1_4_final2_*")
            if p.is_dir()
        ],
        reverse=True,
    )
    if not extras:
        raise RuntimeError("Không tìm thấy backup FINAL-2.")

    extra = extras[0]
    restore_manifest(extra)

    note = extra / "base_backup_path.txt"
    if note.exists():
        base = Path(note.read_text(encoding="utf-8").strip())
        if base.exists():
            restore_manifest(base)

    print("ĐÃ KHÔI PHỤC BÀI 13B-6 V1.4 FINAL-2")
    print("Backup FINAL-2:", extra)


if __name__ == "__main__":
    main()
