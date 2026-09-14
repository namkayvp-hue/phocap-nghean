BÀI 32B - TRA TÊN TRƯỜNG THEO NĂM HỌC KHI NẠP NGUỒN HỌC SINH ĐỐI CHIẾU

Mục tiêu:
- Không đổi schema database.
- Không sửa school_id, mã trường, xã/phường, cấp học, trạng thái.
- Không chạy engine sáp nhập.
- Thêm bộ tra tên lịch sử theo school_name_histories.
- Khi nạp nguồn học sinh 2025-2026 để đối chiếu 2026-2027, tên trường trong Excel được khớp theo TÊN CỦA NĂM NGUỒN, không phải tên hiện hành.

File thay đổi:
1) app/services/school_name_history.py (MỚI)
2) app/routers/student_reconciliation_source.py (thay bằng bản 32B đã khóa SHA)

Cài đặt từ PowerShell:
  cd <thư mục đã giải nén gói 32B>
  C:\PhoCap\.venv\Scripts\python.exe .\install_32b.py

Cài đặt chỉ ghi SOURCE, KHÔNG ghi database.
Installer tự backup source cũ vào C:\PhoCap\backups\source_32b_YYYYMMDD_HHMMSS\
Nếu SHA nguồn không đúng bản đã khảo sát, installer DỪNG trước khi ghi.
Nếu compile lỗi, installer tự rollback source.

Sau khi cài thành công, chạy kiểm toán CHỈ ĐỌC:
  C:\PhoCap\.venv\Scripts\python.exe .\audit_32b.py

Gửi lại toàn bộ kết quả audit trước khi thử nạp Excel thật.
