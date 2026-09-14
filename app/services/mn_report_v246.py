from __future__ import annotations
from openpyxl.cell.cell import MergedCell

import unicodedata
# === BAI_13B_11_15_2_4_6_5_1_IMPORT_UNICODEDATA ===

"""
BÀI 13B-11.15.2.4.6
Bộ quy tắc/công thức Mầm non theo file:
    Bieu pho cap GDMN(1).xlsx

Nguyên tắc:
- Python tính trực tiếp; không phụ thuộc Excel recalculation.
- Mẫu số trống hoặc <= 0 -> để trống.
- Tỷ số GV/lớp, phòng/lớp KHÔNG nhân 100.
- Tỷ lệ % nhân 100.
- Không tự suy đoán dữ liệu đầu vào chưa có.
"""

from typing import Any


REFERENCE_SHA256 = "c5d2a4ab84197d221de8ffdcc8b8f7b635cd469cadf347bf29471541e81fb89e"

FORMULA_CONTRACT = {
    "MN01_TE": {
        "mobilization": "attending / required * 100",
        "two_sessions": "two_sessions / attending * 100",
        "completion": "completed / completion_denominator * 100",
        "disability_access": "disabled_access / disabled_can_learn * 100",
    },
    "MN01_TC_DK": {
        "classes_total": "single_classes + mixed_classes",
        "mobilization": "attending / required * 100",
        "completion": "completed / attending * 100",
        "disability_access": "disabled_access / disabled_can_learn * 100",
    },
    "MN01_GV": {
        "teacher_class_ratio": "teachers / classes",
        "qualified_rate": "(qualified + above_qualified) / teachers * 100",
        "professional_standard_rate": "professional_standard / teachers * 100",
    },
    "MN01_CSVC": {
        "room_class_ratio": "classrooms / classes",
    },
    "FINANCE": {
        "five_year_average": "(y1+y2+y3+y4+y5)/5",
    },
}


def safe_number(value: Any) -> float | None:
    if value in (None, ""):
        return None

    if isinstance(value, bool):
        return float(int(value))

    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip()

    if not text:
        return None

    # Không cố parse công thức Excel/text hướng dẫn.
    if text.startswith("="):
        return None

    text = text.replace(" ", "")

    # Hỗ trợ dữ liệu hiển thị VN: 1.234,56 / 12,5.
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        text = text.replace(",", ".")

    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def safe_percent(
    numerator: Any,
    denominator: Any,
) -> float | None:
    n = safe_number(numerator)
    d = safe_number(denominator)

    if n is None or d is None or d <= 0:
        return None

    return round(
        n * 100.0 / d,
        2,
    )


def safe_ratio(
    numerator: Any,
    denominator: Any,
) -> float | None:
    n = safe_number(numerator)
    d = safe_number(denominator)

    if n is None or d is None or d <= 0:
        return None

    return round(
        n / d,
        2,
    )


def compatible_can_learn(
    disability_can_learn: Any,
    disability_access_education: Any,
) -> bool:
    """
    Tương thích dữ liệu cũ, chỉ dùng trong báo cáo:
    - True  -> Có
    - False -> Không (ưu tiên tuyệt đối)
    - None + access=True -> suy ra Có
    """
    if disability_can_learn is True:
        return True

    if disability_can_learn is False:
        return False

    return disability_access_education is True


def _cell(ws: Any, ref: str) -> Any:
    return ws[ref].value


# === BAI_13B_12_V2_4_2_1_SAFE_MERGEDCELL_SET ===
def _set(ws: Any, ref: str, value: Any) -> None:
    """
    Ghi giá trị an toàn vào ô thường.

    Nếu ref là MergedCell không phải ô neo trên-trái của vùng merge:
    - KHÔNG ghi;
    - KHÔNG chuyển giá trị về ô neo;
    vì làm vậy có thể ghi đè tiêu đề/nhãn của biểu.
    """
    cell = ws[ref]

    if isinstance(cell, MergedCell):
        return

    cell.value = value




