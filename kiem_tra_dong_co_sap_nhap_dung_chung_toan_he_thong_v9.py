# -*- coding: utf-8 -*-
r"""
DRY-RUN V9 - ĐỘNG CƠ SÁP NHẬP TRƯỜNG DÙNG CHUNG TOÀN HỆ THỐNG
================================================================

MỤC TIÊU
--------
Xây bộ kiểm tra dùng chung trước khi tích hợp chức năng sáp nhập vào phần mềm.

Nguyên tắc:
1. Dữ liệu lịch sử năm cũ giữ nguyên.
2. Năm hiện hành:
   - dữ liệu trường nguồn -> trường đích;
   - dữ liệu trường đích giữ nguyên;
   - kiểm tra UNIQUE trước khi chuyển.
3. Đội ngũ:
   - rollover năm trước của chính target + các source;
   - loại trùng staff_member_id;
   - không tự rollover người nghỉ/chuyển.
4. Lớp:
   - chuyển class của source trong năm hiện hành sang target;
   - phát hiện trùng (school_id, school_year_id, name).
5. Học sinh:
   - students là master, không đổi school_id vì bảng không có school_id;
   - student_enrollments mới là quan hệ HS-trường-lớp-năm;
   - chỉ chuyển enrollment khi có dữ liệu thật.
6. Điều tra:
   - survey_person_year_records có thể chuyển school_id/class_id theo năm hiện hành;
   - KHÔNG tự biến survey_people thành students.
7. Tài khoản:
   - CBQL/GV của source đi về target;
   - tài khoản Trường nguồn giữ ở source và khóa;
   - tài khoản Trường gốc của target giữ active.
8. Các bảng khác có school_id + school_year_id:
   - kiểm tra current-year source rows;
   - mô phỏng đổi school_id;
   - phát hiện UNIQUE conflict.
9. Bảng có school_id nhưng không có school_year_id:
   - KHÔNG tự động xử lý nếu chưa có policy rõ;
   - xuất báo cáo để phân loại.

V9 CHỈ ĐỌC - KHÔNG SỬA DATABASE.

CHẠY
----
    cd C:\PhoCap
    .\.venv\Scripts\python.exe .\kiem_tra_dong_co_sap_nhap_dung_chung_toan_he_thong_v9.py
"""

from __future__ import annotations

import csv
import sqlite3
import sys
import unicodedata
import re
import zipfile
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(r"C:\PhoCap")
DB_PATH = PROJECT_ROOT / "data" / "phocap.db"

MERGE_MAP = {
    750: 748,
    751: 748,
    749: 747,
    1181: 1178,
    1180: 1179,
    1608: 1605,
    1607: 1606,
}

SOURCE_IDS = tuple(sorted(MERGE_MAP))
TARGET_IDS = tuple(sorted(set(MERGE_MAP.values())))
ALL_IDS = tuple(sorted(set(SOURCE_IDS) | set(TARGET_IDS)))


class AuditAbort(RuntimeError):
    pass


def qident(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def markers(n: int) -> str:
    return ",".join("?" for _ in range(n))


def connect_ro(path: Path) -> sqlite3.Connection:
    uri = path.resolve().as_uri() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def tables(conn: sqlite3.Connection) -> list[str]:
    return [
        r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' "
            "ORDER BY name"
        ).fetchall()
    ]


def columns(conn: sqlite3.Connection, table: str) -> list[dict]:
    rows = conn.execute(f"PRAGMA table_info({qident(table)})").fetchall()
    return [
        {
            "cid": r[0], "name": r[1], "type": r[2],
            "notnull": r[3], "default": r[4], "pk": r[5],
        }
        for r in rows
    ]


def colset(conn: sqlite3.Connection, table: str) -> set[str]:
    return {x["name"] for x in columns(conn, table)}


def unique_indexes(conn: sqlite3.Connection, table: str) -> list[dict]:
    out = []
    for r in conn.execute(f"PRAGMA index_list({qident(table)})").fetchall():
        if int(r[2]) != 1:
            continue
        idx_name = r[1]
        idx_rows = conn.execute(
            f"PRAGMA index_info({qident(idx_name)})"
        ).fetchall()
        cols_ = []
        for x in idx_rows:
            cols_.append("<EXPRESSION>" if x[2] is None else str(x[2]))
        out.append({
            "index_name": str(idx_name),
            "columns_list": cols_,
            "columns": ",".join(cols_),
        })
    return out


