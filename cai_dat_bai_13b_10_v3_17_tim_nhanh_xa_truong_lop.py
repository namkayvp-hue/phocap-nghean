from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

PROJECT = Path(r"C:\PhoCap")
APP = PROJECT / "app"
TARGET = APP / "templates" / "students" / "list.html"
EXPORTS = PROJECT / "exports"

MARK_START = "<!-- === BAI_13B_10_V3_17_QUICK_SELECT_START === -->"
MARK_END = "<!-- === BAI_13B_10_V3_17_QUICK_SELECT_END === -->"

BLOCK = r"""
<!-- === BAI_13B_10_V3_17_QUICK_SELECT_START === -->
<style>
.pc-quick-select-source {
    position: absolute !important;
    width: 1px !important;
    height: 1px !important;
    opacity: 0 !important;
    pointer-events: none !important;
    overflow: hidden !important;
}
.pc-quick-select { position: relative; width: 100%; }
.pc-quick-select-input {
    width: 100%;
    min-height: 44px;
    padding: 10px 38px 10px 12px;
    border: 1px solid #cbd8e6;
    border-radius: 8px;
    background: #fff;
    color: #1f3349;
    font: inherit;
    box-sizing: border-box;
}
.pc-quick-select-input:focus {
    outline: none;
    border-color: #1d75cf;
    box-shadow: 0 0 0 3px rgba(29,117,207,.12);
}
.pc-quick-select-input:disabled {
    background: #f3f5f7;
    color: #8492a2;
    cursor: not-allowed;
}
.pc-quick-select-arrow {
    position: absolute;
    right: 12px;
    top: 12px;
    pointer-events: none;
    color: #60758b;
    font-size: 14px;
}
.pc-quick-select-list {
    position: absolute;
    z-index: 5000;
    left: 0;
    right: 0;
    top: calc(100% + 4px);
    max-height: 280px;
    overflow-y: auto;
    padding: 5px;
    margin: 0;
    border: 1px solid #cbd8e6;
    border-radius: 9px;
    background: #fff;
    box-shadow: 0 12px 30px rgba(24,48,73,.18);
}
.pc-quick-select-list[hidden] { display: none !important; }
.pc-quick-select-option {
    display: block;
    width: 100%;
    padding: 9px 10px;
    border: 0;
    border-radius: 6px;
    background: transparent;
    color: #23384d;
    text-align: left;
    font: inherit;
    cursor: pointer;
}
.pc-quick-select-option:hover,
.pc-quick-select-option.is-active {
    background: #eaf3ff;
    color: #075ea8;
}
.pc-quick-select-empty {
    padding: 10px;
    color: #7a8795;
    font-size: 13px;
}
.pc-quick-select-hint {
    margin-top: 5px;
    font-size: 12px;
    color: #718197;
}
@media (max-width: 700px) {
    .pc-quick-select-input { min-height: 48px; font-size: 16px; }
    .pc-quick-select-list { max-height: 240px; }
    .pc-quick-select-option { min-height: 44px; padding: 11px 10px; }
}
</style>

<script>
(function () {
    "use strict";

    const TARGETS = [
        {
            id: "commune_id",
            placeholder: "Gõ tên xã/phường để tìm...",
            stripWords: ["xã", "phường", "thị trấn"]
        },
        {
            id: "school_id",
            placeholder: "Gõ tên trường để tìm...",
            stripWords: ["trường", "mầm non", "tiểu học", "thcs", "thpt", "mn", "th"]
        },
        {
            id: "class_id",
            placeholder: "Gõ tên lớp để tìm...",
            stripWords: ["lớp", "khối"]
        }
    ];

    function normalize(value) {
        return String(value || "")
            .normalize("NFD")
            .replace(/[\u0300-\u036f]/g, "")
            .toLowerCase()
            .replace(/đ/g, "d")
            .replace(/[–—\-_/.,;:()[\]{}]+/g, " ")
            .replace(/\s+/g, " ")
            .trim();
    }

    function stripCommonPrefix(text, words) {
        let result = normalize(text);
        for (const word of words || []) {
            const w = normalize(word);
            if (result === w) return "";
            if (result.startsWith(w + " ")) {
                return result.slice(w.length + 1).trim();
            }
        }
        return result;
    }

    function scoreOption(option, query, config) {
        const q = normalize(query);
        if (!q) return 100;

        const full = normalize(option.textContent || "");
        const stripped = stripCommonPrefix(option.textContent || "", config.stripWords);

        if (stripped === q) return 0;
        if (stripped.startsWith(q)) return 1;
        if (full.startsWith(q)) return 2;

        const words = stripped.split(" ");
        if (words.some(function (word) { return word.startsWith(q); })) return 3;
        if (stripped.includes(q)) return 4;
        if (full.includes(q)) return 5;

        return 999;
    }

    function realOptions(select) {
        return Array.from(select.options).filter(function (option) {
            return String(option.value || "").trim() !== "";
        });
    }

    function selectedLabel(select) {
        const option = select.options[select.selectedIndex];
        if (!option || !option.value) return "";
        return String(option.textContent || "").trim();
    }

    function createQuickSelect(select, config) {
        if (!select || select.dataset.pcQuickSelect === "1") return;

        select.dataset.pcQuickSelect = "1";
        select.classList.add("pc-quick-select-source");

        const wrapper = document.createElement("div");
        wrapper.className = "pc-quick-select";

        const input = document.createElement("input");
        input.type = "text";
        input.className = "pc-quick-select-input";
        input.placeholder = config.placeholder;
        input.autocomplete = "off";
        input.spellcheck = false;

        const arrow = document.createElement("span");
        arrow.className = "pc-quick-select-arrow";
        arrow.textContent = "▼";

        const list = document.createElement("div");
        list.className = "pc-quick-select-list";
        list.hidden = true;

        const hint = document.createElement("div");
        hint.className = "pc-quick-select-hint";
        hint.textContent = "Gõ từ đầu tiên của tên để lọc nhanh.";

        select.parentNode.insertBefore(wrapper, select);
        wrapper.appendChild(input);
        wrapper.appendChild(arrow);
        wrapper.appendChild(list);
        wrapper.appendChild(hint);
        wrapper.appendChild(select);

        let activeIndex = -1;
        let visibleOptions = [];

        function syncDisabled() {
            input.disabled = !!select.disabled;
            if (select.disabled) list.hidden = true;
        }

        function syncValue() {
            input.value = selectedLabel(select);
            input.dataset.selectedValue = String(select.value || "");
        }

        function closeList() {
            list.hidden = true;
            activeIndex = -1;
        }

        function choose(option) {
            if (!option) return;
            const oldValue = String(select.value || "");
            select.value = String(option.value || "");
            input.value = String(option.textContent || "").trim();
            input.dataset.selectedValue = String(select.value || "");
            closeList();

            if (String(select.value || "") !== oldValue) {
                select.dispatchEvent(new Event("change", { bubbles: true }));
            }
        }

        function render(query) {
            visibleOptions = realOptions(select)
                .map(function (option) {
                    return { option: option, score: scoreOption(option, query, config) };
                })
                .filter(function (item) { return item.score < 999; })
                .sort(function (a, b) {
                    if (a.score !== b.score) return a.score - b.score;
                    return String(a.option.textContent || "")
                        .localeCompare(String(b.option.textContent || ""), "vi");
                })
                .slice(0, 30)
                .map(function (item) { return item.option; });

            list.innerHTML = "";
            activeIndex = visibleOptions.length ? 0 : -1;

            if (!visibleOptions.length) {
                const empty = document.createElement("div");
                empty.className = "pc-quick-select-empty";
                empty.textContent = "Không tìm thấy kết quả phù hợp.";
                list.appendChild(empty);
                list.hidden = false;
                return;
            }

            visibleOptions.forEach(function (option, index) {
                const button = document.createElement("button");
                button.type = "button";
                button.className = "pc-quick-select-option";
                if (index === activeIndex) button.classList.add("is-active");
                button.textContent = String(option.textContent || "").trim();

                button.addEventListener("mousedown", function (event) {
                    event.preventDefault();
                    choose(option);
                });

                list.appendChild(button);
            });

            list.hidden = false;
        }

        function updateActive() {
            const items = list.querySelectorAll(".pc-quick-select-option");
            items.forEach(function (item, index) {
                item.classList.toggle("is-active", index === activeIndex);
            });
            const current = items[activeIndex];
            if (current && current.scrollIntoView) {
                current.scrollIntoView({ block: "nearest" });
            }
        }

        input.addEventListener("focus", function () {
            input.select();
            render("");
        });

        input.addEventListener("input", function () {
            input.dataset.selectedValue = "";
            render(input.value);
        });

        input.addEventListener("keydown", function (event) {
            if (event.key === "ArrowDown") {
                event.preventDefault();
                if (list.hidden) render(input.value);
                if (visibleOptions.length) {
                    activeIndex = Math.min(activeIndex + 1, visibleOptions.length - 1);
                    updateActive();
                }
                return;
            }

            if (event.key === "ArrowUp") {
                event.preventDefault();
                if (visibleOptions.length) {
                    activeIndex = Math.max(activeIndex - 1, 0);
                    updateActive();
                }
                return;
            }

            if (event.key === "Enter") {
                if (!list.hidden && visibleOptions.length) {
                    event.preventDefault();
                    choose(visibleOptions[activeIndex >= 0 ? activeIndex : 0]);
                }
                return;
            }

            if (event.key === "Escape") {
                closeList();
                syncValue();
            }
        });

        input.addEventListener("blur", function () {
            window.setTimeout(function () {
                closeList();
                if (
                    String(input.dataset.selectedValue || "") !==
                    String(select.value || "")
                ) {
                    syncValue();
                }
            }, 120);
        });

        select.addEventListener("change", syncValue);

        const observer = new MutationObserver(function () {
            syncDisabled();
            syncValue();
        });

        observer.observe(select, {
            childList: true,
            subtree: true,
            attributes: true,
            attributeFilter: ["disabled"]
        });

        syncDisabled();
        syncValue();
    }

    function install() {
        TARGETS.forEach(function (config) {
            const select = document.getElementById(config.id);
            if (select) createQuickSelect(select, config);
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", install);
    } else {
        install();
    }
})();
</script>
<!-- === BAI_13B_10_V3_17_QUICK_SELECT_END === -->
"""