def _sheet(
    workbook: Any,
    *names: str,
) -> Any | None:
    for name in names:
        if name in workbook.sheetnames:
            return workbook[name]

    return None


def _apply_new_te(
    ws: Any,
) -> None:
    # File người dùng gửi:
    # F:L = tuổi 0..6, M = tổng 0..5.
    age_cols = (
        "F", "G", "H", "I", "J", "K", "L",
    )

    for col in age_cols:
        _set(
            ws,
            f"{col}16",
            safe_percent(
                _cell(ws, f"{col}13"),
                _cell(ws, f"{col}12"),
            ),
        )

        _set(
            ws,
            f"{col}22",
            safe_percent(
                _cell(ws, f"{col}21"),
                _cell(ws, f"{col}13"),
            ),
        )

        _set(
            ws,
            f"{col}28",
            safe_percent(
                _cell(ws, f"{col}27"),
                _cell(ws, f"{col}26"),
            ),
        )

    # Tổng 0-5, không cộng cột tuổi 6.
    _set(
        ws,
        "M16",
        safe_percent(
            _cell(ws, "M13"),
            _cell(ws, "M12"),
        ),
    )

    _set(
        ws,
        "M22",
        safe_percent(
            _cell(ws, "M21"),
            _cell(ws, "M13"),
        ),
    )

    _set(
        ws,
        "M28",
        safe_percent(
            _cell(ws, "M27"),
            _cell(ws, "M26"),
        ),
    )


def _apply_old_te(
    ws: Any,
) -> None:
    # Template master cũ: tỷ lệ huy động E17:L17.
    for col in (
        "E", "F", "G", "H",
        "I", "J", "K",
    ):
        _set(
            ws,
            f"{col}17",
            safe_percent(
                _cell(ws, f"{col}14"),
                _cell(ws, f"{col}13"),
            ),
        )

        _set(
            ws,
            f"{col}28",
            safe_percent(
                _cell(ws, f"{col}27"),
                _cell(ws, f"{col}26"),
            ),
        )

    _set(
        ws,
        "L17",
        safe_percent(
            _cell(ws, "L14"),
            _cell(ws, "L13"),
        ),
    )

    _set(
        ws,
        "L28",
        safe_percent(
            _cell(ws, "L27"),
            _cell(ws, "L26"),
        ),
    )


def _apply_tc_dk(
    ws: Any,
) -> None:
    # Bảng bắt đầu dữ liệu từ dòng 8; chạy rộng để hỗ trợ
    # toàn tỉnh + nhiều xã/phường.
    for row in range(
        8,
        int(ws.max_row) + 1,
    ):
        h = safe_number(
            _cell(ws, f"H{row}")
        )
        i = safe_number(
            _cell(ws, f"I{row}")
        )

        if h is not None or i is not None:
            _set(
                ws,
                f"G{row}",
                (h or 0.0) + (i or 0.0),
            )

        _set(
            ws,
            f"L{row}",
            safe_percent(
                _cell(ws, f"K{row}"),
                _cell(ws, f"J{row}"),
            ),
        )

        _set(
            ws,
            f"N{row}",
            safe_percent(
                _cell(ws, f"M{row}"),
                _cell(ws, f"K{row}"),
            ),
        )

        _set(
            ws,
            f"R{row}",
            safe_percent(
                _cell(ws, f"Q{row}"),
                _cell(ws, f"P{row}"),
            ),
        )


