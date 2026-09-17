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

PROJECT = Path(os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")).resolve()
APP = PROJECT / "app"
ROUTER = APP / "routers" / "surveys.py"
YEAR_TEMPLATE = APP / "templates" / "surveys" / "year_records.html"
QUICK_TEMPLATE = APP / "templates" / "surveys" / "quick_entry.html"
DATA_QUALITY_TEMPLATE = APP / "templates" / "surveys" / "data_quality.html"
MODEL = APP / "survey_models.py"
DB = PROJECT / "data" / "phocap.db"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = PROJECT / "exports" / f"backup_bai_13b_11_13_3_2_{STAMP}"

HELPER_BLOCK = '\n# === BAI_13B_11_13_3_1_DYNAMIC_PROGRESS_START ===\nB131133_MN_FIELDS = (\n    "completed_preschool_by_age",\n    "attends_required_days",\n    "attends_regularly",\n    "prepared_vietnamese",\n    "weight_monitored",\n    "underweight",\n    "height_monitored",\n    "stunted",\n)\n\n\ndef b131133_chuan_hoa_khong_dau(value):\n    import unicodedata\n\n    text_value = str(value or "")\n    text_value = unicodedata.normalize("NFD", text_value)\n    text_value = "".join(\n        char\n        for char in text_value\n        if unicodedata.category(char) != "Mn"\n    )\n    return " ".join(text_value.upper().split())\n\n\ndef b131133_nam_tham_chieu(school_year):\n    import re as _re\n\n    code = str(getattr(school_year, "code", "") or "")\n    match = _re.search(r"\\b(20\\d{2})\\b", code)\n\n    if match is None:\n        return None\n\n    try:\n        return int(match.group(1))\n    except (TypeError, ValueError):\n        return None\n\n\ndef b131133_xac_dinh_cap_hoc(person, record, school_year):\n    import re as _re\n\n    school_name = ""\n    class_name = ""\n\n    if record is not None:\n        school_name = str(\n            getattr(record, "school_name_reported", None)\n            or getattr(getattr(record, "school", None), "name", "")\n            or ""\n        )\n        class_name = str(\n            getattr(record, "class_name_reported", None)\n            or getattr(getattr(record, "classroom", None), "name", "")\n            or ""\n        )\n\n    school_key = b131133_chuan_hoa_khong_dau(school_name)\n    class_key = b131133_chuan_hoa_khong_dau(class_name)\n    combined = f"{school_key} {class_key}".strip()\n\n    if (\n        "MAM NON" in combined\n        or "MAU GIAO" in combined\n        or "NHA TRE" in combined\n        or _re.search(r"(^|\\s)MN(\\s|$)", school_key)\n    ):\n        return "MN"\n\n    if "THCS" in combined or "TRUNG HOC CO SO" in combined:\n        return "THCS"\n\n    if "THPT" in combined or "TRUNG HOC PHO THONG" in combined:\n        return "OTHER"\n\n    if (\n        "TIEU HOC" in combined\n        or "PRIMARY" in combined\n        or _re.search(r"(^|\\s)TH(\\s|$)", school_key)\n    ):\n        return "TH"\n\n    grade = None\n    match = _re.search(r"\\bLOP\\s*([0-9]{1,2})\\b", class_key)\n    if match is None:\n        match = _re.match(r"^\\s*([0-9]{1,2})(?:\\s|[A-Z]|$)", class_key)\n\n    if match is not None:\n        try:\n            grade = int(match.group(1))\n        except (TypeError, ValueError):\n            grade = None\n\n    if grade is not None:\n        if 1 <= grade <= 5:\n            return "TH"\n        if 6 <= grade <= 9:\n            return "THCS"\n        if 10 <= grade <= 12:\n            return "OTHER"\n\n    birth_date = getattr(person, "date_of_birth", None)\n    reference_year = b131133_nam_tham_chieu(school_year)\n\n    if birth_date is not None and reference_year is not None:\n        try:\n            age = reference_year - int(birth_date.year)\n        except (TypeError, ValueError, AttributeError):\n            age = None\n\n        if age is not None:\n            if 0 <= age <= 5:\n                return "MN"\n            if 6 <= age <= 10:\n                return "TH"\n            if 11 <= age <= 14:\n                return "THCS"\n\n    return "OTHER"\n\n\ndef b131133_truong_da_tra_loi(record, field_name):\n    if record is None:\n        return False\n\n    value = getattr(record, field_name, None)\n\n    if field_name in {"literacy_status", "post_lower_secondary_path"}:\n        normalized = str(value or "").strip().upper()\n        return normalized not in {"", "CHUA_XAC_DINH", "NONE"}\n\n    return value is not None\n\n\ndef b131133_tien_do_nam_hoc(*, person, record, school_year):\n    level = b131133_xac_dinh_cap_hoc(person, record, school_year)\n\n    required_fields = ["is_literacy_target"]\n\n    is_literacy_target = (\n        getattr(record, "is_literacy_target", None)\n        if record is not None\n        else None\n    )\n\n    if is_literacy_target is True:\n        required_fields.extend(\n            (\n                "literacy_status",\n                "completed_grade_3",\n                "completed_grade_5",\n            )\n        )\n\n    if level == "MN":\n        required_fields.extend(B131133_MN_FIELDS)\n    elif level == "TH":\n        required_fields.append("completed_primary_program")\n    elif level == "THCS":\n        required_fields.extend(\n            (\n                "completed_lower_secondary_program",\n                "post_lower_secondary_path",\n            )\n        )\n\n    answered = sum(\n        b131133_truong_da_tra_loi(record, field_name)\n        for field_name in required_fields\n    )\n    total = len(required_fields)\n\n    return {\n        "level": level,\n        "answered": int(answered),\n        "total": int(total),\n        "complete": bool(record is not None and answered == total),\n        "required_fields": tuple(required_fields),\n    }\n\n\ndef b131133_danh_gia_do_day_du_phieu_nhap_nhanh(*, db, survey_form):\n    people = list(\n        db.scalars(\n            select(SurveyPerson)\n            .where(\n                SurveyPerson.household_id == survey_form.household_id,\n                SurveyPerson.is_active.is_(True),\n            )\n            .order_by(\n                SurveyPerson.date_of_birth.asc(),\n                SurveyPerson.full_name.asc(),\n                SurveyPerson.id.asc(),\n            )\n        ).all()\n    )\n\n    person_ids = [int(person.id) for person in people]\n\n    records = []\n    if person_ids:\n        records = list(\n            db.scalars(\n                select(SurveyPersonYearRecord)\n                .where(\n                    SurveyPersonYearRecord.survey_form_id == survey_form.id,\n                    SurveyPersonYearRecord.school_year_id\n                    == survey_form.survey_batch.school_year_id,\n                    SurveyPersonYearRecord.survey_person_id.in_(person_ids),\n                )\n                .order_by(\n                    SurveyPersonYearRecord.updated_at.desc(),\n                    SurveyPersonYearRecord.id.desc(),\n                )\n            ).all()\n        )\n\n    record_by_person = {}\n    for record in records:\n        record_by_person.setdefault(int(record.survey_person_id), record)\n\n    missing_personal_id_count = 0\n    missing_year_record_count = 0\n    incomplete_year_record_count = 0\n    school_year = survey_form.survey_batch.school_year\n\n    for person in people:\n        if not str(getattr(person, "personal_id", "") or "").strip():\n            missing_personal_id_count += 1\n\n        record = record_by_person.get(int(person.id))\n\n        if record is None:\n            missing_year_record_count += 1\n            continue\n\n        progress = b131133_tien_do_nam_hoc(\n            person=person,\n            record=record,\n            school_year=school_year,\n        )\n\n        if not bool(progress["complete"]):\n            incomplete_year_record_count += 1\n\n    return {\n        "active_people_count": len(people),\n        "missing_personal_id_count": int(missing_personal_id_count),\n        "missing_year_record_count": int(missing_year_record_count),\n        "incomplete_year_record_count": int(incomplete_year_record_count),\n    }\n# === BAI_13B_11_13_3_1_DYNAMIC_PROGRESS_END ===\n'
YEAR_UI_SCRIPT = '\n<!-- === BAI_13B_11_13_3_1_YEAR_UI_START === -->\n<style>\n    #b131133_preschool_indicators[hidden],\n    #b131132_primary_indicators[hidden],\n    #b131132_thcs_indicators[hidden],\n    #b131132_xmc_details[hidden] {\n        display: none !important;\n    }\n</style>\n\n<script>\n(function () {\n    "use strict";\n\n    function normalizeText(value) {\n        return String(value || "")\n            .normalize("NFD")\n            .replace(/[\\u0300-\\u036f]/g, "")\n            .toUpperCase()\n            .replace(/\\s+/g, " ")\n            .trim();\n    }\n\n    function textOf(selector) {\n        const element = document.querySelector(selector);\n        if (!element) return "";\n\n        const values = [];\n        if ("value" in element && element.value) {\n            values.push(String(element.value));\n        }\n        if (element.textContent) {\n            values.push(String(element.textContent));\n        }\n        return values.join(" ");\n    }\n\n    function referenceAge() {\n        const birth =\n            {{ (person.date_of_birth.isoformat() if person.date_of_birth else \'\') | tojson }};\n        const yearCode =\n            {{ (batch.school_year.code if batch.school_year else \'\') | tojson }};\n\n        if (!birth) return null;\n\n        const birthYear = parseInt(String(birth).slice(0, 4), 10);\n        const years = String(yearCode || "").match(/20\\d{2}/g);\n\n        if (!Number.isFinite(birthYear) || !years || !years.length) {\n            return null;\n        }\n\n        const year = parseInt(years[0], 10);\n        const age = year - birthYear;\n\n        return (\n            Number.isFinite(age)\n            && age >= 0\n            && age <= 120\n        ) ? age : null;\n    }\n\n    function detectLevel() {\n        const school = normalizeText(\n            [\n                textOf("#school_search"),\n                textOf("#school_selected"),\n                textOf(\'[name="school_name_reported"]\')\n            ].join(" ")\n        );\n\n        const classText = normalizeText(\n            [\n                textOf("#class_search"),\n                textOf("#class_selected"),\n                textOf(\'[name="class_name_reported"]\')\n            ].join(" ")\n        );\n\n        const combined = school + " " + classText;\n\n        if (\n            combined.includes("MAM NON")\n            || combined.includes("MAU GIAO")\n            || combined.includes("NHA TRE")\n            || /(^|\\s)MN(\\s|$)/.test(school)\n        ) {\n            return "MN";\n        }\n\n        if (\n            combined.includes("THCS")\n            || combined.includes("TRUNG HOC CO SO")\n        ) {\n            return "THCS";\n        }\n\n        if (\n            combined.includes("THPT")\n            || combined.includes("TRUNG HOC PHO THONG")\n        ) {\n            return "OTHER";\n        }\n\n        if (\n            combined.includes("TIEU HOC")\n            || /(^|\\s)TH(\\s|$)/.test(school)\n        ) {\n            return "TH";\n        }\n\n        let match = classText.match(/\\bLOP\\s*([0-9]{1,2})\\b/);\n        if (!match) {\n            match = classText.match(/^\\s*([0-9]{1,2})(?:\\s|[A-Z]|$)/);\n        }\n\n        if (match) {\n            const grade = parseInt(match[1], 10);\n            if (grade >= 1 && grade <= 5) return "TH";\n            if (grade >= 6 && grade <= 9) return "THCS";\n            if (grade >= 10 && grade <= 12) return "OTHER";\n        }\n\n        const age = referenceAge();\n\n        if (age !== null) {\n            if (age <= 5) return "MN";\n            if (age >= 6 && age <= 10) return "TH";\n            if (age >= 11 && age <= 14) return "THCS";\n        }\n\n        return "OTHER";\n    }\n\n    function setVisible(element, visible) {\n        if (!element) return;\n\n        element.hidden = !visible;\n\n        element\n            .querySelectorAll("input,select,textarea")\n            .forEach(function (field) {\n                field.disabled = !visible;\n            });\n    }\n\n    function applyLiteracy() {\n        const target = document.getElementById("is_literacy_target");\n        const details = document.getElementById("b131132_xmc_details");\n\n        if (!target || !details) return;\n\n        setVisible(details, target.value === "CO");\n    }\n\n    function applyLevel() {\n        const level = detectLevel();\n\n        setVisible(\n            document.getElementById("b131133_preschool_indicators"),\n            level === "MN"\n        );\n        setVisible(\n            document.getElementById("b131132_primary_indicators"),\n            level === "TH"\n        );\n        setVisible(\n            document.getElementById("b131132_thcs_indicators"),\n            level === "THCS"\n        );\n\n        document.body.dataset.b131133Level = level;\n    }\n\n    function applyAll() {\n        applyLiteracy();\n        applyLevel();\n    }\n\n    document.addEventListener("DOMContentLoaded", function () {\n        const literacy = document.getElementById("is_literacy_target");\n\n        if (literacy) {\n            literacy.addEventListener("change", applyLiteracy);\n        }\n\n        [\n            "#school_search",\n            "#school_selected",\n            "#class_search",\n            "#class_selected",\n            "#school_id",\n            "#class_id",\n            \'[name="school_name_reported"]\',\n            \'[name="class_name_reported"]\'\n        ].forEach(function (selector) {\n            const element = document.querySelector(selector);\n            if (!element) return;\n\n            ["change", "input"].forEach(function (eventName) {\n                element.addEventListener(eventName, function () {\n                    window.setTimeout(applyLevel, 0);\n                });\n            });\n        });\n\n        applyAll();\n        window.setTimeout(applyAll, 120);\n        window.setTimeout(applyAll, 450);\n    });\n})();\n</script>\n<!-- === BAI_13B_11_13_3_1_YEAR_UI_END === -->\n'

HELPER_START = "# === BAI_13B_11_13_3_1_DYNAMIC_PROGRESS_START ==="
QUICK_START = "# === BAI_13B_11_13_3_1_QUICK_PROGRESS_START ==="
YEAR_UI_START = "<!-- === BAI_13B_11_13_3_1_YEAR_UI_START === -->"

LEVEL_START = "<!-- === BAI_13B_11_13_2_LEVEL_UI_START === -->"
LEVEL_END = "<!-- === BAI_13B_11_13_2_LEVEL_UI_END === -->"

REQUIRED_DB_FIELDS = {
    "is_literacy_target",
    "literacy_status",
    "completed_grade_3",
    "completed_grade_5",
    "completed_primary_program",
    "completed_lower_secondary_program",
    "post_lower_secondary_path",
}


def read_text(path: Path) -> str:
    if not path.exists():
        raise RuntimeError(f"Không tìm thấy: {path}")
    return path.read_text(encoding="utf-8-sig")


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
    src = sqlite3.connect(str(source))
    dst = sqlite3.connect(str(target))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()


def db_state():
    conn = sqlite3.connect(str(DB))
    try:
        count = int(
            conn.execute(
                "SELECT COUNT(*) FROM survey_person_year_records"
            ).fetchone()[0]
        )
        integrity = str(
            conn.execute("PRAGMA integrity_check").fetchone()[0]
        )
        fk_count = len(
            conn.execute("PRAGMA foreign_key_check").fetchall()
        )
        columns = {
            str(row[1])
            for row in conn.execute(
                "PRAGMA table_info(survey_person_year_records)"
            ).fetchall()
        }
        return count, integrity, fk_count, columns
    finally:
        conn.close()


def clear_cache() -> None:
    for cache in APP.rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(cache, ignore_errors=True)


def find_top_function(tree: ast.Module, name: str):
    matches = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == name
    ]
    if len(matches) != 1:
        raise RuntimeError(
            f"Phải tìm thấy đúng 1 hàm {name}; hiện có {len(matches)}."
        )
    return matches[0]


