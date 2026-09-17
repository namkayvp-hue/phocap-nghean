from __future__ import annotations

from decimal import Decimal, InvalidOperation
import json
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.models import Commune, School, SchoolYear
from app.permissions import (
    ADMIN_ROLE_CODES,
    COMMUNE_ROLE_CODE,
    DEPARTMENT_ROLE_CODE,
    SCHOOL_ROLE_CODE,
    normalize_role_code,
)
from app.report_input_catalog import FINANCE_ITEMS
from app.structured_report_catalog import STRUCTURED_SCHOOL_FORMS, flatten_fields
from app.report_input_models import (
    FinanceReportValue,
    SchoolFinanceReportValue,
    SchoolMn01CsvcInput,
    SchoolMn01GvInput,
    SchoolStructuredReportInput,
    SchoolNetworkYearData,
)
from app.routers.report_center import _choose_year_id, _load_school_years, _load_scope_options
from app.pcgd_xmc_report_builders_v1 import (
    _class_count as _pc_class_count,
    _norm as _pc_norm,
    _school_level as _pc_school_level,
    _schools_and_classes as _pc_schools_and_classes,
    _staff_rows as _pc_staff_rows,
    _staff_summary as _pc_staff_summary,
)
from app.services.finance_school_service import (
    finance_school_ids_for_scope,
    is_preschool_school,
    load_finance_values,
)
from app.routers.staff_management import (
    EMPLOYMENT_LABELS,
    INSTITUTION_GROUP_LABELS,
    PROFESSIONAL_STANDARD_LABELS,
    QUALIFICATION_LEVEL_LABELS,
    QUALIFICATION_STANDARD_LABELS,
    TEACHING_AGE_LABELS,
)
from app.routers.surveys import lay_thong_tin_nguoi_dung
from app.staff_models import SchoolStaffYearSummary, StaffYearRecord


router = APIRouter(tags=["Dữ liệu đầu vào báo cáo"])
templates = Jinja2Templates(directory="app/templates")

GV_EDIT_ROLES = frozenset({*ADMIN_ROLE_CODES, COMMUNE_ROLE_CODE, SCHOOL_ROLE_CODE})
CSVC_EDIT_ROLES = frozenset({*ADMIN_ROLE_CODES, COMMUNE_ROLE_CODE, SCHOOL_ROLE_CODE})
FINANCE_EDIT_ROLES = frozenset({*ADMIN_ROLE_CODES, COMMUNE_ROLE_CODE})
REPORT_INPUT_VIEW_ROLES = frozenset({*ADMIN_ROLE_CODES, DEPARTMENT_ROLE_CODE, COMMUNE_ROLE_CODE, SCHOOL_ROLE_CODE})


def _redirect_forbidden() -> RedirectResponse:
    return RedirectResponse(url="/?status=forbidden", status_code=303)


