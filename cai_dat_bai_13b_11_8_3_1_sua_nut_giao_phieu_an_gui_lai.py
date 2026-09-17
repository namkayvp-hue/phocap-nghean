from __future__ import annotations

import os
import shutil
import traceback
from datetime import datetime
from pathlib import Path

PROJECT = Path(os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")).resolve()
TARGET = PROJECT / "app" / "templates" / "surveys" / "bulk_assignments.html"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = PROJECT / "exports" / f"backup_source_bai_13b_11_8_3_1_{STAMP}"

MARK_START = "<!-- === BAI_13B_11_8_3_1_UI_START === -->"
MARK_END = "<!-- === BAI_13B_11_8_3_1_UI_END === -->"

BLOCK = r'''
<!-- === BAI_13B_11_8_3_1_UI_START === -->
<script>
(function () {
    function normalizeText(value) {
        return String(value || "")
            .replace(/\s+/g, " ")
            .trim()
            .toLowerCase();
    }

    function applySchoolTeacherAssignmentUi() {
        var path = String(window.location.pathname || "");

        if (!/\/dieu-tra\/\d+\/giao-phieu-giao-vien\/?$/.test(path)) {
            return;
        }

        var forms = Array.prototype.slice.call(document.querySelectorAll("form"));
        var assignmentForm = forms.find(function (form) {
            var action = form.getAttribute("action") || "";
            try {
                action = new URL(action, window.location.origin).pathname;
            } catch (e) {
            }

            return /\/dieu-tra\/\d+\/giao-phieu-giao-vien\/luu\/?$/.test(action);
        });

        if (assignmentForm) {
            var submitButton = assignmentForm.querySelector(
                'button[type="submit"], input[type="submit"]'
            );

            if (submitButton) {
                if (submitButton.tagName.toLowerCase() === "input") {
                    submitButton.value =
                        "Giao phiếu / Gửi báo cáo xã, phường";
                } else {
                    submitButton.textContent =
                        "📤 Giao phiếu / Gửi báo cáo xã, phường";
                }

                submitButton.setAttribute(
                    "title",
                    "Giao phiếu cho giáo viên và đồng thời gửi báo cáo xã/phường"
                );
            }
        }

        Array.prototype.slice
            .call(document.querySelectorAll("a, button"))
            .forEach(function (el) {
                var text = normalizeText(el.textContent || el.value);

                if (
                    text.indexOf("gửi lại báo cáo cho xã/phường") !== -1 ||
                    text.indexOf("gửi lại báo cáo cho phường/xã") !== -1
                ) {
                    el.style.display = "none";
                    el.setAttribute("aria-hidden", "true");
                }
            });
    }

    if (document.readyState === "loading") {
        document.addEventListener(
            "DOMContentLoaded",
            applySchoolTeacherAssignmentUi
        );
    } else {
        applySchoolTeacherAssignmentUi();
    }
})();
</script>
<!-- === BAI_13B_11_8_3_1_UI_END === -->
'''


def read_text(path: Path) -> str:
    if not path.exists():
        raise RuntimeError(f"Không tìm thấy tệp: {path}")
    return path.read_text(encoding="utf-8-sig")


def write_text(path: Path, value: str) -> None:
    path.write_text(value, encoding="utf-8")


def backup_source() -> None:
    dst = BACKUP / TARGET.relative_to(PROJECT)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(TARGET, dst)


def restore_source() -> None:
    src = BACKUP / TARGET.relative_to(PROJECT)
    if src.exists():
        shutil.copy2(src, TARGET)


def patch(text: str) -> str:
    if MARK_START in text:
        print(" - Bài 13B-11.8.3.1 đã có sẵn, không chèn lặp.")
        return text

    return text.rstrip() + "\n\n" + BLOCK.strip() + "\n"


def verify(text: str) -> None:
    required = [
        MARK_START,
        MARK_END,
        "giao-phieu-giao-vien",
        "giao-phieu-giao-vien\\/luu",
        "Giao phiếu / Gửi báo cáo xã, phường",
        "gửi lại báo cáo cho xã/phường",
    ]

    for marker in required:
        if marker not in text:
            raise RuntimeError(f"Thiếu marker sau cài: {marker}")

    if text.count(MARK_START) != 1 or text.count(MARK_END) != 1:
        raise RuntimeError("Khối Bài 13B-11.8.3.1 bị lặp.")

    try:
        from jinja2 import Environment
        Environment().parse(text)
    except Exception as exc:
        raise RuntimeError(f"Jinja parse không đạt: {exc}") from exc


def main() -> int:
    print("=" * 108)
    print("BÀI 13B-11.8.3.1 - SỬA CHẮC CHẮN NÚT GIAO PHIẾU / ẨN GỬI LẠI BÁO CÁO")
    print("=" * 108)
    print()
    print("THAY ĐỔI TRÊN TRANG TRƯỜNG GIAO PHIẾU CHO GIÁO VIÊN:")
    print(" - Nút: Giao phiếu / Gửi báo cáo xã, phường")
    print(" - Ẩn: Gửi lại báo cáo cho xã/phường")
    print()
    print("AN TOÀN:")
    print(" - Chỉ sửa app/templates/surveys/bulk_assignments.html")
    print(" - Không sửa router")
    print(" - Không sửa quyền")
    print(" - Không sửa database")
    print(" - Không ảnh hưởng trang Xã giao phiếu cho trường")
    print()

    if not TARGET.exists():
        raise RuntimeError(f"Không tìm thấy: {TARGET}")

    BACKUP.mkdir(parents=True, exist_ok=False)
    backup_source()
    print("Backup source:", BACKUP)

    try:
        before = read_text(TARGET)
        after = patch(before)
        verify(after)
        write_text(TARGET, after)

        print()
        print("KIỂM TRA SAU CÀI:")
        print(" - Khối giao diện: OK")
        print(" - Nút mới: OK")
        print(" - Ẩn nút gửi lại: OK")
        print(" - Jinja parse: OK")
        print(" - Database: KHÔNG THAY ĐỔI")
        print()
        print("CÀI ĐẶT BÀI 13B-11.8.3.1 THÀNH CÔNG")
        return 0

    except Exception:
        traceback.print_exc()
        print()
        print("CÓ LỖI - ĐANG KHÔI PHỤC TEMPLATE...")
        restore_source()
        print("ĐÃ KHÔI PHỤC SOURCE.")
        print("Database không bị thay đổi.")
        print("Backup:", BACKUP)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
