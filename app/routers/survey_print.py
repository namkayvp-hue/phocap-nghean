from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, selectinload, with_loader_criteria

from app.database import get_db
from app.survey_models import (
    Household,
    SurveyFileExchangeLog,
    SurveyForm,
    SurveyFormInvestigator,
    SurveyPerson,
    SurveyPersonYearRecord,
)
from app.routers.surveys import (
    FORM_STATUS_LABELS,
    LEARNING_STATUS_LABELS,
    RESIDENCY_STATUS_LABELS,
    lay_dot_dieu_tra,
    tao_bo_loc_bao_cao_theo_nguoi_dung,
    dong_bo_phan_cong_truong_hien_tai_tu_nhat_ky,
)


APP_DIR = Path(__file__).resolve().parent.parent

templates = Jinja2Templates(
    directory=str(APP_DIR / "templates")
)

router = APIRouter(
    prefix="/dieu-tra",
    tags=["Phiếu điều tra thực địa"],
)


BOOLEAN_LABELS = {
    True: "Có",
    False: "Không",
    None: "Chưa xác định",
}


def lay_nguoi_dung(request: Request) -> dict[str, Any]:
    return dict(request.scope.get("auth_user") or {})


def dinh_dang_ngay(value) -> str:
    if value is None:
        return ""
    return value.strftime("%d/%m/%Y")


def ten_truong(record: SurveyPersonYearRecord | None) -> str:
    if record is None:
        return ""
    if record.school is not None:
        return str(record.school.name or "")
    return str(record.school_name_reported or "")


def ten_lop(record: SurveyPersonYearRecord | None) -> str:
    if record is None:
        return ""
    if record.classroom is not None:
        return str(record.classroom.name or "")
    return str(record.class_name_reported or "")



def lay_truong_duoc_giao_cho_phieu(
    db: Session,
    form_ids: list[int],
) -> dict[int, list[dict[str, Any]]]:
    """Lấy trường đang được giao theo từng phiếu để in bảng bàn giao."""

    result: dict[int, list[dict[str, Any]]] = {}
    if not form_ids:
        return result
    placeholders = ", ".join(
        f":form_id_{index}" for index in range(len(form_ids))
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
                sfi.is_primary,
                sfi.signed_at,
                u.username,
                u.full_name,
                s.code AS school_code,
                s.name AS school_name
            FROM survey_form_investigators AS sfi
            JOIN users AS u ON u.id = sfi.user_id
            JOIN roles AS r ON r.id = u.role_id
            LEFT JOIN schools AS s ON s.id = u.school_id
            WHERE sfi.survey_form_id IN ({placeholders})
              AND r.code = 'TRUONG'
              AND LOWER(u.username) NOT LIKE 'cbql.%'
            ORDER BY
                sfi.survey_form_id,
                sfi.is_primary DESC,
                s.name,
                sfi.id
            """
        ),
        parameters,
    ).mappings().all()
    for row in rows:
        result.setdefault(int(row["survey_form_id"]), []).append(dict(row))
    return result


def lay_giao_vien_duoc_giao_cho_phieu(
    db: Session,
    form_ids: list[int],
) -> dict[int, list[dict[str, Any]]]:
    """Lấy giáo viên/CBQL đang được giao theo từng phiếu."""

    result: dict[int, list[dict[str, Any]]] = {}
    if not form_ids:
        return result

    placeholders = ", ".join(
        f":form_id_{index}" for index in range(len(form_ids))
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
                sfi.is_primary,
                sfi.signed_at,
                u.id AS user_id,
                u.username,
                u.full_name,
                r.code AS role_code,
                r.name AS role_name,
                s.code AS school_code,
                s.name AS school_name
            FROM survey_form_investigators AS sfi
            JOIN users AS u ON u.id = sfi.user_id
            JOIN roles AS r ON r.id = u.role_id
            LEFT JOIN schools AS s ON s.id = u.school_id
            WHERE sfi.survey_form_id IN ({placeholders})
              AND (
                    r.code = 'GIAO_VIEN'
                 OR (
                        r.code = 'TRUONG'
                    AND LOWER(u.username) LIKE 'cbql.%'
                 )
              )
            ORDER BY
                sfi.survey_form_id,
                sfi.is_primary DESC,
                sfi.order_number,
                u.full_name,
                sfi.id
            """
        ),
        parameters,
    ).mappings().all()

    for row in rows:
        result.setdefault(int(row["survey_form_id"]), []).append(
            dict(row)
        )
    return result


