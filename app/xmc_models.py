"""Additional evidence for the 2026 XMC forms, attached to a surveyed year record."""
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class XmcEvidence(Base):
    __tablename__ = "xmc_year_evidence"
    record_id: Mapped[int] = mapped_column(ForeignKey("survey_person_year_records.id"), primary_key=True)
    data: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    updated_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


BOOL_FIELDS = {
    "completed_stage1": "Đã hoàn thành giai đoạn 1 chương trình XMC (Điều 23)",
    "completed_stage2": "Đã hoàn thành giai đoạn 2 chương trình XMC (Điều 23)",
    "illiterate": "Chưa biết chữ (đã xác minh)",
    "enrolled1": "Học viên XMC mức độ 1 trong năm",
    "enrolled2": "Học viên XMC mức độ 2 trong năm",
    "recognized1": "Được công nhận mức độ 1 trong năm",
    "recognized2": "Được công nhận mức độ 2 trong năm",
    "relapsed": "Đã xác minh tái mù chữ",
}
TEXT_FIELDS = {
    "policy": "Đối tượng hưởng chính sách",
    "recognized_year": "Năm công nhận hoàn thành XMC trước đây",
    "support_status": "Tình trạng hỗ trợ, học tập bổ sung",
    "support_start_year": "Năm bắt đầu hỗ trợ",
    "support_result": "Kết quả đánh giá sau hỗ trợ",
    "support_duration": "Thời gian hỗ trợ",
    "note": "Ghi chú / căn cứ xác nhận",
}
