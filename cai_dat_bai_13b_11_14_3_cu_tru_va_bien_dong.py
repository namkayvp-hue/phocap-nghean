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
TEMPLATE = APP / "templates" / "surveys" / "year_records.html"
DB = PROJECT / "data" / "phocap.db"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = PROJECT / "exports" / f"backup_bai_13b_11_14_3_{STAMP}"
DB_BACKUP = BACKUP / "data" / "phocap.db"

HELPER_MARKER = "# === BAI_13B_11_14_3_EVENT_HELPERS_START ==="
GET_MARKER = "# === BAI_13B_11_14_3_LOAD_EVENTS_START ==="
SAVE_MARKER = "# === BAI_13B_11_14_3_SAVE_EVENTS_START ==="

UI_START = "<!-- === BAI_13B_11_14_3_RESIDENCY_EVENTS_UI_START === -->"
UI_END = "<!-- === BAI_13B_11_14_3_RESIDENCY_EVENTS_UI_END === -->"

UI_BLOCK = '\n<!-- === BAI_13B_11_14_3_RESIDENCY_EVENTS_UI_START === -->\n{% set _events = b131143_events if b131143_events else {} %}\n{% set _move_in = _events.get("MOVE_IN") %}\n{% set _move_out = _events.get("MOVE_OUT") %}\n{% set _death = _events.get("DEATH") %}\n\n<div id="b131143_residency_events" class="form-group full"\n     style="border:1px solid #dbe7f3;border-radius:14px;padding:16px;background:#f8fbff;margin-top:10px;">\n    <label style="font-size:18px;">Cư trú và biến động</label>\n    <div class="form-note" style="margin-bottom:14px;">\n        Dữ liệu được lưu có cấu trúc để phục vụ MN-01-TE,\n        Sổ theo dõi phổ cập Mầm non và biến động theo từng năm học.\n    </div>\n\n    <div class="form-grid">\n        <div class="form-group full">\n            <label for="residency_status">1. Cư trú *</label>\n            <select id="residency_status" name="residency_status"\n                    class="form-control" required>\n                <option value="CHUA_XAC_DINH"\n                    {% if not person.residency_status or person.residency_status == "CHUA_XAC_DINH" %}selected{% endif %}>\n                    -- Chưa xác định --\n                </option>\n                <option value="THUONG_TRU"\n                    {% if person.residency_status == "THUONG_TRU" %}selected{% endif %}>\n                    Thường trú\n                </option>\n                <option value="TAM_TRU"\n                    {% if person.residency_status == "TAM_TRU" %}selected{% endif %}>\n                    Tạm trú\n                </option>\n            </select>\n        </div>\n\n        <div class="form-group full"\n             style="border:1px solid #e5e7eb;border-radius:12px;padding:14px;background:#fff;">\n            <label style="display:flex;gap:8px;align-items:center;cursor:pointer;">\n                <input id="move_in_active" name="move_in_active"\n                       type="checkbox" value="1"\n                       {% if _move_in %}checked{% endif %}>\n                <strong>2. Có chuyển đến trong năm học</strong>\n            </label>\n            <div id="move_in_details" class="form-grid" style="margin-top:10px;">\n                <div class="form-group">\n                    <label for="move_in_date">Ngày chuyển đến</label>\n                    <input id="move_in_date" name="move_in_date"\n                           type="date" class="form-control"\n                           value="{{ _move_in.event_date if _move_in and _move_in.event_date else \'\' }}">\n                </div>\n                <div class="form-group">\n                    <label for="move_in_origin">Nơi đi</label>\n                    <input id="move_in_origin" name="move_in_origin"\n                           type="text" class="form-control"\n                           value="{{ _move_in.origin_location if _move_in and _move_in.origin_location else \'\' }}"\n                           placeholder="Xã/phường, tỉnh/thành nơi chuyển đi">\n                </div>\n            </div>\n        </div>\n\n        <div class="form-group full"\n             style="border:1px solid #e5e7eb;border-radius:12px;padding:14px;background:#fff;">\n            <label style="display:flex;gap:8px;align-items:center;cursor:pointer;">\n                <input id="move_out_active" name="move_out_active"\n                       type="checkbox" value="1"\n                       {% if _move_out %}checked{% endif %}>\n                <strong>3. Có chuyển đi trong năm học</strong>\n            </label>\n            <div id="move_out_details" class="form-grid" style="margin-top:10px;">\n                <div class="form-group">\n                    <label for="move_out_date">Ngày chuyển đi</label>\n                    <input id="move_out_date" name="move_out_date"\n                           type="date" class="form-control"\n                           value="{{ _move_out.event_date if _move_out and _move_out.event_date else \'\' }}">\n                </div>\n                <div class="form-group">\n                    <label for="move_out_destination">Nơi đến</label>\n                    <input id="move_out_destination" name="move_out_destination"\n                           type="text" class="form-control"\n                           value="{{ _move_out.destination_location if _move_out and _move_out.destination_location else \'\' }}"\n                           placeholder="Xã/phường, tỉnh/thành nơi chuyển đến">\n                </div>\n            </div>\n        </div>\n\n        <div class="form-group full"\n             style="border:1px solid #f0d6d6;border-radius:12px;padding:14px;background:#fffafa;">\n            <label style="display:flex;gap:8px;align-items:center;cursor:pointer;">\n                <input id="death_active" name="death_active"\n                       type="checkbox" value="1"\n                       {% if _death %}checked{% endif %}>\n                <strong>4. Tử vong trong năm học</strong>\n            </label>\n            <div id="death_details" style="margin-top:10px;">\n                <div class="form-group">\n                    <label for="death_date">Ngày tử vong</label>\n                    <input id="death_date" name="death_date"\n                           type="date" class="form-control"\n                           value="{{ _death.event_date if _death and _death.event_date else \'\' }}">\n                </div>\n            </div>\n        </div>\n    </div>\n</div>\n\n<script>\n(function () {\n    function bindEventToggle(checkboxId, detailsId) {\n        const checkbox = document.getElementById(checkboxId);\n        const details = document.getElementById(detailsId);\n        if (!checkbox || !details) return;\n\n        function update() {\n            details.hidden = !checkbox.checked;\n        }\n\n        checkbox.addEventListener("change", update);\n        update();\n    }\n\n    bindEventToggle("move_in_active", "move_in_details");\n    bindEventToggle("move_out_active", "move_out_details");\n    bindEventToggle("death_active", "death_details");\n})();\n</script>\n<!-- === BAI_13B_11_14_3_RESIDENCY_EVENTS_UI_END === -->\n'
HELPERS = '\n# === BAI_13B_11_14_3_EVENT_HELPERS_START ===\ndef b131143_event_checked(value) -> bool:\n    return str(value or "").strip().upper() in {\n        "1", "TRUE", "ON", "CO", "YES",\n    }\n\n\ndef b131143_load_person_events(\n    db,\n    person_id: int,\n    school_year_id: int | None,\n) -> dict[str, dict]:\n    from sqlalchemy import text as _sa_text\n\n    rows = db.execute(\n        _sa_text(\n            "SELECT id, event_type, event_date, origin_location, "\n            "destination_location, notes "\n            "FROM survey_person_events "\n            "WHERE survey_person_id = :person_id "\n            "AND ((school_year_id = :school_year_id) "\n            "OR (school_year_id IS NULL AND :school_year_id IS NULL)) "\n            "AND COALESCE(is_active, 1) = 1 "\n            "AND event_type IN (\'MOVE_IN\',\'MOVE_OUT\',\'DEATH\') "\n            "ORDER BY id DESC"\n        ),\n        {\n            "person_id": int(person_id),\n            "school_year_id": school_year_id,\n        },\n    ).mappings().all()\n\n    result: dict[str, dict] = {}\n\n    for row in rows:\n        event_type = str(\n            row.get("event_type") or ""\n        ).strip().upper()\n\n        if event_type and event_type not in result:\n            result[event_type] = {\n                "id": row.get("id"),\n                "event_type": event_type,\n                "event_date": row.get("event_date"),\n                "origin_location": row.get("origin_location"),\n                "destination_location": row.get("destination_location"),\n                "notes": row.get("notes"),\n            }\n\n    return result\n\n\ndef b131143_save_person_event(\n    db,\n    *,\n    person_id: int,\n    school_year_id: int | None,\n    survey_form_id: int | None,\n    event_type: str,\n    active: bool,\n    event_date: str | None,\n    origin_location: str | None = None,\n    destination_location: str | None = None,\n) -> None:\n    from sqlalchemy import text as _sa_text\n\n    event_type = str(event_type or "").strip().upper()\n\n    if event_type not in {"MOVE_IN", "MOVE_OUT", "DEATH"}:\n        raise ValueError("Loại biến động không hợp lệ.")\n\n    existing_id = db.execute(\n        _sa_text(\n            "SELECT id FROM survey_person_events "\n            "WHERE survey_person_id = :person_id "\n            "AND ((school_year_id = :school_year_id) "\n            "OR (school_year_id IS NULL AND :school_year_id IS NULL)) "\n            "AND event_type = :event_type "\n            "ORDER BY COALESCE(is_active,1) DESC, id DESC LIMIT 1"\n        ),\n        {\n            "person_id": int(person_id),\n            "school_year_id": school_year_id,\n            "event_type": event_type,\n        },\n    ).scalar()\n\n    if not active:\n        if existing_id is not None:\n            db.execute(\n                _sa_text(\n                    "UPDATE survey_person_events "\n                    "SET is_active = 0, updated_at = CURRENT_TIMESTAMP "\n                    "WHERE id = :id"\n                ),\n                {"id": int(existing_id)},\n            )\n        return\n\n    params = {\n        "person_id": int(person_id),\n        "school_year_id": school_year_id,\n        "survey_form_id": survey_form_id,\n        "event_type": event_type,\n        "event_date": str(event_date or "").strip() or None,\n        "origin_location": (\n            str(origin_location or "").strip() or None\n        ),\n        "destination_location": (\n            str(destination_location or "").strip() or None\n        ),\n    }\n\n    if existing_id is not None:\n        params["id"] = int(existing_id)\n\n        db.execute(\n            _sa_text(\n                "UPDATE survey_person_events SET "\n                "survey_form_id=:survey_form_id, "\n                "event_date=:event_date, "\n                "origin_location=:origin_location, "\n                "destination_location=:destination_location, "\n                "is_active=1, updated_at=CURRENT_TIMESTAMP "\n                "WHERE id=:id"\n            ),\n            params,\n        )\n    else:\n        db.execute(\n            _sa_text(\n                "INSERT INTO survey_person_events ("\n                "survey_person_id, school_year_id, survey_form_id, "\n                "event_type, event_date, origin_location, "\n                "destination_location, is_active"\n                ") VALUES ("\n                ":person_id, :school_year_id, :survey_form_id, "\n                ":event_type, :event_date, :origin_location, "\n                ":destination_location, 1"\n                ")"\n            ),\n            params,\n        )\n# === BAI_13B_11_14_3_EVENT_HELPERS_END ===\n'
VALIDATION_BLOCK = '\n    # === BAI_13B_11_14_3_SAVE_EVENTS_START ===\n    _b131143_residency_status = str(\n        residency_status or ""\n    ).strip().upper()\n\n    if _b131143_residency_status not in {\n        "THUONG_TRU",\n        "TAM_TRU",\n    }:\n        errors.append(\n            "Cần xác định tình trạng cư trú: "\n            "Thường trú hoặc Tạm trú."\n        )\n\n    _b131143_move_in_active = b131143_event_checked(\n        move_in_active\n    )\n    _b131143_move_out_active = b131143_event_checked(\n        move_out_active\n    )\n    _b131143_death_active = b131143_event_checked(\n        death_active\n    )\n\n    _b131143_move_in_date = str(\n        move_in_date or ""\n    ).strip()\n    _b131143_move_in_origin = str(\n        move_in_origin or ""\n    ).strip()\n\n    _b131143_move_out_date = str(\n        move_out_date or ""\n    ).strip()\n    _b131143_move_out_destination = str(\n        move_out_destination or ""\n    ).strip()\n\n    _b131143_death_date = str(\n        death_date or ""\n    ).strip()\n\n    if _b131143_move_in_active:\n        if not _b131143_move_in_date:\n            errors.append(\n                "Chuyển đến: cần nhập ngày chuyển đến."\n            )\n        if not _b131143_move_in_origin:\n            errors.append(\n                "Chuyển đến: cần nhập nơi đi."\n            )\n\n    if _b131143_move_out_active:\n        if not _b131143_move_out_date:\n            errors.append(\n                "Chuyển đi: cần nhập ngày chuyển đi."\n            )\n        if not _b131143_move_out_destination:\n            errors.append(\n                "Chuyển đi: cần nhập nơi đến."\n            )\n\n    if _b131143_death_active:\n        if not _b131143_death_date:\n            errors.append(\n                "Tử vong: cần nhập ngày tử vong."\n            )\n    # === BAI_13B_11_14_3_SAVE_EVENTS_END ===\n'


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


