# -*- coding: utf-8 -*-
from __future__ import annotations

import ast
import re
import sqlite3
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

ROOT = Path(r"C:\PhoCap")
APP = ROOT / "app"
DB = ROOT / "data" / "phocap.db"
EXPORTS = ROOT / "exports"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
REPORT = EXPORTS / f"bao_cao_khao_sat_v2_4_0_excel_dieu_tra_7_bieu_mn_{STAMP}.txt"

CANDIDATE_FILES = [
    APP / "routers" / "surveys.py",
    APP / "routers" / "mn_official_reports.py",
    APP / "routers" / "pcgdmn_template_report.py",
    APP / "routers" / "report_center.py",
    APP / "templates" / "base.html",
    APP / "templates" / "surveys" / "households.html",
    APP / "templates" / "surveys" / "print_field_forms.html",
    APP / "templates" / "surveys" / "field_forms.html",
]

OFFICIAL_TEMPLATE = APP / "report_templates" / "Bieu_mau_PCGDMN_2025.xlsx"

KEYWORDS = [
    "phieu-in-thuc-dia",
    "xuat-excel",
    "nhap-excel",
    "Xuất Excel điều tra",
    "Nhập Excel cập nhật hộ dân",
    "phiếu điều tra",
    "phieu dieu tra",
    "openpyxl",
    "xlsxwriter",
    "Workbook",
    "load_workbook",
    "Bieu_mau_PCGDMN_2025.xlsx",
    "MN-01 TE",
    "MN-01 GV",
    "MN-01 CSVC",
    "MN-02",
    "MN - Tài chính",
    "MN- Trẻ KT",
    "Sổ theo dõi PCGDMN",
    "Báo cáo Mầm non",
    "5.2",
]


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="replace")


def excerpt(lines: list[str], center: int, before: int = 6, after: int = 10) -> list[str]:
    a = max(1, center - before)
    b = min(len(lines), center + after)
    result = []
    for i in range(a, b + 1):
        result.append(
            f"{'>>' if i == center else '  '} {i:05d}: {lines[i-1]}"
        )
    return result


def scan_file(report: list[str], path: Path, max_hits: int = 80) -> None:
    report.extend([
        "",
        "=" * 120,
        f"FILE: {path}",
        "=" * 120,
    ])

    if not path.exists():
        report.append("KHÔNG TỒN TẠI")
        return

    text = read_text(path)
    lines = text.splitlines()
    hits: list[int] = []

    for i, line in enumerate(lines, start=1):
        low = line.casefold()
        if any(k.casefold() in low for k in KEYWORDS):
            hits.append(i)

    report.append(f"Số dòng khớp từ khóa: {len(hits)}")

    shown = set()
    for pos in hits[:max_hits]:
        # tránh lặp quá nhiều đoạn chồng nhau
        bucket = pos // 12
        if bucket in shown:
            continue
        shown.add(bucket)
        report.append("")
        report.extend(excerpt(lines, pos, 8, 14))

    if len(hits) > max_hits:
        report.append(f"... còn {len(hits) - max_hits} vị trí khớp khác.")


def find_python_functions(report: list[str], path: Path) -> None:
    if not path.exists() or path.suffix.lower() != ".py":
        return

    source = read_text(path)
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        report.append(f"AST lỗi {path}: {exc}")
        return

    lines = source.splitlines()
    wanted = (
        "excel",
        "xlsx",
        "phieu",
        "field",
        "print",
        "report",
        "mn",
        "pcgd",
        "import",
        "export",
    )

    matches = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            name = node.name.casefold()
            if any(x in name for x in wanted):
                start = int(node.lineno)
                end = int(getattr(node, "end_lineno", node.lineno) or node.lineno)
                body = "\n".join(lines[start - 1:end])
                if any(k.casefold() in body.casefold() for k in KEYWORDS):
                    matches.append((node.name, start, end))

    if matches:
        report.extend([
            "",
            f"HÀM ỨNG VIÊN TRONG {path.name}:",
        ])
        for name, start, end in matches[:50]:
            report.append(f" - {name}: dòng {start}-{end}")


def xlsx_sheet_names(path: Path) -> list[str]:
    if not path.exists():
        return []

    with zipfile.ZipFile(path, "r") as zf:
        data = zf.read("xl/workbook.xml")

    root = ET.fromstring(data)
    ns = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    return [
        el.attrib.get("name", "")
        for el in root.findall("x:sheets/x:sheet", ns)
    ]


def find_all_relevant_files(report: list[str]) -> None:
    report.extend([
        "",
        "=" * 120,
        "TÌM FILE/ROUTE LIÊN QUAN TRONG TOÀN APP",
        "=" * 120,
    ])

    patterns = (
        "phieu-in-thuc-dia",
        "xuat-excel",
        "nhap-excel",
        "Bieu_mau_PCGDMN_2025",
        "Sổ theo dõi PCGDMN",
    )

    found = []
    for path in APP.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".py", ".html", ".js", ".txt"}:
            continue
        try:
            text = read_text(path)
        except Exception:
            continue
        if any(p.casefold() in text.casefold() for p in patterns):
            found.append(path)

    for path in sorted(found):
        report.append(f" - {path}")


