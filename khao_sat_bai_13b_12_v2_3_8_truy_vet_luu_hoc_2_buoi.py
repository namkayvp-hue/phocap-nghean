# -*- coding: utf-8 -*-
from __future__ import annotations

import ast
import re
import sqlite3
from datetime import datetime
from pathlib import Path

PROJECT = Path(r"C:\PhoCap")
APP = PROJECT / "app"
DB = PROJECT / "data" / "phocap.db"
SURVEYS = APP / "routers" / "surveys.py"
TEMPLATE = APP / "templates" / "surveys" / "year_records.html"
EXPORTS = PROJECT / "exports"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
REPORT = EXPORTS / f"bao_cao_khao_sat_v2_3_8_truy_vet_hoc_2_buoi_{STAMP}.txt"

FUNC_NAME = "luu_theo_doi_nam_hoc"
FIELD = "attends_two_sessions_per_day"
MARKER_V237 = "BAI_13B_12_V2_3_7_SAVE_TWO_SESSIONS_START"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="replace")


def locate_function(source: str):
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == FUNC_NAME:
            return int(node.lineno), int(getattr(node, "end_lineno", node.lineno) or node.lineno)
    raise RuntimeError(f"Không tìm thấy hàm {FUNC_NAME}")


def line_excerpt(lines, center, before=6, after=10):
    start = max(1, center - before)
    end = min(len(lines), center + after)
    out = []
    for i in range(start, end + 1):
        prefix = ">>" if i == center else "  "
        out.append(f"{prefix} {i:05d}: {lines[i-1]}")
    return out


