from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path

PROJECT = Path(os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")).resolve()
APP = PROJECT / "app"
MAIN = APP / "main.py"
INDEX = APP / "templates" / "surveys" / "index.html"
ROUTER = APP / "routers" / "survey_batch_admin_v13b11.py"
TEMPLATE = APP / "templates" / "surveys" / "province_batch_admin_v13b11.html"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = PROJECT / "exports" / f"backup_source_bai_13b_11_{STAMP}"
MANIFEST = BACKUP / "manifest.json"

MARK_MAIN = "BAI_13B_11_PROVINCE_BATCH_ADMIN_ROUTER"
MARK_INDEX = "BAI_13B_11_PROVINCE_BATCH_ADMIN_UI"

ROUTER_CODE = 'from __future__ import annotations\n\nimport json\nimport re\nimport sqlite3\nfrom datetime import date, datetime\nfrom pathlib import Path\nfrom typing import Any\nfrom urllib.parse import urlencode\n\nfrom fastapi import APIRouter, Depends, Form, Query, Request\nfrom fastapi.responses import HTMLResponse, RedirectResponse\nfrom fastapi.templating import Jinja2Templates\nfrom sqlalchemy import func, select\nfrom sqlalchemy.orm import Session, selectinload\n\nfrom app.database import DATABASE_PATH, get_db\nfrom app.models import Commune, SchoolYear\nfrom app.permissions import is_admin_role, normalize_role_code\nfrom app.routers.surveys import BATCH_STATUS_LABELS, lay_thong_tin_nguoi_dung, tao_ma_dot_dieu_tra\nfrom app.survey_models import SurveyBatch, SurveyForm\n\n# === BAI_13B_11_PROVINCE_BATCH_ADMIN_START ===\n\nAPP_DIR = Path(__file__).resolve().parent.parent\nPROJECT_DIR = APP_DIR.parent\nEXPORT_DIR = PROJECT_DIR / "exports"\ntemplates = Jinja2Templates(directory=str(APP_DIR / "templates"))\n\nrouter = APIRouter(\n    prefix="/dieu-tra/quan-ly-dot-toan-tinh",\n    tags=["Bài 13B-11 - Quản lý đợt toàn tỉnh"],\n)\n\nCREATE_CONFIRM_TEXT = "KHOI TAO TOAN TINH"\n\n\ndef _user(request: Request) -> dict[str, Any]:\n    return dict(lay_thong_tin_nguoi_dung(request) or {})\n\n\ndef _admin(request: Request) -> bool:\n    return is_admin_role(normalize_role_code(_user(request).get("role_code")))\n\n\ndef _forbidden() -> RedirectResponse:\n    return RedirectResponse(url="/?status=forbidden", status_code=303)\n\n\ndef _clean(value: Any, limit: int = 1000) -> str:\n    return " ".join(str(value or "").strip().split())[:limit]\n\n\ndef _parse_date(value: Any) -> tuple[date | None, str | None]:\n    text = str(value or "").strip()\n    if not text:\n        return None, None\n    try:\n        return date.fromisoformat(text), None\n    except ValueError:\n        return None, "Ngày không đúng định dạng YYYY-MM-DD."\n\n\ndef _pick_year(db: Session, year_id: int | None) -> SchoolYear | None:\n    if year_id:\n        year = db.get(SchoolYear, int(year_id))\n        if year is not None and bool(getattr(year, "is_active", True)):\n            return year\n    return db.scalar(\n        select(SchoolYear)\n        .where(SchoolYear.is_active.is_(True))\n        .order_by(SchoolYear.code.desc(), SchoolYear.id.desc())\n        .limit(1)\n    )\n\n\ndef _page_data(db: Session, year_id: int | None) -> dict[str, Any]:\n    years = list(db.scalars(\n        select(SchoolYear)\n        .where(SchoolYear.is_active.is_(True))\n        .order_by(SchoolYear.code.desc(), SchoolYear.id.desc())\n    ).all())\n    year = _pick_year(db, year_id)\n    communes = list(db.scalars(\n        select(Commune)\n        .where(Commune.is_active.is_(True))\n        .order_by(Commune.name.asc(), Commune.id.asc())\n    ).all())\n\n    batches: list[SurveyBatch] = []\n    form_counts: dict[int, int] = {}\n    if year is not None:\n        batches = list(db.scalars(\n            select(SurveyBatch)\n            .options(selectinload(SurveyBatch.commune), selectinload(SurveyBatch.school_year))\n            .where(SurveyBatch.school_year_id == year.id)\n            .order_by(SurveyBatch.commune_id.asc(), SurveyBatch.created_at.desc(), SurveyBatch.id.desc())\n        ).all())\n        if batches:\n            ids = [int(x.id) for x in batches]\n            count_rows = db.execute(\n                select(SurveyForm.survey_batch_id, func.count(SurveyForm.id))\n                .where(SurveyForm.survey_batch_id.in_(ids))\n                .group_by(SurveyForm.survey_batch_id)\n            ).all()\n            form_counts = {int(bid): int(total or 0) for bid, total in count_rows}\n\n    by_commune: dict[int, list[SurveyBatch]] = {}\n    for batch in batches:\n        by_commune.setdefault(int(batch.commune_id), []).append(batch)\n\n    rows = []\n    commune_with_batch = 0\n    duplicate_total = 0\n    for commune in communes:\n        items = by_commune.get(int(commune.id), [])\n        if items:\n            commune_with_batch += 1\n            duplicate_total += max(0, len(items) - 1)\n        rows.append({"commune": commune, "batches": items, "has_batch": bool(items), "batch_total": len(items)})\n\n    batch_rows = []\n    for batch in batches:\n        form_total = int(form_counts.get(int(batch.id), 0))\n        locked = bool(getattr(batch, "is_locked", False))\n        prelim = str(batch.status or "") == "CHUAN_BI" and not locked and form_total == 0\n        batch_rows.append({\n            "batch": batch,\n            "form_total": form_total,\n            "is_locked": locked,\n            "prelim_deletable": prelim,\n            "delete_phrase": f"XOA DOT {batch.code}",\n        })\n\n    return {\n        "school_years": years,\n        "selected_year": year,\n        "selected_year_id": year.id if year else None,\n        "rows": rows,\n        "batch_rows": batch_rows,\n        "active_commune_total": len(communes),\n        "commune_with_batch_total": commune_with_batch,\n        "missing_commune_total": max(0, len(communes) - commune_with_batch),\n        "batch_total": len(batches),\n        "duplicate_batch_total": duplicate_total,\n    }\n\n\ndef _status_message(status: str | None, params: dict[str, Any]) -> tuple[str | None, str | None]:\n    if status == "province_created":\n        return (f"Đã tạo {params.get(\'created\',\'0\')} đợt còn thiếu; bỏ qua {params.get(\'skipped\',\'0\')} xã/phường đã có đợt.", None)\n    if status == "nothing_to_create":\n        return ("Toàn bộ xã/phường đang hoạt động đã có đợt trong năm học này; không tạo bản ghi trùng.", None)\n    if status == "batch_deleted":\n        return (f"Đã xóa an toàn đợt {_clean(params.get(\'code\'),100)}. Backup: {_clean(params.get(\'backup\'),300)}.", None)\n    if status == "delete_blocked":\n        return (None, "Không thể xóa đợt. " + (_clean(params.get(\'detail\'),800) or "Đợt không đạt điều kiện an toàn."))\n    if status == "create_blocked":\n        return (None, "Không thể khởi tạo toàn tỉnh. " + (_clean(params.get(\'detail\'),800) or "Dữ liệu chưa hợp lệ."))\n    if status == "create_failed":\n        return (None, "Khởi tạo không thành công; toàn bộ giao dịch đã rollback, không có đợt nào được tạo dở.")\n    if status == "delete_failed":\n        suffix = f" Backup đã tạo: {_clean(params.get(\'backup\'),300)}." if params.get("backup") else ""\n        return (None, "Xóa đợt không thành công; dữ liệu hiện hành được giữ nguyên." + suffix)\n    return None, None\n\n\ndef _render(request: Request, db: Session, year_id: int | None, status: str | None = None, params: dict[str, Any] | None = None):\n    message, error = _status_message(status, params or {})\n    return templates.TemplateResponse(\n        request=request,\n        name="surveys/province_batch_admin_v13b11.html",\n        context={\n            "nguoi_dung": _user(request),\n            "status_labels": BATCH_STATUS_LABELS,\n            "create_confirm_text": CREATE_CONFIRM_TEXT,\n            "message": message,\n            "error": error,\n            "today": date.today().isoformat(),\n            **_page_data(db, year_id),\n        },\n    )\n\n\n@router.get("", response_class=HTMLResponse)\ndef page(\n    request: Request,\n    school_year_id: int | None = Query(default=None),\n    status: str | None = Query(default=None),\n    created: str | None = Query(default=None),\n    skipped: str | None = Query(default=None),\n    backup: str | None = Query(default=None),\n    code: str | None = Query(default=None),\n    detail: str | None = Query(default=None),\n    db: Session = Depends(get_db),\n):\n    if not _admin(request):\n        return _forbidden()\n    return _render(request, db, school_year_id, status, {\n        "created": created, "skipped": skipped, "backup": backup, "code": code, "detail": detail,\n    })\n\n\n@router.post("/khoi-tao")\ndef create_all_missing(\n    request: Request,\n    school_year_id: int = Form(...),\n    name: str = Form(...),\n    start_date: str = Form(...),\n    end_date: str = Form(""),\n    notes: str = Form(""),\n    confirm_text: str = Form(""),\n    db: Session = Depends(get_db),\n):\n    if not _admin(request):\n        return _forbidden()\n\n    year = db.get(SchoolYear, int(school_year_id))\n    clean_name = _clean(name, 300)\n    clean_notes = _clean(notes, 3000)\n    parsed_start, start_error = _parse_date(start_date)\n    parsed_end, end_error = _parse_date(end_date)\n    errors: list[str] = []\n\n    if year is None or not bool(getattr(year, "is_active", True)):\n        errors.append("Năm học không hợp lệ hoặc đã ngừng sử dụng.")\n    if not clean_name:\n        errors.append("Tên đợt điều tra không được để trống.")\n    if parsed_start is None:\n        errors.append(start_error or "Ngày bắt đầu không được để trống.")\n    if end_error:\n        errors.append(end_error)\n    if parsed_start and parsed_end and parsed_end < parsed_start:\n        errors.append("Ngày kết thúc không được trước ngày bắt đầu.")\n    if _clean(confirm_text, 100).upper() != CREATE_CONFIRM_TEXT:\n        errors.append(f\'Phải nhập chính xác "{CREATE_CONFIRM_TEXT}" để xác nhận.\')\n\n    communes = list(db.scalars(\n        select(Commune).where(Commune.is_active.is_(True)).order_by(Commune.id.asc())\n    ).all())\n    if not communes:\n        errors.append("Không có xã/phường đang hoạt động để khởi tạo.")\n\n    if errors:\n        return RedirectResponse(\n            url="/dieu-tra/quan-ly-dot-toan-tinh?" + urlencode({\n                "school_year_id": school_year_id,\n                "status": "create_blocked",\n                "detail": " ".join(errors),\n            }),\n            status_code=303,\n        )\n\n    existing_ids = {int(x) for x in db.scalars(\n        select(SurveyBatch.commune_id).where(SurveyBatch.school_year_id == year.id)\n    ).all()}\n    missing = [c for c in communes if int(c.id) not in existing_ids]\n\n    if not missing:\n        return RedirectResponse(\n            url="/dieu-tra/quan-ly-dot-toan-tinh?" + urlencode({\n                "school_year_id": year.id, "status": "nothing_to_create"\n            }),\n            status_code=303,\n        )\n\n    actor = _user(request)\n    created = 0\n    try:\n        for commune in missing:\n            batch = SurveyBatch(\n                code=tao_ma_dot_dieu_tra(db=db, commune=commune, school_year=year),\n                name=clean_name,\n                school_year_id=year.id,\n                commune_id=commune.id,\n                status="CHUAN_BI",\n                start_date=parsed_start,\n                end_date=parsed_end,\n                created_by_user_id=actor.get("id"),\n                notes=("Bài 13B-11 - Khởi tạo toàn tỉnh. " + clean_notes).strip(),\n            )\n            db.add(batch)\n            db.flush()\n            created += 1\n        db.commit()\n    except Exception:\n        db.rollback()\n        return RedirectResponse(\n            url="/dieu-tra/quan-ly-dot-toan-tinh?" + urlencode({\n                "school_year_id": year.id, "status": "create_failed"\n            }),\n            status_code=303,\n        )\n\n    return RedirectResponse(\n        url="/dieu-tra/quan-ly-dot-toan-tinh?" + urlencode({\n            "school_year_id": year.id,\n            "status": "province_created",\n            "created": created,\n            "skipped": len(existing_ids),\n        }),\n        status_code=303,\n    )\n\n\ndef _qi(name: str) -> str:\n    return \'"\' + str(name).replace(\'"\', \'""\') + \'"\'\n\n\ndef _tables(con: sqlite3.Connection) -> list[str]:\n    return [str(r[0]) for r in con.execute(\n        "SELECT name FROM sqlite_master WHERE type=\'table\' AND name NOT LIKE \'sqlite_%\' ORDER BY name"\n    ).fetchall()]\n\n\ndef _columns(con: sqlite3.Connection, table: str) -> set[str]:\n    return {str(r[1]) for r in con.execute(f"PRAGMA table_info({_qi(table)})").fetchall()}\n\n\ndef _snapshot(con: sqlite3.Connection, batch_id: int) -> dict[str, Any] | None:\n    cols = _columns(con, "survey_batches")\n    wanted = ["id", "code", "name", "status", "school_year_id", "commune_id", "start_date", "end_date", "created_at"]\n    for optional in ("is_locked", "locked_at"):\n        if optional in cols:\n            wanted.append(optional)\n    row = con.execute(\n        "SELECT " + ", ".join(_qi(x) for x in wanted) + " FROM survey_batches WHERE id=? LIMIT 1",\n        (int(batch_id),),\n    ).fetchone()\n    if row is None:\n        return None\n    return {wanted[i]: row[i] for i in range(len(wanted))}\n\n\ndef _references(con: sqlite3.Connection, batch_id: int) -> list[dict[str, Any]]:\n    out: list[dict[str, Any]] = []\n    for table in _tables(con):\n        if table == "survey_batches":\n            continue\n        cols = _columns(con, table)\n        candidates: set[str] = set()\n        for fk in con.execute(f"PRAGMA foreign_key_list({_qi(table)})").fetchall():\n            if str(fk[2] or "") == "survey_batches" and str(fk[3] or ""):\n                candidates.add(str(fk[3]))\n        for conventional in ("survey_batch_id", "source_batch_id", "target_batch_id", "batch_id"):\n            if conventional in cols:\n                candidates.add(conventional)\n        for col in sorted(candidates):\n            count = int(con.execute(\n                f"SELECT COUNT(*) FROM {_qi(table)} WHERE {_qi(col)}=?", (int(batch_id),)\n            ).fetchone()[0] or 0)\n            if count > 0:\n                out.append({"table": table, "column": col, "count": count})\n    return out\n\n\ndef _safety_reason(snapshot: dict[str, Any] | None, references: list[dict[str, Any]]) -> str | None:\n    if snapshot is None:\n        return "Không tìm thấy đợt điều tra."\n    if str(snapshot.get("status") or "") != "CHUAN_BI":\n        return f"Chỉ được xóa đợt còn Chuẩn bị; trạng thái hiện tại là {snapshot.get(\'status\')}."\n    if bool(snapshot.get("is_locked")) or bool(snapshot.get("locked_at")):\n        return "Đợt đã khóa/chốt nên không cho phép xóa."\n    if references:\n        detail = "; ".join(\n            f"{x[\'table\']}.{x[\'column\']}: {x[\'count\']}" for x in references[:8]\n        )\n        if len(references) > 8:\n            detail += f"; và {len(references)-8} nhóm tham chiếu khác"\n        return "Đợt đang có dữ liệu hoặc bản ghi phụ thuộc: " + detail\n    return None\n\n\ndef _backup_before_delete(actor: dict[str, Any], snapshot: dict[str, Any]) -> Path:\n    EXPORT_DIR.mkdir(parents=True, exist_ok=True)\n    safe_code = re.sub(r"[^A-Za-z0-9_-]+", "_", str(snapshot.get("code") or "dot"))[:80]\n    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")\n    backup_dir = EXPORT_DIR / f"backup_truoc_xoa_dot_{safe_code}_{stamp}"\n    backup_dir.mkdir(parents=True, exist_ok=False)\n    target = backup_dir / "phocap.db"\n\n    src = sqlite3.connect(str(DATABASE_PATH), timeout=30)\n    dst = sqlite3.connect(str(target), timeout=30)\n    try:\n        src.execute("PRAGMA busy_timeout=30000")\n        src.backup(dst, pages=1000, sleep=0.05)\n        dst.commit()\n    finally:\n        dst.close()\n        src.close()\n\n    check = sqlite3.connect(str(target))\n    try:\n        integrity = str(check.execute("PRAGMA integrity_check").fetchone()[0])\n        fk_rows = check.execute("PRAGMA foreign_key_check").fetchall()\n    finally:\n        check.close()\n    if integrity.lower() != "ok" or fk_rows:\n        raise RuntimeError("Backup trước xóa không đạt kiểm tra toàn vẹn.")\n\n    metadata = {\n        "backup_type": "before_safe_survey_batch_delete",\n        "created_at": datetime.now().isoformat(timespec="seconds"),\n        "database_source": str(DATABASE_PATH),\n        "database_backup": str(target),\n        "integrity_check": integrity,\n        "foreign_key_check_total": len(fk_rows),\n        "batch_snapshot": snapshot,\n        "actor": {k: actor.get(k) for k in ("id", "username", "full_name", "role_code")},\n    }\n    (backup_dir / "thong_tin_backup.json").write_text(\n        json.dumps(metadata, ensure_ascii=False, indent=2, default=str), encoding="utf-8"\n    )\n    return backup_dir\n\n\ndef _log_delete(actor: dict[str, Any], snapshot: dict[str, Any], backup_dir: Path) -> None:\n    record = {\n        "time": datetime.now().isoformat(timespec="seconds"),\n        "action": "DELETE_EMPTY_SURVEY_BATCH",\n        "batch": snapshot,\n        "backup_dir": str(backup_dir),\n        "actor": {k: actor.get(k) for k in ("id", "username", "full_name", "role_code")},\n    }\n    with (EXPORT_DIR / "nhat_ky_xoa_dot_13b11.jsonl").open("a", encoding="utf-8") as f:\n        f.write(json.dumps(record, ensure_ascii=False, default=str) + "\\n")\n\n\n@router.post("/{batch_id}/xoa")\ndef delete_empty_batch(\n    batch_id: int,\n    request: Request,\n    confirm_checked: str = Form(""),\n    confirm_phrase: str = Form(""),\n):\n    if not _admin(request):\n        return _forbidden()\n\n    actor = _user(request)\n    backup_dir: Path | None = None\n    year_id: int | None = None\n\n    con = sqlite3.connect(str(DATABASE_PATH), timeout=30)\n    try:\n        con.execute("PRAGMA foreign_keys=ON")\n        con.execute("PRAGMA busy_timeout=30000")\n        snapshot = _snapshot(con, int(batch_id))\n        if snapshot is not None:\n            year_id = int(snapshot.get("school_year_id") or 0) or None\n        reason = _safety_reason(snapshot, _references(con, int(batch_id)))\n    finally:\n        con.close()\n\n    if snapshot is None:\n        reason = "Không tìm thấy đợt điều tra."\n    else:\n        expected = f"XOA DOT {snapshot.get(\'code\')}"\n        if str(confirm_checked or "").lower() not in {"1", "on", "yes", "true"}:\n            reason = "Chưa đánh dấu ô xác nhận xóa."\n        if _clean(confirm_phrase, 200) != expected:\n            reason = f\'Phải nhập chính xác: "{expected}".\'\n\n    if reason:\n        q = {"status": "delete_blocked", "detail": reason}\n        if year_id:\n            q["school_year_id"] = year_id\n        return RedirectResponse(url="/dieu-tra/quan-ly-dot-toan-tinh?" + urlencode(q), status_code=303)\n\n    try:\n        backup_dir = _backup_before_delete(actor, snapshot)\n    except Exception:\n        q = {"status": "delete_failed"}\n        if year_id:\n            q["school_year_id"] = year_id\n        return RedirectResponse(url="/dieu-tra/quan-ly-dot-toan-tinh?" + urlencode(q), status_code=303)\n\n    write_con = sqlite3.connect(str(DATABASE_PATH), timeout=30)\n    try:\n        write_con.execute("PRAGMA foreign_keys=ON")\n        write_con.execute("PRAGMA busy_timeout=30000")\n        write_con.execute("BEGIN IMMEDIATE")\n        latest = _snapshot(write_con, int(batch_id))\n        latest_reason = _safety_reason(latest, _references(write_con, int(batch_id)))\n        if latest_reason:\n            write_con.rollback()\n            q = {\n                "status": "delete_blocked",\n                "detail": "Dữ liệu đã thay đổi sau bước kiểm tra ban đầu. " + latest_reason,\n                "backup": backup_dir.name,\n            }\n            if year_id:\n                q["school_year_id"] = year_id\n            return RedirectResponse(url="/dieu-tra/quan-ly-dot-toan-tinh?" + urlencode(q), status_code=303)\n\n        cur = write_con.execute("DELETE FROM survey_batches WHERE id=?", (int(batch_id),))\n        if int(cur.rowcount or 0) != 1:\n            raise RuntimeError("Không xóa đúng một đợt điều tra.")\n        write_con.commit()\n    except Exception:\n        write_con.rollback()\n        q = {"status": "delete_failed", "backup": backup_dir.name if backup_dir else ""}\n        if year_id:\n            q["school_year_id"] = year_id\n        return RedirectResponse(url="/dieu-tra/quan-ly-dot-toan-tinh?" + urlencode(q), status_code=303)\n    finally:\n        write_con.close()\n\n    try:\n        _log_delete(actor, snapshot, backup_dir)\n    except Exception:\n        pass\n\n    q = {"status": "batch_deleted", "code": snapshot.get("code") or "", "backup": backup_dir.name}\n    if year_id:\n        q["school_year_id"] = year_id\n    return RedirectResponse(url="/dieu-tra/quan-ly-dot-toan-tinh?" + urlencode(q), status_code=303)\n\n# === BAI_13B_11_PROVINCE_BATCH_ADMIN_END ===\n'
TEMPLATE_CODE = '<!DOCTYPE html>\n<html lang="vi">\n<head>\n<meta charset="UTF-8">\n<meta name="viewport" content="width=device-width, initial-scale=1.0">\n<title>Khởi tạo đợt điều tra toàn tỉnh</title>\n<link rel="stylesheet" href="{{ url_for(\'static\', path=\'/css/style.css\') }}">\n<style>\n.b1311-page{max-width:1380px;margin:0 auto;padding:22px 18px 48px}.b1311-hero{border-radius:16px;padding:24px;margin-bottom:20px;background:linear-gradient(135deg,#0d5fb8,#2385d7);color:#fff}.b1311-hero h1{margin:4px 0 8px;font-size:30px}.b1311-hero p{margin:0;opacity:.95}.b1311-grid{display:grid;grid-template-columns:minmax(340px,.9fr) minmax(0,1.7fr);gap:18px;align-items:start}.b1311-card{background:#fff;border:1px solid #dce6ef;border-radius:14px;padding:20px;margin-bottom:18px;box-shadow:0 4px 16px rgba(14,55,92,.05)}.b1311-card h2{margin:0 0 14px}.b1311-field{margin-bottom:13px}.b1311-field label{display:block;margin-bottom:6px;font-weight:700}.b1311-control{width:100%;padding:11px 12px;border:1px solid #c9d7e4;border-radius:9px;font:inherit;background:#fff;box-sizing:border-box}textarea.b1311-control{min-height:90px;resize:vertical}.b1311-summary{display:grid;grid-template-columns:repeat(5,minmax(130px,1fr));gap:10px;margin-bottom:16px}.b1311-stat{padding:14px;border:1px solid #dbe7f0;border-radius:12px;background:#f8fbfe}.b1311-stat span{display:block;color:#60758a;font-size:12px;font-weight:700;text-transform:uppercase}.b1311-stat strong{display:block;margin-top:6px;font-size:25px;color:#0d5fb8}.b1311-notice{padding:13px 14px;border-radius:10px;margin-bottom:14px;line-height:1.5}.b1311-ok{background:#eaf7ed;border:1px solid #b9dfc1;color:#17652c}.b1311-error{background:#fff1f0;border:1px solid #efc1bc;color:#a1261c}.b1311-warn{background:#fff8e5;border:1px solid #f2d78b;color:#6f5300}.b1311-table-wrap{overflow-x:auto}.b1311-table{width:100%;min-width:1050px;border-collapse:collapse}.b1311-table th,.b1311-table td{padding:10px 9px;border-bottom:1px solid #e4ebf1;text-align:left;vertical-align:top}.b1311-table th{background:#f3f7fb;font-size:13px}.b1311-pill{display:inline-block;padding:4px 8px;border-radius:999px;font-size:12px;font-weight:700}.b1311-ready{background:#eaf7ed;color:#17652c}.b1311-missing{background:#fff3df;color:#7b5000}.b1311-danger{background:#ffebee;color:#8b1b1b}.b1311-actions{display:flex;gap:9px;flex-wrap:wrap;align-items:center}.b1311-delete-form{display:grid;gap:7px;min-width:260px}.b1311-delete-form input[type=text]{width:100%;padding:8px 9px;border:1px solid #d0d9e2;border-radius:7px;box-sizing:border-box}.b1311-danger-button{border:1px solid #b42318;background:#b42318;color:#fff;border-radius:8px;padding:9px 12px;cursor:pointer;font-weight:700}.b1311-confirm{padding:12px;background:#f7fbff;border:1px dashed #9cc6e8;border-radius:10px;margin-bottom:13px}.b1311-code{font-family:Consolas,monospace;font-size:13px;overflow-wrap:anywhere}@media(max-width:1000px){.b1311-grid{grid-template-columns:1fr}.b1311-summary{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:600px){.b1311-summary{grid-template-columns:1fr}}\n</style>\n</head>\n<body>\n{% include "partials/dropdown_menu_v1.html" %}\n<main class="b1311-page">\n<section class="b1311-hero"><div style="font-size:13px;font-weight:800;letter-spacing:.08em">BÀI 13B-11 · QUẢN LÝ ĐỢT ĐIỀU TRA CẤP TỈNH</div><h1>Khởi tạo toàn tỉnh + Xóa đợt tạo nhầm an toàn</h1><p>Sở tạo một lần cho toàn bộ xã/phường đang hoạt động. Hệ thống không tạo trùng xã đã có đợt và không tự xóa dữ liệu hiện có.</p></section>\n{% if message %}<div class="b1311-notice b1311-ok">{{ message }}</div>{% endif %}\n{% if error %}<div class="b1311-notice b1311-error">{{ error }}</div>{% endif %}\n<section class="b1311-card"><form method="get" action="/dieu-tra/quan-ly-dot-toan-tinh"><div class="b1311-actions"><div style="min-width:260px;flex:1"><label for="school_year_filter"><strong>Năm học đang quản lý</strong></label><select id="school_year_filter" name="school_year_id" class="b1311-control" onchange="this.form.submit()">{% for year in school_years %}<option value="{{ year.id }}" {% if selected_year_id == year.id %}selected{% endif %}>{{ year.code }}</option>{% endfor %}</select></div><a class="button button-secondary" href="/dieu-tra">← Danh sách đợt điều tra</a></div></form></section>\n{% if selected_year %}\n<section class="b1311-summary"><div class="b1311-stat"><span>Xã/phường hoạt động</span><strong>{{ active_commune_total }}</strong></div><div class="b1311-stat"><span>Đã có đợt</span><strong>{{ commune_with_batch_total }}</strong></div><div class="b1311-stat"><span>Còn thiếu</span><strong>{{ missing_commune_total }}</strong></div><div class="b1311-stat"><span>Tổng bản ghi đợt</span><strong>{{ batch_total }}</strong></div><div class="b1311-stat"><span>Đợt trùng địa bàn/năm</span><strong>{{ duplicate_batch_total }}</strong></div></section>\n<div class="b1311-grid"><div><section class="b1311-card"><h2>1. Khởi tạo đợt cho toàn tỉnh</h2><div class="b1311-notice b1311-warn">Chỉ tạo cho các xã/phường <strong>chưa có bất kỳ đợt nào</strong> trong năm học {{ selected_year.code }}. Xã đã có đợt được bỏ qua để bảo toàn dữ liệu.</div><form method="post" action="/dieu-tra/quan-ly-dot-toan-tinh/khoi-tao" onsubmit="return confirm(\'Khởi tạo đợt cho tất cả xã/phường còn thiếu của năm học này?\');"><input type="hidden" name="school_year_id" value="{{ selected_year.id }}"><div class="b1311-field"><label>Tên đợt điều tra</label><input class="b1311-control" type="text" name="name" maxlength="300" value="Điều tra phổ cập giáo dục đầu năm học {{ selected_year.code }}" required></div><div class="b1311-field"><label>Ngày bắt đầu</label><input class="b1311-control" type="date" name="start_date" value="{{ today }}" required></div><div class="b1311-field"><label>Ngày kết thúc dự kiến</label><input class="b1311-control" type="date" name="end_date"></div><div class="b1311-field"><label>Ghi chú</label><textarea class="b1311-control" name="notes" placeholder="Nội dung chung áp dụng cho toàn tỉnh"></textarea></div><div class="b1311-confirm"><strong>Xác nhận:</strong> nhập chính xác <span class="b1311-code">{{ create_confirm_text }}</span> để khởi tạo {{ missing_commune_total }} xã/phường còn thiếu.</div><div class="b1311-field"><input class="b1311-control" type="text" name="confirm_text" autocomplete="off" placeholder="{{ create_confirm_text }}" required></div><button class="button button-primary" type="submit" {% if missing_commune_total == 0 %}disabled{% endif %}>🌐 Khởi tạo các đợt còn thiếu toàn tỉnh</button></form></section></div>\n<div><section class="b1311-card"><h2>2. Kiểm tra phạm vi trước khi tạo</h2><div class="b1311-table-wrap"><table class="b1311-table" style="min-width:720px"><thead><tr><th>STT</th><th>Xã/phường</th><th>Tình trạng {{ selected_year.code }}</th><th>Số đợt</th></tr></thead><tbody>{% for row in rows %}<tr><td>{{ loop.index }}</td><td><strong>{{ row.commune.name }}</strong><div class="b1311-code">{{ row.commune.code }}</div></td><td>{% if row.has_batch %}<span class="b1311-pill b1311-ready">Đã có đợt</span>{% for batch in row.batches %}<div style="margin-top:5px"><span class="b1311-code">{{ batch.code }}</span> · {{ status_labels.get(batch.status, batch.status) }}</div>{% endfor %}{% else %}<span class="b1311-pill b1311-missing">Sẽ được tạo</span>{% endif %}</td><td>{{ row.batch_total }}</td></tr>{% endfor %}</tbody></table></div></section></div></div>\n<section class="b1311-card"><h2>3. Xóa đợt tạo nhầm — kiểm soát nghiêm ngặt</h2><div class="b1311-notice b1311-warn">Chỉ xóa đợt còn <strong>Chuẩn bị</strong>, chưa khóa và không có phiếu, phân công, nhật ký hay bất kỳ bản ghi tham chiếu nào. Ngay trước DELETE, hệ thống tạo <strong>backup SQLite + integrity_check + foreign_key_check</strong> và kiểm tra lại lần thứ hai trong giao dịch ghi.</div>{% if batch_rows %}<div class="b1311-table-wrap"><table class="b1311-table"><thead><tr><th>Đợt</th><th>Xã/phường</th><th>Trạng thái</th><th>Phiếu</th><th>Đánh giá sơ bộ</th><th>Xóa an toàn</th></tr></thead><tbody>{% for row in batch_rows %}<tr><td><strong class="b1311-code">{{ row.batch.code }}</strong><div>{{ row.batch.name }}</div></td><td>{{ row.batch.commune.name }}</td><td>{{ status_labels.get(row.batch.status, row.batch.status) }}{% if row.is_locked %}<div class="b1311-pill b1311-danger">Đã khóa</div>{% endif %}</td><td>{{ row.form_total }}</td><td>{% if row.prelim_deletable %}<span class="b1311-pill b1311-ready">Có thể kiểm tra xóa</span>{% else %}<span class="b1311-pill b1311-danger">Không đủ điều kiện</span>{% endif %}</td><td>{% if row.prelim_deletable %}<form class="b1311-delete-form" method="post" action="/dieu-tra/quan-ly-dot-toan-tinh/{{ row.batch.id }}/xoa" onsubmit="return confirm(\'Xóa đợt {{ row.batch.code }}? Hệ thống sẽ backup database trước khi xóa.\');"><label style="font-size:13px"><input type="checkbox" name="confirm_checked" value="1" required> Tôi xác nhận đợt này được tạo nhầm</label><input type="text" name="confirm_phrase" autocomplete="off" placeholder="{{ row.delete_phrase }}" required><button class="b1311-danger-button" type="submit">🗑 Xóa đợt trống</button></form>{% else %}<span style="color:#718096">Không cho xóa</span>{% endif %}</td></tr>{% endfor %}</tbody></table></div>{% else %}<div class="b1311-notice b1311-ok">Năm học này chưa có đợt điều tra nào.</div>{% endif %}</section>\n{% else %}<section class="b1311-card"><div class="b1311-notice b1311-error">Chưa có năm học đang hoạt động để quản lý.</div></section>{% endif %}\n</main></body></html>\n'
INDEX_UI = '\n                {# === BAI_13B_11_PROVINCE_BATCH_ADMIN_UI_START === #}\n                <div\n                    style="\n                        margin-bottom: 16px;\n                        padding: 14px;\n                        border: 1px solid #b9d8f2;\n                        border-radius: 10px;\n                        background: #eef7ff;\n                    "\n                >\n                    <strong>Khuyến nghị cấp tỉnh:</strong>\n                    tạo đợt cho toàn bộ xã/phường trong một lần và kiểm tra/xóa\n                    đợt tạo nhầm theo cơ chế an toàn.\n                    <div style="margin-top:10px;">\n                        <a\n                            class="button button-primary"\n                            href="/dieu-tra/quan-ly-dot-toan-tinh"\n                        >\n                            🌐 Khởi tạo toàn tỉnh / Xóa đợt an toàn\n                        </a>\n                    </div>\n                </div>\n                {# === BAI_13B_11_PROVINCE_BATCH_ADMIN_UI_END === #}\n\n'


def read_text(path: Path) -> str:
    if not path.exists():
        raise RuntimeError(f"Không tìm thấy tệp bắt buộc: {path}")
    return path.read_text(encoding="utf-8-sig")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def backup_file(path: Path, manifest: list[dict]) -> None:
    rel = path.relative_to(PROJECT)
    item = {"path": rel.as_posix(), "existed": path.exists()}
    manifest.append(item)
    if path.exists():
        target = BACKUP / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)


