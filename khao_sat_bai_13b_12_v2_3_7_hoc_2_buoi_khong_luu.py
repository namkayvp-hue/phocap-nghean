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
REPORT = EXPORTS / f"bao_cao_khao_sat_v2_3_7_hoc_2_buoi_khong_luu_{STAMP}.txt"

FIELD = "attends_two_sessions_per_day"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="replace")


def numbered_excerpt(lines: list[str], start: int, end: int) -> list[str]:
    start = max(1, start)
    end = min(len(lines), end)
    return [f"{i:05d}: {lines[i-1]}" for i in range(start, end + 1)]


def find_route_function(source: str) -> tuple[int | None, int | None, str]:
    lines = source.splitlines()
    candidates = []

    # Ưu tiên route có đường dẫn nam-hoc/luu.
    for i, line in enumerate(lines, start=1):
        low = line.lower()
        if "nam-hoc/luu" in low or "nam_hoc/luu" in low:
            candidates.append(i)

    if not candidates:
        # Dự phòng: tìm tên hàm.
        for i, line in enumerate(lines, start=1):
            if "luu_theo_doi_nam_hoc" in line:
                candidates.append(i)

    if not candidates:
        return None, None, ""

    anchor = candidates[0]

    # Tìm def gần sau decorator.
    def_line = None
    for i in range(max(1, anchor - 8), min(len(lines), anchor + 30) + 1):
        if re.match(r"\s*(async\s+def|def)\s+", lines[i-1]):
            def_line = i
            break

    if def_line is None:
        return anchor, None, ""

    # Tìm hết hàm bằng AST để chính xác.
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.lineno == def_line:
                end_line = int(getattr(node, "end_lineno", def_line) or def_line)
                return anchor, def_line, "\n".join(
                    numbered_excerpt(lines, max(1, anchor - 5), min(end_line, def_line + 320))
                )

    return anchor, def_line, "\n".join(
        numbered_excerpt(lines, max(1, anchor - 5), min(len(lines), def_line + 320))
    )


