"""Preview and explicitly confirm admin person imports, with no schema changes."""
from datetime import datetime
from contextlib import closing
from pathlib import Path
from io import BytesIO
import hashlib
import secrets
import sqlite3
import time
import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, text
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.models import SchoolYear
from app.permissions import is_admin_role
from app.survey_models import SurveyBatch
from app.household_import_models import HouseholdImportJob
from app.services import person_excel_import as service

PREFIX = '/cong-cu-du-lieu/nhap-chi-tiet-doi-tuong'
ROOT = Path(__file__).resolve().parents[2] / 'exports' / 'person_imports'
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parents[1] / 'templates'))
router = APIRouter(prefix=PREFIX, tags=['Nhập chi tiết đối tượng'])
logger = logging.getLogger(__name__)


def admin(request):
    user = request.scope.get('auth_user') or {}
    if not is_admin_role(user.get('role_code')):
        raise HTTPException(403, 'Chỉ tài khoản admin được nhập chi tiết đối tượng tại Công cụ dữ liệu.')
    return user


def csrf_check(request, token):
    expected = request.session.get('person_import_csrf', '')
    if not expected or not secrets.compare_digest(expected, token):
        raise HTTPException(403, 'Phiên thao tác không hợp lệ. Tải lại trang để tiếp tục.')


def get_batch(db, batch_id):
    batch = db.scalar(select(SurveyBatch).options(selectinload(SurveyBatch.school_year), selectinload(SurveyBatch.commune)).where(SurveyBatch.id == batch_id))
    if batch is None:
        raise HTTPException(404, 'Không tìm thấy đợt điều tra.')
    return batch


def page(request, db, *, batch_id=None, school_year_id=None, status=200, **extra):
    user = admin(request)
    csrf = request.session.setdefault('person_import_csrf', secrets.token_urlsafe(32))
    years = list(db.scalars(select(SchoolYear).order_by(SchoolYear.code.desc())).all())
    if school_year_id is None and batch_id:
        school_year_id = get_batch(db, batch_id).school_year_id
    if school_year_id is None and years:
        school_year_id = years[0].id
    batches = list(db.scalars(select(SurveyBatch).options(selectinload(SurveyBatch.school_year), selectinload(SurveyBatch.commune)).where(SurveyBatch.school_year_id == school_year_id).order_by(SurveyBatch.commune_id, SurveyBatch.id.desc())).all())
    batch = next((b for b in batches if b.id == batch_id), None)
    jobs = list(db.scalars(select(HouseholdImportJob).where(HouseholdImportJob.job_code.startswith('DETAIL-'), HouseholdImportJob.school_year_id == school_year_id).order_by(HouseholdImportJob.created_at.desc()).limit(30)).all())
    return templates.TemplateResponse(request=request, name='data_tools/person_excel_import.html', context=dict(nguoi_dung=user, prefix=PREFIX, csrf=csrf, years=years, school_year_id=school_year_id, batches=batches, batch=batch, jobs=jobs, field_labels=service.FIELD_LABELS, **extra), status_code=status)


@router.get('', response_class=HTMLResponse)
def home(request: Request, school_year_id: int | None = None, batch_id: int | None = None, db: Session = Depends(get_db)):
    return page(request, db, batch_id=batch_id, school_year_id=school_year_id)


