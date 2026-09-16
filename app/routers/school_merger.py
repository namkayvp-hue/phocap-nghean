from __future__ import annotations

from pathlib import Path
import sqlite3
from typing import Any

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.permissions import is_admin_role, normalize_role_code
from app.services.school_merger_service import (
    CONFIRM_PHRASE,
    PLAN_APPROVE_PHRASE,
    PLAN_CANCEL_PHRASE,
    SchoolMergerError,
    approve_merger_plan,
    build_preview,
    cancel_merger_plan,
    delete_merger_plan_draft,
    execute_merge,
    get_merger_plan_record,
    list_communes,
    list_merger_plan_admin,
    list_merger_plans,
    list_school_years,
    list_schools,
    merger_history,
    save_merger_plan_draft,
)
from app.services.school_merger_official_registry import (
    list_official_registry_plans,
    official_registry_summary,
)
from app.services.school_merger_preview_service import (
    SchoolMergerPreviewError,
    build_official_plan_impact_preview,
)
from app.services.school_merger_execution_service import (
    OFFICIAL_CONFIRM_PHRASE,
    SchoolMergerExecutionError,
    annotate_official_plan_execution_status,
    execute_official_plan,
    get_official_execution_result,
)
from app.services.school_merger_source_audit_service import (
    SchoolMergerSourceAuditError,
    audit_official_plans,
    source_registry_summary,
)


APP_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(APP_DIR / "templates"))

router = APIRouter(
    prefix="/cong-cu-du-lieu/sap-nhap-truong",
    tags=["Sáp nhập trường"],
)

LEVEL_CHOICES = (
    ("", "Tất cả cấp học"),
    ("MN", "Mầm non"),
    ("TH", "Tiểu học"),
    ("THCS", "THCS"),
    ("THPT", "THPT"),
)

DISPLAY_CHOICES = (
    ("all", "Tất cả phương án"),
    ("mapped", "Nhóm đã xác định rõ nguồn → đích"),
    ("keep", "Giữ nguyên"),
    ("special", "Phương án đặc thù / cần đối chiếu"),
)

# Chỉ điều khiển phần THÔNG TIN hiển thị. Khi thực hiện thật, engine luôn xử lý
# đồng bộ toàn bộ dữ liệu bắt buộc theo chính sách; không cho partial merge.
DATA_VIEW_CHOICES = (
    ("all", "Tổng hợp tất cả dữ liệu"),
    ("accounts", "Tài khoản"),
    ("staff", "Đội ngũ"),
    ("classes", "Lớp học"),
    ("students", "Học sinh / enrollment"),
    ("survey", "Điều tra"),
    ("other", "Dữ liệu nghiệp vụ khác"),
)

PLAN_STATUS_CHOICES = (
    ("", "Tất cả trạng thái"),
    ("DRAFT", "Nháp"),
    ("APPROVED", "Đã duyệt – chờ thực hiện"),
    ("COMPLETED", "Đã hoàn thành"),
    ("CANCELLED", "Đã hủy"),
)


def _auth_user(request: Request) -> dict[str, Any]:
    return dict(request.scope.get("auth_user") or {})


def _admin_only(request: Request) -> bool:
    return is_admin_role(normalize_role_code(_auth_user(request).get("role_code")))


def _safe_int(value: Any) -> int | None:
    try:
        text = str(value or "").strip()
        return int(text) if text else None
    except (TypeError, ValueError):
        return None


def _safe_int_list(values: list[Any]) -> list[int]:
    result: list[int] = []
    for value in values:
        item = _safe_int(value)
        if item is not None and item not in result:
            result.append(item)
    return result


def _default_year_id(years: list[dict[str, Any]]) -> int | None:
    # Bài SÁP NHẬP V3 tiếp tục dùng phương án chính thức cho năm học 2026-2027.
    # CSDL hiện có thể có nhiều năm cùng is_active=1, vì vậy không chọn theo cờ active.
    official = next(
        (x for x in years if str(x.get("code") or "").replace("–", "-").replace("—", "-") == "2026-2027"),
        None,
    )
    if official is not None:
        return int(official["id"])
    active = next((x for x in years if x.get("is_active")), None)
    if active is not None:
        return int(active["id"])
    return int(years[0]["id"]) if years else None


