# -*- coding: utf-8 -*-
from __future__ import annotations

import ast
import py_compile
import re
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

PROJECT = Path(r"C:\PhoCap")
APP = PROJECT / "app"
DB = PROJECT / "data" / "phocap.db"
EXPORTS = PROJECT / "exports"
HELPER = APP / "household_field_excel_v240.py"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = EXPORTS / f"backup_bai_13b_12_v2_4_1_1_{STAMP}"
DB_BACKUP = BACKUP / "phocap.db"
REPORT = EXPORTS / f"bao_cao_cai_bai_13b_12_v2_4_1_1_{STAMP}.txt"

MARKER = "BAI_13B_12_V2_4_1_1_CLEAN_FIELD_EXCEL"

NOTE_HELPERS = '\n# === BAI_13B_12_V2_4_1_1_CLEAN_FIELD_EXCEL_NOTES_START ===\n_TECHNICAL_NOTE_PREFIXES = (\n    "cấp/nhóm:",\n    "địa bàn trường:",\n    "tình trạng cư trú theo file:",\n    "cập nhật từ excel imp-",\n    "nhập từ excel imp-",\n)\n\n\ndef _split_notes(raw: Any) -> tuple[str, str]:\n    text = _text(raw)\n    if not text:\n        return "", ""\n\n    parts = [\n        item.strip()\n        for item in re.split(r"[;\\r\\n]+", text)\n        if item and item.strip()\n    ]\n    user_parts: list[str] = []\n    internal_parts: list[str] = []\n    for item in parts:\n        low = item.casefold()\n        if any(low.startswith(prefix) for prefix in _TECHNICAL_NOTE_PREFIXES):\n            internal_parts.append(item)\n        else:\n            user_parts.append(item)\n\n    return "; ".join(user_parts), "; ".join(internal_parts)\n\n\ndef _combine_notes(internal: Any, visible_user_note: Any) -> str:\n    internal_text = _text(internal)\n    user_text, _discarded = _split_notes(visible_user_note)\n    return "; ".join(\n        item for item in (user_text, internal_text) if item\n    )\n# === BAI_13B_12_V2_4_1_1_CLEAN_FIELD_EXCEL_NOTES_END ===\n\n\n'

NEW_HISTORY = '\ndef _history_rows(\n    tracking: Any,\n    spec: dict[str, Any],\n    tracking_row: int,\n) -> list[tuple[str, str]]:\n    """Năm hiện tại luôn hiện; năm cũ chỉ hiện khi thực sự có dữ liệu."""\n    block_start = int(spec.get("block_start") or 1)\n    current_col = int(spec.get("current_year_column") or 18)\n\n    values: list[tuple[str, str]] = []\n\n    current_label = (\n        spec.get("school_year_code")\n        or _year_label(tracking, block_start, current_col)\n    )\n    current_value = _text(\n        tracking.cell(tracking_row, current_col).value\n    )\n    values.append((str(current_label or ""), current_value))\n\n    for col in range(\n        current_col - 1,\n        max(11, current_col - 6),\n        -1,\n    ):\n        value = _text(tracking.cell(tracking_row, col).value)\n        if not value:\n            continue\n        label = _year_label(tracking, block_start, col)\n        values.append((label, value))\n        if len(values) >= 7:\n            break\n\n    while len(values) < 7:\n        values.append(("20__-20__", ""))\n\n    return values[:7]\n\n\n'


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def db_state() -> dict:
    con = sqlite3.connect(str(DB))
    try:
        result = {
            "integrity": str(
                con.execute("PRAGMA integrity_check").fetchone()[0]
            ),
            "fk_count": len(
                con.execute("PRAGMA foreign_key_check").fetchall()
            ),
        }
        for table in (
            "survey_forms",
            "survey_people",
            "survey_person_year_records",
        ):
            result[table] = int(
                con.execute(
                    f"SELECT COUNT(*) FROM {table}"
                ).fetchone()[0]
            )
        return result
    finally:
        con.close()


def backup_file(path: Path) -> None:
    target = BACKUP / path.relative_to(PROJECT)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, target)


def restore_file(path: Path) -> None:
    source = BACKUP / path.relative_to(PROJECT)
    if source.exists():
        shutil.copy2(source, path)


