from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path

PROJECT = Path(os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")).resolve()
APP = PROJECT / "app"
EXPORTS = PROJECT / "exports"

GV = APP / "templates" / "report_inputs" / "gv_mn01.html"
CSVC = APP / "templates" / "report_inputs" / "csvc_mn01.html"
MENU = APP / "templates" / "partials" / "dropdown_menu_v1.html"
REPORT_CENTER = APP / "routers" / "report_center.py"
LEVEL_TEMPLATE = APP / "templates" / "reports" / "level_report_center.html"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = EXPORTS / f"backup_bai_13b_4_v1_{STAMP}"
MANIFEST = BACKUP / "manifest.json"

GV_SCRIPT = '\n<!-- === BAI_13B_4_V1_CASCADE_GV_START === -->\n<style>\n    .b134-disabled {\n        opacity: .55 !important;\n        cursor: not-allowed !important;\n    }\n</style>\n<script>\n(function () {\n    const form = document.querySelector(\'form[method="get"][action="/doi-ngu/nhap-mn-01-gv"]\');\n    if (!form) return;\n\n    const year = form.querySelector(\'select[name="school_year_id"]\');\n    const commune = form.querySelector(\'select[name="commune_id"]\');\n    const school = form.querySelector(\'select[name="school_id"]\');\n    const openButton = form.querySelector(\'button[type="submit"]\');\n\n    function syncOpenButton() {\n        if (!openButton || !school) return;\n        const disabled = !school.value;\n        openButton.disabled = disabled;\n        openButton.classList.toggle(\'b134-disabled\', disabled);\n        openButton.title = disabled ? \'Hãy chọn trường trước\' : \'Mở dữ liệu của trường đã chọn\';\n    }\n\n    function reloadSchools() {\n        if (school) school.value = \'\';\n        form.submit();\n    }\n\n    if (commune) {\n        commune.addEventListener(\'change\', reloadSchools);\n    }\n\n    if (year) {\n        year.addEventListener(\'change\', function () {\n            if (school) school.value = \'\';\n            form.submit();\n        });\n    }\n\n    if (school) {\n        school.addEventListener(\'change\', syncOpenButton);\n    }\n\n    syncOpenButton();\n})();\n</script>\n<!-- === BAI_13B_4_V1_CASCADE_GV_END === -->\n'
CSVC_SCRIPT = '\n<!-- === BAI_13B_4_V1_CASCADE_CSVC_START === -->\n<style>\n    .b134-disabled {\n        opacity: .55 !important;\n        cursor: not-allowed !important;\n    }\n</style>\n<script>\n(function () {\n    const form = document.querySelector(\'form[method="get"][action^="/csvc/"]\');\n    if (!form) return;\n\n    const year = form.querySelector(\'select[name="school_year_id"]\');\n    const commune = form.querySelector(\'select[name="commune_id"]\');\n    const school = form.querySelector(\'select[name="school_id"]\');\n    const openButton = form.querySelector(\'button\');\n\n    function syncOpenButton() {\n        if (!openButton || !school) return;\n        const disabled = !school.value;\n        openButton.disabled = disabled;\n        openButton.classList.toggle(\'b134-disabled\', disabled);\n        openButton.title = disabled ? \'Hãy chọn trường trước\' : \'Mở dữ liệu của trường đã chọn\';\n    }\n\n    function reloadSchools() {\n        if (school) school.value = \'\';\n        form.submit();\n    }\n\n    if (commune) {\n        commune.addEventListener(\'change\', reloadSchools);\n    }\n\n    if (year) {\n        year.addEventListener(\'change\', function () {\n            if (school) school.value = \'\';\n            form.submit();\n        });\n    }\n\n    if (school) {\n        school.addEventListener(\'change\', syncOpenButton);\n    }\n\n    syncOpenButton();\n})();\n</script>\n<!-- === BAI_13B_4_V1_CASCADE_CSVC_END === -->\n'
LEVEL_TEMPLATE_CONTENT = '<!DOCTYPE html>\n<html lang="vi">\n<head>\n    <meta charset="UTF-8">\n    <meta name="viewport" content="width=device-width, initial-scale=1.0">\n    <title>{{ level.title }}</title>\n    <link rel="stylesheet" href="/static/css/style.css">\n    <style>\n        :root{\n            --blue:#0f5fa8;--blue2:#1976d2;--bg:#eef4f9;--line:#d7e4ef;\n            --text:#17324d;--green:#198f42;--amber:#a66a00;\n        }\n        *{box-sizing:border-box}\n        body{margin:0;background:var(--bg);color:var(--text);font-family:Arial,sans-serif}\n        .hero{background:linear-gradient(135deg,#0f5fa8,#1682d6);color:#fff;padding:30px 3vw}\n        .hero-inner,.wrap{max-width:1280px;margin:auto}\n        .hero h1{margin:7px 0 8px;font-size:32px}\n        .hero p{margin:0;opacity:.93;line-height:1.5}\n        .eyebrow{font-weight:900;letter-spacing:.08em;font-size:13px}\n        .wrap{padding:22px 3vw 50px}\n        .panel{background:#fff;border:1px solid var(--line);border-radius:16px;padding:20px;margin-bottom:18px;box-shadow:0 7px 22px rgba(23,50,77,.05)}\n        .filters{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}\n        .field label{display:block;font-weight:800;margin:0 0 7px}\n        .field select{width:100%;min-height:45px;border:1px solid #bfd0df;border-radius:10px;padding:9px 11px;background:#fff;font:inherit}\n        .actions{display:flex;align-items:end;gap:9px;flex-wrap:wrap}\n        .btn{display:inline-flex;align-items:center;justify-content:center;min-height:44px;border:0;border-radius:10px;padding:10px 14px;text-decoration:none;font-weight:800;cursor:pointer}\n        .primary{background:var(--blue2);color:#fff}.success{background:var(--green);color:#fff}.secondary{background:#e7eef5;color:var(--text)}\n        .scope{margin-top:14px;padding:12px 14px;border-radius:11px;background:#eaf4ff;font-weight:800}\n        .notice{padding:14px;border:1px solid #eed194;border-radius:12px;background:#fff7e5;color:#7b570b;margin-bottom:18px;line-height:1.5}\n        .cards{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:15px}\n        .card{background:#fff;border:1px solid var(--line);border-radius:15px;padding:18px;box-shadow:0 6px 18px rgba(23,50,77,.05)}\n        .card-head{display:flex;align-items:flex-start;justify-content:space-between;gap:12px}\n        .card h3{margin:0;font-size:20px}.card p{color:#6b8195;line-height:1.5;min-height:46px}\n        .badge{display:inline-block;border-radius:999px;padding:6px 9px;font-size:12px;font-weight:900;white-space:nowrap}\n        .ready{background:#e5f6ea;color:#19743b}.partial{background:#fff1ca;color:#8a5c00}\n        .card-actions{display:flex;gap:9px;flex-wrap:wrap;margin-top:14px}\n        .summary{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin-bottom:18px}\n        .summary-card{background:#fff;border-radius:15px;padding:17px;border:1px solid var(--line)}\n        .summary-card span{display:block;color:#6b8195;font-weight:700}.summary-card strong{display:block;margin-top:7px;font-size:26px;color:var(--blue)}\n        .disabled{opacity:.55;cursor:not-allowed}\n        @media(max-width:850px){.filters,.cards,.summary{grid-template-columns:1fr 1fr}}\n        @media(max-width:620px){.filters,.cards,.summary{grid-template-columns:1fr}.wrap{padding:12px}.panel,.card{padding:14px}.hero{padding:24px 16px}.hero h1{font-size:25px}.actions .btn{width:100%}}\n    </style>\n</head>\n<body>\n{% include \'partials/dropdown_menu_v1.html\' %}\n\n<header class="hero">\n    <div class="hero-inner">\n        <div class="eyebrow">BÀI 13B-4 · TRUNG TÂM BÁO CÁO THEO CẤP HỌC</div>\n        <h1>{{ level.title }}</h1>\n        <p>{{ level.description }}</p>\n    </div>\n</header>\n\n<main class="wrap">\n    <section class="panel">\n        <h2 style="margin-top:0">Chọn năm học và phạm vi báo cáo</h2>\n        <form method="get" action="{{ level.path }}" id="b134-level-filter">\n            <div class="filters">\n                <div class="field">\n                    <label>Năm học</label>\n                    <select name="school_year_id">\n                        {% for y in school_years %}\n                        <option value="{{ y.id }}" {% if y.id == selected_year_id %}selected{% endif %}>{{ y.code }}</option>\n                        {% endfor %}\n                    </select>\n                </div>\n                <div class="field">\n                    <label>Xã/phường</label>\n                    <select name="commune_id">\n                        {% if province_reader %}<option value="">-- Toàn tỉnh --</option>{% endif %}\n                        {% for c in communes %}\n                        <option value="{{ c.id }}" {% if c.id == selected_commune_id %}selected{% endif %}>{{ c.name }}</option>\n                        {% endfor %}\n                    </select>\n                </div>\n                <div class="field">\n                    <label>Trường</label>\n                    <select name="school_id">\n                        <option value="">-- Tất cả trường trong phạm vi --</option>\n                        {% for s in schools %}\n                        <option value="{{ s.id }}" {% if s.id == selected_school_id %}selected{% endif %}>{{ s.name }}</option>\n                        {% endfor %}\n                    </select>\n                </div>\n                <div class="actions">\n                    <button class="btn primary" type="submit">Mở phạm vi</button>\n                    <a class="btn secondary" href="{{ level.path }}">Xóa lọc</a>\n                </div>\n            </div>\n        </form>\n        <div class="scope">Phạm vi đang xem: {{ scope_label }}{% if selected_year %} · Năm học {{ selected_year.code }}{% endif %}</div>\n    </section>\n\n    <div class="summary">\n        <div class="summary-card"><span>Số biểu trong bộ</span><strong>{{ cards|length }}</strong></div>\n        <div class="summary-card"><span>Biểu có tự động tổng hợp</span><strong>{{ ready_count }}</strong></div>\n        <div class="summary-card"><span>Nguyên tắc</span><strong style="font-size:18px">Không suy diễn dữ liệu</strong></div>\n    </div>\n\n    <div class="notice">\n        <strong>Nguyên tắc lập báo cáo:</strong>\n        dùng đúng mẫu Excel đã có trong hệ thống; chỉ tự động điền các chỉ tiêu có nguồn dữ liệu rõ ràng.\n        Chỉ tiêu chưa có trường dữ liệu chuyên biệt được để trống để tránh kết luận sai.\n    </div>\n\n    <section class="cards">\n        {% for card in cards %}\n        <article class="card">\n            <div class="card-head">\n                <div>\n                    <h3>{{ card.title }}</h3>\n                    <p>{{ card.description }}</p>\n                </div>\n                <span class="badge {{ card.status_class }}">{{ card.status }}</span>\n            </div>\n            <div class="card-actions">\n                <a class="btn secondary" href="{{ card.open_url }}">Mở báo cáo</a>\n                <a class="btn success" href="{{ card.export_url }}">Xuất Excel mẫu</a>\n            </div>\n        </article>\n        {% endfor %}\n    </section>\n</main>\n\n<script>\n(function () {\n    const form = document.getElementById(\'b134-level-filter\');\n    if (!form) return;\n    const year = form.querySelector(\'select[name="school_year_id"]\');\n    const commune = form.querySelector(\'select[name="commune_id"]\');\n    const school = form.querySelector(\'select[name="school_id"]\');\n\n    if (commune) {\n        commune.addEventListener(\'change\', function () {\n            if (school) school.value = \'\';\n            form.submit();\n        });\n    }\n    if (year) {\n        year.addEventListener(\'change\', function () {\n            if (school) school.value = \'\';\n            form.submit();\n        });\n    }\n})();\n</script>\n</body>\n</html>\n'
ROUTE_BLOCK = '\n# === BAI_13B_4_V1_LEVEL_REPORT_CENTERS_START ===\n\n_B134_LEVEL_REPORTS = {\n    "tieu-hoc": {\n        "title": "Bộ báo cáo Phổ cập giáo dục Tiểu học",\n        "description": "Tập hợp các biểu Tiểu học hiện có, dùng cùng bộ lọc năm học – xã/phường – trường và xuất trực tiếp đúng mẫu Excel.",\n        "path": "/bao-cao/tieu-hoc",\n        "reports": [\n            ("PCGD_TH_M1_2025", "TH-M1 – Phổ cập giáo dục Tiểu học", "Tự động tổng hợp dữ liệu điều tra độ tuổi Tiểu học.", "Sẵn sàng", "ready"),\n            ("PCGD_TH_02_2025", "TH-02 – Kết quả PCGD Tiểu học", "Tự động tổng hợp các chỉ tiêu kết quả PCGD Tiểu học có nguồn dữ liệu.", "Sẵn sàng", "ready"),\n            ("PCGD_TH_01_GV_2025", "TH-01-GV – Đội ngũ giáo viên", "Lấy dữ liệu từ phân hệ Đội ngũ theo năm học và phạm vi.", "Sẵn sàng", "ready"),\n            ("PCGD_TH_01_CSVC_2025", "TH-01-CSVC – Cơ sở vật chất", "Điền các chỉ tiêu hiện có; chỉ tiêu CSVC chưa có nguồn chuyên biệt được để trống.", "Theo dữ liệu hiện có", "partial"),\n        ],\n    },\n    "thcs": {\n        "title": "Bộ báo cáo Phổ cập giáo dục THCS",\n        "description": "Tập hợp các biểu THCS hiện có, dùng cùng bộ lọc năm học – xã/phường – trường và xuất trực tiếp đúng mẫu Excel.",\n        "path": "/bao-cao/thcs",\n        "reports": [\n            ("PCGD_THCS_M1_2025", "THCS-M1 – Phổ cập giáo dục THCS", "Tự động tổng hợp đối tượng, học lớp 6–9, hoàn thành và tốt nghiệp theo dữ liệu điều tra.", "Sẵn sàng", "ready"),\n            ("PCGD_THCS_M2_2025", "THCS-M2 – Tiêu chuẩn PCGD THCS", "Tự động tổng hợp các chỉ tiêu tiêu chuẩn có nguồn dữ liệu rõ ràng.", "Sẵn sàng", "ready"),\n            ("PCGD_THCS_TK_2025", "THCS-TK – Thống kê kết quả", "Tự động tổng hợp kết quả PCGD THCS theo phạm vi.", "Sẵn sàng", "ready"),\n            ("PCGD_THCS_M5_2025", "THCS-M5 – Đội ngũ giáo viên", "Lấy dữ liệu từ phân hệ Đội ngũ theo năm học và phạm vi.", "Sẵn sàng", "ready"),\n            ("PCGD_THCS_CSVC_2025", "THCS-CSVC – Cơ sở vật chất", "Điền các chỉ tiêu hiện có; chỉ tiêu CSVC chưa có nguồn chuyên biệt được để trống.", "Theo dữ liệu hiện có", "partial"),\n        ],\n    },\n    "xoa-mu-chu": {\n        "title": "Bộ báo cáo Xóa mù chữ",\n        "description": "Tập hợp các biểu XMC/CMC hiện có, tổng hợp theo năm học và phạm vi điều tra, xuất trực tiếp đúng mẫu Excel.",\n        "path": "/bao-cao/xoa-mu-chu",\n        "reports": [\n            ("PCGD_XMC_3_2025", "XMC-3 – Tổng hợp kết quả xóa mù chữ", "Tự động tổng hợp dân số theo nhóm tuổi và các chỉ tiêu có nguồn dữ liệu.", "Theo dữ liệu hiện có", "partial"),\n            ("PCGD_CMC_2_2025", "CMC-2 – Thống kê số người mù chữ", "Tự động điền các chỉ tiêu có thể xác định từ hồ sơ điều tra.", "Theo dữ liệu hiện có", "partial"),\n            ("PCGD_CMC_1_2025", "CMC-1 – Tổng hợp chống mù chữ", "Tự động tổng hợp dân số và các nhóm tuổi theo phạm vi.", "Theo dữ liệu hiện có", "partial"),\n            ("PCGD_XMC_4_2025", "XMC-4 – Thống kê đạt chuẩn xóa mù chữ", "Tự động điền các chỉ tiêu có nguồn; mức biết chữ chuyên biệt chưa có nguồn sẽ để trống.", "Theo dữ liệu hiện có", "partial"),\n        ],\n    },\n}\n\n\ndef _b134_level_center_context(\n    *,\n    level_code: str,\n    request: Request,\n    db: Session,\n    school_year_id: int | None,\n    commune_id: int | None,\n    school_id: int | None,\n) -> dict[str, Any]:\n    level = _B134_LEVEL_REPORTS[level_code]\n    user = lay_thong_tin_nguoi_dung(request)\n    years = _load_school_years(db)\n    selected_year_id = _choose_year_id(years, school_year_id)\n    communes, schools, selected_commune_id, selected_school_id, scope_label = _load_scope_options(\n        db,\n        user,\n        commune_id,\n        school_id,\n    )\n    selected_year = next(\n        (item for item in years if item.id == selected_year_id),\n        None,\n    )\n\n    base_params: dict[str, Any] = {\n        "school_year_id": selected_year_id or "",\n    }\n    if selected_commune_id is not None:\n        base_params["commune_id"] = selected_commune_id\n    if selected_school_id is not None:\n        base_params["school_id"] = selected_school_id\n\n    cards: list[dict[str, Any]] = []\n    for report_type, title, description, status, status_class in level["reports"]:\n        open_params = dict(base_params)\n        open_params["report_type"] = report_type\n        export_params = dict(open_params)\n        cards.append(\n            {\n                "report_type": report_type,\n                "title": title,\n                "description": description,\n                "status": status,\n                "status_class": status_class,\n                "open_url": "/bao-cao?" + urlencode(open_params),\n                "export_url": "/bao-cao/xuat-danh-muc-excel?" + urlencode(export_params),\n            }\n        )\n\n    return {\n        "nguoi_dung": user,\n        "level": level,\n        "school_years": years,\n        "selected_year_id": selected_year_id,\n        "selected_year": selected_year,\n        "communes": communes,\n        "schools": schools,\n        "selected_commune_id": selected_commune_id,\n        "selected_school_id": selected_school_id,\n        "scope_label": scope_label,\n        "province_reader": is_province_reader(normalize_role_code(user.get("role_code"))),\n        "cards": cards,\n        "ready_count": sum(1 for item in cards if item["status_class"] == "ready"),\n    }\n\n\n@router.get("/tieu-hoc", response_class=HTMLResponse)\ndef b134_primary_report_center(\n    request: Request,\n    school_year_id: int | None = None,\n    commune_id: int | None = None,\n    school_id: int | None = None,\n    db: Session = Depends(get_db),\n):\n    return templates.TemplateResponse(\n        request=request,\n        name="reports/level_report_center.html",\n        context=_b134_level_center_context(\n            level_code="tieu-hoc",\n            request=request,\n            db=db,\n            school_year_id=school_year_id,\n            commune_id=commune_id,\n            school_id=school_id,\n        ),\n    )\n\n\n@router.get("/thcs", response_class=HTMLResponse)\ndef b134_thcs_report_center(\n    request: Request,\n    school_year_id: int | None = None,\n    commune_id: int | None = None,\n    school_id: int | None = None,\n    db: Session = Depends(get_db),\n):\n    return templates.TemplateResponse(\n        request=request,\n        name="reports/level_report_center.html",\n        context=_b134_level_center_context(\n            level_code="thcs",\n            request=request,\n            db=db,\n            school_year_id=school_year_id,\n            commune_id=commune_id,\n            school_id=school_id,\n        ),\n    )\n\n\n@router.get("/xoa-mu-chu", response_class=HTMLResponse)\ndef b134_literacy_report_center(\n    request: Request,\n    school_year_id: int | None = None,\n    commune_id: int | None = None,\n    school_id: int | None = None,\n    db: Session = Depends(get_db),\n):\n    return templates.TemplateResponse(\n        request=request,\n        name="reports/level_report_center.html",\n        context=_b134_level_center_context(\n            level_code="xoa-mu-chu",\n            request=request,\n            db=db,\n            school_year_id=school_year_id,\n            commune_id=commune_id,\n            school_id=school_id,\n        ),\n    )\n\n# === BAI_13B_4_V1_LEVEL_REPORT_CENTERS_END ===\n'
MENU_LINKS = {'PCGD_TH_M1_2025': '\n                            {# === BAI_13B_4_V1_PRIMARY_CENTER_MENU_START === #}\n                            <a href="/bao-cao/tieu-hoc" role="menuitem"><strong>5.3.0. Bộ báo cáo Tiểu học</strong></a>\n                            {# === BAI_13B_4_V1_PRIMARY_CENTER_MENU_END === #}\n', 'PCGD_THCS_M1_2025': '\n                            {# === BAI_13B_4_V1_THCS_CENTER_MENU_START === #}\n                            <a href="/bao-cao/thcs" role="menuitem"><strong>5.4.0. Bộ báo cáo THCS</strong></a>\n                            {# === BAI_13B_4_V1_THCS_CENTER_MENU_END === #}\n', 'PCGD_XMC_3_2025': '\n                            {# === BAI_13B_4_V1_XMC_CENTER_MENU_START === #}\n                            <a href="/bao-cao/xoa-mu-chu" role="menuitem"><strong>5.5.0. Bộ báo cáo Xóa mù chữ</strong></a>\n                            {# === BAI_13B_4_V1_XMC_CENTER_MENU_END === #}\n'}

MODIFIED = [
    "app/templates/report_inputs/gv_mn01.html",
    "app/templates/report_inputs/csvc_mn01.html",
    "app/templates/partials/dropdown_menu_v1.html",
    "app/routers/report_center.py",
    "app/templates/reports/level_report_center.html",
]


def _read(path: Path) -> str:
    if not path.exists():
        raise RuntimeError(f"Không tìm thấy tệp bắt buộc: {path}")
    return path.read_text(encoding="utf-8-sig")


def _backup(rel: str, manifest: list[dict]) -> None:
    src = PROJECT / rel
    existed = src.exists()
    manifest.append({"path": rel, "existed": existed})
    if existed:
        dst = BACKUP / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def _restore(manifest: list[dict]) -> None:
    for item in reversed(manifest):
        target = PROJECT / item["path"]
        if item["existed"]:
            src = BACKUP / item["path"]
            if src.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, target)
        elif target.exists():
            target.unlink()


