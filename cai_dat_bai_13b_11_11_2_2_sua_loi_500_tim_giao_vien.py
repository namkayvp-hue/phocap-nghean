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
BACKUP = PROJECT / "exports" / f"backup_source_bai_13b_11_11_2_2_{STAMP}"

OLD_BACKEND_START = "# === BAI_13B_11_11_2_TEACHER_NAME_ONLY_START ==="
OLD_BACKEND_END = "# === BAI_13B_11_11_2_TEACHER_NAME_ONLY_END ==="

NEW_BACKEND_START = "# === BAI_13B_11_11_2_2_TEACHER_NAME_ONLY_START ==="
NEW_BACKEND_END = "# === BAI_13B_11_11_2_2_TEACHER_NAME_ONLY_END ==="

OLD_UI_START = "<!-- === BAI_13B_11_11_2_TEACHER_SEARCH_UI_START === -->"
OLD_UI_END = "<!-- === BAI_13B_11_11_2_TEACHER_SEARCH_UI_END === -->"

NEW_UI_START = "<!-- === BAI_13B_11_11_2_2_TEACHER_SEARCH_UI_START === -->"
NEW_UI_END = "<!-- === BAI_13B_11_11_2_2_TEACHER_SEARCH_UI_END === -->"

UI_BLOCK = '<!-- === BAI_13B_11_11_2_2_TEACHER_SEARCH_UI_START === -->\n<script>\n(function () {\n    function applyTeacherNameSearchUi() {\n        var params = new URLSearchParams(window.location.search || "");\n        var muc = String(params.get("muc") || "").trim().toLowerCase();\n        if (muc !== "giao_vien") return;\n\n        var input = document.querySelector(\'input[name="q"]\');\n        if (!input) return;\n\n        input.setAttribute("placeholder", "Nhập họ và tên giáo viên");\n        input.setAttribute(\n            "title",\n            "Nhập toàn bộ hoặc một phần họ và tên giáo viên"\n        );\n\n        var label = null;\n        if (input.id) {\n            label = document.querySelector(\'label[for="\' + input.id + \'"]\');\n        }\n        if (!label && input.parentElement) {\n            label = input.parentElement.querySelector("label");\n        }\n        if (label) {\n            label.textContent = "Tìm tên giáo viên";\n        }\n    }\n\n    if (document.readyState === "loading") {\n        document.addEventListener(\n            "DOMContentLoaded",\n            applyTeacherNameSearchUi\n        );\n    } else {\n        applyTeacherNameSearchUi();\n    }\n})();\n</script>\n<!-- === BAI_13B_11_11_2_2_TEACHER_SEARCH_UI_END === -->'


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


def remove_python_marker_blocks(text: str) -> tuple[str, int]:
    removed = 0
    while OLD_BACKEND_START in text:
        start = text.find(OLD_BACKEND_START)
        end = text.find(OLD_BACKEND_END, start)
        if end < 0:
            raise RuntimeError("Thiếu marker cuối của block 13B-11.11.2 cũ.")
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


def source_segment(text: str, node: ast.AST) -> str:
    return ast.get_source_segment(text, node) or ""


def find_account_function(text: str):
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


def find_user_query_assignments(text: str, func):
    results = []

    for node in ast.walk(func):
        if not isinstance(node, ast.Assign):
            continue
        if len(node.targets) != 1:
            continue

        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue

        var_name = target.id
        value_text = source_segment(text, node.value)

        if "select(User)" not in value_text:
            continue

        if (
            "statement" not in var_name.lower()
            and "query" not in var_name.lower()
        ):
            continue

        results.append((node, var_name))

    unique = {}
    for node, var_name in results:
        unique[(node.lineno, node.end_lineno, var_name)] = (node, var_name)

    final = list(unique.values())
    final.sort(key=lambda item: item[0].lineno)

    if not final:
        raise RuntimeError(
            "Không tìm thấy câu khởi tạo select(User) trong danh_sach_tai_khoan."
        )

    return final


def make_name_filter(indent: int, statement_var: str) -> str:
    i0 = " " * indent
    i1 = " " * (indent + 4)
    i2 = " " * (indent + 8)
    i3 = " " * (indent + 12)
    i4 = " " * (indent + 16)

    return (
        f"{i0}{NEW_BACKEND_START}\n"
        f"{i0}if (\n"
        f"{i1}str(muc or '').strip().lower() == 'giao_vien'\n"
        f"{i1}and str(q or '').strip()\n"
        f"{i0}):\n"
        f"{i1}teacher_name = str(q or '').strip()\n"
        f"{i1}teacher_name_variants = []\n"
        f"{i1}for candidate in (\n"
        f"{i2}teacher_name,\n"
        f"{i2}teacher_name.upper(),\n"
        f"{i2}teacher_name.lower(),\n"
        f"{i2}teacher_name.title(),\n"
        f"{i1}):\n"
        f"{i2}if candidate and candidate not in teacher_name_variants:\n"
        f"{i3}teacher_name_variants.append(candidate)\n"
        f"{i1}teacher_name_condition = None\n"
        f"{i1}for candidate in teacher_name_variants:\n"
        f"{i2}current_condition = User.full_name.like(f'%{candidate}%')\n"
        f"{i2}if teacher_name_condition is None:\n"
        f"{i3}teacher_name_condition = current_condition\n"
        f"{i2}else:\n"
        f"{i3}teacher_name_condition = (\n"
        f"{i4}teacher_name_condition | current_condition\n"
        f"{i3})\n"
        f"{i1}if teacher_name_condition is not None:\n"
        f"{i2}{statement_var} = {statement_var}.where(\n"
        f"{i3}teacher_name_condition\n"
        f"{i2})\n"
        f"{i0}{NEW_BACKEND_END}\n"
    )


