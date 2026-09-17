from __future__ import annotations

import json
import shutil
from pathlib import Path

PROJECT = Path(r"C:\PhoCap")
EXPORTS = PROJECT / "exports"

backups = sorted(
    [
        p for p in EXPORTS.glob("backup_giao_vien_mobile_v1_7c_*")
        if p.is_dir()
    ],
    key=lambda p: p.name,
    reverse=True,
)

if not backups:
    print("Khong tim thay backup V1.7C.")
    raise SystemExit(1)

backup = backups[0]
manifest = json.loads(
    (backup / "manifest.json").read_text(encoding="utf-8")
)

for rel, info in manifest.items():
    if not info.get("existed"):
        continue
    src = backup / rel
    dst = PROJECT / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)

for cache in (PROJECT / "app").rglob("__pycache__"):
    if cache.is_dir():
        shutil.rmtree(cache, ignore_errors=True)

print("KHOI PHUC GIAO VIEN MOBILE V1.7C THANH CONG")
print("Nguon:", backup)
