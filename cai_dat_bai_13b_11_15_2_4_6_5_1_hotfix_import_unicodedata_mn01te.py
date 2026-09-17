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
    / f"backup_bai_13b_11_15_2_4_6_5_1_{STAMP}"
)

REPORT = (
    EXPORTS
    / f"bao_cao_bai_13b_11_15_2_4_6_5_1_{STAMP}.txt"
)

MARKER = (
    "# === BAI_13B_11_15_2_4_6_5_1_"
    "IMPORT_UNICODEDATA ==="
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
    value: str,
) -> None:
    path.write_text(
        value,
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

    required = (
        "def _v2464_norm_text(",
        "unicodedata.normalize(",
        "def apply_formula_contract(",
    )

    for token in required:
        if token not in source:
            raise RuntimeError(
                "Service không đúng nền 4.6.4/4.6.5. "
                "Thiếu: "
                + token
            )

    # Đã có import thì chỉ thêm marker nếu cần.
    if "import unicodedata\n" in source:
        if MARKER in source:
            return source

        # Gắn marker ngay sau import hiện có.
        source = source.replace(
            "import unicodedata\n",
            "import unicodedata\n"
            + MARKER
            + "\n",
            1,
        )

        ast.parse(
            source
        )

        return source

    # Chèn import an toàn sau future import.
    anchor = (
        "from __future__ import annotations\n"
    )

    if anchor not in source:
        raise RuntimeError(
            "Không tìm thấy future import để chèn "
            "unicodedata an toàn."
        )

    source = source.replace(
        anchor,
        anchor
        + "\n"
        + "import unicodedata\n"
        + MARKER
        + "\n",
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
        "import unicodedata",
        MARKER,
        "unicodedata.normalize(",
        "def _v2464_norm_text(",
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
        "BÀI 13B-11.15.2.4.6.5.1 - "
        "HOTFIX IMPORT UNICODEDATA CHO MN-01-TE"
    )
    print("=" * 132)
    print()

    print("NGUYÊN NHÂN:")
    print(
        " - Helper Bài 4.6.4 dùng unicodedata.normalize()."
    )
    print(
        " - Service chưa import unicodedata."
    )
    print(
        " - Sau Bài 4.6.5 helper mới thực sự được chạy, "
        "nên lỗi 500 mới lộ ra."
    )
    print()

    print("SẼ LÀM:")
    print(
        " - Chỉ thêm import unicodedata."
    )
    print(
        " - Không sửa công thức, template, route, menu."
    )
    print(
        " - Không sửa database."
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
        if before.get(
            "integrity"
        ) != "ok":
            raise RuntimeError(
                "Database integrity_check != ok."
            )

        if before.get(
            "fk_count"
        ) != 0:
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

    REPORT.write_text(
        "\n".join(
            (
                "=" * 132,
                "BÀI 13B-11.15.2.4.6.5.1 - KẾT QUẢ",
                "=" * 132,
                "",
                "ĐÃ SỬA:",
                " - Bổ sung import unicodedata cho mn_report_v246.py.",
                "",
                "KHÔNG ĐỔI:",
                " - Công thức nghiệp vụ.",
                " - Template Excel.",
                " - Database/schema.",
                " - Menu/route.",
                f" - Backup: {BACKUP}",
                "",
            )
        ),
        encoding="utf-8",
    )

    print("KIỂM TRA:")
    print(" - AST: OK")
    print(" - py_compile: OK")
    print(" - import unicodedata: OK")
    print(" - Database invariant: OK")
    print()
    print("Backup:", BACKUP)
    print("Báo cáo:", REPORT)
    print()
    print("=" * 132)
    print(
        "BÀI 13B-11.15.2.4.6.5.1 THÀNH CÔNG"
    )
    print("=" * 132)


if __name__ == "__main__":
    main()