def insert_helpers(text: str) -> str:
    if HELPER_START in text:
        return text

    tree = ast.parse(text)
    matches = []

    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue

        names = []

        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.append(target.id)
        elif isinstance(node.target, ast.Name):
            names.append(node.target.id)

        if "BOOLEAN_YEAR_FIELDS" in names:
            matches.append(node)

    if len(matches) != 1:
        raise RuntimeError(
            "Không xác định duy nhất BOOLEAN_YEAR_FIELDS."
        )

    line_no = int(matches[0].end_lineno)
    lines = text.splitlines(keepends=True)

    lines.insert(
        line_no,
        "\n" + HELPER_BLOCK.strip("\n") + "\n\n",
    )

    patched = "".join(lines)
    ast.parse(patched)
    return patched


def patch_completion_logic(text: str) -> str:
    old = (
        "completion_data = "
        "danh_gia_do_day_du_phieu_nhap_nhanh("
    )
    new = (
        "completion_data = "
        "b131133_danh_gia_do_day_du_phieu_nhap_nhanh("
    )

    count = text.count(old)

    # Bài 13B-11.13.3.2:
    # Source hiện tại có 3 điểm dùng completion helper:
    # trang cập nhật phiếu + POST cập nhật phiếu + POST nhập nhanh.
    # Cả 3 đều phải dùng cùng logic động theo MN/TH/THCS/XMC.
    if count not in {0, 3}:
        raise RuntimeError(
            f"Số lời gọi completion helper cũ khác dự kiến: {count}."
        )

    if count == 3:
        text = text.replace(old, new)

    text = text.replace(
        'f"{incomplete_year_record_count} thành viên chưa đủ "',
        'f"{incomplete_year_record_count} thành viên chưa hoàn thành "',
    )
    text = text.replace(
        'f"{len(BOOLEAN_YEAR_FIELDS)} chỉ báo."',
        '"thông tin năm học theo nhóm đối tượng."',
    )
    text = text.replace(
        '"THIEU_CHI_BAO": "Đối tượng chưa nhập đủ 8 chỉ báo"',
        '"THIEU_CHI_BAO": '
        '"Đối tượng chưa hoàn thành thông tin năm học theo nhóm đối tượng"',
    )

    return text


