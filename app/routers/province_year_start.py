from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import urlencode
import re
import sqlite3

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.database import DATABASE_PATH, get_db
from app.models import Commune, SchoolYear
from app.permissions import is_admin_role
from app.survey_models import (
    Household,
    SurveyBatch,
    SurveyForm,
    SurveyPerson,
    SurveyPersonYearRecord,
)


APP_DIR = Path(__file__).resolve().parent.parent

templates = Jinja2Templates(directory=str(APP_DIR / "templates"))

router = APIRouter(
    prefix="/dieu-tra",
    tags=["Khởi tạo năm học toàn tỉnh"],
)


BATCH_STATUS_LABELS = {
    "CHUAN_BI": "Chuẩn bị",
    "DANG_DIEU_TRA": "Đang điều tra",
    "DA_KET_THUC": "Đã kết thúc",
}


# =========================================================
# HÀM DÙNG CHUNG
# =========================================================

def lay_nguoi_dung(request: Request) -> dict[str, Any]:
    return dict(request.scope.get("auth_user") or {})


def chuan_hoa_van_ban(value: str) -> str:
    return " ".join(str(value or "").strip().split())


def chuyen_id_tuy_chon(value: str | int | None) -> int | None:
    try:
        parsed = int(str(value or "").strip())
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def chuyen_ngay(
    value: str,
    ten_truong: str,
    *,
    bat_buoc: bool,
) -> tuple[date | None, str | None]:
    normalized = str(value or "").strip()
    if not normalized:
        if bat_buoc:
            return None, f"{ten_truong} không được để trống."
        return None, None
    try:
        return date.fromisoformat(normalized), None
    except ValueError:
        return None, f"{ten_truong} không đúng định dạng."


def tach_ma_nam_hoc(code: str) -> tuple[int, int] | None:
    match = re.fullmatch(r"\s*(\d{4})\s*-\s*(\d{4})\s*", str(code or ""))
    if match is None:
        return None
    first_year = int(match.group(1))
    second_year = int(match.group(2))
    if second_year != first_year + 1:
        return None
    return first_year, second_year


def tao_ma_nam_hoc_ke_tiep(code: str) -> str:
    years = tach_ma_nam_hoc(code)
    if years is not None:
        return f"{years[1]}-{years[1] + 1}"
    current_year = date.today().year
    return f"{current_year}-{current_year + 1}"


def khoa_nam_hoc(school_year: SchoolYear) -> tuple[int, int]:
    years = tach_ma_nam_hoc(school_year.code)
    if years is not None:
        return years
    return 0, school_year.id


def khoa_dot(batch: SurveyBatch) -> tuple[int, date, int]:
    return (
        1 if batch.is_locked else 0,
        batch.start_date or date.min,
        batch.id,
    )


def chon_dot_nguon(batches: list[SurveyBatch]) -> SurveyBatch | None:
    """Ưu tiên đợt đã khóa, sau đó lấy đợt mới nhất."""

    if not batches:
        return None
    return max(batches, key=khoa_dot)


def chon_dot_dich(batches: list[SurveyBatch]) -> SurveyBatch | None:
    """Ưu tiên đợt còn mở để có thể bổ sung dữ liệu bị thiếu."""

    if not batches:
        return None
    return max(
        batches,
        key=lambda item: (
            1 if not item.is_locked else 0,
            item.start_date or date.min,
            item.id,
        ),
    )


def tao_ma_dot_dieu_tra(
    db: Session,
    commune: Commune,
    school_year: SchoolYear,
) -> str:
    year_code = school_year.code.replace("-", "")
    sequence = int(
        db.scalar(
            select(func.count(SurveyBatch.id)).where(
                SurveyBatch.commune_id == commune.id,
                SurveyBatch.school_year_id == school_year.id,
            )
        )
        or 0
    ) + 1

    while True:
        candidate = f"DT-{commune.code}-{year_code}-{sequence:03d}"
        duplicate = db.scalar(
            select(SurveyBatch.id).where(SurveyBatch.code == candidate)
        )
        if duplicate is None:
            return candidate
        sequence += 1


def tao_ban_sao_truoc_khi_khoi_tao_toan_tinh() -> Path:
    database_path = Path(DATABASE_PATH)
    backup_dir = database_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"before_province_year_start_{timestamp}.db"

    source = sqlite3.connect(str(database_path))
    target = sqlite3.connect(str(backup_path))
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()

    return backup_path


