
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
MODEL = APP / "survey_models.py"
ROUTER = APP / "routers" / "surveys.py"
YEAR_TEMPLATE = APP / "templates" / "surveys" / "year_records.html"
QUICK_TEMPLATE = APP / "templates" / "surveys" / "quick_entry.html"
DATA_QUALITY_TEMPLATE = APP / "templates" / "surveys" / "data_quality.html"
DB = PROJECT / "data" / "phocap.db"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = PROJECT / "exports" / f"backup_bai_13b_11_14_2_1_{STAMP}"
DB_BACKUP = BACKUP / "data" / "phocap.db"

MODEL_MARKER = "# === BAI_13B_11_14_2_REPORT_DISABILITY_MODEL_START ==="
PROGRESS_MARKER = "# === BAI_13B_11_14_2_REPORT_PROGRESS_START ==="
SAVE_MARKER = "# === BAI_13B_11_14_2_REPORT_SAVE_START ==="

UI_START = "<!-- === BAI_13B_11_14_2_PCGDMN_REPORT_UI_START === -->"
UI_END = "<!-- === BAI_13B_11_14_2_PCGDMN_REPORT_UI_END === -->"
DISABILITY_UI_START = "<!-- === BAI_13B_11_14_2_DISABILITY_REPORT_UI_START === -->"
DISABILITY_UI_END = "<!-- === BAI_13B_11_14_2_DISABILITY_REPORT_UI_END === -->"

DB_REQUIRED = {
    "disability_can_learn",
    "disability_access_education",
    "attends_two_sessions_per_day",
}

LEGACY_NOT_REPORT_FIELDS = (
    "attends_required_days",
    "attends_regularly",
    "weight_monitored",
    "underweight",
    "height_monitored",
    "stunted",
)

REPORT_UI_BLOCK = r'''
                    <!-- === BAI_13B_11_14_2_PCGDMN_REPORT_UI_START === -->
                    <div
                        id="b131133_preschool_indicators"
                        class="form-group full"
                    >
                        <label>Chỉ báo phục vụ báo cáo PCGDMN</label>

                        <div class="form-note" style="margin-bottom:10px;">
                            Chỉ thu thập dữ liệu gốc cần cho bộ 7 sheet báo cáo.
                            Dữ liệu sức khỏe cũ vẫn được giữ trong CSDL nhưng
                            không còn dùng để chốt đủ dữ liệu PCGDMN.
                        </div>

                        <div class="indicator-grid">
                            <div class="indicator-item">
                                <label for="completed_preschool_by_age">
                                    1. Hoàn thành Chương trình GDMN theo độ tuổi (3-5 tuổi)
                                </label>
                                <select
                                    id="completed_preschool_by_age"
                                    name="completed_preschool_by_age"
                                    class="form-control"
                                >
                                    <option value=""
                                        {% if not selected_record or selected_record.completed_preschool_by_age is none %}selected{% endif %}
                                    >-- Chưa xác định --</option>
                                    <option value="1"
                                        {% if selected_record and selected_record.completed_preschool_by_age is sameas true %}selected{% endif %}
                                    >Có</option>
                                    <option value="0"
                                        {% if selected_record and selected_record.completed_preschool_by_age is sameas false %}selected{% endif %}
                                    >Không</option>
                                </select>
                                <small class="form-note">
                                    Áp dụng cho trẻ mẫu giáo 3, 4 và 5 tuổi.
                                </small>
                            </div>

                            <div class="indicator-item">
                                <label for="attends_two_sessions_per_day">
                                    2. Học 2 buổi/ngày
                                </label>
                                <select
                                    id="attends_two_sessions_per_day"
                                    name="attends_two_sessions_per_day"
                                    class="form-control"
                                >
                                    <option value=""
                                        {% if not selected_record or selected_record.attends_two_sessions_per_day is none %}selected{% endif %}
                                    >-- Chưa xác định --</option>
                                    <option value="1"
                                        {% if selected_record and selected_record.attends_two_sessions_per_day is sameas true %}selected{% endif %}
                                    >Có</option>
                                    <option value="0"
                                        {% if selected_record and selected_record.attends_two_sessions_per_day is sameas false %}selected{% endif %}
                                    >Không</option>
                                </select>
                                <small class="form-note">
                                    Nguồn trực tiếp cho MN-01-TE.
                                </small>
                            </div>

                            <div class="indicator-item">
                                <label for="prepared_vietnamese">
                                    3. Trẻ DTTS được chuẩn bị tiếng Việt
                                </label>
                                <select
                                    id="prepared_vietnamese"
                                    name="prepared_vietnamese"
                                    class="form-control"
                                >
                                    <option value=""
                                        {% if not selected_record or selected_record.prepared_vietnamese is none %}selected{% endif %}
                                    >-- Chưa xác định --</option>
                                    <option value="1"
                                        {% if selected_record and selected_record.prepared_vietnamese is sameas true %}selected{% endif %}
                                    >Có</option>
                                    <option value="0"
                                        {% if selected_record and selected_record.prepared_vietnamese is sameas false %}selected{% endif %}
                                    >Không</option>
                                </select>
                                <small class="form-note">
                                    Chỉ bắt buộc khi đối tượng là trẻ dân tộc thiểu số.
                                </small>
                            </div>
                        </div>
                    </div>
                    <!-- === BAI_13B_11_14_2_PCGDMN_REPORT_UI_END === -->
'''

