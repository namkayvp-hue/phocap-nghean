# -*- coding: utf-8 -*-
from __future__ import annotations

import ast
import hashlib
import py_compile
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from jinja2 import Environment

PROJECT = Path(r"C:\PhoCap")
APP = PROJECT / "app"
DB = PROJECT / "data" / "phocap.db"
EXPORTS = PROJECT / "exports"

MODEL = APP / "survey_models.py"
ROUTER = APP / "routers" / "surveys.py"
TEMPLATE = APP / "templates" / "surveys" / "year_records.html"
XMC_BUILDERS = APP / "pcgd_xmc_report_builders_v1.py"
XMC_SERVICE = APP / "services" / "xmc_report_v247.py"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = EXPORTS / f"backup_bai_13b_12_v2_1_{STAMP}"
REPORT = EXPORTS / f"bao_cao_cai_bai_13b_12_v2_1_{STAMP}.txt"
DB_BACKUP = BACKUP / "phocap.db"

MODEL_START = "# === BAI_13B_12_V2_1_ATTAINMENT_FIELDS_START ==="
MODEL_END = "# === BAI_13B_12_V2_1_ATTAINMENT_FIELDS_END ==="
ROUTER_PARAMS = "# === BAI_13B_12_V2_1_ATTAINMENT_PARAMS ==="
ROUTER_VALIDATE_START = "# === BAI_13B_12_V2_1_ATTAINMENT_VALIDATE_START ==="
ROUTER_VALIDATE_END = "# === BAI_13B_12_V2_1_ATTAINMENT_VALIDATE_END ==="
ROUTER_SAVE_START = "# === BAI_13B_12_V2_1_ATTAINMENT_SAVE_START ==="
ROUTER_SAVE_END = "# === BAI_13B_12_V2_1_ATTAINMENT_SAVE_END ==="
TEMPLATE_START = "<!-- === BAI_13B_12_V2_1_ATTAINMENT_UI_START === -->"
TEMPLATE_END = "<!-- === BAI_13B_12_V2_1_ATTAINMENT_UI_END === -->"

NEW_DB_COLUMNS = {
    "highest_completed_grade": "INTEGER",
    "education_attainment_level": "VARCHAR(40) NOT NULL DEFAULT 'CHUA_XAC_DINH'",
}

XMC_REQUIRED_COLUMNS = {
    "is_literacy_target",
    "literacy_status",
    "completed_grade_3",
    "completed_grade_5",
    "completed_primary_program",
    "completed_lower_secondary_program",
    "post_lower_secondary_path",
}

