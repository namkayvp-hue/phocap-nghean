from __future__ import annotations

import os
import shutil
import traceback
from datetime import datetime
from pathlib import Path

PROJECT = Path(
    os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")
).resolve()

YEAR = PROJECT / "app" / "templates" / "surveys" / "year_records.html"
QUICK = PROJECT / "app" / "templates" / "surveys" / "quick_entry.html"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = PROJECT / "exports" / f"backup_giao_vien_mobile_v1_8d_{STAMP}"

CSS_MARKER = "GV_MOBILE_V18D_EDIT_CSS_START"
HEAD_MARKER = "GV_MOBILE_V18D_EDIT_HEAD_START"

CSS_BLOCK = '\n        /* === GV_MOBILE_V18D_EDIT_CSS_START === */\n        .pc-gv-v18d-edit-head {\n            display: none;\n        }\n\n        @media (max-width: 760px) {\n            body.pc-gv-mobile-year-edit {\n                overflow-x: hidden;\n                background: #f2f6fb;\n            }\n\n            body.pc-gv-mobile-year-edit .pc-global-nav,\n            body.pc-gv-mobile-year-edit .admin-header,\n            body.pc-gv-mobile-year-edit .summary-grid,\n            body.pc-gv-mobile-year-edit .layout > article.panel:not(.sticky) {\n                display: none !important;\n            }\n\n            body.pc-gv-mobile-year-edit .page-wrap {\n                width: 100%;\n                max-width: 100%;\n                margin: 0;\n                padding: 10px 10px 26px;\n            }\n\n            body.pc-gv-mobile-year-edit .layout {\n                display: block !important;\n                width: 100%;\n                min-width: 0;\n            }\n\n            body.pc-gv-mobile-year-edit .layout > article.panel.sticky {\n                display: block !important;\n                position: static !important;\n                width: 100%;\n                min-width: 0;\n                padding: 12px;\n                border-radius: 13px;\n                box-shadow: none;\n            }\n\n            body.pc-gv-mobile-year-edit .layout > article.panel.sticky > .panel-label,\n            body.pc-gv-mobile-year-edit .layout > article.panel.sticky > h2,\n            body.pc-gv-mobile-year-edit .layout > article.panel.sticky > form[action$="/nam-hoc"] {\n                display: none !important;\n            }\n\n            body.pc-gv-mobile-year-edit .inheritance-hint {\n                display: none !important;\n            }\n\n            body.pc-gv-mobile-year-edit .prefill-alert {\n                margin-bottom: 10px;\n                padding: 10px;\n                font-size: 13px;\n                line-height: 1.4;\n            }\n\n            body.pc-gv-mobile-year-edit #year_record_form,\n            body.pc-gv-mobile-year-edit .form-grid,\n            body.pc-gv-mobile-year-edit .indicator-grid,\n            body.pc-gv-mobile-year-edit .disability-grid {\n                width: 100%;\n                min-width: 0;\n            }\n\n            body.pc-gv-mobile-year-edit .form-grid,\n            body.pc-gv-mobile-year-edit .indicator-grid,\n            body.pc-gv-mobile-year-edit .disability-grid {\n                grid-template-columns: minmax(0, 1fr) !important;\n                gap: 10px;\n            }\n\n            body.pc-gv-mobile-year-edit .form-group,\n            body.pc-gv-mobile-year-edit .form-group.full,\n            body.pc-gv-mobile-year-edit .indicator-item,\n            body.pc-gv-mobile-year-edit .disability-section {\n                min-width: 0;\n                max-width: 100%;\n            }\n\n            body.pc-gv-mobile-year-edit .form-group.full,\n            body.pc-gv-mobile-year-edit .disability-grid .full {\n                grid-column: auto !important;\n            }\n\n            body.pc-gv-mobile-year-edit .form-group label,\n            body.pc-gv-mobile-year-edit .indicator-item label {\n                min-height: 0;\n                font-size: 15px;\n                line-height: 1.35;\n                overflow-wrap: anywhere;\n            }\n\n            body.pc-gv-mobile-year-edit .form-control,\n            body.pc-gv-mobile-year-edit input,\n            body.pc-gv-mobile-year-edit select,\n            body.pc-gv-mobile-year-edit textarea {\n                width: 100%;\n                max-width: 100%;\n                min-width: 0;\n                font-size: 16px !important;\n            }\n\n            body.pc-gv-mobile-year-edit .form-control {\n                min-height: 48px;\n                padding: 10px 11px;\n            }\n\n            body.pc-gv-mobile-year-edit textarea.form-control {\n                min-height: 88px;\n                resize: vertical;\n            }\n\n            body.pc-gv-mobile-year-edit .lookup-row {\n                grid-template-columns: minmax(0, 1fr) 66px;\n                gap: 7px;\n            }\n\n            body.pc-gv-mobile-year-edit .lookup-clear {\n                min-width: 0;\n                width: 66px;\n                padding: 0 8px;\n            }\n\n            body.pc-gv-mobile-year-edit .suggestion-list {\n                left: 0;\n                right: 0;\n                max-width: 100%;\n            }\n\n            body.pc-gv-mobile-year-edit .selected-box,\n            body.pc-gv-mobile-year-edit .form-note {\n                overflow-wrap: anywhere;\n            }\n\n            body.pc-gv-mobile-year-edit .indicator-item {\n                padding: 10px;\n                border-radius: 10px;\n            }\n\n            body.pc-gv-mobile-year-edit .disability-section {\n                padding: 11px;\n                border-radius: 12px;\n            }\n\n            body.pc-gv-mobile-year-edit .disability-heading {\n                display: block;\n                margin-bottom: 10px;\n            }\n\n            body.pc-gv-mobile-year-edit .disability-heading h3 {\n                font-size: 17px;\n                line-height: 1.35;\n                overflow-wrap: anywhere;\n            }\n\n            body.pc-gv-mobile-year-edit .form-note {\n                font-size: 12px;\n                line-height: 1.4;\n            }\n\n            body.pc-gv-mobile-year-edit #year_record_form > .button[type="submit"] {\n                min-height: 54px;\n                margin-top: 13px !important;\n                font-size: 17px;\n                border-radius: 12px;\n            }\n\n            .pc-gv-v18d-edit-head {\n                display: flex;\n                align-items: center;\n                gap: 10px;\n                width: 100%;\n                margin: 0 0 10px;\n                padding: 11px 12px;\n                border-radius: 13px;\n                background: #0f5fa8;\n                color: #ffffff;\n            }\n\n            .pc-gv-v18d-edit-back {\n                flex: 0 0 auto;\n                display: inline-flex;\n                align-items: center;\n                justify-content: center;\n                min-height: 40px;\n                padding: 7px 10px;\n                border-radius: 9px;\n                background: #ffffff;\n                color: #0f5fa8 !important;\n                text-decoration: none !important;\n                font-size: 13px;\n                font-weight: 800;\n            }\n\n            .pc-gv-v18d-edit-person {\n                min-width: 0;\n            }\n\n            .pc-gv-v18d-edit-person small,\n            .pc-gv-v18d-edit-person strong {\n                display: block;\n            }\n\n            .pc-gv-v18d-edit-person small {\n                font-size: 11px;\n                font-weight: 800;\n                opacity: .9;\n                text-transform: uppercase;\n            }\n\n            .pc-gv-v18d-edit-person strong {\n                margin-top: 2px;\n                font-size: 17px;\n                line-height: 1.25;\n                overflow-wrap: anywhere;\n            }\n        }\n        /* === GV_MOBILE_V18D_EDIT_CSS_END === */\n'
HEAD_HTML = '\n    {% if nguoi_dung.role_code == \'GIAO_VIEN\' %}\n    <!-- === GV_MOBILE_V18D_EDIT_HEAD_START === -->\n    <section class="pc-gv-v18d-edit-head">\n        <a\n            class="pc-gv-v18d-edit-back"\n            href="/dieu-tra/{{ batch.id }}/ho-dan/{{ household.id }}/nhap-nhanh"\n        >\n            ← Nhập nhanh\n        </a>\n        <div class="pc-gv-v18d-edit-person">\n            <small>Sửa thông tin năm học</small>\n            <strong>{{ person.full_name }} · {{ batch.school_year.code }}</strong>\n        </div>\n    </section>\n    <!-- === GV_MOBILE_V18D_EDIT_HEAD_END === -->\n    {% endif %}\n'
OLD_EDIT = 'href="/dieu-tra/{{ batch.id }}/ho-dan/{{ household.id }}/doi-tuong/{{ item.person.id }}/nam-hoc?school_year_id={{ batch.school_year_id }}"'
NEW_EDIT = 'href="/dieu-tra/{{ batch.id }}/ho-dan/{{ household.id }}/doi-tuong/{{ item.person.id }}/nam-hoc?school_year_id={{ batch.school_year_id }}#year_record_form"'
BODY_REPLACEMENT = '<body class="{% if nguoi_dung.role_code == \'GIAO_VIEN\' %}pc-gv-mobile-year-edit{% endif %}">'

