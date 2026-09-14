from __future__ import annotations

import os
import re
import shutil
import traceback
from datetime import datetime
from pathlib import Path

PROJECT = Path(
    os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")
).resolve()

APP = PROJECT / "app"
QUICK = APP / "templates" / "surveys" / "quick_entry.html"
YEAR = APP / "templates" / "surveys" / "year_records.html"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = (
    PROJECT
    / "exports"
    / f"backup_giao_vien_mobile_v1_9_1_{STAMP}"
)

QUICK_START_MARKER = "GV_MOBILE_V18_QUICK_START"
V18D_HEAD_MARKER = "GV_MOBILE_V18D_EDIT_HEAD_START"
V19_ACTION_START = "<!-- === GV_MOBILE_V19_YEAR_ACTIONS_START === -->"
V19_ACTION_END = "<!-- === GV_MOBILE_V19_YEAR_ACTIONS_END === -->"

BIRTH_MARKER_START = "<!-- === GV_MOBILE_V191_BIRTH_YEAR_START === -->"
BIRTH_MARKER_END = "<!-- === GV_MOBILE_V191_BIRTH_YEAR_END === -->"
QUICK_CSS_MARKER = "GV_MOBILE_V191_QUICK_CSS_START"
YEAR_CSS_MARKER = "GV_MOBILE_V191_AFTER_SAVE_CSS_START"
YEAR_ACTION_MARKER = "GV_MOBILE_V191_AFTER_SAVE_ACTIONS"

OLD_BODY = (
    '<body class="{% if nguoi_dung.role_code == \'GIAO_VIEN\' %}'
    'pc-gv-mobile-year-edit{% endif %}">'
)
NEW_BODY = (
    '<body class="{% if nguoi_dung.role_code == \'GIAO_VIEN\' %}'
    'pc-gv-mobile-year-edit'
    '{% if year_record_saved %} pc-gv-v191-saved{% endif %}'
    '{% endif %}">'
)

QUICK_CSS = r'''
        /* === GV_MOBILE_V191_QUICK_CSS_START === */
        .pc-gv-v191-birth {
            display: block;
            margin-top: 4px;
            color: #60758a;
            font-size: 13px;
            font-weight: 700;
            line-height: 1.25;
            white-space: nowrap;
        }

        @media (max-width: 760px) {
            .pc-gv-v191-birth {
                margin-top: 5px;
                color: #526b82;
                font-size: 13px;
                font-weight: 750;
            }
        }
        /* === GV_MOBILE_V191_QUICK_CSS_END === */
'''

BIRTH_HTML = r'''
                    <!-- === GV_MOBILE_V191_BIRTH_YEAR_START === -->
                    <span class="pc-gv-v191-birth">
                        Năm sinh:
                        {% if item.person.date_of_birth %}
                            {{ item.person.date_of_birth.year }}
                        {% else %}
                            —
                        {% endif %}
                    </span>
                    <!-- === GV_MOBILE_V191_BIRTH_YEAR_END === -->
'''

YEAR_CSS = r'''
        /* === GV_MOBILE_V191_AFTER_SAVE_CSS_START === */
        @media (max-width: 760px) {
            body.pc-gv-mobile-year-edit.pc-gv-v191-saved #year_record_form {
                display: none !important;
            }

            body.pc-gv-mobile-year-edit.pc-gv-v191-saved .pc-v19-after-save {
                margin: 0 0 4px !important;
                padding: 13px !important;
            }

            body.pc-gv-mobile-year-edit.pc-gv-v191-saved
            .pc-v19-after-save__title {
                margin-bottom: 11px !important;
                font-size: 17px;
                line-height: 1.35;
            }

            body.pc-gv-mobile-year-edit.pc-gv-v191-saved
            .pc-v19-after-save__actions {
                grid-template-columns: 1fr !important;
                gap: 9px !important;
            }

            body.pc-gv-mobile-year-edit.pc-gv-v191-saved
            .pc-v19-after-save__actions a {
                min-height: 52px;
                font-size: 16px;
            }
        }
        /* === GV_MOBILE_V191_AFTER_SAVE_CSS_END === */
'''

NEW_YEAR_ACTIONS = r'''<!-- === GV_MOBILE_V19_YEAR_ACTIONS_START === -->
    <!-- === GV_MOBILE_V191_AFTER_SAVE_ACTIONS_START === -->
    <section class="pc-v19-after-save">
        <p class="pc-v19-after-save__title">
            ✓ Đã lưu thông tin năm học của {{ person.full_name }}
        </p>

        <div class="pc-v19-after-save__actions">
            {% if next_person_url %}
            <a class="pc-v19-next" href="{{ next_person_url }}">
                Thành viên tiếp theo →
            </a>
            <a href="{{ quick_entry_url }}">
                ← Về Nhập nhanh
            </a>
            {% else %}
            <a class="pc-v19-next" href="{{ quick_entry_url }}">
                ✓ Về phiếu để hoàn thành hộ
            </a>
            <a href="{{ work_url }}">
                ← Trang làm việc
            </a>
            {% endif %}
        </div>
    </section>
    <!-- === GV_MOBILE_V191_AFTER_SAVE_ACTIONS_END === -->
    <!-- === GV_MOBILE_V19_YEAR_ACTIONS_END === -->'''


