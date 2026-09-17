from __future__ import annotations

import ast
import os
import shutil
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path

PROJECT = Path(
    os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")
).resolve()

APP = PROJECT / "app"
ROUTER = APP / "routers" / "users.py"
TEMPLATES = APP / "templates"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = (
    PROJECT
    / "exports"
    / f"backup_source_bai_13b_11_11_2_{STAMP}"
)

MARK_START = (
    "# === BAI_13B_11_11_2_TEACHER_NAME_ONLY_START ==="
)
MARK_END = (
    "# === BAI_13B_11_11_2_TEACHER_NAME_ONLY_END ==="
)
UI_START = (
    "<!-- === BAI_13B_11_11_2_TEACHER_SEARCH_UI_START === -->"
)
UI_END = (
    "<!-- === BAI_13B_11_11_2_TEACHER_SEARCH_UI_END === -->"
)

UI_BLOCK = '<!-- === BAI_13B_11_11_2_TEACHER_SEARCH_UI_START === -->\n<script>\n(function () {\n    function applyTeacherSearchUi() {\n        var params = new URLSearchParams(window.location.search || "");\n        var muc = String(params.get("muc") || "").trim().toLowerCase();\n\n        if (muc !== "giao_vien") return;\n\n        var qInput = document.querySelector(\'input[name="q"]\');\n        if (!qInput) return;\n\n        qInput.setAttribute("placeholder", "Nhập họ và tên giáo viên");\n        qInput.setAttribute(\n            "title",\n            "Nhập toàn bộ hoặc một phần họ và tên giáo viên"\n        );\n\n        var label = null;\n        if (qInput.id) {\n            label = document.querySelector(\n                \'label[for="\' + qInput.id + \'"]\'\n            );\n        }\n        if (!label && qInput.parentElement) {\n            label = qInput.parentElement.querySelector("label");\n        }\n        if (label) {\n            label.textContent = "Tìm tên giáo viên";\n        }\n    }\n\n    if (document.readyState === "loading") {\n        document.addEventListener(\n            "DOMContentLoaded",\n            applyTeacherSearchUi\n        );\n    } else {\n        applyTeacherSearchUi();\n    }\n})();\n</script>\n<!-- === BAI_13B_11_11_2_TEACHER_SEARCH_UI_END === -->'
INJECTED_BLOCK = '    # === BAI_13B_11_11_2_TEACHER_NAME_ONLY_START ===\n    if (\n        str(muc or "").strip().lower() == "giao_vien"\n        and str(q or "").strip()\n    ):\n        teacher_name = str(q or "").strip()\n        teacher_variants = []\n        for candidate in (\n            teacher_name,\n            teacher_name.upper(),\n            teacher_name.lower(),\n            teacher_name.title(),\n        ):\n            if candidate and candidate not in teacher_variants:\n                teacher_variants.append(candidate)\n\n        teacher_name_condition = None\n        for candidate in teacher_variants:\n            current_condition = User.full_name.like(\n                f"%{candidate}%"\n            )\n            if teacher_name_condition is None:\n                teacher_name_condition = current_condition\n            else:\n                teacher_name_condition = (\n                    teacher_name_condition | current_condition\n                )\n\n        if teacher_name_condition is not None:\n            {statement_var} = {statement_var}.where(\n                teacher_name_condition\n            )\n    # === BAI_13B_11_11_2_TEACHER_NAME_ONLY_END ===\n'


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


def node_source(
    text: str,
    node: ast.AST,
) -> str:
    return ast.get_source_segment(text, node) or ""


