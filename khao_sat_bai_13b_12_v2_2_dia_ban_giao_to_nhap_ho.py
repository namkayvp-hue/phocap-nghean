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
    APP / "templates" / "partials" / "dropdown_menu_v1.html",
    APP / "templates" / "surveys" / "households.html",
    APP / "routers" / "surveys.py",
    APP / "routers" / "survey_team_registration.py",
    APP / "survey_models.py",
    APP / "access_control.py",
    APP / "permissions.py",
]

TOKENS = [
    "BAI_13B_12_V2_1",
    "highest_completed_grade",
    "education_attainment_level",
    "2.2.1. Danh sách hộ dân / phiếu được giao",
    "Thêm hộ điều tra",
    "openHouseholdDialog",
    "/ho-dan/them",
    "co_quyen_quan_tri_dot",
    "GIAO_VIEN",
    "TEACHER_ROLE_CODE",
    "COMMUNE_ROLE_CODE",
    "survey_investigation_teams",
    "survey_investigation_team_members",
    "survey_investigation_team_forms",
    "lap-to/tao-ngau-nhien",
    "lap-to/chot-gui",
    "Không phân đủ toàn bộ phiếu/hộ",
    "không có hộ/phiếu",
    "survey_form_investigators",
    "is_primary",
    "assignment_order",
    "menu_role",
    "1. Danh mục",
]


def read_text(path: Path) -> str:
    for enc in ("utf-8-sig", "utf-8", "cp1258"):
        try:
            return path.read_text(encoding=enc)
        except Exception:
            pass
    return ""


def emit_hits(lines_out: list[str], path: Path, max_blocks: int = 90):
    lines_out.append("")
    lines_out.append("=" * 118)
    lines_out.append(f"SOURCE: {path}")
    lines_out.append("=" * 118)

    if not path.is_file():
        lines_out.append("KHÔNG TỒN TẠI")
        return

    text = read_text(path)
    src_lines = text.splitlines()

    ranges = []
    for i, line in enumerate(src_lines, 1):
        low = line.lower()
        if any(token.lower() in low for token in TOKENS):
            start = max(1, i - 7)
            end = min(len(src_lines), i + 15)
            if ranges and start <= ranges[-1][1] + 2:
                ranges[-1] = (
                    ranges[-1][0],
                    max(ranges[-1][1], end),
                )
            else:
                ranges.append((start, end))

    lines_out.append(
        f"Số dòng={len(src_lines)} | "
        f"kích thước={path.stat().st_size} bytes | "
        f"khối liên quan={len(ranges)}"
    )

    for start, end in ranges[:max_blocks]:
        lines_out.append("")
        lines_out.append(f"--- L{start}-L{end} ---")
        for n in range(start, end + 1):
            lines_out.append(f"{n:05d}: {src_lines[n-1]}")

    if len(ranges) > max_blocks:
        lines_out.append(
            f"... còn {len(ranges)-max_blocks} khối không in."
        )


def table_exists(con: sqlite3.Connection, table: str) -> bool:
    return con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone() is not None


def schema(con: sqlite3.Connection, table: str):
    return con.execute(
        f'PRAGMA table_info("{table}")'
    ).fetchall()


def fk_schema(con: sqlite3.Connection, table: str):
    return con.execute(
        f'PRAGMA foreign_key_list("{table}")'
    ).fetchall()


