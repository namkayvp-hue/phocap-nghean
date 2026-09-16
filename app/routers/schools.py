from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.models import Commune, School
from app.report_input_models import SchoolNetworkYearData
from app.permissions import ADMIN_ROLE_CODES, COMMUNE_ROLE_CODE, normalize_role_code


APP_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(APP_DIR / "templates"))
router = APIRouter(prefix="/truong", tags=["Danh mục trường"])

# === BAI_13B_6_V1_4_DANH_MUC_TRUONG_THEO_CAP ===
SCHOOL_LEVEL_LABELS = {
    "MN": "Mầm non",
    "TH": "Tiểu học",
    "THCS": "THCS",
}

def chuan_hoa_cap_hoc(value: str | None) -> str | None:
    code = str(value or "").strip().upper()
    return code if code in SCHOOL_LEVEL_LABELS else None


STATUS_MESSAGES = {
    "created": "Đã thêm trường mới thành công.",
    "updated": "Đã cập nhật thông tin trường thành công.",
    "locked": "Đã khóa trường thành công.",
    "unlocked": "Đã mở lại trường thành công.",
    "duplicate": "Mã trường đã tồn tại trong hệ thống.",
    "invalid": "Mã trường và tên trường không được để trống.",
    "invalid_commune": "Xã được chọn không tồn tại hoặc đã bị khóa.",
    "forbidden": "Tài khoản chỉ được xem các trường thuộc phạm vi quản lý.",
}


def chuan_hoa_ma_truong(value: str) -> str:
    return value.strip().upper()


def chuan_hoa_ten_truong(value: str) -> str:
    return " ".join(value.strip().split())


def chuan_hoa_dia_chi(value: str) -> str | None:
    result = " ".join(value.strip().split())
    return result or None


def lay_actor(request: Request) -> dict[str, Any]:
    return dict(request.scope.get("auth_user") or {})


def la_quan_tri(request: Request) -> bool:
    return normalize_role_code(lay_actor(request).get("role_code")) in ADMIN_ROLE_CODES


# === V13_14_MERGED_SOURCE_HELPER_START ===
def _v1314_completed_merger_source_map(
    db: Session,
) -> dict[int, dict[str, Any]]:
    json_module = __import__('json')
    pairs: dict[int, int] = {}
    plan_path = APP_DIR.parent / 'data' / 'school_merger_approved_plans.json'

    try:
        payload = json_module.loads(plan_path.read_text(encoding='utf-8'))
        for plan in payload.get('plans') or []:
            if not isinstance(plan, dict):
                continue
            if str(plan.get('status') or '').upper() != 'COMPLETED':
                continue
            try:
                target_id = int(plan.get('target_school_id') or 0)
            except (TypeError, ValueError):
                target_id = 0
            if target_id <= 0:
                continue
            for raw_source_id in plan.get('source_school_ids') or []:
                try:
                    source_id = int(raw_source_id)
                except (TypeError, ValueError):
                    continue
                if source_id <= 0 or source_id == target_id:
                    continue
                previous = pairs.get(source_id)
                if previous is not None and previous != target_id:
                    raise RuntimeError(
                        f'Trường nguồn {source_id} có nhiều target: {previous}/{target_id}'
                    )
                pairs[source_id] = target_id
    except FileNotFoundError:
        pass

    try:
        rows = db.connection().exec_driver_sql(
            'SELECT target_school_id, source_school_ids_json '
            'FROM school_merger_operations ORDER BY id'
        ).fetchall()
        for row in rows:
            try:
                target_id = int(row[0] or 0)
                source_ids = json_module.loads(row[1] or '[]')
            except Exception:
                continue
            if target_id <= 0:
                continue
            for raw_source_id in source_ids or []:
                try:
                    source_id = int(raw_source_id)
                except (TypeError, ValueError):
                    continue
                if source_id <= 0 or source_id == target_id:
                    continue
                previous = pairs.get(source_id)
                if previous is not None and previous != target_id:
                    raise RuntimeError(
                        f'Audit source {source_id} có nhiều target: {previous}/{target_id}'
                    )
                pairs[source_id] = target_id
    except Exception:
        pass

    if not pairs:
        return {}

    target_ids = sorted(set(pairs.values()))
    targets = db.scalars(
        select(School).where(School.id.in_(target_ids))
    ).all()
    target_by_id = {int(item.id): item for item in targets}

    result: dict[int, dict[str, Any]] = {}
    for source_id, target_id in pairs.items():
        target = target_by_id.get(target_id)
        result[source_id] = {
            'target_school_id': target_id,
            'target_code': str(target.code or '') if target is not None else '',
            'target_name': (
                str(target.name or '')
                if target is not None
                else f'school_id={target_id}'
            ),
        }
    return result
