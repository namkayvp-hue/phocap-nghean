from __future__ import annotations

import ast
import os
import shutil
import sqlite3
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path

PROJECT = Path(
    os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")
).resolve()

APP = PROJECT / "app"
ROUTER = APP / "routers" / "mn_official_reports.py"
DB = PROJECT / "data" / "phocap.db"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = (
    PROJECT
    / "exports"
    / f"backup_bao_cao_mn_ty_le_v1_3_{STAMP}"
)

V12_START = (
    "# === BAO_CAO_MN_MAU_MOI_V1_2_TINH_TY_LE START ==="
)
V12_END = (
    "# === BAO_CAO_MN_MAU_MOI_V1_2_TINH_TY_LE END ==="
)

V13_START = (
    "# === BAO_CAO_MN_MAU_MOI_V1_3_TY_LE_TRUC_TIEP START ==="
)
V13_END = (
    "# === BAO_CAO_MN_MAU_MOI_V1_3_TY_LE_TRUC_TIEP END ==="
)

V13_BLOCK = '\n    # === BAO_CAO_MN_MAU_MOI_V1_3_TY_LE_TRUC_TIEP START ===\n    # V1.3:\n    # - Ghi giá trị tỷ lệ trực tiếp, không phụ thuộc Excel recalculation.\n    # - Dò dòng theo nhãn của mẫu, không phụ thuộc số dòng cố định.\n    # - Nếu mẫu số chưa có/không hợp lệ thì giữ ô trống.\n\n    def _v13_number(value):\n        if isinstance(value, bool):\n            return int(value)\n        if isinstance(value, (int, float)):\n            return float(value)\n        return None\n\n    def _v13_pct100(numerator, denominator):\n        n = _v13_number(numerator)\n        d = _v13_number(denominator)\n\n        if n is None or d is None or d <= 0:\n            return None\n\n        return round(n / d * 100.0, 2)\n\n    def _v13_ratio_decimal(numerator, denominator):\n        n = _v13_number(numerator)\n        d = _v13_number(denominator)\n\n        if n is None or d is None or d <= 0:\n            return None\n\n        return n / d\n\n    def _v13_row_contains(*parts, start_row=1):\n        expected = [\n            _norm_text(part)\n            for part in parts\n            if str(part or "").strip()\n        ]\n\n        for row_no in range(\n            max(1, int(start_row)),\n            ws.max_row + 1,\n        ):\n            row_text = " ".join(\n                str(\n                    ws.cell(\n                        row=row_no,\n                        column=col_no,\n                    ).value\n                    or ""\n                )\n                for col_no in range(\n                    1,\n                    min(ws.max_column, 16) + 1,\n                )\n            )\n\n            normalized = _norm_text(row_text)\n\n            if all(\n                part in normalized\n                for part in expected\n            ):\n                return row_no\n\n        return None\n\n    def _v13_header_column(\n        row_no,\n        label,\n    ):\n        expected = _norm_text(label)\n\n        if not row_no:\n            return None\n\n        for col_no in range(\n            1,\n            ws.max_column + 1,\n        ):\n            value = ws.cell(\n                row=row_no,\n                column=col_no,\n            ).value\n\n            if (\n                expected\n                in _norm_text(value or "")\n            ):\n                return col_no\n\n        return None\n\n    def _v13_cell(row_no, col_letter):\n        if not row_no or not col_letter:\n            return None\n\n        return ws[\n            f"{col_letter}{row_no}"\n        ].value\n\n    def _v13_sum_ages(\n        row_no,\n        ages,\n    ):\n        if not row_no:\n            return None\n\n        values = []\n\n        for age in ages:\n            col = age_cols.get(age)\n\n            if not col:\n                continue\n\n            value = _v13_number(\n                ws[\n                    f"{col}{row_no}"\n                ].value\n            )\n\n            if value is not None:\n                values.append(value)\n\n        if not values:\n            return None\n\n        return sum(values)\n\n    # ----------------------------------------------------------\n    # A. XÁC ĐỊNH DÒNG CỦA BẢNG CHÍNH\n    # ----------------------------------------------------------\n    total_children_row = _v13_row_contains(\n        "Tổng số trẻ trong độ tuổi"\n    )\n\n    disability_total_row = _v13_row_contains(\n        "Trẻ khuyết tật trong độ tuổi",\n        "Tổng số",\n    )\n\n    disability_access_row = _v13_row_contains(\n        "Số trẻ được tiếp cận giáo dục"\n    )\n\n    must_mobilize_row = _v13_row_contains(\n        "Số trẻ phải huy động"\n    )\n\n    attending_row = _v13_row_contains(\n        "Số trẻ đến trường"\n    )\n\n    mobilization_ratio_row = _v13_row_contains(\n        "Tỉ lệ huy động"\n    )\n\n    two_sessions_row = _v13_row_contains(\n        "Số trẻ học 2 buổi/ngày"\n    )\n\n    two_sessions_ratio_row = _v13_row_contains(\n        "Tỉ lệ trẻ học 2 buổi"\n    )\n\n    completion_basis_row = _v13_row_contains(\n        "Số trẻ làm căn cứ",\n        "hoàn thành",\n    )\n\n    completion_count_row = _v13_row_contains(\n        "Số trẻ hoàn thành",\n        "Chương trình GDMN theo độ tuổi",\n    )\n\n    if completion_count_row == completion_basis_row:\n        completion_count_row = None\n\n    completion_ratio_row = _v13_row_contains(\n        "Tỉ lệ hoàn thành chương trình GDMN"\n    )\n\n    # ----------------------------------------------------------\n    # B. ĐIỀN HỌC 2 BUỔI/NGÀY\n    # ----------------------------------------------------------\n    two_sessions = metrics.get(\n        "two_sessions",\n        {},\n    )\n\n    if two_sessions_row:\n        for age, col in age_cols.items():\n            ws[\n                f"{col}{two_sessions_row}"\n            ] = int(\n                two_sessions.get(\n                    age,\n                    0,\n                )\n                or 0\n            )\n\n        total_col_letter = "M"\n\n        ws[\n            f"{total_col_letter}{two_sessions_row}"\n        ] = int(\n            sum(\n                int(\n                    two_sessions.get(\n                        age,\n                        0,\n                    )\n                    or 0\n                )\n                for age in range(0, 6)\n            )\n        )\n\n    # ----------------------------------------------------------\n    # C. TỶ LỆ BẢNG CHÍNH\n    # ----------------------------------------------------------\n    total_col_letter = "M"\n\n    ratio_columns = list(\n        age_cols.values()\n    ) + [total_col_letter]\n\n    if (\n        must_mobilize_row\n        and attending_row\n        and mobilization_ratio_row\n    ):\n        for col in ratio_columns:\n            value = _v13_ratio_decimal(\n                _v13_cell(\n                    attending_row,\n                    col,\n                ),\n                _v13_cell(\n                    must_mobilize_row,\n                    col,\n                ),\n            )\n\n            ws[\n                f"{col}{mobilization_ratio_row}"\n            ] = (\n                value\n                if value is not None\n                else ""\n            )\n\n    if (\n        two_sessions_row\n        and attending_row\n        and two_sessions_ratio_row\n    ):\n        for col in ratio_columns:\n            value = _v13_pct100(\n                _v13_cell(\n                    two_sessions_row,\n                    col,\n                ),\n                _v13_cell(\n                    attending_row,\n                    col,\n                ),\n            )\n\n            ws[\n                f"{col}{two_sessions_ratio_row}"\n            ] = (\n                value\n                if value is not None\n                else ""\n            )\n\n    if (\n        completion_basis_row\n        and completion_count_row\n        and completion_ratio_row\n    ):\n        for col in ratio_columns:\n            value = _v13_pct100(\n                _v13_cell(\n                    completion_count_row,\n                    col,\n                ),\n                _v13_cell(\n                    completion_basis_row,\n                    col,\n                ),\n            )\n\n            ws[\n                f"{col}{completion_ratio_row}"\n            ] = (\n                value\n                if value is not None\n                else ""\n            )\n\n    # ----------------------------------------------------------\n    # D. BẢNG TIÊU CHÍ PHÍA DƯỚI\n    # ----------------------------------------------------------\n    criteria_header_row = _v13_row_contains(\n        "Tiêu chí",\n        "Số lượng",\n        "Tỉ lệ",\n        start_row=25,\n    )\n\n    quantity_col = _v13_header_column(\n        criteria_header_row,\n        "Số lượng",\n    )\n\n    percentage_col = _v13_header_column(\n        criteria_header_row,\n        "Tỉ lệ",\n    )\n\n    def _v13_write_criterion(\n        row_no,\n        quantity,\n        percentage,\n    ):\n        if (\n            not row_no\n            or not quantity_col\n            or not percentage_col\n        ):\n            return\n\n        quantity_value = quantity\n\n        if isinstance(\n            quantity,\n            (int, float),\n        ):\n            q_float = float(quantity)\n\n            if q_float.is_integer():\n                quantity_value = int(\n                    q_float\n                )\n\n        ws.cell(\n            row=row_no,\n            column=quantity_col,\n        ).value = quantity_value\n\n        ws.cell(\n            row=row_no,\n            column=percentage_col,\n        ).value = (\n            percentage\n            if percentage is not None\n            else ""\n        )\n\n    criteria_start = (\n        criteria_header_row + 1\n        if criteria_header_row\n        else 1\n    )\n\n    row_5_attending = _v13_row_contains(\n        "Trẻ 5 tuổi đến trường",\n        start_row=criteria_start,\n    )\n\n    row_5_completed = _v13_row_contains(\n        "Trẻ 5 tuổi hoàn thành chương trình GDMN",\n        start_row=criteria_start,\n    )\n\n    row_5_disability = _v13_row_contains(\n        "Trẻ 5 tuổi khuyết tật",\n        "tiếp cận",\n        start_row=criteria_start,\n    )\n\n    row_5_two_sessions = _v13_row_contains(\n        "Trẻ học 2 buổi/ngày",\n        start_row=criteria_start,\n    )\n\n    row_34_attending = _v13_row_contains(\n        "Trẻ 3, 4 tuổi đến trường",\n        start_row=criteria_start,\n    )\n\n    row_34_completed = _v13_row_contains(\n        "Trẻ 3, 4 tuổi hoàn thành",\n        start_row=criteria_start,\n    )\n\n    row_34_two_sessions = _v13_row_contains(\n        "Trẻ 3, 4 tuổi học 2 buổi/ngày",\n        start_row=criteria_start,\n    )\n\n    col_age_5 = age_cols.get(5)\n\n    quantity = (\n        _v13_number(\n            _v13_cell(\n                attending_row,\n                col_age_5,\n            )\n        )\n        if col_age_5\n        else None\n    )\n\n    percentage = (\n        _v13_pct100(\n            quantity,\n            _v13_cell(\n                total_children_row,\n                col_age_5,\n            ),\n        )\n        if col_age_5\n        else None\n    )\n\n    _v13_write_criterion(\n        row_5_attending,\n        quantity,\n        percentage,\n    )\n\n    quantity = (\n        _v13_number(\n            _v13_cell(\n                completion_count_row,\n                col_age_5,\n            )\n        )\n        if col_age_5\n        else None\n    )\n\n    percentage = (\n        _v13_pct100(\n            quantity,\n            _v13_cell(\n                completion_basis_row,\n                col_age_5,\n            ),\n        )\n        if col_age_5\n        else None\n    )\n\n    _v13_write_criterion(\n        row_5_completed,\n        quantity,\n        percentage,\n    )\n\n    quantity = (\n        _v13_number(\n            _v13_cell(\n                disability_access_row,\n                col_age_5,\n            )\n        )\n        if col_age_5\n        else None\n    )\n\n    percentage = (\n        _v13_pct100(\n            quantity,\n            _v13_cell(\n                disability_total_row,\n                col_age_5,\n            ),\n        )\n        if col_age_5\n        else None\n    )\n\n    _v13_write_criterion(\n        row_5_disability,\n        quantity,\n        percentage,\n    )\n\n    quantity = (\n        _v13_number(\n            _v13_cell(\n                two_sessions_row,\n                col_age_5,\n            )\n        )\n        if col_age_5\n        else None\n    )\n\n    percentage = (\n        _v13_pct100(\n            quantity,\n            _v13_cell(\n                attending_row,\n                col_age_5,\n            ),\n        )\n        if col_age_5\n        else None\n    )\n\n    _v13_write_criterion(\n        row_5_two_sessions,\n        quantity,\n        percentage,\n    )\n\n    quantity = _v13_sum_ages(\n        attending_row,\n        (3, 4),\n    )\n\n    percentage = _v13_pct100(\n        quantity,\n        _v13_sum_ages(\n            total_children_row,\n            (3, 4),\n        ),\n    )\n\n    _v13_write_criterion(\n        row_34_attending,\n        quantity,\n        percentage,\n    )\n\n    quantity = _v13_sum_ages(\n        completion_count_row,\n        (3, 4),\n    )\n\n    percentage = _v13_pct100(\n        quantity,\n        _v13_sum_ages(\n            completion_basis_row,\n            (3, 4),\n        ),\n    )\n\n    _v13_write_criterion(\n        row_34_completed,\n        quantity,\n        percentage,\n    )\n\n    quantity = _v13_sum_ages(\n        two_sessions_row,\n        (3, 4),\n    )\n\n    percentage = _v13_pct100(\n        quantity,\n        _v13_sum_ages(\n            attending_row,\n            (3, 4),\n        ),\n    )\n\n    _v13_write_criterion(\n        row_34_two_sessions,\n        quantity,\n        percentage,\n    )\n\n    # Không cần Excel tính lại công thức mới:\n    # toàn bộ tỷ lệ V1.3 đã được ghi thành số trực tiếp.\n    # === BAO_CAO_MN_MAU_MOI_V1_3_TY_LE_TRUC_TIEP END ===\n'


