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
TARGET = APP / "routers" / "report_inputs.py"
EXPORTS = PROJECT / "exports"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = EXPORTS / f"backup_bai_13b_12_v2_4_3_9a_{STAMP}"
DB_BACKUP = BACKUP / "phocap.db"
REPORT = EXPORTS / f"bao_cao_cai_bai_13b_12_v2_4_3_9a_{STAMP}.txt"

HELPER_MARKER = "BAI_13B_12_V2_4_3_9_SCHOOL_UNIT_SCOPE_HELPER"
MN_SAVE_MARKER = "BAI_13B_12_V2_4_3_9_MN_SAVE_OWN_SCHOOL"
STRUCT_SAVE_MARKER = "BAI_13B_12_V2_4_3_9_STRUCT_SAVE_OWN_SCHOOL"
MN_PAGE_MARKER = "BAI_13B_12_V2_4_3_9_MN_PAGE_CAN_EDIT"
STRUCT_PAGE_MARKER = "BAI_13B_12_V2_4_3_9_STRUCT_PAGE_CAN_EDIT"

HELPER = '\n# === BAI_13B_12_V2_4_3_9_SCHOOL_UNIT_SCOPE_HELPER ===\ndef _v2439_is_school_unit(user: dict | None, role_code: str | None = None) -> bool:\n    """Nhận diện đúng tài khoản ĐƠN VỊ TRƯỜNG; không nhận giáo viên/CBQL cá nhân."""\n    user = user or {}\n    normalized_role = normalize_role_code(\n        role_code if role_code is not None else user.get("role_code")\n    )\n    username = str(user.get("username") or "").strip().lower()\n    school_id = user.get("school_id")\n\n    if school_id is None:\n        return False\n\n    return normalized_role == SCHOOL_ROLE_CODE or username.startswith("truong_")\n\n\ndef _v2439_school_unit_id(user: dict | None) -> int | None:\n    user = user or {}\n    try:\n        value = int(user.get("school_id"))\n    except (TypeError, ValueError):\n        return None\n    return value if value > 0 else None\n\n\ndef _v2439_school_unit_owns_target(\n    db: Session,\n    user: dict | None,\n    school_id: int | None,\n) -> bool:\n    """Cấp Trường chỉ được ghi đúng chính trường đang đăng nhập."""\n    own_id = _v2439_school_unit_id(user)\n    try:\n        target_id = int(school_id or 0)\n    except (TypeError, ValueError):\n        return False\n\n    if own_id is None or target_id != own_id:\n        return False\n\n    school = db.get(School, own_id)\n    return school is not None and bool(school.is_active)\n'
MN_HEADER = '\n    user = lay_thong_tin_nguoi_dung(request)\n    role = normalize_role_code((user or {}).get("role_code"))\n\n    # === BAI_13B_12_V2_4_3_9_MN_SAVE_OWN_SCHOOL ===\n    is_school_unit = _v2439_is_school_unit(user, role)\n\n    if role not in CSVC_EDIT_ROLES and not is_school_unit:\n        return _redirect_forbidden()\n\n    form = await request.form()\n    year_id = _parse_int(form.get("school_year_id"), 0, 1)\n    submitted_school_id = _parse_int(form.get("school_id"), 0, 1)\n\n    if is_school_unit:\n        school_id = _v2439_school_unit_id(user)\n        if not year_id or not _v2439_school_unit_owns_target(db, user, school_id):\n            return _redirect_forbidden()\n    else:\n        school_id = submitted_school_id\n        if (\n            not year_id\n            or not school_id\n            or not _school_in_scope(db, request, school_id)\n        ):\n            return _redirect_forbidden()\n\n'
STRUCT_HEADER = '\n    user = lay_thong_tin_nguoi_dung(request)\n    role = normalize_role_code((user or {}).get("role_code"))\n\n    # === BAI_13B_12_V2_4_3_9_STRUCT_SAVE_OWN_SCHOOL ===\n    is_school_unit = _v2439_is_school_unit(user, role)\n\n    if role not in STRUCTURED_FORM_EDIT_ROLES and not is_school_unit:\n        return _redirect_forbidden()\n\n    form = await request.form()\n    year_id = _parse_int(form.get("school_year_id"), 0, 1)\n    submitted_school_id = _parse_int(form.get("school_id"), 0, 1)\n\n    if is_school_unit:\n        school_id = _v2439_school_unit_id(user)\n        if not year_id or not _v2439_school_unit_owns_target(db, user, school_id):\n            return _redirect_forbidden()\n    else:\n        school_id = submitted_school_id\n        if (\n            not year_id\n            or not school_id\n            or not _school_in_scope(db, request, school_id)\n        ):\n            return _redirect_forbidden()\n\n'


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="replace")


