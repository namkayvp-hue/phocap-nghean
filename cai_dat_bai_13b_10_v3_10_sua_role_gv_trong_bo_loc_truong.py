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
BACKUP = PROJECT / "exports" / f"backup_bai_13b_10_v3_10_{STAMP}"
BACKUP_SURVEYS = BACKUP / "app" / "routers" / "surveys.py"

MARK_DOT = "BAI_13B_10_V3_10_FIX_SCHOOL_BATCH_ROLE"
MARK_FORM = "BAI_13B_10_V3_10_FIX_SCHOOL_FORM_ROLE"


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


def function_block(text_value: str, func_name: str) -> tuple[int, int, str]:
    match = re.search(
        rf"^def\s+{re.escape(func_name)}\s*\(",
        text_value,
        flags=re.MULTILINE,
    )
    if not match:
        raise RuntimeError(f"Không tìm thấy hàm {func_name}().")

    start = match.start()
    next_def = re.search(
        r"^(?:def|@router\.)\s*",
        text_value[match.end():],
        flags=re.MULTILINE,
    )
    end = match.end() + next_def.start() if next_def else len(text_value)
    return start, end, text_value[start:end]


def patch_one_function(
    text_value: str,
    func_name: str,
    marker: str,
) -> str:
    start, end, block = function_block(text_value, func_name)

    if marker in block:
        print(f" - {func_name}: V3.10 đã có, không sửa lặp.")
        return text_value

    required = [
        'if role_code == "TRUONG":',
        "User.school_id == int(school_id)",
        "User.role.has(code=SCHOOL_ROLE_CODE)",
        '~func.lower(User.username).like("cbql.%")',
    ]
    for item in required:
        if item not in block:
            raise RuntimeError(
                f"{func_name}() không giống source V3.9; thiếu: {item}"
            )

    old = "User.role.has(code=SCHOOL_ROLE_CODE)"
    occurrences = block.count(old)
    if occurrences != 1:
        raise RuntimeError(
            f"{func_name}(): tìm thấy {occurrences} chỗ '{old}', "
            "cần đúng 1 để sửa an toàn."
        )

    line_match = re.search(
        r"(?m)^(?P<indent>[ \t]*)User\.role\.has\(code=SCHOOL_ROLE_CODE\),?\s*$",
        block,
    )
    if not line_match:
        raise RuntimeError(
            f"{func_name}(): không tìm thấy dòng role theo định dạng dự kiến."
        )

    indent = line_match.group("indent")
    replacement = (
        f"{indent}# === {marker}_START ===\n"
        f"{indent}# Phiếu được giao cho GIÁO VIÊN của trường,\n"
        f"{indent}# không phải tài khoản vai trò TRƯỜNG.\n"
        f"{indent}User.role.has(code=TEACHER_ROLE_CODE),\n"
        f"{indent}# === {marker}_END ==="
    )

    block = (
        block[:line_match.start()]
        + replacement
        + block[line_match.end():]
    )
    return text_value[:start] + block + text_value[end:]


def patch_source(text_value: str) -> str:
    text_value = patch_one_function(
        text_value,
        "tao_bo_loc_dot_theo_nguoi_dung",
        MARK_DOT,
    )
    text_value = patch_one_function(
        text_value,
        "tao_bo_loc_phieu_theo_nguoi_dung",
        MARK_FORM,
    )
    return text_value


def verify_static() -> None:
    text_value = read_text(SURVEYS)

    for func_name, marker in (
        ("tao_bo_loc_dot_theo_nguoi_dung", MARK_DOT),
        ("tao_bo_loc_phieu_theo_nguoi_dung", MARK_FORM),
    ):
        _, _, block = function_block(text_value, func_name)

        if marker not in block:
            raise RuntimeError(
                f"Kiểm tra sau cài: {func_name} thiếu marker V3.10."
            )
        if "User.role.has(code=SCHOOL_ROLE_CODE)" in block:
            raise RuntimeError(
                f"Kiểm tra sau cài: {func_name} vẫn còn SCHOOL_ROLE_CODE."
            )
        if "User.role.has(code=TEACHER_ROLE_CODE)" not in block:
            raise RuntimeError(
                f"Kiểm tra sau cài: {func_name} chưa có TEACHER_ROLE_CODE."
            )

    subprocess.run(
        [sys.executable, "-m", "py_compile", str(SURVEYS)],
        cwd=PROJECT,
        check=True,
    )


