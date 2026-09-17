# -*- coding: utf-8 -*-
from __future__ import annotations

import ast
import py_compile
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from jinja2 import Environment

PROJECT = Path(r"C:\PhoCap")
APP = PROJECT / "app"
DB = PROJECT / "data" / "phocap.db"
EXPORTS = PROJECT / "exports"

ROUTER = APP / "routers" / "pcgdmn_template_report.py"
MENU = APP / "templates" / "partials" / "dropdown_menu_v1.html"
REPORT_TEMPLATE = APP / "templates" / "reports" / "pcgdmn_template_report.html"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = EXPORTS / f"backup_bai_13b_12_v2_4_2_{STAMP}"
DB_BACKUP = BACKUP / "phocap.db"
REPORT = EXPORTS / f"bao_cao_cai_bai_13b_12_v2_4_2_{STAMP}.txt"

MARKER_ROUTER = "BAI_13B_12_V2_4_2_MN_SINGLE_SHEET_EXPORT"
MARKER_MENU = "BAI_13B_12_V2_4_2_MN_7_REPORT_MENU"
MARKER_TEMPLATE = "BAI_13B_12_V2_4_2_MN_SELECTED_SHEET"

CONSTANT_NEEDLE = 'DATA_STATE_LABELS = {\n    "": "Tất cả trạng thái dữ liệu",\n    "HAS_DATA": "Đã có dữ liệu",\n    "NO_DATA": "Chưa có dữ liệu",\n    "LOCKED": "Đã khóa số liệu",\n    "OPEN": "Dữ liệu đang mở",\n}\n'
CONSTANT_REPLACEMENT = 'DATA_STATE_LABELS = {\n    "": "Tất cả trạng thái dữ liệu",\n    "HAS_DATA": "Đã có dữ liệu",\n    "NO_DATA": "Chưa có dữ liệu",\n    "LOCKED": "Đã khóa số liệu",\n    "OPEN": "Dữ liệu đang mở",\n}\n\n\n# === BAI_13B_12_V2_4_2_MN_SINGLE_SHEET_EXPORT_START ===\nSINGLE_SHEET_EXPORTS = {\n    "tre-khuyet-tat": {\n        "sheet_name": "MN- Trẻ KT",\n        "label": "MN-Trẻ KT – Thống kê trẻ khuyết tật",\n        "filename": "MN_Tre_KT",\n    },\n    "so-theo-doi": {\n        "sheet_name": "Sổ theo dõi PCGDMN",\n        "label": "Sổ theo dõi PCGDMN",\n        "filename": "So_theo_doi_PCGDMN",\n    },\n}\n# === BAI_13B_12_V2_4_2_MN_SINGLE_SHEET_EXPORT_END ===\n'
PAGE_SIGNATURE_OLD = 'def report_page(\n    request: Request,\n    school_year_id: str = "",\n    commune_id: str = "",\n    school_id: str = "",\n    data_state: str = "",\n    db: Session = Depends(get_db),\n) -> HTMLResponse:\n'
PAGE_SIGNATURE_NEW = 'def report_page(\n    request: Request,\n    school_year_id: str = "",\n    commune_id: str = "",\n    school_id: str = "",\n    data_state: str = "",\n    sheet_code: str = "",\n    db: Session = Depends(get_db),\n) -> HTMLResponse:\n'
PAGE_START_OLD = 'def report_page(\n    request: Request,\n    school_year_id: str = "",\n    commune_id: str = "",\n    school_id: str = "",\n    data_state: str = "",\n    sheet_code: str = "",\n    db: Session = Depends(get_db),\n) -> HTMLResponse:\n    normalized_state = str(data_state or "").strip().upper()\n    if normalized_state not in DATA_STATE_LABELS:\n        normalized_state = ""\n    context = _load_context(\n'
PAGE_START_NEW = 'def report_page(\n    request: Request,\n    school_year_id: str = "",\n    commune_id: str = "",\n    school_id: str = "",\n    data_state: str = "",\n    sheet_code: str = "",\n    db: Session = Depends(get_db),\n) -> HTMLResponse:\n    normalized_state = str(data_state or "").strip().upper()\n    if normalized_state not in DATA_STATE_LABELS:\n        normalized_state = ""\n\n    normalized_sheet_code = str(sheet_code or "").strip().lower()\n    selected_sheet = SINGLE_SHEET_EXPORTS.get(normalized_sheet_code)\n    if selected_sheet is None:\n        normalized_sheet_code = ""\n\n    context = _load_context(\n'
EXPORT_QUERY_OLD = '    export_query = urlencode(export_params)\n    return templates.TemplateResponse(\n'
EXPORT_QUERY_NEW = '    export_query = urlencode(export_params)\n\n    if normalized_sheet_code:\n        export_url = (\n            "/bao-cao/pcgdmn-mau-2025/xuat-bieu/"\n            + normalized_sheet_code\n            + "?"\n            + export_query\n        )\n    else:\n        export_url = (\n            "/bao-cao/pcgdmn-mau-2025/xuat-excel?"\n            + export_query\n        )\n\n    return templates.TemplateResponse(\n'
CONTEXT_OLD = '            "export_url": "/bao-cao/pcgdmn-mau-2025/xuat-excel?" + export_query,\n'
CONTEXT_NEW = '            "export_url": export_url,\n            "sheet_code": normalized_sheet_code,\n            "selected_sheet_label": (\n                selected_sheet["label"] if selected_sheet is not None else ""\n            ),\n'
END_EXPORT_NEEDLE = '    return StreamingResponse(\n        output,\n        media_type=(\n            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"\n        ),\n        headers={\n            "Content-Disposition": f\'attachment; filename="{filename}"\',\n        },\n    )\n'
SINGLE_EXPORT_ROUTE = '\n\n# === BAI_13B_12_V2_4_2_MN_SINGLE_SHEET_EXPORT_ROUTE_START ===\n@router.get("/xuat-bieu/{sheet_code}")\ndef export_single_sheet_excel(\n    sheet_code: str,\n    request: Request,\n    school_year_id: str = "",\n    commune_id: str = "",\n    school_id: str = "",\n    data_state: str = "",\n    db: Session = Depends(get_db),\n) -> StreamingResponse:\n    normalized_sheet_code = str(sheet_code or "").strip().lower()\n    sheet_spec = SINGLE_SHEET_EXPORTS.get(normalized_sheet_code)\n    if sheet_spec is None:\n        raise ValueError("Mã biểu Mầm non không hợp lệ.")\n\n    normalized_state = str(data_state or "").strip().upper()\n    if normalized_state not in DATA_STATE_LABELS:\n        normalized_state = ""\n\n    context = _load_context(\n        db=db,\n        request=request,\n        school_year_id=_parse_optional_int(school_year_id),\n        commune_id=_parse_optional_int(commune_id),\n        school_id=_parse_optional_int(school_id),\n        data_state=normalized_state,\n    )\n\n    workbook = build_template_workbook(\n        db=db,\n        context=context,\n    )\n\n    target_sheet = next(\n        (\n            ws\n            for ws in workbook.worksheets\n            if ws.title.strip() == sheet_spec["sheet_name"]\n        ),\n        None,\n    )\n    if target_sheet is None:\n        raise RuntimeError(\n            "Tệp mẫu không có trang " + sheet_spec["sheet_name"]\n        )\n\n    for ws in list(workbook.worksheets):\n        if ws is not target_sheet:\n            workbook.remove(ws)\n\n    target_sheet.sheet_state = "visible"\n    workbook.active = 0\n\n    output = BytesIO()\n    workbook.save(output)\n    output.seek(0)\n\n    year_code = context["report_data"]["school_year"].code.replace("-", "_")\n    scope_code = "toan_tinh"\n    if context.get("selected_school") is not None:\n        scope_code = f"truong_{context[\'selected_school\'].code}"\n    elif context.get("selected_commune") is not None:\n        scope_code = f"xa_{context[\'selected_commune\'].code}"\n\n    filename = (\n        f"{sheet_spec[\'filename\']}_{year_code}_{scope_code}.xlsx"\n    )\n\n    return StreamingResponse(\n        output,\n        media_type=(\n            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"\n        ),\n        headers={\n            "Content-Disposition": f\'attachment; filename="{filename}"\',\n        },\n    )\n# === BAI_13B_12_V2_4_2_MN_SINGLE_SHEET_EXPORT_ROUTE_END ===\n'
MENU_OLD = '                            <a href="/bao-cao/mn-01-te" role="menuitem">5.2.1. MN-01-TE – Thống kê trẻ em Mầm non theo độ tuổi</a>\n                            <a href="/bao-cao?report_type=PCGD_MN_02_2025" role="menuitem">5.2.2. MN-02 – Kết quả PCGD Mầm non</a>\n                            <a href="/bao-cao/mn-01-gv-bgd" role="menuitem">5.2.3. MN-01-GV – Thống kê đội ngũ CBQL, giáo viên, nhân viên</a>\n                            <a href="/bao-cao?report_type=PCGD_MN_01_CSVC_2025" role="menuitem">5.2.4. MN-01-CSVC – Cơ sở vật chất</a>\n                            <a href="/bao-cao?report_type=PCGD_MN_TAICHINH_2025" role="menuitem">5.2.5. MN-TC – Báo cáo tài chính</a>\n\n                            {# === BAI_13B_3_FINANCE_INPUT_MENU_START === #}\n                            {% if menu_role in [\'ADMIN\', \'SO\', \'XA\'] %}\n                            <a href="/bao-cao/tai-chinh/nhap" role="menuitem">5.2.6. Nhập dữ liệu BC-Tài chính</a>\n                            {% endif %}\n                            {# === BAI_13B_3_FINANCE_INPUT_MENU_END === #}\n'
MENU_NEW = '                            {# === BAI_13B_12_V2_4_2_MN_7_REPORT_MENU_START === #}\n                            <a href="/bao-cao/mn-01-te" role="menuitem">5.2.1. MN-01-TE – Thống kê trẻ em Mầm non theo độ tuổi</a>\n                            <a href="/bao-cao?report_type=PCGD_MN_02_2025" role="menuitem">5.2.2. MN-02 – Kết quả PCGD Mầm non</a>\n                            <a href="/bao-cao/mn-01-gv-bgd" role="menuitem">5.2.3. MN-01-GV – Thống kê đội ngũ CBQL, giáo viên, nhân viên</a>\n                            <a href="/bao-cao?report_type=PCGD_MN_01_CSVC_2025" role="menuitem">5.2.4. MN-01-CSVC – Cơ sở vật chất</a>\n                            <a href="/bao-cao?report_type=PCGD_MN_TAICHINH_2025" role="menuitem">5.2.5. MN-TC – Báo cáo tài chính</a>\n                            <a href="/bao-cao/pcgdmn-mau-2025?sheet_code=tre-khuyet-tat" role="menuitem">5.2.6. MN-Trẻ KT – Thống kê trẻ khuyết tật</a>\n                            <a href="/bao-cao/pcgdmn-mau-2025?sheet_code=so-theo-doi" role="menuitem">5.2.7. Sổ theo dõi PCGDMN</a>\n                            {# === BAI_13B_12_V2_4_2_MN_7_REPORT_MENU_END === #}\n\n                            {# === BAI_13B_3_FINANCE_INPUT_MENU_START === #}\n                            {% if menu_role in [\'ADMIN\', \'SO\', \'XA\'] %}\n                            <a href="/bao-cao/tai-chinh/nhap" role="menuitem">5.2.8. Nhập dữ liệu BC-Tài chính</a>\n                            {% endif %}\n                            {# === BAI_13B_3_FINANCE_INPUT_MENU_END === #}\n'
TITLE_OLD = '            <h1>Xuất bộ biểu mẫu PCGDMN 2025 đúng tệp Excel mẫu</h1>\n            <p>Sao chép nguyên khuôn mẫu, giữ bố cục và điền dữ liệu vào đúng trang biểu.</p>\n'
TITLE_NEW = '            {# === BAI_13B_12_V2_4_2_MN_SELECTED_SHEET_START === #}\n            <h1>{% if selected_sheet_label %}{{ selected_sheet_label }}{% else %}Xuất bộ biểu mẫu PCGDMN 2025 đúng tệp Excel mẫu{% endif %}</h1>\n            <p>{% if selected_sheet_label %}Xuất riêng đúng trang biểu trong tệp mẫu gốc, giữ nguyên bố cục và vùng in.{% else %}Sao chép nguyên khuôn mẫu, giữ bố cục và điền dữ liệu vào đúng trang biểu.{% endif %}</p>\n            {# === BAI_13B_12_V2_4_2_MN_SELECTED_SHEET_END === #}\n'
BUTTON_OLD = '            <a class="button button-success" href="{{ export_url }}">📊 Xuất đúng file Excel mẫu</a>\n'
BUTTON_NEW = '            <a class="button button-success" href="{{ export_url }}">📊 {% if selected_sheet_label %}Xuất biểu Excel đúng mẫu{% else %}Xuất đúng file Excel mẫu{% endif %}</a>\n'
FORM_OLD = '        <form method="get" action="/bao-cao/pcgdmn-mau-2025">\n            <div class="filters">\n'
FORM_NEW = '        <form method="get" action="/bao-cao/pcgdmn-mau-2025">\n            {% if sheet_code %}<input type="hidden" name="sheet_code" value="{{ sheet_code }}">{% endif %}\n            <div class="filters">\n'


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def write_text(path: Path, value: str) -> None:
    path.write_text(value, encoding="utf-8")