def _clean(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _parse_int(value: Any, default: int = 0, minimum: int = 0) -> int:
    try:
        number = int(str(value or "").strip())
    except (TypeError, ValueError):
        number = default
    return max(minimum, number)


def _parse_optional_decimal(value: Any) -> Decimal | None:
    text = str(value or "").strip().replace(" ", "").replace(",", ".")
    if not text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def _user_role(request: Request) -> str:
    return normalize_role_code((lay_thong_tin_nguoi_dung(request) or {}).get("role_code"))


def _load_scope(
    db: Session,
    request: Request,
    school_year_id: int | None,
    commune_id: int | None,
    school_id: int | None,
) -> dict[str, Any]:
    user = lay_thong_tin_nguoi_dung(request)
    years = _load_school_years(db)
    selected_year_id = _choose_year_id(years, school_year_id)
    communes, schools, selected_commune_id, selected_school_id, scope_label = _load_scope_options(
        db, user, commune_id, school_id
    )
    selected_year = next((y for y in years if int(y.id) == int(selected_year_id or 0)), None)
    selected_school = next((s for s in schools if int(s.id) == int(selected_school_id or 0)), None)
    return {
        "user": user,
        "role_code": normalize_role_code((user or {}).get("role_code")),
        "school_years": years,
        "selected_year_id": selected_year_id,
        "selected_year": selected_year,
        "communes": communes,
        "schools": schools,
        "selected_commune_id": selected_commune_id,
        "selected_school_id": selected_school_id,
        "selected_school": selected_school,
        "scope_label": scope_label,
    }



# === BAI_13B_6_V1_4_MN_SCOPE_START ===
# === BAI_13B_6_V1_3_MN_SCOPE_START ===
def _looks_like_preschool_school(school: School) -> bool:
    text = _pc_norm(
        " ".join([
            str(getattr(school, "name", "") or ""),
            str(getattr(school, "code", "") or ""),
        ])
    )
    words = set(text.split())
    return (
        "MAM NON" in text
        or "MAU GIAO" in text
        or "NHA TRE" in text
        or "NHOM TRE" in text
        or "LOP MAM NON" in text
        or "GDMN" in words
        or "MN" in words
    )


def _mn_scope(
    db: Session,
    request: Request,
    school_year_id: int | None,
    commune_id: int | None,
    school_id: int | None,
) -> dict[str, Any]:
    scope = _load_scope(
        db,
        request,
        school_year_id,
        commune_id,
        school_id,
    )

    mn_ids = {
        int(value)
        for value in db.scalars(
            select(SchoolNetworkYearData.school_id)
            .where(SchoolNetworkYearData.level_code == "MN")
            .distinct()
        ).all()
    }

    if mn_ids:
        filtered = [
            school
            for school in list(scope.get("schools") or [])
            if int(school.id) in mn_ids
        ]
    else:
        non_mn_ids = {
            int(value)
            for value in db.scalars(
                select(SchoolNetworkYearData.school_id)
                .where(SchoolNetworkYearData.level_code.in_(["TH", "THCS"]))
                .distinct()
            ).all()
        }
        filtered = [
            school
            for school in list(scope.get("schools") or [])
            if _looks_like_preschool_school(school)
            and int(school.id) not in non_mn_ids
        ]

    valid_ids = {int(s.id) for s in filtered}
    selected_school_id = scope.get("selected_school_id")

    if (
        selected_school_id is not None
        and int(selected_school_id) not in valid_ids
    ):
        selected_school_id = None

    selected_school = next(
        (
            s for s in filtered
            if int(s.id) == int(selected_school_id or 0)
        ),
        None,
    )

    scope["schools"] = filtered
    scope["selected_school_id"] = selected_school_id
    scope["selected_school"] = selected_school

    if selected_school is not None:
        scope["scope_label"] = f"Trường {selected_school.name}"

    return scope
# === BAI_13B_6_V1_3_MN_SCOPE_END ===
# === BAI_13B_6_V1_4_MN_SCOPE_END ===

# === BAI_13B_6_V1_4_MN_DISPLAY_START ===
def _mn_reference_staff_rows(
    db: Session,
    *,
    school_id: int,
    target_year_id: int,
) -> tuple[list[StaffYearRecord], str | None]:
    rows = list(
        db.scalars(
            select(StaffYearRecord)
            .where(
                StaffYearRecord.school_id == school_id,
                StaffYearRecord.is_active.is_(True),
                StaffYearRecord.status_code == "DANG_LAM_VIEC",
            )
            .options(
                selectinload(StaffYearRecord.staff_member),
                selectinload(StaffYearRecord.school_year),
            )
        ).all()
    )

    # Ưu tiên hồ sơ có đánh dấu nguồn MN; vẫn cho phép hồ sơ cũ chưa có source_level.
    mn_rows = [
        row for row in rows
        if str(getattr(row, "source_level", "") or "").upper() == "MN"
    ]
    if mn_rows:
        rows = mn_rows

    if not rows:
        return [], None

    by_year: dict[int, list[StaffYearRecord]] = {}
    for row in rows:
        by_year.setdefault(int(row.school_year_id), []).append(row)

    if int(target_year_id) in by_year:
        chosen_year_id = int(target_year_id)
    else:
        target_year = db.get(SchoolYear, target_year_id)
        target_start = _structured_year_start(
            getattr(target_year, "code", None)
        )
        candidates: list[tuple[int, int, int]] = []
        for year_id in by_year:
            year = db.get(SchoolYear, year_id)
            start = _structured_year_start(
                getattr(year, "code", None)
            )
            valid = 1 if (
                not target_start or start <= target_start
            ) else 0
            candidates.append((valid, start, year_id))
        _valid, _start, chosen_year_id = max(candidates)

    chosen = list(by_year.get(chosen_year_id, []))
    rank = {"CBQL": 0, "GIAO_VIEN": 1, "NHAN_VIEN": 2}
    chosen.sort(
        key=lambda row: (
            rank.get(str(row.position_group or "").upper(), 9),
            _pc_norm(
                getattr(
                    getattr(row, "staff_member", None),
                    "full_name",
                    "",
                )
            ),
            int(row.id),
        )
    )
    year = db.get(SchoolYear, chosen_year_id)
    return chosen, getattr(year, "code", None)


def _mn_institution_group(school: School | None) -> str:
    text = _pc_norm(
        str(getattr(school, "name", "") or "")
    )
    if any(
        token in text
        for token in (
            "NHOM TRE",
            "LOP MAM NON",
            "CO SO",
            "GDMN DOC LAP",
        )
    ):
        return "CO_SO_GDMN_DOC_LAP"
    return "TRUONG_MAM_NON"


def _mn_ethnic_count(rows: list[StaffYearRecord]) -> int:
    total = 0
    for row in rows:
        member = getattr(row, "staff_member", None)
        ethnic = _pc_norm(
            getattr(member, "ethnic_group", None)
        )
        if ethnic and ethnic != "KINH":
            total += 1
    return total
# === BAI_13B_6_V1_4_MN_DISPLAY_END ===


def _require_selected_school(scope: dict[str, Any]) -> RedirectResponse | None:
    if scope.get("selected_school_id") is not None:
        return None
    params = {"school_year_id": scope.get("selected_year_id") or "", "status": "chon_truong"}
    return RedirectResponse(url="/doi-ngu/nhap-mn-01-gv?" + urlencode(params), status_code=303)


def _school_in_scope(db: Session, request: Request, school_id: int) -> bool:
    user = lay_thong_tin_nguoi_dung(request)
    role = normalize_role_code((user or {}).get("role_code"))
    school = db.get(School, school_id)
    if school is None or not school.is_active:
        return False
    if role in ADMIN_ROLE_CODES or role == DEPARTMENT_ROLE_CODE:
        return True
    if role == COMMUNE_ROLE_CODE:
        return int(school.commune_id) == int((user or {}).get("commune_id") or 0)
    if role == SCHOOL_ROLE_CODE:
        return int(school.id) == int((user or {}).get("school_id") or 0)
    return False


def _staff_rows(db: Session, school_year_id: int, school_id: int) -> list[StaffYearRecord]:
    stmt = (
        select(StaffYearRecord)
        .where(
            StaffYearRecord.school_year_id == school_year_id,
            StaffYearRecord.school_id == school_id,
            StaffYearRecord.is_active.is_(True),
        )
        .options(selectinload(StaffYearRecord.staff_member))
        .order_by(StaffYearRecord.position_group.asc(), StaffYearRecord.id.asc())
    )
    return list(db.scalars(stmt).all())


def _gv_summary(rows: list[StaffYearRecord]) -> dict[str, int]:
    result = {
        "total": len(rows),
        "contracts": 0,
        "managers": 0,
        "teachers": 0,
        "employees": 0,
        "missing": 0,
    }
    for row in rows:
        if str(row.employment_type or "").startswith("HOP_DONG"):
            result["contracts"] += 1
        if row.position_group == "CBQL":
            result["managers"] += 1
        elif row.position_group == "GIAO_VIEN":
            result["teachers"] += 1
        elif row.position_group == "NHAN_VIEN":
            result["employees"] += 1
        if (
            row.employment_type == "CHUA_XAC_DINH"
            or row.qualification_level == "CHUA_XAC_DINH"
            or row.qualification_standard == "CHUA_XAC_DINH"
            or row.professional_standard == "CHUA_DANH_GIA"
            or (row.position_group == "GIAO_VIEN" and row.teaching_age_group == "KHONG_XAC_DINH")
        ):
            result["missing"] += 1
    return result



# === BAI_13B_11_14_7_2_HELPER_START ===
def _b1472_optional_bool(value: Any) -> bool | None:
    raw = str(value or "").strip().upper()

    if raw in {"CO", "1", "TRUE", "YES", "ON"}:
        return True

    if raw in {"KHONG", "0", "FALSE", "NO", "OFF"}:
        return False

    return None
# === BAI_13B_11_14_7_2_HELPER_END ===



# === BAI_13B_11_14_7_3_SOURCE_FIELDS_START ===
# Bài 14.7.3 chỉ chuẩn hóa giao diện và nguồn nhập đã có.
# Không tạo field DB mới. Các tỷ lệ vẫn tự tính.
# === BAI_13B_11_14_7_3_SOURCE_FIELDS_END ===


@router.get("/doi-ngu/nhap-mn-01-gv", response_class=HTMLResponse)
def gv_report_input_page(
    request: Request,
    school_year_id: int | None = None,
    commune_id: int | None = None,
    school_id: int | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
):
    scope = _mn_scope(db, request, school_year_id, commune_id, school_id)
    if scope["role_code"] not in REPORT_INPUT_VIEW_ROLES:
        return _redirect_forbidden()

    selected_school_id = scope["selected_school_id"]
    rows: list[StaffYearRecord] = []
    display_rows: list[StaffYearRecord] = []
    display_year = None
    extra = None
    class_summary = None
    csvc_record = None
    network_reference: dict[str, Any] = {}
    network_reference_year = None

    if selected_school_id is not None and scope["selected_year_id"] is not None:
        selected_year_id = int(scope["selected_year_id"])
        selected_school_id_int = int(selected_school_id)

        rows = _staff_rows(
            db,
            selected_year_id,
            selected_school_id_int,
        )
        current_rows = [
            row for row in rows
            if str(row.status_code or "") == "DANG_LAM_VIEC"
        ]

        if current_rows:
            display_rows = current_rows
            display_year = getattr(scope.get("selected_year"), "code", None)
        else:
            display_rows, display_year = _mn_reference_staff_rows(
                db,
                school_id=selected_school_id_int,
                target_year_id=selected_year_id,
            )

        network_reference, network_reference_year = _structured_network_reference(
            db,
            school_id=selected_school_id_int,
            level="MN",
            target_year_id=selected_year_id,
        )

        extra = db.scalar(
            select(SchoolMn01GvInput).where(
                SchoolMn01GvInput.school_id == selected_school_id_int,
                SchoolMn01GvInput.school_year_id == selected_year_id,
            )
        )
        class_summary = db.scalar(
            select(SchoolStaffYearSummary).where(
                SchoolStaffYearSummary.school_id == selected_school_id_int,
                SchoolStaffYearSummary.school_year_id == selected_year_id,
            )
        )

        csvc_record = db.scalar(
            select(SchoolMn01CsvcInput).where(
                SchoolMn01CsvcInput.school_id == selected_school_id_int,
                SchoolMn01CsvcInput.school_year_id == selected_year_id,
            )
        )

    display_summary = _gv_summary(display_rows)
    selected_school = scope.get("selected_school")

    ref_total_classes = int(network_reference.get("class_total") or 0)
    ref_preschool_3_4 = (
        int(network_reference.get("class_3_4y") or 0)
        + int(network_reference.get("class_4_5y") or 0)
    )
    ref_preschool_5 = int(network_reference.get("class_5_6y") or 0)

    # === BAI_13B_11_14_7_2_CSVC_CLASS_SOURCE_START ===
    # Số nhóm/lớp trong MN-01-GV chỉ đọc từ phân hệ CSVC.
    # Không nhập lại số lớp tại Đội ngũ.
    csvc_has_data = csvc_record is not None

    csvc_nursery_groups = (
        int(csvc_record.nursery_group_count or 0)
        if csvc_record is not None
        else 0
    )

    csvc_preschool_3_4 = (
        int(csvc_record.preschool_class_3_4_count or 0)
        if csvc_record is not None
        else 0
    )

    csvc_preschool_5 = (
        int(csvc_record.preschool_class_5_count or 0)
        if csvc_record is not None
        else 0
    )

    class_prefill = {
        "institution_group": (
            class_summary.institution_group
            if class_summary
            else _mn_institution_group(selected_school)
        ),
        "total_groups_classes": (
            csvc_nursery_groups
            + csvc_preschool_3_4
            + csvc_preschool_5
        ),
        "preschool_classes_3_4": csvc_preschool_3_4,
        "preschool_classes_5": csvc_preschool_5,
    }
    # === BAI_13B_11_14_7_2_CSVC_CLASS_SOURCE_END ===

    ethnic_prefill = (
        int(extra.ethnic_staff_count or 0)
        if extra and int(extra.ethnic_staff_count or 0) > 0
        else _mn_ethnic_count(display_rows)
    )

    classes_for_ratio = int(class_prefill["total_groups_classes"] or 0)
    teacher_class_ratio = (
        round(display_summary["teachers"] / classes_for_ratio, 2)
        if classes_for_ratio > 0
        else None
    )

    return templates.TemplateResponse(
        request=request,
        name="report_inputs/gv_mn01.html",
        context={
            **scope,
            "nguoi_dung": scope["user"],
            "rows": rows,
            "display_rows": display_rows,
            "display_year": display_year,
            "display_summary": display_summary,
            "summary": _gv_summary(rows),
            "extra": extra,
            "class_summary": class_summary,
            "class_prefill": class_prefill,
            "csvc_record": csvc_record,
            "csvc_has_data": csvc_has_data,
            "ethnic_prefill": ethnic_prefill,
            "network_reference": network_reference,
            "network_reference_year": network_reference_year,
            "teacher_class_ratio": teacher_class_ratio,
            "can_edit": scope["role_code"] in GV_EDIT_ROLES,
            "status": status,
            "employment_labels": EMPLOYMENT_LABELS,
            "teaching_age_labels": TEACHING_AGE_LABELS,
            "qualification_level_labels": QUALIFICATION_LEVEL_LABELS,
            "qualification_standard_labels": QUALIFICATION_STANDARD_LABELS,
            "professional_standard_labels": PROFESSIONAL_STANDARD_LABELS,
            "institution_group_labels": INSTITUTION_GROUP_LABELS,
            "position_labels": {
                "CBQL": "CBQL",
                "GIAO_VIEN": "Giáo viên",
                "NHAN_VIEN": "Nhân viên",
            },
            "teaching_level_labels": {
                "KHONG_DAY": "Không trực tiếp giảng dạy",
                "NHA_TRE": "Nhà trẻ",
                "MAU_GIAO": "Mẫu giáo",
                "TIEU_HOC": "Tiểu học",
                "THCS": "Trung học cơ sở",
                "LIEN_CAP_TH_THCS": "Tiểu học & THCS",
            },
            "status_labels": {
                "DANG_LAM_VIEC": "Đang làm việc",
                "CHUYEN_DI": "Chuyển đi",
                "NGHI_HUU": "Nghỉ hưu",
                "NGHI_VIEC": "Nghỉ việc",
                "TAM_NGHI": "Tạm nghỉ",
            },
        },
    )

@router.post("/doi-ngu/nhap-mn-01-gv")
async def gv_report_input_save(request: Request, db: Session = Depends(get_db)):
    user = lay_thong_tin_nguoi_dung(request)
    role = normalize_role_code((user or {}).get("role_code"))
    if role not in GV_EDIT_ROLES:
        return _redirect_forbidden()

    form = await request.form()
    year_id = _parse_int(form.get("school_year_id"), 0, 1)
    school_id = _parse_int(form.get("school_id"), 0, 1)
    if not year_id or not school_id or not _school_in_scope(db, request, school_id):
        return _redirect_forbidden()

    extra = db.scalar(
        select(SchoolMn01GvInput).where(
            SchoolMn01GvInput.school_id == school_id,
            SchoolMn01GvInput.school_year_id == year_id,
        )
    )
    if extra is None:
        extra = SchoolMn01GvInput(school_id=school_id, school_year_id=year_id)
        db.add(extra)
    extra.ethnic_staff_count = _parse_int(form.get("ethnic_staff_count"), 0)
    extra.notes = _clean(form.get("notes")) or None
    extra.updated_by_user_id = int((user or {}).get("id") or 0) or None

    # Bài 13B-11.14.7.2:
    # Cơ sở/nhóm/lớp là nguồn của CSVC.
    # MN-01-GV không ghi lại dữ liệu lớp ở đây.

    allowed_records = {int(r.id): r for r in _staff_rows(db, year_id, school_id)}
    for record_id, row in allowed_records.items():
        prefix = f"staff_{record_id}_"
        if prefix + "employment" not in form:
            continue
        row.employment_type = str(form.get(prefix + "employment") or row.employment_type)
        row.teaching_age_group = str(form.get(prefix + "age_group") or row.teaching_age_group)
        row.qualification_level = str(form.get(prefix + "qualification") or row.qualification_level)
        row.qualification_standard = str(form.get(prefix + "qual_standard") or row.qualification_standard)
        row.professional_standard = str(form.get(prefix + "professional") or row.professional_standard)
        _b1473_policy_raw = str(
            form.get(prefix + "policy") or "CHUA_XAC_DINH"
        ).strip().upper()

        if _b1473_policy_raw in {"CO", "1", "TRUE"}:
            row.receives_policy = True
        elif _b1473_policy_raw in {"KHONG", "0", "FALSE"}:
            row.receives_policy = False
        else:
            row.receives_policy = None
        # === BAI_13B_11_14_7_2_SAVE_MULTIGRADE_START ===
        if (
            str(row.position_group or "").strip().upper()
            == "GIAO_VIEN"
            and prefix + "multigrade" in form
        ):
            _b1472_multigrade = _b1472_optional_bool(
                form.get(prefix + "multigrade")
            )

            row.teaches_multigrade = _b1472_multigrade

            if _b1472_multigrade is True:
                row.uses_multigrade_program_4yo = (
                    _b1472_optional_bool(
                        form.get(prefix + "program_4yo")
                    )
                )

                row.uses_multigrade_program_5yo = (
                    _b1472_optional_bool(
                        form.get(prefix + "program_5yo")
                    )
                )
            else:
                row.uses_multigrade_program_4yo = None
                row.uses_multigrade_program_5yo = None
        # === BAI_13B_11_14_7_2_SAVE_MULTIGRADE_END ===

    db.commit()
    params = {"school_year_id": year_id, "school_id": school_id, "status": "saved"}
    school = db.get(School, school_id)
    if school is not None:
        params["commune_id"] = int(school.commune_id)
    return RedirectResponse(url="/doi-ngu/nhap-mn-01-gv?" + urlencode(params), status_code=303)


CSVC_SECTIONS = {
    "co-so": {"title": "Cơ sở và điểm trường", "number": "5.1"},
    "nhom-lop": {"title": "Nhóm/lớp và phòng học", "number": "5.2"},
    "cong-trinh": {"title": "Thiết bị, vệ sinh và nước sạch", "number": "5.3"},
    "bep-san": {"title": "Bếp ăn, sân chơi và đồ chơi", "number": "5.4"},
    "kiem-tra": {"title": "Kiểm tra dữ liệu MN-01-CSVC", "number": "5.5"},
}


def _csvc_record(db: Session, year_id: int, school_id: int) -> SchoolMn01CsvcInput | None:
    return db.scalar(
        select(SchoolMn01CsvcInput).where(
            SchoolMn01CsvcInput.school_id == school_id,
            SchoolMn01CsvcInput.school_year_id == year_id,
        )
    )


def _csvc_completion(record: SchoolMn01CsvcInput | None) -> dict[str, Any]:
    if record is None:
        return {"filled": 0, "total": 19, "percent": 0, "warnings": ["Chưa có dữ liệu CSVC của trường/năm học này."]}
    fields = [
        "facility_count", "satellite_site_count", "nursery_group_count", "preschool_class_3_4_count",
        "preschool_class_5_count", "total_classroom_count", "nursery_classroom_count",
        "permanent_preschool_room_count", "semi_permanent_preschool_room_count",
        "temporary_preschool_room_count", "equipped_preschool_class_count", "toilet_count",
        "standard_toilet_count", "clean_water_count", "standard_clean_water_count", "kitchen_count",
        "standard_kitchen_count", "playground_count", "playground_with_toys_count",
    ]
    filled = sum(1 for field in fields if getattr(record, field, None) is not None)
    warnings: list[str] = []
    preschool_classes = int(record.preschool_class_3_4_count or 0) + int(record.preschool_class_5_count or 0)
    preschool_rooms = (
        int(record.permanent_preschool_room_count or 0)
        + int(record.semi_permanent_preschool_room_count or 0)
        + int(record.temporary_preschool_room_count or 0)
    )
    if preschool_classes and preschool_rooms < preschool_classes:
        warnings.append("Số phòng học mẫu giáo đang nhỏ hơn số lớp mẫu giáo.")
    if int(record.standard_toilet_count or 0) > int(record.toilet_count or 0):
        warnings.append("Số khu vệ sinh đạt chuẩn lớn hơn tổng số khu vệ sinh.")
    if int(record.standard_clean_water_count or 0) > int(record.clean_water_count or 0):
        warnings.append("Số công trình nước sạch đạt chuẩn lớn hơn tổng số công trình.")
    if int(record.standard_kitchen_count or 0) > int(record.kitchen_count or 0):
        warnings.append("Số bếp ăn đạt chuẩn lớn hơn tổng số bếp ăn.")
    if int(record.playground_with_toys_count or 0) > int(record.playground_count or 0):
        warnings.append("Số sân có đồ chơi lớn hơn tổng số sân chơi.")
    return {"filled": filled, "total": len(fields), "percent": round(filled * 100 / len(fields)), "warnings": warnings}



# === BAI_13B_12_V2_4_3_9_SCHOOL_UNIT_SCOPE_HELPER ===
def _v2439_is_school_unit(user: dict | None, role_code: str | None = None) -> bool:
    """Nhận diện đúng tài khoản ĐƠN VỊ TRƯỜNG; không nhận giáo viên/CBQL cá nhân."""
    user = user or {}
    normalized_role = normalize_role_code(
        role_code if role_code is not None else user.get("role_code")
    )
    username = str(user.get("username") or "").strip().lower()
    school_id = user.get("school_id")

    if school_id is None:
        return False

    return normalized_role == SCHOOL_ROLE_CODE or username.startswith("truong_")


def _v2439_school_unit_id(user: dict | None) -> int | None:
    user = user or {}
    try:
        value = int(user.get("school_id"))
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _v2439_school_unit_owns_target(
    db: Session,
    user: dict | None,
    school_id: int | None,
) -> bool:
    """Cấp Trường chỉ được ghi đúng chính trường đang đăng nhập."""
    own_id = _v2439_school_unit_id(user)
    try:
        target_id = int(school_id or 0)
    except (TypeError, ValueError):
        return False

    if own_id is None or target_id != own_id:
        return False

    school = db.get(School, own_id)
    return school is not None and bool(school.is_active)

@router.get("/csvc/{section}", response_class=HTMLResponse)
def csvc_input_page(
    section: str,
    request: Request,
    school_year_id: int | None = None,
    commune_id: int | None = None,
    school_id: int | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
):
    if section not in CSVC_SECTIONS:
        return RedirectResponse(url="/csvc/co-so", status_code=303)
    scope = _mn_scope(db, request, school_year_id, commune_id, school_id)
    if scope["role_code"] not in REPORT_INPUT_VIEW_ROLES:
        return _redirect_forbidden()
    record = None
    if scope["selected_year_id"] and scope["selected_school_id"]:
        record = _csvc_record(db, int(scope["selected_year_id"]), int(scope["selected_school_id"]))
    return templates.TemplateResponse(
        request=request,
        name="report_inputs/csvc_mn01.html",
        context={
            **scope,
            "nguoi_dung": scope["user"],
            "section": section,
            "section_meta": CSVC_SECTIONS[section],
            "sections": CSVC_SECTIONS,
            "record": record,
            "completion": _csvc_completion(record),
            # === BAI_13B_12_V2_4_3_8_CSVC_ALL_LEVEL_SCHOOL_WRITE ===
            "can_edit": (
                (scope["role_code"] in CSVC_EDIT_ROLES or _v2439_is_school_unit(scope.get("user"), scope.get("role_code")))  # === BAI_13B_12_V2_4_3_9_MN_PAGE_CAN_EDIT ===
            ),
            "status": status,
        },
    )


@router.post("/csvc/{section}")
async def csvc_input_save(section: str, request: Request, db: Session = Depends(get_db)):
    if section not in CSVC_SECTIONS or section == "kiem-tra":
        return RedirectResponse(url="/csvc/co-so", status_code=303)

    user = lay_thong_tin_nguoi_dung(request)
    role = normalize_role_code((user or {}).get("role_code"))

    # === BAI_13B_12_V2_4_3_9_MN_SAVE_OWN_SCHOOL ===
    is_school_unit = _v2439_is_school_unit(user, role)

    if role not in CSVC_EDIT_ROLES and not is_school_unit:
        return _redirect_forbidden()

    form = await request.form()
    year_id = _parse_int(form.get("school_year_id"), 0, 1)
    submitted_school_id = _parse_int(form.get("school_id"), 0, 1)

    if is_school_unit:
        school_id = _v2439_school_unit_id(user)
        if not year_id or not _v2439_school_unit_owns_target(db, user, school_id):
            return _redirect_forbidden()
    else:
        school_id = submitted_school_id
        if (
            not year_id
            or not school_id
            or not _school_in_scope(db, request, school_id)
        ):
            return _redirect_forbidden()

    record = _csvc_record(db, year_id, school_id)
    if record is None:
        record = SchoolMn01CsvcInput(school_id=school_id, school_year_id=year_id)
        db.add(record)

    field_map = {
        "co-so": ["facility_count", "satellite_site_count"],
        "nhom-lop": [
            "nursery_group_count", "preschool_class_3_4_count", "preschool_class_5_count",
            "total_classroom_count", "nursery_classroom_count", "permanent_preschool_room_count",
            "semi_permanent_preschool_room_count", "temporary_preschool_room_count",
        ],
        "cong-trinh": [
            "equipped_preschool_class_count", "toilet_count", "standard_toilet_count",
            "clean_water_count", "standard_clean_water_count",
        ],
        "bep-san": [
            "kitchen_count", "standard_kitchen_count", "playground_count", "playground_with_toys_count",
        ],
    }
    for field in field_map[section]:
        setattr(record, field, _parse_int(form.get(field), int(getattr(record, field, 0) or 0)))
    record.notes = _clean(form.get("notes")) or record.notes
    record.updated_by_user_id = int((user or {}).get("id") or 0) or None
    db.commit()

    school = db.get(School, school_id)
    params = {"school_year_id": year_id, "school_id": school_id, "status": "saved"}
    if school is not None:
        params["commune_id"] = int(school.commune_id)
    return RedirectResponse(url=f"/csvc/{section}?" + urlencode(params), status_code=303)


def _finance_scope(
    db: Session,
    request: Request,
    commune_id: int | None,
    school_id: int | None,
) -> dict[str, Any]:
    user = lay_thong_tin_nguoi_dung(request)
    role = normalize_role_code((user or {}).get("role_code"))
    allowed = {*ADMIN_ROLE_CODES, DEPARTMENT_ROLE_CODE, COMMUNE_ROLE_CODE, SCHOOL_ROLE_CODE}
    if role not in allowed:
        return {
            "user": user,
            "role": role,
            "communes": [],
            "schools": [],
            "selected_commune_id": None,
            "selected_school_id": None,
            "selected_school": None,
            "scope_label": "Không có quyền",
        }

    own_commune_id = int((user or {}).get("commune_id") or 0) or None
    own_school_id = int((user or {}).get("school_id") or 0) or None

    if role == SCHOOL_ROLE_CODE:
        school = db.get(School, own_school_id) if own_school_id else None
        if school is None or not school.is_active or not is_preschool_school(school):
            return {
                "user": user,
                "role": role,
                "communes": [],
                "schools": [],
                "selected_commune_id": None,
                "selected_school_id": None,
                "selected_school": None,
                "scope_label": "Trường không thuộc phạm vi Mầm non",
            }
        commune = db.get(Commune, int(school.commune_id))
        return {
            "user": user,
            "role": role,
            "communes": [commune] if commune is not None else [],
            "schools": [school],
            "selected_commune_id": int(school.commune_id),
            "selected_school_id": int(school.id),
            "selected_school": school,
            "scope_label": f"Trường {school.name}",
        }

    if role == COMMUNE_ROLE_CODE:
        communes = list(
            db.scalars(
                select(Commune).where(
                    Commune.id == own_commune_id,
                    Commune.is_active.is_(True),
                )
            ).all()
        )
        school_ids = finance_school_ids_for_scope(db, commune_id=own_commune_id)
        schools = list(
            db.scalars(
                select(School)
                .where(School.id.in_(school_ids))
                .order_by(School.name.asc(), School.id.asc())
            ).all()
        ) if school_ids else []
        valid_ids = {int(s.id) for s in schools}
        selected_school_id = int(school_id) if school_id and int(school_id) in valid_ids else None
        selected_school = next((s for s in schools if int(s.id) == int(selected_school_id or 0)), None)
        scope_label = f"Trường {selected_school.name}" if selected_school is not None else (communes[0].name if communes else "Cấp xã/phường")
        return {
            "user": user,
            "role": role,
            "communes": communes,
            "schools": schools,
            "selected_commune_id": own_commune_id,
            "selected_school_id": selected_school_id,
            "selected_school": selected_school,
            "scope_label": scope_label,
        }

    communes = list(
        db.scalars(
            select(Commune)
            .where(Commune.is_active.is_(True))
            .order_by(Commune.name.asc(), Commune.id.asc())
        ).all()
    )
    valid_commune_ids = {int(c.id) for c in communes}
    selected_commune_id = int(commune_id) if commune_id and int(commune_id) in valid_commune_ids else None

    school_ids = finance_school_ids_for_scope(db, commune_id=selected_commune_id) if selected_commune_id else []
    schools = list(
        db.scalars(
            select(School)
            .where(School.id.in_(school_ids))
            .order_by(School.name.asc(), School.id.asc())
        ).all()
    ) if school_ids else []
    valid_school_ids = {int(s.id) for s in schools}
    selected_school_id = int(school_id) if school_id and int(school_id) in valid_school_ids else None
    selected_school = next((s for s in schools if int(s.id) == int(selected_school_id or 0)), None)

    if selected_school is not None:
        scope_label = f"Trường {selected_school.name}"
    elif selected_commune_id is not None:
        commune = next((c for c in communes if int(c.id) == selected_commune_id), None)
        scope_label = commune.name if commune is not None else "Cấp xã/phường"
    else:
        scope_label = "Toàn tỉnh"

    return {
        "user": user,
        "role": role,
        "communes": communes,
        "schools": schools,
        "selected_commune_id": selected_commune_id,
        "selected_school_id": selected_school_id,
        "selected_school": selected_school,
        "scope_label": scope_label,
    }


def _school_year_start(year: SchoolYear | None) -> int:
    import re
    from datetime import datetime
    match = re.search(r"(20\d{2})", str(getattr(year, "code", "") or ""))
    return int(match.group(1)) if match else datetime.now().year


@router.get("/bao-cao/tai-chinh/nhap", response_class=HTMLResponse)
def finance_input_page(
    request: Request,
    school_year_id: int | None = None,
    commune_id: int | None = None,
    school_id: int | None = None,
    report_year: int | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
):
    scope = _finance_scope(db, request, commune_id, school_id)
    user = scope["user"]
    role = scope["role"]
    if role not in {*ADMIN_ROLE_CODES, DEPARTMENT_ROLE_CODE, COMMUNE_ROLE_CODE, SCHOOL_ROLE_CODE}:
        return _redirect_forbidden()

    years = _load_school_years(db)
    selected_year_id = _choose_year_id(years, school_year_id)
    selected_school_year = next((y for y in years if int(y.id) == int(selected_year_id or 0)), None)
    base_year = _school_year_start(selected_school_year)
    selected_report_year = int(report_year or base_year)
    if selected_report_year < 2020 or selected_report_year > 2050:
        selected_report_year = base_year

    values, total_school_count, data_school_count = load_finance_values(
        db,
        report_year=selected_report_year,
        commune_id=scope["selected_commune_id"] if scope["selected_school_id"] is None else None,
        school_id=scope["selected_school_id"],
    )

    can_edit = (
        role == SCHOOL_ROLE_CODE
        and scope["selected_school_id"] is not None
        and int(scope["selected_school_id"]) == int((user or {}).get("school_id") or 0)
    )

    return templates.TemplateResponse(
        request=request,
        name="report_inputs/finance.html",
        context={
            "nguoi_dung": user,
            "role_code": role,
            "communes": scope["communes"],
            "schools": scope["schools"],
            "selected_commune_id": scope["selected_commune_id"],
            "selected_school_id": scope["selected_school_id"],
            "selected_school": scope["selected_school"],
            "scope_label": scope["scope_label"],
            "school_years": years,
            "selected_year_id": selected_year_id,
            "selected_school_year": selected_school_year,
            "report_year": selected_report_year,
            "report_year_options": list(range(max(2020, base_year - 4), base_year + 6)),
            "items": FINANCE_ITEMS,
            "values": values,
            "can_edit": can_edit,
            "is_aggregate": scope["selected_school_id"] is None,
            "total_school_count": total_school_count,
            "data_school_count": data_school_count,
            "status": status,
        },
    )


@router.post("/bao-cao/tai-chinh/nhap")
async def finance_input_save(request: Request, db: Session = Depends(get_db)):
    user = lay_thong_tin_nguoi_dung(request)
    role = normalize_role_code((user or {}).get("role_code"))
    if role != SCHOOL_ROLE_CODE:
        return _redirect_forbidden()

    form = await request.form()
    school_id = _parse_int(form.get("school_id"), 0, 1)
    report_year = _parse_int(form.get("report_year"), 0, 2020)
    school_year_id = _parse_int(form.get("school_year_id"), 0, 1)
    own_school_id = int((user or {}).get("school_id") or 0)
    if school_id != own_school_id:
        return _redirect_forbidden()

    school = db.get(School, school_id)
    if school is None or not school.is_active or not is_preschool_school(school):
        return _redirect_forbidden()
    if db.get(SchoolYear, school_year_id) is None:
        return _redirect_forbidden()
    if report_year < 2020 or report_year > 2050:
        return _redirect_forbidden()

    existing = {
        row.item_code: row
        for row in db.scalars(
            select(SchoolFinanceReportValue).where(
                SchoolFinanceReportValue.school_id == school_id,
                SchoolFinanceReportValue.report_year == report_year,
            )
        ).all()
    }
    for item in FINANCE_ITEMS:
        code = item["code"]
        amount = _parse_optional_decimal(form.get(f"amount_{code}"))
        note = _clean(form.get(f"note_{code}")) or None
        row = existing.get(code)
        if row is None and amount is None and note is None:
            continue
        if row is None:
            row = SchoolFinanceReportValue(
                school_id=school_id,
                report_year=report_year,
                item_code=code,
            )
            db.add(row)
        row.amount = amount
        row.note = note
        row.updated_by_user_id = int((user or {}).get("id") or 0) or None

    db.commit()
    params = {
        "school_year_id": school_year_id,
        "commune_id": int(school.commune_id),
        "school_id": school_id,
        "report_year": report_year,
        "status": "saved",
    }
    return RedirectResponse(url="/bao-cao/tai-chinh/nhap?" + urlencode(params), status_code=303)


# === BAI_13B_6_V1_STRUCTURED_INPUT_START ===

STRUCTURED_FORM_EDIT_ROLES = frozenset({
    *ADMIN_ROLE_CODES,
    COMMUNE_ROLE_CODE,
    SCHOOL_ROLE_CODE,
})


def _structured_catalog(slug: str) -> dict[str, Any] | None:
    return STRUCTURED_SCHOOL_FORMS.get(slug)


def _structured_record(
    db: Session,
    *,
    school_id: int,
    school_year_id: int,
    form_code: str,
) -> SchoolStructuredReportInput | None:
    return db.scalar(
        select(SchoolStructuredReportInput).where(
            SchoolStructuredReportInput.school_id == school_id,
            SchoolStructuredReportInput.school_year_id == school_year_id,
            SchoolStructuredReportInput.form_code == form_code,
        )
    )


def _structured_load_json(record: SchoolStructuredReportInput | None) -> dict[str, Any]:
    if record is None:
        return {}
    try:
        data = json.loads(record.data_json or "{}")
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


# === BAI_13B_6_V1_2_NETWORK_DATA_START ===
def _structured_year_start(code: str | None) -> int:
    text = str(code or "").strip()
    try:
        return int(text.split("-", 1)[0])
    except (TypeError, ValueError):
        return 0


def _structured_network_reference(
    db: Session,
    *,
    school_id: int,
    level: str,
    target_year_id: int,
) -> tuple[dict[str, Any], str | None]:
    rows = list(
        db.scalars(
            select(SchoolNetworkYearData)
            .where(
                SchoolNetworkYearData.school_id == school_id,
                SchoolNetworkYearData.level_code == level,
            )
            .options(selectinload(SchoolNetworkYearData.school_year))
        ).all()
    )
    if not rows:
        return {}, None

    target_year = db.get(SchoolYear, target_year_id) if target_year_id else None
    target_start = _structured_year_start(getattr(target_year, "code", None))

    def key(item: SchoolNetworkYearData) -> tuple[int, int]:
        start = _structured_year_start(getattr(item.school_year, "code", None))
        # Ưu tiên năm không vượt quá năm đang nhập; nếu không có thì lấy gần nhất.
        valid = 1 if (not target_start or start <= target_start) else 0
        return (valid, start)

    item = max(rows, key=key)
    try:
        data = json.loads(item.data_json or "{}")
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}
    return data, getattr(item.school_year, "code", None)