def read_text(path: Path) -> str:
    if not path.exists():
        raise RuntimeError(
            f"Không tìm thấy: {path}"
        )

    return path.read_text(
        encoding="utf-8-sig",
        errors="strict",
    )


def write_text(
    path: Path,
    text: str,
) -> None:
    path.write_text(
        text,
        encoding="utf-8",
    )


def backup_source() -> None:
    target = (
        BACKUP
        / ROUTER.relative_to(PROJECT)
    )

    target.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    shutil.copy2(
        ROUTER,
        target,
    )


def restore_source() -> None:
    source = (
        BACKUP
        / ROUTER.relative_to(PROJECT)
    )

    if source.exists():
        shutil.copy2(
            source,
            ROUTER,
        )


def clear_cache() -> None:
    for cache in APP.rglob(
        "__pycache__"
    ):
        if cache.is_dir():
            shutil.rmtree(
                cache,
                ignore_errors=True,
            )


def db_check() -> tuple[str, int]:
    conn = sqlite3.connect(
        str(DB)
    )

    try:
        integrity = str(
            conn.execute(
                "PRAGMA integrity_check"
            ).fetchone()[0]
        )

        fk_count = len(
            conn.execute(
                "PRAGMA foreign_key_check"
            ).fetchall()
        )

        return (
            integrity,
            fk_count,
        )

    finally:
        conn.close()


