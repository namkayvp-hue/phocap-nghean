# -*- coding: utf-8 -*-
r'''
V12.2 - CHỌN NHANH BẰNG CÁCH GÕ ĐỂ TÌM
=======================================

Tạo bộ chọn nhanh dùng lại cho các select dài.
Áp dụng ngay cho ô Xã/phường tại màn hình nguồn học sinh đối chiếu.

Không sửa database. Không đổi route.
'''

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path


PROJECT = Path(r"C:\PhoCap")
TARGET = PROJECT / "app" / "templates" / "surveys" / "student_reconciliation_source.html"
JS_TARGET = PROJECT / "app" / "static" / "js" / "quick_select_v1.js"
EXPORTS = PROJECT / "exports"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP_DIR = EXPORTS / f"backup_v12_2_quick_select_{STAMP}"
BACKUP_TEMPLATE = (
    BACKUP_DIR / "app" / "templates" / "surveys" / "student_reconciliation_source.html"
)
REPORT = EXPORTS / f"bao_cao_v12_2_quick_select_{STAMP}.txt"

MARK_SELECT = 'data-quick-search="true"'
SCRIPT_TAG = '<script src="/static/js/quick_select_v1.js"></script>'

OLD_SELECT_START = (
    '<select name="commune_id" required '
    '{% if not can_unlock and communes|length == 1 %}disabled{% endif %}>'
)

NEW_SELECT_START = (
    '<select name="commune_id" required '
    'data-quick-search="true" '
    'data-quick-search-placeholder="Gõ tên xã/phường để tìm nhanh..." '
    '{% if not can_unlock and communes|length == 1 %}disabled{% endif %}>'
)

JS_CONTENT = r'''/* QUICK_SELECT_V1 */
(function () {
    "use strict";

    function norm(value) {
        return String(value || "")
            .normalize("NFD")
            .replace(/[\u0300-\u036f]/g, "")
            .replace(/đ/g, "d")
            .replace(/Đ/g, "D")
            .toLowerCase()
            .replace(/[^a-z0-9]+/g, " ")
            .trim()
            .replace(/\s+/g, " ");
    }

    function addStyle() {
        if (document.getElementById("quick-select-v1-style")) {
            return;
        }

        var style = document.createElement("style");
        style.id = "quick-select-v1-style";
        style.textContent =
            ".quick-select-wrap{width:100%}" +
            ".quick-select-input{" +
            "width:100%;box-sizing:border-box;padding:10px;" +
            "border:1px solid #c8d6e3;border-radius:8px;" +
            "background:#fff;color:inherit;font:inherit}" +
            ".quick-select-input:focus{" +
            "outline:2px solid rgba(21,101,192,.18);" +
            "border-color:#1565c0}";
        document.head.appendChild(style);
    }

    function enhance(select, index) {
        if (!select || select.dataset.quickSearchReady === "1") {
            return;
        }

        select.dataset.quickSearchReady = "1";

        var options = Array.from(select.options).filter(function (o) {
            return String(o.value || "").trim() !== "";
        });

        if (!options.length) {
            return;
        }

        var wrapper = document.createElement("div");
        wrapper.className = "quick-select-wrap";

        var input = document.createElement("input");
        input.type = "text";
        input.className = "quick-select-input";
        input.autocomplete = "off";
        input.placeholder =
            select.dataset.quickSearchPlaceholder || "Gõ để tìm nhanh...";

        var listId =
            "quick-select-list-" +
            String(index) +
            "-" +
            Math.random().toString(36).slice(2, 8);

        input.setAttribute("list", listId);

        var datalist = document.createElement("datalist");
        datalist.id = listId;

        options.forEach(function (option) {
            var item = document.createElement("option");
            item.value = option.text.trim();
            datalist.appendChild(item);
        });

        var selected = select.options[select.selectedIndex];
        if (selected && String(selected.value || "").trim() !== "") {
            input.value = selected.text.trim();
        }

        var wasRequired = select.required;
        select.required = false;

        function clearValidity() {
            input.setCustomValidity("");
        }

        function matchValue(raw, allowUniquePrefix) {
            var key = norm(raw);

            if (!key) {
                select.value = "";
                clearValidity();
                return false;
            }

            var exact = options.filter(function (o) {
                return norm(o.text) === key;
            });

            if (exact.length === 1) {
                select.value = exact[0].value;
                input.value = exact[0].text.trim();
                clearValidity();
                return true;
            }

            if (allowUniquePrefix) {
                var prefix = options.filter(function (o) {
                    return norm(o.text).startsWith(key);
                });

                if (prefix.length === 1) {
                    select.value = prefix[0].value;
                    input.value = prefix[0].text.trim();
                    clearValidity();
                    return true;
                }
            }

            select.value = "";
            return false;
        }

        input.addEventListener("input", function () {
            clearValidity();
            matchValue(input.value, false);
        });

        input.addEventListener("change", function () {
            if (!matchValue(input.value, true)) {
                input.setCustomValidity(
                    "Hãy chọn đúng một mục trong danh sách gợi ý."
                );
            }
        });

        input.addEventListener("blur", function () {
            if (input.value.trim()) {
                matchValue(input.value, true);
            }
        });

        var form = select.closest("form");
        if (form) {
            form.addEventListener("submit", function (event) {
                if (select.disabled) {
                    return;
                }

                if (!matchValue(input.value, true) && wasRequired) {
                    input.setCustomValidity(
                        "Hãy gõ và chọn đúng một mục trong danh sách."
                    );
                    input.reportValidity();
                    event.preventDefault();
                    return;
                }

                clearValidity();
            });
        }

        if (select.disabled) {
            input.disabled = true;
        }

        select.style.display = "none";
        select.parentNode.insertBefore(wrapper, select);
        wrapper.appendChild(input);
        wrapper.appendChild(datalist);
        wrapper.appendChild(select);
    }

    function init() {
        addStyle();

        document
            .querySelectorAll('select[data-quick-search="true"]')
            .forEach(function (select, index) {
                enhance(select, index);
            });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
'''


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def backup() -> None:
    BACKUP_TEMPLATE.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(TARGET, BACKUP_TEMPLATE)


