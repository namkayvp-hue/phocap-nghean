"""Excel adapter for the existing CSVC fields. No tables or report formats change."""
from decimal import Decimal, InvalidOperation
from io import BytesIO
import hashlib
import json
from types import SimpleNamespace
from zipfile import ZipFile, BadZipFile

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

from app.report_input_models import SchoolMn01CsvcInput, SchoolStructuredReportInput
from app.structured_report_catalog import STRUCTURED_SCHOOL_FORMS, flatten_fields
from app.routers import report_inputs as inputs

MN_FIELDS = [
    ('facility_count', 'Số trường/cơ sở', 'cơ sở'),
    ('satellite_site_count', 'Số điểm trường lẻ', 'điểm'),
    ('nursery_group_count', 'Số nhóm nhà trẻ', 'nhóm'),
    ('preschool_class_3_4_count', 'Lớp mẫu giáo 3–4 tuổi', 'lớp'),
    ('preschool_class_5_count', 'Lớp mẫu giáo 5 tuổi', 'lớp'),
    ('total_classroom_count', 'Tổng số phòng học toàn trường', 'phòng'),
    ('nursery_classroom_count', 'Phòng học nhà trẻ', 'phòng'),
    ('permanent_preschool_room_count', 'Phòng mẫu giáo kiên cố', 'phòng'),
    ('semi_permanent_preschool_room_count', 'Phòng mẫu giáo bán kiên cố', 'phòng'),
    ('temporary_preschool_room_count', 'Phòng mẫu giáo tạm/nhờ', 'phòng'),
    ('equipped_preschool_class_count', 'Lớp đủ thiết bị dạy học, đồ dùng, đồ chơi', 'lớp'),
    ('toilet_count', 'Số phòng/khu vệ sinh', 'khu'),
    ('standard_toilet_count', 'Vệ sinh đạt chuẩn', 'khu'),
    ('clean_water_count', 'Số công trình nước sạch', 'công trình'),
    ('standard_clean_water_count', 'Nước sạch đạt chuẩn', 'công trình'),
    ('kitchen_count', 'Số bếp ăn', 'bếp'),
    ('standard_kitchen_count', 'Bếp ăn đạt chuẩn', 'bếp'),
    ('playground_count', 'Số sân chơi', 'sân'),
    ('playground_with_toys_count', 'Sân có đồ chơi', 'sân'),
]
LEVEL_NAMES = {'MN': 'Mầm non', 'TH': 'Tiểu học', 'THCS': 'THCS'}


def catalog(level):
    if level == 'MN':
        return dict(level='MN', form_code='MN_01_CSVC', title='MN-01-CSVC – Cơ sở vật chất Mầm non', kind='facility', groups=[dict(fields=[dict(code=code, label=label, unit=unit, type='int') for code, label, unit in MN_FIELDS])])
    return STRUCTURED_SCHOOL_FORMS[f'{level.lower()}-01-csvc']


def current_record(db, level, year_id, school_id):
    if level == 'MN':
        return inputs._csvc_record(db, year_id, school_id)
    return inputs._structured_record(db, school_id=school_id, school_year_id=year_id, form_code=catalog(level)['form_code'])


def saved_values(record, level):
    if level == 'MN':
        return {f['code']: getattr(record, f['code'], None) for f in flatten_fields(catalog(level))}
    if record is None:
        return {}
    try:
        data = json.loads(record.data_json)
    except (ValueError, TypeError):
        raise ValueError('Dữ liệu CSVC đã lưu không đọc được. Cần kiểm tra trước khi nhập thêm.')
    if not isinstance(data, dict):
        raise ValueError('Dữ liệu CSVC đã lưu không đúng cấu trúc. Chưa cập nhật dữ liệu.')
    return data


def fingerprint(record):
    snapshot = {c.name: getattr(record, c.name) for c in record.__table__.columns} if record is not None else None
    return hashlib.sha256(json.dumps(snapshot, sort_keys=True, default=str, ensure_ascii=False).encode()).hexdigest()


def display(value, kind):
    if value is None:
        return '—'
    if kind == 'yesno':
        return 'Có' if value == 1 else 'Không'
    return str(value)


