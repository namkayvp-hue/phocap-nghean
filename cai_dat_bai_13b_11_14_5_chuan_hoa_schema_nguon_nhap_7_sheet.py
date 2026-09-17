from __future__ import annotations

import os
import shutil
import sqlite3
import traceback
from datetime import datetime
from pathlib import Path


PROJECT = Path(
    os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")
).resolve()

DB = PROJECT / "data" / "phocap.db"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

BACKUP = (
    PROJECT
    / "exports"
    / f"backup_bai_13b_11_14_5_{STAMP}"
)

DB_BACKUP = BACKUP / "data" / "phocap.db"


NEW_TABLES = {
    "pcgdmn_input_catalog": {
        "id", "domain_code", "item_code", "item_group",
        "item_name", "unit_name", "source_form", "source_sheet",
        "sort_order", "is_active", "notes", "created_at", "updated_at",
    },
    "school_site_year_records": {
        "id", "school_id", "school_year_id", "site_code",
        "site_name", "site_type", "is_independent", "address",
        "is_active", "notes", "created_at", "updated_at",
    },
    "school_class_year_attributes": {
        "id", "class_id", "site_year_id", "class_structure",
        "age_group_code", "is_mixed_age", "planned_children_count",
        "notes", "created_at", "updated_at",
    },
    "school_facility_year_items": {
        "id", "school_id", "school_year_id", "site_year_id",
        "item_code", "item_group", "item_name", "quantity",
        "qualified_quantity", "unit_name", "evidence_note", "notes",
        "created_at", "updated_at",
    },
    "staff_policy_year_records": {
        "id", "staff_year_record_id", "policy_code", "policy_name",
        "is_eligible", "is_receiving", "effective_from", "effective_to",
        "notes", "created_at", "updated_at",
    },
    "finance_year_entries": {
        "id", "school_year_id", "unit_scope", "commune_id", "school_id",
        "item_code", "item_group", "item_name", "funding_source", "amount",
        "document_no", "document_date", "entry_date", "notes",
        "created_by_user_id", "updated_by_user_id",
        "created_at", "updated_at",
    },
}

