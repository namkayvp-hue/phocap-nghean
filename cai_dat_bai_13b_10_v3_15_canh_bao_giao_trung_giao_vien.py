from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path

PROJECT = Path(r"C:\PhoCap")
TEMPLATE = PROJECT / "app" / "templates" / "surveys" / "bulk_assignments.html"
EXPORTS = PROJECT / "exports"

MARK_START = "{# === BAI_13B_10_V3_15_DUPLICATE_ASSIGN_WARNING_START === #}"
MARK_END = "{# === BAI_13B_10_V3_15_DUPLICATE_ASSIGN_WARNING_END === #}"
DATA_ATTR = "data-assigned-user-ids"

JS_BLOCK = r'''
{# === BAI_13B_10_V3_15_DUPLICATE_ASSIGN_WARNING_START === #}
<script>
(function () {
    "use strict";

    if (!window.location.pathname.includes("/giao-phieu-giao-vien")) {
        return;
    }

    function selectedMode() {
        const radio = document.querySelector('input[name="mode"]:checked');
        return radio ? String(radio.value || "").toLowerCase() : "replace";
    }

    function selectedInvestigatorIds() {
        return new Set(
            Array.from(
                document.querySelectorAll(
                    'input[name="investigator_ids"]:checked'
                )
            )
            .map(function (item) {
                return String(item.value || "").trim();
            })
            .filter(Boolean)
        );
    }

    function selectedFormCheckboxes() {
        return Array.from(
            document.querySelectorAll('.form-checkbox:checked')
        );
    }

    function assignedIdsOfForm(checkbox) {
        const raw = String(
            checkbox.getAttribute("data-assigned-user-ids") || ""
        );

        return new Set(
            raw.split(",")
                .map(function (item) { return item.trim(); })
                .filter(Boolean)
        );
    }

    function formLabel(checkbox) {
        const row = checkbox.closest("tr");
        if (!row) {
            return "Phiếu #" + String(checkbox.value || "");
        }

        const code = row.querySelector(".code");
        if (code && (code.textContent || "").trim()) {
            return (code.textContent || "").trim();
        }

        return "Phiếu #" + String(checkbox.value || "");
    }

    function candidateLabelById(userId) {
        const checkbox = document.querySelector(
            'input[name="investigator_ids"][value="' +
            String(userId).replace(/"/g, '\\"') +
            '"]'
        );

        if (!checkbox) {
            return "Tài khoản #" + userId;
        }

        const candidate = checkbox.closest(".candidate");
        if (!candidate) {
            return "Tài khoản #" + userId;
        }

        const nameNode = candidate.querySelector(".candidate-name");
        const metaNode = candidate.querySelector(".candidate-meta");

        const name = nameNode
            ? (nameNode.textContent || "").replace(/\s+/g, " ").trim()
            : "";
        const meta = metaNode
            ? (metaNode.textContent || "").replace(/\s+/g, " ").trim()
            : "";

        if (name && meta) return name + " — " + meta;
        return name || meta || ("Tài khoản #" + userId);
    }

    function findDuplicateAssignments() {
        const selectedUsers = selectedInvestigatorIds();
        const forms = selectedFormCheckboxes();
        const duplicates = [];

        if (!selectedUsers.size || !forms.length) {
            return duplicates;
        }

        forms.forEach(function (formCheckbox) {
            const current = assignedIdsOfForm(formCheckbox);

            selectedUsers.forEach(function (userId) {
                if (current.has(userId)) {
                    duplicates.push({
                        formId: String(formCheckbox.value || ""),
                        formLabel: formLabel(formCheckbox),
                        userId: userId,
                        userLabel: candidateLabelById(userId)
                    });
                }
            });
        });

        return duplicates;
    }

    const form = document.getElementById("bulk-form");
    if (!form) {
        return;
    }

    /*
     * Capture phase:
     * chạy trước listener xác nhận chung đã có sẵn.
     * Chỉ cảnh báo khi CHÍNH giáo viên được chọn đã có trên CHÍNH phiếu
     * được chọn. Giáo viên có các phiếu khác vẫn giao bình thường.
     */
    form.addEventListener("submit", function (event) {
        const mode = selectedMode();

        if (mode === "clear") {
            return;
        }

        const duplicates = findDuplicateAssignments();

        if (!duplicates.length) {
            return;
        }

        const shown = duplicates.slice(0, 8).map(function (item) {
            return "• " + item.formLabel + ": " + item.userLabel;
        });

        if (duplicates.length > 8) {
            shown.push(
                "• ... và " + (duplicates.length - 8) +
                " trường hợp trùng khác"
            );
        }

        const ok = window.confirm(
            "CẢNH BÁO: Có phiếu đã được giao cho đúng người này rồi.\n\n" +
            shown.join("\n") +
            "\n\nNếu tiếp tục, hệ thống sẽ thực hiện lại thao tác phân công " +
            "theo chế độ bạn đang chọn và ghi nhật ký mới.\n\n" +
            "Bạn có chắc chắn muốn tiếp tục?"
        );

        if (!ok) {
            event.preventDefault();
            event.stopImmediatePropagation();
            event.stopPropagation();
            return false;
        }
    }, true);
})();
</script>
{# === BAI_13B_10_V3_15_DUPLICATE_ASSIGN_WARNING_END === #}
'''


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def backup_file() -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = EXPORTS / f"backup_bai_13b_10_v3_15_{stamp}"
    dst = backup / TEMPLATE.relative_to(PROJECT)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(TEMPLATE, dst)
    return backup


