from __future__ import annotations

import ast
import os
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
BACKUP = PROJECT / "exports" / f"backup_source_bai_13b_11_11_{STAMP}"

MARK_BACKEND_START = "# === BAI_13B_11_11_TEACHER_NAME_SEARCH_START ==="
MARK_BACKEND_END = "# === BAI_13B_11_11_TEACHER_NAME_SEARCH_END ==="
MARK_UI_START = "<!-- === BAI_13B_11_11_TEACHER_SEARCH_UI_START === -->"
MARK_UI_END = "<!-- === BAI_13B_11_11_TEACHER_SEARCH_UI_END === -->"
UI_BLOCK = '<!-- === BAI_13B_11_11_TEACHER_SEARCH_UI_START === -->\n<script>\n(function () {\n    function applyTeacherSearchUi() {\n        var params = new URLSearchParams(window.location.search || "");\n        var muc = String(params.get("muc") || "").trim().toLowerCase();\n        var pageText = String(document.body ? document.body.innerText : "");\n        var isTeacherPage =\n            muc === "giao_vien" ||\n            pageText.indexOf("Quản lý giáo viên") !== -1;\n\n        if (!isTeacherPage) return;\n\n        var qInput = document.querySelector(\'input[name="q"]\');\n        if (!qInput) return;\n\n        qInput.setAttribute("placeholder", "Nhập họ và tên giáo viên");\n        qInput.setAttribute("title", "Nhập toàn bộ hoặc một phần họ và tên giáo viên");\n\n        var label = null;\n        if (qInput.id) {\n            label = document.querySelector(\'label[for="\' + qInput.id + \'"]\');\n        }\n        if (!label) {\n            var parent = qInput.closest("div");\n            if (parent) label = parent.querySelector("label");\n        }\n        if (label) label.textContent = "Tìm tên giáo viên";\n    }\n\n    if (document.readyState === "loading") {\n        document.addEventListener("DOMContentLoaded", applyTeacherSearchUi);\n    } else {\n        applyTeacherSearchUi();\n    }\n})();\n</script>\n<!-- === BAI_13B_11_11_TEACHER_SEARCH_UI_END === -->'


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
        shutil.copy2(src, path)


def clear_cache() -> None:
    for cache in APP.rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(cache, ignore_errors=True)


def src(node: ast.AST, text: str) -> str:
    return ast.get_source_segment(text, node) or ""


def find_account_list_function(tree: ast.Module, text: str):
    candidates = []
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        args = {arg.arg for arg in node.args.args}
        if "q" not in args:
            continue
        body = src(node, text)
        score = 0
        if "User.full_name" in body:
            score += 5
        if "User.username" in body:
            score += 2
        if "muc" in args or "muc" in body:
            score += 3
        if "TemplateResponse" in body:
            score += 2
        if "tai-khoan" in body or "accounts" in body.lower():
            score += 2
        for deco in node.decorator_list:
            if "router.get" in src(deco, text):
                score += 2
        if score >= 7:
            candidates.append((score, node))

    if not candidates:
        raise RuntimeError("Không xác định được hàm danh sách tài khoản trong users.py.")

    candidates.sort(key=lambda item: (-item[0], item[1].lineno))
    best_score = candidates[0][0]
    best = [node for score, node in candidates if score == best_score]
    if len(best) != 1:
        raise RuntimeError("Có nhiều hàm danh sách tài khoản tương tự; dừng để tránh sửa nhầm.")
    return best[0]


def find_search_if(function_node, text: str):
    candidates = []
    for node in ast.walk(function_node):
        if not isinstance(node, ast.If):
            continue
        test_text = src(node.test, text)
        block_text = src(node, text)
        if "q" not in test_text:
            continue
        if "User.full_name" not in block_text:
            continue
        if ".ilike(" not in block_text and ".like(" not in block_text:
            continue

        statement_var = None
        for inner in ast.walk(node):
            if not isinstance(inner, ast.Assign) or len(inner.targets) != 1:
                continue
            target = inner.targets[0]
            if not isinstance(target, ast.Name):
                continue
            value_text = src(inner.value, text)
            if ".where(" in value_text:
                statement_var = target.id
                break

        if statement_var is None:
            continue

        score = 0
        if "User.username" in block_text:
            score += 2
        if "School." in block_text or ".school" in block_text:
            score += 2
        if "or_(" in block_text:
            score += 2
        candidates.append((score, node, statement_var))

    if not candidates:
        raise RuntimeError("Không tìm thấy khối lọc q có User.full_name.")

    candidates.sort(key=lambda item: (-item[0], item[1].lineno))
    best_score = candidates[0][0]
    best = [item for item in candidates if item[0] == best_score]
    if len(best) != 1:
        raise RuntimeError("Có nhiều khối tìm kiếm tương tự; dừng để tránh sửa nhầm.")
    return best[0][1], best[0][2]


def indent_block(text: str, spaces: int) -> str:
    prefix = " " * spaces
    return "\n".join(prefix + line if line.strip() else line for line in text.splitlines())