def table_exists(conn, table: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master "
        "WHERE type='table' AND name=? LIMIT 1",
        (table,),
    ).fetchone() is not None


def table_columns(conn, table: str) -> set[str]:
    return {
        str(row[1])
        for row in conn.execute(
            f'PRAGMA table_info("{table}")'
        ).fetchall()
    }


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


def function_span(source: str, name: str):
    tree = ast.parse(source)

    matches = [
        node
        for node in tree.body
        if isinstance(
            node,
            (ast.FunctionDef, ast.AsyncFunctionDef),
        )
        and node.name == name
    ]

    if len(matches) != 1:
        raise RuntimeError(
            f"Phải tìm thấy đúng 1 hàm {name}; "
            f"hiện có {len(matches)}."
        )

    node = matches[0]
    lines = source.splitlines(keepends=True)
    offsets = [0]

    for line in lines:
        offsets.append(offsets[-1] + len(line))

    return (
        offsets[int(node.lineno) - 1],
        offsets[int(node.end_lineno)],
    )


def get_function(source: str, name: str) -> str:
    start, end = function_span(source, name)
    return source[start:end]


def replace_function(
    source: str,
    name: str,
    fn: str,
) -> str:
    start, end = function_span(source, name)

    patched = (
        source[:start]
        + fn.rstrip()
        + "\n\n"
        + source[end:].lstrip("\n")
    )

    ast.parse(patched)
    return patched


