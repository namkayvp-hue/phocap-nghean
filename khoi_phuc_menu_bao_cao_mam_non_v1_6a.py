from __future__ import annotations

import shutil
from pathlib import Path

PROJECT = Path(r"C:\PhoCap").resolve()
EXPORTS = PROJECT / "exports"
PARTIAL = PROJECT / "app" / "templates" / "partials" / "dropdown_menu_v1.html"

backups = sorted(
    [
        p for p in EXPORTS.glob("backup_menu_bao_cao_mam_non_v1_6a_*")
        if p.is_dir()
    ],
    key=lambda p: p.name,
    reverse=True,
)

if not backups:
    print("Khong tim thay ban sao Menu Mam non V1.6A.")
    raise SystemExit(1)

backup = backups[0]
saved = backup / "app" / "templates" / "partials" / "dropdown_menu_v1.html"

if not saved.exists():
    print("Ban sao khong co dropdown_menu_v1.html.")
    raise SystemExit(1)

PARTIAL.parent.mkdir(parents=True, exist_ok=True)
shutil.copy2(saved, PARTIAL)

for cache in (PROJECT / "app").rglob("__pycache__"):
    if cache.is_dir():
        shutil.rmtree(cache, ignore_errors=True)

print("KHOI PHUC MENU BAO CAO MAM NON V1.6A THANH CONG")
print("Nguon:", backup)
