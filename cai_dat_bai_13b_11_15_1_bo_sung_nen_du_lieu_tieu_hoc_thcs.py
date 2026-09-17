from __future__ import annotations

import ast
import importlib
import os
import shutil
import sqlite3
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path


PROJECT = Path(
    os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")
).resolve()

APP = PROJECT / "app"
DB_PATH = PROJECT / "data" / "phocap.db"
EXPORTS = PROJECT / "exports"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = EXPORTS / f"backup_bai_13b_11_15_1_{STAMP}"

TABLE = "survey_person_year_records"

NEW_COLUMNS = [
    (
        "study_location_scope",
        "VARCHAR(30)",
        "'CHUA_XAC_DINH'",
        "Nơi học dùng chung Tiểu học + THCS: "
        "CHUA_XAC_DINH / TAI_CHO / "
        "DI_HOC_NOI_KHAC / NOI_KHAC_DEN",
    ),
    (
        "is_repeating_grade",
        "BOOLEAN",
        None,
        "Lưu ban: NULL=Chưa xác định, 1=Có, 0=Không",
    ),
    (
        "current_education_program",
        "VARCHAR(30)",
        "'CHUA_XAC_DINH'",
        "Chương trình đang học - chỉ hiển thị ở THCS: "
        "CHUA_XAC_DINH / THPT / GDTX / GDNN / KHAC",
    ),
]

MODEL_FIELD_BLOCKS = {
    "study_location_scope": '''    study_location_scope: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="CHUA_XAC_DINH",
        server_default="CHUA_XAC_DINH",
    )
''',
    "is_repeating_grade": '''    is_repeating_grade: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
    )
''',
    "current_education_program": '''    current_education_program: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="CHUA_XAC_DINH",
        server_default="CHUA_XAC_DINH",
    )
''',
}

MARK_START = "# === BAI_13B_11_15_1_PRIMARY_THCS_FIELDS_START ==="
MARK_END = "# === BAI_13B_11_15_1_PRIMARY_THCS_FIELDS_END ==="


def say(text: str = "") -> None:
    print(text)


def read_text(path: Path) -> str:
    if not path.exists():
        raise RuntimeError(f"Không tìm thấy: {path}")

    return path.read_text(
        encoding="utf-8-sig",
        errors="strict",
    )


def write_text(path: Path, text: str) -> None:
    path.write_text(
        text,
        encoding="utf-8",
    )


def sqlite_backup(source: Path, target: Path) -> None:
    target.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    src = sqlite3.connect(str(source))
    dst = sqlite3.connect(str(target))

    try:
        src.backup(dst)
        dst.commit()
    finally:
        dst.close()
        src.close()


def sqlite_restore(source_backup: Path, target_db: Path) -> None:
    src = sqlite3.connect(str(source_backup))
    dst = sqlite3.connect(str(target_db))

    try:
        src.backup(dst)
        dst.commit()
    finally:
        dst.close()
        src.close()


def db_columns(db_path: Path) -> dict[str, tuple]:
    conn = sqlite3.connect(str(db_path))

    try:
        rows = conn.execute(
            f'PRAGMA table_info("{TABLE}")'
        ).fetchall()

        return {
            str(row[1]): row
            for row in rows
        }

    finally:
        conn.close()


def db_count(db_path: Path) -> int:
    conn = sqlite3.connect(str(db_path))

    try:
        return int(
            conn.execute(
                f'SELECT COUNT(*) FROM "{TABLE}"'
            ).fetchone()[0]
        )

    finally:
        conn.close()


def db_integrity(db_path: Path) -> tuple[str, int]:
    conn = sqlite3.connect(str(db_path))

    try:
        integrity = str(
            conn.execute(
                "PRAGMA integrity_check"
            ).fetchone()[0]
        )

        fk_total = len(
            conn.execute(
                "PRAGMA foreign_key_check"
            ).fetchall()
        )

        return integrity, fk_total

    finally:
        conn.close()


