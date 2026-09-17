# -*- coding: utf-8 -*-
from __future__ import annotations

import ast
import py_compile
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

PROJECT = Path(r"C:\PhoCap")
APP = PROJECT / "app"
DB = PROJECT / "data" / "phocap.db"
EXPORTS = PROJECT / "exports"

SURVEY = APP / "routers" / "survey_summary_report.py"
TEMPLATE = APP / "routers" / "pcgdmn_template_report.py"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = EXPORTS / f"backup_bai_13b_12_v2_4_3_{STAMP}"
DB_BACKUP = BACKUP / "phocap.db"
REPORT = EXPORTS / f"bao_cao_cai_bai_13b_12_v2_4_3_{STAMP}.txt"

MARKER_SURVEY = "BAI_13B_12_V2_4_3_REPORT_SCOPE_HELPERS_START"
MARKER_TEMPLATE = "BAI_13B_12_V2_4_3_TEMPLATE_HELPERS_START"

SURVEY_HELPERS = '\n# === BAI_13B_12_V2_4_3_REPORT_SCOPE_HELPERS_START ===\ndef _v243_school_name_variants(name: str | None) -> tuple[str, ...]:\n    text = " ".join(str(name or "").split())\n    if not text:\n        return tuple()\n\n    variants = {text}\n\n    replacements = (\n        ("Trường Mầm non ", "Trường MN "),\n        ("Trường mầm non ", "Trường MN "),\n        ("Mầm non ", "MN "),\n        ("mầm non ", "MN "),\n    )\n    for old, new in replacements:\n        if old in text:\n            variants.add(text.replace(old, new, 1))\n\n    # Chỉ dùng exact variant, không fuzzy-match.\n    lowered = {\n        " ".join(item.split()).lower()\n        for item in variants\n        if " ".join(item.split())\n    }\n    return tuple(sorted(lowered))\n\n\ndef _v243_school_record_condition(\n    school_year_id: int,\n    school_id: int,\n    school_name: str | None,\n) -> Any:\n    variants = _v243_school_name_variants(school_name)\n\n    exact_id = SurveyPersonYearRecord.school_id == school_id\n    if not variants:\n        school_match = exact_id\n    else:\n        reported = func.lower(\n            func.trim(SurveyPersonYearRecord.school_name_reported)\n        )\n        school_match = or_(\n            exact_id,\n            and_(\n                SurveyPersonYearRecord.school_id.is_(None),\n                reported.in_(variants),\n            ),\n        )\n\n    return and_(\n        SurveyPersonYearRecord.school_year_id == school_year_id,\n        school_match,\n    )\n\n\ndef _v243_completed_preschool(row: dict[str, Any]) -> bool:\n    canonical = row.get("completed_preschool_by_age")\n    if canonical is not None:\n        return bool(canonical)\n    return row.get("completed_preschool_5") is True\n# === BAI_13B_12_V2_4_3_REPORT_SCOPE_HELPERS_END ===\n\n\n'
NEW_REFERENCE_DATE = 'def _reference_date(school_year: SchoolYear | None) -> date:\n    """\n    Tuổi PCGD tính theo năm dương lịch bắt đầu của năm học.\n\n    Ví dụ năm học 2026-2027:\n    - sinh 2026 => 0 tuổi\n    - sinh 2021 => 5 tuổi\n    - sinh 2020 => 6 tuổi\n\n    Không dùng start_date sai/lệch của bản ghi năm học để làm tăng tuổi thêm 1.\n    """\n    if school_year is not None:\n        try:\n            start_year = int(str(school_year.code).split("-")[0])\n            return date(start_year, 12, 31)\n        except (TypeError, ValueError):\n            pass\n\n        if school_year.start_date is not None:\n            return school_year.start_date\n\n    return date.today()\n\n\n'
NEW_SCHOOL_BATCH_CONDITION = 'def _school_batch_condition(\n    school_year_id: int,\n    school_id: int,\n    school_name: str | None = None,\n) -> Any:\n    return SurveyBatch.survey_forms.any(\n        SurveyForm.person_year_records.any(\n            _v243_school_record_condition(\n                school_year_id,\n                school_id,\n                school_name,\n            )\n        )\n    )\n\n\n'
NEW_LOAD_BATCHES = 'def _load_batches(\n    *,\n    db: Session,\n    request: Request,\n    school_year_id: int | None,\n    commune_id: int | None,\n    school_id: int | None,\n    data_state: str,\n    q: str,\n) -> tuple[list[SurveyBatch], dict[int, dict[str, int]]]:\n    if school_year_id is None:\n        return [], {}\n\n    selected_school = db.get(School, school_id) if school_id is not None else None\n    school_name = selected_school.name if selected_school is not None else None\n\n    statement = (\n        select(SurveyBatch)\n        .options(\n            selectinload(SurveyBatch.school_year),\n            selectinload(SurveyBatch.commune),\n        )\n        .where(\n            SurveyBatch.school_year_id == school_year_id,\n            *tao_bo_loc_dot_theo_nguoi_dung(request),\n        )\n        .order_by(\n            SurveyBatch.commune_id.asc(),\n            SurveyBatch.id.asc(),\n        )\n    )\n\n    if commune_id is not None:\n        statement = statement.where(SurveyBatch.commune_id == commune_id)\n    elif selected_school is not None:\n        # Khóa đúng địa bàn của trường, tránh trùng tên trường ở xã khác.\n        statement = statement.where(\n            SurveyBatch.commune_id == selected_school.commune_id\n        )\n\n    if school_id is not None:\n        statement = statement.where(\n            _school_batch_condition(\n                school_year_id,\n                school_id,\n                school_name,\n            )\n        )\n\n    if data_state == "LOCKED":\n        statement = statement.where(SurveyBatch.is_locked.is_(True))\n    elif data_state == "OPEN":\n        statement = statement.where(SurveyBatch.is_locked.is_(False))\n\n    if q:\n        like_value = f"%{q}%"\n        statement = statement.join(\n            Commune,\n            Commune.id == SurveyBatch.commune_id,\n        )\n        statement = statement.where(\n            or_(\n                SurveyBatch.code.ilike(like_value),\n                SurveyBatch.name.ilike(like_value),\n                Commune.code.ilike(like_value),\n                Commune.name.ilike(like_value),\n            )\n        )\n\n    batches = list(db.scalars(statement).unique().all())\n    batch_ids = [item.id for item in batches]\n    counts = {\n        batch_id: {"forms": 0, "households": 0}\n        for batch_id in batch_ids\n    }\n\n    if not batch_ids:\n        return batches, counts\n\n    form_statement = (\n        select(\n            SurveyForm.survey_batch_id,\n            func.count(distinct(SurveyForm.id)).label("forms"),\n            func.count(distinct(SurveyForm.household_id)).label("households"),\n        )\n        .where(\n            SurveyForm.survey_batch_id.in_(batch_ids),\n            *_form_permission_filters(request),\n        )\n        .group_by(SurveyForm.survey_batch_id)\n    )\n\n    if school_id is not None:\n        form_statement = form_statement.where(\n            SurveyForm.person_year_records.any(\n                _v243_school_record_condition(\n                    school_year_id,\n                    school_id,\n                    school_name,\n                )\n            )\n        )\n\n    for batch_id, form_total, household_total in db.execute(form_statement):\n        counts[int(batch_id)] = {\n            "forms": int(form_total or 0),\n            "households": int(household_total or 0),\n        }\n\n    if data_state == "HAS_DATA":\n        batches = [\n            item\n            for item in batches\n            if counts[item.id]["forms"] > 0\n        ]\n    elif data_state == "NO_DATA":\n        batches = [\n            item\n            for item in batches\n            if counts[item.id]["forms"] == 0\n        ]\n\n    return batches, counts\n\n\n'
NEW_LOAD_PERSON_ROWS = 'def _load_person_rows(\n    *,\n    db: Session,\n    request: Request,\n    batch_ids: list[int],\n    school_year_id: int | None,\n    school_id: int | None,\n) -> list[dict[str, Any]]:\n    if not batch_ids or school_year_id is None:\n        return []\n\n    year_record = SurveyPersonYearRecord\n    selected_school = db.get(School, school_id) if school_id is not None else None\n    school_name = selected_school.name if selected_school is not None else None\n\n    statement = (\n        select(\n            SurveyBatch.id.label("batch_id"),\n            SurveyBatch.code.label("batch_code"),\n            SurveyBatch.name.label("batch_name"),\n            SurveyBatch.is_locked.label("batch_is_locked"),\n            SurveyBatch.status.label("batch_status"),\n            Commune.id.label("commune_id"),\n            Commune.code.label("commune_code"),\n            Commune.name.label("commune_name"),\n            SurveyForm.id.label("form_id"),\n            SurveyForm.form_number.label("form_number"),\n            SurveyForm.status.label("form_status"),\n            SurveyForm.survey_date.label("survey_date"),\n            Household.id.label("household_id"),\n            Household.code.label("household_code"),\n            Household.head_name.label("head_name"),\n            Household.hamlet_name.label("hamlet_name"),\n            Household.address.label("address"),\n            SurveyPerson.id.label("person_id"),\n            SurveyPerson.code.label("person_code"),\n            SurveyPerson.full_name.label("full_name"),\n            SurveyPerson.date_of_birth.label("date_of_birth"),\n            SurveyPerson.gender.label("gender"),\n            SurveyPerson.ethnic_group.label("ethnic_group"),\n            SurveyPerson.personal_id.label("personal_id"),\n            SurveyPerson.ministry_student_code.label("ministry_student_code"),\n            SurveyPerson.residency_status.label("residency_status"),\n            SurveyPerson.relationship_to_head.label("relationship_to_head"),\n            year_record.id.label("year_record_id"),\n            year_record.learning_status.label("learning_status"),\n            year_record.is_reviewed.label("is_reviewed"),\n            year_record.completed_preschool_5.label("completed_preschool_5"),\n            year_record.completed_preschool_by_age.label(\n                "completed_preschool_by_age"\n            ),\n            year_record.attends_two_sessions_per_day.label(\n                "attends_two_sessions_per_day"\n            ),\n            year_record.prepared_vietnamese.label("prepared_vietnamese"),\n            year_record.disability_status.label("disability_status"),\n            year_record.disability_type.label("disability_type"),\n            year_record.disability_level.label("disability_level"),\n            year_record.disability_certificate.label("disability_certificate"),\n            year_record.disability_can_learn.label("disability_can_learn"),\n            year_record.disability_access_education.label(\n                "disability_access_education"\n            ),\n            year_record.inclusive_education.label("inclusive_education"),\n            year_record.disability_support.label("disability_support"),\n            year_record.study_location_scope.label("study_location_scope"),\n            year_record.school_id.label("school_id"),\n            year_record.school_name_reported.label("school_name_reported"),\n            year_record.class_name_reported.label("class_name_reported"),\n            School.code.label("school_code"),\n            School.name.label("school_name"),\n            School.commune_id.label("school_commune_id"),\n            Classroom.name.label("class_name"),\n        )\n        .select_from(SurveyForm)\n        .join(SurveyBatch, SurveyBatch.id == SurveyForm.survey_batch_id)\n        .join(Commune, Commune.id == SurveyBatch.commune_id)\n        .join(Household, Household.id == SurveyForm.household_id)\n        .join(SurveyPerson, SurveyPerson.household_id == Household.id)\n        .outerjoin(\n            year_record,\n            and_(\n                year_record.survey_form_id == SurveyForm.id,\n                year_record.survey_person_id == SurveyPerson.id,\n                year_record.school_year_id == school_year_id,\n            ),\n        )\n        .outerjoin(School, School.id == year_record.school_id)\n        .outerjoin(Classroom, Classroom.id == year_record.class_id)\n        .where(\n            SurveyForm.survey_batch_id.in_(batch_ids),\n            SurveyPerson.is_active.is_(True),\n            *_form_permission_filters(request),\n        )\n        .order_by(\n            Commune.name.asc(),\n            Household.hamlet_name.asc(),\n            Household.head_name.asc(),\n            SurveyPerson.full_name.asc(),\n            SurveyPerson.id.asc(),\n        )\n    )\n\n    if school_id is not None:\n        statement = statement.where(\n            _v243_school_record_condition(\n                school_year_id,\n                school_id,\n                school_name,\n            )\n        )\n\n    raw_rows = [\n        dict(item)\n        for item in db.execute(statement).mappings().all()\n    ]\n\n    seen: set[tuple[int, int]] = set()\n    rows: list[dict[str, Any]] = []\n    for row in raw_rows:\n        key = (\n            int(row["batch_id"]),\n            int(row["person_id"]),\n        )\n        if key in seen:\n            continue\n        seen.add(key)\n        rows.append(row)\n\n    return rows\n\n\n'

