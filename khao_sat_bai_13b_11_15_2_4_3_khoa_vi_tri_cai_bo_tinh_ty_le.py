from __future__ import annotations

import ast
import os
import re
import sqlite3
from datetime import datetime
from pathlib import Path


PROJECT = Path(
    os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")
).resolve()

APP = PROJECT / "app"
DB = PROJECT / "data" / "phocap.db"
EXPORTS = PROJECT / "exports"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
OUT = (
    EXPORTS
    / f"khao_sat_vi_tri_cai_bo_tinh_ty_le_bai_13b_11_15_2_4_3_{STAMP}.txt"
)

TARGET_FILES = (
    APP / "pcgd_mn_report_builders_v1.py",
    APP / "pcgd_xmc_report_builders_v1.py",
    APP / "routers" / "report_center.py",
    APP / "routers" / "pcgdmn_template_report.py",
    APP / "routers" / "mn_official_reports.py",
)

TARGET_FUNCTION_HINTS = {
    "MẦM NON - M1": (
        "_fill_mn_m1",
        "mn_m1",
    ),
    "MẦM NON - MN02": (
        "_fill_mn02",
        "mn02",
    ),
    "TIỂU HỌC - TH_M1": (
        "_build_primary_th_m1_workbook",
        "th_m1",
    ),
    "TIỂU HỌC - TH_02": (
        "th02",
        "th_02",
    ),
    "TIỂU HỌC - CSVC": (
        "th_01_csvc",
        "csvc",
    ),
    "THCS - M1": (
        "_build_thcs_m1",
        "thcs_m1",
    ),
    "THCS - M2": (
        "_build_thcs_m2",
        "thcs_m2",
    ),
    "THCS - M5": (
        "thcs_m5",
    ),
    "THCS - TK": (
        "_build_thcs_tk",
        "thcs_tk",
    ),
    "THCS - CSVC": (
        "thcs_csvc",
    ),
    "XMC - CMC1": (
        "_build_cmc1",
        "cmc1",
        "cmc_1",
    ),
    "XMC - XMC3": (
        "_build_xmc3",
        "xmc3",
        "xmc_3",
    ),
    "XMC - XMC4": (
        "_build_xmc4",
        "xmc4",
        "xmc_4",
    ),
}

IMPORTANT_FIELDS = (
    "learning_status",
    "study_location_scope",
    "is_repeating_grade",
    "current_education_program",
    "completed_primary_program",
    "completed_lower_secondary_program",
    "post_lower_secondary_path",
    "is_literacy_target",
    "literacy_status",
    "completed_grade_3",
    "completed_grade_5",
    "completed_preschool_by_age",
    "completed_preschool_5",
    "attends_two_sessions_per_day",
    "prepared_vietnamese",
    "disability_type",
    "is_disabled",
    "disability",
    "school_id",
    "class_id",
    "school_name_reported",
    "class_name_reported",
)

IMPORTANT_TABLE_HINTS = (
    "survey_person_year",
    "survey_person",
    "staff",
    "teacher",
    "facility",
    "csvc",
    "class",
    "school_site",
    "finance",
    "structured_report",
)

