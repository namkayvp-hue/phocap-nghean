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
BACKUP = PROJECT / "exports" / f"backup_sua_menu_doi_ngu_th_thcs_v1_{STAMP}"
BACKUP_MENU = BACKUP / "app" / "templates" / "partials" / "dropdown_menu_v1.html"

MARK_TH = "FIX_MENU_STAFF_LIST_TH_V1"
MARK_THCS = "FIX_MENU_STAFF_LIST_THCS_V1"

LINK_TEMPLATE = '                            {# === __MARKER___START === #}\n                            <a\n                                href="/bieu-nhap/__SLUG__#danh-sach-nhan-su"\n                                role="menuitem"\n                            >\n                                __PREFIX__2. Danh sách đội ngũ\n                            </a>\n                            {# === __MARKER___END === #}'


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
    app_dir = PROJECT / "app"
    for cache in app_dir.rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(cache, ignore_errors=True)


def find_submenu_block(text_value: str, label: str) -> tuple[int, int, str]:
    label_pos = text_value.find(label)
    if label_pos < 0:
        raise RuntimeError(f"Không tìm thấy submenu: {label}")

    start = text_value.rfind('<div class="pc-submenu">', 0, label_pos)
    if start < 0:
        raise RuntimeError(f"Không tìm thấy đầu submenu: {label}")

    depth = 0
    token_re = re.compile(r"<div\b|</div>", re.I)

    for match in token_re.finditer(text_value, start):
        token = match.group(0).lower()
        if token.startswith("<div"):
            depth += 1
        else:
            depth -= 1
            if depth == 0:
                end = match.end()
                return start, end, text_value[start:end]

    raise RuntimeError(f"Không tìm thấy cuối submenu: {label}")


def patch_level(
    text_value: str,
    *,
    label: str,
    slug: str,
    number_prefix: str,
    marker: str,
) -> str:
    if marker in text_value:
        return text_value

    start, end, block = find_submenu_block(text_value, label)

    if f"/bieu-nhap/{slug}" not in block:
        raise RuntimeError(
            f"Submenu {label} chưa có route /bieu-nhap/{slug}."
        )

    if "#danh-sach-nhan-su" in block:
        raise RuntimeError(
            f"Submenu {label} đã có link danh sách nhân sự nhưng chưa có marker; "
            "dừng để tránh chèn trùng."
        )

    input_pattern = re.compile(
        r'(<a\b[^>]*href="/bieu-nhap/'
        + re.escape(slug)
        + r'"[^>]*>.*?</a>)',
        flags=re.S | re.I,
    )
    input_match = input_pattern.search(block)
    if input_match is None:
        raise RuntimeError(
            f"Không tìm thấy link nhập dữ liệu /bieu-nhap/{slug} trong {label}."
        )

    # Nếu mục kiểm tra đang là x.2 thì đổi thành x.3.
    block = re.sub(
        rf"{re.escape(number_prefix)}2(\.\s*Kiểm tra dữ liệu đội ngũ)",
        rf"{number_prefix}3\1",
        block,
        count=1,
    )
    block = re.sub(
        rf"{re.escape(number_prefix)}2(\.\s*Kiểm tra dữ liệu)(?!\s*đội ngũ)",
        rf"{number_prefix}3\1",
        block,
        count=1,
    )

    input_match = input_pattern.search(block)
    if input_match is None:
        raise RuntimeError("Không tìm lại được link nhập dữ liệu sau khi đánh số.")

    link = (
        LINK_TEMPLATE
        .replace("__MARKER__", marker)
        .replace("__SLUG__", slug)
        .replace("__PREFIX__", number_prefix)
    )

    block = block[:input_match.end()] + "\n" + link + block[input_match.end():]
    return text_value[:start] + block + text_value[end:]


def patch_menu(text_value: str) -> str:
    text_value = patch_level(
        text_value,
        label="4.2. Tiểu học",
        slug="th-01-gv",
        number_prefix="4.2.",
        marker=MARK_TH,
    )

    text_value = patch_level(
        text_value,
        label="4.3. THCS",
        slug="thcs-01-gv",
        number_prefix="4.3.",
        marker=MARK_THCS,
    )

    return text_value


def verify(text_value: str) -> None:
    required = [
        MARK_TH,
        MARK_THCS,
        "/bieu-nhap/th-01-gv#danh-sach-nhan-su",
        "/bieu-nhap/thcs-01-gv#danh-sach-nhan-su",
        "4.2.2. Danh sách đội ngũ",
        "4.3.2. Danh sách đội ngũ",
    ]
    for marker in required:
        if marker not in text_value:
            raise RuntimeError(f"Kiểm tra sau cài chưa đạt: {marker}")

    if text_value.count(
        "/bieu-nhap/th-01-gv#danh-sach-nhan-su"
    ) != 1:
        raise RuntimeError(
            "Link Danh sách đội ngũ Tiểu học không đúng 1 lần."
        )

    if text_value.count(
        "/bieu-nhap/thcs-01-gv#danh-sach-nhan-su"
    ) != 1:
        raise RuntimeError(
            "Link Danh sách đội ngũ THCS không đúng 1 lần."
        )

    from jinja2 import Environment
    Environment().parse(text_value)


def main() -> int:
    print("=" * 102)
    print("SỬA MENU ĐỘI NGŨ TIỂU HỌC / THCS V1")
    print("=" * 102)
    print("")
    print("ĐÃ XÁC ĐỊNH:")
    print(" - Dữ liệu nhân sự Tiểu học và THCS đã có.")
    print(" - TH-01-GV / THCS-01-GV đã hiển thị danh sách nhân sự.")
    print(" - Chỉ thiếu mục Danh sách đội ngũ trong menu như Mầm non.")
    print("")
    print("BẢN SỬA CHỈ THAY MENU:")
    print(" - 4.2.2. Danh sách đội ngũ -> nhảy thẳng tới bảng nhân sự Tiểu học.")
    print(" - 4.3.2. Danh sách đội ngũ -> nhảy thẳng tới bảng nhân sự THCS.")
    print(" - Mục Kiểm tra dữ liệu cũ đổi số thành 4.2.3 / 4.3.3 nếu cần.")
    print("")
    print("KHÔNG THAY ĐỔI database, dữ liệu giáo viên, Điều tra hộ dân hay tài khoản.")
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
        print("CAI DAT SUA MENU DOI NGU TH THCS V1 THANH CONG")
        print("Backup:", BACKUP)
        print("")
        print("Sau khi khởi động lại:")
        print(" - 4. Đội ngũ -> 4.2 Tiểu học -> 4.2.2 Danh sách đội ngũ")
        print(" - 4. Đội ngũ -> 4.3 THCS -> 4.3.2 Danh sách đội ngũ")
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
