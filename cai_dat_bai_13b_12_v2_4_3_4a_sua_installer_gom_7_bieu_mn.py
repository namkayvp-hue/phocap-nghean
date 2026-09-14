# -*- coding: utf-8 -*-
from __future__ import annotations

import ast
import py_compile
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

PROJECT = Path(r"C:\PhoCap")
APP = PROJECT / "app"
DB = PROJECT / "data" / "phocap.db"
EXPORTS = PROJECT / "exports"

MASTER = APP / "routers" / "pcgdmn_template_report.py"
MENU = APP / "templates" / "partials" / "dropdown_menu_v1.html"
OFFICIAL = APP / "routers" / "mn_official_reports.py"
CENTER = APP / "routers" / "report_center.py"
SURVEY = APP / "routers" / "survey_summary_report.py"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = EXPORTS / f"backup_bai_13b_12_v2_4_3_4a_{STAMP}"
DB_BACKUP = BACKUP / "phocap.db"
REPORT = EXPORTS / f"bao_cao_cai_bai_13b_12_v2_4_3_4a_{STAMP}.txt"

MARKER_MASTER = "BAI_13B_12_V2_4_3_4_SINGLE_PIPELINE_7_MN"
MARKER_MENU = "BAI_13B_12_V2_4_3_4_MENU_7_MN_SINGLE_PIPELINE"
MARKER_OFFICIAL = "BAI_13B_12_V2_4_3_4_LEGACY_REDIRECT"
MARKER_CENTER = "BAI_13B_12_V2_4_3_4_REPORT_CENTER_REDIRECT"

