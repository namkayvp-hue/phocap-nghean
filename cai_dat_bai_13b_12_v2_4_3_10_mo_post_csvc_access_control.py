# -*- coding: utf-8 -*-
from __future__ import annotations

import ast
import importlib.util
import py_compile
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

PROJECT = Path(r"C:\PhoCap")
APP = PROJECT / "app"
DB = PROJECT / "data" / "phocap.db"
ACCESS = APP / "access_control.py"
REPORT_INPUTS = APP / "routers" / "report_inputs.py"
EXPORTS = PROJECT / "exports"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = EXPORTS / f"backup_bai_13b_12_v2_4_3_10_{STAMP}"
DB_BACKUP = BACKUP / "phocap.db"
REPORT = EXPORTS / f"bao_cao_cai_bai_13b_12_v2_4_3_10_{STAMP}.txt"

MARKER = "BAI_13B_12_V2_4_3_10_ACCESS_POST_CSVC_ALL_LEVELS"
PATCH_BLOCK = '\n        # === BAI_13B_12_V2_4_3_10_ACCESS_POST_CSVC_ALL_LEVELS ===\n        # Quyền qua MIDDLEWARE cho dữ liệu CSVC.\n        # Phạm vi school_id cụ thể tiếp tục được router kiểm tra.\n        if normalized_path.startswith("/csvc"):\n            if method in SAFE_METHODS:\n                return role_code in {\n                    *ADMIN_ROLE_CODES,\n                    DEPARTMENT_ROLE_CODE,\n                    COMMUNE_ROLE_CODE,\n                    SCHOOL_ROLE_CODE,\n                }\n            return (\n                is_admin_role(role_code)\n                or role_code in {\n                    COMMUNE_ROLE_CODE,\n                    SCHOOL_ROLE_CODE,\n                }\n            )\n\n        # Biểu CSVC cấu trúc dùng chung cho Tiểu học / THCS /\n        # trường liên cấp; slug phải kết thúc bằng "csvc".\n        is_structured_csvc = bool(\n            re.fullmatch(\n                r"/bieu-nhap/[a-z0-9-]*csvc",\n                normalized_path.lower(),\n            )\n        )\n        if is_structured_csvc:\n            if method in SAFE_METHODS:\n                return role_code in {\n                    *ADMIN_ROLE_CODES,\n                    DEPARTMENT_ROLE_CODE,\n                    COMMUNE_ROLE_CODE,\n                    SCHOOL_ROLE_CODE,\n                }\n            return (\n                is_admin_role(role_code)\n                or role_code in {\n                    COMMUNE_ROLE_CODE,\n                    SCHOOL_ROLE_CODE,\n                }\n            )\n'


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="replace")


def write_text(path: Path, value: str) -> None:
    path.write_text(value, encoding="utf-8")


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
            "users",
            "schools",
            "school_mn01_csvc_inputs",
            "school_structured_report_inputs",
            "survey_forms",
            "survey_people",
        ):
            exists = con.execute(
                "SELECT 1 FROM sqlite_master "
                "WHERE type='table' AND name=?",
                (table,),
            ).fetchone()
            result[table] = (
                int(
                    con.execute(
                        f'SELECT COUNT(*) FROM "{table}"'
                    ).fetchone()[0]
                )
                if exists
                else None
            )
        return result
    finally:
        con.close()


def backup_file(path: Path) -> None:
    dest = BACKUP / path.relative_to(PROJECT)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, dest)


def restore_file(path: Path) -> None:
    src = BACKUP / path.relative_to(PROJECT)
    if src.exists():
        shutil.copy2(src, path)


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


def find_action_method(tree: ast.Module):
    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "_co_quyen_theo_thao_tac"
        ):
            return node
    raise RuntimeError(
        "Không tìm thấy AccessControlMiddleware._co_quyen_theo_thao_tac()."
    )


def is_generic_safe_if(node: ast.AST) -> bool:
    if not isinstance(node, ast.If):
        return False
    try:
        value = ast.unparse(node.test).replace(" ", "")
    except Exception:
        return False
    return value == "methodinSAFE_METHODS"


def patch_access(source: str) -> str:
    if MARKER in source:
        return source

    required = (
        "class AccessControlMiddleware",
        "def _co_quyen_theo_thao_tac(",
        "normalized_path = path.rstrip",
        "SAFE_METHODS",
        "ADMIN_ROLE_CODES",
        "DEPARTMENT_ROLE_CODE",
        "COMMUNE_ROLE_CODE",
        "SCHOOL_ROLE_CODE",
        "TEACHER_ROLE_CODE",
        "is_admin_role",
    )
    for token in required:
        if token not in source:
            raise RuntimeError(
                "access_control.py khác cấu trúc dự kiến. Thiếu: "
                + token
            )

    tree = ast.parse(source)
    method_node = find_action_method(tree)

    candidates = [
        node
        for node in method_node.body
        if is_generic_safe_if(node)
    ]
    if len(candidates) != 1:
        raise RuntimeError(
            "Không xác định duy nhất được nhánh generic "
            f"'if method in SAFE_METHODS': {len(candidates)}"
        )

    anchor = candidates[0]
    lines = source.splitlines(keepends=True)
    insert_index = anchor.lineno - 1
    value = PATCH_BLOCK.strip("\n") + "\n\n"

    patched = "".join(
        lines[:insert_index]
        + [value]
        + lines[insert_index:]
    )
    ast.parse(patched)
    compile(patched, str(ACCESS), "exec")
    return patched