@router.get('/mau-excel')
def template(request: Request, batch_id: int, db: Session = Depends(get_db)):
    admin(request)
    batch = get_batch(db, batch_id)
    return StreamingResponse(BytesIO(service.make_template(batch)), media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', headers={'Content-Disposition': f'attachment; filename="mau_chi_tiet_doi_tuong_{batch.id}.xlsx"'})


@router.post('/xem-truoc', response_class=HTMLResponse)
async def preview(request: Request, batch_id: int = Form(...), csrf: str = Form(...), mode: str = Form('draft'), excel_file: UploadFile = File(...), db: Session = Depends(get_db)):
    user = admin(request)
    csrf_check(request, csrf)
    request.session.pop('person_import_preview', None)
    batch = get_batch(db, batch_id)
    if mode not in {'draft', 'complete'}:
        raise HTTPException(422, 'Chế độ nhập không hợp lệ.')
    content = await excel_file.read(15 * 1024 * 1024 + 1)
    issues, rows, plan, fingerprint = [], [], [], ''
    try:
        if not (excel_file.filename or '').lower().endswith('.xlsx') or len(content) > 15 * 1024 * 1024 or not content:
            raise ValueError('Chọn file .xlsx có dữ liệu, tối đa 15 MB.')
        service.check_unlocked(db, batch)
        rows, issues = service.parse_file(content, batch)
        if not issues:
            plan, issues, fingerprint = service.build_plan(db, batch, rows, mode == 'complete')
    except (ValueError, KeyError, TypeError) as exc:
        issues = [{'row': None, 'message': str(exc)}]
    except Exception:
        logger.exception('Cannot preview person import')
        issues = [{'row': None, 'message': 'Không đọc được file. Hãy kiểm tra định dạng hoặc tải lại mẫu.'}]
    token = None
    if not issues:
        try:
            token = secrets.token_hex(24)
            ROOT.mkdir(parents=True, exist_ok=True)
            (ROOT / f'{token}.xlsx').write_bytes(content)
            request.session['person_import_preview'] = dict(token=token, actor=user.get('id'), batch_id=batch_id, mode=mode, fingerprint=fingerprint, digest=hashlib.sha256(content).hexdigest(), expires=time.time() + 1800, filename=Path(excel_file.filename or 'data.xlsx').name[:220])
        except OSError:
            logger.exception('Cannot stage person import')
            token = None
            issues = [{'row': None, 'message': 'Không lưu được file xem trước. Kiểm tra dung lượng và quyền ghi thư mục exports.'}]
    return page(request, db, batch_id=batch_id, preview=True, rows=plan or rows, issues=issues, token=token, mode=mode, filename=excel_file.filename, total=len(rows), households=len({r['form_number'] for r in rows}), new_people=sum(r.get('person_id') is None for r in plan), status=422 if issues else 200)


def backup_database(db, token):
    database = db.get_bind().url.database
    if not database or database == ':memory:':
        return None
    folder = ROOT / 'backups'
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f'before_{token}.db'
    source = sqlite3.connect(f'{Path(database).resolve().as_uri()}?mode=ro', uri=True)
    try:
        with closing(sqlite3.connect(str(path))) as target:
            source.backup(target)
    finally:
        source.close()
    return path


@router.post('/xac-nhan', response_class=HTMLResponse)
def confirm(request: Request, csrf: str = Form(...), token: str = Form(...), acknowledge: str = Form(''), db: Session = Depends(get_db)):
    user = admin(request)
    csrf_check(request, csrf)
    saved = request.session.get('person_import_preview') or {}
    if not saved or not secrets.compare_digest(str(saved.get('token', '')), token) or saved.get('actor') != user.get('id') or saved.get('expires', 0) < time.time():
        raise HTTPException(409, 'Bản xem trước hết hạn hoặc đã xử lý. Hãy kiểm tra lại file.')
    if acknowledge != 'yes':
        raise HTTPException(422, 'Cần xác nhận đã kiểm tra phạm vi và nội dung nhập.')
    if not all(c in '0123456789abcdef' for c in token) or len(token) != 48:
        raise HTTPException(409, 'Mã xem trước không hợp lệ.')
    batch_id = saved['batch_id']
    try:
        content = (ROOT / f'{token}.xlsx').read_bytes()
        if hashlib.sha256(content).hexdigest() != saved['digest']:
            raise ValueError('File đã thay đổi. Hãy tải lên và kiểm tra lại.')
        # Serialize against every SQLite writer; re-read after the lock, not before.
        db.rollback()
        db.execute(text('BEGIN IMMEDIATE'))
        db.expire_all()
        job_code = 'DETAIL-' + token
        if db.scalar(select(HouseholdImportJob.id).where(HouseholdImportJob.job_code == job_code)):
            raise ValueError('Lần nhập này đã hoàn thành; không nhập lặp lại.')
        batch = get_batch(db, batch_id)
        rows, issues = service.parse_file(content, batch)
        if issues:
            raise ValueError('File không còn hợp lệ. Hãy xem trước lại.')
        plan, issues, fingerprint = service.build_plan(db, batch, rows, saved['mode'] == 'complete')
        if issues:
            raise ValueError(issues[0]['message'])
        if fingerprint != saved['fingerprint']:
            raise ValueError('Dữ liệu đã thay đổi từ lúc xem trước. Hãy kiểm tra lại file để tránh ghi đè.')
        backup_database(db, token)
        summary = service.apply_plan(db, batch, plan, saved['mode'] == 'complete', job_code)
        message = f"Đã nhập {len(rows)} đối tượng / {len({r['form_number'] for r in rows})} hộ. " + ('Phiếu đã hoàn thành và được dùng làm nguồn báo cáo.' if saved['mode'] == 'complete' else 'Phiếu đang điều tra, cần rà soát hoàn thành trước khi đưa vào báo cáo.')
        db.add(HouseholdImportJob(job_code=job_code, survey_batch_id=batch.id, school_year_id=batch.school_year_id, commune_id=batch.commune_id, uploaded_by_user_id=user.get('id'), actor_name_snapshot=user.get('full_name'), actor_role_snapshot=user.get('role_code'), original_file_name=saved['filename'], stored_path=str(ROOT / f'{token}.xlsx'), file_ext='.xlsx', file_size=len(content), sha256=saved['digest'], status='DA_CAP_NHAT', stage='HOAN_THANH', rows_total=len(rows), rows_valid=len(rows), rows_error=0, message=message, processed_at=datetime.now(), **summary))
        db.commit()
    except ValueError as exc:
        db.rollback()
        return page(request, db, batch_id=batch_id, error=str(exc), status=409)
    except Exception:
        db.rollback()
        logger.exception('Person import rolled back')
        return page(request, db, batch_id=batch_id, error='Không thể hoàn tất lần nhập. Toàn bộ thay đổi đã được hoàn tác; hãy kiểm tra lại file.', status=500)
    request.session.pop('person_import_preview', None)
    # Post/redirect/get avoids accidental resubmission on refresh.
    return RedirectResponse(f'{PREFIX}?batch_id={batch_id}', status_code=303)