def verify_runtime() -> None:
    code = r"""
import sys
from pathlib import Path

PROJECT = Path(r"C:\PhoCap")
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from sqlalchemy import func, select
from starlette.requests import Request
from app.database import SessionLocal
from app.models import Role, User
from app.permissions import normalize_role_code
from app.routers import surveys
from app.survey_models import SurveyBatch, SurveyForm

USERNAME = "truong_40413507"
BATCH_ID = 3

db = SessionLocal()
try:
    row = db.execute(
        select(
            User.id,
            User.username,
            User.full_name,
            User.school_id,
            User.commune_id,
            Role.code.label("role_code"),
            Role.name.label("role_name"),
        )
        .join(Role, Role.id == User.role_id)
        .where(User.username == USERNAME)
    ).mappings().first()

    if row is None:
        print("VERIFY_RUNTIME_SKIPPED: không còn tài khoản test THCS Hải Hòa")
        raise SystemExit(0)

    auth_user = {
        "id": int(row["id"]),
        "username": row["username"],
        "full_name": row["full_name"],
        "role_code": normalize_role_code(row["role_code"]),
        "role_name": row["role_name"],
        "school_id": row["school_id"],
        "commune_id": row["commune_id"],
    }

    scope = {
        "type": "http",
        "method": "GET",
        "path": f"/dieu-tra/{BATCH_ID}/ho-dan",
        "raw_path": f"/dieu-tra/{BATCH_ID}/ho-dan".encode(),
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 12345),
        "server": ("127.0.0.1", 80),
        "scheme": "http",
        "root_path": "",
        "http_version": "1.1",
        "auth_user": auth_user,
    }
    request = Request(scope)

    batch_filters = surveys.tao_bo_loc_dot_theo_nguoi_dung(request)
    form_filters = surveys.tao_bo_loc_phieu_theo_nguoi_dung(request)

    batch_count = int(db.scalar(
        select(func.count(SurveyBatch.id)).where(
            SurveyBatch.id == BATCH_ID,
            *batch_filters,
        )
    ) or 0)

    form_count = int(db.scalar(
        select(func.count(SurveyForm.id)).where(
            SurveyForm.survey_batch_id == BATCH_ID,
            *form_filters,
        )
    ) or 0)

    print(f"VERIFY_RUNTIME: batch_count={batch_count} | form_count={form_count}")

    if batch_count != 1 or form_count != 5:
        raise RuntimeError(
            f"Runtime verify chưa đạt: batch={batch_count}, form={form_count}; "
            "kỳ vọng batch=1, form=5."
        )
finally:
    db.close()
"""
    subprocess.run(
        [sys.executable, "-c", code],
        cwd=PROJECT,
        check=True,
    )


def main() -> int:
    print("=" * 118)
    print("BÀI 13B-10 V3.10 - SỬA ĐÚNG ROLE GIÁO VIÊN TRONG PHẠM VI TRƯỜNG")
    print("=" * 118)
    print()
    print("NGUYÊN NHÂN ĐÃ XÁC ĐỊNH TỪ V3.9:")
    print(" - RAW SQL theo school_id = 5 phiếu.")
    print(" - ORM batch = 0, ORM form = 0.")
    print(" - Các GV được phân công có role_code = GIAO_VIEN.")
    print(" - Nhưng source phạm vi TRƯỜNG lại yêu cầu:")
    print("       User.role.has(code=SCHOOL_ROLE_CODE)")
    print()
    print("V3.10 SỬA:")
    print(" - Bộ lọc ĐỢT: SCHOOL_ROLE_CODE -> TEACHER_ROLE_CODE.")
    print(" - Bộ lọc PHIẾU: SCHOOL_ROLE_CODE -> TEACHER_ROLE_CODE.")
    print(" - Giữ nguyên school_id và điều kiện loại cbql.%.")
    print()
    print("KHÔNG sửa database, tổ SENT, hộ dân, Đội ngũ, báo cáo hay mobile.")
    print()

    if not SURVEYS.exists():
        raise RuntimeError(f"Không tìm thấy: {SURVEYS}")

    backup()

    try:
        original = read_text(SURVEYS)
        patched = patch_source(original)
        SURVEYS.write_text(patched, encoding="utf-8")

        verify_static()
        clear_cache()
        verify_runtime()
        clear_cache()

        print()
        print("CAI DAT BAI 13B-10 V3.10 THANH CONG")
        print("Backup:", BACKUP)
        print()
        print("KẾT QUẢ KỲ VỌNG:")
        print(" - THCS Hải Hòa: /dieu-tra/3/ho-dan thấy 5 phiếu.")
        print(" - Tiểu học Nghi Hương thấy 5 phiếu.")
        print(" - Trường MN Nghi Hải thấy 5 phiếu.")
        print(" - Giáo viên vẫn chỉ thấy phiếu được phân công trực tiếp.")
        return 0

    except Exception:
        traceback.print_exc()
        print()
        print("CÓ LỖI - ĐANG KHÔI PHỤC SOURCE...")
        restore()
        clear_cache()
        print("ĐÃ KHÔI PHỤC surveys.py TRƯỚC V3.10.")
        print("Backup:", BACKUP)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