def _structured_network_school_ids(
    db: Session,
    *,
    level: str,
) -> set[int]:
    return {
        int(value)
        for value in db.scalars(
            select(SchoolNetworkYearData.school_id)
            .where(SchoolNetworkYearData.level_code == level)
            .distinct()
        ).all()
    }


def _structured_school_supports_level(
    db: Session,
    *,
    school: School,
    level: str,
    grades: dict[int, list[int]],
) -> bool:
    network_ids = _structured_network_school_ids(db, level=level)
    if int(school.id) in network_ids:
        return True
    return _pc_school_level(school, grades) == level
# === BAI_13B_6_V1_2_NETWORK_DATA_END ===


def _structured_level_scope(
    db: Session,
    request: Request,
    catalog: dict[str, Any],
    school_year_id: int | None,
    commune_id: int | None,
    school_id: int | None,
) -> dict[str, Any]:
    scope = _load_scope(db, request, school_year_id, commune_id, school_id)
    year_id = int(scope.get("selected_year_id") or 0)
    schools = list(scope.get("schools") or [])

    grades: dict[int, list[int]] = {}
    if year_id and schools:
        _all_schools, grades = _pc_schools_and_classes(
            db,
            year_id,
            int(scope["selected_commune_id"]) if scope.get("selected_commune_id") else None,
            None,
        )

    level = catalog["level"]
    network_ids = _structured_network_school_ids(db, level=level)
    filtered = [
        school
        for school in schools
        if int(school.id) in network_ids
        or _pc_school_level(school, grades) == level
    ]

    valid_ids = {int(s.id) for s in filtered}
    selected_school_id = scope.get("selected_school_id")
    if selected_school_id is not None and int(selected_school_id) not in valid_ids:
        selected_school_id = None

    selected_school = next(
        (s for s in filtered if int(s.id) == int(selected_school_id or 0)),
        None,
    )

    scope["schools"] = filtered
    scope["selected_school_id"] = selected_school_id
    scope["selected_school"] = selected_school
    if selected_school is not None:
        scope["scope_label"] = f"Trường {selected_school.name}"

    return scope


