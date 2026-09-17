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

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = (
    PROJECT
    / "exports"
    / f"backup_bai_13b_11_15_2_3_{STAMP}"
)

TEMPLATE_BACKUP = (
    BACKUP
    / "app"
    / "templates"
    / "surveys"
    / "year_records.html"
)

DB_BACKUP = (
    BACKUP
    / "data"
    / "phocap.db"
)

OLD_MARKER = (
    "BAI_13B_11_15_2_1_1_SAFE_UI_NO_MUTATION_OBSERVER"
)

NEW_MARKER = (
    "BAI_13B_11_15_2_3_EXCLUSIVE_LEVEL_SAFE_UI"
)

SAFE_JS = '\n<script>\n(function () {\n    // === BAI_13B_11_15_2_3_EXCLUSIVE_LEVEL_SAFE_UI ===\n    //\n    // Một bộ điều khiển duy nhất, KHÔNG MutationObserver.\n    // Ưu tiên xác định cấp bằng:\n    // 1. Lớp hiện tại/lớp theo phiếu.\n    // 2. Tên trường.\n    // 3. Tuổi chỉ là dự phòng.\n    //\n    // Tiểu học: chỉ khối TH + Nơi học/Lưu ban.\n    // THCS: chỉ khối THCS + Nơi học/Lưu ban/Chương trình.\n    // Mầm non: chỉ khối PCGDMN.\n    // Ngoài 3 cấp: ẩn cả 3 khối.\n\n    const LEVEL = {\n        MN: "MN",\n        TH: "TH",\n        THCS: "THCS",\n        OTHER: "OTHER",\n        UNKNOWN: "UNKNOWN"\n    };\n\n    function norm(value) {\n        return String(value || "")\n            .normalize("NFD")\n            .replace(/[\\u0300-\\u036f]/g, "")\n            .replace(/đ/g, "d")\n            .replace(/Đ/g, "D")\n            .trim()\n            .toLowerCase();\n    }\n\n    function byName(name) {\n        return document.querySelector(\n            \'[name="\' + name + \'"]\'\n        );\n    }\n\n    function controlText(element) {\n        if (!element) {\n            return "";\n        }\n\n        if (\n            element.tagName\n            && element.tagName.toLowerCase() === "select"\n        ) {\n            const option =\n                element.options[element.selectedIndex];\n\n            return (\n                (option ? option.text : "")\n                + " "\n                + (element.value || "")\n            ).trim();\n        }\n\n        return String(\n            element.value || element.textContent || ""\n        ).trim();\n    }\n\n    function classText() {\n        const candidates = [\n            byName("class_name_reported"),\n            document.getElementById(\n                "class_name_reported"\n            ),\n            byName("class_id"),\n            document.getElementById(\n                "class_id"\n            )\n        ];\n\n        for (const element of candidates) {\n            const value = controlText(\n                element\n            );\n\n            if (value) {\n                return value;\n            }\n        }\n\n        return "";\n    }\n\n    function schoolText() {\n        const candidates = [\n            byName("school_name_reported"),\n            document.getElementById(\n                "school_name_reported"\n            ),\n            byName("school_id"),\n            document.getElementById(\n                "school_id"\n            )\n        ];\n\n        for (const element of candidates) {\n            const value = controlText(\n                element\n            );\n\n            if (value) {\n                return value;\n            }\n        }\n\n        return "";\n    }\n\n    function levelFromClass(value) {\n        const raw = norm(\n            value\n        );\n\n        if (!raw) {\n            return LEVEL.UNKNOWN;\n        }\n\n        if (\n            raw.includes("mau giao")\n            || raw.includes("nha tre")\n            || raw.includes("mam non")\n            || raw.includes("tuoi")\n        ) {\n            return LEVEL.MN;\n        }\n\n        const match = raw.match(\n            /(?:^|\\D)(1[0-2]|[1-9])(?:\\D|$)/\n        );\n\n        if (!match) {\n            return LEVEL.UNKNOWN;\n        }\n\n        const grade = Number(\n            match[1]\n        );\n\n        if (\n            grade >= 1\n            && grade <= 5\n        ) {\n            return LEVEL.TH;\n        }\n\n        if (\n            grade >= 6\n            && grade <= 9\n        ) {\n            return LEVEL.THCS;\n        }\n\n        if (\n            grade >= 10\n            && grade <= 12\n        ) {\n            return LEVEL.OTHER;\n        }\n\n        return LEVEL.UNKNOWN;\n    }\n\n    function levelFromSchool(value) {\n        const raw = norm(\n            value\n        );\n\n        if (!raw) {\n            return LEVEL.UNKNOWN;\n        }\n\n        if (\n            raw.includes("thcs")\n            || raw.includes("trung hoc co so")\n        ) {\n            return LEVEL.THCS;\n        }\n\n        if (\n            raw.includes("tieu hoc")\n        ) {\n            return LEVEL.TH;\n        }\n\n        if (\n            raw.includes("mam non")\n            || raw.includes("mau giao")\n            || raw.includes("nha tre")\n        ) {\n            return LEVEL.MN;\n        }\n\n        if (\n            raw.includes("thpt")\n            || raw.includes("trung hoc pho thong")\n        ) {\n            return LEVEL.OTHER;\n        }\n\n        return LEVEL.UNKNOWN;\n    }\n\n    function levelFromAge() {\n        const dob =\n            "{{ person.date_of_birth.isoformat() if person and person.date_of_birth else \'\' }}";\n\n        const yearCode =\n            "{{ batch.school_year.code if batch and batch.school_year else \'\' }}";\n\n        const dobMatch =\n            String(dob).match(\n                /(\\d{4})/\n            );\n\n        const yearMatch =\n            String(yearCode).match(\n                /(\\d{4})/\n            );\n\n        if (\n            !dobMatch\n            || !yearMatch\n        ) {\n            return LEVEL.UNKNOWN;\n        }\n\n        const age =\n            Number(yearMatch[1])\n            - Number(dobMatch[1]);\n\n        if (\n            age >= 0\n            && age <= 5\n        ) {\n            return LEVEL.MN;\n        }\n\n        if (\n            age >= 6\n            && age <= 10\n        ) {\n            return LEVEL.TH;\n        }\n\n        if (\n            age >= 11\n            && age <= 14\n        ) {\n            return LEVEL.THCS;\n        }\n\n        return LEVEL.OTHER;\n    }\n\n    function detectLevel() {\n        let level = levelFromClass(\n            classText()\n        );\n\n        if (\n            level !== LEVEL.UNKNOWN\n        ) {\n            return level;\n        }\n\n        level = levelFromSchool(\n            schoolText()\n        );\n\n        if (\n            level !== LEVEL.UNKNOWN\n        ) {\n            return level;\n        }\n\n        return levelFromAge();\n    }\n\n    function findSection(\n        fieldNames,\n        headingTexts\n    ) {\n        let field = null;\n\n        for (const name of fieldNames) {\n            field = byName(\n                name\n            );\n\n            if (field) {\n                break;\n            }\n        }\n\n        if (!field) {\n            return null;\n        }\n\n        const wanted =\n            headingTexts.map(\n                norm\n            );\n\n        let node =\n            field.parentElement;\n\n        while (\n            node\n            && node !== document.body\n        ) {\n            const text = norm(\n                node.textContent\n            );\n\n            const hasHeading =\n                wanted.some(\n                    function (heading) {\n                        return text.includes(\n                            heading\n                        );\n                    }\n                );\n\n            if (hasHeading) {\n                return node;\n            }\n\n            node =\n                node.parentElement;\n        }\n\n        return null;\n    }\n\n    function setSectionVisible(\n        element,\n        visible\n    ) {\n        if (!element) {\n            return;\n        }\n\n        element.hidden = !visible;\n\n        if (visible) {\n            element.style.removeProperty(\n                "display"\n            );\n        } else {\n            element.style.setProperty(\n                "display",\n                "none",\n                "important"\n            );\n        }\n    }\n\n    function applyLevel() {\n        const level =\n            detectLevel();\n\n        const mnSection =\n            findSection(\n                [\n                    "completed_preschool_by_age",\n                    "completed_preschool_5",\n                    "attends_two_sessions_per_day",\n                    "prepared_vietnamese"\n                ],\n                [\n                    "Chỉ báo phục vụ báo cáo PCGDMN",\n                    "Các chỉ báo mầm non"\n                ]\n            );\n\n        const thSection =\n            findSection(\n                [\n                    "completed_primary_program"\n                ],\n                [\n                    "Các chỉ báo Tiểu học"\n                ]\n            );\n\n        const thcsSection =\n            findSection(\n                [\n                    "completed_lower_secondary_program",\n                    "post_lower_secondary_path"\n                ],\n                [\n                    "Các chỉ báo THCS"\n                ]\n            );\n\n        setSectionVisible(\n            mnSection,\n            level === LEVEL.MN\n        );\n\n        setSectionVisible(\n            thSection,\n            level === LEVEL.TH\n        );\n\n        setSectionVisible(\n            thcsSection,\n            level === LEVEL.THCS\n        );\n\n        const shared =\n            document.getElementById(\n                "b1512_primary_thcs_fields"\n            );\n\n        const programWrap =\n            document.getElementById(\n                "b1512_program_wrap"\n            );\n\n        const locationSelect =\n            document.getElementById(\n                "study_location_scope"\n            );\n\n        const repeatSelect =\n            document.getElementById(\n                "is_repeating_grade"\n            );\n\n        const programSelect =\n            document.getElementById(\n                "current_education_program"\n            );\n\n        const sharedVisible = (\n            level === LEVEL.TH\n            || level === LEVEL.THCS\n        );\n\n        if (shared) {\n            shared.hidden =\n                !sharedVisible;\n\n            if (sharedVisible) {\n                shared.style.removeProperty(\n                    "display"\n                );\n            } else {\n                shared.style.setProperty(\n                    "display",\n                    "none",\n                    "important"\n                );\n            }\n        }\n\n        if (locationSelect) {\n            locationSelect.disabled =\n                !sharedVisible;\n        }\n\n        if (repeatSelect) {\n            repeatSelect.disabled =\n                !sharedVisible;\n        }\n\n        const programVisible =\n            level === LEVEL.THCS;\n\n        if (programWrap) {\n            programWrap.hidden =\n                !programVisible;\n\n            if (programVisible) {\n                programWrap.style.removeProperty(\n                    "display"\n                );\n            } else {\n                programWrap.style.setProperty(\n                    "display",\n                    "none",\n                    "important"\n                );\n            }\n        }\n\n        if (programSelect) {\n            programSelect.disabled =\n                !programVisible;\n        }\n\n        const learningStatus =\n            document.getElementById(\n                "learning_status"\n            )\n            || byName(\n                "learning_status"\n            );\n\n        if (learningStatus) {\n            const extraOptions =\n                learningStatus.querySelectorAll(\n                    "option[data-b1512-primary-thcs-status]"\n                );\n\n            extraOptions.forEach(\n                function (option) {\n                    option.hidden =\n                        !sharedVisible;\n\n                    option.disabled =\n                        !sharedVisible;\n                }\n            );\n        }\n\n        document.documentElement.setAttribute(\n            "data-b15123-level",\n            level\n        );\n    }\n\n    let timer = null;\n\n    function scheduleApply() {\n        if (timer !== null) {\n            window.clearTimeout(\n                timer\n            );\n        }\n\n        timer = window.setTimeout(\n            function () {\n                timer = null;\n                applyLevel();\n            },\n            60\n        );\n    }\n\n    // Chạy hữu hạn sau khi trang render.\n    applyLevel();\n\n    window.setTimeout(\n        applyLevel,\n        120\n    );\n\n    window.setTimeout(\n        applyLevel,\n        450\n    );\n\n    window.setTimeout(\n        applyLevel,\n        900\n    );\n\n    // Chỉ cập nhật lại khi người dùng đổi trường/lớp.\n    [\n        "school_id",\n        "school_name_reported",\n        "class_id",\n        "class_name_reported"\n    ].forEach(\n        function (name) {\n            const elements =\n                document.querySelectorAll(\n                    \'[name="\' + name + \'"]\'\n                );\n\n            elements.forEach(\n                function (element) {\n                    element.addEventListener(\n                        "change",\n                        scheduleApply\n                    );\n\n                    element.addEventListener(\n                        "input",\n                        scheduleApply\n                    );\n                }\n            );\n        }\n    );\n})();\n</script>\n'


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
    conn = sqlite3.connect(
        str(DB)
    )

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

    src = sqlite3.connect(
        str(DB)
    )

    dst = sqlite3.connect(
        str(DB_BACKUP)
    )

    try:
        src.backup(
            dst
        )
        dst.commit()
    finally:
        dst.close()
        src.close()


