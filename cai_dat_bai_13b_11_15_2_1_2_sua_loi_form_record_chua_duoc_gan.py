from __future__ import annotations

import ast
import os
import re
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
    / f"backup_bai_13b_11_15_2_1_2_{STAMP}"
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

NEW_START = (
    "# === BAI_13B_11_15_2_SAVE_PRIMARY_THCS_FIELDS_START ==="
)
NEW_END = (
    "# === BAI_13B_11_15_2_SAVE_PRIMARY_THCS_FIELDS_END ==="
)

SAFE_ANCHORS = (
    "# === BAI_13B_11_13_2_SAVE_FIELDS_END ===",
    "# === BAI_13B_11_13_2_2_SAVE_FIELDS_END ===",
    "# === BAI_13B_11_13_2_1_SAVE_FIELDS_END ===",
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
        names = [
            node.name
            for node in found
        ]

        raise RuntimeError(
            "Phải tìm thấy đúng 1 route POST /nam-hoc/luu; "
            f"hiện có {len(found)}: {names}"
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


def extract_move_block(
    function_text: str,
) -> tuple[str, str]:
    start_pos = function_text.find(
        NEW_START
    )

    end_pos = function_text.find(
        NEW_END
    )

    if start_pos < 0 or end_pos < 0:
        raise RuntimeError(
            "Không tìm thấy đầy đủ block lưu Bài 15.2.1 "
            "trong route."
        )

    if end_pos <= start_pos:
        raise RuntimeError(
            "Marker block Bài 15.2.1 sai thứ tự."
        )

    # Mở rộng tới đầu dòng chứa START.
    line_start = (
        function_text.rfind(
            "\n",
            0,
            start_pos,
        )
        + 1
    )

    # Mở rộng tới hết dòng chứa END.
    line_end = function_text.find(
        "\n",
        end_pos,
    )

    if line_end < 0:
        line_end = len(function_text)
    else:
        line_end += 1

    block = function_text[
        line_start:
        line_end
    ]

    remaining = (
        function_text[:line_start]
        + function_text[line_end:]
    )

    if NEW_START in remaining or NEW_END in remaining:
        raise RuntimeError(
            "Có nhiều hơn một block Bài 15.2.1; "
            "dừng để tránh sửa nhầm."
        )

    return remaining, block


def detect_record_name(
    block: str,
) -> str:
    match = re.search(
        r"(?m)^\s*([A-Za-z_]\w*)\.study_location_scope\s*=",
        block,
    )

    if not match:
        raise RuntimeError(
            "Không xác định được biến record trong block Bài 15.2.1."
        )

    return match.group(1)


def find_safe_anchor(
    function_text: str,
    record_name: str,
) -> tuple[int, str]:
    # Ưu tiên marker của Bài 13.2 vì đây là khối đã dùng chính
    # year-record sau khi record được tìm/tạo.
    for anchor in SAFE_ANCHORS:
        pos = function_text.find(
            anchor
        )

        if pos >= 0:
            line_end = function_text.find(
                "\n",
                pos,
            )

            if line_end < 0:
                line_end = len(function_text)
            else:
                line_end += 1

            prefix = function_text[:line_end]

            # Phải có dấu hiệu record đã được sử dụng/khởi tạo
            # trong phần lưu năm học trước anchor.
            record_use = re.search(
                rf"\b{re.escape(record_name)}\.",
                prefix,
            )

            if not record_use:
                continue

            return (
                line_end,
                anchor,
            )

    # Fallback rất thận trọng:
    # tìm assignment hiện có của completed_primary_program /
    # completed_lower_secondary_program trên cùng record,
    # rồi chèn sau dòng cuối cùng của nhóm đó.
    patterns = (
        rf"(?m)^\s*{re.escape(record_name)}"
        r"\.completed_primary_program\s*=.*$",
        rf"(?m)^\s*{re.escape(record_name)}"
        r"\.completed_lower_secondary_program\s*=.*$",
        rf"(?m)^\s*{re.escape(record_name)}"
        r"\.post_lower_secondary_path\s*=.*$",
    )

    matches = []

    for pattern in patterns:
        matches.extend(
            re.finditer(
                pattern,
                function_text,
            )
        )

    if matches:
        last = max(
            matches,
            key=lambda item: item.end(),
        )

        line_end = function_text.find(
            "\n",
            last.end(),
        )

        if line_end < 0:
            line_end = len(function_text)
        else:
            line_end += 1

        return (
            line_end,
            "fallback: sau assignment dữ liệu TH/THCS hiện có",
        )

    raise RuntimeError(
        "Không tìm được điểm chèn an toàn sau khi "
        f"{record_name} đã tồn tại."
    )


def verify_order(
    function_text: str,
    record_name: str,
) -> None:
    block_pos = function_text.find(
        NEW_START
    )

    if block_pos < 0:
        raise RuntimeError(
            "Sau sửa không còn marker Bài 15.2.1."
        )

    # Trước block phải có dấu hiệu tạo/lấy record.
    prefix = function_text[:block_pos]

    assignment_patterns = (
        rf"(?m)^\s*{re.escape(record_name)}\s*=",
        rf"(?m)^\s*{re.escape(record_name)}\s*:\s*",
    )

    assigned = any(
        re.search(
            pattern,
            prefix,
        )
        for pattern in assignment_patterns
    )

    # Một số route có thể gán trong câu lệnh nhiều dòng nhưng
    # dòng đầu vẫn có "form_record =".
    if not assigned:
        raise RuntimeError(
            f"Sau sửa, chưa chứng minh được {record_name} "
            "đã được gán trước block Bài 15.2.1."
        )

    # Sau block phải còn commit của route.
    suffix = function_text[block_pos:]

    if "db.commit()" not in suffix:
        raise RuntimeError(
            "Sau điểm chèn không còn db.commit(); "
            "dừng để tránh lưu không được commit."
        )

    # Các field chính phải còn nguyên.
    required = (
        f"{record_name}.study_location_scope",
        f"{record_name}.is_repeating_grade",
        f"{record_name}.current_education_program",
        'learning_status or ""',
    )

    for token in required:
        if token not in function_text:
            raise RuntimeError(
                "Sau sửa thiếu logic: "
                + token
            )


def patch_source(
    source: str,
) -> tuple[str, str, str]:
    node = find_save_function(
        source
    )

    start, end = function_bounds(
        source,
        node,
    )

    function_text = source[
        start:
        end
    ]

    remaining, block = extract_move_block(
        function_text
    )

    record_name = detect_record_name(
        block
    )

    anchor_pos, anchor_name = find_safe_anchor(
        remaining,
        record_name,
    )

    patched_function = (
        remaining[:anchor_pos]
        + block
        + remaining[anchor_pos:]
    )

    verify_order(
        patched_function,
        record_name,
    )

    patched = (
        source[:start]
        + patched_function
        + source[end:]
    )

    ast.parse(
        patched
    )

    return (
        patched,
        record_name,
        anchor_name,
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
        "BÀI 13B-11.15.2.1.2 - "
        "SỬA LỖI 500 KHI LƯU TIỂU HỌC/THCS: "
        "form_record CHƯA ĐƯỢC GÁN"
    )
    print("=" * 132)
    print()
    print("LỖI ĐÃ XÁC ĐỊNH:")
    print(
        " - surveys.py gọi form_record.study_location_scope "
        "khi form_record chưa được tạo/tìm."
    )
    print(
        " - Nguyên nhân: block Bài 15.2.1 từng được chèn "
        "trước db.commit() đầu tiên của route, nhưng commit đó "
        "không phải commit cuối của bản ghi năm học."
    )
    print()
    print("SỬA:")
    print(
        " - Giữ nguyên toàn bộ nội dung block Bài 15.2.1."
    )
    print(
        " - Chỉ DI CHUYỂN block xuống sau khối lưu năm học "
        "Bài 13.2, nơi form_record đã tồn tại."
    )
    print(
        " - Không đổi tên field, không đổi giá trị nghiệp vụ."
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

    if (
        NEW_START not in original
        or NEW_END not in original
    ):
        raise RuntimeError(
            "Router hiện tại không có block lưu Bài 15.2.1."
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
        patched, record_name, anchor_name = patch_source(
            original
        )

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
                "Số bản ghi database thay đổi trong lúc cài."
            )

        if columns_after != columns_before:
            raise RuntimeError(
                "Schema database thay đổi trong lúc cài."
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
            " - Route:",
            "luu_theo_doi_nam_hoc",
        )
        print(
            " - Biến year record:",
            record_name,
        )
        print(
            " - Điểm chèn mới:",
            anchor_name,
        )
        print(
            " - Block 15.2.1 nằm sau khi record được gán: OK"
        )
        print(
            " - Sau block còn db.commit(): OK"
        )
        print(
            " - AST parse: OK"
        )
        print(
            " - py_compile surveys.py: OK"
        )
        print(
            " - Database/schema: KHÔNG THAY ĐỔI"
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
            "CÀI ĐẶT BÀI 13B-11.15.2.1.2 THÀNH CÔNG"
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
