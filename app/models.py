from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
    relationship,
)

from app.database import Base


# =========================================================
# VAI TRÒ NGƯỜI DÙNG
# =========================================================

class Role(Base):
    """
    Bảng lưu các vai trò phân quyền của hệ thống.
    """

    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    code: Mapped[str] = mapped_column(
        String(20),
        unique=True,
        nullable=False,
    )

    name: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
    )

    description: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    users: Mapped[list[User]] = relationship(
        back_populates="role",
    )


# =========================================================
# DANH MỤC XÃ
# =========================================================

class Commune(Base):
    """
    Bảng danh mục xã.
    """

    __tablename__ = "communes"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    code: Mapped[str] = mapped_column(
        String(30),
        unique=True,
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        index=True,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    # Phân loại địa bàn để áp dụng ngưỡng chỉ tiêu trẻ em theo
    # Nghị định 277/2025/NĐ-CP. Mặc định là địa bàn thông thường.
    is_special_difficulty_area: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.now,
        nullable=False,
    )

    schools: Mapped[list[School]] = relationship(
        back_populates="commune",
    )

    users: Mapped[list[User]] = relationship(
        back_populates="commune",
    )


# =========================================================
# DANH MỤC TRƯỜNG
# =========================================================

class School(Base):
    """
    Bảng danh mục trường.
    Mỗi trường trực thuộc một xã.
    """

    __tablename__ = "schools"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    commune_id: Mapped[int] = mapped_column(
        ForeignKey("communes.id"),
        nullable=False,
        index=True,
    )

    code: Mapped[str] = mapped_column(
        String(30),
        unique=True,
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(300),
        nullable=False,
        index=True,
    )

    address: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.now,
        nullable=False,
    )

    commune: Mapped[Commune] = relationship(
        back_populates="schools",
    )

    users: Mapped[list[User]] = relationship(
        back_populates="school",
    )

    classrooms: Mapped[list[Classroom]] = relationship(
        back_populates="school",
    )

    enrollments: Mapped[list[StudentEnrollment]] = relationship(
        back_populates="school",
    )


# =========================================================
# TÀI KHOẢN NGƯỜI DÙNG
# =========================================================