def _structured_class_count(
    db: Session,
    *,
    year_id: int,
    school_id: int,
    level: str,
) -> int:
    schools, grades = _pc_schools_and_classes(
        db,
        year_id,
        None,
        school_id,
    )
    current_count = 0
    if schools:
        current_count = _pc_class_count(grades.get(int(school_id), []), level)
    if current_count:
        return current_count

    network_data, _network_year = _structured_network_reference(
        db,
        school_id=school_id,
        level=level,
        target_year_id=year_id,
    )
    try:
        return max(0, int(float(network_data.get("class_total") or 0)))
    except (TypeError, ValueError):
        return 0


def _structured_staff_auto_values(
    db: Session,
    *,
    year_id: int,
    school_id: int,
    catalog: dict[str, Any],
) -> tuple[dict[str, Any], int]:
    level = catalog["level"]
    class_count = _structured_class_count(
        db,
        year_id=year_id,
        school_id=school_id,
        level=level,
    )

    staff_by_school = _pc_staff_rows(db, year_id, [school_id])
    records = list(staff_by_school.get(int(school_id), []))

    # Nếu năm đang nhập chưa có hồ sơ đội ngũ chi tiết, chỉ gợi ý những
    # chỉ tiêu có thể lấy chính xác từ dữ liệu mạng lưới năm trước.
    if not records:
        network_data, _network_year = _structured_network_reference(
            db,
            school_id=school_id,
            level=level,
            target_year_id=year_id,
        )
        result: dict[str, Any] = {}
        teachers = network_data.get("teachers")
        if teachers is not None:
            try:
                result["teacher_total"] = max(0, int(float(teachers)))
            except (TypeError, ValueError):
                pass
        return result, class_count

    summary = _pc_staff_summary(records, class_count)

    result: dict[str, Any] = {
        "principal": summary["principal"],
        "vice_principal": summary["vice"],
        "teacher_total": summary["teachers"],
        "teacher_permanent": summary["bienche"],
        "teacher_contract": summary["hopdong"],
        "teacher_female": summary["female"],
        "teacher_ethnic": summary["ethnic"],
        "qual_postgrad": int(summary["qual"].get("postgrad", 0)),
        "qual_university": int(summary["qual"].get("univ", 0)),
        "qual_college": int(summary["qual"].get("college", 0)),
        "qual_secondary": int(summary["qual"].get("secondary", 0)),
        "prof_excellent": int(summary["prof"].get("excellent", 0)),
        "prof_good": int(summary["prof"].get("good", 0)),
        "prof_average": int(summary["prof"].get("average", 0)),
        "prof_poor": int(summary["prof"].get("poor", 0)),
        "employee_office": int(summary["employees"].get("office", 0)),
    }

    team_leader = 0
    for row in records:
        text = _pc_norm(" ".join([
            str(getattr(row, "position_title", "") or ""),
            str(getattr(row, "notes", "") or ""),
        ]))
        if "TONG PHU TRACH" in text or "TPT DOI" in text:
            team_leader += 1
    result["team_leader"] = team_leader

    if level == "TH":
        result.update({
            "qual_below_secondary": 0,
            "training_primary": int(summary["subjects"].get("general", 0)),
            "training_music": int(summary["subjects"].get("music", 0)),
            "training_art": int(summary["subjects"].get("art", 0)),
            "training_pe": int(summary["subjects"].get("pe", 0)),
            "training_it": int(summary["subjects"].get("it", 0)),
            "training_foreign": int(summary["subjects"].get("english", 0))
                + int(summary["subjects"].get("foreign", 0)),
            "training_other": int(summary["subjects"].get("other", 0)),
            "employee_library_equipment": int(summary["employees"].get("library", 0))
                + int(summary["employees"].get("equipment", 0)),
        })
    else:
        result.update({
            "subject_math": int(summary["subjects"].get("math", 0)),
            "subject_literature": int(summary["subjects"].get("literature", 0)),
            "subject_physics": int(summary["subjects"].get("physics", 0)),
            "subject_chemistry": int(summary["subjects"].get("chemistry", 0)),
            "subject_biology": int(summary["subjects"].get("biology", 0)),
            "subject_history": int(summary["subjects"].get("history", 0)),
            "subject_geography": int(summary["subjects"].get("geography", 0)),
            "subject_music": int(summary["subjects"].get("music", 0)),
            "subject_art": int(summary["subjects"].get("art", 0)),
            "subject_pe": int(summary["subjects"].get("pe", 0)),
            "subject_civic": int(summary["subjects"].get("civic", 0)),
            "subject_technology": int(summary["subjects"].get("technology", 0)),
            "subject_it": int(summary["subjects"].get("it", 0)),
            "subject_english": int(summary["subjects"].get("english", 0)),
            "subject_russian": int(summary["subjects"].get("russian", 0)),
            "subject_french": int(summary["subjects"].get("french", 0)),
            "subject_other": int(summary["subjects"].get("other", 0)),
            "employee_library": int(summary["employees"].get("library", 0)),
            "employee_equipment_lab": int(summary["employees"].get("equipment", 0)),
            "employee_health": int(summary["employees"].get("health", 0)),
        })

    return result, class_count


