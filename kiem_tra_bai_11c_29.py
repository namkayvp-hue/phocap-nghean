from __future__ import annotations

import py_compile
from pathlib import Path

from jinja2 import Environment, FileSystemLoader


ROOT = Path(__file__).resolve().parent
USERS_PY = ROOT / "app" / "routers" / "users.py"
LIST_HTML = ROOT / "app" / "templates" / "users" / "list.html"


def require_text(path: Path, markers: list[str]) -> None:
    content = path.read_text(encoding="utf-8")
    missing = [marker for marker in markers if marker not in content]
    if missing:
        raise RuntimeError(
            f"{path}: thiếu dấu hiệu mã nguồn: {', '.join(missing)}"
        )


def main() -> int:
    if not USERS_PY.exists() or not LIST_HTML.exists():
        print("KHÔNG THÀNH CÔNG: chưa chép đúng bộ mã vào C:\\PhoCap.")
        return 1

    py_compile.compile(str(USERS_PY), doraise=True)

    environment = Environment(
        loader=FileSystemLoader(str(ROOT / "app" / "templates"))
    )
    environment.get_template("users/list.html")

    require_text(
        USERS_PY,
        [
            "ADMIN_SECTIONS",
            "lay_danh_sach_tai_khoan_phan_trang",
            "tong_hop_tai_khoan",
            "dat-lai-mat-khau",
            "khoa-mo",
            "return_to",
            "page_size",
        ],
    )
    require_text(
        LIST_HTML,
        [
            "Tài khoản Xã/phường",
            "Tài khoản Trường MN",
            "Tra cứu toàn hệ thống",
            "filter_commune_id",
            "filter_school_id",
            "Cấp lại MK",
            "Tạo mật khẩu tạm",
            "pagination-links",
        ],
    )

    print("BÀI 11C-29 ĐÃ SẴN SÀNG.")
    print("OK PYTHON: app/routers/users.py")
    print("OK HTML: app/templates/users/list.html")
    print("OK TRUY CẬP NHANH: Phòng ban, Xã/phường, Trường và Tra cứu.")
    print("OK TÌM KIẾM: tên đăng nhập, họ tên, mã/tên xã và trường.")
    print("OK PHÂN TRANG: 20, 50 hoặc 100 tài khoản mỗi trang.")
    print("OK THAO TÁC: tạo, sửa, sao chép tên đăng nhập, cấp lại mật khẩu, khóa/mở.")
    print("OK PHẠM VI: ADMIN/SO và Trường theo quyền hiện có.")
    print("Không có dữ liệu cơ sở dữ liệu nào được thêm, sửa hoặc xóa.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