def read_text(path: Path) -> str:
    if not path.exists():
        raise RuntimeError(f"Không tìm thấy tệp bắt buộc: {path}")
    return path.read_text(encoding="utf-8-sig")


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def backup_file(path: Path) -> None:
    target = BACKUP / path.relative_to(PROJECT)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, target)


def restore_file(path: Path) -> None:
    source = BACKUP / path.relative_to(PROJECT)
    if source.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, path)


def clear_cache() -> None:
    for cache in APP.rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(cache, ignore_errors=True)


def insert_style_block(text: str, css_block: str, marker: str) -> str:
    if marker in text:
        return text

    if "</style>" in text:
        return text.replace(
            "</style>",
            css_block + "\n    </style>",
            1,
        )

    if "</head>" in text:
        return text.replace(
            "</head>",
            "<style>\n" + css_block + "\n</style>\n</head>",
            1,
        )

    raise RuntimeError("Không tìm thấy điểm chèn CSS an toàn.")


def patch_quick(text: str) -> str:
    required = [
        QUICK_START_MARKER,
        "pc-gv-v18-edit",
        "Sửa",
    ]
    for marker in required:
        if marker not in text:
            raise RuntimeError(
                "quick_entry.html không đúng nền Mobile V1.8/V1.8D. "
                f"Thiếu marker: {marker}"
            )

    text = insert_style_block(
        text,
        QUICK_CSS,
        QUICK_CSS_MARKER,
    )

    if BIRTH_MARKER_START in text:
        return text

    mobile_pos = text.find(QUICK_START_MARKER)
    if mobile_pos < 0:
        raise RuntimeError(
            "Không xác định được khối Nhập nhanh Mobile V1.8."
        )

    name_pattern = re.compile(
        r"\{\{\s*item\.person\.full_name\s*\}\}"
    )
    name_match = name_pattern.search(text, mobile_pos)

    if name_match is None:
        raise RuntimeError(
            "Không tìm thấy {{ item.person.full_name }} "
            "trong phần Nhập nhanh Mobile."
        )

    insert_pos = name_match.end()

    next_close_candidates = []
    for closing in ("</strong>", "</span>", "</div>", "</td>"):
        pos = text.find(closing, name_match.end())
        if pos >= 0 and pos - name_match.end() < 240:
            next_close_candidates.append((pos + len(closing), closing))

    if next_close_candidates:
        insert_pos = min(next_close_candidates, key=lambda x: x[0])[0]

    return (
        text[:insert_pos]
        + "\n"
        + BIRTH_HTML.rstrip()
        + text[insert_pos:]
    )


def replace_v19_after_save_actions(text: str) -> str:
    if YEAR_ACTION_MARKER in text:
        return text

    start = text.find(V19_ACTION_START)
    end = text.find(V19_ACTION_END, start + 1)

    if start < 0 or end < 0:
        raise RuntimeError(
            "Không tìm thấy khối GV_MOBILE_V19_YEAR_ACTIONS hiện tại. "
            "Dừng an toàn để không sửa sai màn hình sau khi lưu."
        )

    end += len(V19_ACTION_END)

    return (
        text[:start]
        + NEW_YEAR_ACTIONS
        + text[end:]
    )


def patch_year(text: str) -> str:
    required = [
        V18D_HEAD_MARKER,
        'id="year_record_form"',
        "pc-v19-after-save",
        V19_ACTION_START,
        V19_ACTION_END,
        "next_person_url",
        "quick_entry_url",
        "work_url",
    ]
    for marker in required:
        if marker not in text:
            raise RuntimeError(
                "year_records.html không đúng nền Mobile V1.8D + V1.9. "
                f"Thiếu marker: {marker}"
            )

    if "pc-gv-v191-saved" not in text:
        if OLD_BODY not in text:
            raise RuntimeError(
                "Không tìm thấy thẻ <body> Mobile V1.8D đúng cấu trúc hiện tại."
            )
        text = text.replace(OLD_BODY, NEW_BODY, 1)

    text = insert_style_block(
        text,
        YEAR_CSS,
        YEAR_CSS_MARKER,
    )

    text = replace_v19_after_save_actions(text)

    return text


