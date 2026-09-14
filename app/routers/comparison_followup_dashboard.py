from __future__ import annotations

from datetime import date, datetime, timedelta
from io import BytesIO
from math import ceil
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.comparison_models import StudentSurveyComparisonSignoff
from app.database import get_db
from app.models import Commune, SchoolYear
from app.permissions import is_province_reader
from app.routers.surveys import BATCH_STATUS_LABELS, lay_thong_tin_nguoi_dung
from app.survey_models import SurveyBatch


APP_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(APP_DIR / "templates"))

router = APIRouter(
    prefix="/dieu-tra",
    tags=["Giám sát và đôn đốc đối chiếu học sinh"],
)

PAGE_SIZE_OPTIONS = (50, 100, 200)

GROUP_LABELS = {
    "": "Tất cả địa bàn",
    "NEED_FOLLOWUP": "Cần đôn đốc",
    "URGENT": "Ưu tiên cao",
    "OVERDUE": "Quá hạn",
    "DUE_SOON": "Sắp đến hạn (7 ngày)",
    "REOPENED": "Đã mở lại",
    "UNSIGNED": "Chưa chốt",
    "MISSING_BATCH": "Chưa có đợt",
    "SIGNED": "Đã chốt",
}

STATE_LABELS = {
    "SIGNED": "Đã chốt",
    "REOPENED": "Đã mở lại",
    "UNSIGNED": "Chưa chốt",
    "MISSING_BATCH": "Chưa có đợt",
}

ACTION_LABELS = {
    "CHOT": "Đã chốt kết quả đối chiếu",
    "MO_LAI": "Đã mở lại để xử lý",
}

PRIORITY_META = {
    "OVERDUE": (0, "Khẩn cấp", "priority-critical"),
    "MISSING_BATCH": (1, "Khẩn cấp", "priority-critical"),
    "REOPENED": (2, "Ưu tiên cao", "priority-high"),
    "DUE_SOON": (3, "Ưu tiên cao", "priority-high"),
    "UNSIGNED": (4, "Cần đôn đốc", "priority-medium"),
    "NOT_STARTED": (5, "Theo dõi", "priority-low"),
    "SIGNED": (9, "Hoàn thành", "priority-done"),
}


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _parse_optional_int(value: Any) -> int | None:
    text = str(value or "").strip()
    return int(text) if text.isdigit() else None


def _format_date(value: date | None) -> str:
    return value.strftime("%d/%m/%Y") if value is not None else "—"


def _format_datetime(value: datetime | None) -> str:
    return value.strftime("%d/%m/%Y %H:%M") if value is not None else "—"


def _load_school_years(db: Session) -> list[SchoolYear]:
    return list(
        db.scalars(
            select(SchoolYear).order_by(
                SchoolYear.code.desc(),
                SchoolYear.id.desc(),
            )
        ).all()
    )


def _default_year_id(
    school_years: list[SchoolYear],
    requested_year_id: int | None,
) -> int | None:
    valid_ids = {item.id for item in school_years}
    if requested_year_id in valid_ids:
        return requested_year_id
    return school_years[0].id if school_years else None


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


def _deadline_details(
    batch: SurveyBatch | None,
    today: date,
) -> tuple[int | None, str]:
    if batch is None:
        return None, "Chưa có đợt điều tra"
    if batch.end_date is None:
        return None, "Chưa đặt hạn hoàn thành"
    days = (batch.end_date - today).days
    if days < 0:
        return days, f"Quá hạn {abs(days)} ngày"
    if days == 0:
        return days, "Hết hạn hôm nay"
    return days, f"Còn {days} ngày"


