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
BACKUP = EXPORTS / f"backup_bai_13b_12_v2_4_3_13_{STAMP}"
DB_BACKUP = BACKUP / "phocap.db"
REPORT = EXPORTS / f"bao_cao_cai_bai_13b_12_v2_4_3_13_{STAMP}.txt"

OLD_MARKER = "BAI_13B_12_V2_4_3_12_MN02_STAFF_RATIO"
NEW_MARKER = "BAI_13B_12_V2_4_3_13_MN02_STAFF_RATIO_CSVCDENOM"

NEW_FUNCTION = '\ndef _b24312_complete_mn02_staff_ratios(\n    staff_data: dict[str, Any],\n    csvc: dict[str, Any],\n    current_ratios: dict[str, float | None],\n) -> dict[str, float | None]:\n    """\n    V2.4.3.13:\n    - Tử số GV lấy từ staff_year_records theo teaching_age_group.\n    - Mẫu số lớp lấy TRỰC TIẾP từ MN-01-CSVC năm hiện tại.\n    - Không còn phụ thuộc school_staff_year_summaries/classes_34/classes_5\n      khi tính cột 19 của MN-02.\n\n    Nếu đã có GV phân nhóm tuổi:\n      TUOI_3_4 / classes_34\n      TUOI_5   / classes_5\n\n    Nếu hoàn toàn chưa phân nhóm tuổi:\n      tổng GV Mẫu giáo / tổng lớp Mẫu giáo\n      làm fallback cho các dòng có lớp.\n\n    Nếu chỉ phân nhóm một phần:\n      không tự phân bổ phần còn thiếu.\n    """\n    result = dict(current_ratios or {})\n    result.setdefault("age_34", None)\n    result.setdefault("age_5", None)\n\n    rows = list(staff_data.get("rows") or [])\n    records = [\n        record\n        for row in rows\n        for record in list(row.get("records") or [])\n    ]\n\n    preschool_teachers = [\n        item\n        for item in records\n        if getattr(item, "position_group", None) == "GIAO_VIEN"\n        and getattr(item, "teaching_level", None) == "MAU_GIAO"\n    ]\n\n    specs = (\n        ("age_34", "TUOI_3_4", "classes_34"),\n        ("age_5", "TUOI_5", "classes_5"),\n    )\n\n    known_counts: dict[str, int] = {}\n    for key, age_code, _class_key in specs:\n        known_counts[key] = sum(\n            1\n            for item in preschool_teachers\n            if getattr(item, "teaching_age_group", None) == age_code\n        )\n\n    has_any_age_assignment = any(\n        count > 0\n        for count in known_counts.values()\n    )\n\n    if has_any_age_assignment:\n        for key, _age_code, class_key in specs:\n            teachers = int(known_counts.get(key, 0) or 0)\n            classes = _b24311_int(csvc.get(class_key))\n\n            if teachers > 0 and classes > 0:\n                result[key] = round(\n                    float(teachers) / float(classes),\n                    2,\n                )\n            elif teachers <= 0:\n                # Có phân nhóm một phần: không suy đoán nhóm còn thiếu.\n                result[key] = None\n\n        return result\n\n    total_teachers = len(preschool_teachers)\n    total_classes = _b24311_int(csvc.get("classes_total"))\n\n    if total_teachers <= 0 or total_classes <= 0:\n        return result\n\n    pooled_ratio = round(\n        float(total_teachers) / float(total_classes),\n        2,\n    )\n\n    for key, _age_code, class_key in specs:\n        if _b24311_int(csvc.get(class_key)) > 0:\n            result[key] = pooled_ratio\n\n    return result\n'


def read_text(path: Path) -> str:
    if not path.exists():
        raise RuntimeError(f"Không tìm thấy tệp bắt buộc: {path}")
    return path.read_text(encoding="utf-8-sig", errors="strict")


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def function_node(source: str, name: str):
    tree = ast.parse(source)
    nodes = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == name
    ]
    if len(nodes) != 1:
        raise RuntimeError(
            f"Phải tìm đúng 1 hàm {name}; hiện có {len(nodes)}."
        )
    return nodes[0]


