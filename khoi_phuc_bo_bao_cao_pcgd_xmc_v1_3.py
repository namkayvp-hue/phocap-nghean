from __future__ import annotations
import json
import shutil
from pathlib import Path

PROJECT = Path(r"C:\PhoCap")
root = PROJECT / "exports"
items = sorted(
    root.glob("backup_pcgd_xmc_v1_3_*"),
    key=lambda p: p.stat().st_mtime,
    reverse=True,
)
if not items:
    print("KHONG TIM THAY BAN SAO V1.3")
    raise SystemExit(1)

backup = items[0]
manifest_path = backup / "manifest.json"
if not manifest_path.exists():
    print("BAN SAO KHONG CO manifest.json:", backup)
    raise SystemExit(1)

manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
for rel, info in manifest.items():
    target = PROJECT / rel
    saved = backup / rel
    if info.get("existed"):
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(saved, target)
    elif target.exists():
        target.unlink()

print("DA KHOI PHUC TRANG THAI TRUOC V1.3")
print("Tu ban sao:", backup)
