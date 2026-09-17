from __future__ import annotations

import re
import shutil
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path

PROJECT = Path(r"C:\PhoCap")
APP = PROJECT / "app"
ROUTER = APP / "routers" / "data_tools.py"
CLEANUP_TEMPLATE = APP / "templates" / "data_tools" / "survey_cleanup.html"
MANAGE_TEMPLATE = APP / "templates" / "data_tools" / "database_backups.html"
EXPORTS = PROJECT / "exports"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = EXPORTS / f"backup_source_bai_13b_10_v3_21_{STAMP}"

MARK_ROUTER = "BAI_13B_10_V3_21_BACKUP_MANAGER"
MARK_BUTTON = "BAI_13B_10_V3_21_BACKUP_MANAGER_BUTTON"
MARK_TEMPLATE = "BAI_13B_10_V3_21_BACKUP_MANAGER_PAGE"

MANAGE_HELPERS = '\n# === BAI_13B_10_V3_21_BACKUP_MANAGER ===\nBACKUP_DELETE_CONFIRM_PHRASE = "XOA BACKUP"\n\n\ndef _backup_manager_context(\n    request: Request,\n    *,\n    manage_status: str = "",\n    selected_backup_name: str = "",\n    error_message: str = "",\n) -> dict[str, Any]:\n    backups = _restore_backup_candidates()\n    total_size_bytes = sum(\n        int(item.get("size_bytes") or 0)\n        for item in backups\n    )\n    newest_name = backups[0]["name"] if backups else ""\n\n    return {\n        "nguoi_dung": _auth_user(request),\n        "backups": backups,\n        "backup_count": len(backups),\n        "total_size": _format_backup_size(total_size_bytes),\n        "newest_backup_name": newest_name,\n        "delete_confirm_phrase": BACKUP_DELETE_CONFIRM_PHRASE,\n        "manage_status": manage_status,\n        "selected_backup_name": selected_backup_name,\n        "error_message": error_message,\n    }\n\n\ndef _delete_system_backup(\n    *,\n    backup_name: str,\n    actor: dict[str, Any],\n) -> str:\n    # Chỉ xóa một thư mục backup hợp lệ trong C:\\PhoCap\\exports.\n    # Không bao giờ chạm DATABASE_PATH hiện tại.\n    backups = _restore_backup_candidates()\n\n    if len(backups) <= 1:\n        raise RuntimeError(\n            "Hệ thống phải giữ lại ít nhất 1 bản backup. "\n            "Hãy tạo một bản Backup mới trước khi xóa."\n        )\n\n    newest_name = backups[0]["name"]\n    if backup_name == newest_name:\n        raise RuntimeError(\n            "Bản backup mới nhất đang được bảo vệ. "\n            "Chỉ xóa các bản cũ. Nếu thật sự cần loại bỏ bản này, "\n            "hãy tạo một bản Backup mới trước."\n        )\n\n    backup_dir, db_path = _resolve_restore_backup(backup_name)\n\n    if Path(DATABASE_PATH).resolve() == db_path.resolve():\n        raise RuntimeError(\n            "Dừng an toàn: đường dẫn backup trùng database hiện tại."\n        )\n\n    export_root = EXPORT_DIR.resolve()\n    resolved_dir = backup_dir.resolve()\n\n    if resolved_dir.parent != export_root:\n        raise RuntimeError(\n            "Dừng an toàn: thư mục cần xóa không nằm trực tiếp trong exports."\n        )\n\n    if backup_dir.is_symlink():\n        raise RuntimeError(\n            "Dừng an toàn: không cho phép xóa backup dạng liên kết."\n        )\n\n    deleted_name = backup_dir.name\n    deleted_size = db_path.stat().st_size if db_path.exists() else 0\n\n    shutil.rmtree(backup_dir)\n\n    try:\n        log_path = EXPORT_DIR / "nhat_ky_quan_ly_backup.jsonl"\n        log_item = {\n            "action": "delete_backup",\n            "deleted_at": datetime.now().isoformat(),\n            "backup_name": deleted_name,\n            "database_size_bytes": int(deleted_size or 0),\n            "actor": {\n                "id": actor.get("id"),\n                "username": actor.get("username"),\n                "full_name": actor.get("full_name"),\n                "role_code": actor.get("role_code"),\n            },\n        }\n        with log_path.open("a", encoding="utf-8") as fh:\n            fh.write(\n                json.dumps(\n                    log_item,\n                    ensure_ascii=False,\n                )\n                + "\\n"\n            )\n    except Exception:\n        pass\n\n    return deleted_name\n'
MANAGE_ROUTES = '\n@router.get(\n    "/don-du-lieu-dieu-tra/backup-quan-ly",\n    response_class=HTMLResponse,\n)\ndef database_backup_manager_page(\n    request: Request,\n    manage_status: str = Query(default=""),\n    backup_name: str = Query(default=""),\n):\n    if not _admin_only(request):\n        return RedirectResponse(\n            url="/?status=forbidden",\n            status_code=303,\n        )\n\n    return templates.TemplateResponse(\n        request=request,\n        name="data_tools/database_backups.html",\n        context=_backup_manager_context(\n            request,\n            manage_status=manage_status,\n            selected_backup_name=backup_name,\n        ),\n    )\n\n\n@router.post(\n    "/don-du-lieu-dieu-tra/backup-quan-ly/xoa",\n    response_class=HTMLResponse,\n)\ndef delete_database_backup(\n    request: Request,\n    backup_name: str = Form(default=""),\n    confirm_scope: str = Form(default=""),\n    confirm_text: str = Form(default=""),\n):\n    if not _admin_only(request):\n        return RedirectResponse(\n            url="/?status=forbidden",\n            status_code=303,\n        )\n\n    if confirm_scope != "yes":\n        return templates.TemplateResponse(\n            request=request,\n            name="data_tools/database_backups.html",\n            context=_backup_manager_context(\n                request,\n                selected_backup_name=backup_name,\n                error_message=(\n                    "Bạn chưa đánh dấu xác nhận xóa bản backup đã chọn."\n                ),\n            ),\n            status_code=400,\n        )\n\n    if confirm_text.strip().upper() != BACKUP_DELETE_CONFIRM_PHRASE:\n        return templates.TemplateResponse(\n            request=request,\n            name="data_tools/database_backups.html",\n            context=_backup_manager_context(\n                request,\n                selected_backup_name=backup_name,\n                error_message=(\n                    "Câu xác nhận chưa đúng. Hãy nhập chính xác: "\n                    + BACKUP_DELETE_CONFIRM_PHRASE\n                ),\n            ),\n            status_code=400,\n        )\n\n    actor = _auth_user(request)\n\n    try:\n        deleted_name = _delete_system_backup(\n            backup_name=backup_name,\n            actor=actor,\n        )\n    except Exception as exc:\n        return templates.TemplateResponse(\n            request=request,\n            name="data_tools/database_backups.html",\n            context=_backup_manager_context(\n                request,\n                selected_backup_name=backup_name,\n                error_message=(\n                    "Không thể xóa bản backup. Chi tiết: "\n                    + str(exc)\n                ),\n            ),\n            status_code=400,\n        )\n\n    return RedirectResponse(\n        url=(\n            "/cong-cu-du-lieu/don-du-lieu-dieu-tra/backup-quan-ly"\n            "?manage_status=deleted"\n            f"&backup_name={deleted_name}"\n        ),\n        status_code=303,\n    )\n'
MANAGE_BUTTON = '\n<!-- === BAI_13B_10_V3_21_BACKUP_MANAGER_BUTTON === -->\n<a\n    href="/cong-cu-du-lieu/don-du-lieu-dieu-tra/backup-quan-ly"\n    style="\n        min-height:46px;\n        box-sizing:border-box;\n        display:inline-flex;\n        align-items:center;\n        justify-content:center;\n        padding:11px 18px;\n        border:1px solid #6c7f93;\n        border-radius:8px;\n        background:#f5f8fb;\n        color:#34495e;\n        text-decoration:none;\n        font-weight:800;\n        white-space:nowrap;\n    "\n>\n    🗂 QUẢN LÝ BACKUP\n</a>\n'
MANAGE_TEMPLATE_CODE = '<!DOCTYPE html>\n<html lang="vi">\n<head>\n    <meta charset="UTF-8">\n    <meta\n        name="viewport"\n        content="width=device-width, initial-scale=1.0"\n    >\n    <title>Quản lý Backup</title>\n    <link rel="stylesheet" href="/static/css/style.css">\n\n    <style>\n        .backup-manager-page {\n            max-width: 1180px;\n            margin: 0 auto;\n            padding: 24px 18px 50px;\n        }\n        .backup-manager-hero {\n            padding: 24px;\n            border-radius: 16px;\n            background: linear-gradient(135deg,#34495e,#607d9a);\n            color: #fff;\n        }\n        .backup-manager-hero h1 {\n            margin: 4px 0 8px;\n            font-size: 30px;\n        }\n        .backup-panel {\n            margin-top: 18px;\n            padding: 20px;\n            border: 1px solid #dfe8f1;\n            border-radius: 14px;\n            background: #fff;\n            box-shadow: 0 8px 24px rgba(24,54,84,.07);\n        }\n        .backup-panel h2 {\n            margin: 0 0 14px;\n            color: #20364d;\n        }\n        .backup-summary {\n            display: grid;\n            grid-template-columns: repeat(3, minmax(0, 1fr));\n            gap: 12px;\n            margin-top: 18px;\n        }\n        .backup-card {\n            padding: 16px;\n            border: 1px solid #dfe8f1;\n            border-radius: 12px;\n            background: #f8fafc;\n        }\n        .backup-card span {\n            display: block;\n            color: #6b7e91;\n            font-size: 12px;\n            font-weight: 800;\n            text-transform: uppercase;\n        }\n        .backup-card strong {\n            display: block;\n            margin-top: 7px;\n            color: #1f5f96;\n            font-size: 25px;\n        }\n        .backup-success {\n            margin-top: 16px;\n            padding: 14px 16px;\n            border: 1px solid #bfe0c6;\n            border-radius: 10px;\n            background: #edf9ef;\n            color: #236533;\n            line-height: 1.55;\n        }\n        .backup-error {\n            margin-top: 16px;\n            padding: 14px 16px;\n            border: 1px solid #efb6b0;\n            border-radius: 10px;\n            background: #fff0ef;\n            color: #a1261c;\n            line-height: 1.55;\n        }\n        .backup-warn {\n            margin-top: 14px;\n            padding: 14px 16px;\n            border: 1px solid #efcf83;\n            border-radius: 10px;\n            background: #fff7df;\n            color: #755100;\n            line-height: 1.55;\n        }\n        .backup-table-wrap {\n            width: 100%;\n            overflow-x: auto;\n        }\n        .backup-table {\n            width: 100%;\n            min-width: 860px;\n            border-collapse: collapse;\n        }\n        .backup-table th,\n        .backup-table td {\n            padding: 11px 12px;\n            border-bottom: 1px solid #e6edf4;\n            text-align: left;\n            vertical-align: middle;\n        }\n        .backup-table th {\n            background: #f7f9fc;\n            color: #526b84;\n            font-size: 12px;\n            text-transform: uppercase;\n        }\n        .backup-newest {\n            display: inline-block;\n            margin-left: 6px;\n            padding: 3px 7px;\n            border-radius: 999px;\n            background: #e7f4ea;\n            color: #236533;\n            font-size: 11px;\n            font-weight: 800;\n        }\n        .backup-protected {\n            color: #236533;\n            font-weight: 800;\n        }\n        .backup-confirm {\n            display: flex;\n            gap: 10px;\n            align-items: flex-start;\n            margin: 14px 0;\n            line-height: 1.5;\n        }\n        .backup-input {\n            width: 100%;\n            min-height: 46px;\n            box-sizing: border-box;\n            padding: 10px 12px;\n            border: 1px solid #cbd8e6;\n            border-radius: 8px;\n            background: #fff;\n        }\n        .backup-danger-button {\n            min-height: 48px;\n            padding: 11px 18px;\n            border: 0;\n            border-radius: 9px;\n            background: #b42318;\n            color: #fff;\n            font-weight: 800;\n            cursor: pointer;\n        }\n        .backup-danger-button:disabled {\n            background: #cfd4da;\n            color: #717981;\n            cursor: not-allowed;\n        }\n        .backup-actions {\n            display: flex;\n            gap: 10px;\n            align-items: center;\n            flex-wrap: wrap;\n        }\n        .backup-link {\n            display: inline-flex;\n            min-height: 44px;\n            box-sizing: border-box;\n            align-items: center;\n            padding: 9px 14px;\n            border: 1px solid #cbd8e6;\n            border-radius: 8px;\n            color: #285a87;\n            text-decoration:none;\n            font-weight:700;\n            background:#fff;\n        }\n        code {\n            overflow-wrap:anywhere;\n        }\n        @media (max-width:760px) {\n            .backup-summary {\n                grid-template-columns:1fr;\n            }\n        }\n    </style>\n</head>\n<body>\n    {% include "partials/dropdown_menu_v1.html" %}\n\n    <main class="backup-manager-page">\n        <!-- === BAI_13B_10_V3_21_BACKUP_MANAGER_PAGE === -->\n        <section class="backup-manager-hero">\n            <div style="font-size:12px;font-weight:800;letter-spacing:.6px;opacity:.9;">\n                DANH MỤC → CÔNG CỤ DỮ LIỆU\n            </div>\n            <h1>🗂 Quản lý các bản Backup</h1>\n            <p style="margin:0;line-height:1.55;">\n                Xem các bản backup database trong <strong>C:\\PhoCap\\exports</strong>,\n                theo dõi dung lượng và xóa các bản cũ khi không còn cần thiết.\n                Database hiện tại <strong>phocap.db không bị thay đổi</strong>\n                bởi chức năng quản lý này.\n            </p>\n        </section>\n\n        {% if manage_status == "deleted" %}\n        <div class="backup-success">\n            <strong>✓ Đã xóa bản Backup thành công.</strong><br>\n            Bản đã xóa: <code>{{ selected_backup_name }}</code>\n        </div>\n        {% endif %}\n\n        {% if error_message %}\n        <div class="backup-error">\n            <strong>Không thể xóa bản Backup.</strong><br>\n            {{ error_message }}\n        </div>\n        {% endif %}\n\n        <section class="backup-summary">\n            <div class="backup-card">\n                <span>Số bản Backup</span>\n                <strong>{{ backup_count }}</strong>\n            </div>\n            <div class="backup-card">\n                <span>Tổng dung lượng database</span>\n                <strong>{{ total_size }}</strong>\n            </div>\n            <div class="backup-card">\n                <span>Bản mới nhất</span>\n                <strong style="font-size:14px;line-height:1.4;">\n                    {% if newest_backup_name %}\n                        {{ newest_backup_name }}\n                    {% else %}\n                        Chưa có\n                    {% endif %}\n                </strong>\n            </div>\n        </section>\n\n        <section class="backup-panel">\n            <h2>1. Danh sách Backup</h2>\n\n            <div class="backup-warn" style="margin-top:0;">\n                <strong>Nguyên tắc an toàn:</strong>\n                bản Backup mới nhất luôn được bảo vệ và không thể xóa tại đây.\n                Hệ thống cũng luôn giữ lại ít nhất 1 bản Backup.\n                Muốn loại bỏ bản đang là mới nhất, hãy tạo một bản Backup mới trước.\n            </div>\n\n            {% if backups %}\n            <form\n                method="post"\n                action="/cong-cu-du-lieu/don-du-lieu-dieu-tra/backup-quan-ly/xoa"\n                onsubmit="return window.confirm(\'XÁC NHẬN XÓA VĨNH VIỄN bản Backup đã chọn?\');"\n            >\n                <div class="backup-table-wrap" style="margin-top:14px;">\n                    <table class="backup-table">\n                        <thead>\n                            <tr>\n                                <th style="width:54px;">Chọn</th>\n                                <th>Thời gian</th>\n                                <th>Loại Backup</th>\n                                <th>Dung lượng</th>\n                                <th>Tên thư mục</th>\n                                <th>Trạng thái</th>\n                            </tr>\n                        </thead>\n                        <tbody>\n                            {% for item in backups %}\n                            <tr>\n                                <td>\n                                    <input\n                                        type="radio"\n                                        name="backup_name"\n                                        value="{{ item.name }}"\n                                        {% if item.name == newest_backup_name %}disabled{% endif %}\n                                        {% if selected_backup_name == item.name %}checked{% endif %}\n                                        required\n                                    >\n                                </td>\n                                <td>{{ item.created_at }}</td>\n                                <td>{{ item.type }}</td>\n                                <td>{{ item.size }}</td>\n                                <td><code>{{ item.name }}</code></td>\n                                <td>\n                                    {% if item.name == newest_backup_name %}\n                                        <span class="backup-protected">🔒 Bảo vệ</span>\n                                        <span class="backup-newest">Mới nhất</span>\n                                    {% else %}\n                                        Có thể xóa\n                                    {% endif %}\n                                </td>\n                            </tr>\n                            {% endfor %}\n                        </tbody>\n                    </table>\n                </div>\n\n                <section class="backup-panel" style="box-shadow:none;margin-top:18px;">\n                    <h2>2. Xác nhận xóa bản cũ</h2>\n\n                    <label class="backup-confirm">\n                        <input\n                            type="checkbox"\n                            name="confirm_scope"\n                            value="yes"\n                            {% if backup_count <= 1 %}disabled{% endif %}\n                            required\n                        >\n                        <span>\n                            Tôi xác nhận đã chọn đúng bản Backup cũ cần xóa.\n                            Tôi hiểu thao tác này xóa vĩnh viễn thư mục Backup đã chọn\n                            nhưng <strong>không xóa database hiện tại</strong>.\n                        </span>\n                    </label>\n\n                    <div style="margin:14px 0 7px;font-weight:700;">\n                        Nhập chính xác câu xác nhận:\n                    </div>\n                    <div style="margin-bottom:8px;font-weight:800;color:#a1261c;">\n                        {{ delete_confirm_phrase }}\n                    </div>\n                    <input\n                        class="backup-input"\n                        type="text"\n                        name="confirm_text"\n                        autocomplete="off"\n                        {% if backup_count <= 1 %}disabled{% endif %}\n                        required\n                    >\n\n                    <div class="backup-actions" style="margin-top:16px;">\n                        <button\n                            class="backup-danger-button"\n                            type="submit"\n                            {% if backup_count <= 1 %}disabled{% endif %}\n                        >\n                            🗑 XÓA BẢN BACKUP ĐÃ CHỌN\n                        </button>\n\n                        <a\n                            class="backup-link"\n                            href="/cong-cu-du-lieu/don-du-lieu-dieu-tra"\n                        >\n                            ← Quay lại Công cụ dữ liệu\n                        </a>\n\n                        <a\n                            class="backup-link"\n                            href="/cong-cu-du-lieu/don-du-lieu-dieu-tra/khoi-phuc"\n                        >\n                            ♻ Mở Khôi phục\n                        </a>\n                    </div>\n                </section>\n            </form>\n            {% else %}\n            <div class="backup-warn">\n                Chưa tìm thấy bản Backup hợp lệ có <code>phocap.db</code>.\n                Hãy quay lại và tạo Backup trước.\n            </div>\n\n            <div class="backup-actions" style="margin-top:16px;">\n                <a\n                    class="backup-link"\n                    href="/cong-cu-du-lieu/don-du-lieu-dieu-tra"\n                >\n                    ← Quay lại Công cụ dữ liệu\n                </a>\n            </div>\n            {% endif %}\n        </section>\n    </main>\n</body>\n</html>\n'


