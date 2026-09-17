BÀI SÁP NHẬP V4.4 - XỬ LÝ MÃ 4017981444 / TRẦN THỊ NGỌC
======================================================================

Mục tiêu:
- Làm sạch xung đột nguồn đang chặn phương án Tiểu học Nghi Thuỷ -> Tiểu học Nghi Tân.
- Không sửa file Excel gốc Danh_sach_giao_vien Tiểu học(2).xlsx.
- Không ghi phocap.db và không thực hiện sáp nhập trong bộ cài.

Kết luận kiểm chứng:
- File nguồn có 2 dòng cùng mã 4017981444, cùng Trần Thị Ngọc, sinh 12/01/1987:
  + Excel dòng 7663: Trường Tiểu học Nghi Hải - Đang làm việc.
  + Excel dòng 7861: Trường tiểu học Nghi Thuỷ - Đang làm việc.
- Database năm 2025-2026 có đúng 1 staff_member cho mã 4017981444 và đúng 1 staff_year_record,
  đang ở Tiểu học Nghi Thuỷ (mã trường 40413403).
- V4.4 giữ dòng Nghi Thuỷ trong nguồn canonical và loại dòng Nghi Hải khỏi registry đối chiếu
  bằng sổ điều chỉnh có kiểm soát; raw registry và Excel gốc vẫn được bảo toàn.

Sau V4.4 đã kiểm thử trên bản sao trạng thái sau hai lần sáp nhập Cửa Lò:
- Nghi Tân: 56/56 PASS.
- Nghi Thuỷ: 53/53 PASS.
- Cổng nguồn V4.3: PASS.
- Cổng trạng thái V4.1: PASS.
- Mô phỏng trong RAM: PASS.
- Rollover dự kiến Nghi Thuỷ -> Nghi Tân: 109 hồ sơ.
- Tiểu học toàn tỉnh: PASS 96 / BLOCK 139 / tổng 235.
- Thực hiện thật thử trên bản sao: thành công, nhật ký 419, integrity/FK đạt.

CÀI ĐẶT:
1. Dừng Uvicorn bằng Ctrl+C.
2. Chép cai_dat_bai_sap_nhap_v4_4_xu_ly_4017981444.py vào C:\PhoCap.
3. Chạy:
   cd C:\PhoCap
   .\.venv\Scripts\python.exe .\cai_dat_bai_sap_nhap_v4_4_xu_ly_4017981444.py
4. Khi báo thành công, khởi động lại Uvicorn.
5. Vào Cửa Lò -> Tiểu học -> Nghi Thuỷ -> Nghi Tân -> XEM TRƯỚC TÁC ĐỘNG.
6. Phải thấy V4.3 ĐẠT, V4.1 ĐẠT và MÔ PHỎNG ĐẠT. Chưa bấm thực hiện trước khi đối chiếu màn hình.
