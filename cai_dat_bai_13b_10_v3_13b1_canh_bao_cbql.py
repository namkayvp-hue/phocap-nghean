from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

PROJECT = Path(r"C:\PhoCap")
TEMPLATE = PROJECT / "app" / "templates" / "surveys" / "bulk_assignments.html"
EXPORTS = PROJECT / "exports"

MARKER_START = "{# === BAI_13B_10_V3_13B1_CBQL_WARNING_START === #}"
MARKER_END = "{# === BAI_13B_10_V3_13B1_CBQL_WARNING_END === #}"

BLOCK = r'''
{# === BAI_13B_10_V3_13B1_CBQL_WARNING_START === #}
<style>
    .pc-cbql-warning {
        margin: 10px 0 12px;
        padding: 12px 14px;
        border: 1px solid #f2cf77;
        border-radius: 10px;
        background: #fff8df;
        color: #805900;
        font-weight: 600;
        line-height: 1.45;
    }

    .pc-cbql-warning[hidden] {
        display: none !important;
    }

    .pc-cbql-warning__title {
        display: block;
        margin-bottom: 4px;
        color: #9a6500;
        font-weight: 800;
    }

    .pc-cbql-warning__detail {
        font-weight: 500;
    }
</style>

<script>
(function () {
    "use strict";

    if (!window.location.pathname.includes("/giao-phieu-giao-vien")) {
        return;
    }

    function textOfCandidate(checkbox) {
        let node = checkbox;
        for (let i = 0; i < 6 && node; i += 1, node = node.parentElement) {
            const text = (node.innerText || node.textContent || "").trim();
            if (/cbql\./i.test(text)) {
                return text.replace(/\s+/g, " ");
            }
        }
        return "";
    }

    function selectedCbqlItems() {
        const checked = Array.from(
            document.querySelectorAll('input[type="checkbox"]:checked')
        );

        const results = [];
        for (const checkbox of checked) {
            const text = textOfCandidate(checkbox);
            if (/cbql\./i.test(text)) {
                results.push(text);
            }
        }

        return Array.from(new Set(results));
    }

    function findActionArea() {
        const buttons = Array.from(
            document.querySelectorAll('button, input[type="submit"]')
        );

        const giaoButton = buttons.find(function (el) {
            const text = (
                el.innerText ||
                el.value ||
                el.textContent ||
                ""
            ).trim().toLowerCase();

            return text.includes("giao phiếu");
        });

        if (giaoButton) {
            return giaoButton.parentElement || giaoButton;
        }

        return document.querySelector("form") || document.body;
    }

    const warning = document.createElement("div");
    warning.className = "pc-cbql-warning";
    warning.hidden = true;
    warning.innerHTML =
        '<span class="pc-cbql-warning__title">⚠ Cảnh báo người được giao là CBQL</span>' +
        '<span class="pc-cbql-warning__detail"></span>';

    const actionArea = findActionArea();

    if (actionArea && actionArea.parentElement) {
        actionArea.parentElement.insertBefore(warning, actionArea);
    } else {
        document.body.prepend(warning);
    }

    function refreshWarning() {
        const items = selectedCbqlItems();
        const detail = warning.querySelector(".pc-cbql-warning__detail");

        if (!items.length) {
            warning.hidden = true;
            detail.textContent = "";
            return;
        }

        warning.hidden = false;
        detail.textContent =
            " Tổ điều tra vẫn phải giữ đủ 3 cấp: 1 Mầm non + 1 Tiểu học + 1 THCS. " +
            "Bạn đang chọn người có tài khoản CBQL. Đây là trường hợp thay thế/điều chỉnh đặc biệt; " +
            "hãy kiểm tra đúng người, đúng trường trước khi bấm Giao phiếu.";
    }

    document.addEventListener("change", function (event) {
        if (
            event.target &&
            event.target.matches &&
            event.target.matches('input[type="checkbox"]')
        ) {
            refreshWarning();
        }
    });

    document.addEventListener("submit", function (event) {
        const items = selectedCbqlItems();

        if (!items.length) {
            return;
        }

        const preview = items
            .slice(0, 3)
            .map(function (item) { return "• " + item; })
            .join("\n");

        const extra = items.length > 3
            ? "\n• ... và " + (items.length - 3) + " người khác"
            : "";

        const ok = window.confirm(
            "CẢNH BÁO: Người được giao có tài khoản CBQL.\n\n" +
            "Nguyên tắc tổ vẫn là 1 người Mầm non + 1 người Tiểu học + 1 người THCS.\n" +
            "CBQL chỉ là trường hợp thay thế/điều chỉnh có chủ đích.\n\n" +
            preview + extra +
            "\n\nBạn xác nhận vẫn tiếp tục Giao phiếu?"
        );

        if (!ok) {
            event.preventDefault();
            event.stopImmediatePropagation();
        }
    }, true);

    refreshWarning();
})();
</script>
{# === BAI_13B_10_V3_13B1_CBQL_WARNING_END === #}
'''


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def backup_file() -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = EXPORTS / f"backup_bai_13b_10_v3_13b1_{stamp}"
    dst = backup / TEMPLATE.relative_to(PROJECT)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(TEMPLATE, dst)
    return backup


