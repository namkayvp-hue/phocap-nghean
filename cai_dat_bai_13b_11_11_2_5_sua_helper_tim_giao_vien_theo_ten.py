from __future__ import annotations

import ast
import os
import re
import shutil
import subprocess
import sys
import traceback
from collections import Counter
from datetime import datetime
from pathlib import Path

PROJECT = Path(os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")).resolve()
APP = PROJECT / "app"
ROUTER = APP / "routers" / "users.py"
TEMPLATES = APP / "templates"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = PROJECT / "exports" / f"backup_source_bai_13b_11_11_2_5_{STAMP}"

HELPER_NAME = "lay_danh_sach_tai_khoan_phan_trang"

MARK_HELPER_START = "# === BAI_13B_11_11_2_5_NAME_ONLY_START ==="
MARK_HELPER_END = "# === BAI_13B_11_11_2_5_NAME_ONLY_END ==="

UI_START = "<!-- === BAI_13B_11_11_2_5_UI_START === -->"
UI_END = "<!-- === BAI_13B_11_11_2_5_UI_END === -->"
UI_BLOCK = '<!-- === BAI_13B_11_11_2_5_UI_START === -->\n<script>\n(function () {\n    function applyTeacherSearchUi() {\n        var params = new URLSearchParams(window.location.search || "");\n        if (String(params.get("muc") || "").trim().toLowerCase() !== "giao_vien") {\n            return;\n        }\n\n        var input = document.querySelector(\'input[name="q"]\');\n        if (!input) return;\n\n        input.placeholder = "Nhập họ và tên giáo viên";\n        input.title = "Chỉ tìm theo toàn bộ hoặc một phần họ và tên giáo viên";\n\n        var label = null;\n        if (input.id) {\n            label = document.querySelector(\'label[for="\' + input.id + \'"]\');\n        }\n        if (!label && input.parentElement) {\n            label = input.parentElement.querySelector("label");\n        }\n        if (label) {\n            label.textContent = "Tìm tên giáo viên";\n        }\n    }\n\n    if (document.readyState === "loading") {\n        document.addEventListener("DOMContentLoaded", applyTeacherSearchUi);\n    } else {\n        applyTeacherSearchUi();\n    }\n})();\n</script>\n<!-- === BAI_13B_11_11_2_5_UI_END === -->'

CLEAN_MARKER_PAIRS = [
    (
        "# === BAI_13B_11_11_2_TEACHER_NAME_ONLY_START ===",
        "# === BAI_13B_11_11_2_TEACHER_NAME_ONLY_END ===",
    ),
    (
        "# === BAI_13B_11_11_2_3_TEACHER_KEYWORD_START ===",
        "# === BAI_13B_11_11_2_3_TEACHER_KEYWORD_END ===",
    ),
    (
        "# === BAI_13B_11_11_2_3_TEACHER_FILTER_START ===",
        "# === BAI_13B_11_11_2_3_TEACHER_FILTER_END ===",
    ),
    (
        "# === BAI_13B_11_11_2_4_PREPARE_NAME_START ===",
        "# === BAI_13B_11_11_2_4_PREPARE_NAME_END ===",
    ),
    (
        "# === BAI_13B_11_11_2_4_FILTER_NAME_START ===",
        "# === BAI_13B_11_11_2_4_FILTER_NAME_END ===",
    ),
]

CLEAN_UI_PAIRS = [
    (
        "<!-- === BAI_13B_11_11_2_TEACHER_SEARCH_UI_START === -->",
        "<!-- === BAI_13B_11_11_2_TEACHER_SEARCH_UI_END === -->",
    ),
    (
        "<!-- === BAI_13B_11_11_2_3_TEACHER_SEARCH_UI_START === -->",
        "<!-- === BAI_13B_11_11_2_3_TEACHER_SEARCH_UI_END === -->",
    ),
    (
        "<!-- === BAI_13B_11_11_2_4_UI_START === -->",
        "<!-- === BAI_13B_11_11_2_4_UI_END === -->",
    ),
]


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


def remove_marker_blocks(
    text: str,
    pairs: list[tuple[str, str]],
) -> tuple[str, int]:
    removed = 0

    for start_marker, end_marker in pairs:
        while start_marker in text:
            start = text.find(start_marker)
            end = text.find(end_marker, start)
            if end < 0:
                raise RuntimeError(
                    f"Có marker đầu nhưng thiếu marker cuối: {start_marker}"
                )

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


def source_segment(text: str, node: ast.AST) -> str:
    return ast.get_source_segment(text, node) or ""


def find_helper_function(text: str):
    tree = ast.parse(text)

    matches = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == HELPER_NAME
    ]

    if len(matches) != 1:
        raise RuntimeError(
            f"Phải có đúng 1 hàm {HELPER_NAME}, hiện có {len(matches)}."
        )

    return matches[0]


