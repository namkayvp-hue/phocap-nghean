from __future__ import annotations

import ast
import os
import py_compile
import re
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path


PROJECT = Path(
    os.environ.get(
        "PHOCAP_PROJECT",
        r"C:\PhoCap",
    )
).resolve()

APP = PROJECT / "app"
EXPORTS = PROJECT / "exports"
DB = PROJECT / "data" / "phocap.db"

ROUTER = APP / "routers" / "surveys.py"
TEMPLATE = APP / "templates" / "surveys" / "year_records.html"
BUILDERS = APP / "pcgd_xmc_report_builders_v1.py"
FORMULA_SERVICE = APP / "services" / "xmc_report_v247.py"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

BACKUP = (
    EXPORTS
    / f"backup_bai_13b_11_15_2_4_7_1b_{STAMP}"
)

REPORT = (
    EXPORTS
    / f"bao_cao_bai_13b_11_15_2_4_7_1b_{STAMP}.txt"
)

SAVE_START = "# === BAI_13B_11_13_2_SAVE_FIELDS_START ==="
SAVE_END = "# === BAI_13B_11_13_2_SAVE_FIELDS_END ==="

AGE15_MARKER = (
    "# === BAI_13B_11_15_2_4_7_1A_"
    "FORCE_XMC_AGE15_START ==="
)

PY_START = (
    "# === BAI_13B_11_15_2_4_7_1B_"
    "DERIVE_LITERACY_STATUS_START ==="
)

PY_END = (
    "# === BAI_13B_11_15_2_4_7_1B_"
    "DERIVE_LITERACY_STATUS_END ==="
)

UI_START = (
    "<!-- === BAI_13B_11_15_2_4_7_1B_"
    "DERIVED_STATUS_UI_START === -->"
)

UI_END = (
    "<!-- === BAI_13B_11_15_2_4_7_1B_"
    "DERIVED_STATUS_UI_END === -->"
)

REPORT_START = (
    "# === BAI_13B_11_15_2_4_7_1B_"
    "REPORT_SOURCE_START ==="
)

REPORT_END = (
    "# === BAI_13B_11_15_2_4_7_1B_"
    "REPORT_SOURCE_END ==="
)

FORMULA_CALL_MARKER = (
    "# === BAI_13B_11_15_2_4_7_"
    "APPLY_XMC_BEFORE_SAVE ==="
)

