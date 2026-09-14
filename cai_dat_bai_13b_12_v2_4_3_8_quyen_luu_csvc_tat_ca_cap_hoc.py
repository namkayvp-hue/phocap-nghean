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
TARGET = APP / "routers" / "report_inputs.py"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = EXPORTS / f"backup_bai_13b_12_v2_4_3_8_{STAMP}"
DB_BACKUP = BACKUP / "phocap.db"
REPORT = EXPORTS / f"bao_cao_cai_bai_13b_12_v2_4_3_8_{STAMP}.txt"

MARKER_MN_PAGE = "BAI_13B_12_V2_4_3_8_CSVC_ALL_LEVEL_SCHOOL_WRITE"
MARKER_MN_SAVE = "BAI_13B_12_V2_4_3_8_CSVC_MN_SCHOOL_WRITE"
MARKER_STRUCT_PAGE = "BAI_13B_12_V2_4_3_8_STRUCTURED_ALL_LEVEL_SCHOOL_WRITE"
MARKER_STRUCT_SAVE = "BAI_13B_12_V2_4_3_8_STRUCTURED_SCHOOL_WRITE"

OLD_MN_CAN_EDIT = '            "can_edit": scope["role_code"] in CSVC_EDIT_ROLES,\n'
NEW_MN_CAN_EDIT = '            # === BAI_13B_12_V2_4_3_8_CSVC_ALL_LEVEL_SCHOOL_WRITE ===\n            "can_edit": (\n                scope["role_code"] in CSVC_EDIT_ROLES\n                or scope["role_code"] == SCHOOL_ROLE_CODE\n            ),\n'
OLD_MN_SAVE = '    user = lay_thong_tin_nguoi_dung(request)\n    role = normalize_role_code((user or {}).get("role_code"))\n    if role not in CSVC_EDIT_ROLES:\n        return _redirect_forbidden()\n    form = await request.form()\n    year_id = _parse_int(form.get("school_year_id"), 0, 1)\n    school_id = _parse_int(form.get("school_id"), 0, 1)\n    if not year_id or not school_id or not _school_in_scope(db, request, school_id):\n        return _redirect_forbidden()\n'
NEW_MN_SAVE = '    user = lay_thong_tin_nguoi_dung(request)\n    role = normalize_role_code((user or {}).get("role_code"))\n\n    # === BAI_13B_12_V2_4_3_8_CSVC_MN_SCHOOL_WRITE ===\n    # Tài khoản đơn vị Trường được lưu CSVC của CHÍNH trường mình.\n    # Không tin school_id gửi từ trình duyệt đối với cấp Trường.\n    is_school_unit = (\n        role == SCHOOL_ROLE_CODE\n        and (user or {}).get("school_id") is not None\n    )\n    if role not in CSVC_EDIT_ROLES and not is_school_unit:\n        return _redirect_forbidden()\n\n    form = await request.form()\n    year_id = _parse_int(form.get("school_year_id"), 0, 1)\n    form_school_id = _parse_int(form.get("school_id"), 0, 1)\n\n    if is_school_unit:\n        school_id = _parse_int((user or {}).get("school_id"), 0, 1)\n    else:\n        school_id = form_school_id\n\n    if not year_id or not school_id or not _school_in_scope(db, request, school_id):\n        return _redirect_forbidden()\n'
OLD_STRUCT_CAN_EDIT = '            "can_edit": scope["role_code"] in STRUCTURED_FORM_EDIT_ROLES,\n'
NEW_STRUCT_CAN_EDIT = '            # === BAI_13B_12_V2_4_3_8_STRUCTURED_ALL_LEVEL_SCHOOL_WRITE ===\n            "can_edit": (\n                scope["role_code"] in STRUCTURED_FORM_EDIT_ROLES\n                or scope["role_code"] == SCHOOL_ROLE_CODE\n            ),\n'
OLD_STRUCT_SAVE = '    user = lay_thong_tin_nguoi_dung(request)\n    role = normalize_role_code((user or {}).get("role_code"))\n    if role not in STRUCTURED_FORM_EDIT_ROLES:\n        return _redirect_forbidden()\n\n    form = await request.form()\n    year_id = _parse_int(form.get("school_year_id"), 0, 1)\n    school_id = _parse_int(form.get("school_id"), 0, 1)\n    if not year_id or not school_id or not _school_in_scope(db, request, school_id):\n        return _redirect_forbidden()\n'
NEW_STRUCT_SAVE = '    user = lay_thong_tin_nguoi_dung(request)\n    role = normalize_role_code((user or {}).get("role_code"))\n\n    # === BAI_13B_12_V2_4_3_8_STRUCTURED_SCHOOL_WRITE ===\n    # Áp dụng cho TH-01-CSVC, THCS-01-CSVC và mọi biểu trường\n    # cấu trúc dùng chung route /bieu-nhap/{slug}.\n    # Tài khoản đơn vị Trường chỉ được lưu đúng school_id của mình.\n    is_school_unit = (\n        role == SCHOOL_ROLE_CODE\n        and (user or {}).get("school_id") is not None\n    )\n    if role not in STRUCTURED_FORM_EDIT_ROLES and not is_school_unit:\n        return _redirect_forbidden()\n\n    form = await request.form()\n    year_id = _parse_int(form.get("school_year_id"), 0, 1)\n    form_school_id = _parse_int(form.get("school_id"), 0, 1)\n\n    if is_school_unit:\n        school_id = _parse_int((user or {}).get("school_id"), 0, 1)\n    else:\n        school_id = form_school_id\n\n    if not year_id or not school_id or not _school_in_scope(db, request, school_id):\n        return _redirect_forbidden()\n'


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


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(
            f"{label}: cần đúng 1 marker nền, thực tế={count}. "
            "Dừng để tránh sửa nhầm source."
        )
    return source.replace(old, new, 1)


