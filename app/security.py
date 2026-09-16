from pwdlib import PasswordHash


# Sử dụng cấu hình mã hóa mật khẩu được khuyến nghị.
password_hash = PasswordHash.recommended()


def ma_hoa_mat_khau(mat_khau: str) -> str:
    """
    Mã hóa mật khẩu trước khi lưu vào cơ sở dữ liệu.
    """

    return password_hash.hash(mat_khau)


def kiem_tra_mat_khau(
    mat_khau_thuong: str,
    mat_khau_da_ma_hoa: str,
) -> bool:
    """
    Kiểm tra mật khẩu người dùng nhập
    có khớp với mật khẩu đã mã hóa hay không.
    """

    return password_hash.verify(
        mat_khau_thuong,
        mat_khau_da_ma_hoa,
    )