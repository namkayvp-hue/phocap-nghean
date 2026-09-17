from __future__ import annotations

import json
import sqlite3
import sys
from collections import defaultdict, deque
from datetime import datetime
from pathlib import Path

PROJECT = Path(r"C:\PhoCap").resolve()
DB_PATH = PROJECT / "data" / "phocap.db"
EXPORT_DIR = PROJECT / "exports"

CONFIRM_TEXT = "XOA TOAN BO DU LIEU THU NGHIEM"

# =====================================================================
# SCHEMA ĐÃ ĐƯỢC KIỂM TRA TRỰC TIẾP BẰNG SCRIPT CHỈ ĐỌC V1 NGÀY 19/08/2026.
# Nếu database có thêm/bớt bảng, công cụ DỪNG thay vì tự suy đoán.
# =====================================================================

EXPECTED_TABLES = {
    "account_provision_batch_items",
    "account_provision_batches",
    "classes",
    "communes",
    "finance_report_values",
    "historical_data_logs",
    "historical_datasets",
    "historical_households",
    "historical_people",
    "households",
    "import_batches",
    "roles",
    "school_mn01_csvc_inputs",
    "school_mn01_gv_inputs",
    "school_network_year_data",
    "school_staff_year_summaries",
    "school_structured_report_inputs",
    "school_years",
    "schools",
    "staff_members",
    "staff_year_records",
    "student_change_logs",
    "student_enrollments",
    "student_survey_comparison_signoffs",
    "student_survey_resolution_logs",
    "students",
    "survey_assignment_logs",
    "survey_batch_lock_logs",
    "survey_batches",
    "survey_commune_execution_states",
    "survey_execution_workflow_logs",
    "survey_file_exchange_logs",
    "survey_form_investigators",
    "survey_forms",
    "survey_household_import_errors",
    "survey_household_import_jobs",
    "survey_investigation_participants",
    "survey_investigation_team_forms",
    "survey_investigation_team_members",
    "survey_investigation_teams",
    "survey_participant_submissions",
    "survey_people",
    "survey_person_year_records",
    "survey_school_assignments",
    "survey_team_generation_logs",
    "survey_team_registration_logs",
    "thpt_grade_references",
    "thpt_school_references",
    "users",
}

# =====================================================================
# GIỮ TOÀN BỘ.
#
# Ngoài xã/trường/lớp/giáo viên theo yêu cầu, phải giữ roles/users/
# school_years để phần mềm đăng nhập và quan hệ lớp còn hợp lệ.
#
# Giữ thêm dữ liệu mạng lưới, biểu giáo viên và tham chiếu THPT vì đây
# là dữ liệu nền thuộc trường/lớp/giáo viên, không phải hộ/HS/điều tra.
# =====================================================================

KEEP_WHOLE = {
    "communes",
    "schools",
    "classes",
    "staff_members",
    "staff_year_records",
    "school_staff_year_summaries",
    "school_mn01_gv_inputs",
    "school_network_year_data",
    "thpt_school_references",
    "thpt_grade_references",
    "roles",
    "users",
    "school_years",
}

# Bảng này chứa cả biểu GV và CSVC.
# Chỉ giữ hai biểu giáo viên, xóa các biểu khác.
PARTIAL_TABLE = "school_structured_report_inputs"
KEEP_STRUCTURED_FORM_CODES = {
    "TH_01_GV",
    "THCS_01_GV",
}


