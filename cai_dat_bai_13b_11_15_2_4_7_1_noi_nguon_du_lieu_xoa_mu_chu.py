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
DATA = PROJECT / "data"
EXPORTS = PROJECT / "exports"
BUILDERS = APP / "pcgd_xmc_report_builders_v1.py"
SERVICE = APP / "services" / "xmc_report_v247.py"
DB = DATA / "phocap.db"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = EXPORTS / f"backup_bai_13b_11_15_2_4_7_1_{STAMP}"
REPORT = EXPORTS / f"bao_cao_bai_13b_11_15_2_4_7_1_{STAMP}.txt"

START = "# === BAI_13B_11_15_2_4_7_1_XMC_DATA_SOURCE_START ==="
END = "# === BAI_13B_11_15_2_4_7_1_XMC_DATA_SOURCE_END ==="
FORMULA_CALL_MARKER = "# === BAI_13B_11_15_2_4_7_APPLY_XMC_BEFORE_SAVE ==="

HELPERS = '# === BAI_13B_11_15_2_4_7_1_XMC_DATA_SOURCE_START ===\ndef _xmc2471_bool(record: SurveyPersonYearRecord | None, field_name: str) -> bool | None:\n    """Đọc field bool ba trạng thái; None tuyệt đối không bị đổi thành False."""\n    if record is None:\n        return None\n    value = getattr(record, field_name, None)\n    if value is True or value == 1:\n        return True\n    if value is False or value == 0:\n        return False\n    text = str(value or "").strip().upper()\n    if text in {"1", "TRUE", "YES", "Y", "CO", "CÓ"}:\n        return True\n    if text in {"0", "FALSE", "NO", "N", "KHONG", "KHÔNG"}:\n        return False\n    return None\n\n\ndef _xmc2471_metrics(\n    people: list[tuple[SurveyPerson, SurveyPersonYearRecord | None]],\n    year: int,\n) -> dict[int, dict[str, int]]:\n    """\n    Mù chữ mức 1   = completed_grade_3 is False.\n    Biết chữ mức 1 = completed_grade_3 is True.\n    Mù chữ mức 2   = completed_grade_5 is False.\n    Biết chữ mức 2 = completed_grade_5 is True.\n    None = chưa xác định, không tự xếp loại.\n    """\n    keys = (\n        "total", "female", "ethnic", "female_ethnic",\n        "mc1_total", "mc1_female", "mc1_ethnic", "mc1_female_ethnic",\n        "mc2_total", "mc2_female", "mc2_ethnic", "mc2_female_ethnic",\n        "bc1_total", "bc1_female", "bc1_ethnic", "bc1_female_ethnic",\n        "bc2_total", "bc2_female", "bc2_ethnic", "bc2_female_ethnic",\n    )\n    result: dict[int, dict[str, int]] = {}\n    for person, record in people:\n        age = _age(person, year)\n        if age is None:\n            continue\n        item = result.setdefault(age, {key: 0 for key in keys})\n        female = bool(_female(person))\n        ethnic = bool(_ethnic(person))\n        female_ethnic = bool(_female_ethnic(person))\n        item["total"] += 1\n        item["female"] += int(female)\n        item["ethnic"] += int(ethnic)\n        item["female_ethnic"] += int(female_ethnic)\n\n        g3 = _xmc2471_bool(record, "completed_grade_3")\n        g5 = _xmc2471_bool(record, "completed_grade_5")\n\n        if g3 is False:\n            prefix = "mc1"\n        elif g3 is True:\n            prefix = "bc1"\n        else:\n            prefix = None\n        if prefix:\n            item[f"{prefix}_total"] += 1\n            item[f"{prefix}_female"] += int(female)\n            item[f"{prefix}_ethnic"] += int(ethnic)\n            item[f"{prefix}_female_ethnic"] += int(female_ethnic)\n\n        if g5 is False:\n            prefix = "mc2"\n        elif g5 is True:\n            prefix = "bc2"\n        else:\n            prefix = None\n        if prefix:\n            item[f"{prefix}_total"] += 1\n            item[f"{prefix}_female"] += int(female)\n            item[f"{prefix}_ethnic"] += int(ethnic)\n            item[f"{prefix}_female_ethnic"] += int(female_ethnic)\n\n    return result\n\n\ndef _xmc2471_sum(metrics: dict[int, dict[str, int]], ages, key: str) -> int:\n    return sum(int(metrics.get(int(age), {}).get(key, 0) or 0) for age in ages)\n\n\ndef _xmc2471_value(population: int, value: int):\n    """Không có dân số -> trống; có dân số -> cho phép ghi 0 thật."""\n    if int(population or 0) <= 0:\n        return None\n    return int(value or 0)\n# === BAI_13B_11_15_2_4_7_1_XMC_DATA_SOURCE_END ==='
NEW_XMC3 = 'def _build_xmc3(\n    ws: Any,\n    people: list[tuple[SurveyPerson, SurveyPersonYearRecord | None]],\n    year: int,\n) -> None:\n    # C:F dân số; G:J MC1; K:N MC2; O:R biết chữ (mức 2); S tỷ lệ O/C.\n    row_by_age: dict[int, int] = {}\n    for age in range(15, 26):\n        row_by_age[age] = 9 + (age - 15)\n    for age in range(26, 36):\n        row_by_age[age] = 21 + (age - 26)\n    for age in range(36, 61):\n        row_by_age[age] = 32 + (age - 36)\n\n    for row in range(9, 58):\n        for col in range(2, 20):\n            cell = ws.cell(row, col)\n            if cell.__class__.__name__ == "MergedCell":\n                continue\n            if col == 2 and row in {20, 31, 57}:\n                continue\n            if col >= 3:\n                cell.value = None\n\n    metrics = _xmc2471_metrics(people, year)\n    column_keys = (\n        (3, "total"), (4, "female"), (5, "ethnic"), (6, "female_ethnic"),\n        (7, "mc1_total"), (8, "mc1_female"), (9, "mc1_ethnic"), (10, "mc1_female_ethnic"),\n        (11, "mc2_total"), (12, "mc2_female"), (13, "mc2_ethnic"), (14, "mc2_female_ethnic"),\n        (15, "bc2_total"), (16, "bc2_female"), (17, "bc2_ethnic"), (18, "bc2_female_ethnic"),\n    )\n\n    for age, row in row_by_age.items():\n        item = metrics.get(age, {})\n        population = int(item.get("total", 0) or 0)\n        ws.cell(row, 2).value = year - age\n        for col, key in column_keys:\n            ws.cell(row, col).value = _xmc2471_value(\n                population, int(item.get(key, 0) or 0)\n            )\n\n    for row, ages in (\n        (20, range(15, 26)),\n        (31, range(15, 36)),\n        (57, range(15, 61)),\n    ):\n        ages = list(ages)\n        population = _xmc2471_sum(metrics, ages, "total")\n        for col, key in column_keys:\n            ws.cell(row, col).value = _xmc2471_value(\n                population, _xmc2471_sum(metrics, ages, key)\n            )'
NEW_CMC2 = 'def _build_cmc2(\n    ws: Any,\n    people: list[tuple[SurveyPerson, SurveyPersonYearRecord | None]],\n    year: int,\n) -> None:\n    # B:D dân số; F:H MC1; J:L MC2.\n    # Tôn giáo, Tái mù chữ và tỷ lệ riêng của CMC-2 chưa có nguồn/công thức đủ căn cứ.\n    _clear_range(ws, 8, 11, 2, 19)\n    metrics = _xmc2471_metrics(people, year)\n\n    groups = (\n        (8, range(15, 26)),\n        (9, range(26, 36)),\n        (10, range(36, 61)),\n        (11, range(15, 61)),\n    )\n\n    for row, ages in groups:\n        ages = list(ages)\n        population = _xmc2471_sum(metrics, ages, "total")\n        values = {\n            2: _xmc2471_sum(metrics, ages, "total"),\n            3: _xmc2471_sum(metrics, ages, "female"),\n            4: _xmc2471_sum(metrics, ages, "ethnic"),\n            6: _xmc2471_sum(metrics, ages, "mc1_total"),\n            7: _xmc2471_sum(metrics, ages, "mc1_female"),\n            8: _xmc2471_sum(metrics, ages, "mc1_ethnic"),\n            10: _xmc2471_sum(metrics, ages, "mc2_total"),\n            11: _xmc2471_sum(metrics, ages, "mc2_female"),\n            12: _xmc2471_sum(metrics, ages, "mc2_ethnic"),\n        }\n        for col, value in values.items():\n            ws.cell(row, col).value = _xmc2471_value(population, value)\n        for col in (5, 9, 13, 14, 15, 16, 17, 18, 19):\n            ws.cell(row, col).value = None'
NEW_CMC1 = 'def _build_cmc1(\n    ws: Any,\n    people: list[tuple[SurveyPerson, SurveyPersonYearRecord | None]],\n    year: int,\n    meta: dict[str, str],\n) -> None:\n    _clear_range(ws, 8, 8, 3, 66)\n    metrics = _xmc2471_metrics(people, year)\n    all_people = [person for person, _record in people]\n\n    ws["A8"] = 1\n    ws["B8"] = meta["title"]\n    ws["C8"] = len(all_people)\n    ws["D8"] = sum(int(_female(p)) for p in all_people)\n    ws["E8"] = sum(int(_ethnic(p)) for p in all_people)\n    ws["F8"] = sum(int(_female_ethnic(p)) for p in all_people)\n\n    groups = (\n        (7, range(15, 26)),   # G:Z\n        (27, range(15, 36)),  # AA:AT\n        (47, range(15, 61)),  # AU:BN\n    )\n    demographic_keys = ("total", "female", "ethnic", "female_ethnic")\n    mc1_keys = ("mc1_total", "mc1_female", "mc1_ethnic", "mc1_female_ethnic")\n    mc2_keys = ("mc2_total", "mc2_female", "mc2_ethnic", "mc2_female_ethnic")\n\n    for start_col, ages in groups:\n        ages = list(ages)\n        population = _xmc2471_sum(metrics, ages, "total")\n\n        for offset, key in enumerate(demographic_keys):\n            ws.cell(8, start_col + offset).value = _xmc2471_value(\n                population, _xmc2471_sum(metrics, ages, key)\n            )\n\n        # MC1: K/M/O/Q hoặc AE/AG/AI/AK hoặc AY/BA/BC/BE.\n        for index, key in enumerate(mc1_keys):\n            ws.cell(8, start_col + 4 + index * 2).value = _xmc2471_value(\n                population, _xmc2471_sum(metrics, ages, key)\n            )\n\n        # MC2: S/U/W/Y hoặc AM/AO/AQ/AS hoặc BG/BI/BK/BM.\n        for index, key in enumerate(mc2_keys):\n            ws.cell(8, start_col + 12 + index * 2).value = _xmc2471_value(\n                population, _xmc2471_sum(metrics, ages, key)\n            )'
NEW_XMC4 = 'def _build_xmc4(\n    ws: Any,\n    people: list[tuple[SurveyPerson, SurveyPersonYearRecord | None]],\n    year: int,\n    meta: dict[str, str],\n) -> None:\n    # C/H/M tổng; D/I/N biết chữ MĐ1; F/K/P biết chữ MĐ2.\n    # E/G/J/L/O/Q do service 4.7 tính; R Đạt chuẩn để bước công nhận xử lý riêng.\n    _clear_range(ws, 8, 8, 1, 18)\n    metrics = _xmc2471_metrics(people, year)\n    ws["A8"] = 1\n    ws["B8"] = meta["title"]\n\n    for total_col, ages in (\n        (3, range(15, 26)),\n        (8, range(15, 36)),\n        (13, range(15, 61)),\n    ):\n        ages = list(ages)\n        population = _xmc2471_sum(metrics, ages, "total")\n        bc1 = _xmc2471_sum(metrics, ages, "bc1_total")\n        bc2 = _xmc2471_sum(metrics, ages, "bc2_total")\n        ws.cell(8, total_col).value = _xmc2471_value(population, population)\n        ws.cell(8, total_col + 1).value = _xmc2471_value(population, bc1)\n        ws.cell(8, total_col + 3).value = _xmc2471_value(population, bc2)\n\n    ws["R8"] = None'


