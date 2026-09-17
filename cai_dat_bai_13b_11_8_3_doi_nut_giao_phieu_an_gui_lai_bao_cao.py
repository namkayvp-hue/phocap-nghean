from __future__ import annotations

import os
import re
import shutil
import traceback
from datetime import datetime
from pathlib import Path

PROJECT = Path(os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")).resolve()
TARGET = PROJECT / "app" / "templates" / "surveys" / "bulk_assignments.html"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = PROJECT / "exports" / f"backup_source_bai_13b_11_8_3_{STAMP}"

MARK_BUTTON_START = "{# === BAI_13B_11_8_3_BUTTON_LABEL_START === #}"
MARK_BUTTON_END = "{# === BAI_13B_11_8_3_BUTTON_LABEL_END === #}"
MARK_HIDE_START = "{# === BAI_13B_11_8_3_HIDE_RESUBMIT_START === #}"
MARK_HIDE_END = "{# === BAI_13B_11_8_3_HIDE_RESUBMIT_END === #}"


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


def patch_button_label(text: str) -> str:
    if MARK_BUTTON_START in text:
        print(" - Nhãn nút đã được sửa trước đó.")
        return text

    button_pattern = re.compile(
        r"(<button\b[^>]*>)(.*?)(</button>)",
        re.IGNORECASE | re.DOTALL,
    )

    matches = list(button_pattern.finditer(text))
    candidates = []

    for match in matches:
        inner = match.group(2)
        visible = re.sub(r"<[^>]+>", " ", inner)
        visible = re.sub(r"\s+", " ", visible).strip()

        if re.search(r"\bGiao\s+phiếu\b", visible, re.IGNORECASE):
            candidates.append(match)

    if not candidates:
        raise RuntimeError(
            "Không tìm thấy nút có nhãn 'Giao phiếu' trong bulk_assignments.html."
        )

    # Ưu tiên nút submit / primary; nếu chỉ có 1 ứng viên thì dùng ứng viên đó.
    selected = None
    for match in candidates:
        opening = match.group(1).lower()
        if 'type="submit"' in opening or "type='submit'" in opening or "button-primary" in opening:
            selected = match
            break

    if selected is None:
        if len(candidates) != 1:
            raise RuntimeError(
                f"Tìm thấy {len(candidates)} nút 'Giao phiếu', không thể chọn an toàn."
            )
        selected = candidates[0]

    inner = selected.group(2)

    replacement_label = (
        MARK_BUTTON_START
        + "\n"
        + "{% if assignment_level == 'teacher' %}"
        + "Giao phiếu / Gửi báo cáo xã, phường"
        + "{% else %}"
        + "Giao phiếu"
        + "{% endif %}"
        + "\n"
        + MARK_BUTTON_END
    )

    new_inner, count = re.subn(
        r"Giao\s+phiếu",
        replacement_label,
        inner,
        count=1,
        flags=re.IGNORECASE,
    )

    if count != 1:
        raise RuntimeError("Không thay được đúng nhãn nút Giao phiếu.")

    return (
        text[: selected.start()]
        + selected.group(1)
        + new_inner
        + selected.group(3)
        + text[selected.end() :]
    )


def hide_resubmit_link(text: str) -> str:
    if MARK_HIDE_START in text:
        print(" - Nút Gửi lại báo cáo đã được ẩn trước đó.")
        return text

    anchor_pattern = re.compile(
        r"""
        <a\b
        (?=[^>]*href\s*=\s*["']?/dieu-tra/\{\{\s*batch\.id\s*\}\}/phan-cong-truong["']?)
        [^>]*>
        .*?
        Gửi\s+lại\s+báo\s+cáo\s+cho\s+xã/phường
        .*?
        </a>
        """,
        re.IGNORECASE | re.DOTALL | re.VERBOSE,
    )

    match = anchor_pattern.search(text)

    if match is None:
        # Fallback: tìm thẻ <a> chứa đúng cụm chữ, không phụ thuộc thứ tự thuộc tính.
        generic_anchor = re.compile(
            r"<a\b[^>]*>.*?Gửi\s+lại\s+báo\s+cáo\s+cho\s+xã/phường.*?</a>",
            re.IGNORECASE | re.DOTALL,
        )
        match = generic_anchor.search(text)

    if match is None:
        # Nếu chữ đã không còn thì coi như đạt mục tiêu.
        if "Gửi lại báo cáo cho xã/phường" not in text:
            print(" - Không còn nút Gửi lại báo cáo; bỏ qua.")
            return text
        raise RuntimeError("Không xác định được khối nút Gửi lại báo cáo để ẩn.")

    hidden = (
        MARK_HIDE_START
        + "\n"
        + "{# Nút riêng đã ẩn vì thao tác Giao phiếu của Trường "
          "đã đồng thời gửi báo cáo xã/phường. #}"
        + "\n"
        + MARK_HIDE_END
    )

    return text[: match.start()] + hidden + text[match.end() :]


def verify(text: str) -> None:
    if "Giao phiếu / Gửi báo cáo xã, phường" not in text:
        raise RuntimeError("Chưa có nhãn nút mới.")

    if MARK_BUTTON_START not in text or MARK_BUTTON_END not in text:
        raise RuntimeError("Thiếu marker nhãn nút.")

    if MARK_HIDE_START not in text or MARK_HIDE_END not in text:
        raise RuntimeError("Thiếu marker ẩn nút gửi lại.")

    # Cụm chữ cũ không được còn hiển thị trong thẻ <a>.
    visible_resubmit = re.search(
        r"<a\b[^>]*>.*?Gửi\s+lại\s+báo\s+cáo\s+cho\s+xã/phường.*?</a>",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    if visible_resubmit:
        raise RuntimeError("Nút Gửi lại báo cáo vẫn còn hiển thị.")

    # Kiểm tra cú pháp Jinja.
    try:
        from jinja2 import Environment
        Environment().parse(text)
    except Exception as exc:
        raise RuntimeError(f"Jinja parse không đạt: {exc}") from exc


def main() -> int:
    print("=" * 108)
    print("BÀI 13B-11.8.3 - ĐỔI TÊN NÚT GIAO PHIẾU VÀ ẨN NÚT GỬI LẠI BÁO CÁO")
    print("=" * 108)
    print()
    print("THAY ĐỔI:")
    print(" - Trường: 'Giao phiếu' -> 'Giao phiếu / Gửi báo cáo xã, phường'.")
    print(" - Ẩn nút riêng 'Gửi lại báo cáo cho xã/phường'.")
    print(" - Cấp Xã vẫn giữ nhãn 'Giao phiếu' như cũ.")
    print()
    print("KHÔNG THAY ĐỔI:")
    print(" - Không sửa router.")
    print(" - Không sửa quyền.")
    print(" - Không sửa database.")
    print(" - Không xóa route gửi báo cáo cũ.")
    print()

    if not TARGET.exists():
        raise RuntimeError(f"Không tìm thấy: {TARGET}")

    BACKUP.mkdir(parents=True, exist_ok=False)
    backup_source()
    print("Backup source:", BACKUP)

    try:
        text = read_text(TARGET)
        text = patch_button_label(text)
        text = hide_resubmit_link(text)
        verify(text)
        write_text(TARGET, text)

        print()
        print("KIỂM TRA SAU CÀI:")
        print(" - Nhãn nút Trường: OK")
        print(" - Nút Gửi lại báo cáo: ĐÃ ẨN")
        print(" - Jinja parse: OK")
        print(" - Database: KHÔNG THAY ĐỔI")
        print()
        print("CÀI ĐẶT BÀI 13B-11.8.3 THÀNH CÔNG")
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
