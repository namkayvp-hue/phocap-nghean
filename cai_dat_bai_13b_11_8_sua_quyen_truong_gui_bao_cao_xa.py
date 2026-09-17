from __future__ import annotations

import ast
import os
import shutil
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path

PROJECT = Path(os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")).resolve()
APP = PROJECT / "app"
TARGET = APP / "access_control.py"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = PROJECT / "exports" / f"backup_source_bai_13b_11_8_{STAMP}"

MARK_START = "# === BAI_13B_11_8_SCHOOL_WORKFLOW_SCOPE_START ==="
MARK_END = "# === BAI_13B_11_8_SCHOOL_WORKFLOW_SCOPE_END ==="


def read_text(path: Path) -> str:
    if not path.exists():
        raise RuntimeError(f"Không tìm thấy tệp bắt buộc: {path}")
    return path.read_text(encoding="utf-8-sig")


def write_text(path: Path, text_value: str) -> None:
    path.write_text(text_value, encoding="utf-8")


def backup_source() -> None:
    dst = BACKUP / TARGET.relative_to(PROJECT)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(TARGET, dst)


def restore_source() -> None:
    src = BACKUP / TARGET.relative_to(PROJECT)
    if src.exists():
        TARGET.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, TARGET)


def clear_cache() -> None:
    for p in APP.rglob("__pycache__"):
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True)


def _source(node: ast.AST, text_value: str) -> str:
    return ast.get_source_segment(text_value, node) or ""


def find_target_node(text_value: str) -> ast.If:
    tree = ast.parse(text_value)

    function_node = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "_co_quyen_dieu_tra":
            function_node = node
            break
    if function_node is None:
        raise RuntimeError("Không tìm thấy hàm _co_quyen_dieu_tra.")

    workflow_if = None
    for node in ast.walk(function_node):
        if isinstance(node, ast.If):
            test_src = _source(node.test, text_value)
            if "school_workflow_path is not None" in test_src:
                workflow_if = node
                break
    if workflow_if is None:
        raise RuntimeError("Không tìm thấy nhánh school_workflow_path.")

    for node in workflow_if.body:
        if isinstance(node, ast.If):
            test_src = _source(node.test, text_value)
            if "role_code == SCHOOL_ROLE_CODE" in test_src:
                return node

    raise RuntimeError("Không tìm thấy nhánh quyền SCHOOL trong school_workflow_path.")


NEW_BLOCK = '''            # === BAI_13B_11_8_SCHOOL_WORKFLOW_SCOPE_START ===
            if role_code == SCHOOL_ROLE_CODE:
                school_id = auth_user.get("school_id")
                if school_id is None:
                    return False

                try:
                    school_id_int = int(school_id)
                except (TypeError, ValueError):
                    return False

                school_commune_id = db.execute(
                    text(
                        """
                        SELECT commune_id
                        FROM schools
                        WHERE id = :school_id
                        """
                    ),
                    {"school_id": school_id_int},
                ).scalar()
                if school_commune_id is None:
                    return False

                try:
                    if int(school_commune_id) != int(batch_commune_id):
                        return False
                except (TypeError, ValueError):
                    return False

                assigned = db.execute(
                    text(
                        """
                        SELECT 1
                        FROM survey_school_assignments
                        WHERE survey_batch_id = :batch_id
                          AND school_id = :school_id
                        LIMIT 1
                        """
                    ),
                    {
                        "batch_id": batch_id,
                        "school_id": school_id_int,
                    },
                ).scalar()

                if assigned is not None:
                    return True

                assigned_form = db.execute(
                    text(
                        """
                        SELECT 1
                        FROM survey_forms AS sf
                        JOIN survey_form_investigators AS sfi
                          ON sfi.survey_form_id = sf.id
                        JOIN users AS u
                          ON u.id = sfi.user_id
                        WHERE sf.survey_batch_id = :batch_id
                          AND u.school_id = :school_id
                        LIMIT 1
                        """
                    ),
                    {
                        "batch_id": batch_id,
                        "school_id": school_id_int,
                    },
                ).scalar()

                return assigned_form is not None
            # === BAI_13B_11_8_SCHOOL_WORKFLOW_SCOPE_END ==='''


