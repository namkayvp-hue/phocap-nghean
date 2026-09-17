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

BACKUP = (
    EXPORTS
    / f"backup_bai_13b_11_15_2_4_6_4_{STAMP}"
)

REPORT = (
    EXPORTS
    / f"bao_cao_bai_13b_11_15_2_4_6_4_{STAMP}.txt"
)

MARKER_463 = (
    "# === BAI_13B_11_15_2_4_6_3_"
    "PERCENT_NO_DECIMAL ==="
)

MARKER_464 = (
    "# === BAI_13B_11_15_2_4_6_4_"
    "AUTO_FIND_PERCENT_COLUMN ==="
)

CALL_464 = (
    "# === BAI_13B_11_15_2_4_6_4_"
    "CALL_AUTO_FIND_PERCENT_COLUMN ==="
)

AUTO_HELPERS = '\n# === BAI_13B_11_15_2_4_6_4_AUTO_FIND_PERCENT_COLUMN ===\ndef _v2464_norm_text(\n    value: Any,\n) -> str:\n    text = str(\n        value or ""\n    ).strip()\n\n    text = unicodedata.normalize(\n        "NFD",\n        text,\n    )\n\n    text = "".join(\n        ch\n        for ch in text\n        if unicodedata.category(ch) != "Mn"\n    )\n\n    text = (\n        text\n        .replace("Đ", "D")\n        .replace("đ", "d")\n        .upper()\n    )\n\n    return " ".join(\n        text.split()\n    )\n\n\ndef _v2464_format_percent_table_by_header(\n    ws: Any,\n) -> None:\n    """\n    Tự tìm bảng có tiêu đề:\n        Tiêu chí | Số lượng | Tỉ lệ\n\n    Không phụ thuộc cột cố định.\n    Chỉ định dạng cột Tỉ lệ.\n    """\n    max_scan_row = min(\n        int(ws.max_row),\n        120,\n    )\n\n    max_scan_col = min(\n        int(ws.max_column),\n        40,\n    )\n\n    for row in range(\n        1,\n        max_scan_row + 1,\n    ):\n        row_values = {\n            col: _v2464_norm_text(\n                ws.cell(\n                    row,\n                    col,\n                ).value\n            )\n            for col in range(\n                1,\n                max_scan_col + 1,\n            )\n        }\n\n        has_criteria = any(\n            value == "TIEU CHI"\n            for value in row_values.values()\n        )\n\n        has_quantity = any(\n            value in (\n                "SO LUONG",\n                "SL",\n            )\n            for value in row_values.values()\n        )\n\n        if not (\n            has_criteria\n            and has_quantity\n        ):\n            continue\n\n        for col, value in row_values.items():\n            if value not in (\n                "TI LE",\n                "TY LE",\n                "TI LE %",\n                "TY LE %",\n            ):\n                continue\n\n            empty_streak = 0\n\n            for data_row in range(\n                row + 1,\n                min(\n                    int(ws.max_row),\n                    row + 80,\n                )\n                + 1,\n            ):\n                cell = ws.cell(\n                    data_row,\n                    col,\n                )\n\n                if cell.value in (\n                    None,\n                    "",\n                ):\n                    empty_streak += 1\n                else:\n                    empty_streak = 0\n\n                # Helper bài 4.6.2/4.6.3:\n                # - đổi chuỗi số thành số thật;\n                # - hiển thị dạng 100%, 0%, 50%.\n                _v2461_percent_format(\n                    cell\n                )\n\n                if empty_streak >= 6:\n                    break\n# === BAI_13B_11_15_2_4_6_4_AUTO_FIND_PERCENT_COLUMN_END ===\n'


def read_text(
    path: Path,
) -> str:
    if not path.exists():
        raise RuntimeError(
            f"Không tìm thấy: {path}"
        )

    return path.read_text(
        encoding="utf-8-sig",
        errors="strict",
    )


def write_text(
    path: Path,
    value: str,
) -> None:
    path.write_text(
        value,
        encoding="utf-8",
    )


def function_span(
    source: str,
    name: str,
) -> tuple[int, int]:
    tree = ast.parse(
        source
    )

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
            f"Cần đúng 1 hàm {name}; "
            f"tìm thấy {len(matches)}."
        )

    node = matches[0]

    lines = source.splitlines(
        keepends=True
    )

    offsets = [0]

    for line in lines:
        offsets.append(
            offsets[-1]
            + len(line)
        )

    return (
        offsets[
            int(node.lineno) - 1
        ],
        offsets[
            int(node.end_lineno)
        ],
    )


def get_function(
    source: str,
    name: str,
) -> str:
    start, end = function_span(
        source,
        name,
    )

    return source[start:end]


def replace_function(
    source: str,
    name: str,
    replacement: str,
) -> str:
    start, end = function_span(
        source,
        name,
    )

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
        return {
            "exists": False,
        }

    conn = sqlite3.connect(
        str(DB)
    )

    try:
        integrity = str(
            conn.execute(
                "PRAGMA integrity_check"
            ).fetchone()[0]
        )

        fk_count = len(
            conn.execute(
                "PRAGMA foreign_key_check"
            ).fetchall()
        )

        count = int(
            conn.execute(
                "SELECT COUNT(*) "
                "FROM survey_person_year_records"
            ).fetchone()[0]
        )

        columns = [
            str(row[1])
            for row in conn.execute(
                "PRAGMA table_info("
                "survey_person_year_records"
                ")"
            ).fetchall()
        ]

        return {
            "exists": True,
            "integrity": integrity,
            "fk_count": fk_count,
            "count": count,
            "columns": columns,
        }

    finally:
        conn.close()


