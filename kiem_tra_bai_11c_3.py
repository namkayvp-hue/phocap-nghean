from __future__ import annotations

import sqlite3
from pathlib import Path

from app.database import DATABASE_PATH


def main() -> None:
    database_path = Path(DATABASE_PATH)
    connection = sqlite3.connect(str(database_path))
    connection.row_factory = sqlite3.Row

    try:
        print("=== KIỂM TRA BÀI 11C-3 ===")

        expected_roles = {
            "ADMIN": "Quản trị hệ thống",
            "PHONG_BAN": "Phòng ban",
        }

        for code, expected_name in expected_roles.items():
            rows = connection.execute(
                """
                SELECT id, code, name, description
                FROM roles
                WHERE UPPER(code) = UPPER(?)
                """,
                (code,),
            ).fetchall()

            if len(rows) != 1:
                raise RuntimeError(
                    f"Vai trò {code} có {len(rows)} bản ghi; yêu cầu đúng 1."
                )

            row = rows[0]
            print(
                f"OK ROLE: id={row['id']} | "
                f"code={row['code']} | name={row['name']}"
            )

            if not row["description"]:
                raise RuntimeError(
                    f"Vai trò {code} chưa có mô tả."
                )

        expected_users = {
            "admin.sogddt": "SO",
            "p_gdmn": "SO",
        }

        for username, expected_role in expected_users.items():
            row = connection.execute(
                """
                SELECT u.username, r.code AS role_code
                FROM users AS u
                JOIN roles AS r ON r.id = u.role_id
                WHERE LOWER(u.username) = LOWER(?)
                """,
                (username,),
            ).fetchone()

            if row is None:
                raise RuntimeError(
                    f"Không tìm thấy tài khoản {username}."
                )

            if str(row["role_code"]).upper() != expected_role:
                raise RuntimeError(
                    f"{username} đang có vai trò {row['role_code']}; "
                    f"giai đoạn này phải vẫn là {expected_role}."
                )

            print(
                f"OK USER CHƯA CHUYỂN: "
                f"{row['username']} | role={row['role_code']}"
            )

        print()
        print("BÀI 11C-3 ĐÃ HOÀN THÀNH.")
        print("ADMIN và PHONG_BAN đã có trong danh mục roles.")
        print("Hai tài khoản cấp Sở vẫn chưa bị chuyển vai trò.")

    finally:
        connection.close()


if __name__ == "__main__":
    main()