def find_keyword_if(text: str, helper):
    candidates = []

    for node in ast.walk(helper):
        if not isinstance(node, ast.If):
            continue

        test_text = source_segment(text, node.test)
        block_text = source_segment(text, node)

        if "keyword" not in test_text:
            continue

        if "User.full_name" not in block_text:
            continue

        if ".where(" not in block_text:
            continue

        score = 0

        stripped_test = re.sub(r"\s+", "", test_text)
        if stripped_test in {"keyword", "bool(keyword)"}:
            score += 10

        if "User.username" in block_text:
            score += 4
        if "User.full_name" in block_text:
            score += 4
        if "or_(" in block_text:
            score += 2
        if "School" in block_text or "Commune" in block_text:
            score += 1

        candidates.append((score, node, block_text))

    if not candidates:
        raise RuntimeError(
            f"Không tìm thấy khối lọc keyword trong {HELPER_NAME}."
        )

    candidates.sort(key=lambda item: (-item[0], item[1].lineno))
    best_score = candidates[0][0]
    best = [item for item in candidates if item[0] == best_score]

    if len(best) != 1:
        lines = ", ".join(str(item[1].lineno) for item in best)
        raise RuntimeError(
            "Có nhiều khối keyword cùng mức phù hợp tại các dòng: "
            + lines
        )

    return best[0][1]


def detect_statement_var(text: str, keyword_if) -> str:
    names = []

    for node in ast.walk(keyword_if):
        if not isinstance(node, ast.Assign):
            continue

        if len(node.targets) != 1:
            continue

        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue

        value_text = source_segment(text, node.value)

        if ".where(" in value_text:
            names.append(target.id)

    if not names:
        # Fallback regex từ source block.
        block_text = source_segment(text, keyword_if)
        matches = re.findall(
            r"(?m)^\s*([A-Za-z_]\w*)\s*=\s*\1\.where\(",
            block_text,
        )
        names.extend(matches)

    if not names:
        raise RuntimeError(
            "Không xác định được biến statement/query trong khối keyword."
        )

    counts = Counter(names)
    statement_var, _ = counts.most_common(1)[0]
    return statement_var


def dedent_body(lines: list[str]) -> str:
    nonempty = [line for line in lines if line.strip()]
    if not nonempty:
        raise RuntimeError("Thân khối keyword rỗng.")

    margin = min(
        len(line) - len(line.lstrip(" "))
        for line in nonempty
    )

    return "\n".join(
        line[margin:] if line.strip() else ""
        for line in lines
    )


def indent_text(text: str, spaces: int) -> str:
    prefix = " " * spaces
    return "\n".join(
        prefix + line if line.strip() else line
        for line in text.splitlines()
    )


