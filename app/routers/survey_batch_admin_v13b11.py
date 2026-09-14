from __future__ import annotations

import json
import re
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.database import DATABASE_PATH, get_db
from app.models import Commune, SchoolYear
from app.permissions import is_admin_role, normalize_role_code
from app.routers.surveys import BATCH_STATUS_LABELS, lay_thong_tin_nguoi_dung, tao_ma_dot_dieu_tra
from app.survey_models import SurveyBatch, SurveyForm

# === BAI_13B_11_PROVINCE_BATCH_ADMIN_START ===

APP_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = APP_DIR.parent
EXPORT_DIR = PROJECT_DIR / "exports"
templates = Jinja2Templates(directory=str(APP_DIR / "templates"))

router = APIRouter(
    prefix="/dieu-tra/quan-ly-dot-toan-tinh",
    tags=["Bài 13B-11 - Quản lý đợt toàn tỉnh"],
)

CREATE_CONFIRM_TEXT = "KHOI TAO TOAN TINH"


def _user(request: Request) -> dict[str, Any]:
    return dict(lay_thong_tin_nguoi_dung(request) or {})


def _admin(request: Request) -> bool:
    return is_admin_role(normalize_role_code(_user(request).get("role_code")))


def _forbidden() -> RedirectResponse:
    return RedirectResponse(url="/?status=forbidden", status_code=303)


def _clean(value: Any, limit: int = 1000) -> str:
    return " ".join(str(value or "").strip().split())[:limit]


def _parse_date(value: Any) -> tuple[date | None, str | None]:
    text = str(value or "").strip()
    if not text:
        return None, None
    try:
        return date.fromisoformat(text), None
    except ValueError:
        return None, "Ngày không đúng định dạng YYYY-MM-DD."


def _pick_year(db: Session, year_id: int | None) -> SchoolYear | None:
    if year_id:
        year = db.get(SchoolYear, int(year_id))
        if year is not None and bool(getattr(year, "is_active", True)):
            return year
    return db.scalar(
        select(SchoolYear)
        .where(SchoolYear.is_active.is_(True))
        .order_by(SchoolYear.code.desc(), SchoolYear.id.desc())
        .limit(1)
    )


def _page_data(db: Session, year_id: int | None) -> dict[str, Any]:
    years = list(db.scalars(
        select(SchoolYear)
        .where(SchoolYear.is_active.is_(True))
        .order_by(SchoolYear.code.desc(), SchoolYear.id.desc())
    ).all())
    year = _pick_year(db, year_id)
    communes = list(db.scalars(
        select(Commune)
        .where(Commune.is_active.is_(True))
        .order_by(Commune.name.asc(), Commune.id.asc())
    ).all())

    batches: list[SurveyBatch] = []
    form_counts: dict[int, int] = {}
    if year is not None:
        batches = list(db.scalars(
            select(SurveyBatch)
            .options(selectinload(SurveyBatch.commune), selectinload(SurveyBatch.school_year))
            .where(SurveyBatch.school_year_id == year.id)
            .order_by(SurveyBatch.commune_id.asc(), SurveyBatch.created_at.desc(), SurveyBatch.id.desc())
        ).all())
        if batches:
            ids = [int(x.id) for x in batches]
            count_rows = db.execute(
                select(SurveyForm.survey_batch_id, func.count(SurveyForm.id))
                .where(SurveyForm.survey_batch_id.in_(ids))
                .group_by(SurveyForm.survey_batch_id)
            ).all()
            form_counts = {int(bid): int(total or 0) for bid, total in count_rows}

    by_commune: dict[int, list[SurveyBatch]] = {}
    for batch in batches:
        by_commune.setdefault(int(batch.commune_id), []).append(batch)

    rows = []
    commune_with_batch = 0
    duplicate_total = 0
    for commune in communes:
        items = by_commune.get(int(commune.id), [])
        if items:
            commune_with_batch += 1
            duplicate_total += max(0, len(items) - 1)
        rows.append({"commune": commune, "batches": items, "has_batch": bool(items), "batch_total": len(items)})

    batch_rows = []
    for batch in batches:
        form_total = int(form_counts.get(int(batch.id), 0))
        locked = bool(getattr(batch, "is_locked", False))
        prelim = str(batch.status or "") == "CHUAN_BI" and not locked and form_total == 0
        batch_rows.append({
            "batch": batch,
            "form_total": form_total,
            "is_locked": locked,
            "prelim_deletable": prelim,
            "delete_phrase": f"XOA DOT {batch.code}",
        })

    return {
        "school_years": years,
        "selected_year": year,
        "selected_year_id": year.id if year else None,
        "rows": rows,
        "batch_rows": batch_rows,
        "active_commune_total": len(communes),
        "commune_with_batch_total": commune_with_batch,
        "missing_commune_total": max(0, len(communes) - commune_with_batch),
        "batch_total": len(batches),
        "duplicate_batch_total": duplicate_total,
    }