def restore_files(manifest: list[dict]) -> None:
    for item in reversed(manifest):
        path = PROJECT / item["path"]
        source = BACKUP / item["path"]
        if item["existed"]:
            if source.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, path)
        elif path.exists():
            path.unlink()


def clear_cache() -> None:
    if not APP.exists():
        return
    for cache in APP.rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(cache, ignore_errors=True)


def patch_main(text: str) -> str:
    import_line = (
        "from app.routers.survey_batch_admin_v13b11 "
        "import router as survey_batch_admin_v13b11_router"
    )
    include_line = "app.include_router(survey_batch_admin_v13b11_router)"

    if import_line not in text:
        anchor = "from app.routers.surveys import router as surveys_router"
        if anchor not in text:
            raise RuntimeError(
                "Không tìm thấy dòng import surveys_router trong app/main.py. "
                "Dừng an toàn để không chèn sai."
            )
        text = text.replace(
            anchor,
            anchor + "\n# === " + MARK_MAIN + "_IMPORT ===\n" + import_line,
            1,
        )

    if include_line not in text:
        anchor = "app.include_router(surveys_router)"
        if anchor not in text:
            raise RuntimeError(
                "Không tìm thấy app.include_router(surveys_router) trong app/main.py."
            )
        text = text.replace(
            anchor,
            anchor + "\n# === " + MARK_MAIN + "_INCLUDE ===\n" + include_line,
            1,
        )
    return text