def _apply_gv(
    ws: Any,
) -> None:
    for row in range(
        8,
        int(ws.max_row) + 1,
    ):
        _set(
            ws,
            f"N{row}",
            safe_ratio(
                _cell(ws, f"K{row}"),
                _cell(ws, f"J{row}"),
            ),
        )

        qualified = safe_number(
            _cell(ws, f"O{row}")
        )
        above = safe_number(
            _cell(ws, f"P{row}")
        )

        numerator = None

        if (
            qualified is not None
            or above is not None
        ):
            numerator = (
                (qualified or 0.0)
                + (above or 0.0)
            )

        _set(
            ws,
            f"Q{row}",
            safe_percent(
                numerator,
                _cell(ws, f"K{row}"),
            ),
        )

        _set(
            ws,
            f"S{row}",
            safe_percent(
                _cell(ws, f"R{row}"),
                _cell(ws, f"K{row}"),
            ),
        )


def _apply_csvc(
    ws: Any,
) -> None:
    for row in range(
        9,
        int(ws.max_row) + 1,
    ):
        _set(
            ws,
            f"L{row}",
            safe_ratio(
                _cell(ws, f"K{row}"),
                _cell(ws, f"H{row}"),
            ),
        )


def _apply_old_gv(
    ws: Any,
) -> None:
    # Template master cũ MN-01 GV.
    for row in range(
        8,
        int(ws.max_row) + 1,
    ):
        _set(
            ws,
            f"N{row}",
            safe_ratio(
                _cell(ws, f"K{row}"),
                _cell(ws, f"J{row}"),
            ),
        )

        standard = safe_number(
            _cell(ws, f"O{row}")
        )
        above = safe_number(
            _cell(ws, f"P{row}")
        )

        total_standard = None

        if (
            standard is not None
            or above is not None
        ):
            total_standard = (
                (standard or 0.0)
                + (above or 0.0)
            )

        _set(
            ws,
            f"Q{row}",
            safe_percent(
                total_standard,
                _cell(ws, f"K{row}"),
            ),
        )

        _set(
            ws,
            f"S{row}",
            safe_percent(
                _cell(ws, f"R{row}"),
                _cell(ws, f"K{row}"),
            ),
        )


def _apply_finance(
    ws: Any,
) -> None:
    # Chỉ tính đúng công thức /5 khi đủ 5 năm số liệu.
    for row in (
        13,
        14,
    ):
        values = [
            safe_number(
                _cell(
                    ws,
                    f"{col}{row}",
                )
            )
            for col in (
                "E", "F", "G", "H", "I",
            )
        ]

        if all(
            value is not None
            for value in values
        ):
            _set(
                ws,
                f"D{row}",
                round(
                    sum(values) / 5.0,
                    2,
                ),
            )
        else:
            _set(
                ws,
                f"D{row}",
                None,
            )


# === BAI_13B_11_15_2_4_6_1_HIEN_DAU_PHAN_TRAM ===
def _v2461_percent_format(
    cell: Any,
) -> None:
    # Giá trị tỷ lệ hiện đang ở thang 0..100.
    # Ví dụ 100.00 nghĩa là 100%, nên phải dùng dấu % literal.
    # KHÔNG dùng 0.00% vì Excel sẽ hiển thị 100 thành 10000%.
    # === BAI_13B_11_15_2_4_6_3_PERCENT_NO_DECIMAL ===
    cell.number_format = r'0\%'


def _v2461_format_refs(
    ws: Any,
    refs: tuple[str, ...] | list[str],
) -> None:
    for ref in refs:
        _v2461_percent_format(ws[ref])


def _v2461_format_column_rows(
    ws: Any,
    columns: tuple[str, ...],
    start_row: int,
    end_row: int,
) -> None:
    for row in range(int(start_row), int(end_row) + 1):
        for col in columns:
            _v2461_percent_format(ws[f"{col}{row}"])


# === BAI_13B_11_15_2_4_6_4_AUTO_FIND_PERCENT_COLUMN ===
def _v2464_norm_text(
    value: Any,
) -> str:
    text = str(
        value or ""
    ).strip()

    text = unicodedata.normalize(
        "NFD",
        text,
    )

    text = "".join(
        ch
        for ch in text
        if unicodedata.category(ch) != "Mn"
    )

    text = (
        text
        .replace("Đ", "D")
        .replace("đ", "d")
        .upper()
    )

    return " ".join(
        text.split()
    )


