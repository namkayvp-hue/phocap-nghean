from __future__ import annotations

import ast
import os
import py_compile
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path


PROJECT = Path(
    os.environ.get(
        "PHOCAP_PROJECT",
        r"C:\PhoCap",
    )
).resolve()

APP = PROJECT / "app"
EXPORTS = PROJECT / "exports"
DB = PROJECT / "data" / "phocap.db"

SERVICE = APP / "services" / "mn_report_v246.py"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = EXPORTS / f"backup_bai_13b_11_15_2_4_6_1_{STAMP}"
REPORT = EXPORTS / f"bao_cao_bai_13b_11_15_2_4_6_1_{STAMP}.txt"

MARKER = "# === BAI_13B_11_15_2_4_6_1_HIEN_DAU_PHAN_TRAM ==="
CALL_MARKER = "# === BAI_13B_11_15_2_4_6_1_CALL_PERCENT_FORMAT ==="


PERCENT_HELPERS = r"""
# === BAI_13B_11_15_2_4_6_1_HIEN_DAU_PHAN_TRAM ===
def _v2461_percent_format(
    cell: Any,
) -> None:
    # Giá trị tỷ lệ hiện đang ở thang 0..100.
    # Ví dụ 100.00 nghĩa là 100%, nên phải dùng dấu % literal.
    # KHÔNG dùng 0.00% vì Excel sẽ hiển thị 100 thành 10000%.
    cell.number_format = r'0.00\%'


def _v2461_format_refs(
    ws: Any,
    refs: tuple[str, ...] | list[str],
) -> None:
    for ref in refs:
        _v2461_percent_format(ws[ref])


def _v2461_format_column_rows(
    ws: Any,
    columns: tuple[str, ...],
    start_row: int,
    end_row: int,
) -> None:
    for row in range(int(start_row), int(end_row) + 1):
        for col in columns:
            _v2461_percent_format(ws[f"{col}{row}"])


def _apply_percent_display_v2461(
    workbook: Any,
) -> None:
    # 1) MN-01-TE mẫu mới.
    ws = _sheet(
        workbook,
        "Thống kê trẻ em từ 0 đến 5 tuổi",
    )
    if ws is not None:
        refs = []
        for col in ("F", "G", "H", "I", "J", "K", "L", "M"):
            refs.extend(
                (
                    f"{col}16",
                    f"{col}22",
                    f"{col}28",
                )
            )

        refs.extend(
            (
                "F35",
                "F36",
                "F37",
                "F38",
                "F40",
                "F41",
                "F42",
            )
        )
        _v2461_format_refs(ws, refs)

    # 2) MN-02 đang xuất thực tế.
    ws = _sheet(
        workbook,
        "Thống kê kết quả PCGD MN",
    )
    if ws is not None:
        _v2461_format_refs(
            ws,
            (
                "H7",
                "K7",
                "O7",
            ),
        )

    # 3) TK đạt chuẩn: L, N, R là tỷ lệ %.
    ws = _sheet(
        workbook,
        "TK dat chuan",
    )
    if ws is not None:
        _v2461_format_column_rows(
            ws,
            ("L", "N", "R"),
            8,
            int(ws.max_row),
        )

    # 4) MN-02 trong bộ 7 sheet master.
    ws = _sheet(
        workbook,
        "MN-02",
    )
    if ws is not None:
        _v2461_format_column_rows(
            ws,
            ("L",),
            8,
            int(ws.max_row),
        )

    # 5) GV: N = GV/lớp là tỷ số, KHÔNG thêm %.
    #    Q và S là tỷ lệ %, thêm dấu %.
    for sheet_name in ("GV", "MN-01 GV"):
        ws = _sheet(
            workbook,
            sheet_name,
        )
        if ws is not None:
            _v2461_format_column_rows(
                ws,
                ("Q", "S"),
                8,
                int(ws.max_row),
            )

    # 6) MN-01 TE master cũ.
    ws = _sheet(
        workbook,
        "MN-01 TE",
    )
    if ws is not None:
        refs = []
        for col in ("E", "F", "G", "H", "I", "J", "K", "L"):
            refs.append(f"{col}17")

        refs.extend(
            (
                "E32",
                "E33",
                "E34",
            )
        )
        _v2461_format_refs(ws, refs)

    # 7) Tài chính: D13/D14 là bình quân tỷ lệ 5 năm.
    ws = _sheet(
        workbook,
        "Báo cáo tài chính",
    )
    if ws is not None:
        _v2461_format_refs(
            ws,
            ("D13", "D14"),
        )
# === BAI_13B_11_15_2_4_6_1_HIEN_DAU_PHAN_TRAM_END ===
"""


