from __future__ import annotations

import os
import shutil
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path

PROJECT = Path(os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")).resolve()
APP = PROJECT / "app"
ROUTER = APP / "routers" / "survey_team_registration.py"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = PROJECT / "exports" / f"backup_bai_13b_10_v2_1_{STAMP}"
BACKUP_ROUTER = BACKUP / "app" / "routers" / "survey_team_registration.py"

MARKER = "BAI_13B_10_V2_1_NO_EMPTY_TEAM"

OLD = """    team_count = min(
        len(by_level["MN"]),
        len(by_level["TH"]),
        len(by_level["THCS"]),
    )
"""

NEW = """    # === BAI_13B_10_V2_1_NO_EMPTY_TEAM ===
    # Số tổ không được vượt số hộ/phiếu.
    # Ví dụ 6 GV mỗi cấp nhưng chỉ có 5 hộ thì chỉ lập 5 tổ,
    # 3 GV còn lại (1 MN + 1 TH + 1 THCS) nằm ở Dự phòng.
    team_count = min(
        len(by_level["MN"]),
        len(by_level["TH"]),
        len(by_level["THCS"]),
        len(forms),
    )
"""


def read_text(path: Path) -> str:
    if not path.exists():
        raise RuntimeError(f"Không tìm thấy tệp: {path}")
    return path.read_text(encoding="utf-8-sig")


def backup() -> None:
    BACKUP_ROUTER.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROUTER, BACKUP_ROUTER)


def restore() -> None:
    if BACKUP_ROUTER.exists():
        shutil.copy2(BACKUP_ROUTER, ROUTER)


def clear_cache() -> None:
    for cache in APP.rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(cache, ignore_errors=True)


def patch(text_value: str) -> str:
    if MARKER in text_value:
        print(" - V2.1 đã có, không sửa lặp.")
        return text_value

    if "BAI_13B_10_V2_RANDOM_TEAMS_START" not in text_value:
        raise RuntimeError(
            "Chưa thấy nền Bài 13B-10 V2 trong survey_team_registration.py."
        )

    if OLD not in text_value:
        raise RuntimeError(
            "Không tìm thấy công thức team_count của V2 đúng như dự kiến. "
            "Dừng để tránh sửa nhầm."
        )

    return text_value.replace(OLD, NEW, 1)


def verify(text_value: str) -> None:
    required = [
        MARKER,
        'len(by_level["MN"])',
        'len(by_level["TH"])',
        'len(by_level["THCS"])',
        "len(forms)",
    ]
    for marker in required:
        if marker not in text_value:
            raise RuntimeError(f"Thiếu nội dung sau sửa: {marker}")

    if text_value.count(MARKER) != 1:
        raise RuntimeError("Marker V2.1 không đúng 1 lần.")

    subprocess.run(
        [sys.executable, "-m", "py_compile", str(ROUTER)],
        cwd=PROJECT,
        check=True,
    )


def main() -> int:
    print("=" * 105)
    print("BÀI 13B-10 V2.1 - KHÔNG TẠO TỔ ĐIỀU TRA RỖNG")
    print("=" * 105)
    print("")
    print("DỮ LIỆU THỬ HIỆN TẠI:")
    print(" - 6 GV MN, 6 GV TH, 6 GV THCS")
    print(" - 5 hộ/phiếu")
    print(" - V2 đang tạo 6 tổ nên có 1 tổ 0 hộ.")
    print("")
    print("V2.1 sửa:")
    print(" Số tổ = min(GV MN, GV TH, GV THCS, SỐ HỘ/PHIẾU)")
    print("")
    print("Với dữ liệu thử hiện tại sẽ tạo 5 tổ, mỗi tổ 1 hộ;")
    print("1 GV mỗi cấp còn lại nằm ở danh sách Dự phòng.")
    print("")
    print("KHÔNG SỬA database và không đụng dữ liệu hộ.")
    print("")

    backup()

    try:
        before = read_text(ROUTER)
        after = patch(before)
        verify(after)

        ROUTER.write_text(after, encoding="utf-8")
        clear_cache()
        verify(read_text(ROUTER))

        print("")
        print("CAI DAT BAI 13B-10 V2.1 THANH CONG")
        print("Backup:", BACKUP)
        print("")
        print("Sau khi khởi động lại:")
        print(" 1. Vào Lập tổ điều tra 3 cấp.")
        print(" 2. Bấm 'Tạo lại ngẫu nhiên'.")
        print(" 3. Với 5 hộ hiện tại phải còn 5 tổ, mỗi tổ 1 hộ.")
        print(" 4. Dự phòng phải có 3 GV: 1 MN + 1 TH + 1 THCS.")
        return 0

    except Exception:
        traceback.print_exc()
        print("")
        print("CÓ LỖI - ĐANG KHÔI PHỤC...")
        restore()
        clear_cache()
        print("ĐÃ KHÔI PHỤC survey_team_registration.py.")
        print("Backup:", BACKUP)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
