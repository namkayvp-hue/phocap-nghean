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
# HỘ GIA ĐÌNH
# =========================================================

class Household(Base):
    """
    Hồ sơ một hộ gia đình thuộc một xã.

    Mã hộ do phần mềm tự sinh, ví dụ:
    HO-16681-000001
    """

    __tablename__ = "households"

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

    commune_id: Mapped[int] = mapped_column(
        ForeignKey("communes.id"),
        nullable=False,
        index=True,
    )

    head_name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        index=True,
    )

    hamlet_name: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
        index=True,
    )

    address: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    phone: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
        index=True,
    )

    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    is_active: Mapped[bool] = mapped_column(
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

    commune: Mapped["Commune"] = relationship()

    people: Mapped[list["SurveyPerson"]] = relationship(
        back_populates="household",
        cascade="all, delete-orphan",
    )

    survey_forms: Mapped[list["SurveyForm"]] = relationship(
        back_populates="household",
    )


# =========================================================
# ĐỐI TƯỢNG ĐIỀU TRA
# =========================================================

class SurveyPerson(Base):
    """
    Một người thuộc diện điều tra trong hộ.

    Người này có thể:
    - Chưa đi học.
    - Đang học tại một trường.
    - Đã có hoặc chưa có mã Bộ GD&ĐT.
    - Được liên kết với hồ sơ học sinh hiện có.
    """

    __tablename__ = "survey_people"

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

    household_id: Mapped[int] = mapped_column(
        ForeignKey("households.id"),
        nullable=False,
        index=True,
    )

    student_id: Mapped[int | None] = mapped_column(
        ForeignKey("students.id"),
        nullable=True,
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

    father_name: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
        index=True,
    )

    mother_name: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
        index=True,
    )

    contact_phone: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
        index=True,
    )

    relationship_to_head: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    personal_id: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        index=True,
    )

    # Căn cước công dân chính thức nếu người dân cung cấp.
    # Trường này độc lập với personal_id và mã nội bộ SurveyPerson.code.
    citizen_id: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        index=True,
    )

    ministry_student_code: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        index=True,
    )

    permanent_address: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    current_address: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    residency_status: Mapped[str] = mapped_column(
        String(50),
        default="THUONG_TRU",
        nullable=False,
        index=True,
    )

    special_circumstances: Mapped[str | None] = mapped_column(
        Text,
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

    household: Mapped[Household] = relationship(
        back_populates="people",
    )

    student: Mapped["Student | None"] = relationship()

    year_records: Mapped[
        list["SurveyPersonYearRecord"]
    ] = relationship(
        back_populates="survey_person",
        cascade="all, delete-orphan",
    )


# =========================================================
# ĐỢT ĐIỀU TRA
# =========================================================

class SurveyBatch(Base):
    """
    Một đợt điều tra của một xã trong một năm học.

    Ví dụ:
    Điều tra đầu năm học 2025-2026
    tại Phường Thành Vinh.
    """

    __tablename__ = "survey_batches"

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

    name: Mapped[str] = mapped_column(
        String(300),
        nullable=False,
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

    status: Mapped[str] = mapped_column(
        String(50),
        default="CHUAN_BI",
        nullable=False,
        index=True,
    )

    is_locked: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        index=True,
    )

    locked_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    locked_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )

    lock_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    status_before_lock: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    start_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    end_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )

    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
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

    school_year: Mapped["SchoolYear"] = relationship()

    commune: Mapped["Commune"] = relationship()

    creator: Mapped["User | None"] = relationship(
        foreign_keys=[created_by_user_id],
    )

    locked_by: Mapped["User | None"] = relationship(
        foreign_keys=[locked_by_user_id],
    )

    survey_forms: Mapped[list["SurveyForm"]] = relationship(
        back_populates="survey_batch",
        cascade="all, delete-orphan",
    )

    lock_logs: Mapped[list["SurveyBatchLockLog"]] = relationship(
        back_populates="survey_batch",
        cascade="all, delete-orphan",
    )


