from __future__ import annotations

import ast
import os
import py_compile
import re
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path


PROJECT = Path(os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")).resolve()
APP = PROJECT / "app"
ROUTERS = APP / "routers"
TEMPLATE = APP / "templates" / "surveys" / "year_records.html"
BUILDERS = APP / "pcgd_xmc_report_builders_v1.py"
SERVICE = APP / "services" / "xmc_report_v247.py"
DB = PROJECT / "data" / "phocap.db"
EXPORTS = PROJECT / "exports"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = EXPORTS / f"backup_bai_13b_11_15_2_4_7_1_v2_{STAMP}"
REPORT = EXPORTS / f"bao_cao_bai_13b_11_15_2_4_7_1_v2_{STAMP}.txt"

ROUTER_MARKER = "# === BAI_13B_11_15_2_4_7_1_V2_FORCE_XMC_AGE_15_PLUS ==="
TEMPLATE_MARKER = "<!-- === BAI_13B_11_15_2_4_7_1_V2_AUTO_XMC_AGE_15_PLUS === -->"

PY_START = "# === BAI_13B_11_13_2_SAVE_FIELDS_START ==="
PY_END = "# === BAI_13B_11_13_2_SAVE_FIELDS_END ==="

BASE_INSTALLER_CONTENT = 'from __future__ import annotations\n\nimport ast\nimport os\nimport py_compile\nimport shutil\nimport sqlite3\nfrom datetime import datetime\nfrom pathlib import Path\n\n\nPROJECT = Path(os.environ.get("PHOCAP_PROJECT", r"C:\\PhoCap")).resolve()\nAPP = PROJECT / "app"\nDATA = PROJECT / "data"\nEXPORTS = PROJECT / "exports"\nBUILDERS = APP / "pcgd_xmc_report_builders_v1.py"\nSERVICE = APP / "services" / "xmc_report_v247.py"\nDB = DATA / "phocap.db"\n\nSTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")\nBACKUP = EXPORTS / f"backup_bai_13b_11_15_2_4_7_1_{STAMP}"\nREPORT = EXPORTS / f"bao_cao_bai_13b_11_15_2_4_7_1_{STAMP}.txt"\n\nSTART = "# === BAI_13B_11_15_2_4_7_1_XMC_DATA_SOURCE_START ==="\nEND = "# === BAI_13B_11_15_2_4_7_1_XMC_DATA_SOURCE_END ==="\nFORMULA_CALL_MARKER = "# === BAI_13B_11_15_2_4_7_APPLY_XMC_BEFORE_SAVE ==="\n\nHELPERS = \'# === BAI_13B_11_15_2_4_7_1_XMC_DATA_SOURCE_START ===\\ndef _xmc2471_bool(record: SurveyPersonYearRecord | None, field_name: str) -> bool | None:\\n    """Đọc field bool ba trạng thái; None tuyệt đối không bị đổi thành False."""\\n    if record is None:\\n        return None\\n    value = getattr(record, field_name, None)\\n    if value is True or value == 1:\\n        return True\\n    if value is False or value == 0:\\n        return False\\n    text = str(value or "").strip().upper()\\n    if text in {"1", "TRUE", "YES", "Y", "CO", "CÓ"}:\\n        return True\\n    if text in {"0", "FALSE", "NO", "N", "KHONG", "KHÔNG"}:\\n        return False\\n    return None\\n\\n\\ndef _xmc2471_metrics(\\n    people: list[tuple[SurveyPerson, SurveyPersonYearRecord | None]],\\n    year: int,\\n) -> dict[int, dict[str, int]]:\\n    """\\n    Mù chữ mức 1   = completed_grade_3 is False.\\n    Biết chữ mức 1 = completed_grade_3 is True.\\n    Mù chữ mức 2   = completed_grade_5 is False.\\n    Biết chữ mức 2 = completed_grade_5 is True.\\n    None = chưa xác định, không tự xếp loại.\\n    """\\n    keys = (\\n        "total", "female", "ethnic", "female_ethnic",\\n        "mc1_total", "mc1_female", "mc1_ethnic", "mc1_female_ethnic",\\n        "mc2_total", "mc2_female", "mc2_ethnic", "mc2_female_ethnic",\\n        "bc1_total", "bc1_female", "bc1_ethnic", "bc1_female_ethnic",\\n        "bc2_total", "bc2_female", "bc2_ethnic", "bc2_female_ethnic",\\n    )\\n    result: dict[int, dict[str, int]] = {}\\n    for person, record in people:\\n        age = _age(person, year)\\n        if age is None:\\n            continue\\n        item = result.setdefault(age, {key: 0 for key in keys})\\n        female = bool(_female(person))\\n        ethnic = bool(_ethnic(person))\\n        female_ethnic = bool(_female_ethnic(person))\\n        item["total"] += 1\\n        item["female"] += int(female)\\n        item["ethnic"] += int(ethnic)\\n        item["female_ethnic"] += int(female_ethnic)\\n\\n        g3 = _xmc2471_bool(record, "completed_grade_3")\\n        g5 = _xmc2471_bool(record, "completed_grade_5")\\n\\n        if g3 is False:\\n            prefix = "mc1"\\n        elif g3 is True:\\n            prefix = "bc1"\\n        else:\\n            prefix = None\\n        if prefix:\\n            item[f"{prefix}_total"] += 1\\n            item[f"{prefix}_female"] += int(female)\\n            item[f"{prefix}_ethnic"] += int(ethnic)\\n            item[f"{prefix}_female_ethnic"] += int(female_ethnic)\\n\\n        if g5 is False:\\n            prefix = "mc2"\\n        elif g5 is True:\\n            prefix = "bc2"\\n        else:\\n            prefix = None\\n        if prefix:\\n            item[f"{prefix}_total"] += 1\\n            item[f"{prefix}_female"] += int(female)\\n            item[f"{prefix}_ethnic"] += int(ethnic)\\n            item[f"{prefix}_female_ethnic"] += int(female_ethnic)\\n\\n    return result\\n\\n\\ndef _xmc2471_sum(metrics: dict[int, dict[str, int]], ages, key: str) -> int:\\n    return sum(int(metrics.get(int(age), {}).get(key, 0) or 0) for age in ages)\\n\\n\\ndef _xmc2471_value(population: int, value: int):\\n    """Không có dân số -> trống; có dân số -> cho phép ghi 0 thật."""\\n    if int(population or 0) <= 0:\\n        return None\\n    return int(value or 0)\\n# === BAI_13B_11_15_2_4_7_1_XMC_DATA_SOURCE_END ===\'\nNEW_XMC3 = \'def _build_xmc3(\\n    ws: Any,\\n    people: list[tuple[SurveyPerson, SurveyPersonYearRecord | None]],\\n    year: int,\\n) -> None:\\n    # C:F dân số; G:J MC1; K:N MC2; O:R biết chữ (mức 2); S tỷ lệ O/C.\\n    row_by_age: dict[int, int] = {}\\n    for age in range(15, 26):\\n        row_by_age[age] = 9 + (age - 15)\\n    for age in range(26, 36):\\n        row_by_age[age] = 21 + (age - 26)\\n    for age in range(36, 61):\\n        row_by_age[age] = 32 + (age - 36)\\n\\n    for row in range(9, 58):\\n        for col in range(2, 20):\\n            cell = ws.cell(row, col)\\n            if cell.__class__.__name__ == "MergedCell":\\n                continue\\n            if col == 2 and row in {20, 31, 57}:\\n                continue\\n            if col >= 3:\\n                cell.value = None\\n\\n    metrics = _xmc2471_metrics(people, year)\\n    column_keys = (\\n        (3, "total"), (4, "female"), (5, "ethnic"), (6, "female_ethnic"),\\n        (7, "mc1_total"), (8, "mc1_female"), (9, "mc1_ethnic"), (10, "mc1_female_ethnic"),\\n        (11, "mc2_total"), (12, "mc2_female"), (13, "mc2_ethnic"), (14, "mc2_female_ethnic"),\\n        (15, "bc2_total"), (16, "bc2_female"), (17, "bc2_ethnic"), (18, "bc2_female_ethnic"),\\n    )\\n\\n    for age, row in row_by_age.items():\\n        item = metrics.get(age, {})\\n        population = int(item.get("total", 0) or 0)\\n        ws.cell(row, 2).value = year - age\\n        for col, key in column_keys:\\n            ws.cell(row, col).value = _xmc2471_value(\\n                population, int(item.get(key, 0) or 0)\\n            )\\n\\n    for row, ages in (\\n        (20, range(15, 26)),\\n        (31, range(15, 36)),\\n        (57, range(15, 61)),\\n    ):\\n        ages = list(ages)\\n        population = _xmc2471_sum(metrics, ages, "total")\\n        for col, key in column_keys:\\n            ws.cell(row, col).value = _xmc2471_value(\\n                population, _xmc2471_sum(metrics, ages, key)\\n            )\'\nNEW_CMC2 = \'def _build_cmc2(\\n    ws: Any,\\n    people: list[tuple[SurveyPerson, SurveyPersonYearRecord | None]],\\n    year: int,\\n) -> None:\\n    # B:D dân số; F:H MC1; J:L MC2.\\n    # Tôn giáo, Tái mù chữ và tỷ lệ riêng của CMC-2 chưa có nguồn/công thức đủ căn cứ.\\n    _clear_range(ws, 8, 11, 2, 19)\\n    metrics = _xmc2471_metrics(people, year)\\n\\n    groups = (\\n        (8, range(15, 26)),\\n        (9, range(26, 36)),\\n        (10, range(36, 61)),\\n        (11, range(15, 61)),\\n    )\\n\\n    for row, ages in groups:\\n        ages = list(ages)\\n        population = _xmc2471_sum(metrics, ages, "total")\\n        values = {\\n            2: _xmc2471_sum(metrics, ages, "total"),\\n            3: _xmc2471_sum(metrics, ages, "female"),\\n            4: _xmc2471_sum(metrics, ages, "ethnic"),\\n            6: _xmc2471_sum(metrics, ages, "mc1_total"),\\n            7: _xmc2471_sum(metrics, ages, "mc1_female"),\\n            8: _xmc2471_sum(metrics, ages, "mc1_ethnic"),\\n            10: _xmc2471_sum(metrics, ages, "mc2_total"),\\n            11: _xmc2471_sum(metrics, ages, "mc2_female"),\\n            12: _xmc2471_sum(metrics, ages, "mc2_ethnic"),\\n        }\\n        for col, value in values.items():\\n            ws.cell(row, col).value = _xmc2471_value(population, value)\\n        for col in (5, 9, 13, 14, 15, 16, 17, 18, 19):\\n            ws.cell(row, col).value = None\'\nNEW_CMC1 = \'def _build_cmc1(\\n    ws: Any,\\n    people: list[tuple[SurveyPerson, SurveyPersonYearRecord | None]],\\n    year: int,\\n    meta: dict[str, str],\\n) -> None:\\n    _clear_range(ws, 8, 8, 3, 66)\\n    metrics = _xmc2471_metrics(people, year)\\n    all_people = [person for person, _record in people]\\n\\n    ws["A8"] = 1\\n    ws["B8"] = meta["title"]\\n    ws["C8"] = len(all_people)\\n    ws["D8"] = sum(int(_female(p)) for p in all_people)\\n    ws["E8"] = sum(int(_ethnic(p)) for p in all_people)\\n    ws["F8"] = sum(int(_female_ethnic(p)) for p in all_people)\\n\\n    groups = (\\n        (7, range(15, 26)),   # G:Z\\n        (27, range(15, 36)),  # AA:AT\\n        (47, range(15, 61)),  # AU:BN\\n    )\\n    demographic_keys = ("total", "female", "ethnic", "female_ethnic")\\n    mc1_keys = ("mc1_total", "mc1_female", "mc1_ethnic", "mc1_female_ethnic")\\n    mc2_keys = ("mc2_total", "mc2_female", "mc2_ethnic", "mc2_female_ethnic")\\n\\n    for start_col, ages in groups:\\n        ages = list(ages)\\n        population = _xmc2471_sum(metrics, ages, "total")\\n\\n        for offset, key in enumerate(demographic_keys):\\n            ws.cell(8, start_col + offset).value = _xmc2471_value(\\n                population, _xmc2471_sum(metrics, ages, key)\\n            )\\n\\n        # MC1: K/M/O/Q hoặc AE/AG/AI/AK hoặc AY/BA/BC/BE.\\n        for index, key in enumerate(mc1_keys):\\n            ws.cell(8, start_col + 4 + index * 2).value = _xmc2471_value(\\n                population, _xmc2471_sum(metrics, ages, key)\\n            )\\n\\n        # MC2: S/U/W/Y hoặc AM/AO/AQ/AS hoặc BG/BI/BK/BM.\\n        for index, key in enumerate(mc2_keys):\\n            ws.cell(8, start_col + 12 + index * 2).value = _xmc2471_value(\\n                population, _xmc2471_sum(metrics, ages, key)\\n            )\'\nNEW_XMC4 = \'def _build_xmc4(\\n    ws: Any,\\n    people: list[tuple[SurveyPerson, SurveyPersonYearRecord | None]],\\n    year: int,\\n    meta: dict[str, str],\\n) -> None:\\n    # C/H/M tổng; D/I/N biết chữ MĐ1; F/K/P biết chữ MĐ2.\\n    # E/G/J/L/O/Q do service 4.7 tính; R Đạt chuẩn để bước công nhận xử lý riêng.\\n    _clear_range(ws, 8, 8, 1, 18)\\n    metrics = _xmc2471_metrics(people, year)\\n    ws["A8"] = 1\\n    ws["B8"] = meta["title"]\\n\\n    for total_col, ages in (\\n        (3, range(15, 26)),\\n        (8, range(15, 36)),\\n        (13, range(15, 61)),\\n    ):\\n        ages = list(ages)\\n        population = _xmc2471_sum(metrics, ages, "total")\\n        bc1 = _xmc2471_sum(metrics, ages, "bc1_total")\\n        bc2 = _xmc2471_sum(metrics, ages, "bc2_total")\\n        ws.cell(8, total_col).value = _xmc2471_value(population, population)\\n        ws.cell(8, total_col + 1).value = _xmc2471_value(population, bc1)\\n        ws.cell(8, total_col + 3).value = _xmc2471_value(population, bc2)\\n\\n    ws["R8"] = None\'\n\n\ndef read_text(path: Path) -> str:\n    if not path.exists():\n        raise RuntimeError(f"Không tìm thấy: {path}")\n    return path.read_text(encoding="utf-8-sig", errors="strict")\n\n\ndef write_text(path: Path, value: str) -> None:\n    path.write_text(value, encoding="utf-8")\n\n\ndef function_node(source: str, name: str):\n    tree = ast.parse(source)\n    matches = [\n        node for node in tree.body\n        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))\n        and node.name == name\n    ]\n    if len(matches) != 1:\n        raise RuntimeError(f"Cần đúng 1 hàm {name}, tìm thấy {len(matches)}.")\n    return matches[0]\n\n\ndef function_span(source: str, name: str) -> tuple[int, int]:\n    node = function_node(source, name)\n    lines = source.splitlines(keepends=True)\n    start = sum(len(line) for line in lines[: int(node.lineno) - 1])\n    end = sum(len(line) for line in lines[: int(node.end_lineno)])\n    while end < len(source) and source[end:end + 1] in {"\\r", "\\n"}:\n        end += 1\n    return start, end\n\n\ndef get_function(source: str, name: str) -> str:\n    start, end = function_span(source, name)\n    return source[start:end]\n\n\ndef replace_function(source: str, name: str, replacement: str) -> str:\n    start, end = function_span(source, name)\n    return source[:start] + replacement.rstrip() + "\\n\\n\\n" + source[end:]\n\n\ndef patch_builder(source: str) -> tuple[str, list[str]]:\n    notes: list[str] = []\n    for name in (\n        "_age", "_female", "_ethnic", "_female_ethnic",\n        "_build_xmc3", "_build_cmc2", "_build_cmc1", "_build_xmc4",\n        "export_additional_report",\n    ):\n        function_node(source, name)\n\n    export_fn = get_function(source, "export_additional_report")\n    if FORMULA_CALL_MARKER not in export_fn or "apply_xmc_formula_contract(" not in export_fn:\n        raise RuntimeError("Chưa phát hiện Bài 4.7 hoàn chỉnh trong export.")\n\n    if START in source:\n        if END not in source:\n            raise RuntimeError("Có marker đầu 4.7.1 nhưng thiếu marker cuối.")\n        notes.append("Bài 4.7.1 đã tồn tại; không chèn lặp.")\n        return source, notes\n\n    insert_at, _ = function_span(source, "_build_xmc3")\n    source = source[:insert_at] + HELPERS + "\\n\\n\\n" + source[insert_at:]\n    source = replace_function(source, "_build_xmc3", NEW_XMC3)\n    source = replace_function(source, "_build_cmc2", NEW_CMC2)\n    source = replace_function(source, "_build_cmc1", NEW_CMC1)\n    source = replace_function(source, "_build_xmc4", NEW_XMC4)\n    ast.parse(source)\n\n    notes.extend([\n        "Đã giữ đúng bool ba trạng thái: None không thành False.",\n        "Đã nối CMC-1: mù chữ mức 1/mức 2.",\n        "Đã nối CMC-2: mù chữ mức 1/mức 2; không đoán Tôn giáo/Tái mù chữ.",\n        "Đã nối XMC-3: mù chữ mức 1/mức 2/biết chữ.",\n        "Đã nối XMC-4: biết chữ mức độ 1/mức độ 2.",\n        "Đạt chuẩn vẫn để bước công nhận riêng.",\n    ])\n    return source, notes\n\n\ndef db_snapshot() -> dict:\n    if not DB.exists():\n        return {"exists": False}\n    conn = sqlite3.connect(str(DB))\n    try:\n        integrity = str(conn.execute("PRAGMA integrity_check").fetchone()[0])\n        fk_count = len(conn.execute("PRAGMA foreign_key_check").fetchall())\n        columns = [row[1] for row in conn.execute(\n            "PRAGMA table_info(survey_person_year_records)"\n        ).fetchall()]\n        count = int(conn.execute(\n            "SELECT COUNT(*) FROM survey_person_year_records"\n        ).fetchone()[0])\n        stats = {}\n        for key, sql in (\n            ("target_true", "SELECT COUNT(*) FROM survey_person_year_records WHERE is_literacy_target=1"),\n            ("g3_true", "SELECT COUNT(*) FROM survey_person_year_records WHERE completed_grade_3=1"),\n            ("g3_false", "SELECT COUNT(*) FROM survey_person_year_records WHERE completed_grade_3=0"),\n            ("g5_true", "SELECT COUNT(*) FROM survey_person_year_records WHERE completed_grade_5=1"),\n            ("g5_false", "SELECT COUNT(*) FROM survey_person_year_records WHERE completed_grade_5=0"),\n        ):\n            stats[key] = int(conn.execute(sql).fetchone()[0])\n        return {\n            "exists": True, "integrity": integrity, "fk_count": fk_count,\n            "columns": columns, "count": count, "stats": stats,\n        }\n    finally:\n        conn.close()\n\n\ndef backup_db() -> None:\n    if not DB.exists():\n        return\n    src = sqlite3.connect(str(DB))\n    dst = sqlite3.connect(str(BACKUP / DB.name))\n    try:\n        src.backup(dst)\n    finally:\n        dst.close()\n        src.close()\n\n\ndef restore() -> None:\n    source_backup = BACKUP / BUILDERS.name\n    if source_backup.exists():\n        shutil.copy2(source_backup, BUILDERS)\n    db_backup = BACKUP / DB.name\n    if DB.exists() and db_backup.exists():\n        src = sqlite3.connect(str(db_backup))\n        dst = sqlite3.connect(str(DB))\n        try:\n            src.backup(dst)\n        finally:\n            dst.close()\n            src.close()\n\n\ndef clear_cache() -> None:\n    for cache in APP.rglob("__pycache__"):\n        if cache.is_dir():\n            shutil.rmtree(cache, ignore_errors=True)\n\n\ndef verify_builder(source: str) -> None:\n    ast.parse(source)\n    for token in (\n        START, END, "def _xmc2471_bool(", "def _xmc2471_metrics(",\n        \'"completed_grade_3"\', \'"completed_grade_5"\',\n        \'"mc1_total"\', \'"mc2_total"\', \'"bc1_total"\', \'"bc2_total"\',\n    ):\n        if token not in source:\n            raise RuntimeError("Verifier thiếu: " + token)\n\n    xmc3 = get_function(source, "_build_xmc3")\n    for token in (\'"mc1_total"\', \'"mc2_total"\', \'"bc2_total"\'):\n        if token not in xmc3:\n            raise RuntimeError("XMC-3 chưa nối đủ: " + token)\n\n    cmc1 = get_function(source, "_build_cmc1")\n    for token in ("mc1_keys", "mc2_keys", "index * 2"):\n        if token not in cmc1:\n            raise RuntimeError("CMC-1 chưa nối đủ: " + token)\n\n    cmc2 = get_function(source, "_build_cmc2")\n    for token in (\'"mc1_total"\', \'"mc2_total"\', "Tái mù chữ"):\n        if token not in cmc2:\n            raise RuntimeError("CMC-2 chưa nối đủ: " + token)\n\n    xmc4 = get_function(source, "_build_xmc4")\n    for token in (\'"bc1_total"\', \'"bc2_total"\', \'ws["R8"] = None\'):\n        if token not in xmc4:\n            raise RuntimeError("XMC-4 chưa nối đủ: " + token)\n\n    export_fn = get_function(source, "export_additional_report")\n    call_pos = export_fn.find("apply_xmc_formula_contract(")\n    save_pos = export_fn.find("workbook.save(output)")\n    if call_pos < 0 or save_pos < 0 or call_pos >= save_pos:\n        raise RuntimeError("Bộ tính 4.7 không còn nằm trước workbook.save(output).")\n\n\ndef verify_service() -> None:\n    text = read_text(SERVICE)\n    ast.parse(text)\n    for token in (\n        "CMC1_PERCENT_FORMULAS", "XMC3_PERCENT_FORMULAS",\n        "XMC4_PERCENT_FORMULAS", "def apply_xmc_formula_contract(",\n    ):\n        if token not in text:\n            raise RuntimeError("Service Bài 4.7 thiếu: " + token)\n\n\ndef main() -> None:\n    print("=" * 138)\n    print("BÀI 13B-11.15.2.4.7.1 - NỐI NGUỒN DỮ LIỆU XÓA MÙ CHỮ")\n    print("=" * 138)\n    print()\n    print("SẼ LÀM:")\n    print(" - CMC-1: nối mù chữ mức 1/mức 2.")\n    print(" - CMC-2: nối mù chữ mức 1/mức 2.")\n    print(" - XMC-3: nối mù chữ mức 1/mức 2/biết chữ.")\n    print(" - XMC-4: nối biết chữ mức độ 1/mức độ 2.")\n    print(" - Giữ Bài 4.7 tính tỷ lệ trước khi lưu Excel.")\n    print()\n    print("KHÔNG LÀM:")\n    print(" - Không UPDATE/ALTER database.")\n    print(" - Không sửa menu/route/template.")\n    print(" - Không biến None thành Không.")\n    print(" - Không suy diễn Tôn giáo/Tái mù chữ.")\n    print(" - Không tự kết luận Đạt chuẩn.")\n    print()\n\n    old_source = read_text(BUILDERS)\n    ast.parse(old_source)\n    verify_service()\n\n    before = db_snapshot()\n    if before.get("exists"):\n        if before.get("integrity") != "ok" or before.get("fk_count") != 0:\n            raise RuntimeError("Database không đạt kiểm tra an toàn trước cài.")\n        required = {\n            "is_literacy_target", "literacy_status",\n            "completed_grade_3", "completed_grade_5",\n        }\n        missing = required - set(before.get("columns", []))\n        if missing:\n            raise RuntimeError("Thiếu field XMC: " + ", ".join(sorted(missing)))\n\n    new_source, notes = patch_builder(old_source)\n    verify_builder(new_source)\n\n    EXPORTS.mkdir(parents=True, exist_ok=True)\n    BACKUP.mkdir(parents=True, exist_ok=False)\n    shutil.copy2(BUILDERS, BACKUP / BUILDERS.name)\n    shutil.copy2(SERVICE, BACKUP / SERVICE.name)\n    backup_db()\n\n    try:\n        if new_source != old_source:\n            write_text(BUILDERS, new_source)\n\n        py_compile.compile(str(BUILDERS), doraise=True)\n        py_compile.compile(str(SERVICE), doraise=True)\n        verify_builder(read_text(BUILDERS))\n        verify_service()\n\n        after = db_snapshot()\n        if before != after:\n            raise RuntimeError("Database bị thay đổi ngoài dự kiến.")\n        if after.get("exists") and (\n            after.get("integrity") != "ok" or after.get("fk_count") != 0\n        ):\n            raise RuntimeError("Database không đạt kiểm tra sau cài.")\n\n        REPORT.write_text(\n            "\\n".join([\n                "=" * 120,\n                "BÀI 13B-11.15.2.4.7.1 - NỐI NGUỒN XMC",\n                "=" * 120,\n                "",\n                "QUY TẮC:",\n                " - MC mức 1 = completed_grade_3=False.",\n                " - Biết chữ mức 1 = completed_grade_3=True.",\n                " - MC mức 2 = completed_grade_5=False.",\n                " - Biết chữ mức 2 = completed_grade_5=True.",\n                " - None giữ là chưa xác định.",\n                " - literacy_status không thay thế completed_grade_3/5.",\n                "",\n                *[" - " + note for note in notes],\n                "",\n                "DB trước: " + repr(before),\n                "DB sau  : " + repr(after),\n                "",\n                "Database: KHÔNG THAY ĐỔI.",\n                "Menu/route/template: KHÔNG THAY ĐỔI.",\n            ]),\n            encoding="utf-8",\n        )\n        clear_cache()\n\n    except Exception:\n        print()\n        print("CÓ LỖI - ĐANG KHÔI PHỤC SOURCE/DB...")\n        restore()\n        clear_cache()\n        raise\n\n    print("CÀI ĐẶT THÀNH CÔNG.")\n    print("Backup:", BACKUP)\n    print("Báo cáo:", REPORT)\n    print("Database: KHÔNG THAY ĐỔI.")\n    print()\n    print("=" * 138)\n    print("BÀI 13B-11.15.2.4.7.1 THÀNH CÔNG")\n    print("=" * 138)\n\n\nif __name__ == "__main__":\n    main()\n'
JS_REPLACEMENT = 'function updateLiteracy() {\n        const target = document.getElementById("is_literacy_target");\n        const details = document.getElementById("b131132_xmc_details");\n\n        if (!target || !details) return;\n\n        const age = parseAge();\n        const forcedByAge = age !== null && age >= 15;\n\n        if (forcedByAge) {\n            target.value = "CO";\n            target.disabled = true;\n            target.setAttribute(\n                "data-auto-xmc-age-15-plus",\n                "1"\n            );\n        } else {\n            target.disabled = false;\n            target.removeAttribute(\n                "data-auto-xmc-age-15-plus"\n            );\n        }\n\n        setVisible(\n            details,\n            forcedByAge || target.value === "CO"\n        );\n    }'
NOTE_HTML = '\n                        <!-- === BAI_13B_11_15_2_4_7_1_V2_AUTO_XMC_AGE_15_PLUS === -->\n                        <small\n                            id="b2471v2_xmc_age_rule"\n                            class="b131132-note"\n                        >\n                            Từ đủ 15 tuổi trở lên, hệ thống tự xác định\n                            Đối tượng điều tra Xóa mù chữ = Có.\n                        </small>\n'


def read_text(path: Path) -> str:
    if not path.exists():
        raise RuntimeError(f"Không tìm thấy: {path}")
    return path.read_text(encoding="utf-8-sig", errors="strict")


def write_text(path: Path, value: str) -> None:
    path.write_text(value, encoding="utf-8")


def clear_cache() -> None:
    for cache in APP.rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(cache, ignore_errors=True)


def backup_sqlite(source: Path, target: Path) -> None:
    if not source.exists():
        return
    src = sqlite3.connect(str(source))
    dst = sqlite3.connect(str(target))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()


def restore_sqlite(source: Path, target: Path) -> None:
    if not source.exists():
        return
    src = sqlite3.connect(str(source))
    dst = sqlite3.connect(str(target))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()


def db_snapshot() -> dict:
    conn = sqlite3.connect(str(DB))
    try:
        integrity = str(conn.execute("PRAGMA integrity_check").fetchone()[0])
        fk_count = len(conn.execute("PRAGMA foreign_key_check").fetchall())
        row_count = int(conn.execute(
            "SELECT COUNT(*) FROM survey_person_year_records"
        ).fetchone()[0])
        columns = [
            str(row[1])
            for row in conn.execute(
                "PRAGMA table_info(survey_person_year_records)"
            ).fetchall()
        ]
        stats = {}
        for key, sql in (
            ("target_true",
             "SELECT COUNT(*) FROM survey_person_year_records "
             "WHERE is_literacy_target = 1"),
            ("target_false",
             "SELECT COUNT(*) FROM survey_person_year_records "
             "WHERE is_literacy_target = 0"),
            ("target_null",
             "SELECT COUNT(*) FROM survey_person_year_records "
             "WHERE is_literacy_target IS NULL"),
            ("g3_true",
             "SELECT COUNT(*) FROM survey_person_year_records "
             "WHERE completed_grade_3 = 1"),
            ("g3_false",
             "SELECT COUNT(*) FROM survey_person_year_records "
             "WHERE completed_grade_3 = 0"),
            ("g5_true",
             "SELECT COUNT(*) FROM survey_person_year_records "
             "WHERE completed_grade_5 = 1"),
            ("g5_false",
             "SELECT COUNT(*) FROM survey_person_year_records "
             "WHERE completed_grade_5 = 0"),
        ):
            stats[key] = int(conn.execute(sql).fetchone()[0])
        return {
            "integrity": integrity,
            "fk_count": fk_count,
            "row_count": row_count,
            "columns": columns,
            "stats": stats,
        }
    finally:
        conn.close()


def first_year(value) -> int | None:
    text = str(value or "")
    match = re.search(r"(?<!\d)(19\d{2}|20\d{2}|21\d{2})(?!\d)", text)
    if not match:
        return None
    year = int(match.group(1))
    return year if 1900 <= year <= 2199 else None


def birth_year(value) -> int | None:
    if value is None:
        return None
    text = str(value).strip()
    match = re.search(r"(19\d{2}|20\d{2}|21\d{2})", text)
    if not match:
        return None
    year = int(match.group(1))
    return year if 1900 <= year <= 2199 else None


def eligible_record_ids(conn: sqlite3.Connection) -> list[int]:
    rows = conn.execute(
        """
        SELECT
            spr.id,
            sp.date_of_birth,
            sy.code,
            sy.name
        FROM survey_person_year_records AS spr
        JOIN survey_people AS sp
          ON sp.id = spr.survey_person_id
        JOIN school_years AS sy
          ON sy.id = spr.school_year_id
        ORDER BY spr.id
        """
    ).fetchall()

    result: list[int] = []
    for record_id, dob, sy_code, sy_name in rows:
        by = birth_year(dob)
        ry = first_year(sy_code)
        if ry is None:
            ry = first_year(sy_name)
        if by is None or ry is None:
            continue
        age = int(ry) - int(by)
        if age >= 15:
            result.append(int(record_id))
    return result


def migrate_existing_targets() -> dict:
    conn = sqlite3.connect(str(DB))
    try:
        ids = eligible_record_ids(conn)
        already_true = 0
        if ids:
            already_true = sum(
                1
                for record_id in ids
                if conn.execute(
                    "SELECT is_literacy_target "
                    "FROM survey_person_year_records WHERE id=?",
                    (record_id,),
                ).fetchone()[0] == 1
            )

            conn.executemany(
                """
                UPDATE survey_person_year_records
                   SET is_literacy_target = 1
                 WHERE id = ?
                   AND (
                       is_literacy_target IS NULL
                       OR is_literacy_target <> 1
                   )
                """,
                [(record_id,) for record_id in ids],
            )
        conn.commit()

        remaining = []
        for record_id in ids:
            row = conn.execute(
                "SELECT is_literacy_target "
                "FROM survey_person_year_records WHERE id=?",
                (record_id,),
            ).fetchone()
            if row is None or row[0] != 1:
                remaining.append(record_id)

        if remaining:
            raise RuntimeError(
                "Vẫn còn bản ghi >=15 tuổi chưa được đánh dấu XMC=True: "
                + ", ".join(str(x) for x in remaining[:20])
            )

        integrity = str(conn.execute("PRAGMA integrity_check").fetchone()[0])
        fk_count = len(conn.execute("PRAGMA foreign_key_check").fetchall())
        if integrity != "ok":
            raise RuntimeError("integrity_check sau migrate != ok.")
        if fk_count != 0:
            raise RuntimeError("foreign_key_check sau migrate có lỗi.")

        return {
            "eligible_records": len(ids),
            "already_true_before": already_true,
            "changed_to_true": len(ids) - already_true,
        }
    finally:
        conn.close()


def find_save_router() -> Path:
    path = ROUTERS / "surveys.py"
    if not path.exists():
        raise RuntimeError("Không tìm thấy app/routers/surveys.py.")
    source = read_text(path)
    ast.parse(source)
    if PY_START not in source or PY_END not in source:
        raise RuntimeError(
            "surveys.py chưa có marker Bài 13B-11.13.2."
        )
    if source.count(PY_START) != 1 or source.count(PY_END) != 1:
        raise RuntimeError("Marker SAVE_FIELDS không duy nhất.")
    return path


def patch_router(source: str) -> str:
    if ROUTER_MARKER in source:
        return source

    start = source.find(PY_START)
    end = source.find(PY_END, start)
    if start < 0 or end < 0:
        raise RuntimeError("Không xác định được block lưu XMC.")

    block = source[start:end]
    assignment = re.search(
        r"(?m)^([ \t]*)([A-Za-z_]\w*)"
        r"\.is_literacy_target"
        r"\s*=\s*_b131132_is_literacy_target\s*$",
        block,
    )
    if not assignment:
        raise RuntimeError(
            "Không tìm thấy dòng gán is_literacy_target trong block lưu."
        )

    indent = assignment.group(1)
    insert_pos = assignment.start()

    lines = [
        ROUTER_MARKER,
        "_b2471v2_birth_year = getattr(",
        "    getattr(person, \"date_of_birth\", None),",
        "    \"year\",",
        "    None,",
        ")",
        "",
        "_b2471v2_school_year_text = str(",
        "    getattr(",
        "        getattr(batch, \"school_year\", None),",
        "        \"code\",",
        "        \"\",",
        "    )",
        "    or \"\"",
        ")",
        "",
        "_b2471v2_reference_year = None",
        "",
        "for _b2471v2_index in range(",
        "    max(0, len(_b2471v2_school_year_text) - 3)",
        "):",
        "    _b2471v2_piece = _b2471v2_school_year_text[",
        "        _b2471v2_index : _b2471v2_index + 4",
        "    ]",
        "    if _b2471v2_piece.isdigit():",
        "        _b2471v2_candidate = int(_b2471v2_piece)",
        "        if 1900 <= _b2471v2_candidate <= 2199:",
        "            _b2471v2_reference_year = _b2471v2_candidate",
        "            break",
        "",
        "_b2471v2_age = None",
        "if (",
        "    _b2471v2_birth_year is not None",
        "    and _b2471v2_reference_year is not None",
        "):",
        "    _b2471v2_age = (",
        "        int(_b2471v2_reference_year)",
        "        - int(_b2471v2_birth_year)",
        "    )",
        "",
        "if _b2471v2_age is not None and _b2471v2_age >= 15:",
        "    # Từ đủ 15 tuổi: bắt buộc là đối tượng điều tra XMC.",
        "    _b131132_is_literacy_target = True",
        "",
    ]

    logic = "\n".join(
        (indent + line if line else "")
        for line in lines
    )

    new_block = block[:insert_pos] + logic + block[insert_pos:]
    result = source[:start] + new_block + source[end:]
    ast.parse(result)
    return result


def patch_template(source: str) -> str:
    if TEMPLATE_MARKER in source:
        return source

    select_pos = source.find('id="is_literacy_target"')
    if select_pos < 0:
        raise RuntimeError("Không tìm thấy is_literacy_target trong template.")

    select_end = source.find("</select>", select_pos)
    if select_end < 0:
        raise RuntimeError("Không tìm thấy </select> của is_literacy_target.")
    select_end += len("</select>")

    source = source[:select_end] + NOTE_HTML + source[select_end:]

    pattern = re.compile(
        r"function[ \t]+updateLiteracy\(\)[ \t]*\{.*?\n[ \t]*\}",
        re.DOTALL,
    )
    matches = list(pattern.finditer(source))
    if len(matches) != 1:
        raise RuntimeError(
            "Cần đúng 1 updateLiteracy(); "
            f"tìm thấy {len(matches)}."
        )

    source = pattern.sub(JS_REPLACEMENT, source, count=1)
    return source


def verify_router(source: str) -> None:
    ast.parse(source)
    for token in (
        ROUTER_MARKER,
        "_b2471v2_age >= 15",
        "_b131132_is_literacy_target = True",
        ".is_literacy_target = _b131132_is_literacy_target",
        "completed_grade_3",
        "completed_grade_5",
    ):
        if token not in source:
            raise RuntimeError("Verifier router thiếu: " + token)


def verify_template(source: str) -> None:
    for token in (
        TEMPLATE_MARKER,
        'id="is_literacy_target"',
        "const forcedByAge = age !== null && age >= 15;",
        'target.value = "CO";',
        "target.disabled = true;",
        "data-auto-xmc-age-15-plus",
    ):
        if token not in source:
            raise RuntimeError("Verifier template thiếu: " + token)

    match = re.search(
        r"function[ \t]+updateLiteracy\(\)[ \t]*\{.*?\n[ \t]*\}",
        source,
        re.DOTALL,
    )
    if not match:
        raise RuntimeError("Không đọc lại được updateLiteracy().")
    if "MutationObserver" in match.group(0):
        raise RuntimeError("updateLiteracy mới không được chứa MutationObserver.")


def verify_builder_source() -> None:
    source = read_text(BUILDERS)
    ast.parse(source)
    for token in (
        "BAI_13B_11_15_2_4_7_1_XMC_DATA_SOURCE_START",
        "def _xmc2471_metrics(",
        '"completed_grade_3"',
        '"completed_grade_5"',
        "def _build_xmc3(",
        "def _build_cmc2(",
        "def _build_cmc1(",
        "def _build_xmc4(",
        "apply_xmc_formula_contract(",
    ):
        if token not in source:
            raise RuntimeError(
                "Bài 4.7.1 nguồn XMC chưa đầy đủ: " + token
            )


def restore_all(router: Path) -> None:
    for source, target in (
        (BACKUP / BUILDERS.name, BUILDERS),
        (BACKUP / SERVICE.name, SERVICE),
        (BACKUP / router.name, router),
        (BACKUP / TEMPLATE.name, TEMPLATE),
    ):
        if source.exists():
            shutil.copy2(source, target)

    db_backup = BACKUP / DB.name
    if db_backup.exists():
        restore_sqlite(db_backup, DB)

    clear_cache()


def run_base_471() -> None:
    namespace = {
        "__name__": "embedded_bai_13b_11_15_2_4_7_1",
        "__file__": "<embedded_bai_13b_11_15_2_4_7_1>",
    }
    exec(
        compile(
            BASE_INSTALLER_CONTENT,
            "<embedded_bai_13b_11_15_2_4_7_1>",
            "exec",
        ),
        namespace,
        namespace,
    )
    main_fn = namespace.get("main")
    if not callable(main_fn):
        raise RuntimeError("Không nạp được main() Bài 4.7.1 nền.")
    main_fn()


def main() -> None:
    print("=" * 148)
    print(
        "BÀI 13B-11.15.2.4.7.1 V2 - "
        "TỪ 15 TUỔI TRỞ LÊN BẮT BUỘC THUỘC ĐỐI TƯỢNG ĐIỀU TRA XMC"
    )
    print("=" * 148)
    print()
    print("QUY TẮC MỚI:")
    print(" - Đủ 15 tuổi trở lên: is_literacy_target=True bắt buộc.")
    print(" - Giao diện tự chọn Có và khóa lựa chọn.")
    print(" - Backend tự ép Có khi lưu, không phụ thuộc JavaScript.")
    print(" - Bản ghi cũ >=15 tuổi được đồng bộ sang True.")
    print(" - Không tự thay literacy_status/completed_grade_3/completed_grade_5.")
    print()
    print("LƯU Ý:")
    print(
        " - Các biểu XMC hiện thống kê các nhóm chính thức đến 60 tuổi; "
        "người >60 vẫn được đánh dấu là đối tượng điều tra trong dữ liệu."
    )
    print()

    router = find_save_router()

    for path in (BUILDERS, SERVICE, DB, router, TEMPLATE):
        if not path.exists():
            raise RuntimeError(f"Không tìm thấy: {path}")

    before = db_snapshot()
    if before["integrity"] != "ok" or before["fk_count"] != 0:
        raise RuntimeError("Database không đạt kiểm tra an toàn trước cài.")

    required_columns = {
        "is_literacy_target",
        "literacy_status",
        "completed_grade_3",
        "completed_grade_5",
    }
    missing = required_columns - set(before["columns"])
    if missing:
        raise RuntimeError(
            "Database thiếu field XMC: " + ", ".join(sorted(missing))
        )

    EXPORTS.mkdir(parents=True, exist_ok=True)
    BACKUP.mkdir(parents=True, exist_ok=False)

    shutil.copy2(BUILDERS, BACKUP / BUILDERS.name)
    shutil.copy2(SERVICE, BACKUP / SERVICE.name)
    shutil.copy2(router, BACKUP / router.name)
    shutil.copy2(TEMPLATE, BACKUP / TEMPLATE.name)
    backup_sqlite(DB, BACKUP / DB.name)

    migration = None

    try:
        # Cài/đảm bảo phần nối nguồn 4.7.1.
        run_base_471()
        verify_builder_source()

        # Backend: >=15 tuổi luôn True.
        router_old = read_text(router)
        router_new = patch_router(router_old)
        verify_router(router_new)
        if router_new != router_old:
            write_text(router, router_new)

        # UI: tự Có + khóa.
        template_old = read_text(TEMPLATE)
        template_new = patch_template(template_old)
        verify_template(template_new)
        if template_new != template_old:
            write_text(TEMPLATE, template_new)

        # Đồng bộ record cũ.
        migration = migrate_existing_targets()

        py_compile.compile(str(router), doraise=True)
        py_compile.compile(str(BUILDERS), doraise=True)
        py_compile.compile(str(SERVICE), doraise=True)

        verify_router(read_text(router))
        verify_template(read_text(TEMPLATE))
        verify_builder_source()

        after = db_snapshot()

        if after["integrity"] != "ok" or after["fk_count"] != 0:
            raise RuntimeError("Database không đạt kiểm tra sau cài.")
        if after["row_count"] != before["row_count"]:
            raise RuntimeError(
                "Số survey_person_year_records thay đổi ngoài dự kiến."
            )
        if after["columns"] != before["columns"]:
            raise RuntimeError("Schema database thay đổi ngoài dự kiến.")

        for key in ("g3_true", "g3_false", "g5_true", "g5_false"):
            if after["stats"][key] != before["stats"][key]:
                raise RuntimeError(
                    "Dữ liệu lớp 3/lớp 5 bị thay đổi ngoài dự kiến: " + key
                )

        clear_cache()

    except Exception:
        print()
        print(
            "CÓ LỖI - ĐANG KHÔI PHỤC SOURCE + TEMPLATE + DATABASE..."
        )
        restore_all(router)
        raise

    lines = [
        "=" * 148,
        "BÀI 13B-11.15.2.4.7.1 V2 - KẾT QUẢ",
        "=" * 148,
        "",
        "QUY TẮC ĐÃ CÀI:",
        " - Đủ 15 tuổi trở lên = đối tượng điều tra XMC bắt buộc.",
        " - is_literacy_target=True.",
        " - UI tự chọn Có và khóa lựa chọn.",
        " - Backend tự ép True khi lưu.",
        " - Báo cáo XMC tiếp tục theo nhóm tuổi của mẫu đến 60.",
        "",
        "KHÔNG TỰ THAY:",
        " - literacy_status.",
        " - completed_grade_3.",
        " - completed_grade_5.",
        " - Kết luận Đạt/Không đạt.",
        "",
        "ĐỒNG BỘ DB:",
        f" - Record đủ >=15 tuổi: {migration['eligible_records']}",
        f" - Đã True trước cài: {migration['already_true_before']}",
        f" - Chuyển sang True: {migration['changed_to_true']}",
        "",
        "DB trước: " + repr(before),
        "DB sau: " + repr(after),
        "",
        "AN TOÀN:",
        " - Không ALTER TABLE.",
        " - Không thêm/xóa year-record.",
        " - Không thay completed_grade_3/5.",
        " - Có backup + rollback.",
        f" - Backup: {BACKUP}",
        "",
    ]
    REPORT.write_text("\n".join(lines), encoding="utf-8")

    print("KIỂM TRA:")
    print(" - Nối nguồn 4.7.1: OK")
    print(" - Backend ép XMC >=15: OK")
    print(" - UI tự Có >=15: OK")
    print(" - Đồng bộ DB cũ: OK")
    print(" - completed_grade_3/5 không đổi: OK")
    print(" - integrity/FK: OK")
    print()
    print("Record >=15 tuổi:", migration["eligible_records"])
    print("Chuyển sang XMC=True:", migration["changed_to_true"])
    print("Backup:", BACKUP)
    print("Báo cáo:", REPORT)
    print()
    print("=" * 148)
    print("BÀI 13B-11.15.2.4.7.1 V2 THÀNH CÔNG")
    print("=" * 148)


if __name__ == "__main__":
    main()
