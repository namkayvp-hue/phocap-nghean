BÀI 13A-2 V4 - BÁO CÁO TỔNG HỢP ĐIỀU TRA

Bản V4 sửa lỗi ModuleNotFoundError: No module named 'app' ở bước kiểm tra.
Nguyên nhân: Python chạy tệp kiểm tra nằm trong thư mục exports nên không tự đưa C:\PhoCap vào sys.path.

V4 thực hiện đồng thời hai lớp bảo vệ:
1. Bộ cài truyền PYTHONPATH và PHOCAP_PROJECT_DIR cho tiến trình kiểm tra.
2. Tệp kiểm tra chủ động thêm thư mục dự án vào sys.path trước khi import app.

Bộ cài vẫn sao lưu, kiểm tra và tự khôi phục nếu có lỗi.