# =========================================================
# NHẬT KÝ CHỐT VÀ MỞ KHÓA ĐỢT ĐIỀU TRA
# =========================================================

class SurveyBatchLockLog(Base):
    """
    Lưu lịch sử chốt số liệu và mở khóa đợt điều tra.

    Mỗi bản ghi giữ lại người thực hiện, thời gian, lý do
    và các số liệu tổng hợp tại thời điểm thao tác.
    """

    __tablename__ = "survey_batch_lock_logs"

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

    action: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
    )

    actor_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )

    actor_name_snapshot: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )

    actor_role_snapshot: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    reason: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    form_total: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    completed_form_total: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    blocking_issue_total: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    previous_status: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    new_status: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.now,
        nullable=False,
        index=True,
    )

    survey_batch: Mapped[SurveyBatch] = relationship(
        back_populates="lock_logs",
    )

    actor: Mapped["User | None"] = relationship(
        foreign_keys=[actor_user_id],
    )


# =========================================================
# PHIẾU ĐIỀU TRA MỘT HỘ
# =========================================================

class SurveyForm(Base):
    """
    Một phiếu điều tra của một hộ
    trong một đợt điều tra cụ thể.

    Thông tin chủ hộ và địa chỉ được lưu lại
    tại thời điểm xuất phiếu để bảo toàn lịch sử.
    """

    __tablename__ = "survey_forms"

    __table_args__ = (
        UniqueConstraint(
            "survey_batch_id",
            "household_id",
            name="uq_survey_form_batch_household",
        ),
        UniqueConstraint(
            "survey_batch_id",
            "form_number",
            name="uq_survey_form_batch_number",
        ),
    )

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

    household_id: Mapped[int] = mapped_column(
        ForeignKey("households.id"),
        nullable=False,
        index=True,
    )

    form_number: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )

    head_name_snapshot: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    address_snapshot: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    hamlet_name_snapshot: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )

    survey_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    status: Mapped[str] = mapped_column(
        String(50),
        default="CHUA_DIEU_TRA",
        nullable=False,
        index=True,
    )

    village_head_name: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )

    household_representative_name: Mapped[
        str | None
    ] = mapped_column(
        String(200),
        nullable=True,
    )

    household_confirmed_at: Mapped[
        datetime | None
    ] = mapped_column(
        DateTime,
        nullable=True,
    )

    commune_confirmed_at: Mapped[
        datetime | None
    ] = mapped_column(
        DateTime,
        nullable=True,
    )

    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
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

    survey_batch: Mapped[SurveyBatch] = relationship(
        back_populates="survey_forms",
    )

    household: Mapped[Household] = relationship(
        back_populates="survey_forms",
    )

    investigators: Mapped[
        list["SurveyFormInvestigator"]
    ] = relationship(
        back_populates="survey_form",
        cascade="all, delete-orphan",
    )

    person_year_records: Mapped[
        list["SurveyPersonYearRecord"]
    ] = relationship(
        back_populates="survey_form",
        cascade="all, delete-orphan",
    )


# =========================================================
# GIÁO VIÊN/CÁN BỘ ĐIỀU TRA
# =========================================================

