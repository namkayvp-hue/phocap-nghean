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
RESTORE_TEMPLATE = APP / "templates" / "data_tools" / "database_restore.html"
EXPORTS = PROJECT / "exports"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = EXPORTS / f"backup_source_bai_13b_10_v3_20_1_{STAMP}"

MARK_ROUTER = "BAI_13B_10_V3_20_DATABASE_RESTORE"
MARK_BUTTON = "BAI_13B_10_V3_20_RESTORE_BUTTON"
MARK_TEMPLATE = "BAI_13B_10_V3_20_RESTORE_PAGE"


RESTORE_HELPERS = r'''
# === BAI_13B_10_V3_20_DATABASE_RESTORE ===
RESTORE_CONFIRM_PHRASE = "KHOI PHUC DU LIEU"
RESTORE_BACKUP_PREFIXES = (
    "backup_thu_cong_",
    "backup_truoc_don_du_lieu_",
    "backup_truoc_khoi_phuc_",
)


def _format_backup_size(num_bytes: int) -> str:
    size = float(num_bytes or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{int(num_bytes or 0)} B"


def _restore_backup_type(name: str) -> str:
    if name.startswith("backup_thu_cong_"):
        return "Backup thủ công"
    if name.startswith("backup_truoc_don_du_lieu_"):
        return "Backup trước khi dọn dữ liệu"
    if name.startswith("backup_truoc_khoi_phuc_"):
        return "Backup an toàn trước lần khôi phục"
    return "Backup dữ liệu"


def _restore_backup_candidates() -> list[dict[str, Any]]:
    """Liệt kê các backup DB hợp lệ do hệ thống tạo trong exports."""
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    result: list[dict[str, Any]] = []

    for folder in EXPORT_DIR.iterdir():
        if not folder.is_dir():
            continue

        name = folder.name
        if not name.startswith(RESTORE_BACKUP_PREFIXES):
            continue

        db_path = folder / "phocap.db"
        if not db_path.is_file():
            continue

        try:
            stat = db_path.stat()
            modified = datetime.fromtimestamp(stat.st_mtime)
        except OSError:
            continue

        result.append(
            {
                "name": name,
                "type": _restore_backup_type(name),
                "created_at": modified.strftime("%d/%m/%Y %H:%M:%S"),
                "size": _format_backup_size(stat.st_size),
                "size_bytes": int(stat.st_size),
                "mtime": float(stat.st_mtime),
                "path": str(db_path),
            }
        )

    result.sort(key=lambda item: item["mtime"], reverse=True)
    return result


def _resolve_restore_backup(backup_name: str) -> tuple[Path, Path]:
    name = str(backup_name or "").strip()
    if not name:
        raise RuntimeError("Bạn chưa chọn bản backup cần khôi phục.")

    if Path(name).name != name or "/" in name or "\\" in name:
        raise RuntimeError("Tên bản backup không hợp lệ.")

    if not name.startswith(RESTORE_BACKUP_PREFIXES):
        raise RuntimeError(
            "Bản backup không thuộc nhóm backup do hệ thống cho phép khôi phục."
        )

    backup_dir = EXPORT_DIR / name
    db_path = backup_dir / "phocap.db"

    if not backup_dir.is_dir() or not db_path.is_file():
        raise RuntimeError(
            "Không tìm thấy phocap.db trong bản backup đã chọn."
        )

    export_root = EXPORT_DIR.resolve()
    resolved_dir = backup_dir.resolve()
    if resolved_dir.parent != export_root:
        raise RuntimeError("Đường dẫn bản backup không hợp lệ.")

    return backup_dir, db_path


def _check_database_file(db_path: Path) -> dict[str, Any]:
    if not db_path.is_file():
        raise RuntimeError(f"Không tìm thấy database: {db_path}")

    con = sqlite3.connect(
        str(db_path),
        timeout=30,
    )
    try:
        integrity = con.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]

        if str(integrity).lower() != "ok":
            raise RuntimeError(
                f"Database không đạt integrity_check: {integrity}"
            )

        foreign_key_rows = con.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()

        if foreign_key_rows:
            raise RuntimeError(
                "Database có lỗi foreign_key_check; không cho phép khôi phục."
            )

        table_count = con.execute(
            """
            SELECT COUNT(*)
            FROM sqlite_master
            WHERE type='table'
              AND name NOT LIKE 'sqlite_%'
            """
        ).fetchone()[0]
    finally:
        con.close()

    if int(table_count or 0) <= 0:
        raise RuntimeError(
            "Database backup không có bảng nghiệp vụ; dừng an toàn."
        )

    return {
        "integrity": str(integrity),
        "foreign_key_check": "ok",
        "table_count": int(table_count or 0),
        "size_bytes": db_path.stat().st_size,
    }


def _backup_before_restore(
    *,
    actor: dict[str, Any],
    selected_backup_name: str,
) -> Path:
    """Backup DB hiện tại trước khi ghi dữ liệu từ bản cũ vào."""
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup_dir = EXPORT_DIR / f"backup_truoc_khoi_phuc_{stamp}"
    backup_dir.mkdir(parents=True, exist_ok=False)
    db_target = backup_dir / "phocap.db"

    src = sqlite3.connect(
        str(DATABASE_PATH),
        timeout=30,
    )
    dst = sqlite3.connect(
        str(db_target),
        timeout=30,
    )

    try:
        src.backup(dst)
        dst.commit()
    finally:
        dst.close()
        src.close()

    check_info = _check_database_file(db_target)

    metadata = {
        "backup_type": "automatic_before_restore",
        "created_at": datetime.now().isoformat(),
        "selected_restore_backup": selected_backup_name,
        "database_source": str(DATABASE_PATH),
        "database_backup": str(db_target),
        "integrity_check": check_info["integrity"],
        "foreign_key_check": check_info["foreign_key_check"],
        "table_count": check_info["table_count"],
        "database_size_bytes": check_info["size_bytes"],
        "actor": {
            "id": actor.get("id"),
            "username": actor.get("username"),
            "full_name": actor.get("full_name"),
            "role_code": actor.get("role_code"),
        },
    }

    (backup_dir / "thong_tin_truoc_khoi_phuc.json").write_text(
        json.dumps(
            metadata,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return backup_dir


def _copy_database_by_sqlite_backup(
    source_db: Path,
    target_db: Path,
) -> None:
    """Ghi toàn bộ source_db vào target_db bằng SQLite Backup API."""
    src = sqlite3.connect(
        str(source_db),
        timeout=30,
    )
    dst = sqlite3.connect(
        str(target_db),
        timeout=30,
    )

    try:
        dst.execute("PRAGMA busy_timeout = 30000")
        src.backup(dst)
        dst.commit()
    finally:
        dst.close()
        src.close()


def _restore_page_context(
    request: Request,
    *,
    restore_status: str = "",
    selected_backup_name: str = "",
    safety_backup_name: str = "",
    error_message: str = "",
) -> dict[str, Any]:
    return {
        "nguoi_dung": _auth_user(request),
        "backups": _restore_backup_candidates(),
        "restore_confirm_phrase": RESTORE_CONFIRM_PHRASE,
        "restore_status": restore_status,
        "selected_backup_name": selected_backup_name,
        "safety_backup_name": safety_backup_name,
        "error_message": error_message,
    }


def _perform_database_restore(
    *,
    actor: dict[str, Any],
    selected_backup_name: str,
) -> tuple[Path, dict[str, Any]]:
    """
    Kiểm tra backup -> backup DB hiện tại -> restore -> kiểm tra lại.
    Nếu restore lỗi sau khi đã chạm DB hiện tại, tự quay lại safety backup.
    """
    _, selected_db = _resolve_restore_backup(selected_backup_name)

    # Bắt buộc kiểm tra bản nguồn trước khi chạm database hiện tại.
    source_info = _check_database_file(selected_db)

    safety_dir = _backup_before_restore(
        actor=actor,
        selected_backup_name=selected_backup_name,
    )
    safety_db = safety_dir / "phocap.db"

    target_touched = False
    try:
        target_touched = True
        _copy_database_by_sqlite_backup(
            selected_db,
            Path(DATABASE_PATH),
        )

        restored_info = _check_database_file(
            Path(DATABASE_PATH)
        )

        log = {
            "restore_type": "full_database_restore",
            "restored_at": datetime.now().isoformat(),
            "selected_backup": selected_backup_name,
            "selected_database": str(selected_db),
            "safety_backup": safety_dir.name,
            "safety_database": str(safety_db),
            "source_check": source_info,
            "restored_check": restored_info,
            "actor": {
                "id": actor.get("id"),
                "username": actor.get("username"),
                "full_name": actor.get("full_name"),
                "role_code": actor.get("role_code"),
            },
        }

        (safety_dir / "nhat_ky_khoi_phuc.json").write_text(
            json.dumps(
                log,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        return safety_dir, restored_info

    except Exception as restore_exc:
        rollback_error = None

        if target_touched and safety_db.is_file():
            try:
                _copy_database_by_sqlite_backup(
                    safety_db,
                    Path(DATABASE_PATH),
                )
                _check_database_file(
                    Path(DATABASE_PATH)
                )
            except Exception as rollback_exc:
                rollback_error = rollback_exc

        if rollback_error is None:
            raise RuntimeError(
                "Khôi phục không thành công. "
                "Hệ thống đã tự quay lại database trước khi khôi phục. "
                f"Chi tiết: {restore_exc}"
            ) from restore_exc

        raise RuntimeError(
            "KHẨN CẤP: Khôi phục lỗi và tự quay lại cũng lỗi. "
            f"Backup an toàn còn tại {safety_db}. "
            f"Lỗi restore: {restore_exc}; "
            f"lỗi rollback: {rollback_error}"
        ) from restore_exc


'''


