"""Confirmed, school/year-scoped removal of mistakenly imported staff lists."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import secrets
import time
from datetime import datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session, selectinload

from app.database import DATABASE_PATH, get_db
from app.models import School, SchoolYear
from app.staff_models import StaffYearRecord
from app.routers.staff_management import _can_manage, _ensure_school_in_scope, templates
from app.routers.surveys import lay_thong_tin_nguoi_dung

router = APIRouter(prefix="/doi-ngu")
# The Docker deployment persists and grants write access to the data directory.
BACKUP_DIR = DATABASE_PATH.parent / "backups" / "staff_list_delete"
logger = logging.getLogger(__name__)
GROUPS = {"GIAO_VIEN": "Chỉ giáo viên", "ALL": "Toàn bộ đội ngũ (giáo viên, cán bộ quản lý, nhân viên)"}


def _scope(request, db, school_id, school_year_id, group):
    user = lay_thong_tin_nguoi_dung(request)
    if not _can_manage(user) or not _ensure_school_in_scope(user, school_id):
        raise HTTPException(403, "Tài khoản không có quyền xóa danh sách của trường này.")
    school, year = db.get(School, school_id), db.get(SchoolYear, school_year_id)
    if not school or not year or group not in GROUPS:
        raise HTTPException(400, "Hãy chọn đúng một trường, năm học và nhóm cần xóa.")
    return user, school, year


def _conditions(school_id, school_year_id, group):
    conditions = [StaffYearRecord.school_id == school_id, StaffYearRecord.school_year_id == school_year_id]
    if group != "ALL":
        conditions.append(StaffYearRecord.position_group == group)
    return conditions


def _snapshot(db, school_id, school_year_id, group):
    records = db.scalars(select(StaffYearRecord).where(*_conditions(school_id, school_year_id, group))
                         .options(selectinload(StaffYearRecord.staff_member)).order_by(StaffYearRecord.id)).all()
    rows = [{c.name: getattr(record, c.name) for c in StaffYearRecord.__table__.columns} for record in records]
    encoded = json.dumps(rows, ensure_ascii=False, sort_keys=True, default=str)
    return records, rows, hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@router.get("/xoa-danh-sach")
def preview(request: Request, school_id: int, school_year_id: int,
            group: str = "GIAO_VIEN", db: Session = Depends(get_db)):
    user, school, year = _scope(request, db, school_id, school_year_id, group)
    records, _, digest = _snapshot(db, school_id, school_year_id, group)
    token = secrets.token_urlsafe(32)
    request.session["staff_delete"] = dict(token=token, actor=user.get("id"), school=school_id,
                                           year=school_year_id, group=group, digest=digest, expires=time.time() + 900)
    return templates.TemplateResponse(request=request, name="staff/delete_list.html", context={
        "nguoi_dung": user, "school": school, "year": year, "group": group, "groups": GROUPS,
        "records": records, "token": token,
    })


@router.post("/xoa-danh-sach")
def execute(request: Request, school_id: int = Form(...), school_year_id: int = Form(...),
            group: str = Form(...), token: str = Form(...), confirmation: str = Form(""),
            db: Session = Depends(get_db)):
    user = lay_thong_tin_nguoi_dung(request)
    pending = request.session.get("staff_delete", {})
    if (not secrets.compare_digest(str(pending.get("token", "")), token) or not token
            or pending.get("actor") != user.get("id") or pending.get("school") != school_id
            or pending.get("year") != school_year_id or pending.get("group") != group
            or pending.get("expires", 0) < time.time()):
        raise HTTPException(403, "Xác nhận không hợp lệ hoặc đã hết hạn. Hãy mở lại màn hình xóa danh sách.")
    # This application uses SQLite. Reserve the write lock before re-reading the
    # previewed data so a simultaneous import cannot change the deletion set.
    stage = "lock"
    try:
        db.execute(text("BEGIN IMMEDIATE"))
        _, school, year = _scope(request, db, school_id, school_year_id, group)
        if confirmation.strip() != "XOA":
            raise HTTPException(400, "Nhập XOA để xác nhận.")
        records, rows, digest = _snapshot(db, school_id, school_year_id, group)
        if digest != pending.get("digest") or not records:
            raise HTTPException(409, "Danh sách đã thay đổi hoặc không còn hồ sơ. Hãy mở lại màn hình xác nhận.")
        backup = {
            "format": "staff_year_records_delete_v1", "created_at": datetime.now().isoformat(),
            "actor_user_id": user.get("id"), "school_id": school_id, "school_name": school.name,
            "school_year_id": school_year_id, "school_year": year.code, "group": group,
            "count": len(rows), "digest": digest, "records": rows,
        }
        stage = "backup"
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        path = BACKUP_DIR / f"{datetime.now():%Y%m%d_%H%M%S}_{secrets.token_hex(8)}.json"
        # A complete durable recovery copy is required before any SQL deletion.
        with path.open("x", encoding="utf-8") as stream:
            json.dump(backup, stream, ensure_ascii=False, indent=2, default=str)
            stream.flush()
            os.fsync(stream.fileno())
        stage = "delete"
        result = db.execute(delete(StaffYearRecord).where(*_conditions(school_id, school_year_id, group)))
        if result.rowcount != len(rows):
            raise HTTPException(409, "Danh sách đã thay đổi. Chưa xóa dữ liệu; hãy kiểm tra lại.")
        stage = "commit"
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        logger.exception("Staff list deletion failed at %s (school_id=%s, school_year_id=%s)", stage, school_id, school_year_id)
        message = ("Chưa xóa dữ liệu: không thể tạo bản sao lưu. Vui lòng liên hệ quản trị để kiểm tra quyền ghi hoặc dung lượng lưu trữ."
                   if stage == "backup" else "Chưa xóa dữ liệu: không thể lưu thay đổi. Vui lòng thử lại.")
        if stage == "backup":
            return templates.TemplateResponse(request=request, name="staff/delete_list.html", status_code=503, context={
                "nguoi_dung": user, "school": school, "year": year, "group": group, "groups": GROUPS,
                "records": records, "token": token, "error_message": message,
            })
        raise HTTPException(503, message) from exc
    request.session.pop("staff_delete", None)
    return RedirectResponse(f"/doi-ngu?school_year_id={school_year_id}&school_id={school_id}&status=deleted_{len(rows)}", status_code=303)
