from __future__ import annotations

import json
import shutil
from pathlib import Path

PROJECT = Path(r"C:\PhoCap")
EXPORTS = PROJECT / "exports"


def main() -> None:
    backups = sorted(
        [p for p in EXPORTS.glob("backup_bai_13b_7_v1_thpt_*") if p.is_dir()],
        reverse=True,
    )
    if not backups:
        raise RuntimeError("Không tìm thấy backup Bài 13B-7 V1.")

    backup = backups[0]
    manifest = json.loads((backup / "manifest.json").read_text(encoding="utf-8"))

    for item in reversed(manifest):
        target = PROJECT / item["path"]
        if item["existed"]:
            src = backup / item["path"]
            if src.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, target)
        elif target.exists() and target.is_file():
            target.unlink()

    print("ĐÃ KHÔI PHỤC FILE BÀI 13B-7 V1")
    print("Từ backup:", backup)
    print("Các bảng thpt_* trong database không bị xóa tự động để tránh rủi ro dữ liệu.")


if __name__ == "__main__":
    main()