MODEL_BLOCK = '    # === BAI_13B_12_V2_1_ATTAINMENT_FIELDS_START ===\n    # Trình độ học vấn của MỌI thành viên hộ theo năm điều tra.\n    # Không thay thế / không suy diễn các field XMC completed_grade_3/5.\n    highest_completed_grade: Mapped[int | None] = mapped_column(\n        Integer,\n        nullable=True,\n    )\n    education_attainment_level: Mapped[str] = mapped_column(\n        String(40),\n        nullable=False,\n        default="CHUA_XAC_DINH",\n        server_default="CHUA_XAC_DINH",\n    )\n    # === BAI_13B_12_V2_1_ATTAINMENT_FIELDS_END ===\n\n'
VALIDATE_BLOCK = '    # === BAI_13B_12_V2_1_ATTAINMENT_VALIDATE_START ===\n    # Hai trường này áp dụng cho TOÀN BỘ thành viên hộ, không chỉ học sinh.\n    _b1312v21_grade_value = None\n    _b1312v21_grade_raw = str(\n        highest_completed_grade or ""\n    ).strip()\n\n    if not _b1312v21_grade_raw:\n        errors.append(\n            "Chưa khai báo lớp cao nhất đã hoàn thành."\n        )\n    else:\n        try:\n            _b1312v21_grade_value = int(\n                _b1312v21_grade_raw\n            )\n        except (TypeError, ValueError):\n            errors.append(\n                "Lớp cao nhất đã hoàn thành không hợp lệ."\n            )\n        else:\n            if not 0 <= _b1312v21_grade_value <= 12:\n                errors.append(\n                    "Lớp cao nhất đã hoàn thành phải từ 0 đến 12."\n                )\n\n    _b1312v21_level_value = str(\n        education_attainment_level\n        or "CHUA_XAC_DINH"\n    ).strip().upper()\n\n    _b1312v21_allowed_levels = {\n        "CHUA_XAC_DINH",\n        "CHUA_HOAN_THANH_TIEU_HOC",\n        "TIEU_HOC",\n        "THCS",\n        "THPT",\n        "TRUNG_CAP",\n        "CAO_DANG",\n        "DAI_HOC",\n        "SAU_DAI_HOC",\n        "KHAC",\n    }\n\n    if (\n        _b1312v21_level_value\n        not in _b1312v21_allowed_levels\n    ):\n        errors.append(\n            "Trình độ học vấn cao nhất không hợp lệ."\n        )\n        _b1312v21_level_value = "CHUA_XAC_DINH"\n    elif _b1312v21_level_value == "CHUA_XAC_DINH":\n        errors.append(\n            "Chưa khai báo trình độ học vấn cao nhất."\n        )\n    # === BAI_13B_12_V2_1_ATTAINMENT_VALIDATE_END ===\n\n'
SAVE_BLOCK = '        # === BAI_13B_12_V2_1_ATTAINMENT_SAVE_START ===\n        # Dữ liệu trình độ chung, dùng cho toàn dân.\n        # TUYỆT ĐỐI không ghi đè completed_grade_3/5 hoặc literacy_status.\n        record.highest_completed_grade = (\n            _b1312v21_grade_value\n        )\n        record.education_attainment_level = (\n            _b1312v21_level_value\n        )\n        # === BAI_13B_12_V2_1_ATTAINMENT_SAVE_END ===\n\n'
UI_BLOCK = '                    <!-- === BAI_13B_12_V2_1_ATTAINMENT_UI_START === -->\n                    <div\n                        class="form-group full b1312v21-attainment-card"\n                        style="\n                            margin-top:16px;\n                            padding:16px;\n                            border:1px solid #cfe0ee;\n                            border-radius:12px;\n                            background:#f8fbfe;\n                        "\n                    >\n                        <div style="margin-bottom:12px;">\n                            <strong style="font-size:17px;">\n                                Trình độ học vấn của đối tượng\n                            </strong>\n                            <p class="form-note" style="margin:6px 0 0;">\n                                Khai báo cho mọi thành viên trong hộ.\n                                Đây là dữ liệu điều tra thực tế theo năm,\n                                không thay đổi quy tắc Xóa mù chữ hiện có.\n                            </p>\n                        </div>\n\n                        <div\n                            style="\n                                display:grid;\n                                grid-template-columns:repeat(2,minmax(0,1fr));\n                                gap:14px;\n                            "\n                        >\n                            <div>\n                                <label for="highest_completed_grade">\n                                    Lớp cao nhất đã hoàn thành *\n                                </label>\n\n                                {% set b1312v21_grade =\n                                    selected_record.highest_completed_grade\n                                    if selected_record\n                                    else none\n                                %}\n\n                                <select\n                                    id="highest_completed_grade"\n                                    name="highest_completed_grade"\n                                    class="form-control"\n                                    required\n                                >\n                                    <option\n                                        value=""\n                                        {% if b1312v21_grade is none %}selected{% endif %}\n                                    >\n                                        -- Chưa xác định --\n                                    </option>\n                                    <option\n                                        value="0"\n                                        {% if b1312v21_grade == 0 %}selected{% endif %}\n                                    >\n                                        Chưa hoàn thành lớp 1\n                                    </option>\n                                    {% for grade_no in range(1, 13) %}\n                                    <option\n                                        value="{{ grade_no }}"\n                                        {% if b1312v21_grade == grade_no %}selected{% endif %}\n                                    >\n                                        Lớp {{ grade_no }}\n                                    </option>\n                                    {% endfor %}\n                                </select>\n\n                                <small class="form-note">\n                                    Ví dụ: đã học xong lớp 7 thì chọn Lớp 7;\n                                    trẻ chưa hoàn thành lớp 1 chọn “Chưa hoàn thành lớp 1”.\n                                </small>\n                            </div>\n\n                            <div>\n                                <label for="education_attainment_level">\n                                    Trình độ học vấn cao nhất *\n                                </label>\n\n                                {% set b1312v21_level =\n                                    selected_record.education_attainment_level\n                                    if selected_record and selected_record.education_attainment_level\n                                    else "CHUA_XAC_DINH"\n                                %}\n\n                                <select\n                                    id="education_attainment_level"\n                                    name="education_attainment_level"\n                                    class="form-control"\n                                    required\n                                >\n                                    <option value="CHUA_XAC_DINH"\n                                        {% if b1312v21_level == "CHUA_XAC_DINH" %}selected{% endif %}>\n                                        -- Chưa xác định --\n                                    </option>\n                                    <option value="CHUA_HOAN_THANH_TIEU_HOC"\n                                        {% if b1312v21_level == "CHUA_HOAN_THANH_TIEU_HOC" %}selected{% endif %}>\n                                        Chưa hoàn thành chương trình Tiểu học\n                                    </option>\n                                    <option value="TIEU_HOC"\n                                        {% if b1312v21_level == "TIEU_HOC" %}selected{% endif %}>\n                                        Hoàn thành Tiểu học\n                                    </option>\n                                    <option value="THCS"\n                                        {% if b1312v21_level == "THCS" %}selected{% endif %}>\n                                        Tốt nghiệp THCS\n                                    </option>\n                                    <option value="THPT"\n                                        {% if b1312v21_level == "THPT" %}selected{% endif %}>\n                                        Tốt nghiệp THPT hoặc tương đương\n                                    </option>\n                                    <option value="TRUNG_CAP"\n                                        {% if b1312v21_level == "TRUNG_CAP" %}selected{% endif %}>\n                                        Trung cấp\n                                    </option>\n                                    <option value="CAO_DANG"\n                                        {% if b1312v21_level == "CAO_DANG" %}selected{% endif %}>\n                                        Cao đẳng\n                                    </option>\n                                    <option value="DAI_HOC"\n                                        {% if b1312v21_level == "DAI_HOC" %}selected{% endif %}>\n                                        Đại học\n                                    </option>\n                                    <option value="SAU_DAI_HOC"\n                                        {% if b1312v21_level == "SAU_DAI_HOC" %}selected{% endif %}>\n                                        Sau đại học\n                                    </option>\n                                    <option value="KHAC"\n                                        {% if b1312v21_level == "KHAC" %}selected{% endif %}>\n                                        Khác\n                                    </option>\n                                </select>\n\n                                <small class="form-note">\n                                    Chọn trình độ đã hoàn thành cao nhất.\n                                    Tình trạng đang học hiện tại vẫn khai báo ở\n                                    Tình trạng học tập / Trường / Lớp.\n                                </small>\n                            </div>\n                        </div>\n                    </div>\n                    <!-- === BAI_13B_12_V2_1_ATTAINMENT_UI_END === -->\n'


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def db_columns() -> set[str]:
    con = sqlite3.connect(str(DB))
    try:
        return {
            str(row[1])
            for row in con.execute(
                "PRAGMA table_info(survey_person_year_records)"
            ).fetchall()
        }
    finally:
        con.close()


