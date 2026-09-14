# -*- coding: utf-8 -*-
r"""
V12.1 - HỖ TRỢ ĐẦY ĐỦ TRẠNG THÁI HỌC SINH KHI NẠP NGUỒN ĐỐI CHIẾU
====================================================================

Sửa đúng 1 file:
    C:\PhoCap\app\routers\student_reconciliation_source.py

Không sửa database, không nạp dữ liệu.
"""

from __future__ import annotations

import ast
import py_compile
import shutil
from datetime import datetime
from pathlib import Path


PROJECT = Path(r"C:\PhoCap")
TARGET = PROJECT / "app" / "routers" / "student_reconciliation_source.py"
EXPORTS = PROJECT / "exports"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP_DIR = EXPORTS / f"backup_v12_1_status_hoc_sinh_{STAMP}"
BACKUP_FILE = BACKUP_DIR / "app" / "routers" / "student_reconciliation_source.py"
REPORT = EXPORTS / f"bao_cao_v12_1_status_hoc_sinh_{STAMP}.txt"

MARK_START = "# === V12_1_STUDENT_STATUS_NORMALIZATION_START ==="
MARK_END = "# === V12_1_STUDENT_STATUS_NORMALIZATION_END ==="

OLD_FUNCTION = """def _normalize_status(value: Any) -> tuple[str, bool] | None:
    text_value = _optional_text(value)
    if not text_value:
        return "DANG_HOC", True
    return STATUS_MAP.get(_normalize(text_value))
"""

NEW_FUNCTION = """# === V12_1_STUDENT_STATUS_NORMALIZATION_START ===
def _normalize_status(value: Any) -> tuple[str, bool] | None:
    text_value = _optional_text(value)
    if not text_value:
        return "DANG_HOC", True

    key = _normalize(text_value)

    exact = STATUS_MAP.get(key)
    if exact is not None:
        return exact

    if key == "dang hoc" or key.startswith("dang hoc "):
        return "DANG_HOC", True

    # Nguồn thực tế có 'Nghỉ học xin học lại kỳ 1':
    # đã xin học lại => coi là còn hiệu lực.
    if "nghi hoc xin hoc lai" in key:
        return "DANG_HOC", True

    if key.startswith("chuyen den"):
        if "ky 2" in key or "hoc ky 2" in key:
            return "CHUYEN_DEN_KY_2", True
        return "CHUYEN_DEN_KY_1", True

    if key.startswith("chuyen di"):
        return "CHUYEN_DI", False

    if key.startswith("thoi hoc") or key.startswith("bo hoc"):
        return "THOI_HOC", False

    if key.startswith("tam nghi") or key.startswith("nghi hoc"):
        return "TAM_NGHI", False

    return None
# === V12_1_STUDENT_STATUS_NORMALIZATION_END ===
"""


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def backup() -> None:
    BACKUP_FILE.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(TARGET, BACKUP_FILE)


def restore() -> None:
    if BACKUP_FILE.exists():
        TARGET.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(BACKUP_FILE, TARGET)


def patch(source: str) -> tuple[str, str]:
    if MARK_START in source and MARK_END in source:
        return source, "ALREADY_INSTALLED"

    required = (
        'prefix="/dieu-tra/nguon-hoc-sinh-doi-chieu"',
        "STATUS_MAP = {",
        "def _normalize_status(value: Any)",
        "Trạng thái học sinh chưa được hỗ trợ.",
    )
    missing = [x for x in required if x not in source]
    if missing:
        raise RuntimeError(
            "Router không đúng nền V12; thiếu marker: " + repr(missing)
        )

    if source.count(OLD_FUNCTION) != 1:
        raise RuntimeError(
            "Không tìm thấy đúng 1 hàm _normalize_status của V12. "
            "Dừng để tránh sửa nhầm source."
        )

    return source.replace(OLD_FUNCTION, NEW_FUNCTION, 1), "PATCHED"


def verify(source: str) -> None:
    ast.parse(source)

    required = (
        MARK_START,
        MARK_END,
        '"CHUYEN_DI", False',
        '"THOI_HOC", False',
        '"TAM_NGHI", False',
        '"CHUYEN_DEN_KY_1", True',
        '"CHUYEN_DEN_KY_2", True',
        '"DANG_HOC", True',
        '"nghi hoc xin hoc lai"',
        'key.startswith("chuyen di")',
        'key.startswith("thoi hoc")',
    )
    missing = [x for x in required if x not in source]
    if missing:
        raise RuntimeError(
            "Hậu kiểm V12.1 thiếu nội dung: " + repr(missing)
        )

    if source.count(MARK_START) != 1 or source.count(MARK_END) != 1:
        raise RuntimeError("Marker V12.1 bị lặp.")


def main() -> int:
    print("=" * 112)
    print("V12.1 - HỖ TRỢ ĐẦY ĐỦ TRẠNG THÁI HỌC SINH")
    print("=" * 112)

    if not TARGET.exists():
        print(f"Không tìm thấy: {TARGET}")
        return 2

    EXPORTS.mkdir(parents=True, exist_ok=True)
    BACKUP_DIR.mkdir(parents=True, exist_ok=False)
    backup()

    try:
        before = read_text(TARGET)
        after, mode = patch(before)
        verify(after)

        if mode == "PATCHED":
            TARGET.write_text(after, encoding="utf-8")
            py_compile.compile(str(TARGET), doraise=True)

        REPORT.write_text(
            f"""V12.1 - HỖ TRỢ ĐẦY ĐỦ TRẠNG THÁI HỌC SINH
====================================================

MODE: {mode}

ĐÃ HỖ TRỢ:
- Đang học -> DANG_HOC / current=1
- Chuyển đến kỳ 1 / trong hè -> CHUYEN_DEN_KY_1 / current=1
- Chuyển đến kỳ 2 -> CHUYEN_DEN_KY_2 / current=1
- Chuyển đi mọi kỳ / trong hè -> CHUYEN_DI / current=0
- Thôi học / bỏ học mọi kỳ -> THOI_HOC / current=0
- Tạm nghỉ / nghỉ học -> TAM_NGHI / current=0
- Nghỉ học xin học lại -> DANG_HOC / current=1

DATABASE: KHÔNG THAY ĐỔI
BACKUP: {BACKUP_DIR}
""",
            encoding="utf-8",
        )

        print("CÀI V12.1 THÀNH CÔNG")
        print(f"Mode: {mode}")
        print("Database: KHÔNG THAY ĐỔI")
        print(f"Backup: {BACKUP_DIR}")
        print(f"Report: {REPORT}")
        print()
        print("KỲ VỌNG KHI KIỂM TRA LẠI FILE TH NGHI LỘC:")
        print(" - Dòng hợp lệ: 4581")
        print(" - Học sinh duy nhất: 4567")
        print(" - Trường: 5")
        print(" - Lớp: 120")
        print(" - Mã chuyển trường: 14")
        print(" - Lỗi: 0")
        print(" - Cảnh báo: 14")
        return 0

    except Exception as exc:
        print()
        print("CÓ LỖI V12.1:", repr(exc))
        print("Đang khôi phục router cũ...")
        restore()
        print("Đã khôi phục. Database không thay đổi.")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