def verify_report_inputs() -> list[str]:
    source = read_text(REPORT_INPUTS)
    notes = []

    required = (
        "async def csvc_input_save(",
        "async def structured_school_form_save(",
        "_school_in_scope",
        "db.commit()",
        "SCHOOL_ROLE_CODE",
    )
    for token in required:
        if token not in source:
            raise RuntimeError(
                "report_inputs.py thiếu cấu trúc an toàn: " + token
            )

    if "BAI_13B_12_V2_4_3_9_MN_SAVE_OWN_SCHOOL" in source:
        notes.append(
            "Router MN có marker V2.4.3.9 khóa school_id về trường đăng nhập."
        )
    else:
        notes.append(
            "Router MN dùng _school_in_scope gốc để kiểm đúng trường."
        )

    if "BAI_13B_12_V2_4_3_9_STRUCT_SAVE_OWN_SCHOOL" in source:
        notes.append(
            "Router structured có marker V2.4.3.9 khóa school_id."
        )
    else:
        notes.append(
            "Router structured dùng _school_in_scope gốc để kiểm đúng trường."
        )

    return notes


def clear_cache() -> None:
    for cache in APP.rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(cache, ignore_errors=True)


def load_access_module():
    if str(PROJECT) not in sys.path:
        sys.path.insert(0, str(PROJECT))

    name = "_phocap_access_control_v24310"
    spec = importlib.util.spec_from_file_location(name, ACCESS)
    if spec is None or spec.loader is None:
        raise RuntimeError(
            "Không tạo được module test cho access_control.py."
        )

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def smoke_test_permissions() -> list[str]:
    module = load_access_module()
    middleware = getattr(module, "AccessControlMiddleware", None)
    if middleware is None:
        raise RuntimeError(
            "Không import được AccessControlMiddleware."
        )

    fn = getattr(
        middleware,
        "_co_quyen_theo_thao_tac",
        None,
    )
    if fn is None:
        raise RuntimeError(
            "Không đọc được _co_quyen_theo_thao_tac."
        )

    ADMIN = next(iter(module.ADMIN_ROLE_CODES))
    XA = module.COMMUNE_ROLE_CODE
    TRUONG = module.SCHOOL_ROLE_CODE
    PHONG = module.DEPARTMENT_ROLE_CODE
    GV = module.TEACHER_ROLE_CODE

    tests = [
        ("/csvc/co-so", "GET", TRUONG, True, "MN GET Trường"),
        ("/csvc/co-so", "POST", TRUONG, True, "MN POST Trường"),
        ("/csvc/nhom-lop", "POST", XA, True, "MN POST Xã"),
        ("/csvc/cong-trinh", "POST", ADMIN, True, "MN POST Admin"),
        ("/csvc/bep-san", "POST", PHONG, False, "MN POST Phòng ban"),
        ("/csvc/co-so", "POST", GV, False, "MN POST Giáo viên"),

        ("/bieu-nhap/th-01-csvc", "GET", TRUONG, True, "TH GET Trường"),
        ("/bieu-nhap/th-01-csvc", "POST", TRUONG, True, "TH POST Trường"),
        ("/bieu-nhap/thcs-01-csvc", "POST", TRUONG, True, "THCS POST Trường"),
        ("/bieu-nhap/thcs-01-csvc", "POST", XA, True, "THCS POST Xã"),
        ("/bieu-nhap/thcs-01-csvc", "POST", PHONG, False, "THCS POST Phòng ban"),
        ("/bieu-nhap/thcs-01-csvc", "POST", GV, False, "THCS POST Giáo viên"),

        ("/bao-cao/abc", "POST", TRUONG, False, "POST báo cáo khác"),
    ]

    rows = []
    for path, method, role, expected, label in tests:
        actual = bool(
            fn(
                path=path,
                method=method,
                role_code=role,
            )
        )
        rows.append(
            f"{label}: actual={actual} expected={expected}"
        )
        if actual != expected:
            raise RuntimeError(
                f"Smoke test sai: {label}: "
                f"actual={actual}, expected={expected}"
            )

    return rows


def verify_source(source: str) -> None:
    if MARKER not in source:
        raise RuntimeError(
            "Verifier access_control thiếu marker V2.4.3.10."
        )

    required = (
        'normalized_path.startswith("/csvc")',
        'r"/bieu-nhap/[a-z0-9-]*csvc"',
        "COMMUNE_ROLE_CODE",
        "SCHOOL_ROLE_CODE",
        "DEPARTMENT_ROLE_CODE",
        "SAFE_METHODS",
    )
    for token in required:
        if token not in source:
            raise RuntimeError(
                "Verifier thiếu cấu trúc: " + token
            )

    ast.parse(source)
    compile(source, str(ACCESS), "exec")
    py_compile.compile(str(ACCESS), doraise=True)