def ghi_nhat_ky_in(
    *,
    request: Request,
    db: Session,
    batch,
    form_total: int,
    person_total: int,
) -> None:
    user = lay_nguoi_dung(request)
    safe_year = str(batch.school_year.code or "").replace("-", "")
    file_name = (
        f"phieu_in_thuc_dia_{batch.commune.code}_{safe_year}.html"
    )
    db.add(
        SurveyFileExchangeLog(
            school_year_id=batch.school_year_id,
            survey_batch_id=batch.id,
            commune_id=batch.commune_id,
            action="IN_PHIEU",
            status="THANH_CONG",
            file_name=file_name,
            actor_user_id=user.get("id"),
            actor_name_snapshot=user.get("full_name"),
            actor_role_snapshot=(
                user.get("role_name") or user.get("role_code")
            ),
            form_total=form_total,
            person_total=person_total,
            notes=(
                "Mở bản in phiếu điều tra thực địa và bảng kê bàn giao."
            ),
        )
    )



# === LOC_TAI_KHOAN_TRUONG_KHOI_NGUOI_DIEU_TRA_V1_HELPER ===
def la_tai_khoan_don_vi_truong(user) -> bool:
    if user is None:
        return False

    username = str(getattr(user, "username", "") or "").strip().lower()

    # CBQL vẫn là người điều tra hợp lệ khi được phân công.
    if username.startswith("cbql."):
        return False

    role = getattr(user, "role", None)
    role_code = str(getattr(role, "code", "") or "").strip().upper()

    if role_code:
        return role_code == "TRUONG"

    # Tương thích tài khoản đơn vị trường cũ.
    return username.startswith("truong_")


