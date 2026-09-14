# -*- coding: utf-8 -*-
r"""
V13.13 - TÌM KIẾM NHANH TOÀN HỆ THỐNG
=======================================

MỤC TIÊU
--------
Bổ sung tìm kiếm nhanh mà KHÔNG đổi route, KHÔNG đổi database,
KHÔNG đổi dữ liệu và KHÔNG thay luồng nghiệp vụ.

1) BẢNG DANH SÁCH DÀI
- Tự thêm ô "Tìm nhanh trong danh sách".
- Có nút "Tìm" và "Xóa".
- Enter để tìm.
- Ctrl+K để đưa con trỏ vào ô tìm nhanh đầu tiên.
- Tìm không phân biệt hoa/thường và hỗ trợ bỏ dấu tiếng Việt.
- Tìm trên toàn bộ nội dung các cột của từng dòng đang hiển thị.
- Tự hiện "x / y dòng".

2) SELECT DÀI
- Tự thêm ô "Gõ để lọc lựa chọn" cho các select dài.
- Đặc biệt phù hợp Xã/phường, Trường, Lớp, Giáo viên/nhân sự...
- KHÔNG đổi name/id/value của select.
- KHÔNG xóa option thật; chỉ ẩn option không khớp.
- Select động được cập nhật qua AJAX/JavaScript vẫn được theo dõi.

PHẠM VI
-------
Cài 1 block dùng chung vào:
C:\PhoCap\app\templates\partials\dropdown_menu_v1.html

Do partial menu này được dùng trên các màn hình nghiệp vụ chính, chức năng
tìm kiếm nhanh sẽ tự áp dụng cho các trang danh sách và select dài.

AN TOÀN
-------
- Backup file nguồn trước khi sửa.
- Marker chống chèn lặp.
- Kiểm tra cú pháp Jinja sau khi cài.
- KHÔNG sửa database.
- KHÔNG sửa Plan JSON.
- KHÔNG đụng dữ liệu sáp nhập.

CHẠY
----
cd C:\PhoCap
.\.venv\Scripts\python.exe .\cai_dat_v13_13_tim_kiem_nhanh_toan_he_thong.py

SAU KHI CÀI
-----------
Khởi động lại Uvicorn và Ctrl+F5 trình duyệt.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path


ROOT = Path(r"C:\PhoCap")
APP = ROOT / "app"
MENU = APP / "templates" / "partials" / "dropdown_menu_v1.html"
EXPORTS = ROOT / "exports"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = EXPORTS / f"backup_source_v13_13_tim_kiem_nhanh_{STAMP}"
REPORT = ROOT / f"bao_cao_cai_v13_13_tim_kiem_nhanh_{STAMP}.txt"

MARK_START = "<!-- === V13_13_QUICK_SEARCH_GLOBAL_START === -->"
MARK_END = "<!-- === V13_13_QUICK_SEARCH_GLOBAL_END === -->"


BLOCK = r"""
<!-- === V13_13_QUICK_SEARCH_GLOBAL_START === -->
<style>
    .pcqs-table-toolbar {
        margin: 14px 0 16px;
        padding: 12px;
        border: 1px solid #d8e4ef;
        border-radius: 12px;
        background: #f8fbff;
        display: flex;
        align-items: center;
        gap: 9px;
        flex-wrap: wrap;
    }

    .pcqs-table-toolbar__input {
        flex: 1 1 320px;
        min-width: 220px;
        height: 40px;
        padding: 0 13px;
        border: 1px solid #bfcddd;
        border-radius: 9px;
        background: #fff;
        color: #1f3347;
        font: inherit;
        outline: none;
    }

    .pcqs-table-toolbar__input:focus,
    .pcqs-select-filter__input:focus {
        border-color: #1976d2;
        box-shadow: 0 0 0 3px rgba(25, 118, 210, 0.12);
    }

    .pcqs-btn {
        min-height: 40px;
        padding: 0 15px;
        border: 0;
        border-radius: 9px;
        font: inherit;
        font-weight: 700;
        cursor: pointer;
    }

    .pcqs-btn--find {
        background: #1976d2;
        color: #fff;
    }

    .pcqs-btn--find:hover {
        background: #125ea8;
    }

    .pcqs-btn--clear {
        background: #eaf1f7;
        color: #24405a;
    }

    .pcqs-btn--clear:hover {
        background: #dce8f2;
    }

    .pcqs-count {
        margin-left: auto;
        color: #60758a;
        font-size: 13px;
        font-weight: 700;
        white-space: nowrap;
    }

    .pcqs-no-result {
        display: none;
        margin: -5px 0 15px;
        padding: 10px 12px;
        border-radius: 9px;
        background: #fff8e1;
        color: #725300;
        font-size: 13px;
        font-weight: 700;
    }

    .pcqs-no-result.is-visible {
        display: block;
    }

    .pcqs-select-filter {
        margin: 0 0 7px;
        display: flex;
        align-items: center;
        gap: 6px;
    }

    .pcqs-select-filter__input {
        width: 100%;
        min-width: 0;
        height: 36px;
        padding: 0 10px;
        border: 1px solid #c5d2df;
        border-radius: 8px;
        background: #fff;
        color: #1f3347;
        font: inherit;
        font-size: 13px;
        outline: none;
    }

    .pcqs-select-filter__clear {
        width: 36px;
        height: 36px;
        flex: 0 0 36px;
        border: 1px solid #c5d2df;
        border-radius: 8px;
        background: #f3f7fa;
        color: #455e75;
        cursor: pointer;
        font-size: 18px;
        line-height: 1;
    }

    .pcqs-select-filter__clear:hover {
        background: #e6eef5;
    }

    .pcqs-select-filter.is-disabled {
        opacity: 0.55;
        pointer-events: none;
    }

    .pcqs-highlight-row {
        background: #fffde7 !important;
    }

    @media (max-width: 650px) {
        .pcqs-table-toolbar {
            align-items: stretch;
        }

        .pcqs-table-toolbar__input {
            flex-basis: 100%;
            width: 100%;
        }

        .pcqs-btn {
            flex: 1 1 90px;
        }

        .pcqs-count {
            width: 100%;
            margin-left: 0;
        }
    }
