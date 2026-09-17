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
BACKUP = PROJECT / "exports" / f"backup_bai_13b_5_v1_{STAMP}"
MANIFEST = BACKUP / "manifest.json"

TEAM_NEW = '\n            {# === BAI_13B_5_V1_TEAM_MENU_START === #}\n            {% if menu_role in [\'ADMIN\', \'SO\', \'XA\'] %}\n            <div class="pc-menu-group {% if menu_path.startswith(\'/doi-ngu\') %}is-active{% endif %}">\n                <button type="button" class="pc-menu-trigger" aria-expanded="false">\n                    4. Đội ngũ <span class="pc-menu-caret">▾</span>\n                </button>\n\n                <div class="pc-dropdown pc-dropdown--right" role="menu">\n\n                    <div class="pc-submenu">\n                        <button type="button" class="pc-submenu-trigger" aria-expanded="false">\n                            <span class="pc-submenu-trigger__text">4.1. Mầm non</span>\n                            <span class="pc-submenu-arrow">▶</span>\n                        </button>\n                        <div class="pc-submenu-panel" role="menu">\n                            <a href="/doi-ngu/nhap-mn-01-gv" role="menuitem">\n                                4.1.1. MN-01-GV – Nhập/kiểm tra dữ liệu\n                            </a>\n                            <a href="/doi-ngu" role="menuitem">\n                                4.1.2. Danh sách đội ngũ\n                            </a>\n                            <a href="/doi-ngu/kiem-tra-du-lieu" role="menuitem">\n                                4.1.3. Kiểm tra dữ liệu đội ngũ\n                            </a>\n                            <a href="/bao-cao?report_type=PCGD_MN_01_GV_2025" role="menuitem">\n                                4.1.4. Báo cáo MN-01-GV\n                            </a>\n                        </div>\n                    </div>\n\n                    <div class="pc-submenu">\n                        <button type="button" class="pc-submenu-trigger" aria-expanded="false">\n                            <span class="pc-submenu-trigger__text">4.2. Tiểu học</span>\n                            <span class="pc-submenu-arrow">▶</span>\n                        </button>\n                        <div class="pc-submenu-panel" role="menu">\n                            <a href="/doi-ngu" role="menuitem">\n                                4.2.1. Dữ liệu đội ngũ phục vụ TH-01-GV\n                            </a>\n                            <a href="/doi-ngu/kiem-tra-du-lieu" role="menuitem">\n                                4.2.2. Kiểm tra dữ liệu đội ngũ\n                            </a>\n                            <a href="/bao-cao?report_type=PCGD_TH_01_GV_2025" role="menuitem">\n                                4.2.3. Báo cáo TH-01-GV\n                            </a>\n                        </div>\n                    </div>\n\n                    <div class="pc-submenu">\n                        <button type="button" class="pc-submenu-trigger" aria-expanded="false">\n                            <span class="pc-submenu-trigger__text">4.3. THCS</span>\n                            <span class="pc-submenu-arrow">▶</span>\n                        </button>\n                        <div class="pc-submenu-panel" role="menu">\n                            <a href="/doi-ngu" role="menuitem">\n                                4.3.1. Dữ liệu đội ngũ phục vụ THCS-01-GV\n                            </a>\n                            <a href="/doi-ngu/kiem-tra-du-lieu" role="menuitem">\n                                4.3.2. Kiểm tra dữ liệu đội ngũ\n                            </a>\n                            <a href="/bao-cao?report_type=PCGD_THCS_M5_2025" role="menuitem">\n                                4.3.3. Báo cáo THCS-01-GV\n                            </a>\n                        </div>\n                    </div>\n\n                    {% if menu_role in [\'ADMIN\', \'SO\'] %}\n                    <div class="pc-submenu">\n                        <button type="button" class="pc-submenu-trigger" aria-expanded="false">\n                            <span class="pc-submenu-trigger__text">4.4. Công cụ quản lý chung</span>\n                            <span class="pc-submenu-arrow">▶</span>\n                        </button>\n                        <div class="pc-submenu-panel" role="menu">\n                            <a href="/doi-ngu/them" role="menuitem">4.4.1. Thêm nhân sự</a>\n                            <a href="/doi-ngu/cau-hinh-lop" role="menuitem">4.4.2. Cấu hình lớp</a>\n                            <a href="/doi-ngu/xuat-mau-excel" role="menuitem">4.4.3. Xuất mẫu Excel đội ngũ</a>\n                            <a href="/doi-ngu/xuat-danh-sach-excel" role="menuitem">4.4.4. Xuất danh sách Excel</a>\n                        </div>\n                    </div>\n                    {% endif %}\n                </div>\n            </div>\n            {% else %}\n            __OLD_TEAM_BLOCK__\n            {% endif %}\n            {# === BAI_13B_5_V1_TEAM_MENU_END === #}\n'
CSVC_NEW = '\n            {# === BAI_13B_5_V1_CSVC_MENU_START === #}\n            {% if menu_role in [\'ADMIN\', \'SO\', \'XA\'] %}\n            <div class="pc-menu-group {% if menu_path.startswith(\'/csvc\') %}is-active{% endif %}">\n                <button type="button" class="pc-menu-trigger" aria-expanded="false">\n                    CSVC <span class="pc-menu-caret">▾</span>\n                </button>\n\n                <div class="pc-dropdown pc-dropdown--right" role="menu">\n\n                    <div class="pc-submenu">\n                        <button type="button" class="pc-submenu-trigger" aria-expanded="false">\n                            <span class="pc-submenu-trigger__text">CSVC.1. Mầm non</span>\n                            <span class="pc-submenu-arrow">▶</span>\n                        </button>\n                        <div class="pc-submenu-panel" role="menu">\n                            <a href="/csvc/co-so" role="menuitem">\n                                CSVC.1.1. MN-01-CSVC – Cơ sở và điểm trường\n                            </a>\n                            <a href="/csvc/nhom-lop" role="menuitem">\n                                CSVC.1.2. Nhóm/lớp và phòng học\n                            </a>\n                            <a href="/csvc/cong-trinh" role="menuitem">\n                                CSVC.1.3. Thiết bị, vệ sinh và nước sạch\n                            </a>\n                            <a href="/csvc/bep-san" role="menuitem">\n                                CSVC.1.4. Bếp ăn, sân chơi và đồ chơi\n                            </a>\n                            <a href="/csvc/kiem-tra" role="menuitem">\n                                CSVC.1.5. Kiểm tra dữ liệu MN-01-CSVC\n                            </a>\n                            <a href="/bao-cao?report_type=PCGD_MN_01_CSVC_2025" role="menuitem">\n                                CSVC.1.6. Báo cáo MN-01-CSVC\n                            </a>\n                        </div>\n                    </div>\n\n                    <div class="pc-submenu">\n                        <button type="button" class="pc-submenu-trigger" aria-expanded="false">\n                            <span class="pc-submenu-trigger__text">CSVC.2. Tiểu học</span>\n                            <span class="pc-submenu-arrow">▶</span>\n                        </button>\n                        <div class="pc-submenu-panel" role="menu">\n                            <a href="/bao-cao?report_type=PCGD_TH_01_CSVC_2025" role="menuitem">\n                                CSVC.2.1. TH-01-CSVC – Điểm trường, lớp và phòng học\n                            </a>\n                            <a href="/bao-cao?report_type=PCGD_TH_01_CSVC_2025" role="menuitem">\n                                CSVC.2.2. Phòng chức năng\n                            </a>\n                            <a href="/bao-cao?report_type=PCGD_TH_01_CSVC_2025" role="menuitem">\n                                CSVC.2.3. Công trình vệ sinh\n                            </a>\n                            <a href="/bao-cao?report_type=PCGD_TH_01_CSVC_2025" role="menuitem">\n                                CSVC.2.4. Sân chơi và bãi tập\n                            </a>\n                            <a href="/bao-cao?report_type=PCGD_TH_01_CSVC_2025" role="menuitem">\n                                CSVC.2.5. Báo cáo TH-01-CSVC\n                            </a>\n                        </div>\n                    </div>\n\n                    <div class="pc-submenu">\n                        <button type="button" class="pc-submenu-trigger" aria-expanded="false">\n                            <span class="pc-submenu-trigger__text">CSVC.3. THCS</span>\n                            <span class="pc-submenu-arrow">▶</span>\n                        </button>\n                        <div class="pc-submenu-panel" role="menu">\n                            <a href="/bao-cao?report_type=PCGD_THCS_CSVC_2025" role="menuitem">\n                                CSVC.3.1. THCS-01-CSVC – Điểm trường, lớp và phòng học\n                            </a>\n                            <a href="/bao-cao?report_type=PCGD_THCS_CSVC_2025" role="menuitem">\n                                CSVC.3.2. Phòng chức năng và phòng thí nghiệm\n                            </a>\n                            <a href="/bao-cao?report_type=PCGD_THCS_CSVC_2025" role="menuitem">\n                                CSVC.3.3. Công trình vệ sinh\n                            </a>\n                            <a href="/bao-cao?report_type=PCGD_THCS_CSVC_2025" role="menuitem">\n                                CSVC.3.4. Sân chơi và bãi tập\n                            </a>\n                            <a href="/bao-cao?report_type=PCGD_THCS_CSVC_2025" role="menuitem">\n                                CSVC.3.5. Báo cáo THCS-01-CSVC\n                            </a>\n                        </div>\n                    </div>\n\n                </div>\n            </div>\n            {% else %}\n            __OLD_CSVC_BLOCK__\n            {% endif %}\n            {# === BAI_13B_5_V1_CSVC_MENU_END === #}\n'