def _normalize_display(value: str) -> str:
    value = str(value or "all").strip().lower()
    return value if value in {x[0] for x in DISPLAY_CHOICES} else "all"


def _normalize_data_view(value: str) -> str:
    value = str(value or "all").strip().lower()
    return value if value in {x[0] for x in DATA_VIEW_CHOICES} else "all"


def _page_context(
    request: Request,
    *,
    school_year_id: int | None = None,
    commune_id: int | None = None,
    level_code: str = "",
    display_mode: str = "all",
    data_view: str = "all",
    preview: dict[str, Any] | None = None,
    error_message: str = "",
    status_message: str = "",
    backup_name: str = "",
) -> dict[str, Any]:
    years = list_school_years()
    if school_year_id is None:
        school_year_id = _default_year_id(years)

    communes = list_communes()
    selected_commune = next(
        (x for x in communes if commune_id is not None and int(x["id"]) == int(commune_id)),
        None,
    )

    display_mode = _normalize_display(display_mode)
    data_view = _normalize_data_view(data_view)

    plans = (
        list_official_registry_plans(
            school_year_id=school_year_id,
            commune_id=commune_id,
            level_code=level_code or None,
            display_mode=display_mode,
        )
        if school_year_id is not None and commune_id is not None
        else []
    )

    return {
        "nguoi_dung": _auth_user(request),
        "school_years": years,
        "communes": communes,
        "selected_commune": selected_commune,
        "selected_commune_name": str((selected_commune or {}).get("name") or ""),
        "plans": plans,
        "selected_school_year_id": school_year_id,
        "selected_commune_id": commune_id,
        "selected_level_code": str(level_code or "").upper(),
        "selected_display_mode": display_mode,
        "selected_data_view": data_view,
        "level_choices": LEVEL_CHOICES,
        "display_choices": DISPLAY_CHOICES,
        "data_view_choices": DATA_VIEW_CHOICES,
        "preview": preview,
        "confirm_phrase": CONFIRM_PHRASE,
        "error_message": error_message,
        "status_message": status_message,
        "backup_name": backup_name,
        "history": merger_history(limit=15),
        "execution_enabled": False,
        "official_registry_summary": official_registry_summary(),
    }



def _normalize_plan_status(value: str) -> str:
    value = str(value or "").strip().upper()
    return value if value in {x[0] for x in PLAN_STATUS_CHOICES} else ""


def _plan_page_context(
    request: Request,
    *,
    school_year_id: int | None = None,
    commune_id: int | None = None,
    level_code: str = "",
    plan_status: str = "",
    edit_plan_id: str = "",
    form_draft: dict[str, Any] | None = None,
    error_message: str = "",
    status_message: str = "",
) -> dict[str, Any]:
    years = list_school_years()
    if school_year_id is None:
        school_year_id = _default_year_id(years)

    communes = list_communes()
    selected_commune = next(
        (x for x in communes if commune_id is not None and int(x["id"]) == int(commune_id)),
        None,
    )
    level = str(level_code or "").strip().upper()
    status = _normalize_plan_status(plan_status)

    schools: list[dict[str, Any]] = []
    if school_year_id is not None and commune_id is not None and level:
        schools = list_schools(
            year_id=int(school_year_id),
            commune_id=int(commune_id),
            level_code=level,
            include_inactive=False,
        )

    plans = list_official_registry_plans(
        school_year_id=school_year_id,
        commune_id=commune_id,
        level_code=level or None,
        display_mode="all",
    )
    plans = annotate_official_plan_execution_status(plans)

    edit_plan = None
    # Bài SÁP NHẬP V2 chỉ đọc/đối chiếu phương án từ Excel chính thức.
    # Không mở chế độ soạn/sửa/phê duyệt thủ công.

    draft = dict(form_draft or {})
    if edit_plan and not draft:
        draft = {
            "plan_id": edit_plan.get("id") or "",
            "document_code": edit_plan.get("document_code") or "",
            "document_title": edit_plan.get("document_title") or "",
            "document_date": edit_plan.get("document_date") or "",
            "note": edit_plan.get("note") or "",
            "source_school_ids": list(edit_plan.get("source_school_ids") or []),
            "target_school_id": edit_plan.get("target_school_id"),
        }

    draft.setdefault("plan_id", "")
    draft.setdefault("document_code", "")
    draft.setdefault("document_title", "")
    draft.setdefault("document_date", "")
    draft.setdefault("note", "")
    draft.setdefault("source_school_ids", [])
    draft.setdefault("target_school_id", None)

    return {
        "nguoi_dung": _auth_user(request),
        "school_years": years,
        "communes": communes,
        "selected_commune": selected_commune,
        "selected_commune_name": str((selected_commune or {}).get("name") or ""),
        "selected_school_year_id": school_year_id,
        "selected_commune_id": commune_id,
        "selected_level_code": level,
        "selected_plan_status": status,
        "level_choices": LEVEL_CHOICES,
        "plan_status_choices": PLAN_STATUS_CHOICES,
        "schools": schools,
        "plans": plans,
        "edit_plan": edit_plan,
        "draft": draft,
        "approve_phrase": PLAN_APPROVE_PHRASE,
        "cancel_phrase": PLAN_CANCEL_PHRASE,
        "error_message": error_message,
        "status_message": status_message,
        "execution_enabled": True,
        "official_confirm_phrase": OFFICIAL_CONFIRM_PHRASE,
        "official_registry_summary": official_registry_summary(),
    }


