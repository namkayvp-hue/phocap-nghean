
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
ROUTER = APP / "routers" / "surveys.py"
STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = PROJECT / "exports" / f"backup_source_bai_13b_11_5_{STAMP}"

MARK1 = "BAI_13B_11_5_FIX_EMPTY_STATUS_START"
MARK2 = "BAI_13B_11_5_VALID_STATUS_ONLY_START"

OLD_BLOCK = (
    '    if survey_status not in BATCH_STATUS_LABELS:\n'
    '        survey_status = ""\n'
    '\n'
    '    filters = tao_bo_loc_dot_theo_nguoi_dung(request)\n'
)

NEW_BLOCK = (
    '    # === BAI_13B_11_5_FIX_EMPTY_STATUS_START ===\n'
    '    raw_survey_status = request.query_params.get(\n'
    '        "survey_status",\n'
    '        "",\n'
    '    )\n'
    '    survey_status = str(raw_survey_status or "").strip()\n'
    '\n'
    '    if survey_status not in BATCH_STATUS_LABELS:\n'
    '        survey_status = ""\n'
    '    # === BAI_13B_11_5_FIX_EMPTY_STATUS_END ===\n'
    '\n'
    '    filters = tao_bo_loc_dot_theo_nguoi_dung(request)\n'
)

OLD_CONDITION = (
    '    if survey_status:\n'
    '        filters.append(\n'
    '            SurveyBatch.status == survey_status\n'
    '        )\n'
)

NEW_CONDITION = (
    '    # === BAI_13B_11_5_VALID_STATUS_ONLY_START ===\n'
    '    if survey_status in BATCH_STATUS_LABELS:\n'
    '        filters.append(\n'
    '            SurveyBatch.status == survey_status\n'
    '        )\n'
    '    # === BAI_13B_11_5_VALID_STATUS_ONLY_END ===\n'
)


def read_text(path: Path) -> str:
    if not path.exists():
        raise RuntimeError(f"Không tìm thấy tệp: {path}")
    return path.read_text(encoding="utf-8-sig")


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def backup_source() -> None:
    target = BACKUP / ROUTER.relative_to(PROJECT)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROUTER, target)


def restore_source() -> None:
    source = BACKUP / ROUTER.relative_to(PROJECT)
    if source.exists():
        shutil.copy2(source, ROUTER)


def clear_cache() -> None:
    for cache in APP.rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(cache, ignore_errors=True)


def patch(text: str) -> str:
    if MARK1 in text and MARK2 in text:
        return text

    required = [
        '@router.get("", response_class=HTMLResponse)',
        'def danh_sach_dot_dieu_tra(',
        'survey_status: str = ""',
        'SurveyBatch.status == survey_status',
    ]
    for marker in required:
        if marker not in text:
            raise RuntimeError(f"surveys.py thiếu nền mã nguồn: {marker}")

    if text.count(OLD_BLOCK) != 1:
        raise RuntimeError("Không tìm thấy đúng 1 khối chuẩn hóa survey_status cần sửa.")
    if text.count(OLD_CONDITION) != 1:
        raise RuntimeError("Không tìm thấy đúng 1 điều kiện lọc trạng thái cần sửa.")

    text = text.replace(OLD_BLOCK, NEW_BLOCK, 1)
    text = text.replace(OLD_CONDITION, NEW_CONDITION, 1)
    return text


def verify_source() -> None:
    text = read_text(ROUTER)
    checks = [
        MARK1,
        MARK2,
        'request.query_params.get(',
        '"survey_status"',
        'survey_status = str(raw_survey_status or "").strip()',
        'if survey_status in BATCH_STATUS_LABELS:',
    ]
    for marker in checks:
        if marker not in text:
            raise RuntimeError(f"Kiểm tra source sau cài thiếu: {marker}")

    if text.count(MARK1) != 1:
        raise RuntimeError("Marker chuẩn hóa trạng thái bị lặp.")
    if text.count(MARK2) != 1:
        raise RuntimeError("Marker điều kiện trạng thái bị lặp.")

    subprocess.run(
        [sys.executable, "-m", "py_compile", str(ROUTER)],
        cwd=PROJECT,
        check=True,
    )


