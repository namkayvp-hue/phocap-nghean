# -*- coding: utf-8 -*-
r"""
DRY-RUN V8.2 - TRUY TÌM NGUỒN LỚP HỌC + HỌC SINH TẠI TÀI KHOẢN NHÀ TRƯỜNG
QĐ 3805 - NGHI LỘC
============================================================================

MỤC TIÊU
--------
V8.1.1 đã xác định:
- classes
- students
- student_enrollments
- survey_person_year_records

Nhưng dữ liệu classes/student_enrollments của các trường sáp nhập còn rất ít.
V8.2 truy tìm dữ liệu thật đang nằm ở đâu, gồm:
- classes
- students
- student_enrollments
- survey_people
- survey_person_year_records
- historical_datasets
- historical_people

V8.2 CHỈ ĐỌC - KHÔNG SỬA DATABASE.

KẾT QUẢ CẦN BIẾT
----------------
1. Tổng số dòng toàn hệ thống ở từng bảng.
2. Phân bố classes và student_enrollments theo school/year.
3. Có bao nhiêu students đã được gắn enrollment.
4. Có bao nhiêu students được liên kết từ survey_people / historical_people.
5. Danh sách school_name_reported trong historical_people và
   survey_person_year_records có liên quan Nghi Lộc / Nghi Hoa / Nghi Trung /
   Nghi Diên / Nghi Vạn / Quán Hành.
6. Số học sinh có thể truy ngược về từng trường sáp nhập bằng tên báo cáo.
7. Cổng quyết định bước V8.3:
   - dùng student_enrollments hiện có;
   - hay phải khởi tạo enrollment từ dữ liệu lịch sử/điều tra.

CHẠY
----
    cd C:\PhoCap
    .\.venv\Scripts\python.exe .\truy_tim_nguon_lop_hoc_hoc_sinh_tai_khoan_truong_QD3805_Nghi_Loc_v8_2.py
"""

from __future__ import annotations

import csv
import re
import sqlite3
import sys
import unicodedata
import zipfile
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(r"C:\PhoCap")
CURRENT_DB = PROJECT_ROOT / "data" / "phocap.db"
BACKUP_DIR = PROJECT_ROOT / "backups"

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

KEY_TABLES = (
    "classes",
    "students",
    "student_enrollments",
    "survey_people",
    "survey_person_year_records",
    "historical_datasets",
    "historical_people",
)


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


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone() is not None


def colset(conn: sqlite3.Connection, table: str) -> set[str]:
    return {
        r[1]
        for r in conn.execute(
            f"PRAGMA table_info({qident(table)})"
        ).fetchall()
    }


def normalize(value) -> str:
    if value is None:
        return ""
    s = str(value).strip().lower()
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())


