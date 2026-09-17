from __future__ import annotations

import csv
import os
import re
import sqlite3
import traceback
import zipfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree as ET


PROJECT = Path(
    os.environ.get(
        "PHOCAP_PROJECT",
        r"C:\PhoCap",
    )
).resolve()

APP = PROJECT / "app"
DB = PROJECT / "data" / "phocap.db"
EXPORTS = PROJECT / "exports"

STAMP = datetime.now().strftime(
    "%Y%m%d_%H%M%S"
)

OUT_TXT = (
    EXPORTS
    / f"bao_cao_bai_13b_11_14_0_khao_sat_7_sheet_gdmn_{STAMP}.txt"
)

OUT_CSV = (
    EXPORTS
    / f"ma_tran_bai_13b_11_14_0_nguon_du_lieu_7_sheet_{STAMP}.csv"
)

EXPECTED_SHEETS = [
    "Thống kê trẻ em từ 0 đến 5 tuổi",
    "TK dat chuan",
    "GV",
    "CSVC",
    "Báo cáo tài chính",
    "Báo cáo thống kê ĐTKT",
    "Sổ theo dõi phổ cập MN",
]


# ---------------------------------------------------------------------
# Ma trận yêu cầu được rút trực tiếp từ 7 sheet bộ biểu GDMN.
#
# source_type:
# - DERIVED: hệ thống phải tự tổng hợp, không tạo ô nhập tay.
# - PERSON: dữ liệu nhân khẩu/đối tượng.
# - YEAR: dữ liệu theo từng năm học của đối tượng.
# - EVENT: biến động có ngày/nơi đến-nơi đi/tử vong.
# - COMMUNE: danh mục xã/phường.
# - CLASS: cấu hình lớp.
# - STAFF: đội ngũ.
# - FACILITY: CSVC/TBDH.
# - FINANCE: dữ liệu tài chính theo đơn vị/năm/mã chỉ tiêu.
# ---------------------------------------------------------------------
REQUIREMENTS = [
    # ================================================================
    # SHEET 1 - MN-01-TE
    # ================================================================
    {
        "sheet": "Thống kê trẻ em từ 0 đến 5 tuổi",
        "group": "Dân số",
        "indicator": "Tổng số trẻ trong độ tuổi",
        "source_type": "DERIVED",
        "candidates": [
            "date_of_birth",
            "is_active",
            "residency_status",
        ],
        "ui": "Thông tin đối tượng/hộ",
        "condition": "Tự tính theo ngày sinh và phạm vi cư trú",
        "proposal": "Không nhập tay; tính theo tuổi tại thời điểm báo cáo.",
    },
    {
        "sheet": "Thống kê trẻ em từ 0 đến 5 tuổi",
        "group": "Dân số",
        "indicator": "Trẻ em gái",
        "source_type": "PERSON",
        "candidates": ["gender"],
        "ui": "Thông tin đối tượng",
        "condition": "Mọi trẻ",
        "proposal": "Giữ trường giới tính chuẩn hóa.",
    },
    {
        "sheet": "Thống kê trẻ em từ 0 đến 5 tuổi",
        "group": "Dân số",
        "indicator": "Trẻ dân tộc thiểu số",
        "source_type": "PERSON",
        "candidates": [
            "ethnic_group",
            "ethnicity",
        ],
        "ui": "Thông tin đối tượng",
        "condition": "Mọi trẻ",
        "proposal": "Giữ dân tộc chuẩn hóa; báo cáo tự xác định DTTS.",
    },
    {
        "sheet": "Thống kê trẻ em từ 0 đến 5 tuổi",
        "group": "Khuyết tật",
        "indicator": "Tổng số trẻ khuyết tật",
        "source_type": "YEAR",
        "candidates": ["disability_status"],
        "ui": "Thông tin năm học > Theo dõi trẻ khuyết tật",
        "condition": "Mọi trẻ",
        "proposal": "Giữ trường tình trạng khuyết tật.",
    },
    {
        "sheet": "Thống kê trẻ em từ 0 đến 5 tuổi",
        "group": "Khuyết tật",
        "indicator": "Số trẻ khuyết tật có khả năng học tập",
        "source_type": "YEAR",
        "candidates": [
            "disability_can_learn",
            "can_learn",
        ],
        "ui": "Thông tin năm học > Theo dõi trẻ khuyết tật",
        "condition": "Chỉ hiện khi Có khuyết tật",
        "proposal": (
            "Bổ sung Có/Không/Chưa xác định: "
            "Khuyết tật có khả năng học tập."
        ),
    },
    {
        "sheet": "Thống kê trẻ em từ 0 đến 5 tuổi",
        "group": "Khuyết tật",
        "indicator": "Số trẻ khuyết tật được tiếp cận giáo dục",
        "source_type": "YEAR",
        "candidates": [
            "disability_access_education",
            "access_education",
        ],
        "ui": "Thông tin năm học > Theo dõi trẻ khuyết tật",
        "condition": "Chỉ hiện khi Có khuyết tật",
        "proposal": (
            "Bổ sung Có/Không/Chưa xác định: "
            "Được tiếp cận giáo dục."
        ),
    },
    {
        "sheet": "Thống kê trẻ em từ 0 đến 5 tuổi",
        "group": "Huy động",
        "indicator": "Số trẻ phải huy động",
        "source_type": "DERIVED",
        "candidates": ["date_of_birth"],
        "ui": "Không nhập",
        "condition": "Theo quy tắc nghiệp vụ đã chốt",
        "proposal": (
            "Số phải huy động = Tổng số trẻ trong độ tuổi; "
            "không tạo trường nhập tay."
        ),
    },
    {
        "sheet": "Thống kê trẻ em từ 0 đến 5 tuổi",
        "group": "Huy động",
        "indicator": "Số trẻ đến trường, nhóm, lớp",
        "source_type": "YEAR",
        "candidates": [
            "learning_status",
            "school_id",
            "class_id",
            "school_name_reported",
        ],
        "ui": "Thông tin năm học > Tình trạng học tập/Trường/Lớp",
        "condition": "Mọi trẻ",
        "proposal": "Tự xác định đang đi học từ hồ sơ năm học.",
    },
    {
        "sheet": "Thống kê trẻ em từ 0 đến 5 tuổi",
        "group": "Trái tuyến",
        "indicator": "Trẻ ở tỉnh học tại địa bàn tỉnh",
        "source_type": "DERIVED",
        "candidates": [
            "commune_id",
            "school_id",
            "school_commune_id",
            "province_id",
        ],
        "ui": "Thông tin năm học > Nơi cư trú + nơi học",
        "condition": "Trẻ đang đi học",
        "proposal": (
            "Tự đối chiếu địa bàn cư trú và địa bàn trường; "
            "không nhập tay."
        ),
    },
    {
        "sheet": "Thống kê trẻ em từ 0 đến 5 tuổi",
        "group": "Trái tuyến",
        "indicator": "Trẻ ở tỉnh học trái tuyến tại địa bàn khác",
        "source_type": "DERIVED",
        "candidates": [
            "commune_id",
            "school_id",
            "school_commune_id",
            "school_commune_name_reported",
            "school_province_name_reported",
        ],
        "ui": "Thông tin năm học > Trường hiện tại",
        "condition": "Trẻ đang đi học ngoài địa bàn cư trú",
        "proposal": (
            "Nếu trường ngoài hệ thống phải thu thập thêm "
            "xã/phường và tỉnh của trường theo phiếu."
        ),
    },
    {
        "sheet": "Thống kê trẻ em từ 0 đến 5 tuổi",
        "group": "Huy động",
        "indicator": "Tỉ lệ huy động",
        "source_type": "DERIVED",
        "candidates": [],
        "ui": "Không nhập",
        "condition": "Có tử số và mẫu số",
        "proposal": "Tự tính Đến trường / Phải huy động x 100%.",
    },
    {
        "sheet": "Thống kê trẻ em từ 0 đến 5 tuổi",
        "group": "Đang đi học",
        "indicator": "Trong số trẻ đến trường: trẻ em gái",
        "source_type": "DERIVED",
        "candidates": [
            "gender",
            "learning_status",
        ],
        "ui": "Không nhập thêm",
        "condition": "Trẻ đang đi học",
        "proposal": "Tự tổng hợp từ giới tính + tình trạng học tập.",
    },
    {
        "sheet": "Thống kê trẻ em từ 0 đến 5 tuổi",
        "group": "Đang đi học",
        "indicator": "Trong số trẻ đến trường: trẻ DTTS",
        "source_type": "DERIVED",
        "candidates": [
            "ethnic_group",
            "learning_status",
        ],
        "ui": "Không nhập thêm",
        "condition": "Trẻ đang đi học",
        "proposal": "Tự tổng hợp.",
    },
    {
        "sheet": "Thống kê trẻ em từ 0 đến 5 tuổi",
        "group": "Đang đi học",
        "indicator": "Trẻ DTTS được chuẩn bị tiếng Việt",
        "source_type": "YEAR",
        "candidates": ["prepared_vietnamese"],
        "ui": "Thông tin năm học > Chỉ báo Mầm non",
        "condition": "Chỉ hiện nếu trẻ DTTS và thuộc nhóm cần theo dõi",
        "proposal": (
            "Giữ Có/Không/Chưa xác định; "
            "đưa vào nhóm chỉ báo phục vụ báo cáo."
        ),
    },
    {
        "sheet": "Thống kê trẻ em từ 0 đến 5 tuổi",
        "group": "Trái tuyến",
        "indicator": "Trẻ từ nơi khác đến học (trái tuyến)",
        "source_type": "DERIVED",
        "candidates": [
            "commune_id",
            "school_id",
            "school_commune_id",
            "school_province_name_reported",
        ],
        "ui": "Thông tin năm học > Nơi cư trú + nơi học",
        "condition": "Trẻ cư trú ngoài địa bàn nhưng học tại địa bàn",
        "proposal": "Tự xác định từ cư trú và địa bàn trường.",
    },
    {
        "sheet": "Thống kê trẻ em từ 0 đến 5 tuổi",
        "group": "Chương trình",
        "indicator": "Số trẻ học 2 buổi/ngày",
        "source_type": "YEAR",
        "candidates": ["attends_two_sessions_per_day"],
        "ui": "Thông tin năm học > Chỉ báo Mầm non",
        "condition": "Trẻ Mầm non đang đi học",
        "proposal": (
            "Giữ Có/Không/Chưa xác định. "
            "Chưa nhập phải để trống trong báo cáo, không coi là Không."
        ),
    },
    {
        "sheet": "Thống kê trẻ em từ 0 đến 5 tuổi",
        "group": "Chương trình",
        "indicator": "Tỉ lệ trẻ học 2 buổi/ngày",
        "source_type": "DERIVED",
        "candidates": [],
        "ui": "Không nhập",
        "condition": "Dữ liệu 2 buổi/ngày đã xác định đầy đủ",
        "proposal": "Tự tính Học 2 buổi / Đến trường x 100%.",
    },
    {
        "sheet": "Thống kê trẻ em từ 0 đến 5 tuổi",
        "group": "Biến động",
        "indicator": "Số trẻ bị chết",
        "source_type": "EVENT",
        "candidates": [
            "deceased_during_year",
            "death_date",
            "person_event",
            "event_type",
        ],
        "ui": "Đối tượng > Biến động",
        "condition": "Khi phát sinh",
        "proposal": (
            "Nên dùng sự kiện TỬ VONG có ngày xảy ra; "
            "không chỉ dùng ghi chú tự do."
        ),
    },
    {
        "sheet": "Thống kê trẻ em từ 0 đến 5 tuổi",
        "group": "Biến động",
        "indicator": "Số trẻ chuyển đi",
        "source_type": "EVENT",
        "candidates": [
            "moved_out",
            "move_out_date",
            "person_event",
            "event_type",
            "destination",
        ],
        "ui": "Đối tượng > Biến động",
        "condition": "Khi phát sinh",
        "proposal": "Sự kiện CHUYỂN ĐI: ngày, nơi đến, ghi chú.",
    },
    {
        "sheet": "Thống kê trẻ em từ 0 đến 5 tuổi",
        "group": "Biến động",
        "indicator": "Số trẻ chuyển đến",
        "source_type": "EVENT",
        "candidates": [
            "moved_in",
            "move_in_date",
            "person_event",
            "event_type",
            "origin",
        ],
        "ui": "Đối tượng > Biến động",
        "condition": "Khi phát sinh",
        "proposal": "Sự kiện CHUYỂN ĐẾN: ngày, nơi đi, ghi chú.",
    },
    {
        "sheet": "Thống kê trẻ em từ 0 đến 5 tuổi",
        "group": "Hoàn thành CT GDMN",
        "indicator": "Số trẻ làm căn cứ tính tỷ lệ hoàn thành CT GDMN",
        "source_type": "DERIVED",
        "candidates": [
            "completed_preschool_by_age",
            "school_year_id",
            "event_type",
        ],
        "ui": "Không nhập trực tiếp",
        "condition": "Lấy dữ liệu năm học vừa kết thúc và điều chỉnh biến động",
        "proposal": (
            "Tự chuyển tuổi +1 theo ghi chú của mẫu; "
            "trừ chết/chuyển đi, cộng chuyển đến."
        ),
    },
    {
        "sheet": "Thống kê trẻ em từ 0 đến 5 tuổi",
        "group": "Hoàn thành CT GDMN",
        "indicator": "Số trẻ hoàn thành CT GDMN theo độ tuổi",
        "source_type": "YEAR",
        "candidates": [
            "completed_preschool_by_age",
            "completed_preschool_5",
        ],
        "ui": "Thông tin năm học > Chỉ báo Mầm non",
        "condition": "Trẻ mẫu giáo 3, 4, 5 tuổi",
        "proposal": (
            "Dùng một chỉ báo Có/Không/Chưa xác định "
            "Hoàn thành CT GDMN theo độ tuổi."
        ),
    },
    {
        "sheet": "Thống kê trẻ em từ 0 đến 5 tuổi",
        "group": "Hoàn thành CT GDMN",
        "indicator": "Tỉ lệ hoàn thành CT GDMN",
        "source_type": "DERIVED",
        "candidates": [],
        "ui": "Không nhập",
        "condition": "Có số làm căn cứ",
        "proposal": "Tự tính Hoàn thành / Làm căn cứ x 100%.",
    },

    # ================================================================
    # SHEET 2 - MN-01-TC, ĐK
    # ================================================================
    {
        "sheet": "TK dat chuan",
        "group": "Địa bàn",
        "indicator": "Vùng KTXH đặc biệt khó khăn",
        "source_type": "COMMUNE",
        "candidates": [
            "is_difficult_area",
            "socioeconomic_area",
            "area_classification",
        ],
        "ui": "Danh mục xã/phường",
        "condition": "Theo xã/phường",
        "proposal": "Bổ sung phân loại vùng nếu danh mục hiện chưa có.",
    },
    {
        "sheet": "TK dat chuan",
        "group": "Mạng lưới",
        "indicator": "Số trường Mầm non",
        "source_type": "DERIVED",
        "candidates": [
            "schools",
            "school_level",
        ],
        "ui": "Danh mục trường",
        "condition": "Theo địa bàn",
        "proposal": "Tự đếm trường Mầm non đang hoạt động.",
    },
    {
        "sheet": "TK dat chuan",
        "group": "Mạng lưới",
        "indicator": "Số cơ sở GDMN độc lập",
        "source_type": "FACILITY",
        "candidates": [
            "independent_facility",
            "facility_type",
            "co_so_gdmn_doc_lap",
        ],
        "ui": "Danh mục cơ sở GDMN",
        "condition": "Theo địa bàn",
        "proposal": (
            "Nếu hiện chỉ có bảng schools, cần danh mục "
            "cơ sở GDMN độc lập riêng hoặc loại cơ sở chuẩn hóa."
        ),
    },
    {
        "sheet": "TK dat chuan",
        "group": "Mạng lưới",
        "indicator": "Số điểm trường",
        "source_type": "FACILITY",
        "candidates": [
            "school_site",
            "satellite_site",
            "campus",
            "school_point",
        ],
        "ui": "CSVC/Danh mục điểm trường",
        "condition": "Theo trường/cơ sở",
        "proposal": "Cần danh mục điểm trường chính/lẻ.",
    },
    {
        "sheet": "TK dat chuan",
        "group": "Lớp mẫu giáo",
        "indicator": "Số lớp mẫu giáo 3,4 tuổi và 5 tuổi; lớp đơn/lớp ghép",
        "source_type": "CLASS",
        "candidates": [
            "class_config",
            "class_id",
            "age_group",
            "is_multigrade",
            "class_type",
        ],
        "ui": "Cấu hình lớp Mầm non",
        "condition": "Theo trường/cơ sở và năm học",
        "proposal": (
            "Mỗi lớp cần nhóm tuổi và loại LỚP ĐƠN/LỚP GHÉP; "
            "không nhập số tổng bằng tay."
        ),
    },
    {
        "sheet": "TK dat chuan",
        "group": "Huy động",
        "indicator": "Số trẻ cần huy động / đến lớp / tỷ lệ",
        "source_type": "DERIVED",
        "candidates": [],
        "ui": "Không nhập",
        "condition": "Theo nhóm tuổi 3,4 và 5",
        "proposal": "Dùng trực tiếp nguồn MN-01-TE.",
    },
    {
        "sheet": "TK dat chuan",
        "group": "Hoàn thành",
        "indicator": "Số trẻ hoàn thành CTGDMN / tỷ lệ",
        "source_type": "DERIVED",
        "candidates": [],
        "ui": "Không nhập",
        "condition": "Theo nhóm tuổi",
        "proposal": "Dùng trực tiếp nguồn MN-01-TE.",
    },
    {
        "sheet": "TK dat chuan",
        "group": "Khuyết tật",
        "indicator": "Trẻ MG khuyết tật: tổng số / có khả năng HT / tiếp cận GD / tỷ lệ",
        "source_type": "DERIVED",
        "candidates": [
            "disability_status",
            "disability_can_learn",
            "disability_access_education",
        ],
        "ui": "Không nhập thêm",
        "condition": "Theo nhóm tuổi",
        "proposal": "Dùng nguồn khuyết tật của hồ sơ năm học.",
    },
    {
        "sheet": "TK dat chuan",
        "group": "Điều kiện bảo đảm",
        "indicator": "Tỷ lệ GV/lớp; tỷ lệ phòng học/lớp; lớp đủ TBDH",
        "source_type": "DERIVED",
        "candidates": [
            "staff",
            "class_config",
            "classroom",
            "equipment",
        ],
        "ui": "Không nhập tỷ lệ",
        "condition": "Theo địa bàn",
        "proposal": "Tự lấy từ sheet GV + CSVC.",
    },
    {
        "sheet": "TK dat chuan",
        "group": "Kết luận",
        "indicator": "Đạt chuẩn / Không đạt",
        "source_type": "DERIVED",
        "candidates": [],
        "ui": "Không nhập",
        "condition": "Đủ tiêu chí pháp lý",
        "proposal": (
            "Tính từ toàn bộ chỉ tiêu; "
            "không cho người dùng gõ kết quả đạt chuẩn."
        ),
    },

    # ================================================================
    # SHEET 3 - MN-01-GV
    # ================================================================
    {
        "sheet": "GV",
        "group": "Toàn trường",
        "indicator": "Tổng CBQL, giáo viên, nhân viên",
        "source_type": "STAFF",
        "candidates": [
            "staff",
            "position_group",
            "position",
            "staff_type",
        ],
        "ui": "Đội ngũ",
        "condition": "Nhân sự đang hoạt động",
        "proposal": "Dùng hồ sơ nhân sự, không nhập số tổng.",
    },
    {
        "sheet": "GV",
        "group": "Toàn trường",
        "indicator": "Hợp đồng làm việc",
        "source_type": "STAFF",
        "candidates": [
            "employment_type",
            "employment_form",
            "contract_type",
        ],
        "ui": "Đội ngũ > Hồ sơ nhân sự",
        "condition": "Mỗi nhân sự",
        "proposal": "Chuẩn hóa hình thức tuyển dụng/hợp đồng.",
    },
    {
        "sheet": "GV",
        "group": "Toàn trường",
        "indicator": "CBQL / Giáo viên / Nhân viên",
        "source_type": "STAFF",
        "candidates": [
            "position_group",
            "position",
        ],
        "ui": "Đội ngũ",
        "condition": "Mỗi nhân sự",
        "proposal": "Chuẩn hóa nhóm vị trí.",
    },
    {
        "sheet": "GV",
        "group": "Lớp mẫu giáo",
        "indicator": "Số lớp 3,4 tuổi / 5 tuổi",
        "source_type": "CLASS",
        "candidates": [
            "class_config",
            "age_group",
            "teaching_age",
        ],
        "ui": "Cấu hình lớp",
        "condition": "Theo năm học",
        "proposal": "Lấy từ cấu hình lớp, không nhập lại ở báo cáo GV.",
    },
    {
        "sheet": "GV",
        "group": "Giáo viên lớp mẫu giáo",
        "indicator": "Tổng GV / Hợp đồng làm việc",
        "source_type": "STAFF",
        "candidates": [
            "teaching_level",
            "teaching_age",
            "employment_type",
        ],
        "ui": "Đội ngũ > Phân công dạy",
        "condition": "GV đang dạy lớp mẫu giáo",
        "proposal": "Phải gán GV với cấp/nhóm tuổi hoặc lớp.",
    },
    {
        "sheet": "GV",
        "group": "Giáo viên lớp mẫu giáo",
        "indicator": "Được hưởng chế độ, chính sách theo quy định",
        "source_type": "STAFF",
        "candidates": [
            "receives_policy_benefits",
            "benefit_status",
            "policy_benefit",
        ],
        "ui": "Đội ngũ > Hồ sơ/chính sách",
        "condition": "GV lớp mẫu giáo",
        "proposal": "Bổ sung Có/Không/Chưa xác định nếu chưa có.",
    },
    {
        "sheet": "GV",
        "group": "Giáo viên lớp mẫu giáo",
        "indicator": "Tỉ lệ GV/lớp",
        "source_type": "DERIVED",
        "candidates": [],
        "ui": "Không nhập",
        "condition": "Có GV và số lớp",
        "proposal": "Tự tính.",
    },
    {
        "sheet": "GV",
        "group": "Trình độ",
        "indicator": "Đạt chuẩn / Trên chuẩn / Tỉ lệ đạt chuẩn trở lên",
        "source_type": "STAFF",
        "candidates": [
            "qualification_level",
            "qualification",
            "training_level",
        ],
        "ui": "Đội ngũ > Trình độ",
        "condition": "GV lớp mẫu giáo",
        "proposal": "Dùng trình độ đào tạo chuẩn hóa.",
    },
    {
        "sheet": "GV",
        "group": "Chuẩn nghề nghiệp",
        "indicator": "Số GV đạt chuẩn nghề nghiệp / Tỷ lệ",
        "source_type": "STAFF",
        "candidates": [
            "professional_standard_status",
            "professional_standard",
            "teacher_standard",
        ],
        "ui": "Đội ngũ > Đánh giá chuẩn nghề nghiệp",
        "condition": "GV thuộc diện đánh giá",
        "proposal": (
            "Bổ sung trạng thái chuẩn nghề nghiệp theo năm học "
            "nếu hiện chưa có."
        ),
    },

    # ================================================================
    # SHEET 4 - MN-01-CSVC
    # ================================================================
    {
        "sheet": "CSVC",
        "group": "Mạng lưới",
        "indicator": "Số trường/cơ sở; số điểm trường lẻ",
        "source_type": "FACILITY",
        "candidates": [
            "school",
            "facility_type",
            "school_site",
            "satellite_site",
        ],
        "ui": "Danh mục trường/cơ sở/điểm trường",
        "condition": "Theo địa bàn",
        "proposal": "Dùng danh mục cấu trúc, không nhập số tổng.",
    },
    {
        "sheet": "CSVC",
        "group": "Nhóm/lớp",
        "indicator": "Tổng số nhóm/lớp; Nhà trẻ; Mẫu giáo; 3,4 tuổi; 5 tuổi",
        "source_type": "CLASS",
        "candidates": [
            "class_config",
            "class_type",
            "age_group",
        ],
        "ui": "Cấu hình lớp",
        "condition": "Theo năm học",
        "proposal": "Chuẩn hóa loại nhóm/lớp và nhóm tuổi.",
    },
    {
        "sheet": "CSVC",
        "group": "Phòng học",
        "indicator": "Tổng phòng toàn trường; phòng Nhà trẻ; phòng lớp mẫu giáo",
        "source_type": "FACILITY",
        "candidates": [
            "classroom",
            "room_type",
            "room_count",
        ],
        "ui": "CSVC > Phòng học",
        "condition": "Theo trường/cơ sở",
        "proposal": "Nhập theo loại phòng, hệ thống tự cộng.",
    },
    {
        "sheet": "CSVC",
        "group": "Phòng học",
        "indicator": "Tỷ lệ phòng học/lớp",
        "source_type": "DERIVED",
        "candidates": [],
        "ui": "Không nhập",
        "condition": "Có phòng và lớp",
        "proposal": "Tự tính.",
    },
    {
        "sheet": "CSVC",
        "group": "Phòng học",
        "indicator": "Kiên cố / Bán kiên cố / Tạm, nhờ",
        "source_type": "FACILITY",
        "candidates": [
            "room_quality",
            "construction_type",
            "permanent_room",
        ],
        "ui": "CSVC > Phòng học",
        "condition": "Phòng lớp mẫu giáo",
        "proposal": "Chuẩn hóa loại chất lượng phòng.",
    },
    {
        "sheet": "CSVC",
        "group": "TBDH",
        "indicator": "Lớp đủ thiết bị dạy học, đồ dùng, đồ chơi",
        "source_type": "FACILITY",
        "candidates": [
            "equipment_adequate",
            "has_required_equipment",
            "teaching_equipment",
        ],
        "ui": "CSVC/TBDH > Theo lớp",
        "condition": "Lớp mẫu giáo",
        "proposal": "Có/Không theo lớp; báo cáo tự đếm lớp đạt.",
    },
    {
        "sheet": "CSVC",
        "group": "Vệ sinh",
        "indicator": "Phòng/khu vệ sinh: số lượng / đạt chuẩn",
        "source_type": "FACILITY",
        "candidates": [
            "toilet_count",
            "toilet_standard",
            "sanitation",
        ],
        "ui": "CSVC > Vệ sinh",
        "condition": "Theo cơ sở",
        "proposal": "Nhập số lượng + số/đánh dấu đạt chuẩn.",
    },
    {
        "sheet": "CSVC",
        "group": "Nước sạch",
        "indicator": "Công trình nước sạch: số lượng / đạt chuẩn",
        "source_type": "FACILITY",
        "candidates": [
            "clean_water_count",
            "clean_water_standard",
            "water_system",
        ],
        "ui": "CSVC > Nước sạch",
        "condition": "Theo cơ sở",
        "proposal": "Nhập cấu trúc riêng.",
    },
    {
        "sheet": "CSVC",
        "group": "Bếp ăn",
        "indicator": "Bếp ăn: số lượng / đạt chuẩn",
        "source_type": "FACILITY",
        "candidates": [
            "kitchen_count",
            "kitchen_standard",
            "kitchen",
        ],
        "ui": "CSVC > Bếp ăn",
        "condition": "Theo cơ sở",
        "proposal": "Nhập cấu trúc riêng.",
    },
    {
        "sheet": "CSVC",
        "group": "Sân chơi",
        "indicator": "Sân chơi / trong đó sân có đồ chơi",
        "source_type": "FACILITY",
        "candidates": [
            "playground_count",
            "playground_with_toys",
            "playground",
        ],
        "ui": "CSVC > Sân chơi",
        "condition": "Theo cơ sở",
        "proposal": "Nhập số sân và số sân có đồ chơi.",
    },

    # ================================================================
    # SHEET 5 - TÀI CHÍNH
    # ================================================================
    {
        "sheet": "Báo cáo tài chính",
        "group": "Mô hình dữ liệu",
        "indicator": "Toàn bộ các khoản thu/chi theo từng năm trong biểu",
        "source_type": "FINANCE",
        "candidates": [
            "finance",
            "financial",
            "finance_item_code",
            "amount",
            "fiscal_year",
        ],
        "ui": "Báo cáo Mầm non > Nhập số liệu tài chính",
        "condition": "Theo đơn vị + năm + mã chỉ tiêu",
        "proposal": (
            "Không tạo hàng chục cột trong một bảng. "
            "Nên dùng bảng chi tiết: unit_id, school_year/fiscal_year, "
            "item_code, amount, note. Danh mục item_code bám đúng từng dòng biểu."
        ),
    },
    {
        "sheet": "Báo cáo tài chính",
        "group": "Tổng chi",
        "indicator": (
            "Tổng chi GDMN; NSTX; đầu tư; chương trình/dự án; "
            "xã hội hóa"
        ),
        "source_type": "FINANCE",
        "candidates": [
            "finance_item_code",
            "amount",
        ],
        "ui": "Nhập số liệu tài chính",
        "condition": "Theo năm",
        "proposal": "Các mã chỉ tiêu cố định, nhập số tiền.",
    },
    {
        "sheet": "Báo cáo tài chính",
        "group": "Chi chuyên môn/đầu tư",
        "indicator": (
            "Tỷ lệ chi CM trong NSTX; định mức 3-5 tuổi; "
            "xây dựng phòng; mua sắm TBDH/nội thất"
        ),
        "source_type": "FINANCE",
        "candidates": [
            "finance_item_code",
            "amount",
        ],
        "ui": "Nhập số liệu tài chính",
        "condition": "Theo năm",
        "proposal": "Tỷ lệ nếu có thể thì tính từ tử số/mẫu số; còn lại nhập số.",
    },
    {
        "sheet": "Báo cáo tài chính",
        "group": "Chính sách trẻ em",
        "indicator": (
            "Hỗ trợ học tập; miễn học phí; ăn trưa; "
            "chính sách khác"
        ),
        "source_type": "FINANCE",
        "candidates": [
            "finance_item_code",
            "amount",
        ],
        "ui": "Nhập số liệu tài chính",
        "condition": "Theo năm",
        "proposal": "Danh mục mã chỉ tiêu tài chính.",
    },
    {
        "sheet": "Báo cáo tài chính",
        "group": "Chính sách giáo viên",
        "indicator": (
            "Tuyển dụng; thực hiện phổ cập; lớp ghép/TCTV; "
            "con công nhân; chính sách địa phương"
        ),
        "source_type": "FINANCE",
        "candidates": [
            "finance_item_code",
            "amount",
        ],
        "ui": "Nhập số liệu tài chính",
        "condition": "Theo năm",
        "proposal": "Danh mục mã chỉ tiêu tài chính.",
    },

    # ================================================================
    # SHEET 6 - MN-05-KT
    # ================================================================
    {
        "sheet": "Báo cáo thống kê ĐTKT",
        "group": "Đối tượng",
        "indicator": "Năm sinh / độ tuổi / tổng người khuyết tật 0-5",
        "source_type": "DERIVED",
        "candidates": [
            "date_of_birth",
            "disability_status",
        ],
        "ui": "Thông tin đối tượng + năm học",
        "condition": "Trẻ 0-5 có khuyết tật",
        "proposal": "Tự tổng hợp theo tuổi.",
    },
    {
        "sheet": "Báo cáo thống kê ĐTKT",
        "group": "Dạng tật",
        "indicator": (
            "Vận động; Nghe,nói; Nhìn; Thần kinh,tâm thần; "
            "Trí tuệ; Rối loạn phổ tự kỷ; Học tập; Khác"
        ),
        "source_type": "YEAR",
        "candidates": [
            "disability_type",
            "disability_types",
        ],
        "ui": "Thông tin năm học > Theo dõi trẻ khuyết tật",
        "condition": "Có khuyết tật",
        "proposal": (
            "Chuẩn hóa dạng tật theo đúng 8 nhóm của biểu. "
            "Nếu một trẻ có thể có nhiều dạng tật, nên dùng multi-select/bảng liên kết."
        ),
    },
    {
        "sheet": "Báo cáo thống kê ĐTKT",
        "group": "Tiếp cận giáo dục",
        "indicator": "Số trẻ khuyết tật tiếp cận giáo dục / Tỉ lệ",
        "source_type": "YEAR",
        "candidates": [
            "disability_access_education",
            "access_education",
        ],
        "ui": "Thông tin năm học > Theo dõi trẻ khuyết tật",
        "condition": "Có khuyết tật",
        "proposal": "Dùng cùng trường nguồn với MN-01-TE.",
    },

    # ================================================================
    # SHEET 7 - SỔ PC
    # ================================================================
    {
        "sheet": "Sổ theo dõi phổ cập MN",
        "group": "Định danh",
        "indicator": "Số phiếu / Họ tên / Ngày sinh / Nữ / Chỗ ở / Dân tộc",
        "source_type": "PERSON",
        "candidates": [
            "survey_form",
            "full_name",
            "date_of_birth",
            "gender",
            "ethnic_group",
            "address",
            "hamlet",
        ],
        "ui": "Hộ dân + Đối tượng",
        "condition": "Mọi đối tượng Mầm non",
        "proposal": "Dùng dữ liệu lõi, không nhập lại.",
    },
    {
        "sheet": "Sổ theo dõi phổ cập MN",
        "group": "Gia đình",
        "indicator": "Họ và tên cha hoặc mẹ hoặc người đỡ đầu",
        "source_type": "PERSON",
        "candidates": [
            "guardian_name",
            "father_name",
            "mother_name",
            "relationship_to_head",
        ],
        "ui": "Thông tin đối tượng/hộ",
        "condition": "Trẻ Mầm non",
        "proposal": (
            "Ưu tiên suy ra từ thành viên hộ có quan hệ cha/mẹ; "
            "nếu không có thì cần trường Người đỡ đầu."
        ),
    },
    {
        "sheet": "Sổ theo dõi phổ cập MN",
        "group": "Liên năm",
        "indicator": "Chương trình học / Lớp theo từng năm học",
        "source_type": "YEAR",
        "candidates": [
            "school_year_id",
            "learning_status",
            "school_id",
            "class_id",
            "class_name_reported",
            "program",
        ],
        "ui": "Thông tin năm học",
        "condition": "Mỗi năm học",
        "proposal": (
            "Dùng hồ sơ năm học liên năm; "
            "không lưu 6 cột năm trong một bản ghi người."
        ),
    },
    {
        "sheet": "Sổ theo dõi phổ cập MN",
        "group": "Cơ sở GDMN",
        "indicator": "Tên cơ sở GDMN",
        "source_type": "YEAR",
        "candidates": [
            "school_id",
            "school_name_reported",
        ],
        "ui": "Thông tin năm học > Trường hiện tại",
        "condition": "Trẻ đang học",
        "proposal": "Dùng trường danh mục hoặc tên trường theo phiếu.",
    },
    {
        "sheet": "Sổ theo dõi phổ cập MN",
        "group": "Ghi chú",
        "indicator": (
            "Loại khuyết tật; tạm trú; địa điểm/thời gian "
            "chuyển đến, chuyển đi, chết"
        ),
        "source_type": "EVENT",
        "candidates": [
            "disability_type",
            "residency_status",
            "person_event",
            "event_type",
            "event_date",
            "origin",
            "destination",
            "death_date",
        ],
        "ui": "Đối tượng > Cư trú/Biến động + Theo dõi khuyết tật",
        "condition": "Khi phát sinh",
        "proposal": (
            "Không phụ thuộc ghi chú tự do. "
            "Dùng dữ liệu cấu trúc rồi tự ghép nội dung cột Ghi chú."
        ),
    },
]