def read_text(path: Path) -> str:
    if not path.exists():
        raise RuntimeError(f"Không tìm thấy template: {path}")
    return path.read_text(encoding="utf-8-sig")


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def backup_file() -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = EXPORTS / f"backup_bai_13b_10_v3_17_{stamp}"
    dst = backup / TARGET.relative_to(PROJECT)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(TARGET, dst)
    return backup


def restore_file(backup: Path) -> None:
    src = backup / TARGET.relative_to(PROJECT)
    if src.exists():
        shutil.copy2(src, TARGET)


def remove_old_block(text: str) -> str:
    while MARK_START in text and MARK_END in text:
        start = text.index(MARK_START)
        end = text.index(MARK_END, start) + len(MARK_END)
        text = text[:start] + text[end:]
    return text


def patch(text: str) -> str:
    for required_id in (
        'id="commune_id"',
        'id="school_id"',
        'id="class_id"',
    ):
        if required_id not in text:
            raise RuntimeError(
                f"Template hiện tại thiếu {required_id}. Dừng an toàn."
            )

    text = remove_old_block(text)

    if "</body>" in text:
        return text.replace("</body>", BLOCK + "\n</body>", 1)

    endblock = text.rfind("{% endblock %}")
    if endblock >= 0:
        return text[:endblock] + BLOCK + "\n" + text[endblock:]

    return text.rstrip() + "\n\n" + BLOCK + "\n"