CREATE_SQL = "\nCREATE TABLE IF NOT EXISTS pcgdmn_input_catalog (\n    id INTEGER PRIMARY KEY AUTOINCREMENT,\n    domain_code VARCHAR(30) NOT NULL,\n    item_code VARCHAR(80) NOT NULL,\n    item_group VARCHAR(120),\n    item_name VARCHAR(255) NOT NULL,\n    unit_name VARCHAR(50),\n    source_form VARCHAR(80),\n    source_sheet VARCHAR(120),\n    sort_order INTEGER NOT NULL DEFAULT 0,\n    is_active INTEGER NOT NULL DEFAULT 1,\n    notes TEXT,\n    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,\n    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,\n    UNIQUE(domain_code, item_code)\n);\n\nCREATE INDEX IF NOT EXISTS ix_pcgdmn_input_catalog_domain\nON pcgdmn_input_catalog (\n    domain_code,\n    is_active,\n    sort_order\n);\n\nCREATE TABLE IF NOT EXISTS school_site_year_records (\n    id INTEGER PRIMARY KEY AUTOINCREMENT,\n    school_id INTEGER NOT NULL,\n    school_year_id INTEGER NOT NULL,\n    site_code VARCHAR(80),\n    site_name VARCHAR(255) NOT NULL,\n    site_type VARCHAR(30) NOT NULL DEFAULT 'MAIN',\n    is_independent INTEGER NOT NULL DEFAULT 0,\n    address VARCHAR(500),\n    is_active INTEGER NOT NULL DEFAULT 1,\n    notes TEXT,\n    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,\n    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,\n\n    FOREIGN KEY(school_id)\n        REFERENCES schools(id)\n        ON DELETE CASCADE,\n\n    FOREIGN KEY(school_year_id)\n        REFERENCES school_years(id)\n        ON DELETE CASCADE\n);\n\nCREATE UNIQUE INDEX IF NOT EXISTS ux_school_site_year_code\nON school_site_year_records (\n    school_id,\n    school_year_id,\n    site_code\n)\nWHERE site_code IS NOT NULL\n  AND TRIM(site_code) <> '';\n\nCREATE INDEX IF NOT EXISTS ix_school_site_year_school\nON school_site_year_records (\n    school_id,\n    school_year_id,\n    is_active\n);\n\nCREATE TABLE IF NOT EXISTS school_class_year_attributes (\n    id INTEGER PRIMARY KEY AUTOINCREMENT,\n    class_id INTEGER NOT NULL UNIQUE,\n    site_year_id INTEGER,\n    class_structure VARCHAR(30) NOT NULL DEFAULT 'SINGLE',\n    age_group_code VARCHAR(50),\n    is_mixed_age INTEGER NOT NULL DEFAULT 0,\n    planned_children_count INTEGER,\n    notes TEXT,\n    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,\n    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,\n\n    FOREIGN KEY(class_id)\n        REFERENCES classes(id)\n        ON DELETE CASCADE,\n\n    FOREIGN KEY(site_year_id)\n        REFERENCES school_site_year_records(id)\n        ON DELETE SET NULL\n);\n\nCREATE INDEX IF NOT EXISTS ix_school_class_year_site\nON school_class_year_attributes (\n    site_year_id,\n    class_structure\n);\n\nCREATE TABLE IF NOT EXISTS school_facility_year_items (\n    id INTEGER PRIMARY KEY AUTOINCREMENT,\n    school_id INTEGER NOT NULL,\n    school_year_id INTEGER NOT NULL,\n    site_year_id INTEGER,\n    item_code VARCHAR(80) NOT NULL,\n    item_group VARCHAR(120),\n    item_name VARCHAR(255) NOT NULL,\n    quantity NUMERIC,\n    qualified_quantity NUMERIC,\n    unit_name VARCHAR(50),\n    evidence_note TEXT,\n    notes TEXT,\n    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,\n    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,\n\n    FOREIGN KEY(school_id)\n        REFERENCES schools(id)\n        ON DELETE CASCADE,\n\n    FOREIGN KEY(school_year_id)\n        REFERENCES school_years(id)\n        ON DELETE CASCADE,\n\n    FOREIGN KEY(site_year_id)\n        REFERENCES school_site_year_records(id)\n        ON DELETE SET NULL\n);\n\nCREATE UNIQUE INDEX IF NOT EXISTS ux_school_facility_year_item\nON school_facility_year_items (\n    school_id,\n    school_year_id,\n    IFNULL(site_year_id, -1),\n    item_code\n);\n\nCREATE INDEX IF NOT EXISTS ix_school_facility_year_school\nON school_facility_year_items (\n    school_id,\n    school_year_id,\n    item_group\n);\n\nCREATE TABLE IF NOT EXISTS staff_policy_year_records (\n    id INTEGER PRIMARY KEY AUTOINCREMENT,\n    staff_year_record_id INTEGER NOT NULL,\n    policy_code VARCHAR(80) NOT NULL,\n    policy_name VARCHAR(255) NOT NULL,\n    is_eligible INTEGER,\n    is_receiving INTEGER,\n    effective_from DATE,\n    effective_to DATE,\n    notes TEXT,\n    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,\n    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,\n\n    FOREIGN KEY(staff_year_record_id)\n        REFERENCES staff_year_records(id)\n        ON DELETE CASCADE,\n\n    UNIQUE(\n        staff_year_record_id,\n        policy_code\n    )\n);\n\nCREATE INDEX IF NOT EXISTS ix_staff_policy_year_record\nON staff_policy_year_records (\n    staff_year_record_id,\n    policy_code\n);\n\nCREATE TABLE IF NOT EXISTS finance_year_entries (\n    id INTEGER PRIMARY KEY AUTOINCREMENT,\n    school_year_id INTEGER NOT NULL,\n    unit_scope VARCHAR(20) NOT NULL,\n    commune_id INTEGER,\n    school_id INTEGER,\n    item_code VARCHAR(80) NOT NULL,\n    item_group VARCHAR(120),\n    item_name VARCHAR(255) NOT NULL,\n    funding_source VARCHAR(255),\n    amount NUMERIC,\n    document_no VARCHAR(120),\n    document_date DATE,\n    entry_date DATE,\n    notes TEXT,\n    created_by_user_id INTEGER,\n    updated_by_user_id INTEGER,\n    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,\n    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,\n\n    FOREIGN KEY(school_year_id)\n        REFERENCES school_years(id)\n        ON DELETE CASCADE,\n\n    FOREIGN KEY(commune_id)\n        REFERENCES communes(id)\n        ON DELETE CASCADE,\n\n    FOREIGN KEY(school_id)\n        REFERENCES schools(id)\n        ON DELETE CASCADE,\n\n    CHECK(\n        unit_scope IN (\n            'SCHOOL',\n            'COMMUNE'\n        )\n    ),\n\n    CHECK(\n        (\n            unit_scope = 'SCHOOL'\n            AND school_id IS NOT NULL\n        )\n        OR\n        (\n            unit_scope = 'COMMUNE'\n            AND commune_id IS NOT NULL\n        )\n    )\n);\n\nCREATE INDEX IF NOT EXISTS ix_finance_year_unit\nON finance_year_entries (\n    school_year_id,\n    unit_scope,\n    commune_id,\n    school_id\n);\n\nCREATE INDEX IF NOT EXISTS ix_finance_year_item\nON finance_year_entries (\n    school_year_id,\n    item_code,\n    funding_source\n);\n"