DERIVE_BLOCK_TEMPLATE = '# === BAI_13B_11_15_2_4_7_1B_DERIVE_LITERACY_STATUS_START ===\n# Tình trạng XMC không còn nhập tay.\n# Field literacy_status chỉ giữ để tương thích dữ liệu/lịch sử.\n# Báo cáo lấy trực tiếp completed_grade_3 / completed_grade_5.\n#\n# Quy ước:\n# - Có False lớp 3/lớp 5 -> THEO_DOI_XMC.\n# - Cả lớp 3 và lớp 5 True -> KHONG_THUOC_DIEN\n#   (không thuộc diện THEO DÕI mù chữ; vẫn thuộc diện ĐIỀU TRA).\n# - Còn thiếu -> CHUA_XAC_DINH.\n_b1471b_g3 = __RECORD_VAR__.completed_grade_3\n_b1471b_g5 = __RECORD_VAR__.completed_grade_5\n\nif _b131132_is_literacy_target is True:\n    if _b1471b_g3 is False or _b1471b_g5 is False:\n        __RECORD_VAR__.literacy_status = "THEO_DOI_XMC"\n    elif _b1471b_g3 is True and _b1471b_g5 is True:\n        __RECORD_VAR__.literacy_status = "KHONG_THUOC_DIEN"\n    else:\n        __RECORD_VAR__.literacy_status = "CHUA_XAC_DINH"\nelse:\n    __RECORD_VAR__.literacy_status = "CHUA_XAC_DINH"\n# === BAI_13B_11_15_2_4_7_1B_DERIVE_LITERACY_STATUS_END ==='
READONLY_STATUS_BLOCK = '<!-- === BAI_13B_11_15_2_4_7_1B_DERIVED_STATUS_UI_START === -->\n<div\n    id="b1471b_literacy_status_box"\n    class="b1471b-derived-status"\n>\n    <label>\n        Tình trạng Xóa mù chữ\n        <span style="font-weight:600;">\n            (hệ thống tự xác định)\n        </span>\n    </label>\n\n    <div\n        id="b1471b_literacy_status_text"\n        class="form-control"\n        style="\n            background:#f4f6f8;\n            min-height:42px;\n            display:flex;\n            align-items:center;\n            font-weight:700;\n        "\n    >\n        Chưa đủ dữ liệu xác định\n    </div>\n\n    <small class="b131132-note">\n        Không nhập tay. Hệ thống suy ra từ\n        “Hoàn thành lớp 3” và “Hoàn thành lớp 5”.\n    </small>\n</div>\n<!-- === BAI_13B_11_15_2_4_7_1B_DERIVED_STATUS_UI_END === -->'
UI_SCRIPT = '<!-- === BAI_13B_11_15_2_4_7_1B_DERIVED_STATUS_SCRIPT_START === -->\n<script>\n(function () {\n    "use strict";\n\n    function deriveXmcStatusText() {\n        const g3 =\n            document.getElementById(\n                "completed_grade_3"\n            );\n\n        const g5 =\n            document.getElementById(\n                "completed_grade_5"\n            );\n\n        const output =\n            document.getElementById(\n                "b1471b_literacy_status_text"\n            );\n\n        if (!g3 || !g5 || !output) {\n            return;\n        }\n\n        const v3 = String(\n            g3.value || ""\n        ).toUpperCase();\n\n        const v5 = String(\n            g5.value || ""\n        ).toUpperCase();\n\n        let text =\n            "Chưa đủ dữ liệu xác định";\n\n        if (\n            v3 === "KHONG"\n            && v5 === "CO"\n        ) {\n            text =\n                "Dữ liệu cần rà soát: lớp 5 = Có nhưng lớp 3 = Không";\n        } else if (\n            v3 === "KHONG"\n        ) {\n            text =\n                "Mù chữ mức độ 1 – chưa hoàn thành lớp 3";\n        } else if (\n            v3 === "CO"\n            && v5 === "KHONG"\n        ) {\n            text =\n                "Biết chữ mức độ 1 – chưa hoàn thành lớp 5";\n        } else if (\n            v3 === "CO"\n            && v5 === "CO"\n        ) {\n            text =\n                "Biết chữ mức độ 2";\n        }\n\n        output.textContent = text;\n    }\n\n    document.addEventListener(\n        "DOMContentLoaded",\n        function () {\n            const g3 =\n                document.getElementById(\n                    "completed_grade_3"\n                );\n\n            const g5 =\n                document.getElementById(\n                    "completed_grade_5"\n                );\n\n            if (g3) {\n                g3.addEventListener(\n                    "change",\n                    deriveXmcStatusText\n                );\n            }\n\n            if (g5) {\n                g5.addEventListener(\n                    "change",\n                    deriveXmcStatusText\n                );\n            }\n\n            deriveXmcStatusText();\n\n            window.setTimeout(\n                deriveXmcStatusText,\n                120\n            );\n\n            window.setTimeout(\n                deriveXmcStatusText,\n                450\n            );\n        }\n    );\n})();\n</script>\n<!-- === BAI_13B_11_15_2_4_7_1B_DERIVED_STATUS_SCRIPT_END === -->'
REPORT_HELPERS = '# === BAI_13B_11_15_2_4_7_1B_REPORT_SOURCE_START ===\ndef _xmc1471b_bool(\n    record: SurveyPersonYearRecord | None,\n    field_name: str,\n) -> bool | None:\n    if record is None:\n        return None\n\n    value = getattr(\n        record,\n        field_name,\n        None,\n    )\n\n    if value is True:\n        return True\n\n    if value is False:\n        return False\n\n    if value == 1:\n        return True\n\n    if value == 0:\n        return False\n\n    text = str(\n        value or ""\n    ).strip().upper()\n\n    if text in {\n        "CO",\n        "CÓ",\n        "TRUE",\n        "YES",\n        "1",\n    }:\n        return True\n\n    if text in {\n        "KHONG",\n        "KHÔNG",\n        "FALSE",\n        "NO",\n        "0",\n    }:\n        return False\n\n    return None\n\n\ndef _xmc1471b_metrics(\n    people: list[\n        tuple[\n            SurveyPerson,\n            SurveyPersonYearRecord | None,\n        ]\n    ],\n    year: int,\n) -> dict[int, dict[str, int]]:\n    """\n    Nguồn chuẩn cho 4 biểu XMC.\n\n    Mọi người >=15 tuổi là đối tượng ĐIỀU TRA XMC.\n    Không lọc bằng literacy_status.\n\n    - MC mức 1 : completed_grade_3=False\n    - BC mức 1 : completed_grade_3=True\n    - MC mức 2 : completed_grade_5=False\n    - BC mức 2 : completed_grade_5=True\n    - None     : chưa phân loại, vẫn nằm trong dân số\n    """\n    keys = (\n        "total",\n        "female",\n        "ethnic",\n        "female_ethnic",\n        "mc1_total",\n        "mc1_female",\n        "mc1_ethnic",\n        "mc1_female_ethnic",\n        "mc2_total",\n        "mc2_female",\n        "mc2_ethnic",\n        "mc2_female_ethnic",\n        "bc1_total",\n        "bc1_female",\n        "bc1_ethnic",\n        "bc1_female_ethnic",\n        "bc2_total",\n        "bc2_female",\n        "bc2_ethnic",\n        "bc2_female_ethnic",\n    )\n\n    result: dict[\n        int,\n        dict[str, int],\n    ] = {}\n\n    for person, record in people:\n        age = _age(\n            person,\n            year,\n        )\n\n        if age is None or age < 15:\n            continue\n\n        if age not in result:\n            result[age] = {\n                key: 0\n                for key in keys\n            }\n\n        item = result[age]\n\n        female = bool(\n            _female(person)\n        )\n\n        ethnic = bool(\n            _ethnic(person)\n        )\n\n        female_ethnic = bool(\n            _female_ethnic(person)\n        )\n\n        item["total"] += 1\n        item["female"] += int(female)\n        item["ethnic"] += int(ethnic)\n        item["female_ethnic"] += int(\n            female_ethnic\n        )\n\n        grade3 = _xmc1471b_bool(\n            record,\n            "completed_grade_3",\n        )\n\n        grade5 = _xmc1471b_bool(\n            record,\n            "completed_grade_5",\n        )\n\n        if grade3 is False:\n            item["mc1_total"] += 1\n            item["mc1_female"] += int(\n                female\n            )\n            item["mc1_ethnic"] += int(\n                ethnic\n            )\n            item["mc1_female_ethnic"] += int(\n                female_ethnic\n            )\n\n        elif grade3 is True:\n            item["bc1_total"] += 1\n            item["bc1_female"] += int(\n                female\n            )\n            item["bc1_ethnic"] += int(\n                ethnic\n            )\n            item["bc1_female_ethnic"] += int(\n                female_ethnic\n            )\n\n        if grade5 is False:\n            item["mc2_total"] += 1\n            item["mc2_female"] += int(\n                female\n            )\n            item["mc2_ethnic"] += int(\n                ethnic\n            )\n            item["mc2_female_ethnic"] += int(\n                female_ethnic\n            )\n\n        elif grade5 is True:\n            item["bc2_total"] += 1\n            item["bc2_female"] += int(\n                female\n            )\n            item["bc2_ethnic"] += int(\n                ethnic\n            )\n            item["bc2_female_ethnic"] += int(\n                female_ethnic\n            )\n\n    return result\n\n\ndef _xmc1471b_sum(\n    metrics: dict[int, dict[str, int]],\n    ages,\n    key: str,\n) -> int:\n    return sum(\n        int(\n            metrics\n            .get(\n                int(age),\n                {},\n            )\n            .get(\n                key,\n                0,\n            )\n            or 0\n        )\n        for age in ages\n    )\n\n\ndef _xmc1471b_value(\n    population: int,\n    value: int,\n):\n    if int(\n        population or 0\n    ) <= 0:\n        return None\n\n    return int(\n        value or 0\n    )\n# === BAI_13B_11_15_2_4_7_1B_REPORT_SOURCE_END ==='
NEW_XMC3 = 'def _build_xmc3(\n    ws: Any,\n    people: list[\n        tuple[\n            SurveyPerson,\n            SurveyPersonYearRecord | None,\n        ]\n    ],\n    year: int,\n) -> None:\n    row_by_age: dict[int, int] = {}\n\n    for age in range(15, 26):\n        row_by_age[age] = 9 + age - 15\n\n    for age in range(26, 36):\n        row_by_age[age] = 21 + age - 26\n\n    for age in range(36, 61):\n        row_by_age[age] = 32 + age - 36\n\n    metrics = _xmc1471b_metrics(\n        people,\n        year,\n    )\n\n    column_keys = (\n        (3, "total"),\n        (4, "female"),\n        (5, "ethnic"),\n        (6, "female_ethnic"),\n        (7, "mc1_total"),\n        (8, "mc1_female"),\n        (9, "mc1_ethnic"),\n        (10, "mc1_female_ethnic"),\n        (11, "mc2_total"),\n        (12, "mc2_female"),\n        (13, "mc2_ethnic"),\n        (14, "mc2_female_ethnic"),\n        (15, "bc2_total"),\n        (16, "bc2_female"),\n        (17, "bc2_ethnic"),\n        (18, "bc2_female_ethnic"),\n    )\n\n    for age, row in row_by_age.items():\n        item = metrics.get(\n            age,\n            {},\n        )\n\n        population = int(\n            item.get(\n                "total",\n                0,\n            )\n            or 0\n        )\n\n        ws.cell(\n            row,\n            2,\n        ).value = year - age\n\n        for col, key in column_keys:\n            value = int(\n                item.get(\n                    key,\n                    0,\n                )\n                or 0\n            )\n\n            ws.cell(\n                row,\n                col,\n            ).value = _xmc1471b_value(\n                population,\n                value,\n            )\n\n    for row, ages in (\n        (20, range(15, 26)),\n        (31, range(15, 36)),\n        (57, range(15, 61)),\n    ):\n        ages = list(ages)\n\n        population = _xmc1471b_sum(\n            metrics,\n            ages,\n            "total",\n        )\n\n        for col, key in column_keys:\n            value = _xmc1471b_sum(\n                metrics,\n                ages,\n                key,\n            )\n\n            ws.cell(\n                row,\n                col,\n            ).value = _xmc1471b_value(\n                population,\n                value,\n            )\n'
NEW_CMC2 = 'def _build_cmc2(\n    ws: Any,\n    people: list[\n        tuple[\n            SurveyPerson,\n            SurveyPersonYearRecord | None,\n        ]\n    ],\n    year: int,\n) -> None:\n    _clear_range(\n        ws,\n        8,\n        11,\n        2,\n        19,\n    )\n\n    metrics = _xmc1471b_metrics(\n        people,\n        year,\n    )\n\n    groups = (\n        (8, range(15, 26)),\n        (9, range(26, 36)),\n        (10, range(36, 61)),\n        (11, range(15, 61)),\n    )\n\n    for row, ages in groups:\n        ages = list(ages)\n\n        population = _xmc1471b_sum(\n            metrics,\n            ages,\n            "total",\n        )\n\n        assignments = {\n            2: "total",\n            3: "female",\n            4: "ethnic",\n            6: "mc1_total",\n            7: "mc1_female",\n            8: "mc1_ethnic",\n            10: "mc2_total",\n            11: "mc2_female",\n            12: "mc2_ethnic",\n        }\n\n        for col, key in assignments.items():\n            value = _xmc1471b_sum(\n                metrics,\n                ages,\n                key,\n            )\n\n            ws.cell(\n                row,\n                col,\n            ).value = _xmc1471b_value(\n                population,\n                value,\n            )\n\n        for col in (\n            5,\n            9,\n            13,\n            14,\n            15,\n            16,\n            17,\n            18,\n            19,\n        ):\n            ws.cell(\n                row,\n                col,\n            ).value = None\n'
NEW_CMC1 = 'def _build_cmc1(\n    ws: Any,\n    people: list[\n        tuple[\n            SurveyPerson,\n            SurveyPersonYearRecord | None,\n        ]\n    ],\n    year: int,\n    meta: dict[str, str],\n) -> None:\n    _clear_range(\n        ws,\n        8,\n        8,\n        3,\n        66,\n    )\n\n    metrics = _xmc1471b_metrics(\n        people,\n        year,\n    )\n\n    all_people = [\n        person\n        for person, _record\n        in people\n    ]\n\n    ws["A8"] = 1\n    ws["B8"] = meta["title"]\n    ws["C8"] = len(all_people)\n    ws["D8"] = sum(\n        int(_female(person))\n        for person in all_people\n    )\n    ws["E8"] = sum(\n        int(_ethnic(person))\n        for person in all_people\n    )\n    ws["F8"] = sum(\n        int(_female_ethnic(person))\n        for person in all_people\n    )\n\n    groups = (\n        (7, range(15, 26)),\n        (27, range(15, 36)),\n        (47, range(15, 61)),\n    )\n\n    demographic_keys = (\n        "total",\n        "female",\n        "ethnic",\n        "female_ethnic",\n    )\n\n    mc1_keys = (\n        "mc1_total",\n        "mc1_female",\n        "mc1_ethnic",\n        "mc1_female_ethnic",\n    )\n\n    mc2_keys = (\n        "mc2_total",\n        "mc2_female",\n        "mc2_ethnic",\n        "mc2_female_ethnic",\n    )\n\n    for start_col, ages in groups:\n        ages = list(ages)\n\n        population = _xmc1471b_sum(\n            metrics,\n            ages,\n            "total",\n        )\n\n        for offset, key in enumerate(\n            demographic_keys\n        ):\n            value = _xmc1471b_sum(\n                metrics,\n                ages,\n                key,\n            )\n\n            ws.cell(\n                8,\n                start_col + offset,\n            ).value = _xmc1471b_value(\n                population,\n                value,\n            )\n\n        for index, key in enumerate(\n            mc1_keys\n        ):\n            value = _xmc1471b_sum(\n                metrics,\n                ages,\n                key,\n            )\n\n            ws.cell(\n                8,\n                start_col + 4 + index * 2,\n            ).value = _xmc1471b_value(\n                population,\n                value,\n            )\n\n        for index, key in enumerate(\n            mc2_keys\n        ):\n            value = _xmc1471b_sum(\n                metrics,\n                ages,\n                key,\n            )\n\n            ws.cell(\n                8,\n                start_col + 12 + index * 2,\n            ).value = _xmc1471b_value(\n                population,\n                value,\n            )\n'
NEW_XMC4 = 'def _build_xmc4(\n    ws: Any,\n    people: list[\n        tuple[\n            SurveyPerson,\n            SurveyPersonYearRecord | None,\n        ]\n    ],\n    year: int,\n    meta: dict[str, str],\n) -> None:\n    _clear_range(\n        ws,\n        8,\n        8,\n        1,\n        18,\n    )\n\n    metrics = _xmc1471b_metrics(\n        people,\n        year,\n    )\n\n    ws["A8"] = 1\n    ws["B8"] = meta["title"]\n\n    groups = (\n        (3, range(15, 26)),\n        (8, range(15, 36)),\n        (13, range(15, 61)),\n    )\n\n    for total_col, ages in groups:\n        ages = list(ages)\n\n        population = _xmc1471b_sum(\n            metrics,\n            ages,\n            "total",\n        )\n\n        bc1 = _xmc1471b_sum(\n            metrics,\n            ages,\n            "bc1_total",\n        )\n\n        bc2 = _xmc1471b_sum(\n            metrics,\n            ages,\n            "bc2_total",\n        )\n\n        ws.cell(\n            8,\n            total_col,\n        ).value = _xmc1471b_value(\n            population,\n            population,\n        )\n\n        ws.cell(\n            8,\n            total_col + 1,\n        ).value = _xmc1471b_value(\n            population,\n            bc1,\n        )\n\n        ws.cell(\n            8,\n            total_col + 3,\n        ).value = _xmc1471b_value(\n            population,\n            bc2,\n        )\n\n    ws["R8"] = None\n'


