from __future__ import annotations

import py_compile
import shutil
import sys
from datetime import datetime
from pathlib import Path

BUNDLE_DIR = Path(__file__).resolve().parent
DEFAULT_PROJECT = Path(r"C:\PhoCap")
FILES = (Path("app/routers/pcgdmn_template_report.py"),)
REQUIRED_MARKER = "BAI_13B_12_V2_4_3_16_MN02_CONCLUSION_FROM_VISIBLE_TOTALS"


def main() -> int:
    project_dir = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else DEFAULT_PROJECT
    if not project_dir.exists():
        print(f"[LOI] Khong tim thay thu muc du an: {project_dir}")
        return 1

    source_file = BUNDLE_DIR / FILES[0]
    if not source_file.is_file():
        print(f"[LOI] Thieu tep trong bo cai: {source_file}")
        return 1
    if REQUIRED_MARKER not in source_file.read_text(encoding="utf-8"):
        print("[LOI] Tep bo cai khong dung phien ban V2.4.3.16.")
        return 1

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = project_dir / "backups" / f"backup_bai_13b_12_v2_4_3_16_{timestamp}"
    backup_dir.mkdir(parents=True, exist_ok=False)

    copied: list[tuple[Path, Path]] = []
    try:
        print("BAI 13B-12 V2.4.3.16")
        print("- MN-02 cap Xa: ket luan tu chinh tong so tre 3-5 tren bieu MN-02.")
        print("- Khong con doi hoi tach du lieu hoan thanh rieng tung tuoi 3, 4, 5.")
        print("- Giu nguyen ban va quyen dien thoai V2.4.3.15 da cai.")
        print("- Khong sua database, giao dien, menu hay luong thao tac.")
        print()

        for relative in FILES:
            source = BUNDLE_DIR / relative
            target = project_dir / relative
            if not target.is_file():
                raise FileNotFoundError(f"Khong tim thay tep hien tai: {target}")

            backup_target = backup_dir / relative
            backup_target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, backup_target)
            copied.append((target, backup_target))
            print(f"[BACKUP] {relative}")

            shutil.copy2(source, target)
            print(f"[CAP NHAT] {relative}")

        for relative in FILES:
            py_compile.compile(str(project_dir / relative), doraise=True)
        print("[KIEM TRA] Cu phap Python: OK")

    except Exception as exc:
        print(f"[LOI] {type(exc).__name__}: {exc}")
        print("Dang khoi phuc tep da sao luu...")
        for target, backup_target in reversed(copied):
            if backup_target.is_file():
                shutil.copy2(backup_target, target)
                print(f"[KHOI PHUC] {target}")
        print("Du an da duoc dua ve trang thai truoc khi cai dat.")
        return 1

    print()
    print("=== CAI DAT THANH CONG ===")
    print(f"Ban sao an toan: {backup_dir}")
    print("Database phocap.db khong bi thay doi.")
    print("Khoi dong lai Uvicorn va xuat lai MN-02 cap Xa.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
