# -*- coding: utf-8 -*-
from __future__ import annotations

import ast
import json
import py_compile
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

PROJECT = Path(r"C:\PhoCap")
APP = PROJECT / "app"
DB = PROJECT / "data" / "phocap.db"

CATALOG = APP / "structured_report_catalog.py"
BUILDER = APP / "pcgd_xmc_report_builders_v1.py"
ACCESS = APP / "access_control.py"

EXPORTS = PROJECT / "exports"
STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = EXPORTS / f"backup_bai_13b_12_v2_4_4_1_{STAMP}"
DB_BACKUP = BACKUP / "phocap.db"
REPORT = EXPORTS / f"bao_cao_cai_bai_13b_12_v2_4_4_1_{STAMP}.txt"

CATALOG_MARKER = "BAI_13B_12_V2_4_4_1_PCGD_CONDITION_CHECKLIST"
BUILDER_MARKER = "BAI_13B_12_V2_4_4_1_PCGD_CONDITION_GATE"
ACCESS_MARKER = "BAI_13B_12_V2_4_4_1_STRUCTURED_STAFF_POST"

STAFF_FIELDS = [
    (
        "pcgd_staffing_sufficient",
        "Đủ giáo viên và nhân viên theo quy định/định mức hiện hành",
        "Xác nhận điều kiện đội ngũ phục vụ công tác phổ cập.",
    ),
    (
        "pcgd_teacher_training_standard_all",
        "100% giáo viên đạt chuẩn trình độ đào tạo theo quy định",
        "Chỉ chọn Có khi đã kiểm tra toàn bộ giáo viên thuộc phạm vi.",
    ),
    (
        "pcgd_teacher_professional_standard_all",
        "100% giáo viên đạt yêu cầu chuẩn nghề nghiệp",
        "Chỉ chọn Có khi đã kiểm tra toàn bộ giáo viên thuộc phạm vi.",
    ),
    (
        "pcgd_tracker_assigned",
        "Đã phân công người theo dõi công tác PCGD-XMC",
        "Người theo dõi công tác PCGD-XMC đã được phân công.",
    ),
]

FACILITY_FIELDS = [
    (
        "pcgd_classrooms_standard_safe",
        "Phòng học bảo đảm tiêu chuẩn, an toàn, ánh sáng và điều kiện học tập",
        "Tỉ lệ phòng/lớp được hệ thống kiểm tra riêng.",
    ),
    (
        "pcgd_furniture_access_sufficient",
        "Đủ bàn ghế, bảng, bàn ghế giáo viên và điều kiện tối thiểu cho người học khuyết tật",
        "Xác nhận điều kiện sử dụng thực tế.",
    ),
    (
        "pcgd_function_rooms_sufficient",
        "Có đủ các phòng chức năng cần thiết theo quy định",
        "Phòng quản lý, y tế, thư viện, thiết bị/thí nghiệm và phòng liên quan theo cấp học.",
    ),
    (
        "pcgd_minimum_teaching_equipment_sufficient",
        "Đủ thiết bị dạy học tối thiểu theo quy định",
        "Không chỉ tính số phòng; phải xác nhận đủ thiết bị tối thiểu.",
    ),
    (
        "pcgd_teaching_equipment_regular_use",
        "Thiết bị dạy học được sử dụng thường xuyên, thuận tiện",
        "Xác nhận tình trạng sử dụng thực tế.",
    ),
    (
        "pcgd_playground_sports_safe",
        "Sân chơi/bãi tập phù hợp, sử dụng thường xuyên và an toàn",
        "Xác nhận điều kiện sân chơi, bãi tập.",
    ),
    (
        "pcgd_clean_water_drainage",
        "Có nguồn nước sạch và hệ thống thoát nước",
        "Xác nhận điều kiện nước sạch, thoát nước.",
    ),
    (
        "pcgd_toilets_separate_hygienic",
        "Công trình vệ sinh thuận tiện, hợp vệ sinh và tách phù hợp",
        "Xác nhận điều kiện vệ sinh.",
    ),
]

CHECKLIST_BY_SLUG = {
    "th-01-gv": (
        "7. Xác nhận điều kiện bảo đảm PCGD Tiểu học – Đội ngũ",
        STAFF_FIELDS,
    ),
    "th-01-csvc": (
        "5. Xác nhận điều kiện bảo đảm PCGD Tiểu học – CSVC, TBDH",
        FACILITY_FIELDS,
    ),
    "thcs-01-gv": (
        "7. Xác nhận điều kiện bảo đảm PCGD THCS – Đội ngũ",
        STAFF_FIELDS,
    ),
    "thcs-01-csvc": (
        "5. Xác nhận điều kiện bảo đảm PCGD THCS – CSVC, TBDH",
        FACILITY_FIELDS,
    ),
}

