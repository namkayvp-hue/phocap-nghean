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

FUNC_NAME = "luu_theo_doi_nam_hoc"
FIELD = "attends_two_sessions_per_day"
OLD_MARKER = "BAI_13B_12_V2_3_7_SAVE_TWO_SESSIONS_START"
NEW_MARKER = "BAI_13B_12_V2_3_8_SAVE_TWO_SESSIONS_TO_REAL_RECORD_START"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = EXPORTS / f"backup_bai_13b_12_v2_3_8_{STAMP}"
DB_BACKUP = BACKUP / "phocap.db"
REPORT = EXPORTS / f"bao_cao_cai_bai_13b_12_v2_3_8_{STAMP}.txt"


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


def find_function(tree: ast.Module):
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == FUNC_NAME:
                return node
    raise RuntimeError(f"Không tìm thấy hàm {FUNC_NAME}.")


def is_record_existing_assign(node: ast.AST) -> bool:
    if not isinstance(node, ast.Assign):
        return False
    if len(node.targets) != 1:
        return False
    target = node.targets[0]
    return (
        isinstance(target, ast.Name)
        and target.id == "record"
        and isinstance(node.value, ast.Name)
        and node.value.id == "existing_record"
    )


def is_record_none_if(node: ast.AST) -> bool:
    if not isinstance(node, ast.If):
        return False

    test = node.test
    if not isinstance(test, ast.Compare):
        return False
    if not isinstance(test.left, ast.Name) or test.left.id != "record":
        return False
    if len(test.ops) != 1 or not isinstance(test.ops[0], ast.Is):
        return False
    if len(test.comparators) != 1:
        return False

    return isinstance(test.comparators[0], ast.Constant) and test.comparators[0].value is None


def patch_source(source: str) -> tuple[str, str]:
    if NEW_MARKER in source:
        return source, "V2.3.8 đã có; không cài lặp."

    tree = ast.parse(source)
    fn = find_function(tree)

    # V2.3.7 phải có đúng trong route hiện tại.
    fn_text = "\n".join(
        source.splitlines()[
            int(fn.lineno) - 1:
            int(getattr(fn, "end_lineno", fn.lineno) or fn.lineno)
        ]
    )
    if OLD_MARKER not in fn_text:
        raise RuntimeError(
            "Không thấy marker V2.3.7 trong đúng route lưu năm học."
        )

    assign_node = None
    for node in ast.walk(fn):
        if is_record_existing_assign(node):
            if assign_node is None or node.lineno < assign_node.lineno:
                assign_node = node

    if assign_node is None:
        raise RuntimeError(
            "Không tìm thấy 'record = existing_record' trong route."
        )

    if_node = None
    for node in ast.walk(fn):
        if (
            is_record_none_if(node)
            and node.lineno > assign_node.lineno
        ):
            if if_node is None or node.lineno < if_node.lineno:
                if_node = node

    if if_node is None:
        raise RuntimeError(
            "Không tìm thấy 'if record is None:' sau record = existing_record."
        )

    # Đảm bảo đúng cặp gần nhau, tránh vá nhầm một if khác.
    if if_node.lineno - assign_node.lineno > 8:
        raise RuntimeError(
            "Khoảng cách record=existing_record -> if record is None quá xa; "
            "source đã khác bản khảo sát."
        )

    insert_after = int(
        getattr(if_node, "end_lineno", if_node.lineno) or if_node.lineno
    )

    lines = source.splitlines(keepends=True)

    assign_line = lines[assign_node.lineno - 1]
    indent = assign_line[:len(assign_line) - len(assign_line.lstrip())]

    block = (
        "\n"
        + indent
        + "# === BAI_13B_12_V2_3_8_SAVE_TWO_SESSIONS_TO_REAL_RECORD_START ===\n"
        + indent
        + "# V2.3.7 đã gán nhầm vào form_record. Từ đây record mới là "
          "SurveyPersonYearRecord thực sự sẽ được commit.\n"
        + indent
        + 'record.attends_two_sessions_per_day = '
          'parsed_tri_state["attends_two_sessions_per_day"]\n'
        + indent
        + "# === BAI_13B_12_V2_3_8_SAVE_TWO_SESSIONS_TO_REAL_RECORD_END ===\n"
    )

    lines.insert(insert_after, block)
    patched = "".join(lines)

    ast.parse(patched)
    return (
        patched,
        "Đã gán attends_two_sessions_per_day vào biến record thực sự "
        "sau khi record được lấy/tạo.",
    )


def verify() -> None:
    source = read_text(SURVEYS)
    tree = ast.parse(source)
    fn = find_function(tree)

    fn_text = "\n".join(
        source.splitlines()[
            int(fn.lineno) - 1:
            int(getattr(fn, "end_lineno", fn.lineno) or fn.lineno)
        ]
    )

    if NEW_MARKER not in fn_text:
        raise RuntimeError("Thiếu marker V2.3.8 trong route.")

    expected = (
        'record.attends_two_sessions_per_day = '
        'parsed_tri_state["attends_two_sessions_per_day"]'
    )
    if expected not in fn_text:
        raise RuntimeError(
            "Thiếu phép gán vào record thực sự."
        )

    # Phải có đúng 1 phép gán vào record.FIELD; phép gán form_record.FIELD của V2.3.7
    # được phép giữ nguyên để không sửa rộng.
    count_real = fn_text.count("record.attends_two_sessions_per_day =")
    if count_real != 1:
        raise RuntimeError(
            f"Số phép gán record.attends_two_sessions_per_day bất thường: {count_real}"
        )

    py_compile.compile(str(SURVEYS), doraise=True)


def main() -> int:
    print("=" * 122)
    print(
        "BÀI 13B-12 V2.3.8 - "
        "SỬA HỌC 2 BUỔI/NGÀY GHI VÀO ĐÚNG YEAR-RECORD"
    )
    print("=" * 122)

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
                shutil.rmtree(cache, ignore_errors=True)

    except Exception as exc:
        print()
        print("CÓ LỖI - ĐANG ROLLBACK SOURCE + DATABASE...")
        print(type(exc).__name__ + ":", exc)

        restore_file(SURVEYS)
        restore_db()
        print("ĐÃ KHÔI PHỤC.")
        return 9

    REPORT.write_text(
        "\n".join(
            [
                "=" * 122,
                "BÁO CÁO CÀI BÀI 13B-12 V2.3.8",
                "=" * 122,
                f"Thời gian: {datetime.now():%d/%m/%Y %H:%M:%S}",
                "",
                "NGUYÊN NHÂN ĐÃ XÁC ĐỊNH:",
                "- V2.3.7 đã được cài và có phép gán.",
                "- Nhưng phép gán nằm ở form_record tại khoảng dòng 14915.",
                "- Sau đó route mới lấy/tạo đối tượng record = existing_record / "
                  "SurveyPersonYearRecord.",
                "- Chính record này mới đi tiếp đến db.commit().",
                "- Vì vậy giá trị Học 2 buổi/ngày không vào bản ghi thực sự.",
                "",
                "ĐÃ SỬA:",
                f"- {action}",
                "- Không thay quy tắc PCGD/XMC.",
                "- Không tự điền dữ liệu cũ đã bị mất.",
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
    print("=" * 122)
    print("CÀI ĐẶT THÀNH CÔNG BÀI 13B-12 V2.3.8")
    print("=" * 122)
    print(" - Đã ghi Học 2 buổi/ngày vào đúng SurveyPersonYearRecord.")
    print(" - Không thay dữ liệu hiện có trong lúc cài.")
    print("Báo cáo:", REPORT)
    print("Backup:", BACKUP)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