# === V13_14_MERGED_SOURCE_HELPER_END ===


@router.get("", response_class=HTMLResponse)
def danh_sach_truong(
    request: Request,
    db: Session = Depends(get_db),
    status: str | None = None,
    cap: str | None = Query(default=None),
):
    actor = lay_actor(request)
    role_code = normalize_role_code(actor.get("role_code"))
    can_manage = role_code in ADMIN_ROLE_CODES

    if can_manage:
        communes = db.scalars(
            select(Commune)
            .where(Commune.is_active.is_(True))
            .order_by(Commune.name.asc())
        ).all()
        statement = select(School)
    elif role_code == COMMUNE_ROLE_CODE and actor.get("commune_id") is not None:
        communes = []
        statement = select(School).where(
            School.commune_id == int(actor["commune_id"])
        )
    else:
        communes = []
        statement = select(School).where(School.id == -1)

    level_code = chuan_hoa_cap_hoc(cap)
    if level_code is not None:
        level_school_ids = (
            select(SchoolNetworkYearData.school_id)
            .where(SchoolNetworkYearData.level_code == level_code)
            .distinct()
        )
        statement = statement.where(School.id.in_(level_school_ids))

    schools = db.scalars(
        statement.options(selectinload(School.commune)).order_by(School.name.asc())
    ).all()

    # === V13_14_MERGED_SOURCE_LIST_START ===
    sap_nhap_nguon_map = _v1314_completed_merger_source_map(db)
    # === V13_14_MERGED_SOURCE_LIST_END ===

    return templates.TemplateResponse(
        request=request,
        name="schools/list.html",
        context={
            "nguoi_dung": actor,
            "danh_sach_xa": communes,
            "danh_sach_truong": schools,
            "thong_bao": STATUS_MESSAGES.get(status),
            "trang_thai": status,
            "co_quyen_quan_ly": can_manage,
            "sap_nhap_nguon_map": sap_nhap_nguon_map,
            "cap_hoc": level_code,
            "cap_hoc_label": SCHOOL_LEVEL_LABELS.get(level_code),
        },
    )


@router.post("/them")
def them_truong(
    request: Request,
    commune_id: Annotated[int, Form()],
    ma_truong: Annotated[str, Form()],
    ten_truong: Annotated[str, Form()],
    dia_chi: Annotated[str, Form()] = "",
    db: Session = Depends(get_db),
):
    if not la_quan_tri(request):
        return RedirectResponse("/truong?status=forbidden", 303)

    code = chuan_hoa_ma_truong(ma_truong)
    name = chuan_hoa_ten_truong(ten_truong)
    address = chuan_hoa_dia_chi(dia_chi)
    if not code or not name or len(code) > 30 or len(name) > 300:
        return RedirectResponse("/truong?status=invalid", 303)

    commune = db.get(Commune, commune_id)
    if commune is None or not commune.is_active:
        return RedirectResponse("/truong?status=invalid_commune", 303)
    if db.scalar(select(School).where(School.code == code)) is not None:
        return RedirectResponse("/truong?status=duplicate", 303)

    db.add(School(
        commune_id=commune_id,
        code=code,
        name=name,
        address=address,
        is_active=True,
    ))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return RedirectResponse("/truong?status=duplicate", 303)
    return RedirectResponse("/truong?status=created", 303)


