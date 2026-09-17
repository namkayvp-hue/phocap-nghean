from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path

PROJECT = Path(r"C:\PhoCap")
APP = PROJECT / "app"
MENU = APP / "templates" / "partials" / "dropdown_menu_v1.html"
SCHOOL_LIST = APP / "templates" / "schools" / "list.html"
EXPORTS = PROJECT / "exports"

MENU_MARK_START = "{# === BAI_13B_10_V3_16_HIDE_WORKING_BATCH_START === #}"
MENU_MARK_END = "{# === BAI_13B_10_V3_16_HIDE_WORKING_BATCH_END === #}"
SCHOOL_MARK = "BAI_13B_10_V3_16_COMMUNE_SCHOOL_FULL_WIDTH"

COMMUNE_CSS = r"""
{% if not co_quyen_quan_ly %}
<style>
/* === BAI_13B_10_V3_16_COMMUNE_SCHOOL_FULL_WIDTH ===
   Tài khoản Xã/phường chỉ có bảng danh sách, không có form thêm trường.
   Cho bảng chiếm toàn bộ chiều ngang thay vì giữ cột hẹp của admin-grid.
*/
.admin-container{
    max-width: 1400px !important;
    width: calc(100% - 32px) !important;
}
.admin-grid{
    display: block !important;
    width: 100% !important;
}
.admin-grid > .panel-wide{
    width: 100% !important;
    max-width: none !important;
    min-width: 0 !important;
    grid-column: 1 / -1 !important;
}
.table-wrapper{
    width: 100% !important;
    max-width: 100% !important;
    overflow-x: auto !important;
}
.data-table{
    width: 100% !important;
    min-width: 1050px !important;
    table-layout: auto !important;
}
.data-table th,
.data-table td{
    vertical-align: top !important;
}
.data-table th:nth-child(1),
.data-table td:nth-child(1){
    width: 60px !important;
    min-width: 60px !important;
}
.data-table th:nth-child(2),
.data-table td:nth-child(2){
    width: 150px !important;
    min-width: 150px !important;
    white-space: nowrap !important;
}
.data-table th:nth-child(3),
.data-table td:nth-child(3){
    width: 34% !important;
    min-width: 300px !important;
    max-width: none !important;
    white-space: normal !important;
    overflow: visible !important;
    text-overflow: clip !important;
    overflow-wrap: anywhere !important;
    word-break: normal !important;
}
.data-table th:nth-child(4),
.data-table td:nth-child(4){
    min-width: 180px !important;
    white-space: normal !important;
    overflow-wrap: anywhere !important;
}
.data-table th:nth-child(5),
.data-table td:nth-child(5){
    min-width: 220px !important;
    white-space: normal !important;
    overflow-wrap: anywhere !important;
}
@media (max-width: 900px){
    .admin-container{
        width: calc(100% - 20px) !important;
    }
    .data-table{
        min-width: 950px !important;
    }
}
</style>
{% endif %}
"""


def read_text(path: Path) -> str:
    if not path.exists():
        raise RuntimeError(f"Không tìm thấy tệp bắt buộc: {path}")
    return path.read_text(encoding="utf-8-sig")


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def backup_files() -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = EXPORTS / f"backup_bai_13b_10_v3_16_{stamp}"

    for src in (MENU, SCHOOL_LIST):
        dst = backup / src.relative_to(PROJECT)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    return backup


def restore_files(backup: Path) -> None:
    for target in (MENU, SCHOOL_LIST):
        src = backup / target.relative_to(PROJECT)
        if src.exists():
            shutil.copy2(src, target)


def clear_cache() -> None:
    for cache in APP.rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(cache, ignore_errors=True)


def find_working_batch_fragment(line: str) -> str | None:
    if "Đợt đang làm việc:" not in line:
        return None

    dynamic = re.search(
        r"Đợt đang làm việc:\s*"
        r"\{%\s*if\s+pc_survey_batch_id\s*%\}\s*"
        r"#\s*\{\{\s*pc_survey_batch_id\s*\}\}\s*"
        r"\{%\s*else\s*%\}\s*"
        r"Chưa có đợt phù hợp\s*"
        r"\{%\s*endif\s*%\}",
        line,
        flags=re.I,
    )
    if dynamic:
        return dynamic.group(0)

    fixed = re.search(
        r"Đợt đang làm việc:\s*#\s*\d+",
        line,
        flags=re.I,
    )
    if fixed:
        return fixed.group(0)

    variable = re.search(
        r"Đợt đang làm việc:\s*#\s*\{\{\s*[^}]+\s*\}\}",
        line,
        flags=re.I,
    )
    if variable:
        return variable.group(0)

    return "Đợt đang làm việc:"


def patch_menu(text: str) -> tuple[str, str]:
    """Chỉ ẩn nhãn đợt ở Sở/Xã/Trường, giữ nguyên cơ chế batch phía sau."""

    if MENU_MARK_START in text and MENU_MARK_END in text:
        return text, "already_v316"

    lines = text.splitlines(keepends=True)

    for index, line in enumerate(lines):
        fragment = find_working_batch_fragment(line)
        if fragment is None:
            continue

        indent = line[: len(line) - len(line.lstrip())]
        newline = "\n" if line.endswith("\n") else ""

        wrapped = (
            indent + MENU_MARK_START + "\n"
            + indent + "{% if menu_role == 'GIAO_VIEN' %}\n"
            + line.rstrip("\n") + "\n"
            + indent + "{% endif %}\n"
            + indent + MENU_MARK_END + newline
        )

        lines[index] = wrapped
        return "".join(lines), "hide_for_so_xa_truong"

    raise RuntimeError(
        "Không tìm thấy dòng 'Đợt đang làm việc:' trong dropdown_menu_v1.html. "
        "Dừng an toàn để tránh sửa nhầm menu."
    )