def _append_before_body_end(text: str, block: str, marker: str) -> str:
    if marker in text:
        return text
    if "</body>" not in text:
        raise RuntimeError("Không tìm thấy </body> để chèn mã hỗ trợ.")
    return text.replace("</body>", block + "\n</body>", 1)


def _patch_menu(text: str) -> str:
    anchors = [
        (
            "BAI_13B_4_V1_PRIMARY_CENTER_MENU_START",
            '<a href="/bao-cao?report_type=PCGD_TH_M1_2025" role="menuitem">',
            MENU_LINKS["PCGD_TH_M1_2025"],
        ),
        (
            "BAI_13B_4_V1_THCS_CENTER_MENU_START",
            '<a href="/bao-cao?report_type=PCGD_THCS_M1_2025" role="menuitem">',
            MENU_LINKS["PCGD_THCS_M1_2025"],
        ),
        (
            "BAI_13B_4_V1_XMC_CENTER_MENU_START",
            '<a href="/bao-cao?report_type=PCGD_XMC_3_2025" role="menuitem">',
            MENU_LINKS["PCGD_XMC_3_2025"],
        ),
    ]
    for marker, anchor, block in anchors:
        if marker in text:
            continue
        if anchor not in text:
            raise RuntimeError(f"Không tìm thấy điểm chèn menu: {anchor}")
        text = text.replace(anchor, block + "\n" + anchor, 1)
    return text