def write_text(path: Path, value: str) -> None:
    path.write_text(value, encoding="utf-8")


def db_state() -> dict:
    con = sqlite3.connect(str(DB))
    try:
        result = {
            "integrity": str(con.execute("PRAGMA integrity_check").fetchone()[0]),
            "fk_count": len(con.execute("PRAGMA foreign_key_check").fetchall()),
        }
        for table in (
            "users",
            "schools",
            "school_mn01_csvc_inputs",
            "school_structured_report_inputs",
            "school_facility_year_items",
            "survey_forms",
            "survey_people",
        ):
            exists = con.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            ).fetchone()
            result[table] = (
                int(con.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
                if exists else None
            )
        return result
    finally:
        con.close()


def school_account_info() -> list[tuple]:
    con = sqlite3.connect(str(DB))
    try:
        return con.execute(
            """
            SELECT u.id, u.username, u.school_id, u.role_id,
                   COALESCE(r.code, ''), COALESCE(s.name, '')
            FROM users u
            LEFT JOIN roles r ON r.id = u.role_id
            LEFT JOIN schools s ON s.id = u.school_id
            WHERE lower(u.username) LIKE 'truong_%'
              AND COALESCE(u.is_active, 1) = 1
            ORDER BY u.id
            LIMIT 20
            """
        ).fetchall()
    except sqlite3.Error:
        return []
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


def function_region(source: str, name: str) -> tuple[int, int]:
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return offsets[node.lineno - 1], offsets[node.end_lineno]

    raise RuntimeError(f"Không tìm thấy hàm {name}")


def replace_between_in_function(
    source: str,
    function_name: str,
    start_token: str,
    end_token: str,
    replacement: str,
) -> str:
    a, b = function_region(source, function_name)
    block = source[a:b]
    start = block.find(start_token)
    if start < 0:
        raise RuntimeError(
            f"{function_name}: không tìm thấy điểm đầu patch: {start_token.strip()}"
        )
    end = block.find(end_token, start)
    if end < 0:
        raise RuntimeError(
            f"{function_name}: không tìm thấy điểm cuối patch: {end_token.strip()}"
        )
    new_block = block[:start] + replacement + block[end:]
    return source[:a] + new_block + source[b:]


def replace_can_edit_in_function(
    source: str,
    function_name: str,
    new_value: str,
    marker: str,
) -> str:
    """
    V2.4.3.9A:
    Thay GIÁ TRỊ của key "can_edit" bằng AST, vì nền V2.4.3.8 đang dùng
    biểu thức nhiều dòng. Không thay từng dòng text để tránh sót dấu ).
    """
    tree = ast.parse(source)
    target_func = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name:
            target_func = node
            break
    if target_func is None:
        raise RuntimeError(f"Không tìm thấy hàm {function_name}")

    # Nếu marker đã ở đúng hàm thì không cài lặp.
    a, b = function_region(source, function_name)
    if marker in source[a:b]:
        return source

    candidates = []
    for node in ast.walk(target_func):
        if not isinstance(node, ast.Dict):
            continue
        for key, value in zip(node.keys, node.values):
            if (
                isinstance(key, ast.Constant)
                and key.value == "can_edit"
                and value is not None
            ):
                candidates.append(value)

    if len(candidates) != 1:
        raise RuntimeError(
            f"{function_name}: cần đúng 1 giá trị can_edit bằng AST, thực tế={len(candidates)}"
        )

    value_node = candidates[0]
    lines = source.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))

    start = offsets[value_node.lineno - 1] + value_node.col_offset
    end = offsets[value_node.end_lineno - 1] + value_node.end_col_offset

    replacement = (
        f"({new_value})"
        + f"  # === {marker} ==="
    )
    result = source[:start] + replacement + source[end:]
    ast.parse(result)
    return result


def inject_helper(source: str) -> str:
    """
    V2.4.3.9A:
    Chèn helper TRƯỚC decorator đầu tiên của csvc_input_page,
    không bao giờ chèn giữa @router... và def.
    """
    if HELPER_MARKER in source:
        return source

    tree = ast.parse(source)
    target = None
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "csvc_input_page":
            target = node
            break
    if target is None:
        raise RuntimeError("Không tìm thấy def csvc_input_page để chèn helper.")

    start_lineno = target.lineno
    decorator_lines = [
        dec.lineno
        for dec in getattr(target, "decorator_list", [])
        if getattr(dec, "lineno", None)
    ]
    if decorator_lines:
        start_lineno = min([start_lineno] + decorator_lines)

    lines = source.splitlines(keepends=True)
    index = start_lineno - 1
    value = HELPER.rstrip("\n") + "\n\n"
    result = "".join(lines[:index] + [value] + lines[index:])
    ast.parse(result)
    return result


