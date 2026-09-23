from datetime import datetime
from pathlib import Path
from io import BytesIO
import json
import re
import sqlite3
from uuid import uuid4

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

from app.database import DATABASE_PATH
from app.permissions import normalize_role_code, ADMIN_ROLE_CODES
from app.services.survey_archive_service import (
    MAX_ARCHIVE, build_archive, read_archive, restore_plan, insert_missing,
)

router = APIRouter(prefix="/dieu-tra/luu-tru", tags=["Lưu trữ điều tra"])
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))


def user_scope(request):
    user = dict(request.scope.get("auth_user") or {})
    role = normalize_role_code(user.get("role_code"))
    if role in ADMIN_ROLE_CODES:
        return user, None
    if role == "XA" and user.get("commune_id"):
        return user, [int(user["commune_id"])]
    return None


def connect(write=False):
    con = sqlite3.connect(str(DATABASE_PATH) if write else Path(DATABASE_PATH).resolve().as_uri()+"?mode=ro", uri=not write, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    return con


def render(request, *, error="", result=None, preview=None, token="", status_code=200):
    scope = user_scope(request)
    if scope is None:
        return RedirectResponse("/?status=forbidden", 303)
    user, permitted = scope
    con = connect()
    try:
        years = [dict(r) for r in con.execute("SELECT id,code FROM school_years ORDER BY code DESC")]
        communes = [dict(r) for r in con.execute("SELECT id,code,name FROM communes ORDER BY name")
                    if permitted is None or r["id"] in permitted]
    finally:
        con.close()
    return templates.TemplateResponse(request=request, name="surveys/archive.html", status_code=status_code,
        context=dict(nguoi_dung=user, years=years, communes=communes, commune_account=permitted is not None,
                     error=error, result=result, preview=preview, token=token))


@router.get("")
def page(request: Request):
    return render(request)


@router.post("/xuat")
async def export(request: Request):
    scope = user_scope(request)
    if scope is None:
        return RedirectResponse("/?status=forbidden", 303)
    user, permitted = scope
    form = await request.form()
    con = connect()
    try:
        year = int(form.get("school_year_id") or 0)
        selected = sorted({int(v) for v in form.getlist("commune_ids")})
        if not selected or (permitted is not None and not set(selected) <= set(permitted)):
            raise ValueError("Hãy chọn xã trong phạm vi được phân quyền.")
        if con.execute("SELECT 1 FROM school_years WHERE id=?", (year,)).fetchone() is None:
            raise ValueError("Năm học không hợp lệ.")
        # Hold one read snapshot across all tables for a consistent archive.
        con.execute("BEGIN")
        content, manifest = build_archive(con, year, selected,
            {"id": user.get("id"), "name": user.get("full_name"), "role": user.get("role_code")})
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return StreamingResponse(BytesIO(content), media_type="application/zip", headers={
            "Content-Disposition": f'attachment; filename="luu_tru_dieu_tra_{year}_{stamp}.zip"',
            "Cache-Control": "no-store"})
    except ValueError as exc:
        return render(request, error=str(exc), status_code=400)
    finally:
        con.close()


def stage_dir():
    folder = Path(DATABASE_PATH).parent / "survey_archive_staging"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def preview_context(manifest, plan, data):
    return dict(year=manifest["school_year_id"], communes=manifest["commune_ids"],
                year_name=data.get("school_years", {}).get(manifest["school_year_id"], {}).get("code", ""),
                commune_names=[data.get("communes", {}).get(i, {}).get("name", str(i)) for i in manifest["commune_ids"]],
                households=len(data.get("households", {})), people=len(data.get("survey_people", {})),
                forms=len(data.get("survey_forms", {})), records=len(data.get("survey_person_year_records", {})),
                created_at=manifest["created_at"], tables=manifest["tables"],
                new=plan["total_new"], same=plan["same"], conflicts=plan["conflicts"][:100],
                conflict_count=len(plan["conflicts"]))


@router.post("/xem-truoc")
def preview_import(request: Request, file: UploadFile = File(...)):
    scope = user_scope(request)
    if scope is None:
        file.file.close()
        return RedirectResponse("/?status=forbidden", 303)
    user, permitted = scope
    con = connect()
    try:
        content = file.file.read(MAX_ARCHIVE+1)
        manifest, data = read_archive(content)
        plan = restore_plan(con, manifest, data, permitted)
        token = ""
        if not plan["conflicts"] and plan["total_new"]:
            token = uuid4().hex
            folder = stage_dir()
            (folder / (token+".zip")).write_bytes(content)
            (folder / (token+".json")).write_text(json.dumps({"user_id": user.get("id"), "created_at": datetime.now().timestamp()}), encoding="utf-8")
        return render(request, preview=preview_context(manifest, plan, data), token=token)
    except ValueError as exc:
        return render(request, error=str(exc), status_code=400)
    finally:
        file.file.close()
        con.close()


@router.post("/nhap")
def restore(request: Request, token: str = Form(...)):
    scope = user_scope(request)
    if scope is None:
        return RedirectResponse("/?status=forbidden", 303)
    user, permitted = scope
    if not re.fullmatch(r"[0-9a-f]{32}", token):
        return render(request, error="Phiên nhập không hợp lệ.", status_code=400)
    folder = stage_dir()
    con = None
    try:
        info = json.loads((folder/(token+".json")).read_text(encoding="utf-8"))
        if info["user_id"] != user.get("id") or datetime.now().timestamp()-info["created_at"] > 3600:
            raise ValueError("Phiên nhập đã hết hạn hoặc thuộc tài khoản khác. Hãy tải file lên lại.")
        manifest, data = read_archive((folder/(token+".zip")).read_bytes())
        con = connect(write=True)
        con.execute("BEGIN IMMEDIATE")
        plan = restore_plan(con, manifest, data, permitted)
        count = insert_missing(con, plan)
        if con.execute("PRAGMA foreign_key_check").fetchone():
            raise ValueError("Liên kết dữ liệu không hợp lệ. Chưa lưu dữ liệu nhập.")
        con.commit()
        (folder/(token+".zip")).unlink(missing_ok=True)
        (folder/(token+".json")).unlink(missing_ok=True)
        return render(request, result=f"Đã khôi phục {count} bản ghi còn thiếu; giữ nguyên {plan['same']} bản ghi đã có.")
    except (ValueError, OSError, sqlite3.Error) as exc:
        if con:
            con.rollback()
        error = str(exc) if isinstance(exc, ValueError) else "Không thể khôi phục gói này: phiên nhập không còn hoặc dữ liệu có xung đột. Chưa lưu thay đổi. Hãy xem trước lại."
        return render(request, error=error, status_code=400)
    finally:
        if con:
            con.close()
