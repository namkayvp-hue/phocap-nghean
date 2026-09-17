# -*- coding: utf-8 -*-
r"""
DRY-RUN V8 - DÒ CẤU TRÚC LỚP HỌC + HỌC SINH SAU SÁP NHẬP QĐ 3805 - NGHI LỘC
===============================================================================

MỤC TIÊU
--------
- CHỈ ĐỌC database hiện tại và backup trước sáp nhập.
- KHÔNG SỬA phocap.db.
- Xác định chính xác các bảng dùng cho:
    1) Lớp học
    2) Học sinh / hồ sơ học sinh theo năm
    3) Quan hệ học sinh - lớp nếu có bảng riêng
- Ghi ra:
    + schema
    + foreign key
    + unique index
    + số dòng 2025-2026 và 2026-2027 theo từng trường nguồn/đích
    + các khóa ổn định có thể dùng để chống trùng
- Tạo cổng READY_FOR_V8_1 để bước sau viết dry-run rollover/gộp thật sự.

NGUYÊN TẮC HỆ THỐNG
-------------------
Năm 2026-2027 của trường đích phải được hình thành từ:
    dữ liệu năm trước của chính trường đích
  + dữ liệu năm trước của các trường nguồn nhập vào
  - trùng
  - học sinh chuyển đi/nghỉ/hết thuộc phạm vi nếu trạng thái thể hiện rõ
  - dữ liệu đã có ở năm 2026-2027

Lịch sử năm cũ KHÔNG sửa.

CHẠY:
    cd C:\PhoCap
    .\.venv\Scripts\python.exe .\kiem_tra_schema_lop_hoc_hoc_sinh_sau_sap_nhap_QD3805_Nghi_Loc_v8.py

KẾT QUẢ:
    C:\PhoCap\dry_run_schema_lop_hoc_hoc_sinh_QD3805_Nghi_Loc_v8_<timestamp>.zip
"""

from __future__ import annotations

import csv
import sqlite3
import sys
import zipfile
from collections import defaultdict
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
ALL_MERGER_IDS = tuple(sorted(set(SOURCE_IDS) | set(TARGET_IDS)))


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


