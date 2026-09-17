from __future__ import annotations

import ast
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import traceback
from collections import Counter
from datetime import datetime
from pathlib import Path

PROJECT = Path(os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")).resolve()
APP = PROJECT / "app"
ROUTERS = APP / "routers"
TEMPLATE = APP / "templates" / "surveys" / "year_records.html"
DB_PATH = PROJECT / "data" / "phocap.db"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = PROJECT / "exports" / f"backup_bai_13b_11_13_2_{STAMP}"

XMC_BLOCK = '\n                    <!-- === BAI_13B_11_13_2_XMC_UI_START === -->\n                    <div class="form-group full b131132-card b131132-xmc-main">\n                        <div class="b131132-title">\n                            1. Đối tượng điều tra Xóa mù chữ\n                        </div>\n                        <p class="b131132-help">\n                            Xác định đối tượng này có thuộc phạm vi điều tra Xóa mù chữ trong năm học đang chọn hay không.\n                        </p>\n\n                        <label for="is_literacy_target">\n                            Đối tượng điều tra Xóa mù chữ\n                        </label>\n                        <select\n                            id="is_literacy_target"\n                            name="is_literacy_target"\n                            class="form-control"\n                        >\n                            <option\n                                value="CHUA_XAC_DINH"\n                                {% if not selected_record or selected_record.is_literacy_target is none %}selected{% endif %}\n                            >\n                                -- Chưa xác định --\n                            </option>\n                            <option\n                                value="CO"\n                                {% if selected_record and selected_record.is_literacy_target is sameas true %}selected{% endif %}\n                            >\n                                Có\n                            </option>\n                            <option\n                                value="KHONG"\n                                {% if selected_record and selected_record.is_literacy_target is sameas false %}selected{% endif %}\n                            >\n                                Không\n                            </option>\n                        </select>\n                    </div>\n\n                    <div\n                        id="b131132_xmc_details"\n                        class="form-group full b131132-card b131132-xmc-details"\n                    >\n                        <div class="b131132-subtitle">\n                            Thông tin Xóa mù chữ\n                        </div>\n\n                        <div class="b131132-grid">\n                            <div>\n                                <label for="literacy_status">\n                                    Tình trạng Xóa mù chữ\n                                </label>\n                                <select\n                                    id="literacy_status"\n                                    name="literacy_status"\n                                    class="form-control"\n                                >\n                                    <option\n                                        value="CHUA_XAC_DINH"\n                                        {% if not selected_record or (selected_record.literacy_status or \'CHUA_XAC_DINH\') == \'CHUA_XAC_DINH\' %}selected{% endif %}\n                                    >\n                                        -- Chưa xác định --\n                                    </option>\n                                    <option\n                                        value="KHONG_THUOC_DIEN"\n                                        {% if selected_record and selected_record.literacy_status == \'KHONG_THUOC_DIEN\' %}selected{% endif %}\n                                    >\n                                        Không thuộc diện mù chữ\n                                    </option>\n                                    <option\n                                        value="THEO_DOI_XMC"\n                                        {% if selected_record and selected_record.literacy_status == \'THEO_DOI_XMC\' %}selected{% endif %}\n                                    >\n                                        Thuộc diện theo dõi XMC\n                                    </option>\n                                </select>\n                            </div>\n\n                            <div>\n                                <label for="completed_grade_3">\n                                    Hoàn thành lớp 3\n                                </label>\n                                <select\n                                    id="completed_grade_3"\n                                    name="completed_grade_3"\n                                    class="form-control"\n                                >\n                                    <option\n                                        value="CHUA_XAC_DINH"\n                                        {% if not selected_record or selected_record.completed_grade_3 is none %}selected{% endif %}\n                                    >\n                                        -- Chưa xác định --\n                                    </option>\n                                    <option\n                                        value="CO"\n                                        {% if selected_record and selected_record.completed_grade_3 is sameas true %}selected{% endif %}\n                                    >\n                                        Có\n                                    </option>\n                                    <option\n                                        value="KHONG"\n                                        {% if selected_record and selected_record.completed_grade_3 is sameas false %}selected{% endif %}\n                                    >\n                                        Không\n                                    </option>\n                                </select>\n                                <small class="b131132-note">\n                                    Không → dùng xác định Mức độ 1 – Chưa hoàn thành lớp 3.\n                                </small>\n                            </div>\n\n                            <div>\n                                <label for="completed_grade_5">\n                                    Hoàn thành lớp 5\n                                </label>\n                                <select\n                                    id="completed_grade_5"\n                                    name="completed_grade_5"\n                                    class="form-control"\n                                >\n                                    <option\n                                        value="CHUA_XAC_DINH"\n                                        {% if not selected_record or selected_record.completed_grade_5 is none %}selected{% endif %}\n                                    >\n                                        -- Chưa xác định --\n                                    </option>\n                                    <option\n                                        value="CO"\n                                        {% if selected_record and selected_record.completed_grade_5 is sameas true %}selected{% endif %}\n                                    >\n                                        Có\n                                    </option>\n                                    <option\n                                        value="KHONG"\n                                        {% if selected_record and selected_record.completed_grade_5 is sameas false %}selected{% endif %}\n                                    >\n                                        Không\n                                    </option>\n                                </select>\n                                <small class="b131132-note">\n                                    Không → dùng xác định Mức độ 2 – Chưa hoàn thành lớp 5.\n                                </small>\n                            </div>\n                        </div>\n                    </div>\n                    <!-- === BAI_13B_11_13_2_XMC_UI_END === -->\n'
LEVEL_BLOCK = '\n                    <!-- === BAI_13B_11_13_2_LEVEL_UI_START === -->\n                    <div\n                        id="b131132_primary_indicators"\n                        class="form-group full b131132-card b131132-level-card"\n                    >\n                        <div class="b131132-title">\n                            Các chỉ báo Tiểu học\n                        </div>\n                        <p class="b131132-help">\n                            Các nhóm tuổi và chỉ tiêu có thể tính từ năm sinh, trường và lớp sẽ do hệ thống tự tổng hợp.\n                            Giáo viên chỉ nhập dữ liệu gốc không thể tự suy ra.\n                        </p>\n\n                        <label for="completed_primary_program">\n                            Hoàn thành chương trình Tiểu học\n                        </label>\n                        <select\n                            id="completed_primary_program"\n                            name="completed_primary_program"\n                            class="form-control"\n                        >\n                            <option\n                                value="CHUA_XAC_DINH"\n                                {% if not selected_record or selected_record.completed_primary_program is none %}selected{% endif %}\n                            >\n                                -- Chưa xác định --\n                            </option>\n                            <option\n                                value="CO"\n                                {% if selected_record and selected_record.completed_primary_program is sameas true %}selected{% endif %}\n                            >\n                                Có\n                            </option>\n                            <option\n                                value="KHONG"\n                                {% if selected_record and selected_record.completed_primary_program is sameas false %}selected{% endif %}\n                            >\n                                Không\n                            </option>\n                        </select>\n                    </div>\n\n                    <div\n                        id="b131132_thcs_indicators"\n                        class="form-group full b131132-card b131132-level-card"\n                    >\n                        <div class="b131132-title">\n                            Các chỉ báo THCS\n                        </div>\n                        <p class="b131132-help">\n                            Dữ liệu này phục vụ tổng hợp hoàn thành THCS và hướng học sau THCS.\n                        </p>\n\n                        <div class="b131132-grid">\n                            <div>\n                                <label for="completed_lower_secondary_program">\n                                    Hoàn thành chương trình THCS\n                                </label>\n                                <select\n                                    id="completed_lower_secondary_program"\n                                    name="completed_lower_secondary_program"\n                                    class="form-control"\n                                >\n                                    <option\n                                        value="CHUA_XAC_DINH"\n                                        {% if not selected_record or selected_record.completed_lower_secondary_program is none %}selected{% endif %}\n                                    >\n                                        -- Chưa xác định --\n                                    </option>\n                                    <option\n                                        value="CO"\n                                        {% if selected_record and selected_record.completed_lower_secondary_program is sameas true %}selected{% endif %}\n                                    >\n                                        Có\n                                    </option>\n                                    <option\n                                        value="KHONG"\n                                        {% if selected_record and selected_record.completed_lower_secondary_program is sameas false %}selected{% endif %}\n                                    >\n                                        Không\n                                    </option>\n                                </select>\n                            </div>\n\n                            <div>\n                                <label for="post_lower_secondary_path">\n                                    Hướng học sau THCS\n                                </label>\n                                <select\n                                    id="post_lower_secondary_path"\n                                    name="post_lower_secondary_path"\n                                    class="form-control"\n                                >\n                                    <option\n                                        value="CHUA_XAC_DINH"\n                                        {% if not selected_record or (selected_record.post_lower_secondary_path or \'CHUA_XAC_DINH\') == \'CHUA_XAC_DINH\' %}selected{% endif %}\n                                    >\n                                        -- Chưa xác định --\n                                    </option>\n                                    <option\n                                        value="THPT"\n                                        {% if selected_record and selected_record.post_lower_secondary_path == \'THPT\' %}selected{% endif %}\n                                    >\n                                        Đang học THPT\n                                    </option>\n                                    <option\n                                        value="GDTX"\n                                        {% if selected_record and selected_record.post_lower_secondary_path == \'GDTX\' %}selected{% endif %}\n                                    >\n                                        Đang học GDTX cấp THPT\n                                    </option>\n                                    <option\n                                        value="GDNN"\n                                        {% if selected_record and selected_record.post_lower_secondary_path == \'GDNN\' %}selected{% endif %}\n                                    >\n                                        Đang học giáo dục nghề nghiệp\n                                    </option>\n                                    <option\n                                        value="KHONG_HOC"\n                                        {% if selected_record and selected_record.post_lower_secondary_path == \'KHONG_HOC\' %}selected{% endif %}\n                                    >\n                                        Không học tiếp\n                                    </option>\n                                </select>\n                            </div>\n                        </div>\n                    </div>\n                    <!-- === BAI_13B_11_13_2_LEVEL_UI_END === -->\n'
STYLE_AND_SCRIPT = '\n<!-- === BAI_13B_11_13_2_DYNAMIC_UI_START === -->\n<style>\n    .b131132-card {\n        border: 1px solid #d8e4ef;\n        border-radius: 12px;\n        padding: 15px;\n        background: #f8fbfe;\n    }\n\n    .b131132-xmc-main {\n        border-color: #b9d7f0;\n        background: #f4f9fd;\n    }\n\n    .b131132-xmc-details {\n        border-color: #f0d58a;\n        background: #fffaf0;\n    }\n\n    .b131132-level-card {\n        border-color: #c9ddce;\n        background: #f7fbf8;\n    }\n\n    .b131132-title {\n        font-size: 16px;\n        font-weight: 900;\n        margin-bottom: 5px;\n        color: #17324d;\n    }\n\n    .b131132-subtitle {\n        font-size: 15px;\n        font-weight: 900;\n        margin-bottom: 12px;\n    }\n\n    .b131132-help {\n        margin: 0 0 12px;\n        color: #557086;\n        line-height: 1.45;\n        font-size: 13px;\n    }\n\n    .b131132-note {\n        display: block;\n        margin-top: 6px;\n        color: #705d26;\n        line-height: 1.4;\n    }\n\n    .b131132-grid {\n        display: grid;\n        grid-template-columns: repeat(2, minmax(0, 1fr));\n        gap: 14px;\n    }\n\n    @media (max-width: 760px) {\n        .b131132-grid {\n            grid-template-columns: 1fr;\n        }\n    }\n</style>\n\n<script>\n(function () {\n    function parseAge() {\n        const dobText = {{ (person.date_of_birth.isoformat() if person.date_of_birth else \'\') | tojson }};\n        const schoolYearText = {{ (batch.school_year.code if batch.school_year else \'\') | tojson }};\n\n        if (!dobText) return null;\n\n        const birthYear = parseInt(String(dobText).slice(0, 4), 10);\n        if (!Number.isFinite(birthYear)) return null;\n\n        const matches = String(schoolYearText || "").match(/\\d{4}/g);\n        let referenceYear = null;\n\n        if (matches && matches.length) {\n            referenceYear = parseInt(matches[0], 10);\n        }\n\n        if (!Number.isFinite(referenceYear)) {\n            referenceYear = new Date().getFullYear();\n        }\n\n        const age = referenceYear - birthYear;\n\n        if (!Number.isFinite(age) || age < 0 || age > 120) {\n            return null;\n        }\n\n        return age;\n    }\n\n    function setVisible(element, visible) {\n        if (!element) return;\n        element.hidden = !visible;\n    }\n\n    function updateLiteracy() {\n        const target = document.getElementById("is_literacy_target");\n        const details = document.getElementById("b131132_xmc_details");\n\n        if (!target || !details) return;\n\n        setVisible(details, target.value === "CO");\n    }\n\n    function findPreschoolContainers() {\n        const names = [\n            "completed_preschool_5",\n            "completed_preschool_by_age",\n            "attends_required_days",\n            "attends_regularly",\n            "prepared_vietnamese",\n            "weight_monitored",\n            "underweight",\n            "height_monitored",\n            "stunted"\n        ];\n\n        const result = new Set();\n\n        names.forEach(function (name) {\n            const field = document.querySelector(\'[name="\' + name + \'"]\');\n            if (!field) return;\n\n            const group = field.closest(".form-group");\n            if (group) result.add(group);\n        });\n\n        Array.from(document.querySelectorAll("label,h3,h4,strong,div")).forEach(function (node) {\n            const text = String(node.textContent || "").trim().toLowerCase();\n            if (text === "các chỉ báo mầm non" || text === "các chỉ báo mầm non:") {\n                const group = node.closest(".form-group");\n                if (group) {\n                    result.add(group);\n                } else if (node.parentElement) {\n                    result.add(node.parentElement);\n                }\n            }\n        });\n\n        return Array.from(result);\n    }\n\n    function updateLevelIndicators() {\n        const age = parseAge();\n\n        const primary = document.getElementById("b131132_primary_indicators");\n        const thcs = document.getElementById("b131132_thcs_indicators");\n        const preschoolContainers = findPreschoolContainers();\n\n        /*\n         * Không có ngày sinh: không tự ẩn nhóm nào để người dùng vẫn có thể rà soát.\n         * Có ngày sinh:\n         *   0-5  : Mầm non\n         *   6-14 : dữ liệu phục vụ Tiểu học\n         *   11-18: dữ liệu phục vụ THCS\n         * Các khoảng 11-14 cố ý giao nhau vì báo cáo phổ cập cần cả\n         * hoàn thành Tiểu học và tình trạng THCS.\n         */\n        if (age === null) {\n            setVisible(primary, true);\n            setVisible(thcs, true);\n            preschoolContainers.forEach(function (item) {\n                setVisible(item, true);\n            });\n            return;\n        }\n\n        setVisible(primary, age >= 6 && age <= 14);\n        setVisible(thcs, age >= 11 && age <= 18);\n\n        preschoolContainers.forEach(function (item) {\n            setVisible(item, age <= 5);\n        });\n    }\n\n    document.addEventListener("DOMContentLoaded", function () {\n        const target = document.getElementById("is_literacy_target");\n\n        if (target) {\n            target.addEventListener("change", updateLiteracy);\n        }\n\n        updateLiteracy();\n        updateLevelIndicators();\n    });\n})();\n</script>\n<!-- === BAI_13B_11_13_2_DYNAMIC_UI_END === -->\n'
SAVE_BLOCK_TEMPLATE = '\n# === BAI_13B_11_13_2_SAVE_FIELDS_START ===\ndef _b131132_optional_bool(value):\n    raw = str(value or "").strip().upper()\n    if raw in {"CO", "1", "TRUE"}:\n        return True\n    if raw in {"KHONG", "0", "FALSE"}:\n        return False\n    return None\n\n_b131132_is_literacy_target = _b131132_optional_bool(\n    is_literacy_target\n)\n\n{record}.is_literacy_target = _b131132_is_literacy_target\n\nif _b131132_is_literacy_target is True:\n    _b131132_literacy_status = str(\n        literacy_status or "CHUA_XAC_DINH"\n    ).strip().upper()\n\n    if _b131132_literacy_status not in {\n        "CHUA_XAC_DINH",\n        "KHONG_THUOC_DIEN",\n        "THEO_DOI_XMC",\n    }:\n        _b131132_literacy_status = "CHUA_XAC_DINH"\n\n    {record}.literacy_status = _b131132_literacy_status\n    {record}.completed_grade_3 = _b131132_optional_bool(\n        completed_grade_3\n    )\n    {record}.completed_grade_5 = _b131132_optional_bool(\n        completed_grade_5\n    )\nelse:\n    # Khi không thuộc đối tượng XMC thì không giữ chỉ báo XMC cũ.\n    {record}.literacy_status = "CHUA_XAC_DINH"\n    {record}.completed_grade_3 = None\n    {record}.completed_grade_5 = None\n\n{record}.completed_primary_program = _b131132_optional_bool(\n    completed_primary_program\n)\n{record}.completed_lower_secondary_program = _b131132_optional_bool(\n    completed_lower_secondary_program\n)\n\n_b131132_post_path = str(\n    post_lower_secondary_path or "CHUA_XAC_DINH"\n).strip().upper()\n\nif _b131132_post_path not in {\n    "CHUA_XAC_DINH",\n    "THPT",\n    "GDTX",\n    "GDNN",\n    "KHONG_HOC",\n}:\n    _b131132_post_path = "CHUA_XAC_DINH"\n\n{record}.post_lower_secondary_path = _b131132_post_path\n# === BAI_13B_11_13_2_SAVE_FIELDS_END ===\n'
PARAMS_ANNOTATED = '\n{indent}is_literacy_target: Annotated[str | None, Form()] = None,\n{indent}literacy_status: Annotated[str | None, Form()] = None,\n{indent}completed_grade_3: Annotated[str | None, Form()] = None,\n{indent}completed_grade_5: Annotated[str | None, Form()] = None,\n{indent}completed_primary_program: Annotated[str | None, Form()] = None,\n{indent}completed_lower_secondary_program: Annotated[str | None, Form()] = None,\n{indent}post_lower_secondary_path: Annotated[str | None, Form()] = None,\n'
PARAMS_CLASSIC = '\n{indent}is_literacy_target: str | None = Form(None),\n{indent}literacy_status: str | None = Form(None),\n{indent}completed_grade_3: str | None = Form(None),\n{indent}completed_grade_5: str | None = Form(None),\n{indent}completed_primary_program: str | None = Form(None),\n{indent}completed_lower_secondary_program: str | None = Form(None),\n{indent}post_lower_secondary_path: str | None = Form(None),\n'

PY_START = "# === BAI_13B_11_13_2_SAVE_FIELDS_START ==="
PY_END = "# === BAI_13B_11_13_2_SAVE_FIELDS_END ==="
UI_START = "<!-- === BAI_13B_11_13_2_XMC_UI_START === -->"
LEVEL_START = "<!-- === BAI_13B_11_13_2_LEVEL_UI_START === -->"
DYNAMIC_START = "<!-- === BAI_13B_11_13_2_DYNAMIC_UI_START === -->"

REQUIRED_DB_COLUMNS = [
    "is_literacy_target",
    "literacy_status",
    "completed_grade_3",
    "completed_grade_5",
    "completed_primary_program",
    "completed_lower_secondary_program",
    "post_lower_secondary_path",
]

PRESCHOOL_FIELDS = [
    "completed_preschool_5",
    "completed_preschool_by_age",
    "attends_required_days",
    "attends_regularly",
    "prepared_vietnamese",
    "weight_monitored",
    "underweight",
    "height_monitored",
    "stunted",
]


def read_text(path: Path) -> str:
    if not path.exists():
        raise RuntimeError(f"Không tìm thấy tệp: {path}")
    return path.read_text(encoding="utf-8-sig")


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def backup_file(path: Path) -> Path:
    dst = BACKUP / path.relative_to(PROJECT)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, dst)
    return dst


