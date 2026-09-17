from __future__ import annotations

from pathlib import Path
import sqlite3

from app.database import DATABASE_PATH


def main() -> None:
    database_path = Path(DATABASE_PATH)
    app_root = Path(r"C:\PhoCap\app")

    connection = sqlite3.connect(str(database_path))
    cursor = connection.cursor()

    try:
        print("=== CAU TRUC BANG ROLES ===")
        for row in cursor.execute("PRAGMA table_info(roles)"):
            print(row)

        print()
        print("=== CHI MUC BANG ROLES ===")
        indexes = list(cursor.execute("PRAGMA index_list(roles)"))
        if not indexes:
            print("Khong co chi muc")
        else:
            for index_row in indexes:
                print(index_row)
                index_name = index_row[1]
                safe_index_name = str(index_name).replace("'", "''")
                for info_row in cursor.execute(
                    f"PRAGMA index_info('{safe_index_name}')"
                ):
                    print("   ", info_row)

        print()
        print("=== KHOA NGOAI BANG USERS ===")
        foreign_keys = list(cursor.execute("PRAGMA foreign_key_list(users)"))
        if not foreign_keys:
            print("Khong co khoa ngoai")
        else:
            for row in foreign_keys:
                print(row)

        print()
        print("=== SO LUONG TAI KHOAN THEO VAI TRO ===")
        query = """
            SELECT
                r.id,
                r.code,
                r.name,
                COUNT(u.id) AS user_count
            FROM roles AS r
            LEFT JOIN users AS u
                ON u.role_id = r.id
            GROUP BY
                r.id,
                r.code,
                r.name
            ORDER BY
                r.id
        """
        for row in cursor.execute(query):
            print(
                f"id={row[0]} | code={row[1]} | "
                f"name={row[2]} | users={row[3]}"
            )

        print()
        print("=== KIEM TRA MA VAI TRO MOI ===")
        for role_code in ("ADMIN", "PHONG_BAN"):
            row = cursor.execute(
                """
                SELECT id, code, name
                FROM roles
                WHERE UPPER(code) = UPPER(?)
                """,
                (role_code,),
            ).fetchone()

            if row is None:
                print(f"{role_code}: CHUA CO")
            else:
                print(
                    f"{role_code}: id={row[0]} | "
                    f"code={row[1]} | name={row[2]}"
                )

    finally:
        connection.close()

    print()
    print("=== CAC VI TRI DUNG MA VAI TRO TRONG MA NGUON ===")

    role_codes = ("SO", "XA", "TRUONG", "GIAO_VIEN")
    allowed_extensions = {".py", ".html", ".js", ".css"}
    match_count = 0

    if not app_root.exists():
        print(f"Khong tim thay thu muc ma nguon: {app_root}")
    else:
        for path in sorted(app_root.rglob("*")):
            if not path.is_file():
                continue

            if path.suffix.lower() not in allowed_extensions:
                continue

            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except UnicodeDecodeError:
                continue

            for line_number, line in enumerate(lines, start=1):
                if any(code in line for code in role_codes):
                    relative_path = path.relative_to(app_root.parent)
                    print(f"{relative_path}:{line_number}: {line.strip()}")
                    match_count += 1

    print()
    print(f"TONG SO DONG MA NGUON CO MA VAI TRO: {match_count}")
    print(
        "HOAN TAT: chi doc du lieu va ma nguon, "
        "khong them, sua hoac xoa."
    )


if __name__ == "__main__":
    main()
