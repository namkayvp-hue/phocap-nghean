from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path

PROJECT = Path(os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")).resolve()
TARGET = PROJECT / "app" / "routers" / "mn_official_reports.py"
EXPORTS = PROJECT / "exports"
STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = EXPORTS / f"backup_bao_cao_mn_mau_moi_v1_1_{STAMP}"
MANIFEST = BACKUP / "manifest.json"
MARKER = "BAO_CAO_MN_MAU_MOI_V1_1_EMPTY_QUERY_FIX"

ROUTE_FUNCTIONS = (
    "mn01te_page",
    "mn01gv_bgd_page",
    "mn01te_export",
    "mn01gv_bgd_export",
)
PARAMS = ("school_year_id", "commune_id", "school_id")


def read_text(path: Path) -> str:
    if not path.exists():
        raise RuntimeError(f"Không tìm thấy tệp bắt buộc: {path}")
    return path.read_text(encoding="utf-8-sig")


def backup_source() -> None:
    BACKUP.mkdir(parents=True, exist_ok=False)
    dst = BACKUP / "app" / "routers" / TARGET.name
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(TARGET, dst)
    MANIFEST.write_text(
        json.dumps(
            {
                "version": "Bao cao MN mau moi V1.1",
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "source": str(TARGET),
                "backup": str(dst),
                "database_modified": False,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def restore_source() -> None:
    src = BACKUP / "app" / "routers" / TARGET.name
    if src.exists():
        TARGET.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, TARGET)


def function_signature_bounds(text_value: str, function_name: str) -> tuple[int, int]:
    anchor = f"def {function_name}("
    start = text_value.find(anchor)
    if start < 0:
        raise RuntimeError(f"Không tìm thấy hàm cần sửa: {function_name}")

    body_markers = ("\n):\n", "\n) ->", "\n):\r\n")
    candidates: list[int] = []
    for marker in body_markers:
        pos = text_value.find(marker, start)
        if pos >= 0:
            candidates.append(pos + len(marker))
    if not candidates:
        raise RuntimeError(f"Không xác định được chữ ký hàm: {function_name}")
    end = min(candidates)
    return start, end


def patch_route_signature(text_value: str, function_name: str) -> str:
    start, end = function_signature_bounds(text_value, function_name)
    block = text_value[start:end]

    for param in PARAMS:
        old = f"{param}: int | None = None"
        new = f"{param}: str | None = None"
        if old in block:
            block = block.replace(old, new, 1)
        elif new not in block:
            raise RuntimeError(
                f"Chữ ký {function_name} không có tham số theo cấu trúc dự kiến: {param}"
            )

    return text_value[:start] + block + text_value[end:]


def patch_source(text_value: str) -> str:
    # Nền V1 phải có bộ chuyển giá trị chuỗi/rỗng -> int | None.
    # Sau hotfix, FastAPI nhận '' dưới dạng chuỗi; _as_int() sẽ xử lý an toàn.
    if "def _as_int(value" not in text_value:
        raise RuntimeError(
            "Không tìm thấy _as_int() của Báo cáo Mầm non mẫu mới V1. "
            "Dừng để tránh sửa nhầm phiên bản source."
        )

    for function_name in ROUTE_FUNCTIONS:
        text_value = patch_route_signature(text_value, function_name)

    if MARKER not in text_value:
        text_value = text_value.rstrip() + f"\n\n# === {MARKER} ===\n"
    return text_value


def verify_source(text_value: str) -> None:
    if MARKER not in text_value:
        raise RuntimeError("Thiếu marker V1.1 sau khi sửa.")

    for function_name in ROUTE_FUNCTIONS:
        start, end = function_signature_bounds(text_value, function_name)
        block = text_value[start:end]
        for param in PARAMS:
            expected = f"{param}: str | None = None"
            if expected not in block:
                raise RuntimeError(
                    f"Kiểm tra sau sửa không đạt: {function_name} / {expected}"
                )

    # Những thành phần quan trọng của V1 vẫn phải còn nguyên.
    required = (
        '@router.get("/bao-cao/mn-01-te"',
        '@router.get("/bao-cao/mn-01-gv-bgd"',
        '@router.get("/bao-cao/mn-01-te/xuat-excel")',
        '@router.get("/bao-cao/mn-01-gv-bgd/xuat-excel")',
        "def _as_int(value",
        "_fill_te_workbook",
        "_fill_gv_workbook",
    )
    for item in required:
        if item not in text_value:
            raise RuntimeError(f"Nguồn V1 sau sửa thiếu thành phần: {item}")


def clear_cache() -> None:
    app_dir = PROJECT / "app"
    for cache in app_dir.rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(cache, ignore_errors=True)


def main() -> int:
    print("=" * 104)
    print("BÁO CÁO MẦM NON MẪU MỚI V1.1 - SỬA LỖI XUẤT EXCEL KHI CHỌN TOÀN TỈNH/TOÀN PHẠM VI")
    print("=" * 104)
    print()
    print("LỖI ĐÃ XÁC ĐỊNH:")
    print(" - Trình duyệt gửi commune_id= và school_id= khi chọn Toàn tỉnh/Tất cả trong phạm vi.")
    print(" - FastAPI V1 đang khai báo hai tham số này là int nên chặn request trước khi vào hàm xử lý.")
    print(" - Kết quả là lỗi JSON: Input should be a valid integer, unable to parse string as an integer.")
    print()
    print("V1.1 SẼ SỬA:")
    print(" - Cho 4 route MN-01-TE / MN-01-GV nhận query rỗng dưới dạng chuỗi.")
    print(" - Dùng lại _as_int() đã có để đổi chuỗi rỗng thành None an toàn.")
    print(" - Sửa cả nút Mở báo cáo và Xuất Excel.")
    print()
    print("AN TOÀN:")
    print(" - KHÔNG sửa database, KHÔNG đổi số liệu, KHÔNG đổi mẫu Excel.")
    print(" - Chỉ sửa app\\routers\\mn_official_reports.py.")
    print(" - Tự backup source trước khi sửa và tự rollback nếu có lỗi.")
    print()

    if not TARGET.exists():
        raise RuntimeError(f"Không tìm thấy: {TARGET}")

    original = read_text(TARGET)
    backup_source()
    print("Backup source trước khi cài:", BACKUP)

    try:
        patched = patch_source(original)
        verify_source(patched)
        TARGET.write_text(patched, encoding="utf-8")

        subprocess.run(
            [sys.executable, "-m", "py_compile", str(TARGET)],
            cwd=PROJECT,
            check=True,
        )
        verify_source(read_text(TARGET))
        clear_cache()

        print()
        print("KIỂM TRA SAU CÀI:")
        print(" - Cú pháp Python: ĐẠT")
        print(" - 4 route nhận query rỗng: ĐẠT")
        print(" - Route xuất Excel MN-01-TE: GIỮ NGUYÊN")
        print(" - Route xuất Excel MN-01-GV: GIỮ NGUYÊN")
        print(" - Database: KHÔNG THAY ĐỔI")
        print(" - Mẫu Excel: KHÔNG THAY ĐỔI")
        print()
        print("CÀI ĐẶT BÁO CÁO MẦM NON MẪU MỚI V1.1 THÀNH CÔNG")
        print("Backup source:", BACKUP)
        print()
        print("BƯỚC TIẾP THEO:")
        print(" 1. Chạy lại Uvicorn.")
        print(" 2. Ctrl+F5 trên trình duyệt.")
        print(" 3. Vào MN-01-TE, giữ Toàn tỉnh/Tất cả rồi bấm Xuất Excel đúng mẫu.")
        print(" 4. Làm tương tự với MN-01-GV.")
        return 0

    except Exception:
        traceback.print_exc()
        print()
        print("CÓ LỖI - ĐANG KHÔI PHỤC SOURCE TRƯỚC V1.1...")
        restore_source()
        clear_cache()
        print("ĐÃ KHÔI PHỤC SOURCE.")
        print("Backup source:", BACKUP)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