def db_state() -> dict:
    con = sqlite3.connect(str(DB))
    try:
        integrity = str(
            con.execute("PRAGMA integrity_check").fetchone()[0]
        )
        fk_count = len(
            con.execute("PRAGMA foreign_key_check").fetchall()
        )
        record_count = int(
            con.execute(
                "SELECT COUNT(*) FROM survey_person_year_records"
            ).fetchone()[0]
        )

        cols = {
            str(row[1])
            for row in con.execute(
                "PRAGMA table_info(survey_person_year_records)"
            ).fetchall()
        }

        distributions = {}
        for field in (
            "is_literacy_target",
            "literacy_status",
            "completed_grade_3",
            "completed_grade_5",
            "completed_primary_program",
            "completed_lower_secondary_program",
            "post_lower_secondary_path",
        ):
            if field not in cols:
                continue
            distributions[field] = [
                tuple(row)
                for row in con.execute(
                    f"""
                    SELECT {field}, COUNT(*)
                    FROM survey_person_year_records
                    GROUP BY {field}
                    ORDER BY {field}
                    """
                ).fetchall()
            ]

        return {
            "integrity": integrity,
            "fk_count": fk_count,
            "record_count": record_count,
            "xmc_distributions": distributions,
        }
    finally:
        con.close()


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


def restore_database() -> None:
    if not DB_BACKUP.exists():
        return
    src = sqlite3.connect(str(DB_BACKUP))
    dst = sqlite3.connect(str(DB))
    try:
        src.backup(dst)
        dst.commit()
    finally:
        dst.close()
        src.close()