# === BAI_13B_6_V1_3_STAFF_DETAIL_START ===
def _structured_staff_row_matches_level(
    row: StaffYearRecord,
    level: str,
) -> bool:
    source_level = str(
        getattr(row, "source_level", "") or ""
    ).strip().upper()

    teaching_level = str(
        getattr(row, "teaching_level", "") or ""
    ).strip().upper()

    if level == "TH":
        if source_level == "TH":
            return True
        if teaching_level in {"TIEU_HOC", "LIEN_CAP_TH_THCS"}:
            return True
        # Hồ sơ cũ chưa có trường source_level vẫn cho hiển thị
        # nếu không xác định rõ là THCS.
        return source_level not in {"THCS"}

    if level == "THCS":
        if source_level == "THCS":
            return True
        if teaching_level in {"THCS", "LIEN_CAP_TH_THCS"}:
            return True
        return source_level not in {"TH"}

    return True


def _structured_staff_detail_rows(
    db: Session,
    *,
    school_id: int,
    target_year_id: int,
    level: str,
) -> tuple[list[StaffYearRecord], str | None]:
    """
    Lấy danh sách tên nhân sự để hiển thị ngay dưới biểu TH-01-GV/
    THCS-01-GV.

    Ưu tiên năm đang nhập. Nếu năm đang nhập chưa có hồ sơ chi tiết,
    lấy năm dữ liệu gần nhất không vượt quá năm đang nhập
    (ví dụ 2025-2026 làm tham chiếu cho 2026-2027).
    """
    rows = list(
        db.scalars(
            select(StaffYearRecord)
            .where(
                StaffYearRecord.school_id == school_id,
                StaffYearRecord.is_active.is_(True),
                StaffYearRecord.status_code == "DANG_LAM_VIEC",
            )
            .options(
                selectinload(StaffYearRecord.staff_member),
                selectinload(StaffYearRecord.school_year),
            )
        ).all()
    )

    rows = [
        row
        for row in rows
        if _structured_staff_row_matches_level(row, level)
    ]

    if not rows:
        return [], None

    by_year: dict[int, list[StaffYearRecord]] = {}
    for row in rows:
        by_year.setdefault(int(row.school_year_id), []).append(row)

    if int(target_year_id) in by_year:
        chosen_year_id = int(target_year_id)
    else:
        target_year = db.get(SchoolYear, target_year_id)
        target_start = _structured_year_start(
            getattr(target_year, "code", None)
        )

        candidates: list[tuple[int, int]] = []
        for year_id in by_year:
            year = db.get(SchoolYear, year_id)
            start = _structured_year_start(
                getattr(year, "code", None)
            )
            valid = 1 if (
                not target_start or start <= target_start
            ) else 0
            candidates.append((valid, start, year_id))

        _valid, _start, chosen_year_id = max(candidates)

    chosen_rows = list(by_year.get(chosen_year_id, []))

    position_rank = {
        "CBQL": 0,
        "GIAO_VIEN": 1,
        "NHAN_VIEN": 2,
    }

    chosen_rows.sort(
        key=lambda row: (
            position_rank.get(
                str(row.position_group or "").upper(),
                9,
            ),
            _pc_norm(
                getattr(
                    getattr(row, "staff_member", None),
                    "full_name",
                    "",
                )
            ),
            int(row.id),
        )
    )

    chosen_year = db.get(SchoolYear, chosen_year_id)
    chosen_year_code = (
        getattr(chosen_year, "code", None)
        if chosen_year is not None
        else None
    )

    return chosen_rows, chosen_year_code