BUILDER_HELPERS = '\n# === BAI_13B_12_V2_4_4_1_PCGD_CONDITION_GATE_HELPERS_START ===\n_B2441_STAFF_VERIFY_KEYS = (\n    "pcgd_staffing_sufficient",\n    "pcgd_teacher_training_standard_all",\n    "pcgd_teacher_professional_standard_all",\n    "pcgd_tracker_assigned",\n)\n\n_B2441_FACILITY_VERIFY_KEYS = (\n    "pcgd_classrooms_standard_safe",\n    "pcgd_furniture_access_sufficient",\n    "pcgd_function_rooms_sufficient",\n    "pcgd_minimum_teaching_equipment_sufficient",\n    "pcgd_teaching_equipment_regular_use",\n    "pcgd_playground_sports_safe",\n    "pcgd_clean_water_drainage",\n    "pcgd_toilets_separate_hygienic",\n)\n\n\ndef _b2441_json_dict(record: Any) -> dict[str, Any]:\n    if record is None:\n        return {}\n    import json as _b2441_json\n\n    try:\n        value = _b2441_json.loads(\n            getattr(record, "data_json", None) or "{}"\n        )\n    except Exception:\n        return {}\n    return value if isinstance(value, dict) else {}\n\n\ndef _b2441_form_records(\n    db: Session,\n    *,\n    school_year_id: int,\n    school_ids: list[int],\n    form_code: str,\n) -> dict[int, dict[str, Any]]:\n    if not school_ids:\n        return {}\n\n    from sqlalchemy import select as _b2441_select\n\n    stmt = _b2441_select(\n        SchoolStructuredReportInput\n    ).where(\n        SchoolStructuredReportInput.school_year_id\n        == int(school_year_id),\n        SchoolStructuredReportInput.school_id.in_(\n            [int(x) for x in school_ids]\n        ),\n        SchoolStructuredReportInput.form_code == form_code,\n    )\n\n    result: dict[int, dict[str, Any]] = {}\n    for record in db.scalars(stmt).all():\n        result[int(record.school_id)] = _b2441_json_dict(record)\n    return result\n\n\ndef _b2441_verification_status(\n    rows: dict[int, dict[str, Any]],\n    school_ids: list[int],\n    keys: tuple[str, ...],\n) -> tuple[str, list[str]]:\n    missing: list[str] = []\n    any_no = False\n\n    for school_id in school_ids:\n        values = rows.get(int(school_id), {})\n        if not values:\n            missing.append(\n                f"school_id={school_id}: chưa có phiếu xác nhận"\n            )\n            continue\n\n        for key in keys:\n            if key not in values or values.get(key) is None:\n                missing.append(\n                    f"school_id={school_id}: thiếu {key}"\n                )\n                continue\n\n            try:\n                flag = int(values.get(key))\n            except (TypeError, ValueError):\n                missing.append(\n                    f"school_id={school_id}: {key} không hợp lệ"\n                )\n                continue\n\n            if flag != 1:\n                any_no = True\n\n    if any_no:\n        return "Chưa đạt", missing\n    if missing:\n        return "Chưa xác nhận", missing\n    return "Đạt", []\n\n\ndef _b2441_room_ratio_status(\n    csvc_rows: dict[int, dict[str, Any]],\n    school_ids: list[int],\n    *,\n    level: str,\n) -> tuple[bool | None, list[str]]:\n    threshold = 0.7 if level == "TH" else 0.5\n    missing: list[str] = []\n    passed = True\n\n    for school_id in school_ids:\n        values = csvc_rows.get(int(school_id), {})\n        try:\n            class_total = float(values.get("class_total"))\n        except (TypeError, ValueError):\n            missing.append(\n                f"school_id={school_id}: thiếu class_total"\n            )\n            continue\n\n        room_keys = [\n            "room_permanent",\n            "room_semi_permanent",\n            "room_temporary",\n        ]\n        if level == "TH":\n            room_keys.append("room_rent_borrow")\n\n        if not any(key in values for key in room_keys):\n            missing.append(\n                f"school_id={school_id}: thiếu số phòng học"\n            )\n            continue\n\n        if class_total <= 0:\n            missing.append(\n                f"school_id={school_id}: class_total <= 0"\n            )\n            continue\n\n        room_total = 0.0\n        invalid = False\n        for key in room_keys:\n            try:\n                room_total += float(values.get(key) or 0)\n            except (TypeError, ValueError):\n                invalid = True\n                missing.append(\n                    f"school_id={school_id}: {key} không hợp lệ"\n                )\n\n        if invalid:\n            continue\n\n        ratio = room_total / class_total\n        if ratio + 1e-9 < threshold:\n            passed = False\n\n    if missing:\n        return None, missing\n    return passed, []\n\n\ndef _b2441_condition_state(\n    db: Session,\n    *,\n    school_year_id: int,\n    selected_commune_id: int | None,\n    selected_school_id: int | None,\n    level: str,\n) -> dict[str, Any]:\n    schools, grades = _schools_and_classes(\n        db,\n        int(school_year_id),\n        selected_commune_id,\n        selected_school_id,\n    )\n    schools = [\n        school\n        for school in schools\n        if _school_supports_report_level(\n            db,\n            school,\n            grades,\n            level,\n        )\n    ]\n    school_ids = [int(s.id) for s in schools]\n\n    if not school_ids:\n        return {\n            "school_ids": [],\n            "staff_status": "Chưa xác nhận",\n            "csvc_status": "Chưa xác nhận",\n            "staff_missing": ["Không có trường trong phạm vi"],\n            "csvc_missing": ["Không có trường trong phạm vi"],\n            "all_passed": False,\n        }\n\n    staff_form = (\n        "TH_01_GV"\n        if level == "TH"\n        else "THCS_01_GV"\n    )\n    csvc_form = (\n        "TH_01_CSVC"\n        if level == "TH"\n        else "THCS_01_CSVC"\n    )\n\n    staff_rows = _b2441_form_records(\n        db,\n        school_year_id=int(school_year_id),\n        school_ids=school_ids,\n        form_code=staff_form,\n    )\n    csvc_rows = _b2441_form_records(\n        db,\n        school_year_id=int(school_year_id),\n        school_ids=school_ids,\n        form_code=csvc_form,\n    )\n\n    staff_status, staff_missing = _b2441_verification_status(\n        staff_rows,\n        school_ids,\n        _B2441_STAFF_VERIFY_KEYS,\n    )\n    csvc_status, csvc_missing = _b2441_verification_status(\n        csvc_rows,\n        school_ids,\n        _B2441_FACILITY_VERIFY_KEYS,\n    )\n\n    room_passed, room_missing = _b2441_room_ratio_status(\n        csvc_rows,\n        school_ids,\n        level=level,\n    )\n    csvc_missing.extend(room_missing)\n\n    if room_passed is False:\n        csvc_status = "Chưa đạt"\n    elif room_passed is None and csvc_status == "Đạt":\n        csvc_status = "Chưa xác nhận"\n\n    return {\n        "school_ids": school_ids,\n        "staff_status": staff_status,\n        "csvc_status": csvc_status,\n        "staff_missing": staff_missing,\n        "csvc_missing": csvc_missing,\n        "all_passed": (\n            staff_status == "Đạt"\n            and csvc_status == "Đạt"\n        ),\n    }\n\n\ndef _b2441_apply_condition_gate(\n    *,\n    ws: Any,\n    report_type: str,\n    db: Session,\n    school_year_id: int,\n    selected_commune_id: int | None,\n    selected_school_id: int | None,\n) -> None:\n    if report_type == "PCGD_TH_02_2025":\n        state = _b2441_condition_state(\n            db,\n            school_year_id=school_year_id,\n            selected_commune_id=selected_commune_id,\n            selected_school_id=selected_school_id,\n            level="TH",\n        )\n\n        ws["R8"] = state["staff_status"]\n        ws["S8"] = state["csvc_status"]\n\n        if selected_school_id is not None:\n            ws["T8"] = None\n        elif not state["all_passed"]:\n            if (\n                state["staff_status"] == "Chưa đạt"\n                or state["csvc_status"] == "Chưa đạt"\n            ):\n                ws["T8"] = "Chưa đạt ĐK"\n            else:\n                ws["T8"] = "Chưa đủ ĐK"\n        return\n\n    if report_type in {\n        "PCGD_THCS_M2_2025",\n        "PCGD_THCS_TK_2025",\n    }:\n        state = _b2441_condition_state(\n            db,\n            school_year_id=school_year_id,\n            selected_commune_id=selected_commune_id,\n            selected_school_id=selected_school_id,\n            level="THCS",\n        )\n\n        conclusion_ref = (\n            "W14"\n            if report_type == "PCGD_THCS_M2_2025"\n            else "R8"\n        )\n\n        if selected_school_id is not None:\n            ws[conclusion_ref] = None\n        elif not state["all_passed"]:\n            if (\n                state["staff_status"] == "Chưa đạt"\n                or state["csvc_status"] == "Chưa đạt"\n            ):\n                ws[conclusion_ref] = "Chưa đạt ĐK"\n            else:\n                ws[conclusion_ref] = "Chưa đủ ĐK"\n# === BAI_13B_12_V2_4_4_1_PCGD_CONDITION_GATE_HELPERS_END ===\n'
BUILDER_CALL = '\n# === BAI_13B_12_V2_4_4_1_PCGD_CONDITION_GATE_CALL_START ===\n_b2441_apply_condition_gate(\n    ws=ws,\n    report_type=report_type,\n    db=db,\n    school_year_id=int(school_year.id),\n    selected_commune_id=selected_commune_id,\n    selected_school_id=selected_school_id,\n)\n# === BAI_13B_12_V2_4_4_1_PCGD_CONDITION_GATE_CALL_END ===\n'
ACCESS_BLOCK = '\n        # === BAI_13B_12_V2_4_4_1_STRUCTURED_STAFF_POST ===\n        # Cho phép tài khoản đơn vị Trường/Xã lưu dữ liệu\n        # TH-01-GV / THCS-01-GV. Router vẫn khóa đúng school_id.\n        is_structured_staff = bool(\n            re.fullmatch(\n                r"/bieu-nhap/(?:th|thcs)-01-gv",\n                normalized_path.lower(),\n            )\n        )\n        if is_structured_staff:\n            if method in SAFE_METHODS:\n                return role_code in {\n                    *ADMIN_ROLE_CODES,\n                    DEPARTMENT_ROLE_CODE,\n                    COMMUNE_ROLE_CODE,\n                    SCHOOL_ROLE_CODE,\n                }\n            return (\n                is_admin_role(role_code)\n                or role_code in {\n                    COMMUNE_ROLE_CODE,\n                    SCHOOL_ROLE_CODE,\n                }\n            )\n'


