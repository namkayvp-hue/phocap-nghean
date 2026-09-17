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
BACKUP = PROJECT / "exports" / f"backup_source_bai_13b_11_11_2_3_{STAMP}"

OLD_BACKEND_START = "# === BAI_13B_11_11_2_TEACHER_NAME_ONLY_START ==="
OLD_BACKEND_END = "# === BAI_13B_11_11_2_TEACHER_NAME_ONLY_END ==="

NEW_KEYWORD_START = "# === BAI_13B_11_11_2_3_TEACHER_KEYWORD_START ==="
NEW_KEYWORD_END = "# === BAI_13B_11_11_2_3_TEACHER_KEYWORD_END ==="

NEW_FILTER_START = "# === BAI_13B_11_11_2_3_TEACHER_FILTER_START ==="
NEW_FILTER_END = "# === BAI_13B_11_11_2_3_TEACHER_FILTER_END ==="

OLD_UI_START = "<!-- === BAI_13B_11_11_2_TEACHER_SEARCH_UI_START === -->"
OLD_UI_END = "<!-- === BAI_13B_11_11_2_TEACHER_SEARCH_UI_END === -->"

NEW_UI_START = "<!-- === BAI_13B_11_11_2_3_TEACHER_SEARCH_UI_START === -->"
NEW_UI_END = "<!-- === BAI_13B_11_11_2_3_TEACHER_SEARCH_UI_END === -->"

UI_BLOCK = '<!-- === BAI_13B_11_11_2_3_TEACHER_SEARCH_UI_START === -->\n<script>\n(function () {\n    function applyTeacherNameSearchUi() {\n        var params = new URLSearchParams(window.location.search || "");\n        var muc = String(params.get("muc") || "").trim().toLowerCase();\n\n        if (muc !== "giao_vien") return;\n\n        var input = document.querySelector(\'input[name="q"]\');\n        if (!input) return;\n\n        input.setAttribute("placeholder", "Nhập họ và tên giáo viên");\n        input.setAttribute(\n            "title",\n            "Chỉ tìm theo toàn bộ hoặc một phần họ và tên giáo viên"\n        );\n\n        var label = null;\n\n        if (input.id) {\n            label = document.querySelector(\n                \'label[for="\' + input.id + \'"]\'\n            );\n        }\n\n        if (!label && input.parentElement) {\n            label = input.parentElement.querySelector("label");\n        }\n\n        if (label) {\n            label.textContent = "Tìm tên giáo viên";\n        }\n    }\n\n    if (document.readyState === "loading") {\n        document.addEventListener(\n            "DOMContentLoaded",\n            applyTeacherNameSearchUi\n        );\n    } else {\n        applyTeacherNameSearchUi();\n    }\n})();\n</script>\n<!-- === BAI_13B_11_11_2_3_TEACHER_SEARCH_UI_END === -->'


def read_text(path: Path) -> str:
    if not path.exists():
        raise RuntimeError(f"Không tìm thấy tệp: {path}")
    return path.read_text(encoding="utf-8-sig")


def write_text(path: Path, value: str) -> None:
    path.write_text(value, encoding="utf-8")


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


def remove_python_block(text: str) -> tuple[str, int]:
    removed = 0

    while OLD_BACKEND_START in text:
        start = text.find(OLD_BACKEND_START)
        end = text.find(OLD_BACKEND_END, start)

        if end < 0:
            raise RuntimeError(
                "Tìm thấy marker đầu 13B-11.11.2 nhưng thiếu marker cuối."
            )

        end += len(OLD_BACKEND_END)
        line_start = text.rfind("\n", 0, start) + 1
        line_end = text.find("\n", end)

        if line_end < 0:
            line_end = len(text)
        else:
            line_end += 1

        text = text[:line_start] + text[line_end:]
        removed += 1

    return text, removed


def find_function(text: str):
    tree = ast.parse(text)
    found = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "danh_sach_tai_khoan"
    ]

    if len(found) != 1:
        raise RuntimeError(
            f"Phải có đúng 1 hàm danh_sach_tai_khoan, hiện có {len(found)}."
        )

    return found[0]