def _status_message(status: str | None, params: dict[str, Any]) -> tuple[str | None, str | None]:
    if status == "province_created":
        return (f"Đã tạo {params.get('created','0')} đợt còn thiếu; bỏ qua {params.get('skipped','0')} xã/phường đã có đợt.", None)
    if status == "nothing_to_create":
        return ("Toàn bộ xã/phường đang hoạt động đã có đợt trong năm học này; không tạo bản ghi trùng.", None)
    if status == "batch_deleted":
        return (f"Đã xóa an toàn đợt {_clean(params.get('code'),100)}. Backup: {_clean(params.get('backup'),300)}.", None)
    if status == "delete_blocked":
        return (None, "Không thể xóa đợt. " + (_clean(params.get('detail'),800) or "Đợt không đạt điều kiện an toàn."))
    if status == "create_blocked":
        return (None, "Không thể khởi tạo toàn tỉnh. " + (_clean(params.get('detail'),800) or "Dữ liệu chưa hợp lệ."))
    if status == "create_failed":
        return (None, "Khởi tạo không thành công; toàn bộ giao dịch đã rollback, không có đợt nào được tạo dở.")
    if status == "delete_failed":
        suffix = f" Backup đã tạo: {_clean(params.get('backup'),300)}." if params.get("backup") else ""
        return (None, "Xóa đợt không thành công; dữ liệu hiện hành được giữ nguyên." + suffix)
    return None, None


def _render(request: Request, db: Session, year_id: int | None, status: str | None = None, params: dict[str, Any] | None = None):
    message, error = _status_message(status, params or {})
    return templates.TemplateResponse(
        request=request,
        name="surveys/province_batch_admin_v13b11.html",
        context={
            "nguoi_dung": _user(request),
            "status_labels": BATCH_STATUS_LABELS,
            "create_confirm_text": CREATE_CONFIRM_TEXT,
            "message": message,
            "error": error,
            "today": date.today().isoformat(),
            **_page_data(db, year_id),
        },
    )


