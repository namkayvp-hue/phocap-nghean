from __future__ import annotations

import ast
import os
import py_compile
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path


PROJECT = Path(
    os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")
).resolve()

APP = PROJECT / "app"
EXPORTS = PROJECT / "exports"
DB = PROJECT / "data" / "phocap.db"

BUILDERS = APP / "pcgd_xmc_report_builders_v1.py"
RULES = APP / "services" / "pcgd_business_rules.py"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

BACKUP_DIR = (
    EXPORTS
    / f"backup_bai_13b_11_15_2_4_5_1_{STAMP}"
)

REPORT_FILE = (
    EXPORTS
    / f"bao_cao_bai_13b_11_15_2_4_5_1_{STAMP}.txt"
)

MARKER = (
    "# === BAI_13B_11_15_2_4_5_1_"
    "DISABLED_CAPABLE_AND_M2_CLEANUP ==="
)

HELPERS = r"""
# === BAI_13B_11_15_2_4_5_1_DISABLED_CAPABLE_AND_M2_CLEANUP ===
def _b152451_disabled_can_learn(
    person: SurveyPerson,
    record: SurveyPersonYearRecord | None,
) -> bool:
    # Không suy diễn từ loại/mức độ khuyết tật.
    # Chỉ tính khi field năm học đã xác nhận True.
    return bool(
        _is_disabled(person, record)
        and record is not None
        and getattr(
            record,
            "disability_can_learn",
            None,
        )
        is True
    )


def _b152451_disabled_access(
    person: SurveyPerson,
    record: SurveyPersonYearRecord | None,
) -> bool:
    # Tử số tiếp cận GD chỉ thuộc nhóm có khả năng học tập.
    return bool(
        _b152451_disabled_can_learn(
            person,
            record,
        )
        and record is not None
        and getattr(
            record,
            "disability_access_education",
            None,
        )
        is True
    )


def _b152451_plain_number(
    value: float | int | None,
) -> str:
    if value is None:
        return ""

    number = float(value)

    if number.is_integer():
        return str(
            int(number)
        )

    return (
        f"{number:.2f}"
        .rstrip("0")
        .rstrip(".")
    )


def _b152451_looks_like_sample_ratio(
    value: object,
) -> bool:
    if not isinstance(
        value,
        str,
    ):
        return False

    text = value.strip()

    if text.count("/") != 1:
        return False

    left, right = (
        part.strip()
        for part in text.split(
            "/",
            1,
        )
    )

    def is_number(
        item: str,
    ) -> bool:
        compact = (
            item.replace(
                ".",
                "",
            )
            .replace(
                ",",
                "",
            )
            .replace(
                " ",
                "",
            )
        )

        return bool(
            compact
            and compact.isdigit()
        )

    return (
        is_number(left)
        and is_number(right)
    )


def _b152451_ratio_text(
    ws: Any,
    numerator_refs: tuple[str, ...],
    denominator_refs: tuple[str, ...],
) -> str:
    numerator = _b15245_ws_sum(
        ws,
        numerator_refs,
    )

    denominator = _b15245_ws_sum(
        ws,
        denominator_refs,
    )

    if (
        numerator is None
        or denominator is None
    ):
        return ""

    return (
        _b152451_plain_number(
            numerator
        )
        + "/"
        + _b152451_plain_number(
            denominator
        )
    )


def _b152451_clean_thcs_m2_evaluation(
    ws: Any,
) -> None:
    # K20:K24 lấy tỷ lệ thực tế từ dòng Tổng 15.
    result_map = {
        20: "E15",
        21: "M15",
        22: "J15",
        23: "Q15",
        24: "V15",
    }

    # Tỉ số thực tế tương ứng 5 tiêu chí.
    ratio_map = {
        20: (
            ("D15",),
            ("C15",),
        ),
        21: (
            ("L15",),
            ("K15",),
        ),
        22: (
            ("I15",),
            ("F15",),
        ),
        23: (
            ("P15", "O15"),
            ("N15",),
        ),
        24: (
            ("U15",),
            ("R15",),
        ),
    }

    for row, source_ref in result_map.items():
        ws[f"K{row}"] = _b15245_ws_number(
            ws,
            source_ref,
        )

    for row, (
        numerator_refs,
        denominator_refs,
    ) in ratio_map.items():
        actual_ratio = _b152451_ratio_text(
            ws,
            numerator_refs,
            denominator_refs,
        )

        # Chỉ thay chuỗi minh họa dạng số/số trong đúng dòng 20-24.
        for column in range(
            1,
            ws.max_column + 1,
        ):
            cell = ws.cell(
                row,
                column,
            )

            if _b152451_looks_like_sample_ratio(
                cell.value
            ):
                cell.value = (
                    actual_ratio
                    or None
                )
                break

    # Bỏ ghi chú đỏ "Số liệu trong bảng là số liệu làm mẫu"
    # dù mẫu có dịch chuyển ô.
    for row_cells in ws.iter_rows():
        for cell in row_cells:
            if not isinstance(
                cell.value,
                str,
            ):
                continue

            normalized = _norm(
                cell.value
            )

            if (
                "SO LIEU TRONG BANG"
                in normalized
                and "LAM MAU"
                in normalized
            ):
                cell.value = None
# === END BAI_13B_11_15_2_4_5_1_DISABLED_CAPABLE_AND_M2_CLEANUP ===


"""