# Các chỉ báo hiện có đã nhìn thấy ở giao diện trước khảo sát.
# Bài khảo sát sẽ tìm token thật trong source/DB để xác nhận.
CURRENT_MN_INDICATOR_TOKENS = [
    "completed_preschool_by_age",
    "completed_preschool_5",
    "attends_required_days",
    "attends_regularly",
    "prepared_vietnamese",
    "weight_monitored",
    "underweight",
    "height_monitored",
    "stunted",
    "attends_two_sessions_per_day",
]


REPORT_DRIVEN_MN_INDICATORS = [
    "completed_preschool_by_age",
    "prepared_vietnamese",
    "attends_two_sessions_per_day",
    "disability_can_learn",
    "disability_access_education",
]


HEALTH_INDICATORS = [
    "weight_monitored",
    "underweight",
    "height_monitored",
    "stunted",
]


def norm(value: object) -> str:
    return re.sub(
        r"[^A-Z0-9]+",
        "",
        str(value or "").upper(),
    )


def find_workbook() -> Path | None:
    candidates: list[Path] = []

    exact_names = [
        "Bieu pho cap GDMN.xlsx",
        "Biểu phổ cập GDMN.xlsx",
    ]

    roots = [
        PROJECT,
        PROJECT / "data",
        PROJECT / "templates",
        PROJECT / "app" / "templates",
        Path.home() / "Downloads",
        Path.home() / "Desktop",
    ]

    for root in roots:
        if not root.exists():
            continue

        for name in exact_names:
            path = root / name

            if path.exists():
                candidates.append(
                    path
                )

    # Tìm mềm trong các thư mục nhỏ, không quét toàn ổ C:.
    patterns = [
        "*pho*cap*GDMN*.xlsx",
        "*phổ*cập*GDMN*.xlsx",
        "*GDMN*.xlsx",
    ]

    for root in roots:
        if not root.exists():
            continue

        try:
            for pattern in patterns:
                for path in root.glob(
                    pattern
                ):
                    if (
                        path.is_file()
                        and path not in candidates
                    ):
                        candidates.append(
                            path
                        )
        except Exception:
            pass

    if not candidates:
        return None

    candidates.sort(
        key=lambda p: (
            p.stat().st_mtime,
            p.stat().st_size,
        ),
        reverse=True,
    )

    return candidates[0]