def patch_index(text: str) -> str:
    if MARK_INDEX in text:
        return text
    action_pos = text.find('action="/dieu-tra/them"')
    if action_pos < 0:
        raise RuntimeError(
            "Không tìm thấy form tạo đợt hiện tại trong surveys/index.html. "
            "Dừng an toàn để giữ nguyên giao diện."
        )
    form_pos = text.rfind("<form", 0, action_pos)
    if form_pos < 0:
        raise RuntimeError("Không xác định được đầu form tạo đợt hiện tại.")
    return text[:form_pos] + INDEX_UI + text[form_pos:]


def preflight() -> None:
    required = [
        MAIN,
        INDEX,
        APP / "database.py",
        APP / "models.py",
        APP / "permissions.py",
        APP / "survey_models.py",
        APP / "routers" / "surveys.py",
        APP / "templates" / "partials" / "dropdown_menu_v1.html",
    ]
    for path in required:
        if not path.exists():
            raise RuntimeError(f"Không tìm thấy nền bắt buộc: {path}")
    if "surveys_router" not in read_text(MAIN):
        raise RuntimeError("main.py hiện tại thiếu surveys_router.")
    if "Quản lý đợt điều tra" not in read_text(INDEX):
        raise RuntimeError("surveys/index.html không đúng trang Quản lý đợt điều tra.")


