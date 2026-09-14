from __future__ import annotations

import os
import shutil
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path

PROJECT = Path(
    os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")
).resolve()

APP = PROJECT / "app"
MAIN = APP / "main.py"
SURVEYS = APP / "routers" / "surveys.py"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = (
    PROJECT
    / "exports"
    / f"backup_source_bai_13b_11_4_{STAMP}"
)

IMPORT_LINE = "from app.routers.surveys import router as surveys_router"
INCLUDE_LINE = "app.include_router(surveys_router)"
MARK_IMPORT = "BAI_13B_11_4_SURVEYS_ROUTER_IMPORT"
MARK_INCLUDE = "BAI_13B_11_4_SURVEYS_ROUTER_INCLUDE"

CHECK_CODE = '\nfrom app.main import app\nfrom app.routers import surveys\n\nmatches = []\nfor index, route in enumerate(app.routes):\n    path = getattr(route, "path", None)\n    methods = set(getattr(route, "methods", None) or [])\n    endpoint = getattr(route, "endpoint", None)\n    if path == "/dieu-tra" and "GET" in methods:\n        matches.append((index, endpoint))\n\nprint("GET_DIEU_TRA_COUNT=", len(matches))\nfor index, endpoint in matches:\n    print(\n        "ROUTE=", index,\n        getattr(endpoint, "__module__", ""),\n        getattr(endpoint, "__name__", ""),\n        "SAME=", endpoint is surveys.danh_sach_dot_dieu_tra,\n    )\n\nif len(matches) != 1:\n    raise SystemExit(21)\n\nif matches[0][1] is not surveys.danh_sach_dot_dieu_tra:\n    raise SystemExit(22)\n'


def read_text(path: Path) -> str:
    if not path.exists():
        raise RuntimeError(f"Không tìm thấy tệp: {path}")
    return path.read_text(encoding="utf-8-sig")


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def backup() -> None:
    target = BACKUP / MAIN.relative_to(PROJECT)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(MAIN, target)


def restore() -> None:
    source = BACKUP / MAIN.relative_to(PROJECT)
    if source.exists():
        shutil.copy2(source, MAIN)


def clear_cache() -> None:
    for cache in APP.rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(cache, ignore_errors=True)


def patch(text: str) -> str:
    if "FastAPI(" not in text:
        raise RuntimeError("app/main.py không chứa ứng dụng FastAPI.")

    if IMPORT_LINE not in text:
        anchors = [
            "from app.routers.students import router as students_router",
            "from app.routers.schools import router as schools_router",
            "from app.routers.auth import router as auth_router",
        ]
        anchor = next((a for a in anchors if a in text), None)
        if anchor is None:
            raise RuntimeError(
                "Không tìm thấy vị trí import router an toàn trong main.py."
            )
        text = text.replace(
            anchor,
            anchor + f"\n# === {MARK_IMPORT} ===\n" + IMPORT_LINE,
            1,
        )

    if INCLUDE_LINE not in text:
        anchors = [
            "app.include_router(students_router)",
            "app.include_router(schools_router)",
            "app.include_router(auth_router)",
        ]
        anchor = next((a for a in anchors if a in text), None)
        if anchor is None:
            raise RuntimeError(
                "Không tìm thấy vị trí include_router an toàn trong main.py."
            )
        text = text.replace(
            anchor,
            anchor + f"\n# === {MARK_INCLUDE} ===\n" + INCLUDE_LINE,
            1,
        )

    if text.count(INCLUDE_LINE) != 1:
        raise RuntimeError(
            "main.py có nhiều hơn một app.include_router(surveys_router)."
        )

    return text


def verify_source() -> None:
    main_text = read_text(MAIN)
    surveys_text = read_text(SURVEYS)

    if IMPORT_LINE not in main_text:
        raise RuntimeError("Thiếu import surveys_router sau cài.")

    if main_text.count(INCLUDE_LINE) != 1:
        raise RuntimeError(
            "Số lần include surveys_router sau cài không bằng 1."
        )

    if 'router = APIRouter(' not in surveys_text:
        raise RuntimeError("surveys.py không còn APIRouter.")

    if 'prefix="/dieu-tra"' not in surveys_text:
        raise RuntimeError("surveys.py không còn prefix /dieu-tra.")

    if '@router.get("", response_class=HTMLResponse)' not in surveys_text:
        raise RuntimeError(
            'surveys.py không còn route gốc @router.get("").'
        )

    subprocess.run(
        [sys.executable, "-m", "py_compile", str(MAIN)],
        cwd=PROJECT,
        check=True,
    )
    subprocess.run(
        [sys.executable, "-m", "py_compile", str(SURVEYS)],
        cwd=PROJECT,
        check=True,
    )


def verify_runtime_routes() -> None:
    result = subprocess.run(
        [sys.executable, "-c", CHECK_CODE],
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
            "FastAPI vẫn chưa đăng ký đúng duy nhất GET /dieu-tra "
            f"(mã kiểm tra {result.returncode})."
        )


def main() -> int:
    print("=" * 104)
    print("BÀI 13B-11.4 - KHÔI PHỤC ROUTE GET /dieu-tra")
    print("=" * 104)
    print()
    print("KẾT QUẢ CHẨN ĐOÁN:")
    print(" - Database Nghi Lộc: đúng.")
    print(" - Helper scope cấp xã: trả đúng 1 batch.")
    print(" - app.main.app hiện không có GET /dieu-tra.")
    print()
    print("BẢN SỬA:")
    print(" - Chỉ sửa app/main.py nếu thiếu import/include surveys_router.")
    print(" - Không chèn lặp router.")
    print(" - Không sửa surveys.py.")
    print(" - Không sửa database.")
    print(" - Sau cài kiểm tra trực tiếp đúng 1 GET /dieu-tra.")
    print()

    for path in (MAIN, SURVEYS):
        if not path.exists():
            raise RuntimeError(f"Không tìm thấy nền bắt buộc: {path}")

    BACKUP.mkdir(parents=True, exist_ok=False)
    backup()
    print("Backup source:", BACKUP)

    try:
        before = read_text(MAIN)
        after = patch(before)
        write_text(MAIN, after)

        verify_source()
        clear_cache()
        verify_runtime_routes()

        print()
        print("KIỂM TRA SAU CÀI:")
        print(" - main.py py_compile: OK")
        print(" - surveys.py py_compile: OK")
        print(" - surveys_router include đúng 1 lần: OK")
        print(" - GET /dieu-tra đăng ký đúng endpoint: OK")
        print(" - Database: KHÔNG THAY ĐỔI")
        print()
        print("CÀI ĐẶT BÀI 13B-11.4 THÀNH CÔNG")
        return 0

    except Exception:
        traceback.print_exc()
        print()
        print("CÓ LỖI - ĐANG KHÔI PHỤC app/main.py...")
        restore()
        clear_cache()
        print("ĐÃ KHÔI PHỤC SOURCE.")
        print("Database không bị thay đổi.")
        print("Backup source:", BACKUP)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