def _plan_manager_template(
    request: Request,
    *,
    status_code: int = 200,
    **kwargs: Any,
):
    return templates.TemplateResponse(
        request=request,
        name="data_tools/school_merger_plans.html",
        context=_plan_page_context(request, **kwargs),
        status_code=status_code,
    )


@router.get("", response_class=HTMLResponse)
def merger_page(
    request: Request,
    school_year_id: str | None = Query(default=None),
    commune_id: str | None = Query(default=None),
    level_code: str = Query(default=""),
    display_mode: str = Query(default="all"),
    data_view: str = Query(default="all"),
    # Giữ tương thích URL V9.2/V9.2.1 cũ; không còn dùng để chọn trường.
    include_inactive: str = Query(default=""),
    status: str = Query(default=""),
    backup_name: str = Query(default=""),
):
    if not _admin_only(request):
        return RedirectResponse(url="/?status=forbidden", status_code=303)

    status_message = ""
    if status == "success":
        status_message = (
            "Sáp nhập trường đã hoàn thành đúng phương án và vượt qua kiểm tra "
            "integrity/FK. Dữ liệu lịch sử năm cũ được giữ nguyên."
        )

    return templates.TemplateResponse(
        request=request,
        name="data_tools/school_merger.html",
        context=_page_context(
            request,
            school_year_id=_safe_int(school_year_id),
            commune_id=_safe_int(commune_id),
            level_code=level_code,
            display_mode=display_mode,
            data_view=data_view,
            status_message=status_message,
            backup_name=backup_name,
        ),
    )


@router.post("/xem-truoc", response_class=HTMLResponse)
def merger_preview(
    request: Request,
    school_year_id: str = Form(default=""),
    commune_id: str = Form(default=""),
    level_code: str = Form(default=""),
    display_mode: str = Form(default="all"),
    data_view: str = Form(default="all"),
    plan_id: str = Form(default=""),
    target_school_id: str = Form(default=""),
    source_school_ids: list[str] = Form(default=[]),
):
    if not _admin_only(request):
        return RedirectResponse(url="/?status=forbidden", status_code=303)

    # Bài SÁP NHẬP V2: chưa mở XEM TRƯỚC kỹ thuật / THỰC HIỆN.
    return templates.TemplateResponse(
        request=request,
        name="data_tools/school_merger.html",
        context=_page_context(
            request,
            school_year_id=_safe_int(school_year_id),
            commune_id=_safe_int(commune_id),
            level_code=level_code,
            display_mode=display_mode,
            data_view=data_view,
            error_message=(
                "Bài SÁP NHẬP V2 đang khóa thao tác thực hiện. "
                "Hiện chỉ chuẩn hóa và đối chiếu phương án chính thức từ file PA sáp xếp phần mềm.xlsx."
            ),
        ),
        status_code=409,
    )

    year_id = _safe_int(school_year_id)
    target_id = _safe_int(target_school_id)
    source_ids = _safe_int_list(source_school_ids)
    commune_id_int = _safe_int(commune_id)

    if year_id is None or target_id is None or not source_ids:
        return templates.TemplateResponse(
            request=request,
            name="data_tools/school_merger.html",
            context=_page_context(
                request,
                school_year_id=year_id,
                commune_id=commune_id_int,
                level_code=level_code,
                display_mode=display_mode,
                data_view=data_view,
                error_message=(
                    "Phương án sáp nhập không đầy đủ. Hãy chọn lại đúng phương án "
                    "được hiển thị theo văn bản."
                ),
            ),
            status_code=400,
        )

    preview = build_preview(
        selected_year_id=year_id,
        target_school_id=target_id,
        source_ids=source_ids,
        require_active_sources=True,
    )

    actual_plan_id = str((preview.get("approved_plan") or {}).get("id") or "")
    if plan_id and actual_plan_id != str(plan_id):
        preview.setdefault("blockers", []).append(
            "Mã phương án trên màn hình không khớp phương án backend xác nhận."
        )
        preview["safe_to_execute"] = False

    if commune_id_int is None and preview.get("target_school"):
        commune_id_int = _safe_int(preview["target_school"].get("commune_id"))

    return templates.TemplateResponse(
        request=request,
        name="data_tools/school_merger.html",
        context=_page_context(
            request,
            school_year_id=year_id,
            commune_id=commune_id_int,
            level_code=level_code,
            display_mode=display_mode,
            data_view=data_view,
            preview=preview,
        ),
        status_code=200 if preview.get("safe_to_execute") else 409,
    )