</style>

<script>
(function () {
    "use strict";

    if (window.PCQuickSearchV1313Installed) {
        return;
    }
    window.PCQuickSearchV1313Installed = true;

    var TABLE_MIN_ROWS = 12;
    var SELECT_MIN_OPTIONS = 15;

    function normalizeText(value) {
        return String(value || "")
            .toLowerCase()
            .normalize("NFD")
            .replace(/[\u0300-\u036f]/g, "")
            .replace(/đ/g, "d")
            .replace(/\s+/g, " ")
            .trim();
    }

    function isElementVisible(element) {
        if (!element) {
            return false;
        }

        var style = window.getComputedStyle(element);
        return (
            style.display !== "none"
            && style.visibility !== "hidden"
        );
    }

    function hasManyEditableCells(table) {
        var inputs = table.querySelectorAll(
            "tbody input, tbody textarea, tbody select"
        );
        return inputs.length >= 6;
    }

    function getTableRows(table) {
        return Array.prototype.slice.call(
            table.querySelectorAll("tbody tr")
        ).filter(function (row) {
            return !row.hasAttribute("data-pcqs-ignore");
        });
    }

    function rowSearchText(row) {
        return normalizeText(row.innerText || row.textContent || "");
    }

    function findInsertionTarget(table) {
        var wrapper = table.closest(
            ".table-responsive, .table-container, "
            + ".table-wrapper, .responsive-table, .card, section"
        );

        if (
            wrapper
            && wrapper !== document.body
            && wrapper.querySelectorAll("table").length === 1
        ) {
            return wrapper;
        }

        return table;
    }

    function enhanceTable(table, index) {
        if (!table || table.dataset.pcqsReady === "1") {
            return;
        }

        if (table.closest("[data-no-quick-search]")) {
            return;
        }

        var rows = getTableRows(table);

        if (rows.length < TABLE_MIN_ROWS) {
            return;
        }

        if (hasManyEditableCells(table)) {
            return;
        }

        table.dataset.pcqsReady = "1";

        var target = findInsertionTarget(table);

        var toolbar = document.createElement("div");
        toolbar.className = "pcqs-table-toolbar";
        toolbar.setAttribute("data-pcqs-toolbar", "1");

        var input = document.createElement("input");
        input.type = "search";
        input.className = "pcqs-table-toolbar__input";
        input.placeholder = "Tìm nhanh: tên, mã, xã/phường, trạng thái...";
        input.autocomplete = "off";
        input.setAttribute(
            "aria-label",
            "Tìm nhanh trong danh sách"
        );

        var findButton = document.createElement("button");
        findButton.type = "button";
        findButton.className = "pcqs-btn pcqs-btn--find";
        findButton.textContent = "Tìm";

        var clearButton = document.createElement("button");
        clearButton.type = "button";
        clearButton.className = "pcqs-btn pcqs-btn--clear";
        clearButton.textContent = "Xóa";

        var count = document.createElement("span");
        count.className = "pcqs-count";

        toolbar.appendChild(input);
        toolbar.appendChild(findButton);
        toolbar.appendChild(clearButton);
        toolbar.appendChild(count);

        var noResult = document.createElement("div");
        noResult.className = "pcqs-no-result";
        noResult.textContent = "Không tìm thấy dòng phù hợp.";

        target.parentNode.insertBefore(toolbar, target);
        target.parentNode.insertBefore(noResult, target);

        function applySearch() {
            var query = normalizeText(input.value);
            var matched = 0;

            rows = getTableRows(table);

            rows.forEach(function (row) {
                var ok = !query || rowSearchText(row).indexOf(query) !== -1;
                row.hidden = !ok;

                row.classList.remove("pcqs-highlight-row");

                if (ok) {
                    matched += 1;
                    if (query) {
                        row.classList.add("pcqs-highlight-row");
                    }
                }
            });

            count.textContent = matched + " / " + rows.length + " dòng";
            noResult.classList.toggle(
                "is-visible",
                rows.length > 0 && matched === 0
            );
        }

        function clearSearch() {
            input.value = "";
            applySearch();
            input.focus();
        }

        findButton.addEventListener("click", applySearch);
        clearButton.addEventListener("click", clearSearch);

        input.addEventListener("keydown", function (event) {
            if (event.key === "Enter") {
                event.preventDefault();
                applySearch();
            }

            if (event.key === "Escape") {
                clearSearch();
            }
        });

        // Gõ cũng lọc ngay để thao tác nhanh hơn.
        input.addEventListener("input", applySearch);

        applySearch();

        if (index === 0) {
            input.dataset.pcqsPrimary = "1";
        }
    }

    function selectShouldBeEnhanced(select) {
        if (!select || select.dataset.pcqsSelectReady === "1") {
            return false;
        }

        if (
            select.closest("[data-no-select-search]")
            || select.multiple
            || select.size > 1
        ) {
            return false;
        }

        var name = String(
            select.getAttribute("name")
            || select.id
            || ""
        ).toLowerCase();

        var blacklist = [
            "school_year",
            "nam_hoc",
            "year_id",
            "status",
            "role",
            "level_code",
            "cap",
            "report_type",
            "gender",
            "gioi_tinh"
        ];

        if (blacklist.some(function (part) {
            return name.indexOf(part) !== -1;
        })) {
            return false;
        }

        var options = select.querySelectorAll("option");
        return options.length >= SELECT_MIN_OPTIONS;
    }

    function enhanceSelect(select) {
        if (!selectShouldBeEnhanced(select)) {
            return;
        }

        select.dataset.pcqsSelectReady = "1";

        var box = document.createElement("div");
        box.className = "pcqs-select-filter";

        var input = document.createElement("input");
        input.type = "search";
        input.className = "pcqs-select-filter__input";
        input.autocomplete = "off";

        var labelText = "";
        if (select.id) {
            var escapedId = (
                window.CSS && CSS.escape
                ? CSS.escape(select.id)
                : select.id.replace(/"/g, '\\"')
            );
            var label = document.querySelector(
                'label[for="' + escapedId + '"]'
            );
            if (label) {
                labelText = String(
                    label.innerText || label.textContent || ""
                ).trim();
            }
        }

        input.placeholder = labelText
            ? "Gõ để tìm " + labelText.toLowerCase()
            : "Gõ để lọc lựa chọn...";

        var clear = document.createElement("button");
        clear.type = "button";
        clear.className = "pcqs-select-filter__clear";
        clear.textContent = "×";
        clear.title = "Xóa nội dung tìm";

        box.appendChild(input);
        box.appendChild(clear);
        select.parentNode.insertBefore(box, select);

        var observerBusy = false;

        function syncDisabled() {
            var disabled = !!select.disabled;
            input.disabled = disabled;
            clear.disabled = disabled;
            box.classList.toggle("is-disabled", disabled);
        }

        function applyFilter() {
            var query = normalizeText(input.value);
            var selectedValue = select.value;

            Array.prototype.slice.call(
                select.options
            ).forEach(function (option, idx) {
                var text = normalizeText(
                    option.textContent || option.innerText || ""
                );

                var keep = (
                    idx === 0
                    || option.value === selectedValue
                    || !query
                    || text.indexOf(query) !== -1
                );

                option.hidden = !keep;
            });
        }

        input.addEventListener("input", applyFilter);

        input.addEventListener("keydown", function (event) {
            if (event.key === "Escape") {
                input.value = "";
                applyFilter();
                input.focus();
            }
        });

        clear.addEventListener("click", function () {
            input.value = "";
            applyFilter();
            input.focus();
        });

        select.addEventListener("change", applyFilter);

        var observer = new MutationObserver(function () {
            if (observerBusy) {
                return;
            }

            observerBusy = true;
            window.requestAnimationFrame(function () {
                syncDisabled();
                applyFilter();
                observerBusy = false;
            });
        });

        observer.observe(select, {
            childList: true,
            subtree: true,
            attributes: true,
            attributeFilter: ["disabled"]
        });

        syncDisabled();
        applyFilter();
    }

    function scanTables() {
        var tables = Array.prototype.slice.call(
            document.querySelectorAll("table")
        );

        var enhancedIndex = 0;

        tables.forEach(function (table) {
            var before = table.dataset.pcqsReady;
            enhanceTable(table, enhancedIndex);
            if (!before && table.dataset.pcqsReady === "1") {
                enhancedIndex += 1;
            }
        });
    }

    function scanSelects() {
        Array.prototype.slice.call(
            document.querySelectorAll("select")
        ).forEach(enhanceSelect);
    }

    function scanAll() {
        scanTables();
        scanSelects();
    }

    function focusPrimarySearch() {
        var input = document.querySelector(
            '.pcqs-table-toolbar__input[data-pcqs-primary="1"], '
            + ".pcqs-table-toolbar__input"
        );

        if (input && isElementVisible(input)) {
            input.focus();
            input.select();
            return true;
        }

        var selectInput = document.querySelector(
            ".pcqs-select-filter__input:not(:disabled)"
        );

        if (selectInput && isElementVisible(selectInput)) {
            selectInput.focus();
            selectInput.select();
            return true;
        }

        return false;
    }

    document.addEventListener("keydown", function (event) {
        if (
            (event.ctrlKey || event.metaKey)
            && String(event.key || "").toLowerCase() === "k"
        ) {
            if (focusPrimarySearch()) {
                event.preventDefault();
            }
        }
    });

    function start() {
        scanAll();

        var bodyObserver = new MutationObserver(function (mutations) {
            var shouldScan = mutations.some(function (mutation) {
                return mutation.addedNodes && mutation.addedNodes.length > 0;
            });

            if (shouldScan) {
                window.requestAnimationFrame(scanAll);
            }
        });

        bodyObserver.observe(document.body, {
            childList: true,
            subtree: true
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", start);
    } else {
        start();
    }
})();
</script>
<!-- === V13_13_QUICK_SEARCH_GLOBAL_END === -->
"""


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def backup_file() -> None:
    target = BACKUP / MENU.relative_to(ROOT)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(MENU, target)

    manifest = {
        "version": "V13.13",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "file": str(MENU),
        "backup": str(target),
        "database_changed": False,
        "plan_json_changed": False,
    }

    (BACKUP / "manifest.json").write_text(
        json.dumps(
            manifest,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def patch(text: str) -> tuple[str, str]:
    if MARK_START in text and MARK_END in text:
        return text, "ALREADY_INSTALLED"

    required = [
        "menu_role",
        "pc-menu-group",
        "pc-menu-trigger",
    ]

    missing = [
        marker
        for marker in required
        if marker not in text
    ]

    if missing:
        raise RuntimeError(
            "dropdown_menu_v1.html không đúng cấu trúc dự kiến; "
            f"thiếu marker: {missing}"
        )

    if MARK_START in text or MARK_END in text:
        raise RuntimeError(
            "Chỉ tìm thấy một đầu marker V13.13; "
            "dừng để tránh chèn sai."
        )

    new_text = text.rstrip() + "\n\n" + BLOCK.strip() + "\n"
    return new_text, "INSTALLED"


def verify_template(path: Path) -> None:
    text = read_text(path)

    required = [
        MARK_START,
        MARK_END,
        "PCQuickSearchV1313Installed",
        "Tìm nhanh: tên, mã, xã/phường, trạng thái",
        "Gõ để lọc lựa chọn",
        "TABLE_MIN_ROWS = 12",
        "SELECT_MIN_OPTIONS = 15",
    ]

    for marker in required:
        if marker not in text:
            raise RuntimeError(
                f"Thiếu marker sau cài: {marker}"
            )

    try:
        from jinja2 import Environment
        Environment().parse(text)
    except Exception as exc:
        raise RuntimeError(
            f"Jinja parse không đạt: {exc}"
        ) from exc


def clear_cache() -> int:
    count = 0
    for cache in APP.rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(cache, ignore_errors=True)
            count += 1
    return count


def main() -> int:
    print("=" * 104)
    print("V13.13 - CÀI TÌM KIẾM NHANH TOÀN HỆ THỐNG")
    print("=" * 104)
    print("")

    if not MENU.exists():
        raise RuntimeError(
            f"Không tìm thấy menu dùng chung: {MENU}"
        )

    old_text = read_text(MENU)
    new_text, action = patch(old_text)

    if action == "ALREADY_INSTALLED":
        verify_template(MENU)
        print("V13.13 đã có sẵn - không chèn lặp.")
        print("Database: KHÔNG THAY ĐỔI")
        print("Plan JSON: KHÔNG THAY ĐỔI")
        return 0

    backup_file()

    try:
        MENU.write_text(
            new_text,
            encoding="utf-8",
        )

        verify_template(MENU)
        cache_count = clear_cache()

    except Exception:
        backup_source = (
            BACKUP
            / MENU.relative_to(ROOT)
        )
        if backup_source.exists():
            shutil.copy2(
                backup_source,
                MENU,
            )
        raise

    report = f"""V13.13 - TÌM KIẾM NHANH TOÀN HỆ THỐNG
================================================================================

STATUS=SUCCESS

Đã cài vào:
{MENU}

Chức năng:
1. Danh sách dài >= 12 dòng:
   - ô Tìm nhanh
   - nút Tìm
   - nút Xóa
   - Enter để tìm
   - Esc để xóa
   - Ctrl+K focus tìm nhanh
   - bỏ dấu tiếng Việt khi so khớp
   - hiện số dòng phù hợp

2. Select dài >= 15 lựa chọn:
   - ô gõ để lọc
   - nút xóa
   - không đổi id/name/value
   - không xóa option thật
   - theo dõi select động

Bỏ qua:
- bảng nhập liệu có nhiều input/select
- select Năm học / trạng thái / vai trò / cấp học / loại báo cáo
- bảng ngắn
- select ngắn

Backup:
{BACKUP}

Đã xóa __pycache__: {cache_count}

Database=KHÔNG THAY ĐỔI
Plan JSON=KHÔNG THAY ĐỔI
Dữ liệu sáp nhập=KHÔNG THAY ĐỔI

Sau cài:
- khởi động lại Uvicorn
- Ctrl+F5 trình duyệt
"""

    REPORT.write_text(
        report,
        encoding="utf-8",
    )

    print("CÀI ĐẶT THÀNH CÔNG")
    print(f"Backup: {BACKUP}")
    print(f"Báo cáo: {REPORT}")
    print("")
    print("Đã thêm:")
    print(" - Tìm nhanh cho bảng danh sách dài")
    print(" - Nút Tìm + Xóa")
    print(" - Ctrl+K để focus ô tìm")
    print(" - Gõ để lọc Xã/Trường/Lớp/GV ở select dài")
    print("")
    print("Database: KHÔNG THAY ĐỔI")
    print("Plan JSON: KHÔNG THAY ĐỔI")
    print("Dữ liệu sáp nhập: KHÔNG THAY ĐỔI")
    print("")
    print("Hãy khởi động lại Uvicorn và bấm Ctrl+F5.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print("")
        print("=" * 104)
        print("V13.13 DỪNG AN TOÀN")
        print("=" * 104)
        print(repr(exc))
        print("Nếu đã tạo backup, source sẽ được tự khôi phục khi lỗi.")
        print("Database: KHÔNG THAY ĐỔI")
        print("Plan JSON: KHÔNG THAY ĐỔI")
        raise SystemExit(2)
