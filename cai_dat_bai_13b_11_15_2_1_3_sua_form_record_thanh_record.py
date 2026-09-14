from __future__ import annotations

import ast
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
ROUTER = APP / "routers" / "surveys.py"
DB = PROJECT / "data" / "phocap.db"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = (
    PROJECT
    / "exports"
    / f"backup_bai_13b_11_15_2_1_3_{STAMP}"
)

ROUTER_BACKUP = (
    BACKUP
    / "app"
    / "routers"
    / "surveys.py"
)

DB_BACKUP = (
    BACKUP
    / "data"
    / "phocap.db"
)

START_MARKER = (
    "# === BAI_13B_11_15_2_SAVE_PRIMARY_THCS_FIELDS_START ==="
)

END_MARKER = (
    "# === BAI_13B_11_15_2_SAVE_PRIMARY_THCS_FIELDS_END ==="
)

FIELDS = (
    "study_location_scope",
    "is_repeating_grade",
    "current_education_program",
    "learning_status",
)


def read_text(path: Path) -> str:
    if not path.exists():
        raise RuntimeError(
            f"Không tìm thấy: {path}"
        )

    return path.read_text(
        encoding="utf-8-sig",
        errors="strict",
    )


def write_text(path: Path, text: str) -> None:
    path.write_text(
        text,
        encoding="utf-8",
    )


def db_check() -> tuple[int, str, int, set[str]]:
    conn = sqlite3.connect(str(DB))

    try:
        count = int(
            conn.execute(
                """
                SELECT COUNT(*)
                FROM survey_person_year_records
                """
            ).fetchone()[0]
        )

        integrity = str(
            conn.execute(
                "PRAGMA integrity_check"
            ).fetchone()[0]
        )

        fk = len(
            conn.execute(
                "PRAGMA foreign_key_check"
            ).fetchall()
        )

        columns = {
            str(row[1])
            for row in conn.execute(
                'PRAGMA table_info("survey_person_year_records")'
            ).fetchall()
        }

        return (
            count,
            integrity,
            fk,
            columns,
        )

    finally:
        conn.close()


def backup_db() -> None:
    DB_BACKUP.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    src = sqlite3.connect(str(DB))
    dst = sqlite3.connect(str(DB_BACKUP))

    try:
        src.backup(dst)
        dst.commit()
    finally:
        dst.close()
        src.close()


def restore_db() -> None:
    src = sqlite3.connect(str(DB_BACKUP))
    dst = sqlite3.connect(str(DB))

    try:
        src.backup(dst)
        dst.commit()
    finally:
        dst.close()
        src.close()


def find_save_function(
    source: str,
) -> ast.FunctionDef | ast.AsyncFunctionDef:
    tree = ast.parse(source)

    found = []

    for node in ast.walk(tree):
        if not isinstance(
            node,
            (
                ast.FunctionDef,
                ast.AsyncFunctionDef,
            ),
        ):
            continue

        decorators = "\n".join(
            ast.get_source_segment(
                source,
                dec,
            )
            or ""
            for dec in node.decorator_list
        )

        if (
            "/nam-hoc/luu" in decorators
            and ".post" in decorators.lower()
        ):
            found.append(node)

    if len(found) != 1:
        raise RuntimeError(
            "Phải tìm thấy đúng 1 route POST /nam-hoc/luu; "
            f"hiện tìm thấy {len(found)}."
        )

    return found[0]