def read_text(path: Path) -> str:
    if not path.exists():
        raise RuntimeError(f"Không tìm thấy: {path}")
    return path.read_text(encoding="utf-8-sig", errors="strict")


def write_text(path: Path, value: str) -> None:
    path.write_text(value, encoding="utf-8")


def function_node(source: str, name: str):
    tree = ast.parse(source)
    matches = [
        node for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == name
    ]
    if len(matches) != 1:
        raise RuntimeError(f"Cần đúng 1 hàm {name}, tìm thấy {len(matches)}.")
    return matches[0]


def function_span(source: str, name: str) -> tuple[int, int]:
    node = function_node(source, name)
    lines = source.splitlines(keepends=True)
    start = sum(len(line) for line in lines[: int(node.lineno) - 1])
    end = sum(len(line) for line in lines[: int(node.end_lineno)])
    while end < len(source) and source[end:end + 1] in {"\r", "\n"}:
        end += 1
    return start, end


def get_function(source: str, name: str) -> str:
    start, end = function_span(source, name)
    return source[start:end]


def replace_function(source: str, name: str, replacement: str) -> str:
    start, end = function_span(source, name)
    return source[:start] + replacement.rstrip() + "\n\n\n" + source[end:]


def patch_builder(source: str) -> tuple[str, list[str]]:
    notes: list[str] = []
    for name in (
        "_age", "_female", "_ethnic", "_female_ethnic",
        "_build_xmc3", "_build_cmc2", "_build_cmc1", "_build_xmc4",
        "export_additional_report",
    ):
        function_node(source, name)

    export_fn = get_function(source, "export_additional_report")
    if FORMULA_CALL_MARKER not in export_fn or "apply_xmc_formula_contract(" not in export_fn:
        raise RuntimeError("Chưa phát hiện Bài 4.7 hoàn chỉnh trong export.")

    if START in source:
        if END not in source:
            raise RuntimeError("Có marker đầu 4.7.1 nhưng thiếu marker cuối.")
        notes.append("Bài 4.7.1 đã tồn tại; không chèn lặp.")
        return source, notes

    insert_at, _ = function_span(source, "_build_xmc3")
    source = source[:insert_at] + HELPERS + "\n\n\n" + source[insert_at:]
    source = replace_function(source, "_build_xmc3", NEW_XMC3)
    source = replace_function(source, "_build_cmc2", NEW_CMC2)
    source = replace_function(source, "_build_cmc1", NEW_CMC1)
    source = replace_function(source, "_build_xmc4", NEW_XMC4)
    ast.parse(source)

    notes.extend([
        "Đã giữ đúng bool ba trạng thái: None không thành False.",
        "Đã nối CMC-1: mù chữ mức 1/mức 2.",
        "Đã nối CMC-2: mù chữ mức 1/mức 2; không đoán Tôn giáo/Tái mù chữ.",
        "Đã nối XMC-3: mù chữ mức 1/mức 2/biết chữ.",
        "Đã nối XMC-4: biết chữ mức độ 1/mức độ 2.",
        "Đạt chuẩn vẫn để bước công nhận riêng.",
    ])
    return source, notes