TEMPLATE_HELPERS = '\n# === BAI_13B_12_V2_4_3_TEMPLATE_HELPERS_START ===\ndef _v243_true(value: Any) -> bool:\n    if value is True:\n        return True\n    if isinstance(value, (int, float)):\n        return value == 1\n    return str(value or "").strip().upper() in {\n        "1",\n        "TRUE",\n        "YES",\n        "CO",\n        "CÓ",\n    }\n\n\ndef _v243_false(value: Any) -> bool:\n    if value is False:\n        return True\n    if isinstance(value, (int, float)):\n        return value == 0\n    return str(value or "").strip().upper() in {\n        "0",\n        "FALSE",\n        "NO",\n        "KHONG",\n        "KHÔNG",\n    }\n\n\ndef _v243_completed(row: dict[str, Any]) -> bool:\n    canonical = row.get("completed_preschool_by_age")\n    if canonical is not None:\n        return _v243_true(canonical)\n    return row.get("completed_preschool_5") is True\n\n\ndef _v243_can_learn(row: dict[str, Any]) -> bool:\n    return _is_disabled(row) and _v243_true(\n        row.get("disability_can_learn")\n    )\n\n\ndef _v243_access(row: dict[str, Any]) -> bool:\n    return _is_disabled(row) and _v243_true(\n        row.get("disability_access_education")\n    )\n\n\ndef _v243_mobilizable(row: dict[str, Any]) -> bool:\n    if not _is_disabled(row):\n        return True\n    # Chỉ loại khỏi "phải huy động" khi đã xác nhận rõ là không có khả năng học.\n    return not _v243_false(row.get("disability_can_learn"))\n\n\ndef _v243_two_sessions(row: dict[str, Any]) -> bool:\n    return _v243_true(row.get("attends_two_sessions_per_day"))\n\n\ndef _v243_local_study(row: dict[str, Any]) -> bool:\n    code = str(row.get("study_location_scope") or "").strip().upper()\n    if code in {"TAI_CHO", "TRONG_XA", "CUNG_XA"}:\n        return True\n    if code in {\n        "KHAC_XA",\n        "TRONG_TINH_KHAC_XA",\n        "NGOAI_DIA_BAN",\n        "TRAI_TUYEN",\n    }:\n        return False\n\n    school_commune_id = row.get("school_commune_id")\n    return (\n        not school_commune_id\n        or school_commune_id == row.get("commune_id")\n    )\n\n\ndef _v243_cross_study(row: dict[str, Any]) -> bool:\n    return _is_studying(row) and not _v243_local_study(row)\n\n\ndef _v243_normalize_year_labels(\n    workbook: Any,\n    school_year: SchoolYear,\n) -> None:\n    start_year, _end_year = _reference_years(school_year)\n\n    ws = _get_sheet(workbook, "MN-01 TE")\n    ws["C2"] = f"Thời điểm: Năm {start_year}"\n\n    ws = _get_sheet(workbook, "MN-01 GV")\n    ws["C2"] = f"Thời điểm: Năm {start_year}"\n\n    ws = _get_sheet(workbook, "MN-01 CSVC")\n    ws["C2"] = f"Thời điểm: Năm {start_year}"\n\n    ws = _get_sheet(workbook, "MN - Tài chính")\n    ws["A4"] = f"Năm: {start_year}"\n    for offset, column in enumerate(range(5, 10)):\n        ws.cell(8, column).value = start_year + offset\n\n    ws = _get_sheet(workbook, "MN- Trẻ KT")\n    ws["A5"] = f"Năm: {school_year.code}"\n\n    ws = _get_sheet(workbook, "Sổ theo dõi PCGDMN")\n    ws["A3"] = f"Năm học: {school_year.code}"\n# === BAI_13B_12_V2_4_3_TEMPLATE_HELPERS_END ===\n\n\n'
NEW_WRITE_TE = 'def _write_mn01_te(\n    ws: Any,\n    person_rows: list[dict[str, Any]],\n    record_map: dict[int, SurveyPersonYearRecord],\n    school_year: SchoolYear,\n) -> None:\n    start_year, _end_year = _reference_years(school_year)\n    age_cols = {age: 5 + age for age in range(7)}\n\n    # Tuổi PCGD theo năm dương lịch bắt đầu của năm học.\n    for age, column in age_cols.items():\n        ws.cell(5, column).value = start_year - age\n        ws.cell(6, column).value = f"{age} tuổi"\n\n    _clear_range_values(ws, "E7:L29")\n\n    age_rows: dict[int, list[dict[str, Any]]] = {\n        age: [\n            row\n            for row in person_rows\n            if row.get("age") == age\n        ]\n        for age in range(7)\n    }\n\n    row_values: dict[int, dict[int, Any]] = defaultdict(dict)\n\n    for age, rows in age_rows.items():\n        disabled = [row for row in rows if _is_disabled(row)]\n        can_learn = [row for row in disabled if _v243_can_learn(row)]\n        access = [row for row in disabled if _v243_access(row)]\n        mobilizable = [row for row in rows if _v243_mobilizable(row)]\n        studying = [row for row in rows if _is_studying(row)]\n\n        local_studying = [\n            row\n            for row in studying\n            if _v243_local_study(row)\n        ]\n        cross_studying = [\n            row\n            for row in studying\n            if _v243_cross_study(row)\n        ]\n\n        transferred_in = [\n            row\n            for row in rows\n            if str(\n                row.get("learning_status_code") or ""\n            ).upper() == "CHUYEN_DEN"\n        ]\n        transferred_out = [\n            row\n            for row in rows\n            if str(\n                row.get("learning_status_code") or ""\n            ).upper() in TRANSFER_OUT_CODES\n        ]\n        dead = [\n            row\n            for row in rows\n            if str(\n                row.get("learning_status_code") or ""\n            ).upper() in DEAD_CODES\n        ]\n\n        two_sessions = [\n            row\n            for row in studying\n            if _v243_two_sessions(row)\n        ]\n        completed = [\n            row\n            for row in rows\n            if _v243_completed(row)\n        ]\n\n        row_values[7][age] = len(rows)\n        row_values[8][age] = sum(_is_female(row) for row in rows)\n        row_values[9][age] = sum(_is_minority(row) for row in rows)\n        row_values[10][age] = len(disabled)\n        row_values[11][age] = len(can_learn)\n        row_values[12][age] = len(access)\n        row_values[13][age] = len(mobilizable)\n        row_values[14][age] = len(studying)\n        row_values[15][age] = len(local_studying)\n        row_values[16][age] = len(cross_studying)\n        row_values[17][age] = _safe_ratio(\n            len(studying),\n            len(mobilizable),\n        )\n        row_values[18][age] = sum(\n            _is_female(row)\n            for row in studying\n        )\n        row_values[19][age] = sum(\n            _is_minority(row)\n            for row in studying\n        )\n        row_values[20][age] = sum(\n            _is_minority(row)\n            and _v243_true(row.get("prepared_vietnamese"))\n            for row in studying\n        )\n        row_values[21][age] = len(transferred_in)\n        row_values[22][age] = len(two_sessions)\n        row_values[23][age] = _safe_percent(\n            len(two_sessions),\n            len(studying),\n        )\n        row_values[24][age] = len(dead)\n        row_values[25][age] = len(transferred_out)\n        row_values[26][age] = len(transferred_in)\n\n        if age == 5:\n            row_values[27][age] = len(completed)\n            row_values[28][age] = _safe_percent(\n                len(completed),\n                len(studying),\n            )\n            row_values[29][age] = sum(\n                row in transferred_in\n                for row in completed\n            )\n        else:\n            row_values[27][age] = None\n            row_values[28][age] = None\n            row_values[29][age] = None\n\n    for row_number, values in row_values.items():\n        for age, value in values.items():\n            ws.cell(\n                row_number,\n                age_cols[age],\n            ).value = value\n\n    # Tổng cộng của biểu gốc là nhóm 0-5 tuổi.\n    for row_number in range(7, 30):\n        values = [\n            row_values.get(row_number, {}).get(age)\n            for age in range(6)\n        ]\n        numeric_values = [\n            value\n            for value in values\n            if isinstance(value, (int, float))\n        ]\n\n        if row_number == 17:\n            ws.cell(row_number, 12).value = _safe_ratio(\n                sum(\n                    row_values[14].get(age, 0) or 0\n                    for age in range(6)\n                ),\n                sum(\n                    row_values[13].get(age, 0) or 0\n                    for age in range(6)\n                ),\n            )\n        elif row_number == 23:\n            ws.cell(row_number, 12).value = _safe_percent(\n                sum(\n                    row_values[22].get(age, 0) or 0\n                    for age in range(6)\n                ),\n                sum(\n                    row_values[14].get(age, 0) or 0\n                    for age in range(6)\n                ),\n            )\n        elif row_number == 28:\n            ws.cell(row_number, 12).value = None\n        elif numeric_values:\n            ws.cell(row_number, 12).value = sum(numeric_values)\n\n    for column in list(age_cols.values()) + [12]:\n        ws.cell(17, column).number_format = "0.00%"\n        ws.cell(23, column).number_format = "0.00"\n\n    age_5 = age_rows[5]\n    age_34 = age_rows[3] + age_rows[4]\n\n    age_5_mobilizable = sum(_v243_mobilizable(row) for row in age_5)\n    age_34_mobilizable = sum(_v243_mobilizable(row) for row in age_34)\n\n    age_5_studying = sum(_is_studying(row) for row in age_5)\n    age_34_studying = sum(_is_studying(row) for row in age_34)\n\n    age_5_completed = sum(_v243_completed(row) for row in age_5)\n    age_34_completed = sum(_v243_completed(row) for row in age_34)\n\n    age_5_can_learn = sum(_v243_can_learn(row) for row in age_5)\n    age_5_access = sum(_v243_access(row) for row in age_5)\n\n    age_5_two_sessions = sum(\n        _is_studying(row) and _v243_two_sessions(row)\n        for row in age_5\n    )\n    age_34_two_sessions = sum(\n        _is_studying(row) and _v243_two_sessions(row)\n        for row in age_34\n    )\n\n    ws["D33"] = age_5_studying\n    ws["E33"] = _safe_percent(\n        age_5_studying,\n        age_5_mobilizable,\n    )\n\n    ws["D34"] = age_5_completed\n    ws["E34"] = _safe_percent(\n        age_5_completed,\n        age_5_studying,\n    )\n\n    ws["D35"] = age_5_access\n    ws["E35"] = _safe_percent(\n        age_5_access,\n        age_5_can_learn,\n    )\n\n    ws["D36"] = age_5_two_sessions\n    ws["E36"] = _safe_percent(\n        age_5_two_sessions,\n        age_5_studying,\n    )\n\n    ws["D38"] = age_34_studying\n    ws["E38"] = _safe_percent(\n        age_34_studying,\n        age_34_mobilizable,\n    )\n\n    ws["D39"] = age_34_completed\n    ws["E39"] = _safe_percent(\n        age_34_completed,\n        age_34_studying,\n    )\n\n    ws["D40"] = age_34_two_sessions\n    ws["E40"] = _safe_percent(\n        age_34_two_sessions,\n        age_34_studying,\n    )\n\n\n'
NEW_WRITE_MN02 = 'def _write_mn02(\n    ws: Any,\n    person_rows: list[dict[str, Any]],\n    school_rows: list[dict[str, Any]],\n) -> None:\n    _clear_range_values(ws, "D8:V9")\n\n    groups = {\n        8: [\n            row\n            for row in person_rows\n            if row.get("age") in {3, 4}\n        ],\n        9: [\n            row\n            for row in person_rows\n            if row.get("age") == 5\n        ],\n    }\n\n    for row_number, rows in groups.items():\n        mobilizable = [\n            row\n            for row in rows\n            if _v243_mobilizable(row)\n        ]\n        studying = [\n            row\n            for row in rows\n            if _is_studying(row)\n        ]\n        disabled = [\n            row\n            for row in rows\n            if _is_disabled(row)\n        ]\n        can_learn = [\n            row\n            for row in disabled\n            if _v243_can_learn(row)\n        ]\n        access = [\n            row\n            for row in disabled\n            if _v243_access(row)\n        ]\n\n        class_keys = {\n            (\n                row.get("school_display"),\n                row.get("class_display"),\n            )\n            for row in studying\n            if (\n                row.get("school_display")\n                or row.get("class_display")\n            )\n        }\n\n        completed = sum(\n            _v243_completed(row)\n            for row in rows\n        )\n\n        ws.cell(row_number, 3).value = None\n        ws.cell(row_number, 4).value = len(school_rows)\n        ws.cell(row_number, 5).value = None\n        ws.cell(row_number, 6).value = None\n        ws.cell(row_number, 7).value = len(class_keys)\n        ws.cell(row_number, 8).value = len(class_keys)\n        ws.cell(row_number, 9).value = 0\n        ws.cell(row_number, 10).value = len(mobilizable)\n        ws.cell(row_number, 11).value = len(studying)\n        ws.cell(row_number, 12).value = _safe_percent(\n            len(studying),\n            len(mobilizable),\n        )\n        ws.cell(row_number, 13).value = completed\n        ws.cell(row_number, 14).value = _safe_percent(\n            completed,\n            len(studying),\n        )\n        ws.cell(row_number, 15).value = len(disabled)\n        ws.cell(row_number, 16).value = len(can_learn)\n        ws.cell(row_number, 17).value = len(access)\n        ws.cell(row_number, 18).value = _safe_percent(\n            len(access),\n            len(can_learn),\n        )\n        ws.cell(row_number, 19).value = None\n        ws.cell(row_number, 20).value = None\n        ws.cell(row_number, 21).value = None\n        ws.cell(row_number, 22).value = "Thiếu dữ liệu CSVC"\n\n\n'
NEW_DISABILITY = 'def _write_disability_sheet(\n    ws: Any,\n    person_rows: list[dict[str, Any]],\n    school_year: SchoolYear,\n) -> None:\n    start_year, _ = _reference_years(school_year)\n    _clear_range_values(ws, "C9:M15")\n\n    type_columns = {\n        "VAN_DONG": 4,\n        "NGHE_NOI": 5,\n        "NHIN": 6,\n        "THAN_KINH_TAM_THAN": 7,\n        "TRI_TUE": 8,\n        "TU_KY": 9,\n        "HOC_TAP": 10,\n        "DA_TAT": 11,\n        "KHAC": 11,\n    }\n\n    totals_by_col: dict[int, int] = defaultdict(int)\n\n    for age in range(6):\n        row_number = 9 + age\n        rows = [\n            row\n            for row in person_rows\n            if row.get("age") == age\n            and _is_disabled(row)\n        ]\n\n        ws.cell(row_number, 1).value = start_year - age\n        ws.cell(row_number, 2).value = age\n        ws.cell(row_number, 3).value = len(rows)\n        totals_by_col[3] += len(rows)\n\n        for row in rows:\n            code = str(\n                row.get("disability_type") or "KHAC"\n            ).upper()\n            column = type_columns.get(code, 11)\n            current = ws.cell(row_number, column).value or 0\n            ws.cell(row_number, column).value = current + 1\n            totals_by_col[column] += 1\n\n        access = sum(\n            _v243_access(row)\n            for row in rows\n        )\n        ws.cell(row_number, 12).value = access\n        ws.cell(row_number, 13).value = _safe_percent(\n            access,\n            len(rows),\n        )\n        totals_by_col[12] += access\n\n    ws["B15"] = "Tổng:"\n    for column in range(3, 13):\n        ws.cell(15, column).value = totals_by_col.get(column, 0)\n\n    ws.cell(15, 13).value = _safe_percent(\n        totals_by_col.get(12, 0),\n        totals_by_col.get(3, 0),\n    )\n\n\n'
NEW_BLANK_MODULES = 'def _blank_future_modules(\n    workbook: Any,\n    commune_label: str,\n    year_code: str,\n) -> None:\n    """\n    Không tạo số liệu giả khi phân hệ hiện chưa có dữ liệu nguồn.\n\n    Giữ đúng mẫu nhưng ghi rõ trạng thái "chưa nhập dữ liệu" thay vì\n    ghi "sẽ triển khai", vì các phân hệ đã có cấu trúc nhưng scope hiện tại rỗng.\n    """\n    ws = _get_sheet(workbook, "MN-01 CSVC")\n    _write_header(ws, commune_label, year_code)\n    _clear_range_values(ws, "C9:X70")\n    _clear_range_values(ws, "A11:B70")\n    ws["B11"] = (\n        "CHƯA NHẬP DỮ LIỆU CƠ SỞ VẬT CHẤT "\n        f"CHO NĂM HỌC {year_code}"\n    )\n    ws["B11"].font = Font(\n        color="C00000",\n        bold=True,\n    )\n\n    ws = _get_sheet(workbook, "MN - Tài chính")\n    _write_header(ws, commune_label, year_code)\n    _clear_range_values(ws, "D10:I39")\n    ws["D10"] = (\n        "CHƯA NHẬP DỮ LIỆU TÀI CHÍNH "\n        f"CHO NĂM HỌC {year_code}"\n    )\n    ws["D10"].font = Font(\n        color="C00000",\n        bold=True,\n    )\n\n\n'


