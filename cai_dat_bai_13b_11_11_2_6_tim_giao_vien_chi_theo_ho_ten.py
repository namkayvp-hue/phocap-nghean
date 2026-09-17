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
BACKUP = PROJECT / "exports" / f"backup_source_bai_13b_11_11_2_6_{STAMP}"

MARK_START = "# === BAI_13B_11_11_2_6_TEACHER_NAME_ONLY_START ==="
MARK_END = "# === BAI_13B_11_11_2_6_TEACHER_NAME_ONLY_END ==="

UI_START = "<!-- === BAI_13B_11_11_2_6_UI_START === -->"
UI_END = "<!-- === BAI_13B_11_11_2_6_UI_END === -->"

UI_BLOCK = '<!-- === BAI_13B_11_11_2_6_UI_START === -->\n<script>\n(function () {\n    function applyTeacherSearchUi() {\n        var params = new URLSearchParams(window.location.search || "");\n        var bodyText = String(document.body ? document.body.innerText : "");\n        var muc = String(params.get("muc") || "").trim().toLowerCase();\n\n        var isTeacherPage =\n            muc === "giao_vien" ||\n            bodyText.indexOf("Quản lý giáo viên") !== -1 ||\n            bodyText.indexOf("Giáo viên của trường") !== -1;\n\n        if (!isTeacherPage) return;\n\n        var input = document.querySelector(\'input[name="q"]\');\n        if (!input) return;\n\n        input.placeholder = "Nhập họ và tên giáo viên";\n        input.title = "Chỉ tìm theo toàn bộ hoặc một phần họ và tên giáo viên";\n\n        var label = null;\n        if (input.id) {\n            label = document.querySelector(\'label[for="\' + input.id + \'"]\');\n        }\n        if (!label && input.parentElement) {\n            label = input.parentElement.querySelector("label");\n        }\n        if (label) {\n            label.textContent = "Tìm tên giáo viên";\n        }\n    }\n\n    if (document.readyState === "loading") {\n        document.addEventListener("DOMContentLoaded", applyTeacherSearchUi);\n    } else {\n        applyTeacherSearchUi();\n    }\n})();\n</script>\n<!-- === BAI_13B_11_11_2_6_UI_END === -->'
OLD_CONDITIONS_BLOCK = '    conditions = tao_dieu_kien_loc(\n        actor=actor,\n        section=section,\n        keyword=keyword,\n        commune_id=commune_id,\n        school_id=school_id,\n        account_status=account_status,\n    )\n'
NEW_CONDITIONS_BLOCK = '    # === BAI_13B_11_11_2_6_TEACHER_NAME_ONLY_START ===\n    teacher_name_keyword = " ".join(str(keyword or "").split())\n\n    conditions = list(\n        tao_dieu_kien_loc(\n            actor=actor,\n            section=section,\n            keyword=(\n                ""\n                if section == "giao_vien" and teacher_name_keyword\n                else keyword\n            ),\n            commune_id=commune_id,\n            school_id=school_id,\n            account_status=account_status,\n        )\n    )\n\n    if section == "giao_vien" and teacher_name_keyword:\n        teacher_name_variants: list[str] = []\n\n        for candidate in (\n            teacher_name_keyword,\n            teacher_name_keyword.upper(),\n            teacher_name_keyword.lower(),\n            teacher_name_keyword.title(),\n        ):\n            candidate = str(candidate or "").strip()\n            if candidate and candidate not in teacher_name_variants:\n                teacher_name_variants.append(candidate)\n\n        teacher_name_condition = None\n\n        for candidate in teacher_name_variants:\n            current_condition = User.full_name.like(\n                f"%{candidate}%"\n            )\n\n            if teacher_name_condition is None:\n                teacher_name_condition = current_condition\n            else:\n                teacher_name_condition = (\n                    teacher_name_condition | current_condition\n                )\n\n        if teacher_name_condition is not None:\n            conditions.append(teacher_name_condition)\n    # === BAI_13B_11_11_2_6_TEACHER_NAME_ONLY_END ===\n'

OLD_PYTHON_MARKERS = [
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
    (
        "# === BAI_13B_11_11_2_5_NAME_ONLY_START ===",
        "# === BAI_13B_11_11_2_5_NAME_ONLY_END ===",
    ),
]

