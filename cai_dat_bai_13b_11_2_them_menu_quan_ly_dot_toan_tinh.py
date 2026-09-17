from __future__ import annotations

import os
import shutil
import traceback
from datetime import datetime
from pathlib import Path

PROJECT = Path(
    os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")
).resolve()

APP = PROJECT / "app"
MENU = APP / "templates" / "partials" / "dropdown_menu_v1.html"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = (
    PROJECT
    / "exports"
    / f"backup_source_bai_13b_11_2_{STAMP}"
)

MARK_START = "{# === BAI_13B_11_2_MENU_START === #}"
MARK_END = "{# === BAI_13B_11_2_MENU_END === #}"

NEW_MENU = '\n                            {# === BAI_13B_11_2_MENU_START === #}\n                            {% if menu_role in [\'ADMIN\', \'SO\'] %}\n                            <a\n                                href="/dieu-tra/quan-ly-dot-toan-tinh"\n                                role="menuitem"\n                            >\n                                2.1.6. Quản lý đợt toàn tỉnh / Xóa an toàn\n                            </a>\n                            {% endif %}\n                            {# === BAI_13B_11_2_MENU_END === #}\n'


def read_text(path: Path) -> str:
    if not path.exists():
        raise RuntimeError(f"Không tìm thấy tệp bắt buộc: {path}")
    return path.read_text(encoding="utf-8-sig")


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def backup() -> None:
    target = BACKUP / MENU.relative_to(PROJECT)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(MENU, target)


def restore() -> None:
    source = BACKUP / MENU.relative_to(PROJECT)
    if source.exists():
        MENU.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, MENU)


def clear_cache() -> None:
    for cache in APP.rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(cache, ignore_errors=True)


def patch(text: str) -> str:
    if MARK_START in text:
        print(" - Menu Bài 13B-11.2 đã có sẵn, không chèn lặp.")
        return text

    required = [
        "2. Điều tra hộ dân",
        "2.1. Đợt điều tra",
        "2.1.5. Trung tâm phiếu điều tra",
    ]
    for marker in required:
        if marker not in text:
            raise RuntimeError(
                "dropdown_menu_v1.html không đúng nền hiện tại. "
                f"Thiếu: {marker}"
            )

    text_pos = text.find("2.1.5. Trung tâm phiếu điều tra")
    anchor_start = text.rfind("<a", 0, text_pos)
    anchor_end = text.find("</a>", text_pos)

    if anchor_start < 0 or anchor_end < 0:
        raise RuntimeError(
            "Không xác định được thẻ <a> của mục 2.1.5. "
            "Dừng an toàn để không phá menu."
        )

    anchor_end += len("</a>")

    return (
        text[:anchor_end]
        + "\n"
        + NEW_MENU.rstrip()
        + text[anchor_end:]
    )


def verify() -> None:
    text = read_text(MENU)

    required = [
        "BAI_13B_11_2_MENU_START",
        "BAI_13B_11_2_MENU_END",
        "/dieu-tra/quan-ly-dot-toan-tinh",
        "2.1.6. Quản lý đợt toàn tỉnh / Xóa an toàn",
        "menu_role in ['ADMIN', 'SO']",
        "2.1.5. Trung tâm phiếu điều tra",
    ]

    for marker in required:
        if marker not in text:
            raise RuntimeError(
                f"Kiểm tra sau cài không đạt: thiếu {marker}"
            )

    if text.count("BAI_13B_11_2_MENU_START") != 1:
        raise RuntimeError("Menu 2.1.6 bị chèn lặp.")

    from jinja2 import Environment, FileSystemLoader

    env = Environment(
        loader=FileSystemLoader(str(APP / "templates"))
    )
    env.get_template("partials/dropdown_menu_v1.html")


def main() -> int:
    print("=" * 94)
    print("BÀI 13B-11.2 - THÊM MENU QUẢN LÝ ĐỢT TOÀN TỈNH")
    print("=" * 94)
    print()
    print("SẼ THÊM:")
    print(" 2. Điều tra hộ dân")
    print("   -> 2.1. Đợt điều tra")
    print("      -> 2.1.6. Quản lý đợt toàn tỉnh / Xóa an toàn")
    print()
    print("PHẠM VI:")
    print(" - Chỉ hiển thị cho ADMIN/Sở.")
    print(" - Link: /dieu-tra/quan-ly-dot-toan-tinh")
    print()
    print("KHÔNG THAY ĐỔI:")
    print(" - Database.")
    print(" - Router Bài 13B-11.")
    print(" - Chức năng tạo/xóa.")
    print(" - Các mục menu 2.1.1 đến 2.1.5.")
    print()

    if not MENU.exists():
        raise RuntimeError(f"Không tìm thấy: {MENU}")

    BACKUP.mkdir(parents=True, exist_ok=False)
    backup()
    print("Backup source:", BACKUP)

    try:
        before = read_text(MENU)
        after = patch(before)
        write_text(MENU, after)

        verify()
        clear_cache()

        print()
        print("KIỂM TRA:")
        print(" - Jinja menu: OK")
        print(" - Mục 2.1.6: OK")
        print(" - Chỉ ADMIN/SO: OK")
        print(" - Không sửa database: OK")
        print()
        print("CÀI ĐẶT BÀI 13B-11.2 THÀNH CÔNG")
        return 0

    except Exception:
        traceback.print_exc()
        print()
        print("CÓ LỖI - ĐANG KHÔI PHỤC MENU...")
        restore()
        clear_cache()
        print("ĐÃ KHÔI PHỤC MENU.")
        print("Database không bị thay đổi.")
        print("Backup source:", BACKUP)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
