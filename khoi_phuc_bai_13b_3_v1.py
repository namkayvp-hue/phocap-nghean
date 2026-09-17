from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

PROJECT = Path(os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")).resolve()
EXPORTS = PROJECT / "exports"
DB = PROJECT / "data" / "phocap.db"


def main() -> int:
    backups = sorted(
        [p for p in EXPORTS.glob("backup_bai_13b_3_v1_*") if p.is_dir()],
        reverse=True,
    )
    if not backups:
        raise RuntimeError("Không tìm thấy backup Bài 13B-3 V1.")

    backup = backups[0]
    manifest_path = backup / "manifest.json"
    if not manifest_path.exists():
        raise RuntimeError(f"Không tìm thấy manifest: {manifest_path}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    for item in reversed(manifest):
        rel = item["path"]
        target = PROJECT / rel
        if item.get("existed"):
            src = backup / rel
            if not src.exists():
                raise RuntimeError(f"Thiếu tệp backup: {src}")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, target)
        else:
            if target.exists() and target.is_file():
                target.unlink()

    backup_db = backup / "data" / "phocap.db"
    if backup_db.exists():
        DB.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(backup_db, DB)

    for cache in (PROJECT / "app").rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(cache, ignore_errors=True)

    print("ĐÃ KHÔI PHỤC BÀI 13B-3 V1")
    print("Từ backup:", backup)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