@router.post("/thuc-hien", response_class=HTMLResponse)
def merger_execute(
    request: Request,
    school_year_id: str = Form(default=""),
    commune_id: str = Form(default=""),
    level_code: str = Form(default=""),
    display_mode: str = Form(default="all"),
    data_view: str = Form(default="all"),
    plan_id: str = Form(default=""),
    target_school_id: str = Form(default=""),
    source_school_ids: list[str] = Form(default=[]),
    plan_fingerprint: str = Form(default=""),
    confirm_scope: str = Form(default=""),
    confirm_text: str = Form(default=""),
):
    if not _admin_only(request):
        return RedirectResponse(url="/?status=forbidden", status_code=303)

    # Bài SÁP NHẬP V2: chặn tuyệt đối endpoint thực hiện ở backend.
    return templates.TemplateResponse(
        request=request,
        name="data_tools/school_merger.html",
        context=_page_context(
            request,
            school_year_id=_safe_int(school_year_id),
            commune_id=_safe_int(commune_id),
            level_code=level_code,
            display_mode=display_mode,
            data_view=data_view,
            error_message=(
                "Chức năng THỰC HIỆN SÁP NHẬP chưa được mở trong Bài SÁP NHẬP V2. "
                "Không có thay đổi nào được ghi vào database."
            ),
        ),
        status_code=409,
    )

    year_id = _safe_int(school_year_id)
    target_id = _safe_int(target_school_id)
    source_ids = _safe_int_list(source_school_ids)
    commune_id_int = _safe_int(commune_id)

    if year_id is None or target_id is None or not source_ids:
        return templates.TemplateResponse(
            request=request,
            name="data_tools/school_merger.html",
            context=_page_context(
                request,
                school_year_id=year_id,
                commune_id=commune_id_int,
                level_code=level_code,
                display_mode=display_mode,
                data_view=data_view,
                error_message=(
                    "Thông tin phương án sáp nhập không đầy đủ. Hãy xem trước lại."
                ),
            ),
            status_code=400,
        )

    preview = build_preview(
        selected_year_id=year_id,
        target_school_id=target_id,
        source_ids=source_ids,
        require_active_sources=True,
    )

    actual_plan_id = str((preview.get("approved_plan") or {}).get("id") or "")
    if plan_id and actual_plan_id != str(plan_id):
        error = "Mã phương án không khớp. Hãy quay lại và xem trước đúng phương án."
    elif confirm_scope != "yes":
        error = (
            "Bạn chưa xác nhận đã dừng nhập liệu và kiểm tra đúng phương án, "
            "trường nguồn, trường đích."
        )
    elif confirm_text.strip().upper() != CONFIRM_PHRASE:
        error = f"Câu xác nhận chưa đúng. Hãy nhập chính xác: {CONFIRM_PHRASE}"
    elif not preview.get("safe_to_execute"):
        error = (
            "Phương án hiện không an toàn hoặc không còn ở trạng thái được phép "
            "thực hiện. Hãy xem cảnh báo/chặn bên dưới."
        )
    elif plan_fingerprint != preview.get("fingerprint"):
        error = (
            "Dữ liệu/phương án đã thay đổi từ lúc xem trước. "
            "Hãy bấm Xem trước lại trước khi thực hiện."
        )
    else:
        error = ""

    if error:
        return templates.TemplateResponse(
            request=request,
            name="data_tools/school_merger.html",
            context=_page_context(
                request,
                school_year_id=year_id,
                commune_id=commune_id_int,
                level_code=level_code,
                display_mode=display_mode,
                data_view=data_view,
                preview=preview,
                error_message=error,
            ),
            status_code=400,
        )

    try:
        result = execute_merge(
            selected_year_id=year_id,
            target_school_id=target_id,
            source_ids=source_ids,
            actor=_auth_user(request),
            expected_fingerprint=plan_fingerprint,
        )
    except (SchoolMergerError, sqlite3.Error) as exc:
        return templates.TemplateResponse(
            request=request,
            name="data_tools/school_merger.html",
            context=_page_context(
                request,
                school_year_id=year_id,
                commune_id=commune_id_int,
                level_code=level_code,
                display_mode=display_mode,
                data_view=data_view,
                preview=build_preview(
                    selected_year_id=year_id,
                    target_school_id=target_id,
                    source_ids=source_ids,
                    require_active_sources=False,
                ),
                error_message="Sáp nhập KHÔNG thành công. " + str(exc),
            ),
            status_code=500,
        )
    except Exception as exc:
        return templates.TemplateResponse(
            request=request,
            name="data_tools/school_merger.html",
            context=_page_context(
                request,
                school_year_id=year_id,
                commune_id=commune_id_int,
                level_code=level_code,
                display_mode=display_mode,
                data_view=data_view,
                error_message="Sáp nhập KHÔNG thành công. " + str(exc),
            ),
            status_code=500,
        )

    return RedirectResponse(
        url=(
            "/cong-cu-du-lieu/sap-nhap-truong"
            f"?school_year_id={year_id}"
            f"&commune_id={commune_id_int or ''}"
            f"&level_code={level_code}"
            "&display_mode=completed"
            f"&data_view={_normalize_data_view(data_view)}"
            "&status=success"
            f"&backup_name={result['backup_name']}"
        ),
        status_code=303,
    )