def _classify_row(
    *,
    batch: SurveyBatch | None,
    latest: StudentSurveyComparisonSignoff | None,
    today: date,
) -> tuple[str, str, str, str, bool]:
    if batch is None:
        code = "MISSING_BATCH"
        reason = "Địa bàn chưa có đợt điều tra cho năm học được chọn."
        action = "Khởi tạo hoặc kiểm tra lại đợt điều tra của địa bàn."
        needs_followup = True
    elif latest is not None and latest.action_code == "CHOT":
        code = "SIGNED"
        reason = "Kết quả đối chiếu đã được xác nhận."
        action = "Theo dõi; chưa cần đôn đốc ở thời điểm hiện tại."
        needs_followup = False
    elif latest is not None and latest.action_code == "MO_LAI":
        code = "REOPENED"
        reason = "Kết quả đã được mở lại và chưa chốt lại."
        action = "Đề nghị địa bàn hoàn tất xử lý và chốt lại kết quả."
        needs_followup = True
    else:
        days, _ = _deadline_details(batch, today)
        if days is not None and days < 0:
            code = "OVERDUE"
            reason = f"Chưa chốt và đã quá hạn {abs(days)} ngày."
            action = "Liên hệ khẩn, yêu cầu hoàn tất đối chiếu và báo cáo nguyên nhân chậm."
        elif days is not None and days <= 7:
            code = "DUE_SOON"
            reason = f"Chưa chốt và chỉ còn {days} ngày đến hạn."
            action = "Nhắc địa bàn hoàn tất xử lý và chốt trước thời hạn."
        elif batch.start_date is not None and batch.start_date > today:
            code = "NOT_STARTED"
            reason = "Đợt điều tra chưa đến ngày bắt đầu."
            action = "Theo dõi lịch; chưa cần nhắc hoàn thành ngay."
        else:
            code = "UNSIGNED"
            reason = "Đã có đợt nhưng chưa có lịch sử chốt kết quả."
            if batch.end_date is not None:
                action = (
                    "Đề nghị địa bàn hoàn tất đối chiếu và chốt trước "
                    f"{_format_date(batch.end_date)}."
                )
            else:
                action = "Đề nghị địa bàn hoàn tất đối chiếu và thực hiện chốt kết quả."
        needs_followup = True

    rank, label, css_class = PRIORITY_META[code]
    return code, label, css_class, reason, action, needs_followup


def _build_rows(
    db: Session,
    school_year_id: int | None,
    *,
    today: date | None = None,
) -> list[dict[str, Any]]:
    report_date = today or date.today()
    communes = list(
        db.scalars(
            select(Commune)
            .where(Commune.is_active.is_(True))
            .order_by(Commune.name.asc(), Commune.id.asc())
        ).all()
    )
    if school_year_id is None:
        return []

    batches = list(
        db.scalars(
            select(SurveyBatch)
            .options(
                selectinload(SurveyBatch.commune),
                selectinload(SurveyBatch.school_year),
            )
            .where(SurveyBatch.school_year_id == school_year_id)
            .order_by(SurveyBatch.commune_id.asc(), SurveyBatch.id.desc())
        ).all()
    )
    batches_by_commune: dict[int, list[SurveyBatch]] = {}
    for batch in batches:
        batches_by_commune.setdefault(batch.commune_id, []).append(batch)

    latest_signoffs = _load_latest_signoffs(db, [item.id for item in batches])
    rows: list[dict[str, Any]] = []
    for commune in communes:
        commune_batches = batches_by_commune.get(commune.id, [])
        batch = commune_batches[0] if commune_batches else None
        latest = latest_signoffs.get(batch.id) if batch is not None else None

        if batch is None:
            state = "MISSING_BATCH"
        elif latest is None:
            state = "UNSIGNED"
        elif latest.action_code == "CHOT":
            state = "SIGNED"
        else:
            state = "REOPENED"

        priority_code, priority_label, priority_css, reason, action, needs_followup = (
            _classify_row(batch=batch, latest=latest, today=report_date)
        )
        priority_rank = PRIORITY_META[priority_code][0]
        days_to_deadline, deadline_label = _deadline_details(batch, report_date)

        latest_action = (
            ACTION_LABELS.get(latest.action_code, latest.action_code)
            if latest is not None
            else "Chưa có lịch sử chốt"
        )
        suggested_message = (
            f"Đề nghị {commune.name} kiểm tra tiến độ đối chiếu học sinh năm học "
            f"{batch.school_year.code if batch is not None else ''}. {action}"
        ).strip()

        rows.append(
            {
                "commune": commune,
                "batch": batch,
                "extra_batch_count": max(0, len(commune_batches) - 1),
                "state": state,
                "state_label": STATE_LABELS[state],
                "priority_code": priority_code,
                "priority_label": priority_label,
                "priority_css": priority_css,
                "priority_rank": priority_rank,
                "needs_followup": needs_followup,
                "reason": reason,
                "suggested_action": action,
                "suggested_message": suggested_message,
                "days_to_deadline": days_to_deadline,
                "deadline_label": deadline_label,
                "start_date_label": _format_date(batch.start_date if batch else None),
                "end_date_label": _format_date(batch.end_date if batch else None),
                "batch_status_label": (
                    BATCH_STATUS_LABELS.get(batch.status, batch.status)
                    if batch is not None
                    else "—"
                ),
                "latest_signoff": latest,
                "latest_action_label": latest_action,
                "latest_time_label": _format_datetime(latest.created_at if latest else None),
                "pending_rows": latest.pending_rows if latest is not None else None,
                "issue_rows": latest.issue_rows if latest is not None else None,
                "resolved_rows": latest.resolved_rows if latest is not None else None,
            }
        )

    rows.sort(
        key=lambda item: (
            item["priority_rank"],
            item["days_to_deadline"] if item["days_to_deadline"] is not None else 999999,
            item["commune"].name.casefold(),
            item["commune"].id,
        )
    )
    return rows