DISABILITY_REPORT_UI = r'''
                                <!-- === BAI_13B_11_14_2_DISABILITY_REPORT_UI_START === -->
                                <div class="form-group">
                                    <label for="disability_can_learn">
                                        Có khả năng học tập
                                    </label>
                                    <select
                                        id="disability_can_learn"
                                        name="disability_can_learn"
                                        class="form-control"
                                    >
                                        <option value=""
                                            {% if not selected_record or selected_record.disability_can_learn is none %}selected{% endif %}
                                        >-- Chưa xác định --</option>
                                        <option value="1"
                                            {% if selected_record and selected_record.disability_can_learn is sameas true %}selected{% endif %}
                                        >Có</option>
                                        <option value="0"
                                            {% if selected_record and selected_record.disability_can_learn is sameas false %}selected{% endif %}
                                        >Không</option>
                                    </select>
                                    <small class="form-note">
                                        Nguồn cho MN-01-TE và tiêu chuẩn/điều kiện PCGDMN.
                                    </small>
                                </div>

                                <div class="form-group">
                                    <label for="disability_access_education">
                                        Được tiếp cận giáo dục
                                    </label>
                                    <select
                                        id="disability_access_education"
                                        name="disability_access_education"
                                        class="form-control"
                                    >
                                        <option value=""
                                            {% if not selected_record or selected_record.disability_access_education is none %}selected{% endif %}
                                        >-- Chưa xác định --</option>
                                        <option value="1"
                                            {% if selected_record and selected_record.disability_access_education is sameas true %}selected{% endif %}
                                        >Có</option>
                                        <option value="0"
                                            {% if selected_record and selected_record.disability_access_education is sameas false %}selected{% endif %}
                                        >Không</option>
                                    </select>
                                    <small class="form-note">
                                        Nguồn cho MN-01-TE, MN-05-KT và tiêu chuẩn/điều kiện.
                                    </small>
                                </div>
                                <!-- === BAI_13B_11_14_2_DISABILITY_REPORT_UI_END === -->
'''


def read_text(path: Path) -> str:
    if not path.exists():
        raise RuntimeError(f"Không tìm thấy: {path}")
    return path.read_text(encoding="utf-8-sig", errors="strict")


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def backup_file(path: Path) -> None:
    if not path.exists():
        return
    dst = BACKUP / path.relative_to(PROJECT)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, dst)


def restore_file(path: Path) -> None:
    src = BACKUP / path.relative_to(PROJECT)
    if src.exists():
        shutil.copy2(src, path)


