from __future__ import annotations

import os
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.cell.cell import MergedCell


PROJECT = Path(
    os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")
).resolve()

APP = PROJECT / "app"
TEMPLATE_ROOT = APP / "report_templates"
EXPORTS = PROJECT / "exports"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
OUT = (
    EXPORTS
    / f"ma_tran_sach_ty_le_bai_13b_11_15_2_4_1_{STAMP}.txt"
)

SOURCE_BY_GROUP = {
    "MẦM NON": (
        APP / "pcgd_mn_report_builders_v1.py",
        APP / "routers" / "mn_official_reports.py",
        APP / "routers" / "pcgdmn_template_report.py",
        APP / "routers" / "preschool_3_5_report.py",
        APP / "routers" / "report_inputs.py",
    ),
    "TIỂU HỌC": (
        APP / "pcgd_xmc_report_builders_v1.py",
        APP / "routers" / "report_center.py",
        APP / "routers" / "report_inputs.py",
    ),
    "THCS": (
        APP / "pcgd_xmc_report_builders_v1.py",
        APP / "routers" / "report_center.py",
        APP / "routers" / "report_inputs.py",
    ),
    "XÓA MÙ CHỮ": (
        APP / "pcgd_xmc_report_builders_v1.py",
        APP / "routers" / "report_center.py",
    ),
}

REPORT_CODE_HINTS = {
    "MẦM NON": ("PCGD_MN", "MN_", "PCGDMN"),
    "TIỂU HỌC": ("PCGD_TH_", "TH_01_", "TH_M1", "TH_02"),
    "THCS": ("PCGD_THCS_", "THCS_"),
    "XÓA MÙ CHỮ": ("PCGD_XMC_", "XMC_", "PCGD_CMC_", "CMC_"),
}

PERCENT_LABELS = (
    "tỷ lệ",
    "tỉ lệ",
    "ty le",
    "ti le",
    "%",
)

RATIO_LABELS = (
    "gv/lớp",
    "gv/lop",
    "giáo viên/lớp",
    "giao vien/lop",
    "phòng/lớp",
    "phong/lop",
    "phòng học/lớp",
    "phong hoc/lop",
    "tỷ số",
    "tỉ số",
)

HEADER_WORDS = (
    "tỷ lệ",
    "tỉ lệ",
    "tỷ số",
    "tỉ số",
    "giáo viên",
    "lớp",
    "phòng",
    "tổng số",
    "đạt",
    "chuẩn",
    "huy động",
    "hoàn thành",
    "khuyết tật",
    "tiếp cận",
    "xóa mù",
    "chống mù",
    "mù chữ",
    "phổ cập",
)


def norm(value: object) -> str:
    return " ".join(
        str(value or "")
        .strip()
        .lower()
        .split()
    )


def group_from_path(path: Path) -> str:
    name = path.name.upper()

    if "THCS" in name:
        return "THCS"

    if "XMC" in name or "CMC" in name:
        return "XÓA MÙ CHỮ"

    if "PCGD_2025_TH_" in name or "_TH_" in name:
        return "TIỂU HỌC"

    if "MN" in name or "PCGDMN" in name:
        return "MẦM NON"

    return "CHƯA PHÂN NHÓM"


def canonical_files() -> list[Path]:
    candidates = []

    direct = TEMPLATE_ROOT / "Bieu_mau_PCGDMN_2025.xlsx"
    if direct.exists():
        candidates.append(direct)

    for folder_name in (
        "pcgd_mn_2025",
        "pcgd_xmc_2025",
    ):
        folder = TEMPLATE_ROOT / folder_name

        if folder.exists():
            candidates.extend(
                sorted(
                    path
                    for path in folder.glob("*.xlsx")
                    if path.is_file()
                )
            )

    seen = set()
    result = []

    for path in candidates:
        key = str(path.resolve()).lower()

        if key in seen:
            continue

        seen.add(key)
        result.append(path)

    return result


def merged_anchor_value(
    ws,
    row: int,
    col: int,
):
    cell = ws.cell(
        row=row,
        column=col,
    )

    if not isinstance(
        cell,
        MergedCell,
    ):
        return cell.value

    coord = cell.coordinate

    for merged in ws.merged_cells.ranges:
        if coord in merged:
            return ws.cell(
                row=merged.min_row,
                column=merged.min_col,
            ).value

    return None


