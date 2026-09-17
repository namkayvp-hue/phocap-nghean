from __future__ import annotations

import re
import sqlite3
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.database import DATABASE_PATH
from app.permissions import is_admin_role, normalize_role_code
from app.services.school_merger_service import (
    list_communes,
    list_school_years,
    list_schools,
)

APP_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = APP_DIR.parent
# Dùng vùng dữ liệu có quyền ghi và được lưu bền vững trên máy chủ Docker.
BACKUP_DIR = DATABASE_PATH.parent / "backups"

templates = Jinja2Templates(directory=str(APP_DIR / "templates"))

router = APIRouter(
    prefix="/cong-cu-du-lieu/doi-ten-truong",
    tags=["Đổi tên trường"],
)

def _auth_user(request: Request) -> dict[str, Any]:
    return dict(request.scope.get("auth_user") or {})

def _admin_only(request: Request) -> bool:
    return is_admin_role(normalize_role_code(_auth_user(request).get("role_code")))


def _own_school(request: Request) -> dict[str, Any] | None:
    user = _auth_user(request)
    if normalize_role_code(user.get("role_code")) != "TRUONG":
        return None
    school_id = _safe_int(user.get("school_id"))
    if school_id is None:
        return None
    with _connect(read_only=True) as con:
        school = _school_row(con, school_id)
    if school is None or not school["is_active"]:
        return None
    return dict(school)


def _can_rename(request: Request, school_id: int | None = None) -> bool:
    if _admin_only(request):
        return True
    own_school = _own_school(request)
    return own_school is not None and (
        school_id is None or int(own_school["id"]) == school_id
    )

def _safe_int(value: Any) -> int | None:
    try:
        text = str(value or "").strip()
        return int(text) if text else None
    except (TypeError, ValueError):
        return None

def _clean(value: Any) -> str:
    return " ".join(str(value or "").strip().split())

def _norm(value: Any) -> str:
    text = _clean(value).lower()
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = text.replace("đ", "d")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())

def _connect(*, read_only: bool = False) -> sqlite3.Connection:
    if read_only:
        uri = DATABASE_PATH.resolve().as_uri() + "?mode=ro"
        con = sqlite3.connect(uri, uri=True, timeout=30)
    else:
        con = sqlite3.connect(str(DATABASE_PATH), timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    if read_only:
        con.execute("PRAGMA query_only=ON")
    return con

def _default_year_id(years: list[dict[str, Any]]) -> int | None:
    active = [x for x in years if int(x.get("is_active") or 0) == 1]
    if active:
        return int(active[0]["id"])
    return int(years[0]["id"]) if years else None

def _year_row(years: list[dict[str, Any]], year_id: int | None) -> dict[str, Any] | None:
    if year_id is None:
        return None
    return next((x for x in years if int(x["id"]) == int(year_id)), None)

def _ensure_history_table(con: sqlite3.Connection) -> None:
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS school_name_histories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            school_id INTEGER NOT NULL,
            effective_school_year_id INTEGER NOT NULL,
            old_name TEXT NOT NULL,
            new_name TEXT NOT NULL,
            changed_at TEXT NOT NULL,
            changed_by_user_id INTEGER,
            FOREIGN KEY(school_id) REFERENCES schools(id),
            FOREIGN KEY(effective_school_year_id) REFERENCES school_years(id),
            UNIQUE(school_id,effective_school_year_id)
        )
        """
    )
    con.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_school_name_histories_school
        ON school_name_histories(school_id,id)
        """
    )

def _school_row(con: sqlite3.Connection, school_id: int) -> sqlite3.Row | None:
    return con.execute(
        """
        SELECT s.id,s.code,s.name,s.commune_id,s.is_active,c.name AS commune_name
        FROM schools s
        JOIN communes c ON c.id=s.commune_id
        WHERE s.id=?
        """,
        (int(school_id),),
    ).fetchone()