def read_text(path: Path) -> str:
    if not path.exists():
        raise RuntimeError(f"Không tìm thấy: {path}")

    return path.read_text(
        encoding="utf-8-sig",
        errors="strict",
    )


def write_text(
    path: Path,
    value: str,
) -> None:
    path.write_text(
        value,
        encoding="utf-8",
    )


def function_node(
    source: str,
    name: str,
):
    tree = ast.parse(source)

    matches = [
        node
        for node in tree.body
        if isinstance(
            node,
            (
                ast.FunctionDef,
                ast.AsyncFunctionDef,
            ),
        )
        and node.name == name
    ]

    if len(matches) != 1:
        raise RuntimeError(
            f"Cần đúng 1 hàm {name}; "
            f"tìm thấy {len(matches)}."
        )

    return matches[0]


def function_span(
    source: str,
    name: str,
) -> tuple[int, int]:
    node = function_node(
        source,
        name,
    )

    lines = source.splitlines(
        keepends=True
    )

    offsets = [0]

    for line in lines:
        offsets.append(
            offsets[-1] + len(line)
        )

    return (
        offsets[int(node.lineno) - 1],
        offsets[int(node.end_lineno)],
    )


def get_function(
    source: str,
    name: str,
) -> str:
    start, end = function_span(
        source,
        name,
    )

    return source[start:end]