def sqlite_backup(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(str(source))
    dst = sqlite3.connect(str(target))
    try:
        src.backup(dst)
        dst.commit()
    finally:
        dst.close()
        src.close()


def sqlite_restore(source: Path, target: Path) -> None:
    src = sqlite3.connect(str(source))
    dst = sqlite3.connect(str(target))
    try:
        src.backup(dst)
        dst.commit()
    finally:
        dst.close()
        src.close()


def db_state():
    conn = sqlite3.connect(str(DB))
    try:
        cols = {
            str(row[1])
            for row in conn.execute(
                "PRAGMA table_info(survey_person_year_records)"
            ).fetchall()
        }
        count = int(
            conn.execute(
                "SELECT COUNT(*) FROM survey_person_year_records"
            ).fetchone()[0]
        )
        integrity = str(
            conn.execute("PRAGMA integrity_check").fetchone()[0]
        )
        fk = len(
            conn.execute("PRAGMA foreign_key_check").fetchall()
        )
        return cols, count, integrity, fk
    finally:
        conn.close()


def clear_cache() -> None:
    for cache in APP.rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(cache, ignore_errors=True)


def assignment_name(node):
    if (
        isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
    ):
        return node.targets[0].id

    if (
        isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
    ):
        return node.target.id

    return None


def top_function(tree: ast.Module, name: str):
    nodes = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == name
    ]
    if len(nodes) != 1:
        raise RuntimeError(
            f"Phải tìm thấy đúng 1 hàm {name}; hiện có {len(nodes)}."
        )
    return nodes[0]


def function_span(text: str, name: str):
    tree = ast.parse(text)
    node = top_function(tree, name)
    lines = text.splitlines(keepends=True)

    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))

    return (
        offsets[int(node.lineno) - 1],
        offsets[int(node.end_lineno)],
    )


def get_function(text: str, name: str) -> str:
    start, end = function_span(text, name)
    return text[start:end]


def replace_function(text: str, name: str, new_fn: str) -> str:
    start, end = function_span(text, name)
    patched = text[:start] + new_fn.rstrip() + "\n\n" + text[end:].lstrip("\n")
    ast.parse(patched)
    return patched


def patch_model(text: str) -> str:
    tree = ast.parse(text)
    classes = [
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef)
        and node.name == "SurveyPersonYearRecord"
    ]

    if len(classes) != 1:
        raise RuntimeError(
            "Phải có đúng 1 class SurveyPersonYearRecord."
        )

    cls = classes[0]
    existing = {
        assignment_name(node)
        for node in cls.body
    }

    needed = {
        "disability_can_learn",
        "disability_access_education",
    }

    missing = needed - existing

    if not missing:
        return text

    anchor = next(
        (
            node
            for node in cls.body
            if assignment_name(node) == "disability_status"
        ),
        None,
    )

    if anchor is None:
        raise RuntimeError(
            "Không tìm thấy disability_status trong model."
        )

    lines = text.splitlines(keepends=True)

    block = [
        "",
        "    # === BAI_13B_11_14_2_REPORT_DISABILITY_MODEL_START ===",
    ]

    if "disability_can_learn" in missing:
        block += [
            "    disability_can_learn: Mapped[bool | None] = mapped_column(",
            "        Boolean,",
            "        nullable=True,",
            "    )",
            "",
        ]

    if "disability_access_education" in missing:
        block += [
            "    disability_access_education: Mapped[bool | None] = mapped_column(",
            "        Boolean,",
            "        nullable=True,",
            "    )",
        ]

    block += [
        "    # === BAI_13B_11_14_2_REPORT_DISABILITY_MODEL_END ===",
        "",
    ]

    lines.insert(
        int(anchor.end_lineno),
        "\n".join(block) + "\n",
    )

    patched = "".join(lines)
    ast.parse(patched)
    return patched


def replace_top_tuple(
    text: str,
    variable: str,
    values: tuple[str, ...],
) -> str:
    tree = ast.parse(text)

    nodes = [
        node
        for node in tree.body
        if isinstance(node, (ast.Assign, ast.AnnAssign))
        and assignment_name(node) == variable
    ]

    if len(nodes) != 1:
        raise RuntimeError(
            f"Phải có đúng 1 {variable}; hiện có {len(nodes)}."
        )

    node = nodes[0]
    lines = text.splitlines(keepends=True)
    original = lines[int(node.lineno) - 1]
    indent = original[: len(original) - len(original.lstrip())]

    new_lines = [f"{indent}{variable} = (\n"]
    for value in values:
        new_lines.append(f'{indent}    "{value}",\n')
    new_lines.append(f"{indent})\n")

    lines[
        int(node.lineno) - 1 : int(node.end_lineno)
    ] = new_lines

    patched = "".join(lines)
    ast.parse(patched)
    return patched