def db_snapshot() -> dict:
    if not DB.exists():
        return {"exists": False}
    conn = sqlite3.connect(str(DB))
    try:
        integrity = str(conn.execute("PRAGMA integrity_check").fetchone()[0])
        fk_count = len(conn.execute("PRAGMA foreign_key_check").fetchall())
        columns = [row[1] for row in conn.execute(
            "PRAGMA table_info(survey_person_year_records)"
        ).fetchall()]
        count = int(conn.execute(
            "SELECT COUNT(*) FROM survey_person_year_records"
        ).fetchone()[0])
        stats = {}
        for key, sql in (
            ("target_true", "SELECT COUNT(*) FROM survey_person_year_records WHERE is_literacy_target=1"),
            ("g3_true", "SELECT COUNT(*) FROM survey_person_year_records WHERE completed_grade_3=1"),
            ("g3_false", "SELECT COUNT(*) FROM survey_person_year_records WHERE completed_grade_3=0"),
            ("g5_true", "SELECT COUNT(*) FROM survey_person_year_records WHERE completed_grade_5=1"),
            ("g5_false", "SELECT COUNT(*) FROM survey_person_year_records WHERE completed_grade_5=0"),
        ):
            stats[key] = int(conn.execute(sql).fetchone()[0])
        return {
            "exists": True, "integrity": integrity, "fk_count": fk_count,
            "columns": columns, "count": count, "stats": stats,
        }
    finally:
        conn.close()


