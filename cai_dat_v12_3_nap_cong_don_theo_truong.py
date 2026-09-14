# -*- coding: utf-8 -*-
r"""
V12.3 - NẠP CỘNG DỒN NGUỒN HỌC SINH THEO TRƯỜNG

- File mới chỉ thay enrollment của các trường xuất hiện trong file.
- Dữ liệu trường/cấp đã nạp trước được giữ nguyên.
- Card trạng thái tính tổng cộng dồn của cả xã.
- Không sửa database trong lúc cài patch.
"""

from __future__ import annotations

import ast
import py_compile
import shutil
from datetime import datetime
from pathlib import Path


PROJECT = Path(r"C:\PhoCap")
ROUTER = PROJECT / "app" / "routers" / "student_reconciliation_source.py"
TEMPLATE = PROJECT / "app" / "templates" / "surveys" / "student_reconciliation_source.html"
EXPORTS = PROJECT / "exports"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = EXPORTS / f"backup_v12_3_nap_cong_don_{STAMP}"
REPORT = EXPORTS / f"bao_cao_v12_3_nap_cong_don_{STAMP}.txt"

MARK_START = "# === V12_3_CUMULATIVE_IMPORT_START ==="
MARK_END = "# === V12_3_CUMULATIVE_IMPORT_END ==="

OLD_DELETE_BLOCK = """        owned_ids = _state_enrollment_ids(db, state_id)
        if owned_ids:
            for start in range(0, len(owned_ids), 700):
                chunk = sorted(owned_ids)[start:start + 700]
                db.execute(
                    text("DELETE FROM student_reconciliation_state_enrollments WHERE enrollment_id IN (" + ",".join(str(int(x)) for x in chunk) + ")")
                )
                db.execute(
                    text("DELETE FROM student_enrollments WHERE id IN (" + ",".join(str(int(x)) for x in chunk) + ")")
                )
            db.flush()

        school_ids = sorted({int(x["school_id"]) for x in records})
"""

NEW_DELETE_BLOCK = """        # === V12_3_CUMULATIVE_IMPORT_START ===
        # Chỉ thay dữ liệu của các trường có trong file đang nạp.
        school_ids = sorted({int(x["school_id"]) for x in records})
        owned_ids = _state_enrollment_ids(db, state_id)

        replace_ids: set[int] = set()
        if owned_ids and school_ids:
            replace_rows = db.execute(
                text(
                    "SELECT se.enrollment_id "
                    "FROM student_reconciliation_state_enrollments se "
                    "JOIN student_enrollments e ON e.id=se.enrollment_id "
                    "WHERE se.state_id=:state_id "
                    "AND e.school_year_id=:source_year_id "
                    "AND e.school_id IN ("
                    + ",".join(str(int(x)) for x in school_ids)
                    + ")"
                ),
                {
                    "state_id": state_id,
                    "source_year_id": source_year_id,
                },
            ).all()
            replace_ids = {int(r[0]) for r in replace_rows}

        if replace_ids:
            for start in range(0, len(replace_ids), 700):
                chunk = sorted(replace_ids)[start:start + 700]
                id_sql = ",".join(str(int(x)) for x in chunk)

                db.execute(
                    text(
                        "DELETE FROM student_reconciliation_state_enrollments "
                        "WHERE state_id=:state_id "
                        "AND enrollment_id IN (" + id_sql + ")"
                    ),
                    {"state_id": state_id},
                )
                db.execute(
                    text(
                        "DELETE FROM student_enrollments "
                        "WHERE id IN (" + id_sql + ")"
                    )
                )

            db.flush()
        # === V12_3_CUMULATIVE_IMPORT_END ===
"""

OLD_STATE_UPDATE = """        db.execute(
            text(
                "UPDATE student_reconciliation_source_states SET "
                "source_school_year_id=:source,status='LOADED',file_name=:file_name,total_rows=:total_rows,"
                "valid_rows=:valid_rows,student_count=:student_count,enrollment_count=:enrollment_count,"
                "class_count=:class_count,import_count=COALESCE(import_count,0)+1,last_imported_at=:now,"
                "imported_by_user_id=:actor,locked_at=NULL,locked_by_user_id=NULL,updated_at=:now "
                "WHERE id=:state_id"
            ),
            {
                "source": source_year_id,
                "file_name": payload["file_name"],
                "total_rows": len(records),
                "valid_rows": len(records),
                "student_count": int(payload.get("student_count") or 0),
                "enrollment_count": inserted_enrollments,
                "class_count": int(payload.get("class_count") or 0),
                "now": now,
                "actor": actor.get("id"),
                "state_id": state_id,
            },
        )
"""