def _apply_filters(
    rows: list[dict[str, Any]],
    *,
    group: str,
    q: str,
) -> list[dict[str, Any]]:
    query = _clean_text(q).casefold()
    result: list[dict[str, Any]] = []
    for row in rows:
        if group == "NEED_FOLLOWUP" and not row["needs_followup"]:
            continue
        if group == "URGENT" and row["priority_code"] not in {
            "OVERDUE", "MISSING_BATCH", "REOPENED", "DUE_SOON"
        }:
            continue
        if group == "OVERDUE" and row["priority_code"] != "OVERDUE":
            continue
        if group == "DUE_SOON" and row["priority_code"] != "DUE_SOON":
            continue
        if group == "REOPENED" and row["state"] != "REOPENED":
            continue
        if group == "UNSIGNED" and row["state"] != "UNSIGNED":
            continue
        if group == "MISSING_BATCH" and row["state"] != "MISSING_BATCH":
            continue
        if group == "SIGNED" and row["state"] != "SIGNED":
            continue

        if query:
            batch = row["batch"]
            latest = row["latest_signoff"]
            search_text = " ".join(
                (
                    row["commune"].code,
                    row["commune"].name,
                    batch.code if batch is not None else "",
                    batch.name if batch is not None else "",
                    row["priority_label"],
                    row["reason"],
                    row["suggested_action"],
                    latest.actor_name_snapshot if latest is not None else "",
                    latest.note if latest is not None else "",
                )
            ).casefold()
            if query not in search_text:
                continue
        result.append(row)
    return result


def _build_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    signed = sum(1 for row in rows if row["state"] == "SIGNED")
    summary = {
        "commune_total": total,
        "signed_total": signed,
        "followup_total": sum(1 for row in rows if row["needs_followup"]),
        "urgent_total": sum(
            1
            for row in rows
            if row["priority_code"] in {"OVERDUE", "MISSING_BATCH", "REOPENED", "DUE_SOON"}
        ),
        "overdue_total": sum(1 for row in rows if row["priority_code"] == "OVERDUE"),
        "due_soon_total": sum(1 for row in rows if row["priority_code"] == "DUE_SOON"),
        "reopened_total": sum(1 for row in rows if row["state"] == "REOPENED"),
        "unsigned_total": sum(1 for row in rows if row["state"] == "UNSIGNED"),
        "missing_batch_total": sum(1 for row in rows if row["state"] == "MISSING_BATCH"),
        "completion_percent": round((signed * 100 / total), 1) if total else 0.0,
    }
    return summary


def _page_url(
    *,
    school_year_id: int | None,
    group: str,
    q: str,
    page_size: int,
    page: int,
) -> str:
    params = {
        "school_year_id": school_year_id or "",
        "group": group,
        "q": q,
        "page_size": page_size,
        "page": page,
    }
    return "/dieu-tra/don-doc-doi-chieu-hoc-sinh?" + urlencode(params)


def _forbidden_response(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="surveys/student_survey_followup_dashboard.html",
        context={
            "nguoi_dung": lay_thong_tin_nguoi_dung(request),
            "error_message": (
                "Chức năng giám sát và đôn đốc toàn tỉnh chỉ dành cho tài khoản "
                "quản trị hoặc phòng ban cấp Sở."
            ),
            "school_years": [],
            "selected_year": None,
            "rows": [],
            "summary": _build_summary([]),
        },
        status_code=403,
    )


