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
BACKUP = PROJECT / "exports" / f"backup_source_bai_13b_11_11_1_{STAMP}"

MARK_BACKEND = "BAI_13B_11_11_1_TEACHER_NAME_SEARCH"
MARK_UI_START = "<!-- === BAI_13B_11_11_1_TEACHER_SEARCH_UI_START === -->"
MARK_UI_END = "<!-- === BAI_13B_11_11_1_TEACHER_SEARCH_UI_END === -->"
UI_BLOCK = '<!-- === BAI_13B_11_11_1_TEACHER_SEARCH_UI_START === -->\n<script>\n(function () {\n    function applyTeacherSearchUi() {\n        var params = new URLSearchParams(window.location.search || "");\n        var muc = String(params.get("muc") || "").trim().toLowerCase();\n\n        if (muc !== "giao_vien") {\n            return;\n        }\n\n        var qInput = document.querySelector(\'input[name="q"]\');\n        if (!qInput) {\n            return;\n        }\n\n        qInput.setAttribute("placeholder", "Nhập họ và tên giáo viên");\n        qInput.setAttribute(\n            "title",\n            "Nhập toàn bộ hoặc một phần họ và tên giáo viên"\n        );\n\n        var label = null;\n\n        if (qInput.id) {\n            label = document.querySelector(\n                \'label[for="\' + qInput.id + \'"]\'\n            );\n        }\n\n        if (!label) {\n            var container = qInput.parentElement;\n            if (container) {\n                label = container.querySelector("label");\n            }\n        }\n\n        if (label) {\n            label.textContent = "Tìm tên giáo viên";\n        }\n    }\n\n    if (document.readyState === "loading") {\n        document.addEventListener(\n            "DOMContentLoaded",\n            applyTeacherSearchUi\n        );\n    } else {\n        applyTeacherSearchUi();\n    }\n})();\n</script>\n<!-- === BAI_13B_11_11_1_TEACHER_SEARCH_UI_END === -->'


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


def source(node: ast.AST, text: str) -> str:
    return ast.get_source_segment(text, node) or ""


def dedent_block(lines: list[str]) -> str:
    nonempty = [line for line in lines if line.strip()]
    if not nonempty:
        return ""
    margin = min(len(line) - len(line.lstrip(" ")) for line in nonempty)
    return "\n".join(line[margin:] if line.strip() else "" for line in lines)


def indent_text(text: str, spaces: int) -> str:
    prefix = " " * spaces
    return "\n".join(prefix + line if line.strip() else line for line in text.splitlines())


def find_patch_targets(text: str):
    tree = ast.parse(text)
    targets = []

    for func in tree.body:
        if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        func_text = source(func, text)
        if "muc" not in func_text:
            continue

        for node in ast.walk(func):
            if not isinstance(node, ast.If):
                continue

            test_text = source(node.test, text)
            block_text = source(node, text)

            if "q" not in test_text:
                continue
            if "User.full_name" not in block_text:
                continue
            if ".where(" not in block_text:
                continue
            if MARK_BACKEND in block_text:
                continue

            statement_var = None
            for inner in ast.walk(node):
                if not isinstance(inner, ast.Assign):
                    continue
                if len(inner.targets) != 1:
                    continue
                target = inner.targets[0]
                if not isinstance(target, ast.Name):
                    continue
                value_text = source(inner.value, text)
                if ".where(" in value_text:
                    statement_var = target.id
                    break

            if statement_var is None:
                continue

            targets.append((node, statement_var, func.name))

    unique = {}
    for node, statement_var, func_name in targets:
        key = (node.lineno, node.end_lineno)
        unique[key] = (node, statement_var, func_name)

    return list(unique.values())


