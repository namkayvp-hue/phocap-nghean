from __future__ import annotations

import shutil
from datetime import datetime
from getpass import getpass
from pathlib import Path

from sqlalchemy import text

from app.database import DATABASE_PATH, SessionLocal
from app.models import User
from app.security import ma_hoa_mat_khau


# Chỉ đặt lại mật khẩu cho đúng tài khoản trường này.
TARGET_USERNAME = "truong_hoasen"
EXPECTED_ROLE_CODE = "TRUONG"
EXPECTED_SCHOOL_NAME = "Trường Mầm non Hoa Sen"

MIN_PASSWORD_LENGTH = 8


def doc_thong_tin_tai_khoan() -> dict | None:
    """Đọc thông tin tài khoản nhưng không thay đổi dữ liệu."""
    sql = text(
        """
        SELECT
            u.id,
            u.username,
            u.full_name,
            u.password_hash,
            u.is_active,
            r.code AS role_code,
            s.name AS school_name
        FROM users AS u
        JOIN roles AS r
            ON r.id = u.role_id
        LEFT JOIN schools AS s
            ON s.id = u.school_id
        WHERE lower(u.username) = lower(:username)
        LIMIT 1
        """
    )

    with SessionLocal() as db:
        row = db.execute(
            sql,
            {"username": TARGET_USERNAME},
        ).mappings().first()

        if row is None:
            return None

        return dict(row)


def kiem_tra_dung_tai_khoan(thong_tin: dict) -> bool:
    """Ngăn đặt lại nhầm tài khoản, nhầm vai trò hoặc nhầm trường."""
    if thong_tin["role_code"] != EXPECTED_ROLE_CODE:
        print()
        print("KHÔNG THỰC HIỆN: tài khoản không mang vai trò TRUONG.")
        print(f"Vai trò thực tế: {thong_tin['role_code']}")
        return False

    if thong_tin["school_name"] != EXPECTED_SCHOOL_NAME:
        print()
        print("KHÔNG THỰC HIỆN: tài khoản không thuộc đúng trường.")
        print(f"Trường thực tế: {thong_tin['school_name']}")
        return False

    return True


def nhap_mat_khau_moi() -> str | None:
    """Yêu cầu nhập mật khẩu mới hai lần; nội dung không hiện trên màn hình."""
    print()
    print(f"Mật khẩu phải có ít nhất {MIN_PASSWORD_LENGTH} ký tự.")
    print("Khi nhập, Terminal sẽ không hiển thị ký tự. Đây là trạng thái bình thường.")

    mat_khau_1 = getpass("Nhập mật khẩu mới: ")

    if len(mat_khau_1) < MIN_PASSWORD_LENGTH:
        print("KHÔNG THỰC HIỆN: mật khẩu chưa đủ 8 ký tự.")
        return None

    if mat_khau_1 != mat_khau_1.strip():
        print("KHÔNG THỰC HIỆN: mật khẩu không được có khoảng trắng ở đầu hoặc cuối.")
        return None

    mat_khau_2 = getpass("Nhập lại mật khẩu mới: ")

    if mat_khau_1 != mat_khau_2:
        print("KHÔNG THỰC HIỆN: hai lần nhập mật khẩu không giống nhau.")
        return None

    return mat_khau_1


def sao_luu_co_so_du_lieu() -> Path:
    """Sao lưu nguyên tệp cơ sở dữ liệu trước khi cập nhật."""
    duong_dan_db = Path(DATABASE_PATH).resolve()

    if not duong_dan_db.exists():
        raise FileNotFoundError(
            f"Không tìm thấy cơ sở dữ liệu: {duong_dan_db}"
        )

    thu_muc_sao_luu = duong_dan_db.parent / "backups"
    thu_muc_sao_luu.mkdir(parents=True, exist_ok=True)

    moc_thoi_gian = datetime.now().strftime("%Y%m%d_%H%M%S")
    tep_sao_luu = (
        thu_muc_sao_luu
        / f"truoc_reset_truong_hoasen_{moc_thoi_gian}{duong_dan_db.suffix}"
    )

    shutil.copy2(duong_dan_db, tep_sao_luu)
    return tep_sao_luu


def dat_lai_mat_khau(
    user_id: int,
    mat_khau_moi: str,
    password_hash_cu: str,
) -> None:
    """Chỉ cập nhật trường password_hash của đúng một tài khoản."""
    with SessionLocal() as db:
        try:
            user = db.get(User, user_id)

            if user is None:
                raise RuntimeError(
                    "Tài khoản không còn tồn tại trước thời điểm cập nhật."
                )

            if user.username.lower() != TARGET_USERNAME.lower():
                raise RuntimeError(
                    "ID tài khoản không còn khớp với tên đăng nhập cần đặt lại."
                )

            user.password_hash = ma_hoa_mat_khau(mat_khau_moi)

            # Không thay đổi họ tên, vai trò, xã, trường hoặc trạng thái hoạt động.
            db.commit()
            db.refresh(user)

            if user.password_hash == password_hash_cu:
                raise RuntimeError(
                    "Mã băm mật khẩu không thay đổi sau khi cập nhật."
                )

        except Exception:
            db.rollback()
            raise


def main() -> int:
    print("=" * 68)
    print("ĐẶT LẠI MẬT KHẨU AN TOÀN CHO TÀI KHOẢN TRƯỜNG HOA SEN")
    print("=" * 68)

    thong_tin = doc_thong_tin_tai_khoan()

    if thong_tin is None:
        print(f"KHÔNG TÌM THẤY TÀI KHOẢN: {TARGET_USERNAME}")
        return 1

    print(f"Tên đăng nhập : {thong_tin['username']}")
    print(f"Họ và tên     : {thong_tin['full_name']}")
    print(f"Vai trò       : {thong_tin['role_code']}")
    print(f"Trường        : {thong_tin['school_name']}")
    print(
        "Trạng thái    : "
        + ("Đang hoạt động" if thong_tin["is_active"] else "Đang bị khóa")
    )

    if not kiem_tra_dung_tai_khoan(thong_tin):
        return 1

    mat_khau_moi = nhap_mat_khau_moi()

    if mat_khau_moi is None:
        return 1

    print()
    print("Để xác nhận, nhập chính xác tên đăng nhập sau:")
    print(TARGET_USERNAME)

    xac_nhan = input("Xác nhận tên đăng nhập: ").strip()

    if xac_nhan.lower() != TARGET_USERNAME.lower():
        print("ĐÃ HỦY: nội dung xác nhận không đúng.")
        return 1

    try:
        tep_sao_luu = sao_luu_co_so_du_lieu()

        dat_lai_mat_khau(
            user_id=int(thong_tin["id"]),
            mat_khau_moi=mat_khau_moi,
            password_hash_cu=str(thong_tin["password_hash"]),
        )

    except Exception as exc:
        print()
        print("KHÔNG THÀNH CÔNG.")
        print(f"Lỗi: {exc}")
        return 1

    print()
    print("=" * 68)
    print("ĐẶT LẠI MẬT KHẨU THÀNH CÔNG")
    print("=" * 68)
    print(f"Tài khoản : {TARGET_USERNAME}")
    print(f"Vai trò   : {EXPECTED_ROLE_CODE}")
    print(f"Trường    : {EXPECTED_SCHOOL_NAME}")
    print(f"Đã sao lưu: {tep_sao_luu}")
    print("Không thay đổi họ tên, vai trò, trường hoặc trạng thái tài khoản.")
    print("Mật khẩu mới không được in ra màn hình.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())