def locate_model_source() -> tuple[Path, ast.ClassDef]:
    candidates: list[tuple[Path, ast.ClassDef]] = []

    for path in APP.rglob("*.py"):
        low_parts = {
            part.lower()
            for part in path.parts
        }

        if (
            "__pycache__" in low_parts
            or "backup" in low_parts
            or "backups" in low_parts
        ):
            continue

        try:
            text = read_text(path)
            tree = ast.parse(text)
        except Exception:
            continue

        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue

            if node.name == "SurveyPersonYearRecord":
                candidates.append((path, node))
                continue

            class_text = ast.get_source_segment(text, node) or ""

            if (
                "survey_person_year_records" in class_text
                and "mapped_column" in class_text
            ):
                candidates.append((path, node))

    unique = {}

    for path, node in candidates:
        unique[
            (
                str(path.resolve()),
                node.name,
            )
        ] = (
            path,
            node,
        )

    found = list(
        unique.values()
    )

    if len(found) != 1:
        detail = "\n".join(
            " - "
            f"{path.relative_to(PROJECT)} "
            f":: {node.name}"
            for path, node in found
        )

        raise RuntimeError(
            "Phải xác định được đúng 1 class "
            "SurveyPersonYearRecord.\n"
            f"Hiện tìm thấy {len(found)}:\n"
            f"{detail}"
        )

    return found[0]


def assigned_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.AnnAssign):
        if isinstance(node.target, ast.Name):
            return node.target.id

    if isinstance(node, ast.Assign):
        if (
            len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
        ):
            return node.targets[0].id

    return None


def class_field_names(
    text: str,
    class_node: ast.ClassDef,
) -> set[str]:
    names = set()

    for item in class_node.body:
        name = assigned_name(item)

        if name:
            names.add(name)

    return names


def find_insert_line(
    text: str,
    class_node: ast.ClassDef,
) -> int:
    preferred = (
        "post_lower_secondary_path",
        "completed_lower_secondary_program",
        "completed_primary_program",
        "class_name_reported",
    )

    by_name: dict[str, ast.AST] = {}

    for item in class_node.body:
        name = assigned_name(item)

        if name:
            by_name[name] = item

    for name in preferred:
        item = by_name.get(name)

        if item is not None:
            return int(item.end_lineno)

    last_line = None

    for item in class_node.body:
        item_text = ast.get_source_segment(text, item) or ""

        if "mapped_column" not in item_text:
            continue

        if isinstance(
            item,
            (
                ast.AnnAssign,
                ast.Assign,
            ),
        ):
            last_line = int(item.end_lineno)

    if last_line is None:
        raise RuntimeError(
            "Không xác định được vị trí chèn field "
            "trong SurveyPersonYearRecord."
        )

    return last_line


def patch_model(path: Path) -> bool:
    text = read_text(path)
    tree = ast.parse(text)

    target = None

    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue

        if node.name == "SurveyPersonYearRecord":
            target = node
            break

        class_text = ast.get_source_segment(text, node) or ""

        if (
            "survey_person_year_records" in class_text
            and "mapped_column" in class_text
        ):
            target = node
            break

    if target is None:
        raise RuntimeError(
            "Không tìm thấy class SurveyPersonYearRecord khi patch."
        )

    existing_names = class_field_names(
        text,
        target,
    )

    missing = [
        name
        for name, _, _, _ in NEW_COLUMNS
        if name not in existing_names
    ]

    if not missing:
        say(
            " - Model đã có đủ 3 field Bài 13B-11.15.1; "
            "không chèn lặp."
        )
        return False

    if MARK_START in text or MARK_END in text:
        raise RuntimeError(
            "Model có marker Bài 13B-11.15.1 "
            "nhưng vẫn thiếu field. "
            "Dừng để tránh chèn sai cấu trúc."
        )

    class_text = ast.get_source_segment(
        text,
        target,
    ) or ""

    if (
        "Mapped[" not in class_text
        or "mapped_column" not in class_text
    ):
        raise RuntimeError(
            "SurveyPersonYearRecord không dùng "
            "Mapped/mapped_column như dự kiến."
        )

    if "String" not in text or "Boolean" not in text:
        raise RuntimeError(
            "Model source chưa có String/Boolean; "
            "dừng để khảo sát riêng."
        )

    insert_after_line = find_insert_line(
        text,
        target,
    )

    block_lines = [
        f"    {MARK_START}\n",
    ]

    for name in missing:
        block_lines.append(
            MODEL_FIELD_BLOCKS[name]
        )

    block_lines.append(
        f"    {MARK_END}\n"
    )

    block = (
        "\n"
        + "".join(block_lines)
        + "\n"
    )

    lines = text.splitlines(
        keepends=True
    )

    lines[
        insert_after_line:
        insert_after_line
    ] = [
        block
    ]

    patched = "".join(lines)

    ast.parse(patched)
    write_text(
        path,
        patched,
    )

    return True