def read_text(path: Path) -> str:
    if not path.exists():
        raise RuntimeError(f"Không tìm thấy: {path}")
    return path.read_text(encoding="utf-8-sig")


def backup_source() -> bool:
    manage_template_existed = MANAGE_TEMPLATE.exists()

    for src in (ROUTER, CLEANUP_TEMPLATE, MANAGE_TEMPLATE):
        if not src.exists():
            continue
        dst = BACKUP / src.relative_to(PROJECT)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    return manage_template_existed


def restore_source(manage_template_existed: bool) -> None:
    for target in (ROUTER, CLEANUP_TEMPLATE):
        src = BACKUP / target.relative_to(PROJECT)
        if src.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, target)

    saved_manage = BACKUP / MANAGE_TEMPLATE.relative_to(PROJECT)

    if manage_template_existed and saved_manage.exists():
        MANAGE_TEMPLATE.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(saved_manage, MANAGE_TEMPLATE)
    elif not manage_template_existed and MANAGE_TEMPLATE.exists():
        MANAGE_TEMPLATE.unlink()


def _ensure_router_shutil_import(text: str) -> str:
    if re.search(r"(?m)^import shutil\s*$", text):
        return text

    future_line = "from __future__ import annotations\n"
    if future_line in text:
        return text.replace(
            future_line,
            future_line + "\nimport shutil\n",
            1,
        )

    first_import = re.search(r"(?m)^(?:import|from)\s+", text)
    if first_import:
        return text[:first_import.start()] + "import shutil\n" + text[first_import.start():]

    return "import shutil\n" + text