@router.get("/don-doc-doi-chieu-hoc-sinh", response_class=HTMLResponse)
def followup_dashboard(
    request: Request,
    school_year_id: str = "",
    group: str = "NEED_FOLLOWUP",
    q: str = "",
    page_size: int = 50,
    page: int = 1,
    db: Session = Depends(get_db),
):
    user = lay_thong_tin_nguoi_dung(request)
    if not is_province_reader(user.get("role_code")):
        return _forbidden_response(request)

    school_years = _load_school_years(db)
    selected_year_id = _default_year_id(school_years, _parse_optional_int(school_year_id))
    selected_year = next((item for item in school_years if item.id == selected_year_id), None)

    normalized_group = _clean_text(group).upper()
    if normalized_group not in GROUP_LABELS:
        normalized_group = "NEED_FOLLOWUP"
    q = _clean_text(q)[:120]
    if page_size not in PAGE_SIZE_OPTIONS:
        page_size = 50

    report_date = date.today()
    all_rows = _build_rows(db, selected_year_id, today=report_date)
    summary = _build_summary(all_rows)
    filtered_rows = _apply_filters(all_rows, group=normalized_group, q=q)

    total_records = len(filtered_rows)
    total_pages = max(1, ceil(total_records / page_size))
    page = max(1, min(page, total_pages))
    start_index = (page - 1) * page_size
    page_rows = filtered_rows[start_index:start_index + page_size]

    page_links = [
        {
            "number": number,
            "url": _page_url(
                school_year_id=selected_year_id,
                group=normalized_group,
                q=q,
                page_size=page_size,
                page=number,
            ),
        }
        for number in range(max(1, page - 2), min(total_pages, page + 2) + 1)
    ]
    export_url = "/dieu-tra/don-doc-doi-chieu-hoc-sinh/xuat-excel?" + urlencode(
        {
            "school_year_id": selected_year_id or "",
            "group": normalized_group,
            "q": q,
        }
    )

    return templates.TemplateResponse(
        request=request,
        name="surveys/student_survey_followup_dashboard.html",
        context={
            "nguoi_dung": user,
            "error_message": None,
            "school_years": school_years,
            "selected_year": selected_year,
            "selected_year_id": selected_year_id,
            "group": normalized_group,
            "group_labels": GROUP_LABELS,
            "q": q,
            "page_size": page_size,
            "page_size_options": PAGE_SIZE_OPTIONS,
            "summary": summary,
            "rows": page_rows,
            "total_records": total_records,
            "page": page,
            "total_pages": total_pages,
            "page_links": page_links,
            "previous_url": (
                _page_url(
                    school_year_id=selected_year_id,
                    group=normalized_group,
                    q=q,
                    page_size=page_size,
                    page=page - 1,
                )
                if page > 1 else None
            ),
            "next_url": (
                _page_url(
                    school_year_id=selected_year_id,
                    group=normalized_group,
                    q=q,
                    page_size=page_size,
                    page=page + 1,
                )
                if page < total_pages else None
            ),
            "export_url": export_url,
            "report_date_label": _format_date(report_date),
        },
    )


def _style_sheet(worksheet: Any) -> None:
    dark_fill = PatternFill("solid", fgColor="1F4E78")
    white_font = Font(color="FFFFFF", bold=True)
    thin = Side(style="thin", color="C9D4DF")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    for cell in worksheet[1]:
        cell.fill = dark_fill
        cell.font = white_font
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = border
    for row in worksheet.iter_rows(min_row=2):
        for cell in row:
            cell.border = border
            cell.alignment = Alignment(vertical="top", wrap_text=True)
    worksheet.freeze_panes = "A2"
    worksheet.auto_filter.ref = worksheet.dimensions


def _set_widths(worksheet: Any, widths: dict[int, float]) -> None:
    for index, width in widths.items():
        worksheet.column_dimensions[get_column_letter(index)].width = width


