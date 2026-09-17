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
SURVEYS = APP / "routers" / "surveys.py"
EXPORTS = PROJECT / "exports"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = EXPORTS / f"backup_bai_13b_12_v2_3_7_{STAMP}"
DB_BACKUP = BACKUP / "phocap.db"
REPORT = EXPORTS / f"bao_cao_cai_bai_13b_12_v2_3_7_{STAMP}.txt"

FUNC_NAME = "luu_theo_doi_nam_hoc"
FIELD = "attends_two_sessions_per_day"
MARKER = "# === BAI_13B_12_V2_3_7_SAVE_TWO_SESSIONS_START ==="


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def write_text(path: Path, value: str) -> None:
    path.write_text(value, encoding="utf-8")


def backup_file(path: Path) -> None:
    target = BACKUP / path.relative_to(PROJECT)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, target)


def restore_file(path: Path) -> None:
    source = BACKUP / path.relative_to(PROJECT)
    if source.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
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


def db_state() -> dict:
    con = sqlite3.connect(str(DB))
    try:
        cols = {
            row[1]
            for row in con.execute(
                "PRAGMA table_info(survey_person_year_records)"
            ).fetchall()
        }
        return {
            "integrity": str(
                con.execute("PRAGMA integrity_check").fetchone()[0]
            ),
            "fk_count": len(
                con.execute("PRAGMA foreign_key_check").fetchall()
            ),
            "people": int(
                con.execute("SELECT COUNT(*) FROM survey_people").fetchone()[0]
            ),
            "year_records": int(
                con.execute(
                    "SELECT COUNT(*) FROM survey_person_year_records"
                ).fetchone()[0]
            ),
            "has_field": FIELD in cols,
        }
    finally:
        con.close()


def locate_function(source: str):
    tree = ast.parse(source)

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == FUNC_NAME:
                start = int(node.lineno)
                end = int(getattr(node, "end_lineno", node.lineno) or node.lineno)
                return start, end

    raise RuntimeError(
        f"Không tìm thấy hàm {FUNC_NAME}."
    )


def patch_source(source: str) -> tuple[str, str]:
    start, end = locate_function(source)
    lines = source.splitlines(keepends=True)

    function_text = "".join(lines[start - 1:end])

    if MARKER in function_text:
        return source, "V2.3.7 đã có trong route lưu năm học."

    # Xác nhận route hiện tại đúng với báo cáo khảo sát.
    required_tokens = (
        'attends_two_sessions_per_day: Annotated[str, Form()] = ""',
        '"attends_two_sessions_per_day": (',
        'parsed_tri_state[field_name] = parsed_value',
    )
    for token in required_tokens:
        if token not in function_text:
            raise RuntimeError(
                "Route lưu năm học đã khác bản khảo sát; thiếu: "
                + token
            )

    # Nếu source mới đã có phép gán cuối cùng thì không vá mù.
    existing_assignment = re.search(
        r"(?m)^\s*[A-Za-z_][A-Za-z0-9_]*\."
        + re.escape(FIELD)
        + r"\s*=",
        function_text,
    )
    if existing_assignment:
        raise RuntimeError(
            "Route đã có phép gán attends_two_sessions_per_day; "
            "không áp dụng V2.3.7 vì cần khảo sát nhánh ghi đè."
        )

    # Tìm đúng biến year-record qua các phép gán trường MN đã tồn tại.
    candidate_patterns = (
        r"(?m)^(?P<indent>\s*)(?P<var>[A-Za-z_][A-Za-z0-9_]*)"
        r"\.completed_preschool_by_age\s*=\s*completed_preschool_by_age_value\s*$",
        r"(?m)^(?P<indent>\s*)(?P<var>[A-Za-z_][A-Za-z0-9_]*)"
        r"\.prepared_vietnamese\s*=\s*prepared_vietnamese_value\s*$",
        r"(?m)^(?P<indent>\s*)(?P<var>[A-Za-z_][A-Za-z0-9_]*)"
        r"\.stunted\s*=\s*stunted_value\s*$",
    )

    match = None
    for pattern in candidate_patterns:
        match = re.search(pattern, function_text)
        if match:
            break

    if not match:
        raise RuntimeError(
            "Không xác định được biến year-record từ block lưu các chỉ báo MN."
        )

    record_var = match.group("var")
    indent = match.group("indent")

    # Chèn ngay sau phép gán MN đã xác định.
    matched_line = match.group(0)
    insertion = (
        matched_line
        + "\n"
        + indent
        + MARKER
        + "\n"
        + indent
        + f'{record_var}.{FIELD} = '
          'parsed_tri_state["attends_two_sessions_per_day"]'
        + "\n"
        + indent
        + "# === BAI_13B_12_V2_3_7_SAVE_TWO_SESSIONS_END ==="
    )

    function_new = function_text.replace(
        matched_line,
        insertion,
        1,
    )

    patched = (
        "".join(lines[:start - 1])
        + function_new
        + "".join(lines[end:])
    )

    ast.parse(patched)

    return (
        patched,
        f"Đã gán {record_var}.{FIELD} từ parsed_tri_state.",
    )


