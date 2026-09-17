# -*- coding: utf-8 -*-
r"""
V13.1 - CÀI CHỨC NĂNG ĐỔI TÊN TRƯỜNG
=====================================
- Menu 1.3.3 Đổi tên trường.
- Chỉ Tên cũ -> Tên mới.
- Không có số/ký hiệu văn bản, ngày văn bản, lý do/ghi chú.
- school_id và mã trường giữ nguyên.
- Lưu lịch sử tên trường theo năm học.
- Backup source + database, rollback nếu cài lỗi.
"""

from __future__ import annotations

import ast
import py_compile
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

ROOT = Path(r"C:\PhoCap")
DB_PATH = ROOT / "data" / "phocap.db"
BACKUPS = ROOT / "backups"
EXPORTS = ROOT / "exports"
MAIN = ROOT / "app" / "main.py"
MENU = ROOT / "app" / "templates" / "partials" / "dropdown_menu_v1.html"
MERGER_TEMPLATE = ROOT / "app" / "templates" / "data_tools" / "school_merger.html"
ROUTER = ROOT / "app" / "routers" / "school_rename.py"
TEMPLATE = ROOT / "app" / "templates" / "data_tools" / "school_rename.html"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
SOURCE_BACKUP = EXPORTS / f"backup_v13_1_doi_ten_truong_{STAMP}"
DB_BACKUP = BACKUPS / f"phocap_truoc_cai_v13_1_doi_ten_truong_{STAMP}.db"
REPORT = EXPORTS / f"bao_cao_cai_v13_1_doi_ten_truong_{STAMP}.txt"

IMPORT_MARK = "# === V13_1_SCHOOL_RENAME_IMPORT ==="
INCLUDE_MARK = "# === V13_1_SCHOOL_RENAME_INCLUDE ==="
MENU_MARK = "{# === V13_1_SCHOOL_RENAME_MENU === #}"
MERGER_BUTTON_MARK = "{# === V13_1_SCHOOL_RENAME_BUTTON === #}"