def _patch_report_center(text: str) -> str:
    if "BAI_13B_4_V1_LEVEL_REPORT_CENTERS_START" in text:
        return text
    return text.rstrip() + "\n\n" + ROUTE_BLOCK.strip() + "\n"


def _check_templates() -> None:
    from jinja2 import Environment, FileSystemLoader
    env = Environment(loader=FileSystemLoader(str(APP / "templates")))
    for name in [
        "report_inputs/gv_mn01.html",
        "report_inputs/csvc_mn01.html",
        "reports/level_report_center.html",
        "partials/dropdown_menu_v1.html",
    ]:
        env.get_template(name)


def main() -> int:
    print("=" * 88)
    print("BÀI 13B-4 V1 - HOÀN THIỆN MENU NHẬP VÀ BÁO CÁO CÁC CẤP")
    print("=" * 88)
    print("Nguyên tắc: giữ nguyên phần đã chạy đúng, chỉ sửa lỗi lọc trường và bổ sung trung tâm báo cáo.")
    print("")

    for path in [GV, CSVC, MENU, REPORT_CENTER]:
        if not path.exists():
            raise RuntimeError(f"Không tìm thấy: {path}")

    # Chỉ cài trên đúng nền Bài 13B-3 V1.
    menu_before = _read(MENU)
    gv_before = _read(GV)
    csvc_before = _read(CSVC)
    report_before = _read(REPORT_CENTER)

    required = [
        ("menu nhập MN-01-GV", "BAI_13B_3_GV_REPORT_INPUT_MENU_START", menu_before),
        ("menu CSVC", "BAI_13B_3_CSVC_MENU_START", menu_before),
        ("menu tài chính", "BAI_13B_3_FINANCE_INPUT_MENU_START", menu_before),
        ("form MN-01-GV", 'action="/doi-ngu/nhap-mn-01-gv"', gv_before),
        ("form MN-01-CSVC", 'action="/csvc/{{ section }}"', csvc_before),
        ("báo cáo Tiểu học", "PCGD_TH_M1_2025", report_before),
        ("báo cáo THCS", "PCGD_THCS_M1_2025", report_before),
        ("báo cáo XMC", "PCGD_XMC_3_2025", report_before),
    ]
    for label, marker, text in required:
        if marker not in text:
            raise RuntimeError(f"Không tìm thấy {label}. Dừng để tránh sửa nhầm mã nguồn.")

    BACKUP.mkdir(parents=True, exist_ok=False)
    manifest: list[dict] = []
    for rel in MODIFIED:
        _backup(rel, manifest)
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    try:
        gv_text = _append_before_body_end(
            gv_before,
            GV_SCRIPT,
            "BAI_13B_4_V1_CASCADE_GV_START",
        )
        csvc_text = _append_before_body_end(
            csvc_before,
            CSVC_SCRIPT,
            "BAI_13B_4_V1_CASCADE_CSVC_START",
        )
        menu_text = _patch_menu(menu_before)
        report_text = _patch_report_center(report_before)

        GV.write_text(gv_text, encoding="utf-8")
        CSVC.write_text(csvc_text, encoding="utf-8")
        MENU.write_text(menu_text, encoding="utf-8")
        REPORT_CENTER.write_text(report_text, encoding="utf-8")
        LEVEL_TEMPLATE.parent.mkdir(parents=True, exist_ok=True)
        LEVEL_TEMPLATE.write_text(LEVEL_TEMPLATE_CONTENT, encoding="utf-8")

        subprocess.run(
            [sys.executable, "-m", "py_compile", str(REPORT_CENTER)],
            cwd=PROJECT,
            check=True,
        )
        _check_templates()

        checks = [
            ("GV lọc xã -> trường", "BAI_13B_4_V1_CASCADE_GV_START", _read(GV)),
            ("CSVC lọc xã -> trường", "BAI_13B_4_V1_CASCADE_CSVC_START", _read(CSVC)),
            ("Trung tâm Tiểu học", '"/tieu-hoc"', _read(REPORT_CENTER)),
            ("Trung tâm THCS", '"/thcs"', _read(REPORT_CENTER)),
            ("Trung tâm XMC", '"/xoa-mu-chu"', _read(REPORT_CENTER)),
            ("Menu Tiểu học", "BAI_13B_4_V1_PRIMARY_CENTER_MENU_START", _read(MENU)),
            ("Menu THCS", "BAI_13B_4_V1_THCS_CENTER_MENU_START", _read(MENU)),
            ("Menu XMC", "BAI_13B_4_V1_XMC_CENTER_MENU_START", _read(MENU)),
        ]
        for label, marker, text in checks:
            if marker not in text:
                raise RuntimeError(f"Kiểm tra không đạt: {label}")

        for cache in APP.rglob("__pycache__"):
            if cache.is_dir():
                shutil.rmtree(cache, ignore_errors=True)

        print("")
        print("ĐÃ HOÀN THIỆN:")
        print("  1. Đội ngũ → Nhập dữ liệu MN-01-GV")
        print("     - Đổi xã/phường: tự nạp lại danh sách trường đúng xã.")
        print("     - Chưa chọn trường: nút Mở dữ liệu được khóa.")
        print("     - Chọn trường: nút Mở dữ liệu hoạt động.")
        print("")
        print("  2. CSVC")
        print("     - Sửa cùng lỗi lọc xã/phường → trường cho cả 5 nhánh.")
        print("     - Giữ nguyên dữ liệu và biểu nhập đang có.")
        print("")
        print("  3. Báo cáo")
        print("     - Thêm Bộ báo cáo Tiểu học.")
        print("     - Thêm Bộ báo cáo THCS.")
        print("     - Thêm Bộ báo cáo Xóa mù chữ.")
        print("     - Mỗi bộ có bộ lọc năm học/xã/trường, Mở báo cáo và Xuất Excel mẫu.")
        print("")
        print("GIỮ NGUYÊN:")
        print("  - Báo cáo Mầm non đã có.")
        print("  - Dữ liệu điều tra, đội ngũ, CSVC, tài chính.")
        print("  - Database: KHÔNG thay đổi.")
        print("  - Giao diện giáo viên trên điện thoại: KHÔNG thay đổi.")
        print("")
        print("CAI DAT BAI 13B-4 V1 THANH CONG")
        print("Backup:", BACKUP)
        return 0

    except Exception:
        traceback.print_exc()
        print("")
        print("CÓ LỖI - ĐANG KHÔI PHỤC TỰ ĐỘNG...")
        _restore(manifest)
        print("ĐÃ KHÔI PHỤC MÃ NGUỒN VỀ TRƯỚC BÀI 13B-4 V1.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