def patch_person_model(source: str) -> str:
    tree = ast.parse(source)

    classes = [
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef)
        and node.name == "SurveyPerson"
    ]

    if len(classes) != 1:
        raise RuntimeError(
            "Phải có đúng 1 class SurveyPerson."
        )

    cls = classes[0]
    existing = {
        assignment_name(node)
        for node in cls.body
    }

    if "residency_status" in existing:
        return source

    anchor = None

    for preferred in (
        "residency_type",
        "address",
        "ethnic_group",
        "gender",
        "date_of_birth",
    ):
        anchor = next(
            (
                node
                for node in cls.body
                if assignment_name(node) == preferred
            ),
            None,
        )
        if anchor is not None:
            break

    if anchor is None:
        raise RuntimeError(
            "Không tìm thấy vị trí thêm residency_status."
        )

    lines = source.splitlines(keepends=True)

    block = (
        "\n"
        "    # === BAI_13B_11_14_3_RESIDENCY_MODEL_START ===\n"
        "    residency_status: Mapped[str | None] = mapped_column(\n"
        "        String(30),\n"
        "        nullable=True,\n"
        "    )\n"
        "    # === BAI_13B_11_14_3_RESIDENCY_MODEL_END ===\n"
        "\n"
    )

    lines.insert(int(anchor.end_lineno), block)

    patched = "".join(lines)
    ast.parse(patched)
    return patched


