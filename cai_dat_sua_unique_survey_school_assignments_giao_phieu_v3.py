# -*- coding: utf-8 -*-
from __future__ import annotations

import ast
import hashlib
import os
import shutil
import sqlite3
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path

PROJECT = Path(os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")).resolve()
SURVEYS = PROJECT / "app" / "routers" / "surveys.py"
DB = PROJECT / "data" / "phocap.db"
EXPORTS = PROJECT / "exports"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = EXPORTS / f"backup_source_sua_unique_giao_phieu_v3_{STAMP}"
REPORT = EXPORTS / f"bao_cao_sua_unique_giao_phieu_v3_{STAMP}.txt"

EXPECTED_SURVEYS_SHA256 = (
    "a81206fbf6c43b6329c8b40e3bb41b8b095eb126bfca51c260f9eca98a6f8b8f"
)

V1_MARKER = "# === DONG_BO_GIAO_PHIEU_THEO_PHAN_CONG_HIEN_CO_V1_POST ==="
DIAG_MARKER = "# === CHAN_DOAN_SAVE_FAILED_GIAO_PHIEU_V2_1 ==="
V3_MARKER = "# === SUA_UNIQUE_SURVEY_SCHOOL_ASSIGNMENTS_GIAO_PHIEU_V3 ==="


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="strict")


def write_text(path: Path, text_value: str) -> None:
    path.write_text(text_value, encoding="utf-8")


def db_state() -> dict:
    uri = DB.resolve().as_uri() + "?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    try:
        con.execute("PRAGMA query_only = ON")

        integrity = str(
            con.execute("PRAGMA integrity_check").fetchone()[0]
        )
        fk_count = len(
            con.execute("PRAGMA foreign_key_check").fetchall()
        )
        assignment_total = int(
            con.execute(
                "SELECT COUNT(*) FROM survey_school_assignments"
            ).fetchone()[0]
        )

        duplicate_sql = (
            "SELECT COUNT(*) FROM ("
            "SELECT survey_batch_id, school_id, COUNT(*) AS total "
            "FROM survey_school_assignments "
            "GROUP BY survey_batch_id, school_id "
            "HAVING COUNT(*) > 1"
            ")"
        )
        duplicates = int(
            con.execute(duplicate_sql).fetchone()[0]
        )

        return {
            "integrity": integrity,
            "fk_count": fk_count,
            "assignment_total": assignment_total,
            "duplicates": duplicates,
        }
    finally:
        con.close()


def get_function_block(
    source: str,
    name: str,
) -> tuple[int, int, str]:
    tree = ast.parse(source)
    nodes = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == name
    ]

    if len(nodes) != 1:
        raise RuntimeError(
            f"Cần đúng 1 hàm {name}, tìm thấy {len(nodes)}."
        )

    node = nodes[0]
    lines = source.splitlines(keepends=True)
    start = int(node.lineno) - 1
    end = int(node.end_lineno)

    return start, end, "".join(lines[start:end])


def replace_function_block(
    source: str,
    name: str,
    new_block: str,
) -> str:
    start, end, _ = get_function_block(source, name)
    lines = source.splitlines(keepends=True)

    if not new_block.endswith("\n"):
        new_block += "\n"

    return (
        "".join(lines[:start])
        + new_block
        + "".join(lines[end:])
    )


def patch_helper(source: str) -> str:
    if V3_MARKER in source:
        return source

    _, _, block = get_function_block(
        source,
        "dong_bo_nhiem_vu_truong_khi_giao_phieu",
    )

    old = '''        if assignment is None:
            db.add(
                SurveySchoolAssignment(
                    survey_batch_id=batch_id,
                    school_id=school_id,
                    status="DANG_THUC_HIEN",
                    assigned_by_user_id=actor_user_id,
                    assigned_at=datetime.now(),
                    notes=notes or None,
                )
            )
        else:
'''

    new = f'''        if assignment is None:
            db.add(
                SurveySchoolAssignment(
                    survey_batch_id=batch_id,
                    school_id=school_id,
                    status="DANG_THUC_HIEN",
                    assigned_by_user_id=actor_user_id,
                    assigned_at=datetime.now(),
                    notes=notes or None,
                )
            )

            {V3_MARKER}
            # Flush ngay nhiệm vụ vừa thêm để lần gọi helper tiếp theo
            # trong cùng transaction nhìn thấy cặp
            # (survey_batch_id, school_id) vừa tạo.
            db.flush()
        else:
'''

    count = block.count(old)

    if count != 1:
        raise RuntimeError(
            "Không tìm thấy đúng 1 block tạo "
            "SurveySchoolAssignment cần sửa; "
            f"tìm thấy {count}."
        )

    new_block = block.replace(old, new, 1)

    result = replace_function_block(
        source,
        "dong_bo_nhiem_vu_truong_khi_giao_phieu",
        new_block,
    )

    ast.parse(result)
    return result