def context_labels(
    ws,
    row: int,
    col: int,
) -> list[str]:
    candidates = []

    # Ưu tiên các tiêu đề phía trên cùng cột.
    for rr in range(
        max(1, row - 7),
        row,
    ):
        value = merged_anchor_value(
            ws,
            rr,
            col,
        )

        text = str(
            value or ""
        ).strip()

        if text and not text.startswith("="):
            candidates.append(
                (
                    0,
                    rr,
                    col,
                    text,
                )
            )

    # Nhãn phía trái cùng hàng.
    for cc in range(
        max(1, col - 8),
        col,
    ):
        value = merged_anchor_value(
            ws,
            row,
            cc,
        )

        text = str(
            value or ""
        ).strip()

        if text and not text.startswith("="):
            candidates.append(
                (
                    1,
                    row,
                    cc,
                    text,
                )
            )

    # Vùng lân cận phía trên-trái.
    for rr in range(
        max(1, row - 4),
        row + 1,
    ):
        for cc in range(
            max(1, col - 5),
            col + 1,
        ):
            if rr == row and cc == col:
                continue

            value = merged_anchor_value(
                ws,
                rr,
                cc,
            )

            text = str(
                value or ""
            ).strip()

            if text and not text.startswith("="):
                candidates.append(
                    (
                        2,
                        rr,
                        cc,
                        text,
                    )
                )

    # Khử lặp, ưu tiên text có nghĩa nghiệp vụ hơn số thuần.
    scored = []

    for priority, rr, cc, text in candidates:
        n = norm(text)

        is_numeric = bool(
            re.fullmatch(
                r"[-+]?\d+(?:[.,]\d+)?",
                n,
            )
        )

        keyword_score = sum(
            1
            for word in HEADER_WORDS
            if word in n
        )

        score = (
            keyword_score * 100
            - int(is_numeric) * 50
            - priority * 10
            - abs(row - rr)
            - abs(col - cc)
        )

        scored.append(
            (
                score,
                text,
            )
        )

    scored.sort(
        key=lambda item: item[0],
        reverse=True,
    )

    result = []
    seen = set()

    for _score, text in scored:
        key = norm(text)

        if not key or key in seen:
            continue

        seen.add(key)
        result.append(text)

        if len(result) >= 5:
            break

    return result


def unwrap_sum(expr: str) -> str:
    text = expr.strip()

    match = re.fullmatch(
        r"(?i)SUM\((.*)\)",
        text,
    )

    if match:
        return match.group(1).strip()

    return text


def split_top_level_division(
    expr: str,
) -> tuple[str, str] | None:
    depth = 0

    for idx, ch in enumerate(expr):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        elif ch == "/" and depth == 0:
            return (
                expr[:idx].strip(),
                expr[idx + 1:].strip(),
            )

    return None


def parse_formula(
    formula: str,
) -> dict[str, str | bool]:
    original = str(
        formula or ""
    ).strip()

    expr = (
        original[1:]
        if original.startswith("=")
        else original
    ).strip()

    percent_suffix = False
    multiply_100 = False

    if expr.endswith("%"):
        percent_suffix = True
        expr = expr[:-1].strip()

    # Chuẩn hóa dạng A/B*100 hoặc 100*A/B.
    m = re.fullmatch(
        r"(?is)(.+?)\*\s*100(?:\.0+)?",
        expr,
    )

    if m:
        multiply_100 = True
        expr = m.group(1).strip()

    m = re.fullmatch(
        r"(?is)100(?:\.0+)?\s*\*\s*(.+)",
        expr,
    )

    if m:
        multiply_100 = True
        expr = m.group(1).strip()

    outer_sum = re.fullmatch(
        r"(?is)SUM\((.*)\)",
        expr,
    )

    if outer_sum:
        inner = outer_sum.group(1).strip()

        if "/" in inner:
            expr = inner

    split = split_top_level_division(
        expr
    )

    if not split:
        return {
            "numerator": "",
            "denominator": "",
            "is_division": False,
            "percent_signal": (
                percent_suffix
                or multiply_100
            ),
            "normalized": expr,
        }

    numerator, denominator = split

    return {
        "numerator": unwrap_sum(
            numerator
        ),
        "denominator": denominator,
        "is_division": True,
        "percent_signal": (
            percent_suffix
            or multiply_100
        ),
        "normalized": expr,
    }


