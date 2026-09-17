# -*- coding: utf-8 -*-
from __future__ import annotations

import py_compile
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

PROJECT = Path(r"C:\PhoCap")
APP = PROJECT / "app"
DB = PROJECT / "data" / "phocap.db"
EXPORTS = PROJECT / "exports"
SERVICE = APP / "services" / "mn_report_v246.py"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = EXPORTS / f"backup_bai_13b_12_v2_4_3_6_{STAMP}"
DB_BACKUP = BACKUP / "phocap.db"
REPORT = EXPORTS / f"bao_cao_cai_bai_13b_12_v2_4_3_6_{STAMP}.txt"

MARKER = "BAI_13B_12_V2_4_3_6_MN01_TE_PERCENT_FORMAT"

OLD_BLOCK = '    # 6) MN-01 TE master cũ.\n    ws = _sheet(\n        workbook,\n        "MN-01 TE",\n    )\n    if ws is not None:\n        refs = []\n        for col in ("E", "F", "G", "H", "I", "J", "K", "L"):\n            refs.append(f"{col}17")\n\n        refs.extend(\n            (\n                "E32",\n                "E33",\n                "E34",\n            )\n        )\n        _v2461_format_refs(ws, refs)\n'
NEW_BLOCK = '    # 6) MN-01 TE master.\n    # === BAI_13B_12_V2_4_3_6_MN01_TE_PERCENT_FORMAT ===\n    # Tất cả ô mang ý nghĩa TỈ LỆ trong MN-01-TE phải hiển thị cùng dạng %.\n    # Giá trị nguồn của các ô này đang ở thang 0..100, vì vậy dùng dấu % literal,\n    # KHÔNG dùng number_format kiểu 0% (sẽ biến 100 thành 10000%).\n    ws = _sheet(\n        workbook,\n        "MN-01 TE",\n    )\n    if ws is not None:\n        refs = []\n\n        # Bảng chính:\n        # dòng 17 = Tỉ lệ huy động\n        # dòng 23 = Tỉ lệ trẻ học 2 buổi/ngày\n        # dòng 28 = Tỉ lệ hoàn thành chương trình GDMN\n        for col in ("E", "F", "G", "H", "I", "J", "K", "L"):\n            refs.extend(\n                (\n                    f"{col}17",\n                    f"{col}23",\n                    f"{col}28",\n                )\n            )\n\n        # Bảng tiêu chí:\n        # E33:E36 = nhóm trẻ 5 tuổi\n        # E38:E40 = nhóm trẻ 3,4 tuổi\n        refs.extend(\n            (\n                "E33",\n                "E34",\n                "E35",\n                "E36",\n                "E38",\n                "E39",\n                "E40",\n            )\n        )\n\n        for ref in refs:\n            ws[ref].number_format = r"0.##\\%"\n'


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="replace")


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
            "staff_year_records",
        ):
            result[table] = int(
                con.execute(
                    f'SELECT COUNT(*) FROM "{table}"'
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


def patch_source(source: str) -> str:
    if MARKER in source:
        return source

    # Khóa đúng nền hiện hành sau V2.4.3.5.
    if "BAI_13B_12_V2_4_3_5_MN02_PERCENT_FORMAT" not in source:
        raise RuntimeError(
            "Chưa thấy marker V2.4.3.5 trong mn_report_v246.py. "
            "Dừng để tránh sửa nhầm nền."
        )

    if OLD_BLOCK not in source:
        raise RuntimeError(
            "Không tìm thấy đúng block định dạng MN-01 TE hiện tại. "
            "Dừng an toàn trước khi ghi source."
        )

    if source.count(OLD_BLOCK) != 1:
        raise RuntimeError(
            f"Block MN-01 TE xuất hiện {source.count(OLD_BLOCK)} lần; "
            "không tự động vá."
        )

    return source.replace(OLD_BLOCK, NEW_BLOCK, 1)


def verify_source(source: str) -> None:
    required = (
        MARKER,
        'f"{col}17"',
        'f"{col}23"',
        'f"{col}28"',
        '"E33"',
        '"E34"',
        '"E35"',
        '"E36"',
        '"E38"',
        '"E39"',
        '"E40"',
        'r"0.##\\\\%"',
        '("L", "N", "R")',
        "def _apply_percent_display_v2461(",
    )
    for token in required:
        if token not in source:
            raise RuntimeError("Verifier thiếu: " + token)

    py_compile.compile(str(SERVICE), doraise=True)


def main() -> int:
    print("=" * 124)
    print(
        "BÀI 13B-12 V2.4.3.6 - "
        "THỐNG NHẤT ĐỊNH DẠNG TỶ LỆ % TRÊN MN-01-TE"
    )
    print("=" * 124)

    for path in (DB, SERVICE):
        if not path.exists():
            print("DỪNG AN TOÀN: thiếu", path)
            return 2

    before = db_state()
    print("integrity_check:", before["integrity"])
    print("foreign_key_check:", before["fk_count"], "lỗi")

    if before["integrity"].lower() != "ok" or before["fk_count"] != 0:
        print("DỪNG: database chưa đạt kiểm tra an toàn.")
        return 3

    source = read_text(SERVICE)

    if MARKER in source:
        print("V2.4.3.6 đã được cài trước đó. Không cài lặp.")
        return 0

    try:
        patched = patch_source(source)
        compile(patched, str(SERVICE), "exec")
    except Exception as exc:
        print()
        print("DỪNG AN TOÀN TRƯỚC KHI GHI SOURCE:")
        print(type(exc).__name__ + ":", exc)
        print("Không có source/database nào bị thay đổi.")
        return 4

    EXPORTS.mkdir(parents=True, exist_ok=True)
    BACKUP.mkdir(parents=True, exist_ok=False)

    backup_file(SERVICE)
    backup_db()
    print("Backup:", BACKUP)

    try:
        write_text(SERVICE, patched)
        verify_source(read_text(SERVICE))

        after = db_state()

        if after["integrity"].lower() != "ok":
            raise RuntimeError("integrity_check không đạt sau cài.")
        if after["fk_count"] != 0:
            raise RuntimeError("foreign_key_check có lỗi sau cài.")

        for table in (
            "survey_forms",
            "survey_people",
            "survey_person_year_records",
            "staff_year_records",
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
        restore_file(SERVICE)
        restore_db()
        print("ĐÃ KHÔI PHỤC.")
        return 9

    REPORT.write_text(
        "\n".join(
            [
                "=" * 124,
                "BÁO CÁO CÀI BÀI 13B-12 V2.4.3.6",
                "=" * 124,
                f"Thời gian: {datetime.now():%d/%m/%Y %H:%M:%S}",
                "",
                "LỖI:",
                "- MN-01-TE chưa thống nhất cách hiển thị tỷ lệ.",
                "- Dòng Tỉ lệ huy động đã có dấu %, nhưng",
                "  Tỉ lệ học 2 buổi/ngày và bảng Tiêu chí còn hiện 100 thay vì 100%.",
                "",
                "ĐÃ SỬA ĐỊNH DẠNG:",
                "- Bảng chính dòng 17: Tỉ lệ huy động.",
                "- Bảng chính dòng 23: Tỉ lệ trẻ học 2 buổi/ngày.",
                "- Bảng chính dòng 28: Tỉ lệ hoàn thành chương trình GDMN.",
                "- Bảng tiêu chí E33:E36: nhóm trẻ 5 tuổi.",
                "- Bảng tiêu chí E38:E40: nhóm trẻ 3,4 tuổi.",
                "- Dùng định dạng 0.##% dạng literal:",
                "  100 -> 100%; 92.82 -> 92.82%.",
                "",
                "KHÔNG THAY:",
                "- Giá trị số nguồn;",
                "- công thức/tử số/mẫu số;",
                "- MN-02 đã sửa ở V2.4.3.5;",
                "- 7 biểu đã gom pipeline V2.4.3.4A;",
                "- Excel điều tra 2.2.3/2.2.4;",
                "- dữ liệu điều tra;",
                "- PCGD/XMC.",
                "",
                f"integrity_check: {after['integrity']}",
                f"foreign_key_check: {after['fk_count']} lỗi",
                f"Backup: {BACKUP}",
            ]
        ) + "\n",
        encoding="utf-8-sig",
    )

    print()
    print("=" * 124)
    print("CÀI ĐẶT THÀNH CÔNG BÀI 13B-12 V2.4.3.6")
    print("=" * 124)
    print(" - MN-01-TE các ô tỷ lệ cùng hiển thị dấu %: ĐẠT.")
    print(" - Không sửa giá trị số nguồn.")
    print(" - Không sửa dữ liệu hiện có.")
    print("Báo cáo:", REPORT)
    print("Backup:", BACKUP)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
