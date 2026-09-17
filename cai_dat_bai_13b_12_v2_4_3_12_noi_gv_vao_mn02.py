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
EXPORTS = PROJECT / "exports"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = EXPORTS / f"backup_bai_13b_12_v2_4_3_12_{STAMP}"
DB_BACKUP = BACKUP / "phocap.db"
REPORT = EXPORTS / f"bao_cao_cai_bai_13b_12_v2_4_3_12_{STAMP}.txt"

MARKER = "BAI_13B_12_V2_4_3_12_MN02_STAFF_RATIO"
HELPER = '\n# === BAI_13B_12_V2_4_3_12_MN02_STAFF_RATIO_START ===\ndef _b24312_complete_mn02_staff_ratios(\n    staff_data: dict[str, Any],\n    csvc: dict[str, Any],\n    current_ratios: dict[str, float | None],\n) -> dict[str, float | None]:\n    result = dict(current_ratios or {})\n    result.setdefault("age_34", None)\n    result.setdefault("age_5", None)\n\n    if (\n        result.get("age_34") is not None\n        and result.get("age_5") is not None\n    ):\n        return result\n\n    rows = list(staff_data.get("rows") or [])\n    records = [\n        record\n        for row in rows\n        for record in list(row.get("records") or [])\n    ]\n\n    preschool_teachers = [\n        item\n        for item in records\n        if getattr(item, "position_group", None) == "GIAO_VIEN"\n        and getattr(item, "teaching_level", None) == "MAU_GIAO"\n    ]\n\n    known_age_codes = {"TUOI_3_4", "TUOI_5"}\n    known_age_teachers = [\n        item\n        for item in preschool_teachers\n        if getattr(item, "teaching_age_group", None)\n        in known_age_codes\n    ]\n\n    # Nếu đã có phân nhóm tuổi thật thì không dùng fallback gộp.\n    if known_age_teachers:\n        return result\n\n    total_teachers = len(preschool_teachers)\n    total_classes = _b24311_int(csvc.get("classes_total"))\n\n    if total_teachers <= 0 or total_classes <= 0:\n        return result\n\n    pooled_ratio = round(\n        float(total_teachers) / float(total_classes),\n        2,\n    )\n\n    if (\n        result.get("age_34") is None\n        and _b24311_int(csvc.get("classes_34")) > 0\n    ):\n        result["age_34"] = pooled_ratio\n\n    if (\n        result.get("age_5") is None\n        and _b24311_int(csvc.get("classes_5")) > 0\n    ):\n        result["age_5"] = pooled_ratio\n\n    return result\n# === BAI_13B_12_V2_4_3_12_MN02_STAFF_RATIO_END ===\n'


def read_text(path: Path) -> str:
    if not path.exists():
        raise RuntimeError(f"Không tìm thấy tệp bắt buộc: {path}")
    return path.read_text(encoding="utf-8-sig", errors="strict")


def write_text(path: Path, value: str) -> None:
    path.write_text(value, encoding="utf-8")


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
            "staff_members",
            "staff_year_records",
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


def backup_file(path: Path) -> None:
    dst = BACKUP / path.relative_to(PROJECT)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, dst)


def restore_file(path: Path) -> None:
    src = BACKUP / path.relative_to(PROJECT)
    if src.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
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


def function_span(source: str, name: str) -> tuple[int, int]:
    tree = ast.parse(source)
    matches = [
        node
        for node in tree.body
        if isinstance(
            node,
            (ast.FunctionDef, ast.AsyncFunctionDef),
        )
        and node.name == name
    ]
    if len(matches) != 1:
        raise RuntimeError(
            f"Không xác định duy nhất function {name}: {len(matches)}"
        )

    node = matches[0]
    if node.end_lineno is None:
        raise RuntimeError(f"AST thiếu end_lineno cho {name}")

    lines = source.splitlines(keepends=True)
    start = sum(len(x) for x in lines[: node.lineno - 1])
    end = sum(len(x) for x in lines[: node.end_lineno])
    return start, end


def insert_before_function(
    source: str,
    function_name: str,
    block: str,
) -> str:
    start, _end = function_span(source, function_name)
    return (
        source[:start]
        + block.strip()
        + "\n\n\n"
        + source[start:]
    )