def function_bounds(
    source: str,
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> tuple[int, int]:
    lines = source.splitlines(
        keepends=True
    )

    start = sum(
        len(line)
        for line in lines[
            : int(node.lineno) - 1
        ]
    )

    end = sum(
        len(line)
        for line in lines[
            : int(node.end_lineno)
        ]
    )

    return start, end


def patch_source(
    source: str,
) -> tuple[str, int]:
    node = find_save_function(
        source
    )

    function_start, function_end = function_bounds(
        source,
        node,
    )

    function_text = source[
        function_start:
        function_end
    ]

    start = function_text.find(
        START_MARKER
    )

    end = function_text.find(
        END_MARKER
    )

    if start < 0 or end < 0 or end <= start:
        raise RuntimeError(
            "Không tìm thấy đầy đủ block lưu Bài 15.2.1."
        )

    block_end = end + len(
        END_MARKER
    )

    block = function_text[
        start:
        block_end
    ]

    prefix = function_text[
        :start
    ]

    # Khảo sát đã chứng minh luồng lưu bình thường dùng biến record.
    if (
        "record = SurveyPersonYearRecord(" not in prefix
        and "record = existing_record or SurveyPersonYearRecord(" not in prefix
    ):
        raise RuntimeError(
            "Không tìm thấy assignment tạo year-record bằng biến record "
            "trước block Bài 15.2.1. Dừng để tránh sửa nhầm."
        )

    # Block cũ phải đang dùng sai form_record cho ít nhất 1 field.
    wrong_occurrences = sum(
        block.count(
            f"form_record.{field}"
        )
        for field in FIELDS
    )

    if wrong_occurrences == 0:
        # Nếu đã sửa đúng rồi thì coi là không cần cài lặp.
        correct_occurrences = sum(
            block.count(
                f"record.{field}"
            )
            for field in FIELDS
        )

        if correct_occurrences >= 4:
            return source, 0

        raise RuntimeError(
            "Block Bài 15.2.1 không có form_record.* "
            "nhưng cũng chưa đủ record.*; dừng để khảo sát lại."
        )

    patched_block = block

    changes = 0

    for field in FIELDS:
        old = f"form_record.{field}"
        new = f"record.{field}"

        n = patched_block.count(
            old
        )

        if n:
            patched_block = patched_block.replace(
                old,
                new,
            )
            changes += n

    if changes != wrong_occurrences:
        raise RuntimeError(
            "Số thay thế không khớp số lỗi phát hiện."
        )

    if "form_record." in patched_block:
        # Không cấm form_record ngoài block, vì nhánh validation
        # vẫn dùng đúng biến này để render lại form lỗi.
        raise RuntimeError(
            "Sau sửa block Bài 15.2.1 vẫn còn form_record.*."
        )

    for field in FIELDS:
        if f"record.{field}" not in patched_block:
            raise RuntimeError(
                "Sau sửa block thiếu: "
                f"record.{field}"
            )

    patched_function = (
        function_text[:start]
        + patched_block
        + function_text[block_end:]
    )

    patched_source = (
        source[:function_start]
        + patched_function
        + source[function_end:]
    )

    ast.parse(
        patched_source
    )

    return (
        patched_source,
        changes,
    )


def compile_router() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "py_compile",
            str(ROUTER),
        ],
        cwd=PROJECT,
        capture_output=True,
        text=True,
    )

    if result.stdout:
        print(
            result.stdout.rstrip()
        )

    if result.stderr:
        print(
            result.stderr.rstrip()
        )

    if result.returncode != 0:
        raise RuntimeError(
            "py_compile surveys.py không đạt."
        )


def clear_cache() -> None:
    for cache in APP.rglob(
        "__pycache__"
    ):
        if cache.is_dir():
            shutil.rmtree(
                cache,
                ignore_errors=True,
            )