def backup_file(path: Path) -> None:
    target = BACKUP / path.relative_to(PROJECT)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, target)


def restore_file(path: Path) -> None:
    source = BACKUP / path.relative_to(PROJECT)
    if source.exists():
        shutil.copy2(source, path)


def backup_db() -> None:
    src = sqlite3.connect(str(DB))
    dst = sqlite3.connect(str(DB_BACKUP))
    try:
        src.backup(dst)
        dst.commit()
    finally:
        dst.close()
        src.close()


def restore_db() -> None:
    if not DB_BACKUP.exists():
        return
    src = sqlite3.connect(str(DB_BACKUP))
    dst = sqlite3.connect(str(DB))
    try:
        src.backup(dst)
        dst.commit()
    finally:
        dst.close()
        src.close()


def db_state() -> dict:
    con = sqlite3.connect(str(DB))
    try:
        return {
            "integrity": str(
                con.execute("PRAGMA integrity_check").fetchone()[0]
            ),
            "fk_count": len(
                con.execute("PRAGMA foreign_key_check").fetchall()
            ),
        }
    finally:
        con.close()


def patch_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(
            f"{label}: số marker khớp = {count}, mong đợi 1."
        )
    return source.replace(old, new, 1)


def verify_source() -> None:
    router = read_text(ROUTER)
    menu = read_text(MENU)
    html = read_text(REPORT_TEMPLATE)

    for token in (
        MARKER_ROUTER,
        "SINGLE_SHEET_EXPORTS",
        "export_single_sheet_excel",
        'sheet_name": "MN- Trẻ KT"',
        'sheet_name": "Sổ theo dõi PCGDMN"',
    ):
        if token not in router:
            raise RuntimeError("Verifier router thiếu: " + token)

    for token in (
        MARKER_MENU,
        "5.2.6. MN-Trẻ KT",
        "5.2.7. Sổ theo dõi PCGDMN",
        "5.2.8. Nhập dữ liệu BC-Tài chính",
    ):
        if token not in menu:
            raise RuntimeError("Verifier menu thiếu: " + token)

    if MARKER_TEMPLATE not in html:
        raise RuntimeError("Verifier template thiếu marker biểu chọn.")

    ast.parse(router)
    py_compile.compile(str(ROUTER), doraise=True)
    Environment().parse(menu)
    Environment().parse(html)


