from __future__ import annotations
import shutil
from pathlib import Path

PROJECT = Path(r"C:\PhoCap")
EXPORTS = PROJECT / "exports"
TARGET = PROJECT / "app" / "pcgd_xmc_report_builders_v1.py"

backups = sorted(
    [p for p in EXPORTS.glob("backup_pcgd_xmc_v1_2_*") if p.is_dir()],
    key=lambda p: p.stat().st_mtime,
    reverse=True,
)
if not backups:
    raise SystemExit("Không tìm thấy bản sao V1.2 để khôi phục.")
backup = backups[0]
saved = backup / "app" / "pcgd_xmc_report_builders_v1.py"
if not saved.exists():
    raise SystemExit(f"Bản sao không có tệp cần khôi phục: {saved}")
shutil.copy2(saved, TARGET)
print("KHOI PHUC BO BAO CAO PCGD & XMC V1.2 THANH CONG")
print(f"Da khoi phuc tu: {backup}")
