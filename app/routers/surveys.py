from __future__ import annotations
# === BAI_13B_12_V2_3_9_DATETIME_ALIASES ===
from datetime import date as _b13239_date, datetime as _b13239_datetime
import re

from datetime import date, datetime
from io import BytesIO
from math import ceil
from pathlib import Path
from types import SimpleNamespace
from typing import Annotated, Any
from urllib.parse import urlencode
from uuid import uuid4
import sqlite3
import unicodedata

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    StreamingResponse,
)
from fastapi.templating import Jinja2Templates
from sqlalchemy import and_, case, func, or_, select, text
from sqlalchemy.exc import IntegrityError
from openpyxl import Workbook, load_workbook
from openpyxl.styles import (
    Alignment,
    Border,
    Font,
    PatternFill,
    Side,
)
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation
from sqlalchemy.orm import (
    Session,
    selectinload,
    with_loader_criteria,
)

from app.database import DATABASE_PATH, get_db
from app.permissions import (
    ADMIN_ROLE_CODES,
    COMMUNE_ROLE_CODE,
    DEPARTMENT_ROLE_CODE,
    PROVINCE_READ_ROLE_CODES,
    SCHOOL_ROLE_CODE,
    TEACHER_ROLE_CODE,
    can_edit_survey_data,
    can_manage_survey_assignments,
    is_admin_role,
    is_province_reader,
    normalize_role_code,
)
from app.models import (
    Classroom,
    Commune,
    School,
    SchoolYear,
    Student,
    User,
)
from app.survey_models import (
    Household,
    SurveyBatch,
    SurveyBatchLockLog,
    SurveyForm,
    SurveyFormInvestigator,
    SurveyPerson,
    SurveyPersonYearRecord,
    SurveyFileExchangeLog,
)
from app.survey_workflow_models import SurveySchoolAssignment


APP_DIR = Path(__file__).resolve().parent.parent

templates = Jinja2Templates(
    directory=str(APP_DIR / "templates")
)

router = APIRouter(
    prefix="/dieu-tra",
    tags=["Điều tra phổ cập"],
)


BATCH_STATUS_LABELS = {
    "CHUAN_BI": "Chuẩn bị",
    "DANG_DIEU_TRA": "Đang điều tra",
    "DA_KET_THUC": "Đã kết thúc",
}

FORM_STATUS_LABELS = {
    "CHUA_DIEU_TRA": "Chưa điều tra",
    "DANG_DIEU_TRA": "Đang điều tra",
    "DA_HOAN_THANH": "Đã hoàn thành",
    "CAN_BO_SUNG": "Cần bổ sung",
}

STATUS_MESSAGES = {
    "bulk_assignments_sent_existing": (
        "Đã giao phiếu theo phân công hiện có."
    ),
    "created": "Đã tạo đợt điều tra mới thành công.",
    "household_created": (
        "Đã thêm hộ gia đình và tạo phiếu điều tra thành công."
    ),
    "household_attached": (
        "Hộ gia đình đã có trong hệ thống; "
        "đã tạo phiếu cho đợt điều tra này."
    ),
    "person_created": (
        "Đã thêm đối tượng điều tra vào hộ gia đình thành công."
    ),
    "person_updated": (
        "Đã cập nhật thông tin đối tượng thành công."
    ),
    "person_deactivated": (
        "Đã ngừng theo dõi đối tượng. Lịch sử năm học vẫn được giữ nguyên."
    ),
    "year_record_saved": (
        "Đã lưu thông tin theo dõi năm học thành công."
    ),
    "household_auto_completed": (
        "Đã lưu thành viên cuối và hoàn thành hộ dân thành công."
    ),
    "form_updated": (
        "Đã cập nhật trạng thái và thông tin phiếu điều tra thành công."
    ),
    "quick_saved": (
        "Đã lưu thông tin hộ và phiếu điều tra."
    ),
    "quick_saved_next": (
        "Đã lưu hộ trước và chuyển sang hộ tiếp theo."
    ),
    "quick_saved_last": (
        "Đã lưu hộ. Đây là hộ cuối cùng trong phạm vi được giao."
    ),
    "quick_person_created": (
        "Đã thêm nhanh thành viên vào hộ."
    ),
    "investigators_saved": (
        "Đã lưu phân công người điều tra cho phiếu thành công."
    ),
    "investigators_cleared": (
        "Đã xóa phân công người điều tra trong phạm vi được phép."
    ),
    "bulk_assignments_saved": (
        "Đã cập nhật phân công hàng loạt thành công."
    ),
    "bulk_assignments_cleared": (
        "Đã thu hồi phân công hàng loạt thành công."
    ),
    "batch_locked": (
        "Đợt điều tra đã được khóa ở cấp xã hoặc theo cơ chế chốt số liệu. "
        "Bạn vẫn có thể xem và xuất báo cáo nhưng không thể cập nhật."
    ),
    "province_locked": (
        "Sở đã khóa đợt điều tra trên toàn tỉnh. Xã, trường và giáo viên "
        "chỉ được xem dữ liệu cho đến khi Sở mở lại."
    ),
    "school_locked": (
        "Xã/phường đã khóa quyền cập nhật của trường. "
        "Trường và giáo viên vẫn được xem dữ liệu."
    ),
    "lock_admin_only": (
        "Chỉ tài khoản quản trị mới được chốt hoặc mở khóa đợt điều tra."
    ),
    "batch_locked_success": (
        "Đã chốt số liệu và khóa đợt điều tra thành công."
    ),
    "batch_unlocked_success": (
        "Đã mở khóa đợt điều tra thành công."
    ),
    "summary_requires_lock": (
        "Chỉ được xuất báo cáo kết quả chính thức sau khi đợt điều tra đã chốt và khóa dữ liệu."
    ),
    "inheritance_admin_only": (
        "Chỉ tài khoản quản trị mới được kế thừa dữ liệu sang năm học mới."
    ),
    "inheritance_source_requires_lock": (
        "Đợt nguồn phải được chốt và khóa dữ liệu trước khi kế thừa."
    ),
    "inheritance_success": (
        "Đã kế thừa danh sách hộ và tạo hồ sơ năm học mới thành công."
    ),
    "inheritance_target_created": (
        "Đã tạo đợt điều tra của năm học mới. Hãy kiểm tra và thực hiện kế thừa."
    ),
}

# === GV_MOBILE_V18_STATUS_START ===
STATUS_MESSAGES.update(
    {
        "mobile_person_accepted": "Đã chấp nhận thông tin thành viên.",
        "mobile_person_need_edit": "Thành viên chưa có dữ liệu để chấp nhận. Hãy bấm Sửa và lưu thông tin trước.",
    }
)
# === GV_MOBILE_V18_STATUS_END ===

HOUSEHOLD_PAGE_SIZE = 20
HOUSEHOLD_PAGE_SIZE_OPTIONS = (20, 50, 100)
HOUSEHOLD_SORT_OPTIONS = {
    "hamlet": "Thôn/xóm và chủ hộ",
    "updated_desc": "Cập nhật mới nhất",
    "head_name": "Tên chủ hộ",
    "status": "Trạng thái phiếu",
}
PERSON_PAGE_SIZE = 20

RESIDENCY_STATUS_LABELS = {
    "THUONG_TRU": "Thường trú",
    "TAM_TRU": "Tạm trú",
    "TAM_VANG": "Tạm vắng",
    "CHUYEN_DEN": "Chuyển đến",
    "CHUYEN_DI": "Chuyển đi",
    "CHUA_XAC_DINH": "Chưa xác định",
}


LEARNING_STATUS_LABELS = {
    "DANG_HOC": "Đang học",
    "CHUA_DI_HOC": "Chưa đi học",
    "CHUYEN_DEN": "Chuyển đến",
    "CHUYEN_DI": "Chuyển đi",
    "TAM_NGHI": "Tạm nghỉ",
    "THOI_HOC": "Thôi học",
    "BO_HOC": "Bỏ học",
    "DA_TOT_NGHIEP": "Đã tốt nghiệp",
    "KHONG_THUOC_DIEN": "Không thuộc diện theo dõi",
}

DISABILITY_STATUS_LABELS = {
    "CHUA_XAC_DINH": "Chưa xác định",
    "KHONG_KHUYET_TAT": "Không khuyết tật",
    "CO_KHUYET_TAT": "Có khuyết tật",
}

DISABILITY_TYPE_LABELS = {
    "VAN_DONG": "Khuyết tật vận động",
    "NGHE_NOI": "Khuyết tật nghe, nói",
    "NHIN": "Khuyết tật nhìn",
    "THAN_KINH_TAM_THAN": "Khuyết tật thần kinh, tâm thần",
    "TRI_TUE": "Khuyết tật trí tuệ",
    "DA_TAT": "Đa khuyết tật",
    "KHAC": "Khuyết tật khác",
}

DISABILITY_LEVEL_LABELS = {
    "CHUA_XAC_DINH": "Chưa xác định mức độ",
    "NHE": "Mức độ nhẹ",
    "NANG": "Mức độ nặng",
    "DAC_BIET_NANG": "Mức độ đặc biệt nặng",
}

BOOLEAN_YEAR_FIELDS = (
    "completed_preschool_by_age",
    "attends_required_days",
    "attends_regularly",
    "prepared_vietnamese",
    "weight_monitored",
    "underweight",
    "height_monitored",
    "stunted",
    "attends_two_sessions_per_day",
)

# === BAI_13B_11_13_3_1_DYNAMIC_PROGRESS_START ===
B131133_MN_FIELDS = (
    "completed_preschool_by_age",
    "attends_two_sessions_per_day",
)


def b131133_chuan_hoa_khong_dau(value):
    import unicodedata

    text_value = str(value or "")
    text_value = unicodedata.normalize("NFD", text_value)
    text_value = "".join(
        char
        for char in text_value
        if unicodedata.category(char) != "Mn"
    )
    return " ".join(text_value.upper().split())


def b131133_nam_tham_chieu(school_year):
    import re as _re

    code = str(getattr(school_year, "code", "") or "")
    match = _re.search(r"\b(20\d{2})\b", code)

    if match is None:
        return None

    try:
        return int(match.group(1))
    except (TypeError, ValueError):
        return None


def b131133_xac_dinh_cap_hoc(person, record, school_year):
    import re as _re

    school_name = ""
    class_name = ""

    if record is not None:
        school_name = str(
            getattr(record, "school_name_reported", None)
            or getattr(getattr(record, "school", None), "name", "")
            or ""
        )
        class_name = str(
            getattr(record, "class_name_reported", None)
            or getattr(getattr(record, "classroom", None), "name", "")
            or ""
        )

    school_key = b131133_chuan_hoa_khong_dau(school_name)
    class_key = b131133_chuan_hoa_khong_dau(class_name)
    combined = f"{school_key} {class_key}".strip()

    if (
        "MAM NON" in combined
        or "MAU GIAO" in combined
        or "NHA TRE" in combined
        or _re.search(r"(^|\s)MN(\s|$)", school_key)
    ):
        return "MN"

    if "THCS" in combined or "TRUNG HOC CO SO" in combined:
        return "THCS"

    if "THPT" in combined or "TRUNG HOC PHO THONG" in combined:
        return "OTHER"

    if (
        "TIEU HOC" in combined
        or "PRIMARY" in combined
        or _re.search(r"(^|\s)TH(\s|$)", school_key)
    ):
        return "TH"

    grade = None
    match = _re.search(r"\bLOP\s*([0-9]{1,2})\b", class_key)
    if match is None:
        match = _re.match(r"^\s*([0-9]{1,2})(?:\s|[A-Z]|$)", class_key)

    if match is not None:
        try:
            grade = int(match.group(1))
        except (TypeError, ValueError):
            grade = None

    if grade is not None:
        if 1 <= grade <= 5:
            return "TH"
        if 6 <= grade <= 9:
            return "THCS"
        if 10 <= grade <= 12:
            return "OTHER"

    birth_date = getattr(person, "date_of_birth", None)
    reference_year = b131133_nam_tham_chieu(school_year)

    if birth_date is not None and reference_year is not None:
        try:
            age = reference_year - int(birth_date.year)
        except (TypeError, ValueError, AttributeError):
            age = None

        if age is not None:
            if 0 <= age <= 5:
                return "MN"
            if 6 <= age <= 10:
                return "TH"
            if 11 <= age <= 14:
                return "THCS"

    return "OTHER"


def b131133_truong_da_tra_loi(record, field_name):
    if record is None:
        return False

    value = getattr(record, field_name, None)

    if field_name in {"literacy_status", "post_lower_secondary_path", "education_attainment_level"}:
        normalized = str(value or "").strip().upper()
        return normalized not in {"", "CHUA_XAC_DINH", "NONE"}

    return value is not None


def b131133_tien_do_nam_hoc(*, person, record, school_year):
    level = b131133_xac_dinh_cap_hoc(person, record, school_year)

    required_fields = [
        "highest_completed_grade",
        "education_attainment_level",
        "is_literacy_target",
    ]

    is_literacy_target = (
        getattr(record, "is_literacy_target", None)
        if record is not None
        else None
    )

    if is_literacy_target is True:
        required_fields.extend(
            (
                "literacy_status",
                "completed_grade_3",
                "completed_grade_5",
            )
        )

    if level == "MN":
        # === BAI_13B_11_14_2_REPORT_PROGRESS_START ===
        required_fields.extend(B131133_MN_FIELDS)
        required_fields.append("disability_status")

        ethnic_key = b131133_chuan_hoa_khong_dau(
            getattr(person, "ethnic_group", None)
        )

        if (
            ethnic_key
            and ethnic_key not in {"KINH", "DAN TOC KINH"}
        ):
            required_fields.append("prepared_vietnamese")

        disability_status_value = (
            getattr(record, "disability_status", None)
            if record is not None
            else None
        )

        if disability_status_value == "CO_KHUYET_TAT":
            required_fields.extend(
                (
                    "disability_type",
                    "disability_can_learn",
                    "disability_access_education",
                )
            )
        # === BAI_13B_11_14_2_REPORT_PROGRESS_END ===
    elif level == "TH":
        required_fields.append("completed_primary_program")
    elif level == "THCS":
        required_fields.extend(
            (
                "completed_lower_secondary_program",
                "post_lower_secondary_path",
            )
        )

    answered = sum(
        b131133_truong_da_tra_loi(record, field_name)
        for field_name in required_fields
    )
    total = len(required_fields)

    return {
        "level": level,
        "answered": int(answered),
        "total": int(total),
        "complete": bool(record is not None and answered == total),
        "required_fields": tuple(required_fields),
    }

def b131133_danh_gia_do_day_du_phieu_nhap_nhanh(*, db, survey_form):
    people = list(
        db.scalars(
            select(SurveyPerson)
            .where(
                SurveyPerson.household_id == survey_form.household_id,
                SurveyPerson.is_active.is_(True),
            )
            .order_by(
                SurveyPerson.date_of_birth.asc(),
                SurveyPerson.full_name.asc(),
                SurveyPerson.id.asc(),
            )
        ).all()
    )

    person_ids = [int(person.id) for person in people]

    records = []
    if person_ids:
        records = list(
            db.scalars(
                select(SurveyPersonYearRecord)
                .where(
                    SurveyPersonYearRecord.survey_form_id == survey_form.id,
                    SurveyPersonYearRecord.school_year_id
                    == survey_form.survey_batch.school_year_id,
                    SurveyPersonYearRecord.survey_person_id.in_(person_ids),
                )
                .order_by(
                    SurveyPersonYearRecord.updated_at.desc(),
                    SurveyPersonYearRecord.id.desc(),
                )
            ).all()
        )

    record_by_person = {}
    for record in records:
        record_by_person.setdefault(int(record.survey_person_id), record)

    missing_personal_id_count = 0
    missing_year_record_count = 0
    incomplete_year_record_count = 0
    school_year = survey_form.survey_batch.school_year

    for person in people:
        if not str(getattr(person, "personal_id", "") or "").strip():
            missing_personal_id_count += 1

        record = record_by_person.get(int(person.id))

        if record is None:
            missing_year_record_count += 1
            continue

        progress = b131133_tien_do_nam_hoc(
            person=person,
            record=record,
            school_year=school_year,
        )

        if not bool(progress["complete"]):
            incomplete_year_record_count += 1

    return {
        "active_people_count": len(people),
        "missing_personal_id_count": int(missing_personal_id_count),
        "missing_year_record_count": int(missing_year_record_count),
        "incomplete_year_record_count": int(incomplete_year_record_count),
    }
# === BAI_13B_11_13_3_1_DYNAMIC_PROGRESS_END ===



DATA_QUALITY_PAGE_SIZE = 20
DATA_QUALITY_PAGE_SIZE_OPTIONS = (20, 50, 100)

DATA_QUALITY_ISSUE_LABELS = {
    "CHUA_PHAN_CONG": "Phiếu chưa được phân công",
    "KHONG_CO_DOI_TUONG": "Hộ chưa có đối tượng đang theo dõi",
    "THIEU_THONG_TIN_CA_NHAN": "Đối tượng thiếu thông tin cá nhân cơ bản",
    "THIEU_SO_DINH_DANH": "Đối tượng thiếu số định danh cá nhân",
    "THIEU_DU_LIEU_NAM": "Đối tượng chưa có dữ liệu năm học",
    "THIEU_CHI_BAO": "Đối tượng chưa hoàn thành thông tin năm học theo nhóm đối tượng",
    "THIEU_NGAY_DIEU_TRA": "Phiếu thiếu ngày điều tra",
    "CHUA_HO_XAC_NHAN": "Hộ gia đình chưa xác nhận",
    "CHUA_XA_XAC_NHAN": "Xã/phường chưa xác nhận",
    "THIEU_NOI_DUNG_BO_SUNG": "Phiếu cần bổ sung nhưng chưa ghi nội dung",
    "CHUA_DONG_BO_THONG_TIN_HO": "Thông tin hộ và ảnh chụp phiếu chưa đồng bộ",
    "CHUA_HOAN_THANH": "Phiếu chưa được đánh dấu hoàn thành",
}

DATA_QUALITY_FILTER_LABELS = {
    "": "Tất cả kết quả",
    "DAT_YEU_CAU": "Đạt yêu cầu",
    "SAN_SANG_HOAN_THANH": "Sẵn sàng hoàn thành",
    "CAN_KIEM_TRA": "Cần kiểm tra",
    "CAN_XU_LY": "Cần xử lý",
    **DATA_QUALITY_ISSUE_LABELS,
}


SURVEY_SCOPE_DESCRIPTIONS = {
    "SO": "Quyền quản trị cũ trong giai đoạn chuyển đổi; xem toàn tỉnh.",
    "ADMIN": "Quản trị và xem dữ liệu điều tra trong phạm vi toàn tỉnh.",
    "PHONG_BAN": "Chỉ xem và xuất dữ liệu điều tra trong phạm vi toàn tỉnh.",
    "XA": "Tiếp nhận đợt do Sở tạo; phân công, kiểm tra và khóa các trường thuộc xã/phường.",
    "TRUONG": (
        "Tiếp nhận nhiệm vụ do xã giao; phân công tiếp cho cán bộ quản lý "
        "hoặc giáo viên thuộc trường và gửi kết quả lên xã."
    ),
    "GIAO_VIEN": "Chỉ nhập và cập nhật các phiếu được phân công trực tiếp.",
}


def lay_thong_tin_nguoi_dung(
    request: Request,
) -> dict[str, Any]:
    """Lấy thông tin tài khoản đã được middleware xác thực."""

    return dict(request.scope.get("auth_user") or {})


def tao_bo_loc_dot_theo_nguoi_dung(
    request: Request,
) -> list[Any]:
    """Tạo bộ lọc đợt điều tra theo phạm vi của tài khoản."""

    user = lay_thong_tin_nguoi_dung(request)
    role_code = str(user.get("role_code") or "")

    if is_province_reader(role_code):
        return []

    if role_code == "XA":
        commune_id = user.get("commune_id")
        if commune_id is None:
            return [SurveyBatch.id == -1]

        return [
            SurveyBatch.commune_id == int(commune_id),
        ]

    if role_code == "TRUONG":
        school_id = user.get("school_id")
        if school_id is None:
            return [SurveyBatch.id == -1]

        return [
            or_(
                SurveyBatch.id.in_(
                    select(SurveySchoolAssignment.survey_batch_id).where(
                        SurveySchoolAssignment.school_id == int(school_id)
                    )
                ),
                SurveyBatch.survey_forms.any(
                    SurveyForm.investigators.any(
                        SurveyFormInvestigator.user.has(
                            and_(
                                User.school_id == int(school_id),
                                # === BAI_13B_10_V3_10_FIX_SCHOOL_BATCH_ROLE_START ===
                                # Phiếu được giao cho GIÁO VIÊN của trường,
                                # không phải tài khoản vai trò TRƯỜNG.
                                User.role.has(code=TEACHER_ROLE_CODE),
                                # === BAI_13B_10_V3_10_FIX_SCHOOL_BATCH_ROLE_END ===
                                ~func.lower(User.username).like("cbql.%"),
                            )
                        )
                    )
                ),
            )
        ]

    # === BAI_13B_12_V2_2_TEACHER_BATCH_SCOPE_START ===
    if role_code == "GIAO_VIEN":
        user_id = user.get("id")
        if user_id is None:
            return [SurveyBatch.id == -1]

        legacy_assigned_form = (
            SurveyBatch.survey_forms.any(
                SurveyForm.investigators.any(
                    SurveyFormInvestigator.user_id == int(user_id)
                )
            )
        )
        team_membership = text(
            "EXISTS ("
            "SELECT 1 "
            "FROM survey_investigation_teams AS b1322_t "
            "JOIN survey_investigation_team_members AS b1322_tm "
            "ON b1322_tm.team_id = b1322_t.id "
            "WHERE b1322_t.survey_batch_id = survey_batches.id "
            "AND b1322_t.status = 'SENT' "
            f"AND b1322_tm.user_id = {int(user_id)}"
            ")"
        )

        return [
            or_(
                legacy_assigned_form,
                team_membership,
            )
        ]
    # === BAI_13B_12_V2_2_TEACHER_BATCH_SCOPE_END ===

    return [SurveyBatch.id == -1]


def tao_bo_loc_phieu_theo_nguoi_dung(
    request: Request,
) -> list[Any]:
    """Tạo bộ lọc phiếu trong một đợt theo tài khoản."""

    user = lay_thong_tin_nguoi_dung(request)
    role_code = str(user.get("role_code") or "")

    if is_province_reader(role_code) or role_code == COMMUNE_ROLE_CODE:
        return []

    if role_code == "TRUONG":
        school_id = user.get("school_id")
        if school_id is None:
            return [SurveyForm.id == -1]

        return [
            SurveyForm.investigators.any(
                SurveyFormInvestigator.user.has(
                    and_(
                        User.school_id == int(school_id),
                        # === BAI_13B_10_V3_10_FIX_SCHOOL_FORM_ROLE_START ===
                        # Phiếu được giao cho GIÁO VIÊN của trường,
                        # không phải tài khoản vai trò TRƯỜNG.
                        User.role.has(code=TEACHER_ROLE_CODE),
                        # === BAI_13B_10_V3_10_FIX_SCHOOL_FORM_ROLE_END ===
                        ~func.lower(User.username).like("cbql.%"),
                    )
                )
            )
        ]

    if role_code == "GIAO_VIEN":
        user_id = user.get("id")
        if user_id is None:
            return [SurveyForm.id == -1]

        return [
            SurveyForm.investigators.any(
                SurveyFormInvestigator.user_id == int(user_id)
            )
        ]

    return [SurveyForm.id == -1]


# === BAI_13B_12_V2_4_3_15_MOBILE_FORM_SCOPE_GUARD_START ===
def co_quyen_truy_cap_phieu(
    *,
    db: Session,
    request: Request,
    survey_form: SurveyForm,
) -> bool:
    """Kiểm tra lại quyền trên đúng phiếu, kể cả khi URL được nhập trực tiếp.

    Bộ lọc dùng chung giữ nguyên phạm vi hiện có:
    - Sở/Admin/Xã: theo quyền đã được middleware và phạm vi đợt kiểm soát.
    - Trường: chỉ phiếu thuộc giáo viên của trường.
    - Giáo viên: chỉ phiếu được phân công trực tiếp.
    """
    filters = tao_bo_loc_phieu_theo_nguoi_dung(request)
    if not filters:
        return True

    allowed_form_id = db.scalar(
        select(SurveyForm.id).where(
            SurveyForm.id == int(survey_form.id),
            *filters,
        )
    )
    return allowed_form_id is not None


# === BAI_13B_12_V2_4_3_15_MOBILE_FORM_SCOPE_GUARD_END ===


def tao_bo_loc_bao_cao_theo_nguoi_dung(
    request: Request,
) -> list[Any]:
    """Tạo bộ lọc báo cáo; Trường và Giáo viên xem toàn trường."""

    user = lay_thong_tin_nguoi_dung(request)
    role_code = normalize_role_code(user.get("role_code"))

    if is_province_reader(role_code) or role_code == COMMUNE_ROLE_CODE:
        return []

    if role_code in {SCHOOL_ROLE_CODE, TEACHER_ROLE_CODE}:
        school_id = user.get("school_id")
        if school_id is None:
            return [SurveyForm.id == -1]

        return [
            SurveyForm.investigators.any(
                SurveyFormInvestigator.user.has(
                    User.school_id == int(school_id)
                )
            )
        ]

    return [SurveyForm.id == -1]


def tao_thong_tin_quyen_giao_dien(
    request: Request,
) -> dict[str, Any]:
    """Các cờ quyền dùng để ẩn/hiện chức năng trên giao diện."""

    user = lay_thong_tin_nguoi_dung(request)
    role_code = str(user.get("role_code") or "")

    admin = is_admin_role(role_code)
    province_reader = is_province_reader(role_code)
    can_edit = can_edit_survey_data(role_code)

    if admin:
        empty_scope_message = (
            "Hãy tạo đợt điều tra đầu tiên bằng biểu mẫu bên cạnh."
        )
    elif role_code == TEACHER_ROLE_CODE:
        empty_scope_message = (
            "Bạn chưa được phân công phiếu điều tra nào."
        )
    elif role_code == SCHOOL_ROLE_CODE:
        empty_scope_message = (
            "Trường chưa được xã/phường giao nhiệm vụ điều tra trong đợt nào."
        )
    elif role_code == COMMUNE_ROLE_CODE:
        empty_scope_message = (
            "Chưa có đợt điều tra nào thuộc xã/phường của tài khoản."
        )
    elif role_code == DEPARTMENT_ROLE_CODE:
        empty_scope_message = (
            "Chưa có đợt điều tra nào phù hợp với bộ lọc."
        )
    else:
        empty_scope_message = (
            "Chưa có dữ liệu điều tra thuộc phạm vi của tài khoản."
        )

    return {
        "co_quyen_tao_dot": False,
        "co_quyen_quan_tri_dot": admin,
        "co_quyen_phan_cong": can_manage_survey_assignments(role_code),
        "co_quyen_phan_cong_truong": (
            admin or role_code == COMMUNE_ROLE_CODE
        ),
        "co_quyen_gui_xa": role_code == SCHOOL_ROLE_CODE,
        "co_quyen_dieu_hanh_toan_tinh": role_code in {
            *ADMIN_ROLE_CODES,
            DEPARTMENT_ROLE_CODE,
        },
        "co_quyen_khoa_xa": (
            admin or role_code == COMMUNE_ROLE_CODE
        ),
        "co_quyen_cap_nhat_du_lieu": can_edit,
        "co_quyen_xem_tien_do": role_code in {
            *PROVINCE_READ_ROLE_CODES,
            COMMUNE_ROLE_CODE,
            SCHOOL_ROLE_CODE,
            TEACHER_ROLE_CODE,
        },
        "co_quyen_xuat_du_lieu": role_code in {
            *PROVINCE_READ_ROLE_CODES,
            COMMUNE_ROLE_CODE,
            SCHOOL_ROLE_CODE,
            TEACHER_ROLE_CODE,
        },
        "chi_xem_du_lieu": role_code in {
            DEPARTMENT_ROLE_CODE,
            COMMUNE_ROLE_CODE,
            SCHOOL_ROLE_CODE,
        },
        "pham_vi_han_che": role_code not in ADMIN_ROLE_CODES,
        "pham_vi_mo_ta": SURVEY_SCOPE_DESCRIPTIONS.get(
            role_code,
            "Tài khoản chưa được cấu hình phạm vi điều tra.",
        ),
        "empty_scope_message": empty_scope_message,
    }


def chuan_hoa_van_ban(value: str) -> str:
    """Xóa khoảng trắng thừa trong văn bản."""

    return " ".join(value.strip().split())


def chuan_hoa_ma(value: str) -> str:
    """Chuẩn hóa mã định danh nhưng vẫn giữ dạng văn bản."""

    return "".join(value.strip().split()).upper()


def chuan_hoa_so_dien_thoai(value: str) -> str | None:
    """Giữ số điện thoại dưới dạng văn bản."""

    normalized = "".join(value.strip().split())
    return normalized or None


def chuyen_ngay(
    value: str,
    ten_truong: str,
    bat_buoc: bool = False,
) -> tuple[date | None, str | None]:
    value = value.strip()

    if not value:
        if bat_buoc:
            return None, f"{ten_truong} không được để trống."
        return None, None

    try:
        result = date.fromisoformat(value)
    except ValueError:
        return None, f"{ten_truong} không đúng định dạng."

    return result, None


def tao_ma_dot_dieu_tra(
    db: Session,
    commune: Commune,
    school_year: SchoolYear,
) -> str:
    year_code = school_year.code.replace("-", "")

    existing_count = db.scalar(
        select(func.count(SurveyBatch.id)).where(
            SurveyBatch.commune_id == commune.id,
            SurveyBatch.school_year_id == school_year.id,
        )
    )

    sequence = int(existing_count or 0) + 1

    while True:
        candidate = (
            f"DT-{commune.code}-{year_code}-{sequence:03d}"
        )

        duplicate = db.scalar(
            select(SurveyBatch.id).where(
                SurveyBatch.code == candidate
            )
        )

        if duplicate is None:
            return candidate

        sequence += 1


def tao_ma_ho(
    db: Session,
    commune: Commune,
) -> str:
    """Tạo mã hộ duy nhất trong toàn hệ thống."""

    existing_count = db.scalar(
        select(func.count(Household.id)).where(
            Household.commune_id == commune.id
        )
    )

    sequence = int(existing_count or 0) + 1

    while True:
        candidate = (
            f"HO-{commune.code}-{sequence:06d}"
        )

        duplicate = db.scalar(
            select(Household.id).where(
                Household.code == candidate
            )
        )

        if duplicate is None:
            return candidate

        sequence += 1


def tao_so_phieu(
    db: Session,
    batch: SurveyBatch,
) -> str:
    """Tạo số phiếu duy nhất trong một đợt điều tra."""

    year_code = batch.school_year.code.replace("-", "")

    existing_count = db.scalar(
        select(func.count(SurveyForm.id)).where(
            SurveyForm.survey_batch_id == batch.id
        )
    )

    sequence = int(existing_count or 0) + 1

    while True:
        candidate = (
            f"PH-{batch.commune.code}-"
            f"{year_code}-{sequence:06d}"
        )

        duplicate = db.scalar(
            select(SurveyForm.id).where(
                SurveyForm.survey_batch_id == batch.id,
                SurveyForm.form_number == candidate,
            )
        )

        if duplicate is None:
            return candidate

        sequence += 1


def lay_du_lieu_danh_muc(
    db: Session,
) -> tuple[list[SchoolYear], list[Commune]]:
    school_years = db.scalars(
        select(SchoolYear)
        .where(SchoolYear.is_active.is_(True))
        .order_by(SchoolYear.code.desc())
    ).all()

    communes = db.scalars(
        select(Commune)
        .where(Commune.is_active.is_(True))
        .order_by(Commune.name.asc())
    ).all()

    return school_years, communes


def lay_dot_dieu_tra(
    db: Session,
    batch_id: int,
) -> SurveyBatch | None:
    return db.scalar(
        select(SurveyBatch)
        .options(
            selectinload(SurveyBatch.school_year),
            selectinload(SurveyBatch.commune),
        )
        .where(SurveyBatch.id == batch_id)
    )


def tao_url_danh_sach_ho(
    batch_id: int,
    page: int,
    q: str,
    hamlet: str,
    form_status: str = "",
    investigator_id: int = 0,
    assignment_status: str = "",
    object_filter: str = "",
    page_size: int = HOUSEHOLD_PAGE_SIZE,
    sort: str = "hamlet",
) -> str:
    """Tạo URL danh sách hộ và giữ nguyên toàn bộ bộ lọc."""

    parameters: dict[str, str | int] = {
        "page": page,
        "page_size": page_size,
        "sort": sort,
    }

    if q:
        parameters["q"] = q

    if hamlet:
        parameters["hamlet"] = hamlet

    if form_status:
        parameters["form_status"] = form_status

    if investigator_id > 0:
        parameters["investigator_id"] = investigator_id

    if assignment_status:
        parameters["assignment_status"] = assignment_status

    # BATCH25_OBJECT_FILTER_BACKEND
    if object_filter:
        parameters["object_filter"] = object_filter

    return (
        f"/dieu-tra/{batch_id}/ho-dan?"
        + urlencode(parameters)
    )



def tao_ma_doi_tuong(db: Session) -> str:
    """Tạo mã đối tượng duy nhất, ví dụ DT-00000001."""

    existing_count = db.scalar(
        select(func.count(SurveyPerson.id))
    )

    sequence = int(existing_count or 0) + 1

    while True:
        candidate = f"DT-{sequence:08d}"

        duplicate = db.scalar(
            select(SurveyPerson.id).where(
                SurveyPerson.code == candidate
            )
        )

        if duplicate is None:
            return candidate

        sequence += 1


def lay_phieu_ho(
    db: Session,
    batch_id: int,
    household_id: int,
) -> SurveyForm | None:
    """Lấy đúng phiếu của hộ trong đợt điều tra."""

    return db.scalar(
        select(SurveyForm)
        .options(
            selectinload(SurveyForm.household)
            .selectinload(Household.people),
            selectinload(SurveyForm.survey_batch)
            .selectinload(SurveyBatch.school_year),
            selectinload(SurveyForm.survey_batch)
            .selectinload(SurveyBatch.commune),
        )
        .where(
            SurveyForm.survey_batch_id == batch_id,
            SurveyForm.household_id == household_id,
        )
    )



def _cau_lenh_tao_bang_nhat_ky_phan_cong() -> tuple[str, str]:
    return (
        """
        CREATE TABLE IF NOT EXISTS survey_assignment_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            survey_form_id INTEGER NOT NULL,
            action VARCHAR(40) NOT NULL,
            actor_user_id INTEGER,
            actor_name_snapshot VARCHAR(200),
            actor_role_snapshot VARCHAR(50),
            target_user_ids TEXT,
            notes TEXT,
            created_at DATETIME NOT NULL,
            FOREIGN KEY (survey_form_id)
                REFERENCES survey_forms(id)
                ON DELETE CASCADE,
            FOREIGN KEY (actor_user_id)
                REFERENCES users(id)
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS
            ix_survey_assignment_logs_form_created
        ON survey_assignment_logs (
            survey_form_id,
            created_at
        )
        """,
    )


def khoi_tao_bang_nhat_ky_phan_cong() -> None:
    """Khởi tạo bảng nhật ký ngay khi mô-đun được nạp."""

    create_table_sql, create_index_sql = (
        _cau_lenh_tao_bang_nhat_ky_phan_cong()
    )
    connection = sqlite3.connect(str(DATABASE_PATH))
    try:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute(create_table_sql)
        connection.execute(create_index_sql)
        connection.commit()
    finally:
        connection.close()


def dam_bao_bang_nhat_ky_phan_cong(db: Session) -> None:
    """Bảo đảm bảng tồn tại trong chính giao dịch đang dùng."""

    create_table_sql, create_index_sql = (
        _cau_lenh_tao_bang_nhat_ky_phan_cong()
    )
    db.execute(text(create_table_sql))
    db.execute(text(create_index_sql))


khoi_tao_bang_nhat_ky_phan_cong()

def ghi_nhat_ky_phan_cong(
    *,
    db: Session,
    survey_form_id: int,
    action: str,
    actor_user: dict[str, Any],
    target_user_ids: list[int],
    notes: str = "",
) -> None:
    """Ghi người thao tác, thời điểm và danh sách tài khoản được giao."""

    dam_bao_bang_nhat_ky_phan_cong(db)

    db.execute(
        text(
            """
            INSERT INTO survey_assignment_logs (
                survey_form_id,
                action,
                actor_user_id,
                actor_name_snapshot,
                actor_role_snapshot,
                target_user_ids,
                notes,
                created_at
            ) VALUES (
                :survey_form_id,
                :action,
                :actor_user_id,
                :actor_name_snapshot,
                :actor_role_snapshot,
                :target_user_ids,
                :notes,
                :created_at
            )
            """
        ),
        {
            "survey_form_id": survey_form_id,
            "action": action,
            "actor_user_id": actor_user.get("id"),
            "actor_name_snapshot": (
                str(actor_user.get("full_name") or "")[:200] or None
            ),
            "actor_role_snapshot": (
                str(actor_user.get("role_code") or "")[:50] or None
            ),
            "target_user_ids": ",".join(
                str(item) for item in target_user_ids
            ),
            "notes": notes[:1000] or None,
            "created_at": datetime.now().isoformat(
                sep=" ",
                timespec="seconds",
            ),
        },
    )


def lay_nhat_ky_phan_cong_gan_nhat(
    db: Session,
    survey_form_id: int,
) -> dict[str, Any] | None:
    """Lấy lần phân công hoặc thu hồi gần nhất của phiếu."""

    dam_bao_bang_nhat_ky_phan_cong(db)

    row = db.execute(
        text(
            """
            SELECT
                sal.id,
                sal.action,
                sal.actor_user_id,
                sal.actor_name_snapshot,
                sal.actor_role_snapshot,
                sal.target_user_ids,
                sal.notes,
                sal.created_at
            FROM survey_assignment_logs AS sal
            WHERE sal.survey_form_id = :survey_form_id
            ORDER BY sal.id DESC
            LIMIT 1
            """
        ),
        {"survey_form_id": survey_form_id},
    ).mappings().first()

    return dict(row) if row else None


def lay_pham_vi_phan_cong(
    request: Request,
) -> dict[str, Any]:
    """Thông tin phạm vi phân công theo tài khoản đang đăng nhập."""

    user = lay_thong_tin_nguoi_dung(request)
    role_code = normalize_role_code(user.get("role_code"))

    if is_admin_role(role_code):
        description = (
            "Quản trị hệ thống được phân công trong toàn bộ đợt điều tra."
        )
    elif role_code == COMMUNE_ROLE_CODE:
        description = (
            "Xã/phường được phân công các phiếu thuộc đúng địa bàn của mình."
        )
    elif role_code == SCHOOL_ROLE_CODE:
        description = (
            "Trường chỉ phân công các phiếu đã được giao cho nhân sự "
            "thuộc trường và chỉ chọn tài khoản của chính trường."
        )
    else:
        description = "Tài khoản không có quyền quản lý phân công."

    return {
        "user": user,
        "role_code": role_code,
        "commune_id": user.get("commune_id"),
        "school_id": user.get("school_id"),
        "description": description,
        "can_manage": can_manage_survey_assignments(role_code),
    }


def lay_danh_sach_nguoi_dieu_tra(
    db: Session,
    commune_id: int,
    request: Request,
) -> list[dict[str, Any]]:
    """Lấy người có thể được chọn theo phạm vi của tài khoản thao tác."""

    scope = lay_pham_vi_phan_cong(request)
    school_id = scope.get("school_id")
    role_code = scope["role_code"]

    filters = [
        "u.is_active = 1",
    ]

    if role_code == COMMUNE_ROLE_CODE:
        # Xã giao phiếu cho tài khoản đơn vị trường, không giao thẳng
        # cho tài khoản cá nhân giáo viên/CBQL để giữ đúng quy trình.
        filters.extend([
            "r.code = 'TRUONG'",
            "LOWER(u.username) NOT LIKE 'cbql.%'",
            "u.school_id IS NOT NULL",
            "s.commune_id = :commune_id",
            "s.is_active = 1",
        ])
    elif role_code == SCHOOL_ROLE_CODE:
        # Trường phân công tiếp cho giáo viên hoặc CBQL của chính trường,
        # không tự giao lại cho tài khoản đơn vị trường.
        filters.extend([
            "r.code IN ('TRUONG', 'GIAO_VIEN')",
            "(r.code = 'GIAO_VIEN' OR LOWER(u.username) LIKE 'cbql.%')",
            "u.commune_id = :commune_id",
        ])
    else:
        filters.extend([
            "r.code IN ('TRUONG', 'GIAO_VIEN')",
            "u.commune_id = :commune_id",
        ])
    parameters: dict[str, Any] = {
        "commune_id": commune_id,
    }

    if role_code == SCHOOL_ROLE_CODE:
        if school_id is None:
            return []
        filters.append("u.school_id = :school_id")
        parameters["school_id"] = int(school_id)

    rows = db.execute(
        text(
            f"""
            SELECT
                u.id,
                u.username,
                u.full_name,
                u.commune_id,
                u.school_id,
                r.code AS role_code,
                r.name AS role_name,
                s.code AS school_code,
                s.name AS school_name
            FROM users AS u
            JOIN roles AS r
                ON r.id = u.role_id
            LEFT JOIN schools AS s
                ON s.id = u.school_id
            WHERE {' AND '.join(filters)}
            ORDER BY
                CASE WHEN s.name IS NULL THEN 1 ELSE 0 END,
                s.name COLLATE NOCASE,
                CASE WHEN r.code = 'TRUONG' THEN 0 ELSE 1 END,
                u.full_name COLLATE NOCASE,
                u.id
            """
        ),
        parameters,
    ).mappings().all()

    return [dict(row) for row in rows]


def lay_danh_sach_truong_trong_xa_cho_phan_cong(
    *,
    db: Session,
    commune_id: int,
) -> list[dict[str, Any]]:
    """Lấy đủ trường trong xã và tài khoản đơn vị dùng để phân công.

    Danh mục trường phải lấy từ bảng ``schools`` thay vì suy ra từ danh
    sách tài khoản. Nhờ đó bộ lọc luôn hiện đủ trường trong xã, kể cả khi
    một trường chưa được cấp tài khoản đơn vị.
    """

    rows = db.execute(
        text(
            """
            SELECT
                s.id,
                s.code,
                s.name,
                s.commune_id,
                (
                    SELECT u.id
                    FROM users AS u
                    JOIN roles AS r
                        ON r.id = u.role_id
                    WHERE u.school_id = s.id
                      AND u.is_active = 1
                      AND r.code = 'TRUONG'
                      AND LOWER(u.username) NOT LIKE 'cbql.%'
                    ORDER BY
                        CASE
                            WHEN LOWER(u.username) LIKE 'truong_%'
                            THEN 0
                            ELSE 1
                        END,
                        u.id
                    LIMIT 1
                ) AS account_id,
                (
                    SELECT u.username
                    FROM users AS u
                    JOIN roles AS r
                        ON r.id = u.role_id
                    WHERE u.school_id = s.id
                      AND u.is_active = 1
                      AND r.code = 'TRUONG'
                      AND LOWER(u.username) NOT LIKE 'cbql.%'
                    ORDER BY
                        CASE
                            WHEN LOWER(u.username) LIKE 'truong_%'
                            THEN 0
                            ELSE 1
                        END,
                        u.id
                    LIMIT 1
                ) AS account_username,
                (
                    SELECT u.full_name
                    FROM users AS u
                    JOIN roles AS r
                        ON r.id = u.role_id
                    WHERE u.school_id = s.id
                      AND u.is_active = 1
                      AND r.code = 'TRUONG'
                      AND LOWER(u.username) NOT LIKE 'cbql.%'
                    ORDER BY
                        CASE
                            WHEN LOWER(u.username) LIKE 'truong_%'
                            THEN 0
                            ELSE 1
                        END,
                        u.id
                    LIMIT 1
                ) AS account_full_name
            FROM schools AS s
            WHERE s.commune_id = :commune_id
              AND s.is_active = 1
            ORDER BY s.name COLLATE NOCASE, s.code COLLATE NOCASE
            """
        ),
        {"commune_id": int(commune_id)},
    ).mappings().all()

    return [dict(row) for row in rows]


def lay_phan_cong_hien_tai(
    db: Session,
    survey_form_id: int,
) -> list[dict[str, Any]]:
    """Lấy danh sách người đã được phân công vào một phiếu."""

    rows = db.execute(
        text(
            """
            SELECT
                sfi.id AS assignment_id,
                sfi.user_id,
                sfi.order_number,
                sfi.is_primary,
                sfi.signed_at,
                sfi.notes,
                sfi.created_at,
                u.username,
                u.full_name,
                u.commune_id,
                u.school_id,
                r.code AS role_code,
                r.name AS role_name,
                s.code AS school_code,
                s.name AS school_name
            FROM survey_form_investigators AS sfi
            JOIN users AS u
                ON u.id = sfi.user_id
            JOIN roles AS r
                ON r.id = u.role_id
            LEFT JOIN schools AS s
                ON s.id = u.school_id
            WHERE sfi.survey_form_id = :survey_form_id
            ORDER BY
                sfi.is_primary DESC,
                sfi.order_number ASC,
                sfi.id ASC
            """
        ),
        {"survey_form_id": survey_form_id},
    ).mappings().all()

    return [dict(row) for row in rows]


def lay_ids_nguoi_dieu_tra_hop_le(
    *,
    db: Session,
    request: Request,
    commune_id: int,
    user_ids: list[int],
) -> set[int]:
    """Kiểm tra các tài khoản được chọn còn hoạt động và đúng phạm vi."""

    if not user_ids:
        return set()

    scope = lay_pham_vi_phan_cong(request)
    placeholders = ", ".join(
        f":user_id_{index}"
        for index in range(len(user_ids))
    )
    parameters: dict[str, Any] = {
        "commune_id": commune_id,
    }
    parameters.update(
        {
            f"user_id_{index}": user_id
            for index, user_id in enumerate(user_ids)
        }
    )

    scope_condition = "AND r.code IN ('TRUONG', 'GIAO_VIEN')"
    school_condition = ""
    commune_condition = "AND u.commune_id = :commune_id"

    if scope["role_code"] == COMMUNE_ROLE_CODE:
        scope_condition = (
            "AND r.code = 'TRUONG' "
            "AND LOWER(u.username) NOT LIKE 'cbql.%'"
        )
        commune_condition = (
            "AND u.school_id IS NOT NULL "
            "AND s.commune_id = :commune_id "
            "AND s.is_active = 1"
        )
    elif scope["role_code"] == SCHOOL_ROLE_CODE:
        school_id = scope.get("school_id")
        if school_id is None:
            return set()
        school_condition = "AND u.school_id = :school_id"
        scope_condition = (
            "AND r.code IN ('TRUONG', 'GIAO_VIEN') "
            "AND (r.code = 'GIAO_VIEN' "
            "OR LOWER(u.username) LIKE 'cbql.%')"
        )
        parameters["school_id"] = int(school_id)

    values = db.execute(
        text(
            f"""
            SELECT u.id
            FROM users AS u
            JOIN roles AS r
                ON r.id = u.role_id
            LEFT JOIN schools AS s
                ON s.id = u.school_id
            WHERE u.id IN ({placeholders})
              AND u.is_active = 1
              {commune_condition}
              {scope_condition}
              {school_condition}
            """
        ),
        parameters,
    ).scalars().all()

    return {int(value) for value in values}


def la_phieu_trong_pham_vi_phan_cong(
    *,
    db: Session,
    request: Request,
    survey_form: SurveyForm,
) -> bool:
    """Kiểm tra phiếu có nằm trong phạm vi được phép phân công không."""

    scope = lay_pham_vi_phan_cong(request)
    role_code = scope["role_code"]

    if is_admin_role(role_code):
        return True

    if role_code == COMMUNE_ROLE_CODE:
        commune_id = scope.get("commune_id")
        return (
            commune_id is not None
            and int(survey_form.survey_batch.commune_id)
            == int(commune_id)
        )

    if role_code == SCHOOL_ROLE_CODE:
        school_id = scope.get("school_id")
        if school_id is None:
            return False

        allowed = db.execute(
            text(
                """
                SELECT 1
                FROM survey_form_investigators AS sfi
                JOIN users AS u
                    ON u.id = sfi.user_id
                WHERE sfi.survey_form_id = :survey_form_id
                  AND u.school_id = :school_id
                  AND u.is_active = 1
                LIMIT 1
                """
            ),
            {
                "survey_form_id": survey_form.id,
                "school_id": int(school_id),
            },
        ).scalar()
        return allowed is not None

    return False


def xoa_phan_cong_trong_pham_vi(
    *,
    db: Session,
    request: Request,
    survey_form_id: int,
) -> None:
    """Xóa phân công toàn phiếu hoặc chỉ phần thuộc trường đang thao tác."""

    scope = lay_pham_vi_phan_cong(request)

    if scope["role_code"] == SCHOOL_ROLE_CODE:
        school_id = scope.get("school_id")
        if school_id is None:
            return
        db.execute(
            text(
                """
                DELETE FROM survey_form_investigators
                WHERE survey_form_id = :survey_form_id
                  AND user_id IN (
                      SELECT id
                      FROM users
                      WHERE school_id = :school_id
                  )
                """
            ),
            {
                "survey_form_id": survey_form_id,
                "school_id": int(school_id),
            },
        )
        return

    db.execute(
        text(
            """
            DELETE FROM survey_form_investigators
            WHERE survey_form_id = :survey_form_id
            """
        ),
        {"survey_form_id": survey_form_id},
    )


def chuan_hoa_thu_tu_phan_cong(
    *,
    db: Session,
    survey_form_id: int,
    preferred_primary_user_id: int | None = None,
) -> None:
    """Đánh lại thứ tự và bảo đảm toàn phiếu chỉ có một người chính."""

    rows = db.execute(
        text(
            """
            SELECT
                id,
                user_id,
                is_primary
            FROM survey_form_investigators
            WHERE survey_form_id = :survey_form_id
            ORDER BY
                is_primary DESC,
                order_number ASC,
                id ASC
            """
        ),
        {"survey_form_id": survey_form_id},
    ).mappings().all()

    if not rows:
        return

    user_ids = {int(row["user_id"]) for row in rows}
    primary_user_id = (
        int(preferred_primary_user_id)
        if preferred_primary_user_id in user_ids
        else None
    )

    if primary_user_id is None:
        primary_user_id = next(
            (
                int(row["user_id"])
                for row in rows
                if bool(row["is_primary"])
            ),
            int(rows[0]["user_id"]),
        )

    # Đặt thứ tự tạm âm để không va chạm ràng buộc duy nhất.
    for index, row in enumerate(rows, start=1):
        db.execute(
            text(
                """
                UPDATE survey_form_investigators
                SET order_number = :temporary_order,
                    is_primary = 0
                WHERE id = :assignment_id
                """
            ),
            {
                "temporary_order": -index,
                "assignment_id": int(row["id"]),
            },
        )

    ordered_rows = sorted(
        rows,
        key=lambda row: (
            0 if int(row["user_id"]) == primary_user_id else 1,
            int(row["id"]),
        ),
    )

    for index, row in enumerate(ordered_rows, start=1):
        user_id = int(row["user_id"])
        db.execute(
            text(
                """
                UPDATE survey_form_investigators
                SET order_number = :order_number,
                    is_primary = :is_primary
                WHERE id = :assignment_id
                """
            ),
            {
                "order_number": index,
                "is_primary": 1 if user_id == primary_user_id else 0,
                "assignment_id": int(row["id"]),
            },
        )


def cap_nhat_phan_cong_mot_phieu(
    *,
    db: Session,
    request: Request,
    survey_form: SurveyForm,
    selected_ids: list[int],
    primary_user_id: int | None,
    assignment_notes: str,
    mode: str,
    log_action: str,
) -> None:
    """Thêm, thay thế hoặc thu hồi phân công của một phiếu."""

    actor_user = lay_thong_tin_nguoi_dung(request)
    now_value = datetime.now().isoformat(
        sep=" ",
        timespec="seconds",
    )

    if mode in {"replace", "clear"}:
        xoa_phan_cong_trong_pham_vi(
            db=db,
            request=request,
            survey_form_id=survey_form.id,
        )

    if mode != "clear":
        existing_ids = {
            int(value)
            for value in db.execute(
                text(
                    """
                    SELECT user_id
                    FROM survey_form_investigators
                    WHERE survey_form_id = :survey_form_id
                    """
                ),
                {"survey_form_id": survey_form.id},
            ).scalars().all()
        }
        max_order = int(
            db.execute(
                text(
                    """
                    SELECT COALESCE(MAX(order_number), 0)
                    FROM survey_form_investigators
                    WHERE survey_form_id = :survey_form_id
                    """
                ),
                {"survey_form_id": survey_form.id},
            ).scalar()
            or 0
        )

        for index, user_id in enumerate(selected_ids, start=1):
            if user_id in existing_ids:
                db.execute(
                    text(
                        """
                        UPDATE survey_form_investigators
                        SET signed_at = :signed_at,
                            notes = :notes
                        WHERE survey_form_id = :survey_form_id
                          AND user_id = :user_id
                        """
                    ),
                    {
                        "signed_at": now_value,
                        "notes": assignment_notes or None,
                        "survey_form_id": survey_form.id,
                        "user_id": user_id,
                    },
                )
                continue

            db.execute(
                text(
                    """
                    INSERT INTO survey_form_investigators (
                        survey_form_id,
                        user_id,
                        order_number,
                        is_primary,
                        signed_at,
                        notes,
                        created_at
                    ) VALUES (
                        :survey_form_id,
                        :user_id,
                        :order_number,
                        0,
                        :signed_at,
                        :notes,
                        :created_at
                    )
                    """
                ),
                {
                    "survey_form_id": survey_form.id,
                    "user_id": user_id,
                    "order_number": max_order + 1000 + index,
                    "signed_at": now_value,
                    "notes": assignment_notes or None,
                    "created_at": now_value,
                },
            )

    chuan_hoa_thu_tu_phan_cong(
        db=db,
        survey_form_id=survey_form.id,
        preferred_primary_user_id=primary_user_id,
    )

    ghi_nhat_ky_phan_cong(
        db=db,
        survey_form_id=survey_form.id,
        action=log_action,
        actor_user=actor_user,
        target_user_ids=selected_ids,
        notes=assignment_notes,
    )


def hien_thi_trang_phan_cong(
    *,
    request: Request,
    db: Session,
    survey_form: SurveyForm,
    status: str | None = None,
    thong_bao_loi: str | None = None,
    status_code: int = 200,
):
    """Hiển thị trang phân công người điều tra cho một phiếu."""

    candidates = lay_danh_sach_nguoi_dieu_tra(
        db=db,
        commune_id=survey_form.survey_batch.commune_id,
        request=request,
    )
    assignments = lay_phan_cong_hien_tai(
        db=db,
        survey_form_id=survey_form.id,
    )

    selected_ids = {
        int(item["user_id"])
        for item in assignments
    }
    primary_user_id = next(
        (
            int(item["user_id"])
            for item in assignments
            if bool(item["is_primary"])
        ),
        None,
    )

    school_map: dict[int, dict[str, Any]] = {}
    role_counts = {
        "TRUONG": 0,
        "GIAO_VIEN": 0,
    }

    for candidate in candidates:
        role_code = str(candidate.get("role_code") or "")
        if role_code in role_counts:
            role_counts[role_code] += 1

        school_id = candidate.get("school_id")
        if school_id is None:
            continue

        school_id = int(school_id)
        school_map.setdefault(
            school_id,
            {
                "id": school_id,
                "code": candidate.get("school_code") or "",
                "name": candidate.get("school_name") or "",
            },
        )

    schools = sorted(
        school_map.values(),
        key=lambda item: str(item["name"]).casefold(),
    )

    assignment_notes = next(
        (
            str(item["notes"])
            for item in assignments
            if item.get("notes")
        ),
        "",
    )

    return templates.TemplateResponse(
        request=request,
        name="surveys/investigators.html",
        context={
            "nguoi_dung": request.scope.get("auth_user"),
            "batch": survey_form.survey_batch,
            "survey_form": survey_form,
            "household": survey_form.household,
            "candidates": candidates,
            "schools": schools,
            "assignments": assignments,
            "selected_ids": selected_ids,
            "primary_user_id": primary_user_id,
            "assignment_notes": assignment_notes,
            "role_counts": role_counts,
            "assignment_scope": lay_pham_vi_phan_cong(request),
            "latest_assignment_log": lay_nhat_ky_phan_cong_gan_nhat(
                db,
                survey_form.id,
            ),
            "thong_bao": STATUS_MESSAGES.get(status),
            "thong_bao_loi": thong_bao_loi,
        },
        status_code=status_code,
    )


def tao_url_danh_sach_doi_tuong(
    batch_id: int,
    household_id: int,
    page: int,
    q: str,
    residency_status: str,
) -> str:
    parameters: dict[str, str | int] = {
        "page": page,
    }

    if q:
        parameters["q"] = q

    if residency_status:
        parameters["residency_status"] = residency_status

    return (
        f"/dieu-tra/{batch_id}/ho-dan/"
        f"{household_id}/doi-tuong?"
        + urlencode(parameters)
    )


def hien_thi_trang_doi_tuong(
    *,
    request: Request,
    db: Session,
    survey_form: SurveyForm,
    q: str = "",
    residency_status: str = "",
    page: int = 1,
    status: str | None = None,
    thong_bao_loi: str | None = None,
    form_data: dict[str, Any] | None = None,
    status_code: int = 200,
):
    """Dùng chung khi mở trang và khi biểu mẫu có lỗi."""

    q = q.strip()[:100]

    if residency_status not in RESIDENCY_STATUS_LABELS:
        residency_status = ""

    filters = [
        SurveyPerson.household_id == survey_form.household_id,
        SurveyPerson.is_active.is_(True),
    ]

    if q:
        search_value = f"%{q}%"
        filters.append(
            or_(
                SurveyPerson.code.ilike(search_value),
                SurveyPerson.full_name.ilike(search_value),
                SurveyPerson.personal_id.ilike(search_value),
                SurveyPerson.ministry_student_code.ilike(search_value),
            )
        )

    if residency_status:
        filters.append(
            SurveyPerson.residency_status == residency_status
        )

    total_records = db.scalar(
        select(func.count(SurveyPerson.id)).where(*filters)
    )
    total_records = int(total_records or 0)

    total_pages = max(
        1,
        ceil(total_records / PERSON_PAGE_SIZE),
    )

    page = max(1, page)
    page = min(page, total_pages)
    offset = (page - 1) * PERSON_PAGE_SIZE

    people = db.scalars(
        select(SurveyPerson)
        .options(selectinload(SurveyPerson.student))
        .where(*filters)
        .order_by(
            SurveyPerson.date_of_birth.asc(),
            SurveyPerson.full_name.asc(),
            SurveyPerson.id.asc(),
        )
        .offset(offset)
        .limit(PERSON_PAGE_SIZE)
    ).all()

    start_page = max(1, page - 2)
    end_page = min(total_pages, page + 2)

    page_links = [
        {
            "number": page_number,
            "active": page_number == page,
            "url": tao_url_danh_sach_doi_tuong(
                batch_id=survey_form.survey_batch_id,
                household_id=survey_form.household_id,
                page=page_number,
                q=q,
                residency_status=residency_status,
            ),
        }
        for page_number in range(start_page, end_page + 1)
    ]

    previous_url = None
    if page > 1:
        previous_url = tao_url_danh_sach_doi_tuong(
            batch_id=survey_form.survey_batch_id,
            household_id=survey_form.household_id,
            page=page - 1,
            q=q,
            residency_status=residency_status,
        )

    next_url = None
    if page < total_pages:
        next_url = tao_url_danh_sach_doi_tuong(
            batch_id=survey_form.survey_batch_id,
            household_id=survey_form.household_id,
            page=page + 1,
            q=q,
            residency_status=residency_status,
        )

    if form_data is None:
        form_data = {
            "student_id": None,
            "full_name": "",
            "date_of_birth": "",
            "gender": "",
            "ethnic_group": "",
            "relationship_to_head": "",
            "personal_id": "",
            "ministry_student_code": "",
            "permanent_address": survey_form.household.address,
            "current_address": survey_form.household.address,
            "residency_status": "THUONG_TRU",
            "special_circumstances": "",
            "notes": "",
        }

    selected_student = None
    selected_student_id = form_data.get("student_id")
    if selected_student_id:
        selected_student = db.get(Student, int(selected_student_id))

    active_household_filter = [
        SurveyPerson.household_id == survey_form.household_id,
        SurveyPerson.is_active.is_(True),
    ]
    household_person_total = int(
        db.scalar(
            select(func.count(SurveyPerson.id)).where(
                *active_household_filter
            )
        )
        or 0
    )
    linked_student_count = int(
        db.scalar(
            select(func.count(SurveyPerson.id)).where(
                *active_household_filter,
                SurveyPerson.student_id.is_not(None),
            )
        )
        or 0
    )
    missing_personal_id_count = int(
        db.scalar(
            select(func.count(SurveyPerson.id)).where(
                *active_household_filter,
                or_(
                    SurveyPerson.personal_id.is_(None),
                    func.trim(SurveyPerson.personal_id) == "",
                ),
            )
        )
        or 0
    )

    active_household_person_ids = select(SurveyPerson.id).where(
        *active_household_filter
    )
    current_year_person_ids = set(
        db.scalars(
            select(SurveyPersonYearRecord.survey_person_id).where(
                SurveyPersonYearRecord.survey_form_id == survey_form.id,
                SurveyPersonYearRecord.school_year_id
                == survey_form.survey_batch.school_year_id,
                SurveyPersonYearRecord.survey_person_id.in_(
                    active_household_person_ids
                ),
            )
        ).all()
    )
    missing_current_year_count = max(
        0,
        household_person_total - len(current_year_person_ids),
    )

    person_ids = [item.id for item in people]
    year_record_counts: dict[int, int] = {}
    if person_ids:
        year_count_rows = db.execute(
            select(
                SurveyPersonYearRecord.survey_person_id,
                func.count(SurveyPersonYearRecord.id),
            )
            .where(
                SurveyPersonYearRecord.survey_form_id == survey_form.id,
                SurveyPersonYearRecord.survey_person_id.in_(person_ids),
            )
            .group_by(SurveyPersonYearRecord.survey_person_id)
        ).all()
        year_record_counts = {
            int(person_id): int(record_count)
            for person_id, record_count in year_count_rows
        }

    user = lay_thong_tin_nguoi_dung(request)
    can_edit_data = can_edit_survey_data(user.get("role_code"))

    return templates.TemplateResponse(
        request=request,
        name="surveys/people.html",
        context={
            "nguoi_dung": user,
            "can_edit_data": can_edit_data,
            "survey_form": survey_form,
            "batch": survey_form.survey_batch,
            "household": survey_form.household,
            "people": people,
            "selected_student": selected_student,
            "year_record_counts": year_record_counts,
            "household_person_total": household_person_total,
            "linked_student_count": linked_student_count,
            "missing_personal_id_count": missing_personal_id_count,
            "missing_current_year_count": missing_current_year_count,
            "q": q,
            "selected_residency_status": residency_status,
            "residency_status_labels": RESIDENCY_STATUS_LABELS,
            "page": page,
            "page_size": PERSON_PAGE_SIZE,
            "total_records": total_records,
            "total_pages": total_pages,
            "page_links": page_links,
            "previous_url": previous_url,
            "next_url": next_url,
            "thong_bao": STATUS_MESSAGES.get(status),
            "thong_bao_loi": thong_bao_loi,
            "form_data": form_data,
        },
        status_code=status_code,
    )


# =========================================================
# QUẢN LÝ ĐỢT ĐIỀU TRA
# =========================================================

@router.get("", response_class=HTMLResponse)
def danh_sach_dot_dieu_tra(
    request: Request,
    school_year_id: str = "",
    commune_id: str = "",
    survey_status: str = "",
    status: str | None = None,
    db: Session = Depends(get_db),
):
    # Các ô lọc HTML gửi chuỗi rỗng khi người dùng chọn
    # “Tất cả”. Không để FastAPI ép chuỗi rỗng thành int vì sẽ
    # trả lỗi 422 trước khi hàm này được chạy.
    selected_school_year_id = chuyen_id_tuy_chon(school_year_id)
    selected_commune_id = chuyen_id_tuy_chon(commune_id)

    school_years, communes = lay_du_lieu_danh_muc(db)
    user = lay_thong_tin_nguoi_dung(request)
    role_code = str(user.get("role_code") or "")

    # Giữ nhiệm vụ đã giao trong danh sách kể cả khi phiếu đã hoàn thành
    # hoặc đợt đã khóa. Chỉ khôi phục phân công hợp lệ từ nhật ký,
    # không tạo quyền mới và không thay đổi bố cục giao diện.
    if role_code == "TRUONG" and user.get("school_id") is not None:
        dong_bo_danh_sach_dot_truong_tu_nhat_ky(
            db=db,
            school_id=int(user["school_id"]),
        )
    elif role_code == "GIAO_VIEN" and user.get("id") is not None:
        dong_bo_phan_cong_giao_vien_hien_tai_tu_nhat_ky(
            db=db,
            user_id=int(user["id"]),
            school_id=(
                int(user["school_id"])
                if user.get("school_id") is not None
                else None
            ),
        )

    if role_code not in PROVINCE_READ_ROLE_CODES:
        user_commune_id = user.get("commune_id")
        communes = [
            item
            for item in communes
            if (
                user_commune_id is not None
                and item.id == int(user_commune_id)
            )
        ]

        selected_commune_id = (
            int(user_commune_id)
            if user_commune_id is not None
            else None
        )

    valid_year_ids = {item.id for item in school_years}
    valid_commune_ids = {item.id for item in communes}

    if selected_school_year_id not in valid_year_ids:
        selected_school_year_id = None

    if selected_commune_id not in valid_commune_ids:
        selected_commune_id = None

    if survey_status not in BATCH_STATUS_LABELS:
        survey_status = ""

    filters = tao_bo_loc_dot_theo_nguoi_dung(request)

    if selected_school_year_id is not None:
        filters.append(
            SurveyBatch.school_year_id == selected_school_year_id
        )

    # === BAI_13B_10_V3_7_SKIP_COMMUNE_FILTER_FOR_SCHOOL_TEACHER_START ===
    # Xã/phường vẫn lọc theo địa bàn.
    # Riêng Trường/Giáo viên đã được khóa phạm vi bằng
    # tao_bo_loc_dot_theo_nguoi_dung() -> survey_form_investigators,
    # nên không ép thêm SurveyBatch.commune_id.
    if (
        selected_commune_id is not None
        and role_code not in {SCHOOL_ROLE_CODE, TEACHER_ROLE_CODE}
    ):
        filters.append(
            SurveyBatch.commune_id == selected_commune_id
        )
    # === BAI_13B_10_V3_7_SKIP_COMMUNE_FILTER_FOR_SCHOOL_TEACHER_END ===
    # === BAI_13B_11_5_1_FIX_GLUE_STATUS_IF_START ===
    if survey_status in BATCH_STATUS_LABELS:
        filters.append(
            SurveyBatch.status == survey_status
        )
    # === BAI_13B_11_5_1_FIX_GLUE_STATUS_IF_END ===

    statement = (
        select(SurveyBatch)
        .options(
            selectinload(SurveyBatch.school_year),
            selectinload(SurveyBatch.commune),
        )
        .where(*filters)
        .order_by(
            SurveyBatch.created_at.desc(),
            SurveyBatch.id.desc(),
        )
    )

    survey_batches = db.scalars(statement).all()

    batch_visible_counts: dict[int, int] = {}

    if survey_batches:
        batch_ids = [item.id for item in survey_batches]
        form_scope_filters = tao_bo_loc_phieu_theo_nguoi_dung(
            request
        )

        count_rows = db.execute(
            select(
                SurveyForm.survey_batch_id,
                func.count(SurveyForm.id),
            )
            .where(
                SurveyForm.survey_batch_id.in_(batch_ids),
                *form_scope_filters,
            )
            .group_by(SurveyForm.survey_batch_id)
        ).all()

        batch_visible_counts = {
            int(batch_id): int(count_value or 0)
            for batch_id, count_value in count_rows
        }

    permissions = tao_thong_tin_quyen_giao_dien(request)

    return templates.TemplateResponse(
        request=request,
        name="surveys/index.html",
        context={
            "nguoi_dung": user,
            "school_years": school_years,
            "communes": communes,
            "survey_batches": survey_batches,
            "batch_visible_counts": batch_visible_counts,
            "selected_school_year_id": selected_school_year_id,
            "selected_commune_id": selected_commune_id,
            "selected_status": survey_status,
            "status_labels": BATCH_STATUS_LABELS,
            "thong_bao": STATUS_MESSAGES.get(status),
            "today": date.today().isoformat(),
            **permissions,
        },
    )


@router.post("/them")
def them_dot_dieu_tra(
    request: Request,
    school_year_id: Annotated[int, Form()],
    commune_id: Annotated[int, Form()],
    name: Annotated[str, Form()],
    start_date: Annotated[str, Form()] = "",
    end_date: Annotated[str, Form()] = "",
    notes: Annotated[str, Form()] = "",
    db: Session = Depends(get_db),
):
    # Quy trình chính thức: Sở khởi tạo đồng loạt toàn tỉnh.
    # Không cho tạo riêng lẻ từng xã để tránh trùng và lệch năm học.
    return RedirectResponse(
        url="/dieu-tra/khoi-tao-nam-hoc-toan-tinh",
        status_code=303,
    )

    errors: list[str] = []

    name = chuan_hoa_van_ban(name)
    notes = notes.strip()

    if not name:
        errors.append(
            "Tên đợt điều tra không được để trống."
        )

    if len(name) > 300:
        errors.append(
            "Tên đợt điều tra dài quá 300 ký tự."
        )

    school_year = db.get(
        SchoolYear,
        school_year_id,
    )

    if school_year is None or not school_year.is_active:
        errors.append("Năm học được chọn không hợp lệ.")

    commune = db.get(
        Commune,
        commune_id,
    )

    if commune is None or not commune.is_active:
        errors.append("Xã được chọn không hợp lệ.")

    parsed_start_date, start_error = chuyen_ngay(
        start_date,
        "Ngày bắt đầu",
        bat_buoc=True,
    )

    if start_error:
        errors.append(start_error)

    parsed_end_date, end_error = chuyen_ngay(
        end_date,
        "Ngày kết thúc",
        bat_buoc=False,
    )

    if end_error:
        errors.append(end_error)

    if (
        parsed_start_date is not None
        and parsed_end_date is not None
        and parsed_end_date < parsed_start_date
    ):
        errors.append(
            "Ngày kết thúc không được trước ngày bắt đầu."
        )

    if errors:
        school_years, communes = lay_du_lieu_danh_muc(db)

        survey_batches = db.scalars(
            select(SurveyBatch)
            .options(
                selectinload(SurveyBatch.school_year),
                selectinload(SurveyBatch.commune),
                selectinload(SurveyBatch.survey_forms),
            )
            .order_by(
                SurveyBatch.created_at.desc(),
                SurveyBatch.id.desc(),
            )
        ).all()

        batch_visible_counts = {
            item.id: len(item.survey_forms)
            for item in survey_batches
        }
        permissions = tao_thong_tin_quyen_giao_dien(request)

        return templates.TemplateResponse(
            request=request,
            name="surveys/index.html",
            context={
                "nguoi_dung": request.scope.get("auth_user"),
                "school_years": school_years,
                "communes": communes,
                "survey_batches": survey_batches,
                "batch_visible_counts": batch_visible_counts,
                "selected_school_year_id": school_year_id,
                "selected_commune_id": commune_id,
                "selected_status": "",
                "status_labels": BATCH_STATUS_LABELS,
                "thong_bao_loi": " ".join(errors),
                "form_data": {
                    "school_year_id": school_year_id,
                    "commune_id": commune_id,
                    "name": name,
                    "start_date": start_date,
                    "end_date": end_date,
                    "notes": notes,
                },
                "today": date.today().isoformat(),
                **permissions,
            },
            status_code=400,
        )

    user = request.scope.get("auth_user") or {}

    batch = SurveyBatch(
        code=tao_ma_dot_dieu_tra(
            db=db,
            commune=commune,
            school_year=school_year,
        ),
        name=name,
        school_year_id=school_year_id,
        commune_id=commune_id,
        status="CHUAN_BI",
        start_date=parsed_start_date,
        end_date=parsed_end_date,
        created_by_user_id=user.get("id"),
        notes=notes or None,
    )

    db.add(batch)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()

        return RedirectResponse(
            url="/dieu-tra",
            status_code=303,
        )

    return RedirectResponse(
        url="/dieu-tra?status=created",
        status_code=303,
    )


# =========================================================
# QUẢN LÝ HỘ GIA ĐÌNH TRONG MỘT ĐỢT ĐIỀU TRA
# =========================================================

@router.get(
    "/{batch_id}/ho-dan",
    response_class=HTMLResponse,
)
def danh_sach_ho_dan(
    batch_id: int,
    request: Request,
    q: str = "",
    hamlet: str = "",
    form_status: str = "",
    investigator_id: int = 0,
    assignment_status: str = "",
    object_filter: str = "",
    page_size: int = HOUSEHOLD_PAGE_SIZE,
    sort: str = "hamlet",
    page: int = 1,
    status: str | None = None,
    db: Session = Depends(get_db),
):
    batch = lay_dot_dieu_tra(db, batch_id)

    if batch is None:
        return RedirectResponse(
            url="/dieu-tra",
            status_code=303,
        )

    user = lay_thong_tin_nguoi_dung(request)
    role_code = normalize_role_code(user.get("role_code"))
    form_scope_filters = tao_bo_loc_phieu_theo_nguoi_dung(
        request
    )

    school_teacher_assignment = None
    if role_code == SCHOOL_ROLE_CODE and user.get("school_id") is not None:
        school_teacher_assignment = SurveyForm.investigators.any(
            SurveyFormInvestigator.user.has(
                and_(
                    User.school_id == int(user["school_id"]),
                    User.role.has(code=TEACHER_ROLE_CODE),
                )
            )
        )

    q = q.strip()[:100]
    hamlet = chuan_hoa_van_ban(hamlet)[:200]

    if form_status not in FORM_STATUS_LABELS:
        form_status = ""

    if assignment_status not in {"assigned", "unassigned"}:
        assignment_status = ""

    # === BATCH25_OBJECT_FILTER_BACKEND ===
    object_filter = str(object_filter or "").strip().upper()
    object_filter_labels = {
        "": "Tất cả đối tượng",
        "XMC": "Xóa mù chữ (15-60 tuổi)",
        "MN": "Mầm non (0-5 tuổi)",
        "TH": "Tiểu học (6-14 tuổi)",
        "THCS": "THCS (11-18 tuổi)",
        "KHUYET_TAT": "Khuyết tật",
    }
    if object_filter not in object_filter_labels:
        object_filter = ""
    # === END BATCH25_OBJECT_FILTER_BACKEND ===

    if page_size not in HOUSEHOLD_PAGE_SIZE_OPTIONS:
        page_size = HOUSEHOLD_PAGE_SIZE

    if sort not in HOUSEHOLD_SORT_OPTIONS:
        sort = "hamlet"

    try:
        investigator_id = int(investigator_id or 0)
    except (TypeError, ValueError):
        investigator_id = 0

    filters = [
        SurveyForm.survey_batch_id == batch.id,
        *form_scope_filters,
    ]

    if q:
        search_value = f"%{q}%"

        filters.append(
            or_(
                SurveyForm.form_number.ilike(search_value),
                Household.code.ilike(search_value),
                Household.head_name.ilike(search_value),
                Household.address.ilike(search_value),
                Household.phone.ilike(search_value),
                Household.hamlet_name.ilike(search_value),
                Household.people.any(
                    and_(
                        SurveyPerson.is_active.is_(True),
                        or_(
                            SurveyPerson.code.ilike(search_value),
                            SurveyPerson.full_name.ilike(search_value),
                            SurveyPerson.personal_id.ilike(search_value),
                            SurveyPerson.citizen_id.ilike(search_value),
                            SurveyPerson.ministry_student_code.ilike(
                                search_value
                            ),
                        ),
                    )
                ),
            )
        )

    if hamlet:
        filters.append(
            Household.hamlet_name == hamlet
        )

    if form_status:
        filters.append(
            SurveyForm.status == form_status
        )

    if investigator_id > 0:
        filters.append(
            SurveyForm.investigators.any(
                SurveyFormInvestigator.user_id == investigator_id
            )
        )

    if assignment_status == "assigned":
        filters.append(
            school_teacher_assignment
            if school_teacher_assignment is not None
            else SurveyForm.investigators.any()
        )
    elif assignment_status == "unassigned":
        filters.append(
            ~school_teacher_assignment
            if school_teacher_assignment is not None
            else ~SurveyForm.investigators.any()
        )

    # === BATCH25_OBJECT_FILTER_BACKEND_APPLY ===
    if object_filter:
        sy = db.get(SchoolYear, int(batch.school_year_id))
        try:
            ref_year = int(str(sy.code).split("-")[0])
        except (AttributeError, TypeError, ValueError):
            ref_year = date.today().year

        age_ranges = {
            "MN": (0, 5),
            "TH": (6, 14),
            "THCS": (11, 18),
            "XMC": (15, 60),
        }

        if object_filter in age_ranges:
            min_age, max_age = age_ranges[object_filter]
            birth_from = date(ref_year - max_age, 1, 1)
            birth_to = date(ref_year - min_age, 12, 31)
            filters.append(
                Household.people.any(
                    and_(
                        SurveyPerson.is_active.is_(True),
                        SurveyPerson.date_of_birth.is_not(None),
                        SurveyPerson.date_of_birth >= birth_from,
                        SurveyPerson.date_of_birth <= birth_to,
                    )
                )
            )
        elif object_filter == "KHUYET_TAT":
            disabled_ids = select(SurveyPersonYearRecord.survey_person_id).where(
                SurveyPersonYearRecord.school_year_id == batch.school_year_id,
                SurveyPersonYearRecord.disability_status == "CO_KHUYET_TAT",
            )
            filters.append(
                Household.people.any(
                    and_(
                        SurveyPerson.is_active.is_(True),
                        SurveyPerson.id.in_(disabled_ids),
                    )
                )
            )
    # === END BATCH25_OBJECT_FILTER_BACKEND_APPLY ===

    total_records = db.scalar(
        select(func.count(SurveyForm.id))
        .join(
            Household,
            Household.id == SurveyForm.household_id,
        )
        .where(*filters)
    )

    total_records = int(total_records or 0)

    total_pages = max(
        1,
        ceil(total_records / page_size),
    )

    page = max(1, page)
    page = min(page, total_pages)

    offset = (
        page - 1
    ) * page_size

    if sort == "updated_desc":
        order_by_fields = (
            SurveyForm.updated_at.desc(),
            Household.updated_at.desc(),
            SurveyForm.id.desc(),
        )
    elif sort == "head_name":
        order_by_fields = (
            Household.head_name.asc(),
            Household.hamlet_name.asc(),
            SurveyForm.id.asc(),
        )
    elif sort == "status":
        order_by_fields = (
            SurveyForm.status.asc(),
            Household.hamlet_name.asc(),
            Household.head_name.asc(),
            SurveyForm.id.asc(),
        )
    else:
        order_by_fields = (
            Household.hamlet_name.asc(),
            Household.head_name.asc(),
            SurveyForm.id.asc(),
        )

    survey_forms = db.scalars(
        select(SurveyForm)
        .join(
            Household,
            Household.id == SurveyForm.household_id,
        )
        .options(
            selectinload(SurveyForm.household)
            .selectinload(Household.people),
            selectinload(SurveyForm.investigators),
            with_loader_criteria(
                SurveyPerson,
                SurveyPerson.is_active.is_(True),
                include_aliases=True,
            ),
        )
        .where(*filters)
        .order_by(*order_by_fields)
        .offset(offset)
        .limit(page_size)
    ).all()

    investigator_summaries: dict[int, list[dict[str, Any]]] = {}

    if survey_forms:
        form_ids = [int(item.id) for item in survey_forms]
        placeholders = ", ".join(
            f":form_id_{index}"
            for index in range(len(form_ids))
        )
        parameters = {
            f"form_id_{index}": form_id
            for index, form_id in enumerate(form_ids)
        }

        assignment_rows = db.execute(
            text(
                f"""
                SELECT
                    sfi.survey_form_id,
                    sfi.user_id,
                    sfi.is_primary,
                    sfi.order_number,
                    u.full_name,
                    u.username,
                    r.name AS role_name,
                    s.name AS school_name
                FROM survey_form_investigators AS sfi
                JOIN users AS u
                    ON u.id = sfi.user_id
                JOIN roles AS r
                    ON r.id = u.role_id
                LEFT JOIN schools AS s
                    ON s.id = u.school_id
                WHERE sfi.survey_form_id IN ({placeholders})
                ORDER BY
                    sfi.survey_form_id,
                    sfi.is_primary DESC,
                    sfi.order_number,
                    sfi.id
                """
            ),
            parameters,
        ).mappings().all()

        for row in assignment_rows:
            form_id = int(row["survey_form_id"])
            investigator_summaries.setdefault(
                form_id,
                [],
            ).append(dict(row))

    assigned_form_count = int(
        db.scalar(
            select(func.count(SurveyForm.id)).where(
                SurveyForm.survey_batch_id == batch.id,
                *form_scope_filters,
                (
                    school_teacher_assignment
                    if school_teacher_assignment is not None
                    else SurveyForm.investigators.any()
                ),
            )
        )
        or 0
    )

    hamlet_names = db.scalars(
        select(Household.hamlet_name)
        .join(
            SurveyForm,
            SurveyForm.household_id == Household.id,
        )
        .where(
            SurveyForm.survey_batch_id == batch.id,
            *form_scope_filters,
            Household.hamlet_name.is_not(None),
            Household.hamlet_name != "",
        )
        .distinct()
        .order_by(Household.hamlet_name.asc())
    ).all()

    investigator_rows = db.execute(
        select(
            User.id.label("id"),
            User.full_name.label("full_name"),
            User.username.label("username"),
            School.name.label("school_name"),
        )
        .join(
            SurveyFormInvestigator,
            SurveyFormInvestigator.user_id == User.id,
        )
        .join(
            SurveyForm,
            SurveyForm.id == SurveyFormInvestigator.survey_form_id,
        )
        .outerjoin(
            School,
            School.id == User.school_id,
        )
        .where(
            SurveyForm.survey_batch_id == batch.id,
            *form_scope_filters,
            User.is_active.is_(True),
        )
        .distinct()
        .order_by(
            School.name.asc(),
            User.full_name.asc(),
            User.username.asc(),
        )
    ).mappings().all()
    investigator_options = [dict(row) for row in investigator_rows]

    status_rows = db.execute(
        select(
            SurveyForm.status,
            func.count(SurveyForm.id),
        )
        .where(
            SurveyForm.survey_batch_id == batch.id,
            *form_scope_filters,
        )
        .group_by(SurveyForm.status)
    ).all()

    status_counts = {
        code: 0
        for code in FORM_STATUS_LABELS
    }

    for status_code, count_value in status_rows:
        status_counts[status_code] = int(count_value or 0)

    batch_total_records = sum(status_counts.values())
    unassigned_form_count = max(
        0,
        batch_total_records - assigned_form_count,
    )
    completed_records = status_counts.get("DA_HOAN_THANH", 0)
    progress_percent = (
        round(completed_records * 100 / batch_total_records)
        if batch_total_records
        else 0
    )

    visible_people_count = int(
        db.scalar(
            select(func.count(func.distinct(SurveyPerson.id)))
            .join(
                Household,
                Household.id == SurveyPerson.household_id,
            )
            .join(
                SurveyForm,
                SurveyForm.household_id == Household.id,
            )
            .where(
                SurveyForm.survey_batch_id == batch.id,
                *form_scope_filters,
                SurveyPerson.is_active.is_(True),
            )
        )
        or 0
    )

    start_page = max(1, page - 2)
    end_page = min(total_pages, page + 2)

    page_links = [
        {
            "number": page_number,
            "active": page_number == page,
            "url": tao_url_danh_sach_ho(
                batch_id=batch.id,
                page=page_number,
                q=q,
                hamlet=hamlet,
                form_status=form_status,
                investigator_id=investigator_id,
                assignment_status=assignment_status,
                object_filter=object_filter,
                page_size=page_size,
                sort=sort,
            ),
        }
        for page_number in range(
            start_page,
            end_page + 1,
        )
    ]

    previous_url = None

    if page > 1:
        previous_url = tao_url_danh_sach_ho(
            batch_id=batch.id,
            page=page - 1,
            q=q,
            hamlet=hamlet,
            form_status=form_status,
            investigator_id=investigator_id,
            assignment_status=assignment_status,
            object_filter=object_filter,
            page_size=page_size,
            sort=sort,
        )

    next_url = None

    if page < total_pages:
        next_url = tao_url_danh_sach_ho(
            batch_id=batch.id,
            page=page + 1,
            q=q,
            hamlet=hamlet,
            form_status=form_status,
            investigator_id=investigator_id,
            assignment_status=assignment_status,
            object_filter=object_filter,
            page_size=page_size,
            sort=sort,
        )

    permissions = tao_thong_tin_quyen_giao_dien(request)
    has_filters = any((
        q,
        hamlet,
        form_status,
        investigator_id > 0,
        assignment_status,
        object_filter,
    ))

    return templates.TemplateResponse(
        request=request,
        name="surveys/households.html",
        context={
            "nguoi_dung": user,
            "batch": batch,
            "survey_forms": survey_forms,
            "investigator_summaries": investigator_summaries,
            "investigator_options": investigator_options,
            "assigned_form_count": assigned_form_count,
            "unassigned_form_count": unassigned_form_count,
            "hamlet_names": hamlet_names,
            "q": q,
            "selected_hamlet": hamlet,
            "selected_form_status": form_status,
            "selected_investigator_id": investigator_id,
            "selected_assignment_status": assignment_status,
            "selected_object_filter": object_filter,
            "object_filter_labels": object_filter_labels,
            "selected_page_size": page_size,
            "selected_sort": sort,
            "page_size_options": HOUSEHOLD_PAGE_SIZE_OPTIONS,
            "sort_options": HOUSEHOLD_SORT_OPTIONS,
            "has_filters": has_filters,
            "status_counts": status_counts,
            "batch_total_records": batch_total_records,
            "visible_people_count": visible_people_count,
            "progress_percent": progress_percent,
            "page": page,
            "page_size": page_size,
            "total_records": total_records,
            "total_pages": total_pages,
            "page_links": page_links,
            "previous_url": previous_url,
            "next_url": next_url,
            "form_status_labels": FORM_STATUS_LABELS,
            "thong_bao": STATUS_MESSAGES.get(status),
            **permissions,
        },
    )



# =========================================================
# PHÂN CÔNG NGƯỜI ĐIỀU TRA
# =========================================================

BULK_ASSIGNMENT_ERROR_MESSAGES = {
    "no_existing_assignment": (
        "Phiếu chưa có phân công phù hợp để giao tự động. Nếu cần thay đổi, hãy chọn trường hoặc giáo viên mới."
    ),
    "no_forms": "Bạn cần chọn ít nhất một phiếu để thực hiện.",
    "no_investigators": (
        "Bạn cần chọn ít nhất một đơn vị hoặc người thực hiện khi giao mới, "
        "giao lại hoặc bổ sung phối hợp."
    ),
    "invalid_forms": (
        "Danh sách có phiếu nằm ngoài phạm vi được phép. "
        "Hãy tải lại trang và chọn lại."
    ),
    "invalid_investigators": (
        "Danh sách có tài khoản không còn hoạt động hoặc ngoài phạm vi."
    ),
    "invalid_assignment_level": (
        "Tài khoản không có quyền thực hiện loại phân công này."
    ),
    "save_failed": (
        "Không thể lưu phân công. Dữ liệu cũ vẫn được giữ nguyên."
    ),
}


def duong_dan_phan_cong_theo_cap(
    batch_id: int,
    assignment_level: str,
) -> str:
    if assignment_level == "teacher":
        return f"/dieu-tra/{batch_id}/giao-phieu-giao-vien"
    return f"/dieu-tra/{batch_id}/giao-phieu-truong"


def tao_url_phan_cong_hang_loat(
    *,
    batch_id: int,
    page: int,
    q: str,
    hamlet: str,
    assignment_status: str,
    investigator_id: int,
    school_id: int,
    page_size: int,
    assignment_level: str = "school",
) -> str:
    parameters: dict[str, str | int] = {
        "page": page,
        "page_size": page_size,
    }
    if q:
        parameters["q"] = q
    if hamlet:
        parameters["hamlet"] = hamlet
    if assignment_status:
        parameters["assignment_status"] = assignment_status
    if investigator_id > 0:
        parameters["investigator_id"] = investigator_id
    if school_id > 0:
        parameters["school_id"] = school_id

    return (
        duong_dan_phan_cong_theo_cap(batch_id, assignment_level)
        + "?"
        + urlencode(parameters)
    )


def dieu_kien_phieu_da_giao_truong(
    school_id: int | None = None,
) -> Any:
    user_conditions: list[Any] = [
        User.role.has(code=SCHOOL_ROLE_CODE),
        ~func.lower(User.username).like("cbql.%"),
        User.school_id.is_not(None),
    ]
    if school_id is not None:
        user_conditions.append(User.school_id == int(school_id))

    return SurveyForm.investigators.any(
        SurveyFormInvestigator.user.has(and_(*user_conditions))
    )


def dieu_kien_phieu_da_giao_nhan_su_truong(
    school_id: int,
) -> Any:
    return SurveyForm.investigators.any(
        SurveyFormInvestigator.user.has(
            and_(
                User.school_id == int(school_id),
                or_(
                    User.role.has(code=TEACHER_ROLE_CODE),
                    and_(
                        User.role.has(code=SCHOOL_ROLE_CODE),
                        func.lower(User.username).like("cbql.%"),
                    ),
                ),
            )
        )
    )


def co_quyen_phan_cong_theo_cap(
    *,
    scope: dict[str, Any],
    batch: SurveyBatch,
    assignment_level: str,
) -> bool:
    role_code = scope["role_code"]

    if assignment_level == "school":
        if is_admin_role(role_code):
            return True
        return (
            role_code == COMMUNE_ROLE_CODE
            and scope.get("commune_id") is not None
            and int(scope["commune_id"]) == int(batch.commune_id)
        )

    if assignment_level == "teacher":
        return (
            role_code == SCHOOL_ROLE_CODE
            and scope.get("school_id") is not None
        )

    return False


def lay_tom_tat_phan_cong_nhieu_phieu(
    db: Session,
    form_ids: list[int],
) -> tuple[
    dict[int, list[dict[str, Any]]],
    dict[int, dict[str, Any]],
]:
    """Lấy phân công hai cấp và nhật ký gần nhất cho nhiều phiếu."""

    assignments: dict[int, list[dict[str, Any]]] = {}
    latest_logs: dict[int, dict[str, Any]] = {}

    if not form_ids:
        return assignments, latest_logs

    placeholders = ", ".join(
        f":form_id_{index}"
        for index in range(len(form_ids))
    )
    parameters = {
        f"form_id_{index}": form_id
        for index, form_id in enumerate(form_ids)
    }

    rows = db.execute(
        text(
            f"""
            SELECT
                sfi.survey_form_id,
                sfi.user_id,
                sfi.is_primary,
                sfi.order_number,
                sfi.signed_at,
                u.full_name,
                u.username,
                u.school_id,
                r.code AS role_code,
                r.name AS role_name,
                s.code AS school_code,
                s.name AS school_name,
                CASE
                    WHEN r.code = 'TRUONG'
                     AND LOWER(u.username) NOT LIKE 'cbql.%'
                    THEN 'school'
                    ELSE 'teacher'
                END AS assignment_level
            FROM survey_form_investigators AS sfi
            JOIN users AS u
                ON u.id = sfi.user_id
            JOIN roles AS r
                ON r.id = u.role_id
            LEFT JOIN schools AS s
                ON s.id = u.school_id
            WHERE sfi.survey_form_id IN ({placeholders})
            ORDER BY
                sfi.survey_form_id,
                CASE
                    WHEN r.code = 'TRUONG'
                     AND LOWER(u.username) NOT LIKE 'cbql.%'
                    THEN 0 ELSE 1
                END,
                sfi.is_primary DESC,
                sfi.order_number,
                sfi.id
            """
        ),
        parameters,
    ).mappings().all()

    for row in rows:
        form_id = int(row["survey_form_id"])
        assignments.setdefault(form_id, []).append(dict(row))

    dam_bao_bang_nhat_ky_phan_cong(db)
    log_rows = db.execute(
        text(
            f"""
            SELECT sal.*
            FROM survey_assignment_logs AS sal
            JOIN (
                SELECT
                    survey_form_id,
                    MAX(id) AS max_id
                FROM survey_assignment_logs
                WHERE survey_form_id IN ({placeholders})
                GROUP BY survey_form_id
            ) AS newest
                ON newest.max_id = sal.id
            """
        ),
        parameters,
    ).mappings().all()

    for row in log_rows:
        latest_logs[int(row["survey_form_id"])] = dict(row)

    return assignments, latest_logs



def tach_danh_sach_id_nhat_ky(raw_value: Any) -> list[int]:
    """Tách danh sách ID được lưu dạng chuỗi trong nhật ký phân công."""

    result: list[int] = []
    seen: set[int] = set()
    for item in str(raw_value or "").split(","):
        item = item.strip()
        if not item:
            continue
        try:
            value = int(item)
        except (TypeError, ValueError):
            continue
        if value > 0 and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def dong_bo_danh_sach_dot_truong_tu_nhat_ky(
    *,
    db: Session,
    school_id: int,
) -> int:
    """Bảo đảm trường vẫn thấy các đợt đã giao, kể cả đã khóa."""

    school_user_ids = {
        int(value)
        for value in db.execute(
            select(User.id).where(
                User.school_id == int(school_id),
                User.role.has(code=SCHOOL_ROLE_CODE),
                ~func.lower(User.username).like("cbql.%"),
            )
        ).scalars().all()
    }
    if not school_user_ids:
        return 0

    candidate_batch_ids = {
        int(value)
        for value in db.execute(
            select(SurveySchoolAssignment.survey_batch_id).where(
                SurveySchoolAssignment.school_id == int(school_id)
            )
        ).scalars().all()
    }

    parameters = {
        f"school_user_{index}": user_id
        for index, user_id in enumerate(sorted(school_user_ids))
    }
    school_log_filter = " OR ".join(
        "(',' || COALESCE(sal.target_user_ids, '') || ',') "
        f"LIKE '%,' || :school_user_{index} || ',%'"
        for index in range(len(school_user_ids))
    )
    rows = db.execute(
        text(
            f"""
            SELECT DISTINCT sf.survey_batch_id
            FROM survey_assignment_logs AS sal
            JOIN survey_forms AS sf ON sf.id = sal.survey_form_id
            WHERE sal.action LIKE 'V4_SCHOOL_%'
              AND ({school_log_filter})
            """
        ),
        parameters,
    ).scalars().all()
    candidate_batch_ids.update(int(value) for value in rows)

    restored = 0
    for batch_id in sorted(candidate_batch_ids):
        restored += dong_bo_phan_cong_truong_hien_tai_tu_nhat_ky(
            db=db,
            batch_id=batch_id,
        )
    return restored


def dong_bo_phan_cong_giao_vien_hien_tai_tu_nhat_ky(
    *,
    db: Session,
    user_id: int,
    school_id: int | None,
) -> int:
    """
    Khôi phục phân công giáo viên còn hiệu lực từ nhật ký V4.

    Mục đích là giữ phiếu đã hoàn thành và đợt đã khóa trong danh sách
    của đúng giáo viên được giao. Nhật ký được phát lại theo thứ tự để
    tôn trọng thao tác giao, thêm, thu hồi và chuyển trường.
    """

    dam_bao_bang_nhat_ky_phan_cong(db)

    candidate_form_ids = [
        int(value)
        for value in db.execute(
            text(
                """
                SELECT DISTINCT sal.survey_form_id
                FROM survey_assignment_logs AS sal
                WHERE sal.action LIKE 'V4_TEACHER_%'
                  AND (
                      ',' || COALESCE(sal.target_user_ids, '') || ','
                  ) LIKE :user_pattern
                """
            ),
            {"user_pattern": f"%,{int(user_id)},%"},
        ).scalars().all()
    ]
    if not candidate_form_ids:
        return 0

    placeholders = ", ".join(
        f":form_id_{index}"
        for index in range(len(candidate_form_ids))
    )
    parameters = {
        f"form_id_{index}": form_id
        for index, form_id in enumerate(candidate_form_ids)
    }

    log_rows = db.execute(
        text(
            f"""
            SELECT
                sal.id,
                sal.survey_form_id,
                sal.action,
                sal.target_user_ids,
                sal.created_at
            FROM survey_assignment_logs AS sal
            WHERE sal.survey_form_id IN ({placeholders})
              AND (
                    sal.action LIKE 'V4_TEACHER_%'
                 OR sal.action IN (
                        'V4_SCHOOL_REPLACE',
                        'V4_SCHOOL_CLEAR'
                    )
              )
            ORDER BY sal.survey_form_id, sal.id
            """
        ),
        parameters,
    ).mappings().all()

    assigned_state: dict[int, bool] = {
        form_id: False for form_id in candidate_form_ids
    }
    latest_times: dict[int, str] = {}

    for row in log_rows:
        form_id = int(row["survey_form_id"])
        action = str(row.get("action") or "").upper()
        target_ids = set(
            tach_danh_sach_id_nhat_ky(row.get("target_user_ids"))
        )

        # Chuyển/thu hồi trường xóa toàn bộ phân công giáo viên phía dưới.
        if action in {"V4_SCHOOL_REPLACE", "V4_SCHOOL_CLEAR"}:
            assigned_state[form_id] = False
            continue

        if action == "V4_TEACHER_REPLACE":
            assigned_state[form_id] = int(user_id) in target_ids
        elif action == "V4_TEACHER_ADD":
            if int(user_id) in target_ids:
                assigned_state[form_id] = True
        elif action == "V4_TEACHER_CLEAR":
            assigned_state[form_id] = False

        if assigned_state.get(form_id):
            latest_times[form_id] = str(row.get("created_at") or "")

    effective_form_ids = [
        form_id
        for form_id, is_assigned in assigned_state.items()
        if is_assigned
    ]
    if not effective_form_ids:
        return 0

    existing_form_ids = {
        int(value)
        for value in db.execute(
            select(SurveyFormInvestigator.survey_form_id).where(
                SurveyFormInvestigator.user_id == int(user_id),
                SurveyFormInvestigator.survey_form_id.in_(effective_form_ids),
            )
        ).scalars().all()
    }

    inserted = 0
    for form_id in effective_form_ids:
        if form_id in existing_form_ids:
            continue

        max_order = int(
            db.execute(
                text(
                    """
                    SELECT COALESCE(MAX(order_number), 0)
                    FROM survey_form_investigators
                    WHERE survey_form_id = :survey_form_id
                    """
                ),
                {"survey_form_id": form_id},
            ).scalar()
            or 0
        )
        signed_at = latest_times.get(form_id) or datetime.now().isoformat(
            sep=" ", timespec="seconds"
        )
        db.execute(
            text(
                """
                INSERT OR IGNORE INTO survey_form_investigators (
                    survey_form_id,
                    user_id,
                    order_number,
                    is_primary,
                    signed_at,
                    notes,
                    created_at
                ) VALUES (
                    :survey_form_id,
                    :user_id,
                    :order_number,
                    0,
                    :signed_at,
                    :notes,
                    :created_at
                )
                """
            ),
            {
                "survey_form_id": form_id,
                "user_id": int(user_id),
                "order_number": max_order + 1000,
                "signed_at": signed_at,
                "notes": (
                    "Khôi phục tự động từ nhật ký giao giáo viên hợp lệ."
                ),
                "created_at": signed_at,
            },
        )
        chuan_hoa_phan_cong_hai_cap_v4(
            db=db,
            survey_form_id=form_id,
            preferred_teacher_user_id=int(user_id),
            preferred_teacher_school_id=school_id,
        )
        inserted += 1

    if inserted:
        db.commit()
    return inserted


def lay_tai_khoan_don_vi_truong_theo_ids(
    db: Session,
    user_ids: set[int],
) -> dict[int, dict[str, Any]]:
    """Lấy đúng tài khoản đơn vị trường, loại tài khoản CBQL/GV."""

    if not user_ids:
        return {}
    placeholders = ", ".join(
        f":user_id_{index}" for index in range(len(user_ids))
    )
    parameters = {
        f"user_id_{index}": user_id
        for index, user_id in enumerate(sorted(user_ids))
    }
    rows = db.execute(
        text(
            f"""
            SELECT
                u.id AS user_id,
                u.username,
                u.full_name,
                u.school_id,
                s.code AS school_code,
                s.name AS school_name
            FROM users AS u
            JOIN roles AS r ON r.id = u.role_id
            LEFT JOIN schools AS s ON s.id = u.school_id
            WHERE u.id IN ({placeholders})
              AND u.is_active = 1
              AND r.code = 'TRUONG'
              AND LOWER(u.username) NOT LIKE 'cbql.%'
              AND u.school_id IS NOT NULL
            """
        ),
        parameters,
    ).mappings().all()
    return {int(row["user_id"]): dict(row) for row in rows}


def tai_hien_phan_cong_truong_tu_nhat_ky(
    db: Session,
    form_ids: list[int],
) -> tuple[dict[int, set[int]], dict[int, dict[str, Any]], dict[int, str]]:
    """Tái hiện trạng thái giao trường hiện hành từ nhật ký V4.

    Nhật ký được dùng làm lớp an toàn khi dữ liệu phân công hiện hành bị
    thiếu do một bản nâng cấp cũ. Chỉ nhật ký cấp trường V4 được sử dụng,
    không suy diễn từ nhật ký giao giáo viên.
    """

    states: dict[int, set[int]] = {int(form_id): set() for form_id in form_ids}
    latest_times: dict[int, str] = {}
    if not form_ids:
        return states, {}, latest_times

    placeholders = ", ".join(
        f":form_id_{index}" for index in range(len(form_ids))
    )
    parameters = {
        f"form_id_{index}": int(form_id)
        for index, form_id in enumerate(form_ids)
    }
    rows = db.execute(
        text(
            f"""
            SELECT
                id,
                survey_form_id,
                action,
                target_user_ids,
                created_at
            FROM survey_assignment_logs
            WHERE survey_form_id IN ({placeholders})
              AND action IN (
                  'V4_SCHOOL_REPLACE',
                  'V4_SCHOOL_ADD',
                  'V4_SCHOOL_CLEAR'
              )
            ORDER BY id ASC
            """
        ),
        parameters,
    ).mappings().all()

    all_target_ids: set[int] = set()
    parsed_rows: list[tuple[dict[str, Any], list[int]]] = []
    for raw_row in rows:
        row = dict(raw_row)
        target_ids = tach_danh_sach_id_nhat_ky(row.get("target_user_ids"))
        all_target_ids.update(target_ids)
        parsed_rows.append((row, target_ids))

    school_users = lay_tai_khoan_don_vi_truong_theo_ids(db, all_target_ids)

    for row, target_ids in parsed_rows:
        form_id = int(row["survey_form_id"])
        valid_ids = {
            int(user_id) for user_id in target_ids if int(user_id) in school_users
        }
        action = str(row.get("action") or "")
        if action == "V4_SCHOOL_REPLACE":
            states[form_id] = set(valid_ids)
        elif action == "V4_SCHOOL_ADD":
            states.setdefault(form_id, set()).update(valid_ids)
        elif action == "V4_SCHOOL_CLEAR":
            states[form_id] = set()
        latest_times[form_id] = str(row.get("created_at") or "")

    return states, school_users, latest_times


def dong_bo_phan_cong_truong_hien_tai_tu_nhat_ky(
    *,
    db: Session,
    batch_id: int,
) -> int:
    """Khôi phục bản ghi giao trường bị thiếu nhưng đã có nhật ký hợp lệ.

    Hàm chỉ bổ sung bản ghi còn thiếu, tuyệt đối không xóa hoặc thay thế
    phân công hiện hành. Nhờ đó các thao tác đã hoàn thành vẫn được giữ nguyên.
    """

    dam_bao_bang_nhat_ky_phan_cong(db)
    form_ids = [
        int(value)
        for value in db.execute(
            text(
                """
                SELECT id
                FROM survey_forms
                WHERE survey_batch_id = :batch_id
                ORDER BY id
                """
            ),
            {"batch_id": int(batch_id)},
        ).scalars().all()
    ]
    if not form_ids:
        return 0

    expected, school_users, latest_times = tai_hien_phan_cong_truong_tu_nhat_ky(
        db, form_ids
    )
    if not school_users:
        return 0

    placeholders = ", ".join(
        f":form_id_{index}" for index in range(len(form_ids))
    )
    parameters = {
        f"form_id_{index}": form_id
        for index, form_id in enumerate(form_ids)
    }
    current_rows = db.execute(
        text(
            f"""
            SELECT sfi.survey_form_id, sfi.user_id
            FROM survey_form_investigators AS sfi
            JOIN users AS u ON u.id = sfi.user_id
            JOIN roles AS r ON r.id = u.role_id
            WHERE sfi.survey_form_id IN ({placeholders})
              AND r.code = 'TRUONG'
              AND LOWER(u.username) NOT LIKE 'cbql.%'
            """
        ),
        parameters,
    ).mappings().all()
    current: dict[int, set[int]] = {}
    for row in current_rows:
        current.setdefault(int(row["survey_form_id"]), set()).add(
            int(row["user_id"])
        )

    inserted = 0
    changed_forms: set[int] = set()
    for form_id, expected_ids in expected.items():
        missing_ids = expected_ids - current.get(form_id, set())
        if not missing_ids:
            continue
        max_order = int(
            db.execute(
                text(
                    """
                    SELECT COALESCE(MAX(order_number), 0)
                    FROM survey_form_investigators
                    WHERE survey_form_id = :survey_form_id
                    """
                ),
                {"survey_form_id": form_id},
            ).scalar()
            or 0
        )
        signed_at = latest_times.get(form_id) or datetime.now().isoformat(
            sep=" ", timespec="seconds"
        )
        for offset, user_id in enumerate(sorted(missing_ids), start=1):
            db.execute(
                text(
                    """
                    INSERT OR IGNORE INTO survey_form_investigators (
                        survey_form_id,
                        user_id,
                        order_number,
                        is_primary,
                        signed_at,
                        notes,
                        created_at
                    ) VALUES (
                        :survey_form_id,
                        :user_id,
                        :order_number,
                        0,
                        :signed_at,
                        :notes,
                        :created_at
                    )
                    """
                ),
                {
                    "survey_form_id": form_id,
                    "user_id": user_id,
                    "order_number": max_order + 1000 + offset,
                    "signed_at": signed_at,
                    "notes": "Khôi phục tự động từ nhật ký giao trường hợp lệ.",
                    "created_at": signed_at,
                },
            )
            inserted += 1
            changed_forms.add(form_id)

    for form_id in changed_forms:
        chuan_hoa_phan_cong_hai_cap_v4(
            db=db,
            survey_form_id=form_id,
        )
    if inserted:
        db.commit()
    return inserted


def lay_lich_su_giao_truong(
    *,
    db: Session,
    batch_id: int,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Lấy danh sách thao tác giao trường để hiển thị ngay trên màn hình."""

    dam_bao_bang_nhat_ky_phan_cong(db)
    rows = db.execute(
        text(
            """
            SELECT
                sal.id,
                sal.survey_form_id,
                sal.action,
                sal.actor_name_snapshot,
                sal.actor_role_snapshot,
                sal.target_user_ids,
                sal.notes,
                sal.created_at,
                sf.form_number,
                h.code AS household_code,
                h.head_name,
                h.hamlet_name
            FROM survey_assignment_logs AS sal
            JOIN survey_forms AS sf ON sf.id = sal.survey_form_id
            JOIN households AS h ON h.id = sf.household_id
            WHERE sf.survey_batch_id = :batch_id
              AND sal.action IN (
                  'V4_SCHOOL_REPLACE',
                  'V4_SCHOOL_ADD',
                  'V4_SCHOOL_CLEAR'
              )
            ORDER BY sal.id DESC
            LIMIT :limit
            """
        ),
        {"batch_id": int(batch_id), "limit": max(1, min(int(limit), 300))},
    ).mappings().all()

    all_target_ids: set[int] = set()
    for row in rows:
        all_target_ids.update(
            tach_danh_sach_id_nhat_ky(row.get("target_user_ids"))
        )
    school_users = lay_tai_khoan_don_vi_truong_theo_ids(db, all_target_ids)

    action_labels = {
        "V4_SCHOOL_REPLACE": "Giao/chuyển trường",
        "V4_SCHOOL_ADD": "Thêm trường phối hợp",
        "V4_SCHOOL_CLEAR": "Thu hồi khỏi trường",
    }
    result: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        target_ids = tach_danh_sach_id_nhat_ky(item.get("target_user_ids"))
        schools = [
            school_users[user_id]
            for user_id in target_ids
            if user_id in school_users
        ]
        item["action_label"] = action_labels.get(
            str(item.get("action") or ""), str(item.get("action") or "")
        )
        item["school_names"] = [
            str(school.get("school_name") or school.get("full_name") or "")
            for school in schools
        ]
        item["school_codes"] = [
            str(school.get("school_code") or "") for school in schools
        ]
        result.append(item)
    return result


def xoa_phan_cong_v4_theo_cap(
    *,
    db: Session,
    survey_form_id: int,
    assignment_level: str,
    school_id: int | None,
) -> None:
    """Xóa đúng tầng phân công, không làm mất nhiệm vụ của cấp trên."""

    if assignment_level == "school":
        # Khi xã chuyển hoặc thu hồi trường, phân công giáo viên phía dưới
        # cũng phải được xóa để trường cũ không còn quyền truy cập phiếu.
        db.execute(
            text(
                """
                DELETE FROM survey_form_investigators
                WHERE survey_form_id = :survey_form_id
                """
            ),
            {"survey_form_id": survey_form_id},
        )
        return

    if assignment_level == "teacher" and school_id is not None:
        db.execute(
            text(
                """
                DELETE FROM survey_form_investigators
                WHERE survey_form_id = :survey_form_id
                  AND user_id IN (
                      SELECT u.id
                      FROM users AS u
                      JOIN roles AS r ON r.id = u.role_id
                      WHERE u.school_id = :school_id
                        AND (
                            r.code = 'GIAO_VIEN'
                            OR (
                                r.code = 'TRUONG'
                                AND LOWER(u.username) LIKE 'cbql.%'
                            )
                        )
                  )
                """
            ),
            {
                "survey_form_id": survey_form_id,
                "school_id": int(school_id),
            },
        )


def chuan_hoa_phan_cong_hai_cap_v4(
    *,
    db: Session,
    survey_form_id: int,
    preferred_school_user_id: int | None = None,
    preferred_teacher_user_id: int | None = None,
    preferred_teacher_school_id: int | None = None,
) -> None:
    """Đánh lại thứ tự và giữ một đơn vị/người chính ở từng tầng."""

    rows = db.execute(
        text(
            """
            SELECT
                sfi.id,
                sfi.user_id,
                sfi.is_primary,
                u.school_id,
                u.username,
                r.code AS role_code,
                COALESCE(s.name, '') AS school_name,
                CASE
                    WHEN r.code = 'TRUONG'
                     AND LOWER(u.username) NOT LIKE 'cbql.%'
                    THEN 1 ELSE 0
                END AS is_school_unit
            FROM survey_form_investigators AS sfi
            JOIN users AS u ON u.id = sfi.user_id
            JOIN roles AS r ON r.id = u.role_id
            LEFT JOIN schools AS s ON s.id = u.school_id
            WHERE sfi.survey_form_id = :survey_form_id
            ORDER BY sfi.order_number, sfi.id
            """
        ),
        {"survey_form_id": survey_form_id},
    ).mappings().all()

    if not rows:
        return

    school_rows = [row for row in rows if bool(row["is_school_unit"])]
    teacher_rows = [row for row in rows if not bool(row["is_school_unit"])]

    school_user_ids = {int(row["user_id"]) for row in school_rows}
    selected_school_primary = (
        int(preferred_school_user_id)
        if preferred_school_user_id in school_user_ids
        else None
    )
    if selected_school_primary is None and school_rows:
        selected_school_primary = next(
            (
                int(row["user_id"])
                for row in school_rows
                if bool(row["is_primary"])
            ),
            int(school_rows[0]["user_id"]),
        )

    teacher_groups: dict[int, list[Any]] = {}
    for row in teacher_rows:
        if row["school_id"] is None:
            continue
        teacher_groups.setdefault(int(row["school_id"]), []).append(row)

    teacher_primary_by_school: dict[int, int] = {}
    for current_school_id, group in teacher_groups.items():
        group_user_ids = {int(row["user_id"]) for row in group}
        preferred = None
        if (
            preferred_teacher_school_id is not None
            and int(preferred_teacher_school_id) == current_school_id
            and preferred_teacher_user_id in group_user_ids
        ):
            preferred = int(preferred_teacher_user_id)
        if preferred is None:
            preferred = next(
                (
                    int(row["user_id"])
                    for row in group
                    if bool(row["is_primary"])
                ),
                int(group[0]["user_id"]),
            )
        teacher_primary_by_school[current_school_id] = preferred

    # Tránh va chạm ràng buộc duy nhất (phiếu, thứ tự).
    for index, row in enumerate(rows, start=1):
        db.execute(
            text(
                """
                UPDATE survey_form_investigators
                SET order_number = :temporary_order,
                    is_primary = 0
                WHERE id = :assignment_id
                """
            ),
            {
                "temporary_order": -index,
                "assignment_id": int(row["id"]),
            },
        )

    school_rows = sorted(
        school_rows,
        key=lambda row: (
            0
            if int(row["user_id"]) == selected_school_primary
            else 1,
            str(row["school_name"]).casefold(),
            int(row["id"]),
        ),
    )
    teacher_rows = sorted(
        teacher_rows,
        key=lambda row: (
            str(row["school_name"]).casefold(),
            0
            if row["school_id"] is not None
            and int(row["user_id"])
            == teacher_primary_by_school.get(int(row["school_id"]))
            else 1,
            int(row["id"]),
        ),
    )

    ordered_rows = [*school_rows, *teacher_rows]
    for index, row in enumerate(ordered_rows, start=1):
        user_id = int(row["user_id"])
        if bool(row["is_school_unit"]):
            is_primary = user_id == selected_school_primary
        elif row["school_id"] is not None:
            is_primary = (
                user_id
                == teacher_primary_by_school.get(int(row["school_id"]))
            )
        else:
            is_primary = False

        db.execute(
            text(
                """
                UPDATE survey_form_investigators
                SET order_number = :order_number,
                    is_primary = :is_primary
                WHERE id = :assignment_id
                """
            ),
            {
                "order_number": index,
                "is_primary": 1 if is_primary else 0,
                "assignment_id": int(row["id"]),
            },
        )


def cap_nhat_phan_cong_v4_mot_phieu(
    *,
    db: Session,
    request: Request,
    survey_form: SurveyForm,
    selected_ids: list[int],
    primary_user_id: int | None,
    assignment_notes: str,
    mode: str,
    assignment_level: str,
) -> None:
    """Cập nhật phân công đúng tầng Xã→Trường hoặc Trường→Giáo viên."""

    actor_user = lay_thong_tin_nguoi_dung(request)
    scope = lay_pham_vi_phan_cong(request)
    current_school_id = scope.get("school_id")
    now_value = datetime.now().isoformat(sep=" ", timespec="seconds")

    if mode in {"replace", "clear"}:
        xoa_phan_cong_v4_theo_cap(
            db=db,
            survey_form_id=survey_form.id,
            assignment_level=assignment_level,
            school_id=(
                int(current_school_id)
                if current_school_id is not None
                else None
            ),
        )

    if mode != "clear":
        existing_ids = {
            int(value)
            for value in db.execute(
                text(
                    """
                    SELECT user_id
                    FROM survey_form_investigators
                    WHERE survey_form_id = :survey_form_id
                    """
                ),
                {"survey_form_id": survey_form.id},
            ).scalars().all()
        }
        max_order = int(
            db.execute(
                text(
                    """
                    SELECT COALESCE(MAX(order_number), 0)
                    FROM survey_form_investigators
                    WHERE survey_form_id = :survey_form_id
                    """
                ),
                {"survey_form_id": survey_form.id},
            ).scalar()
            or 0
        )

        for index, user_id in enumerate(selected_ids, start=1):
            if user_id in existing_ids:
                db.execute(
                    text(
                        """
                        UPDATE survey_form_investigators
                        SET signed_at = :signed_at,
                            notes = :notes
                        WHERE survey_form_id = :survey_form_id
                          AND user_id = :user_id
                        """
                    ),
                    {
                        "signed_at": now_value,
                        "notes": assignment_notes or None,
                        "survey_form_id": survey_form.id,
                        "user_id": user_id,
                    },
                )
                continue

            db.execute(
                text(
                    """
                    INSERT INTO survey_form_investigators (
                        survey_form_id,
                        user_id,
                        order_number,
                        is_primary,
                        signed_at,
                        notes,
                        created_at
                    ) VALUES (
                        :survey_form_id,
                        :user_id,
                        :order_number,
                        0,
                        :signed_at,
                        :notes,
                        :created_at
                    )
                    """
                ),
                {
                    "survey_form_id": survey_form.id,
                    "user_id": user_id,
                    "order_number": max_order + 1000 + index,
                    "signed_at": now_value,
                    "notes": assignment_notes or None,
                    "created_at": now_value,
                },
            )

    chuan_hoa_phan_cong_hai_cap_v4(
        db=db,
        survey_form_id=survey_form.id,
        preferred_school_user_id=(
            primary_user_id if assignment_level == "school" else None
        ),
        preferred_teacher_user_id=(
            primary_user_id if assignment_level == "teacher" else None
        ),
        preferred_teacher_school_id=(
            int(current_school_id)
            if assignment_level == "teacher"
            and current_school_id is not None
            else None
        ),
    )

    ghi_nhat_ky_phan_cong(
        db=db,
        survey_form_id=survey_form.id,
        action=(
            f"V4_{assignment_level.upper()}_{mode.upper()}"
        ),
        actor_user=actor_user,
        target_user_ids=selected_ids,
        notes=assignment_notes,
    )


def dong_bo_nhiem_vu_truong_khi_giao_phieu(
    *,
    db: Session,
    batch_id: int,
    selected_user_ids: list[int],
    actor_user_id: int | None,
    notes: str,
) -> None:
    """Giao phiếu đồng thời bảo đảm trường có nhiệm vụ ở cấp đợt."""

    if not selected_user_ids:
        return
    placeholders = ", ".join(
        f":user_id_{index}"
        for index in range(len(selected_user_ids))
    )
    parameters: dict[str, Any] = {
        f"user_id_{index}": user_id
        for index, user_id in enumerate(selected_user_ids)
    }
    school_ids = {
        int(value)
        for value in db.execute(
            text(
                f"""
                SELECT DISTINCT school_id
                FROM users
                WHERE id IN ({placeholders})
                  AND school_id IS NOT NULL
                """
            ),
            parameters,
        ).scalars().all()
    }

    for school_id in school_ids:
        assignment = db.scalar(
            select(SurveySchoolAssignment).where(
                SurveySchoolAssignment.survey_batch_id == batch_id,
                SurveySchoolAssignment.school_id == school_id,
            )
        )
        if assignment is None:
            db.add(
                SurveySchoolAssignment(
                    survey_batch_id=batch_id,
                    school_id=school_id,
                    status="DANG_THUC_HIEN",
                    assigned_by_user_id=actor_user_id,
                    assigned_at=datetime.now(),
                    notes=notes or None,
                )
            )

            # === SUA_UNIQUE_SURVEY_SCHOOL_ASSIGNMENTS_GIAO_PHIEU_V3 ===
            # Flush ngay nhiệm vụ vừa thêm để lần gọi helper tiếp theo
            # trong cùng transaction nhìn thấy cặp
            # (survey_batch_id, school_id) vừa tạo.
            db.flush()
        else:
            assignment.status = "DANG_THUC_HIEN"
            assignment.assigned_by_user_id = actor_user_id
            assignment.assigned_at = datetime.now()
            if notes:
                assignment.notes = notes


def hien_thi_trang_phan_cong_v4(
    *,
    batch_id: int,
    request: Request,
    assignment_level: str,
    q: str,
    hamlet: str,
    assignment_status: str,
    investigator_id: int,
    school_id: int,
    page: int,
    page_size: int,
    status: str | None,
    error: str | None,
    db: Session,
):
    batch = lay_dot_dieu_tra(db, batch_id)
    if batch is None:
        return RedirectResponse(url="/dieu-tra", status_code=303)

    scope = lay_pham_vi_phan_cong(request)
    if not co_quyen_phan_cong_theo_cap(
        scope=scope,
        batch=batch,
        assignment_level=assignment_level,
    ):
        return RedirectResponse(url="/?status=forbidden", status_code=303)

    if assignment_level == "school":
        dong_bo_phan_cong_truong_hien_tai_tu_nhat_ky(
            db=db,
            batch_id=batch.id,
        )

    q = chuan_hoa_van_ban(q)[:200]
    hamlet = chuan_hoa_van_ban(hamlet)[:200]
    assignment_status = assignment_status.strip().lower()
    if assignment_status not in {"", "assigned", "unassigned"}:
        assignment_status = ""
    if page_size not in HOUSEHOLD_PAGE_SIZE_OPTIONS:
        page_size = HOUSEHOLD_PAGE_SIZE
    page = max(1, page)
    investigator_id = max(0, investigator_id)
    school_id = max(0, school_id)

    current_school_id = scope.get("school_id")
    if assignment_level == "teacher" and current_school_id is None:
        return RedirectResponse(url="/?status=forbidden", status_code=303)

    base_scope_filters: list[Any] = [
        SurveyForm.survey_batch_id == batch.id,
    ]
    if assignment_level == "teacher":
        # === BAI_13B_10_V3_12_TEAM_SCOPE_GET_START ===
        # V3.12: giữ tương thích giao trường V4 cũ, đồng thời nhận đúng
        # các phiếu tổ điều tra 3 cấp mà xã/phường đã chốt.
        base_scope_filters.append(
            or_(
                dieu_kien_phieu_da_giao_truong(int(current_school_id)),
                SurveyForm.investigators.any(
                    SurveyFormInvestigator.user.has(
                        User.school_id == int(current_school_id)
                    )
                ),
            )
        )
        # === BAI_13B_10_V3_12_TEAM_SCOPE_GET_END ===
    else:
        base_scope_filters.extend(tao_bo_loc_phieu_theo_nguoi_dung(request))

    filters: list[Any] = [*base_scope_filters]
    if q:
        keyword = f"%{q}%"
        filters.append(
            or_(
                SurveyForm.form_number.ilike(keyword),
                Household.code.ilike(keyword),
                Household.head_name.ilike(keyword),
                Household.address.ilike(keyword),
                Household.phone.ilike(keyword),
            )
        )
    if hamlet:
        filters.append(Household.hamlet_name == hamlet)

    assigned_condition = (
        dieu_kien_phieu_da_giao_truong()
        if assignment_level == "school"
        else dieu_kien_phieu_da_giao_nhan_su_truong(
            int(current_school_id)
        )
    )
    if assignment_status:
        filters.append(
            assigned_condition
            if assignment_status == "assigned"
            else ~assigned_condition
        )

    if assignment_level == "teacher" and investigator_id > 0:
        filters.append(
            SurveyForm.investigators.any(
                SurveyFormInvestigator.user_id == investigator_id
            )
        )
    if assignment_level == "school" and school_id > 0:
        filters.append(dieu_kien_phieu_da_giao_truong(school_id))

    total_records = int(
        db.scalar(
            select(func.count(SurveyForm.id))
            .join(Household, Household.id == SurveyForm.household_id)
            .where(*filters)
        )
        or 0
    )
    total_pages = max(1, ceil(total_records / page_size))
    page = min(page, total_pages)
    offset = (page - 1) * page_size

    survey_forms = db.scalars(
        select(SurveyForm)
        .join(Household, Household.id == SurveyForm.household_id)
        .options(
            selectinload(SurveyForm.household),
            selectinload(SurveyForm.investigators),
        )
        .where(*filters)
        .order_by(
            Household.hamlet_name.asc(),
            Household.head_name.asc(),
            SurveyForm.id.asc(),
        )
        .offset(offset)
        .limit(page_size)
    ).all()

    form_ids = [int(item.id) for item in survey_forms]
    assignment_summaries, latest_logs = (
        lay_tom_tat_phan_cong_nhieu_phieu(db, form_ids)
    )

    candidates: list[dict[str, Any]] = []
    schools: list[dict[str, Any]] = []
    if assignment_level == "school":
        schools = lay_danh_sach_truong_trong_xa_cho_phan_cong(
            db=db,
            commune_id=batch.commune_id,
        )
    else:
        candidates = lay_danh_sach_nguoi_dieu_tra(
            db=db,
            commune_id=batch.commune_id,
            request=request,
        )

    schools_with_account_total = sum(
        1 for item in schools if item.get("account_id") is not None
    )
    schools_without_account_total = (
        len(schools) - schools_with_account_total
    )

    hamlet_names = db.scalars(
        select(Household.hamlet_name)
        .join(SurveyForm, SurveyForm.household_id == Household.id)
        .where(
            *base_scope_filters,
            Household.hamlet_name.is_not(None),
            Household.hamlet_name != "",
        )
        .distinct()
        .order_by(Household.hamlet_name.asc())
    ).all()

    start_page = max(1, page - 2)
    end_page = min(total_pages, page + 2)
    page_links = [
        {
            "number": number,
            "active": number == page,
            "url": tao_url_phan_cong_hang_loat(
                batch_id=batch.id,
                page=number,
                q=q,
                hamlet=hamlet,
                assignment_status=assignment_status,
                investigator_id=investigator_id,
                school_id=school_id,
                page_size=page_size,
                assignment_level=assignment_level,
            ),
        }
        for number in range(start_page, end_page + 1)
    ]

    previous_url = (
        tao_url_phan_cong_hang_loat(
            batch_id=batch.id,
            page=page - 1,
            q=q,
            hamlet=hamlet,
            assignment_status=assignment_status,
            investigator_id=investigator_id,
            school_id=school_id,
            page_size=page_size,
            assignment_level=assignment_level,
        )
        if page > 1
        else None
    )
    next_url = (
        tao_url_phan_cong_hang_loat(
            batch_id=batch.id,
            page=page + 1,
            q=q,
            hamlet=hamlet,
            assignment_status=assignment_status,
            investigator_id=investigator_id,
            school_id=school_id,
            page_size=page_size,
            assignment_level=assignment_level,
        )
        if page < total_pages
        else None
    )

    page_title = (
        "Giao phiếu cho trường"
        if assignment_level == "school"
        else "Giao phiếu cho giáo viên"
    )
    page_kicker = (
        "XÃ/PHƯỜNG GIAO PHIẾU CHO TRƯỜNG"
        if assignment_level == "school"
        else "TRƯỜNG GIAO PHIẾU CHO GIÁO VIÊN"
    )
    assignment_history = (
        lay_lich_su_giao_truong(db=db, batch_id=batch.id, limit=100)
        if assignment_level == "school"
        else []
    )

    return templates.TemplateResponse(
        request=request,
        name="surveys/bulk_assignments.html",
        context={
            "nguoi_dung": request.scope.get("auth_user"),
            "batch": batch,
            "scope": scope,
            "assignment_level": assignment_level,
            "page_title": page_title,
            "page_kicker": page_kicker,
            "filter_url": duong_dan_phan_cong_theo_cap(
                batch.id, assignment_level
            ),
            "save_url": (
                duong_dan_phan_cong_theo_cap(batch.id, assignment_level)
                + "/luu"
            ),
            "survey_forms": survey_forms,
            "assignment_summaries": assignment_summaries,
            "latest_logs": latest_logs,
            "assignment_history": assignment_history,
            "candidates": candidates,
            "schools": schools,
            "schools_with_account_total": schools_with_account_total,
            "schools_without_account_total": schools_without_account_total,
            "hamlet_names": hamlet_names,
            "q": q,
            "selected_hamlet": hamlet,
            "selected_assignment_status": assignment_status,
            "selected_investigator_id": investigator_id,
            "selected_school_id": school_id,
            "selected_page_size": page_size,
            "page_size_options": HOUSEHOLD_PAGE_SIZE_OPTIONS,
            "page": page,
            "total_pages": total_pages,
            "total_records": total_records,
            "page_links": page_links,
            "previous_url": previous_url,
            "next_url": next_url,
            "thong_bao": STATUS_MESSAGES.get(status),
            "thong_bao_loi": BULK_ASSIGNMENT_ERROR_MESSAGES.get(error),
        },
    )


@router.get(
    "/{batch_id}/giao-phieu-truong",
    response_class=HTMLResponse,
)
def trang_giao_phieu_cho_truong(
    batch_id: int,
    request: Request,
    q: str = "",
    hamlet: str = "",
    assignment_status: str = "",
    investigator_id: int = 0,
    school_id: int = 0,
    page: int = 1,
    page_size: int = HOUSEHOLD_PAGE_SIZE,
    status: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
):
    return hien_thi_trang_phan_cong_v4(
        batch_id=batch_id,
        request=request,
        assignment_level="school",
        q=q,
        hamlet=hamlet,
        assignment_status=assignment_status,
        investigator_id=investigator_id,
        school_id=school_id,
        page=page,
        page_size=page_size,
        status=status,
        error=error,
        db=db,
    )


@router.get(
    "/{batch_id}/giao-phieu-giao-vien",
    response_class=HTMLResponse,
)
def trang_giao_phieu_cho_giao_vien(
    batch_id: int,
    request: Request,
    q: str = "",
    hamlet: str = "",
    assignment_status: str = "",
    investigator_id: int = 0,
    school_id: int = 0,
    page: int = 1,
    page_size: int = HOUSEHOLD_PAGE_SIZE,
    status: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
):
    return hien_thi_trang_phan_cong_v4(
        batch_id=batch_id,
        request=request,
        assignment_level="teacher",
        q=q,
        hamlet=hamlet,
        assignment_status=assignment_status,
        investigator_id=investigator_id,
        school_id=school_id,
        page=page,
        page_size=page_size,
        status=status,
        error=error,
        db=db,
    )


@router.get(
    "/{batch_id}/phan-cong-hang-loat",
    response_class=HTMLResponse,
)
def trang_phan_cong_hang_loat_cu(
    batch_id: int,
    request: Request,
):
    """Giữ liên kết cũ nhưng chuyển đúng trang theo cấp tài khoản."""

    scope = lay_pham_vi_phan_cong(request)
    assignment_level = (
        "teacher"
        if scope["role_code"] == SCHOOL_ROLE_CODE
        else "school"
    )
    target = duong_dan_phan_cong_theo_cap(batch_id, assignment_level)
    if request.url.query:
        target += "?" + request.url.query
    return RedirectResponse(url=target, status_code=303)



# === DONG_BO_GIAO_PHIEU_THEO_PHAN_CONG_HIEN_CO_V1_HELPER ===
def lay_nguoi_nhan_giao_phieu_tu_phan_cong_hien_co(
    *,
    db: Session,
    survey_form_id: int,
    assignment_level: str,
    current_school_id: int | None,
) -> tuple[list[int], int | None]:
    # Lấy người nhận từ phân công đã có, không bắt người dùng chọn lại.
    rows = db.execute(
        select(
            SurveyFormInvestigator.user_id,
            SurveyFormInvestigator.is_primary,
            User.school_id,
        )
        .join(
            User,
            User.id == SurveyFormInvestigator.user_id,
        )
        .where(
            SurveyFormInvestigator.survey_form_id
            == int(survey_form_id)
        )
        .order_by(
            SurveyFormInvestigator.is_primary.desc(),
            SurveyFormInvestigator.id.asc(),
        )
    ).all()

    if assignment_level == "school":
        school_ids: list[int] = []
        seen_school_ids: set[int] = set()

        for row in rows:
            if row.school_id is None:
                continue

            school_id = int(row.school_id)

            if school_id not in seen_school_ids:
                seen_school_ids.add(school_id)
                school_ids.append(school_id)

        if not school_ids:
            return [], None

        account_rows = db.execute(
            select(
                User.id,
                User.school_id,
            )
            .where(
                User.school_id.in_(school_ids),
                User.role.has(code=SCHOOL_ROLE_CODE),
                ~func.lower(User.username).like("cbql.%"),
            )
            .order_by(
                User.school_id.asc(),
                User.id.asc(),
            )
        ).all()

        result: list[int] = []
        seen_ids: set[int] = set()

        for row in account_rows:
            user_id = int(row.id)

            if user_id not in seen_ids:
                seen_ids.add(user_id)
                result.append(user_id)

        return result, (result[0] if result else None)

    if assignment_level == "teacher":
        if current_school_id is None:
            return [], None

        result: list[int] = []
        seen_ids: set[int] = set()
        primary_id: int | None = None

        for row in rows:
            if (
                row.school_id is None
                or int(row.school_id) != int(current_school_id)
            ):
                continue

            user_id = int(row.user_id)

            is_school_account = bool(
                db.scalar(
                    select(func.count(User.id))
                    .where(
                        User.id == user_id,
                        User.role.has(code=SCHOOL_ROLE_CODE),
                        ~func.lower(User.username).like("cbql.%"),
                    )
                )
                or 0
            )

            if is_school_account:
                continue

            if user_id not in seen_ids:
                seen_ids.add(user_id)
                result.append(user_id)

            if bool(row.is_primary) and primary_id is None:
                primary_id = user_id

        if primary_id not in seen_ids:
            primary_id = result[0] if result else None

        return result, primary_id

    return [], None


async def luu_phan_cong_v4_theo_cap(
    *,
    batch_id: int,
    assignment_level: str,
    request: Request,
    db: Session,
):
    batch = lay_dot_dieu_tra(db, batch_id)
    if batch is None:
        return RedirectResponse(url="/dieu-tra", status_code=303)

    scope = lay_pham_vi_phan_cong(request)
    base_url = duong_dan_phan_cong_theo_cap(batch_id, assignment_level)
    if not co_quyen_phan_cong_theo_cap(
        scope=scope,
        batch=batch,
        assignment_level=assignment_level,
    ):
        return RedirectResponse(
            url=f"{base_url}?error=invalid_assignment_level",
            status_code=303,
        )

    submitted = await request.form()
    mode = str(submitted.get("mode") or "replace").strip().lower()
    if mode not in {"replace", "add", "clear"}:
        mode = "replace"

    form_ids: list[int] = []
    seen_form_ids: set[int] = set()
    for raw_value in submitted.getlist("survey_form_ids"):
        try:
            form_id = int(str(raw_value))
        except (TypeError, ValueError):
            continue
        if form_id > 0 and form_id not in seen_form_ids:
            seen_form_ids.add(form_id)
            form_ids.append(form_id)

    if not form_ids:
        return RedirectResponse(
            url=f"{base_url}?error=no_forms",
            status_code=303,
        )

    selected_ids: list[int] = []
    seen_user_ids: set[int] = set()
    for raw_value in submitted.getlist("investigator_ids"):
        try:
            user_id = int(str(raw_value))
        except (TypeError, ValueError):
            continue
        if user_id > 0 and user_id not in seen_user_ids:
            seen_user_ids.add(user_id)
            selected_ids.append(user_id)

    # === DONG_BO_GIAO_PHIEU_THEO_PHAN_CONG_HIEN_CO_V1_POST ===
    # Không chọn nơi nhận mới + mode=replace:
    # giao theo phân công hiện có.
    auto_send_existing = (
        mode == "replace"
        and not selected_ids
    )

    # Chỉ chế độ "Thêm" mới bắt buộc chọn nơi nhận mới.
    if mode == "add" and not selected_ids:
        return RedirectResponse(
            url=f"{base_url}?error=no_investigators",
            status_code=303,
        )

    primary_value = str(submitted.get("primary_user_id") or "").strip()
    try:
        primary_user_id = int(primary_value)
    except ValueError:
        primary_user_id = selected_ids[0] if selected_ids else None
    if (
        primary_user_id is not None
        and primary_user_id not in seen_user_ids
    ):
        primary_user_id = selected_ids[0] if selected_ids else None

    assignment_notes = chuan_hoa_van_ban(
        str(submitted.get("assignment_notes") or "")
    )[:1000]
    print_after = str(submitted.get("print_after") or "").strip() == "1"

    form_filters: list[Any] = [
        SurveyForm.survey_batch_id == batch.id,
        SurveyForm.id.in_(form_ids),
    ]
    if assignment_level == "teacher":
        current_school_id = scope.get("school_id")
        if current_school_id is None:
            return RedirectResponse(
                url=f"{base_url}?error=invalid_assignment_level",
                status_code=303,
            )
        # === BAI_13B_10_V3_12_TEAM_SCOPE_POST_START ===
        # V3.12: POST dùng cùng phạm vi với GET. Chỉ cho phép trường
        # thao tác phiếu có thành viên tổ thuộc chính school_id của mình.
        form_filters.append(
            or_(
                dieu_kien_phieu_da_giao_truong(int(current_school_id)),
                SurveyForm.investigators.any(
                    SurveyFormInvestigator.user.has(
                        User.school_id == int(current_school_id)
                    )
                ),
            )
        )
        # === BAI_13B_10_V3_12_TEAM_SCOPE_POST_END ===
    else:
        form_filters.extend(tao_bo_loc_phieu_theo_nguoi_dung(request))

    survey_forms = db.scalars(
        select(SurveyForm)
        .options(
            selectinload(SurveyForm.survey_batch),
            selectinload(SurveyForm.household),
        )
        .where(*form_filters)
    ).all()
    if len(survey_forms) != len(form_ids):
        return RedirectResponse(
            url=f"{base_url}?error=invalid_forms",
            status_code=303,
        )

    if mode != "clear" and not auto_send_existing:
        allowed_ids = lay_ids_nguoi_dieu_tra_hop_le(
            db=db,
            request=request,
            commune_id=batch.commune_id,
            user_ids=selected_ids,
        )
        if allowed_ids != seen_user_ids:
            return RedirectResponse(
                url=f"{base_url}?error=invalid_investigators",
                status_code=303,
            )

    auto_targets_by_form: dict[
        int,
        tuple[list[int], int | None],
    ] = {}

    if auto_send_existing:
        current_school_id = (
            scope.get("school_id")
            if assignment_level == "teacher"
            else None
        )

        for survey_form in survey_forms:
            target_ids, target_primary_id = (
                lay_nguoi_nhan_giao_phieu_tu_phan_cong_hien_co(
                    db=db,
                    survey_form_id=int(survey_form.id),
                    assignment_level=assignment_level,
                    current_school_id=(
                        int(current_school_id)
                        if current_school_id is not None
                        else None
                    ),
                )
            )

            if not target_ids:
                return RedirectResponse(
                    url=f"{base_url}?error=no_existing_assignment",
                    status_code=303,
                )

            auto_targets_by_form[int(survey_form.id)] = (
                target_ids,
                target_primary_id,
            )

    try:
        # Chọn nơi nhận mới thì giữ nguyên hành vi cũ.
        if (
            assignment_level == "school"
            and mode != "clear"
            and not auto_send_existing
        ):
            dong_bo_nhiem_vu_truong_khi_giao_phieu(
                db=db,
                batch_id=batch.id,
                selected_user_ids=selected_ids,
                actor_user_id=scope["user"].get("id"),
                notes=assignment_notes,
            )

        for survey_form in survey_forms:
            effective_ids = selected_ids
            effective_primary_id = primary_user_id
            effective_mode = mode

            if auto_send_existing:
                (
                    effective_ids,
                    effective_primary_id,
                ) = auto_targets_by_form[int(survey_form.id)]

                # Giao theo phân công hiện có chỉ bổ sung tầng nhận.
                # Không replace để tránh xóa tổ giáo viên 3 cấp.
                effective_mode = "add"

                if assignment_level == "school":
                    dong_bo_nhiem_vu_truong_khi_giao_phieu(
                        db=db,
                        batch_id=batch.id,
                        selected_user_ids=effective_ids,
                        actor_user_id=scope["user"].get("id"),
                        notes=(
                            assignment_notes
                            or "Giao phiếu theo phân công hiện có."
                        ),
                    )

            cap_nhat_phan_cong_v4_mot_phieu(
                db=db,
                request=request,
                survey_form=survey_form,
                selected_ids=effective_ids,
                primary_user_id=effective_primary_id,
                assignment_notes=(
                    assignment_notes
                    or (
                        "Giao phiếu theo phân công hiện có."
                        if auto_send_existing
                        else ""
                    )
                ),
                mode=effective_mode,
                assignment_level=assignment_level,
            )

        db.commit()
    except Exception as exc:
        # === CHAN_DOAN_SAVE_FAILED_GIAO_PHIEU_V2_1 ===
        db.rollback()

        print()
        print("=" * 100)
        print("[GIAO_PHIEU_SAVE_FAILED]")
        print("TYPE :", type(exc).__name__)
        print("ERROR:", repr(exc))
        print(
            "LEVEL:",
            assignment_level,
            "| MODE:",
            mode,
            "| AUTO_EXISTING:",
            auto_send_existing,
        )
        print(
            "FORM_IDS:",
            form_ids,
            "| SELECTED_IDS:",
            selected_ids,
        )
        print("=" * 100)
        print()

        return RedirectResponse(
            url=f"{base_url}?error=save_failed",
            status_code=303,
        )

    success_status = (
        "bulk_assignments_cleared"
        if mode == "clear"
        else (
            "bulk_assignments_sent_existing"
            if auto_send_existing
            else "bulk_assignments_saved"
        )
    )

    if mode != "clear" and print_after:
        print_ids = ",".join(str(item.id) for item in survey_forms)
        return RedirectResponse(
            url=(
                f"/dieu-tra/{batch_id}/phieu-in-thuc-dia"
                f"?form_ids={print_ids}&auto_print=1"
                f"&source=v4_{assignment_level}_assignment"
            ),
            status_code=303,
        )

    return RedirectResponse(
        url=f"{base_url}?status={success_status}",
        status_code=303,
    )


@router.post("/{batch_id}/giao-phieu-truong/luu")
async def luu_giao_phieu_cho_truong(
    batch_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    return await luu_phan_cong_v4_theo_cap(
        batch_id=batch_id,
        assignment_level="school",
        request=request,
        db=db,
    )


@router.post("/{batch_id}/giao-phieu-giao-vien/luu")
async def luu_giao_phieu_cho_giao_vien(
    batch_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    # === BAI_13B_11_8_2_AUTO_SEND_AFTER_TEACHER_ASSIGN_START ===
    response = await luu_phan_cong_v4_theo_cap(
        batch_id=batch_id,
        assignment_level="teacher",
        request=request,
        db=db,
    )

    location = str(response.headers.get("location") or "")
    lower_location = location.lower()

    assignment_saved = (
        int(getattr(response, "status_code", 0) or 0) == 303
        and "error=" not in lower_location
        and "forbidden" not in lower_location
        and "save_failed" not in lower_location
        and "invalid" not in lower_location
        and "not_found" not in lower_location
        and (
            "auto_print=1" in lower_location
            or "?status=" in lower_location
            or "&status=" in lower_location
        )
    )

    if assignment_saved:
        from app.routers.survey_school_workflow import truong_gui_xa

        send_response = truong_gui_xa(
            request=request,
            batch_id=batch_id,
            notes=(
                "Tự động gửi lại báo cáo xã/phường "
                "sau khi trường giao/thay giáo viên."
            ),
            db=db,
        )

        send_location = str(
            send_response.headers.get("location") or ""
        ).lower()

        if "school_submitted" not in send_location:
            return send_response

    return response
    # === BAI_13B_11_8_2_AUTO_SEND_AFTER_TEACHER_ASSIGN_END ===




@router.post("/{batch_id}/phan-cong-hang-loat/luu")
async def luu_phan_cong_hang_loat_cu(
    batch_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """Tương thích biểu mẫu cũ và xử lý đúng tầng theo tài khoản."""

    scope = lay_pham_vi_phan_cong(request)
    assignment_level = (
        "teacher"
        if scope["role_code"] == SCHOOL_ROLE_CODE
        else "school"
    )
    return await luu_phan_cong_v4_theo_cap(
        batch_id=batch_id,
        assignment_level=assignment_level,
        request=request,
        db=db,
    )


@router.get(
    "/{batch_id}/ho-dan/{household_id}/phan-cong",
    response_class=HTMLResponse,
)
def trang_phan_cong_nguoi_dieu_tra(
    batch_id: int,
    household_id: int,
    request: Request,
    status: str | None = None,
    db: Session = Depends(get_db),
):
    survey_form = lay_phieu_ho(
        db=db,
        batch_id=batch_id,
        household_id=household_id,
    )

    if survey_form is None:
        return RedirectResponse(
            url=f"/dieu-tra/{batch_id}/ho-dan",
            status_code=303,
        )

    if not la_phieu_trong_pham_vi_phan_cong(
        db=db,
        request=request,
        survey_form=survey_form,
    ):
        return RedirectResponse(url="/?status=forbidden", status_code=303)

    return hien_thi_trang_phan_cong(
        request=request,
        db=db,
        survey_form=survey_form,
        status=status,
    )


@router.post(
    "/{batch_id}/ho-dan/{household_id}/phan-cong/luu",
)
async def luu_phan_cong_nguoi_dieu_tra(
    batch_id: int,
    household_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    survey_form = lay_phieu_ho(
        db=db,
        batch_id=batch_id,
        household_id=household_id,
    )

    if survey_form is None:
        return RedirectResponse(
            url=f"/dieu-tra/{batch_id}/ho-dan",
            status_code=303,
        )

    if not la_phieu_trong_pham_vi_phan_cong(
        db=db,
        request=request,
        survey_form=survey_form,
    ):
        return RedirectResponse(url="/?status=forbidden", status_code=303)

    submitted = await request.form()
    raw_ids = submitted.getlist("investigator_ids")

    selected_ids: list[int] = []
    seen_ids: set[int] = set()

    for raw_value in raw_ids:
        try:
            user_id = int(str(raw_value))
        except (TypeError, ValueError):
            continue

        if user_id <= 0 or user_id in seen_ids:
            continue

        seen_ids.add(user_id)
        selected_ids.append(user_id)

    if not selected_ids:
        return hien_thi_trang_phan_cong(
            request=request,
            db=db,
            survey_form=survey_form,
            thong_bao_loi=(
                "Bạn cần chọn ít nhất một người điều tra. "
                "Nếu muốn thu hồi phân công, hãy dùng nút "
                "Thu hồi phân công."
            ),
            status_code=400,
        )

    primary_value = str(
        submitted.get("primary_user_id") or ""
    ).strip()

    try:
        primary_user_id = int(primary_value)
    except ValueError:
        primary_user_id = selected_ids[0]

    if primary_user_id not in seen_ids:
        primary_user_id = selected_ids[0]

    assignment_notes = chuan_hoa_van_ban(
        str(submitted.get("assignment_notes") or "")
    )[:1000]

    allowed_ids = lay_ids_nguoi_dieu_tra_hop_le(
        db=db,
        request=request,
        commune_id=survey_form.survey_batch.commune_id,
        user_ids=selected_ids,
    )

    if allowed_ids != seen_ids:
        return hien_thi_trang_phan_cong(
            request=request,
            db=db,
            survey_form=survey_form,
            thong_bao_loi=(
                "Danh sách có tài khoản không còn hoạt động, "
                "không thuộc đúng phạm vi hoặc không đúng vai trò. "
                "Hãy tải lại trang và chọn lại."
            ),
            status_code=400,
        )

    try:
        cap_nhat_phan_cong_mot_phieu(
            db=db,
            request=request,
            survey_form=survey_form,
            selected_ids=selected_ids,
            primary_user_id=primary_user_id,
            assignment_notes=assignment_notes,
            mode="replace",
            log_action="REPLACE",
        )
        db.commit()
    except Exception:
        db.rollback()

        return hien_thi_trang_phan_cong(
            request=request,
            db=db,
            survey_form=survey_form,
            thong_bao_loi=(
                "Không thể lưu phân công. Dữ liệu cũ vẫn được giữ nguyên."
            ),
            status_code=500,
        )

    return RedirectResponse(
        url=(
            f"/dieu-tra/{batch_id}/ho-dan/"
            f"{household_id}/phan-cong?status=investigators_saved"
        ),
        status_code=303,
    )


@router.post(
    "/{batch_id}/ho-dan/{household_id}/phan-cong/xoa",
)
def xoa_phan_cong_nguoi_dieu_tra(
    batch_id: int,
    household_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    survey_form = lay_phieu_ho(
        db=db,
        batch_id=batch_id,
        household_id=household_id,
    )

    if survey_form is None:
        return RedirectResponse(
            url=f"/dieu-tra/{batch_id}/ho-dan",
            status_code=303,
        )

    if not la_phieu_trong_pham_vi_phan_cong(
        db=db,
        request=request,
        survey_form=survey_form,
    ):
        return RedirectResponse(url="/?status=forbidden", status_code=303)

    try:
        cap_nhat_phan_cong_mot_phieu(
            db=db,
            request=request,
            survey_form=survey_form,
            selected_ids=[],
            primary_user_id=None,
            assignment_notes="",
            mode="clear",
            log_action="CLEAR",
        )
        db.commit()
    except Exception:
        db.rollback()
        return RedirectResponse(
            url=(
                f"/dieu-tra/{batch_id}/ho-dan/"
                f"{household_id}/phan-cong"
            ),
            status_code=303,
        )

    return RedirectResponse(
        url=(
            f"/dieu-tra/{batch_id}/ho-dan"
            "?status=investigators_cleared"
        ),
        status_code=303,
    )


# =========================================================
# TRẠNG THÁI PHIẾU VÀ TIẾN ĐỘ ĐIỀU TRA
# =========================================================

def hien_thi_trang_cap_nhat_phieu(
    *,
    request: Request,
    survey_form: SurveyForm,
    active_people_count: int,
    status: str | None = None,
    thong_bao_loi: str | None = None,
    form_data: dict[str, Any] | None = None,
    status_code: int = 200,
):
    """Hiển thị biểu mẫu cập nhật trạng thái một phiếu điều tra."""

    nguoi_dung = lay_thong_tin_nguoi_dung(request)
    role_code = str(nguoi_dung.get("role_code") or "")
    can_confirm_commune = is_admin_role(role_code) or normalize_role_code(role_code) == "XA"
    can_edit_data = can_edit_survey_data(role_code)

    if form_data is None:
        form_data = {
            "form_status": survey_form.status,
            "survey_date": (
                survey_form.survey_date.isoformat()
                if survey_form.survey_date
                else ""
            ),
            "village_head_name": (
                survey_form.village_head_name or ""
            ),
            "household_representative_name": (
                survey_form.household_representative_name or ""
            ),
            "household_confirmed": (
                survey_form.household_confirmed_at is not None
            ),
            "commune_confirmed": (
                survey_form.commune_confirmed_at is not None
            ),
            "notes": survey_form.notes or "",
        }

    return templates.TemplateResponse(
        request=request,
        name="surveys/form_status.html",
        context={
            "nguoi_dung": nguoi_dung,
            "can_confirm_commune": can_confirm_commune,
            "can_edit_data": can_edit_data,
            "batch": survey_form.survey_batch,
            "survey_form": survey_form,
            "household": survey_form.household,
            "active_people_count": active_people_count,
            "form_status_labels": FORM_STATUS_LABELS,
            "thong_bao": STATUS_MESSAGES.get(status),
            "thong_bao_loi": thong_bao_loi,
            "form_data": form_data,
            "today": date.today().isoformat(),
        },
        status_code=status_code,
    )


@router.get(
    "/{batch_id}/ho-dan/{household_id}/phieu",
    response_class=HTMLResponse,
)
def trang_cap_nhat_phieu(
    batch_id: int,
    household_id: int,
    request: Request,
    status: str | None = None,
    db: Session = Depends(get_db),
):
    survey_form = lay_phieu_ho(
        db=db,
        batch_id=batch_id,
        household_id=household_id,
    )

    if survey_form is None:
        return RedirectResponse(
            url=f"/dieu-tra/{batch_id}/ho-dan",
            status_code=303,
        )

    active_people_count = int(
        db.scalar(
            select(func.count(SurveyPerson.id)).where(
                SurveyPerson.household_id == household_id,
                SurveyPerson.is_active.is_(True),
            )
        )
        or 0
    )

    return hien_thi_trang_cap_nhat_phieu(
        request=request,
        survey_form=survey_form,
        active_people_count=active_people_count,
        status=status,
    )


@router.post(
    "/{batch_id}/ho-dan/{household_id}/phieu/cap-nhat"
)
def cap_nhat_phieu(
    batch_id: int,
    household_id: int,
    request: Request,
    form_status: Annotated[str, Form()],
    survey_date: Annotated[str, Form()] = "",
    village_head_name: Annotated[str, Form()] = "",
    household_representative_name: Annotated[str, Form()] = "",
    household_confirmed: Annotated[str, Form()] = "",
    commune_confirmed: Annotated[str, Form()] = "",
    notes: Annotated[str, Form()] = "",
    db: Session = Depends(get_db),
):
    survey_form = lay_phieu_ho(
        db=db,
        batch_id=batch_id,
        household_id=household_id,
    )

    if survey_form is None:
        return RedirectResponse(
            url=f"/dieu-tra/{batch_id}/ho-dan",
            status_code=303,
        )

    nguoi_dung = lay_thong_tin_nguoi_dung(request)
    role_code = str(nguoi_dung.get("role_code") or "")
    can_confirm_commune = is_admin_role(role_code) or normalize_role_code(role_code) == "XA"

    # === BAI_30B2_XA_CONFIRM_SCOPE_GUARD_START ===
    # Chỉ bổ sung guard cho vai trò XA vừa được mở quyền.
    # ADMIN và các vai trò cũ giữ nguyên luồng đang chạy.
    if (
        normalize_role_code(role_code) == "XA"
        and not co_quyen_truy_cap_phieu(
            db=db,
            request=request,
            survey_form=survey_form,
        )
    ):
        return RedirectResponse(
            url=f"/dieu-tra/{batch_id}/ho-dan",
            status_code=303,
        )
    # === BAI_30B2_XA_CONFIRM_SCOPE_GUARD_END ===

    completion_data = b131133_danh_gia_do_day_du_phieu_nhap_nhanh(
        db=db,
        survey_form=survey_form,
    )
    active_people_count = completion_data["active_people_count"]
    missing_personal_id_count = completion_data[
        "missing_personal_id_count"
    ]
    missing_year_record_count = completion_data[
        "missing_year_record_count"
    ]
    incomplete_year_record_count = completion_data[
        "incomplete_year_record_count"
    ]

    form_status = form_status.strip().upper()
    village_head_name = chuan_hoa_van_ban(village_head_name)
    household_representative_name = chuan_hoa_van_ban(
        household_representative_name
    )
    notes = notes.strip()

    parsed_survey_date, date_error = chuyen_ngay(
        survey_date,
        "Ngày điều tra",
        bat_buoc=form_status != "CHUA_DIEU_TRA",
    )

    errors: list[str] = []

    if form_status not in FORM_STATUS_LABELS:
        errors.append("Trạng thái phiếu không hợp lệ.")

    if date_error:
        errors.append(date_error)

    if parsed_survey_date and parsed_survey_date > date.today():
        errors.append("Ngày điều tra không được lớn hơn ngày hiện tại.")

    if len(village_head_name) > 200:
        errors.append("Tên trưởng thôn/xóm dài quá 200 ký tự.")

    if len(household_representative_name) > 200:
        errors.append("Tên người đại diện hộ dài quá 200 ký tự.")

    if form_status == "DA_HOAN_THANH":
        if active_people_count == 0:
            errors.append(
                "Không thể hoàn thành phiếu vì hộ chưa có đối tượng đang hoạt động."
            )
        if missing_year_record_count:
            errors.append(
                "Không thể hoàn thành phiếu: còn "
                f"{missing_year_record_count} thành viên chưa có dữ liệu năm "
                f"{survey_form.survey_batch.school_year.code}."
            )
        if incomplete_year_record_count:
            errors.append(
                "Không thể hoàn thành phiếu: còn "
                f"{incomplete_year_record_count} thành viên chưa hoàn thành "
                "thông tin năm học theo nhóm đối tượng."
            )
        if not household_confirmed:
            errors.append(
                "Không thể hoàn thành phiếu vì hộ gia đình chưa xác nhận."
            )

    if form_status == "CAN_BO_SUNG" and not notes:
        errors.append(
            "Phiếu cần bổ sung phải ghi rõ nội dung cần bổ sung."
        )

    form_data = {
        "form_status": form_status,
        "survey_date": survey_date,
        "village_head_name": village_head_name,
        "household_representative_name": (
            household_representative_name
        ),
        "household_confirmed": bool(household_confirmed),
        "commune_confirmed": (
            bool(commune_confirmed)
            if can_confirm_commune
            else survey_form.commune_confirmed_at is not None
        ),
        "notes": notes,
    }

    if errors:
        return hien_thi_trang_cap_nhat_phieu(
            request=request,
            survey_form=survey_form,
            active_people_count=active_people_count,
            thong_bao_loi=" ".join(errors),
            form_data=form_data,
            status_code=400,
        )

    now = datetime.now()

    survey_form.status = form_status
    survey_form.survey_date = parsed_survey_date
    survey_form.village_head_name = village_head_name or None
    survey_form.household_representative_name = (
        household_representative_name or None
    )
    survey_form.household_confirmed_at = (
        survey_form.household_confirmed_at or now
        if household_confirmed
        else None
    )
    if can_confirm_commune:
        survey_form.commune_confirmed_at = (
            survey_form.commune_confirmed_at or now
            if commune_confirmed
            else None
        )

    survey_form.notes = notes or None

    # Đồng bộ ảnh chụp thông tin hộ tại thời điểm cập nhật phiếu.
    survey_form.head_name_snapshot = survey_form.household.head_name
    survey_form.address_snapshot = survey_form.household.address
    survey_form.hamlet_name_snapshot = survey_form.household.hamlet_name

    db.commit()

    return RedirectResponse(
        url=(
            f"/dieu-tra/{batch_id}/ho-dan/{household_id}/phieu?"
            + urlencode({"status": "form_updated"})
        ),
        status_code=303,
    )



# =========================================================
# NHẬP NHANH HỘ DÂN CHO GIÁO VIÊN ĐIỀU TRA
# =========================================================

def tao_url_nhap_nhanh(
    *,
    batch_id: int,
    household_id: int,
    q: str = "",
    status: str | None = None,
    anchor: str = "",
) -> str:
    """Tạo URL ổn định cho màn hình nhập nhanh."""

    params: dict[str, Any] = {}
    if q:
        params["q"] = q
    if status:
        params["status"] = status

    url = f"/dieu-tra/{batch_id}/ho-dan/{household_id}/nhap-nhanh"
    if params:
        url += "?" + urlencode(params)
    if anchor:
        url += f"#{anchor}"
    return url


def lay_chuoi_phieu_nhap_nhanh(
    *,
    db: Session,
    request: Request,
    batch_id: int,
) -> list[dict[str, Any]]:
    """Lấy chuỗi phiếu đúng phạm vi quyền để điều hướng trước/sau."""

    rows = db.execute(
        select(
            SurveyForm.id.label("survey_form_id"),
            SurveyForm.household_id.label("household_id"),
            SurveyForm.form_number.label("form_number"),
            SurveyForm.status.label("form_status"),
            Household.code.label("household_code"),
            Household.head_name.label("head_name"),
            Household.hamlet_name.label("hamlet_name"),
            Household.address.label("address"),
        )
        .join(Household, Household.id == SurveyForm.household_id)
        .where(
            SurveyForm.survey_batch_id == batch_id,
            *tao_bo_loc_phieu_theo_nguoi_dung(request),
        )
        .order_by(
            Household.hamlet_name.asc(),
            Household.head_name.asc(),
            SurveyForm.id.asc(),
        )
    ).mappings().all()

    return [dict(row) for row in rows]


# === BAI_13B_12_V2_4_4_6_MOBILE_DYNAMIC_COMPLETION_START ===
def danh_gia_do_day_du_phieu_nhap_nhanh(
    *,
    db: Session,
    survey_form: SurveyForm,
) -> dict[str, Any]:
    """Đánh giá điều kiện nhập nhanh theo đúng nhóm tuổi/cấp học.

    V2.4.4.6: đồng bộ phần HIỂN THỊ với chính bộ quy tắc động đang
    được dùng khi lưu/hoàn thành phiếu, tránh báo thiếu giả trên điện thoại.
    """

    people = [
        item
        for item in survey_form.household.people
        if item.is_active
    ]
    person_ids = [int(item.id) for item in people]

    records: list[SurveyPersonYearRecord] = []
    if person_ids:
        records = db.scalars(
            select(SurveyPersonYearRecord).where(
                SurveyPersonYearRecord.survey_form_id == survey_form.id,
                SurveyPersonYearRecord.school_year_id
                == survey_form.survey_batch.school_year_id,
                SurveyPersonYearRecord.survey_person_id.in_(person_ids),
            )
        ).all()

    record_map = {
        int(item.survey_person_id): item
        for item in records
    }

    missing_personal_id_count = sum(
        not (item.personal_id or "").strip()
        for item in people
    )
    missing_year_record_count = 0
    incomplete_year_record_count = 0
    school_year = survey_form.survey_batch.school_year

    for person in people:
        record = record_map.get(int(person.id))
        if record is None:
            missing_year_record_count += 1
            continue

        progress = b131133_tien_do_nam_hoc(
            person=person,
            record=record,
            school_year=school_year,
        )
        if not bool(progress["complete"]):
            incomplete_year_record_count += 1

    return {
        "people": people,
        "record_map": record_map,
        "active_people_count": len(people),
        "missing_personal_id_count": int(missing_personal_id_count),
        "missing_year_record_count": int(missing_year_record_count),
        "incomplete_year_record_count": int(incomplete_year_record_count),
    }


# === BAI_13B_12_V2_4_4_6_MOBILE_DYNAMIC_COMPLETION_END ===

def hien_thi_trang_nhap_nhanh(
    *,
    request: Request,
    db: Session,
    survey_form: SurveyForm,
    q: str = "",
    status: str | None = None,
    thong_bao_loi: str | None = None,
    household_form_data: dict[str, Any] | None = None,
    person_form_data: dict[str, Any] | None = None,
    status_code: int = 200,
):
    """Chuẩn bị toàn bộ dữ liệu cho màn hình nhập liên tục một hộ."""

    q = q.strip()[:100]
    user = lay_thong_tin_nguoi_dung(request)
    role_code = normalize_role_code(user.get("role_code"))
    can_edit_data = can_edit_survey_data(role_code)
    can_confirm_commune = is_admin_role(role_code) or normalize_role_code(role_code) == "XA"

    batch = survey_form.survey_batch
    household = survey_form.household
    sequence = lay_chuoi_phieu_nhap_nhanh(
        db=db,
        request=request,
        batch_id=batch.id,
    )

    current_index = next(
        (
            index
            for index, item in enumerate(sequence)
            if int(item["household_id"]) == int(household.id)
        ),
        -1,
    )

    previous_item = (
        sequence[current_index - 1]
        if current_index > 0
        else None
    )
    next_item = (
        sequence[current_index + 1]
        if 0 <= current_index < len(sequence) - 1
        else None
    )

    previous_url = (
        tao_url_nhap_nhanh(
            batch_id=batch.id,
            household_id=int(previous_item["household_id"]),
        )
        if previous_item
        else None
    )
    next_url = (
        tao_url_nhap_nhanh(
            batch_id=batch.id,
            household_id=int(next_item["household_id"]),
        )
        if next_item
        else None
    )

    status_counts = {
        code: 0
        for code in FORM_STATUS_LABELS
    }
    for item in sequence:
        item_status = str(item.get("form_status") or "")
        if item_status in status_counts:
            status_counts[item_status] += 1

    total_forms = len(sequence)
    completed_forms = status_counts.get("DA_HOAN_THANH", 0)
    progress_percent = (
        round(completed_forms * 100 / total_forms)
        if total_forms
        else 0
    )

    search_results: list[dict[str, Any]] = []
    if q:
        search_value = f"%{q}%"
        rows = db.execute(
            select(
                SurveyForm.household_id.label("household_id"),
                SurveyForm.form_number.label("form_number"),
                SurveyForm.status.label("form_status"),
                Household.code.label("household_code"),
                Household.head_name.label("head_name"),
                Household.hamlet_name.label("hamlet_name"),
                Household.address.label("address"),
            )
            .join(Household, Household.id == SurveyForm.household_id)
            .where(
                SurveyForm.survey_batch_id == batch.id,
                *tao_bo_loc_phieu_theo_nguoi_dung(request),
                or_(
                    SurveyForm.form_number.ilike(search_value),
                    Household.code.ilike(search_value),
                    Household.head_name.ilike(search_value),
                    Household.address.ilike(search_value),
                    Household.phone.ilike(search_value),
                ),
            )
            .order_by(
                Household.hamlet_name.asc(),
                Household.head_name.asc(),
                SurveyForm.id.asc(),
            )
            .limit(12)
        ).mappings().all()
        search_results = [dict(row) for row in rows]

    # === BAI_13B_11_13_3_3_FIX_QUICK_ENTRY_PEOPLE ===
    completion_data = danh_gia_do_day_du_phieu_nhap_nhanh(
        db=db,
        survey_form=survey_form,
    )
    people = sorted(
        completion_data["people"],
        key=lambda item: (
            item.date_of_birth or date.max,
            item.full_name.casefold(),
            item.id,
        ),
    )
    # === FIX28B_HEAD_PERSON_PROMPT_START ===
    _fix28b_active_head_person = next(
        (
            item
            for item in people
            if item.is_active
            and la_quan_he_chu_ho(item.relationship_to_head)
        ),
        None,
    )
    household_head_needs_person = bool(
        chuan_hoa_van_ban(household.head_name or "")
        and _fix28b_active_head_person is None
    )
    # === FIX28B_HEAD_PERSON_PROMPT_END ===

    record_map = completion_data["record_map"]
    missing_personal_id_count = completion_data[
        "missing_personal_id_count"
    ]
    missing_year_record_count = completion_data[
        "missing_year_record_count"
    ]
    incomplete_year_record_count = completion_data[
        "incomplete_year_record_count"
    ]

    # === FIX28C_HEAD_AND_COMPLETION_PREFILL_START ===
    _fix28c_head_person = next(
        (
            item
            for item in people
            if item.is_active
            and la_quan_he_chu_ho(item.relationship_to_head)
        ),
        None,
    )
    fix28c_head_missing = bool(
        chuan_hoa_van_ban(household.head_name or "")
        and _fix28c_head_person is None
    )
    # === FIX28C_HEAD_AND_COMPLETION_PREFILL_HEAD_END ===

    person_summaries: list[dict[str, Any]] = []

    for person in people:
        record = record_map.get(int(person.id))
        answered = (
            sum(
                getattr(record, field_name) is not None
                for field_name in BOOLEAN_YEAR_FIELDS
            )
            if record is not None
            else 0
        )

        person_summaries.append(
            {
                "person": person,
                "year_record": record,
                "answered": answered,
                "total": len(BOOLEAN_YEAR_FIELDS),
                "learning_status": (
                    LEARNING_STATUS_LABELS.get(
                        record.learning_status,
                        "Chưa xác định",
                    )
                    if record is not None
                    else "Chưa nhập"
                ),
            }
        )

    # === GV_MOBILE_V18_SUMMARY_START ===
    # Bổ sung dữ liệu hiển thị tối giản cho màn hình giáo viên trên điện thoại.
    # Nếu hồ sơ năm hiện tại chưa được rà soát, sử dụng dữ liệu kế thừa năm trước
    # làm phần gợi ý đúng như màn hình năm học hiện có.
    for summary in person_summaries:
        person = summary["person"]
        current_record = summary["year_record"]
        previous_hint = lay_goi_y_nam_hoc_truoc(
            db=db,
            person_id=int(person.id),
            school_year_id=batch.school_year_id,
        )
        if current_record is not None and getattr(current_record, "is_reviewed", False):
            previous_hint = None

        display_record, inherited_fields = tao_ban_ghi_hien_thi_nam_hoc(
            selected_record=current_record,
            previous_hint=previous_hint,
            survey_form_id=survey_form.id,
            person_id=int(person.id),
            school_year_id=batch.school_year_id,
        )

        school_name = "—"
        class_name = "—"
        if display_record is not None:
            school_obj = (
                db.get(School, display_record.school_id)
                if getattr(display_record, "school_id", None) is not None
                else None
            )
            class_obj = (
                db.get(Classroom, display_record.class_id)
                if getattr(display_record, "class_id", None) is not None
                else None
            )
            school_name = (
                getattr(display_record, "school_name_reported", None)
                or (school_obj.name if school_obj is not None else "")
                or "—"
            )
            class_name = (
                getattr(display_record, "class_name_reported", None)
                or (class_obj.name if class_obj is not None else "")
                or "—"
            )

        summary.update(
            {
                "display_record": display_record,
                "inherited_fields": inherited_fields,
                "school_name": school_name,
                "class_name": class_name,
                "is_reviewed": bool(
                    current_record is not None
                    and getattr(current_record, "is_reviewed", False)
                ),
                "can_accept": bool(
                    display_record is not None
                    and ban_ghi_nam_hoc_co_du_lieu(display_record)
                ),
            }
        )
    # === GV_MOBILE_V18_SUMMARY_END ===

    warnings: list[str] = []
    if not people:
        warnings.append("Hộ chưa có thành viên đang theo dõi.")
    if missing_personal_id_count:
        warnings.append(
            f"{missing_personal_id_count} thành viên chưa có số định danh chính thức; "
            "hệ thống đang nhận diện bằng mã nội bộ."
        )
    if missing_year_record_count:
        warnings.append(
            f"Còn {missing_year_record_count} thành viên chưa có dữ liệu "
            f"năm {batch.school_year.code}."
        )
    if incomplete_year_record_count:
        warnings.append(
            f"Còn {incomplete_year_record_count} thành viên chưa nhập đủ "
            "thông tin năm học theo nhóm đối tượng."
        )

    completion_blockers: list[str] = []
    if not people:
        completion_blockers.append(
            "Hộ chưa có thành viên đang theo dõi."
        )
    if missing_year_record_count:
        completion_blockers.append(
            f"{missing_year_record_count} thành viên chưa có dữ liệu năm "
            f"{batch.school_year.code}."
        )
    if incomplete_year_record_count:
        completion_blockers.append(
            f"{incomplete_year_record_count} thành viên chưa hoàn thành "
            "thông tin năm học theo nhóm đối tượng."
        )
    assignments = lay_phan_cong_hien_tai(
        db=db,
        survey_form_id=survey_form.id,
    )

    if household_form_data is None:
        household_form_data = {
            "head_name": household.head_name,
            "hamlet_name": household.hamlet_name or "",
            "address": household.address,
            "phone": household.phone or "",
            "household_notes": household.notes or "",
            "form_status": survey_form.status,
            "survey_date": (
                survey_form.survey_date.isoformat()
                if survey_form.survey_date
                else ""
            ),
            "village_head_name": survey_form.village_head_name or "",
            "household_representative_name": (
                survey_form.household_representative_name or ""
            ),
            "household_confirmed": (
                survey_form.household_confirmed_at is not None
            ),
            "commune_confirmed": (
                survey_form.commune_confirmed_at is not None
            ),
            "form_notes": survey_form.notes or "",
        }

    if not household_form_data.get("household_confirmed"):
        completion_blockers.append(
            "Hộ gia đình chưa xác nhận thông tin phiếu."
        )

    if person_form_data is None:
        person_form_data = {
            "full_name": (
                household.head_name
                if household_head_needs_person
                else ""
            ),
            "date_of_birth": "",
            "gender": "",
            "ethnic_group": "Kinh",
            "relationship_to_head": (
                "Chủ hộ"
                if household_head_needs_person
                else "Con"
            ),
            "personal_id": "",
            "citizen_id": "",
            "residency_status": "THUONG_TRU",
        }

    # === BAI_13B_11_13_3_1_QUICK_PROGRESS_START ===
    for _b131133_item in person_summaries:
        if isinstance(_b131133_item, dict):
            _b131133_person = _b131133_item.get("person")
            _b131133_record = _b131133_item.get("year_record")
        else:
            _b131133_person = getattr(_b131133_item, "person", None)
            _b131133_record = getattr(_b131133_item, "year_record", None)

        _b131133_progress = b131133_tien_do_nam_hoc(
            person=_b131133_person,
            record=_b131133_record,
            school_year=survey_form.survey_batch.school_year,
        )

        if isinstance(_b131133_item, dict):
            _b131133_item["answered"] = _b131133_progress["answered"]
            _b131133_item["total"] = _b131133_progress["total"]
            _b131133_item["education_level"] = _b131133_progress["level"]
        else:
            setattr(_b131133_item, "answered", _b131133_progress["answered"])
            setattr(_b131133_item, "total", _b131133_progress["total"])
            setattr(_b131133_item, "education_level", _b131133_progress["level"])
    # === BAI_13B_11_13_3_1_QUICK_PROGRESS_END ===

    # === FIX28C_HEAD_AND_COMPLETION_PREFILL_PREFILL_START ===
    if (
        fix28c_head_missing
        and not chuan_hoa_van_ban(
            str(person_form_data.get("full_name") or "")
        )
    ):
        person_form_data["full_name"] = household.head_name
        person_form_data["relationship_to_head"] = "Chủ hộ"

    fix28c_ready_to_complete = bool(
        len(people) > 0
        and missing_personal_id_count == 0
        and missing_year_record_count == 0
        and incomplete_year_record_count == 0
        and not fix28c_head_missing
    )

    if (
        fix28c_ready_to_complete
        and survey_form.status != "DA_HOAN_THANH"
    ):
        household_form_data["form_status"] = "DA_HOAN_THANH"
        if not household_form_data.get("survey_date"):
            household_form_data["survey_date"] = date.today().isoformat()
        if not chuan_hoa_van_ban(
            str(household_form_data.get("household_representative_name") or "")
        ):
            household_form_data["household_representative_name"] = household.head_name
        household_form_data["household_confirmed"] = True
    # === FIX28C_HEAD_AND_COMPLETION_PREFILL_PREFILL_END ===

    return templates.TemplateResponse(
        request=request,
        name="surveys/quick_entry.html",
        context={
            "nguoi_dung": user,
            "batch": batch,
            "survey_form": survey_form,
            "household": household,
            "household_head_needs_person": household_head_needs_person,
            "can_edit_data": can_edit_data,
            "can_confirm_commune": can_confirm_commune,
            "form_status_labels": FORM_STATUS_LABELS,
            "residency_status_labels": RESIDENCY_STATUS_LABELS,
            "household_form_data": household_form_data,
            "person_form_data": person_form_data,
            "fix28c_head_missing": fix28c_head_missing,
            "fix28c_ready_to_complete": fix28c_ready_to_complete,
            "person_summaries": person_summaries,
            "active_people_count": len(people),
            "missing_personal_id_count": missing_personal_id_count,
            "missing_year_record_count": missing_year_record_count,
            "incomplete_year_record_count": incomplete_year_record_count,
            "warnings": warnings,
            "completion_blockers": completion_blockers,
            "completion_ready": not completion_blockers,
            "assignments": assignments,
            "total_forms": total_forms,
            "completed_forms": completed_forms,
            "status_counts": status_counts,
            "progress_percent": progress_percent,
            "current_position": current_index + 1 if current_index >= 0 else 0,
            "previous_url": previous_url,
            "next_url": next_url,
            "q": q,
            "search_results": search_results,
            "thong_bao": STATUS_MESSAGES.get(status),
            "thong_bao_loi": thong_bao_loi,
            "today": date.today().isoformat(),
        },
        status_code=status_code,
    )



@router.get(
    "/{batch_id}/ho-dan/{household_id}/nhap-nhanh",
    response_class=HTMLResponse,
)
def trang_nhap_nhanh_ho_dan(
    batch_id: int,
    household_id: int,
    request: Request,
    q: str = "",
    status: str | None = None,
    db: Session = Depends(get_db),
):
    survey_form = lay_phieu_ho(
        db=db,
        batch_id=batch_id,
        household_id=household_id,
    )

    if survey_form is None:
        return RedirectResponse(
            url=f"/dieu-tra/{batch_id}/ho-dan",
            status_code=303,
        )

    if not co_quyen_truy_cap_phieu(
        db=db, request=request, survey_form=survey_form
    ):
        return RedirectResponse(
            url=f"/dieu-tra/{batch_id}/ho-dan",
            status_code=303,
        )

    return hien_thi_trang_nhap_nhanh(
        request=request,
        db=db,
        survey_form=survey_form,
        q=q,
        status=status,
    )


@router.post(
    "/{batch_id}/ho-dan/{household_id}/nhap-nhanh/luu"
)
def luu_nhap_nhanh_ho_dan(
    batch_id: int,
    household_id: int,
    request: Request,
    head_name: Annotated[str, Form()],
    address: Annotated[str, Form()],
    hamlet_name: Annotated[str, Form()] = "",
    phone: Annotated[str, Form()] = "",
    household_notes: Annotated[str, Form()] = "",
    form_status: Annotated[str, Form()] = "DANG_DIEU_TRA",
    survey_date: Annotated[str, Form()] = "",
    village_head_name: Annotated[str, Form()] = "",
    household_representative_name: Annotated[str, Form()] = "",
    household_confirmed: Annotated[str, Form()] = "",
    commune_confirmed: Annotated[str, Form()] = "",
    form_notes: Annotated[str, Form()] = "",
    submit_action: Annotated[str, Form()] = "save",
    db: Session = Depends(get_db),
):
    survey_form = lay_phieu_ho(
        db=db,
        batch_id=batch_id,
        household_id=household_id,
    )
    if survey_form is None:
        return RedirectResponse(
            url=f"/dieu-tra/{batch_id}/ho-dan",
            status_code=303,
        )

    if not co_quyen_truy_cap_phieu(
        db=db, request=request, survey_form=survey_form
    ):
        return RedirectResponse(
            url=f"/dieu-tra/{batch_id}/ho-dan",
            status_code=303,
        )

    user = lay_thong_tin_nguoi_dung(request)
    role_code = normalize_role_code(user.get("role_code"))
    can_confirm_commune = is_admin_role(role_code) or normalize_role_code(role_code) == "XA"

    # === BAI_13B_12_V2_4_4_6_MOBILE_WRITE_GUARD_QUICK_START ===
    if not can_edit_survey_data(role_code):
        return RedirectResponse(
            url=f"/dieu-tra/{batch_id}/ho-dan",
            status_code=303,
        )
    # === BAI_13B_12_V2_4_4_6_MOBILE_WRITE_GUARD_QUICK_END ===

    head_name = chuan_hoa_van_ban(head_name)
    address = chuan_hoa_van_ban(address)
    hamlet_name = chuan_hoa_van_ban(hamlet_name)
    phone_value = chuan_hoa_so_dien_thoai(phone)
    household_notes = household_notes.strip()
    form_status = form_status.strip().upper()
    village_head_name = chuan_hoa_van_ban(village_head_name)
    household_representative_name = chuan_hoa_van_ban(
        household_representative_name
    )
    form_notes = form_notes.strip()

    parsed_survey_date, date_error = chuyen_ngay(
        survey_date,
        "Ngày điều tra",
        bat_buoc=form_status != "CHUA_DIEU_TRA",
    )

    completion_data = b131133_danh_gia_do_day_du_phieu_nhap_nhanh(
        db=db,
        survey_form=survey_form,
    )
    active_people_count = completion_data["active_people_count"]
    missing_personal_id_count = completion_data[
        "missing_personal_id_count"
    ]
    missing_year_record_count = completion_data[
        "missing_year_record_count"
    ]
    incomplete_year_record_count = completion_data[
        "incomplete_year_record_count"
    ]

    errors: list[str] = []
    if (
        survey_form.survey_batch.status == "DA_KET_THUC"
        or survey_form.survey_batch.is_locked
    ):
        errors.append("Đợt điều tra đã khóa/kết thúc, không thể cập nhật.")
    if not head_name:
        errors.append("Họ và tên chủ hộ không được để trống.")
    if len(head_name) > 200:
        errors.append("Họ và tên chủ hộ dài quá 200 ký tự.")
    if not address:
        errors.append("Địa chỉ hộ không được để trống.")
    if len(hamlet_name) > 200:
        errors.append("Tên thôn/xóm dài quá 200 ký tự.")
    if phone_value and len(phone_value) > 30:
        errors.append("Số điện thoại dài quá 30 ký tự.")
    if form_status not in FORM_STATUS_LABELS:
        errors.append("Trạng thái phiếu không hợp lệ.")
    if date_error:
        errors.append(date_error)
    if parsed_survey_date and parsed_survey_date > date.today():
        errors.append("Ngày điều tra không được lớn hơn ngày hiện tại.")
    if form_status == "DA_HOAN_THANH":
        if active_people_count == 0:
            errors.append(
                "Không thể hoàn thành phiếu vì hộ chưa có thành viên đang theo dõi."
            )
        if missing_year_record_count:
            errors.append(
                "Không thể hoàn thành phiếu: còn "
                f"{missing_year_record_count} thành viên chưa có dữ liệu năm "
                f"{survey_form.survey_batch.school_year.code}."
            )
        if incomplete_year_record_count:
            errors.append(
                "Không thể hoàn thành phiếu: còn "
                f"{incomplete_year_record_count} thành viên chưa hoàn thành "
                "thông tin năm học theo nhóm đối tượng."
            )
        if not household_confirmed:
            errors.append(
                "Không thể hoàn thành phiếu vì hộ gia đình chưa xác nhận."
            )
    if form_status == "CAN_BO_SUNG" and not form_notes:
        errors.append(
            "Phiếu cần bổ sung phải ghi rõ nội dung cần bổ sung."
        )

    household_form_data = {
        "head_name": head_name,
        "hamlet_name": hamlet_name,
        "address": address,
        "phone": phone,
        "household_notes": household_notes,
        "form_status": form_status,
        "survey_date": survey_date,
        "village_head_name": village_head_name,
        "household_representative_name": household_representative_name,
        "household_confirmed": bool(household_confirmed),
        "commune_confirmed": (
            bool(commune_confirmed)
            if can_confirm_commune
            else survey_form.commune_confirmed_at is not None
        ),
        "form_notes": form_notes,
    }

    if errors:
        return hien_thi_trang_nhap_nhanh(
            request=request,
            db=db,
            survey_form=survey_form,
            thong_bao_loi=" ".join(errors),
            household_form_data=household_form_data,
            status_code=400,
        )

    sequence = lay_chuoi_phieu_nhap_nhanh(
        db=db,
        request=request,
        batch_id=batch_id,
    )
    current_index = next(
        (
            index
            for index, item in enumerate(sequence)
            if int(item["household_id"]) == int(household_id)
        ),
        -1,
    )
    next_household_id = (
        int(sequence[current_index + 1]["household_id"])
        if 0 <= current_index < len(sequence) - 1
        else None
    )

    household = survey_form.household
    household.head_name = head_name
    household.hamlet_name = hamlet_name or None
    household.address = address
    household.phone = phone_value
    household.notes = household_notes or None

    survey_form.status = form_status
    survey_form.survey_date = parsed_survey_date
    survey_form.village_head_name = village_head_name or None
    survey_form.household_representative_name = (
        household_representative_name or None
    )
    survey_form.household_confirmed_at = (
        survey_form.household_confirmed_at or datetime.now()
        if household_confirmed
        else None
    )
    if can_confirm_commune:
        survey_form.commune_confirmed_at = (
            survey_form.commune_confirmed_at or datetime.now()
            if commune_confirmed
            else None
        )
    survey_form.notes = form_notes or None

    survey_form.head_name_snapshot = head_name
    survey_form.address_snapshot = address
    survey_form.hamlet_name_snapshot = hamlet_name or None

    db.commit()

    if submit_action == "save_next" and next_household_id is not None:
        return RedirectResponse(
            url=tao_url_nhap_nhanh(
                batch_id=batch_id,
                household_id=next_household_id,
                status="quick_saved_next",
            ),
            status_code=303,
        )

    status_value = (
        "quick_saved_last"
        if submit_action == "save_next" and next_household_id is None
        else "quick_saved"
    )
    return RedirectResponse(
        url=tao_url_nhap_nhanh(
            batch_id=batch_id,
            household_id=household_id,
            status=status_value,
        ),
        status_code=303,
    )


@router.post(
    "/{batch_id}/ho-dan/{household_id}/nhap-nhanh/them-doi-tuong"
)
def them_doi_tuong_tu_nhap_nhanh(
    batch_id: int,
    household_id: int,
    request: Request,
    full_name: Annotated[str, Form()],
    date_of_birth: Annotated[str, Form()],
    gender: Annotated[str, Form()],
    ethnic_group: Annotated[str, Form()] = "Kinh",
    relationship_to_head: Annotated[str, Form()] = "Con",
    personal_id: Annotated[str, Form()] = "",
    citizen_id: Annotated[str, Form()] = "",
    residency_status: Annotated[str, Form()] = "THUONG_TRU",
    db: Session = Depends(get_db),
):
    survey_form = lay_phieu_ho(
        db=db,
        batch_id=batch_id,
        household_id=household_id,
    )
    if survey_form is None:
        return RedirectResponse(
            url=f"/dieu-tra/{batch_id}/ho-dan",
            status_code=303,
        )

    if not co_quyen_truy_cap_phieu(
        db=db, request=request, survey_form=survey_form
    ):
        return RedirectResponse(
            url=f"/dieu-tra/{batch_id}/ho-dan",
            status_code=303,
        )

    # === BAI_13B_12_V2_4_4_6_MOBILE_WRITE_GUARD_ADD_PERSON_START ===
    role_code = normalize_role_code(
        lay_thong_tin_nguoi_dung(request).get("role_code")
    )
    if not can_edit_survey_data(role_code):
        return RedirectResponse(
            url=f"/dieu-tra/{batch_id}/ho-dan",
            status_code=303,
        )
    # === BAI_13B_12_V2_4_4_6_MOBILE_WRITE_GUARD_ADD_PERSON_END ===

    full_name = chuan_hoa_van_ban(full_name)
    gender = chuan_hoa_van_ban(gender)
    ethnic_group = chuan_hoa_van_ban(ethnic_group)
    relationship_to_head = chuan_hoa_van_ban(relationship_to_head)
    personal_id = chuan_hoa_ma(personal_id)
    citizen_id = chuan_hoa_ma(citizen_id)

    person_form_data = {
        "full_name": full_name,
        "date_of_birth": date_of_birth,
        "gender": gender,
        "ethnic_group": ethnic_group,
        "relationship_to_head": relationship_to_head,
        "personal_id": personal_id,
        "citizen_id": citizen_id,
        "residency_status": residency_status,
    }

    errors: list[str] = []
    if (
        survey_form.survey_batch.status == "DA_KET_THUC"
        or survey_form.survey_batch.is_locked
    ):
        errors.append("Đợt điều tra đã khóa/kết thúc, không thể thêm thành viên.")
    if not full_name:
        errors.append("Họ và tên thành viên không được để trống.")
    if len(full_name) > 200:
        errors.append("Họ và tên dài quá 200 ký tự.")

    parsed_birth_date, birth_error = chuyen_ngay(
        date_of_birth,
        "Ngày sinh",
        bat_buoc=True,
    )
    if birth_error:
        errors.append(birth_error)
    if parsed_birth_date and parsed_birth_date > date.today():
        errors.append("Ngày sinh không được lớn hơn ngày hiện tại.")

    if gender not in {"Nam", "Nữ", "Khác"}:
        errors.append("Giới tính không hợp lệ.")
    if not ethnic_group:
        errors.append("Dân tộc không được để trống.")
    if not relationship_to_head:
        errors.append("Quan hệ với chủ hộ không được để trống.")
    if residency_status not in RESIDENCY_STATUS_LABELS:
        errors.append("Trạng thái cư trú không hợp lệ.")
    if len(personal_id) > 50:
        errors.append("Số định danh dài quá 50 ký tự.")
    if len(citizen_id) > 50:
        errors.append("Căn cước công dân dài quá 50 ký tự.")

    if personal_id:
        duplicate_personal_id = db.scalar(
            select(SurveyPerson).where(
                SurveyPerson.personal_id == personal_id,
                SurveyPerson.is_active.is_(True),
            )
        )
        if duplicate_personal_id is not None:
            errors.append(
                "Số định danh cá nhân đã được sử dụng cho đối tượng khác."
            )

    if citizen_id:
        duplicate_citizen_id = db.scalar(
            select(SurveyPerson).where(
                SurveyPerson.citizen_id == citizen_id,
                SurveyPerson.is_active.is_(True),
            )
        )
        if duplicate_citizen_id is not None:
            errors.append("CCCD đã được sử dụng cho đối tượng khác.")

    duplicate_name = None
    if full_name and parsed_birth_date:
        duplicate_name = db.scalar(
            select(SurveyPerson).where(
                SurveyPerson.household_id == household_id,
                func.lower(SurveyPerson.full_name) == full_name.lower(),
                SurveyPerson.date_of_birth == parsed_birth_date,
                SurveyPerson.is_active.is_(True),
            )
        )
    if duplicate_name is not None:
        errors.append(
            "Thành viên có cùng họ tên và ngày sinh đã tồn tại trong hộ."
        )

    will_be_head = la_quan_he_chu_ho(relationship_to_head)
    if will_be_head:
        existing_head = next(
            (
                item
                for item in survey_form.household.people
                if item.is_active
                and la_quan_he_chu_ho(item.relationship_to_head)
            ),
            None,
        )
        if existing_head is not None:
            errors.append("Trong hộ đã có một thành viên được ghi là Chủ hộ.")

    if errors:
        return hien_thi_trang_nhap_nhanh(
            request=request,
            db=db,
            survey_form=survey_form,
            thong_bao_loi=" ".join(errors),
            person_form_data=person_form_data,
            status_code=400,
        )

    person = SurveyPerson(
        code=f"TMP-{uuid4().hex[:12]}",
        household_id=household_id,
        student_id=None,
        full_name=full_name,
        date_of_birth=parsed_birth_date,
        gender=gender,
        ethnic_group=ethnic_group,
        relationship_to_head=relationship_to_head,
        personal_id=personal_id or None,
        citizen_id=citizen_id or None,
        ministry_student_code=None,
        permanent_address=survey_form.household.address,
        current_address=survey_form.household.address,
        residency_status=residency_status,
        special_circumstances=None,
        notes=None,
        is_active=True,
    )
    db.add(person)
    db.flush()
    person.code = f"DT-{person.id:08d}"


    # === FIX28B_CREATE_YEAR_RECORD_FOR_NEW_PERSON_START ===
    _fix28b_year_id = int(survey_form.survey_batch.school_year_id)
    _fix28b_year_record = db.scalar(
        select(SurveyPersonYearRecord).where(
            SurveyPersonYearRecord.survey_form_id == survey_form.id,
            SurveyPersonYearRecord.survey_person_id == person.id,
            SurveyPersonYearRecord.school_year_id == _fix28b_year_id,
        )
    )
    if _fix28b_year_record is None:
        _fix28b_year_record = SurveyPersonYearRecord(
            survey_form_id=survey_form.id,
            survey_person_id=person.id,
            school_year_id=_fix28b_year_id,
            learning_status="CHUA_XAC_DINH",
        )
        db.add(_fix28b_year_record)
    # === FIX28B_CREATE_YEAR_RECORD_FOR_NEW_PERSON_END ===

    if will_be_head:
        survey_form.household.head_name = full_name
        survey_form.head_name_snapshot = full_name

    if survey_form.status == "CHUA_DIEU_TRA":
        survey_form.status = "DANG_DIEU_TRA"

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return hien_thi_trang_nhap_nhanh(
            request=request,
            db=db,
            survey_form=survey_form,
            thong_bao_loi=(
                "Không thể lưu thành viên. Thông tin định danh có thể đã tồn tại."
            ),
            person_form_data=person_form_data,
            status_code=400,
        )

    return RedirectResponse(
        url=tao_url_nhap_nhanh(
            batch_id=batch_id,
            household_id=household_id,
            status="quick_person_created",
            anchor="members",
        ),
        status_code=303,
    )




# === GV_MOBILE_V18_ACCEPT_START ===

@router.post(
    "/{batch_id}/ho-dan/{household_id}/nhap-nhanh/{person_id}/chap-nhan"
)
def chap_nhan_thanh_vien_nhap_nhanh_mobile(
    batch_id: int,
    household_id: int,
    person_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """Chấp nhận dữ liệu đang hiển thị mà không buộc giáo viên mở form sửa."""

    survey_form = lay_phieu_ho(
        db=db,
        batch_id=batch_id,
        household_id=household_id,
    )
    if survey_form is None:
        return RedirectResponse(
            url=f"/dieu-tra/{batch_id}/ho-dan",
            status_code=303,
        )

    user = lay_thong_tin_nguoi_dung(request)
    role_code = normalize_role_code(user.get("role_code"))
    if not can_edit_survey_data(role_code):
        return RedirectResponse(
            url=tao_url_nhap_nhanh(
                batch_id=batch_id,
                household_id=household_id,
            ),
            status_code=303,
        )

    allowed_form_id = db.scalar(
        select(SurveyForm.id).where(
            SurveyForm.id == survey_form.id,
            *tao_bo_loc_phieu_theo_nguoi_dung(request),
        )
    )
    if allowed_form_id is None:
        return RedirectResponse(
            url=f"/dieu-tra/{batch_id}/ho-dan",
            status_code=303,
        )

    if survey_form.survey_batch.status == "DA_KET_THUC" or survey_form.survey_batch.is_locked:
        return RedirectResponse(
            url=tao_url_nhap_nhanh(
                batch_id=batch_id,
                household_id=household_id,
            ),
            status_code=303,
        )

    person = db.scalar(
        select(SurveyPerson).where(
            SurveyPerson.id == person_id,
            SurveyPerson.household_id == household_id,
            SurveyPerson.is_active.is_(True),
        )
    )
    if person is None:
        return RedirectResponse(
            url=tao_url_nhap_nhanh(
                batch_id=batch_id,
                household_id=household_id,
            ),
            status_code=303,
        )

    school_year_id = int(survey_form.survey_batch.school_year_id)
    current_record = db.scalar(
        select(SurveyPersonYearRecord).where(
            SurveyPersonYearRecord.survey_form_id == survey_form.id,
            SurveyPersonYearRecord.survey_person_id == person.id,
            SurveyPersonYearRecord.school_year_id == school_year_id,
        )
    )

    previous_hint = lay_goi_y_nam_hoc_truoc(
        db=db,
        person_id=int(person.id),
        school_year_id=school_year_id,
    )
    if current_record is not None and getattr(current_record, "is_reviewed", False):
        previous_hint = None

    display_record, _ = tao_ban_ghi_hien_thi_nam_hoc(
        selected_record=current_record,
        previous_hint=previous_hint,
        survey_form_id=survey_form.id,
        person_id=int(person.id),
        school_year_id=school_year_id,
    )

    if display_record is None or not ban_ghi_nam_hoc_co_du_lieu(display_record):
        return RedirectResponse(
            url=tao_url_nhap_nhanh(
                batch_id=batch_id,
                household_id=household_id,
                status="mobile_person_need_edit",
                anchor="members",
            ),
            status_code=303,
        )

    record = current_record
    if record is None:
        record = SurveyPersonYearRecord(
            survey_form_id=survey_form.id,
            survey_person_id=person.id,
            school_year_id=school_year_id,
            learning_status=(
                getattr(display_record, "learning_status", None)
                or "CHUA_XAC_DINH"
            ),
        )
        db.add(record)

    fields_to_copy = (
        "school_id",
        "class_id",
        "school_name_reported",
        "class_name_reported",
        "learning_status",
        "highest_completed_grade",
        "education_attainment_level",
        "is_literacy_target",
        "literacy_status",
        "completed_grade_3",
        "completed_grade_5",
        "completed_primary_program",
        "completed_lower_secondary_program",
        "post_lower_secondary_path",
        "completed_preschool_5",
        "special_circumstances",
        "attends_required_days",
        "attends_regularly",
        "prepared_vietnamese",
        "weight_monitored",
        "underweight",
        "height_monitored",
        "stunted",
        "disability_status",
        "disability_can_learn",
        "disability_access_education",
        "disability_type",
        "disability_level",
        "disability_certificate",
        "inclusive_education",
        "disability_support",
        "disability_support_details",
        "notes",
        "attends_two_sessions_per_day",
    )
    for field_name in fields_to_copy:
        setattr(record, field_name, getattr(display_record, field_name, None))

    record.is_reviewed = True
    if survey_form.status == "CHUA_DIEU_TRA":
        survey_form.status = "DANG_DIEU_TRA"

    db.commit()

    return RedirectResponse(
        url=tao_url_nhap_nhanh(
            batch_id=batch_id,
            household_id=household_id,
            status="mobile_person_accepted",
            anchor="members",
        ),
        status_code=303,
    )

# === GV_MOBILE_V18_ACCEPT_END ===

# =========================================================
# KIỂM TRA CHẤT LƯỢNG DỮ LIỆU ĐIỀU TRA
# =========================================================

def _gia_tri_so(value: Any) -> int:
    """Chuyển giá trị tổng hợp từ SQLite thành số nguyên an toàn."""

    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _khac_van_ban(value_a: Any, value_b: Any) -> bool:
    """So sánh hai chuỗi sau khi bỏ khoảng trắng thừa."""

    return chuan_hoa_van_ban(str(value_a or "")) != chuan_hoa_van_ban(
        str(value_b or "")
    )


def tao_du_lieu_kiem_tra_chat_luong(
    *,
    request: Request,
    db: Session,
    batch: SurveyBatch,
    q: str = "",
    hamlet: str = "",
    form_status: str = "",
    issue: str = "",
    page_size: int = DATA_QUALITY_PAGE_SIZE,
    page: int = 1,
    paginate: bool = True,
    use_report_scope: bool = False,
) -> dict[str, Any]:
    """
    Đối chiếu các điều kiện tối thiểu của từng phiếu trong đúng phạm vi tài khoản.

    Báo cáo chỉ đọc dữ liệu hiện có, không thêm, sửa hoặc xóa bản ghi.
    """

    q = q.strip()[:100]
    hamlet = chuan_hoa_van_ban(hamlet)[:200]

    if form_status not in FORM_STATUS_LABELS:
        form_status = ""

    if issue not in DATA_QUALITY_FILTER_LABELS:
        issue = ""

    if page_size not in DATA_QUALITY_PAGE_SIZE_OPTIONS:
        page_size = DATA_QUALITY_PAGE_SIZE

    try:
        page = max(int(page), 1)
    except (TypeError, ValueError):
        page = 1

    scope_filters = [
        SurveyForm.survey_batch_id == batch.id,
        *(
            tao_bo_loc_bao_cao_theo_nguoi_dung(request)
            if use_report_scope
            else tao_bo_loc_phieu_theo_nguoi_dung(request)
        ),
    ]

    missing_personal_id_condition = or_(
        SurveyPerson.personal_id.is_(None),
        func.trim(SurveyPerson.personal_id) == "",
    )
    missing_basic_condition = or_(
        SurveyPerson.date_of_birth.is_(None),
        SurveyPerson.gender.is_(None),
        func.trim(SurveyPerson.gender) == "",
        SurveyPerson.ethnic_group.is_(None),
        func.trim(SurveyPerson.ethnic_group) == "",
        SurveyPerson.relationship_to_head.is_(None),
        func.trim(SurveyPerson.relationship_to_head) == "",
    )
    incomplete_indicator_condition = or_(
        *[
            getattr(SurveyPersonYearRecord, field_name).is_(None)
            for field_name in BOOLEAN_YEAR_FIELDS
        ]
    )

    people_summary = (
        select(
            SurveyPerson.household_id.label("household_id"),
            func.count(SurveyPerson.id).label("active_people_count"),
            func.sum(
                case(
                    (missing_personal_id_condition, 1),
                    else_=0,
                )
            ).label("missing_personal_id_count"),
            func.sum(
                case(
                    (missing_basic_condition, 1),
                    else_=0,
                )
            ).label("missing_basic_count"),
        )
        .where(SurveyPerson.is_active.is_(True))
        .group_by(SurveyPerson.household_id)
        .subquery()
    )

    year_summary = (
        select(
            SurveyPersonYearRecord.survey_form_id.label("survey_form_id"),
            func.count(
                func.distinct(SurveyPersonYearRecord.survey_person_id)
            ).label("year_record_count"),
            func.sum(
                case(
                    (incomplete_indicator_condition, 1),
                    else_=0,
                )
            ).label("incomplete_year_record_count"),
        )
        .join(
            SurveyPerson,
            SurveyPerson.id == SurveyPersonYearRecord.survey_person_id,
        )
        .where(
            SurveyPersonYearRecord.school_year_id == batch.school_year_id,
            SurveyPerson.is_active.is_(True),
        )
        .group_by(SurveyPersonYearRecord.survey_form_id)
        .subquery()
    )

    assignment_summary = (
        select(
            SurveyFormInvestigator.survey_form_id.label("survey_form_id"),
            func.count(
                func.distinct(SurveyFormInvestigator.user_id)
            ).label("assignment_count"),
        )
        .join(User, User.id == SurveyFormInvestigator.user_id)
        .where(User.is_active.is_(True))
        .group_by(SurveyFormInvestigator.survey_form_id)
        .subquery()
    )

    filters: list[Any] = [*scope_filters]

    if q:
        search_value = f"%{q}%"
        filters.append(
            or_(
                SurveyForm.form_number.ilike(search_value),
                Household.code.ilike(search_value),
                Household.head_name.ilike(search_value),
                Household.hamlet_name.ilike(search_value),
                Household.address.ilike(search_value),
                Household.phone.ilike(search_value),
                Household.people.any(
                    and_(
                        SurveyPerson.is_active.is_(True),
                        or_(
                            SurveyPerson.code.ilike(search_value),
                            SurveyPerson.full_name.ilike(search_value),
                            SurveyPerson.personal_id.ilike(search_value),
                            SurveyPerson.ministry_student_code.ilike(
                                search_value
                            ),
                        ),
                    )
                ),
            )
        )

    if hamlet:
        filters.append(Household.hamlet_name == hamlet)

    if form_status:
        filters.append(SurveyForm.status == form_status)

    rows = db.execute(
        select(
            SurveyForm.id.label("survey_form_id"),
            SurveyForm.household_id.label("household_id"),
            SurveyForm.form_number.label("form_number"),
            SurveyForm.status.label("form_status"),
            SurveyForm.survey_date.label("survey_date"),
            SurveyForm.household_confirmed_at.label("household_confirmed_at"),
            SurveyForm.commune_confirmed_at.label("commune_confirmed_at"),
            SurveyForm.notes.label("form_notes"),
            SurveyForm.head_name_snapshot.label("head_name_snapshot"),
            SurveyForm.address_snapshot.label("address_snapshot"),
            SurveyForm.hamlet_name_snapshot.label("hamlet_name_snapshot"),
            SurveyForm.updated_at.label("updated_at"),
            Household.code.label("household_code"),
            Household.head_name.label("head_name"),
            Household.hamlet_name.label("hamlet_name"),
            Household.address.label("address"),
            Household.phone.label("phone"),
            func.coalesce(
                people_summary.c.active_people_count,
                0,
            ).label("active_people_count"),
            func.coalesce(
                people_summary.c.missing_personal_id_count,
                0,
            ).label("missing_personal_id_count"),
            func.coalesce(
                people_summary.c.missing_basic_count,
                0,
            ).label("missing_basic_count"),
            func.coalesce(
                year_summary.c.year_record_count,
                0,
            ).label("year_record_count"),
            func.coalesce(
                year_summary.c.incomplete_year_record_count,
                0,
            ).label("incomplete_year_record_count"),
            func.coalesce(
                assignment_summary.c.assignment_count,
                0,
            ).label("assignment_count"),
        )
        .join(Household, Household.id == SurveyForm.household_id)
        .outerjoin(
            people_summary,
            people_summary.c.household_id == Household.id,
        )
        .outerjoin(
            year_summary,
            year_summary.c.survey_form_id == SurveyForm.id,
        )
        .outerjoin(
            assignment_summary,
            assignment_summary.c.survey_form_id == SurveyForm.id,
        )
        .where(*filters)
        .order_by(
            Household.hamlet_name.asc(),
            Household.head_name.asc(),
            SurveyForm.id.asc(),
        )
    ).mappings().all()


    # === BAI_13B_11_13_3_6_DYNAMIC_DATA_QUALITY_START ===
    # Tính tiến độ theo đúng nhóm MN/TH/THCS/XMC.
    _b1311336_form_ids = [
        int(_row["survey_form_id"])
        for _row in rows
    ]
    _b1311336_household_ids = [
        int(_row["household_id"])
        for _row in rows
    ]

    _b1311336_people: list[SurveyPerson] = []
    if _b1311336_household_ids:
        _b1311336_people = list(
            db.scalars(
                select(SurveyPerson)
                .where(
                    SurveyPerson.household_id.in_(
                        _b1311336_household_ids
                    ),
                    SurveyPerson.is_active.is_(True),
                )
                .order_by(
                    SurveyPerson.household_id.asc(),
                    SurveyPerson.date_of_birth.asc(),
                    SurveyPerson.full_name.asc(),
                    SurveyPerson.id.asc(),
                )
            ).all()
        )

    _b1311336_people_by_household: dict[int, list[SurveyPerson]] = {}
    for _person in _b1311336_people:
        _b1311336_people_by_household.setdefault(
            int(_person.household_id),
            [],
        ).append(_person)

    _b1311336_person_ids = [
        int(_person.id)
        for _person in _b1311336_people
    ]

    _b1311336_records: list[SurveyPersonYearRecord] = []
    if _b1311336_form_ids and _b1311336_person_ids:
        _b1311336_records = list(
            db.scalars(
                select(SurveyPersonYearRecord)
                .where(
                    SurveyPersonYearRecord.survey_form_id.in_(
                        _b1311336_form_ids
                    ),
                    SurveyPersonYearRecord.school_year_id
                    == batch.school_year_id,
                    SurveyPersonYearRecord.survey_person_id.in_(
                        _b1311336_person_ids
                    ),
                )
                .order_by(
                    SurveyPersonYearRecord.updated_at.desc(),
                    SurveyPersonYearRecord.id.desc(),
                )
            ).all()
        )

    _b1311336_record_by_key: dict[
        tuple[int, int],
        SurveyPersonYearRecord,
    ] = {}

    for _record in _b1311336_records:
        _key = (
            int(_record.survey_form_id),
            int(_record.survey_person_id),
        )
        _b1311336_record_by_key.setdefault(
            _key,
            _record,
        )

    _b1311336_quality_progress: dict[
        int,
        dict[str, int],
    ] = {}

    for _row in rows:
        _form_id = int(_row["survey_form_id"])
        _household_id = int(_row["household_id"])

        _missing_year = 0
        _incomplete_year = 0

        for _person in _b1311336_people_by_household.get(
            _household_id,
            [],
        ):
            _record = _b1311336_record_by_key.get(
                (
                    _form_id,
                    int(_person.id),
                )
            )

            if _record is None:
                _missing_year += 1
                continue

            _progress = b131133_tien_do_nam_hoc(
                person=_person,
                record=_record,
                school_year=batch.school_year,
            )

            if not bool(_progress["complete"]):
                _incomplete_year += 1

        _b1311336_quality_progress[_form_id] = {
            "missing_year_record_count": int(_missing_year),
            "incomplete_year_record_count": int(_incomplete_year),
        }
    # === BAI_13B_11_13_3_6_DYNAMIC_DATA_QUALITY_END ===

    items: list[dict[str, Any]] = []

    for raw_row in rows:
        row = dict(raw_row)
        active_people_count = _gia_tri_so(row["active_people_count"])
        assignment_count = _gia_tri_so(row["assignment_count"])
        missing_personal_id_count = _gia_tri_so(
            row["missing_personal_id_count"]
        )
        missing_basic_count = _gia_tri_so(row["missing_basic_count"])
        year_record_count = _gia_tri_so(row["year_record_count"])

        _b1311336_counts = _b1311336_quality_progress.get(
            int(row["survey_form_id"]),
            {
                "missing_year_record_count": max(
                    active_people_count - year_record_count,
                    0,
                ),
                "incomplete_year_record_count": _gia_tri_so(
                    row["incomplete_year_record_count"]
                ),
            },
        )

        missing_year_record_count = int(
            _b1311336_counts["missing_year_record_count"]
        )
        incomplete_year_record_count = int(
            _b1311336_counts["incomplete_year_record_count"]
        )

        issues: list[dict[str, str]] = []

        def add_issue(
            code: str,
            detail: str,
            severity: str = "error",
        ) -> None:
            issues.append(
                {
                    "code": code,
                    "label": DATA_QUALITY_ISSUE_LABELS[code],
                    "detail": detail,
                    "severity": severity,
                }
            )

        if assignment_count == 0:
            add_issue(
                "CHUA_PHAN_CONG",
                "Phiếu chưa có cán bộ quản lý hoặc giáo viên phụ trách.",
            )

        if active_people_count == 0:
            add_issue(
                "KHONG_CO_DOI_TUONG",
                "Hộ chưa có thành viên đang theo dõi.",
            )
        else:
            if missing_basic_count:
                add_issue(
                    "THIEU_THONG_TIN_CA_NHAN",
                    f"Còn {missing_basic_count} đối tượng thiếu ngày sinh, "
                    "giới tính, dân tộc hoặc quan hệ với chủ hộ.",
                )

            if missing_personal_id_count:
                add_issue(
                    "THIEU_SO_DINH_DANH",
                    f"Còn {missing_personal_id_count} đối tượng thiếu "
                    "số định danh cá nhân.",
                )

            if missing_year_record_count:
                add_issue(
                    "THIEU_DU_LIEU_NAM",
                    f"Còn {missing_year_record_count} đối tượng chưa có "
                    f"dữ liệu năm học {batch.school_year.code}.",
                )

            if incomplete_year_record_count:
                add_issue(
                    "THIEU_CHI_BAO",
                    f"Còn {incomplete_year_record_count} đối tượng chưa hoàn thành "
                    "thông tin năm học theo nhóm đối tượng.",
                )

        if (
            row["form_status"] != "CHUA_DIEU_TRA"
            and row["survey_date"] is None
        ):
            add_issue(
                "THIEU_NGAY_DIEU_TRA",
                "Phiếu đã bắt đầu xử lý nhưng chưa có ngày điều tra.",
            )

        if row["form_status"] == "DA_HOAN_THANH":
            if row["household_confirmed_at"] is None:
                add_issue(
                    "CHUA_HO_XAC_NHAN",
                    "Phiếu đã hoàn thành nhưng chưa có xác nhận của hộ gia đình.",
                )

            if row["commune_confirmed_at"] is None:
                add_issue(
                    "CHUA_XA_XAC_NHAN",
                    "Phiếu đã hoàn thành nhưng chưa được xã/phường xác nhận.",
                    severity="warning",
                )

        if (
            row["form_status"] == "CAN_BO_SUNG"
            and not str(row["form_notes"] or "").strip()
        ):
            add_issue(
                "THIEU_NOI_DUNG_BO_SUNG",
                "Trạng thái Cần bổ sung phải ghi rõ nội dung cần bổ sung.",
            )

        snapshot_changed = (
            _khac_van_ban(row["head_name_snapshot"], row["head_name"])
            or _khac_van_ban(row["address_snapshot"], row["address"])
            or _khac_van_ban(
                row["hamlet_name_snapshot"],
                row["hamlet_name"],
            )
        )
        if snapshot_changed:
            add_issue(
                "CHUA_DONG_BO_THONG_TIN_HO",
                "Thông tin hộ đã thay đổi sau lần đồng bộ gần nhất của phiếu.",
                severity="warning",
            )

        blocking_issue_count = sum(
            item["severity"] == "error"
            for item in issues
        )

        if (
            row["form_status"] != "DA_HOAN_THANH"
            and blocking_issue_count == 0
        ):
            add_issue(
                "CHUA_HOAN_THANH",
                "Dữ liệu tối thiểu đã đủ; có thể kiểm tra và đánh dấu hoàn thành.",
                severity="warning",
            )

        if blocking_issue_count:
            quality_code = "CAN_XU_LY"
            quality_label = "Cần xử lý"
        elif row["form_status"] != "DA_HOAN_THANH":
            quality_code = "SAN_SANG_HOAN_THANH"
            quality_label = "Sẵn sàng hoàn thành"
        elif issues:
            quality_code = "CAN_KIEM_TRA"
            quality_label = "Cần kiểm tra"
        else:
            quality_code = "DAT_YEU_CAU"
            quality_label = "Đạt yêu cầu"

        row.update(
            {
                "active_people_count": active_people_count,
                "assignment_count": assignment_count,
                "missing_personal_id_count": missing_personal_id_count,
                "missing_basic_count": missing_basic_count,
                "missing_year_record_count": missing_year_record_count,
                "incomplete_year_record_count": (
                    incomplete_year_record_count
                ),
                "issues": issues,
                "issue_codes": {item["code"] for item in issues},
                "blocking_issue_count": int(blocking_issue_count),
                "warning_issue_count": sum(
                    item["severity"] == "warning"
                    for item in issues
                ),
                "quality_code": quality_code,
                "quality_label": quality_label,
                "form_status_label": FORM_STATUS_LABELS.get(
                    row["form_status"],
                    row["form_status"],
                ),
            }
        )
        items.append(row)

    summary = {
        "total_forms": len(items),
        "passed_forms": sum(
            item["quality_code"] == "DAT_YEU_CAU"
            for item in items
        ),
        "ready_forms": sum(
            item["quality_code"] == "SAN_SANG_HOAN_THANH"
            for item in items
        ),
        "need_review_forms": sum(
            item["quality_code"] == "CAN_KIEM_TRA"
            for item in items
        ),
        "need_action_forms": sum(
            item["quality_code"] == "CAN_XU_LY"
            for item in items
        ),
        "unassigned_forms": sum(
            "CHUA_PHAN_CONG" in item["issue_codes"]
            for item in items
        ),
        "missing_personal_id_people": sum(
            item["missing_personal_id_count"]
            for item in items
        ),
        "missing_year_record_people": sum(
            item["missing_year_record_count"]
            for item in items
        ),
        "incomplete_year_record_people": sum(
            item["incomplete_year_record_count"]
            for item in items
        ),
    }

    if issue == "DAT_YEU_CAU":
        filtered_items = [
            item for item in items
            if item["quality_code"] == "DAT_YEU_CAU"
        ]
    elif issue == "SAN_SANG_HOAN_THANH":
        filtered_items = [
            item for item in items
            if item["quality_code"] == "SAN_SANG_HOAN_THANH"
        ]
    elif issue == "CAN_KIEM_TRA":
        filtered_items = [
            item for item in items
            if item["quality_code"] == "CAN_KIEM_TRA"
        ]
    elif issue == "CAN_XU_LY":
        filtered_items = [
            item for item in items
            if item["quality_code"] == "CAN_XU_LY"
        ]
    elif issue:
        filtered_items = [
            item for item in items
            if issue in item["issue_codes"]
        ]
    else:
        filtered_items = items

    total_records = len(filtered_items)
    total_pages = max(ceil(total_records / page_size), 1)

    if page > total_pages:
        page = total_pages

    if paginate:
        start_index = (page - 1) * page_size
        displayed_items = filtered_items[
            start_index:start_index + page_size
        ]
    else:
        start_index = 0
        displayed_items = filtered_items

    hamlets = [
        value
        for value in db.scalars(
            select(Household.hamlet_name)
            .join(
                SurveyForm,
                SurveyForm.household_id == Household.id,
            )
            .where(
                *scope_filters,
                Household.hamlet_name.is_not(None),
                func.trim(Household.hamlet_name) != "",
            )
            .distinct()
            .order_by(Household.hamlet_name.asc())
        ).all()
        if value
    ]

    auth_user = lay_thong_tin_nguoi_dung(request)
    role_code = normalize_role_code(auth_user.get("role_code"))
    if role_code == TEACHER_ROLE_CODE and not use_report_scope:
        scope_label = "PHIẾU ĐƯỢC PHÂN CÔNG TRỰC TIẾP"
    elif role_code in {SCHOOL_ROLE_CODE, TEACHER_ROLE_CODE}:
        scope_label = "PHẠM VI TOÀN TRƯỜNG"
    elif role_code == COMMUNE_ROLE_CODE:
        scope_label = "PHẠM VI TOÀN XÃ/PHƯỜNG"
    else:
        scope_label = "PHẠM VI TOÀN TỈNH"

    query_params = {
        "q": q,
        "hamlet": hamlet,
        "form_status": form_status,
        "issue": issue,
        "page_size": page_size,
    }
    query_string = urlencode(
        {
            key: value
            for key, value in query_params.items()
            if value not in {"", None}
        }
    )

    return {
        "items": displayed_items,
        "all_filtered_items": filtered_items,
        "summary": summary,
        "hamlets": hamlets,
        "scope_label": scope_label,
        "selected_q": q,
        "selected_hamlet": hamlet,
        "selected_form_status": form_status,
        "selected_issue": issue,
        "selected_page_size": page_size,
        "page": page,
        "total_pages": total_pages,
        "total_records": total_records,
        "start_record": start_index + 1 if total_records else 0,
        "end_record": min(start_index + len(displayed_items), total_records),
        "query_string": query_string,
        "form_status_labels": FORM_STATUS_LABELS,
        "issue_filter_labels": DATA_QUALITY_FILTER_LABELS,
    }


@router.get(
    "/{batch_id}/kiem-tra-du-lieu",
    response_class=HTMLResponse,
)
def kiem_tra_chat_luong_du_lieu(
    batch_id: int,
    request: Request,
    q: str = "",
    hamlet: str = "",
    form_status: str = "",
    issue: str = "",
    page_size: int = DATA_QUALITY_PAGE_SIZE,
    page: int = 1,
    db: Session = Depends(get_db),
):
    """Hiển thị bảng kiểm chất lượng dữ liệu của một đợt điều tra."""

    batch = lay_dot_dieu_tra(db, batch_id)
    if batch is None:
        return RedirectResponse(url="/dieu-tra", status_code=303)

    report_data = tao_du_lieu_kiem_tra_chat_luong(
        request=request,
        db=db,
        batch=batch,
        q=q,
        hamlet=hamlet,
        form_status=form_status,
        issue=issue,
        page_size=page_size,
        page=page,
    )

    return templates.TemplateResponse(
        request=request,
        name="surveys/data_quality.html",
        context={
            "nguoi_dung": lay_thong_tin_nguoi_dung(request),
            "batch": batch,
            **report_data,
            **tao_thong_tin_quyen_giao_dien(request),
        },
    )


@router.get(
    "/{batch_id}/kiem-tra-du-lieu/xuat-excel",
)
def xuat_excel_kiem_tra_chat_luong(
    batch_id: int,
    request: Request,
    q: str = "",
    hamlet: str = "",
    form_status: str = "",
    issue: str = "",
    db: Session = Depends(get_db),
):
    """Xuất kết quả kiểm tra chất lượng dữ liệu theo đúng phạm vi tài khoản."""

    batch = lay_dot_dieu_tra(db, batch_id)
    if batch is None:
        return RedirectResponse(url="/dieu-tra", status_code=303)

    report_data = tao_du_lieu_kiem_tra_chat_luong(
        request=request,
        db=db,
        batch=batch,
        q=q,
        hamlet=hamlet,
        form_status=form_status,
        issue=issue,
        page_size=DATA_QUALITY_PAGE_SIZE,
        page=1,
        paginate=False,
    )

    workbook = Workbook()
    overview_sheet = workbook.active
    overview_sheet.title = "Tong quan"

    dien_tieu_de_bao_cao_tien_do(
        overview_sheet,
        title="BÁO CÁO KIỂM TRA CHẤT LƯỢNG DỮ LIỆU",
        batch=batch,
        scope_label=report_data["scope_label"],
        last_column=4,
    )

    overview_sheet.append([])
    overview_sheet.append(["Chỉ tiêu", "Số lượng", "Tỷ lệ", "Ghi chú"])

    summary = report_data["summary"]
    total_forms = int(summary["total_forms"] or 0)

    overview_rows = [
        (
            "Tổng số phiếu",
            total_forms,
            1 if total_forms else 0,
            "Số phiếu thuộc phạm vi đang kiểm tra",
        ),
        (
            "Đạt yêu cầu",
            summary["passed_forms"],
            (
                summary["passed_forms"] / total_forms
                if total_forms
                else 0
            ),
            "Hoàn thành và không phát hiện vấn đề",
        ),
        (
            "Sẵn sàng hoàn thành",
            summary["ready_forms"],
            (
                summary["ready_forms"] / total_forms
                if total_forms
                else 0
            ),
            "Đủ dữ liệu tối thiểu nhưng chưa đánh dấu hoàn thành",
        ),
        (
            "Cần kiểm tra",
            summary["need_review_forms"],
            (
                summary["need_review_forms"] / total_forms
                if total_forms
                else 0
            ),
            "Có cảnh báo nhưng không có lỗi chặn",
        ),
        (
            "Cần xử lý",
            summary["need_action_forms"],
            (
                summary["need_action_forms"] / total_forms
                if total_forms
                else 0
            ),
            "Có ít nhất một lỗi cần khắc phục",
        ),
        (
            "Chưa phân công",
            summary["unassigned_forms"],
            (
                summary["unassigned_forms"] / total_forms
                if total_forms
                else 0
            ),
            "Phiếu chưa có người phụ trách",
        ),
        (
            "Đối tượng thiếu số định danh",
            summary["missing_personal_id_people"],
            None,
            "Tính theo số đối tượng",
        ),
        (
            "Đối tượng thiếu dữ liệu năm học",
            summary["missing_year_record_people"],
            None,
            "Tính theo số đối tượng",
        ),
        (
            "Đối tượng thiếu chỉ báo",
            summary["incomplete_year_record_people"],
            None,
            f"Chưa đủ {len(BOOLEAN_YEAR_FIELDS)} chỉ báo",
        ),
    ]

    for row in overview_rows:
        overview_sheet.append(row)

    for row_index in range(5, 5 + len(overview_rows)):
        overview_sheet.cell(row=row_index, column=3).number_format = "0%"

    dinh_dang_bang_bao_cao_tien_do(
        overview_sheet,
        header_row=4,
        last_row=4 + len(overview_rows),
        last_column=4,
    )

    detail_sheet = workbook.create_sheet("Chi tiet")
    detail_headers = [
        "STT",
        "Số phiếu",
        "Mã hộ",
        "Chủ hộ",
        "Thôn/xóm",
        "Địa chỉ",
        "Điện thoại",
        "Trạng thái phiếu",
        "Số đối tượng",
        "Số người được phân công",
        "Thiếu thông tin cá nhân",
        "Thiếu số định danh",
        "Thiếu dữ liệu năm",
        "Thiếu chỉ báo",
        "Kết quả kiểm tra",
        "Nội dung phát hiện",
        "Cập nhật gần nhất",
    ]

    dien_tieu_de_bao_cao_tien_do(
        detail_sheet,
        title="CHI TIẾT KIỂM TRA CHẤT LƯỢNG DỮ LIỆU",
        batch=batch,
        scope_label=report_data["scope_label"],
        last_column=len(detail_headers),
    )
    detail_sheet.append([])
    detail_sheet.append(detail_headers)

    for index, item in enumerate(
        report_data["all_filtered_items"],
        start=1,
    ):
        issue_text = "\n".join(
            f"- {issue_item['label']}: {issue_item['detail']}"
            for issue_item in item["issues"]
        ) or "Không phát hiện vấn đề"

        detail_sheet.append(
            [
                index,
                item["form_number"],
                item["household_code"],
                item["head_name"],
                item["hamlet_name"] or "",
                item["address"],
                item["phone"] or "",
                item["form_status_label"],
                item["active_people_count"],
                item["assignment_count"],
                item["missing_basic_count"],
                item["missing_personal_id_count"],
                item["missing_year_record_count"],
                item["incomplete_year_record_count"],
                item["quality_label"],
                issue_text,
                item["updated_at"].strftime("%d/%m/%Y %H:%M")
                if item["updated_at"]
                else "",
            ]
        )

    detail_last_row = 4 + len(report_data["all_filtered_items"])
    dinh_dang_bang_bao_cao_tien_do(
        detail_sheet,
        header_row=4,
        last_row=detail_last_row,
        last_column=len(detail_headers),
    )

    detail_sheet.column_dimensions["F"].width = 36
    detail_sheet.column_dimensions["P"].width = 58

    output = BytesIO()
    workbook.save(output)
    output.seek(0)

    safe_batch_code = str(batch.code or batch.id).replace("/", "-")
    file_name = (
        f"bao_cao_kiem_tra_du_lieu_{safe_batch_code}_"
        f"{batch.school_year.code}.xlsx"
    )

    return StreamingResponse(
        output,
        media_type=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
        headers={
            "Content-Disposition": (
                f'attachment; filename="{file_name}"'
            )
        },
    )


# =========================================================
# CHỐT SỐ LIỆU VÀ KHÓA ĐỢT ĐIỀU TRA
# =========================================================

LOCK_ACTION_LABELS = {
    "LOCK": "Chốt và khóa dữ liệu",
    "UNLOCK": "Mở khóa dữ liệu",
}


def tao_du_lieu_chot_so_lieu(
    *,
    request: Request,
    db: Session,
    batch: SurveyBatch,
) -> dict[str, Any]:
    """Kiểm tra các điều kiện trước khi khóa toàn bộ đợt điều tra."""

    quality_data = tao_du_lieu_kiem_tra_chat_luong(
        request=request,
        db=db,
        batch=batch,
        paginate=False,
    )
    items = quality_data["all_filtered_items"]

    total_forms = len(items)
    completed_forms = sum(
        item["form_status"] == "DA_HOAN_THANH"
        for item in items
    )
    blocking_issue_forms = sum(
        item["blocking_issue_count"] > 0
        for item in items
    )
    blocking_issue_total = sum(
        int(item["blocking_issue_count"])
        for item in items
    )
    missing_household_confirmation = sum(
        item["household_confirmed_at"] is None
        for item in items
    )
    missing_commune_confirmation = sum(
        item["commune_confirmed_at"] is None
        for item in items
    )
    warning_issue_total = sum(
        int(item["warning_issue_count"])
        for item in items
    )

    conditions = [
        {
            "code": "HAS_FORMS",
            "label": "Đợt điều tra đã có phiếu",
            "passed": total_forms > 0,
            "detail": (
                f"Hiện có {total_forms} phiếu điều tra."
                if total_forms
                else "Chưa có phiếu điều tra nào để chốt số liệu."
            ),
        },
        {
            "code": "ALL_COMPLETED",
            "label": "Tất cả phiếu đã hoàn thành",
            "passed": total_forms > 0 and completed_forms == total_forms,
            "detail": (
                f"Đã hoàn thành {completed_forms}/{total_forms} phiếu."
            ),
        },
        {
            "code": "NO_BLOCKING_ISSUES",
            "label": "Không còn lỗi chất lượng nghiêm trọng",
            "passed": blocking_issue_total == 0,
            "detail": (
                "Không phát hiện lỗi nghiêm trọng."
                if blocking_issue_total == 0
                else (
                    f"Còn {blocking_issue_total} lỗi nghiêm trọng "
                    f"trên {blocking_issue_forms} phiếu."
                )
            ),
        },
        {
            "code": "HOUSEHOLD_CONFIRMED",
            "label": "Đầy đủ xác nhận của hộ gia đình",
            "passed": (
                total_forms > 0
                and missing_household_confirmation == 0
            ),
            "detail": (
                "Tất cả phiếu đã có xác nhận của hộ gia đình."
                if missing_household_confirmation == 0 and total_forms > 0
                else (
                    f"Còn {missing_household_confirmation} phiếu "
                    "chưa có xác nhận của hộ gia đình."
                )
            ),
        },
        {
            "code": "COMMUNE_CONFIRMED",
            "label": "Đầy đủ xác nhận của xã/phường",
            "passed": (
                total_forms > 0
                and missing_commune_confirmation == 0
            ),
            "detail": (
                "Tất cả phiếu đã được xã/phường xác nhận."
                if missing_commune_confirmation == 0 and total_forms > 0
                else (
                    f"Còn {missing_commune_confirmation} phiếu "
                    "chưa được xã/phường xác nhận."
                )
            ),
        },
    ]

    can_lock = all(bool(item["passed"]) for item in conditions)

    logs = db.scalars(
        select(SurveyBatchLockLog)
        .where(SurveyBatchLockLog.survey_batch_id == batch.id)
        .order_by(
            SurveyBatchLockLog.created_at.desc(),
            SurveyBatchLockLog.id.desc(),
        )
        .limit(30)
    ).all()

    return {
        "conditions": conditions,
        "can_lock": can_lock,
        "total_forms": total_forms,
        "completed_forms": completed_forms,
        "blocking_issue_forms": blocking_issue_forms,
        "blocking_issue_total": blocking_issue_total,
        "missing_household_confirmation": (
            missing_household_confirmation
        ),
        "missing_commune_confirmation": (
            missing_commune_confirmation
        ),
        "warning_issue_total": warning_issue_total,
        "quality_summary": quality_data["summary"],
        "logs": logs,
    }


def hien_thi_trang_chot_so_lieu(
    *,
    request: Request,
    db: Session,
    batch: SurveyBatch,
    status: str | None = None,
    thong_bao_loi: str | None = None,
    form_data: dict[str, Any] | None = None,
    status_code: int = 200,
):
    lock_data = tao_du_lieu_chot_so_lieu(
        request=request,
        db=db,
        batch=batch,
    )

    # === FIX27_EFFECTIVE_LOCK_CONTEXT_START ===
    _fix27_state = db.execute(
        text("""
            SELECT COALESCE(is_commune_locked,0) AS is_commune_locked,
                   COALESCE(is_province_locked,0) AS is_province_locked
            FROM survey_commune_execution_states
            WHERE survey_batch_id=:batch_id LIMIT 1
        """), {"batch_id": int(batch.id)}
    ).mappings().first()
    _fix27_commune_locked = bool(_fix27_state["is_commune_locked"] if _fix27_state is not None else False)
    _fix27_province_locked = bool(_fix27_state["is_province_locked"] if _fix27_state is not None else False)
    _fix27_school_locked_total = int(db.execute(
        text("""SELECT COUNT(*) FROM survey_school_assignments
                 WHERE survey_batch_id=:batch_id AND COALESCE(is_locked,0)=1"""),
        {"batch_id": int(batch.id)}
    ).scalar() or 0)
    lock_state = {
        "batch_locked": bool(batch.is_locked),
        "commune_locked": _fix27_commune_locked,
        "province_locked": _fix27_province_locked,
        "effective_locked": bool(batch.is_locked or _fix27_commune_locked or _fix27_province_locked),
        "school_locked_total": _fix27_school_locked_total,
    }
    # === FIX27_EFFECTIVE_LOCK_CONTEXT_END ===

    return templates.TemplateResponse(
        request=request,
        name="surveys/batch_lock.html",
        context={
            "nguoi_dung": lay_thong_tin_nguoi_dung(request),
            "batch": batch,
            "lock_data": lock_data,
            "lock_state": lock_state,
            "action_labels": LOCK_ACTION_LABELS,
            "status_labels": BATCH_STATUS_LABELS,
            "thong_bao": STATUS_MESSAGES.get(status),
            "thong_bao_loi": thong_bao_loi,
            "form_data": form_data or {},
        },
        status_code=status_code,
    )



@router.get(
    "/{batch_id}/chot-so-lieu",
    response_class=HTMLResponse,
)
def trang_chot_so_lieu(
    batch_id: int,
    request: Request,
    status: str | None = None,
    db: Session = Depends(get_db),
):
    user = lay_thong_tin_nguoi_dung(request)
    if not is_admin_role(user.get("role_code")):
        return RedirectResponse(
            url="/?status=forbidden",
            status_code=303,
        )

    batch = lay_dot_dieu_tra(db, batch_id)
    if batch is None:
        return RedirectResponse(url="/dieu-tra", status_code=303)

    return hien_thi_trang_chot_so_lieu(
        request=request,
        db=db,
        batch=batch,
        status=status,
    )


@router.post("/{batch_id}/chot-so-lieu/khoa")
def khoa_dot_dieu_tra(
    batch_id: int,
    request: Request,
    reason: Annotated[str, Form()],
    db: Session = Depends(get_db),
):
    user = lay_thong_tin_nguoi_dung(request)
    if not is_admin_role(user.get("role_code")):
        return RedirectResponse(
            url="/?status=forbidden",
            status_code=303,
        )

    batch = lay_dot_dieu_tra(db, batch_id)
    if batch is None:
        return RedirectResponse(url="/dieu-tra", status_code=303)

    reason = chuan_hoa_van_ban(reason)
    errors: list[str] = []

    if batch.is_locked:
        errors.append("Đợt điều tra này đã được khóa trước đó.")

    if len(reason) < 10:
        errors.append("Lý do chốt số liệu phải có ít nhất 10 ký tự.")
    if len(reason) > 1000:
        errors.append("Lý do chốt số liệu không được quá 1000 ký tự.")

    lock_data = tao_du_lieu_chot_so_lieu(
        request=request,
        db=db,
        batch=batch,
    )
    if not lock_data["can_lock"]:
        errors.append(
            "Đợt điều tra chưa đáp ứng đủ điều kiện để chốt số liệu."
        )

    if errors:
        return hien_thi_trang_chot_so_lieu(
            request=request,
            db=db,
            batch=batch,
            thong_bao_loi=" ".join(errors),
            form_data={"lock_reason": reason},
            status_code=400,
        )

    previous_status = batch.status
    now = datetime.now()

    batch.status_before_lock = previous_status
    batch.status = "DA_KET_THUC"
    batch.is_locked = True
    batch.locked_at = now
    batch.locked_by_user_id = int(user["id"])
    batch.lock_reason = reason

    db.add(
        SurveyBatchLockLog(
            survey_batch_id=batch.id,
            action="LOCK",
            actor_user_id=int(user["id"]),
            actor_name_snapshot=str(user.get("full_name") or ""),
            actor_role_snapshot=str(user.get("role_name") or ""),
            reason=reason,
            form_total=int(lock_data["total_forms"]),
            completed_form_total=int(lock_data["completed_forms"]),
            blocking_issue_total=int(
                lock_data["blocking_issue_total"]
            ),
            previous_status=previous_status,
            new_status="DA_KET_THUC",
            created_at=now,
        )
    )

    # === FIX27_SYNC_COMMUNE_LOCK_ON_BATCH_LOCK_START ===
    _fix27_upd = db.execute(
        text("""UPDATE survey_commune_execution_states
                SET is_commune_locked=1, commune_locked_at=:locked_at,
                    commune_locked_by_user_id=:actor_id, commune_lock_reason=:reason,
                    updated_at=:updated_at
                WHERE survey_batch_id=:batch_id"""),
        {"batch_id":int(batch.id),"locked_at":now,"actor_id":int(user["id"]),"reason":reason,"updated_at":now},
    )
    if int(_fix27_upd.rowcount or 0)==0:
        db.execute(
            text("""INSERT INTO survey_commune_execution_states
                    (survey_batch_id,is_commune_locked,is_province_locked,commune_locked_at,
                     commune_locked_by_user_id,commune_lock_reason,updated_at)
                    VALUES (:batch_id,1,0,:locked_at,:actor_id,:reason,:updated_at)"""),
            {"batch_id":int(batch.id),"locked_at":now,"actor_id":int(user["id"]),"reason":reason,"updated_at":now},
        )
    # === FIX27_SYNC_COMMUNE_LOCK_ON_BATCH_LOCK_END ===

    db.commit()

    return RedirectResponse(
        url=(
            f"/dieu-tra/{batch.id}/chot-so-lieu"
            "?status=batch_locked_success"
        ),
        status_code=303,
    )



@router.post("/{batch_id}/chot-so-lieu/mo-khoa")
def mo_khoa_dot_dieu_tra(
    batch_id: int,
    request: Request,
    reason: Annotated[str, Form()],
    db: Session = Depends(get_db),
):
    user = lay_thong_tin_nguoi_dung(request)
    if not is_admin_role(user.get("role_code")):
        return RedirectResponse(
            url="/?status=forbidden",
            status_code=303,
        )

    batch = lay_dot_dieu_tra(db, batch_id)
    if batch is None:
        return RedirectResponse(url="/dieu-tra", status_code=303)

    reason = chuan_hoa_van_ban(reason)
    errors: list[str] = []

    _fix27_state = db.execute(
        text("""SELECT COALESCE(is_commune_locked,0) AS is_commune_locked,
                       COALESCE(is_province_locked,0) AS is_province_locked
                FROM survey_commune_execution_states
                WHERE survey_batch_id=:batch_id LIMIT 1"""),
        {"batch_id":int(batch.id)},
    ).mappings().first()
    commune_locked = bool(_fix27_state["is_commune_locked"] if _fix27_state is not None else False)
    province_locked = bool(_fix27_state["is_province_locked"] if _fix27_state is not None else False)

    if province_locked:
        errors.append("Cấp tỉnh đang khóa. Hãy mở khóa cấp tỉnh trước khi mở địa bàn.")
    if not batch.is_locked and not commune_locked:
        errors.append("Đợt và cấp xã hiện đều đang mở cập nhật.")
    if len(reason) < 10:
        errors.append("Lý do mở khóa phải có ít nhất 10 ký tự.")
    if len(reason) > 1000:
        errors.append("Lý do mở khóa không được quá 1000 ký tự.")

    if errors:
        return hien_thi_trang_chot_so_lieu(
            request=request,
            db=db,
            batch=batch,
            thong_bao_loi=" ".join(errors),
            form_data={"unlock_reason": reason},
            status_code=400,
        )

    lock_data = tao_du_lieu_chot_so_lieu(
        request=request,
        db=db,
        batch=batch,
    )
    previous_status = batch.status
    restored_status = batch.status_before_lock or "DANG_DIEU_TRA"
    now = datetime.now()

    db.add(
        SurveyBatchLockLog(
            survey_batch_id=batch.id,
            action="UNLOCK",
            actor_user_id=int(user["id"]),
            actor_name_snapshot=str(user.get("full_name") or ""),
            actor_role_snapshot=str(user.get("role_name") or ""),
            reason=reason,
            form_total=int(lock_data["total_forms"]),
            completed_form_total=int(lock_data["completed_forms"]),
            blocking_issue_total=int(
                lock_data["blocking_issue_total"]
            ),
            previous_status=previous_status,
            new_status=restored_status,
            created_at=now,
        )
    )

    batch.status = restored_status
    batch.is_locked = False
    batch.locked_at = None
    batch.locked_by_user_id = None
    batch.lock_reason = None
    batch.status_before_lock = None

    # === FIX27_SYNC_COMMUNE_UNLOCK_ON_BATCH_UNLOCK_START ===
    db.execute(
        text("""UPDATE survey_commune_execution_states
                SET is_commune_locked=0, commune_locked_at=NULL,
                    commune_locked_by_user_id=NULL, commune_lock_reason=NULL,
                    updated_at=:updated_at
                WHERE survey_batch_id=:batch_id AND COALESCE(is_province_locked,0)=0"""),
        {"batch_id":int(batch.id),"updated_at":now},
    )
    # === FIX27_SYNC_COMMUNE_UNLOCK_ON_BATCH_UNLOCK_END ===

    db.commit()

    return RedirectResponse(
        url=(
            f"/dieu-tra/{batch.id}/chot-so-lieu"
            "?status=batch_unlocked_success"
        ),
        status_code=303,
    )



def tao_du_lieu_tien_do_dieu_tra(
    *,
    request: Request,
    db: Session,
    batch: SurveyBatch,
) -> dict[str, Any]:
    """Tổng hợp tiến độ theo địa bàn, trường và người điều tra."""

    report_filters = [
        SurveyForm.survey_batch_id == batch.id,
        *tao_bo_loc_bao_cao_theo_nguoi_dung(request),
    ]

    auth_user = lay_thong_tin_nguoi_dung(request)
    role_code = normalize_role_code(auth_user.get("role_code"))
    assignment_scope_filters: list[Any] = []
    if role_code in {SCHOOL_ROLE_CODE, TEACHER_ROLE_CODE}:
        school_id = auth_user.get("school_id")
        if school_id is None:
            assignment_scope_filters.append(User.id == -1)
        else:
            assignment_scope_filters.append(User.school_id == int(school_id))

    status_rows = db.execute(
        select(
            SurveyForm.status,
            func.count(SurveyForm.id),
        )
        .where(*report_filters)
        .group_by(SurveyForm.status)
    ).all()

    status_counts = {code: 0 for code in FORM_STATUS_LABELS}
    for status_code, count_value in status_rows:
        status_counts[status_code] = int(count_value or 0)

    total_forms = sum(status_counts.values())
    completed_forms = status_counts.get("DA_HOAN_THANH", 0)
    progress_percent = (
        round(completed_forms * 100 / total_forms)
        if total_forms
        else 0
    )

    total_people = int(
        db.scalar(
            select(func.count(SurveyPerson.id))
            .join(
                SurveyForm,
                SurveyForm.household_id == SurveyPerson.household_id,
            )
            .where(
                *report_filters,
                SurveyPerson.is_active.is_(True),
            )
        )
        or 0
    )

    unassigned_forms = int(
        db.scalar(
            select(func.count(SurveyForm.id)).where(
                *report_filters,
                ~SurveyForm.investigators.any(),
            )
        )
        or 0
    )

    hamlet_rows = db.execute(
        select(
            Household.hamlet_name,
            SurveyForm.status,
            func.count(SurveyForm.id),
        )
        .join(
            Household,
            Household.id == SurveyForm.household_id,
        )
        .where(*report_filters)
        .group_by(Household.hamlet_name, SurveyForm.status)
        .order_by(Household.hamlet_name.asc())
    ).all()

    hamlet_grouped: dict[str, dict[str, int]] = {}
    for hamlet_name, status_code, count_value in hamlet_rows:
        display_name = hamlet_name or "Chưa xác định thôn/xóm"
        hamlet_grouped.setdefault(
            display_name,
            {code: 0 for code in FORM_STATUS_LABELS},
        )
        hamlet_grouped[display_name][status_code] = int(count_value or 0)

    hamlet_progress: list[dict[str, Any]] = []
    for hamlet_name, counts in hamlet_grouped.items():
        hamlet_total = sum(counts.values())
        hamlet_completed = counts.get("DA_HOAN_THANH", 0)
        hamlet_progress.append(
            {
                "hamlet_name": hamlet_name,
                "counts": counts,
                "total": hamlet_total,
                "progress_percent": (
                    round(hamlet_completed * 100 / hamlet_total)
                    if hamlet_total
                    else 0
                ),
            }
        )

    school_rows = db.execute(
        select(
            School.id,
            School.code,
            School.name,
            SurveyForm.status,
            func.count(func.distinct(SurveyForm.id)),
        )
        .select_from(SurveyForm)
        .join(
            SurveyFormInvestigator,
            SurveyFormInvestigator.survey_form_id == SurveyForm.id,
        )
        .join(User, User.id == SurveyFormInvestigator.user_id)
        .join(School, School.id == User.school_id)
        .where(
            *report_filters,
            *assignment_scope_filters,
            User.is_active.is_(True),
            School.is_active.is_(True),
        )
        .group_by(
            School.id,
            School.code,
            School.name,
            SurveyForm.status,
        )
        .order_by(School.name.asc())
    ).all()

    school_grouped: dict[int, dict[str, Any]] = {}
    for school_id, school_code, school_name, status_code, count_value in school_rows:
        item = school_grouped.setdefault(
            int(school_id),
            {
                "school_id": int(school_id),
                "school_code": school_code,
                "school_name": school_name,
                "counts": {code: 0 for code in FORM_STATUS_LABELS},
            },
        )
        item["counts"][status_code] = int(count_value or 0)

    school_progress: list[dict[str, Any]] = []
    for item in school_grouped.values():
        counts = item["counts"]
        school_total = sum(counts.values())
        school_completed = counts.get("DA_HOAN_THANH", 0)
        item["total"] = school_total
        item["progress_percent"] = (
            round(school_completed * 100 / school_total)
            if school_total
            else 0
        )
        school_progress.append(item)

    investigator_rows = db.execute(
        select(
            User.id,
            User.username,
            User.full_name,
            School.code,
            School.name,
            SurveyForm.status,
            SurveyFormInvestigator.is_primary,
            func.count(SurveyForm.id),
        )
        .select_from(SurveyForm)
        .join(
            SurveyFormInvestigator,
            SurveyFormInvestigator.survey_form_id == SurveyForm.id,
        )
        .join(User, User.id == SurveyFormInvestigator.user_id)
        .outerjoin(School, School.id == User.school_id)
        .where(
            *report_filters,
            *assignment_scope_filters,
            User.is_active.is_(True),
        )
        .group_by(
            User.id,
            User.username,
            User.full_name,
            School.code,
            School.name,
            SurveyForm.status,
            SurveyFormInvestigator.is_primary,
        )
        .order_by(User.full_name.asc(), User.username.asc())
    ).all()

    investigator_grouped: dict[int, dict[str, Any]] = {}
    for (
        user_id,
        username,
        full_name,
        school_code,
        school_name,
        status_code,
        is_primary,
        count_value,
    ) in investigator_rows:
        item = investigator_grouped.setdefault(
            int(user_id),
            {
                "user_id": int(user_id),
                "username": username,
                "full_name": full_name,
                "school_code": school_code,
                "school_name": school_name or "Chưa gắn trường",
                "counts": {code: 0 for code in FORM_STATUS_LABELS},
                "primary_count": 0,
            },
        )
        number = int(count_value or 0)
        item["counts"][status_code] += number
        if bool(is_primary):
            item["primary_count"] += number

    investigator_progress: list[dict[str, Any]] = []
    for item in investigator_grouped.values():
        counts = item["counts"]
        assigned_total = sum(counts.values())
        assigned_completed = counts.get("DA_HOAN_THANH", 0)
        item["total"] = assigned_total
        item["progress_percent"] = (
            round(assigned_completed * 100 / assigned_total)
            if assigned_total
            else 0
        )
        investigator_progress.append(item)

    if role_code in {SCHOOL_ROLE_CODE, TEACHER_ROLE_CODE}:
        progress_scope_label = "TOÀN TRƯỜNG"
    elif role_code == COMMUNE_ROLE_CODE:
        progress_scope_label = "TOÀN XÃ/PHƯỜNG"
    else:
        progress_scope_label = "TOÀN TỈNH"

    return {
        "form_status_labels": FORM_STATUS_LABELS,
        "status_counts": status_counts,
        "total_forms": total_forms,
        "total_people": total_people,
        "completed_forms": completed_forms,
        "unassigned_forms": unassigned_forms,
        "progress_percent": progress_percent,
        "hamlet_progress": hamlet_progress,
        "school_progress": school_progress,
        "investigator_progress": investigator_progress,
        "progress_scope_label": progress_scope_label,
    }


def dien_tieu_de_bao_cao_tien_do(
    worksheet,
    *,
    title: str,
    batch: SurveyBatch,
    scope_label: str,
    last_column: int,
) -> None:
    """Tạo phần đầu thống nhất cho các trang Excel tiến độ."""

    worksheet.merge_cells(
        start_row=1,
        start_column=1,
        end_row=1,
        end_column=last_column,
    )
    title_cell = worksheet.cell(row=1, column=1, value=title)
    title_cell.font = Font(size=16, bold=True, color="FFFFFF")
    title_cell.fill = PatternFill("solid", fgColor="1565C0")
    title_cell.alignment = Alignment(horizontal="center", vertical="center")
    worksheet.row_dimensions[1].height = 28

    worksheet.merge_cells(
        start_row=2,
        start_column=1,
        end_row=2,
        end_column=last_column,
    )
    subtitle = (
        f"Đợt: {batch.name} | Năm học: {batch.school_year.code} | "
        f"Xã/phường: {batch.commune.name} | Phạm vi: {scope_label}"
    )
    subtitle_cell = worksheet.cell(row=2, column=1, value=subtitle)
    subtitle_cell.font = Font(italic=True, color="44546A")
    subtitle_cell.alignment = Alignment(horizontal="center", vertical="center")
    worksheet.row_dimensions[2].height = 22


def dinh_dang_bang_bao_cao_tien_do(
    worksheet,
    *,
    header_row: int,
    last_row: int,
    last_column: int,
) -> None:
    """Định dạng bảng và tự điều chỉnh độ rộng cột."""

    header_fill = PatternFill("solid", fgColor="D9EAF7")
    thin_gray = Side(style="thin", color="D8E1EA")
    border = Border(
        left=thin_gray,
        right=thin_gray,
        top=thin_gray,
        bottom=thin_gray,
    )

    for cell in worksheet[header_row]:
        if cell.column <= last_column:
            cell.font = Font(bold=True, color="17324D")
            cell.fill = header_fill
            cell.alignment = Alignment(
                horizontal="center",
                vertical="center",
                wrap_text=True,
            )
            cell.border = border

    for row in worksheet.iter_rows(
        min_row=header_row + 1,
        max_row=max(last_row, header_row),
        min_col=1,
        max_col=last_column,
    ):
        for cell in row:
            cell.border = border
            cell.alignment = Alignment(vertical="top", wrap_text=True)

    worksheet.freeze_panes = f"A{header_row + 1}"
    worksheet.auto_filter.ref = (
        f"A{header_row}:{get_column_letter(last_column)}{max(last_row, header_row)}"
    )

    for column_index in range(1, last_column + 1):
        max_length = 0
        for row_index in range(1, max(last_row, header_row) + 1):
            value = worksheet.cell(row=row_index, column=column_index).value
            if value is None:
                continue
            max_length = max(max_length, len(str(value)))
        worksheet.column_dimensions[get_column_letter(column_index)].width = min(
            max(max_length + 2, 10),
            38,
        )


@router.get(
    "/{batch_id}/tien-do",
    response_class=HTMLResponse,
)
def tien_do_dieu_tra(
    batch_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    batch = lay_dot_dieu_tra(db, batch_id)

    if batch is None:
        return RedirectResponse(url="/dieu-tra", status_code=303)

    progress_data = tao_du_lieu_tien_do_dieu_tra(
        request=request,
        db=db,
        batch=batch,
    )

    return templates.TemplateResponse(
        request=request,
        name="surveys/progress.html",
        context={
            "nguoi_dung": request.scope.get("auth_user"),
            "batch": batch,
            **progress_data,
        },
    )


@router.get(
    "/{batch_id}/tien-do/xuat-excel",
)
def xuat_excel_tien_do_dieu_tra(
    batch_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """Xuất báo cáo tiến độ đúng phạm vi dữ liệu của tài khoản."""

    batch = lay_dot_dieu_tra(db, batch_id)
    if batch is None:
        return RedirectResponse(url="/dieu-tra", status_code=303)

    progress_data = tao_du_lieu_tien_do_dieu_tra(
        request=request,
        db=db,
        batch=batch,
    )

    workbook = Workbook()
    overview_sheet = workbook.active
    overview_sheet.title = "Tong quan"

    dien_tieu_de_bao_cao_tien_do(
        overview_sheet,
        title="BÁO CÁO TIẾN ĐỘ ĐIỀU TRA PHỔ CẬP GIÁO DỤC",
        batch=batch,
        scope_label=progress_data["progress_scope_label"],
        last_column=4,
    )
    overview_sheet.append([])
    overview_sheet.append(["Chỉ tiêu", "Số lượng", "Tỷ lệ", "Ghi chú"])

    total_forms = progress_data["total_forms"]
    status_counts = progress_data["status_counts"]
    overview_rows = [
        ("Tổng số phiếu", total_forms, "100%" if total_forms else "0%", ""),
        ("Tổng số đối tượng", progress_data["total_people"], "", "Đối tượng đang theo dõi"),
        (
            "Chưa điều tra",
            status_counts.get("CHUA_DIEU_TRA", 0),
            f"{round(status_counts.get('CHUA_DIEU_TRA', 0) * 100 / total_forms) if total_forms else 0}%",
            "",
        ),
        (
            "Đang điều tra",
            status_counts.get("DANG_DIEU_TRA", 0),
            f"{round(status_counts.get('DANG_DIEU_TRA', 0) * 100 / total_forms) if total_forms else 0}%",
            "",
        ),
        (
            "Đã hoàn thành",
            status_counts.get("DA_HOAN_THANH", 0),
            f"{progress_data['progress_percent']}%",
            "",
        ),
        (
            "Cần bổ sung",
            status_counts.get("CAN_BO_SUNG", 0),
            f"{round(status_counts.get('CAN_BO_SUNG', 0) * 100 / total_forms) if total_forms else 0}%",
            "",
        ),
        (
            "Chưa phân công",
            progress_data["unassigned_forms"],
            f"{round(progress_data['unassigned_forms'] * 100 / total_forms) if total_forms else 0}%",
            "Phiếu chưa có người điều tra",
        ),
    ]
    for row in overview_rows:
        overview_sheet.append(row)
    dinh_dang_bang_bao_cao_tien_do(
        overview_sheet,
        header_row=4,
        last_row=overview_sheet.max_row,
        last_column=4,
    )

    hamlet_sheet = workbook.create_sheet("Theo dia ban")
    dien_tieu_de_bao_cao_tien_do(
        hamlet_sheet,
        title="TIẾN ĐỘ THEO THÔN/XÓM/KHỐI/BẢN",
        batch=batch,
        scope_label=progress_data["progress_scope_label"],
        last_column=8,
    )
    hamlet_sheet.append([])
    hamlet_sheet.append([
        "STT",
        "Thôn/xóm/khối/bản",
        "Tổng phiếu",
        "Chưa điều tra",
        "Đang điều tra",
        "Đã hoàn thành",
        "Cần bổ sung",
        "Tiến độ",
    ])
    for index, item in enumerate(progress_data["hamlet_progress"], start=1):
        counts = item["counts"]
        hamlet_sheet.append([
            index,
            item["hamlet_name"],
            item["total"],
            counts.get("CHUA_DIEU_TRA", 0),
            counts.get("DANG_DIEU_TRA", 0),
            counts.get("DA_HOAN_THANH", 0),
            counts.get("CAN_BO_SUNG", 0),
            f"{item['progress_percent']}%",
        ])
    dinh_dang_bang_bao_cao_tien_do(
        hamlet_sheet,
        header_row=4,
        last_row=hamlet_sheet.max_row,
        last_column=8,
    )

    school_sheet = workbook.create_sheet("Theo truong")
    dien_tieu_de_bao_cao_tien_do(
        school_sheet,
        title="TIẾN ĐỘ THEO TRƯỜNG",
        batch=batch,
        scope_label=progress_data["progress_scope_label"],
        last_column=9,
    )
    school_sheet.append([])
    school_sheet.append([
        "STT",
        "Mã trường",
        "Tên trường",
        "Tổng phiếu",
        "Chưa điều tra",
        "Đang điều tra",
        "Đã hoàn thành",
        "Cần bổ sung",
        "Tiến độ",
    ])
    for index, item in enumerate(progress_data["school_progress"], start=1):
        counts = item["counts"]
        school_sheet.append([
            index,
            item["school_code"],
            item["school_name"],
            item["total"],
            counts.get("CHUA_DIEU_TRA", 0),
            counts.get("DANG_DIEU_TRA", 0),
            counts.get("DA_HOAN_THANH", 0),
            counts.get("CAN_BO_SUNG", 0),
            f"{item['progress_percent']}%",
        ])
    dinh_dang_bang_bao_cao_tien_do(
        school_sheet,
        header_row=4,
        last_row=school_sheet.max_row,
        last_column=9,
    )

    investigator_sheet = workbook.create_sheet("Theo nguoi dieu tra")
    dien_tieu_de_bao_cao_tien_do(
        investigator_sheet,
        title="TIẾN ĐỘ THEO NGƯỜI ĐIỀU TRA",
        batch=batch,
        scope_label=progress_data["progress_scope_label"],
        last_column=12,
    )
    investigator_sheet.append([])
    investigator_sheet.append([
        "STT",
        "Tên đăng nhập",
        "Họ và tên",
        "Trường",
        "Tổng phiếu được giao",
        "Phiếu phụ trách chính",
        "Chưa điều tra",
        "Đang điều tra",
        "Đã hoàn thành",
        "Cần bổ sung",
        "Tiến độ",
        "Ghi chú",
    ])
    for index, item in enumerate(progress_data["investigator_progress"], start=1):
        counts = item["counts"]
        investigator_sheet.append([
            index,
            item["username"],
            item["full_name"],
            item["school_name"],
            item["total"],
            item["primary_count"],
            counts.get("CHUA_DIEU_TRA", 0),
            counts.get("DANG_DIEU_TRA", 0),
            counts.get("DA_HOAN_THANH", 0),
            counts.get("CAN_BO_SUNG", 0),
            f"{item['progress_percent']}%",
            "Một phiếu có thể được giao cho nhiều người.",
        ])
    dinh_dang_bang_bao_cao_tien_do(
        investigator_sheet,
        header_row=4,
        last_row=investigator_sheet.max_row,
        last_column=12,
    )

    output = BytesIO()
    workbook.save(output)
    output.seek(0)

    safe_year = str(batch.school_year.code).replace("/", "-")
    filename = f"bao_cao_tien_do_{batch.code}_{safe_year}.xlsx"
    headers = {
        "Content-Disposition": (
            f'attachment; filename="{filename}"'
        )
    }

    return StreamingResponse(
        output,
        media_type=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
        headers=headers,
    )


# =========================================================
# BÀI 12D-6: BÁO CÁO TỔNG HỢP KẾT QUẢ ĐIỀU TRA
# =========================================================

def tinh_tuoi_tai_ngay(
    ngay_sinh: date | None,
    ngay_tham_chieu: date,
) -> int | None:
    """Tính tuổi tròn tại ngày tham chiếu; trả về None khi thiếu ngày sinh."""

    if ngay_sinh is None or ngay_sinh > ngay_tham_chieu:
        return None

    return (
        ngay_tham_chieu.year
        - ngay_sinh.year
        - (
            (ngay_tham_chieu.month, ngay_tham_chieu.day)
            < (ngay_sinh.month, ngay_sinh.day)
        )
    )


def tao_du_lieu_bao_cao_tong_hop(
    *,
    request: Request,
    db: Session,
    batch: SurveyBatch,
) -> dict[str, Any]:
    """
    Tổng hợp kết quả điều tra theo đúng phạm vi báo cáo của tài khoản.

    Báo cáo chỉ đọc dữ liệu hiện có. Các số liệu chính thức nên được xuất
    sau khi đợt đã chốt và khóa để bảo đảm dữ liệu không tiếp tục thay đổi.
    """

    report_filters = [
        SurveyForm.survey_batch_id == batch.id,
        *tao_bo_loc_bao_cao_theo_nguoi_dung(request),
    ]

    progress_data = tao_du_lieu_tien_do_dieu_tra(
        request=request,
        db=db,
        batch=batch,
    )
    quality_data = tao_du_lieu_kiem_tra_chat_luong(
        request=request,
        db=db,
        batch=batch,
        paginate=False,
        use_report_scope=True,
    )

    reference_date = (
        batch.school_year.start_date
        or batch.start_date
        or date.today()
    )

    person_rows_raw = db.execute(
        select(
            SurveyForm.id.label("survey_form_id"),
            SurveyForm.form_number.label("form_number"),
            SurveyForm.status.label("form_status"),
            Household.code.label("household_code"),
            Household.head_name.label("head_name"),
            Household.hamlet_name.label("hamlet_name"),
            Household.address.label("address"),
            SurveyPerson.id.label("person_id"),
            SurveyPerson.code.label("person_code"),
            SurveyPerson.full_name.label("full_name"),
            SurveyPerson.date_of_birth.label("date_of_birth"),
            SurveyPerson.gender.label("gender"),
            SurveyPerson.ethnic_group.label("ethnic_group"),
            SurveyPerson.relationship_to_head.label("relationship_to_head"),
            SurveyPerson.personal_id.label("personal_id"),
            SurveyPerson.ministry_student_code.label("ministry_student_code"),
            SurveyPerson.residency_status.label("residency_status"),
            SurveyPersonYearRecord.learning_status.label("learning_status"),
            # === BAI_13B_12_V2_4_4_6_5_SUMMARY_ACTIVE_INDICATORS ===
            # Bao cao tong hop chi lay cac chi bao dang con theo doi.
            SurveyPersonYearRecord.completed_preschool_by_age.label(
                "completed_preschool_by_age"
            ),
            SurveyPersonYearRecord.attends_two_sessions_per_day.label(
                "attends_two_sessions_per_day"
            ),
            SurveyPersonYearRecord.prepared_vietnamese.label(
                "prepared_vietnamese"
            ),
            SurveyPersonYearRecord.disability_status.label("disability_status"),
            SurveyPersonYearRecord.disability_type.label("disability_type"),
            SurveyPersonYearRecord.disability_level.label("disability_level"),
            SurveyPersonYearRecord.disability_certificate.label("disability_certificate"),
            SurveyPersonYearRecord.inclusive_education.label("inclusive_education"),
            SurveyPersonYearRecord.disability_support.label("disability_support"),
            SurveyPersonYearRecord.disability_support_details.label("disability_support_details"),
            SurveyPersonYearRecord.school_name_reported.label(
                "school_name_reported"
            ),
            SurveyPersonYearRecord.class_name_reported.label(
                "class_name_reported"
            ),
            School.code.label("school_code"),
            School.name.label("school_name"),
            Classroom.name.label("class_name"),
        )
        .select_from(SurveyForm)
        .join(Household, Household.id == SurveyForm.household_id)
        .join(
            SurveyPerson,
            SurveyPerson.household_id == Household.id,
        )
        .outerjoin(
            SurveyPersonYearRecord,
            and_(
                SurveyPersonYearRecord.survey_form_id == SurveyForm.id,
                SurveyPersonYearRecord.survey_person_id == SurveyPerson.id,
                SurveyPersonYearRecord.school_year_id
                == batch.school_year_id,
            ),
        )
        .outerjoin(School, School.id == SurveyPersonYearRecord.school_id)
        .outerjoin(
            Classroom,
            Classroom.id == SurveyPersonYearRecord.class_id,
        )
        .where(
            *report_filters,
            SurveyPerson.is_active.is_(True),
        )
        .order_by(
            Household.hamlet_name.asc(),
            Household.head_name.asc(),
            SurveyPerson.date_of_birth.asc(),
            SurveyPerson.full_name.asc(),
        )
    ).mappings().all()

    person_rows: list[dict[str, Any]] = []
    gender_counts = {
        "NAM": 0,
        "NU": 0,
        "KHAC": 0,
        "CHUA_XAC_DINH": 0,
    }
    age_group_order = ["0", "1", "2", "3", "4", "5", "6+", "Chưa rõ"]
    age_grouped = {
        key: {"age_group": key, "total": 0, "male": 0, "female": 0}
        for key in age_group_order
    }
    learning_grouped: dict[str, dict[str, Any]] = {}
    hamlet_grouped: dict[str, dict[str, Any]] = {}
    school_grouped: dict[str, dict[str, Any]] = {}

    # Chỉ báo thực sự còn dùng trong theo dõi PCGDMN hiện tại.
    # Các chỉ báo cũ vẫn nằm trong DB để bảo toàn lịch sử nhưng không đưa vào báo cáo.
    indicator_labels = {
        "completed_preschool_by_age": "Hoàn thành Chương trình GDMN theo độ tuổi",
        "attends_two_sessions_per_day": "Học 2 buổi/ngày",
        "prepared_vietnamese": "Trẻ dân tộc được chuẩn bị tiếng Việt",
    }
    indicator_grouped = {
        field_name: {
            "field_name": field_name,
            "label": label,
            "yes": 0,
            "no": 0,
            "unknown": 0,
        }
        for field_name, label in indicator_labels.items()
    }
    disability_status_counts = {
        code: 0 for code in DISABILITY_STATUS_LABELS
    }
    disability_type_counts = {
        code: 0 for code in DISABILITY_TYPE_LABELS
    }
    disability_level_counts = {
        code: 0 for code in DISABILITY_LEVEL_LABELS
    }
    disability_certificate_total = 0
    inclusive_education_total = 0
    disability_support_total = 0

    for raw_row in person_rows_raw:
        row = dict(raw_row)
        age = tinh_tuoi_tai_ngay(row["date_of_birth"], reference_date)
        if age is None:
            age_group = "Chưa rõ"
        elif age <= 5:
            age_group = str(max(age, 0))
        else:
            age_group = "6+"

        gender_key = chuan_hoa_ma(str(row["gender"] or ""))
        if gender_key in {"NAM", "MALE"}:
            normalized_gender = "NAM"
            gender_label = "Nam"
        elif gender_key in {"NU", "NỮ", "FEMALE"}:
            normalized_gender = "NU"
            gender_label = "Nữ"
        elif gender_key:
            normalized_gender = "KHAC"
            gender_label = str(row["gender"])
        else:
            normalized_gender = "CHUA_XAC_DINH"
            gender_label = "Chưa xác định"
        gender_counts[normalized_gender] += 1

        age_grouped[age_group]["total"] += 1
        if normalized_gender == "NAM":
            age_grouped[age_group]["male"] += 1
        elif normalized_gender == "NU":
            age_grouped[age_group]["female"] += 1

        learning_code = str(row["learning_status"] or "CHUA_XAC_DINH")
        learning_label = LEARNING_STATUS_LABELS.get(
            learning_code,
            "Chưa có dữ liệu năm học",
        )
        learning_item = learning_grouped.setdefault(
            learning_code,
            {
                "code": learning_code,
                "label": learning_label,
                "total": 0,
            },
        )
        learning_item["total"] += 1

        hamlet_name = str(row["hamlet_name"] or "Chưa xác định thôn/xóm")
        hamlet_item = hamlet_grouped.setdefault(
            hamlet_name,
            {
                "hamlet_name": hamlet_name,
                "people_total": 0,
                "household_ids": set(),
                "form_ids": set(),
            },
        )
        hamlet_item["people_total"] += 1
        hamlet_item["household_ids"].add(row["household_code"])
        hamlet_item["form_ids"].add(row["survey_form_id"])

        school_name = (
            row["school_name_reported"]
            or row["school_name"]
            or "Chưa xác định trường"
        )
        school_code = row["school_code"] or ""
        school_key = f"{school_code}|{school_name}"
        school_item = school_grouped.setdefault(
            school_key,
            {
                "school_code": school_code,
                "school_name": school_name,
                "people_total": 0,
                "studying_total": 0,
            },
        )
        school_item["people_total"] += 1
        if learning_code == "DANG_HOC":
            school_item["studying_total"] += 1

        for field_name, indicator_item in indicator_grouped.items():
            value = row.get(field_name)
            if value is True:
                indicator_item["yes"] += 1
            elif value is False:
                indicator_item["no"] += 1
            else:
                indicator_item["unknown"] += 1

        disability_status_code = str(
            row["disability_status"] or "CHUA_XAC_DINH"
        )
        if disability_status_code not in DISABILITY_STATUS_LABELS:
            disability_status_code = "CHUA_XAC_DINH"
        disability_status_counts[disability_status_code] += 1

        disability_type_code = row["disability_type"]
        if (
            disability_status_code == "CO_KHUYET_TAT"
            and disability_type_code in DISABILITY_TYPE_LABELS
        ):
            disability_type_counts[disability_type_code] += 1

        disability_level_code = row["disability_level"]
        if (
            disability_status_code == "CO_KHUYET_TAT"
            and disability_level_code in DISABILITY_LEVEL_LABELS
        ):
            disability_level_counts[disability_level_code] += 1

        if row["disability_certificate"] is True:
            disability_certificate_total += 1
        if row["inclusive_education"] is True:
            inclusive_education_total += 1
        if row["disability_support"] is True:
            disability_support_total += 1

        row.update(
            {
                "age": age,
                "age_group": age_group,
                "gender_label": gender_label,
                "form_status_label": FORM_STATUS_LABELS.get(
                    row["form_status"],
                    row["form_status"],
                ),
                "residency_status_label": RESIDENCY_STATUS_LABELS.get(
                    row["residency_status"],
                    row["residency_status"],
                ),
                "learning_status_label": learning_label,
                "disability_status_label": DISABILITY_STATUS_LABELS.get(
                    disability_status_code,
                    "Chưa xác định",
                ),
                "disability_type_label": DISABILITY_TYPE_LABELS.get(
                    disability_type_code,
                    "",
                ),
                "disability_level_label": DISABILITY_LEVEL_LABELS.get(
                    disability_level_code,
                    "",
                ),
                "school_display": school_name,
                "class_display": (
                    row["class_name_reported"]
                    or row["class_name"]
                    or ""
                ),
            }
        )
        person_rows.append(row)

    age_rows = [age_grouped[key] for key in age_group_order]
    learning_rows = sorted(
        learning_grouped.values(),
        key=lambda item: (-item["total"], item["label"]),
    )
    indicator_rows = list(indicator_grouped.values())
    disability_status_rows = [
        {
            "code": code,
            "label": label,
            "total": disability_status_counts[code],
        }
        for code, label in DISABILITY_STATUS_LABELS.items()
    ]
    disability_type_rows = [
        {
            "code": code,
            "label": label,
            "total": disability_type_counts[code],
        }
        for code, label in DISABILITY_TYPE_LABELS.items()
        if disability_type_counts[code] > 0
    ]
    disability_level_rows = [
        {
            "code": code,
            "label": label,
            "total": disability_level_counts[code],
        }
        for code, label in DISABILITY_LEVEL_LABELS.items()
        if disability_level_counts[code] > 0
    ]
    hamlet_rows: list[dict[str, Any]] = []
    for item in sorted(
        hamlet_grouped.values(),
        key=lambda value: value["hamlet_name"],
    ):
        hamlet_rows.append(
            {
                "hamlet_name": item["hamlet_name"],
                "household_total": len(item["household_ids"]),
                "form_total": len(item["form_ids"]),
                "people_total": item["people_total"],
            }
        )
    school_rows = sorted(
        school_grouped.values(),
        key=lambda item: (-item["studying_total"], item["school_name"]),
    )

    total_people = len(person_rows)
    people_with_year_record = sum(
        row["learning_status"] is not None for row in person_rows
    )
    studying_people = sum(
        row["learning_status"] == "DANG_HOC" for row in person_rows
    )
    completed_preschool_by_age = sum(
        row.get("completed_preschool_by_age") is True for row in person_rows
    )

    lock_logs = db.scalars(
        select(SurveyBatchLockLog)
        .where(SurveyBatchLockLog.survey_batch_id == batch.id)
        .order_by(
            SurveyBatchLockLog.created_at.desc(),
            SurveyBatchLockLog.id.desc(),
        )
        .limit(10)
    ).all()

    return {
        "reference_date": reference_date,
        "scope_label": quality_data["scope_label"],
        "progress_data": progress_data,
        "quality_summary": quality_data["summary"],
        "total_people": total_people,
        "people_with_year_record": people_with_year_record,
        "studying_people": studying_people,
        "completed_preschool_by_age": completed_preschool_by_age,
        "gender_counts": gender_counts,
        "age_rows": age_rows,
        "learning_rows": learning_rows,
        "indicator_rows": indicator_rows,
        "disability_total": disability_status_counts["CO_KHUYET_TAT"],
        "non_disability_total": disability_status_counts["KHONG_KHUYET_TAT"],
        "disability_unknown_total": disability_status_counts["CHUA_XAC_DINH"],
        "disability_certificate_total": disability_certificate_total,
        "inclusive_education_total": inclusive_education_total,
        "disability_support_total": disability_support_total,
        "disability_status_rows": disability_status_rows,
        "disability_type_rows": disability_type_rows,
        "disability_level_rows": disability_level_rows,
        "hamlet_rows": hamlet_rows,
        "school_rows": school_rows,
        "person_rows": person_rows,
        "lock_logs": lock_logs,
    }


@router.get(
    "/{batch_id}/bao-cao-tong-hop",
    response_class=HTMLResponse,
)
def bao_cao_tong_hop_ket_qua(
    batch_id: int,
    request: Request,
    status: str | None = None,
    db: Session = Depends(get_db),
):
    """Hiển thị báo cáo tổng hợp kết quả điều tra của một đợt."""

    batch = lay_dot_dieu_tra(db, batch_id)
    if batch is None:
        return RedirectResponse(url="/dieu-tra", status_code=303)

    report_data = tao_du_lieu_bao_cao_tong_hop(
        request=request,
        db=db,
        batch=batch,
    )

    return templates.TemplateResponse(
        request=request,
        name="surveys/summary_report.html",
        context={
            "nguoi_dung": lay_thong_tin_nguoi_dung(request),
            "batch": batch,
            "thong_bao": STATUS_MESSAGES.get(status or ""),
            **report_data,
            **tao_thong_tin_quyen_giao_dien(request),
        },
    )


@router.get("/{batch_id}/bao-cao-tong-hop/xuat-excel")
def xuat_excel_bao_cao_tong_hop(
    batch_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """Xuất báo cáo kết quả chính thức sau khi đợt đã khóa dữ liệu."""

    batch = lay_dot_dieu_tra(db, batch_id)
    if batch is None:
        return RedirectResponse(url="/dieu-tra", status_code=303)

    if not batch.is_locked:
        return RedirectResponse(
            url=(
                f"/dieu-tra/{batch.id}/bao-cao-tong-hop"
                "?status=summary_requires_lock"
            ),
            status_code=303,
        )

    data = tao_du_lieu_bao_cao_tong_hop(
        request=request,
        db=db,
        batch=batch,
    )

    workbook = Workbook()
    overview = workbook.active
    overview.title = "Tong quan"
    dien_tieu_de_bao_cao_tien_do(
        overview,
        title="BÁO CÁO TỔNG HỢP KẾT QUẢ ĐIỀU TRA PHỔ CẬP GIÁO DỤC",
        batch=batch,
        scope_label=data["scope_label"],
        last_column=4,
    )
    overview.append([])
    overview.append(["Thông tin", "Giá trị", "Thông tin", "Giá trị"])
    overview_rows = [
        (
            "Mã đợt",
            batch.code,
            "Trạng thái dữ liệu",
            "Đã khóa" if batch.is_locked else "Đang mở",
        ),
        (
            "Tên đợt",
            batch.name,
            "Ngày tham chiếu tính tuổi",
            data["reference_date"].strftime("%d/%m/%Y"),
        ),
        (
            "Năm học",
            batch.school_year.code,
            "Xã/phường",
            batch.commune.name,
        ),
        (
            "Tổng số phiếu",
            data["progress_data"]["total_forms"],
            "Phiếu hoàn thành",
            data["progress_data"]["completed_forms"],
        ),
        (
            "Tổng số đối tượng",
            data["total_people"],
            "Có dữ liệu năm học",
            data["people_with_year_record"],
        ),
        (
            "Đang học",
            data["studying_people"],
            "Hoàn thành CTGDMN theo độ tuổi",
            data["completed_preschool_by_age"],
        ),
        (
            "Trẻ có khuyết tật",
            data["disability_total"],
            "Trẻ học hòa nhập",
            data["inclusive_education_total"],
        ),
        (
            "Có giấy xác nhận khuyết tật",
            data["disability_certificate_total"],
            "Được hỗ trợ khuyết tật",
            data["disability_support_total"],
        ),
        (
            "Phiếu đạt yêu cầu",
            data["quality_summary"]["passed_forms"],
            "Phiếu cần xử lý",
            data["quality_summary"]["need_action_forms"],
        ),
        (
            "Thời điểm khóa",
            batch.locked_at.strftime("%d/%m/%Y %H:%M:%S")
            if batch.locked_at
            else "",
            "Lý do khóa",
            batch.lock_reason or "",
        ),
    ]
    for row in overview_rows:
        overview.append(row)
    dinh_dang_bang_bao_cao_tien_do(
        overview,
        header_row=4,
        last_row=overview.max_row,
        last_column=4,
    )

    age_sheet = workbook.create_sheet("Theo do tuoi")
    dien_tieu_de_bao_cao_tien_do(
        age_sheet,
        title="TỔNG HỢP ĐỐI TƯỢNG THEO ĐỘ TUỔI",
        batch=batch,
        scope_label=data["scope_label"],
        last_column=5,
    )
    age_sheet.append([])
    age_sheet.append(["STT", "Nhóm tuổi", "Tổng số", "Nam", "Nữ"])
    for index, item in enumerate(data["age_rows"], start=1):
        age_sheet.append([
            index,
            item["age_group"],
            item["total"],
            item["male"],
            item["female"],
        ])
    dinh_dang_bang_bao_cao_tien_do(
        age_sheet,
        header_row=4,
        last_row=age_sheet.max_row,
        last_column=5,
    )

    learning_sheet = workbook.create_sheet("Trang thai hoc tap")
    dien_tieu_de_bao_cao_tien_do(
        learning_sheet,
        title="TỔNG HỢP TRẠNG THÁI HỌC TẬP",
        batch=batch,
        scope_label=data["scope_label"],
        last_column=4,
    )
    learning_sheet.append([])
    learning_sheet.append(["STT", "Mã trạng thái", "Trạng thái", "Số lượng"])
    for index, item in enumerate(data["learning_rows"], start=1):
        learning_sheet.append([
            index,
            item["code"],
            item["label"],
            item["total"],
        ])
    dinh_dang_bang_bao_cao_tien_do(
        learning_sheet,
        header_row=4,
        last_row=learning_sheet.max_row,
        last_column=4,
    )

    indicator_sheet = workbook.create_sheet("Chi bao")
    dien_tieu_de_bao_cao_tien_do(
        indicator_sheet,
        title="TỔNG HỢP CÁC CHỈ BÁO NĂM HỌC",
        batch=batch,
        scope_label=data["scope_label"],
        last_column=6,
    )
    indicator_sheet.append([])
    indicator_sheet.append([
        "STT",
        "Chỉ báo",
        "Có",
        "Không",
        "Chưa xác định",
        "Tổng",
    ])
    for index, item in enumerate(data["indicator_rows"], start=1):
        indicator_sheet.append([
            index,
            item["label"],
            item["yes"],
            item["no"],
            item["unknown"],
            item["yes"] + item["no"] + item["unknown"],
        ])
    dinh_dang_bang_bao_cao_tien_do(
        indicator_sheet,
        header_row=4,
        last_row=indicator_sheet.max_row,
        last_column=6,
    )

    disability_sheet = workbook.create_sheet("Khuyet tat")
    dien_tieu_de_bao_cao_tien_do(
        disability_sheet,
        title="TỔNG HỢP TRẺ KHUYẾT TẬT VÀ HỌC HÒA NHẬP",
        batch=batch,
        scope_label=data["scope_label"],
        last_column=4,
    )
    disability_sheet.append([])
    disability_sheet.append(["Nhóm", "Nội dung", "Số lượng", "Ghi chú"])
    for item in data["disability_status_rows"]:
        disability_sheet.append(["Tình trạng", item["label"], item["total"], ""])
    for item in data["disability_type_rows"]:
        disability_sheet.append(["Dạng khuyết tật", item["label"], item["total"], ""])
    for item in data["disability_level_rows"]:
        disability_sheet.append(["Mức độ", item["label"], item["total"], ""])
    disability_sheet.append([
        "Hồ sơ", "Có giấy xác nhận khuyết tật",
        data["disability_certificate_total"], "",
    ])
    disability_sheet.append([
        "Giáo dục", "Đang học hòa nhập",
        data["inclusive_education_total"], "",
    ])
    disability_sheet.append([
        "Hỗ trợ", "Được hỗ trợ trong năm học",
        data["disability_support_total"], "",
    ])
    dinh_dang_bang_bao_cao_tien_do(
        disability_sheet,
        header_row=4,
        last_row=disability_sheet.max_row,
        last_column=4,
    )

    hamlet_sheet = workbook.create_sheet("Theo dia ban")
    dien_tieu_de_bao_cao_tien_do(
        hamlet_sheet,
        title="TỔNG HỢP THEO THÔN/XÓM/KHỐI/BẢN",
        batch=batch,
        scope_label=data["scope_label"],
        last_column=5,
    )
    hamlet_sheet.append([])
    hamlet_sheet.append([
        "STT",
        "Thôn/xóm/khối/bản",
        "Số hộ",
        "Số phiếu",
        "Số đối tượng",
    ])
    for index, item in enumerate(data["hamlet_rows"], start=1):
        hamlet_sheet.append([
            index,
            item["hamlet_name"],
            item["household_total"],
            item["form_total"],
            item["people_total"],
        ])
    dinh_dang_bang_bao_cao_tien_do(
        hamlet_sheet,
        header_row=4,
        last_row=hamlet_sheet.max_row,
        last_column=5,
    )

    school_sheet = workbook.create_sheet("Theo truong")
    dien_tieu_de_bao_cao_tien_do(
        school_sheet,
        title="TỔNG HỢP ĐỐI TƯỢNG THEO TRƯỜNG",
        batch=batch,
        scope_label=data["scope_label"],
        last_column=5,
    )
    school_sheet.append([])
    school_sheet.append([
        "STT",
        "Mã trường",
        "Tên trường",
        "Tổng đối tượng",
        "Đang học",
    ])
    for index, item in enumerate(data["school_rows"], start=1):
        school_sheet.append([
            index,
            item["school_code"],
            item["school_name"],
            item["people_total"],
            item["studying_total"],
        ])
    dinh_dang_bang_bao_cao_tien_do(
        school_sheet,
        header_row=4,
        last_row=school_sheet.max_row,
        last_column=5,
    )

    detail_sheet = workbook.create_sheet("Chi tiet doi tuong")
    detail_headers = [
        "STT",
        "Số phiếu",
        "Mã hộ",
        "Chủ hộ",
        "Thôn/xóm",
        "Mã đối tượng",
        "Họ và tên",
        "Ngày sinh",
        "Tuổi",
        "Giới tính",
        "Dân tộc",
        "Quan hệ chủ hộ",
        "Số định danh",
        "Mã học sinh Bộ",
        "Cư trú",
        "Trạng thái học tập",
        "Trường",
        "Lớp",
        "Tình trạng khuyết tật",
        "Dạng khuyết tật",
        "Mức độ khuyết tật",
        "Giấy xác nhận khuyết tật",
        "Học hòa nhập",
        "Được hỗ trợ",
        "Nội dung hỗ trợ",
        "Hoàn thành CTGDMN theo độ tuổi",
        "Học 2 buổi/ngày",
        "Chuẩn bị tiếng Việt",
    ]
    dien_tieu_de_bao_cao_tien_do(
        detail_sheet,
        title="DANH SÁCH CHI TIẾT ĐỐI TƯỢNG ĐIỀU TRA",
        batch=batch,
        scope_label=data["scope_label"],
        last_column=len(detail_headers),
    )
    detail_sheet.append([])
    detail_sheet.append(detail_headers)
    for index, row in enumerate(data["person_rows"], start=1):
        detail_sheet.append([
            index,
            row["form_number"],
            row["household_code"],
            row["head_name"],
            row["hamlet_name"] or "",
            row["person_code"],
            row["full_name"],
            row["date_of_birth"].strftime("%d/%m/%Y")
            if row["date_of_birth"]
            else "",
            row["age"] if row["age"] is not None else "",
            row["gender_label"],
            row["ethnic_group"] or "",
            row["relationship_to_head"] or "",
            row["personal_id"] or "",
            row["ministry_student_code"] or "",
            row["residency_status_label"],
            row["learning_status_label"],
            row["school_display"],
            row["class_display"],
            row["disability_status_label"],
            row["disability_type_label"],
            row["disability_level_label"],
            gia_tri_co_khong(row["disability_certificate"]),
            gia_tri_co_khong(row["inclusive_education"]),
            gia_tri_co_khong(row["disability_support"]),
            row["disability_support_details"] or "",
            gia_tri_co_khong(row.get("completed_preschool_by_age")),
            gia_tri_co_khong(row.get("attends_two_sessions_per_day")),
            gia_tri_co_khong(row.get("prepared_vietnamese")),
        ])
    dinh_dang_bang_bao_cao_tien_do(
        detail_sheet,
        header_row=4,
        last_row=detail_sheet.max_row,
        last_column=len(detail_headers),
    )

    output = BytesIO()
    workbook.save(output)
    output.seek(0)

    safe_year = str(batch.school_year.code).replace("/", "-")
    filename = f"bao_cao_tong_hop_{batch.code}_{safe_year}.xlsx"
    return StreamingResponse(
        output,
        media_type=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        },
    )


# =========================================================
# BÀI 12D-7: KẾ THỪA DỮ LIỆU SANG NĂM HỌC MỚI
# =========================================================

def cong_mot_nam(value: date | None) -> date | None:
    """Cộng một năm và xử lý an toàn trường hợp ngày 29/02."""

    if value is None:
        return None
    try:
        return value.replace(year=value.year + 1)
    except ValueError:
        return value.replace(year=value.year + 1, day=28)


def tao_ma_nam_hoc_ke_tiep(code: str) -> str:
    """Sinh mã năm học kế tiếp từ dạng 2025-2026."""

    numbers = [
        int(value)
        for value in "".join(
            character if character.isdigit() else " "
            for character in str(code or "")
        ).split()
    ]
    if len(numbers) >= 2:
        return f"{numbers[1]}-{numbers[1] + 1}"
    if len(numbers) == 1:
        return f"{numbers[0] + 1}-{numbers[0] + 2}"
    next_year = date.today().year + 1
    return f"{next_year}-{next_year + 1}"


def tao_mac_dinh_dot_ke_tiep(source_batch: SurveyBatch) -> dict[str, str]:
    """Chuẩn bị giá trị gợi ý để tạo nhanh đợt của năm học sau."""

    next_code = tao_ma_nam_hoc_ke_tiep(source_batch.school_year.code)
    suggested_start = cong_mot_nam(
        source_batch.start_date
        or source_batch.school_year.start_date
        or date.today()
    )
    suggested_end = cong_mot_nam(
        source_batch.end_date
        or source_batch.school_year.end_date
    )
    return {
        "school_year_code": next_code,
        "name": f"Điều tra phổ cập giáo dục năm học {next_code}",
        "start_date": suggested_start.isoformat() if suggested_start else "",
        "end_date": suggested_end.isoformat() if suggested_end else "",
    }


def khoa_sap_xep_nam_hoc(school_year: SchoolYear) -> tuple[int, ...]:
    """Tạo khóa so sánh năm học, ưu tiên ngày bắt đầu rồi đến mã năm."""

    if school_year.start_date is not None:
        return (
            school_year.start_date.year,
            school_year.start_date.month,
            school_year.start_date.day,
        )

    numbers = [
        int(value)
        for value in "".join(
            character if character.isdigit() else " "
            for character in str(school_year.code or "")
        ).split()
    ]
    return tuple(numbers or [0])


def lay_cac_dot_dich_ke_thua(
    db: Session,
    source_batch: SurveyBatch,
) -> list[SurveyBatch]:
    """Lấy các đợt tương lai cùng xã có thể nhận dữ liệu kế thừa."""

    candidates = db.scalars(
        select(SurveyBatch)
        .options(
            selectinload(SurveyBatch.school_year),
            selectinload(SurveyBatch.commune),
        )
        .where(
            SurveyBatch.commune_id == source_batch.commune_id,
            SurveyBatch.id != source_batch.id,
            SurveyBatch.school_year_id != source_batch.school_year_id,
            SurveyBatch.is_locked.is_(False),
        )
    ).all()

    source_key = khoa_sap_xep_nam_hoc(source_batch.school_year)
    future_batches = [
        item
        for item in candidates
        if khoa_sap_xep_nam_hoc(item.school_year) > source_key
    ]
    future_batches.sort(
        key=lambda item: (
            khoa_sap_xep_nam_hoc(item.school_year),
            item.start_date or date.min,
            item.id,
        )
    )
    return future_batches


def tao_du_lieu_ke_thua_nam_hoc(
    *,
    db: Session,
    source_batch: SurveyBatch,
) -> dict[str, Any]:
    """Tính trước số phiếu và hồ sơ sẽ được tạo ở từng đợt đích."""

    source_household_ids = list(
        db.scalars(
            select(SurveyForm.household_id)
            .where(SurveyForm.survey_batch_id == source_batch.id)
            .order_by(SurveyForm.id)
        ).all()
    )

    source_form_total = len(source_household_ids)
    active_person_total = 0
    source_year_record_total = 0

    if source_household_ids:
        active_person_total = int(
            db.scalar(
                select(func.count(SurveyPerson.id)).where(
                    SurveyPerson.household_id.in_(source_household_ids),
                    SurveyPerson.is_active.is_(True),
                )
            )
            or 0
        )
        source_year_record_total = int(
            db.scalar(
                select(func.count(SurveyPersonYearRecord.id)).where(
                    SurveyPersonYearRecord.survey_form_id.in_(
                        select(SurveyForm.id).where(
                            SurveyForm.survey_batch_id == source_batch.id
                        )
                    ),
                    SurveyPersonYearRecord.school_year_id
                    == source_batch.school_year_id,
                )
            )
            or 0
        )

    target_rows: list[dict[str, Any]] = []
    for target_batch in lay_cac_dot_dich_ke_thua(db, source_batch):
        existing_household_ids: set[int] = set()
        if source_household_ids:
            existing_household_ids = {
                int(value)
                for value in db.scalars(
                    select(SurveyForm.household_id).where(
                        SurveyForm.survey_batch_id == target_batch.id,
                        SurveyForm.household_id.in_(source_household_ids),
                    )
                ).all()
            }

        new_household_ids = [
            household_id
            for household_id in source_household_ids
            if household_id not in existing_household_ids
        ]
        new_person_total = 0
        if new_household_ids:
            new_person_total = int(
                db.scalar(
                    select(func.count(SurveyPerson.id)).where(
                        SurveyPerson.household_id.in_(new_household_ids),
                        SurveyPerson.is_active.is_(True),
                    )
                )
                or 0
            )

        target_rows.append(
            {
                "batch": target_batch,
                "existing_form_total": len(existing_household_ids),
                "new_form_total": len(new_household_ids),
                "new_year_record_total": new_person_total,
            }
        )

    return {
        "source_summary": {
            "form_total": source_form_total,
            "household_total": source_form_total,
            "active_person_total": active_person_total,
            "year_record_total": source_year_record_total,
        },
        "target_rows": target_rows,
    }


def tao_ban_sao_truoc_khi_ke_thua() -> Path:
    """Tạo bản sao SQLite trước khi sinh phiếu cho năm học mới."""

    database_path = Path(DATABASE_PATH)
    backup_dir = database_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"before_year_inheritance_{timestamp}.db"

    source = sqlite3.connect(str(database_path))
    target = sqlite3.connect(str(backup_path))
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()
    return backup_path


def thuc_hien_ke_thua_nam_hoc(
    *,
    db: Session,
    source_batch: SurveyBatch,
    target_batch: SurveyBatch,
) -> dict[str, int]:
    """
    Sinh phiếu mới cho các hộ của đợt nguồn.

    Hồ sơ hộ và đối tượng là dữ liệu dùng chung nên không nhân bản. Mỗi
    đối tượng đang theo dõi được tạo một bản ghi năm học trống để cán bộ
    rà soát, cập nhật lại trường/lớp, trạng thái học tập và 8 chỉ báo.
    """

    source_forms = db.scalars(
        select(SurveyForm)
        .options(
            selectinload(SurveyForm.household)
            .selectinload(Household.people)
        )
        .where(SurveyForm.survey_batch_id == source_batch.id)
        .order_by(SurveyForm.id)
    ).all()

    existing_household_ids = {
        int(value)
        for value in db.scalars(
            select(SurveyForm.household_id).where(
                SurveyForm.survey_batch_id == target_batch.id
            )
        ).all()
    }

    created_forms = 0
    skipped_forms = 0
    created_year_records = 0

    for source_form in source_forms:
        household = source_form.household
        if household.id in existing_household_ids:
            skipped_forms += 1
            continue

        target_form = SurveyForm(
            survey_batch_id=target_batch.id,
            household_id=household.id,
            form_number=tao_so_phieu(db, target_batch),
            head_name_snapshot=household.head_name,
            address_snapshot=household.address,
            hamlet_name_snapshot=household.hamlet_name,
            status="CHUA_DIEU_TRA",
        )
        db.add(target_form)
        db.flush()

        created_forms += 1
        existing_household_ids.add(household.id)

        for person in household.people:
            if not person.is_active:
                continue

            db.add(
                SurveyPersonYearRecord(
                    survey_form_id=target_form.id,
                    survey_person_id=person.id,
                    school_year_id=target_batch.school_year_id,
                    learning_status="CHUA_XAC_DINH",
                    notes=(
                        f"Kế thừa hồ sơ từ đợt {source_batch.code}; "
                        f"cần rà soát và cập nhật cho năm học "
                        f"{target_batch.school_year.code}."
                    ),
                )
            )
            created_year_records += 1

    return {
        "created_forms": created_forms,
        "skipped_forms": skipped_forms,
        "created_year_records": created_year_records,
    }


def hien_thi_trang_ke_thua_nam_hoc(
    *,
    request: Request,
    db: Session,
    source_batch: SurveyBatch,
    selected_target_id: int = 0,
    thong_bao: str = "",
    thong_bao_loi: str = "",
    result_summary: dict[str, Any] | None = None,
    status_code: int = 200,
):
    data = tao_du_lieu_ke_thua_nam_hoc(
        db=db,
        source_batch=source_batch,
    )

    return templates.TemplateResponse(
        request=request,
        name="surveys/year_inheritance.html",
        context={
            "nguoi_dung": lay_thong_tin_nguoi_dung(request),
            "source_batch": source_batch,
            "selected_target_id": selected_target_id,
            "thong_bao": thong_bao,
            "thong_bao_loi": thong_bao_loi,
            "result_summary": result_summary,
            "quick_create": tao_mac_dinh_dot_ke_tiep(source_batch),
            **data,
            **tao_thong_tin_quyen_giao_dien(request),
        },
        status_code=status_code,
    )


@router.get(
    "/{batch_id}/ke-thua-du-lieu",
    response_class=HTMLResponse,
)
def ke_thua_du_lieu_nam_hoc(
    batch_id: int,
    request: Request,
    target_id: int = 0,
    status: str | None = None,
    created_forms: int = 0,
    skipped_forms: int = 0,
    created_year_records: int = 0,
    backup: str = "",
    db: Session = Depends(get_db),
):
    user = lay_thong_tin_nguoi_dung(request)
    if not is_admin_role(user.get("role_code")):
        return RedirectResponse(
            url="/dieu-tra?status=inheritance_admin_only",
            status_code=303,
        )

    source_batch = lay_dot_dieu_tra(db, batch_id)
    if source_batch is None:
        return RedirectResponse(url="/dieu-tra", status_code=303)

    if not source_batch.is_locked:
        return RedirectResponse(
            url="/dieu-tra?status=inheritance_source_requires_lock",
            status_code=303,
        )

    result_summary = None
    if status == "inheritance_success":
        result_summary = {
            "message": STATUS_MESSAGES["inheritance_success"],
            "created_forms": max(int(created_forms or 0), 0),
            "skipped_forms": max(int(skipped_forms or 0), 0),
            "created_year_records": max(
                int(created_year_records or 0),
                0,
            ),
            "backup": Path(backup).name if backup else "",
        }

    return hien_thi_trang_ke_thua_nam_hoc(
        request=request,
        db=db,
        source_batch=source_batch,
        selected_target_id=max(int(target_id or 0), 0),
        thong_bao=(
            STATUS_MESSAGES.get(status or "", "")
            if status != "inheritance_success"
            else ""
        ),
        result_summary=result_summary,
    )


@router.post("/{batch_id}/ke-thua-du-lieu/tao-dot-dich")
def tao_nhanh_dot_dich_ke_thua(
    batch_id: int,
    request: Request,
    school_year_code: Annotated[str, Form()],
    target_name: Annotated[str, Form()],
    start_date: Annotated[str, Form()],
    end_date: Annotated[str, Form()] = "",
    confirm_create_target: Annotated[str, Form()] = "",
    db: Session = Depends(get_db),
):
    user = lay_thong_tin_nguoi_dung(request)
    if not is_admin_role(user.get("role_code")):
        return RedirectResponse(
            url="/dieu-tra?status=inheritance_admin_only",
            status_code=303,
        )

    source_batch = lay_dot_dieu_tra(db, batch_id)
    if source_batch is None:
        return RedirectResponse(url="/dieu-tra", status_code=303)
    if not source_batch.is_locked:
        return RedirectResponse(
            url="/dieu-tra?status=inheritance_source_requires_lock",
            status_code=303,
        )

    school_year_code = chuan_hoa_van_ban(school_year_code)[:20]
    target_name = chuan_hoa_van_ban(target_name)[:300]
    parsed_start, start_error = chuyen_ngay(
        start_date,
        "Ngày bắt đầu",
        bat_buoc=True,
    )
    parsed_end, end_error = chuyen_ngay(
        end_date,
        "Ngày kết thúc",
        bat_buoc=False,
    )

    errors: list[str] = []
    if not school_year_code:
        errors.append("Mã năm học không được để trống.")
    if not target_name:
        errors.append("Tên đợt điều tra không được để trống.")
    if start_error:
        errors.append(start_error)
    if end_error:
        errors.append(end_error)
    if parsed_start and parsed_end and parsed_end < parsed_start:
        errors.append("Ngày kết thúc không được trước ngày bắt đầu.")
    if confirm_create_target != "yes":
        errors.append("Bạn cần xác nhận trước khi tạo đợt năm học mới.")

    school_year = db.scalar(
        select(SchoolYear).where(SchoolYear.code == school_year_code)
    )
    if school_year is not None and not school_year.is_active:
        errors.append("Năm học đã tồn tại nhưng đang ngừng sử dụng.")

    if errors:
        return hien_thi_trang_ke_thua_nam_hoc(
            request=request,
            db=db,
            source_batch=source_batch,
            thong_bao_loi=" ".join(errors),
            status_code=400,
        )

    try:
        if school_year is None:
            school_year = SchoolYear(
                code=school_year_code,
                name=f"Năm học {school_year_code}",
                start_date=parsed_start,
                end_date=parsed_end,
                is_active=True,
            )
            db.add(school_year)
            db.flush()

        if khoa_sap_xep_nam_hoc(school_year) <= khoa_sap_xep_nam_hoc(
            source_batch.school_year
        ):
            db.rollback()
            return hien_thi_trang_ke_thua_nam_hoc(
                request=request,
                db=db,
                source_batch=source_batch,
                thong_bao_loi=(
                    "Năm học đích phải nằm sau năm học của đợt nguồn."
                ),
                status_code=400,
            )

        existing_target = db.scalar(
            select(SurveyBatch)
            .options(
                selectinload(SurveyBatch.school_year),
                selectinload(SurveyBatch.commune),
            )
            .where(
                SurveyBatch.commune_id == source_batch.commune_id,
                SurveyBatch.school_year_id == school_year.id,
            )
            .order_by(SurveyBatch.id)
        )
        if existing_target is not None:
            if existing_target.is_locked:
                db.rollback()
                return hien_thi_trang_ke_thua_nam_hoc(
                    request=request,
                    db=db,
                    source_batch=source_batch,
                    thong_bao_loi=(
                        "Đợt của năm học đích đã tồn tại nhưng đang khóa dữ liệu."
                    ),
                    status_code=400,
                )
            db.commit()
            return RedirectResponse(
                url=(
                    f"/dieu-tra/{source_batch.id}/ke-thua-du-lieu"
                    f"?status=inheritance_target_created"
                    f"&target_id={existing_target.id}"
                ),
                status_code=303,
            )

        target_batch = SurveyBatch(
            code=tao_ma_dot_dieu_tra(
                db=db,
                commune=source_batch.commune,
                school_year=school_year,
            ),
            name=target_name,
            school_year_id=school_year.id,
            commune_id=source_batch.commune_id,
            status="CHUAN_BI",
            start_date=parsed_start,
            end_date=parsed_end,
            created_by_user_id=user.get("id"),
            notes=(
                f"Đợt được tạo để kế thừa dữ liệu từ {source_batch.code}."
            ),
        )
        db.add(target_batch)
        db.commit()
        db.refresh(target_batch)
    except Exception as error:
        db.rollback()
        return hien_thi_trang_ke_thua_nam_hoc(
            request=request,
            db=db,
            source_batch=source_batch,
            thong_bao_loi=(
                "Không thể tạo đợt năm học mới. "
                f"Chi tiết kỹ thuật: {type(error).__name__}."
            ),
            status_code=500,
        )

    return RedirectResponse(
        url=(
            f"/dieu-tra/{source_batch.id}/ke-thua-du-lieu"
            f"?status=inheritance_target_created"
            f"&target_id={target_batch.id}"
        ),
        status_code=303,
    )


@router.post("/{batch_id}/ke-thua-du-lieu")
def luu_ke_thua_du_lieu_nam_hoc(
    batch_id: int,
    request: Request,
    target_batch_id: Annotated[int, Form()],
    confirm_inheritance: Annotated[str, Form()] = "",
    db: Session = Depends(get_db),
):
    user = lay_thong_tin_nguoi_dung(request)
    if not is_admin_role(user.get("role_code")):
        return RedirectResponse(
            url="/dieu-tra?status=inheritance_admin_only",
            status_code=303,
        )

    source_batch = lay_dot_dieu_tra(db, batch_id)
    if source_batch is None:
        return RedirectResponse(url="/dieu-tra", status_code=303)

    if not source_batch.is_locked:
        return RedirectResponse(
            url="/dieu-tra?status=inheritance_source_requires_lock",
            status_code=303,
        )

    candidate_ids = {
        item.id for item in lay_cac_dot_dich_ke_thua(db, source_batch)
    }
    target_batch = lay_dot_dieu_tra(db, target_batch_id)

    if (
        target_batch is None
        or target_batch.id not in candidate_ids
        or target_batch.commune_id != source_batch.commune_id
        or target_batch.school_year_id == source_batch.school_year_id
        or target_batch.is_locked
    ):
        return hien_thi_trang_ke_thua_nam_hoc(
            request=request,
            db=db,
            source_batch=source_batch,
            selected_target_id=target_batch_id,
            thong_bao_loi=(
                "Đợt đích không hợp lệ. Hãy chọn một đợt chưa khóa, "
                "cùng xã/phường và thuộc năm học sau."
            ),
            status_code=400,
        )

    if confirm_inheritance != "yes":
        return hien_thi_trang_ke_thua_nam_hoc(
            request=request,
            db=db,
            source_batch=source_batch,
            selected_target_id=target_batch_id,
            thong_bao_loi=(
                "Bạn cần đánh dấu xác nhận trước khi thực hiện kế thừa."
            ),
            status_code=400,
        )

    source_form_total = int(
        db.scalar(
            select(func.count(SurveyForm.id)).where(
                SurveyForm.survey_batch_id == source_batch.id
            )
        )
        or 0
    )
    if source_form_total == 0:
        return hien_thi_trang_ke_thua_nam_hoc(
            request=request,
            db=db,
            source_batch=source_batch,
            selected_target_id=target_batch_id,
            thong_bao_loi="Đợt nguồn chưa có phiếu để kế thừa.",
            status_code=400,
        )

    backup_path = tao_ban_sao_truoc_khi_ke_thua()

    try:
        summary = thuc_hien_ke_thua_nam_hoc(
            db=db,
            source_batch=source_batch,
            target_batch=target_batch,
        )
        db.commit()
    except Exception as error:
        db.rollback()
        return hien_thi_trang_ke_thua_nam_hoc(
            request=request,
            db=db,
            source_batch=source_batch,
            selected_target_id=target_batch_id,
            thong_bao_loi=(
                "Không thể hoàn tất kế thừa. Dữ liệu chưa được thay đổi. "
                f"Chi tiết kỹ thuật: {type(error).__name__}."
            ),
            status_code=500,
        )

    query = urlencode(
        {
            "status": "inheritance_success",
            "target_id": target_batch.id,
            "created_forms": summary["created_forms"],
            "skipped_forms": summary["skipped_forms"],
            "created_year_records": summary["created_year_records"],
            "backup": backup_path.name,
        }
    )
    return RedirectResponse(
        url=f"/dieu-tra/{source_batch.id}/ke-thua-du-lieu?{query}",
        status_code=303,
    )


# =========================================================
# XUẤT EXCEL ĐI ĐIỀU TRA
# =========================================================

def gia_tri_co_khong(value: bool | None) -> str:
    """Đổi dữ liệu Boolean sang chữ dễ đọc trong Excel."""

    if value is None:
        return ""

    return "Có" if value else "Không"


def tao_tieu_de_excel(
    worksheet,
    *,
    title: str,
    last_column: int,
) -> None:
    """Tạo phần tiêu đề chung của trang Excel điều tra."""

    worksheet.merge_cells(
        start_row=1,
        start_column=1,
        end_row=1,
        end_column=last_column,
    )
    title_cell = worksheet.cell(row=1, column=1, value=title)
    title_cell.font = Font(size=16, bold=True)
    title_cell.alignment = Alignment(horizontal="center")


@router.get("/{batch_id}/ho-dan/xuat-excel")
def xuat_excel_di_dieu_tra(
    batch_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """Xuất Excel điều tra theo mẫu Phiếu điều tra PCGD-XMC A4 ngang; file xuất dùng lại để nhập."""

    from app.household_excel_exchange import export_household_excel

    return export_household_excel(
        batch_id=batch_id,
        request=request,
        db=db,
    )

    batch = lay_dot_dieu_tra(db, batch_id)

    if batch is None:
        return RedirectResponse(
            url="/dieu-tra",
            status_code=303,
        )

    survey_forms = db.scalars(
        select(SurveyForm)
        .join(
            Household,
            Household.id == SurveyForm.household_id,
        )
        .options(
            selectinload(SurveyForm.household)
            .selectinload(Household.people),
            with_loader_criteria(
                SurveyPerson,
                SurveyPerson.is_active.is_(True),
                include_aliases=True,
            ),
        )
        .where(
            SurveyForm.survey_batch_id == batch.id,
            *tao_bo_loc_bao_cao_theo_nguoi_dung(request),
        )
        .order_by(
            Household.hamlet_name.asc(),
            Household.head_name.asc(),
            SurveyForm.id.asc(),
        )
    ).all()

    person_ids = [
        person.id
        for survey_form in survey_forms
        for person in survey_form.household.people
        if person.is_active
    ]

    year_records = db.scalars(
        select(SurveyPersonYearRecord).where(
            SurveyPersonYearRecord.survey_person_id.in_(person_ids),
            SurveyPersonYearRecord.school_year_id
            == batch.school_year_id,
        )
    ).all() if person_ids else []

    record_by_person_id = {
        item.survey_person_id: item
        for item in year_records
    }

    school_ids = {
        item.school_id
        for item in year_records
        if item.school_id is not None
    }
    class_ids = {
        item.class_id
        for item in year_records
        if item.class_id is not None
    }

    schools = {
        item.id: item
        for item in db.scalars(
            select(School).where(School.id.in_(school_ids))
        ).all()
    } if school_ids else {}

    classrooms = {
        item.id: item
        for item in db.scalars(
            select(Classroom).where(Classroom.id.in_(class_ids))
        ).all()
    } if class_ids else {}

    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "DIEU_TRA"

    visible_headers = [
        "STT",
        "Số phiếu",
        "Mã hộ",
        "Thôn/xóm/khối/bản",
        "Chủ hộ",
        "Địa chỉ hộ",
        "Điện thoại chủ hộ",
        "Trạng thái phiếu",
        "Mã đối tượng",
        "Họ và tên",
        "Ngày sinh",
        "Giới tính",
        "Dân tộc",
        "Quan hệ với chủ hộ",
        "Số định danh cá nhân",
        "Mã Bộ GD&ĐT",
        "Trạng thái cư trú",
        "Địa chỉ thường trú",
        "Chỗ ở hiện nay",
        "Tình trạng học tập",
        "Tên trường",
        "Tên lớp",
        "Tình trạng khuyết tật",
        "Dạng khuyết tật",
        "Mức độ khuyết tật",
        "Có giấy xác nhận khuyết tật",
        "Học hòa nhập",
        "Được hỗ trợ khuyết tật",
        "Nội dung hỗ trợ khuyết tật",
        "Hoàn thành CT GDMN 5 tuổi",
        "Đi học đủ ngày theo quy định",
        "Đi học chuyên cần",
        "Được chuẩn bị tiếng Việt",
        "Theo dõi biểu đồ cân nặng",
        "Suy dinh dưỡng nhẹ cân",
        "Theo dõi biểu đồ chiều cao",
        "Suy dinh dưỡng thấp còi",
        "Hoàn cảnh đặc biệt",
        "Ghi chú đối tượng",
        "Ghi chú năm học",
    ]

    technical_headers = [
        "__survey_form_id",
        "__household_id",
        "__survey_person_id",
        "__school_year_id",
        "__school_id",
        "__class_id",
        "__is_active",
    ]

    all_headers = visible_headers + technical_headers
    last_column = len(all_headers)

    tao_tieu_de_excel(
        worksheet,
        title="DANH SÁCH ĐIỀU TRA PHỔ CẬP GIÁO DỤC",
        last_column=last_column,
    )

    worksheet.cell(
        row=2,
        column=1,
        value=f"Đợt điều tra: {batch.code} – {batch.name}",
    )
    worksheet.cell(
        row=3,
        column=1,
        value=(
            f"Năm học: {batch.school_year.code} | "
            f"Xã/phường: {batch.commune.name} "
            f"(Mã {batch.commune.code})"
        ),
    )
    worksheet.cell(
        row=4,
        column=1,
        value=(
            "Chỉ sửa dữ liệu từ hàng 7 trở xuống. "
            "Không đổi tên cột, không xóa cột kỹ thuật và không đổi tên sheet."
        ),
    )

    header_row = 6
    for column_index, header in enumerate(all_headers, start=1):
        cell = worksheet.cell(
            row=header_row,
            column=column_index,
            value=header,
        )
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1F4E78")
        cell.alignment = Alignment(
            horizontal="center",
            vertical="center",
            wrap_text=True,
        )

    thin_side = Side(style="thin", color="D9E2F3")
    border = Border(
        left=thin_side,
        right=thin_side,
        top=thin_side,
        bottom=thin_side,
    )

    row_number = header_row + 1
    sequence = 1

    for survey_form in survey_forms:
        household = survey_form.household
        active_people = [
            item
            for item in household.people
            if item.is_active
        ]
        active_people.sort(
            key=lambda item: (
                item.date_of_birth or date.max,
                item.full_name,
                item.id,
            )
        )

        # Hộ chưa có người vẫn được xuất một dòng để cán bộ điều tra
        # có thể bổ sung dữ liệu ngoài thực địa.
        people_for_export: list[SurveyPerson | None] = (
            active_people if active_people else [None]
        )

        for person in people_for_export:
            record = (
                record_by_person_id.get(person.id)
                if person is not None
                else None
            )

            school = (
                schools.get(record.school_id)
                if record is not None
                else None
            )
            classroom = (
                classrooms.get(record.class_id)
                if record is not None
                else None
            )

            school_name = ""
            class_name = ""
            if record is not None:
                school_name = (
                    record.school_name_reported
                    or (school.name if school is not None else "")
                )
                class_name = (
                    record.class_name_reported
                    or (
                        classroom.name
                        if classroom is not None
                        else ""
                    )
                )

            values = [
                sequence,
                survey_form.form_number,
                household.code,
                household.hamlet_name or "",
                household.head_name,
                household.address,
                household.phone or "",
                FORM_STATUS_LABELS.get(
                    survey_form.status,
                    survey_form.status,
                ),
                person.code if person is not None else "",
                person.full_name if person is not None else "",
                (
                    person.date_of_birth
                    if person is not None
                    else ""
                ),
                person.gender or "" if person is not None else "",
                (
                    person.ethnic_group or ""
                    if person is not None
                    else ""
                ),
                (
                    person.relationship_to_head or ""
                    if person is not None
                    else ""
                ),
                (
                    person.personal_id or ""
                    if person is not None
                    else ""
                ),
                (
                    person.ministry_student_code or ""
                    if person is not None
                    else ""
                ),
                (
                    RESIDENCY_STATUS_LABELS.get(
                        person.residency_status,
                        person.residency_status,
                    )
                    if person is not None
                    else ""
                ),
                (
                    person.permanent_address or ""
                    if person is not None
                    else ""
                ),
                (
                    person.current_address or ""
                    if person is not None
                    else ""
                ),
                (
                    LEARNING_STATUS_LABELS.get(
                        record.learning_status,
                        record.learning_status,
                    )
                    if record is not None
                    else ""
                ),
                school_name,
                class_name,
                (
                    DISABILITY_STATUS_LABELS.get(
                        getattr(record, "disability_status", "CHUA_XAC_DINH"),
                        "Chưa xác định",
                    )
                    if record is not None
                    else ""
                ),
                (
                    DISABILITY_TYPE_LABELS.get(
                        getattr(record, "disability_type", None),
                        "",
                    )
                    if record is not None
                    else ""
                ),
                (
                    DISABILITY_LEVEL_LABELS.get(
                        getattr(record, "disability_level", None),
                        "",
                    )
                    if record is not None
                    else ""
                ),
                (
                    gia_tri_co_khong(getattr(record, "disability_certificate", None))
                    if record is not None
                    else ""
                ),
                (
                    gia_tri_co_khong(getattr(record, "inclusive_education", None))
                    if record is not None
                    else ""
                ),
                (
                    gia_tri_co_khong(getattr(record, "disability_support", None))
                    if record is not None
                    else ""
                ),
                (
                    getattr(record, "disability_support_details", None) or ""
                    if record is not None
                    else ""
                ),
                (
                    gia_tri_co_khong(
                        record.completed_preschool_5
                    )
                    if record is not None
                    else ""
                ),
                (
                    gia_tri_co_khong(
                        record.attends_required_days
                    )
                    if record is not None
                    else ""
                ),
                (
                    gia_tri_co_khong(
                        record.attends_regularly
                    )
                    if record is not None
                    else ""
                ),
                (
                    gia_tri_co_khong(
                        record.prepared_vietnamese
                    )
                    if record is not None
                    else ""
                ),
                (
                    gia_tri_co_khong(record.weight_monitored)
                    if record is not None
                    else ""
                ),
                (
                    gia_tri_co_khong(record.underweight)
                    if record is not None
                    else ""
                ),
                (
                    gia_tri_co_khong(record.height_monitored)
                    if record is not None
                    else ""
                ),
                (
                    gia_tri_co_khong(record.stunted)
                    if record is not None
                    else ""
                ),
                (
                    (
                        record.special_circumstances
                        if record is not None
                        and record.special_circumstances
                        else person.special_circumstances or ""
                    )
                    if person is not None
                    else ""
                ),
                person.notes or "" if person is not None else "",
                record.notes or "" if record is not None else "",
                survey_form.id,
                household.id,
                person.id if person is not None else "",
                batch.school_year_id,
                record.school_id if record is not None else "",
                record.class_id if record is not None else "",
                True if person is not None else "",
            ]

            for column_index, value in enumerate(values, start=1):
                cell = worksheet.cell(
                    row=row_number,
                    column=column_index,
                    value=value,
                )
                cell.border = border
                cell.alignment = Alignment(
                    vertical="top",
                    wrap_text=True,
                )

            worksheet.cell(
                row=row_number,
                column=11,
            ).number_format = "dd/mm/yyyy"

            row_number += 1
            sequence += 1

    last_data_row = max(header_row + 1, row_number - 1)

    worksheet.freeze_panes = f"A{header_row + 1}"
    worksheet.auto_filter.ref = (
        f"A{header_row}:"
        f"{get_column_letter(len(visible_headers))}{last_data_row}"
    )
    worksheet.row_dimensions[header_row].height = 42

    widths = {
        1: 7,
        2: 28,
        3: 22,
        4: 22,
        5: 24,
        6: 34,
        7: 19,
        8: 18,
        9: 18,
        10: 26,
        11: 14,
        12: 12,
        13: 14,
        14: 22,
        15: 24,
        16: 20,
        17: 20,
        18: 34,
        19: 34,
        20: 22,
        21: 32,
        22: 24,
        23: 24,
        24: 30,
        25: 25,
        26: 25,
        27: 18,
        28: 24,
        29: 40,
        30: 22,
        31: 24,
        32: 20,
        33: 23,
        34: 23,
        35: 24,
        36: 23,
        37: 23,
        38: 34,
        39: 34,
        40: 34,
    }

    for column_index, width in widths.items():
        worksheet.column_dimensions[
            get_column_letter(column_index)
        ].width = width

    technical_start = len(visible_headers) + 1
    for column_index in range(technical_start, last_column + 1):
        worksheet.column_dimensions[
            get_column_letter(column_index)
        ].hidden = True

    # Danh mục dùng cho các ô lựa chọn trong file điều tra.
    list_sheet = workbook.create_sheet("DANH_MUC")
    list_values = {
        1: ["Giới tính", "Nam", "Nữ", "Khác"],
        2: [
            "Trạng thái cư trú",
            *RESIDENCY_STATUS_LABELS.values(),
        ],
        3: [
            "Tình trạng học tập",
            *LEARNING_STATUS_LABELS.values(),
        ],
        4: ["Có/Không", "Có", "Không"],
        5: ["Tình trạng khuyết tật", *DISABILITY_STATUS_LABELS.values()],
        6: ["Dạng khuyết tật", *DISABILITY_TYPE_LABELS.values()],
        7: ["Mức độ khuyết tật", *DISABILITY_LEVEL_LABELS.values()],
    }

    for column_index, items in list_values.items():
        for item_index, value in enumerate(items, start=1):
            list_sheet.cell(
                row=item_index,
                column=column_index,
                value=value,
            )

    list_sheet.sheet_state = "hidden"

    validation_gender = DataValidation(
        type="list",
        formula1="'DANH_MUC'!$A$2:$A$4",
        allow_blank=True,
    )
    validation_residency = DataValidation(
        type="list",
        formula1=(
            f"'DANH_MUC'!$B$2:$B$"
            f"{len(RESIDENCY_STATUS_LABELS) + 1}"
        ),
        allow_blank=True,
    )
    validation_learning = DataValidation(
        type="list",
        formula1=(
            f"'DANH_MUC'!$C$2:$C$"
            f"{len(LEARNING_STATUS_LABELS) + 1}"
        ),
        allow_blank=True,
    )
    validation_boolean = DataValidation(
        type="list",
        formula1="'DANH_MUC'!$D$2:$D$3",
        allow_blank=True,
    )
    validation_disability_status = DataValidation(
        type="list",
        formula1=(
            f"'DANH_MUC'!$E$2:$E${len(DISABILITY_STATUS_LABELS) + 1}"
        ),
        allow_blank=True,
    )
    validation_disability_type = DataValidation(
        type="list",
        formula1=(
            f"'DANH_MUC'!$F$2:$F${len(DISABILITY_TYPE_LABELS) + 1}"
        ),
        allow_blank=True,
    )
    validation_disability_level = DataValidation(
        type="list",
        formula1=(
            f"'DANH_MUC'!$G$2:$G${len(DISABILITY_LEVEL_LABELS) + 1}"
        ),
        allow_blank=True,
    )

    for validation in (
        validation_gender,
        validation_residency,
        validation_learning,
        validation_boolean,
        validation_disability_status,
        validation_disability_type,
        validation_disability_level,
    ):
        worksheet.add_data_validation(validation)

    validation_gender.add(f"L7:L5000")
    validation_residency.add(f"Q7:Q5000")
    validation_learning.add(f"T7:T5000")
    validation_disability_status.add("W7:W5000")
    validation_disability_type.add("X7:X5000")
    validation_disability_level.add("Y7:Y5000")
    for column_letter in (
        "Z", "AA", "AB", "AD", "AE", "AF", "AG", "AH", "AI", "AJ", "AK"
    ):
        validation_boolean.add(
            f"{column_letter}7:{column_letter}5000"
        )

    guide = workbook.create_sheet("HUONG_DAN", 0)
    guide["A1"] = "HƯỚNG DẪN SỬ DỤNG FILE ĐIỀU TRA"
    guide["A1"].font = Font(size=16, bold=True)
    guide["A3"] = "1. Mở sheet DIEU_TRA để rà soát và cập nhật dữ liệu."
    guide["A4"] = (
        "2. Không đổi tên sheet, không đổi tiêu đề cột và không xóa "
        "các cột kỹ thuật đang được ẩn."
    )
    guide["A5"] = (
        "3. Không sửa Số phiếu, Mã hộ và Mã đối tượng đã có."
    )
    guide["A6"] = (
        "4. Để bổ sung người mới vào hộ: sao chép một dòng của đúng hộ, "
        "giữ Số phiếu và Mã hộ, sau đó xóa Mã đối tượng và nhập thông tin mới."
    )
    guide["A7"] = (
        "5. Các cột Có/Không, giới tính, cư trú và tình trạng học tập "
        "đã có danh sách lựa chọn."
    )
    guide["A8"] = (
        "6. Sau khi điều tra xong, lưu nguyên định dạng .xlsx để sử dụng "
        "chức năng Nhập Excel cập nhật ở bài tiếp theo."
    )
    guide["A10"] = f"Mã đợt: {batch.code}"
    guide["A11"] = f"Năm học: {batch.school_year.code}"
    guide["A12"] = f"Xã/phường: {batch.commune.name}"
    guide.column_dimensions["A"].width = 115
    for row in range(1, 13):
        guide.cell(row=row, column=1).alignment = Alignment(
            wrap_text=True,
            vertical="top",
        )

    output = BytesIO()
    workbook.save(output)
    output.seek(0)

    file_name = (
        f"dieu_tra_{batch.commune.code}_"
        f"{batch.school_year.code.replace('-', '')}.xlsx"
    )

    return StreamingResponse(
        output,
        media_type=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
        headers={
            "Content-Disposition": (
                f'attachment; filename="{file_name}"'
            )
        },
    )


# =========================================================
# NHẬP EXCEL CẬP NHẬT
# =========================================================

EXCEL_IMPORT_REQUIRED_HEADERS = (
    "Số phiếu",
    "Mã hộ",
    "Thôn/xóm/khối/bản",
    "Chủ hộ",
    "Địa chỉ hộ",
    "Điện thoại chủ hộ",
    "Trạng thái phiếu",
    "Mã đối tượng",
    "Họ và tên",
    "Ngày sinh",
    "Giới tính",
    "Dân tộc",
    "Quan hệ với chủ hộ",
    "Số định danh cá nhân",
    "Mã Bộ GD&ĐT",
    "Trạng thái cư trú",
    "Địa chỉ thường trú",
    "Chỗ ở hiện nay",
    "Tình trạng học tập",
    "Tên trường",
    "Tên lớp",
    "Hoàn thành CT GDMN 5 tuổi",
    "Đi học đủ ngày theo quy định",
    "Đi học chuyên cần",
    "Được chuẩn bị tiếng Việt",
    "Theo dõi biểu đồ cân nặng",
    "Suy dinh dưỡng nhẹ cân",
    "Theo dõi biểu đồ chiều cao",
    "Suy dinh dưỡng thấp còi",
    "Hoàn cảnh đặc biệt",
    "Ghi chú đối tượng",
    "Ghi chú năm học",
    "__survey_form_id",
    "__household_id",
    "__survey_person_id",
    "__school_year_id",
    "__school_id",
    "__class_id",
)


def gia_tri_excel_dang_chu(value: Any) -> str:
    """Đọc ô Excel thành văn bản, không tạo đuôi .0 ngoài ý muốn."""

    if value is None:
        return ""
    if isinstance(value, bool):
        return "Có" if value else "Không"
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def khoa_so_sanh_excel(value: Any) -> str:
    """Khóa so sánh không phân biệt dấu, hoa thường và khoảng trắng."""

    text = gia_tri_excel_dang_chu(value)
    text = unicodedata.normalize("NFD", text)
    text = "".join(
        char
        for char in text
        if unicodedata.category(char) != "Mn"
    )
    return " ".join(text.lower().strip().split())


def so_nguyen_excel(value: Any) -> int | None:
    """Đọc ID kỹ thuật từ Excel."""

    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    text = str(value).strip()
    return int(text) if text.isdigit() else None


def ngay_excel(value: Any) -> date | None:
    """Đọc ngày Excel hoặc chuỗi ngày thông dụng."""

    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value

    text = str(value).strip()
    for format_code in (
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%Y-%m-%d",
        "%d.%m.%Y",
    ):
        try:
            return datetime.strptime(text, format_code).date()
        except ValueError:
            continue
    return None


def co_khong_excel(value: Any) -> tuple[bool | None, bool]:
    """Trả về (giá trị, hợp lệ). Ô trống tương ứng None."""

    if value in (None, ""):
        return None, True
    if isinstance(value, bool):
        return value, True
    key = khoa_so_sanh_excel(value)
    if key in {"co", "yes", "true", "1", "x"}:
        return True, True
    if key in {"khong", "no", "false", "0"}:
        return False, True
    return None, False


def tao_ban_sao_truoc_khi_nhap_excel() -> Path:
    """Tạo bản sao SQLite trước khi nhập dữ liệu."""

    database_path = Path(DATABASE_PATH)
    backup_dir = database_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"before_excel_import_{timestamp}.db"

    source = sqlite3.connect(str(database_path))
    target = sqlite3.connect(str(backup_path))
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()
    return backup_path


def hien_thi_nhap_excel(
    *,
    request: Request,
    batch: SurveyBatch,
    errors: list[dict[str, Any]] | None = None,
    summary: dict[str, Any] | None = None,
    file_name: str = "",
    status_code: int = 200,
):
    return templates.TemplateResponse(
        request=request,
        name="surveys/excel_import.html",
        context={
            "nguoi_dung": request.scope.get("auth_user"),
            "batch": batch,
            "errors": errors or [],
            "summary": summary,
            "file_name": file_name,
        },
        status_code=status_code,
    )


@router.get(
    "/{batch_id}/ho-dan/nhap-excel",
    response_class=HTMLResponse,
)
def trang_nhap_excel(
    batch_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    from app.household_excel_exchange import import_household_excel_page

    return import_household_excel_page(
        batch_id=batch_id,
        request=request,
        db=db,
    )

    batch = lay_dot_dieu_tra(db, batch_id)
    if batch is None:
        return RedirectResponse(url="/dieu-tra", status_code=303)
    return hien_thi_nhap_excel(request=request, batch=batch)


@router.post(
    "/{batch_id}/ho-dan/nhap-excel",
    response_class=HTMLResponse,
)
async def nhap_excel_cap_nhat(
    batch_id: int,
    request: Request,
    excel_file: UploadFile | None = File(None),
    confirm_token: str = Form(""),
    db: Session = Depends(get_db),
):
    """Xem trước thay đổi rồi mới xác nhận cập nhật phiếu Excel theo hộ."""

    from app.household_excel_exchange import import_household_excel_post

    return await import_household_excel_post(
        batch_id=batch_id,
        request=request,
        excel_file=excel_file,
        confirm_token=confirm_token,
        db=db,
    )

    batch = lay_dot_dieu_tra(db, batch_id)
    if batch is None:
        return RedirectResponse(url="/dieu-tra", status_code=303)

    if batch.status == "DA_KET_THUC":
        return hien_thi_nhap_excel(
            request=request,
            batch=batch,
            errors=[{
                "row": "—",
                "message": "Đợt điều tra đã kết thúc, không thể nhập Excel.",
            }],
            file_name=excel_file.filename or "",
            status_code=400,
        )

    file_name = excel_file.filename or ""
    if not file_name.lower().endswith(".xlsx"):
        return hien_thi_nhap_excel(
            request=request,
            batch=batch,
            errors=[{
                "row": "—",
                "message": "Chỉ chấp nhận file Excel định dạng .xlsx.",
            }],
            file_name=file_name,
            status_code=400,
        )

    content = await excel_file.read()
    if not content:
        return hien_thi_nhap_excel(
            request=request,
            batch=batch,
            errors=[{"row": "—", "message": "File tải lên đang trống."}],
            file_name=file_name,
            status_code=400,
        )
    if len(content) > 15 * 1024 * 1024:
        return hien_thi_nhap_excel(
            request=request,
            batch=batch,
            errors=[{
                "row": "—",
                "message": "File lớn quá 15 MB. Hãy kiểm tra lại file điều tra.",
            }],
            file_name=file_name,
            status_code=400,
        )

    try:
        workbook = load_workbook(BytesIO(content), data_only=True)
    except Exception:
        return hien_thi_nhap_excel(
            request=request,
            batch=batch,
            errors=[{
                "row": "—",
                "message": "Không đọc được file Excel. File có thể bị hỏng hoặc sai định dạng.",
            }],
            file_name=file_name,
            status_code=400,
        )

    if "DIEU_TRA" not in workbook.sheetnames:
        return hien_thi_nhap_excel(
            request=request,
            batch=batch,
            errors=[{
                "row": "—",
                "message": "Không tìm thấy sheet DIEU_TRA. Không đổi tên sheet của file xuất từ phần mềm.",
            }],
            file_name=file_name,
            status_code=400,
        )

    worksheet = workbook["DIEU_TRA"]
    header_row = 6
    header_map: dict[str, int] = {}
    for column_index in range(1, worksheet.max_column + 1):
        header = gia_tri_excel_dang_chu(
            worksheet.cell(row=header_row, column=column_index).value
        )
        if header:
            header_map[header] = column_index

    missing_headers = [
        header
        for header in EXCEL_IMPORT_REQUIRED_HEADERS
        if header not in header_map
    ]
    if missing_headers:
        return hien_thi_nhap_excel(
            request=request,
            batch=batch,
            errors=[{
                "row": "6",
                "message": (
                    "Thiếu hoặc đã đổi tên các cột: "
                    + ", ".join(missing_headers)
                ),
            }],
            file_name=file_name,
            status_code=400,
        )

    def cell_value(row_number: int, header: str) -> Any:
        return worksheet.cell(
            row=row_number,
            column=header_map[header],
        ).value

    residency_reverse = {
        khoa_so_sanh_excel(label): code
        for code, label in RESIDENCY_STATUS_LABELS.items()
    }
    learning_reverse = {
        khoa_so_sanh_excel(label): code
        for code, label in LEARNING_STATUS_LABELS.items()
    }
    form_status_reverse = {
        khoa_so_sanh_excel(label): code
        for code, label in FORM_STATUS_LABELS.items()
    }
    disability_status_reverse = {
        khoa_so_sanh_excel(label): code
        for code, label in DISABILITY_STATUS_LABELS.items()
    }
    disability_type_reverse = {
        khoa_so_sanh_excel(label): code
        for code, label in DISABILITY_TYPE_LABELS.items()
    }
    disability_level_reverse = {
        khoa_so_sanh_excel(label): code
        for code, label in DISABILITY_LEVEL_LABELS.items()
    }

    def optional_cell_value(row_number: int, header: str) -> Any:
        column_index = header_map.get(header)
        if column_index is None:
            return None
        return worksheet.cell(row=row_number, column=column_index).value

    has_disability_columns = "Tình trạng khuyết tật" in header_map

    survey_forms = {
        item.id: item
        for item in db.scalars(
            select(SurveyForm)
            .options(selectinload(SurveyForm.household))
            .where(SurveyForm.survey_batch_id == batch.id)
        ).all()
    }
    household_ids = {item.household_id for item in survey_forms.values()}
    households = {
        item.id: item
        for item in db.scalars(
            select(Household).where(Household.id.in_(household_ids))
        ).all()
    } if household_ids else {}

    existing_people = {
        item.id: item
        for item in db.scalars(
            select(SurveyPerson).where(
                SurveyPerson.household_id.in_(household_ids)
            )
        ).all()
    } if household_ids else {}

    errors: list[dict[str, Any]] = []
    actions: list[dict[str, Any]] = []
    household_values: dict[int, tuple[str, ...]] = {}
    seen_existing_person_ids: dict[int, int] = {}
    seen_personal_ids: dict[str, int] = {}
    seen_ministry_codes: dict[str, int] = {}
    seen_name_birth: dict[tuple[int, str, date], int] = {}

    for row_number in range(header_row + 1, worksheet.max_row + 1):
        form_id = so_nguyen_excel(cell_value(row_number, "__survey_form_id"))
        household_id = so_nguyen_excel(cell_value(row_number, "__household_id"))
        school_year_id = so_nguyen_excel(cell_value(row_number, "__school_year_id"))
        visible_person_code = chuan_hoa_ma(
            gia_tri_excel_dang_chu(cell_value(row_number, "Mã đối tượng"))
        )
        technical_person_id = so_nguyen_excel(
            cell_value(row_number, "__survey_person_id")
        )

        visible_values = [
            cell_value(row_number, header)
            for header in EXCEL_IMPORT_REQUIRED_HEADERS[:33]
        ]
        if not any(value not in (None, "") for value in visible_values) and not form_id:
            continue

        row_errors: list[str] = []
        survey_form = survey_forms.get(form_id) if form_id else None
        household = households.get(household_id) if household_id else None

        if survey_form is None:
            row_errors.append("ID phiếu kỹ thuật không thuộc đợt điều tra này.")
        if household is None:
            row_errors.append("ID hộ kỹ thuật không thuộc đợt điều tra này.")
        if survey_form is not None and survey_form.household_id != household_id:
            row_errors.append("ID phiếu và ID hộ không khớp nhau.")
        if school_year_id != batch.school_year_id:
            row_errors.append("ID năm học không đúng với đợt điều tra.")

        if survey_form is not None:
            if chuan_hoa_ma(gia_tri_excel_dang_chu(
                cell_value(row_number, "Số phiếu")
            )) != chuan_hoa_ma(survey_form.form_number):
                row_errors.append("Số phiếu đã bị thay đổi.")
        if household is not None:
            if chuan_hoa_ma(gia_tri_excel_dang_chu(
                cell_value(row_number, "Mã hộ")
            )) != chuan_hoa_ma(household.code):
                row_errors.append("Mã hộ đã bị thay đổi.")

        hamlet_name = chuan_hoa_van_ban(gia_tri_excel_dang_chu(
            cell_value(row_number, "Thôn/xóm/khối/bản")
        ))
        head_name = chuan_hoa_van_ban(gia_tri_excel_dang_chu(
            cell_value(row_number, "Chủ hộ")
        ))
        address = chuan_hoa_van_ban(gia_tri_excel_dang_chu(
            cell_value(row_number, "Địa chỉ hộ")
        ))
        phone = chuan_hoa_so_dien_thoai(gia_tri_excel_dang_chu(
            cell_value(row_number, "Điện thoại chủ hộ")
        )) or ""
        form_status_key = khoa_so_sanh_excel(
            cell_value(row_number, "Trạng thái phiếu")
        )
        form_status = form_status_reverse.get(form_status_key)
        if not head_name:
            row_errors.append("Chủ hộ không được để trống.")
        if not address:
            row_errors.append("Địa chỉ hộ không được để trống.")
        if form_status is None:
            row_errors.append("Trạng thái phiếu không hợp lệ.")

        household_tuple = (
            hamlet_name,
            head_name,
            address,
            phone,
            form_status or "",
        )
        if household_id is not None:
            previous_household_tuple = household_values.get(household_id)
            if previous_household_tuple is None:
                household_values[household_id] = household_tuple
            elif previous_household_tuple != household_tuple:
                row_errors.append(
                    "Thông tin hộ không thống nhất giữa các dòng của cùng một hộ. "
                    "Hãy sao chép cùng thông tin chủ hộ, địa chỉ, điện thoại và trạng thái phiếu cho mọi dòng."
                )

        full_name = chuan_hoa_van_ban(gia_tri_excel_dang_chu(
            cell_value(row_number, "Họ và tên")
        ))
        birth_date = ngay_excel(cell_value(row_number, "Ngày sinh"))
        gender = chuan_hoa_van_ban(gia_tri_excel_dang_chu(
            cell_value(row_number, "Giới tính")
        ))
        ethnic_group = chuan_hoa_van_ban(gia_tri_excel_dang_chu(
            cell_value(row_number, "Dân tộc")
        ))
        relationship = chuan_hoa_van_ban(gia_tri_excel_dang_chu(
            cell_value(row_number, "Quan hệ với chủ hộ")
        ))
        personal_id = chuan_hoa_ma(gia_tri_excel_dang_chu(
            cell_value(row_number, "Số định danh cá nhân")
        ))
        ministry_code = chuan_hoa_ma(gia_tri_excel_dang_chu(
            cell_value(row_number, "Mã Bộ GD&ĐT")
        ))
        residency_key = khoa_so_sanh_excel(
            cell_value(row_number, "Trạng thái cư trú")
        )
        residency_status = residency_reverse.get(residency_key)
        permanent_address = chuan_hoa_van_ban(gia_tri_excel_dang_chu(
            cell_value(row_number, "Địa chỉ thường trú")
        ))
        current_address = chuan_hoa_van_ban(gia_tri_excel_dang_chu(
            cell_value(row_number, "Chỗ ở hiện nay")
        ))
        special_circumstances = gia_tri_excel_dang_chu(
            cell_value(row_number, "Hoàn cảnh đặc biệt")
        ).strip()
        person_notes = gia_tri_excel_dang_chu(
            cell_value(row_number, "Ghi chú đối tượng")
        ).strip()

        has_person_data = any((
            visible_person_code,
            full_name,
            birth_date,
            gender,
            ethnic_group,
            relationship,
            personal_id,
            ministry_code,
        ))

        person: SurveyPerson | None = None
        is_new_person = False
        # Xóa Mã đối tượng trên dòng sao chép nghĩa là thêm người mới,
        # dù ID kỹ thuật ẩn vẫn còn do Excel sao chép cả dòng.
        if visible_person_code:
            if technical_person_id is None:
                row_errors.append("Đối tượng đã có mã nhưng thiếu ID kỹ thuật.")
            else:
                person = existing_people.get(technical_person_id)
                if person is None or person.household_id != household_id:
                    row_errors.append("Đối tượng kỹ thuật không thuộc đúng hộ.")
                elif not person.is_active:
                    row_errors.append("Đối tượng này đã ngừng theo dõi.")
                elif chuan_hoa_ma(person.code) != visible_person_code:
                    row_errors.append("Mã đối tượng không khớp ID kỹ thuật.")
                elif technical_person_id in seen_existing_person_ids:
                    row_errors.append(
                        f"Đối tượng bị lặp lại; đã xuất hiện ở dòng {seen_existing_person_ids[technical_person_id]}."
                    )
                else:
                    seen_existing_person_ids[technical_person_id] = row_number
        elif has_person_data:
            is_new_person = True
            technical_person_id = None

        if person is not None or is_new_person:
            if not full_name:
                row_errors.append("Họ và tên đối tượng không được để trống.")
            if birth_date is None:
                row_errors.append("Ngày sinh không hợp lệ hoặc đang để trống.")
            elif birth_date > date.today():
                row_errors.append("Ngày sinh không được lớn hơn ngày hiện tại.")
            if gender not in {"Nam", "Nữ", "Khác"}:
                row_errors.append("Giới tính phải là Nam, Nữ hoặc Khác.")
            if not ethnic_group:
                row_errors.append("Dân tộc không được để trống.")
            if not relationship:
                row_errors.append("Quan hệ với chủ hộ không được để trống.")
            if residency_status is None:
                row_errors.append("Trạng thái cư trú không hợp lệ.")

            if personal_id:
                previous_row = seen_personal_ids.get(personal_id)
                if previous_row is not None:
                    row_errors.append(
                        f"Số định danh bị trùng với dòng {previous_row}."
                    )
                else:
                    seen_personal_ids[personal_id] = row_number
                duplicate = db.scalar(
                    select(SurveyPerson).where(
                        SurveyPerson.personal_id == personal_id,
                        SurveyPerson.is_active.is_(True),
                        SurveyPerson.id != (person.id if person else -1),
                    )
                )
                if duplicate is not None:
                    row_errors.append("Số định danh đã được dùng cho đối tượng khác.")

            if ministry_code:
                previous_row = seen_ministry_codes.get(ministry_code)
                if previous_row is not None:
                    row_errors.append(
                        f"Mã Bộ GD&ĐT bị trùng với dòng {previous_row}."
                    )
                else:
                    seen_ministry_codes[ministry_code] = row_number
                duplicate = db.scalar(
                    select(SurveyPerson).where(
                        SurveyPerson.ministry_student_code == ministry_code,
                        SurveyPerson.is_active.is_(True),
                        SurveyPerson.id != (person.id if person else -1),
                    )
                )
                if duplicate is not None:
                    row_errors.append("Mã Bộ GD&ĐT đã được dùng cho đối tượng khác.")

            if household_id is not None and full_name and birth_date:
                name_birth_key = (
                    household_id,
                    full_name.lower(),
                    birth_date,
                )
                previous_row = seen_name_birth.get(name_birth_key)
                if previous_row is not None:
                    row_errors.append(
                        f"Họ tên và ngày sinh bị trùng với dòng {previous_row}."
                    )
                else:
                    seen_name_birth[name_birth_key] = row_number
                duplicate = db.scalar(
                    select(SurveyPerson).where(
                        SurveyPerson.household_id == household_id,
                        func.lower(SurveyPerson.full_name) == full_name.lower(),
                        SurveyPerson.date_of_birth == birth_date,
                        SurveyPerson.is_active.is_(True),
                        SurveyPerson.id != (person.id if person else -1),
                    )
                )
                if duplicate is not None:
                    row_errors.append("Người cùng họ tên và ngày sinh đã tồn tại trong hộ.")

        learning_key = khoa_so_sanh_excel(
            cell_value(row_number, "Tình trạng học tập")
        )
        learning_status = learning_reverse.get(learning_key) if learning_key else None
        school_name = chuan_hoa_van_ban(gia_tri_excel_dang_chu(
            cell_value(row_number, "Tên trường")
        ))
        class_name = chuan_hoa_van_ban(gia_tri_excel_dang_chu(
            cell_value(row_number, "Tên lớp")
        ))
        year_notes = gia_tri_excel_dang_chu(
            cell_value(row_number, "Ghi chú năm học")
        ).strip()

        disability_status_key = khoa_so_sanh_excel(
            optional_cell_value(row_number, "Tình trạng khuyết tật")
        )
        disability_status_value = (
            disability_status_reverse.get(disability_status_key)
            if disability_status_key
            else "CHUA_XAC_DINH"
        )
        disability_type_key = khoa_so_sanh_excel(
            optional_cell_value(row_number, "Dạng khuyết tật")
        )
        disability_type_value = (
            disability_type_reverse.get(disability_type_key)
            if disability_type_key
            else None
        )
        disability_level_key = khoa_so_sanh_excel(
            optional_cell_value(row_number, "Mức độ khuyết tật")
        )
        disability_level_value = (
            disability_level_reverse.get(disability_level_key)
            if disability_level_key
            else None
        )
        disability_certificate_value, disability_certificate_valid = co_khong_excel(
            optional_cell_value(row_number, "Có giấy xác nhận khuyết tật")
        )
        inclusive_education_value, inclusive_education_valid = co_khong_excel(
            optional_cell_value(row_number, "Học hòa nhập")
        )
        disability_support_value, disability_support_valid = co_khong_excel(
            optional_cell_value(row_number, "Được hỗ trợ khuyết tật")
        )
        disability_support_details_value = gia_tri_excel_dang_chu(
            optional_cell_value(row_number, "Nội dung hỗ trợ khuyết tật")
        ).strip()

        if disability_status_key and disability_status_value is None:
            row_errors.append("Tình trạng khuyết tật không hợp lệ.")
        if disability_type_key and disability_type_value is None:
            row_errors.append("Dạng khuyết tật không hợp lệ.")
        if disability_level_key and disability_level_value is None:
            row_errors.append("Mức độ khuyết tật không hợp lệ.")
        if not disability_certificate_valid:
            row_errors.append("Cột Có giấy xác nhận khuyết tật chỉ được nhập Có, Không hoặc để trống.")
        if not inclusive_education_valid:
            row_errors.append("Cột Học hòa nhập chỉ được nhập Có, Không hoặc để trống.")
        if not disability_support_valid:
            row_errors.append("Cột Được hỗ trợ khuyết tật chỉ được nhập Có, Không hoặc để trống.")
        if disability_status_value == "CO_KHUYET_TAT":
            if not disability_type_value:
                row_errors.append("Trẻ có khuyết tật cần chọn dạng khuyết tật.")
            if not disability_level_value:
                row_errors.append("Trẻ có khuyết tật cần chọn mức độ khuyết tật.")
        else:
            disability_type_value = None
            disability_level_value = None
            disability_certificate_value = None
            inclusive_education_value = None
            disability_support_value = None
            disability_support_details_value = ""

        boolean_headers = (
            ("completed_preschool_5", "Hoàn thành CT GDMN 5 tuổi"),
            ("attends_required_days", "Đi học đủ ngày theo quy định"),
            ("attends_regularly", "Đi học chuyên cần"),
            ("prepared_vietnamese", "Được chuẩn bị tiếng Việt"),
            ("weight_monitored", "Theo dõi biểu đồ cân nặng"),
            ("underweight", "Suy dinh dưỡng nhẹ cân"),
            ("height_monitored", "Theo dõi biểu đồ chiều cao"),
            ("stunted", "Suy dinh dưỡng thấp còi"),
        )
        boolean_values: dict[str, bool | None] = {}
        for field_name, header in boolean_headers:
            parsed_value, valid = co_khong_excel(cell_value(row_number, header))
            boolean_values[field_name] = parsed_value
            if not valid:
                row_errors.append(f"Cột {header} chỉ được nhập Có, Không hoặc để trống.")

        has_year_data = any((
            learning_key,
            school_name,
            class_name,
            special_circumstances,
            year_notes,
            disability_status_key,
            disability_type_key,
            disability_level_key,
            disability_certificate_value is not None,
            inclusive_education_value is not None,
            disability_support_value is not None,
            disability_support_details_value,
            *[value is not None for value in boolean_values.values()],
        ))
        if has_year_data and person is None and not is_new_person:
            row_errors.append("Có dữ liệu năm học nhưng dòng chưa có đối tượng.")
        if has_year_data and learning_status is None:
            row_errors.append("Tình trạng học tập không hợp lệ hoặc đang để trống.")
        if learning_status in {"DANG_HOC", "CHUYEN_DEN"} and not school_name:
            row_errors.append("Đối tượng đang học cần có tên trường.")

        if row_errors:
            errors.extend(
                {"row": row_number, "message": message}
                for message in row_errors
            )
            continue

        actions.append({
            "row": row_number,
            "survey_form": survey_form,
            "household": household,
            "household_values": household_tuple,
            "person": person,
            "is_new_person": is_new_person,
            "person_values": {
                "full_name": full_name,
                "date_of_birth": birth_date,
                "gender": gender,
                "ethnic_group": ethnic_group,
                "relationship_to_head": relationship,
                "personal_id": personal_id or None,
                "ministry_student_code": ministry_code or None,
                "permanent_address": permanent_address or None,
                "current_address": current_address or None,
                "residency_status": residency_status,
                "special_circumstances": special_circumstances or None,
                "notes": person_notes or None,
            },
            "has_person_data": person is not None or is_new_person,
            "has_year_data": has_year_data,
            "has_disability_columns": has_disability_columns,
            "year_values": {
                "learning_status": learning_status,
                "school_name": school_name,
                "class_name": class_name,
                "special_circumstances": special_circumstances or None,
                "notes": year_notes or None,
                "disability_status": disability_status_value or "CHUA_XAC_DINH",
                "disability_type": disability_type_value,
                "disability_level": disability_level_value,
                "disability_certificate": disability_certificate_value,
                "inclusive_education": inclusive_education_value,
                "disability_support": disability_support_value,
                "disability_support_details": disability_support_details_value or None,
                **boolean_values,
            },
            "technical_school_id": so_nguyen_excel(
                cell_value(row_number, "__school_id")
            ),
            "technical_class_id": so_nguyen_excel(
                cell_value(row_number, "__class_id")
            ),
        })

    if errors:
        db.rollback()
        return hien_thi_nhap_excel(
            request=request,
            batch=batch,
            errors=errors[:200],
            file_name=file_name,
            status_code=400,
        )

    if not actions:
        return hien_thi_nhap_excel(
            request=request,
            batch=batch,
            errors=[{
                "row": "—",
                "message": "Không tìm thấy dòng dữ liệu hợp lệ để cập nhật.",
            }],
            file_name=file_name,
            status_code=400,
        )

    backup_path = tao_ban_sao_truoc_khi_nhap_excel()
    updated_households: set[int] = set()
    updated_people = 0
    created_people = 0
    updated_year_records = 0
    created_year_records = 0

    try:
        for action in actions:
            survey_form = action["survey_form"]
            household = action["household"]
            hamlet_name, head_name, address, phone, form_status = action[
                "household_values"
            ]

            if household.id not in updated_households:
                household.hamlet_name = hamlet_name or None
                household.head_name = head_name
                household.address = address
                household.phone = phone or None
                household.is_active = True
                survey_form.head_name_snapshot = head_name
                survey_form.address_snapshot = address
                survey_form.hamlet_name_snapshot = hamlet_name or None
                survey_form.status = form_status
                updated_households.add(household.id)

            person = action["person"]
            if action["is_new_person"]:
                values = action["person_values"]
                student: Student | None = None
                inferred: list[Student] = []
                if values["ministry_student_code"]:
                    item = db.scalar(select(Student).where(
                        Student.code == values["ministry_student_code"]
                    ))
                    if item is not None:
                        inferred.append(item)
                if values["personal_id"]:
                    item = db.scalar(select(Student).where(
                        Student.personal_id == values["personal_id"]
                    ))
                    if item is not None and item not in inferred:
                        inferred.append(item)
                if len(inferred) == 1:
                    candidate = inferred[0]
                    existing_link = db.scalar(select(SurveyPerson).where(
                        SurveyPerson.student_id == candidate.id,
                        SurveyPerson.is_active.is_(True),
                    ))
                    if existing_link is None:
                        student = candidate

                person = SurveyPerson(
                    code=f"TMP-{uuid4().hex[:12]}",
                    household_id=household.id,
                    student_id=student.id if student is not None else None,
                    is_active=True,
                    **values,
                )
                db.add(person)
                db.flush()
                person.code = f"DT-{person.id:08d}"
                created_people += 1
                if survey_form.status == "CHUA_DIEU_TRA":
                    survey_form.status = "DANG_DIEU_TRA"
            elif action["has_person_data"]:
                for field_name, value in action["person_values"].items():
                    setattr(person, field_name, value)
                updated_people += 1

            if action["has_year_data"] and person is not None:
                year_values = action["year_values"]
                school: School | None = None
                classroom: Classroom | None = None
                school_name_key = khoa_so_sanh_excel(year_values["school_name"])
                class_name_key = khoa_so_sanh_excel(year_values["class_name"])

                technical_school_id = action["technical_school_id"]
                if technical_school_id:
                    candidate = db.get(School, technical_school_id)
                    if (
                        candidate is not None
                        and candidate.commune_id == batch.commune_id
                        and khoa_so_sanh_excel(candidate.name) == school_name_key
                    ):
                        school = candidate
                if school is None and school_name_key:
                    candidates = db.scalars(select(School).where(
                        School.commune_id == batch.commune_id,
                        School.is_active.is_(True),
                    )).all()
                    matches = [
                        item for item in candidates
                        if khoa_so_sanh_excel(item.name) == school_name_key
                    ]
                    if len(matches) == 1:
                        school = matches[0]

                technical_class_id = action["technical_class_id"]
                if school is not None and technical_class_id:
                    candidate = db.get(Classroom, technical_class_id)
                    if (
                        candidate is not None
                        and candidate.school_id == school.id
                        and candidate.school_year_id == batch.school_year_id
                        and khoa_so_sanh_excel(candidate.name) == class_name_key
                    ):
                        classroom = candidate
                if school is not None and classroom is None and class_name_key:
                    candidates = db.scalars(select(Classroom).where(
                        Classroom.school_id == school.id,
                        Classroom.school_year_id == batch.school_year_id,
                    )).all()
                    matches = [
                        item for item in candidates
                        if khoa_so_sanh_excel(item.name) == class_name_key
                    ]
                    if len(matches) == 1:
                        classroom = matches[0]

                record = db.scalar(select(SurveyPersonYearRecord).where(
                    SurveyPersonYearRecord.survey_person_id == person.id,
                    SurveyPersonYearRecord.school_year_id == batch.school_year_id,
                ))
                if record is None:
                    record = SurveyPersonYearRecord(
                        survey_form_id=survey_form.id,
                        survey_person_id=person.id,
                        school_year_id=batch.school_year_id,
                        learning_status=year_values["learning_status"],
                    )
                    db.add(record)
                    created_year_records += 1
                else:
                    updated_year_records += 1

                record.survey_form_id = survey_form.id
                record.school_id = school.id if school is not None else None
                record.class_id = classroom.id if classroom is not None else None
                record.school_name_reported = year_values["school_name"] or None
                record.class_name_reported = year_values["class_name"] or None
                record.learning_status = year_values["learning_status"]
                record.special_circumstances = year_values[
                    "special_circumstances"
                ]
                record.notes = year_values["notes"]
                if action["has_disability_columns"]:
                    record.disability_status = year_values["disability_status"]
                    record.disability_type = year_values["disability_type"]
                    record.disability_level = year_values["disability_level"]
                    record.disability_certificate = year_values["disability_certificate"]
                    record.inclusive_education = year_values["inclusive_education"]
                    record.disability_support = year_values["disability_support"]
                    record.disability_support_details = year_values["disability_support_details"]
                record.is_reviewed = True
                for field_name in BOOLEAN_YEAR_FIELDS:
                    setattr(record, field_name, year_values[field_name])

        # Bài 12D-12: ghi nhận việc tiếp nhận file thành công trong cùng
        # giao dịch với dữ liệu cập nhật. Nếu nhật ký không ghi được thì
        # toàn bộ thao tác nhập cũng được hoàn tác để tránh trạng thái lệch.
        actor = lay_thong_tin_nguoi_dung(request)
        db.add(
            SurveyFileExchangeLog(
                school_year_id=batch.school_year_id,
                survey_batch_id=batch.id,
                commune_id=batch.commune_id,
                action="NHAP_EXCEL",
                status="THANH_CONG",
                file_name=file_name,
                actor_user_id=actor.get("id"),
                actor_name_snapshot=actor.get("full_name"),
                actor_role_snapshot=(
                    actor.get("role_name") or actor.get("role_code")
                ),
                form_total=len(updated_households),
                person_total=updated_people + created_people,
                updated_household_total=len(updated_households),
                updated_person_total=updated_people,
                created_person_total=created_people,
                updated_year_record_total=updated_year_records,
                created_year_record_total=created_year_records,
                notes=(
                    "Tiếp nhận Excel cập nhật thành công. "
                    f"Bản sao an toàn: {backup_path}"
                ),
            )
        )

        db.commit()
    except Exception as exc:
        db.rollback()
        return hien_thi_nhap_excel(
            request=request,
            batch=batch,
            errors=[{
                "row": "—",
                "message": (
                    "Không thể hoàn tất cập nhật. Dữ liệu chưa được thay đổi. "
                    f"Chi tiết kỹ thuật: {type(exc).__name__}."
                ),
            }],
            file_name=file_name,
            status_code=500,
        )

    return hien_thi_nhap_excel(
        request=request,
        batch=batch,
        file_name=file_name,
        summary={
            "updated_households": len(updated_households),
            "updated_people": updated_people,
            "created_people": created_people,
            "updated_year_records": updated_year_records,
            "created_year_records": created_year_records,
            "backup_path": str(backup_path),
        },
    )


@router.post("/{batch_id}/ho-dan/them")
def them_ho_dan(
    batch_id: int,
    request: Request,
    head_name: Annotated[str, Form()],
    address: Annotated[str, Form()],
    hamlet_name: Annotated[str, Form()] = "",
    phone: Annotated[str, Form()] = "",
    notes: Annotated[str, Form()] = "",
    db: Session = Depends(get_db),
):
    batch = lay_dot_dieu_tra(db, batch_id)

    if batch is None:
        return RedirectResponse(
            url="/dieu-tra",
            status_code=303,
        )

    head_name = chuan_hoa_van_ban(head_name)
    address = chuan_hoa_van_ban(address)
    hamlet_name = chuan_hoa_van_ban(hamlet_name)
    phone_value = chuan_hoa_so_dien_thoai(phone)
    notes = notes.strip()

    errors: list[str] = []

    if batch.status == "DA_KET_THUC":
        errors.append(
            "Đợt điều tra đã kết thúc, không thể thêm hộ."
        )

    if not head_name:
        errors.append(
            "Họ và tên chủ hộ không được để trống."
        )

    if len(head_name) > 200:
        errors.append(
            "Họ và tên chủ hộ dài quá 200 ký tự."
        )

    if not address:
        errors.append(
            "Địa chỉ hộ gia đình không được để trống."
        )

    if len(hamlet_name) > 200:
        errors.append(
            "Tên thôn/xóm dài quá 200 ký tự."
        )

    if phone_value and len(phone_value) > 30:
        errors.append(
            "Số điện thoại dài quá 30 ký tự."
        )

    form_data: dict[str, Any] = {
        "head_name": head_name,
        "address": address,
        "hamlet_name": hamlet_name,
        "phone": phone,
        "notes": notes,
    }

    existing_household = db.scalar(
        select(Household).where(
            Household.commune_id == batch.commune_id,
            Household.head_name == head_name,
            Household.address == address,
        )
    )

    if existing_household is not None:
        existing_form = db.scalar(
            select(SurveyForm).where(
                SurveyForm.survey_batch_id == batch.id,
                SurveyForm.household_id == existing_household.id,
            )
        )

        if existing_form is not None:
            errors.append(
                "Hộ gia đình này đã có phiếu "
                "trong đợt điều tra hiện tại."
            )

    if errors:
        # Hiển thị lại danh sách trang đầu để người dùng sửa dữ liệu.
        survey_forms = db.scalars(
            select(SurveyForm)
            .options(
                selectinload(SurveyForm.household)
                .selectinload(Household.people),
                selectinload(SurveyForm.investigators),
                with_loader_criteria(
                    SurveyPerson,
                    SurveyPerson.is_active.is_(True),
                    include_aliases=True,
                ),
            )
            .where(
                SurveyForm.survey_batch_id == batch.id
            )
            .order_by(SurveyForm.id.asc())
            .limit(HOUSEHOLD_PAGE_SIZE)
        ).all()

        hamlet_names = db.scalars(
            select(Household.hamlet_name)
            .join(
                SurveyForm,
                SurveyForm.household_id == Household.id,
            )
            .where(
                SurveyForm.survey_batch_id == batch.id,
                Household.hamlet_name.is_not(None),
                Household.hamlet_name != "",
            )
            .distinct()
            .order_by(Household.hamlet_name.asc())
        ).all()

        total_records = db.scalar(
            select(func.count(SurveyForm.id)).where(
                SurveyForm.survey_batch_id == batch.id
            )
        )

        status_rows = db.execute(
            select(
                SurveyForm.status,
                func.count(SurveyForm.id),
            )
            .where(SurveyForm.survey_batch_id == batch.id)
            .group_by(SurveyForm.status)
        ).all()
        status_counts = {code: 0 for code in FORM_STATUS_LABELS}
        for status_code, count_value in status_rows:
            status_counts[status_code] = int(count_value or 0)
        batch_total_records = sum(status_counts.values())
        progress_percent = (
            round(
                status_counts.get("DA_HOAN_THANH", 0)
                * 100
                / batch_total_records
            )
            if batch_total_records
            else 0
        )

        permissions = tao_thong_tin_quyen_giao_dien(request)

        return templates.TemplateResponse(
            request=request,
            name="surveys/households.html",
            context={
                "nguoi_dung": request.scope.get("auth_user"),
                "batch": batch,
                "survey_forms": survey_forms,
                "hamlet_names": hamlet_names,
                "q": "",
                "selected_hamlet": "",
                "selected_form_status": "",
                "status_counts": status_counts,
                "batch_total_records": batch_total_records,
                "progress_percent": progress_percent,
                "page": 1,
                "page_size": HOUSEHOLD_PAGE_SIZE,
                "total_records": int(total_records or 0),
                "total_pages": max(
                    1,
                    ceil(
                        int(total_records or 0)
                        / HOUSEHOLD_PAGE_SIZE
                    ),
                ),
                "page_links": [],
                "previous_url": None,
                "next_url": None,
                "form_status_labels": FORM_STATUS_LABELS,
                "thong_bao_loi": " ".join(errors),
                "form_data": form_data,
                **permissions,
            },
            status_code=400,
        )

    message_status = "household_created"

    try:
        if existing_household is None:
            household = Household(
                code=tao_ma_ho(
                    db=db,
                    commune=batch.commune,
                ),
                commune_id=batch.commune_id,
                head_name=head_name,
                hamlet_name=hamlet_name or None,
                address=address,
                phone=phone_value,
                notes=notes or None,
                is_active=True,
            )

            db.add(household)
            db.flush()
        else:
            household = existing_household
            message_status = "household_attached"

            if hamlet_name:
                household.hamlet_name = hamlet_name

            if phone_value:
                household.phone = phone_value

            if notes:
                household.notes = notes

            household.is_active = True

        survey_form = SurveyForm(
            survey_batch_id=batch.id,
            household_id=household.id,
            form_number=tao_so_phieu(
                db=db,
                batch=batch,
            ),
            head_name_snapshot=household.head_name,
            address_snapshot=household.address,
            hamlet_name_snapshot=household.hamlet_name,
            survey_date=None,
            status="CHUA_DIEU_TRA",
            village_head_name=None,
            household_representative_name=None,
            household_confirmed_at=None,
            commune_confirmed_at=None,
            notes=None,
        )

        db.add(survey_form)
        db.commit()

    except IntegrityError:
        db.rollback()

        return RedirectResponse(
            url=f"/dieu-tra/{batch.id}/ho-dan",
            status_code=303,
        )

    return RedirectResponse(
        url=(
            f"/dieu-tra/{batch.id}/ho-dan?"
            + urlencode({"status": message_status})
        ),
        status_code=303,
    )


# =========================================================
# QUẢN LÝ ĐỐI TƯỢNG TRONG HỘ GIA ĐÌNH
# =========================================================

@router.get(
    "/{batch_id}/ho-dan/{household_id}/doi-tuong",
    response_class=HTMLResponse,
)
def danh_sach_doi_tuong(
    batch_id: int,
    household_id: int,
    request: Request,
    q: str = "",
    residency_status: str = "",
    page: int = 1,
    status: str | None = None,
    db: Session = Depends(get_db),
):
    survey_form = lay_phieu_ho(
        db=db,
        batch_id=batch_id,
        household_id=household_id,
    )

    if survey_form is None:
        return RedirectResponse(
            url=f"/dieu-tra/{batch_id}/ho-dan",
            status_code=303,
        )

    return hien_thi_trang_doi_tuong(
        request=request,
        db=db,
        survey_form=survey_form,
        q=q,
        residency_status=residency_status,
        page=page,
        status=status,
    )


@router.post(
    "/{batch_id}/ho-dan/{household_id}/doi-tuong/them"
)
def them_doi_tuong(
    batch_id: int,
    household_id: int,
    request: Request,
    full_name: Annotated[str, Form()],
    student_id: Annotated[str, Form()] = "",
    date_of_birth: Annotated[str, Form()] = "",
    gender: Annotated[str, Form()] = "",
    ethnic_group: Annotated[str, Form()] = "",
    relationship_to_head: Annotated[str, Form()] = "",
    personal_id: Annotated[str, Form()] = "",
    citizen_id: Annotated[str, Form()] = "",
    ministry_student_code: Annotated[str, Form()] = "",
    permanent_address: Annotated[str, Form()] = "",
    current_address: Annotated[str, Form()] = "",
    residency_status: Annotated[str, Form()] = "THUONG_TRU",
    special_circumstances: Annotated[str, Form()] = "",
    notes: Annotated[str, Form()] = "",
    db: Session = Depends(get_db),
):
    survey_form = lay_phieu_ho(
        db=db,
        batch_id=batch_id,
        household_id=household_id,
    )

    if survey_form is None:
        return RedirectResponse(
            url=f"/dieu-tra/{batch_id}/ho-dan",
            status_code=303,
        )

    full_name = chuan_hoa_van_ban(full_name)
    gender = chuan_hoa_van_ban(gender)
    ethnic_group = chuan_hoa_van_ban(ethnic_group)
    relationship_to_head = chuan_hoa_van_ban(
        relationship_to_head
    )
    personal_id = chuan_hoa_ma(personal_id)
    citizen_id = chuan_hoa_ma(citizen_id)
    ministry_student_code = chuan_hoa_ma(
        ministry_student_code
    )
    permanent_address = chuan_hoa_van_ban(
        permanent_address
    )
    current_address = chuan_hoa_van_ban(
        current_address
    )
    special_circumstances = special_circumstances.strip()
    notes = notes.strip()

    form_data: dict[str, Any] = {
        "student_id": int(student_id) if student_id.isdigit() else None,
        "full_name": full_name,
        "date_of_birth": date_of_birth,
        "gender": gender,
        "ethnic_group": ethnic_group,
        "relationship_to_head": relationship_to_head,
        "personal_id": personal_id,
        "citizen_id": citizen_id,
        "ministry_student_code": ministry_student_code,
        "permanent_address": permanent_address,
        "current_address": current_address,
        "residency_status": residency_status,
        "special_circumstances": special_circumstances,
        "notes": notes,
    }

    errors: list[str] = []

    if survey_form.survey_batch.status == "DA_KET_THUC":
        errors.append(
            "Đợt điều tra đã kết thúc, không thể thêm đối tượng."
        )

    selected_student: Student | None = None

    if student_id.strip():
        if not student_id.isdigit():
            errors.append("Học sinh liên kết không hợp lệ.")
        else:
            selected_student = db.get(Student, int(student_id))

            if (
                selected_student is None
                or not selected_student.is_active
            ):
                errors.append(
                    "Không tìm thấy học sinh được chọn."
                )

    # Có thể tự tìm hồ sơ học sinh theo mã Bộ hoặc số định danh.
    inferred_students: list[Student] = []

    if ministry_student_code:
        item = db.scalar(
            select(Student).where(
                Student.code == ministry_student_code
            )
        )
        if item is not None:
            inferred_students.append(item)

    if personal_id:
        item = db.scalar(
            select(Student).where(
                Student.personal_id == personal_id
            )
        )
        if item is not None and item not in inferred_students:
            inferred_students.append(item)

    if selected_student is None and len(inferred_students) == 1:
        selected_student = inferred_students[0]
        form_data["student_id"] = selected_student.id

    if len(inferred_students) > 1:
        errors.append(
            "Mã Bộ và số định danh đang trỏ đến hai học sinh khác nhau."
        )

    if (
        selected_student is not None
        and any(
            item.id != selected_student.id
            for item in inferred_students
        )
    ):
        errors.append(
            "Học sinh được chọn không khớp với mã Bộ hoặc số định danh đã nhập."
        )

    if selected_student is not None:
        existing_link = db.scalar(
            select(SurveyPerson).where(
                SurveyPerson.student_id == selected_student.id,
                SurveyPerson.is_active.is_(True),
            )
        )

        if existing_link is not None:
            errors.append(
                "Học sinh này đã được liên kết với một đối tượng điều tra khác."
            )

        if not full_name:
            full_name = selected_student.full_name
            form_data["full_name"] = full_name

        if not date_of_birth and selected_student.date_of_birth:
            date_of_birth = selected_student.date_of_birth.isoformat()
            form_data["date_of_birth"] = date_of_birth

        if not gender and selected_student.gender:
            gender = selected_student.gender
            form_data["gender"] = gender

        if not ethnic_group and selected_student.ethnic_group:
            ethnic_group = selected_student.ethnic_group
            form_data["ethnic_group"] = ethnic_group

        if not personal_id and selected_student.personal_id:
            personal_id = selected_student.personal_id
            form_data["personal_id"] = personal_id

        if not ministry_student_code and selected_student.code:
            ministry_student_code = selected_student.code
            form_data["ministry_student_code"] = (
                ministry_student_code
            )

        if not permanent_address and selected_student.permanent_address:
            permanent_address = selected_student.permanent_address
            form_data["permanent_address"] = permanent_address

        if not current_address and selected_student.current_address:
            current_address = selected_student.current_address
            form_data["current_address"] = current_address

    if not full_name:
        errors.append("Họ và tên đối tượng không được để trống.")

    if len(full_name) > 200:
        errors.append("Họ và tên dài quá 200 ký tự.")

    parsed_birth_date, birth_error = chuyen_ngay(
        date_of_birth,
        "Ngày sinh",
        bat_buoc=True,
    )

    if birth_error:
        errors.append(birth_error)

    if parsed_birth_date and parsed_birth_date > date.today():
        errors.append(
            "Ngày sinh không được lớn hơn ngày hiện tại."
        )

    if not gender:
        errors.append("Giới tính không được để trống.")
    elif gender not in {"Nam", "Nữ", "Khác"}:
        errors.append("Giới tính không hợp lệ.")

    if not ethnic_group:
        errors.append("Dân tộc không được để trống.")

    if not relationship_to_head:
        errors.append(
            "Quan hệ với chủ hộ không được để trống."
        )

    if residency_status not in RESIDENCY_STATUS_LABELS:
        errors.append("Trạng thái cư trú không hợp lệ.")

    if len(personal_id) > 50:
        errors.append("Số định danh dài quá 50 ký tự.")
    if len(citizen_id) > 50:
        errors.append("Căn cước công dân dài quá 50 ký tự.")

    if len(ministry_student_code) > 50:
        errors.append("Mã Bộ GD&ĐT dài quá 50 ký tự.")

    if personal_id:
        duplicate_personal_id = db.scalar(
            select(SurveyPerson).where(
                SurveyPerson.personal_id == personal_id,
                SurveyPerson.is_active.is_(True),
            )
        )
        if duplicate_personal_id is not None:
            errors.append(
                "Số định danh cá nhân đã được sử dụng cho đối tượng khác."
            )

    if ministry_student_code:
        duplicate_ministry_code = db.scalar(
            select(SurveyPerson).where(
                SurveyPerson.ministry_student_code
                == ministry_student_code,
                SurveyPerson.is_active.is_(True),
            )
        )
        if duplicate_ministry_code is not None:
            errors.append(
                "Mã Bộ GD&ĐT đã được sử dụng cho đối tượng khác."
            )

    if citizen_id:
        duplicate_citizen_id = db.scalar(
            select(SurveyPerson).where(
                SurveyPerson.citizen_id == citizen_id,
                SurveyPerson.is_active.is_(True),
            )
        )
        if duplicate_citizen_id is not None:
            errors.append("CCCD đã được sử dụng cho đối tượng khác.")

    duplicate_name = db.scalar(
        select(SurveyPerson).where(
            SurveyPerson.household_id == household_id,
            func.lower(SurveyPerson.full_name) == full_name.lower(),
            SurveyPerson.date_of_birth == parsed_birth_date,
            SurveyPerson.is_active.is_(True),
        )
    )

    if duplicate_name is not None:
        errors.append(
            "Đối tượng có cùng họ tên và ngày sinh đã tồn tại trong hộ."
        )

    will_be_head = la_quan_he_chu_ho(relationship_to_head)
    if will_be_head:
        existing_head = next(
            (
                item
                for item in survey_form.household.people
                if item.is_active
                and la_quan_he_chu_ho(item.relationship_to_head)
            ),
            None,
        )
        if existing_head is not None:
            errors.append(
                "Trong hộ đã có một đối tượng được ghi là Chủ hộ."
            )

    if errors:
        return hien_thi_trang_doi_tuong(
            request=request,
            db=db,
            survey_form=survey_form,
            thong_bao_loi=" ".join(errors),
            form_data=form_data,
            status_code=400,
        )

    person = SurveyPerson(
        # Mã tạm duy nhất để lấy ID an toàn trước khi sinh mã chính thức.
        code=f"TMP-{uuid4().hex[:12]}",
        household_id=household_id,
        student_id=(
            selected_student.id
            if selected_student is not None
            else None
        ),
        full_name=full_name,
        date_of_birth=parsed_birth_date,
        gender=gender or None,
        ethnic_group=ethnic_group or None,
        relationship_to_head=relationship_to_head or None,
        personal_id=personal_id or None,
        citizen_id=citizen_id or None,
        ministry_student_code=ministry_student_code or None,
        permanent_address=permanent_address or None,
        current_address=current_address or None,
        residency_status=residency_status,
        special_circumstances=special_circumstances or None,
        notes=notes or None,
        is_active=True,
    )

    db.add(person)
    db.flush()

    # Dùng khóa chính đã được CSDL cấp để tránh trùng mã khi nhiều
    # người cùng nhập dữ liệu. Mã đã cấp không bị dùng lại vì bản ghi
    # được xóa mềm bằng is_active=False.
    person.code = f"DT-{person.id:08d}"

    if will_be_head:
        survey_form.household.head_name = full_name
        survey_form.head_name_snapshot = full_name

    if survey_form.status == "CHUA_DIEU_TRA":
        survey_form.status = "DANG_DIEU_TRA"

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return hien_thi_trang_doi_tuong(
            request=request,
            db=db,
            survey_form=survey_form,
            thong_bao_loi=(
                "Không thể lưu đối tượng. Mã hoặc thông tin "
                "định danh có thể đã tồn tại."
            ),
            form_data=form_data,
            status_code=400,
        )

    return RedirectResponse(
        url=(
            f"/dieu-tra/{batch_id}/ho-dan/"
            f"{household_id}/doi-tuong?status=person_created"
        ),
        status_code=303,
    )

@router.get(
    "/{batch_id}/ho-dan/{household_id}/doi-tuong/tim-hoc-sinh"
)
def tim_hoc_sinh_de_lien_ket(
    batch_id: int,
    household_id: int,
    request: Request,
    q: str = "",
    current_person_id: int | None = None,
    limit: int = 20,
    db: Session = Depends(get_db),
):
    """
    Tìm nhanh học sinh để liên kết với đối tượng điều tra.

    Chỉ trả về tối đa 30 kết quả và loại các học sinh đã được liên kết
    với một đối tượng đang hoạt động khác. Đường dẫn nằm trong đúng
    phiếu/hộ nên vẫn được middleware kiểm tra phạm vi tài khoản.
    """

    user = lay_thong_tin_nguoi_dung(request)
    if not can_edit_survey_data(user.get("role_code")):
        return JSONResponse(
            content={
                "items": [],
                "message": "Tài khoản không có quyền liên kết học sinh.",
            },
            status_code=403,
        )

    survey_form = lay_phieu_ho(
        db=db,
        batch_id=batch_id,
        household_id=household_id,
    )
    if survey_form is None:
        return JSONResponse(
            content={"items": [], "message": "Không tìm thấy phiếu điều tra."},
            status_code=404,
        )

    keyword = chuan_hoa_van_ban(q)[:100]
    if len(keyword) < 2:
        return {
            "items": [],
            "message": "Nhập ít nhất 2 ký tự để tìm học sinh.",
        }

    limit = max(1, min(int(limit or 20), 30))

    linked_student_ids = select(SurveyPerson.student_id).where(
        SurveyPerson.student_id.is_not(None),
        SurveyPerson.is_active.is_(True),
    )
    if current_person_id is not None:
        linked_student_ids = linked_student_ids.where(
            SurveyPerson.id != current_person_id
        )

    search_value = f"%{keyword}%"
    students = db.scalars(
        select(Student)
        .where(
            Student.is_active.is_(True),
            ~Student.id.in_(linked_student_ids),
            or_(
                Student.code.ilike(search_value),
                Student.full_name.ilike(search_value),
                Student.personal_id.ilike(search_value),
            ),
        )
        .order_by(
            Student.full_name.asc(),
            Student.date_of_birth.asc(),
            Student.code.asc(),
        )
        .limit(limit)
    ).all()

    return {
        "items": [
            {
                "id": student.id,
                "code": student.code,
                "full_name": student.full_name,
                "date_of_birth": (
                    student.date_of_birth.isoformat()
                    if student.date_of_birth
                    else ""
                ),
                "gender": student.gender or "",
                "ethnic_group": student.ethnic_group or "",
                "personal_id": student.personal_id or "",
                "permanent_address": student.permanent_address or "",
                "current_address": student.current_address or "",
            }
            for student in students
        ],
        "message": (
            "Không tìm thấy học sinh phù hợp."
            if not students
            else ""
        ),
    }


# =========================================================
# CHỈNH SỬA VÀ NGỪNG THEO DÕI ĐỐI TƯỢNG
# =========================================================

def khoa_so_sanh_khong_dau(value: str | None) -> str:
    """Chuẩn hóa văn bản để so sánh không phân biệt dấu và hoa thường."""

    normalized = unicodedata.normalize(
        "NFD",
        value or "",
    )

    without_marks = "".join(
        character
        for character in normalized
        if unicodedata.category(character) != "Mn"
    )

    return " ".join(
        without_marks.lower().strip().split()
    )


def la_quan_he_chu_ho(value: str | None) -> bool:
    """Nhận diện các cách ghi phổ biến của quan hệ chủ hộ."""

    return khoa_so_sanh_khong_dau(value) in {
        "chu ho",
        "chủ hộ",
    }


def la_doi_tuong_chu_ho(
    person: SurveyPerson,
    household: Household,
) -> bool:
    """Xác định đối tượng đang đại diện vai trò chủ hộ."""

    if la_quan_he_chu_ho(person.relationship_to_head):
        return True

    return (
        khoa_so_sanh_khong_dau(person.full_name)
        == khoa_so_sanh_khong_dau(household.head_name)
    )


def lay_doi_tuong_sua(
    db: Session,
    household_id: int,
    person_id: int,
) -> SurveyPerson | None:
    """Lấy một đối tượng đang hoạt động thuộc đúng hộ để sửa."""

    return db.scalar(
        select(SurveyPerson)
        .options(selectinload(SurveyPerson.student))
        .where(
            SurveyPerson.id == person_id,
            SurveyPerson.household_id == household_id,
            SurveyPerson.is_active.is_(True),
        )
    )


def hien_thi_form_sua_doi_tuong(
    *,
    request: Request,
    db: Session,
    survey_form: SurveyForm,
    person: SurveyPerson,
    thong_bao_loi: str | None = None,
    form_data: dict[str, Any] | None = None,
    status_code: int = 200,
):
    """Hiển thị biểu mẫu sửa đối tượng và giữ lại dữ liệu khi có lỗi."""

    if form_data is None:
        form_data = {
            "student_id": person.student_id,
            "full_name": person.full_name,
            "date_of_birth": (
                person.date_of_birth.isoformat()
                if person.date_of_birth
                else ""
            ),
            "gender": person.gender or "",
            "ethnic_group": person.ethnic_group or "",
            "relationship_to_head": (
                person.relationship_to_head or ""
            ),
            "personal_id": person.personal_id or "",
            "citizen_id": person.citizen_id or "",
            "ministry_student_code": (
                person.ministry_student_code or ""
            ),
            "permanent_address": person.permanent_address or "",
            "current_address": person.current_address or "",
            "residency_status": (
                person.residency_status or "CHUA_XAC_DINH"
            ),
            "special_circumstances": (
                person.special_circumstances or ""
            ),
            "notes": person.notes or "",
        }

    selected_student = None
    selected_student_id = form_data.get("student_id")
    if selected_student_id:
        selected_student = db.get(Student, int(selected_student_id))

    return templates.TemplateResponse(
        request=request,
        name="surveys/person_edit.html",
        context={
            "nguoi_dung": request.scope.get("auth_user"),
            "survey_form": survey_form,
            "batch": survey_form.survey_batch,
            "household": survey_form.household,
            "person": person,
            "selected_student": selected_student,
            "residency_status_labels": RESIDENCY_STATUS_LABELS,
            "form_data": form_data,
            "thong_bao_loi": thong_bao_loi,
        },
        status_code=status_code,
    )

@router.get(
    "/{batch_id}/ho-dan/{household_id}/doi-tuong/{person_id}/sua",
    response_class=HTMLResponse,
)
def sua_doi_tuong_form(
    batch_id: int,
    household_id: int,
    person_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    survey_form = lay_phieu_ho(
        db=db,
        batch_id=batch_id,
        household_id=household_id,
    )

    if survey_form is None:
        return RedirectResponse(
            url=f"/dieu-tra/{batch_id}/ho-dan",
            status_code=303,
        )

    person = lay_doi_tuong_sua(
        db=db,
        household_id=household_id,
        person_id=person_id,
    )

    if person is None:
        return RedirectResponse(
            url=(
                f"/dieu-tra/{batch_id}/ho-dan/"
                f"{household_id}/doi-tuong"
            ),
            status_code=303,
        )

    return hien_thi_form_sua_doi_tuong(
        request=request,
        db=db,
        survey_form=survey_form,
        person=person,
    )


@router.post(
    "/{batch_id}/ho-dan/{household_id}/doi-tuong/{person_id}/sua"
)
def cap_nhat_doi_tuong(
    batch_id: int,
    household_id: int,
    person_id: int,
    request: Request,
    full_name: Annotated[str, Form()],
    student_id: Annotated[str, Form()] = "",
    date_of_birth: Annotated[str, Form()] = "",
    gender: Annotated[str, Form()] = "",
    ethnic_group: Annotated[str, Form()] = "",
    relationship_to_head: Annotated[str, Form()] = "",
    personal_id: Annotated[str, Form()] = "",
    citizen_id: Annotated[str, Form()] = "",
    ministry_student_code: Annotated[str, Form()] = "",
    permanent_address: Annotated[str, Form()] = "",
    current_address: Annotated[str, Form()] = "",
    residency_status: Annotated[str, Form()] = "THUONG_TRU",
    special_circumstances: Annotated[str, Form()] = "",
    notes: Annotated[str, Form()] = "",
    db: Session = Depends(get_db),
):
    survey_form = lay_phieu_ho(
        db=db,
        batch_id=batch_id,
        household_id=household_id,
    )

    if survey_form is None:
        return RedirectResponse(
            url=f"/dieu-tra/{batch_id}/ho-dan",
            status_code=303,
        )

    person = lay_doi_tuong_sua(
        db=db,
        household_id=household_id,
        person_id=person_id,
    )

    if person is None:
        return RedirectResponse(
            url=(
                f"/dieu-tra/{batch_id}/ho-dan/"
                f"{household_id}/doi-tuong"
            ),
            status_code=303,
        )

    full_name = chuan_hoa_van_ban(full_name)
    gender = chuan_hoa_van_ban(gender)
    ethnic_group = chuan_hoa_van_ban(ethnic_group)
    relationship_to_head = chuan_hoa_van_ban(
        relationship_to_head
    )
    personal_id = chuan_hoa_ma(personal_id)
    citizen_id = chuan_hoa_ma(citizen_id)
    ministry_student_code = chuan_hoa_ma(
        ministry_student_code
    )
    permanent_address = chuan_hoa_van_ban(
        permanent_address
    )
    current_address = chuan_hoa_van_ban(
        current_address
    )
    special_circumstances = special_circumstances.strip()
    notes = notes.strip()

    form_data: dict[str, Any] = {
        "student_id": int(student_id) if student_id.isdigit() else None,
        "full_name": full_name,
        "date_of_birth": date_of_birth,
        "gender": gender,
        "ethnic_group": ethnic_group,
        "relationship_to_head": relationship_to_head,
        "personal_id": personal_id,
        "citizen_id": citizen_id,
        "ministry_student_code": ministry_student_code,
        "permanent_address": permanent_address,
        "current_address": current_address,
        "residency_status": residency_status,
        "special_circumstances": special_circumstances,
        "notes": notes,
    }

    errors: list[str] = []

    if survey_form.survey_batch.status == "DA_KET_THUC":
        errors.append(
            "Đợt điều tra đã kết thúc, không thể sửa đối tượng."
        )

    selected_student: Student | None = None

    if student_id.strip():
        if not student_id.isdigit():
            errors.append("Học sinh liên kết không hợp lệ.")
        else:
            selected_student = db.get(Student, int(student_id))

            if (
                selected_student is None
                or not selected_student.is_active
            ):
                errors.append(
                    "Không tìm thấy học sinh được chọn."
                )

    if selected_student is not None:
        existing_link = db.scalar(
            select(SurveyPerson).where(
                SurveyPerson.student_id == selected_student.id,
                SurveyPerson.id != person.id,
                SurveyPerson.is_active.is_(True),
            )
        )

        if existing_link is not None:
            errors.append(
                "Học sinh này đã được liên kết với đối tượng khác."
            )

        if ministry_student_code and (
            selected_student.code != ministry_student_code
        ):
            errors.append(
                "Mã Bộ GD&ĐT không khớp với học sinh đã chọn."
            )

        if (
            personal_id
            and selected_student.personal_id
            and selected_student.personal_id != personal_id
        ):
            errors.append(
                "Số định danh không khớp với học sinh đã chọn."
            )

        if not full_name:
            full_name = selected_student.full_name
            form_data["full_name"] = full_name

        if not date_of_birth and selected_student.date_of_birth:
            date_of_birth = selected_student.date_of_birth.isoformat()
            form_data["date_of_birth"] = date_of_birth

        if not gender and selected_student.gender:
            gender = selected_student.gender
            form_data["gender"] = gender

        if not ethnic_group and selected_student.ethnic_group:
            ethnic_group = selected_student.ethnic_group
            form_data["ethnic_group"] = ethnic_group

        if not personal_id and selected_student.personal_id:
            personal_id = selected_student.personal_id
            form_data["personal_id"] = personal_id

        if not ministry_student_code and selected_student.code:
            ministry_student_code = selected_student.code
            form_data["ministry_student_code"] = ministry_student_code

        if not permanent_address and selected_student.permanent_address:
            permanent_address = selected_student.permanent_address
            form_data["permanent_address"] = permanent_address

        if not current_address and selected_student.current_address:
            current_address = selected_student.current_address
            form_data["current_address"] = current_address

    if not full_name:
        errors.append("Họ và tên đối tượng không được để trống.")

    if len(full_name) > 200:
        errors.append("Họ và tên dài quá 200 ký tự.")

    parsed_birth_date, birth_error = chuyen_ngay(
        date_of_birth,
        "Ngày sinh",
        bat_buoc=True,
    )

    if birth_error:
        errors.append(birth_error)

    if parsed_birth_date and parsed_birth_date > date.today():
        errors.append(
            "Ngày sinh không được lớn hơn ngày hiện tại."
        )

    if not gender:
        errors.append("Giới tính không được để trống.")
    elif gender not in {"Nam", "Nữ", "Khác"}:
        errors.append("Giới tính không hợp lệ.")

    if not ethnic_group:
        errors.append("Dân tộc không được để trống.")

    if not relationship_to_head:
        errors.append(
            "Quan hệ với chủ hộ không được để trống."
        )

    if residency_status not in RESIDENCY_STATUS_LABELS:
        errors.append("Trạng thái cư trú không hợp lệ.")

    if len(personal_id) > 50:
        errors.append("Số định danh dài quá 50 ký tự.")
    if len(citizen_id) > 50:
        errors.append("Căn cước công dân dài quá 50 ký tự.")

    if len(ministry_student_code) > 50:
        errors.append("Mã Bộ GD&ĐT dài quá 50 ký tự.")

    if personal_id:
        duplicate_personal_id = db.scalar(
            select(SurveyPerson).where(
                SurveyPerson.personal_id == personal_id,
                SurveyPerson.id != person.id,
                SurveyPerson.is_active.is_(True),
            )
        )

        if duplicate_personal_id is not None:
            errors.append(
                "Số định danh cá nhân đã được dùng cho đối tượng khác."
            )

    if ministry_student_code:
        duplicate_ministry_code = db.scalar(
            select(SurveyPerson).where(
                SurveyPerson.ministry_student_code
                == ministry_student_code,
                SurveyPerson.id != person.id,
                SurveyPerson.is_active.is_(True),
            )
        )

        if duplicate_ministry_code is not None:
            errors.append(
                "Mã Bộ GD&ĐT đã được dùng cho đối tượng khác."
            )

    if citizen_id:
        duplicate_citizen_id = db.scalar(
            select(SurveyPerson).where(
                SurveyPerson.citizen_id == citizen_id,
                SurveyPerson.id != person.id,
                SurveyPerson.is_active.is_(True),
            )
        )
        if duplicate_citizen_id is not None:
            errors.append("CCCD đã được dùng cho đối tượng khác.")

    duplicate_name = db.scalar(
        select(SurveyPerson).where(
            SurveyPerson.household_id == household_id,
            func.lower(SurveyPerson.full_name) == full_name.lower(),
            SurveyPerson.date_of_birth == parsed_birth_date,
            SurveyPerson.id != person.id,
            SurveyPerson.is_active.is_(True),
        )
    )

    if duplicate_name is not None:
        errors.append(
            "Đối tượng có cùng họ tên và ngày sinh đã tồn tại trong hộ."
        )

    other_people = db.scalars(
        select(SurveyPerson).where(
            SurveyPerson.household_id == household_id,
            SurveyPerson.id != person.id,
            SurveyPerson.is_active.is_(True),
        )
    ).all()

    replacement_head = next(
        (
            item
            for item in other_people
            if la_quan_he_chu_ho(item.relationship_to_head)
        ),
        None,
    )

    was_head = la_doi_tuong_chu_ho(
        person,
        survey_form.household,
    )
    will_be_head = la_quan_he_chu_ho(
        relationship_to_head
    )

    if will_be_head and replacement_head is not None:
        errors.append(
            "Trong hộ đã có một đối tượng được ghi là Chủ hộ."
        )

    if was_head and not will_be_head and replacement_head is None:
        errors.append(
            "Đối tượng này đang là chủ hộ. Hãy sửa một đối tượng khác "
            "thành quan hệ Chủ hộ trước."
        )

    if errors:
        return hien_thi_form_sua_doi_tuong(
            request=request,
            db=db,
            survey_form=survey_form,
            person=person,
            thong_bao_loi=" ".join(errors),
            form_data=form_data,
            status_code=400,
        )

    person.student_id = (
        selected_student.id
        if selected_student is not None
        else None
    )
    person.full_name = full_name
    person.date_of_birth = parsed_birth_date
    person.gender = gender or None
    person.ethnic_group = ethnic_group or None
    person.relationship_to_head = relationship_to_head or None
    person.personal_id = personal_id or None
    person.citizen_id = citizen_id or None
    person.ministry_student_code = ministry_student_code or None
    person.permanent_address = permanent_address or None
    person.current_address = current_address or None
    person.residency_status = residency_status
    person.special_circumstances = special_circumstances or None
    person.notes = notes or None

    if will_be_head:
        survey_form.household.head_name = full_name
        survey_form.head_name_snapshot = full_name
    elif was_head and replacement_head is not None:
        survey_form.household.head_name = replacement_head.full_name
        survey_form.head_name_snapshot = replacement_head.full_name

    try:
        db.commit()
    except IntegrityError:
        db.rollback()

        return hien_thi_form_sua_doi_tuong(
            request=request,
            db=db,
            survey_form=survey_form,
            person=person,
            thong_bao_loi=(
                "Không thể cập nhật đối tượng. Thông tin định danh "
                "hoặc liên kết học sinh có thể đã tồn tại."
            ),
            form_data=form_data,
            status_code=400,
        )

    return RedirectResponse(
        url=(
            f"/dieu-tra/{batch_id}/ho-dan/"
            f"{household_id}/doi-tuong?status=person_updated"
        ),
        status_code=303,
    )

@router.post(
    "/{batch_id}/ho-dan/{household_id}/doi-tuong/{person_id}/ngung-theo-doi"
)
def ngung_theo_doi_doi_tuong(
    batch_id: int,
    household_id: int,
    person_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    survey_form = lay_phieu_ho(
        db=db,
        batch_id=batch_id,
        household_id=household_id,
    )

    if survey_form is None:
        return RedirectResponse(
            url=f"/dieu-tra/{batch_id}/ho-dan",
            status_code=303,
        )

    person = lay_doi_tuong_sua(
        db=db,
        household_id=household_id,
        person_id=person_id,
    )

    if person is None:
        return RedirectResponse(
            url=(
                f"/dieu-tra/{batch_id}/ho-dan/"
                f"{household_id}/doi-tuong"
            ),
            status_code=303,
        )

    errors: list[str] = []

    if survey_form.survey_batch.status == "DA_KET_THUC":
        errors.append(
            "Đợt điều tra đã kết thúc, không thể ngừng theo dõi."
        )

    if la_doi_tuong_chu_ho(person, survey_form.household):
        other_people = db.scalars(
            select(SurveyPerson).where(
                SurveyPerson.household_id == household_id,
                SurveyPerson.id != person.id,
                SurveyPerson.is_active.is_(True),
            )
        ).all()

        replacement_head = next(
            (
                item
                for item in other_people
                if la_quan_he_chu_ho(item.relationship_to_head)
            ),
            None,
        )

        if replacement_head is None:
            errors.append(
                "Không thể ngừng theo dõi chủ hộ. Hãy sửa một đối tượng "
                "khác thành quan hệ Chủ hộ trước."
            )
        else:
            survey_form.household.head_name = replacement_head.full_name
            survey_form.head_name_snapshot = replacement_head.full_name

    if errors:
        return hien_thi_trang_doi_tuong(
            request=request,
            db=db,
            survey_form=survey_form,
            thong_bao_loi=" ".join(errors),
            status_code=400,
        )

    person.is_active = False

    try:
        db.commit()
    except IntegrityError:
        db.rollback()

        return hien_thi_trang_doi_tuong(
            request=request,
            db=db,
            survey_form=survey_form,
            thong_bao_loi=(
                "Không thể ngừng theo dõi đối tượng ở thời điểm này."
            ),
            status_code=400,
        )

    return RedirectResponse(
        url=(
            f"/dieu-tra/{batch_id}/ho-dan/"
            f"{household_id}/doi-tuong?status=person_deactivated"
        ),
        status_code=303,
    )


# =========================================================
# THEO DÕI THÔNG TIN TỪNG NĂM HỌC
# =========================================================

def lay_doi_tuong_trong_ho(
    db: Session,
    household_id: int,
    person_id: int,
) -> SurveyPerson | None:
    """Lấy một đối tượng đang hoạt động thuộc đúng hộ."""

    return db.scalar(
        select(SurveyPerson)
        .options(selectinload(SurveyPerson.student))
        .where(
            SurveyPerson.id == person_id,
            SurveyPerson.household_id == household_id,
            SurveyPerson.is_active.is_(True),
        )
    )


def chuyen_id_tuy_chon(value: str) -> int | None:
    """Chuyển ID từ biểu mẫu; giá trị trống trả về None."""

    value = value.strip()
    if not value:
        return None
    if not value.isdigit():
        return None
    return int(value)


def chuyen_gia_tri_co_khong(
    value: str,
    field_label: str,
) -> tuple[bool | None, str | None]:
    """
    Chuyển giá trị ba trạng thái từ biểu mẫu:
    - ""  -> chưa xác định (None)
    - "1" -> Có (True)
    - "0" -> Không (False)
    """

    normalized = str(value or "").strip()
    if normalized == "":
        return None, None
    if normalized == "1":
        return True, None
    if normalized == "0":
        return False, None
    return None, f"{field_label} không hợp lệ."


def nhan_co_khong(value: bool | None) -> str:
    """Nhãn hiển thị thống nhất cho giá trị Có/Không/Chưa xác định."""

    if value is True:
        return "Có"
    if value is False:
        return "Không"
    return "Chưa xác định"


def ban_ghi_nam_hoc_co_du_lieu(
    record: SurveyPersonYearRecord | None,
) -> bool:
    """Xác định hồ sơ năm học đã có ít nhất một thông tin thực tế."""

    if record is None:
        return False

    return any(
        (
            bool(record.school_id),
            bool(record.class_id),
            bool(record.school_name_reported),
            bool(record.class_name_reported),
            record.learning_status not in {
                "",
                "CHUA_XAC_DINH",
                None,
            },
            record.completed_preschool_5 is not None,
            record.attends_required_days is not None,
            record.attends_regularly is not None,
            record.prepared_vietnamese is not None,
            record.weight_monitored is not None,
            record.underweight is not None,
            record.height_monitored is not None,
            record.stunted is not None,
            bool(record.special_circumstances),
            bool(getattr(record, "is_reviewed", False)),
            getattr(record, "disability_status", "CHUA_XAC_DINH")
            not in {"", "CHUA_XAC_DINH", None},
            bool(getattr(record, "disability_type", None)),
            bool(getattr(record, "disability_level", None)),
            getattr(record, "disability_certificate", None) is not None,
            getattr(record, "inclusive_education", None) is not None,
            getattr(record, "disability_support", None) is not None,
            bool(getattr(record, "disability_support_details", None)),
        )
    )


def lay_goi_y_nam_hoc_truoc(
    db: Session,
    person_id: int,
    school_year_id: int | None,
) -> dict[str, Any] | None:
    """Lấy hồ sơ gần nhất trước năm đang mở để gợi ý nhập liệu."""

    if school_year_id is None:
        return None

    selected_year = db.get(SchoolYear, school_year_id)
    if selected_year is None:
        return None

    rows = db.execute(
        select(SurveyPersonYearRecord, SchoolYear)
        .join(
            SchoolYear,
            SchoolYear.id == SurveyPersonYearRecord.school_year_id,
        )
        .where(
            SurveyPersonYearRecord.survey_person_id == person_id,
            SchoolYear.code < selected_year.code,
        )
        .order_by(
            SchoolYear.code.desc(),
            SurveyPersonYearRecord.updated_at.desc(),
            SurveyPersonYearRecord.id.desc(),
        )
    ).all()

    for previous_record, previous_year in rows:
        if not ban_ghi_nam_hoc_co_du_lieu(previous_record):
            continue

        previous_school = (
            db.get(School, previous_record.school_id)
            if previous_record.school_id is not None
            else None
        )
        previous_class = (
            db.get(Classroom, previous_record.class_id)
            if previous_record.class_id is not None
            else None
        )

        school_name = (
            previous_record.school_name_reported
            or (previous_school.name if previous_school is not None else "")
        )
        class_name = (
            previous_record.class_name_reported
            or (previous_class.name if previous_class is not None else "")
        )

        suggested_school_id = None
        if previous_school is not None and previous_school.is_active:
            suggested_school_id = previous_school.id

        suggested_class_id = None
        if suggested_school_id is not None and class_name:
            current_classes = db.scalars(
                select(Classroom)
                .where(
                    Classroom.school_id == suggested_school_id,
                    Classroom.school_year_id == school_year_id,
                    Classroom.is_active.is_(True),
                )
                .order_by(Classroom.name.asc(), Classroom.id.asc())
            ).all()

            class_key = khoa_so_sanh_khong_dau(class_name)
            matched_class = next(
                (
                    item
                    for item in current_classes
                    if khoa_so_sanh_khong_dau(item.name) == class_key
                ),
                None,
            )
            if matched_class is not None:
                suggested_class_id = matched_class.id

        return {
            "record": previous_record,
            "school_year": previous_year,
            "school_year_code": previous_year.code,
            "learning_status": previous_record.learning_status,
            "learning_status_label": LEARNING_STATUS_LABELS.get(
                previous_record.learning_status,
                previous_record.learning_status,
            ),
            "school_name": school_name or "—",
            "class_name": class_name or "—",
            "suggested_school_id": suggested_school_id,
            "suggested_class_id": suggested_class_id,
            "completed_preschool_by_age_label": nhan_co_khong(
                getattr(previous_record, "completed_preschool_by_age", None)
                if getattr(previous_record, "completed_preschool_by_age", None) is not None
                else previous_record.completed_preschool_5
            ),
            "completed_preschool_5_label": nhan_co_khong(
                previous_record.completed_preschool_5
            ),
            "attends_regularly_label": nhan_co_khong(
                previous_record.attends_regularly
            ),
            "disability_status_label": DISABILITY_STATUS_LABELS.get(
                getattr(previous_record, "disability_status", "CHUA_XAC_DINH"),
                "Chưa xác định",
            ),
            "disability_type_label": DISABILITY_TYPE_LABELS.get(
                getattr(previous_record, "disability_type", None),
                "—",
            ),
            "disability_level_label": DISABILITY_LEVEL_LABELS.get(
                getattr(previous_record, "disability_level", None),
                "—",
            ),
            "disability_certificate_label": nhan_co_khong(
                getattr(previous_record, "disability_certificate", None)
            ),
            "inclusive_education_label": nhan_co_khong(
                getattr(previous_record, "inclusive_education", None)
            ),
        }

    return None


def tao_ban_ghi_hien_thi_nam_hoc(
    selected_record: SurveyPersonYearRecord | None,
    previous_hint: dict[str, Any] | None,
    survey_form_id: int,
    person_id: int,
    school_year_id: int | None,
) -> tuple[SimpleNamespace | SurveyPersonYearRecord | None, list[str]]:
    """Ghép dữ liệu hiện tại với phần cơ bản còn thiếu của năm trước."""

    if school_year_id is None:
        return selected_record, []

    # Sau khi người dùng đã bấm Lưu, chỉ hiển thị dữ liệu chính thức của
    # năm hiện tại; không tiếp tục ghép dữ liệu tham chiếu năm trước.
    if selected_record is not None and getattr(selected_record, "is_reviewed", False):
        return selected_record, []

    field_names = (
        "school_id",
        "class_id",
        "school_name_reported",
        "class_name_reported",
        "learning_status",
        "highest_completed_grade",
        "education_attainment_level",
        "completed_preschool_by_age",
        "completed_preschool_5",
        "attends_required_days",
        "attends_regularly",
        "prepared_vietnamese",
        "weight_monitored",
        "underweight",
        "height_monitored",
        "stunted",
        "disability_status",
        "disability_type",
        "disability_level",
        "disability_certificate",
        "inclusive_education",
        "disability_support",
        "disability_support_details",
        "is_reviewed",
        "special_circumstances",
        "notes",
    )

    values: dict[str, Any] = {
        "survey_form_id": survey_form_id,
        "survey_person_id": person_id,
        "school_year_id": school_year_id,
        "school_id": None,
        "class_id": None,
        "school_name_reported": None,
        "class_name_reported": None,
        "learning_status": "CHUA_XAC_DINH",
        "highest_completed_grade": None,
        "education_attainment_level": "CHUA_XAC_DINH",
        "completed_preschool_by_age": None,
        "completed_preschool_5": None,
        "attends_required_days": None,
        "attends_regularly": None,
        "prepared_vietnamese": None,
        "weight_monitored": None,
        "underweight": None,
        "height_monitored": None,
        "stunted": None,
        "disability_status": "CHUA_XAC_DINH",
        "disability_type": None,
        "disability_level": None,
        "disability_certificate": None,
        "inclusive_education": None,
        "disability_support": None,
        "disability_support_details": None,
        "is_reviewed": False,
        "special_circumstances": None,
        "notes": None,
    }

    if selected_record is not None:
        for field_name in field_names:
            values[field_name] = getattr(selected_record, field_name)

    inherited_fields: list[str] = []
    if previous_hint is not None:
        previous_record = previous_hint["record"]

        if values["learning_status"] in {
            "",
            "CHUA_XAC_DINH",
            None,
        }:
            values["learning_status"] = previous_record.learning_status
            inherited_fields.append("tình trạng học tập")

        if not values["school_id"] and not values["school_name_reported"]:
            values["school_id"] = previous_hint["suggested_school_id"]
            values["school_name_reported"] = (
                previous_hint["school_name"]
                if previous_hint["school_name"] != "—"
                else None
            )
            inherited_fields.append("trường")

        if not values["class_id"] and not values["class_name_reported"]:
            values["class_id"] = previous_hint["suggested_class_id"]
            values["class_name_reported"] = (
                previous_hint["class_name"]
                if previous_hint["class_name"] != "—"
                else None
            )
            inherited_fields.append("lớp")

        if values["disability_status"] in {"", "CHUA_XAC_DINH", None}:
            values["disability_status"] = getattr(
                previous_record, "disability_status", "CHUA_XAC_DINH"
            )
            values["disability_type"] = getattr(
                previous_record, "disability_type", None
            )
            values["disability_level"] = getattr(
                previous_record, "disability_level", None
            )
            values["disability_certificate"] = getattr(
                previous_record, "disability_certificate", None
            )
            values["inclusive_education"] = getattr(
                previous_record, "inclusive_education", None
            )
            values["disability_support"] = getattr(
                previous_record, "disability_support", None
            )
            values["disability_support_details"] = getattr(
                previous_record, "disability_support_details", None
            )
            if values["disability_status"] != "CHUA_XAC_DINH":
                inherited_fields.append("thông tin khuyết tật")

        if (
            not values["special_circumstances"]
            and previous_record.special_circumstances
        ):
            values["special_circumstances"] = (
                previous_record.special_circumstances
            )
            inherited_fields.append("hoàn cảnh đặc biệt")

    if selected_record is not None and not inherited_fields:
        return selected_record, []

    return SimpleNamespace(**values), inherited_fields


def tao_du_lieu_lich_su_nam_hoc(
    db: Session,
    person_id: int,
    survey_form_id: int,
) -> list[dict[str, Any]]:
    """Ghép toàn bộ lịch sử năm học của đối tượng qua các đợt điều tra."""

    _ = survey_form_id  # Giữ tham số để tương thích với các chỗ gọi cũ.

    records = db.scalars(
        select(SurveyPersonYearRecord)
        .options(
            selectinload(SurveyPersonYearRecord.school_year),
            selectinload(SurveyPersonYearRecord.school),
            selectinload(SurveyPersonYearRecord.classroom),
        )
        .where(SurveyPersonYearRecord.survey_person_id == person_id)
    ).all()

    records.sort(
        key=lambda item: (
            item.school_year.code if item.school_year is not None else "",
            item.updated_at or item.created_at,
            item.id,
        ),
        reverse=True,
    )

    unique_records: list[SurveyPersonYearRecord] = []
    seen_year_ids: set[int] = set()
    for record in records:
        if record.school_year_id in seen_year_ids:
            continue
        seen_year_ids.add(record.school_year_id)
        unique_records.append(record)

    result: list[dict[str, Any]] = []
    for record in unique_records:
        year = record.school_year
        school = record.school
        classroom = record.classroom
        result.append(
            {
                "record": record,
                "school_year_code": (
                    year.code if year is not None else str(record.school_year_id)
                ),
                "school_name": (
                    record.school_name_reported
                    or (school.name if school is not None else "—")
                ),
                "class_name": (
                    record.class_name_reported
                    or (classroom.name if classroom is not None else "—")
                ),
                "learning_status_label": LEARNING_STATUS_LABELS.get(
                    record.learning_status,
                    record.learning_status,
                ),
                "completed_preschool_by_age_label": nhan_co_khong(
                    getattr(record, "completed_preschool_by_age", None)
                    if getattr(record, "completed_preschool_by_age", None) is not None
                    else record.completed_preschool_5
                ),
                "completed_preschool_5_label": nhan_co_khong(
                    record.completed_preschool_5
                ),
                "attends_regularly_label": nhan_co_khong(
                    record.attends_regularly
                ),
                "disability_status_label": DISABILITY_STATUS_LABELS.get(
                    getattr(record, "disability_status", "CHUA_XAC_DINH"),
                    "Chưa xác định",
                ),
                "disability_type_label": DISABILITY_TYPE_LABELS.get(
                    getattr(record, "disability_type", None),
                    "—",
                ),
                "disability_level_label": DISABILITY_LEVEL_LABELS.get(
                    getattr(record, "disability_level", None),
                    "—",
                ),
                "inclusive_education_label": nhan_co_khong(
                    getattr(record, "inclusive_education", None)
                ),
                "criteria_answered": sum(
                    value is not None
                    for value in (
                        getattr(record, "completed_preschool_by_age", None),
                        record.attends_required_days,
                        record.attends_regularly,
                        record.prepared_vietnamese,
                        record.weight_monitored,
                        record.underweight,
                        record.height_monitored,
                        record.stunted,
                    )
                ),
                "criteria_total": len(BOOLEAN_YEAR_FIELDS),
            }
        )

    return result


@router.get(
    "/{batch_id}/ho-dan/{household_id}/doi-tuong/nam-hoc",
    response_class=HTMLResponse,
)
def tong_quan_theo_doi_nam_hoc(
    request: Request,
    batch_id: int,
    household_id: int,
    db: Session = Depends(get_db),
):
    """Danh sách tất cả đối tượng trong hộ và số hồ sơ năm học."""

    survey_form = lay_phieu_ho(
        db=db,
        batch_id=batch_id,
        household_id=household_id,
    )
    if survey_form is None:
        return RedirectResponse(
            url=f"/dieu-tra/{batch_id}/ho-dan",
            status_code=303,
        )

    # === BAI_13B_12_V2_4_4_6_YEAR_OVERVIEW_SCOPE_GUARD_START ===
    if not co_quyen_truy_cap_phieu(
        db=db, request=request, survey_form=survey_form
    ):
        return RedirectResponse(
            url=f"/dieu-tra/{batch_id}/ho-dan",
            status_code=303,
        )
    # === BAI_13B_12_V2_4_4_6_YEAR_OVERVIEW_SCOPE_GUARD_END ===

    people = db.scalars(
        select(SurveyPerson)
        .where(
            SurveyPerson.household_id == household_id,
            SurveyPerson.is_active.is_(True),
        )
        .order_by(
            SurveyPerson.date_of_birth.asc(),
            SurveyPerson.full_name.asc(),
        )
    ).all()

    person_ids = [item.id for item in people]
    records = db.scalars(
        select(SurveyPersonYearRecord)
        .where(
            SurveyPersonYearRecord.survey_form_id == survey_form.id,
            SurveyPersonYearRecord.survey_person_id.in_(person_ids),
        )
        .order_by(
            SurveyPersonYearRecord.school_year_id.desc(),
            SurveyPersonYearRecord.id.desc(),
        )
    ).all() if person_ids else []

    year_ids = {item.school_year_id for item in records}
    years = {
        item.id: item
        for item in db.scalars(
            select(SchoolYear).where(SchoolYear.id.in_(year_ids))
        ).all()
    } if year_ids else {}

    grouped: dict[int, list[SurveyPersonYearRecord]] = {}
    for record in records:
        grouped.setdefault(record.survey_person_id, []).append(record)

    rows: list[dict[str, Any]] = []
    current_school_year_id = survey_form.survey_batch.school_year_id

    for person in people:
        person_records = grouped.get(person.id, [])
        latest = person_records[0] if person_records else None
        latest_year = years.get(latest.school_year_id) if latest else None
        current_record = next(
            (
                item
                for item in person_records
                if item.school_year_id == current_school_year_id
            ),
            None,
        )
        # === BAI_13B_11_13_3_7_YEAR_OVERVIEW_DYNAMIC_START ===
        current_progress = b131133_tien_do_nam_hoc(
            person=person,
            record=current_record,
            school_year=survey_form.survey_batch.school_year,
        )
        current_answered = int(
            current_progress["answered"]
        )
        current_total = int(
            current_progress["total"]
        )
        # === BAI_13B_11_13_3_7_YEAR_OVERVIEW_DYNAMIC_END ===

        rows.append(
            {
                "person": person,
                "record_count": len(person_records),
                "latest_year_code": latest_year.code if latest_year else "—",
                "latest_status": (
                    LEARNING_STATUS_LABELS.get(
                        latest.learning_status,
                        latest.learning_status,
                    )
                    if latest
                    else "Chưa có dữ liệu"
                ),
                "current_year_status": (
                    LEARNING_STATUS_LABELS.get(
                        current_record.learning_status,
                        current_record.learning_status,
                    )
                    if current_record
                    else "Chưa nhập"
                ),
                "current_year_answered": current_answered,
                "current_year_total": current_total,
            }
        )

    return templates.TemplateResponse(
        request=request,
        name="surveys/year_overview.html",
        context={
            "nguoi_dung": request.scope.get("auth_user"),
            "survey_form": survey_form,
            "batch": survey_form.survey_batch,
            "household": survey_form.household,
            "rows": rows,
            "can_edit_data": can_edit_survey_data(
                lay_thong_tin_nguoi_dung(request).get("role_code")
            ),
        },
    )


@router.get(
    "/{batch_id}/ho-dan/{household_id}/doi-tuong/{person_id}/nam-hoc",
    response_class=HTMLResponse,
)
def theo_doi_nam_hoc_doi_tuong(
    request: Request,
    batch_id: int,
    household_id: int,
    person_id: int,
    school_year_id: int | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
):
    survey_form = lay_phieu_ho(
        db=db,
        batch_id=batch_id,
        household_id=household_id,
    )
    person = lay_doi_tuong_trong_ho(
        db=db,
        household_id=household_id,
        person_id=person_id,
    )

    if survey_form is None or person is None:
        return RedirectResponse(
            url=(
                f"/dieu-tra/{batch_id}/ho-dan/"
                f"{household_id}/doi-tuong"
            ),
            status_code=303,
        )

    if not co_quyen_truy_cap_phieu(
        db=db, request=request, survey_form=survey_form
    ):
        return RedirectResponse(
            url=f"/dieu-tra/{batch_id}/ho-dan",
            status_code=303,
        )

    # === BAI_13B_12_V2_4_4_6_TEACHER_CURRENT_YEAR_GET_START ===
    _mobile_role_code = normalize_role_code(
        lay_thong_tin_nguoi_dung(request).get("role_code")
    )
    if _mobile_role_code == TEACHER_ROLE_CODE:
        school_year_id = int(survey_form.survey_batch.school_year_id)
    # === BAI_13B_12_V2_4_4_6_TEACHER_CURRENT_YEAR_GET_END ===

    school_years = db.scalars(
        select(SchoolYear)
        .order_by(SchoolYear.code.desc(), SchoolYear.id.desc())
    ).all()
    valid_year_ids = {item.id for item in school_years}

    if school_year_id not in valid_year_ids:
        school_year_id = survey_form.survey_batch.school_year_id
    if school_year_id not in valid_year_ids and school_years:
        school_year_id = school_years[0].id

    selected_record = None
    if school_year_id is not None:
        selected_record = db.scalar(
            select(SurveyPersonYearRecord).where(
                SurveyPersonYearRecord.survey_form_id == survey_form.id,
                SurveyPersonYearRecord.survey_person_id == person_id,
                SurveyPersonYearRecord.school_year_id == school_year_id,
            )
        )

    previous_year_hint = lay_goi_y_nam_hoc_truoc(
        db=db,
        person_id=person_id,
        school_year_id=school_year_id,
    )
    if selected_record is not None and getattr(selected_record, "is_reviewed", False):
        previous_year_hint = None

    display_record, inherited_fields = tao_ban_ghi_hien_thi_nam_hoc(
        selected_record=selected_record,
        previous_hint=previous_year_hint,
        survey_form_id=survey_form.id,
        person_id=person.id,
        school_year_id=school_year_id,
    )

    schools = db.scalars(
        select(School)
        .options(selectinload(School.commune))
        .where(School.is_active.is_(True))
        .order_by(School.name.asc())
    ).all()

    selected_school_id = (
        display_record.school_id if display_record else None
    )
    selected_class_id = (
        display_record.class_id if display_record else None
    )

    history_rows = tao_du_lieu_lich_su_nam_hoc(
        db=db,
        person_id=person_id,
        survey_form_id=survey_form.id,
    )

    # Điều hướng nhanh cho giáo viên trên điện thoại sau khi lưu.
    active_people = db.scalars(
        select(SurveyPerson)
        .where(
            SurveyPerson.household_id == household_id,
            SurveyPerson.is_active.is_(True),
        )
        .order_by(
            SurveyPerson.date_of_birth.asc(),
            SurveyPerson.full_name.asc(),
            SurveyPerson.id.asc(),
        )
    ).all()

    current_person_index = next(
        (
            index
            for index, item in enumerate(active_people)
            if int(item.id) == int(person_id)
        ),
        -1,
    )
    next_person = (
        active_people[current_person_index + 1]
        if 0 <= current_person_index < len(active_people) - 1
        else None
    )
    next_person_url = (
        f"/dieu-tra/{batch_id}/ho-dan/{household_id}/doi-tuong/"
        f"{next_person.id}/nam-hoc?school_year_id={school_year_id}#year_record_form"
        if next_person is not None
        else None
    )
    quick_entry_url = (
        f"/dieu-tra/{batch_id}/ho-dan/{household_id}/nhap-nhanh#members"
    )
    work_url = "/"

    # === BAI_13B_11_14_3_LOAD_EVENTS_START ===
    b131143_events = b131143_load_person_events(
        db,
        person.id,
        school_year_id,
    )
    # === BAI_13B_11_14_3_LOAD_EVENTS_END ===

    return templates.TemplateResponse(
        request=request,
        name="surveys/year_records.html",
        context={
            "b131143_events": b131143_events,
            "nguoi_dung": request.scope.get("auth_user"),
            "survey_form": survey_form,
            "batch": survey_form.survey_batch,
            "household": survey_form.household,
            "person": person,
            "school_years": school_years,
            "schools": schools,
            "selected_school_year_id": school_year_id,
            "selected_record": display_record,
            "selected_record_saved": selected_record is not None,
            "selected_school_id": selected_school_id,
            "selected_class_id": selected_class_id,
            "previous_year_hint": previous_year_hint,
            "inherited_fields": inherited_fields,
            "history_rows": history_rows,
            "learning_status_labels": LEARNING_STATUS_LABELS,
            "residency_status_labels": RESIDENCY_STATUS_LABELS,
            "disability_status_labels": DISABILITY_STATUS_LABELS,
            "disability_type_labels": DISABILITY_TYPE_LABELS,
            "disability_level_labels": DISABILITY_LEVEL_LABELS,
            "can_edit_data": can_edit_survey_data(
                lay_thong_tin_nguoi_dung(request).get("role_code")
            ),
            "thong_bao": STATUS_MESSAGES.get(status),
            "thong_bao_loi": None,
            "year_record_saved": status == "year_record_saved",
            "next_person_url": next_person_url,
            "quick_entry_url": quick_entry_url,
            "work_url": work_url,
        },
    )

@router.post(
    "/{batch_id}/ho-dan/{household_id}/doi-tuong/{person_id}/nam-hoc/luu"
)
def luu_theo_doi_nam_hoc(
    request: Request,
    batch_id: int,
    household_id: int,
    person_id: int,
    school_year_id: Annotated[int, Form()],
    learning_status: Annotated[str, Form()] = "DANG_HOC",
    school_id: Annotated[str, Form()] = "",
    class_id: Annotated[str, Form()] = "",
    school_name_reported: Annotated[str, Form()] = "",
    class_name_reported: Annotated[str, Form()] = "",
    completed_preschool_by_age: Annotated[str, Form()] = "",
    completed_preschool_5: Annotated[str, Form()] = "",
    attends_required_days: Annotated[str, Form()] = "",
    attends_regularly: Annotated[str, Form()] = "",
    prepared_vietnamese: Annotated[str, Form()] = "",
    weight_monitored: Annotated[str, Form()] = "",
    underweight: Annotated[str, Form()] = "",
    height_monitored: Annotated[str, Form()] = "",
    stunted: Annotated[str, Form()] = "",
    attends_two_sessions_per_day: Annotated[str, Form()] = "",
    disability_status: Annotated[str, Form()] = "CHUA_XAC_DINH",
    disability_can_learn: Annotated[str, Form()] = "",
    disability_access_education: Annotated[str, Form()] = "",
    residency_status: Annotated[str, Form()] = "CHUA_XAC_DINH",
    move_in_active: Annotated[str | None, Form()] = None,
    move_in_date: Annotated[str | None, Form()] = None,
    move_in_origin: Annotated[str | None, Form()] = None,
    move_out_active: Annotated[str | None, Form()] = None,
    move_out_date: Annotated[str | None, Form()] = None,
    move_out_destination: Annotated[str | None, Form()] = None,
    death_active: Annotated[str | None, Form()] = None,
    death_date: Annotated[str | None, Form()] = None,
    disability_type: Annotated[str, Form()] = "",
    disability_level: Annotated[str, Form()] = "",
    disability_certificate: Annotated[str, Form()] = "",
    inclusive_education: Annotated[str, Form()] = "",
    disability_support: Annotated[str, Form()] = "",
    disability_support_details: Annotated[str, Form()] = "",
    special_circumstances: Annotated[str, Form()] = "",
    notes: Annotated[str, Form()] = "",
    finish_household: Annotated[str | None, Form()] = None,
    db: Session = Depends(get_db),

    is_literacy_target: Annotated[str | None, Form()] = None,
    literacy_status: Annotated[str | None, Form()] = None,
    completed_grade_3: Annotated[str | None, Form()] = None,
    completed_grade_5: Annotated[str | None, Form()] = None,
    completed_primary_program: Annotated[str | None, Form()] = None,
    completed_lower_secondary_program: Annotated[str | None, Form()] = None,
    post_lower_secondary_path: Annotated[str | None, Form()] = None,
    study_location_scope: Annotated[str | None, Form()] = None,
    is_repeating_grade: Annotated[str | None, Form()] = None,
    current_education_program: Annotated[str | None, Form()] = None,
    # === BAI_13B_12_V2_1_ATTAINMENT_PARAMS ===
    highest_completed_grade: Annotated[str | None, Form()] = None,
    education_attainment_level: Annotated[str | None, Form()] = None,
):
    survey_form = lay_phieu_ho(
        db=db,
        batch_id=batch_id,
        household_id=household_id,
    )
    person = lay_doi_tuong_trong_ho(
        db=db,
        household_id=household_id,
        person_id=person_id,
    )

    if survey_form is None or person is None:
        return RedirectResponse(
            url=(
                f"/dieu-tra/{batch_id}/ho-dan/"
                f"{household_id}/doi-tuong"
            ),
            status_code=303,
        )

    if not co_quyen_truy_cap_phieu(
        db=db, request=request, survey_form=survey_form
    ):
        return RedirectResponse(
            url=f"/dieu-tra/{batch_id}/ho-dan",
            status_code=303,
        )

    # === BAI_13B_12_V2_4_4_6_MOBILE_WRITE_GUARD_YEAR_START ===
    _mobile_role_code = normalize_role_code(
        lay_thong_tin_nguoi_dung(request).get("role_code")
    )
    if not can_edit_survey_data(_mobile_role_code):
        return RedirectResponse(
            url=f"/dieu-tra/{batch_id}/ho-dan",
            status_code=303,
        )
    if _mobile_role_code == TEACHER_ROLE_CODE:
        school_year_id = int(survey_form.survey_batch.school_year_id)
    # === BAI_13B_12_V2_4_4_6_MOBILE_WRITE_GUARD_YEAR_END ===

    errors: list[str] = []

    if (
        survey_form.survey_batch.status == "DA_KET_THUC"
        or survey_form.survey_batch.is_locked
    ):
        errors.append(
            "Đợt điều tra đã khóa/kết thúc, không thể cập nhật năm học."
        )

    school_year = db.get(SchoolYear, school_year_id)
    if school_year is None:
        errors.append("Năm học không hợp lệ.")

    if learning_status not in LEARNING_STATUS_LABELS:
        errors.append("Tình trạng học tập không hợp lệ.")
    # === BAI_13B_12_V2_1_ATTAINMENT_VALIDATE_START ===
    # Bài V2.3: nếu đang học và có lớp hiện tại thì cho phép suy ra lớp
    # cao nhất đã hoàn thành ở bước sau, sau khi đã xác định selected_class.
    _b1312v21_grade_value = None
    _b1312v21_grade_raw = str(
        highest_completed_grade or ""
    ).strip()

    if _b1312v21_grade_raw:
        try:
            _b1312v21_grade_value = int(
                _b1312v21_grade_raw
            )
        except (TypeError, ValueError):
            errors.append(
                "Lớp cao nhất đã hoàn thành không hợp lệ."
            )
        else:
            if not 0 <= _b1312v21_grade_value <= 12:
                errors.append(
                    "Lớp cao nhất đã hoàn thành phải từ 0 đến 12."
                )
                _b1312v21_grade_value = None

    _b1312v21_level_value = str(
        education_attainment_level
        or "CHUA_XAC_DINH"
    ).strip().upper()

    _b1312v21_allowed_levels = {
        "CHUA_XAC_DINH",
        "CHUA_HOAN_THANH_TIEU_HOC",
        "TIEU_HOC",
        "THCS",
        "THPT",
        "TRUNG_CAP",
        "CAO_DANG",
        "DAI_HOC",
        "SAU_DAI_HOC",
        "KHAC",
    }

    if (
        _b1312v21_level_value
        not in _b1312v21_allowed_levels
    ):
        errors.append(
            "Trình độ học vấn cao nhất không hợp lệ."
        )
        _b1312v21_level_value = "CHUA_XAC_DINH"
    # === BAI_13B_12_V2_1_ATTAINMENT_VALIDATE_END ===

    tri_state_inputs = {
        "completed_preschool_by_age": (
            completed_preschool_by_age,
            "Hoàn thành Chương trình GDMN theo độ tuổi",
        ),
        "completed_preschool_5": (
            completed_preschool_5,
            "Hoàn thành chương trình GDMN 5 tuổi",
        ),
        "attends_required_days": (
            attends_required_days,
            "Đi học đủ ngày theo quy định",
        ),
        "attends_regularly": (
            attends_regularly,
            "Đi học chuyên cần",
        ),
        "prepared_vietnamese": (
            prepared_vietnamese,
            "Chuẩn bị tiếng Việt",
        ),
        "weight_monitored": (
            weight_monitored,
            "Theo dõi cân nặng",
        ),
        "underweight": (
            underweight,
            "Suy dinh dưỡng thể nhẹ cân",
        ),
        "height_monitored": (
            height_monitored,
            "Theo dõi chiều cao",
        ),
        "stunted": (
            stunted,
            "Suy dinh dưỡng thể thấp còi",
        ),
        "attends_two_sessions_per_day": (
            attends_two_sessions_per_day,
            "Học 2 buổi/ngày",
        ),
        "disability_can_learn": (
            disability_can_learn,
            "Khuyết tật có khả năng học tập",
        ),
        "disability_access_education": (
            disability_access_education,
            "Khuyết tật được tiếp cận giáo dục",
        ),
    }
    parsed_tri_state: dict[str, bool | None] = {}
    for field_name, (raw_value, field_label) in tri_state_inputs.items():
        parsed_value, value_error = chuyen_gia_tri_co_khong(
            raw_value,
            field_label,
        )
        parsed_tri_state[field_name] = parsed_value
        if value_error:
            errors.append(value_error)

    completed_preschool_by_age_value = parsed_tri_state[
        "completed_preschool_by_age"
    ]
    completed_preschool_5_value = parsed_tri_state[
        "completed_preschool_5"
    ]

    # Duy trì tương thích dữ liệu cũ: đối với trẻ 5 tuổi, chỉ tiêu mới
    # đồng thời cập nhật trường hoàn thành CT GDMN 5 tuổi. Với trẻ 3-4
    # tuổi, không ghi đè dữ liệu lịch sử của trường cũ.
    reference_date = school_year.start_date if school_year is not None else None
    if reference_date is None and school_year is not None:
        try:
            reference_date = date(int(str(school_year.code).split("-")[-1]), 7, 15)
        except (TypeError, ValueError):
            reference_date = date.today()
    person_age = tinh_tuoi_tai_ngay(person.date_of_birth, reference_date or date.today())
    if person_age == 5:
        completed_preschool_5_value = completed_preschool_by_age_value
    attends_required_days_value = parsed_tri_state[
        "attends_required_days"
    ]
    attends_regularly_value = parsed_tri_state[
        "attends_regularly"
    ]
    prepared_vietnamese_value = parsed_tri_state[
        "prepared_vietnamese"
    ]
    weight_monitored_value = parsed_tri_state[
        "weight_monitored"
    ]
    underweight_value = parsed_tri_state["underweight"]
    height_monitored_value = parsed_tri_state[
        "height_monitored"
    ]
    stunted_value = parsed_tri_state["stunted"]

    # === BAI_13B_11_14_2_REPORT_SAVE_START ===
    disability_can_learn_value = parsed_tri_state.get(
        "disability_can_learn"
    )
    disability_access_education_value = parsed_tri_state.get(
        "disability_access_education"
    )

    if disability_status != "CO_KHUYET_TAT":
        disability_can_learn_value = None
        disability_access_education_value = None
    # === BAI_13B_11_14_2_REPORT_SAVE_END ===

    if disability_status not in DISABILITY_STATUS_LABELS:
        errors.append("Tình trạng khuyết tật không hợp lệ.")

    disability_type = str(disability_type or "").strip()
    disability_level = str(disability_level or "").strip()
    disability_support_details = str(disability_support_details or "").strip()

    if disability_type and disability_type not in DISABILITY_TYPE_LABELS:
        errors.append("Dạng khuyết tật không hợp lệ.")
    if disability_level and disability_level not in DISABILITY_LEVEL_LABELS:
        errors.append("Mức độ khuyết tật không hợp lệ.")

    disability_certificate_value, disability_certificate_error = chuyen_gia_tri_co_khong(
        disability_certificate,
        "Giấy xác nhận khuyết tật",
    )
    inclusive_education_value, inclusive_education_error = chuyen_gia_tri_co_khong(
        inclusive_education,
        "Học hòa nhập",
    )
    disability_support_value, disability_support_error = chuyen_gia_tri_co_khong(
        disability_support,
        "Được hỗ trợ",
    )
    for disability_error in (
        disability_certificate_error,
        inclusive_education_error,
        disability_support_error,
    ):
        if disability_error:
            errors.append(disability_error)

    if disability_status == "CO_KHUYET_TAT":
        if not disability_type:
            errors.append("Trẻ có khuyết tật cần chọn dạng khuyết tật.")
        if not disability_level:
            errors.append("Trẻ có khuyết tật cần chọn mức độ khuyết tật.")
    else:
        disability_type = ""
        disability_level = ""
        disability_certificate_value = None
        inclusive_education_value = None
        disability_support_value = None
        disability_support_details = ""

    if len(disability_support_details) > 2000:
        errors.append("Nội dung hỗ trợ khuyết tật dài quá 2.000 ký tự.")

    parsed_school_id = chuyen_id_tuy_chon(school_id)
    parsed_class_id = chuyen_id_tuy_chon(class_id)

    selected_school = (
        db.get(School, parsed_school_id)
        if parsed_school_id is not None
        else None
    )
    selected_class = (
        db.get(Classroom, parsed_class_id)
        if parsed_class_id is not None
        else None
    )

    if school_id.strip() and parsed_school_id is None:
        errors.append("Trường được chọn không hợp lệ.")
    elif parsed_school_id is not None and selected_school is None:
        errors.append("Không tìm thấy trường được chọn.")

    if class_id.strip() and parsed_class_id is None:
        errors.append("Lớp được chọn không hợp lệ.")
    elif parsed_class_id is not None and selected_class is None:
        errors.append("Không tìm thấy lớp được chọn.")

    if selected_class is not None:
        if selected_school is None:
            errors.append("Cần chọn trường trước khi chọn lớp.")
        elif selected_class.school_id != selected_school.id:
            errors.append("Lớp không thuộc trường đã chọn.")
        elif selected_class.school_year_id != school_year_id:
            errors.append("Lớp không thuộc năm học đã chọn.")

    school_name_reported = chuan_hoa_van_ban(
        school_name_reported
    )
    class_name_reported = chuan_hoa_van_ban(
        class_name_reported
    )
    special_circumstances = special_circumstances.strip()
    notes = notes.strip()

    if selected_school is not None:
        school_name_reported = selected_school.name
    if selected_class is not None:
        class_name_reported = selected_class.name

    # === BAI_13B_12_V2_3_CLASS_TO_ATTAINMENT_START ===
    _b1323_current_class_text = (
        selected_class.name
        if selected_class is not None
        else class_name_reported
    )
    
    # === BAI_13B_12_V2_3_6_PRESCHOOL_GRADE_GUARD_START ===
    _b13236_school_text = " ".join(
        [
            str(
                getattr(selected_school, "name", "")
                if selected_school is not None
                else ""
            ),
            str(school_name_reported or ""),
        ]
    ).casefold()

    _b13236_is_preschool = any(
        token in _b13236_school_text
        for token in (
            "mầm non",
            "mam non",
            "mẫu giáo",
            "mau giao",
            "nhà trẻ",
            "nha tre",
        )
    ) or bool(
        re.search(
            r"(^|\s)mn(\s|$)",
            _b13236_school_text,
            flags=re.IGNORECASE,
        )
    )
    # === BAI_13B_12_V2_3_6_PRESCHOOL_GRADE_GUARD_END ===

# === BAI_13B_12_V2_3_1_GRADE_PARSER_START ===
    _b1323_current_grade = None
    _b13231_class_text = str(
        _b1323_current_class_text or ""
    ).strip()
    _b13231_class_fold = _b13231_class_text.casefold()

    # Không nhầm "5 tuổi" của Mầm non thành lớp 5.
    if (
        "tuổi" not in _b13231_class_fold
        and "tuoi" not in _b13231_class_fold
        and not _b13236_is_preschool
    ):
        _b1323_class_match = re.search(
            r"(?i)\b(?:lớp|lop|khối|khoi)\s*(1[0-2]|[1-9])\b",
            _b13231_class_text,
        )
        if _b1323_class_match is None:
            _b1323_class_match = re.match(
                r"^\s*(1[0-2]|[1-9])"
                r"(?:\s*[A-Za-z]\d*)?\s*$",
                _b13231_class_text,
            )

        if _b1323_class_match:
            _b1323_current_grade = int(
                _b1323_class_match.group(1)
            )
    # === BAI_13B_12_V2_3_1_GRADE_PARSER_END ===

    if (
        learning_status == "DANG_HOC"
        and _b1323_current_grade is not None
    ):
        _b1323_inferred_completed = max(
            0,
            _b1323_current_grade - 1,
        )
        # === BAI_13B_12_V2_3_3_CURRENT_CLASS_SOURCE_START ===
        _b1312v21_grade_value = (
            _b1323_inferred_completed
        )

        if _b1323_current_grade >= 10:
            _b1312v21_level_value = "THCS"
        elif _b1323_current_grade >= 6:
            _b1312v21_level_value = "TIEU_HOC"
        elif _b1323_current_grade >= 1:
            _b1312v21_level_value = (
                "CHUA_HOAN_THANH_TIEU_HOC"
            )
        # === BAI_13B_12_V2_3_3_CURRENT_CLASS_SOURCE_END ===

        # === BAI_13B_12_V2_3_10_EDUCATION_CONSISTENCY_BACKEND_START ===
        # Lớp cao nhất đã hoàn thành là nguồn kiểm soát nhất quán cho
        # trình độ phổ thông. Trình độ nghề/higher education chỉ được
        # giữ khi lớp phổ thông đã đạt ngưỡng hợp lý.
        if _b1312v21_grade_value is not None:
            if _b1312v21_grade_value <= 4:
                _b1312v21_level_value = (
                    "CHUA_HOAN_THANH_TIEU_HOC"
                )
            elif _b1312v21_grade_value <= 8:
                _b1312v21_level_value = "TIEU_HOC"
            elif _b1312v21_grade_value <= 11:
                if _b1312v21_level_value != "TRUNG_CAP":
                    _b1312v21_level_value = "THCS"
            else:
                _b132310_allowed_after_12 = {
                    "THPT",
                    "TRUNG_CAP",
                    "CAO_DANG",
                    "DAI_HOC",
                    "SAU_DAI_HOC",
                    "KHAC",
                }
                if (
                    _b1312v21_level_value
                    not in _b132310_allowed_after_12
                ):
                    _b1312v21_level_value = "THPT"
        # === BAI_13B_12_V2_3_10_EDUCATION_CONSISTENCY_BACKEND_END ===

    # === BAI_13B_12_V2_3_11_XMC_CONSISTENCY_VALIDATE_START ===
    # completed_grade_3/5 vẫn là chỉ báo XMC theo quy tắc cũ và được phép
    # người điều tra lựa chọn. Tuy nhiên khi đã khai báo Lớp cao nhất đã
    # hoàn thành thì không cho lưu tổ hợp mâu thuẫn.
    def _b132311_parse_xmc_bool(raw_value):
        _raw = str(raw_value or "").strip().upper()
        if _raw in {"CO", "1", "TRUE", "YES"}:
            return True
        if _raw in {"KHONG", "0", "FALSE", "NO"}:
            return False
        return None

    _b132311_g3 = _b132311_parse_xmc_bool(completed_grade_3)
    _b132311_g5 = _b132311_parse_xmc_bool(completed_grade_5)

    if _b1312v21_grade_value is not None:
        _b132311_expected_g3 = (_b1312v21_grade_value >= 3)
        _b132311_expected_g5 = (_b1312v21_grade_value >= 5)

        if (
            _b132311_g3 is not None
            and _b132311_g3 != _b132311_expected_g3
        ):
            errors.append(
                "Mâu thuẫn dữ liệu Xóa mù chữ: "
                "Hoàn thành lớp 3 không phù hợp với "
                "Lớp cao nhất đã hoàn thành."
            )

        if (
            _b132311_g5 is not None
            and _b132311_g5 != _b132311_expected_g5
        ):
            errors.append(
                "Mâu thuẫn dữ liệu Xóa mù chữ: "
                "Hoàn thành lớp 5 không phù hợp với "
                "Lớp cao nhất đã hoàn thành."
            )

    if _b132311_g5 is True and _b132311_g3 is False:
        errors.append(
            "Mâu thuẫn dữ liệu Xóa mù chữ: "
            "đã hoàn thành lớp 5 thì phải hoàn thành lớp 3."
        )
    # === BAI_13B_12_V2_3_11_XMC_CONSISTENCY_VALIDATE_END ===

    if _b1312v21_grade_value is None:
        errors.append(
            "Chưa khai báo lớp cao nhất đã hoàn thành."
        )

    if _b1312v21_level_value == "CHUA_XAC_DINH":
        errors.append(
            "Chưa khai báo trình độ học vấn cao nhất."
        )
    # === BAI_13B_12_V2_3_CLASS_TO_ATTAINMENT_END ===

    statuses_requiring_school = {
        "DANG_HOC",
        "CHUYEN_DEN",
        "TAM_NGHI",
    }
    if (
        learning_status in statuses_requiring_school
        and selected_school is None
        and not school_name_reported
    ):
        errors.append(
            "Đối tượng đang học cần chọn trường hoặc nhập tên trường ngoài hệ thống."
        )

    if (
        learning_status == "DANG_HOC"
        and selected_class is None
        and not class_name_reported
    ):
        errors.append(
            "Đối tượng đang học cần chọn lớp hoặc nhập tên lớp theo phiếu."
        )

    if len(school_name_reported) > 300:
        errors.append("Tên trường dài quá 300 ký tự.")
    if len(class_name_reported) > 200:
        errors.append("Tên lớp dài quá 200 ký tự.")

    existing_record = db.scalar(
        select(SurveyPersonYearRecord).where(
            SurveyPersonYearRecord.survey_form_id == survey_form.id,
            SurveyPersonYearRecord.survey_person_id == person_id,
            SurveyPersonYearRecord.school_year_id == school_year_id,
        )
    )

    # === BAI_13B_11_14_3_SAVE_EVENTS_START ===
    _b131143_residency_status = str(
        residency_status or ""
    ).strip().upper()

    if _b131143_residency_status not in {
        "THUONG_TRU",
        "TAM_TRU",
    }:
        errors.append(
            "Cần xác định tình trạng cư trú: "
            "Thường trú hoặc Tạm trú."
        )

    _b131143_move_in_active = b131143_event_checked(
        move_in_active
    )
    _b131143_move_out_active = b131143_event_checked(
        move_out_active
    )
    _b131143_death_active = b131143_event_checked(
        death_active
    )

    _b131143_move_in_date = str(
        move_in_date or ""
    ).strip()
    _b131143_move_in_origin = str(
        move_in_origin or ""
    ).strip()

    _b131143_move_out_date = str(
        move_out_date or ""
    ).strip()
    _b131143_move_out_destination = str(
        move_out_destination or ""
    ).strip()

    _b131143_death_date = str(
        death_date or ""
    ).strip()

    if _b131143_move_in_active:
        if not _b131143_move_in_date:
            errors.append(
                "Chuyển đến: cần nhập ngày chuyển đến."
            )
        if not _b131143_move_in_origin:
            errors.append(
                "Chuyển đến: cần nhập nơi đi."
            )

    if _b131143_move_out_active:
        if not _b131143_move_out_date:
            errors.append(
                "Chuyển đi: cần nhập ngày chuyển đi."
            )
        if not _b131143_move_out_destination:
            errors.append(
                "Chuyển đi: cần nhập nơi đến."
            )

    if _b131143_death_active:
        if not _b131143_death_date:
            errors.append(
                "Tử vong: cần nhập ngày tử vong."
            )
    # === BAI_13B_11_14_3_SAVE_EVENTS_END ===

    if errors:
        school_years = db.scalars(
            select(SchoolYear)
            .order_by(SchoolYear.code.desc(), SchoolYear.id.desc())
        ).all()
        schools = db.scalars(
            select(School)
            .options(selectinload(School.commune))
            .where(School.is_active.is_(True))
            .order_by(School.name.asc())
        ).all()

        form_record = existing_record or SurveyPersonYearRecord(
            survey_form_id=survey_form.id,
            survey_person_id=person.id,
            school_year_id=school_year_id,
            learning_status=learning_status,
        )
        form_record.school_id = parsed_school_id
        form_record.class_id = parsed_class_id
        form_record.school_name_reported = school_name_reported or None
        form_record.class_name_reported = class_name_reported or None
        form_record.learning_status = learning_status
        form_record.completed_preschool_by_age = completed_preschool_by_age_value
        # === BAI_13B_12_V2_3_7_SAVE_TWO_SESSIONS_START ===
        form_record.attends_two_sessions_per_day = parsed_tri_state["attends_two_sessions_per_day"]
        # === BAI_13B_12_V2_3_7_SAVE_TWO_SESSIONS_END ===
        form_record.completed_preschool_5 = completed_preschool_5_value
        form_record.prepared_vietnamese = prepared_vietnamese_value
        form_record.disability_status = disability_status
        form_record.disability_type = disability_type or None
        form_record.disability_level = disability_level or None
        form_record.disability_certificate = disability_certificate_value
        form_record.inclusive_education = inclusive_education_value
        form_record.disability_support = disability_support_value
        form_record.disability_support_details = disability_support_details or None
        form_record.special_circumstances = special_circumstances or None
        form_record.notes = notes or None

        form_record.disability_can_learn = disability_can_learn_value
        form_record.disability_access_education = disability_access_education_value

        return templates.TemplateResponse(
            request=request,
            name="surveys/year_records.html",
            context={
                "nguoi_dung": request.scope.get("auth_user"),
                "survey_form": survey_form,
                "batch": survey_form.survey_batch,
                "household": survey_form.household,
                "person": person,
                "school_years": school_years,
                "schools": schools,
                "selected_school_year_id": school_year_id,
                "selected_record": form_record,
                "selected_record_saved": existing_record is not None,
                "selected_school_id": parsed_school_id,
                "selected_class_id": parsed_class_id,
                "previous_year_hint": lay_goi_y_nam_hoc_truoc(
                    db=db,
                    person_id=person_id,
                    school_year_id=school_year_id,
                ),
                "inherited_fields": [],
                "history_rows": tao_du_lieu_lich_su_nam_hoc(
                    db=db,
                    person_id=person_id,
                    survey_form_id=survey_form.id,
                ),
                "learning_status_labels": LEARNING_STATUS_LABELS,
                "residency_status_labels": RESIDENCY_STATUS_LABELS,
                "disability_status_labels": DISABILITY_STATUS_LABELS,
                "disability_type_labels": DISABILITY_TYPE_LABELS,
                "disability_level_labels": DISABILITY_LEVEL_LABELS,
                "can_edit_data": can_edit_survey_data(
                    lay_thong_tin_nguoi_dung(request).get("role_code")
                ),
                "thong_bao": None,
                "thong_bao_loi": " ".join(errors),
                "year_record_saved": False,
                "next_person_url": None,
                "quick_entry_url": (
                    f"/dieu-tra/{batch_id}/ho-dan/{household_id}/nhap-nhanh#members"
                ),
                "work_url": "/",
            },
            status_code=400,
        )

    record = existing_record
    if record is None:
        record = SurveyPersonYearRecord(
            survey_form_id=survey_form.id,
            survey_person_id=person.id,
            school_year_id=school_year_id,
            learning_status=learning_status,
        )
        db.add(record)

    # === BAI_13B_12_V2_3_8_1_SAVE_TWO_SESSIONS_TO_REAL_RECORD_START ===
    # V2.3.7 gán vào form_record; từ đây record mới là year-record thật.
    record.attends_two_sessions_per_day = parsed_tri_state["attends_two_sessions_per_day"]
    # === BAI_13B_12_V2_3_8_1_SAVE_TWO_SESSIONS_TO_REAL_RECORD_END ===

    record.survey_form_id = survey_form.id
    record.school_id = parsed_school_id
    record.class_id = parsed_class_id
    record.school_name_reported = school_name_reported or None
    record.class_name_reported = class_name_reported or None
    record.learning_status = learning_status
    record.completed_preschool_by_age = completed_preschool_by_age_value
    record.completed_preschool_5 = completed_preschool_5_value
    record.special_circumstances = special_circumstances or None
    record.prepared_vietnamese = prepared_vietnamese_value
    record.disability_status = disability_status
    record.disability_type = disability_type or None
    record.disability_level = disability_level or None
    record.disability_certificate = disability_certificate_value
    record.inclusive_education = inclusive_education_value
    record.disability_support = disability_support_value
    record.disability_support_details = disability_support_details or None
    record.is_reviewed = True
    record.notes = notes or None

    try:
        # === BAI_13B_11_13_2_SAVE_FIELDS_START ===
        def _b131132_optional_bool(value):
            raw = str(value or "").strip().upper()
            if raw in {"CO", "1", "TRUE"}:
                return True
            if raw in {"KHONG", "0", "FALSE"}:
                return False
            return None

        _b131132_is_literacy_target = _b131132_optional_bool(
            is_literacy_target
        )

        record.is_literacy_target = _b131132_is_literacy_target

        # === BAI_13B_11_15_2_4_7_1A_FORCE_XMC_AGE15_START ===
# === BAI_13B_12_V2_3_3_XMC_BIDIRECTIONAL ===
        # Tuổi theo năm điều tra >= 15 => bắt buộc thuộc diện điều tra XMC.
        _b1471a_reference_year = None

        if school_year is not None:
            _b1471a_year_text = str(getattr(school_year, "code", "") or "")
            for _b1471a_token in (
                _b1471a_year_text.replace("/", "-").replace("_", "-").split("-")
            ):
                _b1471a_token = _b1471a_token.strip()
                if len(_b1471a_token) >= 4 and _b1471a_token[:4].isdigit():
                    _b1471a_reference_year = int(_b1471a_token[:4])
                    break

            if (
                _b1471a_reference_year is None
                and getattr(school_year, "start_date", None) is not None
            ):
                _b1471a_reference_year = school_year.start_date.year

        _b1471a_age_by_year = None

        if (
            _b1471a_reference_year is not None
            and getattr(person, "date_of_birth", None) is not None
        ):
            _b1471a_age_by_year = _b1471a_reference_year - person.date_of_birth.year

        if _b1471a_age_by_year is not None:
            _b131132_is_literacy_target = (_b1471a_age_by_year >= 15)
            record.is_literacy_target = _b131132_is_literacy_target
        # === BAI_13B_11_15_2_4_7_1A_FORCE_XMC_AGE15_END ===

        if _b131132_is_literacy_target is True:
            _b131132_literacy_status = str(
                literacy_status or "CHUA_XAC_DINH"
            ).strip().upper()

            if _b131132_literacy_status not in {
                "CHUA_XAC_DINH",
                "KHONG_THUOC_DIEN",
                "THEO_DOI_XMC",
            }:
                _b131132_literacy_status = "CHUA_XAC_DINH"

            record.literacy_status = _b131132_literacy_status
            record.completed_grade_3 = _b131132_optional_bool(
                completed_grade_3
            )
            record.completed_grade_5 = _b131132_optional_bool(
                completed_grade_5
            )
        else:
            # Khi không thuộc đối tượng XMC thì không giữ chỉ báo XMC cũ.
            record.literacy_status = "CHUA_XAC_DINH"
            record.completed_grade_3 = None
            record.completed_grade_5 = None

        # === BAI_13B_12_V2_3_GRADE_TO_XMC_START ===
        # completed_grade_3/5 là hệ quả trực tiếp của lớp cao nhất đã hoàn thành.
        # Người 15+ vẫn thuộc phạm vi ĐIỀU TRA XMC theo quy tắc cũ;
        # đây chỉ tự xác định mức biết chữ, không đổi quy tắc đối tượng.
        if (
            _b131132_is_literacy_target is True
            and _b1312v21_grade_value is not None
        ):
            record.completed_grade_3 = (
                _b1312v21_grade_value >= 3
            )
            record.completed_grade_5 = (
                _b1312v21_grade_value >= 5
            )
        # === BAI_13B_12_V2_3_GRADE_TO_XMC_END ===

        # === BAI_13B_11_15_2_4_7_1B_DERIVE_LITERACY_STATUS_START ===
        # Tình trạng XMC không còn nhập tay.
        # Field literacy_status chỉ giữ để tương thích dữ liệu/lịch sử.
        # Báo cáo lấy trực tiếp completed_grade_3 / completed_grade_5.
        #
        # Quy ước:
        # - Có False lớp 3/lớp 5 -> THEO_DOI_XMC.
        # - Cả lớp 3 và lớp 5 True -> KHONG_THUOC_DIEN
        #   (không thuộc diện THEO DÕI mù chữ; vẫn thuộc diện ĐIỀU TRA).
        # - Còn thiếu -> CHUA_XAC_DINH.
        _b1471b_g3 = record.completed_grade_3
        _b1471b_g5 = record.completed_grade_5

        if _b131132_is_literacy_target is True:
            if _b1471b_g3 is False or _b1471b_g5 is False:
                record.literacy_status = "THEO_DOI_XMC"
            elif _b1471b_g3 is True and _b1471b_g5 is True:
                record.literacy_status = "KHONG_THUOC_DIEN"
            else:
                record.literacy_status = "CHUA_XAC_DINH"
        else:
            record.literacy_status = "CHUA_XAC_DINH"
        # === BAI_13B_11_15_2_4_7_1B_DERIVE_LITERACY_STATUS_END ===

        record.completed_primary_program = _b131132_optional_bool(
            completed_primary_program
        )
        record.completed_lower_secondary_program = _b131132_optional_bool(
            completed_lower_secondary_program
        )

        _b131132_post_path = str(
            post_lower_secondary_path or "CHUA_XAC_DINH"
        ).strip().upper()

        if _b131132_post_path not in {
            "CHUA_XAC_DINH",
            "THPT",
            "GDTX",
            "GDNN",
            "KHONG_HOC",
        }:
            _b131132_post_path = "CHUA_XAC_DINH"

        record.post_lower_secondary_path = _b131132_post_path
        # === BAI_13B_11_13_2_SAVE_FIELDS_END ===
        # === BAI_13B_11_15_2_SAVE_PRIMARY_THCS_FIELDS_START ===
        # Nơi học dùng chung Tiểu học + THCS.
        # === FIX26G_MAIN_SAVE_PRESERVE_START ===
        # Nếu control động không gửi giá trị, không được ghi đè dữ liệu
        # đã được lưu riêng bởi endpoint FIX26G.
        if (
            study_location_scope is not None
            and str(study_location_scope or "").strip()
        ):
            _b1512_location = str(
                study_location_scope
            ).strip().upper()
            # BATCH22_STUDY_LOCATION_SAVE
            if _b1512_location not in {
                "CHUA_XAC_DINH",
                "TAI_CHO",
                "DI_HOC_TRONG_TINH",
                "DI_HOC_NGOAI_TINH",
                "DI_HOC_NOI_KHAC",
                "NOI_KHAC_DEN",
            }:
                _b1512_location = "CHUA_XAC_DINH"
            record.study_location_scope = _b1512_location
        
        # Lưu ban dùng chung Tiểu học + THCS.
        if is_repeating_grade is not None:
            _b1512_repeat = str(
                is_repeating_grade or "CHUA_XAC_DINH"
            ).strip().upper()
            if _b1512_repeat in {"CO", "1", "TRUE"}:
                record.is_repeating_grade = True
            elif _b1512_repeat in {"KHONG", "0", "FALSE"}:
                record.is_repeating_grade = False
            else:
                record.is_repeating_grade = None
        
        # Chương trình hiện tại chỉ do giao diện THCS gửi lên.
        # Khi Tiểu học/nhóm khác không có field này, giữ nguyên dữ liệu.
        if current_education_program is not None:
            _b1512_program = str(
                current_education_program or "CHUA_XAC_DINH"
            ).strip().upper()
            if _b1512_program not in {
                "CHUA_XAC_DINH",
                "THPT",
                "GDTX",
                "GDNN",
                "KHAC",
            }:
                _b1512_program = "CHUA_XAC_DINH"
            record.current_education_program = _b1512_program
        
        # === BAI_13B_12_V2_1_ATTAINMENT_SAVE_START ===
        # Dữ liệu trình độ chung, dùng cho toàn dân.
        # TUYỆT ĐỐI không ghi đè completed_grade_3/5 hoặc literacy_status.
        record.highest_completed_grade = (
            _b1312v21_grade_value
        )
        record.education_attainment_level = (
            _b1312v21_level_value
        )
        # === BAI_13B_12_V2_1_ATTAINMENT_SAVE_END ===

        # Hai trạng thái này tái sử dụng learning_status hiện có.
        _b1512_learning = str(
            learning_status or ""
        ).strip().upper()
        if _b1512_learning in {"BO_HOC", "CHUA_DI_HOC"}:
            record.learning_status = _b1512_learning
        # === BAI_13B_11_15_2_SAVE_PRIMARY_THCS_FIELDS_END ===

        person.residency_status = _b131143_residency_status

        _b131143_survey_form_id = getattr(
            record,
            "survey_form_id",
            None,
        )

        b131143_save_person_event(
            db,
            person_id=person.id,
            school_year_id=school_year_id,
            survey_form_id=_b131143_survey_form_id,
            event_type="MOVE_IN",
            active=_b131143_move_in_active,
            event_date=_b131143_move_in_date,
            origin_location=_b131143_move_in_origin,
        )

        b131143_save_person_event(
            db,
            person_id=person.id,
            school_year_id=school_year_id,
            survey_form_id=_b131143_survey_form_id,
            event_type="MOVE_OUT",
            active=_b131143_move_out_active,
            event_date=_b131143_move_out_date,
            destination_location=_b131143_move_out_destination,
        )

        b131143_save_person_event(
            db,
            person_id=person.id,
            school_year_id=school_year_id,
            survey_form_id=_b131143_survey_form_id,
            event_type="DEATH",
            active=_b131143_death_active,
            event_date=_b131143_death_date,
        )

        # === BAI_13B_12_V2_3_9_AUTO_FINISH_HOUSEHOLD_START ===
        _b13239_household_completed = False
        _b13239_finish_requested = (
            str(finish_household or "").strip() == "1"
            and str(
                lay_thong_tin_nguoi_dung(request).get("role_code") or ""
            ).strip().upper() == "GIAO_VIEN"
        )
        
        if _b13239_finish_requested:
            db.flush()
            _b13239_completion = b131133_danh_gia_do_day_du_phieu_nhap_nhanh(
                db=db,
                survey_form=survey_form,
            )
            _b13239_active = int(_b13239_completion.get("active_people_count", 0) or 0)
            _b13239_missing = int(_b13239_completion.get("missing_year_record_count", 0) or 0)
            _b13239_incomplete = int(_b13239_completion.get("incomplete_year_record_count", 0) or 0)
        
            if _b13239_active > 0 and _b13239_missing == 0 and _b13239_incomplete == 0:
                survey_form.status = "DA_HOAN_THANH"
                if survey_form.survey_date is None:
                    survey_form.survey_date = _b13239_date.today()
                _b13239_head_name = str(
                    getattr(survey_form.household, "head_name", "")
                    or getattr(survey_form, "head_name_snapshot", "")
                    or ""
                ).strip()
                if _b13239_head_name:
                    survey_form.household_representative_name = _b13239_head_name
                if survey_form.household_confirmed_at is None:
                    survey_form.household_confirmed_at = _b13239_datetime.now()
                _b13239_household_completed = True
        # === BAI_13B_12_V2_3_9_AUTO_FINISH_HOUSEHOLD_END ===
        # === FIX26B_FINAL_ASSIGN_BEFORE_COMMIT ===
        if str(disability_can_learn or "").strip():
            record.disability_can_learn = disability_can_learn_value
        if str(disability_access_education or "").strip():
            record.disability_access_education = disability_access_education_value
        # === FIX26G_MAIN_SAVE_PRESERVE_END ===
        db.commit()

        if _b13239_household_completed:
            return RedirectResponse(
                url=(
                    f"/dieu-tra/{batch_id}/ho-dan"
                    f"?school_year_id={school_year_id}"
                    "&status=household_auto_completed"
                ),
                status_code=303,
            )
    except IntegrityError:
        db.rollback()
        return RedirectResponse(
            url=(
                f"/dieu-tra/{batch_id}/ho-dan/{household_id}/"
                f"doi-tuong/{person_id}/nam-hoc?school_year_id="
                f"{school_year_id}"
            ),
            status_code=303,
        )

    return RedirectResponse(
        url=(
            f"/dieu-tra/{batch_id}/ho-dan/{household_id}/"
            f"doi-tuong/{person_id}/nam-hoc?school_year_id="
            f"{school_year_id}&status=year_record_saved"
        ),
        status_code=303,
    )


# === BAI_13B_11_14_3_EVENT_HELPERS_START ===
def b131143_event_checked(value) -> bool:
    return str(value or "").strip().upper() in {
        "1", "TRUE", "ON", "CO", "YES",
    }


def b131143_load_person_events(
    db,
    person_id: int,
    school_year_id: int | None,
) -> dict[str, dict]:
    from sqlalchemy import text as _sa_text

    rows = db.execute(
        _sa_text(
            "SELECT id, event_type, event_date, origin_location, "
            "destination_location, notes "
            "FROM survey_person_events "
            "WHERE survey_person_id = :person_id "
            "AND ((school_year_id = :school_year_id) "
            "OR (school_year_id IS NULL AND :school_year_id IS NULL)) "
            "AND COALESCE(is_active, 1) = 1 "
            "AND event_type IN ('MOVE_IN','MOVE_OUT','DEATH') "
            "ORDER BY id DESC"
        ),
        {
            "person_id": int(person_id),
            "school_year_id": school_year_id,
        },
    ).mappings().all()

    result: dict[str, dict] = {}

    for row in rows:
        event_type = str(
            row.get("event_type") or ""
        ).strip().upper()

        if event_type and event_type not in result:
            result[event_type] = {
                "id": row.get("id"),
                "event_type": event_type,
                "event_date": row.get("event_date"),
                "origin_location": row.get("origin_location"),
                "destination_location": row.get("destination_location"),
                "notes": row.get("notes"),
            }

    return result


def b131143_save_person_event(
    db,
    *,
    person_id: int,
    school_year_id: int | None,
    survey_form_id: int | None,
    event_type: str,
    active: bool,
    event_date: str | None,
    origin_location: str | None = None,
    destination_location: str | None = None,
) -> None:
    from sqlalchemy import text as _sa_text

    event_type = str(event_type or "").strip().upper()

    if event_type not in {"MOVE_IN", "MOVE_OUT", "DEATH"}:
        raise ValueError("Loại biến động không hợp lệ.")

    existing_id = db.execute(
        _sa_text(
            "SELECT id FROM survey_person_events "
            "WHERE survey_person_id = :person_id "
            "AND ((school_year_id = :school_year_id) "
            "OR (school_year_id IS NULL AND :school_year_id IS NULL)) "
            "AND event_type = :event_type "
            "ORDER BY COALESCE(is_active,1) DESC, id DESC LIMIT 1"
        ),
        {
            "person_id": int(person_id),
            "school_year_id": school_year_id,
            "event_type": event_type,
        },
    ).scalar()

    if not active:
        if existing_id is not None:
            db.execute(
                _sa_text(
                    "UPDATE survey_person_events "
                    "SET is_active = 0, updated_at = CURRENT_TIMESTAMP "
                    "WHERE id = :id"
                ),
                {"id": int(existing_id)},
            )
        return

    params = {
        "person_id": int(person_id),
        "school_year_id": school_year_id,
        "survey_form_id": survey_form_id,
        "event_type": event_type,
        "event_date": str(event_date or "").strip() or None,
        "origin_location": (
            str(origin_location or "").strip() or None
        ),
        "destination_location": (
            str(destination_location or "").strip() or None
        ),
    }

    if existing_id is not None:
        params["id"] = int(existing_id)

        db.execute(
            _sa_text(
                "UPDATE survey_person_events SET "
                "survey_form_id=:survey_form_id, "
                "event_date=:event_date, "
                "origin_location=:origin_location, "
                "destination_location=:destination_location, "
                "is_active=1, updated_at=CURRENT_TIMESTAMP "
                "WHERE id=:id"
            ),
            params,
        )
    else:
        db.execute(
            _sa_text(
                "INSERT INTO survey_person_events ("
                "survey_person_id, school_year_id, survey_form_id, "
                "event_type, event_date, origin_location, "
                "destination_location, is_active"
                ") VALUES ("
                ":person_id, :school_year_id, :survey_form_id, "
                ":event_type, :event_date, :origin_location, "
                ":destination_location, 1"
                ")"
            ),
            params,
        )
# === BAI_13B_11_14_3_EVENT_HELPERS_END ===

# === FIX26G_DIRECT_SAVE_INDICATORS_START ===
@router.post(
    "/{batch_id}/ho-dan/{household_id}/doi-tuong/{person_id}/nam-hoc/"
    "luu-chi-bao-nhanh"
)
def fix26g_luu_chi_bao_nhanh(
    request: Request,
    batch_id: int,
    household_id: int,
    person_id: int,
    school_year_id: Annotated[int, Form()],
    study_location_scope: Annotated[str | None, Form()] = None,
    disability_can_learn: Annotated[str | None, Form()] = None,
    disability_access_education: Annotated[str | None, Form()] = None,
    db: Session = Depends(get_db),
):
    survey_form = lay_phieu_ho(
        db=db,
        batch_id=batch_id,
        household_id=household_id,
    )
    person = lay_doi_tuong_trong_ho(
        db=db,
        household_id=household_id,
        person_id=person_id,
    )

    if survey_form is None or person is None:
        return {"ok": False, "message": "Không tìm thấy phiếu hoặc đối tượng."}

    if not co_quyen_truy_cap_phieu(
        db=db,
        request=request,
        survey_form=survey_form,
    ):
        return {"ok": False, "message": "Không có quyền cập nhật phiếu."}

    role_code = normalize_role_code(
        lay_thong_tin_nguoi_dung(request).get("role_code")
    )
    if not can_edit_survey_data(role_code):
        return {"ok": False, "message": "Tài khoản không có quyền cập nhật."}

    if (
        survey_form.survey_batch.status == "DA_KET_THUC"
        or survey_form.survey_batch.is_locked
    ):
        return {"ok": False, "message": "Đợt điều tra đã khóa/kết thúc."}

    if role_code == TEACHER_ROLE_CODE:
        school_year_id = int(survey_form.survey_batch.school_year_id)

    record = db.scalar(
        select(SurveyPersonYearRecord).where(
            SurveyPersonYearRecord.survey_form_id == survey_form.id,
            SurveyPersonYearRecord.survey_person_id == person.id,
            SurveyPersonYearRecord.school_year_id == school_year_id,
        )
    )
    if record is None:
                # === FIX28B_AUTOCREATE_YEAR_RECORD_IN_FIX26G_START ===
        record = SurveyPersonYearRecord(
            survey_form_id=survey_form.id,
            survey_person_id=person.id,
            school_year_id=school_year_id,
            learning_status="CHUA_XAC_DINH",
        )
        db.add(record)
        # === FIX28B_AUTOCREATE_YEAR_RECORD_IN_FIX26G_END ===

    allowed_locations = {
        "CHUA_XAC_DINH",
        "TAI_CHO",
        "DI_HOC_TRONG_TINH",
        "DI_HOC_NGOAI_TINH",
        "DI_HOC_NOI_KHAC",
        "NOI_KHAC_DEN",
    }

    if study_location_scope is not None:
        location = str(study_location_scope or "").strip().upper()
        if not location:
            location = "CHUA_XAC_DINH"
        if location not in allowed_locations:
            return {"ok": False, "message": "Giá trị Nơi học không hợp lệ."}
        record.study_location_scope = location

    def _fix26g_parse_optional_bool(raw_value):
        if raw_value is None:
            return "__NO_CHANGE__"
        raw = str(raw_value or "").strip().upper()
        if raw == "":
            return None
        if raw in {"CO", "1", "TRUE", "YES"}:
            return True
        if raw in {"KHONG", "0", "FALSE", "NO"}:
            return False
        return "__INVALID__"

    can_learn_value = _fix26g_parse_optional_bool(disability_can_learn)
    access_value = _fix26g_parse_optional_bool(disability_access_education)

    if can_learn_value == "__INVALID__":
        return {"ok": False, "message": "Giá trị Có khả năng học tập không hợp lệ."}
    if access_value == "__INVALID__":
        return {"ok": False, "message": "Giá trị Tiếp cận giáo dục không hợp lệ."}

    if str(record.disability_status or "").strip().upper() == "CO_KHUYET_TAT":
        if can_learn_value != "__NO_CHANGE__":
            record.disability_can_learn = can_learn_value
        if access_value != "__NO_CHANGE__":
            record.disability_access_education = access_value
    else:
        record.disability_can_learn = None
        record.disability_access_education = None

    try:
        db.commit()
        db.refresh(record)
    except Exception:
        db.rollback()
        return {
            "ok": False,
            "message": "Không thể lưu chỉ báo. Dữ liệu cũ được giữ nguyên.",
        }

    return {
        "ok": True,
        "message": "Đã lưu",
        "study_location_scope": record.study_location_scope,
        "disability_can_learn": record.disability_can_learn,
        "disability_access_education": record.disability_access_education,
    }

# === FIX26G_DIRECT_SAVE_INDICATORS_END ===
