from datetime import datetime
import re
import secrets
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.models import Commune, School, SchoolYear, User
from app.permissions import SURVEY_ROLE_CODES
from app.survey_models import Household, SurveyBatch, SurveyForm, SurveyFormInvestigator, SurveyPerson, SurveyPersonYearRecord
from app.xmc_models import XmcEvidence, BOOL_FIELDS, TEXT_FIELDS
from app.xmc_appendices import XMC_FORMS, COMPULSORY_FORMS
from app.services.xmc_appendix_reports import build_report
from app.services.xmc_rules_353 import personal_levels
from app.routers.report_center import templates, _load_scope_options, _load_school_years, _choose_year_id
from app.access_control import AccessControlMiddleware

router = APIRouter(prefix="/bao-cao/xoa-mu-chu", tags=["Tổng hợp phụ lục XMC"])


def load_people(db, user, year_id, commune_id=None, school_id=None):
    role = user.get("role_code")
    if role not in SURVEY_ROLE_CODES:
        raise HTTPException(403, "Không có quyền xem báo cáo.")
    stmt = select(SurveyForm).join(SurveyBatch).join(Household).where(
        SurveyBatch.school_year_id == year_id, Household.is_active.is_(True),
        Household.commune.has(Commune.is_active.is_(True)))
    if role == "XA":
        if not user.get("commune_id"):
            raise HTTPException(403, "Tài khoản chưa có xã/phường.")
        stmt = stmt.where(Household.commune_id == user["commune_id"])
    elif role == "TRUONG":
        if not user.get("school_id"):
            raise HTTPException(403, "Tài khoản chưa có trường.")
        stmt = stmt.where(SurveyForm.investigators.any(
            SurveyFormInvestigator.user.has(User.school_id == user["school_id"])))
    elif role == "GIAO_VIEN":
        if not user.get("id"):
            raise HTTPException(403, "Tài khoản không hợp lệ.")
        stmt = stmt.where(SurveyForm.investigators.any(SurveyFormInvestigator.user_id == user["id"]))
    if commune_id is not None:
        stmt = stmt.where(Household.commune_id == commune_id)
    if school_id is not None and role not in {"TRUONG", "GIAO_VIEN"}:
        stmt = stmt.where(SurveyForm.investigators.any(
            SurveyFormInvestigator.user.has(User.school_id == school_id)))
    forms = list(db.scalars(stmt.options(selectinload(SurveyForm.household).selectinload(Household.people))).unique())
    people = {p.id: p for f in forms for p in f.household.people if p.is_active}
    records = list(db.scalars(select(SurveyPersonYearRecord).where(
        SurveyPersonYearRecord.survey_form_id.in_([f.id for f in forms]),
        SurveyPersonYearRecord.school_year_id == year_id).options(
            selectinload(SurveyPersonYearRecord.school), selectinload(SurveyPersonYearRecord.classroom)
        ).order_by(SurveyPersonYearRecord.is_reviewed.desc(), SurveyPersonYearRecord.updated_at.desc(), SurveyPersonYearRecord.id.desc()))) if forms else []
    latest = {}
    for r in records:
        latest.setdefault(r.survey_person_id, r)
    return [(p, latest.get(p.id)) for p in people.values()]


