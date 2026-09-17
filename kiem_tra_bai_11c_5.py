from __future__ import annotations

import sqlite3
from pathlib import Path

from app.database import DATABASE_PATH


EXPECTED = {
    "admin.sogddt": "ADMIN",
    "p_gdmn": "PHONG_BAN",
}


def main() -> None:
    database_path = Path(DATABASE_PATH)
    connection = sqlite3.connect(str(database_path))
    connection.row_factory = sqlite3.Row

    try:
        print("=" * 72)
        print("BÀI 11C-5 - KIỂM TRA SAU KHI CHUYỂN TÀI KHOẢN")
        print("=" * 72)

        total_users = connection.execute(
            "SELECT COUNT(*) FROM users"
        ).fetchone()[0]

        for username, expected_role in EXPECTED.items():
            rows = connection.execute(
                """
                SELECT
                    u.id,
                    u.username,
                    u.full_name,
                    r.code AS role_code,
                    u.commune_id,
                    u.school_id,
                    u.is_active
                FROM users AS u
                JOIN roles AS r
                    ON r.id = u.role_id
                WHERE LOWER(u.username) = LOWER(?)
                """,
                (username,),
            ).fetchall()

            if len(rows) != 1:
                raise RuntimeError(
                    f"{username} có {len(rows)} bản ghi; yêu cầu đúng 1."
                )

            row = rows[0]

            if str(row["role_code"]).upper() != expected_role:
                raise RuntimeError(
                    f"{username} đang là {row['role_code']}; "
                    f"yêu cầu {expected_role}."
                )

            if row["commune_id"] is not None:
                raise RuntimeError(
                    f"{username} đang gắn commune_id={row['commune_id']}."
                )

            if row["school_id"] is not None:
                raise RuntimeError(
                    f"{username} đang gắn school_id={row['school_id']}."
                )

            if int(row["is_active"]) != 1:
                raise RuntimeError(
                    f"{username} đang không hoạt động."
                )

            print(
                f"OK USER: id={row['id']} | "
                f"username={row['username']} | "
                f"full_name={row['full_name']} | "
                f"role={row['role_code']} | "
                f"is_active={row['is_active']}"
            )

        so_count = connection.execute(
            """
            SELECT COUNT(*)
            FROM users AS u
            JOIN roles AS r
                ON r.id = u.role_id
            WHERE UPPER(r.code) = 'SO'
            """
        ).fetchone()[0]

        admin_count = connection.execute(
            """
            SELECT COUNT(*)
            FROM users AS u
            JOIN roles AS r
                ON r.id = u.role_id
            WHERE UPPER(r.code) = 'ADMIN'
            """
        ).fetchone()[0]

        department_count = connection.execute(
            """
            SELECT COUNT(*)
            FROM users AS u
            JOIN roles AS r
                ON r.id = u.role_id
            WHERE UPPER(r.code) = 'PHONG_BAN'
            """
        ).fetchone()[0]

        print()
        print("=== TỔNG HỢP ===")
        print(f"Tổng số tài khoản: {total_users}")
        print(f"SO: {so_count}")
        print(f"ADMIN: {admin_count}")
        print(f"PHONG_BAN: {department_count}")

        if so_count != 0:
            raise RuntimeError(
                f"Vẫn còn {so_count} tài khoản mang vai trò SO."
            )

        if admin_count != 1:
            raise RuntimeError(
                f"Số tài khoản ADMIN là {admin_count}; yêu cầu 1."
            )

        if department_count != 1:
            raise RuntimeError(
                "Số tài khoản PHONG_BAN là "
                f"{department_count}; yêu cầu 1."
            )

        print()
        print("BÀI 11C-5 ĐÃ HOÀN THÀNH.")
        print("admin.sogddt = ADMIN")
        print("p_gdmn = PHONG_BAN")
        print("Không còn tài khoản nào mang vai trò SO.")

    finally:
        connection.close()


if __name__ == "__main__":
    main()
