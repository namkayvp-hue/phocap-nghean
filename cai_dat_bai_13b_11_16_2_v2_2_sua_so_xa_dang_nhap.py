from __future__ import annotations

import hashlib
import py_compile
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path


EXPECTED_NORMALIZED_SHA256 = (
    "b2ded4751bcfe13e731e5bcff0a61b396b67fab077619e60a4a911fe48f18f47"
)

OLD_BLOCK = '''        if scope == "SO":
            stmt = stmt.where(
                User.commune_id.is_(None),
                User.school_id.is_(None),
            )

        elif scope == "XA":
            selected_commune_id = _safe_id(commune_id)
            if selected_commune_id is None:
                return _json_no_store(
                    {"ok": True, "items": []}
                )
            stmt = stmt.where(
                User.commune_id == selected_commune_id,
                User.school_id.is_(None),
            )

        elif scope in {"TRUONG", "GIAO_VIEN"}:
'''

NEW_BLOCK = '''        if scope == "SO":
            # Tài khoản cấp Sở/Quản trị được xác định bằng vai trò.
            # Không ràng buộc commune_id/school_id vì dữ liệu lịch sử
            # có thể còn giá trị phạm vi cũ trên tài khoản cấp tỉnh.
            pass

        elif scope == "XA":
            selected_commune_id = _safe_id(commune_id)
            if selected_commune_id is None:
                return _json_no_store(
                    {"ok": True, "items": []}
                )
            # Tài khoản xã được xác định bởi vai trò XA + xã đã chọn.
            # Không bắt buộc school_id phải NULL để tương thích dữ liệu cũ.
            stmt = stmt.where(
                User.commune_id == selected_commune_id,
            )

        elif scope in {"TRUONG", "GIAO_VIEN"}:
'''

MARKER = "Tài khoản cấp Sở/Quản trị được xác định bằng vai trò."


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
    auth_path = root / "app" / "routers" / "auth.py"
    db_path = root / "data" / "phocap.db"

    if not auth_path.is_file():
        root = Path.cwd()
        auth_path = root / "app" / "routers" / "auth.py"
        db_path = root / "data" / "phocap.db"

    print(
        "BÀI 13B-11-16.2 V2.2 - "
        "SỬA TÀI KHOẢN CẤP SỞ VÀ XÃ/PHƯỜNG"
    )
    print("=" * 100)
    print(f"Dự án: {root}")

    if not auth_path.is_file():
        print(
            "DỪNG AN TOÀN: không tìm thấy "
            "app/routers/auth.py"
        )
        return 2

    text = auth_path.read_text(encoding="utf-8")

    if MARKER in text:
        print()
        print(
            "V2.2 đã có trong mã nguồn. "
            "Không cài lặp."
        )
        return 0

    current_hash = normalized_sha256(auth_path)
    print(f"app/routers/auth.py: {current_hash}")

    if current_hash != EXPECTED_NORMALIZED_SHA256:
        print()
        print(
            "DỪNG AN TOÀN: auth.py đã khác "
            "bản V2 đang được sửa."
        )
        print(
            "Không tự ghi đè. Nếu anh vừa sửa thêm, "
            "hãy gửi ZIP mã nguồn mới nhất."
        )
        return 3

    count = text.count(OLD_BLOCK)
    if count != 1:
        print()
        print(
            "DỪNG AN TOÀN: không tìm thấy đúng "
            "1 khối lọc tài khoản Sở/Xã cần sửa."
        )
        print(f"Số vị trí tìm thấy: {count}")
        return 4

    integrity, fk_count = db_check(db_path)
    print(f"Database integrity_check: {integrity}")
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
            "DỪNG AN TOÀN: database chưa đạt kiểm tra."
        )
        return 5

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = (
        root
        / "exports"
        / (
            "backup_truoc_bai_13b_11_16_2_"
            "v2_2_"
            + stamp
        )
    )

    backup_auth = (
        backup_dir
        / "app"
        / "routers"
        / "auth.py"
    )
    backup_auth.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    shutil.copy2(auth_path, backup_auth)

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
        shutil.copy2(db_path, backup_db)

    print()
    print(f"Đã backup: {backup_dir}")

    new_text = text.replace(
        OLD_BLOCK,
        NEW_BLOCK,
        1,
    )

    try:
        auth_path.write_text(
            new_text,
            encoding="utf-8",
        )
        py_compile.compile(
            str(auth_path),
            doraise=True,
        )

        verify = auth_path.read_text(
            encoding="utf-8"
        )
        if MARKER not in verify:
            raise RuntimeError(
                "Không xác nhận được marker V2.2."
            )

    except Exception as exc:
        shutil.copy2(
            backup_auth,
            auth_path,
        )
        print()
        print(
            "CÀI ĐẶT LỖI - "
            "ĐÃ TỰ KHÔI PHỤC auth.py"
        )
        print(f"Lỗi: {exc}")
        return 6

    integrity_after, fk_after = db_check(db_path)

    report_path = (
        root
        / "exports"
        / (
            "bao_cao_sua_so_xa_dang_nhap_v2_2_"
            + stamp
            + ".txt"
        )
    )

    report_lines = [
        "BÁO CÁO BÀI 13B-11-16.2 V2.2",
        f"Thời gian: {datetime.now():%d/%m/%Y %H:%M:%S}",
        f"Dự án: {root}",
        "",
        "ĐÃ SỬA:",
        (
            "1. Cấp Sở/Quản trị: lấy tài khoản đang hoạt động "
            "theo vai trò ADMIN/SO/PHONG_BAN; không loại tài khoản "
            "chỉ vì dữ liệu lịch sử còn commune_id/school_id."
        ),
        (
            "2. Cấp Xã/phường: lấy tài khoản vai trò XA theo đúng "
            "xã đã chọn; không bắt buộc school_id phải NULL."
        ),
        (
            "3. Giữ nguyên chuỗi Trường: Xã -> Trường -> tài khoản."
        ),
        (
            "4. Giữ nguyên chuỗi Giáo viên: Xã -> Trường -> Giáo viên."
        ),
        "5. Không thay đổi cấu trúc database.",
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
    print("Đã sửa đúng 1 file:")
    print(" - app/routers/auth.py")
    print("Không thay đổi cấu trúc database.")
    print(f"Báo cáo: {report_path}")
    print()
    print("Khởi động lại Uvicorn rồi kiểm tra:")
    print("1. Cấp Sở/Quản trị -> gõ 'admin' hoặc 'sogddt'.")
    print("2. Xã/phường -> chọn xã -> chọn tài khoản xã.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
