from __future__ import annotations
import json, shutil
from pathlib import Path

PROJECT = Path(r"C:\PhoCap")
EXPORTS = PROJECT / "exports"

def main():
    backups = sorted(
        [p for p in EXPORTS.glob("backup_bai_13b_6_v1_5_1_hien_nut_*") if p.is_dir()],
        reverse=True,
    )
    if not backups:
        raise RuntimeError("Không tìm thấy backup V1.5.1.")
    backup = backups[0]
    items = json.loads((backup / "manifest.json").read_text(encoding="utf-8"))
    for item in reversed(items):
        target = PROJECT / item["path"]
        if item["existed"]:
            src = backup / item["path"]
            if src.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, target)
        elif target.exists():
            target.unlink()
    print("ĐÃ KHÔI PHỤC BÀI 13B-6 V1.5.1")
    print("Từ backup:", backup)

if __name__ == "__main__":
    main()