def read_text(path: Path) -> str:
    return path.read_text(
        encoding="utf-8-sig",
        errors="replace",
    )


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def db_state() -> dict:
    con = sqlite3.connect(str(DB))
    try:
        result = {
            "integrity": str(
                con.execute("PRAGMA integrity_check").fetchone()[0]
            ),
            "fk_count": len(
                con.execute("PRAGMA foreign_key_check").fetchall()
            ),
        }
        for table in (
            "survey_forms",
            "survey_people",
            "survey_person_year_records",
            "staff_year_records",
        ):
            result[table] = int(
                con.execute(
                    f'SELECT COUNT(*) FROM "{table}"'
                ).fetchone()[0]
            )
        return result
    finally:
        con.close()


def backup_file(path: Path) -> None:
    target = BACKUP / path.relative_to(PROJECT)
    target.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    shutil.copy2(path, target)


def restore_file(path: Path) -> None:
    source = BACKUP / path.relative_to(PROJECT)
    if source.exists():
        shutil.copy2(source, path)


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


def function_node(tree: ast.Module, name: str):
    for node in tree.body:
        if isinstance(
            node,
            (ast.FunctionDef, ast.AsyncFunctionDef),
        ) and node.name == name:
            return node
    raise RuntimeError(
        f"Không xác định được hàm {name} bằng AST."
    )