class SurveyFormInvestigator(Base):
    """
    Cán bộ hoặc giáo viên được phân công
    thực hiện một phiếu điều tra.

    order_number cho phép lưu người điều tra
    thứ 1, thứ 2 và thứ 3.
    """

    __tablename__ = "survey_form_investigators"

    __table_args__ = (
        UniqueConstraint(
            "survey_form_id",
            "user_id",
            name="uq_survey_form_investigator_user",
        ),
        UniqueConstraint(
            "survey_form_id",
            "order_number",
            name="uq_survey_form_investigator_order",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    survey_form_id: Mapped[int] = mapped_column(
        ForeignKey("survey_forms.id"),
        nullable=False,
        index=True,
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    order_number: Mapped[int] = mapped_column(
        Integer,
        default=1,
        nullable=False,
    )

    is_primary: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    signed_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.now,
        nullable=False,
    )

    survey_form: Mapped[SurveyForm] = relationship(
        back_populates="investigators",
    )

    user: Mapped["User"] = relationship()


# =========================================================
# KẾT QUẢ ĐIỀU TRA TỪNG NĂM HỌC
# =========================================================

class SurveyPersonYearRecord(Base):
    """
    Thông tin của một đối tượng trong một năm học
    và một phiếu điều tra cụ thể.

    Trường và lớp có thể chưa tồn tại trong danh mục,
    ví dụ trẻ học ngoài địa bàn. Khi đó vẫn lưu được
    tên trường và tên lớp do giáo viên ghi nhận.
    """

    __tablename__ = "survey_person_year_records"

    __table_args__ = (
        UniqueConstraint(
            "survey_form_id",
            "survey_person_id",
            "school_year_id",
            name="uq_survey_person_form_year",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    survey_form_id: Mapped[int] = mapped_column(
        ForeignKey("survey_forms.id"),
        nullable=False,
        index=True,
    )

    survey_person_id: Mapped[int] = mapped_column(
        ForeignKey("survey_people.id"),
        nullable=False,
        index=True,
    )

    school_year_id: Mapped[int] = mapped_column(
        ForeignKey("school_years.id"),
        nullable=False,
        index=True,
    )

    school_id: Mapped[int | None] = mapped_column(
        ForeignKey("schools.id"),
        nullable=True,
        index=True,
    )

    class_id: Mapped[int | None] = mapped_column(
        ForeignKey("classes.id"),
        nullable=True,
        index=True,
    )

    school_name_reported: Mapped[str | None] = mapped_column(
        String(300),
        nullable=True,
    )

    class_name_reported: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )

    learning_status: Mapped[str] = mapped_column(
        String(50),
        default="CHUA_XAC_DINH",
        nullable=False,
        index=True,
    )

    # Đánh dấu hồ sơ năm học đã được cán bộ rà soát và bấm Lưu.
    # Các hồ sơ được tạo tự động khi kế thừa có giá trị False để giao diện
    # còn hiển thị dữ liệu năm trước làm gợi ý. Sau lần lưu đầu tiên, phần
    # tham chiếu được ẩn để tránh nhầm lẫn với dữ liệu chính thức năm hiện tại.
    is_reviewed: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        index=True,
    )

    # Theo dõi khuyết tật theo từng năm học. Không lưu trực tiếp trên hồ sơ
    # cá nhân vì tình trạng, mức độ, giấy xác nhận và hình thức học có thể
    # thay đổi qua từng năm điều tra.
    disability_status: Mapped[str] = mapped_column(
        String(30),
        default="CHUA_XAC_DINH",
        nullable=False,
        index=True,
    )

    # === BAI_13B_11_14_2_REPORT_DISABILITY_MODEL_START ===
    disability_can_learn: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
    )

    disability_access_education: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
    )
    # === BAI_13B_11_14_2_REPORT_DISABILITY_MODEL_END ===


    disability_type: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    disability_level: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
    )

    disability_certificate: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
    )

    inclusive_education: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
    )

    disability_support: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
    )

    disability_support_details: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    completed_preschool_5: Mapped[
        bool | None
    ] = mapped_column(
        Boolean,
        nullable=True,
    )

    # Chỉ tiêu mới theo Nghị định 277/2025/NĐ-CP:
    # trẻ 3, 4 hoặc 5 tuổi hoàn thành Chương trình GDMN
    # tương ứng với độ tuổi trong năm học đang theo dõi.
    completed_preschool_by_age: Mapped[
        bool | None
    ] = mapped_column(
        Boolean,
        nullable=True,
    )

    # === BAI_13B_11_13_1_XMC_TH_THCS_FIELDS_START ===
    is_literacy_target: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
    )
    literacy_status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="CHUA_XAC_DINH",
        server_default="CHUA_XAC_DINH",
    )
    completed_grade_3: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
    )
    completed_grade_5: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
    )
    completed_primary_program: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
    )
    completed_lower_secondary_program: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
    )
    post_lower_secondary_path: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="CHUA_XAC_DINH",
        server_default="CHUA_XAC_DINH",
    )

    # === BAI_13B_11_15_1_PRIMARY_THCS_FIELDS_START ===
    study_location_scope: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="CHUA_XAC_DINH",
        server_default="CHUA_XAC_DINH",
    )
    is_repeating_grade: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
    )
    current_education_program: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="CHUA_XAC_DINH",
        server_default="CHUA_XAC_DINH",
    )
        # === BAI_13B_12_V2_1_ATTAINMENT_FIELDS_START ===
    # Trình độ học vấn của MỌI thành viên hộ theo năm điều tra.
    # Không thay thế / không suy diễn các field XMC completed_grade_3/5.
    highest_completed_grade: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    education_attainment_level: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default="CHUA_XAC_DINH",
        server_default="CHUA_XAC_DINH",
    )
    # === BAI_13B_12_V2_1_ATTAINMENT_FIELDS_END ===

