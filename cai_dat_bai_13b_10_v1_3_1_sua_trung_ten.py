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
ROUTER = APP / "routers" / "survey_team_registration.py"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = PROJECT / "exports" / f"backup_bai_13b_10_v1_3_1_{STAMP}"
BACKUP_ROUTER = BACKUP / "app" / "routers" / "survey_team_registration.py"

MARKER = "BAI_13B_10_V1_3_1_DUPLICATE_NAME_FIX"
REPLACEMENT_FUNCTION = 'def _teacher_account_matches(\n    db: Session,\n    *,\n    school_id: int,\n    staff_row: dict[str, Any],\n) -> tuple[str, dict[str, Any] | None]:\n    ministry_code = str(\n        staff_row.get("ministry_staff_code")\n        or staff_row.get("internal_staff_code")\n        or ""\n    ).strip()\n\n    # V1.3.1:\n    # Khi hồ sơ Đội ngũ đã có MÃ CÁN BỘ/GV thì mã là định danh ưu tiên.\n    # Không được ghép theo họ tên nếu username gv.<mã> chưa tồn tại,\n    # vì một trường có thể có 2 giáo viên trùng họ tên.\n    expected_username = (\n        f"gv.{ministry_code}".lower()\n        if ministry_code\n        else ""\n    )\n\n    if expected_username:\n        row = db.execute(\n            text(\n                """\n                SELECT\n                    u.id,\n                    u.username,\n                    u.full_name,\n                    u.school_id,\n                    u.is_active,\n                    UPPER(r.code) AS role_code\n                FROM users AS u\n                JOIN roles AS r\n                  ON r.id = u.role_id\n                WHERE LOWER(u.username) = :username\n                LIMIT 1\n                """\n            ),\n            {"username": expected_username},\n        ).mappings().first()\n\n        if row is not None:\n            account = dict(row)\n\n            if (\n                str(account.get("role_code") or "")\n                == TEACHER_ROLE_CODE\n                and int(account.get("school_id") or 0)\n                == int(school_id)\n            ):\n                return (\n                    "ACTIVE"\n                    if int(account.get("is_active") or 0) == 1\n                    else "LOCKED",\n                    account,\n                )\n\n            # Username gv.<mã> đã tồn tại nhưng thuộc sai trường/vai trò:\n            # phải dừng ở CONFLICT, tuyệt đối không chiếm dụng.\n            return "CONFLICT", account\n\n        # Có mã GV nhưng chưa có đúng username -> đây là tài khoản còn thiếu.\n        # KHÔNG fallback theo họ tên.\n        return "MISSING", None\n\n    # Chỉ khi hồ sơ thật sự KHÔNG CÓ mã cán bộ/GV mới được phép\n    # đối chiếu theo họ tên trong cùng trường và cùng vai trò.\n    candidates = db.execute(\n        text(\n            """\n            SELECT\n                u.id,\n                u.username,\n                u.full_name,\n                u.school_id,\n                u.is_active,\n                UPPER(r.code) AS role_code\n            FROM users AS u\n            JOIN roles AS r\n              ON r.id = u.role_id\n            WHERE u.school_id = :school_id\n              AND UPPER(r.code) = :role_code\n            """\n        ),\n        {\n            "school_id": int(school_id),\n            "role_code": TEACHER_ROLE_CODE,\n        },\n    ).mappings().all()\n\n    target_name = _normalized_person_name(\n        staff_row.get("full_name")\n    )\n    name_matches = [\n        dict(row)\n        for row in candidates\n        if _normalized_person_name(row.get("full_name"))\n        == target_name\n    ]\n\n    if len(name_matches) == 1:\n        account = name_matches[0]\n        return (\n            "ACTIVE"\n            if int(account.get("is_active") or 0) == 1\n            else "LOCKED",\n            account,\n        )\n\n    return "MISSING", None'


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


