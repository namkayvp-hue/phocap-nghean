# Phương án tham chiếu sáp nhập trường

Hai tệp JSON được đóng gói cùng mã nguồn để máy chủ Docker có thể mở trang
sáp nhập khi vùng `data` chưa có sổ phương án. Đây là bản sao của sổ phương án
chính thức và khóa cấp học QĐ3805 đang có tại local, không chứa danh sách giáo viên.

Ưu tiên các tệp đang có trong `data/school_merger_official_registry.json` và
`data/school_merger_registry/qd3805_level_lock.json`. Chỉ dùng bản tham chiếu
khi tệp tương ứng không tồn tại; không thay thế tệp sai cấu trúc hay ghi đè dữ liệu.

Các dữ liệu đối chiếu đội ngũ trong `data/school_merger_source_rosters` vẫn phải
được quản trị cung cấp riêng trên máy chủ. Không bỏ qua kiểm tra nguồn, xác nhận,
sao lưu hay điều kiện thực hiện sáp nhập.

Sau khi cập nhật mã nguồn trên máy chủ, cần tạo lại container để đưa các tệp
tham chiếu và bản sửa vào ứng dụng. Không cần sao chép cơ sở dữ liệu local.
