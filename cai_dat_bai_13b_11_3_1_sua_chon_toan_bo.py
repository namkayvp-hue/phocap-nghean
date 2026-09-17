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
TEMPLATE = (
    APP
    / "templates"
    / "surveys"
    / "province_batch_admin_v13b11.html"
)

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = (
    PROJECT
    / "exports"
    / f"backup_source_bai_13b_11_3_1_{STAMP}"
)

START = "{# === BAI_13B_11_1_SELECT_ALL_TOOLBAR_START === #}"
END = "{# === BAI_13B_11_1_SELECT_ALL_TOOLBAR_END === #}"
FIX_MARK = "BAI_13B_11_3_1_SELECT_ALL_FIX_START"

NEW_TOOLBAR = '\n            {# === BAI_13B_11_1_SELECT_ALL_TOOLBAR_START === #}\n            <div\n                class="b1311-actions"\n                style="\n                    margin: 0 0 14px;\n                    padding: 12px 14px;\n                    border: 1px solid #d9e6f1;\n                    border-radius: 10px;\n                    background: #f8fbfe;\n                "\n            >\n                <label\n                    for="b1311-select-all-checkbox"\n                    style="\n                        display:inline-flex;\n                        align-items:center;\n                        gap:8px;\n                        font-weight:700;\n                        cursor:pointer;\n                        user-select:none;\n                    "\n                >\n                    <input\n                        id="b1311-select-all-checkbox"\n                        type="checkbox"\n                        style="width:18px;height:18px;cursor:pointer;"\n                    >\n                    <span>Chọn toàn bộ đợt đủ điều kiện</span>\n                </label>\n\n                <span\n                    id="b1311-select-all-status"\n                    style="color:#5e7184;font-size:13px;"\n                >\n                    Đã chọn 0/0 đợt đủ điều kiện xóa.\n                </span>\n            </div>\n            {# === BAI_13B_11_1_SELECT_ALL_TOOLBAR_END === #}\n'
FIX_SCRIPT = '\n    {# === BAI_13B_11_3_1_SELECT_ALL_FIX_START === #}\n    <script>\n    (function () {\n        function initSelectAllFix() {\n            const master =\n                document.getElementById("b1311-select-all-checkbox");\n            const status =\n                document.getElementById("b1311-select-all-status");\n            const bulkButton =\n                document.getElementById("b1311-bulk-delete-button");\n            const bulkHelp =\n                document.getElementById("b1311-bulk-delete-help");\n\n            if (!master) {\n                return;\n            }\n\n            function boxes() {\n                return Array.from(\n                    document.querySelectorAll(\n                        \'.b1311-delete-form \' +\n                        \'input[name="confirm_checked"]\'\n                    )\n                ).filter(function (box) {\n                    return !box.disabled;\n                });\n            }\n\n            function checkedBoxes() {\n                return boxes().filter(function (box) {\n                    return box.checked;\n                });\n            }\n\n            function refresh() {\n                const all = boxes();\n                const checked = checkedBoxes();\n                const total = all.length;\n                const selected = checked.length;\n\n                master.checked =\n                    total > 0 && selected === total;\n                master.indeterminate =\n                    selected > 0 && selected < total;\n\n                if (status) {\n                    status.textContent =\n                        "Đã chọn " + selected + "/" + total +\n                        " đợt đủ điều kiện xóa.";\n                }\n\n                if (bulkButton) {\n                    bulkButton.disabled = selected === 0;\n                    bulkButton.textContent =\n                        selected > 0\n                            ? (\n                                "🗑 Xóa toàn bộ đã chọn (" +\n                                selected +\n                                ")"\n                            )\n                            : "🗑 Xóa toàn bộ đã chọn";\n                }\n\n                if (bulkHelp) {\n                    bulkHelp.textContent =\n                        selected > 0\n                            ? (\n                                "Đã chọn " + selected +\n                                " đợt. Hệ thống sẽ tạo 1 backup chung, " +\n                                "kiểm tra lại toàn bộ và chỉ xóa nếu " +\n                                "tất cả đều an toàn."\n                            )\n                            : (\n                                "Chưa chọn đợt nào. Hệ thống chỉ xóa " +\n                                "khi toàn bộ đợt được chọn đều vượt qua " +\n                                "kiểm tra an toàn."\n                            );\n                }\n            }\n\n            master.addEventListener("change", function () {\n                const targetState = master.checked;\n\n                boxes().forEach(function (box) {\n                    box.checked = targetState;\n                    box.dispatchEvent(\n                        new Event("change", { bubbles: true })\n                    );\n                });\n\n                refresh();\n            });\n\n            document.addEventListener(\n                "change",\n                function (event) {\n                    if (\n                        event.target &&\n                        event.target.matches &&\n                        event.target.matches(\n                            \'.b1311-delete-form \' +\n                            \'input[name="confirm_checked"]\'\n                        )\n                    ) {\n                        refresh();\n                    }\n                }\n            );\n\n            refresh();\n        }\n\n        if (document.readyState === "loading") {\n            document.addEventListener(\n                "DOMContentLoaded",\n                initSelectAllFix\n            );\n        } else {\n            initSelectAllFix();\n        }\n    })();\n    </script>\n    {# === BAI_13B_11_3_1_SELECT_ALL_FIX_END === #}\n'


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


