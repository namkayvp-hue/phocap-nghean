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
APP = PROJECT / "app"
SURVEYS = APP / "routers" / "surveys.py"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = PROJECT / "exports" / f"backup_bai_13b_10_v3_6_{STAMP}"

MARKER = "BAI_13B_10_V3_6_IGNORE_COMMUNE_FOR_SCHOOL_TEACHER"


def read_text(path: Path) -> str:
    if not path.exists():
        raise RuntimeError(f"Không tìm thấy tệp: {path}")
    return path.read_text(encoding="utf-8-sig")


def backup_file(path: Path) -> None:
    dst = BACKUP / path.relative_to(PROJECT)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, dst)


def restore_file(path: Path) -> None:
    src = BACKUP / path.relative_to(PROJECT)
    if src.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, path)


def clear_cache() -> None:
    for cache in APP.rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(cache, ignore_errors=True)


def function_block(text_value: str, name: str) -> tuple[int, int, str]:
    match = re.search(
        rf"^def\s+{re.escape(name)}\s*\(",
        text_value,
        flags=re.MULTILINE,
    )
    if not match:
        raise RuntimeError(f"Không tìm thấy hàm {name} trong surveys.py")

    start = match.start()

    next_route = re.search(
        r"^@router\.",
        text_value[match.end():],
        flags=re.MULTILINE,
    )
    end = (
        match.end() + next_route.start()
        if next_route
        else len(text_value)
    )
    return start, end, text_value[start:end]


def patch_list_route(text_value: str) -> str:
    start, end, block = function_block(
        text_value,
        "danh_sach_dot_dieu_tra",
    )

    if MARKER in block:
        return text_value

    # Xác nhận đúng route cần sửa.
    required = [
        "filters = tao_bo_loc_dot_theo_nguoi_dung(request)",
        "SurveyBatch.commune_id == commune_id",
        "role_code = str(user.get(\"role_code\") or \"\")",
    ]
    for item in required:
        if item not in block:
            raise RuntimeError(
                f"Route /dieu-tra không giống cấu trúc dự kiến, thiếu: {item}"
            )

    # Có thể source đang ở bản gốc:
    #   if commune_id is not None:
    # hoặc đã có V3.4:
    #   if commune_id is not None and apply_commune_filter:
    #
    # V3.6 thay bằng điều kiện trực tiếp theo role, không phụ thuộc biến trung gian.
    pattern = re.compile(
        r"(?P<indent>^[ \t]*)if\s+commune_id\s+is\s+not\s+None"
        r"(?:\s+and\s+apply_commune_filter)?\s*:\s*\n"
        r"(?P=indent)[ \t]+filters\.append\(\s*\n"
        r"(?P=indent)[ \t]+SurveyBatch\.commune_id\s*==\s*commune_id\s*\n"
        r"(?P=indent)[ \t]+\)\s*",
        flags=re.MULTILINE,
    )

    matches = list(pattern.finditer(block))
    if len(matches) != 1:
        raise RuntimeError(
            "Không xác định duy nhất khối lọc commune_id trong "
            f"danh_sach_dot_dieu_tra(); tìm thấy {len(matches)} khối."
        )

    indent = matches[0].group("indent")
    replacement = (
        f'{indent}# === {MARKER}_START ===\n'
        f'{indent}# Trường/Giáo viên đã được giới hạn bằng '
        'survey_form_investigators.\n'
        f'{indent}# Không ép thêm SurveyBatch.commune_id vì dữ liệu danh mục '
        'có thể có commune id lịch sử khác nhau.\n'
        f'{indent}if (\n'
        f'{indent}    commune_id is not None\n'
        f'{indent}    and role_code not in {{"TRUONG", "GIAO_VIEN"}}\n'
        f'{indent}):\n'
        f'{indent}    filters.append(\n'
        f'{indent}        SurveyBatch.commune_id == commune_id\n'
        f'{indent}    )\n'
        f'{indent}# === {MARKER}_END ==='
    )

    block = pattern.sub(replacement, block, count=1)

    return text_value[:start] + block + text_value[end:]