NEW_STATE_UPDATE = """        # V12.3: card trạng thái phản ánh toàn bộ nguồn cộng dồn của xã.
        aggregate = db.execute(
            text(
                "SELECT "
                "COUNT(*) AS enrollment_count, "
                "COUNT(DISTINCT e.student_id) AS student_count, "
                "COUNT(DISTINCT e.class_id) AS class_count "
                "FROM student_reconciliation_state_enrollments se "
                "JOIN student_enrollments e ON e.id=se.enrollment_id "
                "WHERE se.state_id=:state_id"
            ),
            {"state_id": state_id},
        ).mappings().one()

        aggregate_enrollment_count = int(
            aggregate["enrollment_count"] or 0
        )
        aggregate_student_count = int(
            aggregate["student_count"] or 0
        )
        aggregate_class_count = int(
            aggregate["class_count"] or 0
        )

        db.execute(
            text(
                "UPDATE student_reconciliation_source_states SET "
                "source_school_year_id=:source,status='LOADED',file_name=:file_name,total_rows=:total_rows,"
                "valid_rows=:valid_rows,student_count=:student_count,enrollment_count=:enrollment_count,"
                "class_count=:class_count,import_count=COALESCE(import_count,0)+1,last_imported_at=:now,"
                "imported_by_user_id=:actor,locked_at=NULL,locked_by_user_id=NULL,updated_at=:now "
                "WHERE id=:state_id"
            ),
            {
                "source": source_year_id,
                "file_name": payload["file_name"],
                "total_rows": aggregate_enrollment_count,
                "valid_rows": aggregate_enrollment_count,
                "student_count": aggregate_student_count,
                "enrollment_count": aggregate_enrollment_count,
                "class_count": aggregate_class_count,
                "now": now,
                "actor": actor.get("id"),
                "state_id": state_id,
            },
        )
"""

HELP_TEXT = (
    "Có thể nạp file MN, TH, THCS, THPT riêng hoặc file tổng hợp, "
    "miễn có các cột Trường – Lớp – Mã định danh Bộ GD&ĐT – Họ tên – Ngày sinh."
)

NEW_HELP_TEXT = (
    HELP_TEXT
    + " Các file được cộng dồn theo trường; nạp lại một file chỉ thay dữ liệu "
      "của các trường có trong file đó, không xóa dữ liệu các cấp/trường đã nạp trước."
)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def backup_file(path: Path) -> None:
    rel = path.relative_to(PROJECT)
    dst = BACKUP / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, dst)


def restore_file(path: Path) -> None:
    src = BACKUP / path.relative_to(PROJECT)
    if src.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, path)


def patch_router(source: str) -> tuple[str, str]:
    if MARK_START in source and MARK_END in source:
        return source, "ALREADY_INSTALLED"

    required = [
        "def import_source(",
        "student_reconciliation_state_enrollments",
        "def _state_enrollment_ids(",
        "import_count=COALESCE(import_count,0)+1",
    ]
    missing = [x for x in required if x not in source]
    if missing:
        raise RuntimeError(
            "Router không đúng nền V12; thiếu: " + repr(missing)
        )

    if source.count(OLD_DELETE_BLOCK) != 1:
        raise RuntimeError(
            "Không tìm thấy đúng block xóa enrollment cũ của V12."
        )

    if source.count(OLD_STATE_UPDATE) != 1:
        raise RuntimeError(
            "Không tìm thấy đúng block cập nhật state của V12."
        )

    source = source.replace(OLD_DELETE_BLOCK, NEW_DELETE_BLOCK, 1)
    source = source.replace(OLD_STATE_UPDATE, NEW_STATE_UPDATE, 1)

    return source, "PATCHED"