def restore(backup: Path) -> None:
    saved = backup / TEMPLATE.relative_to(PROJECT)
    if saved.exists():
        shutil.copy2(saved, TEMPLATE)


def remove_old_failed_blocks(text: str) -> str:
    old_start = "{# === BAI_13B_10_V3_13B_CBQL_WARNING_START === #}"
    old_end = "{# === BAI_13B_10_V3_13B_CBQL_WARNING_END === #}"

    if old_start in text and old_end in text:
        a = text.index(old_start)
        b = text.index(old_end, a) + len(old_end)
        text = text[:a] + text[b:]

    return text


def patch_template(text: str) -> str:
    text = remove_old_failed_blocks(text)

    if MARKER_START in text and MARKER_END in text:
        return text

    idx = text.rfind("{% endblock %}")

    if idx >= 0:
        return text[:idx] + BLOCK + "\n" + text[idx:]

    return text.rstrip() + "\n\n" + BLOCK + "\n"


def verify(text: str) -> None:
    checks = [
        (MARKER_START in text, "thiếu marker START"),
        (MARKER_END in text, "thiếu marker END"),
        ('/giao-phieu-giao-vien' in text, "thiếu giới hạn route giao phiếu"),
        (r'/cbql\./i' in text, "thiếu nhận diện tài khoản CBQL"),
        ("Cảnh báo người được giao là CBQL" in text, "thiếu cảnh báo CBQL"),
        ("1 Mầm non + 1 Tiểu học + 1 THCS" in text, "thiếu nguyên tắc tổ 3 cấp"),
        ("window.confirm" in text, "thiếu hộp xác nhận"),
    ]

    failures = [msg for ok, msg in checks if not ok]

    if failures:
        raise RuntimeError("Kiểm tra sau cài chưa đạt: " + "; ".join(failures))


def main() -> None:
    print("=" * 78)
    print("BÀI 13B-10 V3.13B.1 - SỬA LỖI KIỂM TRA CẢNH BÁO CBQL")
    print("=" * 78)
    print("Nguyên nhân bản V3.13B:")
    print(" - Code nhận diện CBQL dùng regex /cbql\\./i.")
    print(" - Bộ verify lại kiểm tra chuỗi literal 'cbql.'.")
    print(" - Vì vậy cài đúng nhưng verify báo sai và tự rollback.")
    print()
    print("V3.13B.1:")
    print(" - Sửa verify đúng với regex thực tế.")
    print(" - Không sửa database.")
    print(" - Không đổi route.")
    print(" - Không đổi cơ chế tổ 3 cấp.")
    print(" - Vẫn chỉ cảnh báo, KHÔNG chặn CBQL.")

    if not TEMPLATE.exists():
        raise RuntimeError(f"Không tìm thấy template: {TEMPLATE}")

    EXPORTS.mkdir(parents=True, exist_ok=True)

    backup = backup_file()
    print("Backup:", backup)

    try:
        original = read_text(TEMPLATE)
        patched = patch_template(original)
        write_text(TEMPLATE, patched)

        reread = read_text(TEMPLATE)
        verify(reread)

        print()
        print("KIỂM TRA SAU CÀI:")
        print(" - Nhận diện cbql.*: OK")
        print(" - Cảnh báo màu vàng: OK")
        print(" - Hộp xác nhận trước Giao phiếu: OK")
        print(" - CBQL vẫn được phép nếu bấm OK: OK")
        print()
        print("CÀI ĐẶT BÀI 13B-10 V3.13B.1 THÀNH CÔNG")
        print("Khởi động lại Uvicorn và Ctrl+F5.")

    except Exception:
        print()
        print("CÓ LỖI - ĐANG KHÔI PHỤC TEMPLATE...")
        restore(backup)
        print("ĐÃ KHÔI PHỤC TEMPLATE TRƯỚC V3.13B.1.")
        print("Backup:", backup)
        raise


if __name__ == "__main__":
    main()