def patch_backend(text: str) -> tuple[str, int, int]:
    text, removed_old = remove_python_marker_blocks(text)

    if NEW_BACKEND_START in text:
        return text, removed_old, 0

    func = find_account_function(text)
    assignments = find_user_query_assignments(text, func)

    lines = text.splitlines(keepends=True)
    insertions = []

    print("Các query User sẽ được gắn bộ lọc tên:")
    for node, var_name in assignments:
        indent = int(node.col_offset)
        print(
            f" - dòng {node.lineno}: {var_name} "
            f"(indent={indent})"
        )
        insertions.append(
            (
                node.end_lineno,
                make_name_filter(indent, var_name),
            )
        )

    insertions.sort(key=lambda item: item[0], reverse=True)

    for end_lineno, block in insertions:
        lines[end_lineno:end_lineno] = [block]

    return "".join(lines), removed_old, len(insertions)


def find_related_templates() -> list[Path]:
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


def verify_backend() -> int:
    text = read_text(ROUTER)

    if OLD_BACKEND_START in text:
        raise RuntimeError("Block backend lỗi 13B-11.11.2 vẫn còn.")

    if NEW_BACKEND_START not in text:
        raise RuntimeError("Chưa có block backend 13B-11.11.2.2.")

    if "User.full_name.like" not in text:
        raise RuntimeError("Chưa có lọc theo User.full_name.")

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

    return text.count(NEW_BACKEND_START)


def verify_templates(paths: list[Path]) -> None:
    from jinja2 import Environment

    for path in paths:
        text = read_text(path)

        if NEW_UI_START not in text:
            raise RuntimeError(f"Template chưa có UI mới: {path}")

        if "Tìm tên giáo viên" not in text:
            raise RuntimeError(f"Template thiếu nhãn mới: {path}")

        Environment().parse(text)


def main() -> int:
    print("=" * 116)
    print(
        "BÀI 13B-11.11.2.2 - SỬA LỖI 500 VÀ "
        "TÌM GIÁO VIÊN CHỈ THEO HỌ TÊN"
    )
    print("=" * 116)
    print()
    print("LỖI ĐÃ XÁC ĐỊNH:")
    print(
        " - school_statement bị dùng trước khi được khởi tạo."
    )
    print(
        " - Block cũ được chèn sai nhánh/thụt lề."
    )
    print()
    print("BẢN SỬA:")
    print(
        " - Gỡ toàn bộ block backend 13B-11.11.2 cũ."
    )
    print(
        " - Chỉ làm việc trong hàm danh_sach_tai_khoan."
    )
    print(
        " - Chèn bộ lọc tên ngay SAU từng select(User)."
    )
    print(
        " - Giữ đúng mức thụt lề của chính query đó."
    )
    print(
        " - muc=giao_vien: kết quả bắt buộc khớp User.full_name."
    )
    print()
    print("AN TOÀN:")
    print(" - Backup source trước khi sửa.")
    print(" - py_compile users.py.")
    print(" - Kiểm tra Jinja.")
    print(" - Không sửa database.")
    print()

    if not ROUTER.exists():
        raise RuntimeError(f"Không tìm thấy: {ROUTER}")

    templates = find_related_templates()

    BACKUP.mkdir(parents=True, exist_ok=False)
    backup_file(ROUTER)

    for path in templates:
        backup_file(path)

    print("Backup source:", BACKUP)

    try:
        before = read_text(ROUTER)
        after, removed_old, inserted = patch_backend(before)
        write_text(ROUTER, after)

        for path in templates:
            write_text(path, patch_template(read_text(path)))

        block_count = verify_backend()
        verify_templates(templates)
        clear_cache()

        print()
        print("KIỂM TRA SAU CÀI:")
        print(f" - Block lỗi cũ đã gỡ: {removed_old}")
        print(f" - Block mới đã chèn: {inserted}")
        print(f" - Tổng block mới trong source: {block_count}")
        print(" - py_compile: OK")
        print(" - Jinja parse: OK")
        print(" - Database: KHÔNG THAY ĐỔI")
        print()
        print(
            "CÀI ĐẶT BÀI 13B-11.11.2.2 THÀNH CÔNG"
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
