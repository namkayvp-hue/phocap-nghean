from __future__ import annotations

import ast
import os
import re
from datetime import datetime
from pathlib import Path

PROJECT = Path(os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")).resolve()
APP = PROJECT / "app"
EXPORTS = PROJECT / "exports"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
REPORT = EXPORTS / (
    f"bao_cao_khao_sat_bai_13b_11_15_2_4_8_0_"
    f"nam_hoc_lam_viec_toan_he_thong_{STAMP}.txt"
)

PY_HINTS = (
    "SessionMiddleware",
    "request.session",
    "school_year_id",
    "SchoolYear",
    "school_year",
    "login",
    "logout",
    "TemplateResponse",
    "RedirectResponse",
)

HTML_HINTS = (
    "school_year_id",
    "Năm học",
    "nam_hoc",
    "Đăng xuất",
    "user",
    "current_user",
    "base.html",
)

PRIORITY_NAMES = {
    "main.py",
    "auth.py",
    "dependencies.py",
    "report_center.py",
    "reports.py",
    "surveys.py",
    "base.html",
    "layout.html",
    "index.html",
}


def read_text(path: Path) -> str:
    return path.read_text(
        encoding="utf-8-sig",
        errors="replace",
    )


def line_hits(text: str, hints) -> list[tuple[int, str]]:
    hits = []
    for i, line in enumerate(text.splitlines(), start=1):
        if any(h.lower() in line.lower() for h in hints):
            hits.append((i, line.rstrip()))
    return hits


def scan_python(path: Path) -> dict:
    text = read_text(path)
    syntax = "OK"
    functions = []

    try:
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                fn_text = "\n".join(
                    text.splitlines()[
                        max(0, node.lineno - 1):
                        min(len(text.splitlines()), (node.end_lineno or node.lineno))
                    ]
                )
                if any(
                    h.lower() in fn_text.lower()
                    for h in ("school_year", "session", "login", "logout")
                ):
                    functions.append(
                        f"{node.name} (L{node.lineno}-L{node.end_lineno})"
                    )
    except Exception as exc:
        syntax = f"LỖI: {exc}"

    return {
        "syntax": syntax,
        "hits": line_hits(text, PY_HINTS),
        "functions": functions,
    }


def scan_html(path: Path) -> dict:
    text = read_text(path)
    return {
        "hits": line_hits(text, HTML_HINTS),
    }


def main() -> None:
    print("=" * 142)
    print(
        "BÀI 13B-11.15.2.4.8.0 - KHẢO SÁT NĂM HỌC LÀM VIỆC TOÀN HỆ THỐNG"
    )
    print("=" * 142)
    print()
    print("CHỈ ĐỌC:")
    print(" - Không sửa source.")
    print(" - Không sửa database.")
    print(" - Không sửa menu/route/template.")
    print()

    if not APP.exists():
        raise RuntimeError(f"Không tìm thấy thư mục app: {APP}")

    EXPORTS.mkdir(parents=True, exist_ok=True)

    py_files = sorted(
        p for p in APP.rglob("*.py")
        if "__pycache__" not in p.parts
        and "backup" not in str(p).lower()
    )

    html_files = sorted(
        p for p in APP.rglob("*.html")
        if "backup" not in str(p).lower()
    )

    py_results = []
    html_results = []

    for path in py_files:
        result = scan_python(path)
        if result["hits"] or result["functions"] or path.name in PRIORITY_NAMES:
            py_results.append((path, result))

    for path in html_files:
        result = scan_html(path)
        if result["hits"] or path.name in PRIORITY_NAMES:
            html_results.append((path, result))

    lines = [
        "=" * 142,
        "BÀI 13B-11.15.2.4.8.0 - KẾT QUẢ KHẢO SÁT",
        "=" * 142,
        "",
        "MỤC TIÊU NGHIỆP VỤ:",
        " - Sau đăng nhập chọn 1 Năm học làm việc.",
        " - Năm học đó giữ cố định cho mọi màn hình cho đến khi người dùng đổi.",
        " - Áp dụng cho Sở / Xã / Trường / Giáo viên.",
        " - Không được làm thay đổi các quy tắc khóa/mở dữ liệu hiện có.",
        "",
        "CẦN XÁC ĐỊNH:",
        " 1. Hệ thống đã có SessionMiddleware/request.session hay chưa.",
        " 2. Route đăng nhập/đăng xuất nằm ở đâu.",
        " 3. Base template/header dùng chung nằm ở đâu.",
        " 4. Các route hiện đang nhận school_year_id bằng query/form như thế nào.",
        " 5. Có helper dùng chung để lấy năm học hay chưa.",
        "",
        "=" * 142,
        "PYTHON",
        "=" * 142,
    ]

    for path, result in py_results:
        rel = path.relative_to(PROJECT)
        lines.append("")
        lines.append(f"[{rel}]")
        lines.append(f"AST: {result['syntax']}")

        if result["functions"]:
            lines.append("Hàm liên quan:")
            for fn in result["functions"][:40]:
                lines.append(f" - {fn}")

        if result["hits"]:
            lines.append("Dòng liên quan:")
            for lineno, text in result["hits"][:100]:
                lines.append(f" L{lineno}: {text}")

    lines.extend(
        [
            "",
            "=" * 142,
            "TEMPLATE",
            "=" * 142,
        ]
    )

    for path, result in html_results:
        rel = path.relative_to(PROJECT)
        lines.append("")
        lines.append(f"[{rel}]")

        if result["hits"]:
            for lineno, text in result["hits"][:100]:
                lines.append(f" L{lineno}: {text}")

    lines.extend(
        [
            "",
            "=" * 142,
            "ĐỀ XUẤT KIẾN TRÚC SAU KHẢO SÁT",
            "=" * 142,
            "",
            " - session['working_school_year_id'] lưu năm học làm việc của phiên đăng nhập.",
            " - Header chung hiển thị selector 'Năm học làm việc'.",
            " - Route đổi năm học cập nhật session rồi quay lại trang trước.",
            " - Các màn hình đang có school_year_id vẫn giữ route cũ; chỉ lấy session làm mặc định.",
            " - Không xóa dropdown cũ ở bước đầu để tránh phá luồng; tự chọn sẵn đúng năm học làm việc.",
            " - Đổi năm học tại selector chung phải áp dụng ngay cho các mục tiếp theo.",
            " - Đăng xuất xóa session năm học làm việc.",
            " - Nếu năm học không còn hợp lệ, hệ thống yêu cầu chọn lại.",
            "",
        ]
    )

    REPORT.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )

    print("Khảo sát source: OK")
    print("Python file liên quan:", len(py_results))
    print("Template liên quan:", len(html_results))
    print()
    print("Báo cáo:", REPORT)
    print()
    print("=" * 142)
    print("KHẢO SÁT BÀI 13B-11.15.2.4.8.0 THÀNH CÔNG")
    print("=" * 142)


if __name__ == "__main__":
    main()
