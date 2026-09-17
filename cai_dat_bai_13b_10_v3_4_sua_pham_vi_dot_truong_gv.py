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
BACKUP = PROJECT / "exports" / f"backup_bai_13b_10_v3_4_{STAMP}"

MARKER = "BAI_13B_10_V3_4_SCHOOL_TEACHER_BATCH_SCOPE"


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
        re.MULTILINE,
    )
    if not match:
        raise RuntimeError(f"Không tìm thấy hàm {name} trong surveys.py")

    start = match.start()
    next_decorator = re.search(
        r"^@router\.",
        text_value[match.end():],
        re.MULTILINE,
    )
    end = (
        match.end() + next_decorator.start()
        if next_decorator
        else len(text_value)
    )
    return start, end, text_value[start:end]


def patch_route(text_value: str) -> str:
    start, end, block = function_block(
        text_value,
        "danh_sach_dot_dieu_tra",
    )

    if MARKER in block:
        return text_value

    old_scope = '''    if role_code not in PROVINCE_READ_ROLE_CODES:
        user_commune_id = user.get("commune_id")
        communes = [
            item
            for item in communes
            if (
                user_commune_id is not None
                and item.id == int(user_commune_id)
            )
        ]

        commune_id = (
            int(user_commune_id)
            if user_commune_id is not None
            else None
        )
'''

    if old_scope not in block:
        raise RuntimeError(
            "Không tìm thấy đúng khối ép commune_id trong "
            "danh_sach_dot_dieu_tra(). Dừng để tránh sửa nhầm."
        )

    new_scope = f'''    # === {MARKER}_START ===
    # Xã/phường vẫn khóa theo commune_id của tài khoản.
    # Riêng Trường/Giáo viên đã được giới hạn an toàn bằng
    # survey_form_investigators, nên KHÔNG dùng commune_id để lọc đợt.
    #
    # Lý do: dữ liệu danh mục lịch sử có thể tồn tại nhiều bản ghi
    # commune cùng mã/tên nhưng khác id. Nếu ép commune_id của tài khoản
    # Trường/GV vào SurveyBatch.commune_id thì đợt đã được phân công hợp lệ
    # vẫn bị loại khỏi /dieu-tra.
    apply_commune_filter = True

    if role_code not in PROVINCE_READ_ROLE_CODES:
        user_commune_id = user.get("commune_id")
        communes = [
            item
            for item in communes
            if (
                user_commune_id is not None
                and item.id == int(user_commune_id)
            )
        ]

        commune_id = (
            int(user_commune_id)
            if user_commune_id is not None
            else None
        )

        if role_code in {{SCHOOL_ROLE_CODE, TEACHER_ROLE_CODE}}:
            apply_commune_filter = False
    # === {MARKER}_END ===
'''

    block = block.replace(old_scope, new_scope, 1)

    old_filter = '''    if commune_id is not None:
        filters.append(
            SurveyBatch.commune_id == commune_id
        )
'''

    if old_filter not in block:
        raise RuntimeError(
            "Không tìm thấy khối lọc SurveyBatch.commune_id "
            "trong danh_sach_dot_dieu_tra()."
        )

    new_filter = '''    if commune_id is not None and apply_commune_filter:
        filters.append(
            SurveyBatch.commune_id == commune_id
        )
'''

    block = block.replace(old_filter, new_filter, 1)

    return text_value[:start] + block + text_value[end:]


def verify() -> None:
    text_value = read_text(SURVEYS)
    _, _, block = function_block(
        text_value,
        "danh_sach_dot_dieu_tra",
    )

    required = [
        MARKER,
        "apply_commune_filter = True",
        "role_code in {SCHOOL_ROLE_CODE, TEACHER_ROLE_CODE}",
        "apply_commune_filter = False",
        "if commune_id is not None and apply_commune_filter:",
        "filters = tao_bo_loc_dot_theo_nguoi_dung(request)",
    ]

    for marker in required:
        if marker not in block:
            raise RuntimeError(
                f"Kiểm tra sau cài chưa đạt, thiếu: {marker}"
            )

    subprocess.run(
        [sys.executable, "-m", "py_compile", str(SURVEYS)],
        cwd=PROJECT,
        check=True,
    )


def main() -> int:
    print("=" * 112)
    print("BÀI 13B-10 V3.4 - SỬA PHẠM VI ĐỢT CHO TRƯỜNG / GIÁO VIÊN")
    print("=" * 112)
    print()
    print("NGUYÊN NHÂN ĐÃ XÁC ĐỊNH:")
    print(" - Đợt #3: Phường Cửa Lò có commune_id = 5.")
    print(" - Trang tài khoản Trường đang mang commune_id = 58.")
    print(" - /dieu-tra hiện ép thêm SurveyBatch.commune_id == commune_id tài khoản.")
    print(" - Vì 5 != 58 nên đợt đã chốt/gửi vẫn bị loại và Trường hiện 0 đợt.")
    print()
    print("V3.4:")
    print(" - Giữ nguyên khóa phạm vi commune_id cho Xã/phường.")
    print(" - Trường/Giáo viên không lọc đợt bằng commune_id nữa.")
    print(" - Trường/Giáo viên vẫn bị giới hạn CHẶT bằng survey_form_investigators:")
    print("   + Trường: chỉ đợt có phiếu gắn GV thuộc chính school_id của trường.")
    print("   + Giáo viên: chỉ đợt có phiếu gắn đúng user_id của giáo viên.")
    print(" - Không sửa database.")
    print(" - Không sửa 5 tổ đã chốt.")
    print(" - Không sửa hộ dân, thành viên, Đội ngũ, báo cáo hoặc mobile.")
    print()

    if not SURVEYS.exists():
        raise RuntimeError(f"Không tìm thấy: {SURVEYS}")

    BACKUP.mkdir(parents=True, exist_ok=False)
    backup_file(SURVEYS)

    try:
        current = read_text(SURVEYS)
        patched = patch_route(current)
        SURVEYS.write_text(patched, encoding="utf-8")

        verify()
        clear_cache()

        print()
        print("CAI DAT BAI 13B-10 V3.4 THANH CONG")
        print("Backup:", BACKUP)
        print()
        print("KIỂM TRA:")
        print(" 1. Khởi động lại Uvicorn.")
        print(" 2. Ctrl+F5.")
        print(" 3. Đăng nhập THCS Hải Hòa -> /dieu-tra.")
        print(" 4. Đợt 2026-2027 phải xuất hiện nếu school_id của GV trong tổ khớp trường.")
        print(" 5. Vào 2.2.1 để kiểm tra hộ/phiếu được giao.")
        return 0

    except Exception:
        traceback.print_exc()
        print()
        print("CÓ LỖI - ĐANG KHÔI PHỤC SOURCE...")
        restore_file(SURVEYS)
        clear_cache()
        print("ĐÃ KHÔI PHỤC SOURCE TRƯỚC V3.4.")
        print("Backup:", BACKUP)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
