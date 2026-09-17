from __future__ import annotations

import os
import shutil
import traceback
from datetime import datetime
from pathlib import Path

PROJECT = Path(
    os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")
).resolve()

APP = PROJECT / "app"
TEMPLATE = APP / "templates" / "surveys" / "province_batch_admin_v13b11.html"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = (
    PROJECT
    / "exports"
    / f"backup_source_bai_13b_11_1_{STAMP}"
)

MARK_TOOLBAR = "BAI_13B_11_1_SELECT_ALL_TOOLBAR"
MARK_SCRIPT = "BAI_13B_11_1_SELECT_ALL_SCRIPT"

TOOLBAR = '\n            {# === BAI_13B_11_1_SELECT_ALL_TOOLBAR_START === #}\n            <div\n                class="b1311-actions"\n                style="\n                    margin: 0 0 14px;\n                    padding: 12px 14px;\n                    border: 1px solid #d9e6f1;\n                    border-radius: 10px;\n                    background: #f8fbfe;\n                "\n            >\n                <button\n                    id="b1311-select-all-toggle"\n                    class="button button-secondary"\n                    type="button"\n                >\n                    ☑ Chọn toàn bộ\n                </button>\n\n                <span\n                    id="b1311-select-all-status"\n                    style="color:#5e7184;font-size:13px;"\n                >\n                    Chỉ chọn các đợt đang đủ điều kiện xóa.\n                </span>\n            </div>\n            {# === BAI_13B_11_1_SELECT_ALL_TOOLBAR_END === #}\n'
SCRIPT = '\n    {# === BAI_13B_11_1_SELECT_ALL_SCRIPT_START === #}\n    <script>\n    (function () {\n        const button = document.getElementById("b1311-select-all-toggle");\n        const status = document.getElementById("b1311-select-all-status");\n\n        if (!button) {\n            return;\n        }\n\n        function eligibleBoxes() {\n            return Array.from(\n                document.querySelectorAll(\n                    \'.b1311-delete-form input[name="confirm_checked"]\'\n                )\n            ).filter(function (box) {\n                return !box.disabled;\n            });\n        }\n\n        function refresh() {\n            const boxes = eligibleBoxes();\n            const checked = boxes.filter(function (box) {\n                return box.checked;\n            }).length;\n\n            const allChecked =\n                boxes.length > 0 &&\n                checked === boxes.length;\n\n            button.textContent = allChecked\n                ? "☐ Bỏ chọn toàn bộ"\n                : "☑ Chọn toàn bộ";\n\n            if (status) {\n                status.textContent =\n                    "Đã chọn " + checked + "/" + boxes.length +\n                    " đợt đủ điều kiện xóa.";\n            }\n        }\n\n        button.addEventListener("click", function () {\n            const boxes = eligibleBoxes();\n\n            if (!boxes.length) {\n                refresh();\n                return;\n            }\n\n            const allChecked = boxes.every(function (box) {\n                return box.checked;\n            });\n\n            boxes.forEach(function (box) {\n                box.checked = !allChecked;\n                box.dispatchEvent(\n                    new Event("change", { bubbles: true })\n                );\n            });\n\n            refresh();\n        });\n\n        document.addEventListener("change", function (event) {\n            if (\n                event.target &&\n                event.target.matches &&\n                event.target.matches(\n                    \'.b1311-delete-form input[name="confirm_checked"]\'\n                )\n            ) {\n                refresh();\n            }\n        });\n\n        refresh();\n    })();\n    </script>\n    {# === BAI_13B_11_1_SELECT_ALL_SCRIPT_END === #}\n'


def read_text(path: Path) -> str:
    if not path.exists():
        raise RuntimeError(f"Không tìm thấy tệp bắt buộc: {path}")
    return path.read_text(encoding="utf-8-sig")


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def backup() -> None:
    target = BACKUP / TEMPLATE.relative_to(PROJECT)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(TEMPLATE, target)