def patch_router(text: str) -> str:
    if (
        MARK_ROUTER in text
        and "/don-du-lieu-dieu-tra/backup-quan-ly/xoa" in text
    ):
        return text

    if "BAI_13B_10_V3_20_DATABASE_RESTORE" not in text:
        raise RuntimeError(
            "Chưa phát hiện V3.20/V3.20.1 trong data_tools.py. "
            "Hãy hoàn thành nút Khôi phục trước khi cài V3.21."
        )

    text = _ensure_router_shutil_import(text)

    helper_anchor = "# === BAI_13B_10_V3_20_DATABASE_RESTORE ==="
    helper_pos = text.find(helper_anchor)

    if helper_pos < 0:
        raise RuntimeError(
            "Không tìm thấy helper Restore V3.20 để chèn Quản lý Backup."
        )

    text = text[:helper_pos] + MANAGE_HELPERS + text[helper_pos:]

    route_pattern = re.compile(
        r'(?m)^@router\.get\(\s*\n'
        r'\s*"/don-du-lieu-dieu-tra/khoi-phuc",'
    )
    match = route_pattern.search(text)

    if match is None:
        raise RuntimeError(
            "Không tìm thấy route Khôi phục V3.20 để chèn route Quản lý Backup."
        )

    text = text[:match.start()] + MANAGE_ROUTES + text[match.start():]
    return text