def qi(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def table_names(con: sqlite3.Connection) -> set[str]:
    return {
        str(row[0])
        for row in con.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type='table'
              AND name NOT LIKE 'sqlite_%'
            """
        ).fetchall()
    }


def columns(con: sqlite3.Connection, table: str) -> set[str]:
    return {
        str(row[1])
        for row in con.execute(
            f"PRAGMA table_info({qi(table)})"
        ).fetchall()
    }


def foreign_keys(con: sqlite3.Connection, table: str):
    result = []
    for row in con.execute(
        f"PRAGMA foreign_key_list({qi(table)})"
    ).fetchall():
        result.append({
            "parent": str(row[2]),
            "child_col": str(row[3]),
            "parent_col": str(row[4]),
        })
    return result


def scalar(con: sqlite3.Connection, sql: str, params=()) -> int:
    row = con.execute(sql, params).fetchone()
    return int(row[0] or 0) if row else 0


def table_count(con: sqlite3.Connection, table: str) -> int:
    return scalar(
        con,
        f"SELECT COUNT(*) FROM {qi(table)}",
    )


def structured_counts(con: sqlite3.Connection) -> dict[str, int]:
    if PARTIAL_TABLE not in table_names(con):
        return {}

    cols = columns(con, PARTIAL_TABLE)
    if "form_code" not in cols:
        raise RuntimeError(
            f"{PARTIAL_TABLE} thiếu cột form_code. "
            "Dừng an toàn."
        )

    rows = con.execute(
        f"""
        SELECT
            UPPER(COALESCE(form_code, '')) AS code,
            COUNT(*) AS total
        FROM {qi(PARTIAL_TABLE)}
        GROUP BY UPPER(COALESCE(form_code, ''))
        ORDER BY code
        """
    ).fetchall()

    return {
        str(row[0]): int(row[1] or 0)
        for row in rows
    }


def full_delete_tables() -> set[str]:
    return (
        EXPECTED_TABLES
        - KEEP_WHOLE
        - {PARTIAL_TABLE}
    )


def verify_schema(con: sqlite3.Connection) -> None:
    actual = table_names(con)

    missing = sorted(EXPECTED_TABLES - actual)
    extra = sorted(actual - EXPECTED_TABLES)

    if missing or extra:
        print()
        print("SCHEMA KHÔNG CÒN ĐÚNG VỚI LẦN KIỂM TRA.")
        if missing:
            print("Thiếu bảng:")
            for item in missing:
                print(" -", item)
        if extra:
            print("Có bảng mới/chưa được phân loại:")
            for item in extra:
                print(" -", item)

        raise RuntimeError(
            "Dừng an toàn. Không tự suy đoán phạm vi DELETE."
        )

    if not KEEP_WHOLE.issubset(actual):
        raise RuntimeError(
            "Thiếu một hoặc nhiều bảng cần giữ."
        )

    if "form_code" not in columns(con, PARTIAL_TABLE):
        raise RuntimeError(
            f"{PARTIAL_TABLE} không có form_code."
        )


def verify_keep_fk_safety(con: sqlite3.Connection) -> None:
    delete_targets = full_delete_tables() | {PARTIAL_TABLE}
    problems = []

    for child in sorted(KEEP_WHOLE):
        for fk in foreign_keys(con, child):
            if fk["parent"] in delete_targets:
                problems.append(
                    f"{child}.{fk['child_col']} -> "
                    f"{fk['parent']}.{fk['parent_col']}"
                )

    if problems:
        print()
        print("CẢNH BÁO FK: BẢNG CẦN GIỮ ĐANG PHỤ THUỘC BẢNG SẼ XÓA")
        for item in problems:
            print(" -", item)
        raise RuntimeError(
            "Không đủ an toàn để dọn dữ liệu."
        )


def delete_order(con: sqlite3.Connection) -> list[str]:
    """
    Xếp child trước parent cho tất cả bảng có thao tác DELETE.
    PARTIAL_TABLE cũng tham gia graph vì có DELETE một phần.
    """
    targets = full_delete_tables() | {PARTIAL_TABLE}

    edges: dict[str, set[str]] = defaultdict(set)
    indegree = {table: 0 for table in targets}

    for child in targets:
        for fk in foreign_keys(con, child):
            parent = fk["parent"]

            if parent not in targets:
                continue

            # DELETE FROM một bảng tự tham chiếu xóa toàn bộ các row mục tiêu
            # có thể xử lý trong một statement; không tạo cạnh self-cycle.
            if parent == child:
                continue

            if parent not in edges[child]:
                edges[child].add(parent)
                indegree[parent] += 1

    queue = deque(
        sorted(
            table
            for table, degree in indegree.items()
            if degree == 0
        )
    )

    result = []

    while queue:
        child = queue.popleft()
        result.append(child)

        for parent in sorted(edges.get(child, set())):
            indegree[parent] -= 1
            if indegree[parent] == 0:
                queue.append(parent)

    if len(result) != len(targets):
        unresolved = sorted(targets - set(result))
        raise RuntimeError(
            "Phát hiện vòng phụ thuộc FK giữa các bảng sẽ dọn: "
            + ", ".join(unresolved)
            + ". Dừng an toàn."
        )

    return result


def keep_snapshot(con: sqlite3.Connection) -> dict[str, int]:
    return {
        table: table_count(con, table)
        for table in sorted(KEEP_WHOLE)
    }


def live_integrity(con: sqlite3.Connection) -> None:
    integrity = str(
        con.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]
    )

    if integrity.lower() != "ok":
        raise RuntimeError(
            "Database hiện tại không đạt integrity_check: "
            + integrity
        )

    fk_errors = con.execute(
        "PRAGMA foreign_key_check"
    ).fetchall()

    if fk_errors:
        print()
        print(
            "Database hiện tại đang có "
            f"{len(fk_errors)} lỗi foreign key."
        )
        for row in fk_errors[:20]:
            print(" -", tuple(row))

        raise RuntimeError(
            "Dừng trước khi dọn vì database hiện tại "
            "đã có lỗi foreign key."
        )


def print_preview(con: sqlite3.Connection) -> dict:
    verify_schema(con)
    verify_keep_fk_safety(con)

    keep_before = keep_snapshot(con)
    structured = structured_counts(con)
    order = delete_order(con)

    print()
    print("=" * 112)
    print("1. DỮ LIỆU SẼ GIỮ NGUYÊN")
    print("=" * 112)

    labels = {
        "communes": "Xã/phường",
        "schools": "Trường",
        "classes": "Lớp",
        "staff_members": "Hồ sơ đội ngũ/giáo viên",
        "staff_year_records": "Đội ngũ theo năm học",
        "school_staff_year_summaries": "Tổng hợp đội ngũ",
        "school_mn01_gv_inputs": "Dữ liệu bổ sung MN-01-GV",
        "school_network_year_data": "Mạng lưới trường/lớp theo năm",
        "thpt_school_references": "Danh mục trường THPT tham chiếu",
        "thpt_grade_references": "Khối/lớp THPT tham chiếu",
        "roles": "Vai trò hệ thống",
        "users": "Tài khoản đăng nhập",
        "school_years": "Danh mục năm học",
    }

    for table in sorted(KEEP_WHOLE):
        print(
            f"GIỮ | {table:<42} | "
            f"{keep_before[table]:>8} | "
            f"{labels.get(table, '')}"
        )

    print()
    print(
        f"GIỮ MỘT PHẦN | {PARTIAL_TABLE}"
    )

    gv_structured_total = 0
    delete_structured_total = 0

    if structured:
        for code, total in structured.items():
            keep = code in KEEP_STRUCTURED_FORM_CODES
            if keep:
                gv_structured_total += total
            else:
                delete_structured_total += total

            print(
                f" {'GIỮ' if keep else 'XÓA':<4} "
                f"| form_code={code or '(trống)':<20} "
                f"| {total:>6} bản ghi"
            )
    else:
        print(" - Bảng hiện không có bản ghi.")

    print()
    print("=" * 112)
    print("2. DỮ LIỆU THỬ NGHIỆM SẼ XÓA SẠCH")
    print("=" * 112)

    full_counts = {}
    total_delete = delete_structured_total

    for table in sorted(full_delete_tables()):
        c = table_count(con, table)
        full_counts[table] = c
        total_delete += c
        print(
            f"XÓA | {table:<45} | {c:>8} bản ghi"
        )

    print()
    print("=" * 112)
    print("3. TÓM TẮT")
    print("=" * 112)
    print("Số bảng giữ toàn bộ                 :", len(KEEP_WHOLE))
    print("Bảng giữ một phần                   :", PARTIAL_TABLE)
    print("Bản ghi biểu GV cấu trúc giữ lại    :", gv_structured_total)
    print("Bản ghi cấu trúc khác sẽ xóa        :", delete_structured_total)
    print("Số bảng xóa sạch toàn bộ            :", len(full_delete_tables()))
    print("Tổng bản ghi dự kiến xóa            :", total_delete)
    print("Thứ tự DELETE đã kiểm tra FK        : ĐẠT")
    print("Bảng GIỮ tham chiếu bảng XÓA        : KHÔNG")
    print()

    return {
        "keep_before": keep_before,
        "structured_before": structured,
        "gv_structured_total": gv_structured_total,
        "delete_structured_total": delete_structured_total,
        "full_counts": full_counts,
        "delete_order": order,
        "total_delete": total_delete,
    }


def backup_database(preview: dict) -> Path:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup_dir = (
        EXPORT_DIR
        / f"backup_truoc_DON_SACH_DU_LIEU_THU_NGHIEM_{stamp}"
    )
    backup_dir.mkdir(parents=True, exist_ok=False)

    backup_db = backup_dir / "phocap.db"

    src = sqlite3.connect(
        str(DB_PATH),
        timeout=30,
    )
    dst = sqlite3.connect(
        str(backup_db),
        timeout=30,
    )

    try:
        src.execute("PRAGMA busy_timeout=30000")
        src.backup(
            dst,
            pages=1000,
            sleep=0.05,
        )
        dst.commit()
    finally:
        dst.close()
        src.close()

    check = sqlite3.connect(str(backup_db))

    try:
        integrity = str(
            check.execute(
                "PRAGMA integrity_check"
            ).fetchone()[0]
        )
        fk_errors = check.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()
    finally:
        check.close()

    if integrity.lower() != "ok":
        raise RuntimeError(
            "Backup không đạt integrity_check."
        )

    if fk_errors:
        raise RuntimeError(
            f"Backup có {len(fk_errors)} lỗi foreign key."
        )

    metadata = {
        "type": "backup_before_clean_trial_business_data",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "database": str(DB_PATH),
        "backup_database": str(backup_db),
        "confirmation_phrase": CONFIRM_TEXT,
        "keep_whole": sorted(KEEP_WHOLE),
        "keep_structured_form_codes": sorted(
            KEEP_STRUCTURED_FORM_CODES
        ),
        "keep_counts_before": preview["keep_before"],
        "structured_counts_before": preview[
            "structured_before"
        ],
        "full_delete_counts_before": preview[
            "full_counts"
        ],
        "total_rows_expected_to_delete": preview[
            "total_delete"
        ],
        "integrity_check": integrity,
        "foreign_key_check_total": len(fk_errors),
    }

    (
        backup_dir
        / "thong_tin_backup.json"
    ).write_text(
        json.dumps(
            metadata,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return backup_dir


def delete_partial_structured(
    con: sqlite3.Connection,
) -> int:
    codes = sorted(KEEP_STRUCTURED_FORM_CODES)
    marks = ",".join("?" for _ in codes)

    cur = con.execute(
        f"""
        DELETE FROM {qi(PARTIAL_TABLE)}
        WHERE UPPER(COALESCE(form_code, ''))
              NOT IN ({marks})
        """,
        tuple(codes),
    )

    return max(0, int(cur.rowcount or 0))


def verify_after(
    con: sqlite3.Connection,
    preview: dict,
) -> dict:
    # 1. Tất cả bảng xóa sạch phải = 0.
    nonzero = {}

    for table in sorted(full_delete_tables()):
        c = table_count(con, table)
        if c != 0:
            nonzero[table] = c

    if nonzero:
        detail = ", ".join(
            f"{table}={count}"
            for table, count in nonzero.items()
        )
        raise RuntimeError(
            "Sau DELETE vẫn còn dữ liệu ở bảng cần sạch: "
            + detail
        )

    # 2. Các bảng giữ toàn bộ phải giữ nguyên chính xác số bản ghi.
    keep_after = keep_snapshot(con)
    changed_keep = {}

    for table, before in preview["keep_before"].items():
        after = keep_after[table]
        if after != before:
            changed_keep[table] = {
                "before": before,
                "after": after,
            }

    if changed_keep:
        detail = "; ".join(
            f"{table}: {v['before']} -> {v['after']}"
            for table, v in changed_keep.items()
        )
        raise RuntimeError(
            "Phát hiện bảng cần GIỮ bị thay đổi: "
            + detail
        )

    # 3. Structured report chỉ được còn hai biểu GV.
    struct_after = structured_counts(con)

    unexpected_codes = {
        code: total
        for code, total in struct_after.items()
        if code not in KEEP_STRUCTURED_FORM_CODES
        and total > 0
    }

    if unexpected_codes:
        detail = ", ".join(
            f"{code or '(trống)'}={total}"
            for code, total in unexpected_codes.items()
        )
        raise RuntimeError(
            "school_structured_report_inputs vẫn còn "
            "biểu ngoài phạm vi GV: "
            + detail
        )

    expected_gv = {
        code: total
        for code, total in preview[
            "structured_before"
        ].items()
        if code in KEEP_STRUCTURED_FORM_CODES
    }

    actual_gv = {
        code: total
        for code, total in struct_after.items()
        if code in KEEP_STRUCTURED_FORM_CODES
    }

    for code in KEEP_STRUCTURED_FORM_CODES:
        if actual_gv.get(code, 0) != expected_gv.get(code, 0):
            raise RuntimeError(
                f"Biểu giáo viên {code} bị thay đổi: "
                f"{expected_gv.get(code, 0)} -> "
                f"{actual_gv.get(code, 0)}"
            )

    # 4. Kiểm tra toàn DB trước COMMIT.
    fk_errors = con.execute(
        "PRAGMA foreign_key_check"
    ).fetchall()

    if fk_errors:
        print()
        print("FOREIGN KEY ERRORS SAU DELETE:")
        for row in fk_errors[:20]:
            print(" -", tuple(row))

        raise RuntimeError(
            f"foreign_key_check còn {len(fk_errors)} lỗi."
        )

    integrity = str(
        con.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]
    )

    if integrity.lower() != "ok":
        raise RuntimeError(
            "integrity_check sau DELETE không đạt: "
            + integrity
        )

    return {
        "keep_after": keep_after,
        "structured_after": struct_after,
        "foreign_key_errors": 0,
        "integrity": integrity,
    }


def main() -> int:
    print("=" * 112)
    print(
        "DỌN SẠCH DỮ LIỆU THỬ NGHIỆM "
        "– GIỮ XÃ / TRƯỜNG / LỚP / GIÁO VIÊN"
    )
    print("=" * 112)
    print()
    print("CÔNG CỤ NÀY SẼ XÓA DỮ LIỆU NGHIỆP VỤ THỬ NGHIỆM:")
    print(" - Học sinh và quá trình học.")
    print(" - Hộ dân và thành viên hộ.")
    print(" - Toàn bộ đợt/phiếu điều tra.")
    print(" - Phân công, tổ điều tra, trạng thái khóa/điều hành.")
    print(" - Lịch sử dữ liệu, import thử nghiệm và các nhật ký liên quan.")
    print(" - CSVC/tài chính/biểu cấu trúc không thuộc nhóm giáo viên.")
    print()
    print("SẼ GIỮ:")
    print(" - 130 xã/phường.")
    print(" - Danh mục trường.")
    print(" - Danh mục lớp hiện có.")
    print(" - Hồ sơ giáo viên/đội ngũ và dữ liệu đội ngũ theo năm.")
    print(" - Dữ liệu biểu GV và mạng lưới trường/lớp.")
    print(" - Danh mục THPT tham chiếu.")
    print(" - Tài khoản, vai trò và năm học để hệ thống tiếp tục hoạt động.")
    print()
    print("AN TOÀN:")
    print(" - Khóa cứng schema 49 bảng đã kiểm tra.")
    print(" - Database phải đạt integrity_check + foreign_key_check.")
    print(" - Xem trước trước khi xóa.")
    print(" - Backup SQLite đầy đủ trước DELETE.")
    print(" - BEGIN IMMEDIATE, kiểm tra lại trước COMMIT.")
    print(" - Có lỗi -> ROLLBACK toàn bộ.")
    print()

    if not DB_PATH.exists():
        print("Không tìm thấy database:", DB_PATH)
        return 1

    con = sqlite3.connect(
        str(DB_PATH),
        timeout=30,
    )

    try:
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("PRAGMA busy_timeout=30000")

        print("ĐANG KIỂM TRA DATABASE HIỆN TẠI...")
        live_integrity(con)
        print(" - integrity_check: OK")
        print(" - foreign_key_check: 0 lỗi")

        preview = print_preview(con)

    except Exception as exc:
        print()
        print("KHÔNG ĐỦ ĐIỀU KIỆN DỌN:")
        print(exc)
        print("DATABASE CHƯA BỊ THAY ĐỔI.")
        return 1

    finally:
        con.close()

    print()
    print("=" * 112)
    print("4. XÁC NHẬN CUỐI")
    print("=" * 112)
    print("Nhập CHÍNH XÁC câu sau để tiếp tục:")
    print()
    print(CONFIRM_TEXT)
    print()

    typed = input("Xác nhận: ").strip()

    if typed != CONFIRM_TEXT:
        print()
        print("SAI CÂU XÁC NHẬN -> DỪNG.")
        print("DATABASE CHƯA BỊ THAY ĐỔI.")
        return 0

    print()
    print("ĐANG TẠO BACKUP TOÀN BỘ DATABASE...")

    try:
        backup_dir = backup_database(preview)
    except Exception as exc:
        print()
        print("KHÔNG TẠO ĐƯỢC BACKUP:", exc)
        print("DỪNG. DATABASE CHƯA BỊ XÓA.")
        return 1

    print("BACKUP ĐẠT KIỂM TRA:")
    print(" ", backup_dir)

    con = sqlite3.connect(
        str(DB_PATH),
        timeout=30,
    )

    deleted = {}

    try:
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("PRAGMA busy_timeout=30000")
        con.execute("BEGIN IMMEDIATE")

        # Tái kiểm tra ngay trong transaction.
        verify_schema(con)
        verify_keep_fk_safety(con)

        keep_now = keep_snapshot(con)
        if keep_now != preview["keep_before"]:
            raise RuntimeError(
                "Dữ liệu bảng GIỮ đã thay đổi sau bước xem trước. "
                "Dừng để tránh xóa trên trạng thái khác."
            )

        structured_now = structured_counts(con)
        if structured_now != preview["structured_before"]:
            raise RuntimeError(
                "Dữ liệu biểu cấu trúc đã thay đổi sau bước xem trước. "
                "Dừng an toàn."
            )

        current_full_counts = {
            table: table_count(con, table)
            for table in sorted(full_delete_tables())
        }

        if current_full_counts != preview["full_counts"]:
            raise RuntimeError(
                "Dữ liệu thử nghiệm đã thay đổi sau bước xem trước. "
                "Dừng an toàn."
            )

        order = delete_order(con)

        for table in order:
            if table == PARTIAL_TABLE:
                deleted[table] = delete_partial_structured(con)
                continue

            cur = con.execute(
                f"DELETE FROM {qi(table)}"
            )
            deleted[table] = max(
                0,
                int(cur.rowcount or 0),
            )

        after = verify_after(
            con,
            preview,
        )

        con.commit()

    except Exception as exc:
        con.rollback()
        print()
        print("=" * 112)
        print("DỌN DỮ LIỆU KHÔNG THÀNH CÔNG")
        print("=" * 112)
        print(exc)
        print()
        print("ĐÃ ROLLBACK TOÀN BỘ DATABASE.")
        print("Backup an toàn vẫn còn tại:")
        print(" ", backup_dir)
        return 1

    finally:
        con.close()

    print()
    print("=" * 112)
    print("DỌN SẠCH DỮ LIỆU THỬ NGHIỆM THÀNH CÔNG")
    print("=" * 112)
    print()

    for table in sorted(deleted):
        print(
            f" - {table:<45}: "
            f"đã xóa {deleted[table]} bản ghi"
        )

    print()
    print("XÁC NHẬN SAU DỌN:")
    print(" - Học sinh                    : 0")
    print(" - Hộ dân                      : 0")
    print(" - Thành viên hộ               : 0")
    print(" - Đợt điều tra                : 0")
    print(" - Phiếu điều tra              : 0")
    print(" - Các bảng thử nghiệm khác    : 0")
    print(" - foreign_key_check           : 0 lỗi")
    print(" - integrity_check             : ok")
    print()
    print("DỮ LIỆU NỀN ĐƯỢC GIỮ NGUYÊN:")

    for table in sorted(after["keep_after"]):
        print(
            f" - {table:<42}: "
            f"{after['keep_after'][table]}"
        )

    print()
    print("BIỂU ĐỘI NGŨ CẤU TRÚC GIỮ LẠI:")

    if after["structured_after"]:
        for code, total in sorted(
            after["structured_after"].items()
        ):
            print(
                f" - {code or '(trống)':<20}: {total}"
            )
    else:
        print(" - Không có bản ghi.")

    print()
    print("BACKUP TRƯỚC KHI DỌN:")
    print(" ", backup_dir)
    print()
    print(
        "Bây giờ có thể khởi động lại Uvicorn "
        "và kiểm tra giao diện."
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
