# -*- coding: utf-8 -*-
from __future__ import annotations

import re
import sqlite3
from datetime import datetime
from pathlib import Path

PROJECT = Path(r"C:\PhoCap")
APP = PROJECT / "app"
DB = PROJECT / "data" / "phocap.db"
EXPORTS = PROJECT / "exports"

CANDIDATE_FILES = [
    APP / "survey_models.py",
    APP / "routers" / "surveys.py",
    APP / "templates" / "surveys" / "year_records.html",
    APP / "templates" / "surveys" / "households.html",
    APP / "templates" / "partials" / "dropdown_menu_v1.html",
    APP / "routers" / "survey_team_registration.py",
    APP / "access_control.py",
    APP / "pcgd_xmc_report_builders_v1.py",
    APP / "services" / "xmc_report_v247.py",
]

XMC_TOKENS = [
    "is_literacy_target",
    "literacy_status",
    "completed_grade_3",
    "completed_grade_5",
    "completed_primary_program",
    "completed_lower_secondary_program",
    "post_lower_secondary_path",
    "FORCE_XMC_AGE15",
    "DERIVE_LITERACY_STATUS",
    "THEO_DOI_XMC",
    "KHONG_THUOC_DIEN",
    "CMC-1",
    "CMC-2",
    "XMC-3",
    "XMC-4",
]

ATTAINMENT_TOKENS = [
    "highest_grade",
    "highest_education",
    "education_level",
    "education_attainment",
    "grade_completed",
    "completed_grade",
    "trinh_do",
    "trình độ",
    "lớp cao nhất",
    "lop_cao_nhat",
    "bậc học",
    "bac_hoc",
    "tốt nghiệp",
    "tot_nghiep",
    "learning_status",
    "current_education_program",
    "is_repeating_grade",
]

MENU_TOKENS = [
    "1. Danh mục",
    "2.2.1.",
    "Cập nhật dữ liệu hộ dân",
    "Danh sách hộ dân / phiếu được giao",
    "Thêm hộ",
    "Điều tra mới",
]


def read_text(path: Path) -> str:
    for enc in ("utf-8-sig", "utf-8", "cp1258"):
        try:
            return path.read_text(encoding=enc)
        except Exception:
            pass
    return ""


def context_blocks(text: str, tokens: list[str], before=5, after=10, max_blocks=80):
    lines = text.splitlines()
    ranges = []
    for i, line in enumerate(lines, 1):
        low = line.lower()
        if any(token.lower() in low for token in tokens):
            start = max(1, i - before)
            end = min(len(lines), i + after)
            if ranges and start <= ranges[-1][1] + 2:
                ranges[-1] = (ranges[-1][0], max(ranges[-1][1], end))
            else:
                ranges.append((start, end))
    return lines, ranges[:max_blocks], max(0, len(ranges) - max_blocks)


def emit_source_section(out: list[str], path: Path, tokens: list[str], title: str):
    out.append("")
    out.append("=" * 118)
    out.append(f"{title}: {path}")
    out.append("=" * 118)
    if not path.is_file():
        out.append("KHÔNG TỒN TẠI")
        return

    text = read_text(path)
    lines, ranges, hidden = context_blocks(text, tokens)
    out.append(f"Số dòng: {len(lines)} | Kích thước: {path.stat().st_size} bytes")
    out.append(f"Số khối hiển thị: {len(ranges)}")

    for start, end in ranges:
        out.append("")
        out.append(f"--- L{start}-L{end} ---")
        for n in range(start, end + 1):
            out.append(f"{n:05d}: {lines[n-1]}")
    if hidden:
        out.append(f"... còn {hidden} khối không in.")


def table_exists(con: sqlite3.Connection, table: str) -> bool:
    return con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone() is not None


