from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

PROJECT = Path(os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")).resolve()
EXPORTS = PROJECT / "exports"


def main():
    backups = sorted(
        [p for p in EXPORTS.glob("backup_giao_vien_mobile_v1_8_*") if p.is_dir()],
        reverse=True,
    )
    if not backups:
        raise RuntimeError("Khong tim thay backup Giao vien Mobile V1.8.")

    backup = backups[0]
    manifest_path = backup / "manifest.json"
    if not manifest_path.exists():
        raise RuntimeError(f"Khong tim thay manifest: {manifest_path}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for rel, info in manifest.items():
        dst = PROJECT / rel
        src = backup / rel
        if info.get("existed"):
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        elif dst.exists():
            dst.unlink()

    print("DA KHOI PHUC TRUOC GIAO VIEN MOBILE V1.8")
    print("Tu backup:", backup)


if __name__ == "__main__":
    main()