def patch_source(source: str) -> str:
    all_markers = (
        MARKER_MN_PAGE,
        MARKER_MN_SAVE,
        MARKER_STRUCT_PAGE,
        MARKER_STRUCT_SAVE,
    )
    if all(marker in source for marker in all_markers):
        return source

    # Khóa đúng các route đã được khảo sát V2.4.3.7.
    required = (
        "def csvc_input_page(",
        "async def csvc_input_save(",
        "def structured_school_form_page(",
        "async def structured_school_form_save(",
        "CSVC_EDIT_ROLES",
        "STRUCTURED_FORM_EDIT_ROLES",
        "SCHOOL_ROLE_CODE",
        "_school_in_scope",
    )
    for token in required:
        if token not in source:
            raise RuntimeError("Thiếu cấu trúc nền: " + token)

    if MARKER_MN_PAGE not in source:
        source = replace_once(
            source,
            OLD_MN_CAN_EDIT,
            NEW_MN_CAN_EDIT,
            "GET MN CSVC can_edit",
        )

    if MARKER_MN_SAVE not in source:
        source = replace_once(
            source,
            OLD_MN_SAVE,
            NEW_MN_SAVE,
            "POST MN CSVC",
        )

    if MARKER_STRUCT_PAGE not in source:
        source = replace_once(
            source,
            OLD_STRUCT_CAN_EDIT,
            NEW_STRUCT_CAN_EDIT,
            "GET structured CSVC can_edit",
        )

    if MARKER_STRUCT_SAVE not in source:
        source = replace_once(
            source,
            OLD_STRUCT_SAVE,
            NEW_STRUCT_SAVE,
            "POST structured CSVC",
        )

    compile(source, str(TARGET), "exec")
    return source


def verify_source(source: str) -> None:
    for marker in (
        MARKER_MN_PAGE,
        MARKER_MN_SAVE,
        MARKER_STRUCT_PAGE,
        MARKER_STRUCT_SAVE,
    ):
        if marker not in source:
            raise RuntimeError("Verifier thiếu marker: " + marker)

    required = (
        'or scope["role_code"] == SCHOOL_ROLE_CODE',
        "if role not in CSVC_EDIT_ROLES and not is_school_unit:",
        "if role not in STRUCTURED_FORM_EDIT_ROLES and not is_school_unit:",
        'form_school_id = _parse_int(form.get("school_id"), 0, 1)',
        'school_id = _parse_int((user or {}).get("school_id"), 0, 1)',
        "_structured_school_supports_level(",
        "db.commit()",
    )
    for token in required:
        if token not in source:
            raise RuntimeError("Verifier thiếu: " + token)

    # Bảo đảm không vô tình mở quyền giáo viên.
    if 'role == "GIAO_VIEN"' in NEW_MN_SAVE or 'role == "GIAO_VIEN"' in NEW_STRUCT_SAVE:
        raise RuntimeError("Verifier phát hiện mở quyền giáo viên ngoài yêu cầu.")

    compile(source, str(TARGET), "exec")
    py_compile.compile(str(TARGET), doraise=True)