def foreign_keys(conn: sqlite3.Connection, table: str) -> list[dict]:
    rows = conn.execute(f"PRAGMA foreign_key_list({qident(table)})").fetchall()
    return [
        {
            "id": r[0], "seq": r[1], "ref_table": r[2],
            "from_col": r[3], "to_col": r[4] or "id",
            "on_update": r[5], "on_delete": r[6],
        }
        for r in rows
    ]


def detect_year_ids(conn: sqlite3.Connection) -> tuple[int, int]:
    if "school_years" not in tables(conn):
        raise AuditAbort("Không có bảng school_years.")
    cs = colset(conn, "school_years")
    label_col = next(
        (c for c in ("name", "label", "school_year", "year_name") if c in cs),
        None,
    )
    if not label_col:
        raise AuditAbort("Không xác định cột tên năm học.")

    prev = target = None
    rows = conn.execute(
        f"SELECT id,{qident(label_col)} FROM school_years ORDER BY id"
    ).fetchall()
    for r in rows:
        label = str(r[1] or "")
        if "2025" in label and "2026" in label:
            prev = int(r[0])
        if "2026" in label and "2027" in label:
            target = int(r[0])
    if prev is None or target is None:
        raise AuditAbort(
            f"Không xác định đủ năm học: previous={prev}, target={target}"
        )
    return prev, target


def school_names(conn: sqlite3.Connection) -> dict[int, str]:
    cs = colset(conn, "schools")
    name_col = next(
        (c for c in ("name", "school_name", "ten_truong") if c in cs),
        None
    )
    if not name_col:
        return {}
    rows = conn.execute(
        f"SELECT id,{qident(name_col)} FROM schools "
        f"WHERE id IN ({markers(len(ALL_IDS))})",
        ALL_IDS,
    ).fetchall()
    return {int(r[0]): str(r[1]) for r in rows}


def normalize(v) -> str:
    if v is None:
        return ""
    s = str(v).strip().lower()
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())


def classify_staff(row) -> str:
    keys = row.keys()
    text = " ".join(
        normalize(row[c])
        for c in (
            "position_group", "position_title",
            "source_level", "teaching_level",
            "source_status_label"
        )
        if c in keys and row[c] not in (None, "")
    )
    if any(x in text for x in (
        "quan ly", "cbql", "hieu truong", "pho hieu truong",
        "principal", "manager", "management"
    )):
        return "QUAN_LY"
    if any(x in text for x in (
        "nhan vien", "ke toan", "van thu", "thu vien",
        "thiet bi", "y te", "bao ve", "phuc vu",
        "cap duong", "thu quy", "employee"
    )):
        return "NHAN_VIEN"
    if any(x in text for x in ("giao vien", "teacher", "teaching", "gv")):
        return "GIAO_VIEN"
    return "CHUA_XAC_DINH"


def staff_inactive(row) -> bool:
    keys = row.keys()
    if "is_active" in keys and row["is_active"] in (0, False, "0"):
        return True
    text = " ".join(
        normalize(row[c])
        for c in ("status_code", "source_status_label", "notes")
        if c in keys and row[c] not in (None, "")
    )
    return any(x in text for x in (
        "nghi viec", "thoi viec", "nghi huu",
        "chuyen di", "da chuyen", "inactive",
        "resigned", "retired", "terminated"
    ))


