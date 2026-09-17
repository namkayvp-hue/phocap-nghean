BÀI 33A - TÀI CHÍNH CẤP TRƯỜNG -> XÃ/SỞ TỔNG HỢP
====================================================

MỤC TIÊU
- Trường Mầm non nhập tài chính của chính trường mình.
- Trường không chọn/sửa trường khác.
- Xã xem từng trường hoặc tổng hợp tất cả trường Mầm non thuộc xã.
- Sở/Admin xem từng xã, từng trường hoặc tổng hợp toàn tỉnh.
- Biểu MN-TC đúng mẫu lấy dữ liệu từ trường và tổng hợp theo phạm vi.
- Giữ nguyên bảng finance_report_values cũ và toàn bộ dữ liệu cũ.
- Không sửa các phân hệ Điều tra, Học sinh, Đội ngũ, CSVC, Sáp nhập, Đổi tên trường...

PHẠM VI SOURCE
- Thay đúng 5 file hiện có:
  app/report_input_models.py
  app/routers/report_inputs.py
  app/templates/report_inputs/finance.html
  app/templates/partials/dropdown_menu_v1.html
  app/routers/pcgdmn_template_report.py
- Thêm đúng 1 file:
  app/services/finance_school_service.py

DATABASE
- Chỉ thêm 1 bảng: school_finance_report_values
- Không ALTER/DROP bảng cũ.
- Không chuyển/xóa dữ liệu tài chính cũ.
- Bước cài không ghi số liệu nghiệp vụ vào bảng mới.

CÁCH CÀI
1. Giải nén gói ra Desktop.
2. Mở PowerShell tại đúng thư mục gói.
3. Chạy:
   C:\PhoCap\.venv\Scripts\python.exe .\install_33a.py
4. Phải thấy cuối màn hình:
   PY_COMPILE = OK
   JINJA_PARSE = OK
   INTEGRITY_AFTER = ok
   FK_COUNT_AFTER = 0
   BUSINESS_DATA_WRITE = 0
   INSTALL33A_SUCCESS = YES
5. Chạy kiểm toán:
   C:\PhoCap\.venv\Scripts\python.exe .\audit_33a.py
6. Phải thấy:
   SOURCE_SHA_OK = YES
   MARKERS_OK = YES
   TABLE_SCHEMA_OK = YES
   DB_SHA_UNCHANGED = YES
   AUDIT33A_SUCCESS = YES

KIỂM THỬ GIAO DIỆN
A. Tài khoản Trường Mầm non:
- Báo cáo -> Báo cáo Mầm non -> 5.2.8 Nhập dữ liệu BC-Tài chính.
- Xã và Trường bị cố định đúng tài khoản.
- Nhập thử 1-2 chỉ tiêu của năm tài chính 2026 và Lưu.

B. Tài khoản Xã:
- Mở /bao-cao/tai-chinh/nhap
- Chọn "Tổng hợp các trường trong xã" hoặc chọn từng trường.
- Xã chỉ xem, không có nút lưu.

C. Tài khoản Sở/Admin:
- Có thể chọn xã, trường; nếu không chọn xã thì tổng hợp toàn tỉnh.

D. MN-TC:
- Mở /bao-cao/pcgdmn-mau-2025?sheet_code=mn-tc
- Cấp trường: chỉ số liệu trường đó.
- Cấp xã: tổng hợp các trường Mầm non thuộc xã.
- Cấp tỉnh: tổng hợp toàn tỉnh.

QUY TẮC TỔNG HỢP
- Các khoản tiền: cộng các trường.
- F02 (tỷ lệ): tổng hợp theo trọng số "Ngân sách thường xuyên" F01_1; nếu thiếu trọng số thì lấy bình quân các trường có dữ liệu.
- F03 (định mức bình quân): lấy bình quân các trường có dữ liệu.

AN TOÀN
- Installer khóa SHA đúng nền source người dùng vừa gửi.
- Nếu SHA khác: dừng, không sửa.
- Tự backup source + database vào C:\PhoCap\backups\finance_school_33a_YYYYMMDD_HHMMSS.
- Nếu cài lỗi: tự rollback source và database.
