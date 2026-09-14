from __future__ import annotations

from datetime import datetime
from pathlib import Path
import shutil
import sqlite3

from app.database import DATABASE_PATH


NEW_ROLES = (
    (
        "ADMIN",
        "Quản trị hệ thống",
        "Tài khoản quản trị cấp cao nhất; quản lý tài khoản, danh mục, dữ liệu và báo cáo toàn tỉnh.",
    ),
    (
        "PHONG_BAN",
        "Phòng ban",
        "Tài khoản phòng ban cấp Sở; chỉ xem dữ liệu và xuất báo cáo cấp tỉnh, không nhập dữ liệu và không quản lý tài khoản.",
    ),
)


def backup_database(database_path: Path) -> Path:
    backup_dir = Path(r"C:\PhoCap\data\backups")
    backup_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = database_path.suffix or ".db"
    backup_path = backup_dir / f"truoc_bai_11c_3_{timestamp}{suffix}"

    shutil.copy2(database_path, backup_path)
    return backup_path


def validate_roles_table(connection: sqlite3.Connection) -> None:
    columns = {
        row[1]: row
        for row in connection.execute("PRAGMA table_info(roles)")
    }

    required_columns = {"id", "code", "name", "description"}
    missing = required_columns.difference(columns)

    if missing:
        raise RuntimeError(
            "Bảng roles thiếu các cột bắt buộc: "
            + ", ".join(sorted(missing))
        )


def get_role(
    connection: sqlite3.Connection,
    role_code: str,
) -> sqlite3.Row | None:
    return connection.execute(
        """
        SELECT id, code, name, description
        FROM roles
        WHERE UPPER(code) = UPPER(?)
        """,
        (role_code,),
    ).fetchone()


def main() -> None:
    database_path = Path(DATABASE_PATH)

    if not database_path.exists():
        raise FileNotFoundError(
            f"Không tìm thấy cơ sở dữ liệu: {database_path}"
        )

    backup_path = backup_database(database_path)

    print("=" * 72)
    print("BÀI 11C-3 - THÊM VAI TRÒ ADMIN VÀ PHONG_BAN")
    print("=" * 72)
    print(f"Cơ sở dữ liệu: {database_path}")
    print(f"Đã sao lưu tại: {backup_path}")
    print()

    connection = sqlite3.connect(str(database_path))
    connection.row_factory = sqlite3.Row

    try:
        connection.execute("PRAGMA foreign_keys = ON")
        validate_roles_table(connection)

        connection.execute("BEGIN IMMEDIATE")

        inserted_count = 0

        for role_code, role_name, description in NEW_ROLES:
            existing = get_role(connection, role_code)

            if existing is not None:
                print(
                    f"GIỮ NGUYÊN: {role_code} đã tồn tại "
                    f"(id={existing['id']}, name={existing['name']})."
                )
                continue

            connection.execute(
                """
                INSERT INTO roles (code, name, description)
                VALUES (?, ?, ?)
                """,
                (role_code, role_name, description),
            )
            inserted_count += 1
            print(f"ĐÃ THÊM: {role_code} - {role_name}")

        connection.commit()

        print()
        print("=== KẾT QUẢ SAU KHI THÊM ===")

        for role_code, _, _ in NEW_ROLES:
            row = get_role(connection, role_code)

            if row is None:
                raise RuntimeError(
                    f"Không tìm thấy vai trò {role_code} sau khi COMMIT."
                )

            user_count = connection.execute(
                "SELECT COUNT(*) FROM users WHERE role_id = ?",
                (row["id"],),
            ).fetchone()[0]

            print(
                f"id={row['id']} | code={row['code']} | "
                f"name={row['name']} | users={user_count}"
            )

        admin_user = connection.execute(
            """
            SELECT u.username, r.code AS role_code
            FROM users AS u
            JOIN roles AS r ON r.id = u.role_id
            WHERE LOWER(u.username) = LOWER(?)
            """,
            ("admin.sogddt",),
        ).fetchone()

        department_user = connection.execute(
            """
            SELECT u.username, r.code AS role_code
            FROM users AS u
            JOIN roles AS r ON r.id = u.role_id
            WHERE LOWER(u.username) = LOWER(?)
            """,
            ("p_gdmn",),
        ).fetchone()

        print()
        print("=== TÀI KHOẢN CHƯA CHUYỂN ĐỔI ===")
        if admin_user:
            print(
                f"{admin_user['username']}: "
                f"vai trò hiện tại = {admin_user['role_code']}"
            )
        else:
            print("Không tìm thấy admin.sogddt")

        if department_user:
            print(
                f"{department_user['username']}: "
                f"vai trò hiện tại = {department_user['role_code']}"
            )
        else:
            print("Không tìm thấy p_gdmn")

        print()
        print(f"Số vai trò mới được thêm trong lần chạy này: {inserted_count}")
        print("THÀNH CÔNG: đã thêm danh mục vai trò mới.")
        print(
            "CHƯA CHUYỂN admin.sogddt hoặc p_gdmn sang vai trò mới."
        )

    except Exception:
        connection.rollback()
        print()
        print("KHÔNG THÀNH CÔNG: giao dịch đã ROLLBACK.")
        print(f"Có thể phục hồi từ: {backup_path}")
        raise

    finally:
        connection.close()


if __name__ == "__main__":
    main()
