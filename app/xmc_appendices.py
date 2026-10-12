"""Excel templates transcribed from the user-provided Các phụ lục.pdf."""
from pathlib import Path

TEMPLATE_DIR = Path(__file__).resolve().parent / "report_templates" / "phu_luc_2026"
COMPULSORY_FORMS = (
    ("01-TH_TN", "Thống kê trẻ em 6–14 tuổi giáo dục bắt buộc tiểu học", (4, 5)),
    ("02-TH_GV", "Đội ngũ giáo viên tiểu học", (6,)),
    ("03-TH_CSVC", "Cơ sở vật chất tiểu học", (7,)),
    ("04-TH_HT", "Danh sách hoàn thành chương trình tiểu học", (8,)),
    ("05-THCS_TTN", "Thống kê thanh thiếu niên giáo dục bắt buộc THCS", (9, 10)),
    ("06-THCS_GV", "Đội ngũ giáo viên THCS", (11,)),
    ("07-THCS_CSVC", "Cơ sở vật chất THCS", (12,)),
    ("08-THCS_HT", "Danh sách hoàn thành chương trình THCS", (13,)),
)
XMC_FORMS = (
    ("01", "Tổng hợp kết quả xóa mù chữ", (15, 16, 17)),
    ("02", "Danh sách người chưa đạt chuẩn biết chữ", (18,)),
    ("03", "Thống kê hiện trạng chưa đạt chuẩn biết chữ mức độ 1", (19,)),
    ("04", "Thống kê hiện trạng chưa đạt chuẩn biết chữ mức độ 2", (20,)),
    ("05", "Thống kê kết quả học tập và đạt chuẩn biết chữ mức độ 1", (21,)),
    ("06", "Thống kê kết quả học tập và đạt chuẩn biết chữ mức độ 2", (22,)),
    ("07", "Thống kê trình độ văn hóa phục vụ công tác xóa mù chữ", (23, 24, 25, 26)),
    ("08", "Danh sách người tái mù chữ và tình hình hỗ trợ, học tập bổ sung", (27,)),
    ("09", "Thống kê đạt chuẩn xóa mù chữ", (28,)),
)


def template_files():
    files = {
        "tat-ca": "Cac_phu_luc_2026.xlsx",
        "bo-xmc": "Phu_luc_3_Xoa_mu_chu.xlsx",
        "phieu-dieu-tra": "Phu_luc_1_Phieu_dieu_tra.xlsx",
        "giao-duc-bat-buoc": "Phu_luc_2_Giao_duc_bat_buoc.xlsx",
    }
    files.update({code: f"Mau_{code}_XMC.xlsx" for code, _, _ in XMC_FORMS})
    files.update({code: f"Mau_{code}.xlsx" for code, _, _ in COMPULSORY_FORMS})
    return files