def main() -> int:
    EXPORTS.mkdir(parents=True, exist_ok=True)

    lines = [
        "=" * 120,
        "KHẢO SÁT BÀI 13B-12 V2.3.7 - HỌC 2 BUỔI/NGÀY NHẬP NHƯNG KHÔNG LƯU",
        "=" * 120,
        f"Thời gian: {datetime.now():%d/%m/%Y %H:%M:%S}",
        f"Dự án: {PROJECT}",
        "",
        "KHẢO SÁT CHỈ ĐỌC - KHÔNG SỬA SOURCE, KHÔNG SỬA DATABASE.",
        "",
    ]

    for p in (SURVEYS, TEMPLATE, DB):
        if not p.exists():
            lines.append(f"THIẾU: {p}")
            REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
            print("DỪNG: thiếu", p)
            print("Báo cáo:", REPORT)
            return 2

    source = read_text(SURVEYS)
    template = read_text(TEMPLATE)

    lines.extend([
        "=" * 120,
        "1. TEMPLATE year_records.html",
        "=" * 120,
    ])

    tlines = template.splitlines()
    matches = [
        i for i, raw in enumerate(tlines, start=1)
        if FIELD in raw
    ]
    lines.append(f"Số vị trí chứa {FIELD}: {len(matches)}")
    for pos in matches[:12]:
        lines.extend(numbered_excerpt(tlines, pos - 8, pos + 12))
        lines.append("")

    lines.extend([
        "=" * 120,
        "2. ROUTER surveys.py - KHAI BÁO / DANH SÁCH FIELD",
        "=" * 120,
    ])

    slines = source.splitlines()
    smatches = [
        i for i, raw in enumerate(slines, start=1)
        if FIELD in raw
    ]
    lines.append(f"Số vị trí chứa {FIELD}: {len(smatches)}")
    for pos in smatches[:30]:
        lines.extend(numbered_excerpt(slines, pos - 7, pos + 12))
        lines.append("")

    lines.extend([
        "=" * 120,
        "3. ROUTE POST LƯU NĂM HỌC",
        "=" * 120,
    ])

    anchor, def_line, route_excerpt = find_route_function(source)
    lines.append(f"Route anchor line: {anchor}")
    lines.append(f"Function def line: {def_line}")
    if route_excerpt:
        lines.append(route_excerpt)
    else:
        lines.append("KHÔNG XÁC ĐỊNH ĐƯỢC ROUTE LƯU NĂM HỌC.")

    lines.extend([
        "",
        "=" * 120,
        "4. KIỂM TRA TỰ ĐỘNG TRONG ROUTE LƯU",
        "=" * 120,
    ])

    if route_excerpt:
        checks = {
            "route_co_ten_field": FIELD in route_excerpt,
            "doc_form_get_field": (
                f'form.get("{FIELD}")' in route_excerpt
                or f"form.get('{FIELD}')" in route_excerpt
            ),
            "gan_truc_tiep_record_field": (
                f"record.{FIELD}" in route_excerpt
                or f"selected_record.{FIELD}" in route_excerpt
            ),
            "setattr_field": (
                f'setattr(record, "{FIELD}"' in route_excerpt
                or f"setattr(record, '{FIELD}'" in route_excerpt
            ),
            "co_vong_BOOLEAN_YEAR_FIELDS": "BOOLEAN_YEAR_FIELDS" in route_excerpt,
        }
        for key, value in checks.items():
            lines.append(f"{key}: {value}")
    else:
        lines.append("Không có route_excerpt để kiểm tra.")

    lines.extend([
        "",
        "=" * 120,
        "5. DATABASE",
        "=" * 120,
    ])

    con = sqlite3.connect(str(DB))
    con.row_factory = sqlite3.Row
    try:
        integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
        fk = con.execute("PRAGMA foreign_key_check").fetchall()
        lines.append(f"integrity_check: {integrity}")
        lines.append(f"foreign_key_check: {len(fk)} lỗi")

        cols = {
            row["name"]: row
            for row in con.execute(
                "PRAGMA table_info(survey_person_year_records)"
            ).fetchall()
        }
        lines.append(f"Có cột {FIELD}: {FIELD in cols}")
        if FIELD in cols:
            lines.append(
                f"Kiểu cột: {cols[FIELD]['type']} | nullable/default: "
                f"notnull={cols[FIELD]['notnull']} default={cols[FIELD]['dflt_value']}"
            )

        # Đúng đối tượng trong ảnh hiện tại.
        row = con.execute(
            f"""
            SELECT
                spr.id,
                spr.survey_form_id,
                spr.survey_person_id,
                spr.school_year_id,
                spr.learning_status,
                spr.school_name_reported,
                spr.class_name_reported,
                spr.completed_preschool_by_age,
                spr.{FIELD},
                spr.prepared_vietnamese,
                spr.is_reviewed,
                spr.updated_at,
                sp.full_name,
                sp.date_of_birth
            FROM survey_person_year_records spr
            JOIN survey_people sp
              ON sp.id = spr.survey_person_id
            WHERE spr.survey_person_id = 75
              AND spr.school_year_id = 2
            LIMIT 1
            """
        ).fetchone()

        lines.append("")
        lines.append("ĐỐI TƯỢNG TEST person_id=75, school_year_id=2:")
        if row:
            for key in row.keys():
                lines.append(f" - {key}: {row[key]}")
        else:
            lines.append(" - Không tìm thấy.")

        # Kiểm tra các record MN đang có completed_preschool_by_age nhưng 2 buổi NULL.
        rows = con.execute(
            f"""
            SELECT
                spr.id,
                spr.survey_person_id,
                sp.full_name,
                spr.school_name_reported,
                spr.class_name_reported,
                spr.completed_preschool_by_age,
                spr.{FIELD},
                spr.updated_at
            FROM survey_person_year_records spr
            JOIN survey_people sp
              ON sp.id = spr.survey_person_id
            WHERE spr.completed_preschool_by_age IS NOT NULL
              AND spr.{FIELD} IS NULL
            ORDER BY spr.id
            LIMIT 50
            """
        ).fetchall()

        lines.append("")
        lines.append(
            "RECORD có completed_preschool_by_age đã lưu nhưng "
            f"{FIELD} vẫn NULL: {len(rows)}"
        )
        for r in rows:
            lines.append(
                " - "
                + " | ".join(
                    f"{k}={r[k]}"
                    for k in r.keys()
                )
            )

    finally:
        con.close()

    lines.extend([
        "",
        "=" * 120,
        "6. KẾT LUẬN CHẨN ĐOÁN",
        "=" * 120,
        "Nếu template có field + DB có cột nhưng route POST không đọc/gán field,",
        "thì V2.3.7 chính thức chỉ cần bổ sung đúng đường lưu cho attends_two_sessions_per_day.",
        "Nếu route đã đọc/gán field nhưng DB vẫn NULL, sẽ kiểm tra nhánh ghi đè sau đó.",
        "",
        "Không tự sửa dữ liệu trong khảo sát này.",
    ])

    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")

    print("=" * 120)
    print("KHẢO SÁT V2.3.7 HOÀN THÀNH - KHÔNG THAY ĐỔI DỮ LIỆU")
    print("=" * 120)
    print("Báo cáo:", REPORT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
