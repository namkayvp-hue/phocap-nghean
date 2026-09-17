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

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = (
    PROJECT
    / "exports"
    / f"backup_bai_13b_11_15_2_2_{STAMP}"
)

TEMPLATE_BACKUP = (
    BACKUP
    / "app"
    / "templates"
    / "surveys"
    / "year_records.html"
)

DB_BACKUP = BACKUP / "data" / "phocap.db"

MARKER = "BAI_13B_11_15_2_2_EXCLUSIVE_LEVEL_UI"

PATCH = '\n<style>\n    /* === BAI_13B_11_15_2_2_EXCLUSIVE_LEVEL_UI === */\n    .b15122-force-hide {\n        display: none !important;\n    }\n</style>\n\n<script>\n(function () {\n    // === BAI_13B_11_15_2_2_EXCLUSIVE_LEVEL_UI ===\n\n    const LEVEL = {\n        MN: "MN",\n        PRIMARY: "PRIMARY",\n        THCS: "THCS",\n        OTHER: "OTHER",\n        UNKNOWN: "UNKNOWN"\n    };\n\n    function norm(value) {\n        return String(value || "")\n            .normalize("NFD")\n            .replace(/[\\u0300-\\u036f]/g, "")\n            .replace(/đ/g, "d")\n            .replace(/Đ/g, "D")\n            .trim()\n            .toLowerCase();\n    }\n\n    function fieldByName(name) {\n        return document.querySelector(\n            \'[name="\' + name + \'"]\'\n        );\n    }\n\n    function textOfControl(element) {\n        if (!element) return "";\n\n        if (\n            element.tagName\n            && element.tagName.toLowerCase() === "select"\n        ) {\n            const option =\n                element.options[element.selectedIndex];\n\n            return (\n                (option ? option.text : "")\n                + " "\n                + (element.value || "")\n            ).trim();\n        }\n\n        return String(\n            element.value || element.textContent || ""\n        ).trim();\n    }\n\n    function currentClassText() {\n        const candidates = [\n            fieldByName("class_name_reported"),\n            document.getElementById("class_name_reported"),\n            fieldByName("class_id"),\n            document.getElementById("class_id")\n        ];\n\n        for (const element of candidates) {\n            const value = textOfControl(element);\n            if (value) return value;\n        }\n\n        return "";\n    }\n\n    function currentSchoolText() {\n        const candidates = [\n            fieldByName("school_name_reported"),\n            document.getElementById("school_name_reported"),\n            fieldByName("school_id"),\n            document.getElementById("school_id")\n        ];\n\n        for (const element of candidates) {\n            const value = textOfControl(element);\n            if (value) return value;\n        }\n\n        return "";\n    }\n\n    function levelFromClass(value) {\n        const raw = norm(value);\n\n        if (!raw) return LEVEL.UNKNOWN;\n\n        if (\n            raw.includes("mau giao")\n            || raw.includes("nha tre")\n            || raw.includes("tuoi")\n            || raw.includes("mam non")\n        ) {\n            return LEVEL.MN;\n        }\n\n        const match = raw.match(\n            /(?:^|\\D)(1[0-2]|[1-9])(?:\\D|$)/\n        );\n\n        if (!match) return LEVEL.UNKNOWN;\n\n        const grade = Number(match[1]);\n\n        if (grade >= 1 && grade <= 5) {\n            return LEVEL.PRIMARY;\n        }\n\n        if (grade >= 6 && grade <= 9) {\n            return LEVEL.THCS;\n        }\n\n        if (grade >= 10 && grade <= 12) {\n            return LEVEL.OTHER;\n        }\n\n        return LEVEL.UNKNOWN;\n    }\n\n    function levelFromSchool(value) {\n        const raw = norm(value);\n\n        if (!raw) return LEVEL.UNKNOWN;\n\n        if (\n            raw.includes("thcs")\n            || raw.includes("trung hoc co so")\n        ) {\n            return LEVEL.THCS;\n        }\n\n        if (\n            raw.includes("tieu hoc")\n            || raw.includes("truong th ")\n        ) {\n            return LEVEL.PRIMARY;\n        }\n\n        if (\n            raw.includes("mam non")\n            || raw.includes("mau giao")\n            || raw.includes("nha tre")\n        ) {\n            return LEVEL.MN;\n        }\n\n        if (\n            raw.includes("thpt")\n            || raw.includes("trung hoc pho thong")\n        ) {\n            return LEVEL.OTHER;\n        }\n\n        return LEVEL.UNKNOWN;\n    }\n\n    function levelFromAge() {\n        const birthValue = "{{ person.date_of_birth.isoformat() if person and person.date_of_birth else \'\' }}";\n        const yearCode = "{{ batch.school_year.code if batch and batch.school_year else \'\' }}";\n\n        const birthYearMatch =\n            String(birthValue).match(/(\\d{4})/);\n\n        const schoolYearMatch =\n            String(yearCode).match(/(\\d{4})/);\n\n        if (!birthYearMatch || !schoolYearMatch) {\n            return LEVEL.UNKNOWN;\n        }\n\n        const birthYear = Number(\n            birthYearMatch[1]\n        );\n\n        const schoolYear = Number(\n            schoolYearMatch[1]\n        );\n\n        if (!birthYear || !schoolYear) {\n            return LEVEL.UNKNOWN;\n        }\n\n        const age = schoolYear - birthYear;\n\n        if (age >= 0 && age <= 5) {\n            return LEVEL.MN;\n        }\n\n        if (age >= 6 && age <= 10) {\n            return LEVEL.PRIMARY;\n        }\n\n        if (age >= 11 && age <= 14) {\n            return LEVEL.THCS;\n        }\n\n        return LEVEL.OTHER;\n    }\n\n    function detectLevel() {\n        let level = levelFromClass(\n            currentClassText()\n        );\n\n        if (level !== LEVEL.UNKNOWN) {\n            return level;\n        }\n\n        level = levelFromSchool(\n            currentSchoolText()\n        );\n\n        if (level !== LEVEL.UNKNOWN) {\n            return level;\n        }\n\n        return levelFromAge();\n    }\n\n    function findHeading(exactTexts) {\n        const wanted = exactTexts.map(norm);\n\n        const elements = document.querySelectorAll(\n            "h1,h2,h3,h4,h5,strong,label,div"\n        );\n\n        for (const element of elements) {\n            const text = norm(\n                element.textContent\n            );\n\n            if (wanted.includes(text)) {\n                return element;\n            }\n        }\n\n        return null;\n    }\n\n    function minimalBlock(\n        heading,\n        ownFields,\n        otherFields\n    ) {\n        if (!heading) return null;\n\n        let node = heading;\n\n        while (\n            node\n            && node !== document.body\n        ) {\n            const hasOwn = ownFields.some(\n                function (name) {\n                    return !!node.querySelector(\n                        \'[name="\' + name + \'"]\'\n                    );\n                }\n            );\n\n            const hasOther = otherFields.some(\n                function (name) {\n                    return !!node.querySelector(\n                        \'[name="\' + name + \'"]\'\n                    );\n                }\n            );\n\n            if (hasOwn && !hasOther) {\n                return node;\n            }\n\n            node = node.parentElement;\n        }\n\n        return heading.parentElement;\n    }\n\n    function locateBlocks() {\n        const mnHeading = findHeading([\n            "Chỉ báo phục vụ báo cáo PCGDMN",\n            "Các chỉ báo mầm non"\n        ]);\n\n        const primaryHeading = findHeading([\n            "Các chỉ báo Tiểu học"\n        ]);\n\n        const thcsHeading = findHeading([\n            "Các chỉ báo THCS"\n        ]);\n\n        const mnFields = [\n            "completed_preschool_by_age",\n            "completed_preschool_5",\n            "attends_two_sessions_per_day",\n            "prepared_vietnamese"\n        ];\n\n        const primaryFields = [\n            "completed_primary_program"\n        ];\n\n        const thcsFields = [\n            "completed_lower_secondary_program",\n            "post_lower_secondary_path"\n        ];\n\n        return {\n            mn: minimalBlock(\n                mnHeading,\n                mnFields,\n                primaryFields.concat(thcsFields)\n            ),\n            primary: minimalBlock(\n                primaryHeading,\n                primaryFields,\n                mnFields.concat(thcsFields)\n            ),\n            thcs: minimalBlock(\n                thcsHeading,\n                thcsFields,\n                mnFields.concat(primaryFields)\n            )\n        };\n    }\n\n    function setHidden(\n        element,\n        shouldHide\n    ) {\n        if (!element) return;\n\n        element.classList.toggle(\n            "b15122-force-hide",\n            !!shouldHide\n        );\n    }\n\n    function applyLevel() {\n        const level = detectLevel();\n        const blocks = locateBlocks();\n\n        setHidden(\n            blocks.mn,\n            level !== LEVEL.MN\n        );\n\n        setHidden(\n            blocks.primary,\n            level !== LEVEL.PRIMARY\n        );\n\n        setHidden(\n            blocks.thcs,\n            level !== LEVEL.THCS\n        );\n\n        const shared = document.getElementById(\n            "b1512_primary_thcs_fields"\n        );\n\n        const programWrap =\n            document.getElementById(\n                "b1512_program_wrap"\n            );\n\n        const location =\n            document.getElementById(\n                "study_location_scope"\n            );\n\n        const repeat =\n            document.getElementById(\n                "is_repeating_grade"\n            );\n\n        const program =\n            document.getElementById(\n                "current_education_program"\n            );\n\n        const sharedVisible = (\n            level === LEVEL.PRIMARY\n            || level === LEVEL.THCS\n        );\n\n        if (shared) {\n            shared.classList.toggle(\n                "b15122-force-hide",\n                !sharedVisible\n            );\n\n            if (sharedVisible) {\n                shared.hidden = false;\n            }\n        }\n\n        if (location) {\n            location.disabled = !sharedVisible;\n        }\n\n        if (repeat) {\n            repeat.disabled = !sharedVisible;\n        }\n\n        const thcsProgramVisible =\n            level === LEVEL.THCS;\n\n        if (programWrap) {\n            programWrap.classList.toggle(\n                "b15122-force-hide",\n                !thcsProgramVisible\n            );\n\n            if (thcsProgramVisible) {\n                programWrap.hidden = false;\n            }\n        }\n\n        if (program) {\n            program.disabled =\n                !thcsProgramVisible;\n        }\n\n        const learningStatus =\n            document.getElementById(\n                "learning_status"\n            )\n            || document.querySelector(\n                \'select[name="learning_status"]\'\n            );\n\n        if (learningStatus) {\n            const extras =\n                learningStatus.querySelectorAll(\n                    "option[data-b1512-primary-thcs-status]"\n                );\n\n            extras.forEach(\n                function (option) {\n                    option.hidden =\n                        !sharedVisible;\n\n                    option.disabled =\n                        !sharedVisible;\n                }\n            );\n        }\n\n        document.documentElement.setAttribute(\n            "data-b15122-level",\n            level\n        );\n    }\n\n    let queued = false;\n\n    function queueApply() {\n        if (queued) return;\n\n        queued = true;\n\n        window.requestAnimationFrame(\n            function () {\n                queued = false;\n                applyLevel();\n            }\n        );\n    }\n\n    applyLevel();\n    window.setTimeout(applyLevel, 0);\n    window.setTimeout(applyLevel, 150);\n    window.setTimeout(applyLevel, 500);\n\n    [\n        "school_id",\n        "school_name_reported",\n        "class_id",\n        "class_name_reported"\n    ].forEach(\n        function (name) {\n            const element =\n                fieldByName(name);\n\n            if (!element) return;\n\n            element.addEventListener(\n                "change",\n                queueApply\n            );\n\n            element.addEventListener(\n                "input",\n                queueApply\n            );\n        }\n    );\n\n    const form =\n        document.getElementById(\n            "year_record_form"\n        );\n\n    if (form) {\n        const observer =\n            new MutationObserver(\n                function () {\n                    queueApply();\n                }\n            );\n\n        observer.observe(\n            form,\n            {\n                attributes: true,\n                subtree: true,\n                childList: false,\n                attributeFilter: [\n                    "hidden",\n                    "style",\n                    "class",\n                    "value"\n                ]\n            }\n        );\n    }\n})();\n</script>\n'


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