# === BAI_13B_6_V1_3_STAFF_DETAIL_END ===

def _structured_auto_values(
    db: Session,
    *,
    year_id: int,
    school_id: int,
    catalog: dict[str, Any],
) -> tuple[dict[str, Any], int]:
    if catalog["kind"] == "staff":
        return _structured_staff_auto_values(
            db,
            year_id=year_id,
            school_id=school_id,
            catalog=catalog,
        )

    class_count = _structured_class_count(
        db,
        year_id=year_id,
        school_id=school_id,
        level=catalog["level"],
    )
    network_data, _network_year = _structured_network_reference(
        db,
        school_id=school_id,
        level=catalog["level"],
        target_year_id=year_id,
    )

    result: dict[str, Any] = {}
    if class_count:
        result["class_total"] = class_count

    # Các cột phòng học trong hai file mạng lưới là số liệu gốc có thể
    # dùng làm số tham chiếu. Người dùng vẫn phải kiểm tra/lưu cho năm mới.
    mapping = {
        "rooms_permanent": "room_permanent",
        "rooms_semi_permanent": "room_semi_permanent",
        "rooms_temporary": "room_temporary",
    }
    for source_code, target_code in mapping.items():
        value = network_data.get(source_code)
        if value is None:
            continue
        try:
            result[target_code] = max(0, int(float(value)))
        except (TypeError, ValueError):
            pass

    return result, class_count

