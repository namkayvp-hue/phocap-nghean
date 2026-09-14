from __future__ import annotations

import os
import re
import shutil
import traceback
from datetime import datetime
from pathlib import Path

PROJECT = Path(os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")).resolve()
MENU = PROJECT / "app" / "templates" / "partials" / "dropdown_menu_v1.html"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = PROJECT / "exports" / f"backup_sua_menu_4_1_1_th_thcs_v1_1_{STAMP}"
BACKUP_MENU = BACKUP / "app" / "templates" / "partials" / "dropdown_menu_v1.html"

START = "{# === FIX_4_1_1_STAFF_LIST_BY_SCHOOL_LEVEL_V1_1_START === #}"
END = "{# === FIX_4_1_1_STAFF_LIST_BY_SCHOOL_LEVEL_V1_1_END === #}"

NEW_BLOCK = '                            {# === FIX_4_1_1_STAFF_LIST_BY_SCHOOL_LEVEL_V1_1_START === #}\n                            {% if menu_role == \'TRUONG\' and menu_school_thcs and not menu_school_liencap %}\n                            <a href="/bieu-nhap/thcs-01-gv#danh-sach-nhan-su" role="menuitem">\n                                4.1.1. Danh sách đội ngũ\n                            </a>\n                            {% elif menu_role == \'TRUONG\' and (menu_school_th or menu_school_liencap) %}\n                            <a href="/bieu-nhap/th-01-gv#danh-sach-nhan-su" role="menuitem">\n                                4.1.1. Danh sách đội ngũ\n                            </a>\n                            {% else %}\n                            <a href="/doi-ngu" role="menuitem">\n                                4.1.1. Danh sách đội ngũ\n                            </a>\n                            {% endif %}\n                            {# === FIX_4_1_1_STAFF_LIST_BY_SCHOOL_LEVEL_V1_1_END === #}'


def read_text(path: Path) -> str:
    if not path.exists():
        raise RuntimeError(f"Không tìm thấy tệp: {path}")
    return path.read_text(encoding="utf-8-sig")


def backup() -> None:
    BACKUP_MENU.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(MENU, BACKUP_MENU)


def restore() -> None:
    if BACKUP_MENU.exists():
        shutil.copy2(BACKUP_MENU, MENU)


def clear_cache() -> None:
    for cache in (PROJECT / "app").rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(cache, ignore_errors=True)


def patch(text_value: str) -> str:
    if START in text_value:
        print(" - V1.1 đã có, không chèn lặp.")
        return text_value

    pattern = re.compile(
        r'<a\s+href="/doi-ngu"\s+role="menuitem">\s*'
        r'4\.1\.1\.\s*Danh sách đội ngũ\s*</a>',
        flags=re.I | re.S,
    )
    matches = list(pattern.finditer(text_value))

    if len(matches) != 1:
        raise RuntimeError(
            "Cần tìm đúng 1 link '4.1.1. Danh sách đội ngũ' trỏ /doi-ngu, "
            f"nhưng tìm thấy {len(matches)}. Dừng để tránh sửa nhầm."
        )

    match = matches[0]
    return text_value[:match.start()] + NEW_BLOCK + text_value[match.end():]


def verify(text_value: str) -> None:
    required = [
        START,
        END,
        "menu_school_thcs",
        "menu_school_th",
        "/bieu-nhap/th-01-gv#danh-sach-nhan-su",
        "/bieu-nhap/thcs-01-gv#danh-sach-nhan-su",
        "4.1.1. Danh sách đội ngũ",
    ]
    for marker in required:
        if marker not in text_value:
            raise RuntimeError(f"Thiếu marker sau cài: {marker}")

    from jinja2 import Environment
    Environment().parse(text_value)


def main() -> int:
    print("=" * 108)
    print("SỬA MENU 4.1.1 DANH SÁCH ĐỘI NGŨ TIỂU HỌC / THCS V1.1")
    print("=" * 108)
    print("")
    print("NGUYÊN NHÂN:")
    print(" - 4.1.1 hiện vẫn trỏ /doi-ngu.")
    print(" - /doi-ngu đang lọc năm 2026-2027 nên TH/THCS chưa có bản ghi năm mới => hiện 0.")
    print(" - Danh sách nhân sự TH/THCS thực tế đã có trong TH-01-GV / THCS-01-GV")
    print("   và đang dùng nguồn tham chiếu 2025-2026.")
    print("")
    print("BẢN SỬA:")
    print(" - Trường Mầm non: 4.1.1 vẫn mở /doi-ngu như hiện tại.")
    print(" - Trường Tiểu học: 4.1.1 mở TH-01-GV và nhảy tới Danh sách nhân sự.")
    print(" - Trường THCS: 4.1.1 mở THCS-01-GV và nhảy tới Danh sách nhân sự.")
    print("")
    print("KHÔNG SỬA database, không sao chép dữ liệu, không tạo tài khoản.")
    print("")

    before = read_text(MENU)
    backup()

    try:
        after = patch(before)
        verify(after)
        MENU.write_text(after, encoding="utf-8")
        clear_cache()
        verify(read_text(MENU))

        print("")
        print("CAI DAT SUA MENU 4.1.1 TH THCS V1.1 THANH CONG")
        print("Backup:", BACKUP)
        print("")
        print("KIỂM TRA:")
        print(" - Tiểu học -> 4. Đội ngũ -> 4.1 Dữ liệu đội ngũ -> 4.1.1 Danh sách đội ngũ")
        print(" - THCS     -> 4. Đội ngũ -> 4.1 Dữ liệu đội ngũ -> 4.1.1 Danh sách đội ngũ")
        print("Hai trường hợp phải mở đúng bảng nhân sự đã có.")
        return 0

    except Exception:
        traceback.print_exc()
        print("")
        print("CÓ LỖI - ĐANG KHÔI PHỤC MENU...")
        restore()
        clear_cache()
        print("ĐÃ KHÔI PHỤC dropdown_menu_v1.html.")
        print("Backup:", BACKUP)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
