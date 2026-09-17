BÀI SÁP NHẬP V4.5
BẢNG ĐIỀU KHIỂN TOÀN TỈNH + SÁP NHẬP PHÁT SINH NGUỒN/ĐÍCH TỰ CHỌN
================================================================================

1. MỤC TIÊU
- Giữ nguyên luồng “Phương án chính thức” hiện tại.
- Bổ sung “Bảng điều khiển V4.5” để phân loại toàn tỉnh:
  GIỮ NGUYÊN / ĐÃ THỰC HIỆN / PASS-CÓ THỂ XEM TRƯỚC / BLOCK-CẦN XỬ LÝ.
- Có nút xuất Excel các phương án BLOCK kèm nguyên nhân.
- Bổ sung “Sáp nhập phát sinh” cho các quyết định sáp nhập mới trong tương lai.
- Sáp nhập phát sinh cho phép chọn một hoặc nhiều trường nguồn -> một trường đích,
  có thể khác xã/phường, nhưng phải cùng cấp kiểm tra nguồn đã chọn và phải qua đầy đủ cổng an toàn.

2. CỔNG AN TOÀN GIỮ NGUYÊN
- V4.3: kiểm tra dữ liệu nguồn.
- V4.1: fingerprint đúng tập dữ liệu có thể tác động.
- Mô phỏng trên bản sao SQLite trong RAM.
- Xem trước hoàn toàn chỉ đọc.
- Khi thực hiện thật: bắt buộc nhập SAP NHAP.
- BEGIN IMMEDIATE, tính lại fingerprint sau khóa ghi.
- Backup database trước khi thay đổi.
- Một transaction duy nhất.
- integrity_check + foreign_key_check trước COMMIT.
- Chống thực hiện lặp cùng nguồn/đích/năm hiệu lực.
- Giữ nguyên school_id của trường đích; không xóa trường nguồn; bảo toàn lịch sử năm cũ.

3. KHÔNG CÓ SÁP NHẬP HÀNG LOẠT
V4.5 không có nút “sáp nhập tất cả”. Mỗi phương án vẫn phải được xem trước và xác nhận riêng.

4. CÀI ĐẶT
Dừng Uvicorn bằng Ctrl+C.
Chép file:
  cai_dat_bai_sap_nhap_v4_5_bang_dieu_khien_va_phat_sinh.py
vào:
  C:\PhoCap

Chạy:
  cd C:\PhoCap
  .\.venv\Scripts\python.exe .\cai_dat_bai_sap_nhap_v4_5_bang_dieu_khien_va_phat_sinh.py

Sau khi cài thành công, khởi động lại:
  cd C:\PhoCap
  .\.venv\Scripts\python.exe -m uvicorn app.main:app --reload

5. ĐƯỜNG DẪN MỚI
- /cong-cu-du-lieu/sap-nhap-truong/bang-dieu-khien
- /cong-cu-du-lieu/sap-nhap-truong/phat-sinh

6. KIỂM TRA ĐẦU TIÊN SAU CÀI
- Mở Sáp nhập trường.
- Bấm “BẢNG ĐIỀU KHIỂN V4.5”.
- Kiểm tra 3 phương án Cửa Lò đã thực hiện phải hiện “ĐÃ THỰC HIỆN”.
- Bấm “SÁP NHẬP PHÁT SINH”.
- Kiểm tra có thể chọn năm hiệu lực, cấp học, nhiều trường nguồn và một trường đích bằng tìm nhanh.
- CHƯA thực hiện một phương án phát sinh thật ở bước kiểm tra đầu tiên.

7. LƯU Ý VỀ TRƯỜNG ĐÍCH MỚI HOÀN TOÀN
Cổng V4.3 hiện kiểm tra cả nguồn và đích bằng dữ liệu nguồn năm trước. Nếu một trường đích mới hoàn toàn
không có hồ sơ nguồn năm trước thì V4.3 sẽ chặn. Đây là chủ đích an toàn; trường hợp tạo trường mới hoàn toàn
sẽ được xây luồng riêng khi có nhu cầu thực tế.
================================================================================