ROUTER_CONTENT = 'from __future__ import annotations\n\nimport re\nimport sqlite3\nimport unicodedata\nfrom datetime import datetime\nfrom pathlib import Path\nfrom typing import Any\n\nfrom fastapi import APIRouter, Form, Query, Request\nfrom fastapi.responses import HTMLResponse, RedirectResponse\nfrom fastapi.templating import Jinja2Templates\n\nfrom app.database import DATABASE_PATH\nfrom app.permissions import is_admin_role, normalize_role_code\nfrom app.services.school_merger_service import (\n    list_communes,\n    list_school_years,\n    list_schools,\n)\n\nAPP_DIR = Path(__file__).resolve().parent.parent\nPROJECT_DIR = APP_DIR.parent\nBACKUP_DIR = PROJECT_DIR / "backups"\n\ntemplates = Jinja2Templates(directory=str(APP_DIR / "templates"))\n\nrouter = APIRouter(\n    prefix="/cong-cu-du-lieu/doi-ten-truong",\n    tags=["Đổi tên trường"],\n)\n\ndef _auth_user(request: Request) -> dict[str, Any]:\n    return dict(request.scope.get("auth_user") or {})\n\ndef _admin_only(request: Request) -> bool:\n    return is_admin_role(normalize_role_code(_auth_user(request).get("role_code")))\n\ndef _safe_int(value: Any) -> int | None:\n    try:\n        text = str(value or "").strip()\n        return int(text) if text else None\n    except (TypeError, ValueError):\n        return None\n\ndef _clean(value: Any) -> str:\n    return " ".join(str(value or "").strip().split())\n\ndef _norm(value: Any) -> str:\n    text = _clean(value).lower()\n    text = unicodedata.normalize("NFD", text)\n    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")\n    text = text.replace("đ", "d")\n    text = re.sub(r"[^a-z0-9]+", " ", text)\n    return " ".join(text.split())\n\ndef _connect(*, read_only: bool = False) -> sqlite3.Connection:\n    if read_only:\n        uri = DATABASE_PATH.resolve().as_uri() + "?mode=ro"\n        con = sqlite3.connect(uri, uri=True, timeout=30)\n    else:\n        con = sqlite3.connect(str(DATABASE_PATH), timeout=30)\n    con.row_factory = sqlite3.Row\n    con.execute("PRAGMA foreign_keys=ON")\n    if read_only:\n        con.execute("PRAGMA query_only=ON")\n    return con\n\ndef _default_year_id(years: list[dict[str, Any]]) -> int | None:\n    active = [x for x in years if int(x.get("is_active") or 0) == 1]\n    if active:\n        return int(active[0]["id"])\n    return int(years[0]["id"]) if years else None\n\ndef _year_row(years: list[dict[str, Any]], year_id: int | None) -> dict[str, Any] | None:\n    if year_id is None:\n        return None\n    return next((x for x in years if int(x["id"]) == int(year_id)), None)\n\ndef _ensure_history_table(con: sqlite3.Connection) -> None:\n    con.execute(\n        """\n        CREATE TABLE IF NOT EXISTS school_name_histories (\n            id INTEGER PRIMARY KEY AUTOINCREMENT,\n            school_id INTEGER NOT NULL,\n            effective_school_year_id INTEGER NOT NULL,\n            old_name TEXT NOT NULL,\n            new_name TEXT NOT NULL,\n            changed_at TEXT NOT NULL,\n            changed_by_user_id INTEGER,\n            FOREIGN KEY(school_id) REFERENCES schools(id),\n            FOREIGN KEY(effective_school_year_id) REFERENCES school_years(id),\n            UNIQUE(school_id,effective_school_year_id)\n        )\n        """\n    )\n    con.execute(\n        """\n        CREATE INDEX IF NOT EXISTS ix_school_name_histories_school\n        ON school_name_histories(school_id,id)\n        """\n    )\n\ndef _school_row(con: sqlite3.Connection, school_id: int) -> sqlite3.Row | None:\n    return con.execute(\n        """\n        SELECT s.id,s.code,s.name,s.commune_id,s.is_active,c.name AS commune_name\n        FROM schools s\n        JOIN communes c ON c.id=s.commune_id\n        WHERE s.id=?\n        """,\n        (int(school_id),),\n    ).fetchone()\n\ndef _history(limit: int = 100) -> list[dict[str, Any]]:\n    with _connect(read_only=True) as con:\n        try:\n            rows = con.execute(\n                """\n                SELECT h.id,h.school_id,h.effective_school_year_id,\n                       h.old_name,h.new_name,h.changed_at,\n                       s.code AS school_code,c.name AS commune_name,\n                       y.code AS school_year_code,y.name AS school_year_name\n                FROM school_name_histories h\n                JOIN schools s ON s.id=h.school_id\n                JOIN communes c ON c.id=s.commune_id\n                JOIN school_years y ON y.id=h.effective_school_year_id\n                ORDER BY h.id DESC\n                LIMIT ?\n                """,\n                (int(limit),),\n            ).fetchall()\n        except sqlite3.Error:\n            return []\n        return [dict(r) for r in rows]\n\ndef _backup_database() -> Path:\n    BACKUP_DIR.mkdir(parents=True, exist_ok=True)\n    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")\n    path = BACKUP_DIR / f"phocap_truoc_doi_ten_truong_{stamp}.db"\n    src = sqlite3.connect(str(DATABASE_PATH))\n    dst = sqlite3.connect(str(path))\n    try:\n        src.backup(dst)\n        dst.commit()\n    finally:\n        dst.close()\n        src.close()\n    check = sqlite3.connect(str(path))\n    try:\n        integrity = check.execute("PRAGMA integrity_check").fetchone()[0]\n        fk = check.execute("PRAGMA foreign_key_check").fetchall()\n    finally:\n        check.close()\n    if integrity != "ok" or fk:\n        raise RuntimeError("Backup database không đạt kiểm tra an toàn.")\n    return path\n\ndef _restore_database(backup: Path) -> None:\n    src = sqlite3.connect(str(backup))\n    dst = sqlite3.connect(str(DATABASE_PATH))\n    try:\n        src.backup(dst)\n        dst.commit()\n    finally:\n        dst.close()\n        src.close()\n\ndef _validate_new_name(\n    *,\n    con: sqlite3.Connection,\n    school: sqlite3.Row,\n    new_name: str,\n    school_year_id: int,\n) -> str:\n    new_name = _clean(new_name)\n    if not new_name:\n        raise ValueError("Tên mới không được để trống.")\n    if int(school["is_active"] or 0) != 1:\n        raise ValueError("Trường đã khóa/ngừng hoạt động. Không được đổi tên hiện hành.")\n    if _norm(new_name) == _norm(school["name"]):\n        raise ValueError("Tên mới đang giống tên cũ.")\n    rows = con.execute(\n        """\n        SELECT id,name FROM schools\n        WHERE commune_id=? AND is_active=1 AND id<>?\n        """,\n        (int(school["commune_id"]), int(school["id"])),\n    ).fetchall()\n    for row in rows:\n        if _norm(row["name"]) == _norm(new_name):\n            raise ValueError("Tên mới đang trùng với một trường đang hoạt động trong cùng xã/phường.")\n    exists = con.execute(\n        """\n        SELECT 1 FROM school_name_histories\n        WHERE school_id=? AND effective_school_year_id=?\n        LIMIT 1\n        """,\n        (int(school["id"]), int(school_year_id)),\n    ).fetchone()\n    if exists:\n        raise ValueError("Trường này đã có một lần đổi tên trong năm học đã chọn.")\n    return new_name\n\ndef _page_context(\n    request: Request,\n    *,\n    school_year_id: int | None = None,\n    commune_id: int | None = None,\n    school_id: int | None = None,\n    new_name: str = "",\n    preview: dict[str, Any] | None = None,\n    error_message: str = "",\n    status_message: str = "",\n    backup_name: str = "",\n) -> dict[str, Any]:\n    years = list_school_years()\n    if school_year_id is None:\n        school_year_id = _default_year_id(years)\n    selected_year = _year_row(years, school_year_id)\n    communes = [x for x in list_communes() if int(x.get("is_active") or 0) == 1]\n    selected_commune = next(\n        (x for x in communes if commune_id is not None and int(x["id"]) == int(commune_id)),\n        None,\n    )\n    schools: list[dict[str, Any]] = []\n    if school_year_id is not None and commune_id is not None:\n        schools = list_schools(\n            year_id=int(school_year_id),\n            commune_id=int(commune_id),\n            include_inactive=False,\n        )\n    selected_school = next(\n        (x for x in schools if school_id is not None and int(x["id"]) == int(school_id)),\n        None,\n    )\n    return {\n        "nguoi_dung": _auth_user(request),\n        "school_years": years,\n        "selected_school_year_id": school_year_id,\n        "selected_year": selected_year,\n        "communes": communes,\n        "selected_commune_id": commune_id,\n        "selected_commune_name": str((selected_commune or {}).get("name") or ""),\n        "schools": schools,\n        "selected_school_id": school_id,\n        "selected_school_name": str((selected_school or {}).get("name") or ""),\n        "selected_school": selected_school,\n        "new_name": _clean(new_name),\n        "preview": preview,\n        "error_message": error_message,\n        "status_message": status_message,\n        "backup_name": backup_name,\n        "history": _history(limit=100),\n    }\n\ndef _render(request: Request, *, status_code: int = 200, **kwargs: Any):\n    return templates.TemplateResponse(\n        request=request,\n        name="data_tools/school_rename.html",\n        context=_page_context(request, **kwargs),\n        status_code=status_code,\n    )\n\n@router.get("", response_class=HTMLResponse)\ndef school_rename_page(\n    request: Request,\n    school_year_id: str | None = Query(default=None),\n    commune_id: str | None = Query(default=None),\n    school_id: str | None = Query(default=None),\n    status: str = Query(default=""),\n    backup_name: str = Query(default=""),\n):\n    if not _admin_only(request):\n        return RedirectResponse(url="/?status=forbidden", status_code=303)\n    message = ""\n    if status == "success":\n        message = (\n            "Đổi tên trường thành công. school_id, mã trường "\n            "và toàn bộ liên kết dữ liệu được giữ nguyên."\n        )\n    return _render(\n        request,\n        school_year_id=_safe_int(school_year_id),\n        commune_id=_safe_int(commune_id),\n        school_id=_safe_int(school_id),\n        status_message=message,\n        backup_name=backup_name,\n    )\n\n@router.post("/xem-truoc", response_class=HTMLResponse)\ndef preview_school_rename(\n    request: Request,\n    school_year_id: int = Form(...),\n    commune_id: int = Form(...),\n    school_id: int = Form(...),\n    new_name: str = Form(...),\n):\n    if not _admin_only(request):\n        return RedirectResponse(url="/?status=forbidden", status_code=303)\n    try:\n        years = list_school_years()\n        year = _year_row(years, int(school_year_id))\n        if not year:\n            raise ValueError("Không xác định được năm học.")\n        if int(year.get("is_active") or 0) != 1:\n            raise ValueError("Đổi tên hiện hành chỉ được thực hiện trong năm học đang hoạt động.")\n        with _connect(read_only=False) as con:\n            _ensure_history_table(con)\n            con.commit()\n            school = _school_row(con, int(school_id))\n            if not school:\n                raise ValueError("Không tìm thấy trường.")\n            if int(school["commune_id"]) != int(commune_id):\n                raise ValueError("Trường không thuộc xã/phường đã chọn.")\n            clean_new_name = _validate_new_name(\n                con=con,\n                school=school,\n                new_name=new_name,\n                school_year_id=int(school_year_id),\n            )\n        preview = {\n            "school_id": int(school_id),\n            "school_code": str(school["code"] or ""),\n            "commune_name": str(school["commune_name"] or ""),\n            "school_year_id": int(school_year_id),\n            "school_year_code": str(year.get("code") or year.get("name") or ""),\n            "old_name": str(school["name"] or ""),\n            "new_name": clean_new_name,\n        }\n        return _render(\n            request,\n            school_year_id=int(school_year_id),\n            commune_id=int(commune_id),\n            school_id=int(school_id),\n            new_name=clean_new_name,\n            preview=preview,\n        )\n    except Exception as exc:\n        return _render(\n            request,\n            school_year_id=int(school_year_id),\n            commune_id=int(commune_id),\n            school_id=int(school_id),\n            new_name=new_name,\n            error_message=str(exc),\n            status_code=400,\n        )\n\n@router.post("/thuc-hien")\ndef execute_school_rename(\n    request: Request,\n    school_year_id: int = Form(...),\n    commune_id: int = Form(...),\n    school_id: int = Form(...),\n    new_name: str = Form(...),\n):\n    if not _admin_only(request):\n        return RedirectResponse(url="/?status=forbidden", status_code=303)\n\n    backup: Path | None = None\n    committed = False\n    try:\n        years = list_school_years()\n        year = _year_row(years, int(school_year_id))\n        if not year:\n            raise ValueError("Không xác định được năm học.")\n        if int(year.get("is_active") or 0) != 1:\n            raise ValueError("Chỉ được đổi tên trong năm học đang hoạt động.")\n\n        backup = _backup_database()\n        con = _connect(read_only=False)\n        try:\n            _ensure_history_table(con)\n            con.execute("BEGIN IMMEDIATE")\n            school = _school_row(con, int(school_id))\n            if not school:\n                raise ValueError("Không tìm thấy trường.")\n            if int(school["commune_id"]) != int(commune_id):\n                raise ValueError("Trường không thuộc xã/phường đã chọn.")\n            clean_new_name = _validate_new_name(\n                con=con,\n                school=school,\n                new_name=new_name,\n                school_year_id=int(school_year_id),\n            )\n            actor = _auth_user(request)\n            con.execute(\n                """\n                INSERT INTO school_name_histories (\n                    school_id,effective_school_year_id,\n                    old_name,new_name,changed_at,changed_by_user_id\n                )\n                VALUES (?,?,?,?,?,?)\n                """,\n                (\n                    int(school_id),\n                    int(school_year_id),\n                    str(school["name"] or ""),\n                    clean_new_name,\n                    datetime.now().isoformat(sep=" ", timespec="seconds"),\n                    _safe_int(actor.get("id")),\n                ),\n            )\n            cur = con.execute(\n                "UPDATE schools SET name=? WHERE id=? AND is_active=1",\n                (clean_new_name, int(school_id)),\n            )\n            if cur.rowcount != 1:\n                raise RuntimeError("Không cập nhật được đúng 1 trường.")\n            integrity = con.execute("PRAGMA integrity_check").fetchone()[0]\n            fk = con.execute("PRAGMA foreign_key_check").fetchall()\n            if integrity != "ok":\n                raise RuntimeError(f"integrity_check={integrity}")\n            if fk:\n                raise RuntimeError(f"foreign_key_check={len(fk)} lỗi")\n            con.commit()\n            committed = True\n        except Exception:\n            con.rollback()\n            raise\n        finally:\n            con.close()\n\n        check = _connect(read_only=True)\n        try:\n            row = _school_row(check, int(school_id))\n            integrity = check.execute("PRAGMA integrity_check").fetchone()[0]\n            fk = check.execute("PRAGMA foreign_key_check").fetchall()\n        finally:\n            check.close()\n\n        if not row or _norm(row["name"]) != _norm(clean_new_name):\n            raise RuntimeError("Hậu kiểm tên trường sau COMMIT không đạt.")\n        if integrity != "ok" or fk:\n            raise RuntimeError("Hậu kiểm database sau COMMIT không đạt.")\n\n        url = (\n            "/cong-cu-du-lieu/doi-ten-truong"\n            f"?school_year_id={int(school_year_id)}"\n            f"&commune_id={int(commune_id)}"\n            f"&school_id={int(school_id)}"\n            "&status=success"\n            f"&backup_name={backup.name if backup else \'\'}"\n        )\n        return RedirectResponse(url=url, status_code=303)\n\n    except Exception as exc:\n        if committed and backup is not None and backup.exists():\n            try:\n                _restore_database(backup)\n            except Exception as restore_exc:\n                return _render(\n                    request,\n                    school_year_id=int(school_year_id),\n                    commune_id=int(commune_id),\n                    school_id=int(school_id),\n                    new_name=new_name,\n                    error_message=f"{exc}. CẢNH BÁO: khôi phục backup lỗi: {restore_exc}",\n                    status_code=500,\n                )\n        return _render(\n            request,\n            school_year_id=int(school_year_id),\n            commune_id=int(commune_id),\n            school_id=int(school_id),\n            new_name=new_name,\n            error_message=str(exc),\n            status_code=400,\n        )\n'
TEMPLATE_CONTENT = '<!DOCTYPE html>\n<html lang="vi">\n<head>\n    <meta charset="UTF-8">\n    <meta name="viewport" content="width=device-width, initial-scale=1.0">\n    <title>Đổi tên trường</title>\n    <link rel="stylesheet" href="{{ url_for(\'static\', path=\'/css/style.css\') }}">\n    <style>\n        .rename-wrap{max-width:1450px;margin:0 auto;padding:24px 18px 60px}\n        .rename-hero,.rename-panel{background:#fff;border:1px solid #dbe3ec;border-radius:14px;padding:20px;margin-bottom:18px}\n        .rename-hero h1{margin:0 0 8px;font-size:26px}\n        .rename-hero p{margin:6px 0;color:#52606d;line-height:1.55}\n        .rename-grid{display:grid;grid-template-columns:repeat(3,minmax(220px,1fr));gap:14px}\n        .rename-grid.two{grid-template-columns:1fr 1fr}\n        .field label{display:block;font-weight:700;margin-bottom:6px}\n        .field input,.field select{width:100%;box-sizing:border-box;padding:10px;border:1px solid #c9d4df;border-radius:8px;background:#fff}\n        .field input[readonly]{background:#f4f7fa;color:#52606d}\n        .actions{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-top:16px}\n        .btn{display:inline-flex;align-items:center;justify-content:center;border:0;border-radius:8px;padding:10px 16px;font-weight:700;text-decoration:none;cursor:pointer}\n        .btn.primary{background:#1f5f99;color:#fff}.btn.success{background:#18794e;color:#fff}.btn.muted{background:#e8eef4;color:#213547}\n        .note{padding:12px 14px;border-radius:9px;margin:10px 0;line-height:1.5}\n        .note.info{background:#eef6ff;border:1px solid #b9d8fa;color:#164e7a}.note.ok{background:#edf9f2;border:1px solid #a8dfbd;color:#155f3a}.note.error{background:#fff0ef;border:1px solid #f0b4ae;color:#842029}\n        .preview{border:2px solid #a8dfbd;background:#f7fcf9;border-radius:12px;padding:18px}\n        .arrow{font-size:24px;font-weight:800;text-align:center;align-self:center}\n        .table-wrap{overflow:auto;border:1px solid #e0e6ec;border-radius:10px}\n        table{width:100%;border-collapse:collapse;min-width:800px}th,td{padding:10px;border-bottom:1px solid #e7ecf1;text-align:left}th{background:#f7f9fb}\n        .muted{color:#667788;font-size:13px}\n        .combo{position:relative}.combo-list{display:none;position:absolute;z-index:50;left:0;right:0;top:100%;max-height:280px;overflow:auto;background:#fff;border:1px solid #c9d4df;border-radius:8px;box-shadow:0 8px 22px rgba(20,40,60,.16);margin-top:4px}\n        .combo-list.open{display:block}.combo-item{padding:9px 10px;cursor:pointer;border-bottom:1px solid #eef2f6}.combo-item:hover{background:#eef6ff}.combo-empty{padding:10px;color:#667788}\n        @media(max-width:900px){.rename-grid,.rename-grid.two{grid-template-columns:1fr}.rename-wrap{padding:14px 10px 40px}}\n    </style>\n</head>\n<body>\n{% include "partials/dropdown_menu_v1.html" %}\n<main class="rename-wrap">\n    <section class="rename-hero">\n        <h1>Đổi tên trường</h1>\n        <p>Chức năng chỉ thay <strong>tên hiện hành</strong> của trường. <strong>school_id, mã trường và toàn bộ dữ liệu liên kết được giữ nguyên.</strong></p>\n        <p>Phần đổi tên chỉ gồm <strong>Tên cũ → Tên mới</strong>. Không yêu cầu số văn bản, ngày văn bản hoặc ghi chú.</p>\n        <div class="actions"><a class="btn muted" href="/cong-cu-du-lieu/sap-nhap-truong">← Sáp nhập trường</a></div>\n    </section>\n\n    {% if error_message %}<div class="note error"><strong>Không thực hiện:</strong> {{ error_message }}</div>{% endif %}\n    {% if status_message %}\n    <div class="note ok"><strong>{{ status_message }}</strong>{% if backup_name %}<br>Backup an toàn: <code>{{ backup_name }}</code>{% endif %}</div>\n    {% endif %}\n\n    <section class="rename-panel">\n        <h2>1. Chọn trường</h2>\n        <form id="select-form" method="get" action="/cong-cu-du-lieu/doi-ten-truong">\n            <div class="rename-grid">\n                <div class="field">\n                    <label>Năm học</label>\n                    <select name="school_year_id" required>\n                        {% for y in school_years %}\n                        <option value="{{ y.id }}" {% if y.id == selected_school_year_id %}selected{% endif %}>\n                            {{ y.code or y.name }}{% if y.is_active %} · đang hoạt động{% endif %}\n                        </option>\n                        {% endfor %}\n                    </select>\n                    <div class="muted">Chỉ năm học đang hoạt động mới được thực hiện đổi tên.</div>\n                </div>\n\n                <div class="field">\n                    <label>Xã/phường</label>\n                    <div class="combo">\n                        <input id="commune-search" type="text" value="{{ selected_commune_name }}" placeholder="Gõ từ đầu tên xã/phường..." autocomplete="off">\n                        <input id="commune-id" name="commune_id" type="hidden" value="{{ selected_commune_id or \'\' }}">\n                        <div id="commune-list" class="combo-list"></div>\n                    </div>\n                </div>\n\n                <div class="field">\n                    <label>Trường</label>\n                    <div class="combo">\n                        <input id="school-search" type="text" value="{{ selected_school_name }}" placeholder="Gõ từ đầu tên trường..." autocomplete="off">\n                        <input id="school-id" name="school_id" type="hidden" value="{{ selected_school_id or \'\' }}">\n                        <div id="school-list" class="combo-list"></div>\n                    </div>\n                    <div class="muted">Chỉ hiển thị trường đang hoạt động trong xã/phường đã chọn.</div>\n                </div>\n            </div>\n            <div class="actions"><button class="btn primary" type="submit">Hiển thị trường</button></div>\n        </form>\n    </section>\n\n    {% if selected_school %}\n    <section class="rename-panel">\n        <h2>2. Tên cũ → Tên mới</h2>\n        <form method="post" action="/cong-cu-du-lieu/doi-ten-truong/xem-truoc">\n            <input type="hidden" name="school_year_id" value="{{ selected_school_year_id }}">\n            <input type="hidden" name="commune_id" value="{{ selected_commune_id }}">\n            <input type="hidden" name="school_id" value="{{ selected_school_id }}">\n            <div class="rename-grid two">\n                <div class="field"><label>Tên cũ</label><input type="text" value="{{ selected_school.name }}" readonly></div>\n                <div class="field"><label>Tên mới</label><input type="text" name="new_name" value="{{ new_name }}" placeholder="Nhập tên mới của trường" required></div>\n            </div>\n            <div class="actions"><button class="btn primary" type="submit">Xem trước</button></div>\n        </form>\n    </section>\n    {% endif %}\n\n    {% if preview %}\n    <section class="rename-panel">\n        <h2>3. Xem trước</h2>\n        <div class="preview">\n            <div class="rename-grid">\n                <div><strong>Năm hiệu lực</strong><div>{{ preview.school_year_code }}</div></div>\n                <div><strong>Xã/phường</strong><div>{{ preview.commune_name }}</div></div>\n                <div><strong>Mã trường</strong><div>{{ preview.school_code or "—" }}</div></div>\n            </div>\n            <div class="rename-grid" style="margin-top:18px">\n                <div class="field"><label>Tên cũ</label><input type="text" value="{{ preview.old_name }}" readonly></div>\n                <div class="arrow">→</div>\n                <div class="field"><label>Tên mới</label><input type="text" value="{{ preview.new_name }}" readonly></div>\n            </div>\n            <div class="note info">Không đổi school_id. Không đổi mã trường. Không chuyển lại tài khoản, đội ngũ, lớp, học sinh hoặc dữ liệu điều tra.</div>\n            <form method="post" action="/cong-cu-du-lieu/doi-ten-truong/thuc-hien">\n                <input type="hidden" name="school_year_id" value="{{ preview.school_year_id }}">\n                <input type="hidden" name="commune_id" value="{{ selected_commune_id }}">\n                <input type="hidden" name="school_id" value="{{ preview.school_id }}">\n                <input type="hidden" name="new_name" value="{{ preview.new_name }}">\n                <div class="actions"><button class="btn success" type="submit">Thực hiện đổi tên</button></div>\n            </form>\n        </div>\n    </section>\n    {% endif %}\n\n    <section class="rename-panel">\n        <h2>Lịch sử đổi tên trường</h2>\n        {% if history %}\n        <div class="table-wrap">\n            <table>\n                <thead><tr><th>Năm hiệu lực</th><th>Xã/phường</th><th>Mã trường</th><th>Tên cũ</th><th>Tên mới</th></tr></thead>\n                <tbody>\n                    {% for item in history %}\n                    <tr>\n                        <td>{{ item.school_year_code or item.school_year_name }}</td>\n                        <td>{{ item.commune_name }}</td>\n                        <td>{{ item.school_code or "—" }}</td>\n                        <td>{{ item.old_name }}</td>\n                        <td><strong>{{ item.new_name }}</strong></td>\n                    </tr>\n                    {% endfor %}\n                </tbody>\n            </table>\n        </div>\n        {% else %}\n        <div class="note info">Chưa có lần đổi tên trường nào được thực hiện bằng chức năng này.</div>\n        {% endif %}\n    </section>\n</main>\n\n<script>\n(function () {\n    "use strict";\n    const communes = {{ communes | tojson }};\n    const schools = {{ schools | tojson }};\n    const communeInput = document.getElementById("commune-search");\n    const communeId = document.getElementById("commune-id");\n    const communeList = document.getElementById("commune-list");\n    const schoolInput = document.getElementById("school-search");\n    const schoolId = document.getElementById("school-id");\n    const schoolList = document.getElementById("school-list");\n\n    function norm(value) {\n        return String(value || "")\n            .normalize("NFD")\n            .replace(/[\\u0300-\\u036f]/g, "")\n            .replace(/đ/g, "d").replace(/Đ/g, "D")\n            .toLowerCase()\n            .replace(/[^a-z0-9]+/g, " ")\n            .trim()\n            .replace(/\\s+/g, " ");\n    }\n\n    function render(input, hidden, box, rows, labelFn, valueFn) {\n        const q = norm(input.value);\n        box.innerHTML = "";\n        if (!q) { box.classList.remove("open"); return; }\n        const matches = rows.filter(row => norm(labelFn(row)).startsWith(q)).slice(0, 40);\n        if (!matches.length) {\n            const div = document.createElement("div");\n            div.className = "combo-empty";\n            div.textContent = "Không có kết quả phù hợp.";\n            box.appendChild(div);\n            box.classList.add("open");\n            return;\n        }\n        matches.forEach(row => {\n            const div = document.createElement("div");\n            div.className = "combo-item";\n            div.textContent = labelFn(row);\n            div.addEventListener("mousedown", function (event) {\n                event.preventDefault();\n                input.value = labelFn(row);\n                hidden.value = valueFn(row);\n                box.classList.remove("open");\n            });\n            box.appendChild(div);\n        });\n        box.classList.add("open");\n    }\n\n    if (communeInput) {\n        communeInput.addEventListener("input", function () {\n            communeId.value = "";\n            if (schoolInput) { schoolInput.value = ""; schoolId.value = ""; }\n            render(communeInput, communeId, communeList, communes, row => row.name, row => row.id);\n        });\n    }\n\n    if (schoolInput) {\n        schoolInput.addEventListener("input", function () {\n            schoolId.value = "";\n            render(schoolInput, schoolId, schoolList, schools, row => row.name, row => row.id);\n        });\n    }\n\n    document.addEventListener("click", function (event) {\n        if (communeList && !communeList.contains(event.target) && event.target !== communeInput) communeList.classList.remove("open");\n        if (schoolList && !schoolList.contains(event.target) && event.target !== schoolInput) schoolList.classList.remove("open");\n    });\n})();\n</script>\n</body>\n</html>\n'