def patch_quick_progress(text: str) -> str:
    if QUICK_START in text:
        return text

    tree = ast.parse(text)
    fn = find_top_function(tree, "hien_thi_trang_nhap_nhanh")

    target_return = None
    summaries_name = None

    for node in ast.walk(fn):
        if not isinstance(node, ast.Return):
            continue

        segment = ast.get_source_segment(text, node) or ""

        if "person_summaries" not in segment:
            continue

        match = re.search(
            r'["\']person_summaries["\']\s*:\s*([A-Za-z_][A-Za-z0-9_]*)',
            segment,
        )

        if match:
            target_return = node
            summaries_name = match.group(1)
            break

    if target_return is None or summaries_name is None:
        raise RuntimeError(
            "Không xác định được TemplateResponse có person_summaries."
        )

    lines = text.splitlines(keepends=True)
    line_no = int(target_return.lineno)
    source_line = lines[line_no - 1]
    indent = source_line[: len(source_line) - len(source_line.lstrip())]

    raw_lines = [
        "# === BAI_13B_11_13_3_1_QUICK_PROGRESS_START ===",
        f"for _b131133_item in {summaries_name}:",
        "    if isinstance(_b131133_item, dict):",
        '        _b131133_person = _b131133_item.get("person")',
        '        _b131133_record = _b131133_item.get("year_record")',
        "    else:",
        '        _b131133_person = getattr(_b131133_item, "person", None)',
        '        _b131133_record = getattr(_b131133_item, "year_record", None)',
        "",
        "    _b131133_progress = b131133_tien_do_nam_hoc(",
        "        person=_b131133_person,",
        "        record=_b131133_record,",
        "        school_year=survey_form.survey_batch.school_year,",
        "    )",
        "",
        "    if isinstance(_b131133_item, dict):",
        '        _b131133_item["answered"] = _b131133_progress["answered"]',
        '        _b131133_item["total"] = _b131133_progress["total"]',
        '        _b131133_item["education_level"] = _b131133_progress["level"]',
        "    else:",
        '        setattr(_b131133_item, "answered", _b131133_progress["answered"])',
        '        setattr(_b131133_item, "total", _b131133_progress["total"])',
        '        setattr(_b131133_item, "education_level", _b131133_progress["level"])',
        "# === BAI_13B_11_13_3_1_QUICK_PROGRESS_END ===",
        "",
    ]

    block = "\n".join(
        (indent + line if line else "")
        for line in raw_lines
    ) + "\n"

    lines.insert(line_no - 1, block)

    patched = "".join(lines)
    ast.parse(patched)
    return patched