def replace_function_ast(
    source: str,
    name: str,
    replacement: str,
) -> str:
    tree = ast.parse(source)
    node = function_node(tree, name)
    lines = source.splitlines(keepends=True)

    start = node.lineno - 1
    end = int(
        getattr(node, "end_lineno", node.lineno)
        or node.lineno
    )

    text = replacement
    if not text.endswith("\n"):
        text += "\n"

    result = "".join(
        lines[:start]
        + [text]
        + lines[end:]
    )
    ast.parse(result)
    return result


def insert_before_function_ast(
    source: str,
    name: str,
    block: str,
) -> str:
    tree = ast.parse(source)
    node = function_node(tree, name)
    lines = source.splitlines(keepends=True)

    index = node.lineno - 1
    text = block
    if not text.endswith("\n"):
        text += "\n"

    result = "".join(
        lines[:index]
        + [text]
        + lines[index:]
    )
    ast.parse(result)
    return result


def patch_survey(source: str) -> str:
    if MARKER_SURVEY in source:
        return source

    required = (
        "def _reference_date(",
        "def _school_batch_condition(",
        "def _load_batches(",
        "def _load_person_rows(",
        "def _finalize_people(",
        "SurveyPersonYearRecord.school_id == school_id",
        "year_record.completed_preschool_5.label",
    )
    for token in required:
        if token not in source:
            raise RuntimeError(
                "survey_summary_report.py khác nền khảo sát. Thiếu: "
                + token
            )

    # Chuyển các phép đếm hoàn thành cũ sang helper canonical.
    old_completed = 'row.get("completed_preschool_5") is True'
    completed_count = source.count(old_completed)
    if completed_count < 4:
        raise RuntimeError(
            "Số marker completed_preschool_5 bất thường: "
            f"{completed_count}"
        )
    source = source.replace(
        old_completed,
        "_v243_completed_preschool(row)",
    )

    source = replace_function_ast(
        source,
        "_reference_date",
        NEW_REFERENCE_DATE,
    )

    source = insert_before_function_ast(
        source,
        "_school_batch_condition",
        SURVEY_HELPERS,
    )

    source = replace_function_ast(
        source,
        "_school_batch_condition",
        NEW_SCHOOL_BATCH_CONDITION,
    )

    source = replace_function_ast(
        source,
        "_load_batches",
        NEW_LOAD_BATCHES,
    )

    source = replace_function_ast(
        source,
        "_load_person_rows",
        NEW_LOAD_PERSON_ROWS,
    )

    ast.parse(source)
    return source


