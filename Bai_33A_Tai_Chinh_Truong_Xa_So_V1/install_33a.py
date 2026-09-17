from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
from datetime import datetime

PACKAGE = Path(__file__).resolve().parent
PROJECT = Path(os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap"))
DB = PROJECT / "data" / "phocap.db"
PAYLOAD = PACKAGE / "payload"
MANIFEST = json.loads((PACKAGE / "manifest.json").read_text(encoding="utf-8"))
STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = PROJECT / "backups" / f"finance_school_33a_{STAMP}"

DDL = r'''
CREATE TABLE IF NOT EXISTS school_finance_report_values (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    school_id INTEGER NOT NULL,
    report_year INTEGER NOT NULL,
    item_code VARCHAR(40) NOT NULL,
    amount NUMERIC(20,4),
    note TEXT,
    updated_by_user_id INTEGER,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_school_finance_year_item UNIQUE (school_id, report_year, item_code),
    FOREIGN KEY(school_id) REFERENCES schools(id),
    FOREIGN KEY(updated_by_user_id) REFERENCES users(id)
);
CREATE INDEX IF NOT EXISTS ix_school_finance_report_values_school_id
ON school_finance_report_values (school_id);
CREATE INDEX IF NOT EXISTS ix_school_finance_report_values_report_year
ON school_finance_report_values (report_year);
CREATE INDEX IF NOT EXISTS ix_school_finance_report_values_item_code
ON school_finance_report_values (item_code);
'''

EXPECTED_COLUMNS = {
    "id", "school_id", "report_year", "item_code", "amount",
    "note", "updated_by_user_id", "updated_at",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sqlite_backup(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(src) as s, sqlite3.connect(dst) as d:
        s.backup(d)


def restore_db(backup_db: Path, target_db: Path) -> None:
    with sqlite3.connect(backup_db) as s, sqlite3.connect(target_db) as d:
        s.backup(d)


def db_health(path: Path) -> tuple[str, int]:
    with sqlite3.connect(path) as con:
        integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
        fk_count = len(con.execute("PRAGMA foreign_key_check").fetchall())
    return integrity, fk_count


def table_columns(con: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in con.execute(f'PRAGMA table_info("{table}")').fetchall()}


def compile_python(path: Path) -> None:
    compile(path.read_text(encoding="utf-8"), str(path), "exec")


def parse_jinja(path: Path) -> None:
    from jinja2 import Environment
    Environment().parse(path.read_text(encoding="utf-8"))


def main() -> None:
    print("=" * 118)
    print("BÀI 33A - TÀI CHÍNH CẤP TRƯỜNG -> XÃ/SỞ TỔNG HỢP")
    print("KHÓA SHA SOURCE - BACKUP TRƯỚC - CHỈ BỔ SUNG PHÂN HỆ TÀI CHÍNH")
    print("=" * 118)
    print("PROJECT =", PROJECT)
    print("DB =", DB)

    if not PROJECT.is_dir():
        raise SystemExit("STOP: Không tìm thấy C:\\PhoCap (hoặc PHOCAP_PROJECT).")
    if not DB.is_file():
        raise SystemExit("STOP: Không tìm thấy database data\\phocap.db.")

    # 1. Khóa đúng nền source đã nhận từ người dùng.
    for rel, expected in MANIFEST["expected_before"].items():
        target = PROJECT / rel
        if not target.is_file():
            raise SystemExit(f"STOP: Thiếu file nền: {rel}")
        actual = sha256(target)
        print(f"SHA_BEFORE {rel} = {actual}")
        if actual != expected:
            raise SystemExit(
                "STOP AN TOÀN: SHA source hiện tại không đúng gói đã khảo sát.\n"
                f"FILE = {rel}\nEXPECTED = {expected}\nACTUAL   = {actual}"
            )

    for rel in MANIFEST.get("new_files", []):
        target = PROJECT / rel
        if target.exists():
            raise SystemExit(f"STOP AN TOÀN: File mới đã tồn tại, không ghi đè: {rel}")

    integrity_before, fk_before = db_health(DB)
    print("INTEGRITY_BEFORE =", integrity_before)
    print("FK_COUNT_BEFORE =", fk_before)
    if integrity_before != "ok" or fk_before != 0:
        raise SystemExit("STOP: Database không đạt kiểm tra an toàn trước cài đặt.")

    # 2. Backup source + DB.
    BACKUP.mkdir(parents=True, exist_ok=False)
    for rel in MANIFEST["expected_before"]:
        src = PROJECT / rel
        dst = BACKUP / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    backup_db = BACKUP / "phocap_before_33a.db"
    sqlite_backup(DB, backup_db)
    print("BACKUP_DIR =", BACKUP)
    print("BACKUP_DB =", backup_db)

    installed_files: list[Path] = []
    try:
        # 3. Tạo đúng một bảng mới, không sửa bảng cũ và không ghi dữ liệu nghiệp vụ.
        with sqlite3.connect(DB) as con:
            existed = con.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='school_finance_report_values'"
            ).fetchone() is not None
            if existed:
                cols = table_columns(con, "school_finance_report_values")
                if not EXPECTED_COLUMNS.issubset(cols):
                    raise RuntimeError(
                        "Bảng school_finance_report_values đã tồn tại nhưng schema không đúng."
                    )
            else:
                con.executescript(DDL)
                con.commit()
            row_count = con.execute(
                "SELECT COUNT(*) FROM school_finance_report_values"
            ).fetchone()[0]
            if not existed and row_count != 0:
                raise RuntimeError("Bảng mới không rỗng sau khi tạo.")
            print("TABLE_EXISTED_BEFORE =", "YES" if existed else "NO")
            print("NEW_TABLE_ROWS =", row_count)

        # 4. Chỉ thay 5 file cũ + thêm 1 service mới.
        for rel in MANIFEST["expected_after"]:
            src = PAYLOAD / rel
            dst = PROJECT / rel
            if not src.is_file():
                raise RuntimeError(f"Payload thiếu: {rel}")
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            installed_files.append(dst)

        # 5. Khóa SHA sau cài.
        for rel, expected in MANIFEST["expected_after"].items():
            actual = sha256(PROJECT / rel)
            print(f"SHA_AFTER {rel} = {actual}")
            if actual != expected:
                raise RuntimeError(f"SHA_AFTER sai: {rel}")

        # 6. Compile đúng các file Python đã chạm; parse 2 template.
        python_files = [
            PROJECT / "app/report_input_models.py",
            PROJECT / "app/services/finance_school_service.py",
            PROJECT / "app/routers/report_inputs.py",
            PROJECT / "app/routers/pcgdmn_template_report.py",
        ]
        for path in python_files:
            compile_python(path)
        parse_jinja(PROJECT / "app/templates/report_inputs/finance.html")
        parse_jinja(PROJECT / "app/templates/partials/dropdown_menu_v1.html")
        print("PY_COMPILE = OK")
        print("JINJA_PARSE = OK")

        integrity_after, fk_after = db_health(DB)
        print("INTEGRITY_AFTER =", integrity_after)
        print("FK_COUNT_AFTER =", fk_after)
        if integrity_after != "ok" or fk_after != 0:
            raise RuntimeError("Database không đạt hậu kiểm.")

        with sqlite3.connect(DB) as con:
            rows = con.execute("SELECT COUNT(*) FROM school_finance_report_values").fetchone()[0]

        print("BUSINESS_DATA_WRITE = 0")
        print("SCHEMA_CHANGE = ADD school_finance_report_values ONLY")
        print("SOURCE_FILES_REPLACED = 5")
        print("SOURCE_FILES_ADDED = 1")
        print("SCHOOL_FINANCE_ROWS =", rows)
        print("INSTALL33A_SUCCESS = YES")
        print("=" * 118)

    except Exception as exc:
        print("INSTALL ERROR =", repr(exc))
        print("ROLLBACK = START")
        for rel in MANIFEST["expected_before"]:
            src = BACKUP / rel
            dst = PROJECT / rel
            if src.exists():
                shutil.copy2(src, dst)
        for rel in MANIFEST.get("new_files", []):
            target = PROJECT / rel
            if target.exists():
                target.unlink()
        try:
            restore_db(backup_db, DB)
            print("ROLLBACK_DB = OK")
        except Exception as db_exc:
            print("ROLLBACK_DB = FAIL", repr(db_exc))
        print("ROLLBACK_SOURCE = OK")
        print("INSTALL33A_SUCCESS = NO")
        print("=" * 118)
        raise


if __name__ == "__main__":
    main()