# ---------------------------------------------------------------------------
# V9.4 - QUẢN LÝ / NHẬP PHƯƠNG ÁN THEO VĂN BẢN
# ---------------------------------------------------------------------------

@router.get("/phuong-an/xem-truoc/{plan_id}", response_class=HTMLResponse)
def merger_official_plan_preview(
    request: Request,
    plan_id: str,
    school_year_id: str | None = Query(default=None),
    commune_id: str | None = Query(default=None),
    level_code: str = Query(default=""),
):
    if not _admin_only(request):
        return RedirectResponse(url="/?status=forbidden", status_code=303)

    try:
        preview = build_official_plan_impact_preview(plan_id)
        error_message = ""
        status_code = 200
    except SchoolMergerPreviewError as exc:
        preview = None
        error_message = str(exc)
        status_code = 404
    except (SchoolMergerError, sqlite3.Error) as exc:
        preview = None
        error_message = "Không thể lập bản xem trước kỹ thuật: " + str(exc)
        status_code = 409

    return templates.TemplateResponse(
        request=request,
        name="data_tools/school_merger_preview.html",
        context={
            "nguoi_dung": _auth_user(request),
            "preview": preview,
            "error_message": error_message,
            "selected_school_year_id": _safe_int(school_year_id),
            "selected_commune_id": _safe_int(commune_id),
            "selected_level_code": str(level_code or "").strip().upper(),
            "execution_enabled": bool(
                preview
                and not preview.get("keep_only")
                and preview.get("safe_for_future_execution")
                and preview.get("simulation_ok")
                and preview.get("v41_state_check_ok")
                and preview.get("v43_source_check_ok")
                and not preview.get("completed_operation")
            ),
            "official_confirm_phrase": OFFICIAL_CONFIRM_PHRASE,
            "official_registry_summary": official_registry_summary(),
        },
        status_code=status_code,
    )