def xlsx_sheet_names(
    path: Path,
) -> list[str]:
    ns = {
        "m": (
            "http://schemas.openxmlformats.org/"
            "spreadsheetml/2006/main"
        )
    }

    with zipfile.ZipFile(
        path,
        "r",
    ) as archive:
        xml = archive.read(
            "xl/workbook.xml"
        )

    root = ET.fromstring(
        xml
    )

    result = []

    for sheet in root.findall(
        ".//m:sheets/m:sheet",
        ns,
    ):
        name = sheet.attrib.get(
            "name"
        )

        if name:
            result.append(
                name
            )

    return result


def read_db_schema():
    if not DB.exists():
        raise RuntimeError(
            f"Không tìm thấy database: {DB}"
        )

    uri = (
        f"file:{DB.as_posix()}?mode=ro"
    )

    conn = sqlite3.connect(
        uri,
        uri=True,
    )

    try:
        integrity = str(
            conn.execute(
                "PRAGMA integrity_check"
            ).fetchone()[0]
        )

        fk_rows = conn.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()

        tables = [
            str(row[0])
            for row in conn.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type='table'
                  AND name NOT LIKE 'sqlite_%'
                ORDER BY name
                """
            ).fetchall()
        ]

        table_columns: dict[
            str,
            list[str],
        ] = {}

        table_counts: dict[
            str,
            int | None,
        ] = {}

        for table in tables:
            cols = [
                str(row[1])
                for row in conn.execute(
                    f'PRAGMA table_info("{table}")'
                ).fetchall()
            ]

            table_columns[
                table
            ] = cols

            try:
                count = int(
                    conn.execute(
                        f'SELECT COUNT(*) '
                        f'FROM "{table}"'
                    ).fetchone()[0]
                )
            except Exception:
                count = None

            table_counts[
                table
            ] = count

        return (
            integrity,
            len(fk_rows),
            table_columns,
            table_counts,
        )

    finally:
        conn.close()


def scan_source():
    source_files = []

    if APP.exists():
        for path in APP.rglob("*"):
            if (
                path.is_file()
                and path.suffix.lower()
                in {
                    ".py",
                    ".html",
                    ".js",
                    ".json",
                }
                and "__pycache__"
                not in path.parts
            ):
                source_files.append(
                    path
                )

    source_text: dict[
        Path,
        str,
    ] = {}

    for path in source_files:
        try:
            source_text[
                path
            ] = path.read_text(
                encoding="utf-8-sig",
                errors="ignore",
            )
        except Exception:
            pass

    return source_text


def build_token_index(
    table_columns,
    source_text,
):
    db_token_tables = defaultdict(
        set
    )

    for table, cols in table_columns.items():
        db_token_tables[
            norm(table)
        ].add(
            table
        )

        for col in cols:
            db_token_tables[
                norm(col)
            ].add(
                table
            )

    source_joined = "\n".join(
        source_text.values()
    ).upper()

    return (
        db_token_tables,
        source_joined,
    )


def candidate_evidence(
    candidates,
    db_token_tables,
    source_joined,
):
    db_hits = []
    source_hits = []

    for candidate in candidates:
        key = norm(
            candidate
        )

        if not key:
            continue

        # DB: exact normalized token hoặc token nằm trong tên bảng/cột.
        matched_tables = set()

        for indexed_key, tables in db_token_tables.items():
            if (
                key == indexed_key
                or key in indexed_key
                or indexed_key in key
            ):
                matched_tables.update(
                    tables
                )

        if matched_tables:
            db_hits.append(
                (
                    candidate,
                    sorted(
                        matched_tables
                    ),
                )
            )

        # Source: tìm nguyên token và các biến thể text đơn giản.
        if (
            candidate.upper()
            in source_joined
        ):
            source_hits.append(
                candidate
            )

    return db_hits, source_hits


def status_for(
    requirement,
    db_hits,
    source_hits,
):
    source_type = requirement[
        "source_type"
    ]

    if source_type == "DERIVED":
        if (
            requirement["candidates"]
            and not db_hits
            and not source_hits
        ):
            return (
                "CẦN NGUỒN ĐẦU VÀO"
            )

        return "TỰ TỔNG HỢP"

    if db_hits and source_hits:
        return "CÓ NGUỒN + CÓ SOURCE"

    if db_hits:
        return "CÓ DB - CẦN KIỂM TRA UI"

    if source_hits:
        return "CÓ SOURCE - CHƯA THẤY DB"

    return "CẦN BỔ SUNG"


def evidence_text(
    db_hits,
    source_hits,
):
    parts = []

    if db_hits:
        db_items = []

        for candidate, tables in db_hits:
            db_items.append(
                f"{candidate}→"
                + "/".join(
                    tables[:4]
                )
            )

        parts.append(
            "DB: "
            + "; ".join(
                db_items
            )
        )

    if source_hits:
        parts.append(
            "Source: "
            + ", ".join(
                source_hits
            )
        )

    return (
        " | ".join(parts)
        if parts
        else "-"
    )


def write_report(
    workbook_path,
    workbook_sheets,
    integrity,
    fk_count,
    table_columns,
    table_counts,
    rows,
    source_text,
):
    EXPORTS.mkdir(
        parents=True,
        exist_ok=True,
    )

    lines: list[str] = []

    def add(value=""):
        lines.append(
            str(value)
        )

    def title(value):
        add()
        add("=" * 126)
        add(value)
        add("=" * 126)

    add("=" * 126)
    add(
        "BÀI 13B-11.14.0 - "
        "KHẢO SÁT TỔNG THỂ 7 SHEET BỘ BIỂU PHỔ CẬP GDMN"
    )
    add("=" * 126)
    add()
    add("CHẾ ĐỘ: CHỈ ĐỌC")
    add(" - Không sửa source.")
    add(" - Không ALTER/INSERT/UPDATE/DELETE database.")
    add(" - Không sửa file Excel mẫu.")
    add(
        " - Mục tiêu: mỗi chỉ tiêu báo cáo phải có nguồn dữ liệu "
        "và có nơi nhập liệu rõ ràng."
    )

    title(
        "1. BỘ BIỂU EXCEL CHUẨN"
    )

    if workbook_path:
        add(
            f"Workbook tìm thấy: {workbook_path}"
        )
        add(
            f"Số sheet: {len(workbook_sheets)}"
        )

        for index, name in enumerate(
            workbook_sheets,
            start=1,
        ):
            check = (
                "ĐÚNG"
                if name
                in EXPECTED_SHEETS
                else "KHÁC DỰ KIẾN"
            )

            add(
                f" {index}. {name} [{check}]"
            )
    else:
        add(
            "Không tìm thấy workbook trong C:\\PhoCap/Downloads."
        )
        add(
            "Khảo sát vẫn tiếp tục bằng cấu trúc 7 sheet "
            "đã chốt trong Bài này."
        )

    missing_sheet_names = [
        name
        for name in EXPECTED_SHEETS
        if name not in workbook_sheets
    ]

    extra_sheet_names = [
        name
        for name in workbook_sheets
        if name not in EXPECTED_SHEETS
    ]

    if workbook_path:
        add(
            "Sheet thiếu so với bộ chuẩn: "
            + (
                ", ".join(
                    missing_sheet_names
                )
                if missing_sheet_names
                else "KHÔNG"
            )
        )
        add(
            "Sheet ngoài bộ chuẩn: "
            + (
                ", ".join(
                    extra_sheet_names
                )
                if extra_sheet_names
                else "KHÔNG"
            )
        )

    title(
        "2. TÌNH TRẠNG DATABASE/SOURCE"
    )

    add(
        f"Database: {DB}"
    )
    add(
        f"PRAGMA integrity_check: {integrity}"
    )
    add(
        f"PRAGMA foreign_key_check: {fk_count} lỗi"
    )
    add(
        f"Số bảng: {len(table_columns)}"
    )
    add(
        f"Số file source/template đã quét: {len(source_text)}"
    )

    important_tables = [
        "survey_people",
        "survey_person_year_records",
        "survey_forms",
        "households",
        "schools",
        "staff",
        "classes",
        "class_configs",
        "school_years",
    ]

    add()
    add("Một số bảng quan trọng:")

    for table in important_tables:
        if table in table_columns:
            add(
                f" - {table}: "
                f"{table_counts.get(table)} bản ghi; "
                f"{len(table_columns[table])} cột"
            )

    title(
        "3. KẾT QUẢ MA TRẬN CHỈ TIÊU → NGUỒN DỮ LIỆU → GIAO DIỆN"
    )

    by_sheet = defaultdict(
        list
    )

    for row in rows:
        by_sheet[
            row["sheet"]
        ].append(
            row
        )

    order = EXPECTED_SHEETS

    for sheet in order:
        title(
            f"SHEET: {sheet}"
        )

        sheet_rows = by_sheet.get(
            sheet,
            [],
        )

        counts = defaultdict(
            int
        )

        for row in sheet_rows:
            counts[
                row["status"]
            ] += 1

        add(
            "Tóm tắt: "
            + "; ".join(
                f"{key}={value}"
                for key, value
                in sorted(
                    counts.items()
                )
            )
        )
        add()

        for index, row in enumerate(
            sheet_rows,
            start=1,
        ):
            add(
                f"{index}. [{row['status']}] "
                f"{row['indicator']}"
            )
            add(
                f"   Nhóm: {row['group']}"
            )
            add(
                f"   Kiểu nguồn: {row['source_type']}"
            )
            add(
                f"   Nơi nhập/nguồn: {row['ui']}"
            )
            add(
                f"   Điều kiện: {row['condition']}"
            )
            add(
                f"   Bằng chứng hiện có: {row['evidence']}"
            )
            add(
                f"   Đề xuất: {row['proposal']}"
            )
            add()

    title(
        "4. ĐỀ XUẤT THAY ĐỔI GIAO DIỆN NHẬP LIỆU MẦM NON"
    )

    add(
        "A. Khối 'Các chỉ báo Mầm non' nên đổi thành "
        "'Chỉ báo phục vụ báo cáo PCGDMN'."
    )
    add(
        "Các trường cốt lõi cần phục vụ trực tiếp 7 sheet:"
    )
    add(
        " 1. Hoàn thành Chương trình GDMN theo độ tuổi "
        "(3,4,5 tuổi) - Có/Không/Chưa xác định."
    )
    add(
        " 2. Học 2 buổi/ngày - Có/Không/Chưa xác định."
    )
    add(
        " 3. Trẻ DTTS được chuẩn bị tiếng Việt - "
        "chỉ hiện khi là DTTS và thuộc đối tượng cần theo dõi."
    )
    add(
        " 4. Khuyết tật có khả năng học tập - "
        "chỉ hiện khi Có khuyết tật."
    )
    add(
        " 5. Khuyết tật được tiếp cận giáo dục - "
        "chỉ hiện khi Có khuyết tật."
    )
    add()

    add(
        "B. Khối 'Theo dõi trẻ khuyết tật' cần chuẩn hóa:"
    )
    add(
        " - Tình trạng khuyết tật."
    )
    add(
        " - Dạng tật theo đúng 8 nhóm MN-05-KT."
    )
    add(
        " - Có khả năng học tập."
    )
    add(
        " - Được tiếp cận giáo dục."
    )
    add(
        " - Mức độ/Giấy xác nhận/Hòa nhập/Hỗ trợ "
        "vẫn giữ nếu hệ thống đang dùng."
    )
    add()

    add(
        "C. Bổ sung khối 'Cư trú và biến động' có cấu trúc:"
    )
    add(
        " - Thường trú/Tạm trú."
    )
    add(
        " - Chuyển đến: ngày + nơi đi."
    )
    add(
        " - Chuyển đi: ngày + nơi đến."
    )
    add(
        " - Tử vong: ngày."
    )
    add(
        "Không dùng ghi chú tự do làm nguồn chính cho báo cáo."
    )
    add()

    add(
        "D. Khi trường học ngoài danh mục hệ thống:"
    )
    add(
        " - Ngoài Tên trường theo phiếu cần thêm "
        "Xã/phường của trường và Tỉnh/TP của trường."
    )
    add(
        " - Mục đích: xác định đúng học trong địa bàn, "
        "trái tuyến và trẻ nơi khác đến học."
    )
    add()

    add(
        "E. Các chỉ báo sức khỏe hiện có như "
        "Theo dõi cân nặng / suy dinh dưỡng nhẹ cân / "
        "theo dõi chiều cao / thấp còi:"
    )
    add(
        " - Không xuất hiện trong 7 sheet bộ biểu mới."
    )
    add(
        " - Đề nghị chuyển sang mục "
        "'Theo dõi sức khỏe (không dùng chốt dữ liệu PCGDMN)'."
    )
    add(
        " - Không tính các trường này vào điều kiện "
        "'đủ dữ liệu báo cáo PCGDMN'."
    )
    add(
        " - Không xóa dữ liệu cũ."
    )
    add()

    title(
        "5. ĐỀ XUẤT CẤU TRÚC DỮ LIỆU MỚI/NÂNG CẤP"
    )

    proposals = [
        (
            "survey_person_year_records",
            "disability_can_learn",
            "BOOLEAN nullable",
            "Nguồn MN-01-TE, MN-01-TC,ĐK",
        ),
        (
            "survey_person_year_records",
            "disability_access_education",
            "BOOLEAN nullable",
            "Nguồn MN-01-TE, MN-01-TC,ĐK, MN-05-KT",
        ),
        (
            "survey_person_year_records hoặc bảng liên kết",
            "disability_types",
            "ENUM/multi-select chuẩn hóa",
            "8 dạng tật của MN-05-KT",
        ),
        (
            "survey_person_year_records",
            "school_commune_name_reported",
            "VARCHAR nullable",
            "Trường ngoài hệ thống",
        ),
        (
            "survey_person_year_records",
            "school_province_name_reported",
            "VARCHAR nullable",
            "Trường ngoài hệ thống",
        ),
        (
            "survey_people/households",
            "residency_status",
            "ENUM: THUONG_TRU/TAM_TRU",
            "Sổ PC + phạm vi thống kê",
        ),
        (
            "person_events (khuyến nghị bảng mới)",
            "event_type,event_date,origin,destination,notes",
            "MOVE_IN/MOVE_OUT/DEATH",
            "MN-01-TE + Sổ PC",
        ),
        (
            "class configuration",
            "age_group,is_multigrade,class_type",
            "Cấu trúc lớp theo năm",
            "MN-01-TC,ĐK + GV + CSVC",
        ),
        (
            "staff/year assignment",
            "receives_policy_benefits",
            "BOOLEAN nullable",
            "MN-01-GV",
        ),
        (
            "staff/year evaluation",
            "professional_standard_status",
            "ENUM theo năm",
            "MN-01-GV",
        ),
        (
            "communes",
            "socioeconomic_area/is_difficult_area",
            "ENUM/BOOLEAN",
            "MN-01-TC,ĐK",
        ),
        (
            "facility/csvc",
            "room/equipment/toilet/water/kitchen/playground structured fields",
            "Dữ liệu theo cơ sở/năm",
            "MN-01-CSVC",
        ),
        (
            "finance_values",
            "unit_id,year,item_code,amount,note",
            "Bảng chi tiết",
            "MN-01-Tài chính",
        ),
    ]

    for index, (
        entity,
        fields,
        dtype,
        purpose,
    ) in enumerate(
        proposals,
        start=1,
    ):
        add(
            f"{index}. {entity}"
        )
        add(
            f"   Trường: {fields}"
        )
        add(
            f"   Kiểu: {dtype}"
        )
        add(
            f"   Phục vụ: {purpose}"
        )

    title(
        "6. KIẾN TRÚC NHẬP LIỆU THEO 7 SHEET"
    )

    add(
        "1) Điều tra hộ dân / Thông tin năm học:"
    )
    add(
        "   MN-01-TE + MN-05-KT + Sổ PC."
    )
    add(
        "2) Danh mục xã/trường/cơ sở/điểm trường/lớp:"
    )
    add(
        "   MN-01-TC,ĐK + MN-01-CSVC."
    )
    add(
        "3) Đội ngũ + phân công lớp + đánh giá theo năm:"
    )
    add(
        "   MN-01-GV."
    )
    add(
        "4) CSVC/TBDH theo cơ sở/năm:"
    )
    add(
        "   MN-01-CSVC."
    )
    add(
        "5) Nhập tài chính theo mã chỉ tiêu/năm:"
    )
    add(
        "   MN-01-Tài chính."
    )
    add(
        "6) Các tỷ lệ/kết luận đạt chuẩn:"
    )
    add(
        "   Chỉ tính tự động, không nhập tay."
    )

    title(
        "7. QUY TẮC HOÀN THÀNH DỮ LIỆU PCGDMN ĐỀ XUẤT"
    )

    add(
        "Không dùng một danh sách cố định 8/9 chỉ báo cho mọi trẻ."
    )
    add(
        "Điều kiện đủ phải động theo đối tượng:"
    )
    add(
        " - Mọi trẻ: dữ liệu định danh/cư trú cần thiết."
    )
    add(
        " - Trẻ đang học: trường/lớp hoặc trường theo phiếu."
    )
    add(
        " - Trẻ MN: Hoàn thành CT GDMN + Học 2 buổi/ngày."
    )
    add(
        " - Trẻ DTTS: Chuẩn bị tiếng Việt khi thuộc nhóm áp dụng."
    )
    add(
        " - Trẻ khuyết tật: dạng tật + khả năng học tập "
        "+ tiếp cận giáo dục."
    )
    add(
        " - Biến động: chỉ yêu cầu ngày/nơi khi người dùng "
        "chọn có biến động."
    )
    add(
        "Các chỉ số cân nặng/chiều cao/dinh dưỡng không còn "
        "là điều kiện hoàn thành báo cáo 7 sheet."
    )

    title(
        "8. BƯỚC TRIỂN KHAI SAU KHẢO SÁT"
    )

    add(
        "Bài 13B-11.14.1: bổ sung schema dữ liệu còn thiếu "
        "(chỉ các trường thực sự chưa có)."
    )
    add(
        "Bài 13B-11.14.2: thay giao diện Thông tin năm học "
        "và Theo dõi khuyết tật theo bộ chỉ báo mới."
    )
    add(
        "Bài 13B-11.14.3: chuẩn hóa Cư trú/Biến động/Trường ngoài hệ thống."
    )
    add(
        "Bài 13B-11.14.4: chuẩn hóa lớp + GV + CSVC + tài chính."
    )
    add(
        "Bài 13B-11.14.5+: xây 7 báo cáo theo đúng 7 sheet "
        "và nút Xuất toàn bộ workbook."
    )
    add(
        "Chỉ ẩn báo cáo cũ sau khi 7 báo cáo mới kiểm thử đạt."
    )

    OUT_TXT.write_text(
        "\n".join(lines)
        + "\n",
        encoding="utf-8",
    )

    csv_fields = [
        "sheet",
        "group",
        "indicator",
        "source_type",
        "status",
        "candidate_fields",
        "evidence",
        "ui",
        "condition",
        "proposal",
    ]

    with OUT_CSV.open(
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=csv_fields,
        )

        writer.writeheader()

        for row in rows:
            writer.writerow(
                {
                    "sheet": row["sheet"],
                    "group": row["group"],
                    "indicator": row["indicator"],
                    "source_type": row["source_type"],
                    "status": row["status"],
                    "candidate_fields": ", ".join(
                        row["candidates"]
                    ),
                    "evidence": row["evidence"],
                    "ui": row["ui"],
                    "condition": row["condition"],
                    "proposal": row["proposal"],
                }
            )

    return lines


def main() -> int:
    print("=" * 126)
    print(
        "BÀI 13B-11.14.0 - "
        "KHẢO SÁT TỔNG THỂ 7 SHEET BỘ BIỂU PHỔ CẬP GDMN"
    )
    print("=" * 126)
    print()
    print("CHẾ ĐỘ: CHỈ ĐỌC")
    print(
        " - Không sửa source/database/file Excel."
    )
    print(
        " - Đối chiếu từng chỉ tiêu với CSDL và giao diện hiện tại."
    )
    print(
        " - Đề xuất thay chỉ báo để tất cả báo cáo có nguồn dữ liệu."
    )
    print()

    try:
        workbook_path = find_workbook()

        workbook_sheets = []

        if workbook_path:
            workbook_sheets = xlsx_sheet_names(
                workbook_path
            )

            print(
                "Workbook:",
                workbook_path,
            )
            print(
                "Sheets:",
                len(workbook_sheets),
            )
        else:
            print(
                "Workbook: CHƯA TÌM THẤY TRÊN MÁY."
            )
            print(
                "Vẫn dùng ma trận 7 sheet đã chốt để khảo sát."
            )

        (
            integrity,
            fk_count,
            table_columns,
            table_counts,
        ) = read_db_schema()

        print(
            "integrity_check:",
            integrity,
        )
        print(
            "foreign_key_check:",
            fk_count,
            "lỗi",
        )
        print(
            "Số bảng:",
            len(table_columns),
        )

        source_text = scan_source()

        print(
            "Số file source/template quét:",
            len(source_text),
        )

        (
            db_token_tables,
            source_joined,
        ) = build_token_index(
            table_columns,
            source_text,
        )

        result_rows = []

        for requirement in REQUIREMENTS:
            db_hits, source_hits = candidate_evidence(
                requirement["candidates"],
                db_token_tables,
                source_joined,
            )

            row = dict(
                requirement
            )

            row["status"] = status_for(
                requirement,
                db_hits,
                source_hits,
            )

            row["evidence"] = evidence_text(
                db_hits,
                source_hits,
            )

            result_rows.append(
                row
            )

        lines = write_report(
            workbook_path,
            workbook_sheets,
            integrity,
            fk_count,
            table_columns,
            table_counts,
            result_rows,
            source_text,
        )

        status_counts = defaultdict(
            int
        )

        for row in result_rows:
            status_counts[
                row["status"]
            ] += 1

        print()
        print("TÓM TẮT MA TRẬN:")

        for status, count in sorted(
            status_counts.items()
        ):
            print(
                f" - {status}: {count}"
            )

        print()
        print("ĐỀ XUẤT QUAN TRỌNG:")
        print(
            " - Đổi 'Các chỉ báo Mầm non' thành "
            "'Chỉ báo phục vụ báo cáo PCGDMN'."
        )
        print(
            " - Bổ sung Khuyết tật có khả năng học tập "
            "+ tiếp cận giáo dục nếu còn thiếu."
        )
        print(
            " - Chuẩn hóa biến động chuyển đến/chuyển đi/tử vong."
        )
        print(
            " - Chuẩn hóa nơi học ngoài hệ thống để xác định trái tuyến."
        )
        print(
            " - Cân nặng/chiều cao/dinh dưỡng chuyển sang "
            "Theo dõi sức khỏe, không dùng chốt dữ liệu 7 sheet."
        )
        print()
        print("=" * 126)
        print(
            "BÀI 13B-11.14.0 HOÀN THÀNH - "
            "KHÔNG THAY ĐỔI DỮ LIỆU"
        )
        print("=" * 126)
        print(
            "Báo cáo chi tiết:"
        )
        print(
            OUT_TXT
        )
        print(
            "Ma trận CSV:"
        )
        print(
            OUT_CSV
        )

        return 0

    except Exception:
        traceback.print_exc()

        EXPORTS.mkdir(
            parents=True,
            exist_ok=True,
        )

        try:
            OUT_TXT.write_text(
                "BÀI 13B-11.14.0 DỪNG DO LỖI\n\n"
                + traceback.format_exc(),
                encoding="utf-8",
            )
        except Exception:
            pass

        print()
        print(
            "KHẢO SÁT DỪNG DO LỖI."
        )
        print(
            "Source/database không bị thay đổi."
        )
        print(
            "Báo cáo lỗi:",
            OUT_TXT,
        )

        return 1


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
