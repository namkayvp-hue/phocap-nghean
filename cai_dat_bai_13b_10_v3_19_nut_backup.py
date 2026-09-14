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
TEMPLATE = APP / "templates" / "data_tools" / "survey_cleanup.html"
EXPORTS = PROJECT / "exports"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = EXPORTS / f"backup_source_bai_13b_10_v3_19_{STAMP}"

MARK_ROUTER = "BAI_13B_10_V3_19_MANUAL_BACKUP"
MARK_TEMPLATE = "BAI_13B_10_V3_19_MANUAL_BACKUP_UI"


BACKUP_HELPER = r'''
# === BAI_13B_10_V3_19_MANUAL_BACKUP ===
def _manual_backup_database(
    *,
    actor: dict[str, Any],
) -> Path:
    """Tạo bản sao đầy đủ phocap.db, không sửa/xóa dữ liệu hiện hành."""
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup_dir = EXPORT_DIR / f"backup_thu_cong_{stamp}"
    backup_dir.mkdir(parents=True, exist_ok=False)

    db_target = backup_dir / "phocap.db"

    src = sqlite3.connect(
        str(DATABASE_PATH),
        timeout=30,
    )
    dst = sqlite3.connect(str(db_target))

    try:
        src.backup(dst)
        dst.commit()
    finally:
        dst.close()
        src.close()

    check = sqlite3.connect(str(db_target))
    try:
        integrity = check.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]

        table_count = check.execute(
            """
            SELECT COUNT(*)
            FROM sqlite_master
            WHERE type='table'
              AND name NOT LIKE 'sqlite_%'
            """
        ).fetchone()[0]
    finally:
        check.close()

    if str(integrity).lower() != "ok":
        raise RuntimeError(
            "Backup thủ công không đạt integrity_check."
        )

    metadata = {
        "backup_type": "manual_full_database",
        "created_at": datetime.now().isoformat(),
        "database_source": str(DATABASE_PATH),
        "database_backup": str(db_target),
        "database_size_bytes": db_target.stat().st_size,
        "table_count": int(table_count or 0),
        "integrity_check": integrity,
        "actor": {
            "id": actor.get("id"),
            "username": actor.get("username"),
            "full_name": actor.get("full_name"),
            "role_code": actor.get("role_code"),
        },
    }

    (backup_dir / "thong_tin_backup.json").write_text(
        json.dumps(
            metadata,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return backup_dir


'''


BACKUP_ROUTE = r'''
@router.post(
    "/don-du-lieu-dieu-tra/backup",
    response_class=HTMLResponse,
)
def manual_survey_backup(
    request: Request,
):
    if not _admin_only(request):
        return RedirectResponse(
            url="/?status=forbidden",
            status_code=303,
        )

    actor = _auth_user(request)

    try:
        backup_dir = _manual_backup_database(
            actor=actor,
        )

        return RedirectResponse(
            url=(
                "/cong-cu-du-lieu/don-du-lieu-dieu-tra"
                "?cleanup_status=backup_success"
                f"&backup_name={backup_dir.name}"
            ),
            status_code=303,
        )

    except Exception as exc:
        context = _cleanup_page_context(
            request,
            school_year_id=None,
            batch_id=None,
            error_message=(
                "Backup dữ liệu KHÔNG thành công. Chi tiết: "
                + str(exc)
            ),
        )
        return templates.TemplateResponse(
            request=request,
            name="data_tools/survey_cleanup.html",
            context=context,
            status_code=500,
        )


'''