def find_backup() -> Path:
    candidates = sorted(
        BACKUP_DIR.glob("phocap_truoc_sap_nhap_QD3805_Nghi_Loc_*.db"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise AuditAbort(
            r"Không tìm thấy backup trước sáp nhập trong C:\PhoCap\backups."
        )
    return candidates[0]


def detect_year_ids(conn: sqlite3.Connection) -> tuple[int, int]:
    if not table_exists(conn, "school_years"):
        raise AuditAbort("Không có bảng school_years.")
    cs = colset(conn, "school_years")
    label_col = next(
        (c for c in ("name", "label", "school_year", "year_name") if c in cs),
        None,
    )
    if not label_col:
        raise AuditAbort("Không xác định cột tên năm học.")

    rows = conn.execute(
        f"SELECT id,{qident(label_col)} FROM school_years ORDER BY id"
    ).fetchall()
    prev = target = None
    for r in rows:
        label = str(r[1] or "")
        if "2025" in label and "2026" in label:
            prev = int(r[0])
        if "2026" in label and "2027" in label:
            target = int(r[0])
    if prev is None or target is None:
        raise AuditAbort(
            f"Không xác định đủ năm học prev={prev}, target={target}"
        )
    return prev, target


def get_school_names(conn: sqlite3.Connection) -> dict[int, str]:
    if not table_exists(conn, "schools"):
        return {}
    cs = colset(conn, "schools")
    name_col = next(
        (c for c in ("name", "school_name", "ten_truong") if c in cs),
        None,
    )
    if not name_col:
        return {}
    rows = conn.execute(
        f"SELECT id,{qident(name_col)} FROM schools "
        f"WHERE id IN ({markers(len(ALL_IDS))})",
        ALL_IDS,
    ).fetchall()
    return {int(r[0]): str(r[1]) for r in rows}


def write_csv(path: Path, headers: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def global_table_counts(cur: sqlite3.Connection, bak: sqlite3.Connection) -> list[dict]:
    out = []
    for table in KEY_TABLES:
        current_n = (
            cur.execute(f"SELECT COUNT(*) FROM {qident(table)}").fetchone()[0]
            if table_exists(cur, table) else None
        )
        backup_n = (
            bak.execute(f"SELECT COUNT(*) FROM {qident(table)}").fetchone()[0]
            if table_exists(bak, table) else None
        )
        out.append({
            "table": table,
            "current_rows": current_n,
            "backup_before_merger_rows": backup_n,
            "delta": (
                None
                if current_n is None or backup_n is None
                else int(current_n) - int(backup_n)
            ),
        })
    return out


def class_distribution(
    conn: sqlite3.Connection,
    label: str,
    names: dict[int, str],
) -> list[dict]:
    if not table_exists(conn, "classes"):
        return []
    rows = conn.execute(
        "SELECT school_year_id,school_id,COUNT(*) AS n,"
        "GROUP_CONCAT(name,' | ') AS class_names "
        "FROM classes "
        "GROUP BY school_year_id,school_id "
        "ORDER BY school_year_id,school_id"
    ).fetchall()
    return [{
        "db": label,
        "school_year_id": r["school_year_id"],
        "school_id": r["school_id"],
        "school_name": names.get(int(r["school_id"]), ""),
        "class_count": r["n"],
        "class_names": r["class_names"],
        "is_merger_school": "YES" if int(r["school_id"]) in ALL_IDS else "NO",
    } for r in rows]


def enrollment_distribution(
    conn: sqlite3.Connection,
    label: str,
    names: dict[int, str],
) -> list[dict]:
    if not table_exists(conn, "student_enrollments"):
        return []
    rows = conn.execute(
        "SELECT school_year_id,school_id,status,is_current,"
        "COUNT(*) AS n,COUNT(DISTINCT student_id) AS students "
        "FROM student_enrollments "
        "GROUP BY school_year_id,school_id,status,is_current "
        "ORDER BY school_year_id,school_id,status,is_current"
    ).fetchall()
    return [{
        "db": label,
        "school_year_id": r["school_year_id"],
        "school_id": r["school_id"],
        "school_name": names.get(int(r["school_id"]), ""),
        "status": r["status"],
        "is_current": r["is_current"],
        "row_count": r["n"],
        "distinct_students": r["students"],
        "is_merger_school": "YES" if int(r["school_id"]) in ALL_IDS else "NO",
    } for r in rows]


def link_summary(conn: sqlite3.Connection, label: str) -> list[dict]:
    out = []

    if table_exists(conn, "students"):
        total_students = conn.execute(
            "SELECT COUNT(*) FROM students"
        ).fetchone()[0]
        active_students = (
            conn.execute("SELECT COUNT(*) FROM students WHERE is_active=1").fetchone()[0]
            if "is_active" in colset(conn, "students") else None
        )
        out.append({
            "db": label,
            "metric": "students_total",
            "value": total_students,
        })
        out.append({
            "db": label,
            "metric": "students_active",
            "value": active_students,
        })

    if table_exists(conn, "student_enrollments"):
        out.extend([
            {
                "db": label,
                "metric": "student_enrollments_rows",
                "value": conn.execute(
                    "SELECT COUNT(*) FROM student_enrollments"
                ).fetchone()[0],
            },
            {
                "db": label,
                "metric": "students_linked_to_enrollment",
                "value": conn.execute(
                    "SELECT COUNT(DISTINCT student_id) FROM student_enrollments"
                ).fetchone()[0],
            },
        ])

    if table_exists(conn, "survey_people") and "student_id" in colset(conn, "survey_people"):
        out.extend([
            {
                "db": label,
                "metric": "survey_people_total",
                "value": conn.execute(
                    "SELECT COUNT(*) FROM survey_people"
                ).fetchone()[0],
            },
            {
                "db": label,
                "metric": "survey_people_linked_student",
                "value": conn.execute(
                    "SELECT COUNT(*) FROM survey_people WHERE student_id IS NOT NULL"
                ).fetchone()[0],
            },
            {
                "db": label,
                "metric": "distinct_students_linked_from_survey_people",
                "value": conn.execute(
                    "SELECT COUNT(DISTINCT student_id) "
                    "FROM survey_people WHERE student_id IS NOT NULL"
                ).fetchone()[0],
            },
        ])

    if table_exists(conn, "historical_people") and "linked_student_id" in colset(conn, "historical_people"):
        out.extend([
            {
                "db": label,
                "metric": "historical_people_total",
                "value": conn.execute(
                    "SELECT COUNT(*) FROM historical_people"
                ).fetchone()[0],
            },
            {
                "db": label,
                "metric": "historical_people_linked_student",
                "value": conn.execute(
                    "SELECT COUNT(*) FROM historical_people "
                    "WHERE linked_student_id IS NOT NULL"
                ).fetchone()[0],
            },
            {
                "db": label,
                "metric": "distinct_students_linked_from_historical_people",
                "value": conn.execute(
                    "SELECT COUNT(DISTINCT linked_student_id) "
                    "FROM historical_people WHERE linked_student_id IS NOT NULL"
                ).fetchone()[0],
            },
        ])

    return out


def reported_school_names_historical(
    conn: sqlite3.Connection,
    label: str,
) -> list[dict]:
    if not table_exists(conn, "historical_people"):
        return []
    cs = colset(conn, "historical_people")
    if "school_name_reported" not in cs:
        return []

    year_expr = ""
    join = ""
    group_prefix = ""
    if table_exists(conn, "historical_datasets"):
        join = (
            " LEFT JOIN historical_datasets d "
            "ON d.id=p.dataset_id "
        )
        year_expr = "d.school_year_id AS school_year_id,"
        group_prefix = "d.school_year_id,"

    rows = conn.execute(
        "SELECT "
        + year_expr
        + "p.school_name_reported AS school_name_reported,"
        "COUNT(*) AS n,"
        "COUNT(DISTINCT p.linked_student_id) AS linked_students,"
        "SUM(CASE WHEN p.linked_student_id IS NOT NULL THEN 1 ELSE 0 END) AS linked_rows "
        "FROM historical_people p "
        + join
        + "WHERE p.school_name_reported IS NOT NULL "
        "AND TRIM(p.school_name_reported)<>'' "
        "GROUP BY "
        + group_prefix
        + "p.school_name_reported "
        "ORDER BY n DESC"
    ).fetchall()

    out = []
    for r in rows:
        name = str(r["school_name_reported"])
        norm = normalize(name)
        relevant = any(
            token in norm
            for token in (
                "nghi hoa", "nghi trung", "nghi dien", "nghi van",
                "quan hanh", "tt quan hanh"
            )
        )
        out.append({
            "db": label,
            "school_year_id": r["school_year_id"] if "school_year_id" in r.keys() else "",
            "school_name_reported": name,
            "normalized_name": norm,
            "row_count": r["n"],
            "linked_student_rows": r["linked_rows"],
            "distinct_linked_students": r["linked_students"],
            "relevant_to_merger": "YES" if relevant else "NO",
        })
    return out


def reported_school_names_survey(
    conn: sqlite3.Connection,
    label: str,
) -> list[dict]:
    if not table_exists(conn, "survey_person_year_records"):
        return []
    cs = colset(conn, "survey_person_year_records")
    if "school_name_reported" not in cs:
        return []

    rows = conn.execute(
        "SELECT school_year_id,school_name_reported,school_id,"
        "COUNT(*) AS n,COUNT(DISTINCT survey_person_id) AS persons "
        "FROM survey_person_year_records "
        "WHERE school_name_reported IS NOT NULL "
        "AND TRIM(school_name_reported)<>'' "
        "GROUP BY school_year_id,school_name_reported,school_id "
        "ORDER BY n DESC"
    ).fetchall()

    out = []
    for r in rows:
        name = str(r["school_name_reported"])
        norm = normalize(name)
        relevant = (
            r["school_id"] in ALL_IDS
            if r["school_id"] is not None
            else any(
                token in norm
                for token in (
                    "nghi hoa", "nghi trung", "nghi dien", "nghi van",
                    "quan hanh", "tt quan hanh"
                )
            )
        )
        out.append({
            "db": label,
            "school_year_id": r["school_year_id"],
            "school_id": r["school_id"],
            "school_name_reported": name,
            "normalized_name": norm,
            "row_count": r["n"],
            "distinct_persons": r["persons"],
            "relevant_to_merger": "YES" if relevant else "NO",
        })
    return out


def historical_school_detail(
    conn: sqlite3.Connection,
    names: dict[int, str],
) -> list[dict]:
    """
    Chỉ lấy các tên trường lịch sử có từ khóa liên quan để ta map thủ công/an toàn.
    Không tự gán school_id.
    """
    rows = reported_school_names_historical(conn, "CURRENT")
    relevant = [r for r in rows if r["relevant_to_merger"] == "YES"]
    return relevant


def linked_student_overlap(conn: sqlite3.Connection, label: str) -> list[dict]:
    if not table_exists(conn, "students"):
        return []

    metrics = []

    def scalar(sql):
        return conn.execute(sql).fetchone()[0]

    metrics.append({
        "db": label,
        "metric": "students_without_any_enrollment",
        "value": scalar(
            "SELECT COUNT(*) FROM students s "
            "WHERE NOT EXISTS (SELECT 1 FROM student_enrollments e WHERE e.student_id=s.id)"
        ) if table_exists(conn, "student_enrollments") else scalar("SELECT COUNT(*) FROM students"),
    })

    if table_exists(conn, "historical_people"):
        metrics.append({
            "db": label,
            "metric": "students_linked_historical_but_no_enrollment",
            "value": scalar(
                "SELECT COUNT(DISTINCT h.linked_student_id) "
                "FROM historical_people h "
                "WHERE h.linked_student_id IS NOT NULL "
                "AND NOT EXISTS ("
                " SELECT 1 FROM student_enrollments e "
                " WHERE e.student_id=h.linked_student_id"
                ")"
            ) if table_exists(conn, "student_enrollments") else 0,
        })

    if table_exists(conn, "survey_people"):
        metrics.append({
            "db": label,
            "metric": "students_linked_survey_but_no_enrollment",
            "value": scalar(
                "SELECT COUNT(DISTINCT p.student_id) "
                "FROM survey_people p "
                "WHERE p.student_id IS NOT NULL "
                "AND NOT EXISTS ("
                " SELECT 1 FROM student_enrollments e "
                " WHERE e.student_id=p.student_id"
                ")"
            ) if table_exists(conn, "student_enrollments") else 0,
        })

    return metrics


def audit() -> None:
    print("=" * 116)
    print("DRY-RUN V8.2 - TRUY TÌM NGUỒN LỚP HỌC + HỌC SINH TẠI TÀI KHOẢN NHÀ TRƯỜNG")
    print("=" * 116)
    print("Chế độ: CHỈ ĐỌC - KHÔNG SỬA DATABASE")

    if not CURRENT_DB.exists():
        raise AuditAbort(f"Không tìm thấy current DB: {CURRENT_DB}")

    backup_db = find_backup()
    cur = connect_ro(CURRENT_DB)
    bak = connect_ro(backup_db)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = PROJECT_ROOT / (
        f"dry_run_truy_tim_nguon_lop_hoc_hoc_sinh_QD3805_Nghi_Loc_v8_2_{ts}"
    )
    out_dir.mkdir(parents=True, exist_ok=False)

    try:
        int_cur = cur.execute("PRAGMA integrity_check").fetchone()[0]
        int_bak = bak.execute("PRAGMA integrity_check").fetchone()[0]
        if int_cur != "ok":
            raise AuditAbort(f"Current integrity_check={int_cur}")
        if int_bak != "ok":
            raise AuditAbort(f"Backup integrity_check={int_bak}")

        previous_year_id, target_year_id = detect_year_ids(cur)
        names = get_school_names(cur)

        global_counts = global_table_counts(cur, bak)
        class_dist = (
            class_distribution(cur, "CURRENT", names)
            + class_distribution(bak, "BACKUP_BEFORE_MERGER", names)
        )
        enrollment_dist = (
            enrollment_distribution(cur, "CURRENT", names)
            + enrollment_distribution(bak, "BACKUP_BEFORE_MERGER", names)
        )
        links = (
            link_summary(cur, "CURRENT")
            + link_summary(bak, "BACKUP_BEFORE_MERGER")
        )
        overlaps = (
            linked_student_overlap(cur, "CURRENT")
            + linked_student_overlap(bak, "BACKUP_BEFORE_MERGER")
        )
        historical_names = (
            reported_school_names_historical(cur, "CURRENT")
            + reported_school_names_historical(bak, "BACKUP_BEFORE_MERGER")
        )
        survey_names = (
            reported_school_names_survey(cur, "CURRENT")
            + reported_school_names_survey(bak, "BACKUP_BEFORE_MERGER")
        )

        relevant_hist = [
            r for r in historical_names
            if r["relevant_to_merger"] == "YES"
        ]
        relevant_survey = [
            r for r in survey_names
            if r["relevant_to_merger"] == "YES"
        ]

        # Xác định có đủ roster school/year theo enrollment hay chưa.
        merger_enrollment_rows = [
            r for r in enrollment_dist
            if r["db"] == "CURRENT"
            and r["school_id"] in ALL_IDS
        ]
        merger_enrollment_total = sum(
            int(r["row_count"]) for r in merger_enrollment_rows
        )

        relevant_hist_total = sum(
            int(r["row_count"])
            for r in relevant_hist
            if r["db"] == "CURRENT"
        )
        relevant_survey_total = sum(
            int(r["row_count"])
            for r in relevant_survey
            if r["db"] == "CURRENT"
        )

        if merger_enrollment_total > 0:
            recommended_source = "STUDENT_ENROLLMENTS_PRESENT"
            next_action = (
                "Có enrollment của trường sáp nhập; V8.3 sẽ đối chiếu rollover/gộp trực tiếp."
            )
        elif relevant_hist_total > 0:
            recommended_source = "HISTORICAL_PEOPLE_REPORTED_SCHOOL"
            next_action = (
                "Không có enrollment của các trường sáp nhập nhưng có dữ liệu lịch sử theo "
                "school_name_reported; cần map tên trường + lớp trước khi khởi tạo enrollment."
            )
        elif relevant_survey_total > 0:
            recommended_source = "SURVEY_PERSON_YEAR_RECORDS"
            next_action = (
                "Không có enrollment/lịch sử trường rõ nhưng có dữ liệu điều tra theo trường; "
                "cần đối chiếu với students trước khi khởi tạo enrollment."
            )
        else:
            recommended_source = "NO_ROSTER_SOURCE_CONFIRMED"
            next_action = (
                "Chưa xác nhận được roster lớp/học sinh của các trường sáp nhập trong DB; "
                "không được tự sinh dữ liệu."
            )

        gate = [
            {
                "check": "current_integrity",
                "result": "PASS",
                "detail": int_cur,
            },
            {
                "check": "backup_integrity",
                "result": "PASS",
                "detail": int_bak,
            },
            {
                "check": "years",
                "result": "PASS",
                "detail": f"previous={previous_year_id}; target={target_year_id}",
            },
            {
                "check": "merger_enrollment_rows_found",
                "result": "PASS" if merger_enrollment_total > 0 else "NO_DATA",
                "detail": str(merger_enrollment_total),
            },
            {
                "check": "historical_reported_school_rows_relevant",
                "result": "PASS" if relevant_hist_total > 0 else "NO_DATA",
                "detail": str(relevant_hist_total),
            },
            {
                "check": "survey_reported_school_rows_relevant",
                "result": "PASS" if relevant_survey_total > 0 else "NO_DATA",
                "detail": str(relevant_survey_total),
            },
            {
                "check": "recommended_source",
                "result": "INFO",
                "detail": recommended_source,
            },
        ]

        write_csv(
            out_dir / "140_GLOBAL_TABLE_COUNTS.csv",
            ["table", "current_rows", "backup_before_merger_rows", "delta"],
            global_counts,
        )
        write_csv(
            out_dir / "141_CLASSES_DISTRIBUTION.csv",
            [
                "db", "school_year_id", "school_id", "school_name",
                "class_count", "class_names", "is_merger_school",
            ],
            class_dist,
        )
        write_csv(
            out_dir / "142_STUDENT_ENROLLMENTS_DISTRIBUTION.csv",
            [
                "db", "school_year_id", "school_id", "school_name",
                "status", "is_current", "row_count",
                "distinct_students", "is_merger_school",
            ],
            enrollment_dist,
        )
        write_csv(
            out_dir / "143_STUDENT_LINK_SUMMARY.csv",
            ["db", "metric", "value"],
            links,
        )
        write_csv(
            out_dir / "144_STUDENT_LINK_OVERLAP.csv",
            ["db", "metric", "value"],
            overlaps,
        )
        write_csv(
            out_dir / "145_HISTORICAL_REPORTED_SCHOOL_NAMES_ALL.csv",
            [
                "db", "school_year_id", "school_name_reported",
                "normalized_name", "row_count", "linked_student_rows",
                "distinct_linked_students", "relevant_to_merger",
            ],
            historical_names,
        )
        write_csv(
            out_dir / "146_HISTORICAL_REPORTED_SCHOOL_NAMES_RELEVANT.csv",
            [
                "db", "school_year_id", "school_name_reported",
                "normalized_name", "row_count", "linked_student_rows",
                "distinct_linked_students", "relevant_to_merger",
            ],
            relevant_hist,
        )
        write_csv(
            out_dir / "147_SURVEY_REPORTED_SCHOOL_NAMES_RELEVANT.csv",
            [
                "db", "school_year_id", "school_id",
                "school_name_reported", "normalized_name",
                "row_count", "distinct_persons", "relevant_to_merger",
            ],
            relevant_survey,
        )
        write_csv(
            out_dir / "148_GATE_V8_3.csv",
            ["check", "result", "detail"],
            gate,
        )

        summary = out_dir / "00_TONG_QUAN_V8_2.txt"
        with summary.open("w", encoding="utf-8") as f:
            f.write(
                "DRY-RUN V8.2 - TRUY TÌM NGUỒN LỚP HỌC + HỌC SINH\n"
            )
            f.write("=" * 116 + "\n")
            f.write("CHẾ ĐỘ: CHỈ ĐỌC - KHÔNG SỬA DATABASE\n")
            f.write(f"Current DB: {CURRENT_DB}\n")
            f.write(f"Backup DB : {backup_db}\n")
            f.write(f"Năm trước: {previous_year_id}\n")
            f.write(f"Năm hiện hành: {target_year_id}\n\n")

            f.write("TỔNG SỐ DÒNG BẢNG CHÍNH\n")
            for r in global_counts:
                f.write(
                    f"- {r['table']}: current={r['current_rows']}; "
                    f"backup={r['backup_before_merger_rows']}; delta={r['delta']}\n"
                )

            f.write("\nDỮ LIỆU CÁC TRƯỜNG SÁP NHẬP\n")
            f.write(
                f"- student_enrollments thuộc các school_id sáp nhập hiện tại: "
                f"{merger_enrollment_total}\n"
            )
            f.write(
                f"- historical_people có school_name_reported liên quan: "
                f"{relevant_hist_total}\n"
            )
            f.write(
                f"- survey_person_year_records có trường báo cáo liên quan: "
                f"{relevant_survey_total}\n"
            )

            f.write("\nKẾT LUẬN NGUỒN DỮ LIỆU\n")
            f.write(f"- RECOMMENDED_SOURCE = {recommended_source}\n")
            f.write(f"- NEXT_ACTION = {next_action}\n")

            f.write("\nLƯU Ý\n")
            f.write(
                "- V8.2 không tạo lớp, không tạo enrollment và không sửa học sinh.\n"
            )
            f.write(
                "- Chỉ sau khi xác định nguồn roster thật mới làm V8.3 tính/gộp dữ liệu.\n"
            )

        zip_path = PROJECT_ROOT / (
            f"dry_run_truy_tim_nguon_lop_hoc_hoc_sinh_QD3805_Nghi_Loc_v8_2_{ts}.zip"
        )
        with zipfile.ZipFile(
            zip_path, "w", compression=zipfile.ZIP_DEFLATED
        ) as zf:
            for p in sorted(out_dir.iterdir()):
                zf.write(p, arcname=p.name)

        print()
        print("=" * 116)
        print("HOÀN THÀNH DRY-RUN V8.2")
        print("=" * 116)
        print(f"student_enrollments của các trường sáp nhập: {merger_enrollment_total}")
        print(f"historical_people liên quan tên trường: {relevant_hist_total}")
        print(f"survey_person_year_records liên quan tên trường: {relevant_survey_total}")
        print(f"RECOMMENDED_SOURCE: {recommended_source}")
        print(f"NEXT_ACTION: {next_action}")
        print(f"ZIP: {zip_path}")
        print("Database KHÔNG bị thay đổi.")

    finally:
        cur.close()
        bak.close()


def main() -> None:
    try:
        audit()
    except AuditAbort as e:
        print()
        print("=" * 116)
        print("ĐÃ DỪNG DRY-RUN V8.2")
        print("=" * 116)
        print(str(e))
        print("Database KHÔNG bị thay đổi.")
        sys.exit(2)
    except sqlite3.Error as e:
        print()
        print("=" * 116)
        print("LỖI SQLITE TRONG V8.2")
        print("=" * 116)
        print(repr(e))
        print("Database KHÔNG bị thay đổi.")
        sys.exit(3)
    except Exception as e:
        print()
        print("=" * 116)
        print("LỖI KHÔNG DỰ KIẾN TRONG V8.2")
        print("=" * 116)
        print(repr(e))
        print("Database KHÔNG bị thay đổi.")
        sys.exit(4)


if __name__ == "__main__":
    main()