def backup_db(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    s = sqlite3.connect(str(src))
    d = sqlite3.connect(str(dst))
    try:
        s.backup(d)
        d.commit()
    finally:
        d.close()
        s.close()
    c = sqlite3.connect(str(dst))
    try:
        integrity = c.execute("PRAGMA integrity_check").fetchone()[0]
        fk = c.execute("PRAGMA foreign_key_check").fetchall()
    finally:
        c.close()
    if integrity != "ok" or fk:
        raise RuntimeError("Backup DB trước V13.1 không đạt kiểm tra.")

def restore_db(src: Path, dst: Path) -> None:
    s = sqlite3.connect(str(src))
    d = sqlite3.connect(str(dst))
    try:
        s.backup(d)
        d.commit()
    finally:
        d.close()
        s.close()

def backup_file(path: Path) -> None:
    if not path.exists():
        return
    rel = path.relative_to(ROOT)
    dst = SOURCE_BACKUP / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, dst)

def restore_file(path: Path, existed: bool) -> None:
    rel = path.relative_to(ROOT)
    saved = SOURCE_BACKUP / rel
    if existed:
        if not saved.exists():
            raise RuntimeError(f"Thiếu backup source: {saved}")
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(saved, path)
    elif path.exists():
        path.unlink()

def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")