def _history(limit: int = 100, school_id: int | None = None) -> list[dict[str, Any]]:
    with _connect(read_only=True) as con:
        try:
            rows = con.execute(
                """
                SELECT h.id,h.school_id,h.effective_school_year_id,
                       h.old_name,h.new_name,h.changed_at,
                       s.code AS school_code,c.name AS commune_name,
                       y.code AS school_year_code,y.name AS school_year_name
                FROM school_name_histories h
                JOIN schools s ON s.id=h.school_id
                JOIN communes c ON c.id=s.commune_id
                JOIN school_years y ON y.id=h.effective_school_year_id
                WHERE (? IS NULL OR h.school_id=?)
                ORDER BY h.id DESC
                LIMIT ?
                """,
                (school_id, school_id, int(limit)),
            ).fetchall()
        except sqlite3.Error:
            return []
        return [dict(r) for r in rows]

def _backup_database() -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    path = BACKUP_DIR / f"phocap_truoc_doi_ten_truong_{stamp}.db"
    src = sqlite3.connect(str(DATABASE_PATH))
    dst = sqlite3.connect(str(path))
    try:
        src.backup(dst)
        dst.commit()
    finally:
        dst.close()
        src.close()
    check = sqlite3.connect(str(path))
    try:
        integrity = check.execute("PRAGMA integrity_check").fetchone()[0]
        fk = check.execute("PRAGMA foreign_key_check").fetchall()
    finally:
        check.close()
    if integrity != "ok" or fk:
        raise RuntimeError("Backup database không đạt kiểm tra an toàn.")
    return path

def _restore_database(backup: Path) -> None:
    src = sqlite3.connect(str(backup))
    dst = sqlite3.connect(str(DATABASE_PATH))
    try:
        src.backup(dst)
        dst.commit()
    finally:
        dst.close()
        src.close()

def _validate_new_name(
    *,
    con: sqlite3.Connection,
    school: sqlite3.Row,
    new_name: str,
    school_year_id: int,
) -> str:
    new_name = _clean(new_name)
    if not new_name:
        raise ValueError("Tên mới không được để trống.")
    if int(school["is_active"] or 0) != 1:
        raise ValueError("Trường đã khóa/ngừng hoạt động. Không được đổi tên hiện hành.")
    if _norm(new_name) == _norm(school["name"]):
        raise ValueError("Tên mới đang giống tên cũ.")
    rows = con.execute(
        """
        SELECT id,name FROM schools
        WHERE commune_id=? AND is_active=1 AND id<>?
        """,
        (int(school["commune_id"]), int(school["id"])),
    ).fetchall()
    for row in rows:
        if _norm(row["name"]) == _norm(new_name):
            raise ValueError("Tên mới đang trùng với một trường đang hoạt động trong cùng xã/phường.")
    exists = con.execute(
        """
        SELECT 1 FROM school_name_histories
        WHERE school_id=? AND effective_school_year_id=?
        LIMIT 1
        """,
        (int(school["id"]), int(school_year_id)),
    ).fetchone()
    if exists:
        raise ValueError("Trường này đã có một lần đổi tên trong năm học đã chọn.")
    return new_name