def compile_python() -> None:
    for path in (MAIN, ROUTER):
        subprocess.run(
            [sys.executable, "-m", "py_compile", str(path)],
            cwd=PROJECT,
            check=True,
        )


def parse_templates() -> None:
    from jinja2 import Environment, FileSystemLoader
    env = Environment(loader=FileSystemLoader(str(APP / "templates")))
    env.get_template("surveys/index.html")
    env.get_template("surveys/province_batch_admin_v13b11.html")


def verify_source() -> None:
    main = read_text(MAIN)
    index = read_text(INDEX)
    router = read_text(ROUTER)
    template = read_text(TEMPLATE)
    checks = [
        ("main router", "survey_batch_admin_v13b11_router", main),
        ("main marker", MARK_MAIN, main),
        ("index marker", MARK_INDEX, index),
        ("index link", "/dieu-tra/quan-ly-dot-toan-tinh", index),
        ("router marker", "BAI_13B_11_PROVINCE_BATCH_ADMIN_START", router),
        ("route create", '@router.post("/khoi-tao")', router),
        ("route delete", '@router.post("/{batch_id}/xoa")', router),
        ("confirm create", "KHOI TAO TOAN TINH", router),
        ("confirm delete", "XOA DOT", router),
        ("backup before delete", "_backup_before_delete", router),
        ("scan references", "_references", router),
        ("double check delete", "BEGIN IMMEDIATE", router),
        ("template", "BÀI 13B-11", template),
    ]
    for label, marker, content in checks:
        if marker not in content:
            raise RuntimeError(f"Kiểm tra sau cài không đạt: {label} / {marker}")