PRESERVE_TABLES = (
    "schools",
    "classes",
    "staff_members",
    "staff_year_records",
    "school_mn01_csvc_inputs",
    "finance_report_values",
    "survey_people",
    "survey_person_year_records",
    "survey_person_events",
    "survey_person_year_disability_types",
    "school_staff_year_summaries",
    "school_structured_report_inputs",
    "school_network_year_data",
)


def sqlite_backup(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(str(source))
    dst = sqlite3.connect(str(target))
    try:
        src.backup(dst)
        dst.commit()
    finally:
        dst.close()
        src.close()


def sqlite_restore(source: Path, target: Path) -> None:
    src = sqlite3.connect(str(source))
    dst = sqlite3.connect(str(target))
    try:
        src.backup(dst)
        dst.commit()
    finally:
        dst.close()
        src.close()


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type='table'
          AND name=?
        LIMIT 1
        """,
        (table,),
    ).fetchone() is not None


def table_columns(conn: sqlite3.Connection, table: str) -> tuple[str, ...]:
    if not table_exists(conn, table):
        return tuple()

    return tuple(
        str(row[1])
        for row in conn.execute(
            f'PRAGMA table_info("{table}")'
        ).fetchall()
    )


def table_count(conn: sqlite3.Connection, table: str) -> int | None:
    if not table_exists(conn, table):
        return None

    return int(
        conn.execute(
            f'SELECT COUNT(*) FROM "{table}"'
        ).fetchone()[0]
    )


def db_health(conn: sqlite3.Connection) -> tuple[str, int]:
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


def snapshot_existing(conn: sqlite3.Connection) -> dict:
    tables = [
        str(row[0])
        for row in conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type='table'
              AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """
        ).fetchall()
    ]

    snapshot = {}

    for table in tables:
        snapshot[table] = {
            "columns": table_columns(conn, table),
            "count": table_count(conn, table),
        }

    return snapshot


def apply_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(CREATE_SQL)


def verify_new_tables(conn: sqlite3.Connection) -> None:
    for table, required_columns in NEW_TABLES.items():
        if not table_exists(conn, table):
            raise RuntimeError(
                f"Chưa tạo được bảng: {table}"
            )

        actual = set(
            table_columns(conn, table)
        )

        missing = required_columns - actual

        if missing:
            raise RuntimeError(
                f"Bảng {table} thiếu cột: "
                + ", ".join(sorted(missing))
            )

        count = table_count(conn, table)

        if count != 0:
            raise RuntimeError(
                f"Bảng mới {table} phải rỗng sau cài; "
                f"hiện có {count} bản ghi."
            )


def verify_preserved_schema(before: dict, after: dict) -> None:
    for table, old_meta in before.items():
        if table in NEW_TABLES:
            continue

        if table not in after:
            raise RuntimeError(
                f"Bảng cũ bị mất: {table}"
            )

        if after[table]["columns"] != old_meta["columns"]:
            raise RuntimeError(
                f"Cấu trúc bảng cũ bị thay đổi: {table}"
            )


def verify_preserved_counts(before: dict, after: dict) -> None:
    for table in PRESERVE_TABLES:
        if table not in before:
            continue

        before_count = before[table]["count"]
        after_count = after.get(table, {}).get("count")

        if before_count != after_count:
            raise RuntimeError(
                f"Số bản ghi bảng {table} thay đổi: "
                f"{before_count} -> {after_count}"
            )


