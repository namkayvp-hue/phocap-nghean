from __future__ import annotations

import shutil
from pathlib import Path

PROJECT = Path(r"C:\PhoCap").resolve()
EXPORTS = PROJECT / "exports"

backups = sorted(
    [
        p
        for p in EXPORTS.glob("backup_sua_bao_cao_tre_3_5_tuoi_v1_*")
        if p.is_dir()
    ],
    key=lambda p: p.name,
    reverse=True,
)

if not backups:
    print("Khong tim thay ban sao SUA BAO CAO TRE 3-5 TUOI V1.")
    raise SystemExit(1)

backup = backups[0]
print("Dang khoi phuc tu:", backup)

for rel in [
    Path("app/main.py"),
    Path("app/routers/preschool_3_5_report.py"),
    Path("app/templates/reports/preschool_3_5_report.html"),
    Path("data/phocap.db"),
]:
    saved = backup / rel
    target = PROJECT / rel
    if saved.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(saved, target)

for cache in (PROJECT / "app").rglob("__pycache__"):
    if cache.is_dir():
        shutil.rmtree(cache, ignore_errors=True)

print("KHOI PHUC BAO CAO TRE 3-5 TUOI V1 THANH CONG")