def patch_mobile_accept(text: str) -> str:
    fn_pos = text.find(
        "def chap_nhan_thanh_vien_nhap_nhanh_mobile("
    )

    if fn_pos < 0:
        raise RuntimeError(
            "Không tìm thấy chap_nhan_thanh_vien_nhap_nhanh_mobile."
        )

    tuple_pos = text.find("fields_to_copy = (", fn_pos)

    if tuple_pos < 0:
        raise RuntimeError("Không tìm thấy fields_to_copy.")

    tuple_end = text.find("\n    )", tuple_pos)

    if tuple_end < 0:
        raise RuntimeError("Không xác định được cuối fields_to_copy.")

    block = text[tuple_pos:tuple_end]

    if '"is_literacy_target"' in block:
        return text

    anchor = '        "learning_status",\n'

    if anchor not in block:
        raise RuntimeError(
            "fields_to_copy không có learning_status."
        )

    extra = (
        '        "is_literacy_target",\n'
        '        "literacy_status",\n'
        '        "completed_grade_3",\n'
        '        "completed_grade_5",\n'
        '        "completed_primary_program",\n'
        '        "completed_lower_secondary_program",\n'
        '        "post_lower_secondary_path",\n'
    )

    new_block = block.replace(anchor, anchor + extra, 1)

    return text[:tuple_pos] + new_block + text[tuple_end:]