def backup_db() -> None:
    src = sqlite3.connect(str(DB))
    dst = sqlite3.connect(str(DB_BACKUP))
    try:
        src.backup(dst)
        dst.commit()
    finally:
        dst.close()
        src.close()


def restore_db() -> None:
    if not DB_BACKUP.exists():
        return
    src = sqlite3.connect(str(DB_BACKUP))
    dst = sqlite3.connect(str(DB))
    try:
        src.backup(dst)
        dst.commit()
    finally:
        dst.close()
        src.close()


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(
            f"{label}: tìm thấy {count} vị trí, mong đợi 1."
        )
    return source.replace(old, new, 1)


def patch_helper(source: str) -> str:
    if MARKER in source:
        return source

    required = (
        'FIELD_VERSION = "PCGDMN_FIELD_FORM_V240"',
        "def _history_rows(",
        "def _fill_person_slot(",
        "def sync_field_form_to_tracking(",
    )
    for token in required:
        if token not in source:
            raise RuntimeError("Thiếu nền V2.4.1: " + token)

    old_load = """    workbook = load_workbook(
        BytesIO(content)
    )
"""
    new_load = """    # === BAI_13B_12_V2_4_1_1_CLEAN_FIELD_EXCEL ===
    workbook = load_workbook(
        BytesIO(content),
        keep_links=False,
    )
    try:
        workbook._external_links = []
    except Exception:
        pass
"""
    source = replace_once(
        source,
        old_load,
        new_load,
        "Bỏ liên kết workbook ngoài",
    )

    anchor = "def _year_label("
    if anchor not in source:
        raise RuntimeError("Không tìm thấy vị trí chèn bộ lọc ghi chú.")
    source = source.replace(anchor, NOTE_HELPERS + anchor, 1)

    pattern = re.compile(
        r"def _history_rows\(\n.*?\n\ndef _fill_person_slot\(",
        flags=re.S,
    )
    match = pattern.search(source)
    if not match:
        raise RuntimeError("Không xác định được hàm _history_rows.")
    source = (
        source[:match.start()]
        + NEW_HISTORY
        + "def _fill_person_slot("
        + source[match.end():]
    )

    old_notes = """    notes = _text(
        tracking.cell(
            tracking_row,
            20,
        ).value
    )
"""
    new_notes = """    raw_notes = _text(
        tracking.cell(
            tracking_row,
            20,
        ).value
    )
    notes, internal_notes = _split_notes(raw_notes)
"""
    source = replace_once(
        source,
        old_notes,
        new_notes,
        "Tách ghi chú kỹ thuật",
    )

    old_headers = """        "SCHOOL_YEAR_CODE",
        "HEADER_ROW",
    ]
"""
    new_headers = """        "SCHOOL_YEAR_CODE",
        "HEADER_ROW",
        "INTERNAL_NOTES",
    ]
"""
    source = replace_once(
        source,
        old_headers,
        new_headers,
        "Thêm INTERNAL_NOTES",
    )

    old_values = """        spec.get("school_year_code"),
        spec.get("visible_header_row"),
    ]
"""
    new_values = """        spec.get("school_year_code"),
        spec.get("visible_header_row"),
        internal_notes,
    ]
"""
    source = replace_once(
        source,
        old_values,
        new_values,
        "Ghi INTERNAL_NOTES",
    )

    old_write = """        tracking.cell(
            tracking_row,
            20,
        ).value = fields["notes"]
"""
    new_write = """        internal_notes_col = headers.get("INTERNAL_NOTES")
        if internal_notes_col is not None:
            internal_notes = _text(
                map_sheet.cell(
                    row,
                    internal_notes_col,
                ).value
            )
        else:
            _visible_old, internal_notes = _split_notes(
                tracking.cell(
                    tracking_row,
                    20,
                ).value
            )

        tracking.cell(
            tracking_row,
            20,
        ).value = _combine_notes(
            internal_notes,
            fields["notes"],
        )
"""
    source = replace_once(
        source,
        old_write,
        new_write,
        "Giữ ghi chú kỹ thuật khi nhập",
    )

    ast.parse(source)
    return source


