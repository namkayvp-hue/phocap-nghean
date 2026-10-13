import re
import unicodedata
from datetime import date
from sqlalchemy import inspect, text

DETAIL_COLUMNS = {
    'study_origin_address': 'VARCHAR(500)', 'study_destination_address': 'VARCHAR(500)',
    'primary_completion_year': 'INTEGER', 'lower_secondary_graduation_year': 'INTEGER',
}


def ensure_school_details_schema(engine):
    with engine.begin() as conn:
        if not inspect(conn).has_table('survey_person_year_records'):
            return
        existing = {c['name'] for c in inspect(conn).get_columns('survey_person_year_records')}
        for name, kind in DETAIL_COLUMNS.items():
            if name not in existing:
                conn.execute(text(f'ALTER TABLE survey_person_year_records ADD COLUMN {name} {kind}'))


def grade_number(value):
    value = ''.join(c for c in unicodedata.normalize('NFD', str(value or '')) if not unicodedata.combining(c)).lower().strip()
    if re.search(r'tuoi|thang|mau giao|nha tre', value):
        return None
    match = re.match(r'^(?:(?:lop|khoi)\s*)?(1[0-2]|[1-9])(?=\s|[a-z]|$)', value)
    return int(match[1]) if match else None


def completion_reference_age(birth, school_year):
    match = re.search(r'\d{4}', str(getattr(school_year, 'code', '') or ''))
    return int(match.group()) - birth.year if birth and match else None


def validate_completion_details(grade, primary, secondary, primary_year, secondary_year, birth, school_year):
    values, errors = {}, []
    age = completion_reference_age(birth, school_year)
    for expected, flag, raw, key, label in [
        (5,primary,primary_year,'primary_completion_year','hoàn thành Tiểu học'),
        (9,secondary,secondary_year,'lower_secondary_graduation_year','tốt nghiệp THCS'),
    ]:
        if flag is None and raw is None:
            continue  # Hidden/omitted controls must preserve historical facts.
        age_eligible = age is not None and (11 <= age <= 14 if expected == 5 else 15 <= age <= 18)
        if grade != expected and not age_eligible:
            if flag not in (None,'','CHUA_XAC_DINH') or raw:
                ages = '11–14' if expected == 5 else '15–18'
                errors.append(f'Chỉ nhập {label} khi đang chọn lớp {expected} hoặc đối tượng {ages} tuổi.')
            continue
        if str(flag or '').upper() not in {'CO','1','TRUE'}:
            values[key] = None
            continue
        try:
            year = int(raw or '')
            limit = min(date.today().year, int(str(getattr(school_year, 'code', '')).split('-')[-1]))
            if not max(1900, birth.year if birth else 1900) <= year <= limit:
                raise ValueError()
            values[key] = year
        except (ValueError, TypeError):
            errors.append(f'Nhập năm {label} hợp lệ, không lớn hơn năm hiện tại hoặc năm học đang chọn.')
    return values, errors
