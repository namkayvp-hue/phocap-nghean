from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

PROJECT = Path(r"C:\PhoCap")
TEMPLATE = PROJECT / "app" / "templates" / "surveys" / "bulk_assignments.html"
EXPORTS = PROJECT / "exports"

OLD_BLOCKS = [
    (
        "{# === BAI_13B_10_V3_13B_CBQL_WARNING_START === #}",
        "{# === BAI_13B_10_V3_13B_CBQL_WARNING_END === #}",
    ),
    (
        "{# === BAI_13B_10_V3_13B1_CBQL_WARNING_START === #}",
        "{# === BAI_13B_10_V3_13B1_CBQL_WARNING_END === #}",
    ),
    (
        "{# === BAI_13B_10_V3_13B2_CBQL_WARNING_START === #}",
        "{# === BAI_13B_10_V3_13B2_CBQL_WARNING_END === #}",
    ),
]

START = "{# === BAI_13B_10_V3_13B3_CBQL_WARNING_START === #}"
END = "{# === BAI_13B_10_V3_13B3_CBQL_WARNING_END === #}"

BLOCK = r'''
{# === BAI_13B_10_V3_13B3_CBQL_WARNING_START === #}
<style>
.pc-cbql-warning-v313b3 {
    margin: 10px 0 12px;
    padding: 12px 14px;
    border: 1px solid #e8bd56;
    border-radius: 10px;
    background: #fff5cf;
    color: #6f4d00;
    line-height: 1.45;
}
.pc-cbql-warning-v313b3[hidden] {
    display: none !important;
}
.pc-cbql-warning-v313b3 strong {
    display: block;
    margin-bottom: 3px;
    color: #8f5f00;
}
</style>

<script>
(function () {
    "use strict";

    if (!window.location.pathname.includes("/giao-phieu-giao-vien")) {
        return;
    }

    function cleanText(el) {
        return ((el && (el.innerText || el.textContent)) || "")
            .replace(/\s+/g, " ")
            .trim();
    }

    function personCardOf(checkbox) {
        let node = checkbox.parentElement;
        let fallback = checkbox.parentElement;

        for (let i = 0; i < 10 && node; i += 1, node = node.parentElement) {
            const boxes = node.querySelectorAll('input[type="checkbox"]');

            if (boxes.length === 1 && boxes[0] === checkbox) {
                fallback = node;

                const text = cleanText(node);
                const hasUsername = /\b(?:cbql|gv)\.\d+\b/i.test(text);

                if (hasUsername) {
                    return node;
                }
            }

            if (boxes.length > 1) {
                break;
            }
        }

        return fallback;
    }

    function selectedCbqlPeople() {
        const checked = Array.from(
            document.querySelectorAll('input[type="checkbox"]:checked')
        );

        const result = [];

        for (const checkbox of checked) {
            const card = personCardOf(checkbox);
            const text = cleanText(card);

            if (/\bcbql\.\d+\b/i.test(text)) {
                result.push(text);
            }
        }

        return Array.from(new Set(result));
    }

    function shortLabel(text) {
        let value = String(text || "")
            .replace(/\bChính\b/gi, "")
            .replace(/\s+/g, " ")
            .trim();

        if (value.length > 150) {
            value = value.slice(0, 147) + "...";
        }

        return value;
    }

    function findGiaoButton() {
        const elements = Array.from(
            document.querySelectorAll('button, input[type="submit"]')
        );

        return elements.find(function (el) {
            const t = cleanText(el).toLowerCase();
            const v = String(el.value || "").toLowerCase();
            return t.includes("giao phiếu") || v.includes("giao phiếu");
        }) || null;
    }

    const warning = document.createElement("div");
    warning.className = "pc-cbql-warning-v313b3";
    warning.hidden = true;
    warning.innerHTML =
        "<strong>⚠ Cảnh báo người được giao là CBQL</strong>" +
        "<span></span>";

    const giaoButton = findGiaoButton();

    if (giaoButton && giaoButton.parentElement) {
        giaoButton.parentElement.insertBefore(warning, giaoButton);
    } else {
        const form = document.querySelector("form");
        (form || document.body).appendChild(warning);
    }

    function refreshWarning() {
        const cbqlPeople = selectedCbqlPeople();
        const detail = warning.querySelector("span");

        if (!cbqlPeople.length) {
            warning.hidden = true;
            detail.textContent = "";
            return;
        }

        warning.hidden = false;
        detail.textContent =
            "Tổ điều tra vẫn phải giữ đủ 3 cấp: 1 Mầm non + 1 Tiểu học + 1 THCS. " +
            "Bạn đang chọn CBQL: " +
            cbqlPeople.map(shortLabel).join(" | ") +
            ". Đây là trường hợp thay thế/điều chỉnh đặc biệt.";
    }

    function isGiaoPhieuButton(target) {
        const button = target && target.closest
            ? target.closest('button, input[type="submit"]')
            : null;

        if (!button) {
            return false;
        }

        const t = cleanText(button).toLowerCase();
        const v = String(button.value || "").toLowerCase();

        return t.includes("giao phiếu") || v.includes("giao phiếu");
    }

    document.addEventListener("click", function (event) {
        if (!isGiaoPhieuButton(event.target)) {
            return;
        }

        const cbqlPeople = selectedCbqlPeople();

        if (!cbqlPeople.length) {
            return;
        }

        const preview = cbqlPeople
            .map(function (text) {
                return "• " + shortLabel(text);
            })
            .join("\n");

        const ok = window.confirm(
            "CẢNH BÁO: Người được giao có tài khoản CBQL.\n\n" +
            "Nguyên tắc tổ vẫn là 1 người Mầm non + 1 người Tiểu học + 1 người THCS.\n" +
            "CBQL chỉ là trường hợp thay thế/điều chỉnh có chủ đích.\n\n" +
            preview +
            "\n\nBạn xác nhận vẫn tiếp tục?"
        );

        if (!ok) {
            event.preventDefault();
            event.stopImmediatePropagation();
            event.stopPropagation();
            return false;
        }
    }, true);

    document.addEventListener("change", function (event) {
        if (
            event.target &&
            event.target.matches &&
            event.target.matches('input[type="checkbox"]')
        ) {
            refreshWarning();
        }
    }, true);

    refreshWarning();
})();
</script>
{# === BAI_13B_10_V3_13B3_CBQL_WARNING_END === #}
'''


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def remove_block(text: str, start: str, end: str) -> str:
    while start in text and end in text:
        a = text.index(start)
        b = text.index(end, a) + len(end)
        text = text[:a] + text[b:]
    return text


