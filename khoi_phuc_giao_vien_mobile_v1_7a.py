from __future__ import annotations

import shutil
from pathlib import Path

PROJECT = Path(r"C:\PhoCap")
EXPORTS = PROJECT / "exports"
MENU = PROJECT / "app" / "templates" / "partials" / "dropdown_menu_v1.html"

backups = sorted(
    [
        p for p in EXPORTS.glob("backup_giao_vien_mobile_v1_7a_*")
        if p.is_dir()
    ],
    key=lambda p: p.name,
    reverse=True,
)

if not backups:
    print("Khong tim thay ban sao V1.7A.")
    raise SystemExit(1)

backup = backups[0]
saved = backup / "app" / "templates" / "partials" / "dropdown_menu_v1.html"

if not saved.exists():
    print("Ban sao thieu dropdown_menu_v1.html")
    raise SystemExit(1)

MENU.parent.mkdir(parents=True, exist_ok=True)
shutil.copy2(saved, MENU)

for cache in (PROJECT / "app").rglob("__pycache__"):
    if cache.is_dir():
        shutil.rmtree(cache, ignore_errors=True)

print("KHOI PHUC GIAO DIEN GIAO VIEN MOBILE V1.7A THANH CONG")
print("Nguon:", backup)
