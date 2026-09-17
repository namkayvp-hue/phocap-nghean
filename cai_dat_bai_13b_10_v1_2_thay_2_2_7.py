from __future__ import annotations

import os
import re
import shutil
import traceback
from datetime import datetime
from pathlib import Path

PROJECT = Path(os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")).resolve()
APP = PROJECT / "app"
MENU = APP / "templates" / "partials" / "dropdown_menu_v1.html"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = PROJECT / "exports" / f"backup_bai_13b_10_v1_2_menu_{STAMP}"
BACKUP_MENU = BACKUP / "app" / "templates" / "partials" / "dropdown_menu_v1.html"

OLD_START = "{# === BAI_13B_10_V1_MENU_START === #}"
OLD_END = "{# === BAI_13B_10_V1_MENU_END === #}"

NEW_START = "{# === BAI_13B_10_V1_2_MENU_START === #}"
NEW_END = "{# === BAI_13B_10_V1_2_MENU_END === #}"

OLD_BULK_TEMPLATE = "/dieu-tra/{batch_id}/phan-cong-hang-loat"
XA_ANCHOR_TEMPLATE = "/dieu-tra/{batch_id}/giao-phieu-truong"
SCHOOL_ANCHOR_TEMPLATE = "/dieu-tra/{batch_id}/giao-phieu-giao-vien"

XA_BLOCK = '                                {# === BAI_13B_10_V1_2_MENU_START === #}\n                                {% if menu_role == \'XA\' %}\n                                <a\n                                    href="/dieu-tra/phan-cong-to-dieu-tra/danh-sach-truong"\n                                    role="menuitem"\n                                >\n                                    2.2.7. GV trường gửi về xã/phường\n                                </a>\n                                {% endif %}\n                                {# === BAI_13B_10_V1_2_MENU_END === #}'
SCHOOL_BLOCK = '                                {# === BAI_13B_10_V1_2_SCHOOL_MENU_START === #}\n                                <a\n                                    href="/dieu-tra/phan-cong-to-dieu-tra/giao-vien-tham-gia"\n                                    role="menuitem"\n                                >\n                                    2.2.7. Giáo viên tham gia điều tra\n                                </a>\n                                {# === BAI_13B_10_V1_2_SCHOOL_MENU_END === #}'


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


def remove_old_v1_block(text_value: str) -> str:
    start = text_value.find(OLD_START)
    if start < 0:
        return text_value

    end = text_value.find(OLD_END, start + len(OLD_START))
    if end < 0:
        raise RuntimeError(
            "Có marker START BAI_13B_10_V1 nhưng không tìm thấy marker END."
        )

    end += len(OLD_END)
    return text_value[:start] + text_value[end:]


def remove_old_bulk_links(text_value: str) -> tuple[str, int]:
    pattern = re.compile(
        r'<a\b(?=[^>]*data-batch-template="'
        + re.escape(OLD_BULK_TEMPLATE)
        + r'")[^>]*>.*?</a>',
        flags=re.S | re.I,
    )
    return pattern.subn("", text_value)


def insert_after_link(
    text_value: str,
    *,
    data_template: str,
    block: str,
) -> str:
    pattern = re.compile(
        r'(<a\b(?=[^>]*data-batch-template="'
        + re.escape(data_template)
        + r'")[^>]*>.*?</a>)',
        flags=re.S | re.I,
    )
    matches = list(pattern.finditer(text_value))
    if len(matches) != 1:
        raise RuntimeError(
            f"Cần đúng 1 link anchor {data_template}, tìm thấy {len(matches)}."
        )

    match = matches[0]
    return text_value[:match.end()] + "\n" + block + text_value[match.end():]


def patch_menu(text_value: str) -> tuple[str, int]:
    if (
        "BAI_13B_10_V1_2_SCHOOL_MENU_START" in text_value
        and NEW_START in text_value
    ):
        return text_value, 0

    text_value = remove_old_v1_block(text_value)
    text_value, removed_count = remove_old_bulk_links(text_value)

    text_value = insert_after_link(
        text_value,
        data_template=XA_ANCHOR_TEMPLATE,
        block=XA_BLOCK,
    )

    text_value = insert_after_link(
        text_value,
        data_template=SCHOOL_ANCHOR_TEMPLATE,
        block=SCHOOL_BLOCK,
    )

    return text_value, removed_count


def verify(text_value: str) -> None:
    if OLD_BULK_TEMPLATE in text_value:
        raise RuntimeError("Menu vẫn còn link /phan-cong-hang-loat.")

    required = [
        "2.2.7. Giáo viên tham gia điều tra",
        "/dieu-tra/phan-cong-to-dieu-tra/giao-vien-tham-gia",
        "2.2.7. GV trường gửi về xã/phường",
        "/dieu-tra/phan-cong-to-dieu-tra/danh-sach-truong",
        "BAI_13B_10_V1_2_SCHOOL_MENU_START",
        "BAI_13B_10_V1_2_MENU_START",
    ]

    for marker in required:
        if marker not in text_value:
            raise RuntimeError(f"Thiếu nội dung sau sửa: {marker}")

    if OLD_START in text_value or OLD_END in text_value:
        raise RuntimeError("Khối menu V1 cũ chưa được loại bỏ hoàn toàn.")

    if text_value.count(
        "/dieu-tra/phan-cong-to-dieu-tra/giao-vien-tham-gia"
    ) != 1:
        raise RuntimeError(
            "Link Giáo viên tham gia điều tra không đúng 1 lần."
        )

    if text_value.count(
        "/dieu-tra/phan-cong-to-dieu-tra/danh-sach-truong"
    ) != 1:
        raise RuntimeError(
            "Link GV trường gửi về xã/phường không đúng 1 lần."
        )

    from jinja2 import Environment
    Environment().parse(text_value)


def main() -> int:
    print("=" * 104)
    print("BÀI 13B-10 V1.2 - THAY 2.2.7 CŨ BẰNG QUY TRÌNH TỔ ĐIỀU TRA 3 CẤP")
    print("=" * 104)
    print("")
    print("THEO NGHIỆP VỤ MỚI:")
    print(" - Bỏ mục 2.2.7 Phân công hàng loạt khỏi MENU.")
    print(" - Không xóa route/code cũ để bảo toàn khả năng khôi phục.")
    print(" - Trường: 2.2.7 = Giáo viên tham gia điều tra.")
    print(" - Xã:     2.2.7 = GV trường gửi về xã/phường.")
    print("")
    print("KHÔNG SỬA:")
    print(" - Database.")
    print(" - Router Bài 13B-10 V1.")
    print(" - Access control.")
    print(" - Các mục 2.2.1 đến 2.2.6.")
    print(" - Dữ liệu hộ dân và phân công đã có.")
    print("")

    before = read_text(MENU)
    backup()

    try:
        after, removed_count = patch_menu(before)
        verify(after)

        MENU.write_text(after, encoding="utf-8")
        clear_cache()

        verify(read_text(MENU))

        print("")
        print("CAI DAT BAI 13B-10 V1.2 THANH CONG")
        print("Backup:", BACKUP)
        print(f"Số link 'Phân công hàng loạt' đã bỏ khỏi menu: {removed_count}")
        print("")
        print("KIỂM TRA SAU CÀI:")
        print(" - Trường: 2 -> 2.2 -> 2.2.7 Giáo viên tham gia điều tra")
        print(" - Xã:     2 -> 2.2 -> 2.2.7 GV trường gửi về xã/phường")
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