def patch_router(text_value: str) -> str:
    if MARKER in text_value:
        print(" - V1.3.1 đã có, không sửa lặp.")
        return text_value

    if "BAI_13B_10_V1_3_STAFF_TO_TEACHER_ACCOUNTS_START" not in text_value:
        raise RuntimeError(
            "Chưa thấy nền Bài 13B-10 V1.3 trong survey_team_registration.py."
        )

    start_match = re.search(
        r"^def _teacher_account_matches\(",
        text_value,
        flags=re.M,
    )
    if start_match is None:
        raise RuntimeError(
            "Không tìm thấy def _teacher_account_matches()."
        )

    next_match = re.search(
        r"^def _safe_teacher_username\(",
        text_value[start_match.start():],
        flags=re.M,
    )
    if next_match is None:
        raise RuntimeError(
            "Không tìm thấy def _safe_teacher_username() sau hàm cần sửa."
        )

    start = start_match.start()
    end = start_match.start() + next_match.start()

    old_block = text_value[start:end]
    required_old = [
        "expected_username",
        "_normalized_person_name",
        "name_matches",
        'return "MISSING", None',
    ]
    for marker in required_old:
        if marker not in old_block:
            raise RuntimeError(
                f"Hàm hiện tại khác dự kiến, thiếu: {marker}"
            )

    marker_line = (
        "# === BAI_13B_10_V1_3_1_DUPLICATE_NAME_FIX ===\n"
    )

    return (
        text_value[:start]
        + marker_line
        + REPLACEMENT_FUNCTION
        + "\n\n"
        + text_value[end:]
    )


def verify(text_value: str) -> None:
    required = [
        MARKER,
        "Khi hồ sơ Đội ngũ đã có MÃ CÁN BỘ/GV",
        "KHÔNG fallback theo họ tên",
        'return "MISSING", None',
        "def _safe_teacher_username(",
    ]
    for marker in required:
        if marker not in text_value:
            raise RuntimeError(
                f"Kiểm tra sau cài chưa đạt: {marker}"
            )

    # Đảm bảo hàm chỉ có một lần.
    if text_value.count("def _teacher_account_matches(") != 1:
        raise RuntimeError(
            "_teacher_account_matches() không đúng 1 lần."
        )

    subprocess.run(
        [sys.executable, "-m", "py_compile", str(ROUTER)],
        cwd=PROJECT,
        check=True,
    )


def main() -> int:
    print("=" * 108)
    print("BÀI 13B-10 V1.3.1 - SỬA TRƯỜNG HỢP GIÁO VIÊN TRÙNG HỌ TÊN")
    print("=" * 108)
    print("")
    print("ĐÃ XÁC ĐỊNH TẠI TIỂU HỌC NGHI HƯƠNG:")
    print(" - Hồ sơ Đội ngũ: 40 GV.")
    print(" - Tài khoản GIAO_VIEN hoạt động: 39.")
    print(" - Có Hoàng Thị Lan mã 4001211336")
    print("   nhưng V1.3 đang ghép theo tên với user gv.4001050561.")
    print("")
    print("NGUYÊN NHÂN:")
    print(" - Một trường có thể có 2 người trùng họ tên.")
    print(" - V1.3 fallback theo họ tên dù hồ sơ đã có mã GV.")
    print(" - Hai hồ sơ khác mã có thể bị coi là cùng một tài khoản.")
    print("")
    print("V1.3.1 SỬA:")
    print(" - Nếu hồ sơ có mã GV: chỉ nhận đúng username gv.<mã>.")
    print(" - Không còn ghép theo họ tên khi đã có mã.")
    print(" - Chỉ fallback theo tên nếu hồ sơ thực sự không có mã.")
    print(" - Không đổi username/mật khẩu của tài khoản đã tồn tại.")
    print(" - Không sửa database khi cài.")
    print("")

    backup()

    try:
        before = read_text(ROUTER)
        after = patch_router(before)
        verify(after)

        ROUTER.write_text(after, encoding="utf-8")
        clear_cache()
        verify(read_text(ROUTER))

        print("")
        print("CAI DAT BAI 13B-10 V1.3.1 THANH CONG")
        print("Backup:", BACKUP)
        print("")
        print("SAU CÀI:")
        print(" 1. Khởi động lại Uvicorn.")
        print(" 2. Trường Tiểu học Nghi Hương -> 2.2.7.")
        print(" 3. Bấm lại 'Tạo tài khoản GV còn thiếu + tải Excel mật khẩu'.")
        print(" 4. Hệ thống chỉ nên tạo thêm user còn thiếu, ví dụ gv.4001211336.")
        print(" 5. Làm mới -> GV đang hoạt động phải đạt 40.")
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
