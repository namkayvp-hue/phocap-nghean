"""Additive Excel routes; retain the manual CSVC forms and their storage."""
from io import BytesIO
from pathlib import Path
import logging
import secrets
import time
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import School, SchoolYear
from app.routers import report_inputs as inputs
from app.services import csvc_excel_import as service

router = APIRouter(prefix='/csvc/nhap-excel', tags=['Nhập Excel cơ sở vật chất'])
templates = Jinja2Templates(directory='app/templates')
logger = logging.getLogger(__name__)


def context(db, request, level, year_id, school_id):
    if level not in service.LEVEL_NAMES:
        raise HTTPException(404, 'Chỉ hỗ trợ Mầm non, Tiểu học và THCS.')
    user = inputs.lay_thong_tin_nguoi_dung(request) or {}
    role = inputs.normalize_role_code(user.get('role_code'))
    unit = inputs._v2439_is_school_unit(user, role)
    if role not in inputs.CSVC_EDIT_ROLES and not unit:
        raise HTTPException(403, 'Tài khoản không có quyền nhập cơ sở vật chất.')
    allowed = inputs._v2439_school_unit_owns_target(db, user, school_id) if unit else inputs._school_in_scope(db, request, school_id)
    if not allowed:
        raise HTTPException(403, 'Trường nhận dữ liệu nằm ngoài phạm vi tài khoản.')
    year = db.get(SchoolYear, year_id)
    school = db.get(School, school_id)
    if year is None or year_id not in {y.id for y in inputs._load_school_years(db)}:
        raise HTTPException(422, 'Năm học không hợp lệ.')
    if level == 'MN':
        scope = inputs._mn_scope(db, request, year_id, school.commune_id, school_id)
    else:
        scope = inputs._structured_level_scope(db, request, service.catalog(level), year_id, school.commune_id, school_id)
    if scope['selected_school_id'] != school_id or scope['selected_year_id'] != year_id:
        raise HTTPException(403, 'Trường không thuộc cấp học hoặc phạm vi đã chọn.')
    params = urlencode(dict(school_year_id=year_id, school_id=school_id, commune_id=school.commune_id))
    back = ('/csvc/co-so' if level == 'MN' else f'/bieu-nhap/{level.lower()}-01-csvc') + '?' + params
    return dict(nguoi_dung=user, level=level, title=service.catalog(level)['title'], school=school, year=year,
                prefix=f'/csvc/nhap-excel/{level}', params=params, back_url=back)


def render(request, ctx, status=200, **extra):
    csrf = request.session.setdefault('csvc_excel_csrf', secrets.token_urlsafe(32))
    return templates.TemplateResponse(request=request, name='report_inputs/csvc_excel_import.html', context=dict(ctx, csrf=csrf, **extra), status_code=status)


def check_csrf(request, value):
    expected = request.session.get('csvc_excel_csrf', '')
    if not expected or not secrets.compare_digest(expected, value):
        raise HTTPException(403, 'Phiên thao tác không hợp lệ. Hãy tải lại trang.')


@router.get('/{level}')
def home(level: str, request: Request, school_year_id: int, school_id: int, db: Session = Depends(get_db)):
    return render(request, context(db, request, level, school_year_id, school_id))


@router.get('/{level}/mau')
def download(level: str, request: Request, school_year_id: int, school_id: int, db: Session = Depends(get_db)):
    ctx = context(db, request, level, school_year_id, school_id)
    record = service.current_record(db, level, school_year_id, school_id)
    try:
        content = service.workbook_bytes(level, ctx['school'], ctx['year'], service.saved_values(record, level))
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    return StreamingResponse(BytesIO(content), media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', headers={'Content-Disposition': f'attachment; filename="CSVC_{level}_{school_id}_{school_year_id}.xlsx"'})


@router.post('/{level}/xem-truoc')
async def preview(level: str, request: Request, school_year_id: int = Form(...), school_id: int = Form(...), csrf: str = Form(...), excel_file: UploadFile = File(...), db: Session = Depends(get_db)):
    check_csrf(request, csrf)
    ctx = context(db, request, level, school_year_id, school_id)
    request.session.pop('csvc_excel_preview', None)
    content = await excel_file.read(3 * 1024 * 1024 + 1)
    issues, rows, warnings, token = [], [], [], None
    try:
        if not (excel_file.filename or '').lower().endswith('.xlsx') or not content or len(content) > 3 * 1024 * 1024:
            raise ValueError('Chọn file .xlsx theo mẫu, tối đa 3 MB.')
        patch, issues = service.parse(content, level, ctx['school'], ctx['year'])
        record = service.current_record(db, level, school_year_id, school_id)
        if not issues:
            rows, warnings = service.preview_values(db, level, school_year_id, school_id, record, patch)
            token = secrets.token_hex(24)
            request.session['csvc_excel_preview'] = dict(token=token, actor=ctx['nguoi_dung'].get('id'), level=level,
                school_id=school_id, year_id=school_year_id, patch=patch, fingerprint=service.fingerprint(record), expires=time.time() + 1800)
    except ValueError as exc:
        issues = [dict(row=None, message=str(exc))]
    except Exception:
        logger.exception('CSVC Excel preview failed')
        issues = [dict(row=None, message='Không đọc được file Excel. Hãy tải lại mẫu và kiểm tra nội dung.')]
    return render(request, ctx, status=422 if issues else 200, preview=True, filename=Path(excel_file.filename or '').name,
                  issues=issues, rows=rows, warnings=warnings, token=token)


@router.post('/{level}/xac-nhan')
def confirm(level: str, request: Request, csrf: str = Form(...), token: str = Form(...), acknowledge: str = Form(''), db: Session = Depends(get_db)):
    check_csrf(request, csrf)
    saved = request.session.get('csvc_excel_preview') or {}
    if not saved or not secrets.compare_digest(str(saved.get('token', '')), token) or saved.get('level') != level or saved.get('expires', 0) < time.time():
        raise HTTPException(409, 'Bản xem trước hết hạn hoặc đã xử lý. Hãy kiểm tra lại file.')
    ctx = context(db, request, level, saved['year_id'], saved['school_id'])
    if saved['actor'] != ctx['nguoi_dung'].get('id'):
        raise HTTPException(403, 'Bản xem trước thuộc phiên tài khoản khác.')
    if acknowledge != 'yes':
        raise HTTPException(422, 'Cần xác nhận đã kiểm tra dữ liệu.')
    try:
        db.rollback()
        db.execute(text('BEGIN IMMEDIATE'))
        db.expire_all()
        ctx = context(db, request, level, saved['year_id'], saved['school_id'])
        record = service.current_record(db, level, saved['year_id'], saved['school_id'])
        if service.fingerprint(record) != saved['fingerprint']:
            raise ValueError('Dữ liệu đã thay đổi từ lúc xem trước. Hãy kiểm tra lại file để tránh ghi đè.')
        service.store_patch(db, level, saved['year_id'], saved['school_id'], record, saved['patch'], ctx['nguoi_dung'].get('id'))
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except ValueError as exc:
        db.rollback()
        return render(request, ctx, status=409, error=str(exc))
    except Exception:
        db.rollback()
        logger.exception('CSVC Excel import rolled back')
        return render(request, ctx, status=500, error='Chưa nhập được dữ liệu; toàn bộ thay đổi đã được hoàn tác.')
    request.session.pop('csvc_excel_preview', None)
    return RedirectResponse(ctx['back_url'] + '&status=saved', status_code=303)