def patch_helpers(source: str) -> str:
    if HELPER_MARKER in source:
        return source

    patched = (
        source.rstrip()
        + "\n\n\n"
        + HELPERS.strip("\n")
        + "\n"
    )

    ast.parse(patched)
    return patched


def find_year_get_function(source: str) -> str:
    tree = ast.parse(source)
    matches = []

    for node in tree.body:
        if not isinstance(
            node,
            (ast.FunctionDef, ast.AsyncFunctionDef),
        ):
            continue

        start, end = function_span(source, node.name)
        fn = source[start:end]

        if (
            "year_records.html" in fn
            and "selected_school_year_id" in fn
            and "TemplateResponse" in fn
        ):
            matches.append(node.name)

    if len(matches) != 1:
        raise RuntimeError(
            "Phải tìm thấy đúng 1 route GET "
            "hiển thị year_records.html; "
            f"hiện có {len(matches)}: {matches}"
        )

    return matches[0]


def patch_get_route(source: str):
    name = find_year_get_function(source)
    fn = get_function(source, name)

    if GET_MARKER not in fn:
        anchor = "    return templates.TemplateResponse("
        pos = fn.find(anchor)

        if pos < 0:
            raise RuntimeError(
                "Không tìm thấy return TemplateResponse."
            )

        block = (
            "    # === BAI_13B_11_14_3_LOAD_EVENTS_START ===\n"
            "    b131143_events = b131143_load_person_events(\n"
            "        db,\n"
            "        person.id,\n"
            "        selected_school_year_id,\n"
            "    )\n"
            "    # === BAI_13B_11_14_3_LOAD_EVENTS_END ===\n"
            "\n"
        )

        fn = fn[:pos] + block + fn[pos:]

    if '"b131143_events":' not in fn:
        pattern = re.compile(
            r'(?P<indent>[ \t]*)'
            r'"selected_school_year_id"'
            r'[ \t]*:[ \t]*selected_school_year_id'
            r'[ \t]*,[ \t]*\n'
        )

        match = pattern.search(fn)

        if match is None:
            raise RuntimeError(
                "Không tìm thấy context selected_school_year_id."
            )

        replacement = (
            match.group(0)
            + match.group("indent")
            + '"b131143_events": b131143_events,\n'
        )

        fn = (
            fn[:match.start()]
            + replacement
            + fn[match.end():]
        )

    return replace_function(
        source,
        name,
        fn,
    ), name


