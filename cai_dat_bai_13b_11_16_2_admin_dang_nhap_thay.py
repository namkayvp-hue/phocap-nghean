from __future__ import annotations

import argparse
import hashlib
import py_compile
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

EXPECTED_HASHES = {'app/routers/users.py': 'f411fb6ad14c4d148ab3e798a69f5b599dcb48accbf11eec2ec238a25304959f', 'app/routers/auth.py': '6cd381a3a9623d6882fb50051d8e5511138ea2eb00275956ff849108572406b1', 'app/templates/users/list.html': '560af2337dce0d773c478589afff5d6d9681e7e96c7ced85647ef4a47a745694', 'app/templates/partials/dropdown_menu_v1.html': 'b228c4ad62da0b38a029a5b821045541ac6e5bcaf3259ab50c29187128742691'}
INSTALL_MARKER = "BAI_13B_11_16_2_ADMIN_IMPERSONATION"

IMPERSONATION_MODULE = 'from __future__ import annotations\n\nfrom datetime import datetime\nfrom pathlib import Path\nfrom typing import Any\nfrom urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit\n\nfrom fastapi import Request\n\n\nIMPERSONATOR_USER_ID_KEY = "impersonator_user_id"\nIMPERSONATOR_RETURN_TO_KEY = "impersonator_return_to"\nIMPERSONATOR_STARTED_AT_KEY = "impersonator_started_at"\n\nAPP_DIR = Path(__file__).resolve().parent\nAUDIT_PATH = APP_DIR.parent / "data" / "admin_impersonation_audit.log"\n\n\ndef safe_return_to(value: str | None) -> str:\n    value = str(value or "").strip()\n    if not value.startswith("/tai-khoan") or value.startswith("//"):\n        return "/tai-khoan?muc=tra_cuu"\n    return value\n\n\ndef add_status(url: str, status: str) -> str:\n    parts = urlsplit(safe_return_to(url))\n    items = [\n        (key, value)\n        for key, value in parse_qsl(parts.query, keep_blank_values=True)\n        if key != "status"\n    ]\n    items.append(("status", status))\n    return urlunsplit(("", "", parts.path or "/tai-khoan", urlencode(items), parts.fragment))\n\n\ndef write_audit(\n    *,\n    request: Request,\n    action: str,\n    admin_id: int | None,\n    admin_username: str | None,\n    target_id: int | None,\n    target_username: str | None,\n    target_role: str | None = None,\n) -> None:\n    """Chỉ ghi nhật ký phiên đăng nhập thay; không ghi mật khẩu hay dữ liệu biểu mẫu."""\n    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)\n    client = request.client.host if request.client is not None else "-"\n    user_agent = str(request.headers.get("user-agent") or "-")\n    user_agent = " ".join(user_agent.replace("\\r", " ").replace("\\n", " ").split())[:300]\n    line = "\\t".join(\n        [\n            datetime.now().isoformat(timespec="seconds"),\n            str(action or "-"),\n            f"admin_id={admin_id if admin_id is not None else \'-\'}",\n            f"admin={admin_username or \'-\'}",\n            f"target_id={target_id if target_id is not None else \'-\'}",\n            f"target={target_username or \'-\'}",\n            f"target_role={target_role or \'-\'}",\n            f"ip={client}",\n            f"ua={user_agent}",\n        ]\n    )\n    with AUDIT_PATH.open("a", encoding="utf-8") as handle:\n        handle.write(line + "\\n")\n\n\ndef begin_impersonation(\n    request: Request,\n    *,\n    admin_id: int,\n    target_id: int,\n    return_to: str | None,\n) -> None:\n    session = request.session\n    session.pop(IMPERSONATOR_USER_ID_KEY, None)\n    session.pop(IMPERSONATOR_RETURN_TO_KEY, None)\n    session.pop(IMPERSONATOR_STARTED_AT_KEY, None)\n    session[IMPERSONATOR_USER_ID_KEY] = int(admin_id)\n    session[IMPERSONATOR_RETURN_TO_KEY] = safe_return_to(return_to)\n    session[IMPERSONATOR_STARTED_AT_KEY] = datetime.now().isoformat(timespec="seconds")\n    session["user_id"] = int(target_id)\n\n\ndef end_impersonation(request: Request) -> tuple[int | None, str]:\n    session = request.session\n    raw = session.get(IMPERSONATOR_USER_ID_KEY)\n    return_to = safe_return_to(session.get(IMPERSONATOR_RETURN_TO_KEY))\n    try:\n        admin_id = int(raw) if raw is not None else None\n    except (TypeError, ValueError):\n        admin_id = None\n    if admin_id is not None:\n        session["user_id"] = admin_id\n    session.pop(IMPERSONATOR_USER_ID_KEY, None)\n    session.pop(IMPERSONATOR_RETURN_TO_KEY, None)\n    session.pop(IMPERSONATOR_STARTED_AT_KEY, None)\n    return admin_id, return_to\n\n\ndef is_impersonating(request: Request) -> bool:\n    return request.session.get(IMPERSONATOR_USER_ID_KEY) is not None\n'
USERS_IMPORT_INSERT = 'from app.security import ma_hoa_mat_khau\n# === BAI_13B_11_16_2_ADMIN_IMPERSONATION_IMPORT ===\nfrom app.admin_impersonation import begin_impersonation, write_audit\n'
USERS_STATUS_OLD = '    "invalid_reset_password": (\n        "Mật khẩu mới phải có từ 8 đến 128 ký tự và "\n        "không có khoảng trắng ở đầu hoặc cuối."\n    ),\n}'
USERS_STATUS_NEW = '    "invalid_reset_password": (\n        "Mật khẩu mới phải có từ 8 đến 128 ký tự và "\n        "không có khoảng trắng ở đầu hoặc cuối."\n    ),\n    # === BAI_13B_11_16_2_ADMIN_IMPERSONATION_STATUS ===\n    "impersonation_ended": "Đã trở lại tài khoản quản trị Admin.",\n    "impersonation_forbidden": "Chỉ tài khoản Admin/Sở quản trị mới được đăng nhập thay.",\n    "impersonation_locked": "Không thể đăng nhập thay tài khoản đã bị khóa.",\n    "impersonation_admin_target": "Không đăng nhập thay một tài khoản ADMIN khác.",\n    "impersonation_invalid": "Tài khoản cần đăng nhập thay không tồn tại.",\n}'
USERS_ROUTE = '# === BAI_13B_11_16_2_ADMIN_IMPERSONATION_ROUTE ===\n@router.post("/{user_id}/dang-nhap-thay")\ndef dang_nhap_thay_tai_khoan(\n    request: Request,\n    user_id: int,\n    return_to: Annotated[str, Form()] = "/tai-khoan?muc=tra_cuu",\n    db: Session = Depends(get_db),\n):\n    actor = lay_nguoi_dung(request)\n    actor_role = normalize_role_code(actor.get("role_code"))\n    if actor_role not in ADMIN_ROLE_CODES:\n        return chuyen_huong_trang_thai(return_to, "impersonation_forbidden")\n\n    target = db.scalar(\n        select(User)\n        .options(\n            selectinload(User.role),\n            selectinload(User.commune),\n            selectinload(User.school),\n        )\n        .where(User.id == int(user_id))\n    )\n    if target is None or target.role is None:\n        return chuyen_huong_trang_thai(return_to, "impersonation_invalid")\n    if not bool(target.is_active):\n        return chuyen_huong_trang_thai(return_to, "impersonation_locked")\n    if int(target.id) == int(actor.get("id") or 0):\n        return chuyen_huong_trang_thai(return_to, "cannot_self")\n\n    target_role = normalize_role_code(target.role.code)\n    # ADMIN là tài khoản quản trị gốc, không cho giả lập một ADMIN khác.\n    # SO là vai trò Sở cũ nên vẫn được phép là tài khoản đích.\n    if target_role == ADMIN_ROLE_CODE:\n        return chuyen_huong_trang_thai(return_to, "impersonation_admin_target")\n\n    write_audit(\n        request=request,\n        action="START",\n        admin_id=int(actor["id"]),\n        admin_username=str(actor.get("username") or ""),\n        target_id=int(target.id),\n        target_username=str(target.username),\n        target_role=target_role,\n    )\n    begin_impersonation(\n        request,\n        admin_id=int(actor["id"]),\n        target_id=int(target.id),\n        return_to=return_to,\n    )\n    return RedirectResponse(url="/", status_code=303)\n\n\n'
AUTH_IMPORT_INSERT = 'from app.security import kiem_tra_mat_khau\nfrom app.permissions import ADMIN_ROLE_CODES, normalize_role_code\n# === BAI_13B_11_16_2_ADMIN_IMPERSONATION_IMPORT ===\nfrom app.admin_impersonation import (\n    add_status,\n    end_impersonation,\n    is_impersonating,\n    write_audit,\n)\n'
AUTH_NEW_TAIL = '# === BAI_13B_11_16_2_ADMIN_IMPERSONATION_STOP ===\ndef _tro_lai_admin(\n    request: Request,\n    db: Session,\n) -> RedirectResponse | None:\n    if not is_impersonating(request):\n        return None\n\n    current_id_raw = request.session.get("user_id")\n    admin_id_raw = request.session.get("impersonator_user_id")\n    try:\n        current_id = int(current_id_raw) if current_id_raw is not None else None\n        admin_id = int(admin_id_raw) if admin_id_raw is not None else None\n    except (TypeError, ValueError):\n        current_id = None\n        admin_id = None\n\n    admin = (\n        db.scalar(\n            select(User)\n            .options(selectinload(User.role))\n            .where(User.id == admin_id)\n        )\n        if admin_id is not None\n        else None\n    )\n    target = (\n        db.scalar(\n            select(User)\n            .options(selectinload(User.role))\n            .where(User.id == current_id)\n        )\n        if current_id is not None\n        else None\n    )\n\n    if (\n        admin is None\n        or admin.role is None\n        or not admin.is_active\n        or normalize_role_code(admin.role.code) not in ADMIN_ROLE_CODES\n    ):\n        request.session.clear()\n        return RedirectResponse(\n            url="/dang-nhap?status=required",\n            status_code=303,\n        )\n\n    _restored_id, return_to = end_impersonation(request)\n    write_audit(\n        request=request,\n        action="STOP",\n        admin_id=int(admin.id),\n        admin_username=str(admin.username),\n        target_id=(int(target.id) if target is not None else current_id),\n        target_username=(str(target.username) if target is not None else None),\n        target_role=(\n            normalize_role_code(target.role.code)\n            if target is not None and target.role is not None\n            else None\n        ),\n    )\n    return RedirectResponse(\n        url=add_status(return_to, "impersonation_ended"),\n        status_code=303,\n    )\n\n\n@router.post("/thoat-dang-nhap-thay")\ndef thoat_dang_nhap_thay(\n    request: Request,\n    db: Session = Depends(get_db),\n):\n    response = _tro_lai_admin(request, db)\n    if response is not None:\n        return response\n    return RedirectResponse(url="/", status_code=303)\n\n\n@router.post("/dang-xuat")\ndef dang_xuat(\n    request: Request,\n    db: Session = Depends(get_db),\n):\n    """\n    Đăng xuất bình thường. Nếu đang đăng nhập thay thì trở lại Admin,\n    tránh làm mất phiên quản trị gốc.\n    """\n    response = _tro_lai_admin(request, db)\n    if response is not None:\n        return response\n\n    request.session.clear()\n\n    return RedirectResponse(\n        url="/dang-nhap?status=logged_out",\n        status_code=303,\n    )\n'
UNIT_ANCHOR = '<button class="action-button action-copy" type="button" data-copy-username="{{ tai_khoan.username }}">Sao chép TĐN</button>'
UNIT_INSERT_AFTER = '\n                                                {% if nguoi_dung.role_code in [\'ADMIN\', \'SO\'] and tai_khoan.is_active %}\n                                                    <form method="post" action="/tai-khoan/{{ tai_khoan.id }}/dang-nhap-thay" onsubmit="return confirm(\'Đăng nhập thay tài khoản {{ tai_khoan.username }}?\');">\n                                                        <input type="hidden" name="return_to" value="{{ url_bo_loc }}">\n                                                        <button class="action-button action-impersonate" type="submit">🔐 Đăng nhập thay</button>\n                                                    </form>\n                                                {% endif %}'
ROLE_ANCHOR = '                                            {% set ma_vai_tro_muc_tieu = tai_khoan.role.code %}'
ROLE_INSERT_BEFORE = '                                            {% if nguoi_dung.role_code in [\'ADMIN\', \'SO\'] and tai_khoan.is_active and tai_khoan.id != nguoi_dung.id and tai_khoan.role.code != \'ADMIN\' %}\n                                                <form method="post" action="/tai-khoan/{{ tai_khoan.id }}/dang-nhap-thay" onsubmit="return confirm(\'Đăng nhập thay tài khoản {{ tai_khoan.username }}?\');">\n                                                    <input type="hidden" name="return_to" value="{{ url_bo_loc }}">\n                                                    <button class="action-button action-impersonate" type="submit">🔐 Đăng nhập thay</button>\n                                                </form>\n                                            {% endif %}\n\n'
STYLE_INSERT = '        .action-impersonate {\n            background: #e7f0ff !important;\n            color: #0b57a4 !important;\n            border: 1px solid #9fc5ef !important;\n        }\n\n        .action-impersonate:hover {\n            background: #d8eaff !important;\n        }\n\n'
MENU_STYLE_ANCHOR = '.pc-global-nav__logout:hover,\n.pc-global-nav__logout:focus-visible {\n    background: #ffffff;\n    color: #0d47a1;\n    outline: none;\n}\n'
MENU_STYLE_INSERT = '\n/* === BAI_13B_11_16_2_ADMIN_IMPERSONATION_BANNER === */\n.pc-impersonation-banner {\n    display: flex;\n    align-items: center;\n    justify-content: center;\n    gap: 14px;\n    padding: 8px 18px;\n    background: #fff3cd;\n    border-top: 1px solid #ffe08a;\n    border-bottom: 1px solid #e8c55b;\n    color: #664d03;\n    font-size: 13px;\n    font-weight: 700;\n}\n.pc-impersonation-banner form { margin: 0 !important; }\n.pc-impersonation-return {\n    padding: 6px 11px;\n    border: 1px solid #ad7b00;\n    border-radius: 7px;\n    background: #ffffff;\n    color: #704f00;\n    font: inherit;\n    font-size: 12px;\n    font-weight: 800;\n    cursor: pointer;\n}\n.pc-impersonation-return:hover { background: #fff8df; }\n'
MENU_LOGOUT_ANCHOR = '                <form method="post" action="/dang-xuat" class="pc-global-nav__logout-form">\n                    <button type="submit" class="pc-global-nav__logout">Đăng xuất</button>\n                </form>'
MENU_LOGOUT_REPLACEMENT = '                {% if request.session.get(\'impersonator_user_id\') %}\n                    <form method="post" action="/thoat-dang-nhap-thay" class="pc-global-nav__logout-form">\n                        <button type="submit" class="pc-global-nav__logout">Trở lại Admin</button>\n                    </form>\n                {% else %}\n                    <form method="post" action="/dang-xuat" class="pc-global-nav__logout-form">\n                        <button type="submit" class="pc-global-nav__logout">Đăng xuất</button>\n                    </form>\n                {% endif %}'
BAR_ANCHOR = '<div class="pc-global-nav__bar" data-pc-dropdown-menu-v15>'
BANNER_HTML = '{% if request.session.get(\'impersonator_user_id\') %}\n<div class="pc-impersonation-banner">\n    <span>🛡️ ADMIN ĐANG ĐĂNG NHẬP THAY: <strong>{{ menu_user.full_name }}</strong> · {{ menu_user.role_name }} · {{ menu_user.unit_name }}</span>\n    <form method="post" action="/thoat-dang-nhap-thay">\n        <button type="submit" class="pc-impersonation-return">← Quay lại tài khoản Admin</button>\n    </form>\n</div>\n{% endif %}\n\n'


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def find_root(arg_root: str | None) -> Path:
    candidates = []
    if arg_root:
        candidates.append(Path(arg_root))
    candidates.extend([Path.cwd(), Path(r"C:\PhoCap")])
    for item in candidates:
        try:
            item = item.resolve()
        except Exception:
            continue
        if (item / "app" / "main.py").is_file() and (item / "app" / "routers" / "users.py").is_file():
            return item
    raise SystemExit("Không tìm thấy dự án. Hãy chép bộ cài vào C:\\PhoCap và chạy tại C:\\PhoCap.")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: cần đúng 1 vị trí nhưng tìm thấy {count}.")
    return text.replace(old, new, 1)


