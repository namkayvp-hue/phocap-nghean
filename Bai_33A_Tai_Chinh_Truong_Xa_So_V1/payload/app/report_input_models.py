from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class SchoolMn01GvInput(Base):
    """Dữ liệu bổ sung cấp trường phục vụ biểu MN-01-GV theo năm học."""

    __tablename__ = "school_mn01_gv_inputs"
    __table_args__ = (
        UniqueConstraint("school_id", "school_year_id", name="uq_school_mn01_gv_input_year"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    school_id: Mapped[int] = mapped_column(ForeignKey("schools.id"), nullable=False, index=True)
    school_year_id: Mapped[int] = mapped_column(ForeignKey("school_years.id"), nullable=False, index=True)
    ethnic_staff_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)

    school = relationship("School")
    school_year = relationship("SchoolYear")


class SchoolMn01CsvcInput(Base):
    """Dữ liệu cơ sở vật chất cấp trường phục vụ biểu MN-01-CSVC."""

    __tablename__ = "school_mn01_csvc_inputs"
    __table_args__ = (
        UniqueConstraint("school_id", "school_year_id", name="uq_school_mn01_csvc_input_year"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    school_id: Mapped[int] = mapped_column(ForeignKey("schools.id"), nullable=False, index=True)
    school_year_id: Mapped[int] = mapped_column(ForeignKey("school_years.id"), nullable=False, index=True)

    facility_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    satellite_site_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    nursery_group_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    preschool_class_3_4_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    preschool_class_5_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    total_classroom_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    nursery_classroom_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    permanent_preschool_room_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    semi_permanent_preschool_room_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    temporary_preschool_room_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    equipped_preschool_class_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    toilet_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    standard_toilet_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    clean_water_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    standard_clean_water_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    kitchen_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    standard_kitchen_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    playground_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    playground_with_toys_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)

    school = relationship("School")
    school_year = relationship("SchoolYear")


class FinanceReportValue(Base):
    """Giá trị từng chỉ tiêu của biểu BC-Tài chính theo xã/phường và năm dương lịch."""

    __tablename__ = "finance_report_values"
    __table_args__ = (
        UniqueConstraint("commune_id", "report_year", "item_code", name="uq_finance_commune_year_item"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    commune_id: Mapped[int] = mapped_column(ForeignKey("communes.id"), nullable=False, index=True)
    report_year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    item_code: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)

    commune = relationship("Commune")


class SchoolFinanceReportValue(Base):
    """Giá trị BC-Tài chính do từng trường nhập theo năm dương lịch."""

    __tablename__ = "school_finance_report_values"
    __table_args__ = (
        UniqueConstraint(
            "school_id",
            "report_year",
            "item_code",
            name="uq_school_finance_year_item",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    school_id: Mapped[int] = mapped_column(
        ForeignKey("schools.id"), nullable=False, index=True
    )
    report_year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    item_code: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now, nullable=False
    )

    school = relationship("School")


class SchoolStructuredReportInput(Base):
    """Dữ liệu nhập chuyên biệt theo đúng một biểu, một trường và một năm học."""

    __tablename__ = "school_structured_report_inputs"
    __table_args__ = (
        UniqueConstraint(
            "school_id",
            "school_year_id",
            "form_code",
            name="uq_school_structured_report_input",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    school_id: Mapped[int] = mapped_column(
        ForeignKey("schools.id"), nullable=False, index=True
    )
    school_year_id: Mapped[int] = mapped_column(
        ForeignKey("school_years.id"), nullable=False, index=True
    )
    form_code: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    data_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now, nullable=False
    )

    school = relationship("School")
    school_year = relationship("SchoolYear")

class SchoolNetworkYearData(Base):
    """Dữ liệu mạng lưới trường/lớp theo cấp học và năm học, dùng làm nguồn tham chiếu."""

    __tablename__ = "school_network_year_data"
    __table_args__ = (
        UniqueConstraint(
            "school_id",
            "school_year_id",
            "level_code",
            name="uq_school_network_year_level",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    school_id: Mapped[int] = mapped_column(
        ForeignKey("schools.id"), nullable=False, index=True
    )
    school_year_id: Mapped[int] = mapped_column(
        ForeignKey("school_years.id"), nullable=False, index=True
    )
    level_code: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    data_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    source_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    imported_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, nullable=False
    )

    school = relationship("School")
    school_year = relationship("SchoolYear")