def generic_unique_conflicts(
    conn: sqlite3.Connection,
    table: str,
    source_id: int,
    target_id: int,
    target_year_id: int,
) -> list[dict]:
    """
    Mô phỏng đổi school_id source->target cho các row năm hiện hành.
    Chỉ kiểm tra UNIQUE index gồm toàn cột thật; index expression được báo REVIEW.
    """
    cs = colset(conn, table)
    if not {"school_id", "school_year_id"} <= cs:
        return []

    source_rows = conn.execute(
        f"SELECT * FROM {qident(table)} "
        "WHERE school_id=? AND school_year_id=?",
        (source_id, target_year_id),
    ).fetchall()
    if not source_rows:
        return []

    conflicts = []
    for idx in unique_indexes(conn, table):
        idx_cols = idx["columns_list"]
        if "<EXPRESSION>" in idx_cols:
            conflicts.append({
                "table": table,
                "source_school_id": source_id,
                "target_school_id": target_id,
                "index_name": idx["index_name"],
                "unique_columns": idx["columns"],
                "source_row_id": "",
                "result": "REVIEW_EXPRESSION_INDEX",
                "detail": "UNIQUE index có biểu thức; V9 không tự suy diễn.",
            })
            continue

        if "school_id" not in idx_cols:
            continue

        for src in source_rows:
            where_parts = []
            params = []
            for c in idx_cols:
                value = target_id if c == "school_id" else src[c]
                if value is None:
                    where_parts.append(f"{qident(c)} IS NULL")
                else:
                    where_parts.append(f"{qident(c)}=?")
                    params.append(value)

            sql = (
                f"SELECT id FROM {qident(table)} WHERE "
                + " AND ".join(where_parts)
                + " LIMIT 1"
            )
            existing = conn.execute(sql, params).fetchone()
            if existing:
                conflicts.append({
                    "table": table,
                    "source_school_id": source_id,
                    "target_school_id": target_id,
                    "index_name": idx["index_name"],
                    "unique_columns": idx["columns"],
                    "source_row_id": src["id"] if "id" in src.keys() else "",
                    "result": "CONFLICT",
                    "detail": f"Target đã có row id={existing['id']}.",
                })
    return conflicts


def table_strategy(table: str, cs: set[str]) -> str:
    if table == "students":
        return "MASTER_KEEP"
    if table == "staff_year_records":
        return "STAFF_ROLLOVER_SPECIAL"
    if table == "classes":
        return "CLASS_CURRENT_MOVE"
    if table == "student_enrollments":
        return "ENROLLMENT_CURRENT_MOVE"
    if table == "survey_person_year_records":
        return "SURVEY_CURRENT_MOVE"
    if table == "users":
        return "USER_ACCOUNT_SPECIAL"
    if {"school_id", "school_year_id"} <= cs:
        return "GENERIC_CURRENT_YEAR_MOVE"
    if "school_id" in cs:
        return "NO_YEAR_POLICY_REQUIRED"
    return "NO_SCHOOL_SCOPE"


