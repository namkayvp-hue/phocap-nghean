from __future__ import annotations

import shutil
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import inspect, text

from app.database import DATABASE_PATH, engine


PROJECT_DIR = Path(__file__).resolve().parent.parent
BACKUP_DIR = PROJECT_DIR / "data" / "backups"
TABLE_NAME = "survey_person_year_records"

COLUMN_DEFINITIONS = {
    "is_reviewed": "INTEGER NOT NULL DEFAULT 0",
    "disability_status": "VARCHAR(30) NOT NULL DEFAULT 'CHUA_XAC_DINH'",
    "disability_type": "VARCHAR(50)",
    "disability_level": "VARCHAR(30)",
    "disability_certificate": "INTEGER",
    "inclusive_education": "INTEGER",
    "disability_support": "INTEGER",
    "disability_support_details": "TEXT",
}


try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, OSError):
    pass


def backup_database() -> Path | None:
    if not DATABASE_PATH.exists():
        return None

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"before_bai_12d_14c2_{timestamp}.db"
    shutil.copy2(DATABASE_PATH, backup_path)
    return backup_path


def main() -> None:
    print("=" * 78)
    print("NÂNG CẤP BÀI 12D-14C2")
    print("THEO DÕI TRẺ KHUYẾT TẬT THEO TỪNG NĂM HỌC")
    print("=" * 78)

    backup_path = backup_database()
    print()
    if backup_path is None:
        print("Chưa có cơ sở dữ liệu cũ để sao lưu.")
    else:
        print("Đã sao lưu cơ sở dữ liệu:")
        print(backup_path)

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if TABLE_NAME not in tables:
        print()
        print(f"Không tìm thấy bảng {TABLE_NAME}.")
        print("Hãy chạy phần mềm ít nhất một lần để tạo các bảng cơ sở.")
        raise SystemExit(1)

    existing_columns = {
        item["name"]
        for item in inspector.get_columns(TABLE_NAME)
    }

    created_columns: list[str] = []
    with engine.begin() as connection:
        for column_name, definition in COLUMN_DEFINITIONS.items():
            if column_name in existing_columns:
                continue
            connection.execute(
                text(
                    f'ALTER TABLE "{TABLE_NAME}" '
                    f'ADD COLUMN "{column_name}" {definition}'
                )
            )
            created_columns.append(column_name)

        # Những hồ sơ đã có dữ liệu thực tế trước khi nâng cấp được xem là
        # đã rà soát. Hồ sơ rỗng do kế thừa tự động vẫn giữ is_reviewed = 0
        # để tiếp tục hiện thông tin tham chiếu từ năm trước.
        connection.execute(
            text(
                f'''
                UPDATE "{TABLE_NAME}"
                SET is_reviewed = 1
                WHERE is_reviewed = 0
                  AND (
                    COALESCE(learning_status, 'CHUA_XAC_DINH') <> 'CHUA_XAC_DINH'
                    OR school_id IS NOT NULL
                    OR class_id IS NOT NULL
                    OR COALESCE(school_name_reported, '') <> ''
                    OR COALESCE(class_name_reported, '') <> ''
                    OR completed_preschool_5 IS NOT NULL
                    OR attends_required_days IS NOT NULL
                    OR attends_regularly IS NOT NULL
                    OR prepared_vietnamese IS NOT NULL
                    OR weight_monitored IS NOT NULL
                    OR underweight IS NOT NULL
                    OR height_monitored IS NOT NULL
                    OR stunted IS NOT NULL
                    OR COALESCE(special_circumstances, '') <> ''
                    OR COALESCE(notes, '') <> ''
                  )
                '''
            )
        )

    inspector = inspect(engine)
    final_columns = {
        item["name"]
        for item in inspector.get_columns(TABLE_NAME)
    }
    missing = sorted(set(COLUMN_DEFINITIONS) - final_columns)
    if missing:
        print()
        print("NÂNG CẤP KHÔNG THÀNH CÔNG.")
        print("Còn thiếu các cột:")
        for column_name in missing:
            print(f"- {column_name}")
        raise SystemExit(1)

    print()
    if created_columns:
        print("Các cột vừa bổ sung:")
        for column_name in created_columns:
            print(f"- {column_name}")
    else:
        print("Các cột đã tồn tại; không tạo trùng.")

    print()
    print("=" * 78)
    print("NÂNG CẤP BÀI 12D-14C2 THÀNH CÔNG.")
    print("Có thể khởi động lại phần mềm.")
    print("=" * 78)


if __name__ == "__main__":
    main()
