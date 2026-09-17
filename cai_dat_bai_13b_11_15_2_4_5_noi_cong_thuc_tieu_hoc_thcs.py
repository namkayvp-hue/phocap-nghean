from __future__ import annotations

import ast
import os
import py_compile
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

PROJECT = Path(os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")).resolve()
APP = PROJECT / "app"
EXPORTS = PROJECT / "exports"
DB = PROJECT / "data" / "phocap.db"
REPORT_CENTER = APP / "routers" / "report_center.py"
XMC_BUILDERS = APP / "pcgd_xmc_report_builders_v1.py"
RULES_FILE = APP / "services" / "pcgd_business_rules.py"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP_DIR = EXPORTS / f"backup_bai_13b_11_15_2_4_5_{STAMP}"
REPORT_FILE = EXPORTS / f"bao_cao_bai_13b_11_15_2_4_5_{STAMP}.txt"

MARKER_RC = "# === BAI_13B_11_15_2_4_5_PRIMARY_OFFICIAL_PERCENTAGES ==="
MARKER_XMC = "# === BAI_13B_11_15_2_4_5_TH_THCS_OFFICIAL_CALCULATIONS ==="

PRIMARY_HELPER = r'''# === BAI_13B_11_15_2_4_5_PRIMARY_OFFICIAL_PERCENTAGES ===
def _b15245_cell_number(ws: Any, ref: str) -> float | None:
    value = ws[ref].value
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _b15245_sum_cells(ws: Any, refs: tuple[str, ...]) -> float | None:
    values = [_b15245_cell_number(ws, ref) for ref in refs]
    if all(value is None for value in values):
        return None
    return sum(value or 0.0 for value in values)


def _b15245_apply_primary_th_m1_percentages(ws: Any) -> None:
    # Tính đúng công thức mẫu; thiếu nguồn thì để trống.
    from app.services.pcgd_business_rules import safe_percent

    mappings = (
        ("G40", "F40", ("F12",)),
        ("G41", "F41", ("L12",)),
        ("G42", "F42", ("L12",)),
        ("G43", "F43", ("P12",)),
        ("G44", "F44", ("K10", "P10")),
    )
    for result_ref, numerator_ref, denominator_refs in mappings:
        numerator = _b15245_cell_number(ws, numerator_ref)
        denominator = _b15245_sum_cells(ws, denominator_refs)
        ws[result_ref] = safe_percent(numerator, denominator)
# === END BAI_13B_11_15_2_4_5_PRIMARY_OFFICIAL_PERCENTAGES ===


'''

TH_THCS_HELPER = r'''# === BAI_13B_11_15_2_4_5_TH_THCS_OFFICIAL_CALCULATIONS ===
def _b15245_ws_number(ws: Any, ref: str) -> float | None:
    value = ws[ref].value
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _b15245_ws_sum(ws: Any, refs: tuple[str, ...]) -> float | None:
    values = [_b15245_ws_number(ws, ref) for ref in refs]
    if all(value is None for value in values):
        return None
    return sum(value or 0.0 for value in values)


def _b15245_percent_from_cells(ws: Any, numerator_refs: tuple[str, ...], denominator_refs: tuple[str, ...]) -> float | None:
    from app.services.pcgd_business_rules import safe_percent
    return safe_percent(_b15245_ws_sum(ws, numerator_refs), _b15245_ws_sum(ws, denominator_refs))


def _b15245_ratio_from_cells(ws: Any, numerator_refs: tuple[str, ...], denominator_refs: tuple[str, ...]) -> float | None:
    from app.services.pcgd_business_rules import safe_ratio
    return safe_ratio(_b15245_ws_sum(ws, numerator_refs), _b15245_ws_sum(ws, denominator_refs))


def _b15245_apply_official_th_thcs_calculations(ws: Any, report_type: str) -> None:
    # TIỂU HỌC TH-02: Q8 = P8/O8%
    if report_type == "PCGD_TH_02_2025":
        ws["Q8"] = _b15245_percent_from_cells(ws, ("P8",), ("O8",))
        return

    # TIỂU HỌC CSVC: J = SUM(F:I)/D
    if report_type == "PCGD_TH_01_CSVC_2025":
        for row in range(8, 19):
            refs = tuple(f"{col}{row}" for col in ("F", "G", "H", "I"))
            ws[f"J{row}"] = _b15245_ratio_from_cells(ws, refs, (f"D{row}",))
        return

    # THCS M2: E=D/C%; J=I/F%; M=L/K%; Q=(P+O)/N%; V=U/R%
    if report_type == "PCGD_THCS_M2_2025":
        for row in (14, 15):
            ws[f"E{row}"] = _b15245_percent_from_cells(ws, (f"D{row}",), (f"C{row}",))
            ws[f"J{row}"] = _b15245_percent_from_cells(ws, (f"I{row}",), (f"F{row}",))
            ws[f"M{row}"] = _b15245_percent_from_cells(ws, (f"L{row}",), (f"K{row}",))
            ws[f"Q{row}"] = _b15245_percent_from_cells(ws, (f"P{row}", f"O{row}"), (f"N{row}",))
            ws[f"V{row}"] = _b15245_percent_from_cells(ws, (f"U{row}",), (f"R{row}",))
        return

    # THCS TK: O8 = N8/M8%
    if report_type == "PCGD_THCS_TK_2025":
        ws["O8"] = _b15245_percent_from_cells(ws, ("N8",), ("M8",))
        return

    # THCS M5: L21:L23 = K/H19%
    if report_type == "PCGD_THCS_M5_2025":
        for row in (21, 22, 23):
            ws[f"L{row}"] = _b15245_percent_from_cells(ws, (f"K{row}",), ("H19",))
        return

    # THCS CSVC: H = SUM(E:G)/D
    if report_type == "PCGD_THCS_CSVC_2025":
        for row in range(8, 19):
            refs = tuple(f"{col}{row}" for col in ("E", "F", "G"))
            ws[f"H{row}"] = _b15245_ratio_from_cells(ws, refs, (f"D{row}",))
        return
# === END BAI_13B_11_15_2_4_5_TH_THCS_OFFICIAL_CALCULATIONS ===


'''


def db_state() -> dict:
    if not DB.exists():
        return {"exists": False}
    conn = sqlite3.connect(str(DB))
    try:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        fk = conn.execute("PRAGMA foreign_key_check").fetchall()
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        schema = {}
        for (table,) in tables:
            schema[table] = [row[1] for row in conn.execute(f'PRAGMA table_info("{table}")').fetchall()]
        return {"exists": True, "integrity": integrity, "fk_count": len(fk), "schema": schema}
    finally:
        conn.close()


def backup_db() -> None:
    if not DB.exists():
        return
    src = sqlite3.connect(str(DB))
    dst = sqlite3.connect(str(BACKUP_DIR / "phocap.db"))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()


def replace_once(text: str, old: str, new: str, description: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{description}: cần đúng 1 anchor, tìm thấy {count}.")
    return text.replace(old, new, 1)


def patch_report_center(text: str) -> tuple[str, list[str]]:
    notes = []
    if MARKER_RC not in text:
        anchor = "def _build_primary_th_m1_workbook("
        if anchor not in text:
            raise RuntimeError("Không tìm thấy def _build_primary_th_m1_workbook(")
        text = text.replace(anchor, PRIMARY_HELPER + anchor, 1)
        notes.append("Đã thêm helper tính công thức TH_M1.")
    else:
        notes.append("Helper TH_M1 đã tồn tại.")

    call = "    _b15245_apply_primary_th_m1_percentages(ws)\n"
    if call not in text:
        old = '    ws["F44"] = None\n    ws["G44"] = None\n'
        text = replace_once(text, old, old + "\n" + call, "Chèn lời gọi công thức TH_M1")
        notes.append("Đã nối công thức chính thức TH_M1.")
    else:
        notes.append("Lời gọi TH_M1 đã tồn tại.")
    return text, notes


def patch_xmc_builders(text: str) -> tuple[str, list[str]]:
    notes = []
    if MARKER_XMC not in text:
        anchor = "def export_additional_report("
        if anchor not in text:
            raise RuntimeError("Không tìm thấy def export_additional_report(")
        text = text.replace(anchor, TH_THCS_HELPER + anchor, 1)
        notes.append("Đã thêm helper công thức TH/THCS.")
    else:
        notes.append("Helper TH/THCS đã tồn tại.")

    call = "    _b15245_apply_official_th_thcs_calculations(ws, report_type)\n"
    if call not in text:
        old = (
            '    elif report_type=="PCGD_XMC_4_2025": _build_xmc4(ws,people,year,meta)\n'
            '    if meta["kind"]=="province":\n'
        )
        new = (
            '    elif report_type=="PCGD_XMC_4_2025": _build_xmc4(ws,people,year,meta)\n'
            + call
            + '    if meta["kind"]=="province":\n'
        )
        text = replace_once(text, old, new, "Chèn lời gọi công thức TH/THCS")
        notes.append("Đã nối post-processing TH/THCS sau builder.")
    else:
        notes.append("Lời gọi TH/THCS đã tồn tại.")
    return text, notes


def main() -> None:
    print("=" * 136)
    print("BÀI 13B-11.15.2.4.5 - NỐI CÔNG THỨC CHÍNH THỨC TIỂU HỌC + THCS")
    print("=" * 136)
    print("Không sửa database / menu / route / template.")
    print("Thiếu tử số hoặc mẫu số -> để trống, không tự đoán.")
    print()

    for required in (REPORT_CENTER, XMC_BUILDERS, RULES_FILE):
        if not required.exists():
            raise SystemExit(f"Không tìm thấy: {required}")

    rules_text = RULES_FILE.read_text(encoding="utf-8")
    for helper in ("def safe_percent(", "def safe_ratio("):
        if helper not in rules_text:
            raise SystemExit(f"Thiếu {helper} trong {RULES_FILE}")

    rc_old = REPORT_CENTER.read_text(encoding="utf-8-sig")
    xb_old = XMC_BUILDERS.read_text(encoding="utf-8-sig")
    ast.parse(rc_old)
    ast.parse(xb_old)

    before = db_state()
    if before.get("exists") and before.get("integrity") != "ok":
        raise SystemExit("Database integrity_check không phải ok.")
    if before.get("exists") and before.get("fk_count") != 0:
        raise SystemExit("Database có lỗi foreign key.")

    rc_new, rc_notes = patch_report_center(rc_old)
    xb_new, xb_notes = patch_xmc_builders(xb_old)
    ast.parse(rc_new)
    ast.parse(xb_new)

    for token in (
        MARKER_RC,
        "_b15245_apply_primary_th_m1_percentages(ws)",
        '("G44", "F44", ("K10", "P10"))',
    ):
        if token not in rc_new:
            raise RuntimeError(f"Verifier report_center thiếu: {token}")

    for token in (
        MARKER_XMC,
        "_b15245_apply_official_th_thcs_calculations(",
        'report_type == "PCGD_TH_02_2025"',
        'report_type == "PCGD_TH_01_CSVC_2025"',
        'report_type == "PCGD_THCS_M2_2025"',
        'report_type == "PCGD_THCS_TK_2025"',
        'report_type == "PCGD_THCS_M5_2025"',
        'report_type == "PCGD_THCS_CSVC_2025"',
    ):
        if token not in xb_new:
            raise RuntimeError(f"Verifier builder thiếu: {token}")

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(REPORT_CENTER, BACKUP_DIR / "report_center.py")
    shutil.copy2(XMC_BUILDERS, BACKUP_DIR / "pcgd_xmc_report_builders_v1.py")
    shutil.copy2(RULES_FILE, BACKUP_DIR / "pcgd_business_rules.py")
    backup_db()

    try:
        if rc_new != rc_old:
            REPORT_CENTER.write_text(rc_new, encoding="utf-8")
        if xb_new != xb_old:
            XMC_BUILDERS.write_text(xb_new, encoding="utf-8")

        py_compile.compile(str(REPORT_CENTER), doraise=True)
        py_compile.compile(str(XMC_BUILDERS), doraise=True)
        py_compile.compile(str(RULES_FILE), doraise=True)
        ast.parse(REPORT_CENTER.read_text(encoding="utf-8-sig"))
        ast.parse(XMC_BUILDERS.read_text(encoding="utf-8-sig"))

        after = db_state()
        if before != after:
            raise RuntimeError("Database/schema thay đổi ngoài dự kiến.")
    except Exception:
        shutil.copy2(BACKUP_DIR / "report_center.py", REPORT_CENTER)
        shutil.copy2(BACKUP_DIR / "pcgd_xmc_report_builders_v1.py", XMC_BUILDERS)
        raise

    lines = [
        "=" * 136 + "\n",
        "BÀI 13B-11.15.2.4.5 - BÁO CÁO CÀI ĐẶT\n",
        "=" * 136 + "\n\n",
        "REPORT_CENTER:\n",
        *[f" - {note}\n" for note in rc_notes],
        "\nTH/THCS BUILDERS:\n",
        *[f" - {note}\n" for note in xb_notes],
        "\nCÔNG THỨC ĐÃ NỐI:\n",
        " - TH_M1: G40=F40/F12%; G41=F41/L12%; G42=F42/L12%; G43=F43/P12%; G44=F44/(K10+P10)%.\n",
        " - TH_02: Q8=P8/O8%.\n",
        " - TH_01_CSVC: J8:J18=SUM(F:I)/D.\n",
        " - THCS_M2: E=D/C%; J=I/F%; M=L/K%; Q=(P+O)/N%; V=U/R% cho dòng 14-15.\n",
        " - THCS_TK: O8=N8/M8%.\n",
        " - THCS_M5: L21:L23=K/H19%.\n",
        " - THCS_CSVC: H8:H18=SUM(E:G)/D.\n",
        "\nAN TOÀN:\n",
        " - Database không thay đổi.\n",
        " - Không sửa route/menu/template.\n",
        " - Thiếu nguồn -> tỷ lệ để trống.\n",
        " - G44 TH_M1 vẫn trống nếu F44 chưa có nguồn.\n",
        " - TH_02 Q8 vẫn trống nếu O8 chưa có nguồn chính thức.\n",
        f" - Backup: {BACKUP_DIR}\n",
    ]
    REPORT_FILE.write_text("".join(lines), encoding="utf-8")

    print("CÀI ĐẶT THÀNH CÔNG.")
    print(f"Backup: {BACKUP_DIR}")
    print(f"Báo cáo: {REPORT_FILE}")
    print("Database: KHÔNG THAY ĐỔI.")
    print("=" * 136)
    print("BÀI 13B-11.15.2.4.5 THÀNH CÔNG")
    print("=" * 136)


if __name__ == "__main__":
    main()
