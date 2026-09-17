# -*- coding: utf-8 -*-
from __future__ import annotations

import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from jinja2 import Environment

PROJECT = Path(r"C:\PhoCap")
APP = PROJECT / "app"
DB = PROJECT / "data" / "phocap.db"
EXPORTS = PROJECT / "exports"
TEMPLATE = APP / "templates" / "surveys" / "year_records.html"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = EXPORTS / f"backup_bai_13b_12_v2_3_12_{STAMP}"
REPORT = EXPORTS / f"bao_cao_cai_bai_13b_12_v2_3_12_{STAMP}.txt"

MARKER = "BAI_13B_12_V2_3_12_POST_THCS_LABELS"

OLD_TO_NEW = {
    "Đang học THPT": "Học lên THPT",
    "Đang học GDTX cấp THPT": "Học lên GDTX cấp THPT",
    "Đang học giáo dục nghề nghiệp": "Học giáo dục nghề nghiệp",
}


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def write_text(path: Path, value: str) -> None:
    path.write_text(value, encoding="utf-8")


def backup_file(path: Path) -> None:
    target = BACKUP / path.relative_to(PROJECT)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, target)


def db_state() -> tuple[str, int]:
    con = sqlite3.connect(str(DB))
    try:
        integrity = str(con.execute("PRAGMA integrity_check").fetchone()[0])
        fk_count = len(con.execute("PRAGMA foreign_key_check").fetchall())
        return integrity, fk_count
    finally:
        con.close()


def main() -> int:
    print("=" * 118)
    print("BÀI 13B-12 V2.3.12 - SỬA CÁCH GỌI HƯỚNG HỌC SAU THCS")
    print("=" * 118)

    if not TEMPLATE.exists() or not DB.exists():
        print("DỪNG AN TOÀN: thiếu template hoặc database.")
        return 2

    integrity, fk_count = db_state()
    print("integrity_check:", integrity)
    print("foreign_key_check:", fk_count, "lỗi")

    if integrity.lower() != "ok" or fk_count != 0:
        print("DỪNG: database chưa đạt kiểm tra an toàn.")
        return 3

    source = read_text(TEMPLATE)

    if MARKER in source:
        print("V2.3.12 đã cài. Không cài lặp.")
        return 0

    required = (
        'id="post_lower_secondary_path"',
        'value="THPT"',
        'value="GDTX"',
        'value="GDNN"',
        'value="KHONG_HOC"',
        "Hướng học sau THCS",
    )
    for token in required:
        if token not in source:
            print("DỪNG AN TOÀN: thiếu", token)
            return 4

    changed = source
    applied = []

    for old, new in OLD_TO_NEW.items():
        count = changed.count(old)
        if count != 1:
            print(
                "DỪNG AN TOÀN: số lần xuất hiện",
                repr(old),
                "=",
                count,
                "(mong đợi 1)",
            )
            return 5
        changed = changed.replace(old, new, 1)
        applied.append((old, new))

    # Gắn marker ngay trước label để nhận diện phiên bản,
    # không thay đổi value/code lưu trong database.
    label_needle = """                                <label for="post_lower_secondary_path">
                                    Hướng học sau THCS
"""
    label_replacement = """                                <!-- === BAI_13B_12_V2_3_12_POST_THCS_LABELS === -->
                                <label for="post_lower_secondary_path">
                                    Hướng học sau THCS
"""

    if label_needle not in changed:
        print("DỪNG AN TOÀN: không tìm thấy label đúng bản dự kiến.")
        return 6

    changed = changed.replace(label_needle, label_replacement, 1)

    try:
        Environment().parse(changed)
    except Exception as exc:
        print("DỪNG AN TOÀN: Jinja parse lỗi:", exc)
        return 7

    EXPORTS.mkdir(parents=True, exist_ok=True)
    BACKUP.mkdir(parents=True, exist_ok=False)
    backup_file(TEMPLATE)
    print("Backup:", BACKUP)

    try:
        write_text(TEMPLATE, changed)

        verify = read_text(TEMPLATE)

        for old, new in applied:
            if old in verify:
                raise RuntimeError(f"Vẫn còn nhãn cũ: {old}")
            if new not in verify:
                raise RuntimeError(f"Thiếu nhãn mới: {new}")

        # Không thay mã nghiệp vụ.
        for value in ("THPT", "GDTX", "GDNN", "KHONG_HOC"):
            if f'value="{value}"' not in verify:
                raise RuntimeError(
                    f"Mất mã nghiệp vụ post_lower_secondary_path={value}"
                )

        Environment().parse(verify)

        integrity2, fk_count2 = db_state()
        if integrity2.lower() != "ok" or fk_count2 != 0:
            raise RuntimeError(
                "Database không đạt kiểm tra sau cài."
            )

    except Exception as exc:
        print()
        print("CÓ LỖI - ĐANG ROLLBACK TEMPLATE...")
        print(type(exc).__name__ + ":", exc)

        backup_template = BACKUP / TEMPLATE.relative_to(PROJECT)
        shutil.copy2(backup_template, TEMPLATE)
        print("ĐÃ KHÔI PHỤC.")
        return 9

    REPORT.write_text(
        "\n".join(
            [
                "=" * 118,
                "BÁO CÁO CÀI BÀI 13B-12 V2.3.12",
                "=" * 118,
                f"Thời gian: {datetime.now():%d/%m/%Y %H:%M:%S}",
                "",
                "ĐÃ SỬA CÁCH HIỂN THỊ:",
                "- Đang học THPT -> Học lên THPT",
                "- Đang học GDTX cấp THPT -> Học lên GDTX cấp THPT",
                "- Đang học giáo dục nghề nghiệp -> Học giáo dục nghề nghiệp",
                "- Không học tiếp: giữ nguyên",
                "",
                "KHÔNG THAY ĐỔI MÃ NGHIỆP VỤ:",
                "- THPT",
                "- GDTX",
                "- GDNN",
                "- KHONG_HOC",
                "",
                "Không sửa database, không sửa báo cáo, không sửa quy tắc THCS/XMC.",
                f"integrity_check: {integrity2}",
                f"foreign_key_check: {fk_count2} lỗi",
                f"Backup: {BACKUP}",
            ]
        )
        + "\n",
        encoding="utf-8-sig",
    )

    print()
    print("=" * 118)
    print("CÀI ĐẶT THÀNH CÔNG BÀI 13B-12 V2.3.12")
    print("=" * 118)
    print(" - Hướng học sau THCS đã đổi sang cách gọi 'Học lên...'.")
    print(" - Mã lưu dữ liệu giữ nguyên.")
    print("Báo cáo:", REPORT)
    print("Backup:", BACKUP)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