def function_span(source: str, name: str) -> tuple[int, int]:
    node = function_node(source, name)
    if node.end_lineno is None:
        raise RuntimeError(f"AST thiếu end_lineno cho {name}")
    lines = source.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    return offsets[node.lineno - 1], offsets[node.end_lineno]


def replace_function(
    source: str,
    name: str,
    replacement: str,
) -> str:
    start, end = function_span(source, name)
    result = (
        source[:start]
        + replacement.strip()
        + "\n\n"
        + source[end:].lstrip("\n")
    )
    ast.parse(result)
    return result


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


def patch_source(source: str) -> str:
    if NEW_MARKER in source:
        return source

    required = (
        OLD_MARKER,
        "def _b24312_complete_mn02_staff_ratios(",
        "def _b24311_int(",
        "mn02_csvc = _b24311_load_mn02_csvc(db, context)",
        "staff_ratios = _b24312_complete_mn02_staff_ratios(",
        "_b24311_apply_mn02_csvc(",
    )
    for token in required:
        if token not in source:
            raise RuntimeError(
                "Source không đúng nền V2.4.3.12. Thiếu: " + token
            )

    replacement = (
        "# === BAI_13B_12_V2_4_3_13_MN02_STAFF_RATIO_CSVCDENOM_START ===\n"
        + NEW_FUNCTION.strip()
        + "\n"
        "# === BAI_13B_12_V2_4_3_13_MN02_STAFF_RATIO_CSVCDENOM_END ==="
    )

    source = replace_function(
        source,
        "_b24312_complete_mn02_staff_ratios",
        replacement,
    )

    ast.parse(source)
    compile(source, str(ROUTER), "exec")
    return source


def verify_source(source: str) -> None:
    required = (
        NEW_MARKER,
        "def _b24312_complete_mn02_staff_ratios(",
        '("age_34", "TUOI_3_4", "classes_34")',
        '("age_5", "TUOI_5", "classes_5")',
        "classes = _b24311_int(csvc.get(class_key))",
        "result[key] = round(",
        "float(teachers) / float(classes)",
        "has_any_age_assignment = any(",
        "staff_ratios = _b24312_complete_mn02_staff_ratios(",
    )
    for token in required:
        if token not in source:
            raise RuntimeError("Verifier source thiếu: " + token)

    start, end = function_span(
        source,
        "_b24312_complete_mn02_staff_ratios",
    )
    fn = source[start:end]

    # Không cho phép quay lại lỗi cũ:
    bad = 'classes = sum(int(row[class_key] or 0) for row in rows)'
    if bad in fn:
        raise RuntimeError(
            "Vẫn còn dùng mẫu số lớp từ staff summary."
        )

    ast.parse(source)
    compile(source, str(ROUTER), "exec")
    py_compile.compile(str(ROUTER), doraise=True)