@router.post("/phuong-an/thuc-hien/{plan_id}", response_class=HTMLResponse)
def merger_official_plan_execute(
    request: Request,
    plan_id: str,
    school_year_id: str = Form(default=""),
    commune_id: str = Form(default=""),
    level_code: str = Form(default=""),
    impact_state_fingerprint: str = Form(default=""),
    source_audit_fingerprint: str = Form(default=""),
    confirm_scope: str = Form(default=""),
    confirm_text: str = Form(default=""),
):
    if not _admin_only(request):
        return RedirectResponse(url="/?status=forbidden", status_code=303)

    year_id = _safe_int(school_year_id)
    commune_id_int = _safe_int(commune_id)
    level = str(level_code or "").strip().upper()

    try:
        execute_official_plan(
            str(plan_id),
            actor=_auth_user(request),
            expected_impact_state_fingerprint=str(impact_state_fingerprint or ""),
            expected_source_audit_fingerprint=str(source_audit_fingerprint or ""),
            confirmation_scope=str(confirm_scope or ""),
            confirmation_text=str(confirm_text or ""),
        )
    except SchoolMergerExecutionError as exc:
        try:
            preview = build_official_plan_impact_preview(str(plan_id))
        except Exception:
            preview = None
        return templates.TemplateResponse(
            request=request,
            name="data_tools/school_merger_preview.html",
            context={
                "nguoi_dung": _auth_user(request),
                "preview": preview,
                "error_message": "Sáp nhập KHÔNG thành công. " + str(exc),
                "selected_school_year_id": year_id,
                "selected_commune_id": commune_id_int,
                "selected_level_code": level,
                "execution_enabled": bool(
                    preview
                    and not preview.get("keep_only")
                    and preview.get("safe_for_future_execution")
                    and preview.get("simulation_ok")
                    and preview.get("v41_state_check_ok")
                    and preview.get("v43_source_check_ok")
                    and not preview.get("completed_operation")
                ),
                "official_confirm_phrase": OFFICIAL_CONFIRM_PHRASE,
                "official_registry_summary": official_registry_summary(),
            },
            status_code=409,
        )

    return RedirectResponse(
        url=(
            f"/cong-cu-du-lieu/sap-nhap-truong/phuong-an/ket-qua/{plan_id}"
            f"?school_year_id={year_id or ''}"
            f"&commune_id={commune_id_int or ''}"
            f"&level_code={level}"
        ),
        status_code=303,
    )


@router.get("/phuong-an/ket-qua/{plan_id}", response_class=HTMLResponse)
def merger_official_plan_result(
    request: Request,
    plan_id: str,
    school_year_id: str | None = Query(default=None),
    commune_id: str | None = Query(default=None),
    level_code: str = Query(default=""),
):
    if not _admin_only(request):
        return RedirectResponse(url="/?status=forbidden", status_code=303)

    result = get_official_execution_result(str(plan_id))
    if result is None:
        return templates.TemplateResponse(
            request=request,
            name="data_tools/school_merger_result.html",
            context={
                "nguoi_dung": _auth_user(request),
                "result": None,
                "error_message": "Chưa có nhật ký thực hiện V4/V4.1 cho phương án này.",
                "selected_school_year_id": _safe_int(school_year_id),
                "selected_commune_id": _safe_int(commune_id),
                "selected_level_code": str(level_code or "").strip().upper(),
            },
            status_code=404,
        )

    return templates.TemplateResponse(
        request=request,
        name="data_tools/school_merger_result.html",
        context={
            "nguoi_dung": _auth_user(request),
            "result": result,
            "error_message": "",
            "selected_school_year_id": _safe_int(school_year_id),
            "selected_commune_id": _safe_int(commune_id),
            "selected_level_code": str(level_code or "").strip().upper(),
        },
    )