def main() -> int:
    EXPORTS.mkdir(parents=True, exist_ok=True)

    rows = [
        "=" * 122,
        "KHẢO SÁT BÀI 13B-12 V2.3.8 - TRUY VẾT HỌC 2 BUỔI/NGÀY VẪN KHÔNG LƯU",
        "=" * 122,
        f"Thời gian: {datetime.now():%d/%m/%Y %H:%M:%S}",
        "CHỈ ĐỌC - KHÔNG SỬA SOURCE - KHÔNG SỬA DATABASE",
        "",
    ]

    for p in (SURVEYS, TEMPLATE, DB):
        if not p.exists():
            rows.append(f"THIẾU: {p}")
            REPORT.write_text("\n".join(rows) + "\n", encoding="utf-8-sig")
            print("DỪNG:", p)
            print("Báo cáo:", REPORT)
            return 2

    source = read_text(SURVEYS)
    template = read_text(TEMPLATE)
    slines = source.splitlines()
    tlines = template.splitlines()

    rows.extend([
        "=" * 122,
        "1. KIỂM TRA V2.3.7 CÓ THỰC SỰ ĐƯỢC CÀI KHÔNG",
        "=" * 122,
        f"Có marker V2.3.7: {MARKER_V237 in source}",
        "",
    ])

    start, end = locate_function(source)
    function_text = "\n".join(slines[start - 1:end])

    rows.extend([
        f"Hàm {FUNC_NAME}: dòng {start} -> {end}",
        f"Trong đúng hàm có marker V2.3.7: {MARKER_V237 in function_text}",
        "",
    ])

    occurrences = []
    for i in range(start, end + 1):
        if FIELD in slines[i - 1]:
            occurrences.append(i)

    rows.extend([
        "=" * 122,
        "2. MỌI VỊ TRÍ CÓ attends_two_sessions_per_day TRONG ROUTE LƯU",
        "=" * 122,
        f"Tổng vị trí: {len(occurrences)}",
    ])

    for pos in occurrences:
        rows.append("")
        rows.extend(line_excerpt(slines, pos, 5, 8))

    assignment_lines = []
    for i in range(start, end + 1):
        line = slines[i - 1]
        if re.search(
            r"\.[ \t]*attends_two_sessions_per_day[ \t]*=",
            line,
        ):
            assignment_lines.append(i)

    rows.extend([
        "",
        "=" * 122,
        "3. CÁC PHÉP GÁN THỰC SỰ VÀO YEAR-RECORD",
        "=" * 122,
        f"Số phép gán tìm thấy: {len(assignment_lines)}",
    ])

    if assignment_lines:
        for pos in assignment_lines:
            rows.append("")
            rows.extend(line_excerpt(slines, pos, 8, 14))
    else:
        rows.append("KHÔNG CÓ phép gán .attends_two_sessions_per_day = ... trong route.")

    commit_lines = []
    for i in range(start, end + 1):
        if "db.commit()" in slines[i - 1]:
            commit_lines.append(i)

    rows.extend([
        "",
        "=" * 122,
        "4. CÁC db.commit() TRONG ROUTE",
        "=" * 122,
        f"Số commit: {len(commit_lines)}",
    ])

    for pos in commit_lines:
        rows.append("")
        rows.extend(line_excerpt(slines, pos, 25, 12))

    rows.extend([
        "",
        "=" * 122,
        "5. TÌM CÁC KHỐI CÓ THỂ GHI ĐÈ SAU PHÉP GÁN",
        "=" * 122,
    ])

    if assignment_lines:
        last_assignment = max(assignment_lines)
        suspicious = []
        for i in range(last_assignment + 1, end + 1):
            line = slines[i - 1]
            low = line.lower()
            if any(token in low for token in (
                "setattr(",
                "fields_to_copy",
                "boolean_year_fields",
                "parsed_tri_state",
                "display_record",
                "record =",
                ".update(",
                "merge(",
                "refresh(",
            )):
                suspicious.append(i)

        rows.append(
            f"Từ phép gán cuối dòng {last_assignment} đến hết hàm, "
            f"có {len(suspicious)} dòng nghi có khả năng ghi đè."
        )
        for pos in suspicious[:60]:
            rows.extend(line_excerpt(slines, pos, 2, 3))
            rows.append("")
    else:
        rows.append("Không thể truy vết ghi đè vì chưa có phép gán.")

    rows.extend([
        "=" * 122,
        "6. TEMPLATE - FIELD CÓ NẰM TRONG ĐÚNG FORM POST KHÔNG",
        "=" * 122,
    ])

    field_positions = [
        i for i, line in enumerate(tlines, start=1)
        if 'name="attends_two_sessions_per_day"' in line
    ]
    rows.append(f"Vị trí name field: {field_positions}")

    for pos in field_positions:
        # tìm form mở gần nhất phía trước
        form_open = None
        for j in range(pos, max(0, pos - 1800), -1):
            if "<form" in tlines[j - 1]:
                form_open = j
                break
        rows.append(f"Field dòng {pos}; form mở gần nhất: {form_open}")
        if form_open:
            rows.extend(line_excerpt(tlines, form_open, 1, 10))
        rows.extend(line_excerpt(tlines, pos, 4, 7))
        rows.append("")

    rows.extend([
        "=" * 122,
        "7. DATABASE ĐỐI TƯỢNG TEST",
        "=" * 122,
    ])

    con = sqlite3.connect(str(DB))
    con.row_factory = sqlite3.Row
    try:
        integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
        fk = con.execute("PRAGMA foreign_key_check").fetchall()
        rows.append(f"integrity_check: {integrity}")
        rows.append(f"foreign_key_check: {len(fk)} lỗi")

        row = con.execute(
            """
            SELECT
                spr.id,
                spr.survey_person_id,
                spr.school_year_id,
                spr.completed_preschool_by_age,
                spr.attends_two_sessions_per_day,
                spr.prepared_vietnamese,
                spr.updated_at,
                sp.full_name,
                sp.date_of_birth,
                spr.school_name_reported,
                spr.class_name_reported
            FROM survey_person_year_records spr
            JOIN survey_people sp
              ON sp.id = spr.survey_person_id
            WHERE spr.survey_person_id = 75
              AND spr.school_year_id = 2
            LIMIT 1
            """
        ).fetchone()

        if row:
            for key in row.keys():
                rows.append(f" - {key}: {row[key]}")
        else:
            rows.append("Không tìm thấy person_id=75 / school_year_id=2.")
    finally:
        con.close()

    rows.extend([
        "",
        "=" * 122,
        "8. KẾT LUẬN TỰ ĐỘNG",
        "=" * 122,
    ])

    if MARKER_V237 not in function_text:
        rows.append(
            "V2.3.7 CHƯA nằm trong route lưu hiện tại. "
            "Cần kiểm tra kết quả cài đặt hoặc source đã bị thay sau đó."
        )
    elif not assignment_lines:
        rows.append(
            "Có marker V2.3.7 nhưng không có phép gán thật: "
            "bộ cài trước chưa chèn đúng vị trí."
        )
    else:
        rows.append(
            "V2.3.7 đã có phép gán. Nếu DB vẫn NULL thì cần sửa nhánh "
            "ghi đè/phạm vi form dựa trên các đoạn source ở mục 4-6."
        )

    REPORT.write_text("\n".join(rows) + "\n", encoding="utf-8-sig")

    print("=" * 122)
    print("KHẢO SÁT V2.3.8 HOÀN THÀNH - KHÔNG THAY ĐỔI DỮ LIỆU")
    print("=" * 122)
    print("Báo cáo:", REPORT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