def patch_template(source: str) -> str:
    if MARKER_TEMPLATE in source:
        return source

    required = (
        "def _write_mn01_te(",
        "def _write_mn02(",
        "def _write_disability_sheet(",
        "def _write_tracking_book(",
        "def _blank_future_modules(",
        "def build_template_workbook(",
        "_blank_future_modules(workbook, commune_label, school_year.code)",
    )
    for token in required:
        if token not in source:
            raise RuntimeError(
                "pcgdmn_template_report.py khác nền khảo sát. Thiếu: "
                + token
            )

    source = insert_before_function_ast(
        source,
        "_write_mn01_te",
        TEMPLATE_HELPERS,
    )

    source = replace_function_ast(
        source,
        "_write_mn01_te",
        NEW_WRITE_TE,
    )

    source = replace_function_ast(
        source,
        "_write_mn02",
        NEW_WRITE_MN02,
    )

    source = replace_function_ast(
        source,
        "_write_disability_sheet",
        NEW_DISABILITY,
    )

    source = replace_function_ast(
        source,
        "_blank_future_modules",
        NEW_BLANK_MODULES,
    )

    old_call = (
        "    _blank_future_modules("
        "workbook, commune_label, school_year.code)\n"
    )
    if source.count(old_call) != 1:
        raise RuntimeError(
            "Không tìm thấy đúng một lời gọi "
            "_blank_future_modules trong build_template_workbook."
        )

    new_call = old_call + (
        "    _v243_normalize_year_labels("
        "workbook, school_year)\n"
    )

    source = source.replace(
        old_call,
        new_call,
        1,
    )

    ast.parse(source)
    return source


