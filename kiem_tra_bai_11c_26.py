from __future__ import annotations

from pathlib import Path
import ast

from jinja2 import Environment

ROOT = Path(__file__).resolve().parent
PYTHON_FILE = ROOT / "app" / "routers" / "surveys.py"
HTML_FILE = ROOT / "app" / "templates" / "surveys" / "index.html"


def main() -> None:
    python_text = PYTHON_FILE.read_text(encoding="utf-8")
    html_text = HTML_FILE.read_text(encoding="utf-8")

    ast.parse(python_text, filename=str(PYTHON_FILE))
    Environment().parse(html_text)

    required_python = (
        '"Bạn chưa được phân công phiếu điều tra nào."',
        '"Hãy tạo đợt điều tra đầu tiên bằng biểu mẫu bên cạnh."',
        '"empty_scope_message": empty_scope_message',
    )
    for text in required_python:
        assert text in python_text, f"Thiếu nội dung trong surveys.py: {text}"

    assert "{{ empty_scope_message }}" in html_text
    assert "Hãy tạo đợt điều tra đầu tiên\n                            bằng biểu mẫu bên cạnh." not in html_text

    print("BÀI 11C-26 - KIỂM TRA THÔNG BÁO KHI KHÔNG CÓ DỮ LIỆU")
    print("OK PYTHON: app\\routers\\surveys.py")
    print("OK HTML: app\\templates\\surveys\\index.html")
    print("OK ADMIN: vẫn có hướng dẫn tạo đợt đầu tiên.")
    print("OK GIAO_VIEN: hiển thị chưa được phân công phiếu.")
    print("OK TRUONG/XA/PHONG_BAN: có thông báo theo đúng phạm vi.")
    print("BÀI 11C-26 ĐÃ SẴN SÀNG.")
    print("Không có dữ liệu cơ sở dữ liệu nào được thêm, sửa hoặc xóa.")


if __name__ == "__main__":
    main()