def main() -> int:
    print("=" * 126)
    print(
        "BÀI 13B-11.14.5 - "
        "CHUẨN HÓA SCHEMA NGUỒN NHẬP "
        "TRƯỜNG/LỚP + GV + CSVC + BCTC"
    )
    print("=" * 126)
    print()
    print("GIỮ NGUYÊN NỀN ĐÃ CÓ:")
    print(" - GV: staff_members + staff_year_records.")
    print(" - CSVC cũ: school_mn01_csvc_inputs.")
    print(" - Tài chính cũ: finance_report_values.")
    print(" - ĐTKT/Sổ PC: không tạo lại.")
    print()
    print("BỔ SUNG 6 BẢNG:")
    print(" 1. pcgdmn_input_catalog")
    print(" 2. school_site_year_records")
    print(" 3. school_class_year_attributes")
    print(" 4. school_facility_year_items")
    print(" 5. staff_policy_year_records")
    print(" 6. finance_year_entries")
    print()
    print("AN TOÀN:")
    print(" - Không xóa/sửa cột bảng cũ.")
    print(" - Không chuyển dữ liệu cũ trong bài này.")
    print(" - Không tạo dữ liệu nghiệp vụ mẫu.")
    print(" - Bảng mới phải rỗng sau cài.")
    print(" - Backup database bằng SQLite Backup API.")
    print(" - Có lỗi tự rollback.")
    print()

    if not DB.exists():
        raise RuntimeError(
            f"Không tìm thấy database: {DB}"
        )

    conn = sqlite3.connect(str(DB))
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        integrity_before, fk_before = db_health(conn)

        if integrity_before.lower() != "ok" or fk_before != 0:
            raise RuntimeError(
                "Database không đạt kiểm tra trước cài."
            )

        before = snapshot_existing(conn)
    finally:
        conn.close()

    print("integrity_check trước cài:", integrity_before)
    print("foreign_key_check trước cài:", fk_before, "lỗi")
    print("Tổng số bảng trước cài:", len(before))

    for table in PRESERVE_TABLES:
        if table in before:
            print(
                f" - {table}: "
                f"{before[table]['count']} bản ghi"
            )

    BACKUP.mkdir(parents=True, exist_ok=False)
    sqlite_backup(DB, DB_BACKUP)

    print("Backup:", BACKUP)

    try:
        conn = sqlite3.connect(str(DB))
        try:
            conn.execute("PRAGMA foreign_keys = ON")

            apply_schema(conn)
            conn.commit()

            verify_new_tables(conn)

            integrity_after, fk_after = db_health(conn)
            after = snapshot_existing(conn)

            verify_preserved_schema(before, after)
            verify_preserved_counts(before, after)

            if integrity_after.lower() != "ok":
                raise RuntimeError(
                    f"integrity_check sau cài: {integrity_after}"
                )

            if fk_after != 0:
                raise RuntimeError(
                    f"foreign_key_check sau cài có {fk_after} lỗi."
                )
        finally:
            conn.close()

        print()
        print("KIỂM TRA SAU CÀI:")
        print(" - Bảng cũ: KHÔNG XÓA / KHÔNG ĐỔI CỘT")
        print(" - Dữ liệu bảng lõi: GIỮ NGUYÊN")

        for table in NEW_TABLES:
            print(
                f" - {table}: ĐÃ TẠO, 0 bản ghi"
            )

        print(" - integrity_check: OK")
        print(" - foreign_key_check: 0 lỗi")
        print(" - Database backup: OK")
        print()
        print("=" * 126)
        print(
            "CÀI ĐẶT BÀI 13B-11.14.5 THÀNH CÔNG"
        )
        print("=" * 126)
        print()
        print("BƯỚC TIẾP THEO:")
        print(
            " - 14.6: Giao diện nhập "
            "Trường/Cơ sở/Điểm trường/Lớp đơn-Lớp ghép."
        )
        print(
            " - 14.7: Hoàn thiện nguồn nhập GV."
        )
        print(
            " - 14.8: Hoàn thiện nguồn nhập CSVC/TBDH."
        )
        print(
            " - 14.9: Hoàn thiện nguồn nhập BCTC."
        )

        return 0

    except Exception:
        traceback.print_exc()

        print()
        print(
            "CÓ LỖI - ĐANG KHÔI PHỤC DATABASE..."
        )

        try:
            sqlite_restore(DB_BACKUP, DB)
            print(
                " - Đã khôi phục database từ backup."
            )
        except Exception as exc:
            print(
                " - LỖI KHÔI PHỤC DATABASE:",
                exc,
            )

        print("Backup:", BACKUP)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
