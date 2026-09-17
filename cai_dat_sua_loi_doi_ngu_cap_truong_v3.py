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
TARGET = PROJECT / "app" / "routers" / "staff_management.py"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP_DIR = PROJECT / "exports" / f"backup_sua_loi_doi_ngu_cap_truong_v3_{STAMP}"
BACKUP_FILE = BACKUP_DIR / "app" / "routers" / "staff_management.py"

KEY_1 = '"teaching_level_labels": TEACHING_LEVEL_LABELS'
KEY_2 = '"qualification_level_labels": QUALIFICATION_LEVEL_LABELS'


def read_text(path: Path) -> str:
    if not path.exists():
        raise RuntimeError(f"Không tìm thấy tệp: {path}")
    return path.read_text(encoding="utf-8-sig")


def backup() -> None:
    BACKUP_FILE.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(TARGET, BACKUP_FILE)


def restore() -> None:
    if BACKUP_FILE.exists():
        TARGET.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(BACKUP_FILE, TARGET)


def locate_list_route(text: str) -> tuple[int, int]:
    """
    Tìm CHÍNH XÁC route đang render staff/list.html.
    V2 bị lỗi vì chỉ thấy 2 key ở một context khác trong cùng file rồi tưởng đã sửa.
    """
    m = re.search(r'name\s*=\s*["\']staff/list\.html["\']', text)
    if not m:
        raise RuntimeError('Không tìm thấy name="staff/list.html" trong staff_management.py.')

    route_start = text.rfind("@router.get", 0, m.start())
    if route_start < 0:
        raise RuntimeError("Không tìm thấy đầu route /doi-ngu chứa staff/list.html.")

    next_route = text.find("\n@router.", m.end())
    route_end = next_route if next_route >= 0 else len(text)

    block = text[route_start:route_end]
    if "TemplateResponse" not in block or "staff/list.html" not in block:
        raise RuntimeError("Khối xác định được không phải route danh sách đội ngũ.")

    return route_start, route_end


def patch_list_context(text: str) -> str:
    start, end = locate_list_route(text)
    block = text[start:end]

    missing_1 = KEY_1 not in block
    missing_2 = KEY_2 not in block

    if not missing_1 and not missing_2:
        print("Route staff/list.html đã có đủ 2 biến. Không chèn lặp.")
        return text

    # Chèn ngay trong context của route staff/list.html, ưu tiên sau employment_labels.
    anchors = [
        r'(?P<indent>[ \t]*)"employment_labels"\s*:\s*EMPLOYMENT_LABELS\s*,',
        r'(?P<indent>[ \t]*)"teaching_age_labels"\s*:\s*TEACHING_AGE_LABELS\s*,',
        r'(?P<indent>[ \t]*)"status_labels"\s*:\s*STATUS_LABELS\s*,',
    ]

    match = None
    for pattern in anchors:
        match = re.search(pattern, block)
        if match:
            break

    if not match:
        raise RuntimeError(
            "Không tìm thấy điểm chèn an toàn bên trong context staff/list.html."
        )

    indent = match.group("indent")
    insertion = match.group(0)

    if missing_1:
        insertion += f'\n{indent}"teaching_level_labels": TEACHING_LEVEL_LABELS,'
    if missing_2:
        insertion += f'\n{indent}"qualification_level_labels": QUALIFICATION_LEVEL_LABELS,'

    block = block[:match.start()] + insertion + block[match.end():]
    return text[:start] + block + text[end:]


def verify_exact_route(text: str) -> None:
    start, end = locate_list_route(text)
    block = text[start:end]

    if KEY_1 not in block:
        raise RuntimeError(
            "Route staff/list.html vẫn thiếu teaching_level_labels sau khi sửa."
        )
    if KEY_2 not in block:
        raise RuntimeError(
            "Route staff/list.html vẫn thiếu qualification_level_labels sau khi sửa."
        )

    # Kiểm tra các constant nguồn có thật.
    if re.search(r"^TEACHING_LEVEL_LABELS\s*=", text, re.MULTILINE) is None:
        raise RuntimeError("Không tìm thấy constant TEACHING_LEVEL_LABELS.")
    if re.search(r"^QUALIFICATION_LEVEL_LABELS\s*=", text, re.MULTILINE) is None:
        raise RuntimeError("Không tìm thấy constant QUALIFICATION_LEVEL_LABELS.")


def clear_cache() -> None:
    app_dir = PROJECT / "app"
    for cache in app_dir.rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(cache, ignore_errors=True)


def main() -> int:
    print("=" * 104)
    print("SỬA LỖI ĐỘI NGŨ CẤP TRƯỜNG V3 - CHÈN ĐÚNG CONTEXT staff/list.html")
    print("=" * 104)
    print("")
    print("ĐÃ XÁC ĐỊNH NGUYÊN NHÂN:")
    print(" - Traceback vẫn báo: teaching_level_labels is undefined.")
    print(" - V2 đã thêm key vào staff_management.py, nhưng nằm ở CONTEXT KHÁC.")
    print(" - Route thật render staff/list.html vẫn chưa nhận 2 biến cần thiết.")
    print("")
    print("V3 SẼ:")
    print(" - Tìm chính xác route có name='staff/list.html'.")
    print(" - Chỉ trong route đó, thêm:")
    print("     teaching_level_labels = TEACHING_LEVEL_LABELS")
    print("     qualification_level_labels = QUALIFICATION_LEVEL_LABELS")
    print(" - Không sửa database.")
    print(" - Không sửa /doi-ngu/them đang chạy tốt.")
    print(" - Không sửa báo cáo, CSVC, điều tra hộ dân, điện thoại.")
    print("")

    before = read_text(TARGET)

    # In kiểm tra trước cài để người dùng thấy rõ.
    start, end = locate_list_route(before)
    route_before = before[start:end]
    print("KIỂM TRA ROUTE staff/list.html TRƯỚC CÀI:")
    print(" - teaching_level_labels trong đúng route:", KEY_1 in route_before)
    print(" - qualification_level_labels trong đúng route:", KEY_2 in route_before)
    print("")

    backup()

    try:
        after = patch_list_context(before)
        verify_exact_route(after)

        TARGET.write_text(after, encoding="utf-8")

        subprocess.run(
            [sys.executable, "-m", "py_compile", str(TARGET)],
            cwd=PROJECT,
            check=True,
        )

        clear_cache()

        # Đọc lại từ đĩa để xác nhận, không chỉ kiểm tra biến trong RAM.
        disk_text = read_text(TARGET)
        verify_exact_route(disk_text)

        start2, end2 = locate_list_route(disk_text)
        route_after = disk_text[start2:end2]

        print("")
        print("KIỂM TRA ROUTE staff/list.html SAU CÀI:")
        print(" - teaching_level_labels:", KEY_1 in route_after)
        print(" - qualification_level_labels:", KEY_2 in route_after)
        print("")
        print("SỬA LỖI ĐỘI NGŨ CẤP TRƯỜNG V3 THÀNH CÔNG")
        print("Backup:", BACKUP_DIR)
        print("")
        print("Khởi động lại Uvicorn rồi mở: http://127.0.0.1/doi-ngu")
        return 0

    except Exception:
        traceback.print_exc()
        print("")
        print("CÓ LỖI - ĐANG KHÔI PHỤC...")
        restore()
        clear_cache()
        print("ĐÃ KHÔI PHỤC staff_management.py VỀ TRƯỚC V3.")
        print("Backup:", BACKUP_DIR)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