def classify(
    formula_info: dict[str, str | bool],
    number_format: str,
    labels: list[str],
) -> str:
    label_text = norm(
        " | ".join(
            labels
        )
    )

    fmt = norm(
        number_format
    )

    if (
        bool(
            formula_info[
                "percent_signal"
            ]
        )
        or "%" in fmt
        or any(
            token in label_text
            for token in PERCENT_LABELS
        )
    ):
        return "PERCENT"

    if any(
        token in label_text
        for token in RATIO_LABELS
    ):
        return "RATIO"

    return "DIVISION_CẦN_XÁC_MINH"


def load_group_sources(
    group: str,
) -> dict[str, list[str]]:
    result = {}

    for path in SOURCE_BY_GROUP.get(
        group,
        (),
    ):
        if not path.exists():
            continue

        try:
            text = path.read_text(
                encoding="utf-8-sig",
            )
        except UnicodeDecodeError:
            text = path.read_text(
                encoding="utf-8",
                errors="replace",
            )

        result[
            str(
                path.relative_to(
                    PROJECT
                )
            )
        ] = text.splitlines()

    return result


def report_code_tokens(
    path: Path,
) -> set[str]:
    stem = path.stem.upper()

    tokens = {
        stem,
    }

    # Các token có giá trị định danh mạnh.
    for part in re.split(
        r"[^A-Z0-9]+",
        stem,
    ):
        if len(part) >= 3:
            tokens.add(part)

    return tokens


def source_matches(
    group: str,
    template_path: Path,
    cell_ref: str,
) -> list[str]:
    sources = load_group_sources(
        group
    )

    q1 = f'"{cell_ref}"'
    q2 = f"'{cell_ref}'"

    strong_tokens = report_code_tokens(
        template_path
    )

    group_hints = set(
        REPORT_CODE_HINTS.get(
            group,
            (),
        )
    )

    matches = []

    for rel, lines in sources.items():
        for number, line in enumerate(
            lines,
            start=1,
        ):
            if q1 not in line and q2 not in line:
                continue

            window_start = max(
                0,
                number - 20,
            )
            window_end = min(
                len(lines),
                number + 20,
            )

            window = "\n".join(
                lines[
                    window_start:
                    window_end
                ]
            ).upper()

            line_upper = line.upper()

            context_ok = (
                any(
                    token in window
                    for token in strong_tokens
                    if len(token) >= 5
                )
                or any(
                    hint in window
                    for hint in group_hints
                )
                or (
                    "pcgd_xmc_report_builders_v1.py" in rel
                    and group
                    in {
                        "TIỂU HỌC",
                        "THCS",
                        "XÓA MÙ CHỮ",
                    }
                )
                or (
                    group == "MẦM NON"
                    and (
                        "pcgd_mn_report_builders_v1.py" in rel
                        or "mn_official_reports.py" in rel
                        or "pcgdmn_template_report.py" in rel
                    )
                )
            )

            if not context_ok:
                continue

            matches.append(
                f"{rel}:{number}: {line.strip()}"
            )

    return matches[:10]


def likely_false_match(
    group: str,
    match: str,
) -> bool:
    low = match.lower()

    if group == "XÓA MÙ CHỮ":
        return (
            "mn02_ws" in low
            or "mn_official_reports.py" in low
            or "pcgdmn_template_report.py" in low
        )

    if group == "THCS":
        return "mn_official_reports.py" in low

    if group == "TIỂU HỌC":
        return (
            'ws["h40"] = _percent' in low
            or 'ws["h41"] = _percent' in low
        )

    return False


