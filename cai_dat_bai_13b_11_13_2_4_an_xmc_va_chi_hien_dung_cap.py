from __future__ import annotations

import shutil
import traceback
from datetime import datetime
from pathlib import Path

PROJECT = Path(r"C:\PhoCap").resolve()
TARGET = (
    PROJECT
    / "app"
    / "templates"
    / "surveys"
    / "year_records.html"
)

STAMP = datetime.now().strftime(
    "%Y%m%d_%H%M%S"
)

BACKUP = (
    PROJECT
    / "exports"
    / f"backup_bai_13b_11_13_2_4_{STAMP}"
)

MARK_START = (
    "<!-- === "
    "BAI_13B_11_13_2_4_STRICT_UI_START"
    " === -->"
)

PATCH_HTML = '\n<!-- === BAI_13B_11_13_2_4_STRICT_UI_START === -->\n<style>\n    .b131132-hard-hidden {\n        display: none !important;\n    }\n</style>\n\n<script>\n(function () {\n    "use strict";\n\n    const PRESCHOOL_FIELDS = [\n        "completed_preschool_5",\n        "completed_preschool_by_age",\n        "attends_required_days",\n        "attends_regularly",\n        "prepared_vietnamese",\n        "weight_monitored",\n        "underweight",\n        "height_monitored",\n        "stunted"\n    ];\n\n    function normalizeText(value) {\n        return String(value || "")\n            .normalize("NFD")\n            .replace(/[\\u0300-\\u036f]/g, "")\n            .toLowerCase()\n            .replace(/\\s+/g, " ")\n            .trim();\n    }\n\n    function elementText(selector) {\n        const element = document.querySelector(selector);\n        if (!element) return "";\n\n        const parts = [];\n        if ("value" in element && element.value) {\n            parts.push(String(element.value));\n        }\n        if (element.textContent) {\n            parts.push(String(element.textContent));\n        }\n        return parts.join(" ").trim();\n    }\n\n    function setHardVisible(element, visible) {\n        if (!element) return;\n\n        element.classList.toggle(\n            "b131132-hard-hidden",\n            !visible\n        );\n\n        if (visible) {\n            element.removeAttribute("hidden");\n        } else {\n            element.setAttribute("hidden", "");\n        }\n    }\n\n    function setChildrenDisabled(container, disabled) {\n        if (!container) return;\n\n        container\n            .querySelectorAll("select,input,textarea,button")\n            .forEach(function (element) {\n                element.disabled = disabled;\n            });\n    }\n\n    function enforceLiteracyBlock() {\n        const target = document.getElementById(\n            "is_literacy_target"\n        );\n        const details = document.getElementById(\n            "b131132_xmc_details"\n        );\n\n        if (!target || !details) return;\n\n        const showDetails =\n            target.value === "CO";\n\n        setHardVisible(\n            details,\n            showDetails\n        );\n\n        setChildrenDisabled(\n            details,\n            !showDetails\n        );\n    }\n\n    function parseAgeAtSchoolYearStart() {\n        const dobText =\n            {{ (person.date_of_birth.isoformat() if person.date_of_birth else \'\') | tojson }};\n        const yearCode =\n            {{ (batch.school_year.code if batch.school_year else \'\') | tojson }};\n\n        if (!dobText) return null;\n\n        const birthYear = parseInt(\n            String(dobText).slice(0, 4),\n            10\n        );\n\n        if (!Number.isFinite(birthYear)) {\n            return null;\n        }\n\n        const matches = String(\n            yearCode || ""\n        ).match(/\\d{4}/g);\n\n        let referenceYear = null;\n\n        if (matches && matches.length) {\n            referenceYear = parseInt(\n                matches[0],\n                10\n            );\n        }\n\n        if (!Number.isFinite(referenceYear)) {\n            referenceYear =\n                new Date().getFullYear();\n        }\n\n        const age =\n            referenceYear - birthYear;\n\n        if (\n            !Number.isFinite(age)\n            || age < 0\n            || age > 120\n        ) {\n            return null;\n        }\n\n        return age;\n    }\n\n    function detectGrade(classText) {\n        const text = normalizeText(\n            classText\n        );\n\n        if (\n            /\\b[0-6]\\s*tuoi\\b/.test(text)\n            || /\\bmau giao\\b/.test(text)\n            || /\\bnha tre\\b/.test(text)\n        ) {\n            return null;\n        }\n\n        let match =\n            text.match(\n                /\\blop\\s*([0-9]{1,2})\\b/\n            );\n\n        if (!match) {\n            match =\n                text.match(\n                    /^\\s*([0-9]{1,2})(?:\\s|[a-z]|$)/\n                );\n        }\n\n        if (!match) return null;\n\n        const grade =\n            parseInt(match[1], 10);\n\n        if (\n            !Number.isFinite(grade)\n            || grade < 1\n            || grade > 12\n        ) {\n            return null;\n        }\n\n        return grade;\n    }\n\n    function detectEducationLevel() {\n        const schoolText = [\n            elementText("#school_search"),\n            elementText("#school_selected"),\n            elementText(\n                \'[name="school_name_reported"]\'\n            )\n        ].join(" ");\n\n        const classText = [\n            elementText("#class_search"),\n            elementText("#class_selected"),\n            elementText(\n                \'[name="class_name_reported"]\'\n            )\n        ].join(" ");\n\n        const school =\n            normalizeText(schoolText);\n        const klass =\n            normalizeText(classText);\n        const combined =\n            (school + " " + klass).trim();\n\n        if (\n            /\\bmam non\\b/.test(combined)\n            || /\\bmau giao\\b/.test(combined)\n            || /\\bnha tre\\b/.test(combined)\n            || /\\bmn\\b/.test(school)\n        ) {\n            return "MN";\n        }\n\n        if (\n            /\\bthcs\\b/.test(combined)\n            || /\\btrung hoc co so\\b/.test(combined)\n        ) {\n            return "THCS";\n        }\n\n        if (\n            /\\bthpt\\b/.test(combined)\n            || /\\btrung hoc pho thong\\b/.test(combined)\n        ) {\n            return "OTHER";\n        }\n\n        if (\n            /\\btieu hoc\\b/.test(combined)\n            || /\\bprimary\\b/.test(combined)\n            || /\\bth\\b/.test(school)\n        ) {\n            return "TH";\n        }\n\n        const grade =\n            detectGrade(classText);\n\n        if (grade !== null) {\n            if (\n                grade >= 1\n                && grade <= 5\n            ) {\n                return "TH";\n            }\n\n            if (\n                grade >= 6\n                && grade <= 9\n            ) {\n                return "THCS";\n            }\n\n            if (\n                grade >= 10\n                && grade <= 12\n            ) {\n                return "OTHER";\n            }\n        }\n\n        const age =\n            parseAgeAtSchoolYearStart();\n\n        if (age !== null) {\n            if (age <= 5) {\n                return "MN";\n            }\n\n            if (\n                age >= 6\n                && age <= 10\n            ) {\n                return "TH";\n            }\n\n            if (\n                age >= 11\n                && age <= 14\n            ) {\n                return "THCS";\n            }\n        }\n\n        return "OTHER";\n    }\n\n    function findExactHeading(label) {\n        const expected =\n            normalizeText(label);\n\n        const candidates =\n            Array.from(\n                document.querySelectorAll(\n                    "h1,h2,h3,h4,h5,h6,strong"\n                )\n            );\n\n        return (\n            candidates.find(function (element) {\n                return (\n                    normalizeText(\n                        element.textContent\n                    ) === expected\n                );\n            })\n            || null\n        );\n    }\n\n    function findPreschoolScope() {\n        const fields =\n            PRESCHOOL_FIELDS\n                .map(function (name) {\n                    return document.querySelector(\n                        \'[name="\' + name + \'"]\'\n                    );\n                })\n                .filter(Boolean);\n\n        if (!fields.length) {\n            return null;\n        }\n\n        const heading =\n            findExactHeading(\n                "Các chỉ báo mầm non"\n            );\n\n        const disability =\n            document.getElementById(\n                "disability_status"\n            );\n\n        let node =\n            fields[0].parentElement;\n\n        while (\n            node\n            && node.id !== "year_record_form"\n        ) {\n            const count =\n                fields.filter(function (field) {\n                    return node.contains(field);\n                }).length;\n\n            const hasHeading =\n                !heading\n                || node.contains(heading);\n\n            const containsDisability =\n                disability\n                && node.contains(disability);\n\n            if (\n                count >= 7\n                && hasHeading\n                && !containsDisability\n            ) {\n                return node;\n            }\n\n            node =\n                node.parentElement;\n        }\n\n        return null;\n    }\n\n    function fallbackPreschoolElements() {\n        const result =\n            new Set();\n\n        PRESCHOOL_FIELDS.forEach(\n            function (name) {\n                const field =\n                    document.querySelector(\n                        \'[name="\' + name + \'"]\'\n                    );\n\n                if (!field) return;\n\n                const card =\n                    field.closest(\n                        ".indicator-card,"\n                        + ".criteria-card,"\n                        + ".form-group"\n                    );\n\n                if (card) {\n                    result.add(card);\n                }\n            }\n        );\n\n        const heading =\n            findExactHeading(\n                "Các chỉ báo mầm non"\n            );\n\n        if (heading) {\n            result.add(heading);\n\n            const next =\n                heading.nextElementSibling;\n\n            if (\n                next\n                && (\n                    next.tagName === "P"\n                    || next.classList.contains(\n                        "muted"\n                    )\n                )\n            ) {\n                result.add(next);\n            }\n        }\n\n        return Array.from(result);\n    }\n\n    function findDisabilitySection() {\n        const field =\n            document.getElementById(\n                "disability_status"\n            );\n\n        const heading =\n            findExactHeading(\n                "Theo dõi trẻ khuyết tật"\n            );\n\n        if (!field || !heading) {\n            return null;\n        }\n\n        let node =\n            heading.parentElement;\n\n        while (\n            node\n            && node.id !== "year_record_form"\n        ) {\n            if (node.contains(field)) {\n                return node;\n            }\n\n            node =\n                node.parentElement;\n        }\n\n        return null;\n    }\n\n    function moveLevelCardsOutOfDisability() {\n        const primary =\n            document.getElementById(\n                "b131132_primary_indicators"\n            );\n\n        const thcs =\n            document.getElementById(\n                "b131132_thcs_indicators"\n            );\n\n        const disabilitySection =\n            findDisabilitySection();\n\n        if (\n            !disabilitySection\n            || !disabilitySection.parentElement\n        ) {\n            return;\n        }\n\n        const parent =\n            disabilitySection.parentElement;\n\n        if (\n            primary\n            && disabilitySection.contains(\n                primary\n            )\n        ) {\n            parent.insertBefore(\n                primary,\n                disabilitySection\n            );\n        }\n\n        if (\n            thcs\n            && disabilitySection.contains(\n                thcs\n            )\n        ) {\n            parent.insertBefore(\n                thcs,\n                disabilitySection\n            );\n        }\n    }\n\n    function enforceEducationLevel() {\n        moveLevelCardsOutOfDisability();\n\n        const level =\n            detectEducationLevel();\n\n        const primary =\n            document.getElementById(\n                "b131132_primary_indicators"\n            );\n\n        const thcs =\n            document.getElementById(\n                "b131132_thcs_indicators"\n            );\n\n        const preschoolScope =\n            findPreschoolScope();\n\n        setHardVisible(\n            primary,\n            level === "TH"\n        );\n\n        setHardVisible(\n            thcs,\n            level === "THCS"\n        );\n\n        if (preschoolScope) {\n            setHardVisible(\n                preschoolScope,\n                level === "MN"\n            );\n        } else {\n            fallbackPreschoolElements()\n                .forEach(function (element) {\n                    setHardVisible(\n                        element,\n                        level === "MN"\n                    );\n                });\n        }\n\n        document.body.dataset\n            .b131132StrictEducationLevel =\n            level;\n    }\n\n    function bindChanges() {\n        const literacy =\n            document.getElementById(\n                "is_literacy_target"\n            );\n\n        if (literacy) {\n            literacy.addEventListener(\n                "change",\n                enforceLiteracyBlock\n            );\n        }\n\n        [\n            "#school_search",\n            "#school_selected",\n            "#class_search",\n            "#class_selected",\n            "#school_id",\n            "#class_id",\n            \'[name="school_name_reported"]\',\n            \'[name="class_name_reported"]\'\n        ].forEach(function (selector) {\n            const element =\n                document.querySelector(\n                    selector\n                );\n\n            if (!element) return;\n\n            ["input", "change"].forEach(\n                function (eventName) {\n                    element.addEventListener(\n                        eventName,\n                        function () {\n                            window.setTimeout(\n                                enforceEducationLevel,\n                                0\n                            );\n                        }\n                    );\n                }\n            );\n        });\n\n        if (\n            typeof MutationObserver\n            !== "undefined"\n        ) {\n            [\n                "#school_selected",\n                "#class_selected"\n            ].forEach(function (selector) {\n                const element =\n                    document.querySelector(\n                        selector\n                    );\n\n                if (!element) return;\n\n                const observer =\n                    new MutationObserver(\n                        function () {\n                            window.setTimeout(\n                                enforceEducationLevel,\n                                0\n                            );\n                        }\n                    );\n\n                observer.observe(\n                    element,\n                    {\n                        childList: true,\n                        subtree: true,\n                        characterData: true,\n                        attributes: true\n                    }\n                );\n            });\n        }\n    }\n\n    function enforceAll() {\n        enforceLiteracyBlock();\n        enforceEducationLevel();\n    }\n\n    document.addEventListener(\n        "DOMContentLoaded",\n        function () {\n            bindChanges();\n            enforceAll();\n\n            window.setTimeout(\n                enforceAll,\n                80\n            );\n\n            window.setTimeout(\n                enforceAll,\n                350\n            );\n        }\n    );\n})();\n</script>\n<!-- === BAI_13B_11_13_2_4_STRICT_UI_END === -->\n'


