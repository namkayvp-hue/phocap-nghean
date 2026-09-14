from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class HouseholdImportJob(Base):
    """Một lần tiếp nhận file cập nhật dữ liệu hộ dân."""

    __tablename__ = "survey_household_import_jobs"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )
    job_code: Mapped[str] = mapped_column(
        String(80),
        unique=True,
        nullable=False,
        index=True,
    )
    survey_batch_id: Mapped[int] = mapped_column(
        ForeignKey("survey_batches.id"),
        nullable=False,
        index=True,
    )
    school_year_id: Mapped[int] = mapped_column(
        ForeignKey("school_years.id"),
        nullable=False,
        index=True,
    )
    commune_id: Mapped[int] = mapped_column(
        ForeignKey("communes.id"),
        nullable=False,
        index=True,
    )
    uploaded_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )
    actor_name_snapshot: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )
    actor_role_snapshot: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    actor_unit_snapshot: Mapped[str | None] = mapped_column(
        String(300),
        nullable=True,
    )
    original_file_name: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )
    stored_path: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    file_ext: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        index=True,
    )
    file_size: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    sha256: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(50),
        default="DA_NHAN",
        nullable=False,
        index=True,
    )
    stage: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        index=True,
    )
    message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    sheet_names: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    has_macro: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    rows_total: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    rows_valid: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    rows_error: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    conflict_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    households_created: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    households_updated: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    people_created: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    people_updated: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    duplicate_of_job_code: Mapped[str | None] = mapped_column(
        String(80),
        nullable=True,
    )
    received_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )
    checked_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.now,
        nullable=False,
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.now,
        onupdate=datetime.now,
        nullable=False,
    )


class HouseholdImportError(Base):
    """Chi tiết lỗi/khuyến cáo của từng lần gửi file."""

    __tablename__ = "survey_household_import_errors"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )
    job_id: Mapped[int] = mapped_column(
        ForeignKey("survey_household_import_jobs.id"),
        nullable=False,
        index=True,
    )
    severity: Mapped[str] = mapped_column(
        String(20),
        default="ERROR",
        nullable=False,
        index=True,
    )
    sheet_name: Mapped[str | None] = mapped_column(
        String(300),
        nullable=True,
    )
    row_number: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    column_name: Mapped[str | None] = mapped_column(
        String(300),
        nullable=True,
    )
    error_code: Mapped[str | None] = mapped_column(
        String(80),
        nullable=True,
        index=True,
    )
    message: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.now,
        nullable=False,
    )
