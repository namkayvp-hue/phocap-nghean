from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class THPTSchoolReference(Base):
    """
    Danh mục tham chiếu trường THPT lấy từ file mạng lưới của Sở.

    Bảng này độc lập với app.models.School vì file nguồn THPT hiện tại
    không có xã/phường trực thuộc, trong khi bảng School bắt buộc commune_id.
    Nếu mã trường đã tồn tại trong School thì official_school_id được liên kết.
    """

    __tablename__ = "thpt_school_references"
    __table_args__ = (
        UniqueConstraint(
            "school_year_code",
            "school_code",
            name="uq_thpt_ref_year_school",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    school_year_code: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    school_code: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    school_name: Mapped[str] = mapped_column(String(300), nullable=False, index=True)

    official_school_id: Mapped[int | None] = mapped_column(
        ForeignKey("schools.id"),
        nullable=True,
        index=True,
    )

    national_standard: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    total_class_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_student_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    new_student_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    staff_total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    manager_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    teacher_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    youth_union_teacher_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    employee_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    classroom_total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    classroom_permanent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    classroom_semi: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    classroom_temporary: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    source_name: Mapped[str] = mapped_column(String(500), nullable=False)
    source_row: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        default=datetime.now,
        onupdate=datetime.now,
        nullable=False,
    )

    grades: Mapped[list["THPTGradeReference"]] = relationship(
        back_populates="school",
        cascade="all, delete-orphan",
        order_by="THPTGradeReference.grade",
    )


class THPTGradeReference(Base):
    """
    Thông tin khối 10/11/12.

    File nguồn chỉ có SỐ LƯỢNG lớp theo khối, không có tên lớp thực tế
    (10A1, 10A2...). Vì vậy tuyệt đối không tự sinh lớp giả.
    """

    __tablename__ = "thpt_grade_references"
    __table_args__ = (
        UniqueConstraint(
            "school_ref_id",
            "grade",
            name="uq_thpt_ref_school_grade",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    school_ref_id: Mapped[int] = mapped_column(
        ForeignKey("thpt_school_references.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    grade: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    class_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    student_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    new_student_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    school: Mapped[THPTSchoolReference] = relationship(back_populates="grades")
