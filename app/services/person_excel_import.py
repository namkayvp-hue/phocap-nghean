"""Admin import of person-level survey results into the existing report records."""
from datetime import date
from io import BytesIO
import hashlib
import json
import re
from uuid import uuid4
from zipfile import ZipFile

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation
from sqlalchemy import or_, select

from app.models import School, Classroom
from app.survey_models import Household, SurveyForm, SurveyPerson, SurveyPersonYearRecord
from app.survey_workflow_models import SurveyCommuneExecutionState, SurveySchoolAssignment
from app.routers.household_updates import _parse_xlsx_rows, _norm, _find_header_row, _cell_text
from app.routers.surveys import (
    LEARNING_STATUS_LABELS, DISABILITY_STATUS_LABELS,
    DISABILITY_TYPE_LABELS, DISABILITY_LEVEL_LABELS,
)


BASE_HEADERS = [
    'TT', 'Họ đệm', 'Tên', 'Ngày', 'Tháng', 'Năm sinh', 'Nữ', 'Dân tộc',
    'Tôn giáo', 'Diện ưu tiên', 'Chủ hộ - Họ đệm', 'Chủ hộ - Tên',
    'Địa chỉ: Số nhà, tên đường, tổ (nếu có)', 'Số phiếu', 'Diện cư trú',
    'Tình trạng cư trú', 'Khối học', 'Lớp học', 'Tên trường', 'Địa bàn trường',
    'Mã Trường', 'Số định danh', 'Căn cước công dân',
]
# Empty optional cells preserve the existing value. False and zero are real values.
BOOL_FIELDS = {
    'completed_preschool_5': 'Hoàn thành mầm non 5 tuổi',
    'completed_preschool_by_age': 'Hoàn thành mầm non theo độ tuổi',
    'completed_primary_program': 'Hoàn thành tiểu học',
    'completed_lower_secondary_program': 'Tốt nghiệp THCS',
    'completed_grade_3': 'Hoàn thành lớp 3', 'completed_grade_5': 'Hoàn thành lớp 5',
    'is_literacy_target': 'Thuộc diện XMC',
    'disability_can_learn': 'Khuyết tật có khả năng học',
    'disability_access_education': 'Khuyết tật được tiếp cận giáo dục',
    'inclusive_education': 'Học hòa nhập', 'is_repeating_grade': 'Lưu ban',
    'attends_required_days': 'Đi học đủ ngày', 'attends_regularly': 'Đi học chuyên cần',
    'attends_two_sessions_per_day': 'Học 2 buổi mỗi ngày',
    'prepared_vietnamese': 'Chuẩn bị tiếng Việt',
    'weight_monitored': 'Theo dõi cân nặng', 'underweight': 'Suy dinh dưỡng nhẹ cân',
    'height_monitored': 'Theo dõi chiều cao', 'stunted': 'Suy dinh dưỡng thấp còi',
    'disability_certificate': 'Có giấy xác nhận khuyết tật',
    'disability_support': 'Được hỗ trợ khuyết tật',
    'literacy_learning_support': 'Được hỗ trợ học XMC',
}
INT_FIELDS = {
    'highest_completed_grade': 'Lớp cao nhất đã hoàn thành',
    'primary_completion_year': 'Năm hoàn thành tiểu học',
    'lower_secondary_graduation_year': 'Năm tốt nghiệp THCS',
}
ENUM_FIELDS = {
    'learning_status': ('Tình trạng học tập', LEARNING_STATUS_LABELS),
    'disability_status': ('Tình trạng khuyết tật', DISABILITY_STATUS_LABELS),
    'disability_type': ('Dạng khuyết tật', DISABILITY_TYPE_LABELS),
    'disability_level': ('Mức độ khuyết tật', DISABILITY_LEVEL_LABELS),
    'education_attainment_level': ('Trình độ học vấn', {
        'CHUA_XAC_DINH': 'Chưa xác định', 'CHUA_HOAN_THANH_TIEU_HOC': 'Chưa hoàn thành tiểu học',
        'TIEU_HOC': 'Tiểu học', 'THCS': 'THCS', 'THPT': 'THPT', 'TRUNG_CAP': 'Trung cấp',
        'CAO_DANG': 'Cao đẳng', 'DAI_HOC': 'Đại học', 'SAU_DAI_HOC': 'Sau đại học', 'KHAC': 'Khác',
    }),
    'post_lower_secondary_path': ('Hướng học sau THCS', {
        'CHUA_XAC_DINH': 'Chưa xác định', 'THPT': 'THPT', 'GDTX': 'GDTX', 'GDNN': 'GDNN', 'KHONG_HOC': 'Không học',
    }),
    'current_education_program': ('Chương trình đang học', {
        'CHUA_XAC_DINH': 'Chưa xác định', 'THPT': 'THPT', 'GDTX': 'GDTX', 'GDNN': 'GDNN', 'KHAC': 'Khác',
    }),
    'study_location_scope': ('Phạm vi nơi học', {
        'CHUA_XAC_DINH': 'Chưa xác định', 'DI_HOC_TRONG_TINH': 'Đi học trong tỉnh',
        'DI_HOC_NGOAI_TINH': 'Đi học ngoài tỉnh', 'TAI_CHO': 'Tại chỗ',
        'DI_HOC_NOI_KHAC': 'Đi học nơi khác', 'NOI_KHAC_DEN': 'Nơi khác đến',
    }),
}
TEXT_FIELDS = {
    'study_origin_address': 'Địa chỉ nơi đi học chuyển đến',
    'study_destination_address': 'Địa chỉ nơi chuyển đi học',
    'literacy_support_period': 'Thời gian hỗ trợ XMC',
    'literacy_support_result': 'Kết quả hỗ trợ XMC',
    'disability_support_details': 'Nội dung hỗ trợ khuyết tật',
}
EXTRA_HEADERS = ['Thôn/xóm', 'Quan hệ với chủ hộ'] + list(BOOL_FIELDS.values()) + list(INT_FIELDS.values()) + [v[0] for v in ENUM_FIELDS.values()] + list(TEXT_FIELDS.values())
FIELD_LABELS = {**BOOL_FIELDS, **INT_FIELDS, **{k: v[0] for k, v in ENUM_FIELDS.items()}, **TEXT_FIELDS}


