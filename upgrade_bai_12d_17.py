from __future__ import annotations

import shutil
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import inspect

from app.comparison_models import (
    StudentSurveyComparisonSignoff,  # noqa: F401
    StudentSurveyResolutionLog,  # noqa: F401
)
from app.database import Base, DATABASE_PATH, engine
from app.models import User  # noqa: F401
from app.survey_models import SurveyBatch  # noqa: F401


PROJECT_DIR = Path(__file__).resolve().parent
BACKUP_DIR = PROJECT_DIR / "data" / "backups"
TABLE_NAME = "student_survey_comparison_signoffs"


try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, OSError):
    pass


def backup_database() -> Path | None:
    if not DATABASE_PATH.exists():
        return None

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"before_bai_12d_17_{timestamp}.db"
    shutil.copy2(DATABASE_PATH, backup_path)
    return backup_path


def main() -> None:
    print("=" * 76)
    print("NANG CAP BAI 12D-17")
    print("CHOT KET QUA DOI CHIEU VA LAP BIEN BAN XAC NHAN")
    print("=" * 76)

    backup_path = backup_database()
    print()
    if backup_path is None:
        print("Chua co co so du lieu cu de sao luu.")
    else:
        print("Da sao luu co so du lieu:")
        print(backup_path)

    Base.metadata.create_all(bind=engine)
    tables = set(inspect(engine).get_table_names())
    if TABLE_NAME not in tables:
        raise RuntimeError(f"Chua tao duoc bang {TABLE_NAME}.")

    columns = {
        item["name"]
        for item in inspect(engine).get_columns(TABLE_NAME)
    }
    required_columns = {
        "id",
        "survey_batch_id",
        "action_code",
        "note",
        "actor_user_id",
        "actor_name_snapshot",
        "actor_role_snapshot",
        "total_rows",
        "matched_rows",
        "issue_rows",
        "resolved_rows",
        "pending_rows",
        "created_at",
    }
    missing = required_columns - columns
    if missing:
        raise RuntimeError(
            "Bang chot ket qua thieu cot: " + ", ".join(sorted(missing))
        )

    print()
    print(f"- {TABLE_NAME}: Da san sang")
    print("=" * 76)
    print("NANG CAP BAI 12D-17 THANH CONG")
    print("=" * 76)


if __name__ == "__main__":
    main()