def patch_backend(text: str) -> tuple[str, int]:
    if MARK_BACKEND in text:
        return text, 0

    targets = find_patch_targets(text)
    if not targets:
        raise RuntimeError(
            "Không tìm thấy khối tìm kiếm tài khoản giáo viên phù hợp trong users.py."
        )

    lines = text.splitlines(keepends=True)
    replacements = []

    for node, statement_var, func_name in targets:
        start = node.lineno - 1
        end = node.end_lineno

        old_block = "".join(lines[start:end]).rstrip("\r\n")
        old_lines = old_block.splitlines()
        if len(old_lines) < 2:
            continue

        base_indent = len(old_lines[0]) - len(old_lines[0].lstrip(" "))
        old_body = dedent_block(old_lines[1:])

        indent = " " * base_indent
        i1 = " " * (base_indent + 4)
        i2 = " " * (base_indent + 8)
        i3 = " " * (base_indent + 12)
        i4 = " " * (base_indent + 16)

        new_block = (
            f"{indent}# === {MARK_BACKEND}_START ===\n"
            f"{indent}if q:\n"
            f"{i1}if str(muc or '').strip().lower() == 'giao_vien':\n"
            f"{i2}teacher_name = str(q or '').strip()\n"
            f"{i2}teacher_name_variants = []\n"
            f"{i2}for candidate in (\n"
            f"{i3}teacher_name,\n"
            f"{i3}teacher_name.upper(),\n"
            f"{i3}teacher_name.lower(),\n"
            f"{i3}teacher_name.title(),\n"
            f"{i2}):\n"
            f"{i3}if candidate and candidate not in teacher_name_variants:\n"
            f"{i4}teacher_name_variants.append(candidate)\n"
            f"{i2}{statement_var} = {statement_var}.where(\n"
            f"{i3}or_(\n"
            f"{i4}*[\n"
            f"{i4}    User.full_name.like(f'%{candidate}%')\n"
            f"{i4}    for candidate in teacher_name_variants\n"
            f"{i4}]\n"
            f"{i3})\n"
            f"{i2})\n"
            f"{i1}else:\n"
            f"{indent_text(old_body, base_indent + 8)}\n"
            f"{indent}# === {MARK_BACKEND}_END ===\n"
        )

        replacements.append((start, end, new_block, func_name))

    if not replacements:
        raise RuntimeError("Không tạo được khối sửa nào.")

    replacements.sort(key=lambda item: item[0], reverse=True)

    for start, end, new_block, func_name in replacements:
        lines[start:end] = [new_block]

    return "".join(lines), len(replacements)


def find_account_templates():
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
        ):
            found.append(path)

    if not found:
        raise RuntimeError(
            "Không tìm thấy template quản lý tài khoản có ô q."
        )

    return found


def patch_templates(paths):
    changed = 0
    for path in paths:
        text = read_text(path)
        if MARK_UI_START in text:
            continue
        text = text.rstrip() + "\n\n" + UI_BLOCK + "\n"
        write_text(path, text)
        changed += 1
    return changed


def verify_backend() -> int:
    text = read_text(ROUTER)

    if MARK_BACKEND not in text:
        raise RuntimeError("users.py chưa có marker Bài 13B-11.11.1.")
    if "User.full_name.like" not in text:
        raise RuntimeError("users.py chưa có tìm theo User.full_name.")
    if "str(muc or '').strip().lower() == 'giao_vien'" not in text:
        raise RuntimeError("users.py chưa giới hạn riêng muc=giao_vien.")

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

    return text.count(f"# === {MARK_BACKEND}_START ===")


def verify_templates(paths):
    from jinja2 import Environment
    for path in paths:
        text = read_text(path)
        if MARK_UI_START not in text:
            raise RuntimeError(f"Template chưa có UI mới: {path}")
        if "Tìm tên giáo viên" not in text:
            raise RuntimeError(f"Template thiếu nhãn mới: {path}")
        Environment().parse(text)


def main() -> int:
    print("=" * 112)
    print(
        "BÀI 13B-11.11.1 - TÌM GIÁO VIÊN CHỈ THEO HỌ TÊN "
        "CHO TẤT CẢ CẤP HỌC"
    )
    print("=" * 112)
    print()
    print("ÁP DỤNG: Mầm non, Tiểu học, THCS.")
    print(" - Chỉ tìm theo Họ và tên giáo viên ở mục muc=giao_vien.")
    print(" - Không tìm theo tên trường/đơn vị.")
    print(" - Có thể nhập một phần họ tên.")
    print(" - Hỗ trợ biến thể chữ HOA/thường.")
    print(" - Các mục tài khoản khác giữ nguyên bộ lọc cũ.")
    print(" - Không sửa database, không đổi quyền, không đổi menu.")
    print()

    if not ROUTER.exists():
        raise RuntimeError(f"Không tìm thấy: {ROUTER}")

    templates = find_account_templates()

    BACKUP.mkdir(parents=True, exist_ok=False)
    backup_file(ROUTER)
    for path in templates:
        backup_file(path)

    print("Backup source:", BACKUP)
    print("Số template liên quan:", len(templates))

    try:
        before = read_text(ROUTER)
        after, patched_count = patch_backend(before)
        write_text(ROUTER, after)

        template_changed = patch_templates(templates)

        backend_blocks = verify_backend()
        verify_templates(templates)
        clear_cache()

        print()
        print("KIỂM TRA SAU CÀI:")
        print(f" - Khối backend đã sửa: {backend_blocks}")
        print(f" - Template đã bổ sung UI: {template_changed}")
        print(" - Chỉ tìm User.full_name khi muc=giao_vien: OK")
        print(" - Các mục khác giữ bộ lọc cũ: OK")
        print(" - Python/Jinja: OK")
        print(" - Database: KHÔNG THAY ĐỔI")
        print()
        print("CÀI ĐẶT BÀI 13B-11.11.1 THÀNH CÔNG")
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
