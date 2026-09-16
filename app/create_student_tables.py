from __future__ import annotations

import shutil
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import inspect, select

from app.database import (
    Base,
    DATABASE_PATH,
    SessionLocal,
    engine,
)

# Import models để SQLAlchemy nhận biết tất cả các bảng.
from app.models import SchoolYear


PROJECT_DIR = Path(__file__).resolve().parent.parent

BACKUP_DIR = PROJECT_DIR / "data" / "backups"


try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, OSError):
    pass


NEW_TABLES = {
    "school_years",
    "classes",
    "students",
    "student_enrollments",
    "import_batches",
    "student_change_logs",
}


def sao_luu_co_so_du_lieu() -> Path | None:
    """
    Sao lưu cơ sở dữ liệu trước khi tạo bảng mới.
    """

    if not DATABASE_PATH.exists():
        return None

    BACKUP_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    backup_path = (
        BACKUP_DIR
        / f"phocap_before_student_tables_{timestamp}.db"
    )

    shutil.copy2(
        DATABASE_PATH,
        backup_path,
    )

    return backup_path


def tao_cac_bang() -> None:
    """
    Tạo những bảng chưa tồn tại.
    """

    Base.metadata.create_all(
        bind=engine
    )


def tao_nam_hoc_mac_dinh() -> bool:
    """
    Tạo năm học 2025-2026 nếu chưa có.

    Trả về True nếu vừa tạo mới.
    """

    with SessionLocal() as db:
        statement = select(SchoolYear).where(
            SchoolYear.code == "2025-2026"
        )

        school_year = db.scalar(statement)

        if school_year is not None:
            return False

        school_year = SchoolYear(
            code="2025-2026",
            name="Năm học 2025-2026",
            start_date=None,
            end_date=None,
            is_active=True,
        )

        db.add(school_year)
        db.commit()

        return True


def kiem_tra_cac_bang() -> tuple[
    set[str],
    set[str],
]:
    """
    Trả về:
    - Các bảng đã có.
    - Các bảng còn thiếu.
    """

    inspector = inspect(engine)

    existing_tables = set(
        inspector.get_table_names()
    )

    missing_tables = (
        NEW_TABLES - existing_tables
    )

    return existing_tables, missing_tables


def main() -> None:
    print("=" * 70)
    print("KHỞI TẠO CƠ SỞ DỮ LIỆU QUẢN LÝ HỌC SINH")
    print("=" * 70)

    backup_path = sao_luu_co_so_du_lieu()

    if backup_path is not None:
        print("Đã sao lưu cơ sở dữ liệu:")
        print(backup_path)
    else:
        print(
            "Chưa có cơ sở dữ liệu cũ để sao lưu."
        )

    print()
    print("Đang tạo các bảng mới...")

    tao_cac_bang()

    nam_hoc_moi = tao_nam_hoc_mac_dinh()

    existing_tables, missing_tables = (
        kiem_tra_cac_bang()
    )

    print()
    print("Kết quả kiểm tra:")

    for table_name in sorted(NEW_TABLES):
        if table_name in existing_tables:
            print(f"- {table_name}: Đã có")
        else:
            print(f"- {table_name}: Chưa có")

    print()

    if missing_tables:
        print("=" * 70)
        print("KHỞI TẠO CHƯA HOÀN THÀNH")
        print("=" * 70)
        print(
            "Các bảng còn thiếu:"
        )

        for table_name in sorted(
            missing_tables
        ):
            print(f"- {table_name}")

        raise SystemExit(1)

    if nam_hoc_moi:
        print(
            "Đã tạo năm học: 2025-2026"
        )
    else:
        print(
            "Năm học 2025-2026 đã tồn tại."
        )

    print()
    print("=" * 70)
    print("KHỞI TẠO THÀNH CÔNG")
    print("=" * 70)
    print(
        "Dữ liệu xã, trường và tài khoản "
        "hiện có được giữ nguyên."
    )
    print(
        "Phần mềm đã sẵn sàng để quản lý "
        "lớp và học sinh."
    )


if __name__ == "__main__":
    main()