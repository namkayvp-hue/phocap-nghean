from __future__ import annotations

import hashlib
import os
import shutil
import sqlite3
import subprocess
import sys
import traceback
import zipfile
from datetime import datetime
from pathlib import Path

PROJECT = Path(r"C:\PhoCap")
DB_SOURCE = PROJECT / "data" / "phocap.db"
OUT_ROOT = Path(r"C:\PhoCap_ChuyenMay")

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
PACKAGE_NAME = f"PhoCap_ChuyenMay_{STAMP}"
PACKAGE_DIR = OUT_ROOT / PACKAGE_NAME
PAYLOAD_DIR = PACKAGE_DIR / "PhoCap"
ZIP_PATH = OUT_ROOT / f"{PACKAGE_NAME}.zip"

RESTORE_GUIDE_TEMPLATE = 'PHỔ CẬP GIÁO DỤC VÀ XÓA MÙ CHỮ\nGÓI CHUYỂN MÁY\n\nThời điểm đóng gói: {timestamp}\nNguồn: C:\\PhoCap\n\nDATABASE:\n- File: PhoCap\\data\\phocap.db\n- Integrity check: {integrity}\n- Số bảng: {tables}\n- Kích thước: {db_size}\n- SHA256: {db_sha256}\n\nDEPENDENCIES:\n- Đã tạo: PhoCap\\requirements_chuyen_may.txt\n- Số package ghi nhận: {req_count}\n\n============================================================\nCÁCH ĐƯA SANG MÁY MỚI\n============================================================\n\n1. Cài Python trên máy mới.\n2. Giải nén file ZIP này.\n3. Lấy nguyên thư mục PhoCap chép thành C:\\PhoCap.\n4. Mở PowerShell và chạy:\n\ncd C:\\PhoCap\npy -m venv .venv\n& C:\\PhoCap\\.venv\\Scripts\\python.exe -m pip install --upgrade pip\n& C:\\PhoCap\\.venv\\Scripts\\python.exe -m pip install -r C:\\PhoCap\\requirements_chuyen_may.txt\n\n5. Chạy phần mềm:\n\ncd C:\\PhoCap\n& C:\\PhoCap\\.venv\\Scripts\\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 80\n\n6. Mở:\nhttp://127.0.0.1/\n\nLƯU Ý:\n- Không sao chép .venv từ máy cũ.\n- Gói đã loại .venv và __pycache__.\n- Database được tạo bằng SQLite backup API và kiểm tra integrity.\n'
PS1_TEXT = 'Write-Host "=== PHO CAP - KHOI TAO MAY MOI ===" -ForegroundColor Cyan\n\nif (-not (Test-Path "C:\\PhoCap")) {\n    Write-Host "Khong tim thay C:\\PhoCap" -ForegroundColor Red\n    Write-Host "Hay chep thu muc PhoCap trong goi vao C:\\PhoCap truoc."\n    exit 1\n}\n\nSet-Location C:\\PhoCap\n\nif (-not (Test-Path ".venv")) {\n    Write-Host "Tao moi truong ao .venv..."\n    py -m venv .venv\n}\n\nWrite-Host "Nang cap pip..."\n& C:\\PhoCap\\.venv\\Scripts\\python.exe -m pip install --upgrade pip\n\nif (Test-Path "C:\\PhoCap\\requirements_chuyen_may.txt") {\n    Write-Host "Cai dependencies..."\n    & C:\\PhoCap\\.venv\\Scripts\\python.exe -m pip install -r C:\\PhoCap\\requirements_chuyen_may.txt\n}\n\nWrite-Host ""\nWrite-Host "HOAN TAT CAI MOI TRUONG." -ForegroundColor Green\nWrite-Host "Chay phan mem:"\nWrite-Host "& C:\\PhoCap\\.venv\\Scripts\\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 80"\n'

EXCLUDE_DIRS = {
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".git",
    ".idea",
}