def patch_router(source: str) -> str:
    if MARKER in source:
        return source

    required = (
        "def _staff_ratios_by_age(",
        "def _b24311_int(",
        "def _b24311_load_mn02_csvc(",
        "def _b24311_apply_mn02_csvc(",
        "def build_template_workbook(",
        "staff_ratios = _staff_ratios_by_age(staff_data)",
        "mn02_csvc = _b24311_load_mn02_csvc(db, context)",
        "_b24311_apply_mn02_csvc(",
    )
    for token in required:
        if token not in source:
            raise RuntimeError(
                "pcgdmn_template_report.py khác nền V2.4.3.11. "
                "Thiếu: " + token
            )

    source = insert_before_function(
        source,
        "build_template_workbook",
        HELPER,
    )

    start, end = function_span(
        source,
        "build_template_workbook",
    )
    func = source[start:end]

    old = (
        "    mn02_csvc = _b24311_load_mn02_csvc(db, context)\n"
        "    _b24311_apply_mn02_csvc(\n"
    )
    new = (
        "    mn02_csvc = _b24311_load_mn02_csvc(db, context)\n"
        "    staff_ratios = _b24312_complete_mn02_staff_ratios(\n"
        "        staff_data,\n"
        "        mn02_csvc,\n"
        "        staff_ratios,\n"
        "    )\n"
        "    _b24311_apply_mn02_csvc(\n"
    )

    if func.count(old) != 1:
        raise RuntimeError(
            "Không xác định duy nhất điểm nối MN-02 sau V2.4.3.11: "
            f"{func.count(old)}"
        )

    func = func.replace(old, new, 1)
    patched = source[:start] + func + source[end:]

    ast.parse(patched)
    compile(patched, str(ROUTER), "exec")
    return patched


def verify_router(source: str) -> None:
    required = (
        MARKER,
        "def _b24312_complete_mn02_staff_ratios(",
        'known_age_codes = {"TUOI_3_4", "TUOI_5"}',
        'getattr(item, "teaching_level", None) == "MAU_GIAO"',
        'getattr(item, "position_group", None) == "GIAO_VIEN"',
        "pooled_ratio = round(",
        "staff_ratios = _b24312_complete_mn02_staff_ratios(",
        "_b24311_apply_mn02_csvc(",
    )
    for token in required:
        if token not in source:
            raise RuntimeError("Verifier source thiếu: " + token)

    start, end = function_span(
        source,
        "build_template_workbook",
    )
    func = source[start:end]

    pos_load = func.find(
        "mn02_csvc = _b24311_load_mn02_csvc(db, context)"
    )
    pos_complete = func.find(
        "staff_ratios = _b24312_complete_mn02_staff_ratios("
    )
    pos_apply = func.find(
        "_b24311_apply_mn02_csvc("
    )

    if not (0 <= pos_load < pos_complete < pos_apply):
        raise RuntimeError(
            "Thứ tự pipeline MN-02 không đúng."
        )

    ast.parse(source)
    compile(source, str(ROUTER), "exec")
    py_compile.compile(str(ROUTER), doraise=True)


def smoke_current_data() -> list[str]:
    con = sqlite3.connect(str(DB))
    con.row_factory = sqlite3.Row
    try:
        schools = con.execute(
            """
            SELECT id, name
            FROM schools
            WHERE lower(name) LIKE '%mầm non%nghi hoa%'
               OR lower(name) LIKE '%mầm non%nghi hòa%'
            ORDER BY id
            """
        ).fetchall()

        if not schools:
            return [
                "Không tự tìm thấy Trường Mầm non Nghi Hoa/Hòa."
            ]

        lines: list[str] = []
        for school in schools[:3]:
            sid = int(school["id"])

            year_row = con.execute(
                """
                SELECT school_year_id
                FROM school_mn01_csvc_inputs
                WHERE school_id=?
                ORDER BY school_year_id DESC, id DESC
                LIMIT 1
                """,
                (sid,),
            ).fetchone()

            if year_row is None:
                continue

            year_id = int(year_row["school_year_id"])

            teacher_rows = con.execute(
                """
                SELECT
                    teaching_age_group,
                    COUNT(*) AS n
                FROM staff_year_records
                WHERE school_id=?
                  AND school_year_id=?
                  AND COALESCE(is_active, 1)=1
                  AND position_group='GIAO_VIEN'
                  AND teaching_level='MAU_GIAO'
                GROUP BY teaching_age_group
                ORDER BY teaching_age_group
                """,
                (sid, year_id),
            ).fetchall()

            csvc = con.execute(
                """
                SELECT
                    preschool_class_3_4_count,
                    preschool_class_5_count
                FROM school_mn01_csvc_inputs
                WHERE school_id=?
                  AND school_year_id=?
                ORDER BY id DESC
                LIMIT 1
                """,
                (sid, year_id),
            ).fetchone()

            total_teachers = sum(
                int(row["n"] or 0)
                for row in teacher_rows
            )
            c34 = int(
                (csvc["preschool_class_3_4_count"] if csvc else 0)
                or 0
            )
            c5 = int(
                (csvc["preschool_class_5_count"] if csvc else 0)
                or 0
            )
            total_classes = c34 + c5

            pooled = (
                round(total_teachers / total_classes, 2)
                if total_classes > 0
                else None
            )

            lines.append(
                f"{school['name']} | school_id={sid} | "
                f"year_id={year_id} | GV MG={total_teachers} | "
                f"lớp 3-4={c34} | lớp 5={c5} | "
                f"tỷ lệ gộp={pooled}"
            )
            lines.append(
                "  teaching_age_group: "
                + repr(
                    {
                        str(row["teaching_age_group"]): int(row["n"])
                        for row in teacher_rows
                    }
                )
            )

        return lines or [
            "Có trường phù hợp nhưng chưa có CSVC để smoke-test."
        ]
    finally:
        con.close()