def patch_progress(text: str) -> str:
    text = replace_top_tuple(
        text,
        "B131133_MN_FIELDS",
        (
            "completed_preschool_by_age",
            "attends_two_sessions_per_day",
        ),
    )

    fn = get_function(
        text,
        "b131133_tien_do_nam_hoc",
    )

    if PROGRESS_MARKER in fn:
        return text

    old = (
        '    if level == "MN":\n'
        '        required_fields.extend(B131133_MN_FIELDS)\n'
        '    elif level == "TH":\n'
    )

    new = (
        '    if level == "MN":\n'
        '        # === BAI_13B_11_14_2_REPORT_PROGRESS_START ===\n'
        '        required_fields.extend(B131133_MN_FIELDS)\n'
        '        required_fields.append("disability_status")\n'
        '\n'
        '        ethnic_key = b131133_chuan_hoa_khong_dau(\n'
        '            getattr(person, "ethnic_group", None)\n'
        '        )\n'
        '\n'
        '        if (\n'
        '            ethnic_key\n'
        '            and ethnic_key not in {"KINH", "DAN TOC KINH"}\n'
        '        ):\n'
        '            required_fields.append("prepared_vietnamese")\n'
        '\n'
        '        disability_status_value = (\n'
        '            getattr(record, "disability_status", None)\n'
        '            if record is not None\n'
        '            else None\n'
        '        )\n'
        '\n'
        '        if disability_status_value == "CO_KHUYET_TAT":\n'
        '            required_fields.extend(\n'
        '                (\n'
        '                    "disability_type",\n'
        '                    "disability_can_learn",\n'
        '                    "disability_access_education",\n'
        '                )\n'
        '            )\n'
        '        # === BAI_13B_11_14_2_REPORT_PROGRESS_END ===\n'
        '    elif level == "TH":\n'
    )

    if old not in fn:
        raise RuntimeError(
            "Không tìm thấy khối tiến độ MN cũ."
        )

    fn = fn.replace(old, new, 1)

    return replace_function(
        text,
        "b131133_tien_do_nam_hoc",
        fn,
    )


def patch_route_params(fn: str) -> str:
    if (
        "disability_can_learn:"
        in fn
        and "disability_access_education:"
        in fn
    ):
        return fn

    anchor = (
        '    disability_status: Annotated[str, Form()] '
        '= "CHUA_XAC_DINH",\n'
    )

    if anchor not in fn:
        raise RuntimeError(
            "Không tìm thấy tham số disability_status."
        )

    extra = (
        '    disability_can_learn: Annotated[str, Form()] = "",\n'
        '    disability_access_education: Annotated[str, Form()] = "",\n'
    )

    return fn.replace(
        anchor,
        anchor + extra,
        1,
    )


def patch_tri_state(fn: str) -> str:
    if (
        '"disability_can_learn": ('
        in fn
        and '"disability_access_education": ('
        in fn
    ):
        return fn

    start = fn.find(
        "    tri_state_inputs = {"
    )

    if start < 0:
        raise RuntimeError(
            "Không tìm thấy tri_state_inputs."
        )

    end_anchor = fn.find(
        "    parsed_tri_state:",
        start,
    )

    if end_anchor < 0:
        raise RuntimeError(
            "Không tìm thấy parsed_tri_state."
        )

    block = fn[start:end_anchor]
    close = block.rfind(
        "    }\n"
    )

    if close < 0:
        raise RuntimeError(
            "Không tìm thấy cuối tri_state_inputs."
        )

    addition = (
        '        "disability_can_learn": (\n'
        '            disability_can_learn,\n'
        '            "Khuyết tật có khả năng học tập",\n'
        '        ),\n'
        '        "disability_access_education": (\n'
        '            disability_access_education,\n'
        '            "Khuyết tật được tiếp cận giáo dục",\n'
        '        ),\n'
    )

    block = (
        block[:close]
        + addition
        + block[close:]
    )

    return (
        fn[:start]
        + block
        + fn[end_anchor:]
    )


