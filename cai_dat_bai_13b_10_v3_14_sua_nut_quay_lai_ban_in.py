from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

PROJECT = Path(r"C:\PhoCap")
TEMPLATE = PROJECT / "app" / "templates" / "surveys" / "field_print.html"
EXPORTS = PROJECT / "exports"

MARK_START = "{# === BAI_13B_10_V3_14_PRINT_BACK_SCOPE_START === #}"
MARK_END = "{# === BAI_13B_10_V3_14_PRINT_BACK_SCOPE_END === #}"

OLD_ANCHOR = (
    '<a class="button" href="/dieu-tra/trung-tam-phieu?school_year_id='
    '{{ batch.school_year.id }}">← Trung tâm phiếu</a>'
)

NEW_BLOCK = r'''
{# === BAI_13B_10_V3_14_PRINT_BACK_SCOPE_START === #}
{% set print_role = (nguoi_dung.role_code or '')|upper %}
{% if print_role == 'TRUONG' %}
    <a class="button"
       href="/dieu-tra/{{ batch.id }}/giao-phieu-giao-vien">
        ← Giao phiếu cho giáo viên
    </a>
{% elif print_role == 'GIAO_VIEN' %}
    <a class="button"
       href="/dieu-tra/{{ batch.id }}/ho-dan">
        ← Danh sách hộ được giao
    </a>
{% else %}
    <a class="button"
       href="/dieu-tra/trung-tam-phieu?school_year_id={{ batch.school_year.id }}">
        ← Trung tâm phiếu
    </a>
{% endif %}
{# === BAI_13B_10_V3_14_PRINT_BACK_SCOPE_END === #}
'''


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def backup_file() -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = EXPORTS / f"backup_bai_13b_10_v3_14_{stamp}"
    dst = backup / TEMPLATE.relative_to(PROJECT)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(TEMPLATE, dst)
    return backup


def restore(backup: Path) -> None:
    src = backup / TEMPLATE.relative_to(PROJECT)
    if src.exists():
        shutil.copy2(src, TEMPLATE)


def remove_existing_block(text: str) -> str:
    while MARK_START in text and MARK_END in text:
        a = text.index(MARK_START)
        b = text.index(MARK_END, a) + len(MARK_END)
        text = text[:a] + OLD_ANCHOR + text[b:]
    return text


def patch_template(text: str) -> str:
    text = remove_existing_block(text)

    if OLD_ANCHOR in text:
        return text.replace(OLD_ANCHOR, NEW_BLOCK, 1)

    href = (
        '/dieu-tra/trung-tam-phieu?school_year_id='
        '{{ batch.school_year.id }}'
    )

    if href not in text or "← Trung tâm phiếu" not in text:
        raise RuntimeError(
            "Không tìm thấy nút '← Trung tâm phiếu' trong field_print.html "
            "theo cấu trúc hiện tại. Source được giữ nguyên."
        )

    href_pos = text.index(href)
    start = text.rfind("<a", 0, href_pos)
    end = text.find("</a>", href_pos)

    if start < 0 or end < 0:
        raise RuntimeError(
            "Không xác định được thẻ <a> của nút Trung tâm phiếu."
        )

    end += len("</a>")
    return text[:start] + NEW_BLOCK + text[end:]


def verify(text: str) -> None:
    required = [
        MARK_START,
        MARK_END,
        "print_role == 'TRUONG'",
        "/dieu-tra/{{ batch.id }}/giao-phieu-giao-vien",
        "← Giao phiếu cho giáo viên",
        "print_role == 'GIAO_VIEN'",
        "/dieu-tra/{{ batch.id }}/ho-dan",
        "← Danh sách hộ được giao",
        "/dieu-tra/trung-tam-phieu?school_year_id={{ batch.school_year.id }}",
        "← Trung tâm phiếu",
    ]

    missing = [item for item in required if item not in text]
    if missing:
        raise RuntimeError(
            "Kiểm tra sau cài chưa đạt, thiếu: " + " | ".join(missing)
        )


def main() -> None:
    print("=" * 86)
    print("BÀI 13B-10 V3.14 - SỬA NÚT QUAY LẠI TRÊN BẢN IN PHIẾU")
    print("=" * 86)
    print("Nguyên nhân:")
    print(" - Bản in đang hard-code nút quay về /dieu-tra/trung-tam-phieu.")
    print(" - Trung tâm phiếu chỉ dành cho cấp được phép; tài khoản TRƯỜNG bị forbidden.")
    print()
    print("V3.14 chỉ đổi đích nút quay lại theo vai trò:")
    print(" - TRƯỜNG      -> Giao phiếu cho giáo viên của đúng đợt.")
    print(" - GIÁO_VIÊN   -> Danh sách hộ được giao của đúng đợt.")
    print(" - SỞ/XÃ/ADMIN -> Giữ nguyên Trung tâm phiếu.")
    print()
    print("KHÔNG mở rộng quyền Trung tâm phiếu.")
    print("KHÔNG sửa database, phân công, hộ dân, Đội ngũ hay bản in.")

    if not TEMPLATE.exists():
        raise RuntimeError(f"Không tìm thấy template: {TEMPLATE}")

    EXPORTS.mkdir(parents=True, exist_ok=True)
    backup = backup_file()
    print("Backup:", backup)

    try:
        original = read_text(TEMPLATE)
        patched = patch_template(original)
        write_text(TEMPLATE, patched)
        verify(read_text(TEMPLATE))

        print()
        print("KIỂM TRA SAU CÀI:")
        print(" - Nút quay lại cấp Trường: OK")
        print(" - Nút quay lại cấp Giáo viên: OK")
        print(" - Trung tâm phiếu Sở/Xã/Admin vẫn giữ: OK")
        print()
        print("CÀI ĐẶT BÀI 13B-10 V3.14 THÀNH CÔNG")
        print("Khởi động lại Uvicorn và Ctrl+F5.")

    except Exception:
        print()
        print("CÓ LỖI - ĐANG KHÔI PHỤC TEMPLATE...")
        restore(backup)
        print("ĐÃ KHÔI PHỤC TEMPLATE TRƯỚC V3.14.")
        print("Backup:", backup)
        raise


if __name__ == "__main__":
    main()