def verify_source(source: str) -> None:
    ast.parse(source)

    for marker, label in (
        (V1_MARKER, "V1 giao theo phân công"),
        (DIAG_MARKER, "V2.1 chẩn đoán"),
        (V3_MARKER, "V3 sửa UNIQUE"),
    ):
        if marker not in source:
            raise RuntimeError(f"Thiếu marker: {label}")

    _, _, block = get_function_block(
        source,
        "dong_bo_nhiem_vu_truong_khi_giao_phieu",
    )

    required = (
        "SurveySchoolAssignment.survey_batch_id == batch_id",
        "SurveySchoolAssignment.school_id == school_id",
        "if assignment is None:",
        "db.add(",
        "SurveySchoolAssignment(",
        V3_MARKER,
        "db.flush()",
        'assignment.status = "DANG_THUC_HIEN"',
    )

    missing = [
        token
        for token in required
        if token not in block
    ]

    if missing:
        raise RuntimeError(
            "Helper sau sửa thiếu: " + repr(missing)
        )

    add_pos = block.find("db.add(")
    flush_pos = block.find("db.flush()", add_pos)
    else_pos = block.find("        else:", add_pos)

    if not (
        add_pos >= 0
        and flush_pos > add_pos
        and else_pos > flush_pos
    ):
        raise RuntimeError(
            "db.flush() chưa nằm đúng sau db.add và trước else."
        )


def py_compile_source() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "py_compile", str(SURVEYS)],
        cwd=str(PROJECT),
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(
            "py_compile lỗi:\n"
            + result.stdout
            + "\n"
            + result.stderr
        )


