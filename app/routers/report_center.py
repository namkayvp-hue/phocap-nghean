from __future__ import annotations
from fastapi.responses import RedirectResponse

from datetime import datetime
import re
import unicodedata
from io import BytesIO
from math import ceil
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.page import PageMargins
from sqlalchemy import and_, distinct, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.comparison_models import StudentSurveyComparisonSignoff
from app.database import get_db
from app.models import (
    Commune,
    School,
    SchoolYear,
    StudentEnrollment,
    User,
)
from app.permissions import (
    COMMUNE_ROLE_CODE,
    SCHOOL_ROLE_CODE,
    TEACHER_ROLE_CODE,
    is_province_reader,
    normalize_role_code,
)
from app.routers.surveys import (
    BATCH_STATUS_LABELS,
    lay_thong_tin_nguoi_dung,
    tao_bo_loc_bao_cao_theo_nguoi_dung,
    tao_bo_loc_dot_theo_nguoi_dung,
    tao_bo_loc_phieu_theo_nguoi_dung,
)
from app.survey_models import (
    Household,
    SurveyBatch,
    SurveyForm,
    SurveyFormInvestigator,
    SurveyPerson,
    SurveyPersonYearRecord,
)


APP_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(APP_DIR / "templates"))

router = APIRouter(
    prefix="/bao-cao",
    tags=["Trung tâm báo cáo"],
)

PAGE_SIZE_OPTIONS = (20, 50, 100, 200)

REPORT_TYPES: dict[str, dict[str, Any]] = {
    "TONG_HOP_DIEU_TRA": {
        "title": "Báo cáo tổng hợp điều tra",
        "short_title": "Tổng hợp điều tra",
        "description": (
            "Tổng hợp hộ, phiếu, đối tượng, độ tuổi, giới tính, tình trạng "
            "học tập, khuyết tật và dữ liệu theo trường."
        ),
        "icon": "📊",
        "stage": "Sẵn sàng",
        "stage_class": "ready",
        "lesson": "Bài 13A-2",
    },
    "PCGDMN_MAU_2025": {
        "title": "Bộ biểu mẫu PCGDMN 2025",
        "short_title": "Biểu mẫu PCGDMN 2025",
        "description": (
            "Xuất đúng tệp Excel mẫu gồm MN-01 TE, MN-01 GV, MN-01 CSVC, "
            "MN-02, tài chính, trẻ khuyết tật và sổ theo dõi PCGDMN."
        ),
        "icon": "📑",
        "stage": "Sẵn sàng dữ liệu trẻ và đội ngũ",
        "stage_class": "ready",
        "lesson": "Bài 13B-1",
    },
    "BIEN_DONG_THEO_DOI": {
        "title": "Báo cáo biến động và đối tượng cần theo dõi",
        "short_title": "Biến động – theo dõi",
        "description": (
            "Theo dõi chuyển đến, chuyển đi, chưa đi học, bỏ học, thiếu số "
            "định danh và thiếu dữ liệu năm học."
        ),
        "icon": "🔎",
        "stage": "Sẵn sàng",
        "stage_class": "ready",
        "lesson": "Bài 13A-4",
    },
    "DOI_CHIEU_HOC_SINH": {
        "title": "Báo cáo đối chiếu điều tra với học sinh",
        "short_title": "Đối chiếu học sinh",
        "description": (
            "Phát hiện hồ sơ chưa khớp, sai trường/lớp, sai trạng thái và "
            "theo dõi kết quả xử lý."
        ),
        "icon": "🧩",
        "stage": "Sẵn sàng",
        "stage_class": "ready",
        "lesson": "Bài 12D-15 đến 12D-18",
    },
    "TIEN_DO_CHOT": {
        "title": "Báo cáo tiến độ chốt và đôn đốc",
        "short_title": "Tiến độ – đôn đốc",
        "description": (
            "Giám sát trạng thái chốt, lịch sử mở lại, thời hạn và danh sách "
            "địa bàn cần nhắc việc."
        ),
        "icon": "⏱️",
        "stage": "Sẵn sàng cấp tỉnh",
        "stage_class": "ready",
        "lesson": "Bài 12D-18 và 12D-19",
    },
    # === PCGD_XMC_REPORT_TYPES_V1_5_START ===
    "PCGD_TH_M1_2025": {
        "title": "TH-M1 – Báo cáo phổ cập giáo dục Tiểu học",
        "short_title": "Tiểu học – TH-M1",
        "description": "Tự động tổng hợp từ dữ liệu điều tra 6–14 tuổi vào đúng mẫu Excel TH-M1. Hai chỉ tiêu chưa có trường dữ liệu trực tiếp (Có khả năng HT, Lưu ban) được để trống, không suy diễn.",
        "icon": "📘",
        "stage": "Sẵn sàng tự động",
        "stage_class": "ready",
        "lesson": "Bài 13C-1",
    },
    "PCGD_TH_02_2025": {
        "title": "TH-02 – Thống kê kết quả PCGD Tiểu học",
        "short_title": "Tiểu học – TH-02",
        "description": "Biểu TH-02 năm 2025. Đã tiếp nhận mẫu Excel gốc; chưa thay đổi dữ liệu hoặc luồng nghiệp vụ hiện có.",
        "icon": "📘",
        "stage": "Sẵn sàng V1.1 – xuất đúng mẫu Excel",
        "stage_class": "ready",
        "lesson": "PCGD & XMC V1.5",
    },
    "PCGD_TH_01_GV_2025": {
        "title": "TH-01-GV – Thống kê đội ngũ giáo viên Tiểu học",
        "short_title": "Tiểu học – TH-01-GV",
        "description": "Biểu đội ngũ giáo viên Tiểu học năm 2025. Mẫu gốc được lưu nguyên trạng để triển khai ánh xạ dữ liệu ở bước sau.",
        "icon": "👩‍🏫",
        "stage": "Sẵn sàng V1.1 – xuất đúng mẫu Excel",
        "stage_class": "ready",
        "lesson": "PCGD & XMC V1.5",
    },
    "PCGD_TH_01_CSVC_2025": {
        "title": "TH-01-CSVC – Thống kê cơ sở vật chất Tiểu học",
        "short_title": "Tiểu học – TH-01-CSVC",
        "description": "Biểu cơ sở vật chất Tiểu học năm 2025. Mẫu gốc được lưu nguyên trạng để triển khai tự động điền ở bước sau.",
        "icon": "🏫",
        "stage": "Sẵn sàng V1.1 – xuất đúng mẫu Excel",
        "stage_class": "ready",
        "lesson": "PCGD & XMC V1.5",
    },
    "PCGD_THCS_M1_2025": {
        "title": "THCS-M1 – Báo cáo phổ cập giáo dục THCS",
        "short_title": "THCS – M1",
        "description": "Biểu M1 THCS năm 2025. Đã tiếp nhận mẫu Excel gốc; chưa tự động điền dữ liệu.",
        "icon": "📗",
        "stage": "Sẵn sàng V1.1 – xuất đúng mẫu Excel",
        "stage_class": "ready",
        "lesson": "PCGD & XMC V1.5",
    },
    "PCGD_THCS_M2_2025": {
        "title": "THCS-M2 – Tiêu chuẩn phổ cập giáo dục THCS",
        "short_title": "THCS – M2",
        "description": "Biểu M2 THCS năm 2025 về tiêu chuẩn PCGD THCS. Mẫu gốc được lưu nguyên trạng.",
        "icon": "📗",
        "stage": "Sẵn sàng V1.1 – xuất đúng mẫu Excel",
        "stage_class": "ready",
        "lesson": "PCGD & XMC V1.5",
    },
    "PCGD_THCS_TK_2025": {
        "title": "THCS-TK – Thống kê kết quả PCGD THCS",
        "short_title": "THCS – TK",
        "description": "Biểu thống kê kết quả PCGD THCS năm 2025. Đã tiếp nhận mẫu Excel gốc.",
        "icon": "📗",
        "stage": "Sẵn sàng V1.1 – xuất đúng mẫu Excel",
        "stage_class": "ready",
        "lesson": "PCGD & XMC V1.5",
    },
    "PCGD_THCS_M5_2025": {
        "title": "THCS-M5 – Thống kê đội ngũ giáo viên",
        "short_title": "THCS – M5",
        "description": "Biểu đội ngũ giáo viên THCS năm 2025. Mẫu gốc được lưu nguyên trạng.",
        "icon": "👨‍🏫",
        "stage": "Sẵn sàng V1.1 – xuất đúng mẫu Excel",
        "stage_class": "ready",
        "lesson": "PCGD & XMC V1.5",
    },
    "PCGD_THCS_CSVC_2025": {
        "title": "THCS-CSVC – Thống kê cơ sở vật chất",
        "short_title": "THCS – CSVC",
        "description": "Biểu cơ sở vật chất THCS năm 2025. Mẫu gốc được lưu nguyên trạng.",
        "icon": "🏫",
        "stage": "Sẵn sàng V1.1 – xuất đúng mẫu Excel",
        "stage_class": "ready",
        "lesson": "PCGD & XMC V1.5",
    },
    "PCGD_XMC_3_2025": {
        "title": "XMC-3 – Tổng hợp kết quả xóa mù chữ",
        "short_title": "XMC – Biểu 3",
        "description": "Biểu tổng hợp kết quả xóa mù chữ năm 2025. Đã tiếp nhận mẫu Excel gốc.",
        "icon": "📙",
        "stage": "Sẵn sàng V1.1 – xuất đúng mẫu Excel",
        "stage_class": "ready",
        "lesson": "PCGD & XMC V1.5",
    },
    "PCGD_CMC_2_2025": {
        "title": "CMC-2 – Thống kê số người mù chữ",
        "short_title": "XMC – CMC-2",
        "description": "Biểu thống kê số người mù chữ năm 2025. Đã tiếp nhận mẫu Excel gốc.",
        "icon": "📙",
        "stage": "Sẵn sàng V1.1 – xuất đúng mẫu Excel",
        "stage_class": "ready",
        "lesson": "PCGD & XMC V1.5",
    },
    "PCGD_CMC_1_2025": {
        "title": "CMC-1 – Tổng hợp chống mù chữ",
        "short_title": "XMC – CMC-1",
        "description": "Biểu tổng hợp chống mù chữ năm 2025. Đã tiếp nhận mẫu Excel gốc.",
        "icon": "📙",
        "stage": "Sẵn sàng V1.1 – xuất đúng mẫu Excel",
        "stage_class": "ready",
        "lesson": "PCGD & XMC V1.5",
    },
    "PCGD_XMC_4_2025": {
        "title": "XMC-4 – Thống kê đạt chuẩn xóa mù chữ",
        "short_title": "XMC – Biểu 4",
        "description": "Biểu thống kê đạt chuẩn xóa mù chữ năm 2025. Đã tiếp nhận mẫu Excel gốc.",
        "icon": "📙",
        "stage": "Sẵn sàng V1.1 – xuất đúng mẫu Excel",
        "stage_class": "ready",
        "lesson": "PCGD & XMC V1.5",
    },
    # === PCGD_XMC_REPORT_TYPES_V1_5_END ===

    # === PCGD_MN_REPORT_TYPES_V1_6B_START ===
    "PCGD_MN_M1_2025": {
        "title": "MN-01-TE – Phổ cập giáo dục Mầm non",
        "short_title": "Mầm non – MN-01-TE",
        "description": "Biểu MN-01-TE chính thức. Tự động tổng hợp các chỉ tiêu có nguồn dữ liệu rõ; chỉ tiêu chưa có nguồn để trống.",
        "icon": "🧒",
        "stage": "Sẵn sàng – mẫu chính thức",
        "stage_class": "ready",
        "lesson": "PCGD & XMC V1.6B",
    },
    "PCGD_MN_02_2025": {
        "title": "MN-02 – Kết quả PCGD Mầm non",
        "short_title": "Mầm non – MN-02",
        "description": "Thống kê kết quả PCGDMN cho trẻ em 5 tuổi theo mẫu chính thức.",
        "icon": "📘",
        "stage": "Sẵn sàng – mẫu chính thức",
        "stage_class": "ready",
        "lesson": "PCGD & XMC V1.6B",
    },
    "PCGD_MN_01_GV_2025": {
        "title": "MN-01-GV – Thống kê đội ngũ CBQL, giáo viên, nhân viên",
        "short_title": "Mầm non – MN-01-GV",
        "description": "Đội ngũ cán bộ quản lý, giáo viên, nhân viên từ dữ liệu đội ngũ hiện có.",
        "icon": "👩‍🏫",
        "stage": "Sẵn sàng – mẫu chính thức",
        "stage_class": "ready",
        "lesson": "PCGD & XMC V1.6B",
    },
    "PCGD_MN_01_CSVC_2025": {
        "title": "MN-01-CSVC – Cơ sở vật chất",
        "short_title": "Mầm non – MN-01-CSVC",
        "description": "Mẫu CSVC chính thức. Tự động điền các chỉ tiêu lớp học có nguồn dữ liệu; các chỉ tiêu CSVC chưa có nguồn để trống.",
        "icon": "🏫",
        "stage": "Sẵn sàng – mẫu chính thức",
        "stage_class": "ready",
        "lesson": "PCGD & XMC V1.6B",
    },
    "PCGD_MN_TAICHINH_2025": {
        "title": "MN-TC – Báo cáo tài chính",
        "short_title": "Mầm non – Tài chính",
        "description": "Mẫu tài chính chính thức. Dữ liệu đầu vào được nhập tại Báo cáo → Nhập dữ liệu BC-Tài chính theo xã/phường và năm.",
        "icon": "💰",
        "stage": "Đã có phân hệ nhập dữ liệu",
        "stage_class": "ready",
        "lesson": "Bài 13B-3",
    },
    # === PCGD_MN_REPORT_TYPES_V1_6B_END ===
}