def db_check(report: list[str]) -> None:
    report.extend([
        "",
        "=" * 120,
        "DATABASE SAFETY CHECK",
        "=" * 120,
    ])

    if not DB.exists():
        report.append(f"Không tìm thấy DB: {DB}")
        return

    con = sqlite3.connect(str(DB))
    try:
        integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
        fk = con.execute("PRAGMA foreign_key_check").fetchall()
        report.append(f"integrity_check: {integrity}")
        report.append(f"foreign_key_check: {len(fk)} lỗi")

        for table in ("survey_forms", "survey_people", "survey_person_year_records"):
            try:
                n = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                report.append(f"{table}: {n} bản ghi")
            except sqlite3.Error as exc:
                report.append(f"{table}: lỗi {exc}")
    finally:
        con.close()


def main() -> int:
    EXPORTS.mkdir(parents=True, exist_ok=True)

    report = [
        "=" * 120,
        "KHẢO SÁT BÀI 13B-12 V2.4.0 - EXCEL ĐIỀU TRA + 7 BIỂU MẦM NON",
        "=" * 120,
        f"Thời gian: {datetime.now():%d/%m/%Y %H:%M:%S}",
        "",
        "YÊU CẦU ĐÃ KHÓA:",
        "1. 2.2.2 In phiếu điều tra = mẫu chuẩn nghiệp vụ hiện tại.",
        "2. 2.2.3 Xuất Excel điều tra phải có HÌNH THỨC/MẪU giống phiếu điều tra,",
        "   không dùng Sổ theo dõi PCGDMN làm phiếu đi thực địa.",
        "3. 2.2.4 Nhập Excel cập nhật hộ dân dùng CHÍNH CÙNG MẪU Excel điều tra;",
        "   file xuất đi điều tra là file nhập trở lại, không bắt nhập mẫu khác.",
        "4. Báo cáo Mầm non phải đủ đúng 7 biểu theo file Bieu_mau_PCGDMN_2025.xlsx.",
        "5. Giữ nguyên phân công tổ, giao phiếu, nhập nhanh, PCGD/XMC và dữ liệu đã ổn.",
        "",
        "KHẢO SÁT NÀY CHỈ ĐỌC - KHÔNG SỬA SOURCE / DATABASE.",
    ]

    report.extend([
        "",
        "=" * 120,
        "MẪU PCGDMN CHÍNH THỨC",
        "=" * 120,
        f"Đường dẫn dự kiến: {OFFICIAL_TEMPLATE}",
        f"Tồn tại: {'CÓ' if OFFICIAL_TEMPLATE.exists() else 'KHÔNG'}",
    ])

    sheets = xlsx_sheet_names(OFFICIAL_TEMPLATE)
    report.append(f"Số sheet: {len(sheets)}")
    for i, name in enumerate(sheets, start=1):
        report.append(f" {i}. {name}")

    expected = [
        "MN-01 TE",
        "MN-01 GV",
        "MN-01 CSVC",
        "MN-02",
        "MN - Tài chính",
        "MN- Trẻ KT",
        "Sổ theo dõi PCGDMN",
    ]
    report.append("")
    report.append("ĐỐI CHIẾU 7 BIỂU:")
    for name in expected:
        report.append(f" - {name}: {'CÓ' if name in sheets else 'THIẾU'}")

    find_all_relevant_files(report)

    for path in CANDIDATE_FILES:
        scan_file(report, path)
        find_python_functions(report, path)

    # Quét bổ sung các file vừa phát hiện theo tên route.
    extra_paths = []
    for path in APP.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in {".py", ".html"}:
            continue
        if path in CANDIDATE_FILES:
            continue
        try:
            text = read_text(path)
        except Exception:
            continue
        if any(
            token.casefold() in text.casefold()
            for token in (
                "phieu-in-thuc-dia",
                "/ho-dan/xuat-excel",
                "/ho-dan/nhap-excel",
                "Bieu_mau_PCGDMN_2025.xlsx",
            )
        ):
            extra_paths.append(path)

    for path in sorted(extra_paths):
        scan_file(report, path, max_hits=50)
        find_python_functions(report, path)

    db_check(report)

    report.extend([
        "",
        "=" * 120,
        "ĐẦU RA MONG MUỐN CHO BỘ CÀI SAU KHẢO SÁT",
        "=" * 120,
        "A. EXCEL ĐIỀU TRA:",
        "- Giữ hình thức của Phiếu điều tra PCGD-XMC A4 ngang đang dùng ở 2.2.2.",
        "- Excel có vùng in đúng A4 ngang, tiêu đề hộ, thành viên, các cột PCGD/XMC,",
        "  chữ ký/xác nhận tương ứng mẫu phiếu.",
        "- Cùng một file phục vụ: Xuất đi điều tra -> nhập/cập nhật -> in nếu cần.",
        "- Giữ mã phiếu/mã hộ/định danh kỹ thuật để import đúng, nhưng không làm rối mẫu nhìn thấy.",
        "",
        "B. BÁO CÁO MẦM NON:",
        "- Dùng nguyên mẫu Bieu_mau_PCGDMN_2025.xlsx.",
        "- Đủ 7 sheet, giữ sheet name/merge/font/border/print area/chữ ký/công thức.",
        "- Chỉ điền số liệu từ CSDL vào đúng ô; không thiết kế lại mẫu.",
        "",
        "Sau khi có báo cáo khảo sát này mới tạo bộ cài V2.4.x, tránh đụng nhầm",
        "route Excel/import/report đã hoạt động.",
    ])

    REPORT.write_text("\n".join(report) + "\n", encoding="utf-8-sig")

    print("=" * 120)
    print("KHẢO SÁT V2.4.0 HOÀN THÀNH - KHÔNG THAY ĐỔI DỮ LIỆU")
    print("=" * 120)
    print("Báo cáo:", REPORT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
