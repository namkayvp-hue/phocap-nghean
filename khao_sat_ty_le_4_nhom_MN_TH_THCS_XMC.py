from __future__ import annotations

import ast
import os
import re
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path


PROJECT = Path(
    os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")
).resolve()

APP = PROJECT / "app"
EXPORTS = PROJECT / "exports"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
OUT = (
    EXPORTS
    / f"bao_cao_khao_sat_ty_le_4_nhom_MN_TH_THCS_XMC_{STAMP}.txt"
)

GROUPS = {
    "MẦM NON": {
        "source_keywords": (
            "pcgd_mn",
            "mn_official",
            "mn-01",
            "pcgdmn",
            "preschool",
        ),
        "report_codes": (
            "MN-01",
            "MN_01",
            "PCGDMN",
            "MN01",
        ),
        "xlsx_keywords": (
            "MN",
            "PCGDMN",
            "MAM NON",
            "MẦM NON",
        ),
    },
    "TIỂU HỌC": {
        "source_keywords": (
            "pcgd_xmc",
            "primary",
            "tieu_hoc",
            "th_01",
            "pcgd_th",
        ),
        "report_codes": (
            "PCGD_TH_",
            "TH_01_",
            "TIEU_HOC",
        ),
        "xlsx_keywords": (
            "PCGD_TH",
            "TIEU HOC",
            "TIỂU HỌC",
            "_TH_",
        ),
    },
    "THCS": {
        "source_keywords": (
            "pcgd_xmc",
            "secondary",
            "thcs",
            "pcgd_thcs",
        ),
        "report_codes": (
            "PCGD_THCS_",
            "THCS_01_",
            "THCS",
        ),
        "xlsx_keywords": (
            "THCS",
            "PCGD_THCS",
        ),
    },
    "XÓA MÙ CHỮ": {
        "source_keywords": (
            "pcgd_xmc",
            "xmc",
            "literacy",
            "xoa_mu_chu",
        ),
        "report_codes": (
            "PCGD_XMC_",
            "XMC",
            "LITERACY",
        ),
        "xlsx_keywords": (
            "XMC",
            "XOA MU CHU",
            "XÓA MÙ CHỮ",
        ),
    },
}

FORMULA_TOKENS = (
    "_percent",
    "_pct",
    "percent",
    "percentage",
    "ratio",
    "ty_le",
    "ti_le",
    "tỷ lệ",
    "tỉ lệ",
    "* 100",
    "*100",
    "/ 100",
    "/100",
    "number_format",
)

REPORT_SOURCE_HINTS = (
    "report",
    "bao_cao",
    "pcgd",
    "xmc",
    "official",
    "builder",
    "structured",
)

NS = {
    "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
}


def normalize(text: str) -> str:
    return (
        text.upper()
        .replace("Đ", "D")
        .replace("Ầ", "A")
        .replace("Ẩ", "A")
        .replace("Ẫ", "A")
        .replace("Ậ", "A")
        .replace("Ấ", "A")
        .replace("Á", "A")
        .replace("À", "A")
        .replace("Ả", "A")
        .replace("Ã", "A")
        .replace("Ạ", "A")
        .replace("Ắ", "A")
        .replace("Ằ", "A")
        .replace("Ẳ", "A")
        .replace("Ẵ", "A")
        .replace("Ặ", "A")
        .replace("É", "E")
        .replace("È", "E")
        .replace("Ẻ", "E")
        .replace("Ẽ", "E")
        .replace("Ẹ", "E")
        .replace("Ê", "E")
        .replace("Ế", "E")
        .replace("Ề", "E")
        .replace("Ể", "E")
        .replace("Ễ", "E")
        .replace("Ệ", "E")
        .replace("Í", "I")
        .replace("Ì", "I")
        .replace("Ỉ", "I")
        .replace("Ĩ", "I")
        .replace("Ị", "I")
        .replace("Ó", "O")
        .replace("Ò", "O")
        .replace("Ỏ", "O")
        .replace("Õ", "O")
        .replace("Ọ", "O")
        .replace("Ô", "O")
        .replace("Ố", "O")
        .replace("Ồ", "O")
        .replace("Ổ", "O")
        .replace("Ỗ", "O")
        .replace("Ộ", "O")
        .replace("Ơ", "O")
        .replace("Ớ", "O")
        .replace("Ờ", "O")
        .replace("Ở", "O")
        .replace("Ỡ", "O")
        .replace("Ợ", "O")
        .replace("Ú", "U")
        .replace("Ù", "U")
        .replace("Ủ", "U")
        .replace("Ũ", "U")
        .replace("Ụ", "U")
        .replace("Ư", "U")
        .replace("Ứ", "U")
        .replace("Ừ", "U")
        .replace("Ử", "U")
        .replace("Ữ", "U")
        .replace("Ự", "U")
        .replace("Ý", "Y")
        .replace("Ỳ", "Y")
        .replace("Ỷ", "Y")
        .replace("Ỹ", "Y")
        .replace("Ỵ", "Y")
    )


