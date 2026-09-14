from __future__ import annotations

"""
BÀI 13B-11.15.2.4.7
Bộ tính trực tiếp 79 tỷ lệ Xóa mù chữ theo mẫu Excel chính thức.

Nguyên tắc:
- Chỉ tính từ các ô nguồn đã có trong workbook.
- Không tự suy diễn/điền số liệu nguồn.
- Mẫu số <= 0 hoặc thiếu nguồn -> để trống.
- Giá trị tỷ lệ giữ thang 0..100.
- Hiển thị theo yêu cầu: 100%, 50%, 0% (không phần thập phân).
- Không phụ thuộc Excel recalculation.
"""

from typing import Any


XMC_REPORT_TYPES = {
    "PCGD_CMC_1_2025",
    "PCGD_CMC_2_2025",
    "PCGD_XMC_3_2025",
    "PCGD_XMC_4_2025",
}

# 24 công thức CMC-1.
CMC1_PERCENT_FORMULAS: tuple[
    tuple[str, str, str],
    ...,
] = (
    # 15-25 tuổi, mẫu số G8.
    ("L8", "K8", "G8"),
    ("N8", "M8", "G8"),
    ("P8", "O8", "G8"),
    ("R8", "Q8", "G8"),
    ("T8", "S8", "G8"),
    ("V8", "U8", "G8"),
    ("X8", "W8", "G8"),
    ("Z8", "Y8", "G8"),

    # 15-35 tuổi, mẫu số AA8.
    ("AF8", "AE8", "AA8"),
    ("AH8", "AG8", "AA8"),
    ("AJ8", "AI8", "AA8"),
    ("AL8", "AK8", "AA8"),
    ("AN8", "AM8", "AA8"),
    ("AP8", "AO8", "AA8"),
    ("AR8", "AQ8", "AA8"),
    ("AT8", "AS8", "AA8"),

    # 15-60 tuổi, mẫu số AU8.
    ("AZ8", "AY8", "AU8"),
    ("BB8", "BA8", "AU8"),
    ("BD8", "BC8", "AU8"),
    ("BF8", "BE8", "AU8"),
    ("BH8", "BG8", "AU8"),
    ("BJ8", "BI8", "AU8"),
    ("BL8", "BK8", "AU8"),
    ("BN8", "BM8", "AU8"),
)

# XMC-3: S9:S57 = O/C, gồm cả các dòng cộng 20, 31, 57.
XMC3_PERCENT_FORMULAS: tuple[
    tuple[str, str, str],
    ...,
] = tuple(
    (
        f"S{row}",
        f"O{row}",
        f"C{row}",
    )
    for row in range(9, 58)
)

# 6 công thức XMC-4.
XMC4_PERCENT_FORMULAS: tuple[
    tuple[str, str, str],
    ...,
] = (
    ("E8", "D8", "C8"),
    ("G8", "F8", "C8"),
    ("J8", "I8", "H8"),
    ("L8", "K8", "H8"),
    ("O8", "N8", "M8"),
    ("Q8", "P8", "M8"),
)


def _number(
    value: Any,
) -> float | None:
    if value is None:
        return None

    if isinstance(
        value,
        bool,
    ):
        return float(
            int(value)
        )

    if isinstance(
        value,
        (int, float),
    ):
        return float(value)

    text = str(
        value
    ).strip()

    if not text:
        return None

    # Không dùng cached Excel formula; Python phải lấy
    # từ các ô nguồn đã được builder ghi bằng số.
    if text.startswith("="):
        return None

    compact = text.replace(
        " ",
        "",
    )

    if (
        "," in compact
        and "." in compact
    ):
        if (
            compact.rfind(",")
            > compact.rfind(".")
        ):
            compact = (
                compact
                .replace(
                    ".",
                    "",
                )
                .replace(
                    ",",
                    ".",
                )
            )
        else:
            compact = compact.replace(
                ",",
                "",
            )

    elif "," in compact:
        compact = compact.replace(
            ",",
            ".",
        )

    try:
        return float(
            compact
        )
    except (
        TypeError,
        ValueError,
    ):
        return None


def _percent(
    numerator: Any,
    denominator: Any,
) -> float | None:
    n = _number(
        numerator
    )

    d = _number(
        denominator
    )

    if (
        n is None
        or d is None
        or d <= 0
    ):
        return None

    return round(
        n * 100.0 / d,
        6,
    )


def _write_percent(
    ws: Any,
    target_ref: str,
    numerator_ref: str,
    denominator_ref: str,
) -> None:
    value = _percent(
        ws[numerator_ref].value,
        ws[denominator_ref].value,
    )

    cell = ws[target_ref]
    cell.value = value

    # Giá trị nội bộ 100 => hiển thị 100%.
    # Dấu % là literal, không để Excel nhân thêm 100.
    cell.number_format = r'0\%'


def _apply_formulas(
    ws: Any,
    formulas: tuple[
        tuple[str, str, str],
        ...,
    ],
) -> None:
    for (
        target_ref,
        numerator_ref,
        denominator_ref,
    ) in formulas:
        _write_percent(
            ws,
            target_ref,
            numerator_ref,
            denominator_ref,
        )


def apply_xmc_formula_contract(
    report_type: str,
    ws: Any,
) -> None:
    """
    Tính toàn bộ tỷ lệ XMC đã được xác minh trong mẫu.

    CMC-2 hiện không có phép chia/tỷ lệ trong ma trận 79
    công thức, nên giữ nguyên builder hiện tại.
    """
    code = str(
        report_type or ""
    ).strip().upper()

    if code == "PCGD_CMC_1_2025":
        _apply_formulas(
            ws,
            CMC1_PERCENT_FORMULAS,
        )
        return

    if code == "PCGD_XMC_3_2025":
        _apply_formulas(
            ws,
            XMC3_PERCENT_FORMULAS,
        )
        return

    if code == "PCGD_XMC_4_2025":
        _apply_formulas(
            ws,
            XMC4_PERCENT_FORMULAS,
        )
        return

    # PCGD_CMC_2_2025: không có tỷ lệ trong ma trận,
    # không sửa dữ liệu.
    return


def formula_count() -> dict[str, int]:
    return {
        "CMC_1": len(
            CMC1_PERCENT_FORMULAS
        ),
        "XMC_3": len(
            XMC3_PERCENT_FORMULAS
        ),
        "XMC_4": len(
            XMC4_PERCENT_FORMULAS
        ),
        "TOTAL": (
            len(
                CMC1_PERCENT_FORMULAS
            )
            + len(
                XMC3_PERCENT_FORMULAS
            )
            + len(
                XMC4_PERCENT_FORMULAS
            )
        ),
    }
