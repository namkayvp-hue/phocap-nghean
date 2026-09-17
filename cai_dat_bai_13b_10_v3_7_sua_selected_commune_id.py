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
BACKUP = PROJECT / "exports" / f"backup_bai_13b_10_v3_7_{STAMP}"
BACKUP_SURVEYS = BACKUP / "app" / "routers" / "surveys.py"

MARKER = "BAI_13B_10_V3_7_SKIP_COMMUNE_FILTER_FOR_SCHOOL_TEACHER"


def read_text(path: Path) -> str:
    if not path.exists():
        raise RuntimeError(f"Không tìm thấy tệp: {path}")
    return path.read_text(encoding="utf-8-sig")


def backup() -> None:
    BACKUP_SURVEYS.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SURVEYS, BACKUP_SURVEYS)


def restore() -> None:
    if BACKUP_SURVEYS.exists():
        shutil.copy2(BACKUP_SURVEYS, SURVEYS)


def clear_cache() -> None:
    for cache in APP.rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(cache, ignore_errors=True)


def get_route_block(text_value: str) -> tuple[int, int, str]:
    match = re.search(
        r"^def\s+danh_sach_dot_dieu_tra\s*\(",
        text_value,
        flags=re.MULTILINE,
    )
    if not match:
        raise RuntimeError(
            "Không tìm thấy hàm danh_sach_dot_dieu_tra() trong surveys.py."
        )

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


def detect_filter_variable(route_block: str) -> str:
    """
    Hỗ trợ cả hai dạng đã tồn tại trong dự án:
      SurveyBatch.commune_id == commune_id
      SurveyBatch.commune_id == selected_commune_id
    """

    candidates = []

    if "SurveyBatch.commune_id == selected_commune_id" in route_block:
        candidates.append("selected_commune_id")

    if "SurveyBatch.commune_id == commune_id" in route_block:
        candidates.append("commune_id")

    if len(candidates) == 1:
        return candidates[0]

    if len(candidates) == 0:
        raise RuntimeError(
            "Không tìm thấy biểu thức lọc xã/phường trong route /dieu-tra. "
            "Bản source hiện tại khác cả hai dạng đã biết."
        )

    raise RuntimeError(
        "Route /dieu-tra chứa đồng thời nhiều dạng lọc commune; "
        "dừng để tránh sửa nhầm."
    )


def patch_route(text_value: str) -> str:
    start, end, block = get_route_block(text_value)

    if MARKER in block:
        print(" - V3.7 đã có trong route, không sửa lặp.")
        return text_value

    required = [
        "filters = tao_bo_loc_dot_theo_nguoi_dung(request)",
        'role_code = str(user.get("role_code") or "")',
    ]
    for item in required:
        if item not in block:
            raise RuntimeError(
                f"Route /dieu-tra thiếu cấu trúc bắt buộc: {item}"
            )

    variable = detect_filter_variable(block)

    print(f" - Phát hiện biến lọc xã/phường thực tế: {variable}")

    # Dạng chuẩn:
    # if selected_commune_id is not None:
    #     filters.append(
    #         SurveyBatch.commune_id == selected_commune_id
    #     )
    #
    # hoặc commune_id.
    pattern = re.compile(
        rf"(?P<indent>^[ \t]*)if\s+{re.escape(variable)}\s+is\s+not\s+None"
        rf"(?:\s+and\s+[A-Za-z_][A-Za-z0-9_]*)?\s*:\s*\n"
        rf"(?P=indent)[ \t]+filters\.append\(\s*\n"
        rf"(?P=indent)[ \t]+SurveyBatch\.commune_id\s*==\s*{re.escape(variable)}\s*\n"
        rf"(?P=indent)[ \t]+\)\s*",
        flags=re.MULTILINE,
    )

    matches = list(pattern.finditer(block))

    if len(matches) != 1:
        # Fallback linh hoạt hơn nếu format bị xuống dòng khác.
        pattern = re.compile(
            rf"(?P<indent>^[ \t]*)if\s+{re.escape(variable)}\s+is\s+not\s+None"
            rf"[^\n]*:\s*\n"
            rf"(?P<body>(?:(?P=indent)[ \t]+[^\n]*\n){{1,6}})",
            flags=re.MULTILINE,
        )

        candidates = []
        for m in pattern.finditer(block):
            candidate = m.group(0)
            if (
                "filters.append" in candidate
                and "SurveyBatch.commune_id" in candidate
                and variable in candidate
            ):
                candidates.append(m)

        if len(candidates) != 1:
            raise RuntimeError(
                "Đã nhận ra biến lọc nhưng không xác định duy nhất khối "
                f"'if {variable} is not None' cần sửa. "
                f"Tìm thấy {len(candidates)} khối phù hợp."
            )

        match = candidates[0]
    else:
        match = matches[0]

    indent = match.group("indent")

    replacement = (
        f'{indent}# === {MARKER}_START ===\n'
        f'{indent}# Xã/phường vẫn lọc theo địa bàn.\n'
        f'{indent}# Riêng Trường/Giáo viên đã được khóa phạm vi bằng\n'
        f'{indent}# tao_bo_loc_dot_theo_nguoi_dung() -> survey_form_investigators,\n'
        f'{indent}# nên không ép thêm SurveyBatch.commune_id.\n'
        f'{indent}if (\n'
        f'{indent}    {variable} is not None\n'
        f'{indent}    and role_code not in {{SCHOOL_ROLE_CODE, TEACHER_ROLE_CODE}}\n'
        f'{indent}):\n'
        f'{indent}    filters.append(\n'
        f'{indent}        SurveyBatch.commune_id == {variable}\n'
        f'{indent}    )\n'
        f'{indent}# === {MARKER}_END ==='
    )

    block = block[:match.start()] + replacement + block[match.end():]

    return text_value[:start] + block + text_value[end:]