def restore_file(path: Path) -> None:
    src = BACKUP / path.relative_to(PROJECT)
    if src.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, path)


def sqlite_backup(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(str(source))
    dst = sqlite3.connect(str(target))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()


def db_columns() -> set[str]:
    conn = sqlite3.connect(str(DB_PATH))
    try:
        rows = conn.execute(
            "PRAGMA table_info(survey_person_year_records)"
        ).fetchall()
        return {str(row[1]) for row in rows}
    finally:
        conn.close()


def find_save_route() -> tuple[Path, ast.FunctionDef | ast.AsyncFunctionDef]:
    matches = []

    for path in ROUTERS.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue

        try:
            text = read_text(path)
            tree = ast.parse(text)
        except Exception:
            continue

        for node in ast.walk(tree):
            if not isinstance(
                node,
                (ast.FunctionDef, ast.AsyncFunctionDef),
            ):
                continue

            for dec in node.decorator_list:
                if not isinstance(dec, ast.Call):
                    continue

                method_name = None
                if isinstance(dec.func, ast.Attribute):
                    method_name = dec.func.attr
                elif isinstance(dec.func, ast.Name):
                    method_name = dec.func.id

                if str(method_name or "").lower() != "post":
                    continue

                if not dec.args:
                    continue

                route_value = dec.args[0]

                if not (
                    isinstance(route_value, ast.Constant)
                    and isinstance(route_value.value, str)
                ):
                    continue

                route = route_value.value

                if (
                    "nam-hoc/luu" in route
                    and "doi-tuong" in route
                ):
                    matches.append((path, node))

    if len(matches) != 1:
        detail = "\n".join(
            f" - {p.relative_to(PROJECT)}::{n.name}"
            for p, n in matches
        )
        raise RuntimeError(
            "Phải tìm thấy đúng 1 route POST /nam-hoc/luu. "
            f"Hiện tìm thấy {len(matches)}.\n{detail}"
        )

    return matches[0]


def owner_from_target(target: ast.AST) -> str | None:
    if (
        isinstance(target, ast.Attribute)
        and isinstance(target.value, ast.Name)
    ):
        return target.value.id

    return None


def find_record_variable(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> tuple[str, int]:
    scores = Counter()
    first_lines: dict[str, int] = {}

    important_attrs = {
        "learning_status",
        "completed_preschool_5",
        "completed_preschool_by_age",
        "disability_status",
        "school_id",
        "class_id",
        "notes",
    }

    for item in ast.walk(node):
        if isinstance(item, ast.Assign):
            targets = item.targets
        elif isinstance(item, ast.AnnAssign):
            targets = [item.target]
        else:
            targets = []

        for target in targets:
            owner = owner_from_target(target)

            if (
                owner
                and isinstance(target, ast.Attribute)
                and target.attr in important_attrs
            ):
                scores[owner] += 3
                first_lines.setdefault(owner, item.lineno)

        if isinstance(item, ast.Assign):
            if (
                isinstance(item.value, ast.Call)
                and len(item.targets) == 1
                and isinstance(item.targets[0], ast.Name)
            ):
                call_name = None

                if isinstance(item.value.func, ast.Name):
                    call_name = item.value.func.id
                elif isinstance(item.value.func, ast.Attribute):
                    call_name = item.value.func.attr

                if call_name == "SurveyPersonYearRecord":
                    name = item.targets[0].id
                    scores[name] += 10
                    first_lines.setdefault(name, item.lineno)

    if not scores:
        raise RuntimeError(
            "Không xác định được biến SurveyPersonYearRecord trong route lưu."
        )

    best_score = max(scores.values())
    best = [
        name
        for name, score in scores.items()
        if score == best_score
    ]

    if len(best) != 1:
        raise RuntimeError(
            "Có nhiều biến bản ghi năm học cùng mức tin cậy: "
            + ", ".join(best)
        )

    name = best[0]
    return name, int(first_lines.get(name, node.lineno))


def find_commit_line(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    after_line: int,
) -> int:
    lines = []

    for item in ast.walk(node):
        if not isinstance(item, ast.Call):
            continue

        if not isinstance(item.func, ast.Attribute):
            continue

        if item.func.attr != "commit":
            continue

        if item.lineno > after_line:
            lines.append(item.lineno)

    if not lines:
        raise RuntimeError(
            "Không tìm thấy db.commit() sau phần xử lý bản ghi năm học."
        )

    return min(lines)


def function_header_end_line(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> int:
    if not node.body:
        raise RuntimeError("Route lưu không có body.")

    return int(node.body[0].lineno) - 1


def parameter_indent(
    lines: list[str],
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    header_end: int,
) -> str:
    # Tìm indentation của các tham số hiện có.
    for line_no in range(node.lineno + 1, header_end + 1):
        line = lines[line_no - 1]

        if not line.strip():
            continue

        stripped = line.lstrip()

        if stripped.startswith(")"):
            continue

        return line[: len(line) - len(stripped)]

    # fallback: indent body
    body_line = lines[node.body[0].lineno - 1]
    body_indent = body_line[: len(body_line) - len(body_line.lstrip())]
    return body_indent


def patch_router(
    path: Path,
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> str:
    text = read_text(path)

    if PY_START in text:
        print(" - Backend 13B-11.13.2 đã có sẵn.")
        return text

    record_name, record_line = find_record_variable(node)
    commit_line = find_commit_line(node, record_line)
    header_end = function_header_end_line(node)

    lines = text.splitlines(keepends=True)

    header_text = "".join(
        lines[node.lineno - 1 : header_end]
    )

    for name in REQUIRED_DB_COLUMNS:
        if re.search(rf"\b{name}\s*:", header_text):
            raise RuntimeError(
                f"Route đã có tham số {name} nhưng chưa có marker 13B-11.13.2."
            )

    indent = parameter_indent(
        lines,
        node,
        header_end,
    )

    if "Annotated[" in header_text and "Form()" in header_text:
        params = PARAMS_ANNOTATED.format(indent=indent)
    else:
        params = PARAMS_CLASSIC.format(indent=indent)

    # Vị trí chèn tham số: ngay trước dòng đóng header "):".
    close_index = None

    for line_no in range(header_end, node.lineno - 1, -1):
        stripped = lines[line_no - 1].strip()

        if stripped.endswith("):") or stripped == "):":
            close_index = line_no - 1
            break

    if close_index is None:
        raise RuntimeError(
            "Không xác định được dòng đóng phần khai báo route lưu."
        )

    commit_indent = (
        lines[commit_line - 1][
            : len(lines[commit_line - 1])
            - len(lines[commit_line - 1].lstrip())
        ]
    )

    save_block = SAVE_BLOCK_TEMPLATE.format(
        record=record_name
    )

    save_block = "\n".join(
        (
            commit_indent + line
            if line.strip()
            else ""
        )
        for line in save_block.strip("\n").splitlines()
    ) + "\n\n"

    # Chèn từ dưới lên để số dòng cũ không bị lệch.
    lines.insert(
        commit_line - 1,
        save_block,
    )
    lines.insert(
        close_index,
        params,
    )

    patched = "".join(lines)
    ast.parse(patched)

    return patched


def find_disability_group_start(text: str) -> int:
    markers = [
        'id="disability_status"',
        'name="disability_status"',
    ]

    positions = [
        text.find(marker)
        for marker in markers
        if text.find(marker) >= 0
    ]

    if not positions:
        raise RuntimeError(
            "Không tìm thấy trường disability_status trong year_records.html."
        )

    pos = min(positions)

    # Tìm form-group bắt đầu gần nhất phía trước.
    candidates = [
        text.rfind('<div class="form-group full"', 0, pos),
        text.rfind("<div class='form-group full'", 0, pos),
        text.rfind('<div class="form-group"', 0, pos),
        text.rfind("<div class='form-group'", 0, pos),
    ]

    candidates = [value for value in candidates if value >= 0]

    if not candidates:
        raise RuntimeError(
            "Không xác định được đầu nhóm Theo dõi khuyết tật."
        )

    return max(candidates)


def patch_template(text: str) -> str:
    if UI_START in text:
        print(" - UI XMC 13B-11.13.2 đã có sẵn.")
        return text

    before_counts = {
        name: text.count(name)
        for name in PRESCHOOL_FIELDS
    }

    form_id_pos = text.find('id="year_record_form"')
    if form_id_pos < 0:
        raise RuntimeError(
            "Không tìm thấy year_record_form."
        )

    form_grid_pos = text.find(
        '<div class="form-grid">',
        form_id_pos,
    )

    if form_grid_pos < 0:
        raise RuntimeError(
            "Không tìm thấy form-grid của year_record_form."
        )

    form_grid_end = form_grid_pos + len(
        '<div class="form-grid">'
    )

    # XMC là nội dung đầu tiên trong form-grid.
    text = (
        text[:form_grid_end]
        + "\n"
        + XMC_BLOCK
        + text[form_grid_end:]
    )

    if LEVEL_START not in text:
        disability_start = find_disability_group_start(
            text
        )

        text = (
            text[:disability_start]
            + LEVEL_BLOCK
            + "\n"
            + text[disability_start:]
        )

    if DYNAMIC_START not in text:
        body_end = text.lower().rfind("</body>")

        if body_end < 0:
            raise RuntimeError(
                "Không tìm thấy </body> trong year_records.html."
            )

        text = (
            text[:body_end]
            + "\n"
            + STYLE_AND_SCRIPT
            + "\n"
            + text[body_end:]
        )

    # Bảo đảm không sửa/xóa field Mầm non cũ.
    after_counts = {
        name: text.count(name)
        for name in PRESCHOOL_FIELDS
    }

    for name in PRESCHOOL_FIELDS:
        if after_counts[name] < before_counts[name]:
            raise RuntimeError(
                f"Phát hiện giảm field Mầm non {name}; dừng cài đặt."
            )

    return text


def verify_router(path: Path) -> None:
    text = read_text(path)

    required = [
        PY_START,
        PY_END,
        "is_literacy_target",
        "literacy_status",
        "completed_grade_3",
        "completed_grade_5",
        "completed_primary_program",
        "completed_lower_secondary_program",
        "post_lower_secondary_path",
    ]

    for marker in required:
        if marker not in text:
            raise RuntimeError(
                f"Backend thiếu sau cài: {marker}"
            )

    ast.parse(text)

    result = subprocess.run(
        [sys.executable, "-m", "py_compile", str(path)],
        cwd=PROJECT,
        capture_output=True,
        text=True,
    )

    if result.stdout:
        print(result.stdout.rstrip())

    if result.stderr:
        print(result.stderr.rstrip())

    if result.returncode != 0:
        raise RuntimeError(
            "py_compile route lưu không đạt."
        )


def verify_template() -> None:
    text = read_text(TEMPLATE)

    required = [
        UI_START,
        LEVEL_START,
        DYNAMIC_START,
        'name="is_literacy_target"',
        'name="literacy_status"',
        'name="completed_grade_3"',
        'name="completed_grade_5"',
        'name="completed_primary_program"',
        'name="completed_lower_secondary_program"',
        'name="post_lower_secondary_path"',
        "Các chỉ báo Tiểu học",
        "Các chỉ báo THCS",
        "Các chỉ báo mầm non",
    ]

    for marker in required:
        if marker not in text:
            raise RuntimeError(
                f"Template thiếu sau cài: {marker}"
            )

    from jinja2 import Environment

    Environment().parse(text)


def verify_db_schema() -> None:
    columns = db_columns()

    missing = [
        name
        for name in REQUIRED_DB_COLUMNS
        if name not in columns
    ]

    if missing:
        raise RuntimeError(
            "Database chưa có cột từ Bài 13B-11.13.1: "
            + ", ".join(missing)
        )

    conn = sqlite3.connect(str(DB_PATH))
    try:
        integrity = str(
            conn.execute(
                "PRAGMA integrity_check"
            ).fetchone()[0]
        )

        fk_total = len(
            conn.execute(
                "PRAGMA foreign_key_check"
            ).fetchall()
        )
    finally:
        conn.close()

    if integrity.lower() != "ok":
        raise RuntimeError(
            f"integrity_check không đạt: {integrity}"
        )

    if fk_total != 0:
        raise RuntimeError(
            f"foreign_key_check có {fk_total} lỗi."
        )


def clear_cache() -> None:
    for cache in APP.rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(
                cache,
                ignore_errors=True,
            )


def main() -> int:
    print("=" * 124)
    print(
        "BÀI 13B-11.13.2 - GIAO DIỆN THÔNG TIN NĂM HỌC ĐỘNG "
        "XMC + MN + TIỂU HỌC + THCS"
    )
    print("=" * 124)
    print()
    print("NGHIỆP VỤ:")
    print(
        " - Mục đầu tiên: Đối tượng điều tra Xóa mù chữ."
    )
    print(
        " - XMC = Có mới mở: Tình trạng XMC, Hoàn thành lớp 3, Hoàn thành lớp 5."
    )
    print(
        " - Tiểu học: Hoàn thành chương trình Tiểu học."
    )
    print(
        " - THCS: Hoàn thành chương trình THCS + Hướng học sau THCS."
    )
    print(
        " - Chỉ báo Mầm non hiện có GIỮ NGUYÊN, chỉ ẩn giao diện khi ngoài độ tuổi MN."
    )
    print(
        " - Nhóm tuổi tính từ năm sinh và năm học; không lưu cột tuổi."
    )
    print()
    print("AN TOÀN:")
    print(" - Không ALTER TABLE.")
    print(" - Không UPDATE dữ liệu khi cài.")
    print(
        " - Tự tìm đúng route POST có /nam-hoc/luu bằng AST."
    )
    print(
        " - Backup router, template và database trước khi sửa source."
    )
    print(
        " - py_compile + Jinja parse + integrity_check + foreign_key_check."
    )
    print(
        " - Nếu cài lỗi: tự khôi phục source; database không bị thay đổi."
    )
    print()

    verify_db_schema()

    router_path, route_node = find_save_route()

    print(
        "Route lưu phát hiện:",
        f"{router_path.relative_to(PROJECT)}::{route_node.name}",
    )

    BACKUP.mkdir(
        parents=True,
        exist_ok=False,
    )

    backup_file(router_path)
    backup_file(TEMPLATE)
    sqlite_backup(
        DB_PATH,
        BACKUP / "phocap.db",
    )

    print("Backup:", BACKUP)

    try:
        router_before = read_text(
            router_path
        )
        template_before = read_text(
            TEMPLATE
        )

        router_after = patch_router(
            router_path,
            route_node,
        )
        template_after = patch_template(
            template_before
        )

        write_text(
            router_path,
            router_after,
        )
        write_text(
            TEMPLATE,
            template_after,
        )

        verify_router(
            router_path
        )
        verify_template()
        verify_db_schema()
        clear_cache()

        print()
        print("KIỂM TRA SAU CÀI:")
        print(
            " - Route lưu 7 trường mới: OK"
        )
        print(
            " - XMC là mục đầu tiên: OK"
        )
        print(
            " - XMC Có/Không và 3 trường chi tiết: OK"
        )
        print(
            " - Chỉ báo Tiểu học: OK"
        )
        print(
            " - Chỉ báo THCS: OK"
        )
        print(
            " - Các field Mầm non cũ: GIỮ NGUYÊN"
        )
        print(
            " - Ẩn/hiện nhóm theo tuổi trên giao diện: OK"
        )
        print(
            " - py_compile backend: OK"
        )
        print(
            " - Jinja parse: OK"
        )
        print(
            " - integrity_check: OK"
        )
        print(
            " - foreign_key_check: 0 lỗi"
        )
        print(
            " - Database trong lúc cài: KHÔNG UPDATE"
        )
        print()
        print(
            "CÀI ĐẶT BÀI 13B-11.13.2 THÀNH CÔNG"
        )

        return 0

    except Exception:
        traceback.print_exc()

        print()
        print(
            "CÓ LỖI - ĐANG KHÔI PHỤC SOURCE..."
        )

        restore_file(
            router_path
        )
        restore_file(
            TEMPLATE
        )
        clear_cache()

        print(
            "ĐÃ KHÔI PHỤC ROUTER VÀ TEMPLATE."
        )
        print(
            "Database không bị thay đổi bởi bộ cài."
        )
        print(
            "Backup:",
            BACKUP,
        )

        return 1


if __name__ == "__main__":
    raise SystemExit(main())