@router.get("/don-doc-doi-chieu-hoc-sinh/xuat-excel")
def export_followup_dashboard(
    request: Request,
    school_year_id: str = "",
    group: str = "NEED_FOLLOWUP",
    q: str = "",
    db: Session = Depends(get_db),
):
    user = lay_thong_tin_nguoi_dung(request)
    if not is_province_reader(user.get("role_code")):
        return _forbidden_response(request)

    school_years = _load_school_years(db)
    selected_year_id = _default_year_id(school_years, _parse_optional_int(school_year_id))
    selected_year = next((item for item in school_years if item.id == selected_year_id), None)
    normalized_group = _clean_text(group).upper()
    if normalized_group not in GROUP_LABELS:
        normalized_group = "NEED_FOLLOWUP"
    q = _clean_text(q)[:120]
    report_date = date.today()

    all_rows = _build_rows(db, selected_year_id, today=report_date)
    rows = _apply_filters(all_rows, group=normalized_group, q=q)
    summary = _build_summary(all_rows)

    workbook = Workbook()
    detail = workbook.active
    detail.title = "Danh sach don doc"
    detail.append([
        "STT", "Mã xã", "Xã/phường", "Mã đợt", "Tên đợt", "Trạng thái đợt",
        "Trạng thái chốt", "Mức ưu tiên", "Ngày bắt đầu", "Hạn hoàn thành",
        "Tình trạng thời hạn", "Thao tác gần nhất", "Người thực hiện", "Thời điểm",
        "Căn cứ xếp ưu tiên", "Hành động đề nghị", "Nội dung đôn đốc gợi ý",
        "Cần xử lý gần nhất", "Đã ghi nhận gần nhất", "Còn chờ gần nhất",
    ])
    for index, row in enumerate(rows, start=1):
        batch = row["batch"]
        latest = row["latest_signoff"]
        detail.append([
            index,
            row["commune"].code,
            row["commune"].name,
            batch.code if batch is not None else "",
            batch.name if batch is not None else "",
            row["batch_status_label"],
            row["state_label"],
            row["priority_label"],
            row["start_date_label"] if batch is not None else "",
            row["end_date_label"] if batch is not None else "",
            row["deadline_label"],
            row["latest_action_label"],
            latest.actor_name_snapshot if latest is not None else "",
            row["latest_time_label"] if latest is not None else "",
            row["reason"],
            row["suggested_action"],
            row["suggested_message"],
            row["issue_rows"] if row["issue_rows"] is not None else "",
            row["resolved_rows"] if row["resolved_rows"] is not None else "",
            row["pending_rows"] if row["pending_rows"] is not None else "",
        ])
    _style_sheet(detail)
    _set_widths(detail, {
        1:7, 2:13, 3:28, 4:25, 5:40, 6:17, 7:16, 8:16, 9:14, 10:16,
        11:20, 12:28, 13:22, 14:19, 15:42, 16:48, 17:65, 18:15, 19:17, 20:15,
    })

    summary_sheet = workbook.create_sheet("Tong hop uu tien")
    summary_sheet.append(["Chỉ tiêu", "Số lượng / tỷ lệ"])
    summary_sheet.append(["Ngày lập báo cáo", _format_date(report_date)])
    summary_sheet.append(["Năm học", selected_year.code if selected_year else ""])
    summary_sheet.append(["Tổng xã/phường", summary["commune_total"]])
    summary_sheet.append(["Đã chốt", summary["signed_total"]])
    summary_sheet.append(["Cần đôn đốc", summary["followup_total"]])
    summary_sheet.append(["Ưu tiên cao", summary["urgent_total"]])
    summary_sheet.append(["Quá hạn", summary["overdue_total"]])
    summary_sheet.append(["Sắp đến hạn", summary["due_soon_total"]])
    summary_sheet.append(["Đã mở lại", summary["reopened_total"]])
    summary_sheet.append(["Chưa chốt", summary["unsigned_total"]])
    summary_sheet.append(["Chưa có đợt", summary["missing_batch_total"]])
    summary_sheet.append(["Tỷ lệ hoàn thành", f'{summary["completion_percent"]}%'])
    _style_sheet(summary_sheet)
    _set_widths(summary_sheet, {1:35, 2:24})

    info = workbook.create_sheet("Thong tin bao cao")
    info.append(["Nội dung", "Giá trị"])
    info.append(["Tên báo cáo", "Giám sát tiến độ và danh sách địa bàn cần đôn đốc"])
    info.append(["Năm học", selected_year.code if selected_year else ""])
    info.append(["Ngày lập", _format_date(report_date)])
    info.append(["Nhóm đang xuất", GROUP_LABELS.get(normalized_group, normalized_group)])
    info.append(["Từ khóa", q])
    info.append(["Số địa bàn trong danh sách", len(rows)])
    info.append(["Người xuất", user.get("full_name", "")])
    info.append(["Đơn vị", user.get("unit_name", "")])
    info.append([
        "Nguyên tắc",
        "Báo cáo chỉ đọc dữ liệu hiện có, không tự sửa dữ liệu điều tra, học sinh hoặc lịch sử chốt.",
    ])
    _style_sheet(info)
    _set_widths(info, {1:30, 2:90})

    stream = BytesIO()
    workbook.save(stream)
    stream.seek(0)
    year_code = selected_year.code if selected_year is not None else "khong_xac_dinh"
    filename = f"danh_sach_don_doc_doi_chieu_{year_code}.xlsx"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(
        stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers,
    )