def main() -> int:
    print("=" * 132)
    print(
        "BÀI 13B-11.15.2.1.3 - "
        "SỬA ĐÚNG BIẾN LƯU TIỂU HỌC/THCS: "
        "form_record -> record"
    )
    print("=" * 132)
    print()
    print("KẾT LUẬN TỪ KHẢO SÁT:")
    print(
        " - form_record chỉ được tạo trong nhánh if errors "
        "để render lại form."
    )
    print(
        " - Luồng lưu bình thường dùng biến record."
    )
    print(
        " - Block Bài 15.2.1 đang dùng nhầm form_record "
        "nên phát sinh UnboundLocalError."
    )
    print()
    print("SỬA:")
    print(
        " - Chỉ trong block Bài 15.2.1:"
    )
    print(
        "   form_record.study_location_scope "
        "-> record.study_location_scope"
    )
    print(
        "   form_record.is_repeating_grade "
        "-> record.is_repeating_grade"
    )
    print(
        "   form_record.current_education_program "
        "-> record.current_education_program"
    )
    print(
        "   form_record.learning_status "
        "-> record.learning_status"
    )
    print()
    print("GIỮ NGUYÊN:")
    print(
        " - form_record ở nhánh validation lỗi."
    )
    print(
        " - Giao diện Bài 15.2.3.2."
    )
    print(
        " - Nơi học / Lưu ban / Chương trình."
    )
    print(
        " - Bỏ học / Chưa đi học."
    )
    print(
        " - Database và schema."
    )
    print()
    print("AN TOÀN:")
    print(
        " - Chỉ sửa app/routers/surveys.py."
    )
    print(
        " - Không sửa template."
    )
    print(
        " - Không ALTER/INSERT/UPDATE/DELETE database khi cài."
    )
    print(
        " - Backup router + database."
    )
    print(
        " - AST + py_compile + integrity + foreign key."
    )
    print(
        " - Có lỗi tự rollback."
    )
    print()

    if not ROUTER.exists():
        raise RuntimeError(
            f"Không tìm thấy router: {ROUTER}"
        )

    if not DB.exists():
        raise RuntimeError(
            f"Không tìm thấy database: {DB}"
        )

    (
        count_before,
        integrity_before,
        fk_before,
        columns_before,
    ) = db_check()

    if (
        integrity_before.lower() != "ok"
        or fk_before != 0
    ):
        raise RuntimeError(
            "Database không đạt kiểm tra an toàn trước cài."
        )

    required_columns = {
        "study_location_scope",
        "is_repeating_grade",
        "current_education_program",
    }

    missing_columns = sorted(
        required_columns
        - columns_before
    )

    if missing_columns:
        raise RuntimeError(
            "Database thiếu schema Bài 15.1: "
            + ", ".join(missing_columns)
        )

    original = read_text(
        ROUTER
    )

    print(
        "survey_person_year_records:",
        count_before,
        "bản ghi",
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

    patched, changes = patch_source(
        original
    )

    if changes == 0:
        print()
        print(
            "Block Bài 15.2.1 đã dùng đúng biến record; "
            "không cần cài lặp."
        )
        return 0

    BACKUP.mkdir(
        parents=True,
        exist_ok=False,
    )

    ROUTER_BACKUP.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    shutil.copy2(
        ROUTER,
        ROUTER_BACKUP,
    )

    backup_db()

    print(
        "Backup:",
        BACKUP,
    )

    try:
        write_text(
            ROUTER,
            patched,
        )

        compile_router()

        (
            count_after,
            integrity_after,
            fk_after,
            columns_after,
        ) = db_check()

        if count_after != count_before:
            raise RuntimeError(
                "Số bản ghi database thay đổi khi cài."
            )

        if columns_after != columns_before:
            raise RuntimeError(
                "Schema database thay đổi khi cài."
            )

        if integrity_after.lower() != "ok":
            raise RuntimeError(
                "integrity_check sau cài không OK."
            )

        if fk_after != 0:
            raise RuntimeError(
                "foreign_key_check sau cài có "
                f"{fk_after} lỗi."
            )

        clear_cache()

        print()
        print("KIỂM TRA SAU CÀI:")
        print(
            " - Số chỗ form_record -> record đã sửa:",
            changes,
        )
        print(
            " - form_record trong nhánh validation: GIỮ NGUYÊN"
        )
        print(
            " - Block Bài 15.2.1 dùng record: OK"
        )
        print(
            " - AST parse: OK"
        )
        print(
            " - py_compile surveys.py: OK"
        )
        print(
            " - Template: KHÔNG ĐỤNG"
        )
        print(
            " - Database/schema/dữ liệu: KHÔNG THAY ĐỔI"
        )
        print(
            " - integrity_check: OK"
        )
        print(
            " - foreign_key_check: 0 lỗi"
        )
        print()
        print("=" * 132)
        print(
            "CÀI ĐẶT BÀI 13B-11.15.2.1.3 THÀNH CÔNG"
        )
        print("=" * 132)

        return 0

    except Exception:
        traceback.print_exc()

        print()
        print(
            "CÓ LỖI - ĐANG KHÔI PHỤC ROUTER/DATABASE..."
        )

        try:
            shutil.copy2(
                ROUTER_BACKUP,
                ROUTER,
            )

            print(
                " - Đã khôi phục surveys.py."
            )

        except Exception as exc:
            print(
                " - Lỗi khôi phục router:",
                exc,
            )

        try:
            restore_db()

            print(
                " - Đã khôi phục database."
            )

        except Exception as exc:
            print(
                " - Lỗi khôi phục database:",
                exc,
            )

        clear_cache()

        print(
            "Backup:",
            BACKUP,
        )

        return 1


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
