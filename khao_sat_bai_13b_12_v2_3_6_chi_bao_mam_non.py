# -*- coding: utf-8 -*-
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

PROJECT = Path(r"C:\PhoCap")
APP = PROJECT / "app"
DB = PROJECT / "data" / "phocap.db"
EXPORTS = PROJECT / "exports"

FILES = [
    APP / "templates" / "surveys" / "year_records.html",
    APP / "routers" / "surveys.py",
    APP / "survey_models.py",
    APP / "models.py",
]

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
REPORT = EXPORTS / f"bao_cao_khao_sat_v2_3_6_chi_bao_mam_non_{STAMP}.txt"

KEYWORDS = [
    "mầm non",
    "mam non",
    "preschool",
    "hoàn thành chương trình",
    "hoan thanh chuong trinh",
    "đúng độ tuổi",
    "dung do tuoi",
    "5 tuổi",
    "5 tuoi",
    "3 tuổi",
    "4 tuổi",
    "trẻ 3",
    "trẻ 4",
    "trẻ 5",
    "học hòa nhập",
    "hoc hoa nhap",
    "khuyết tật",
    "khuyet tat",
    "completed_preschool",
    "preschool_5",
    "attend",
    "attendance",
]


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="replace")


def excerpt(text: str, line_no: int, radius: int = 5) -> str:
    items = text.splitlines()
    start = max(0, line_no - 1 - radius)
    end = min(len(items), line_no + radius)
    rows = []
    for i in range(start, end):
        prefix = ">>" if i == line_no - 1 else "  "
        rows.append(f"{prefix} {i+1:05d}: {items[i]}")
    return "\n".join(rows)


def main() -> int:
    EXPORTS.mkdir(parents=True, exist_ok=True)
    lines = [
        "=" * 120,
        "KHẢO SÁT BÀI 13B-12 V2.3.6 - CHỈ BÁO MẦM NON KHÔNG XUẤT HIỆN",
        "=" * 120,
        f"Thời gian: {datetime.now():%d/%m/%Y %H:%M:%S}",
        f"Dự án: {PROJECT}",
        "",
    ]

    for path in FILES:
        lines.extend(["-" * 120, f"FILE: {path}"])
        if not path.exists():
            lines.append("KHÔNG TỒN TẠI")
            continue

        text = read_text(path)
        matches = []
        for idx, raw in enumerate(text.splitlines(), start=1):
            low = raw.casefold()
            if any(k.casefold() in low for k in KEYWORDS):
                matches.append(idx)

        lines.append(f"Số dòng khớp từ khóa MN: {len(matches)}")
        for line_no in matches[:80]:
            lines.append("")
            lines.append(excerpt(text, line_no))
        if len(matches) > 80:
            lines.append(f"... còn {len(matches)-80} vị trí khác.")

    lines.extend(["", "=" * 120, "DATABASE", "=" * 120])

    if not DB.exists():
        lines.append(f"KHÔNG TÌM THẤY DB: {DB}")
    else:
        con = sqlite3.connect(str(DB))
        con.row_factory = sqlite3.Row
        try:
            integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
            fk = con.execute("PRAGMA foreign_key_check").fetchall()
            lines.append(f"integrity_check: {integrity}")
            lines.append(f"foreign_key_check: {len(fk)} lỗi")
            lines.append("")

            cols = con.execute(
                "PRAGMA table_info(survey_person_year_records)"
            ).fetchall()
            lines.append("CÁC CỘT year-record LIÊN QUAN MN/PCGD:")
            for c in cols:
                name = str(c["name"])
                low = name.casefold()
                if any(token in low for token in (
                    "preschool", "mam", "age", "attend", "complete",
                    "grade", "school", "class", "disab", "integr",
                    "literacy", "education", "learning"
                )):
                    lines.append(f" - {name} ({c['type']})")

            lines.append("")
            person_id = 75
            year_id = 2
            row = con.execute(
                """
                SELECT
                    sp.id AS person_id,
                    sp.full_name,
                    sp.date_of_birth,
                    spr.id AS year_record_id,
                    spr.school_year_id,
                    spr.learning_status,
                    spr.school_id,
                    spr.class_id,
                    spr.school_name_reported,
                    spr.class_name_reported,
                    spr.education_attainment_level,
                    spr.highest_completed_grade,
                    spr.is_literacy_target,
                    spr.completed_grade_3,
                    spr.completed_grade_5,
                    c.name AS class_name,
                    s.name AS school_name,
                    sy.code AS school_year_code
                FROM survey_people sp
                LEFT JOIN survey_person_year_records spr
                  ON spr.survey_person_id = sp.id
                 AND spr.school_year_id = ?
                LEFT JOIN classes c ON c.id = spr.class_id
                LEFT JOIN schools s ON s.id = spr.school_id
                LEFT JOIN school_years sy ON sy.id = spr.school_year_id
                WHERE sp.id = ?
                """,
                (year_id, person_id),
            ).fetchone()

            lines.append("ĐỐI TƯỢNG TEST TRÊN ẢNH (person_id=75, school_year_id=2):")
            if row:
                for key in row.keys():
                    lines.append(f" - {key}: {row[key]}")
            else:
                lines.append(" - Không tìm thấy bản ghi tương ứng.")

            if row and row["year_record_id"] is not None:
                lines.append("")
                lines.append("TOÀN BỘ YEAR-RECORD ĐỐI TƯỢNG TEST:")
                full = con.execute(
                    "SELECT * FROM survey_person_year_records WHERE id = ?",
                    (row["year_record_id"],)
                ).fetchone()
                for key in full.keys():
                    lines.append(f" - {key}: {full[key]}")
        finally:
            con.close()

    lines.extend([
        "",
        "=" * 120,
        "KẾT LUẬN DÙNG CHO V2.3.6",
        "=" * 120,
        "Khảo sát này KHÔNG sửa source/DB.",
        "Mục tiêu là xác định chính xác các chỉ báo MN hiện nằm ở đâu,",
        "điều kiện hiển thị đang dựa vào tuổi/cấp học/trường/lớp hay role,",
        "và dữ liệu đối tượng test đang lưu như thế nào.",
    ])

    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
    print("=" * 120)
    print("KHẢO SÁT V2.3.6 HOÀN THÀNH - KHÔNG THAY ĐỔI DỮ LIỆU")
    print("=" * 120)
    print("Báo cáo:", REPORT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