def patch_save_values(fn: str) -> str:
    if SAVE_MARKER not in fn:
        anchor = (
            "    if disability_status "
            "not in DISABILITY_STATUS_LABELS:\n"
        )

        pos = fn.find(anchor)

        if pos < 0:
            raise RuntimeError(
                "Không tìm thấy kiểm tra disability_status."
            )

        block = (
            "    # === BAI_13B_11_14_2_REPORT_SAVE_START ===\n"
            '    disability_can_learn_value = parsed_tri_state.get(\n'
            '        "disability_can_learn"\n'
            "    )\n"
            '    disability_access_education_value = parsed_tri_state.get(\n'
            '        "disability_access_education"\n'
            "    )\n"
            "\n"
            '    if disability_status != "CO_KHUYET_TAT":\n'
            "        disability_can_learn_value = None\n"
            "        disability_access_education_value = None\n"
            "    # === BAI_13B_11_14_2_REPORT_SAVE_END ===\n"
            "\n"
        )

        fn = fn[:pos] + block + fn[pos:]

    # Không ghi None đè dữ liệu cũ của các trường đã bỏ khỏi UI.
    for prefix in ("form_record", "record"):
        for field in LEGACY_NOT_REPORT_FIELDS:
            pattern = re.compile(
                rf"^[ \t]*{prefix}\.{field}[ \t]*=.*?\n",
                re.MULTILINE,
            )
            fn = pattern.sub("", fn)

    if "form_record.disability_can_learn" not in fn:
        anchor = (
            "        form_record.special_circumstances "
            "= special_circumstances or None\n"
        )

        if anchor in fn:
            fn = fn.replace(
                anchor,
                (
                    "        form_record.disability_can_learn "
                    "= disability_can_learn_value\n"
                    "        form_record.disability_access_education "
                    "= disability_access_education_value\n"
                    + anchor
                ),
                1,
            )

    if "record.disability_can_learn" not in fn:
        anchor = (
            "    record.special_circumstances "
            "= special_circumstances or None\n"
        )

        if anchor not in fn:
            anchor = "    record.notes = notes or None\n"

        if anchor not in fn:
            raise RuntimeError(
                "Không tìm thấy vị trí gán vào record."
            )

        fn = fn.replace(
            anchor,
            (
                "    record.disability_can_learn "
                "= disability_can_learn_value\n"
                "    record.disability_access_education "
                "= disability_access_education_value\n"
                + anchor
            ),
            1,
        )

    ast.parse(fn)
    return fn


def patch_save_route(text: str) -> str:
    fn = get_function(
        text,
        "luu_theo_doi_nam_hoc",
    )

    fn = patch_route_params(fn)
    fn = patch_tri_state(fn)
    fn = patch_save_values(fn)

    return replace_function(
        text,
        "luu_theo_doi_nam_hoc",
        fn,
    )


def patch_mobile_copy(text: str) -> str:
    name = "chap_nhan_thanh_vien_nhap_nhanh_mobile"

    try:
        fn = get_function(text, name)
    except RuntimeError:
        return text

    if (
        '"disability_can_learn"'
        in fn
        and '"disability_access_education"'
        in fn
    ):
        return text

    anchor = '        "disability_status",\n'

    if anchor not in fn:
        return text

    fn = fn.replace(
        anchor,
        (
            anchor
            + '        "disability_can_learn",\n'
            + '        "disability_access_education",\n'
        ),
        1,
    )

    return replace_function(text, name, fn)