def matrix_rows():
    rows = []

    for path in canonical_files():
        group = group_from_path(
            path
        )

        wb = load_workbook(
            path,
            data_only=False,
            read_only=False,
        )

        try:
            for ws in wb.worksheets:
                for row in ws.iter_rows():
                    for cell in row:
                        value = cell.value

                        if (
                            not isinstance(
                                value,
                                str,
                            )
                            or not value.startswith("=")
                            or "/" not in value
                        ):
                            continue

                        info = parse_formula(
                            value
                        )

                        labels = context_labels(
                            ws,
                            cell.row,
                            cell.column,
                        )

                        kind = classify(
                            info,
                            cell.number_format,
                            labels,
                        )

                        matches = [
                            item
                            for item in source_matches(
                                group,
                                path,
                                cell.coordinate,
                            )
                            if not likely_false_match(
                                group,
                                item,
                            )
                        ]

                        status = (
                            "CÓ_DẤU_VẾT_PYTHON_CÙNG_NHÓM"
                            if matches
                            else (
                                "ĐỦ_CT_EXCEL_CHƯA_THẤY_PYTHON"
                                if kind
                                in {
                                    "PERCENT",
                                    "RATIO",
                                }
                                and info[
                                    "numerator"
                                ]
                                and info[
                                    "denominator"
                                ]
                                else "CẦN_XÁC_MINH_NGHIỆP_VỤ"
                            )
                        )

                        rows.append(
                            {
                                "group": group,
                                "file": str(
                                    path.relative_to(
                                        PROJECT
                                    )
                                ),
                                "sheet": ws.title,
                                "cell": cell.coordinate,
                                "formula": value,
                                "number_format": cell.number_format,
                                "labels": labels,
                                "kind": kind,
                                "numerator": str(
                                    info[
                                        "numerator"
                                    ]
                                ),
                                "denominator": str(
                                    info[
                                        "denominator"
                                    ]
                                ),
                                "matches": matches,
                                "status": status,
                            }
                        )
        finally:
            wb.close()

    return rows