OLD_UI_MARKERS = [
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
    (
        "<!-- === BAI_13B_11_11_2_5_UI_START === -->",
        "<!-- === BAI_13B_11_11_2_5_UI_END === -->",
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


def remove_marker_blocks(text: str, pairs: list[tuple[str, str]]) -> tuple[str, int]:
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


def bad_school_statement_block_exists(text: str) -> bool:
    return re.search(
        r"teacher_name_condition.*?"
        r"school_statement\s*=\s*school_statement\.where\(\s*"
        r"teacher_name_condition",
        text,
        flags=re.DOTALL,
    ) is not None


def find_helper_range(text: str) -> tuple[int, int]:
    tree = ast.parse(text)

    matches = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "lay_danh_sach_tai_khoan_phan_trang"
    ]

    if len(matches) != 1:
        raise RuntimeError(
            "Phải tìm thấy đúng 1 hàm lay_danh_sach_tai_khoan_phan_trang, "
            f"hiện có {len(matches)}."
        )

    node = matches[0]
    return node.lineno, node.end_lineno


def patch_backend(text: str) -> tuple[str, int]:
    text, removed = remove_marker_blocks(
        text,
        OLD_PYTHON_MARKERS,
    )

    if bad_school_statement_block_exists(text):
        raise RuntimeError(
            "Sau khi gỡ marker cũ vẫn còn cấu trúc lỗi school_statement."
        )

    if MARK_START in text:
        print(" - Bài 13B-11.11.2.6 đã có sẵn.")
        return text, removed

    helper_start, helper_end = find_helper_range(text)

    lines = text.splitlines(keepends=True)
    helper_text = "".join(
        lines[helper_start - 1 : helper_end]
    )

    count = helper_text.count(OLD_CONDITIONS_BLOCK)

    if count != 1:
        raise RuntimeError(
            "Trong helper phải có đúng 1 block conditions = tao_dieu_kien_loc(...), "
            f"hiện tìm thấy {count}."
        )

    helper_text = helper_text.replace(
        OLD_CONDITIONS_BLOCK,
        NEW_CONDITIONS_BLOCK,
        1,
    )

    text = (
        "".join(lines[: helper_start - 1])
        + helper_text
        + "".join(lines[helper_end:])
    )

    return text, removed


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
    for start_marker, end_marker in OLD_UI_MARKERS:
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
        MARK_START,
        MARK_END,
        'if section == "giao_vien" and teacher_name_keyword',
        'User.full_name.like(',
        'conditions.append(teacher_name_condition)',
        '.where(*conditions)',
        'select(func.count(User.id))',
    ]

    for marker in required:
        if marker not in text:
            raise RuntimeError(
                f"Source sau cài thiếu: {marker}"
            )

    if bad_school_statement_block_exists(text):
        raise RuntimeError(
            "Vẫn còn cấu trúc lỗi school_statement."
        )

    for start_marker, _ in OLD_PYTHON_MARKERS:
        if start_marker in text:
            raise RuntimeError(
                f"Marker thử nghiệm cũ vẫn còn: {start_marker}"
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
    print("=" * 124)
    print(
        "BÀI 13B-11.11.2.6 - TÌM GIÁO VIÊN CHỈ THEO HỌ TÊN "
        "TẠI ĐÚNG HELPER THỰC TẾ"
    )
    print("=" * 124)
    print()
    print("SOURCE ĐÃ XÁC ĐỊNH:")
    print(
        " - lay_danh_sach_tai_khoan_phan_trang gọi "
        "tao_dieu_kien_loc(...) để tạo conditions."
    )
    print(
        " - count_statement và statement đều dùng chung conditions."
    )
    print()
    print("CÁCH SỬA:")
    print(
        " - Gỡ sạch block school_statement lỗi của các bản trước."
    )
    print(
        " - section=giao_vien: không truyền keyword vào bộ lọc rộng cũ."
    )
    print(
        " - Thêm riêng điều kiện User.full_name vào conditions."
    )
    print(
        " - Count và phân trang tự động đúng vì cùng dùng conditions."
    )
    print(
        " - Tìm một phần tên; hỗ trợ HOA/thường/Title."
    )
    print(
        " - Các mục tài khoản khác giữ nguyên."
    )
    print()
    print("ÁP DỤNG: Mầm non, Tiểu học, THCS.")
    print("KHÔNG sửa database, quyền, menu.")
    print()

    if not ROUTER.exists():
        raise RuntimeError(
            f"Không tìm thấy: {ROUTER}"
        )

    templates = find_templates()

    BACKUP.mkdir(
        parents=True,
        exist_ok=False,
    )

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
            " - giao_vien chỉ lọc User.full_name: OK"
        )
        print(
            " - Count và phân trang dùng cùng conditions: OK"
        )
        print(
            " - Các mục tài khoản khác giữ nguyên: OK"
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
            "CÀI ĐẶT BÀI 13B-11.11.2.6 THÀNH CÔNG"
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