STATUS_LABELS = {
    "": "Tất cả trạng thái",
    "HAS_DATA": "Đã có dữ liệu",
    "NO_DATA": "Chưa có dữ liệu",
    "LOCKED": "Đã khóa số liệu",
    "OPEN": "Dữ liệu đang mở",
    "SIGNED": "Đã chốt đối chiếu",
    "UNSIGNED": "Chưa chốt đối chiếu",
}

SIGNOFF_ACTION_LABELS = {
    "CHOT": "Đã chốt",
    "MO_LAI": "Đã mở lại",
}


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _parse_optional_int(value: Any) -> int | None:
    text = str(value or "").strip()
    return int(text) if text.isdigit() else None


def _load_school_years(db: Session) -> list[SchoolYear]:
    return list(
        db.scalars(
            select(SchoolYear).order_by(
                SchoolYear.code.desc(),
                SchoolYear.id.desc(),
            )
        ).all()
    )


def _choose_year_id(
    school_years: list[SchoolYear],
    requested_id: int | None,
) -> int | None:
    valid_ids = {item.id for item in school_years}
    if requested_id in valid_ids:
        return requested_id
    active = next((item for item in school_years if item.is_active), None)
    if active is not None:
        return active.id
    return school_years[0].id if school_years else None


def _load_scope_options(
    db: Session,
    user: dict[str, Any],
    requested_commune_id: int | None,
    requested_school_id: int | None,
) -> tuple[list[Commune], list[School], int | None, int | None, str]:
    role_code = normalize_role_code(user.get("role_code"))
    account_commune_id = _parse_optional_int(user.get("commune_id"))
    account_school_id = _parse_optional_int(user.get("school_id"))

    if is_province_reader(role_code):
        communes = list(
            db.scalars(
                select(Commune)
                .where(Commune.is_active.is_(True))
                .order_by(Commune.name.asc(), Commune.id.asc())
            ).all()
        )
        valid_commune_ids = {item.id for item in communes}
        selected_commune_id = (
            requested_commune_id
            if requested_commune_id in valid_commune_ids
            else None
        )

        school_statement = (
            select(School)
            .where(School.is_active.is_(True))
            .order_by(School.name.asc(), School.id.asc())
        )
        if selected_commune_id is not None:
            school_statement = school_statement.where(
                School.commune_id == selected_commune_id
            )
        schools = list(db.scalars(school_statement).all())
        valid_school_ids = {item.id for item in schools}
        selected_school_id = (
            requested_school_id
            if requested_school_id in valid_school_ids
            else None
        )

        if selected_school_id is not None:
            school = next(
                item for item in schools if item.id == selected_school_id
            )
            scope_label = f"Trường {school.name}"
        elif selected_commune_id is not None:
            commune = next(
                item for item in communes if item.id == selected_commune_id
            )
            scope_label = commune.name
        else:
            scope_label = "Toàn tỉnh"
        return (
            communes,
            schools,
            selected_commune_id,
            selected_school_id,
            scope_label,
        )

    if role_code == COMMUNE_ROLE_CODE:
        communes = list(
            db.scalars(
                select(Commune)
                .where(
                    Commune.id == account_commune_id,
                    Commune.is_active.is_(True),
                )
            ).all()
        )
        schools = list(
            db.scalars(
                select(School)
                .where(
                    School.commune_id == account_commune_id,
                    School.is_active.is_(True),
                )
                .order_by(School.name.asc(), School.id.asc())
            ).all()
        )
        valid_school_ids = {item.id for item in schools}
        selected_school_id = (
            requested_school_id
            if requested_school_id in valid_school_ids
            else None
        )
        if selected_school_id is not None:
            school = next(
                item for item in schools if item.id == selected_school_id
            )
            scope_label = f"Trường {school.name}"
        else:
            scope_label = communes[0].name if communes else "Cấp xã/phường"
        return (
            communes,
            schools,
            account_commune_id,
            selected_school_id,
            scope_label,
        )

    school = db.get(School, account_school_id) if account_school_id else None
    commune_id = school.commune_id if school is not None else account_commune_id
    commune = db.get(Commune, commune_id) if commune_id else None
    communes = [commune] if commune is not None else []
    schools = [school] if school is not None else []
    scope_label = school.name if school is not None else user.get("unit_name", "Phạm vi tài khoản")
    return (
        communes,
        schools,
        commune_id,
        account_school_id,
        f"Trường {scope_label}" if school is not None else str(scope_label),
    )


def _load_latest_signoffs(
    db: Session,
    batch_ids: list[int],
) -> dict[int, StudentSurveyComparisonSignoff]:
    if not batch_ids:
        return {}
    history = list(
        db.scalars(
            select(StudentSurveyComparisonSignoff)
            .where(StudentSurveyComparisonSignoff.survey_batch_id.in_(batch_ids))
            .order_by(
                StudentSurveyComparisonSignoff.created_at.desc(),
                StudentSurveyComparisonSignoff.id.desc(),
            )
        ).all()
    )
    latest: dict[int, StudentSurveyComparisonSignoff] = {}
    for item in history:
        latest.setdefault(item.survey_batch_id, item)
    return latest


def _form_scope_filters(
    request: Request,
    selected_school_id: int | None,
) -> list[Any]:
    filters = list(tao_bo_loc_bao_cao_theo_nguoi_dung(request))
    user = lay_thong_tin_nguoi_dung(request)
    role_code = normalize_role_code(user.get("role_code"))
    account_school_id = _parse_optional_int(user.get("school_id"))

    # Với tài khoản cấp tỉnh/xã, lựa chọn trường thu hẹp theo hồ sơ năm học
    # hoặc theo phiếu đã được giao cho nhân sự của trường đó.
    if selected_school_id is not None and role_code not in {
        SCHOOL_ROLE_CODE,
        TEACHER_ROLE_CODE,
    }:
        filters.append(
            or_(
                SurveyForm.person_year_records.any(
                    SurveyPersonYearRecord.school_id == selected_school_id
                ),
                SurveyForm.investigators.any(
                    SurveyFormInvestigator.user.has(
                        User.school_id == selected_school_id
                    )
                ),
            )
        )
    elif role_code in {SCHOOL_ROLE_CODE, TEACHER_ROLE_CODE} and account_school_id:
        # tao_bo_loc_bao_cao_theo_nguoi_dung đã áp dụng phạm vi trường.
        pass
    return filters


def _aggregate_batch_counts(
    db: Session,
    request: Request,
    batch_ids: list[int],
    school_year_id: int | None,
    selected_school_id: int | None,
) -> dict[int, dict[str, int]]:
    result = {
        batch_id: {
            "forms": 0,
            "households": 0,
            "people": 0,
            "year_records": 0,
            "reviewed_records": 0,
            "linked_people": 0,
        }
        for batch_id in batch_ids
    }
    if not batch_ids:
        return result

    scope_filters = _form_scope_filters(request, selected_school_id)

    form_rows = db.execute(
        select(
            SurveyForm.survey_batch_id,
            func.count(distinct(SurveyForm.id)).label("forms"),
            func.count(distinct(SurveyForm.household_id)).label("households"),
        )
        .where(
            SurveyForm.survey_batch_id.in_(batch_ids),
            *scope_filters,
        )
        .group_by(SurveyForm.survey_batch_id)
    ).all()
    for batch_id, forms, households in form_rows:
        result[int(batch_id)]["forms"] = int(forms or 0)
        result[int(batch_id)]["households"] = int(households or 0)

    people_rows = db.execute(
        select(
            SurveyForm.survey_batch_id,
            func.count(distinct(SurveyPerson.id)).label("people"),
            func.count(
                distinct(SurveyPerson.id)
            ).filter(
                SurveyPerson.student_id.is_not(None)
            ).label("linked_people"),
        )
        .select_from(SurveyForm)
        .join(Household, Household.id == SurveyForm.household_id)
        .join(SurveyPerson, SurveyPerson.household_id == Household.id)
        .where(
            SurveyForm.survey_batch_id.in_(batch_ids),
            SurveyPerson.is_active.is_(True),
            *scope_filters,
        )
        .group_by(SurveyForm.survey_batch_id)
    ).all()
    for batch_id, people, linked_people in people_rows:
        result[int(batch_id)]["people"] = int(people or 0)
        result[int(batch_id)]["linked_people"] = int(linked_people or 0)

    if school_year_id is not None:
        year_filters: list[Any] = [
            SurveyPersonYearRecord.school_year_id == school_year_id
        ]
        if selected_school_id is not None:
            year_filters.append(
                SurveyPersonYearRecord.school_id == selected_school_id
            )
        year_rows = db.execute(
            select(
                SurveyForm.survey_batch_id,
                func.count(distinct(SurveyPersonYearRecord.id)).label(
                    "year_records"
                ),
                func.count(
                    distinct(SurveyPersonYearRecord.id)
                ).filter(
                    SurveyPersonYearRecord.is_reviewed.is_(True)
                ).label("reviewed_records"),
            )
            .select_from(SurveyForm)
            .join(
                SurveyPersonYearRecord,
                SurveyPersonYearRecord.survey_form_id == SurveyForm.id,
            )
            .where(
                SurveyForm.survey_batch_id.in_(batch_ids),
                *scope_filters,
                *year_filters,
            )
            .group_by(SurveyForm.survey_batch_id)
        ).all()
        for batch_id, year_records, reviewed_records in year_rows:
            result[int(batch_id)]["year_records"] = int(year_records or 0)
            result[int(batch_id)]["reviewed_records"] = int(
                reviewed_records or 0
            )
    return result


def _student_total(
    db: Session,
    school_year_id: int | None,
    selected_commune_id: int | None,
    selected_school_id: int | None,
    user: dict[str, Any],
) -> int:
    if school_year_id is None:
        return 0
    role_code = normalize_role_code(user.get("role_code"))
    account_school_id = _parse_optional_int(user.get("school_id"))
    account_commune_id = _parse_optional_int(user.get("commune_id"))

    statement = (
        select(func.count(distinct(StudentEnrollment.student_id)))
        .select_from(StudentEnrollment)
        .join(School, School.id == StudentEnrollment.school_id)
        .where(StudentEnrollment.school_year_id == school_year_id)
    )
    if selected_school_id is not None:
        statement = statement.where(
            StudentEnrollment.school_id == selected_school_id
        )
    elif role_code in {SCHOOL_ROLE_CODE, TEACHER_ROLE_CODE} and account_school_id:
        statement = statement.where(
            StudentEnrollment.school_id == account_school_id
        )
    elif selected_commune_id is not None:
        statement = statement.where(School.commune_id == selected_commune_id)
    elif role_code == COMMUNE_ROLE_CODE and account_commune_id:
        statement = statement.where(School.commune_id == account_commune_id)
    return int(db.scalar(statement) or 0)


