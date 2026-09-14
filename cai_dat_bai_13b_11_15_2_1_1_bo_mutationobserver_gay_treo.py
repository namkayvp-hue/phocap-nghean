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
    / f"backup_bai_13b_11_15_2_1_1_bo_mutationobserver_{STAMP}"
)

TEMPLATE_BACKUP = (
    BACKUP
    / "app"
    / "templates"
    / "surveys"
    / "year_records.html"
)

DB_BACKUP = BACKUP / "data" / "phocap.db"

OLD_MARKER = "BAI_13B_11_15_2_PRIMARY_THCS_UI"
NEW_MARKER = "BAI_13B_11_15_2_1_1_SAFE_UI_NO_MUTATION_OBSERVER"

REQUIRED_TOKENS = (
    "b1512_primary_thcs_fields",
    "study_location_scope",
    "is_repeating_grade",
    "current_education_program",
    "BO_HOC",
    "CHUA_DI_HOC",
)

SAFE_JS = '\n<script>\n(function () {\n    // === BAI_13B_11_15_2_1_1_SAFE_UI_NO_MUTATION_OBSERVER ===\n\n    const shared = document.getElementById(\n        "b1512_primary_thcs_fields"\n    );\n\n    const programWrap = document.getElementById(\n        "b1512_program_wrap"\n    );\n\n    const locationSelect = document.getElementById(\n        "study_location_scope"\n    );\n\n    const repeatSelect = document.getElementById(\n        "is_repeating_grade"\n    );\n\n    const programSelect = document.getElementById(\n        "current_education_program"\n    );\n\n    const learningStatus =\n        document.getElementById(\n            "learning_status"\n        )\n        || document.querySelector(\n            \'select[name="learning_status"]\'\n        );\n\n    function isVisible(element) {\n        if (!element) {\n            return false;\n        }\n\n        if (element.hidden) {\n            return false;\n        }\n\n        const style = window.getComputedStyle(\n            element\n        );\n\n        if (\n            style.display === "none"\n            || style.visibility === "hidden"\n        ) {\n            return false;\n        }\n\n        return true;\n    }\n\n    function syncPrimaryThcsFields() {\n        const primaryField =\n            document.querySelector(\n                \'[name="completed_primary_program"]\'\n            );\n\n        const secondaryField =\n            document.querySelector(\n                \'[name="completed_lower_secondary_program"]\'\n            );\n\n        const primaryVisible = isVisible(\n            primaryField\n        );\n\n        const secondaryVisible = isVisible(\n            secondaryField\n        );\n\n        const showShared = (\n            primaryVisible\n            || secondaryVisible\n        );\n\n        if (shared) {\n            shared.hidden = !showShared;\n        }\n\n        if (locationSelect) {\n            locationSelect.disabled = !showShared;\n        }\n\n        if (repeatSelect) {\n            repeatSelect.disabled = !showShared;\n        }\n\n        if (programWrap) {\n            programWrap.hidden = !secondaryVisible;\n        }\n\n        if (programSelect) {\n            programSelect.disabled = !secondaryVisible;\n        }\n\n        if (learningStatus) {\n            const extraOptions =\n                learningStatus.querySelectorAll(\n                    "option[data-b1512-primary-thcs-status]"\n                );\n\n            extraOptions.forEach(\n                function (option) {\n                    option.hidden = !showShared;\n                    option.disabled = !showShared;\n                }\n            );\n        }\n    }\n\n    let timer = null;\n\n    function scheduleSync() {\n        if (timer !== null) {\n            window.clearTimeout(\n                timer\n            );\n        }\n\n        timer = window.setTimeout(\n            function () {\n                timer = null;\n                syncPrimaryThcsFields();\n            },\n            40\n        );\n    }\n\n    // Chỉ đồng bộ hữu hạn khi trang vừa tải.\n    syncPrimaryThcsFields();\n\n    window.setTimeout(\n        syncPrimaryThcsFields,\n        100\n    );\n\n    window.setTimeout(\n        syncPrimaryThcsFields,\n        400\n    );\n\n    // Chỉ nghe các control thực sự liên quan.\n    [\n        "school_id",\n        "school_name_reported",\n        "class_id",\n        "class_name_reported",\n        "learning_status"\n    ].forEach(\n        function (name) {\n            const elements =\n                document.querySelectorAll(\n                    \'[name="\' + name + \'"]\'\n                );\n\n            elements.forEach(\n                function (element) {\n                    element.addEventListener(\n                        "change",\n                        scheduleSync\n                    );\n\n                    element.addEventListener(\n                        "input",\n                        scheduleSync\n                    );\n                }\n            );\n        }\n    );\n})();\n</script>\n'


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

        columns = {
            str(row[1])
            for row in conn.execute(
                'PRAGMA table_info("survey_person_year_records")'
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


def backup_db() -> None:
    DB_BACKUP.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    src = sqlite3.connect(str(DB))
    dst = sqlite3.connect(str(DB_BACKUP))

    try:
        src.backup(dst)
        dst.commit()
    finally:
        dst.close()
        src.close()


def restore_db() -> None:
    src = sqlite3.connect(str(DB_BACKUP))
    dst = sqlite3.connect(str(DB))

    try:
        src.backup(dst)
        dst.commit()
    finally:
        dst.close()
        src.close()


def find_script_with_marker(
    text: str,
    marker: str,
) -> tuple[int, int, str] | None:
    for match in re.finditer(
        r"(?is)<script\b[^>]*>.*?</script>",
        text,
    ):
        block = match.group(0)

        if marker in block:
            return (
                match.start(),
                match.end(),
                block,
            )

    return None


def verify_template(text: str) -> None:
    from jinja2 import Environment

    Environment().parse(text)

    missing = [
        token
        for token in REQUIRED_TOKENS
        if token not in text
    ]

    if missing:
        raise RuntimeError(
            "Template thiếu nền Bài 15.2.1: "
            + ", ".join(missing)
        )

    safe_script = find_script_with_marker(
        text,
        NEW_MARKER,
    )

    if safe_script is None:
        raise RuntimeError(
            "Không tìm thấy JavaScript an toàn mới."
        )

    if "MutationObserver" in safe_script[2]:
        raise RuntimeError(
            "Script an toàn vẫn còn MutationObserver."
        )

    old_script = find_script_with_marker(
        text,
        OLD_MARKER,
    )

    if old_script is not None:
        raise RuntimeError(
            "Sau cài vẫn còn script UI cũ của Bài 15.2.1."
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
        "BÀI 13B-11.15.2.1.1 - "
        "GỠ MUTATIONOBSERVER GÂY TREO TRANG"
    )
    print("=" * 132)
    print()
    print("SỬA:")
    print(
        " - Chỉ thay JavaScript UI của Bài 15.2.1."
    )
    print(
        " - Gỡ MutationObserver theo dõi document.body."
    )
    print(
        " - Thay bằng đồng bộ hữu hạn khi tải trang "
        "và khi đổi trường/lớp."
    )
    print()
    print("GIỮ NGUYÊN:")
    print(
        " - Nơi học / Lưu ban / Chương trình đang học."
    )
    print(
        " - Bỏ học / Chưa đi học trong learning_status."
    )
    print(
        " - Router lưu dữ liệu."
    )
    print(
        " - Schema Bài 15.1."
    )
    print(
        " - Database."
    )
    print()
    print("AN TOÀN:")
    print(
        " - Backup template + database."
    )
    print(
        " - Không ALTER/INSERT/UPDATE/DELETE database."
    )
    print(
        " - Jinja + integrity + foreign key."
    )
    print(
        " - Có lỗi tự rollback."
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

    (
        count_before,
        integrity_before,
        fk_before,
        columns_before,
    ) = db_check()

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

    original = read_text(TEMPLATE)

    missing_tokens = [
        token
        for token in REQUIRED_TOKENS
        if token not in original
    ]

    if missing_tokens:
        raise RuntimeError(
            "Template hiện tại thiếu nền Bài 15.2.1: "
            + ", ".join(missing_tokens)
        )

    if NEW_MARKER in original:
        print(
            "Bài 15.2.1.1 đã có; không cài lặp."
        )
        return 0

    old_script = find_script_with_marker(
        original,
        OLD_MARKER,
    )

    if old_script is None:
        raise RuntimeError(
            "Không tìm thấy script UI cũ của Bài 15.2.1. "
            "Dừng để tránh sửa nhầm."
        )

    if "MutationObserver" not in old_script[2]:
        raise RuntimeError(
            "Script cũ không còn MutationObserver. "
            "Dừng để khảo sát lại."
        )

    print(
        "Đã xác định đúng script cũ gây treo."
    )
    print(
        "survey_person_year_records:",
        count_before,
        "bản ghi",
    )
    print(
        "integrity_check trước cài:",
        integrity_before,
    )
    print(
        "foreign_key_check trước cài:",
        fk_before,
        "lỗi",
    )

    BACKUP.mkdir(
        parents=True,
        exist_ok=False,
    )

    TEMPLATE_BACKUP.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    shutil.copy2(
        TEMPLATE,
        TEMPLATE_BACKUP,
    )

    backup_db()

    print(
        "Backup:",
        BACKUP,
    )

    try:
        start, end, _ = old_script

        patched = (
            original[:start]
            + SAFE_JS
            + original[end:]
        )

        verify_template(
            patched
        )

        TEMPLATE.write_text(
            patched,
            encoding="utf-8",
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
                "integrity_check sau cài không OK."
            )

        if fk_after != 0:
            raise RuntimeError(
                "foreign_key_check sau cài có "
                f"{fk_after} lỗi."
            )

        clear_cache()

        print()
        print("KIỂM TRA SAU CÀI:")
        print(
            " - MutationObserver Bài 15.2.1: ĐÃ GỠ"
        )
        print(
            " - Script hữu hạn an toàn: ĐÃ THAY"
        )
        print(
            " - Nơi học/Lưu ban/Chương trình: GIỮ NGUYÊN"
        )
        print(
            " - BO_HOC/CHUA_DI_HOC: GIỮ NGUYÊN"
        )
        print(
            " - Router: KHÔNG ĐỤNG"
        )
        print(
            " - Database/schema: KHÔNG THAY ĐỔI"
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
            "CÀI ĐẶT BÀI 13B-11.15.2.1.1 THÀNH CÔNG"
        )
        print("=" * 132)

        return 0

    except Exception:
        traceback.print_exc()

        print()
        print(
            "CÓ LỖI - ĐANG KHÔI PHỤC TEMPLATE/DATABASE..."
        )

        try:
            shutil.copy2(
                TEMPLATE_BACKUP,
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

        try:
            restore_db()

            print(
                " - Đã khôi phục database."
            )

        except Exception as exc:
            print(
                " - Lỗi khôi phục database:",
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