def patch_source(source: str) -> str:
    required = (
        "async def csvc_input_save(",
        "async def structured_school_form_save(",
        "def csvc_input_page(",
        "def structured_school_form_page(",
        "CSVC_EDIT_ROLES",
        "STRUCTURED_FORM_EDIT_ROLES",
        "SCHOOL_ROLE_CODE",
        "normalize_role_code",
        "School",
    )
    for token in required:
        if token not in source:
            raise RuntimeError("Source hiện tại thiếu cấu trúc nền: " + token)

    source = inject_helper(source)

    if MN_SAVE_MARKER not in source:
        source = replace_between_in_function(
            source,
            "csvc_input_save",
            "    user = lay_thong_tin_nguoi_dung(request)\n",
            "    record = _csvc_record(db, year_id, school_id)\n",
            MN_HEADER,
        )

    if STRUCT_SAVE_MARKER not in source:
        source = replace_between_in_function(
            source,
            "structured_school_form_save",
            "    user = lay_thong_tin_nguoi_dung(request)\n",
            "    schools, grades = _pc_schools_and_classes(db, year_id, None, school_id)\n",
            STRUCT_HEADER,
        )

    source = replace_can_edit_in_function(
        source,
        "csvc_input_page",
        'scope["role_code"] in CSVC_EDIT_ROLES '
        'or _v2439_is_school_unit(scope.get("user"), scope.get("role_code"))',
        MN_PAGE_MARKER,
    )

    source = replace_can_edit_in_function(
        source,
        "structured_school_form_page",
        'scope["role_code"] in STRUCTURED_FORM_EDIT_ROLES '
        'or _v2439_is_school_unit(scope.get("user"), scope.get("role_code"))',
        STRUCT_PAGE_MARKER,
    )

    compile(source, str(TARGET), "exec")
    return source


def verify_source(source: str) -> None:
    for marker in (
        HELPER_MARKER,
        MN_SAVE_MARKER,
        STRUCT_SAVE_MARKER,
        MN_PAGE_MARKER,
        STRUCT_PAGE_MARKER,
    ):
        if marker not in source:
            raise RuntimeError("Verifier thiếu marker: " + marker)

    required = (
        'username.startswith("truong_")',
        "target_id != own_id",
        "school = db.get(School, own_id)",
        "school_id = _v2439_school_unit_id(user)",
        "_v2439_school_unit_owns_target(db, user, school_id)",
        "role not in CSVC_EDIT_ROLES and not is_school_unit",
        "role not in STRUCTURED_FORM_EDIT_ROLES and not is_school_unit",
        "_structured_school_supports_level(",
    )
    for token in required:
        if token not in source:
            raise RuntimeError("Verifier thiếu cấu trúc: " + token)

    helper_start = source.find("# === " + HELPER_MARKER)
    helper_end = source.find("def csvc_input_page(", helper_start)
    helper_block = source[helper_start:helper_end]
    if "GIAO_VIEN" in helper_block:
        raise RuntimeError("Helper vô tình mở quyền Giáo viên.")

    compile(source, str(TARGET), "exec")
    py_compile.compile(str(TARGET), doraise=True)


