# -*- coding: utf-8 -*-
from __future__ import annotations

import ast
import re
from datetime import datetime
from pathlib import Path

PROJECT = Path(r"C:\PhoCap")
APP = PROJECT / "app"
EXPORTS = PROJECT / "exports"

TARGET_FILES = [
    APP / "routers" / "pcgdmn_template_report.py",
    APP / "routers" / "mn_official_reports.py",
    APP / "routers" / "survey_summary_report.py",
    APP / "services" / "mn_report_v246.py",
    APP / "routers" / "report_center.py",
    APP / "main.py",
    APP / "templates" / "partials" / "dropdown_menu_v1.html",
    APP / "templates" / "reports" / "pcgdmn_template_report.html",
]

KEYWORDS = [
    "MN-01-TE",
    "MN-01-GV",
    "MN-01-CSVC",
    "MN-02",
    "MN - Tài chính",
    "MN- Trẻ KT",
    "Sổ theo dõi PCGDMN",
    "MN_Tre_KT",
    "So_theo_doi_PCGDMN",
    "PCGD_MN_02",
    "PCGD_MN_01_CSVC",
    "PCGD_MN_TAICHINH",
    "mn-01-te",
    "mn-01-gv",
    "mn-01-csvc",
    "tre-khuyet-tat",
    "so-theo-doi",
    "xuat-bieu",
    "report_type",
]

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
REPORT = EXPORTS / f"bao_cao_khao_sat_v2_4_3_3_route_thuc_te_7_bieu_mn_{STAMP}.txt"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="replace")


def route_decorators(node: ast.AST) -> list[str]:
    result = []
    for dec in getattr(node, "decorator_list", []):
        if not isinstance(dec, ast.Call):
            continue
        func = dec.func
        attr = getattr(func, "attr", None)
        if attr not in {"get", "post", "put", "delete", "patch", "api_route"}:
            continue
        path = None
        if dec.args:
            arg = dec.args[0]
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                path = arg.value
        result.append(f"{attr.upper()} {path or '<dynamic>'}")
    return result


def source_segment(lines: list[str], node: ast.AST) -> str:
    start = max(0, getattr(node, "lineno", 1) - 1)
    end = min(len(lines), getattr(node, "end_lineno", start + 1))
    return "\n".join(
        f"{i+1:05d}: {lines[i]}"
        for i in range(start, end)
    )


def scan_python(path: Path) -> list[str]:
    text = read_text(path)
    lines = text.splitlines()
    out = []

    out.append("#" * 120)
    out.append(f"FILE: {path}")
    out.append("-" * 120)

    try:
        tree = ast.parse(text)
    except Exception as exc:
        out.append(f"AST ERROR: {type(exc).__name__}: {exc}")
        return out

    # Router prefix / APIRouter declarations.
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            value = getattr(node, "value", None)
            if isinstance(value, ast.Call):
                name = getattr(value.func, "id", None) or getattr(value.func, "attr", None)
                if name == "APIRouter":
                    out.append("APIRouter declaration:")
                    out.append(source_segment(lines, node))

    # Mapping constants that may route sheet codes.
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            segment = source_segment(lines, node)
            if any(k.lower() in segment.lower() for k in (
                "SINGLE_SHEET_EXPORTS",
                "OLD_TO_NEW",
                "REPORT",
                "sheet_code",
                "filename",
            )):
                if any(k.lower() in segment.lower() for k in KEYWORDS):
                    out.append("")
                    out.append("MAPPING/CONSTANT LIÊN QUAN:")
                    out.append(segment)

    # Functions / routes whose source contains report keywords.
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        segment_plain = "\n".join(lines[node.lineno-1:getattr(node, "end_lineno", node.lineno)])
        routes = route_decorators(node)
        hit = routes or any(k.lower() in segment_plain.lower() for k in KEYWORDS)
        if not hit:
            continue
        if routes or any(k.lower() in segment_plain.lower() for k in KEYWORDS):
            out.append("")
            out.append("-" * 100)
            out.append(f"FUNCTION: {node.name}")
            if routes:
                out.append("ROUTES: " + " | ".join(routes))
            matched = [k for k in KEYWORDS if k.lower() in segment_plain.lower()]
            if matched:
                out.append("KEYWORDS: " + ", ".join(matched))
            # Full function body for key export builders/routes; cap extremely long functions.
            if len(segment_plain.splitlines()) <= 260:
                out.append(source_segment(lines, node))
            else:
                out.append(f"[Hàm dài {len(segment_plain.splitlines())} dòng - chỉ in các dòng chứa từ khóa]")
                for i in range(node.lineno-1, getattr(node, "end_lineno", node.lineno)):
                    line = lines[i]
                    if any(k.lower() in line.lower() for k in KEYWORDS):
                        lo = max(node.lineno-1, i-4)
                        hi = min(getattr(node, "end_lineno", node.lineno), i+5)
                        out.extend(
                            f"{j+1:05d}: {lines[j]}"
                            for j in range(lo, hi)
                        )

    return out


