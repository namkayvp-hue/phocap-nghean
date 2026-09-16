from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import case, func, select, text
from sqlalchemy.orm import Session, selectinload

from app.database import Base, engine, get_db
from app.models import Commune, Role, School, SchoolYear, User
from app.permissions import (
    ADMIN_ROLE_CODES,
    COMMUNE_ROLE_CODE,
    DEPARTMENT_ROLE_CODE,
    SCHOOL_ROLE_CODE,
    is_admin_role,
    normalize_role_code,
)
from app.survey_models import SurveyBatch, SurveyForm
from app.survey_workflow_models import (
    SurveyCommuneExecutionState,
    SurveyExecutionWorkflowLog,
    SurveySchoolAssignment,
)


APP_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(APP_DIR / "templates"))

router = APIRouter(
    prefix="/dieu-tra",
    tags=["Điều hành thực hiện điều tra ba cấp"],
)


SCHOOL_STATUS_LABELS = {
    "DANG_THUC_HIEN": "Đang thực hiện",
    "DA_GUI_XA": "Đã gửi xã kiểm tra",
    "YEU_CAU_BO_SUNG": "Xã yêu cầu bổ sung",
    "DA_HOAN_THANH": "Đã hoàn thành",
}

WORKFLOW_MESSAGES = {
    "school_not_complete": (
        "Chưa thể khóa trường: phải hoàn thành 100% phiếu điều tra của trường."
    ),
    "school_assigned": "Đã giao nhiệm vụ điều tra cho trường.",
    "school_revoked": "Đã thu hồi nhiệm vụ của trường chưa có phiếu được giao.",
    "school_locked": "Đã khóa quyền cập nhật của trường.",
    "school_unlocked": "Đã mở lại quyền cập nhật của trường.",
    "school_submitted": "Đã gửi kết quả của trường lên xã/phường kiểm tra.",
    "school_supplement": "Đã yêu cầu trường bổ sung dữ liệu.",
    "school_completed": "Đã xác nhận trường hoàn thành nhiệm vụ.",
    "commune_not_complete": (
        "Chưa thể khóa toàn xã: phải hoàn thành 100% phiếu điều tra của địa bàn."
    ),
    "commune_schools_not_locked": (
        "Chưa thể khóa toàn xã: tất cả trường có phiếu phải được khóa/xác nhận hoàn thành trước."
    ),
    "commune_locked": "Đã khóa toàn bộ dữ liệu điều tra của xã/phường.",
    "commune_unlocked": "Đã mở lại dữ liệu điều tra của xã/phường.",
    "province_not_ready": (
        "Chưa thể khóa toàn tỉnh: tất cả xã/phường của năm học phải khóa cấp xã trước."
    ),
    "province_no_batches": "Năm học chưa có đợt điều tra để khóa.",
    "province_locked": "Đã khóa đợt điều tra trên toàn tỉnh.",
    "province_unlocked": "Đã mở khóa cấp tỉnh; địa bàn đã khóa cấp xã vẫn tiếp tục bị khóa.",
    "invalid_reason": "Cần nhập lý do rõ ràng trước khi khóa hoặc mở khóa.",
    "province_lock_blocks": "Sở đang khóa toàn tỉnh nên xã/phường không thể mở lại.",
    "school_has_forms": "Không thể thu hồi trường vì đã có phiếu được giao.",
    "forbidden": "Tài khoản không có quyền thực hiện thao tác này.",
}