def make_template(batch):
    wb = Workbook()
    ws = wb.active
    ws.title = 'MauNhapLieu'
    ws.append(['Năm học', batch.school_year.code, None, 'Mã xã/phường', str(batch.commune.code)])
    ws.append(['Xã/phường', batch.commune.name])
    ws.append(['Một dòng/một đối tượng. Nhập từ dòng 6. Cùng hộ dùng cùng Số phiếu.'])
    headers = BASE_HEADERS + EXTRA_HEADERS
    ws.append(headers)
    ws.append(list(range(1, len(headers) + 1)))
    ws.freeze_panes = 'D6'
    ws.auto_filter.ref = f'A4:{get_column_letter(len(headers))}205'
    ws.row_dimensions[4].height = 62
    for col, header in enumerate(headers, 1):
        letter = get_column_letter(col)
        ws.column_dimensions[letter].width = 22 if col > 23 else (34 if col in (13, 19) else 18)
        ws.cell(4, col).fill = PatternFill('solid', fgColor='155E9C')
        ws.cell(4, col).font = Font(color='FFFFFF', bold=True)
        ws.cell(4, col).alignment = Alignment(wrap_text=True, vertical='center')
        for n in range(6, 206):
            ws.cell(n, col).number_format = '0' if header in ['TT', 'Ngày', 'Tháng', 'Năm sinh'] + list(INT_FIELDS.values()) else '@'
        if header in BOOL_FIELDS.values() or header == 'Nữ':
            validation = DataValidation(type='list', formula1='"Có,Không"', allow_blank=True)
            validation.errorTitle = 'Giá trị không hợp lệ'
            validation.error = 'Chọn Có hoặc Không; để trống nếu chưa có thông tin.'
            validation.showErrorMessage = True
            ws.add_data_validation(validation)
            validation.add(f'{letter}6:{letter}1048576')
    guide = wb.create_sheet('HuongDan')
    instructions = [
        ('Nội dung', 'Hướng dẫn nhập'),
        ('Phạm vi', 'Một file cho một xã và một đợt/năm học. Giữ nguyên thông tin ở dòng 1–2.'),
        ('Bắt buộc', 'Họ đệm/Tên, ngày/tháng/năm sinh, tên chủ hộ, địa chỉ và số phiếu. Nữ: Có hoặc Không.'),
        ('Định danh', 'Nhập dạng văn bản để giữ số 0 đầu. Có thể để trống khi chưa có định danh.'),
        ('Trường/lớp', 'Ưu tiên mã trường. Tên trường không có trong danh mục vẫn được lưu đúng như khai báo.'),
        ('Ô trống', 'Cột bổ sung để trống sẽ giữ dữ liệu cũ, không có nghĩa là Không. Không xóa người vắng khỏi file.'),
        ('Kết quả điều tra', 'Chọn chế độ hoàn thành trên trang nhập chỉ khi file đủ thành viên của từng hộ và đã kiểm tra kết quả.'),
        ('Báo cáo', 'Phiếu hoàn thành được dùng làm nguồn báo cáo. Quy trình chốt/khóa để xuất báo cáo chính thức vẫn giữ nguyên.'),
        ('XMC', 'Hoàn thành lớp 3/5 chỉ nhập theo kết quả thực tế; không suy ra từ tuổi hoặc tên lớp hiện tại.'),
        ('Bổ sung', 'Các thông tin chưa có trong mẫu tiếp tục cập nhật ở hồ sơ đối tượng hoặc phần dữ liệu bổ sung báo cáo.'),
    ]
    for field, (label, choices) in ENUM_FIELDS.items():
        instructions.append((label, '; '.join(f'{key}: {value}' for key, value in choices.items())))
    for row in instructions:
        guide.append(row)
    guide.column_dimensions['A'].width = 28
    guide.column_dimensions['B'].width = 110
    for row in guide:
        guide.row_dimensions[row[0].row].height = 42
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical='top')
    output = BytesIO()
    wb.save(output)
    return output.getvalue()