def verify() -> None:
    text_value = read_text(SURVEYS)
    _, _, block = function_block(
        text_value,
        "danh_sach_dot_dieu_tra",
    )

    required = [
        MARKER,
        'role_code not in {"TRUONG", "GIAO_VIEN"}',
        "filters = tao_bo_loc_dot_theo_nguoi_dung(request)",
        "SurveyBatch.commune_id == commune_id",
    ]
    for item in required:
        if item not in block:
            raise RuntimeError(
                f"Kiểm tra sau cài chưa đạt, thiếu: {item}"
            )

    # Phải chỉ còn điều kiện commune dành cho role khác, không được có lại
    # khối cũ "if commune_id is not None:" ngay trước filters.append.
    bad_pattern = re.compile(
        r"if\s+commune_id\s+is\s+not\s+None\s*:\s*\n"
        r"\s*filters\.append\(\s*\n"
        r"\s*SurveyBatch\.commune_id\s*==\s*commune_id",
        flags=re.MULTILINE,
    )
    if bad_pattern.search(block):
        raise RuntimeError(
            "Vẫn còn khối lọc commune_id cũ trong route /dieu-tra."
        )

    subprocess.run(
        [sys.executable, "-m", "py_compile", str(SURVEYS)],
        cwd=PROJECT,
        check=True,
    )


def main() -> int:
    print("=" * 116)
    print("BÀI 13B-10 V3.6 - SỬA DỨT ĐIỂM TRƯỜNG/GV HIỆN 0 ĐỢT")
    print("=" * 116)
    print()
    print("DỮ LIỆU V3.5 ĐÃ XÁC NHẬN:")
    print(" - 5/5 tổ đã SENT.")
    print(" - Có đủ 15 lượt phân công chính thức.")
    print(" - team_school_id và users.school_id khớp 100%.")
    print(" - THCS Hải Hòa school_id=1409 có 5 phiếu đợt #3.")
    print(" - Tiểu học Nghi Hương school_id=896 có 5 phiếu.")
    print(" - Trường MN Nghi Hải school_id=197 có 5 phiếu.")
    print()
    print("=> Database và phân công ĐÃ ĐÚNG.")
    print("=> Lỗi còn lại chỉ nằm ở route /dieu-tra.")
    print()
    print("V3.6 chỉ sửa 1 điều kiện trong danh_sach_dot_dieu_tra():")
    print(" - Xã vẫn lọc theo commune_id.")
    print(" - Trường/Giáo viên KHÔNG lọc thêm theo commune_id.")
    print(" - Trường vẫn chỉ thấy đợt có GV thuộc chính school_id của trường.")
    print(" - Giáo viên vẫn chỉ thấy đợt/phiếu gắn đúng user_id của mình.")
    print()
    print("KHÔNG sửa database.")
    print("KHÔNG sửa 5 tổ đã chốt.")
    print("KHÔNG sửa hộ dân, thành viên, Đội ngũ, báo cáo hoặc mobile.")
    print()

    if not SURVEYS.exists():
        raise RuntimeError(f"Không tìm thấy: {SURVEYS}")

    BACKUP.mkdir(parents=True, exist_ok=False)
    backup_file(SURVEYS)

    try:
        original = read_text(SURVEYS)
        patched = patch_list_route(original)
        SURVEYS.write_text(patched, encoding="utf-8")

        verify()
        clear_cache()

        print()
        print("CAI DAT BAI 13B-10 V3.6 THANH CONG")
        print("Backup:", BACKUP)
        print()
        print("SAU CÀI:")
        print(" 1. Khởi động lại Uvicorn.")
        print(" 2. Ctrl+F5.")
        print(" 3. Đăng nhập THCS Hải Hòa -> /dieu-tra.")
        print(" 4. Đợt 2026-2027 phải xuất hiện.")
        print(" 5. 2.2.1 phải thấy 5 hộ/phiếu được giao.")
        return 0

    except Exception:
        traceback.print_exc()
        print()
        print("CÓ LỖI - ĐANG KHÔI PHỤC SOURCE...")
        restore_file(SURVEYS)
        clear_cache()
        print("ĐÃ KHÔI PHỤC SOURCE TRƯỚC V3.6.")
        print("Backup:", BACKUP)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