def patch_school_list(text: str) -> tuple[str, str]:
    """Mở layout full-width V1.6 cho tài khoản Xã tại /truong."""

    if SCHOOL_MARK in text:
        return text, "already_v316"

    old_v16_marker = "BAI_13B_6_V1_6_HIEN_DAY_DU_TEN_TRUONG"

    if old_v16_marker in text:
        marker_pos = text.index(old_v16_marker)
        prefix = text[:marker_pos]

        candidates = list(
            re.finditer(r"\{%\s*if\s+cap_hoc\s*%\}", prefix, flags=re.I)
        )

        if candidates:
            match = candidates[-1]
            between = text[match.end():marker_pos]

            if len(between) < 500:
                text = (
                    text[:match.start()]
                    + "{% if cap_hoc or not co_quyen_quan_ly %}"
                    + text[match.end():]
                )
                text = text.replace(
                    old_v16_marker,
                    old_v16_marker + "\n   === " + SCHOOL_MARK,
                    1,
                )
                return text, "extend_existing_v16"

    anchor = '{% include "partials/dropdown_menu_v1.html" %}'
    if anchor not in text:
        anchor = "{% include 'partials/dropdown_menu_v1.html' %}"

    if anchor not in text:
        raise RuntimeError(
            "Không tìm thấy điểm chèn an toàn trong schools/list.html. "
            "Dừng và khôi phục tự động."
        )

    return (
        text.replace(anchor, COMMUNE_CSS + "\n" + anchor, 1),
        "inject_commune_css",
    )


def verify(menu_text: str, school_text: str) -> None:
    from jinja2 import Environment

    Environment().parse(menu_text)
    Environment().parse(school_text)

    for item in (
        MENU_MARK_START,
        MENU_MARK_END,
        "menu_role == 'GIAO_VIEN'",
        "Đợt đang làm việc:",
        "pc_survey_batch_id",
    ):
        if item not in menu_text:
            raise RuntimeError(f"Kiểm tra menu chưa đạt: thiếu {item}")

    if SCHOOL_MARK not in school_text:
        raise RuntimeError(
            "Kiểm tra schools/list.html chưa đạt: thiếu marker V3.16."
        )

    if not (
        "cap_hoc or not co_quyen_quan_ly" in school_text
        or "{% if not co_quyen_quan_ly %}" in school_text
    ):
        raise RuntimeError(
            "Chưa xác nhận được CSS full-width cho tài khoản Xã."
        )

    for item in (
        "grid-column: 1 / -1",
        "min-width: 300px",
        "overflow-wrap: anywhere",
    ):
        if item not in school_text:
            raise RuntimeError(
                f"Kiểm tra hiển thị danh mục trường chưa đạt: thiếu {item}"
            )


def main() -> None:
    print("=" * 100)
    print("BÀI 13B-10 V3.16 - GỌN MENU + HIỂN THỊ ĐẦY ĐỦ DANH MỤC TRƯỜNG CẤP XÃ")
    print("=" * 100)
    print()
    print("SỬA 1:")
    print(" - Bỏ hiển thị 'Đợt đang làm việc: #...' ở cấp Sở, Xã và Trường.")
    print(" - KHÔNG xóa pc_survey_batch_id; các link 2.2 -> 2.5 vẫn dùng đúng đợt.")
    print()
    print("SỬA 2:")
    print(" - Trang /truong của Xã hiển thị bảng gần toàn bộ chiều ngang.")
    print(" - Tên trường không còn bị cắt do panel quá hẹp.")
    print(" - Không thay đổi dữ liệu trường đang có.")
    print()
    print("KHÔNG SỬA database, route, quyền, phân công, tổ 3 cấp hoặc mobile.")
    print()

    for path in (MENU, SCHOOL_LIST):
        if not path.exists():
            raise RuntimeError(f"Không tìm thấy: {path}")

    EXPORTS.mkdir(parents=True, exist_ok=True)
    backup = backup_files()
    print("Backup:", backup)

    try:
        menu_before = read_text(MENU)
        school_before = read_text(SCHOOL_LIST)

        menu_after, menu_mode = patch_menu(menu_before)
        school_after, school_mode = patch_school_list(school_before)

        write_text(MENU, menu_after)
        write_text(SCHOOL_LIST, school_after)

        verify(read_text(MENU), read_text(SCHOOL_LIST))
        clear_cache()

        print()
        print("KẾT QUẢ:")
        print(" - Menu:", menu_mode)
        print(" - Danh mục trường:", school_mode)
        print(" - Jinja: OK")
        print()
        print("CÀI ĐẶT BÀI 13B-10 V3.16 THÀNH CÔNG")
        print("Khởi động lại Uvicorn và nhấn Ctrl+F5.")

    except Exception:
        print()
        print("CÓ LỖI - ĐANG KHÔI PHỤC 2 TEMPLATE...")
        restore_files(backup)
        clear_cache()
        print("ĐÃ KHÔI PHỤC SOURCE TRƯỚC V3.16.")
        print("Backup:", backup)
        raise


if __name__ == "__main__":
    main()
