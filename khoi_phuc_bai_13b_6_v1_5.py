from __future__ import annotations

import json
import shutil
from pathlib import Path

PROJECT = Path(r"C:\PhoCap").resolve()
EXPORTS = PROJECT / "exports"


def main() -> None:
    backups = sorted(
        [
            p for p in EXPORTS.glob(
                "backup_bai_13b_6_v1_5_cap_tat_ca_tai_khoan_*"
            )
            if p.is_dir()
        ],
        reverse=True,
    )
    if not backups:
        raise RuntimeError("Không tìm thấy backup Bài 13B-6 V1.5.")

    backup = backups[0]
    manifest = json.loads(
        (backup / "manifest.json").read_text(encoding="utf-8")
    )

    for item in reversed(manifest):
        target = PROJECT / item["path"]
        if item["existed"]:
            src = backup / item["path"]
            if src.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, target)
        elif target.exists() and target.is_file():
            target.unlink()

    print("ĐÃ KHÔI PHỤC BÀI 13B-6 V1.5")
    print("Từ backup:", backup)


if __name__ == "__main__":
    main()