SHEET_EXPORTS = '# === BAI_13B_12_V2_4_3_4_SINGLE_PIPELINE_7_MN ===\nSINGLE_SHEET_EXPORTS = {\n    "mn-01-te": {\n        "sheet_name": "MN-01 TE",\n        "label": "MN-01-TE – Thống kê trẻ em Mầm non theo độ tuổi",\n        "filename": "MN-01-TE",\n    },\n    "mn-02": {\n        "sheet_name": "MN-02",\n        "label": "MN-02 – Kết quả PCGD Mầm non",\n        "filename": "MN-02",\n    },\n    "mn-01-gv": {\n        "sheet_name": "MN-01 GV",\n        "label": "MN-01-GV – Thống kê đội ngũ CBQL, giáo viên, nhân viên",\n        "filename": "MN-01-GV",\n    },\n    "mn-01-csvc": {\n        "sheet_name": "MN-01 CSVC",\n        "label": "MN-01-CSVC – Cơ sở vật chất",\n        "filename": "MN-01-CSVC",\n    },\n    "mn-tc": {\n        "sheet_name": "MN - Tài chính",\n        "label": "MN-TC – Báo cáo tài chính",\n        "filename": "MN-TC",\n    },\n    "tre-khuyet-tat": {\n        "sheet_name": "MN- Trẻ KT",\n        "label": "MN-Trẻ KT – Thống kê trẻ khuyết tật",\n        "filename": "MN_Tre_KT",\n    },\n    "so-theo-doi": {\n        "sheet_name": "Sổ theo dõi PCGDMN",\n        "label": "Sổ theo dõi PCGDMN",\n        "filename": "So_theo_doi_PCGDMN",\n    },\n}\n'
OLD_TO_NEW = '# === BAI_13B_12_V2_4_3_4_LEGACY_REDIRECT ===\nOLD_TO_NEW = {\n    "PCGD_MN_M1_2025": "mn-01-te",\n    "PCGD_MN_02_2025": "mn-02",\n    "PCGD_MN_01_GV_2025": "mn-01-gv",\n    "PCGD_MN_01_CSVC_2025": "mn-01-csvc",\n    "PCGD_MN_TAICHINH_2025": "mn-tc",\n}\n'
NEW_INSTALL_REDIRECTS = 'def install_mn_official_report_redirects(app) -> None:\n    """\n    V2.4.3.4:\n    Giữ tương thích link/mã báo cáo Mầm non cũ, nhưng toàn bộ\n    5 mã report_type cũ được đưa về cùng pipeline master 7 sheet.\n    """\n    if getattr(app.state, "_mn_official_reports_v1_redirect", False):\n        return\n    app.state._mn_official_reports_v1_redirect = True\n\n    @app.middleware("http")\n    async def _mn_report_redirect(request: Request, call_next):\n        if (\n            request.method in {"GET", "HEAD"}\n            and request.url.path.startswith("/bao-cao")\n        ):\n            old_code = request.query_params.get("report_type")\n            sheet_code = OLD_TO_NEW.get(str(old_code or ""))\n            if sheet_code:\n                params = [\n                    (key, value)\n                    for key, value in request.query_params.multi_items()\n                    if key != "report_type"\n                ]\n\n                is_export = "xuat" in request.url.path.lower()\n                if is_export:\n                    target = (\n                        "/bao-cao/pcgdmn-mau-2025/xuat-bieu/"\n                        + sheet_code\n                    )\n                else:\n                    target = "/bao-cao/pcgdmn-mau-2025"\n                    params.append(("sheet_code", sheet_code))\n\n                query = urlencode(params)\n                return RedirectResponse(\n                    url=target + (f"?{query}" if query else ""),\n                    status_code=303,\n                )\n\n        return await call_next(request)\n'
NEW_TE_PAGE = 'def mn01te_page(\n    request: Request,\n    school_year_id: str | None = None,\n    commune_id: str | None = None,\n    school_id: str | None = None,\n    db: Session = Depends(get_db),\n):\n    params = [("sheet_code", "mn-01-te")]\n    if school_year_id not in (None, ""):\n        params.append(("school_year_id", str(school_year_id)))\n    if commune_id not in (None, ""):\n        params.append(("commune_id", str(commune_id)))\n    if school_id not in (None, ""):\n        params.append(("school_id", str(school_id)))\n\n    return RedirectResponse(\n        url="/bao-cao/pcgdmn-mau-2025?" + urlencode(params),\n        status_code=303,\n    )\n'
NEW_GV_PAGE = 'def mn01gv_bgd_page(\n    request: Request,\n    school_year_id: str | None = None,\n    commune_id: str | None = None,\n    school_id: str | None = None,\n    db: Session = Depends(get_db),\n):\n    params = [("sheet_code", "mn-01-gv")]\n    if school_year_id not in (None, ""):\n        params.append(("school_year_id", str(school_year_id)))\n    if commune_id not in (None, ""):\n        params.append(("commune_id", str(commune_id)))\n    if school_id not in (None, ""):\n        params.append(("school_id", str(school_id)))\n\n    return RedirectResponse(\n        url="/bao-cao/pcgdmn-mau-2025?" + urlencode(params),\n        status_code=303,\n    )\n'
NEW_TE_EXPORT = 'def mn01te_export(\n    request: Request,\n    school_year_id: str | None = None,\n    commune_id: str | None = None,\n    school_id: str | None = None,\n    db: Session = Depends(get_db),\n):\n    params = []\n    if school_year_id not in (None, ""):\n        params.append(("school_year_id", str(school_year_id)))\n    if commune_id not in (None, ""):\n        params.append(("commune_id", str(commune_id)))\n    if school_id not in (None, ""):\n        params.append(("school_id", str(school_id)))\n\n    query = urlencode(params)\n    return RedirectResponse(\n        url=(\n            "/bao-cao/pcgdmn-mau-2025/xuat-bieu/mn-01-te"\n            + (f"?{query}" if query else "")\n        ),\n        status_code=303,\n    )\n'
NEW_GV_EXPORT = 'def mn01gv_bgd_export(\n    request: Request,\n    school_year_id: str | None = None,\n    commune_id: str | None = None,\n    school_id: str | None = None,\n    db: Session = Depends(get_db),\n):\n    params = []\n    if school_year_id not in (None, ""):\n        params.append(("school_year_id", str(school_year_id)))\n    if commune_id not in (None, ""):\n        params.append(("commune_id", str(commune_id)))\n    if school_id not in (None, ""):\n        params.append(("school_id", str(school_id)))\n\n    query = urlencode(params)\n    return RedirectResponse(\n        url=(\n            "/bao-cao/pcgdmn-mau-2025/xuat-bieu/mn-01-gv"\n            + (f"?{query}" if query else "")\n        ),\n        status_code=303,\n    )\n'
CENTER_HELPER = '# === BAI_13B_12_V2_4_3_4_REPORT_CENTER_REDIRECT ===\n_V2434_MN_MASTER_SHEETS = {\n    "PCGD_MN_M1_2025": "mn-01-te",\n    "PCGD_MN_02_2025": "mn-02",\n    "PCGD_MN_01_GV_2025": "mn-01-gv",\n    "PCGD_MN_01_CSVC_2025": "mn-01-csvc",\n    "PCGD_MN_TAICHINH_2025": "mn-tc",\n}\n\n\ndef _v2434_mn_master_redirect(\n    report_type: str,\n    *,\n    school_year_id: str,\n    commune_id: str,\n    school_id: str,\n    is_export: bool,\n):\n    sheet_code = _V2434_MN_MASTER_SHEETS.get(\n        str(report_type or "").strip().upper()\n    )\n    if not sheet_code:\n        return None\n\n    params = []\n    if school_year_id not in (None, ""):\n        params.append(("school_year_id", str(school_year_id)))\n    if commune_id not in (None, ""):\n        params.append(("commune_id", str(commune_id)))\n    if school_id not in (None, ""):\n        params.append(("school_id", str(school_id)))\n\n    if is_export:\n        target = (\n            "/bao-cao/pcgdmn-mau-2025/xuat-bieu/"\n            + sheet_code\n        )\n    else:\n        target = "/bao-cao/pcgdmn-mau-2025"\n        params.append(("sheet_code", sheet_code))\n\n    query = urlencode(params)\n    return RedirectResponse(\n        url=target + (f"?{query}" if query else ""),\n        status_code=303,\n    )\n'
CENTER_PAGE_INSERT = '    # === BAI_13B_12_V2_4_3_4_REPORT_CENTER_REDIRECT_PAGE ===\n    _v2434_redirect = _v2434_mn_master_redirect(\n        normalized_report_type,\n        school_year_id=school_year_id,\n        commune_id=commune_id,\n        school_id=school_id,\n        is_export=False,\n    )\n    if _v2434_redirect is not None:\n        return _v2434_redirect\n'
CENTER_EXPORT_INSERT = '    # === BAI_13B_12_V2_4_3_4_REPORT_CENTER_REDIRECT_EXPORT ===\n    _v2434_redirect = _v2434_mn_master_redirect(\n        normalized_report_type,\n        school_year_id=school_year_id,\n        commune_id=commune_id,\n        school_id=school_id,\n        is_export=True,\n    )\n    if _v2434_redirect is not None:\n        return _v2434_redirect\n'
MENU_BLOCK = '                            {# === BAI_13B_12_V2_4_3_4_MENU_7_MN_SINGLE_PIPELINE === #}\n                            <a href="/bao-cao/pcgdmn-mau-2025?sheet_code=mn-01-te" role="menuitem">5.2.1. MN-01-TE – Thống kê trẻ em Mầm non theo độ tuổi</a>\n                            <a href="/bao-cao/pcgdmn-mau-2025?sheet_code=mn-02" role="menuitem">5.2.2. MN-02 – Kết quả PCGD Mầm non</a>\n                            <a href="/bao-cao/pcgdmn-mau-2025?sheet_code=mn-01-gv" role="menuitem">5.2.3. MN-01-GV – Thống kê đội ngũ CBQL, giáo viên, nhân viên</a>\n                            <a href="/bao-cao/pcgdmn-mau-2025?sheet_code=mn-01-csvc" role="menuitem">5.2.4. MN-01-CSVC – Cơ sở vật chất</a>\n                            <a href="/bao-cao/pcgdmn-mau-2025?sheet_code=mn-tc" role="menuitem">5.2.5. MN-TC – Báo cáo tài chính</a>\n                            <a href="/bao-cao/pcgdmn-mau-2025?sheet_code=tre-khuyet-tat" role="menuitem">5.2.6. MN-Trẻ KT – Thống kê trẻ khuyết tật</a>\n                            <a href="/bao-cao/pcgdmn-mau-2025?sheet_code=so-theo-doi" role="menuitem">5.2.7. Sổ theo dõi PCGDMN</a>\n'


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="replace")


