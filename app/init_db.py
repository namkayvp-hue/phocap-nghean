from sqlalchemy import select

from app.database import (
    Base,
    DATABASE_PATH,
    SessionLocal,
    engine,
)
from app.models import Commune, Role, School, User


DEFAULT_ROLES = [
    {
        "id": 1,
        "code": "SO",
        "name": "Sở",
        "description": (
            "Quản lý, kiểm tra và tổng hợp dữ liệu toàn tỉnh"
        ),
    },
    {
        "id": 2,
        "code": "XA",
        "name": "Xã",
        "description": (
            "Quản lý và tổng hợp dữ liệu trên địa bàn xã"
        ),
    },
    {
        "id": 3,
        "code": "TRUONG",
        "name": "Trường",
        "description": (
            "Quản lý dữ liệu của cơ sở giáo dục"
        ),
    },
    {
        "id": 4,
        "code": "GIAO_VIEN",
        "name": "Giáo viên",
        "description": (
            "Nhập và cập nhật dữ liệu được phân công"
        ),
    },
    {
        "id": 5,
        "code": "ADMIN",
        "name": "Quản trị hệ thống",
        "description": (
            "Quản trị tài khoản, danh mục, dữ liệu và báo cáo toàn tỉnh"
        ),
    },
    {
        "id": 6,
        "code": "PHONG_BAN",
        "name": "Phòng ban",
        "description": (
            "Chỉ xem dữ liệu và xuất báo cáo cấp tỉnh"
        ),
    },
]


def create_tables() -> None:
    """
    Tạo toàn bộ bảng chưa tồn tại.
    """

    Base.metadata.create_all(bind=engine)


def seed_roles() -> None:
    """
    Thêm các vai trò mặc định.
    Không thêm lại nếu vai trò đã tồn tại.
    """

    with SessionLocal() as db:
        for role_data in DEFAULT_ROLES:
            statement = select(Role).where(
                Role.id == role_data["id"]
            )

            existing_role = db.scalar(statement)

            if existing_role is None:
                db.add(Role(**role_data))

        db.commit()


def main() -> None:
    create_tables()
    seed_roles()

    print("=" * 60)
    print("KHỞI TẠO CƠ SỞ DỮ LIỆU THÀNH CÔNG")
    print("=" * 60)
    print(f"Tệp dữ liệu: {DATABASE_PATH}")
    print("Các bảng đã tạo:")
    print("- roles")
    print("- communes")
    print("- schools")
    print("- users")
    print("Đã bảo đảm đủ 6 vai trò mặc định.")


if __name__ == "__main__":
    main()