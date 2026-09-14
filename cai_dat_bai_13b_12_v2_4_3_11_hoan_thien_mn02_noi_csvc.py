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
ROUTER = APP / "routers" / "pcgdmn_template_report.py"
TEMPLATE = APP / "templates" / "reports" / "pcgdmn_template_report.html"
EXPORTS = PROJECT / "exports"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = EXPORTS / f"backup_bai_13b_12_v2_4_3_11_{STAMP}"
DB_BACKUP = BACKUP / "phocap.db"
REPORT = EXPORTS / f"bao_cao_cai_bai_13b_12_v2_4_3_11_{STAMP}.txt"

MARKER = "BAI_13B_12_V2_4_3_11_MN02_CSVC_REAL_DATA"
HELPERS = '\n# === BAI_13B_12_V2_4_3_11_MN02_CSVC_REAL_DATA_START ===\ndef _b24311_int(value: Any) -> int:\n    try:\n        return max(0, int(value or 0))\n    except (TypeError, ValueError):\n        return 0\n\n\ndef _b24311_ratio(numerator: int, denominator: int) -> float | None:\n    if int(denominator or 0) <= 0:\n        return None\n    return round(float(numerator or 0) / float(denominator), 2)\n\n\ndef _b24311_load_mn02_csvc(\n    db: Session,\n    context: dict[str, Any],\n) -> dict[str, Any]:\n    report_data = context.get("report_data") or {}\n    school_year = report_data.get("school_year")\n\n    year_id = context.get("selected_year_id")\n    if year_id is None and school_year is not None:\n        year_id = getattr(school_year, "id", None)\n\n    school_id = context.get("selected_school_id")\n    commune_id = context.get("selected_commune_id")\n\n    result = {\n        "has_csvc": False,\n        "record_count": 0,\n        "school_count_with_csvc": 0,\n        "independent_facility_count": None,\n        "satellite_site_count": None,\n        "classes_34": None,\n        "classes_5": None,\n        "classes_total": None,\n        "preschool_rooms": None,\n        "room_ratio": None,\n        "equipped_total": None,\n        "equipped_34": None,\n        "equipped_5": None,\n        "equipment_age_split_known": False,\n    }\n\n    if year_id is None:\n        return result\n\n    filters = ["c.school_year_id = :year_id"]\n    params: dict[str, Any] = {"year_id": int(year_id)}\n\n    if school_id is not None:\n        filters.append("c.school_id = :school_id")\n        params["school_id"] = int(school_id)\n    elif commune_id is not None:\n        filters.append("s.commune_id = :commune_id")\n        params["commune_id"] = int(commune_id)\n\n    sql = """\n        SELECT\n            c.school_id,\n            c.satellite_site_count,\n            c.preschool_class_3_4_count,\n            c.preschool_class_5_count,\n            c.permanent_preschool_room_count,\n            c.semi_permanent_preschool_room_count,\n            c.temporary_preschool_room_count,\n            c.equipped_preschool_class_count\n        FROM school_mn01_csvc_inputs AS c\n        JOIN schools AS s\n          ON s.id = c.school_id\n        WHERE {where_sql}\n    """.format(where_sql=" AND ".join(filters))\n\n    rows = list(\n        db.execute(\n            text(sql),\n            params,\n        ).mappings().all()\n    )\n\n    if not rows:\n        return result\n\n    result["has_csvc"] = True\n    result["record_count"] = len(rows)\n    result["school_count_with_csvc"] = len(\n        {int(row["school_id"]) for row in rows}\n    )\n\n    satellite = sum(\n        _b24311_int(row["satellite_site_count"])\n        for row in rows\n    )\n    classes_34 = sum(\n        _b24311_int(row["preschool_class_3_4_count"])\n        for row in rows\n    )\n    classes_5 = sum(\n        _b24311_int(row["preschool_class_5_count"])\n        for row in rows\n    )\n    rooms = sum(\n        _b24311_int(row["permanent_preschool_room_count"])\n        + _b24311_int(row["semi_permanent_preschool_room_count"])\n        + _b24311_int(row["temporary_preschool_room_count"])\n        for row in rows\n    )\n    equipped = sum(\n        _b24311_int(row["equipped_preschool_class_count"])\n        for row in rows\n    )\n    total_classes = classes_34 + classes_5\n\n    result.update(\n        {\n            "satellite_site_count": satellite,\n            "classes_34": classes_34,\n            "classes_5": classes_5,\n            "classes_total": total_classes,\n            "preschool_rooms": rooms,\n            "room_ratio": _b24311_ratio(rooms, total_classes),\n            "equipped_total": equipped,\n        }\n    )\n\n    if total_classes > 0 and equipped >= total_classes:\n        result["equipped_34"] = classes_34\n        result["equipped_5"] = classes_5\n        result["equipment_age_split_known"] = True\n    elif equipped == 0:\n        result["equipped_34"] = 0\n        result["equipped_5"] = 0\n        result["equipment_age_split_known"] = True\n\n    table_exists = db.execute(\n        text(\n            """\n            SELECT 1\n            FROM sqlite_master\n            WHERE type=\'table\'\n              AND name=\'school_site_year_records\'\n            LIMIT 1\n            """\n        )\n    ).scalar()\n\n    if table_exists is not None:\n        site_filters = ["school_year_id = :year_id"]\n        site_params: dict[str, Any] = {"year_id": int(year_id)}\n\n        if school_id is not None:\n            site_filters.append("school_id = :site_school_id")\n            site_params["site_school_id"] = int(school_id)\n        elif commune_id is not None:\n            site_filters.append(\n                "school_id IN (SELECT id FROM schools "\n                "WHERE commune_id = :site_commune_id)"\n            )\n            site_params["site_commune_id"] = int(commune_id)\n\n        independent = db.execute(\n            text(\n                """\n                SELECT COUNT(*)\n                FROM school_site_year_records\n                WHERE {where_sql}\n                  AND COALESCE(is_active, 1) = 1\n                  AND COALESCE(is_independent, 0) = 1\n                """.format(\n                    where_sql=" AND ".join(site_filters)\n                )\n            ),\n            site_params,\n        ).scalar()\n\n        result["independent_facility_count"] = int(independent or 0)\n\n    return result\n\n\ndef _b24311_apply_mn02_csvc(\n    ws: Any,\n    csvc: dict[str, Any],\n    context: dict[str, Any],\n    staff_ratios: dict[str, float | None],\n) -> None:\n    if not csvc.get("has_csvc"):\n        ws["V8"] = "Thiếu dữ liệu CSVC"\n        ws["V9"] = "Thiếu dữ liệu CSVC"\n        return\n\n    independent = csvc.get("independent_facility_count")\n    satellite = csvc.get("satellite_site_count")\n\n    if independent is not None:\n        ws["E8"] = independent\n        ws["E9"] = independent\n\n    if satellite is not None:\n        ws["F8"] = satellite\n        ws["F9"] = satellite\n\n    row_specs = (\n        (8, "classes_34", "age_34", "equipped_34"),\n        (9, "classes_5", "age_5", "equipped_5"),\n    )\n\n    for row_number, class_key, staff_key, equipment_key in row_specs:\n        class_count = csvc.get(class_key)\n        if class_count is not None:\n            class_count = _b24311_int(class_count)\n            ws.cell(row_number, 7).value = class_count\n\n            single = ws.cell(row_number, 8).value\n            mixed = ws.cell(row_number, 9).value\n            try:\n                split_total = int(single or 0) + int(mixed or 0)\n            except (TypeError, ValueError):\n                split_total = -1\n\n            if split_total != class_count:\n                ws.cell(row_number, 8).value = None\n                ws.cell(row_number, 9).value = None\n\n        staff_ratio = staff_ratios.get(staff_key)\n        ws.cell(row_number, 19).value = staff_ratio\n        if staff_ratio is not None:\n            ws.cell(row_number, 19).number_format = "0.00"\n\n        room_ratio = csvc.get("room_ratio")\n        ws.cell(row_number, 20).value = room_ratio\n        if room_ratio is not None:\n            ws.cell(row_number, 20).number_format = "0.00"\n\n        equipped_value = csvc.get(equipment_key)\n        ws.cell(row_number, 21).value = equipped_value\n\n        missing: list[str] = []\n        if staff_ratio is None:\n            missing.append("phân nhóm GV")\n        if room_ratio is None:\n            missing.append("phòng/lớp")\n        if not csvc.get("equipment_age_split_known"):\n            missing.append("TBDH theo độ tuổi")\n\n        if missing:\n            ws.cell(row_number, 22).value = (\n                "Chưa đủ dữ liệu: " + ", ".join(missing)\n            )\n        elif context.get("selected_school_id") is not None:\n            ws.cell(row_number, 22).value = "Chưa kết luận cấp xã"\n        else:\n            ws.cell(row_number, 22).value = "Chờ kết luận cấp xã"\n# === BAI_13B_12_V2_4_3_11_MN02_CSVC_REAL_DATA_END ===\n'


