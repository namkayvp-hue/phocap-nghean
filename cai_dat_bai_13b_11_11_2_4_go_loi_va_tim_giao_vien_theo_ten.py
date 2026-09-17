from __future__ import annotations

import ast
import os
import re
import shutil
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path

PROJECT = Path(os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")).resolve()
APP = PROJECT / "app"
ROUTER = APP / "routers" / "users.py"
TEMPLATES = APP / "templates"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = PROJECT / "exports" / f"backup_source_bai_13b_11_11_2_4_{STAMP}"

OLD_BLOCK_START = "# === BAI_13B_11_11_2_TEACHER_NAME_ONLY_START ==="
OLD_BLOCK_END = "# === BAI_13B_11_11_2_TEACHER_NAME_ONLY_END ==="

MARK_PREP_START = "# === BAI_13B_11_11_2_4_PREPARE_NAME_START ==="
MARK_PREP_END = "# === BAI_13B_11_11_2_4_PREPARE_NAME_END ==="
MARK_FILTER_START = "# === BAI_13B_11_11_2_4_FILTER_NAME_START ==="
MARK_FILTER_END = "# === BAI_13B_11_11_2_4_FILTER_NAME_END ==="

UI_START = "<!-- === BAI_13B_11_11_2_4_UI_START === -->"
UI_END = "<!-- === BAI_13B_11_11_2_4_UI_END === -->"

UI_BLOCK = '<!-- === BAI_13B_11_11_2_4_UI_START === -->\n<script>\n(function () {\n    function applyTeacherSearchUi() {\n        var params = new URLSearchParams(window.location.search || "");\n        if (String(params.get("muc") || "").toLowerCase() !== "giao_vien") {\n            return;\n        }\n\n        var input = document.querySelector(\'input[name="q"]\');\n        if (!input) return;\n\n        input.placeholder = "Nhập họ và tên giáo viên";\n        input.title = "Chỉ tìm theo toàn bộ hoặc một phần họ và tên giáo viên";\n\n        var label = null;\n        if (input.id) {\n            label = document.querySelector(\'label[for="\' + input.id + \'"]\');\n        }\n        if (!label && input.parentElement) {\n            label = input.parentElement.querySelector("label");\n        }\n        if (label) {\n            label.textContent = "Tìm tên giáo viên";\n        }\n    }\n\n    if (document.readyState === "loading") {\n        document.addEventListener("DOMContentLoaded", applyTeacherSearchUi);\n    } else {\n        applyTeacherSearchUi();\n    }\n})();\n</script>\n<!-- === BAI_13B_11_11_2_4_UI_END === -->'


def read_text(path: Path) -> str:
    if not path.exists():
        raise RuntimeError(f"Không tìm thấy tệp: {path}")
    return path.read_text(encoding="utf-8-sig")


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def backup_file(path: Path) -> None:
    dst = BACKUP / path.relative_to(PROJECT)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, dst)


def restore_file(path: Path) -> None:
    src = BACKUP / path.relative_to(PROJECT)
    if src.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, path)


def clear_cache() -> None:
    for cache in APP.rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(cache, ignore_errors=True)


def remove_marker_block(text: str, start_marker: str, end_marker: str) -> tuple[str, int]:
    removed = 0

    while start_marker in text:
        start = text.find(start_marker)
        end = text.find(end_marker, start)
        if end < 0:
            raise RuntimeError(f"Thiếu marker cuối: {end_marker}")

        end += len(end_marker)
        line_start = text.rfind("\n", 0, start) + 1
        line_end = text.find("\n", end)

        if line_end < 0:
            line_end = len(text)
        else:
            line_end += 1

        text = text[:line_start] + text[line_end:]
        removed += 1

    return text, removed


def remove_previous_attempts(text: str) -> tuple[str, int]:
    total = 0

    pairs = [
        (OLD_BLOCK_START, OLD_BLOCK_END),
        (
            "# === BAI_13B_11_11_2_3_TEACHER_KEYWORD_START ===",
            "# === BAI_13B_11_11_2_3_TEACHER_KEYWORD_END ===",
        ),
        (
            "# === BAI_13B_11_11_2_3_TEACHER_FILTER_START ===",
            "# === BAI_13B_11_11_2_3_TEACHER_FILTER_END ===",
        ),
    ]

    for start_marker, end_marker in pairs:
        text, count = remove_marker_block(text, start_marker, end_marker)
        total += count

    return text, total