def write_text(path: Path, value: str) -> None:
    path.write_text(value, encoding="utf-8")


def db_state() -> dict:
    con = sqlite3.connect(str(DB))
    try:
        result = {
            "integrity": str(con.execute("PRAGMA integrity_check").fetchone()[0]),
            "fk_count": len(con.execute("PRAGMA foreign_key_check").fetchall()),
        }
        for table in (
            "survey_forms",
            "survey_people",
            "survey_person_year_records",
            "staff_year_records",
        ):
            result[table] = int(
                con.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            )
        return result
    finally:
        con.close()


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


def function_node(tree: ast.Module, name: str):
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise RuntimeError(f"Không xác định được hàm {name} bằng AST.")


def assignment_node(tree: ast.Module, name: str):
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return node
        if isinstance(node, ast.AnnAssign):
            target = node.target
            if isinstance(target, ast.Name) and target.id == name:
                return node
    raise RuntimeError(f"Không xác định được biến {name} bằng AST.")


def replace_node(source: str, node: ast.AST, replacement: str) -> str:
    lines = source.splitlines(keepends=True)
    start = int(node.lineno) - 1
    end = int(getattr(node, "end_lineno", node.lineno) or node.lineno)
    value = replacement
    if not value.endswith("\n"):
        value += "\n"
    result = "".join(lines[:start] + [value] + lines[end:])
    ast.parse(result)
    return result


