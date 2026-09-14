from __future__ import annotations

import hashlib
import py_compile
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path


EXPECTED_NORMALIZED_SHA256 = (
    "99730ee16e43221990f2d78086cecbd6d18298c0f0d0826cd9aac8c3808bbd61"
)

OLD_PUBLIC_PREFIXES = 'PUBLIC_PREFIXES = ("/static",)'
NEW_PUBLIC_PREFIXES = (
    'PUBLIC_PREFIXES = ("/static", "/dang-nhap/api/")'
)

MARKER = "/dang-nhap/api/"


def normalized_sha256(path: Path) -> str:
    raw = path.read_bytes()
    normalized = (
        raw
        .replace(b"\r\n", b"\n")
        .replace(b"\r", b"\n")
    )
    return hashlib.sha256(normalized).hexdigest()


def db_check(path: Path) -> tuple[str, int]:
    if not path.is_file():
        return "missing", 0

    uri = f"file:{path.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)

    try:
        integrity = str(
            conn.execute(
                "PRAGMA integrity_check"
            ).fetchone()[0]
        )
        fk_count = len(
            list(
                conn.execute(
                    "PRAGMA foreign_key_check"
                )
            )
        )
        return integrity, fk_count
    finally:
        conn.close()


def main() -> int:
    root = Path(r"C:\PhoCap")

    if not (
        root / "app" / "access_control.py"
    ).is_file():
        root = Path.cwd()

    access_path = (
        root / "app" / "access_control.py"
    )
    db_path = root / "data" / "phocap.db"

    print(
        "BÀI 13B-11-16.2 V2.1 - "
        "SỬA DANH SÁCH CHỌN ĐĂNG NHẬP"
    )
    print("=" * 100)
    print(f"Dự án: {root}")

    if not access_path.is_file():
        print(
            "DỪNG AN TOÀN: không tìm thấy "
            "app/access_control.py"
        )
        return 2

    text = access_path.read_text(
        encoding="utf-8"
    )

    if (
        NEW_PUBLIC_PREFIXES in text
        or (
            "PUBLIC_PREFIXES" in text
            and MARKER in text
        )
    ):
        print()
        print(
            "V2.1 đã có trong mã nguồn. "
            "Không cài lặp."
        )
        return 0

    current_hash = normalized_sha256(
        access_path
    )

    print(
        f"app/access_control.py: {current_hash}"
    )

    if current_hash != EXPECTED_NORMALIZED_SHA256:
        print()
        print(
            "DỪNG AN TOÀN: access_control.py "
            "đã khác bản sau Danh mục lớp 4 cấp."
        )
        print(
            "Không tự ghi đè. Hãy gửi lại ZIP "
            "mã nguồn mới nhất nếu vừa sửa thêm."
        )
        return 3

    count = text.count(
        OLD_PUBLIC_PREFIXES
    )

    if count != 1:
        print()
        print(
            "DỪNG AN TOÀN: không tìm thấy đúng "
            "1 vị trí PUBLIC_PREFIXES cần sửa."
        )
        print(f"Số vị trí tìm thấy: {count}")
        return 4

    integrity, fk_count = db_check(
        db_path
    )

    print(
        f"Database integrity_check: {integrity}"
    )
    print(
        f"Database foreign_key_check: "
        f"{fk_count} lỗi"
    )

    if (
        db_path.is_file()
        and (
            integrity.lower() != "ok"
            or fk_count != 0
        )
    ):
        print()
        print(
            "DỪNG AN TOÀN: database chưa đạt "
            "kiểm tra."
        )
        return 5

    stamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    backup_dir = (
        root
        / "exports"
        / (
            "backup_truoc_bai_13b_11_16_2_"
            "v2_1_"
            + stamp
        )
    )

    backup_access = (
        backup_dir
        / "app"
        / "access_control.py"
    )

    backup_access.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    shutil.copy2(
        access_path,
        backup_access,
    )

    backup_db = None
    if db_path.is_file():
        backup_db = (
            backup_dir
            / "data"
            / "phocap.db"
        )
        backup_db.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        shutil.copy2(
            db_path,
            backup_db,
        )

    print()
    print(f"Đã backup: {backup_dir}")

    new_text = text.replace(
        OLD_PUBLIC_PREFIXES,
        NEW_PUBLIC_PREFIXES,
        1,
    )

    try:
        access_path.write_text(
            new_text,
            encoding="utf-8",
        )

        py_compile.compile(
            str(access_path),
            doraise=True,
        )

        verify = access_path.read_text(
            encoding="utf-8"
        )

        if NEW_PUBLIC_PREFIXES not in verify:
            raise RuntimeError(
                "Không xác nhận được đường dẫn "
                "API đăng nhập công khai."
            )

    except Exception as exc:
        shutil.copy2(
            backup_access,
            access_path,
        )

        print()
        print(
            "CÀI ĐẶT LỖI - "
            "ĐÃ TỰ KHÔI PHỤC access_control.py"
        )
        print(f"Lỗi: {exc}")
        return 6

    integrity_after, fk_after = db_check(
        db_path
    )

    report_path = (
        root
        / "exports"
        / (
            "bao_cao_sua_danh_sach_"
            "dang_nhap_v2_1_"
            + stamp
            + ".txt"
        )
    )

    report_lines = [
        "BÁO CÁO BÀI 13B-11-16.2 V2.1",
        f"Thời gian: "
        f"{datetime.now():%d/%m/%Y %H:%M:%S}",
        f"Dự án: {root}",
        "",
        "NGUYÊN NHÂN:",
        (
            "API /dang-nhap/api/lua-chon bị "
            "middleware phân quyền chuyển về "
            "/dang-nhap vì chưa được khai báo "
            "là đường dẫn công khai."
        ),
        "",
        "ĐÃ SỬA:",
        (
            "Cho phép duy nhất prefix "
            "/dang-nhap/api/ truy cập khi chưa "
            "đăng nhập."
        ),
        (
            "Không mở công khai các chức năng "
            "khác của hệ thống."
        ),
        (
            "Không thay đổi auth.py, login.html "
            "hay cấu trúc database."
        ),
        "",
        f"Backup: {backup_dir}",
        (
            "Database integrity_check sau cài: "
            f"{integrity_after}"
        ),
        (
            "Database foreign_key_check sau cài: "
            f"{fk_after} lỗi"
        ),
    ]

    report_path.write_text(
        "\n".join(report_lines) + "\n",
        encoding="utf-8-sig",
    )

    print()
    print("=" * 100)
    print("CÀI ĐẶT THÀNH CÔNG")
    print("=" * 100)
    print(
        "Đã sửa đúng 1 file:"
    )
    print(
        " - app/access_control.py"
    )
    print(
        "Không thay đổi cấu trúc database."
    )
    print(
        f"Báo cáo: {report_path}"
    )
    print()
    print(
        "Khởi động lại Uvicorn, "
        "mở /dang-nhap và thử:"
    )
    print(
        "Trường -> chọn Xã -> chọn Trường "
        "-> chọn tài khoản."
    )
    print(
        "Giáo viên -> chọn Xã -> chọn Trường "
        "-> chọn Giáo viên."
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