def verify() -> None:
    quick = read_text(QUICK)
    year = read_text(YEAR)

    quick_required = [
        QUICK_START_MARKER,
        QUICK_CSS_MARKER,
        BIRTH_MARKER_START,
        BIRTH_MARKER_END,
        "Năm sinh:",
        "item.person.date_of_birth.year",
        "pc-gv-v18-edit",
    ]
    for marker in quick_required:
        if marker not in quick:
            raise RuntimeError(
                f"Kiểm tra quick_entry.html không đạt: {marker}"
            )

    if quick.count(BIRTH_MARKER_START) != 1:
        raise RuntimeError(
            "Năm sinh bị chèn lặp trong quick_entry.html."
        )

    year_required = [
        V18D_HEAD_MARKER,
        YEAR_CSS_MARKER,
        YEAR_ACTION_MARKER,
        "pc-gv-v191-saved",
        'id="year_record_form"',
        "Thành viên tiếp theo →",
        "← Về Nhập nhanh",
        "✓ Về phiếu để hoàn thành hộ",
        "← Trang làm việc",
        "{{ quick_entry_url }}",
        "{{ work_url }}",
    ]
    for marker in year_required:
        if marker not in year:
            raise RuntimeError(
                f"Kiểm tra year_records.html không đạt: {marker}"
            )

    from jinja2 import Environment, FileSystemLoader

    env = Environment(
        loader=FileSystemLoader(str(APP / "templates"))
    )
    env.get_template("surveys/quick_entry.html")
    env.get_template("surveys/year_records.html")


def main() -> int:
    print("=" * 100)
    print("GIÁO VIÊN MOBILE V1.9.1 - HOÀN THIỆN NHẬP NHANH")
    print("=" * 100)
    print()
    print("LÝ DO DÙNG SỐ V1.9.1:")
    print(" - Dự án đã có Mobile V1.9 trước đó (định danh/CCCD/chuyển thành viên).")
    print(" - Bản này nối tiếp V1.9, không ghi đè ý nghĩa phiên bản cũ.")
    print()
    print("V1.9.1 SẼ LÀM:")
    print(" 1. Nhập nhanh: thêm 'Năm sinh' ngay dưới tên từng thành viên.")
    print(" 2. Giữ nguyên Trường, Lớp, Sửa và Chấp nhận.")
    print(" 3. Sau khi Lưu năm học trên điện thoại: ẩn form dài phía dưới.")
    print(" 4. Còn thành viên: hiện 'Thành viên tiếp theo' + 'Về Nhập nhanh'.")
    print(" 5. Hết thành viên: hiện 'Về phiếu để hoàn thành hộ'.")
    print()
    print("KHÔNG THAY ĐỔI:")
    print(" - Database.")
    print(" - Router / logic lưu dữ liệu.")
    print(" - Phân công tổ điều tra 3 cấp.")
    print(" - Backup / Restore / Quản lý Backup.")
    print(" - Giao diện máy tính.")
    print(" - Các chức năng Thêm thành viên, Chấp nhận, Hoàn thành hiện có.")
    print()

    for path in (QUICK, YEAR):
        if not path.exists():
            raise RuntimeError(f"Không tìm thấy: {path}")

    quick_before = read_text(QUICK)
    year_before = read_text(YEAR)

    BACKUP.mkdir(parents=True, exist_ok=False)
    backup_file(QUICK)
    backup_file(YEAR)

    print("Backup source trước khi cài:", BACKUP)

    try:
        quick_after = patch_quick(quick_before)
        year_after = patch_year(year_before)

        write_text(QUICK, quick_after)
        write_text(YEAR, year_after)

        verify()
        clear_cache()

        print()
        print("KIỂM TRA SAU CÀI:")
        print(" - Jinja quick_entry.html: OK")
        print(" - Jinja year_records.html: OK")
        print(" - Năm sinh Mobile: OK")
        print(" - Không chèn lặp Năm sinh: OK")
        print(" - Ẩn form sau Lưu trên điện thoại: OK")
        print(" - Thành viên tiếp theo / Về Nhập nhanh: OK")
        print(" - Hết thành viên -> Về phiếu để hoàn thành hộ: OK")
        print()
        print("CÀI ĐẶT GIÁO VIÊN MOBILE V1.9.1 THÀNH CÔNG")
        print()
        print("BƯỚC KIỂM TRA:")
        print(" 1. Khởi động lại Uvicorn.")
        print(" 2. Điện thoại: tải lại trang / đăng nhập lại nếu cần.")
        print(" 3. Phiếu phân công -> Nhập nhanh.")
        print(" 4. Kiểm tra mỗi thành viên có Năm sinh.")
        print(" 5. Bấm Sửa một thành viên -> Lưu.")
        print(" 6. Sau Lưu, form dài không còn hiển thị trên điện thoại.")
        return 0

    except Exception:
        traceback.print_exc()
        print()
        print("CÓ LỖI - ĐANG KHÔI PHỤC SOURCE TRƯỚC V1.9.1...")
        restore_file(QUICK)
        restore_file(YEAR)
        clear_cache()
        print("ĐÃ KHÔI PHỤC SOURCE.")
        print("Backup source:", BACKUP)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
