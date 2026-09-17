BÀI SÁP NHẬP V4.3 - KIỂM TRA DỮ LIỆU NGUỒN TOÀN TỈNH TRƯỚC SÁP NHẬP
================================================================================

MỤC TIÊU
- Áp dụng cổng kiểm tra dữ liệu nguồn cho mọi phương án sáp nhập chính thức.
- Chỉ mở mô phỏng/thực hiện thật khi dữ liệu nguồn của trường nguồn VÀ trường đích đạt.
- Kiểm tra nguồn theo: năm nguồn + cấp học + xã/phường + trường.
- Kiểm tra mã nhân sự, họ tên/ngày sinh, đúng trường trong năm nguồn, trạng thái đủ rollover,
  xung đột mã nhân sự và số lượng đang hoạt động.
- Tính fingerprint nguồn ở XEM TRƯỚC và tính lại bên trong BEGIN IMMEDIATE khi THỰC HIỆN.
  Nếu nguồn thay đổi thì chặn ghi database và yêu cầu xem trước lại.

NGUỒN ĐỐI CHIẾU ĐANG ĐƯỢC ĐĂNG KÝ
- TH / 2025-2026: Danh_sach_giao_vien Tiểu học(2).xlsx
- Registry chuẩn hóa: nguon_doi_chieu/TH_2025_2026.json
- 18.247 dòng, 518 nhóm trường.

QUY TẮC AN TOÀN VỀ PHẠM VI
- Bộ cài V4.3 áp dụng cơ chế cho toàn tỉnh và cả MN/TH/THCS.
- Hiện chưa có danh sách đội ngũ nguồn MN và THCS tương ứng trong bộ dữ liệu người dùng đã cung cấp.
  Vì vậy các phương án MN/THCS sẽ hiển thị CHƯA CÓ NGUỒN ĐỐI CHIẾU và BỊ KHÓA.
  Đây là hành vi an toàn có chủ đích, không phải lỗi.
- Phương án liên cấp cũng bị khóa nếu chưa xác định được duy nhất nguồn đối chiếu theo từng cấp.

CÀI ĐẶT
1. Dừng Uvicorn: Ctrl+C.
2. Chép file cai_dat_bai_sap_nhap_v4_3_kiem_tra_nguon_toan_tinh.py vào C:\PhoCap.
3. Chạy:

   cd C:\PhoCap
   .\.venv\Scripts\python.exe .\cai_dat_bai_sap_nhap_v4_3_kiem_tra_nguon_toan_tinh.py

4. Phải thấy:
   BÀI SÁP NHẬP V4.3 - CÀI ĐẶT THÀNH CÔNG
   Database: KHÔNG THAY ĐỔI

5. Khởi động lại:

   cd C:\PhoCap
   .\.venv\Scripts\python.exe -m uvicorn app.main:app --reload

SAU KHI CÀI
- Vào Sáp nhập trường -> Danh sách phương án chính thức.
- Bấm KIỂM TRA NGUỒN V4.3.
- Có thể lọc Năm học / Xã-phường / Cấp học.
- Mỗi phương án có PASS hoặc BLOCK và chi tiết từng trường.
- Bản XEM TRƯỚC của từng phương án có thêm mục KIỂM TRA DỮ LIỆU NGUỒN V4.3.
- Nút thực hiện thật chỉ mở khi đồng thời đạt V4.1 + V4.3 + mô phỏng kỹ thuật.

AN TOÀN BỘ CÀI
- Tự backup mã nguồn trước khi thay.
- Không thực hiện sáp nhập.
- Không ghi phocap.db.
- Kiểm tra hash phocap.db/WAL trước và sau.
- Kiểm tra integrity_check và foreign_key_check.
- Nếu cài lỗi sau khi chạm mã nguồn thì tự khôi phục các file đã thay.
- Có thể chạy lại bộ cài; trạng thái đã cài đúng sẽ được nhận biết (idempotent).