def read_text(path: Path) -> str:
    if not path.exists():
        raise RuntimeError(f"Không tìm thấy tệp bắt buộc: {path}")
    return path.read_text(encoding="utf-8-sig", errors="replace")


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
    source = sqlite3.connect(str(DB))
    target = sqlite3.connect(str(DB_BACKUP))
    try:
        source.backup(target)
        target.commit()
    finally:
        target.close()
        source.close()


def restore_db() -> None:
    if not DB_BACKUP.exists():
        return
    source = sqlite3.connect(str(DB_BACKUP))
    target = sqlite3.connect(str(DB))
    try:
        source.backup(target)
        target.commit()
    finally:
        target.close()
        source.close()


def db_state() -> dict[str, object]:
    con = sqlite3.connect(str(DB))
    try:
        state: dict[str, object] = {
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
            "survey_forms",
            "survey_people",
        ):
            exists = con.execute(
                "SELECT 1 FROM sqlite_master "
                "WHERE type='table' AND name=?",
                (table,),
            ).fetchone()
            state[table] = (
                int(
                    con.execute(
                        f'SELECT COUNT(*) FROM "{table}"'
                    ).fetchone()[0]
                )
                if exists
                else None
            )
        return state
    finally:
        con.close()


def function_span(source: str, name: str) -> tuple[int, int]:
    tree = ast.parse(source)
    hits = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == name
    ]
    if len(hits) != 1:
        raise RuntimeError(
            f"Không xác định duy nhất function {name}: {len(hits)}"
        )

    node = hits[0]
    if node.end_lineno is None:
        raise RuntimeError(f"AST không có end_lineno cho {name}")

    lines = source.splitlines(keepends=True)
    start_line = node.lineno - 1
    end_line = node.end_lineno
    start = sum(len(x) for x in lines[:start_line])
    end = sum(len(x) for x in lines[:end_line])
    return start, end