@router.get("/{school_id}/sua", response_class=HTMLResponse)
def form_sua_truong(
    school_id: int,
    request: Request,
    db: Session = Depends(get_db),
    status: str | None = None,
):
    if not la_quan_tri(request):
        return RedirectResponse("/truong?status=forbidden", 303)
    school = db.get(School, school_id)
    if school is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy trường.")

    # === V13_15_MERGED_SOURCE_READONLY_GET_START ===
    v1315_merger_map = _v1314_completed_merger_source_map(db)
    v1315_merger_target = v1315_merger_map.get(school_id)
    if v1315_merger_target is not None:
        return templates.TemplateResponse(
            request=request,
            name="schools/merged_readonly.html",
            context={
                "nguoi_dung": lay_actor(request),
                "truong": school,
                "merger_target": v1315_merger_target,
            },
        )
    # === V13_15_MERGED_SOURCE_READONLY_GET_END ===
    communes = db.scalars(
        select(Commune)
        .where(or_(Commune.is_active.is_(True), Commune.id == school.commune_id))
        .order_by(Commune.name.asc())
    ).all()
    return templates.TemplateResponse(
        request=request,
        name="schools/edit.html",
        context={
            "nguoi_dung": lay_actor(request),
            "truong": school,
            "danh_sach_xa": communes,
            "thong_bao": STATUS_MESSAGES.get(status),
        },
    )


@router.post("/{school_id}/sua")
def cap_nhat_truong(
    school_id: int,
    request: Request,
    commune_id: Annotated[int, Form()],
    ma_truong: Annotated[str, Form()],
    ten_truong: Annotated[str, Form()],
    dia_chi: Annotated[str, Form()] = "",
    db: Session = Depends(get_db),
):
    if not la_quan_tri(request):
        return RedirectResponse("/truong?status=forbidden", 303)
    school = db.get(School, school_id)
    if school is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy trường.")

    # === V13_15_MERGED_SOURCE_EDIT_GUARD_START ===
    v1315_merger_target = _v1314_completed_merger_source_map(db).get(school_id)
    if v1315_merger_target is not None:
        raise HTTPException(
            status_code=409,
            detail=(
                "Trường nguồn đã sáp nhập là hồ sơ chỉ đọc, không được sửa. "
                f"Trường đích: {v1315_merger_target.get('target_name') or v1315_merger_target.get('target_school_id')}."
            ),
        )
    # === V13_15_MERGED_SOURCE_EDIT_GUARD_END ===

    code = chuan_hoa_ma_truong(ma_truong)
    name = chuan_hoa_ten_truong(ten_truong)
    address = chuan_hoa_dia_chi(dia_chi)
    if not code or not name:
        return RedirectResponse(f"/truong/{school_id}/sua?status=invalid", 303)

    commune = db.get(Commune, commune_id)
    invalid_commune = commune is None or (
        not commune.is_active and commune_id != school.commune_id
    )
    if invalid_commune:
        return RedirectResponse(f"/truong/{school_id}/sua?status=invalid_commune", 303)

    duplicate = db.scalar(
        select(School).where(School.code == code, School.id != school_id)
    )
    if duplicate is not None:
        return RedirectResponse(f"/truong/{school_id}/sua?status=duplicate", 303)

    school.commune_id = commune_id
    school.code = code
    school.name = name
    school.address = address
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return RedirectResponse(f"/truong/{school_id}/sua?status=duplicate", 303)
    return RedirectResponse("/truong?status=updated", 303)


@router.post("/{school_id}/khoa-mo")
def khoa_hoac_mo_truong(
    school_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    if not la_quan_tri(request):
        return RedirectResponse("/truong?status=forbidden", 303)
    school = db.get(School, school_id)
    if school is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy trường.")
    # === V13_14_MERGED_SOURCE_REOPEN_GUARD_START ===
    v1314_merged_sources = _v1314_completed_merger_source_map(db)
    if school_id in v1314_merged_sources and not school.is_active:
        target = v1314_merged_sources[school_id]
        raise HTTPException(
            status_code=409,
            detail=(
                'Trường nguồn đã sáp nhập không được phép mở lại. '
                f"Trường đích: {target.get('target_name') or target.get('target_school_id')}."
            ),
        )
    # === V13_14_MERGED_SOURCE_REOPEN_GUARD_END ===
    school.is_active = not school.is_active
    db.commit()
    status = "unlocked" if school.is_active else "locked"
    return RedirectResponse(f"/truong?status={status}", 303)
