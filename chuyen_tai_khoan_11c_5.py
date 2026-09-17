from __future__ import annotations

from datetime import datetime
from pathlib import Path
import shutil
import sqlite3

from app.database import DATABASE_PATH


ACCOUNT_ROLE_MAP = {
    "admin.sogddt": "ADMIN",
    "p_gdmn": "PHONG_BAN",
}


def backup_database(database_path: Path) -> Path:
    backup_dir = Path(r"C:\PhoCap\data\backups")
    backup_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = database_path.suffix or ".db"
    backup_path = backup_dir / f"truoc_bai_11c_5_{timestamp}{suffix}"

    shutil.copy2(database_path, backup_path)
    return backup_path


def fetch_role(
    connection: sqlite3.Connection,
    role_code: str,
) -> sqlite3.Row:
    rows = connection.execute(
        """
        SELECT id, code, name
        FROM roles
        WHERE UPPER(code) = UPPER(?)
        """,
        (role_code,),
    ).fetchall()

    if len(rows) != 1:
        raise RuntimeError(
            f"Vai trò {role_code} có {len(rows)} bản ghi; yêu cầu đúng 1."
        )

    return rows[0]


def fetch_user(
    connection: sqlite3.Connection,
    username: str,
) -> sqlite3.Row:
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
            f"Tài khoản {username} có {len(rows)} bản ghi; yêu cầu đúng 1."
        )

    return rows[0]


