from __future__ import annotations

import shutil
import sys
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import inspect, select

from app.database import Base, DATABASE_PATH, SessionLocal, engine
from app.models import Commune, SchoolYear, Student, User  # noqa: F401
from app.survey_models import (
    HistoricalDataLog,
    HistoricalDataset,
    HistoricalHousehold,
    HistoricalPerson,
    Household,  # noqa: F401
    SurveyBatch,  # noqa: F401
    SurveyForm,  # noqa: F401
    SurveyPerson,  # noqa: F401
)


PROJECT_DIR = Path(__file__).resolve().parent.parent
BACKUP_DIR = PROJECT_DIR / "data" / "backups"

REQUIRED_TABLES = {
    "historical_datasets",
    "historical_households",
    "historical_people",
    "historical_data_logs",
}

HISTORICAL_YEARS = tuple(
    f"{start}-{start + 1}"
    for start in range(2020, 2026)
)


try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, OSError):
    pass


def backup_database() -> Path | None:
    if not DATABASE_PATH.exists():
        return None

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"before_bai_12d_14a_{timestamp}.db"
    shutil.copy2(DATABASE_PATH, backup_path)
    return backup_path


def ensure_historical_years() -> tuple[int, int]:
    created = 0
    existing = 0

    with SessionLocal() as db:
        existing_codes = set(
            db.scalars(
                select(SchoolYear.code).where(
                    SchoolYear.code.in_(HISTORICAL_YEARS)
                )
            ).all()
        )

        for code in HISTORICAL_YEARS:
            if code in existing_codes:
                existing += 1
                continue

            start_year = int(code[:4])
            db.add(
                SchoolYear(
                    code=code,
                    name=f"Năm học {code}",
                    start_date=date(start_year, 7, 1),
                    end_date=date(start_year + 1, 6, 30),
                    is_active=True,
                )
            )
            created += 1

        db.commit()

    return created, existing


def main() -> None:
    print("=" * 76)
    print("NÂNG CẤP BÀI 12D-14A")
    print("TRUNG TÂM CẬP NHẬT DỮ LIỆU LỊCH SỬ")
    print("=" * 76)

    backup_path = backup_database()
    print()
    if backup_path is None:
        print("Chưa có cơ sở dữ liệu cũ để sao lưu.")
    else:
        print("Đã sao lưu cơ sở dữ liệu:")
        print(backup_path)

    print()
    print("Đang tạo các bảng dữ liệu lịch sử...")
    Base.metadata.create_all(bind=engine)

    tables = set(inspect(engine).get_table_names())
    missing_tables = sorted(REQUIRED_TABLES - tables)
    if missing_tables:
        print()
        print("NÂNG CẤP KHÔNG THÀNH CÔNG.")
        print("Chưa tạo được các bảng:")
        for table_name in missing_tables:
            print(f"- {table_name}")
        raise SystemExit(1)

    created_years, existing_years = ensure_historical_years()

    print()
    for table_name in sorted(REQUIRED_TABLES):
        print(f"- {table_name}: Đã có")
    print()
    print(f"- Năm học lịch sử đã có trước: {existing_years}")
    print(f"- Năm học lịch sử được tạo mới: {created_years}")
    print("- Phạm vi năm học: 2020-2021 đến 2025-2026")
    print()
    print("=" * 76)
    print("NÂNG CẤP BÀI 12D-14A THÀNH CÔNG.")
    print("Có thể khởi động lại phần mềm.")
    print("=" * 76)


if __name__ == "__main__":
    main()
