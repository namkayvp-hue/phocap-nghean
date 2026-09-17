BÀI 33A.3 - ĐỊNH DẠNG SỐ TÀI CHÍNH

Mục tiêu:
- Excel MN-TC: 2.5000 hiển thị 2,5; 10.0000 hiển thị 10; 2.25 hiển thị 2,25.
- Không làm tròn thành số nguyên (2,5 không biến thành 3).
- Giá trị thật trong ô/DB không thay đổi; Excel chỉ áp dụng number format #,##0.##.
- Trang nhập web bỏ các số 0 dư cuối: 10.0000 -> 10, 2.5000 -> 2.5.
- Không đổi route, menu, schema, phân quyền hoặc dữ liệu nghiệp vụ.

Cài:
  C:\PhoCap\.venv\Scripts\python.exe .\install_33a_3.py

Audit:
  C:\PhoCap\.venv\Scripts\python.exe .\audit_33a_3.py