def all_tables(conn: sqlite3.Connection) -> list[str]:
    return [
        r[0]
        for r in conn.execute(
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
    return {c["name"] for c in columns(conn, table)}


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


def unique_indexes(conn: sqlite3.Connection, table: str) -> list[dict]:
    out = []
    for r in conn.execute(f"PRAGMA index_list({qident(table)})").fetchall():
        if int(r[2]) != 1:
            continue
        idx_name = r[1]
        cols_ = [
            x[2]
            for x in conn.execute(
                f"PRAGMA index_info({qident(idx_name)})"
            ).fetchall()
        ]
        out.append({
            "index_name": idx_name,
            "columns": ",".join(cols_),
        })
    return out


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


def detect_year_ids(conn: sqlite3.Connection) -> tuple[int, int, list[dict]]:
    if not table_exists(conn, "school_years"):
        raise AuditAbort("Không có bảng school_years.")

    cs = colset(conn, "school_years")
    label_col = next(
        (c for c in ("name", "label", "school_year", "year_name") if c in cs),
        None,
    )
    if not label_col:
        raise AuditAbort("Không xác định được cột tên năm học.")

    rows = conn.execute(
        f"SELECT id, {qident(label_col)} AS label "
        "FROM school_years ORDER BY id"
    ).fetchall()

    previous = target = None
    report = []
    for r in rows:
        rid = int(r["id"])
        label = str(r["label"] or "")
        report.append({"id": rid, "label": label})
        if "2025" in label and "2026" in label:
            previous = rid
        if "2026" in label and "2027" in label:
            target = rid

    if previous is None or target is None:
        raise AuditAbort(
            f"Không xác định đủ năm học: previous={previous}, target={target}"
        )
    return previous, target, report


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
        f"SELECT id, {qident(name_col)} FROM schools "
        f"WHERE id IN ({markers(len(ALL_MERGER_IDS))})",
        ALL_MERGER_IDS,
    ).fetchall()
    return {int(r[0]): str(r[1]) for r in rows}


def score_table(table: str, cs: set[str], fks: list[dict]) -> tuple[int, int, list[str]]:
    """
    Trả (class_score, student_score, reasons)
    """
    low = table.lower()
    class_score = 0
    student_score = 0
    reasons = []

    class_words = ("class", "classes", "lop", "classroom")
    student_words = ("student", "students", "hoc_sinh", "pupil", "learner", "enrollment")

    if any(w in low for w in class_words):
        class_score += 5
        reasons.append("Tên bảng gợi ý lớp học")
    if any(w in low for w in student_words):
        student_score += 5
        reasons.append("Tên bảng gợi ý học sinh")

    if "school_id" in cs:
        class_score += 2
        student_score += 2
        reasons.append("Có school_id")
    if "school_year_id" in cs:
        class_score += 3
        student_score += 3
        reasons.append("Có school_year_id")

    class_cols = {
        "class_name", "class_code", "grade", "grade_level",
        "class_type", "homeroom_teacher_id", "teacher_id",
        "student_count", "capacity"
    }
    student_cols = {
        "student_id", "student_member_id", "student_code",
        "full_name", "date_of_birth", "class_id",
        "enrollment_status", "status", "grade", "grade_level"
    }

    class_hits = sorted(class_cols & cs)
    student_hits = sorted(student_cols & cs)

    if class_hits:
        class_score += min(5, len(class_hits))
        reasons.append("Cột lớp: " + ",".join(class_hits))
    if student_hits:
        student_score += min(6, len(student_hits))
        reasons.append("Cột HS: " + ",".join(student_hits))

    for fk in fks:
        ref = fk["ref_table"].lower()
        if "class" in ref or "lop" in ref:
            student_score += 3
            reasons.append(
                f"FK tới bảng lớp: {fk['from_col']}->{fk['ref_table']}.{fk['to_col']}"
            )
        if "student" in ref or "hoc_sinh" in ref:
            student_score += 3
            reasons.append(
                f"FK tới bảng HS: {fk['from_col']}->{fk['ref_table']}.{fk['to_col']}"
            )

    return class_score, student_score, reasons


def count_by_school_year(
    conn: sqlite3.Connection,
    table: str,
    previous_year_id: int,
    target_year_id: int,
    names: dict[int, str],
) -> list[dict]:
    cs = colset(conn, table)
    if not {"school_id", "school_year_id"} <= cs:
        return []

    out = []
    for sid in ALL_MERGER_IDS:
        prev = conn.execute(
            f"SELECT COUNT(*) FROM {qident(table)} "
            "WHERE school_id=? AND school_year_id=?",
            (sid, previous_year_id),
        ).fetchone()[0]
        curr = conn.execute(
            f"SELECT COUNT(*) FROM {qident(table)} "
            "WHERE school_id=? AND school_year_id=?",
            (sid, target_year_id),
        ).fetchone()[0]

        if prev or curr:
            out.append({
                "table": table,
                "school_id": sid,
                "school_name": names.get(sid, ""),
                "role_in_merger": "SOURCE" if sid in SOURCE_IDS else "TARGET",
                "previous_year_rows": int(prev),
                "target_year_rows": int(curr),
            })
    return out


def detect_stable_keys(table: str, cs: set[str], uniq: list[dict]) -> list[str]:
    candidates = []
    preferred = (
        "student_id", "student_member_id", "person_id",
        "class_code", "class_name", "student_code",
        "school_year_id", "school_id", "class_id"
    )
    for c in preferred:
        if c in cs:
            candidates.append(c)

    for idx in uniq:
        if idx["columns"]:
            candidates.append("UNIQUE(" + idx["columns"] + ")")

    seen = []
    for x in candidates:
        if x not in seen:
            seen.append(x)
    return seen


def child_tables_of(conn: sqlite3.Connection, parent_table: str) -> list[dict]:
    out = []
    for table in all_tables(conn):
        for fk in foreign_keys(conn, table):
            if fk["ref_table"] == parent_table:
                out.append({
                    "child_table": table,
                    "from_col": fk["from_col"],
                    "parent_table": parent_table,
                    "to_col": fk["to_col"],
                })
    return out


def write_csv(path: Path, headers: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def audit() -> None:
    print("=" * 112)
    print("DRY-RUN V8 - DÒ CẤU TRÚC LỚP HỌC + HỌC SINH SAU SÁP NHẬP QĐ 3805 - NGHI LỘC")
    print("=" * 112)
    print("Chế độ: CHỈ ĐỌC - KHÔNG SỬA DATABASE")

    if not CURRENT_DB.exists():
        raise AuditAbort(f"Không tìm thấy current DB: {CURRENT_DB}")

    backup_db = find_backup()
    cur = connect_ro(CURRENT_DB)
    bak = connect_ro(backup_db)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = PROJECT_ROOT / (
        f"dry_run_schema_lop_hoc_hoc_sinh_QD3805_Nghi_Loc_v8_{ts}"
    )
    out_dir.mkdir(parents=True, exist_ok=False)

    try:
        int_cur = cur.execute("PRAGMA integrity_check").fetchone()[0]
        int_bak = bak.execute("PRAGMA integrity_check").fetchone()[0]
        if int_cur != "ok":
            raise AuditAbort(f"Current DB integrity_check={int_cur}")
        if int_bak != "ok":
            raise AuditAbort(f"Backup DB integrity_check={int_bak}")

        previous_year_id, target_year_id, years = detect_year_ids(cur)
        names_cur = school_names(cur)

        candidate_rows = []
        table_details = []
        all_counts = []
        all_children = []
        schema_rows = []
        fk_rows = []
        unique_rows = []

        for table in all_tables(cur):
            cs = colset(cur, table)
            fks = foreign_keys(cur, table)
            uniq = unique_indexes(cur, table)
            class_score, student_score, reasons = score_table(table, cs, fks)

            # Chỉ đưa vào candidate nếu có dấu hiệu rõ.
            if max(class_score, student_score) < 4:
                continue

            stable = detect_stable_keys(table, cs, uniq)
            candidate_rows.append({
                "table": table,
                "class_score": class_score,
                "student_score": student_score,
                "has_school_id": "YES" if "school_id" in cs else "NO",
                "has_school_year_id": "YES" if "school_year_id" in cs else "NO",
                "stable_key_candidates": " | ".join(stable),
                "reasons": " | ".join(reasons),
            })

            for c in columns(cur, table):
                schema_rows.append({
                    "table": table,
                    **c,
                })

            for fk in fks:
                fk_rows.append({
                    "table": table,
                    **fk,
                })

            for idx in uniq:
                unique_rows.append({
                    "table": table,
                    **idx,
                })

            counts = count_by_school_year(
                cur, table, previous_year_id, target_year_id, names_cur
            )
            all_counts.extend(counts)

            for child in child_tables_of(cur, table):
                all_children.append(child)

        candidate_rows.sort(
            key=lambda r: (
                -max(r["class_score"], r["student_score"]),
                r["table"]
            )
        )

        likely_class = [
            r for r in candidate_rows
            if r["class_score"] >= 6
            and r["class_score"] >= r["student_score"]
        ]
        likely_student = [
            r for r in candidate_rows
            if r["student_score"] >= 6
            and r["student_score"] > r["class_score"]
        ]

        # Chọn "ứng viên chính" chỉ khi score nổi bật duy nhất.
        top_class = None
        if likely_class:
            top_score = likely_class[0]["class_score"]
            tied = [x for x in likely_class if x["class_score"] == top_score]
            if len(tied) == 1:
                top_class = tied[0]["table"]

        top_student = None
        if likely_student:
            top_score = likely_student[0]["student_score"]
            tied = [x for x in likely_student if x["student_score"] == top_score]
            if len(tied) == 1:
                top_student = tied[0]["table"]

        gate = [
            {
                "check": "current_integrity_check",
                "result": "PASS" if int_cur == "ok" else "FAIL",
                "detail": str(int_cur),
            },
            {
                "check": "backup_integrity_check",
                "result": "PASS" if int_bak == "ok" else "FAIL",
                "detail": str(int_bak),
            },
            {
                "check": "previous_and_target_year_identified",
                "result": "PASS",
                "detail": (
                    f"previous={previous_year_id}; target={target_year_id}"
                ),
            },
            {
                "check": "likely_class_table_identified",
                "result": "PASS" if top_class else "REVIEW",
                "detail": top_class or f"candidates={len(likely_class)}",
            },
            {
                "check": "likely_student_table_identified",
                "result": "PASS" if top_student else "REVIEW",
                "detail": top_student or f"candidates={len(likely_student)}",
            },
        ]

        ready = (
            all(x["result"] == "PASS" for x in gate[:3])
            and top_class is not None
            and top_student is not None
        )

        write_csv(
            out_dir / "120_SCHOOL_YEARS.csv",
            ["id", "label"],
            years,
        )
        write_csv(
            out_dir / "121_CANDIDATE_TABLES_CLASS_STUDENT.csv",
            [
                "table", "class_score", "student_score",
                "has_school_id", "has_school_year_id",
                "stable_key_candidates", "reasons",
            ],
            candidate_rows,
        )
        write_csv(
            out_dir / "122_SCHEMA_CANDIDATE_TABLES.csv",
            [
                "table", "cid", "name", "type",
                "notnull", "default", "pk",
            ],
            schema_rows,
        )
        write_csv(
            out_dir / "123_FOREIGN_KEYS_CANDIDATE_TABLES.csv",
            [
                "table", "id", "seq", "ref_table",
                "from_col", "to_col", "on_update", "on_delete",
            ],
            fk_rows,
        )
        write_csv(
            out_dir / "124_UNIQUE_INDEXES_CANDIDATE_TABLES.csv",
            ["table", "index_name", "columns"],
            unique_rows,
        )
        write_csv(
            out_dir / "125_COUNTS_BY_SCHOOL_YEAR.csv",
            [
                "table", "school_id", "school_name",
                "role_in_merger",
                "previous_year_rows", "target_year_rows",
            ],
            all_counts,
        )
        write_csv(
            out_dir / "126_CHILD_TABLE_RELATIONS.csv",
            [
                "child_table", "from_col",
                "parent_table", "to_col",
            ],
            all_children,
        )
        write_csv(
            out_dir / "127_GATE_V8_1.csv",
            ["check", "result", "detail"],
            gate,
        )

        summary = out_dir / "00_TONG_QUAN_V8.txt"
        with summary.open("w", encoding="utf-8") as f:
            f.write(
                "DRY-RUN V8 - DÒ CẤU TRÚC LỚP HỌC + HỌC SINH SAU SÁP NHẬP QĐ 3805\n"
            )
            f.write("=" * 112 + "\n")
            f.write("CHẾ ĐỘ: CHỈ ĐỌC - KHÔNG SỬA DATABASE\n")
            f.write(f"Current DB: {CURRENT_DB}\n")
            f.write(f"Backup DB : {backup_db}\n")
            f.write(f"Năm trước: {previous_year_id}\n")
            f.write(f"Năm hiện hành: {target_year_id}\n\n")

            f.write("ỨNG VIÊN BẢNG LỚP\n")
            for r in likely_class[:10]:
                f.write(
                    f"- {r['table']}: class_score={r['class_score']}; "
                    f"student_score={r['student_score']}; "
                    f"{r['stable_key_candidates']}\n"
                )

            f.write("\nỨNG VIÊN BẢNG HỌC SINH\n")
            for r in likely_student[:10]:
                f.write(
                    f"- {r['table']}: student_score={r['student_score']}; "
                    f"class_score={r['class_score']}; "
                    f"{r['stable_key_candidates']}\n"
                )

            f.write("\nỨNG VIÊN CHÍNH\n")
            f.write(f"- Class table: {top_class or 'CẦN XEM THÊM'}\n")
            f.write(f"- Student table: {top_student or 'CẦN XEM THÊM'}\n")

            f.write("\nCỔNG V8.1\n")
            for g in gate:
                f.write(f"- [{g['result']}] {g['check']}: {g['detail']}\n")

            f.write("\nKẾT LUẬN\n")
            f.write(
                f"READY_FOR_V8_1 = {'YES' if ready else 'NO'}\n"
            )
            f.write(
                "- V8 chỉ dò schema và số lượng, chưa sửa database.\n"
            )

        zip_path = PROJECT_ROOT / (
            f"dry_run_schema_lop_hoc_hoc_sinh_QD3805_Nghi_Loc_v8_{ts}.zip"
        )
        with zipfile.ZipFile(
            zip_path, "w", compression=zipfile.ZIP_DEFLATED
        ) as zf:
            for p in sorted(out_dir.iterdir()):
                zf.write(p, arcname=p.name)

        print()
        print("=" * 112)
        print("HOÀN THÀNH DRY-RUN V8")
        print("=" * 112)
        print(f"Ứng viên class table chính: {top_class or 'CẦN XEM THÊM'}")
        print(f"Ứng viên student table chính: {top_student or 'CẦN XEM THÊM'}")
        print(f"READY_FOR_V8_1: {'YES' if ready else 'NO'}")
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
        print("=" * 112)
        print("ĐÃ DỪNG DRY-RUN V8")
        print("=" * 112)
        print(str(e))
        print("Database KHÔNG bị thay đổi.")
        sys.exit(2)
    except sqlite3.Error as e:
        print()
        print("=" * 112)
        print("LỖI SQLITE TRONG V8")
        print("=" * 112)
        print(repr(e))
        print("Database KHÔNG bị thay đổi.")
        sys.exit(3)
    except Exception as e:
        print()
        print("=" * 112)
        print("LỖI KHÔNG DỰ KIẾN TRONG V8")
        print("=" * 112)
        print(repr(e))
        print("Database KHÔNG bị thay đổi.")
        sys.exit(4)


if __name__ == "__main__":
    main()
