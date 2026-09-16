from __future__ import annotations

import re
from datetime import date
from math import ceil
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import urlencode

from fastapi import (
    APIRouter,
    Depends,
    Form,
    HTTPException,
    Request,
)
from fastapi.responses import (
    HTMLResponse,
    RedirectResponse,
)
from fastapi.templating import Jinja2Templates
from sqlalchemy import (
    func,
    or_,
    select,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import (
    Session,
    selectinload,
)

from app.database import get_db
from app.models import (
    Classroom,
    Commune,
    School,
    SchoolYear,
    Student,
    StudentEnrollment,
)


# =========================================================
# THIẾT LẬP CHUNG
# =========================================================

APP_DIR = Path(__file__).resolve().parent.parent

templates = Jinja2Templates(
    directory=str(APP_DIR / "templates")
)

router = APIRouter(
    prefix="/hoc-sinh",
    tags=["Quản lý học sinh"],
)

PAGE_SIZE = 20


STATUS_MESSAGES = {
    "created": "Đã thêm học sinh mới thành công.",
}


STATUS_LABELS = {
    "DANG_HOC": "Đang học",
    "CHUYEN_DEN_KY_1": "Chuyển đến kỳ 1",
    "CHUYEN_DEN_KY_2": "Chuyển đến kỳ 2",
    "TAM_NGHI": "Tạm nghỉ",
    "CHUYEN_DI": "Chuyển đi",
    "THOI_HOC": "Thôi học",
}


ALLOWED_ENROLLMENT_STATUSES = set(
    STATUS_LABELS.keys()
)


# =========================================================
# HÀM CHUẨN HÓA
# =========================================================


def chuan_hoa_van_ban(value: str) -> str:
    """Xóa khoảng trắng thừa trong văn bản."""

    return " ".join(value.strip().split())



def chuan_hoa_ma(value: str) -> str:
    """Chuẩn hóa mã học sinh và số định danh."""

    return re.sub(
        r"\s+",
        "",
        value.strip(),
    ).upper()



def chuan_hoa_so_dien_thoai(
    value: str,
) -> str | None:
    """Giữ số điện thoại dưới dạng văn bản."""

    value = re.sub(
        r"\s+",
        "",
        value.strip(),
    )

    if not value:
        return None

    return value



def chuyen_id(
    value: str | int | None,
) -> int | None:
    """Chuyển giá trị biểu mẫu hoặc query thành ID số nguyên."""

    if value is None:
        return None

    if isinstance(value, int):
        return value

    value = value.strip()

    if not value:
        return None

    try:
        return int(value)
    except ValueError:
        return None



def chuyen_ngay(
    value: str,
) -> tuple[date | None, str | None]:
    """Chuyển ngày theo định dạng YYYY-MM-DD."""

    value = value.strip()

    if not value:
        return None, "Ngày sinh không được để trống."

    try:
        result = date.fromisoformat(value)
    except ValueError:
        return None, "Ngày sinh không đúng định dạng."

    if result > date.today():
        return None, (
            "Ngày sinh không được lớn hơn ngày hiện tại."
        )

    return result, None



def chuyen_nam_sinh(
    value: str,
    ten_truong_du_lieu: str,
) -> tuple[int | None, str | None]:
    """Chuyển năm sinh cha hoặc mẹ thành số nguyên."""

    value = value.strip()

    if not value:
        return None, None

    if not value.isdigit():
        return None, (
            f"{ten_truong_du_lieu} phải là số."
        )

    year = int(value)
    current_year = date.today().year

    if year < 1900 or year > current_year:
        return None, (
            f"{ten_truong_du_lieu} không hợp lệ."
        )

    return year, None


# =========================================================
# TRUY VẤN DANH MỤC PHỤ THUỘC
# =========================================================


def lay_nam_hoc(
    db: Session,
) -> list[SchoolYear]:
    """Lấy các năm học đang hoạt động."""

    return db.scalars(
        select(SchoolYear)
        .where(
            SchoolYear.is_active.is_(True)
        )
        .order_by(
            SchoolYear.code.desc()
        )
    ).all()



def lay_xa(
    db: Session,
) -> list[Commune]:
    """Lấy các xã đang hoạt động."""

    return db.scalars(
        select(Commune)
        .where(
            Commune.is_active.is_(True)
        )
        .order_by(
            Commune.name.asc()
        )
    ).all()



def lay_truong_theo_xa(
    db: Session,
    commune_id: int | None,
) -> list[School]:
    """Lấy các trường đang hoạt động thuộc một xã."""

    if commune_id is None:
        return []

    return db.scalars(
        select(School)
        .options(
            selectinload(School.commune)
        )
        .where(
            School.commune_id == commune_id,
            School.is_active.is_(True),
        )
        .order_by(
            School.name.asc()
        )
    ).all()



def lay_lop_theo_truong(
    db: Session,
    school_year_id: int | None,
    school_id: int | None,
) -> list[Classroom]:
    """Lấy lớp theo đúng năm học và trường."""

    if (
        school_year_id is None
        or school_id is None
    ):
        return []

    return db.scalars(
        select(Classroom)
        .where(
            Classroom.school_year_id
            == school_year_id,
            Classroom.school_id == school_id,
            Classroom.is_active.is_(True),
        )
        .order_by(
            Classroom.name.asc()
        )
    ).all()



def xac_dinh_nam_hoc_mac_dinh(
    school_years: list[SchoolYear],
) -> int | None:
    """Chọn năm học đang hoạt động đầu tiên."""

    if not school_years:
        return None

    active_year = next(
        (
            item
            for item in school_years
            if item.is_active
        ),
        school_years[0],
    )

    return active_year.id



def chuan_bi_lua_chon_bieu_mau(
    db: Session,
    school_year_id: int | None,
    commune_id: int | None,
    school_id: int | None,
    class_id: int | None,
) -> tuple[
    list[SchoolYear],
    list[Commune],
    list[School],
    list[Classroom],
    int | None,
    int | None,
    int | None,
    int | None,
]:
    """
    Chuẩn bị lựa chọn theo đúng thứ tự:
    năm học -> xã -> trường -> lớp.
    """

    school_years = lay_nam_hoc(db)
    communes = lay_xa(db)

    valid_year_ids = {
        item.id
        for item in school_years
    }

    if school_year_id not in valid_year_ids:
        school_year_id = (
            xac_dinh_nam_hoc_mac_dinh(
                school_years
            )
        )

    valid_commune_ids = {
        item.id
        for item in communes
    }

    if commune_id not in valid_commune_ids:
        commune_id = None

    schools = lay_truong_theo_xa(
        db,
        commune_id,
    )

    valid_school_ids = {
        item.id
        for item in schools
    }

    if school_id not in valid_school_ids:
        school_id = None

    classrooms = lay_lop_theo_truong(
        db,
        school_year_id,
        school_id,
    )

    valid_class_ids = {
        item.id
        for item in classrooms
    }

    if class_id not in valid_class_ids:
        class_id = None

    return (
        school_years,
        communes,
        schools,
        classrooms,
        school_year_id,
        commune_id,
        school_id,
        class_id,
    )


# =========================================================
# HÀM TẠO URL
# =========================================================


def tao_url_trang(
    page_number: int,
    q: str,
    school_year_id: int | None,
    commune_id: int | None,
    school_id: int | None,
    class_id: int | None,
) -> str:
    """Tạo URL phân trang và giữ nguyên bộ lọc."""

    parameters: dict[str, str | int] = {
        "page": page_number,
    }

    if q:
        parameters["q"] = q

    if school_year_id is not None:
        parameters["school_year_id"] = school_year_id

    if commune_id is not None:
        parameters["commune_id"] = commune_id

    if school_id is not None:
        parameters["school_id"] = school_id

    if class_id is not None:
        parameters["class_id"] = class_id

    return "/hoc-sinh?" + urlencode(parameters)



def tao_url_them(
    school_year_id: int | None,
    commune_id: int | None,
    school_id: int | None,
    class_id: int | None,
) -> str:
    """Mở trang thêm và giữ lựa chọn hiện tại."""

    parameters: dict[str, int] = {}

    if school_year_id is not None:
        parameters["school_year_id"] = school_year_id

    if commune_id is not None:
        parameters["commune_id"] = commune_id

    if school_id is not None:
        parameters["school_id"] = school_id

    if class_id is not None:
        parameters["class_id"] = class_id

    if not parameters:
        return "/hoc-sinh/them"

    return (
        "/hoc-sinh/them?"
        + urlencode(parameters)
    )


# =========================================================
# API PHỤ THUỘC: XÃ -> TRƯỜNG -> LỚP
# =========================================================


@router.get("/api/truong")
def api_danh_sach_truong(
    commune_id: int,
    db: Session = Depends(get_db),
) -> list[dict[str, str | int]]:
    """Trả về danh sách trường thuộc xã đã chọn."""

    commune = db.get(
        Commune,
        commune_id,
    )

    if (
        commune is None
        or not commune.is_active
    ):
        raise HTTPException(
            status_code=404,
            detail="Không tìm thấy xã.",
        )

    schools = lay_truong_theo_xa(
        db,
        commune_id,
    )

    return [
        {
            "id": school.id,
            "code": school.code,
            "name": school.name,
        }
        for school in schools
    ]


@router.get("/api/lop")
def api_danh_sach_lop(
    school_year_id: int,
    school_id: int,
    db: Session = Depends(get_db),
) -> list[dict[str, str | int]]:
    """Trả về danh sách lớp thuộc trường và năm học."""

    school_year = db.get(
        SchoolYear,
        school_year_id,
    )

    school = db.get(
        School,
        school_id,
    )

    if (
        school_year is None
        or not school_year.is_active
    ):
        raise HTTPException(
            status_code=404,
            detail="Không tìm thấy năm học.",
        )

    if (
        school is None
        or not school.is_active
    ):
        raise HTTPException(
            status_code=404,
            detail="Không tìm thấy trường.",
        )

    classrooms = lay_lop_theo_truong(
        db,
        school_year_id,
        school_id,
    )

    return [
        {
            "id": classroom.id,
            "name": classroom.name,
        }
        for classroom in classrooms
    ]


# =========================================================
# DANH SÁCH HỌC SINH
# =========================================================


@router.get(
    "",
    response_class=HTMLResponse,
)
def danh_sach_hoc_sinh(
    request: Request,
    q: str = "",
    school_year_id: str | None = None,
    commune_id: str | None = None,
    school_id: str | None = None,
    class_id: str | None = None,
    page: int = 1,
    status: str | None = None,
    db: Session = Depends(get_db),
):
    """Hiển thị danh sách học sinh có lọc và phân trang."""

    q = q.strip()[:100]
    school_year_id = chuyen_id(school_year_id)
    commune_id = chuyen_id(commune_id)
    school_id = chuyen_id(school_id)
    class_id = chuyen_id(class_id)

    (
        school_years,
        communes,
        schools,
        classrooms,
        school_year_id,
        commune_id,
        school_id,
        class_id,
    ) = chuan_bi_lua_chon_bieu_mau(
        db=db,
        school_year_id=school_year_id,
        commune_id=commune_id,
        school_id=school_id,
        class_id=class_id,
    )

    filters = []

    if school_year_id is not None:
        filters.append(
            StudentEnrollment.school_year_id
            == school_year_id
        )

    if commune_id is not None:
        filters.append(
            School.commune_id == commune_id
        )

    if school_id is not None:
        filters.append(
            StudentEnrollment.school_id
            == school_id
        )

    if class_id is not None:
        filters.append(
            StudentEnrollment.class_id
            == class_id
        )

    if q:
        search_value = f"%{q}%"

        filters.append(
            or_(
                Student.code.ilike(
                    search_value
                ),
                Student.full_name.ilike(
                    search_value
                ),
                Student.contact_phone.ilike(
                    search_value
                ),
                Student.personal_id.ilike(
                    search_value
                ),
            )
        )

    total_records = db.scalar(
        select(
            func.count(
                StudentEnrollment.id
            )
        )
        .join(
            Student,
            Student.id
            == StudentEnrollment.student_id,
        )
        .join(
            School,
            School.id
            == StudentEnrollment.school_id,
        )
        .where(*filters)
    )

    total_records = int(
        total_records or 0
    )

    total_pages = max(
        1,
        ceil(
            total_records / PAGE_SIZE
        ),
    )

    page = max(1, page)
    page = min(page, total_pages)

    offset = (
        page - 1
    ) * PAGE_SIZE

    enrollments = db.scalars(
        select(StudentEnrollment)
        .join(
            Student,
            Student.id
            == StudentEnrollment.student_id,
        )
        .join(
            School,
            School.id
            == StudentEnrollment.school_id,
        )
        .options(
            selectinload(
                StudentEnrollment.student
            ),
            selectinload(
                StudentEnrollment.school
            ).selectinload(
                School.commune
            ),
            selectinload(
                StudentEnrollment.classroom
            ),
            selectinload(
                StudentEnrollment.school_year
            ),
        )
        .where(*filters)
        .order_by(
            Student.full_name.asc(),
            Student.code.asc(),
        )
        .offset(offset)
        .limit(PAGE_SIZE)
    ).all()

    start_page = max(
        1,
        page - 2,
    )

    end_page = min(
        total_pages,
        page + 2,
    )

    page_links = []

    for page_number in range(
        start_page,
        end_page + 1,
    ):
        page_links.append(
            {
                "number": page_number,
                "url": tao_url_trang(
                    page_number=page_number,
                    q=q,
                    school_year_id=(
                        school_year_id
                    ),
                    commune_id=commune_id,
                    school_id=school_id,
                    class_id=class_id,
                ),
                "active": (
                    page_number == page
                ),
            }
        )

    previous_url = None

    if page > 1:
        previous_url = tao_url_trang(
            page_number=page - 1,
            q=q,
            school_year_id=(
                school_year_id
            ),
            commune_id=commune_id,
            school_id=school_id,
            class_id=class_id,
        )

    next_url = None

    if page < total_pages:
        next_url = tao_url_trang(
            page_number=page + 1,
            q=q,
            school_year_id=(
                school_year_id
            ),
            commune_id=commune_id,
            school_id=school_id,
            class_id=class_id,
        )

    return templates.TemplateResponse(
        request=request,
        name="students/list.html",
        context={
            "nguoi_dung": request.scope.get(
                "auth_user"
            ),
            "enrollments": enrollments,
            "school_years": school_years,
            "communes": communes,
            "schools": schools,
            "classrooms": classrooms,
            "q": q,
            "selected_school_year_id": (
                school_year_id
            ),
            "selected_commune_id": (
                commune_id
            ),
            "selected_school_id": school_id,
            "selected_class_id": class_id,
            "page": page,
            "page_size": PAGE_SIZE,
            "total_records": total_records,
            "total_pages": total_pages,
            "page_links": page_links,
            "previous_url": previous_url,
            "next_url": next_url,
            "create_url": tao_url_them(
                school_year_id=school_year_id,
                commune_id=commune_id,
                school_id=school_id,
                class_id=class_id,
            ),
            "thong_bao": (
                STATUS_MESSAGES.get(status)
            ),
            "trang_thai": status,
            "status_labels": STATUS_LABELS,
        },
    )


# =========================================================
# BIỂU MẪU THÊM HỌC SINH
# =========================================================


def hien_thi_form_them(
    request: Request,
    db: Session,
    thong_bao: str | None = None,
    form_data: dict[str, Any] | None = None,
):
    """Hiển thị biểu mẫu thêm học sinh."""

    if form_data is None:
        form_data = {
            "school_year_id": None,
            "commune_id": None,
            "school_id": None,
            "class_id": None,
            "ten_lop_moi": "",
            "ma_hoc_sinh": "",
            "ho_ten": "",
            "ngay_sinh": "",
            "gioi_tinh": "",
            "dan_toc": "",
            "noi_sinh": "",
            "dia_chi_thuong_tru": "",
            "cho_o_hien_nay": "",
            "ten_cha": "",
            "nam_sinh_cha": "",
            "nghe_nghiep_cha": "",
            "ten_me": "",
            "nam_sinh_me": "",
            "nghe_nghiep_me": "",
            "so_dien_thoai": "",
            "so_dinh_danh": "",
            "loai_khuyet_tat": "",
            "ghi_chu": "",
            "trang_thai": "DANG_HOC",
        }

    (
        school_years,
        communes,
        schools,
        classrooms,
        school_year_id,
        commune_id,
        school_id,
        class_id,
    ) = chuan_bi_lua_chon_bieu_mau(
        db=db,
        school_year_id=form_data.get(
            "school_year_id"
        ),
        commune_id=form_data.get(
            "commune_id"
        ),
        school_id=form_data.get(
            "school_id"
        ),
        class_id=form_data.get(
            "class_id"
        ),
    )

    form_data["school_year_id"] = (
        school_year_id
    )
    form_data["commune_id"] = commune_id
    form_data["school_id"] = school_id
    form_data["class_id"] = class_id

    return templates.TemplateResponse(
        request=request,
        name="students/create.html",
        context={
            "nguoi_dung": request.scope.get(
                "auth_user"
            ),
            "school_years": school_years,
            "communes": communes,
            "schools": schools,
            "classrooms": classrooms,
            "form_data": form_data,
            "thong_bao": thong_bao,
            "status_labels": STATUS_LABELS,
        },
    )


@router.get(
    "/them",
    response_class=HTMLResponse,
)
def form_them_hoc_sinh(
    request: Request,
    school_year_id: str | None = None,
    commune_id: str | None = None,
    school_id: str | None = None,
    class_id: str | None = None,
    db: Session = Depends(get_db),
):
    """Hiển thị trang thêm học sinh."""

    school_year_id = chuyen_id(school_year_id)
    commune_id = chuyen_id(commune_id)
    school_id = chuyen_id(school_id)
    class_id = chuyen_id(class_id)

    form_data = {
        "school_year_id": school_year_id,
        "commune_id": commune_id,
        "school_id": school_id,
        "class_id": class_id,
        "ten_lop_moi": "",
        "ma_hoc_sinh": "",
        "ho_ten": "",
        "ngay_sinh": "",
        "gioi_tinh": "",
        "dan_toc": "",
        "noi_sinh": "",
        "dia_chi_thuong_tru": "",
        "cho_o_hien_nay": "",
        "ten_cha": "",
        "nam_sinh_cha": "",
        "nghe_nghiep_cha": "",
        "ten_me": "",
        "nam_sinh_me": "",
        "nghe_nghiep_me": "",
        "so_dien_thoai": "",
        "so_dinh_danh": "",
        "loai_khuyet_tat": "",
        "ghi_chu": "",
        "trang_thai": "DANG_HOC",
    }

    return hien_thi_form_them(
        request=request,
        db=db,
        form_data=form_data,
    )


# =========================================================
# LƯU HỌC SINH MỚI
# =========================================================


@router.post("/them")
def them_hoc_sinh(
    request: Request,
    school_year_id: Annotated[
        int,
        Form(),
    ],
    commune_id: Annotated[
        int,
        Form(),
    ],
    school_id: Annotated[
        int,
        Form(),
    ],
    ma_hoc_sinh: Annotated[
        str,
        Form(),
    ],
    ho_ten: Annotated[
        str,
        Form(),
    ],
    ngay_sinh: Annotated[
        str,
        Form(),
    ],
    gioi_tinh: Annotated[
        str,
        Form(),
    ],
    class_id: Annotated[
        str,
        Form(),
    ] = "",
    ten_lop_moi: Annotated[
        str,
        Form(),
    ] = "",
    dan_toc: Annotated[
        str,
        Form(),
    ] = "",
    noi_sinh: Annotated[
        str,
        Form(),
    ] = "",
    dia_chi_thuong_tru: Annotated[
        str,
        Form(),
    ] = "",
    cho_o_hien_nay: Annotated[
        str,
        Form(),
    ] = "",
    ten_cha: Annotated[
        str,
        Form(),
    ] = "",
    nam_sinh_cha: Annotated[
        str,
        Form(),
    ] = "",
    nghe_nghiep_cha: Annotated[
        str,
        Form(),
    ] = "",
    ten_me: Annotated[
        str,
        Form(),
    ] = "",
    nam_sinh_me: Annotated[
        str,
        Form(),
    ] = "",
    nghe_nghiep_me: Annotated[
        str,
        Form(),
    ] = "",
    so_dien_thoai: Annotated[
        str,
        Form(),
    ] = "",
    so_dinh_danh: Annotated[
        str,
        Form(),
    ] = "",
    loai_khuyet_tat: Annotated[
        str,
        Form(),
    ] = "",
    ghi_chu: Annotated[
        str,
        Form(),
    ] = "",
    trang_thai: Annotated[
        str,
        Form(),
    ] = "DANG_HOC",
    db: Session = Depends(get_db),
):
    """Kiểm tra và lưu học sinh mới."""

    form_data = {
        "school_year_id": school_year_id,
        "commune_id": commune_id,
        "school_id": school_id,
        "class_id": chuyen_id(class_id),
        "ten_lop_moi": ten_lop_moi,
        "ma_hoc_sinh": ma_hoc_sinh,
        "ho_ten": ho_ten,
        "ngay_sinh": ngay_sinh,
        "gioi_tinh": gioi_tinh,
        "dan_toc": dan_toc,
        "noi_sinh": noi_sinh,
        "dia_chi_thuong_tru": (
            dia_chi_thuong_tru
        ),
        "cho_o_hien_nay": (
            cho_o_hien_nay
        ),
        "ten_cha": ten_cha,
        "nam_sinh_cha": nam_sinh_cha,
        "nghe_nghiep_cha": (
            nghe_nghiep_cha
        ),
        "ten_me": ten_me,
        "nam_sinh_me": nam_sinh_me,
        "nghe_nghiep_me": (
            nghe_nghiep_me
        ),
        "so_dien_thoai": so_dien_thoai,
        "so_dinh_danh": so_dinh_danh,
        "loai_khuyet_tat": (
            loai_khuyet_tat
        ),
        "ghi_chu": ghi_chu,
        "trang_thai": trang_thai,
    }

    errors: list[str] = []

    ma_hoc_sinh = chuan_hoa_ma(
        ma_hoc_sinh
    )

    ho_ten = chuan_hoa_van_ban(
        ho_ten
    )

    ten_lop_moi = chuan_hoa_van_ban(
        ten_lop_moi
    )

    gioi_tinh = chuan_hoa_van_ban(
        gioi_tinh
    )

    dan_toc = chuan_hoa_van_ban(
        dan_toc
    )

    noi_sinh = chuan_hoa_van_ban(
        noi_sinh
    )

    dia_chi_thuong_tru = (
        chuan_hoa_van_ban(
            dia_chi_thuong_tru
        )
    )

    cho_o_hien_nay = (
        chuan_hoa_van_ban(
            cho_o_hien_nay
        )
    )

    ten_cha = chuan_hoa_van_ban(
        ten_cha
    )

    nghe_nghiep_cha = (
        chuan_hoa_van_ban(
            nghe_nghiep_cha
        )
    )

    ten_me = chuan_hoa_van_ban(
        ten_me
    )

    nghe_nghiep_me = (
        chuan_hoa_van_ban(
            nghe_nghiep_me
        )
    )

    so_dinh_danh = chuan_hoa_ma(
        so_dinh_danh
    )

    loai_khuyet_tat = (
        chuan_hoa_van_ban(
            loai_khuyet_tat
        )
    )

    ghi_chu = ghi_chu.strip()

    contact_phone = (
        chuan_hoa_so_dien_thoai(
            so_dien_thoai
        )
    )

    if not ma_hoc_sinh:
        errors.append(
            "Mã học sinh không được để trống."
        )

    if len(ma_hoc_sinh) > 50:
        errors.append(
            "Mã học sinh dài quá 50 ký tự."
        )

    if not ho_ten:
        errors.append(
            "Họ và tên không được để trống."
        )

    if len(ho_ten) > 200:
        errors.append(
            "Họ và tên dài quá 200 ký tự."
        )

    if gioi_tinh not in {
        "Nam",
        "Nữ",
        "Khác",
    }:
        errors.append(
            "Giới tính không hợp lệ."
        )

    if (
        trang_thai
        not in ALLOWED_ENROLLMENT_STATUSES
    ):
        errors.append(
            "Trạng thái học tập không hợp lệ."
        )

    date_of_birth, date_error = (
        chuyen_ngay(ngay_sinh)
    )

    if date_error:
        errors.append(date_error)

    father_birth_year, father_error = (
        chuyen_nam_sinh(
            nam_sinh_cha,
            "Năm sinh cha",
        )
    )

    if father_error:
        errors.append(father_error)

    mother_birth_year, mother_error = (
        chuyen_nam_sinh(
            nam_sinh_me,
            "Năm sinh mẹ",
        )
    )

    if mother_error:
        errors.append(mother_error)

    school_year = db.get(
        SchoolYear,
        school_year_id,
    )

    if (
        school_year is None
        or not school_year.is_active
    ):
        errors.append(
            "Năm học được chọn không hợp lệ."
        )

    commune = db.get(
        Commune,
        commune_id,
    )

    if (
        commune is None
        or not commune.is_active
    ):
        errors.append(
            "Xã được chọn không hợp lệ."
        )

    school = db.get(
        School,
        school_id,
    )

    if (
        school is None
        or not school.is_active
    ):
        errors.append(
            "Trường được chọn không hợp lệ."
        )
    elif school.commune_id != commune_id:
        errors.append(
            "Trường không thuộc xã đã chọn."
        )

    selected_class_id = (
        chuyen_id(class_id)
    )

    if (
        class_id.strip()
        and selected_class_id is None
    ):
        errors.append(
            "Lớp được chọn không hợp lệ."
        )

    if (
        selected_class_id is not None
        and ten_lop_moi
    ):
        errors.append(
            "Chỉ chọn lớp hiện có hoặc nhập lớp mới, "
            "không thực hiện đồng thời cả hai."
        )

    if (
        selected_class_id is None
        and not ten_lop_moi
    ):
        errors.append(
            "Bạn cần chọn lớp hoặc nhập tên lớp mới."
        )

    classroom: Classroom | None = None

    if selected_class_id is not None:
        classroom = db.get(
            Classroom,
            selected_class_id,
        )

        if classroom is None:
            errors.append(
                "Không tìm thấy lớp được chọn."
            )
        elif (
            classroom.school_id != school_id
            or classroom.school_year_id
            != school_year_id
        ):
            errors.append(
                "Lớp không thuộc đúng trường "
                "hoặc năm học đã chọn."
            )
        elif not classroom.is_active:
            errors.append(
                "Lớp được chọn đã bị khóa."
            )

    existing_student = db.scalar(
        select(Student).where(
            Student.code == ma_hoc_sinh
        )
    )

    if existing_student is not None:
        errors.append(
            "Mã học sinh đã tồn tại trong hệ thống."
        )

    if so_dinh_danh:
        existing_personal_id = db.scalar(
            select(Student).where(
                Student.personal_id
                == so_dinh_danh
            )
        )

        if existing_personal_id is not None:
            errors.append(
                "Số định danh cá nhân đã được sử dụng "
                "cho một học sinh khác."
            )

    if errors:
        return hien_thi_form_them(
            request=request,
            db=db,
            thong_bao=" ".join(errors),
            form_data=form_data,
        )

    try:
        if (
            classroom is None
            and ten_lop_moi
        ):
            classroom = db.scalar(
                select(Classroom).where(
                    Classroom.school_id
                    == school_id,
                    Classroom.school_year_id
                    == school_year_id,
                    func.lower(
                        Classroom.name
                    )
                    == ten_lop_moi.lower(),
                )
            )

            if classroom is None:
                classroom = Classroom(
                    school_id=school_id,
                    school_year_id=(
                        school_year_id
                    ),
                    code=None,
                    name=ten_lop_moi,
                    is_active=True,
                )

                db.add(classroom)
                db.flush()

            elif not classroom.is_active:
                classroom.is_active = True

        student = Student(
            code=ma_hoc_sinh,
            full_name=ho_ten,
            date_of_birth=date_of_birth,
            gender=gioi_tinh,
            ethnic_group=dan_toc or None,
            birth_place=noi_sinh or None,
            permanent_address=(
                dia_chi_thuong_tru or None
            ),
            current_address=(
                cho_o_hien_nay or None
            ),
            father_name=ten_cha or None,
            father_birth_year=(
                father_birth_year
            ),
            father_job=(
                nghe_nghiep_cha or None
            ),
            mother_name=ten_me or None,
            mother_birth_year=(
                mother_birth_year
            ),
            mother_job=(
                nghe_nghiep_me or None
            ),
            contact_phone=contact_phone,
            personal_id=(
                so_dinh_danh or None
            ),
            disability_type=(
                loai_khuyet_tat or None
            ),
            notes=ghi_chu or None,
            is_active=True,
        )

        db.add(student)
        db.flush()

        enrollment = StudentEnrollment(
            student_id=student.id,
            school_year_id=(
                school_year_id
            ),
            school_id=school_id,
            class_id=classroom.id,
            status=trang_thai,
            enrollment_date=date.today(),
            transfer_date=None,
            is_current=True,
        )

        db.add(enrollment)
        db.commit()

    except IntegrityError:
        db.rollback()

        return hien_thi_form_them(
            request=request,
            db=db,
            thong_bao=(
                "Không thể lưu học sinh. "
                "Mã học sinh hoặc dữ liệu liên quan "
                "có thể đã tồn tại."
            ),
            form_data=form_data,
        )

    return RedirectResponse(
        url=(
            "/hoc-sinh?"
            + urlencode(
                {
                    "school_year_id": (
                        school_year_id
                    ),
                    "commune_id": commune_id,
                    "school_id": school_id,
                    "class_id": classroom.id,
                    "status": "created",
                }
            )
        ),
        status_code=303,
    )