def patch_template(text: str) -> str:
    for start, end in OLD_BLOCKS:
        text = remove_block(text, start, end)

    text = remove_block(text, START, END)

    idx = text.rfind("{% endblock %}")
    if idx >= 0:
        return text[:idx] + BLOCK + "\n" + text[idx:]

    return text.rstrip() + "\n\n" + BLOCK + "\n"


def verify(text: str) -> None:
    required = [
        START,
        END,
        "function personCardOf",
        "boxes.length === 1",
        r"/\bcbql\.\d+\b/i",
        "Cảnh báo người được giao là CBQL",
        "1 Mầm non + 1 Tiểu học + 1 THCS",
    ]

    missing = [item for item in required if item not in text]
    if missing:
        raise RuntimeError(
            "Kiểm tra sau cài chưa đạt, thiếu: " + " | ".join(missing)
        )


def main() -> None:
    print("=" * 84)
    print("BÀI 13B-10 V3.13B.3 - SỬA CẢNH BÁO NHẦM CBQL")
    print("=" * 84)
    print("Nguyên nhân:")
    print(" - Bản trước leo DOM lên quá cao.")
    print(" - Khi chọn 1 giáo viên, vùng cha vẫn chứa tên các CBQL khác.")
    print(" - Vì vậy hệ thống hiểu nhầm người đang chọn là CBQL.")
    print()
    print("V3.13B.3:")
    print(" - Chỉ đọc đúng card của checkbox đang được chọn.")
    print(" - Card phải chứa đúng 1 checkbox.")
    print(" - Chỉ cảnh báo nếu chính card đó có username cbql.*.")
    print(" - Không sửa database, route, tổ 3 cấp hay nghiệp vụ giao phiếu.")

    if not TEMPLATE.exists():
        raise RuntimeError(f"Không tìm thấy template: {TEMPLATE}")

    EXPORTS.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = EXPORTS / f"backup_bai_13b_10_v3_13b3_{stamp}"
    dst = backup / TEMPLATE.relative_to(PROJECT)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(TEMPLATE, dst)

    print("Backup:", backup)

    try:
        original = read_text(TEMPLATE)
        patched = patch_template(original)
        write_text(TEMPLATE, patched)
        verify(read_text(TEMPLATE))

        print()
        print("KIỂM TRA SAU CÀI:")
        print(" - Đã bỏ block cảnh báo CBQL cũ: OK")
        print(" - Chỉ nhận diện card của người đang tích: OK")
        print(" - Giáo viên gv.* không bị cảnh báo nhầm: OK")
        print(" - CBQL cbql.* vẫn được cảnh báo: OK")
        print()
        print("CÀI ĐẶT BÀI 13B-10 V3.13B.3 THÀNH CÔNG")

    except Exception:
        print()
        print("CÓ LỖI - ĐANG KHÔI PHỤC TEMPLATE...")
        shutil.copy2(dst, TEMPLATE)
        print("ĐÃ KHÔI PHỤC TEMPLATE TRƯỚC V3.13B.3.")
        print("Backup:", backup)
        raise


if __name__ == "__main__":
    main()