def main() -> int:
    print("=" * 126)
    print(
        "BÀI 13B-12 V2.4.3.8 - "
        "QUYỀN LƯU CSVC CHO TÀI KHOẢN TRƯỜNG Ở TẤT CẢ CẤP HỌC"
    )
    print("=" * 126)

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

    source = read_text(TARGET)

    if all(
        marker in source
        for marker in (
            MARKER_MN_PAGE,
            MARKER_MN_SAVE,
            MARKER_STRUCT_PAGE,
            MARKER_STRUCT_SAVE,
        )
    ):
        print("V2.4.3.8 đã được cài trước đó. Không cài lặp.")
        return 0

    try:
        print("Kiểm tra quyền giao diện MN...")
        print("Kiểm tra POST lưu MN...")
        print("Kiểm tra quyền giao diện TH/THCS...")
        print("Kiểm tra POST lưu TH/THCS...")
        patched = patch_source(source)
    except Exception as exc:
        print()
        print("DỪNG AN TOÀN TRƯỚC KHI GHI SOURCE:")
        print(type(exc).__name__ + ":", exc)
        print("Không có source/database nào bị thay đổi.")
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

        # Bộ cài quyền không được thay đổi bất kỳ số bản ghi nào.
        for table, before_count in before.items():
            if table in {"integrity", "fk_count"}:
                continue
            if after.get(table) != before_count:
                raise RuntimeError(
                    f"Số bản ghi {table} thay đổi ngoài dự kiến: "
                    f"{before_count} -> {after.get(table)}"
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

    REPORT.write_text(
        "\n".join(
            [
                "=" * 126,
                "BÁO CÁO CÀI BÀI 13B-12 V2.4.3.8",
                "=" * 126,
                f"Thời gian: {datetime.now():%d/%m/%Y %H:%M:%S}",
                "",
                "PHẠM VI QUYỀN:",
                "- Tài khoản đơn vị Trường (role TRUONG) được nhập/lưu CSVC.",
                "- Mầm non: /csvc/{section}.",
                "- Tiểu học: /bieu-nhap/th-01-csvc.",
                "- THCS: /bieu-nhap/thcs-01-csvc.",
                "- Trường liên cấp dùng cùng route structured và vẫn kiểm tra cấp học phù hợp.",
                "",
                "NGUYÊN TẮC AN TOÀN:",
                "- Cấp Trường KHÔNG được tin school_id gửi từ form.",
                "- Server tự ép school_id = user.school_id.",
                "- Trường chỉ sửa đúng dữ liệu của chính trường mình.",
                "- Không mở quyền lưu CSVC cho Giáo viên.",
                "- Quyền ADMIN/Xã/Phòng ban đang có được giữ nguyên.",
                "- Kiểm tra _structured_school_supports_level vẫn được giữ.",
                "",
                "KHÔNG ĐỤNG:",
                "- dữ liệu CSVC hiện có;",
                "- Excel điều tra;",
                "- 7 biểu Mầm non;",
                "- nghiệp vụ PCGD/XMC;",
                "- phân công/giao phiếu.",
                "",
                f"integrity_check: {after['integrity']}",
                f"foreign_key_check: {after['fk_count']} lỗi",
                f"Backup: {BACKUP}",
            ]
        ) + "\n",
        encoding="utf-8-sig",
    )

    print()
    print("=" * 126)
    print("CÀI ĐẶT THÀNH CÔNG BÀI 13B-12 V2.4.3.8")
    print("=" * 126)
    print(" - Mầm non: tài khoản Trường được lưu CSVC của chính trường: ĐẠT.")
    print(" - Tiểu học: tài khoản Trường được lưu CSVC của chính trường: ĐẠT.")
    print(" - THCS: tài khoản Trường được lưu CSVC của chính trường: ĐẠT.")
    print(" - Không mở quyền cho Giáo viên.")
    print(" - Không sửa dữ liệu hiện có.")
    print("Báo cáo:", REPORT)
    print("Backup:", BACKUP)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