def context(db, request, school_year_id=None, commune_id=None, school_id=None):
    user = request.scope.get("auth_user") or {}
    if user.get("role_code") not in SURVEY_ROLE_CODES:
        raise HTTPException(403, "Không có quyền truy cập.")
    years = _load_school_years(db)
    year_id = _choose_year_id(years, school_year_id)
    if year_id is None or (school_year_id is not None and year_id != school_year_id):
        raise HTTPException(422, "Năm học không hợp lệ.")
    communes, schools, cid, sid, label = _load_scope_options(db, user, commune_id, school_id)
    if commune_id is not None and commune_id != cid:
        raise HTTPException(403, "Xã/phường ngoài phạm vi tài khoản.")
    if school_id is not None and school_id != sid:
        raise HTTPException(403, "Trường ngoài phạm vi tài khoản.")
    people = load_people(db, user, year_id, cid, sid)
    ids = [r.id for _, r in people if r]
    evidence = {e.record_id: e.data for e in db.scalars(select(XmcEvidence).where(XmcEvidence.record_id.in_(ids)))} if ids else {}
    year = next(y for y in years if y.id == year_id)
    match = re.search(r"\d{4}", year.code)
    if not match:
        raise HTTPException(422, "Mã năm học không xác định được năm điều tra.")
    report_communes = [c for c in communes if cid is None or c.id == cid]
    if sid is not None:
        school = db.get(School, sid)
        report_communes = [c for c in report_communes if school and c.id == school.commune_id]
    if user.get("role_code") == "GIAO_VIEN":
        label = "Phiếu được phân công cho " + str(user.get("full_name") or user.get("username") or "giáo viên")
    return dict(user=user, people=people, evidence=evidence, year=year, reference_year=int(match[0]),
                commune_id=cid, school_id=sid, communes=report_communes, label=label)


