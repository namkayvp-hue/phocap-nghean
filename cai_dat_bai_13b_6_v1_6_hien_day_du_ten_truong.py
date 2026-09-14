from __future__ import annotations

import base64
import gzip
import hashlib
import json
import os
import shutil
import traceback
from datetime import datetime
from pathlib import Path

PROJECT = Path(os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")).resolve()
TARGET = PROJECT / "app" / "templates" / "schools" / "list.html"
EXPECTED_HASH = '58ac5289f1b466903620562b46e78d8bf35afc24e94f526ba8dc74cecd584bf7'
PAYLOAD = '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'

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = PROJECT / "exports" / f"backup_bai_13b_6_v1_6_hien_day_du_ten_truong_{STAMP}"
MANIFEST = BACKUP / "manifest.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    print("=" * 96)
    print("BÀI 13B-6 V1.6 - HIỂN THỊ ĐẦY ĐỦ TÊN ĐƠN VỊ/TRƯỜNG")
    print("=" * 96)
    print("")
    print("Sửa giao diện Danh mục trường MN / Tiểu học / THCS:")
    print(" - Bảng chiếm toàn bộ chiều ngang màn hình.")
    print(" - Tên trường hiển thị đầy đủ, tự xuống dòng.")
    print(" - Không cắt mất tên đơn vị dài.")
    print(" - Vẫn giữ đủ Mã trường, Xã/phường, Địa chỉ, Trạng thái, Thao tác.")
    print("")

    if not TARGET.exists():
        raise RuntimeError(f"Không tìm thấy {TARGET}")

    current = sha256(TARGET)
    if current != EXPECTED_HASH:
        print("DỪNG AN TOÀN: schools/list.html đã khác source dùng để tạo bản vá.")
        print("Không có tệp nào bị thay đổi.")
        print("Expected:", EXPECTED_HASH)
        print("Actual  :", current)
        return 2

    BACKUP.mkdir(parents=True, exist_ok=False)
    backup_target = BACKUP / "app" / "templates" / "schools" / "list.html"
    backup_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(TARGET, backup_target)
    MANIFEST.write_text(
        json.dumps([{"path": "app/templates/schools/list.html", "existed": True}],
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    try:
        TARGET.write_bytes(gzip.decompress(base64.b64decode(PAYLOAD)))

        from jinja2 import Environment
        text = TARGET.read_text(encoding="utf-8-sig")
        Environment().parse(text)

        required = [
            "BAI_13B_6_V1_6_HIEN_DAY_DU_TEN_TRUONG",
            "grid-column: 1 / -1",
            "min-width: 300px",
            "overflow-wrap: anywhere",
        ]
        for item in required:
            if item not in text:
                raise RuntimeError(f"Kiểm tra sau cài không đạt: {item}")

        print("")
        print("CAI DAT BAI 13B-6 V1.6 HIEN DAY DU TEN TRUONG THANH CONG")
        print("Backup:", BACKUP)
        return 0

    except Exception:
        traceback.print_exc()
        shutil.copy2(backup_target, TARGET)
        print("")
        print("CÓ LỖI - ĐÃ KHÔI PHỤC schools/list.html TỰ ĐỘNG.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