def patch_save_parameters(fn: str) -> str:
    if (
        "residency_status:" in fn
        and "move_in_active:" in fn
        and "death_date:" in fn
    ):
        return fn

    anchors = [
        (
            '    disability_access_education: '
            'Annotated[str, Form()] = "",\n'
        ),
        (
            '    disability_status: Annotated[str, Form()] '
            '= "CHUA_XAC_DINH",\n'
        ),
    ]

    anchor = next(
        (item for item in anchors if item in fn),
        None,
    )

    if anchor is None:
        raise RuntimeError(
            "Không tìm thấy vị trí chèn tham số."
        )

    block = (
        '    residency_status: Annotated[str, Form()] '
        '= "CHUA_XAC_DINH",\n'
        '    move_in_active: Annotated[str | None, Form()] = None,\n'
        '    move_in_date: Annotated[str | None, Form()] = None,\n'
        '    move_in_origin: Annotated[str | None, Form()] = None,\n'
        '    move_out_active: Annotated[str | None, Form()] = None,\n'
        '    move_out_date: Annotated[str | None, Form()] = None,\n'
        '    move_out_destination: Annotated[str | None, Form()] = None,\n'
        '    death_active: Annotated[str | None, Form()] = None,\n'
        '    death_date: Annotated[str | None, Form()] = None,\n'
    )

    return fn.replace(
        anchor,
        anchor + block,
        1,
    )


def patch_save_validation(fn: str) -> str:
    if SAVE_MARKER in fn:
        return fn

    anchor = "\n    if errors:\n"
    pos = fn.find(anchor)

    if pos < 0:
        raise RuntimeError(
            "Không tìm thấy if errors: trong route lưu."
        )

    return (
        fn[:pos]
        + "\n"
        + VALIDATION_BLOCK.strip("\n")
        + "\n"
        + fn[pos:]
    )


def patch_save_persistence(fn: str) -> str:
    if "b131143_save_person_event(" in fn:
        return fn

    commits = list(
        re.finditer(
            r"^[ \t]*db\.commit\(\)[ \t]*$",
            fn,
            flags=re.MULTILINE,
        )
    )

    if not commits:
        raise RuntimeError(
            "Không tìm thấy db.commit() trong route lưu."
        )

    match = commits[-1]
    indent = re.match(
        r"[ \t]*",
        match.group(0),
    ).group(0)

    block = "\n".join(
        [
            f"{indent}person.residency_status = _b131143_residency_status",
            "",
            f"{indent}_b131143_survey_form_id = getattr(",
            f"{indent}    record,",
            f'{indent}    "survey_form_id",',
            f"{indent}    None,",
            f"{indent})",
            "",
            f"{indent}b131143_save_person_event(",
            f"{indent}    db,",
            f"{indent}    person_id=person.id,",
            f"{indent}    school_year_id=school_year_id,",
            f"{indent}    survey_form_id=_b131143_survey_form_id,",
            f'{indent}    event_type="MOVE_IN",',
            f"{indent}    active=_b131143_move_in_active,",
            f"{indent}    event_date=_b131143_move_in_date,",
            f"{indent}    origin_location=_b131143_move_in_origin,",
            f"{indent})",
            "",
            f"{indent}b131143_save_person_event(",
            f"{indent}    db,",
            f"{indent}    person_id=person.id,",
            f"{indent}    school_year_id=school_year_id,",
            f"{indent}    survey_form_id=_b131143_survey_form_id,",
            f'{indent}    event_type="MOVE_OUT",',
            f"{indent}    active=_b131143_move_out_active,",
            f"{indent}    event_date=_b131143_move_out_date,",
            f"{indent}    destination_location=_b131143_move_out_destination,",
            f"{indent})",
            "",
            f"{indent}b131143_save_person_event(",
            f"{indent}    db,",
            f"{indent}    person_id=person.id,",
            f"{indent}    school_year_id=school_year_id,",
            f"{indent}    survey_form_id=_b131143_survey_form_id,",
            f'{indent}    event_type="DEATH",',
            f"{indent}    active=_b131143_death_active,",
            f"{indent}    event_date=_b131143_death_date,",
            f"{indent})",
            "",
        ]
    )

    return (
        fn[:match.start()]
        + block
        + fn[match.start():]
    )