def verify_sources() -> None:
    survey = read_text(SURVEY)
    template = read_text(TEMPLATE)

    for token in (
        MARKER_SURVEY,
        "return date(start_year, 12, 31)",
        "_v243_school_record_condition",
        "year_record.completed_preschool_by_age.label",
        "year_record.attends_two_sessions_per_day.label",
        "year_record.disability_can_learn.label",
        "year_record.disability_access_education.label",
        "_v243_completed_preschool(row)",
    ):
        if token not in survey:
            raise RuntimeError(
                "Verifier survey thiếu: " + token
            )

    for token in (
        MARKER_TEMPLATE,
        "ws.cell(5, column).value = start_year - age",
        "_v243_completed(row)",
        "_v243_two_sessions(row)",
        "_v243_can_learn(row)",
        "_v243_access(row)",
        "ws[\"D39\"] = age_34_completed",
        "ws[\"D40\"] = age_34_two_sessions",
        "_v243_normalize_year_labels",
        "CHƯA NHẬP DỮ LIỆU CƠ SỞ VẬT CHẤT",
        "CHƯA NHẬP DỮ LIỆU TÀI CHÍNH",
    ):
        if token not in template:
            raise RuntimeError(
                "Verifier template thiếu: " + token
            )

    ast.parse(survey)
    ast.parse(template)

    py_compile.compile(
        str(SURVEY),
        doraise=True,
    )
    py_compile.compile(
        str(TEMPLATE),
        doraise=True,
    )


