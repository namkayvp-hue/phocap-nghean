# -*- coding: utf-8 -*-
r"""
DRY-RUN V10.9 - KIỂM TRA SCHEMA TRƯỚC KHI NẠP BASELINE HS 2025-2026 QĐ3805
=============================================================================

MỤC TIÊU
--------
V10.8.1 đã xác nhận nguồn sạch:
- 7.781 dòng
- 7.777 mã học sinh duy nhất
- 4 mã có nhiều enrollment do chuyển trường
- baseline 2025-2026 trong DB hiện = 0
- route đối chiếu hiện đang dùng năm của đợt điều tra 2026-2027

V10.9 kiểm tra CHỈ ĐỌC:
1. Schema chính xác của:
   - students
   - classes
   - student_enrollments
   - school_years
   - schools
2. NOT NULL / DEFAULT / PK / FK.
3. UNIQUE indexes, đặc biệt:
   - student_enrollments có cho phép 1 student có nhiều enrollment cùng năm không?
4. Các cột trạng thái/chuyển trường có sẵn trong enrollment không.
5. Trích các đoạn mã nguồn liên quan StudentEnrollment trong
   app\routers\student_survey_comparison.py.
6. Trích model class Student / Class / StudentEnrollment nếu tìm thấy.
7. Kết luận:
   - MULTI_ENROLLMENT_SAME_YEAR_SUPPORTED = YES/NO/UNKNOWN
   - STATUS_FIELD_AVAILABLE = YES/NO
   - READY_TO_BUILD_SAFE_IMPORTER = YES/NO

KHÔNG sửa database / mã nguồn.
"""

from __future__ import annotations

import csv
import re
import sqlite3
import sys
import zipfile
from datetime import datetime
from pathlib import Path


ROOT = Path(r"C:\PhoCap")
DB_PATH = ROOT / "data" / "phocap.db"
ROUTE_PATH = ROOT / "app" / "routers" / "student_survey_comparison.py"
APP_DIR = ROOT / "app"

TABLES = [
    "students",
    "classes",
    "student_enrollments",
    "school_years",
    "schools",
]


class AuditAbort(RuntimeError):
    pass