def insert_before_function(source: str, name: str, block: str) -> str:
    start, _end = function_span(source, name)
    return source[:start] + block.strip() + "\n\n\n" + source[start:]


def ensure_text_import(source: str) -> str:
    if "from sqlalchemy import text" in source:
        return source

    tree = ast.parse(source)
    imports = [
        node
        for node in tree.body
        if isinstance(node, (ast.Import, ast.ImportFrom))
    ]
    if not imports:
        raise RuntimeError("Không tìm thấy vùng import của router.")

    last = max(imports, key=lambda node: node.end_lineno or node.lineno)
    lines = source.splitlines(keepends=True)
    index = int(last.end_lineno or last.lineno)
    lines.insert(index, "from sqlalchemy import text\n")
    return "".join(lines)


def patch_build_template(source: str) -> str:
    start, end = function_span(source, "build_template_workbook")
    func = source[start:end]

    required = (
        "staff_ratios = _staff_ratios_by_age(staff_data)",
        'mn02_ws = _get_sheet(workbook, "MN-02")',
        'mn02_ws["S8"] = staff_ratios["age_34"]',
        'mn02_ws["S9"] = staff_ratios["age_5"]',
        'mn02_ws["V8"] = "Thiếu dữ liệu CSVC"',
        'mn02_ws["V9"] = "Thiếu dữ liệu CSVC"',
    )
    for token in required:
        if token not in func:
            raise RuntimeError(
                "build_template_workbook khác nền dự kiến. Thiếu: "
                + token
            )

    old = (
        '    staff_ratios = _staff_ratios_by_age(staff_data)\n'
        '    mn02_ws = _get_sheet(workbook, "MN-02")\n'
        '    mn02_ws["S8"] = staff_ratios["age_34"]\n'
        '    mn02_ws["S9"] = staff_ratios["age_5"]\n'
        '    mn02_ws["V8"] = "Thiếu dữ liệu CSVC"\n'
        '    mn02_ws["V9"] = "Thiếu dữ liệu CSVC"\n'
    )

    new = (
        '    staff_ratios = _staff_ratios_by_age(staff_data)\n'
        '    mn02_ws = _get_sheet(workbook, "MN-02")\n'
        '    mn02_csvc = _b24311_load_mn02_csvc(db, context)\n'
        '    _b24311_apply_mn02_csvc(\n'
        '        mn02_ws,\n'
        '        mn02_csvc,\n'
        '        context,\n'
        '        staff_ratios,\n'
        '    )\n'
    )

    if old not in func:
        raise RuntimeError(
            "Không tìm thấy đúng khối MN-02 hardcode để thay."
        )

    func = func.replace(old, new, 1)
    return source[:start] + func + source[end:]


