from __future__ import annotations

import hashlib
import py_compile
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from jinja2 import Environment


EXPECTED_NORMALIZED_HASHES = {
    "app/routers/auth.py":
        "c6318093672eac266da4328b1c5461d7420f7aea068697cc0a7cc93edb63abf0",
    "app/templates/auth/login.html":
        "981f5f2c824bcdb7f40993335571311db0bc54ca45d1694e577aa9eac06f4980",
}

AUTH_PAYLOAD = 'from __future__ import annotations\n\nfrom datetime import datetime\nfrom pathlib import Path\nfrom typing import Annotated\n\nfrom fastapi import (\n    APIRouter,\n    Depends,\n    Form,\n    Query,\n    Request,\n)\nfrom fastapi.responses import (\n    HTMLResponse,\n    JSONResponse,\n    RedirectResponse,\n)\nfrom fastapi.templating import Jinja2Templates\nfrom sqlalchemy import or_, select\nfrom sqlalchemy.orm import (\n    Session,\n    selectinload,\n)\n\nfrom app.database import get_db\nfrom app.models import (\n    Commune,\n    Role,\n    School,\n    SchoolYear,\n    User,\n)\nfrom app.security import kiem_tra_mat_khau\nfrom app.working_school_year import SESSION_KEY as WORKING_SCHOOL_YEAR_SESSION_KEY\n\n\nAPP_DIR = Path(__file__).resolve().parent.parent\n\ntemplates = Jinja2Templates(\n    directory=str(APP_DIR / "templates")\n)\n\nrouter = APIRouter(\n    tags=["Đăng nhập"],\n)\n\n\nSTATUS_MESSAGES = {\n    "required": (\n        "Bạn cần đăng nhập để sử dụng phần mềm."\n    ),\n    "invalid": (\n        "Tài khoản hoặc mật khẩu không chính xác."\n    ),\n    "locked": (\n        "Tài khoản không tồn tại hoặc đã bị khóa."\n    ),\n    "year_invalid": (\n        "Năm học đã chọn không hợp lệ hoặc không còn hoạt động."\n    ),\n    "logged_out": (\n        "Bạn đã đăng xuất khỏi hệ thống."\n    ),\n}\n\n\nLOGIN_SCOPE_ROLE_CODES = {\n    "SO": {"ADMIN", "SO", "PHONG_BAN"},\n    "XA": {"XA"},\n    "TRUONG": {"TRUONG"},\n    "GIAO_VIEN": {"GIAO_VIEN"},\n}\n\n\ndef chuan_hoa_ten_dang_nhap(\n    ten_dang_nhap: str,\n) -> str:\n    return ten_dang_nhap.strip().lower()\n\n\ndef _normalize_scope(value: str | None) -> str | None:\n    code = str(value or "").strip().upper()\n    return code if code in LOGIN_SCOPE_ROLE_CODES else None\n\n\ndef _safe_id(value: int | str | None) -> int | None:\n    try:\n        number = int(str(value).strip())\n    except (TypeError, ValueError):\n        return None\n    return number if number > 0 else None\n\n\ndef _active_school_years(\n    db: Session,\n) -> list[SchoolYear]:\n    return list(\n        db.scalars(\n            select(SchoolYear)\n            .where(SchoolYear.is_active.is_(True))\n            .order_by(\n                SchoolYear.code.desc(),\n                SchoolYear.id.desc(),\n            )\n        ).all()\n    )\n\n\ndef _default_school_year_id(\n    school_years: list[SchoolYear],\n) -> int | None:\n    if not school_years:\n        return None\n\n    now = datetime.now()\n    start_year = now.year if now.month >= 7 else now.year - 1\n    expected_code = f"{start_year}-{start_year + 1}"\n\n    for item in school_years:\n        if str(item.code or "").strip() == expected_code:\n            return int(item.id)\n\n    return int(school_years[0].id)\n\n\ndef _trim_query(value: str | None) -> str:\n    return " ".join(str(value or "").strip().split())[:100]\n\n\ndef _json_no_store(payload: dict) -> JSONResponse:\n    return JSONResponse(\n        payload,\n        headers={\n            "Cache-Control": "no-store, max-age=0",\n            "Pragma": "no-cache",\n        },\n    )\n\n\n@router.get(\n    "/dang-nhap",\n    response_class=HTMLResponse,\n)\ndef form_dang_nhap(\n    request: Request,\n    status: str | None = None,\n    db: Session = Depends(get_db),\n):\n    if request.session.get("user_id") is not None:\n        return RedirectResponse(\n            url="/",\n            status_code=303,\n        )\n\n    school_years = _active_school_years(db)\n\n    return templates.TemplateResponse(\n        request=request,\n        name="auth/login.html",\n        context={\n            "thong_bao": STATUS_MESSAGES.get(status),\n            "trang_thai": status,\n            "school_years": school_years,\n            "default_school_year_id": _default_school_year_id(\n                school_years\n            ),\n        },\n    )\n\n\n@router.get("/dang-nhap/api/lua-chon")\ndef api_lua_chon_dang_nhap(\n    loai: Annotated[str, Query()],\n    cap: Annotated[str | None, Query()] = None,\n    commune_id: Annotated[int | None, Query()] = None,\n    school_id: Annotated[int | None, Query()] = None,\n    q: Annotated[str | None, Query()] = None,\n    db: Session = Depends(get_db),\n):\n    """\n    API công khai phục vụ màn hình đăng nhập phân cấp.\n\n    Chỉ trả về danh mục/tài khoản đang hoạt động.\n    Không bao giờ trả mật khẩu hay password_hash.\n    """\n    loai = str(loai or "").strip().lower()\n    q_text = _trim_query(q)\n    q_like = f"%{q_text}%"\n\n    if loai == "communes":\n        stmt = (\n            select(Commune)\n            .where(Commune.is_active.is_(True))\n            .order_by(Commune.name, Commune.code)\n            .limit(40)\n        )\n\n        if q_text:\n            stmt = stmt.where(\n                or_(\n                    Commune.name.ilike(q_like),\n                    Commune.code.ilike(q_like),\n                )\n            )\n\n        rows = list(db.scalars(stmt).all())\n\n        return _json_no_store(\n            {\n                "ok": True,\n                "items": [\n                    {\n                        "id": int(item.id),\n                        "value": str(item.id),\n                        "text": str(item.name or ""),\n                        "subtext": str(item.code or ""),\n                    }\n                    for item in rows\n                ],\n            }\n        )\n\n    if loai == "schools":\n        selected_commune_id = _safe_id(commune_id)\n        if selected_commune_id is None:\n            return _json_no_store(\n                {"ok": True, "items": []}\n            )\n\n        stmt = (\n            select(School)\n            .where(\n                School.is_active.is_(True),\n                School.commune_id == selected_commune_id,\n            )\n            .order_by(School.name, School.code)\n            .limit(50)\n        )\n\n        if q_text:\n            stmt = stmt.where(\n                or_(\n                    School.name.ilike(q_like),\n                    School.code.ilike(q_like),\n                )\n            )\n\n        rows = list(db.scalars(stmt).all())\n\n        return _json_no_store(\n            {\n                "ok": True,\n                "items": [\n                    {\n                        "id": int(item.id),\n                        "value": str(item.id),\n                        "text": str(item.name or ""),\n                        "subtext": str(item.code or ""),\n                    }\n                    for item in rows\n                ],\n            }\n        )\n\n    if loai == "accounts":\n        scope = _normalize_scope(cap)\n        if scope is None:\n            return _json_no_store(\n                {"ok": True, "items": []}\n            )\n\n        role_codes = LOGIN_SCOPE_ROLE_CODES[scope]\n\n        stmt = (\n            select(User)\n            .join(Role, User.role_id == Role.id)\n            .options(\n                selectinload(User.role),\n                selectinload(User.commune),\n                selectinload(User.school),\n            )\n            .where(\n                User.is_active.is_(True),\n                Role.code.in_(role_codes),\n            )\n            .order_by(\n                User.full_name,\n                User.username,\n            )\n            .limit(50)\n        )\n\n        if scope == "SO":\n            stmt = stmt.where(\n                User.commune_id.is_(None),\n                User.school_id.is_(None),\n            )\n\n        elif scope == "XA":\n            selected_commune_id = _safe_id(commune_id)\n            if selected_commune_id is None:\n                return _json_no_store(\n                    {"ok": True, "items": []}\n                )\n            stmt = stmt.where(\n                User.commune_id == selected_commune_id,\n                User.school_id.is_(None),\n            )\n\n        elif scope in {"TRUONG", "GIAO_VIEN"}:\n            selected_school_id = _safe_id(school_id)\n            if selected_school_id is None:\n                return _json_no_store(\n                    {"ok": True, "items": []}\n                )\n            stmt = stmt.where(\n                User.school_id == selected_school_id\n            )\n\n        if q_text:\n            stmt = stmt.where(\n                or_(\n                    User.username.ilike(q_like),\n                    User.full_name.ilike(q_like),\n                )\n            )\n\n        rows = list(db.scalars(stmt).all())\n\n        items = []\n        for item in rows:\n            role_name = (\n                str(item.role.name or "")\n                if item.role is not None\n                else ""\n            )\n\n            location = ""\n            if item.school is not None:\n                location = str(item.school.name or "")\n            elif item.commune is not None:\n                location = str(item.commune.name or "")\n\n            sub_parts = [\n                part\n                for part in (\n                    str(item.full_name or ""),\n                    role_name,\n                    location,\n                )\n                if part\n            ]\n\n            items.append(\n                {\n                    "id": int(item.id),\n                    "value": str(item.username or ""),\n                    "text": str(item.username or ""),\n                    "subtext": " · ".join(sub_parts),\n                }\n            )\n\n        return _json_no_store(\n            {\n                "ok": True,\n                "items": items,\n            }\n        )\n\n    return _json_no_store(\n        {\n            "ok": False,\n            "items": [],\n            "detail": "Loại dữ liệu không hợp lệ.",\n        }\n    )\n\n\n@router.post("/dang-nhap")\ndef xu_ly_dang_nhap(\n    request: Request,\n    ten_dang_nhap: Annotated[str, Form()],\n    mat_khau: Annotated[str, Form()],\n    school_year_id: Annotated[str, Form()],\n    db: Session = Depends(get_db),\n):\n    ten_dang_nhap = chuan_hoa_ten_dang_nhap(\n        ten_dang_nhap\n    )\n\n    selected_year_id = _safe_id(\n        school_year_id\n    )\n\n    if (\n        not ten_dang_nhap\n        or not mat_khau\n        or selected_year_id is None\n    ):\n        return RedirectResponse(\n            url="/dang-nhap?status=invalid",\n            status_code=303,\n        )\n\n    selected_year = db.scalar(\n        select(SchoolYear).where(\n            SchoolYear.id == selected_year_id,\n            SchoolYear.is_active.is_(True),\n        )\n    )\n\n    if selected_year is None:\n        return RedirectResponse(\n            url="/dang-nhap?status=year_invalid",\n            status_code=303,\n        )\n\n    statement = (\n        select(User)\n        .options(\n            selectinload(User.role),\n        )\n        .where(\n            User.username == ten_dang_nhap\n        )\n    )\n\n    user = db.scalar(statement)\n\n    if user is None:\n        return RedirectResponse(\n            url="/dang-nhap?status=invalid",\n            status_code=303,\n        )\n\n    if not user.is_active:\n        return RedirectResponse(\n            url="/dang-nhap?status=locked",\n            status_code=303,\n        )\n\n    try:\n        mat_khau_hop_le = kiem_tra_mat_khau(\n            mat_khau_thuong=mat_khau,\n            mat_khau_da_ma_hoa=user.password_hash,\n        )\n    except Exception:\n        mat_khau_hop_le = False\n\n    if not mat_khau_hop_le:\n        return RedirectResponse(\n            url="/dang-nhap?status=invalid",\n            status_code=303,\n        )\n\n    request.session.clear()\n    request.session["user_id"] = user.id\n    request.session[\n        WORKING_SCHOOL_YEAR_SESSION_KEY\n    ] = int(selected_year.id)\n\n    return RedirectResponse(\n        url="/",\n        status_code=303,\n    )\n\n\n@router.post("/dang-xuat")\ndef dang_xuat(\n    request: Request,\n):\n    request.session.clear()\n\n    return RedirectResponse(\n        url="/dang-nhap?status=logged_out",\n        status_code=303,\n    )\n'
LOGIN_PAYLOAD = '<!DOCTYPE html>\n<html lang="vi">\n<head>\n    <meta charset="UTF-8">\n    <meta\n        name="viewport"\n        content="width=device-width, initial-scale=1.0"\n    >\n    <title>Đăng nhập hệ thống</title>\n\n    <style>\n        :root {\n            --pc-blue: #1769c2;\n            --pc-blue-dark: #0d4f98;\n            --pc-blue-soft: #eef6ff;\n            --pc-line: #d9e2ec;\n            --pc-text: #24364b;\n            --pc-muted: #66788a;\n            --pc-danger: #b42318;\n            --pc-success: #157a42;\n            --pc-card: #ffffff;\n            --pc-bg: #f3f7fb;\n        }\n\n        * {\n            box-sizing: border-box;\n        }\n\n        html,\n        body {\n            min-height: 100%;\n        }\n\n        body {\n            margin: 0;\n            font-family:\n                Inter,\n                "Segoe UI",\n                Arial,\n                sans-serif;\n            color: var(--pc-text);\n            background:\n                linear-gradient(\n                    180deg,\n                    #eaf3ff 0,\n                    var(--pc-bg) 260px,\n                    #f7f9fc 100%\n                );\n        }\n\n        .login-shell {\n            width: min(100%, 620px);\n            margin: 0 auto;\n            padding: 28px 18px 38px;\n        }\n\n        .login-brand {\n            display: flex;\n            align-items: center;\n            gap: 14px;\n            margin-bottom: 18px;\n        }\n\n        .login-logo {\n            width: 58px;\n            height: 58px;\n            border-radius: 50%;\n            display: grid;\n            place-items: center;\n            background: var(--pc-blue);\n            color: #fff;\n            font-size: 20px;\n            font-weight: 900;\n            box-shadow: 0 8px 24px rgba(23, 105, 194, 0.24);\n        }\n\n        .login-brand h1 {\n            margin: 0;\n            font-size: clamp(22px, 4vw, 30px);\n            line-height: 1.1;\n            font-weight: 800;\n        }\n\n        .login-brand p {\n            margin: 5px 0 0;\n            color: var(--pc-blue);\n            font-weight: 700;\n        }\n\n        .login-card {\n            background: var(--pc-card);\n            border: 1px solid #e1e8ef;\n            border-radius: 18px;\n            box-shadow:\n                0 16px 42px rgba(33, 57, 82, 0.12);\n            overflow: visible;\n        }\n\n        .login-card-head {\n            padding: 22px 24px 14px;\n            border-bottom: 1px solid #edf1f5;\n        }\n\n        .login-card-head .eyebrow {\n            color: var(--pc-blue);\n            font-size: 12px;\n            font-weight: 900;\n            letter-spacing: 0.08em;\n            text-transform: uppercase;\n        }\n\n        .login-card-head h2 {\n            margin: 5px 0 0;\n            font-size: 24px;\n        }\n\n        .login-form {\n            padding: 22px 24px 26px;\n        }\n\n        .field {\n            margin-bottom: 16px;\n            position: relative;\n        }\n\n        .field label {\n            display: block;\n            margin-bottom: 7px;\n            font-size: 14px;\n            font-weight: 800;\n            color: #31506f;\n        }\n\n        .field input,\n        .field select {\n            width: 100%;\n            height: 46px;\n            padding: 0 13px;\n            border: 1px solid #cbd6e2;\n            border-radius: 10px;\n            background: #fff;\n            color: #1f3042;\n            font-size: 15px;\n            outline: none;\n        }\n\n        .field input:focus,\n        .field select:focus {\n            border-color: var(--pc-blue);\n            box-shadow: 0 0 0 3px rgba(23, 105, 194, 0.12);\n        }\n\n        .fixed-unit {\n            min-height: 46px;\n            display: flex;\n            align-items: center;\n            justify-content: space-between;\n            gap: 12px;\n            padding: 0 13px;\n            border: 1px solid #d7e0e8;\n            border-radius: 10px;\n            background: #f8fafc;\n        }\n\n        .fixed-unit strong {\n            color: #20364d;\n        }\n\n        .fixed-unit span {\n            color: var(--pc-muted);\n            font-size: 13px;\n        }\n\n        .combo {\n            position: relative;\n        }\n\n        .combo-list {\n            position: absolute;\n            z-index: 1000;\n            left: 0;\n            right: 0;\n            top: calc(100% + 5px);\n            max-height: 260px;\n            overflow: auto;\n            background: #fff;\n            border: 1px solid #c9d6e3;\n            border-radius: 11px;\n            box-shadow:\n                0 16px 32px rgba(33, 57, 82, 0.18);\n            display: none;\n        }\n\n        .combo-list.is-open {\n            display: block;\n        }\n\n        .combo-item {\n            padding: 10px 12px;\n            cursor: pointer;\n            border-bottom: 1px solid #edf1f5;\n        }\n\n        .combo-item:last-child {\n            border-bottom: 0;\n        }\n\n        .combo-item:hover,\n        .combo-item.is-active {\n            background: var(--pc-blue-soft);\n        }\n\n        .combo-item strong {\n            display: block;\n            font-size: 14px;\n            color: #183b5d;\n        }\n\n        .combo-item small {\n            display: block;\n            margin-top: 2px;\n            color: var(--pc-muted);\n            font-size: 12px;\n            line-height: 1.3;\n        }\n\n        .combo-empty {\n            padding: 12px;\n            color: var(--pc-muted);\n            font-size: 13px;\n        }\n\n        .field-help {\n            margin-top: 6px;\n            color: var(--pc-muted);\n            font-size: 12px;\n            line-height: 1.4;\n        }\n\n        .remember-row {\n            display: flex;\n            align-items: center;\n            gap: 8px;\n            margin: 2px 0 18px;\n            font-size: 14px;\n            color: #31506f;\n        }\n\n        .remember-row input {\n            width: 17px;\n            height: 17px;\n            margin: 0;\n        }\n\n        .login-button {\n            width: 100%;\n            min-height: 48px;\n            border: 0;\n            border-radius: 10px;\n            background:\n                linear-gradient(\n                    135deg,\n                    var(--pc-blue-dark),\n                    var(--pc-blue)\n                );\n            color: #fff;\n            font-size: 15px;\n            font-weight: 900;\n            cursor: pointer;\n        }\n\n        .login-button:hover {\n            filter: brightness(1.04);\n        }\n\n        .alert {\n            margin: 0 24px 0;\n            padding: 11px 13px;\n            border-radius: 9px;\n            font-size: 14px;\n            font-weight: 700;\n        }\n\n        .alert-error {\n            color: var(--pc-danger);\n            background: #fff1f0;\n            border: 1px solid #ffd3cf;\n        }\n\n        .alert-success {\n            color: var(--pc-success);\n            background: #edf9f2;\n            border: 1px solid #c9ead7;\n        }\n\n        .hidden {\n            display: none !important;\n        }\n\n        .security-note {\n            margin-top: 16px;\n            color: var(--pc-muted);\n            font-size: 12px;\n            text-align: center;\n            line-height: 1.5;\n        }\n\n        @media (max-width: 560px) {\n            .login-shell {\n                padding: 18px 10px 28px;\n            }\n\n            .login-card-head,\n            .login-form {\n                padding-left: 16px;\n                padding-right: 16px;\n            }\n\n            .alert {\n                margin-left: 16px;\n                margin-right: 16px;\n            }\n\n            .login-brand {\n                padding: 0 4px;\n            }\n        }\n    </style>\n</head>\n\n<body>\n    <main class="login-shell">\n        <div class="login-brand">\n            <div class="login-logo">PC</div>\n\n            <div>\n                <h1>ĐĂNG NHẬP HỆ THỐNG</h1>\n                <p>Phổ cập giáo dục và Xóa mù chữ</p>\n            </div>\n        </div>\n\n        <section class="login-card">\n            <div class="login-card-head">\n                <div class="eyebrow">\n                    Tài khoản của bạn\n                </div>\n                <h2>Chọn đúng đơn vị để đăng nhập</h2>\n            </div>\n\n            {% if thong_bao %}\n                <div\n                    class="\n                        alert\n                        {% if trang_thai == \'logged_out\' %}\n                            alert-success\n                        {% else %}\n                            alert-error\n                        {% endif %}\n                    "\n                >\n                    {{ thong_bao }}\n                </div>\n            {% endif %}\n\n            <form\n                id="login-form"\n                class="login-form"\n                method="post"\n                action="/dang-nhap"\n                autocomplete="on"\n            >\n                <input\n                    id="ten_dang_nhap"\n                    name="ten_dang_nhap"\n                    type="hidden"\n                    value=""\n                >\n\n                <div class="field">\n                    <label for="cap_dang_nhap">\n                        1. Cấp đăng nhập\n                    </label>\n\n                    <select\n                        id="cap_dang_nhap"\n                        required\n                    >\n                        <option value="">\n                            -- Chọn cấp đăng nhập --\n                        </option>\n                        <option value="SO">\n                            Cấp Sở / Quản trị\n                        </option>\n                        <option value="XA">\n                            Xã / phường\n                        </option>\n                        <option value="TRUONG">\n                            Trường\n                        </option>\n                        <option value="GIAO_VIEN">\n                            Giáo viên\n                        </option>\n                    </select>\n                </div>\n\n                <div class="field">\n                    <label>Thông tin đơn vị</label>\n                    <div class="fixed-unit">\n                        <strong>Tỉnh Nghệ An</strong>\n                        <span>Phạm vi hệ thống</span>\n                    </div>\n                </div>\n\n                <div\n                    id="commune-field"\n                    class="field hidden"\n                >\n                    <label for="commune-search">\n                        Xã / phường\n                    </label>\n\n                    <div class="combo">\n                        <input\n                            id="commune-search"\n                            type="text"\n                            placeholder="Gõ tên xã/phường để tìm"\n                            autocomplete="off"\n                        >\n                        <input\n                            id="commune-id"\n                            type="hidden"\n                            value=""\n                        >\n                        <div\n                            id="commune-list"\n                            class="combo-list"\n                        ></div>\n                    </div>\n                </div>\n\n                <div\n                    id="school-field"\n                    class="field hidden"\n                >\n                    <label for="school-search">\n                        Trường\n                    </label>\n\n                    <div class="combo">\n                        <input\n                            id="school-search"\n                            type="text"\n                            placeholder="Gõ tên trường để tìm"\n                            autocomplete="off"\n                        >\n                        <input\n                            id="school-id"\n                            type="hidden"\n                            value=""\n                        >\n                        <div\n                            id="school-list"\n                            class="combo-list"\n                        ></div>\n                    </div>\n                </div>\n\n                <div\n                    id="account-field"\n                    class="field hidden"\n                >\n                    <label for="account-search">\n                        Tài khoản\n                    </label>\n\n                    <div class="combo">\n                        <input\n                            id="account-search"\n                            type="text"\n                            placeholder="Gõ tên đăng nhập hoặc họ tên"\n                            autocomplete="username"\n                        >\n                        <div\n                            id="account-list"\n                            class="combo-list"\n                        ></div>\n                    </div>\n\n                    <div class="field-help">\n                        Chọn tài khoản trong danh sách gợi ý.\n                        Nếu đơn vị chỉ có một tài khoản,\n                        hệ thống sẽ tự chọn.\n                    </div>\n                </div>\n\n                <div\n                    id="password-field"\n                    class="field hidden"\n                >\n                    <label for="mat_khau">\n                        Mật khẩu\n                    </label>\n\n                    <input\n                        id="mat_khau"\n                        name="mat_khau"\n                        type="password"\n                        placeholder="Nhập mật khẩu"\n                        autocomplete="current-password"\n                        required\n                    >\n                </div>\n\n                <div class="field">\n                    <label for="school_year_id">\n                        Năm học làm việc\n                    </label>\n\n                    <select\n                        id="school_year_id"\n                        name="school_year_id"\n                        required\n                    >\n                        {% for year in school_years %}\n                            <option\n                                value="{{ year.id }}"\n                                {% if year.id == default_school_year_id %}\n                                    selected\n                                {% endif %}\n                            >\n                                {{ year.code }}\n                            </option>\n                        {% endfor %}\n                    </select>\n\n                    <div class="field-help">\n                        Năm học này được dùng ngay sau khi đăng nhập,\n                        không cần chọn lại trên trang chính.\n                    </div>\n                </div>\n\n                <label class="remember-row">\n                    <input\n                        id="remember-account"\n                        type="checkbox"\n                    >\n                    <span>\n                        Ghi nhớ tài khoản và đơn vị trên thiết bị này\n                    </span>\n                </label>\n\n                <button\n                    class="login-button"\n                    type="submit"\n                >\n                    Đăng nhập\n                </button>\n            </form>\n        </section>\n\n        <div class="security-note">\n            Hệ thống chỉ ghi nhớ cấp đăng nhập, đơn vị,\n            tài khoản và năm học khi bạn chọn “Ghi nhớ”.\n            Mật khẩu không được lưu.\n        </div>\n    </main>\n\n    <script>\n        (function () {\n            const API_URL =\n                "/dang-nhap/api/lua-chon";\n\n            const STORAGE_KEY =\n                "phocap_login_selection_v2";\n\n            const form =\n                document.getElementById("login-form");\n\n            const scope =\n                document.getElementById("cap_dang_nhap");\n\n            const communeField =\n                document.getElementById("commune-field");\n            const communeInput =\n                document.getElementById("commune-search");\n            const communeId =\n                document.getElementById("commune-id");\n            const communeList =\n                document.getElementById("commune-list");\n\n            const schoolField =\n                document.getElementById("school-field");\n            const schoolInput =\n                document.getElementById("school-search");\n            const schoolId =\n                document.getElementById("school-id");\n            const schoolList =\n                document.getElementById("school-list");\n\n            const accountField =\n                document.getElementById("account-field");\n            const accountInput =\n                document.getElementById("account-search");\n            const accountList =\n                document.getElementById("account-list");\n            const username =\n                document.getElementById("ten_dang_nhap");\n\n            const passwordField =\n                document.getElementById("password-field");\n            const password =\n                document.getElementById("mat_khau");\n\n            const yearSelect =\n                document.getElementById("school_year_id");\n            const remember =\n                document.getElementById("remember-account");\n\n            let restoring = false;\n\n            function debounce(fn, delay) {\n                let timer = null;\n\n                return function () {\n                    const args = arguments;\n                    clearTimeout(timer);\n                    timer = setTimeout(\n                        function () {\n                            fn.apply(null, args);\n                        },\n                        delay\n                    );\n                };\n            }\n\n            function closeList(list) {\n                list.classList.remove("is-open");\n            }\n\n            function openList(list) {\n                list.classList.add("is-open");\n            }\n\n            function clearList(list) {\n                list.innerHTML = "";\n                closeList(list);\n            }\n\n            function clearAccount() {\n                accountInput.value = "";\n                username.value = "";\n                clearList(accountList);\n                password.value = "";\n            }\n\n            function clearSchool() {\n                schoolInput.value = "";\n                schoolId.value = "";\n                clearList(schoolList);\n                clearAccount();\n            }\n\n            function clearCommune() {\n                communeInput.value = "";\n                communeId.value = "";\n                clearList(communeList);\n                clearSchool();\n            }\n\n            function showByScope() {\n                const value = scope.value;\n\n                const needsCommune =\n                    value === "XA"\n                    || value === "TRUONG"\n                    || value === "GIAO_VIEN";\n\n                const needsSchool =\n                    value === "TRUONG"\n                    || value === "GIAO_VIEN";\n\n                communeField.classList.toggle(\n                    "hidden",\n                    !needsCommune\n                );\n\n                schoolField.classList.toggle(\n                    "hidden",\n                    !needsSchool\n                );\n\n                accountField.classList.toggle(\n                    "hidden",\n                    !value\n                );\n\n                passwordField.classList.toggle(\n                    "hidden",\n                    !value\n                );\n            }\n\n            async function api(params) {\n                const url =\n                    API_URL\n                    + "?"\n                    + new URLSearchParams(params).toString();\n\n                const response =\n                    await fetch(\n                        url,\n                        {\n                            headers: {\n                                "Accept": "application/json"\n                            },\n                            cache: "no-store"\n                        }\n                    );\n\n                if (!response.ok) {\n                    return {\n                        ok: false,\n                        items: []\n                    };\n                }\n\n                return await response.json();\n            }\n\n            function renderList(\n                list,\n                items,\n                onPick\n            ) {\n                list.innerHTML = "";\n\n                if (!items.length) {\n                    const empty =\n                        document.createElement("div");\n                    empty.className = "combo-empty";\n                    empty.textContent =\n                        "Không tìm thấy dữ liệu phù hợp.";\n                    list.appendChild(empty);\n                    openList(list);\n                    return;\n                }\n\n                items.forEach(function (item) {\n                    const row =\n                        document.createElement("div");\n                    row.className = "combo-item";\n                    row.tabIndex = 0;\n\n                    const title =\n                        document.createElement("strong");\n                    title.textContent =\n                        String(item.text || "");\n\n                    row.appendChild(title);\n\n                    if (item.subtext) {\n                        const sub =\n                            document.createElement("small");\n                        sub.textContent =\n                            String(item.subtext || "");\n                        row.appendChild(sub);\n                    }\n\n                    function pick() {\n                        onPick(item);\n                        closeList(list);\n                    }\n\n                    row.addEventListener(\n                        "mousedown",\n                        function (event) {\n                            event.preventDefault();\n                            pick();\n                        }\n                    );\n\n                    row.addEventListener(\n                        "keydown",\n                        function (event) {\n                            if (\n                                event.key === "Enter"\n                                || event.key === " "\n                            ) {\n                                event.preventDefault();\n                                pick();\n                            }\n                        }\n                    );\n\n                    list.appendChild(row);\n                });\n\n                openList(list);\n            }\n\n            async function loadCommunes(query) {\n                const data =\n                    await api({\n                        loai: "communes",\n                        q: query || ""\n                    });\n\n                renderList(\n                    communeList,\n                    data.items || [],\n                    function (item) {\n                        communeInput.value =\n                            String(item.text || "");\n                        communeId.value =\n                            String(item.id || "");\n\n                        clearSchool();\n\n                        if (\n                            scope.value === "XA"\n                        ) {\n                            loadAccounts("");\n                        } else {\n                            schoolInput.focus();\n                            loadSchools("");\n                        }\n                    }\n                );\n            }\n\n            async function loadSchools(query) {\n                if (!communeId.value) {\n                    return;\n                }\n\n                const data =\n                    await api({\n                        loai: "schools",\n                        commune_id: communeId.value,\n                        q: query || ""\n                    });\n\n                renderList(\n                    schoolList,\n                    data.items || [],\n                    function (item) {\n                        schoolInput.value =\n                            String(item.text || "");\n                        schoolId.value =\n                            String(item.id || "");\n\n                        clearAccount();\n                        loadAccounts("");\n                    }\n                );\n            }\n\n            async function loadAccounts(query) {\n                const currentScope =\n                    scope.value;\n\n                if (!currentScope) {\n                    return;\n                }\n\n                if (\n                    currentScope === "XA"\n                    && !communeId.value\n                ) {\n                    return;\n                }\n\n                if (\n                    (\n                        currentScope === "TRUONG"\n                        || currentScope === "GIAO_VIEN"\n                    )\n                    && !schoolId.value\n                ) {\n                    return;\n                }\n\n                const data =\n                    await api({\n                        loai: "accounts",\n                        cap: currentScope,\n                        commune_id: communeId.value || "",\n                        school_id: schoolId.value || "",\n                        q: query || ""\n                    });\n\n                const items = data.items || [];\n\n                if (\n                    items.length === 1\n                    && !query\n                ) {\n                    selectAccount(items[0]);\n                    return;\n                }\n\n                renderList(\n                    accountList,\n                    items,\n                    selectAccount\n                );\n            }\n\n            function selectAccount(item) {\n                accountInput.value =\n                    String(item.text || item.value || "");\n                username.value =\n                    String(item.value || "");\n\n                closeList(accountList);\n\n                window.setTimeout(\n                    function () {\n                        password.focus();\n                    },\n                    30\n                );\n            }\n\n            const searchCommunes =\n                debounce(\n                    function () {\n                        communeId.value = "";\n                        clearSchool();\n                        loadCommunes(\n                            communeInput.value\n                        );\n                    },\n                    220\n                );\n\n            const searchSchools =\n                debounce(\n                    function () {\n                        schoolId.value = "";\n                        clearAccount();\n                        loadSchools(\n                            schoolInput.value\n                        );\n                    },\n                    220\n                );\n\n            const searchAccounts =\n                debounce(\n                    function () {\n                        username.value = "";\n                        loadAccounts(\n                            accountInput.value\n                        );\n                    },\n                    220\n                );\n\n            communeInput.addEventListener(\n                "input",\n                searchCommunes\n            );\n\n            communeInput.addEventListener(\n                "focus",\n                function () {\n                    loadCommunes(\n                        communeInput.value\n                    );\n                }\n            );\n\n            schoolInput.addEventListener(\n                "input",\n                searchSchools\n            );\n\n            schoolInput.addEventListener(\n                "focus",\n                function () {\n                    if (communeId.value) {\n                        loadSchools(\n                            schoolInput.value\n                        );\n                    }\n                }\n            );\n\n            accountInput.addEventListener(\n                "input",\n                searchAccounts\n            );\n\n            accountInput.addEventListener(\n                "focus",\n                function () {\n                    loadAccounts(\n                        accountInput.value\n                    );\n                }\n            );\n\n            scope.addEventListener(\n                "change",\n                function () {\n                    if (!restoring) {\n                        clearCommune();\n                    }\n\n                    showByScope();\n\n                    if (\n                        scope.value === "SO"\n                    ) {\n                        loadAccounts("");\n                    } else if (\n                        scope.value\n                        && !communeId.value\n                    ) {\n                        communeInput.focus();\n                    }\n                }\n            );\n\n            document.addEventListener(\n                "mousedown",\n                function (event) {\n                    [\n                        {\n                            input: communeInput,\n                            list: communeList\n                        },\n                        {\n                            input: schoolInput,\n                            list: schoolList\n                        },\n                        {\n                            input: accountInput,\n                            list: accountList\n                        }\n                    ].forEach(function (pair) {\n                        if (\n                            event.target !== pair.input\n                            && !pair.list.contains(\n                                event.target\n                            )\n                        ) {\n                            closeList(pair.list);\n                        }\n                    });\n                }\n            );\n\n            function saveRemembered() {\n                if (!remember.checked) {\n                    localStorage.removeItem(\n                        STORAGE_KEY\n                    );\n                    return;\n                }\n\n                const payload = {\n                    scope: scope.value,\n                    commune_id: communeId.value,\n                    commune_text: communeInput.value,\n                    school_id: schoolId.value,\n                    school_text: schoolInput.value,\n                    username: username.value,\n                    account_text: accountInput.value,\n                    year_id: yearSelect.value\n                };\n\n                localStorage.setItem(\n                    STORAGE_KEY,\n                    JSON.stringify(payload)\n                );\n            }\n\n            function restoreRemembered() {\n                let saved = null;\n\n                try {\n                    saved = JSON.parse(\n                        localStorage.getItem(\n                            STORAGE_KEY\n                        ) || "null"\n                    );\n                } catch (error) {\n                    saved = null;\n                }\n\n                if (!saved) {\n                    showByScope();\n                    return;\n                }\n\n                restoring = true;\n                remember.checked = true;\n\n                scope.value =\n                    String(saved.scope || "");\n\n                communeId.value =\n                    String(saved.commune_id || "");\n                communeInput.value =\n                    String(saved.commune_text || "");\n\n                schoolId.value =\n                    String(saved.school_id || "");\n                schoolInput.value =\n                    String(saved.school_text || "");\n\n                username.value =\n                    String(saved.username || "");\n                accountInput.value =\n                    String(\n                        saved.account_text\n                        || saved.username\n                        || ""\n                    );\n\n                if (\n                    saved.year_id\n                    && Array.from(\n                        yearSelect.options\n                    ).some(\n                        function (option) {\n                            return String(option.value)\n                                === String(saved.year_id);\n                        }\n                    )\n                ) {\n                    yearSelect.value =\n                        String(saved.year_id);\n                }\n\n                showByScope();\n                restoring = false;\n            }\n\n            form.addEventListener(\n                "submit",\n                function (event) {\n                    if (!scope.value) {\n                        event.preventDefault();\n                        alert(\n                            "Hãy chọn cấp đăng nhập."\n                        );\n                        scope.focus();\n                        return;\n                    }\n\n                    if (\n                        (\n                            scope.value === "XA"\n                            || scope.value === "TRUONG"\n                            || scope.value === "GIAO_VIEN"\n                        )\n                        && !communeId.value\n                    ) {\n                        event.preventDefault();\n                        alert(\n                            "Hãy chọn xã/phường trong danh sách gợi ý."\n                        );\n                        communeInput.focus();\n                        return;\n                    }\n\n                    if (\n                        (\n                            scope.value === "TRUONG"\n                            || scope.value === "GIAO_VIEN"\n                        )\n                        && !schoolId.value\n                    ) {\n                        event.preventDefault();\n                        alert(\n                            "Hãy chọn trường trong danh sách gợi ý."\n                        );\n                        schoolInput.focus();\n                        return;\n                    }\n\n                    if (!username.value) {\n                        event.preventDefault();\n                        alert(\n                            "Hãy chọn tài khoản trong danh sách gợi ý."\n                        );\n                        accountInput.focus();\n                        return;\n                    }\n\n                    saveRemembered();\n                }\n            );\n\n            restoreRemembered();\n        }());\n    </script>\n</body>\n</html>\n'