def lay_cac_dot_theo_nam(
    db: Session,
    school_year_id: int,
) -> dict[int, list[SurveyBatch]]:
    batches = db.scalars(
        select(SurveyBatch)
        .options(
            selectinload(SurveyBatch.school_year),
            selectinload(SurveyBatch.commune),
        )
        .where(SurveyBatch.school_year_id == school_year_id)
        .order_by(SurveyBatch.start_date.asc(), SurveyBatch.id.asc())
    ).all()

    grouped: dict[int, list[SurveyBatch]] = {}
    for batch in batches:
        grouped.setdefault(batch.commune_id, []).append(batch)
    return grouped


def lay_so_phieu_theo_dot(
    db: Session,
    batch_ids: list[int],
) -> dict[int, int]:
    if not batch_ids:
        return {}
    rows = db.execute(
        select(
            SurveyForm.survey_batch_id,
            func.count(SurveyForm.id),
        )
        .where(SurveyForm.survey_batch_id.in_(batch_ids))
        .group_by(SurveyForm.survey_batch_id)
    ).all()
    return {
        int(batch_id): int(total or 0)
        for batch_id, total in rows
    }


def tao_du_lieu_xem_truoc(
    *,
    db: Session,
    source_school_year: SchoolYear,
    target_code: str,
) -> dict[str, Any]:
    communes = db.scalars(
        select(Commune)
        .where(Commune.is_active.is_(True))
        .order_by(Commune.name.asc(), Commune.code.asc())
    ).all()

    source_grouped = lay_cac_dot_theo_nam(db, source_school_year.id)
    target_school_year = db.scalar(
        select(SchoolYear).where(SchoolYear.code == target_code)
    )
    target_grouped = (
        lay_cac_dot_theo_nam(db, target_school_year.id)
        if target_school_year is not None
        else {}
    )

    source_batches = [
        chon_dot_nguon(source_grouped.get(commune.id, []))
        for commune in communes
    ]
    source_batch_ids = [
        item.id for item in source_batches if item is not None
    ]
    source_form_counts = lay_so_phieu_theo_dot(db, source_batch_ids)

    target_batches = [
        chon_dot_dich(target_grouped.get(commune.id, []))
        for commune in communes
    ]
    target_batch_ids = [
        item.id for item in target_batches if item is not None
    ]
    target_form_counts = lay_so_phieu_theo_dot(db, target_batch_ids)

    rows: list[dict[str, Any]] = []
    locked_source_total = 0
    unlocked_source_total = 0
    missing_source_total = 0
    estimated_forms = 0
    existing_target_total = 0

    for commune, source_batch, target_batch in zip(
        communes,
        source_batches,
        target_batches,
    ):
        source_form_total = (
            source_form_counts.get(source_batch.id, 0)
            if source_batch is not None
            else 0
        )
        target_form_total = (
            target_form_counts.get(target_batch.id, 0)
            if target_batch is not None
            else 0
        )

        if source_batch is None:
            source_state = "missing"
            source_note = "Chưa có đợt nguồn; sẽ tạo đợt mới trống."
            missing_source_total += 1
        elif not source_batch.is_locked:
            source_state = "unlocked"
            source_note = "Đợt nguồn chưa khóa; chưa tự động kế thừa dữ liệu."
            unlocked_source_total += 1
        else:
            source_state = "ready"
            source_note = "Sẵn sàng kế thừa dữ liệu đã chốt."
            locked_source_total += 1
            estimated_forms += source_form_total

        if target_batch is not None:
            existing_target_total += 1

        rows.append(
            {
                "commune": commune,
                "source_batch": source_batch,
                "source_form_total": source_form_total,
                "source_state": source_state,
                "source_note": source_note,
                "target_batch": target_batch,
                "target_form_total": target_form_total,
            }
        )

    return {
        "communes": communes,
        "preview_rows": rows,
        "target_school_year": target_school_year,
        "preview_summary": {
            "commune_total": len(communes),
            "locked_source_total": locked_source_total,
            "unlocked_source_total": unlocked_source_total,
            "missing_source_total": missing_source_total,
            "estimated_forms": estimated_forms,
            "existing_target_total": existing_target_total,
        },
    }