def main() -> int:
    print("=" * 122)
    print(
        "BÀI 13B-12 V2.4.2 - "
        "BÁO CÁO MẦM NON ĐỦ 7 BIỂU THEO MẪU GỐC"
    )
    print("=" * 122)

    for path in (DB, ROUTER, MENU, REPORT_TEMPLATE):
        if not path.exists():
            print("DỪNG AN TOÀN: thiếu", path)
            return 2

    before = db_state()
    print("integrity_check:", before["integrity"])
    print("foreign_key_check:", before["fk_count"], "lỗi")

    if before["integrity"].lower() != "ok" or before["fk_count"] != 0:
        print("DỪNG: database chưa đạt kiểm tra.")
        return 3

    router = read_text(ROUTER)
    menu = read_text(MENU)
    html = read_text(REPORT_TEMPLATE)

    if (
        MARKER_ROUTER in router
        and MARKER_MENU in menu
        and MARKER_TEMPLATE in html
    ):
        print("V2.4.2 đã cài. Không cài lặp.")
        return 0

    try:
        new_router = patch_once(
            router, CONSTANT_NEEDLE, CONSTANT_REPLACEMENT, "Patch hằng số biểu"
        )
        new_router = patch_once(
            new_router,
            PAGE_SIGNATURE_OLD,
            PAGE_SIGNATURE_NEW,
            "Patch tham số sheet_code",
        )
        new_router = patch_once(
            new_router,
            PAGE_START_OLD,
            PAGE_START_NEW,
            "Patch xử lý sheet_code",
        )
        new_router = patch_once(
            new_router,
            EXPORT_QUERY_OLD,
            EXPORT_QUERY_NEW,
            "Patch export_url",
        )
        new_router = patch_once(
            new_router,
            CONTEXT_OLD,
            CONTEXT_NEW,
            "Patch context",
        )
        new_router = patch_once(
            new_router,
            END_EXPORT_NEEDLE,
            END_EXPORT_NEEDLE + SINGLE_EXPORT_ROUTE,
            "Patch route xuất riêng",
        )

        new_menu = patch_once(menu, MENU_OLD, MENU_NEW, "Patch menu 7 biểu")

        new_html = patch_once(html, TITLE_OLD, TITLE_NEW, "Patch tiêu đề biểu")
        new_html = patch_once(new_html, BUTTON_OLD, BUTTON_NEW, "Patch nút xuất")
        new_html = patch_once(
            new_html, FORM_OLD, FORM_NEW, "Patch giữ sheet_code khi lọc"
        )

        ast.parse(new_router)
        Environment().parse(new_menu)
        Environment().parse(new_html)

    except Exception as exc:
        print()
        print("DỪNG AN TOÀN TRƯỚC KHI GHI FILE:")
        print(type(exc).__name__ + ":", exc)
        return 4

    EXPORTS.mkdir(parents=True, exist_ok=True)
    BACKUP.mkdir(parents=True, exist_ok=False)

    for path in (ROUTER, MENU, REPORT_TEMPLATE):
        backup_file(path)
    backup_db()
    print("Backup:", BACKUP)

    try:
        write_text(ROUTER, new_router)
        write_text(MENU, new_menu)
        write_text(REPORT_TEMPLATE, new_html)

        verify_source()

        after = db_state()
        if after["integrity"].lower() != "ok":
            raise RuntimeError("integrity_check không đạt sau cài.")
        if after["fk_count"] != 0:
            raise RuntimeError("foreign_key_check có lỗi sau cài.")

        for cache in APP.rglob("__pycache__"):
            if cache.is_dir():
                shutil.rmtree(cache, ignore_errors=True)

    except Exception as exc:
        print()
        print("CÓ LỖI - ĐANG ROLLBACK SOURCE + DATABASE...")
        print(type(exc).__name__ + ":", exc)
        restore_file(ROUTER)
        restore_file(MENU)
        restore_file(REPORT_TEMPLATE)
        restore_db()
        print("ĐÃ KHÔI PHỤC.")
        return 9

    REPORT.write_text(
        "\n".join(
            [
                "=" * 122,
                "BÁO CÁO CÀI BÀI 13B-12 V2.4.2",
                "=" * 122,
                f"Thời gian: {datetime.now():%d/%m/%Y %H:%M:%S}",
                "",
                "MENU 5.2 SAU KHI CÀI:",
                "5.2.1 MN-01-TE",
                "5.2.2 MN-02",
                "5.2.3 MN-01-GV",
                "5.2.4 MN-01-CSVC",
                "5.2.5 MN-TC",
                "5.2.6 MN-Trẻ KT",
                "5.2.7 Sổ theo dõi PCGDMN",
                "",
                "Nhập dữ liệu BC-Tài chính chuyển xuống 5.2.8 và không tính là biểu báo cáo.",
                "",
                "Hai biểu bổ sung lấy trực tiếp đúng sheet của Bieu_mau_PCGDMN_2025.xlsx:",
                "- MN- Trẻ KT",
                "- Sổ theo dõi PCGDMN",
                "",
                "Trang lọc năm học/xã/trường được giữ; khi mở 5.2.6/5.2.7, nút xuất chỉ xuất đúng biểu đã chọn.",
                "",
                "Không sửa dữ liệu lúc cài.",
                f"integrity_check: {after['integrity']}",
                f"foreign_key_check: {after['fk_count']} lỗi",
                f"Backup: {BACKUP}",
            ]
        )
        + "\n",
        encoding="utf-8-sig",
    )

    print()
    print("=" * 122)
    print("CÀI ĐẶT THÀNH CÔNG BÀI 13B-12 V2.4.2")
    print("=" * 122)
    print(" - Menu Báo cáo Mầm non đã đủ 7 biểu.")
    print(" - MN-Trẻ KT và Sổ theo dõi xuất riêng đúng sheet mẫu gốc.")
    print(" - Không thay dữ liệu.")
    print("Báo cáo:", REPORT)
    print("Backup:", BACKUP)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