def normalized_sha256(path: Path) -> str:
    raw = path.read_bytes()
    normalized = (
        raw
        .replace(b"\r\n", b"\n")
        .replace(b"\r", b"\n")
    )
    return hashlib.sha256(normalized).hexdigest()


def db_check(path: Path) -> tuple[str, int]:
    if not path.is_file():
        return "missing", 0

    uri = f"file:{path.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)

    try:
        integrity = str(
            conn.execute(
                "PRAGMA integrity_check"
            ).fetchone()[0]
        )

        fk_count = len(
            list(
                conn.execute(
                    "PRAGMA foreign_key_check"
                )
            )
        )

        return integrity, fk_count
    finally:
        conn.close()


def main() -> int:
    root = Path(r"C:\PhoCap")

    if not (
        root
        / "app"
        / "routers"
        / "auth.py"
    ).is_file():
        root = Path.cwd()

    auth_path = (
        root
        / "app"
        / "routers"
        / "auth.py"
    )

    login_path = (
        root
        / "app"
        / "templates"
        / "auth"
        / "login.html"
    )

    db_path = (
        root
        / "data"
        / "phocap.db"
    )

    print(
        "BÀI 13B-11-16.2 V2 - "
        "ĐĂNG NHẬP PHÂN CẤP + CHỌN NĂM HỌC"
    )
    print("=" * 100)
    print(f"Dự án: {root}")

    for rel, expected in EXPECTED_NORMALIZED_HASHES.items():
        path = root / rel

        if not path.is_file():
            print(
                f"DỪNG AN TOÀN: thiếu file {rel}"
            )
            return 2

        actual = normalized_sha256(path)

        print(
            f"{rel}: {actual}"
        )

        if actual != expected:
            print()
            print(
                "DỪNG AN TOÀN: mã nguồn đã khác "
                "bản đang được thiết kế."
            )
            print(
                f"File khác: {rel}"
            )
            print(
                "Không tự ghi đè. Hãy gửi lại "
                "ZIP mã nguồn mới nhất."
            )
            return 3

    integrity, fk_count = db_check(
        db_path
    )

    print(
        f"Database integrity_check: {integrity}"
    )
    print(
        f"Database foreign_key_check: {fk_count} lỗi"
    )

    if (
        db_path.is_file()
        and (
            integrity.lower() != "ok"
            or fk_count != 0
        )
    ):
        print(
            "DỪNG AN TOÀN: database chưa đạt kiểm tra."
        )
        return 4

    stamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    backup_dir = (
        root
        / "exports"
        / (
            "backup_truoc_bai_13b_11_16_2_v2_"
            + stamp
        )
    )

    backup_auth = (
        backup_dir
        / "app"
        / "routers"
        / "auth.py"
    )

    backup_login = (
        backup_dir
        / "app"
        / "templates"
        / "auth"
        / "login.html"
    )

    backup_auth.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    backup_login.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    shutil.copy2(
        auth_path,
        backup_auth,
    )

    shutil.copy2(
        login_path,
        backup_login,
    )

    backup_db = None

    if db_path.is_file():
        backup_db = (
            backup_dir
            / "data"
            / "phocap.db"
        )

        backup_db.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        shutil.copy2(
            db_path,
            backup_db,
        )

    print()
    print(
        f"Đã backup: {backup_dir}"
    )

    try:
        auth_path.write_text(
            AUTH_PAYLOAD,
            encoding="utf-8",
        )

        login_path.write_text(
            LOGIN_PAYLOAD,
            encoding="utf-8",
        )

        py_compile.compile(
            str(auth_path),
            doraise=True,
        )

        Environment().parse(
            login_path.read_text(
                encoding="utf-8"
            )
        )

        new_auth_text = auth_path.read_text(
            encoding="utf-8"
        )

        required_markers = (
            '/dang-nhap/api/lua-chon',
            'WORKING_SCHOOL_YEAR_SESSION_KEY',
            'LOGIN_SCOPE_ROLE_CODES',
        )

        for marker in required_markers:
            if marker not in new_auth_text:
                raise RuntimeError(
                    "Thiếu marker sau cài: "
                    + marker
                )

        new_login_text = login_path.read_text(
            encoding="utf-8"
        )

        for marker in (
            'id="cap_dang_nhap"',
            'id="remember-account"',
            'name="school_year_id"',
            'id="account-search"',
        ):
            if marker not in new_login_text:
                raise RuntimeError(
                    "Thiếu thành phần giao diện: "
                    + marker
                )

    except Exception as exc:
        shutil.copy2(
            backup_auth,
            auth_path,
        )

        shutil.copy2(
            backup_login,
            login_path,
        )

        print()
        print(
            "CÀI ĐẶT LỖI - "
            "ĐÃ TỰ KHÔI PHỤC MÃ NGUỒN."
        )
        print(
            f"Lỗi: {exc}"
        )
        return 5

    integrity_after, fk_after = db_check(
        db_path
    )

    report_path = (
        root
        / "exports"
        / (
            "bao_cao_cai_dat_"
            "dang_nhap_phan_cap_v2_"
            + stamp
            + ".txt"
        )
    )

    report = [
        "BÁO CÁO CÀI ĐẶT "
        "BÀI 13B-11-16.2 V2",
        f"Thời gian: {datetime.now():%d/%m/%Y %H:%M:%S}",
        f"Dự án: {root}",
        "",
        "ĐÃ CÀI:",
        "1. Chọn cấp đăng nhập: Sở/Quản trị, Xã/phường, Trường, Giáo viên.",
        "2. Xã/phường: tìm xã -> chọn tài khoản -> nhập mật khẩu.",
        "3. Trường: tìm xã -> tìm trường -> chọn tài khoản -> nhập mật khẩu.",
        "4. Giáo viên: tìm xã -> tìm trường -> tìm giáo viên/tài khoản -> nhập mật khẩu.",
        "5. Chọn Năm học ngay tại màn hình đăng nhập.",
        "6. Năm học được lưu thành Năm học làm việc của phiên.",
        "7. Ghi nhớ cấp/đơn vị/tài khoản/năm học bằng localStorage.",
        "8. Không lưu mật khẩu.",
        "9. Không có mã xác nhận/CAPTCHA.",
        "10. Không thay đổi cấu trúc database.",
        "",
        f"Backup: {backup_dir}",
        f"Database integrity_check sau cài: {integrity_after}",
        f"Database foreign_key_check sau cài: {fk_after} lỗi",
    ]

    report_path.write_text(
        "\n".join(report) + "\n",
        encoding="utf-8-sig",
    )

    print()
    print("=" * 100)
    print(
        "CÀI ĐẶT THÀNH CÔNG"
    )
    print("=" * 100)
    print(
        "Đã sửa đúng 2 file:"
    )
    print(
        " - app/routers/auth.py"
    )
    print(
        " - app/templates/auth/login.html"
    )
    print(
        "Không thay đổi cấu trúc database."
    )
    print(
        f"Báo cáo: {report_path}"
    )
    print()
    print(
        "Hãy khởi động lại Uvicorn "
        "và mở /dang-nhap."
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