def patch_cleanup_template(text: str) -> str:
    if MARK_BUTTON in text:
        return text

    restore_marker = "<!-- === BAI_13B_10_V3_20_RESTORE_BUTTON === -->"
    marker_pos = text.find(restore_marker)

    if marker_pos < 0:
        raise RuntimeError(
            "Không tìm thấy nút KHÔI PHỤC V3.20 trên màn hình chính."
        )

    close_anchor = text.find("</a>", marker_pos)
    if close_anchor < 0:
        raise RuntimeError(
            "Không xác định được điểm kết thúc nút KHÔI PHỤC."
        )

    close_anchor += len("</a>")

    return (
        text[:close_anchor]
        + "\n"
        + MANAGE_BUTTON
        + text[close_anchor:]
    )


def verify() -> None:
    subprocess.run(
        [sys.executable, "-m", "py_compile", str(ROUTER)],
        cwd=PROJECT,
        check=True,
    )

    from jinja2 import Environment, FileSystemLoader

    env = Environment(
        loader=FileSystemLoader(str(APP / "templates"))
    )
    env.get_template("data_tools/survey_cleanup.html")
    env.get_template("data_tools/database_restore.html")
    env.get_template("data_tools/database_backups.html")

    router_text = read_text(ROUTER)
    cleanup_text = read_text(CLEANUP_TEMPLATE)
    manage_text = read_text(MANAGE_TEMPLATE)

    for item in (
        MARK_ROUTER,
        'BACKUP_DELETE_CONFIRM_PHRASE = "XOA BACKUP"',
        "def _backup_manager_context",
        "def _delete_system_backup",
        '"/don-du-lieu-dieu-tra/backup-quan-ly"',
        '"/don-du-lieu-dieu-tra/backup-quan-ly/xoa"',
        "shutil.rmtree",
        "nhat_ky_quan_ly_backup.jsonl",
        "len(backups) <= 1",
        "backup_name == newest_name",
    ):
        if item not in router_text:
            raise RuntimeError(f"Router V3.21 thiếu: {item}")

    for item in (
        MARK_BUTTON,
        "🗂 QUẢN LÝ BACKUP",
        "/cong-cu-du-lieu/don-du-lieu-dieu-tra/backup-quan-ly",
        "♻ KHÔI PHỤC",
        "💾 BACKUP NGAY",
    ):
        if item not in cleanup_text:
            raise RuntimeError(f"Màn hình chính V3.21 thiếu: {item}")

    for item in (
        MARK_TEMPLATE,
        "🗂 Quản lý các bản Backup",
        "Tổng dung lượng database",
        "🔒 Bảo vệ",
        "{{ delete_confirm_phrase }}",
        "🗑 XÓA BẢN BACKUP ĐÃ CHỌN",
        "không xóa database hiện tại",
    ):
        if item not in manage_text:
            raise RuntimeError(f"Trang Quản lý Backup V3.21 thiếu: {item}")