def qident(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def connect_ro(path: Path) -> sqlite3.Connection:
    uri = path.resolve().as_uri() + "?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    con.row_factory = sqlite3.Row
    return con


def table_exists(con, table: str) -> bool:
    return con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone() is not None


def scalar(con, sql: str, params=()) -> int:
    row = con.execute(sql, params).fetchone()
    return int(row[0] or 0) if row else 0


def write_csv(path: Path, headers: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def get_table_sql(con, table: str) -> str:
    row = con.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return str(row[0] or "") if row else ""


def table_info(con, table: str) -> list[dict]:
    rows = con.execute(
        f"PRAGMA table_info({qident(table)})"
    ).fetchall()
    return [
        {
            "table": table,
            "cid": r[0],
            "column": r[1],
            "type": r[2],
            "notnull": r[3],
            "default": r[4],
            "pk": r[5],
        }
        for r in rows
    ]


def foreign_keys(con, table: str) -> list[dict]:
    rows = con.execute(
        f"PRAGMA foreign_key_list({qident(table)})"
    ).fetchall()
    return [
        {
            "table": table,
            "fk_id": r[0],
            "seq": r[1],
            "ref_table": r[2],
            "from_column": r[3],
            "to_column": r[4],
            "on_update": r[5],
            "on_delete": r[6],
            "match": r[7],
        }
        for r in rows
    ]


def indexes(con, table: str) -> tuple[list[dict], list[dict]]:
    index_rows = []
    index_cols = []
    for r in con.execute(
        f"PRAGMA index_list({qident(table)})"
    ).fetchall():
        # SQLite columns: seq, name, unique, origin, partial
        seq, name, unique, origin, partial = r[:5]
        cols = con.execute(
            f"PRAGMA index_info({qident(name)})"
        ).fetchall()
        names = [str(c[2]) for c in cols]

        index_rows.append({
            "table": table,
            "index_name": name,
            "unique": unique,
            "origin": origin,
            "partial": partial,
            "columns": ",".join(names),
        })

        for c in cols:
            index_cols.append({
                "table": table,
                "index_name": name,
                "unique": unique,
                "seqno": c[0],
                "cid": c[1],
                "column": c[2],
            })
    return index_rows, index_cols


def read_text_safe(path: Path) -> str:
    if not path.exists():
        return ""
    for enc in ("utf-8", "utf-8-sig", "cp1258"):
        try:
            return path.read_text(encoding=enc)
        except Exception:
            pass
    return ""


def find_model_files() -> list[Path]:
    if not APP_DIR.exists():
        return []
    result = []
    for p in APP_DIR.rglob("*.py"):
        try:
            text = read_text_safe(p)
        except Exception:
            continue
        if (
            "class StudentEnrollment" in text
            or "class Student(" in text
            or "class Class(" in text
            or "class SchoolClass" in text
        ):
            result.append(p)
    return sorted(set(result))


def extract_context(text: str, pattern: str, before=20, after=35) -> list[str]:
    lines = text.splitlines()
    hits = []
    pat = re.compile(pattern, re.I)
    for i, line in enumerate(lines):
        if pat.search(line):
            start = max(0, i - before)
            end = min(len(lines), i + after + 1)
            block = [
                f"{j+1:05d}: {lines[j]}"
                for j in range(start, end)
            ]
            hits.append("\n".join(block))
    # dedupe overlapping blocks
    unique = []
    seen = set()
    for b in hits:
        key = b[:500]
        if key not in seen:
            seen.add(key)
            unique.append(b)
    return unique


def main():
    print("=" * 126)
    print("DRY-RUN V10.9 - SCHEMA TRƯỚC NẠP BASELINE HS 2025-2026 QĐ3805")
    print("=" * 126)
    print("Chế độ: CHỈ ĐỌC")

    if not DB_PATH.exists():
        raise AuditAbort(f"Không tìm thấy DB: {DB_PATH}")

    con = connect_ro(DB_PATH)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = ROOT / f"dry_run_schema_baseline_HS_QD3805_v10_9_{ts}"
    out_dir.mkdir(parents=True, exist_ok=False)

    try:
        integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
        fk_check = con.execute("PRAGMA foreign_key_check").fetchall()

        missing_tables = [t for t in TABLES if not table_exists(con, t)]

        schema_rows = []
        column_rows = []
        fk_rows = []
        index_rows = []
        index_col_rows = []
        count_rows = []

        for table in TABLES:
            if not table_exists(con, table):
                continue

            sql = get_table_sql(con, table)
            schema_rows.append({
                "table": table,
                "create_sql": sql,
            })

            column_rows.extend(table_info(con, table))
            fk_rows.extend(foreign_keys(con, table))

            idx, idx_cols = indexes(con, table)
            index_rows.extend(idx)
            index_col_rows.extend(idx_cols)

            count_rows.append({
                "table": table,
                "rows": scalar(
                    con, f"SELECT COUNT(*) FROM {qident(table)}"
                ),
            })

        # Enrollment-specific analysis.
        enrollment_cols = {
            r["column"]: r
            for r in column_rows
            if r["table"] == "student_enrollments"
        }

        unique_indexes = [
            r for r in index_rows
            if r["table"] == "student_enrollments"
            and int(r["unique"] or 0) == 1
        ]

        unique_sets = [
            tuple(
                c.strip()
                for c in str(r["columns"]).split(",")
                if c.strip()
            )
            for r in unique_indexes
        ]

        # If UNIQUE(student_id, school_year_id), multiple transfers in same year cannot be represented.
        blocks_multi_same_year = any(
            set(cols) == {"student_id", "school_year_id"}
            or cols == ("student_id", "school_year_id")
            for cols in unique_sets
        )

        # If there is a larger UNIQUE including school_id/class_id, multiple enrollments may be allowed.
        allows_distinct_school = not blocks_multi_same_year

        status_candidates = [
            c for c in enrollment_cols
            if any(token in c.lower() for token in (
                "status", "state", "change", "transfer",
                "movement", "note", "remark"
            ))
        ]

        # Required columns without default besides id.
        required_no_default = []
        for name, info in enrollment_cols.items():
            if name == "id":
                continue
            if int(info["notnull"] or 0) == 1 and info["default"] is None:
                required_no_default.append(name)

        # Route source excerpts.
        route_text = read_text_safe(ROUTE_PATH)
        route_blocks = []
        if route_text:
            for pat in (
                r"StudentEnrollment",
                r"school_year_id",
                r"batch\.school_year_id",
                r"school_id",
            ):
                route_blocks.extend(
                    extract_context(route_text, pat, before=12, after=24)
                )

        # model source excerpts.
        model_files = find_model_files()
        model_blocks = []
        for p in model_files:
            txt = read_text_safe(p)
            for pat in (
                r"class\s+StudentEnrollment\b",
                r"class\s+Student\b",
                r"class\s+(Class|SchoolClass)\b",
            ):
                blocks = extract_context(txt, pat, before=5, after=80)
                for b in blocks:
                    model_blocks.append(
                        f"FILE: {p}\n{b}"
                    )

        uses_batch_current_year = bool(
            re.search(
                r"StudentEnrollment\.school_year_id\s*==\s*batch\.school_year_id",
                route_text,
                flags=re.S,
            )
        )

        has_prev_year_logic = bool(
            re.search(
                r"(previous|prev|prior|baseline|2025.?2026)",
                route_text,
                flags=re.I,
            )
        )

        has_qd3805 = "3805" in route_text

        multi_support = (
            "NO" if blocks_multi_same_year
            else "YES"
        )

        ready = (
            integrity == "ok"
            and not fk_check
            and not missing_tables
            and "student_id" in enrollment_cols
            and "school_id" in enrollment_cols
            and "school_year_id" in enrollment_cols
        )

        gate_rows = [
            {
                "check": "integrity_check",
                "result": "PASS" if integrity == "ok" else "FAIL",
                "detail": str(integrity),
            },
            {
                "check": "foreign_key_check",
                "result": "PASS" if not fk_check else "FAIL",
                "detail": str(len(fk_check)),
            },
            {
                "check": "required_tables",
                "result": "PASS" if not missing_tables else "FAIL",
                "detail": ",".join(missing_tables),
            },
            {
                "check": "student_enrollment_columns",
                "result": "INFO",
                "detail": ",".join(enrollment_cols.keys()),
            },
            {
                "check": "student_enrollment_required_no_default",
                "result": "INFO",
                "detail": ",".join(required_no_default),
            },
            {
                "check": "student_enrollment_unique_sets",
                "result": "INFO",
                "detail": " | ".join(
                    "(" + ",".join(x) + ")" for x in unique_sets
                ),
            },
            {
                "check": "MULTI_ENROLLMENT_SAME_YEAR_SUPPORTED",
                "result": multi_support,
                "detail": (
                    "Có UNIQUE(student_id,school_year_id), phải chọn 1 enrollment hiệu lực."
                    if blocks_multi_same_year
                    else "Không thấy UNIQUE chặn nhiều enrollment cùng năm."
                ),
            },
            {
                "check": "STATUS_FIELD_AVAILABLE",
                "result": "YES" if status_candidates else "NO",
                "detail": ",".join(status_candidates),
            },
            {
                "check": "comparison_uses_batch_current_year",
                "result": "YES" if uses_batch_current_year else "NO",
                "detail": str(ROUTE_PATH),
            },
            {
                "check": "comparison_has_previous_year_logic",
                "result": "YES" if has_prev_year_logic else "NO",
                "detail": "",
            },
            {
                "check": "comparison_has_qd3805_logic",
                "result": "YES" if has_qd3805 else "NO",
                "detail": "",
            },
            {
                "check": "READY_TO_BUILD_SAFE_IMPORTER",
                "result": "YES" if ready else "NO",
                "detail": (
                    "Đã đủ schema để viết bộ cài chính thức."
                    if ready
                    else "Thiếu bảng/cột hoặc DB không an toàn."
                ),
            },
        ]

        write_csv(
            out_dir / "510_TABLE_CREATE_SQL.csv",
            ["table", "create_sql"],
            schema_rows,
        )
        write_csv(
            out_dir / "511_TABLE_COLUMNS.csv",
            ["table", "cid", "column", "type", "notnull", "default", "pk"],
            column_rows,
        )
        write_csv(
            out_dir / "512_FOREIGN_KEYS.csv",
            [
                "table", "fk_id", "seq", "ref_table",
                "from_column", "to_column",
                "on_update", "on_delete", "match",
            ],
            fk_rows,
        )
        write_csv(
            out_dir / "513_INDEXES.csv",
            ["table", "index_name", "unique", "origin", "partial", "columns"],
            index_rows,
        )
        write_csv(
            out_dir / "514_INDEX_COLUMNS.csv",
            ["table", "index_name", "unique", "seqno", "cid", "column"],
            index_col_rows,
        )
        write_csv(
            out_dir / "515_TABLE_COUNTS.csv",
            ["table", "rows"],
            count_rows,
        )
        write_csv(
            out_dir / "516_GATE_V10_9.csv",
            ["check", "result", "detail"],
            gate_rows,
        )

        (out_dir / "517_COMPARISON_ROUTE_CONTEXT.txt").write_text(
            (
                f"FILE: {ROUTE_PATH}\n\n"
                + ("\n\n" + "="*110 + "\n\n").join(route_blocks[:40])
                if route_blocks
                else f"Không đọc được hoặc không tìm thấy context trong {ROUTE_PATH}"
            ),
            encoding="utf-8",
        )

        (out_dir / "518_MODEL_CONTEXT.txt").write_text(
            (
                "\n\n" + "="*110 + "\n\n"
            ).join(model_blocks[:30])
            if model_blocks
            else "Không tìm thấy model class Student/StudentEnrollment/Class.",
            encoding="utf-8",
        )

        summary = out_dir / "00_TONG_QUAN_V10_9.txt"
        with summary.open("w", encoding="utf-8") as f:
            f.write(
                "DRY-RUN V10.9 - SCHEMA TRƯỚC NẠP BASELINE HS 2025-2026 QĐ3805\n"
            )
            f.write("=" * 126 + "\n")
            f.write("CHỈ ĐỌC - KHÔNG SỬA DATABASE / MÃ NGUỒN\n\n")

            f.write(f"Integrity: {integrity}\n")
            f.write(f"FK errors: {len(fk_check)}\n")
            f.write(f"Missing tables: {missing_tables}\n\n")

            f.write("STUDENT_ENROLLMENTS\n")
            f.write(
                "- columns: " + ",".join(enrollment_cols.keys()) + "\n"
            )
            f.write(
                "- required_no_default: "
                + ",".join(required_no_default)
                + "\n"
            )
            f.write(
                "- unique_sets: "
                + " | ".join(
                    "(" + ",".join(x) + ")" for x in unique_sets
                )
                + "\n"
            )
            f.write(
                "- MULTI_ENROLLMENT_SAME_YEAR_SUPPORTED = "
                + multi_support + "\n"
            )
            f.write(
                "- STATUS_FIELD_AVAILABLE = "
                + ("YES" if status_candidates else "NO")
                + " [" + ",".join(status_candidates) + "]\n\n"
            )

            f.write("COMPARISON ROUTE\n")
            f.write(
                "- uses_batch_current_year = "
                + ("YES" if uses_batch_current_year else "NO")
                + "\n"
            )
            f.write(
                "- has_previous_year_logic = "
                + ("YES" if has_prev_year_logic else "NO")
                + "\n"
            )
            f.write(
                "- has_qd3805_logic = "
                + ("YES" if has_qd3805 else "NO")
                + "\n\n"
            )

            f.write(
                "READY_TO_BUILD_SAFE_IMPORTER = "
                + ("YES" if ready else "NO")
                + "\n"
            )

        zip_path = ROOT / f"dry_run_schema_baseline_HS_QD3805_v10_9_{ts}.zip"
        with zipfile.ZipFile(
            zip_path,
            "w",
            compression=zipfile.ZIP_DEFLATED,
        ) as zf:
            for p in sorted(out_dir.iterdir()):
                zf.write(p, arcname=p.name)

        print()
        print("=" * 126)
        print("HOÀN THÀNH DRY-RUN V10.9")
        print("=" * 126)
        print(
            "MULTI_ENROLLMENT_SAME_YEAR_SUPPORTED: "
            + multi_support
        )
        print(
            "STATUS_FIELD_AVAILABLE: "
            + ("YES" if status_candidates else "NO")
        )
        if status_candidates:
            print("Status fields: " + ",".join(status_candidates))
        print(
            "COMPARISON_USES_BATCH_CURRENT_YEAR: "
            + ("YES" if uses_batch_current_year else "NO")
        )
        print(
            "READY_TO_BUILD_SAFE_IMPORTER: "
            + ("YES" if ready else "NO")
        )
        print(f"ZIP: {zip_path}")
        print("Database / mã nguồn: KHÔNG bị thay đổi.")

    finally:
        con.close()


if __name__ == "__main__":
    try:
        main()
    except AuditAbort as exc:
        print()
        print("=" * 126)
        print("ĐÃ DỪNG DRY-RUN V10.9")
        print("=" * 126)
        print(str(exc))
        print("Database / mã nguồn: KHÔNG bị thay đổi.")
        sys.exit(2)
    except Exception as exc:
        print()
        print("=" * 126)
        print("LỖI KHÔNG DỰ KIẾN TRONG V10.9")
        print("=" * 126)
        print(repr(exc))
        print("Database / mã nguồn: KHÔNG bị thay đổi.")
        sys.exit(4)