BACKUP_UI = r'''
        <!-- === BAI_13B_10_V3_19_MANUAL_BACKUP_UI === -->
        <section class="panel" style="border-color:#b9d8f6;">
            <div style="
                display:flex;
                gap:16px;
                align-items:center;
                justify-content:space-between;
                flex-wrap:wrap;
            ">
                <div style="min-width:260px;flex:1;">
                    <h2 style="margin-bottom:6px;">
                        💾 Backup dữ liệu
                    </h2>
                    <div style="color:#526b84;line-height:1.5;">
                        Tạo ngay một bản sao đầy đủ của
                        <strong>phocap.db</strong> vào thư mục
                        <code>C:\PhoCap\exports</code>.
                        Thao tác này <strong>không xóa</strong> và
                        <strong>không thay đổi</strong> dữ liệu hiện tại.
                    </div>
                </div>

                <form
                    method="post"
                    action="/cong-cu-du-lieu/don-du-lieu-dieu-tra/backup"
                    onsubmit="return window.confirm('Tạo một bản Backup đầy đủ của phocap.db ngay bây giờ?');"
                >
                    <button
                        type="submit"
                        class="button button-primary"
                        style="min-height:46px;padding:11px 18px;font-weight:800;white-space:nowrap;"
                    >
                        💾 BACKUP NGAY
                    </button>
                </form>
            </div>
        </section>

        {% if cleanup_status == "backup_success" %}
        <div class="success">
            <strong>✓ Backup dữ liệu thành công.</strong><br>
            Đã tạo bản sao đầy đủ của <code>phocap.db</code> tại:<br>
            <code>C:\PhoCap\exports\{{ backup_name }}\phocap.db</code>
        </div>
        {% endif %}
'''


def read_text(path: Path) -> str:
    if not path.exists():
        raise RuntimeError(f"Không tìm thấy: {path}")
    return path.read_text(encoding="utf-8-sig")


def backup_source() -> None:
    for src in (ROUTER, TEMPLATE):
        dst = BACKUP / src.relative_to(PROJECT)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def restore_source() -> None:
    for target in (ROUTER, TEMPLATE):
        src = BACKUP / target.relative_to(PROJECT)
        if src.exists():
            shutil.copy2(src, target)


def patch_router(text: str) -> str:
    if MARK_ROUTER in text and "/don-du-lieu-dieu-tra/backup" in text:
        return text

    if "BAI_13B_10_V3_18B6_SCOPE_BY_COMMUNE" not in text:
        raise RuntimeError(
            "data_tools.py chưa ở nền V3.18B6/B6C. "
            "Dừng an toàn, không sửa source."
        )

    helper_anchor = "def _backup_database("
    helper_pos = text.find(helper_anchor)
    if helper_pos < 0:
        raise RuntimeError(
            "Không tìm thấy hàm _backup_database để chèn Backup thủ công."
        )

    text = text[:helper_pos] + BACKUP_HELPER + text[helper_pos:]

    route_pattern = re.compile(
        r'(?m)^@router\.post\(\s*\n'
        r'\s*"/don-du-lieu-dieu-tra/thuc-hien",'
    )
    match = route_pattern.search(text)
    if match is None:
        raise RuntimeError(
            "Không tìm thấy route thực hiện dọn dữ liệu để chèn route Backup."
        )

    text = text[:match.start()] + BACKUP_ROUTE + text[match.start():]
    return text


def patch_template(text: str) -> str:
    if MARK_TEMPLATE in text:
        return text

    if "BAI_13B_10_V3_18B6_SCOPE_UI" not in text:
        raise RuntimeError(
            "survey_cleanup.html chưa ở nền V3.18B6/B6C. "
            "Dừng an toàn, không sửa giao diện."
        )

    main_anchor = '<main class="cleanup-page">'
    main_pos = text.find(main_anchor)
    if main_pos < 0:
        raise RuntimeError("Không tìm thấy khối cleanup-page.")

    hero_pos = text.find('<section class="hero">', main_pos)
    if hero_pos < 0:
        raise RuntimeError("Không tìm thấy khối hero.")

    hero_end = text.find("</section>", hero_pos)
    if hero_end < 0:
        raise RuntimeError("Không tìm thấy cuối khối hero.")

    hero_end += len("</section>")
    text = text[:hero_end] + "\n\n" + BACKUP_UI + text[hero_end:]
    return text


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

    router_text = read_text(ROUTER)
    template_text = read_text(TEMPLATE)

    for item in (
        MARK_ROUTER,
        "def _manual_backup_database",
        '"/don-du-lieu-dieu-tra/backup"',
        "src.backup(dst)",
        "PRAGMA integrity_check",
        "thong_tin_backup.json",
        "cleanup_status=backup_success",
    ):
        if item not in router_text:
            raise RuntimeError(f"Router V3.19 thiếu: {item}")

    for item in (
        MARK_TEMPLATE,
        "💾 Backup dữ liệu",
        "💾 BACKUP NGAY",
        "/cong-cu-du-lieu/don-du-lieu-dieu-tra/backup",
        'cleanup_status == "backup_success"',
        "Backup dữ liệu thành công",
    ):
        if item not in template_text:
            raise RuntimeError(f"Template V3.19 thiếu: {item}")