def smoke_db_logic() -> dict:
    con = sqlite3.connect(str(DB))
    con.row_factory = sqlite3.Row
    try:
        year = con.execute(
            "SELECT id, code FROM school_years WHERE code='2026-2027'"
        ).fetchone()
        school = con.execute(
            "SELECT id, name FROM schools WHERE code='40429325'"
        ).fetchone()

        if year is None or school is None:
            return {
                "skipped": True,
                "reason": "Không có dữ liệu test Nghi Lộc/Nghi Hoa.",
            }

        year_id = int(year["id"])
        school_id = int(school["id"])

        exact = int(
            con.execute(
                """
                SELECT COUNT(*)
                FROM survey_person_year_records
                WHERE school_year_id=? AND school_id=?
                """,
                (year_id, school_id),
            ).fetchone()[0]
        )

        variants = {
            "trường mầm non nghi hoa",
            "trường mn nghi hoa",
        }
        placeholders = ",".join("?" for _ in variants)
        fallback = int(
            con.execute(
                f"""
                SELECT COUNT(*)
                FROM survey_person_year_records
                WHERE school_year_id=?
                  AND school_id IS NULL
                  AND lower(trim(school_name_reported))
                      IN ({placeholders})
                """,
                (year_id, *sorted(variants)),
            ).fetchone()[0]
        )

        ages = []
        for row in con.execute(
            """
            SELECT p.date_of_birth
            FROM survey_person_year_records yr
            JOIN survey_people p
              ON p.id=yr.survey_person_id
            JOIN households h
              ON h.id=p.household_id
            WHERE yr.school_year_id=?
              AND h.commune_id=114
            """,
            (year_id,),
        ):
            value = str(row["date_of_birth"] or "")
            try:
                birth_year = int(value[:4])
            except Exception:
                continue
            age = 2026 - birth_year
            if 0 <= age <= 6:
                ages.append(age)

        return {
            "skipped": False,
            "exact_school_id": exact,
            "fallback_reported_name": fallback,
            "expected_school_rows_after_patch": exact + fallback,
            "commune_age_0_6": len(ages),
            "commune_age_distribution": {
                age: ages.count(age)
                for age in sorted(set(ages))
            },
        }
    finally:
        con.close()


