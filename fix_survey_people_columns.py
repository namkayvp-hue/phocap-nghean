from __future__ import annotations

import shutil
import sqlite3
from datetime import datetime
from pathlib import Path


PROJECT_DIR = Path(r"C:\PhoCap")
DATABASE_PATH = PROJECT_DIR / "data" / "phocap.db"
BACKUP_DIR = PROJECT_DIR / "data" / "backups"

REQUIRED_COLUMNS = {
    "birth_place": "TEXT",
    "father_name": "TEXT",
    "mother_name": "TEXT",
    "contact_phone": "TEXT",
}


def get_column_names(connection: sqlite3.Connection) -> set[str]:
    rows = connection.execute(
        "PRAGMA table_info(survey_people)"
    ).fetchall()

    return {str(row[1]) for row in rows}


def main() -> None:
    print("=" * 70)
    print("BO SUNG COT CON THIEU CHO BANG survey_people")
    print("=" * 70)

    if not DATABASE_PATH.exists():
        raise FileNotFoundError(
            f"Khong tim thay co so du lieu: {DATABASE_PATH}"
        )

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = (
        BACKUP_DIR
        / f"before_fix_survey_people_columns_{timestamp}.db"
    )

    print(f"Co so du lieu: {DATABASE_PATH}")
    print(f"Ban sao an toan: {backup_path}")

    shutil.copy2(DATABASE_PATH, backup_path)
    print("Da tao ban sao co so du lieu.")

    connection = sqlite3.connect(DATABASE_PATH)

    try:
        existing_columns = get_column_names(connection)

        print("\nCac cot hien co:")
        for column_name in sorted(existing_columns):
            print(f"  - {column_name}")

        added_columns: list[str] = []

        for column_name, column_type in REQUIRED_COLUMNS.items():
            if column_name in existing_columns:
                print(f"\nDa co cot: {column_name}")
                continue

            sql = (
                f'ALTER TABLE survey_people '
                f'ADD COLUMN "{column_name}" {column_type}'
            )

            connection.execute(sql)
            added_columns.append(column_name)

            print(f"\nDa bo sung cot: {column_name} ({column_type})")

        connection.commit()

        final_columns = get_column_names(connection)

        print("\n" + "=" * 70)
        print("KET QUA")
        print("=" * 70)

        if added_columns:
            print("Cac cot da bo sung:")
            for column_name in added_columns:
                print(f"  - {column_name}")
        else:
            print("Khong can bo sung. Tat ca cac cot da ton tai.")

        missing_after_update = [
            column_name
            for column_name in REQUIRED_COLUMNS
            if column_name not in final_columns
        ]

        if missing_after_update:
            raise RuntimeError(
                "Van con cot chua duoc tao: "
                + ", ".join(missing_after_update)
            )

        print("\nBang survey_people da du cac cot can thiet.")
        print("Du lieu cu duoc giu nguyen.")
        print(f"Ban sao an toan nam tai: {backup_path}")

    except Exception:
        connection.rollback()
        print("\nCo loi xay ra. Co so du lieu da rollback.")
        print(f"Ban sao an toan van nam tai: {backup_path}")
        raise

    finally:
        connection.close()


if __name__ == "__main__":
    main()