def main():
    EXPORTS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report = EXPORTS / (
        "bao_cao_khao_sat_bai_13b_12_v2_2_"
        f"dia_ban_giao_to_nhap_ho_{stamp}.txt"
    )

    out: list[str] = []
    out.append("=" * 118)
    out.append(
        "KHẢO SÁT BÀI 13B-12 V2.2 - "
        "DANH MỤC ĐỊA BÀN + GIAO ĐỊA BÀN/CHỈ TIÊU + TỔ TẠO HỘ"
    )
    out.append("=" * 118)
    out.append(f"Thời gian: {datetime.now():%d/%m/%Y %H:%M:%S}")
    out.append(f"Dự án: {PROJECT}")
    out.append("")
    out.append("NGHIỆP VỤ ĐÃ KHÓA")
    out.append("1. Không tạo menu 2.2.8.")
    out.append(
        "2. Nút lớn '➕ Điều tra mới – Nhập hộ dân mới' "
        "nằm tại 2.2.1."
    )
    out.append(
        "3. Xã KHÔNG nhập hộ; Xã chỉ khai báo "
        "thôn/xóm/khối/tổ/bản + số hộ dự kiến."
    )
    out.append(
        "4. Trường gửi GV; Xã ghép tổ 3 người đủ MN + TH + THCS."
    )
    out.append(
        "5. Xã giao địa bàn + chỉ tiêu số hộ cho từng tổ."
    )
    out.append(
        "6. Thành viên tổ đã được chốt/gửi mới được tạo hộ tại thực địa."
    )
    out.append(
        "7. Hộ mới phải chọn địa bàn từ danh mục; "
        "hệ thống tự tạo phiếu và gắn cả tổ."
    )
    out.append(
        "8. Theo dõi: Số hộ dự kiến / Đã nhập / Còn thiếu / % hoàn thành."
    )
    out.append(
        "9. Giữ nguyên giao phiếu, nhập nhanh, khóa/mở, PCGD và XMC đã có."
    )
    out.append("")

    # SOURCE
    out.append("I. SOURCE HIỆN TẠI")
    for path in FILES:
        emit_hits(out, path)

    # DB
    out.append("")
    out.append("=" * 118)
    out.append("II. DATABASE HIỆN TẠI")
    out.append("=" * 118)

    if not DB.is_file():
        out.append(f"KHÔNG TÌM THẤY DB: {DB}")
    else:
        con = sqlite3.connect(str(DB))
        con.row_factory = sqlite3.Row
        try:
            integrity = str(
                con.execute(
                    "PRAGMA integrity_check"
                ).fetchone()[0]
            )
            fk_errors = con.execute(
                "PRAGMA foreign_key_check"
            ).fetchall()

            out.append(f"integrity_check: {integrity}")
            out.append(
                f"foreign_key_check: {len(fk_errors)} lỗi"
            )

            out.append("")
            out.append("A. KIỂM TRA V2.1")
            if table_exists(con, "survey_person_year_records"):
                yr_cols = {
                    str(r["name"])
                    for r in schema(
                        con,
                        "survey_person_year_records",
                    )
                }
                for field in (
                    "highest_completed_grade",
                    "education_attainment_level",
                ):
                    out.append(
                        f"- {field}: "
                        f"{'CÓ' if field in yr_cols else 'CHƯA CÓ'}"
                    )

            all_tables = [
                str(r["name"])
                for r in con.execute(
                    """
                    SELECT name
                    FROM sqlite_master
                    WHERE type='table'
                      AND name NOT LIKE 'sqlite_%'
                    ORDER BY name
                    """
                ).fetchall()
            ]

            out.append("")
            out.append("B. BẢNG ĐỊA BÀN V2.2 ĐÃ TỒN TẠI?")
            area_candidates = [
                t for t in all_tables
                if any(
                    key in t.lower()
                    for key in (
                        "survey_area",
                        "commune_area",
                        "team_area",
                        "residential_area",
                        "hamlet",
                        "village",
                    )
                )
            ]
            if area_candidates:
                for table in area_candidates:
                    out.append(f"- {table}")
            else:
                out.append("- Chưa có bảng địa bàn V2.2.")

            important = [
                "survey_batches",
                "households",
                "survey_forms",
                "survey_form_investigators",
                "survey_investigation_participants",
                "survey_investigation_teams",
                "survey_investigation_team_members",
                "survey_investigation_team_forms",
                "survey_team_generation_logs",
                "communes",
                "school_years",
                "users",
            ]

            out.append("")
            out.append("C. SCHEMA CÁC BẢNG CỐT LÕI")
            for table in important:
                out.append("")
                out.append(f"[{table}]")
                if not table_exists(con, table):
                    out.append("  KHÔNG TỒN TẠI")
                    continue

                total = int(
                    con.execute(
                        f'SELECT COUNT(*) FROM "{table}"'
                    ).fetchone()[0]
                )
                out.append(f"  rows={total}")

                for c in schema(con, table):
                    out.append(
                        f"  - {c['name']} | {c['type']} | "
                        f"notnull={c['notnull']} | "
                        f"pk={c['pk']} | default={c['dflt_value']}"
                    )

                fks = fk_schema(con, table)
                if fks:
                    out.append("  FKs:")
                    for fk in fks:
                        out.append(
                            f"    {fk['from']} -> "
                            f"{fk['table']}.{fk['to']} | "
                            f"on_delete={fk['on_delete']}"
                        )

            # Nghi Lộc cleanliness / test state
            out.append("")
            out.append("D. TRẠNG THÁI NGHI LỘC 2026-2027")
            commune = con.execute(
                """
                SELECT id, code, name
                FROM communes
                WHERE code='17827'
                LIMIT 1
                """
            ).fetchone()
            year = con.execute(
                """
                SELECT id, code
                FROM school_years
                WHERE code='2026-2027'
                LIMIT 1
                """
            ).fetchone()

            if commune and year:
                batches = con.execute(
                    """
                    SELECT id, code, name, status, is_locked
                    FROM survey_batches
                    WHERE commune_id=?
                      AND school_year_id=?
                    ORDER BY id
                    """,
                    (
                        int(commune["id"]),
                        int(year["id"]),
                    ),
                ).fetchall()

                out.append(
                    f"Xã={commune['name']} | "
                    f"commune_id={commune['id']} | "
                    f"năm={year['code']}"
                )
                out.append(f"Số đợt hiện có: {len(batches)}")
                for batch in batches:
                    out.append(
                        f"- id={batch['id']} | "
                        f"{batch['code']} | "
                        f"{batch['status']} | "
                        f"locked={batch['is_locked']}"
                    )
            else:
                out.append(
                    "Không tìm thấy Nghi Lộc hoặc năm 2026-2027."
                )

            # Unique/index team_forms
            if table_exists(
                con,
                "survey_investigation_team_forms",
            ):
                out.append("")
                out.append(
                    "E. INDEX survey_investigation_team_forms"
                )
                for idx in con.execute(
                    "PRAGMA index_list("
                    "'survey_investigation_team_forms'"
                    ")"
                ).fetchall():
                    out.append(
                        f"- {idx['name']} | "
                        f"unique={idx['unique']} | "
                        f"origin={idx['origin']}"
                    )
                    cols = con.execute(
                        f"PRAGMA index_info('{idx['name']}')"
                    ).fetchall()
                    out.append(
                        "  cols="
                        + ", ".join(
                            str(c["name"])
                            for c in cols
                        )
                    )

        finally:
            con.close()

    out.append("")
    out.append("=" * 118)
    out.append("III. V2.2 DỰ KIẾN THÊM - CHỈ KHẢO SÁT")
    out.append("=" * 118)
    out.append(
        "- Bảng survey_commune_areas: "
        "địa bàn theo xã + năm học; loại THON/XOM/KHOI/TO/BAN; "
        "số hộ dự kiến."
    )
    out.append(
        "- Bảng survey_team_area_assignments: "
        "team_id + area_id + household_quota; "
        "hỗ trợ nhiều tổ cùng một địa bàn hoặc một tổ nhiều địa bàn."
    )
    out.append(
        "- Bảng survey_form_areas: "
        "survey_form_id duy nhất + area_id; "
        "dùng đếm hộ thực tế theo địa bàn mà không phá households cũ."
    )
    out.append(
        "- Khi tổ tạo hộ: tự insert survey_investigation_team_forms "
        "và 3 survey_form_investigators theo thành viên tổ."
    )
    out.append(
        "- Nhánh ghép tổ mới: nếu chưa có phiếu thì vẫn cho ghép tổ; "
        "không ép assigned_count == len(forms)."
    )
    out.append(
        "- Nhánh chốt mới: tổ có giao địa bàn/chỉ tiêu thì được chốt "
        "dù chưa có phiếu; khi có phiếu mới mới gắn investigator."
    )
    out.append(
        "- Nhánh cũ vẫn giữ: nếu đã có phiếu trước khi ghép tổ, "
        "cơ chế phân phiếu hiện có không bị xóa."
    )
    out.append(
        "- Nút tạo hộ ở 2.2.1 chỉ hiện cho GV thuộc tổ status SENT "
        "và còn địa bàn/chỉ tiêu được giao."
    )
    out.append("")
    out.append(
        "KHẢO SÁT CHỈ ĐỌC - KHÔNG ALTER/INSERT/UPDATE/DELETE."
    )

    report.write_text(
        "\n".join(out) + "\n",
        encoding="utf-8-sig",
    )

    print("=" * 118)
    print("KHẢO SÁT BÀI 13B-12 V2.2 HOÀN TẤT")
    print("=" * 118)
    print("KHÔNG thay đổi source hoặc database.")
    print("Báo cáo:", report)
    print(
        "Gửi lại file báo cáo để tạo bộ cài V2.2 an toàn."
    )


if __name__ == "__main__":
    main()
