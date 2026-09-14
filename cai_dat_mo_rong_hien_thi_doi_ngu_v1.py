from __future__ import annotations

import os
import shutil
import sys
import traceback
from datetime import datetime
from pathlib import Path

PROJECT = Path(os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")).resolve()
TARGET = PROJECT / "app" / "templates" / "staff" / "list.html"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP_DIR = PROJECT / "exports" / f"backup_mo_rong_hien_thi_doi_ngu_v1_{STAMP}"
BACKUP_FILE = BACKUP_DIR / "app" / "templates" / "staff" / "list.html"

MARKER = "MO_RONG_HIEN_THI_DOI_NGU_V1"

CSS = r'''
    <!-- === MO_RONG_HIEN_THI_DOI_NGU_V1_START === -->
    <style id="MO_RONG_HIEN_THI_DOI_NGU_V1">
        /*
         * Chỉ thay đổi bố cục hiển thị trang Danh sách đội ngũ.
         * Không thay đổi dữ liệu, route, quyền, import/export.
         */

        @media (min-width: 1101px) {
            .hero-inner {
                width: 100% !important;
                max-width: none !important;
                box-sizing: border-box !important;
            }

            .container {
                width: 100% !important;
                max-width: none !important;
                margin-left: 0 !important;
                margin-right: 0 !important;
                padding-left: 16px !important;
                padding-right: 16px !important;
                box-sizing: border-box !important;
            }

            .container > * {
                max-width: none !important;
            }

            .panel {
                width: 100% !important;
                max-width: none !important;
                box-sizing: border-box !important;
            }

            .table-wrap {
                width: 100% !important;
                max-width: none !important;
                overflow-x: auto !important;
                box-sizing: border-box !important;
            }

            .data-table {
                width: 100% !important;
                min-width: 0 !important;
                max-width: none !important;
                table-layout: fixed !important;
            }

            .data-table th,
            .data-table td {
                padding: 9px 7px !important;
                font-size: 13px !important;
                line-height: 1.35 !important;
                white-space: normal !important;
                overflow-wrap: anywhere !important;
                word-break: normal !important;
                vertical-align: top !important;
            }

            .data-table th:nth-child(1),
            .data-table td:nth-child(1)  { width: 4% !important; }

            .data-table th:nth-child(2),
            .data-table td:nth-child(2)  { width: 13% !important; }

            .data-table th:nth-child(3),
            .data-table td:nth-child(3)  { width: 12% !important; }

            .data-table th:nth-child(4),
            .data-table td:nth-child(4)  { width: 9% !important; }

            .data-table th:nth-child(5),
            .data-table td:nth-child(5)  { width: 9% !important; }

            .data-table th:nth-child(6),
            .data-table td:nth-child(6)  { width: 11% !important; }

            .data-table th:nth-child(7),
            .data-table td:nth-child(7)  { width: 9% !important; }

            .data-table th:nth-child(8),
            .data-table td:nth-child(8)  { width: 6% !important; }

            .data-table th:nth-child(9),
            .data-table td:nth-child(9)  { width: 9% !important; }

            .data-table th:nth-child(10),
            .data-table td:nth-child(10) { width: 9% !important; }

            .data-table th:nth-child(11),
            .data-table td:nth-child(11) { width: 9% !important; }

            .data-table th:nth-child(12),
            .data-table td:nth-child(12) { width: 10% !important; }

            .small-actions {
                gap: 5px !important;
            }

            .small-actions .button {
                padding: 7px 8px !important;
                font-size: 12px !important;
            }

            .tool-grid,
            .stats,
            .filters,
            .audit-grid {
                width: 100% !important;
                max-width: none !important;
            }
        }

        @media (max-width: 1100px) {
            .table-wrap {
                overflow-x: auto !important;
                -webkit-overflow-scrolling: touch;
            }

            .data-table {
                min-width: 1250px !important;
                table-layout: auto !important;
            }
        }
    </style>
    <!-- === MO_RONG_HIEN_THI_DOI_NGU_V1_END === -->
'''


def read_text(path: Path) -> str:
    if not path.exists():
        raise RuntimeError(f"Không tìm thấy tệp bắt buộc: {path}")
    return path.read_text(encoding="utf-8-sig")


def backup() -> None:
    BACKUP_FILE.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(TARGET, BACKUP_FILE)


def restore() -> None:
    if BACKUP_FILE.exists():
        TARGET.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(BACKUP_FILE, TARGET)


def clear_cache() -> None:
    app_dir = PROJECT / "app"
    for cache in app_dir.rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(cache, ignore_errors=True)


def patch(text: str) -> str:
    if MARKER in text:
        print("Trang staff/list.html đã có bản mở rộng V1. Không chèn lặp.")
        return text

    if "</head>" not in text:
        raise RuntimeError("Không tìm thấy thẻ </head> trong staff/list.html.")

    required_any = [
        "Quản lý đội ngũ",
        "Dữ liệu chi tiết",
        "data-table",
        "table-wrap",
    ]
    if not any(item in text for item in required_any):
        raise RuntimeError(
            "staff/list.html không giống template đội ngũ hiện tại. "
            "Dừng để tránh sửa nhầm tệp."
        )

    return text.replace("</head>", CSS + "\n</head>", 1)


def verify(text: str) -> None:
    if MARKER not in text:
        raise RuntimeError("Không tìm thấy marker mở rộng sau khi sửa.")

    from jinja2 import Environment
    Environment().parse(text)


def main() -> int:
    print("=" * 104)
    print("MỞ RỘNG TOÀN BỘ PHẦN HIỂN THỊ DANH SÁCH ĐỘI NGŨ V1")
    print("=" * 104)
    print("")
    print("THAY ĐỔI:")
    print(" - Vùng nội dung dùng gần như toàn bộ chiều ngang màn hình máy tính.")
    print(" - Bảng 12 cột được dàn lại để nhìn đủ các cột trên màn hình lớn.")
    print(" - Chữ và khoảng cách trong bảng được thu gọn vừa phải.")
    print(" - Màn hình nhỏ vẫn giữ cuộn ngang an toàn.")
    print("")
    print("KHÔNG THAY ĐỔI:")
    print(" - Database và dữ liệu đội ngũ.")
    print(" - Route /doi-ngu.")
    print(" - Quyền tài khoản.")
    print(" - Nhập/Xuất Excel.")
    print(" - CSVC, Báo cáo, Điều tra hộ dân, giao diện điện thoại.")
    print("")

    before = read_text(TARGET)
    backup()

    try:
        after = patch(before)
        verify(after)
        TARGET.write_text(after, encoding="utf-8")

        from jinja2 import Environment, FileSystemLoader
        env = Environment(loader=FileSystemLoader(str(PROJECT / "app" / "templates")))
        env.get_template("staff/list.html")

        clear_cache()

        print("")
        print("CÀI ĐẶT MỞ RỘNG HIỂN THỊ ĐỘI NGŨ V1 THÀNH CÔNG")
        print("Backup:", BACKUP_DIR)
        print("")
        print("Khởi động lại Uvicorn và nhấn Ctrl + F5 tại trang /doi-ngu.")
        return 0

    except Exception:
        traceback.print_exc()
        print("")
        print("CÓ LỖI - ĐANG KHÔI PHỤC...")
        restore()
        clear_cache()
        print("ĐÃ KHÔI PHỤC staff/list.html VỀ TRƯỚC KHI CÀI.")
        print("Backup:", BACKUP_DIR)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