def patch_router(source: str) -> str:
    if MARKER in source:
        return source

    required = (
        "def _write_mn02(",
        "def _staff_ratios_by_age(",
        "def build_template_workbook(",
        'mn02_ws["V8"] = "Thiếu dữ liệu CSVC"',
        'mn02_ws["V9"] = "Thiếu dữ liệu CSVC"',
        "Session",
        "Any",
    )
    for token in required:
        if token not in source:
            raise RuntimeError(
                "pcgdmn_template_report.py khác nền dự kiến. Thiếu: "
                + token
            )

    source = ensure_text_import(source)
    source = insert_before_function(
        source,
        "build_template_workbook",
        HELPERS,
    )
    source = patch_build_template(source)

    ast.parse(source)
    compile(source, str(ROUTER), "exec")
    return source


def patch_template(source: str) -> str:
    old_csvc = '<span class="badge next">Bài 13C – đang chuẩn bị</span>'
    new_csvc = '<span class="badge ready">Đã có dữ liệu CSVC</span>'

    old_mn02 = '<span class="badge partial">Điền phần dữ liệu trẻ</span>'
    new_mn02 = (
        '<span class="badge ready">'
        'Tự động tổng hợp trẻ + GV + CSVC</span>'
    )

    if old_csvc in source:
        source = source.replace(old_csvc, new_csvc, 1)
    if old_mn02 in source:
        source = source.replace(old_mn02, new_mn02, 1)
    return source


def verify_router(source: str) -> None:
    required = (
        MARKER,
        "def _b24311_load_mn02_csvc(",
        "def _b24311_apply_mn02_csvc(",
        "mn02_csvc = _b24311_load_mn02_csvc(db, context)",
        "_b24311_apply_mn02_csvc(",
        "school_mn01_csvc_inputs",
        "preschool_class_3_4_count",
        "preschool_class_5_count",
        "equipped_preschool_class_count",
        "permanent_preschool_room_count",
        "Chưa kết luận cấp xã",
    )
    for token in required:
        if token not in source:
            raise RuntimeError("Verifier router thiếu: " + token)

    start, end = function_span(source, "build_template_workbook")
    func = source[start:end]
    if 'mn02_ws["V8"] = "Thiếu dữ liệu CSVC"' in func:
        raise RuntimeError("Vẫn còn hardcode V8 trong builder.")
    if 'mn02_ws["V9"] = "Thiếu dữ liệu CSVC"' in func:
        raise RuntimeError("Vẫn còn hardcode V9 trong builder.")

    ast.parse(source)
    compile(source, str(ROUTER), "exec")
    py_compile.compile(str(ROUTER), doraise=True)


def clear_cache() -> None:
    for cache in APP.rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(cache, ignore_errors=True)


def smoke_database_read() -> list[str]:
    con = sqlite3.connect(str(DB))
    con.row_factory = sqlite3.Row
    try:
        row = con.execute(
            """
            SELECT
                school_id,
                school_year_id,
                satellite_site_count,
                preschool_class_3_4_count,
                preschool_class_5_count,
                permanent_preschool_room_count,
                semi_permanent_preschool_room_count,
                temporary_preschool_room_count,
                equipped_preschool_class_count
            FROM school_mn01_csvc_inputs
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            """
        ).fetchone()

        if row is None:
            return [
                "Chưa có bản ghi CSVC để smoke-test dữ liệu thật; "
                "source vẫn đã được kiểm cú pháp/marker."
            ]

        c34 = int(row["preschool_class_3_4_count"] or 0)
        c5 = int(row["preschool_class_5_count"] or 0)
        rooms = (
            int(row["permanent_preschool_room_count"] or 0)
            + int(row["semi_permanent_preschool_room_count"] or 0)
            + int(row["temporary_preschool_room_count"] or 0)
        )
        equipped = int(row["equipped_preschool_class_count"] or 0)
        total = c34 + c5

        return [
            f"CSVC thật: school_id={row['school_id']}, "
            f"school_year_id={row['school_year_id']}",
            f"Lớp MG 3-4={c34}; lớp MG 5={c5}; tổng={total}",
            f"Phòng MG={rooms}; lớp đủ TBDH={equipped}",
            (
                "Tỷ lệ phòng/lớp="
                + (
                    f"{rooms / total:.2f}"
                    if total > 0
                    else "không xác định"
                )
            ),
        ]
    finally:
        con.close()