def patch(text_value: str) -> str:
    if MARK_START in text_value:
        print(" - Bài 13B-11.8 đã có sẵn, không sửa lặp.")
        return text_value

    node = find_target_node(text_value)
    lines = text_value.splitlines(keepends=True)
    start = node.lineno - 1
    end = node.end_lineno

    old_block = "".join(lines[start:end])
    if "role_code == SCHOOL_ROLE_CODE" not in old_block:
        raise RuntimeError("Nhánh nguồn cần thay không đúng dự kiến.")

    return "".join(lines[:start]) + NEW_BLOCK + "\n" + "".join(lines[end:])


def verify() -> None:
    text_value = read_text(TARGET)

    required = [
        MARK_START,
        MARK_END,
        "survey_school_assignments",
        "survey_form_investigators",
        "u.school_id = :school_id",
        "sf.survey_batch_id = :batch_id",
        "int(school_commune_id) != int(batch_commune_id)",
        'normalized_path.endswith("/gui-xa")',
        "return role_code == SCHOOL_ROLE_CODE",
    ]
    for marker in required:
        if marker not in text_value:
            raise RuntimeError(f"Kiểm tra sau cài không đạt, thiếu: {marker}")

    if text_value.count(MARK_START) != 1 or text_value.count(MARK_END) != 1:
        raise RuntimeError("Marker Bài 13B-11.8 bị lặp.")

    ast.parse(text_value)

    result = subprocess.run(
        [sys.executable, "-m", "py_compile", str(TARGET)],
        cwd=PROJECT,
        text=True,
        capture_output=True,
    )
    if result.stdout:
        print(result.stdout.rstrip())
    if result.stderr:
        print(result.stderr.rstrip())
    if result.returncode != 0:
        raise RuntimeError("py_compile access_control.py không đạt.")


def main() -> int:
    print("=" * 108)
    print("BÀI 13B-11.8 - SỬA QUYỀN TRƯỜNG MỞ LẠI NHIỆM VỤ / GỬI BÁO CÁO LÊN XÃ")
    print("=" * 108)
    print()
    print("BẢN SỬA:")
    print(" - Chỉ sửa app/access_control.py.")
    print(" - Trường phải đúng xã/phường của đợt.")
    print(" - Cho phép nếu có survey_school_assignments; hoặc")
    print("   đã có phiếu của đợt giao cho tài khoản thuộc chính trường đó.")
    print(" - Route /gui-xa vẫn chỉ dành cho vai trò TRUONG như cũ.")
    print()
    print("KHÔNG THAY ĐỔI:")
    print(" - Database.")
    print(" - Menu/giao diện.")
    print(" - Router survey_school_workflow.py.")
    print(" - Quyền quản lý trường của cấp Xã.")
    print(" - Không mở quyền sang trường khác/xã khác.")
    print()

    if not TARGET.exists():
        raise RuntimeError(f"Không tìm thấy: {TARGET}")

    BACKUP.mkdir(parents=True, exist_ok=False)
    backup_source()
    print("Backup source:", BACKUP)

    try:
        before = read_text(TARGET)
        after = patch(before)
        write_text(TARGET, after)
        verify()
        clear_cache()

        print()
        print("KIỂM TRA SAU CÀI:")
        print(" - access_control.py AST: OK")
        print(" - py_compile: OK")
        print(" - Kiểm tra đúng địa bàn trường/đợt: OK")
        print(" - Hỗ trợ assignment chính thức: OK")
        print(" - Hỗ trợ phiếu đã giao theo dữ liệu hiện có: OK")
        print(" - POST /gui-xa vẫn chỉ TRUONG: OK")
        print(" - Database: KHÔNG THAY ĐỔI")
        print()
        print("CÀI ĐẶT BÀI 13B-11.8 THÀNH CÔNG")
        return 0

    except Exception:
        traceback.print_exc()
        print()
        print("CÓ LỖI - ĐANG KHÔI PHỤC access_control.py...")
        restore_source()
        clear_cache()
        print("ĐÃ KHÔI PHỤC SOURCE.")
        print("Database không bị thay đổi.")
        print("Backup source:", BACKUP)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