def patch_save_route(source: str) -> str:
    fn = get_function(
        source,
        "luu_theo_doi_nam_hoc",
    )

    fn = patch_save_parameters(fn)
    fn = patch_save_validation(fn)
    fn = patch_save_persistence(fn)

    ast.parse(fn)

    return replace_function(
        source,
        "luu_theo_doi_nam_hoc",
        fn,
    )


def patch_template(source: str) -> str:
    if UI_START in source:
        return source

    anchor = (
        "<!-- === "
        "BAI_13B_11_14_2_PCGDMN_REPORT_UI_START"
        " === -->"
    )

    pos = source.find(anchor)

    if pos < 0:
        marker = 'id="b131133_preschool_indicators"'
        marker_pos = source.find(marker)

        if marker_pos < 0:
            raise RuntimeError(
                "Không tìm thấy khối PCGDMN."
            )

        pos = source.rfind(
            "<div",
            0,
            marker_pos,
        )

    return (
        source[:pos]
        + UI_BLOCK.strip("\n")
        + "\n\n"
        + source[pos:]
    )


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


def clear_cache() -> None:
    for cache in APP.rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(
                cache,
                ignore_errors=True,
            )


def db_state():
    conn = sqlite3.connect(str(DB))

    try:
        return (
            str(
                conn.execute(
                    "PRAGMA integrity_check"
                ).fetchone()[0]
            ),
            len(
                conn.execute(
                    "PRAGMA foreign_key_check"
                ).fetchall()
            ),
            table_columns(
                conn,
                "survey_people",
            ),
            int(
                conn.execute(
                    "SELECT COUNT(*) FROM survey_people"
                ).fetchone()[0]
            ),
            int(
                conn.execute(
                    "SELECT COUNT(*) FROM survey_person_events"
                ).fetchone()[0]
            ),
        )
    finally:
        conn.close()


def verify(
    people_before: int,
    events_before: int,
    get_name: str,
) -> None:
    model = read_text(MODEL)
    router = read_text(ROUTER)
    template = read_text(TEMPLATE)

    if "residency_status" not in model:
        raise RuntimeError(
            "Model thiếu residency_status."
        )

    for item in (
        HELPER_MARKER,
        GET_MARKER,
        SAVE_MARKER,
        "b131143_load_person_events(",
        "b131143_save_person_event(",
        "person.residency_status = ",
    ):
        if item not in router:
            raise RuntimeError(
                "Router thiếu: " + item
            )

    get_fn = get_function(
        router,
        get_name,
    )

    if (
        '"b131143_events": b131143_events'
        not in get_fn
    ):
        raise RuntimeError(
            "GET route chưa truyền events sang template."
        )

    for item in (
        UI_START,
        UI_END,
        'name="residency_status"',
        'name="move_in_active"',
        'name="move_in_date"',
        'name="move_in_origin"',
        'name="move_out_active"',
        'name="move_out_date"',
        'name="move_out_destination"',
        'name="death_active"',
        'name="death_date"',
    ):
        if item not in template:
            raise RuntimeError(
                "Template thiếu: " + item
            )

    compile_py(MODEL)
    compile_py(ROUTER)

    from jinja2 import Environment
    Environment().parse(template)

    (
        integrity,
        fk,
        people_cols,
        people_after,
        events_after,
    ) = db_state()

    if "residency_status" not in people_cols:
        raise RuntimeError(
            "DB thiếu survey_people.residency_status."
        )

    if people_after != people_before:
        raise RuntimeError(
            "Số survey_people bị thay đổi."
        )

    if events_after != events_before:
        raise RuntimeError(
            "Bộ cài tự sinh sự kiện ngoài dự kiến."
        )

    if integrity.lower() != "ok":
        raise RuntimeError(
            f"integrity_check: {integrity}"
        )

    if fk != 0:
        raise RuntimeError(
            f"foreign_key_check có {fk} lỗi."
        )


