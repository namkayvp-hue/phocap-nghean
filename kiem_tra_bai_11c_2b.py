from __future__ import annotations

import sqlite3
from pathlib import Path

from app.database import DATABASE_PATH


def main() -> None:
    database_path = Path(DATABASE_PATH)
    connection = sqlite3.connect(str(database_path))
    connection.row_factory = sqlite3.Row

    try:
        rows = connection.execute(
            """
            SELECT
                u.id,
                u.username,
                u.full_name,
                u.role_id,
                r.code AS role_code,
                r.name AS role_name,
                u.commune_id,
                u.school_id,
                u.is_active,
                u.created_at
            FROM users AS u
            JOIN roles AS r
                ON r.id = u.role_id
            WHERE UPPER(r.code) = 'SO'
            ORDER BY
                CASE
                    WHEN LOWER(u.username) = 'admin.sogddt' THEN 0
                    ELSE 1
                END,
                u.id
            """
        ).fetchall()

        print("=== DANH SACH TAI KHOAN CAP SO HIEN CO ===")
        print(f"TONG SO TAI KHOAN SO: {len(rows)}")
        print()

        if not rows:
            print("KHONG CO TAI KHOAN NAO MANG VAI TRO SO.")
        else:
            for index, row in enumerate(rows, start=1):
                print(f"--- TAI KHOAN {index} ---")
                print(f"id={row['id']}")
                print(f"username={row['username']}")
                print(f"full_name={row['full_name']}")
                print(f"role_id={row['role_id']}")
                print(f"role_code={row['role_code']}")
                print(f"role_name={row['role_name']}")
                print(f"commune_id={row['commune_id']}")
                print(f"school_id={row['school_id']}")
                print(f"is_active={row['is_active']}")
                print(f"created_at={row['created_at']}")
                print()

        print("=== DU KIEN CHUYEN DOI ===")
        admin_rows = [
            row for row in rows
            if str(row["username"]).strip().lower() == "admin.sogddt"
        ]
        other_rows = [
            row for row in rows
            if str(row["username"]).strip().lower() != "admin.sogddt"
        ]

        print(
            "admin.sogddt -> ADMIN: "
            + ("TIM THAY" if len(admin_rows) == 1 else f"BAT THUONG ({len(admin_rows)} dong)")
        )
        print(f"Tai khoan SO con lai can xac minh: {len(other_rows)}")

        for row in other_rows:
            print(
                f"- id={row['id']} | username={row['username']} | "
                f"full_name={row['full_name']} | is_active={row['is_active']}"
            )

        print()
        print(
            "HOAN TAT: chi doc du lieu, "
            "khong them, sua hoac xoa tai khoan."
        )

    finally:
        connection.close()


if __name__ == "__main__":
    main()
