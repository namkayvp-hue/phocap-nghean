# -*- coding: utf-8 -*-
from __future__ import annotations

import ast
import importlib.util
import py_compile
import shutil
import sqlite3
from datetime import datetime
from io import BytesIO
from pathlib import Path

from openpyxl import Workbook, load_workbook

PROJECT = Path(r"C:\PhoCap")
APP = PROJECT / "app"
DB = PROJECT / "data" / "phocap.db"
EXPORTS = PROJECT / "exports"

EXCHANGE = APP / "household_excel_exchange.py"
HELPER = APP / "household_field_excel_v240.py"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = EXPORTS / f"backup_bai_13b_12_v2_4_1_3_{STAMP}"
DB_BACKUP = BACKUP / "phocap.db"
REPORT = EXPORTS / f"bao_cao_cai_bai_13b_12_v2_4_1_3_{STAMP}.txt"

MARKER_EXCHANGE = "BAI_13B_12_V2_4_1_3_INVESTIGATOR_NAMES_START"
MARKER_HELPER = "BAI_13B_12_V2_4_1_3_SIGNATURE_3_INVESTIGATORS"

NEW_SIGNATURE = 'def _fill_signature(\n    ws: Any,\n    row: int,\n    head_name: str,\n    investigator_names: list[str] | None = None,\n) -> int:\n    """Khối ký: Chủ hộ | CÁN BỘ ĐIỀU TRA (3 người) | UBND xã/phường."""\n    names = [\n        _text(item)\n        for item in (investigator_names or [])\n        if _text(item)\n    ][:3]\n    while len(names) < 3:\n        names.append("")\n\n    # Dòng 1: chỉ một tiêu đề chung CÁN BỘ ĐIỀU TRA.\n    ws.merge_cells(\n        start_row=row,\n        start_column=1,\n        end_row=row,\n        end_column=2,\n    )\n    ws.cell(row, 1).value = "HỌ, TÊN CHỦ HỘ"\n\n    ws.merge_cells(\n        start_row=row,\n        start_column=3,\n        end_row=row,\n        end_column=8,\n    )\n    ws.cell(row, 3).value = "CÁN BỘ ĐIỀU TRA"\n\n    ws.merge_cells(\n        start_row=row,\n        start_column=9,\n        end_row=row,\n        end_column=11,\n    )\n    ws.cell(row, 9).value = "XÁC NHẬN CỦA UBND PHƯỜNG/XÃ"\n\n    # Dòng 2-4: 3 người điều tra nằm dưới đúng một tiêu đề chung.\n    signature_start = row + 1\n    signature_end = row + 4\n\n    ws.merge_cells(\n        start_row=signature_start,\n        start_column=1,\n        end_row=signature_end,\n        end_column=2,\n    )\n    head_cell = ws.cell(signature_start, 1)\n    head_cell.value = (\n        f"{head_name or \'\'}\\n"\n        "(Ký, ghi rõ họ tên)"\n    )\n\n    investigator_ranges = (\n        (3, 4),\n        (5, 6),\n        (7, 8),\n    )\n    for index, ((c1, c2), name) in enumerate(\n        zip(investigator_ranges, names),\n        start=1,\n    ):\n        ws.merge_cells(\n            start_row=signature_start,\n            start_column=c1,\n            end_row=signature_end,\n            end_column=c2,\n        )\n        cell = ws.cell(signature_start, c1)\n        cell.value = (\n            (name + "\\n") if name else ""\n        ) + "(Ký, ghi rõ họ tên)"\n        cell.font = Font(\n            name="Times New Roman",\n            size=7,\n            bold=True,\n        )\n        cell.alignment = Alignment(\n            horizontal="center",\n            vertical="top",\n            wrap_text=True,\n        )\n\n    ws.merge_cells(\n        start_row=signature_start,\n        start_column=9,\n        end_row=signature_end,\n        end_column=11,\n    )\n    ubnd_cell = ws.cell(signature_start, 9)\n    ubnd_cell.value = "(Ký tên, đóng dấu)"\n\n    # Định dạng tiêu đề và hai khối ngoài.\n    for col in (1, 3, 9):\n        cell = ws.cell(row, col)\n        cell.font = Font(\n            name="Times New Roman",\n            size=7,\n            bold=True,\n        )\n        cell.alignment = Alignment(\n            horizontal="center",\n            vertical="center",\n            wrap_text=True,\n        )\n\n    for cell in (head_cell, ubnd_cell):\n        cell.font = Font(\n            name="Times New Roman",\n            size=7,\n            bold=True,\n        )\n        cell.alignment = Alignment(\n            horizontal="center",\n            vertical="top",\n            wrap_text=True,\n        )\n\n    ws.row_dimensions[row].height = 14\n    for r in range(signature_start, signature_end + 1):\n        ws.row_dimensions[r].height = 14\n\n    return signature_end + 1\n\n\n'
GET_NAMES_HELPER = '\n# === BAI_13B_12_V2_4_1_3_INVESTIGATOR_NAMES_START ===\ndef _field_excel_investigator_names(\n    db: Session,\n    forms: list[SurveyForm],\n) -> dict[int, list[str]]:\n    """Lấy tối đa 3 người điều tra thực tế của từng phiếu, bỏ tài khoản đơn vị trường."""\n    result: dict[int, list[str]] = {}\n\n    for survey_form in forms:\n        rows = db.execute(\n            select(\n                User.full_name,\n                User.username,\n                SurveyFormInvestigator.order_number,\n                SurveyFormInvestigator.notes,\n                SurveyFormInvestigator.id,\n            )\n            .join(\n                SurveyFormInvestigator,\n                SurveyFormInvestigator.user_id == User.id,\n            )\n            .where(\n                SurveyFormInvestigator.survey_form_id == int(survey_form.id)\n            )\n            .order_by(\n                SurveyFormInvestigator.order_number,\n                SurveyFormInvestigator.id,\n            )\n        ).all()\n\n        candidates: list[tuple[str, str, str]] = []\n        for full_name, username, _order_number, notes, _assignment_id in rows:\n            name = " ".join(str(full_name or "").split())\n            login_name = str(username or "").strip().lower()\n            note_text = str(notes or "")\n\n            if not name:\n                continue\n\n            # Tài khoản đơn vị trường không phải cá nhân ký phiếu.\n            if login_name.startswith("truong_"):\n                continue\n\n            candidates.append((name, login_name, note_text))\n\n        # Ưu tiên đúng thành viên của "Tổ điều tra 3 cấp" nếu lịch sử còn bản ghi khác.\n        team_rows = [\n            item\n            for item in candidates\n            if "tổ điều tra 3 cấp" in item[2].casefold()\n        ]\n        chosen = team_rows if len(team_rows) >= 3 else candidates\n\n        names: list[str] = []\n        seen: set[str] = set()\n        for name, _login_name, _note_text in chosen:\n            key = name.casefold()\n            if key in seen:\n                continue\n            seen.add(key)\n            names.append(name)\n            if len(names) >= 3:\n                break\n\n        result[int(survey_form.id)] = names\n\n    return result\n# === BAI_13B_12_V2_4_1_3_INVESTIGATOR_NAMES_END ===\n\n\n'


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
            "survey_forms",
            "survey_people",
            "survey_form_investigators",
            "survey_person_year_records",
        ):
            result[table] = int(
                con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
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


def function_node(tree: ast.Module, name: str):
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise RuntimeError(f"Không xác định được hàm {name} bằng AST.")


def replace_function_ast(source: str, name: str, replacement: str) -> str:
    tree = ast.parse(source)
    node = function_node(tree, name)
    lines = source.splitlines(keepends=True)
    start = node.lineno - 1
    end = int(getattr(node, "end_lineno", node.lineno) or node.lineno)

    if not replacement.endswith("\n"):
        replacement += "\n"

    result = "".join(lines[:start] + [replacement] + lines[end:])
    ast.parse(result)
    return result


def patch_exchange(source: str) -> str:
    if MARKER_EXCHANGE in source:
        return source

    required = (
        "SurveyFormInvestigator",
        "from app.models import Classroom, School, SchoolYear, User",
        "def export_household_excel(",
        "add_field_form_view_to_bytes",
    )
    for token in required:
        if token not in source:
            raise RuntimeError("Exchange thiếu nền cần thiết: " + token)

    # Chèn helper trước export_household_excel.
    anchor = "def export_household_excel("
    if source.count(anchor) != 1:
        raise RuntimeError(
            f"Số hàm export_household_excel bất thường: {source.count(anchor)}"
        )
    source = source.replace(
        anchor,
        GET_NAMES_HELPER + anchor,
        1,
    )

    # Đổi đúng lời gọi V2.4.1: truyền mapping 3 người điều tra.
    old = "        content = add_field_form_view_to_bytes(content)\n"
    if source.count(old) != 1:
        raise RuntimeError(
            "Không tìm thấy đúng một lời gọi add_field_form_view_to_bytes(content)."
        )
    new = """        investigator_names_by_form_id = _field_excel_investigator_names(
            db,
            forms,
        )
        content = add_field_form_view_to_bytes(
            content,
            investigator_names_by_form_id=investigator_names_by_form_id,
        )
"""
    source = source.replace(old, new, 1)
    ast.parse(source)
    return source


def patch_helper(source: str) -> str:
    if MARKER_HELPER in source:
        return source

    required = (
        "def _fill_signature(",
        "def add_field_form_view_to_bytes(",
        "spec_index",
        "_fill_signature(",
    )
    for token in required:
        if token not in source:
            raise RuntimeError("Helper thiếu nền V2.4.1.2A: " + token)

    # 1. Thay khối ký bằng AST.
    replacement = (
        "# === BAI_13B_12_V2_4_1_3_SIGNATURE_3_INVESTIGATORS ===\n"
        + NEW_SIGNATURE
    )
    source = replace_function_ast(
        source,
        "_fill_signature",
        replacement,
    )

    # 2. Bổ sung tham số mapping vào hàm add_field_form_view_to_bytes.
    tree = ast.parse(source)
    add_node = function_node(tree, "add_field_form_view_to_bytes")
    lines = source.splitlines(keepends=True)
    start = add_node.lineno - 1
    end = int(getattr(add_node, "end_lineno", add_node.lineno) or add_node.lineno)
    block = "".join(lines[start:end])

    old_sig = "def add_field_form_view_to_bytes(content: bytes) -> bytes:"
    if old_sig not in block:
        raise RuntimeError(
            "Chữ ký add_field_form_view_to_bytes không đúng nền V2.4.1.2A."
        )
    block = block.replace(
        old_sig,
        """def add_field_form_view_to_bytes(
    content: bytes,
    investigator_names_by_form_id: dict[int, list[str]] | None = None,
) -> bytes:""",
        1,
    )

    # 3. Trước khi chia trang, gắn 3 tên đúng theo form_id.
    loop_anchor = "    for spec_index, spec in enumerate(specs, start=1):\n"
    if loop_anchor not in block:
        raise RuntimeError(
            "Không tìm thấy vòng lặp spec trong add_field_form_view_to_bytes."
        )
    loop_new = """    investigator_names_by_form_id = (
        investigator_names_by_form_id or {}
    )

    for spec_index, spec in enumerate(specs, start=1):
        try:
            form_key = int(spec.get("form_id") or 0)
        except (TypeError, ValueError):
            form_key = 0
        spec["investigator_names"] = list(
            investigator_names_by_form_id.get(form_key, [])
        )[:3]
"""
    block = block.replace(loop_anchor, loop_new, 1)

    # 4. Truyền danh sách 3 người vào khối ký.
    old_call = """                current_row = _fill_signature(
                    ws,
                    current_row,
                    str(spec.get("head_name") or ""),
                )
"""
    if old_call not in block:
        raise RuntimeError(
            "Không tìm thấy lời gọi _fill_signature trong helper hiện tại."
        )
    new_call = """                current_row = _fill_signature(
                    ws,
                    current_row,
                    str(spec.get("head_name") or ""),
                    investigator_names=list(
                        spec.get("investigator_names") or []
                    ),
                )
"""
    block = block.replace(old_call, new_call, 1)

    source = "".join(lines[:start] + [block] + lines[end:])
    ast.parse(source)
    return source


def load_helper():
    spec = importlib.util.spec_from_file_location(
        "field_excel_v2413_test",
        HELPER,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Không nạp được helper.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def smoke_test_signature() -> None:
    module = load_helper()

    wb = Workbook()
    ws = wb.active
    ws.title = "Test"

    next_row = module._fill_signature(
        ws,
        1,
        "TEST CHỦ HỘ",
        [
            "Nguyễn Văn MN",
            "Trần Văn TH",
            "Lê Văn THCS",
        ],
    )

    if next_row != 6:
        raise RuntimeError(
            f"Smoke test dòng trả về bất thường: {next_row}"
        )

    if ws["C1"].value != "CÁN BỘ ĐIỀU TRA":
        raise RuntimeError("Thiếu tiêu đề chung CÁN BỘ ĐIỀU TRA.")

    expected = (
        "Nguyễn Văn MN",
        "Trần Văn TH",
        "Lê Văn THCS",
    )
    actual = (
        str(ws["C2"].value or ""),
        str(ws["E2"].value or ""),
        str(ws["G2"].value or ""),
    )

    for name, value in zip(expected, actual):
        if name not in value:
            raise RuntimeError(
                f"Smoke test thiếu tên người điều tra: {name}"
            )

    merged = {str(item) for item in ws.merged_cells.ranges}
    for required in ("C1:H1", "C2:D5", "E2:F5", "G2:H5"):
        if required not in merged:
            raise RuntimeError(
                "Smoke test thiếu vùng merge: " + required
            )


def verify_sources() -> None:
    exchange = read_text(EXCHANGE)
    helper = read_text(HELPER)

    for token in (
        MARKER_EXCHANGE,
        "_field_excel_investigator_names",
        "investigator_names_by_form_id",
        'login_name.startswith("truong_")',
        '"tổ điều tra 3 cấp"',
    ):
        if token not in exchange:
            raise RuntimeError("Verifier exchange thiếu: " + token)

    for token in (
        MARKER_HELPER,
        "CÁN BỘ ĐIỀU TRA",
        "investigator_names: list[str] | None",
        'spec["investigator_names"]',
        "C1",
    ):
        if token not in helper:
            raise RuntimeError("Verifier helper thiếu: " + token)

    ast.parse(exchange)
    ast.parse(helper)
    py_compile.compile(str(EXCHANGE), doraise=True)
    py_compile.compile(str(HELPER), doraise=True)
    smoke_test_signature()


def main() -> int:
    print("=" * 124)
    print(
        "BÀI 13B-12 V2.4.1.3 - "
        "MỘT DÒNG CÁN BỘ ĐIỀU TRA + 3 NGƯỜI KÝ"
    )
    print("=" * 124)

    for path in (DB, EXCHANGE, HELPER):
        if not path.exists():
            print("DỪNG AN TOÀN: thiếu", path)
            return 2

    before = db_state()
    print("integrity_check:", before["integrity"])
    print("foreign_key_check:", before["fk_count"], "lỗi")

    if before["integrity"].lower() != "ok" or before["fk_count"] != 0:
        print("DỪNG: database chưa đạt kiểm tra an toàn.")
        return 3

    try:
        new_exchange = patch_exchange(read_text(EXCHANGE))
        new_helper = patch_helper(read_text(HELPER))
        ast.parse(new_exchange)
        ast.parse(new_helper)
    except Exception as exc:
        print()
        print("DỪNG AN TOÀN TRƯỚC KHI GHI SOURCE:")
        print(type(exc).__name__ + ":", exc)
        return 4

    EXPORTS.mkdir(parents=True, exist_ok=True)
    BACKUP.mkdir(parents=True, exist_ok=False)
    backup_file(EXCHANGE)
    backup_file(HELPER)
    backup_db()
    print("Backup:", BACKUP)

    try:
        write_text(EXCHANGE, new_exchange)
        write_text(HELPER, new_helper)

        verify_sources()

        after = db_state()
        if after["integrity"].lower() != "ok":
            raise RuntimeError(
                "integrity_check không đạt sau cài."
            )
        if after["fk_count"] != 0:
            raise RuntimeError(
                "foreign_key_check có lỗi sau cài."
            )

        for table in (
            "survey_forms",
            "survey_people",
            "survey_form_investigators",
            "survey_person_year_records",
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
        restore_file(EXCHANGE)
        restore_file(HELPER)
        restore_db()
        print("ĐÃ KHÔI PHỤC.")
        return 9

    REPORT.write_text(
        "\n".join(
            [
                "=" * 124,
                "BÁO CÁO CÀI BÀI 13B-12 V2.4.1.3",
                "=" * 124,
                f"Thời gian: {datetime.now():%d/%m/%Y %H:%M:%S}",
                "",
                "ĐÃ SỬA KHỐI KÝ PHIẾU EXCEL:",
                "- Chỉ còn MỘT tiêu đề chung: CÁN BỘ ĐIỀU TRA.",
                "- Ngay dưới tiêu đề là 3 ô ký của 3 thành viên tổ điều tra.",
                "- Tên 3 người lấy trực tiếp từ survey_form_investigators.",
                "- Bỏ tài khoản đơn vị trường truong_... khỏi danh sách ký.",
                "- Ưu tiên bản ghi có ghi chú Tổ điều tra 3 cấp.",
                "- Bên trái vẫn là HỌ, TÊN CHỦ HỘ.",
                "- Bên phải vẫn là XÁC NHẬN CỦA UBND PHƯỜNG/XÃ.",
                "",
                "KHÔNG THAY:",
                "- nội dung phiếu;",
                "- xuất/nhập Excel 2.2.3 -> 2.2.4;",
                "- phân công tổ;",
                "- giao phiếu;",
                "- nhập nhanh;",
                "- PCGD/XMC;",
                "- dữ liệu hiện có.",
                "",
                "SMOKE TEST KHỐI KÝ: ĐẠT",
                f"integrity_check: {after['integrity']}",
                f"foreign_key_check: {after['fk_count']} lỗi",
                f"Backup: {BACKUP}",
            ]
        ) + "\n",
        encoding="utf-8-sig",
    )

    print()
    print("=" * 124)
    print("CÀI ĐẶT THÀNH CÔNG BÀI 13B-12 V2.4.1.3")
    print("=" * 124)
    print(" - Một dòng CÁN BỘ ĐIỀU TRA: ĐẠT.")
    print(" - 3 người điều tra có tên riêng để ký: ĐẠT.")
    print(" - Không sửa dữ liệu hiện có.")
    print("Báo cáo:", REPORT)
    print("Backup:", BACKUP)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
