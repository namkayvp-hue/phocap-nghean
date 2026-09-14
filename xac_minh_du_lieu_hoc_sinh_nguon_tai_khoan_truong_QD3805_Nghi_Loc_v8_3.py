# -*- coding: utf-8 -*-
r"""
DRY-RUN V8.3 - XÁC MINH DỮ LIỆU HỌC SINH NGUỒN TẠI TÀI KHOẢN NHÀ TRƯỜNG
QĐ 3805 - NGHI LỘC
=============================================================================

MỤC TIÊU
--------
V8.2 đã xác nhận:
- students = 0
- student_enrollments = 0
- historical_people = 0
- survey_people = 76
- survey_person_year_records = 76
- chỉ 2 bản ghi điều tra có thông tin trường liên quan MN Nghi Hoa.

V8.3:
1. Đọc schema thật của survey_people / survey_person_year_records / classes.
2. Liệt kê các cột liên quan trường, lớp, khối, trạng thái học tập.
3. Thống kê 76 đối tượng điều tra theo năm học, trường báo cáo, lớp/khối.
4. Tách riêng các bản ghi liên quan 15 trường trong kế hoạch sáp nhập.
5. Kiểm tra chi tiết classes của các trường nguồn/đích, so current với backup.
6. Phân biệt:
   - dữ liệu roster học sinh thật
   - dữ liệu điều tra hộ dân
   - lớp thử nghiệm / lớp chưa có enrollment
7. Đưa ra cổng:
   REAL_SCHOOL_STUDENT_ROSTER_AVAILABLE = YES/NO
   SAFE_TO_MERGE_STUDENTS_NOW = YES/NO
   SAFE_TO_BUILD_GENERIC_MERGER_LOGIC = YES/NO

V8.3 CHỈ ĐỌC - KHÔNG SỬA DATABASE.

CHẠY
----
    cd C:\PhoCap
    .\.venv\Scripts\python.exe .\xac_minh_du_lieu_hoc_sinh_nguon_tai_khoan_truong_QD3805_Nghi_Loc_v8_3.py
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

RELEVANT_NAME_TOKENS = (
    "nghi hoa",
    "nghi trung",
    "nghi dien",
    "nghi van",
    "quan hanh",
    "tt quan hanh",
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


def columns(conn: sqlite3.Connection, table: str) -> list[dict]:
    rows = conn.execute(f"PRAGMA table_info({qident(table)})").fetchall()
    return [
        {
            "cid": r[0],
            "name": r[1],
            "type": r[2],
            "notnull": r[3],
            "default": r[4],
            "pk": r[5],
        }
        for r in rows
    ]


def colset(conn: sqlite3.Connection, table: str) -> set[str]:
    return {x["name"] for x in columns(conn, table)}


def foreign_keys(conn: sqlite3.Connection, table: str) -> list[dict]:
    rows = conn.execute(f"PRAGMA foreign_key_list({qident(table)})").fetchall()
    return [
        {
            "id": r[0],
            "seq": r[1],
            "ref_table": r[2],
            "from_col": r[3],
            "to_col": r[4] or "id",
            "on_update": r[5],
            "on_delete": r[6],
        }
        for r in rows
    ]


def normalize(value) -> str:
    if value is None:
        return ""
    s = str(value).strip().lower()
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())


def is_relevant_school_name(value) -> bool:
    s = normalize(value)
    return any(token in s for token in RELEVANT_NAME_TOKENS)


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


def school_names(conn: sqlite3.Connection) -> dict[int, str]:
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


def schema_report(conn: sqlite3.Connection, table: str) -> list[dict]:
    if not table_exists(conn, table):
        return []
    return [{"table": table, **r} for r in columns(conn, table)]


def fk_report(conn: sqlite3.Connection, table: str) -> list[dict]:
    if not table_exists(conn, table):
        return []
    return [{"table": table, **r} for r in foreign_keys(conn, table)]


def likely_school_class_columns(conn: sqlite3.Connection, table: str) -> list[dict]:
    if not table_exists(conn, table):
        return []
    out = []
    keywords = (
        "school", "class", "grade", "level", "study", "education",
        "status", "lop", "truong", "khoi"
    )
    for c in columns(conn, table):
        low = c["name"].lower()
        if any(k in low for k in keywords):
            out.append({
                "table": table,
                "column": c["name"],
                "type": c["type"],
            })
    return out


def survey_year_distribution(conn: sqlite3.Connection) -> list[dict]:
    if not table_exists(conn, "survey_person_year_records"):
        return []
    cs = colset(conn, "survey_person_year_records")

    select_cols = ["school_year_id"]
    group_cols = ["school_year_id"]

    for c in (
        "school_id",
        "school_name_reported",
        "class_name_reported",
        "grade_reported",
        "grade_level",
        "education_level",
        "study_status",
        "status",
    ):
        if c in cs:
            select_cols.append(c)
            group_cols.append(c)

    sql = (
        "SELECT "
        + ", ".join(qident(c) for c in select_cols)
        + ", COUNT(*) AS n "
        "FROM survey_person_year_records "
        "GROUP BY "
        + ", ".join(qident(c) for c in group_cols)
        + " ORDER BY n DESC"
    )

    rows = conn.execute(sql).fetchall()
    out = []
    for r in rows:
        d = {c: r[c] for c in select_cols}
        d["row_count"] = r["n"]
        d["relevant_to_merger"] = "NO"

        sid = d.get("school_id")
        reported = d.get("school_name_reported")
        if sid in ALL_IDS or is_relevant_school_name(reported):
            d["relevant_to_merger"] = "YES"

        out.append(d)
    return out


def survey_relevant_detail(conn: sqlite3.Connection) -> list[dict]:
    if not table_exists(conn, "survey_person_year_records"):
        return []

    ycs = colset(conn, "survey_person_year_records")
    pcs = colset(conn, "survey_people") if table_exists(conn, "survey_people") else set()

    rows = conn.execute(
        "SELECT * FROM survey_person_year_records ORDER BY id"
    ).fetchall()

    out = []
    for y in rows:
        sid = y["school_id"] if "school_id" in ycs else None
        reported = y["school_name_reported"] if "school_name_reported" in ycs else None

        if sid not in ALL_IDS and not is_relevant_school_name(reported):
            continue

        d = {
            "year_record_id": y["id"] if "id" in ycs else "",
            "survey_person_id": y["survey_person_id"] if "survey_person_id" in ycs else "",
            "school_year_id": y["school_year_id"] if "school_year_id" in ycs else "",
            "school_id": sid,
            "school_name_reported": reported,
        }

        # Các cột nghiệp vụ quan trọng, nếu có.
        for c in (
            "class_name_reported", "grade_reported", "grade_level",
            "education_level", "study_status", "status",
            "current_class", "current_grade", "school_level",
            "is_studying", "notes"
        ):
            if c in ycs:
                d[c] = y[c]

        # Thêm thông tin đối tượng nhưng không cố định schema.
        person_id = d.get("survey_person_id")
        if person_id not in (None, "") and pcs:
            p = conn.execute(
                "SELECT * FROM survey_people WHERE id=?",
                (person_id,),
            ).fetchone()
            if p:
                for c in (
                    "full_name", "date_of_birth", "birth_year",
                    "gender", "student_id", "household_id"
                ):
                    if c in pcs:
                        d["person_" + c] = p[c]

        out.append(d)

    return out


def class_detail(
    conn: sqlite3.Connection,
    db_label: str,
    names: dict[int, str],
) -> list[dict]:
    if not table_exists(conn, "classes"):
        return []

    cs = colset(conn, "classes")
    rows = conn.execute(
        f"SELECT * FROM classes "
        f"WHERE school_id IN ({markers(len(ALL_IDS))}) "
        "ORDER BY school_year_id,school_id,id",
        ALL_IDS,
    ).fetchall()

    out = []
    for r in rows:
        d = {
            "db": db_label,
            "class_id": r["id"] if "id" in cs else "",
            "school_year_id": r["school_year_id"] if "school_year_id" in cs else "",
            "school_id": r["school_id"] if "school_id" in cs else "",
            "school_name": names.get(int(r["school_id"]), "") if r["school_id"] is not None else "",
            "class_name": r["name"] if "name" in cs else (
                r["class_name"] if "class_name" in cs else ""
            ),
        }

        for c in (
            "code", "class_code", "grade", "grade_level",
            "is_active", "created_at", "updated_at"
        ):
            if c in cs:
                d[c] = r[c]

        out.append(d)
    return out


def compare_classes(current_rows: list[dict], backup_rows: list[dict]) -> list[dict]:
    def key(r):
        return (
            r.get("class_id"),
            r.get("school_year_id"),
            r.get("class_name"),
        )

    bak_by_id = {r["class_id"]: r for r in backup_rows if r.get("class_id") not in (None, "")}
    cur_by_id = {r["class_id"]: r for r in current_rows if r.get("class_id") not in (None, "")}

    ids = sorted(set(bak_by_id) | set(cur_by_id))
    out = []
    for cid in ids:
        b = bak_by_id.get(cid)
        c = cur_by_id.get(cid)
        if b and c:
            moved = (
                b.get("school_id") != c.get("school_id")
                or b.get("school_year_id") != c.get("school_year_id")
            )
            status = "CHANGED" if moved else "UNCHANGED"
        elif b and not c:
            status = "MISSING_CURRENT"
        else:
            status = "NEW_CURRENT"

        out.append({
            "class_id": cid,
            "status": status,
            "backup_school_year_id": b.get("school_year_id") if b else "",
            "backup_school_id": b.get("school_id") if b else "",
            "backup_school_name": b.get("school_name") if b else "",
            "backup_class_name": b.get("class_name") if b else "",
            "current_school_year_id": c.get("school_year_id") if c else "",
            "current_school_id": c.get("school_id") if c else "",
            "current_school_name": c.get("school_name") if c else "",
            "current_class_name": c.get("class_name") if c else "",
        })
    return out


def all_table_counts(conn: sqlite3.Connection) -> dict[str, int]:
    out = {}
    for t in (
        "classes",
        "students",
        "student_enrollments",
        "survey_people",
        "survey_person_year_records",
        "historical_people",
        "historical_datasets",
    ):
        if table_exists(conn, t):
            out[t] = int(conn.execute(
                f"SELECT COUNT(*) FROM {qident(t)}"
            ).fetchone()[0])
        else:
            out[t] = -1
    return out


def audit() -> None:
    print("=" * 118)
    print("DRY-RUN V8.3 - XÁC MINH DỮ LIỆU HỌC SINH NGUỒN TẠI TÀI KHOẢN NHÀ TRƯỜNG")
    print("=" * 118)
    print("Chế độ: CHỈ ĐỌC - KHÔNG SỬA DATABASE")

    if not CURRENT_DB.exists():
        raise AuditAbort(f"Không tìm thấy current DB: {CURRENT_DB}")

    backup_path = find_backup()
    cur = connect_ro(CURRENT_DB)
    bak = connect_ro(backup_path)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = PROJECT_ROOT / (
        f"dry_run_xac_minh_du_lieu_hoc_sinh_QD3805_Nghi_Loc_v8_3_{ts}"
    )
    out_dir.mkdir(parents=True, exist_ok=False)

    try:
        int_cur = cur.execute("PRAGMA integrity_check").fetchone()[0]
        int_bak = bak.execute("PRAGMA integrity_check").fetchone()[0]
        if int_cur != "ok":
            raise AuditAbort(f"Current integrity_check={int_cur}")
        if int_bak != "ok":
            raise AuditAbort(f"Backup integrity_check={int_bak}")

        names_cur = school_names(cur)
        names_bak = school_names(bak)

        current_counts = all_table_counts(cur)
        backup_counts = all_table_counts(bak)

        schema_rows = []
        fk_rows = []
        likely_cols = []

        for t in (
            "classes",
            "students",
            "student_enrollments",
            "survey_people",
            "survey_person_year_records",
        ):
            schema_rows.extend(schema_report(cur, t))
            fk_rows.extend(fk_report(cur, t))
            likely_cols.extend(likely_school_class_columns(cur, t))

        survey_dist = survey_year_distribution(cur)
        survey_relevant = survey_relevant_detail(cur)

        class_cur = class_detail(cur, "CURRENT", names_cur)
        class_bak = class_detail(bak, "BACKUP_BEFORE_MERGER", names_bak)
        class_compare = compare_classes(class_cur, class_bak)

        student_count = current_counts.get("students", 0)
        enrollment_count = current_counts.get("student_enrollments", 0)

        # Roster thật của nhà trường chỉ được xem là tồn tại khi có students + enrollment.
        real_roster = student_count > 0 and enrollment_count > 0

        # Dữ liệu điều tra có thể giúp tham chiếu trường/lớp nhưng không tự coi là roster.
        survey_relevant_n = len(survey_relevant)

        # Có thể xây logic generic bất kể dữ liệu thực tế hiện tại.
        generic_logic_safe = (
            table_exists(cur, "classes")
            and table_exists(cur, "students")
            and table_exists(cur, "student_enrollments")
            and int_cur == "ok"
        )

        safe_merge_now = real_roster

        gates = [
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
                "check": "students_rows",
                "result": "PASS" if student_count > 0 else "NO_DATA",
                "detail": str(student_count),
            },
            {
                "check": "student_enrollments_rows",
                "result": "PASS" if enrollment_count > 0 else "NO_DATA",
                "detail": str(enrollment_count),
            },
            {
                "check": "survey_records_relevant_to_merger",
                "result": "INFO",
                "detail": str(survey_relevant_n),
            },
            {
                "check": "real_school_student_roster_available",
                "result": "YES" if real_roster else "NO",
                "detail": (
                    "Cần students>0 và student_enrollments>0 để coi là roster học sinh Nhà trường."
                ),
            },
            {
                "check": "safe_to_merge_students_now",
                "result": "YES" if safe_merge_now else "NO",
                "detail": (
                    "Không tự tạo học sinh từ dữ liệu điều tra hộ dân."
                    if not safe_merge_now else
                    "Có roster học sinh thật để dry-run sáp nhập."
                ),
            },
            {
                "check": "safe_to_build_generic_merger_logic",
                "result": "YES" if generic_logic_safe else "NO",
                "detail": (
                    "Schema classes/students/student_enrollments đã tồn tại."
                ),
            },
        ]

        write_csv(
            out_dir / "150_SCHEMA_CLASS_STUDENT_SURVEY.csv",
            [
                "table", "cid", "name", "type",
                "notnull", "default", "pk",
            ],
            schema_rows,
        )
        write_csv(
            out_dir / "151_FOREIGN_KEYS_CLASS_STUDENT_SURVEY.csv",
            [
                "table", "id", "seq", "ref_table",
                "from_col", "to_col", "on_update", "on_delete",
            ],
            fk_rows,
        )
        write_csv(
            out_dir / "152_COT_TRUONG_LOP_TRANG_THAI.csv",
            ["table", "column", "type"],
            likely_cols,
        )
        write_csv(
            out_dir / "153_SURVEY_YEAR_SCHOOL_CLASS_DISTRIBUTION.csv",
            list(survey_dist[0].keys()) if survey_dist else ["school_year_id", "row_count"],
            survey_dist,
        )
        # union headers cho chi tiết survey
        survey_headers = set()
        for r in survey_relevant:
            survey_headers.update(r.keys())
        write_csv(
            out_dir / "154_SURVEY_RELEVANT_DETAIL.csv",
            sorted(survey_headers) if survey_headers else [
                "year_record_id", "survey_person_id", "school_year_id",
                "school_id", "school_name_reported"
            ],
            survey_relevant,
        )
        class_headers = [
            "db", "class_id", "school_year_id", "school_id",
            "school_name", "class_name", "code", "class_code",
            "grade", "grade_level", "is_active",
            "created_at", "updated_at",
        ]
        write_csv(
            out_dir / "155_CLASSES_CURRENT_AND_BACKUP.csv",
            class_headers,
            class_cur + class_bak,
        )
        write_csv(
            out_dir / "156_CLASS_COMPARE_BEFORE_AFTER_MERGER.csv",
            [
                "class_id", "status",
                "backup_school_year_id", "backup_school_id",
                "backup_school_name", "backup_class_name",
                "current_school_year_id", "current_school_id",
                "current_school_name", "current_class_name",
            ],
            class_compare,
        )
        write_csv(
            out_dir / "157_GATE_STUDENT_MERGER.csv",
            ["check", "result", "detail"],
            gates,
        )

        summary = out_dir / "00_TONG_QUAN_V8_3.txt"
        with summary.open("w", encoding="utf-8") as f:
            f.write(
                "DRY-RUN V8.3 - XÁC MINH DỮ LIỆU HỌC SINH NGUỒN\n"
            )
            f.write("=" * 118 + "\n")
            f.write("CHẾ ĐỘ: CHỈ ĐỌC - KHÔNG SỬA DATABASE\n")
            f.write(f"Current DB: {CURRENT_DB}\n")
            f.write(f"Backup DB : {backup_path}\n\n")

            f.write("TỔNG SỐ DÒNG CURRENT\n")
            for t, n in current_counts.items():
                f.write(f"- {t}: {n}\n")

            f.write("\nTỔNG SỐ DÒNG BACKUP TRƯỚC SÁP NHẬP\n")
            for t, n in backup_counts.items():
                f.write(f"- {t}: {n}\n")

            f.write("\nDỮ LIỆU LIÊN QUAN SÁP NHẬP\n")
            f.write(f"- survey relevant records: {survey_relevant_n}\n")
            f.write(
                f"- classes current thuộc 15 trường nguồn/đích: {len(class_cur)}\n"
            )
            f.write(
                f"- classes backup thuộc 15 trường nguồn/đích: {len(class_bak)}\n"
            )
            f.write(
                f"- classes thay đổi school/year sau sáp nhập: "
                f"{sum(r['status']=='CHANGED' for r in class_compare)}\n"
            )

            f.write("\nKẾT LUẬN\n")
            f.write(
                f"REAL_SCHOOL_STUDENT_ROSTER_AVAILABLE = "
                f"{'YES' if real_roster else 'NO'}\n"
            )
            f.write(
                f"SAFE_TO_MERGE_STUDENTS_NOW = "
                f"{'YES' if safe_merge_now else 'NO'}\n"
            )
            f.write(
                f"SAFE_TO_BUILD_GENERIC_MERGER_LOGIC = "
                f"{'YES' if generic_logic_safe else 'NO'}\n"
            )

            if not real_roster:
                f.write(
                    "- Không có students/student_enrollments nên chưa có roster học sinh "
                    "Nhà trường để sáp nhập thực tế.\n"
                )
                f.write(
                    "- survey_person_year_records là dữ liệu điều tra, không được tự động "
                    "biến thành danh sách học sinh Nhà trường nếu chưa qua đối chiếu/import.\n"
                )

            f.write(
                "- Có thể tiếp tục xây cơ chế sáp nhập dùng chung cho classes/students/"
                "student_enrollments để hệ thống tự xử lý khi dữ liệu thật được nhập.\n"
            )

        zip_path = PROJECT_ROOT / (
            f"dry_run_xac_minh_du_lieu_hoc_sinh_QD3805_Nghi_Loc_v8_3_{ts}.zip"
        )
        with zipfile.ZipFile(
            zip_path, "w", compression=zipfile.ZIP_DEFLATED
        ) as zf:
            for p in sorted(out_dir.iterdir()):
                zf.write(p, arcname=p.name)

        print()
        print("=" * 118)
        print("HOÀN THÀNH DRY-RUN V8.3")
        print("=" * 118)
        print(f"students: {student_count}")
        print(f"student_enrollments: {enrollment_count}")
        print(f"survey records liên quan sáp nhập: {survey_relevant_n}")
        print(
            "REAL_SCHOOL_STUDENT_ROSTER_AVAILABLE: "
            + ("YES" if real_roster else "NO")
        )
        print(
            "SAFE_TO_MERGE_STUDENTS_NOW: "
            + ("YES" if safe_merge_now else "NO")
        )
        print(
            "SAFE_TO_BUILD_GENERIC_MERGER_LOGIC: "
            + ("YES" if generic_logic_safe else "NO")
        )
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
        print("=" * 118)
        print("ĐÃ DỪNG DRY-RUN V8.3")
        print("=" * 118)
        print(str(e))
        print("Database KHÔNG bị thay đổi.")
        sys.exit(2)
    except sqlite3.Error as e:
        print()
        print("=" * 118)
        print("LỖI SQLITE TRONG V8.3")
        print("=" * 118)
        print(repr(e))
        print("Database KHÔNG bị thay đổi.")
        sys.exit(3)
    except Exception as e:
        print()
        print("=" * 118)
        print("LỖI KHÔNG DỰ KIẾN TRONG V8.3")
        print("=" * 118)
        print(repr(e))
        print("Database KHÔNG bị thay đổi.")
        sys.exit(4)


if __name__ == "__main__":
    main()
