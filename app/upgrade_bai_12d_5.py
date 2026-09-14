from __future__ import annotations

import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from app.database import DATABASE_PATH


PROJECT_DIR = Path(__file__).resolve().parent.parent
BACKUP_DIR = PROJECT_DIR / "data" / "backups"


try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, OSError):
    pass


BATCH_COLUMNS: dict[str, str] = {
    "is_locked": (
        "ALTER TABLE survey_batches "
        "ADD COLUMN is_locked BOOLEAN NOT NULL DEFAULT 0"
    ),
    "locked_at": (
        "ALTER TABLE survey_batches "
        "ADD COLUMN locked_at DATETIME"
    ),
    "locked_by_user_id": (
        "ALTER TABLE survey_batches "
        "ADD COLUMN locked_by_user_id INTEGER "
        "REFERENCES users(id)"
    ),
    "lock_reason": (
        "ALTER TABLE survey_batches "
        "ADD COLUMN lock_reason TEXT"
    ),
    "status_before_lock": (
        "ALTER TABLE survey_batches "
        "ADD COLUMN status_before_lock VARCHAR(50)"
    ),
}


CREATE_LOG_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS survey_batch_lock_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    survey_batch_id INTEGER NOT NULL,
    action VARCHAR(20) NOT NULL,
    actor_user_id INTEGER,
    actor_name_snapshot VARCHAR(200),
    actor_role_snapshot VARCHAR(50),
    reason TEXT NOT NULL,
    form_total INTEGER NOT NULL DEFAULT 0,
    completed_form_total INTEGER NOT NULL DEFAULT 0,
    blocking_issue_total INTEGER NOT NULL DEFAULT 0,
    previous_status VARCHAR(50),
    new_status VARCHAR(50),
    created_at DATETIME NOT NULL,
    FOREIGN KEY (survey_batch_id)
        REFERENCES survey_batches(id)
        ON DELETE CASCADE,
    FOREIGN KEY (actor_user_id)
        REFERENCES users(id)
)
"""


CREATE_INDEX_STATEMENTS = (
    """
    CREATE INDEX IF NOT EXISTS ix_survey_batches_is_locked
    ON survey_batches (is_locked)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_survey_batches_locked_by_user_id
    ON survey_batches (locked_by_user_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_survey_batch_lock_logs_batch
    ON survey_batch_lock_logs (survey_batch_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_survey_batch_lock_logs_action
    ON survey_batch_lock_logs (action)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_survey_batch_lock_logs_actor
    ON survey_batch_lock_logs (actor_user_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_survey_batch_lock_logs_created_at
    ON survey_batch_lock_logs (created_at)
    """,
)


def sao_luu_co_so_du_lieu() -> Path:
    if not DATABASE_PATH.exists():
        raise FileNotFoundError(
            f"Không tìm thấy cơ sở dữ liệu: {DATABASE_PATH}"
        )

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = (
        BACKUP_DIR
        / f"phocap_before_bai_12d_5_{timestamp}.db"
    )
    shutil.copy2(DATABASE_PATH, backup_path)
    return backup_path


def lay_cac_cot(
    connection: sqlite3.Connection,
    table_name: str,
) -> set[str]:
    rows = connection.execute(
        f"PRAGMA table_info({table_name})"
    ).fetchall()
    return {str(row[1]) for row in rows}


def kiem_tra_bang_ton_tai(
    connection: sqlite3.Connection,
    table_name: str,
) -> bool:
    row = connection.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table'
          AND name = ?
        LIMIT 1
        """,
        (table_name,),
    ).fetchone()
    return row is not None


def nang_cap_co_so_du_lieu() -> list[str]:
    messages: list[str] = []

    with sqlite3.connect(DATABASE_PATH) as connection:
        connection.execute("PRAGMA foreign_keys = ON")

        if not kiem_tra_bang_ton_tai(
            connection,
            "survey_batches",
        ):
            raise RuntimeError(
                "Chưa có bảng survey_batches. "
                "Hãy kiểm tra lại cơ sở dữ liệu hiện tại."
            )

        existing_columns = lay_cac_cot(
            connection,
            "survey_batches",
        )

        for column_name, sql in BATCH_COLUMNS.items():
            if column_name in existing_columns:
                messages.append(
                    f"Đã có cột survey_batches.{column_name}."
                )
                continue

            connection.execute(sql)
            messages.append(
                f"Đã thêm cột survey_batches.{column_name}."
            )

        connection.execute(CREATE_LOG_TABLE_SQL)
        messages.append(
            "Đã bảo đảm bảng survey_batch_lock_logs."
        )

        for statement in CREATE_INDEX_STATEMENTS:
            connection.execute(statement)

        connection.execute(
            """
            UPDATE survey_batches
            SET is_locked = 0
            WHERE is_locked IS NULL
            """
        )

        connection.commit()

    return messages


def kiem_tra_ket_qua() -> dict[str, object]:
    with sqlite3.connect(DATABASE_PATH) as connection:
        batch_columns = lay_cac_cot(
            connection,
            "survey_batches",
        )
        log_table_exists = kiem_tra_bang_ton_tai(
            connection,
            "survey_batch_lock_logs",
        )
        batch_count = connection.execute(
            "SELECT COUNT(*) FROM survey_batches"
        ).fetchone()[0]
        log_count = connection.execute(
            "SELECT COUNT(*) FROM survey_batch_lock_logs"
        ).fetchone()[0]

    return {
        "batch_columns": batch_columns,
        "log_table_exists": log_table_exists,
        "batch_count": int(batch_count or 0),
        "log_count": int(log_count or 0),
    }


def main() -> None:
    print("=" * 72)
    print("BÀI 12D-5 - NÂNG CẤP CHỐT SỐ LIỆU VÀ KHÓA ĐỢT ĐIỀU TRA")
    print("=" * 72)

    backup_path = sao_luu_co_so_du_lieu()
    print()
    print("Đã sao lưu cơ sở dữ liệu:")
    print(backup_path)

    print()
    print("Đang nâng cấp cơ sở dữ liệu...")
    messages = nang_cap_co_so_du_lieu()
    for message in messages:
        print(f"- {message}")

    result = kiem_tra_ket_qua()
    required_columns = set(BATCH_COLUMNS)
    missing_columns = required_columns.difference(
        result["batch_columns"]
    )

    print()
    print("KẾT QUẢ KIỂM TRA")
    print("-" * 72)
    print(f"Số đợt điều tra hiện có: {result['batch_count']}")
    print(f"Số nhật ký khóa/mở khóa: {result['log_count']}")
    print(
        "Bảng nhật ký: "
        + (
            "ĐÃ CÓ"
            if result["log_table_exists"]
            else "CHƯA CÓ"
        )
    )

    if missing_columns:
        print(
            "Thiếu các cột: "
            + ", ".join(sorted(missing_columns))
        )
        raise SystemExit(1)

    if not result["log_table_exists"]:
        raise SystemExit(1)

    print()
    print("NÂNG CẤP BÀI 12D-5 THÀNH CÔNG.")
    print("Có thể khởi động lại phần mềm.")


if __name__ == "__main__":
    main()
