# -*- coding: utf-8 -*-
from __future__ import annotations

import ast
import py_compile
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

PROJECT = Path(r"C:\PhoCap")
APP = PROJECT / "app"
DB = PROJECT / "data" / "phocap.db"
SURVEYS = APP / "routers" / "surveys.py"
EXPORTS = PROJECT / "exports"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = EXPORTS / f"backup_bai_13b_12_v2_3_5_{STAMP}"
DB_BACKUP = BACKUP / "phocap.db"
REPORT = EXPORTS / f"bao_cao_cai_bai_13b_12_v2_3_5_{STAMP}.txt"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def write_text(path: Path, value: str) -> None:
    path.write_text(value, encoding="utf-8")


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


def db_state() -> dict:
    con = sqlite3.connect(str(DB))
    try:
        return {
            "integrity": str(
                con.execute("PRAGMA integrity_check").fetchone()[0]
            ),
            "fk_count": len(
                con.execute("PRAGMA foreign_key_check").fetchall()
            ),
            "people": int(
                con.execute(
                    "SELECT COUNT(*) FROM survey_people"
                ).fetchone()[0]
            ),
            "year_records": int(
                con.execute(
                    "SELECT COUNT(*) FROM survey_person_year_records"
                ).fetchone()[0]
            ),
        }
    finally:
        con.close()


def patch_import_re(source: str) -> tuple[str, str]:
    tree = ast.parse(source)

    # Nếu đã có "import re" hoặc "from re import ..." thì không sửa lặp.
    for node in tree.body:
        if isinstance(node, ast.Import):
            if any(alias.name == "re" for alias in node.names):
                return source, "Đã có import re; không cần thêm."
        if isinstance(node, ast.ImportFrom):
            if node.module == "re":
                return source, "Đã có from re import ...; không cần thêm."

    lines = source.splitlines(keepends=True)

    # Giữ shebang/encoding/docstring/future import đúng chuẩn.
    insert_at = 0

    if lines and lines[0].startswith("#!"):
        insert_at = 1

    while (
        insert_at < len(lines)
        and (
            "coding:" in lines[insert_at]
            or "coding=" in lines[insert_at]
        )
    ):
        insert_at += 1

    # Nếu có module docstring, chèn sau docstring.
    parsed = ast.parse(source)
    if (
        parsed.body
        and isinstance(parsed.body[0], ast.Expr)
        and isinstance(parsed.body[0].value, ast.Constant)
        and isinstance(parsed.body[0].value.value, str)
    ):
        insert_at = max(
            insert_at,
            int(parsed.body[0].end_lineno or 0),
        )

    # Chèn sau toàn bộ __future__ imports.
    for node in parsed.body:
        if isinstance(node, ast.ImportFrom) and node.module == "__future__":
            insert_at = max(insert_at, int(node.end_lineno or node.lineno))
        else:
            if int(getattr(node, "lineno", 0) or 0) > insert_at:
                break

    lines.insert(insert_at, "import re\n")
    patched = "".join(lines)

    ast.parse(patched)

    if "import re" not in patched:
        raise RuntimeError("Không chèn được import re.")

    return patched, "Đã thêm import re vào surveys.py."


