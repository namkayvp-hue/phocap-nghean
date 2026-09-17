from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path

PROJECT = Path(os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")).resolve()
APP = PROJECT / "app"
MENU = APP / "templates" / "partials" / "dropdown_menu_v1.html"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = PROJECT / "exports" / f"backup_source_bai_13b_11_6_{STAMP}"

OLD_ROLE_SET = "['ADMIN', 'SO', 'PHONG_BAN', 'XA']"
NEW_ROLE_SET = "['ADMIN', 'SO', 'PHONG_BAN']"
MARKER = "BAI_13B_11_6_HIDE_214_215_FOR_XA"


def read_text(path: Path) -> str:
    if not path.exists():
        raise RuntimeError(f"Không tìm thấy tệp bắt buộc: {path}")
    return path.read_text(encoding="utf-8-sig")


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def backup_source() -> None:
    target = BACKUP / MENU.relative_to(PROJECT)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(MENU, target)


def restore_source() -> None:
    source = BACKUP / MENU.relative_to(PROJECT)
    if source.exists():
        MENU.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, MENU)


def clear_cache() -> None:
    for cache in APP.rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(cache, ignore_errors=True)


def patch(text: str) -> str:
    if MARKER in text:
        print(" - Bài 13B-11.6 đã có sẵn, không sửa lặp.")
        return text

    pattern = re.compile(
        r"(?P<indent>[ \t]*)\{%\s*if\s+menu_role\s+in\s+"
        + re.escape(OLD_ROLE_SET)
        + r"\s*%\}"
        r"(?P<body>[\s\S]{0,700}?"
        r'href="/dieu-tra/du-lieu-lich-su"[\s\S]{0,350}?'
        r"2\.1\.4\.\s*Trung tâm dữ liệu lịch sử"
        r"[\s\S]{0,350}?"
        r'href="/dieu-tra/trung-tam-phieu"[\s\S]{0,350}?'
        r"2\.1\.5\.\s*Trung tâm phiếu điều tra)"
    )

    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        raise RuntimeError(
            "Không tìm thấy đúng 1 khối menu 2.1.4/2.1.5 cần sửa. "
            f"Số khối tìm thấy: {len(matches)}"
        )

    m = matches[0]
    indent = m.group("indent")
    body = m.group("body")

    replacement = (
        f"{indent}{{# === {MARKER}_START === #}}\n"
        f"{indent}{{% if menu_role in {NEW_ROLE_SET} %}}"
        f"{body}\n"
        f"{indent}{{# === {MARKER}_END === #}}"
    )

    return text[:m.start()] + replacement + text[m.end():]


def verify_source() -> None:
    text = read_text(MENU)

    required = [
        MARKER + "_START",
        MARKER + "_END",
        "2.1.4. Trung tâm dữ liệu lịch sử",
        "2.1.5. Trung tâm phiếu điều tra",
        'href="/dieu-tra/du-lieu-lich-su"',
        'href="/dieu-tra/trung-tam-phieu"',
        "{% if menu_role in ['ADMIN', 'SO', 'PHONG_BAN'] %}",
        "2.1.1. Danh sách đợt điều tra",
        "2.1.6. Quản lý đợt toàn tỉnh / Xóa an toàn",
    ]
    for marker in required:
        if marker not in text:
            raise RuntimeError(f"Kiểm tra sau cài không đạt, thiếu: {marker}")

    start = text.find(MARKER + "_START")
    end = text.find(MARKER + "_END", start)
    block = text[start:end]
    if "'XA'" in block:
        raise RuntimeError("Khối 2.1.4/2.1.5 vẫn còn quyền XA.")

    for marker in (
        "2.2.4. Nhập Excel cập nhật hộ dân",
        "2.2.5. Trường tham gia và khóa/mở trường",
        "2.2.7. GV trường gửi về xã/phường",
        "2.3.5. Bảng điều hành địa bàn",
    ):
        if marker not in text:
            raise RuntimeError(f"Có dấu hiệu sửa nhầm menu Xã, thiếu: {marker}")

    check_code = (
        "from pathlib import Path\n"
        "from jinja2 import Environment, FileSystemLoader\n"
        "project = Path(r'C:\\\\PhoCap')\n"
        "env = Environment(loader=FileSystemLoader(str(project / 'app' / 'templates')))\n"
        "env.get_template('partials/dropdown_menu_v1.html')\n"
        "print('JINJA_TEMPLATE=OK')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", check_code],
        cwd=PROJECT,
        text=True,
        capture_output=True,
    )
    if result.stdout:
        print(result.stdout.rstrip())
    if result.stderr:
        print(result.stderr.rstrip())
    if result.returncode != 0:
        raise RuntimeError("Jinja template kiểm tra không đạt.")


def main() -> int:
    print("=" * 108)
    print("BÀI 13B-11.6 - ẨN 2.1.4 VÀ 2.1.5 ĐỐI VỚI TÀI KHOẢN XÃ")
    print("=" * 108)
    print()
    print("SẼ SỬA:")
    print(" - Xã KHÔNG còn thấy 2.1.4. Trung tâm dữ liệu lịch sử.")
    print(" - Xã KHÔNG còn thấy 2.1.5. Trung tâm phiếu điều tra.")
    print(" - ADMIN / Sở / Phòng ban vẫn giữ hai mục này.")
    print()
    print("KHÔNG THAY ĐỔI:")
    print(" - Các mục nghiệp vụ Điều tra hộ dân khác.")
    print(" - Route/backend.")
    print(" - Database.")
    print(" - Phân quyền backend hiện có.")
    print()

    if not MENU.exists():
        raise RuntimeError(f"Không tìm thấy: {MENU}")

    BACKUP.mkdir(parents=True, exist_ok=False)
    backup_source()
    print("Backup source:", BACKUP)

    try:
        before = read_text(MENU)
        after = patch(before)
        write_text(MENU, after)
        verify_source()
        clear_cache()

        print()
        print("KIỂM TRA SAU CÀI:")
        print(" - 2.1.4 ẩn với XA: OK")
        print(" - 2.1.5 ẩn với XA: OK")
        print(" - ADMIN/SO/PHONG_BAN vẫn được giữ: OK")
        print(" - Các mục nghiệp vụ Xã khác vẫn còn: OK")
        print(" - Jinja template: OK")
        print(" - Database: KHÔNG THAY ĐỔI")
        print()
        print("CÀI ĐẶT BÀI 13B-11.6 THÀNH CÔNG")
        return 0

    except Exception:
        traceback.print_exc()
        print()
        print("CÓ LỖI - ĐANG KHÔI PHỤC MENU...")
        restore_source()
        clear_cache()
        print("ĐÃ KHÔI PHỤC SOURCE.")
        print("Database không bị thay đổi.")
        print("Backup source:", BACKUP)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
