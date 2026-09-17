from __future__ import annotations

import os
import shutil
import traceback
from datetime import datetime
from pathlib import Path

PROJECT = Path(os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")).resolve()
TEMPLATES = PROJECT / "app" / "templates"
STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = PROJECT / "exports" / f"backup_bai_13b_10_v3_11_{STAMP}"

OLD_TEXT = "Phân công giáo viên"
NEW_TEXT = "Giao phiếu cho giáo viên"


def clear_cache() -> None:
    app_dir = PROJECT / "app"
    for cache in app_dir.rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(cache, ignore_errors=True)


def main() -> int:
    print("=" * 100)
    print("BÀI 13B-10 V3.11 - ĐỔI TÊN NÚT")
    print("=" * 100)
    print()
    print(f"Từ : {OLD_TEXT}")
    print(f"Thành: {NEW_TEXT}")
    print()
    print("Chỉ đổi chữ hiển thị trong template.")
    print("KHÔNG đổi route, dữ liệu, quyền, phân công hoặc luồng xử lý.")
    print()

    if not TEMPLATES.exists():
        raise RuntimeError(f"Không tìm thấy thư mục template: {TEMPLATES}")

    candidates = []
    for path in TEMPLATES.rglob("*.html"):
        text = path.read_text(encoding="utf-8-sig")
        if OLD_TEXT in text:
            candidates.append((path, text.count(OLD_TEXT)))

    if not candidates:
        raise RuntimeError(
            f"Không tìm thấy chuỗi '{OLD_TEXT}' trong app/templates. "
            "Dừng để tránh sửa nhầm."
        )

    print("Tìm thấy:")
    for path, count in candidates:
        print(f" - {path.relative_to(PROJECT)}: {count} chỗ")

    BACKUP.mkdir(parents=True, exist_ok=False)

    changed = []
    try:
        for path, _ in candidates:
            rel = path.relative_to(PROJECT)
            backup_path = BACKUP / rel
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, backup_path)

            text = path.read_text(encoding="utf-8-sig")
            new_text = text.replace(OLD_TEXT, NEW_TEXT)
            path.write_text(new_text, encoding="utf-8")
            changed.append(path)

        # Verify
        remaining = []
        new_count = 0
        for path, _ in candidates:
            text = path.read_text(encoding="utf-8-sig")
            if OLD_TEXT in text:
                remaining.append(path)
            new_count += text.count(NEW_TEXT)

        if remaining:
            raise RuntimeError(
                "Sau khi sửa vẫn còn chuỗi cũ trong: "
                + ", ".join(str(p) for p in remaining)
            )

        if new_count < 1:
            raise RuntimeError("Không xác nhận được chuỗi mới sau khi sửa.")

        clear_cache()

        print()
        print("CAI DAT BAI 13B-10 V3.11 THANH CONG")
        print("Backup:", BACKUP)
        print()
        print("Sau khi khởi động lại, nút sẽ hiển thị:")
        print(f"  {NEW_TEXT}")
        return 0

    except Exception:
        traceback.print_exc()
        print()
        print("CÓ LỖI - ĐANG KHÔI PHỤC...")
        for path in changed:
            rel = path.relative_to(PROJECT)
            backup_path = BACKUP / rel
            if backup_path.exists():
                shutil.copy2(backup_path, path)
        clear_cache()
        print("ĐÃ KHÔI PHỤC TEMPLATE TRƯỚC V3.11.")
        print("Backup:", BACKUP)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
