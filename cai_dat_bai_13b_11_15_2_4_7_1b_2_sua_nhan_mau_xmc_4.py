from __future__ import annotations
import ast
import os
import py_compile
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

PROJECT = Path(os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")).resolve()
APP = PROJECT / "app"
EXPORTS = PROJECT / "exports"
DB = PROJECT / "data" / "phocap.db"
BUILDERS = APP / "pcgd_xmc_report_builders_v1.py"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = EXPORTS / f"backup_bai_13b_11_15_2_4_7_1b_2_{STAMP}"
REPORT = EXPORTS / f"bao_cao_bai_13b_11_15_2_4_7_1b_2_{STAMP}.txt"

START = "# === BAI_13B_11_15_2_4_7_1B_2_FIX_XMC4_LABEL_START ==="
END = "# === BAI_13B_11_15_2_4_7_1B_2_FIX_XMC4_LABEL_END ==="

PATCH = r"""
    # === BAI_13B_11_15_2_4_7_1B_2_FIX_XMC4_LABEL_START ===
    # Chỉ sửa nhãn của biểu XMC-4 khi xuất Excel.
    for _b1471b2_row in ws.iter_rows():
        for _b1471b2_cell in _b1471b2_row:
            _b1471b2_value = str(
                getattr(_b1471b2_cell, "value", "") or ""
            ).strip()
            if _b1471b2_value == "Mẫu XMC-5":
                _b1471b2_cell.value = "Mẫu XMC-4"
    # === BAI_13B_11_15_2_4_7_1B_2_FIX_XMC4_LABEL_END ===
""".strip("\n")


def read_text(path: Path) -> str:
    if not path.exists():
        raise RuntimeError(f"Không tìm thấy: {path}")
    return path.read_text(encoding="utf-8-sig")


def db_state() -> dict:
    if not DB.exists():
        return {"exists": False}
    conn = sqlite3.connect(str(DB))
    try:
        return {
            "exists": True,
            "integrity": conn.execute("PRAGMA integrity_check").fetchone()[0],
            "fk": len(conn.execute("PRAGMA foreign_key_check").fetchall()),
        }
    finally:
        conn.close()


def get_function(source: str, name: str) -> ast.FunctionDef:
    tree = ast.parse(source)
    matches = [
        n for n in tree.body
        if isinstance(n, ast.FunctionDef) and n.name == name
    ]
    if len(matches) != 1:
        raise RuntimeError(
            f"Cần đúng 1 hàm {name}; tìm thấy {len(matches)}."
        )
    return matches[0]


def patch_source(source: str) -> str:
    ast.parse(source)

    if START in source:
        return source

    node = get_function(source, "_build_xmc4")
    if not node.body:
        raise RuntimeError("_build_xmc4 không có thân hàm.")

    # Chèn sau docstring nếu có; nếu không, chèn ngay trước câu lệnh đầu tiên.
    first = node.body[0]
    if (
        isinstance(first, ast.Expr)
        and isinstance(first.value, ast.Constant)
        and isinstance(first.value.value, str)
    ):
        insert_line = int(first.end_lineno)
    else:
        insert_line = int(first.lineno) - 1

    lines = source.splitlines(keepends=True)

    prefix = ""
    if insert_line > 0 and not lines[insert_line - 1].endswith("\n"):
        prefix = "\n"

    lines.insert(insert_line, prefix + PATCH + "\n\n")
    result = "".join(lines)
    ast.parse(result)
    return result


def verify(source: str) -> None:
    ast.parse(source)
    get_function(source, "_build_xmc4")
    for token in (
        START,
        END,
        '"Mẫu XMC-5"',
        '"Mẫu XMC-4"',
        "ws.iter_rows()",
    ):
        if token not in source:
            raise RuntimeError("Verifier thiếu: " + token)


def main() -> None:
    print("=" * 128)
    print("BÀI 13B-11.15.2.4.7.1B.2 - SỬA NHÃN MẪU XMC-5 THÀNH MẪU XMC-4")
    print("=" * 128)
    print()
    print("SẼ LÀM:")
    print(" - Chỉ sửa nhãn trên biểu XMC-4 khi xuất Excel.")
    print(" - 'Mẫu XMC-5' -> 'Mẫu XMC-4'.")
    print()
    print("KHÔNG LÀM:")
    print(" - Không sửa database.")
    print(" - Không sửa số liệu/công thức/tỷ lệ.")
    print(" - Không sửa menu/route/template web.")
    print(" - Không đổi bố cục Excel.")
    print()

    old = read_text(BUILDERS)
    new = patch_source(old)
    verify(new)

    before = db_state()
    if before.get("exists") and (
        before.get("integrity") != "ok" or before.get("fk") != 0
    ):
        raise RuntimeError("Database không đạt kiểm tra an toàn trước cài.")

    EXPORTS.mkdir(parents=True, exist_ok=True)
    BACKUP.mkdir(parents=True, exist_ok=False)
    shutil.copy2(BUILDERS, BACKUP / BUILDERS.name)

    try:
        if new != old:
            BUILDERS.write_text(new, encoding="utf-8")

        py_compile.compile(str(BUILDERS), doraise=True)
        verify(read_text(BUILDERS))

        after = db_state()
        if after != before:
            raise RuntimeError("Database thay đổi ngoài dự kiến.")

        for cache in APP.rglob("__pycache__"):
            if cache.is_dir():
                shutil.rmtree(cache, ignore_errors=True)

    except Exception:
        shutil.copy2(BACKUP / BUILDERS.name, BUILDERS)
        raise

    REPORT.write_text(
        "\n".join(
            [
                "BÀI 13B-11.15.2.4.7.1B.2 - KẾT QUẢ",
                "",
                "Đã sửa nhãn khi xuất XMC-4:",
                "Mẫu XMC-5 -> Mẫu XMC-4",
                "",
                "Database: KHÔNG THAY ĐỔI.",
                "Công thức/tỷ lệ/số liệu: KHÔNG THAY ĐỔI.",
                f"Backup: {BACKUP}",
            ]
        ),
        encoding="utf-8",
    )

    print("KIỂM TRA:")
    print(" - AST: OK")
    print(" - py_compile: OK")
    print(" - _build_xmc4: OK")
    print(" - Database invariant: OK")
    print()
    print("Backup:", BACKUP)
    print("Báo cáo:", REPORT)
    print()
    print("=" * 128)
    print("BÀI 13B-11.15.2.4.7.1B.2 THÀNH CÔNG")
    print("=" * 128)


if __name__ == "__main__":
    main()
