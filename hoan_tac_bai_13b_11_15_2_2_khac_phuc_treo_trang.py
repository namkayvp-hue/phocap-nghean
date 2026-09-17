from __future__ import annotations

import os
import re
import shutil
import sqlite3
import traceback
from datetime import datetime
from pathlib import Path


PROJECT = Path(
    os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")
).resolve()

APP = PROJECT / "app"
TEMPLATE = APP / "templates" / "surveys" / "year_records.html"
DB = PROJECT / "data" / "phocap.db"
EXPORTS = PROJECT / "exports"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = (
    EXPORTS
    / f"backup_hoan_tac_bai_13b_11_15_2_2_{STAMP}"
)

MARKER = "BAI_13B_11_15_2_2_EXCLUSIVE_LEVEL_UI"


def read_text(path: Path) -> str:
    if not path.exists():
        raise RuntimeError(
            f"Không tìm thấy: {path}"
        )

    return path.read_text(
        encoding="utf-8-sig",
        errors="strict",
    )


def db_check() -> tuple[int, str, int]:
    conn = sqlite3.connect(str(DB))

    try:
        count = int(
            conn.execute(
                "SELECT COUNT(*) "
                "FROM survey_person_year_records"
            ).fetchone()[0]
        )

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

        return count, integrity, fk

    finally:
        conn.close()


def remove_patch(text: str) -> tuple[str, int]:
    removed = 0

    style_pattern = re.compile(
        r"(?is)<style\b[^>]*>.*?"
        r"BAI_13B_11_15_2_2_EXCLUSIVE_LEVEL_UI"
        r".*?</style>"
    )

    script_pattern = re.compile(
        r"(?is)<script\b[^>]*>.*?"
        r"BAI_13B_11_15_2_2_EXCLUSIVE_LEVEL_UI"
        r".*?</script>"
    )

    text, n_style = style_pattern.subn(
        "",
        text,
        count=1,
    )

    removed += n_style

    text, n_script = script_pattern.subn(
        "",
        text,
        count=1,
    )

    removed += n_script

    text = re.sub(
        r"\n{4,}",
        "\n\n\n",
        text,
    )

    return text, removed


def verify_jinja(text: str) -> None:
    from jinja2 import Environment

    Environment().parse(text)

    if MARKER in text:
        raise RuntimeError(
            "Sau hoàn tác vẫn còn marker Bài 15.2.2."
        )

    required = (
        "b1512_primary_thcs_fields",
        "study_location_scope",
        "is_repeating_grade",
        "current_education_program",
        "BO_HOC",
        "CHUA_DI_HOC",
    )

    missing = [
        token
        for token in required
        if token not in text
    ]

    if missing:
        raise RuntimeError(
            "Template sau hoàn tác thiếu nền Bài 15.2.1: "
            + ", ".join(missing)
        )


def clear_cache() -> None:
    for cache in APP.rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(
                cache,
                ignore_errors=True,
            )


def main() -> int:
    print("=" * 126)
    print(
        "HOÀN TÁC BÀI 13B-11.15.2.2 - "
        "KHẮC PHỤC TREO TRANG THÔNG TIN NĂM HỌC"
    )
    print("=" * 126)
    print()
    print("HOÀN TÁC:")
    print(
        " - Chỉ gỡ CSS + JavaScript của Bài 15.2.2."
    )
    print(
        " - GIỮ NGUYÊN Bài 15.2.1."
    )
    print(
        " - GIỮ NGUYÊN schema Bài 15.1."
    )
    print(
        " - KHÔNG sửa dữ liệu database."
    )
    print()

    if not TEMPLATE.exists():
        raise RuntimeError(
            f"Không tìm thấy template: {TEMPLATE}"
        )

    if not DB.exists():
        raise RuntimeError(
            f"Không tìm thấy database: {DB}"
        )

    count_before, integrity_before, fk_before = db_check()

    print(
        "survey_person_year_records:",
        count_before,
        "bản ghi",
    )
    print(
        "integrity_check trước hoàn tác:",
        integrity_before,
    )
    print(
        "foreign_key_check trước hoàn tác:",
        fk_before,
        "lỗi",
    )

    if (
        integrity_before.lower() != "ok"
        or fk_before != 0
    ):
        raise RuntimeError(
            "Database không đạt kiểm tra an toàn."
        )

    original = read_text(TEMPLATE)

    if MARKER not in original:
        print()
        print(
            "Không thấy Bài 15.2.2 trong template. "
            "Không có gì để gỡ."
        )
        print(
            "Database không thay đổi."
        )
        return 0

    BACKUP.mkdir(
        parents=True,
        exist_ok=False,
    )

    backup_template = (
        BACKUP
        / "app"
        / "templates"
        / "surveys"
        / "year_records.html"
    )

    backup_template.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    shutil.copy2(
        TEMPLATE,
        backup_template,
    )

    print(
        "Backup:",
        BACKUP,
    )

    try:
        patched, removed = remove_patch(
            original
        )

        if removed < 2:
            raise RuntimeError(
                "Không nhận diện đủ cả CSS và JavaScript "
                f"của Bài 15.2.2. Số block tìm thấy: {removed}."
            )

        verify_jinja(
            patched
        )

        TEMPLATE.write_text(
            patched,
            encoding="utf-8",
        )

        count_after, integrity_after, fk_after = db_check()

        if count_after != count_before:
            raise RuntimeError(
                "Số bản ghi database bị thay đổi bất thường."
            )

        if integrity_after.lower() != "ok":
            raise RuntimeError(
                "integrity_check sau hoàn tác không OK."
            )

        if fk_after != 0:
            raise RuntimeError(
                "foreign_key_check sau hoàn tác có "
                f"{fk_after} lỗi."
            )

        clear_cache()

        print()
        print("KIỂM TRA SAU HOÀN TÁC:")
        print(
            " - CSS Bài 15.2.2: ĐÃ GỠ"
        )
        print(
            " - JavaScript Bài 15.2.2: ĐÃ GỠ"
        )
        print(
            " - Bài 15.2.1: GIỮ NGUYÊN"
        )
        print(
            " - Dữ liệu/schema Bài 15.1: GIỮ NGUYÊN"
        )
        print(
            " - Jinja parse: OK"
        )
        print(
            " - integrity_check: OK"
        )
        print(
            " - foreign_key_check: 0 lỗi"
        )
        print()
        print("=" * 126)
        print(
            "HOÀN TÁC BÀI 13B-11.15.2.2 THÀNH CÔNG"
        )
        print("=" * 126)

        return 0

    except Exception:
        traceback.print_exc()

        print()
        print(
            "CÓ LỖI - ĐANG KHÔI PHỤC TEMPLATE "
            "TRƯỚC KHI HOÀN TÁC..."
        )

        try:
            shutil.copy2(
                backup_template,
                TEMPLATE,
            )

            print(
                " - Đã khôi phục template."
            )

        except Exception as exc:
            print(
                " - Lỗi khôi phục template:",
                exc,
            )

        clear_cache()

        print(
            "Backup:",
            BACKUP,
        )

        return 1


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