def _read_text(
    path: Path,
) -> str:
    return path.read_text(
        encoding="utf-8-sig"
    )


def _function_span(
    text: str,
    function_name: str,
) -> tuple[int, int]:
    tree = ast.parse(
        text
    )

    candidates = [
        node
        for node in tree.body
        if isinstance(
            node,
            (
                ast.FunctionDef,
                ast.AsyncFunctionDef,
            ),
        )
        and node.name == function_name
    ]

    if len(candidates) != 1:
        raise RuntimeError(
            f"Cần đúng 1 function {function_name}; "
            f"tìm thấy {len(candidates)}."
        )

    node = candidates[0]
    lines = text.splitlines(
        keepends=True
    )

    start = sum(
        len(line)
        for line in lines[
            : node.lineno - 1
        ]
    )

    end_lineno = int(
        node.end_lineno
        or node.lineno
    )

    end = sum(
        len(line)
        for line in lines[
            :end_lineno
        ]
    )

    return (
        start,
        end,
    )


def _get_function(
    text: str,
    function_name: str,
) -> str:
    start, end = _function_span(
        text,
        function_name,
    )

    return text[
        start:end
    ]


def _replace_function(
    text: str,
    function_name: str,
    new_block: str,
) -> str:
    start, end = _function_span(
        text,
        function_name,
    )

    return (
        text[:start]
        + new_block.rstrip()
        + "\n\n"
        + text[end:]
    )


def _replace_exact_once(
    text: str,
    old: str,
    new: str,
    description: str,
) -> str:
    count = text.count(
        old
    )

    if count != 1:
        raise RuntimeError(
            f"{description}: cần đúng 1 vị trí, "
            f"nhưng tìm thấy {count}."
        )

    return text.replace(
        old,
        new,
        1,
    )


def _patch_th02(
    block: str,
) -> str:
    if (
        "disabled_capable"
        in block
        and "_b152451_disabled_can_learn"
        in block
    ):
        return block

    old_disabled = (
        "    disabled = sum(1 for p, r in people "
        "if 6 <= (_age(p, year) or -1) <= 14 "
        "and _is_disabled(p, r))\n"
    )

    new_disabled = (
        old_disabled
        + "    disabled_capable = sum(\n"
        + "        1\n"
        + "        for p, r in people\n"
        + "        if 6 <= (_age(p, year) or -1) <= 14\n"
        + "        and _b152451_disabled_can_learn(p, r)\n"
        + "    )\n"
    )

    block = _replace_exact_once(
        block,
        old_disabled,
        new_disabled,
        "TH_02 thêm số KT có khả năng học",
    )

    old_access = (
        "    disabled_access = sum(1 for p, r in people "
        "if 6 <= (_age(p, year) or -1) <= 14 "
        "and _disabled_access(p, r))\n"
    )

    new_access = (
        "    disabled_access = sum(\n"
        "        1\n"
        "        for p, r in people\n"
        "        if 6 <= (_age(p, year) or -1) <= 14\n"
        "        and _b152451_disabled_access(p, r)\n"
        "    )\n"
    )

    block = _replace_exact_once(
        block,
        old_access,
        new_access,
        "TH_02 dùng tiếp cận GD trong nhóm có khả năng học",
    )

    old_values = (
        "14: disabled, 16: disabled_access, "
        "17: _percent(disabled_access, disabled)"
    )

    new_values = (
        "14: disabled, 15: disabled_capable, "
        "16: disabled_access, "
        "17: _percent(disabled_access, disabled_capable)"
    )

    block = _replace_exact_once(
        block,
        old_values,
        new_values,
        "TH_02 nối cột 15 và mẫu số tỷ lệ",
    )

    return block


