from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

PROJECT = Path(r"C:\PhoCap")
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from app.database import DATABASE_PATH  # noqa: E402


def print_rows(rows) -> None:
    if not rows:
        print("(không có)")
        return
    for row in rows:
        print(" | ".join(f"{key}={row[key]}" for key in row.keys()))


def main() -> None:
    db_path = Path(DATABASE_PATH)

    print("=" * 110)
    print("KIỂM TRA SAU KHI CHỐT/GỬI TỔ 3 CẤP - CHỈ ĐỌC, KHÔNG SỬA DATABASE")
    print("=" * 110)
    print(f"Database: {db_path}")
    print()

    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row

    try:
        batch = con.execute(
            """
            SELECT
                sb.id,
                sb.name,
                sb.status,
                sb.school_year_id,
                sy.code AS school_year_code,
                sb.commune_id,
                c.code AS commune_code,
                c.name AS commune_name
            FROM survey_batches sb
            JOIN school_years sy ON sy.id = sb.school_year_id
            JOIN communes c ON c.id = sb.commune_id
            WHERE sb.id = 3
            """
        ).fetchone()

        print("=== 1. ĐỢT #3 ===")
        if batch:
            print(" | ".join(f"{k}={batch[k]}" for k in batch.keys()))
        else:
            print("KHÔNG TÌM THẤY survey_batches.id = 3")
        print()

        print("=== 2. CÁC TRƯỜNG LIÊN QUAN TRONG PHƯỜNG CỬA LÒ ===")
        school_rows = con.execute(
            """
            SELECT
                s.id,
                s.code,
                s.name,
                s.level,
                s.commune_id,
                c.name AS commune_name,
                s.is_active
            FROM schools s
            LEFT JOIN communes c ON c.id = s.commune_id
            WHERE s.commune_id = 58
              AND (
                    s.name LIKE '%Hải Hòa%'
                    OR s.name LIKE '%Nghi Hương%'
                    OR s.name LIKE '%Nghi Hải%'
                  )
            ORDER BY s.name, s.id
            """
        ).fetchall()
        print_rows(school_rows)
        print()

        print("=== 3. TÀI KHOẢN TRƯỜNG Ở PHƯỜNG CỬA LÒ ===")
        school_accounts = con.execute(
            """
            SELECT
                u.id AS user_id,
                u.username,
                u.full_name,
                r.code AS role_code,
                u.school_id,
                s.code AS school_code,
                s.name AS school_name,
                u.commune_id,
                c.name AS commune_name,
                u.is_active
            FROM users u
            JOIN roles r ON r.id = u.role_id
            LEFT JOIN schools s ON s.id = u.school_id
            LEFT JOIN communes c ON c.id = u.commune_id
            WHERE UPPER(r.code) = 'TRUONG'
              AND (
                    u.commune_id = 58
                    OR s.commune_id = 58
                  )
            ORDER BY s.name, u.username
            """
        ).fetchall()
        print_rows(school_accounts)
        print()

        print("=== 4. CÁC TỔ CỦA ĐỢT #3 ===")
        teams = con.execute(
            """
            SELECT
                id,
                team_number,
                status,
                commune_id,
                generation_code
            FROM survey_investigation_teams
            WHERE survey_batch_id = 3
            ORDER BY team_number
            """
        ).fetchall()
        print_rows(teams)
        print()

        print("=== 5. THÀNH VIÊN TỔ: SO SÁNH tm.school_id VỚI users.school_id ===")
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
                ts.name AS team_school_name,
                u.school_id AS user_school_id,
                us.name AS user_school_name,
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
        print()

        print("=== 6. PHIẾU CỦA CÁC TỔ VÀ NGƯỜI ĐIỀU TRA ĐÃ GHI CHÍNH THỨC ===")
        assignments = con.execute(
            """
            SELECT
                t.team_number,
                tf.survey_form_id,
                sf.form_number,
                sfi.order_number,
                sfi.is_primary,
                sfi.user_id,
                u.username,
                u.full_name,
                r.code AS role_code,
                u.school_id,
                s.name AS school_name,
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
        print()

        print("=== 7. SỐ PHIẾU MỖI school_id NHÌN THẤY THEO LOGIC /dieu-tra ===")
        visible = con.execute(
            """
            SELECT
                u.school_id,
                s.name AS school_name,
                COUNT(DISTINCT sf.id) AS visible_forms,
                COUNT(DISTINCT sf.survey_batch_id) AS visible_batches
            FROM survey_forms sf
            JOIN survey_form_investigators sfi
                 ON sfi.survey_form_id = sf.id
            JOIN users u ON u.id = sfi.user_id
            LEFT JOIN schools s ON s.id = u.school_id
            WHERE sf.survey_batch_id = 3
              AND u.is_active = 1
            GROUP BY u.school_id, s.name
            ORDER BY s.name
            """
        ).fetchall()
        print_rows(visible)
        print()

        print("=== 8. KIỂM TRA RIÊNG TỪNG TÀI KHOẢN TRƯỜNG ===")
        for acc in school_accounts:
            school_id = acc["school_id"]
            if school_id is None:
                count_value = 0
            else:
                count_value = con.execute(
                    """
                    SELECT COUNT(DISTINCT sf.id)
                    FROM survey_forms sf
                    JOIN survey_form_investigators sfi
                         ON sfi.survey_form_id = sf.id
                    JOIN users gv ON gv.id = sfi.user_id
                    WHERE sf.survey_batch_id = 3
                      AND gv.school_id = ?
                      AND gv.is_active = 1
                    """,
                    (int(school_id),),
                ).fetchone()[0]

            print(
                f"{acc['school_name']} | username={acc['username']} | "
                f"school_id={school_id} | visible_forms_batch_3={count_value}"
            )
        print()

        print("=== 9. KẾT LUẬN TỰ ĐỘNG ===")
        sent_teams = sum(
            1 for row in teams
            if str(row["status"] or "") == "SENT"
        )

        sfi_count = con.execute(
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

        print(f"- Tổ SENT: {sent_teams}/{len(teams)}")
        print(f"- Lượt phân công chính thức: {sfi_count}")
        print(f"- Thành viên lệch tm.school_id / users.school_id: {mismatch_count}")

        if sent_teams == len(teams) and len(teams) > 0 and sfi_count == len(teams) * 3:
            print("- Chốt/gửi đã ghi đủ về mặt số lượng.")
        else:
            print("- Chốt/gửi CHƯA đủ về mặt số lượng.")

        if mismatch_count:
            print(
                "- Có lệch school_id của giáo viên so với trường đã gửi. "
                "Đây có thể là nguyên nhân tài khoản Trường hiện 0 đợt."
            )
        else:
            print(
                "- school_id của thành viên tổ đang khớp. "
                "Hãy đối chiếu school_id của tài khoản Trường với các dòng visible_forms_batch_3."
            )

        print()
        print("HOÀN TẤT: script chỉ đọc dữ liệu, KHÔNG INSERT/UPDATE/DELETE.")

    finally:
        con.close()


if __name__ == "__main__":
    main()