def replace_function(
    source: str,
    name: str,
    replacement: str,
) -> str:
    start, end = function_span(
        source,
        name,
    )

    result = (
        source[:start]
        + replacement.rstrip()
        + "\n\n"
        + source[end:].lstrip("\n")
    )

    ast.parse(result)
    return result


def indent_block(
    block: str,
    indent: str,
) -> str:
    return "\n".join(
        (indent + line) if line else ""
        for line in block.splitlines()
    )


def patch_router(
    source: str,
) -> tuple[str, list[str]]:
    notes: list[str] = []

    ast.parse(source)

    if AGE15_MARKER not in source:
        raise RuntimeError(
            "Chưa thấy Bài 4.7.1A. "
            "Hãy cài 4.7.1A trước."
        )

    if PY_START in source:
        notes.append(
            "Backend tự suy ra literacy_status đã tồn tại."
        )
        return source, notes

    start = source.find(SAVE_START)
    end = source.find(SAVE_END, start)

    if start < 0 or end < 0:
        raise RuntimeError(
            "Không tìm thấy SAVE_FIELDS XMC."
        )

    block = source[start:end]

    record_matches = re.findall(
        r"(?m)^([ \t]*)([A-Za-z_][A-Za-z0-9_]*)"
        r"\.completed_grade_[35]\s*=",
        block,
    )

    record_names = {
        name
        for _indent, name
        in record_matches
    }

    if len(record_names) != 1:
        raise RuntimeError(
            "Không xác định duy nhất biến record "
            "cho completed_grade_3/5."
        )

    record_var = next(iter(record_names))

    anchor_pattern = re.compile(
        r"(?m)^([ \t]*)"
        + re.escape(record_var)
        + r"\.completed_primary_program\s*="
    )

    anchor_match = anchor_pattern.search(
        block
    )

    if not anchor_match:
        raise RuntimeError(
            "Không tìm thấy anchor "
            "completed_primary_program."
        )

    indent = anchor_match.group(1)

    derived = DERIVE_BLOCK_TEMPLATE.replace(
        "__RECORD_VAR__",
        record_var,
    )

    insertion = (
        indent_block(
            derived,
            indent,
        )
        + "\n\n"
    )

    absolute_pos = (
        start + anchor_match.start()
    )

    source = (
        source[:absolute_pos]
        + insertion
        + source[absolute_pos:]
    )

    ast.parse(source)

    notes.append(
        "Backend ghi đè literacy_status bằng trạng thái "
        "suy ra từ lớp 3/lớp 5."
    )

    return source, notes