def function_span(
    source: str,
    name: str,
) -> tuple[int, int]:
    tree = ast.parse(
        source
    )

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
            f"Phải tìm thấy đúng 1 hàm "
            f"{name}; hiện có {len(matches)}."
        )

    node = matches[0]

    lines = source.splitlines(
        keepends=True
    )

    offsets = [0]

    for line in lines:
        offsets.append(
            offsets[-1]
            + len(line)
        )

    return (
        offsets[
            int(node.lineno) - 1
        ],
        offsets[
            int(node.end_lineno)
        ],
    )


def patch_source(
    source: str,
) -> str:
    if V13_START in source:
        print(
            " - V1.3 đã có sẵn; "
            "không chèn lặp."
        )

        return source

    if V12_START not in source:
        raise RuntimeError(
            "Không thấy block V1.2. "
            "Hãy bảo đảm đã cài "
            "cai_dat_bao_cao_mn_mau_moi_v1_2_tinh_ty_le.py."
        )

    start, end = function_span(
        source,
        "_fill_te_workbook",
    )

    function_text = source[
        start:end
    ]

    old_start = function_text.find(
        V12_START
    )

    old_end = function_text.find(
        V12_END,
        old_start,
    )

    if (
        old_start < 0
        or old_end < 0
    ):
        raise RuntimeError(
            "Không xác định đầy đủ "
            "block V1.2 trong _fill_te_workbook."
        )

    old_end += len(
        V12_END
    )

    new_function = (
        function_text[:old_start]
        + V13_BLOCK.strip("\n")
        + function_text[old_end:]
    )

    patched = (
        source[:start]
        + new_function
        + source[end:]
    )

    ast.parse(
        patched
    )

    return patched


