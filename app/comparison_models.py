from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class StudentSurveyResolutionLog(Base):
    """Nhật ký xử lý kết quả đối chiếu điều tra với hồ sơ học sinh.

    Bảng này lưu theo kiểu nối tiếp, không ghi đè lịch sử. Bản ghi mới nhất
    của mỗi đối tượng điều tra hoặc học sinh được dùng làm trạng thái xử lý
    hiện hành trên màn hình đối chiếu.
    """

    __tablename__ = "student_survey_resolution_logs"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    survey_batch_id: Mapped[int] = mapped_column(
        ForeignKey("survey_batches.id"),
        nullable=False,
        index=True,
    )

    survey_person_id: Mapped[int | None] = mapped_column(
        ForeignKey("survey_people.id"),
        nullable=True,
        index=True,
    )

    student_id: Mapped[int | None] = mapped_column(
        ForeignKey("students.id"),
        nullable=True,
        index=True,
    )

    previous_student_id: Mapped[int | None] = mapped_column(
        ForeignKey("students.id"),
        nullable=True,
    )

    action_code: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )

    result_before: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    note: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    actor_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.now,
        nullable=False,
        index=True,
    )


class StudentSurveyComparisonSignoff(Base):
    """Nhật ký chốt hoặc mở lại kết quả đối chiếu học sinh.

    Mỗi lần thao tác tạo một bản ghi mới, không ghi đè lịch sử. Trạng thái
    hiện hành được xác định theo bản ghi mới nhất của từng đợt điều tra.
    Các số liệu tổng hợp được lưu dạng ảnh chụp tại thời điểm thao tác để
    biên bản vẫn phản ánh đúng tình trạng đã được xác nhận.
    """

    __tablename__ = "student_survey_comparison_signoffs"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    survey_batch_id: Mapped[int] = mapped_column(
        ForeignKey("survey_batches.id"),
        nullable=False,
        index=True,
    )

    action_code: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        index=True,
    )

    note: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    actor_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )

    actor_name_snapshot: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    actor_role_snapshot: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    total_rows: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    matched_rows: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    issue_rows: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    resolved_rows: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    pending_rows: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.now,
        nullable=False,
        index=True,
    )
