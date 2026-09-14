from __future__ import annotations

import os
import re
import shutil
import traceback
from datetime import datetime
from pathlib import Path

PROJECT = Path(os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")).resolve()
TARGET = PROJECT / "app" / "templates" / "surveys" / "households.html"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = PROJECT / "exports" / f"backup_source_bai_13b_11_10_2_{STAMP}"

MARK_DESKTOP_START = "{# === BAI_13B_11_10_2_DESKTOP_FULL_TEAM_START === #}"
MARK_DESKTOP_END = "{# === BAI_13B_11_10_2_DESKTOP_FULL_TEAM_END === #}"
MARK_MOBILE_START = "{# === BAI_13B_11_10_2_MOBILE_FULL_TEAM_START === #}"
MARK_MOBILE_END = "{# === BAI_13B_11_10_2_MOBILE_FULL_TEAM_END === #}"

NEW_MOBILE_BLOCK = '<strong>Người điều tra</strong>\n                                {# === BAI_13B_11_10_2_MOBILE_FULL_TEAM_START === #}\n                                {% if assigned_people %}\n                                    {% for item in assigned_people %}\n                                        <div class="investigator-name">\n                                            {% if item.is_primary %}★ {% endif %}\n                                            {{ item.full_name }}\n                                        </div>\n                                        <div class="small-muted">\n                                            {{ item.role_name }}\n                                            {% if item.school_name %}\n                                                · {{ item.school_name }}\n                                            {% endif %}\n                                        </div>\n                                    {% endfor %}\n                                {% else %}\n                                    Chưa phân công\n                                {% endif %}\n                                {# === BAI_13B_11_10_2_MOBILE_FULL_TEAM_END === #}'


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


def patch_desktop(text: str) -> str:
    if MARK_DESKTOP_START in text:
        print(" - Khối desktop đã sửa trước đó.")
        return text

    pattern_loop = re.compile(
        r"{%\s*for\s+item\s+in\s+assigned_people\s*\[\s*:\s*2\s*\]\s*%}"
    )

    text, count_loop = pattern_loop.subn(
        MARK_DESKTOP_START + "\n" + "{% for item in assigned_people %}",
        text,
        count=1,
    )

    if count_loop != 1:
        raise RuntimeError(
            "Không tìm thấy đúng vòng lặp "
            "'for item in assigned_people[:2]'."
        )

    pattern_extra = re.compile(
        r"""
        {%-?\s*if\s+assigned_people\s*\|\s*length\s*>\s*2\s*-?%}
        .*?
        \+\s*{{\s*assigned_people\s*\|\s*length\s*-\s*2\s*}}
        .*?
        người\s+khác
        .*?
        {%-?\s*endif\s*-?%}
        """,
        flags=re.IGNORECASE | re.DOTALL | re.VERBOSE,
    )

    text, count_extra = pattern_extra.subn(
        MARK_DESKTOP_END,
        text,
        count=1,
    )

    if count_extra != 1:
        raise RuntimeError(
            "Không tìm thấy đúng khối '+N người khác' của bảng desktop."
        )

    return text


def patch_mobile(text: str) -> str:
    if MARK_MOBILE_START in text:
        print(" - Khối mobile đã sửa trước đó.")
        return text

    pattern = re.compile(
        r"""
        <strong>Người\s+điều\s+tra</strong>
        (?P<body>
            \s*
            {%-?\s*if\s+assigned_people\s*-?%}
            .*?
            {%-?\s*else\s*-?%}
            \s*Chưa\s+phân\s+công\s*
            {%-?\s*endif\s*-?%}
        )
        """,
        flags=re.IGNORECASE | re.DOTALL | re.VERBOSE,
    )

    match = pattern.search(text)
    if match is None:
        raise RuntimeError(
            "Không tìm thấy đúng khối Người điều tra của thẻ mobile."
        )

    return text[:match.start()] + NEW_MOBILE_BLOCK + text[match.end():]


def verify(text: str) -> None:
    checks = [
        MARK_DESKTOP_START,
        MARK_DESKTOP_END,
        MARK_MOBILE_START,
        MARK_MOBILE_END,
        "{% for item in assigned_people %}",
    ]
    for marker in checks:
        if marker not in text:
            raise RuntimeError(f"Thiếu marker sau cài: {marker}")

    if re.search(r"assigned_people\s*\[\s*:\s*2\s*\]", text):
        raise RuntimeError("Vẫn còn giới hạn assigned_people[:2].")

    if re.search(r"assigned_people\s*\|\s*length\s*-\s*2", text):
        raise RuntimeError(
            "Vẫn còn phép tính '+N người khác' của desktop."
        )

    if re.search(r"assigned_people\s*\|\s*length\s*-\s*1", text):
        raise RuntimeError(
            "Vẫn còn phép tính 'và N người khác' của mobile."
        )

    try:
        from jinja2 import Environment
        Environment().parse(text)
    except Exception as exc:
        raise RuntimeError(f"Jinja parse không đạt: {exc}") from exc


def main() -> int:
    print("=" * 112)
    print(
        "BÀI 13B-11.10.2 - HIỂN THỊ ĐỦ 3 THÀNH VIÊN "
        "TỔ ĐIỀU TRA TRÊN DANH SÁCH HỘ"
    )
    print("=" * 112)
    print()
    print("ĐÃ XÁC ĐỊNH ĐÚNG SOURCE:")
    print(" - app/templates/surveys/households.html")
    print(" - Desktop đang dùng assigned_people[:2].")
    print(" - Mobile đang dùng người đầu tiên + N người khác.")
    print()
    print("SAU KHI CÀI:")
    print(" - Desktop: hiện toàn bộ 3 thành viên.")
    print(" - Mobile: hiện toàn bộ 3 thành viên.")
    print(" - Không còn '+1 người khác'.")
    print(" - Không còn 'và 2 người khác'.")
    print()
    print("KHÔNG THAY ĐỔI:")
    print(" - Không sửa database.")
    print(" - Không sửa router.")
    print(" - Không đổi phân công.")
    print(" - Không đổi người chính/phụ.")
    print(" - Không tạo trạng thái hoàn thành riêng từng giáo viên.")
    print()

    if not TARGET.exists():
        raise RuntimeError(f"Không tìm thấy: {TARGET}")

    BACKUP.mkdir(parents=True, exist_ok=False)
    backup_source()
    print("Backup source:", BACKUP)

    try:
        before = read_text(TARGET)
        after = patch_desktop(before)
        after = patch_mobile(after)

        verify(after)
        write_text(TARGET, after)

        print()
        print("KIỂM TRA SAU CÀI:")
        print(" - Desktop bỏ [:2]: OK")
        print(" - Desktop bỏ '+N người khác': OK")
        print(" - Mobile hiện đủ danh sách: OK")
        print(" - Mobile bỏ 'và N người khác': OK")
        print(" - Jinja parse: OK")
        print(" - Database: KHÔNG THAY ĐỔI")
        print()
        print("CÀI ĐẶT BÀI 13B-11.10.2 THÀNH CÔNG")
        return 0

    except Exception:
        traceback.print_exc()
        print()
        print("CÓ LỖI - ĐANG KHÔI PHỤC households.html...")
        restore_source()
        print("ĐÃ KHÔI PHỤC SOURCE.")
        print("Database không bị thay đổi.")
        print("Backup:", BACKUP)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