# === BAI_13B_11_15_1_PRIMARY_THCS_FIELDS_END ===

    # === BAI_13B_11_13_1_XMC_TH_THCS_FIELDS_END ===


    special_circumstances: Mapped[
        str | None
    ] = mapped_column(
        Text,
        nullable=True,
    )

    # Tiêu chí 1:
    # Trẻ đi học đủ ngày theo quy định
    attends_required_days: Mapped[
        bool | None
    ] = mapped_column(
        Boolean,
        nullable=True,
    )

    # Tiêu chí 2:
    # Trẻ đi học chuyên cần
    attends_regularly: Mapped[
        bool | None
    ] = mapped_column(
        Boolean,
        nullable=True,
    )

    # Tiêu chí 3:
    # Trẻ dân tộc được chuẩn bị tiếng Việt
    prepared_vietnamese: Mapped[
        bool | None
    ] = mapped_column(
        Boolean,
        nullable=True,
    )

    # Tiêu chí 4:
    # Theo dõi bằng biểu đồ cân nặng
    weight_monitored: Mapped[
        bool | None
    ] = mapped_column(
        Boolean,
        nullable=True,
    )

    # Tiêu chí 5:
    # Suy dinh dưỡng thể nhẹ cân
    underweight: Mapped[
        bool | None
    ] = mapped_column(
        Boolean,
        nullable=True,
    )

    # Tiêu chí 6:
    # Theo dõi bằng biểu đồ chiều cao
    height_monitored: Mapped[
        bool | None
    ] = mapped_column(
        Boolean,
        nullable=True,
    )

    # Tiêu chí 7:
    # Suy dinh dưỡng thể thấp còi
    stunted: Mapped[
        bool | None
    ] = mapped_column(
        Boolean,
        nullable=True,
    )

    # === BAI_13B_11_13_3_5_TWO_SESSIONS_MODEL_START ===
    # Tiêu chí 8: Học 2 buổi/ngày
    attends_two_sessions_per_day: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
    )
    # === BAI_13B_11_13_3_5_TWO_SESSIONS_MODEL_END ===

    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
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

    survey_form: Mapped[SurveyForm] = relationship(
        back_populates="person_year_records",
    )

    survey_person: Mapped[SurveyPerson] = relationship(
        back_populates="year_records",
    )

    school_year: Mapped["SchoolYear"] = relationship()

    school: Mapped["School | None"] = relationship()

    classroom: Mapped["Classroom | None"] = relationship()

# =========================================================
# NHẬT KÝ PHÁT HÀNH VÀ TIẾP NHẬN FILE ĐIỀU TRA
# =========================================================

