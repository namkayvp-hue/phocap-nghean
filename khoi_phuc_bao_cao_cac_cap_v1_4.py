from __future__ import annotations

import json
import shutil
from pathlib import Path

PROJECT = Path(r"C:\PhoCap")
POINTER = PROJECT / "exports" / "pcgd_xmc_v1_4_cac_cap_backup_moi_nhat.txt"

if not POINTER.exists():
    raise SystemExit("Khong tim thay thong tin backup V1.4 cac cap.")
backup = Path(POINTER.read_text(encoding="utf-8-sig").strip())
manifest_path = backup / "manifest.json"
if not manifest_path.exists():
    raise SystemExit(f"Khong tim thay manifest: {manifest_path}")
manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
for rel, info in manifest.items():
    target = PROJECT / rel
    saved = backup / rel
    if info.get("existed"):
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(saved, target)
    elif target.exists():
        target.unlink()
print("DA KHOI PHUC TRANG THAI TRUOC BAO CAO CAC CAP V1.4")
print("Tu:", backup)
