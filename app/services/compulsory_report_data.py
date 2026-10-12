"""Scoped, year-specific inputs for appendices 2, 4 and 5. Read-only."""
import json
import re
import math
from collections import defaultdict
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.models import School, Classroom
from app.staff_models import StaffYearRecord
from app.report_input_models import SchoolStructuredReportInput, SchoolNetworkYearData
from app.pcgd_xmc_report_builders_v1 import _norm
from app.services.xmc_appendix_reports import collect, ratio


def tri_all(*values):
    return False if False in values else None if None in values else True


def known(value):
    return value if isinstance(value, bool) else None


def count(items, predicate):
    values = [predicate(x) for x in items]
    return None if None in values else sum(v is True for v in values)


def total(values):
    values = list(values)
    return None if not values or None in values else sum(values)


def attr(x, key):
    return getattr(x['record'], key, None)


def disabled(x):
    value = attr(x, 'disability_status')
    return {'CO_KHUYET_TAT': True, 'KHONG_KHUYET_TAT': False}.get(value)


def capable(x):
    return tri_all(disabled(x), known(attr(x, 'disability_can_learn')))


def accessible(x):
    return tri_all(capable(x), known(attr(x, 'disability_access_education')))


def studying(x):
    s = attr(x, 'learning_status')
    return None if s in (None, '', 'CHUA_XAC_DINH') else s == 'DANG_HOC'


def grade(x):
    r = x['record']
    if r is None:
        return None
    from app.routers.household_updates import _level_from_record
    if _level_from_record(r, r.school, r.classroom) == 'MN':
        return 0
    name = r.class_name_reported or (r.classroom.name if r.classroom else '')
    m = re.fullmatch(r'(?:LOP\s*)?(1[0-2]|[1-9])(?:\s*[A-Z][A-Z0-9]*)?', _norm(name))
    return int(m[1]) if m else None


def in_grade(x, low, high):
    g = grade(x)
    return tri_all(studying(x), None if g is None else low <= g <= high)


def completed(x, level):
    return known(attr(x, 'completed_primary_program' if level == 'TH' else 'completed_lower_secondary_program'))


def upper(x):
    value = attr(x, 'post_lower_secondary_path')
    if value in {'THPT', 'GDTX', 'GDNN'}:
        return True
    if value and value != 'CHUA_XAC_DINH':
        return False
    if in_grade(x, 10, 12) is True:
        return True
    return None


def ppc(x):
    residency = x['person'].residency_status
    resident = None if residency in (None, '', 'CHUA_XAC_DINH') else residency == 'THUONG_TRU'
    status = attr(x, 'learning_status')
    eligible = None if status in (None, '', 'CHUA_XAC_DINH') else status not in {'KHONG_THUOC_DIEN', 'KHONG_THUOC_DIEN_THEO_DOI'}
    return tri_all(resident, eligible)


def location(x):
    return {'TAI_CHO': 'local', 'DI_HOC_TRONG_TINH': 'other', 'DI_HOC_NGOAI_TINH': 'other',
            'DI_HOC_NOI_KHAC': 'other', 'NOI_KHAC_DEN': 'inbound'}.get(attr(x, 'study_location_scope'))


def program(x):
    value = attr(x, 'current_education_program')
    if value == 'GDTX':
        return 'TX'
    if value == 'GDNN':
        return 'GDNN'
    if value == 'THPT':
        return 'PT'
    r = x['record']
    name = _norm((r.school.name if r and r.school else '') or attr(x, 'school_name_reported'))
    if 'GDTX' in name:
        return 'TX'
    if 'GDNN' in name:
        return 'GDNN'
    if 'THCS' in name or 'TRUNG HOC CO SO' in name:
        return 'PT'
    return None


class Population:
    def __init__(self, ctx):
        self.items = collect(ctx['people'], ctx['evidence'], ctx['reference_year'])
        self.missing_birth = any(x['age'] is None for x in self.items)

    def group(self, low, high):
        return [x for x in self.items if x['age'] is not None and low <= x['age'] <= high]

    def number(self, low, high, predicate=lambda x: True):
        return None if self.missing_birth else count(self.group(low, high), predicate)

    def metric(self, low, high, predicate, denominator=lambda x: True):
        n = self.number(low, high, lambda x: tri_all(denominator(x), predicate(x)))
        d = self.number(low, high, denominator)
        return n, d, ratio(n, d)

    def indicators(self):
        return {
            'entry6': self.metric(6, 6, lambda x: in_grade(x, 1, 1)),
            'primary11': self.metric(11, 11, lambda x: completed(x, 'TH')),
            'primary_study11': self.metric(11, 11, lambda x: in_grade(x, 1, 5)),
            'primary6_14': self.metric(6, 14, lambda x: completed(x, 'TH')),
            'primary14': self.metric(14, 14, lambda x: completed(x, 'TH')),
            'disabled6_14': self.metric(6, 14, accessible, capable),
            'secondary15_18': self.metric(15, 18, lambda x: completed(x, 'THCS')),
            'secondary15': self.metric(15, 15, lambda x: completed(x, 'THCS')),
            'secondary18': self.metric(18, 18, lambda x: completed(x, 'THCS')),
            'upper15_18': self.metric(15, 18, upper),
            'disabled11_18': self.metric(11, 18, accessible, capable),
        }