def main() -> int:
    print("=" * 78)
    print("GIAO VIEN MOBILE V1.8D")
    print("TOI UU NUT SUA TREN DIEN THOAI")
    print("=" * 78)

    for path in (YEAR, QUICK):
        if not path.exists():
            raise RuntimeError(f"Không tìm thấy: {path}")

    year_text = YEAR.read_text(encoding="utf-8-sig")
    quick_text = QUICK.read_text(encoding="utf-8-sig")

    required_year = [
        'id="year_record_form"',
        "Theo dõi trẻ khuyết tật",
        "Lưu thông tin năm học",
    ]
    for marker in required_year:
        if marker not in year_text:
            raise RuntimeError(
                f"Không tìm thấy marker '{marker}' trong year_records.html."
            )

    required_quick = [
        "GV_MOBILE_V18_QUICK_START",
        "pc-gv-v18-edit",
        "Sửa",
    ]
    for marker in required_quick:
        if marker not in quick_text:
            raise RuntimeError(
                f"Không tìm thấy marker '{marker}' trong quick_entry.html."
            )

    BACKUP.mkdir(parents=True, exist_ok=False)

    backup_year = BACKUP / "app" / "templates" / "surveys" / "year_records.html"
    backup_quick = BACKUP / "app" / "templates" / "surveys" / "quick_entry.html"
    backup_year.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(YEAR, backup_year)
    shutil.copy2(QUICK, backup_quick)

    try:
        if "pc-gv-mobile-year-edit" not in year_text:
            if "<body>" not in year_text:
                raise RuntimeError("Không tìm thấy thẻ <body>.")
            year_text = year_text.replace("<body>", BODY_REPLACEMENT, 1)

        if CSS_MARKER not in year_text:
            style_anchor = "    </style>"
            if style_anchor not in year_text:
                raise RuntimeError("Không tìm thấy điểm chèn CSS.")
            year_text = year_text.replace(
                style_anchor,
                CSS_BLOCK + "\n" + style_anchor,
                1,
            )

        if HEAD_MARKER not in year_text:
            main_anchor = '<main class="page-wrap">'
            if main_anchor not in year_text:
                raise RuntimeError('Không tìm thấy <main class="page-wrap">.')
            year_text = year_text.replace(
                main_anchor,
                main_anchor + "\n" + HEAD_HTML,
                1,
            )

        if "#year_record_form" not in quick_text:
            if OLD_EDIT not in quick_text:
                raise RuntimeError("Không tìm thấy liên kết Sửa mobile đúng phiên bản.")
            quick_text = quick_text.replace(OLD_EDIT, NEW_EDIT, 1)

        YEAR.write_text(year_text, encoding="utf-8")
        QUICK.write_text(quick_text, encoding="utf-8")

        year_check = YEAR.read_text(encoding="utf-8")
        quick_check = QUICK.read_text(encoding="utf-8")

        checks_year = [
            "pc-gv-mobile-year-edit",
            CSS_MARKER,
            HEAD_MARKER,
            "← Nhập nhanh",
            'id="year_record_form"',
            "Theo dõi trẻ khuyết tật",
            "Lưu thông tin năm học",
        ]
        for marker in checks_year:
            if marker not in year_check:
                raise RuntimeError(f"Kiểm tra year_records không đạt: {marker}")

        if "#year_record_form" not in quick_check:
            raise RuntimeError("Kiểm tra liên kết Sửa -> form không đạt.")

        print("")
        print("GIU NGUYEN:")
        print(" - Man hinh chinh")
        print(" - Phieu phan cong")
        print(" - Danh sach thanh vien")
        print(" - Chap nhan")
        print(" - Them thanh vien")
        print(" - Hoan thanh / Ho tiep theo")
        print(" - Giao dien may tinh")
        print(" - Database")
        print("")
        print("THAY DOI RIENG TREN DIEN THOAI:")
        print(" - Bam Sua -> vao thang bieu mau sua")
        print(" - An menu, tong quan, lich su khi dang sua")
        print(" - Form 1 cot, vua chieu rong dien thoai")
        print(" - Truong/lop/chi bao/khuyet tat khong bi tran ngang")
        print(" - Co nut quay lai Nhap nhanh")
        print("")
        print("CAI DAT GIAO VIEN MOBILE V1.8D THANH CONG")
        print("Backup:", BACKUP)
        return 0

    except Exception:
        traceback.print_exc()
        if backup_year.exists():
            shutil.copy2(backup_year, YEAR)
        if backup_quick.exists():
            shutil.copy2(backup_quick, QUICK)
        print("")
        print("CO LOI - DA KHOI PHUC HAI TEMPLATE TU DONG.")
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