def restore() -> None:
    source = BACKUP / TEMPLATE.relative_to(PROJECT)
    if source.exists():
        TEMPLATE.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, TEMPLATE)


def clear_cache() -> None:
    for cache in APP.rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(cache, ignore_errors=True)


def patch(text: str) -> str:
    required = [
        "BÀI 13B-11",
        "3. Xóa đợt tạo nhầm",
        "b1311-delete-form",
        'name="confirm_checked"',
        "Xóa đợt trống",
    ]

    for marker in required:
        if marker not in text:
            raise RuntimeError(
                "Template chưa đúng nền Bài 13B-11. "
                f"Thiếu marker: {marker}"
            )

    if MARK_TOOLBAR not in text:
        heading = "<h2>3. Xóa đợt tạo nhầm — kiểm soát nghiêm ngặt</h2>"
        if heading not in text:
            raise RuntimeError(
                "Không tìm thấy tiêu đề mục 3 để chèn nút Chọn toàn bộ."
            )
        text = text.replace(
            heading,
            heading + "\n\n" + TOOLBAR.rstrip(),
            1,
        )

    if MARK_SCRIPT not in text:
        if "</body>" not in text:
            raise RuntimeError(
                "Không tìm thấy </body> để chèn JavaScript an toàn."
            )
        text = text.replace(
            "</body>",
            SCRIPT.rstrip() + "\n</body>",
            1,
        )

    return text


def verify() -> None:
    text = read_text(TEMPLATE)

    for marker in (
        MARK_TOOLBAR,
        MARK_SCRIPT,
        'id="b1311-select-all-toggle"',
        "☑ Chọn toàn bộ",
        "☐ Bỏ chọn toàn bộ",
        'input[name="confirm_checked"]',
        "Xóa đợt trống",
    ):
        if marker not in text:
            raise RuntimeError(
                f"Kiểm tra sau cài không đạt: thiếu {marker}"
            )

    from jinja2 import Environment, FileSystemLoader

    env = Environment(
        loader=FileSystemLoader(str(APP / "templates"))
    )
    env.get_template("surveys/province_batch_admin_v13b11.html")


def main() -> int:
    print("=" * 92)
    print("BÀI 13B-11.1 - THÊM NÚT CHỌN TOÀN BỘ ĐỢT ĐỦ ĐIỀU KIỆN XÓA")
    print("=" * 92)
    print()
    print("BỔ SUNG:")
    print(" - Nút ☑ Chọn toàn bộ.")
    print(" - Bấm lại -> ☐ Bỏ chọn toàn bộ.")
    print(" - Hiển thị số đợt đã chọn / tổng đợt đủ điều kiện.")
    print()
    print("GIỮ NGUYÊN AN TOÀN:")
    print(" - Không tự xóa đợt.")
    print(" - Không tự điền câu XOA DOT <MÃ ĐỢT>.")
    print(" - Không sửa router.")
    print(" - Không sửa database.")
    print(" - Không thay cơ chế backup trước DELETE.")
    print()

    if not TEMPLATE.exists():
        raise RuntimeError(f"Không tìm thấy: {TEMPLATE}")

    BACKUP.mkdir(parents=True, exist_ok=False)
    backup()
    print("Backup source:", BACKUP)

    try:
        before = read_text(TEMPLATE)
        after = patch(before)
        write_text(TEMPLATE, after)

        verify()
        clear_cache()

        print()
        print("KIỂM TRA:")
        print(" - Jinja template: OK")
        print(" - Nút Chọn toàn bộ: OK")
        print(" - Nút Bỏ chọn toàn bộ: OK")
        print(" - Không sửa database: OK")
        print()
        print("CÀI ĐẶT BÀI 13B-11.1 THÀNH CÔNG")
        return 0

    except Exception:
        traceback.print_exc()
        print()
        print("CÓ LỖI - ĐANG KHÔI PHỤC TEMPLATE...")
        restore()
        clear_cache()
        print("ĐÃ KHÔI PHỤC SOURCE.")
        print("Database không bị thay đổi.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