def read_text(path: Path) -> str:
    if not path.exists():
        raise RuntimeError(f"Không tìm thấy file bắt buộc: {path}")
    return path.read_text(encoding="utf-8-sig", errors="strict")


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


def backup_db() -> None:
    src = sqlite3.connect(str(DB))
    dst = sqlite3.connect(str(DB_BACKUP))
    try:
        src.backup(dst)
        dst.commit()
    finally:
        dst.close()
        src.close()


def restore_db() -> None:
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


def db_state() -> dict[str, object]:
    con = sqlite3.connect(str(DB))
    try:
        result: dict[str, object] = {
            "integrity": str(
                con.execute("PRAGMA integrity_check").fetchone()[0]
            ),
            "fk_count": len(
                con.execute("PRAGMA foreign_key_check").fetchall()
            ),
        }
        for table in (
            "users",
            "schools",
            "staff_members",
            "staff_year_records",
            "school_structured_report_inputs",
            "survey_people",
            "survey_person_year_records",
        ):
            exists = con.execute(
                "SELECT 1 FROM sqlite_master "
                "WHERE type='table' AND name=?",
                (table,),
            ).fetchone()
            result[table] = (
                int(
                    con.execute(
                        f'SELECT COUNT(*) FROM "{table}"'
                    ).fetchone()[0]
                )
                if exists
                else None
            )
        return result
    finally:
        con.close()


