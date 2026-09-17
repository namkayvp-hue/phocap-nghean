BÀI SÁP NHẬP V4.3.1 - SỬA LỖI UNICODE SMOKE AUDIT
====================================================

Lỗi đã sửa:
UnicodeEncodeError: 'charmap' codec can't encode character ... cp1252
xảy ra trong tiến trình Python con của bước Smoke audit V4.3 trên Windows.

Nguyên nhân:
Khi Python con ghi JSON tiếng Việt vào PIPE, Windows có thể chọn cp1252 cho stdout,
trong khi JSON có ký tự Unicode tiếng Việt.

V4.3.1 sửa theo hai lớp:
1) ép PYTHONIOENCODING=utf-8 và PYTHONUTF8=1 cho tiến trình smoke audit;
2) JSON smoke audit dùng ensure_ascii=True nên luồng kiểm thử chỉ chứa ASCII an toàn.

KHÔNG thay đổi nghiệp vụ V4.3.
KHÔNG thực hiện sáp nhập.
KHÔNG chủ động ghi phocap.db.
Nếu lần chạy V4.3 trước đã báo DỪNG AN TOÀN thì bộ cài đã khôi phục mã nguồn đã chạm.

CÁCH CHẠY
1. Dừng Uvicorn bằng Ctrl+C.
2. Chép cai_dat_bai_sap_nhap_v4_3_1_sua_unicode_smoke_audit.py vào C:\PhoCap.
3. Chạy:
   cd C:\PhoCap
   .\.venv\Scripts\python.exe .\cai_dat_bai_sap_nhap_v4_3_1_sua_unicode_smoke_audit.py

KẾT QUẢ CẦN THẤY
- BÀI SÁP NHẬP V4.3.1 - CÀI ĐẶT THÀNH CÔNG
- Database: KHÔNG THAY ĐỔI
- TH: tổng 235 ... PASS 95; BLOCK 140 (theo bộ dữ liệu kiểm thử hiện tại)
- MN/THCS bị khóa nếu chưa có nguồn đối chiếu tương ứng.