def live_mn_ngihoa_check() -> list[str]:
    con = sqlite3.connect(str(DB))
    con.row_factory = sqlite3.Row
    try:
        school = con.execute(
            """
            SELECT id, name
            FROM schools
            WHERE code='40429325'
               OR lower(name) LIKE '%mầm non%nghi hoa%'
               OR lower(name) LIKE '%mầm non%nghi hòa%'
            ORDER BY
                CASE WHEN code='40429325' THEN 0 ELSE 1 END,
                id
            LIMIT 1
            """
        ).fetchone()

        if school is None:
            return [
                "Không tự tìm được Trường Mầm non Nghi Hoa; "
                "bỏ qua kiểm tra số liệu cụ thể."
            ]

        sid = int(school["id"])

        year = con.execute(
            """
            SELECT id, code
            FROM school_years
            WHERE code='2026-2027'
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()

        if year is None:
            return ["Không tìm thấy năm học 2026-2027."]

        yid = int(year["id"])

        csvc = con.execute(
            """
            SELECT
                preschool_class_3_4_count AS c34,
                preschool_class_5_count AS c5
            FROM school_mn01_csvc_inputs
            WHERE school_id=? AND school_year_id=?
            ORDER BY id DESC
            LIMIT 1
            """,
            (sid, yid),
        ).fetchone()

        if csvc is None:
            return [
                f"{school['name']}: chưa có MN-01-CSVC năm 2026-2027."
            ]

        counts = {
            str(row["teaching_age_group"]): int(row["n"])
            for row in con.execute(
                """
                SELECT teaching_age_group, COUNT(*) AS n
                FROM staff_year_records
                WHERE school_id=?
                  AND school_year_id=?
                  AND COALESCE(is_active, 1)=1
                  AND position_group='GIAO_VIEN'
                  AND teaching_level='MAU_GIAO'
                GROUP BY teaching_age_group
                """,
                (sid, yid),
            ).fetchall()
        }

        c34 = int(csvc["c34"] or 0)
        c5 = int(csvc["c5"] or 0)
        g34 = int(counts.get("TUOI_3_4", 0))
        g5 = int(counts.get("TUOI_5", 0))

        r34 = round(g34 / c34, 2) if c34 > 0 and g34 > 0 else None
        r5 = round(g5 / c5, 2) if c5 > 0 and g5 > 0 else None

        return [
            f"{school['name']} | school_id={sid} | year_id={yid}",
            f"GV theo nhóm: {counts}",
            f"MN-01-CSVC: lớp 3-4={c34}; lớp 5={c5}",
            f"MN-02 phải nhận: S8={r34}; S9={r5}",
        ]
    finally:
        con.close()


def clear_cache() -> None:
    for cache in APP.rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(cache, ignore_errors=True)


def main() -> int:
    print("=" * 140)
    print(
        "BÀI 13B-12 V2.4.3.13 - "
        "SỬA MẪU SỐ TỶ LỆ GV/LỚP MN-02 TỪ MN-01-CSVC"
    )
    print("=" * 140)

    for path in (DB, ROUTER):
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

    print()
    print("Đối chiếu số liệu thật:")
    for line in live_mn_ngihoa_check():
        print(" -", line)

    source = read_text(ROUTER)

    try:
        if NEW_MARKER in source:
            verify_source(source)
            print()
            print("V2.4.3.13 đã có và đạt verifier. Không cài lặp.")
            return 0

        patched = patch_source(source)
        # kiểm trên text trước khi ghi
        ast.parse(patched)
        compile(patched, str(ROUTER), "exec")

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
        verify_source(read_text(ROUTER))
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

        lines = live_mn_ngihoa_check()

    except Exception as exc:
        print()
        print("CÓ LỖI - ĐANG ROLLBACK SOURCE + DATABASE...")
        print(type(exc).__name__ + ":", exc)
        restore_file(ROUTER)
        restore_db()
        clear_cache()
        print("ĐÃ KHÔI PHỤC.")
        return 9

    REPORT.write_text(
        "\n".join(
            [
                "=" * 140,
                "BÁO CÁO CÀI BÀI 13B-12 V2.4.3.13",
                "=" * 140,
                f"Thời gian: {datetime.now():%d/%m/%Y %H:%M:%S}",
                "",
                "LỖI ĐÃ XÁC ĐỊNH:",
                "- GV đã có teaching_age_group thật.",
                "- Nhưng hàm cũ lấy mẫu số lớp từ staff summary.",
                "- Trong khi số lớp năm hiện tại đã nằm ở MN-01-CSVC.",
                "",
                "SỬA:",
                "- TUOI_3_4 / classes_34 từ MN-01-CSVC.",
                "- TUOI_5 / classes_5 từ MN-01-CSVC.",
                "- Không sửa dữ liệu GV.",
                "- Không sửa dữ liệu CSVC.",
                "",
                "ĐỐI CHIẾU:",
                *["- " + x for x in lines],
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
    print("=" * 140)
    print("CÀI ĐẶT THÀNH CÔNG BÀI 13B-12 V2.4.3.13")
    print("=" * 140)
    print(" - Tử số GV lấy đúng theo nhóm tuổi: ĐẠT.")
    print(" - Mẫu số lớp lấy từ MN-01-CSVC năm hiện tại: ĐẠT.")
    print(" - Không sửa dữ liệu hiện có.")
    print("Báo cáo:", REPORT)
    print("Backup:", BACKUP)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