def main() -> None:
    print("=" * 142)
    print(
        "BÀI 13B-11.15.2.4.1 - "
        "LÀM SẠCH MA TRẬN CÔNG THỨC TỶ LỆ 4 NHÓM"
    )
    print("=" * 142)
    print()
    print("SỬA CÁC HẠN CHẾ CỦA BÀI 15.2.4:")
    print(
        " - Không còn coi cùng tọa độ ô ở biểu khác là cùng logic Python."
    )
    print(
        " - K8/J8*100 được tách đúng: tử số K8, mẫu số J8."
    )
    print(
        " - CMC (chống mù chữ) được gom vào nhóm Xóa mù chữ."
    )
    print(
        " - Đọc nhiều nhãn/header xung quanh thay vì lấy một ô số gần nhất."
    )
    print(
        " - Chỉ đọc file mẫu chính thức và source đúng nhóm."
    )
    print()
    print("AN TOÀN:")
    print(
        " - KHÔNG sửa source."
    )
    print(
        " - KHÔNG sửa database."
    )
    print(
        " - KHÔNG sửa Excel."
    )
    print()

    rows = matrix_rows()

    by_group = defaultdict(
        list
    )

    for row in rows:
        by_group[
            row[
                "group"
            ]
        ].append(
            row
        )

    report = []

    report.append(
        "=" * 142
        + "\n"
    )
    report.append(
        "BÀI 13B-11.15.2.4.1 - MA TRẬN SẠCH TỶ LỆ/TỶ SỐ\n"
    )
    report.append(
        "=" * 142
        + "\n"
    )
    report.append(
        f"Project: {PROJECT}\n"
    )
    report.append(
        f"Thời điểm: {datetime.now():%d/%m/%Y %H:%M:%S}\n\n"
    )

    report.append(
        "NGUYÊN TẮC\n"
    )
    report.append(
        "-" * 142
        + "\n"
    )
    report.append(
        "1. Excel chính thức là chuẩn công thức đầu tiên.\n"
    )
    report.append(
        "2. Python chỉ được coi là đã nối khi dấu vết nằm trong source đúng nhóm báo cáo.\n"
    )
    report.append(
        "3. %: tử số / mẫu số * 100; nếu mẫu số = 0/chưa có thì để trống.\n"
    )
    report.append(
        "4. RATIO: tử số / mẫu số; không nhân 100.\n"
    )
    report.append(
        "5. CMC được quản lý như một phân nhóm của Xóa mù chữ.\n"
    )
    report.append(
        "6. Đạt/Không đạt xử lý ở bước riêng sau khi đủ tỷ lệ nguồn.\n"
    )

    for group in (
        "MẦM NON",
        "TIỂU HỌC",
        "THCS",
        "XÓA MÙ CHỮ",
        "CHƯA PHÂN NHÓM",
    ):
        items = by_group.get(
            group,
            [],
        )

        if not items:
            continue

        report.append(
            "\n\n"
            + "=" * 142
            + "\n"
        )
        report.append(
            f"NHÓM: {group}\n"
        )
        report.append(
            "=" * 142
            + "\n"
        )

        kind_counter = Counter(
            item[
                "kind"
            ]
            for item in items
        )

        status_counter = Counter(
            item[
                "status"
            ]
            for item in items
        )

        report.append(
            f"Tổng phép chia: {len(items)}\n"
        )

        for key, value in sorted(
            kind_counter.items()
        ):
            report.append(
                f" - {key}: {value}\n"
            )

        report.append(
            "Trạng thái:\n"
        )

        for key, value in sorted(
            status_counter.items()
        ):
            report.append(
                f" - {key}: {value}\n"
            )

        for index, item in enumerate(
            items,
            start=1,
        ):
            report.append(
                f"\n[{index}] {item['file']} | "
                f"{item['sheet']}!{item['cell']}\n"
            )
            report.append(
                f"    Loại      : {item['kind']}\n"
            )
            report.append(
                f"    Công thức : {item['formula']}\n"
            )
            report.append(
                f"    Tử số     : {item['numerator'] or '(chưa tách)'}\n"
            )
            report.append(
                f"    Mẫu số    : {item['denominator'] or '(chưa tách)'}\n"
            )
            report.append(
                f"    Định dạng : {item['number_format']}\n"
            )
            report.append(
                "    Ngữ cảnh   : "
                + (
                    " | ".join(
                        item[
                            "labels"
                        ]
                    )
                    if item[
                        "labels"
                    ]
                    else "(không lấy được nhãn)"
                )
                + "\n"
            )
            report.append(
                f"    Trạng thái: {item['status']}\n"
            )

            if item[
                "matches"
            ]:
                report.append(
                    "    Python cùng nhóm:\n"
                )

                for match in item[
                    "matches"
                ]:
                    report.append(
                        f"      - {match}\n"
                    )
            else:
                report.append(
                    "    Python cùng nhóm: chưa phát hiện\n"
                )

    report.append(
        "\n\n"
        + "=" * 142
        + "\n"
    )
    report.append(
        "ĐỀ XUẤT BÀI 15.2.4.2\n"
    )
    report.append(
        "=" * 142
        + "\n"
    )
    report.append(
        "A. Nhóm ĐỦ_CT_EXCEL_CHƯA_THẤY_PYTHON: có thể chuyển sang bước nối Python sau khi xác nhận nguồn DB cho tử/mẫu.\n"
    )
    report.append(
        "B. Nhóm CÓ_DẤU_VẾT_PYTHON_CÙNG_NHÓM: phải so sánh đúng tử số/mẫu số, không chỉ kiểm tra đã ghi ô.\n"
    )
    report.append(
        "C. Nhóm CẦN_XÁC_MINH_NGHIỆP_VỤ: không sửa cho đến khi xác định được ý nghĩa cột từ header/mẫu.\n"
    )
    report.append(
        "D. Sau đó mới tạo bộ tính tỷ lệ dùng chung và nối kiểm tra chất lượng Bài 15.3.\n"
    )

    OUT.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    OUT.write_text(
        "".join(
            report
        ),
        encoding="utf-8",
    )

    print("KẾT QUẢ:")

    for group in (
        "MẦM NON",
        "TIỂU HỌC",
        "THCS",
        "XÓA MÙ CHỮ",
    ):
        items = by_group.get(
            group,
            [],
        )

        print(
            f" - {group}: {len(items)} phép chia"
        )

    print()
    print(
        "Source/database/Excel: KHÔNG THAY ĐỔI."
    )
    print(
        "Ma trận sạch:",
        OUT,
    )
    print()
    print("=" * 142)
    print(
        "BÀI 13B-11.15.2.4.1 THÀNH CÔNG"
    )
    print("=" * 142)


if __name__ == "__main__":
    main()