def patch_service(
    source: str,
) -> str:
    ast.parse(source)

    if MARKER_463 not in source:
        raise RuntimeError(
            "Chưa thấy nền Bài 13B-11.15.2.4.6.3 "
            "trong mn_report_v246.py."
        )

    if (
        "def _v2461_percent_format("
        not in source
    ):
        raise RuntimeError(
            "Thiếu helper _v2461_percent_format."
        )

    if MARKER_464 not in source:
        start, _end = function_span(
            source,
            "_apply_percent_display_v2461",
        )

        source = (
            source[:start]
            + AUTO_HELPERS.strip()
            + "\n\n\n"
            + source[start:]
        )

    fn = get_function(
        source,
        "_apply_percent_display_v2461",
    )

    if CALL_464 not in fn:
        call = (
            "\n"
            "    "
            + CALL_464
            + "\n"
            "    ws = _sheet(\n"
            "        workbook,\n"
            '        "Thống kê trẻ em từ 0 đến 5 tuổi",\n'
            "    )\n"
            "    if ws is not None:\n"
            "        _v2464_format_percent_table_by_header(\n"
            "            ws\n"
            "        )\n"
        )

        fn = fn.rstrip() + call + "\n"

        source = replace_function(
            source,
            "_apply_percent_display_v2461",
            fn,
        )

    ast.parse(source)
    return source


def verify(
    source: str,
) -> None:
    ast.parse(source)

    required = (
        MARKER_463,
        MARKER_464,
        CALL_464,
        "def _v2464_norm_text(",
        "def _v2464_format_percent_table_by_header(",
        '"TIEU CHI"',
        '"SO LUONG"',
        '"TI LE"',
        "_v2461_percent_format(",
        "cell.number_format = r'0\\%'",
        '"Thống kê trẻ em từ 0 đến 5 tuổi"',
    )

    for token in required:
        if token not in source:
            raise RuntimeError(
                "Verifier thiếu: "
                + token
            )


def main() -> None:
    print("=" * 138)
    print(
        "BÀI 13B-11.15.2.4.6.4 - "
        "TỰ TÌM CỘT TỈ LỆ TRONG MN-01-TE"
    )
    print("=" * 138)
    print()

    print("PHÁT HIỆN:")
    print(" - MN-02 đã hiển thị 100% đúng.")
    print(
        " - MN-01-TE vẫn 100 / 0 vì cột Tỉ lệ "
        "không ở tọa độ cố định."
    )
    print()

    print("SỬA:")
    print(
        " - Tự tìm hàng Tiêu chí | Số lượng | Tỉ lệ."
    )
    print(
        " - Tự xác định đúng cột Tỉ lệ."
    )
    print(
        " - Định dạng giá trị bên dưới thành "
        "100%, 0%, 50%..."
    )
    print(
        " - Không đụng cột Số lượng."
    )
    print()

    source = read_text(SERVICE)
    patched = patch_service(source)
    verify(patched)

    before = db_state()

    if before.get("exists"):
        if before.get("integrity") != "ok":
            raise RuntimeError(
                "Database integrity_check != ok."
            )

        if before.get("fk_count") != 0:
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

        installed = read_text(
            SERVICE
        )

        verify(installed)

        after = db_state()

        if before != after:
            raise RuntimeError(
                "Database/schema/count thay đổi "
                "ngoài dự kiến."
            )

        for cache in APP.rglob(
            "__pycache__"
        ):
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

        for cache in APP.rglob(
            "__pycache__"
        ):
            if cache.is_dir():
                shutil.rmtree(
                    cache,
                    ignore_errors=True,
                )

        raise

    REPORT.write_text(
        "\n".join(
            (
                "=" * 138,
                "BÀI 13B-11.15.2.4.6.4 - KẾT QUẢ",
                "=" * 138,
                "",
                "ĐÃ SỬA:",
                " - Không dùng tọa độ cố định cho bảng tiêu chí MN-01-TE.",
                " - Tự tìm đúng cột Tỉ lệ theo tiêu đề.",
                " - 100 -> 100%.",
                " - 0 -> 0%.",
                " - 50 -> 50%.",
                "",
                "AN TOÀN:",
                " - Không sửa công thức nghiệp vụ.",
                " - Không sửa số lượng.",
                " - Không sửa database/schema.",
                " - Không đổi menu/route.",
                f" - Backup: {BACKUP}",
                "",
            )
        ),
        encoding="utf-8",
    )

    print("KIỂM TRA:")
    print(" - AST: OK")
    print(" - py_compile: OK")
    print(" - Database invariant: OK")
    print(" - Tự dò cột Tỉ lệ: ĐÃ CÀI")
    print()
    print("Backup:", BACKUP)
    print("Báo cáo:", REPORT)
    print()
    print("=" * 138)
    print(
        "BÀI 13B-11.15.2.4.6.4 THÀNH CÔNG"
    )
    print("=" * 138)


if __name__ == "__main__":
    main()