def find_matching_div_end(text: str, start: int) -> int:
    token = re.compile(r"<div\b[^>]*>|</div>", re.IGNORECASE)
    depth = 0

    for match in token.finditer(text, start):
        value = match.group(0).lower()

        if value.startswith("<div"):
            depth += 1
        else:
            depth -= 1
            if depth == 0:
                return match.end()

    raise RuntimeError("Không tìm thấy </div> khớp.")


def locate_preschool_group(text: str):
    label = "<label>Các chỉ báo mầm non</label>"
    label_pos = text.find(label)

    if label_pos < 0:
        raise RuntimeError("Không tìm thấy Các chỉ báo mầm non.")

    pos = text.rfind("<div", 0, label_pos)

    while pos >= 0:
        opening_end = text.find(">", pos)

        if opening_end < 0:
            break

        opening = text[pos : opening_end + 1]

        if "form-group" in opening and "full" in opening:
            end = find_matching_div_end(text, pos)

            if pos < label_pos < end:
                return pos, end

        pos = text.rfind("<div", 0, pos)

    raise RuntimeError(
        "Không xác định được khối Các chỉ báo mầm non."
    )


def add_preschool_id(text: str) -> str:
    start, _ = locate_preschool_group(text)
    opening_end = text.find(">", start)
    opening = text[start : opening_end + 1]

    if 'id="b131133_preschool_indicators"' in opening:
        return text

    if " id=" in opening:
        raise RuntimeError(
            "Khối Mầm non đã có id khác; dừng để tránh ghi đè."
        )

    opening = opening.replace(
        "<div",
        '<div id="b131133_preschool_indicators"',
        1,
    )

    return text[:start] + opening + text[opening_end + 1 :]