def lay_mac_dinh_form(
    source_school_year: SchoolYear,
) -> dict[str, str]:
    target_code = tao_ma_nam_hoc_ke_tiep(source_school_year.code)
    first_year, _ = tach_ma_nam_hoc(target_code) or (
        date.today().year,
        date.today().year + 1,
    )
    return {
        "source_school_year_id": str(source_school_year.id),
        "target_school_year_code": target_code,
        "target_school_year_name": f"Năm học {target_code}",
        "batch_name": f"Điều tra phổ cập giáo dục đầu năm học {target_code}",
        "start_date": f"{first_year}-07-01",
        "end_date": f"{first_year}-08-31",
        "notes": (
            "Khởi tạo đồng loạt toàn tỉnh và kế thừa dữ liệu "
            f"từ năm học {source_school_year.code}."
        ),
    }


def sinh_so_phieu(
    *,
    commune: Commune,
    school_year: SchoolYear,
    used_numbers: set[str],
    sequence: int,
) -> tuple[str, int]:
    year_code = school_year.code.replace("-", "")
    while True:
        candidate = (
            f"PH-{commune.code}-{year_code}-{sequence:06d}"
        )
        sequence += 1
        if candidate not in used_numbers:
            used_numbers.add(candidate)
            return candidate, sequence


def dam_bao_ke_thua_cho_mot_xa(
    *,
    db: Session,
    source_batch: SurveyBatch,
    target_batch: SurveyBatch,
    commune: Commune,
    target_school_year: SchoolYear,
) -> dict[str, int]:
    """
    Tạo các phiếu và hồ sơ năm học còn thiếu.

    Hàm có thể chạy lại an toàn: phiếu/hồ sơ đã có được giữ nguyên,
    không bị ghi đè và không tạo bản ghi trùng.
    """

    source_forms = db.scalars(
        select(SurveyForm)
        .options(
            selectinload(SurveyForm.household)
            .selectinload(Household.people)
        )
        .where(SurveyForm.survey_batch_id == source_batch.id)
        .order_by(SurveyForm.id.asc())
    ).all()

    target_forms = db.scalars(
        select(SurveyForm)
        .where(SurveyForm.survey_batch_id == target_batch.id)
        .order_by(SurveyForm.id.asc())
    ).all()
    target_by_household_id = {
        item.household_id: item for item in target_forms
    }
    used_numbers = {item.form_number for item in target_forms}

    maximum_sequence = 0
    for form_number in used_numbers:
        match = re.search(r"(\d{6})$", form_number or "")
        if match is not None:
            maximum_sequence = max(maximum_sequence, int(match.group(1)))
    next_sequence = max(maximum_sequence + 1, len(target_forms) + 1, 1)

    target_form_ids = [item.id for item in target_forms]
    existing_record_keys: set[tuple[int, int]] = set()
    if target_form_ids:
        existing_record_keys = {
            (int(form_id), int(person_id))
            for form_id, person_id in db.execute(
                select(
                    SurveyPersonYearRecord.survey_form_id,
                    SurveyPersonYearRecord.survey_person_id,
                ).where(
                    SurveyPersonYearRecord.survey_form_id.in_(target_form_ids),
                    SurveyPersonYearRecord.school_year_id
                    == target_school_year.id,
                )
            ).all()
        }

    created_forms = 0
    existing_forms = 0
    created_year_records = 0

    for source_form in source_forms:
        household = source_form.household
        target_form = target_by_household_id.get(household.id)

        if target_form is None:
            form_number, next_sequence = sinh_so_phieu(
                commune=commune,
                school_year=target_school_year,
                used_numbers=used_numbers,
                sequence=next_sequence,
            )
            target_form = SurveyForm(
                survey_batch_id=target_batch.id,
                household_id=household.id,
                form_number=form_number,
                head_name_snapshot=household.head_name,
                address_snapshot=household.address,
                hamlet_name_snapshot=household.hamlet_name,
                status="CHUA_DIEU_TRA",
            )
            db.add(target_form)
            db.flush()
            target_by_household_id[household.id] = target_form
            created_forms += 1
        else:
            existing_forms += 1

        for person in household.people:
            if not person.is_active:
                continue
            record_key = (target_form.id, person.id)
            if record_key in existing_record_keys:
                continue

            db.add(
                SurveyPersonYearRecord(
                    survey_form_id=target_form.id,
                    survey_person_id=person.id,
                    school_year_id=target_school_year.id,
                    learning_status="CHUA_XAC_DINH",
                    notes=(
                        "Tự động chuyển hồ sơ đầu năm học mới từ đợt "
                        f"{source_batch.code}; cần điều tra và rà soát lại."
                    ),
                )
            )
            existing_record_keys.add(record_key)
            created_year_records += 1

    return {
        "created_forms": created_forms,
        "existing_forms": existing_forms,
        "created_year_records": created_year_records,
    }


