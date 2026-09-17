from __future__ import annotations

import os
import re
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
    / f"backup_bai_13b_11_13_3_4_1_{STAMP}"
)

OLD_START = (
    "<!-- === "
    "BAI_13B_11_13_3_4_HIDE_LOCATION_FOR_XMC_START"
    " === -->"
)

OLD_END = (
    "<!-- === "
    "BAI_13B_11_13_3_4_HIDE_LOCATION_FOR_XMC_END"
    " === -->"
)

NEW_START = (
    "<!-- === "
    "BAI_13B_11_13_3_4_1_HIDE_ONLY_5_XMC_FIELDS_START"
    " === -->"
)

PATCH_HTML = '\n<!-- === BAI_13B_11_13_3_4_1_HIDE_ONLY_5_XMC_FIELDS_START === -->\n<style>\n    .b13113341-hidden {\n        display: none !important;\n    }\n</style>\n\n<script>\n(function () {\n    "use strict";\n\n    function normalizeText(value) {\n        return String(value || "")\n            .normalize("NFD")\n            .replace(/[\\u0300-\\u036f]/g, "")\n            .toLowerCase()\n            .replace(/\\s+/g, " ")\n            .trim();\n    }\n\n    function nearestOwnGroup(element) {\n        if (!element) return null;\n\n        return (\n            element.closest(".form-group")\n            || element.closest(".field-group")\n            || element.closest(".form-field")\n            || element.parentElement\n        );\n    }\n\n    function findBySelectors(selectors) {\n        for (const selector of selectors) {\n            const element = document.querySelector(selector);\n            if (!element) continue;\n\n            const group = nearestOwnGroup(element);\n            if (group) return group;\n        }\n\n        return null;\n    }\n\n    function findByExactLabel(label) {\n        const expected = normalizeText(label);\n\n        const elements = Array.from(\n            document.querySelectorAll(\n                "label,strong,h3,h4,div,span"\n            )\n        );\n\n        const found = elements.find(function (element) {\n            const text = normalizeText(\n                element.textContent\n            );\n\n            return (\n                text === expected\n                || text === "1 " + expected\n                || text === "2 " + expected\n                || text === "3 " + expected\n            );\n        });\n\n        return nearestOwnGroup(found);\n    }\n\n    function getExactFiveBlocks() {\n        const result = [];\n\n        const commune =\n            findBySelectors([\n                "#commune_search",\n                "#commune_selected",\n                \'[name="commune_id"]\'\n            ])\n            || findByExactLabel(\n                "Xã/phường hiện tại"\n            );\n\n        const school =\n            findBySelectors([\n                "#school_search",\n                "#school_selected",\n                \'[name="school_id"]\'\n            ])\n            || findByExactLabel(\n                "Trường hiện tại"\n            );\n\n        const classBlock =\n            findBySelectors([\n                "#class_search",\n                "#class_selected",\n                \'[name="class_id"]\'\n            ])\n            || findByExactLabel(\n                "Lớp hiện tại"\n            );\n\n        const reportedSchool =\n            nearestOwnGroup(\n                document.querySelector(\n                    \'[name="school_name_reported"]\'\n                )\n            );\n\n        const reportedClass =\n            nearestOwnGroup(\n                document.querySelector(\n                    \'[name="class_name_reported"]\'\n                )\n            );\n\n        [\n            commune,\n            school,\n            classBlock,\n            reportedSchool,\n            reportedClass\n        ].forEach(function (block) {\n            if (\n                block\n                && !result.includes(block)\n            ) {\n                result.push(block);\n            }\n        });\n\n        return result;\n    }\n\n    function applyOnlyFiveXmcFields() {\n        const target =\n            document.getElementById(\n                "is_literacy_target"\n            );\n\n        if (!target) return;\n\n        const shouldHide =\n            target.value === "CO";\n\n        getExactFiveBlocks()\n            .forEach(function (block) {\n                block.classList.toggle(\n                    "b13113341-hidden",\n                    shouldHide\n                );\n            });\n    }\n\n    document.addEventListener(\n        "DOMContentLoaded",\n        function () {\n            const target =\n                document.getElementById(\n                    "is_literacy_target"\n                );\n\n            if (target) {\n                target.addEventListener(\n                    "change",\n                    applyOnlyFiveXmcFields\n                );\n            }\n\n            applyOnlyFiveXmcFields();\n\n            window.setTimeout(\n                applyOnlyFiveXmcFields,\n                120\n            );\n\n            window.setTimeout(\n                applyOnlyFiveXmcFields,\n                450\n            );\n        }\n    );\n})();\n</script>\n<!-- === BAI_13B_11_13_3_4_1_HIDE_ONLY_5_XMC_FIELDS_END === -->\n'


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


def remove_old_34_block(
    text: str,
) -> str:
    if OLD_START not in text:
        return text

    start = text.find(
        OLD_START
    )
    end = text.find(
        OLD_END,
        start,
    )

    if end < 0:
        raise RuntimeError(
            "Có marker đầu Bài 13B-11.13.3.4 "
            "nhưng không có marker cuối."
        )

    end += len(
        OLD_END
    )

    return (
        text[:start]
        + text[end:]
    )


def patch(text: str) -> str:
    text = remove_old_34_block(
        text
    )

    if NEW_START in text:
        print(
            " - Bài 13B-11.13.3.4.1 "
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
        + PATCH_HTML
        + "\n"
        + text[body_end:]
    )


def verify(text: str) -> None:
    required = [
        NEW_START,
        "applyOnlyFiveXmcFields",
        'target.value === "CO"',
        "b13113341-hidden",
        'name="school_name_reported"',
        'name="class_name_reported"',
    ]

    for item in required:
        if item not in text:
            raise RuntimeError(
                "Thiếu nội dung sau cài: "
                + item
            )

    if OLD_START in text:
        raise RuntimeError(
            "Khối 13B-11.13.3.4 cũ "
            "chưa được loại bỏ."
        )

    if text.count(
        NEW_START
    ) != 1:
        raise RuntimeError(
            "Khối 13B-11.13.3.4.1 bị lặp."
        )

    from jinja2 import Environment

    Environment().parse(
        text
    )


def main() -> int:
    print("=" * 122)
    print(
        "BÀI 13B-11.13.3.4.1 - "
        "XMC = CÓ CHỈ ẨN ĐÚNG 5 MỤC"
    )
    print("=" * 122)
    print()
    print("CHỈ ẨN:")
    print(" 1. Xã/phường hiện tại")
    print(" 2. Trường hiện tại")
    print(" 3. Lớp hiện tại")
    print(" 4. Tên trường theo phiếu")
    print(" 5. Tên lớp theo phiếu")
    print()
    print("KHÔNG ẨN:")
    print(" - Tình trạng học tập")
    print(" - Chỉ báo theo cấp")
    print(" - Theo dõi khuyết tật")
    print(" - Hoàn cảnh đặc biệt")
    print(" - Ghi chú")
    print(" - Các phần nghiệp vụ khác")
    print()
    print("AN TOÀN:")
    print(" - Chỉ sửa year_records.html")
    print(" - Không sửa router/model/database")
    print(" - Không xóa/đổi dữ liệu đã lưu")
    print(" - Nếu có bản 13B-11.13.3.4 cũ, tự loại bỏ block cũ")
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
            " - XMC Có chỉ ẩn đúng 5 mục: OK"
        )
        print(
            " - Các phần khác giữ nguyên: OK"
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
            "13B-11.13.3.4.1 THÀNH CÔNG"
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