def read_text(path: Path) -> str:
    try:
        return path.read_text(
            encoding="utf-8-sig",
            errors="strict",
        )
    except UnicodeDecodeError:
        return path.read_text(
            encoding="utf-8",
            errors="replace",
        )


def is_backup(path: Path) -> bool:
    low = str(path).lower()

    return any(
        token in low
        for token in (
            "__pycache__",
            "backup",
            "truoc_sua",
            ".bak",
            "_old",
            "_copy",
        )
    )


def is_report_source(path: Path) -> bool:
    if is_backup(path):
        return False

    low = str(
        path.relative_to(PROJECT)
    ).lower()

    return any(
        hint in low
        for hint in REPORT_SOURCE_HINTS
    )


def detect_groups_from_text(
    text: str,
    path_text: str = "",
) -> set[str]:
    joined = normalize(
        path_text + "\n" + text
    )

    groups = set()

    for group_name, cfg in GROUPS.items():
        for token in (
            *cfg["source_keywords"],
            *cfg["report_codes"],
        ):
            if normalize(token) in joined:
                groups.add(group_name)
                break

    return groups


def extract_source_formula_rows(
    source: str,
) -> list[tuple[int, str]]:
    rows = []

    for number, line in enumerate(
        source.splitlines(),
        start=1,
    ):
        low = line.lower()

        if any(
            token.lower() in low
            for token in FORMULA_TOKENS
        ):
            rows.append(
                (
                    number,
                    line.rstrip(),
                )
            )

    return rows


def extract_percent_functions(
    source: str,
) -> list[tuple[str, int, int]]:
    result = []

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return result

    lines = source.splitlines()

    for node in ast.walk(tree):
        if not isinstance(
            node,
            (
                ast.FunctionDef,
                ast.AsyncFunctionDef,
            ),
        ):
            continue

        start = int(node.lineno)
        end = int(
            node.end_lineno
            or node.lineno
        )

        body = "\n".join(
            lines[start - 1:end]
        ).lower()

        if any(
            token.lower() in body
            for token in FORMULA_TOKENS
        ):
            result.append(
                (
                    node.name,
                    start,
                    end,
                )
            )

    return result


def xlsx_sheet_map(
    zf: zipfile.ZipFile,
) -> list[tuple[str, str]]:
    workbook = ET.fromstring(
        zf.read(
            "xl/workbook.xml"
        )
    )

    rels = ET.fromstring(
        zf.read(
            "xl/_rels/workbook.xml.rels"
        )
    )

    rel_map = {}

    for rel in rels:
        rel_map[
            rel.attrib.get("Id")
        ] = rel.attrib.get("Target")

    result = []

    for sheet in workbook.findall(
        "main:sheets/main:sheet",
        NS,
    ):
        name = sheet.attrib.get(
            "name",
            "",
        )

        rid = sheet.attrib.get(
            "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
        )

        target = rel_map.get(
            rid,
            "",
        )

        if not target:
            continue

        if target.startswith("/"):
            xml_path = target.lstrip("/")
        elif target.startswith("xl/"):
            xml_path = target
        else:
            xml_path = "xl/" + target.lstrip("/")

        result.append(
            (
                name,
                xml_path,
            )
        )

    return result


def extract_xlsx_formulas(
    path: Path,
) -> list[tuple[str, str, str]]:
    rows = []

    try:
        with zipfile.ZipFile(
            path,
            "r",
        ) as zf:
            names = set(
                zf.namelist()
            )

            if (
                "xl/workbook.xml" not in names
                or "xl/_rels/workbook.xml.rels" not in names
            ):
                return rows

            for sheet_name, xml_path in xlsx_sheet_map(
                zf
            ):
                if xml_path not in names:
                    continue

                root = ET.fromstring(
                    zf.read(
                        xml_path
                    )
                )

                for cell in root.findall(
                    ".//main:c",
                    NS,
                ):
                    formula = cell.find(
                        "main:f",
                        NS,
                    )

                    if (
                        formula is None
                        or formula.text is None
                    ):
                        continue

                    cell_ref = cell.attrib.get(
                        "r",
                        "",
                    )

                    rows.append(
                        (
                            sheet_name,
                            cell_ref,
                            formula.text,
                        )
                    )

    except (
        zipfile.BadZipFile,
        KeyError,
        ET.ParseError,
        OSError,
    ):
        return rows

    return rows