def clear_cache() -> None:
    for cache in APP.rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(cache, ignore_errors=True)


def main() -> int:
    print("=" * 108)
    print("BÀI 13B-10 V3.21 - QUẢN LÝ CÁC BẢN BACKUP")
    print("=" * 108)
    print()
    print("SẼ THÊM:")
    print(" - Nút 🗂 QUẢN LÝ BACKUP cạnh Backup / Khôi phục.")
    print(" - Danh sách Backup: thời gian, loại, dung lượng, tên thư mục.")
    print(" - Tổng số bản Backup và tổng dung lượng database backup.")
    print(" - Cho phép chọn và xóa BẢN CŨ với xác nhận 'XOA BACKUP'.")
    print(" - Ghi nhật ký xóa vào exports\\nhat_ky_quan_ly_backup.jsonl.")
    print()
    print("AN TOÀN:")
    print(" - CÀI V3.21 KHÔNG xóa backup và KHÔNG thay đổi database.")
    print(" - Chỉ ADMIN/SỞ dùng được, theo đúng Công cụ dữ liệu hiện tại.")
    print(" - Bản Backup mới nhất được bảo vệ, không cho xóa.")
    print(" - Luôn giữ lại ít nhất 1 bản Backup.")
    print(" - Chỉ xóa thư mục backup hợp lệ nằm trực tiếp trong C:\\PhoCap\\exports.")
    print(" - Database hiện tại C:\\PhoCap\\data\\phocap.db không bị chạm.")
    print()

    for path in (ROUTER, CLEANUP_TEMPLATE):
        if not path.exists():
            raise RuntimeError(f"Không tìm thấy: {path}")

    current_router = read_text(ROUTER)
    current_cleanup = read_text(CLEANUP_TEMPLATE)

    if "BAI_13B_10_V3_20_DATABASE_RESTORE" not in current_router:
        raise RuntimeError(
            "Chưa phát hiện V3.20/V3.20.1. Dừng an toàn."
        )

    if "BAI_13B_10_V3_20_RESTORE_BUTTON" not in current_cleanup:
        raise RuntimeError(
            "Chưa phát hiện nút KHÔI PHỤC V3.20. Dừng an toàn."
        )

    EXPORTS.mkdir(parents=True, exist_ok=True)
    BACKUP.mkdir(parents=True, exist_ok=False)

    manage_template_existed = backup_source()
    print("Backup source trước khi cài:", BACKUP)

    try:
        ROUTER.write_text(
            patch_router(current_router),
            encoding="utf-8",
        )

        CLEANUP_TEMPLATE.write_text(
            patch_cleanup_template(current_cleanup),
            encoding="utf-8",
        )

        MANAGE_TEMPLATE.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        MANAGE_TEMPLATE.write_text(
            MANAGE_TEMPLATE_CODE,
            encoding="utf-8",
        )

        verify()
        clear_cache()

        print()
        print("KIỂM TRA SAU CÀI:")
        print(" - Python router: OK")
        print(" - Jinja 3 trang Công cụ dữ liệu: OK")
        print(" - Nút 🗂 QUẢN LÝ BACKUP: OK")
        print(" - Bảo vệ bản mới nhất: OK")
        print(" - Giữ tối thiểu 1 backup: OK")
        print(" - Xóa chỉ trong exports: OK")
        print()
        print("CÀI ĐẶT V3.21 THÀNH CÔNG")
        print()
        print("BƯỚC TIẾP THEO:")
        print(" 1. Khởi động lại Uvicorn.")
        print(" 2. Ctrl+F5 trình duyệt.")
        print(" 3. Bấm 🗂 QUẢN LÝ BACKUP.")
        print(" 4. CHƯA XÓA backup vội; gửi ảnh danh sách để kiểm tra.")
        return 0

    except Exception:
        traceback.print_exc()
        print()
        print("CÓ LỖI - ĐANG KHÔI PHỤC SOURCE TRƯỚC V3.21...")
        restore_source(manage_template_existed)
        clear_cache()
        print("ĐÃ KHÔI PHỤC SOURCE.")
        print("Backup source:", BACKUP)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
