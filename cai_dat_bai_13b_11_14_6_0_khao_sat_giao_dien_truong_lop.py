from __future__ import annotations

import ast
import os
import re
import sqlite3
import traceback
from datetime import datetime
from pathlib import Path


PROJECT = Path(
    os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")
).resolve()

APP = PROJECT / "app"
DB = PROJECT / "data" / "phocap.db"
EXPORTS = PROJECT / "exports"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

REPORT = (
    EXPORTS
    / f"bao_cao_bai_13b_11_14_6_0_khao_sat_giao_dien_truong_lop_{STAMP}.txt"
)

FILES = {
    "main": APP / "main.py",
    "staff_router": APP / "routers" / "staff_management.py",
    "report_inputs_router": APP / "routers" / "report_inputs.py",
    "schools_router": APP / "routers" / "schools.py",
    "access_control": APP / "access_control.py",
    "class_template": APP / "templates" / "staff" / "class_config.html",
    "menu_template": APP / "templates" / "partials" / "dropdown_menu_v1.html",
}


def read_text(path: Path) -> str:
    if not path.exists():
        return ""

    return path.read_text(
        encoding="utf-8-sig",
        errors="ignore",
    )


def add(out: list[str], text: str = "") -> None:
    out.append(text)


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type='table' AND name=?
        LIMIT 1
        """,
        (table,),
    ).fetchone() is not None


def columns(conn: sqlite3.Connection, table: str) -> list[str]:
    if not table_exists(conn, table):
        return []

    return [
        str(row[1])
        for row in conn.execute(
            f'PRAGMA table_info("{table}")'
        ).fetchall()
    ]


def rows(conn: sqlite3.Connection, sql: str, params=()) -> list[tuple]:
    try:
        return conn.execute(sql, params).fetchall()
    except Exception as exc:
        return [("ERROR", str(exc))]


def function_source_by_name(source: str, name: str) -> str:
    try:
        tree = ast.parse(source)
    except Exception:
        return ""

    lines = source.splitlines()

    for node in tree.body:
        if isinstance(
            node,
            (ast.FunctionDef, ast.AsyncFunctionDef),
        ) and node.name == name:
            start = max(0, int(node.lineno) - 1)
            end = int(node.end_lineno)
            return "\n".join(lines[start:end])

    return ""


def functions_containing(source: str, needles: tuple[str, ...]) -> list[tuple[str, str]]:
    try:
        tree = ast.parse(source)
    except Exception:
        return []

    lines = source.splitlines()
    result = []

    for node in tree.body:
        if not isinstance(
            node,
            (ast.FunctionDef, ast.AsyncFunctionDef),
        ):
            continue

        start = max(0, int(node.lineno) - 1)
        end = int(node.end_lineno)
        block = "\n".join(lines[start:end])

        low = block.lower()

        if any(n.lower() in low for n in needles):
            result.append((node.name, block))

    return result


def excerpt_around(
    source: str,
    needles: tuple[str, ...],
    radius: int = 18,
    max_hits: int = 8,
) -> list[str]:
    lines = source.splitlines()
    hit_indexes = []

    for index, line in enumerate(lines):
        low = line.lower()

        if any(n.lower() in low for n in needles):
            hit_indexes.append(index)

    result = []

    for index in hit_indexes[:max_hits]:
        start = max(0, index - radius)
        end = min(len(lines), index + radius + 1)

        chunk = []

        for i in range(start, end):
            chunk.append(
                f"{i + 1:05d}: {lines[i]}"
            )

        result.append("\n".join(chunk))

    return result


def route_summary(source: str) -> list[str]:
    pattern = re.compile(
        r'@(?P<obj>[A-Za-z_][A-Za-z0-9_]*)\.'
        r'(?P<method>get|post|put|patch|delete)'
        r'\(\s*["\'](?P<path>[^"\']+)["\']',
        flags=re.IGNORECASE,
    )

    results = []

    for match in pattern.finditer(source):
        results.append(
            f"{match.group('method').upper()} "
            f"{match.group('path')}"
        )

    return results


def main() -> int:
    print("=" * 126)
    print(
        "BÀI 13B-11.14.6.0 - "
        "KHẢO SÁT ĐIỂM GẮN GIAO DIỆN "
        "TRƯỜNG / ĐIỂM TRƯỜNG / LỚP ĐƠN-LỚP GHÉP"
    )
    print("=" * 126)
    print()
    print("CHỈ ĐỌC:")
    print(" - Không sửa source/template.")
    print(" - Không sửa database.")
    print(" - Không ALTER/INSERT/UPDATE/DELETE.")
    print()
    print("MỤC TIÊU:")
    print(" - Xác định màn cấu hình lớp hiện có.")
    print(" - Xác định menu hiện hành.")
    print(" - Xác định cơ chế phân quyền/current user.")
    print(" - Xác định đúng router để gắn giao diện mới.")
    print(" - Kiểm tra 2 bảng mới của Bài 14.5.")
    print()

    if not DB.exists():
        raise RuntimeError(f"Không tìm thấy DB: {DB}")

    EXPORTS.mkdir(parents=True, exist_ok=True)

    report: list[str] = []

    add(report, "=" * 126)
    add(
        report,
        "BÁO CÁO 13B-11.14.6.0 - "
        "KHẢO SÁT GIAO DIỆN TRƯỜNG/ĐIỂM TRƯỜNG/LỚP",
    )
    add(report, "=" * 126)
    add(report, f"Project: {PROJECT}")
    add(report, f"Database: {DB}")
    add(report, f"Thời điểm: {datetime.now():%d/%m/%Y %H:%M:%S}")
    add(report)

    conn = sqlite3.connect(
        f"file:{DB.as_posix()}?mode=ro",
        uri=True,
    )

    try:
        integrity = str(
            conn.execute(
                "PRAGMA integrity_check"
            ).fetchone()[0]
        )

        fk = conn.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()

        add(report, "I. DATABASE")
        add(report, "-" * 90)
        add(report, f"integrity_check: {integrity}")
        add(report, f"foreign_key_check: {len(fk)} lỗi")

        for table in (
            "schools",
            "school_years",
            "classes",
            "school_site_year_records",
            "school_class_year_attributes",
        ):
            add(report)
            add(report, f"[{table}]")

            if not table_exists(conn, table):
                add(report, "  KHÔNG CÓ BẢNG")
                continue

            cols = columns(conn, table)
            count = int(
                conn.execute(
                    f'SELECT COUNT(*) FROM "{table}"'
                ).fetchone()[0]
            )

            add(report, f"  rows: {count}")
            add(report, "  columns: " + ", ".join(cols))

        add(report)
        add(report, "Mẫu schools:")
        for row in rows(
            conn,
            """
            SELECT id, commune_id, code, name, address, is_active
            FROM schools
            ORDER BY id
            LIMIT 15
            """,
        ):
            add(report, "  " + repr(row))

        add(report)
        add(report, "Mẫu classes + trường + năm:")
        for row in rows(
            conn,
            """
            SELECT
                c.id,
                c.school_id,
                s.name,
                c.school_year_id,
                sy.code,
                c.code,
                c.name,
                c.is_active
            FROM classes c
            LEFT JOIN schools s
                ON s.id = c.school_id
            LEFT JOIN school_years sy
                ON sy.id = c.school_year_id
            ORDER BY c.id
            LIMIT 30
            """,
        ):
            add(report, "  " + repr(row))

        add(report)
        add(report, "Số trường có lớp theo năm:")
        for row in rows(
            conn,
            """
            SELECT
                sy.code,
                COUNT(DISTINCT c.school_id) AS school_count,
                COUNT(*) AS class_count
            FROM classes c
            LEFT JOIN school_years sy
                ON sy.id = c.school_year_id
            GROUP BY sy.code
            ORDER BY sy.code
            """,
        ):
            add(report, "  " + repr(row))

    finally:
        conn.close()

    add(report)
    add(report, "II. MAIN.PY - INCLUDE ROUTER")
    add(report, "-" * 90)

    main_text = read_text(FILES["main"])

    if main_text:
        for chunk in excerpt_around(
            main_text,
            (
                "include_router",
                "staff_management",
                "report_inputs",
                "schools",
            ),
            radius=10,
            max_hits=12,
        ):
            add(report, chunk)
            add(report)
    else:
        add(report, "Không đọc được app/main.py")

    add(report)
    add(report, "III. STAFF_MANAGEMENT - CẤU HÌNH LỚP")
    add(report, "-" * 90)

    staff_text = read_text(FILES["staff_router"])

    if staff_text:
        add(report, "Routes phát hiện:")
        for item in route_summary(staff_text):
            if (
                "lop" in item.lower()
                or "class" in item.lower()
                or "doi-ngu" in item.lower()
            ):
                add(report, "  - " + item)

        matches = functions_containing(
            staff_text,
            (
                "cau-hinh-lop",
                "class_config",
                "classes",
            ),
        )

        for name, block in matches[:8]:
            add(report)
            add(report, f"--- FUNCTION {name} ---")
            add(report, block)
    else:
        add(report, "Không đọc được staff_management.py")

    add(report)
    add(report, "IV. TEMPLATE CẤU HÌNH LỚP")
    add(report, "-" * 90)

    class_template = read_text(FILES["class_template"])

    if class_template:
        for chunk in excerpt_around(
            class_template,
            (
                "<form",
                "school",
                "class",
                "lớp",
                "năm học",
                "save",
                "lưu",
            ),
            radius=12,
            max_hits=12,
        ):
            add(report, chunk)
            add(report)
    else:
        add(report, "Không đọc được staff/class_config.html")

    add(report)
    add(report, "V. REPORT_INPUTS - MẪU PHÂN QUYỀN/CHỌN ĐƠN VỊ")
    add(report, "-" * 90)

    report_inputs_text = read_text(
        FILES["report_inputs_router"]
    )

    if report_inputs_text:
        add(report, "Routes:")
        for item in route_summary(report_inputs_text):
            add(report, "  - " + item)

        for name, block in functions_containing(
            report_inputs_text,
            (
                "current_user",
                "school_id",
                "commune_id",
                "session",
                "role",
                "csvc",
            ),
        )[:10]:
            add(report)
            add(report, f"--- FUNCTION {name} ---")
            add(report, block)
    else:
        add(report, "Không đọc được report_inputs.py")

    add(report)
    add(report, "VI. SCHOOLS ROUTER")
    add(report, "-" * 90)

    schools_text = read_text(FILES["schools_router"])

    if schools_text:
        add(report, "Routes:")
        for item in route_summary(schools_text):
            add(report, "  - " + item)

        for chunk in excerpt_around(
            schools_text,
            (
                "school_level",
                "level_code",
                "commune_id",
                "current_user",
                "role",
                "school_id",
            ),
            radius=12,
            max_hits=8,
        ):
            add(report, chunk)
            add(report)
    else:
        add(report, "Không đọc được schools.py")

    add(report)
    add(report, "VII. MENU HIỆN HÀNH")
    add(report, "-" * 90)

    menu_text = read_text(FILES["menu_template"])

    if menu_text:
        for chunk in excerpt_around(
            menu_text,
            (
                "danh mục",
                "đội ngũ",
                "csvc",
                "cấu hình lớp",
                "lớp",
                "trường",
                "báo cáo",
            ),
            radius=14,
            max_hits=16,
        ):
            add(report, chunk)
            add(report)
    else:
        add(report, "Không đọc được dropdown_menu_v1.html")

    add(report)
    add(report, "VIII. ACCESS CONTROL / SESSION")
    add(report, "-" * 90)

    access_text = read_text(FILES["access_control"])

    if access_text:
        for chunk in excerpt_around(
            access_text,
            (
                "request.session",
                "current_user",
                "role",
                "school_id",
                "commune_id",
                "unit",
            ),
            radius=10,
            max_hits=12,
        ):
            add(report, chunk)
            add(report)
    else:
        add(report, "Không đọc được access_control.py")

    add(report)
    add(report, "IX. KẾT LUẬN DÀNH CHO BÀI 14.6.1")
    add(report, "-" * 90)
    add(
        report,
        "Báo cáo này dùng để chọn đúng một trong hai phương án:",
    )
    add(
        report,
        "A. Mở rộng trực tiếp màn Cấu hình lớp hiện có;",
    )
    add(
        report,
        "B. Tạo màn Nguồn nhập Trường/Lớp riêng nhưng tái sử dụng "
        "classes và cơ chế phân quyền hiện có.",
    )
    add(
        report,
        "Không quyết định phương án trước khi đọc source thật.",
    )
    add(report)
    add(report, "CAM KẾT: CHỈ ĐỌC, KHÔNG THAY ĐỔI SOURCE/DB.")

    REPORT.write_text(
        "\n".join(report),
        encoding="utf-8-sig",
    )

    print("Khảo sát hoàn thành.")
    print("Báo cáo:", REPORT)
    print("Database/source: KHÔNG THAY ĐỔI.")
    print("integrity_check:", integrity)
    print("foreign_key_check:", len(fk), "lỗi")
    print()
    print("=" * 126)
    print("BÀI 13B-11.14.6.0 KHẢO SÁT THÀNH CÔNG")
    print("=" * 126)

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        traceback.print_exc()
        print()
        print(
            "KHẢO SÁT GẶP LỖI. "
            "Bài này chỉ đọc nên source/database không bị thay đổi."
        )
        raise
