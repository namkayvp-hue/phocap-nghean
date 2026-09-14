from __future__ import annotations

# Mã chỉ tiêu được cố định để dữ liệu lưu bền vững qua các phiên bản giao diện.
# template_row là dòng dữ liệu tương ứng trong mẫu Excel "MN - Tài chính".
FINANCE_ITEMS = [
    {"code": "F01", "stt": "1", "label": "Tổng chi cho Giáo dục mầm non", "unit": "Tr.đg", "template_row": 10, "level": 0},
    {"code": "F01_1", "stt": "", "label": "Trong đó: Ngân sách thường xuyên", "unit": "Tr.đg", "template_row": 11, "level": 1},
    {"code": "F01_2", "stt": "", "label": "Ngân sách đầu tư", "unit": "Tr.đg", "template_row": 12, "level": 1},
    {"code": "F01_3", "stt": "", "label": "Ngân sách từ nguồn Chương trình mục tiêu, dự án", "unit": "Tr.đg", "template_row": 13, "level": 1},
    {"code": "F01_4", "stt": "", "label": "Từ nguồn xã hội hóa", "unit": "Tr.đg", "template_row": 14, "level": 1},
    {"code": "F02", "stt": "2", "label": "Tỷ lệ chi hoạt động chuyên môn GDMN trong NSTX", "unit": "%", "template_row": 15, "level": 0},
    {"code": "F03", "stt": "3", "label": "Định mức chi thường xuyên cho trẻ em từ 3 đến 5 tuổi (bình quân)", "unit": "Tr.đg", "template_row": 16, "level": 0},
    {"code": "F04", "stt": "4", "label": "Chi đầu tư xây dựng phòng học, phòng chức năng", "unit": "Tr.đg", "template_row": 17, "level": 0},
    {"code": "F05", "stt": "5", "label": "Chi mua sắm thiết bị dạy học và thiết bị nội thất dùng chung", "unit": "Tr.đg", "template_row": 18, "level": 0},
    {"code": "F05_A", "stt": "a", "label": "Mua sắm thiết bị dạy học, đồ dùng, thiết bị nội thất dùng chung", "unit": "Tr.đg", "template_row": 20, "level": 1},
    {"code": "F05_B", "stt": "b", "label": "Hỗ trợ giấy, truyện tranh, sáp màu, bút chì, đồ chơi, học liệu và đồ dùng cá nhân cho trẻ 3–5 tuổi bán trú (NĐ 277/2025/NĐ-CP)", "unit": "Tr.đg", "template_row": 21, "level": 1},
    {"code": "F05_C", "stt": "c", "label": "Hỗ trợ tiền điện, nước phục vụ học tập và sinh hoạt trẻ 3–5 tuổi bán trú (NĐ 277/2025/NĐ-CP)", "unit": "Tr.đg", "template_row": 22, "level": 1},
    {"code": "F05_D", "stt": "d", "label": "Hỗ trợ kinh phí trông trưa đối với trẻ 3–5 tuổi (NĐ 277/2025/NĐ-CP)", "unit": "Tr.đg", "template_row": 23, "level": 1},
    {"code": "F05_DD", "stt": "đ", "label": "Hỗ trợ kinh phí chi trả cho nhân viên nấu ăn (NĐ 277/2025/NĐ-CP)", "unit": "Tr.đg", "template_row": 24, "level": 1},
    {"code": "F05_E", "stt": "e", "label": "Hỗ trợ kinh phí chi trả cho nhân viên nấu ăn (NĐ 105/2020/NĐ-CP)", "unit": "Tr.đg", "template_row": 25, "level": 1},
    {"code": "F05_F", "stt": "f", "label": "Mua sắm thiết bị, đồ dùng cho cơ sở GDMN độc lập vùng ĐBKK và trường thuộc Bộ Quốc phòng (NĐ 277/2025/NĐ-CP)", "unit": "Tr.đg", "template_row": 26, "level": 1},
    {"code": "F06", "stt": "6", "label": "Chi thực hiện chính sách cho trẻ em", "unit": "Tr.đg", "template_row": 27, "level": 0},
    {"code": "F06_1", "stt": "", "label": "Hỗ trợ chi phí học tập", "unit": "Tr.đg", "template_row": 28, "level": 1},
    {"code": "F06_2", "stt": "", "label": "Miễn học phí", "unit": "Tr.đg", "template_row": 29, "level": 1},
    {"code": "F06_3", "stt": "", "label": "Hỗ trợ ăn trưa", "unit": "Tr.đg", "template_row": 30, "level": 1},
    {"code": "F06_3A", "stt": "", "label": "Hỗ trợ ăn trưa (NĐ 105/2020/NĐ-CP)", "unit": "Tr.đg", "template_row": 31, "level": 2},
    {"code": "F06_3B", "stt": "", "label": "Hỗ trợ ăn trưa (NĐ 277/2025/NĐ-CP)", "unit": "Tr.đg", "template_row": 32, "level": 2},
    {"code": "F06_4", "stt": "", "label": "Hỗ trợ theo chính sách khác của Trung ương, địa phương", "unit": "Tr.đg", "template_row": 33, "level": 1},
    {"code": "F07", "stt": "7", "label": "Chi thực hiện chính sách cho giáo viên mầm non", "unit": "Tr.đg", "template_row": 34, "level": 0},
    {"code": "F07_1", "stt": "", "label": "Tuyển dụng giáo viên mầm non (01 năm lương cơ sở)", "unit": "Tr.đg", "template_row": 35, "level": 1},
    {"code": "F07_2", "stt": "", "label": "Đối tượng thực hiện phổ cập (960.000 đ/người/tháng)", "unit": "Tr.đg", "template_row": 36, "level": 1},
    {"code": "F07_3", "stt": "", "label": "Giáo viên dạy lớp ghép và tăng cường tiếng Việt (NĐ 105/2020/NĐ-CP)", "unit": "Tr.đg", "template_row": 37, "level": 1},
    {"code": "F07_4", "stt": "", "label": "Giáo viên dạy con công nhân (NĐ 105/2020/NĐ-CP)", "unit": "Tr.đg", "template_row": 38, "level": 1},
    {"code": "F07_5", "stt": "", "label": "Hỗ trợ đội ngũ theo chính sách khác của địa phương", "unit": "Tr.đg", "template_row": 39, "level": 1},
]

FINANCE_ITEM_BY_CODE = {item["code"]: item for item in FINANCE_ITEMS}