def _report_action(
    report_type: str,
    batch: SurveyBatch,
    latest_signoff: StudentSurveyComparisonSignoff | None,
    province_reader: bool,
) -> dict[str, Any]:
    if report_type == "TONG_HOP_DIEU_TRA":
        report_params = urlencode(
            {
                "school_year_id": batch.school_year_id,
                "commune_id": batch.commune_id,
            }
        )
        return {
            "view_url": (
                "/bao-cao/tong-hop-dieu-tra?"
                + report_params
            ),
            "view_label": "Lập báo cáo tổng hợp",
            "export_url": (
                "/bao-cao/tong-hop-dieu-tra/xuat-excel?"
                + report_params
            ),
            "export_label": (
                "Xuất Excel chính thức"
                if batch.is_locked
                else "Xuất Excel dự thảo"
            ),
            "availability": (
                "Đủ điều kiện xuất chính thức"
                if batch.is_locked
                else "Có thể xem và xuất dự thảo; cần khóa đợt để chính thức"
            ),
            "availability_class": "ready" if batch.is_locked else "draft",
            "secondary_url": f"/dieu-tra/{batch.id}/bao-cao-tong-hop",
            "secondary_label": "Xem báo cáo theo đợt",
        }
    if report_type == "PCGDMN_MAU_2025":
        report_params = urlencode(
            {
                "school_year_id": batch.school_year_id,
                "commune_id": batch.commune_id,
            }
        )
        return {
            "view_url": "/bao-cao/pcgdmn-mau-2025?" + report_params,
            "view_label": "Mở bộ biểu mẫu",
            "export_url": (
                "/bao-cao/pcgdmn-mau-2025/xuat-excel?" + report_params
            ),
            "export_label": "Xuất đúng file Excel mẫu",
            "availability": (
                "Đã điền dữ liệu trẻ; GV, CSVC và tài chính sẽ bổ sung ở các bài tiếp theo"
            ),
            "availability_class": "ready",
            "secondary_url": "/bao-cao/pcgdmn-mau-2025?" + report_params,
            "secondary_label": "Xem mức sẵn sàng 7 biểu",
        }
    if report_type == "BIEN_DONG_THEO_DOI":
        report_params = urlencode(
            {
                "school_year_id": batch.school_year_id,
                "batch_id": batch.id,
            }
        )
        return {
            "view_url": "/bao-cao/bien-dong-theo-doi?" + report_params,
            "view_label": "Mở biến động – theo dõi",
            "export_url": (
                "/bao-cao/bien-dong-theo-doi/xuat-excel?" + report_params
            ),
            "export_label": "Xuất Excel biến động",
            "availability": "Sẵn sàng trong phạm vi tài khoản",
            "availability_class": "ready",
            "secondary_url": f"/dieu-tra/{batch.id}/ho-dan",
            "secondary_label": "Mở danh sách hộ",
        }
    if report_type == "DOI_CHIEU_HOC_SINH":
        signed = latest_signoff is not None and latest_signoff.action_code == "CHOT"
        return {
            "view_url": f"/dieu-tra/{batch.id}/doi-chieu-hoc-sinh",
            "view_label": "Mở đối chiếu",
            "export_url": f"/dieu-tra/{batch.id}/doi-chieu-hoc-sinh/xuat-excel",
            "export_label": "Xuất Excel đối chiếu",
            "availability": (
                "Đã chốt – có biên bản"
                if signed
                else "Đang xử lý hoặc chưa chốt"
            ),
            "availability_class": "ready" if signed else "draft",
            "secondary_url": (
                f"/dieu-tra/{batch.id}/doi-chieu-hoc-sinh/chot-ket-qua"
            ),
            "secondary_label": "Biên bản / chốt",
        }
    if report_type == "TIEN_DO_CHOT":
        if province_reader:
            return {
                "view_url": "/dieu-tra/tong-hop-doi-chieu-hoc-sinh",
                "view_label": "Mở tổng hợp chốt",
                "export_url": "/dieu-tra/don-doc-doi-chieu-hoc-sinh/xuat-excel",
                "export_label": "Xuất danh sách đôn đốc",
                "secondary_url": "/dieu-tra/don-doc-doi-chieu-hoc-sinh",
                "secondary_label": "Mở giám sát đôn đốc",
                "availability": "Sẵn sàng ở phạm vi toàn tỉnh",
                "availability_class": "ready",
            }
        return {
            "view_url": f"/dieu-tra/{batch.id}/doi-chieu-hoc-sinh/chot-ket-qua",
            "view_label": "Xem trạng thái chốt",
            "export_url": None,
            "availability": "Xem trạng thái trong phạm vi tài khoản",
            "availability_class": "draft",
        }
    meta = REPORT_TYPES[report_type]
    return {
        "view_url": None,
        "export_url": None,
        "availability": f"Sẽ triển khai tại {meta['lesson']}",
        "availability_class": "next",
    }


