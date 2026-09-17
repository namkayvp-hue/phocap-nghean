# -*- coding: utf-8 -*-
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

PROJECT = Path(r"C:\PhoCap")
APP = PROJECT / "app"
DB = PROJECT / "data" / "phocap.db"
EXPORTS = PROJECT / "exports"

SOURCE_FILES = [
    APP / "routers" / "survey_team_registration.py",
    APP / "routers" / "surveys.py",
    APP / "templates" / "survey_teams" / "commune_submissions.html",
    APP / "templates" / "survey_teams" / "commune_team_builder.html",
    APP / "templates" / "survey_teams" / "commune_team_detail.html",
    APP / "templates" / "surveys" / "households.html",
    APP / "templates" / "partials" / "dropdown_menu_v1.html",
    APP / "survey_models.py",
    APP / "models.py",
    APP / "access_control.py",
]

KEYWORDS = [
    "survey_investigation_teams",
    "survey_investigation_team_members",
    "survey_investigation_team_forms",
    "survey_investigation_participants",
    "lap-to",
    "tao-ngau-nhien",
    "chot-gui",
    "SENT",
    "DRAFT",
    "team_id",
    "team_number",
    "household_id",
    "hamlet_name",
    "thôn",
    "xóm",
    "khối",
    "bản",
    "tổ",
    "expected",
    "household",
    "them_ho_dan",
    "ho-dan/them",
    "nhap-nhanh",
    "lay_thong_tin_nguoi_dung",
    "GIAO_VIEN",
    "COMMUNE_ROLE_CODE",
    "2.2.1",
    "Cập nhật dữ liệu hộ dân",
]


def read_text(path: Path) -> str:
    for enc in ("utf-8-sig", "utf-8", "cp1258"):
        try:
            return path.read_text(encoding=enc)
        except Exception:
            pass
    return ""


def add_context(report: list[str], path: Path, max_blocks: int = 80) -> None:
    report.append("")
    report.append("=" * 118)
    report.append(f"SOURCE: {path}")
    report.append("=" * 118)

    if not path.is_file():
        report.append("KHÔNG TỒN TẠI")
        return

    text = read_text(path)
    lines = text.splitlines()
    report.append(f"Số dòng: {len(lines)} | Kích thước: {path.stat().st_size} bytes")

    ranges: list[tuple[int, int]] = []
    for i, line in enumerate(lines, 1):
        low = line.lower()
        if any(k.lower() in low for k in KEYWORDS):
            start = max(1, i - 5)
            end = min(len(lines), i + 10)
            if ranges and start <= ranges[-1][1] + 2:
                ranges[-1] = (ranges[-1][0], max(ranges[-1][1], end))
            else:
                ranges.append((start, end))

    report.append(f"Số khối liên quan: {len(ranges)}")

    for start, end in ranges[:max_blocks]:
        report.append("")
        report.append(f"--- L{start}-L{end} ---")
        for n in range(start, end + 1):
            report.append(f"{n:05d}: {lines[n-1]}")

    if len(ranges) > max_blocks:
        report.append(f"... còn {len(ranges) - max_blocks} khối không in.")


def table_exists(con: sqlite3.Connection, name: str) -> bool:
    return con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone() is not None


def schema(con: sqlite3.Connection, table: str):
    return con.execute(f'PRAGMA table_info("{table}")').fetchall()


def foreign_keys(con: sqlite3.Connection, table: str):
    return con.execute(f'PRAGMA foreign_key_list("{table}")').fetchall()


