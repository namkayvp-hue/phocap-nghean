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
BACKUP = PROJECT / "exports" / f"backup_source_bai_13b_11_5_1_{STAMP}"

MARK_START = "BAI_13B_11_5_1_FIX_GLUE_STATUS_IF_START"
MARK_END = "BAI_13B_11_5_1_FIX_GLUE_STATUS_IF_END"

OLD_MARKER = "# === BAI_13B_10_V3_7_SKIP_COMMUNE_FILTER_FOR_SCHOOL_TEACHER_END ==="

BROKEN_BLOCK = (
    "    # === BAI_13B_10_V3_7_SKIP_COMMUNE_FILTER_FOR_SCHOOL_TEACHER_END ===if survey_status:\n"
    "        filters.append(\n"
    "            SurveyBatch.status == survey_status\n"
    "        )\n"
)

FIXED_BLOCK = (
    "    # === BAI_13B_10_V3_7_SKIP_COMMUNE_FILTER_FOR_SCHOOL_TEACHER_END ===\n"
    "    # === BAI_13B_11_5_1_FIX_GLUE_STATUS_IF_START ===\n"
    "    if survey_status in BATCH_STATUS_LABELS:\n"
    "        filters.append(\n"
    "            SurveyBatch.status == survey_status\n"
    "        )\n"
    "    # === BAI_13B_11_5_1_FIX_GLUE_STATUS_IF_END ===\n"
)


def read_text(path: Path) -> str:
    if not path.exists():
        raise RuntimeError(f"Không tìm thấy tệp bắt buộc: {path}")
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
        ROUTER.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, ROUTER)


def clear_cache() -> None:
    for cache in APP.rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(cache, ignore_errors=True)


def preflight(text: str) -> None:
    required = [
        '@router.get("", response_class=HTMLResponse)',
        "def danh_sach_dot_dieu_tra(",
        'survey_status: str = ""',
        "if survey_status not in BATCH_STATUS_LABELS:",
        'survey_status = ""',
        OLD_MARKER,
        "SurveyBatch.status == survey_status",
    ]
    for marker in required:
        if marker not in text:
            raise RuntimeError(
                "surveys.py không đúng nền đã xác định. "
                f"Thiếu: {marker}"
            )


def patch(text: str) -> str:
    preflight(text)

    if MARK_START in text and MARK_END in text:
        print(" - Bài 13B-11.5.1 đã có sẵn, không chèn lặp.")
        return text

    glued = OLD_MARKER + "if survey_status:"
    glued_count = text.count(glued)
    block_count = text.count(BROKEN_BLOCK)

    if glued_count != 1:
        raise RuntimeError(
            "Không tìm thấy đúng 1 dòng marker bị dính 'if survey_status:'. "
            f"Số lần tìm thấy: {glued_count}. Dừng an toàn."
        )

    if block_count != 1:
        raise RuntimeError(
            "Đã thấy dòng bị dính nhưng khối filters.append phía sau không đúng "
            f"nền dự kiến (số khối: {block_count}). Dừng an toàn."
        )

    return text.replace(BROKEN_BLOCK, FIXED_BLOCK, 1)


def verify_source() -> None:
    text = read_text(ROUTER)

    required = [
        MARK_START,
        MARK_END,
        OLD_MARKER + "\n",
        "if survey_status in BATCH_STATUS_LABELS:",
        "SurveyBatch.status == survey_status",
    ]
    for marker in required:
        if marker not in text:
            raise RuntimeError(f"Kiểm tra source sau cài thiếu: {marker}")

    if OLD_MARKER + "if survey_status:" in text:
        raise RuntimeError("Dòng comment vẫn còn dính với if survey_status.")

    if text.count(MARK_START) != 1 or text.count(MARK_END) != 1:
        raise RuntimeError("Marker Bài 13B-11.5.1 bị thiếu hoặc bị lặp.")

    subprocess.run(
        [sys.executable, "-m", "py_compile", str(ROUTER)],
        cwd=PROJECT,
        check=True,
    )


def verify_runtime() -> None:
    # Giữ đúng bài kiểm tra thực tế của Bài 13B-11.5:
    # cùng tài khoản/địa bàn/năm học đã dùng để tái hiện lỗi.
    check_code = r'''
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
'''

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
    print("BÀI 13B-11.5.1 - SỬA DÒNG IF TRẠNG THÁI BỊ DÍNH VÀO COMMENT")
    print("=" * 108)
    print()
    print("NGUYÊN NHÂN ĐÃ XÁC ĐỊNH TỪ SOURCE THỰC TẾ:")
    print(
        " - Marker Bài 13B-10 V3.7 và 'if survey_status:' "
        "đang nằm trên cùng một dòng."
    )
    print(" - Vì dòng bắt đầu bằng #, phần 'if survey_status:' bị comment mất.")
    print(
        " - filters.append(SurveyBatch.status == survey_status) vì thế "
        "có thể chạy sai ngữ cảnh và tạo lọc status=''."
    )
    print()
    print("BẢN SỬA:")
    print(" - Tách marker và điều kiện lọc thành hai dòng độc lập.")
    print(" - Chỉ thêm điều kiện status khi giá trị thuộc BATCH_STATUS_LABELS.")
    print(" - Chỉ sửa app/routers/surveys.py.")
    print(" - Backup source trước khi sửa.")
    print(" - Không sửa database.")
    print(" - Không đổi menu/giao diện/phân quyền.")
    print(" - py_compile sau sửa.")
    print(" - TestClient kiểm tra trạng thái rỗng và CHUAN_BI.")
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
        print(" - Dòng marker / if đã tách: OK")
        print(" - Chỉ lọc trạng thái hợp lệ: OK")
        print(" - Router py_compile: OK")
        print(" - TestClient trạng thái rỗng: OK")
        print(" - TestClient CHUAN_BI: OK")
        print(" - Database: KHÔNG THAY ĐỔI")
        print()
        print("CÀI ĐẶT BÀI 13B-11.5.1 THÀNH CÔNG")
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