def verify() -> None:
    text_value = read_text(SURVEYS)
    _, _, block = get_route_block(text_value)

    required = [
        MARKER,
        "role_code not in {SCHOOL_ROLE_CODE, TEACHER_ROLE_CODE}",
        "filters = tao_bo_loc_dot_theo_nguoi_dung(request)",
    ]
    for item in required:
        if item not in block:
            raise RuntimeError(
                f"Kiểm tra V3.7 chưa đạt, thiếu: {item}"
            )

    # Phải còn đúng một so sánh commune trong route, nhưng nằm trong
    # điều kiện loại trừ TRUONG/GIAO_VIEN.
    commune_compare_count = len(
        re.findall(
            r"SurveyBatch\.commune_id\s*==\s*(?:selected_commune_id|commune_id)",
            block,
        )
    )
    if commune_compare_count != 1:
        raise RuntimeError(
            f"Số biểu thức lọc commune sau sửa = {commune_compare_count}, "
            "không đúng 1."
        )

    subprocess.run(
        [sys.executable, "-m", "py_compile", str(SURVEYS)],
        cwd=PROJECT,
        check=True,
    )


def main() -> int:
    print("=" * 118)
    print("BÀI 13B-10 V3.7 - SỬA ĐÚNG BIẾN selected_commune_id / commune_id")
    print("=" * 118)
    print()
    print("KẾT QUẢ ĐÃ XÁC NHẬN:")
    print(" - 5/5 tổ SENT.")
    print(" - 15/15 lượt phân công chính thức.")
    print(" - school_id thành viên tổ khớp 100%.")
    print(" - THCS Hải Hòa school_id=1409 có 5 phiếu.")
    print(" - Tiểu học Nghi Hương school_id=896 có 5 phiếu.")
    print(" - Trường MN Nghi Hải school_id=197 có 5 phiếu.")
    print()
    print("V3.6 thất bại an toàn vì bộ cài chỉ tìm:")
    print("   SurveyBatch.commune_id == commune_id")
    print("Trong khi source hiện tại có thể đang dùng:")
    print("   SurveyBatch.commune_id == selected_commune_id")
    print()
    print("V3.7 tự nhận diện CẢ HAI dạng.")
    print("Chỉ sửa route /dieu-tra; KHÔNG sửa database.")
    print()

    if not SURVEYS.exists():
        raise RuntimeError(f"Không tìm thấy: {SURVEYS}")

    backup()

    try:
        original = read_text(SURVEYS)
        patched = patch_route(original)
        SURVEYS.write_text(patched, encoding="utf-8")

        verify()
        clear_cache()

        print()
        print("CAI DAT BAI 13B-10 V3.7 THANH CONG")
        print("Backup:", BACKUP)
        print()
        print("SAU CÀI:")
        print(" 1. Khởi động lại Uvicorn.")
        print(" 2. Ctrl+F5.")
        print(" 3. Đăng nhập THCS Hải Hòa -> /dieu-tra.")
        print(" 4. Đợt 2026-2027 phải xuất hiện.")
        print(" 5. Vào 2.2.1 để kiểm tra 5 hộ/phiếu.")
        return 0

    except Exception:
        traceback.print_exc()
        print()
        print("CÓ LỖI - ĐANG KHÔI PHỤC SOURCE...")
        restore()
        clear_cache()
        print("ĐÃ KHÔI PHỤC surveys.py TRƯỚC V3.7.")
        print("Backup:", BACKUP)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