def _v2464_format_percent_table_by_header(
    ws: Any,
) -> None:
    """
    Tự tìm bảng có tiêu đề:
        Tiêu chí | Số lượng | Tỉ lệ

    Không phụ thuộc cột cố định.
    Chỉ định dạng cột Tỉ lệ.
    """
    max_scan_row = min(
        int(ws.max_row),
        120,
    )

    max_scan_col = min(
        int(ws.max_column),
        40,
    )

    for row in range(
        1,
        max_scan_row + 1,
    ):
        row_values = {
            col: _v2464_norm_text(
                ws.cell(
                    row,
                    col,
                ).value
            )
            for col in range(
                1,
                max_scan_col + 1,
            )
        }

        has_criteria = any(
            value == "TIEU CHI"
            for value in row_values.values()
        )

        has_quantity = any(
            value in (
                "SO LUONG",
                "SL",
            )
            for value in row_values.values()
        )

        if not (
            has_criteria
            and has_quantity
        ):
            continue

        for col, value in row_values.items():
            if value not in (
                "TI LE",
                "TY LE",
                "TI LE %",
                "TY LE %",
            ):
                continue

            empty_streak = 0

            for data_row in range(
                row + 1,
                min(
                    int(ws.max_row),
                    row + 80,
                )
                + 1,
            ):
                cell = ws.cell(
                    data_row,
                    col,
                )

                if cell.value in (
                    None,
                    "",
                ):
                    empty_streak += 1
                else:
                    empty_streak = 0

                # Helper bài 4.6.2/4.6.3:
                # - đổi chuỗi số thành số thật;
                # - hiển thị dạng 100%, 0%, 50%.
                _v2461_percent_format(
                    cell
                )

                if empty_streak >= 6:
                    break
# === BAI_13B_11_15_2_4_6_4_AUTO_FIND_PERCENT_COLUMN_END ===


