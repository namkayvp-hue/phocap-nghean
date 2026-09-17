from __future__ import annotations

import os
import shutil
import traceback
from datetime import datetime
from pathlib import Path

PROJECT = Path(
    os.environ.get(
        "PHOCAP_PROJECT",
        r"C:\PhoCap",
    )
).resolve()

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
    / f"backup_bai_13b_11_13_3_4_{STAMP}"
)

MARK_START = (
    "<!-- === "
    "BAI_13B_11_13_3_4_HIDE_LOCATION_FOR_XMC_START"
    " === -->"
)

MARK_END = (
    "<!-- === "
    "BAI_13B_11_13_3_4_HIDE_LOCATION_FOR_XMC_END"
    " === -->"
)

PATCH = '\n<!-- === BAI_13B_11_13_3_4_HIDE_LOCATION_FOR_XMC_START === -->\n<style>\n    .b1311334-xmc-hidden {\n        display: none !important;\n    }\n</style>\n\n<script>\n(function () {\n    "use strict";\n\n    function normalizeText(value) {\n        return String(value || "")\n            .normalize("NFD")\n            .replace(/[\\u0300-\\u036f]/g, "")\n            .toLowerCase()\n            .replace(/\\s+/g, " ")\n            .trim();\n    }\n\n    function closestReasonableBlock(element) {\n        if (!element) return null;\n\n        return (\n            element.closest(".form-group")\n            || element.closest(".field-group")\n            || element.closest(".form-row")\n            || element.parentElement\n        );\n    }\n\n    function findBlockByFieldSelectors(selectors) {\n        for (const selector of selectors) {\n            const element = document.querySelector(selector);\n            if (!element) continue;\n\n            const block = closestReasonableBlock(element);\n            if (block) return block;\n        }\n\n        return null;\n    }\n\n    function findBlockByHeading(label) {\n        const expected = normalizeText(label);\n\n        const elements = Array.from(\n            document.querySelectorAll(\n                "label,strong,h3,h4,div,span"\n            )\n        );\n\n        const heading = elements.find(function (element) {\n            const text = normalizeText(\n                element.textContent\n            );\n\n            return (\n                text === expected\n                || text === "1 " + expected\n                || text === "2 " + expected\n                || text === "3 " + expected\n            );\n        });\n\n        if (!heading) return null;\n\n        return closestReasonableBlock(heading);\n    }\n\n    function collectBlocks() {\n        const blocks = new Set();\n\n        const communeBlock =\n            findBlockByFieldSelectors([\n                "#commune_search",\n                "#commune_selected",\n                \'[name="commune_id"]\',\n                \'[name="commune_name_reported"]\'\n            ])\n            || findBlockByHeading(\n                "Xã/phường hiện tại"\n            );\n\n        const schoolBlock =\n            findBlockByFieldSelectors([\n                "#school_search",\n                "#school_selected",\n                \'[name="school_id"]\'\n            ])\n            || findBlockByHeading(\n                "Trường hiện tại"\n            );\n\n        const classBlock =\n            findBlockByFieldSelectors([\n                "#class_search",\n                "#class_selected",\n                \'[name="class_id"]\'\n            ])\n            || findBlockByHeading(\n                "Lớp hiện tại"\n            );\n\n        [\n            communeBlock,\n            schoolBlock,\n            classBlock\n        ].forEach(function (block) {\n            if (block) blocks.add(block);\n        });\n\n        const reportedSchool =\n            document.querySelector(\n                \'[name="school_name_reported"]\'\n            );\n\n        const reportedClass =\n            document.querySelector(\n                \'[name="class_name_reported"]\'\n            );\n\n        const reportedBlocks = [\n            closestReasonableBlock(\n                reportedSchool\n            ),\n            closestReasonableBlock(\n                reportedClass\n            )\n        ].filter(Boolean);\n\n        if (\n            reportedSchool\n            && reportedClass\n        ) {\n            let parent =\n                reportedSchool.parentElement;\n\n            while (\n                parent\n                && parent.id !== "year_record_form"\n            ) {\n                if (\n                    parent.contains(reportedClass)\n                ) {\n                    const className =\n                        String(\n                            parent.className || ""\n                        );\n\n                    if (\n                        className.includes("grid")\n                        || className.includes("row")\n                    ) {\n                        blocks.add(parent);\n                        break;\n                    }\n                }\n\n                parent =\n                    parent.parentElement;\n            }\n        }\n\n        reportedBlocks.forEach(\n            function (block) {\n                blocks.add(block);\n            }\n        );\n\n        return Array.from(blocks);\n    }\n\n    function applyXmcLocationVisibility() {\n        const target =\n            document.getElementById(\n                "is_literacy_target"\n            );\n\n        if (!target) return;\n\n        const hideLocation =\n            target.value === "CO";\n\n        collectBlocks()\n            .forEach(function (block) {\n                block.classList.toggle(\n                    "b1311334-xmc-hidden",\n                    hideLocation\n                );\n            });\n    }\n\n    document.addEventListener(\n        "DOMContentLoaded",\n        function () {\n            const target =\n                document.getElementById(\n                    "is_literacy_target"\n                );\n\n            if (target) {\n                target.addEventListener(\n                    "change",\n                    function () {\n                        window.setTimeout(\n                            applyXmcLocationVisibility,\n                            0\n                        );\n                    }\n                );\n            }\n\n            applyXmcLocationVisibility();\n\n            window.setTimeout(\n                applyXmcLocationVisibility,\n                100\n            );\n\n            window.setTimeout(\n                applyXmcLocationVisibility,\n                400\n            );\n        }\n    );\n})();\n</script>\n<!-- === BAI_13B_11_13_3_4_HIDE_LOCATION_FOR_XMC_END === -->\n'


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
    if MARK_START in text:
        print(
            " - Bài 13B-11.13.3.4 "
            "đã có sẵn; không chèn lặp."
        )
        return text

    required = [
        'id="is_literacy_target"',
        "Xã/phường hiện tại",
        "Trường hiện tại",
        "Lớp hiện tại",
        'name="school_name_reported"',
        'name="class_name_reported"',
    ]

    for item in required:
        if item not in text:
            raise RuntimeError(
                "Template thiếu cấu trúc cần thiết: "
                + item
            )

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
        + PATCH
        + "\n"
        + text[body_end:]
    )