def apply_db_columns() -> list[str]:
    conn = sqlite3.connect(str(DB_PATH))
    created = []

    try:
        existing = {
            str(row[1])
            for row in conn.execute(
                f'PRAGMA table_info("{TABLE}")'
            ).fetchall()
        }

        if "learning_status" not in existing:
            raise RuntimeError(
                "Database thiếu learning_status. "
                "Không thể tái sử dụng cho Bỏ học/Chưa đi học."
            )

        for (
            name,
            sql_type,
            default_sql,
            _,
        ) in NEW_COLUMNS:
            if name in existing:
                say(
                    f" - DB đã có cột {name}: giữ nguyên."
                )
                continue

            sql = (
                f'ALTER TABLE "{TABLE}" '
                f'ADD COLUMN "{name}" '
                f'{sql_type}'
            )

            if default_sql is not None:
                sql += (
                    " NOT NULL DEFAULT "
                    + default_sql
                )

            conn.execute(sql)
            created.append(name)

            say(
                " - Đã tạo cột DB: "
                + name
            )

        conn.commit()
        return created

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


def verify_model_file(path: Path) -> None:
    text = read_text(path)
    tree = ast.parse(text)

    target = None

    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue

        if node.name == "SurveyPersonYearRecord":
            target = node
            break

        class_text = ast.get_source_segment(text, node) or ""

        if (
            "survey_person_year_records" in class_text
            and "mapped_column" in class_text
        ):
            target = node
            break

    if target is None:
        raise RuntimeError(
            "Không tìm thấy model SurveyPersonYearRecord sau cài."
        )

    names = class_field_names(
        text,
        target,
    )

    for name, _, _, _ in NEW_COLUMNS:
        if name not in names:
            raise RuntimeError(
                "Model source thiếu field sau cài: "
                f"{name}"
            )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "py_compile",
            str(path),
        ],
        cwd=PROJECT,
        text=True,
        capture_output=True,
    )

    if result.stdout:
        say(
            result.stdout.rstrip()
        )

    if result.stderr:
        say(
            result.stderr.rstrip()
        )

    if result.returncode != 0:
        raise RuntimeError(
            f"py_compile không đạt: {path}"
        )


def verify_runtime_model(path: Path) -> None:
    relative = (
        path.relative_to(PROJECT)
        .with_suffix("")
    )

    module_name = ".".join(
        relative.parts
    )

    importlib.invalidate_caches()

    if module_name in sys.modules:
        del sys.modules[module_name]

    module = importlib.import_module(
        module_name
    )

    cls = getattr(
        module,
        "SurveyPersonYearRecord",
        None,
    )

    if cls is None:
        for value in vars(module).values():
            if isinstance(value, type):
                if (
                    getattr(
                        value,
                        "__tablename__",
                        None,
                    )
                    == TABLE
                ):
                    cls = value
                    break

    if cls is None:
        raise RuntimeError(
            "Runtime import không tìm thấy "
            "SurveyPersonYearRecord."
        )

    for name, _, _, _ in NEW_COLUMNS:
        if not hasattr(cls, name):
            raise RuntimeError(
                "Runtime model thiếu attribute: "
                f"{name}"
            )


def verify_db(count_before: int) -> None:
    columns_after = db_columns(
        DB_PATH
    )

    required_existing = (
        "learning_status",
        "completed_primary_program",
        "completed_lower_secondary_program",
        "post_lower_secondary_path",
    )

    for name in required_existing:
        if name not in columns_after:
            raise RuntimeError(
                "Database thiếu field nền đã chốt: "
                f"{name}"
            )

    for name, _, _, _ in NEW_COLUMNS:
        if name not in columns_after:
            raise RuntimeError(
                "Database thiếu cột sau cài: "
                f"{name}"
            )

    count_after = db_count(
        DB_PATH
    )

    if count_after != count_before:
        raise RuntimeError(
            "Số bản ghi survey_person_year_records thay đổi: "
            f"{count_before} -> {count_after}"
        )

    integrity, fk_total = db_integrity(
        DB_PATH
    )

    if integrity.lower() != "ok":
        raise RuntimeError(
            "integrity_check không đạt: "
            f"{integrity}"
        )

    if fk_total != 0:
        raise RuntimeError(
            "foreign_key_check phát hiện "
            f"{fk_total} lỗi."
        )