def read_text(
    path: Path,
) -> str:
    if not path.exists():
        raise RuntimeError(f"Không tìm thấy: {path}")

    return path.read_text(
        encoding="utf-8-sig",
        errors="strict",
    )


def write_text(
    path: Path,
    text: str,
) -> None:
    path.write_text(
        text,
        encoding="utf-8",
    )


def function_span(
    source: str,
    name: str,
) -> tuple[int, int]:
    tree = ast.parse(source)

    matches = [
        node
        for node in tree.body
        if isinstance(
            node,
            (
                ast.FunctionDef,
                ast.AsyncFunctionDef,
            ),
        )
        and node.name == name
    ]

    if len(matches) != 1:
        raise RuntimeError(
            f"Phải tìm thấy đúng 1 hàm {name}; hiện có {len(matches)}."
        )

    node = matches[0]
    lines = source.splitlines(keepends=True)
    offsets = [0]

    for line in lines:
        offsets.append(offsets[-1] + len(line))

    return (
        offsets[int(node.lineno) - 1],
        offsets[int(node.end_lineno)],
    )


def get_function(
    source: str,
    name: str,
) -> str:
    start, end = function_span(source, name)
    return source[start:end]


def replace_function(
    source: str,
    name: str,
    replacement: str,
) -> str:
    start, end = function_span(source, name)

    result = (
        source[:start]
        + replacement.rstrip()
        + "\n\n"
        + source[end:].lstrip("\n")
    )

    ast.parse(result)
    return result


def db_state() -> dict:
    if not DB.exists():
        return {"exists": False}

    conn = sqlite3.connect(str(DB))

    try:
        integrity = str(
            conn.execute(
                "PRAGMA integrity_check"
            ).fetchone()[0]
        )

        fk = len(
            conn.execute(
                "PRAGMA foreign_key_check"
            ).fetchall()
        )

        count = int(
            conn.execute(
                "SELECT COUNT(*) FROM survey_person_year_records"
            ).fetchone()[0]
        )

        columns = [
            str(row[1])
            for row in conn.execute(
                "PRAGMA table_info(survey_person_year_records)"
            ).fetchall()
        ]

        return {
            "exists": True,
            "integrity": integrity,
            "fk": fk,
            "count": count,
            "columns": columns,
        }

    finally:
        conn.close()


def patch_service(
    source: str,
) -> str:
    ast.parse(source)

    required = (
        "def apply_formula_contract(",
        "def _sheet(",
        "def safe_percent(",
        "REFERENCE_SHA256",
    )

    for token in required:
        if token not in source:
            raise RuntimeError(
                "mn_report_v246.py không đúng nền Bài 4.6. "
                f"Thiếu: {token}"
            )

    if MARKER not in source:
        start, _end = function_span(
            source,
            "apply_formula_contract",
        )

        source = (
            source[:start]
            + PERCENT_HELPERS.strip()
            + "\n\n\n"
            + source[start:]
        )

    fn = get_function(
        source,
        "apply_formula_contract",
    )

    if CALL_MARKER not in fn:
        addition = (
            "\n"
            "    "
            + CALL_MARKER
            + "\n"
            "    _apply_percent_display_v2461(\n"
            "        workbook\n"
            "    )\n"
        )

        fn = fn.rstrip() + addition + "\n"

        source = replace_function(
            source,
            "apply_formula_contract",
            fn,
        )

    ast.parse(source)
    return source