def lay_danh_sach_nam_hoc(db: Session) -> list[SchoolYear]:
    return db.scalars(
        select(SchoolYear)
        .where(SchoolYear.is_active.is_(True))
        .order_by(SchoolYear.code.desc(), SchoolYear.id.desc())
    ).all()


def chon_nam_hoc_nguon_mac_dinh(
    db: Session,
    school_years: list[SchoolYear],
) -> SchoolYear | None:
    year_ids_with_batches = set(
        int(value)
        for value in db.scalars(
            select(SurveyBatch.school_year_id).distinct()
        ).all()
    )
    candidates = [
        item for item in school_years if item.id in year_ids_with_batches
    ]
    if candidates:
        return max(candidates, key=khoa_nam_hoc)
    return max(school_years, key=khoa_nam_hoc) if school_years else None


def tao_context_trang(
    *,
    request: Request,
    db: Session,
    source_school_year_id: int | None,
    target_code: str,
    form_data: dict[str, str] | None = None,
    message: str = "",
    error_message: str = "",
    result_summary: dict[str, Any] | None = None,
    status_code: int = 200,
):
    user = lay_nguoi_dung(request)
    school_years = lay_danh_sach_nam_hoc(db)

    source_school_year = None
    if source_school_year_id is not None:
        source_school_year = db.get(SchoolYear, source_school_year_id)
        if source_school_year is not None and not source_school_year.is_active:
            source_school_year = None

    if source_school_year is None:
        source_school_year = chon_nam_hoc_nguon_mac_dinh(db, school_years)

    if source_school_year is None:
        return templates.TemplateResponse(
            request=request,
            name="surveys/province_year_start.html",
            context={
                "nguoi_dung": user,
                "school_years": [],
                "source_school_year": None,
                "form_data": {},
                "preview_rows": [],
                "preview_summary": {},
                "message": message,
                "error_message": (
                    error_message
                    or "Chưa có danh mục năm học để khởi tạo."
                ),
                "result_summary": result_summary,
                "status_labels": BATCH_STATUS_LABELS,
            },
            status_code=status_code,
        )

    defaults = lay_mac_dinh_form(source_school_year)

    # Trang này chỉ khởi tạo năm học LIỀN SAU năm nguồn. Khi người dùng
    # đổi năm nguồn, trình duyệt có thể vẫn gửi mã năm đích cũ trong URL.
    # Không dùng mã cũ đó để xem trước vì có thể dẫn đến chuỗi sai như
    # 2025-2026 -> 2027-2028. Yêu cầu POST vẫn giữ kiểm tra bắt buộc ở dưới.
    expected_target_code = defaults["target_school_year_code"]
    normalized_target_code = chuan_hoa_van_ban(target_code)[:20]
    if normalized_target_code == expected_target_code:
        defaults["target_school_year_code"] = normalized_target_code

    if form_data:
        defaults.update(form_data)

    preview = tao_du_lieu_xem_truoc(
        db=db,
        source_school_year=source_school_year,
        target_code=defaults["target_school_year_code"],
    )

    return templates.TemplateResponse(
        request=request,
        name="surveys/province_year_start.html",
        context={
            "nguoi_dung": user,
            "school_years": school_years,
            "source_school_year": source_school_year,
            "form_data": defaults,
            "message": message,
            "error_message": error_message,
            "result_summary": result_summary,
            "status_labels": BATCH_STATUS_LABELS,
            **preview,
        },
        status_code=status_code,
    )


# =========================================================
# BÀI 12D-11: KHỞI TẠO NĂM HỌC MỚI TOÀN TỈNH
# =========================================================