def restore(backup: Path) -> None:
    src = backup / TEMPLATE.relative_to(PROJECT)
    if src.exists():
        shutil.copy2(src, TEMPLATE)


def remove_old_block(text: str) -> str:
    while MARK_START in text and MARK_END in text:
        a = text.index(MARK_START)
        b = text.index(MARK_END, a) + len(MARK_END)
        text = text[:a] + text[b:]
    return text


def patch_form_checkbox(text: str) -> str:
    if DATA_ATTR in text:
        return text

    pattern = re.compile(
        r'''(<input\b(?=[^>]*\bclass\s*=\s*["'][^"']*\bform-checkbox\b[^"']*["'])
                   (?=[^>]*\bname\s*=\s*["']survey_form_ids["'])
                   (?=[^>]*\bvalue\s*=\s*["']\{\{\s*phieu\.id\s*\}\}["'])
                   [^>]*)(>)''',
        re.I | re.S | re.X,
    )

    match = pattern.search(text)
    if not match:
        raise RuntimeError(
            "Không tìm thấy checkbox survey_form_ids/form-checkbox "
            "theo cấu trúc hiện tại. Dừng an toàn, không sửa source."
        )

    original_tag = match.group(1)
    attr = r'''
                                            data-assigned-user-ids="{% for item in assigned %}{{ item.user_id }}{% if not loop.last %},{% endif %}{% endfor %}"'''

    new_tag = original_tag.rstrip() + attr
    return text[:match.start()] + new_tag + match.group(2) + text[match.end():]


def insert_js(text: str) -> str:
    text = remove_old_block(text)

    if "</body>" in text:
        return text.replace("</body>", JS_BLOCK + "\n</body>", 1)

    endblock = text.rfind("{% endblock %}")
    if endblock >= 0:
        return text[:endblock] + JS_BLOCK + "\n" + text[endblock:]

    return text.rstrip() + "\n\n" + JS_BLOCK + "\n"


def verify(text: str) -> None:
    required = [
        DATA_ATTR,
        "{% for item in assigned %}{{ item.user_id }}",
        MARK_START,
        MARK_END,
        "findDuplicateAssignments",
        "Có phiếu đã được giao cho đúng người này rồi",
        'form.addEventListener("submit"',
        "}, true);",
        'input[name="investigator_ids"]:checked',
        ".form-checkbox:checked",
    ]

    missing = [item for item in required if item not in text]
    if missing:
        raise RuntimeError(
            "Kiểm tra sau cài chưa đạt, thiếu: " + " | ".join(missing)
        )


def main() -> None:
    print("=" * 88)
    print("BÀI 13B-10 V3.15 - CẢNH BÁO GIAO TRÙNG GIÁO VIÊN TRÊN CÙNG PHIẾU")
    print("=" * 88)
    print("Nguyên tắc:")
    print(" - Chỉ cảnh báo khi giáo viên đang chọn ĐÃ CÓ trên chính phiếu đang chọn.")
    print(" - Giáo viên đã có các phiếu KHÁC vẫn được giao bình thường.")
    print(" - Không chặn cứng; người dùng có thể Hủy hoặc xác nhận tiếp tục.")
    print(" - Nếu tiếp tục, luồng V4 hiện tại vẫn xử lý và ghi nhật ký như cũ.")
    print(" - Không sửa database, route, tổ 3 cấp, dữ liệu hộ hay Đội ngũ.")
    print()

    if not TEMPLATE.exists():
        raise RuntimeError(f"Không tìm thấy template: {TEMPLATE}")

    EXPORTS.mkdir(parents=True, exist_ok=True)
    backup = backup_file()
    print("Backup:", backup)

    try:
        original = read_text(TEMPLATE)
        patched = patch_form_checkbox(original)
        patched = insert_js(patched)
        write_text(TEMPLATE, patched)

        verify(read_text(TEMPLATE))

        print()
        print("KIỂM TRA SAU CÀI:")
        print(" - Mỗi checkbox phiếu mang danh sách user_id đang được giao: OK")
        print(" - So sánh đúng phiếu + đúng người trước khi submit: OK")
        print(" - Cảnh báo chạy ở capture phase trước xác nhận chung: OK")
        print()
        print("CÀI ĐẶT BÀI 13B-10 V3.15 THÀNH CÔNG")
        print("Khởi động lại Uvicorn và Ctrl+F5.")

    except Exception:
        print()
        print("CÓ LỖI - ĐANG KHÔI PHỤC TEMPLATE...")
        restore(backup)
        print("ĐÃ KHÔI PHỤC TEMPLATE TRƯỚC V3.15.")
        print("Backup:", backup)
        raise


if __name__ == "__main__":
    main()