def find_assignment_dict(tree: ast.Module, name: str) -> ast.Dict:
    for node in tree.body:
        if isinstance(node, ast.Assign):
            if any(
                isinstance(target, ast.Name) and target.id == name
                for target in node.targets
            ):
                if not isinstance(node.value, ast.Dict):
                    raise RuntimeError(
                        f"{name} không phải dict literal."
                    )
                return node.value
    raise RuntimeError(f"Không tìm thấy assignment {name}.")


def dict_value_by_string_key(node: ast.Dict, key: str) -> ast.AST:
    for k, v in zip(node.keys, node.values):
        if isinstance(k, ast.Constant) and k.value == key:
            return v
    raise RuntimeError(f"Không tìm thấy key {key} trong dict.")


def checklist_group_source(
    title: str,
    fields: list[tuple[str, str, str]],
) -> str:
    rows = [
        "            {",
        '                "anchor": "dieu-kien-bao-dam-pcgd",',
        f'                "title": {title!r},',
        "                # === " + CATALOG_MARKER + " ===",
        "                # Checklist không xuất thành cột Excel.",
        '                "fields": [',
    ]
    for code, label, help_text in fields:
        rows.extend(
            [
                "                    F(",
                f"                        {code!r},",
                f"                        {label!r},",
                "                        0,",
                '                        field_type="yesno",',
                "                        export=False,",
                f"                        help_text={help_text!r},",
                "                    ),",
            ]
        )
    rows.extend(
        [
            "                ],",
            "            },",
        ]
    )
    return "\n".join(rows) + "\n"


