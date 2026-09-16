import sqlite3

from app.database import DATABASE_PATH


def main() -> None:
    connection = sqlite3.connect(DATABASE_PATH)

    try:
        cursor = connection.cursor()

        print("=" * 60)
        print("KIỂM TRA CƠ SỞ DỮ LIỆU")
        print("=" * 60)

        cursor.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
            ORDER BY name
            """
        )

        tables = cursor.fetchall()

        print("\nDanh sách bảng:")

        for table in tables:
            print(f"- {table[0]}")

        cursor.execute(
            """
            SELECT id, code, name, description
            FROM roles
            ORDER BY id
            """
        )

        roles = cursor.fetchall()

        print("\nDanh sách vai trò:")

        for role in roles:
            role_id, code, name, description = role

            print(
                f"{role_id}. {code} - {name}: "
                f"{description}"
            )

    finally:
        connection.close()


if __name__ == "__main__":
    main()