@router.get("", response_class=HTMLResponse)
def page(
    request: Request,
    school_year_id: int | None = Query(default=None),
    status: str | None = Query(default=None),
    created: str | None = Query(default=None),
    skipped: str | None = Query(default=None),
    backup: str | None = Query(default=None),
    code: str | None = Query(default=None),
    detail: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    if not _admin(request):
        return _forbidden()
    return _render(request, db, school_year_id, status, {
        "created": created, "skipped": skipped, "backup": backup, "code": code, "detail": detail,
    })


@router.post("/khoi-tao")
def create_all_missing(
    request: Request,
    school_year_id: int = Form(...),
    name: str = Form(...),
    start_date: str = Form(...),
    end_date: str = Form(""),
    notes: str = Form(""),
    confirm_text: str = Form(""),
    db: Session = Depends(get_db),
):
    if not _admin(request):
        return _forbidden()

    year = db.get(SchoolYear, int(school_year_id))
    clean_name = _clean(name, 300)
    clean_notes = _clean(notes, 3000)
    parsed_start, start_error = _parse_date(start_date)
    parsed_end, end_error = _parse_date(end_date)
    errors: list[str] = []

    if year is None or not bool(getattr(year, "is_active", True)):
        errors.append("Năm học không hợp lệ hoặc đã ngừng sử dụng.")
    if not clean_name:
        errors.append("Tên đợt điều tra không được để trống.")
    if parsed_start is None:
        errors.append(start_error or "Ngày bắt đầu không được để trống.")
    if end_error:
        errors.append(end_error)
    if parsed_start and parsed_end and parsed_end < parsed_start:
        errors.append("Ngày kết thúc không được trước ngày bắt đầu.")
    if _clean(confirm_text, 100).upper() != CREATE_CONFIRM_TEXT:
        errors.append(f'Phải nhập chính xác "{CREATE_CONFIRM_TEXT}" để xác nhận.')

    communes = list(db.scalars(
        select(Commune).where(Commune.is_active.is_(True)).order_by(Commune.id.asc())
    ).all())
    if not communes:
        errors.append("Không có xã/phường đang hoạt động để khởi tạo.")

    if errors:
        return RedirectResponse(
            url="/dieu-tra/quan-ly-dot-toan-tinh?" + urlencode({
                "school_year_id": school_year_id,
                "status": "create_blocked",
                "detail": " ".join(errors),
            }),
            status_code=303,
        )

    existing_ids = {int(x) for x in db.scalars(
        select(SurveyBatch.commune_id).where(SurveyBatch.school_year_id == year.id)
    ).all()}
    missing = [c for c in communes if int(c.id) not in existing_ids]

    if not missing:
        return RedirectResponse(
            url="/dieu-tra/quan-ly-dot-toan-tinh?" + urlencode({
                "school_year_id": year.id, "status": "nothing_to_create"
            }),
            status_code=303,
        )

    actor = _user(request)
    created = 0
    try:
        for commune in missing:
            batch = SurveyBatch(
                code=tao_ma_dot_dieu_tra(db=db, commune=commune, school_year=year),
                name=clean_name,
                school_year_id=year.id,
                commune_id=commune.id,
                status="CHUAN_BI",
                start_date=parsed_start,
                end_date=parsed_end,
                created_by_user_id=actor.get("id"),
                notes=("Bài 13B-11 - Khởi tạo toàn tỉnh. " + clean_notes).strip(),
            )
            db.add(batch)
            db.flush()
            created += 1
        db.commit()
    except Exception:
        db.rollback()
        return RedirectResponse(
            url="/dieu-tra/quan-ly-dot-toan-tinh?" + urlencode({
                "school_year_id": year.id, "status": "create_failed"
            }),
            status_code=303,
        )

    return RedirectResponse(
        url="/dieu-tra/quan-ly-dot-toan-tinh?" + urlencode({
            "school_year_id": year.id,
            "status": "province_created",
            "created": created,
            "skipped": len(existing_ids),
        }),
        status_code=303,
    )


def _qi(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def _tables(con: sqlite3.Connection) -> list[str]:
    return [str(r[0]) for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()]


def _columns(con: sqlite3.Connection, table: str) -> set[str]:
    return {str(r[1]) for r in con.execute(f"PRAGMA table_info({_qi(table)})").fetchall()}


def _snapshot(con: sqlite3.Connection, batch_id: int) -> dict[str, Any] | None:
    cols = _columns(con, "survey_batches")
    wanted = ["id", "code", "name", "status", "school_year_id", "commune_id", "start_date", "end_date", "created_at"]
    for optional in ("is_locked", "locked_at"):
        if optional in cols:
            wanted.append(optional)
    row = con.execute(
        "SELECT " + ", ".join(_qi(x) for x in wanted) + " FROM survey_batches WHERE id=? LIMIT 1",
        (int(batch_id),),
    ).fetchone()
    if row is None:
        return None
    return {wanted[i]: row[i] for i in range(len(wanted))}


def _references(con: sqlite3.Connection, batch_id: int) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for table in _tables(con):
        if table == "survey_batches":
            continue
        cols = _columns(con, table)
        candidates: set[str] = set()
        for fk in con.execute(f"PRAGMA foreign_key_list({_qi(table)})").fetchall():
            if str(fk[2] or "") == "survey_batches" and str(fk[3] or ""):
                candidates.add(str(fk[3]))
        for conventional in ("survey_batch_id", "source_batch_id", "target_batch_id", "batch_id"):
            if conventional in cols:
                candidates.add(conventional)
        for col in sorted(candidates):
            count = int(con.execute(
                f"SELECT COUNT(*) FROM {_qi(table)} WHERE {_qi(col)}=?", (int(batch_id),)
            ).fetchone()[0] or 0)
            if count > 0:
                out.append({"table": table, "column": col, "count": count})
    return out


def _safety_reason(snapshot: dict[str, Any] | None, references: list[dict[str, Any]]) -> str | None:
    if snapshot is None:
        return "Không tìm thấy đợt điều tra."
    if str(snapshot.get("status") or "") != "CHUAN_BI":
        return f"Chỉ được xóa đợt còn Chuẩn bị; trạng thái hiện tại là {snapshot.get('status')}."
    if bool(snapshot.get("is_locked")) or bool(snapshot.get("locked_at")):
        return "Đợt đã khóa/chốt nên không cho phép xóa."
    if references:
        detail = "; ".join(
            f"{x['table']}.{x['column']}: {x['count']}" for x in references[:8]
        )
        if len(references) > 8:
            detail += f"; và {len(references)-8} nhóm tham chiếu khác"
        return "Đợt đang có dữ liệu hoặc bản ghi phụ thuộc: " + detail
    return None


def _backup_before_delete(actor: dict[str, Any], snapshot: dict[str, Any]) -> Path:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    safe_code = re.sub(r"[^A-Za-z0-9_-]+", "_", str(snapshot.get("code") or "dot"))[:80]
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup_dir = EXPORT_DIR / f"backup_truoc_xoa_dot_{safe_code}_{stamp}"
    backup_dir.mkdir(parents=True, exist_ok=False)
    target = backup_dir / "phocap.db"

    src = sqlite3.connect(str(DATABASE_PATH), timeout=30)
    dst = sqlite3.connect(str(target), timeout=30)
    try:
        src.execute("PRAGMA busy_timeout=30000")
        src.backup(dst, pages=1000, sleep=0.05)
        dst.commit()
    finally:
        dst.close()
        src.close()

    check = sqlite3.connect(str(target))
    try:
        integrity = str(check.execute("PRAGMA integrity_check").fetchone()[0])
        fk_rows = check.execute("PRAGMA foreign_key_check").fetchall()
    finally:
        check.close()
    if integrity.lower() != "ok" or fk_rows:
        raise RuntimeError("Backup trước xóa không đạt kiểm tra toàn vẹn.")

    metadata = {
        "backup_type": "before_safe_survey_batch_delete",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "database_source": str(DATABASE_PATH),
        "database_backup": str(target),
        "integrity_check": integrity,
        "foreign_key_check_total": len(fk_rows),
        "batch_snapshot": snapshot,
        "actor": {k: actor.get(k) for k in ("id", "username", "full_name", "role_code")},
    }
    (backup_dir / "thong_tin_backup.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    return backup_dir


def _log_delete(actor: dict[str, Any], snapshot: dict[str, Any], backup_dir: Path) -> None:
    record = {
        "time": datetime.now().isoformat(timespec="seconds"),
        "action": "DELETE_EMPTY_SURVEY_BATCH",
        "batch": snapshot,
        "backup_dir": str(backup_dir),
        "actor": {k: actor.get(k) for k in ("id", "username", "full_name", "role_code")},
    }
    with (EXPORT_DIR / "nhat_ky_xoa_dot_13b11.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


@router.post("/{batch_id}/xoa")
def delete_empty_batch(
    batch_id: int,
    request: Request,
    confirm_checked: str = Form(""),
    confirm_phrase: str = Form(""),
):
    if not _admin(request):
        return _forbidden()

    actor = _user(request)
    backup_dir: Path | None = None
    year_id: int | None = None

    con = sqlite3.connect(str(DATABASE_PATH), timeout=30)
    try:
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("PRAGMA busy_timeout=30000")
        snapshot = _snapshot(con, int(batch_id))
        if snapshot is not None:
            year_id = int(snapshot.get("school_year_id") or 0) or None
        reason = _safety_reason(snapshot, _references(con, int(batch_id)))
    finally:
        con.close()

    if snapshot is None:
        reason = "Không tìm thấy đợt điều tra."
    else:
        expected = f"XOA DOT {snapshot.get('code')}"
        if str(confirm_checked or "").lower() not in {"1", "on", "yes", "true"}:
            reason = "Chưa đánh dấu ô xác nhận xóa."
        if _clean(confirm_phrase, 200) != expected:
            reason = f'Phải nhập chính xác: "{expected}".'

    if reason:
        q = {"status": "delete_blocked", "detail": reason}
        if year_id:
            q["school_year_id"] = year_id
        return RedirectResponse(url="/dieu-tra/quan-ly-dot-toan-tinh?" + urlencode(q), status_code=303)

    try:
        backup_dir = _backup_before_delete(actor, snapshot)
    except Exception:
        q = {"status": "delete_failed"}
        if year_id:
            q["school_year_id"] = year_id
        return RedirectResponse(url="/dieu-tra/quan-ly-dot-toan-tinh?" + urlencode(q), status_code=303)

    write_con = sqlite3.connect(str(DATABASE_PATH), timeout=30)
    try:
        write_con.execute("PRAGMA foreign_keys=ON")
        write_con.execute("PRAGMA busy_timeout=30000")
        write_con.execute("BEGIN IMMEDIATE")
        latest = _snapshot(write_con, int(batch_id))
        latest_reason = _safety_reason(latest, _references(write_con, int(batch_id)))
        if latest_reason:
            write_con.rollback()
            q = {
                "status": "delete_blocked",
                "detail": "Dữ liệu đã thay đổi sau bước kiểm tra ban đầu. " + latest_reason,
                "backup": backup_dir.name,
            }
            if year_id:
                q["school_year_id"] = year_id
            return RedirectResponse(url="/dieu-tra/quan-ly-dot-toan-tinh?" + urlencode(q), status_code=303)

        cur = write_con.execute("DELETE FROM survey_batches WHERE id=?", (int(batch_id),))
        if int(cur.rowcount or 0) != 1:
            raise RuntimeError("Không xóa đúng một đợt điều tra.")
        write_con.commit()
    except Exception:
        write_con.rollback()
        q = {"status": "delete_failed", "backup": backup_dir.name if backup_dir else ""}
        if year_id:
            q["school_year_id"] = year_id
        return RedirectResponse(url="/dieu-tra/quan-ly-dot-toan-tinh?" + urlencode(q), status_code=303)
    finally:
        write_con.close()

    try:
        _log_delete(actor, snapshot, backup_dir)
    except Exception:
        pass

    q = {"status": "batch_deleted", "code": snapshot.get("code") or "", "backup": backup_dir.name}
    if year_id:
        q["school_year_id"] = year_id
    return RedirectResponse(url="/dieu-tra/quan-ly-dot-toan-tinh?" + urlencode(q), status_code=303)


# === BAI_13B_11_3_BULK_DELETE_START ===

BULK_DELETE_CONFIRM_TEXT = "XOA TOAN BO DA CHON"


def _bulk_execution_state_check(
    con: sqlite3.Connection,
    batch_id: int,
) -> tuple[bool, int, str]:
    """
    survey_commune_execution_states là bản ghi đồng hành 1-1 của đợt.
    Chỉ được xem là 'trống' khi hoàn toàn chưa khóa/chưa điều hành:
    - is_commune_locked = 0/NULL
    - is_province_locked = 0/NULL
    - không có thời gian/người/lý do khóa ở cả hai cấp.
    """
    tables = set(_tables(con))
    if "survey_commune_execution_states" not in tables:
        return True, 0, ""

    rows = con.execute(
        """
        SELECT
            id,
            COALESCE(is_commune_locked, 0),
            COALESCE(is_province_locked, 0),
            commune_locked_at,
            commune_locked_by_user_id,
            commune_lock_reason,
            province_locked_at,
            province_locked_by_user_id,
            province_lock_reason
        FROM survey_commune_execution_states
        WHERE survey_batch_id = ?
        ORDER BY id
        """,
        (int(batch_id),),
    ).fetchall()

    if not rows:
        return True, 0, ""

    if len(rows) > 1:
        return (
            False,
            len(rows),
            "Có nhiều hơn 1 bản ghi trạng thái điều hành cho cùng một đợt.",
        )

    row = rows[0]

    commune_locked = bool(row[1])
    province_locked = bool(row[2])

    has_commune_history = any(
        value not in (None, "")
        for value in (row[3], row[4], row[5])
    )
    has_province_history = any(
        value not in (None, "")
        for value in (row[6], row[7], row[8])
    )

    if (
        commune_locked
        or province_locked
        or has_commune_history
        or has_province_history
    ):
        return (
            False,
            1,
            "Bản ghi trạng thái điều hành đã có dấu vết khóa/chốt.",
        )

    return True, 1, ""


def _bulk_noncompanion_references(
    con: sqlite3.Connection,
    batch_id: int,
) -> tuple[list[dict[str, Any]], int, str]:
    """
    Lấy toàn bộ tham chiếu, nhưng chỉ loại riêng
    survey_commune_execution_states.survey_batch_id
    nếu bản ghi trạng thái là hoàn toàn trắng.
    """
    refs = _references(con, batch_id)

    state_ok, state_count, state_error = _bulk_execution_state_check(
        con,
        batch_id,
    )

    if not state_ok:
        return refs, state_count, state_error

    filtered: list[dict[str, Any]] = []

    for item in refs:
        table_name = str(item.get("table") or "")
        column_name = str(item.get("column") or "")

        if (
            table_name == "survey_commune_execution_states"
            and column_name == "survey_batch_id"
        ):
            continue

        filtered.append(item)

    return filtered, state_count, ""


@router.post("/xoa-hang-loat")
async def delete_empty_batches_bulk(request: Request):
    """
    Bài 13B-11.3.4:
    - đúng helper thực tế của Bài 13B-11;
    - cho phép xóa bản ghi execution-state đồng hành nếu hoàn toàn trắng;
    - mọi dữ liệu/phân công/log/phiếu khác vẫn chặn;
    - backup trước khi chạm DB;
    - kiểm tra lại trong BEGIN IMMEDIATE;
    - all-or-nothing.
    """
    if not _admin(request):
        return _forbidden()

    form = await request.form()
    actor = _user(request)

    raw_ids = list(form.getlist("batch_ids"))
    batch_ids: list[int] = []

    for raw in raw_ids:
        try:
            batch_id = int(str(raw or "").strip())
        except (TypeError, ValueError):
            continue

        if batch_id > 0:
            batch_ids.append(batch_id)

    batch_ids = sorted(set(batch_ids))

    try:
        selected_year_id = int(
            str(form.get("school_year_id") or "0").strip()
        )
    except (TypeError, ValueError):
        selected_year_id = 0

    confirm_phrase = _clean(
        form.get("confirm_phrase"),
        200,
    )

    def redirect_blocked(
        detail: str,
        backup_name: str = "",
    ):
        q: dict[str, Any] = {
            "status": "delete_blocked",
            "detail": detail,
        }

        if selected_year_id > 0:
            q["school_year_id"] = selected_year_id

        if backup_name:
            q["backup"] = backup_name

        return RedirectResponse(
            url=(
                "/dieu-tra/quan-ly-dot-toan-tinh?"
                + urlencode(q)
            ),
            status_code=303,
        )

    def redirect_failed(
        backup_name: str = "",
    ):
        q: dict[str, Any] = {
            "status": "delete_failed",
        }

        if selected_year_id > 0:
            q["school_year_id"] = selected_year_id

        if backup_name:
            q["backup"] = backup_name

        return RedirectResponse(
            url=(
                "/dieu-tra/quan-ly-dot-toan-tinh?"
                + urlencode(q)
            ),
            status_code=303,
        )

    if not batch_ids:
        return redirect_blocked(
            "Chưa nhận được danh sách đợt đã chọn. "
            "Chưa xóa đợt nào."
        )

    if len(batch_ids) > 1000:
        return redirect_blocked(
            "Số đợt được chọn vượt giới hạn an toàn 1000 đợt."
        )

    if confirm_phrase != BULK_DELETE_CONFIRM_TEXT:
        return redirect_blocked(
            f'Phải nhập chính xác "{BULK_DELETE_CONFIRM_TEXT}".'
        )

    snapshots: list[dict[str, Any]] = []
    state_rows_total = 0
    actual_year_id: int | None = None

    # =====================================================
    # KIỂM TRA LẦN 1
    # =====================================================
    con = sqlite3.connect(
        str(DATABASE_PATH),
        timeout=30,
    )

    try:
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("PRAGMA busy_timeout=30000")

        for batch_id in batch_ids:
            snapshot = _snapshot(
                con,
                batch_id,
            )

            if snapshot is None:
                return redirect_blocked(
                    f"Không tìm thấy đợt ID {batch_id}. "
                    "Toàn bộ thao tác đã dừng."
                )

            year_id = int(
                snapshot.get("school_year_id") or 0
            )

            if actual_year_id is None:
                actual_year_id = year_id

            if year_id != actual_year_id:
                return redirect_blocked(
                    "Các đợt được chọn không cùng một năm học."
                )

            if (
                selected_year_id > 0
                and year_id != selected_year_id
            ):
                return redirect_blocked(
                    f"Đợt {snapshot.get('code')} không thuộc "
                    "năm học đang hiển thị."
                )

            refs, state_count, state_error = (
                _bulk_noncompanion_references(
                    con,
                    batch_id,
                )
            )

            if state_error:
                return redirect_blocked(
                    f"Đợt {snapshot.get('code')}: {state_error} "
                    "Chưa xóa đợt nào."
                )

            reason = _safety_reason(
                snapshot,
                refs,
            )

            if reason:
                return redirect_blocked(
                    f"Đợt {snapshot.get('code')}: {reason} "
                    "Chưa xóa đợt nào."
                )

            snapshots.append(snapshot)
            state_rows_total += state_count

    finally:
        con.close()

    if selected_year_id <= 0 and actual_year_id:
        selected_year_id = actual_year_id

    # =====================================================
    # MỘT BACKUP CHUNG TRƯỚC KHI XÓA
    # =====================================================
    bulk_snapshot: dict[str, Any] = {
        "id": None,
        "code": (
            f"HANG_LOAT_{len(batch_ids)}_DOT_"
            f"NAM_{selected_year_id or 'KHONG_RO'}"
        ),
        "name": (
            "Bài 13B-11.3.4 - "
            "Xóa hàng loạt đợt trống và execution-state trắng"
        ),
        "status": "CHUAN_BI",
        "school_year_id": (
            selected_year_id
            or actual_year_id
        ),
        "commune_id": None,
        "batch_total": len(batch_ids),
        "execution_state_total": state_rows_total,
        "batch_ids": batch_ids,
        "batch_codes": [
            str(item.get("code") or "")
            for item in snapshots
        ],
    }

    try:
        backup_dir = _backup_before_delete(
            actor,
            bulk_snapshot,
        )
    except Exception:
        return redirect_failed()

    # =====================================================
    # KIỂM TRA LẦN 2 + DELETE TRONG MỘT GIAO DỊCH
    # =====================================================
    write_con = sqlite3.connect(
        str(DATABASE_PATH),
        timeout=30,
    )

    deleted_state_total = 0
    deleted_batch_total = 0

    try:
        write_con.execute("PRAGMA foreign_keys=ON")
        write_con.execute("PRAGMA busy_timeout=30000")
        write_con.execute("BEGIN IMMEDIATE")

        # Kiểm tra lại tất cả trước khi xóa dòng đầu tiên.
        for batch_id in batch_ids:
            latest = _snapshot(
                write_con,
                batch_id,
            )

            refs, _state_count, state_error = (
                _bulk_noncompanion_references(
                    write_con,
                    batch_id,
                )
            )

            if state_error:
                raise RuntimeError(
                    f"Đợt ID {batch_id}: {state_error}"
                )

            latest_reason = _safety_reason(
                latest,
                refs,
            )

            if latest_reason:
                raise RuntimeError(
                    "Dữ liệu đã thay đổi sau kiểm tra ban đầu. "
                    f"Đợt ID {batch_id}: {latest_reason}"
                )

            latest_year_id = int(
                (latest or {}).get(
                    "school_year_id"
                )
                or 0
            )

            if (
                selected_year_id > 0
                and latest_year_id != selected_year_id
            ):
                raise RuntimeError(
                    "Phát hiện thay đổi phạm vi năm học."
                )

        # Chỉ sau khi tất cả vượt kiểm tra lần 2:
        # 1) xóa execution-state trắng;
        # 2) xóa survey_batch.
        for batch_id in batch_ids:
            cur_state = write_con.execute(
                """
                DELETE FROM survey_commune_execution_states
                WHERE survey_batch_id = ?
                """,
                (batch_id,),
            )
            deleted_state_total += max(
                0,
                int(cur_state.rowcount or 0),
            )

        for batch_id in batch_ids:
            cur_batch = write_con.execute(
                """
                DELETE FROM survey_batches
                WHERE id = ?
                """,
                (batch_id,),
            )

            if int(cur_batch.rowcount or 0) != 1:
                raise RuntimeError(
                    f"Không xóa đúng một đợt ID {batch_id}."
                )

            deleted_batch_total += 1

        if deleted_batch_total != len(batch_ids):
            raise RuntimeError(
                "Số đợt đã xóa không khớp số đợt được chọn."
            )

        # Kiểm tra ngay trong transaction: không còn batch đã chọn.
        placeholders = ",".join("?" for _ in batch_ids)
        remaining = int(
            write_con.execute(
                f"""
                SELECT COUNT(*)
                FROM survey_batches
                WHERE id IN ({placeholders})
                """,
                tuple(batch_ids),
            ).fetchone()[0]
            or 0
        )

        if remaining != 0:
            raise RuntimeError(
                f"Sau DELETE vẫn còn {remaining} đợt đã chọn."
            )

        write_con.commit()

    except Exception as exc:
        write_con.rollback()

        return redirect_blocked(
            (
                "Xóa hàng loạt đã được hủy an toàn: "
                + str(exc)[:700]
            ),
            backup_name=backup_dir.name,
        )

    finally:
        write_con.close()

    # =====================================================
    # NHẬT KÝ SAU COMMIT
    # =====================================================
    try:
        for snapshot in snapshots:
            _log_delete(
                actor,
                snapshot,
                backup_dir,
            )
    except Exception:
        pass

    q: dict[str, Any] = {
        "status": "batch_deleted",
        "code": (
            f"{deleted_batch_total} đợt trống đã chọn "
            f"(kèm {deleted_state_total} trạng thái điều hành trắng)"
        ),
        "backup": backup_dir.name,
    }

    if selected_year_id > 0:
        q["school_year_id"] = selected_year_id

    return RedirectResponse(
        url=(
            "/dieu-tra/quan-ly-dot-toan-tinh?"
            + urlencode(q)
        ),
        status_code=303,
    )


# === BAI_13B_11_3_BULK_DELETE_END ===

# === BAI_13B_11_PROVINCE_BATCH_ADMIN_END ===