def patch_catalog(source: str) -> str:
    if CATALOG_MARKER in source:
        return source

    required = (
        "def F(",
        "STRUCTURED_SCHOOL_FORMS = {",
        '"th-01-gv"',
        '"th-01-csvc"',
        '"thcs-01-gv"',
        '"thcs-01-csvc"',
        "def flatten_fields(",
    )
    for token in required:
        if token not in source:
            raise RuntimeError(
                "structured_report_catalog.py khác nền dự kiến. "
                "Thiếu: " + token
            )

    old_sig = '    help_text: str = "",\n) -> dict:\n'
    new_sig = (
        '    help_text: str = "",\n'
        '    export: bool = True,\n'
        ') -> dict:\n'
    )
    if old_sig not in source:
        raise RuntimeError(
            "Không tìm thấy đúng chữ ký F(...) để thêm export."
        )
    source = source.replace(old_sig, new_sig, 1)

    old_return = '        "help": help_text,\n'
    new_return = (
        '        "help": help_text,\n'
        '        "export": bool(export),\n'
    )
    if old_return not in source:
        raise RuntimeError(
            "Không tìm thấy return của F(...) để thêm export."
        )
    source = source.replace(old_return, new_return, 1)

    tree = ast.parse(source)
    forms = find_assignment_dict(
        tree,
        "STRUCTURED_SCHOOL_FORMS",
    )
    insertions: list[tuple[int, str]] = []
    lines = source.splitlines(keepends=True)

    for slug, (title, fields) in CHECKLIST_BY_SLUG.items():
        form_node = dict_value_by_string_key(forms, slug)
        if not isinstance(form_node, ast.Dict):
            raise RuntimeError(f"Catalog {slug} không phải dict.")
        groups_node = dict_value_by_string_key(
            form_node,
            "groups",
        )
        if not isinstance(groups_node, ast.List):
            raise RuntimeError(
                f"groups của {slug} không phải list."
            )
        if groups_node.end_lineno is None:
            raise RuntimeError(
                f"AST groups {slug} thiếu end_lineno."
            )

        insertions.append(
            (
                int(groups_node.end_lineno) - 1,
                checklist_group_source(title, fields),
            )
        )

    for line_index, block in sorted(
        insertions,
        key=lambda item: item[0],
        reverse=True,
    ):
        lines.insert(line_index, block)

    patched = "".join(lines)
    ast.parse(patched)
    compile(patched, str(CATALOG), "exec")
    return patched


def function_span(source: str, name: str) -> tuple[int, int]:
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
            f"Không xác định duy nhất function {name}: "
            f"{len(matches)}"
        )

    node = matches[0]
    if node.end_lineno is None:
        raise RuntimeError(
            f"AST function {name} thiếu end_lineno."
        )

    lines = source.splitlines(keepends=True)
    start = sum(
        len(x)
        for x in lines[: node.lineno - 1]
    )
    end = sum(
        len(x)
        for x in lines[: node.end_lineno]
    )
    return start, end


def patch_builder(source: str) -> str:
    if BUILDER_MARKER in source:
        return source

    required = (
        "def _structured_overlay_export(",
        "fields = flatten_fields(catalog)",
        "def export_additional_report(",
        "workbook.save(",
        "def _b491_apply_xmc_conclusions(",
        "PCGD_TH_02_2025",
        "PCGD_THCS_M2_2025",
        "PCGD_THCS_TK_2025",
        "SchoolStructuredReportInput",
        "_schools_and_classes",
        "_school_supports_report_level",
    )
    for token in required:
        if token not in source:
            raise RuntimeError(
                "pcgd_xmc_report_builders_v1.py khác nền dự kiến. "
                "Thiếu: " + token
            )

    start, end = function_span(
        source,
        "_structured_overlay_export",
    )
    func = source[start:end]
    old = "    fields = flatten_fields(catalog)\n"
    new = (
        "    fields = [\n"
        "        field\n"
        "        for field in flatten_fields(catalog)\n"
        "        if field.get(\"export\", True)\n"
        "        and int(field.get(\"excel_col\") or 0) > 0\n"
        "    ]\n"
    )
    if old not in func:
        raise RuntimeError(
            "_structured_overlay_export không có câu "
            "fields = flatten_fields(catalog) đúng nền."
        )
    func = func.replace(old, new, 1)
    source = source[:start] + func + source[end:]

    start, end = function_span(
        source,
        "export_additional_report",
    )
    func = source[start:end]
    lines = func.splitlines(keepends=True)
    save_indexes = [
        i
        for i, line in enumerate(lines)
        if "workbook.save(" in line
    ]
    if len(save_indexes) != 1:
        raise RuntimeError(
            "Không xác định duy nhất workbook.save trong "
            "export_additional_report: "
            f"{len(save_indexes)}"
        )

    idx = save_indexes[0]
    indent = lines[idx][
        : len(lines[idx]) - len(lines[idx].lstrip())
    ]
    call = "\n".join(
        indent + line if line.strip() else line
        for line in BUILDER_CALL.strip().splitlines()
    ) + "\n"
    lines.insert(idx, call)
    func = "".join(lines)
    source = source[:start] + func + source[end:]

    source = (
        source.rstrip()
        + "\n\n\n"
        + BUILDER_HELPERS.strip()
        + "\n"
        + f"# {BUILDER_MARKER}\n"
    )

    ast.parse(source)
    compile(source, str(BUILDER), "exec")
    return source


