"""Build editable Excel templates. Build-only dependency: pymupdf==1.28.2.

Run from project root: python -m tools.convert_appendices_pdf
Each PDF page becomes a worksheet, retaining table cell spans and blank inputs.
No education data or unsupported calculations are inferred.
"""
from pathlib import Path
from copy import copy
import re

import pymupdf
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.page import PageMargins

from app.xmc_appendices import TEMPLATE_DIR, XMC_FORMS, COMPULSORY_FORMS

ROOT = Path(__file__).resolve().parents[1]
SCALE = 1.5


def join_xmc_pages(wb):
    """One logical form per sheet; repeat only table headers on printed pages."""
    for code, _, pages in XMC_FORMS:
        if len(pages) == 1 or f"Trang_{pages[0]:02d}" not in wb:
            continue
        target = wb[f"Trang_{pages[0]:02d}"]
        def header_end(ws):
            return next(row[0].row for row in ws if
                        sum(bool(re.fullmatch(r"\(\d+\)", str(c.value or "").strip())) for c in row) >= 10)
        end = header_end(target)
        for page in pages[1:]:
            name = f"Trang_{page:02d}"
            if name not in wb:
                continue
            source = wb[name]
            first = header_end(source) + 1
            offset = target.max_row + 1 - first
            for row in source.iter_rows(min_row=first):
                for cell in row:
                    dest = target.cell(cell.row + offset, cell.column)
                    dest.value = cell.value
                    dest._style = copy(cell._style)
                    if cell.comment:
                        dest.comment = copy(cell.comment)
                target.row_dimensions[row[0].row + offset].height = source.row_dimensions[row[0].row].height
            for merged in source.merged_cells.ranges:
                if merged.min_row >= first:
                    target.merge_cells(start_row=merged.min_row + offset, end_row=merged.max_row + offset,
                                       start_column=merged.min_col, end_column=merged.max_col)
            wb.remove(source)
        target.print_title_rows = f"14:{end}"
        target.freeze_panes = f"D{end + 1}"
        target.page_setup.fitToWidth = 1
        target.page_setup.fitToHeight = 0
        target.print_area = target.dimensions
        target.oddFooter.center.text = f"Mẫu {code}/XMC — Trang &P / &N"


def clusters(values, tolerance=1.0):
    result = []
    for value in sorted(values):
        if not result or value - result[-1] > tolerance:
            result.append(value)
    return result


def nearest(values, value):
    return min(range(len(values)), key=lambda i: abs(values[i] - value))


def page_sheet(wb, page, page_no):
    ws = wb.create_sheet(f"Trang_{page_no:02d}")
    tables = page.find_tables().tables
    rects = [pymupdf.Rect(t.bbox) for t in tables]
    cells = sorted({tuple(c) for t in tables for c in t.cells if c}, key=lambda c: (c[1], c[0]))
    # Keep text outside tables (headings, dates, signatures) in editable cells.
    lines = []
    all_spans = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            spans = [s for s in line["spans"] if s["text"].strip()]
            all_spans.extend(spans)
            if not spans:
                continue
            box = pymupdf.Rect(line["bbox"])
            center = (box.tl + box.br) / 2
            if any(center in rect for rect in rects):
                continue
            lines.append((box, "".join(s["text"] for s in spans).strip(), spans[0]))
    xs = clusters([v for c in cells for v in (c[0], c[2])])
    if not xs:
        xs = [35, page.rect.width - 35]
    ys = clusters([v for c in cells for v in (c[1], c[3])] +
                  [v for box, _, _ in lines for v in (box.y0, box.y1)])
    for i in range(len(xs) - 1):
        ws.column_dimensions[get_column_letter(i + 1)].width = max(0.3, (xs[i + 1] - xs[i]) * SCALE / 5.25)
    for i in range(len(ys) - 1):
        ws.row_dimensions[i + 1].height = max(1, (ys[i + 1] - ys[i]) * SCALE)
    border = Border(*(Side(style="thin", color="555555") for _ in range(4)))
    words = page.get_text("words")
    for box in cells:
        x0, y0, x1, y1 = box
        c0, c1 = nearest(xs, x0) + 1, nearest(xs, x1)
        r0, r1 = nearest(ys, y0) + 1, nearest(ys, y1)
        if c1 < c0 or r1 < r0:
            continue
        selected = [w for w in words if x0 <= (w[0] + w[2]) / 2 < x1 and y0 <= (w[1] + w[3]) / 2 < y1]
        groups = {}
        for w in selected:
            groups.setdefault((w[5], w[6]), []).append(w)
        content = "\n".join(" ".join(w[4] for w in sorted(group, key=lambda w: w[0]))
                            for group in sorted(groups.values(), key=lambda group: (group[0][1], group[0][0])))
        for row in ws.iter_rows(min_row=r0, max_row=r1, min_col=c0, max_col=c1):
            for cell in row:
                cell.border = border
        if c1 > c0 or r1 > r0:
            ws.merge_cells(start_row=r0, end_row=r1, start_column=c0, end_column=c1)
        cell = ws.cell(r0, c0, content or None)
        cell_spans = [s for s in all_spans
                      if x0 <= (s["bbox"][0] + s["bbox"][2]) / 2 < x1
                      and y0 <= (s["bbox"][1] + s["bbox"][3]) / 2 < y1]
        font_size = min((s["size"] for s in cell_spans), default=10)
        cell.font = Font(name="Times New Roman", size=font_size * SCALE,
                         bold=bool(cell_spans and cell_spans[0]["flags"] & 16),
                         italic=bool(cell_spans and cell_spans[0]["flags"] & 2))
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    occupied = set()
    for box, content, span in lines:
        r0, r1 = nearest(ys, box.y0) + 1, max(nearest(ys, box.y0) + 1, nearest(ys, box.y1))
        c0 = min(len(xs) - 1, nearest(xs, box.x0) + 1)
        c1 = min(len(xs) - 1, max(c0, nearest(xs, box.x1)))
        slots = {(r, c) for r in range(r0, r1 + 1) for c in range(c0, c1 + 1)}
        if slots & occupied:
            raise ValueError(f"Overlapping outside text on page {page_no}: {content}")
        occupied.update(slots)
        if r1 > r0 or c1 > c0:
            ws.merge_cells(start_row=r0, end_row=r1, start_column=c0, end_column=c1)
        cell = ws.cell(r0, c0, content)
        cell.font = Font(name="Times New Roman", size=span["size"] * SCALE,
                         bold=bool(span["flags"] & 16), italic=bool(span["flags"] & 2))
        cell.alignment = Alignment(vertical="center", wrap_text=True)
    ws.sheet_view.showGridLines = False
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_setup.orientation = "landscape"
    ws.page_setup.paperSize = ws.PAPERSIZE_A3
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 1
    ws.page_margins = PageMargins(left=.2, right=.2, top=.2, bottom=.2, header=.1, footer=.1)
    ws.print_options.horizontalCentered = True
    ws.print_area = ws.dimensions
    ws.oddFooter.center.text = f"Nguồn: Các phụ lục.pdf — trang {page_no}"
    return ws