@router.get(
    "/khoi-tao-nam-hoc-toan-tinh",
    response_class=HTMLResponse,
)
def trang_khoi_tao_nam_hoc_toan_tinh(
    request: Request,
    source_school_year_id: str = "",
    target_code: str = "",
    target_school_year_code: str = "",
    status: str = "",
    target_school_year_id: str = "",
    created_batches: int = 0,
    reused_batches: int = 0,
    inherited_communes: int = 0,
    missing_source_communes: int = 0,
    unlocked_source_communes: int = 0,
    locked_target_communes: int = 0,
    created_forms: int = 0,
    existing_forms: int = 0,
    created_year_records: int = 0,
    backup: str = "",
    db: Session = Depends(get_db),
):
    user = lay_nguoi_dung(request)
    if not is_admin_role(user.get("role_code")):
        return RedirectResponse(url="/?status=forbidden", status_code=303)

    selected_source_id = chuyen_id_tuy_chon(source_school_year_id)
    selected_target_year_id = chuyen_id_tuy_chon(target_school_year_id)

    result_summary = None
    message = ""
    if status == "success":
        message = (
            "Đã khởi tạo đợt điều tra năm học mới cho toàn tỉnh "
            "và tự động chuyển dữ liệu đủ điều kiện."
        )
        result_summary = {
            "target_school_year_id": selected_target_year_id,
            "created_batches": max(created_batches, 0),
            "reused_batches": max(reused_batches, 0),
            "inherited_communes": max(inherited_communes, 0),
            "missing_source_communes": max(missing_source_communes, 0),
            "unlocked_source_communes": max(unlocked_source_communes, 0),
            "locked_target_communes": max(locked_target_communes, 0),
            "created_forms": max(created_forms, 0),
            "existing_forms": max(existing_forms, 0),
            "created_year_records": max(created_year_records, 0),
            "backup": Path(backup).name if backup else "",
        }

    return tao_context_trang(
        request=request,
        db=db,
        source_school_year_id=selected_source_id,
        target_code=chuan_hoa_van_ban(
            target_code or target_school_year_code
        )[:20],
        message=message,
        result_summary=result_summary,
    )