RESTORE_ROUTES = r'''
@router.get(
    "/don-du-lieu-dieu-tra/khoi-phuc",
    response_class=HTMLResponse,
)
def database_restore_page(
    request: Request,
    restore_status: str = Query(default=""),
    backup_name: str = Query(default=""),
    safety_name: str = Query(default=""),
):
    if not _admin_only(request):
        return RedirectResponse(
            url="/?status=forbidden",
            status_code=303,
        )

    context = _restore_page_context(
        request,
        restore_status=restore_status,
        selected_backup_name=backup_name,
        safety_backup_name=safety_name,
    )

    return templates.TemplateResponse(
        request=request,
        name="data_tools/database_restore.html",
        context=context,
    )


@router.post(
    "/don-du-lieu-dieu-tra/khoi-phuc/thuc-hien",
    response_class=HTMLResponse,
)
def execute_database_restore(
    request: Request,
    backup_name: str = Form(default=""),
    confirm_scope: str = Form(default=""),
    confirm_text: str = Form(default=""),
):
    if not _admin_only(request):
        return RedirectResponse(
            url="/?status=forbidden",
            status_code=303,
        )

    if confirm_scope != "yes":
        context = _restore_page_context(
            request,
            selected_backup_name=backup_name,
            error_message=(
                "Bạn chưa đánh dấu xác nhận đã kiểm tra đúng bản backup "
                "và đã dừng nhập liệu trước khi khôi phục."
            ),
        )
        return templates.TemplateResponse(
            request=request,
            name="data_tools/database_restore.html",
            context=context,
            status_code=400,
        )

    if confirm_text.strip().upper() != RESTORE_CONFIRM_PHRASE:
        context = _restore_page_context(
            request,
            selected_backup_name=backup_name,
            error_message=(
                "Câu xác nhận chưa đúng. Hãy nhập chính xác: "
                + RESTORE_CONFIRM_PHRASE
            ),
        )
        return templates.TemplateResponse(
            request=request,
            name="data_tools/database_restore.html",
            context=context,
            status_code=400,
        )

    actor = _auth_user(request)

    try:
        safety_dir, _ = _perform_database_restore(
            actor=actor,
            selected_backup_name=backup_name,
        )

        return RedirectResponse(
            url=(
                "/cong-cu-du-lieu/don-du-lieu-dieu-tra/khoi-phuc"
                "?restore_status=success"
                f"&backup_name={backup_name}"
                f"&safety_name={safety_dir.name}"
            ),
            status_code=303,
        )

    except Exception as exc:
        context = _restore_page_context(
            request,
            selected_backup_name=backup_name,
            error_message=(
                "Khôi phục dữ liệu KHÔNG thành công. Chi tiết: "
                + str(exc)
            ),
        )
        return templates.TemplateResponse(
            request=request,
            name="data_tools/database_restore.html",
            context=context,
            status_code=500,
        )


'''