def workbook_bytes(level, school, year, values):
    wb = Workbook()
    ws = wb.active
    ws.title = 'CSVC'
    ws.append([catalog(level)['title']])
    ws.append(['Cấp học', level])
    ws.append(['Năm học', year.code])
    ws.append(['Mã trường', str(school.code)])
    ws.append(['Trường', school.name])
    ws.append(['Chỉ nhập cột D. Ô trống giữ nguyên dữ liệu cũ; số 0 là giá trị cập nhật.'])
    ws.append(['Mã chỉ tiêu', 'Chỉ tiêu', 'Đơn vị', 'Giá trị'])
    for field in flatten_fields(catalog(level)):
        value = values.get(field['code'])
        if value is not None and field['type'] == 'yesno':
            value = display(value, 'yesno')
        ws.append([field['code'], field['label'], 'Có/Không' if field['type'] == 'yesno' else field.get('unit', ''), value])
        row = ws.max_row
        ws.cell(row, 4).font = Font(color='145BB0', size=11)
        ws.cell(row, 4).fill = PatternFill('solid', fgColor='EAF4FF')
        ws.cell(row, 4).number_format = '0.00' if field['type'] == 'decimal' else '0' if field['type'] == 'int' else '@'
        if field['type'] == 'yesno':
            rule = DataValidation(type='list', formula1='"Có,Không"', allow_blank=True)
        else:
            rule = DataValidation(type='whole' if field['type'] == 'int' else 'decimal', operator='greaterThanOrEqual', formula1='0', allow_blank=True)
        rule.showErrorMessage = True
        rule.errorTitle = 'Giá trị không hợp lệ'
        rule.error = 'Nhập Có/Không.' if field['type'] == 'yesno' else 'Nhập số không âm, số lượng phải là số nguyên.'
        ws.add_data_validation(rule)
        rule.add(ws.cell(row, 4))
        ws.row_dimensions[row].height = 44 if len(field['label']) > 75 else 32
    ws.column_dimensions['A'].width = 40
    ws.column_dimensions['B'].width = 78
    ws.column_dimensions['C'].width = 16
    ws.column_dimensions['D'].width = 22
    ws.freeze_panes = 'D8'
    ws.auto_filter.ref = f'A7:D{ws.max_row}'
    ws.merge_cells('A1:D1')
    ws.merge_cells('A6:D6')
    ws.row_dimensions[1].height = 30
    ws.row_dimensions[6].height = 32
    for row in ws:
        for cell in row:
            cell.alignment = Alignment(vertical='center', wrap_text=True)
            if cell.data_type == 'f':
                cell.data_type = 's'
    for row_number in (1, 7):
        for cell in ws[row_number]:
            cell.fill = PatternFill('solid', fgColor='155E9C')
            cell.font = Font(bold=True, color='FFFFFF', size=12)
    guide = wb.create_sheet('HuongDan')
    for row in [
        ('Nội dung', 'Hướng dẫn'),
        ('Phạm vi', 'Một file cho đúng một trường, một cấp học và một năm học. Giữ nguyên các dòng 2–5.'),
        ('Giá trị có sẵn', 'Mẫu chứa các chỉ tiêu đã lưu của trường trong năm học này. Số liệu tham chiếu năm trước không tự đưa vào mẫu.'),
        ('Nhập dữ liệu', 'Chỉ sửa cột Giá trị trong trang CSVC. Số lượng là số nguyên không âm; diện tích có thể là số thập phân.'),
        ('Ô trống và số 0', 'Ô trống giữ nguyên giá trị đã lưu. Nhập 0 để cập nhật một chỉ tiêu về 0.'),
        ('Xác nhận điều kiện', 'Các chỉ tiêu Có/Không nhận Có hoặc Không (cũng chấp nhận 1/0).'),
        ('Công thức', 'Chuyển công thức thành giá trị trước khi tải file lên.'),
        ('Lưu', 'Tải file lên, kiểm tra giá trị cũ/mới và cảnh báo, sau đó xác nhận. Dữ liệu sẽ hiện trong biểu nhập và báo cáo đang dùng.'),
    ]:
        guide.append(row)
    guide.column_dimensions['A'].width = 26
    guide.column_dimensions['B'].width = 100
    for row in guide:
        guide.row_dimensions[row[0].row].height = 44
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical='center')
    result = BytesIO()
    wb.save(result)
    wb.close()
    return result.getvalue()