def _apply_percent_display_v2461(
    workbook: Any,
) -> None:
    # 1) MN-01-TE mẫu mới.
    ws = _sheet(
        workbook,
        "Thống kê trẻ em từ 0 đến 5 tuổi",
    )
    if ws is not None:
        refs = []
        for col in ("F", "G", "H", "I", "J", "K", "L", "M"):
            refs.extend(
                (
                    f"{col}16",
                    f"{col}22",
                    f"{col}28",
                )
            )

        refs.extend(
            (
                "F35",
                "F36",
                "F37",
                "F38",
                "F40",
                "F41",
                "F42",
            )
        )
        _v2461_format_refs(ws, refs)

    # 2) MN-02 đang xuất thực tế.
    ws = _sheet(
        workbook,
        "Thống kê kết quả PCGD MN",
    )
    if ws is not None:
        _v2461_format_refs(
            ws,
            (
                "H7",
                "K7",
                "O7",
            ),
        )

    # 3) TK đạt chuẩn: L, N, R là tỷ lệ %.
    ws = _sheet(
        workbook,
        "TK dat chuan",
    )
    if ws is not None:
        _v2461_format_column_rows(
            ws,
            ("L", "N", "R"),
            8,
            int(ws.max_row),
        )

    # 4) MN-02 trong bộ 7 sheet master.
    # === BAI_13B_12_V2_4_3_5_MN02_PERCENT_FORMAT ===
    # L = tỷ lệ huy động
    # N = tỷ lệ hoàn thành CTGDMN theo độ tuổi
    # R = tỷ lệ trẻ khuyết tật tiếp cận giáo dục
    ws = _sheet(
        workbook,
        "MN-02",
    )
    if ws is not None:
        _v2461_format_column_rows(
            ws,
            ("L", "N", "R"),
            8,
            int(ws.max_row),
        )

    # 5) GV: N = GV/lớp là tỷ số, KHÔNG thêm %.
    #    Q và S là tỷ lệ %, thêm dấu %.
    for sheet_name in ("GV", "MN-01 GV"):
        ws = _sheet(
            workbook,
            sheet_name,
        )
        if ws is not None:
            _v2461_format_column_rows(
                ws,
                ("Q", "S"),
                8,
                int(ws.max_row),
            )

    # 6) MN-01 TE master.
    # === BAI_13B_12_V2_4_3_6_MN01_TE_PERCENT_FORMAT ===
    # Tất cả ô mang ý nghĩa TỈ LỆ trong MN-01-TE phải hiển thị cùng dạng %.
    # Giá trị nguồn của các ô này đang ở thang 0..100, vì vậy dùng dấu % literal,
    # KHÔNG dùng number_format kiểu 0% (sẽ biến 100 thành 10000%).
    ws = _sheet(
        workbook,
        "MN-01 TE",
    )
    if ws is not None:
        refs = []

        # Bảng chính:
        # dòng 17 = Tỉ lệ huy động
        # dòng 23 = Tỉ lệ trẻ học 2 buổi/ngày
        # dòng 28 = Tỉ lệ hoàn thành chương trình GDMN
        for col in ("E", "F", "G", "H", "I", "J", "K", "L"):
            refs.extend(
                (
                    f"{col}17",
                    f"{col}23",
                    f"{col}28",
                )
            )

        # Bảng tiêu chí:
        # E33:E36 = nhóm trẻ 5 tuổi
        # E38:E40 = nhóm trẻ 3,4 tuổi
        refs.extend(
            (
                "E33",
                "E34",
                "E35",
                "E36",
                "E38",
                "E39",
                "E40",
            )
        )

        for ref in refs:
            ws[ref].number_format = r"0.##\%"

    # 7) Tài chính: D13/D14 là bình quân tỷ lệ 5 năm.
    ws = _sheet(
        workbook,
        "Báo cáo tài chính",
    )
    if ws is not None:
        _v2461_format_refs(
            ws,
            ("D13", "D14"),
        )
    # === BAI_13B_11_15_2_4_6_4_CALL_AUTO_FIND_PERCENT_COLUMN ===
    ws = _sheet(
        workbook,
        "Thống kê trẻ em từ 0 đến 5 tuổi",
    )
    if ws is not None:
        _v2464_format_percent_table_by_header(
            ws
        )

# === BAI_13B_11_15_2_4_6_1_HIEN_DAU_PHAN_TRAM_END ===


def apply_formula_contract(
    workbook: Any,
) -> None:
    """
    Post-processing công thức dùng cho cả:
    - biểu mới người dùng vừa cung cấp;
    - template master cũ;
    - các file xuất chia biểu.

    Hàm chỉ tính từ ô nguồn đã được builder điền.
    Không tạo số liệu nguồn giả.
    """
    ws = _sheet(
        workbook,
        "Thống kê trẻ em từ 0 đến 5 tuổi",
    )
    if ws is not None:
        _apply_new_te(ws)

    ws = _sheet(
        workbook,
        "MN-01 TE",
    )
    if ws is not None:
        _apply_old_te(ws)

    ws = _sheet(
        workbook,
        "TK dat chuan",
        "MN-02",
    )
    if ws is not None and ws.title == "TK dat chuan":
        _apply_tc_dk(ws)

    ws = _sheet(
        workbook,
        "GV",
    )
    if ws is not None:
        _apply_gv(ws)

    ws = _sheet(
        workbook,
        "MN-01 GV",
    )
    if ws is not None:
        _apply_old_gv(ws)

    ws = _sheet(
        workbook,
        "CSVC",
    )
    if ws is not None:
        _apply_csvc(ws)

    ws = _sheet(
        workbook,
        "Báo cáo tài chính",
    )
    if ws is not None:
        _apply_finance(ws)
    # === BAI_13B_11_15_2_4_6_1_CALL_PERCENT_FORMAT ===
    _apply_percent_display_v2461(
        workbook
    )

