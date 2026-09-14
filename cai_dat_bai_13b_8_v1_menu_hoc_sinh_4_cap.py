from __future__ import annotations

import json
import os
import shutil
import traceback
from datetime import datetime
from pathlib import Path

PROJECT = Path(os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")).resolve()
MENU = PROJECT / "app" / "templates" / "partials" / "dropdown_menu_v1.html"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = PROJECT / "exports" / f"backup_bai_13b_8_v1_menu_hoc_sinh_4_cap_{STAMP}"
MANIFEST = BACKUP / "manifest.json"

MARKER_START = "BAI_13B_8_V1_STUDENT_LEVEL_MENU_START"
MARKER_END = "BAI_13B_8_V1_STUDENT_LEVEL_MENU_END"

OLD_BLOCK = '''            {# 3. HỌC SINH: middleware hiện cho ADMIN/SO quản lý danh sách chính. #}
            {% if menu_role in ['ADMIN', 'SO'] %}
            <div class="pc-menu-group {% if menu_path.startswith('/hoc-sinh') %}is-active{% endif %}">
                <button type="button" class="pc-menu-trigger" aria-expanded="false">3. Học sinh <span class="pc-menu-caret">▾</span></button>
                <div class="pc-dropdown" role="menu">
                    <a href="/hoc-sinh" role="menuitem">3.1. Danh sách học sinh</a>
                    <a href="/hoc-sinh/them" role="menuitem">3.2. Thêm học sinh mới</a>
                </div>
            </div>
            {% endif %}'''

NEW_BLOCK = '''            {# === BAI_13B_8_V1_STUDENT_LEVEL_MENU_START === #}
            {#
                Tách menu Học sinh theo 4 cấp để chuẩn bị nhập dữ liệu:
                MN / TH / THCS / THPT.

                Ở bước V1 này chỉ tổ chức menu và truyền tham số cap.
                Chưa thay đổi database, chưa lọc dữ liệu học sinh theo cấp.
                Bài nhập dữ liệu tiếp theo sẽ dùng chính cap=MN/TH/THCS/THPT.
            #}
            {% if menu_role in ['ADMIN', 'SO'] %}
            <div class="pc-menu-group {% if menu_path.startswith('/hoc-sinh') %}is-active{% endif %}">
                <button type="button" class="pc-menu-trigger" aria-expanded="false">
                    3. Học sinh <span class="pc-menu-caret">▾</span>
                </button>

                <div class="pc-dropdown" role="menu">

                    <div class="pc-submenu">
                        <button type="button" class="pc-submenu-trigger" aria-expanded="false">
                            <span class="pc-submenu-trigger__text">3.1. Mầm non</span>
                            <span class="pc-submenu-arrow">▶</span>
                        </button>
                        <div class="pc-submenu-panel" role="menu">
                            <a href="/hoc-sinh?cap=MN" role="menuitem">
                                3.1.1. Danh sách học sinh Mầm non
                            </a>
                            <a href="/hoc-sinh/them?cap=MN" role="menuitem">
                                3.1.2. Thêm học sinh Mầm non
                            </a>
                        </div>
                    </div>

                    <div class="pc-submenu">
                        <button type="button" class="pc-submenu-trigger" aria-expanded="false">
                            <span class="pc-submenu-trigger__text">3.2. Tiểu học</span>
                            <span class="pc-submenu-arrow">▶</span>
                        </button>
                        <div class="pc-submenu-panel" role="menu">
                            <a href="/hoc-sinh?cap=TH" role="menuitem">
                                3.2.1. Danh sách học sinh Tiểu học
                            </a>
                            <a href="/hoc-sinh/them?cap=TH" role="menuitem">
                                3.2.2. Thêm học sinh Tiểu học
                            </a>
                        </div>
                    </div>

                    <div class="pc-submenu">
                        <button type="button" class="pc-submenu-trigger" aria-expanded="false">
                            <span class="pc-submenu-trigger__text">3.3. THCS</span>
                            <span class="pc-submenu-arrow">▶</span>
                        </button>
                        <div class="pc-submenu-panel" role="menu">
                            <a href="/hoc-sinh?cap=THCS" role="menuitem">
                                3.3.1. Danh sách học sinh THCS
                            </a>
                            <a href="/hoc-sinh/them?cap=THCS" role="menuitem">
                                3.3.2. Thêm học sinh THCS
                            </a>
                        </div>
                    </div>

                    <div class="pc-submenu">
                        <button type="button" class="pc-submenu-trigger" aria-expanded="false">
                            <span class="pc-submenu-trigger__text">3.4. THPT</span>
                            <span class="pc-submenu-arrow">▶</span>
                        </button>
                        <div class="pc-submenu-panel" role="menu">
                            <a href="/hoc-sinh?cap=THPT" role="menuitem">
                                3.4.1. Danh sách học sinh THPT
                            </a>
                            <a href="/hoc-sinh/them?cap=THPT" role="menuitem">
                                3.4.2. Thêm học sinh THPT
                            </a>
                        </div>
                    </div>

                </div>
            </div>
            {% endif %}
            {# === BAI_13B_8_V1_STUDENT_LEVEL_MENU_END === #}'''


def read_text(path: Path) -> str:
    if not path.exists():
        raise RuntimeError(f"Không tìm thấy tệp: {path}")
    return path.read_text(encoding="utf-8-sig")


def backup() -> None:
    BACKUP.mkdir(parents=True, exist_ok=False)
    target = BACKUP / "app" / "templates" / "partials" / "dropdown_menu_v1.html"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(MENU, target)
    MANIFEST.write_text(
        json.dumps(
            {
                "source": str(MENU),
                "backup": str(target),
                "created_at": STAMP,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def restore() -> None:
    source = BACKUP / "app" / "templates" / "partials" / "dropdown_menu_v1.html"
    if source.exists():
        shutil.copy2(source, MENU)


def patch_menu(text: str) -> str:
    if MARKER_START in text:
        return text

    if OLD_BLOCK in text:
        return text.replace(OLD_BLOCK, NEW_BLOCK, 1)

    start_anchor = "{# 3. HỌC SINH:"
    end_anchor = "{# === BAI_13B_5_V1_TEAM_MENU_START === #}"

    start = text.find(start_anchor)
    end = text.find(end_anchor, start + 1) if start >= 0 else -1

    if start < 0 or end < 0 or end <= start:
        raise RuntimeError(
            "Không tìm thấy đúng khối menu Học sinh hiện tại. "
            "Dừng cài để không sửa nhầm menu."
        )

    old_segment = text[start:end]

    required = [
        'href="/hoc-sinh"',
        '3.1. Danh sách học sinh',
        'href="/hoc-sinh/them"',
        '3.2. Thêm học sinh mới',
    ]
    for marker in required:
        if marker not in old_segment:
            raise RuntimeError(
                f"Khối Học sinh hiện tại thiếu marker: {marker}. "
                "Dừng cài để bảo toàn source."
            )

    return text[:start] + NEW_BLOCK.lstrip() + "\n\n            " + text[end:]


def verify(text: str) -> None:
    required = [
        MARKER_START,
        MARKER_END,
        "3.1. Mầm non",
        "3.2. Tiểu học",
        "3.3. THCS",
        "3.4. THPT",
        "/hoc-sinh?cap=MN",
        "/hoc-sinh?cap=TH",
        "/hoc-sinh?cap=THCS",
        "/hoc-sinh?cap=THPT",
        "/hoc-sinh/them?cap=MN",
        "/hoc-sinh/them?cap=THPT",
    ]
    for marker in required:
        if marker not in text:
            raise RuntimeError(f"Kiểm tra sau cài không đạt: {marker}")

    from jinja2 import Environment
    Environment().parse(text)


def clear_cache() -> None:
    app_dir = PROJECT / "app"
    for cache in app_dir.rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(cache, ignore_errors=True)


def main() -> int:
    print("=" * 100)
    print("BÀI 13B-8 V1 - TÁCH MENU HỌC SINH THEO 4 CẤP")
    print("=" * 100)
    print("")
    print("SẼ TẠO:")
    print("  3.1. Mầm non")
    print("      3.1.1. Danh sách học sinh Mầm non")
    print("      3.1.2. Thêm học sinh Mầm non")
    print("  3.2. Tiểu học")
    print("      3.2.1. Danh sách học sinh Tiểu học")
    print("      3.2.2. Thêm học sinh Tiểu học")
    print("  3.3. THCS")
    print("      3.3.1. Danh sách học sinh THCS")
    print("      3.3.2. Thêm học sinh THCS")
    print("  3.4. THPT")
    print("      3.4.1. Danh sách học sinh THPT")
    print("      3.4.2. Thêm học sinh THPT")
    print("")
    print("NGUYÊN TẮC:")
    print(" - Chỉ sửa menu.")
    print(" - Không đổi database.")
    print(" - Không xóa/sửa dữ liệu học sinh hiện có.")
    print(" - Chưa lọc dữ liệu theo cấp ở V1.")
    print(" - Các link đã mang cap=MN/TH/THCS/THPT để dùng ở bài nhập dữ liệu tiếp theo.")
    print("")

    before = read_text(MENU)

    if MARKER_START in before:
        print("BÀI 13B-8 V1 ĐÃ CÓ TRONG MENU - KHÔNG CÀI LẶP.")
        return 0

    backup()

    try:
        after = patch_menu(before)
        verify(after)
        MENU.write_text(after, encoding="utf-8")
        clear_cache()

        print("")
        print("CAI DAT BAI 13B-8 V1 MENU HOC SINH 4 CAP THANH CONG")
        print("Backup:", BACKUP)
        print("")
        print("Tiếp theo:")
        print("  1. Khởi động lại Uvicorn.")
        print("  2. Chrome nhấn Ctrl+F5.")
        print("  3. Mở menu 3. Học sinh và kiểm tra đủ 4 cấp.")
        return 0

    except Exception:
        traceback.print_exc()
        print("")
        print("CÓ LỖI - ĐANG KHÔI PHỤC MENU...")
        restore()
        print("ĐÃ KHÔI PHỤC MENU VỀ TRƯỚC BÀI 13B-8 V1.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