def patch_template(
    source: str,
) -> tuple[str, list[str]]:
    notes: list[str] = []

    if UI_START not in source:
        pattern = re.compile(
            r"""
            (?P<indent>[ \t]*)
            <div>\s*
                <label\s+for="literacy_status">\s*
                    Tình\s+trạng\s+Xóa\s+mù\s+chữ\s*
                </label>\s*
                <select
                    (?:
                        (?!</select>)
                        .
                    )*
                    id="literacy_status"
                    (?:
                        (?!</select>)
                        .
                    )*
                </select>\s*
            </div>
            """,
            re.DOTALL | re.VERBOSE,
        )

        match = pattern.search(source)

        if not match:
            raise RuntimeError(
                "Không tìm thấy đúng khối nhập tay "
                "Tình trạng Xóa mù chữ."
            )

        indent = match.group("indent")

        replacement = indent_block(
            READONLY_STATUS_BLOCK,
            indent,
        )

        source = (
            source[:match.start()]
            + replacement
            + source[match.end():]
        )

        notes.append(
            "Đã bỏ select nhập tay Tình trạng XMC."
        )

    script_start = (
        "<!-- === BAI_13B_11_15_2_4_7_1B_"
        "DERIVED_STATUS_SCRIPT_START === -->"
    )

    if script_start not in source:
        body_pos = source.lower().rfind(
            "</body>"
        )

        if body_pos < 0:
            raise RuntimeError(
                "Không tìm thấy </body>."
            )

        source = (
            source[:body_pos]
            + "\n"
            + UI_SCRIPT
            + "\n"
            + source[body_pos:]
        )

        notes.append(
            "Đã thêm trạng thái XMC tự hiển thị từ lớp 3/lớp 5."
        )

    if 'name="literacy_status"' in source:
        raise RuntimeError(
            "Template vẫn còn field literacy_status nhập tay."
        )

    return source, notes


def remove_old_report_helper(
    source: str,
) -> str:
    old_start = (
        "# === BAI_13B_11_15_2_4_7_1_"
        "XMC_DATA_SOURCE_START ==="
    )

    old_end = (
        "# === BAI_13B_11_15_2_4_7_1_"
        "XMC_DATA_SOURCE_END ==="
    )

    start = source.find(old_start)

    if start < 0:
        return source

    end = source.find(
        old_end,
        start,
    )

    if end < 0:
        raise RuntimeError(
            "Helper 4.7.1 cũ thiếu marker cuối."
        )

    end += len(old_end)

    while (
        end < len(source)
        and source[end] in "\r\n"
    ):
        end += 1

    return (
        source[:start]
        + source[end:]
    )