def is_generic_safe_if(node: ast.AST) -> bool:
    if not isinstance(node, ast.If):
        return False
    try:
        value = ast.unparse(node.test).replace(" ", "")
    except Exception:
        return False
    return value == "methodinSAFE_METHODS"


def patch_access(source: str) -> str:
    if ACCESS_MARKER in source:
        return source

    required = (
        "class AccessControlMiddleware",
        "def _co_quyen_theo_thao_tac(",
        "normalized_path",
        "SAFE_METHODS",
        "ADMIN_ROLE_CODES",
        "DEPARTMENT_ROLE_CODE",
        "COMMUNE_ROLE_CODE",
        "SCHOOL_ROLE_CODE",
        "is_admin_role",
        "BAI_13B_12_V2_4_3_10_ACCESS_POST_CSVC_ALL_LEVELS",
    )
    for token in required:
        if token not in source:
            raise RuntimeError(
                "access_control.py khác nền dự kiến. Thiếu: "
                + token
            )

    tree = ast.parse(source)
    method = None
    for node in ast.walk(tree):
        if (
            isinstance(
                node,
                (ast.FunctionDef, ast.AsyncFunctionDef),
            )
            and node.name == "_co_quyen_theo_thao_tac"
        ):
            method = node
            break

    if method is None:
        raise RuntimeError(
            "Không tìm thấy _co_quyen_theo_thao_tac."
        )

    candidates = [
        node
        for node in method.body
        if is_generic_safe_if(node)
    ]
    if len(candidates) != 1:
        raise RuntimeError(
            "Không xác định duy nhất nhánh generic "
            f"SAFE_METHODS: {len(candidates)}"
        )

    anchor = candidates[0]
    lines = source.splitlines(keepends=True)
    lines.insert(
        anchor.lineno - 1,
        ACCESS_BLOCK.strip("\n") + "\n\n",
    )

    patched = "".join(lines)
    ast.parse(patched)
    compile(patched, str(ACCESS), "exec")
    return patched


def verify_catalog(source: str) -> None:
    required = (
        CATALOG_MARKER,
        "export: bool = True",
        '"export": bool(export)',
        "pcgd_staffing_sufficient",
        "pcgd_teacher_training_standard_all",
        "pcgd_teacher_professional_standard_all",
        "pcgd_tracker_assigned",
        "pcgd_classrooms_standard_safe",
        "pcgd_minimum_teaching_equipment_sufficient",
        "pcgd_clean_water_drainage",
        "pcgd_toilets_separate_hygienic",
        "export=False",
    )
    for token in required:
        if token not in source:
            raise RuntimeError(
                "Verifier catalog thiếu: " + token
            )

    ast.parse(source)
    compile(source, str(CATALOG), "exec")
    py_compile.compile(str(CATALOG), doraise=True)

    namespace: dict[str, object] = {}
    exec(
        compile(source, str(CATALOG), "exec"),
        namespace,
    )
    forms = namespace["STRUCTURED_SCHOOL_FORMS"]
    flatten = namespace["flatten_fields"]

    for slug, (_title, fields) in CHECKLIST_BY_SLUG.items():
        catalog = forms[slug]
        by_code = {
            field["code"]: field
            for field in flatten(catalog)
        }

        for code, _label, _help in fields:
            field = by_code.get(code)
            if field is None:
                raise RuntimeError(
                    f"Catalog {slug} thiếu field {code}"
                )
            if field.get("export") is not False:
                raise RuntimeError(
                    f"{slug}/{code} phải export=False"
                )
            if int(field.get("excel_col") or -1) != 0:
                raise RuntimeError(
                    f"{slug}/{code} phải excel_col=0"
                )


def verify_builder(source: str) -> None:
    required = (
        BUILDER_MARKER,
        "def _b2441_condition_state(",
        "def _b2441_apply_condition_gate(",
        "pcgd_staffing_sufficient",
        "pcgd_classrooms_standard_safe",
        'ws["R8"] = state["staff_status"]',
        'ws["S8"] = state["csvc_status"]',
        '"W14"',
        'field.get("export", True)',
        'and int(field.get("excel_col") or 0) > 0',
        "BAI_13B_12_V2_4_4_1_PCGD_CONDITION_GATE_CALL_START",
    )
    for token in required:
        if token not in source:
            raise RuntimeError(
                "Verifier builder thiếu: " + token
            )

    ast.parse(source)
    compile(source, str(BUILDER), "exec")
    py_compile.compile(str(BUILDER), doraise=True)