def clear_cache() -> None:
    for cache in APP.rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(cache, ignore_errors=True)


def main() -> int:
    print("=" * 104)
    print("BÀI 13B-10 V3.19 - THÊM NÚT BACKUP DỮ LIỆU THỦ CÔNG")
    print("=" * 104)
    print()
    print("SẼ THÊM:")
    print(" - Nút 💾 BACKUP NGAY trên màn hình Dọn dẹp dữ liệu điều tra.")
    print(" - Backup đầy đủ file phocap.db bằng SQLite backup API.")
    print(" - Kiểm tra PRAGMA integrity_check sau khi sao lưu.")
    print(" - Ghi thong_tin_backup.json kèm người thực hiện và thời gian.")
    print(" - Chỉ ADMIN/SỞ được sử dụng, theo đúng quyền Công cụ dữ liệu hiện tại.")
    print()
    print("AN TOÀN:")
    print(" - Nút Backup KHÔNG DELETE, KHÔNG UPDATE dữ liệu.")
    print(" - Cơ chế backup bắt buộc trước khi Dọn dữ liệu vẫn GIỮ NGUYÊN.")
    print(" - Source hiện tại được sao lưu trước khi cài và tự rollback nếu có lỗi.")
    print()

    if not ROUTER.exists() or not TEMPLATE.exists():
        raise RuntimeError(
            "Không tìm thấy data_tools.py hoặc survey_cleanup.html."
        )

    current_router = read_text(ROUTER)
    current_template = read_text(TEMPLATE)

    if "BAI_13B_10_V3_18B6_SCOPE_BY_COMMUNE" not in current_router:
        raise RuntimeError(
            "Chưa phát hiện V3.18B6/B6C trong data_tools.py. Dừng an toàn."
        )

    EXPORTS.mkdir(parents=True, exist_ok=True)
    BACKUP.mkdir(parents=True, exist_ok=False)
    backup_source()
    print("Backup source trước khi cài:", BACKUP)

    try:
        ROUTER.write_text(
            patch_router(current_router),
            encoding="utf-8",
        )
        TEMPLATE.write_text(
            patch_template(current_template),
            encoding="utf-8",
        )

        verify()
        clear_cache()

        print()
        print("CÀI ĐẶT V3.19 THÀNH CÔNG")
        print()
        print("BƯỚC TIẾP THEO:")
        print(" 1. Khởi động lại Uvicorn.")
        print(" 2. Trên trình duyệt nhấn Ctrl+F5.")
        print(" 3. Vào Danh mục -> Công cụ dữ liệu -> Dọn dẹp dữ liệu điều tra.")
        print(" 4. Bấm 💾 BACKUP NGAY.")
        print(" 5. Kiểm tra thông báo xanh và thư mục C:\\PhoCap\\exports\\backup_thu_cong_...")
        return 0

    except Exception:
        traceback.print_exc()
        print()
        print("CÓ LỖI - ĐANG KHÔI PHỤC SOURCE TRƯỚC V3.19...")
        restore_source()
        clear_cache()
        print("ĐÃ KHÔI PHỤC SOURCE.")
        print("Backup source:", BACKUP)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
