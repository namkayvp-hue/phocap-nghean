from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.thpt_reference_models import THPTGradeReference, THPTSchoolReference


router = APIRouter(prefix="/truong-thpt", tags=["thpt-reference"])
templates = Jinja2Templates(directory="app/templates")

SOURCE_YEAR = "2025-2026"


@router.get("", response_class=HTMLResponse)
def danh_muc_thpt(
    request: Request,
    q: str = Query(default="", max_length=120),
    db: Session = Depends(get_db),
):
    keyword = " ".join(q.strip().split())

    statement = (
        select(THPTSchoolReference)
        .where(THPTSchoolReference.school_year_code == SOURCE_YEAR)
        .options(selectinload(THPTSchoolReference.grades))
        .order_by(THPTSchoolReference.school_code.asc())
    )

    if keyword:
        statement = statement.where(
            or_(
                THPTSchoolReference.school_code.ilike(f"%{keyword}%"),
                THPTSchoolReference.school_name.ilike(f"%{keyword}%"),
            )
        )

    schools = list(db.scalars(statement).unique().all())

    total_school = int(
        db.scalar(
            select(func.count(THPTSchoolReference.id)).where(
                THPTSchoolReference.school_year_code == SOURCE_YEAR
            )
        )
        or 0
    )
    total_class = int(
        db.scalar(
            select(func.sum(THPTSchoolReference.total_class_count)).where(
                THPTSchoolReference.school_year_code == SOURCE_YEAR
            )
        )
        or 0
    )
    total_student = int(
        db.scalar(
            select(func.sum(THPTSchoolReference.total_student_count)).where(
                THPTSchoolReference.school_year_code == SOURCE_YEAR
            )
        )
        or 0
    )
    linked_school = int(
        db.scalar(
            select(func.count(THPTSchoolReference.id)).where(
                THPTSchoolReference.school_year_code == SOURCE_YEAR,
                THPTSchoolReference.official_school_id.is_not(None),
            )
        )
        or 0
    )

    return templates.TemplateResponse(
        request=request,
        name="schools/thpt_reference.html",
        context={
            "nguoi_dung": request.scope.get("auth_user"),
            "q": keyword,
            "schools": schools,
            "source_year": SOURCE_YEAR,
            "summary": {
                "school_total": total_school,
                "class_total": total_class,
                "student_total": total_student,
                "linked_total": linked_school,
            },
        },
    )


@router.get("/api/danh-sach")
def api_danh_sach_thpt(
    q: str = Query(default="", max_length=120),
    db: Session = Depends(get_db),
) -> list[dict[str, object]]:
    keyword = " ".join(q.strip().split())

    statement = (
        select(THPTSchoolReference)
        .where(THPTSchoolReference.school_year_code == SOURCE_YEAR)
        .order_by(THPTSchoolReference.school_name.asc())
    )

    if keyword:
        statement = statement.where(
            or_(
                THPTSchoolReference.school_code.ilike(f"%{keyword}%"),
                THPTSchoolReference.school_name.ilike(f"%{keyword}%"),
            )
        )

    rows = db.scalars(statement).all()
    return [
        {
            "id": item.id,
            "code": item.school_code,
            "name": item.school_name,
            "official_school_id": item.official_school_id,
        }
        for item in rows
    ]


@router.get("/api/khoi")
def api_khoi_thpt(
    school_code: str,
    db: Session = Depends(get_db),
) -> list[dict[str, int | None]]:
    school = db.scalar(
        select(THPTSchoolReference)
        .where(
            THPTSchoolReference.school_year_code == SOURCE_YEAR,
            THPTSchoolReference.school_code == school_code.strip(),
        )
        .options(selectinload(THPTSchoolReference.grades))
    )
    if school is None:
        return []

    return [
        {
            "grade": grade.grade,
            "class_count": grade.class_count,
            "student_count": grade.student_count,
            "new_student_count": grade.new_student_count,
        }
        for grade in school.grades
    ]