class SurveyFileExchangeLog(Base):
    """
    Lưu lịch sử xuất file điều tra và nhập file cập nhật.

    Bản ghi dùng cho Trung tâm phát hành và tiếp nhận phiếu:
    - Biết xã/phường đã được phát hành file lúc nào.
    - Biết file cập nhật đã được tiếp nhận thành công lúc nào.
    - Lưu người thực hiện và các số liệu tại thời điểm thao tác.
    """

    __tablename__ = "survey_file_exchange_logs"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    school_year_id: Mapped[int] = mapped_column(
        ForeignKey("school_years.id"),
        nullable=False,
        index=True,
    )

    survey_batch_id: Mapped[int] = mapped_column(
        ForeignKey("survey_batches.id"),
        nullable=False,
        index=True,
    )

    commune_id: Mapped[int] = mapped_column(
        ForeignKey("communes.id"),
        nullable=False,
        index=True,
    )

    action: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        index=True,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        default="THANH_CONG",
        nullable=False,
        index=True,
    )

    file_name: Mapped[str | None] = mapped_column(
        String(300),
        nullable=True,
    )

    actor_user_id: Mapped[int | None] = mapped_column(
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

    form_total: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    person_total: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    updated_household_total: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    updated_person_total: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    created_person_total: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    updated_year_record_total: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    created_year_record_total: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.now,
        nullable=False,
        index=True,
    )

    school_year: Mapped["SchoolYear"] = relationship()
    survey_batch: Mapped[SurveyBatch] = relationship()
    commune: Mapped["Commune"] = relationship()
    actor: Mapped["User | None"] = relationship(
        foreign_keys=[actor_user_id],
    )


# =========================================================
# BỘ DỮ LIỆU LỊCH SỬ THEO NĂM HỌC VÀ XÃ/PHƯỜNG
# =========================================================