def find_matching_div_end(
    text: str,
    start: int,
) -> int:
    token = re.compile(
        r"<div\b[^>]*>|</div>",
        re.IGNORECASE,
    )

    depth = 0

    for match in token.finditer(text, start):
        item = match.group(0).lower()

        if item.startswith("<div"):
            depth += 1
        else:
            depth -= 1
            if depth == 0:
                return match.end()

    raise RuntimeError(
        "Không tìm thấy </div> khớp."
    )


def locate_div_by_id(
    text: str,
    element_id: str,
):
    marker = f'id="{element_id}"'
    pos = text.find(marker)

    if pos < 0:
        raise RuntimeError(
            f"Không tìm thấy id={element_id}."
        )

    start = text.rfind(
        "<div",
        0,
        pos,
    )

    if start < 0:
        raise RuntimeError(
            f"Không tìm thấy div của {element_id}."
        )

    end = find_matching_div_end(
        text,
        start,
    )

    return start, end


def patch_template(text: str) -> str:
    if UI_START not in text:
        start, end = locate_div_by_id(
            text,
            "b131133_preschool_indicators",
        )

        text = (
            text[:start]
            + REPORT_UI_BLOCK.strip("\n")
            + text[end:]
        )

    if DISABILITY_UI_START not in text:
        start, end = locate_div_by_id(
            text,
            "disability_details",
        )

        block = text[start:end]

        match = re.search(
            r'<div\s+class="disability-grid"[^>]*>',
            block,
            flags=re.IGNORECASE,
        )

        if match is None:
            raise RuntimeError(
                "Không tìm thấy disability-grid."
            )

        insert_at = start + match.end()

        text = (
            text[:insert_at]
            + "\n"
            + DISABILITY_REPORT_UI.strip("\n")
            + "\n"
            + text[insert_at:]
        )

    text = text.replace(
        (
            "Khi chọn “Có khuyết tật”, cần xác định "
            "dạng và mức độ khuyết tật."
        ),
        (
            "Khi chọn “Có khuyết tật”, cần xác định "
            "dạng tật, khả năng học tập và khả năng tiếp cận giáo dục."
        ),
    )

    return text


def patch_messages(text: str) -> str:
    for old, new in (
        (
            "chưa đủ 8 chỉ báo",
            "chưa hoàn thành thông tin báo cáo",
        ),
        (
            "chưa đủ 9 chỉ báo",
            "chưa hoàn thành thông tin báo cáo",
        ),
        (
            "đủ 8 chỉ báo",
            "đủ thông tin báo cáo",
        ),
        (
            "đủ 9 chỉ báo",
            "đủ thông tin báo cáo",
        ),
        (
            "Thiếu chỉ báo:",
            "Thiếu thông tin báo cáo:",
        ),
    ):
        text = text.replace(old, new)

    return text


def compile_py(path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "py_compile",
            str(path),
        ],
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
            f"py_compile không đạt: {path}"
        )


