from __future__ import annotations

import os
import shutil
import sqlite3
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path

PROJECT = Path(os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")).resolve()
ACCESS = PROJECT / "app" / "access_control.py"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP_DIR = PROJECT / "exports" / f"backup_sua_quyen_ho_dan_3_cap_v1_{STAMP}"
BACKUP_ACCESS = BACKUP_DIR / "app" / "access_control.py"

MARKER = "FIX_HOUSEHOLD_LIST_SCOPE_3_ROLES_V1"
PATCH_BLOCK = '\n        # === FIX_HOUSEHOLD_LIST_SCOPE_3_ROLES_V1_START ===\n        # Trang danh sách hộ là "cửa vào" của 2.2.1.\n        #\n        # Router danh_sach_ho_dan() đã tự lọc:\n        # - Xã: toàn bộ phiếu đúng xã/phường.\n        # - Trường: chỉ phiếu đã giao cho nhân sự thuộc trường.\n        # - Giáo viên: chỉ phiếu được giao trực tiếp.\n        #\n        # Vì vậy middleware chỉ kiểm tra PHẠM VI ĐỊA BÀN cho URL danh sách,\n        # còn quyền xem từng hộ cụ thể vẫn tiếp tục bị kiểm tra theo phân công\n        # ở các nhánh household_match phía dưới.\n        base_household_list = re.fullmatch(\n            r"/dieu-tra/\\d+/ho-dan",\n            normalized_path,\n        )\n        if (\n            base_household_list is not None\n            and role_code in {\n                SCHOOL_ROLE_CODE,\n                TEACHER_ROLE_CODE,\n            }\n        ):\n            school_id = auth_user.get("school_id")\n            if school_id is None:\n                return False\n\n            school_commune_id = db.execute(\n                text(\n                    "SELECT commune_id "\n                    "FROM schools "\n                    "WHERE id = :school_id "\n                    "LIMIT 1"\n                ),\n                {"school_id": int(school_id)},\n            ).scalar()\n\n            if school_commune_id is None:\n                return False\n\n            return int(batch_commune_id) == int(school_commune_id)\n        # === FIX_HOUSEHOLD_LIST_SCOPE_3_ROLES_V1_END ===\n'


def read_text(path: Path) -> str:
    if not path.exists():
        raise RuntimeError(f"Không tìm thấy tệp bắt buộc: {path}")
    return path.read_text(encoding="utf-8-sig")


def backup() -> None:
    BACKUP_ACCESS.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ACCESS, BACKUP_ACCESS)


def restore() -> None:
    if BACKUP_ACCESS.exists():
        ACCESS.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(BACKUP_ACCESS, ACCESS)


def clear_cache() -> None:
    app_dir = PROJECT / "app"
    for cache in app_dir.rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(cache, ignore_errors=True)


def patch(text_value: str) -> str:
    if MARKER in text_value:
        print("Bản sửa quyền 3 cấp đã có sẵn. Không chèn lặp.")
        return text_value

    required = [
        "def _co_quyen_dieu_tra",
        "COMMUNE_ROLE_CODE",
        "SCHOOL_ROLE_CODE",
        "TEACHER_ROLE_CODE",
        "batch_commune_id",
        "household_match = re.match",
    ]
    for marker in required:
        if marker not in text_value:
            raise RuntimeError(
                f"access_control.py thiếu nền mã nguồn: {marker}"
            )

    anchor = (
        "        if role_code == COMMUNE_ROLE_CODE:\n"
        "            commune_id = auth_user.get(\"commune_id\")\n"
        "            return (\n"
        "                commune_id is not None\n"
        "                and int(batch_commune_id) == int(commune_id)\n"
        "            )\n"
        "\n"
    )

    if anchor not in text_value:
        raise RuntimeError(
            "Không tìm thấy chính xác khối quyền Xã hiện tại. "
            "Dừng cài để tránh sửa nhầm phiên bản."
        )

    return text_value.replace(
        anchor,
        anchor + PATCH_BLOCK + "\n",
        1,
    )


def verify(text_value: str) -> None:
    checks = [
        MARKER,
        "base_household_list = re.fullmatch",
        "FROM schools",
        "return int(batch_commune_id) == int(school_commune_id)",
        "household_match = re.match",
        "sfi.user_id = :user_id",
        "assigned_user.school_id = :school_id",
    ]
    for marker in checks:
        if marker not in text_value:
            raise RuntimeError(
                f"Kiểm tra sau cài chưa đạt: {marker}"
            )

    subprocess.run(
        [sys.executable, "-m", "py_compile", str(ACCESS)],
        cwd=PROJECT,
        check=True,
    )