def db_check(db_path: Path) -> tuple[str, int]:
    if not db_path.is_file():
        return "missing", 0
    conn = sqlite3.connect(str(db_path))
    try:
        integrity = str(conn.execute("PRAGMA integrity_check").fetchone()[0])
        fk_count = len(list(conn.execute("PRAGMA foreign_key_check")))
        return integrity, fk_count
    finally:
        conn.close()


def patch_users(text: str) -> str:
    text = replace_once(
        text,
        "from app.security import ma_hoa_mat_khau\n",
        USERS_IMPORT_INSERT,
        "users import",
    )
    text = replace_once(text, USERS_STATUS_OLD, USERS_STATUS_NEW, "users status")
    anchor = '@router.get("/{user_id}/sua", response_class=HTMLResponse)\n'
    text = replace_once(text, anchor, USERS_ROUTE + anchor, "users impersonation route")
    text = text.replace(
        "from __future__ import annotations\n",
        "from __future__ import annotations\n\n# === BAI_13B_11_16_2_ADMIN_IMPERSONATION ===\n",
        1,
    )
    return text


def patch_auth(text: str) -> str:
    text = replace_once(
        text,
        "from app.security import kiem_tra_mat_khau\n",
        AUTH_IMPORT_INSERT,
        "auth import",
    )
    marker = '@router.post("/dang-xuat")'
    index = text.find(marker)
    if index < 0:
        raise RuntimeError("auth logout: không tìm thấy route /dang-xuat.")
    return text[:index] + AUTH_NEW_TAIL