def find_account_helper_assign(text: str, func):
    matches = []

    for node in ast.walk(func):
        if not isinstance(node, ast.Assign):
            continue

        call = node.value
        if not isinstance(call, ast.Call):
            continue

        func_name = ""
        if isinstance(call.func, ast.Name):
            func_name = call.func.id
        elif isinstance(call.func, ast.Attribute):
            func_name = call.func.attr

        if func_name == "lay_danh_sach_tai_khoan_phan_trang":
            matches.append(node)

    if len(matches) != 1:
        raise RuntimeError(
            "Phải tìm thấy đúng 1 lời gọi "
            "lay_danh_sach_tai_khoan_phan_trang trong danh_sach_tai_khoan, "
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
    text, removed_old = remove_python_block(text)

    if NEW_KEYWORD_START in text and NEW_FILTER_START in text:
        print(" - Bài 13B-11.11.2.3 đã có sẵn, không sửa lặp.")
        return text, removed_old

    old_keyword = '    keyword = " ".join(q.strip().split())\n'
    new_keyword = (
        '    keyword = " ".join(q.strip().split())\n'
        f'    {NEW_KEYWORD_START}\n'
        '    teacher_name_keyword = (\n'
        '        keyword.casefold()\n'
        '        if section == "giao_vien" and keyword\n'
        '        else ""\n'
        '    )\n'
        f'    {NEW_KEYWORD_END}\n'
    )

    if old_keyword not in text:
        raise RuntimeError(
            "Không tìm thấy đúng dòng tạo keyword trong danh_sach_tai_khoan."
        )

    text = text.replace(old_keyword, new_keyword, 1)

    func = find_function(text)
    assignment = find_account_helper_assign(text, func)

    lines = text.splitlines(keepends=True)
    start = assignment.lineno - 1
    end = assignment.end_lineno

    old_call = "".join(lines[start:end]).rstrip("\r\n")
    indent = int(assignment.col_offset)

    for marker in (
        "lay_danh_sach_tai_khoan_phan_trang(",
        "keyword=keyword",
        "page=current_page",
        "page_size=page_size",
    ):
        if marker not in old_call:
            raise RuntimeError(
                f"Lời gọi helper khác dự kiến, thiếu: {marker}"
            )

    new_call = old_call.replace(
        "keyword=keyword",
        'keyword="" if teacher_name_keyword else keyword',
        1,
    ).replace(
        "page=current_page",
        "page=1 if teacher_name_keyword else current_page",
        1,
    ).replace(
        "page_size=page_size",
        "page_size=100000 if teacher_name_keyword else page_size",
        1,
    )

    filter_body = f"""
{NEW_FILTER_START}
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
{NEW_FILTER_END}
""".strip("\n")

    replacement = (
        new_call
        + "\n"
        + indent_block(filter_body, indent)
        + "\n"
    )

    lines[start:end] = [replacement]
    return "".join(lines), removed_old


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
    if OLD_UI_START in text:
        pattern = re.compile(
            re.escape(OLD_UI_START)
            + r".*?"
            + re.escape(OLD_UI_END),
            flags=re.DOTALL,
        )
        text = pattern.sub("", text)

    if NEW_UI_START not in text:
        text = text.rstrip() + "\n\n" + UI_BLOCK + "\n"

    return text


def verify_backend() -> None:
    text = read_text(ROUTER)

    for marker in (
        NEW_KEYWORD_START,
        NEW_KEYWORD_END,
        NEW_FILTER_START,
        NEW_FILTER_END,
        'keyword="" if teacher_name_keyword else keyword',
        'str(account.full_name or "").casefold()',
    ):
        if marker not in text:
            raise RuntimeError(
                f"Kiểm tra source sau cài thiếu: {marker}"
            )

    if OLD_BACKEND_START in text or OLD_BACKEND_END in text:
        raise RuntimeError(
            "Block 13B-11.11.2 lỗi vẫn còn trong users.py."
        )

    if "school_statement = school_statement.where(\n                teacher_name_condition" in text:
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
        raise RuntimeError(
            "py_compile users.py không đạt."
        )


def verify_templates(paths: list[Path]) -> None:
    from jinja2 import Environment

    for path in paths:
        text = read_text(path)

        if NEW_UI_START not in text:
            raise RuntimeError(
                f"Template chưa có UI mới: {path}"
            )

        if "Tìm tên giáo viên" not in text:
            raise RuntimeError(
                f"Template thiếu nhãn Tìm tên giáo viên: {path}"
            )

        Environment().parse(text)


def main() -> int:
    print("=" * 118)
    print(
        "BÀI 13B-11.11.2.3 - SỬA DỨT ĐIỂM LỖI 500 "
        "VÀ TÌM GIÁO VIÊN CHỈ THEO HỌ TÊN"
    )
    print("=" * 118)
    print()
    print("SOURCE THỰC TẾ ĐÃ XÁC ĐỊNH:")
    print(" - school_statement chỉ được tạo trong nhánh ADMIN.")
    print(" - Block cũ nằm ngoài nhánh ADMIN nên tài khoản Trường bị 500.")
    print()
    print("CÁCH SỬA:")
    print(" - Gỡ hoàn toàn block lỗi liên quan school_statement.")
    print(" - Không can thiệp school_statement nữa.")
    print(" - Giữ nguyên helper phân quyền/phạm vi hiện có.")
    print(" - Khi muc=giao_vien có q, helper lấy tài khoản đúng phạm vi")
    print("   nhưng không dùng bộ lọc từ khóa rộng.")
    print(" - Sau đó lọc CHỈ User.full_name bằng Python casefold Unicode.")
    print(" - 'CAO THỊ THƠ' và 'Cao Thị Thơ' sẽ khớp nhau.")
    print(" - Gõ tên trường/đơn vị sẽ không tạo kết quả nếu không nằm trong họ tên.")
    print()
    print("ÁP DỤNG: Mầm non, Tiểu học, THCS.")
    print("KHÔNG sửa database, quyền, menu.")
    print()

    if not ROUTER.exists():
        raise RuntimeError(
            f"Không tìm thấy: {ROUTER}"
        )

    templates = find_templates()

    BACKUP.mkdir(parents=True, exist_ok=False)
    backup_file(ROUTER)

    for path in templates:
        backup_file(path)

    print("Backup source:", BACKUP)

    try:
        before = read_text(ROUTER)
        after, removed_old = patch_backend(before)
        write_text(ROUTER, after)

        for path in templates:
            write_text(
                path,
                patch_template(read_text(path)),
            )

        verify_backend()
        verify_templates(templates)
        clear_cache()

        print()
        print("KIỂM TRA SAU CÀI:")
        print(f" - Block lỗi cũ đã gỡ: {removed_old}")
        print(" - Không còn dùng school_statement cho tìm giáo viên: OK")
        print(" - Tìm chỉ theo full_name + casefold Unicode: OK")
        print(" - Phân trang kết quả tìm tên: OK")
        print(" - py_compile users.py: OK")
        print(" - Jinja parse: OK")
        print(" - Database: KHÔNG THAY ĐỔI")
        print()
        print(
            "CÀI ĐẶT BÀI 13B-11.11.2.3 THÀNH CÔNG"
        )

        return 0

    except Exception:
        traceback.print_exc()

        print()
        print(
            "CÓ LỖI - ĐANG KHÔI PHỤC SOURCE..."
        )

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