def main():
    EXPORTS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = EXPORTS / (
        "bao_cao_khao_sat_bai_13b_12_v2_"
        f"dia_ban_to_dieu_tra_{stamp}.txt"
    )

    report: list[str] = []
    report.append("=" * 118)
    report.append(
        "KHẢO SÁT BÀI 13B-12 V2 - "
        "DANH MỤC ĐỊA BÀN + TỔ ĐIỀU TRA TẠO HỘ MỚI"
    )
    report.append("=" * 118)
    report.append(f"Thời gian: {datetime.now():%d/%m/%Y %H:%M:%S}")
    report.append(f"Dự án: {PROJECT}")
    report.append("")
    report.append("NGHIỆP VỤ ĐÃ CHỐT")
    report.append("1. KHÔNG tạo menu 2.2.8.")
    report.append("2. Nút lớn '➕ Điều tra mới – Nhập hộ dân mới' nằm tại 2.2.1.")
    report.append("3. Cấp Xã không nhập hộ mới; chỉ tổ điều tra được giao nhiệm vụ mới tạo hộ tại thực địa.")
    report.append("4. Cấp Xã quản lý Danh mục thôn/xóm/khối/tổ/bản và số hộ dự kiến.")
    report.append("5. Hệ thống tính Số hộ dự kiến / Đã nhập thực tế / Còn thiếu / % hoàn thành.")
    report.append("6. Khi tạo hộ, tổ điều tra bắt buộc chọn địa bàn từ danh mục.")
    report.append("7. Giữ nguyên toàn bộ phân công tổ 3 cấp, giao phiếu, nhập nhanh, khóa/mở và các chức năng đã có.")
    report.append("8. Dữ liệu học sinh 2025-2026 chỉ dùng liên năm/đối chiếu, không tạo hộ 2026-2027.")
    report.append("")

    report.append("I. KHẢO SÁT SOURCE")
    for path in SOURCE_FILES:
        add_context(report, path)

    report.append("")
    report.append("=" * 118)
    report.append("II. DATABASE")
    report.append("=" * 118)

    if not DB.is_file():
        report.append(f"KHÔNG TÌM THẤY DB: {DB}")
    else:
        con = sqlite3.connect(str(DB))
        con.row_factory = sqlite3.Row
        try:
            integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
            fk_errors = con.execute("PRAGMA foreign_key_check").fetchall()
            report.append(f"integrity_check: {integrity}")
            report.append(f"foreign_key_check: {len(fk_errors)} lỗi")

            all_tables = [
                r["name"]
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

            report.append("")
            report.append("A. BẢNG CÓ THỂ ĐÃ LÀ DANH MỤC ĐỊA BÀN")
            candidates = [
                t for t in all_tables
                if any(
                    token in t.lower()
                    for token in (
                        "hamlet", "village", "area", "zone",
                        "neighborhood", "residential", "ward",
                        "thon", "xom", "khoi", "ban"
                    )
                )
            ]
            if candidates:
                for t in candidates:
                    report.append(f" - {t}")
            else:
                report.append(" - Không thấy bảng tên gợi ý danh mục thôn/xóm/khối/tổ/bản.")

            report.append("")
            report.append("B. CỘT ĐỊA BÀN / SỐ HỘ DỰ KIẾN TRONG TOÀN DB")
            column_hits = []
            for t in all_tables:
                try:
                    cols = schema(con, t)
                except Exception:
                    continue
                for c in cols:
                    name = str(c["name"])
                    low = name.lower()
                    if any(
                        token in low
                        for token in (
                            "hamlet", "village", "area", "zone",
                            "neighborhood", "residential",
                            "thon", "xom", "khoi", "ban",
                            "household_count", "expected_house",
                            "target_house"
                        )
                    ):
                        column_hits.append((t, name, c["type"]))
            if column_hits:
                for t, c, typ in column_hits:
                    report.append(f" - {t}.{c} | {typ}")
            else:
                report.append(" - Không thấy cột phù hợp ngoài các trường địa chỉ hiện hành.")

            important_tables = [
                "households",
                "survey_forms",
                "survey_form_investigators",
                "survey_investigation_participants",
                "survey_investigation_teams",
                "survey_investigation_team_members",
                "survey_investigation_team_forms",
                "survey_team_generation_logs",
                "survey_participant_submissions",
                "survey_batches",
                "communes",
                "users",
            ]

            report.append("")
            report.append("C. SCHEMA CÁC BẢNG CỐT LÕI")
            for t in important_tables:
                report.append("")
                report.append(f"[{t}]")
                if not table_exists(con, t):
                    report.append("  KHÔNG TỒN TẠI")
                    continue

                count = con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
                report.append(f"  rows={count}")

                for c in schema(con, t):
                    report.append(
                        f"  - {c['name']} | {c['type']} | "
                        f"notnull={c['notnull']} | pk={c['pk']} | default={c['dflt_value']}"
                    )

                fks = foreign_keys(con, t)
                if fks:
                    report.append("  foreign keys:")
                    for fk in fks:
                        report.append(
                            f"    {fk['from']} -> {fk['table']}.{fk['to']} "
                            f"| on_delete={fk['on_delete']}"
                        )

            report.append("")
            report.append("=" * 118)
            report.append("III. MẪU DỮ LIỆU TỔ ĐIỀU TRA / HỘ / PHIẾU")
            report.append("=" * 118)

            batch = None
            if table_exists(con, "survey_batches"):
                batch = con.execute(
                    """
                    SELECT sb.id, sb.code, sb.commune_id, sb.school_year_id,
                           c.name AS commune_name
                    FROM survey_batches sb
                    LEFT JOIN communes c ON c.id = sb.commune_id
                    WHERE sb.id = 114
                    LIMIT 1
                    """
                ).fetchone()

                if batch is None:
                    batch = con.execute(
                        """
                        SELECT sb.id, sb.code, sb.commune_id, sb.school_year_id,
                               c.name AS commune_name
                        FROM survey_batches sb
                        LEFT JOIN communes c ON c.id = sb.commune_id
                        ORDER BY sb.id DESC
                        LIMIT 1
                        """
                    ).fetchone()

            if batch is None:
                report.append("Không tìm thấy survey_batch để lấy mẫu.")
            else:
                batch_id = int(batch["id"])
                report.append(
                    f"Đợt mẫu: #{batch_id} | {batch['code']} | "
                    f"xã={batch['commune_name']} | commune_id={batch['commune_id']}"
                )

                queries = [
                    (
                        "TỔ",
                        """
                        SELECT id, team_number, status, generation_code,
                               commune_id, created_by_user_id, created_at, updated_at
                        FROM survey_investigation_teams
                        WHERE survey_batch_id=?
                        ORDER BY team_number
                        """,
                    ),
                    (
                        "THÀNH VIÊN TỔ",
                        """
                        SELECT t.team_number, tm.team_id, tm.user_id,
                               tm.school_id, tm.level_code, tm.order_number,
                               u.username, u.full_name
                        FROM survey_investigation_team_members tm
                        JOIN survey_investigation_teams t ON t.id=tm.team_id
                        LEFT JOIN users u ON u.id=tm.user_id
                        WHERE t.survey_batch_id=?
                        ORDER BY t.team_number, tm.order_number
                        """,
                    ),
                    (
                        "PHIẾU GẮN TỔ",
                        """
                        SELECT t.team_number, tf.team_id, tf.survey_form_id,
                               tf.assignment_order, sf.form_number,
                               sf.household_id, sf.status,
                               h.hamlet_name, h.head_name, h.address
                        FROM survey_investigation_team_forms tf
                        JOIN survey_investigation_teams t ON t.id=tf.team_id
                        JOIN survey_forms sf ON sf.id=tf.survey_form_id
                        JOIN households h ON h.id=sf.household_id
                        WHERE t.survey_batch_id=?
                        ORDER BY t.team_number, tf.assignment_order
                        """,
                    ),
                    (
                        "NGƯỜI ĐIỀU TRA CHÍNH THỨC TRÊN PHIẾU",
                        """
                        SELECT sf.id AS survey_form_id, sf.form_number,
                               sfi.user_id, u.username, u.full_name,
                               sfi.order_number, sfi.is_primary, sfi.notes
                        FROM survey_forms sf
                        JOIN survey_form_investigators sfi ON sfi.survey_form_id=sf.id
                        LEFT JOIN users u ON u.id=sfi.user_id
                        WHERE sf.survey_batch_id=?
                        ORDER BY sf.id, sfi.order_number
                        """,
                    ),
                ]

                for title, sql in queries:
                    report.append("")
                    report.append(f"[{title}]")
                    try:
                        rows = con.execute(sql, (batch_id,)).fetchall()
                        report.append(f"Số dòng: {len(rows)}")
                        for row in rows[:30]:
                            report.append(
                                "  " + " | ".join(
                                    f"{k}={row[k]}" for k in row.keys()
                                )
                            )
                        if len(rows) > 30:
                            report.append(f"  ... còn {len(rows)-30} dòng.")
                    except Exception as exc:
                        report.append(f"ERROR: {type(exc).__name__}: {exc}")

            report.append("")
            report.append("=" * 118)
            report.append("IV. RÀNG BUỘC CHO LUỒNG MỚI")
            report.append("=" * 118)

            if table_exists(con, "survey_investigation_team_forms"):
                idx_rows = con.execute(
                    "PRAGMA index_list('survey_investigation_team_forms')"
                ).fetchall()
                report.append("[INDEX survey_investigation_team_forms]")
                for idx in idx_rows:
                    report.append(
                        f" - {idx['name']} | unique={idx['unique']} | origin={idx['origin']}"
                    )
                    try:
                        cols = con.execute(
                            f"PRAGMA index_info('{idx['name']}')"
                        ).fetchall()
                        report.append(
                            "   cols=" + ", ".join(str(c["name"]) for c in cols)
                        )
                    except Exception:
                        pass

            report.append("")
            report.append("Câu hỏi kỹ thuật cần trả lời:")
            report.append("1. Có thể giữ survey_investigation_team_forms để gắn phiếu MỚI vào tổ sau khi tổ tạo hộ hay không?")
            report.append("2. Có bảng danh mục địa bàn sẵn để tái sử dụng hay phải thêm bảng mới?")
            report.append("3. Có cần bảng giao địa bàn/chỉ tiêu hộ cho tổ (nhiều-tổ/nhiều-địa-bàn) hay không?")
            report.append("4. Route ghép tổ hiện có có bắt buộc phải có survey_forms trước khi tạo tổ hay không?")
            report.append("5. Route chốt/gửi hiện có có thể chốt tổ khi chưa có phiếu hay đang phụ thuộc survey_form_investigators?")
            report.append("6. Tài khoản giáo viên có thể suy ra team_id của mình từ survey_investigation_team_members hay không?")
            report.append("7. Khi GV trong tổ tạo hộ, có thể tự gắn 3 thành viên tổ vào survey_form_investigators mà không phá quyền hiện có hay không?")

        finally:
            con.close()

    report.append("")
    report.append("=" * 118)
    report.append("V. NGUYÊN TẮC THIẾT KẾ V2 - CHỈ GHI NHẬN, CHƯA CÀI")
    report.append("=" * 118)
    report.append("- Xã chỉ khai báo địa bàn và số hộ dự kiến; Xã KHÔNG nhập hộ.")
    report.append("- Tổ điều tra tạo hộ mới tại thực địa.")
    report.append("- Nút tạo hộ chỉ xuất hiện tại 2.2.1 cho người thuộc tổ đã được xã chốt/gửi.")
    report.append("- Hộ mới phải thuộc đúng commune_id, survey_batch_id và địa bàn được giao cho tổ.")
    report.append("- Sau khi tạo hộ, phiếu phải tự gắn team_id và đủ 3 thành viên tổ để cả tổ cùng nhìn thấy.")
    report.append("- Số hộ đã nhập phải đếm từ SurveyForm/Household thực tế, không nhập tay.")
    report.append("- Số hộ dự kiến chỉ là chỉ tiêu theo địa bàn để tính Còn thiếu và % hoàn thành.")
    report.append("- Không xóa cơ chế team_forms / form_investigators hiện có; ưu tiên tái sử dụng.")
    report.append("- Không thay dữ liệu học sinh 2025-2026; phần đó chỉ dùng đối chiếu sau.")
    report.append("")
    report.append("KHẢO SÁT CHỈ ĐỌC - KHÔNG INSERT / UPDATE / DELETE / ALTER.")

    report_path.write_text(
        "\n".join(report) + "\n",
        encoding="utf-8-sig",
    )

    print("=" * 118)
    print("KHẢO SÁT BÀI 13B-12 V2 HOÀN TẤT")
    print("=" * 118)
    print("KHÔNG thay đổi source hoặc database.")
    print("Báo cáo:", report_path)
    print("Hãy gửi file báo cáo này để làm bộ cài V2 an toàn.")


if __name__ == "__main__":
    main()