def parse_file(content, batch):
    with ZipFile(BytesIO(content)) as archive:
        if sum(i.file_size for i in archive.infolist()) > 100 * 1024 * 1024:
            raise ValueError('File quá lớn sau giải nén; hãy chia nhỏ file.')
    wb = load_workbook(BytesIO(content), data_only=False)
    ws = wb['MauNhapLieu'] if 'MauNhapLieu' in wb.sheetnames else wb.worksheets[0]
    if ws.max_row > 20005 or ws.max_column > 100:
        raise ValueError('Mỗi file tối đa 20.000 đối tượng và 100 cột.')
    header_row, _ = _find_header_row(ws)
    columns = {}
    for cell in ws[header_row]:
        key = _norm(cell.value)
        if key:
            if key in columns:
                raise ValueError(f'Trùng cột {cell.value}.')
            columns[key] = cell.column
    for row in ws.iter_rows(min_row=header_row + 1):
        if any(c.data_type == 'f' for c in row):
            raise ValueError(f'Dòng {row[0].row}: hãy chuyển công thức thành giá trị trước khi nhập.')
    rows, issues, metadata = _parse_xlsx_rows(content, batch)
    # The legacy parser stops after 25 blank lines. Do not silently omit later people.
    last_row = max((r['row_number'] for r in rows), default=header_row + 1)
    if any(any(c.value is not None for c in row) for row in ws.iter_rows(min_row=last_row + 1)):
        raise ValueError('Có dữ liệu sau nhiều dòng trống. Hãy xóa dòng trống giữa danh sách rồi kiểm tra lại.')
    if _norm(ws['D1'].value) == _norm('Mã xã/phường') and str(ws['E1'].value or '').strip() != str(batch.commune.code):
        raise ValueError('Mã xã/phường trong file không khớp đợt nhận dữ liệu.')
    seen = set()
    def read(row, label):
        col = columns.get(_norm(label))
        return _cell_text(ws.cell(row['row_number'], col)) if col else ''
    def error(row, message):
        issues.append({'row': row['row_number'], 'message': message, 'severity': 'ERROR'})
    for row in rows:
        keys = [('person', row['form_number'], _norm(row['full_name']), str(row['date_of_birth']))]
        keys += [('id', row[key]) for key in ('personal_id', 'citizen_id') if row[key]]
        # A person's personal ID and citizen ID may be the same on a single row.
        for key in set(keys):
            if key in seen:
                error(row, 'Đối tượng hoặc định danh xuất hiện nhiều lần trong file.')
            seen.add(key)
        female = _norm(read(row, 'Nữ'))
        if female not in {'', 'CO', 'KHONG', 'X', '1', '0', 'NU', 'NAM'}:
            error(row, 'Cột Nữ chỉ nhận Có/Không, X hoặc 1/0.')
        row['gender_supplied'] = bool(female)
        row['extra'] = {}
        for field, label in BOOL_FIELDS.items():
            value = _norm(read(row, label))
            if not value:
                continue
            if value not in {'CO', 'KHONG', '1', '0', 'TRUE', 'FALSE', 'X'}:
                error(row, f'{label}: chỉ nhận Có hoặc Không.')
            else:
                row['extra'][field] = value in {'CO', '1', 'TRUE', 'X'}
        for field, label in INT_FIELDS.items():
            value = read(row, label)
            if not value:
                continue
            maximum = 12 if field == 'highest_completed_grade' else min(date.today().year, int(batch.school_year.code[-4:]))
            minimum = 0 if field == 'highest_completed_grade' else max(1900, row['date_of_birth'].year if row['date_of_birth'] else 1900)
            if not value.isdigit() or not minimum <= int(value) <= maximum:
                error(row, f'{label}: cần số nguyên từ {minimum} đến {maximum}.')
            else:
                row['extra'][field] = int(value)
        for field, (label, choices) in ENUM_FIELDS.items():
            value = read(row, label)
            if value:
                matched = next((k for k, v in choices.items() if _norm(value) in {_norm(k), _norm(v)}), None)
                if matched is None:
                    error(row, f'{label}: giá trị không hợp lệ; xem trang HuongDan của mẫu.')
                else:
                    row['extra'][field] = matched
        for field, label in TEXT_FIELDS.items():
            value = read(row, label)
            if value:
                length = getattr(SurveyPersonYearRecord.__table__.columns[field].type, 'length', None) or 2000
                if len(value) > length:
                    error(row, f'{label}: tối đa {length} ký tự.')
                else:
                    row['extra'][field] = value
        row['hamlet_name'] = read(row, 'Thôn/xóm') or None
        row['relationship'] = read(row, 'Quan hệ với chủ hộ')
        row['learning_supplied'] = bool(read(row, 'Tình trạng học tập') or row['school_name'] or row['class_name'] or row['level'])
        row['residency_supplied'] = bool(read(row, 'Diện cư trú') or read(row, 'Tình trạng cư trú'))
    wb.close()
    return rows, issues