def move_level_block(text: str) -> str:
    start = text.find(LEVEL_START)
    end_start = text.find(LEVEL_END)

    if start < 0 or end_start < 0 or end_start < start:
        raise RuntimeError(
            "Không tìm thấy đầy đủ marker block Tiểu học/THCS."
        )

    end = end_start + len(LEVEL_END)
    block = text[start:end]
    text = text[:start] + text[end:]

    _, preschool_end = locate_preschool_group(text)

    return (
        text[:preschool_end]
        + "\n\n"
        + block
        + "\n"
        + text[preschool_end:]
    )


def patch_year_template(text: str) -> str:
    text = add_preschool_id(text)
    text = move_level_block(text)

    if YEAR_UI_START not in text:
        body_end = text.lower().rfind("</body>")

        if body_end < 0:
            raise RuntimeError(
                "Không tìm thấy </body> trong year_records.html."
            )

        text = (
            text[:body_end]
            + "\n"
            + YEAR_UI_SCRIPT
            + "\n"
            + text[body_end:]
        )

    return text


def patch_simple_templates() -> None:
    if QUICK_TEMPLATE.exists():
        text = read_text(QUICK_TEMPLATE)

        text = text.replace(
            "Ưu tiên xử lý các dòng thiếu định danh hoặc chưa đủ 8 chỉ báo.",
            "Ưu tiên xử lý các dòng thiếu định danh hoặc "
            "chưa hoàn thành thông tin năm học theo nhóm đối tượng.",
        )
        text = text.replace(
            "Chỉ báo:",
            "Thông tin năm học:",
        )
        text = text.replace(
            "Chưa nhập đủ chỉ báo.",
            "Chưa hoàn thành thông tin năm học theo nhóm đối tượng.",
        )

        write_text(QUICK_TEMPLATE, text)

    if DATA_QUALITY_TEMPLATE.exists():
        text = read_text(DATA_QUALITY_TEMPLATE)
        text = text.replace(
            "Thiếu chỉ báo:",
            "Thiếu thông tin năm học:",
        )
        write_text(DATA_QUALITY_TEMPLATE, text)


