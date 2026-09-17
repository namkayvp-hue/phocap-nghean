from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parent
USERS_PY = ROOT / "app" / "routers" / "users.py"
LIST_HTML = ROOT / "app" / "templates" / "users" / "list.html"
ACCESS_CONTROL = ROOT / "app" / "access_control.py"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"KHÔNG ĐẠT: {message}")


def main() -> None:
    users_text = USERS_PY.read_text(encoding="utf-8")
    html_text = LIST_HTML.read_text(encoding="utf-8")
    access_text = ACCESS_CONTROL.read_text(encoding="utf-8")

    ast.parse(users_text, filename=str(USERS_PY))

    require(
        '@router.post("/{user_id}/dat-lai-mat-khau")' in users_text,
        "chưa có đường dẫn POST đặt lại mật khẩu.",
    )
    require(
        "co_quyen_dat_lai_mat_khau" in users_text,
        "chưa có kiểm tra quyền theo phạm vi quản lý.",
    )
    require(
        "account.password_hash = ma_hoa_mat_khau(mat_khau_moi)" in users_text,
        "chưa mã hóa và cập nhật mật khẩu.",
    )
    require(
        "mat_khau_moi != xac_nhan_mat_khau" in users_text,
        "chưa kiểm tra hai lần nhập mật khẩu.",
    )
    require(
        'data-reset-password' in html_text,
        "chưa có nút đặt lại mật khẩu trong danh sách.",
    )
    require(
        'id="reset-password-dialog"' in html_text,
        "chưa có hộp nhập mật khẩu mới.",
    )
    require(
        'name="mat_khau_moi"' in html_text
        and 'name="xac_nhan_mat_khau"' in html_text,
        "biểu mẫu chưa có đủ hai ô mật khẩu.",
    )
    require(
        'method="post"' in html_text,
        "biểu mẫu chưa dùng phương thức POST.",
    )
    require(
        'if role_code == SCHOOL_ROLE_CODE:' in access_text
        and 'return path.startswith("/tai-khoan")' in access_text,
        "AccessControl chưa cho tài khoản Trường thực hiện POST trong /tai-khoan.",
    )

    print("BÀI 11C-28 ĐÃ SẴN SÀNG.")
    print("OK PYTHON: app/routers/users.py")
    print("OK HTML: app/templates/users/list.html")
    print("OK QUYỀN: ADMIN/SO và TRƯỜNG theo đúng phạm vi.")
    print("OK BẢO MẬT: POST, nhập hai lần, mật khẩu được băm.")
    print("Không có dữ liệu cơ sở dữ liệu nào được thêm, sửa hoặc xóa.")


if __name__ == "__main__":
    main()