def numeric(value):
    if value in (None, '') or isinstance(value, bool):
        return int(value) if isinstance(value, bool) else None
    try:
        value = float(value)
        return (int(value) if value.is_integer() else value) if math.isfinite(value) and value >= 0 else None
    except (ValueError, TypeError):
        return None


def parse_data(record):
    try:
        data = json.loads(record.data_json)
        return data if isinstance(data, dict) else {}
    except (ValueError, TypeError):
        return {}


def staff_values(rows):
    """Counts from current active records; unknown attributes remain unknown."""
    if not rows:
        return {}
    teachers = [r for r in rows if r.position_group == 'GIAO_VIEN']
    managers = [r for r in rows if r.position_group == 'CBQL']
    employees = [r for r in rows if r.position_group == 'NHAN_VIEN']
    def tally(records, field, accepted, allowed=None):
        vals = [_norm(getattr(r, field, None)) for r in records]
        if any(not v or v in {'CHUA XAC DINH', 'CHUA DANH GIA'} or (allowed and v not in allowed) for v in vals):
            return None
        return sum(v in accepted for v in vals)
    vals = {'teacher_total': len(teachers)}
    vals['principal'] = tally(managers, 'position_title', {'HIEU TRUONG'})
    vals['vice_principal'] = tally(managers, 'position_title', {'PHO HIEU TRUONG', 'P HIEU TRUONG'})
    for key, value in [('teacher_permanent', 'BIEN CHE'), ('teacher_contract', 'HOP DONG')]:
        vals[key] = tally(teachers, 'employment_type', {value}, {'BIEN CHE', 'HOP DONG'})
    vals['teacher_female'] = tally([r.staff_member for r in teachers], 'gender', {'NU', 'FEMALE', 'F'}, {'NU','NAM','FEMALE','MALE','F','M'})
    ethnic = [_norm(r.staff_member.ethnic_group) for r in teachers]
    vals['teacher_ethnic'] = None if any(not v or v == 'CHUA XAC DINH' for v in ethnic) else sum(v not in {'KINH','K'} for v in ethnic)
    quals = {'qual_postgrad': {'THAC SI', 'TIEN SI'}, 'qual_university': {'DAI HOC'},
             'qual_college': {'CAO DANG'}, 'qual_secondary': {'TRUNG CAP'}}
    for key, accepted in quals.items():
        vals[key] = tally(teachers, 'qualification_level', accepted)
    for key, accepted in [('prof_excellent', {'TOT'}), ('prof_good', {'KHA'}),
                          ('prof_average', {'DAT'}), ('prof_poor', {'CHUA DAT'})]:
        vals[key] = tally(teachers, 'professional_standard', accepted)
    for key, names in [('employee_office', {'VAN PHONG','VAN THU'}), ('employee_library', {'THU VIEN'}),
                       ('employee_equipment_lab', {'THIET BI','THI NGHIEM'}), ('employee_health', {'Y TE'})]:
        vals[key] = tally(employees, 'position_title', names)
    vals['employee_library_equipment'] = tally(employees, 'position_title', {'THU VIEN','THIET BI','THI NGHIEM'})
    specialties = {
        'math': {'TOAN'}, 'literature': {'NGU VAN', 'VAN'}, 'physics': {'VAT LY', 'LY'},
        'chemistry': {'HOA HOC','HOA'}, 'biology': {'SINH HOC','SINH'}, 'history': {'LICH SU','SU'},
        'geography': {'DIA LY','DIA'}, 'music': {'AM NHAC','NHAC'}, 'art': {'MY THUAT'},
        'pe': {'THE DUC','GIAO DUC THE CHAT'}, 'civic': {'GIAO DUC CONG DAN','GDCD'},
        'technology': {'CONG NGHE'}, 'it': {'TIN HOC'}, 'english': {'TIENG ANH'},
        'russian': {'TIENG NGA'}, 'french': {'TIENG PHAP'}, 'primary': {'TIEU HOC','GIAO DUC TIEU HOC'},
    }
    # A teaching assignment is not proof of the training specialty in the form.
    subjects = [_norm(r.main_specialty) for r in teachers]
    for key, accepted in specialties.items():
        n = None if any(not v or v=='CHUA XAC DINH' for v in subjects) else sum(v in accepted for v in subjects)
        vals['subject_'+key] = n
        vals['training_'+key] = n
    foreign = specialties['english'] | specialties['russian'] | specialties['french'] | {'NGOAI NGU'}
    vals['training_foreign'] = None if any(not v or v=='CHUA XAC DINH' for v in subjects) else sum(v in foreign for v in subjects)
    return vals