def replace_function(source: str, name: str, replacement: str) -> str:
    tree = ast.parse(source)
    return replace_node(source, function_node(tree, name), replacement)


def replace_assignment(source: str, name: str, replacement: str) -> str:
    tree = ast.parse(source)
    return replace_node(source, assignment_node(tree, name), replacement)


def insert_before_function(source: str, name: str, block: str) -> str:
    tree = ast.parse(source)
    node = function_node(tree, name)
    lines = source.splitlines(keepends=True)

    # V2.4.3.4A:
    # FunctionDef.lineno trỏ vào dòng "def", KHÔNG trỏ vào decorator.
    # Nếu chèn helper giữa @router.get(...) và def thì Python báo SyntaxError.
    # Vì vậy phải chèn TRƯỚC decorator đầu tiên (nếu có).
    start_lineno = int(node.lineno)
    decorator_lines = [
        int(item.lineno)
        for item in getattr(node, "decorator_list", [])
        if getattr(item, "lineno", None)
    ]
    if decorator_lines:
        start_lineno = min([start_lineno] + decorator_lines)

    index = start_lineno - 1
    value = block
    if not value.endswith("\n"):
        value += "\n"

    # Tách helper khỏi decorator/def bằng một dòng trống.
    value = value.rstrip("\n") + "\n\n"

    result = "".join(lines[:index] + [value] + lines[index:])
    ast.parse(result)
    return result


def ensure_redirect_import(source: str) -> str:
    tree = ast.parse(source)

    # Nếu đã import RedirectResponse thật sự thì giữ nguyên.
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module == "fastapi.responses":
            if any(alias.name == "RedirectResponse" for alias in node.names):
                return source

    # V2.4.3.4A:
    # Thêm một import độc lập, không sửa import hiện có.
    # Cách này an toàn cả khi source dùng:
    # from fastapi.responses import (
    #     HTMLResponse,
    #     ...
    # )
    lines = source.splitlines(keepends=True)

    insert_at = 0
    for i, line in enumerate(lines):
        if line.startswith("from __future__ import "):
            insert_at = i + 1

    lines.insert(
        insert_at,
        "from fastapi.responses import RedirectResponse\n",
    )
    result = "".join(lines)
    ast.parse(result)
    return result


def patch_master(source: str) -> str:
    if MARKER_MASTER in source:
        return source

    for token in (
        "SINGLE_SHEET_EXPORTS",
        "def build_template_workbook(",
        "def export_single_sheet_excel(",
        "BAI_13B_12_V2_4_3_TEMPLATE_HELPERS_START",
        "_v243_normalize_year_labels",
    ):
        if token not in source:
            raise RuntimeError(
                "pcgdmn_template_report.py khác nền V2.4.3. Thiếu: " + token
            )

    source = replace_assignment(source, "SINGLE_SHEET_EXPORTS", SHEET_EXPORTS)
    ast.parse(source)
    return source