def backup_source(path: Path) -> None:
    if not path.is_file():
        return
    dst = BACKUP / path.relative_to(PROJECT)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, dst)


def restore_source(path: Path) -> None:
    src = BACKUP / path.relative_to(PROJECT)
    if src.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, path)


def patch_model(text: str) -> str:
    if MODEL_START in text:
        return text

    anchor = "# === BAI_13B_11_15_1_PRIMARY_THCS_FIELDS_END ==="
    pos = text.find(anchor)
    if pos < 0:
        raise RuntimeError(
            "survey_models.py thiếu marker PRIMARY_THCS_FIELDS_END."
        )

    if "class SurveyPersonYearRecord" not in text:
        raise RuntimeError(
            "Không tìm thấy class SurveyPersonYearRecord."
        )

    return text[:pos] + MODEL_BLOCK + text[pos:]


def patch_progress(text: str) -> str:
    old_answer_check = (
        'if field_name in {"literacy_status", "post_lower_secondary_path"}:'
    )
    new_answer_check = (
        'if field_name in {"literacy_status", "post_lower_secondary_path", '
        '"education_attainment_level"}:'
    )

    if new_answer_check not in text:
        if old_answer_check not in text:
            raise RuntimeError(
                "Không tìm thấy điều kiện b131133_truong_da_tra_loi."
            )
        text = text.replace(
            old_answer_check,
            new_answer_check,
            1,
        )

    fn_pos = text.find("def b131133_tien_do_nam_hoc")
    if fn_pos < 0:
        raise RuntimeError(
            "Không tìm thấy b131133_tien_do_nam_hoc."
        )

    fn_window = text[fn_pos:fn_pos + 1800]
    if '"highest_completed_grade"' not in fn_window:
        old_required = 'required_fields = ["is_literacy_target"]'
        new_required = (
            'required_fields = [\n'
            '        "highest_completed_grade",\n'
            '        "education_attainment_level",\n'
            '        "is_literacy_target",\n'
            '    ]'
        )
        if old_required not in fn_window:
            raise RuntimeError(
                "Không tìm thấy required_fields của tiến độ năm học."
            )
        absolute = text.find(old_required, fn_pos)
        text = (
            text[:absolute]
            + new_required
            + text[absolute + len(old_required):]
        )

    return text


def patch_router_params(text: str) -> str:
    if ROUTER_PARAMS in text:
        return text

    anchor = (
        "    current_education_program: "
        "Annotated[str | None, Form()] = None,\n"
        "):"
    )

    if anchor not in text:
        raise RuntimeError(
            "Không tìm thấy đúng cuối tham số lưu year-record."
        )

    replacement = (
        "    current_education_program: "
        "Annotated[str | None, Form()] = None,\n"
        f"    {ROUTER_PARAMS}\n"
        "    highest_completed_grade: "
        "Annotated[str | None, Form()] = None,\n"
        "    education_attainment_level: "
        "Annotated[str | None, Form()] = None,\n"
        "):"
    )

    return text.replace(anchor, replacement, 1)


def patch_router_validate(text: str) -> str:
    if ROUTER_VALIDATE_START in text:
        return text

    anchor = (
        '    if learning_status not in LEARNING_STATUS_LABELS:\n'
        '        errors.append("Tình trạng học tập không hợp lệ.")\n'
    )
    if anchor not in text:
        raise RuntimeError(
            "Không tìm thấy block kiểm tra learning_status."
        )

    return text.replace(
        anchor,
        anchor + VALIDATE_BLOCK,
        1,
    )


def patch_router_save(text: str) -> str:
    if ROUTER_SAVE_START in text:
        return text

    anchor = (
        "        # Hai trạng thái này tái sử dụng "
        "learning_status hiện có."
    )
    pos = text.find(anchor)
    if pos < 0:
        raise RuntimeError(
            "Không tìm thấy điểm chèn lưu trình độ."
        )

    return text[:pos] + SAVE_BLOCK + text[pos:]


