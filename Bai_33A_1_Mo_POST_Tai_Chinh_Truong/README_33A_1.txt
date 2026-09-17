BÀI 33A.1 - SỬA LỖI BẤM LƯU TÀI CHÍNH TRƯỜNG BỊ FORBIDDEN

Nguyên nhân:
- Router Bài 33A đã cho TRUONG POST /bao-cao/tai-chinh/nhap.
- Nhưng middleware app/access_control.py vẫn dùng luật cũ: TRUONG chỉ được POST /tai-khoan.
- Vì vậy GET trang tài chính mở được, nhưng POST khi bấm Lưu bị chặn trước khi tới router.

Phạm vi sửa:
- Chỉ app/access_control.py.
- Mở POST đúng duy nhất /bao-cao/tai-chinh/nhap cho vai trò TRUONG.
- Router Bài 33A vẫn kiểm tra school_id phải đúng chính trường đăng nhập.
- Không sửa database, không sửa menu, báo cáo, điều tra, học sinh, đội ngũ, CSVC, sáp nhập hay đổi tên trường.

Sau cài cần restart Uvicorn nếu không chạy --reload.