def _build_report_rows(
    db: Session,
    request: Request,
    school_year_id: int | None,
    selected_commune_id: int | None,
    selected_school_id: int | None,
    report_type: str,
    status_filter: str,
    q: str,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    user = lay_thong_tin_nguoi_dung(request)
    role_code = normalize_role_code(user.get("role_code"))
    province_reader = is_province_reader(role_code)

    if school_year_id is None:
        empty_summary = {
            "batches": 0,
            "with_data": 0,
            "locked": 0,
            "signed": 0,
            "forms": 0,
            "households": 0,
            "people": 0,
            "year_records": 0,
            "reviewed_records": 0,
            "linked_people": 0,
            "students": 0,
        }
        return [], empty_summary

    statement = (
        select(SurveyBatch)
        .options(
            selectinload(SurveyBatch.commune),
            selectinload(SurveyBatch.school_year),
        )
        .where(
            SurveyBatch.school_year_id == school_year_id,
            *tao_bo_loc_dot_theo_nguoi_dung(request),
        )
        .order_by(
            SurveyBatch.commune_id.asc(),
            SurveyBatch.created_at.desc(),
            SurveyBatch.id.desc(),
        )
    )
    if selected_commune_id is not None:
        statement = statement.where(
            SurveyBatch.commune_id == selected_commune_id
        )
    if selected_school_id is not None:
        statement = statement.where(
            SurveyBatch.survey_forms.any(
                or_(
                    SurveyForm.person_year_records.any(
                        SurveyPersonYearRecord.school_id == selected_school_id
                    ),
                    SurveyForm.investigators.any(
                        SurveyFormInvestigator.user.has(
                            User.school_id == selected_school_id
                        )
                    ),
                )
            )
        )
    if q:
        q_like = f"%{q}%"
        statement = statement.join(
            Commune,
            Commune.id == SurveyBatch.commune_id,
        ).where(
            or_(
                SurveyBatch.code.ilike(q_like),
                SurveyBatch.name.ilike(q_like),
                Commune.name.ilike(q_like),
                Commune.code.ilike(q_like),
            )
        )

    batches = list(db.scalars(statement).unique().all())
    batch_ids = [item.id for item in batches]
    latest_signoffs = _load_latest_signoffs(db, batch_ids)
    counts = _aggregate_batch_counts(
        db,
        request,
        batch_ids,
        school_year_id,
        selected_school_id,
    )

    rows: list[dict[str, Any]] = []
    for batch in batches:
        count_item = counts.get(batch.id, {})
        latest = latest_signoffs.get(batch.id)
        has_data = int(count_item.get("forms", 0)) > 0
        signed = latest is not None and latest.action_code == "CHOT"

        include = True
        if status_filter == "HAS_DATA":
            include = has_data
        elif status_filter == "NO_DATA":
            include = not has_data
        elif status_filter == "LOCKED":
            include = bool(batch.is_locked)
        elif status_filter == "OPEN":
            include = not bool(batch.is_locked)
        elif status_filter == "SIGNED":
            include = signed
        elif status_filter == "UNSIGNED":
            include = not signed
        if not include:
            continue

        action = _report_action(
            report_type,
            batch,
            latest,
            province_reader,
        )
        rows.append(
            {
                "batch": batch,
                "batch_status_label": BATCH_STATUS_LABELS.get(
                    batch.status,
                    batch.status,
                ),
                "data_status_label": "Đã khóa" if batch.is_locked else "Đang mở",
                "has_data": has_data,
                "signoff_label": (
                    SIGNOFF_ACTION_LABELS.get(
                        latest.action_code,
                        latest.action_code,
                    )
                    if latest is not None
                    else "Chưa có lịch sử chốt"
                ),
                "signoff_class": (
                    "signed"
                    if signed
                    else "reopened"
                    if latest is not None
                    else "unsigned"
                ),
                "signoff_actor": (
                    latest.actor_name_snapshot if latest is not None else ""
                ),
                "signoff_time": (
                    latest.created_at.strftime("%d/%m/%Y %H:%M")
                    if latest is not None
                    else ""
                ),
                "signoff_note": latest.note if latest is not None else "",
                **count_item,
                **action,
            }
        )

    summary = {
        "batches": len(batches),
        "with_data": sum(
            1 for batch in batches if counts.get(batch.id, {}).get("forms", 0)
        ),
        "locked": sum(1 for batch in batches if batch.is_locked),
        "signed": sum(
            1
            for batch in batches
            if latest_signoffs.get(batch.id) is not None
            and latest_signoffs[batch.id].action_code == "CHOT"
        ),
        "forms": sum(item.get("forms", 0) for item in counts.values()),
        "households": sum(
            item.get("households", 0) for item in counts.values()
        ),
        "people": sum(item.get("people", 0) for item in counts.values()),
        "year_records": sum(
            item.get("year_records", 0) for item in counts.values()
        ),
        "reviewed_records": sum(
            item.get("reviewed_records", 0) for item in counts.values()
        ),
        "linked_people": sum(
            item.get("linked_people", 0) for item in counts.values()
        ),
        "students": _student_total(
            db,
            school_year_id,
            selected_commune_id,
            selected_school_id,
            user,
        ),
    }
    return rows, summary


def _build_query_url(
    *,
    school_year_id: int | None,
    report_type: str,
    commune_id: int | None,
    school_id: int | None,
    status_filter: str,
    q: str,
    page_size: int,
    page: int,
) -> str:
    params = urlencode(
        {
            "school_year_id": school_year_id or "",
            "report_type": report_type,
            "commune_id": commune_id or "",
            "school_id": school_id or "",
            "status_filter": status_filter,
            "q": q,
            "page_size": page_size,
            "page": page,
        }
    )
    return "/bao-cao?" + params


def _style_sheet(worksheet: Any) -> None:
    dark_fill = PatternFill("solid", fgColor="1F4E78")
    light_fill = PatternFill("solid", fgColor="D9EAF7")
    white_font = Font(color="FFFFFF", bold=True)
    bold_font = Font(bold=True)
    thin = Side(style="thin", color="C9D4DF")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    for cell in worksheet[1]:
        cell.fill = dark_fill
        cell.font = white_font
        cell.alignment = Alignment(
            horizontal="center",
            vertical="center",
            wrap_text=True,
        )
        cell.border = border
    for row in worksheet.iter_rows(min_row=2):
        for cell in row:
            cell.border = border
            cell.alignment = Alignment(vertical="top", wrap_text=True)
    worksheet.freeze_panes = "A2"
    worksheet.auto_filter.ref = worksheet.dimensions
    for cell in worksheet[2]:
        if cell.value is not None:
            cell.fill = light_fill
            cell.font = bold_font


def _set_widths(worksheet: Any, widths: dict[int, float]) -> None:
    for index, width in widths.items():
        worksheet.column_dimensions[get_column_letter(index)].width = width


# === BAI_13B_12_V2_4_3_4_REPORT_CENTER_REDIRECT ===
_V2434_MN_MASTER_SHEETS = {
    "PCGD_MN_M1_2025": "mn-01-te",
    "PCGD_MN_02_2025": "mn-02",
    "PCGD_MN_01_GV_2025": "mn-01-gv",
    "PCGD_MN_01_CSVC_2025": "mn-01-csvc",
    "PCGD_MN_TAICHINH_2025": "mn-tc",
}


def _v2434_mn_master_redirect(
    report_type: str,
    *,
    school_year_id: str,
    commune_id: str,
    school_id: str,
    is_export: bool,
):
    sheet_code = _V2434_MN_MASTER_SHEETS.get(
        str(report_type or "").strip().upper()
    )
    if not sheet_code:
        return None

    params = []
    if school_year_id not in (None, ""):
        params.append(("school_year_id", str(school_year_id)))
    if commune_id not in (None, ""):
        params.append(("commune_id", str(commune_id)))
    if school_id not in (None, ""):
        params.append(("school_id", str(school_id)))

    if is_export:
        target = (
            "/bao-cao/pcgdmn-mau-2025/xuat-bieu/"
            + sheet_code
        )
    else:
        target = "/bao-cao/pcgdmn-mau-2025"
        params.append(("sheet_code", sheet_code))

    query = urlencode(params)
    return RedirectResponse(
        url=target + (f"?{query}" if query else ""),
        status_code=303,
    )

@router.get("", response_class=HTMLResponse)
def report_center_page(
    request: Request,
    school_year_id: str = "",
    report_type: str = "TONG_HOP_DIEU_TRA",
    commune_id: str = "",
    school_id: str = "",
    status_filter: str = "",
    q: str = "",
    page_size: int = 20,
    page: int = 1,
    db: Session = Depends(get_db),
):
    user = lay_thong_tin_nguoi_dung(request)
    school_years = _load_school_years(db)
    selected_year_id = _choose_year_id(
        school_years,
        _parse_optional_int(school_year_id),
    )
    selected_year = next(
        (item for item in school_years if item.id == selected_year_id),
        None,
    )

    normalized_report_type = _clean_text(report_type).upper()
    if normalized_report_type not in REPORT_TYPES:
        normalized_report_type = "TONG_HOP_DIEU_TRA"
    # === BAI_13B_12_V2_4_3_4_REPORT_CENTER_REDIRECT_PAGE ===
    _v2434_redirect = _v2434_mn_master_redirect(
        normalized_report_type,
        school_year_id=school_year_id,
        commune_id=commune_id,
        school_id=school_id,
        is_export=False,
    )
    if _v2434_redirect is not None:
        return _v2434_redirect
    normalized_status = _clean_text(status_filter).upper()
    if normalized_status not in STATUS_LABELS:
        normalized_status = ""
    q = _clean_text(q)[:120]
    if page_size not in PAGE_SIZE_OPTIONS:
        page_size = 20

    (
        communes,
        schools,
        selected_commune_id,
        selected_school_id,
        scope_label,
    ) = _load_scope_options(
        db,
        user,
        _parse_optional_int(commune_id),
        _parse_optional_int(school_id),
    )

    all_rows, summary = _build_report_rows(
        db,
        request,
        selected_year_id,
        selected_commune_id,
        selected_school_id,
        normalized_report_type,
        normalized_status,
        q,
    )

    total_records = len(all_rows)
    total_pages = max(1, ceil(total_records / page_size))
    page = max(1, min(page, total_pages))
    start = (page - 1) * page_size
    page_rows = all_rows[start:start + page_size]

    page_links = [
        {
            "number": number,
            "url": _build_query_url(
                school_year_id=selected_year_id,
                report_type=normalized_report_type,
                commune_id=selected_commune_id,
                school_id=selected_school_id,
                status_filter=normalized_status,
                q=q,
                page_size=page_size,
                page=number,
            ),
        }
        for number in range(max(1, page - 2), min(total_pages, page + 2) + 1)
    ]

    export_params = urlencode(
        {
            "school_year_id": selected_year_id or "",
            "report_type": normalized_report_type,
            "commune_id": selected_commune_id or "",
            "school_id": selected_school_id or "",
            "status_filter": normalized_status,
            "q": q,
        }
    )

    return templates.TemplateResponse(
        request=request,
        name="reports/report_center.html",
        context={
            "nguoi_dung": user,
            "school_years": school_years,
            "selected_year": selected_year,
            "selected_year_id": selected_year_id,
            "report_types": REPORT_TYPES,
            "selected_report_type": normalized_report_type,
            "selected_report": REPORT_TYPES[normalized_report_type],
            "communes": communes,
            "schools": schools,
            "selected_commune_id": selected_commune_id,
            "selected_school_id": selected_school_id,
            "scope_label": scope_label,
            "status_labels": STATUS_LABELS,
            "status_filter": normalized_status,
            "q": q,
            "summary": summary,
            "rows": page_rows,
            "total_records": total_records,
            "page": page,
            "total_pages": total_pages,
            "page_links": page_links,
            "page_size": page_size,
            "page_size_options": PAGE_SIZE_OPTIONS,
            "previous_url": (
                _build_query_url(
                    school_year_id=selected_year_id,
                    report_type=normalized_report_type,
                    commune_id=selected_commune_id,
                    school_id=selected_school_id,
                    status_filter=normalized_status,
                    q=q,
                    page_size=page_size,
                    page=page - 1,
                )
                if page > 1
                else None
            ),
            "next_url": (
                _build_query_url(
                    school_year_id=selected_year_id,
                    report_type=normalized_report_type,
                    commune_id=selected_commune_id,
                    school_id=selected_school_id,
                    status_filter=normalized_status,
                    q=q,
                    page_size=page_size,
                    page=page + 1,
                )
                if page < total_pages
                else None
            ),
            "export_url": "/bao-cao/xuat-danh-muc-excel?" + export_params,
            "province_reader": is_province_reader(user.get("role_code")),
            "generated_at": datetime.now().strftime("%d/%m/%Y %H:%M"),
        },
    )



# === BAI_13C_1_TH_M1_START ===
TH_M1_TEMPLATE_PATH = (
    APP_DIR
    / "report_templates"
    / "pcgd_xmc_2025"
    / "PCGD_2025_TH_M1.xlsx"
)

_TH_M1_AGE_COLUMNS = {
    6: 6,
    7: 7,
    8: 8,
    9: 9,
    10: 10,
    11: 12,
    12: 13,
    13: 14,
    14: 15,
}

_TH_M1_TOTAL_COLUMNS = {
    "6_10": 11,
    "11_14": 16,
}


def _th_m1_norm(value: Any) -> str:
    text = str(value or "").strip().upper()
    if not text:
        return ""
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return " ".join(text.split())


def _th_m1_reference_year(school_year: SchoolYear | None) -> int:
    if school_year is not None:
        match = re.search(r"(20\d{2})", str(school_year.code or ""))
        if match:
            return int(match.group(1))
    return datetime.now().year


def _th_m1_is_female(person: SurveyPerson) -> bool:
    return _th_m1_norm(person.gender) in {"NU", "F", "FEMALE", "GIRL"}


def _th_m1_is_ethnic_minority(person: SurveyPerson) -> bool:
    ethnic = _th_m1_norm(person.ethnic_group)
    return bool(ethnic) and ethnic not in {"KINH", "K"}


def _th_m1_grade(record: SurveyPersonYearRecord | None) -> int | None:
    if record is None:
        return None
    class_name = ""
    if record.classroom is not None:
        class_name = str(record.classroom.name or "")
    if not class_name:
        class_name = str(record.class_name_reported or "")
    normalized = _th_m1_norm(class_name)
    if not normalized:
        return None
    match = re.search(r"(?<!\d)(1[0-2]|[1-9])(?=[A-Z]|\b|\s|/|\-|$)", normalized)
    if not match:
        return None
    grade = int(match.group(1))
    return grade if 1 <= grade <= 12 else None


def _th_m1_completed_primary(
    person: SurveyPerson,
    record: SurveyPersonYearRecord | None,
) -> bool:
    if record is None:
        return False
    status = _th_m1_norm(record.learning_status)
    if status in {"DA TOT NGHIEP", "DA_TOT_NGHIEP", "HOAN THANH", "HTCTTH"}:
        return True
    grade = _th_m1_grade(record)
    if grade is not None and grade >= 6:
        return True
    combined_notes = _th_m1_norm(
        " ".join(
            [
                str(record.notes or ""),
                str(person.notes or ""),
                str(person.special_circumstances or ""),
            ]
        )
    )
    return (
        "HOAN THANH CHUONG TRINH TIEU HOC" in combined_notes
        or "HTCTTH" in combined_notes
    )


def _th_m1_is_disabled(
    person: SurveyPerson,
    record: SurveyPersonYearRecord | None,
) -> bool:
    if record is not None and str(record.disability_status or "").upper() == "CO_KHUYET_TAT":
        return True
    if person.student is not None and str(person.student.disability_type or "").strip():
        return True
    return False


def _th_m1_disability_accessed_education(
    person: SurveyPerson,
    record: SurveyPersonYearRecord | None,
) -> bool:
    if not _th_m1_is_disabled(person, record) or record is None:
        return False
    status = str(record.learning_status or "").upper()
    return status in {
        "DANG_HOC",
        "CHUYEN_DEN",
        "CHUYEN_DI",
        "DA_TOT_NGHIEP",
    }


def _th_m1_is_ppc(
    person: SurveyPerson,
    record: SurveyPersonYearRecord | None,
) -> bool:
    # Quy tắc an toàn giai đoạn đầu: chỉ đối tượng thường trú được tính
    # vào số phải phổ cập. Không suy diễn thêm các trường dữ liệu chưa có.
    if str(person.residency_status or "").upper() != "THUONG_TRU":
        return False
    if record is not None and str(record.learning_status or "").upper() == "KHONG_THUOC_DIEN":
        return False
    return True


def _th_m1_school_commune_id(
    record: SurveyPersonYearRecord | None,
) -> int | None:
    if record is None or record.school is None:
        return None
    return int(record.school.commune_id) if record.school.commune_id is not None else None


def _th_m1_location_bucket(
    person: SurveyPerson,
    record: SurveyPersonYearRecord | None,
    reporting_commune_id: int | None,
) -> str:
    home_commune_id = (
        int(person.household.commune_id)
        if person.household is not None and person.household.commune_id is not None
        else None
    )
    school_commune_id = _th_m1_school_commune_id(record)

    if reporting_commune_id is None:
        # Ở phạm vi toàn tỉnh, trường có mã trong danh mục tỉnh được xem là
        # tại chỗ; tên trường chỉ ghi tay/không có mã được xem là nơi khác.
        if record is not None and record.school_id is None and str(record.school_name_reported or "").strip():
            return "other"
        return "local"

    if home_commune_id == reporting_commune_id:
        if school_commune_id is None:
            if record is not None and str(record.school_name_reported or "").strip():
                return "other"
            return "local"
        return "local" if school_commune_id == reporting_commune_id else "other"

    if school_commune_id == reporting_commune_id:
        return "inbound"
    return "other"


def _th_m1_empty_age_metric() -> dict[str, Any]:
    return {
        "total": 0,
        "female": 0,
        "ethnic": 0,
        "disabled": 0,
        "disabled_access": 0,
        "ppc": 0,
        "grades": {
            grade: {"local": 0, "other": 0, "inbound": 0}
            for grade in range(1, 6)
        },
        "completed": {"local": 0, "other": 0, "inbound": 0},
        "nonppc_completed": 0,
        "dropout": {"local": 0, "other": 0, "inbound": 0},
        "not_started": 0,
    }


def _th_m1_load_people_and_records(
    *,
    db: Session,
    request: Request,
    school_year_id: int,
    selected_commune_id: int | None,
    selected_school_id: int | None,
) -> list[tuple[SurveyPerson, SurveyPersonYearRecord | None]]:
    form_filters = list(_form_scope_filters(request, selected_school_id))
    statement = (
        select(SurveyForm)
        .where(
            SurveyForm.survey_batch.has(
                SurveyBatch.school_year_id == school_year_id
            ),
            *form_filters,
        )
        .options(
            selectinload(SurveyForm.household)
            .selectinload(Household.people)
            .selectinload(SurveyPerson.student)
        )
    )
    if selected_commune_id is not None:
        statement = statement.where(
            SurveyForm.household.has(
                Household.commune_id == selected_commune_id
            )
        )

    forms = list(db.scalars(statement).unique().all())
    person_map: dict[int, SurveyPerson] = {}
    form_ids: list[int] = []
    for form in forms:
        form_ids.append(int(form.id))
        if form.household is None:
            continue
        for person in form.household.people:
            if bool(person.is_active):
                person_map.setdefault(int(person.id), person)

    if not person_map:
        return []

    record_statement = (
        select(SurveyPersonYearRecord)
        .where(
            SurveyPersonYearRecord.school_year_id == school_year_id,
            SurveyPersonYearRecord.survey_person_id.in_(list(person_map)),
            SurveyPersonYearRecord.survey_form_id.in_(form_ids),
        )
        .options(
            selectinload(SurveyPersonYearRecord.school),
            selectinload(SurveyPersonYearRecord.classroom),
        )
        .order_by(
            SurveyPersonYearRecord.is_reviewed.desc(),
            SurveyPersonYearRecord.updated_at.desc(),
            SurveyPersonYearRecord.id.desc(),
        )
    )
    records = list(db.scalars(record_statement).all())
    latest_record: dict[int, SurveyPersonYearRecord] = {}
    for record in records:
        latest_record.setdefault(int(record.survey_person_id), record)

    return [
        (person, latest_record.get(person_id))
        for person_id, person in person_map.items()
    ]


def _th_m1_build_metrics(
    *,
    people_and_records: list[tuple[SurveyPerson, SurveyPersonYearRecord | None]],
    reference_year: int,
    reporting_commune_id: int | None,
) -> dict[int, dict[str, Any]]:
    metrics = {age: _th_m1_empty_age_metric() for age in range(6, 15)}

    for person, record in people_and_records:
        if person.date_of_birth is None:
            continue
        age = reference_year - int(person.date_of_birth.year)
        if age not in metrics:
            continue

        item = metrics[age]
        item["total"] += 1
        if _th_m1_is_female(person):
            item["female"] += 1
        if _th_m1_is_ethnic_minority(person):
            item["ethnic"] += 1

        if _th_m1_is_disabled(person, record):
            item["disabled"] += 1
            if _th_m1_disability_accessed_education(person, record):
                item["disabled_access"] += 1

        ppc = _th_m1_is_ppc(person, record)
        if ppc:
            item["ppc"] += 1

        bucket = _th_m1_location_bucket(person, record, reporting_commune_id)
        grade = _th_m1_grade(record)
        learning_status = str(record.learning_status or "").upper() if record is not None else ""

        if ppc and grade in {1, 2, 3, 4, 5} and learning_status not in {
            "BO_HOC",
            "THOI_HOC",
            "CHUA_DI_HOC",
            "TAM_NGHI",
        }:
            item["grades"][grade][bucket] += 1

        completed = _th_m1_completed_primary(person, record)
        if completed:
            if ppc:
                item["completed"][bucket] += 1
            else:
                item["nonppc_completed"] += 1

        if ppc and learning_status in {"BO_HOC", "THOI_HOC"}:
            item["dropout"][bucket] += 1

        if ppc and learning_status == "CHUA_DI_HOC":
            item["not_started"] += 1

    return metrics


def _th_m1_scope_title(
    scope_label: str,
    selected_commune_id: int | None,
) -> str:
    text = str(scope_label or "").strip()
    if selected_commune_id is not None:
        return text
    if text.lower().startswith("trường "):
        return text
    return "Toàn tỉnh" if text == "Toàn tỉnh" else text


def _th_m1_write_age_row(
    ws: Any,
    row_number: int,
    metrics: dict[int, dict[str, Any]],
    value_getter: Any,
    *,
    blank_zero: bool = True,
) -> None:
    values_6_10: list[int] = []
    values_11_14: list[int] = []
    for age, column in _TH_M1_AGE_COLUMNS.items():
        value = int(value_getter(metrics[age]) or 0)
        ws.cell(row_number, column).value = None if blank_zero and value == 0 else value
        if age <= 10:
            values_6_10.append(value)
        else:
            values_11_14.append(value)
    ws.cell(row_number, _TH_M1_TOTAL_COLUMNS["6_10"]).value = sum(values_6_10)
    ws.cell(row_number, _TH_M1_TOTAL_COLUMNS["11_14"]).value = sum(values_11_14)


def _th_m1_percent(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round((numerator * 100.0) / denominator, 2)


# === BAI_13B_11_15_2_4_5_PRIMARY_OFFICIAL_PERCENTAGES ===
def _b15245_cell_number(ws: Any, ref: str) -> float | None:
    value = ws[ref].value
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _b15245_sum_cells(ws: Any, refs: tuple[str, ...]) -> float | None:
    values = [_b15245_cell_number(ws, ref) for ref in refs]
    if all(value is None for value in values):
        return None
    return sum(value or 0.0 for value in values)


def _b15245_apply_primary_th_m1_percentages(ws: Any) -> None:
    # Tính đúng công thức mẫu; thiếu nguồn thì để trống.
    from app.services.pcgd_business_rules import safe_percent

    mappings = (
        ("G40", "F40", ("F12",)),
        ("G41", "F41", ("L12",)),
        ("G42", "F42", ("L12",)),
        ("G43", "F43", ("P12",)),
        ("G44", "F44", ("K10", "P10")),
    )
    for result_ref, numerator_ref, denominator_refs in mappings:
        numerator = _b15245_cell_number(ws, numerator_ref)
        denominator = _b15245_sum_cells(ws, denominator_refs)
        ws[result_ref] = safe_percent(numerator, denominator)
# === END BAI_13B_11_15_2_4_5_PRIMARY_OFFICIAL_PERCENTAGES ===



# === BAI_13B_11_15_2_4_5_2_V2_TH_M1_SHARED_LOADER_START ===
def _b152452v2_th_m1_can_learn(
    person,
    record,
) -> bool:
    if (
        not _th_m1_is_disabled(
            person,
            record,
        )
        or record is None
    ):
        return False

    explicit = getattr(
        record,
        "disability_can_learn",
        None,
    )

    if explicit is True:
        return True

    if explicit is False:
        return False

    return (
        getattr(
            record,
            "disability_access_education",
            None,
        )
        is True
    )


def _b152452v2_th_m1_access(
    person,
    record,
) -> bool:
    return bool(
        _b152452v2_th_m1_can_learn(
            person,
            record,
        )
        and record is not None
        and getattr(
            record,
            "disability_access_education",
            None,
        )
        is True
    )


def _b152452v2_birth_year(
    person,
) -> int | None:
    value = getattr(
        person,
        "date_of_birth",
        None,
    )

    year = getattr(
        value,
        "year",
        None,
    )

    if year is not None:
        try:
            return int(year)
        except (TypeError, ValueError):
            return None

    text = str(
        value or ""
    ).strip()

    if len(text) >= 4:
        try:
            return int(
                text[:4]
            )
        except ValueError:
            return None

    return None


def _b152452v2_apply_th_m1_disability(
    *,
    ws,
    db,
    request,
    school_year_id: int,
    selected_commune_id: int | None,
    selected_school_id: int | None,
    reference_year: int,
) -> None:
    """
    TH_M1 dùng cùng bộ nạp đối tượng/phạm vi với
    pcgd_xmc_report_builders_v1.py, không phụ thuộc
    biến cục bộ bên trong _th_m1_build_metrics.
    """
    from app.pcgd_xmc_report_builders_v1 import (
        _load_people_and_records,
    )

    people = _load_people_and_records(
        db=db,
        request=request,
        school_year_id=int(
            school_year_id
        ),
        selected_commune_id=selected_commune_id,
        selected_school_id=selected_school_id,
    )

    age_columns = {
        6: "F",
        7: "G",
        8: "H",
        9: "I",
        10: "J",
        11: "L",
        12: "M",
        13: "N",
        14: "O",
    }

    capable_by_age = {
        age: 0
        for age in age_columns
    }

    access_by_age = {
        age: 0
        for age in age_columns
    }

    for person, record in people:
        birth_year = _b152452v2_birth_year(
            person
        )

        if birth_year is None:
            continue

        age = (
            int(reference_year)
            - int(birth_year)
        )

        if age not in age_columns:
            continue

        if _b152452v2_th_m1_can_learn(
            person,
            record,
        ):
            capable_by_age[age] += 1

            if _b152452v2_th_m1_access(
                person,
                record,
            ):
                access_by_age[age] += 1

    for age, column in age_columns.items():
        capable = capable_by_age[age]
        access = access_by_age[age]

        ws[f"{column}10"] = (
            capable
            if capable > 0
            else None
        )

        ws[f"{column}11"] = (
            access
            if capable > 0
            else None
        )

    capable_6_10 = sum(
        capable_by_age[age]
        for age in range(
            6,
            11,
        )
    )

    access_6_10 = sum(
        access_by_age[age]
        for age in range(
            6,
            11,
        )
    )

    capable_11_14 = sum(
        capable_by_age[age]
        for age in range(
            11,
            15,
        )
    )

    access_11_14 = sum(
        access_by_age[age]
        for age in range(
            11,
            15,
        )
    )

    ws["K10"] = (
        capable_6_10
        if capable_6_10 > 0
        else None
    )

    ws["K11"] = (
        access_6_10
        if capable_6_10 > 0
        else None
    )

    ws["P10"] = (
        capable_11_14
        if capable_11_14 > 0
        else None
    )

    ws["P11"] = (
        access_11_14
        if capable_11_14 > 0
        else None
    )

    capable_total = (
        capable_6_10
        + capable_11_14
    )

    access_total = (
        access_6_10
        + access_11_14
    )

    # F44 là tử số của công thức mẫu:
    # G44 = F44 / (K10 + P10) * 100.
    #
    # Nếu có mẫu số nhưng không ai tiếp cận -> F44=0,
    # để tỷ lệ ra đúng 0%.
    ws["F44"] = (
        access_total
        if capable_total > 0
        else None
    )
# === BAI_13B_11_15_2_4_5_2_V2_TH_M1_SHARED_LOADER_END ===


def _build_primary_th_m1_workbook(
    *,
    db: Session,
    request: Request,
    school_year: SchoolYear | None,
    selected_commune_id: int | None,
    selected_school_id: int | None,
    scope_label: str,
) -> tuple[Any, str]:
    if school_year is None:
        raise ValueError("Chưa xác định được năm học để lập biểu TH-M1.")
    if not TH_M1_TEMPLATE_PATH.exists():
        raise FileNotFoundError(f"Không tìm thấy mẫu TH-M1: {TH_M1_TEMPLATE_PATH}")

    reference_year = _th_m1_reference_year(school_year)
    people_and_records = _th_m1_load_people_and_records(
        db=db,
        request=request,
        school_year_id=int(school_year.id),
        selected_commune_id=selected_commune_id,
        selected_school_id=selected_school_id,
    )
    metrics = _th_m1_build_metrics(
        people_and_records=people_and_records,
        reference_year=reference_year,
        reporting_commune_id=selected_commune_id,
    )

    workbook = load_workbook(TH_M1_TEMPLATE_PATH)
    ws = workbook[workbook.sheetnames[0]]

# === BAI_13C_1_TH_M1_V2_TOAN_TINH ===
    # Chỉ thay nội dung dữ liệu; giữ nguyên merge, font, border, kích thước
    # dòng/cột, vùng in và bố cục mẫu gốc. Khi phạm vi là toàn tỉnh,
    # biểu được nhận diện rõ là biểu cấp tỉnh; khi chọn xã/phường, mẫu xã
    # vẫn giữ nguyên để không làm mất chức năng cũ.
    is_province_scope = selected_commune_id is None and selected_school_id is None
    is_school_scope = selected_school_id is not None
    scope_title = (
        "Toàn tỉnh"
        if is_province_scope
        else _th_m1_scope_title(scope_label, selected_commune_id)
    )

    if is_school_scope and scope_title.lower().startswith("trường trường "):
        scope_title = scope_title[len("Trường "):]

    if is_province_scope and ws.title != "Toàn tỉnh":
        ws.title = "Toàn tỉnh"

    ws["A1"] = "Tỉnh: Nghệ An"
    ws["A2"] = scope_title
    ws["E2"] = f"Thời điểm: ngày 30 tháng 9 năm {reference_year}"

    if is_province_scope:
        ws["J44"] = f"Nghệ An, ngày      tháng      năm {reference_year}"
        ws["J45"] = "XÁC NHẬN CỦA SỞ GIÁO DỤC VÀ ĐÀO TẠO"
        ws["J46"] = "GIÁM ĐỐC"
    elif is_school_scope:
        ws["J44"] = f"{scope_title}, ngày      tháng      năm {reference_year}"
        ws["J45"] = "XÁC NHẬN CỦA NHÀ TRƯỜNG"
        ws["J46"] = "HIỆU TRƯỞNG"
    else:
        ws["J44"] = f"{scope_title}, ngày      tháng      năm {reference_year}"
        ws["J45"] = "XÁC NHẬN CỦA UBND XÃ/PHƯỜNG"
        ws["J46"] = "PHÓ CHỦ TỊCH"

    birth_years = {
        6: reference_year - 6,
        7: reference_year - 7,
        8: reference_year - 8,
        9: reference_year - 9,
        10: reference_year - 10,
        11: reference_year - 11,
        12: reference_year - 12,
        13: reference_year - 13,
        14: reference_year - 14,
    }
    for age, column in _TH_M1_AGE_COLUMNS.items():
        ws.cell(4, column).value = birth_years[age]

    # Xóa toàn bộ số liệu ví dụ của địa phương mẫu trước khi điền dữ liệu thật.
    for row_number in range(6, 39):
        for column in range(6, 17):
            ws.cell(row_number, column).value = None
    for row_number in range(40, 45):
        ws.cell(row_number, 6).value = None
        ws.cell(row_number, 7).value = None

    _th_m1_write_age_row(ws, 6, metrics, lambda item: item["total"])
    _th_m1_write_age_row(ws, 7, metrics, lambda item: item["female"])
    _th_m1_write_age_row(ws, 8, metrics, lambda item: item["ethnic"])
    _th_m1_write_age_row(ws, 9, metrics, lambda item: item["disabled"])

    # Dòng 10 "Có khả năng HT": hệ thống hiện chưa có trường dữ liệu trực tiếp.
    # Cố ý để trống, không suy diễn và không sửa cơ sở dữ liệu.
    _th_m1_write_age_row(ws, 11, metrics, lambda item: item["disabled_access"])
    _th_m1_write_age_row(ws, 12, metrics, lambda item: item["ppc"])

    grade_row_starts = {1: 13, 2: 16, 3: 19, 4: 22, 5: 25}
    bucket_offsets = {"local": 0, "other": 1, "inbound": 2}
    for grade, start_row in grade_row_starts.items():
        for bucket, offset in bucket_offsets.items():
            _th_m1_write_age_row(
                ws,
                start_row + offset,
                metrics,
                lambda item, grade=grade, bucket=bucket: item["grades"][grade][bucket],
            )

    for bucket, offset in bucket_offsets.items():
        _th_m1_write_age_row(
            ws,
            28 + offset,
            metrics,
            lambda item, bucket=bucket: item["completed"][bucket],
        )
    _th_m1_write_age_row(ws, 31, metrics, lambda item: item["nonppc_completed"])

    # Dòng 32-34 "Lưu ban": chưa có trường dữ liệu trực tiếp nên để trống.
    for bucket, offset in bucket_offsets.items():
        _th_m1_write_age_row(
            ws,
            35 + offset,
            metrics,
            lambda item, bucket=bucket: item["dropout"][bucket],
        )
    _th_m1_write_age_row(ws, 38, metrics, lambda item: item["not_started"])

    age6 = metrics[6]
    age11 = metrics[11]
    primary_age11 = sum(
        age11["grades"][grade][bucket]
        for grade in range(1, 6)
        for bucket in ("local", "other")
    )
    grade1_age6 = sum(age6["grades"][1][bucket] for bucket in ("local", "other"))
    completed_age11 = sum(age11["completed"][bucket] for bucket in ("local", "other"))
    completed_11_14 = sum(
        metrics[age]["completed"][bucket]
        for age in range(11, 15)
        for bucket in ("local", "other")
    )
    ppc_11_14 = sum(metrics[age]["ppc"] for age in range(11, 15))

    ws["F40"] = grade1_age6
    ws["G40"] = _th_m1_percent(grade1_age6, age6["ppc"])
    ws["F41"] = completed_age11
    ws["G41"] = _th_m1_percent(completed_age11, age11["ppc"])
    ws["F42"] = primary_age11
    ws["G42"] = _th_m1_percent(primary_age11, age11["ppc"])
    ws["F43"] = completed_11_14
    ws["G43"] = _th_m1_percent(completed_11_14, ppc_11_14)
    ws["F44"] = None
    ws["G44"] = None

    _b152452v2_apply_th_m1_disability(
        ws=ws,
        db=db,
        request=request,
        school_year_id=int(school_year.id),
        selected_commune_id=selected_commune_id,
        selected_school_id=selected_school_id,
        reference_year=reference_year,
    )
    _b15245_apply_primary_th_m1_percentages(ws)

    # BATCH22B_TH_M1_FINAL_PERCENT_FORMAT
    # Giá trị G40:G44 đang là 0..100; chỉ thêm ký hiệu % literal.
    # Ví dụ 100.0 -> hiển thị 100,00%, không biến thành 10000%.
    for _percent_ref in ("G40", "G41", "G42", "G43", "G44"):
        ws[_percent_ref].number_format = r'0\%'

    # Không giữ tên người lập/ký của tệp địa phương mẫu.
    for cell_ref in ("D52", "J52"):
        ws[cell_ref] = None

    output = BytesIO()
    workbook.save(output)
    output.seek(0)

    safe_scope = _th_m1_norm(scope_title).replace(" ", "_") or "TOAN_TINH"
    year_code = str(school_year.code or reference_year).replace("/", "-")
    filename = f"PCGD_TH_M1_{year_code}_{safe_scope}.xlsx"
    return output, filename

def _export_primary_th_m1(
    *,
    db: Session,
    request: Request,
    school_year: SchoolYear | None,
    selected_commune_id: int | None,
    selected_school_id: int | None,
    scope_label: str,
) -> StreamingResponse:
    output, filename = _build_primary_th_m1_workbook(
        db=db,
        request=request,
        school_year=school_year,
        selected_commune_id=selected_commune_id,
        selected_school_id=selected_school_id,
        scope_label=scope_label,
    )
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
# === BAI_13C_1_TH_M1_END ===


@router.get("/xuat-danh-muc-excel")
def export_report_catalog_excel(
    request: Request,
    school_year_id: str = "",
    report_type: str = "TONG_HOP_DIEU_TRA",
    commune_id: str = "",
    school_id: str = "",
    status_filter: str = "",
    q: str = "",
    db: Session = Depends(get_db),
):
    user = lay_thong_tin_nguoi_dung(request)
    school_years = _load_school_years(db)
    selected_year_id = _choose_year_id(
        school_years,
        _parse_optional_int(school_year_id),
    )
    selected_year = next(
        (item for item in school_years if item.id == selected_year_id),
        None,
    )
    normalized_report_type = _clean_text(report_type).upper()
    if normalized_report_type not in REPORT_TYPES:
        normalized_report_type = "TONG_HOP_DIEU_TRA"
    # === BAI_13B_12_V2_4_3_4_REPORT_CENTER_REDIRECT_EXPORT ===
    _v2434_redirect = _v2434_mn_master_redirect(
        normalized_report_type,
        school_year_id=school_year_id,
        commune_id=commune_id,
        school_id=school_id,
        is_export=True,
    )
    if _v2434_redirect is not None:
        return _v2434_redirect
    normalized_status = _clean_text(status_filter).upper()
    if normalized_status not in STATUS_LABELS:
        normalized_status = ""
    q = _clean_text(q)[:120]

    (
        _communes,
        _schools,
        selected_commune_id,
        selected_school_id,
        scope_label,
    ) = _load_scope_options(
        db,
        user,
        _parse_optional_int(commune_id),
        _parse_optional_int(school_id),
    )
    if normalized_report_type == "PCGD_TH_M1_2025":
        return _export_primary_th_m1(
            db=db,
            request=request,
            school_year=selected_year,
            selected_commune_id=selected_commune_id,
            selected_school_id=selected_school_id,
            scope_label=scope_label,
        )

    # === PCGD_XMC_MULTI_REPORT_V1_START ===
    # 12 bieu moi dung lai route xuat Excel hien co. Neu dung ma bao cao moi,
    # tra ve CHINH mau Excel goc; neu khong thi luong xuat danh muc cu tiep tuc nhu truoc.
    from app.pcgd_xmc_report_builders_v1 import (
        SUPPORTED_REPORT_TYPES as PCGD_XMC_SUPPORTED_REPORT_TYPES,
        export_additional_report as export_pcgd_xmc_additional_report,
    )
    if normalized_report_type in PCGD_XMC_SUPPORTED_REPORT_TYPES:
        return export_pcgd_xmc_additional_report(
            report_type=normalized_report_type,
            db=db,
            request=request,
            school_year=selected_year,
            selected_commune_id=selected_commune_id,
            selected_school_id=selected_school_id,
            scope_label=scope_label,
        )
    # === PCGD_XMC_MULTI_REPORT_V1_END ===

    # === PCGD_MN_EXPORT_V1_6B_START ===
    from app.pcgd_mn_report_builders_v1 import (
        SUPPORTED_REPORT_TYPES as PCGD_MN_SUPPORTED_REPORT_TYPES,
        export_mn_report,
    )
    if normalized_report_type in PCGD_MN_SUPPORTED_REPORT_TYPES:
        return export_mn_report(
            report_type=normalized_report_type,
            db=db,
            request=request,
            school_year=selected_year,
            selected_commune_id=selected_commune_id,
            selected_school_id=selected_school_id,
            scope_label=scope_label,
        )
    # === PCGD_MN_EXPORT_V1_6B_END ===

    rows, summary = _build_report_rows(
        db,
        request,
        selected_year_id,
        selected_commune_id,
        selected_school_id,
        normalized_report_type,
        normalized_status,
        q,
    )

    workbook = Workbook()
    catalog = workbook.active
    catalog.title = "Danh muc bao cao"
    catalog.append(
        [
            "STT",
            "Mã đợt",
            "Tên đợt",
            "Năm học",
            "Xã/phường",
            "Trạng thái đợt",
            "Trạng thái dữ liệu",
            "Phiếu",
            "Hộ",
            "Đối tượng",
            "Hồ sơ năm học",
            "Đã rà soát",
            "Đã liên kết học sinh",
            "Trạng thái chốt đối chiếu",
            "Người thao tác gần nhất",
            "Thời điểm gần nhất",
            "Căn cứ/lý do",
            "Mức sẵn sàng báo cáo",
        ]
    )
    for index, row in enumerate(rows, start=1):
        batch = row["batch"]
        catalog.append(
            [
                index,
                batch.code,
                batch.name,
                batch.school_year.code,
                batch.commune.name,
                row["batch_status_label"],
                row["data_status_label"],
                row.get("forms", 0),
                row.get("households", 0),
                row.get("people", 0),
                row.get("year_records", 0),
                row.get("reviewed_records", 0),
                row.get("linked_people", 0),
                row["signoff_label"],
                row["signoff_actor"],
                row["signoff_time"],
                row["signoff_note"],
                row["availability"],
            ]
        )
    _style_sheet(catalog)
    _set_widths(
        catalog,
        {
            1: 8,
            2: 24,
            3: 42,
            4: 14,
            5: 25,
            6: 18,
            7: 18,
            8: 10,
            9: 10,
            10: 12,
            11: 16,
            12: 14,
            13: 18,
            14: 24,
            15: 24,
            16: 20,
            17: 42,
            18: 42,
        },
    )

    overview = workbook.create_sheet("Tong hop pham vi")
    overview.append(["Chỉ tiêu", "Giá trị"])
    overview_rows = [
        ("Loại báo cáo", REPORT_TYPES[normalized_report_type]["title"]),
        ("Năm học", selected_year.code if selected_year else "Chưa xác định"),
        ("Phạm vi", scope_label),
        ("Số đợt trong phạm vi", summary["batches"]),
        ("Đợt đã có dữ liệu", summary["with_data"]),
        ("Đợt đã khóa số liệu", summary["locked"]),
        ("Đợt đã chốt đối chiếu", summary["signed"]),
        ("Tổng phiếu", summary["forms"]),
        ("Tổng hộ", summary["households"]),
        ("Tổng đối tượng", summary["people"]),
        ("Hồ sơ năm học", summary["year_records"]),
        ("Hồ sơ đã rà soát", summary["reviewed_records"]),
        ("Đối tượng đã liên kết học sinh", summary["linked_people"]),
        ("Học sinh theo năm học", summary["students"]),
    ]
    for item in overview_rows:
        overview.append(list(item))
    _style_sheet(overview)
    _set_widths(overview, {1: 38, 2: 50})

    info = workbook.create_sheet("Thong tin bo loc")
    info.append(["Thông tin", "Giá trị"])
    info_rows = [
        ("Thời điểm lập", datetime.now().strftime("%d/%m/%Y %H:%M")),
        ("Người lập", user.get("full_name", "")),
        ("Vai trò", user.get("role_name", "")),
        ("Đơn vị", user.get("unit_name", "")),
        ("Năm học", selected_year.code if selected_year else ""),
        ("Loại báo cáo", REPORT_TYPES[normalized_report_type]["title"]),
        ("Phạm vi", scope_label),
        ("Trạng thái lọc", STATUS_LABELS[normalized_status]),
        ("Từ khóa", q or "Không"),
        (
            "Ghi chú",
            "Tệp này là danh mục và ảnh chụp mức sẵn sàng báo cáo; "
            "không tự sửa dữ liệu gốc.",
        ),
    ]
    for item in info_rows:
        info.append(list(item))
    _style_sheet(info)
    _set_widths(info, {1: 30, 2: 70})

    output = BytesIO()
    workbook.save(output)
    output.seek(0)
    year_code = selected_year.code if selected_year else "khong_nam_hoc"
    filename = f"trung_tam_bao_cao_{year_code}_{normalized_report_type.lower()}.xlsx"
    return StreamingResponse(
        output,
        media_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        },
    )


# =========================================================
# BÀI 13A-4 - BIẾN ĐỘNG VÀ ĐỐI TƯỢNG CẦN THEO DÕI
# =========================================================

MOVEMENT_GROUP_LABELS: dict[str, str] = {
    "": "Tất cả nhóm cần theo dõi",
    "CHUYEN_DEN": "Chuyển đến",
    "CHUYEN_DI": "Chuyển đi",
    "CHUA_DI_HOC": "Chưa đi học",
    "BO_HOC": "Bỏ học",
    "THOI_HOC": "Thôi học",
    "TAM_NGHI": "Tạm nghỉ",
    "THIEU_SO_DINH_DANH": "Thiếu số định danh",
    "THIEU_DU_LIEU_NAM_HOC": "Thiếu dữ liệu năm học",
}

_MOVEMENT_LEARNING_LABELS = {
    "DANG_HOC": "Đang học",
    "CHUA_DI_HOC": "Chưa đi học",
    "CHUYEN_DEN": "Chuyển đến",
    "CHUYEN_DI": "Chuyển đi",
    "TAM_NGHI": "Tạm nghỉ",
    "THOI_HOC": "Thôi học",
    "BO_HOC": "Bỏ học",
    "DA_TOT_NGHIEP": "Đã tốt nghiệp",
    "KHONG_THUOC_DIEN": "Không thuộc diện theo dõi",
    "CHUA_XAC_DINH": "Chưa xác định",
}

_MOVEMENT_RESIDENCY_LABELS = {
    "THUONG_TRU": "Thường trú",
    "TAM_TRU": "Tạm trú",
    "TAM_VANG": "Tạm vắng",
    "CHUYEN_DEN": "Chuyển đến",
    "CHUYEN_DI": "Chuyển đi",
    "CHUA_XAC_DINH": "Chưa xác định",
}


def _movement_categories(
    person: SurveyPerson,
    record: SurveyPersonYearRecord | None,
) -> list[str]:
    categories: list[str] = []
    learning = str(record.learning_status or "").upper() if record else ""
    residency = str(person.residency_status or "").upper()

    # Trạng thái năm học được ưu tiên; trạng thái cư trú là nguồn bổ sung.
    if learning == "CHUYEN_DEN" or (not learning and residency == "CHUYEN_DEN"):
        categories.append("CHUYEN_DEN")
    elif learning == "CHUYEN_DI" or (not learning and residency == "CHUYEN_DI"):
        categories.append("CHUYEN_DI")
    elif learning in {"CHUA_DI_HOC", "BO_HOC", "THOI_HOC", "TAM_NGHI"}:
        categories.append(learning)

    if not str(person.personal_id or "").strip():
        categories.append("THIEU_SO_DINH_DANH")
    if record is None or not bool(record.is_reviewed):
        categories.append("THIEU_DU_LIEU_NAM_HOC")
    return categories


def _movement_primary_group(categories: list[str]) -> str:
    priority = (
        "CHUYEN_DEN",
        "CHUYEN_DI",
        "BO_HOC",
        "THOI_HOC",
        "CHUA_DI_HOC",
        "TAM_NGHI",
        "THIEU_DU_LIEU_NAM_HOC",
        "THIEU_SO_DINH_DANH",
    )
    return next((item for item in priority if item in categories), "")


def _movement_school_name(record: SurveyPersonYearRecord | None) -> str:
    if record is None:
        return ""
    if record.school is not None:
        return str(record.school.name or "").strip()
    return str(record.school_name_reported or "").strip()


def _build_movement_rows(
    *,
    db: Session,
    request: Request,
    school_year_id: int | None,
    selected_commune_id: int | None,
    selected_school_id: int | None,
    selected_batch_id: int | None,
    group: str,
    q: str,
) -> tuple[list[dict[str, Any]], dict[str, int], list[SurveyBatch]]:
    if school_year_id is None:
        return [], {code: 0 for code in [
            "total", "CHUYEN_DEN", "CHUYEN_DI", "CHUA_DI_HOC",
            "BO_HOC", "THOI_HOC", "TAM_NGHI", "THIEU_SO_DINH_DANH",
            "THIEU_DU_LIEU_NAM_HOC",
        ]}, []

    batch_statement = (
        select(SurveyBatch)
        .options(
            selectinload(SurveyBatch.commune),
            selectinload(SurveyBatch.school_year),
        )
        .where(
            SurveyBatch.school_year_id == school_year_id,
            *tao_bo_loc_dot_theo_nguoi_dung(request),
        )
        .order_by(SurveyBatch.commune_id.asc(), SurveyBatch.id.asc())
    )
    if selected_commune_id is not None:
        batch_statement = batch_statement.where(
            SurveyBatch.commune_id == selected_commune_id
        )
    if selected_batch_id is not None:
        batch_statement = batch_statement.where(SurveyBatch.id == selected_batch_id)
    batches = list(db.scalars(batch_statement).unique().all())
    if not batches:
        return [], {code: 0 for code in [
            "total", "CHUYEN_DEN", "CHUYEN_DI", "CHUA_DI_HOC",
            "BO_HOC", "THOI_HOC", "TAM_NGHI", "THIEU_SO_DINH_DANH",
            "THIEU_DU_LIEU_NAM_HOC",
        ]}, []

    batch_map = {item.id: item for item in batches}
    role_code = normalize_role_code(lay_thong_tin_nguoi_dung(request).get("role_code"))
    form_filters = list(tao_bo_loc_phieu_theo_nguoi_dung(request))
    if selected_school_id is not None and role_code not in {
        SCHOOL_ROLE_CODE,
        TEACHER_ROLE_CODE,
    }:
        form_filters.append(
            or_(
                SurveyPersonYearRecord.school_id == selected_school_id,
                SurveyForm.investigators.any(
                    SurveyFormInvestigator.user.has(
                        User.school_id == selected_school_id
                    )
                ),
            )
        )

    statement = (
        select(SurveyForm, Household, SurveyPerson, SurveyPersonYearRecord)
        .join(Household, Household.id == SurveyForm.household_id)
        .join(SurveyPerson, SurveyPerson.household_id == Household.id)
        .outerjoin(
            SurveyPersonYearRecord,
            and_(
                SurveyPersonYearRecord.survey_form_id == SurveyForm.id,
                SurveyPersonYearRecord.survey_person_id == SurveyPerson.id,
                SurveyPersonYearRecord.school_year_id == school_year_id,
            ),
        )
        .options(
            selectinload(SurveyPersonYearRecord.school),
            selectinload(SurveyPersonYearRecord.classroom),
        )
        .where(
            SurveyForm.survey_batch_id.in_(list(batch_map)),
            SurveyPerson.is_active.is_(True),
            *form_filters,
        )
        .order_by(
            SurveyForm.survey_batch_id.asc(),
            Household.hamlet_name.asc(),
            Household.head_name.asc(),
            SurveyPerson.full_name.asc(),
            SurveyPerson.id.asc(),
        )
    )
    if q:
        like = f"%{q}%"
        statement = statement.where(
            or_(
                SurveyPerson.code.ilike(like),
                SurveyPerson.full_name.ilike(like),
                SurveyPerson.personal_id.ilike(like),
                Household.code.ilike(like),
                Household.head_name.ilike(like),
                SurveyForm.form_number.ilike(like),
            )
        )

    raw_rows = db.execute(statement).all()
    rows: list[dict[str, Any]] = []
    summary = {code: 0 for code in [
        "total", "CHUYEN_DEN", "CHUYEN_DI", "CHUA_DI_HOC",
        "BO_HOC", "THOI_HOC", "TAM_NGHI", "THIEU_SO_DINH_DANH",
        "THIEU_DU_LIEU_NAM_HOC",
    ]}
    for survey_form, household, person, record in raw_rows:
        categories = _movement_categories(person, record)
        if not categories:
            continue
        for category in set(categories):
            if category in summary:
                summary[category] += 1
        summary["total"] += 1
        if group and group not in categories:
            continue
        batch = batch_map.get(survey_form.survey_batch_id)
        if batch is None:
            continue
        primary_group = _movement_primary_group(categories)
        updated_at = (
            record.updated_at if record is not None else person.updated_at
        )
        rows.append({
            "batch": batch,
            "form": survey_form,
            "household": household,
            "person": person,
            "record": record,
            "categories": categories,
            "category_labels": [MOVEMENT_GROUP_LABELS[item] for item in categories],
            "primary_group": primary_group,
            "primary_group_label": MOVEMENT_GROUP_LABELS.get(primary_group, "Cần theo dõi"),
            "learning_label": _MOVEMENT_LEARNING_LABELS.get(
                str(record.learning_status or "CHUA_XAC_DINH").upper()
                if record is not None else "CHUA_XAC_DINH",
                "Chưa xác định",
            ),
            "residency_label": _MOVEMENT_RESIDENCY_LABELS.get(
                str(person.residency_status or "CHUA_XAC_DINH").upper(),
                str(person.residency_status or "Chưa xác định"),
            ),
            "school_name": _movement_school_name(record),
            "class_name": (
                str(record.classroom.name or "").strip()
                if record is not None and record.classroom is not None
                else str(record.class_name_reported or "").strip()
                if record is not None else ""
            ),
            "updated_at": updated_at,
            "updated_at_label": updated_at.strftime("%d/%m/%Y %H:%M"),
            "notes": str(record.notes or "").strip() if record is not None else "",
            "open_url": (
                f"/dieu-tra/{batch.id}/ho-dan/{household.id}/doi-tuong/"
                f"{person.id}/nam-hoc?school_year_id={school_year_id}"
            ),
        })
    return rows, summary, batches


def _movement_query_url(
    *,
    school_year_id: int | None,
    commune_id: int | None,
    school_id: int | None,
    batch_id: int | None,
    group: str,
    q: str,
    page_size: int,
    page: int,
) -> str:
    return "/bao-cao/bien-dong-theo-doi?" + urlencode({
        "school_year_id": school_year_id or "",
        "commune_id": commune_id or "",
        "school_id": school_id or "",
        "batch_id": batch_id or "",
        "group": group,
        "q": q,
        "page_size": page_size,
        "page": page,
    })


@router.get("/bien-dong-theo-doi", response_class=HTMLResponse)
def movement_followup_page(
    request: Request,
    school_year_id: str = "",
    commune_id: str = "",
    school_id: str = "",
    batch_id: str = "",
    group: str = "",
    q: str = "",
    page_size: int = 50,
    page: int = 1,
    db: Session = Depends(get_db),
):
    user = lay_thong_tin_nguoi_dung(request)
    school_years = _load_school_years(db)
    selected_year_id = _choose_year_id(
        school_years,
        _parse_optional_int(school_year_id),
    )
    selected_year = next(
        (item for item in school_years if item.id == selected_year_id),
        None,
    )
    (
        communes,
        schools,
        selected_commune_id,
        selected_school_id,
        scope_label,
    ) = _load_scope_options(
        db,
        user,
        _parse_optional_int(commune_id),
        _parse_optional_int(school_id),
    )
    selected_group = _clean_text(group).upper()
    if selected_group not in MOVEMENT_GROUP_LABELS:
        selected_group = ""
    q = _clean_text(q)[:120]
    if page_size not in PAGE_SIZE_OPTIONS:
        page_size = 50
    selected_batch_id = _parse_optional_int(batch_id)

    all_rows, summary, batches = _build_movement_rows(
        db=db,
        request=request,
        school_year_id=selected_year_id,
        selected_commune_id=selected_commune_id,
        selected_school_id=selected_school_id,
        selected_batch_id=selected_batch_id,
        group=selected_group,
        q=q,
    )
    valid_batch_ids = {item.id for item in batches}
    if selected_batch_id not in valid_batch_ids:
        selected_batch_id = None

    total_records = len(all_rows)
    total_pages = max(1, ceil(total_records / page_size))
    page = max(1, min(page, total_pages))
    start = (page - 1) * page_size
    rows = all_rows[start:start + page_size]
    page_links = [
        {
            "number": number,
            "url": _movement_query_url(
                school_year_id=selected_year_id,
                commune_id=selected_commune_id,
                school_id=selected_school_id,
                batch_id=selected_batch_id,
                group=selected_group,
                q=q,
                page_size=page_size,
                page=number,
            ),
        }
        for number in range(max(1, page - 2), min(total_pages, page + 2) + 1)
    ]
    export_url = "/bao-cao/bien-dong-theo-doi/xuat-excel?" + urlencode({
        "school_year_id": selected_year_id or "",
        "commune_id": selected_commune_id or "",
        "school_id": selected_school_id or "",
        "batch_id": selected_batch_id or "",
        "group": selected_group,
        "q": q,
    })
    return templates.TemplateResponse(
        request=request,
        name="reports/movement_followup.html",
        context={
            "nguoi_dung": user,
            "school_years": school_years,
            "selected_year": selected_year,
            "selected_year_id": selected_year_id,
            "communes": communes,
            "schools": schools,
            "batches": batches,
            "selected_commune_id": selected_commune_id,
            "selected_school_id": selected_school_id,
            "selected_batch_id": selected_batch_id,
            "scope_label": scope_label,
            "group_labels": MOVEMENT_GROUP_LABELS,
            "selected_group": selected_group,
            "q": q,
            "summary": summary,
            "rows": rows,
            "total_records": total_records,
            "page": page,
            "total_pages": total_pages,
            "page_links": page_links,
            "page_size": page_size,
            "page_size_options": PAGE_SIZE_OPTIONS,
            "previous_url": (
                _movement_query_url(
                    school_year_id=selected_year_id,
                    commune_id=selected_commune_id,
                    school_id=selected_school_id,
                    batch_id=selected_batch_id,
                    group=selected_group,
                    q=q,
                    page_size=page_size,
                    page=page - 1,
                ) if page > 1 else None
            ),
            "next_url": (
                _movement_query_url(
                    school_year_id=selected_year_id,
                    commune_id=selected_commune_id,
                    school_id=selected_school_id,
                    batch_id=selected_batch_id,
                    group=selected_group,
                    q=q,
                    page_size=page_size,
                    page=page + 1,
                ) if page < total_pages else None
            ),
            "export_url": export_url,
            "province_reader": is_province_reader(user.get("role_code")),
            "generated_at": datetime.now().strftime("%d/%m/%Y %H:%M"),
        },
    )


@router.get("/bien-dong-theo-doi/xuat-excel")
def export_movement_followup_excel(
    request: Request,
    school_year_id: str = "",
    commune_id: str = "",
    school_id: str = "",
    batch_id: str = "",
    group: str = "",
    q: str = "",
    db: Session = Depends(get_db),
):
    user = lay_thong_tin_nguoi_dung(request)
    school_years = _load_school_years(db)
    selected_year_id = _choose_year_id(
        school_years,
        _parse_optional_int(school_year_id),
    )
    selected_year = next(
        (item for item in school_years if item.id == selected_year_id),
        None,
    )
    (
        _communes,
        _schools,
        selected_commune_id,
        selected_school_id,
        scope_label,
    ) = _load_scope_options(
        db,
        user,
        _parse_optional_int(commune_id),
        _parse_optional_int(school_id),
    )
    selected_group = _clean_text(group).upper()
    if selected_group not in MOVEMENT_GROUP_LABELS:
        selected_group = ""
    q = _clean_text(q)[:120]
    rows, summary, _batches = _build_movement_rows(
        db=db,
        request=request,
        school_year_id=selected_year_id,
        selected_commune_id=selected_commune_id,
        selected_school_id=selected_school_id,
        selected_batch_id=_parse_optional_int(batch_id),
        group=selected_group,
        q=q,
    )

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Bien dong theo doi"
    headers = [
        "STT", "Năm học", "Mã đợt", "Xã/phường", "Số phiếu", "Mã hộ",
        "Chủ hộ", "Mã đối tượng", "Họ và tên", "Ngày sinh", "Giới tính",
        "Số định danh", "Trạng thái cư trú", "Tình trạng học tập",
        "Nhóm cần theo dõi", "Trường", "Lớp", "Thời điểm cập nhật", "Ghi chú",
    ]
    sheet.append(headers)
    for index, row in enumerate(rows, start=1):
        person = row["person"]
        sheet.append([
            index,
            row["batch"].school_year.code,
            row["batch"].code,
            row["batch"].commune.name,
            row["form"].form_number,
            row["household"].code,
            row["household"].head_name,
            person.code,
            person.full_name,
            person.date_of_birth.strftime("%d/%m/%Y") if person.date_of_birth else "",
            person.gender or "",
            person.personal_id or "",
            row["residency_label"],
            row["learning_label"],
            ", ".join(row["category_labels"]),
            row["school_name"],
            row["class_name"],
            row["updated_at_label"],
            row["notes"],
        ])
    _style_sheet(sheet)
    _set_widths(sheet, {
        1: 7, 2: 13, 3: 25, 4: 24, 5: 28, 6: 20, 7: 24, 8: 18,
        9: 25, 10: 13, 11: 11, 12: 18, 13: 18, 14: 18, 15: 30,
        16: 28, 17: 18, 18: 20, 19: 45,
    })
    sheet.page_setup.orientation = sheet.ORIENTATION_LANDSCAPE
    sheet.page_setup.paperSize = sheet.PAPERSIZE_A4
    sheet.page_setup.fitToWidth = 1
    sheet.page_setup.fitToHeight = 0
    sheet.sheet_properties.pageSetUpPr.fitToPage = True
    sheet.page_margins = PageMargins(
        left=0.2, right=0.2, top=0.3, bottom=0.3, header=0.0, footer=0.0
    )
    sheet.print_options.horizontalCentered = True
    sheet.freeze_panes = "A2"

    info = workbook.create_sheet("Thong tin bao cao")
    info.append(["Thông tin", "Giá trị"])
    info_rows = [
        ("Thời điểm lập", datetime.now().strftime("%d/%m/%Y %H:%M")),
        ("Người lập", user.get("full_name", "")),
        ("Vai trò", user.get("role_name", "")),
        ("Đơn vị", user.get("unit_name", "")),
        ("Năm học", selected_year.code if selected_year else ""),
        ("Phạm vi", scope_label),
        ("Nhóm lọc", MOVEMENT_GROUP_LABELS.get(selected_group, "Tất cả")),
        ("Từ khóa", q or "Không"),
        ("Tổng đối tượng cần theo dõi", summary["total"]),
        ("Chuyển đến", summary["CHUYEN_DEN"]),
        ("Chuyển đi", summary["CHUYEN_DI"]),
        ("Thiếu số định danh", summary["THIEU_SO_DINH_DANH"]),
        ("Thiếu dữ liệu năm học", summary["THIEU_DU_LIEU_NAM_HOC"]),
        (
            "Thiết lập in",
            "Khổ A4 ngang, tự co vừa chiều rộng; dùng được với máy in đã cài trên máy.",
        ),
    ]
    for item in info_rows:
        info.append(list(item))
    _style_sheet(info)
    _set_widths(info, {1: 34, 2: 80})

    output = BytesIO()
    workbook.save(output)
    output.seek(0)
    year_code = selected_year.code if selected_year else "khong_nam_hoc"
    filename = f"bien_dong_theo_doi_{year_code}.xlsx"
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

# === BAI_13B_4_V1_LEVEL_REPORT_CENTERS_START ===

_B134_LEVEL_REPORTS = {
    "tieu-hoc": {
        "title": "Bộ báo cáo Phổ cập giáo dục Tiểu học",
        "description": "Tập hợp các biểu Tiểu học hiện có, dùng cùng bộ lọc năm học – xã/phường – trường và xuất trực tiếp đúng mẫu Excel.",
        "path": "/bao-cao/tieu-hoc",
        "reports": [
            ("PCGD_TH_M1_2025", "TH-M1 – Phổ cập giáo dục Tiểu học", "Tự động tổng hợp dữ liệu điều tra độ tuổi Tiểu học.", "Sẵn sàng", "ready"),
            ("PCGD_TH_02_2025", "TH-02 – Kết quả PCGD Tiểu học", "Tự động tổng hợp các chỉ tiêu kết quả PCGD Tiểu học có nguồn dữ liệu.", "Sẵn sàng", "ready"),
            ("PCGD_TH_01_GV_2025", "TH-01-GV – Đội ngũ giáo viên", "Lấy dữ liệu từ phân hệ Đội ngũ theo năm học và phạm vi.", "Sẵn sàng", "ready"),
            ("PCGD_TH_01_CSVC_2025", "TH-01-CSVC – Cơ sở vật chất", "Điền các chỉ tiêu hiện có; chỉ tiêu CSVC chưa có nguồn chuyên biệt được để trống.", "Theo dữ liệu hiện có", "partial"),
        ],
    },
    "thcs": {
        "title": "Bộ báo cáo Phổ cập giáo dục THCS",
        "description": "Tập hợp các biểu THCS hiện có, dùng cùng bộ lọc năm học – xã/phường – trường và xuất trực tiếp đúng mẫu Excel.",
        "path": "/bao-cao/thcs",
        "reports": [
            ("PCGD_THCS_M1_2025", "THCS-M1 – Phổ cập giáo dục THCS", "Tự động tổng hợp đối tượng, học lớp 6–9, hoàn thành và tốt nghiệp theo dữ liệu điều tra.", "Sẵn sàng", "ready"),
            ("PCGD_THCS_M2_2025", "THCS-M2 – Tiêu chuẩn PCGD THCS", "Tự động tổng hợp các chỉ tiêu tiêu chuẩn có nguồn dữ liệu rõ ràng.", "Sẵn sàng", "ready"),
            ("PCGD_THCS_TK_2025", "THCS-TK – Thống kê kết quả", "Tự động tổng hợp kết quả PCGD THCS theo phạm vi.", "Sẵn sàng", "ready"),
            ("PCGD_THCS_M5_2025", "THCS-M5 – Đội ngũ giáo viên", "Lấy dữ liệu từ phân hệ Đội ngũ theo năm học và phạm vi.", "Sẵn sàng", "ready"),
            ("PCGD_THCS_CSVC_2025", "THCS-CSVC – Cơ sở vật chất", "Điền các chỉ tiêu hiện có; chỉ tiêu CSVC chưa có nguồn chuyên biệt được để trống.", "Theo dữ liệu hiện có", "partial"),
        ],
    },
    "xoa-mu-chu": {
        "title": "Bộ báo cáo Xóa mù chữ",
        "description": "Tập hợp các biểu XMC/CMC hiện có, tổng hợp theo năm học và phạm vi điều tra, xuất trực tiếp đúng mẫu Excel.",
        "path": "/bao-cao/xoa-mu-chu",
        "reports": [
            ("PCGD_XMC_3_2025", "XMC-3 – Tổng hợp kết quả xóa mù chữ", "Tự động tổng hợp dân số theo nhóm tuổi và các chỉ tiêu có nguồn dữ liệu.", "Theo dữ liệu hiện có", "partial"),
            ("PCGD_CMC_2_2025", "CMC-2 – Thống kê số người mù chữ", "Tự động điền các chỉ tiêu có thể xác định từ hồ sơ điều tra.", "Theo dữ liệu hiện có", "partial"),
            ("PCGD_CMC_1_2025", "CMC-1 – Tổng hợp chống mù chữ", "Tự động tổng hợp dân số và các nhóm tuổi theo phạm vi.", "Theo dữ liệu hiện có", "partial"),
            ("PCGD_XMC_4_2025", "XMC-4 – Thống kê đạt chuẩn xóa mù chữ", "Tự động điền các chỉ tiêu có nguồn; mức biết chữ chuyên biệt chưa có nguồn sẽ để trống.", "Theo dữ liệu hiện có", "partial"),
        ],
    },
}


def _b134_level_center_context(
    *,
    level_code: str,
    request: Request,
    db: Session,
    school_year_id: int | None,
    commune_id: int | None,
    school_id: int | None,
) -> dict[str, Any]:
    level = _B134_LEVEL_REPORTS[level_code]
    user = lay_thong_tin_nguoi_dung(request)
    years = _load_school_years(db)
    selected_year_id = _choose_year_id(years, school_year_id)
    communes, schools, selected_commune_id, selected_school_id, scope_label = _load_scope_options(
        db,
        user,
        commune_id,
        school_id,
    )
    selected_year = next(
        (item for item in years if item.id == selected_year_id),
        None,
    )

    base_params: dict[str, Any] = {
        "school_year_id": selected_year_id or "",
    }
    if selected_commune_id is not None:
        base_params["commune_id"] = selected_commune_id
    if selected_school_id is not None:
        base_params["school_id"] = selected_school_id

    cards: list[dict[str, Any]] = []
    for report_type, title, description, status, status_class in level["reports"]:
        open_params = dict(base_params)
        open_params["report_type"] = report_type
        export_params = dict(open_params)
        cards.append(
            {
                "report_type": report_type,
                "title": title,
                "description": description,
                "status": status,
                "status_class": status_class,
                "open_url": "/bao-cao?" + urlencode(open_params),
                "export_url": "/bao-cao/xuat-danh-muc-excel?" + urlencode(export_params),
            }
        )

    return {
        "nguoi_dung": user,
        "level": level,
        "school_years": years,
        "selected_year_id": selected_year_id,
        "selected_year": selected_year,
        "communes": communes,
        "schools": schools,
        "selected_commune_id": selected_commune_id,
        "selected_school_id": selected_school_id,
        "scope_label": scope_label,
        "province_reader": is_province_reader(normalize_role_code(user.get("role_code"))),
        "cards": cards,
        "ready_count": sum(1 for item in cards if item["status_class"] == "ready"),
    }


@router.get("/tieu-hoc", response_class=HTMLResponse)
def b134_primary_report_center(
    request: Request,
    school_year_id: int | None = None,
    commune_id: int | None = None,
    school_id: int | None = None,
    db: Session = Depends(get_db),
):
    return templates.TemplateResponse(
        request=request,
        name="reports/level_report_center.html",
        context=_b134_level_center_context(
            level_code="tieu-hoc",
            request=request,
            db=db,
            school_year_id=school_year_id,
            commune_id=commune_id,
            school_id=school_id,
        ),
    )


@router.get("/thcs", response_class=HTMLResponse)
def b134_thcs_report_center(
    request: Request,
    school_year_id: int | None = None,
    commune_id: int | None = None,
    school_id: int | None = None,
    db: Session = Depends(get_db),
):
    return templates.TemplateResponse(
        request=request,
        name="reports/level_report_center.html",
        context=_b134_level_center_context(
            level_code="thcs",
            request=request,
            db=db,
            school_year_id=school_year_id,
            commune_id=commune_id,
            school_id=school_id,
        ),
    )


@router.get("/xoa-mu-chu", response_class=HTMLResponse)
def b134_literacy_report_center(
    request: Request,
    school_year_id: int | None = None,
    commune_id: int | None = None,
    school_id: int | None = None,
    db: Session = Depends(get_db),
):
    return templates.TemplateResponse(
        request=request,
        name="reports/level_report_center.html",
        context=_b134_level_center_context(
            level_code="xoa-mu-chu",
            request=request,
            db=db,
            school_year_id=school_year_id,
            commune_id=commune_id,
            school_id=school_id,
        ),
    )

# === BAI_13B_4_V1_LEVEL_REPORT_CENTERS_END ===