def school_data(db, ctx, level):
    """Never borrow a different year's data, or expand a teacher's school scope."""
    cache = ctx.setdefault('_school_report_data', {})
    if level in cache:
        return cache[level]
    year = ctx['year'].id
    school_id = ctx['school_id']
    if ctx['user']['role_code'] in {'TRUONG', 'GIAO_VIEN'}:
        school_id = ctx['user'].get('school_id')
        if not school_id:
            return []
    query = select(School).where(School.is_active.is_(True), School.commune_id.in_([c.id for c in ctx['communes']]))
    if school_id is not None:
        query = query.where(School.id == school_id)
    schools = list(db.scalars(query.order_by(School.name)))
    ids = [s.id for s in schools]
    networks = {r.school_id: parse_data(r) for r in db.scalars(select(SchoolNetworkYearData).where(
        SchoolNetworkYearData.school_id.in_(ids), SchoolNetworkYearData.school_year_id == year,
        SchoolNetworkYearData.level_code == level))}
    forms = {(r.school_id, r.form_code): parse_data(r) for r in db.scalars(select(SchoolStructuredReportInput).where(
        SchoolStructuredReportInput.school_id.in_(ids), SchoolStructuredReportInput.school_year_id == year,
        SchoolStructuredReportInput.form_code.in_([level+'_01_GV', level+'_01_CSVC'])))}
    def supports(s):
        name = _norm(s.name)
        matches = ('THCS' in name or 'TRUNG HOC CO SO' in name) if level == 'THCS' else ('TIEU HOC' in name or bool(re.search(r'\bTH\b', name)))
        return s.id in networks or (s.id, level+'_01_GV') in forms or (s.id, level+'_01_CSVC') in forms or matches
    schools = [s for s in schools if supports(s)]
    ids = [s.id for s in schools]
    staff = defaultdict(list)
    for r in db.scalars(select(StaffYearRecord).where(StaffYearRecord.school_id.in_(ids), StaffYearRecord.school_year_id == year,
            StaffYearRecord.teaching_level.in_([level, 'KHONG_DAY']),
            StaffYearRecord.is_active.is_(True), StaffYearRecord.status_code == 'DANG_LAM_VIEC').options(selectinload(StaffYearRecord.staff_member))):
        if r.staff_member.is_active and r.teaching_level in {level, 'KHONG_DAY'}:
            staff[r.school_id].append(r)
    classes = defaultdict(list)
    for r in db.scalars(select(Classroom).where(Classroom.school_id.in_(ids), Classroom.school_year_id == year, Classroom.is_active.is_(True))):
        match = re.fullmatch(r'(?:LOP\s*)?(1[0-2]|[1-9])(?:\s*[A-Z][A-Z0-9]*)?', _norm(r.name))
        if match and (1 <= int(match[1]) <= 5 if level == 'TH' else 6 <= int(match[1]) <= 9):
            classes[r.school_id].append(r)
    output = []
    for s in schools:
        net = networks.get(s.id, {})
        values = {key: numeric(value) for key, value in net.items()}
        for old, new in [('teachers','teacher_total'), ('rooms_permanent','room_permanent'),
                         ('rooms_semi_permanent','room_semi_permanent'), ('rooms_temporary','room_temporary')]:
            if old in net:
                values[new] = numeric(net[old])
        values.update({k:v for k,v in staff_values(staff[s.id]).items() if v is not None})
        # A linked class roster alone need not be complete; prefer saved year totals.
        if values.get('class_total') is None and classes[s.id]:
            values['class_total'] = len(classes[s.id])
        for kind in ('GV', 'CSVC'):
            values.update({k:numeric(v) for k,v in forms.get((s.id,level+'_01_'+kind),{}).items() if v not in (None,'')})
        values['teacher_ratio'] = round(values['teacher_total']/values['class_total'], 2) if values.get('teacher_total') is not None and values.get('class_total') else None
        rooms = total(values.get(k) for k in (['room_permanent','room_semi_permanent','room_temporary','room_rent_borrow'] if level=='TH' else ['room_permanent','room_semi_permanent','room_temporary']))
        values['room_ratio'] = round(rooms/values['class_total'],2) if rooms is not None and values.get('class_total') else None
        output.append((s, values))
    cache[level] = output
    return output