def _patch_thcs_m1(
    block: str,
) -> str:
    if (
        "_b152451_disabled_can_learn(p, r)"
        in block
        and "_percent(access, capable)"
        in block
    ):
        return block

    row9 = (
        "        ws.cell(9, col).value = "
        "sum(1 for p, r in group if _is_disabled(p, r)) or None\n"
    )

    row9_new = (
        row9
        + "        ws.cell(10, col).value = sum(\n"
        + "            1\n"
        + "            for p, r in group\n"
        + "            if _b152451_disabled_can_learn(p, r)\n"
        + "        ) or None\n"
    )

    block = _replace_exact_once(
        block,
        row9,
        row9_new,
        "THCS_M1 thêm dòng Có khả năng HT",
    )

    row11_old = (
        "        ws.cell(11, col).value = "
        "sum(1 for p, r in group if _disabled_access(p, r)) or None\n"
    )

    row11_new = (
        "        ws.cell(11, col).value = sum(\n"
        "            1\n"
        "            for p, r in group\n"
        "            if _b152451_disabled_access(p, r)\n"
        "        ) or None\n"
    )

    block = _replace_exact_once(
        block,
        row11_old,
        row11_new,
        "THCS_M1 dùng đúng tử số tiếp cận GD",
    )

    disabled_old = (
        "    disabled = sum(1 for p,r in age15_18 "
        "if _is_disabled(p,r))\n"
    )

    disabled_new = (
        disabled_old
        + "    capable = sum(\n"
        + "        1 for p,r in age15_18\n"
        + "        if _b152451_disabled_can_learn(p,r)\n"
        + "    )\n"
    )

    block = _replace_exact_once(
        block,
        disabled_old,
        disabled_new,
        "THCS_M1 thêm tổng có khả năng học",
    )

    access_old = (
        "    access = sum(1 for p,r in age15_18 "
        "if _disabled_access(p,r))\n"
    )

    access_new = (
        "    access = sum(\n"
        "        1 for p,r in age15_18\n"
        "        if _b152451_disabled_access(p,r)\n"
        "    )\n"
    )

    block = _replace_exact_once(
        block,
        access_old,
        access_new,
        "THCS_M1 dùng access theo can-learn",
    )

    rate_old = (
        '    ws["G41"] = access; '
        'ws["H41"] = _percent(access, disabled)\n'
    )

    rate_new = (
        '    ws["G41"] = access; '
        'ws["H41"] = _percent(access, capable)\n'
    )

    block = _replace_exact_once(
        block,
        rate_old,
        rate_new,
        "THCS_M1 đổi mẫu số H41",
    )

    return block


def _patch_thcs_tk(
    block: str,
) -> str:
    if (
        "capable=[pr for pr in disabled"
        in block
        and "13:len(capable)"
        in block
    ):
        return block

    disabled_old = (
        "    disabled=[pr for pr in age1118 "
        "if _is_disabled(*pr)]\n"
    )

    disabled_new = (
        disabled_old
        + "    capable=[\n"
        + "        pr for pr in disabled\n"
        + "        if _b152451_disabled_can_learn(*pr)\n"
        + "    ]\n"
    )

    block = _replace_exact_once(
        block,
        disabled_old,
        disabled_new,
        "THCS_TK thêm danh sách có khả năng học",
    )

    access_old = (
        "    access=sum(1 for p,r in disabled "
        "if _disabled_access(p,r))\n"
    )

    access_new = (
        "    access=sum(\n"
        "        1 for p,r in capable\n"
        "        if _b152451_disabled_access(p,r)\n"
        "    )\n"
    )

    block = _replace_exact_once(
        block,
        access_old,
        access_new,
        "THCS_TK dùng access theo can-learn",
    )

    values_old = (
        "12:len(disabled),14:access,"
        "15:_percent(access,len(disabled))"
    )

    values_new = (
        "12:len(disabled),13:len(capable),"
        "14:access,15:_percent(access,len(capable))"
    )

    block = _replace_exact_once(
        block,
        values_old,
        values_new,
        "THCS_TK nối cột 13 và mẫu số tỷ lệ",
    )

    return block