TEAM_START = "{# 4. ĐỘI NGŨ:"
CSVC_ORIGINAL_START = "{# === BAI_13B_3_CSVC_MENU_START === #}"
CSVC_ORIGINAL_END = "{# === BAI_13B_3_CSVC_MENU_END === #}"
TEAM_NEW_MARKER = "BAI_13B_5_V1_TEAM_MENU_START"
CSVC_NEW_MARKER = "BAI_13B_5_V1_CSVC_MENU_START"


def main() -> int:
    print("=" * 88)
    print("BÀI 13B-5 V1 - CHUẨN HÓA MENU 3 CẤP ĐỘI NGŨ VÀ CSVC CHO SỞ/XÃ")
    print("=" * 88)

    if not MENU.exists():
        raise RuntimeError(f"Không tìm thấy: {MENU}")

    text = MENU.read_text(encoding="utf-8-sig")

    for marker in [
        "BAI_13B_3_GV_REPORT_INPUT_MENU_START",
        "BAI_13B_3_CSVC_MENU_START",
        "BAI_13B_4_V1_PRIMARY_CENTER_MENU_START",
        "BAI_13B_4_V1_THCS_CENTER_MENU_START",
        "BAI_13B_4_V1_XMC_CENTER_MENU_START",
    ]:
        if marker not in text:
            raise RuntimeError(
                f"Không tìm thấy nền mã nguồn cần thiết: {marker}. "
                "Dừng cài để không làm thay đổi sai phiên bản."
            )

    if TEAM_NEW_MARKER in text and CSVC_NEW_MARKER in text:
        print("Bài 13B-5 V1 đã có sẵn. Không chèn lặp.")
        print("CAI DAT BAI 13B-5 V1 THANH CONG")
        return 0

    BACKUP.mkdir(parents=True, exist_ok=False)
    backup_menu = BACKUP / "app" / "templates" / "partials" / "dropdown_menu_v1.html"
    backup_menu.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(MENU, backup_menu)
    MANIFEST.write_text(
        json.dumps({"file": "app/templates/partials/dropdown_menu_v1.html"}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    try:
        # 1. Trích nguyên khối Đội ngũ hiện tại để giữ nguyên cho các vai trò khác.
        team_pos = text.find(TEAM_START)
        csvc_pos = text.find(CSVC_ORIGINAL_START)
        if team_pos < 0 or csvc_pos < 0 or csvc_pos <= team_pos:
            raise RuntimeError("Không xác định được khối menu Đội ngũ hiện tại.")

        old_team = text[team_pos:csvc_pos].rstrip()
        new_team = TEAM_NEW.replace("__OLD_TEAM_BLOCK__", old_team)
        text = text[:team_pos] + new_team + "\n\n" + text[csvc_pos:]

        # 2. Trích nguyên khối CSVC hiện tại để giữ nguyên cho các vai trò khác.
        csvc_start = text.find(CSVC_ORIGINAL_START)
        csvc_end = text.find(CSVC_ORIGINAL_END, csvc_start)
        if csvc_start < 0 or csvc_end < 0:
            raise RuntimeError("Không xác định được khối menu CSVC hiện tại.")
        csvc_end += len(CSVC_ORIGINAL_END)
        old_csvc = text[csvc_start:csvc_end]
        new_csvc = CSVC_NEW.replace("__OLD_CSVC_BLOCK__", old_csvc)
        text = text[:csvc_start] + new_csvc + text[csvc_end:]

        MENU.write_text(text, encoding="utf-8")

        # Kiểm tra Jinja.
        from jinja2 import Environment, FileSystemLoader
        env = Environment(loader=FileSystemLoader(str(PROJECT / "app" / "templates")))
        env.get_template("partials/dropdown_menu_v1.html")

        check = MENU.read_text(encoding="utf-8")
        required = [
            "BAI_13B_5_V1_TEAM_MENU_START",
            "4.1. Mầm non",
            "4.2. Tiểu học",
            "4.3. THCS",
            "BAI_13B_5_V1_CSVC_MENU_START",
            "CSVC.1. Mầm non",
            "CSVC.2. Tiểu học",
            "CSVC.3. THCS",
            "PCGD_TH_01_GV_2025",
            "PCGD_THCS_M5_2025",
            "PCGD_TH_01_CSVC_2025",
            "PCGD_THCS_CSVC_2025",
        ]
        for marker in required:
            if marker not in check:
                raise RuntimeError(f"Kiểm tra sau cài đặt không đạt: {marker}")

        print("")
        print("ÁP DỤNG CHO CẤP SỞ VÀ XÃ (ADMIN/SO/XA):")
        print(" - 4. Đội ngũ -> Mầm non / Tiểu học / THCS -> các nhánh biểu tương ứng.")
        print(" - CSVC -> Mầm non / Tiểu học / THCS -> các nhánh chỉ tiêu tương ứng.")
        print("")
        print("MẦM NON:")
        print(" - Giữ nguyên toàn bộ màn hình nhập MN-01-GV và MN-01-CSVC đã làm.")
        print("")
        print("TIỂU HỌC:")
        print(" - Đội ngũ bám biểu TH-01-GV.")
        print(" - CSVC bám biểu TH-01-CSVC: điểm trường/lớp/phòng học; phòng chức năng; vệ sinh; sân/bãi.")
        print("")
        print("THCS:")
        print(" - Đội ngũ bám biểu THCS-01-GV (THCS-M5).")
        print(" - CSVC bám biểu THCS-01-CSVC: lớp/phòng; phòng chức năng/thí nghiệm; vệ sinh; sân/bãi.")
        print("")
        print("GIỮ NGUYÊN:")
        print(" - Menu Báo cáo đã hoàn thiện.")
        print(" - Vai trò Trường/Phòng ban dùng menu cũ, không bị thay đổi.")
        print(" - Database và dữ liệu: KHÔNG thay đổi.")
        print("")
        print("LƯU Ý:")
        print(" - Bản V1 này chuẩn hóa cấu trúc menu.")
        print(" - Các biểu nhập chuyên biệt Tiểu học/THCS chưa có CSDL riêng vẫn mở dữ liệu/báo cáo hiện có;")
        print("   không tạo số liệu giả hoặc suy diễn.")
        print("")
        print("CAI DAT BAI 13B-5 V1 THANH CONG")
        print("Backup:", BACKUP)
        return 0

    except Exception:
        traceback.print_exc()
        if backup_menu.exists():
            shutil.copy2(backup_menu, MENU)
        print("")
        print("CÓ LỖI - ĐÃ KHÔI PHỤC MENU TỰ ĐỘNG.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