def main() -> int:
    print("=" * 118)
    print("BÀI 13B-12 V2.3.5 - SỬA LỖI NAMEERROR: re IS NOT DEFINED")
    print("=" * 118)

    for path in (DB, SURVEYS):
        if not path.exists():
            print("DỪNG AN TOÀN: thiếu", path)
            return 2

    before = db_state()
    print("integrity_check:", before["integrity"])
    print("foreign_key_check:", before["fk_count"], "lỗi")

    if (
        before["integrity"].lower() != "ok"
        or before["fk_count"] != 0
    ):
        print("DỪNG: database chưa đạt kiểm tra.")
        return 3

    source = read_text(SURVEYS)

    # Xác nhận đúng nền V2.3.x đang dùng re.search.
    if "re.search(" not in source:
        print("DỪNG AN TOÀN: surveys.py không còn re.search như log hiện tại.")
        return 4

    if "BAI_13B_12_V2_3_1_GRADE_PARSER_START" not in source:
        print("DỪNG AN TOÀN: chưa thấy marker parser lớp V2.3.1.")
        return 5

    try:
        patched, action = patch_import_re(source)
        ast.parse(patched)
    except Exception as exc:
        print("DỪNG AN TOÀN TRƯỚC KHI GHI FILE:")
        print(type(exc).__name__ + ":", exc)
        return 6

    EXPORTS.mkdir(parents=True, exist_ok=True)
    BACKUP.mkdir(parents=True, exist_ok=False)

    surveys_backup = BACKUP / SURVEYS.relative_to(PROJECT)
    surveys_backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SURVEYS, surveys_backup)
    backup_db()

    print("Backup:", BACKUP)

    try:
        if patched != source:
            write_text(SURVEYS, patched)

        py_compile.compile(str(SURVEYS), doraise=True)

        check = read_text(SURVEYS)
        ast.parse(check)

        # Kiểm tra import re thực sự tồn tại trong AST.
        parsed = ast.parse(check)
        has_re = False
        for node in parsed.body:
            if isinstance(node, ast.Import):
                if any(alias.name == "re" for alias in node.names):
                    has_re = True
            elif isinstance(node, ast.ImportFrom) and node.module == "re":
                has_re = True

        if not has_re:
            raise RuntimeError("Sau cài vẫn chưa có import re.")

        after = db_state()

        if after["integrity"].lower() != "ok":
            raise RuntimeError("integrity_check không đạt sau cài.")
        if after["fk_count"] != 0:
            raise RuntimeError("foreign_key_check có lỗi sau cài.")
        if before["people"] != after["people"]:
            raise RuntimeError("Số nhân khẩu thay đổi ngoài dự kiến.")
        if before["year_records"] != after["year_records"]:
            raise RuntimeError("Số year-record thay đổi ngoài dự kiến.")

        for cache in APP.rglob("__pycache__"):
            if cache.is_dir():
                shutil.rmtree(cache, ignore_errors=True)

    except Exception as exc:
        print()
        print("CÓ LỖI - ĐANG ROLLBACK SOURCE + DATABASE...")
        print(type(exc).__name__ + ":", exc)

        shutil.copy2(surveys_backup, SURVEYS)
        restore_db()

        for cache in APP.rglob("__pycache__"):
            if cache.is_dir():
                shutil.rmtree(cache, ignore_errors=True)

        print("ĐÃ KHÔI PHỤC.")
        return 9

    REPORT.write_text(
        "\n".join(
            [
                "=" * 118,
                "BÁO CÁO CÀI BÀI 13B-12 V2.3.5",
                "=" * 118,
                f"Thời gian: {datetime.now():%d/%m/%Y %H:%M:%S}",
                "",
                "NGUYÊN NHÂN:",
                "- surveys.py đang gọi re.search trong luu_theo_doi_nam_hoc.",
                "- Nhưng module re chưa được import.",
                "- Khi bấm Lưu và chuyển thành viên tiếp theo -> NameError -> HTTP 500.",
                "",
                "ĐÃ SỬA:",
                f"- {action}",
                "- Không sửa nghiệp vụ PCGD/XMC.",
                "- Không thay dữ liệu nhân khẩu/year-record.",
                "",
                f"integrity_check: {after['integrity']}",
                f"foreign_key_check: {after['fk_count']} lỗi",
                f"Backup: {BACKUP}",
            ]
        )
        + "\n",
        encoding="utf-8-sig",
    )

    print()
    print("=" * 118)
    print("CÀI ĐẶT THÀNH CÔNG BÀI 13B-12 V2.3.5")
    print("=" * 118)
    print(" - Đã sửa lỗi thiếu import re.")
    print(" - Không thay dữ liệu database.")
    print("Báo cáo:", REPORT)
    print("Backup:", BACKUP)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