def backup_db() -> None:
    if not DB.exists():
        return
    src = sqlite3.connect(str(DB))
    dst = sqlite3.connect(str(BACKUP / DB.name))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()


def restore() -> None:
    source_backup = BACKUP / BUILDERS.name
    if source_backup.exists():
        shutil.copy2(source_backup, BUILDERS)
    db_backup = BACKUP / DB.name
    if DB.exists() and db_backup.exists():
        src = sqlite3.connect(str(db_backup))
        dst = sqlite3.connect(str(DB))
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()


def clear_cache() -> None:
    for cache in APP.rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(cache, ignore_errors=True)


def verify_builder(source: str) -> None:
    ast.parse(source)
    for token in (
        START, END, "def _xmc2471_bool(", "def _xmc2471_metrics(",
        '"completed_grade_3"', '"completed_grade_5"',
        '"mc1_total"', '"mc2_total"', '"bc1_total"', '"bc2_total"',
    ):
        if token not in source:
            raise RuntimeError("Verifier thiếu: " + token)

    xmc3 = get_function(source, "_build_xmc3")
    for token in ('"mc1_total"', '"mc2_total"', '"bc2_total"'):
        if token not in xmc3:
            raise RuntimeError("XMC-3 chưa nối đủ: " + token)

    cmc1 = get_function(source, "_build_cmc1")
    for token in ("mc1_keys", "mc2_keys", "index * 2"):
        if token not in cmc1:
            raise RuntimeError("CMC-1 chưa nối đủ: " + token)

    cmc2 = get_function(source, "_build_cmc2")
    for token in ('"mc1_total"', '"mc2_total"', "Tái mù chữ"):
        if token not in cmc2:
            raise RuntimeError("CMC-2 chưa nối đủ: " + token)

    xmc4 = get_function(source, "_build_xmc4")
    for token in ('"bc1_total"', '"bc2_total"', 'ws["R8"] = None'):
        if token not in xmc4:
            raise RuntimeError("XMC-4 chưa nối đủ: " + token)

    export_fn = get_function(source, "export_additional_report")
    call_pos = export_fn.find("apply_xmc_formula_contract(")
    save_pos = export_fn.find("workbook.save(output)")
    if call_pos < 0 or save_pos < 0 or call_pos >= save_pos:
        raise RuntimeError("Bộ tính 4.7 không còn nằm trước workbook.save(output).")


