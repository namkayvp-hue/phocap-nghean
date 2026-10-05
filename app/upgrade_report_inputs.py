from __future__ import annotations

import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import inspect

from app.database import Base, DATABASE_PATH, engine
import app.models  # noqa: F401  (đăng ký bảng cha cho khoá ngoại)
import app.report_input_models as report_input_models


PROJECT_DIR = Path(__file__).resolve().parent.parent
BACKUP_DIR = PROJECT_DIR / "data" / "backups"


try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, OSError):
    pass


def lay_bang_nhap_lieu_bao_cao() -> list:
    """Các bảng khai báo trong app/report_input_models.py."""
    return [
        table
        for table in Base.metadata.sorted_tables
        if table.name
        in {
            mapper.local_table.name
            for mapper in Base.registry.mappers
            if mapper.class_.__module__ == report_input_models.__name__
        }
    ]


def sao_luu_co_so_du_lieu() -> Path | None:
    if not DATABASE_PATH.exists():
        return None

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"phocap_truoc_upgrade_report_inputs_{timestamp}.db"

    # Dùng backup API của sqlite3 để an toàn khi app đang ghi.
    nguon = sqlite3.connect(DATABASE_PATH)
    dich = sqlite3.connect(backup_path)
    try:
        nguon.backup(dich)
    finally:
        dich.close()
        nguon.close()
    return backup_path


def main() -> None:
    print("=" * 72)
    print("NÂNG CẤP CSDL: CÁC BẢNG NHẬP LIỆU BÁO CÁO (report_input_models)")
    print("=" * 72)

    bang_can_co = lay_bang_nhap_lieu_bao_cao()
    da_co = set(inspect(engine).get_table_names())
    bang_thieu = [table for table in bang_can_co if table.name not in da_co]

    print()
    if not bang_thieu:
        print("Tất cả bảng đã có đủ, không cần nâng cấp.")
        return

    print("Các bảng còn thiếu:")
    for table in bang_thieu:
        print(f"  - {table.name}")

    backup_path = sao_luu_co_so_du_lieu()
    print()
    if backup_path is None:
        print("Chưa có cơ sở dữ liệu cũ để sao lưu.")
    else:
        print("Đã sao lưu cơ sở dữ liệu:")
        print(backup_path)

    # Chỉ tạo đúng các bảng thiếu; không động tới bảng/dữ liệu đang có.
    Base.metadata.create_all(bind=engine, tables=bang_thieu, checkfirst=True)

    da_co = set(inspect(engine).get_table_names())
    van_thieu = [table.name for table in bang_thieu if table.name not in da_co]
    print()
    if van_thieu:
        print("NÂNG CẤP KHÔNG THÀNH CÔNG.")
        print("Chưa tạo được bảng: " + ", ".join(van_thieu))
        raise SystemExit(1)

    print("NÂNG CẤP THÀNH CÔNG.")
    print("Đã tạo: " + ", ".join(table.name for table in bang_thieu))


if __name__ == "__main__":
    main()