def check_unlocked(db, batch):
    state = db.scalar(select(SurveyCommuneExecutionState).where(SurveyCommuneExecutionState.survey_batch_id == batch.id))
    school_lock = db.scalar(select(SurveySchoolAssignment.id).where(SurveySchoolAssignment.survey_batch_id == batch.id, SurveySchoolAssignment.is_locked.is_(True)))
    if batch.is_locked or batch.status == 'DA_KET_THUC' or (state and (state.is_commune_locked or state.is_province_locked)) or school_lock:
        raise ValueError('Đợt hoặc nhiệm vụ điều tra đã khóa. Cần mở khóa theo quy trình trước khi nhập.')


def snapshot(obj):
    if obj is None:
        return None
    return {c.name: getattr(obj, c.name) for c in obj.__table__.columns}


def build_plan(db, batch, rows, complete):
    check_unlocked(db, batch)
    issues, snapshots, output = [], [snapshot(batch)], []
    forms = {f.form_number: f for f in db.scalars(select(SurveyForm).where(SurveyForm.survey_batch_id == batch.id)).all()}
    schools = list(db.scalars(select(School).where(School.is_active.is_(True))).all())
    matched_people = set()
    for row in rows:
        def error(message):
            issues.append({'row': row['row_number'], 'message': message})
        form = forms.get(row['form_number'])
        household = db.get(Household, form.household_id) if form else None
        if form and (form.status == 'DA_DUYET' or form.commune_confirmed_at or form.household_confirmed_at):
            error('Phiếu đã được xác nhận/duyệt. Hãy mở lại theo quy trình trước khi cập nhật.')
        if household and (_norm(household.head_name) != _norm(row['head_name']) or _norm(household.address) != _norm(row['address'])):
            error('Số phiếu đã thuộc hộ có tên chủ hộ/địa chỉ khác. Kiểm tra lại để tránh ghi đè nhầm hộ.')
        identifiers = {row[k] for k in ('personal_id', 'citizen_id') if row[k]}
        people = list(db.scalars(select(SurveyPerson).where(or_(SurveyPerson.personal_id.in_(identifiers), SurveyPerson.citizen_id.in_(identifiers)))).all()) if identifiers else []
        if household:
            local = list(db.scalars(select(SurveyPerson).where(SurveyPerson.household_id == household.id, SurveyPerson.date_of_birth == row['date_of_birth'])).all())
            people = list({p.id: p for p in people + [p for p in local if _norm(p.full_name) == _norm(row['full_name'])]}.values())
        person = people[0] if len(people) == 1 else None
        if len(people) > 1:
            error('Thông tin khớp nhiều đối tượng; cần xử lý trùng trước khi nhập.')
        if person:
            if not person.is_active or not household or person.household_id != household.id:
                error('Đối tượng đang ở hộ/địa bàn khác hoặc đã ngừng hoạt động; cần xử lý chuyển hộ riêng.')
            if _norm(person.full_name) != _norm(row['full_name']) or person.date_of_birth != row['date_of_birth']:
                error('Định danh không khớp họ tên/ngày sinh đã lưu.')
            for field in ('personal_id', 'citizen_id'):
                if row[field] and getattr(person, field) and row[field] != getattr(person, field):
                    error('Định danh trong file khác định danh của đối tượng đã lưu.')
            if person.id in matched_people:
                error('Nhiều dòng cùng trỏ đến một đối tượng đã lưu.')
            matched_people.add(person.id)
        candidates = [s for s in schools if s.code == row['school_code']] if row['school_code'] else [s for s in schools if _norm(s.name) == _norm(row['school_name'])] if row['school_name'] else []
        if row['school_code'] and not candidates:
            error('Mã trường không có trong danh mục đang hoạt động.')
        if len(candidates) > 1:
            error('Tên trường bị trùng; hãy nhập Mã Trường để xác định đúng trường.')
        school = candidates[0] if len(candidates) == 1 else None
        if school and row['school_code'] and row['school_name'] and _norm(school.name) != _norm(row['school_name']):
            error('Mã trường và tên trường không khớp danh mục.')
        record = db.scalar(select(SurveyPersonYearRecord).where(SurveyPersonYearRecord.survey_form_id == form.id, SurveyPersonYearRecord.survey_person_id == person.id, SurveyPersonYearRecord.school_year_id == batch.school_year_id)) if form and person else None
        effective = {field: row['extra'].get(field, getattr(record, field, None)) for field in BOOL_FIELDS}
        if effective['completed_grade_5'] is True and effective['completed_grade_3'] is False:
            error('Kết quả hoàn thành lớp 5 mâu thuẫn với chưa hoàn thành lớp 3.')
        for year_field, flag in [('primary_completion_year', 'completed_primary_program'), ('lower_secondary_graduation_year', 'completed_lower_secondary_program')]:
            if row['extra'].get(year_field) is not None and effective[flag] is not True:
                error(f'{INT_FIELDS[year_field]} cần đi kèm xác nhận đã hoàn thành.')
        if complete and not person and not row['gender_supplied']:
            error('Nhập Có/Không ở cột Nữ cho đối tượng mới trước khi xác nhận hoàn thành.')
        learning = row['extra'].get('learning_status', row['learning_status'] if row['learning_supplied'] else getattr(record, 'learning_status', None))
        if complete and learning in (None, '', 'CHUA_XAC_DINH'):
            error('Cần xác định Tình trạng học tập trước khi xác nhận kết quả hoàn thành.')
        if form and form.status == 'DA_HOAN_THANH' and not complete:
            error('Phiếu đã hoàn thành. Chọn xác nhận kết quả hoàn thành sau khi rà soát đủ thành viên.')
        snapshots.extend(snapshot(obj) for obj in (form, household, person, record, school))
        output.append(dict(row, form_id=form.id if form else None, household_id=household.id if household else None, person_id=person.id if person else None, record_id=record.id if record else None, school_id=school.id if school else None, action='Cập nhật' if person else 'Thêm mới'))
    for number in {r['form_number'] for r in rows}:
        form = forms.get(number)
        if form:
            members = list(db.scalars(select(SurveyPerson).where(SurveyPerson.household_id == form.household_id, SurveyPerson.is_active.is_(True))).all())
            snapshots.extend(snapshot(p) for p in members)
            if complete and any(p.id not in matched_people for p in members):
                issues.append({'row': None, 'message': f'Phiếu {number}: file thiếu thành viên đang hoạt động. Chưa thể xác nhận cả hộ hoàn thành.'})
    digest = hashlib.sha256(json.dumps(snapshots, sort_keys=True, default=str, ensure_ascii=False).encode()).hexdigest()
    return output, issues, digest