RESTORE_BUTTON = r'''
                <!-- === BAI_13B_10_V3_20_RESTORE_BUTTON === -->
                <a
                    href="/cong-cu-du-lieu/don-du-lieu-dieu-tra/khoi-phuc"
                    style="
                        min-height:46px;
                        box-sizing:border-box;
                        display:inline-flex;
                        align-items:center;
                        justify-content:center;
                        padding:11px 18px;
                        border:1px solid #d58b16;
                        border-radius:8px;
                        background:#fff7e8;
                        color:#8a5200;
                        text-decoration:none;
                        font-weight:800;
                        white-space:nowrap;
                    "
                >
                    ♻ KHÔI PHỤC
                </a>
'''


RESTORE_TEMPLATE_CODE = r'''<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta
        name="viewport"
        content="width=device-width, initial-scale=1.0"
    >
    <title>Khôi phục dữ liệu</title>
    <link rel="stylesheet" href="/static/css/style.css">

    <style>
        .restore-page {
            max-width: 1180px;
            margin: 0 auto;
            padding: 24px 18px 50px;
        }
        .restore-hero {
            padding: 24px;
            border-radius: 16px;
            background: linear-gradient(135deg,#8a5200,#d58b16);
            color: #fff;
        }
        .restore-hero h1 {
            margin: 4px 0 8px;
            font-size: 30px;
        }
        .restore-panel {
            margin-top: 18px;
            padding: 20px;
            border: 1px solid #dfe8f1;
            border-radius: 14px;
            background: #fff;
            box-shadow: 0 8px 24px rgba(24,54,84,.07);
        }
        .restore-panel h2 {
            margin: 0 0 14px;
            color: #20364d;
        }
        .restore-warn {
            margin-top: 16px;
            padding: 14px 16px;
            border: 1px solid #efcf83;
            border-radius: 10px;
            background: #fff7df;
            color: #755100;
            line-height: 1.55;
        }
        .restore-success {
            margin-top: 16px;
            padding: 14px 16px;
            border: 1px solid #bfe0c6;
            border-radius: 10px;
            background: #edf9ef;
            color: #236533;
            line-height: 1.55;
        }
        .restore-error {
            margin-top: 16px;
            padding: 14px 16px;
            border: 1px solid #efb6b0;
            border-radius: 10px;
            background: #fff0ef;
            color: #a1261c;
            line-height: 1.55;
        }
        .restore-select,
        .restore-input {
            width: 100%;
            min-height: 46px;
            box-sizing: border-box;
            padding: 10px 12px;
            border: 1px solid #cbd8e6;
            border-radius: 8px;
            background: #fff;
        }
        .restore-backup-table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 14px;
        }
        .restore-backup-table th,
        .restore-backup-table td {
            padding: 10px 12px;
            border-bottom: 1px solid #e6edf4;
            text-align: left;
            vertical-align: top;
        }
        .restore-backup-table th {
            background: #f7f9fc;
            color: #526b84;
            font-size: 12px;
            text-transform: uppercase;
        }
        .restore-confirm {
            display: flex;
            gap: 10px;
            align-items: flex-start;
            margin: 14px 0;
            line-height: 1.5;
        }
        .restore-danger-button {
            min-height: 48px;
            padding: 11px 18px;
            border: 0;
            border-radius: 9px;
            background: #b42318;
            color: #fff;
            font-weight: 800;
            cursor: pointer;
        }
        .restore-danger-button:disabled {
            background: #cfd4da;
            color: #717981;
            cursor: not-allowed;
        }
        .restore-actions {
            display: flex;
            gap: 10px;
            align-items: center;
            flex-wrap: wrap;
        }
        .restore-back-link {
            display: inline-flex;
            min-height: 44px;
            box-sizing: border-box;
            align-items: center;
            padding: 9px 14px;
            border: 1px solid #cbd8e6;
            border-radius: 8px;
            color: #285a87;
            text-decoration: none;
            font-weight: 700;
            background: #fff;
        }
        .restore-path {
            overflow-wrap: anywhere;
        }
        @media (max-width: 760px) {
            .restore-backup-table thead {
                display: none;
            }
            .restore-backup-table,
            .restore-backup-table tbody,
            .restore-backup-table tr,
            .restore-backup-table td {
                display: block;
                width: 100%;
                box-sizing: border-box;
            }
            .restore-backup-table tr {
                padding: 8px 0;
                border-bottom: 1px solid #e6edf4;
            }
            .restore-backup-table td {
                border-bottom: 0;
                padding: 5px 8px;
            }
        }
    </style>
</head>
<body>
    {% include "partials/dropdown_menu_v1.html" %}

    <main class="restore-page">
        <!-- === BAI_13B_10_V3_20_RESTORE_PAGE === -->
        <section class="restore-hero">
            <div style="font-size:12px;font-weight:800;letter-spacing:.6px;opacity:.9;">
                DANH MỤC → CÔNG CỤ DỮ LIỆU
            </div>
            <h1>♻ Khôi phục dữ liệu</h1>
            <p style="margin:0;line-height:1.55;">
                Khôi phục toàn bộ <strong>phocap.db</strong> từ một bản Backup đã có.
                Trước khi ghi dữ liệu, hệ thống sẽ tự tạo thêm một
                <strong>backup an toàn của database hiện tại</strong>.
            </p>
        </section>

        {% if restore_status == "success" %}
        <div class="restore-success">
            <strong>✓ Khôi phục dữ liệu thành công.</strong><br>
            Đã khôi phục từ:
            <code class="restore-path">C:\PhoCap\exports\{{ selected_backup_name }}\phocap.db</code><br>
            Backup an toàn trước khi khôi phục:
            <code class="restore-path">C:\PhoCap\exports\{{ safety_backup_name }}\phocap.db</code><br><br>
            <strong>Hãy khởi động lại Uvicorn</strong> rồi đăng nhập kiểm tra dữ liệu.
        </div>
        {% endif %}

        {% if error_message %}
        <div class="restore-error">
            <strong>Không thể khôi phục dữ liệu.</strong><br>
            {{ error_message }}
        </div>
        {% endif %}

        <div class="restore-warn">
            <strong>⚠ Đây là thao tác thay toàn bộ database hiện tại.</strong>
            Chỉ thực hiện khi đã chọn đúng bản Backup và đã dừng việc nhập/sửa dữ liệu
            trên các máy khác. Bản Backup được chọn sẽ được kiểm tra
            <code>integrity_check</code> và <code>foreign_key_check</code>
            trước khi khôi phục.
        </div>

        <form
            method="post"
            action="/cong-cu-du-lieu/don-du-lieu-dieu-tra/khoi-phuc/thuc-hien"
            onsubmit="return window.confirm('XÁC NHẬN KHÔI PHỤC TOÀN BỘ DATABASE từ bản Backup đã chọn?');"
        >
            <section class="restore-panel">
                <h2>1. Chọn bản Backup</h2>

                {% if backups %}
                <select
                    class="restore-select"
                    name="backup_name"
                    required
                >
                    <option value="">-- Chọn bản Backup cần khôi phục --</option>
                    {% for item in backups %}
                    <option
                        value="{{ item.name }}"
                        {% if selected_backup_name == item.name %}selected{% endif %}
                    >
                        {{ item.created_at }} · {{ item.type }} · {{ item.size }} · {{ item.name }}
                    </option>
                    {% endfor %}
                </select>

                <table class="restore-backup-table">
                    <thead>
                        <tr>
                            <th>Thời gian</th>
                            <th>Loại backup</th>
                            <th>Dung lượng</th>
                            <th>Tên thư mục</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for item in backups %}
                        <tr>
                            <td>{{ item.created_at }}</td>
                            <td>{{ item.type }}</td>
                            <td>{{ item.size }}</td>
                            <td><code>{{ item.name }}</code></td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
                {% else %}
                <div class="restore-warn" style="margin-top:0;">
                    Chưa tìm thấy bản Backup có <code>phocap.db</code> trong
                    <code>C:\PhoCap\exports</code>.
                    Hãy quay lại và bấm <strong>BACKUP NGAY</strong> trước.
                </div>
                {% endif %}
            </section>

            <section class="restore-panel">
                <h2>2. Xác nhận an toàn</h2>

                <label class="restore-confirm">
                    <input
                        type="checkbox"
                        name="confirm_scope"
                        value="yes"
                        {% if not backups %}disabled{% endif %}
                        required
                    >
                    <span>
                        Tôi xác nhận đã chọn đúng bản Backup, hiểu rằng dữ liệu hiện tại
                        sẽ được thay bằng dữ liệu trong bản Backup, và đã dừng nhập/sửa
                        dữ liệu trên các máy khác trước khi khôi phục.
                    </span>
                </label>

                <div style="margin:14px 0 7px;font-weight:700;">
                    Nhập chính xác câu xác nhận:
                </div>
                <div style="margin-bottom:8px;font-weight:800;color:#a1261c;">
                    {{ restore_confirm_phrase }}
                </div>
                <input
                    class="restore-input"
                    type="text"
                    name="confirm_text"
                    autocomplete="off"
                    {% if not backups %}disabled{% endif %}
                    required
                >

                <div class="restore-actions" style="margin-top:16px;">
                    <button
                        class="restore-danger-button"
                        type="submit"
                        {% if not backups %}disabled{% endif %}
                    >
                        ♻ KHÔI PHỤC DỮ LIỆU
                    </button>

                    <a
                        class="restore-back-link"
                        href="/cong-cu-du-lieu/don-du-lieu-dieu-tra"
                    >
                        ← Quay lại
                    </a>
                </div>
            </section>
        </form>
    </main>
</body>
</html>
'''