def patch_reports(
    source: str,
) -> tuple[str, list[str]]:
    notes: list[str] = []

    ast.parse(source)

    for name in (
        "_build_xmc3",
        "_build_cmc2",
        "_build_cmc1",
        "_build_xmc4",
        "export_additional_report",
    ):
        function_node(
            source,
            name,
        )

    export_fn = get_function(
        source,
        "export_additional_report",
    )

    if (
        FORMULA_CALL_MARKER not in export_fn
        or "apply_xmc_formula_contract("
        not in export_fn
    ):
        raise RuntimeError(
            "Chưa thấy Bài 4.7 tính tỷ lệ."
        )

    if REPORT_START in source:
        if REPORT_END not in source:
            raise RuntimeError(
                "Marker report 4.7.1B không hoàn chỉnh."
            )
        notes.append(
            "Nguồn 4 biểu XMC 4.7.1B đã tồn tại."
        )
        return source, notes

    source = remove_old_report_helper(
        source
    )

    insert_at, _ = function_span(
        source,
        "_build_xmc3",
    )

    source = (
        source[:insert_at]
        + REPORT_HELPERS
        + "\n\n"
        + source[insert_at:]
    )

    source = replace_function(
        source,
        "_build_xmc3",
        NEW_XMC3,
    )

    source = replace_function(
        source,
        "_build_cmc2",
        NEW_CMC2,
    )

    source = replace_function(
        source,
        "_build_cmc1",
        NEW_CMC1,
    )

    source = replace_function(
        source,
        "_build_xmc4",
        NEW_XMC4,
    )

    ast.parse(source)

    notes.extend(
        [
            "CMC-1: nguồn trực tiếp lớp 3/lớp 5.",
            "CMC-2: nguồn trực tiếp lớp 3/lớp 5.",
            "XMC-3: nguồn trực tiếp lớp 3/lớp 5.",
            "XMC-4: nguồn trực tiếp lớp 3/lớp 5.",
            "Không dùng literacy_status làm nguồn đếm.",
        ]
    )

    return source, notes


def derive_status(
    g3,
    g5,
) -> str:
    if g3 == 0 or g5 == 0:
        return "THEO_DOI_XMC"

    if g3 == 1 and g5 == 1:
        return "KHONG_THUOC_DIEN"

    return "CHUA_XAC_DINH"


def parse_year(
    code,
    start_date,
) -> int | None:
    found = re.findall(
        r"\d{4}",
        str(code or ""),
    )

    if found:
        return int(found[0])

    found = re.findall(
        r"\d{4}",
        str(start_date or ""),
    )

    return int(found[0]) if found else None


def parse_birth_year(
    value,
) -> int | None:
    text = str(value or "").strip()

    if not text:
        return None

    if len(text) >= 4 and text[:4].isdigit():
        return int(text[:4])

    found = re.findall(
        r"\d{4}",
        text,
    )

    return int(found[-1]) if found else None


def normalize_database() -> dict:
    conn = sqlite3.connect(str(DB))
    conn.row_factory = sqlite3.Row

    try:
        year_cols = {
            row[1]
            for row in conn.execute(
                "PRAGMA table_info(school_years)"
            ).fetchall()
        }

        start_expr = (
            "sy.start_date"
            if "start_date" in year_cols
            else "NULL"
        )

        rows = conn.execute(
            f"""
            SELECT
                spr.id AS record_id,
                spr.is_literacy_target,
                spr.literacy_status,
                spr.completed_grade_3,
                spr.completed_grade_5,
                sp.date_of_birth,
                sy.code AS year_code,
                {start_expr} AS start_date
            FROM survey_person_year_records AS spr
            JOIN survey_people AS sp
              ON sp.id = spr.survey_person_id
            JOIN school_years AS sy
              ON sy.id = spr.school_year_id
            """
        ).fetchall()

        eligible = 0
        target_changed = 0
        status_changed = 0
        updates = []

        for row in rows:
            reference_year = parse_year(
                row["year_code"],
                row["start_date"],
            )

            birth_year = parse_birth_year(
                row["date_of_birth"]
            )

            if (
                reference_year is None
                or birth_year is None
            ):
                continue

            if reference_year - birth_year < 15:
                continue

            eligible += 1

            desired_target = 1
            desired_status = derive_status(
                row["completed_grade_3"],
                row["completed_grade_5"],
            )

            if (
                row["is_literacy_target"]
                != desired_target
            ):
                target_changed += 1

            current_status = str(
                row["literacy_status"]
                or "CHUA_XAC_DINH"
            )

            if current_status != desired_status:
                status_changed += 1

            updates.append(
                (
                    desired_target,
                    desired_status,
                    int(row["record_id"]),
                )
            )

        if updates:
            conn.executemany(
                """
                UPDATE survey_person_year_records
                SET
                    is_literacy_target = ?,
                    literacy_status = ?
                WHERE id = ?
                """,
                updates,
            )

        conn.commit()

        return {
            "eligible": eligible,
            "target_changed": target_changed,
            "status_changed": status_changed,
            "updated_rows": len(updates),
        }

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


def db_state() -> dict:
    conn = sqlite3.connect(str(DB))

    try:
        return {
            "integrity": str(
                conn.execute(
                    "PRAGMA integrity_check"
                ).fetchone()[0]
            ),
            "fk_count": len(
                conn.execute(
                    "PRAGMA foreign_key_check"
                ).fetchall()
            ),
            "record_count": int(
                conn.execute(
                    "SELECT COUNT(*) "
                    "FROM survey_person_year_records"
                ).fetchone()[0]
            ),
            "grade3_true": int(
                conn.execute(
                    "SELECT COUNT(*) "
                    "FROM survey_person_year_records "
                    "WHERE completed_grade_3 = 1"
                ).fetchone()[0]
            ),
            "grade3_false": int(
                conn.execute(
                    "SELECT COUNT(*) "
                    "FROM survey_person_year_records "
                    "WHERE completed_grade_3 = 0"
                ).fetchone()[0]
            ),
            "grade5_true": int(
                conn.execute(
                    "SELECT COUNT(*) "
                    "FROM survey_person_year_records "
                    "WHERE completed_grade_5 = 1"
                ).fetchone()[0]
            ),
            "grade5_false": int(
                conn.execute(
                    "SELECT COUNT(*) "
                    "FROM survey_person_year_records "
                    "WHERE completed_grade_5 = 0"
                ).fetchone()[0]
            ),
        }

    finally:
        conn.close()