def patch_copy_fields(text: str) -> str:
    marker = "fields_to_copy = ("
    pos = text.find(marker)
    if pos < 0:
        raise RuntimeError(
            "Không tìm thấy fields_to_copy."
        )

    end = text.find(")", pos)
    if end < 0:
        raise RuntimeError(
            "Không xác định được hết fields_to_copy."
        )

    block = text[pos:end]
    if '"highest_completed_grade"' not in block:
        needle = '        "learning_status",\n'
        if needle not in block:
            raise RuntimeError(
                "fields_to_copy thiếu learning_status."
            )
        block = block.replace(
            needle,
            needle
            + '        "highest_completed_grade",\n'
            + '        "education_attainment_level",\n',
            1,
        )
        text = text[:pos] + block + text[end:]

    return text


def patch_inheritance_fields(text: str) -> str:
    marker = "    field_names = ("
    pos = text.find(marker)
    if pos < 0:
        raise RuntimeError(
            "Không tìm thấy field_names của liên năm."
        )

    end = text.find(")", pos)
    if end < 0:
        raise RuntimeError(
            "Không xác định được hết field_names."
        )

    block = text[pos:end]
    if '"highest_completed_grade"' not in block:
        needle = '        "learning_status",\n'
        if needle not in block:
            raise RuntimeError(
                "field_names liên năm thiếu learning_status."
            )
        block = block.replace(
            needle,
            needle
            + '        "highest_completed_grade",\n'
            + '        "education_attainment_level",\n',
            1,
        )
        text = text[:pos] + block + text[end:]

    default_anchor = (
        '        "learning_status": "CHUA_XAC_DINH",\n'
    )
    if '"highest_completed_grade": None,' not in text:
        if default_anchor not in text:
            raise RuntimeError(
                "Không tìm thấy values mặc định liên năm."
            )
        text = text.replace(
            default_anchor,
            default_anchor
            + '        "highest_completed_grade": None,\n'
            + '        "education_attainment_level": "CHUA_XAC_DINH",\n',
            1,
        )

    return text


def patch_router(text: str) -> str:
    text = patch_progress(text)
    text = patch_router_params(text)
    text = patch_router_validate(text)
    text = patch_router_save(text)
    text = patch_copy_fields(text)
    text = patch_inheritance_fields(text)
    return text


def patch_template(text: str) -> str:
    if TEMPLATE_START in text:
        return text

    name_pos = text.find('name="learning_status"')
    if name_pos < 0:
        raise RuntimeError(
            "Không tìm thấy select learning_status."
        )

    close_select = text.find("</select>", name_pos)
    if close_select < 0:
        raise RuntimeError(
            "Không tìm thấy </select> của learning_status."
        )

    insert_pos = close_select + len("</select>")
    return text[:insert_pos] + "\n" + UI_BLOCK + text[insert_pos:]


def migrate_db() -> None:
    con = sqlite3.connect(str(DB))
    try:
        con.execute("PRAGMA foreign_keys=ON")
        existing = {
            str(row[1])
            for row in con.execute(
                "PRAGMA table_info(survey_person_year_records)"
            ).fetchall()
        }

        for name, ddl in NEW_DB_COLUMNS.items():
            if name not in existing:
                con.execute(
                    f"ALTER TABLE survey_person_year_records "
                    f"ADD COLUMN {name} {ddl}"
                )

        con.commit()
    finally:
        con.close()


def verify_source() -> None:
    model_text = read_text(MODEL)
    router_text = read_text(ROUTER)
    template_text = read_text(TEMPLATE)

    for token in (
        MODEL_START,
        "highest_completed_grade",
        "education_attainment_level",
    ):
        if token not in model_text:
            raise RuntimeError(
                "Model thiếu sau cài: " + token
            )

    for token in (
        ROUTER_PARAMS,
        ROUTER_VALIDATE_START,
        ROUTER_VALIDATE_END,
        ROUTER_SAVE_START,
        ROUTER_SAVE_END,
        '"highest_completed_grade"',
        '"education_attainment_level"',
        "BAI_13B_11_15_2_4_7_1A_FORCE_XMC_AGE15_START",
        "BAI_13B_11_15_2_4_7_1B_DERIVE_LITERACY_STATUS_START",
    ):
        if token not in router_text:
            raise RuntimeError(
                "Router thiếu sau cài: " + token
            )

    for token in (
        TEMPLATE_START,
        TEMPLATE_END,
        'name="highest_completed_grade"',
        'name="education_attainment_level"',
        'name="completed_grade_3"',
        'name="completed_grade_5"',
    ):
        if token not in template_text:
            raise RuntimeError(
                "Template thiếu sau cài: " + token
            )

    ast.parse(model_text)
    ast.parse(router_text)
    py_compile.compile(str(MODEL), doraise=True)
    py_compile.compile(str(ROUTER), doraise=True)
    Environment().parse(template_text)