def verify_new_values(
    created_columns: list[str],
    count_before: int,
) -> None:
    if not created_columns:
        return

    conn = sqlite3.connect(str(DB_PATH))

    try:
        if "is_repeating_grade" in created_columns:
            nonnull = int(
                conn.execute(
                    f'''
                    SELECT COUNT(*)
                    FROM "{TABLE}"
                    WHERE is_repeating_grade IS NOT NULL
                    '''
                ).fetchone()[0]
            )

            if nonnull != 0:
                raise RuntimeError(
                    "is_repeating_grade đã bị tự điền dữ liệu."
                )

        for column in (
            "study_location_scope",
            "current_education_program",
        ):
            if column not in created_columns:
                continue

            unknown_count = int(
                conn.execute(
                    f'''
                    SELECT COUNT(*)
                    FROM "{TABLE}"
                    WHERE "{column}" = 'CHUA_XAC_DINH'
                    '''
                ).fetchone()[0]
            )

            if unknown_count != count_before:
                raise RuntimeError(
                    f"{column} không ở trạng thái "
                    "CHUA_XAC_DINH cho toàn bộ dữ liệu cũ."
                )

    finally:
        conn.close()


def clear_cache() -> None:
    for cache in APP.rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(
                cache,
                ignore_errors=True,
            )