@router.get("/phu-luc/{code}/tong-hop")
def export_appendix(code: str, request: Request, school_year_id: int | None = None,
                    commune_id: int | None = None, school_id: int | None = None,
                    literacy_basis: str | None = "g1", db: Session = Depends(get_db)):
    compulsory_codes = {c for c, _, _ in COMPULSORY_FORMS} | {'bo-pl2'}
    if code not in {c for c, _, _ in XMC_FORMS} | {"bo-xmc", "pl4", "pl5"} | compulsory_codes:
        raise HTTPException(404, "Không tìm thấy mẫu báo cáo.")
    if literacy_basis not in {None, "g1", "g2"}:
        raise HTTPException(422, "Mức biết chữ không hợp lệ.")
    ctx = context(db, request, school_year_id, commune_id, school_id)
    if code in compulsory_codes or code in {'pl4','pl5'}:
        if code in compulsory_codes:
            from app.services.compulsory_appendix_reports import build_compulsory
            stream = build_compulsory(code, db, ctx)
            extension = 'xlsx'
            media_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        else:
            from app.services.appendix_narrative_reports import build_narrative
            stream = build_narrative(int(code[-1]), db, ctx)
            extension = 'docx'
            media_type = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        filename = f"Phu_luc_{code}_{ctx['reference_year']}.{extension}"
        return StreamingResponse(stream, media_type=media_type,
                                 headers={'Content-Disposition': f'attachment; filename="{filename}"'})
    stream = build_report(code, ctx["people"], ctx["evidence"], ctx["reference_year"], ctx["year"].code,
                          ctx["label"], ctx["communes"],
                          school_scope=ctx["school_id"] is not None or ctx["user"].get("role_code") in {"TRUONG", "GIAO_VIEN"},
                          literacy_basis=literacy_basis)
    filename = f"XMC_{code}_{ctx['reference_year']}.xlsx"
    return StreamingResponse(stream, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/du-lieu-bo-sung")
def evidence_page(request: Request, school_year_id: int | None = None, commune_id: int | None = None,
                  school_id: int | None = None, q: str = "", page: int = 1, db: Session = Depends(get_db)):
    ctx = context(db, request, school_year_id, commune_id, school_id)
    if "xmc_csrf" not in request.session:
        request.session["xmc_csrf"] = secrets.token_urlsafe(32)
    people = [(p, r) for p, r in ctx["people"] if (not p.date_of_birth or 15 <= ctx["reference_year"] - p.date_of_birth.year <= 60)
              and q.casefold() in (p.full_name + " " + (p.personal_id or "")).casefold()]
    people.sort(key=lambda item: (item[0].full_name, item[0].id))
    page = max(1, page)
    params = dict(school_year_id=ctx["year"].id, q=q)
    for k in ("commune_id", "school_id"):
        if ctx[k] is not None:
            params[k] = ctx[k]
    return templates.TemplateResponse(request=request, name="reports/xmc_evidence.html", context={
        "nguoi_dung": ctx["user"], "ctx": ctx, "rows": people[(page-1)*30:page*30],
        "total": len(people), "page": page, "q": q, "bool_fields": BOOL_FIELDS, "text_fields": TEXT_FIELDS,
        "can_edit": ctx["user"].get("role_code") != "PHONG_BAN", "csrf": request.session["xmc_csrf"],
        "next_url": "?" + urlencode(dict(params, page=page+1)) if page*30 < len(people) else None,
        "prev_url": "?" + urlencode(dict(params, page=page-1)) if page > 1 else None,
        "personal_levels": personal_levels,
        "back_url": "/bao-cao/xoa-mu-chu?" + urlencode({k:v for k,v in params.items() if k != "q"})})


@router.post("/du-lieu-bo-sung/{record_id}")
async def save_evidence(record_id: int, request: Request, db: Session = Depends(get_db)):
    user = request.scope.get("auth_user") or {}
    if user.get("role_code") not in SURVEY_ROLE_CODES or user.get("role_code") == "PHONG_BAN":
        raise HTTPException(403, "Tài khoản chỉ được xem và xuất báo cáo.")
    form = await request.form()
    if not secrets.compare_digest(str(form.get("csrf", "")), str(request.session.get("xmc_csrf") or "missing")):
        raise HTTPException(403, "Phiên làm việc hết hạn; tải lại trang.")
    record = db.get(SurveyPersonYearRecord, record_id)
    if record is None:
        raise HTTPException(404, "Không tìm thấy hồ sơ năm học.")
    allowed = load_people(db, user, record.school_year_id)
    if record.id not in {r.id for _, r in allowed if r}:
        raise HTTPException(403, "Hồ sơ ngoài phạm vi tài khoản hoặc không phải bản hiện hành.")
    survey_form = db.get(SurveyForm, record.survey_form_id)
    locked = AccessControlMiddleware._kiem_tra_khoa_dot_dieu_tra(
        db=db, path=f"/dieu-tra/{survey_form.survey_batch_id}/xmc", method="POST",
        role_code=user["role_code"], auth_user=user)
    if locked:
        raise HTTPException(409, "Đợt điều tra đã khóa; không thể cập nhật dữ liệu XMC.")
    data = {}
    for key in BOOL_FIELDS:
        value = str(form.get(key, ""))
        if value not in {"", "true", "false"}:
            raise HTTPException(422, "Giá trị xác nhận không hợp lệ.")
        data[key] = {"": None, "true": True, "false": False}[value]
    for key in TEXT_FIELDS:
        value = str(form.get(key, "")).strip()
        if len(value) > 1000:
            raise HTTPException(422, "Nội dung quá dài (tối đa 1000 ký tự).")
        if key.endswith("_year") and value:
            if not value.isdigit() or not 1900 <= int(value) <= datetime.now().year + 1:
                raise HTTPException(422, "Năm xác nhận/hỗ trợ không hợp lệ.")
        data[key] = value or None
    for level in ("1", "2"):
        if data["recognized" + level] is True and data["enrolled" + level] is not True:
            raise HTTPException(422, "Công nhận trong năm phải gắn với học viên XMC cùng mức độ.")
        attained = personal_levels(record, data)[int(level) - 1]
        if data["recognized" + level] is True and attained is not True:
            raise HTTPException(422, "Kết quả công nhận chưa khớp mức biết chữ trên phiếu điều tra; cần kiểm tra phiếu trước.")
    if personal_levels(record, data)[2]:
        raise HTTPException(422, "Thông tin chưa biết chữ mâu thuẫn mức đã đạt; cần kiểm tra hoặc xác nhận tái mù chữ.")
    entry = db.get(XmcEvidence, record_id)
    if entry is None:
        entry = XmcEvidence(record_id=record_id)
        db.add(entry)
    entry.data = data
    entry.updated_by = user["id"]
    entry.updated_at = datetime.now()
    db.commit()
    return RedirectResponse("/bao-cao/xoa-mu-chu/du-lieu-bo-sung?" + urlencode({"school_year_id": record.school_year_id}), status_code=303)