def verify(count_before: int) -> None:
    model = read_text(MODEL)
    router = read_text(ROUTER)
    template = read_text(YEAR_TEMPLATE)

    for field in (
        "disability_can_learn",
        "disability_access_education",
    ):
        if field not in model:
            raise RuntimeError(
                f"Model thiếu {field}."
            )
        if field not in router:
            raise RuntimeError(
                f"Router thiếu {field}."
            )
        if f'name="{field}"' not in template:
            raise RuntimeError(
                f"Template thiếu {field}."
            )

    for marker in (
        UI_START,
        UI_END,
        DISABILITY_UI_START,
        DISABILITY_UI_END,
        PROGRESS_MARKER,
        SAVE_MARKER,
    ):
        if marker not in (router + template):
            raise RuntimeError(
                "Thiếu marker: " + marker
            )

    start = template.find(UI_START)
    end = template.find(UI_END, start)
    ui = template[start : end + len(UI_END)]

    for field in LEGACY_NOT_REPORT_FIELDS:
        if f'name="{field}"' in ui:
            raise RuntimeError(
                "Khối PCGDMN vẫn còn: " + field
            )

    for field in (
        "completed_preschool_by_age",
        "attends_two_sessions_per_day",
        "prepared_vietnamese",
    ):
        if f'name="{field}"' not in ui:
            raise RuntimeError(
                "Khối PCGDMN thiếu: " + field
            )

    progress_fn = get_function(
        router,
        "b131133_tien_do_nam_hoc",
    )

    # BÀI 13B-11.14.2.1:
    # Hai field nền Mầm non nằm trong B131133_MN_FIELDS,
    # không xuất hiện trực tiếp trong thân hàm tiến độ.
    # Vì vậy phải kiểm tra đúng nơi khai báo tuple thay vì
    # tìm chuỗi trực tiếp trong progress_fn.
    tree = ast.parse(router)
    mn_tuple_node = next(
        (
            node
            for node in tree.body
            if isinstance(node, (ast.Assign, ast.AnnAssign))
            and assignment_name(node) == "B131133_MN_FIELDS"
        ),
        None,
    )

    if mn_tuple_node is None:
        raise RuntimeError(
            "Không tìm thấy B131133_MN_FIELDS."
        )

    mn_tuple_source = (
        ast.get_source_segment(
            router,
            mn_tuple_node,
        )
        or ""
    )

    for field in (
        "completed_preschool_by_age",
        "attends_two_sessions_per_day",
    ):
        if field not in mn_tuple_source:
            raise RuntimeError(
                "B131133_MN_FIELDS thiếu: " + field
            )

    for field in (
        "disability_status",
        "prepared_vietnamese",
        "disability_type",
        "disability_can_learn",
        "disability_access_education",
    ):
        if field not in progress_fn:
            raise RuntimeError(
                "Tiến độ thiếu: " + field
            )

    if "required_fields.extend(B131133_MN_FIELDS)" not in progress_fn:
        raise RuntimeError(
            "Hàm tiến độ chưa sử dụng B131133_MN_FIELDS."
        )

    compile_py(MODEL)
    compile_py(ROUTER)

    from jinja2 import Environment

    Environment().parse(template)

    for path in (
        QUICK_TEMPLATE,
        DATA_QUALITY_TEMPLATE,
    ):
        if path.exists():
            Environment().parse(read_text(path))

    cols, count_after, integrity, fk = db_state()

    if DB_REQUIRED - cols:
        raise RuntimeError(
            "Database thiếu: "
            + ", ".join(
                sorted(DB_REQUIRED - cols)
            )
        )

    if count_after != count_before:
        raise RuntimeError(
            f"Số bản ghi thay đổi: {count_before} -> {count_after}"
        )

    if integrity.lower() != "ok":
        raise RuntimeError(
            f"integrity_check: {integrity}"
        )

    if fk != 0:
        raise RuntimeError(
            f"foreign_key_check có {fk} lỗi"
        )