def patch_helper_keyword(text: str) -> str:
    if MARK_HELPER_START in text:
        print(" - Helper 13B-11.11.2.5 đã có sẵn.")
        return text

    helper = find_helper_function(text)
    keyword_if = find_keyword_if(text, helper)
    statement_var = detect_statement_var(text, keyword_if)

    print(
        f" - Khối keyword helper: dòng {keyword_if.lineno}"
    )
    print(
        f" - Biến query xác định: {statement_var}"
    )

    lines = text.splitlines(keepends=True)
    start = keyword_if.lineno - 1
    end = keyword_if.end_lineno

    old_block = "".join(lines[start:end]).rstrip("\r\n")
    old_lines = old_block.splitlines()

    if len(old_lines) < 2:
        raise RuntimeError("Khối keyword không có thân.")

    base_indent = (
        len(old_lines[0])
        - len(old_lines[0].lstrip(" "))
    )

    old_body = dedent_body(old_lines[1:])

    i0 = " " * base_indent
    i1 = " " * (base_indent + 4)
    i2 = " " * (base_indent + 8)
    i3 = " " * (base_indent + 12)
    i4 = " " * (base_indent + 16)

    new_block = (
        f"{i0}{MARK_HELPER_START}\n"
        f"{i0}if keyword:\n"
        f"{i1}if str(section or '').strip().lower() == 'giao_vien':\n"
        f"{i2}teacher_keyword = str(keyword or '').strip()\n"
        f"{i2}teacher_variants = []\n"
        f"{i2}for candidate in (\n"
        f"{i3}teacher_keyword,\n"
        f"{i3}teacher_keyword.upper(),\n"
        f"{i3}teacher_keyword.lower(),\n"
        f"{i3}teacher_keyword.title(),\n"
        f"{i2}):\n"
        f"{i3}if candidate and candidate not in teacher_variants:\n"
        f"{i4}teacher_variants.append(candidate)\n"
        f"\n"
        f"{i2}teacher_name_condition = None\n"
        f"{i2}for candidate in teacher_variants:\n"
        f"{i3}current_condition = User.full_name.like(\n"
        f"{i4}f'%{{candidate}}%'\n"
        f"{i3})\n"
        f"{i3}if teacher_name_condition is None:\n"
        f"{i4}teacher_name_condition = current_condition\n"
        f"{i3}else:\n"
        f"{i4}teacher_name_condition = (\n"
        f"{i4}    teacher_name_condition | current_condition\n"
        f"{i4})\n"
        f"\n"
        f"{i2}if teacher_name_condition is not None:\n"
        f"{i3}{statement_var} = {statement_var}.where(\n"
        f"{i4}teacher_name_condition\n"
        f"{i3})\n"
        f"{i1}else:\n"
        f"{indent_text(old_body, base_indent + 8)}\n"
        f"{i0}{MARK_HELPER_END}\n"
    )

    return (
        "".join(lines[:start])
        + new_block
        + "".join(lines[end:])
    )


def patch_backend(text: str) -> tuple[str, int]:
    # Dọn toàn bộ thử nghiệm lỗi trước.
    text, removed = remove_marker_blocks(
        text,
        CLEAN_MARKER_PAIRS,
    )

    # Kiểm tra chắc chắn block school_statement gây 500 đã biến mất.
    if OLD_BAD_BLOCK_PRESENT(text):
        raise RuntimeError(
            "Sau khi dọn marker vẫn còn cấu trúc lỗi "
            "school_statement/teacher_name_condition ngoài marker."
        )

    text = patch_helper_keyword(text)
    return text, removed


def OLD_BAD_BLOCK_PRESENT(text: str) -> bool:
    # Chỉ báo lỗi nếu teacher_name_condition còn đi cùng school_statement.
    return (
        "teacher_name_condition" in text
        and re.search(
            r"school_statement\s*=\s*school_statement\.where\(\s*"
            r"teacher_name_condition",
            text,
            flags=re.DOTALL,
        )
        is not None
    )


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
            "Không tìm thấy template tài khoản có input name=q."
        )

    return found


