from __future__ import annotations

def F(
    code: str,
    label: str,
    excel_col: int,
    *,
    field_type: str = "int",
    unit: str = "",
    help_text: str = "",
    export: bool = True,
) -> dict:
    return {
        "code": code,
        "label": label,
        "excel_col": excel_col,
        "type": field_type,
        "unit": unit,
        "help": help_text,
        "export": bool(export),
    }


STRUCTURED_SCHOOL_FORMS = {
    "th-01-gv": {
        "form_code": "TH_01_GV",
        "title": "TH-01-GV – Đội ngũ giáo viên Tiểu học",
        "short_title": "TH-01-GV",
        "level": "TH",
        "kind": "staff",
        "report_type": "PCGD_TH_01_GV_2025",
        "description": "Nhập đầy đủ các chỉ tiêu cấp trường phục vụ biểu TH-01-GV.",
        "derived": {"label": "Tỉ lệ giáo viên/lớp", "kind": "staff_ratio", "excel_col": 14},
        "groups": [
            {
                "anchor": "pham-vi-truong",
                "title": "1. Hạng trường và tổ chức dạy học",
                "fields": [
                    F("rank_1", "Hạng 1", 3, field_type="yesno"),
                    F("rank_2", "Hạng 2", 4, field_type="yesno"),
                    F("rank_3", "Hạng 3", 5, field_type="yesno"),
                    F("sessions_1_2", "Tổ chức 1–2 buổi/ngày", 6, field_type="yesno"),
                ],
            },
            {
                "anchor": "cbql-giao-vien",
                "title": "2. Cán bộ quản lý và giáo viên",
                "fields": [
                    F("principal", "Hiệu trưởng", 7, unit="người"),
                    F("vice_principal", "Phó Hiệu trưởng", 8, unit="người"),
                    F("teacher_total", "Giáo viên – Tổng số", 9, unit="người"),
                    F("teacher_permanent", "Giáo viên – Biên chế", 10, unit="người"),
                    F("teacher_contract", "Giáo viên – Hợp đồng", 11, unit="người"),
                    F("teacher_female", "Giáo viên – Nữ", 12, unit="người"),
                    F("teacher_ethnic", "Giáo viên – Dân tộc", 13, unit="người"),
                ],
            },
            {
                "anchor": "trinh-do",
                "title": "3. Trình độ đào tạo",
                "fields": [
                    F("qual_postgrad", "Trên đại học", 15, unit="người"),
                    F("qual_university", "Đại học", 16, unit="người"),
                    F("qual_college", "Cao đẳng", 17, unit="người"),
                    F("qual_secondary", "Trung học sư phạm", 18, unit="người"),
                    F("qual_below_secondary", "Dưới trung học sư phạm", 19, unit="người"),
                ],
            },
            {
                "anchor": "loai-hinh-dao-tao",
                "title": "4. Loại hình/chuyên môn đào tạo",
                "fields": [
                    F("training_primary", "Tiểu học", 20, unit="người"),
                    F("training_music", "Âm nhạc", 21, unit="người"),
                    F("training_art", "Mỹ thuật", 22, unit="người"),
                    F("training_pe", "Thể dục", 23, unit="người"),
                    F("training_it", "Tin học", 24, unit="người"),
                    F("training_foreign", "Ngoại ngữ", 25, unit="người"),
                    F("training_other", "Khác", 26, unit="người"),
                ],
            },
            {
                "anchor": "chuan-nghe-nghiep",
                "title": "5. Chuẩn nghề nghiệp",
                "fields": [
                    F("prof_excellent", "Xuất sắc", 27, unit="người"),
                    F("prof_good", "Khá", 28, unit="người"),
                    F("prof_average", "Trung bình/Đạt", 29, unit="người"),
                    F("prof_poor", "Kém/Chưa đạt", 30, unit="người"),
                ],
            },
            {
                "anchor": "nhan-vien",
                "title": "6. Tổng phụ trách và nhân viên",
                "fields": [
                    F("team_leader", "Tổng phụ trách Đội", 31, unit="người"),
                    F("employee_office", "Nhân viên văn phòng", 32, unit="người"),
                    F("employee_library_equipment", "Nhân viên thư viện – thiết bị dạy học", 33, unit="người"),
                ],
            },
            {
                "anchor": "dieu-kien-bao-dam-pcgd",
                "title": '7. Xác nhận điều kiện bảo đảm PCGD Tiểu học – Đội ngũ',
                # === BAI_13B_12_V2_4_4_1_PCGD_CONDITION_CHECKLIST ===
                # Checklist không xuất thành cột Excel.
                "fields": [
                    F(
                        'pcgd_staffing_sufficient',
                        'Đủ giáo viên và nhân viên theo quy định/định mức hiện hành',
                        0,
                        field_type="yesno",
                        export=False,
                        help_text='Xác nhận điều kiện đội ngũ phục vụ công tác phổ cập.',
                    ),
                    F(
                        'pcgd_teacher_training_standard_all',
                        '100% giáo viên đạt chuẩn trình độ đào tạo theo quy định',
                        0,
                        field_type="yesno",
                        export=False,
                        help_text='Chỉ chọn Có khi đã kiểm tra toàn bộ giáo viên thuộc phạm vi.',
                    ),
                    F(
                        'pcgd_teacher_professional_standard_all',
                        '100% giáo viên đạt yêu cầu chuẩn nghề nghiệp',
                        0,
                        field_type="yesno",
                        export=False,
                        help_text='Chỉ chọn Có khi đã kiểm tra toàn bộ giáo viên thuộc phạm vi.',
                    ),
                    F(
                        'pcgd_tracker_assigned',
                        'Đã phân công người theo dõi công tác PCGD-XMC',
                        0,
                        field_type="yesno",
                        export=False,
                        help_text='Người theo dõi công tác PCGD-XMC đã được phân công.',
                    ),
                ],
            },
        ],
    },

    "th-01-csvc": {
        "form_code": "TH_01_CSVC",
        "title": "TH-01-CSVC – Cơ sở vật chất Tiểu học",
        "short_title": "TH-01-CSVC",
        "level": "TH",
        "kind": "facility",
        "report_type": "PCGD_TH_01_CSVC_2025",
        "description": "Nhập đầy đủ các chỉ tiêu cấp trường phục vụ biểu TH-01-CSVC.",
        "derived": {"label": "Tỉ lệ phòng học/lớp", "kind": "facility_ratio", "excel_col": 10},
        "groups": [
            {
                "anchor": "diem-truong-lop-phong",
                "title": "1. Điểm trường, lớp và phòng học",
                "fields": [
                    F("school_site_count", "Số điểm trường", 3, unit="điểm"),
                    F("class_total", "Số lớp – Tổng số", 4, unit="lớp"),
                    F("combined_class_count", "Số lớp ghép", 5, unit="lớp"),
                    F("room_permanent", "Phòng học kiên cố", 6, unit="phòng"),
                    F("room_semi_permanent", "Phòng học bán kiên cố", 7, unit="phòng"),
                    F("room_temporary", "Phòng học tạm", 8, unit="phòng"),
                    F("room_rent_borrow", "Phòng học thuê/mượn", 9, unit="phòng"),
                ],
            },
            {
                "anchor": "phong-chuc-nang",
                "title": "2. Phòng chức năng",
                "fields": [
                    F("principal_office_count", "Phòng Hiệu trưởng – Số lượng", 11, unit="phòng"),
                    F("vice_office_count", "Phòng Phó Hiệu trưởng – Số lượng", 12, unit="phòng"),
                    F("office_room_count", "Văn phòng – Số lượng", 13, unit="phòng"),
                    F("health_room_count", "Phòng Y tế – Số lượng", 14, unit="phòng"),
                    F("team_activity_room_count", "Phòng hoạt động Đội – Số lượng", 15, unit="phòng"),
                    F("meeting_room_count", "Phòng họp – Số lượng", 16, unit="phòng"),
                    F("meeting_room_area", "Phòng họp – Diện tích", 17, field_type="decimal", unit="m²"),
                    F("library_room_count", "Thư viện – Số lượng", 18, unit="phòng"),
                    F("library_room_area", "Thư viện – Diện tích", 19, field_type="decimal", unit="m²"),
                    F("equipment_room_count", "Phòng thiết bị – Số lượng", 20, unit="phòng"),
                    F("equipment_room_area", "Phòng thiết bị – Diện tích", 21, field_type="decimal", unit="m²"),
                ],
            },
            {
                "anchor": "cong-trinh-ve-sinh",
                "title": "3. Công trình vệ sinh",
                "fields": [
                    F("teacher_toilet_count", "Khu vệ sinh giáo viên – Số lượng", 22, unit="khu"),
                    F("teacher_toilet_area", "Khu vệ sinh giáo viên – Diện tích", 23, field_type="decimal", unit="m²"),
                    F("student_toilet_count", "Khu vệ sinh học sinh – Số lượng", 24, unit="khu"),
                    F("student_toilet_area", "Khu vệ sinh học sinh – Diện tích", 25, field_type="decimal", unit="m²"),
                ],
            },
            {
                "anchor": "san-bai",
                "title": "4. Sân chơi và bãi tập",
                "fields": [
                    F("playground_count", "Sân chơi – Số lượng", 26, unit="sân"),
                    F("playground_area", "Sân chơi – Diện tích", 27, field_type="decimal", unit="m²"),
                    F("sports_ground_count", "Bãi tập – Số lượng", 28, unit="bãi"),
                    F("sports_ground_area", "Bãi tập – Diện tích", 29, field_type="decimal", unit="m²"),
                ],
            },
            {
                "anchor": "dieu-kien-bao-dam-pcgd",
                "title": '5. Xác nhận điều kiện bảo đảm PCGD Tiểu học – CSVC, TBDH',
                # === BAI_13B_12_V2_4_4_1_PCGD_CONDITION_CHECKLIST ===
                # Checklist không xuất thành cột Excel.
                "fields": [
                    F(
                        'pcgd_classrooms_standard_safe',
                        'Phòng học bảo đảm tiêu chuẩn, an toàn, ánh sáng và điều kiện học tập',
                        0,
                        field_type="yesno",
                        export=False,
                        help_text='Tỉ lệ phòng/lớp được hệ thống kiểm tra riêng.',
                    ),
                    F(
                        'pcgd_furniture_access_sufficient',
                        'Đủ bàn ghế, bảng, bàn ghế giáo viên và điều kiện tối thiểu cho người học khuyết tật',
                        0,
                        field_type="yesno",
                        export=False,
                        help_text='Xác nhận điều kiện sử dụng thực tế.',
                    ),
                    F(
                        'pcgd_function_rooms_sufficient',
                        'Có đủ các phòng chức năng cần thiết theo quy định',
                        0,
                        field_type="yesno",
                        export=False,
                        help_text='Phòng quản lý, y tế, thư viện, thiết bị/thí nghiệm và phòng liên quan theo cấp học.',
                    ),
                    F(
                        'pcgd_minimum_teaching_equipment_sufficient',
                        'Đủ thiết bị dạy học tối thiểu theo quy định',
                        0,
                        field_type="yesno",
                        export=False,
                        help_text='Không chỉ tính số phòng; phải xác nhận đủ thiết bị tối thiểu.',
                    ),
                    F(
                        'pcgd_teaching_equipment_regular_use',
                        'Thiết bị dạy học được sử dụng thường xuyên, thuận tiện',
                        0,
                        field_type="yesno",
                        export=False,
                        help_text='Xác nhận tình trạng sử dụng thực tế.',
                    ),
                    F(
                        'pcgd_playground_sports_safe',
                        'Sân chơi/bãi tập phù hợp, sử dụng thường xuyên và an toàn',
                        0,
                        field_type="yesno",
                        export=False,
                        help_text='Xác nhận điều kiện sân chơi, bãi tập.',
                    ),
                    F(
                        'pcgd_clean_water_drainage',
                        'Có nguồn nước sạch và hệ thống thoát nước',
                        0,
                        field_type="yesno",
                        export=False,
                        help_text='Xác nhận điều kiện nước sạch, thoát nước.',
                    ),
                    F(
                        'pcgd_toilets_separate_hygienic',
                        'Công trình vệ sinh thuận tiện, hợp vệ sinh và tách phù hợp',
                        0,
                        field_type="yesno",
                        export=False,
                        help_text='Xác nhận điều kiện vệ sinh.',
                    ),
                ],
            },
        ],
    },

    "thcs-01-gv": {
        "form_code": "THCS_01_GV",
        "title": "THCS-01-GV – Đội ngũ giáo viên THCS",
        "short_title": "THCS-01-GV",
        "level": "THCS",
        "kind": "staff",
        "report_type": "PCGD_THCS_M5_2025",
        "description": "Nhập đầy đủ các chỉ tiêu cấp trường phục vụ biểu THCS-01-GV.",
        "derived": {"label": "Tỉ lệ giáo viên/lớp", "kind": "staff_ratio", "excel_col": 13},
        "groups": [
            {
                "anchor": "hang-truong",
                "title": "1. Hạng trường",
                "fields": [
                    F("rank_1", "Hạng 1", 3, field_type="yesno"),
                    F("rank_2", "Hạng 2", 4, field_type="yesno"),
                    F("rank_3", "Hạng 3", 5, field_type="yesno"),
                ],
            },
            {
                "anchor": "cbql-giao-vien",
                "title": "2. Cán bộ quản lý và giáo viên",
                "fields": [
                    F("principal", "Hiệu trưởng", 6, unit="người"),
                    F("vice_principal", "Phó Hiệu trưởng", 7, unit="người"),
                    F("teacher_total", "Giáo viên – Tổng số", 8, unit="người"),
                    F("teacher_permanent", "Giáo viên – Biên chế", 9, unit="người"),
                    F("teacher_contract", "Giáo viên – Hợp đồng", 10, unit="người"),
                    F("teacher_female", "Giáo viên – Nữ", 11, unit="người"),
                    F("teacher_ethnic", "Giáo viên – Dân tộc", 12, unit="người"),
                ],
            },
            {
                "anchor": "trinh-do",
                "title": "3. Trình độ đào tạo",
                "fields": [
                    F("qual_postgrad", "Trên đại học", 14, unit="người"),
                    F("qual_university", "Đại học", 15, unit="người"),
                    F("qual_college", "Cao đẳng", 16, unit="người"),
                    F("qual_secondary", "Trung học sư phạm", 17, unit="người"),
                ],
            },
            {
                "anchor": "chuyen-nganh",
                "title": "4. Chuyên ngành đào tạo",
                "fields": [
                    F("subject_math", "Toán", 18, unit="người"),
                    F("subject_literature", "Ngữ văn", 19, unit="người"),
                    F("subject_physics", "KHTN – Vật lí", 20, unit="người"),
                    F("subject_chemistry", "KHTN – Hóa học", 21, unit="người"),
                    F("subject_biology", "KHTN – Sinh học", 22, unit="người"),
                    F("subject_history", "KHXH – Lịch sử", 23, unit="người"),
                    F("subject_geography", "KHXH – Địa lí", 24, unit="người"),
                    F("subject_music", "HĐGD – Âm nhạc", 25, unit="người"),
                    F("subject_art", "HĐGD – Mỹ thuật", 26, unit="người"),
                    F("subject_pe", "HĐGD – Thể dục", 27, unit="người"),
                    F("subject_civic", "GDCD", 28, unit="người"),
                    F("subject_technology", "Công nghệ", 29, unit="người"),
                    F("subject_it", "Tin học", 30, unit="người"),
                    F("subject_english", "Ngoại ngữ – Tiếng Anh", 31, unit="người"),
                    F("subject_russian", "Ngoại ngữ – Tiếng Nga", 32, unit="người"),
                    F("subject_french", "Ngoại ngữ – Tiếng Pháp", 33, unit="người"),
                    F("subject_other", "Chuyên ngành khác", 34, unit="người"),
                ],
            },
            {
                "anchor": "chuan-nghe-nghiep",
                "title": "5. Tổng phụ trách và chuẩn nghề nghiệp",
                "fields": [
                    F("team_leader", "Tổng phụ trách Đội", 35, unit="người"),
                    F("prof_excellent", "Chuẩn nghề nghiệp – Xuất sắc", 36, unit="người"),
                    F("prof_good", "Chuẩn nghề nghiệp – Khá", 37, unit="người"),
                    F("prof_average", "Chuẩn nghề nghiệp – Trung bình/Đạt", 38, unit="người"),
                    F("prof_poor", "Chuẩn nghề nghiệp – Kém/Chưa đạt", 39, unit="người"),
                ],
            },
            {
                "anchor": "nhan-vien",
                "title": "6. Nhân viên",
                "fields": [
                    F("employee_library", "Nhân viên thư viện", 40, unit="người"),
                    F("employee_equipment_lab", "Nhân viên thiết bị – thí nghiệm", 41, unit="người"),
                    F("employee_office", "Nhân viên văn phòng", 42, unit="người"),
                    F("employee_health", "Nhân viên y tế", 43, unit="người"),
                ],
            },
            {
                "anchor": "dieu-kien-bao-dam-pcgd",
                "title": '7. Xác nhận điều kiện bảo đảm PCGD THCS – Đội ngũ',
                # === BAI_13B_12_V2_4_4_1_PCGD_CONDITION_CHECKLIST ===
                # Checklist không xuất thành cột Excel.
                "fields": [
                    F(
                        'pcgd_staffing_sufficient',
                        'Đủ giáo viên và nhân viên theo quy định/định mức hiện hành',
                        0,
                        field_type="yesno",
                        export=False,
                        help_text='Xác nhận điều kiện đội ngũ phục vụ công tác phổ cập.',
                    ),
                    F(
                        'pcgd_teacher_training_standard_all',
                        '100% giáo viên đạt chuẩn trình độ đào tạo theo quy định',
                        0,
                        field_type="yesno",
                        export=False,
                        help_text='Chỉ chọn Có khi đã kiểm tra toàn bộ giáo viên thuộc phạm vi.',
                    ),
                    F(
                        'pcgd_teacher_professional_standard_all',
                        '100% giáo viên đạt yêu cầu chuẩn nghề nghiệp',
                        0,
                        field_type="yesno",
                        export=False,
                        help_text='Chỉ chọn Có khi đã kiểm tra toàn bộ giáo viên thuộc phạm vi.',
                    ),
                    F(
                        'pcgd_tracker_assigned',
                        'Đã phân công người theo dõi công tác PCGD-XMC',
                        0,
                        field_type="yesno",
                        export=False,
                        help_text='Người theo dõi công tác PCGD-XMC đã được phân công.',
                    ),
                ],
            },
        ],
    },

    "thcs-01-csvc": {
        "form_code": "THCS_01_CSVC",
        "title": "THCS-01-CSVC – Cơ sở vật chất THCS",
        "short_title": "THCS-01-CSVC",
        "level": "THCS",
        "kind": "facility",
        "report_type": "PCGD_THCS_CSVC_2025",
        "description": "Nhập đầy đủ các chỉ tiêu cấp trường phục vụ biểu THCS-01-CSVC.",
        "derived": {"label": "Tỉ lệ phòng học/lớp", "kind": "facility_ratio", "excel_col": 8},
        "groups": [
            {
                "anchor": "diem-truong-lop-phong",
                "title": "1. Điểm trường, lớp và phòng học",
                "fields": [
                    F("school_site_count", "Số điểm trường", 3, unit="điểm"),
                    F("class_total", "Số lớp", 4, unit="lớp"),
                    F("room_permanent", "Phòng học kiên cố", 5, unit="phòng"),
                    F("room_semi_permanent", "Phòng học bán kiên cố", 6, unit="phòng"),
                    F("room_temporary", "Phòng học tạm", 7, unit="phòng"),
                ],
            },
            {
                "anchor": "phong-chuc-nang",
                "title": "2. Phòng chức năng và phòng thí nghiệm",
                "fields": [
                    F("principal_office_count", "Phòng Hiệu trưởng", 9, unit="phòng"),
                    F("vice_office_count", "Phòng Phó Hiệu trưởng", 10, unit="phòng"),
                    F("office_room_count", "Văn phòng", 11, unit="phòng"),
                    F("health_room_count", "Phòng Y tế", 12, unit="phòng"),
                    F("meeting_room_count", "Phòng họp", 13, unit="phòng"),
                    F("library_room_count", "Thư viện", 14, unit="phòng"),
                    F("laboratory_room_count", "Phòng thí nghiệm – Số lượng", 15, unit="phòng"),
                    F("laboratory_room_area", "Phòng thí nghiệm – Diện tích", 16, field_type="decimal", unit="m²"),
                ],
            },
            {
                "anchor": "cong-trinh-ve-sinh",
                "title": "3. Công trình vệ sinh",
                "fields": [
                    F("teacher_toilet_count", "Khu vệ sinh giáo viên – Số lượng", 17, unit="khu"),
                    F("teacher_toilet_area", "Khu vệ sinh giáo viên – Diện tích", 18, field_type="decimal", unit="m²"),
                    F("student_toilet_count", "Khu vệ sinh học sinh – Số lượng", 19, unit="khu"),
                    F("student_toilet_area", "Khu vệ sinh học sinh – Diện tích", 20, field_type="decimal", unit="m²"),
                ],
            },
            {
                "anchor": "san-bai",
                "title": "4. Sân chơi và bãi tập",
                "fields": [
                    F("playground_count", "Sân chơi – Số lượng", 21, unit="sân"),
                    F("playground_area", "Sân chơi – Diện tích", 22, field_type="decimal", unit="m²"),
                    F("sports_ground_count", "Bãi tập – Số lượng", 23, unit="bãi"),
                    F("sports_ground_area", "Bãi tập – Diện tích", 24, field_type="decimal", unit="m²"),
                ],
            },
            {
                "anchor": "dieu-kien-bao-dam-pcgd",
                "title": '5. Xác nhận điều kiện bảo đảm PCGD THCS – CSVC, TBDH',
                # === BAI_13B_12_V2_4_4_1_PCGD_CONDITION_CHECKLIST ===
                # Checklist không xuất thành cột Excel.
                "fields": [
                    F(
                        'pcgd_classrooms_standard_safe',
                        'Phòng học bảo đảm tiêu chuẩn, an toàn, ánh sáng và điều kiện học tập',
                        0,
                        field_type="yesno",
                        export=False,
                        help_text='Tỉ lệ phòng/lớp được hệ thống kiểm tra riêng.',
                    ),
                    F(
                        'pcgd_furniture_access_sufficient',
                        'Đủ bàn ghế, bảng, bàn ghế giáo viên và điều kiện tối thiểu cho người học khuyết tật',
                        0,
                        field_type="yesno",
                        export=False,
                        help_text='Xác nhận điều kiện sử dụng thực tế.',
                    ),
                    F(
                        'pcgd_function_rooms_sufficient',
                        'Có đủ các phòng chức năng cần thiết theo quy định',
                        0,
                        field_type="yesno",
                        export=False,
                        help_text='Phòng quản lý, y tế, thư viện, thiết bị/thí nghiệm và phòng liên quan theo cấp học.',
                    ),
                    F(
                        'pcgd_minimum_teaching_equipment_sufficient',
                        'Đủ thiết bị dạy học tối thiểu theo quy định',
                        0,
                        field_type="yesno",
                        export=False,
                        help_text='Không chỉ tính số phòng; phải xác nhận đủ thiết bị tối thiểu.',
                    ),
                    F(
                        'pcgd_teaching_equipment_regular_use',
                        'Thiết bị dạy học được sử dụng thường xuyên, thuận tiện',
                        0,
                        field_type="yesno",
                        export=False,
                        help_text='Xác nhận tình trạng sử dụng thực tế.',
                    ),
                    F(
                        'pcgd_playground_sports_safe',
                        'Sân chơi/bãi tập phù hợp, sử dụng thường xuyên và an toàn',
                        0,
                        field_type="yesno",
                        export=False,
                        help_text='Xác nhận điều kiện sân chơi, bãi tập.',
                    ),
                    F(
                        'pcgd_clean_water_drainage',
                        'Có nguồn nước sạch và hệ thống thoát nước',
                        0,
                        field_type="yesno",
                        export=False,
                        help_text='Xác nhận điều kiện nước sạch, thoát nước.',
                    ),
                    F(
                        'pcgd_toilets_separate_hygienic',
                        'Công trình vệ sinh thuận tiện, hợp vệ sinh và tách phù hợp',
                        0,
                        field_type="yesno",
                        export=False,
                        help_text='Xác nhận điều kiện vệ sinh.',
                    ),
                ],
            },
        ],
    },
}


STRUCTURED_FORM_BY_CODE = {
    item["form_code"]: item for item in STRUCTURED_SCHOOL_FORMS.values()
}


def flatten_fields(catalog: dict) -> list[dict]:
    return [field for group in catalog.get("groups", []) for field in group.get("fields", [])]