def main() -> None:
    database_path = Path(DATABASE_PATH)

    if not database_path.exists():
        raise FileNotFoundError(
            f"Không tìm thấy cơ sở dữ liệu: {database_path}"
        )

    backup_path = backup_database(database_path)

    print("=" * 76)
    print("BÀI 11C-5 - CHUYỂN TÀI KHOẢN SANG ADMIN VÀ PHONG_BAN")
    print("=" * 76)
    print(f"Cơ sở dữ liệu: {database_path}")
    print(f"Đã sao lưu tại: {backup_path}")
    print()

    connection = sqlite3.connect(str(database_path))
    connection.row_factory = sqlite3.Row

    try:
        connection.execute("PRAGMA foreign_keys = ON")

        total_before = connection.execute(
            "SELECT COUNT(*) FROM users"
        ).fetchone()[0]

        admin_role = fetch_role(connection, "ADMIN")
        department_role = fetch_role(connection, "PHONG_BAN")
        old_so_role = fetch_role(connection, "SO")

        role_lookup = {
            "ADMIN": admin_role,
            "PHONG_BAN": department_role,
        }

        print("=== KIỂM TRA TRƯỚC KHI CHUYỂN ===")

        users_before: dict[str, sqlite3.Row] = {}

        for username, target_role_code in ACCOUNT_ROLE_MAP.items():
            user = fetch_user(connection, username)
            users_before[username] = user

            if user["commune_id"] is not None:
                raise RuntimeError(
                    f"{username} đang gắn commune_id={user['commune_id']}; "
                    "không được tự động chuyển."
                )

            if user["school_id"] is not None:
                raise RuntimeError(
                    f"{username} đang gắn school_id={user['school_id']}; "
                    "không được tự động chuyển."
                )

            current_role = str(user["role_code"]).upper()

            if current_role not in {"SO", target_role_code}:
                raise RuntimeError(
                    f"{username} đang có vai trò {current_role}; "
                    f"chỉ chấp nhận SO hoặc {target_role_code}."
                )

            print(
                f"OK: {user['username']} | "
                f"họ tên={user['full_name']} | "
                f"vai trò hiện tại={current_role} | "
                f"vai trò đích={target_role_code} | "
                f"hoạt động={user['is_active']}"
            )

        other_so_accounts = connection.execute(
            """
            SELECT u.id, u.username, u.full_name
            FROM users AS u
            WHERE u.role_id = ?
              AND LOWER(u.username) NOT IN (?, ?)
            ORDER BY u.id
            """,
            (
                old_so_role["id"],
                "admin.sogddt",
                "p_gdmn",
            ),
        ).fetchall()

        if other_so_accounts:
            details = "; ".join(
                f"id={row['id']}, username={row['username']}"
                for row in other_so_accounts
            )
            raise RuntimeError(
                "Còn tài khoản SO ngoài hai tài khoản đã xác nhận: "
                + details
            )

        print()
        print("Bắt đầu giao dịch chuyển vai trò...")
        connection.execute("BEGIN IMMEDIATE")

        changed_count = 0

        for username, target_role_code in ACCOUNT_ROLE_MAP.items():
            target_role = role_lookup[target_role_code]
            current_user = fetch_user(connection, username)

            if str(current_user["role_code"]).upper() == target_role_code:
                print(
                    f"GIỮ NGUYÊN: {username} đã là {target_role_code}."
                )
                continue

            cursor = connection.execute(
                """
                UPDATE users
                SET role_id = ?
                WHERE id = ?
                  AND role_id = ?
                """,
                (
                    target_role["id"],
                    current_user["id"],
                    old_so_role["id"],
                ),
            )

            if cursor.rowcount != 1:
                raise RuntimeError(
                    f"Không chuyển được {username}; "
                    f"số dòng cập nhật={cursor.rowcount}."
                )

            changed_count += 1
            print(
                f"ĐÃ CHUYỂN: {username} "
                f"từ SO sang {target_role_code}."
            )

        total_during = connection.execute(
            "SELECT COUNT(*) FROM users"
        ).fetchone()[0]

        if total_during != total_before:
            raise RuntimeError(
                "Tổng số tài khoản thay đổi bất thường: "
                f"trước={total_before}, trong giao dịch={total_during}."
            )

        for username, target_role_code in ACCOUNT_ROLE_MAP.items():
            user_after = fetch_user(connection, username)

            if str(user_after["role_code"]).upper() != target_role_code:
                raise RuntimeError(
                    f"{username} chưa mang vai trò {target_role_code}."
                )

            if user_after["commune_id"] is not None:
                raise RuntimeError(
                    f"{username} phát sinh commune_id bất thường."
                )

            if user_after["school_id"] is not None:
                raise RuntimeError(
                    f"{username} phát sinh school_id bất thường."
                )

        connection.commit()

        print()
        print("=== KẾT QUẢ SAU KHI COMMIT ===")

        for username, target_role_code in ACCOUNT_ROLE_MAP.items():
            user_after = fetch_user(connection, username)
            print(
                f"id={user_after['id']} | "
                f"username={user_after['username']} | "
                f"full_name={user_after['full_name']} | "
                f"role={user_after['role_code']} | "
                f"commune_id={user_after['commune_id']} | "
                f"school_id={user_after['school_id']} | "
                f"is_active={user_after['is_active']}"
            )

        role_counts = connection.execute(
            """
            SELECT r.code, COUNT(u.id) AS user_count
            FROM roles AS r
            LEFT JOIN users AS u
                ON u.role_id = r.id
            WHERE UPPER(r.code) IN ('SO', 'ADMIN', 'PHONG_BAN')
            GROUP BY r.id, r.code
            ORDER BY r.id
            """
        ).fetchall()

        print()
        print("=== SỐ TÀI KHOẢN THEO VAI TRÒ CẤP SỞ ===")
        for row in role_counts:
            print(f"{row['code']}: {row['user_count']}")

        total_after = connection.execute(
            "SELECT COUNT(*) FROM users"
        ).fetchone()[0]

        print()
        print(f"Tổng tài khoản trước chuyển: {total_before}")
        print(f"Tổng tài khoản sau chuyển:   {total_after}")
        print(f"Số tài khoản được chuyển lần này: {changed_count}")
        print()
        print("THÀNH CÔNG: giao dịch đã COMMIT.")
        print("admin.sogddt đã mang vai trò ADMIN.")
        print("p_gdmn đã mang vai trò PHONG_BAN.")
        print("Không thay đổi mật khẩu hoặc trạng thái hoạt động.")

    except Exception:
        connection.rollback()
        print()
        print("KHÔNG THÀNH CÔNG: giao dịch đã ROLLBACK.")
        print(f"Có thể phục hồi từ bản sao lưu: {backup_path}")
        raise

    finally:
        connection.close()


if __name__ == "__main__":
    main()