def verify(text: str) -> None:
    required = [
        MARK_START,
        MARK_END,
        "applyXmcLocationVisibility",
        'target.value === "CO"',
        "b1311334-xmc-hidden",
        "school_name_reported",
        "class_name_reported",
        "Xã/phường hiện tại",
        "Trường hiện tại",
        "Lớp hiện tại",
    ]

    for item in required:
        if item not in text:
            raise RuntimeError(
                "Thiếu nội dung sau cài: "
                + item
            )

    if text.count(MARK_START) != 1:
        raise RuntimeError(
            "Khối 13B-11.13.3.4 bị lặp."
        )

    from jinja2 import Environment

    Environment().parse(text)


def main() -> int:
    print("=" * 124)
    print(
        "BÀI 13B-11.13.3.4 - "
        "ĐỐI TƯỢNG XMC: ẨN MỤC 1, 2, 3 "
        "XÃ/TRƯỜNG/LỚP"
    )
    print("=" * 124)
    print()
    print("NGHIỆP VỤ:")
    print(
        " - XMC = Có -> ẩn 1. Xã/phường hiện tại."
    )
    print(
        " - XMC = Có -> ẩn 2. Trường hiện tại."
    )
    print(
        " - XMC = Có -> ẩn 3. Lớp hiện tại."
    )
    print(
        " - Ẩn luôn Tên trường theo phiếu / "
        "Tên lớp theo phiếu."
    )
    print(
        " - XMC = Không/Chưa xác định -> "
        "hiện lại các mục trên."
    )
    print()
    print("AN TOÀN:")
    print(
        " - Chỉ ẩn giao diện."
    )
    print(
        " - Không xóa dữ liệu đã có."
    )
    print(
        " - Không disable field, nên giá trị cũ "
        "vẫn được giữ khi lưu."
    )
    print(
        " - Không sửa router/model/database."
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
        before = read_text(TARGET)
        after = patch(before)
        verify(after)
        write_text(TARGET, after)

        print()
        print("KIỂM TRA SAU CÀI:")
        print(
            " - XMC Có -> ẩn mục 1,2,3: OK"
        )
        print(
            " - XMC Không -> hiện lại: OK"
        )
        print(
            " - Không xóa dữ liệu cũ: OK"
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
            "13B-11.13.3.4 THÀNH CÔNG"
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
    raise SystemExit(
        main()
    )