def main() -> int:
    print("=" * 128)
    print(
        "BÀI 13B-12 V2.4.3.10 - "
        "MỞ ĐÚNG POST CSVC TẠI ACCESS CONTROL CHO TẤT CẢ CẤP HỌC"
    )
    print("=" * 128)

    for path in (DB, ACCESS, REPORT_INPUTS):
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
        print("DỪNG: database chưa đạt kiểm tra an toàn.")
        return 3

    try:
        router_notes = verify_report_inputs()
        for note in router_notes:
            print("Router:", note)

        source = read_text(ACCESS)

        if MARKER in source:
            print(
                "V2.4.3.10 đã có marker. Kiểm tra lại quyền..."
            )
            clear_cache()
            smoke_rows = smoke_test_permissions()
            for row in smoke_rows:
                print(" -", row)
            print(
                "V2.4.3.10 đang hoạt động. Không cài lặp."
            )
            return 0

        patched = patch_access(source)
        ast.parse(patched)
        compile(patched, str(ACCESS), "exec")

    except Exception as exc:
        print()
        print("DỪNG AN TOÀN TRƯỚC KHI GHI SOURCE:")
        print(type(exc).__name__ + ":", exc)
        print("Không thay đổi source/database.")
        return 4

    EXPORTS.mkdir(parents=True, exist_ok=True)
    BACKUP.mkdir(parents=True, exist_ok=False)
    backup_file(ACCESS)
    backup_db()
    print("Backup:", BACKUP)

    try:
        write_text(ACCESS, patched)
        verify_source(read_text(ACCESS))
        clear_cache()

        print("Smoke test middleware sau khi cài:")
        smoke_rows = smoke_test_permissions()
        for row in smoke_rows:
            print(" -", row)

        after = db_state()

        if after["integrity"].lower() != "ok":
            raise RuntimeError(
                "integrity_check không đạt sau cài."
            )
        if after["fk_count"] != 0:
            raise RuntimeError(
                "foreign_key_check có lỗi sau cài."
            )

        for table, count in before.items():
            if table in {"integrity", "fk_count"}:
                continue
            if after.get(table) != count:
                raise RuntimeError(
                    f"Số bản ghi {table} thay đổi ngoài dự kiến: "
                    f"{count} -> {after.get(table)}"
                )

    except Exception as exc:
        print()
        print(
            "CÓ LỖI - ĐANG ROLLBACK ACCESS CONTROL + DATABASE..."
        )
        print(type(exc).__name__ + ":", exc)
        restore_file(ACCESS)
        restore_db()
        clear_cache()
        print("ĐÃ KHÔI PHỤC.")
        return 9

    report_lines = [
        "=" * 128,
        "BÁO CÁO CÀI BÀI 13B-12 V2.4.3.10",
        "=" * 128,
        f"Thời gian: {datetime.now():%d/%m/%Y %H:%M:%S}",
        "",
        "NGUYÊN NHÂN:",
        "- ROLE_RULES đã cho TRUONG truy cập /csvc.",
        "- Nhưng _co_quyen_theo_thao_tac ở nhánh POST cuối",
        "  chỉ cho TRUONG ghi /tai-khoan.",
        "- Vì vậy POST /csvc/... bị middleware chặn trước router.",
        "",
        "ĐÃ SỬA:",
        "- /csvc/*: ADMIN/SO, XA, TRUONG được POST.",
        "- /bieu-nhap/*csvc: ADMIN/SO, XA, TRUONG được POST.",
        "- PHONG_BAN chỉ đọc.",
        "- GIAO_VIEN không được POST CSVC.",
        "- Router tiếp tục kiểm school_id/phạm vi cụ thể.",
        "",
        "SMOKE TEST:",
        *["- " + row for row in smoke_rows],
        "",
        f"integrity_check: {after['integrity']}",
        f"foreign_key_check: {after['fk_count']} lỗi",
        f"Backup: {BACKUP}",
    ]
    REPORT.write_text(
        "\n".join(report_lines) + "\n",
        encoding="utf-8-sig",
    )

    print()
    print("=" * 128)
    print(
        "CÀI ĐẶT THÀNH CÔNG BÀI 13B-12 V2.4.3.10"
    )
    print("=" * 128)
    print(" - Middleware POST MN-CSVC cho Trường: ĐẠT.")
    print(" - Middleware POST TH-CSVC cho Trường: ĐẠT.")
    print(" - Middleware POST THCS-CSVC cho Trường: ĐẠT.")
    print(" - Xã được ghi CSVC theo quyền router: ĐẠT.")
    print(" - Phòng ban chỉ đọc: ĐẠT.")
    print(" - Giáo viên không được ghi CSVC: ĐẠT.")
    print(" - Không sửa dữ liệu hiện có.")
    print("Báo cáo:", REPORT)
    print("Backup:", BACKUP)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