EXCLUDE_SUFFIXES = {".pyc", ".pyo"}

EXCLUDE_NAMES = {
    "phocap.db",
    "phocap.db-wal",
    "phocap.db-shm",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def format_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{num_bytes} B"


def copy_project() -> tuple[int, int]:
    file_count = 0
    total_bytes = 0

    for root, dirs, files in os.walk(PROJECT):
        root_path = Path(root)

        dirs[:] = [
            d for d in dirs
            if d not in EXCLUDE_DIRS
        ]

        rel_root = root_path.relative_to(PROJECT)
        target_root = PAYLOAD_DIR / rel_root
        target_root.mkdir(parents=True, exist_ok=True)

        for filename in files:
            src = root_path / filename

            if filename in EXCLUDE_NAMES:
                continue

            if src.suffix.lower() in EXCLUDE_SUFFIXES:
                continue

            if "PhoCap_ChuyenMay_" in filename:
                continue

            dst = target_root / filename
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

            file_count += 1
            try:
                total_bytes += src.stat().st_size
            except OSError:
                pass

    return file_count, total_bytes


def backup_sqlite() -> dict:
    if not DB_SOURCE.exists():
        raise RuntimeError(
            f"Không tìm thấy database: {DB_SOURCE}"
        )

    db_target = PAYLOAD_DIR / "data" / "phocap.db"
    db_target.parent.mkdir(parents=True, exist_ok=True)

    src_con = sqlite3.connect(str(DB_SOURCE))
    dst_con = sqlite3.connect(str(db_target))

    try:
        src_con.backup(dst_con)
        dst_con.commit()
    finally:
        dst_con.close()
        src_con.close()

    check_con = sqlite3.connect(str(db_target))
    try:
        integrity = check_con.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]

        table_count = check_con.execute(
            """
            SELECT COUNT(*)
            FROM sqlite_master
            WHERE type='table'
              AND name NOT LIKE 'sqlite_%'
            """
        ).fetchone()[0]
    finally:
        check_con.close()

    if str(integrity).lower() != "ok":
        raise RuntimeError(
            f"Database backup lỗi integrity_check: {integrity}"
        )

    return {
        "path": str(db_target),
        "size": db_target.stat().st_size,
        "sha256": sha256(db_target),
        "tables": int(table_count or 0),
        "integrity": integrity,
    }


def export_requirements() -> dict:
    req_target = PAYLOAD_DIR / "requirements_chuyen_may.txt"

    candidates = [
        PROJECT / ".venv" / "Scripts" / "python.exe",
        Path(sys.executable),
    ]

    errors = []

    for python_exe in candidates:
        if not python_exe.exists():
            continue

        try:
            result = subprocess.run(
                [str(python_exe), "-m", "pip", "freeze"],
                cwd=PROJECT,
                text=True,
                capture_output=True,
                check=True,
            )

            text_value = (result.stdout or "").strip()

            if text_value:
                req_target.write_text(
                    text_value + "\n",
                    encoding="utf-8",
                )
                return {
                    "success": True,
                    "python": str(python_exe),
                    "count": len(
                        [
                            line
                            for line in text_value.splitlines()
                            if line.strip()
                        ]
                    ),
                }

        except Exception as exc:
            errors.append(f"{python_exe}: {exc}")

    existing = PROJECT / "requirements.txt"
    if existing.exists():
        shutil.copy2(existing, req_target)
        text_value = req_target.read_text(
            encoding="utf-8-sig"
        )
        return {
            "success": True,
            "python": "requirements.txt hiện có",
            "count": len(
                [
                    line
                    for line in text_value.splitlines()
                    if line.strip()
                ]
            ),
        }

    req_target.write_text(
        "# Không tự lấy được pip freeze.\n",
        encoding="utf-8",
    )

    return {
        "success": False,
        "python": "",
        "count": 0,
        "errors": errors,
    }