def find_route_function(text: str):
    tree = ast.parse(text)
    matches = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "danh_sach_tai_khoan"
    ]

    if len(matches) != 1:
        raise RuntimeError(
            f"Phải có đúng 1 hàm danh_sach_tai_khoan, hiện có {len(matches)}."
        )

    return matches[0]


def find_helper_assignment(text: str, func):
    matches = []

    for node in ast.walk(func):
        if not isinstance(node, ast.Assign):
            continue

        value = node.value
        if not isinstance(value, ast.Call):
            continue

        name = ""
        if isinstance(value.func, ast.Name):
            name = value.func.id
        elif isinstance(value.func, ast.Attribute):
            name = value.func.attr

        if name == "lay_danh_sach_tai_khoan_phan_trang":
            matches.append(node)

    if len(matches) != 1:
        raise RuntimeError(
            "Phải tìm thấy đúng 1 lời gọi "
            "lay_danh_sach_tai_khoan_phan_trang, "
            f"hiện có {len(matches)}."
        )

    return matches[0]


def indent_block(text: str, spaces: int) -> str:
    prefix = " " * spaces
    return "\n".join(
        prefix + line if line.strip() else line
        for line in text.splitlines()
    )


def patch_backend(text: str) -> tuple[str, int]:
    text, removed = remove_previous_attempts(text)

    if MARK_PREP_START in text or MARK_FILTER_START in text:
        raise RuntimeError(
            "Source đã có một phần Bài 13B-11.11.2.4; "
            "dừng để tránh chèn lặp."
        )

    old_keyword = '    keyword = " ".join(q.strip().split())\n'
    if old_keyword not in text:
        raise RuntimeError(
            "Không tìm thấy dòng keyword chuẩn trong danh_sach_tai_khoan."
        )

    new_keyword = (
        old_keyword
        + f"    {MARK_PREP_START}\n"
        + '    teacher_name_keyword = (\n'
        + '        keyword.casefold()\n'
        + '        if section == "giao_vien" and keyword\n'
        + '        else ""\n'
        + '    )\n'
        + f"    {MARK_PREP_END}\n"
    )

    text = text.replace(old_keyword, new_keyword, 1)

    func = find_route_function(text)
    assignment = find_helper_assignment(text, func)

    lines = text.splitlines(keepends=True)
    start = assignment.lineno - 1
    end = assignment.end_lineno

    call_text = "".join(lines[start:end]).rstrip("\r\n")
    indent = int(assignment.col_offset)

    required = [
        "lay_danh_sach_tai_khoan_phan_trang(",
        "keyword=keyword",
        "page=current_page",
        "page_size=page_size",
    ]

    for marker in required:
        if marker not in call_text:
            raise RuntimeError(
                f"Lời gọi helper khác dự kiến; thiếu: {marker}"
            )

    call_text = call_text.replace(
        "keyword=keyword",
        'keyword="" if teacher_name_keyword else keyword',
        1,
    )
    call_text = call_text.replace(
        "page=current_page",
        "page=1 if teacher_name_keyword else current_page",
        1,
    )
    call_text = call_text.replace(
        "page_size=page_size",
        "page_size=100000 if teacher_name_keyword else page_size",
        1,
    )

    filter_code = f"""
{MARK_FILTER_START}
if teacher_name_keyword:
    accounts = [
        account
        for account in accounts
        if teacher_name_keyword
        in str(account.full_name or "").casefold()
    ]

    total_accounts = len(accounts)
    total_pages = max(
        1,
        (total_accounts + page_size - 1) // page_size,
    )
    current_page = min(
        max(1, current_page),
        total_pages,
    )

    start_index = (current_page - 1) * page_size
    end_index = start_index + page_size
    accounts = accounts[start_index:end_index]
{MARK_FILTER_END}
""".strip()

    replacement = (
        call_text
        + "\n"
        + indent_block(filter_code, indent)
        + "\n"
    )

    lines[start:end] = [replacement]
    return "".join(lines), removed


def find_templates() -> list[Path]:
    found = []

    for path in TEMPLATES.rglob("*.html"):
        try:
            text = read_text(path)
        except Exception:
            continue

        if 'name="q"' not in text:
            continue

        if (
            "Tìm tài khoản hoặc đơn vị" in text
            or "Quản lý giáo viên" in text
            or "Giáo viên của trường" in text
            or "/tai-khoan" in text
        ):
            found.append(path)

    if not found:
        raise RuntimeError(
            "Không tìm thấy template quản lý tài khoản có input name=q."
        )

    return found