@router.post("/khoi-tao-nam-hoc-toan-tinh")
def thuc_hien_khoi_tao_nam_hoc_toan_tinh(
    request: Request,
    source_school_year_id: Annotated[int, Form()],
    target_school_year_code: Annotated[str, Form()],
    target_school_year_name: Annotated[str, Form()],
    batch_name: Annotated[str, Form()],
    start_date: Annotated[str, Form()],
    end_date: Annotated[str, Form()] = "",
    notes: Annotated[str, Form()] = "",
    confirm_province_start: Annotated[str, Form()] = "",
    db: Session = Depends(get_db),
):
    user = lay_nguoi_dung(request)
    if not is_admin_role(user.get("role_code")):
        return RedirectResponse(url="/?status=forbidden", status_code=303)

    source_school_year = db.get(SchoolYear, source_school_year_id)
    target_school_year_code = chuan_hoa_van_ban(
        target_school_year_code
    )[:20]
    target_school_year_name = chuan_hoa_van_ban(
        target_school_year_name
    )[:100]
    batch_name = chuan_hoa_van_ban(batch_name)[:300]
    notes = str(notes or "").strip()[:2000]

    parsed_start, start_error = chuyen_ngay(
        start_date,
        "Ngày bắt đầu điều tra",
        bat_buoc=True,
    )
    parsed_end, end_error = chuyen_ngay(
        end_date,
        "Ngày kết thúc dự kiến",
        bat_buoc=False,
    )

    errors: list[str] = []
    if source_school_year is None or not source_school_year.is_active:
        errors.append("Năm học nguồn không hợp lệ.")

    source_years = (
        tach_ma_nam_hoc(source_school_year.code)
        if source_school_year is not None
        else None
    )
    target_years = tach_ma_nam_hoc(target_school_year_code)
    if target_years is None:
        errors.append("Mã năm học mới phải có dạng 2026-2027.")
    elif source_years is not None and target_years[0] != source_years[1]:
        errors.append(
            "Năm học mới phải là năm liền sau năm học nguồn."
        )

    if not target_school_year_name:
        errors.append("Tên năm học mới không được để trống.")
    if not batch_name:
        errors.append("Tên đợt điều tra dùng chung không được để trống.")
    if start_error:
        errors.append(start_error)
    if end_error:
        errors.append(end_error)
    if parsed_start and parsed_end and parsed_end < parsed_start:
        errors.append("Ngày kết thúc không được trước ngày bắt đầu.")
    if confirm_province_start != "yes":
        errors.append(
            "Bạn cần xác nhận trước khi khởi tạo đồng loạt toàn tỉnh."
        )

    existing_target_year = db.scalar(
        select(SchoolYear).where(
            SchoolYear.code == target_school_year_code
        )
    )
    if existing_target_year is not None and not existing_target_year.is_active:
        errors.append("Năm học đích đã tồn tại nhưng đang ngừng sử dụng.")

    form_data = {
        "source_school_year_id": str(source_school_year_id),
        "target_school_year_code": target_school_year_code,
        "target_school_year_name": target_school_year_name,
        "batch_name": batch_name,
        "start_date": start_date,
        "end_date": end_date,
        "notes": notes,
    }

    if errors:
        return tao_context_trang(
            request=request,
            db=db,
            source_school_year_id=source_school_year_id,
            target_code=target_school_year_code,
            form_data=form_data,
            error_message=" ".join(errors),
            status_code=400,
        )

    backup_path: Path | None = None
    try:
        backup_path = tao_ban_sao_truoc_khi_khoi_tao_toan_tinh()

        target_school_year = existing_target_year
        if target_school_year is None:
            target_school_year = SchoolYear(
                code=target_school_year_code,
                name=target_school_year_name,
                start_date=parsed_start,
                end_date=parsed_end,
                is_active=True,
            )
            db.add(target_school_year)
            db.flush()

        communes = db.scalars(
            select(Commune)
            .where(Commune.is_active.is_(True))
            .order_by(Commune.name.asc(), Commune.id.asc())
        ).all()

        source_grouped = lay_cac_dot_theo_nam(
            db,
            source_school_year.id,
        )
        target_grouped = lay_cac_dot_theo_nam(
            db,
            target_school_year.id,
        )

        created_batches = 0
        reused_batches = 0
        inherited_communes = 0
        missing_source_communes = 0
        unlocked_source_communes = 0
        locked_target_communes = 0
        created_forms = 0
        existing_forms = 0
        created_year_records = 0

        for commune in communes:
            source_batch = chon_dot_nguon(
                source_grouped.get(commune.id, [])
            )
            target_batch = chon_dot_dich(
                target_grouped.get(commune.id, [])
            )

            if target_batch is None:
                target_batch = SurveyBatch(
                    code=tao_ma_dot_dieu_tra(
                        db,
                        commune,
                        target_school_year,
                    ),
                    name=batch_name,
                    school_year_id=target_school_year.id,
                    commune_id=commune.id,
                    status="CHUAN_BI",
                    start_date=parsed_start,
                    end_date=parsed_end,
                    created_by_user_id=user.get("id"),
                    notes=(
                        notes
                        or (
                            "Khởi tạo đồng loạt toàn tỉnh; tự động kế thừa "
                            f"dữ liệu từ năm học {source_school_year.code}."
                        )
                    ),
                )
                db.add(target_batch)
                db.flush()
                target_grouped.setdefault(commune.id, []).append(target_batch)
                created_batches += 1
            else:
                reused_batches += 1

            if source_batch is None:
                missing_source_communes += 1
                continue
            if not source_batch.is_locked:
                unlocked_source_communes += 1
                continue
            if target_batch.is_locked:
                locked_target_communes += 1
                continue

            inherited = dam_bao_ke_thua_cho_mot_xa(
                db=db,
                source_batch=source_batch,
                target_batch=target_batch,
                commune=commune,
                target_school_year=target_school_year,
            )
            inherited_communes += 1
            created_forms += inherited["created_forms"]
            existing_forms += inherited["existing_forms"]
            created_year_records += inherited["created_year_records"]

        db.commit()

    except Exception as error:
        db.rollback()
        return tao_context_trang(
            request=request,
            db=db,
            source_school_year_id=source_school_year_id,
            target_code=target_school_year_code,
            form_data=form_data,
            error_message=(
                "Không thể hoàn tất khởi tạo toàn tỉnh. "
                f"Chi tiết: {str(error)[:500]}"
            ),
            status_code=500,
        )

    query = urlencode(
        {
            "status": "success",
            "source_school_year_id": source_school_year.id,
            "target_code": target_school_year.code,
            "target_school_year_id": target_school_year.id,
            "created_batches": created_batches,
            "reused_batches": reused_batches,
            "inherited_communes": inherited_communes,
            "missing_source_communes": missing_source_communes,
            "unlocked_source_communes": unlocked_source_communes,
            "locked_target_communes": locked_target_communes,
            "created_forms": created_forms,
            "existing_forms": existing_forms,
            "created_year_records": created_year_records,
            "backup": str(backup_path or ""),
        }
    )
    return RedirectResponse(
        url=f"/dieu-tra/khoi-tao-nam-hoc-toan-tinh?{query}",
        status_code=303,
    )