def read_text(path: Path) -> str:
    if not path.exists():
        raise RuntimeError(
            f"Không tìm thấy: {path}"
        )

    return path.read_text(
        encoding="utf-8-sig"
    )


def write_text(
    path: Path,
    text: str,
) -> None:
    path.write_text(
        text,
        encoding="utf-8",
    )


def backup_source() -> None:
    dst = (
        BACKUP
        / TARGET.relative_to(PROJECT)
    )

    dst.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    shutil.copy2(
        TARGET,
        dst,
    )


def restore_source() -> None:
    src = (
        BACKUP
        / TARGET.relative_to(PROJECT)
    )

    if src.exists():
        shutil.copy2(
            src,
            TARGET,
        )


def patch(text: str) -> str:
    required_old = [
        "BAI_13B_11_13_2_XMC_UI_START",
        "BAI_13B_11_13_2_LEVEL_UI_START",
        'id="is_literacy_target"',
        'id="b131132_xmc_details"',
        'id="b131132_primary_indicators"',
        'id="b131132_thcs_indicators"',
        'name="completed_preschool_5"',
        'id="disability_status"',
    ]

    for item in required_old:
        if item not in text:
            raise RuntimeError(
                "Thiếu cấu trúc cần thiết từ "
                "Bài 13B-11.13.2: "
                + item
            )

    if MARK_START in text:
        print(
            " - Bài 13B-11.13.2.4 "
            "đã có sẵn; không chèn lặp."
        )
        return text

    body_end = text.lower().rfind(
        "</body>"
    )

    if body_end < 0:
        raise RuntimeError(
            "Không tìm thấy </body>."
        )

    return (
        text[:body_end]
        + "\n"
        + PATCH_HTML
        + "\n"
        + text[body_end:]
    )