def _structured_effective_values(
    catalog: dict[str, Any],
    saved: dict[str, Any],
    auto_values: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, str]]:
    effective: dict[str, Any] = {}
    source: dict[str, str] = {}
    for field in flatten_fields(catalog):
        code = field["code"]
        if code in saved and saved[code] is not None:
            effective[code] = saved[code]
            source[code] = "saved"
        elif code in auto_values and auto_values[code] is not None:
            effective[code] = auto_values[code]
            source[code] = "auto"
        else:
            effective[code] = None
    return effective, source


def _structured_number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _structured_derived(
    catalog: dict[str, Any],
    effective: dict[str, Any],
    class_count: int,
) -> float | None:
    if catalog["kind"] == "staff":
        teachers = _structured_number(effective.get("teacher_total"))
        if teachers is None or class_count <= 0:
            return None
        return round(teachers / class_count, 2)

    classes = _structured_number(effective.get("class_total"))
    if not classes:
        return None
    rooms = sum(
        _structured_number(effective.get(code)) or 0
        for code in (
            "room_permanent",
            "room_semi_permanent",
            "room_temporary",
            "room_rent_borrow",
        )
    )
    return round(rooms / classes, 2)


def _structured_warnings(
    catalog: dict[str, Any],
    effective: dict[str, Any],
    class_count: int,
) -> list[str]:
    warnings: list[str] = []

    if catalog["kind"] == "staff":
        total = _structured_number(effective.get("teacher_total"))
        permanent = _structured_number(effective.get("teacher_permanent"))
        contract = _structured_number(effective.get("teacher_contract"))
        female = _structured_number(effective.get("teacher_female"))
        ethnic = _structured_number(effective.get("teacher_ethnic"))

        if total is not None and permanent is not None and contract is not None:
            if abs((permanent + contract) - total) > 0.001:
                warnings.append("Tổng giáo viên chưa bằng Biên chế + Hợp đồng.")
        if total is not None and female is not None and female > total:
            warnings.append("Số giáo viên nữ đang lớn hơn tổng số giáo viên.")
        if total is not None and ethnic is not None and ethnic > total:
            warnings.append("Số giáo viên dân tộc đang lớn hơn tổng số giáo viên.")
        if class_count <= 0:
            warnings.append("Chưa xác định được số lớp từ danh mục lớp; tỉ lệ giáo viên/lớp chưa thể tính.")
    else:
        classes = _structured_number(effective.get("class_total"))
        permanent = _structured_number(effective.get("room_permanent")) or 0
        semi = _structured_number(effective.get("room_semi_permanent")) or 0
        temp = _structured_number(effective.get("room_temporary")) or 0
        rent = _structured_number(effective.get("room_rent_borrow")) or 0
        rooms = permanent + semi + temp + rent
        if classes is not None and classes > 0 and rooms < classes:
            warnings.append("Tổng số phòng học đang nhỏ hơn số lớp.")
        if classes is None:
            warnings.append("Chưa nhập/xác định số lớp.")

    return warnings