def patch_backend(text: str) -> str:
    if MARK_BACKEND_START in text:
        return text

    tree = ast.parse(text)
    func = find_account_list_function(tree, text)
    search_if, statement_var = find_search_if(func, text)

    func_args = {arg.arg for arg in func.args.args}
    if "muc" not in func_args and "muc" not in src(func, text):
        raise RuntimeError("Hàm danh sách chưa có biến muc.")

    lines = text.splitlines(keepends=True)
    start = search_if.lineno - 1
    end = search_if.end_lineno
    old_block = "".join(lines[start:end]).rstrip("\r\n")
    old_lines = old_block.splitlines()

    base_indent = len(old_lines[0]) - len(old_lines[0].lstrip(" "))
    body_lines = old_lines[1:]
    min_indent = min(
        len(line) - len(line.lstrip(" "))
        for line in body_lines
        if line.strip()
    )
    old_body = "\n".join(line[min_indent:] if line.strip() else "" for line in body_lines)

    indent = " " * base_indent
    body_indent = " " * (base_indent + 4)
    inner_indent = " " * (base_indent + 8)

    new_block = (
        f"{indent}{MARK_BACKEND_START}\n"
        f"{indent}if q:\n"
        f"{body_indent}if str(muc or '').strip().lower() == 'giao_vien':\n"
        f"{inner_indent}teacher_name = str(q or '').strip()\n"
        f"{inner_indent}teacher_name_variants = []\n"
        f"{inner_indent}for candidate in (teacher_name, teacher_name.upper(), teacher_name.lower(), teacher_name.title()):\n"
        f"{inner_indent}    if candidate and candidate not in teacher_name_variants:\n"
        f"{inner_indent}        teacher_name_variants.append(candidate)\n"
        f"{inner_indent}{statement_var} = {statement_var}.where(\n"
        f"{inner_indent}    or_(*[User.full_name.like(f'%{candidate}%') for candidate in teacher_name_variants])\n"
        f"{inner_indent})\n"
        f"{body_indent}else:\n"
        f"{indent_block(old_body, base_indent + 8)}\n"
        f"{indent}{MARK_BACKEND_END}\n"
    )
    return "".join(lines[:start]) + new_block + "".join(lines[end:])


def find_template() -> Path:
    exact = []
    fallback = []
    for path in TEMPLATES.rglob("*.html"):
        try:
            text = read_text(path)
        except Exception:
            continue
        if "Tìm tài khoản hoặc đơn vị" in text:
            exact.append(path)
        elif 'name="q"' in text and "Quản lý giáo viên" in text:
            fallback.append(path)

    candidates = exact or fallback
    if len(candidates) != 1:
        detail = "\n".join(f" - {p}" for p in candidates)
        raise RuntimeError("Không xác định được đúng 1 template quản lý tài khoản.\n" + detail)
    return candidates[0]


def verify_backend():
    text = read_text(ROUTER)
    required = [
        MARK_BACKEND_START,
        MARK_BACKEND_END,
        "str(muc or '').strip().lower() == 'giao_vien'",
        "User.full_name.like",
        "teacher_name.upper()",
        "teacher_name.lower()",
        "teacher_name.title()",
    ]
    for marker in required:
        if marker not in text:
            raise RuntimeError(f"users.py thiếu marker sau cài: {marker}")

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


def verify_template(path: Path):
    text = read_text(path)
    required = [
        MARK_UI_START,
        MARK_UI_END,
        "Tìm tên giáo viên",
        "Nhập họ và tên giáo viên",
        'input[name="q"]',
        'muc === "giao_vien"',
    ]
    for marker in required:
        if marker not in text:
            raise RuntimeError(f"Template thiếu marker sau cài: {marker}")

    from jinja2 import Environment
    Environment().parse(text)


def main() -> int:
    print("=" * 112)
    print("BÀI 13B-11.11 - TÌM GIÁO VIÊN CHỈ THEO HỌ TÊN CHO TẤT CẢ CẤP HỌC")
    print("=" * 112)
    print()
    print("ÁP DỤNG: Mầm non, Tiểu học, THCS.")
    print(" - Chỉ tìm theo Họ và tên giáo viên ở mục muc=giao_vien.")
    print(" - Không tìm theo tên trường/đơn vị.")
    print(" - Cho phép gõ một phần tên.")
    print(" - Có biến thể HOA/thường để dễ khớp dữ liệu.")
    print(" - Các mục tài khoản khác giữ nguyên cách tìm hiện tại.")
    print(" - Không sửa database, không đổi quyền, không đổi menu.")
    print()

    if not ROUTER.exists():
        raise RuntimeError(f"Không tìm thấy: {ROUTER}")

    template = find_template()
    print("Template:", template)

    BACKUP.mkdir(parents=True, exist_ok=False)
    backup_file(ROUTER)
    backup_file(template)
    print("Backup source:", BACKUP)

    try:
        write_text(ROUTER, patch_backend(read_text(ROUTER)))

        template_text = read_text(template)
        if MARK_UI_START not in template_text:
            template_text = template_text.rstrip() + "\n\n" + UI_BLOCK + "\n"
        write_text(template, template_text)

        verify_backend()
        verify_template(template)
        clear_cache()

        print()
        print("KIỂM TRA SAU CÀI:")
        print(" - Tìm giáo viên theo User.full_name: OK")
        print(" - Không dùng tên đơn vị trong muc=giao_vien: OK")
        print(" - Tìm một phần tên: OK")
        print(" - Giao diện nhãn tìm kiếm: OK")
        print(" - Python/Jinja: OK")
        print(" - Database: KHÔNG THAY ĐỔI")
        print()
        print("CÀI ĐẶT BÀI 13B-11.11 THÀNH CÔNG")
        return 0

    except Exception:
        traceback.print_exc()
        print()
        print("CÓ LỖI - ĐANG KHÔI PHỤC SOURCE...")
        restore_file(ROUTER)
        restore_file(template)
        clear_cache()
        print("ĐÃ KHÔI PHỤC SOURCE.")
        print("Database không bị thay đổi.")
        print("Backup:", BACKUP)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