def build():
    TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)
    source = ROOT / "Biểu mẫu Xóa mù" / "Các phụ lục.pdf"
    doc = pymupdf.open(source if source.exists() else ROOT / "Các phụ lục.pdf")
    wb = Workbook()
    info = wb.active
    info.title = "Danh_muc"
    info.append(["CÁC PHỤ LỤC — BIỂU MẪU EXCEL", "Trang PDF", "Nội dung"])
    info.append(["Nguồn", "", "Các phụ lục.pdf do người dùng cung cấp; giữ nguyên nội dung mẫu, kể cả số/ký hiệu còn trống."])
    info.append(["Cách dùng", "", "Mẫu 01/XMC và 07/XMC mỗi mẫu một trang tính liền mạch, tự sang trang khi in. Đây là mẫu trống; dùng chức năng Tổng hợp để xuất số liệu."])
    info.append(["Phụ lục 1", "1–2", "Phiếu điều tra giáo dục bắt buộc, xóa mù chữ"])
    info.append(["Phụ lục 2", "3–13", "Biểu mẫu thống kê giáo dục bắt buộc"])
    info.append(["Phụ lục 3", "14–28", "Biểu mẫu xóa mù chữ"])
    for code, title, pages in XMC_FORMS:
        info.append([f"{code}/XMC", ", ".join(map(str, pages)), title])
    for row in info:
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")
    for col, width in (("A", 32), ("B", 18), ("C", 100)):
        info.column_dimensions[col].width = width
    for row in range(1, info.max_row + 1):
        info.row_dimensions[row].height = 35
    for i, page in enumerate(doc, 1):
        page_sheet(wb, page, i)
    join_xmc_pages(wb)
    wb.save(TEMPLATE_DIR / "Cac_phu_luc_2026.xlsx")
    # Reopen the master for each subset to retain styles/merges/page settings.
    from openpyxl import load_workbook
    subsets = [("Phu_luc_3_Xoa_mu_chu.xlsx", range(14, 29)),
               ("Phu_luc_1_Phieu_dieu_tra.xlsx", (1, 2)),
               ("Phu_luc_2_Giao_duc_bat_buoc.xlsx", range(3, 14))]
    subsets += [(f"Mau_{code}_XMC.xlsx", pages) for code, _, pages in XMC_FORMS]
    subsets += [(f"Mau_{code}.xlsx", pages) for code, _, pages in COMPULSORY_FORMS]
    for filename, pages in subsets:
        subset = load_workbook(TEMPLATE_DIR / "Cac_phu_luc_2026.xlsx")
        names = {f"Trang_{p:02d}" for p in pages}
        for sheet in list(subset):
            if sheet.title not in names:
                subset.remove(sheet)
        subset.active = 0
        subset.save(TEMPLATE_DIR / filename)
    print(f"Created master (28 pages), XMC collection and 9 individual templates in {TEMPLATE_DIR}")


if __name__ == "__main__":
    build()