def _patch_postprocessor(
    block: str,
) -> str:
    if (
        "_b152451_clean_thcs_m2_evaluation(ws)"
        in block
    ):
        return block

    anchor = (
        '            ws[f"V{row}"] = '
        '_b15245_percent_from_cells('
        'ws, (f"U{row}",), (f"R{row}",))\n'
        '        return\n'
    )

    replacement = (
        '            ws[f"V{row}"] = '
        '_b15245_percent_from_cells('
        'ws, (f"U{row}",), (f"R{row}",))\n'
        '        _b152451_clean_thcs_m2_evaluation(ws)\n'
        '        return\n'
    )

    return _replace_exact_once(
        block,
        anchor,
        replacement,
        "THCS_M2 nối dọn bảng đánh giá",
    )


def _patch_builders(
    text: str,
) -> tuple[str, list[str]]:
    notes: list[str] = []

    if MARKER not in text:
        anchor = "def _build_th02("

        if text.count(
            anchor
        ) != 1:
            raise RuntimeError(
                "Không tìm thấy đúng 1 "
                "def _build_th02("
            )

        text = text.replace(
            anchor,
            HELPERS + anchor,
            1,
        )

        notes.append(
            "Đã thêm helper dùng "
            "disability_can_learn / "
            "disability_access_education."
        )
    else:
        notes.append(
            "Helper 15.2.4.5.1 đã tồn tại."
        )

    for function_name, patcher, note in (
        (
            "_build_th02",
            _patch_th02,
            "Đã nối Có khả năng HT cho TH_02.",
        ),
        (
            "_build_thcs_m1",
            _patch_thcs_m1,
            "Đã nối dòng 10 và sửa tỷ lệ KT THCS_M1.",
        ),
        (
            "_build_thcs_tk",
            _patch_thcs_tk,
            "Đã nối cột 13 và sửa tỷ lệ KT THCS_TK.",
        ),
        (
            "_b15245_apply_official_th_thcs_calculations",
            _patch_postprocessor,
            "Đã nối dọn dữ liệu mẫu THCS_M2.",
        ),
    ):
        block = _get_function(
            text,
            function_name,
        )

        new_block = patcher(
            block
        )

        text = _replace_function(
            text,
            function_name,
            new_block,
        )

        notes.append(
            note
        )

    return (
        text,
        notes,
    )


def _db_state() -> dict:
    if not DB.exists():
        return {
            "exists": False,
        }

    conn = sqlite3.connect(
        str(DB)
    )

    try:
        integrity = conn.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]

        fk_count = len(
            conn.execute(
                "PRAGMA foreign_key_check"
            ).fetchall()
        )

        columns = [
            str(row[1])
            for row in conn.execute(
                'PRAGMA table_info('
                '"survey_person_year_records"'
                ')'
            ).fetchall()
        ]

        row_count = int(
            conn.execute(
                "SELECT COUNT(*) "
                "FROM survey_person_year_records"
            ).fetchone()[0]
        )

        return {
            "exists": True,
            "integrity": integrity,
            "fk_count": fk_count,
            "survey_person_year_records_columns": columns,
            "survey_person_year_records_count": row_count,
        }

    finally:
        conn.close()


def _backup_db() -> None:
    if not DB.exists():
        return

    source = sqlite3.connect(
        str(DB)
    )

    target = sqlite3.connect(
        str(
            BACKUP_DIR
            / "phocap.db"
        )
    )

    try:
        source.backup(
            target
        )
    finally:
        target.close()
        source.close()