def apply_plan(db, batch, plan, complete, job_code):
    forms = {}
    summary = dict(households_created=0, households_updated=0, people_created=0, people_updated=0)
    for row in plan:
        number = row['form_number']
        if number not in forms:
            form = db.get(SurveyForm, row['form_id']) if row['form_id'] else None
            household = db.get(Household, row['household_id']) if row['household_id'] else None
            if form is None:
                household = Household(code='HO-IMP-' + uuid4().hex, commune_id=batch.commune_id, head_name=row['head_name'], address=row['address'], hamlet_name=row['hamlet_name'], is_active=True)
                db.add(household)
                db.flush()
                form = SurveyForm(survey_batch_id=batch.id, household_id=household.id, form_number=number, head_name_snapshot=row['head_name'], address_snapshot=row['address'], hamlet_name_snapshot=row['hamlet_name'])
                db.add(form)
                db.flush()
                summary['households_created'] += 1
            else:
                summary['households_updated'] += 1
            if row['hamlet_name']:
                household.hamlet_name = form.hamlet_name_snapshot = row['hamlet_name']
            form.status = 'DA_HOAN_THANH' if complete else 'DANG_DIEU_TRA'
            form.notes = (form.notes + '\n' if form.notes else '') + f'Nhập chi tiết Excel {job_code}'
            forms[number] = form
        form = forms[number]
        person = db.get(SurveyPerson, row['person_id']) if row['person_id'] else None
        if person is None:
            person = SurveyPerson(code='DT-IMP-' + uuid4().hex, household_id=form.household_id, full_name=row['full_name'], date_of_birth=row['date_of_birth'], gender=row['gender'] if row['gender_supplied'] else 'CHUA_XAC_DINH', permanent_address=row['address'], current_address=row['address'], is_active=True)
            db.add(person)
            db.flush()
            summary['people_created'] += 1
        else:
            summary['people_updated'] += 1
        for field in ('personal_id', 'citizen_id', 'ethnic_group'):
            if row[field]:
                setattr(person, field, row[field])
        if row['gender_supplied']:
            person.gender = row['gender']
        if row['relationship']:
            person.relationship_to_head = row['relationship']
        if row['residency_supplied']:
            person.residency_status = row['residency_status']
        if row['special']:
            person.special_circumstances = row['special']
        if row['religion']:
            note = 'Tôn giáo: ' + row['religion']
            if note not in (person.notes or ''):
                person.notes = (person.notes + '\n' if person.notes else '') + note
        record = db.get(SurveyPersonYearRecord, row['record_id']) if row['record_id'] else None
        if record is None:
            record = SurveyPersonYearRecord(survey_form_id=form.id, survey_person_id=person.id, school_year_id=batch.school_year_id)
            db.add(record)
        if row['school_id'] or row['school_name']:
            school_changed = record.school_id != row['school_id'] or (row['school_name'] and _norm(record.school_name_reported) != _norm(row['school_name']))
            record.school_id = row['school_id']
            if school_changed:
                record.class_id = None
                # An old class must not remain attached to a different school.
                record.class_name_reported = None
            record.school_name_reported = row['school_name'] or db.get(School, row['school_id']).name
        if row['class_name']:
            record.class_name_reported = row['class_name']
            record.class_id = None
            if record.school_id:
                classes = list(db.scalars(select(Classroom).where(Classroom.school_id == record.school_id, Classroom.school_year_id == batch.school_year_id, Classroom.is_active.is_(True))).all())
                matches = [c for c in classes if _norm(c.name) == _norm(row['class_name'])]
                if len(matches) == 1:
                    record.class_id = matches[0].id
        if row['learning_supplied']:
            record.learning_status = row['learning_status']
        if row['special']:
            record.special_circumstances = row['special']
        for field, value in row['extra'].items():
            setattr(record, field, value)
        if any(key in row['extra'] for key in ('is_literacy_target', 'completed_grade_3', 'completed_grade_5')):
            if record.is_literacy_target is True and (record.completed_grade_3 is False or record.completed_grade_5 is False):
                record.literacy_status = 'THEO_DOI_XMC'
            elif record.is_literacy_target is True and record.completed_grade_3 is True and record.completed_grade_5 is True:
                record.literacy_status = 'KHONG_THUOC_DIEN'
            else:
                record.literacy_status = 'CHUA_XAC_DINH'
        record.is_reviewed = bool(complete)
        db.flush()
    return summary
