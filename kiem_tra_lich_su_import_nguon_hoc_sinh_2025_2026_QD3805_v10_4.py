# -*- coding: utf-8 -*-
r"""
DRY-RUN V10.4 - KIỂM TRA LỊCH SỬ IMPORT NGUỒN HỌC SINH 2025-2026
=================================================================

BỐI CẢNH
--------
V10.3A xác nhận:
- 2025-2026 = school_year_id 1 = nguồn chính thức để đối chiếu.
- 2026-2027 = school_year_id 2 = dữ liệu TEST.
- historical_people = 0
- students = 0
- student_enrollments = 0
- QĐ3805 không có dữ liệu baseline 2025-2026 trong các bảng lõi.

MỤC TIÊU
--------
Chỉ đọc database để xác định:
1. Có bảng metadata/import/dataset/batch/file nào chứa dấu vết nguồn 2025-2026 hay không.
2. Có dataset 2025-2026 đã tạo nhưng chưa nạp historical_people hay không.
3. Có đường dẫn/tên file import, trạng thái import, số dòng, lỗi import hay không.
4. Có dữ liệu lịch sử ở bảng khác nhưng V10.3A chưa nhận diện không.
5. Kết luận:
   - BASELINE_FILE_OR_DATASET_METADATA_FOUND = YES/NO
   - BASELINE_ROWS_ACTUALLY_LOADED = YES/NO
   - NEED_REIMPORT_2025_2026 = YES/NO

CHỈ ĐỌC:
- KHÔNG sửa database.
- KHÔNG sửa file.
- KHÔNG sửa mã nguồn.
"""

from __future__ import annotations

import csv
import json
import re
import sqlite3
import sys
import zipfile
from datetime import datetime
from pathlib import Path


ROOT = Path(r"C:\PhoCap")
DB_PATH = ROOT / "data" / "phocap.db"


class AuditAbort(RuntimeError):
    pass