def _restore() -> None:
    source_backup = (
        BACKUP_DIR
        / "pcgd_xmc_report_builders_v1.py"
    )

    if source_backup.exists():
        shutil.copy2(
            source_backup,
            BUILDERS,
        )

    db_backup = (
        BACKUP_DIR
        / "phocap.db"
    )

    if db_backup.exists():
        shutil.copy2(
            db_backup,
            DB,
        )


def _clear_cache() -> None:
    for cache in APP.rglob(
        "__pycache__"
    ):
        if cache.is_dir():
            shutil.rmtree(
                cache,
                ignore_errors=True,
            )


def main() -> None:
    print(
        "=" * 140
    )
    print(
        "BÀI 13B-11.15.2.4.5.1 - "
        "HOÀN THIỆN KHUYẾT TẬT "
        "+ DỌN MẪU THCS_M2"
    )
    print(
        "=" * 140
    )
    print()
    print("SẼ LÀM:")
    print(
        " - Dùng 2 field ĐÃ CÓ: "
        "disability_can_learn và "
        "disability_access_education."
    )
    print(
        " - TH_02: điền Có khả năng HT, "
        "Tiếp cận GD và tỷ lệ đúng mẫu."
    )
    print(
        " - THCS_M1: điền dòng Có khả năng HT; "
        "tỷ lệ = tiếp cận / có khả năng HT."
    )
    print(
        " - THCS_TK: điền cột Có khả năng HT; "
        "tỷ lệ = tiếp cận / có khả năng HT."
    )
    print(
        " - THCS_M2: thay tỉ số minh họa bằng "
        "số thực tế, điền K20:K24, "
        "xóa ghi chú số liệu làm mẫu."
    )
    print()
    print("KHÔNG LÀM:")
    print(
        " - Không ALTER TABLE."
    )
    print(
        " - Không sửa dữ liệu DB."
    )
    print(
        " - Không sửa menu / route / template."
    )
    print(
        " - Chưa tự kết luận Đạt/Không đạt."
    )
    print(
        " - TH_M1 dùng builder riêng; "
        "không sửa mạo hiểm trong bài này."
    )
    print()

    for required in (
        BUILDERS,
        RULES,
    ):
        if not required.exists():
            raise SystemExit(
                f"Không tìm thấy: {required}"
            )

    before = _db_state()

    if before.get(
        "exists"
    ):
        if (
            before.get(
                "integrity"
            )
            != "ok"
        ):
            raise SystemExit(
                "Database integrity_check "
                "không phải ok."
            )

        if (
            before.get(
                "fk_count"
            )
            != 0
        ):
            raise SystemExit(
                "Database có lỗi foreign key."
            )

        columns = set(
            before[
                "survey_person_year_records_columns"
            ]
        )

        required_columns = {
            "disability_can_learn",
            "disability_access_education",
        }

        missing = sorted(
            required_columns
            - columns
        )

        if missing:
            raise SystemExit(
                "DỪNG AN TOÀN: DB thiếu field đã "
                "được kỳ vọng từ bài trước: "
                + ", ".join(
                    missing
                )
            )

    rules_text = _read_text(
        RULES
    )

    if (
        "def safe_percent("
        not in rules_text
    ):
        raise SystemExit(
            "Thiếu safe_percent trong "
            "pcgd_business_rules.py."
        )

    old_text = _read_text(
        BUILDERS
    )

    ast.parse(
        old_text
    )

    if (
        "BAI_13B_11_15_2_4_5_"
        "TH_THCS_OFFICIAL_CALCULATIONS"
        not in old_text
    ):
        raise SystemExit(
            "Chưa thấy nền Bài 15.2.4.5. "
            "Dừng để tránh sửa nhầm phiên bản."
        )

    new_text, notes = _patch_builders(
        old_text
    )

    ast.parse(
        new_text
    )

    required_tokens = (
        MARKER,
        "def _b152451_disabled_can_learn(",
        "def _b152451_disabled_access(",
        "disabled_capable",
        "_percent(disabled_access, disabled_capable)",
        "ws.cell(10, col).value",
        '_percent(access, capable)',
        "13:len(capable)",
        "_b152451_clean_thcs_m2_evaluation(ws)",
        '20: "E15"',
        '21: "M15"',
        '22: "J15"',
        '23: "Q15"',
        '24: "V15"',
    )

    for token in required_tokens:
        if token not in new_text:
            raise RuntimeError(
                "Verifier source thiếu: "
                + token
            )

    BACKUP_DIR.mkdir(
        parents=True,
        exist_ok=False,
    )

    shutil.copy2(
        BUILDERS,
        BACKUP_DIR
        / "pcgd_xmc_report_builders_v1.py",
    )

    _backup_db()

    try:
        if new_text != old_text:
            BUILDERS.write_text(
                new_text,
                encoding="utf-8",
            )

        py_compile.compile(
            str(
                BUILDERS
            ),
            doraise=True,
        )

        ast.parse(
            _read_text(
                BUILDERS
            )
        )

        after = _db_state()

        if before != after:
            raise RuntimeError(
                "Database/schema/count thay đổi "
                "ngoài dự kiến."
            )

        _clear_cache()

    except Exception:
        _restore()
        _clear_cache()
        raise

    report = []

    report.append(
        "=" * 140
        + "\n"
    )

    report.append(
        "BÀI 13B-11.15.2.4.5.1 "
        "- BÁO CÁO CÀI ĐẶT\n"
    )

    report.append(
        "=" * 140
        + "\n\n"
    )

    report.append(
        "XÁC NHẬN NGUỒN DB:\n"
    )

    report.append(
        " - disability_can_learn: ĐÃ CÓ\n"
    )

    report.append(
        " - disability_access_education: ĐÃ CÓ\n"
    )

    report.append(
        " - Không thêm cột DB mới.\n\n"
    )

    report.append(
        "SOURCE:\n"
    )

    for note in notes:
        report.append(
            f" - {note}\n"
        )

    report.append(
        "\nNGHIỆP VỤ KHUYẾT TẬT:\n"
    )

    report.append(
        " - Tổng KT: giữ nguyên tổng số khuyết tật.\n"
    )

    report.append(
        " - Có khả năng HT: "
        "disability_can_learn is True.\n"
    )

    report.append(
        " - Tiếp cận GD: chỉ tính khi "
        "có khả năng HT và "
        "disability_access_education is True.\n"
    )

    report.append(
        " - Tỷ lệ = Tiếp cận GD / "
        "Có khả năng HT * 100.\n"
    )

    report.append(
        " - Mẫu số 0/chưa có -> để trống.\n\n"
    )

    report.append(
        "THCS_M2:\n"
    )

    report.append(
        " - K20 = E15\n"
    )

    report.append(
        " - K21 = M15\n"
    )

    report.append(
        " - K22 = J15\n"
    )

    report.append(
        " - K23 = Q15\n"
    )

    report.append(
        " - K24 = V15\n"
    )

    report.append(
        " - Tỉ số minh họa đỏ được thay bằng "
        "tử/mẫu thực tế.\n"
    )

    report.append(
        " - Ghi chú 'số liệu ... làm mẫu' được xóa.\n\n"
    )

    report.append(
        "AN TOÀN:\n"
    )

    report.append(
        " - Database không thay đổi.\n"
    )

    report.append(
        " - Không sửa menu/route/template.\n"
    )

    report.append(
        " - Không tự kết luận Đạt/Không đạt.\n"
    )

    report.append(
        " - TH_M1 chưa sửa trong bài này để "
        "không suy đoán builder riêng.\n"
    )

    report.append(
        f" - Backup: {BACKUP_DIR}\n"
    )

    REPORT_FILE.write_text(
        "".join(
            report
        ),
        encoding="utf-8",
    )

    print(
        "CÀI ĐẶT THÀNH CÔNG."
    )

    print(
        f"Backup: {BACKUP_DIR}"
    )

    print(
        f"Báo cáo: {REPORT_FILE}"
    )

    print()

    print(
        "Database: KHÔNG THAY ĐỔI."
    )

    print(
        "Menu/route/template: KHÔNG THAY ĐỔI."
    )

    print()

    print(
        "=" * 140
    )

    print(
        "BÀI 13B-11.15.2.4.5.1 THÀNH CÔNG"
    )

    print(
        "=" * 140
    )


if __name__ == "__main__":
    main()
