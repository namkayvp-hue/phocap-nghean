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

STAFF_ROUTER = APP / "routers" / "staff_management.py"
MENU = APP / "templates" / "partials" / "dropdown_menu_v1.html"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = PROJECT / "exports" / f"backup_sua_cap_truong_v1_{STAMP}"

MARKER = "FIX_CAP_TRUONG_V1_SCHOOL_LEVEL_START"


def read_text(path: Path) -> str:
    if not path.exists():
        raise RuntimeError(f"Không tìm thấy tệp bắt buộc: {path}")
    return path.read_text(encoding="utf-8-sig")


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def backup_file(path: Path) -> None:
    rel = path.relative_to(PROJECT)
    dst = BACKUP / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, dst)


def restore_file(path: Path) -> None:
    rel = path.relative_to(PROJECT)
    src = BACKUP / rel
    if src.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, path)


def patch_staff_router(text: str) -> str:
    # Lỗi 500 hiện tại:
    # staff/list.html dùng teaching_level_labels và qualification_level_labels,
    # nhưng route /doi-ngu chưa truyền 2 biến này vào context Jinja.
    if (
        '"teaching_level_labels": TEACHING_LEVEL_LABELS' in text
        and '"qualification_level_labels": QUALIFICATION_LEVEL_LABELS' in text
    ):
        return text

    old = (
        '"teaching_age_labels": TEACHING_AGE_LABELS,\n'
        '            "qualification_standard_labels": QUALIFICATION_STANDARD_LABELS,'
    )
    new = (
        '"teaching_age_labels": TEACHING_AGE_LABELS,\n'
        '            "teaching_level_labels": TEACHING_LEVEL_LABELS,\n'
        '            "qualification_level_labels": QUALIFICATION_LEVEL_LABELS,\n'
        '            "qualification_standard_labels": QUALIFICATION_STANDARD_LABELS,'
    )

    if old not in text:
        raise RuntimeError(
            "Không tìm thấy đúng vị trí truyền dữ liệu cho staff/list.html. "
            "Dừng cài để không sửa nhầm source."
        )

    return text.replace(old, new, 1)


def find_matching_div_end(text: str, start: int) -> int:
    tag_re = re.compile(r"<div\b[^>]*>|</div>")
    depth = 0

    for match in tag_re.finditer(text, start):
        tag = match.group(0)
        if tag.startswith("<div"):
            depth += 1
        else:
            depth -= 1
            if depth == 0:
                return match.end()

    raise RuntimeError("Không xác định được điểm kết thúc khối menu.")


def wrap_report_submenu(
    text: str,
    label: str,
    condition: str,
    marker_name: str,
) -> str:
    if f"{marker_name}_START" in text:
        return text

    pos = text.find(label)
    if pos < 0:
        raise RuntimeError(f"Không tìm thấy menu báo cáo: {label}")

    start = text.rfind('<div class="pc-submenu">', 0, pos)
    if start < 0:
        raise RuntimeError(f"Không tìm thấy đầu submenu: {label}")

    end = find_matching_div_end(text, start)
    block = text[start:end]

    wrapped = (
        f"{{# === {marker_name}_START === #}}\n"
        f"                    {{% if {condition} %}}\n"
        f"{block}\n"
        f"                    {{% endif %}}\n"
        f"                    {{# === {marker_name}_END === #}}"
    )
    return text[:start] + wrapped + text[end:]