def patch_menu(source: str) -> str:
    if MARKER_MENU in source:
        return source

    start_marker = "{# === BAI_13B_12_V2_4_2_MN_7_REPORT_MENU_START === #}"
    end_marker = "{# === BAI_13B_12_V2_4_2_MN_7_REPORT_MENU_END === #}"

    if source.count(start_marker) != 1 or source.count(end_marker) != 1:
        raise RuntimeError("Menu 7 biểu không có đúng một cặp marker V2.4.2.")

    start = source.index(start_marker)
    end = source.index(end_marker, start) + len(end_marker)

    replacement = (
        start_marker
        + "\n"
        + MENU_BLOCK.rstrip()
        + "\n                            "
        + end_marker
    )
    return source[:start] + replacement + source[end:]


def patch_official(source: str) -> str:
    if MARKER_OFFICIAL in source:
        return source

    for token in (
        "OLD_TO_NEW",
        "def mn01te_page(",
        "def mn01gv_bgd_page(",
        "def mn01te_export(",
        "def mn01gv_bgd_export(",
        "def install_mn_official_report_redirects(",
    ):
        if token not in source:
            raise RuntimeError(
                "mn_official_reports.py khác nền khảo sát. Thiếu: " + token
            )

    source = ensure_redirect_import(source)
    source = replace_assignment(source, "OLD_TO_NEW", OLD_TO_NEW)
    source = replace_function(source, "mn01te_page", NEW_TE_PAGE)
    source = replace_function(source, "mn01gv_bgd_page", NEW_GV_PAGE)
    source = replace_function(source, "mn01te_export", NEW_TE_EXPORT)
    source = replace_function(source, "mn01gv_bgd_export", NEW_GV_EXPORT)
    source = replace_function(
        source,
        "install_mn_official_report_redirects",
        NEW_INSTALL_REDIRECTS,
    )
    ast.parse(source)
    return source


def insert_after_report_type_guard(
    source: str,
    function_name: str,
    block: str,
) -> str:
    tree = ast.parse(source)
    node = function_node(tree, function_name)
    lines = source.splitlines(keepends=True)
    start = node.lineno - 1
    end = int(getattr(node, "end_lineno", node.lineno) or node.lineno)

    target = None
    for i in range(start, min(end, start + 140)):
        if "normalized_report_type not in REPORT_TYPES" in lines[i]:
            target = i + 2
            break

    if target is None:
        raise RuntimeError(
            f"Không tìm thấy guard report_type trong {function_name}."
        )

    value = block
    if not value.endswith("\n"):
        value += "\n"

    result = "".join(lines[:target] + [value] + lines[target:])
    ast.parse(result)
    return result


def patch_center(source: str) -> str:
    if MARKER_CENTER in source:
        return source

    for token in (
        "def report_center_page(",
        "def export_report_catalog_excel(",
        "PCGD_MN_EXPORT_V1_6B_START",
        "export_mn_report",
    ):
        if token not in source:
            raise RuntimeError(
                "report_center.py khác nền khảo sát. Thiếu: " + token
            )

    source = ensure_redirect_import(source)
    source = insert_before_function(source, "report_center_page", CENTER_HELPER)
    source = insert_after_report_type_guard(
        source,
        "report_center_page",
        CENTER_PAGE_INSERT,
    )
    source = insert_after_report_type_guard(
        source,
        "export_report_catalog_excel",
        CENTER_EXPORT_INSERT,
    )
    ast.parse(source)
    return source


def dict_value_from_source(source: str, name: str):
    tree = ast.parse(source)
    node = assignment_node(tree, name)
    return ast.literal_eval(node.value)