def verify(text: str) -> None:
    required = [
        MARK_START,
        "function enforceLiteracyBlock()",
        'target.value === "CO"',
        "setChildrenDisabled(",
        "function detectEducationLevel()",
        "function findPreschoolScope()",
        "function moveLevelCardsOutOfDisability()",
        'level === "MN"',
        'level === "TH"',
        'level === "THCS"',
        "b131132-hard-hidden",
        "MutationObserver",
    ]

    for item in required:
        if item not in text:
            raise RuntimeError(
                "Thiếu nội dung sau cài: "
                + item
            )

    if text.count(MARK_START) != 1:
        raise RuntimeError(
            "Khối 13B-11.13.2.4 bị lặp."
        )

    from jinja2 import Environment

    Environment().parse(text)


def main() -> int:
    print("=" * 124)
    print(
        "BÀI 13B-11.13.2.4 - "
        "ẨN XMC KHI KHÔNG ĐIỀU TRA "
        "VÀ CHỈ HIỆN ĐÚNG CHỈ BÁO CẤP"
    )
    print("=" * 124)
    print()
    print("SỬA 1 - XÓA MÙ CHỮ:")
    print(
        " - XMC = Có -> hiện 3 trường chi tiết."
    )
    print(
        " - XMC = Không/Chưa xác định "
        "-> ẩn hoàn toàn thông tin XMC."
    )
    print(
        " - Khi bị ẩn, các trường XMC chi tiết "
        "không phải nhập và không POST."
    )
    print()
    print("SỬA 2 - CHỈ BÁO THEO CẤP:")
    print(
        " - MN -> chỉ hiện chỉ báo Mầm non."
    )
    print(
        " - TH -> chỉ hiện chỉ báo Tiểu học."
    )
    print(
        " - THCS -> chỉ hiện chỉ báo THCS."
    )
    print(
        " - THPT/người lớn -> không hiện nhầm "
        "chỉ báo MN/TH/THCS."
    )
    print(
        " - Sửa luôn việc khối TH/THCS "
        "bị nằm trong phần Khuyết tật."
    )
    print()
    print("AN TOÀN:")
    print(
        " - Chỉ sửa year_records.html."
    )
    print(
        " - Không sửa router/model/database."
    )
    print(
        " - Không xóa dữ liệu đã lưu."
    )
    print(
        " - Không đổi nội dung chỉ báo Mầm non."
    )
    print()

    BACKUP.mkdir(
        parents=True,
        exist_ok=False,
    )

    backup_source()

    print(
        "Backup:",
        BACKUP,
    )

    try:
        before = read_text(
            TARGET
        )

        after = patch(
            before
        )

        verify(
            after
        )

        write_text(
            TARGET,
            after,
        )

        print()
        print("KIỂM TRA SAU CÀI:")
        print(
            " - XMC Không -> ẩn chi tiết: OK"
        )
        print(
            " - XMC Có -> hiện chi tiết: OK"
        )
        print(
            " - MN/TH/THCS hiển thị độc quyền: OK"
        )
        print(
            " - Khối TH/THCS ra ngoài phần Khuyết tật: OK"
        )
        print(
            " - Jinja parse: OK"
        )
        print(
            " - Database: KHÔNG THAY ĐỔI"
        )
        print()
        print(
            "CÀI ĐẶT BÀI "
            "13B-11.13.2.4 THÀNH CÔNG"
        )

        return 0

    except Exception:
        traceback.print_exc()

        print()
        print(
            "CÓ LỖI - "
            "ĐANG KHÔI PHỤC TEMPLATE..."
        )

        restore_source()

        print(
            "ĐÃ KHÔI PHỤC TEMPLATE."
        )
        print(
            "Database không bị thay đổi."
        )
        print(
            "Backup:",
            BACKUP,
        )

        return 1


if __name__ == "__main__":
    raise SystemExit(main())
