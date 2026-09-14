from __future__ import annotations

import os
import shutil
import traceback
from datetime import datetime
from pathlib import Path

PROJECT = Path(
    os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")
).resolve()

TARGET = PROJECT / "app" / "templates" / "surveys" / "index.html"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = PROJECT / "exports" / f"backup_giao_vien_mobile_v1_8c_{STAMP}"

CSS_MARKER = "GV_MOBILE_V18C_TITLE_CSS"
HTML_MARKER = "GV_MOBILE_V18C_TITLE_HTML"

CSS_BLOCK = '\n    /* === GV_MOBILE_V18C_TITLE_CSS === */\n    .pc-gv-v18-brand {\n        display: flex;\n        align-items: center;\n        gap: 12px;\n        padding: 15px 16px;\n        border-radius: 15px;\n        background: linear-gradient(135deg, #0f5fa8, #1976d2);\n        color: #ffffff;\n        box-shadow: 0 5px 14px rgba(23,105,170,.16);\n    }\n\n    .pc-gv-v18-brand-logo {\n        flex: 0 0 52px;\n        width: 52px;\n        height: 52px;\n        display: flex;\n        align-items: center;\n        justify-content: center;\n        border-radius: 12px;\n        background: #ffffff;\n        color: #155fa5;\n        font-size: 22px;\n        font-weight: 900;\n        letter-spacing: .5px;\n    }\n\n    .pc-gv-v18-brand-text {\n        min-width: 0;\n    }\n\n    .pc-gv-v18-brand-title {\n        margin: 0;\n        color: #ffffff;\n        font-size: 18px;\n        font-weight: 900;\n        line-height: 1.22;\n        text-transform: uppercase;\n    }\n\n    .pc-gv-v18-brand-subtitle {\n        margin: 4px 0 0;\n        color: rgba(255,255,255,.90);\n        font-size: 13px;\n        font-weight: 600;\n        line-height: 1.3;\n    }\n'
HTML_BLOCK = '\n        <!-- === GV_MOBILE_V18C_TITLE_HTML === -->\n        <div class="pc-gv-v18-brand">\n            <div class="pc-gv-v18-brand-logo">PC</div>\n            <div class="pc-gv-v18-brand-text">\n                <p class="pc-gv-v18-brand-title">\n                    Phổ cập giáo dục và xóa mù chữ\n                </p>\n                <p class="pc-gv-v18-brand-subtitle">\n                    Hệ thống quản lý dữ liệu\n                </p>\n            </div>\n        </div>\n'

def main() -> int:
    print("=" * 78)
    print("GIAO VIEN MOBILE V1.8C")
    print("BO SUNG TIEU DE PHAN MEM TREN MAN HINH CHINH DIEN THOAI")
    print("=" * 78)

    if not TARGET.exists():
        raise RuntimeError(f"Không tìm thấy: {TARGET}")

    text = TARGET.read_text(encoding="utf-8-sig")

    required = [
        "GV_MOBILE_V18_HOME_START",
        "pc-gv-v18-home-inner",
        "pc-gv-v18-year",
        "Phiếu phân công",
    ]
    for marker in required:
        if marker not in text:
            raise RuntimeError(
                f"Không tìm thấy marker '{marker}'. "
                "Dừng cài để tránh sửa nhầm phiên bản."
            )

    if CSS_MARKER in text and HTML_MARKER in text:
        print("V1.8C đã có sẵn. Không chèn lặp.")
        print("CAI DAT GIAO VIEN MOBILE V1.8C THANH CONG")
        return 0

    BACKUP.mkdir(parents=True, exist_ok=False)
    backup_target = BACKUP / "app" / "templates" / "surveys" / "index.html"
    backup_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(TARGET, backup_target)

    try:
        css_anchor = "    .pc-gv-v18-year {"
        if css_anchor not in text:
            raise RuntimeError("Không tìm thấy điểm chèn CSS an toàn.")

        text = text.replace(
            css_anchor,
            CSS_BLOCK + "\n" + css_anchor,
            1,
        )

        html_anchor = '        <form method="get" action="/dieu-tra" id="pc-gv-v18-year-form">'
        if html_anchor not in text:
            raise RuntimeError("Không tìm thấy điểm chèn tiêu đề an toàn.")

        text = text.replace(
            html_anchor,
            HTML_BLOCK + "\n" + html_anchor,
            1,
        )

        TARGET.write_text(text, encoding="utf-8")

        check = TARGET.read_text(encoding="utf-8")
        checks = [
            CSS_MARKER,
            HTML_MARKER,
            "Phổ cập giáo dục và xóa mù chữ",
            "Hệ thống quản lý dữ liệu",
            'id="pc-gv-v18-year-form"',
            "Phiếu phân công",
        ]
        for item in checks:
            if item not in check:
                raise RuntimeError(f"Kiểm tra sau cài đặt không đạt: {item}")

        print("")
        print("GIU NGUYEN:")
        print(" - Chon nam hoc")
        print(" - Phieu phan cong")
        print(" - So phieu - Ten ho - Nhap nhanh")
        print(" - Nhap nhanh va Them thanh vien")
        print(" - Hoan thanh / Ho tiep theo")
        print(" - Desktop va cac vai tro khac")
        print(" - Database")
        print("")
        print("BO SUNG:")
        print(" - Logo PC")
        print(" - PHO CAP GIAO DUC VA XOA MU CHU")
        print(" - He thong quan ly du lieu")
        print("")
        print("CAI DAT GIAO VIEN MOBILE V1.8C THANH CONG")
        print("Backup:", BACKUP)
        return 0

    except Exception:
        traceback.print_exc()
        if backup_target.exists():
            shutil.copy2(backup_target, TARGET)
        print("")
        print("CO LOI - DA KHOI PHUC index.html TU DONG.")
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