def patch_users_template(text: str) -> str:
    text = replace_once(
        text,
        UNIT_ANCHOR,
        UNIT_ANCHOR + UNIT_INSERT_AFTER,
        "template unit impersonation button",
    )
    text = replace_once(
        text,
        ROLE_ANCHOR,
        ROLE_INSERT_BEFORE + ROLE_ANCHOR,
        "template all-account impersonation button",
    )
    style_anchor = "        .action-button {\n"
    text = replace_once(
        text,
        style_anchor,
        STYLE_INSERT + style_anchor,
        "template impersonation style",
    )
    return text


def patch_menu(text: str) -> str:
    text = replace_once(
        text,
        MENU_STYLE_ANCHOR,
        MENU_STYLE_ANCHOR + MENU_STYLE_INSERT,
        "menu banner style",
    )
    text = replace_once(
        text,
        MENU_LOGOUT_ANCHOR,
        MENU_LOGOUT_REPLACEMENT,
        "menu logout switch",
    )
    text = replace_once(
        text,
        BAR_ANCHOR,
        BANNER_HTML + BAR_ANCHOR,
        "menu banner markup",
    )
    return text


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=None)
    parser.add_argument("--skip-db", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    root = find_root(args.root)

    users_path = root / "app" / "routers" / "users.py"
    auth_path = root / "app" / "routers" / "auth.py"
    users_template_path = root / "app" / "templates" / "users" / "list.html"
    menu_path = root / "app" / "templates" / "partials" / "dropdown_menu_v1.html"
    module_path = root / "app" / "admin_impersonation.py"
    db_path = root / "data" / "phocap.db"

    print("=" * 100)
    print("BÀI 13B-11-16.2 - ADMIN ĐĂNG NHẬP THAY TÀI KHOẢN")
    print("Từ cấp Sở -> Xã/phường -> Trường -> Giáo viên")
    print("=" * 100)
    print(f"Dự án: {root}")

    if module_path.is_file() and INSTALL_MARKER in users_path.read_text(encoding="utf-8"):
        print("Chức năng đã được cài. Không cài lặp.")
        return 0

    for rel, expected in EXPECTED_HASHES.items():
        path = root / rel
        actual = sha256(path)
        print(f"{rel}: {actual}")
        if actual != expected:
            print("\nDỪNG AN TOÀN: mã nguồn đã khác bản đã khảo sát sau Bài Danh mục lớp 4 cấp.")
            print(f"File khác: {rel}")
            print("Không tự ghi đè. Hãy gửi lại ZIP mã nguồn mới nhất nếu vừa sửa thêm.")
            return 2

    if not args.skip_db:
        integrity, fk_count = db_check(db_path)
        print(f"Database integrity_check: {integrity}")
        print(f"Database foreign_key_check: {fk_count} lỗi")
        if integrity.lower() != "ok" or fk_count != 0:
            print("DỪNG AN TOÀN vì database chưa đạt kiểm tra.")
            return 3

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = root / "exports" / f"backup_truoc_bai_13b_11_16_2_{stamp}"
    backup_dir.mkdir(parents=True, exist_ok=True)

    paths = [users_path, auth_path, users_template_path, menu_path]
    originals = {p: p.read_text(encoding="utf-8") for p in paths}
    module_existed = module_path.exists()
    module_original = module_path.read_text(encoding="utf-8") if module_existed else None

    for path in paths:
        dest = backup_dir / path.relative_to(root)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dest)
    if module_existed:
        dest = backup_dir / module_path.relative_to(root)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(module_path, dest)
    if db_path.is_file():
        dest_db = backup_dir / "data" / "phocap.db"
        dest_db.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(db_path, dest_db)

    try:
        users_path.write_text(patch_users(originals[users_path]), encoding="utf-8")
        auth_path.write_text(patch_auth(originals[auth_path]), encoding="utf-8")
        users_template_path.write_text(patch_users_template(originals[users_template_path]), encoding="utf-8")
        menu_path.write_text(patch_menu(originals[menu_path]), encoding="utf-8")
        module_path.write_text(IMPERSONATION_MODULE, encoding="utf-8")

        for pyfile in [users_path, auth_path, module_path]:
            py_compile.compile(str(pyfile), doraise=True)

        check = subprocess.run(
            [
                sys.executable,
                "-c",
                "from app.routers.auth import router as a; "
                "from app.routers.users import router as u; "
                "print(len(a.routes), len(u.routes))",
            ],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=60,
        )
        if check.returncode != 0:
            raise RuntimeError("Không import được router sau cài: " + (check.stderr or check.stdout))

        from jinja2 import Environment, FileSystemLoader
        env = Environment(loader=FileSystemLoader(str(root / "app" / "templates")))
        env.get_template("users/list.html")
        env.get_template("partials/dropdown_menu_v1.html")

        if not args.skip_db:
            integrity2, fk_count2 = db_check(db_path)
            if integrity2.lower() != "ok" or fk_count2 != 0:
                raise RuntimeError("Database không đạt kiểm tra sau cài.")
    except Exception as exc:
        print("\nCÀI ĐẶT LỖI - ĐANG TỰ KHÔI PHỤC.")
        for path, content in originals.items():
            path.write_text(content, encoding="utf-8")
        if module_existed and module_original is not None:
            module_path.write_text(module_original, encoding="utf-8")
        elif module_path.exists():
            module_path.unlink()
        print("Đã khôi phục mã nguồn về trước khi cài.")
        print("Lỗi:", exc)
        return 4

    report = root / "exports" / f"bao_cao_cai_dat_bai_13b_11_16_2_{stamp}.txt"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(
        "\n".join(
            [
                "BÁO CÁO CÀI ĐẶT BÀI 13B-11-16.2 - ADMIN ĐĂNG NHẬP THAY",
                f"Thời gian: {datetime.now():%d/%m/%Y %H:%M:%S}",
                f"Dự án: {root}",
                f"Backup: {backup_dir}",
                "",
                "ĐÃ CÀI:",
                "1. Admin/SO có nút Đăng nhập thay trên danh sách tài khoản.",
                "2. Không đọc hoặc đổi mật khẩu tài khoản đích.",
                "3. Sau khi chuyển, quyền đúng bằng tài khoản đích.",
                "4. Banner vàng luôn báo đang đăng nhập thay.",
                "5. Nút Trở lại Admin có ở thanh đầu trang.",
                "6. Bấm Đăng xuất trong phiên đăng nhập thay cũng tự trở lại Admin.",
                "7. Không cho đăng nhập thay tài khoản bị khóa.",
                "8. Không cho đăng nhập thay một ADMIN khác; tài khoản SO cấp Sở vẫn được phép là đích.",
                "9. Nhật ký START/STOP lưu tại data/admin_impersonation_audit.log.",
                "10. Không thay đổi cấu trúc database.",
            ]
        )
        + "\n",
        encoding="utf-8-sig",
    )

    print("\n" + "=" * 100)
    print("CÀI ĐẶT THÀNH CÔNG")
    print("=" * 100)
    print(f"Backup: {backup_dir}")
    print(f"Báo cáo: {report}")
    print("Không thay đổi cấu trúc database.")
    print("\nKiểm tra sau cài:")
    print("1. Khởi động lại Uvicorn.")
    print("2. Đăng nhập Admin -> 1. Danh mục -> Tra cứu toàn hệ thống.")
    print("3. Chọn một tài khoản Xã/Trường/Giáo viên đang hoạt động -> Đăng nhập thay.")
    print("4. Kiểm tra banner vàng và đúng quyền/màn hình của tài khoản đích.")
    print("5. Bấm Trở lại Admin.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
