from __future__ import annotations

import os
import re
import shutil
import traceback
from datetime import datetime
from pathlib import Path


PROJECT = Path(
    os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")
).resolve()

TEMPLATE = (
    PROJECT
    / "app"
    / "templates"
    / "surveys"
    / "year_records.html"
)

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = (
    PROJECT
    / "exports"
    / f"backup_bai_13b_11_14_3_4_{STAMP}"
)

START_MARKER = (
    "<!-- === "
    "BAI_13B_11_14_3_RESIDENCY_EVENTS_UI_START"
    " === -->"
)

END_MARKER = (
    "<!-- === "
    "BAI_13B_11_14_3_RESIDENCY_EVENTS_UI_END"
    " === -->"
)

NEW_SCRIPT = '\n<script>\n(function () {\n    function bindEventToggle(\n        checkboxId,\n        detailsId\n    ) {\n        const checkbox = document.getElementById(\n            checkboxId\n        );\n\n        const details = document.getElementById(\n            detailsId\n        );\n\n        if (!checkbox || !details) {\n            return;\n        }\n\n        function update() {\n            const active = checkbox.checked;\n\n            details.style.display = active ? "" : "none";\n\n            details\n                .querySelectorAll(\n                    "input, select, textarea"\n                )\n                .forEach(function (field) {\n                    field.disabled = !active;\n                });\n        }\n\n        checkbox.style.width = "auto";\n        checkbox.style.minWidth = "18px";\n        checkbox.style.height = "18px";\n        checkbox.style.margin = "0";\n\n        checkbox.addEventListener(\n            "change",\n            update\n        );\n\n        update();\n    }\n\n    bindEventToggle(\n        "move_in_active",\n        "move_in_details"\n    );\n\n    bindEventToggle(\n        "move_out_active",\n        "move_out_details"\n    );\n\n    bindEventToggle(\n        "death_active",\n        "death_details"\n    );\n})();\n</script>\n'


def read_text(path: Path) -> str:
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


def patch_template(
    source: str,
) -> str:
    start = source.find(
        START_MARKER
    )

    end = source.find(
        END_MARKER,
        start,
    )

    if start < 0 or end < 0:
        raise RuntimeError(
            "Không tìm thấy block Cư trú và biến động "
            "của Bài 14.3."
        )

    block = source[
        start:
        end + len(END_MARKER)
    ]

    script_pattern = re.compile(
        r"<script>\s*"
        r"\(function\s*\(\)\s*\{.*?"
        r"bindEventToggle\(\s*"
        r'"death_active"\s*,\s*'
        r'"death_details"\s*'
        r"\)\s*;.*?"
        r"\}\)\(\)\s*;\s*"
        r"</script>",
        flags=re.DOTALL,
    )

    matches = list(
        script_pattern.finditer(
            block
        )
    )

    if len(matches) != 1:
        raise RuntimeError(
            "Phải tìm thấy đúng 1 script ẩn/hiện "
            f"trong block Cư trú và biến động; "
            f"hiện có {len(matches)}."
        )

    match = matches[0]

    patched_block = (
        block[:match.start()]
        + NEW_SCRIPT.strip()
        + block[match.end():]
    )

    return (
        source[:start]
        + patched_block
        + source[
            end + len(END_MARKER):
        ]
    )


def verify(
    source: str,
) -> None:
    required = (
        'details.style.display = active ? "" : "none";',
        "field.disabled = !active;",
        '"move_in_active"',
        '"move_out_active"',
        '"death_active"',
        START_MARKER,
        END_MARKER,
    )

    for item in required:
        if item not in source:
            raise RuntimeError(
                "Template sau sửa thiếu: "
                + item
            )

    from jinja2 import Environment

    Environment().parse(
        source
    )


def main() -> int:
    print("=" * 116)
    print(
        "BÀI 13B-11.14.3.4 - "
        "SỬA ẨN/HIỆN CHUYỂN ĐẾN - CHUYỂN ĐI - TỬ VONG"
    )
    print("=" * 116)
    print()
    print("SỬA:")
    print(
        " - Chưa tích Chuyển đến -> "
        "ẩn Ngày chuyển đến + Nơi đi."
    )
    print(
        " - Chưa tích Chuyển đi -> "
        "ẩn Ngày chuyển đi + Nơi đến."
    )
    print(
        " - Chưa tích Tử vong -> "
        "ẩn Ngày tử vong."
    )
    print(
        " - Khi ẩn, các input con được disable "
        "để không submit nhầm."
    )
    print(
        " - Chỉnh checkbox gọn lại."
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
        " - Có backup và rollback nếu lỗi."
    )
    print()

    original = read_text(
        TEMPLATE
    )

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
        patched = patch_template(
            original
        )

        verify(
            patched
        )

        write_text(
            TEMPLATE,
            patched,
        )

        verify(
            read_text(
                TEMPLATE
            )
        )

        print()
        print("KIỂM TRA SAU CÀI:")
        print(
            " - Chuyển đến ẩn/hiện bằng style.display: OK"
        )
        print(
            " - Chuyển đi ẩn/hiện bằng style.display: OK"
        )
        print(
            " - Tử vong ẩn/hiện bằng style.display: OK"
        )
        print(
            " - Input ẩn được disable: OK"
        )
        print(
            " - Jinja parse: OK"
        )
        print(
            " - Database: KHÔNG THAY ĐỔI"
        )
        print()
        print("=" * 116)
        print(
            "CÀI ĐẶT BÀI 13B-11.14.3.4 THÀNH CÔNG"
        )
        print("=" * 116)

        return 0

    except Exception:
        traceback.print_exc()

        print()
        print(
            "CÓ LỖI - ĐANG KHÔI PHỤC TEMPLATE..."
        )

        try:
            shutil.copy2(
                backup_template,
                TEMPLATE,
            )
            print(
                " - Đã khôi phục year_records.html."
            )
        except Exception as exc:
            print(
                " - Lỗi khôi phục template:",
                exc,
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
