from __future__ import annotations

import py_compile
import sqlite3
from pathlib import Path

from jinja2 import Environment


PROJECT_DIR = Path(__file__).resolve().parent

PYTHON_FILES = (
    PROJECT_DIR / "app" / "access_control.py",
    PROJECT_DIR / "app" / "routers" / "surveys.py",
    PROJECT_DIR / "app" / "main.py",
)

TEMPLATE_FILES = (
    PROJECT_DIR / "app" / "templates" / "index.html",
    PROJECT_DIR / "app" / "templates" / "surveys" / "index.html",
    PROJECT_DIR / "app" / "templates" / "surveys" / "households.html",
)


def main() -> None:
    print("=" * 72)
    print("BÀI 11B-7A - KIỂM TRA PHẠM VI PHIẾU THEO TÀI KHOẢN")
    print("=" * 72)

    for path in PYTHON_FILES:
        py_compile.compile(str(path), doraise=True)
        print(f"OK PYTHON: {path.relative_to(PROJECT_DIR)}")

    environment = Environment()
    for path in TEMPLATE_FILES:
        environment.parse(path.read_text(encoding="utf-8"))
        print(f"OK HTML:   {path.relative_to(PROJECT_DIR)}")

    access_text = (
        PROJECT_DIR / "app" / "access_control.py"
    ).read_text(encoding="utf-8")

    required_markers = (
        '{"SO", "XA", "TRUONG", "GIAO_VIEN"}',
        "survey_form_investigators",
        "_co_quyen_dieu_tra",
    )

    for marker in required_markers:
        if marker not in access_text:
            raise RuntimeError(
                f"Thiếu nội dung kiểm soát quyền: {marker}"
            )

    database_path = PROJECT_DIR / "data" / "phocap.db"
    if database_path.exists():
        connection = sqlite3.connect(str(database_path))
        try:
            assigned_forms = connection.execute(
                """
                SELECT COUNT(DISTINCT survey_form_id)
                FROM survey_form_investigators
                """
            ).fetchone()[0]

            assigned_users = connection.execute(
                """
                SELECT COUNT(DISTINCT user_id)
                FROM survey_form_investigators
                """
            ).fetchone()[0]

            print(f"PHIẾU ĐÃ PHÂN CÔNG: {assigned_forms}")
            print(f"TÀI KHOẢN ĐÃ ĐƯỢC PHÂN CÔNG: {assigned_users}")
        finally:
            connection.close()
    else:
        print("CHƯA ĐỌC CƠ SỞ DỮ LIỆU: không tìm thấy data/phocap.db")

    print("-" * 72)
    print("BÀI 11B-7A ĐÃ SẴN SÀNG.")
    print("Không có dữ liệu nào được thêm, sửa hoặc xóa.")
    print("=" * 72)


if __name__ == "__main__":
    main()
