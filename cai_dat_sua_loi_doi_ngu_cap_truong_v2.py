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
BACKUP_DIR = PROJECT / "exports" / f"backup_sua_loi_doi_ngu_cap_truong_v2_{STAMP}"
BACKUP_FILE = BACKUP_DIR / "app" / "routers" / "staff_management.py"

NEEDED_1 = '"teaching_level_labels": TEACHING_LEVEL_LABELS'
NEEDED_2 = '"qualification_level_labels": QUALIFICATION_LEVEL_LABELS'


def read_text(path: Path) -> str:
    if not path.exists():
        raise RuntimeError(f"Không tìm thấy tệp: {path}")
    return path.read_text(encoding="utf-8-sig")


def backup() -> None:
    BACKUP_FILE.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(TARGET, BACKUP_FILE)


def restore() -> None:
    if BACKUP_FILE.exists():
        shutil.copy2(BACKUP_FILE, TARGET)


def patch_context(text: str) -> str:
    # Nếu đã có đủ 2 biến thì không sửa lặp.
    if NEEDED_1 in text and NEEDED_2 in text:
        return text

    # Ưu tiên chèn ngay sau teaching_age_labels.
    pattern = re.compile(
        r'(?P<indent>[ \t]*)"teaching_age_labels"\s*:\s*TEACHING_AGE_LABELS\s*,'
    )
    match = pattern.search(text)

    if match:
        indent = match.group("indent")
        insertion = match.group(0)

        if NEEDED_1 not in text:
            insertion += f'\n{indent}"teaching_level_labels": TEACHING_LEVEL_LABELS,'
        if NEEDED_2 not in text:
            insertion += f'\n{indent}"qualification_level_labels": QUALIFICATION_LEVEL_LABELS,'

        text = text[:match.start()] + insertion + text[match.end():]
        return text

    # Fallback: chèn trước qualification_standard_labels.
    pattern2 = re.compile(
        r'(?P<indent>[ \t]*)"qualification_standard_labels"\s*:\s*QUALIFICATION_STANDARD_LABELS\s*,'
    )
    match2 = pattern2.search(text)

    if match2:
        indent = match2.group("indent")
        insertion = ""

        if NEEDED_1 not in text:
            insertion += f'{indent}"teaching_level_labels": TEACHING_LEVEL_LABELS,\n'
        if NEEDED_2 not in text:
            insertion += f'{indent}"qualification_level_labels": QUALIFICATION_LEVEL_LABELS,\n'

        text = text[:match2.start()] + insertion + text[match2.start():]
        return text

    raise RuntimeError(
        "Không tìm thấy vị trí an toàn để bổ sung context cho staff/list.html. "
        "Không có tệp nào bị thay đổi."
    )


def verify(text: str) -> None:
    if NEEDED_1 not in text:
        raise RuntimeError("Sau sửa vẫn thiếu teaching_level_labels.")
    if NEEDED_2 not in text:
        raise RuntimeError("Sau sửa vẫn thiếu qualification_level_labels.")

    # Kiểm tra các constant phải tồn tại trong router.
    if "TEACHING_LEVEL_LABELS" not in text:
        raise RuntimeError("Router không có TEACHING_LEVEL_LABELS.")
    if "QUALIFICATION_LEVEL_LABELS" not in text:
        raise RuntimeError("Router không có QUALIFICATION_LEVEL_LABELS.")


def clear_cache() -> None:
    app_dir = PROJECT / "app"
    for cache in app_dir.rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(cache, ignore_errors=True)


def main() -> int:
    print("=" * 100)
    print("SỬA LỖI ĐỘI NGŨ CẤP TRƯỜNG V2")
    print("=" * 100)
    print("")
    print("Lỗi đã xác định chính xác từ traceback:")
    print("  jinja2.exceptions.UndefinedError: 'teaching_level_labels' is undefined")
    print("")
    print("Nguyên nhân:")
    print("  staff/list.html đang dùng teaching_level_labels và qualification_level_labels")
    print("  nhưng route /doi-ngu chưa truyền 2 biến này vào context Jinja.")
    print("")
    print("Bản này CHỈ sửa lỗi context nói trên.")
    print("Không sửa database, dữ liệu, báo cáo, điều tra hộ dân hoặc giao diện điện thoại.")
    print("")

    before = read_text(TARGET)
    backup()

    try:
        after = patch_context(before)
        verify(after)

        TARGET.write_text(after, encoding="utf-8")

        subprocess.run(
            [sys.executable, "-m", "py_compile", str(TARGET)],
            cwd=PROJECT,
            check=True,
        )

        clear_cache()

        print("")
        print("SỬA LỖI ĐỘI NGŨ CẤP TRƯỜNG V2 THÀNH CÔNG")
        print("Backup:", BACKUP_DIR)
        print("")
        print("Sau khi khởi động lại, kiểm tra:")
        print("  http://127.0.0.1/doi-ngu")
        return 0

    except Exception:
        traceback.print_exc()
        print("")
        print("CÓ LỖI - ĐANG KHÔI PHỤC...")
        restore()
        clear_cache()
        print("ĐÃ KHÔI PHỤC staff_management.py VỀ TRƯỚC KHI CÀI.")
        print("Backup:", BACKUP_DIR)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