def verify_sources() -> None:
    master = read_text(MASTER)
    menu = read_text(MENU)
    official = read_text(OFFICIAL)
    center = read_text(CENTER)

    for marker, text, label in (
        (MARKER_MASTER, master, "master"),
        (MARKER_MENU, menu, "menu"),
        (MARKER_OFFICIAL, official, "official"),
        (MARKER_CENTER, center, "center"),
    ):
        if marker not in text:
            raise RuntimeError(f"Verifier {label} thiếu marker.")

    expected = {
        "mn-01-te": "MN-01 TE",
        "mn-02": "MN-02",
        "mn-01-gv": "MN-01 GV",
        "mn-01-csvc": "MN-01 CSVC",
        "mn-tc": "MN - Tài chính",
        "tre-khuyet-tat": "MN- Trẻ KT",
        "so-theo-doi": "Sổ theo dõi PCGDMN",
    }

    actual = dict_value_from_source(master, "SINGLE_SHEET_EXPORTS")
    if set(actual) != set(expected):
        raise RuntimeError("SINGLE_SHEET_EXPORTS chưa đủ đúng 7 mã.")

    for code, sheet_name in expected.items():
        if actual[code]["sheet_name"] != sheet_name:
            raise RuntimeError(
                f"Sai sheet_name cho {code}: {actual[code]['sheet_name']!r}"
            )
        href = "/bao-cao/pcgdmn-mau-2025?sheet_code=" + code
        if href not in menu:
            raise RuntimeError("Menu chưa trỏ master: " + code)

    required_legacy = {
        "PCGD_MN_M1_2025": "mn-01-te",
        "PCGD_MN_02_2025": "mn-02",
        "PCGD_MN_01_GV_2025": "mn-01-gv",
        "PCGD_MN_01_CSVC_2025": "mn-01-csvc",
        "PCGD_MN_TAICHINH_2025": "mn-tc",
    }
    legacy = dict_value_from_source(official, "OLD_TO_NEW")
    if legacy != required_legacy:
        raise RuntimeError("OLD_TO_NEW chưa đúng mapping master.")

    for token in (
        "/bao-cao/pcgdmn-mau-2025/xuat-bieu/mn-01-te",
        "/bao-cao/pcgdmn-mau-2025/xuat-bieu/mn-01-gv",
        "sheet_code = OLD_TO_NEW.get",
    ):
        if token not in official:
            raise RuntimeError("Verifier official thiếu: " + token)

    for token in (
        "_V2434_MN_MASTER_SHEETS",
        "REPORT_CENTER_REDIRECT_PAGE",
        "REPORT_CENTER_REDIRECT_EXPORT",
        "/bao-cao/pcgdmn-mau-2025/xuat-bieu/",
    ):
        if token not in center:
            raise RuntimeError("Verifier center thiếu: " + token)

    ast.parse(master)
    ast.parse(official)
    ast.parse(center)

    py_compile.compile(str(MASTER), doraise=True)
    py_compile.compile(str(OFFICIAL), doraise=True)
    py_compile.compile(str(CENTER), doraise=True)

    try:
        from jinja2 import Environment
        Environment().parse(menu)
    except Exception as exc:
        raise RuntimeError("Jinja menu không hợp lệ: " + str(exc)) from exc