def backup_database() -> None:
    src = sqlite3.connect(str(DB))
    dst = sqlite3.connect(str(BACKUP / DB.name))

    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()


def restore_database() -> None:
    backup = BACKUP / DB.name

    if not backup.exists():
        return

    src = sqlite3.connect(str(backup))
    dst = sqlite3.connect(str(DB))

    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()


def verify_router(
    source: str,
) -> None:
    ast.parse(source)

    for token in (
        AGE15_MARKER,
        PY_START,
        PY_END,
        ".completed_grade_3",
        ".completed_grade_5",
        '.literacy_status = "THEO_DOI_XMC"',
        '.literacy_status = "KHONG_THUOC_DIEN"',
        '.literacy_status = "CHUA_XAC_DINH"',
    ):
        if token not in source:
            raise RuntimeError(
                "Verifier router thiếu: "
                + token
            )


def verify_template(
    source: str,
) -> None:
    for token in (
        UI_START,
        UI_END,
        "b1471b_literacy_status_text",
        "deriveXmcStatusText",
        "completed_grade_3",
        "completed_grade_5",
        "Không nhập tay",
    ):
        if token not in source:
            raise RuntimeError(
                "Verifier template thiếu: "
                + token
            )

    if 'name="literacy_status"' in source:
        raise RuntimeError(
            "Template vẫn còn literacy_status nhập tay."
        )

    block = source[
        source.find(UI_START):
        source.find(UI_END) + len(UI_END)
    ]

    if "MutationObserver" in block:
        raise RuntimeError(
            "Không cho phép MutationObserver."
        )

    from jinja2 import Environment

    Environment().parse(source)


def verify_reports(
    source: str,
) -> None:
    ast.parse(source)

    for token in (
        REPORT_START,
        REPORT_END,
        "def _xmc1471b_metrics(",
        '"completed_grade_3"',
        '"completed_grade_5"',
        '"mc1_total"',
        '"mc2_total"',
        '"bc1_total"',
        '"bc2_total"',
        "def _build_xmc3(",
        "def _build_cmc2(",
        "def _build_cmc1(",
        "def _build_xmc4(",
    ):
        if token not in source:
            raise RuntimeError(
                "Verifier report thiếu: "
                + token
            )

    export_fn = get_function(
        source,
        "export_additional_report",
    )

    if "apply_xmc_formula_contract(" not in export_fn:
        raise RuntimeError(
            "Mất lời gọi bộ tính tỷ lệ 4.7."
        )

    if (
        export_fn.find(
            "apply_xmc_formula_contract("
        )
        >= export_fn.find(
            "workbook.save(output)"
        )
    ):
        raise RuntimeError(
            "Bộ tính tỷ lệ 4.7 phải chạy trước save."
        )


def verify_formula_service() -> None:
    text = read_text(
        FORMULA_SERVICE
    )

    ast.parse(text)

    for token in (
        "CMC1_PERCENT_FORMULAS",
        "XMC3_PERCENT_FORMULAS",
        "XMC4_PERCENT_FORMULAS",
        "def apply_xmc_formula_contract(",
    ):
        if token not in text:
            raise RuntimeError(
                "Service 4.7 thiếu: "
                + token
            )


def clear_cache() -> None:
    for cache in APP.rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(
                cache,
                ignore_errors=True,
            )