def verify_db(before: dict) -> dict:
    after = db_state()
    cols = db_columns()

    missing = set(NEW_DB_COLUMNS) - cols
    if missing:
        raise RuntimeError(
            "DB thiếu cột mới: "
            + ", ".join(sorted(missing))
        )

    if after["integrity"].lower() != "ok":
        raise RuntimeError(
            "integrity_check không đạt sau cài."
        )

    if after["fk_count"] != 0:
        raise RuntimeError(
            "foreign_key_check có lỗi sau cài."
        )

    if after["record_count"] != before["record_count"]:
        raise RuntimeError(
            "Số year-record thay đổi ngoài dự kiến."
        )

    if after["xmc_distributions"] != before["xmc_distributions"]:
        raise RuntimeError(
            "Dữ liệu XMC hiện có bị thay đổi ngoài dự kiến."
        )

    return after


def clear_cache() -> None:
    for cache in APP.rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(
                cache,
                ignore_errors=True,
            )


def main() -> int:
    global PROJECT, APP, DB, EXPORTS, MODEL, ROUTER, TEMPLATE
    global XMC_BUILDERS, XMC_SERVICE, BACKUP, REPORT, DB_BACKUP

    if not APP.is_dir():
        PROJECT = Path.cwd().resolve()
        APP = PROJECT / "app"
        DB = PROJECT / "data" / "phocap.db"
        EXPORTS = PROJECT / "exports"
        MODEL = APP / "survey_models.py"
        ROUTER = APP / "routers" / "surveys.py"
        TEMPLATE = APP / "templates" / "surveys" / "year_records.html"
        XMC_BUILDERS = APP / "pcgd_xmc_report_builders_v1.py"
        XMC_SERVICE = APP / "services" / "xmc_report_v247.py"
        BACKUP = EXPORTS / f"backup_bai_13b_12_v2_1_{STAMP}"
        REPORT = EXPORTS / f"bao_cao_cai_bai_13b_12_v2_1_{STAMP}.txt"
        DB_BACKUP = BACKUP / "phocap.db"

    print("=" * 120)
    print(
        "BÀI 13B-12 V2.1 - TRÌNH ĐỘ TOÀN DÂN "
        "+ GIỮ NGUYÊN QUY TẮC XÓA MÙ CHỮ"
    )
    print("=" * 120)
    print("Dự án:", PROJECT)
    print()

    for path in (
        MODEL,
        ROUTER,
        TEMPLATE,
        DB,
        XMC_BUILDERS,
        XMC_SERVICE,
    ):
        if not path.exists():
            print("DỪNG AN TOÀN: thiếu", path)
            return 2

    before = db_state()
    cols_before = db_columns()

    print("integrity_check:", before["integrity"])
    print("foreign_key_check:", before["fk_count"], "lỗi")
    print("survey_person_year_records:", before["record_count"])
    print()

    if (
        before["integrity"].lower() != "ok"
        or before["fk_count"] != 0
    ):
        print("DỪNG: database chưa đạt kiểm tra.")
        return 3

    missing_xmc = XMC_REQUIRED_COLUMNS - cols_before
    if missing_xmc:
        print(
            "DỪNG: thiếu nền XMC đã chốt:",
            ", ".join(sorted(missing_xmc)),
        )
        return 4

    router_before = read_text(ROUTER)
    if (
        "BAI_13B_11_15_2_4_7_1A_FORCE_XMC_AGE15_START"
        not in router_before
        or
        "BAI_13B_11_15_2_4_7_1B_DERIVE_LITERACY_STATUS_START"
        not in router_before
    ):
        print(
            "DỪNG: source hiện tại thiếu marker quy tắc XMC đã chốt."
        )
        return 5

    xmc_hashes_before = {
        "builders": sha256(XMC_BUILDERS),
        "service": sha256(XMC_SERVICE),
    }

    EXPORTS.mkdir(parents=True, exist_ok=True)
    BACKUP.mkdir(parents=True, exist_ok=False)

    for path in (
        MODEL,
        ROUTER,
        TEMPLATE,
        XMC_BUILDERS,
        XMC_SERVICE,
    ):
        backup_source(path)

    sqlite_backup(DB, DB_BACKUP)

    print("Backup:", BACKUP)
    print()

    try:
        model_new = patch_model(read_text(MODEL))
        router_new = patch_router(router_before)
        template_new = patch_template(read_text(TEMPLATE))

        ast.parse(model_new)
        ast.parse(router_new)
        Environment().parse(template_new)

        write_text(MODEL, model_new)
        write_text(ROUTER, router_new)
        write_text(TEMPLATE, template_new)

        migrate_db()
        verify_source()
        after = verify_db(before)

        xmc_hashes_after = {
            "builders": sha256(XMC_BUILDERS),
            "service": sha256(XMC_SERVICE),
        }

        if xmc_hashes_after != xmc_hashes_before:
            raise RuntimeError(
                "File công thức/report XMC bị thay đổi ngoài dự kiến."
            )

        clear_cache()

    except Exception as exc:
        print()
        print("CÓ LỖI - ĐANG ROLLBACK SOURCE + DATABASE...")
        print(type(exc).__name__ + ":", exc)

        for path in (
            MODEL,
            ROUTER,
            TEMPLATE,
            XMC_BUILDERS,
            XMC_SERVICE,
        ):
            restore_source(path)

        restore_database()
        clear_cache()

        print("ĐÃ KHÔI PHỤC.")
        print("Backup:", BACKUP)
        return 9

    REPORT.write_text(
        "\n".join(
            [
                "=" * 120,
                "BÁO CÁO CÀI BÀI 13B-12 V2.1",
                "=" * 120,
                f"Thời gian: {datetime.now():%d/%m/%Y %H:%M:%S}",
                f"Dự án: {PROJECT}",
                "",
                "ĐÃ BỔ SUNG:",
                "1. highest_completed_grade: lớp cao nhất đã hoàn thành (0-12).",
                "2. education_attainment_level: trình độ học vấn cao nhất.",
                "3. Hai trường áp dụng cho MỌI thành viên hộ.",
                "4. Hai trường tham gia kiểm tra tiến độ/đủ dữ liệu năm học.",
                "5. Hai trường tham gia cơ chế sao chép/liên năm hiện có.",
                "",
                "GIỮ NGUYÊN XMC:",
                "- is_literacy_target: không đổi.",
                "- literacy_status: không đổi logic.",
                "- completed_grade_3: không đổi dữ liệu/logic.",
                "- completed_grade_5: không đổi dữ liệu/logic.",
                "- CMC-1 / CMC-2 / XMC-3 / XMC-4: không sửa.",
                "- app/services/xmc_report_v247.py: không sửa.",
                "- app/pcgd_xmc_report_builders_v1.py: không sửa.",
                "",
                f"Year-record trước: {before['record_count']}",
                f"Year-record sau: {after['record_count']}",
                f"integrity_check: {after['integrity']}",
                f"foreign_key_check: {after['fk_count']} lỗi",
                f"Backup: {BACKUP}",
            ]
        )
        + "\n",
        encoding="utf-8-sig",
    )

    print("=" * 120)
    print("CÀI ĐẶT THÀNH CÔNG BÀI 13B-12 V2.1")
    print("=" * 120)
    print()
    print("ĐÃ LÀM:")
    print(" - Thêm Lớp cao nhất đã hoàn thành.")
    print(" - Thêm Trình độ học vấn cao nhất.")
    print(" - Áp dụng cho toàn bộ thành viên hộ.")
    print(" - Đưa vào kiểm tra đủ dữ liệu và nền liên năm.")
    print()
    print("XMC:")
    print(" - GIỮ NGUYÊN quy tắc >=15 tuổi.")
    print(" - GIỮ NGUYÊN completed_grade_3/5.")
    print(" - GIỮ NGUYÊN CMC-1 / CMC-2 / XMC-3 / XMC-4.")
    print(" - Không sửa builder/service XMC.")
    print()
    print("Backup:", BACKUP)
    print("Báo cáo:", REPORT)
    print()
    print("BƯỚC KIỂM TRA:")
    print(" 1. Khởi động lại Uvicorn.")
    print(" 2. Mở một thành viên hộ -> Theo dõi năm học.")
    print(" 3. Kiểm tra khối 'Trình độ học vấn của đối tượng'.")
    print(" 4. Với người >=15 tuổi, kiểm tra khối XMC cũ vẫn giữ nguyên.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