def patch_main(source: str) -> str:
    patched = source
    if IMPORT_MARK not in patched:
        candidates = (
            "from app.routers.school_merger import router as school_merger_router",
            "from app.routers.school_merger import router as school_merger_router\n",
        )
        anchor = next((x for x in candidates if x in patched), None)
        if anchor is None:
            raise RuntimeError("Không tìm thấy import school_merger_router trong app/main.py.")
        base = anchor.rstrip("\n")
        patched = patched.replace(
            base,
            base + "\n" + IMPORT_MARK + "\n"
            + "from app.routers.school_rename import router as school_rename_router",
            1,
        )
    if INCLUDE_MARK not in patched:
        anchor = "app.include_router(school_merger_router)"
        if anchor not in patched:
            raise RuntimeError("Không tìm thấy include school_merger_router trong app/main.py.")
        patched = patched.replace(
            anchor,
            anchor + "\n" + INCLUDE_MARK + "\n"
            + "app.include_router(school_rename_router)",
            1,
        )
    return patched

def patch_menu(source: str) -> str:
    if MENU_MARK in source:
        return source
    needle = "1.3.2. Sáp nhập trường"
    pos = source.find(needle)
    if pos < 0:
        raise RuntimeError("Không tìm thấy menu 1.3.2. Sáp nhập trường.")
    close = source.find("</a>", pos)
    if close < 0:
        raise RuntimeError("Không xác định được kết thúc menu 1.3.2.")
    close += len("</a>")
    block = (
        "\n                            " + MENU_MARK + "\n"
        "                            <a\n"
        "                                href=\"/cong-cu-du-lieu/doi-ten-truong\"\n"
        "                                role=\"menuitem\"\n"
        "                            >\n"
        "                                1.3.3. Đổi tên trường\n"
        "                            </a>"
    )
    return source[:close] + block + source[close:]