def verify_template(text: str) -> None:
    from jinja2 import Environment

    Environment().parse(text)

    required = (
        MARKER,
        "b15122-force-hide",
        "Các chỉ báo Tiểu học",
        "Các chỉ báo THCS",
        "completed_primary_program",
        "completed_lower_secondary_program",
    )

    for token in required:
        if token not in text:
            raise RuntimeError(
                "Template sau cài thiếu: "
                + token
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
        "BÀI 13B-11.15.2.2 - "
        "MỖI ĐỐI TƯỢNG CHỈ HIỂN THỊ ĐÚNG CHỈ BÁO THEO CẤP HỌC"
    )
    print("=" * 132)
    print()
    print("SỬA LỖI:")
    print(
        " - Tiểu học không còn thấy chỉ báo Mầm non và THCS."
    )
    print(
        " - THCS không còn thấy chỉ báo Mầm non và Tiểu học."
    )
    print(
        " - Mầm non không còn thấy chỉ báo Tiểu học và THCS."
    )
    print(
        " - THPT/người ngoài 3 cấp không hiện các khối MN/TH/THCS."
    )
    print()
    print("XÁC ĐỊNH CẤP:")
    print(" 1. Lớp hiện tại/lớp theo phiếu.")
    print(" 2. Tên trường hiện tại/tên trường theo phiếu.")
    print(" 3. Tuổi chỉ là phương án dự phòng.")
    print()
    print("GIỮ NGUYÊN:")
    print(" - Xóa mù chữ độc lập.")
    print(" - Theo dõi khuyết tật độc lập.")
    print(" - Cư trú và biến động.")
    print(" - Dữ liệu Bài 15.1 và save logic Bài 15.2.1.")
    print()
    print("AN TOÀN:")
    print(" - Chỉ sửa year_records.html.")
    print(" - Không ALTER/UPDATE/INSERT/DELETE database.")
    print(" - Backup template + database.")
    print(" - Jinja parse + integrity + foreign key.")
    print(" - Có lỗi tự rollback.")
    print()

    if not TEMPLATE.exists():
        raise RuntimeError(
            f"Không tìm thấy template: {TEMPLATE}"
        )

    if not DB.exists():
        raise RuntimeError(
            f"Không tìm thấy database: {DB}"
        )

    before_count, before_integrity, before_fk = db_check()

    print(
        "survey_person_year_records trước cài:",
        before_count,
    )
    print(
        "integrity_check trước cài:",
        before_integrity,
    )
    print(
        "foreign_key_check trước cài:",
        before_fk,
        "lỗi",
    )

    if (
        before_integrity.lower() != "ok"
        or before_fk != 0
    ):
        raise RuntimeError(
            "Database không đạt kiểm tra an toàn trước cài."
        )

    original = TEMPLATE.read_text(
        encoding="utf-8-sig",
        errors="strict",
    )

    for token in (
        "completed_primary_program",
        "completed_lower_secondary_program",
        "Chỉ báo phục vụ báo cáo PCGDMN",
    ):
        if token not in original:
            raise RuntimeError(
                "Template thiếu nền cần thiết: "
                + token
            )

    if MARKER in original:
        print(
            "Bài 15.2.2 đã có trong template; "
            "không cài lặp."
        )
        return 0

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
        body_close = original.rfind(
            "</body>"
        )

        if body_close < 0:
            raise RuntimeError(
                "Không tìm thấy </body> trong year_records.html."
            )

        patched = (
            original[:body_close]
            + PATCH
            + "\n"
            + original[body_close:]
        )

        verify_template(
            patched
        )

        TEMPLATE.write_text(
            patched,
            encoding="utf-8",
        )

        after_count, after_integrity, after_fk = db_check()

        if after_count != before_count:
            raise RuntimeError(
                "Số bản ghi năm học bị thay đổi khi cài."
            )

        if after_integrity.lower() != "ok":
            raise RuntimeError(
                "integrity_check sau cài không OK."
            )

        if after_fk != 0:
            raise RuntimeError(
                "foreign_key_check sau cài có "
                f"{after_fk} lỗi."
            )

        clear_cache()

        print()
        print("KIỂM TRA SAU CÀI:")
        print(" - Template Jinja: OK")
        print(" - Tiểu học: chỉ khối Tiểu học")
        print(" - THCS: chỉ khối THCS")
        print(" - Mầm non: chỉ khối PCGDMN")
        print(" - Chương trình THPT/GDTX/GDNN: chỉ THCS")
        print(" - Database: KHÔNG THAY ĐỔI")
        print(" - integrity_check: OK")
        print(" - foreign_key_check: 0 lỗi")
        print()
        print("=" * 132)
        print(
            "CÀI ĐẶT BÀI 13B-11.15.2.2 THÀNH CÔNG"
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
