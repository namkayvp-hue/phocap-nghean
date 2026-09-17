from __future__ import annotations

import os
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

SAFETY_BACKUP = (
    EXPORTS
    / f"backup_hoan_tac_bai_13b_11_15_2_2_v2_{STAMP}"
)

CURRENT_TEMPLATE_BACKUP = (
    SAFETY_BACKUP
    / "app"
    / "templates"
    / "surveys"
    / "year_records.html"
)

BAD_MARKER = "BAI_13B_11_15_2_2_EXCLUSIVE_LEVEL_UI"

REQUIRED_1521_TOKENS = (
    "b1512_primary_thcs_fields",
    "study_location_scope",
    "is_repeating_grade",
    "current_education_program",
    "BO_HOC",
    "CHUA_DI_HOC",
)


def read_text(path: Path) -> str:
    if not path.exists():
        raise RuntimeError(
            f"Không tìm thấy: {path}"
        )

    return path.read_text(
        encoding="utf-8-sig",
        errors="strict",
    )


def db_check() -> tuple[int, str, int, set[str]]:
    conn = sqlite3.connect(str(DB))

    try:
        count = int(
            conn.execute(
                """
                SELECT COUNT(*)
                FROM survey_person_year_records
                """
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

        columns = {
            str(row[1])
            for row in conn.execute(
                """
                PRAGMA table_info(
                    "survey_person_year_records"
                )
                """
            ).fetchall()
        }

        return (
            count,
            integrity,
            fk,
            columns,
        )

    finally:
        conn.close()


def validate_candidate(
    candidate: Path,
) -> tuple[bool, str]:
    try:
        text = read_text(candidate)
    except Exception as exc:
        return (
            False,
            f"không đọc được: {exc}",
        )

    if BAD_MARKER in text:
        return (
            False,
            "vẫn có marker Bài 15.2.2",
        )

    missing = [
        token
        for token in REQUIRED_1521_TOKENS
        if token not in text
    ]

    if missing:
        return (
            False,
            "thiếu nền Bài 15.2.1: "
            + ", ".join(missing),
        )

    try:
        from jinja2 import Environment

        Environment().parse(text)

    except Exception as exc:
        return (
            False,
            f"Jinja không hợp lệ: {exc}",
        )

    return (
        True,
        "OK",
    )


def find_pre_1522_template() -> tuple[Path, Path]:
    folders = sorted(
        (
            path
            for path in EXPORTS.glob(
                "backup_bai_13b_11_15_2_2_*"
            )
            if path.is_dir()
        ),
        key=lambda path: path.name,
        reverse=True,
    )

    if not folders:
        raise RuntimeError(
            "Không tìm thấy backup_bai_13b_11_15_2_2_* "
            "trong C:\\PhoCap\\exports."
        )

    checked = []

    for folder in folders:
        candidate = (
            folder
            / "app"
            / "templates"
            / "surveys"
            / "year_records.html"
        )

        if not candidate.exists():
            checked.append(
                f" - {folder.name}: không có year_records.html"
            )
            continue

        ok, reason = validate_candidate(candidate)

        checked.append(
            f" - {folder.name}: {reason}"
        )

        if ok:
            return (
                folder,
                candidate,
            )

    raise RuntimeError(
        "Có backup Bài 15.2.2 nhưng chưa tìm được "
        "bản template đúng trạng thái 15.2.1.\n"
        + "\n".join(checked)
    )


def clear_cache() -> None:
    for cache in APP.rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(
                cache,
                ignore_errors=True,
            )


def main() -> int:
    print("=" * 132)
    print(
        "HOÀN TÁC BÀI 13B-11.15.2.2 V2 - "
        "KHÔI PHỤC TEMPLATE TỪ BACKUP GỐC TRƯỚC 15.2.2"
    )
    print("=" * 132)
    print()
    print("CÁCH LÀM V2:")
    print(
        " - KHÔNG dùng regex cắt CSS/JavaScript."
    )
    print(
        " - Tìm backup được tạo ngay trước khi cài Bài 15.2.2."
    )
    print(
        " - Chỉ nhận backup có đầy đủ nền Bài 15.2.1."
    )
    print(
        " - Backup đó phải KHÔNG có marker Bài 15.2.2."
    )
    print(
        " - Chỉ khôi phục year_records.html."
    )
    print(
        " - KHÔNG đụng router, model hoặc database."
    )
    print()

    if not TEMPLATE.exists():
        raise RuntimeError(
            f"Không tìm thấy template hiện tại: {TEMPLATE}"
        )

    if not DB.exists():
        raise RuntimeError(
            f"Không tìm thấy database: {DB}"
        )

    (
        count_before,
        integrity_before,
        fk_before,
        columns_before,
    ) = db_check()

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

    required_schema = {
        "study_location_scope",
        "is_repeating_grade",
        "current_education_program",
    }

    missing_schema = sorted(
        required_schema
        - columns_before
    )

    if missing_schema:
        raise RuntimeError(
            "Database thiếu schema Bài 15.1: "
            + ", ".join(missing_schema)
        )

    if (
        integrity_before.lower() != "ok"
        or fk_before != 0
    ):
        raise RuntimeError(
            "Database không đạt kiểm tra an toàn."
        )

    current_text = read_text(TEMPLATE)

    if BAD_MARKER not in current_text:
        print()
        print(
            "Template hiện tại không còn marker Bài 15.2.2."
        )

        missing_current = [
            token
            for token in REQUIRED_1521_TOKENS
            if token not in current_text
        ]

        if not missing_current:
            print(
                "Nền Bài 15.2.1 vẫn đầy đủ. "
                "Không cần hoàn tác thêm."
            )
            return 0

        print(
            "Template không có 15.2.2 nhưng thiếu nền 15.2.1; "
            "sẽ tiếp tục tìm backup gốc."
        )

    source_backup_folder, source_template = (
        find_pre_1522_template()
    )

    print()
    print(
        "Backup gốc được chọn:",
        source_backup_folder,
    )
    print(
        "Template nguồn:",
        source_template,
    )

    SAFETY_BACKUP.mkdir(
        parents=True,
        exist_ok=False,
    )

    CURRENT_TEMPLATE_BACKUP.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    shutil.copy2(
        TEMPLATE,
        CURRENT_TEMPLATE_BACKUP,
    )

    print(
        "Backup an toàn template hiện tại:",
        SAFETY_BACKUP,
    )

    try:
        source_text = read_text(
            source_template
        )

        ok, reason = validate_candidate(
            source_template
        )

        if not ok:
            raise RuntimeError(
                "Template backup gốc không đạt kiểm tra: "
                + reason
            )

        TEMPLATE.write_text(
            source_text,
            encoding="utf-8",
        )

        restored = read_text(
            TEMPLATE
        )

        if BAD_MARKER in restored:
            raise RuntimeError(
                "Sau khôi phục vẫn còn marker 15.2.2."
            )

        missing_after = [
            token
            for token in REQUIRED_1521_TOKENS
            if token not in restored
        ]

        if missing_after:
            raise RuntimeError(
                "Sau khôi phục thiếu nền Bài 15.2.1: "
                + ", ".join(missing_after)
            )

        from jinja2 import Environment

        Environment().parse(
            restored
        )

        (
            count_after,
            integrity_after,
            fk_after,
            columns_after,
        ) = db_check()

        if count_after != count_before:
            raise RuntimeError(
                "Số bản ghi database thay đổi bất thường."
            )

        if columns_after != columns_before:
            raise RuntimeError(
                "Schema database thay đổi bất thường."
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
        print("KIỂM TRA SAU HOÀN TÁC V2:")
        print(
            " - Bài 15.2.2 gây treo: ĐÃ GỠ"
        )
        print(
            " - Bài 15.2.1: GIỮ NGUYÊN"
        )
        print(
            " - Schema Bài 15.1: GIỮ NGUYÊN"
        )
        print(
            " - Router lưu dữ liệu: KHÔNG ĐỤNG"
        )
        print(
            " - Database: KHÔNG THAY ĐỔI"
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
        print("=" * 132)
        print(
            "HOÀN TÁC BÀI 13B-11.15.2.2 V2 THÀNH CÔNG"
        )
        print("=" * 132)

        return 0

    except Exception:
        traceback.print_exc()

        print()
        print(
            "CÓ LỖI - ĐANG KHÔI PHỤC LẠI TEMPLATE "
            "TRƯỚC KHI CHẠY V2..."
        )

        try:
            shutil.copy2(
                CURRENT_TEMPLATE_BACKUP,
                TEMPLATE,
            )

            print(
                " - Đã khôi phục template hiện tại."
            )

        except Exception as exc:
            print(
                " - Lỗi khôi phục template:",
                exc,
            )

        clear_cache()

        print(
            "Backup an toàn:",
            SAFETY_BACKUP,
        )

        return 1


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