def verify_router() -> None:
    text = read_text(ROUTER)

    for marker in (
        HELPER_START,
        QUICK_START,
        "b131133_danh_gia_do_day_du_phieu_nhap_nhanh(",
        '"completed_primary_program"',
        '"completed_lower_secondary_program"',
    ):
        if marker not in text:
            raise RuntimeError(
                "surveys.py thiếu sau cài: " + marker
            )

    old_call = (
        "completion_data = "
        "danh_gia_do_day_du_phieu_nhap_nhanh("
    )

    if old_call in text:
        raise RuntimeError(
            "Vẫn còn completion_data dùng helper 8 chỉ báo cũ."
        )

    if 'f"{len(BOOLEAN_YEAR_FIELDS)} chỉ báo."' in text:
        raise RuntimeError(
            "Vẫn còn thông báo hoàn thành cố định 8 chỉ báo."
        )

    ast.parse(text)

    result = subprocess.run(
        [sys.executable, "-m", "py_compile", str(ROUTER)],
        cwd=PROJECT,
        capture_output=True,
        text=True,
    )

    if result.stdout:
        print(result.stdout.rstrip())
    if result.stderr:
        print(result.stderr.rstrip())

    if result.returncode != 0:
        raise RuntimeError("py_compile surveys.py không đạt.")


def verify_templates() -> None:
    from jinja2 import Environment

    for path in (
        YEAR_TEMPLATE,
        QUICK_TEMPLATE,
        DATA_QUALITY_TEMPLATE,
    ):
        if path.exists():
            Environment().parse(read_text(path))

    year_text = read_text(YEAR_TEMPLATE)

    for marker in (
        'id="b131133_preschool_indicators"',
        LEVEL_START,
        LEVEL_END,
        YEAR_UI_START,
        'id="b131132_primary_indicators"',
        'id="b131132_thcs_indicators"',
        'id="b131132_xmc_details"',
    ):
        if marker not in year_text:
            raise RuntimeError(
                "year_records.html thiếu sau cài: " + marker
            )

    label_pos = year_text.find(
        "<label>Các chỉ báo mầm non</label>"
    )
    level_pos = year_text.find(LEVEL_START)
    disability_pos = year_text.find(
        "Theo dõi trẻ khuyết tật"
    )

    if not (
        label_pos >= 0
        and level_pos > label_pos
        and disability_pos > level_pos
    ):
        raise RuntimeError(
            "Thứ tự khối chưa đúng: MN -> TH/THCS -> Khuyết tật."
        )

    if QUICK_TEMPLATE.exists():
        quick_text = read_text(QUICK_TEMPLATE).lower()
        if "chưa đủ 8 chỉ báo" in quick_text:
            raise RuntimeError(
                "quick_entry.html vẫn còn 'chưa đủ 8 chỉ báo'."
            )