def clear_cache() -> None:
    for cache in APP.rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(cache, ignore_errors=True)


def main() -> int:
    print("=" * 136)
    print(
        "BÀI 13B-12 V2.4.3.12 - "
        "NỐI MN-01-GV VÀO MN-02 / HOÀN THIỆN TỶ LỆ GV-LỚP"
    )
    print("=" * 136)

    for path in (DB, ROUTER):
        if not path.exists():
            print("DỪNG AN TOÀN: thiếu", path)
            return 2

    before = db_state()
    print("integrity_check:", before["integrity"])
    print(
        "foreign_key_check:",
        before["fk_count"],
        "lỗi",
    )

    if (
        str(before["integrity"]).lower() != "ok"
        or int(before["fk_count"]) != 0
    ):
        print("DỪNG: database chưa đạt kiểm tra an toàn.")
        return 3

    print()
    print("Dữ liệu test hiện tại:")
    for line in smoke_current_data():
        print(" -", line)

    source = read_text(ROUTER)

    try:
        if MARKER in source:
            print()
            print("V2.4.3.12 đã có marker. Kiểm tra lại...")
            verify_router(source)
            print("V2.4.3.12 đang hoạt động. Không cài lặp.")
            return 0

        patched = patch_router(source)
        verify_router(patched)

    except Exception as exc:
        print()
        print("DỪNG AN TOÀN TRƯỚC KHI GHI SOURCE:")
        print(type(exc).__name__ + ":", exc)
        print("Không thay đổi source/database.")
        return 4

    EXPORTS.mkdir(parents=True, exist_ok=True)
    BACKUP.mkdir(parents=True, exist_ok=False)
    backup_file(ROUTER)
    backup_db()
    print()
    print("Backup:", BACKUP)

    try:
        write_text(ROUTER, patched)
        verify_router(read_text(ROUTER))
        clear_cache()

        after = db_state()
        if str(after["integrity"]).lower() != "ok":
            raise RuntimeError(
                "integrity_check không đạt sau cài."
            )
        if int(after["fk_count"]) != 0:
            raise RuntimeError(
                "foreign_key_check có lỗi sau cài."
            )

        for key, value in before.items():
            if key in {"integrity", "fk_count"}:
                continue
            if after.get(key) != value:
                raise RuntimeError(
                    f"Số bản ghi {key} thay đổi ngoài dự kiến: "
                    f"{value} -> {after.get(key)}"
                )

        smoke_lines = smoke_current_data()

    except Exception as exc:
        print()
        print("CÓ LỖI - ĐANG ROLLBACK SOURCE + DATABASE...")
        print(type(exc).__name__ + ":", exc)
        restore_file(ROUTER)
        restore_db()
        clear_cache()
        print("ĐÃ KHÔI PHỤC.")
        return 9

    report_lines = [
        "=" * 136,
        "BÁO CÁO CÀI BÀI 13B-12 V2.4.3.12",
        "=" * 136,
        f"Thời gian: {datetime.now():%d/%m/%Y %H:%M:%S}",
        "",
        "NGUYÊN TẮC:",
        "- Có phân nhóm tuổi thật -> giữ tỷ lệ chính xác.",
        "- Không có bất kỳ phân nhóm tuổi nào -> dùng tỷ lệ gộp "
        "GV Mẫu giáo / tổng lớp Mẫu giáo cho MN-02.",
        "- Phân nhóm một phần -> không fallback.",
        "- Không ghi ngược teaching_age_group.",
        "- Không sửa dữ liệu hiện có.",
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
    print("=" * 136)
    print("CÀI ĐẶT THÀNH CÔNG BÀI 13B-12 V2.4.3.12")
    print("=" * 136)
    print(" - Giữ tỷ lệ theo nhóm tuổi khi có dữ liệu thật: ĐẠT.")
    print(" - Fallback tỷ lệ gộp khi toàn bộ GV chưa phân nhóm: ĐẠT.")
    print(" - Không ghi ngược dữ liệu giáo viên: ĐẠT.")
    print(" - Không sửa dữ liệu hiện có.")
    print("Báo cáo:", REPORT)
    print("Backup:", BACKUP)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