def main() -> int:
    print("=" * 132)
    print(
        "BÀI 13B-12 V2.4.3.11 - "
        "HOÀN THIỆN MN-02: NỐI DỮ LIỆU CSVC THẬT"
    )
    print("=" * 132)

    for path in (DB, ROUTER, TEMPLATE):
        if not path.exists():
            print("DỪNG AN TOÀN: thiếu", path)
            return 2

    before = db_state()
    print("integrity_check:", before["integrity"])
    print("foreign_key_check:", before["fk_count"], "lỗi")

    if (
        str(before["integrity"]).lower() != "ok"
        or int(before["fk_count"]) != 0
    ):
        print("DỪNG: database chưa đạt kiểm tra an toàn.")
        return 3

    router_source = read_text(ROUTER)
    template_source = read_text(TEMPLATE)

    try:
        if MARKER in router_source:
            print("V2.4.3.11 đã có marker. Không cài lặp.")
            verify_router(router_source)
            for line in smoke_database_read():
                print(" -", line)
            return 0

        patched_router = patch_router(router_source)
        patched_template = patch_template(template_source)

        ast.parse(patched_router)
        compile(patched_router, str(ROUTER), "exec")

    except Exception as exc:
        print()
        print("DỪNG AN TOÀN TRƯỚC KHI GHI SOURCE:")
        print(type(exc).__name__ + ":", exc)
        print("Không thay đổi source/database.")
        return 4

    EXPORTS.mkdir(parents=True, exist_ok=True)
    BACKUP.mkdir(parents=True, exist_ok=False)
    backup_file(ROUTER)
    backup_file(TEMPLATE)
    backup_db()
    print("Backup:", BACKUP)

    try:
        write_text(ROUTER, patched_router)
        write_text(TEMPLATE, patched_template)
        verify_router(read_text(ROUTER))
        clear_cache()

        after = db_state()
        if str(after["integrity"]).lower() != "ok":
            raise RuntimeError("integrity_check không đạt sau cài.")
        if int(after["fk_count"]) != 0:
            raise RuntimeError("foreign_key_check có lỗi sau cài.")

        for key, value in before.items():
            if key in {"integrity", "fk_count"}:
                continue
            if after.get(key) != value:
                raise RuntimeError(
                    f"Số bản ghi {key} thay đổi ngoài dự kiến: "
                    f"{value} -> {after.get(key)}"
                )

        smoke_lines = smoke_database_read()

    except Exception as exc:
        print()
        print("CÓ LỖI - ĐANG ROLLBACK SOURCE + DATABASE...")
        print(type(exc).__name__ + ":", exc)
        restore_file(ROUTER)
        restore_file(TEMPLATE)
        restore_db()
        clear_cache()
        print("ĐÃ KHÔI PHỤC.")
        return 9

    report_lines = [
        "=" * 132,
        "BÁO CÁO CÀI BÀI 13B-12 V2.4.3.11",
        "=" * 132,
        f"Thời gian: {datetime.now():%d/%m/%Y %H:%M:%S}",
        "",
        "NGUYÊN NHÂN:",
        "- MN-02 vẫn ghi cứng V8/V9 = 'Thiếu dữ liệu CSVC'.",
        "- Builder chưa đọc school_mn01_csvc_inputs khi lập MN-02.",
        "",
        "ĐÃ SỬA:",
        "- Đọc CSVC đúng school_year + school/commune scope.",
        "- F: số điểm trường.",
        "- G: số lớp MG 3-4 / 5 tuổi từ CSVC.",
        "- S: giữ nguồn tỷ lệ GV/lớp từ Đội ngũ.",
        "- T: tỷ lệ phòng học/lớp từ tổng phòng MG / tổng lớp MG.",
        "- U: lớp đủ TBDH chỉ phân theo tuổi khi suy ra chắc chắn.",
        "- V: bỏ hardcode thiếu CSVC; trả lý do thiếu dữ liệu chính xác.",
        "- Không bịa lớp đơn/lớp ghép nếu tổng H+I không khớp G.",
        "- Ở phạm vi trường không tự kết luận xã Đạt/Không đạt.",
        "",
        "SMOKE READ-ONLY:",
        *["- " + line for line in smoke_lines],
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
    print("=" * 132)
    print("CÀI ĐẶT THÀNH CÔNG BÀI 13B-12 V2.4.3.11")
    print("=" * 132)
    print(" - MN-02 đã nối nguồn CSVC thật: ĐẠT.")
    print(" - Bỏ hardcode 'Thiếu dữ liệu CSVC': ĐẠT.")
    print(" - Số lớp MG lấy từ CSVC: ĐẠT.")
    print(" - Tỷ lệ phòng học/lớp lấy từ CSVC: ĐẠT.")
    print(" - TBDH không phân bổ giả theo tuổi: ĐẠT.")
    print(" - Không tự kết luận cấp xã khi đang xuất phạm vi trường.")
    print(" - Không sửa dữ liệu hiện có.")
    print("Báo cáo:", REPORT)
    print("Backup:", BACKUP)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
