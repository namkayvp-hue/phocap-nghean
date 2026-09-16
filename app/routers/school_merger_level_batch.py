from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.permissions import is_admin_role, normalize_role_code
from app.services.school_merger_service import list_school_years
from app.services.school_merger_level_batch_service import (
    LEVEL_BATCH_CONFIRM_PHRASE,
    SchoolMergerLevelBatchError,
    build_level_batch_preview,
    execute_level_batch,
    get_level_batch_result,
)

router = APIRouter(prefix="/cong-cu-du-lieu/sap-nhap-truong", tags=["Sáp nhập toàn cấp"])
templates = Jinja2Templates(directory="app/templates")
LEVEL_CHOICES = (("MN", "Mầm non"), ("TH", "Tiểu học"), ("THCS", "THCS"))


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


def _default_year_id(years: list[dict[str, Any]]) -> int | None:
    official = next(
        (x for x in years if str(x.get("code") or "").replace("–", "-").replace("—", "-") == "2026-2027"),
        None,
    )
    if official is not None:
        return int(official["id"])
    active = next((x for x in years if x.get("is_active")), None)
    return int(active["id"]) if active is not None else (int(years[0]["id"]) if years else None)


@router.get("/toan-cap", response_class=HTMLResponse)
def level_batch_page(
    request: Request,
    school_year_id: str | None = Query(default=None),
    level_code: str = Query(default="TH"),
):
    if not _admin_only(request):
        return RedirectResponse(url="/?status=forbidden", status_code=303)
    years = list_school_years()
    year_id = _safe_int(school_year_id) or _default_year_id(years)
    level = str(level_code or "TH").strip().upper()
    if level not in {x[0] for x in LEVEL_CHOICES}:
        level = "TH"
    preview = None
    error_message = ""
    if year_id is not None:
        try:
            preview = build_level_batch_preview(school_year_id=year_id, level_code=level)
        except Exception as exc:
            error_message = str(exc)
    return templates.TemplateResponse(
        request=request,
        name="data_tools/school_merger_level_batch.html",
        context={
            "nguoi_dung": _auth_user(request),
            "school_years": years,
            "selected_school_year_id": year_id,
            "selected_level_code": level,
            "level_choices": LEVEL_CHOICES,
            "preview": preview,
            "error_message": error_message,
            "confirm_phrase": LEVEL_BATCH_CONFIRM_PHRASE,
        },
        status_code=200 if not error_message else 409,
    )


@router.post("/toan-cap/thuc-hien")
def level_batch_execute(
    request: Request,
    school_year_id: str = Form(default=""),
    level_code: str = Form(default=""),
    expected_batch_fingerprint: str = Form(default=""),
    confirmation_scope: str = Form(default=""),
    confirmation_text: str = Form(default=""),
):
    if not _admin_only(request):
        return RedirectResponse(url="/?status=forbidden", status_code=303)
    year_id = _safe_int(school_year_id)
    level = str(level_code or "TH").strip().upper()
    if year_id is None:
        return RedirectResponse(url="/cong-cu-du-lieu/sap-nhap-truong/toan-cap", status_code=303)
    try:
        result = execute_level_batch(
            school_year_id=year_id,
            level_code=level,
            actor=_auth_user(request),
            expected_batch_fingerprint=expected_batch_fingerprint,
            confirmation_scope=confirmation_scope,
            confirmation_text=confirmation_text,
        )
    except SchoolMergerLevelBatchError as exc:
        years = list_school_years()
        try:
            preview = build_level_batch_preview(school_year_id=year_id, level_code=level)
        except Exception:
            preview = None
        return templates.TemplateResponse(
            request=request,
            name="data_tools/school_merger_level_batch.html",
            context={
                "nguoi_dung": _auth_user(request),
                "school_years": years,
                "selected_school_year_id": year_id,
                "selected_level_code": level,
                "level_choices": LEVEL_CHOICES,
                "preview": preview,
                "error_message": "Sáp nhập toàn cấp KHÔNG thành công. " + str(exc),
                "confirm_phrase": LEVEL_BATCH_CONFIRM_PHRASE,
            },
            status_code=409,
        )
    return RedirectResponse(
        url=f"/cong-cu-du-lieu/sap-nhap-truong/toan-cap/ket-qua/{result['batch_id']}",
        status_code=303,
    )


@router.get("/toan-cap/ket-qua/{batch_id}", response_class=HTMLResponse)
def level_batch_result(request: Request, batch_id: int):
    if not _admin_only(request):
        return RedirectResponse(url="/?status=forbidden", status_code=303)
    result = get_level_batch_result(int(batch_id))
    return templates.TemplateResponse(
        request=request,
        name="data_tools/school_merger_level_batch_result.html",
        context={
            "nguoi_dung": _auth_user(request),
            "result": result,
            "error_message": "" if result else "Không tìm thấy nhật ký sáp nhập toàn cấp.",
        },
        status_code=200 if result else 404,
    )