def verify(
    source: str,
) -> None:
    ast.parse(source)

    required = (
        MARKER,
        CALL_MARKER,
        "def _apply_percent_display_v2461(",
        "cell.number_format = r'0.00\\%'",
        '"Thống kê trẻ em từ 0 đến 5 tuổi"',
        '"Thống kê kết quả PCGD MN"',
        '"TK dat chuan"',
        '"GV"',
        '"MN-01 GV"',
        '"MN-01 TE"',
        '"Báo cáo tài chính"',
        '"H7"',
        '"K7"',
        '"O7"',
        '"F35"',
        '"F42"',
        '"Q"',
        '"S"',
    )

    for token in required:
        if token not in source:
            raise RuntimeError(
                "Verifier thiếu: "
                + token
            )


def main() -> None:
    print("=" * 132)
    print(
        "BÀI 13B-11.15.2.4.6.1 - "
        "HIỂN THỊ DẤU % SAU CÁC TỶ LỆ MẦM NON"
    )
    print("=" * 132)
    print()

    print("MỤC TIÊU:")
    print(" - 100,00  -> 100,00%")
    print(" - 50,00   -> 50,00%")
    print(" - Không đổi giá trị số/công thức đang tính.")
    print(" - Không biến 100 thành 10000%.")
    print()

    print("LƯU Ý NGHIỆP VỤ:")
    print(" - Tỷ lệ %: có dấu %.")
    print(" - GV/lớp và phòng/lớp là TỶ SỐ, không thêm %.")
    print()

    source = read_text(SERVICE)
    patched = patch_service(source)
    verify(patched)

    before_db = db_state()

    if before_db.get("exists"):
        if before_db.get("integrity") != "ok":
            raise RuntimeError(
                "Database integrity_check != ok."
            )

        if before_db.get("fk") != 0:
            raise RuntimeError(
                "Database đang có lỗi foreign key."
            )

    BACKUP.mkdir(
        parents=True,
        exist_ok=False,
    )

    shutil.copy2(
        SERVICE,
        BACKUP / SERVICE.name,
    )

    try:
        if patched != source:
            write_text(
                SERVICE,
                patched,
            )

        py_compile.compile(
            str(SERVICE),
            doraise=True,
        )

        verify(
            read_text(SERVICE)
        )

        after_db = db_state()

        if before_db != after_db:
            raise RuntimeError(
                "Database thay đổi ngoài dự kiến."
            )

        for cache in APP.rglob("__pycache__"):
            if cache.is_dir():
                shutil.rmtree(
                    cache,
                    ignore_errors=True,
                )

    except Exception:
        shutil.copy2(
            BACKUP / SERVICE.name,
            SERVICE,
        )

        for cache in APP.rglob("__pycache__"):
            if cache.is_dir():
                shutil.rmtree(
                    cache,
                    ignore_errors=True,
                )

        raise

    lines = [
        "=" * 132,
        "BÀI 13B-11.15.2.4.6.1 - KẾT QUẢ",
        "=" * 132,
        "",
        "ĐÃ SỬA:",
        " - Các ô tỷ lệ % hiển thị dạng 100,00%.",
        " - Giá trị nội bộ vẫn giữ 100.00, không đổi công thức.",
        " - Không dùng 0.00% vì sẽ biến 100 thành 10000%.",
        r" - Dùng định dạng literal: 0.00\%",
        "",
        "ÁP DỤNG:",
        " - MN-01-TE mẫu mới.",
        " - MN-02 đang xuất thực tế: H7, K7, O7.",
        " - TK đạt chuẩn.",
        " - MN-01 GV: Q/S là %, N = GV/lớp giữ tỷ số.",
        " - MN-01-TE master cũ.",
        " - Tài chính D13/D14.",
        "",
        "AN TOÀN:",
        " - Không sửa database.",
        " - Không sửa schema.",
        " - Không đổi menu/route.",
        f" - Backup: {BACKUP}",
        "",
    ]

    REPORT.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )

    print("KIỂM TRA:")
    print(" - AST: OK")
    print(" - py_compile: OK")
    print(" - Database invariant: OK")
    print(" - Không sửa số liệu: OK")
    print()
    print("Backup:", BACKUP)
    print("Báo cáo:", REPORT)
    print()
    print("=" * 132)
    print(
        "BÀI 13B-11.15.2.4.6.1 THÀNH CÔNG"
    )
    print("=" * 132)


if __name__ == "__main__":
    main()