def verify_runtime() -> None:
    check_code = r"""
import base64
import json
from itsdangerous import TimestampSigner
from fastapi.testclient import TestClient
import app.main as main_mod

TARGET = "DT-17827-20262027-001"
app = main_mod.app
secret = getattr(main_mod, "SESSION_SECRET_KEY", None)
cookie_name = None

for mw in getattr(app, "user_middleware", []):
    cls = getattr(mw, "cls", None)
    kwargs = dict(getattr(mw, "kwargs", {}) or {})
    if getattr(cls, "__name__", "") == "SessionMiddleware":
        if secret is None:
            secret = kwargs.get("secret_key")
        cookie_name = kwargs.get("session_cookie", cookie_name)

if not secret:
    raise SystemExit(40)

cookie_name = cookie_name or "phocap_session"
raw = base64.b64encode(json.dumps({"user_id": 13359}).encode("utf-8"))
cookie = TimestampSigner(str(secret)).sign(raw).decode("utf-8")
client = TestClient(app, follow_redirects=False)

r1 = client.get(
    "/dieu-tra",
    params={"school_year_id": "2", "commune_id": "114", "survey_status": ""},
    cookies={cookie_name: cookie},
)
print("EMPTY_STATUS_HTTP=", r1.status_code)
print("EMPTY_STATUS_HAS_BATCH=", TARGET in r1.text)
print("EMPTY_STATUS_HAS_1_DOT=", "1 đợt" in r1.text)
if r1.status_code != 200:
    raise SystemExit(41)
if TARGET not in r1.text:
    raise SystemExit(42)

r2 = client.get(
    "/dieu-tra",
    params={"school_year_id": "2", "commune_id": "114", "survey_status": "CHUAN_BI"},
    cookies={cookie_name: cookie},
)
print("CHUAN_BI_HTTP=", r2.status_code)
print("CHUAN_BI_HAS_BATCH=", TARGET in r2.text)
if r2.status_code != 200:
    raise SystemExit(43)
if TARGET not in r2.text:
    raise SystemExit(44)

print("VERIFY_RUNTIME=OK")
"""

    result = subprocess.run(
        [sys.executable, "-c", check_code],
        cwd=PROJECT,
        text=True,
        capture_output=True,
    )

    if result.stdout:
        print(result.stdout.rstrip())
    if result.stderr:
        print(result.stderr.rstrip())
    if result.returncode != 0:
        raise RuntimeError(
            "Kiểm tra runtime sau cài không đạt "
            f"(mã {result.returncode})."
        )


def main() -> int:
    print("=" * 108)
    print("BÀI 13B-11.5 - SỬA LỌC TRẠNG THÁI RỖNG Ở DANH SÁCH ĐỢT")
    print("=" * 108)
    print()
    print("V8 ĐÃ XÁC ĐỊNH SQL SAI:")
    print(" WHERE commune_id=114 AND school_year_id=2 AND commune_id=114 AND status=''")
    print()
    print("BẢN SỬA:")
    print(" - Chuẩn hóa survey_status trực tiếp từ query string.")
    print(" - Chuỗi rỗng/giá trị lạ => không thêm điều kiện status.")
    print(" - Chỉ lọc khi trạng thái thuộc BATCH_STATUS_LABELS.")
    print(" - Không sửa database.")
    print(" - Không đổi menu/giao diện/luồng.")
    print(" - Backup surveys.py trước khi sửa.")
    print(" - TestClient kiểm tra lại Nghi Lộc sau cài.")
    print()

    if not ROUTER.exists():
        raise RuntimeError(f"Không tìm thấy: {ROUTER}")

    BACKUP.mkdir(parents=True, exist_ok=False)
    backup_source()
    print("Backup source:", BACKUP)

    try:
        before = read_text(ROUTER)
        after = patch(before)
        write_text(ROUTER, after)
        verify_source()
        clear_cache()
        verify_runtime()

        print()
        print("KIỂM TRA SAU CÀI:")
        print(" - surveys.py py_compile: OK")
        print(" - survey_status rỗng KHÔNG còn lọc status='': OK")
        print(" - Nghi Lộc + 2026-2027 + Tất cả trạng thái: THẤY ĐỢT")
        print(" - Nghi Lộc + CHUAN_BI: THẤY ĐỢT")
        print(" - Database: KHÔNG THAY ĐỔI")
        print()
        print("CÀI ĐẶT BÀI 13B-11.5 THÀNH CÔNG")
        return 0

    except Exception:
        traceback.print_exc()
        print()
        print("CÓ LỖI - ĐANG KHÔI PHỤC surveys.py...")
        restore_source()
        clear_cache()
        print("ĐÃ KHÔI PHỤC SOURCE.")
        print("Database không bị thay đổi.")
        print("Backup source:", BACKUP)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