def verify_service() -> None:
    text = read_text(SERVICE)
    ast.parse(text)
    for token in (
        "CMC1_PERCENT_FORMULAS", "XMC3_PERCENT_FORMULAS",
        "XMC4_PERCENT_FORMULAS", "def apply_xmc_formula_contract(",
    ):
        if token not in text:
            raise RuntimeError("Service Bài 4.7 thiếu: " + token)


def main() -> None:
    print("=" * 138)
    print("BÀI 13B-11.15.2.4.7.1 - NỐI NGUỒN DỮ LIỆU XÓA MÙ CHỮ")
    print("=" * 138)
    print()
    print("SẼ LÀM:")
    print(" - CMC-1: nối mù chữ mức 1/mức 2.")
    print(" - CMC-2: nối mù chữ mức 1/mức 2.")
    print(" - XMC-3: nối mù chữ mức 1/mức 2/biết chữ.")
    print(" - XMC-4: nối biết chữ mức độ 1/mức độ 2.")
    print(" - Giữ Bài 4.7 tính tỷ lệ trước khi lưu Excel.")
    print()
    print("KHÔNG LÀM:")
    print(" - Không UPDATE/ALTER database.")
    print(" - Không sửa menu/route/template.")
    print(" - Không biến None thành Không.")
    print(" - Không suy diễn Tôn giáo/Tái mù chữ.")
    print(" - Không tự kết luận Đạt chuẩn.")
    print()

    old_source = read_text(BUILDERS)
    ast.parse(old_source)
    verify_service()

    before = db_snapshot()
    if before.get("exists"):
        if before.get("integrity") != "ok" or before.get("fk_count") != 0:
            raise RuntimeError("Database không đạt kiểm tra an toàn trước cài.")
        required = {
            "is_literacy_target", "literacy_status",
            "completed_grade_3", "completed_grade_5",
        }
        missing = required - set(before.get("columns", []))
        if missing:
            raise RuntimeError("Thiếu field XMC: " + ", ".join(sorted(missing)))

    new_source, notes = patch_builder(old_source)
    verify_builder(new_source)

    EXPORTS.mkdir(parents=True, exist_ok=True)
    BACKUP.mkdir(parents=True, exist_ok=False)
    shutil.copy2(BUILDERS, BACKUP / BUILDERS.name)
    shutil.copy2(SERVICE, BACKUP / SERVICE.name)
    backup_db()

    try:
        if new_source != old_source:
            write_text(BUILDERS, new_source)

        py_compile.compile(str(BUILDERS), doraise=True)
        py_compile.compile(str(SERVICE), doraise=True)
        verify_builder(read_text(BUILDERS))
        verify_service()

        after = db_snapshot()
        if before != after:
            raise RuntimeError("Database bị thay đổi ngoài dự kiến.")
        if after.get("exists") and (
            after.get("integrity") != "ok" or after.get("fk_count") != 0
        ):
            raise RuntimeError("Database không đạt kiểm tra sau cài.")

        REPORT.write_text(
            "\n".join([
                "=" * 120,
                "BÀI 13B-11.15.2.4.7.1 - NỐI NGUỒN XMC",
                "=" * 120,
                "",
                "QUY TẮC:",
                " - MC mức 1 = completed_grade_3=False.",
                " - Biết chữ mức 1 = completed_grade_3=True.",
                " - MC mức 2 = completed_grade_5=False.",
                " - Biết chữ mức 2 = completed_grade_5=True.",
                " - None giữ là chưa xác định.",
                " - literacy_status không thay thế completed_grade_3/5.",
                "",
                *[" - " + note for note in notes],
                "",
                "DB trước: " + repr(before),
                "DB sau  : " + repr(after),
                "",
                "Database: KHÔNG THAY ĐỔI.",
                "Menu/route/template: KHÔNG THAY ĐỔI.",
            ]),
            encoding="utf-8",
        )
        clear_cache()

    except Exception:
        print()
        print("CÓ LỖI - ĐANG KHÔI PHỤC SOURCE/DB...")
        restore()
        clear_cache()
        raise

    print("CÀI ĐẶT THÀNH CÔNG.")
    print("Backup:", BACKUP)
    print("Báo cáo:", REPORT)
    print("Database: KHÔNG THAY ĐỔI.")
    print()
    print("=" * 138)
    print("BÀI 13B-11.15.2.4.7.1 THÀNH CÔNG")
    print("=" * 138)


if __name__ == "__main__":
    main()