def patch_template(source: str) -> tuple[str, str]:
    if NEW_HELP_TEXT in source:
        return source, "ALREADY_INSTALLED"

    if HELP_TEXT not in source:
        return source, "HELP_TEXT_NOT_FOUND_SKIP"

    return source.replace(HELP_TEXT, NEW_HELP_TEXT, 1), "PATCHED"


def verify_router(source: str) -> None:
    ast.parse(source)

    required = [
        MARK_START,
        MARK_END,
        "replace_ids: set[int] = set()",
        "COUNT(DISTINCT e.student_id) AS student_count",
        "COUNT(DISTINCT e.class_id) AS class_count",
        '"total_rows": aggregate_enrollment_count',
        '"enrollment_count": aggregate_enrollment_count',
    ]
    missing = [x for x in required if x not in source]
    if missing:
        raise RuntimeError(
            "Hậu kiểm router thiếu: " + repr(missing)
        )

    if source.count(MARK_START) != 1:
        raise RuntimeError("Marker V12.3 bị lặp.")


def verify_template(source: str) -> None:
    from jinja2 import Environment
    Environment().parse(source)


def main() -> int:
    print("=" * 116)
    print("V12.3 - NẠP CỘNG DỒN NGUỒN HỌC SINH THEO TRƯỜNG")
    print("=" * 116)

    for path in (ROUTER, TEMPLATE):
        if not path.exists():
            print(f"Không tìm thấy: {path}")
            return 2

    EXPORTS.mkdir(parents=True, exist_ok=True)
    BACKUP.mkdir(parents=True, exist_ok=False)

    backup_file(ROUTER)
    backup_file(TEMPLATE)

    try:
        router_before = read_text(ROUTER)
        template_before = read_text(TEMPLATE)

        router_after, router_mode = patch_router(router_before)
        template_after, template_mode = patch_template(template_before)

        verify_router(router_after)
        verify_template(template_after)

        ROUTER.write_text(router_after, encoding="utf-8")
        TEMPLATE.write_text(template_after, encoding="utf-8")

        py_compile.compile(str(ROUTER), doraise=True)

        verify_router(read_text(ROUTER))
        verify_template(read_text(TEMPLATE))

        REPORT.write_text(
            f"""V12.3 - NẠP CỘNG DỒN NGUỒN HỌC SINH THEO TRƯỜNG
======================================================

ROUTER_MODE: {router_mode}
TEMPLATE_MODE: {template_mode}

PHỤC HỒI NGHI LỘC:
1. Mở khóa nguồn.
2. Nạp lại MN_Nghi_Loc_2025_2026.xlsx.
3. Nạp lại TH_Nghi_Loc_2025_2026.xlsx.
4. Không cần nạp lại THCS.
5. Kỳ vọng tổng:
   - Học sinh: 10236
   - Enrollment: 10255
   - Lớp: 292
   - Số lần nạp: 5
6. Khóa nguồn lại.

Database không thay đổi trong lúc cài V12.3.
Backup: {BACKUP}
""",
            encoding="utf-8",
        )

        print("CÀI V12.3 THÀNH CÔNG")
        print(f"Router: {router_mode}")
        print(f"Template: {template_mode}")
        print("Database: KHÔNG THAY ĐỔI")
        print(f"Backup: {BACKUP}")
        print(f"Report: {REPORT}")
        print()
        print("PHỤC HỒI NGHI LỘC:")
        print(" 1. Khởi động lại phần mềm.")
        print(" 2. Bấm 'Mở khóa để nạp lại'.")
        print(" 3. Nạp lại file MN.")
        print(" 4. Nạp lại file TH.")
        print(" 5. Không cần nạp lại THCS.")
        print(" 6. Kỳ vọng: HS=10236 | Enrollment=10255 | Lớp=292.")
        print(" 7. Đúng số thì Khóa nguồn lại.")
        return 0

    except Exception as exc:
        print()
        print("CÓ LỖI V12.3:", repr(exc))
        print("Đang khôi phục source cũ...")
        restore_file(ROUTER)
        restore_file(TEMPLATE)
        print("Đã khôi phục. Database không thay đổi.")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
