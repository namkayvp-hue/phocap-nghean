from __future__ import annotations

import shutil
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import inspect

from app.database import Base, DATABASE_PATH, engine
from app.models import Commune, SchoolYear, User  # noqa: F401
from app.survey_models import (
    Household,  # noqa: F401
    SurveyBatch,  # noqa: F401
    SurveyFileExchangeLog,  # noqa: F401
    SurveyForm,  # noqa: F401
    SurveyPerson,  # noqa: F401
)


PROJECT_DIR = Path(__file__).resolve().parent.parent
BACKUP_DIR = PROJECT_DIR / "data" / "backups"
TABLE_NAME = "survey_file_exchange_logs"


try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, OSError):
    pass


def sao_luu_co_so_du_lieu() -> Path | None:
    if not DATABASE_PATH.exists():
        return None

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = (
        BACKUP_DIR
        / f"before_bai_12d_12_{timestamp}.db"
    )
    shutil.copy2(DATABASE_PATH, backup_path)
    return backup_path


def main() -> None:
    print("=" * 72)
    print("NÂNG CẤP BÀI 12D-12")
    print("TRUNG TÂM PHÁT HÀNH VÀ TIẾP NHẬN PHIẾU ĐIỀU TRA")
    print("=" * 72)

    backup_path = sao_luu_co_so_du_lieu()
    print()
    if backup_path is None:
        print("Chưa có cơ sở dữ liệu cũ để sao lưu.")
    else:
        print("Đã sao lưu cơ sở dữ liệu:")
        print(backup_path)

    print()
    print("Đang tạo bảng nhật ký phát hành và tiếp nhận...")
    Base.metadata.create_all(bind=engine)

    tables = set(inspect(engine).get_table_names())
    if TABLE_NAME not in tables:
        print()
        print("NÂNG CẤP KHÔNG THÀNH CÔNG.")
        print(f"Chưa tạo được bảng {TABLE_NAME}.")
        raise SystemExit(1)

    print()
    print(f"- {TABLE_NAME}: Đã có")
    print()
    print("=" * 72)
    print("NÂNG CẤP BÀI 12D-12 THÀNH CÔNG.")
    print("Có thể khởi động lại phần mềm.")
    print("=" * 72)


if __name__ == "__main__":
    main()