def qident(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def connect_ro(path: Path) -> sqlite3.Connection:
    uri = path.resolve().as_uri() + "?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    con.row_factory = sqlite3.Row
    return con


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
    return {str(c["name"]) for c in columns(con, table)}


def scalar(con: sqlite3.Connection, sql: str, params=()) -> int:
    row = con.execute(sql, params).fetchone()
    return int(row[0] or 0) if row else 0


def write_csv(path: Path, headers: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def interesting_table(table: str, cs: set[str]) -> bool:
    low = table.lower()
    tokens = (
        "historical", "history", "dataset", "import",
        "batch", "upload", "source", "file",
        "student", "people", "person", "school_year"
    )
    if any(t in low for t in tokens):
        return True

    col_tokens = (
        "file_name", "filename", "file_path", "source_file",
        "source_path", "dataset_id", "import_batch_id",
        "school_year_id", "year_label", "status",
        "total_rows", "success_rows", "error_rows"
    )
    return any(c in cs for c in col_tokens)


def text_candidate_columns(cs: set[str]) -> list[str]:
    preferred = [
        "id", "name", "code", "label", "title",
        "school_year_id", "year", "school_year", "year_label",
        "dataset_id", "import_batch_id", "batch_id",
        "file_name", "filename", "original_filename",
        "file_path", "source_file", "source_path",
        "status", "status_code", "state",
        "total_rows", "row_count", "success_rows",
        "imported_rows", "error_rows", "failed_rows",
        "notes", "message", "error_message",
        "created_at", "updated_at"
    ]
    return [c for c in preferred if c in cs]


def row_mentions_2025_2026(row: sqlite3.Row) -> bool:
    text = " | ".join("" if v is None else str(v) for v in row)
    return bool(
        re.search(r"2025\D*2026", text, flags=re.I)
        or re.search(r"\b2025\b", text)
    )


def main() -> None:
    print("=" * 122)
    print("DRY-RUN V10.4 - KIỂM TRA LỊCH SỬ IMPORT NGUỒN HỌC SINH 2025-2026")
    print("=" * 122)
    print("Chế độ: CHỈ ĐỌC")

    if not DB_PATH.exists():
        raise AuditAbort(f"Không tìm thấy database: {DB_PATH}")

    con = connect_ro(DB_PATH)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = ROOT / f"dry_run_import_baseline_2025_2026_QD3805_v10_4_{ts}"
    out_dir.mkdir(parents=True, exist_ok=False)

    try:
        integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
        fk_errors = con.execute("PRAGMA foreign_key_check").fetchall()

        catalog = []
        samples_2025 = []
        all_interesting_samples = []

        for table in all_tables(con):
            cs = colset(con, table)
            if not interesting_table(table, cs):
                continue

            total = scalar(
                con, f"SELECT COUNT(*) FROM {qident(table)}"
            )

            sample_cols = text_candidate_columns(cs)
            catalog.append({
                "table": table,
                "total_rows": total,
                "columns": ",".join(sorted(cs)),
                "sample_columns": ",".join(sample_cols),
            })

            if total == 0 or not sample_cols:
                continue

            # Chỉ lấy tối đa 200 dòng/table để rà metadata/dấu vết import.
            sql = (
                "SELECT "
                + ",".join(qident(c) for c in sample_cols)
                + f" FROM {qident(table)} LIMIT 200"
            )
            rows = con.execute(sql).fetchall()

            for r in rows:
                d = {"table": table}
                for k in r.keys():
                    d[k] = "" if r[k] is None else r[k]

                all_interesting_samples.append(d)
                if row_mentions_2025_2026(r):
                    samples_2025.append(d)

        # Core load state.
        core_counts = []
        for table in (
            "historical_datasets",
            "historical_households",
            "historical_people",
            "students",
            "student_enrollments",
            "classes",
        ):
            exists = table in all_tables(con)
            total = (
                scalar(con, f"SELECT COUNT(*) FROM {qident(table)}")
                if exists else 0
            )
            core_counts.append({
                "table": table,
                "exists": "YES" if exists else "NO",
                "total_rows": total,
            })

        historical_people_rows = next(
            (r["total_rows"] for r in core_counts if r["table"] == "historical_people"),
            0,
        )
        students_rows = next(
            (r["total_rows"] for r in core_counts if r["table"] == "students"),
            0,
        )
        enroll_rows = next(
            (r["total_rows"] for r in core_counts if r["table"] == "student_enrollments"),
            0,
        )

        metadata_found = len(samples_2025) > 0
        actually_loaded = (
            int(historical_people_rows) > 0
            or int(students_rows) > 0
            or int(enroll_rows) > 0
        )
        need_reimport = not actually_loaded

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
                "check": "metadata_rows_mentioning_2025_2026",
                "result": "FOUND" if metadata_found else "NO_DATA",
                "detail": str(len(samples_2025)),
            },
            {
                "check": "historical_people_rows",
                "result": "INFO",
                "detail": str(historical_people_rows),
            },
            {
                "check": "students_rows",
                "result": "INFO",
                "detail": str(students_rows),
            },
            {
                "check": "student_enrollments_rows",
                "result": "INFO",
                "detail": str(enroll_rows),
            },
            {
                "check": "BASELINE_FILE_OR_DATASET_METADATA_FOUND",
                "result": "YES" if metadata_found else "NO",
                "detail": (
                    "Có dấu vết metadata/năm 2025-2026 trong database."
                    if metadata_found
                    else "Không thấy dấu vết metadata 2025-2026 trong database."
                ),
            },
            {
                "check": "BASELINE_ROWS_ACTUALLY_LOADED",
                "result": "YES" if actually_loaded else "NO",
                "detail": (
                    f"historical_people={historical_people_rows}; "
                    f"students={students_rows}; enrollments={enroll_rows}"
                ),
            },
            {
                "check": "NEED_REIMPORT_2025_2026",
                "result": "YES" if need_reimport else "REVIEW",
                "detail": (
                    "Nguồn 2025-2026 cần được nạp/import vào đúng cấu trúc dữ liệu."
                    if need_reimport
                    else "Đã có dữ liệu lõi; cần đối chiếu chi tiết trước khi import lại."
                ),
            },
        ]

        write_csv(
            out_dir / "460_IMPORT_DATASET_TABLE_CATALOG.csv",
            ["table", "total_rows", "columns", "sample_columns"],
            catalog,
        )

        sample_headers = sorted({
            k for r in samples_2025 for k in r.keys()
        }) or ["table"]
        write_csv(
            out_dir / "461_ROWS_MENTIONING_2025_2026.csv",
            sample_headers,
            samples_2025,
        )

        all_headers = sorted({
            k for r in all_interesting_samples for k in r.keys()
        }) or ["table"]
        write_csv(
            out_dir / "462_IMPORT_METADATA_SAMPLES.csv",
            all_headers,
            all_interesting_samples,
        )

        write_csv(
            out_dir / "463_CORE_LOAD_STATE.csv",
            ["table", "exists", "total_rows"],
            core_counts,
        )

        write_csv(
            out_dir / "464_GATE_V10_4.csv",
            ["check", "result", "detail"],
            gate_rows,
        )

        summary = out_dir / "00_TONG_QUAN_V10_4.txt"
        with summary.open("w", encoding="utf-8") as f:
            f.write(
                "DRY-RUN V10.4 - LỊCH SỬ IMPORT NGUỒN HỌC SINH 2025-2026\n"
            )
            f.write("=" * 122 + "\n")
            f.write("CHỈ ĐỌC - KHÔNG SỬA DATABASE\n\n")

            f.write(
                f"Metadata rows nhắc 2025-2026: {len(samples_2025)}\n"
            )
            f.write(
                f"historical_people: {historical_people_rows}\n"
            )
            f.write(
                f"students: {students_rows}\n"
            )
            f.write(
                f"student_enrollments: {enroll_rows}\n\n"
            )

            f.write(
                "BASELINE_FILE_OR_DATASET_METADATA_FOUND = "
                + ("YES" if metadata_found else "NO")
                + "\n"
            )
            f.write(
                "BASELINE_ROWS_ACTUALLY_LOADED = "
                + ("YES" if actually_loaded else "NO")
                + "\n"
            )
            f.write(
                "NEED_REIMPORT_2025_2026 = "
                + ("YES" if need_reimport else "REVIEW")
                + "\n"
            )

        zip_path = ROOT / (
            f"dry_run_import_baseline_2025_2026_QD3805_v10_4_{ts}.zip"
        )
        with zipfile.ZipFile(
            zip_path,
            "w",
            compression=zipfile.ZIP_DEFLATED,
        ) as zf:
            for p in sorted(out_dir.iterdir()):
                zf.write(p, arcname=p.name)

        print()
        print("=" * 122)
        print("HOÀN THÀNH DRY-RUN V10.4")
        print("=" * 122)
        print(f"Metadata rows nhắc 2025-2026: {len(samples_2025)}")
        print(f"historical_people: {historical_people_rows}")
        print(f"students: {students_rows}")
        print(f"student_enrollments: {enroll_rows}")
        print(
            "BASELINE_FILE_OR_DATASET_METADATA_FOUND: "
            + ("YES" if metadata_found else "NO")
        )
        print(
            "BASELINE_ROWS_ACTUALLY_LOADED: "
            + ("YES" if actually_loaded else "NO")
        )
        print(
            "NEED_REIMPORT_2025_2026: "
            + ("YES" if need_reimport else "REVIEW")
        )
        print(f"ZIP: {zip_path}")
        print("Database / JSON / mã nguồn: KHÔNG bị thay đổi.")

    finally:
        con.close()


if __name__ == "__main__":
    try:
        main()
    except AuditAbort as exc:
        print()
        print("=" * 122)
        print("ĐÃ DỪNG DRY-RUN V10.4")
        print("=" * 122)
        print(str(exc))
        print("Database / JSON / mã nguồn: KHÔNG bị thay đổi.")
        sys.exit(2)
    except sqlite3.Error as exc:
        print()
        print("=" * 122)
        print("LỖI SQLITE TRONG V10.4")
        print("=" * 122)
        print(repr(exc))
        print("Database / JSON / mã nguồn: KHÔNG bị thay đổi.")
        sys.exit(3)
    except Exception as exc:
        print()
        print("=" * 122)
        print("LỖI KHÔNG DỰ KIẾN TRONG V10.4")
        print("=" * 122)
        print(repr(exc))
        print("Database / JSON / mã nguồn: KHÔNG bị thay đổi.")
        sys.exit(4)