@router.get("/bieu-nhap/{slug}", response_class=HTMLResponse)
def structured_school_form_page(
    slug: str,
    request: Request,
    school_year_id: int | None = None,
    commune_id: int | None = None,
    school_id: int | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
):
    catalog = _structured_catalog(slug)
    if catalog is None:
        return RedirectResponse(url="/", status_code=303)

    scope = _structured_level_scope(
        db,
        request,
        catalog,
        school_year_id,
        commune_id,
        school_id,
    )
    if scope["role_code"] not in REPORT_INPUT_VIEW_ROLES:
        return _redirect_forbidden()

    record = None
    saved: dict[str, Any] = {}
    auto_values: dict[str, Any] = {}
    class_count = 0

    if scope["selected_school_id"] and scope["selected_year_id"]:
        sid = int(scope["selected_school_id"])
        yid = int(scope["selected_year_id"])
        record = _structured_record(
            db,
            school_id=sid,
            school_year_id=yid,
            form_code=catalog["form_code"],
        )
        saved = _structured_load_json(record)
        auto_values, class_count = _structured_auto_values(
            db,
            year_id=yid,
            school_id=sid,
            catalog=catalog,
        )

    network_reference_year = None
    staff_detail_rows: list[StaffYearRecord] = []
    staff_detail_year = None

    if scope["selected_school_id"] and scope["selected_year_id"]:
        _network_data, network_reference_year = _structured_network_reference(
            db,
            school_id=int(scope["selected_school_id"]),
            level=catalog["level"],
            target_year_id=int(scope["selected_year_id"]),
        )

        if catalog["kind"] == "staff":
            staff_detail_rows, staff_detail_year = _structured_staff_detail_rows(
                db,
                school_id=int(scope["selected_school_id"]),
                target_year_id=int(scope["selected_year_id"]),
                level=catalog["level"],
            )

    effective_values, source_by_code = _structured_effective_values(
        catalog,
        saved,
        auto_values,
    )
    fields = flatten_fields(catalog)
    filled = sum(
        1 for field in fields
        if effective_values.get(field["code"]) is not None
    )

    return templates.TemplateResponse(
        request=request,
        name="report_inputs/structured_school_form.html",
        context={
            **scope,
            "nguoi_dung": scope["user"],
            "slug": slug,
            "catalog": catalog,
            "record": record,
            "effective_values": effective_values,
            "source_by_code": source_by_code,
            "class_count": class_count,
            "derived_value": _structured_derived(
                catalog,
                effective_values,
                class_count,
            ),
            "completion": {
                "filled": filled,
                "total": len(fields),
                "percent": round(filled * 100 / len(fields)) if fields else 0,
            },
            "warnings": _structured_warnings(
                catalog,
                effective_values,
                class_count,
            ),
            # === BAI_13B_12_V2_4_3_8_STRUCTURED_ALL_LEVEL_SCHOOL_WRITE ===
            "can_edit": (
                (scope["role_code"] in STRUCTURED_FORM_EDIT_ROLES or _v2439_is_school_unit(scope.get("user"), scope.get("role_code")))  # === BAI_13B_12_V2_4_3_9_STRUCT_PAGE_CAN_EDIT ===
            ),
            "status": status,
            "network_reference_year": network_reference_year,
            "staff_detail_rows": staff_detail_rows,
            "staff_detail_year": staff_detail_year,
            "staff_position_labels": {
                "CBQL": "CBQL",
                "GIAO_VIEN": "Giáo viên",
                "NHAN_VIEN": "Nhân viên",
            },
            "staff_status_labels": {
                "DANG_LAM_VIEC": "Đang làm việc",
                "CHUYEN_DI": "Chuyển đi",
                "NGHI_HUU": "Nghỉ hưu",
                "NGHI_VIEC": "Nghỉ việc",
                "TAM_NGHI": "Tạm nghỉ",
            },
            "employment_labels": EMPLOYMENT_LABELS,
            "qualification_level_labels": QUALIFICATION_LEVEL_LABELS,
        },
    )


@router.post("/bieu-nhap/{slug}")
async def structured_school_form_save(
    slug: str,
    request: Request,
    db: Session = Depends(get_db),
):
    catalog = _structured_catalog(slug)
    if catalog is None:
        return RedirectResponse(url="/", status_code=303)


    user = lay_thong_tin_nguoi_dung(request)
    role = normalize_role_code((user or {}).get("role_code"))

    # === BAI_13B_12_V2_4_3_9_STRUCT_SAVE_OWN_SCHOOL ===
    is_school_unit = _v2439_is_school_unit(user, role)

    if role not in STRUCTURED_FORM_EDIT_ROLES and not is_school_unit:
        return _redirect_forbidden()

    form = await request.form()
    year_id = _parse_int(form.get("school_year_id"), 0, 1)
    submitted_school_id = _parse_int(form.get("school_id"), 0, 1)

    if is_school_unit:
        school_id = _v2439_school_unit_id(user)
        if not year_id or not _v2439_school_unit_owns_target(db, user, school_id):
            return _redirect_forbidden()
    else:
        school_id = submitted_school_id
        if (
            not year_id
            or not school_id
            or not _school_in_scope(db, request, school_id)
        ):
            return _redirect_forbidden()

    schools, grades = _pc_schools_and_classes(db, year_id, None, school_id)
    school = schools[0] if schools else db.get(School, school_id)
    if school is None or not _structured_school_supports_level(
        db,
        school=school,
        level=catalog["level"],
        grades=grades,
    ):
        return _redirect_forbidden()

    data: dict[str, Any] = {}
    for field in flatten_fields(catalog):
        code = field["code"]
        raw = str(form.get(code) or "").strip()
        if raw == "":
            continue

        if field["type"] == "yesno":
            data[code] = 1 if raw == "1" else 0
            continue

        number = _parse_optional_decimal(raw)
        if number is None or number < 0:
            continue
        if field["type"] == "int":
            data[code] = int(number)
        else:
            data[code] = float(number)

    record = _structured_record(
        db,
        school_id=school_id,
        school_year_id=year_id,
        form_code=catalog["form_code"],
    )
    if record is None:
        record = SchoolStructuredReportInput(
            school_id=school_id,
            school_year_id=year_id,
            form_code=catalog["form_code"],
        )
        db.add(record)

    record.data_json = json.dumps(
        data,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    record.notes = _clean(form.get("notes")) or None
    record.updated_by_user_id = int((user or {}).get("id") or 0) or None
    db.commit()

    school = db.get(School, school_id)
    params = {
        "school_year_id": year_id,
        "school_id": school_id,
        "status": "saved",
    }
    if school is not None:
        params["commune_id"] = int(school.commune_id)

    return RedirectResponse(
        url=f"/bieu-nhap/{slug}?" + urlencode(params),
        status_code=303,
    )

# === BAI_13B_6_V1_STRUCTURED_INPUT_END ===