CELL_PATTERNS = (
    "G40",
    "G41",
    "G42",
    "G43",
    "G44",
    "H39",
    "H40",
    "H41",
    "E14",
    "J14",
    "M14",
    "Q14",
    "V14",
    "E15",
    "J15",
    "M15",
    "Q15",
    "V15",
    "L21",
    "L22",
    "L23",
    "O8",
    "S9",
    "S10",
    "S20",
    "S31",
    "S57",
    "E8",
    "G8",
    "J8",
    "L8",
    "Q8",
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


def function_records(
    path: Path,
) -> list[dict]:
    source = read_text(
        path
    )

    try:
        tree = ast.parse(
            source
        )
    except SyntaxError as exc:
        return [
            {
                "error": (
                    f"AST lỗi {path}: {exc}"
                )
            }
        ]

    lines = source.splitlines()

    result = []

    for node in ast.walk(tree):
        if not isinstance(
            node,
            (
                ast.FunctionDef,
                ast.AsyncFunctionDef,
            ),
        ):
            continue

        start = int(
            node.lineno
        )

        end = int(
            node.end_lineno
            or node.lineno
        )

        body_lines = lines[
            start - 1:
            end
        ]

        result.append(
            {
                "file": str(
                    path.relative_to(
                        PROJECT
                    )
                ),
                "name": node.name,
                "start": start,
                "end": end,
                "lines": body_lines,
                "body": "\n".join(
                    body_lines
                ),
            }
        )

    return result


def relevance(
    record: dict,
    hints: tuple[str, ...],
) -> int:
    name = str(
        record.get(
            "name",
            "",
        )
    ).lower()

    body = str(
        record.get(
            "body",
            "",
        )
    ).lower()

    score = 0

    for hint in hints:
        h = hint.lower()

        if h in name:
            score += 100

        if h in body:
            score += 20

    return score


def key_lines(
    record: dict,
) -> list[tuple[int, str]]:
    rows = []

    tokens = (
        'load_workbook',
        'return ',
        'save(',
        'worksheet',
        'worksheets',
        'ws =',
        'ws[',
        'wb[',
        '_percent(',
        '_ratio(',
        '_safe_percent(',
        '_safe_ratio(',
        '_th_m1_percent(',
        'survey_person_year',
        'completed_primary_program',
        'completed_lower_secondary_program',
        'post_lower_secondary_path',
        'is_literacy_target',
        'literacy_status',
        'completed_grade_3',
        'completed_grade_5',
        'is_disabled',
        'disability',
    )

    for offset, line in enumerate(
        record[
            "lines"
        ],
        start=record[
            "start"
        ],
    ):
        low = line.lower()

        if any(
            token.lower() in low
            for token in tokens
        ):
            rows.append(
                (
                    offset,
                    line.rstrip(),
                )
            )
            continue

        if any(
            f'"{cell}"'.lower() in low
            or f"'{cell}'".lower() in low
            for cell in CELL_PATTERNS
        ):
            rows.append(
                (
                    offset,
                    line.rstrip(),
                )
            )

    return rows


def tail_lines(
    record: dict,
    count: int = 35,
) -> list[tuple[int, str]]:
    lines = record[
        "lines"
    ]

    start_index = max(
        0,
        len(lines) - count,
    )

    start_line = (
        record[
            "start"
        ]
        + start_index
    )

    return [
        (
            start_line + idx,
            line.rstrip(),
        )
        for idx, line in enumerate(
            lines[
                start_index:
            ]
        )
    ]


def schema_report() -> list[str]:
    rows = []

    if not DB.exists():
        return [
            f"Không tìm thấy DB: {DB}"
        ]

    conn = sqlite3.connect(
        str(DB)
    )

    try:
        integrity = conn.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]

        fk = conn.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()

        rows.append(
            f"integrity_check: {integrity}"
        )
        rows.append(
            f"foreign_key_check: {len(fk)} lỗi"
        )

        tables = [
            row[0]
            for row in conn.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type='table'
                ORDER BY name
                """
            ).fetchall()
        ]

        rows.append("")
        rows.append(
            "Bảng/cột liên quan:"
        )

        for table in tables:
            low = table.lower()

            if not any(
                hint in low
                for hint in IMPORTANT_TABLE_HINTS
            ):
                continue

            info = conn.execute(
                f'PRAGMA table_info("{table}")'
            ).fetchall()

            columns = [
                str(
                    row[1]
                )
                for row in info
            ]

            selected = [
                col
                for col in columns
                if (
                    col in IMPORTANT_FIELDS
                    or any(
                        token in col.lower()
                        for token in (
                            "grade",
                            "class",
                            "school",
                            "disabled",
                            "disability",
                            "literacy",
                            "complete",
                            "program",
                            "status",
                            "room",
                            "teacher",
                            "staff",
                            "facility",
                        )
                    )
                )
            ]

            if not selected:
                continue

            rows.append(
                f" - {table}:"
            )

            for col in selected:
                rows.append(
                    f"    • {col}"
                )

    finally:
        conn.close()

    return rows


def source_field_locations(
    all_records: list[dict],
) -> list[str]:
    rows = []

    for field in IMPORTANT_FIELDS:
        hits = []

        for record in all_records:
            if "error" in record:
                continue

            for offset, line in enumerate(
                record[
                    "lines"
                ],
                start=record[
                    "start"
                ],
            ):
                if re.search(
                    rf"\b{re.escape(field)}\b",
                    line,
                ):
                    hits.append(
                        (
                            record[
                                "file"
                            ],
                            record[
                                "name"
                            ],
                            offset,
                            line.strip(),
                        )
                    )

        if not hits:
            continue

        rows.append(
            f"\nFIELD: {field}"
        )

        for (
            file_name,
            func_name,
            line_no,
            text,
        ) in hits[:18]:
            rows.append(
                f" - {file_name}:{line_no} "
                f"[{func_name}] {text}"
            )

        if len(hits) > 18:
            rows.append(
                f" - ... còn {len(hits) - 18} chỗ khác"
            )

    return rows


def main() -> None:
    print("=" * 148)
    print(
        "BÀI 13B-11.15.2.4.3 - "
        "KHÓA VỊ TRÍ CÀI BỘ TÍNH TỶ LỆ CHUNG"
    )
    print("=" * 148)
    print()
    print("MỤC TIÊU:")
    print(
        " - Lấy đúng function builder đang xuất từng biểu."
    )
    print(
        " - Xem đoạn cuối function để biết chèn bộ tính ở đâu."
    )
    print(
        " - Xem các assignment ô nguồn/ô tỷ lệ hiện có."
    )
    print(
        " - Xác nhận field DB cho TH / THCS / XMC / khuyết tật."
    )
    print(
        " - Chuẩn bị bộ cài sau, KHÔNG sửa gì ở bước này."
    )
    print()

    all_records = []

    for path in TARGET_FILES:
        if not path.exists():
            continue

        all_records.extend(
            function_records(
                path
            )
        )

    report = []

    report.append(
        "=" * 148
        + "\n"
    )
    report.append(
        "BÀI 13B-11.15.2.4.3 - KHÓA VỊ TRÍ CÀI BỘ TÍNH TỶ LỆ CHUNG\n"
    )
    report.append(
        "=" * 148
        + "\n"
    )
    report.append(
        f"Project: {PROJECT}\n"
    )
    report.append(
        f"Thời điểm: {datetime.now():%d/%m/%Y %H:%M:%S}\n"
    )
    report.append(
        f"Số function AST đã đọc: "
        f"{sum(1 for r in all_records if 'error' not in r)}\n"
    )
    report.append(
        "\n"
    )

    for title, hints in TARGET_FUNCTION_HINTS.items():
        candidates = []

        for record in all_records:
            if "error" in record:
                continue

            score = relevance(
                record,
                hints,
            )

            if score > 0:
                candidates.append(
                    (
                        score,
                        record,
                    )
                )

        candidates.sort(
            key=lambda item: item[0],
            reverse=True,
        )

        report.append(
            "\n"
            + "=" * 148
            + "\n"
        )
        report.append(
            f"{title}\n"
        )
        report.append(
            "=" * 148
            + "\n"
        )

        if not candidates:
            report.append(
                "KHÔNG TÌM THẤY FUNCTION ỨNG VIÊN.\n"
            )
            continue

        # Chỉ lấy 3 ứng viên tốt nhất để báo cáo gọn.
        for rank, (
            score,
            record,
        ) in enumerate(
            candidates[:3],
            start=1,
        ):
            report.append(
                f"\nỨng viên #{rank} - điểm {score}\n"
            )
            report.append(
                f"Function: {record['file']}::{record['name']} "
                f"(dòng {record['start']}-{record['end']})\n"
            )

            report.append(
                "\nDòng trọng tâm:\n"
            )

            important = key_lines(
                record
            )

            if important:
                for line_no, text in important[:180]:
                    report.append(
                        f"{line_no:6}: {text}\n"
                    )
            else:
                report.append(
                    " - Không có dòng trọng tâm theo bộ lọc.\n"
                )

            report.append(
                "\n35 dòng cuối function:\n"
            )

            for line_no, text in tail_lines(
                record,
                35,
            ):
                report.append(
                    f"{line_no:6}: {text}\n"
                )

    report.append(
        "\n\n"
        + "=" * 148
        + "\n"
    )
    report.append(
        "SCHEMA DATABASE LIÊN QUAN\n"
    )
    report.append(
        "=" * 148
        + "\n"
    )

    for row in schema_report():
        report.append(
            row + "\n"
        )

    report.append(
        "\n\n"
        + "=" * 148
        + "\n"
    )
    report.append(
        "DẤU VẾT FIELD TRONG SOURCE BUILDER\n"
    )
    report.append(
        "=" * 148
        + "\n"
    )

    for row in source_field_locations(
        all_records
    ):
        report.append(
            row + "\n"
        )

    report.append(
        "\n\n"
        + "=" * 148
        + "\n"
    )
    report.append(
        "KẾT LUẬN DÙNG CHO BỘ CÀI TIẾP THEO\n"
    )
    report.append(
        "=" * 148
        + "\n"
    )
    report.append(
        "1. Chỉ chèn bộ tính sau khi các ô nguồn đã được Python ghi xong.\n"
    )
    report.append(
        "2. PERCENT: numerator/denominator*100; denominator <= 0 hoặc None -> None.\n"
    )
    report.append(
        "3. RATIO: numerator/denominator; denominator <= 0 hoặc None -> None.\n"
    )
    report.append(
        "4. Không dùng Excel recalculation làm điều kiện bắt buộc.\n"
    )
    report.append(
        "5. Không sửa Đạt/Không đạt ở bước tỷ lệ.\n"
    )
    report.append(
        "6. TH_M1 G44 là khoảng trống xác nhận; chỉ sửa khi thấy rõ K10/P10/F44 đã được gán trước G44.\n"
    )
    report.append(
        "7. XMC/CMC chỉ nối khi xác nhận builder thật sự đang tạo các ô nguồn tương ứng.\n"
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

    print(
        "Khảo sát hoàn tất."
    )
    print(
        "Source/database/Excel: KHÔNG THAY ĐỔI."
    )
    print(
        "Báo cáo:",
        OUT,
    )
    print()
    print("=" * 148)
    print(
        "BÀI 13B-11.15.2.4.3 KHẢO SÁT THÀNH CÔNG"
    )
    print("=" * 148)


if __name__ == "__main__":
    main()