class User(Base):
    """
    Bảng tài khoản đăng nhập hệ thống.
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    username: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
        index=True,
    )

    password_hash: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    full_name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    role_id: Mapped[int] = mapped_column(
        ForeignKey("roles.id"),
        nullable=False,
        index=True,
    )

    commune_id: Mapped[int | None] = mapped_column(
        ForeignKey("communes.id"),
        nullable=True,
        index=True,
    )

    school_id: Mapped[int | None] = mapped_column(
        ForeignKey("schools.id"),
        nullable=True,
        index=True,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.now,
        nullable=False,
    )

    role: Mapped[Role] = relationship(
        back_populates="users",
    )

    commune: Mapped[Commune | None] = relationship(
        back_populates="users",
    )

    school: Mapped[School | None] = relationship(
        back_populates="users",
    )


# =========================================================
# NĂM HỌC
# =========================================================

class SchoolYear(Base):
    """
    Bảng danh mục năm học.

    Ví dụ:
    code = 2025-2026
    name = Năm học 2025-2026
    """

    __tablename__ = "school_years"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    code: Mapped[str] = mapped_column(
        String(20),
        unique=True,
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    start_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    end_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.now,
        nullable=False,
    )

    classrooms: Mapped[list[Classroom]] = relationship(
        back_populates="school_year",
    )

    enrollments: Mapped[list[StudentEnrollment]] = relationship(
        back_populates="school_year",
    )


# =========================================================
# LỚP HỌC
# =========================================================

class Classroom(Base):
    """
    Bảng lớp học theo trường và năm học.

    Một trường có thể có lớp cùng tên ở các năm học khác nhau.
    """

    __tablename__ = "classes"

    __table_args__ = (
        UniqueConstraint(
            "school_id",
            "school_year_id",
            "name",
            name="uq_class_school_year_name",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    school_id: Mapped[int] = mapped_column(
        ForeignKey("schools.id"),
        nullable=False,
        index=True,
    )

    school_year_id: Mapped[int] = mapped_column(
        ForeignKey("school_years.id"),
        nullable=False,
        index=True,
    )

    code: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        index=True,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.now,
        nullable=False,
    )

    school: Mapped[School] = relationship(
        back_populates="classrooms",
    )

    school_year: Mapped[SchoolYear] = relationship(
        back_populates="classrooms",
    )

    enrollments: Mapped[list[StudentEnrollment]] = relationship(
        back_populates="classroom",
    )


# =========================================================
# HỒ SƠ HỌC SINH
# =========================================================

class Student(Base):
    """
    Bảng lưu hồ sơ gốc của học sinh.

    Mã học sinh là thông tin nhận diện duy nhất.
    Trường, lớp và năm học được lưu trong bảng
    student_enrollments.
    """

    __tablename__ = "students"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    code: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
    )

    full_name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        index=True,
    )

    date_of_birth: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
        index=True,
    )

    gender: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )

    ethnic_group: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    birth_place: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    permanent_address: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    current_address: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    father_name: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )

    father_birth_year: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    father_job: Mapped[str | None] = mapped_column(
        String(300),
        nullable=True,
    )

    mother_name: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )

    mother_birth_year: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    mother_job: Mapped[str | None] = mapped_column(
        String(300),
        nullable=True,
    )

    contact_phone: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
        index=True,
    )

    personal_id: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        index=True,
    )

    disability_type: Mapped[str | None] = mapped_column(
        String(300),
        nullable=True,
    )

    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.now,
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.now,
        onupdate=datetime.now,
        nullable=False,
    )

    enrollments: Mapped[list[StudentEnrollment]] = relationship(
        back_populates="student",
    )

    change_logs: Mapped[list[StudentChangeLog]] = relationship(
        back_populates="student",
    )


# =========================================================
# HỌC SINH THEO NĂM HỌC, TRƯỜNG VÀ LỚP
# =========================================================

class StudentEnrollment(Base):
    """
    Bảng lưu quá trình học của học sinh.

    Một học sinh có thể:
    - Học lớp khác ở năm học sau.
    - Chuyển trường.
    - Chuyển lớp.
    - Chuyển đến hoặc chuyển đi.
    """

    __tablename__ = "student_enrollments"

    __table_args__ = (
        UniqueConstraint(
            "student_id",
            "school_year_id",
            "school_id",
            "class_id",
            name="uq_student_enrollment",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id"),
        nullable=False,
        index=True,
    )

    school_year_id: Mapped[int] = mapped_column(
        ForeignKey("school_years.id"),
        nullable=False,
        index=True,
    )

    school_id: Mapped[int] = mapped_column(
        ForeignKey("schools.id"),
        nullable=False,
        index=True,
    )

    class_id: Mapped[int] = mapped_column(
        ForeignKey("classes.id"),
        nullable=False,
        index=True,
    )

    status: Mapped[str] = mapped_column(
        String(50),
        default="DANG_HOC",
        nullable=False,
        index=True,
    )

    enrollment_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    transfer_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    is_current: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.now,
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.now,
        onupdate=datetime.now,
        nullable=False,
    )

    student: Mapped[Student] = relationship(
        back_populates="enrollments",
    )

    school_year: Mapped[SchoolYear] = relationship(
        back_populates="enrollments",
    )

    school: Mapped[School] = relationship(
        back_populates="enrollments",
    )

    classroom: Mapped[Classroom] = relationship(
        back_populates="enrollments",
    )


# =========================================================
# NHẬT KÝ MỖI LẦN NHẬP EXCEL
# =========================================================

class ImportBatch(Base):
    """
    Bảng lưu thông tin một lần nhập hoặc cập nhật Excel.
    """

    __tablename__ = "import_batches"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    file_name: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    template_version: Mapped[str] = mapped_column(
        String(30),
        default="1.0",
        nullable=False,
    )

    operation_type: Mapped[str] = mapped_column(
        String(50),
        default="CAP_NHAT_HOC_SINH",
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(50),
        default="DANG_XU_LY",
        nullable=False,
        index=True,
    )

    total_rows: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    valid_rows: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    inserted_rows: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    updated_rows: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    skipped_rows: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    error_rows: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    error_report_path: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
    )

    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.now,
        nullable=False,
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    creator: Mapped[User | None] = relationship(
        foreign_keys=[created_by_user_id],
    )

    change_logs: Mapped[list[StudentChangeLog]] = relationship(
        back_populates="import_batch",
    )


# =========================================================
# NHẬT KÝ CHI TIẾT THAY ĐỔI HỌC SINH
# =========================================================

class StudentChangeLog(Base):
    """
    Lưu từng trường dữ liệu đã thay đổi.

    Ví dụ:
    field_name = full_name
    old_value = Nguyễn Văn A
    new_value = Nguyễn Văn An
    """

    __tablename__ = "student_change_logs"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    import_batch_id: Mapped[int | None] = mapped_column(
        ForeignKey("import_batches.id"),
        nullable=True,
        index=True,
    )

    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id"),
        nullable=False,
        index=True,
    )

    field_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    old_value: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    new_value: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    changed_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )

    changed_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.now,
        nullable=False,
    )

    import_batch: Mapped[ImportBatch | None] = relationship(
        back_populates="change_logs",
    )

    student: Mapped[Student] = relationship(
        back_populates="change_logs",
    )

    changed_by: Mapped[User | None] = relationship(
        foreign_keys=[changed_by_user_id],
    )