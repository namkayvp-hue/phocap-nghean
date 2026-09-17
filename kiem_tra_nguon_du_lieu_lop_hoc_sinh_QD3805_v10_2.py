# -*- coding: utf-8 -*-
r"""
DRY-RUN V10.2 - TRUY NGUỒN DỮ LIỆU LỚP / HỌC SINH SAU SÁP NHẬP QĐ 3805
=========================================================================

MỤC TIÊU
--------
Sau V10/V10.1:
- Sáp nhập đã đúng.
- Đội ngũ tại 6 trường đích hiển thị đúng.
- Nhưng chỉ có 3 lớp và 0 student_enrollments năm 2026-2027.

V10.2 xác định:
1. Schema và tổng số row của:
   - classes
   - students
   - student_enrollments
2. Dữ liệu lớp/enrollment theo từng năm học tại:
   - 7 trường nguồn
   - 6 trường đích
   - toàn database
3. Có lớp/học sinh lịch sử ở các trường nguồn trước sáp nhập hay không.
4. Có bảng khác chứa dữ liệu lớp/học sinh thật nhưng không phải
   classes/student_enrollments hay không.
5. Có thể kết luận:
   A. Dữ liệu lớp/học sinh đã tồn tại nhưng chưa được chuyển;
   B. Dữ liệu chỉ có một phần;
   C. Hệ thống chưa có roster lớp/học sinh để chuyển.
6. Không tự chuyển survey -> students. Chỉ kiểm tra.

CHỈ ĐỌC:
- KHÔNG sửa database.
- KHÔNG sửa JSON.
- KHÔNG sửa mã nguồn.

CHẠY
----
    cd C:\PhoCap
    .\.venv\Scripts\python.exe .\kiem_tra_nguon_du_lieu_lop_hoc_sinh_QD3805_v10_2.py
"""

from __future__ import annotations

import csv
import json
import re
import sqlite3
import sys
import zipfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path


ROOT = Path(r"C:\PhoCap")
DB_PATH = ROOT / "data" / "phocap.db"
PLAN_FILE = ROOT / "data" / "school_merger_approved_plans.json"

CORE_TABLES = (
    "classes",
    "students",
    "student_enrollments",
)


class AuditAbort(RuntimeError):
    pass


def qident(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def connect_ro(path: Path) -> sqlite3.Connection:
    uri = path.resolve().as_uri() + "?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    con.row_factory = sqlite3.Row
    return con


def table_exists(con: sqlite3.Connection, table: str) -> bool:
    return con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone() is not None


def all_tables(con: sqlite3.Connection) -> list[str]:
    return [
        str(r[0])
        for r in con.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' "
            "ORDER BY name"
        ).fetchall()
    ]


def columns(con: sqlite3.Connection, table: str) -> list[dict]:
    return [
        {
            "cid": r[0],
            "name": r[1],
            "type": r[2],
            "notnull": r[3],
            "default": r[4],
            "pk": r[5],
        }
        for r in con.execute(
            f"PRAGMA table_info({qident(table)})"
        ).fetchall()
    ]


def colset(con: sqlite3.Connection, table: str) -> set[str]:
    return {str(x["name"]) for x in columns(con, table)}


def scalar(con: sqlite3.Connection, sql: str, params=()) -> int:
    row = con.execute(sql, params).fetchone()
    return int(row[0] or 0) if row else 0


def markers(n: int) -> str:
    return ",".join("?" for _ in range(n))


