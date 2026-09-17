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
    / f"backup_bai_13b_11_15_2_4_6_3_{STAMP}"
)

REPORT = (
    EXPORTS
    / f"bao_cao_bai_13b_11_15_2_4_6_3_{STAMP}.txt"
)

OLD_FORMAT = r"0.00\%"
NEW_FORMAT = r"0\%"

MARKER = (
    "# === BAI_13B_11_15_2_4_6_3_"
    "PERCENT_NO_DECIMAL ==="
)


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
    text: str,
) -> None:
    path.write_text(
        text,
        encoding="utf-8",
    )


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

        schema = [
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
            "schema": schema,
        }

    finally:
        conn.close()


def patch_service(
    source: str,
) -> str:
    ast.parse(
        source
    )

    if (
        "def _v2461_percent_format("
        not in source
    ):
        raise RuntimeError(
            "Không tìm thấy helper "
            "_v2461_percent_format."
        )

    # Đã cài rồi thì idempotent.
    if (
        MARKER in source
        and "cell.number_format = r'0\\%'" in source
    ):
        return source

    old_line = (
        "    cell.number_format = r'0.00\\%'\n"
    )

    new_line = (
        "    "
        + MARKER
        + "\n"
        + "    cell.number_format = r'0\\%'\n"
    )

    count = source.count(
        old_line
    )

    if count != 1:
        raise RuntimeError(
            "Cần đúng 1 dòng định dạng "
            "0.00\\%; hiện tìm thấy "
            f"{count}."
        )

    source = source.replace(
        old_line,
        new_line,
        1,
    )

    ast.parse(
        source
    )

    return source


def verify(
    source: str,
) -> None:
    ast.parse(
        source
    )

    required = (
        MARKER,
        "def _v2461_percent_format(",
        "cell.number_format = r'0\\%'",
        "def _apply_percent_display_v2461(",
    )

    for token in required:
        if token not in source:
            raise RuntimeError(
                "Verifier thiếu: "
                + token
            )

    if (
        "cell.number_format = r'0.00\\%'"
        in source
    ):
        raise RuntimeError(
            "Vẫn còn định dạng 0.00\\% "
            "trong helper tỷ lệ."
        )


def main() -> None:
    print("=" * 132)
    print(
        "BÀI 13B-11.15.2.4.6.3 - "
        "HIỂN THỊ TỶ LỆ MẦM NON DẠNG 100%"
    )
    print("=" * 132)
    print()

    print("MỤC TIÊU:")
    print(" - 100,00% -> 100%")
    print(" - 50,00%  -> 50%")
    print(" - 0,00%   -> 0%")
    print()

    print("NGUYÊN TẮC:")
    print(
        " - Chỉ đổi NUMBER FORMAT của Excel."
    )
    print(
        " - Giá trị số bên trong không đổi."
    )
    print(
        " - Công thức nghiệp vụ không đổi."
    )
    print(
        " - Không sửa database/menu/route."
    )
    print()

    source = read_text(
        SERVICE
    )

    patched = patch_service(
        source
    )

    verify(
        patched
    )

    before = db_state()

    if before.get(
        "exists"
    ):
        if (
            before.get(
                "integrity"
            )
            != "ok"
        ):
            raise RuntimeError(
                "Database integrity_check != ok."
            )

        if (
            before.get(
                "fk_count"
            )
            != 0
        ):
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

        verify(
            installed
        )

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

    lines = [
        "=" * 132,
        "BÀI 13B-11.15.2.4.6.3 - KẾT QUẢ",
        "=" * 132,
        "",
        "ĐÃ ĐỔI:",
        r" - number_format từ 0.00\% sang 0\%.",
        " - 100,00% -> 100%.",
        " - 50,00% -> 50%.",
        " - 0,00% -> 0%.",
        "",
        "KHÔNG ĐỔI:",
        " - Giá trị số.",
        " - Công thức nghiệp vụ.",
        " - Database/schema.",
        " - Menu/route.",
        "",
        f"Backup: {BACKUP}",
        "",
    ]

    REPORT.write_text(
        "\n".join(
            lines
        ),
        encoding="utf-8",
    )

    print("KIỂM TRA:")
    print(" - AST: OK")
    print(" - py_compile: OK")
    print(" - Database invariant: OK")
    print(" - Chỉ đổi cách hiển thị: OK")
    print()
    print("Backup:", BACKUP)
    print("Báo cáo:", REPORT)
    print()
    print("=" * 132)
    print(
        "BÀI 13B-11.15.2.4.6.3 THÀNH CÔNG"
    )
    print("=" * 132)


if __name__ == "__main__":
    main()
