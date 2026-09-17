from __future__ import annotations

import os
import shutil
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path


PROJECT_DIR = Path(r"C:\PhoCap")
PACKAGE_DIR = Path(__file__).resolve().parent
PAYLOAD_DIR = PACKAGE_DIR / "payload"
CHECK_FILE = PACKAGE_DIR / "check_bai_13a_2_v4.py"

TARGETS = [
    Path("app/main.py"),
    Path("app/routers/report_center.py"),
    Path("app/routers/survey_summary_report.py"),
    Path("app/templates/reports/report_center.html"),
    Path("app/templates/reports/survey_summary_report.html"),
]


def copy_payload(relative_path: Path) -> None:
    source = PAYLOAD_DIR / relative_path
    target = PROJECT_DIR / relative_path
    if not source.is_file():
        raise FileNotFoundError(f"Thiếu tệp trong bộ cài: {source}")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    print(f"Đã chép: {relative_path}")


def clear_python_cache() -> None:
    for cache_dir in PROJECT_DIR.rglob("__pycache__"):
        try:
            shutil.rmtree(cache_dir)
        except OSError:
            pass


def run_check() -> None:
    compile_targets = [
        str(PROJECT_DIR / item)
        for item in TARGETS
        if item.suffix == ".py"
    ]
    compile_targets.append(str(CHECK_FILE))

    subprocess.run(
        [sys.executable, "-m", "py_compile", *compile_targets],
        cwd=PROJECT_DIR,
        check=True,
    )

    check_env = os.environ.copy()
    existing_pythonpath = check_env.get("PYTHONPATH", "").strip()
    check_env["PYTHONPATH"] = (
        str(PROJECT_DIR)
        if not existing_pythonpath
        else str(PROJECT_DIR) + os.pathsep + existing_pythonpath
    )
    check_env["PHOCAP_PROJECT_DIR"] = str(PROJECT_DIR)

    subprocess.run(
        [sys.executable, str(CHECK_FILE)],
        cwd=PROJECT_DIR,
        env=check_env,
        check=True,
    )


def restore_backup(
    backup_dir: Path,
    existed_before: dict[Path, bool],
) -> None:
    for relative_path in TARGETS:
        target = PROJECT_DIR / relative_path
        backup_target = backup_dir / relative_path
        if existed_before.get(relative_path):
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup_target, target)
        elif target.exists():
            target.unlink()
    clear_python_cache()


def main() -> None:
    print()
    print("=" * 72)
    print("CÀI ĐẶT BÀI 13A-2 V4 - SỬA LỖI ĐƯỜNG DẪN IMPORT KHI KIỂM TRA")
    print("=" * 72)

    if not PROJECT_DIR.is_dir():
        raise FileNotFoundError(f"Không tìm thấy dự án: {PROJECT_DIR}")
    if not PAYLOAD_DIR.is_dir():
        raise FileNotFoundError(f"Không tìm thấy thư mục payload: {PAYLOAD_DIR}")
    if not CHECK_FILE.is_file():
        raise FileNotFoundError(f"Không tìm thấy tệp kiểm tra: {CHECK_FILE}")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = (
        PROJECT_DIR
        / "exports"
        / f"backup_bai_13a_2_v4_{timestamp}"
    )
    backup_dir.mkdir(parents=True, exist_ok=True)

    existed_before: dict[Path, bool] = {}
    print("\nBƯỚC 1 - SAO LƯU MÃ NGUỒN VÀ CƠ SỞ DỮ LIỆU")
    for relative_path in TARGETS:
        target = PROJECT_DIR / relative_path
        existed_before[relative_path] = target.exists()
        if target.exists():
            backup_target = backup_dir / relative_path
            backup_target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, backup_target)
            print(f"Đã sao lưu: {relative_path}")

    database_path = PROJECT_DIR / "data" / "phocap.db"
    if database_path.exists():
        database_backup = backup_dir / "data" / "phocap.db"
        database_backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(database_path, database_backup)
        print("Đã sao lưu: data/phocap.db")

    print(f"Bản sao an toàn: {backup_dir}")

    try:
        print("\nBƯỚC 2 - CHÉP TOÀN BỘ TỆP HOÀN CHỈNH")
        for relative_path in TARGETS:
            copy_payload(relative_path)

        print("\nBƯỚC 3 - XÓA BỘ NHỚ ĐỆM PYTHON")
        clear_python_cache()
        print("Đã xóa các thư mục __pycache__ trong dự án.")

        print("\nBƯỚC 4 - KIỂM TRA CÚ PHÁP, ROUTE, GIAO DIỆN VÀ DỮ LIỆU")
        run_check()

    except Exception:
        print("\nCÓ LỖI KHI CÀI ĐẶT. ĐANG KHÔI PHỤC BẢN CŨ...")
        restore_backup(backup_dir, existed_before)
        print(f"Đã khôi phục từ: {backup_dir}")
        traceback.print_exc()
        raise

    print()
    print("=" * 72)
    print("KIỂM TRA BÀI 13A-2 V4 THÀNH CÔNG")
    print("CÀI ĐẶT BÀI 13A-2 V4 THÀNH CÔNG")
    print("=" * 72)
    print("Địa chỉ mới:")
    print("http://127.0.0.1:8000/bao-cao/tong-hop-dieu-tra")
    print()


if __name__ == "__main__":
    main()