def patch_menu(text: str) -> str:
    if MARKER in text:
        print(" - Menu cấp trường đã có FIX_CAP_TRUONG_V1, không chèn lặp.")
        return text

    path_anchor = "{% set menu_path = request.url.path if request is defined else '/' %}"
    if path_anchor not in text:
        raise RuntimeError("Không tìm thấy menu_path trong dropdown_menu_v1.html.")

    level_block = r"""{% set menu_path = request.url.path if request is defined else '/' %}
    {# === FIX_CAP_TRUONG_V1_SCHOOL_LEVEL_START === #}
    {% set menu_unit_lower = (menu_user.unit_name or '')|lower %}
    {% set menu_school_mn = (
        'mầm non' in menu_unit_lower
        or 'mẫu giáo' in menu_unit_lower
        or 'nhóm trẻ' in menu_unit_lower
        or menu_unit_lower.startswith('mn ')
        or 'trường mn ' in menu_unit_lower
    ) %}
    {% set menu_school_thcs = (
        'thcs' in menu_unit_lower
        or 'trung học cơ sở' in menu_unit_lower
    ) %}
    {% set menu_school_th = (
        'tiểu học' in menu_unit_lower
        or 'trường th ' in menu_unit_lower
        or menu_unit_lower.startswith('th ')
    ) %}
    {% set menu_school_liencap = (
        ('tiểu học' in menu_unit_lower and ('thcs' in menu_unit_lower or 'trung học cơ sở' in menu_unit_lower))
        or 'th & thcs' in menu_unit_lower
    ) %}
    {# === FIX_CAP_TRUONG_V1_SCHOOL_LEVEL_END === #}"""

    text = text.replace(path_anchor, level_block, 1)

    old_team_input = r"""                    {# === BAI_13B_3_GV_REPORT_INPUT_MENU_START === #}
                    {% if menu_role in ['ADMIN', 'SO', 'TRUONG'] %}
                    <a href="/doi-ngu/nhap-mn-01-gv" role="menuitem">4.3. Nhập dữ liệu MN-01-GV</a>
                    {% endif %}
                    {# === BAI_13B_3_GV_REPORT_INPUT_MENU_END === #}"""

    new_team_input = r"""                    {# === BAI_13B_3_GV_REPORT_INPUT_MENU_START === #}
                    {% if menu_role in ['ADMIN', 'SO'] %}
                    <a href="/doi-ngu/nhap-mn-01-gv" role="menuitem">4.3. Nhập dữ liệu MN-01-GV</a>
                    {% elif menu_role == 'TRUONG' %}
                        {% if menu_school_thcs and not menu_school_liencap %}
                        <a href="/bieu-nhap/thcs-01-gv" role="menuitem">4.3. Nhập dữ liệu THCS-01-GV</a>
                        {% elif menu_school_th or menu_school_liencap %}
                        <a href="/bieu-nhap/th-01-gv" role="menuitem">4.3. Nhập dữ liệu TH-01-GV</a>
                        {% else %}
                        <a href="/doi-ngu/nhap-mn-01-gv" role="menuitem">4.3. Nhập dữ liệu MN-01-GV</a>
                        {% endif %}
                    {% endif %}
                    {# === BAI_13B_3_GV_REPORT_INPUT_MENU_END === #}"""

    if old_team_input not in text:
        raise RuntimeError(
            "Không tìm thấy khối nhập dữ liệu Đội ngũ cấp Trường hiện tại."
        )
    text = text.replace(old_team_input, new_team_input, 1)

    old_csvc = r"""                <div class="pc-dropdown" role="menu">
                    <a href="/csvc/co-so" role="menuitem">CSVC.1. Cơ sở và điểm trường</a>
                    <a href="/csvc/nhom-lop" role="menuitem">CSVC.2. Nhóm/lớp và phòng học</a>
                    <a href="/csvc/cong-trinh" role="menuitem">CSVC.3. Thiết bị, vệ sinh và nước sạch</a>
                    <a href="/csvc/bep-san" role="menuitem">CSVC.4. Bếp ăn, sân chơi và đồ chơi</a>
                    <a href="/csvc/kiem-tra" role="menuitem">CSVC.5. Kiểm tra dữ liệu MN-01-CSVC</a>
                </div>"""

    new_csvc = r"""                <div class="pc-dropdown" role="menu">
                    {% if menu_role == 'TRUONG' and menu_school_thcs and not menu_school_liencap %}
                        <a href="/bieu-nhap/thcs-01-csvc#diem-truong-lop-phong" role="menuitem">CSVC.1. Điểm trường, lớp và phòng học</a>
                        <a href="/bieu-nhap/thcs-01-csvc#phong-chuc-nang" role="menuitem">CSVC.2. Phòng chức năng và phòng thí nghiệm</a>
                        <a href="/bieu-nhap/thcs-01-csvc#cong-trinh-ve-sinh" role="menuitem">CSVC.3. Công trình vệ sinh</a>
                        <a href="/bieu-nhap/thcs-01-csvc#san-bai" role="menuitem">CSVC.4. Sân chơi và bãi tập</a>
                        <a href="/bieu-nhap/thcs-01-csvc#kiem-tra" role="menuitem">CSVC.5. Kiểm tra dữ liệu THCS-01-CSVC</a>
                    {% elif menu_role == 'TRUONG' and (menu_school_th or menu_school_liencap) %}
                        <a href="/bieu-nhap/th-01-csvc#diem-truong-lop-phong" role="menuitem">CSVC.1. Điểm trường, lớp và phòng học</a>
                        <a href="/bieu-nhap/th-01-csvc#phong-chuc-nang" role="menuitem">CSVC.2. Phòng chức năng</a>
                        <a href="/bieu-nhap/th-01-csvc#cong-trinh-ve-sinh" role="menuitem">CSVC.3. Công trình vệ sinh</a>
                        <a href="/bieu-nhap/th-01-csvc#san-bai" role="menuitem">CSVC.4. Sân chơi và bãi tập</a>
                        <a href="/bieu-nhap/th-01-csvc#kiem-tra" role="menuitem">CSVC.5. Kiểm tra dữ liệu TH-01-CSVC</a>
                    {% else %}
                        <a href="/csvc/co-so" role="menuitem">CSVC.1. Cơ sở và điểm trường</a>
                        <a href="/csvc/nhom-lop" role="menuitem">CSVC.2. Nhóm/lớp và phòng học</a>
                        <a href="/csvc/cong-trinh" role="menuitem">CSVC.3. Thiết bị, vệ sinh và nước sạch</a>
                        <a href="/csvc/bep-san" role="menuitem">CSVC.4. Bếp ăn, sân chơi và đồ chơi</a>
                        <a href="/csvc/kiem-tra" role="menuitem">CSVC.5. Kiểm tra dữ liệu MN-01-CSVC</a>
                    {% endif %}
                </div>"""

    if old_csvc not in text:
        raise RuntimeError(
            "Không tìm thấy khối CSVC cấp Trường hiện tại."
        )
    text = text.replace(old_csvc, new_csvc, 1)

    text = wrap_report_submenu(
        text,
        "5.2. Báo cáo Mầm non",
        "menu_role != 'TRUONG' or menu_school_mn or (not menu_school_th and not menu_school_thcs)",
        "FIX_CAP_TRUONG_V1_REPORT_MN",
    )
    text = wrap_report_submenu(
        text,
        "5.3. Báo cáo Tiểu học",
        "menu_role != 'TRUONG' or menu_school_th or menu_school_liencap",
        "FIX_CAP_TRUONG_V1_REPORT_TH",
    )
    text = wrap_report_submenu(
        text,
        "5.4. Báo cáo THCS",
        "menu_role != 'TRUONG' or menu_school_thcs or menu_school_liencap",
        "FIX_CAP_TRUONG_V1_REPORT_THCS",
    )
    text = wrap_report_submenu(
        text,
        "5.5. Báo cáo Xóa mù chữ",
        "menu_role != 'TRUONG'",
        "FIX_CAP_TRUONG_V1_REPORT_XMC",
    )

    return text