@router.get(
    "/{batch_id}/phieu-in-thuc-dia",
    response_class=HTMLResponse,
)
def in_phieu_dieu_tra_thuc_dia(
    batch_id: int,
    request: Request,
    form_ids: str = "",
    auto_print: int = 0,
    source: str = "",
    db: Session = Depends(get_db),
):
    batch = lay_dot_dieu_tra(db, batch_id)
    if batch is None:
        return RedirectResponse(
            url="/dieu-tra/trung-tam-phieu",
            status_code=303,
        )

    dong_bo_phan_cong_truong_hien_tai_tu_nhat_ky(
        db=db,
        batch_id=batch.id,
    )

    selected_form_ids: list[int] = []
    seen_form_ids: set[int] = set()
    for raw_value in str(form_ids or "").split(","):
        raw_value = raw_value.strip()
        if not raw_value:
            continue
        try:
            form_id = int(raw_value)
        except ValueError:
            continue
        if form_id > 0 and form_id not in seen_form_ids:
            seen_form_ids.add(form_id)
            selected_form_ids.append(form_id)
        if len(selected_form_ids) >= 200:
            break

    filters = [
        SurveyForm.survey_batch_id == batch.id,
        *tao_bo_loc_bao_cao_theo_nguoi_dung(request),
    ]
    if selected_form_ids:
        filters.append(SurveyForm.id.in_(selected_form_ids))

    forms = list(
        db.scalars(
            select(SurveyForm)
            .join(
                Household,
                Household.id == SurveyForm.household_id,
            )
            .options(
                selectinload(SurveyForm.household)
                .selectinload(Household.people),
                selectinload(SurveyForm.investigators)
                .selectinload(SurveyFormInvestigator.user),
                selectinload(SurveyForm.person_year_records)
                .selectinload(SurveyPersonYearRecord.survey_person),
                selectinload(SurveyForm.person_year_records)
                .selectinload(SurveyPersonYearRecord.school),
                selectinload(SurveyForm.person_year_records)
                .selectinload(SurveyPersonYearRecord.classroom),
                selectinload(SurveyForm.person_year_records)
                .selectinload(SurveyPersonYearRecord.school_year),
                with_loader_criteria(
                    SurveyPerson,
                    SurveyPerson.is_active.is_(True),
                    include_aliases=True,
                ),
            )
            .where(*filters)
            .order_by(
                Household.hamlet_name.asc(),
                Household.head_name.asc(),
                SurveyForm.form_number.asc(),
            )
        ).all()
    )

    form_id_values = [int(item.id) for item in forms]
    assigned_school_map = lay_truong_duoc_giao_cho_phieu(
        db, form_id_values
    )
    assigned_teacher_map = lay_giao_vien_duoc_giao_cho_phieu(
        db, form_id_values
    )
    form_rows: list[dict[str, Any]] = []
    person_total = 0

    for survey_form in forms:
        # === BAI_13B_9_V1A_OFFICIAL_PRINT_START ===
        records_by_person_id: dict[int, list[SurveyPersonYearRecord]] = {}
        for record_item in survey_form.person_year_records:
            records_by_person_id.setdefault(
                record_item.survey_person_id,
                [],
            ).append(record_item)

        people_rows: list[dict[str, Any]] = []

        for person in sorted(
            (
                item
                for item in survey_form.household.people
                if item.is_active
            ),
            key=lambda item: (
                item.date_of_birth is None,
                item.date_of_birth or datetime.max.date(),
                item.full_name,
            ),
        ):
            person_records = sorted(
                records_by_person_id.get(person.id, []),
                key=lambda item: (
                    (
                        item.school_year.code
                        if item.school_year is not None
                        else ""
                    ),
                    item.school_year_id,
                    item.id,
                ),
            )
            record = next(
                (
                    item
                    for item in reversed(person_records)
                    if item.school_year_id == batch.school_year_id
                ),
                None,
            )

            year_rows = [
                {
                    "year_code": (
                        item.school_year.code
                        if item.school_year is not None
                        else str(item.school_year_id)
                    ),
                    "school_name": ten_truong(item),
                    "class_name": ten_lop(item),
                    "learning_status": LEARNING_STATUS_LABELS.get(
                        item.learning_status,
                        item.learning_status or "",
                    ),
                }
                for item in person_records[-7:]
            ]

            completion_parts: list[str] = []
            for item in person_records:
                if item.completed_preschool_5 is True:
                    year_code = (
                        item.school_year.code
                        if item.school_year is not None
                        else ""
                    )
                    completion_parts.append(
                        "MN" + (f" · {year_code}" if year_code else "")
                    )

            study_completed = next(
                (
                    item
                    for item in reversed(person_records)
                    if item.learning_status
                    in {"HOC_XONG", "DA_HOC_XONG"}
                ),
                None,
            )
            dropout = next(
                (
                    item
                    for item in reversed(person_records)
                    if item.learning_status in {"BO_HOC", "THOI_HOC"}
                ),
                None,
            )

            def _record_short(item):
                if item is None:
                    return ""
                class_name = ten_lop(item)
                year_code = (
                    item.school_year.code
                    if item.school_year is not None
                    else ""
                )
                values = [value for value in (class_name, year_code) if value]
                return " · ".join(values)

            special_text = str(person.special_circumstances or "")
            special_lower = special_text.lower()
            disability_text = (
                special_text
                if (
                    "khuyết" in special_lower
                    or "khuyet" in special_lower
                    or "tật" in special_lower
                    or "tat " in special_lower
                )
                else ""
            )

            movement_text = ""
            if person.residency_status in {"CHUYEN_DEN", "CHUYEN_DI"}:
                movement_text = RESIDENCY_STATUS_LABELS.get(
                    person.residency_status,
                    person.residency_status,
                )

            parent_names = [
                value
                for value in (
                    person.father_name,
                    person.mother_name,
                )
                if value
            ]

            people_rows.append(
                {
                    "person": person,
                    "record": record,
                    "date_of_birth": dinh_dang_ngay(
                        person.date_of_birth
                    ),
                    "residency_label": RESIDENCY_STATUS_LABELS.get(
                        person.residency_status,
                        person.residency_status or "Chưa xác định",
                    ),
                    "learning_label": (
                        "Chưa xác định"
                        if record is None
                        else LEARNING_STATUS_LABELS.get(
                            record.learning_status,
                            (
                                "Chưa xác định"
                                if record.learning_status
                                == "CHUA_XAC_DINH"
                                else record.learning_status
                            ),
                        )
                    ),
                    "school_name": ten_truong(record),
                    "class_name": ten_lop(record),
                    "year_rows": year_rows,
                    "completion_text": ", ".join(completion_parts[-3:]),
                    "study_completed_text": _record_short(study_completed),
                    "dropout_text": _record_short(dropout),
                    "literacy_text": "",
                    "disability_text": disability_text,
                    "movement_text": movement_text,
                    "notes_text": str(person.notes or ""),
                    "parent_name": " / ".join(parent_names),
                    "citizen_id": getattr(person, "citizen_id", None) or "",
                    "indicator_values": (
                        []
                        if record is None
                        else [
                            BOOLEAN_LABELS[record.completed_preschool_5],
                            BOOLEAN_LABELS[record.attends_required_days],
                            BOOLEAN_LABELS[record.attends_regularly],
                            BOOLEAN_LABELS[record.prepared_vietnamese],
                            BOOLEAN_LABELS[record.weight_monitored],
                            BOOLEAN_LABELS[record.underweight],
                            BOOLEAN_LABELS[record.height_monitored],
                            BOOLEAN_LABELS[record.stunted],
                        ]
                    ),
                }
            )

        person_total += len(people_rows)
        people_pages = [
            people_rows[index:index + 7]
            for index in range(0, len(people_rows), 7)
        ] or [[]]
        people_pages = [
            page + [None] * (7 - len(page))
            for page in people_pages
        ]
        # === BAI_13B_9_V1A_OFFICIAL_PRINT_END ===
        # === LOC_TAI_KHOAN_TRUONG_KHOI_NGUOI_DIEU_TRA_V1_CALL ===
        investigator_names = [
            item.user.full_name
            for item in sorted(
                survey_form.investigators,
                key=lambda item: item.order_number,
            )
            if (
                item.user is not None
                and not la_tai_khoan_don_vi_truong(item.user)
            )
        ]

        assigned_schools = assigned_school_map.get(int(survey_form.id), [])
        assigned_teachers = assigned_teacher_map.get(
            int(survey_form.id), []
        )
        form_rows.append(
            {
                "form": survey_form,
                "household": survey_form.household,
                "people": people_rows,
                "pages": people_pages,
                "investigator_names": investigator_names,
                "assigned_schools": assigned_schools,
                "assigned_school_names": [
                    str(item.get("school_name") or item.get("full_name") or "")
                    for item in assigned_schools
                ],
                "assigned_at": next(
                    (
                        str(item.get("signed_at") or "")
                        for item in assigned_schools
                        if item.get("signed_at")
                    ),
                    "",
                ),
                "assigned_teachers": assigned_teachers,
                "assigned_teacher_names": [
                    str(item.get("full_name") or item.get("username") or "")
                    for item in assigned_teachers
                ],
                "teacher_assigned_at": next(
                    (
                        str(item.get("signed_at") or "")
                        for item in assigned_teachers
                        if item.get("signed_at")
                    ),
                    "",
                ),
                "form_status_label": FORM_STATUS_LABELS.get(
                    survey_form.status,
                    survey_form.status,
                ),
            }
        )

    handover_school_names: list[str] = []
    seen_school_names: set[str] = set()
    for row in form_rows:
        for school_name in row["assigned_school_names"]:
            if school_name and school_name not in seen_school_names:
                seen_school_names.add(school_name)
                handover_school_names.append(school_name)

    handover_teacher_names: list[str] = []
    seen_teacher_names: set[str] = set()
    for row in form_rows:
        for teacher_name in row["assigned_teacher_names"]:
            if teacher_name and teacher_name not in seen_teacher_names:
                seen_teacher_names.add(teacher_name)
                handover_teacher_names.append(teacher_name)

    ghi_nhat_ky_in(
        request=request,
        db=db,
        batch=batch,
        form_total=len(forms),
        person_total=person_total,
    )
    db.commit()

    return templates.TemplateResponse(
        request=request,
        name="surveys/field_print.html",
        context={
            "nguoi_dung": lay_nguoi_dung(request),
            "batch": batch,
            "form_rows": form_rows,
            "form_total": len(forms),
            "person_total": person_total,
            "generated_at": datetime.now(),
            "selected_form_ids": selected_form_ids,
            "auto_print": bool(auto_print),
            "print_source": str(source or "")[:50],
            "handover_school_names": handover_school_names,
            "handover_teacher_names": handover_teacher_names,
        },
    )