def replace_block(text: str) -> str:
    if START not in text or END not in text:
        raise RuntimeError(
            "Không tìm thấy khối Chọn toàn bộ của Bài 13B-11.1."
        )

    start_pos = text.find(START)
    end_pos = text.find(END, start_pos)

    if start_pos < 0 or end_pos < 0:
        raise RuntimeError(
            "Không xác định được phạm vi khối Chọn toàn bộ."
        )

    end_pos += len(END)

    return (
        text[:start_pos]
        + NEW_TOOLBAR.strip()
        + text[end_pos:]
    )


def patch(text: str) -> str:
    required = [
        "BÀI 13B-11",
        "b1311-delete-form",
        'name="confirm_checked"',
        "b1311-bulk-delete-form",
        "b1311-bulk-delete-button",
        "Xóa toàn bộ đã chọn",
    ]

    for marker in required:
        if marker not in text:
            raise RuntimeError(
                "Template chưa đúng nền Bài 13B-11.3. "
                f"Thiếu: {marker}"
            )

    text = replace_block(text)

    if FIX_MARK not in text:
        if "</body>" not in text:
            raise RuntimeError(
                "Không tìm thấy </body> để chèn script sửa lỗi."
            )
        text = text.replace(
            "</body>",
            FIX_SCRIPT.rstrip() + "\n</body>",
            1,
        )

    return text


def verify() -> None:
    text = read_text(TEMPLATE)

    required = [
        'id="b1311-select-all-checkbox"',
        "Chọn toàn bộ đợt đủ điều kiện",
        'id="b1311-select-all-status"',
        FIX_MARK,
        "master.indeterminate",
        "bulkButton.disabled = selected === 0",
        "Xóa toàn bộ đã chọn",
        "b1311-bulk-delete-form",
    ]

    for marker in required:
        if marker not in text:
            raise RuntimeError(
                f"Kiểm tra sau cài không đạt: thiếu {marker}"
            )

    if 'id="b1311-select-all-toggle"' in text:
        raise RuntimeError(
            "Nút Chọn toàn bộ cũ vẫn còn; chưa thay thành checkbox thật."
        )

    from jinja2 import Environment, FileSystemLoader

    env = Environment(
        loader=FileSystemLoader(str(APP / "templates"))
    )
    env.get_template(
        "surveys/province_batch_admin_v13b11.html"
    )


def main() -> int:
    print("=" * 100)
    print(
        "BÀI 13B-11.3.1 - SỬA CHỌN TOÀN BỘ 0/130"
    )
    print("=" * 100)
    print()
    print("NGUYÊN NHÂN GIAO DIỆN:")
    print(
        " - Dòng ☑ Chọn toàn bộ trước đây là chữ trên nút, "
        "không phải checkbox trạng thái."
    )
    print()
    print("BẢN SỬA:")
    print(" - Thay bằng checkbox thật: Chọn toàn bộ đợt đủ điều kiện.")
    print(" - Tick một lần -> tick toàn bộ các dòng.")
    print(" - Bộ đếm đổi ngay 0/N -> N/N.")
    print(" - Nút Xóa toàn bộ đã chọn tự hiện đúng số lượng.")
    print(" - Bỏ tick -> bỏ chọn toàn bộ.")
    print(" - Tick/bỏ từng dòng -> checkbox tổng có trạng thái trung gian.")
    print()
    print("KHÔNG THAY ĐỔI:")
    print(" - Database.")
    print(" - Router/backend xóa hàng loạt.")
    print(" - Backup trước DELETE.")
    print(" - Kiểm tra an toàn 2 lần.")
    print()

    if not TEMPLATE.exists():
        raise RuntimeError(f"Không tìm thấy: {TEMPLATE}")

    BACKUP.mkdir(parents=True, exist_ok=False)
    backup()
    print("Backup source:", BACKUP)

    try:
        write_text(
            TEMPLATE,
            patch(read_text(TEMPLATE)),
        )

        verify()
        clear_cache()

        print()
        print("KIỂM TRA:")
        print(" - Jinja template: OK")
        print(" - Checkbox Chọn toàn bộ thật: OK")
        print(" - Đồng bộ bộ đếm: OK")
        print(" - Đồng bộ nút xóa hàng loạt: OK")
        print(" - Database: KHÔNG THAY ĐỔI")
        print()
        print("CÀI ĐẶT BÀI 13B-11.3.1 THÀNH CÔNG")
        return 0

    except Exception:
        traceback.print_exc()
        print()
        print("CÓ LỖI - ĐANG KHÔI PHỤC TEMPLATE...")
        restore()
        clear_cache()
        print("ĐÃ KHÔI PHỤC SOURCE.")
        print("Database không bị thay đổi.")
        print("Backup source:", BACKUP)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
