# -*- coding: utf-8 -*-
from __future__ import annotations

import re
import sqlite3
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(r"C:\PhoCap")
APP = ROOT / "app"
EXPORTS = ROOT / "exports"
DB = ROOT / "data" / "phocap.db"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
OUT_ZIP = EXPORTS / f"khao_sat_bo_sung_v2_4_0b_chot_excel_va_7_bieu_{STAMP}.zip"
SUMMARY = EXPORTS / f"bao_cao_khao_sat_bo_sung_v2_4_0b_{STAMP}.txt"

FILES = [
    APP / "household_excel_exchange.py",
    APP / "routers" / "survey_print.py",
    APP / "routers" / "surveys.py",
    APP / "routers" / "pcgdmn_template_report.py",
    APP / "routers" / "mn_official_reports.py",
    APP / "routers" / "report_center.py",
    APP / "templates" / "partials" / "dropdown_menu_v1.html",
    APP / "templates" / "reports" / "pcgdmn_template_report.html",
]

TEMPLATE = APP / "report_templates" / "Bieu_mau_PCGDMN_2025.xlsx"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="replace")


def discover_survey_print_templates() -> list[Path]:
    result = []
    path = APP / "routers" / "survey_print.py"
    if not path.exists():
        return result
    text = read_text(path)

    # Tìm mọi chuỗi .html trong router rồi lấy file tương ứng dưới app/templates.
    names = set(re.findall(r'["\']([^"\']+\.html)["\']', text))
    for name in sorted(names):
        candidate = APP / "templates" / name
        if candidate.exists() and candidate.is_file():
            result.append(candidate)
    return result


def discover_exchange_templates() -> list[Path]:
    result = []
    for path in (APP / "household_excel_exchange.py", APP / "routers" / "surveys.py"):
        if not path.exists():
            continue
        text = read_text(path)
        names = set(re.findall(r'["\']([^"\']+\.html)["\']', text))
        for name in sorted(names):
            candidate = APP / "templates" / name
            if candidate.exists() and candidate.is_file():
                result.append(candidate)
    # loại trùng
    unique = []
    seen = set()
    for item in result:
        key = str(item).lower()
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


def db_check() -> tuple[str, int]:
    if not DB.exists():
        return "MISSING", -1
    con = sqlite3.connect(str(DB))
    try:
        integrity = str(con.execute("PRAGMA integrity_check").fetchone()[0])
        fk = len(con.execute("PRAGMA foreign_key_check").fetchall())
        return integrity, fk
    finally:
        con.close()


def main() -> int:
    EXPORTS.mkdir(parents=True, exist_ok=True)

    integrity, fk = db_check()
    if integrity.lower() != "ok" or fk != 0:
        print("DỪNG: database chưa đạt kiểm tra an toàn.")
        print("integrity_check:", integrity)
        print("foreign_key_check:", fk)
        return 2

    collected = []
    for path in FILES + discover_survey_print_templates() + discover_exchange_templates():
        if path.exists() and path.is_file():
            if path not in collected:
                collected.append(path)

    if TEMPLATE.exists():
        collected.append(TEMPLATE)

    lines = [
        "=" * 120,
        "KHẢO SÁT BỔ SUNG V2.4.0B - CHỐT EXCEL ĐIỀU TRA + 7 BIỂU MẦM NON",
        "=" * 120,
        f"Thời gian: {datetime.now():%d/%m/%Y %H:%M:%S}",
        "",
        "MỤC ĐÍCH:",
        "- Lấy NGUYÊN VẸN các file nguồn liên quan, không còn chỉ lấy đoạn trích từ khóa.",
        "- Chốt chính xác mẫu HTML của 2.2.2 Phiếu điều tra thực địa.",
        "- Chốt toàn bộ export/import hiện tại của household_excel_exchange.py.",
        "- Chốt menu 5.2 và các route báo cáo Mầm non.",
        "- Không sửa source, không sửa database.",
        "",
        f"integrity_check: {integrity}",
        f"foreign_key_check: {fk} lỗi",
        "",
        "FILE ĐƯỢC ĐÓNG GÓI:",
    ]
    for path in collected:
        lines.append(" - " + str(path.relative_to(ROOT)))

    with zipfile.ZipFile(OUT_ZIP, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "00_THONG_TIN_KHAO_SAT.txt",
            "\n".join(lines) + "\n",
        )
        for path in collected:
            arcname = str(path.relative_to(ROOT)).replace("\\", "/")
            zf.write(path, arcname)

    SUMMARY.write_text(
        "\n".join(lines)
        + "\n\n"
        + f"ZIP nguồn khảo sát: {OUT_ZIP}\n",
        encoding="utf-8-sig",
    )

    print("=" * 120)
    print("KHẢO SÁT BỔ SUNG V2.4.0B HOÀN THÀNH - CHỈ ĐỌC")
    print("=" * 120)
    print("Không sửa source/database.")
    print("ZIP cần gửi lại:", OUT_ZIP)
    print("Báo cáo:", SUMMARY)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