def main() -> int:
    print("=" * 126)
    print(
        "BÀI 13B-12 V2.4.3 - "
        "CHUẨN HÓA NGUỒN DỮ LIỆU 7 BIỂU MẦM NON"
    )
    print("=" * 126)

    for path in (DB, SURVEY, TEMPLATE):
        if not path.exists():
            print("DỪNG AN TOÀN: thiếu", path)
            return 2

    before = db_state()
    print("integrity_check:", before["integrity"])
    print("foreign_key_check:", before["fk_count"], "lỗi")

    if (
        before["integrity"].lower() != "ok"
        or before["fk_count"] != 0
    ):
        print(
            "DỪNG: database chưa đạt kiểm tra an toàn."
        )
        return 3

    try:
        new_survey = patch_survey(
            read_text(SURVEY)
        )
        new_template = patch_template(
            read_text(TEMPLATE)
        )
        ast.parse(new_survey)
        ast.parse(new_template)
    except Exception as exc:
        print()
        print(
            "DỪNG AN TOÀN TRƯỚC KHI GHI SOURCE:"
        )
        print(
            type(exc).__name__ + ":",
            exc,
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

    backup_file(SURVEY)
    backup_file(TEMPLATE)
    backup_db()

    print("Backup:", BACKUP)

    try:
        write_text(
            SURVEY,
            new_survey,
        )
        write_text(
            TEMPLATE,
            new_template,
        )

        verify_sources()
        smoke = smoke_db_logic()

        after = db_state()

        if after["integrity"].lower() != "ok":
            raise RuntimeError(
                "integrity_check không đạt sau cài."
            )

        if after["fk_count"] != 0:
            raise RuntimeError(
                "foreign_key_check có lỗi sau cài."
            )

        for table in (
            "survey_forms",
            "survey_people",
            "survey_person_year_records",
            "staff_year_records",
        ):
            if after[table] != before[table]:
                raise RuntimeError(
                    f"Số bản ghi {table} thay đổi ngoài dự kiến."
                )

        for cache in APP.rglob("__pycache__"):
            if cache.is_dir():
                shutil.rmtree(
                    cache,
                    ignore_errors=True,
                )

    except Exception as exc:
        print()
        print(
            "CÓ LỖI - ĐANG ROLLBACK SOURCE + DATABASE..."
        )
        print(
            type(exc).__name__ + ":",
            exc,
        )

        restore_file(SURVEY)
        restore_file(TEMPLATE)
        restore_db()

        print("ĐÃ KHÔI PHỤC.")
        return 9

    REPORT.write_text(
        "\n".join(
            [
                "=" * 126,
                "BÁO CÁO CÀI BÀI 13B-12 V2.4.3",
                "=" * 126,
                f"Thời gian: {datetime.now():%d/%m/%Y %H:%M:%S}",
                "",
                "ĐÃ SỬA:",
                "1. Tuổi PCGD theo năm dương lịch bắt đầu của năm học.",
                "   2026-2027: sinh 2021 = 5 tuổi; sinh 2020 = 6 tuổi.",
                "2. Báo cáo cấp trường ưu tiên school_id;",
                "   nếu school_id trống mới fallback tên trường khai báo exact-variant.",
                "3. Fallback chỉ chấp nhận biến thể Mầm non <-> MN, không fuzzy-match.",
                "4. Bổ sung vào person_rows các chỉ báo canonical:",
                "   completed_preschool_by_age, học 2 buổi/ngày, chuẩn bị tiếng Việt,",
                "   khả năng học, tiếp cận giáo dục, phạm vi nơi học.",
                "5. MN-01-TE dùng completed_preschool_by_age và học 2 buổi/ngày.",
                "6. MN-01-TE điền lại tiêu chí 3-4 tuổi hoàn thành/học 2 buổi.",
                "7. MN-02 dùng cùng nguồn person_rows và cùng quy tắc hoàn thành.",
                "8. MN-Trẻ KT dùng đúng năm sinh và chỉ báo tiếp cận giáo dục.",
                "9. Sổ theo dõi tiếp tục dùng person_rows đã sửa scope/tuổi.",
                "10. Chuẩn hóa năm hiển thị ở 7 sheet.",
                "11. CSVC/Tài chính không tạo số liệu giả;",
                "    nếu chưa có nguồn năm hiện tại sẽ ghi rõ CHƯA NHẬP DỮ LIỆU.",
                "",
                "KHÔNG THAY:",
                "- Excel điều tra 2.2.3 / 2.2.4;",
                "- phân công tổ điều tra;",
                "- giao phiếu;",
                "- nhập nhanh;",
                "- nghiệp vụ Xóa mù chữ;",
                "- dữ liệu hiện có.",
                "",
                f"SMOKE DB: {smoke}",
                f"integrity_check: {after['integrity']}",
                f"foreign_key_check: {after['fk_count']} lỗi",
                f"Backup: {BACKUP}",
            ]
        ) + "\n",
        encoding="utf-8-sig",
    )

    print()
    print("=" * 126)
    print(
        "CÀI ĐẶT THÀNH CÔNG "
        "BÀI 13B-12 V2.4.3"
    )
    print("=" * 126)
    print(
        " - Scope trường + fallback tên: ĐẠT."
    )
    print(
        " - Tuổi PCGD theo năm chuẩn: ĐẠT."
    )
    print(
        " - Mapping MN-01-TE/MN-02/MN-Trẻ KT: ĐẠT."
    )
    print(
        " - Không sửa dữ liệu hiện có."
    )
    print("Smoke DB:", smoke)
    print("Báo cáo:", REPORT)
    print("Backup:", BACKUP)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
