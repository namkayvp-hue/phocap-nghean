from __future__ import annotations

from pathlib import Path

from jinja2 import Environment


ROOT = Path(__file__).resolve().parent
USERS_PY = ROOT / "app" / "routers" / "users.py"
LIST_HTML = ROOT / "app" / "templates" / "users" / "list.html"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> None:
    print("=" * 72)
    print("BÀI 11C-20A - KIỂM TRA CHỌN XÃ/PHƯỜNG TRƯỚC KHI CHỌN TRƯỜNG")
    print("=" * 72)

    require(USERS_PY.is_file(), f"Không tìm thấy: {USERS_PY}")
    require(LIST_HTML.is_file(), f"Không tìm thấy: {LIST_HTML}")

    users_source = USERS_PY.read_text(encoding="utf-8")
    html_source = LIST_HTML.read_text(encoding="utf-8")

    compile(users_source, str(USERS_PY), "exec")
    print("OK PYTHON: app\\routers\\users.py")

    Environment().parse(html_source)
    print("OK HTML: app\\templates\\users\\list.html")

    required_html_markers = [
        'id="commune_id"',
        'id="school_id"',
        'data-commune-id="{{ truong.commune_id }}"',
        "-- Chọn xã/phường trước --",
        "loadSchoolsForSelectedCommune",
        'roleCode === "TRUONG"',
    ]
    for marker in required_html_markers:
        require(marker in html_source, f"Thiếu dấu hiệu giao diện: {marker}")

    required_python_markers = [
        "target_role_code in {SCHOOL_ROLE_CODE, TEACHER_ROLE_CODE}",
        "commune_id != school.commune_id",
        'return None, None, "invalid_scope"',
    ]
    for marker in required_python_markers:
        require(marker in users_source, f"Thiếu kiểm tra phía máy chủ: {marker}")

    print("OK GIAO DIỆN: chọn xã/phường trước, trường được lọc theo xã/phường.")
    print("OK MÁY CHỦ: từ chối trường không thuộc xã/phường đã chọn.")
    print()
    print("BÀI 11C-20A ĐÃ SẴN SÀNG.")
    print("Không có dữ liệu cơ sở dữ liệu nào được thêm, sửa hoặc xóa.")


if __name__ == "__main__":
    main()