@router.get("/phuong-an/kiem-tra-nguon", response_class=HTMLResponse)
def merger_source_audit_dashboard(
    request: Request,
    school_year_id: str | None = Query(default=None),
    commune_id: str | None = Query(default=None),
    level_code: str = Query(default=""),
):
    if not _admin_only(request):
        return RedirectResponse(url="/?status=forbidden", status_code=303)
    year_id = _safe_int(school_year_id)
    commune_id_int = _safe_int(commune_id)
    level = str(level_code or "").strip().upper()
    try:
        audit = audit_official_plans(
            school_year_id=year_id,
            commune_id=commune_id_int,
            level_code=level or None,
            include_keep=False,
        )
        error_message = ""
        status_code = 200
    except (SchoolMergerSourceAuditError, SchoolMergerError, sqlite3.Error) as exc:
        audit = {"rows": [], "total": 0, "pass_count": 0, "block_count": 0, "registry_summary": source_registry_summary()}
        error_message = str(exc)
        status_code = 409
    return templates.TemplateResponse(
        request=request,
        name="data_tools/school_merger_source_audit.html",
        context={
            "nguoi_dung": _auth_user(request),
            "audit": audit,
            "error_message": error_message,
            "selected_school_year_id": year_id,
            "selected_commune_id": commune_id_int,
            "selected_level_code": level,
            "school_years": list_school_years(),
            "communes": list_communes(),
            "level_choices": LEVEL_CHOICES,
        },
        status_code=status_code,
    )


@router.get("/phuong-an", response_class=HTMLResponse)
def merger_plan_manager(
    request: Request,
    school_year_id: str | None = Query(default=None),
    commune_id: str | None = Query(default=None),
    level_code: str = Query(default=""),
    plan_status: str = Query(default=""),
    edit_plan_id: str = Query(default=""),
    status: str = Query(default=""),
):
    if not _admin_only(request):
        return RedirectResponse(url="/?status=forbidden", status_code=303)

    message_map = {
        "saved": "Đã lưu phương án ở trạng thái NHÁP.",
        "approved": "Đã kiểm tra kỹ thuật và PHÊ DUYỆT phương án. Phương án đã xuất hiện ở màn hình Sáp nhập trường.",
        "cancelled": "Đã hủy phương án; phương án không còn được phép thực hiện.",
        "deleted": "Đã xóa phương án NHÁP.",
    }
    return _plan_manager_template(
        request,
        school_year_id=_safe_int(school_year_id),
        commune_id=_safe_int(commune_id),
        level_code=level_code,
        plan_status=plan_status,
        edit_plan_id=edit_plan_id,
        status_message=message_map.get(str(status or ""), ""),
    )


@router.post("/phuong-an/luu-nhap", response_class=HTMLResponse)
def merger_plan_save_draft(
    request: Request,
    school_year_id: str = Form(default=""),
    commune_id: str = Form(default=""),
    level_code: str = Form(default=""),
    plan_id: str = Form(default=""),
    document_code: str = Form(default=""),
    document_title: str = Form(default=""),
    document_date: str = Form(default=""),
    note: str = Form(default=""),
    source_school_ids: list[str] = Form(default=[]),
    target_school_id: str = Form(default=""),
):
    if not _admin_only(request):
        return RedirectResponse(url="/?status=forbidden", status_code=303)

    year_id = _safe_int(school_year_id)
    commune_id_int = _safe_int(commune_id)
    target_id = _safe_int(target_school_id)
    source_ids = _safe_int_list(source_school_ids)
    draft = {
        "plan_id": plan_id,
        "document_code": document_code,
        "document_title": document_title,
        "document_date": document_date,
        "note": note,
        "source_school_ids": source_ids,
        "target_school_id": target_id,
    }

    if year_id is None or commune_id_int is None or not level_code or target_id is None:
        return _plan_manager_template(
            request,
            school_year_id=year_id,
            commune_id=commune_id_int,
            level_code=level_code,
            form_draft=draft,
            error_message="Phải chọn đủ Năm học – Xã/phường – Cấp học – Trường nguồn – Trường đích.",
            status_code=400,
        )

    try:
        save_merger_plan_draft(
            school_year_id=year_id,
            commune_id=commune_id_int,
            level_code=level_code,
            document_code=document_code,
            document_title=document_title,
            document_date=document_date,
            source_school_ids=source_ids,
            target_school_id=target_id,
            note=note,
            actor=_auth_user(request),
            plan_id=plan_id or None,
        )
    except SchoolMergerError as exc:
        return _plan_manager_template(
            request,
            school_year_id=year_id,
            commune_id=commune_id_int,
            level_code=level_code,
            edit_plan_id=plan_id,
            form_draft=draft,
            error_message=str(exc),
            status_code=400,
        )

    return RedirectResponse(
        url=(
            "/cong-cu-du-lieu/sap-nhap-truong/phuong-an"
            f"?school_year_id={year_id}&commune_id={commune_id_int}"
            f"&level_code={str(level_code).upper()}&status=saved"
        ),
        status_code=303,
    )


