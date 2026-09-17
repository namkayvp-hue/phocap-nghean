from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path

PROJECT = Path(os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")).resolve()
ROUTER = PROJECT / "app" / "routers" / "report_inputs.py"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = PROJECT / "exports" / f"backup_bai_13b_6_v1_4_1_mo_quyen_mn01gv_xa_{STAMP}"
BACKUP_ROUTER = BACKUP / "app" / "routers" / "report_inputs.py"

SUCCESS_LINE = "CAI DAT BAI 13B-6 V1.4.1 MO QUYEN NHAP MN-01-GV CHO XA THANH CONG"


def read_text(path: Path) -> str:
    if not path.exists():
        raise RuntimeError(f"Không tìm thấy tệp bắt buộc: {path}")
    return path.read_text(encoding="utf-8-sig")


def backup() -> None:
    BACKUP_ROUTER.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROUTER, BACKUP_ROUTER)


def restore() -> None:
    if BACKUP_ROUTER.exists():
        ROUTER.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(BACKUP_ROUTER, ROUTER)


def patch_gv_edit_roles(text: str) -> str:
    required_markers = [
        'GV_EDIT_ROLES',
        'COMMUNE_ROLE_CODE',
        'SCHOOL_ROLE_CODE',
        '@router.get("/doi-ngu/nhap-mn-01-gv"',
        '@router.post("/doi-ngu/nhap-mn-01-gv")',
    ]
    for marker in required_markers:
        if marker not in text:
            raise RuntimeError(
                f"Source hiện tại thiếu marker bắt buộc: {marker}. "
                "Dừng cài để không sửa nhầm mã nguồn."
            )

    pattern = re.compile(
        r'GV_EDIT_ROLES\s*=\s*frozenset\(\{(?P<body>.*?)\}\)',
        flags=re.S,
    )
    match = pattern.search(text)
    if not match:
        raise RuntimeError(
            "Không tìm thấy khai báo GV_EDIT_ROLES theo cấu trúc hiện tại."
        )

    body = match.group("body")

    if "COMMUNE_ROLE_CODE" in body:
        return text

    # Chèn quyền Xã/phường trước SCHOOL_ROLE_CODE nếu có.
    if "SCHOOL_ROLE_CODE" in body:
        new_body = body.replace(
            "SCHOOL_ROLE_CODE",
            "COMMUNE_ROLE_CODE, SCHOOL_ROLE_CODE",
            1,
        )
    else:
        new_body = body.rstrip() + ", COMMUNE_ROLE_CODE"

    replacement = f"GV_EDIT_ROLES = frozenset({{{new_body}}})"
    return text[:match.start()] + replacement + text[match.end():]


def verify(text: str) -> None:
    pattern = re.compile(
        r'GV_EDIT_ROLES\s*=\s*frozenset\(\{(?P<body>.*?)\}\)',
        flags=re.S,
    )
    match = pattern.search(text)
    if not match:
        raise RuntimeError("Không đọc lại được GV_EDIT_ROLES sau khi sửa.")

    body = match.group("body")
    for marker in (
        "ADMIN_ROLE_CODES",
        "COMMUNE_ROLE_CODE",
        "SCHOOL_ROLE_CODE",
    ):
        if marker not in body:
            raise RuntimeError(
                f"GV_EDIT_ROLES sau sửa thiếu quyền bắt buộc: {marker}"
            )

    if '"can_edit": scope["role_code"] in GV_EDIT_ROLES' not in text:
        raise RuntimeError(
            "Không tìm thấy cơ chế can_edit của màn hình MN-01-GV."
        )

    if "if role not in GV_EDIT_ROLES" not in text:
        raise RuntimeError(
            "Không tìm thấy kiểm tra quyền lưu MN-01-GV ở backend."
        )


def compile_router() -> None:
    subprocess.run(
        [sys.executable, "-m", "py_compile", str(ROUTER)],
        cwd=PROJECT,
        check=True,
    )


def clear_cache() -> None:
    app_dir = PROJECT / "app"
    for cache in app_dir.rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(cache, ignore_errors=True)


def main() -> int:
    print("=" * 100)
    print("BÀI 13B-6 V1.4.1 - MỞ QUYỀN NHẬP CHI TIẾT MN-01-GV CHO TÀI KHOẢN XÃ/PHƯỜNG")
    print("=" * 100)
    print("")
    print("MỤC TIÊU:")
    print(" - Tài khoản Xã/phường đang xem được MN-01-GV nhưng các ô chi tiết đang bị khóa.")
    print(" - Bổ sung COMMUNE_ROLE_CODE vào GV_EDIT_ROLES.")
    print(" - Sau sửa, Xã/phường được sửa và lưu chi tiết giáo viên của các trường thuộc đúng phạm vi xã.")
    print("")
    print("KHÔNG THAY ĐỔI:")
    print(" - Database và dữ liệu đã nhập.")
    print(" - Danh sách nhân sự hiện có.")
    print(" - Tiểu học, THCS.")
    print(" - CSVC, Báo cáo, Điều tra hộ dân, giao diện điện thoại.")
    print(" - Quyền của Trường và Quản trị hiện có.")
    print("")

    before = read_text(ROUTER)
    backup()

    try:
        after = patch_gv_edit_roles(before)
        verify(after)

        if after != before:
            ROUTER.write_text(after, encoding="utf-8")
        else:
            print("GV_EDIT_ROLES đã có COMMUNE_ROLE_CODE; không cần ghi lại nội dung.")

        compile_router()
        clear_cache()

        print("")
        print("KẾT QUẢ:")
        print(" - Đã mở quyền nhập chi tiết MN-01-GV cho tài khoản Xã/phường.")
        print(" - Frontend sẽ hết disabled vì can_edit=True.")
        print(" - Backend POST cũng chấp nhận lưu vì dùng cùng GV_EDIT_ROLES.")
        print(" - Phạm vi trường vẫn do cơ chế _school_in_scope kiểm soát.")
        print("")
        print("Backup:", BACKUP)
        print("")
        print(SUCCESS_LINE)
        return 0

    except Exception:
        traceback.print_exc()
        print("")
        print("CÓ LỖI - ĐANG KHÔI PHỤC...")
        restore()
        print("ĐÃ KHÔI PHỤC report_inputs.py VỀ TRƯỚC V1.4.1.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
