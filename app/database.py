from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


# Thư mục gốc của dự án: C:\PhoCap
PROJECT_DIR = Path(__file__).resolve().parent.parent

# Thư mục chứa cơ sở dữ liệu
DATA_DIR = PROJECT_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Tệp cơ sở dữ liệu
DATABASE_PATH = DATA_DIR / "phocap.db"

# Địa chỉ kết nối SQLite
DATABASE_URL = f"sqlite:///{DATABASE_PATH.as_posix()}"


# Tạo bộ máy kết nối cơ sở dữ liệu
engine = create_engine(
    DATABASE_URL,
    connect_args={
        "check_same_thread": False,
    },
    echo=False,
)


# Bật kiểm tra khóa ngoại trong SQLite
@event.listens_for(engine, "connect")
def enable_sqlite_foreign_keys(
    dbapi_connection,
    connection_record,
) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


# Công cụ tạo phiên làm việc với cơ sở dữ liệu
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
)


# Lớp cơ sở cho tất cả các bảng
class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    """
    Tạo một phiên kết nối cơ sở dữ liệu cho mỗi yêu cầu web.
    Sau khi xử lý xong, phiên kết nối được tự động đóng.
    """

    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()