def dam_bao_bang_quy_trinh() -> None:
    """Tạo các bảng mới và bổ sung trạng thái cho các đợt hiện có."""

    Base.metadata.create_all(
        bind=engine,
        tables=[
            SurveyCommuneExecutionState.__table__,
            SurveySchoolAssignment.__table__,
            SurveyExecutionWorkflowLog.__table__,
        ],
    )
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO survey_commune_execution_states (
                    survey_batch_id,
                    is_commune_locked,
                    is_province_locked,
                    updated_at
                )
                SELECT
                    sb.id,
                    CASE WHEN sb.is_locked = 1 THEN 1 ELSE 0 END,
                    0,
                    CURRENT_TIMESTAMP
                FROM survey_batches AS sb
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM survey_commune_execution_states AS state
                    WHERE state.survey_batch_id = sb.id
                )
                """
            )
        )


dam_bao_bang_quy_trinh()


def lay_nguoi_dung(request: Request) -> dict[str, Any]:
    return dict(request.scope.get("auth_user") or {})


def lay_dot(db: Session, batch_id: int) -> SurveyBatch | None:
    return db.scalar(
        select(SurveyBatch)
        .options(
            selectinload(SurveyBatch.school_year),
            selectinload(SurveyBatch.commune),
        )
        .where(SurveyBatch.id == batch_id)
    )


def lay_trang_thai_dia_ban(
    db: Session,
    batch: SurveyBatch,
) -> SurveyCommuneExecutionState:
    state = db.scalar(
        select(SurveyCommuneExecutionState).where(
            SurveyCommuneExecutionState.survey_batch_id == batch.id
        )
    )
    if state is None:
        state = SurveyCommuneExecutionState(
            survey_batch_id=batch.id,
            is_commune_locked=bool(batch.is_locked),
            is_province_locked=False,
        )
        db.add(state)
        db.flush()
    return state


def co_quyen_quan_ly_xa(
    *,
    user: dict[str, Any],
    batch: SurveyBatch,
) -> bool:
    role_code = normalize_role_code(user.get("role_code"))
    if is_admin_role(role_code):
        return True
    return (
        role_code == COMMUNE_ROLE_CODE
        and user.get("commune_id") is not None
        and int(user["commune_id"]) == int(batch.commune_id)
    )


def dem_phieu_cua_truong(
    db: Session,
    *,
    batch_id: int,
    school_id: int,
) -> dict[str, int]:
    row = db.execute(
        text(
            """
            SELECT
                COUNT(DISTINCT sf.id) AS form_total,
                COUNT(DISTINCT CASE
                    WHEN sf.status = 'DA_HOAN_THANH' THEN sf.id
                END) AS completed_total,
                COUNT(DISTINCT CASE
                    WHEN sf.status = 'CAN_BO_SUNG' THEN sf.id
                END) AS supplement_total
            FROM survey_forms AS sf
            JOIN survey_form_investigators AS sfi
                ON sfi.survey_form_id = sf.id
            JOIN users AS u
                ON u.id = sfi.user_id
            WHERE sf.survey_batch_id = :batch_id
              AND u.school_id = :school_id
              AND u.is_active = 1
            """
        ),
        {"batch_id": batch_id, "school_id": school_id},
    ).mappings().one()
    return {
        "form_total": int(row["form_total"] or 0),
        "completed_total": int(row["completed_total"] or 0),
        "supplement_total": int(row["supplement_total"] or 0),
    }


def lay_tai_khoan_don_vi_truong(
    db: Session,
    school_id: int,
) -> dict[str, Any] | None:
    row = db.execute(
        text(
            """
            SELECT u.id, u.username, u.full_name, u.is_active
            FROM users AS u
            JOIN roles AS r ON r.id = u.role_id
            WHERE u.school_id = :school_id
              AND r.code = 'TRUONG'
              AND LOWER(u.username) NOT LIKE 'cbql.%'
            ORDER BY u.is_active DESC, u.id ASC
            LIMIT 1
            """
        ),
        {"school_id": school_id},
    ).mappings().first()
    return dict(row) if row else None


def ghi_nhat_ky(
    *,
    db: Session,
    batch_id: int,
    school_id: int | None,
    action: str,
    actor: dict[str, Any],
    reason: str = "",
    form_total: int = 0,
    completed_form_total: int = 0,
) -> None:
    db.add(
        SurveyExecutionWorkflowLog(
            survey_batch_id=batch_id,
            school_id=school_id,
            action=action,
            actor_user_id=actor.get("id"),
            actor_name_snapshot=str(actor.get("full_name") or "")[:200] or None,
            actor_role_snapshot=str(actor.get("role_code") or "")[:50] or None,
            reason=reason[:2000] or None,
            form_total=max(int(form_total or 0), 0),
            completed_form_total=max(int(completed_form_total or 0), 0),
        )
    )


def dong_bo_khoa_dot(
    *,
    batch: SurveyBatch,
    state: SurveyCommuneExecutionState,
    actor: dict[str, Any] | None = None,
    reason: str | None = None,
) -> None:
    locked = bool(state.is_province_locked or state.is_commune_locked)
    batch.is_locked = locked
    if locked:
        batch.status_before_lock = batch.status_before_lock or batch.status
        batch.status = "DA_KET_THUC"
        batch.locked_at = datetime.now()
        batch.locked_by_user_id = (actor or {}).get("id")
        batch.lock_reason = reason or batch.lock_reason
    else:
        batch.status = batch.status_before_lock or "DANG_DIEU_TRA"
        batch.status_before_lock = None
        batch.locked_at = None
        batch.locked_by_user_id = None
        batch.lock_reason = None


def tao_hang_truong(
    *,
    db: Session,
    batch: SurveyBatch,
    school: School,
    assignment: SurveySchoolAssignment | None,
) -> dict[str, Any]:
    counts = dem_phieu_cua_truong(
        db,
        batch_id=batch.id,
        school_id=school.id,
    )
    account = lay_tai_khoan_don_vi_truong(db, school.id)
    return {
        "school": school,
        "assignment": assignment,
        "account": account,
        **counts,
        "pending_total": max(
            counts["form_total"] - counts["completed_total"],
            0,
        ),
    }


def redirect_workflow(batch_id: int, status: str) -> RedirectResponse:
    return RedirectResponse(
        url=f"/dieu-tra/{batch_id}/phan-cong-truong?status={status}",
        status_code=303,
    )


@router.get(
    "/{batch_id}/phan-cong-truong",
    response_class=HTMLResponse,
)
def trang_phan_cong_truong(
    request: Request,
    batch_id: int,
    status: str = "",
    db: Session = Depends(get_db),
):
    user = lay_nguoi_dung(request)
    role_code = normalize_role_code(user.get("role_code"))
    batch = lay_dot(db, batch_id)
    if batch is None:
        return RedirectResponse("/dieu-tra", 303)

    state = lay_trang_thai_dia_ban(db, batch)

    if role_code == SCHOOL_ROLE_CODE:
        school_id = user.get("school_id")
        schools = (
            [db.get(School, int(school_id))]
            if school_id is not None
            else []
        )
        schools = [item for item in schools if item is not None]
    else:
        schools = list(
            db.scalars(
                select(School)
                .where(
                    School.commune_id == batch.commune_id,
                    School.is_active.is_(True),
                )
                .order_by(School.name.asc(), School.code.asc())
            ).all()
        )

    school_ids = [item.id for item in schools]
    assignments = {
        item.school_id: item
        for item in db.scalars(
            select(SurveySchoolAssignment).where(
                SurveySchoolAssignment.survey_batch_id == batch.id,
                SurveySchoolAssignment.school_id.in_(school_ids),
            )
        ).all()
    } if school_ids else {}

    rows = [
        tao_hang_truong(
            db=db,
            batch=batch,
            school=school,
            assignment=assignments.get(school.id),
        )
        for school in schools
    ]

    summary = {
        "school_total": len(rows),
        "assigned_total": sum(item["assignment"] is not None for item in rows),
        "submitted_total": sum(
            item["assignment"] is not None
            and item["assignment"].status == "DA_GUI_XA"
            for item in rows
        ),
        "completed_total": sum(
            item["assignment"] is not None
            and item["assignment"].status == "DA_HOAN_THANH"
            for item in rows
        ),
        "locked_total": sum(
            item["assignment"] is not None
            and item["assignment"].is_locked
            for item in rows
        ),
        "form_total": sum(item["form_total"] for item in rows),
        "completed_form_total": sum(item["completed_total"] for item in rows),
    }

    logs = db.execute(
        text(
            """
            SELECT
                log.action,
                log.actor_name_snapshot,
                log.actor_role_snapshot,
                log.reason,
                log.form_total,
                log.completed_form_total,
                log.created_at,
                school.name AS school_name
            FROM survey_execution_workflow_logs AS log
            LEFT JOIN schools AS school ON school.id = log.school_id
            WHERE log.survey_batch_id = :batch_id
            ORDER BY log.id DESC
            LIMIT 30
            """
        ),
        {"batch_id": batch.id},
    ).mappings().all()

    return templates.TemplateResponse(
        request=request,
        name="surveys/school_workflow.html",
        context={
            "nguoi_dung": user,
            "batch": batch,
            "state": state,
            "rows": rows,
            "summary": summary,
            "logs": [dict(item) for item in logs],
            "status_labels": SCHOOL_STATUS_LABELS,
            "message": WORKFLOW_MESSAGES.get(status),
            "role_code": role_code,
            "can_manage_commune": co_quyen_quan_ly_xa(
                user=user,
                batch=batch,
            ),
            "can_submit_school": role_code == SCHOOL_ROLE_CODE,
            "province_locked": bool(state.is_province_locked),
            "commune_locked": bool(state.is_commune_locked),
        },
    )


@router.post("/{batch_id}/phan-cong-truong/{school_id}/giao")
def giao_nhiem_vu_cho_truong(
    request: Request,
    batch_id: int,
    school_id: int,
    notes: Annotated[str, Form()] = "",
    db: Session = Depends(get_db),
):
    actor = lay_nguoi_dung(request)
    batch = lay_dot(db, batch_id)
    school = db.get(School, school_id)
    if (
        batch is None
        or school is None
        or school.commune_id != batch.commune_id
        or not co_quyen_quan_ly_xa(user=actor, batch=batch)
    ):
        return redirect_workflow(batch_id, "forbidden")

    assignment = db.scalar(
        select(SurveySchoolAssignment).where(
            SurveySchoolAssignment.survey_batch_id == batch.id,
            SurveySchoolAssignment.school_id == school.id,
        )
    )
    if assignment is None:
        assignment = SurveySchoolAssignment(
            survey_batch_id=batch.id,
            school_id=school.id,
            status="DANG_THUC_HIEN",
            assigned_by_user_id=actor.get("id"),
            assigned_at=datetime.now(),
            notes=str(notes or "").strip()[:2000] or None,
        )
        db.add(assignment)
    else:
        assignment.status = "DANG_THUC_HIEN"
        assignment.assigned_by_user_id = actor.get("id")
        assignment.assigned_at = datetime.now()
        assignment.notes = str(notes or "").strip()[:2000] or assignment.notes

    ghi_nhat_ky(
        db=db,
        batch_id=batch.id,
        school_id=school.id,
        action="GIAO_TRUONG",
        actor=actor,
        reason=str(notes or "").strip(),
    )
    db.commit()
    return redirect_workflow(batch.id, "school_assigned")


@router.post("/{batch_id}/phan-cong-truong/{school_id}/thu-hoi")
def thu_hoi_nhiem_vu_truong(
    request: Request,
    batch_id: int,
    school_id: int,
    reason: Annotated[str, Form()] = "",
    db: Session = Depends(get_db),
):
    actor = lay_nguoi_dung(request)
    batch = lay_dot(db, batch_id)
    if batch is None or not co_quyen_quan_ly_xa(user=actor, batch=batch):
        return redirect_workflow(batch_id, "forbidden")

    assignment = db.scalar(
        select(SurveySchoolAssignment).where(
            SurveySchoolAssignment.survey_batch_id == batch.id,
            SurveySchoolAssignment.school_id == school_id,
        )
    )
    if assignment is None:
        return redirect_workflow(batch.id, "school_revoked")

    counts = dem_phieu_cua_truong(
        db,
        batch_id=batch.id,
        school_id=school_id,
    )
    if counts["form_total"] > 0:
        return redirect_workflow(batch.id, "school_has_forms")

    ghi_nhat_ky(
        db=db,
        batch_id=batch.id,
        school_id=school_id,
        action="THU_HOI_TRUONG",
        actor=actor,
        reason=str(reason or "").strip(),
    )
    db.delete(assignment)
    db.commit()
    return redirect_workflow(batch.id, "school_revoked")


@router.post("/{batch_id}/phan-cong-truong/{school_id}/khoa")
def khoa_truong(
    request: Request,
    batch_id: int,
    school_id: int,
    reason: Annotated[str, Form()],
    db: Session = Depends(get_db),
):
    actor = lay_nguoi_dung(request)
    batch = lay_dot(db, batch_id)
    reason = str(reason or "").strip()
    if not reason:
        return redirect_workflow(batch_id, "invalid_reason")
    if batch is None or not co_quyen_quan_ly_xa(user=actor, batch=batch):
        return redirect_workflow(batch_id, "forbidden")

    assignment = db.scalar(
        select(SurveySchoolAssignment).where(
            SurveySchoolAssignment.survey_batch_id == batch.id,
            SurveySchoolAssignment.school_id == school_id,
        )
    )
    if assignment is None:
        return redirect_workflow(batch.id, "forbidden")

    counts = dem_phieu_cua_truong(
        db,
        batch_id=batch.id,
        school_id=school_id,
    )

    # === CHOT_QUY_TAC_KHOA_TRUONG_100_PHAN_TRAM_V1 ===
    form_total = int(
        counts.get("form_total")
        or 0
    )
    completed_total = int(
        counts.get("completed_total")
        or 0
    )

    # Chỉ cho phép khóa khi trường có phiếu
    # và 100% phiếu đã hoàn thành.
    if (
        form_total <= 0
        or completed_total != form_total
    ):
        return redirect_workflow(
            batch.id,
            "school_not_complete",
        )

    assignment.is_locked = True
    assignment.locked_at = datetime.now()
    assignment.locked_by_user_id = actor.get("id")
    assignment.lock_reason = reason

    # Đã qua chốt 100%, nên trạng thái nhiệm vụ
    # được xác nhận hoàn thành đồng thời với khóa.
    assignment.status = "DA_HOAN_THANH"
    assignment.reviewed_at = datetime.now()

    ghi_nhat_ky(
        db=db,
        batch_id=batch.id,
        school_id=school_id,
        action="KHOA_TRUONG",
        actor=actor,
        reason=reason,
        form_total=counts["form_total"],
        completed_form_total=counts["completed_total"],
    )
    db.commit()
    return redirect_workflow(batch.id, "school_locked")


@router.post("/{batch_id}/phan-cong-truong/{school_id}/mo-khoa")
def mo_khoa_truong(
    request: Request,
    batch_id: int,
    school_id: int,
    reason: Annotated[str, Form()],
    db: Session = Depends(get_db),
):
    actor = lay_nguoi_dung(request)
    batch = lay_dot(db, batch_id)
    reason = str(reason or "").strip()
    if not reason:
        return redirect_workflow(batch_id, "invalid_reason")
    if batch is None or not co_quyen_quan_ly_xa(user=actor, batch=batch):
        return redirect_workflow(batch_id, "forbidden")

    state = lay_trang_thai_dia_ban(db, batch)
    if state.is_province_locked or state.is_commune_locked:
        return redirect_workflow(batch.id, "province_lock_blocks")

    assignment = db.scalar(
        select(SurveySchoolAssignment).where(
            SurveySchoolAssignment.survey_batch_id == batch.id,
            SurveySchoolAssignment.school_id == school_id,
        )
    )
    if assignment is None:
        return redirect_workflow(batch.id, "forbidden")

    counts = dem_phieu_cua_truong(
        db,
        batch_id=batch.id,
        school_id=school_id,
    )
    assignment.is_locked = False
    assignment.locked_at = None
    assignment.locked_by_user_id = None
    assignment.lock_reason = None
    if assignment.status == "DA_HOAN_THANH":
        assignment.status = "YEU_CAU_BO_SUNG"

    ghi_nhat_ky(
        db=db,
        batch_id=batch.id,
        school_id=school_id,
        action="MO_KHOA_TRUONG",
        actor=actor,
        reason=reason,
        form_total=counts["form_total"],
        completed_form_total=counts["completed_total"],
    )
    db.commit()
    return redirect_workflow(batch.id, "school_unlocked")


@router.post("/{batch_id}/phan-cong-truong/{school_id}/yeu-cau-bo-sung")
def yeu_cau_bo_sung(
    request: Request,
    batch_id: int,
    school_id: int,
    reason: Annotated[str, Form()],
    db: Session = Depends(get_db),
):
    actor = lay_nguoi_dung(request)
    batch = lay_dot(db, batch_id)
    reason = str(reason or "").strip()
    if not reason:
        return redirect_workflow(batch_id, "invalid_reason")
    if batch is None or not co_quyen_quan_ly_xa(user=actor, batch=batch):
        return redirect_workflow(batch_id, "forbidden")

    assignment = db.scalar(
        select(SurveySchoolAssignment).where(
            SurveySchoolAssignment.survey_batch_id == batch.id,
            SurveySchoolAssignment.school_id == school_id,
        )
    )
    if assignment is None:
        return redirect_workflow(batch.id, "forbidden")

    assignment.status = "YEU_CAU_BO_SUNG"
    assignment.reviewed_at = datetime.now()
    assignment.is_locked = False
    counts = dem_phieu_cua_truong(
        db,
        batch_id=batch.id,
        school_id=school_id,
    )
    ghi_nhat_ky(
        db=db,
        batch_id=batch.id,
        school_id=school_id,
        action="YEU_CAU_BO_SUNG",
        actor=actor,
        reason=reason,
        form_total=counts["form_total"],
        completed_form_total=counts["completed_total"],
    )
    db.commit()
    return redirect_workflow(batch.id, "school_supplement")


@router.post("/{batch_id}/phan-cong-truong/gui-xa")
def truong_gui_xa(
    request: Request,
    batch_id: int,
    notes: Annotated[str, Form()] = "",
    db: Session = Depends(get_db),
):
    # === BAI_13B_11_8_2_SEND_TO_COMMUNE_START ===
    actor = lay_nguoi_dung(request)
    role_code = normalize_role_code(actor.get("role_code"))
    batch = lay_dot(db, batch_id)
    school_id = actor.get("school_id")

    if (
        batch is None
        or role_code != SCHOOL_ROLE_CODE
        or school_id is None
    ):
        return redirect_workflow(batch_id, "forbidden")

    try:
        school_id_int = int(school_id)
    except (TypeError, ValueError):
        return redirect_workflow(batch_id, "forbidden")

    counts = dem_phieu_cua_truong(
        db,
        batch_id=batch.id,
        school_id=school_id_int,
    )

    assignment = db.scalar(
        select(SurveySchoolAssignment).where(
            SurveySchoolAssignment.survey_batch_id == batch.id,
            SurveySchoolAssignment.school_id == school_id_int,
        )
    )

    if assignment is None:
        if int(counts.get("form_total") or 0) <= 0:
            return redirect_workflow(batch.id, "forbidden")

        assignment = SurveySchoolAssignment(
            survey_batch_id=batch.id,
            school_id=school_id_int,
            status="DANG_THUC_HIEN",
            assigned_by_user_id=actor.get("id"),
            assigned_at=datetime.now(),
            notes=(
                "Tự đồng bộ nhiệm vụ từ phiếu đã giao "
                "(Bài 13B-11.8.2)."
            ),
        )
        db.add(assignment)
        db.flush()

    if assignment.is_locked:
        db.rollback()
        return redirect_workflow(batch.id, "forbidden")

    state = lay_trang_thai_dia_ban(db, batch)
    if state.is_province_locked or state.is_commune_locked:
        db.rollback()
        return redirect_workflow(batch.id, "province_lock_blocks")

    assignment.status = "DA_GUI_XA"
    assignment.submitted_at = datetime.now()

    ghi_nhat_ky(
        db=db,
        batch_id=batch.id,
        school_id=school_id_int,
        action="TRUONG_GUI_XA",
        actor=actor,
        reason=str(notes or "").strip(),
        form_total=counts["form_total"],
        completed_form_total=counts["completed_total"],
    )

    db.commit()
    return redirect_workflow(batch.id, "school_submitted")
    # === BAI_13B_11_8_2_SEND_TO_COMMUNE_END ===


    # === BAI_13B_11_8_1_RESUBMIT_TO_COMMUNE_END ===




@router.post("/{batch_id}/khoa-xa")
def khoa_toan_xa(
    request: Request,
    batch_id: int,
    reason: Annotated[str, Form()],
    db: Session = Depends(get_db),
):
    actor = lay_nguoi_dung(request)
    batch = lay_dot(db, batch_id)
    reason = str(reason or "").strip()
    if not reason:
        return redirect_workflow(batch_id, "invalid_reason")
    if batch is None or not co_quyen_quan_ly_xa(user=actor, batch=batch):
        return redirect_workflow(batch_id, "forbidden")

    state = lay_trang_thai_dia_ban(db, batch)
    if state.is_province_locked:
        return redirect_workflow(batch.id, "province_lock_blocks")

    # === CHOT_DIEU_KIEN_KHOA_XA_100_PHAN_TRAM_V2 ===
    # Cấp xã chỉ được khóa khi:
    # 1) toàn bộ phiếu của địa bàn đã hoàn thành;
    # 2) mọi trường thực sự có phiếu đều đã được xã khóa/xác nhận hoàn thành.
    totals = db.execute(
        select(
            func.count(SurveyForm.id),
            func.sum(
                case(
                    (SurveyForm.status == "DA_HOAN_THANH", 1),
                    else_=0,
                )
            ),
        ).where(SurveyForm.survey_batch_id == batch.id)
    ).one()

    form_total = int(totals[0] or 0)
    completed_form_total = int(totals[1] or 0)

    if form_total <= 0 or completed_form_total != form_total:
        return redirect_workflow(batch.id, "commune_not_complete")

    assignments = list(
        db.scalars(
            select(SurveySchoolAssignment).where(
                SurveySchoolAssignment.survey_batch_id == batch.id
            )
        ).all()
    )

    for assignment in assignments:
        counts = dem_phieu_cua_truong(
            db,
            batch_id=batch.id,
            school_id=int(assignment.school_id),
        )
        school_form_total = int(counts.get("form_total") or 0)

        # Nhiệm vụ chưa có phiếu không cản khóa toàn xã.
        # Có thể thu hồi nhiệm vụ này riêng trên màn hình phân công trường.
        if school_form_total <= 0:
            continue

        if (
            not bool(assignment.is_locked)
            or str(assignment.status or "") != "DA_HOAN_THANH"
        ):
            return redirect_workflow(
                batch.id,
                "commune_schools_not_locked",
            )
    # === CHOT_DIEU_KIEN_KHOA_XA_100_PHAN_TRAM_V2_END ===

    state.is_commune_locked = True
    state.commune_locked_at = datetime.now()
    state.commune_locked_by_user_id = actor.get("id")
    state.commune_lock_reason = reason
    dong_bo_khoa_dot(batch=batch, state=state, actor=actor, reason=reason)

    ghi_nhat_ky(
        db=db,
        batch_id=batch.id,
        school_id=None,
        action="KHOA_XA",
        actor=actor,
        reason=reason,
        form_total=form_total,
        completed_form_total=completed_form_total,
    )
    db.commit()
    return redirect_workflow(batch.id, "commune_locked")


@router.post("/{batch_id}/mo-khoa-xa")
def mo_khoa_toan_xa(
    request: Request,
    batch_id: int,
    reason: Annotated[str, Form()],
    db: Session = Depends(get_db),
):
    actor = lay_nguoi_dung(request)
    batch = lay_dot(db, batch_id)
    reason = str(reason or "").strip()
    if not reason:
        return redirect_workflow(batch_id, "invalid_reason")
    if batch is None or not co_quyen_quan_ly_xa(user=actor, batch=batch):
        return redirect_workflow(batch_id, "forbidden")

    state = lay_trang_thai_dia_ban(db, batch)
    if state.is_province_locked:
        return redirect_workflow(batch.id, "province_lock_blocks")

    state.is_commune_locked = False
    state.commune_locked_at = None
    state.commune_locked_by_user_id = None
    state.commune_lock_reason = None
    dong_bo_khoa_dot(batch=batch, state=state, actor=actor, reason=reason)
    ghi_nhat_ky(
        db=db,
        batch_id=batch.id,
        school_id=None,
        action="MO_KHOA_XA",
        actor=actor,
        reason=reason,
    )
    db.commit()
    return redirect_workflow(batch.id, "commune_unlocked")


def lay_nam_hoc_mac_dinh(db: Session) -> SchoolYear | None:
    return db.scalar(
        select(SchoolYear)
        .where(SchoolYear.is_active.is_(True))
        .order_by(SchoolYear.id.desc())
    )


@router.get("/dieu-hanh-trien-khai", response_class=HTMLResponse)
def dieu_hanh_trien_khai_toan_tinh(
    request: Request,
    school_year_id: str = "",
    status: str = "",
    db: Session = Depends(get_db),
):
    user = lay_nguoi_dung(request)
    role_code = normalize_role_code(user.get("role_code"))
    if role_code not in {*ADMIN_ROLE_CODES, DEPARTMENT_ROLE_CODE}:
        return RedirectResponse("/?status=forbidden", 303)

    years = list(
        db.scalars(
            select(SchoolYear)
            .where(SchoolYear.is_active.is_(True))
            .order_by(SchoolYear.id.desc())
        ).all()
    )
    try:
        selected_year_id = int(str(school_year_id).strip())
    except (TypeError, ValueError):
        default_year = lay_nam_hoc_mac_dinh(db)
        selected_year_id = default_year.id if default_year else 0

    batches = list(
        db.scalars(
            select(SurveyBatch)
            .options(
                selectinload(SurveyBatch.commune),
                selectinload(SurveyBatch.school_year),
            )
            .where(SurveyBatch.school_year_id == selected_year_id)
            .order_by(SurveyBatch.commune_id.asc())
        ).all()
    )
    batch_ids = [item.id for item in batches]
    states = {
        item.survey_batch_id: item
        for item in db.scalars(
            select(SurveyCommuneExecutionState).where(
                SurveyCommuneExecutionState.survey_batch_id.in_(batch_ids)
            )
        ).all()
    } if batch_ids else {}

    assignment_counts = {
        int(batch_id): int(total or 0)
        for batch_id, total in db.execute(
            select(
                SurveySchoolAssignment.survey_batch_id,
                func.count(SurveySchoolAssignment.id),
            )
            .where(SurveySchoolAssignment.survey_batch_id.in_(batch_ids))
            .group_by(SurveySchoolAssignment.survey_batch_id)
        ).all()
    } if batch_ids else {}

    rows = []
    for batch in batches:
        state = states.get(batch.id) or lay_trang_thai_dia_ban(db, batch)
        rows.append(
            {
                "batch": batch,
                "state": state,
                "assigned_school_total": assignment_counts.get(batch.id, 0),
            }
        )

    summary = {
        "commune_total": len(rows),
        "province_locked_total": sum(
            bool(item["state"].is_province_locked) for item in rows
        ),
        "commune_locked_total": sum(
            bool(item["state"].is_commune_locked) for item in rows
        ),
        "open_total": sum(
            not item["state"].is_province_locked
            and not item["state"].is_commune_locked
            for item in rows
        ),
        "assigned_school_total": sum(
            item["assigned_school_total"] for item in rows
        ),
    }

    return templates.TemplateResponse(
        request=request,
        name="surveys/province_execution_control.html",
        context={
            "nguoi_dung": user,
            "school_years": years,
            "selected_school_year_id": selected_year_id,
            "rows": rows,
            "summary": summary,
            "message": WORKFLOW_MESSAGES.get(status),
            "can_manage": is_admin_role(role_code),
        },
    )


@router.post("/dieu-hanh-trien-khai/khoa-toan-tinh")
def khoa_toan_tinh(
    request: Request,
    school_year_id: Annotated[int, Form()],
    reason: Annotated[str, Form()],
    db: Session = Depends(get_db),
):
    actor = lay_nguoi_dung(request)
    reason = str(reason or "").strip()
    if not is_admin_role(actor.get("role_code")):
        return RedirectResponse("/?status=forbidden", 303)
    if not reason:
        query = urlencode(
            {"school_year_id": school_year_id, "status": "invalid_reason"}
        )
        return RedirectResponse(
            f"/dieu-tra/dieu-hanh-trien-khai?{query}", 303
        )

    batches = list(
        db.scalars(
            select(SurveyBatch).where(
                SurveyBatch.school_year_id == school_year_id
            )
        ).all()
    )

    # === CHOT_DIEU_KIEN_KHOA_TINH_TAT_CA_XA_DA_KHOA_V2 ===
    # Khóa cấp Sở là khóa cuối cùng:
    # chỉ thực hiện khi tất cả xã/phường của năm học đã tự khóa cấp xã.
    if not batches:
        query = urlencode(
            {"school_year_id": school_year_id, "status": "province_no_batches"}
        )
        return RedirectResponse(
            f"/dieu-tra/dieu-hanh-trien-khai?{query}", 303
        )

    for batch in batches:
        state = lay_trang_thai_dia_ban(db, batch)
        if not bool(state.is_commune_locked):
            db.rollback()
            query = urlencode(
                {"school_year_id": school_year_id, "status": "province_not_ready"}
            )
            return RedirectResponse(
                f"/dieu-tra/dieu-hanh-trien-khai?{query}", 303
            )
    # === CHOT_DIEU_KIEN_KHOA_TINH_TAT_CA_XA_DA_KHOA_V2_END ===

    for batch in batches:
        state = lay_trang_thai_dia_ban(db, batch)
        state.is_province_locked = True
        state.province_locked_at = datetime.now()
        state.province_locked_by_user_id = actor.get("id")
        state.province_lock_reason = reason
        dong_bo_khoa_dot(batch=batch, state=state, actor=actor, reason=reason)
        ghi_nhat_ky(
            db=db,
            batch_id=batch.id,
            school_id=None,
            action="KHOA_TINH",
            actor=actor,
            reason=reason,
        )
    db.commit()
    query = urlencode(
        {"school_year_id": school_year_id, "status": "province_locked"}
    )
    return RedirectResponse(
        f"/dieu-tra/dieu-hanh-trien-khai?{query}", 303
    )


@router.post("/dieu-hanh-trien-khai/mo-khoa-toan-tinh")
def mo_khoa_toan_tinh(
    request: Request,
    school_year_id: Annotated[int, Form()],
    reason: Annotated[str, Form()],
    db: Session = Depends(get_db),
):
    actor = lay_nguoi_dung(request)
    reason = str(reason or "").strip()
    if not is_admin_role(actor.get("role_code")):
        return RedirectResponse("/?status=forbidden", 303)
    if not reason:
        query = urlencode(
            {"school_year_id": school_year_id, "status": "invalid_reason"}
        )
        return RedirectResponse(
            f"/dieu-tra/dieu-hanh-trien-khai?{query}", 303
        )

    batches = list(
        db.scalars(
            select(SurveyBatch).where(
                SurveyBatch.school_year_id == school_year_id
            )
        ).all()
    )
    for batch in batches:
        state = lay_trang_thai_dia_ban(db, batch)
        state.is_province_locked = False
        state.province_locked_at = None
        state.province_locked_by_user_id = None
        state.province_lock_reason = None
        dong_bo_khoa_dot(batch=batch, state=state, actor=actor, reason=reason)
        ghi_nhat_ky(
            db=db,
            batch_id=batch.id,
            school_id=None,
            action="MO_KHOA_TINH",
            actor=actor,
            reason=reason,
        )
    db.commit()
    query = urlencode(
        {"school_year_id": school_year_id, "status": "province_unlocked"}
    )
    return RedirectResponse(
        f"/dieu-tra/dieu-hanh-trien-khai?{query}", 303
    )
