from __future__ import annotations

import shutil
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import (
    func,
    inspect,
    select,
)

from app.database import (
    Base,
    DATABASE_PATH,
    SessionLocal,
    engine,
)

# Phải import các model cũ trước
# để SQLAlchemy nhận biết Commune, User,
# SchoolYear, School, Classroom và Student.
from app.models import (
    Commune,
    School,
    Student,
    User,
)

# Import các bảng điều tra mới.
from app.survey_models import (
    Household,
    SurveyBatch,
    SurveyBatchLockLog,
    SurveyForm,
    SurveyFormInvestigator,
    SurveyPerson,
    SurveyPersonYearRecord,
    SurveyFileExchangeLog,
    HistoricalDataset,
    HistoricalHousehold,
    HistoricalPerson,
    HistoricalDataLog,
)


PROJECT_DIR = Path(__file__).resolve().parent.parent

BACKUP_DIR = PROJECT_DIR / "data" / "backups"


NEW_TABLES = {
    "households",
    "survey_people",
    "survey_batches",
    "survey_batch_lock_logs",
    "survey_forms",
    "survey_form_investigators",
    "survey_person_year_records",
    "survey_file_exchange_logs",
    "historical_datasets",
    "historical_households",
    "historical_people",
    "historical_data_logs",
}


try:
    sys.stdout.reconfigure(
        encoding="utf-8"
    )
except (AttributeError, OSError):
    pass


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
        / f"phocap_before_survey_tables_{timestamp}.db"
    )

    shutil.copy2(
        DATABASE_PATH,
        backup_path,
    )

    return backup_path


def tao_cac_bang() -> None:
    """
    Tạo các bảng chưa tồn tại.

    create_all không xóa hoặc thay đổi
    các bảng và dữ liệu hiện có.
    """

    Base.metadata.create_all(
        bind=engine
    )


def lay_danh_sach_bang() -> set[str]:
    """
    Lấy danh sách bảng hiện có trong SQLite.
    """

    inspector = inspect(engine)

    return set(
        inspector.get_table_names()
    )


def lay_so_luong_du_lieu_cu() -> dict[str, int]:
    """
    Kiểm tra dữ liệu xã, trường, tài khoản
    và học sinh vẫn được giữ nguyên.
    """

    with SessionLocal() as db:
        commune_count = db.scalar(
            select(
                func.count(Commune.id)
            )
        )

        school_count = db.scalar(
            select(
                func.count(School.id)
            )
        )

        user_count = db.scalar(
            select(
                func.count(User.id)
            )
        )

        student_count = db.scalar(
            select(
                func.count(Student.id)
            )
        )

    return {
        "communes": int(
            commune_count or 0
        ),
        "schools": int(
            school_count or 0
        ),
        "users": int(
            user_count or 0
        ),
        "students": int(
            student_count or 0
        ),
    }


def lay_so_luong_du_lieu_dieu_tra() -> dict[str, int]:
    """
    Đếm dữ liệu trong các bảng điều tra mới.
    Lần đầu khởi tạo, các giá trị thường bằng 0.
    """

    with SessionLocal() as db:
        household_count = db.scalar(
            select(
                func.count(Household.id)
            )
        )

        person_count = db.scalar(
            select(
                func.count(SurveyPerson.id)
            )
        )

        batch_count = db.scalar(
            select(
                func.count(SurveyBatch.id)
            )
        )

        form_count = db.scalar(
            select(
                func.count(SurveyForm.id)
            )
        )

        investigator_count = db.scalar(
            select(
                func.count(
                    SurveyFormInvestigator.id
                )
            )
        )

        year_record_count = db.scalar(
            select(
                func.count(
                    SurveyPersonYearRecord.id
                )
            )
        )

        lock_log_count = db.scalar(
            select(
                func.count(
                    SurveyBatchLockLog.id
                )
            )
        )

        file_exchange_log_count = db.scalar(
            select(
                func.count(
                    SurveyFileExchangeLog.id
                )
            )
        )

    return {
        "households": int(
            household_count or 0
        ),
        "survey_people": int(
            person_count or 0
        ),
        "survey_batches": int(
            batch_count or 0
        ),
        "survey_forms": int(
            form_count or 0
        ),
        "survey_form_investigators": int(
            investigator_count or 0
        ),
        "survey_person_year_records": int(
            year_record_count or 0
        ),
        "survey_batch_lock_logs": int(
            lock_log_count or 0
        ),
        "survey_file_exchange_logs": int(
            file_exchange_log_count or 0
        ),
    }


def main() -> None:
    print("=" * 72)
    print(
        "KHỞI TẠO CƠ SỞ DỮ LIỆU "
        "ĐIỀU TRA HỘ GIA ĐÌNH"
    )
    print("=" * 72)

    backup_path = sao_luu_co_so_du_lieu()

    if backup_path is not None:
        print()
        print(
            "Đã sao lưu cơ sở dữ liệu:"
        )
        print(backup_path)
    else:
        print()
        print(
            "Chưa có cơ sở dữ liệu cũ để sao lưu."
        )

    print()
    print(
        "Đang tạo các bảng điều tra..."
    )

    tao_cac_bang()

    existing_tables = lay_danh_sach_bang()

    missing_tables = (
        NEW_TABLES - existing_tables
    )

    print()
    print("Kết quả kiểm tra bảng:")

    for table_name in sorted(
        NEW_TABLES
    ):
        if table_name in existing_tables:
            print(
                f"- {table_name}: Đã có"
            )
        else:
            print(
                f"- {table_name}: Chưa có"
            )

    if missing_tables:
        print()
        print("=" * 72)
        print("KHỞI TẠO CHƯA HOÀN THÀNH")
        print("=" * 72)
        print(
            "Các bảng còn thiếu:"
        )

        for table_name in sorted(
            missing_tables
        ):
            print(f"- {table_name}")

        raise SystemExit(1)

    old_counts = (
        lay_so_luong_du_lieu_cu()
    )

    survey_counts = (
        lay_so_luong_du_lieu_dieu_tra()
    )

    print()
    print(
        "Dữ liệu hiện có được giữ nguyên:"
    )
    print(
        f"- Xã: {old_counts['communes']}"
    )
    print(
        f"- Trường: {old_counts['schools']}"
    )
    print(
        f"- Tài khoản: {old_counts['users']}"
    )
    print(
        f"- Học sinh: {old_counts['students']}"
    )

    print()
    print(
        "Dữ liệu điều tra hiện tại:"
    )
    print(
        "- Hộ gia đình: "
        f"{survey_counts['households']}"
    )
    print(
        "- Đối tượng điều tra: "
        f"{survey_counts['survey_people']}"
    )
    print(
        "- Đợt điều tra: "
        f"{survey_counts['survey_batches']}"
    )
    print(
        "- Phiếu điều tra: "
        f"{survey_counts['survey_forms']}"
    )
    print(
        "- Người điều tra được phân công: "
        f"{survey_counts['survey_form_investigators']}"
    )
    print(
        "- Hồ sơ theo năm học: "
        f"{survey_counts['survey_person_year_records']}"
    )
    print(
        "- Nhật ký chốt/mở khóa: "
        f"{survey_counts['survey_batch_lock_logs']}"
    )

    print()
    print("=" * 72)
    print("KHỞI TẠO THÀNH CÔNG")
    print("=" * 72)
    print(
        "Phần mềm đã sẵn sàng xây dựng "
        "chức năng quản lý hộ và điều tra."
    )


if __name__ == "__main__":
    main()