def main() -> int:
    print("=" * 108)
    print("BÀI 13B-11 - KHỞI TẠO ĐỢT TOÀN TỈNH + XÓA ĐỢT TẠO NHẦM AN TOÀN")
    print("=" * 108)
    print()
    print("BỔ SUNG:")
    print(" 1. ADMIN/Sở tạo các đợt còn thiếu cho toàn bộ xã/phường đang hoạt động.")
    print(" 2. Xã/phường đã có đợt trong năm học được bỏ qua, KHÔNG tạo trùng.")
    print(" 3. Xem trước số xã đã có / còn thiếu / đợt trùng.")
    print(" 4. Xóa an toàn từng đợt tạo nhầm nếu còn Chuẩn bị và hoàn toàn trống.")
    print()
    print("AN TOÀN XÓA:")
    print(" - Chỉ ADMIN/Sở.")
    print(" - Phải nhập XOA DOT <MÃ ĐỢT>.")
    print(" - Quét mọi bảng tìm bản ghi tham chiếu tới batch; có tham chiếu là CHẶN.")
    print(" - Backup SQLite đầy đủ + integrity_check + foreign_key_check trước DELETE.")
    print(" - Kiểm tra lại trong BEGIN IMMEDIATE ngay trước DELETE.")
    print()
    print("QUAN TRỌNG:")
    print(" - BỘ CÀI NÀY KHÔNG TẠO, KHÔNG XÓA, KHÔNG SỬA DATABASE.")
    print(" - Tạo/xóa chỉ xảy ra sau cài khi anh chủ động thao tác trên giao diện.")
    print(" - Giữ nguyên form tạo riêng một xã và các chức năng cũ.")
    print()

    preflight()
    BACKUP.mkdir(parents=True, exist_ok=False)
    manifest: list[dict] = []
    for path in (MAIN, INDEX, ROUTER, TEMPLATE):
        backup_file(path, manifest)
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Backup source:", BACKUP)

    try:
        write_text(ROUTER, ROUTER_CODE)
        write_text(TEMPLATE, TEMPLATE_CODE)
        write_text(MAIN, patch_main(read_text(MAIN)))
        write_text(INDEX, patch_index(read_text(INDEX)))
        compile_python()
        parse_templates()
        verify_source()
        clear_cache()
        print()
        print("KIỂM TRA SAU CÀI:")
        print(" - main.py compile: OK")
        print(" - survey_batch_admin_v13b11.py compile: OK")
        print(" - 2 template Jinja: OK")
        print(" - Link Khởi tạo toàn tỉnh / Xóa đợt an toàn: OK")
        print(" - Cơ chế bỏ qua xã đã có đợt: OK")
        print(" - Cơ chế xóa: backup + quét tham chiếu + kiểm tra lần 2: OK")
        print(" - Database trong quá trình cài: KHÔNG THAY ĐỔI")
        print()
        print("CÀI ĐẶT BÀI 13B-11 THÀNH CÔNG")
        return 0
    except Exception:
        traceback.print_exc()
        print()
        print("CÓ LỖI - ĐANG KHÔI PHỤC SOURCE...")
        restore_files(manifest)
        clear_cache()
        print("ĐÃ KHÔI PHỤC SOURCE VỀ TRƯỚC BÀI 13B-11.")
        print("Database không bị thay đổi bởi bộ cài.")
        print("Backup source:", BACKUP)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
