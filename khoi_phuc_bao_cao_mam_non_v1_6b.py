from __future__ import annotations

import json
import shutil
from pathlib import Path

PROJECT = Path(r"C:\PhoCap").resolve()
EXPORTS = PROJECT / "exports"

backups = sorted(
    [p for p in EXPORTS.glob("backup_bao_cao_mam_non_v1_6b_*") if p.is_dir()],
    key=lambda p: p.name,
    reverse=True,
)
if not backups:
    print("Khong tim thay ban sao V1.6B.")
    raise SystemExit(1)

backup = backups[0]
manifest_path = backup / "manifest.json"
if not manifest_path.exists():
    print("Ban sao thieu manifest.json")
    raise SystemExit(1)
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

for rel, info in manifest.items():
    target = PROJECT / rel
    saved = backup / rel
    if info.get("existed"):
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(saved, target)
    elif target.exists() and target.is_file():
        target.unlink()

for cache in (PROJECT / "app").rglob("__pycache__"):
    if cache.is_dir():
        shutil.rmtree(cache, ignore_errors=True)

print("KHOI PHUC BAO CAO MAM NON V1.6B THANH CONG")
print("Nguon:", backup)
