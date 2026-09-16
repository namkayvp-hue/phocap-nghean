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
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class StaffMember(Base):
    """Hồ sơ nhận diện gốc của cán bộ quản lý, giáo viên và nhân viên."""

    __tablename__ = "staff_members"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    ministry_staff_code: Mapped[str | None] = mapped_column(
        String(50), unique=True, nullable=True, index=True
    )
    full_name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
    gender: Mapped[str | None] = mapped_column(String(20), nullable=True)
    ethnic_group: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    personal_id: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now, nullable=False
    )

    year_records: Mapped[list["StaffYearRecord"]] = relationship(
        back_populates="staff_member", cascade="all, delete-orphan"
    )


class StaffYearRecord(Base):
    """Thông tin công tác của một người tại một năm học."""

    __tablename__ = "staff_year_records"
    __table_args__ = (
        UniqueConstraint(
            "staff_member_id",
            "school_year_id",
            name="uq_staff_member_school_year",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    staff_member_id: Mapped[int] = mapped_column(
        ForeignKey("staff_members.id"), nullable=False, index=True
    )
    school_year_id: Mapped[int] = mapped_column(
        ForeignKey("school_years.id"), nullable=False, index=True
    )
    school_id: Mapped[int] = mapped_column(
        ForeignKey("schools.id"), nullable=False, index=True
    )
    status_code: Mapped[str] = mapped_column(
        String(40), default="DANG_LAM_VIEC", nullable=False, index=True
    )
    position_group: Mapped[str] = mapped_column(
        String(30), default="GIAO_VIEN", nullable=False, index=True
    )
    position_title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    employment_type: Mapped[str] = mapped_column(
        String(40), default="CHUA_XAC_DINH", nullable=False, index=True
    )
    recruitment_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    teaching_level: Mapped[str] = mapped_column(
        String(30), default="KHONG_DAY", nullable=False, index=True
    )
    teaching_age_group: Mapped[str] = mapped_column(
        String(30), default="KHONG_XAC_DINH", nullable=False, index=True
    )
    teaching_subject: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    main_specialty: Mapped[str | None] = mapped_column(String(250), nullable=True)
    staff_evaluation: Mapped[str | None] = mapped_column(String(120), nullable=True)
    source_level: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    source_status_label: Mapped[str | None] = mapped_column(String(100), nullable=True)
    receives_policy: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # === BAI_13B_11_14_7_1_1_MULTIGRADE_FIELDS_START ===
    teaches_multigrade: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    uses_multigrade_program_4yo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    uses_multigrade_program_5yo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # === BAI_13B_11_14_7_1_1_MULTIGRADE_FIELDS_END ===
    qualification_level: Mapped[str] = mapped_column(
        String(40), default="CHUA_XAC_DINH", nullable=False, index=True
    )
    qualification_standard: Mapped[str] = mapped_column(
        String(40), default="CHUA_XAC_DINH", nullable=False, index=True
    )
    professional_standard: Mapped[str] = mapped_column(
        String(40), default="CHUA_DANH_GIA", nullable=False, index=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now, nullable=False
    )

    staff_member: Mapped[StaffMember] = relationship(back_populates="year_records")
    school_year = relationship("SchoolYear")
    school = relationship("School")


class SchoolStaffYearSummary(Base):
    """Số nhóm/lớp và loại cơ sở để lập biểu MN-01 GV theo năm học."""

    __tablename__ = "school_staff_year_summaries"
    __table_args__ = (
        UniqueConstraint(
            "school_id",
            "school_year_id",
            name="uq_school_staff_summary_year",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    school_id: Mapped[int] = mapped_column(
        ForeignKey("schools.id"), nullable=False, index=True
    )
    school_year_id: Mapped[int] = mapped_column(
        ForeignKey("school_years.id"), nullable=False, index=True
    )
    institution_group: Mapped[str] = mapped_column(
        String(40), default="TRUONG_MAM_NON", nullable=False, index=True
    )
    total_groups_classes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    preschool_classes_3_4: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    preschool_classes_5: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now, nullable=False
    )

    school = relationship("School")
    school_year = relationship("SchoolYear")