def main():
    EXPORTS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report = EXPORTS / (
        "bao_cao_khao_sat_bai_13b_12_v2_1_"
        f"trinh_do_toan_dan_giu_nguyen_xmc_{stamp}.txt"
    )

    out: list[str] = []
    out.append("=" * 118)
    out.append(
        "KHẢO SÁT BÀI 13B-12 V2.1 - "
        "TRÌNH ĐỘ TOÀN DÂN + GIỮ NGUYÊN QUY TẮC XÓA MÙ CHỮ"
    )
    out.append("=" * 118)
    out.append(f"Thời gian: {datetime.now():%d/%m/%Y %H:%M:%S}")
    out.append(f"Dự án: {PROJECT}")
    out.append("")
    out.append("NGHIỆP VỤ KHÓA")
    out.append("- Điều tra 2026-2027 thu TOÀN BỘ thành viên trong hộ.")
    out.append("- Mỗi thành viên phải có nhân khẩu + cư trú + dữ liệu giáo dục/trình độ phù hợp.")
    out.append("- PCGD dùng quy tắc PCGD hiện có.")
    out.append("- XMC GIỮ NGUYÊN quy tắc cũ; không tạo bộ quy tắc mới.")
    out.append("- Dữ liệu học sinh 2025-2026 chỉ làm liên năm/đối chiếu.")
    out.append("- Không tạo menu 2.2.8.")
    out.append("")

    if not DB.is_file():
        out.append(f"KHÔNG TÌM THẤY DATABASE: {DB}")
    else:
        con = sqlite3.connect(str(DB))
        con.row_factory = sqlite3.Row
        try:
            integrity = str(con.execute("PRAGMA integrity_check").fetchone()[0])
            fk = con.execute("PRAGMA foreign_key_check").fetchall()

            out.append("I. DATABASE")
            out.append(f"integrity_check: {integrity}")
            out.append(f"foreign_key_check: {len(fk)} lỗi")

            if table_exists(con, "survey_person_year_records"):
                cols = con.execute(
                    "PRAGMA table_info(survey_person_year_records)"
                ).fetchall()

                out.append("")
                out.append("II. SCHEMA survey_person_year_records")
                for c in cols:
                    out.append(
                        f"- {c['name']} | {c['type']} | "
                        f"notnull={c['notnull']} | default={c['dflt_value']}"
                    )

                names = {str(c["name"]) for c in cols}

                required_xmc = {
                    "is_literacy_target",
                    "literacy_status",
                    "completed_grade_3",
                    "completed_grade_5",
                    "completed_primary_program",
                    "completed_lower_secondary_program",
                    "post_lower_secondary_path",
                }

                out.append("")
                out.append("III. FIELD XMC HIỆN HÀNH")
                for field in sorted(required_xmc):
                    out.append(
                        f"- {field}: {'CÓ' if field in names else 'THIẾU'}"
                    )

                candidate_attainment = [
                    n for n in names
                    if any(
                        token in n.lower()
                        for token in (
                            "highest",
                            "education",
                            "grade",
                            "primary",
                            "secondary",
                            "program",
                            "learning",
                        )
                    )
                ]

                out.append("")
                out.append("IV. FIELD CÓ THỂ DÙNG CHO TRÌNH ĐỘ HỌC VẤN")
                for field in sorted(candidate_attainment):
                    out.append(f"- {field}")

                count = con.execute(
                    "SELECT COUNT(*) FROM survey_person_year_records"
                ).fetchone()[0]
                out.append(f"Số year-record hiện có: {count}")

                if count:
                    for field in (
                        "learning_status",
                        "is_literacy_target",
                        "literacy_status",
                        "completed_grade_3",
                        "completed_grade_5",
                        "completed_primary_program",
                        "completed_lower_secondary_program",
                        "post_lower_secondary_path",
                    ):
                        if field not in names:
                            continue
                        out.append("")
                        out.append(f"[PHÂN BỐ {field}]")
                        try:
                            rows = con.execute(
                                f"""
                                SELECT {field} AS value, COUNT(*) AS total
                                FROM survey_person_year_records
                                GROUP BY {field}
                                ORDER BY total DESC
                                """
                            ).fetchall()
                            for row in rows[:30]:
                                out.append(
                                    f"  value={row['value']!r} | total={row['total']}"
                                )
                        except Exception as exc:
                            out.append(f"  ERROR: {exc}")

            if table_exists(con, "survey_people"):
                out.append("")
                out.append("V. SCHEMA survey_people - NHÂN KHẨU LÕI")
                for c in con.execute(
                    "PRAGMA table_info(survey_people)"
                ).fetchall():
                    out.append(
                        f"- {c['name']} | {c['type']} | "
                        f"notnull={c['notnull']}"
                    )

        finally:
            con.close()

    out.append("")
    out.append("VI. SOURCE XMC HIỆN TẠI")
    for path in CANDIDATE_FILES:
        if path.name in {
            "surveys.py",
            "year_records.html",
            "pcgd_xmc_report_builders_v1.py",
            "xmc_report_v247.py",
        }:
            emit_source_section(out, path, XMC_TOKENS, "XMC SOURCE")

    out.append("")
    out.append("VII. SOURCE NHẬP TRÌNH ĐỘ / NĂM HỌC")
    for path in CANDIDATE_FILES:
        if path.name in {
            "survey_models.py",
            "surveys.py",
            "year_records.html",
        }:
            emit_source_section(out, path, ATTAINMENT_TOKENS, "TRÌNH ĐỘ SOURCE")

    out.append("")
    out.append("VIII. VỊ TRÍ GIAO DIỆN CHO BÀI V2")
    for path in CANDIDATE_FILES:
        if path.name in {
            "dropdown_menu_v1.html",
            "households.html",
            "survey_team_registration.py",
        }:
            emit_source_section(out, path, MENU_TOKENS, "UI/MENU SOURCE")

    out.append("")
    out.append("=" * 118)
    out.append("IX. KẾT LUẬN CẦN KHÓA TRƯỚC BỘ CÀI V2.1")
    out.append("=" * 118)
    out.append(
        "1. Xác nhận field XMC hiện có và tuyệt đối không thay công thức XMC."
    )
    out.append(
        "2. Xác định liệu đã có field riêng cho 'lớp cao nhất đã hoàn thành' "
        "và 'trình độ học vấn cao nhất' hay chưa."
    )
    out.append(
        "3. Nếu thiếu, chỉ bổ sung field dữ liệu đầu vào; "
        "không sửa completed_grade_3/5 hoặc công thức 4 biểu XMC."
    )
    out.append(
        "4. Khối nhập phải áp dụng cho mọi thành viên hộ, "
        "không chỉ học sinh đang học."
    )
    out.append(
        "5. Hộ chỉ được hoàn thành khi mọi thành viên đang hoạt động "
        "có year-record và đủ field bắt buộc theo nhóm tuổi."
    )
    out.append(
        "6. Nút 'Điều tra mới – Nhập hộ dân mới' vẫn thuộc 2.2.1 "
        "và chỉ tổ đã được giao mới được dùng."
    )
    out.append(
        "7. Danh mục thôn/xóm/khối/tổ/bản thuộc cấp Xã; "
        "không tạo menu 2.2.8."
    )
    out.append("")
    out.append("KHẢO SÁT CHỈ ĐỌC - KHÔNG ALTER / INSERT / UPDATE / DELETE.")

    report.write_text(
        "\n".join(out) + "\n",
        encoding="utf-8-sig",
    )

    print("=" * 118)
    print("KHẢO SÁT BÀI 13B-12 V2.1 HOÀN TẤT")
    print("=" * 118)
    print("KHÔNG thay đổi source hoặc database.")
    print("Báo cáo:", report)
    print("Hãy gửi lại báo cáo này để tạo bộ cài V2.1 an toàn.")


if __name__ == "__main__":
    main()