def main() -> int:
    print("=" * 124)
    print(
        "BÀI 13B-11.14.3 - "
        "CƯ TRÚ VÀ BIẾN ĐỘNG: "
        "CHUYỂN ĐẾN / CHUYỂN ĐI / TỬ VONG"
    )
    print("=" * 124)
    print()
    print("GIAO DIỆN:")
    print(" 1. Cư trú: Thường trú / Tạm trú.")
    print(" 2. Chuyển đến: Ngày + Nơi đi.")
    print(" 3. Chuyển đi: Ngày + Nơi đến.")
    print(" 4. Tử vong: Ngày.")
    print()
    print("LƯU:")
    print(
        " - Cư trú -> survey_people.residency_status."
    )
    print(
        " - Biến động -> survey_person_events theo người + năm học."
    )
    print()
    print("AN TOÀN:")
    print(
        " - Không ALTER database; dùng nền Bài 14.1."
    )
    print(
        " - Không tự tạo dữ liệu khi cài."
    )
    print(
        " - Backup source + database; lỗi rollback."
    )
    print()

    for path in (
        MODEL,
        ROUTER,
        TEMPLATE,
        DB,
    ):
        if not path.exists():
            raise RuntimeError(
                f"Không tìm thấy: {path}"
            )

    conn = sqlite3.connect(str(DB))
    try:
        if not table_exists(
            conn,
            "survey_person_events",
        ):
            raise RuntimeError(
                "Chưa có survey_person_events. "
                "Cần Bài 13B-11.14.1."
            )

        if (
            "residency_status"
            not in table_columns(
                conn,
                "survey_people",
            )
        ):
            raise RuntimeError(
                "Chưa có survey_people.residency_status. "
                "Cần Bài 13B-11.14.1."
            )
    finally:
        conn.close()

    (
        integrity_before,
        fk_before,
        _,
        people_before,
        events_before,
    ) = db_state()

    print(
        "integrity_check trước cài:",
        integrity_before,
    )
    print(
        "foreign_key_check trước cài:",
        fk_before,
        "lỗi",
    )
    print(
        "survey_people:",
        people_before,
        "bản ghi",
    )
    print(
        "survey_person_events:",
        events_before,
        "bản ghi",
    )

    if (
        integrity_before.lower() != "ok"
        or fk_before != 0
    ):
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
        TEMPLATE,
    ):
        backup_file(path)

    sqlite_backup(
        DB,
        DB_BACKUP,
    )

    print("Backup:", BACKUP)

    try:
        model_text = patch_person_model(
            read_text(MODEL)
        )

        router_text = read_text(ROUTER)
        router_text = patch_helpers(
            router_text
        )
        router_text, get_name = patch_get_route(
            router_text
        )
        router_text = patch_save_route(
            router_text
        )

        template_text = patch_template(
            read_text(TEMPLATE)
        )

        ast.parse(model_text)
        ast.parse(router_text)

        from jinja2 import Environment
        Environment().parse(
            template_text
        )

        write_text(
            MODEL,
            model_text,
        )
        write_text(
            ROUTER,
            router_text,
        )
        write_text(
            TEMPLATE,
            template_text,
        )

        verify(
            people_before,
            events_before,
            get_name,
        )

        clear_cache()

        print()
        print("KIỂM TRA SAU CÀI:")
        print(" - SurveyPerson.residency_status: OK")
        print(" - GET đọc biến động theo năm học: OK")
        print(" - POST lưu cư trú: OK")
        print(" - POST lưu chuyển đến: OK")
        print(" - POST lưu chuyển đi: OK")
        print(" - POST lưu tử vong: OK")
        print(" - UI ẩn/hiện chi tiết sự kiện: OK")
        print(" - py_compile + Jinja: OK")
        print(" - Không tự thay đổi dữ liệu khi cài: OK")
        print(" - integrity_check: OK")
        print(" - foreign_key_check: 0 lỗi")
        print()
        print("=" * 124)
        print(
            "CÀI ĐẶT BÀI 13B-11.14.3 THÀNH CÔNG"
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
            TEMPLATE,
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
            sqlite_restore(
                DB_BACKUP,
                DB,
            )
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