def main() -> int:
    print("=" * 128)
    print(
        "BÀI 13B-12 V2.4.3.9 - "
        "KHÓA ĐÚNG PHẠM VI LƯU CSVC CHO TÀI KHOẢN ĐƠN VỊ TRƯỜNG"
    )
    print("=" * 128)

    for path in (DB, TARGET):
        if not path.exists():
            print("DỪNG AN TOÀN: thiếu", path)
            return 2

    before = db_state()
    print("integrity_check:", before["integrity"])
    print("foreign_key_check:", before["fk_count"], "lỗi")
    if before["integrity"].lower() != "ok" or before["fk_count"] != 0:
        print("DỪNG: database chưa đạt kiểm tra an toàn.")
        return 3

    accounts = school_account_info()
    print("Tài khoản đơn vị trường đang hoạt động tìm thấy:", len(accounts))
    for row in accounts[:5]:
        print(
            f" - id={row[0]} username={row[1]} school_id={row[2]} "
            f"role_id={row[3]} role_code={row[4]} school={row[5]}"
        )

    source = read_text(TARGET)

    if all(
        marker in source
        for marker in (
            HELPER_MARKER,
            MN_SAVE_MARKER,
            STRUCT_SAVE_MARKER,
            MN_PAGE_MARKER,
            STRUCT_PAGE_MARKER,
        )
    ):
        print("V2.4.3.9 đã được cài trước đó. Không cài lặp.")
        return 0

    try:
        print("Chuẩn bị helper nhận diện tài khoản đơn vị Trường...")
        print("Chuẩn bị patch POST lưu CSVC Mầm non...")
        print("Chuẩn bị patch POST lưu biểu CSVC Tiểu học/THCS...")
        print("Chuẩn bị patch can_edit bằng AST (hỗ trợ nền nhiều dòng)...")
        patched = patch_source(source)
        compile(patched, str(TARGET), "exec")
    except Exception as exc:
        print()
        print("DỪNG AN TOÀN TRƯỚC KHI GHI SOURCE:")
        print(type(exc).__name__ + ":", exc)
        print("Không thay đổi source/database.")
        return 4

    EXPORTS.mkdir(parents=True, exist_ok=True)
    BACKUP.mkdir(parents=True, exist_ok=False)
    backup_file(TARGET)
    backup_db()
    print("Backup:", BACKUP)

    try:
        write_text(TARGET, patched)
        verify_source(read_text(TARGET))

        after = db_state()
        if after["integrity"].lower() != "ok":
            raise RuntimeError("integrity_check không đạt sau cài.")
        if after["fk_count"] != 0:
            raise RuntimeError("foreign_key_check có lỗi sau cài.")

        for table, count in before.items():
            if table in {"integrity", "fk_count"}:
                continue
            if after.get(table) != count:
                raise RuntimeError(
                    f"Số bản ghi {table} thay đổi ngoài dự kiến: "
                    f"{count} -> {after.get(table)}"
                )

        for cache in APP.rglob("__pycache__"):
            if cache.is_dir():
                shutil.rmtree(cache, ignore_errors=True)

    except Exception as exc:
        print()
        print("CÓ LỖI - ĐANG ROLLBACK SOURCE + DATABASE...")
        print(type(exc).__name__ + ":", exc)
        restore_file(TARGET)
        restore_db()
        print("ĐÃ KHÔI PHỤC.")
        return 9

    lines = [
        "=" * 128,
        "BÁO CÁO CÀI BÀI 13B-12 V2.4.3.9A",
        "=" * 128,
        f"Thời gian: {datetime.now():%d/%m/%Y %H:%M:%S}",
        "",
        "MỤC TIÊU:",
        "- Sửa tầng kiểm phạm vi khiến tài khoản truong_... POST CSVC bị forbidden.",
        "- Server tự lấy user.school_id cho cấp Trường.",
        "- Không dùng school_id từ form để quyết định trường đích ở cấp Trường.",
        "- Không đi qua _school_in_scope cũ đối với tài khoản đơn vị Trường.",
        "- Vẫn bắt buộc target_id == user.school_id và trường đang hoạt động.",
        "",
        "PHẠM VI:",
        "- Mầm non: /csvc/{section}.",
        "- Tiểu học/THCS/liên cấp: /bieu-nhap/{slug}.",
        "- Không mở quyền cho Giáo viên.",
        "- Giữ quyền ADMIN/Xã/Phòng ban.",
        "- Giữ _structured_school_supports_level cho TH/THCS.",
        "",
        f"integrity_check: {after['integrity']}",
        f"foreign_key_check: {after['fk_count']} lỗi",
        f"Backup: {BACKUP}",
        "",
        "TÀI KHOẢN ĐƠN VỊ TRƯỜNG PHÁT HIỆN:",
    ]
    lines.extend(
        [
            f"- id={r[0]} username={r[1]} school_id={r[2]} "
            f"role_id={r[3]} role_code={r[4]} school={r[5]}"
            for r in accounts
        ]
    )
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")

    print()
    print("=" * 128)
    print("CÀI ĐẶT THÀNH CÔNG BÀI 13B-12 V2.4.3.9A")
    print("=" * 128)
    print(" - Đơn vị Trường được nhận diện bằng role TRUONG hoặc username truong_: ĐẠT.")
    print(" - Cấp Trường tự khóa school_id về chính trường đang đăng nhập: ĐẠT.")
    print(" - Bỏ nhánh _school_in_scope cũ RIÊNG cho tài khoản đơn vị Trường: ĐẠT.")
    print(" - Giáo viên không được mở quyền CSVC: ĐẠT.")
    print(" - Không sửa dữ liệu hiện có.")
    print("Báo cáo:", REPORT)
    print("Backup:", BACKUP)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