def parse(content, level, school, year):
    try:
        with ZipFile(BytesIO(content)) as archive:
            if sum(item.file_size for item in archive.infolist()) > 25 * 1024 * 1024:
                raise ValueError('File quá lớn sau giải nén.')
        wb = load_workbook(BytesIO(content), read_only=True, data_only=False)
    except (BadZipFile, OSError, KeyError) as exc:
        raise ValueError('Không đọc được file .xlsx. Hãy tải lại mẫu CSVC.') from exc
    try:
        if 'CSVC' not in wb.sheetnames:
            raise ValueError('Thiếu trang CSVC. Hãy dùng mẫu tải từ chức năng này.')
        ws = wb['CSVC']
        if ws.max_row > 500 or ws.max_column > 8:
            raise ValueError('File không đúng kích thước mẫu CSVC của một trường.')
        table = list(ws.iter_rows())
        for cell, expected, label in [('B2', level, 'cấp học'), ('B3', year.code, 'năm học'), ('B4', str(school.code), 'mã trường')]:
            if str(ws[cell].value or '').strip() != expected:
                raise ValueError(f'File không khớp {label} đang chọn. Hãy tải mẫu đúng phạm vi.')
        if [ws.cell(7, i).value for i in range(1, 5)] != ['Mã chỉ tiêu', 'Chỉ tiêu', 'Đơn vị', 'Giá trị']:
            raise ValueError('Hàng tiêu đề đã thay đổi; hãy giữ nguyên mẫu CSVC.')
        fields = {f['code']: f for f in flatten_fields(catalog(level))}
        patch, issues, seen = {}, [], set()
        for number, cells in enumerate(table[7:], 8):
            values = [c.value for c in cells]
            if not any(v is not None and str(v).strip() for v in values):
                continue
            code = str(values[0] or '').strip()
            message = None
            if code not in fields:
                message = 'Mã chỉ tiêu không thuộc mẫu của cấp học này.'
            elif code in seen:
                message = 'Trùng mã chỉ tiêu trong file.'
            elif any(c.data_type == 'f' for c in cells):
                message = 'Chuyển công thức thành giá trị trước khi nhập.'
            elif str(values[1] or '').strip() != fields[code]['label']:
                message = 'Tên chỉ tiêu không khớp mã. Hãy giữ nguyên mã và tên chỉ tiêu.'
            elif any(v is not None and str(v).strip() for v in values[4:]):
                message = 'Chỉ nhập giá trị ở cột D; có dữ liệu ngoài mẫu.'
            seen.add(code)
            if message:
                issues.append(dict(row=number, message=message))
                continue
            raw = values[3] if len(values) > 3 else None
            if raw is None or str(raw).strip() == '':
                continue
            kind = fields[code]['type']
            try:
                if kind == 'yesno':
                    normal = str(raw).strip().casefold()
                    options = {'có': 1, 'co': 1, '1': 1, 'true': 1, 'không': 0, 'khong': 0, '0': 0, 'false': 0}
                    if normal not in options:
                        raise ValueError('Chỉ nhận Có/Không hoặc 1/0.')
                    value = options[normal]
                else:
                    if isinstance(raw, bool):
                        raise ValueError('Chỉ tiêu số lượng/diện tích phải là số.')
                    numeric = Decimal(str(raw).strip().replace(',', '.'))
                    if not numeric.is_finite() or numeric < 0 or numeric > 2147483647:
                        raise ValueError('Nhập số không âm trong phạm vi cho phép.')
                    if kind == 'int' and numeric != numeric.to_integral_value():
                        raise ValueError('Số lượng phải là số nguyên, không có phần thập phân.')
                    value = int(numeric) if kind == 'int' else float(numeric)
                patch[code] = value
            except (InvalidOperation, ValueError) as exc:
                issues.append(dict(row=number, message=f"{fields[code]['label']}: {str(exc) if isinstance(exc, ValueError) else 'Giá trị không phải là số hợp lệ.'}"))
        if not patch and not issues:
            issues.append(dict(row=None, message='Chưa có giá trị nào để nhập. Điền ít nhất một chỉ tiêu ở cột D.'))
        return patch, issues
    finally:
        wb.close()


def preview_values(db, level, year_id, school_id, record, patch):
    saved = saved_values(record, level)
    merged = {**saved, **patch}
    fields = flatten_fields(catalog(level))
    rows = [dict(label=f['label'], unit=f.get('unit', ''), old=display(saved.get(f['code']), f['type']), new=display(patch[f['code']], f['type']), changed=saved.get(f['code']) != patch[f['code']]) for f in fields if f['code'] in patch]
    if level == 'MN':
        warnings = inputs._csvc_completion(SimpleNamespace(**{f['code']: merged.get(f['code']) for f in fields}))['warnings']
    else:
        auto, class_count = inputs._structured_auto_values(db, year_id=year_id, school_id=school_id, catalog=catalog(level))
        effective, _ = inputs._structured_effective_values(catalog(level), merged, auto)
        warnings = inputs._structured_warnings(catalog(level), effective, class_count)
    return rows, warnings


def store_patch(db, level, year_id, school_id, record, patch, user_id):
    if level == 'MN':
        if record is None:
            record = SchoolMn01CsvcInput(school_id=school_id, school_year_id=year_id)
            db.add(record)
        for code, value in patch.items():
            setattr(record, code, value)
    else:
        merged = {**saved_values(record, level), **patch}
        if record is None:
            record = SchoolStructuredReportInput(school_id=school_id, school_year_id=year_id, form_code=catalog(level)['form_code'])
            db.add(record)
        record.data_json = json.dumps(merged, ensure_ascii=False, separators=(',', ':'))
    record.updated_by_user_id = user_id
    # Explicit timestamp also makes a repeated/stale confirmation detectable.
    from datetime import datetime
    record.updated_at = datetime.now()
    db.flush()
    return record