def patch_merger_template(source: str) -> str:
    if MERGER_BUTTON_MARK in source:
        return source
    anchor = (
        '            <a class="merge-btn muted" href="/cong-cu-du-lieu/sap-nhap-truong/phuong-an">\n'
        '                Danh sách phương án chính thức toàn tỉnh\n'
        '            </a>'
    )
    if anchor not in source:
        return source
    addition = (
        anchor + "\n            " + MERGER_BUTTON_MARK + "\n"
        '            <a class="merge-btn muted" href="/cong-cu-du-lieu/doi-ten-truong">\n'
        '                Đổi tên trường\n'
        '            </a>'
    )
    return source.replace(anchor, addition, 1)

def create_history_schema() -> None:
    con = sqlite3.connect(str(DB_PATH))
    try:
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("""
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
        """)
        con.execute("""
            CREATE INDEX IF NOT EXISTS ix_school_name_histories_school
            ON school_name_histories(school_id,id)
        """)
        con.commit()
    finally:
        con.close()

def db_health() -> tuple[str, int]:
    con = sqlite3.connect(str(DB_PATH))
    try:
        integrity = str(con.execute("PRAGMA integrity_check").fetchone()[0])
        fk = len(con.execute("PRAGMA foreign_key_check").fetchall())
        return integrity, fk
    finally:
        con.close()