def write_csv(path: Path, headers: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def load_plans() -> list[dict]:
    if not PLAN_FILE.exists():
        raise AuditAbort(f"Không tìm thấy {PLAN_FILE}")

    payload = json.loads(PLAN_FILE.read_text(encoding="utf-8"))
    plans = []

    for raw in payload.get("plans") or []:
        if not isinstance(raw, dict):
            continue
        pid = str(raw.get("id") or "")
        doc = str(raw.get("document_code") or "")
        if not (pid.startswith("QD3805-") or "3805" in doc):
            continue

        item = dict(raw)
        item["school_year_id"] = int(item["school_year_id"])
        item["target_school_id"] = int(item["target_school_id"])
        item["source_school_ids"] = [
            int(x) for x in item.get("source_school_ids") or []
        ]
        plans.append(item)

    if len(plans) != 6:
        raise AuditAbort(f"QĐ3805 phải có 6 nhóm, hiện={len(plans)}")

    return plans


def school_map(con: sqlite3.Connection, ids: list[int]) -> dict[int, dict]:
    cs = colset(con, "schools")
    name_col = next(
        (c for c in ("name", "school_name", "ten_truong") if c in cs),
        None,
    )
    code_col = next(
        (c for c in ("code", "school_code", "ma_truong") if c in cs),
        None,
    )

    if not name_col:
        raise AuditAbort("Không xác định được tên trường.")

    select = [
        "id",
        f"{qident(name_col)} AS name",
        "is_active" if "is_active" in cs else "NULL AS is_active",
    ]
    select.append(
        f"{qident(code_col)} AS code" if code_col else "'' AS code"
    )

    rows = con.execute(
        "SELECT " + ",".join(select)
        + f" FROM schools WHERE id IN ({markers(len(ids))})",
        ids,
    ).fetchall()

    return {
        int(r["id"]): {
            "id": int(r["id"]),
            "name": str(r["name"] or ""),
            "code": str(r["code"] or ""),
            "is_active": r["is_active"],
        }
        for r in rows
    }


def year_map(con: sqlite3.Connection) -> dict[int, str]:
    if not table_exists(con, "school_years"):
        return {}

    cs = colset(con, "school_years")
    label_col = next(
        (c for c in ("name", "label", "school_year", "year_name") if c in cs),
        None,
    )
    if not label_col:
        return {}

    rows = con.execute(
        f"SELECT id,{qident(label_col)} AS label FROM school_years ORDER BY id"
    ).fetchall()
    return {
        int(r["id"]): str(r["label"] or "")
        for r in rows
    }


def table_schema_rows(con: sqlite3.Connection) -> list[dict]:
    rows = []
    for table in CORE_TABLES:
        if not table_exists(con, table):
            rows.append({
                "table": table,
                "exists": "NO",
                "cid": "",
                "column_name": "",
                "type": "",
                "notnull": "",
                "pk": "",
                "total_rows": 0,
            })
            continue

        total = scalar(
            con, f"SELECT COUNT(*) FROM {qident(table)}"
        )
        for c in columns(con, table):
            rows.append({
                "table": table,
                "exists": "YES",
                "cid": c["cid"],
                "column_name": c["name"],
                "type": c["type"],
                "notnull": c["notnull"],
                "pk": c["pk"],
                "total_rows": total,
            })
    return rows


def counts_by_year_school(
    con: sqlite3.Connection,
    table: str,
    school_ids: list[int],
    schools: dict[int, dict],
    years: dict[int, str],
    role: str,
) -> list[dict]:
    if not table_exists(con, table):
        return []

    cs = colset(con, table)
    if not {"school_id", "school_year_id"} <= cs:
        return []

    rows = con.execute(
        f"SELECT school_id,school_year_id,COUNT(*) AS n "
        f"FROM {qident(table)} "
        f"WHERE school_id IN ({markers(len(school_ids))}) "
        "GROUP BY school_id,school_year_id "
        "ORDER BY school_id,school_year_id",
        school_ids,
    ).fetchall()

    return [
        {
            "table": table,
            "school_role": role,
            "school_id": int(r["school_id"]),
            "school_name": schools.get(
                int(r["school_id"]), {}
            ).get("name", ""),
            "school_year_id": int(r["school_year_id"]),
            "school_year_label": years.get(
                int(r["school_year_id"]), ""
            ),
            "rows": int(r["n"]),
        }
        for r in rows
    ]


def database_counts_by_year(
    con: sqlite3.Connection,
    table: str,
    years: dict[int, str],
) -> list[dict]:
    if not table_exists(con, table):
        return []

    cs = colset(con, table)

    if "school_year_id" in cs:
        rows = con.execute(
            f"SELECT school_year_id,COUNT(*) AS n "
            f"FROM {qident(table)} "
            "GROUP BY school_year_id ORDER BY school_year_id"
        ).fetchall()
        return [
            {
                "table": table,
                "school_year_id": (
                    int(r["school_year_id"])
                    if r["school_year_id"] is not None else ""
                ),
                "school_year_label": years.get(
                    int(r["school_year_id"]), ""
                ) if r["school_year_id"] is not None else "",
                "rows": int(r["n"]),
            }
            for r in rows
        ]

    return [{
        "table": table,
        "school_year_id": "",
        "school_year_label": "NO_school_year_id",
        "rows": scalar(
            con, f"SELECT COUNT(*) FROM {qident(table)}"
        ),
    }]


def class_detail(
    con: sqlite3.Connection,
    school_ids: list[int],
    schools: dict[int, dict],
    years: dict[int, str],
) -> list[dict]:
    if not table_exists(con, "classes"):
        return []

    cs = colset(con, "classes")
    if "school_id" not in cs:
        return []

    wanted = ["id", "school_id", "school_year_id"]
    for c in (
        "name", "class_name", "code", "class_code",
        "grade", "grade_level", "level_code",
        "is_active", "status"
    ):
        if c in cs and c not in wanted:
            wanted.append(c)

    rows = con.execute(
        "SELECT " + ",".join(qident(c) for c in wanted)
        + f" FROM classes WHERE school_id IN ({markers(len(school_ids))}) "
        + (
            "ORDER BY school_id,school_year_id,id"
            if "school_year_id" in cs
            else "ORDER BY school_id,id"
        ),
        school_ids,
    ).fetchall()

    out = []
    for r in rows:
        d = {
            "school_id": int(r["school_id"]),
            "school_name": schools.get(
                int(r["school_id"]), {}
            ).get("name", ""),
            "school_year_id": (
                int(r["school_year_id"])
                if "school_year_id" in r.keys()
                and r["school_year_id"] is not None else ""
            ),
            "school_year_label": (
                years.get(int(r["school_year_id"]), "")
                if "school_year_id" in r.keys()
                and r["school_year_id"] is not None else ""
            ),
        }
        for k in r.keys():
            d[k] = "" if r[k] is None else r[k]
        out.append(d)
    return out


def related_table_catalog(con: sqlite3.Connection) -> list[dict]:
    """
    Tìm các bảng có khả năng chứa lớp/học sinh ngoài 3 bảng lõi.
    """
    result = []

    for table in all_tables(con):
        if table in CORE_TABLES:
            continue

        low = table.lower()
        if not any(
            token in low
            for token in (
                "student", "pupil", "learner",
                "class", "enroll", "roster",
                "hoc_sinh", "lop"
            )
        ):
            continue

        cs = colset(con, table)
        result.append({
            "table": table,
            "total_rows": scalar(
                con, f"SELECT COUNT(*) FROM {qident(table)}"
            ),
            "has_school_id": "YES" if "school_id" in cs else "NO",
            "has_school_year_id": (
                "YES" if "school_year_id" in cs else "NO"
            ),
            "columns": ",".join(sorted(cs)),
        })

    return result


def source_target_summary(
    con: sqlite3.Connection,
    plans: list[dict],
    schools: dict[int, dict],
    current_year_id: int,
) -> list[dict]:
    rows = []

    for p in plans:
        srcs = p["source_school_ids"]
        target = p["target_school_id"]

        for table in ("classes", "student_enrollments"):
            if not table_exists(con, table):
                rows.append({
                    "plan_id": p.get("id", ""),
                    "table": table,
                    "source_ids": ",".join(map(str, srcs)),
                    "target_id": target,
                    "target_name": schools[target]["name"],
                    "source_current": "",
                    "source_history": "",
                    "target_current": "",
                    "target_history": "",
                })
                continue

            cs = colset(con, table)
            if not {"school_id", "school_year_id"} <= cs:
                continue

            src_current = scalar(
                con,
                f"SELECT COUNT(*) FROM {qident(table)} "
                f"WHERE school_id IN ({markers(len(srcs))}) "
                "AND school_year_id=?",
                srcs + [current_year_id],
            )
            src_history = scalar(
                con,
                f"SELECT COUNT(*) FROM {qident(table)} "
                f"WHERE school_id IN ({markers(len(srcs))}) "
                "AND school_year_id<>?",
                srcs + [current_year_id],
            )
            tgt_current = scalar(
                con,
                f"SELECT COUNT(*) FROM {qident(table)} "
                "WHERE school_id=? AND school_year_id=?",
                (target, current_year_id),
            )
            tgt_history = scalar(
                con,
                f"SELECT COUNT(*) FROM {qident(table)} "
                "WHERE school_id=? AND school_year_id<>?",
                (target, current_year_id),
            )

            rows.append({
                "plan_id": p.get("id", ""),
                "table": table,
                "source_ids": ",".join(map(str, srcs)),
                "target_id": target,
                "target_name": schools[target]["name"],
                "source_current": src_current,
                "source_history": src_history,
                "target_current": tgt_current,
                "target_history": tgt_history,
            })

    return rows


def main() -> None:
    print("=" * 124)
    print("DRY-RUN V10.2 - TRUY NGUỒN DỮ LIỆU LỚP / HỌC SINH QĐ 3805")
    print("=" * 124)
    print("Chế độ: CHỈ ĐỌC")

    plans = load_plans()
    year_ids = {p["school_year_id"] for p in plans}
    if len(year_ids) != 1:
        raise AuditAbort("QĐ3805 không có một school_year_id duy nhất.")
    current_year_id = next(iter(year_ids))

    source_ids = sorted({
        sid for p in plans for sid in p["source_school_ids"]
    })
    target_ids = sorted({
        p["target_school_id"] for p in plans
    })
    all_ids = sorted(set(source_ids) | set(target_ids))

    con = connect_ro(DB_PATH)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = ROOT / f"dry_run_nguon_lop_hoc_sinh_QD3805_v10_2_{ts}"
    out_dir.mkdir(parents=True, exist_ok=False)

    try:
        integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
        fk_errors = con.execute("PRAGMA foreign_key_check").fetchall()

        years = year_map(con)
        schools = school_map(con, all_ids)

        schema_rows = table_schema_rows(con)

        source_year_rows = []
        target_year_rows = []
        db_year_rows = []

        for table in CORE_TABLES:
            source_year_rows.extend(
                counts_by_year_school(
                    con, table, source_ids,
                    schools, years, "SOURCE"
                )
            )
            target_year_rows.extend(
                counts_by_year_school(
                    con, table, target_ids,
                    schools, years, "TARGET"
                )
            )
            db_year_rows.extend(
                database_counts_by_year(
                    con, table, years
                )
            )

        classes_detail = class_detail(
            con, all_ids, schools, years
        )

        related_tables = related_table_catalog(con)

        by_plan = source_target_summary(
            con, plans, schools, current_year_id
        )

        # Core totals.
        total_classes_db = (
            scalar(con, "SELECT COUNT(*) FROM classes")
            if table_exists(con, "classes") else 0
        )
        total_students_db = (
            scalar(con, "SELECT COUNT(*) FROM students")
            if table_exists(con, "students") else 0
        )
        total_enroll_db = (
            scalar(con, "SELECT COUNT(*) FROM student_enrollments")
            if table_exists(con, "student_enrollments") else 0
        )

        qd_classes_all = 0
        qd_enroll_all = 0
        qd_classes_current_source = 0
        qd_classes_current_target = 0
        qd_enroll_current_source = 0
        qd_enroll_current_target = 0

        if table_exists(con, "classes"):
            cs = colset(con, "classes")
            if "school_id" in cs:
                qd_classes_all = scalar(
                    con,
                    f"SELECT COUNT(*) FROM classes "
                    f"WHERE school_id IN ({markers(len(all_ids))})",
                    all_ids,
                )
            if {"school_id", "school_year_id"} <= cs:
                qd_classes_current_source = scalar(
                    con,
                    f"SELECT COUNT(*) FROM classes "
                    f"WHERE school_id IN ({markers(len(source_ids))}) "
                    "AND school_year_id=?",
                    source_ids + [current_year_id],
                )
                qd_classes_current_target = scalar(
                    con,
                    f"SELECT COUNT(*) FROM classes "
                    f"WHERE school_id IN ({markers(len(target_ids))}) "
                    "AND school_year_id=?",
                    target_ids + [current_year_id],
                )

        if table_exists(con, "student_enrollments"):
            cs = colset(con, "student_enrollments")
            if "school_id" in cs:
                qd_enroll_all = scalar(
                    con,
                    f"SELECT COUNT(*) FROM student_enrollments "
                    f"WHERE school_id IN ({markers(len(all_ids))})",
                    all_ids,
                )
            if {"school_id", "school_year_id"} <= cs:
                qd_enroll_current_source = scalar(
                    con,
                    f"SELECT COUNT(*) FROM student_enrollments "
                    f"WHERE school_id IN ({markers(len(source_ids))}) "
                    "AND school_year_id=?",
                    source_ids + [current_year_id],
                )
                qd_enroll_current_target = scalar(
                    con,
                    f"SELECT COUNT(*) FROM student_enrollments "
                    f"WHERE school_id IN ({markers(len(target_ids))}) "
                    "AND school_year_id=?",
                    target_ids + [current_year_id],
                )

        # Determine evidence-based conclusion.
        if total_enroll_db == 0:
            roster_conclusion = (
                "C: student_enrollments toàn database = 0. "
                "Hệ thống hiện chưa có roster enrollment để sáp nhập."
            )
            safe_to_fix_migration = "NO"
        elif qd_enroll_current_source > 0:
            roster_conclusion = (
                "A: Còn student_enrollments năm hiện hành tại trường nguồn. "
                "Có dấu hiệu dữ liệu chưa chuyển."
            )
            safe_to_fix_migration = "REVIEW"
        elif qd_enroll_current_target == 0 and qd_enroll_all > 0:
            roster_conclusion = (
                "B: Có enrollment lịch sử/khác năm ở nhóm QĐ3805 nhưng "
                "không có enrollment năm hiện hành tại đích."
            )
            safe_to_fix_migration = "NO"
        elif qd_enroll_current_target > 0:
            roster_conclusion = (
                "D: Có student_enrollments năm hiện hành ở trường đích."
            )
            safe_to_fix_migration = "NO"
        else:
            roster_conclusion = (
                "C: Không có bằng chứng roster enrollment cần chuyển."
            )
            safe_to_fix_migration = "NO"

        if total_classes_db == 0:
            class_conclusion = (
                "classes toàn database = 0: chưa có dữ liệu lớp."
            )
        elif qd_classes_current_source > 0:
            class_conclusion = (
                "Còn lớp năm hiện hành ở nguồn: cần review migration."
            )
        elif qd_classes_current_target > 0:
            class_conclusion = (
                f"Có {qd_classes_current_target} lớp năm hiện hành tại đích; "
                "nguồn current = 0."
            )
        else:
            class_conclusion = (
                "Có bảng classes trong hệ thống nhưng không có lớp current "
                "ở nhóm QĐ3805."
            )

        gate_rows = [
            {
                "check": "integrity_check",
                "result": "PASS" if integrity == "ok" else "FAIL",
                "detail": str(integrity),
            },
            {
                "check": "foreign_key_check",
                "result": "PASS" if not fk_errors else "FAIL",
                "detail": str(len(fk_errors)),
            },
            {
                "check": "classes_total_database",
                "result": "INFO",
                "detail": str(total_classes_db),
            },
            {
                "check": "students_total_database",
                "result": "INFO",
                "detail": str(total_students_db),
            },
            {
                "check": "student_enrollments_total_database",
                "result": (
                    "GAP" if total_enroll_db == 0 else "INFO"
                ),
                "detail": str(total_enroll_db),
            },
            {
                "check": "qd3805_classes_current_source",
                "result": (
                    "PASS" if qd_classes_current_source == 0 else "REVIEW"
                ),
                "detail": str(qd_classes_current_source),
            },
            {
                "check": "qd3805_classes_current_target",
                "result": "INFO",
                "detail": str(qd_classes_current_target),
            },
            {
                "check": "qd3805_enrollments_current_source",
                "result": (
                    "PASS" if qd_enroll_current_source == 0 else "REVIEW"
                ),
                "detail": str(qd_enroll_current_source),
            },
            {
                "check": "qd3805_enrollments_current_target",
                "result": (
                    "GAP" if qd_enroll_current_target == 0 else "INFO"
                ),
                "detail": str(qd_enroll_current_target),
            },
            {
                "check": "migration_fix_needed_for_students",
                "result": safe_to_fix_migration,
                "detail": roster_conclusion,
            },
        ]

        write_csv(
            out_dir / "430_SCHEMA_CORE_CLASS_STUDENT.csv",
            [
                "table", "exists", "cid", "column_name",
                "type", "notnull", "pk", "total_rows",
            ],
            schema_rows,
        )
        write_csv(
            out_dir / "431_SOURCE_COUNTS_BY_YEAR.csv",
            [
                "table", "school_role", "school_id",
                "school_name", "school_year_id",
                "school_year_label", "rows",
            ],
            source_year_rows,
        )
        write_csv(
            out_dir / "432_TARGET_COUNTS_BY_YEAR.csv",
            [
                "table", "school_role", "school_id",
                "school_name", "school_year_id",
                "school_year_label", "rows",
            ],
            target_year_rows,
        )
        write_csv(
            out_dir / "433_DATABASE_COUNTS_BY_YEAR.csv",
            [
                "table", "school_year_id",
                "school_year_label", "rows",
            ],
            db_year_rows,
        )

        class_headers = set()
        for row in classes_detail:
            class_headers.update(row.keys())
        write_csv(
            out_dir / "434_CLASS_DETAIL_QD3805.csv",
            sorted(class_headers) if class_headers else [
                "school_id", "school_name"
            ],
            classes_detail,
        )

        write_csv(
            out_dir / "435_OTHER_CLASS_STUDENT_TABLES.csv",
            [
                "table", "total_rows",
                "has_school_id", "has_school_year_id",
                "columns",
            ],
            related_tables,
        )
        write_csv(
            out_dir / "436_SOURCE_TARGET_BY_PLAN.csv",
            [
                "plan_id", "table", "source_ids",
                "target_id", "target_name",
                "source_current", "source_history",
                "target_current", "target_history",
            ],
            by_plan,
        )
        write_csv(
            out_dir / "437_GATE_V10_2.csv",
            ["check", "result", "detail"],
            gate_rows,
        )

        summary = out_dir / "00_TONG_QUAN_V10_2.txt"
        with summary.open("w", encoding="utf-8") as f:
            f.write(
                "DRY-RUN V10.2 - TRUY NGUỒN DỮ LIỆU LỚP/HỌC SINH QĐ3805\n"
            )
            f.write("=" * 124 + "\n")
            f.write("CHỈ ĐỌC - KHÔNG SỬA DATABASE\n\n")

            f.write(f"Năm hiện hành: {current_year_id} - {years.get(current_year_id, '')}\n")
            f.write(f"classes toàn DB: {total_classes_db}\n")
            f.write(f"students toàn DB: {total_students_db}\n")
            f.write(f"student_enrollments toàn DB: {total_enroll_db}\n\n")

            f.write("NHÓM QĐ3805\n")
            f.write(f"- classes tất cả năm: {qd_classes_all}\n")
            f.write(f"- classes current tại nguồn: {qd_classes_current_source}\n")
            f.write(f"- classes current tại đích: {qd_classes_current_target}\n")
            f.write(f"- enrollments tất cả năm: {qd_enroll_all}\n")
            f.write(f"- enrollments current tại nguồn: {qd_enroll_current_source}\n")
            f.write(f"- enrollments current tại đích: {qd_enroll_current_target}\n\n")

            f.write("KẾT LUẬN LỚP\n")
            f.write("- " + class_conclusion + "\n\n")
            f.write("KẾT LUẬN HỌC SINH/ENROLLMENT\n")
            f.write("- " + roster_conclusion + "\n")
            f.write(
                "- Không tự chuyển dữ liệu điều tra thành students/enrollment.\n"
            )

            f.write("\nCỔNG\n")
            for g in gate_rows:
                f.write(
                    f"- [{g['result']}] {g['check']}: {g['detail']}\n"
                )

            f.write("\nNEXT_STEP\n")
            if total_enroll_db == 0:
                f.write(
                    "BUILD/IMPORT_STUDENT_ROSTER = YES\n"
                    "Không sửa migration; cần xây/nhập dữ liệu lớp-học sinh "
                    "chính thức cho năm hiện hành.\n"
                )
            else:
                f.write(
                    "BUILD/IMPORT_STUDENT_ROSTER = REVIEW\n"
                    "Xem các CSV chi tiết trước khi quyết định.\n"
                )

        zip_path = ROOT / (
            f"dry_run_nguon_lop_hoc_sinh_QD3805_v10_2_{ts}.zip"
        )
        with zipfile.ZipFile(
            zip_path, "w", compression=zipfile.ZIP_DEFLATED
        ) as zf:
            for p in sorted(out_dir.iterdir()):
                zf.write(p, arcname=p.name)

        print()
        print("=" * 124)
        print("HOÀN THÀNH DRY-RUN V10.2")
        print("=" * 124)
        print(f"classes toàn DB: {total_classes_db}")
        print(f"students toàn DB: {total_students_db}")
        print(f"student_enrollments toàn DB: {total_enroll_db}")
        print(f"QD3805 classes current nguồn: {qd_classes_current_source}")
        print(f"QD3805 classes current đích: {qd_classes_current_target}")
        print(f"QD3805 enrollments current nguồn: {qd_enroll_current_source}")
        print(f"QD3805 enrollments current đích: {qd_enroll_current_target}")
        print(f"Kết luận lớp: {class_conclusion}")
        print(f"Kết luận enrollment: {roster_conclusion}")
        print(f"ZIP: {zip_path}")
        print("Database / JSON / mã nguồn: KHÔNG bị thay đổi.")

    finally:
        con.close()


if __name__ == "__main__":
    try:
        main()
    except AuditAbort as exc:
        print()
        print("=" * 124)
        print("ĐÃ DỪNG DRY-RUN V10.2")
        print("=" * 124)
        print(str(exc))
        print("Database / JSON / mã nguồn: KHÔNG bị thay đổi.")
        sys.exit(2)
    except sqlite3.Error as exc:
        print()
        print("=" * 124)
        print("LỖI SQLITE TRONG V10.2")
        print("=" * 124)
        print(repr(exc))
        print("Database / JSON / mã nguồn: KHÔNG bị thay đổi.")
        sys.exit(3)
    except Exception as exc:
        print()
        print("=" * 124)
        print("LỖI KHÔNG DỰ KIẾN TRONG V10.2")
        print("=" * 124)
        print(repr(exc))
        print("Database / JSON / mã nguồn: KHÔNG bị thay đổi.")
        sys.exit(4)