def verify() -> None:
    router_text = read_text(STAFF_ROUTER)
    menu_text = read_text(MENU)

    router_required = [
        '"teaching_level_labels": TEACHING_LEVEL_LABELS',
        '"qualification_level_labels": QUALIFICATION_LEVEL_LABELS',
    ]
    for marker in router_required:
        if marker not in router_text:
            raise RuntimeError(f"staff_management.py thiếu marker: {marker}")

    menu_required = [
        "FIX_CAP_TRUONG_V1_SCHOOL_LEVEL_START",
        "FIX_CAP_TRUONG_V1_REPORT_MN_START",
        "FIX_CAP_TRUONG_V1_REPORT_TH_START",
        "FIX_CAP_TRUONG_V1_REPORT_THCS_START",
        "FIX_CAP_TRUONG_V1_REPORT_XMC_START",
        "/bieu-nhap/th-01-gv",
        "/bieu-nhap/thcs-01-gv",
    ]
    for marker in menu_required:
        if marker not in menu_text:
            raise RuntimeError(f"dropdown_menu_v1.html thiếu marker: {marker}")

    subprocess.run(
        [sys.executable, "-m", "py_compile", str(STAFF_ROUTER)],
        cwd=PROJECT,
        check=True,
    )

    from jinja2 import Environment
    Environment().parse(menu_text)