def verify_sources() -> None:
    ast.parse(read_text(MAIN))
    ast.parse(read_text(ROUTER))
    from jinja2 import Environment
    env = Environment()
    env.parse(read_text(MENU))
    env.parse(read_text(MERGER_TEMPLATE))
    env.parse(read_text(TEMPLATE))
    if IMPORT_MARK not in read_text(MAIN):
        raise RuntimeError("Thiếu import marker V13.1.")
    if INCLUDE_MARK not in read_text(MAIN):
        raise RuntimeError("Thiếu include marker V13.1.")
    if "/cong-cu-du-lieu/doi-ten-truong" not in read_text(MENU):
        raise RuntimeError("Menu Đổi tên trường chưa được cài.")
    if 'prefix="/cong-cu-du-lieu/doi-ten-truong"' not in read_text(ROUTER):
        raise RuntimeError("Router Đổi tên trường không đúng.")

def main() -> int:
    print("=" * 116)
    print("V13.1 - ĐỔI TÊN TRƯỜNG")
    print("=" * 116)
    for path in (ROOT, DB_PATH, MAIN, MENU, MERGER_TEMPLATE):
        if not path.exists():
            print(f"Không tìm thấy: {path}")
            return 2

    EXPORTS.mkdir(parents=True, exist_ok=True)
    BACKUPS.mkdir(parents=True, exist_ok=True)
    SOURCE_BACKUP.mkdir(parents=True, exist_ok=False)

    existed = {
        MAIN: True,
        MENU: True,
        MERGER_TEMPLATE: True,
        ROUTER: ROUTER.exists(),
        TEMPLATE: TEMPLATE.exists(),
    }
    for path in existed:
        backup_file(path)

    print("[1/6] Kiểm tra DB trước cài...")
    integrity_before, fk_before = db_health()
    if integrity_before != "ok" or fk_before != 0:
        print(f"DB không đạt preflight: integrity={integrity_before}, FK={fk_before}")
        return 2

    print("[2/6] Backup DB...")
    backup_db(DB_PATH, DB_BACKUP)
    print(f"    {DB_BACKUP}")

    try:
        print("[3/6] Cài router + template...")
        ROUTER.parent.mkdir(parents=True, exist_ok=True)
        TEMPLATE.parent.mkdir(parents=True, exist_ok=True)
        ROUTER.write_text(ROUTER_CONTENT, encoding="utf-8")
        TEMPLATE.write_text(TEMPLATE_CONTENT, encoding="utf-8")

        print("[4/6] Gắn main.py + menu...")
        MAIN.write_text(patch_main(read_text(MAIN)), encoding="utf-8")
        MENU.write_text(patch_menu(read_text(MENU)), encoding="utf-8")
        MERGER_TEMPLATE.write_text(
            patch_merger_template(read_text(MERGER_TEMPLATE)),
            encoding="utf-8",
        )

        print("[5/6] Tạo bảng lịch sử tên trường...")
        create_history_schema()

        print("[6/6] Hậu kiểm...")
        verify_sources()
        py_compile.compile(str(ROUTER), doraise=True)
        py_compile.compile(str(MAIN), doraise=True)

        integrity_after, fk_after = db_health()
        if integrity_after != "ok" or fk_after != 0:
            raise RuntimeError(
                f"DB hậu kiểm lỗi: integrity={integrity_after}, FK={fk_after}"
            )

        con = sqlite3.connect(str(DB_PATH))
        try:
            table_ok = con.execute(
                "SELECT 1 FROM sqlite_master "
                "WHERE type='table' AND name='school_name_histories'"
            ).fetchone()
        finally:
            con.close()
        if not table_ok:
            raise RuntimeError("Chưa tạo được bảng school_name_histories.")

        REPORT.write_text(
            f"""V13.1 - ĐỔI TÊN TRƯỜNG
========================================
STATUS=SUCCESS

MENU:
1. Danh mục -> 1.3 Công cụ dữ liệu -> 1.3.3 Đổi tên trường

PHẦN ĐỔI TÊN:
- Tên cũ
- Tên mới

KHÔNG CÓ:
- Số/Ký hiệu văn bản
- Ngày văn bản
- Lý do/Ghi chú

NGUYÊN TẮC:
- school_id giữ nguyên
- mã trường giữ nguyên
- chỉ trường active
- chỉ năm học active
- lưu lịch sử old_name -> new_name
- backup DB trước mỗi lần đổi tên
- transaction + integrity/FK

DB:
- integrity trước={integrity_before}
- FK trước={fk_before}
- integrity sau={integrity_after}
- FK sau={fk_after}

BACKUP DB:
{DB_BACKUP}

BACKUP SOURCE:
{SOURCE_BACKUP}
""",
            encoding="utf-8",
        )

        print()
        print("=" * 116)
        print("CÀI V13.1 THÀNH CÔNG")
        print("=" * 116)
        print("Menu: 1.3.3. Đổi tên trường")
        print("Đổi tên: chỉ Tên cũ -> Tên mới")
        print("school_id: GIỮ NGUYÊN")
        print("Mã trường: GIỮ NGUYÊN")
        print(f"Integrity: {integrity_after}")
        print(f"FK errors: {fk_after}")
        print(f"Backup DB: {DB_BACKUP}")
        print(f"Backup source: {SOURCE_BACKUP}")
        print(f"Report: {REPORT}")
        print()
        print("Khởi động lại phần mềm rồi vào 1.3.3 Đổi tên trường.")
        return 0

    except Exception as exc:
        print()
        print("CÀI V13.1 LỖI:", repr(exc))
        print("Đang khôi phục source + database...")
        for path, was_present in existed.items():
            try:
                restore_file(path, was_present)
            except Exception as restore_exc:
                print(f"Cảnh báo restore source {path}: {restore_exc}")
        try:
            restore_db(DB_BACKUP, DB_PATH)
            print("Database đã được khôi phục.")
        except Exception as restore_exc:
            print("CẢNH BÁO: restore database lỗi:", repr(restore_exc))
        print("V13.1 CHƯA ĐƯỢC CÀI.")
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