def restore() -> None:
    if BACKUP_TEMPLATE.exists():
        TARGET.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(BACKUP_TEMPLATE, TARGET)


def patch_template(source: str) -> tuple[str, str]:
    changes = []

    if MARK_SELECT not in source:
        if source.count(OLD_SELECT_START) != 1:
            raise RuntimeError("Không tìm thấy đúng select Xã/phường của V12.")
        source = source.replace(OLD_SELECT_START, NEW_SELECT_START, 1)
        changes.append("COMMUNE_QUICK_SELECT")

    if SCRIPT_TAG not in source:
        closing = source.lower().rfind("</body>")
        if closing < 0:
            raise RuntimeError("Template không có </body>.")
        source = source[:closing] + "\n" + SCRIPT_TAG + "\n" + source[closing:]
        changes.append("INCLUDE_SHARED_JS")

    return source, "+".join(changes) or "ALREADY_INSTALLED"


def verify_template(source: str) -> None:
    required = (
        MARK_SELECT,
        'data-quick-search-placeholder="Gõ tên xã/phường để tìm nhanh..."',
        SCRIPT_TAG,
        'name="commune_id"',
    )

    missing = [x for x in required if x not in source]
    if missing:
        raise RuntimeError("Template sau sửa thiếu: " + repr(missing))

    if source.count(MARK_SELECT) != 1:
        raise RuntimeError("Marker quick-search Xã/phường bị lặp.")

    from jinja2 import Environment
    Environment().parse(source)


def verify_js(source: str) -> None:
    required = (
        "QUICK_SELECT_V1",
        'select[data-quick-search="true"]',
        "startsWith(key)",
        "setCustomValidity",
        "select.value",
    )
    missing = [x for x in required if x not in source]
    if missing:
        raise RuntimeError("JS quick-select thiếu: " + repr(missing))


def main() -> int:
    print("=" * 112)
    print("V12.2 - CHỌN NHANH BẰNG CÁCH GÕ ĐỂ TÌM")
    print("=" * 112)

    if not TARGET.exists():
        print(f"Không tìm thấy template: {TARGET}")
        return 2

    EXPORTS.mkdir(parents=True, exist_ok=True)
    BACKUP_DIR.mkdir(parents=True, exist_ok=False)
    backup()

    js_existed_before = JS_TARGET.exists()
    old_js = JS_TARGET.read_bytes() if js_existed_before else None

    try:
        before = read_text(TARGET)
        after, mode = patch_template(before)

        verify_template(after)
        verify_js(JS_CONTENT)

        JS_TARGET.parent.mkdir(parents=True, exist_ok=True)
        JS_TARGET.write_text(JS_CONTENT, encoding="utf-8")
        TARGET.write_text(after, encoding="utf-8")

        verify_template(read_text(TARGET))
        verify_js(JS_TARGET.read_text(encoding="utf-8"))

        REPORT.write_text(
            f'''V12.2 - CHỌN NHANH BẰNG CÁCH GÕ ĐỂ TÌM
================================================

MODE: {mode}

ĐÃ ÁP DỤNG:
- Ô Xã/phường tại màn hình Nạp dữ liệu học sinh đối chiếu.
- Gõ từ đầu để tìm nhanh.
- Backend vẫn nhận commune_id như cũ.
- Không thay đổi database / route.

FILE DÙNG CHUNG:
{JS_TARGET}

QUY ƯỚC CHO MÀN HÌNH SAU:
- select dài thêm data-quick-search="true"
- include {SCRIPT_TAG}

BACKUP:
{BACKUP_DIR}
''',
            encoding="utf-8",
        )

        print("CÀI V12.2 THÀNH CÔNG")
        print(f"Mode: {mode}")
        print("Database: KHÔNG THAY ĐỔI")
        print(f"Backup: {BACKUP_DIR}")
        print(f"Report: {REPORT}")
        print()
        print("Sau khi khởi động lại:")
        print(" - Xã/phường trở thành ô gõ tìm nhanh.")
        print(" - Ví dụ gõ 'Nghi' để lọc nhanh.")
        return 0

    except Exception as exc:
        print()
        print("CÓ LỖI V12.2:", repr(exc))
        print("Đang khôi phục...")
        restore()

        if js_existed_before and old_js is not None:
            JS_TARGET.parent.mkdir(parents=True, exist_ok=True)
            JS_TARGET.write_bytes(old_js)
        elif JS_TARGET.exists():
            JS_TARGET.unlink()

        print("Đã khôi phục. Database không thay đổi.")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
