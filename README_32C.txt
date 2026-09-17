BÀI 32C - DRY-RUN NGUỒN HỌC SINH 2025-2026 THEO TÊN TRƯỜNG LỊCH SỬ

Mục tiêu:
- Không sửa source.
- Không ghi database.
- Mở SQLite ở chế độ read-only.
- Tạo file Excel thử hoàn toàn trong bộ nhớ; không nạp dữ liệu thật.
- Gọi đúng parser đang dùng bởi màn hình Nguồn học sinh đối chiếu.
- Với từng lịch sử đổi tên: năm trước hiệu lực phải nhận TÊN CŨ; từ năm hiệu lực phải nhận TÊN MỚI.
- Khóa riêng ca THCS Cắm Muộn -> THCS Mường Quàng.
- Kiểm tra SHA database trước/sau.

Cách chạy:
1) Giải nén thư mục ra Desktop.
2) Mở PowerShell tại thư mục chứa audit_32c.py.
3) Chạy:
   C:\PhoCap\.venv\Scripts\python.exe .\audit_32c.py

Kết quả đạt phải có:
INTEGRITY = ok
FK_COUNT = 0
OLD_NAME_RESULT = PASS
NEW_NAME_RESULT = PASS
TESTS_FAIL = 0
DATABASE_WRITES_THIS_RUN = 0
DB_SHA_UNCHANGED = YES
DRY_RUN_32C_SUCCESS = YES

Nếu SHA source khác nền Bài 32B đã kiểm toán, script sẽ dừng trước khi kiểm thử.