def verify(text: str) -> None:
    from jinja2 import Environment

    Environment().parse(text)

    required = [
        MARK_START,
        MARK_END,
        'id: "commune_id"',
        'id: "school_id"',
        'id: "class_id"',
        "Gõ từ đầu tiên của tên để lọc nhanh.",
        "MutationObserver",
        'new Event("change"',
    ]

    missing = [item for item in required if item not in text]
    if missing:
        raise RuntimeError(
            "Kiểm tra sau cài chưa đạt, thiếu: " + " | ".join(missing)
        )


def clear_cache() -> None:
    for cache in APP.rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(cache, ignore_errors=True)


def main() -> None:
    print("=" * 96)
    print("BÀI 13B-10 V3.17 - TÌM NHANH XÃ / TRƯỜNG / LỚP BẰNG CÁCH GÕ TÊN")
    print("=" * 96)
    print()
    print("Áp dụng chung cho Học sinh MN / TH / THCS / THPT.")
    print("Ví dụ: gõ 'Tân' hoặc 'tan' để tìm nhanh Xã Tân Kỳ, Tân Phú...")
    print("Giữ nguyên lọc liên hoàn Xã -> Trường -> Lớp.")
    print("KHÔNG sửa database, router, dữ liệu học sinh hoặc phân quyền.")
    print()

    if not TARGET.exists():
        raise RuntimeError(f"Không tìm thấy: {TARGET}")

    EXPORTS.mkdir(parents=True, exist_ok=True)
    backup = backup_file()
    print("Backup:", backup)

    try:
        before = read_text(TARGET)
        after = patch(before)
        write_text(TARGET, after)

        verify(read_text(TARGET))
        clear_cache()

        print()
        print("CÀI ĐẶT BÀI 13B-10 V3.17 THÀNH CÔNG")
        print("Khởi động lại Uvicorn và Ctrl+F5.")

    except Exception:
        print()
        print("CÓ LỖI - ĐANG KHÔI PHỤC TEMPLATE...")
        restore_file(backup)
        clear_cache()
        print("ĐÃ KHÔI PHỤC students/list.html TRƯỚC V3.17.")
        print("Backup:", backup)
        raise


if __name__ == "__main__":
    main()