def main() -> int:
    print("=" * 124)
    print(
        "BÀI 13B-11.14.2.1 - "
        "THAY CHỈ BÁO MẦM NON BẰNG CHỈ BÁO PHỤC VỤ 7 SHEET PCGDMN"
    )
    print("=" * 124)
    print()
    print("GIAO DIỆN PCGDMN:")
    print(" 1. Hoàn thành Chương trình GDMN theo độ tuổi.")
    print(" 2. Học 2 buổi/ngày.")
    print(" 3. Trẻ DTTS được chuẩn bị tiếng Việt.")
    print()
    print("KHI CÓ KHUYẾT TẬT:")
    print(" - Dạng tật.")
    print(" - Có khả năng học tập.")
    print(" - Được tiếp cận giáo dục.")
    print()
    print("BỎ KHỎI GIAO DIỆN/CHỐT PCGDMN:")
    print(" - Đi học đủ ngày theo quy định.")
    print(" - Đi học chuyên cần.")
    print(" - Theo dõi cân nặng.")
    print(" - Suy dinh dưỡng nhẹ cân.")
    print(" - Theo dõi chiều cao.")
    print(" - Suy dinh dưỡng thấp còi.")
    print()
    print("AN TOÀN:")
    print(" - Không xóa cột hoặc dữ liệu cũ.")
    print(" - Không ghi None đè dữ liệu cũ đã bỏ khỏi giao diện.")
    print(" - Không thay schema database.")
    print(" - Backup source + database; lỗi sẽ rollback.")
    print(" - V14.2.1 sửa kiểm tra B131133_MN_FIELDS; không đổi nghiệp vụ V14.2.")
    print()

    for path in (
        MODEL,
        ROUTER,
        YEAR_TEMPLATE,
        DB,
    ):
        if not path.exists():
            raise RuntimeError(
                f"Không tìm thấy: {path}"
            )

    cols, count_before, integrity, fk = db_state()

    missing = DB_REQUIRED - cols

    if missing:
        raise RuntimeError(
            "Chưa đủ nền dữ liệu. Thiếu: "
            + ", ".join(sorted(missing))
        )

    if integrity.lower() != "ok" or fk != 0:
        raise RuntimeError(
            "Database không đạt kiểm tra trước cài."
        )

    BACKUP.mkdir(
        parents=True,
        exist_ok=False,
    )

    for path in (
        MODEL,
        ROUTER,
        YEAR_TEMPLATE,
        QUICK_TEMPLATE,
        DATA_QUALITY_TEMPLATE,
    ):
        backup_file(path)

    sqlite_backup(DB, DB_BACKUP)

    print("Backup:", BACKUP)
    print(
        "survey_person_year_records trước cài:",
        count_before,
    )

    try:
        model_text = patch_model(
            read_text(MODEL)
        )

        router_text = read_text(ROUTER)
        router_text = patch_progress(router_text)
        router_text = patch_save_route(router_text)
        router_text = patch_mobile_copy(router_text)

        template_text = patch_template(
            read_text(YEAR_TEMPLATE)
        )

        ast.parse(model_text)
        ast.parse(router_text)

        from jinja2 import Environment
        Environment().parse(template_text)

        write_text(MODEL, model_text)
        write_text(ROUTER, router_text)
        write_text(YEAR_TEMPLATE, template_text)

        for path in (
            QUICK_TEMPLATE,
            DATA_QUALITY_TEMPLATE,
        ):
            if path.exists():
                write_text(
                    path,
                    patch_messages(read_text(path)),
                )

        verify(count_before)
        clear_cache()

        print()
        print("KIỂM TRA SAU CÀI:")
        print(" - Model 2 trường khuyết tật báo cáo: OK")
        print(" - Route lưu dữ liệu mới: OK")
        print(" - Không ghi đè dữ liệu sức khỏe/chuyên cần cũ: OK")
        print(" - Giao diện PCGDMN mới: OK")
        print(" - Tiến độ/chốt dữ liệu theo đúng nhóm: OK")
        print(" - DTTS mới yêu cầu Chuẩn bị tiếng Việt: OK")
        print(
            " - Khuyết tật yêu cầu "
            "Dạng tật + Khả năng học tập + Tiếp cận giáo dục: OK"
        )
        print(" - py_compile + Jinja: OK")
        print(" - Database: KHÔNG THAY ĐỔI")
        print(
            " - Dữ liệu năm học giữ nguyên:",
            count_before,
            "bản ghi",
        )
        print(" - integrity_check: OK")
        print(" - foreign_key_check: 0 lỗi")
        print()
        print("=" * 124)
        print(
            "CÀI ĐẶT BÀI 13B-11.14.2.1 THÀNH CÔNG"
        )
        print("=" * 124)

        return 0

    except Exception:
        traceback.print_exc()

        print()
        print(
            "CÓ LỖI - ĐANG KHÔI PHỤC SOURCE VÀ DATABASE..."
        )

        for path in (
            MODEL,
            ROUTER,
            YEAR_TEMPLATE,
            QUICK_TEMPLATE,
            DATA_QUALITY_TEMPLATE,
        ):
            try:
                restore_file(path)
            except Exception as exc:
                print(
                    " - Lỗi khôi phục",
                    path,
                    exc,
                )

        try:
            sqlite_restore(DB_BACKUP, DB)
            print(" - Đã khôi phục database.")
        except Exception as exc:
            print(
                " - Lỗi khôi phục database:",
                exc,
            )

        clear_cache()
        print("Backup:", BACKUP)

        return 1


if __name__ == "__main__":
    raise SystemExit(main())