def scan_text(path: Path) -> list[str]:
    text = read_text(path)
    lines = text.splitlines()
    out = [
        "#" * 120,
        f"FILE: {path}",
        "-" * 120,
    ]
    hit_lines = []
    for i, line in enumerate(lines):
        if any(k.lower() in line.lower() for k in KEYWORDS):
            hit_lines.append(i)

    seen = set()
    for i in hit_lines:
        lo = max(0, i - 5)
        hi = min(len(lines), i + 6)
        key = (lo, hi)
        if key in seen:
            continue
        seen.add(key)
        out.append("")
        for j in range(lo, hi):
            out.append(f"{j+1:05d}: {lines[j]}")
    return out


def runtime_routes() -> list[str]:
    out = [
        "=" * 120,
        "RUNTIME ROUTES APP.MAIN",
        "=" * 120,
    ]
    try:
        from app.main import app
    except Exception as exc:
        out.append(f"KHÔNG IMPORT ĐƯỢC app.main: {type(exc).__name__}: {exc}")
        return out

    rows = []
    for route in getattr(app, "routes", []):
        path = str(getattr(route, "path", "") or "")
        name = str(getattr(route, "name", "") or "")
        methods = ",".join(sorted(getattr(route, "methods", []) or []))
        endpoint = getattr(route, "endpoint", None)
        module = getattr(endpoint, "__module__", "") if endpoint else ""
        fn = getattr(endpoint, "__name__", "") if endpoint else ""
        hay = f"{path} {name} {module} {fn}".lower()
        if any(k.lower() in hay for k in (
            "mn",
            "pcgdmn",
            "bao-cao",
            "tre-khuyet-tat",
            "so-theo-doi",
        )):
            rows.append((path, methods, name, module, fn))

    for row in sorted(rows):
        out.append(
            f"path={row[0]} | methods={row[1]} | name={row[2]} | endpoint={row[3]}.{row[4]}"
        )
    if not rows:
        out.append("Không tìm thấy route liên quan.")
    return out


def main() -> int:
    print("=" * 120)
    print("BÀI 13B-12 V2.4.3.3 - KHẢO SÁT CHỈ ĐỌC ROUTE THỰC TẾ 7 BIỂU MẦM NON")
    print("=" * 120)

    if not APP.exists():
        print("DỪNG: Không tìm thấy C:\\PhoCap\\app")
        return 2

    EXPORTS.mkdir(parents=True, exist_ok=True)

    sections = [
        "=" * 120,
        "BÀI 13B-12 V2.4.3.3 - KHẢO SÁT CHỈ ĐỌC ROUTE THỰC TẾ 7 BIỂU MẦM NON",
        "=" * 120,
        f"Thời gian: {datetime.now():%d/%m/%Y %H:%M:%S}",
        "",
        "MỤC TIÊU:",
        "- Xác định chính xác 7 nút xuất Excel hiện đang chạy qua endpoint/module nào.",
        "- Khóa nguyên nhân vì V2.4.3 đã sửa một pipeline nhưng ảnh xuất vẫn cho thấy nhiều pipeline khác nhau.",
        "- KHÔNG sửa source/database/template.",
        "",
    ]

    sections.extend(runtime_routes())
    sections.append("")

    # Thêm các file mục tiêu tồn tại.
    scanned = set()
    for path in TARGET_FILES:
        if path.exists():
            scanned.add(path.resolve())
            if path.suffix.lower() == ".py":
                sections.extend(scan_python(path))
            else:
                sections.extend(scan_text(path))
            sections.append("")

    # Quét bổ sung toàn bộ routers/templates để không bỏ sót route cũ.
    sections.extend([
        "=" * 120,
        "QUÉT BỔ SUNG ROUTERS/TEMPLATES CÓ TỪ KHÓA 7 BIỂU",
        "=" * 120,
    ])

    roots = [
        APP / "routers",
        APP / "templates",
        APP / "services",
    ]
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in {".py", ".html"}:
                continue
            if path.resolve() in scanned:
                continue
            try:
                text = read_text(path)
            except Exception:
                continue
            if not any(k.lower() in text.lower() for k in KEYWORDS):
                continue
            scanned.add(path.resolve())
            if path.suffix.lower() == ".py":
                sections.extend(scan_python(path))
            else:
                sections.extend(scan_text(path))
            sections.append("")

    REPORT.write_text("\n".join(sections) + "\n", encoding="utf-8-sig")

    print("ĐÃ TẠO BÁO CÁO CHỈ ĐỌC:")
    print(REPORT)
    print()
    print("Không có source/database/template nào bị sửa.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
