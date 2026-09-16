from __future__ import annotations

from math import ceil
from pathlib import Path
from urllib.parse import urlencode

from fastapi import (
    APIRouter,
    Depends,
    Request,
)
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import (
    func,
    or_,
    select,
)
from sqlalchemy.orm import (
    Session,
    selectinload,
)

from app.database import get_db
from app.models import (
    Classroom,
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


# =========================================================
# TẠO ĐỊA CHỈ CHUYỂN TRANG
# =========================================================

def tao_url_trang(
    page_number: int,
    q: str,
    school_year_id: int | None,
    school_id: int | None,
    class_id: int | None,
) -> str:
    """
    Tạo URL chuyển trang nhưng vẫn giữ nguyên
    từ khóa và các điều kiện lọc hiện tại.
    """

    parameters: dict[str, str | int] = {
        "page": page_number,
    }

    if q:
        parameters["q"] = q

    if school_year_id is not None:
        parameters["school_year_id"] = (
            school_year_id
        )

    if school_id is not None:
        parameters["school_id"] = school_id

    if class_id is not None:
        parameters["class_id"] = class_id

    return (
        "/hoc-sinh?"
        + urlencode(parameters)
    )


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
    school_year_id: int | None = None,
    school_id: int | None = None,
    class_id: int | None = None,
    page: int = 1,
    db: Session = Depends(get_db),
):
    """
    Hiển thị danh sách học sinh.

    Chức năng:
    - Tìm theo mã học sinh.
    - Tìm theo họ tên.
    - Tìm theo số điện thoại.
    - Lọc theo năm học.
    - Lọc theo trường.
    - Lọc theo lớp.
    - Phân trang 20 học sinh mỗi trang.
    """

    q = q.strip()[:100]

    # -----------------------------------------------------
    # DANH SÁCH NĂM HỌC
    # -----------------------------------------------------

    statement_school_years = (
        select(SchoolYear)
        .order_by(
            SchoolYear.is_active.desc(),
            SchoolYear.code.desc(),
        )
    )

    school_years = db.scalars(
        statement_school_years
    ).all()

    valid_school_year_ids = {
        item.id
        for item in school_years
    }

    if (
        school_year_id
        not in valid_school_year_ids
    ):
        school_year_id = None

    # Nếu chưa chọn năm học,
    # tự chọn năm học đang hoạt động.
    if (
        school_year_id is None
        and school_years
    ):
        active_school_year = next(
            (
                item
                for item in school_years
                if item.is_active
            ),
            school_years[0],
        )

        school_year_id = (
            active_school_year.id
        )

    # -----------------------------------------------------
    # DANH SÁCH TRƯỜNG CÓ HỌC SINH
    # -----------------------------------------------------

    statement_schools = (
        select(School)
        .join(
            StudentEnrollment,
            StudentEnrollment.school_id
            == School.id,
        )
    )

    if school_year_id is not None:
        statement_schools = (
            statement_schools.where(
                StudentEnrollment.school_year_id
                == school_year_id
            )
        )

    statement_schools = (
        statement_schools
        .distinct()
        .order_by(School.name.asc())
    )

    schools = db.scalars(
        statement_schools
    ).all()

    valid_school_ids = {
        item.id
        for item in schools
    }

    if school_id not in valid_school_ids:
        school_id = None

    # -----------------------------------------------------
    # DANH SÁCH LỚP
    # -----------------------------------------------------

    classrooms: list[Classroom] = []

    # Chỉ hiển thị danh sách lớp
    # sau khi người dùng đã chọn trường.
    if (
        school_year_id is not None
        and school_id is not None
    ):
        statement_classes = (
            select(Classroom)
            .where(
                Classroom.school_year_id
                == school_year_id,
                Classroom.school_id
                == school_id,
            )
            .order_by(Classroom.name.asc())
        )

        classrooms = db.scalars(
            statement_classes
        ).all()

        valid_class_ids = {
            item.id
            for item in classrooms
        }

        if class_id not in valid_class_ids:
            class_id = None
    else:
        class_id = None

    # -----------------------------------------------------
    # CÁC ĐIỀU KIỆN LỌC
    # -----------------------------------------------------

    filters = []

    if school_year_id is not None:
        filters.append(
            StudentEnrollment.school_year_id
            == school_year_id
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
            )
        )

    # -----------------------------------------------------
    # ĐẾM TỔNG SỐ KẾT QUẢ
    # -----------------------------------------------------

    count_statement = (
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
        .where(*filters)
    )

    total_records = db.scalar(
        count_statement
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

    # -----------------------------------------------------
    # LẤY DANH SÁCH HỌC SINH
    # -----------------------------------------------------

    data_statement = (
        select(StudentEnrollment)
        .join(
            Student,
            Student.id
            == StudentEnrollment.student_id,
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
    )

    enrollments = db.scalars(
        data_statement
    ).all()

    # -----------------------------------------------------
    # TẠO CÁC NÚT PHÂN TRANG
    # -----------------------------------------------------

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
            school_id=school_id,
            class_id=class_id,
        )

    # -----------------------------------------------------
    # HIỂN THỊ GIAO DIỆN
    # -----------------------------------------------------

    return templates.TemplateResponse(
        request=request,
        name="students/list.html",
        context={
            "nguoi_dung": (
                request.scope.get(
                    "auth_user"
                )
            ),
            "enrollments": enrollments,
            "school_years": school_years,
            "schools": schools,
            "classrooms": classrooms,
            "q": q,
            "selected_school_year_id": (
                school_year_id
            ),
            "selected_school_id": (
                school_id
            ),
            "selected_class_id": class_id,
            "page": page,
            "page_size": PAGE_SIZE,
            "total_records": (
                total_records
            ),
            "total_pages": total_pages,
            "page_links": page_links,
            "previous_url": previous_url,
            "next_url": next_url,
        },
    )