def verify_access(source: str) -> None:
    required = (
        ACCESS_MARKER,
        'r"/bieu-nhap/(?:th|thcs)-01-gv"',
        "COMMUNE_ROLE_CODE",
        "SCHOOL_ROLE_CODE",
        "DEPARTMENT_ROLE_CODE",
    )
    for token in required:
        if token not in source:
            raise RuntimeError(
                "Verifier access thiếu: " + token
            )

    ast.parse(source)
    compile(source, str(ACCESS), "exec")
    py_compile.compile(str(ACCESS), doraise=True)


def diagnostic_rows() -> list[str]:
    con = sqlite3.connect(str(DB))
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            """
            SELECT
                r.school_id,
                s.name AS school_name,
                r.school_year_id,
                r.form_code,
                r.data_json
            FROM school_structured_report_inputs r
            JOIN schools s ON s.id=r.school_id
            WHERE r.school_year_id=2
              AND r.form_code IN (
                  'TH_01_GV',
                  'TH_01_CSVC',
                  'THCS_01_GV',
                  'THCS_01_CSVC'
              )
              AND s.commune_id=114
            ORDER BY r.school_id, r.form_code
            """
        ).fetchall()

        result = []
        for row in rows:
            try:
                data = json.loads(
                    row["data_json"] or "{}"
                )
            except Exception:
                data = {}

            result.append(
                f"school_id={row['school_id']} "
                f"{row['school_name']} | "
                f"{row['form_code']} | "
                f"{len(data) if isinstance(data, dict) else 0} "
                "khóa dữ liệu"
            )

        if not result:
            result.append(
                "Chưa có structured input TH/THCS "
                "tại commune_id=114."
            )

        return result
    finally:
        con.close()


def clear_cache() -> None:
    for cache in APP.rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(
                cache,
                ignore_errors=True,
            )


