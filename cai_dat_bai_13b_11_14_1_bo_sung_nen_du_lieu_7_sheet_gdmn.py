from __future__ import annotations

import os
import shutil
import sqlite3
import traceback
from datetime import datetime
from pathlib import Path


PROJECT = Path(
    os.environ.get(
        "PHOCAP_PROJECT",
        r"C:\PhoCap",
    )
).resolve()

DB = PROJECT / "data" / "phocap.db"

STAMP = datetime.now().strftime(
    "%Y%m%d_%H%M%S"
)

BACKUP = (
    PROJECT
    / "exports"
    / f"backup_bai_13b_11_14_1_{STAMP}"
)

BACKUP_DB = (
    BACKUP
    / "data"
    / "phocap.db"
)


YEAR_RECORD_FIELDS = [
    (
        "disability_can_learn",
        "BOOLEAN",
        (
            "Khuyết tật có khả năng học tập: "
            "NULL=Chưa xác định, 1=Có, 0=Không"
        ),
    ),
    (
        "disability_access_education",
        "BOOLEAN",
        (
            "Khuyết tật được tiếp cận giáo dục: "
            "NULL=Chưa xác định, 1=Có, 0=Không"
        ),
    ),
    (
        "school_commune_name_reported",
        "VARCHAR(255)",
        "Xã/phường của trường ngoài hệ thống theo phiếu",
    ),
    (
        "school_province_name_reported",
        "VARCHAR(255)",
        "Tỉnh/TP của trường ngoài hệ thống theo phiếu",
    ),
]

PERSON_FIELDS = [
    (
        "residency_status",
        "VARCHAR(30)",
        (
            "Tình trạng cư trú chuẩn hóa, dự kiến: "
            "THUONG_TRU / TAM_TRU / CHUA_XAC_DINH"
        ),
    ),
    (
        "guardian_name_reported",
        "VARCHAR(255)",
        (
            "Tên cha/mẹ/người đỡ đầu theo phiếu "
            "khi không suy ra được từ thành viên hộ"
        ),
    ),
]


def connect_rw() -> sqlite3.Connection:
    conn = sqlite3.connect(
        str(DB),
        timeout=30,
    )
    conn.execute(
        "PRAGMA foreign_keys=ON"
    )
    return conn


def connect_ro() -> sqlite3.Connection:
    return sqlite3.connect(
        f"file:{DB.as_posix()}?mode=ro",
        uri=True,
        timeout=30,
    )


def table_exists(
    conn: sqlite3.Connection,
    table: str,
) -> bool:
    return (
        conn.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type='table'
              AND name=?
            LIMIT 1
            """,
            (table,),
        ).fetchone()
        is not None
    )


def table_columns(
    conn: sqlite3.Connection,
    table: str,
) -> set[str]:
    if not table_exists(
        conn,
        table,
    ):
        return set()

    return {
        str(row[1])
        for row in conn.execute(
            f'PRAGMA table_info("{table}")'
        ).fetchall()
    }


def integrity_check(
    conn: sqlite3.Connection,
) -> tuple[str, int]:
    integrity = str(
        conn.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]
    )

    fk_count = len(
        conn.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()
    )

    return integrity, fk_count


def count_rows(
    conn: sqlite3.Connection,
    table: str,
) -> int:
    if not table_exists(
        conn,
        table,
    ):
        return -1

    return int(
        conn.execute(
            f'SELECT COUNT(*) FROM "{table}"'
        ).fetchone()[0]
    )


def sqlite_backup(
    source_db: Path,
    target_db: Path,
) -> None:
    target_db.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    source = sqlite3.connect(
        str(source_db),
        timeout=30,
    )
    target = sqlite3.connect(
        str(target_db),
        timeout=30,
    )

    try:
        source.backup(
            target
        )
        target.commit()
    finally:
        target.close()
        source.close()


def add_column_if_missing(
    conn: sqlite3.Connection,
    table: str,
    name: str,
    sql_type: str,
) -> bool:
    cols = table_columns(
        conn,
        table,
    )

    if name in cols:
        return False

    conn.execute(
        f'ALTER TABLE "{table}" '
        f'ADD COLUMN "{name}" {sql_type}'
    )

    return True


def create_events_table(
    conn: sqlite3.Connection,
) -> bool:
    existed = table_exists(
        conn,
        "survey_person_events",
    )

    if not existed:
        conn.execute(
            """
            CREATE TABLE survey_person_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                survey_person_id INTEGER NOT NULL,
                school_year_id INTEGER,
                survey_form_id INTEGER,

                event_type VARCHAR(30) NOT NULL,
                event_date DATE,

                origin_location VARCHAR(255),
                destination_location VARCHAR(255),

                notes TEXT,

                is_active BOOLEAN NOT NULL DEFAULT 1,

                created_at DATETIME
                    NOT NULL
                    DEFAULT CURRENT_TIMESTAMP,

                updated_at DATETIME
                    NOT NULL
                    DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (
                    survey_person_id
                )
                REFERENCES survey_people(id)
                ON DELETE CASCADE,

                FOREIGN KEY (
                    school_year_id
                )
                REFERENCES school_years(id)
                ON DELETE SET NULL,

                FOREIGN KEY (
                    survey_form_id
                )
                REFERENCES survey_forms(id)
                ON DELETE SET NULL
            )
            """
        )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS
        ix_survey_person_events_person
        ON survey_person_events(
            survey_person_id
        )
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS
        ix_survey_person_events_year
        ON survey_person_events(
            school_year_id
        )
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS
        ix_survey_person_events_form
        ON survey_person_events(
            survey_form_id
        )
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS
        ix_survey_person_events_type_date
        ON survey_person_events(
            event_type,
            event_date
        )
        """
    )

    return not existed