def main() -> None:
    print("=" * 152)
    print(
        "BÀI 13B-11.15.2.4.7.1B - "
        "BỎ NHẬP TAY TÌNH TRẠNG XMC + "
        "TỰ SUY RA + CHUẨN HÓA 4 BIỂU XMC"
    )
    print("=" * 152)
    print()

    print("NGHIỆP VỤ:")
    print(" - >=15 tuổi: thuộc diện ĐIỀU TRA XMC = Có.")
    print(" - Tình trạng XMC: KHÔNG nhập tay.")
    print(" - Lớp 3 = Không -> Mù chữ mức độ 1.")
    print(" - Lớp 3 = Có, lớp 5 = Không -> Biết chữ mức độ 1.")
    print(" - Lớp 3 = Có, lớp 5 = Có -> Biết chữ mức độ 2.")
    print(" - None -> chưa đủ dữ liệu, không tự coi là mù chữ.")
    print()

    print("BÁO CÁO:")
    print(
        " - CMC-1 / CMC-2 / XMC-3 / XMC-4 "
        "lấy trực tiếp completed_grade_3/5."
    )
    print(" - Không dùng literacy_status làm nguồn đếm.")
    print(" - 79 công thức tỷ lệ Bài 4.7 giữ nguyên.")
    print()

    for path in (
        ROUTER,
        TEMPLATE,
        BUILDERS,
        FORMULA_SERVICE,
        DB,
    ):
        if not path.exists():
            raise RuntimeError(
                f"Không tìm thấy: {path}"
            )

    verify_formula_service()

    old_router = read_text(ROUTER)
    old_template = read_text(TEMPLATE)
    old_builders = read_text(BUILDERS)

    ast.parse(old_router)
    ast.parse(old_builders)

    new_router, router_notes = patch_router(
        old_router
    )

    new_template, template_notes = patch_template(
        old_template
    )

    new_builders, report_notes = patch_reports(
        old_builders
    )

    verify_router(new_router)
    verify_template(new_template)
    verify_reports(new_builders)

    before_db = db_state()

    if before_db["integrity"] != "ok":
        raise RuntimeError(
            "Database integrity_check != ok trước cài."
        )

    if before_db["fk_count"] != 0:
        raise RuntimeError(
            "Database có lỗi foreign key trước cài."
        )

    EXPORTS.mkdir(
        parents=True,
        exist_ok=True,
    )

    BACKUP.mkdir(
        parents=True,
        exist_ok=False,
    )

    for path in (
        ROUTER,
        TEMPLATE,
        BUILDERS,
        FORMULA_SERVICE,
    ):
        shutil.copy2(
            path,
            BACKUP / path.name,
        )

    backup_database()

    try:
        if new_router != old_router:
            write_text(
                ROUTER,
                new_router,
            )

        if new_template != old_template:
            write_text(
                TEMPLATE,
                new_template,
            )

        if new_builders != old_builders:
            write_text(
                BUILDERS,
                new_builders,
            )

        normalization = normalize_database()

        for path in (
            ROUTER,
            BUILDERS,
            FORMULA_SERVICE,
        ):
            py_compile.compile(
                str(path),
                doraise=True,
            )

        verify_router(
            read_text(ROUTER)
        )

        verify_template(
            read_text(TEMPLATE)
        )

        verify_reports(
            read_text(BUILDERS)
        )

        verify_formula_service()

        after_db = db_state()

        if after_db["integrity"] != "ok":
            raise RuntimeError(
                "Database integrity_check != ok sau cài."
            )

        if after_db["fk_count"] != 0:
            raise RuntimeError(
                "Database có lỗi foreign key sau cài."
            )

        if (
            after_db["record_count"]
            != before_db["record_count"]
        ):
            raise RuntimeError(
                "Số year-record thay đổi ngoài dự kiến."
            )

        for key in (
            "grade3_true",
            "grade3_false",
            "grade5_true",
            "grade5_false",
        ):
            if after_db[key] != before_db[key]:
                raise RuntimeError(
                    "completed_grade_3/5 thay đổi ngoài dự kiến: "
                    + key
                )

        clear_cache()

    except Exception:
        print()
        print(
            "CÓ LỖI - ĐANG ROLLBACK SOURCE + DATABASE..."
        )

        for path in (
            ROUTER,
            TEMPLATE,
            BUILDERS,
        ):
            backup = BACKUP / path.name

            if backup.exists():
                shutil.copy2(
                    backup,
                    path,
                )

        restore_database()
        clear_cache()
        raise

    notes = (
        router_notes
        + template_notes
        + report_notes
    )

    lines = [
        "=" * 152,
        "BÀI 13B-11.15.2.4.7.1B - KẾT QUẢ",
        "=" * 152,
        "",
        "QUY TẮC:",
        " - >=15 tuổi: is_literacy_target=True.",
        " - literacy_status không nhập tay.",
        " - completed_grade_3=False -> MC mức 1.",
        " - completed_grade_3=True -> biết chữ mức 1.",
        " - completed_grade_5=False -> MC/chưa đạt mức 2 theo biểu.",
        " - completed_grade_5=True -> biết chữ mức 2.",
        " - None không tự phân loại.",
        "",
        "TƯƠNG THÍCH literacy_status:",
        " - Có False lớp 3/5 -> THEO_DOI_XMC.",
        " - Cả lớp 3 và lớp 5 True -> KHONG_THUOC_DIEN "
        "(không thuộc diện THEO DÕI, vẫn thuộc diện ĐIỀU TRA).",
        " - Còn thiếu -> CHUA_XAC_DINH.",
        "",
        "4 BIỂU:",
        " - CMC-1: grade3/grade5.",
        " - CMC-2: grade3/grade5.",
        " - XMC-3: grade3/grade5.",
        " - XMC-4: grade3/grade5.",
        " - 79 công thức tỷ lệ Bài 4.7 giữ nguyên.",
        "",
        "CHUẨN HÓA DB:",
        repr(normalization),
        "",
        "DB TRƯỚC:",
        repr(before_db),
        "",
        "DB SAU:",
        repr(after_db),
        "",
        "GHI CHÚ:",
    ]

    for note in notes:
        lines.append(
            " - " + note
        )

    lines.extend(
        [
            "",
            "AN TOÀN:",
            " - Không ALTER TABLE.",
            " - Không sửa completed_grade_3/5.",
            " - Không tạo/xóa year-record.",
            " - Không đổi menu/route.",
            " - Không MutationObserver.",
            f" - Backup: {BACKUP}",
            "",
        ]
    )

    REPORT.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )

    print("KIỂM TRA:")
    print(" - AST/py_compile: OK")
    print(" - Jinja parse: OK")
    print(" - Không còn literacy_status nhập tay: OK")
    print(" - Backend tự suy ra literacy_status: OK")
    print(" - 4 builder XMC dùng grade3/grade5: OK")
    print(" - Bộ tính 4.7 vẫn trước save: OK")
    print(" - integrity_check: OK")
    print(" - foreign_key_check: 0")
    print(" - completed_grade_3/5 không thay đổi: OK")
    print(" - Không tạo/xóa year-record: OK")
    print()
    print(
        "Chuẩn hóa DB:",
        normalization,
    )
    print(
        "Backup:",
        BACKUP,
    )
    print(
        "Báo cáo:",
        REPORT,
    )
    print()
    print("=" * 152)
    print(
        "BÀI 13B-11.15.2.4.7.1B THÀNH CÔNG"
    )
    print("=" * 152)


if __name__ == "__main__":
    main()