def read_text(path: Path) -> str:
    if not path.exists():
        raise RuntimeError(f"Không tìm thấy: {path}")
    return path.read_text(encoding="utf-8-sig")


def backup_source() -> bool:
    restore_template_existed = RESTORE_TEMPLATE.exists()

    for src in (ROUTER, CLEANUP_TEMPLATE, RESTORE_TEMPLATE):
        if not src.exists():
            continue
        dst = BACKUP / src.relative_to(PROJECT)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    return restore_template_existed


def restore_source(restore_template_existed: bool) -> None:
    for target in (ROUTER, CLEANUP_TEMPLATE):
        src = BACKUP / target.relative_to(PROJECT)
        if src.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, target)

    saved_restore = BACKUP / RESTORE_TEMPLATE.relative_to(PROJECT)
    if restore_template_existed and saved_restore.exists():
        RESTORE_TEMPLATE.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(saved_restore, RESTORE_TEMPLATE)
    elif not restore_template_existed and RESTORE_TEMPLATE.exists():
        RESTORE_TEMPLATE.unlink()


def patch_router(text: str) -> str:
    if (
        MARK_ROUTER in text
        and "/don-du-lieu-dieu-tra/khoi-phuc/thuc-hien" in text
    ):
        return text

    if "BAI_13B_10_V3_19_MANUAL_BACKUP" not in text:
        raise RuntimeError(
            "Chưa phát hiện V3.19 trong data_tools.py. "
            "Hãy cài và kiểm tra nút Backup V3.19 trước."
        )

    helper_anchor = "# === BAI_13B_10_V3_19_MANUAL_BACKUP ==="
    helper_pos = text.find(helper_anchor)
    if helper_pos < 0:
        raise RuntimeError(
            "Không tìm thấy vị trí helper Backup V3.19 để chèn Restore."
        )

    text = text[:helper_pos] + RESTORE_HELPERS + text[helper_pos:]

    route_pattern = re.compile(
        r'(?m)^@router\.post\(\s*\n'
        r'\s*"/don-du-lieu-dieu-tra/backup",'
    )
    match = route_pattern.search(text)
    if match is None:
        raise RuntimeError(
            "Không tìm thấy route Backup V3.19 để chèn route Khôi phục."
        )

    text = text[:match.start()] + RESTORE_ROUTES + text[match.start():]
    return text