def write_restore_files(db_info: dict, req_info: dict) -> None:
    guide = RESTORE_GUIDE_TEMPLATE.format(
        timestamp=datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        integrity=db_info["integrity"],
        tables=db_info["tables"],
        db_size=format_size(db_info["size"]),
        db_sha256=db_info["sha256"],
        req_count=req_info.get("count", 0),
    )

    (PACKAGE_DIR / "HUONG_DAN_CHUYEN_MAY.txt").write_text(
        guide,
        encoding="utf-8",
    )

    (PACKAGE_DIR / "KHOI_TAO_MAY_MOI.ps1").write_text(
        PS1_TEXT,
        encoding="utf-8",
    )


def zip_package() -> None:
    if ZIP_PATH.exists():
        ZIP_PATH.unlink()

    with zipfile.ZipFile(
        ZIP_PATH,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=6,
    ) as zf:
        for path in PACKAGE_DIR.rglob("*"):
            if path.is_file():
                zf.write(
                    path,
                    arcname=str(
                        Path(PACKAGE_NAME)
                        / path.relative_to(PACKAGE_DIR)
                    ),
                )


def main() -> int:
    print("=" * 96)
    print("ĐÓNG GÓI PHẦN MỀM PHỔ CẬP GIÁO DỤC ĐỂ CHUYỂN MÁY - V1")
    print("=" * 96)
    print()
    print("Nguồn:", PROJECT)
    print("Đích :", OUT_ROOT)
    print()
    print("Gói sẽ GIỮ:")
    print(" - Toàn bộ source hiện tại.")
    print(" - Database phocap.db.")
    print(" - static, templates, uploads, exports và dữ liệu trong project.")
    print(" - requirements_chuyen_may.txt.")
    print()
    print("Gói sẽ KHÔNG mang theo:")
    print(" - .venv")
    print(" - __pycache__")
    print(" - .git / cache IDE")
    print()
    print("Khuyến nghị: dừng Uvicorn trước khi chạy.")
    print()

    if not PROJECT.exists():
        raise RuntimeError(
            f"Không tìm thấy project: {PROJECT}"
        )

    if PACKAGE_DIR.exists():
        shutil.rmtree(PACKAGE_DIR, ignore_errors=True)

    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    PAYLOAD_DIR.mkdir(parents=True, exist_ok=True)

    try:
        print("[1/5] Sao chép source...")
        file_count, copied_bytes = copy_project()

        print("[2/5] Sao lưu database bằng SQLite backup API...")
        db_info = backup_sqlite()

        print("[3/5] Ghi danh sách thư viện Python...")
        req_info = export_requirements()

        print("[4/5] Tạo hướng dẫn khôi phục...")
        write_restore_files(db_info, req_info)

        print("[5/5] Nén ZIP...")
        zip_package()

        zip_hash = sha256(ZIP_PATH)
        zip_size = ZIP_PATH.stat().st_size

        print()
        print("=" * 96)
        print("ĐÓNG GÓI THÀNH CÔNG")
        print("=" * 96)
        print("Thư mục gói :", PACKAGE_DIR)
        print("File ZIP     :", ZIP_PATH)
        print("Số file copy :", file_count)
        print("Source copy  :", format_size(copied_bytes))
        print("Database     :", format_size(db_info["size"]))
        print("ZIP          :", format_size(zip_size))
        print("ZIP SHA256   :", zip_hash)
        print()
        print("BƯỚC TIẾP THEO:")
        print(" - Chép file ZIP sang USB/ổ cứng/máy mới.")
        print(" - Giữ nguyên ZIP này làm bản sao trước khi dọn dữ liệu thử nghiệm.")
        return 0

    except Exception:
        traceback.print_exc()
        print()
        print("ĐÓNG GÓI KHÔNG THÀNH CÔNG.")
        print("Không thay đổi dữ liệu trong C:\\PhoCap.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