def verify(source: str) -> None:
    for token in (
        MARKER,
        "keep_links=False",
        "_split_notes",
        "_combine_notes",
        '"INTERNAL_NOTES"',
        '"20__-20__"',
    ):
        if token not in source:
            raise RuntimeError("Verifier thiếu: " + token)

    ast.parse(source)
    py_compile.compile(str(HELPER), doraise=True)


def main() -> int:
    print("=" * 122)
    print("BÀI 13B-12 V2.4.1.1 - LÀM SẠCH PHIẾU EXCEL ĐIỀU TRA")
    print("=" * 122)

    for path in (DB, HELPER):
        if not path.exists():
            print("DỪNG AN TOÀN: thiếu", path)
            return 2

    before = db_state()
    print("integrity_check:", before["integrity"])
    print("foreign_key_check:", before["fk_count"], "lỗi")

    if before["integrity"].lower() != "ok" or before["fk_count"] != 0:
        print("DỪNG: database chưa đạt kiểm tra an toàn.")
        return 3

    source = read_text(HELPER)

    if MARKER in source:
        print("V2.4.1.1 đã cài. Không cài lặp.")
        return 0

    try:
        patched = patch_helper(source)
    except Exception as exc:
        print()
        print("DỪNG AN TOÀN TRƯỚC KHI GHI SOURCE:")
        print(type(exc).__name__ + ":", exc)
        return 4

    EXPORTS.mkdir(parents=True, exist_ok=True)
    BACKUP.mkdir(parents=True, exist_ok=False)
    backup_file(HELPER)
    backup_db()
    print("Backup:", BACKUP)

    try:
        write_text(HELPER, patched)
        verify(read_text(HELPER))

        after = db_state()
        if after["integrity"].lower() != "ok":
            raise RuntimeError("integrity_check không đạt sau cài.")
        if after["fk_count"] != 0:
            raise RuntimeError("foreign_key_check có lỗi sau cài.")

        for table in (
            "survey_forms",
            "survey_people",
            "survey_person_year_records",
        ):
            if after[table] != before[table]:
                raise RuntimeError(
                    f"Số bản ghi {table} thay đổi ngoài dự kiến."
                )

        for cache in APP.rglob("__pycache__"):
            if cache.is_dir():
                shutil.rmtree(cache, ignore_errors=True)

    except Exception as exc:
        print()
        print("CÓ LỖI - ĐANG ROLLBACK SOURCE + DATABASE...")
        print(type(exc).__name__ + ":", exc)
        restore_file(HELPER)
        restore_db()
        print("ĐÃ KHÔI PHỤC.")
        return 9

    REPORT.write_text(
        "\n".join(
            [
                "=" * 122,
                "BÁO CÁO CÀI BÀI 13B-12 V2.4.1.1",
                "=" * 122,
                f"Thời gian: {datetime.now():%d/%m/%Y %H:%M:%S}",
                "",
                "ĐÃ SỬA:",
                "- Không giữ external workbook links khi xuất.",
                "- Lọc nhật ký kỹ thuật khỏi cột GHI CHÚ nhìn thấy.",
                "- Vẫn giữ nhật ký kỹ thuật ở trang ánh xạ ẩn.",
                "- Năm hiện tại luôn hiện; năm cũ chỉ hiện khi có dữ liệu thật.",
                "- Dòng dự phòng dùng 20__-20__.",
                "- Giữ cơ chế file 2.2.3 nhập lại tại 2.2.4.",
                "",
                f"integrity_check: {after['integrity']}",
                f"foreign_key_check: {after['fk_count']} lỗi",
                f"Backup: {BACKUP}",
            ]
        ) + "\n",
        encoding="utf-8-sig",
    )

    print()
    print("=" * 122)
    print("CÀI ĐẶT THÀNH CÔNG BÀI 13B-12 V2.4.1.1")
    print("=" * 122)
    print(" - Đã bỏ external link khi xuất.")
    print(" - Đã lọc ghi chú kỹ thuật khỏi Phiếu điều tra.")
    print(" - Đã làm sạch các dòng năm cũ trống.")
    print(" - Không sửa dữ liệu hiện có.")
    print("Báo cáo:", REPORT)
    print("Backup:", BACKUP)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