def _page_context(
    request: Request,
    *,
    school_year_id: int | None = None,
    commune_id: int | None = None,
    school_id: int | None = None,
    new_name: str = "",
    preview: dict[str, Any] | None = None,
    error_message: str = "",
    status_message: str = "",
    backup_name: str = "",
) -> dict[str, Any]:
    school_account = normalize_role_code(_auth_user(request).get("role_code")) == "TRUONG"
    own_school = _own_school(request) if school_account else None
    if school_account:
        if own_school is None:
            raise ValueError("Tài khoản chưa gắn với trường đang hoạt động.")
        school_id = int(own_school["id"])
        commune_id = int(own_school["commune_id"])
    years = list_school_years()
    if school_year_id is None:
        school_year_id = _default_year_id(years)
    selected_year = _year_row(years, school_year_id)
    communes = [x for x in list_communes() if int(x.get("is_active") or 0) == 1]
    if school_account:
        communes = [x for x in communes if int(x["id"]) == commune_id]
    selected_commune = next(
        (x for x in communes if commune_id is not None and int(x["id"]) == int(commune_id)),
        None,
    )
    schools: list[dict[str, Any]] = []
    if school_account:
        schools = [own_school]
    elif school_year_id is not None and commune_id is not None:
        schools = list_schools(
            year_id=int(school_year_id),
            commune_id=int(commune_id),
            include_inactive=False,
        )
    selected_school = next(
        (x for x in schools if school_id is not None and int(x["id"]) == int(school_id)),
        None,
    )
    return {
        "nguoi_dung": _auth_user(request),
        "school_account": school_account,
        "school_years": years,
        "selected_school_year_id": school_year_id,
        "selected_year": selected_year,
        "communes": communes,
        "selected_commune_id": commune_id,
        "selected_commune_name": str((selected_commune or {}).get("name") or ""),
        "schools": schools,
        "selected_school_id": school_id,
        "selected_school_name": str((selected_school or {}).get("name") or ""),
        "selected_school": selected_school,
        "new_name": _clean(new_name),
        "preview": preview,
        "error_message": error_message,
        "status_message": status_message,
        "backup_name": backup_name,
        "history": _history(limit=100, school_id=school_id if school_account else None),
    }

def _render(request: Request, *, status_code: int = 200, **kwargs: Any):
    return templates.TemplateResponse(
        request=request,
        name="data_tools/school_rename.html",
        context=_page_context(request, **kwargs),
        status_code=status_code,
    )

@router.get("", response_class=HTMLResponse)
def school_rename_page(
    request: Request,
    school_year_id: str | None = Query(default=None),
    commune_id: str | None = Query(default=None),
    school_id: str | None = Query(default=None),
    status: str = Query(default=""),
    backup_name: str = Query(default=""),
):
    if not _can_rename(request):
        return RedirectResponse(url="/?status=forbidden", status_code=303)
    message = ""
    if status == "success":
        message = (
            "Đổi tên trường thành công. school_id, mã trường "
            "và toàn bộ liên kết dữ liệu được giữ nguyên."
        )
    return _render(
        request,
        school_year_id=_safe_int(school_year_id),
        commune_id=_safe_int(commune_id),
        school_id=_safe_int(school_id),
        status_message=message,
        backup_name=backup_name,
    )

@router.post("/xem-truoc", response_class=HTMLResponse)
def preview_school_rename(
    request: Request,
    school_year_id: int = Form(...),
    commune_id: int = Form(...),
    school_id: int = Form(...),
    new_name: str = Form(...),
):
    if not _can_rename(request, school_id):
        return RedirectResponse(url="/?status=forbidden", status_code=303)
    try:
        years = list_school_years()
        year = _year_row(years, int(school_year_id))
        if not year:
            raise ValueError("Không xác định được năm học.")
        if int(year.get("is_active") or 0) != 1:
            raise ValueError("Đổi tên hiện hành chỉ được thực hiện trong năm học đang hoạt động.")
        with _connect(read_only=False) as con:
            _ensure_history_table(con)
            con.commit()
            school = _school_row(con, int(school_id))
            if not school:
                raise ValueError("Không tìm thấy trường.")
            if int(school["commune_id"]) != int(commune_id):
                raise ValueError("Trường không thuộc xã/phường đã chọn.")
            clean_new_name = _validate_new_name(
                con=con,
                school=school,
                new_name=new_name,
                school_year_id=int(school_year_id),
            )
        preview = {
            "school_id": int(school_id),
            "school_code": str(school["code"] or ""),
            "commune_name": str(school["commune_name"] or ""),
            "school_year_id": int(school_year_id),
            "school_year_code": str(year.get("code") or year.get("name") or ""),
            "old_name": str(school["name"] or ""),
            "new_name": clean_new_name,
        }
        return _render(
            request,
            school_year_id=int(school_year_id),
            commune_id=int(commune_id),
            school_id=int(school_id),
            new_name=clean_new_name,
            preview=preview,
        )
    except Exception as exc:
        return _render(
            request,
            school_year_id=int(school_year_id),
            commune_id=int(commune_id),
            school_id=int(school_id),
            new_name=new_name,
            error_message=str(exc),
            status_code=400,
        )