def main() -> int:
    say("=" * 126)
    say(
        "BÀI 13B-11.15.1 - "
        "BỔ SUNG NỀN DỮ LIỆU DÙNG CHUNG "
        "TIỂU HỌC + THCS"
    )
    say("=" * 126)
    say()
    say("NGHIỆP VỤ CHỐT:")
    say(
        " - Tiểu học và THCS dùng chung "
        "Nơi học + Lưu ban."
    )
    say(
        " - THCS có thêm Chương trình đang học."
    )
    say(
        " - Tiểu học KHÔNG hiển thị THPT/GDTX/GDNN."
    )
    say(
        " - Bỏ học và Chưa đi học tái sử dụng "
        "learning_status hiện có."
    )
    say(
        " - KHÔNG tạo is_dropout."
    )
    say(
        " - KHÔNG tạo never_attended_school."
    )
    say()
    say("CỘT MỚI:")

    for (
        name,
        _,
        _,
        description,
    ) in NEW_COLUMNS:
        say(
            f" - {name}: {description}"
        )

    say()
    say("CHƯA LÀM Ở BÀI 15.1:")
    say(
        " - Chưa sửa giao diện Thông tin năm học."
    )
    say(
        " - Chưa sửa báo cáo Tiểu học/THCS."
    )
    say(
        " - Chưa thay đổi lựa chọn learning_status "
        "trên giao diện."
    )
    say()
    say("AN TOÀN:")
    say(
        " - Backup database bằng SQLite Backup API."
    )
    say(
        " - Backup model trước khi sửa."
    )
    say(
        " - Chỉ ADD COLUMN còn thiếu."
    )
    say(
        " - Không UPDATE dữ liệu cũ."
    )
    say(
        " - Dữ liệu mới mặc định Chưa xác định."
    )
    say(
        " - py_compile + runtime import "
        "+ integrity + foreign key."
    )
    say(
        " - Có lỗi tự rollback source + database."
    )
    say()

    if not DB_PATH.exists():
        raise RuntimeError(
            f"Không tìm thấy database: {DB_PATH}"
        )

    columns_before = db_columns(
        DB_PATH
    )

    if not columns_before:
        raise RuntimeError(
            f"Không tìm thấy bảng {TABLE}."
        )

    required_before = (
        "learning_status",
        "completed_primary_program",
        "completed_lower_secondary_program",
        "post_lower_secondary_path",
    )

    missing_before = [
        name
        for name in required_before
        if name not in columns_before
    ]

    if missing_before:
        raise RuntimeError(
            "Thiếu nền Bài 13B-11.13.1: "
            + ", ".join(missing_before)
        )

    integrity_before, fk_before = db_integrity(
        DB_PATH
    )

    if (
        integrity_before.lower() != "ok"
        or fk_before != 0
    ):
        raise RuntimeError(
            "Database không đạt kiểm tra an toàn trước cài."
        )

    count_before = db_count(
        DB_PATH
    )

    say(
        "integrity_check trước cài: "
        f"{integrity_before}"
    )
    say(
        "foreign_key_check trước cài: "
        f"{fk_before} lỗi"
    )
    say(
        "survey_person_year_records trước cài: "
        f"{count_before}"
    )

    model_path, model_class = locate_model_source()

    say(
        "Model phát hiện: "
        f"{model_path.relative_to(PROJECT)} "
        f":: {model_class.name}"
    )

    BACKUP.mkdir(
        parents=True,
        exist_ok=False,
    )

    backup_model = (
        BACKUP
        / model_path.relative_to(PROJECT)
    )

    backup_model.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    shutil.copy2(
        model_path,
        backup_model,
    )

    backup_db = BACKUP / "phocap.db"

    sqlite_backup(
        DB_PATH,
        backup_db,
    )

    say(
        "Backup: "
        f"{BACKUP}"
    )

    try:
        model_changed = patch_model(
            model_path
        )

        created_columns = apply_db_columns()

        verify_model_file(
            model_path
        )

        verify_runtime_model(
            model_path
        )

        verify_db(
            count_before
        )

        verify_new_values(
            created_columns,
            count_before,
        )

        clear_cache()

        say()
        say("KIỂM TRA SAU CÀI:")
        say(
            " - learning_status: GIỮ NGUYÊN để dùng "
            "DANG_HOC / BO_HOC / CHUA_DI_HOC / ..."
        )
        say(
            " - study_location_scope: ĐÃ CÓ"
        )
        say(
            " - is_repeating_grade: ĐÃ CÓ"
        )
        say(
            " - current_education_program: ĐÃ CÓ"
        )
        say(
            " - Tiểu học: sẽ không hiển thị "
            "current_education_program."
        )
        say(
            " - THCS: sẽ dùng THPT/GDTX/GDNN/KHAC."
        )
        say(
            " - Model source thay đổi: "
            + (
                "CÓ"
                if model_changed
                else "KHÔNG - đã đủ field"
            )
        )
        say(
            " - DB cột mới tạo: "
            + (
                ", ".join(created_columns)
                if created_columns
                else "không - đã tồn tại"
            )
        )
        say(
            " - Số bản ghi: "
            f"{count_before} - GIỮ NGUYÊN"
        )
        say(
            " - py_compile: OK"
        )
        say(
            " - runtime model attributes: OK"
        )
        say(
            " - integrity_check: OK"
        )
        say(
            " - foreign_key_check: 0 lỗi"
        )
        say()
        say("=" * 126)
        say(
            "CÀI ĐẶT BÀI 13B-11.15.1 THÀNH CÔNG"
        )
        say("=" * 126)
        say()
        say("BƯỚC TIẾP THEO:")
        say(
            " - Bài 13B-11.15.2: nối các field này "
            "vào Thông tin năm học."
        )
        say(
            " - Tiểu học: Nơi học + Lưu ban + "
            "Đang học/Bỏ học/Chưa đi học."
        )
        say(
            " - THCS: thêm Chương trình "
            "THPT/GDTX/GDNN/Khác."
        )

        return 0

    except Exception:
        traceback.print_exc()

        say()
        say(
            "CÓ LỖI - ĐANG KHÔI PHỤC "
            "MODEL VÀ DATABASE..."
        )

        try:
            shutil.copy2(
                backup_model,
                model_path,
            )

            say(
                " - Đã khôi phục model."
            )

        except Exception as exc:
            say(
                " - Lỗi khôi phục model: "
                f"{exc}"
            )

        try:
            sqlite_restore(
                backup_db,
                DB_PATH,
            )

            say(
                " - Đã khôi phục database."
            )

        except Exception as exc:
            say(
                " - Lỗi khôi phục database: "
                f"{exc}"
            )

        clear_cache()

        say(
            "Backup: "
            f"{BACKUP}"
        )

        return 1


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