def patch_template(text: str) -> str:
    # Dọn UI các bản thử trước.
    for start_marker, end_marker in CLEAN_UI_PAIRS:
        pattern = re.compile(
            re.escape(start_marker)
            + r".*?"
            + re.escape(end_marker),
            flags=re.DOTALL,
        )
        text = pattern.sub("", text)

    if UI_START not in text:
        text = text.rstrip() + "\n\n" + UI_BLOCK + "\n"

    return text


def verify_backend() -> None:
    text = read_text(ROUTER)

    required = [
        MARK_HELPER_START,
        MARK_HELPER_END,
        "User.full_name.like(",
        "teacher_keyword.upper()",
        "teacher_keyword.lower()",
        "teacher_keyword.title()",
        "str(section or '').strip().lower() == 'giao_vien'",
    ]

    for marker in required:
        if marker not in text:
            raise RuntimeError(
                f"Source sau cài thiếu: {marker}"
            )

    for start_marker, _ in CLEAN_MARKER_PAIRS:
        if start_marker in text:
            raise RuntimeError(
                f"Marker thử nghiệm cũ vẫn còn: {start_marker}"
            )

    if OLD_BAD_BLOCK_PRESENT(text):
        raise RuntimeError(
            "Vẫn còn cấu trúc lỗi school_statement."
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

        if UI_START not in text:
            raise RuntimeError(
                f"Template chưa có UI mới: {path}"
            )

        if "Tìm tên giáo viên" not in text:
            raise RuntimeError(
                f"Template thiếu nhãn mới: {path}"
            )

        Environment().parse(text)


def main() -> int:
    print("=" * 122)
    print(
        "BÀI 13B-11.11.2.5 - SỬA TẠI HELPER: "
        "TÌM GIÁO VIÊN CHỈ THEO HỌ TÊN"
    )
    print("=" * 122)
    print()
    print("NGUYÊN NHÂN CÁC BẢN TRƯỚC:")
    print(
        " - danh_sach_tai_khoan có 2 lần gọi "
        "lay_danh_sach_tai_khoan_phan_trang."
    )
    print(
        " - Không nên sửa từng lời gọi ở router."
    )
    print()
    print("CÁCH SỬA BẢN NÀY:")
    print(
        " - Gỡ sạch block school_statement lỗi của 13B-11.11.2."
    )
    print(
        " - Sửa trực tiếp helper lay_danh_sach_tai_khoan_phan_trang."
    )
    print(
        " - section=giao_vien: keyword chỉ lọc User.full_name."
    )
    print(
        " - Các section khác giữ nguyên nguyên khối tìm kiếm cũ."
    )
    print(
        " - Pagination/count vẫn do helper xử lý như trước."
    )
    print(
        " - Áp dụng Mầm non, Tiểu học, THCS."
    )
    print()
    print("AN TOÀN:")
    print(" - Backup source.")
    print(" - py_compile users.py.")
    print(" - Jinja parse.")
    print(" - Không sửa database.")
    print(" - Không đổi quyền/menu.")
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
            write_text(
                path,
                patch_template(read_text(path)),
            )

        verify_backend()
        verify_templates(templates)
        clear_cache()

        print()
        print("KIỂM TRA SAU CÀI:")
        print(
            f" - Block thử nghiệm cũ đã gỡ: {removed}"
        )
        print(
            " - Không còn school_statement lỗi: OK"
        )
        print(
            " - Helper chỉ tìm full_name cho giao_vien: OK"
        )
        print(
            " - Bộ lọc các mục khác giữ nguyên: OK"
        )
        print(
            " - Python py_compile: OK"
        )
        print(
            " - Jinja parse: OK"
        )
        print(
            " - Database: KHÔNG THAY ĐỔI"
        )
        print()
        print(
            "CÀI ĐẶT BÀI 13B-11.11.2.5 THÀNH CÔNG"
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