def restore_db() -> None:
    src = sqlite3.connect(
        str(DB_BACKUP)
    )

    dst = sqlite3.connect(
        str(DB)
    )

    try:
        src.backup(
            dst
        )
        dst.commit()
    finally:
        dst.close()
        src.close()


def find_script(
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


def verify_template(
    text: str,
) -> None:
    from jinja2 import Environment

    Environment().parse(
        text
    )

    required = (
        NEW_MARKER,
        "completed_primary_program",
        "completed_lower_secondary_program",
        "b1512_primary_thcs_fields",
        "b1512_program_wrap",
        "study_location_scope",
        "is_repeating_grade",
        "current_education_program",
    )

    for token in required:
        if token not in text:
            raise RuntimeError(
                "Template sau cài thiếu: "
                + token
            )

    new_script = find_script(
        text,
        NEW_MARKER,
    )

    if new_script is None:
        raise RuntimeError(
            "Không tìm thấy script Bài 15.2.3."
        )

    if "MutationObserver" in new_script[2]:
        raise RuntimeError(
            "Bài 15.2.3 không được chứa MutationObserver."
        )

    if find_script(
        text,
        OLD_MARKER,
    ) is not None:
        raise RuntimeError(
            "Script Bài 15.2.1.1 cũ vẫn còn sau thay thế."
        )


def clear_cache() -> None:
    for cache in APP.rglob(
        "__pycache__"
    ):
        if cache.is_dir():
            shutil.rmtree(
                cache,
                ignore_errors=True,
            )


def main() -> int:
    print("=" * 132)
    print(
        "BÀI 13B-11.15.2.3 - "
        "CHỈ HIỂN THỊ ĐÚNG CHỈ BÁO THEO CẤP HỌC, "
        "KHÔNG MUTATIONOBSERVER"
    )
    print("=" * 132)
    print()
    print("QUY TẮC:")
    print(
        " - Lớp 1-5: chỉ chỉ báo Tiểu học."
    )
    print(
        " - Lớp 6-9: chỉ chỉ báo THCS."
    )
    print(
        " - Mầm non: chỉ chỉ báo PCGDMN."
    )
    print(
        " - THPT/ngoài 3 cấp: ẩn cả 3 khối."
    )
    print(
        " - Nơi học + Lưu ban: chỉ TH và THCS."
    )
    print(
        " - Chương trình THPT/GDTX/GDNN/Khác: chỉ THCS."
    )
    print()
    print("AN TOÀN:")
    print(
        " - Thay đúng script hữu hạn của Bài 15.2.1.1."
    )
    print(
        " - KHÔNG MutationObserver."
    )
    print(
        " - Không sửa router."
    )
    print(
        " - Không sửa database/schema/dữ liệu."
    )
    print(
        " - Backup template + database; lỗi rollback."
    )
    print()

    if not TEMPLATE.exists():
        raise RuntimeError(
            f"Không tìm thấy: {TEMPLATE}"
        )

    if not DB.exists():
        raise RuntimeError(
            f"Không tìm thấy: {DB}"
        )

    (
        count_before,
        integrity_before,
        fk_before,
        columns_before,
    ) = db_check()

    if (
        integrity_before.lower()
        != "ok"
        or fk_before != 0
    ):
        raise RuntimeError(
            "Database không đạt kiểm tra an toàn."
        )

    original = read_text(
        TEMPLATE
    )

    if NEW_MARKER in original:
        print(
            "Bài 15.2.3 đã có; không cài lặp."
        )
        return 0

    old_script = find_script(
        original,
        OLD_MARKER,
    )

    if old_script is None:
        raise RuntimeError(
            "Không tìm thấy script an toàn Bài 15.2.1.1. "
            "Dừng để tránh sửa nhầm."
        )

    if "MutationObserver" in old_script[2]:
        raise RuntimeError(
            "Script hiện tại lại có MutationObserver. "
            "Dừng để tránh tái tạo lỗi treo."
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
                "Số bản ghi database thay đổi khi cài."
            )

        if columns_after != columns_before:
            raise RuntimeError(
                "Schema database thay đổi khi cài."
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
            " - MutationObserver: KHÔNG CÓ"
        )
        print(
            " - Tiểu học: chỉ khối Tiểu học"
        )
        print(
            " - THCS: chỉ khối THCS"
        )
        print(
            " - Mầm non: chỉ khối PCGDMN"
        )
        print(
            " - Chương trình đang học: chỉ THCS"
        )
        print(
            " - Nơi học/Lưu ban: TH + THCS"
        )
        print(
            " - Jinja parse: OK"
        )
        print(
            " - Database/schema/dữ liệu: KHÔNG THAY ĐỔI"
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
            "CÀI ĐẶT BÀI 13B-11.15.2.3 THÀNH CÔNG"
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