def main() -> int:
    print("=" * 114)
    print(
        "V3 - SỬA UNIQUE survey_school_assignments "
        "KHI GIAO PHIẾU"
    )
    print("=" * 114)
    print()

    for path in (SURVEYS, DB):
        if not path.exists():
            print("[LỖI] Không tìm thấy: " + str(path))
            return 1

    source_sha_before = sha256_file(SURVEYS)
    db_sha_before = sha256_file(DB)
    state_before = db_state()

    try:
        if state_before["integrity"].lower() != "ok":
            raise RuntimeError("integrity_check != ok")

        if state_before["fk_count"] != 0:
            raise RuntimeError("foreign_key_check có lỗi.")

        if state_before["duplicates"] != 0:
            raise RuntimeError(
                "DB đang có duplicate "
                "(survey_batch_id, school_id) trước khi sửa."
            )

        print(
            "[1/8] Database: "
            f"integrity=ok; FK=0; "
            f"assignments={state_before['assignment_total']}; "
            "duplicate=0."
        )

        source_before = read_text(SURVEYS)
        ast.parse(source_before)

        if V3_MARKER in source_before:
            print("[2/8] V3 đã có; chuyển sang verify.")
        else:
            if source_sha_before != EXPECTED_SURVEYS_SHA256:
                raise RuntimeError(
                    "SHA256 surveys.py không đúng bản sau V2.1.\n"
                    f"Hiện tại: {source_sha_before}\n"
                    f"Yêu cầu : {EXPECTED_SURVEYS_SHA256}\n"
                    "Dừng để tránh sửa nhầm source."
                )

            if V1_MARKER not in source_before:
                raise RuntimeError("Không thấy marker V1.")

            if DIAG_MARKER not in source_before:
                raise RuntimeError("Không thấy marker V2.1.")

            print(
                "[2/8] Source đúng bản V2.1; "
                "SHA guard + AST: ĐẠT."
            )

            backup_path = (
                BACKUP / "app" / "routers" / "surveys.py"
            )
            backup_path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )
            shutil.copy2(SURVEYS, backup_path)

            print(f"[3/8] Backup: {backup_path}")

            source_after = patch_helper(source_before)

            # Verify ứng viên trước khi ghi file thật.
            verify_source(source_after)

            write_text(SURVEYS, source_after)

        final_source = read_text(SURVEYS)
        verify_source(final_source)

        print(
            "[4/8] Đã thêm db.flush() ngay sau "
            "tạo mới SurveySchoolAssignment."
        )

        py_compile_source()
        print("[5/8] AST + py_compile: ĐẠT.")

        print(
            "[6/8] Logic V1 + chẩn đoán V2.1: GIỮ NGUYÊN."
        )

        state_after = db_state()
        db_sha_after = sha256_file(DB)

        if state_after != state_before:
            raise RuntimeError(
                "Trạng thái database trước/sau khác nhau."
            )

        if db_sha_after != db_sha_before:
            raise RuntimeError(
                "SHA256 database thay đổi."
            )

        print("[7/8] Database: KHÔNG THAY ĐỔI.")

        source_sha_after = sha256_file(SURVEYS)

        EXPORTS.mkdir(parents=True, exist_ok=True)

        REPORT.write_text(
            "\n".join(
                [
                    "=" * 114,
                    "BÁO CÁO V3 - SỬA UNIQUE survey_school_assignments",
                    "=" * 114,
                    "",
                    "LỖI THỰC TẾ:",
                    (
                        "UNIQUE constraint failed: "
                        "survey_school_assignments.survey_batch_id, "
                        "survey_school_assignments.school_id"
                    ),
                    "",
                    "SỬA:",
                    (
                        "Thêm db.flush() ngay sau khi tạo mới "
                        "SurveySchoolAssignment."
                    ),
                    (
                        "Mục tiêu: lần gọi helper tiếp theo trong "
                        "cùng transaction thấy ngay nhiệm vụ vừa tạo."
                    ),
                    "",
                    f"Source SHA trước: {source_sha_before}",
                    f"Source SHA sau  : {source_sha_after}",
                    f"DB SHA trước    : {db_sha_before}",
                    f"DB SHA sau      : {db_sha_after}",
                    "Database: KHÔNG THAY ĐỔI.",
                    "",
                    "AST: ĐẠT",
                    "py_compile: ĐẠT",
                    "V1 giao theo phân công: GIỮ NGUYÊN",
                    "V2.1 diagnostic: GIỮ NGUYÊN",
                    "",
                    "KẾT LUẬN: V3 CÀI ĐẶT THÀNH CÔNG.",
                ]
            ),
            encoding="utf-8-sig",
        )

        print(f"[8/8] Báo cáo: {REPORT}")
        print()
        print("=" * 114)
        print("V3 CÀI ĐẶT THÀNH CÔNG.")
        print(
            "Đã xử lý đúng lỗi UNIQUE "
            "survey_school_assignments."
        )
        print("Database: KHÔNG THAY ĐỔI.")
        print("=" * 114)

        return 0

    except Exception as exc:
        print()
        print("=" * 114)
        print("[LỖI] V3 KHÔNG HOÀN TẤT")
        print(str(exc))
        print("=" * 114)

        try:
            backup_path = (
                BACKUP / "app" / "routers" / "surveys.py"
            )
            if backup_path.exists():
                shutil.copy2(backup_path, SURVEYS)
                print(
                    "Đã rollback surveys.py từ backup V3."
                )
        except Exception as rollback_exc:
            print("Rollback lỗi: " + str(rollback_exc))

        try:
            EXPORTS.mkdir(parents=True, exist_ok=True)
            error_path = (
                EXPORTS
                / f"loi_cai_sua_unique_giao_phieu_v3_{STAMP}.txt"
            )
            error_path.write_text(
                f"Lỗi: {exc}\n\n"
                + traceback.format_exc(),
                encoding="utf-8-sig",
            )
            print(f"Chi tiết lỗi: {error_path}")
        except Exception:
            pass

        return 1


if __name__ == "__main__":
    raise SystemExit(main())