def get_function_args(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> set[str]:
    names = {arg.arg for arg in node.args.args}
    names.update(arg.arg for arg in node.args.kwonlyargs)
    return names


def find_statement_assignment(
    func: ast.FunctionDef | ast.AsyncFunctionDef,
    text: str,
):
    candidates = []

    for node in ast.walk(func):
        if not isinstance(node, ast.Assign):
            continue
        if len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue

        value_text = node_source(text, node.value)

        score = 0
        if "select(User)" in value_text:
            score += 10
        elif "select(" in value_text and "User" in value_text:
            score += 6

        if ".options(" in value_text:
            score += 1
        if ".where(" in value_text:
            score += 1
        if ".order_by(" in value_text:
            score += 1

        if score > 0:
            candidates.append(
                (score, node, target.id)
            )

    if not candidates:
        return None

    candidates.sort(
        key=lambda item: (-item[0], item[1].lineno)
    )
    return candidates[0][1], candidates[0][2]


def find_targets(text: str):
    tree = ast.parse(text)
    targets = []

    for func in tree.body:
        if not isinstance(
            func,
            (ast.FunctionDef, ast.AsyncFunctionDef),
        ):
            continue

        args = get_function_args(func)

        if "q" not in args or "muc" not in args:
            continue

        func_text = node_source(text, func)

        if "User" not in func_text:
            continue

        statement_info = find_statement_assignment(
            func,
            text,
        )
        if statement_info is None:
            continue

        assignment_node, statement_var = statement_info

        # Ưu tiên route GET của khu vực tài khoản.
        decorator_text = "\n".join(
            node_source(text, deco)
            for deco in func.decorator_list
        )

        score = 0
        if "router.get" in decorator_text:
            score += 5
        if "tai-khoan" in decorator_text.lower():
            score += 5
        if "TemplateResponse" in func_text:
            score += 3
        if "User.role" in func_text or "Role" in func_text:
            score += 2

        targets.append(
            (
                score,
                func.name,
                assignment_node.end_lineno,
                statement_var,
            )
        )

    if not targets:
        raise RuntimeError(
            "Không tìm thấy hàm có q + muc + select(User) "
            "trong users.py."
        )

    # Nếu có route tài khoản rõ ràng thì chỉ lấy nhóm điểm cao.
    max_score = max(item[0] for item in targets)

    if max_score >= 8:
        chosen = [
            item
            for item in targets
            if item[0] == max_score
        ]
    else:
        chosen = targets

    return chosen


def patch_backend(text: str) -> tuple[str, int]:
    if MARK_START in text:
        print(
            " - Backend 13B-11.11.2 đã có sẵn, "
            "không chèn lặp."
        )
        return text, 0

    targets = find_targets(text)

    lines = text.splitlines(keepends=True)
    insertions = []

    for (
        score,
        func_name,
        end_lineno,
        statement_var,
    ) in targets:
        block = INJECTED_BLOCK.format(
            statement_var=statement_var
        )

        insertions.append(
            (
                end_lineno,
                block,
                func_name,
                score,
            )
        )

    # Chèn từ cuối lên đầu để không lệch line.
    insertions.sort(
        key=lambda item: item[0],
        reverse=True,
    )

    for (
        end_lineno,
        block,
        func_name,
        score,
    ) in insertions:
        lines[end_lineno:end_lineno] = [block]

    print("Các hàm backend được sửa:")
    for _, _, func_name, score in sorted(
        insertions,
        key=lambda item: item[2],
    ):
        print(
            f" - {func_name} (score={score})"
        )

    return "".join(lines), len(insertions)


def find_templates() -> list[Path]:
    candidates = []

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
            candidates.append(path)

    if not candidates:
        raise RuntimeError(
            "Không tìm thấy template quản lý tài khoản "
            "có input name=q."
        )

    return candidates


def patch_templates(
    paths: list[Path],
) -> int:
    changed = 0

    for path in paths:
        text = read_text(path)

        if UI_START in text:
            continue

        text = (
            text.rstrip()
            + "\n\n"
            + UI_BLOCK
            + "\n"
        )
        write_text(path, text)
        changed += 1

    return changed


def verify_backend() -> int:
    text = read_text(ROUTER)

    required = [
        MARK_START,
        MARK_END,
        "User.full_name.like",
        'str(muc or "").strip().lower() == "giao_vien"',
        "teacher_name.upper()",
        "teacher_name.lower()",
        "teacher_name.title()",
    ]

    for marker in required:
        if marker not in text:
            raise RuntimeError(
                "Kiểm tra backend thiếu: "
                + marker
            )

    ast.parse(text)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "py_compile",
            str(ROUTER),
        ],
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

    return text.count(MARK_START)


def verify_templates(
    paths: list[Path],
) -> None:
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
    print("=" * 112)
    print(
        "BÀI 13B-11.11.2 - TÌM GIÁO VIÊN "
        "CHỈ THEO HỌ TÊN CHO TẤT CẢ CẤP HỌC"
    )
    print("=" * 112)
    print()
    print("ÁP DỤNG:")
    print(" - Mầm non")
    print(" - Tiểu học")
    print(" - THCS")
    print()
    print("CÁCH SỬA MỚI:")
    print(
        " - Không tìm/chỉnh khối if q cũ."
    )
    print(
        " - Chèn điều kiện Họ tên ngay sau "
        "select(User)."
    )
    print(
        " - Khi muc=giao_vien và có q, "
        "kết quả bắt buộc khớp User.full_name."
    )
    print(
        " - Bộ lọc cũ phía sau vẫn được giữ nguyên."
    )
    print()
    print("GIỮ NGUYÊN:")
    print(
        " - Không sửa database."
    )
    print(
        " - Không đổi quyền."
    )
    print(
        " - Không đổi menu."
    )
    print(
        " - Các mục tài khoản khác không bị áp "
        "điều kiện tên giáo viên."
    )
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
    print(
        "Template liên quan:",
        len(templates),
    )

    try:
        before = read_text(ROUTER)

        after, backend_changed = (
            patch_backend(before)
        )

        write_text(ROUTER, after)

        template_changed = patch_templates(
            templates
        )

        backend_blocks = verify_backend()

        verify_templates(templates)

        clear_cache()

        print()
        print("KIỂM TRA SAU CÀI:")
        print(
            " - Khối backend đã chèn:",
            backend_blocks,
        )
        print(
            " - Template bổ sung UI:",
            template_changed,
        )
        print(
            " - muc=giao_vien bắt buộc "
            "khớp User.full_name: OK"
        )
        print(
            " - Tìm một phần tên: OK"
        )
        print(
            " - Biến thể HOA/thường: OK"
        )
        print(
            " - Python/Jinja: OK"
        )
        print(
            " - Database: KHÔNG THAY ĐỔI"
        )
        print()
        print(
            "CÀI ĐẶT BÀI 13B-11.11.2 "
            "THÀNH CÔNG"
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
        print(
            "Database không bị thay đổi."
        )
        print("Backup:", BACKUP)

        return 1


if __name__ == "__main__":
    raise SystemExit(main())