def clear_cache() -> None:
    for cache in APP.rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(cache, ignore_errors=True)


def main() -> int:
    print("=" * 96)
    print("SỬA CẤP TRƯỜNG V1 - ĐỘI NGŨ + CSVC + BÁO CÁO ĐÚNG CẤP HỌC")
    print("=" * 96)
    print("")
    print("SỬA 1:")
    print(" - Khắc phục lỗi Internal Server Error tại /doi-ngu.")
    print(" - Bổ sung đúng 2 biến còn thiếu cho template danh sách đội ngũ.")
    print(" - Danh sách và Kiểm tra dữ liệu tiếp tục tự khóa theo school_id của tài khoản Trường.")
    print("")
    print("SỬA 2:")
    print(" - Tài khoản Trường Mầm non chỉ hiện nhập Đội ngũ/CSVC Mầm non.")
    print(" - Tài khoản Trường Tiểu học hiện nhập Đội ngũ/CSVC Tiểu học.")
    print(" - Tài khoản Trường THCS hiện nhập Đội ngũ/CSVC THCS.")
    print("")
    print("SỬA 3:")
    print(" - Menu 5. Báo cáo của tài khoản Trường chỉ hiện báo cáo đúng cấp học.")
    print(" - Trường không còn thấy báo cáo Xóa mù chữ.")
    print(" - Sở/Xã giữ nguyên menu hiện tại.")
    print("")
    print("KHÔNG THAY ĐỔI:")
    print(" - Database.")
    print(" - Dữ liệu đã nhập.")
    print(" - Điều tra hộ dân.")
    print(" - Tài khoản người dùng.")
    print(" - Bản V1.5.2 tạo tài khoản đồng loạt.")
    print("")

    for path in [STAFF_ROUTER, MENU]:
        if not path.exists():
            raise RuntimeError(f"Không tìm thấy: {path}")

    BACKUP.mkdir(parents=True, exist_ok=False)
    backup_file(STAFF_ROUTER)
    backup_file(MENU)

    try:
        staff_before = read_text(STAFF_ROUTER)
        menu_before = read_text(MENU)

        write_text(STAFF_ROUTER, patch_staff_router(staff_before))
        write_text(MENU, patch_menu(menu_before))

        verify()
        clear_cache()

        print("")
        print("CÀI ĐẶT THÀNH CÔNG.")
        print("Backup:", BACKUP)
        print("")
        print("BÂY GIỜ KHỞI ĐỘNG LẠI UVICORN VÀ KIỂM TRA:")
        print("  1. Đăng nhập tài khoản Trường.")
        print("  2. Mở 4. Đội ngũ -> Danh sách đội ngũ.")
        print("  3. Mở 4. Đội ngũ -> Kiểm tra dữ liệu đội ngũ.")
        print("  4. Mở CSVC và kiểm tra đúng cấp học.")
        print("  5. Mở 5. Báo cáo và xác nhận chỉ còn cấp học của trường.")
        return 0

    except Exception:
        print("")
        traceback.print_exc()
        print("")
        print("CÓ LỖI - ĐANG KHÔI PHỤC...")
        restore_file(STAFF_ROUTER)
        restore_file(MENU)
        clear_cache()
        print("ĐÃ KHÔI PHỤC SOURCE TRƯỚC KHI CÀI.")
        print("Backup:", BACKUP)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