@router.post("/phuong-an/phe-duyet", response_class=HTMLResponse)
def merger_plan_approve(
    request: Request,
    plan_id: str = Form(default=""),
    school_year_id: str = Form(default=""),
    commune_id: str = Form(default=""),
    level_code: str = Form(default=""),
    confirm_text: str = Form(default=""),
):
    if not _admin_only(request):
        return RedirectResponse(url="/?status=forbidden", status_code=303)
    year_id = _safe_int(school_year_id)
    commune_id_int = _safe_int(commune_id)

    if confirm_text.strip().upper() != PLAN_APPROVE_PHRASE:
        return _plan_manager_template(
            request,
            school_year_id=year_id,
            commune_id=commune_id_int,
            level_code=level_code,
            error_message=f"Câu xác nhận chưa đúng. Hãy nhập chính xác: {PLAN_APPROVE_PHRASE}",
            status_code=400,
        )
    try:
        approve_merger_plan(plan_id=plan_id, actor=_auth_user(request))
    except SchoolMergerError as exc:
        return _plan_manager_template(
            request,
            school_year_id=year_id,
            commune_id=commune_id_int,
            level_code=level_code,
            error_message=str(exc),
            status_code=409,
        )

    return RedirectResponse(
        url=(
            "/cong-cu-du-lieu/sap-nhap-truong/phuong-an"
            f"?school_year_id={year_id or ''}&commune_id={commune_id_int or ''}"
            f"&level_code={str(level_code).upper()}&status=approved"
        ),
        status_code=303,
    )


@router.post("/phuong-an/huy", response_class=HTMLResponse)
def merger_plan_cancel(
    request: Request,
    plan_id: str = Form(default=""),
    school_year_id: str = Form(default=""),
    commune_id: str = Form(default=""),
    level_code: str = Form(default=""),
    confirm_text: str = Form(default=""),
):
    if not _admin_only(request):
        return RedirectResponse(url="/?status=forbidden", status_code=303)
    year_id = _safe_int(school_year_id)
    commune_id_int = _safe_int(commune_id)

    if confirm_text.strip().upper() != PLAN_CANCEL_PHRASE:
        return _plan_manager_template(
            request,
            school_year_id=year_id,
            commune_id=commune_id_int,
            level_code=level_code,
            error_message=f"Câu xác nhận chưa đúng. Hãy nhập chính xác: {PLAN_CANCEL_PHRASE}",
            status_code=400,
        )
    try:
        cancel_merger_plan(plan_id=plan_id, actor=_auth_user(request))
    except SchoolMergerError as exc:
        return _plan_manager_template(
            request,
            school_year_id=year_id,
            commune_id=commune_id_int,
            level_code=level_code,
            error_message=str(exc),
            status_code=409,
        )

    return RedirectResponse(
        url=(
            "/cong-cu-du-lieu/sap-nhap-truong/phuong-an"
            f"?school_year_id={year_id or ''}&commune_id={commune_id_int or ''}"
            f"&level_code={str(level_code).upper()}&status=cancelled"
        ),
        status_code=303,
    )


@router.post("/phuong-an/xoa-nhap", response_class=HTMLResponse)
def merger_plan_delete_draft(
    request: Request,
    plan_id: str = Form(default=""),
    school_year_id: str = Form(default=""),
    commune_id: str = Form(default=""),
    level_code: str = Form(default=""),
):
    if not _admin_only(request):
        return RedirectResponse(url="/?status=forbidden", status_code=303)
    try:
        delete_merger_plan_draft(plan_id=plan_id, actor=_auth_user(request))
    except SchoolMergerError as exc:
        return _plan_manager_template(
            request,
            school_year_id=_safe_int(school_year_id),
            commune_id=_safe_int(commune_id),
            level_code=level_code,
            error_message=str(exc),
            status_code=409,
        )
    return RedirectResponse(
        url=(
            "/cong-cu-du-lieu/sap-nhap-truong/phuong-an"
            f"?school_year_id={_safe_int(school_year_id) or ''}"
            f"&commune_id={_safe_int(commune_id) or ''}"
            f"&level_code={str(level_code).upper()}&status=deleted"
        ),
        status_code=303,
    )

