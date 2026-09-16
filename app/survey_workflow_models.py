from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SurveyCommuneExecutionState(Base):
    """Trạng thái khóa của một địa bàn trong đợt điều tra cấp tỉnh."""

    __tablename__ = "survey_commune_execution_states"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    survey_batch_id: Mapped[int] = mapped_column(
        ForeignKey("survey_batches.id"),
        nullable=False,
        unique=True,
        index=True,
    )
    is_commune_locked: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, index=True
    )
    is_province_locked: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, index=True
    )
    commune_locked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    commune_locked_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    commune_lock_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    province_locked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    province_locked_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    province_lock_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now, nullable=False
    )


class SurveySchoolAssignment(Base):
    """Nhiệm vụ điều tra mà xã giao cho một trường trong một đợt."""

    __tablename__ = "survey_school_assignments"
    __table_args__ = (
        UniqueConstraint(
            "survey_batch_id",
            "school_id",
            name="uq_survey_school_assignment_batch_school",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    survey_batch_id: Mapped[int] = mapped_column(
        ForeignKey("survey_batches.id"), nullable=False, index=True
    )
    school_id: Mapped[int] = mapped_column(
        ForeignKey("schools.id"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        String(40), default="DANG_THUC_HIEN", nullable=False, index=True
    )
    is_locked: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, index=True
    )
    assigned_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, nullable=False
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    locked_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    lock_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now, nullable=False
    )


class SurveyExecutionWorkflowLog(Base):
    """Nhật ký phân công, gửi xã, khóa và mở khóa trong quy trình ba cấp."""

    __tablename__ = "survey_execution_workflow_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    survey_batch_id: Mapped[int] = mapped_column(
        ForeignKey("survey_batches.id"), nullable=False, index=True
    )
    school_id: Mapped[int | None] = mapped_column(
        ForeignKey("schools.id"), nullable=True, index=True
    )
    action: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    actor_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    actor_name_snapshot: Mapped[str | None] = mapped_column(String(200), nullable=True)
    actor_role_snapshot: Mapped[str | None] = mapped_column(String(50), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    form_total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completed_form_total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, nullable=False, index=True
    )
