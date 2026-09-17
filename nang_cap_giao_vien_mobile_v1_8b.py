from __future__ import annotations

import os
import shutil
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path

PROJECT = Path(
    os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")
).resolve()

MAIN = PROJECT / "app" / "main.py"
SURVEY_INDEX = PROJECT / "app" / "templates" / "surveys" / "index.html"
HOUSEHOLDS = PROJECT / "app" / "templates" / "surveys" / "households.html"
QUICK_ENTRY = PROJECT / "app" / "templates" / "surveys" / "quick_entry.html"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = PROJECT / "exports" / f"backup_giao_vien_mobile_v1_8b_{STAMP}"

START = "    # === GV_MOBILE_V18B_ROOT_REDIRECT_START ==="
END = "    # === GV_MOBILE_V18B_ROOT_REDIRECT_END ==="

NEW_BLOCK = '    # === GV_MOBILE_V18B_ROOT_REDIRECT_START ===\n    # Chỉ áp dụng cho tài khoản giáo viên trên thiết bị di động.\n    # Không thay đổi giao diện/luồng của ADMIN, SỞ, XÃ, TRƯỜNG hoặc máy tính.\n    role_code = str(\n        (nguoi_dung or {}).get("role_code") or ""\n    ).strip().upper()\n\n    user_agent = str(\n        request.headers.get("user-agent") or ""\n    ).lower()\n\n    mobile_tokens = (\n        "iphone",\n        "ipad",\n        "ipod",\n        "android",\n        "mobile",\n        "windows phone",\n    )\n    is_mobile_device = any(\n        token in user_agent\n        for token in mobile_tokens\n    )\n\n    if role_code == "GIAO_VIEN" and is_mobile_device:\n        return RedirectResponse(\n            url="/dieu-tra",\n            status_code=303,\n        )\n    # === GV_MOBILE_V18B_ROOT_REDIRECT_END ===\n'

def strip_old_block(text: str) -> str:
    while START in text and END in text:
        a = text.index(START)
        b = text.index(END, a) + len(END)
        if text[b:b+2] == "\r\n":
            b += 2
        elif text[b:b+1] == "\n":
            b += 1
        text = text[:a] + text[b:]
    return text

def require_file(path: Path) -> str:
    if not path.exists():
        raise RuntimeError(f"Không tìm thấy tệp bắt buộc: {path}")
    return path.read_text(encoding="utf-8-sig")

def main() -> int:
    print("=" * 78)
    print("GIAO VIEN MOBILE V1.8B")
    print("SUA DUNG NGUYEN NHAN TRANG CHU DIEN THOAI VAN CON MENU")
    print("=" * 78)

    main_text = require_file(MAIN)
    survey_index_text = require_file(SURVEY_INDEX)
    households_text = require_file(HOUSEHOLDS)
    quick_entry_text = require_file(QUICK_ENTRY)

    required_markers = [
        ("Chọn năm + Phiếu phân công", survey_index_text, "GV_MOBILE_V18_HOME_START"),
        ("Số phiếu - Tên hộ - Nhập nhanh", households_text, "GV_MOBILE_V18_ASSIGNMENTS_START"),
        ("Nhập nhanh tối giản", quick_entry_text, "GV_MOBILE_V18_QUICK_START"),
    ]
    for label, text, marker in required_markers:
        if marker not in text:
            raise RuntimeError(
                f"Chưa tìm thấy phần đã làm: {label}. "
                "Dừng cài để không làm thay đổi sai mã nguồn."
            )

    if "def trang_chu(" not in main_text:
        raise RuntimeError("Không tìm thấy route Trang chủ trong app/main.py.")

    anchor = '    nguoi_dung = request.scope.get("auth_user")'
    if anchor not in main_text:
        raise RuntimeError("Không tìm thấy điểm chèn an toàn trong hàm trang_chu.")

    BACKUP.mkdir(parents=True, exist_ok=False)
    backup_main = BACKUP / "app" / "main.py"
    backup_main.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(MAIN, backup_main)

    try:
        text = strip_old_block(main_text)

        import_line = "from fastapi.responses import HTMLResponse"
        import_line_new = "from fastapi.responses import HTMLResponse, RedirectResponse"

        if import_line_new not in text:
            if import_line not in text:
                raise RuntimeError(
                    "Không tìm thấy import HTMLResponse đúng như mã nguồn hiện tại."
                )
            text = text.replace(import_line, import_line_new, 1)

        text = text.replace(
            anchor,
            anchor + "\n\n" + NEW_BLOCK.rstrip(),
            1,
        )

        MAIN.write_text(text, encoding="utf-8")

        subprocess.run(
            [sys.executable, "-m", "py_compile", str(MAIN)],
            cwd=str(PROJECT),
            check=True,
        )

        check = MAIN.read_text(encoding="utf-8")
        checks = [
            "GV_MOBILE_V18B_ROOT_REDIRECT_START",
            'role_code == "GIAO_VIEN" and is_mobile_device',
            'url="/dieu-tra"',
            "HTMLResponse, RedirectResponse",
        ]
        for item in checks:
            if item not in check:
                raise RuntimeError(f"Kiểm tra sau cài đặt không đạt: {item}")

        for cache_dir in (PROJECT / "app").rglob("__pycache__"):
            if cache_dir.is_dir():
                shutil.rmtree(cache_dir, ignore_errors=True)

        print("")
        print("CAC PHAN DA LAM DUOC GIU NGUYEN:")
        print(" - Chon nam + Phieu phan cong")
        print(" - So phieu - Ten ho - Nhap nhanh")
        print(" - Thanh vien - Truong - Lop - Sua - Chap nhan")
        print(" - Them thanh vien - Hoan thanh - Ho tiep theo")
        print("")
        print("PHAN MOI V1.8B:")
        print(" - GIAO_VIEN + DIEN THOAI vao Trang chu -> /dieu-tra")
        print(" - Desktop: KHONG DOI")
        print(" - Vai tro khac: KHONG DOI")
        print(" - Database: KHONG DOI")
        print("")
        print("CAI DAT GIAO VIEN MOBILE V1.8B THANH CONG")
        print("Backup:", BACKUP)
        return 0

    except Exception:
        traceback.print_exc()
        if backup_main.exists():
            shutil.copy2(backup_main, MAIN)
        print("")
        print("CO LOI - DA KHOI PHUC app/main.py TU DONG.")
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
