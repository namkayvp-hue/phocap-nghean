from __future__ import annotations

import os
import shutil
import traceback
from datetime import datetime
from pathlib import Path

PROJECT = Path(os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")).resolve()
APP = PROJECT / "app"
MENU = APP / "templates" / "partials" / "dropdown_menu_v1.html"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = PROJECT / "exports" / f"backup_bai_13b_10_v1_1_menu_2_2_8_{STAMP}"
BACKUP_MENU = BACKUP / "app" / "templates" / "partials" / "dropdown_menu_v1.html"

MARK_START = "{# === BAI_13B_10_V1_MENU_START === #}"
MARK_END = "{# === BAI_13B_10_V1_MENU_END === #}"

NEW_BLOCK = '                            {# === BAI_13B_10_V1_MENU_START === #}\n                            {% if menu_role == \'TRUONG\' %}\n                                <a\n                                    href="/dieu-tra/phan-cong-to-dieu-tra/giao-vien-tham-gia"\n                                    role="menuitem"\n                                >\n                                    2.2.8. Giáo viên tham gia điều tra\n                                </a>\n                            {% elif menu_role == \'XA\' %}\n                                <a\n                                    href="/dieu-tra/phan-cong-to-dieu-tra/danh-sach-truong"\n                                    role="menuitem"\n                                >\n                                    2.2.8. GV trường gửi về xã/phường\n                                </a>\n                            {% endif %}\n                            {# === BAI_13B_10_V1_MENU_END === #}'


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
    for cache in APP.rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(cache, ignore_errors=True)


def patch_menu(text_value: str) -> str:
    start = text_value.find(MARK_START)
    end = text_value.find(MARK_END, start + len(MARK_START))

    if start < 0 or end < 0:
        raise RuntimeError(
            "Không tìm thấy nguyên khối BAI_13B_10_V1_MENU hiện tại."
        )

    end += len(MARK_END)

    # Xóa đúng khối 2.2.8 đang bị đặt nhầm bên trong nhánh ADMIN/SO/XA.
    without_old = text_value[:start] + text_value[end:]

    admin_if = "{% if menu_role in ['ADMIN', 'SO', 'XA'] %}"
    school_elif = "{% elif menu_role == 'TRUONG' %}"
    phan_cong_truong_url = (
        'data-batch-template="/dieu-tra/{batch_id}/phan-cong-truong"'
    )
    bulk_url = (
        'data-batch-template="/dieu-tra/{batch_id}/phan-cong-hang-loat"'
    )

    # Tìm đúng nhánh 2.2 thông qua URL phân công trường.
    first_assignment = without_old.find(phan_cong_truong_url)
    if first_assignment < 0:
        raise RuntimeError(
            "Không tìm thấy link phan-cong-truong trong menu 2.2."
        )

    admin_pos = without_old.rfind(admin_if, 0, first_assignment + 1)
    if admin_pos < 0:
        raise RuntimeError(
            "Không xác định được nhánh ADMIN/SO/XA của menu 2.2."
        )

    elif_pos = without_old.find(school_elif, first_assignment)
    if elif_pos < 0:
        raise RuntimeError(
            "Không tìm thấy nhánh TRUONG của menu 2.2."
        )

    second_bulk = without_old.find(bulk_url, elif_pos)
    if second_bulk < 0:
        raise RuntimeError(
            "Không tìm thấy 2.2.7 trong nhánh Trường."
        )

    role_endif = without_old.find("{% endif %}", second_bulk)
    if role_endif < 0:
        raise RuntimeError(
            "Không tìm thấy endif đóng nhánh quyền 2.2."
        )

    insert_at = role_endif + len("{% endif %}")

    return (
        without_old[:insert_at]
        + "\n"
        + NEW_BLOCK
        + without_old[insert_at:]
    )


def verify(text_value: str) -> None:
    if text_value.count(MARK_START) != 1:
        raise RuntimeError("Marker START 2.2.8 không đúng 1 lần.")
    if text_value.count(MARK_END) != 1:
        raise RuntimeError("Marker END 2.2.8 không đúng 1 lần.")

    required = [
        "/dieu-tra/phan-cong-to-dieu-tra/giao-vien-tham-gia",
        "/dieu-tra/phan-cong-to-dieu-tra/danh-sach-truong",
        "2.2.8. Giáo viên tham gia điều tra",
        "2.2.8. GV trường gửi về xã/phường",
    ]
    for marker in required:
        if marker not in text_value:
            raise RuntimeError(
                f"Thiếu nội dung sau sửa: {marker}"
            )

    start = text_value.find(MARK_START)

    # 2.2.8 phải nằm SAU endif đóng nhánh TRUONG.
    role_elif = text_value.rfind(
        "{% elif menu_role == 'TRUONG' %}",
        0,
        start,
    )
    if role_elif < 0:
        raise RuntimeError(
            "Không tìm thấy nhánh TRUONG trước 2.2.8."
        )

    bulk_url = (
        'data-batch-template="/dieu-tra/{batch_id}/phan-cong-hang-loat"'
    )
    second_bulk = text_value.find(bulk_url, role_elif)
    role_endif = text_value.find("{% endif %}", second_bulk)

    if not (
        second_bulk >= 0
        and role_endif >= 0
        and role_endif < start
    ):
        raise RuntimeError(
            "Khối 2.2.8 vẫn đang nằm sai trong nhánh quyền cũ."
        )

    from jinja2 import Environment
    Environment().parse(text_value)


def main() -> int:
    print("=" * 100)
    print("BÀI 13B-10 V1.1 - SỬA HIỂN THỊ MENU 2.2.8")
    print("=" * 100)
    print("")
    print("NGUYÊN NHÂN:")
    print(" - 2.2.8 đã có trong template nhưng bị đặt bên trong")
    print("   nhánh if menu_role in ['ADMIN', 'SO', 'XA'].")
    print(" - Vì vậy tài khoản TRUONG không thể nhìn thấy mục này.")
    print("")
    print("V1.1 CHỈ DI CHUYỂN KHỐI MENU 2.2.8 RA ĐÚNG VỊ TRÍ.")
    print("KHÔNG SỬA database, router, access control hoặc 2.2.1-2.2.7.")
    print("")

    before = read_text(MENU)
    backup()

    try:
        after = patch_menu(before)
        verify(after)

        MENU.write_text(after, encoding="utf-8")
        clear_cache()

        verify(read_text(MENU))

        print("")
        print("CAI DAT BAI 13B-10 V1.1 THANH CONG")
        print("Backup:", BACKUP)
        print("")
        print("Trường phải thấy: 2.2.8 Giáo viên tham gia điều tra")
        print("Xã phải thấy: 2.2.8 GV trường gửi về xã/phường")
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