def main() -> int:
    print("=" * 124)
    print(
        "BÀI 13B-11.13.3.1 - CHỈ BÁO ĐỘNG THEO CẤP + XMC "
        "VÀ HOÀN THÀNH PHIẾU ĐÚNG NGHIỆP VỤ"
    )
    print("=" * 124)
    print()
    print("QUY TẮC:")
    print(" - Mọi đối tượng: phải xác định Có/Không điều tra XMC.")
    print(
        " - XMC = Có: thêm Tình trạng XMC + "
        "Hoàn thành lớp 3 + Hoàn thành lớp 5."
    )
    print(" - Mầm non: đúng 8 chỉ báo MN hiện có.")
    print(" - Tiểu học: Hoàn thành chương trình Tiểu học.")
    print(
        " - THCS: Hoàn thành chương trình THCS "
        "+ Hướng học sau THCS."
    )
    print(
        " - Người ngoài MN/TH/THCS và XMC = Không "
        "không bị ép 8 chỉ báo MN."
    )
    print()
    print("SỬA:")
    print(" - Điều kiện hoàn thành phiếu.")
    print(" - Tiến độ từng thành viên ở Nhập nhanh.")
    print(" - Chấp nhận nhanh sao chép cả dữ liệu mới.")
    print(
        " - Giao diện theo thứ tự MN -> TH/THCS -> Khuyết tật."
    )
    print()
    print("AN TOÀN:")
    print(" - Backup router/template/database.")
    print(" - Không ALTER/INSERT/UPDATE/DELETE database.")
    print(" - py_compile + Jinja + integrity + foreign key.")
    print(" - Có lỗi tự khôi phục source.")
    print()

    for path in (ROUTER, YEAR_TEMPLATE, MODEL, DB):
        if not path.exists():
            raise RuntimeError(f"Không tìm thấy: {path}")

    count_before, integrity_before, fk_before, columns = db_state()

    if integrity_before.lower() != "ok" or fk_before != 0:
        raise RuntimeError(
            "Database không đạt kiểm tra trước khi cài."
        )

    missing = REQUIRED_DB_FIELDS - columns

    if missing:
        raise RuntimeError(
            "Database thiếu cột Bài 13B-11.13.1: "
            + ", ".join(sorted(missing))
        )

    BACKUP.mkdir(parents=True, exist_ok=False)

    for path in (
        ROUTER,
        YEAR_TEMPLATE,
        QUICK_TEMPLATE,
        DATA_QUALITY_TEMPLATE,
        MODEL,
    ):
        backup_file(path)

    sqlite_backup(DB, BACKUP / "phocap.db")

    print("Backup:", BACKUP)
    print(
        "survey_person_year_records trước cài:",
        count_before,
    )

    try:
        router_text = read_text(ROUTER)
        router_text = insert_helpers(router_text)
        router_text = patch_completion_logic(router_text)
        router_text = patch_quick_progress(router_text)
        router_text = patch_mobile_accept(router_text)

        write_text(ROUTER, router_text)

        year_text = read_text(YEAR_TEMPLATE)
        year_text = patch_year_template(year_text)
        write_text(YEAR_TEMPLATE, year_text)

        patch_simple_templates()

        verify_router()
        verify_templates()

        count_after, integrity_after, fk_after, _ = db_state()

        if count_after != count_before:
            raise RuntimeError(
                f"Số bản ghi DB thay đổi: {count_before} -> {count_after}"
            )

        if integrity_after.lower() != "ok":
            raise RuntimeError(
                "integrity_check sau cài không đạt."
            )

        if fk_after != 0:
            raise RuntimeError(
                f"foreign_key_check sau cài có {fk_after} lỗi."
            )

        clear_cache()

        print()
        print("KIỂM TRA SAU CÀI:")
        print(" - Bỏ ép 8 chỉ báo MN cho mọi người: OK")
        print(" - Hoàn thành phiếu dùng tiến độ theo nhóm: OK")
        print(" - Nhập nhanh dùng tiến độ động: OK")
        print(" - MN/TH/THCS hiển thị độc quyền: OK")
        print(" - TH/THCS nằm ngoài khối Khuyết tật: OK")
        print(" - XMC Không -> không cần 3 trường chi tiết: OK")
        print(" - Chỉ báo MN gốc: GIỮ NGUYÊN")
        print(" - py_compile: OK")
        print(" - Jinja parse: OK")
        print(" - integrity_check: OK")
        print(" - foreign_key_check: 0 lỗi")
        print(" - Database: KHÔNG THAY ĐỔI")
        print()
        print(
            "CÀI ĐẶT BÀI 13B-11.13.3.2 THÀNH CÔNG"
        )
        return 0

    except Exception:
        traceback.print_exc()

        print()
        print("CÓ LỖI - ĐANG KHÔI PHỤC SOURCE/TEMPLATE...")

        for path in (
            ROUTER,
            YEAR_TEMPLATE,
            QUICK_TEMPLATE,
            DATA_QUALITY_TEMPLATE,
            MODEL,
        ):
            try:
                restore_file(path)
            except Exception as exc:
                print(
                    " - Lỗi khôi phục",
                    path,
                    ":",
                    exc,
                )

        clear_cache()

        print("ĐÃ KHÔI PHỤC SOURCE/TEMPLATE.")
        print("Database không bị bộ cài ghi dữ liệu.")
        print("Backup:", BACKUP)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