def verify_source(
    source: str,
) -> None:
    ast.parse(
        source
    )

    required = (
        V13_START,
        V13_END,
        "_v13_pct100",
        "_v13_ratio_decimal",
        "_v13_row_contains",
        'metrics.get(',
        '"two_sessions"',
        "Trẻ 3,4 tuổi",
    )

    for item in required:
        if item not in source:
            raise RuntimeError(
                "Source sau cài thiếu: "
                + item
            )

    if V12_START in source:
        raise RuntimeError(
            "Block V1.2 cũ vẫn còn "
            "trong source."
        )


def main() -> int:
    print("=" * 118)
    print(
        "BÁO CÁO MẦM NON MẪU MỚI V1.3 - "
        "TÍNH TỶ LỆ TRỰC TIẾP, KHÔNG PHỤ THUỘC EXCEL"
    )
    print("=" * 118)
    print()
    print("NGUYÊN NHÂN V1.2:")
    print(
        " - V1.2 ghi công thức Excel vào file."
    )
    print(
        " - Protected View có thể chưa tính lại "
        "công thức mới, nên ô tỷ lệ nhìn thấy trống."
    )
    print()
    print("V1.3 SỬA:")
    print(
        " - Python tính tỷ lệ trước khi lưu file."
    )
    print(
        " - Ghi trực tiếp giá trị số vào ô tỷ lệ."
    )
    print(
        " - Không cần Enable Editing để tỷ lệ xuất hiện."
    )
    print(
        " - Dò dòng theo nhãn của mẫu, "
        "không phụ thuộc số dòng cố định."
    )
    print(
        " - Sửa cả bảng Tiêu chí phía dưới."
    )
    print()
    print("NGUYÊN TẮC:")
    print(
        " - Mẫu số chưa có hoặc bằng 0 -> để trống."
    )
    print(
        " - Không tự suy đoán thành 0."
    )
    print(
        " - Không sửa database."
    )
    print(
        " - Không sửa file mẫu Excel gốc."
    )
    print()

    if not ROUTER.exists():
        raise RuntimeError(
            f"Không tìm thấy: {ROUTER}"
        )

    if not DB.exists():
        raise RuntimeError(
            f"Không tìm thấy: {DB}"
        )

    (
        integrity_before,
        fk_before,
    ) = db_check()

    print(
        "integrity_check trước cài:",
        integrity_before,
    )
    print(
        "foreign_key_check trước cài:",
        fk_before,
        "lỗi",
    )

    if (
        integrity_before.lower()
        != "ok"
        or fk_before != 0
    ):
        raise RuntimeError(
            "Database không đạt kiểm tra "
            "an toàn trước khi cài."
        )

    BACKUP.mkdir(
        parents=True,
        exist_ok=False,
    )

    backup_source()

    print(
        "Backup:",
        BACKUP,
    )

    try:
        original = read_text(
            ROUTER
        )

        patched = patch_source(
            original
        )

        verify_source(
            patched
        )

        write_text(
            ROUTER,
            patched,
        )

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "py_compile",
                str(ROUTER),
            ],
            cwd=PROJECT,
            capture_output=True,
            text=True,
        )

        if result.stdout:
            print(
                result.stdout.rstrip()
            )

        if result.stderr:
            print(
                result.stderr.rstrip()
            )

        if result.returncode != 0:
            raise RuntimeError(
                "py_compile "
                "mn_official_reports.py không đạt."
            )

        verify_source(
            read_text(
                ROUTER
            )
        )

        clear_cache()

        (
            integrity_after,
            fk_after,
        ) = db_check()

        if (
            integrity_after.lower()
            != "ok"
            or fk_after != 0
        ):
            raise RuntimeError(
                "Database không đạt kiểm tra "
                "sau cài."
            )

        print()
        print("KIỂM TRA SAU CÀI:")
        print(
            " - Block công thức V1.2: ĐÃ LOẠI"
        )
        print(
            " - Tỷ lệ ghi trực tiếp bằng Python: OK"
        )
        print(
            " - Dò dòng theo nhãn: OK"
        )
        print(
            " - Bảng Tiêu chí: OK"
        )
        print(
            " - py_compile: OK"
        )
        print(
            " - Database: KHÔNG THAY ĐỔI"
        )
        print(
            " - Mẫu Excel gốc: KHÔNG THAY ĐỔI"
        )
        print()
        print("=" * 118)
        print(
            "CÀI ĐẶT BÁO CÁO "
            "MẦM NON V1.3 THÀNH CÔNG"
        )
        print("=" * 118)

        return 0

    except Exception:
        traceback.print_exc()

        print()
        print(
            "CÓ LỖI - "
            "ĐANG KHÔI PHỤC SOURCE..."
        )

        restore_source()
        clear_cache()

        print(
            "ĐÃ KHÔI PHỤC SOURCE."
        )
        print(
            "Database không bị thay đổi."
        )
        print(
            "Backup:",
            BACKUP,
        )

        return 1


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