def patch_cleanup_template(text: str) -> str:
    if MARK_BUTTON in text:
        return text

    if "BAI_13B_10_V3_19_MANUAL_BACKUP_UI" not in text:
        raise RuntimeError(
            "Chưa phát hiện giao diện Backup V3.19. Dừng an toàn."
        )

    form_pattern = re.compile(
        r'(<form\s+method="post"\s*\n'
        r'\s*action="/cong-cu-du-lieu/don-du-lieu-dieu-tra/backup"'
        r'.*?</form>)',
        flags=re.S,
    )

    match = form_pattern.search(text)
    if match is None:
        raise RuntimeError(
            "Không tìm thấy form BACKUP NGAY để đặt nút KHÔI PHỤC bên cạnh."
        )

    return (
        text[:match.end()]
        + "\n"
        + RESTORE_BUTTON
        + text[match.end():]
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

    router_text = read_text(ROUTER)
    cleanup_text = read_text(CLEANUP_TEMPLATE)
    restore_text = read_text(RESTORE_TEMPLATE)

    for item in (
        MARK_ROUTER,
        'RESTORE_CONFIRM_PHRASE = "KHOI PHUC DU LIEU"',
        "def _restore_backup_candidates",
        "def _resolve_restore_backup",
        "def _check_database_file",
        "def _backup_before_restore",
        "def _perform_database_restore",
        '"/don-du-lieu-dieu-tra/khoi-phuc"',
        '"/don-du-lieu-dieu-tra/khoi-phuc/thuc-hien"',
        "PRAGMA integrity_check",
        "PRAGMA foreign_key_check",
        "backup_truoc_khoi_phuc_",
        "nhat_ky_khoi_phuc.json",
    ):
        if item not in router_text:
            raise RuntimeError(f"Router V3.20 thiếu: {item}")

    for item in (
        MARK_BUTTON,
        "♻ KHÔI PHỤC",
        "/cong-cu-du-lieu/don-du-lieu-dieu-tra/khoi-phuc",
        "💾 BACKUP NGAY",
    ):
        if item not in cleanup_text:
            raise RuntimeError(f"Màn hình chính V3.20 thiếu: {item}")

    for item in (
        MARK_TEMPLATE,
        "♻ Khôi phục dữ liệu",
        "Backup an toàn trước khi khôi phục",
        "{{ restore_confirm_phrase }}",
        "♻ KHÔI PHỤC DỮ LIỆU",
        "Hãy khởi động lại Uvicorn",
    ):
        if item not in restore_text:
            raise RuntimeError(f"Trang Restore V3.20 thiếu: {item}")


def clear_cache() -> None:
    for cache in APP.rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(cache, ignore_errors=True)


def main() -> int:
    print("=" * 108)
    print("BÀI 13B-10 V3.20.1 - SỬA VERIFY NÚT KHÔI PHỤC DATABASE")
    print("=" * 108)
    print()
    print("SẼ THÊM:")
    print(" - Nút ♻ KHÔI PHỤC đặt cạnh nút 💾 BACKUP NGAY V3.19.")
    print(" - Trang chọn bản Backup theo ngày giờ / loại / dung lượng.")
    print(" - Kiểm tra integrity_check + foreign_key_check trước Restore.")
    print(" - Tự tạo backup_truoc_khoi_phuc_... của DB hiện tại.")
    print(" - Restore toàn bộ phocap.db bằng SQLite Backup API.")
    print(" - Kiểm tra lại DB sau Restore.")
    print(" - Nếu Restore lỗi sau khi chạm DB, tự rollback về backup an toàn.")
    print()
    print("PHÂN QUYỀN:")
    print(" - Giữ đúng quyền Công cụ dữ liệu hiện tại: chỉ ADMIN/SỞ.")
    print()
    print("HOTFIX V3.20.1:")
    print(" - Chỉ sửa bộ verify nhận đúng biến Jinja {{ restore_confirm_phrase }}.")
    print(" - Không thay đổi cơ chế Restore, không tự chạm database khi cài.")
    print()
    print("AN TOÀN:")
    print(" - CÀI V3.20 KHÔNG tự khôi phục và KHÔNG thay đổi database.")
    print(" - Chỉ khi vào trang Khôi phục, chọn backup, đánh dấu xác nhận,")
    print("   nhập đúng 'KHOI PHUC DU LIEU' và bấm nút đỏ thì mới Restore.")
    print(" - Source được backup trước khi cài; lỗi cài đặt sẽ tự rollback source.")
    print()

    if not ROUTER.exists() or not CLEANUP_TEMPLATE.exists():
        raise RuntimeError(
            "Không tìm thấy data_tools.py hoặc survey_cleanup.html."
        )

    current_router = read_text(ROUTER)
    current_cleanup = read_text(CLEANUP_TEMPLATE)

    if "BAI_13B_10_V3_19_MANUAL_BACKUP" not in current_router:
        raise RuntimeError(
            "Chưa phát hiện V3.19. Hãy cài V3.19 và kiểm tra BACKUP NGAY trước."
        )

    EXPORTS.mkdir(parents=True, exist_ok=True)
    BACKUP.mkdir(parents=True, exist_ok=False)
    restore_template_existed = backup_source()
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
        RESTORE_TEMPLATE.parent.mkdir(parents=True, exist_ok=True)
        RESTORE_TEMPLATE.write_text(
            RESTORE_TEMPLATE_CODE,
            encoding="utf-8",
        )

        verify()
        clear_cache()

        print()
        print("CÀI ĐẶT V3.20.1 THÀNH CÔNG")
        print()
        print("BƯỚC TIẾP THEO:")
        print(" 1. Khởi động lại Uvicorn.")
        print(" 2. Trên trình duyệt nhấn Ctrl+F5.")
        print(" 3. Vào Danh mục -> Công cụ dữ liệu -> Dọn dẹp dữ liệu điều tra.")
        print(" 4. Kiểm tra nút ♻ KHÔI PHỤC cạnh 💾 BACKUP NGAY.")
        print(" 5. Bấm KHÔI PHỤC để kiểm tra danh sách Backup.")
        print()
        print("CHƯA CẦN BẤM NÚT ĐỎ KHÔI PHỤC DỮ LIỆU")
        print("cho tới khi đã kiểm tra đúng danh sách backup trên màn hình.")
        return 0

    except Exception:
        traceback.print_exc()
        print()
        print("CÓ LỖI - ĐANG KHÔI PHỤC SOURCE TRƯỚC V3.20...")
        restore_source(restore_template_existed)
        clear_cache()
        print("ĐÃ KHÔI PHỤC SOURCE.")
        print("Backup source:", BACKUP)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