@router.post("/thuc-hien")
def execute_school_rename(
    request: Request,
    school_year_id: int = Form(...),
    commune_id: int = Form(...),
    school_id: int = Form(...),
    new_name: str = Form(...),
):
    if not _can_rename(request, school_id):
        return RedirectResponse(url="/?status=forbidden", status_code=303)

    backup: Path | None = None
    committed = False
    try:
        years = list_school_years()
        year = _year_row(years, int(school_year_id))
        if not year:
            raise ValueError("Không xác định được năm học.")
        if int(year.get("is_active") or 0) != 1:
            raise ValueError("Chỉ được đổi tên trong năm học đang hoạt động.")

        backup = _backup_database()
        con = _connect(read_only=False)
        try:
            _ensure_history_table(con)
            con.execute("BEGIN IMMEDIATE")
            school = _school_row(con, int(school_id))
            if not school:
                raise ValueError("Không tìm thấy trường.")
            if int(school["commune_id"]) != int(commune_id):
                raise ValueError("Trường không thuộc xã/phường đã chọn.")
            clean_new_name = _validate_new_name(
                con=con,
                school=school,
                new_name=new_name,
                school_year_id=int(school_year_id),
            )
            actor = _auth_user(request)
            con.execute(
                """
                INSERT INTO school_name_histories (
                    school_id,effective_school_year_id,
                    old_name,new_name,changed_at,changed_by_user_id
                )
                VALUES (?,?,?,?,?,?)
                """,
                (
                    int(school_id),
                    int(school_year_id),
                    str(school["name"] or ""),
                    clean_new_name,
                    datetime.now().isoformat(sep=" ", timespec="seconds"),
                    _safe_int(actor.get("id")),
                ),
            )
            cur = con.execute(
                "UPDATE schools SET name=? WHERE id=? AND is_active=1",
                (clean_new_name, int(school_id)),
            )
            if cur.rowcount != 1:
                raise RuntimeError("Không cập nhật được đúng 1 trường.")
            integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
            fk = con.execute("PRAGMA foreign_key_check").fetchall()
            if integrity != "ok":
                raise RuntimeError(f"integrity_check={integrity}")
            if fk:
                raise RuntimeError(f"foreign_key_check={len(fk)} lỗi")
            con.commit()
            committed = True
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

        check = _connect(read_only=True)
        try:
            row = _school_row(check, int(school_id))
            integrity = check.execute("PRAGMA integrity_check").fetchone()[0]
            fk = check.execute("PRAGMA foreign_key_check").fetchall()
        finally:
            check.close()

        if not row or _norm(row["name"]) != _norm(clean_new_name):
            raise RuntimeError("Hậu kiểm tên trường sau COMMIT không đạt.")
        if integrity != "ok" or fk:
            raise RuntimeError("Hậu kiểm database sau COMMIT không đạt.")

        url = (
            "/cong-cu-du-lieu/doi-ten-truong"
            f"?school_year_id={int(school_year_id)}"
            f"&commune_id={int(commune_id)}"
            f"&school_id={int(school_id)}"
            "&status=success"
            f"&backup_name={backup.name if backup else ''}"
        )
        return RedirectResponse(url=url, status_code=303)

    except Exception as exc:
        if committed and backup is not None and backup.exists():
            try:
                _restore_database(backup)
            except Exception as restore_exc:
                return _render(
                    request,
                    school_year_id=int(school_year_id),
                    commune_id=int(commune_id),
                    school_id=int(school_id),
                    new_name=new_name,
                    error_message=f"{exc}. CẢNH BÁO: khôi phục backup lỗi: {restore_exc}",
                    status_code=500,
                )
        return _render(
            request,
            school_year_id=int(school_year_id),
            commune_id=int(commune_id),
            school_id=int(school_id),
            new_name=new_name,
            error_message=str(exc),
            status_code=400,
        )