def create_disability_types_table(
    conn: sqlite3.Connection,
) -> bool:
    existed = table_exists(
        conn,
        "survey_person_year_disability_types",
    )

    if not existed:
        conn.execute(
            """
            CREATE TABLE
            survey_person_year_disability_types (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                survey_person_year_record_id
                    INTEGER NOT NULL,

                disability_type_code
                    VARCHAR(50) NOT NULL,

                notes TEXT,

                created_at DATETIME
                    NOT NULL
                    DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (
                    survey_person_year_record_id
                )
                REFERENCES survey_person_year_records(id)
                ON DELETE CASCADE,

                UNIQUE (
                    survey_person_year_record_id,
                    disability_type_code
                )
            )
            """
        )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS
        ix_year_disability_types_record
        ON survey_person_year_disability_types(
            survey_person_year_record_id
        )
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS
        ix_year_disability_types_code
        ON survey_person_year_disability_types(
            disability_type_code
        )
        """
    )

    return not existed


def verify_required_tables(
    conn: sqlite3.Connection,
) -> None:
    required = [
        "survey_person_year_records",
        "survey_people",
        "school_years",
        "survey_forms",
    ]

    missing = [
        table
        for table in required
        if not table_exists(
            conn,
            table,
        )
    ]

    if missing:
        raise RuntimeError(
            "Thiếu bảng nền bắt buộc: "
            + ", ".join(
                missing
            )
        )


def main() -> int:
    print(
        "=" * 122
    )
    print(
        "BÀI 13B-11.14.1 - "
        "BỔ SUNG NỀN DỮ LIỆU ĐẦU VÀO "
        "CHO 7 SHEET BỘ BIỂU GDMN"
    )
    print(
        "=" * 122
    )
    print()
    print(
        "MỤC TIÊU:"
    )
    print(
        " - Bổ sung đúng các dữ liệu lõi còn thiếu "
        "để giao diện ở các bài sau có nơi lưu."
    )
    print(
        " - Chưa thay giao diện trong bài này."
    )
    print(
        " - Không xóa/đổi dữ liệu cũ."
    )
    print()
    print(
        "BỔ SUNG CHO HỒ SƠ NĂM HỌC:"
    )
    print(
        " - Khuyết tật có khả năng học tập."
    )
    print(
        " - Khuyết tật được tiếp cận giáo dục."
    )
    print(
        " - Xã/phường của trường ngoài hệ thống."
    )
    print(
        " - Tỉnh/TP của trường ngoài hệ thống."
    )
    print()
    print(
        "BỔ SUNG CHO ĐỐI TƯỢNG:"
    )
    print(
        " - Tình trạng cư trú Thường trú/Tạm trú."
    )
    print(
        " - Tên cha/mẹ/người đỡ đầu theo phiếu "
        "khi không suy ra được từ hộ."
    )
    print()
    print(
        "BỔ SUNG BẢNG CẤU TRÚC:"
    )
    print(
        " - survey_person_events: "
        "CHUYỂN ĐẾN / CHUYỂN ĐI / TỬ VONG."
    )
    print(
        " - survey_person_year_disability_types: "
        "nhiều dạng tật/1 trẻ/1 năm học."
    )
    print()
    print(
        "LƯU Ý:"
    )
    print(
        " - Lớp/GV/CSVC/Tài chính sẽ xử lý ở Bài 13B-11.14.4 "
        "sau khi chốt giao diện Điều tra hộ dân."
    )
    print()

    if not DB.exists():
        raise RuntimeError(
            f"Không tìm thấy database: {DB}"
        )

    with connect_ro() as ro:
        verify_required_tables(
            ro
        )

        (
            integrity_before,
            fk_before,
        ) = integrity_check(
            ro
        )

        year_count_before = count_rows(
            ro,
            "survey_person_year_records",
        )

        people_count_before = count_rows(
            ro,
            "survey_people",
        )

        events_count_before = count_rows(
            ro,
            "survey_person_events",
        )

        disability_types_count_before = count_rows(
            ro,
            "survey_person_year_disability_types",
        )

    print(
        "integrity_check trước cài:",
        integrity_before,
    )
    print(
        "foreign_key_check trước cài:",
        fk_before,
        "lỗi",
    )
    print(
        "survey_person_year_records:",
        year_count_before,
        "bản ghi",
    )
    print(
        "survey_people:",
        people_count_before,
        "bản ghi",
    )

    if (
        integrity_before.lower()
        != "ok"
        or fk_before != 0
    ):
        raise RuntimeError(
            "Database không đạt kiểm tra an toàn "
            "trước khi cài."
        )

    BACKUP.mkdir(
        parents=True,
        exist_ok=False,
    )

    sqlite_backup(
        DB,
        BACKUP_DB,
    )

    print(
        "Backup database:",
        BACKUP_DB,
    )

    conn = connect_rw()

    try:
        verify_required_tables(
            conn
        )

        conn.execute(
            "BEGIN IMMEDIATE"
        )

        changes: list[str] = []

        for (
            field_name,
            sql_type,
            description,
        ) in YEAR_RECORD_FIELDS:
            created = add_column_if_missing(
                conn,
                "survey_person_year_records",
                field_name,
                sql_type,
            )

            if created:
                changes.append(
                    "survey_person_year_records."
                    + field_name
                )

            print(
                f" - {field_name}: "
                + (
                    "ĐÃ BỔ SUNG"
                    if created
                    else "ĐÃ CÓ"
                )
            )
            print(
                f"   {description}"
            )

        for (
            field_name,
            sql_type,
            description,
        ) in PERSON_FIELDS:
            created = add_column_if_missing(
                conn,
                "survey_people",
                field_name,
                sql_type,
            )

            if created:
                changes.append(
                    "survey_people."
                    + field_name
                )

            print(
                f" - {field_name}: "
                + (
                    "ĐÃ BỔ SUNG"
                    if created
                    else "ĐÃ CÓ"
                )
            )
            print(
                f"   {description}"
            )

        events_created = create_events_table(
            conn
        )

        if events_created:
            changes.append(
                "survey_person_events"
            )

        print(
            " - survey_person_events:",
            (
                "ĐÃ TẠO"
                if events_created
                else "ĐÃ CÓ"
            ),
        )

        disability_types_created = (
            create_disability_types_table(
                conn
            )
        )

        if disability_types_created:
            changes.append(
                "survey_person_year_disability_types"
            )

        print(
            " - survey_person_year_disability_types:",
            (
                "ĐÃ TẠO"
                if disability_types_created
                else "ĐÃ CÓ"
            ),
        )

        conn.commit()

        (
            integrity_after,
            fk_after,
        ) = integrity_check(
            conn
        )

        year_count_after = count_rows(
            conn,
            "survey_person_year_records",
        )

        people_count_after = count_rows(
            conn,
            "survey_people",
        )

        events_count_after = count_rows(
            conn,
            "survey_person_events",
        )

        disability_types_count_after = count_rows(
            conn,
            "survey_person_year_disability_types",
        )

        year_cols = table_columns(
            conn,
            "survey_person_year_records",
        )

        people_cols = table_columns(
            conn,
            "survey_people",
        )

        required_year_cols = {
            item[0]
            for item in YEAR_RECORD_FIELDS
        }

        required_people_cols = {
            item[0]
            for item in PERSON_FIELDS
        }

        missing_year = sorted(
            required_year_cols
            - year_cols
        )

        missing_people = sorted(
            required_people_cols
            - people_cols
        )

        if missing_year:
            raise RuntimeError(
                "Thiếu cột hồ sơ năm học sau cài: "
                + ", ".join(
                    missing_year
                )
            )

        if missing_people:
            raise RuntimeError(
                "Thiếu cột đối tượng sau cài: "
                + ", ".join(
                    missing_people
                )
            )

        if not table_exists(
            conn,
            "survey_person_events",
        ):
            raise RuntimeError(
                "Chưa có bảng survey_person_events."
            )

        if not table_exists(
            conn,
            "survey_person_year_disability_types",
        ):
            raise RuntimeError(
                "Chưa có bảng "
                "survey_person_year_disability_types."
            )

        if (
            integrity_after.lower()
            != "ok"
            or fk_after != 0
        ):
            raise RuntimeError(
                "Database không đạt kiểm tra sau cài."
            )

        if (
            year_count_after
            != year_count_before
        ):
            raise RuntimeError(
                "Số bản ghi survey_person_year_records "
                "bị thay đổi."
            )

        if (
            people_count_after
            != people_count_before
        ):
            raise RuntimeError(
                "Số bản ghi survey_people bị thay đổi."
            )

        # Nếu bảng mới thì trước cài count = -1.
        # Sau cài phải là 0; nếu bảng đã có thì không làm mất dữ liệu.
        if (
            events_count_before >= 0
            and events_count_after
            != events_count_before
        ):
            raise RuntimeError(
                "Số bản ghi survey_person_events "
                "bị thay đổi ngoài dự kiến."
            )

        if (
            disability_types_count_before >= 0
            and disability_types_count_after
            != disability_types_count_before
        ):
            raise RuntimeError(
                "Số bản ghi bảng dạng tật "
                "bị thay đổi ngoài dự kiến."
            )

        print()
        print(
            "KIỂM TRA SAU CÀI:"
        )
        print(
            " - Cột dữ liệu hồ sơ năm học: OK"
        )
        print(
            " - Cột dữ liệu đối tượng: OK"
        )
        print(
            " - Bảng biến động: OK"
        )
        print(
            " - Bảng nhiều dạng tật: OK"
        )
        print(
            " - Dữ liệu cũ survey_person_year_records:",
            year_count_after,
            "bản ghi - GIỮ NGUYÊN",
        )
        print(
            " - Dữ liệu cũ survey_people:",
            people_count_after,
            "bản ghi - GIỮ NGUYÊN",
        )
        print(
            " - integrity_check:",
            integrity_after,
        )
        print(
            " - foreign_key_check:",
            fk_after,
            "lỗi",
        )
        print()
        print(
            "CÁC THAY ĐỔI THỰC TẾ:"
        )

        if changes:
            for item in changes:
                print(
                    " -",
                    item,
                )
        else:
            print(
                " - Không có: toàn bộ cấu trúc đã tồn tại."
            )

        print()
        print(
            "=" * 122
        )
        print(
            "CÀI ĐẶT BÀI 13B-11.14.1 THÀNH CÔNG"
        )
        print(
            "=" * 122
        )
        print()
        print(
            "BƯỚC TIẾP THEO:"
        )
        print(
            " - Bài 13B-11.14.2 sẽ nối các trường này "
            "vào model + giao diện Thông tin năm học."
        )
        print(
            " - Khối chỉ báo Mầm non sẽ chuyển sang "
            "'Chỉ báo phục vụ báo cáo PCGDMN'."
        )
        print(
            " - Các chỉ báo sức khỏe vẫn giữ dữ liệu "
            "nhưng không dùng chốt đủ dữ liệu 7 sheet."
        )

        return 0

    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass

        traceback.print_exc()

        print()
        print(
            "CÓ LỖI - ĐANG KHÔI PHỤC DATABASE..."
        )

        try:
            conn.close()
        except Exception:
            pass

        shutil.copy2(
            BACKUP_DB,
            DB,
        )

        with connect_ro() as restored:
            (
                restored_integrity,
                restored_fk,
            ) = integrity_check(
                restored
            )

        print(
            "ĐÃ KHÔI PHỤC DATABASE."
        )
        print(
            "integrity_check sau khôi phục:",
            restored_integrity,
        )
        print(
            "foreign_key_check sau khôi phục:",
            restored_fk,
            "lỗi",
        )
        print(
            "Backup:",
            BACKUP_DB,
        )

        return 1

    finally:
        try:
            conn.close()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