def verify() -> None:
    source = read_text(SURVEYS)
    start, end = locate_function(source)
    fn = "\n".join(
        source.splitlines()[start - 1:end]
    )

    if MARKER not in fn:
        raise RuntimeError("Thiếu marker V2.3.7.")

    if not re.search(
        r"(?m)^\s*[A-Za-z_][A-Za-z0-9_]*\."
        + re.escape(FIELD)
        + r'\s*=\s*parsed_tri_state\["attends_two_sessions_per_day"\]\s*$',
        fn,
    ):
        raise RuntimeError(
            "Chưa tìm thấy phép gán Học 2 buổi/ngày vào year-record."
        )

    py_compile.compile(
        str(SURVEYS),
        doraise=True,
    )


def main() -> int:
    print("=" * 120)
    print(
        "BÀI 13B-12 V2.3.7 - "
        "SỬA HỌC 2 BUỔI/NGÀY NHẬP NHƯNG KHÔNG LƯU"
    )
    print("=" * 120)

    for path in (DB, SURVEYS):
        if not path.exists():
            print("DỪNG AN TOÀN: thiếu", path)
            return 2

    before = db_state()

    print("integrity_check:", before["integrity"])
    print("foreign_key_check:", before["fk_count"], "lỗi")
    print(
        "Cột attends_two_sessions_per_day:",
        "Có" if before["has_field"] else "Không",
    )

    if (
        before["integrity"].lower() != "ok"
        or before["fk_count"] != 0
        or not before["has_field"]
    ):
        print("DỪNG: database chưa đạt điều kiện an toàn.")
        return 3

    source = read_text(SURVEYS)

    try:
        patched, action = patch_source(source)
    except Exception as exc:
        print()
        print("DỪNG AN TOÀN TRƯỚC KHI GHI FILE:")
        print(type(exc).__name__ + ":", exc)
        return 4

    if patched == source:
        print(action)
        return 0

    EXPORTS.mkdir(parents=True, exist_ok=True)
    BACKUP.mkdir(parents=True, exist_ok=False)

    backup_file(SURVEYS)
    backup_db()

    print("Backup:", BACKUP)

    try:
        write_text(SURVEYS, patched)
        verify()

        after = db_state()

        if after["integrity"].lower() != "ok":
            raise RuntimeError(
                "integrity_check không đạt sau cài."
            )
        if after["fk_count"] != 0:
            raise RuntimeError(
                "foreign_key_check có lỗi sau cài."
            )
        if after["people"] != before["people"]:
            raise RuntimeError(
                "Số nhân khẩu thay đổi ngoài dự kiến."
            )
        if after["year_records"] != before["year_records"]:
            raise RuntimeError(
                "Số year-record thay đổi ngoài dự kiến."
            )

        for cache in APP.rglob("__pycache__"):
            if cache.is_dir():
                shutil.rmtree(
                    cache,
                    ignore_errors=True,
                )

    except Exception as exc:
        print()
        print(
            "CÓ LỖI - ĐANG ROLLBACK SOURCE + DATABASE..."
        )
        print(type(exc).__name__ + ":", exc)

        restore_file(SURVEYS)
        restore_db()

        print("ĐÃ KHÔI PHỤC.")
        return 9

    REPORT.write_text(
        "\n".join(
            [
                "=" * 120,
                "BÁO CÁO CÀI BÀI 13B-12 V2.3.7",
                "=" * 120,
                (
                    "Thời gian: "
                    f"{datetime.now():%d/%m/%Y %H:%M:%S}"
                ),
                "",
                "NGUYÊN NHÂN:",
                "- Form đã gửi attends_two_sessions_per_day.",
                "- Route đã nhận và parse giá trị vào parsed_tri_state.",
                "- Nhưng route chưa gán trường này vào year-record trước commit.",
                "",
                "ĐÃ SỬA:",
                f"- {action}",
                "- Không sửa quy tắc PCGD/XMC.",
                "- Không tự suy đoán giá trị Học 2 buổi/ngày cũ đã bị mất.",
                "- Người dùng mở lại bản ghi, chọn Có/Không thực tế và lưu lại.",
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
    print("=" * 120)
    print("CÀI ĐẶT THÀNH CÔNG BÀI 13B-12 V2.3.7")
    print("=" * 120)
    print(" - Đã nối giá trị Học 2 buổi/ngày vào year-record.")
    print(" - Không tự thay dữ liệu cũ đã bị mất.")
    print("Báo cáo:", REPORT)
    print("Backup:", BACKUP)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