class HistoricalDataset(Base):
    """
    Một bộ dữ liệu lịch sử của một xã/phường trong một năm học.

    Dữ liệu này được cập nhật độc lập với các đợt điều tra đang vận hành,
    sau đó có thể khóa làm dữ liệu nền và đối chiếu với dữ liệu học sinh.
    """

    __tablename__ = "historical_datasets"

    __table_args__ = (
        UniqueConstraint(
            "school_year_id",
            "commune_id",
            name="uq_historical_dataset_year_commune",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
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

    status: Mapped[str] = mapped_column(
        String(30),
        default="DANG_CAP_NHAT",
        nullable=False,
        index=True,
    )

    reconciliation_status: Mapped[str] = mapped_column(
        String(30),
        default="CHUA_DOI_CHIEU",
        nullable=False,
        index=True,
    )

    source_file_name: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )

    submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    submitted_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )

    locked_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    locked_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )

    lock_reason: Mapped[str | None] = mapped_column(
        Text,
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

    school_year: Mapped["SchoolYear"] = relationship()
    commune: Mapped["Commune"] = relationship()

    creator: Mapped["User | None"] = relationship(
        foreign_keys=[created_by_user_id],
    )

    submitter: Mapped["User | None"] = relationship(
        foreign_keys=[submitted_by_user_id],
    )

    locker: Mapped["User | None"] = relationship(
        foreign_keys=[locked_by_user_id],
    )

    households: Mapped[list["HistoricalHousehold"]] = relationship(
        back_populates="dataset",
        cascade="all, delete-orphan",
    )

    people: Mapped[list["HistoricalPerson"]] = relationship(
        back_populates="dataset",
        cascade="all, delete-orphan",
    )

    logs: Mapped[list["HistoricalDataLog"]] = relationship(
        back_populates="dataset",
        cascade="all, delete-orphan",
    )


# =========================================================
# HỘ GIA ĐÌNH TRONG DỮ LIỆU LỊCH SỬ
# =========================================================

class HistoricalHousehold(Base):
    """Thông tin một hộ tại thời điểm của bộ dữ liệu lịch sử."""

    __tablename__ = "historical_households"

    __table_args__ = (
        UniqueConstraint(
            "dataset_id",
            "household_code",
            name="uq_historical_household_dataset_code",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    dataset_id: Mapped[int] = mapped_column(
        ForeignKey("historical_datasets.id"),
        nullable=False,
        index=True,
    )

    household_code: Mapped[str] = mapped_column(
        String(80),
        nullable=False,
        index=True,
    )

    head_name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        index=True,
    )

    hamlet_name: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
        index=True,
    )

    address: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    phone: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
        index=True,
    )

    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    is_active: Mapped[bool] = mapped_column(
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

    dataset: Mapped[HistoricalDataset] = relationship(
        back_populates="households",
    )

    people: Mapped[list["HistoricalPerson"]] = relationship(
        back_populates="household",
        cascade="all, delete-orphan",
    )


# =========================================================
# ĐỐI TƯỢNG TRONG DỮ LIỆU LỊCH SỬ
# =========================================================

class HistoricalPerson(Base):
    """
    Thông tin một đối tượng tại thời điểm của bộ dữ liệu lịch sử.

    Các trường liên kết học sinh và trạng thái đối chiếu được chuẩn bị sẵn
    cho Bài 12D-14B, nhưng chưa tự động ghép trong Bài 12D-14A.
    """

    __tablename__ = "historical_people"

    __table_args__ = (
        UniqueConstraint(
            "dataset_id",
            "person_code",
            name="uq_historical_person_dataset_code",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    dataset_id: Mapped[int] = mapped_column(
        ForeignKey("historical_datasets.id"),
        nullable=False,
        index=True,
    )

    historical_household_id: Mapped[int] = mapped_column(
        ForeignKey("historical_households.id"),
        nullable=False,
        index=True,
    )

    person_code: Mapped[str] = mapped_column(
        String(80),
        nullable=False,
        index=True,
    )

    linked_student_id: Mapped[int | None] = mapped_column(
        ForeignKey("students.id"),
        nullable=True,
        index=True,
    )

    linked_survey_person_id: Mapped[int | None] = mapped_column(
        ForeignKey("survey_people.id"),
        nullable=True,
        index=True,
    )

    match_status: Mapped[str] = mapped_column(
        String(30),
        default="CHUA_DOI_CHIEU",
        nullable=False,
        index=True,
    )

    match_notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
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

    relationship_to_head: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    personal_id: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        index=True,
    )

    ministry_student_code: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        index=True,
    )

    permanent_address: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    current_address: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    residency_status: Mapped[str] = mapped_column(
        String(50),
        default="CHUA_XAC_DINH",
        nullable=False,
        index=True,
    )

    learning_status: Mapped[str] = mapped_column(
        String(50),
        default="CHUA_XAC_DINH",
        nullable=False,
        index=True,
    )

    school_name_reported: Mapped[str | None] = mapped_column(
        String(300),
        nullable=True,
    )

    class_name_reported: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )

    completed_preschool_5: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
    )

    attends_required_days: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
    )

    attends_regularly: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
    )

    prepared_vietnamese: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
    )

    weight_monitored: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
    )

    underweight: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
    )

    height_monitored: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
    )

    stunted: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
    )

    special_circumstances: Mapped[str | None] = mapped_column(
        Text,
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

    dataset: Mapped[HistoricalDataset] = relationship(
        back_populates="people",
    )

    household: Mapped[HistoricalHousehold] = relationship(
        back_populates="people",
    )

    linked_student: Mapped["Student | None"] = relationship(
        foreign_keys=[linked_student_id],
    )

    linked_survey_person: Mapped["SurveyPerson | None"] = relationship(
        foreign_keys=[linked_survey_person_id],
    )


# =========================================================
# NHẬT KÝ DỮ LIỆU LỊCH SỬ
# =========================================================

class HistoricalDataLog(Base):
    """Lưu lịch sử tạo, nhập, sửa, gửi kiểm tra, khóa và mở khóa."""

    __tablename__ = "historical_data_logs"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    dataset_id: Mapped[int] = mapped_column(
        ForeignKey("historical_datasets.id"),
        nullable=False,
        index=True,
    )

    action: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        index=True,
    )

    actor_user_id: Mapped[int | None] = mapped_column(
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

    file_name: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    household_total: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    person_total: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    inserted_household_total: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    updated_household_total: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    inserted_person_total: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    updated_person_total: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.now,
        nullable=False,
        index=True,
    )

    dataset: Mapped[HistoricalDataset] = relationship(
        back_populates="logs",
    )

    actor: Mapped["User | None"] = relationship(
        foreign_keys=[actor_user_id],
    )