def main() -> int:
    print("=" * 136)
    print(
        "BÀI 13B-12 V2.4.4.1 - "
        "ĐIỀU KIỆN BẢO ĐẢM PCGD TIỂU HỌC + THCS"
    )
    print("=" * 136)

    for path in (DB, CATALOG, BUILDER, ACCESS):
        if not path.exists():
            print("DỪNG AN TOÀN: thiếu", path)
            return 2

    before = db_state()
    print("integrity_check:", before["integrity"])
    print(
        "foreign_key_check:",
        before["fk_count"],
        "lỗi",
    )

    if (
        str(before["integrity"]).lower() != "ok"
        or int(before["fk_count"]) != 0
    ):
        print(
            "DỪNG: database chưa đạt kiểm tra an toàn."
        )
        return 3

    print()
    print("Dữ liệu cấu trúc hiện có tại phạm vi test:")
    for line in diagnostic_rows():
        print(" -", line)

    catalog_source = read_text(CATALOG)
    builder_source = read_text(BUILDER)
    access_source = read_text(ACCESS)

    try:
        already = (
            CATALOG_MARKER in catalog_source
            and BUILDER_MARKER in builder_source
            and ACCESS_MARKER in access_source
        )

        if already:
            print()
            print(
                "V2.4.4.1 đã có đủ marker. "
                "Kiểm tra lại..."
            )
            verify_catalog(catalog_source)
            verify_builder(builder_source)
            verify_access(access_source)
            print(
                "V2.4.4.1 đang hoạt động. "
                "Không cài lặp."
            )
            return 0

        if (
            CATALOG_MARKER in catalog_source
            or BUILDER_MARKER in builder_source
            or ACCESS_MARKER in access_source
        ):
            raise RuntimeError(
                "Phát hiện trạng thái cài dở V2.4.4.1. "
                "Dừng để không ghi chồng."
            )

        patched_catalog = patch_catalog(
            catalog_source
        )
        patched_builder = patch_builder(
            builder_source
        )
        patched_access = patch_access(
            access_source
        )

        ast.parse(patched_catalog)
        ast.parse(patched_builder)
        ast.parse(patched_access)

        compile(
            patched_catalog,
            str(CATALOG),
            "exec",
        )
        compile(
            patched_builder,
            str(BUILDER),
            "exec",
        )
        compile(
            patched_access,
            str(ACCESS),
            "exec",
        )

    except Exception as exc:
        print()
        print(
            "DỪNG AN TOÀN TRƯỚC KHI GHI SOURCE:"
        )
        print(type(exc).__name__ + ":", exc)
        print(
            "Không thay đổi source/database."
        )
        return 4

    EXPORTS.mkdir(
        parents=True,
        exist_ok=True,
    )
    BACKUP.mkdir(
        parents=True,
        exist_ok=False,
    )

    for path in (CATALOG, BUILDER, ACCESS):
        backup_file(path)
    backup_db()

    print()
    print("Backup:", BACKUP)

    try:
        write_text(CATALOG, patched_catalog)
        write_text(BUILDER, patched_builder)
        write_text(ACCESS, patched_access)

        verify_catalog(read_text(CATALOG))
        verify_builder(read_text(BUILDER))
        verify_access(read_text(ACCESS))
        clear_cache()

        after = db_state()

        if str(after["integrity"]).lower() != "ok":
            raise RuntimeError(
                "integrity_check không đạt sau cài."
            )

        if int(after["fk_count"]) != 0:
            raise RuntimeError(
                "foreign_key_check có lỗi sau cài."
            )

        for key, value in before.items():
            if key in {
                "integrity",
                "fk_count",
            }:
                continue

            if after.get(key) != value:
                raise RuntimeError(
                    f"Số bản ghi {key} thay đổi "
                    f"ngoài dự kiến: {value} "
                    f"-> {after.get(key)}"
                )

    except Exception as exc:
        print()
        print(
            "CÓ LỖI - ĐANG ROLLBACK "
            "3 SOURCE + DATABASE..."
        )
        print(type(exc).__name__ + ":", exc)

        for path in (
            CATALOG,
            BUILDER,
            ACCESS,
        ):
            restore_file(path)

        restore_db()
        clear_cache()

        print("ĐÃ KHÔI PHỤC.")
        return 9

    report_lines = [
        "=" * 136,
        "BÁO CÁO CÀI BÀI 13B-12 V2.4.4.1",
        "=" * 136,
        (
            "Thời gian: "
            f"{datetime.now():%d/%m/%Y %H:%M:%S}"
        ),
        "",
        "ĐÃ BỔ SUNG:",
        "- TH-01-GV: 4 xác nhận điều kiện Đội ngũ.",
        "- TH-01-CSVC: 8 xác nhận điều kiện CSVC/TBDH.",
        "- THCS-01-GV: 4 xác nhận điều kiện Đội ngũ.",
        "- THCS-01-CSVC: 8 xác nhận điều kiện CSVC/TBDH.",
        "- Checklist export=False, không thêm cột Excel.",
        "- TH: kiểm tỷ lệ phòng/lớp >= 0.7.",
        "- THCS: kiểm tỷ lệ phòng/lớp >= 0.5.",
        "- TH-02 R8/S8 hiển thị trạng thái điều kiện.",
        "- TH-02 T8 chỉ kết luận khi điều kiện đều Đạt.",
        "- THCS-M2 W14 / THCS-TK R8 bị khóa khi thiếu điều kiện.",
        "- Cấp Trường vẫn không tự kết luận cấp xã.",
        "- Trường/Xã được POST TH-01-GV và THCS-01-GV đúng scope.",
        "",
        "DỮ LIỆU TEST TRƯỚC CÀI:",
        *[
            "- " + line
            for line in diagnostic_rows()
        ],
        "",
        (
            "integrity_check: "
            f"{after['integrity']}"
        ),
        (
            "foreign_key_check: "
            f"{after['fk_count']} lỗi"
        ),
        f"Backup: {BACKUP}",
    ]

    REPORT.write_text(
        "\n".join(report_lines) + "\n",
        encoding="utf-8-sig",
    )

    print()
    print("=" * 136)
    print(
        "CÀI ĐẶT THÀNH CÔNG "
        "BÀI 13B-12 V2.4.4.1"
    )
    print("=" * 136)
    print(
        " - Checklist Đội ngũ TH: ĐẠT."
    )
    print(
        " - Checklist CSVC/TBDH TH: ĐẠT."
    )
    print(
        " - Checklist Đội ngũ THCS: ĐẠT."
    )
    print(
        " - Checklist CSVC/TBDH THCS: ĐẠT."
    )
    print(
        " - Không thêm cột vào Excel mẫu: ĐẠT."
    )
    print(
        " - Khóa kết luận TH-02 khi "
        "thiếu điều kiện: ĐẠT."
    )
    print(
        " - Khóa kết luận THCS-M2/TK khi "
        "thiếu điều kiện: ĐẠT."
    )
    print(
        " - Quyền lưu structured GV cho "
        "Trường/Xã: ĐẠT."
    )
    print(" - Không sửa dữ liệu hiện có.")
    print("Báo cáo:", REPORT)
    print("Backup:", BACKUP)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
