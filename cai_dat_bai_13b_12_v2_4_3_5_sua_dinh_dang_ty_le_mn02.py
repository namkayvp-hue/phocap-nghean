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
BACKUP = EXPORTS / f"backup_bai_13b_12_v2_4_3_5_{STAMP}"
DB_BACKUP = BACKUP / "phocap.db"
REPORT = EXPORTS / f"bao_cao_cai_bai_13b_12_v2_4_3_5_{STAMP}.txt"

MARKER = "BAI_13B_12_V2_4_3_5_MN02_PERCENT_FORMAT"

OLD_BLOCK = '    # 4) MN-02 trong bộ 7 sheet master.\n    ws = _sheet(\n        workbook,\n        "MN-02",\n    )\n    if ws is not None:\n        _v2461_format_column_rows(\n            ws,\n            ("L",),\n            8,\n            int(ws.max_row),\n        )\n'
NEW_BLOCK = '    # 4) MN-02 trong bộ 7 sheet master.\n    # === BAI_13B_12_V2_4_3_5_MN02_PERCENT_FORMAT ===\n    # L = tỷ lệ huy động\n    # N = tỷ lệ hoàn thành CTGDMN theo độ tuổi\n    # R = tỷ lệ trẻ khuyết tật tiếp cận giáo dục\n    ws = _sheet(\n        workbook,\n        "MN-02",\n    )\n    if ws is not None:\n        _v2461_format_column_rows(\n            ws,\n            ("L", "N", "R"),\n            8,\n            int(ws.max_row),\n        )\n'


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="replace")


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def db_state() -> dict:
    con = sqlite3.connect(str(DB))
    try:
        result = {
            "integrity": str(con.execute("PRAGMA integrity_check").fetchone()[0]),
            "fk_count": len(con.execute("PRAGMA foreign_key_check").fetchall()),
        }
        for table in (
            "survey_forms",
            "survey_people",
            "survey_person_year_records",
            "staff_year_records",
        ):
            result[table] = int(
                con.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
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

    if OLD_BLOCK not in source:
        raise RuntimeError(
            "Không tìm thấy đúng block định dạng MN-02 của nền hiện tại. "
            "Bộ cài dừng để tránh sửa nhầm."
        )

    if source.count(OLD_BLOCK) != 1:
        raise RuntimeError(
            f"Block MN-02 xuất hiện {source.count(OLD_BLOCK)} lần; "
            "không tự động vá."
        )

    return source.replace(OLD_BLOCK, NEW_BLOCK, 1)


def verify_source(source: str) -> None:
    required = (
        MARKER,
        '("L", "N", "R")',
        '"MN-02"',
        "def apply_formula_contract(",
        "def _apply_percent_display_v2461(",
    )
    for token in required:
        if token not in source:
            raise RuntimeError("Verifier thiếu: " + token)

    py_compile.compile(str(SERVICE), doraise=True)


def main() -> int:
    print("=" * 122)
    print(
        "BÀI 13B-12 V2.4.3.5 - "
        "SỬA ĐỊNH DẠNG TỶ LỆ % TRÊN BIỂU MN-02"
    )
    print("=" * 122)

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
        print("V2.4.3.5 đã được cài trước đó. Không cài lặp.")
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
                "=" * 122,
                "BÁO CÁO CÀI BÀI 13B-12 V2.4.3.5",
                "=" * 122,
                f"Thời gian: {datetime.now():%d/%m/%Y %H:%M:%S}",
                "",
                "LỖI:",
                "- Trên MN-02, cột L (tỷ lệ huy động) đã được định dạng %.",
                "- Cột N (tỷ lệ hoàn thành CTGDMN) chưa được áp cùng định dạng,",
                "  nên giá trị 100 hiển thị thành '100' thay vì '100%'.",
                "- Cột R (tỷ lệ tiếp cận giáo dục của trẻ khuyết tật) cũng cùng nhóm tỷ lệ.",
                "",
                "ĐÃ SỬA:",
                "- Định dạng % cho cả ba cột MN-02: L, N, R.",
                "- Không đổi giá trị số nguồn.",
                "- Không đổi công thức/tỷ lệ.",
                "- Không đổi dữ liệu CSDL.",
                "",
                "KHÔNG ĐỤNG:",
                "- 7 biểu đã gom pipeline V2.4.3.4A;",
                "- Excel điều tra 2.2.3/2.2.4;",
                "- dữ liệu điều tra;",
                "- PCGD/XMC;",
                "- phân công/giao phiếu/nhập nhanh.",
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
    print("CÀI ĐẶT THÀNH CÔNG BÀI 13B-12 V2.4.3.5")
    print("=" * 122)
    print(" - MN-02 cột L, N, R cùng định dạng tỷ lệ %: ĐẠT.")
    print(" - Không sửa giá trị số nguồn.")
    print(" - Không sửa dữ liệu hiện có.")
    print("Báo cáo:", REPORT)
    print("Backup:", BACKUP)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