def main() -> int:
    print("=" * 126)
    print("BÀI 13B-12 V2.4.3.4A - SỬA INSTALLER + GOM 7 BIỂU MẦM NON VỀ MỘT PIPELINE MASTER")
    print("=" * 126)

    for path in (DB, MASTER, MENU, OFFICIAL, CENTER, SURVEY):
        if not path.exists():
            print("DỪNG AN TOÀN: thiếu", path)
            return 2

    if (
        "BAI_13B_12_V2_4_3_TEMPLATE_HELPERS_START" not in read_text(MASTER)
        or
        "BAI_13B_12_V2_4_3_REPORT_SCOPE_HELPERS_START" not in read_text(SURVEY)
    ):
        print("DỪNG AN TOÀN: chưa thấy đầy đủ marker V2.4.3.")
        return 3

    before = db_state()
    print("integrity_check:", before["integrity"])
    print("foreign_key_check:", before["fk_count"], "lỗi")

    if before["integrity"].lower() != "ok" or before["fk_count"] != 0:
        print("DỪNG: database chưa đạt kiểm tra an toàn.")
        return 4

    try:
        print("Kiểm tra/chuẩn bị patch master...")
        patched_master = patch_master(read_text(MASTER))

        print("Kiểm tra/chuẩn bị patch menu...")
        patched_menu = patch_menu(read_text(MENU))

        print("Kiểm tra/chuẩn bị patch route MN chính thức cũ...")
        patched_official = patch_official(read_text(OFFICIAL))

        print("Kiểm tra/chuẩn bị patch Trung tâm báo cáo...")
        patched_center = patch_center(read_text(CENTER))
    except Exception as exc:
        print()
        print("DỪNG AN TOÀN TRƯỚC KHI GHI SOURCE:")
        print(type(exc).__name__ + ":", exc)
        print("Không có source/database nào bị thay đổi.")
        return 5

    EXPORTS.mkdir(parents=True, exist_ok=True)
    BACKUP.mkdir(parents=True, exist_ok=False)

    for path in (MASTER, MENU, OFFICIAL, CENTER):
        backup_file(path)
    backup_db()
    print("Backup:", BACKUP)

    try:
        write_text(MASTER, patched_master)
        write_text(MENU, patched_menu)
        write_text(OFFICIAL, patched_official)
        write_text(CENTER, patched_center)

        verify_sources()

        after = db_state()
        if after["integrity"].lower() != "ok":
            raise RuntimeError("integrity_check không đạt sau cài.")
        if after["fk_count"] != 0:
            raise RuntimeError("foreign_key_check có lỗi sau cài.")

        for table in (
            "survey_forms",
            "survey_people",
            "survey_person_year_records",
            "staff_year_records",
        ):
            if after[table] != before[table]:
                raise RuntimeError(
                    f"Số bản ghi {table} thay đổi ngoài dự kiến."
                )

        for cache in APP.rglob("__pycache__"):
            if cache.is_dir():
                shutil.rmtree(cache, ignore_errors=True)

    except Exception as exc:
        print()
        print("CÓ LỖI - ĐANG ROLLBACK SOURCE + DATABASE...")
        print(type(exc).__name__ + ":", exc)
        for path in (MASTER, MENU, OFFICIAL, CENTER):
            restore_file(path)
        restore_db()
        print("ĐÃ KHÔI PHỤC.")
        return 9

    REPORT.write_text(
        "\n".join(
            [
                "=" * 126,
                "BÁO CÁO CÀI BÀI 13B-12 V2.4.3.4A",
                "=" * 126,
                f"Thời gian: {datetime.now():%d/%m/%Y %H:%M:%S}",
                "",
                "NGUYÊN NHÂN ĐÃ KHÓA TỪ V2.4.3.3:",
                "- 5.2.1 và 5.2.3 đi qua mn_official_reports.py.",
                "- 5.2.2 / 5.2.4 / 5.2.5 đi qua report_center.py rồi pcgd_mn_report_builders_v1.",
                "- Chỉ 5.2.6 / 5.2.7 đi qua pcgdmn_template_report.py.",
                "- Vì vậy V2.4.3 sửa pipeline master nhưng 5 biểu khác vẫn dùng builder cũ.",
                "",
                "V2.4.3.4 ĐÃ SỬA:",
                "- SINGLE_SHEET_EXPORTS mở đủ 7 sheet chính thức.",
                "- Menu 5.2.1 -> 5.2.7 cùng trỏ /bao-cao/pcgdmn-mau-2025.",
                "- Các link report_type Mầm non cũ redirect về master.",
                "- Các route cũ MN-01-TE / MN-01-GV cũng redirect về master.",
                "- Không xóa route cũ, chỉ giữ tương thích.",
                "",
                "KHÔNG THAY:",
                "- build_template_workbook V2.4.3;",
                "- logic tuổi/scope/fallback tên trường V2.4.3;",
                "- Excel điều tra 2.2.3 / 2.2.4;",
                "- dữ liệu điều tra;",
                "- PCGD/XMC;",
                "- phân công/giao phiếu/nhập nhanh.",
                "",
                f"integrity_check: {after['integrity']}",
                f"foreign_key_check: {after['fk_count']} lỗi",
                f"Backup: {BACKUP}",
            ]
        ) + "\n",
        encoding="utf-8-sig",
    )

    print()
    print("=" * 126)
    print("CÀI ĐẶT THÀNH CÔNG BÀI 13B-12 V2.4.3.4A")
    print("=" * 126)
    print(" - 7 biểu cùng một pipeline master: ĐẠT.")
    print(" - Link cũ được giữ tương thích: ĐẠT.")
    print(" - Không sửa dữ liệu hiện có.")
    print("Báo cáo:", REPORT)
    print("Backup:", BACKUP)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