def diagnostic() -> None:
    print("")
    print("CHẨN ĐOÁN THAM KHẢO (không sửa dữ liệu):")
    try:
        sys.path.insert(0, str(PROJECT))
        old_cwd = Path.cwd()
        os.chdir(PROJECT)
        try:
            from app.database import DATABASE_PATH
            db_path = Path(DATABASE_PATH)
        finally:
            os.chdir(old_cwd)
            try:
                sys.path.remove(str(PROJECT))
            except ValueError:
                pass

        if not db_path.exists():
            print(" - Không tìm thấy database để chẩn đoán.")
            return

        con = sqlite3.connect(str(db_path))
        try:
            usernames = (
                "xa_16732",
                "truong_40413308",
                "gv.4032186629",
            )

            for username in usernames:
                row = con.execute(
                    "SELECT u.id, u.username, u.commune_id, u.school_id, r.code "
                    "FROM users AS u "
                    "JOIN roles AS r ON r.id = u.role_id "
                    "WHERE u.username = ? LIMIT 1",
                    (username,),
                ).fetchone()

                if not row:
                    print(f" - {username}: không tìm thấy.")
                    continue

                user_id, uname, commune_id, school_id, role_code = row
                school_commune_id = None
                school_name = ""
                if school_id is not None:
                    school_row = con.execute(
                        "SELECT commune_id, name FROM schools "
                        "WHERE id = ? LIMIT 1",
                        (school_id,),
                    ).fetchone()
                    if school_row:
                        school_commune_id = school_row[0]
                        school_name = school_row[1] or ""

                print(
                    f" - {uname}: role={role_code}, "
                    f"commune_id={commune_id}, school_id={school_id}, "
                    f"school_commune_id={school_commune_id}, "
                    f"school={school_name}"
                )

            batch = con.execute(
                "SELECT sb.id, sb.commune_id, sy.code, sb.name "
                "FROM survey_batches AS sb "
                "LEFT JOIN school_years AS sy ON sy.id = sb.school_year_id "
                "WHERE sb.id = ? LIMIT 1",
                (132,),
            ).fetchone()
            if batch:
                print(
                    " - Đợt #132: "
                    f"commune_id={batch[1]}, năm={batch[2]}, tên={batch[3]}"
                )
        finally:
            con.close()

    except Exception as exc:
        print(" - Không chạy được chẩn đoán:", exc)


def main() -> int:
    print("=" * 108)
    print("SỬA TRIỆT ĐỂ QUYỀN 2.2.1 - XÃ / TRƯỜNG / GIÁO VIÊN V1")
    print("=" * 108)
    print("")
    print("MỤC TIÊU:")
    print(" - Xã mở 2.2.1 theo đúng địa bàn.")
    print(" - Trường mở được 2.2.1 của đợt thuộc địa bàn trường;")
    print("   trang chỉ hiển thị phiếu thuộc phạm vi trường.")
    print(" - Giáo viên mở được 2.2.1 của đợt thuộc địa bàn trường;")
    print("   trang chỉ hiển thị phiếu được giao trực tiếp.")
    print(" - Nếu chưa được giao phiếu thì trang vẫn mở và danh sách rỗng,")
    print("   KHÔNG còn báo 'không có quyền'.")
    print("")
    print("BẢO MẬT GIỮ NGUYÊN:")
    print(" - Giáo viên không mở được hộ không giao cho mình.")
    print(" - Trường không mở được hộ ngoài phạm vi trường.")
    print(" - Trường/Giáo viên không mở được đợt thuộc xã/phường khác.")
    print("")
    print("KHÔNG THAY ĐỔI:")
    print(" - Database và dữ liệu.")
    print(" - Bài 13B-9 V1A/V1B.")
    print(" - Menu và giao diện.")
    print("")

    before = read_text(ACCESS)
    backup()

    try:
        after = patch(before)
        ACCESS.write_text(after, encoding="utf-8")
        verify(read_text(ACCESS))
        clear_cache()

        print("")
        print("CAI DAT SUA QUYEN HO DAN 3 CAP V1 THANH CONG")
        print("Backup:", BACKUP_DIR)
        diagnostic()
        print("")
        print("Khởi động lại Uvicorn, đăng nhập lại từng cấp và Ctrl + F5.")
        return 0

    except Exception:
        traceback.print_exc()
        print("")
        print("CÓ LỖI - ĐANG KHÔI PHỤC...")
        restore()
        clear_cache()
        print("ĐÃ KHÔI PHỤC access_control.py.")
        print("Backup:", BACKUP_DIR)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