def write_csv(path: Path, headers: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def audit() -> None:
    print("=" * 120)
    print("DRY-RUN V9 - ĐỘNG CƠ SÁP NHẬP TRƯỜNG DÙNG CHUNG TOÀN HỆ THỐNG")
    print("=" * 120)
    print("Chế độ: CHỈ ĐỌC - KHÔNG SỬA DATABASE")

    if not DB_PATH.exists():
        raise AuditAbort(f"Không tìm thấy database: {DB_PATH}")

    conn = connect_ro(DB_PATH)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = PROJECT_ROOT / f"dry_run_dong_co_sap_nhap_dung_chung_v9_{ts}"
    out_dir.mkdir(parents=True, exist_ok=False)

    try:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise AuditAbort(f"integrity_check={integrity}")

        previous_year_id, target_year_id = detect_year_ids(conn)
        names = school_names(conn)

        # 1. Catalog strategy toàn bộ bảng.
        strategy_rows = []
        no_year_tables = []
        generic_year_tables = []

        for table in tables(conn):
            cs = colset(conn, table)
            strategy = table_strategy(table, cs)
            source_current = 0
            historical_source = 0

            if {"school_id", "school_year_id"} <= cs:
                source_current = conn.execute(
                    f"SELECT COUNT(*) FROM {qident(table)} "
                    f"WHERE school_id IN ({markers(len(SOURCE_IDS))}) "
                    "AND school_year_id=?",
                    list(SOURCE_IDS) + [target_year_id],
                ).fetchone()[0]

                historical_source = conn.execute(
                    f"SELECT COUNT(*) FROM {qident(table)} "
                    f"WHERE school_id IN ({markers(len(SOURCE_IDS))}) "
                    "AND school_year_id<>?",
                    list(SOURCE_IDS) + [target_year_id],
                ).fetchone()[0]

            elif "school_id" in cs:
                source_current = conn.execute(
                    f"SELECT COUNT(*) FROM {qident(table)} "
                    f"WHERE school_id IN ({markers(len(SOURCE_IDS))})",
                    SOURCE_IDS,
                ).fetchone()[0]

            row = {
                "table": table,
                "strategy": strategy,
                "has_school_id": "YES" if "school_id" in cs else "NO",
                "has_school_year_id": "YES" if "school_year_id" in cs else "NO",
                "source_rows_requiring_policy": int(source_current),
                "historical_source_rows_preserve": int(historical_source),
                "unique_indexes": " | ".join(
                    x["columns"] for x in unique_indexes(conn, table)
                ),
            }
            strategy_rows.append(row)

            if strategy == "NO_YEAR_POLICY_REQUIRED" and source_current:
                no_year_tables.append(row)
            if strategy == "GENERIC_CURRENT_YEAR_MOVE":
                generic_year_tables.append(row)

        # 2. UNIQUE conflicts cho mọi bảng year+school, bao gồm classes.
        conflict_rows = []
        for table in tables(conn):
            cs = colset(conn, table)
            if not {"school_id", "school_year_id"} <= cs:
                continue
            for source_id, target_id in MERGE_MAP.items():
                conflict_rows.extend(
                    generic_unique_conflicts(
                        conn, table, source_id, target_id, target_year_id
                    )
                )

        real_conflicts = [r for r in conflict_rows if r["result"] == "CONFLICT"]
        expression_reviews = [
            r for r in conflict_rows if r["result"] == "REVIEW_EXPRESSION_INDEX"
        ]

        # 3. Classes current-year.
        class_rows = []
        class_conflicts = []
        if "classes" in tables(conn):
            for source_id, target_id in MERGE_MAP.items():
                rows = conn.execute(
                    "SELECT id,name,school_year_id,school_id,is_active "
                    "FROM classes WHERE school_id=? AND school_year_id=? "
                    "ORDER BY id",
                    (source_id, target_year_id),
                ).fetchall()

                for r in rows:
                    existing = conn.execute(
                        "SELECT id FROM classes "
                        "WHERE school_id=? AND school_year_id=? AND name=? LIMIT 1",
                        (target_id, target_year_id, r["name"]),
                    ).fetchone()
                    result = "MOVE_OK" if not existing else "NAME_CONFLICT"
                    class_rows.append({
                        "class_id": r["id"],
                        "class_name": r["name"],
                        "source_school_id": source_id,
                        "source_school_name": names.get(source_id, ""),
                        "target_school_id": target_id,
                        "target_school_name": names.get(target_id, ""),
                        "school_year_id": target_year_id,
                        "result": result,
                        "conflict_target_class_id": existing["id"] if existing else "",
                    })
                    if existing:
                        class_conflicts.append(class_rows[-1])

        # 4. Enrollment.
        enrollment_rows = []
        if "student_enrollments" in tables(conn):
            for source_id, target_id in MERGE_MAP.items():
                n = conn.execute(
                    "SELECT COUNT(*) FROM student_enrollments "
                    "WHERE school_id=? AND school_year_id=?",
                    (source_id, target_year_id),
                ).fetchone()[0]
                enrollment_rows.append({
                    "source_school_id": source_id,
                    "source_school_name": names.get(source_id, ""),
                    "target_school_id": target_id,
                    "target_school_name": names.get(target_id, ""),
                    "school_year_id": target_year_id,
                    "source_enrollments_to_move": int(n),
                    "policy": (
                        "MOVE_SCHOOL_ID_KEEP_STUDENT_ID_CLASS_ID_AFTER_CLASS_MOVE"
                    ),
                })

        # 5. Students master.
        student_master_count = (
            conn.execute("SELECT COUNT(*) FROM students").fetchone()[0]
            if "students" in tables(conn) else 0
        )
        enrollment_total = (
            conn.execute("SELECT COUNT(*) FROM student_enrollments").fetchone()[0]
            if "student_enrollments" in tables(conn) else 0
        )

        # 6. Staff rollover readiness.
        staff_summary = []
        staff_duplicate = []
        staff_unclassified = []
        if "staff_year_records" in tables(conn):
            origin_by_target = defaultdict(list)
            for tid in TARGET_IDS:
                origin_by_target[tid].append(tid)
            for sid, tid in MERGE_MAP.items():
                origin_by_target[tid].append(sid)

            for tid in TARGET_IDS:
                origins = sorted(set(origin_by_target[tid]))
                prev_rows = conn.execute(
                    f"SELECT * FROM staff_year_records "
                    f"WHERE school_year_id=? "
                    f"AND school_id IN ({markers(len(origins))})",
                    [previous_year_id] + origins,
                ).fetchall()
                current_rows = conn.execute(
                    "SELECT * FROM staff_year_records "
                    "WHERE school_year_id=? AND school_id=?",
                    (target_year_id, tid),
                ).fetchall()
                current_ids = {int(r["staff_member_id"]) for r in current_rows}

                grouped = defaultdict(list)
                for r in prev_rows:
                    grouped[int(r["staff_member_id"])].append(r)

                candidates = []
                for staff_id, rs in grouped.items():
                    if len(rs) > 1:
                        staff_duplicate.append({
                            "target_school_id": tid,
                            "staff_member_id": staff_id,
                            "origin_record_ids": ",".join(str(x["id"]) for x in rs),
                        })
                        continue
                    r = rs[0]
                    category = classify_staff(r)
                    if category == "CHUA_XAC_DINH":
                        staff_unclassified.append({
                            "target_school_id": tid,
                            "source_record_id": r["id"],
                            "staff_member_id": staff_id,
                        })
                    if staff_id not in current_ids and not staff_inactive(r):
                        candidates.append(r)

                staff_summary.append({
                    "target_school_id": tid,
                    "target_school_name": names.get(tid, ""),
                    "previous_union_rows": len(prev_rows),
                    "current_rows": len(current_rows),
                    "rollover_candidates_now": len(candidates),
                    "duplicate_staff": sum(
                        1 for x in staff_duplicate if x["target_school_id"] == tid
                    ),
                    "unclassified": sum(
                        1 for x in staff_unclassified if x["target_school_id"] == tid
                    ),
                })

        # 7. Users.
        user_summary = []
        if "users" in tables(conn):
            for source_id, target_id in MERGE_MAP.items():
                rows = conn.execute(
                    "SELECT id,username,role_id,is_active,school_id "
                    "FROM users WHERE school_id=? ORDER BY id",
                    (source_id,),
                ).fetchall()
                school_logins = [r for r in rows if str(r["username"]).startswith("truong_")]
                cbql = [r for r in rows if str(r["username"]).startswith("cbql.")]
                teachers = [r for r in rows if str(r["username"]).startswith("gv.")]
                other = [
                    r for r in rows
                    if r not in school_logins and r not in cbql and r not in teachers
                ]
                user_summary.append({
                    "source_school_id": source_id,
                    "source_school_name": names.get(source_id, ""),
                    "target_school_id": target_id,
                    "target_school_name": names.get(target_id, ""),
                    "current_users_still_at_source": len(rows),
                    "source_school_login": len(school_logins),
                    "cbql": len(cbql),
                    "teachers": len(teachers),
                    "other": len(other),
                    "policy": (
                        "truong_: KEEP_SOURCE_DISABLE; cbql/gv: MOVE_TARGET"
                    ),
                })

        # Cổng an toàn của engine.
        unknown_no_year_with_data = [
            x for x in no_year_tables
            if x["table"] != "users"
        ]

        gates = [
            {
                "check": "integrity_check",
                "result": "PASS",
                "detail": integrity,
            },
            {
                "check": "history_policy",
                "result": "PASS",
                "detail": "Rows school_year_id != target year are preserve-only.",
            },
            {
                "check": "students_master_policy",
                "result": "PASS",
                "detail": (
                    f"students={student_master_count}; master không có school_id, không di chuyển."
                ),
            },
            {
                "check": "enrollment_policy",
                "result": "PASS",
                "detail": (
                    f"student_enrollments={enrollment_total}; chỉ move khi có dữ liệu thật."
                ),
            },
            {
                "check": "class_name_conflicts",
                "result": "PASS" if not class_conflicts else "FAIL",
                "detail": str(len(class_conflicts)),
            },
            {
                "check": "generic_unique_conflicts",
                "result": "PASS" if not real_conflicts else "FAIL",
                "detail": str(len(real_conflicts)),
            },
            {
                "check": "expression_unique_indexes_need_review",
                "result": "PASS" if not expression_reviews else "REVIEW",
                "detail": str(len(expression_reviews)),
            },
            {
                "check": "staff_duplicate",
                "result": "PASS" if not staff_duplicate else "FAIL",
                "detail": str(len(staff_duplicate)),
            },
            {
                "check": "staff_unclassified",
                "result": "PASS" if not staff_unclassified else "FAIL",
                "detail": str(len(staff_unclassified)),
            },
            {
                "check": "unknown_no_year_tables_with_source_data",
                "result": "PASS" if not unknown_no_year_with_data else "REVIEW",
                "detail": " | ".join(x["table"] for x in unknown_no_year_with_data),
            },
        ]

        safe_generic_executor = (
            not class_conflicts
            and not real_conflicts
            and not staff_duplicate
            and not staff_unclassified
            and not unknown_no_year_with_data
        )

        write_csv(
            out_dir / "200_TABLE_STRATEGY_CATALOG.csv",
            [
                "table", "strategy",
                "has_school_id", "has_school_year_id",
                "source_rows_requiring_policy",
                "historical_source_rows_preserve",
                "unique_indexes",
            ],
            strategy_rows,
        )
        write_csv(
            out_dir / "201_UNIQUE_CONFLICTS.csv",
            [
                "table", "source_school_id", "target_school_id",
                "index_name", "unique_columns",
                "source_row_id", "result", "detail",
            ],
            conflict_rows,
        )
        write_csv(
            out_dir / "202_CLASSES_CURRENT_YEAR_PLAN.csv",
            [
                "class_id", "class_name",
                "source_school_id", "source_school_name",
                "target_school_id", "target_school_name",
                "school_year_id", "result",
                "conflict_target_class_id",
            ],
            class_rows,
        )
        write_csv(
            out_dir / "203_ENROLLMENT_CURRENT_YEAR_PLAN.csv",
            [
                "source_school_id", "source_school_name",
                "target_school_id", "target_school_name",
                "school_year_id",
                "source_enrollments_to_move", "policy",
            ],
            enrollment_rows,
        )
        write_csv(
            out_dir / "204_STAFF_ROLLOVER_STATUS.csv",
            [
                "target_school_id", "target_school_name",
                "previous_union_rows", "current_rows",
                "rollover_candidates_now",
                "duplicate_staff", "unclassified",
            ],
            staff_summary,
        )
        write_csv(
            out_dir / "205_USER_ACCOUNT_POLICY_STATUS.csv",
            [
                "source_school_id", "source_school_name",
                "target_school_id", "target_school_name",
                "current_users_still_at_source",
                "source_school_login", "cbql", "teachers",
                "other", "policy",
            ],
            user_summary,
        )
        write_csv(
            out_dir / "206_NO_YEAR_TABLES_REQUIRING_POLICY.csv",
            [
                "table", "strategy",
                "has_school_id", "has_school_year_id",
                "source_rows_requiring_policy",
                "historical_source_rows_preserve",
                "unique_indexes",
            ],
            no_year_tables,
        )
        write_csv(
            out_dir / "207_GATE_GENERIC_EXECUTOR.csv",
            ["check", "result", "detail"],
            gates,
        )

        summary = out_dir / "00_TONG_QUAN_V9.txt"
        with summary.open("w", encoding="utf-8") as f:
            f.write(
                "DRY-RUN V9 - ĐỘNG CƠ SÁP NHẬP TRƯỜNG DÙNG CHUNG TOÀN HỆ THỐNG\n"
            )
            f.write("=" * 120 + "\n")
            f.write("CHẾ ĐỘ: CHỈ ĐỌC - KHÔNG SỬA DATABASE\n")
            f.write(f"Database: {DB_PATH}\n")
            f.write(f"Năm trước: {previous_year_id}\n")
            f.write(f"Năm hiện hành: {target_year_id}\n\n")

            f.write("CHÍNH SÁCH DÙNG CHUNG\n")
            f.write("- Lịch sử: giữ nguyên.\n")
            f.write("- Staff: rollover target+self + sources, chống trùng.\n")
            f.write("- Classes: move current-year source->target, chống trùng tên.\n")
            f.write("- Students: master giữ nguyên.\n")
            f.write("- Enrollments: move current-year source->target sau class move.\n")
            f.write("- Survey year records: move school_id theo năm, không tạo students.\n")
            f.write("- Users: truong_ nguồn khóa tại source; CBQL/GV đi target.\n\n")

            f.write("TRẠNG THÁI HIỆN TẠI\n")
            f.write(f"- students: {student_master_count}\n")
            f.write(f"- student_enrollments: {enrollment_total}\n")
            f.write(f"- class conflicts: {len(class_conflicts)}\n")
            f.write(f"- generic unique conflicts: {len(real_conflicts)}\n")
            f.write(f"- expression index reviews: {len(expression_reviews)}\n")
            f.write(f"- staff duplicate: {len(staff_duplicate)}\n")
            f.write(f"- staff unclassified: {len(staff_unclassified)}\n")
            f.write(
                f"- unknown no-year tables with source data: "
                f"{len(unknown_no_year_with_data)}\n\n"
            )

            f.write("CỔNG\n")
            for g in gates:
                f.write(f"- [{g['result']}] {g['check']}: {g['detail']}\n")

            f.write("\nKẾT LUẬN\n")
            f.write(
                f"SAFE_TO_BUILD_GENERIC_EXECUTOR = "
                f"{'YES' if safe_generic_executor else 'NO'}\n"
            )
            f.write(
                "- V9 chỉ xây và kiểm chứng chính sách. Chưa sửa database.\n"
            )
            if student_master_count == 0 or enrollment_total == 0:
                f.write(
                    "- Chưa thể acceptance-test nhánh học sinh bằng dữ liệu thật "
                    "vì roster Nhà trường hiện đang trống.\n"
                )

        zip_path = PROJECT_ROOT / f"dry_run_dong_co_sap_nhap_dung_chung_v9_{ts}.zip"
        with zipfile.ZipFile(
            zip_path, "w", compression=zipfile.ZIP_DEFLATED
        ) as zf:
            for p in sorted(out_dir.iterdir()):
                zf.write(p, arcname=p.name)

        print()
        print("=" * 120)
        print("HOÀN THÀNH DRY-RUN V9")
        print("=" * 120)
        print(f"students: {student_master_count}")
        print(f"student_enrollments: {enrollment_total}")
        print(f"Class conflicts: {len(class_conflicts)}")
        print(f"Generic UNIQUE conflicts: {len(real_conflicts)}")
        print(f"Expression UNIQUE cần xem: {len(expression_reviews)}")
        print(f"Staff duplicate: {len(staff_duplicate)}")
        print(f"Staff chưa phân loại: {len(staff_unclassified)}")
        print(f"No-year tables chưa có policy: {len(unknown_no_year_with_data)}")
        print(
            "SAFE_TO_BUILD_GENERIC_EXECUTOR: "
            + ("YES" if safe_generic_executor else "NO")
        )
        print(f"ZIP: {zip_path}")
        print("Database KHÔNG bị thay đổi.")

    finally:
        conn.close()


def main() -> None:
    try:
        audit()
    except AuditAbort as e:
        print()
        print("=" * 120)
        print("ĐÃ DỪNG DRY-RUN V9")
        print("=" * 120)
        print(str(e))
        print("Database KHÔNG bị thay đổi.")
        sys.exit(2)
    except sqlite3.Error as e:
        print()
        print("=" * 120)
        print("LỖI SQLITE TRONG V9")
        print("=" * 120)
        print(repr(e))
        print("Database KHÔNG bị thay đổi.")
        sys.exit(3)
    except Exception as e:
        print()
        print("=" * 120)
        print("LỖI KHÔNG DỰ KIẾN TRONG V9")
        print("=" * 120)
        print(repr(e))
        print("Database KHÔNG bị thay đổi.")
        sys.exit(4)


if __name__ == "__main__":
    main()
