from __future__ import annotations

import py_compile
import shutil
from datetime import datetime
from pathlib import Path

MARK_V23 = "BAI_13B_11_16_2_V2_3_LOGIN_ACCOUNT_SCOPE_START"
MARK_V25 = "BAI_13B_11_16_2_V2_5_SCHOOL_UNIT_ACCOUNT_ONLY"

OLD_BLOCK = '        elif scope in {"TRUONG", "GIAO_VIEN"}:\n            selected_school_id = _safe_id(school_id)\n            if selected_school_id is None:\n                return _json_no_store(\n                    {"ok": True, "items": []}\n                )\n\n            stmt = stmt.where(\n                User.school_id == selected_school_id,\n                Role.code.in_(role_codes),\n            )\n'
NEW_BLOCK = '        elif scope in {"TRUONG", "GIAO_VIEN"}:\n            selected_school_id = _safe_id(school_id)\n            if selected_school_id is None:\n                return _json_no_store(\n                    {"ok": True, "items": []}\n                )\n\n            if scope == "TRUONG":\n                # === BAI_13B_11_16_2_V2_5_SCHOOL_UNIT_ACCOUNT_ONLY ===\n                # Cấp đăng nhập "Trường" chỉ dùng tài khoản ĐƠN VỊ TRƯỜNG.\n                # Không đưa CBQL (cbql.*) vào đây vì CBQL là cá nhân,\n                # có thể tham gia điều tra/phân công nhưng không phải\n                # tài khoản đại diện đơn vị trường.\n                stmt = stmt.where(\n                    User.school_id == selected_school_id,\n                    User.username.ilike("truong_%"),\n                )\n            else:\n                # Giáo viên vẫn chỉ lấy đúng vai trò GIAO_VIEN của trường.\n                stmt = stmt.where(\n                    User.school_id == selected_school_id,\n                    Role.code.in_(role_codes),\n                )\n'


def main() -> int:
    root = Path(r"C:\PhoCap")
    auth_path = root / "app" / "routers" / "auth.py"

    if not auth_path.is_file():
        root = Path.cwd()
        auth_path = root / "app" / "routers" / "auth.py"

    print("=" * 100)
    print("BÀI 13B-11-16.2 V2.5 - LỌC TÀI KHOẢN ĐƠN VỊ Ở CẤP TRƯỜNG")
    print("=" * 100)
    print(f"Dự án: {root}")
    print()

    if not auth_path.is_file():
        print("DỪNG AN TOÀN: không tìm thấy app/routers/auth.py")
        return 2

    text = auth_path.read_text(encoding="utf-8")

    if MARK_V25 in text:
        print("V2.5 đã có trong mã nguồn. Không cài lặp.")
        return 0

    if MARK_V23 not in text:
        print("DỪNG AN TOÀN: chưa thấy nền đăng nhập V2.3 trong auth.py.")
        print("Không tự sửa trên nền mã nguồn khác.")
        return 3

    count = text.count(OLD_BLOCK)
    if count != 1:
        print("DỪNG AN TOÀN: không tìm thấy đúng 1 khối Trường/Giáo viên cần sửa.")
        print(f"Số vị trí tìm thấy: {count}")
        print("Không ghi đè.")
        return 4

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = (
        root
        / "exports"
        / f"backup_truoc_bai_13b_11_16_2_v2_5_{stamp}"
    )
    backup_path = (
        backup_dir
        / "app"
        / "routers"
        / "auth.py"
    )
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(auth_path, backup_path)

    new_text = text.replace(
        OLD_BLOCK,
        NEW_BLOCK,
        1,
    )

    try:
        auth_path.write_text(new_text, encoding="utf-8")
        py_compile.compile(str(auth_path), doraise=True)

        verify = auth_path.read_text(encoding="utf-8")
        if MARK_V25 not in verify:
            raise RuntimeError("Thiếu marker V2.5 sau cài.")

        if 'User.username.ilike("truong_%")' not in verify:
            raise RuntimeError("Thiếu bộ lọc tài khoản đơn vị trường.")

    except Exception as exc:
        shutil.copy2(backup_path, auth_path)
        print()
        print("CÀI LỖI - ĐÃ TỰ KHÔI PHỤC auth.py.")
        print("Chi tiết:", exc)
        return 5

    report = (
        root
        / "exports"
        / f"bao_cao_dang_nhap_v2_5_{stamp}.txt"
    )
    report.write_text(
        "\n".join(
            [
                "BÁO CÁO BÀI 13B-11-16.2 V2.5",
                f"Thời gian: {datetime.now():%d/%m/%Y %H:%M:%S}",
                f"Dự án: {root}",
                "",
                "ĐÃ SỬA CẤP TRƯỜNG:",
                (
                    "1. Sau khi chọn Xã -> Trường, danh sách tài khoản "
                    "chỉ nhận tài khoản đơn vị có username truong_*."
                ),
                (
                    "2. Không còn đưa các tài khoản cá nhân CBQL cbql.* "
                    "vào danh sách đăng nhập cấp Trường."
                ),
                (
                    "3. Nếu trường chỉ có một tài khoản truong_* thì "
                    "JavaScript hiện tại sẽ tự chọn tài khoản đó."
                ),
                (
                    "4. Cấp Giáo viên giữ nguyên: chỉ hiện giáo viên "
                    "thuộc đúng trường đã chọn."
                ),
                "5. Không thay đổi database.",
                "",
                f"Backup: {backup_dir}",
            ]
        ) + "\n",
        encoding="utf-8-sig",
    )

    print()
    print("=" * 100)
    print("CÀI ĐẶT THÀNH CÔNG V2.5")
    print("=" * 100)
    print("Đã sửa đúng 1 file:")
    print(" - app/routers/auth.py")
    print("Không thay đổi database.")
    print()
    print("Sau khi khởi động lại:")
    print("Trường -> chọn Xã -> chọn Trường")
    print("=> chỉ còn tài khoản truong_* của chính trường.")
    print("=> CBQL cbql.* không còn xuất hiện ở cấp Trường.")
    print()
    print(f"Backup: {backup_dir}")
    print(f"Báo cáo: {report}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
