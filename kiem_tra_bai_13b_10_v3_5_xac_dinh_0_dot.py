from __future__ import annotations

import sqlite3
from pathlib import Path

PROJECT = Path(r"C:\PhoCap")
DB = PROJECT / "data" / "phocap.db"
SURVEYS = PROJECT / "app" / "routers" / "surveys.py"


def section(title: str) -> None:
    print()
    print("=" * 120)
    print(title)
    print("=" * 120)


def table_columns(con: sqlite3.Connection, table: str) -> list[str]:
    return [row["name"] for row in con.execute(f"PRAGMA table_info({table})").fetchall()]


def print_rows(rows) -> None:
    if not rows:
        print("(không có)")
        return
    for row in rows:
        print(" | ".join(f"{key}={row[key]}" for key in row.keys()))


def main() -> None:
    print("KIỂM TRA BÀI 13B-10 V3.5 - XÁC ĐỊNH CHÍNH XÁC VÌ SAO TRƯỜNG VẪN 0 ĐỢT")
    print("CHỈ ĐỌC - KHÔNG INSERT / UPDATE / DELETE")
    print(f"Database: {DB}")

    if not DB.exists():
        raise SystemExit(f"Không tìm thấy database: {DB}")

    con = sqlite3.connect(str(DB))
    con.row_factory = sqlite3.Row

    try:
        section("1. KIỂM TRA V3.4 CÓ THỰC SỰ NẰM TRONG surveys.py KHÔNG")
        if SURVEYS.exists():
            text = SURVEYS.read_text(encoding="utf-8-sig")
            checks = {
                "marker_v3_4": "BAI_13B_10_V3_4_SCHOOL_TEACHER_BATCH_SCOPE" in text,
                "apply_commune_filter": "apply_commune_filter = True" in text,
                "school_teacher_skip_commune": "role_code in {SCHOOL_ROLE_CODE, TEACHER_ROLE_CODE}" in text,
                "conditional_commune_filter": "if commune_id is not None and apply_commune_filter:" in text,
            }
            for key, value in checks.items():
                print(f"{key}: {value}")
        else:
            print(f"Không tìm thấy {SURVEYS}")

        section("2. SCHEMA THỰC TẾ CÁC BẢNG LIÊN QUAN")
        for table in (
            "communes",
            "schools",
            "users",
            "roles",
            "survey_batches",
            "survey_forms",
            "survey_form_investigators",
            "survey_investigation_teams",
            "survey_investigation_team_members",
            "survey_investigation_team_forms",
        ):
            print(f"{table}: {table_columns(con, table)}")

        section("3. ĐỢT #3")
        batch = con.execute(
            """
            SELECT
                sb.id,
                sb.code,
                sb.name,
                sb.status,
                sb.school_year_id,
                sy.code AS school_year_code,
                sb.commune_id,
                c.code AS commune_code,
                c.name AS commune_name
            FROM survey_batches sb
            LEFT JOIN school_years sy ON sy.id = sb.school_year_id
            LEFT JOIN communes c ON c.id = sb.commune_id
            WHERE sb.id = 3
            """
        ).fetchall()
        print_rows(batch)

        section("4. SO SÁNH COMMUNE ID 5 VÀ 58")
        communes = con.execute(
            """
            SELECT id, code, name, is_active
            FROM communes
            WHERE id IN (5, 58)
            ORDER BY id
            """
        ).fetchall()
        print_rows(communes)

        section("5. TÀI KHOẢN TRƯỜNG THCS HẢI HÒA / CÁC TÀI KHOẢN TRƯỜNG CỬA LÒ")
        school_accounts = con.execute(
            """
            SELECT
                u.id AS user_id,
                u.username,
                u.full_name,
                r.code AS role_code,
                u.commune_id AS user_commune_id,
                uc.code AS user_commune_code,
                uc.name AS user_commune_name,
                u.school_id,
                s.code AS school_code,
                s.name AS school_name,
                s.commune_id AS school_commune_id,
                sc.code AS school_commune_code,
                sc.name AS school_commune_name,
                u.is_active
            FROM users u
            JOIN roles r ON r.id = u.role_id
            LEFT JOIN communes uc ON uc.id = u.commune_id
            LEFT JOIN schools s ON s.id = u.school_id
            LEFT JOIN communes sc ON sc.id = s.commune_id
            WHERE UPPER(r.code) = 'TRUONG'
              AND (
                    s.name LIKE '%Hải Hòa%'
                 OR s.name LIKE '%Nghi Hương%'
                 OR s.name LIKE '%Nghi Hải%'
                 OR uc.code = '16732'
                 OR sc.code = '16732'
              )
            ORDER BY s.name, u.username
            """
        ).fetchall()
        print_rows(school_accounts)

        section("6. 5 TỔ CỦA ĐỢT #3")
        teams = con.execute(
            """
            SELECT id, team_number, status, commune_id, generation_code
            FROM survey_investigation_teams
            WHERE survey_batch_id = 3
            ORDER BY team_number
            """
        ).fetchall()
        print_rows(teams)

        section("7. THÀNH VIÊN TỔ - ĐỐI CHIẾU TRƯỜNG LƯU TRONG TỔ VÀ TRƯỜNG CỦA USER")
        members = con.execute(
            """
            SELECT
                t.team_number,
                tm.level_code,
                tm.order_number,
                tm.user_id,
                u.username,
                u.full_name,
                r.code AS role_code,
                tm.school_id AS team_school_id,
                ts.code AS team_school_code,
                ts.name AS team_school_name,
                ts.commune_id AS team_school_commune_id,
                u.school_id AS user_school_id,
                us.code AS user_school_code,
                us.name AS user_school_name,
                us.commune_id AS user_school_commune_id,
                CASE
                    WHEN tm.school_id = u.school_id THEN 'KHOP'
                    ELSE 'LECH'
                END AS school_id_check,
                u.is_active
            FROM survey_investigation_team_members tm
            JOIN survey_investigation_teams t ON t.id = tm.team_id
            JOIN users u ON u.id = tm.user_id
            JOIN roles r ON r.id = u.role_id
            LEFT JOIN schools ts ON ts.id = tm.school_id
            LEFT JOIN schools us ON us.id = u.school_id
            WHERE t.survey_batch_id = 3
            ORDER BY t.team_number, tm.order_number
            """
        ).fetchall()
        print_rows(members)

        section("8. PHIẾU CỦA TỔ VÀ 3 PHÂN CÔNG CHÍNH THỨC")
        assignments = con.execute(
            """
            SELECT
                t.team_number,
                tf.survey_form_id,
                sf.form_number,
                sf.survey_batch_id,
                sfi.id AS assignment_id,
                sfi.order_number,
                sfi.is_primary,
                sfi.user_id,
                u.username,
                u.full_name,
                r.code AS role_code,
                u.school_id,
                s.code AS school_code,
                s.name AS school_name,
                s.commune_id AS school_commune_id,
                u.is_active
            FROM survey_investigation_team_forms tf
            JOIN survey_investigation_teams t ON t.id = tf.team_id
            JOIN survey_forms sf ON sf.id = tf.survey_form_id
            LEFT JOIN survey_form_investigators sfi
                   ON sfi.survey_form_id = tf.survey_form_id
            LEFT JOIN users u ON u.id = sfi.user_id
            LEFT JOIN roles r ON r.id = u.role_id
            LEFT JOIN schools s ON s.id = u.school_id
            WHERE t.survey_batch_id = 3
            ORDER BY t.team_number, sfi.order_number
            """
        ).fetchall()
        print_rows(assignments)

        section("9. ĐẾM PHIẾU THEO school_id - ĐÚNG LOGIC TRƯỜNG ĐANG DÙNG")
        visible = con.execute(
            """
            SELECT
                u.school_id,
                s.code AS school_code,
                s.name AS school_name,
                s.commune_id AS school_commune_id,
                COUNT(DISTINCT sf.id) AS visible_forms,
                COUNT(DISTINCT sf.survey_batch_id) AS visible_batches
            FROM survey_forms sf
            JOIN survey_form_investigators sfi
                 ON sfi.survey_form_id = sf.id
            JOIN users u ON u.id = sfi.user_id
            LEFT JOIN schools s ON s.id = u.school_id
            WHERE sf.survey_batch_id = 3
              AND u.is_active = 1
            GROUP BY u.school_id, s.code, s.name, s.commune_id
            ORDER BY s.name
            """
        ).fetchall()
        print_rows(visible)

        section("10. TỪNG TÀI KHOẢN TRƯỜNG: THEO school_id CÓ THẤY BAO NHIÊU PHIẾU ĐỢT #3")
        for acc in school_accounts:
            sid = acc["school_id"]
            visible_forms = 0
            if sid is not None:
                visible_forms = con.execute(
                    """
                    SELECT COUNT(DISTINCT sf.id)
                    FROM survey_forms sf
                    JOIN survey_form_investigators sfi
                         ON sfi.survey_form_id = sf.id
                    JOIN users assigned_user
                         ON assigned_user.id = sfi.user_id
                    WHERE sf.survey_batch_id = 3
                      AND assigned_user.school_id = ?
                      AND assigned_user.is_active = 1
                    """,
                    (int(sid),),
                ).fetchone()[0]
            print(
                f"username={acc['username']} | school={acc['school_name']} | "
                f"school_id={sid} | visible_forms_batch_3={visible_forms}"
            )

        section("11. KẾT LUẬN TỰ ĐỘNG")
        team_count = len(teams)
        sent_count = sum(
            1 for row in teams
            if str(row["status"] or "").upper() == "SENT"
        )
        assignment_count = con.execute(
            """
            SELECT COUNT(*)
            FROM survey_form_investigators sfi
            JOIN survey_forms sf ON sf.id = sfi.survey_form_id
            WHERE sf.survey_batch_id = 3
            """
        ).fetchone()[0]

        mismatch_count = sum(
            1 for row in members
            if row["school_id_check"] == "LECH"
        )

        print(f"Tổ SENT: {sent_count}/{team_count}")
        print(f"Lượt phân công chính thức đợt #3: {assignment_count}")
        print(f"Thành viên lệch team_school_id/user_school_id: {mismatch_count}")

        if team_count and sent_count == team_count:
            print("=> Trạng thái chốt tổ: ĐẠT.")
        else:
            print("=> Trạng thái chốt tổ: CHƯA ĐẠT.")

        if team_count and assignment_count == team_count * 3:
            print("=> Số lượt phân công: ĐẠT (mỗi tổ 3 người).")
        else:
            print("=> Số lượt phân công: CHƯA ĐẠT.")

        if mismatch_count == 0:
            print("=> school_id thành viên tổ khớp user: ĐẠT.")
        else:
            print("=> Có lệch school_id: cần sửa dữ liệu liên kết tài khoản.")

        haihoa = [
            row for row in school_accounts
            if row["school_name"] and "Hải Hòa" in row["school_name"]
        ]
        if haihoa:
            for acc in haihoa:
                sid = acc["school_id"]
                count_value = con.execute(
                    """
                    SELECT COUNT(DISTINCT sf.id)
                    FROM survey_forms sf
                    JOIN survey_form_investigators sfi
                         ON sfi.survey_form_id = sf.id
                    JOIN users assigned_user
                         ON assigned_user.id = sfi.user_id
                    WHERE sf.survey_batch_id = 3
                      AND assigned_user.school_id = ?
                      AND assigned_user.is_active = 1
                    """,
                    (int(sid),),
                ).fetchone()[0] if sid is not None else 0

                if count_value > 0:
                    print(
                        f"=> THCS Hải Hòa theo school_id={sid} ĐÁNG LẼ thấy "
                        f"{count_value} phiếu của đợt #3."
                    )
                    print(
                        "Nếu giao diện vẫn 0 đợt thì lỗi còn nằm ở SOURCE/bộ lọc route, "
                        "không phải dữ liệu phân công."
                    )
                else:
                    print(
                        f"=> THCS Hải Hòa school_id={sid} hiện KHÔNG có phiếu nào "
                        "liên kết qua giáo viên. Lỗi nằm ở dữ liệu liên kết/phân công."
                    )

        print()
        print("HOÀN TẤT. Script chỉ SELECT/PRAGMA, không sửa database.")

    finally:
        con.close()


if __name__ == "__main__":
    main()