def detect_xlsx_groups(
    path: Path,
    formula_rows: list[tuple[str, str, str]],
) -> set[str]:
    text = normalize(
        path.name
        + "\n"
        + "\n".join(
            row[0]
            for row in formula_rows
        )
    )

    groups = set()

    for group_name, cfg in GROUPS.items():
        if any(
            normalize(token) in text
            for token in cfg["xlsx_keywords"]
        ):
            groups.add(
                group_name
            )

    return groups


def main() -> None:
    print("=" * 132)
    print(
        "KHẢO SÁT CHỈ ĐỌC - "
        "TỶ LỆ % CHO 4 NHÓM BÁO CÁO: "
        "MẦM NON / TIỂU HỌC / THCS / XÓA MÙ CHỮ"
    )
    print("=" * 132)
    print()
    print("KIỂM TRA:")
    print(
        " - Source Python/HTML có logic %."
    )
    print(
        " - Hàm _percent/_pct/ratio hoặc phép tính *100."
    )
    print(
        " - Công thức có sẵn trong file Excel mẫu."
    )
    print(
        " - Phân loại theo 4 nhóm báo cáo."
    )
    print()
    print("AN TOÀN:")
    print(
        " - Không sửa source."
    )
    print(
        " - Không sửa database."
    )
    print(
        " - Không sửa file Excel."
    )
    print()

    if not APP.exists():
        raise SystemExit(
            f"Không tìm thấy: {APP}"
        )

    findings = {
        group: {
            "sources": [],
            "xlsx": [],
        }
        for group in GROUPS
    }

    # ---------------------------------------------------------
    # 1. SOURCE
    # ---------------------------------------------------------
    source_files = (
        list(APP.rglob("*.py"))
        + list(APP.rglob("*.html"))
    )

    for path in sorted(source_files):
        if not is_report_source(
            path
        ):
            continue

        source = read_text(
            path
        )

        groups = detect_groups_from_text(
            source,
            str(
                path.relative_to(
                    PROJECT
                )
            ),
        )

        if not groups:
            continue

        formula_rows = extract_source_formula_rows(
            source
        )

        funcs = (
            extract_percent_functions(
                source
            )
            if path.suffix.lower() == ".py"
            else []
        )

        if (
            not formula_rows
            and not funcs
        ):
            continue

        rel = str(
            path.relative_to(
                PROJECT
            )
        )

        for group in groups:
            findings[
                group
            ][
                "sources"
            ].append(
                {
                    "file": rel,
                    "formula_rows": formula_rows,
                    "functions": funcs,
                }
            )

    # ---------------------------------------------------------
    # 2. EXCEL
    # ---------------------------------------------------------
    xlsx_files = [
        path
        for path in PROJECT.rglob("*.xlsx")
        if not is_backup(path)
    ]

    for path in sorted(
        xlsx_files
    ):
        formulas = extract_xlsx_formulas(
            path
        )

        if not formulas:
            continue

        groups = detect_xlsx_groups(
            path,
            formulas,
        )

        if not groups:
            continue

        rel = str(
            path.relative_to(
                PROJECT
            )
        )

        for group in groups:
            findings[
                group
            ][
                "xlsx"
            ].append(
                {
                    "file": rel,
                    "formulas": formulas,
                }
            )

    # ---------------------------------------------------------
    # 3. REPORT
    # ---------------------------------------------------------
    lines = []

    lines.append(
        "=" * 132
        + "\n"
    )
    lines.append(
        "KHẢO SÁT TỶ LỆ % - 4 NHÓM BÁO CÁO\n"
    )
    lines.append(
        "=" * 132
        + "\n"
    )
    lines.append(
        f"Project: {PROJECT}\n"
    )
    lines.append(
        f"Thời điểm: {datetime.now():%d/%m/%Y %H:%M:%S}\n"
    )
    lines.append(
        "\n"
    )

    for group_name in (
        "MẦM NON",
        "TIỂU HỌC",
        "THCS",
        "XÓA MÙ CHỮ",
    ):
        data = findings[
            group_name
        ]

        lines.append(
            "\n"
            + "=" * 132
            + "\n"
        )
        lines.append(
            f"NHÓM: {group_name}\n"
        )
        lines.append(
            "=" * 132
            + "\n"
        )

        lines.append(
            f"Source có dấu vết tỷ lệ: "
            f"{len(data['sources'])} file\n"
        )
        lines.append(
            f"Excel có công thức: "
            f"{len(data['xlsx'])} file\n"
        )

        lines.append(
            "\nI. SOURCE ĐANG TÍNH TỶ LỆ\n"
        )
        lines.append(
            "-" * 132
            + "\n"
        )

        if not data[
            "sources"
        ]:
            lines.append(
                "CHƯA PHÁT HIỆN source có logic tỷ lệ.\n"
            )

        for item in data[
            "sources"
        ]:
            lines.append(
                f"\nFILE: {item['file']}\n"
            )

            if item[
                "functions"
            ]:
                lines.append(
                    "Hàm có logic tỷ lệ:\n"
                )

                for (
                    name,
                    start,
                    end,
                ) in item[
                    "functions"
                ]:
                    lines.append(
                        f" - {name}: dòng {start}-{end}\n"
                    )

            if item[
                "formula_rows"
            ]:
                lines.append(
                    "Dòng có dấu vết công thức/tỷ lệ:\n"
                )

                for (
                    number,
                    text,
                ) in item[
                    "formula_rows"
                ][
                    :180
                ]:
                    lines.append(
                        f" {number:6}: {text}\n"
                    )

                extra = (
                    len(
                        item[
                            "formula_rows"
                        ]
                    )
                    - 180
                )

                if extra > 0:
                    lines.append(
                        f" ... còn {extra} dòng khác\n"
                    )

        lines.append(
            "\nII. CÔNG THỨC TRONG FILE EXCEL\n"
        )
        lines.append(
            "-" * 132
            + "\n"
        )

        if not data[
            "xlsx"
        ]:
            lines.append(
                "Không phát hiện file Excel phù hợp có công thức.\n"
            )

        for item in data[
            "xlsx"
        ]:
            lines.append(
                f"\nFILE: {item['file']}\n"
            )

            for (
                sheet,
                cell,
                formula,
            ) in item[
                "formulas"
            ][
                :250
            ]:
                lines.append(
                    f" - {sheet}!{cell} = {formula}\n"
                )

            extra = (
                len(
                    item[
                        "formulas"
                    ]
                )
                - 250
            )

            if extra > 0:
                lines.append(
                    f" ... còn {extra} công thức khác\n"
                )

        lines.append(
            "\nIII. KẾT LUẬN TẠM THỜI\n"
        )
        lines.append(
            "-" * 132
            + "\n"
        )

        if (
            data[
                "sources"
            ]
            and data[
                "xlsx"
            ]
        ):
            lines.append(
                "Có cả logic Python và công thức Excel. "
                "Cần đối chiếu tử số/mẫu số để xác nhận đúng nghiệp vụ.\n"
            )
        elif data[
            "sources"
        ]:
            lines.append(
                "Đã có logic Python; chưa tìm thấy công thức mẫu Excel tương ứng "
                "hoặc mẫu không chứa công thức.\n"
            )
        elif data[
            "xlsx"
        ]:
            lines.append(
                "Mẫu Excel có công thức nhưng chưa phát hiện logic Python tương ứng. "
                "Cần ưu tiên nối công thức vào phần mềm.\n"
            )
        else:
            lines.append(
                "Chưa có đủ bằng chứng về công thức tỷ lệ. "
                "Cần cung cấp công thức chính thức.\n"
            )

    lines.append(
        "\n\n"
        + "=" * 132
        + "\n"
    )
    lines.append(
        "NGUYÊN TẮC TRIỂN KHAI CHUNG CHO 4 NHÓM\n"
    )
    lines.append(
        "=" * 132
        + "\n"
    )
    lines.append(
        "1. Tỷ lệ % là dữ liệu tự tính, không cho nhập tay.\n"
    )
    lines.append(
        "2. Mỗi chỉ tiêu phải xác định rõ TỬ SỐ và MẪU SỐ.\n"
    )
    lines.append(
        "3. Mẫu số chưa có hoặc bằng 0: để trống, không tự suy đoán thành 0%.\n"
    )
    lines.append(
        "4. Dữ liệu tổng hợp phải lấy từ nguồn chi tiết đã nhập trong hệ thống.\n"
    )
    lines.append(
        "5. Công thức Đạt/Không đạt phải tách khỏi dữ liệu nhập và tính theo tiêu chí pháp lý.\n"
    )
    lines.append(
        "6. Sau khảo sát, cần lập ma trận: "
        "Biểu -> Chỉ tiêu -> Tử số -> Mẫu số -> Công thức -> Làm tròn -> Nguồn dữ liệu.\n"
    )

    OUT.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    OUT.write_text(
        "".join(
            lines
        ),
        encoding="utf-8",
    )

    print(
        "Khảo sát hoàn tất."
    )
    print(
        "Source / database / Excel: KHÔNG THAY ĐỔI."
    )
    print(
        "Báo cáo:",
        OUT,
    )
    print()
    print("=" * 132)
    print(
        "KHẢO SÁT TỶ LỆ 4 NHÓM "
        "MẦM NON / TIỂU HỌC / THCS / XÓA MÙ CHỮ THÀNH CÔNG"
    )
    print("=" * 132)


if __name__ == "__main__":
    main()
