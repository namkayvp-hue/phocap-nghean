from __future__ import annotations

import ast
from pathlib import Path

from jinja2 import Environment


ROOT = Path(r"C:\PhoCap")
APP_ROOT = ROOT / "app"

REQUIRED_FILES = [
    APP_ROOT / "permissions.py",
    APP_ROOT / "access_control.py",
    APP_ROOT / "routers" / "users.py",
    APP_ROOT / "routers" / "schools.py",
    APP_ROOT / "routers" / "surveys.py",
    APP_ROOT / "templates" / "index.html",
    APP_ROOT / "templates" / "users" / "list.html",
    APP_ROOT / "templates" / "users" / "edit.html",
    APP_ROOT / "templates" / "schools" / "list.html",
    APP_ROOT / "templates" / "surveys" / "households.html",
    APP_ROOT / "templates" / "surveys" / "people.html",
    APP_ROOT / "templates" / "surveys" / "form_status.html",
    APP_ROOT / "templates" / "surveys" / "year_records.html",
]


def read(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Thiếu tệp: {path}")
    return path.read_text(encoding="utf-8")


def main() -> None:
    print("=" * 72)
    print("BÀI 11C-4 - KIỂM TRA MÃ NGUỒN PHÂN QUYỀN MỚI")
    print("=" * 72)

    for path in REQUIRED_FILES:
        if not path.exists():
            raise FileNotFoundError(f"Thiếu tệp bắt buộc: {path}")

    python_files = sorted(APP_ROOT.rglob("*.py"))
    for path in python_files:
        ast.parse(read(path), filename=str(path))
    print(f"OK PYTHON: {len(python_files)} tệp hợp lệ.")

    environment = Environment()
    html_files = sorted((APP_ROOT / "templates").rglob("*.html"))
    for path in html_files:
        environment.parse(read(path))
    print(f"OK HTML: {len(html_files)} tệp hợp lệ.")

    permissions = read(APP_ROOT / "permissions.py")
    access = read(APP_ROOT / "access_control.py")
    users = read(APP_ROOT / "routers" / "users.py")
    schools = read(APP_ROOT / "routers" / "schools.py")
    surveys = read(APP_ROOT / "routers" / "surveys.py")
    form_status = read(
        APP_ROOT / "templates" / "surveys" / "form_status.html"
    )
    people = read(APP_ROOT / "templates" / "surveys" / "people.html")
    year_records = read(
        APP_ROOT / "templates" / "surveys" / "year_records.html"
    )

    assert 'ADMIN_ROLE_CODE = "ADMIN"' in permissions
    assert 'DEPARTMENT_ROLE_CODE = "PHONG_BAN"' in permissions
    assert 'LEGACY_ADMIN_ROLE_CODE = "SO"' in permissions
    assert 'READ_ONLY_DATA_ROLE_CODES' in permissions

    assert '("/tai-khoan", ACCOUNT_MANAGEMENT_ROLE_CODES)' in access
    assert '("/hoc-sinh/api", SURVEY_ROLE_CODES)' in access
    assert 'admin_only_survey_fragments' in access
    assert 'is_school_report_path' in access
    assert 'role_code == TEACHER_ROLE_CODE' in access

    assert 'def vai_tro_duoc_tao' in users
    assert 'return {TEACHER_ROLE_CODE}' in users
    assert 'User.school_id == int(school_id)' in users
    assert 'cannot_self' in users

    assert 'co_quyen_quan_ly' in schools
    assert 'School.commune_id == int(actor["commune_id"])' in schools

    assert 'def tao_bo_loc_bao_cao_theo_nguoi_dung' in surveys
    assert 'can_confirm_commune = is_admin_role(role_code)' in surveys
    assert '"can_edit_data": can_edit_data' in surveys
    assert '*tao_bo_loc_bao_cao_theo_nguoi_dung(request)' in surveys

    assert 'Chế độ chỉ xem' in form_status
    assert '{% if can_edit_data %}' in people
    assert 'Tài khoản được xem lịch sử năm học' in year_records

    print("OK QUYỀN ADMIN: quản trị toàn tỉnh và quản lý tài khoản.")
    print("OK QUYỀN PHONG_BAN: chỉ xem, theo dõi và xuất báo cáo toàn tỉnh.")
    print("OK QUYỀN XA: chỉ xem trường và dữ liệu thuộc xã/phường.")
    print("OK QUYỀN TRUONG: quản lý giáo viên, xem/xuất báo cáo trường.")
    print("OK QUYỀN GIAO_VIEN: sửa phiếu được phân công, xem báo cáo trường.")
    print()
    print("BÀI 11C-4 ĐÃ SẴN SÀNG.")
    print("Chưa chuyển vai trò của admin.sogddt và p_gdmn.")
    print("Không có dữ liệu nào được thêm, sửa hoặc xóa.")


if __name__ == "__main__":
    main()