def patch_template(text: str) -> str:
    old_pairs = [
        (
            "<!-- === BAI_13B_11_11_2_TEACHER_SEARCH_UI_START === -->",
            "<!-- === BAI_13B_11_11_2_TEACHER_SEARCH_UI_END === -->",
        ),
        (
            "<!-- === BAI_13B_11_11_2_3_TEACHER_SEARCH_UI_START === -->",
            "<!-- === BAI_13B_11_11_2_3_TEACHER_SEARCH_UI_END === -->",
        ),
    ]

    for start_marker, end_marker in old_pairs:
        pattern = re.compile(
            re.escape(start_marker) + r".*?" + re.escape(end_marker),
            flags=re.DOTALL,
        )
        text = pattern.sub("", text)

    if UI_START not in text:
        text = text.rstrip() + "\n\n" + UI_BLOCK + "\n"

    return text


def verify_backend() -> None:
    text = read_text(ROUTER)

    required = [
        MARK_PREP_START,
        MARK_PREP_END,
        MARK_FILTER_START,
        MARK_FILTER_END,
        'keyword="" if teacher_name_keyword else keyword',
        'str(account.full_name or "").casefold()',
    ]

    for marker in required:
        if marker not in text:
            raise RuntimeError(
                f"Source sau cài thiếu: {marker}"
            )

    if OLD_BLOCK_START in text:
        raise RuntimeError(
            "Block lỗi school_statement vẫn còn trong users.py."
        )

    if "teacher_name_condition" in text and "school_statement = school_statement.where" in text:
        raise RuntimeError(
            "Vẫn còn cấu trúc lỗi dùng school_statement cho tìm giáo viên."
        )

    ast.parse(text)

    result = subprocess.run(
        [sys.executable, "-m", "py_compile", str(ROUTER)],
        cwd=PROJECT,
        text=True,
        capture_output=True,
    )

    if result.stdout:
        print(result.stdout.rstrip())

    if result.stderr:
        print(result.stderr.rstrip())

    if result.returncode != 0:
        raise RuntimeError("py_compile users.py không đạt.")


def verify_templates(paths: list[Path]) -> None:
    from jinja2 import Environment

    for path in paths:
        text = read_text(path)

        if UI_START not in text:
            raise RuntimeError(
                f"Template chưa có UI 13B-11.11.2.4: {path}"
            )

        Environment().parse(text)


def main() -> int:
    print("=" * 120)
    print(
        "BÀI 13B-11.11.2.4 - GỠ LỖI SCHOOL_STATEMENT "
        "VÀ TÌM GIÁO VIÊN CHỈ THEO HỌ TÊN"
    )
    print("=" * 120)
    print()
    print("BẢN NÀY:")
    print(" - Gỡ hoàn toàn block lỗi cũ.")
    print(" - Không sử dụng school_statement cho tìm giáo viên.")
    print(" - Giữ helper phân quyền/phạm vi hiện có.")
    print(" - muc=giao_vien: chỉ lọc account.full_name.")
    print(" - Dùng casefold Unicode: HOA/thường đều tìm được.")
    print(" - Áp dụng MN, Tiểu học, THCS.")
    print(" - Không sửa database.")
    print()

    if not ROUTER.exists():
        raise RuntimeError(f"Không tìm thấy: {ROUTER}")

    templates = find_templates()

    BACKUP.mkdir(parents=True, exist_ok=False)
    backup_file(ROUTER)

    for path in templates:
        backup_file(path)

    print("Backup source:", BACKUP)

    try:
        before = read_text(ROUTER)
        after, removed = patch_backend(before)
        write_text(ROUTER, after)

        for path in templates:
            write_text(path, patch_template(read_text(path)))

        verify_backend()
        verify_templates(templates)
        clear_cache()

        print()
        print("KIỂM TRA SAU CÀI:")
        print(f" - Block thử nghiệm cũ đã gỡ: {removed}")
        print(" - Không còn lỗi school_statement: OK")
        print(" - Chỉ lọc full_name khi muc=giao_vien: OK")
        print(" - Python py_compile: OK")
        print(" - Jinja parse: OK")
        print(" - Database: KHÔNG THAY ĐỔI")
        print()
        print(
            "CÀI ĐẶT BÀI 13B-11.11.2.4 THÀNH CÔNG"
        )
        return 0

    except Exception:
        traceback.print_exc()
        print()
        print("CÓ LỖI - ĐANG KHÔI PHỤC SOURCE...")

        restore_file(ROUTER)

        for path in templates:
            restore_file(path)

        clear_cache()

        print("ĐÃ KHÔI PHỤC SOURCE.")
        print("Database không bị thay đổi.")
        print("Backup:", BACKUP)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
