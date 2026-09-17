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

APP_DIR = PROJECT / "app"
MAIN = APP_DIR / "main.py"
SURVEYS = APP_DIR / "routers" / "surveys.py"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = (
    PROJECT
    / "exports"
    / f"backup_source_bai_13b_11_4_1_{STAMP}"
)

START = "# === BAI_13B_11_4_1_LATE_SURVEYS_ROUTER_START ==="
END = "# === BAI_13B_11_4_1_LATE_SURVEYS_ROUTER_END ==="

LATE_BLOCK = '\n# === BAI_13B_11_4_1_LATE_SURVEYS_ROUTER_START ===\nfrom app.routers.surveys import router as _b1311_surveys_router_late\n\n_b1311_has_get_dieu_tra = any(\n    getattr(_route, "path", None) == "/dieu-tra"\n    and "GET" in set(getattr(_route, "methods", None) or [])\n    for _route in app.routes\n)\n\nif not _b1311_has_get_dieu_tra:\n    app.include_router(_b1311_surveys_router_late)\n\ndel _b1311_has_get_dieu_tra\ndel _b1311_surveys_router_late\n# === BAI_13B_11_4_1_LATE_SURVEYS_ROUTER_END ===\n'
CHECK_CODE = '\nimport inspect\nfrom app.main import app\nfrom app.routers import surveys\n\nmatches = []\nfor index, route in enumerate(app.routes):\n    path = getattr(route, "path", None)\n    methods = set(getattr(route, "methods", None) or [])\n    endpoint = getattr(route, "endpoint", None)\n    if path == "/dieu-tra" and "GET" in methods:\n        matches.append((index, endpoint))\n\nprint("GET_DIEU_TRA_COUNT=", len(matches))\nfor index, endpoint in matches:\n    print(\n        "ROUTE=", index,\n        "MODULE=", getattr(endpoint, "__module__", ""),\n        "NAME=", getattr(endpoint, "__name__", ""),\n        "SOURCE=", inspect.getsourcefile(endpoint),\n        "SAME=", endpoint is surveys.danh_sach_dot_dieu_tra,\n    )\n\nif len(matches) != 1:\n    raise SystemExit(31)\n\nif matches[0][1] is not surveys.danh_sach_dot_dieu_tra:\n    raise SystemExit(32)\n\nprint("VERIFY_RUNTIME_ROUTES=OK")\n'


def read_text(path: Path) -> str:
    if not path.exists():
        raise RuntimeError(f"Không tìm thấy tệp: {path}")
    return path.read_text(encoding="utf-8-sig")


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def backup_source() -> None:
    target = BACKUP / MAIN.relative_to(PROJECT)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(MAIN, target)


def restore_source() -> None:
    source = BACKUP / MAIN.relative_to(PROJECT)
    if source.exists():
        shutil.copy2(source, MAIN)


def clear_cache() -> None:
    for cache in APP_DIR.rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(cache, ignore_errors=True)


def remove_old_block(text: str) -> str:
    a = text.find(START)
    if a < 0:
        return text

    b = text.find(END, a)
    if b < 0:
        raise RuntimeError(
            "Tìm thấy đầu marker 13B-11.4.1 nhưng thiếu marker kết thúc."
        )

    b += len(END)

    left = text[:a].rstrip()
    right = text[b:].lstrip("\r\n")

    if right:
        return left + "\n\n" + right

    return left + "\n"


def patch(text: str) -> str:
    if "FastAPI" not in text or "app" not in text:
        raise RuntimeError(
            "app/main.py không có cấu trúc FastAPI dự kiến."
        )

    cleaned = remove_old_block(text)

    return (
        cleaned.rstrip()
        + "\n\n"
        + LATE_BLOCK.strip()
        + "\n"
    )


def verify_source() -> None:
    main_text = read_text(MAIN)
    surveys_text = read_text(SURVEYS)

    if main_text.count(START) != 1:
        raise RuntimeError(
            "Marker đăng ký route cuối main không đúng 1 lần."
        )

    if main_text.count(END) != 1:
        raise RuntimeError(
            "Marker kết thúc không đúng 1 lần."
        )

    if not main_text.rstrip().endswith(END):
        raise RuntimeError(
            "Khối đăng ký surveys_router chưa nằm ở cuối tuyệt đối main.py."
        )

    required_surveys = [
        'prefix="/dieu-tra"',
        '@router.get("", response_class=HTMLResponse)',
        "def danh_sach_dot_dieu_tra(",
    ]

    for marker in required_surveys:
        if marker not in surveys_text:
            raise RuntimeError(
                "surveys.py không đúng nền. Thiếu: " + marker
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


def verify_runtime() -> None:
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
            "Kiểm tra runtime không đạt "
            f"(mã {result.returncode})."
        )


def main() -> int:
    print("=" * 110)
    print(
        "BÀI 13B-11.4.1 - "
        "ĐĂNG KÝ ROUTE ĐIỀU TRA Ở CUỐI app/main.py"
    )
    print("=" * 110)
    print()
    print("CHẨN ĐOÁN ĐÃ XÁC ĐỊNH:")
    print(" - Database: đúng.")
    print(" - Scope xã: đúng.")
    print(" - surveys.py có route gốc /dieu-tra.")
    print(" - app.main.app vẫn thiếu GET /dieu-tra.")
    print()
    print("CÁCH SỬA:")
    print(" - Không sửa database.")
    print(" - Không sửa surveys.py.")
    print(" - Chỉ thêm block an toàn ở CUỐI TUYỆT ĐỐI app/main.py.")
    print(" - Nếu app cuối cùng chưa có GET /dieu-tra mới include surveys_router.")
    print(" - Nếu route đã có thì không include lại.")
    print(" - Sau sửa kiểm tra runtime trong tiến trình Python mới.")
    print(" - Không đạt -> rollback source ngay.")
    print()

    for path in (MAIN, SURVEYS):
        if not path.exists():
            raise RuntimeError(
                f"Không tìm thấy nền bắt buộc: {path}"
            )

    BACKUP.mkdir(parents=True, exist_ok=False)
    backup_source()
    print("Backup source:", BACKUP)

    try:
        before = read_text(MAIN)
        after = patch(before)
        write_text(MAIN, after)

        verify_source()
        clear_cache()
        verify_runtime()

        print()
        print("KIỂM TRA SAU CÀI:")
        print(" - main.py py_compile: OK")
        print(" - surveys.py py_compile: OK")
        print(" - Block nằm cuối tuyệt đối main.py: OK")
        print(" - GET /dieu-tra đúng 1 route: OK")
        print(" - Endpoint = danh_sach_dot_dieu_tra: OK")
        print(" - Database: KHÔNG THAY ĐỔI")
        print()
        print(
            "CÀI ĐẶT BÀI 13B-11.4.1 THÀNH CÔNG"
        )
        return 0

    except Exception:
        traceback.print_exc()
        print()
        print(
            "CÓ LỖI - ĐANG KHÔI PHỤC app/main.py..."
        )
        restore_source()
        clear_cache()
        print("ĐÃ KHÔI PHỤC SOURCE.")
        print("Database không bị thay đổi.")
        print("Backup source:", BACKUP)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
