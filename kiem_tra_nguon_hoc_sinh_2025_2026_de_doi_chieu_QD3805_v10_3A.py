# -*- coding: utf-8 -*-
r"""
DRY-RUN V10.3A - XÁC ĐỊNH NGUỒN HỌC SINH 2025-2026 ĐỂ ĐỐI CHIẾU QĐ 3805
============================================================================

NGHIỆP VỤ ĐÃ CHỐT
-----------------
- Dữ liệu học sinh NĂM 2025-2026 là NGUỒN CHÍNH THỨC để đối chiếu cho 2026-2027.
- Dữ liệu học sinh 2026-2027 hiện có chỉ là TEST, không dùng làm số liệu thật.
- V10.3A KHÔNG sửa dữ liệu.

MỤC TIÊU
--------
1. Xác định school_year_id thật của:
   - 2025-2026 = BASELINE
   - 2026-2027 = TEST/CURRENT
2. Quét tất cả bảng có dấu hiệu chứa học sinh/lớp:
   - tên bảng student/pupil/enrollment/learner/class/survey/historical/import
   - hoặc có các cột student_id, school_id, school_year_id,
     school_name_reported, class_id, class_name...
3. Đếm dữ liệu 2025-2026 theo:
   - 7 trường nguồn QĐ 3805
   - 6 trường đích QĐ 3805
4. Tách riêng dữ liệu 2026-2027 và ghi rõ TEST.
5. Nếu bảng không có school_id nhưng có tên trường báo cáo, thống kê theo tên trường.
6. Không tự biến survey/historical thành students.
7. Đưa ra kết luận:
   - BASELINE_2025_2026_SOURCE_FOUND = YES/NO
   - BASELINE_TABLES = ...
   - TEST_2026_2027_ROWS = ...
   - READY_TO_BUILD_RECONCILIATION = YES/NO

CHẠY
----
    cd C:\PhoCap
    .\.venv\Scripts\python.exe .\kiem_tra_nguon_hoc_sinh_2025_2026_de_doi_chieu_QD3805_v10_3A.py
"""

from __future__ import annotations

import csv
import json
import re
import sqlite3
import sys
import unicodedata
import zipfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path


ROOT = Path(r"C:\PhoCap")
DB_PATH = ROOT / "data" / "phocap.db"
PLAN_FILE = ROOT / "data" / "school_merger_approved_plans.json"

BASELINE_LABEL = "2025-2026"
TEST_LABEL = "2026-2027"


class AuditAbort(RuntimeError):
    pass


def qident(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def markers(n: int) -> str:
    return ",".join("?" for _ in range(n))


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


def normalize(value) -> str:
    if value is None:
        return ""
    s = str(value).strip().lower()
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())


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
        item["target_school_id"] = int(item["target_school_id"])
        item["source_school_ids"] = [
            int(x) for x in item.get("source_school_ids") or []
        ]
        plans.append(item)

    if len(plans) != 6:
        raise AuditAbort(f"QĐ3805 phải có 6 nhóm, hiện có {len(plans)}.")

    return plans


def school_year_map(con: sqlite3.Connection) -> dict[int, str]:
    if not table_exists(con, "school_years"):
        raise AuditAbort("Không có bảng school_years.")

    cs = colset(con, "school_years")
    label_col = next(
        (c for c in ("name", "label", "school_year", "year_name") if c in cs),
        None,
    )
    if not label_col:
        raise AuditAbort("Không xác định được cột tên năm học.")

    rows = con.execute(
        f"SELECT id,{qident(label_col)} AS label FROM school_years ORDER BY id"
    ).fetchall()

    return {
        int(r["id"]): str(r["label"] or "")
        for r in rows
    }


def find_year_id(years: dict[int, str], wanted: str) -> int:
    a, b = wanted.split("-")
    matches = [
        yid for yid, label in years.items()
        if a in str(label) and b in str(label)
    ]
    if len(matches) != 1:
        raise AuditAbort(
            f"Không xác định duy nhất school_year_id cho {wanted}: {matches}"
        )
    return matches[0]


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
        f"{qident(code_col)} AS code" if code_col else "'' AS code",
        "is_active" if "is_active" in cs else "NULL AS is_active",
    ]

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


def looks_student_related(table: str, cs: set[str]) -> bool:
    low = table.lower()

    table_tokens = (
        "student", "pupil", "learner", "enrollment",
        "class", "roster", "historical_people",
        "survey_person", "school_import", "import_student",
    )
    if any(t in low for t in table_tokens):
        return True

    column_tokens = {
        "student_id",
        "linked_student_id",
        "school_name_reported",
        "class_id",
        "class_name",
        "class_name_reported",
        "grade_level",
        "grade_reported",
    }
    return bool(cs & column_tokens)


def table_kind(table: str) -> str:
    low = table.lower()
    if "enrollment" in low:
        return "ENROLLMENT"
    if low == "students" or low.endswith("_students"):
        return "STUDENT_MASTER"
    if "class" in low:
        return "CLASS"
    if "survey_person" in low:
        return "SURVEY"
    if "historical" in low:
        return "HISTORICAL"
    if "import" in low:
        return "IMPORT"
    return "OTHER_STUDENT_RELATED"


def count_school_year(
    con: sqlite3.Connection,
    table: str,
    school_ids: list[int],
    year_id: int,
) -> int | None:
    cs = colset(con, table)
    if not {"school_id", "school_year_id"} <= cs:
        return None

    return scalar(
        con,
        f"SELECT COUNT(*) FROM {qident(table)} "
        f"WHERE school_id IN ({markers(len(school_ids))}) "
        "AND school_year_id=?",
        school_ids + [year_id],
    )


def reported_school_rows(
    con: sqlite3.Connection,
    table: str,
    year_id: int,
    source_names: list[str],
    target_names: list[str],
) -> list[dict]:
    cs = colset(con, table)
    if "school_name_reported" not in cs:
        return []

    year_filter = ""
    params = []
    if "school_year_id" in cs:
        year_filter = " AND school_year_id=?"
        params.append(year_id)

    rows = con.execute(
        f"SELECT school_name_reported,COUNT(*) AS n "
        f"FROM {qident(table)} "
        "WHERE school_name_reported IS NOT NULL "
        "AND TRIM(school_name_reported)<>''"
        + year_filter
        + " GROUP BY school_name_reported "
        "ORDER BY n DESC",
        params,
    ).fetchall()

    source_norms = [normalize(x) for x in source_names]
    target_norms = [normalize(x) for x in target_names]

    result = []
    for r in rows:
        name = str(r["school_name_reported"] or "")
        norm = normalize(name)
        role = "OTHER"
        if any(x and x in norm for x in source_norms):
            role = "SOURCE_NAME_MATCH"
        elif any(x and x in norm for x in target_norms):
            role = "TARGET_NAME_MATCH"

        if role != "OTHER":
            result.append({
                "table": table,
                "school_year_id": year_id,
                "school_name_reported": name,
                "normalized_name": norm,
                "role_match": role,
                "rows": int(r["n"]),
            })
    return result


def main() -> None:
    print("=" * 124)
    print("DRY-RUN V10.3A - NGUỒN HỌC SINH 2025-2026 ĐỂ ĐỐI CHIẾU QĐ3805")
    print("=" * 124)
    print("Chế độ: CHỈ ĐỌC")

    plans = load_plans()

    source_ids = sorted({
        sid for p in plans for sid in p["source_school_ids"]
    })
    target_ids = sorted({
        p["target_school_id"] for p in plans
    })
    all_ids = sorted(set(source_ids) | set(target_ids))

    con = connect_ro(DB_PATH)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = ROOT / f"dry_run_nguon_hoc_sinh_2025_2026_QD3805_v10_3A_{ts}"
    out_dir.mkdir(parents=True, exist_ok=False)

    try:
        integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
        fk_errors = con.execute("PRAGMA foreign_key_check").fetchall()

        years = school_year_map(con)
        baseline_year_id = find_year_id(years, BASELINE_LABEL)
        test_year_id = find_year_id(years, TEST_LABEL)

        schools = school_map(con, all_ids)

        source_names = [
            schools[sid]["name"] for sid in source_ids
        ]
        target_names = [
            schools[tid]["name"] for tid in target_ids
        ]

        catalog = []
        baseline_direct = []
        test_direct = []
        reported_baseline = []
        reported_test = []

        baseline_tables_with_data = []
        test_tables_with_data = []

        for table in all_tables(con):
            cs = colset(con, table)
            if not looks_student_related(table, cs):
                continue

            total = scalar(
                con, f"SELECT COUNT(*) FROM {qident(table)}"
            )

            baseline_source = count_school_year(
                con, table, source_ids, baseline_year_id
            )
            baseline_target = count_school_year(
                con, table, target_ids, baseline_year_id
            )
            test_source = count_school_year(
                con, table, source_ids, test_year_id
            )
            test_target = count_school_year(
                con, table, target_ids, test_year_id
            )

            catalog.append({
                "table": table,
                "kind": table_kind(table),
                "total_rows": total,
                "has_school_id": "YES" if "school_id" in cs else "NO",
                "has_school_year_id": "YES" if "school_year_id" in cs else "NO",
                "has_school_name_reported": (
                    "YES" if "school_name_reported" in cs else "NO"
                ),
                "has_student_id": "YES" if "student_id" in cs else "NO",
                "columns": ",".join(sorted(cs)),
            })

            if baseline_source is not None:
                baseline_direct.append({
                    "table": table,
                    "kind": table_kind(table),
                    "year_id": baseline_year_id,
                    "year_label": years[baseline_year_id],
                    "source_rows": baseline_source,
                    "target_rows": baseline_target,
                    "meaning": "BASELINE_2025_2026_OFFICIAL_SOURCE",
                })
                if (baseline_source or 0) + (baseline_target or 0) > 0:
                    baseline_tables_with_data.append(table)

            if test_source is not None:
                test_direct.append({
                    "table": table,
                    "kind": table_kind(table),
                    "year_id": test_year_id,
                    "year_label": years[test_year_id],
                    "source_rows": test_source,
                    "target_rows": test_target,
                    "meaning": "TEST_2026_2027_DO_NOT_USE_AS_OFFICIAL_SOURCE",
                })
                if (test_source or 0) + (test_target or 0) > 0:
                    test_tables_with_data.append(table)

            if "school_name_reported" in cs:
                b = reported_school_rows(
                    con,
                    table,
                    baseline_year_id,
                    source_names,
                    target_names,
                )
                for r in b:
                    r["meaning"] = "BASELINE_2025_2026_NAME_MATCH"
                reported_baseline.extend(b)

                t = reported_school_rows(
                    con,
                    table,
                    test_year_id,
                    source_names,
                    target_names,
                )
                for r in t:
                    r["meaning"] = "TEST_2026_2027_NAME_MATCH"
                reported_test.extend(t)

        baseline_direct_rows = sum(
            int(r["source_rows"] or 0) + int(r["target_rows"] or 0)
            for r in baseline_direct
        )
        baseline_reported_rows = sum(
            int(r["rows"]) for r in reported_baseline
        )

        test_direct_rows = sum(
            int(r["source_rows"] or 0) + int(r["target_rows"] or 0)
            for r in test_direct
        )
        test_reported_rows = sum(
            int(r["rows"]) for r in reported_test
        )

        baseline_found = (
            baseline_direct_rows > 0 or baseline_reported_rows > 0
        )

        ready = baseline_found and integrity == "ok" and not fk_errors

        gate_rows = [
            {
                "check": "baseline_year_id_2025_2026",
                "result": "PASS",
                "detail": f"{baseline_year_id}:{years[baseline_year_id]}",
            },
            {
                "check": "test_year_id_2026_2027",
                "result": "PASS",
                "detail": f"{test_year_id}:{years[test_year_id]}",
            },
            {
                "check": "baseline_tables_with_direct_school_data",
                "result": "INFO",
                "detail": ",".join(sorted(set(baseline_tables_with_data))),
            },
            {
                "check": "baseline_direct_rows_qd3805",
                "result": "FOUND" if baseline_direct_rows > 0 else "NO_DATA",
                "detail": str(baseline_direct_rows),
            },
            {
                "check": "baseline_reported_name_rows_qd3805",
                "result": "FOUND" if baseline_reported_rows > 0 else "NO_DATA",
                "detail": str(baseline_reported_rows),
            },
            {
                "check": "test_direct_rows_qd3805",
                "result": "TEST",
                "detail": str(test_direct_rows),
            },
            {
                "check": "test_reported_name_rows_qd3805",
                "result": "TEST",
                "detail": str(test_reported_rows),
            },
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
                "check": "BASELINE_2025_2026_SOURCE_FOUND",
                "result": "YES" if baseline_found else "NO",
                "detail": (
                    f"direct={baseline_direct_rows}; "
                    f"reported_name={baseline_reported_rows}"
                ),
            },
            {
                "check": "READY_TO_BUILD_RECONCILIATION",
                "result": "YES" if ready else "NO",
                "detail": (
                    "Chỉ dùng dữ liệu 2025-2026; "
                    "2026-2027 hiện tại được đánh dấu TEST."
                ),
            },
        ]

        write_csv(
            out_dir / "450_STUDENT_RELATED_TABLE_CATALOG.csv",
            [
                "table", "kind", "total_rows",
                "has_school_id", "has_school_year_id",
                "has_school_name_reported", "has_student_id",
                "columns",
            ],
            catalog,
        )

        write_csv(
            out_dir / "451_BASELINE_2025_2026_DIRECT_COUNTS.csv",
            [
                "table", "kind", "year_id", "year_label",
                "source_rows", "target_rows", "meaning",
            ],
            baseline_direct,
        )

        write_csv(
            out_dir / "452_TEST_2026_2027_DIRECT_COUNTS.csv",
            [
                "table", "kind", "year_id", "year_label",
                "source_rows", "target_rows", "meaning",
            ],
            test_direct,
        )

        write_csv(
            out_dir / "453_BASELINE_2025_2026_REPORTED_SCHOOL_NAMES.csv",
            [
                "table", "school_year_id",
                "school_name_reported", "normalized_name",
                "role_match", "rows", "meaning",
            ],
            reported_baseline,
        )

        write_csv(
            out_dir / "454_TEST_2026_2027_REPORTED_SCHOOL_NAMES.csv",
            [
                "table", "school_year_id",
                "school_name_reported", "normalized_name",
                "role_match", "rows", "meaning",
            ],
            reported_test,
        )

        write_csv(
            out_dir / "455_GATE_V10_3A.csv",
            ["check", "result", "detail"],
            gate_rows,
        )

        summary = out_dir / "00_TONG_QUAN_V10_3A.txt"
        with summary.open("w", encoding="utf-8") as f:
            f.write(
                "DRY-RUN V10.3A - NGUỒN HỌC SINH 2025-2026 ĐỂ ĐỐI CHIẾU\n"
            )
            f.write("=" * 124 + "\n")
            f.write("CHỈ ĐỌC - KHÔNG SỬA DATABASE\n\n")

            f.write(
                f"BASELINE 2025-2026: school_year_id={baseline_year_id} "
                f"label={years[baseline_year_id]}\n"
            )
            f.write(
                f"TEST 2026-2027: school_year_id={test_year_id} "
                f"label={years[test_year_id]}\n\n"
            )

            f.write("BASELINE 2025-2026\n")
            f.write(f"- direct rows QĐ3805: {baseline_direct_rows}\n")
            f.write(f"- reported-school-name rows: {baseline_reported_rows}\n")
            f.write(
                "- tables direct: "
                + ",".join(sorted(set(baseline_tables_with_data)))
                + "\n\n"
            )

            f.write("TEST 2026-2027\n")
            f.write(f"- direct rows QĐ3805: {test_direct_rows}\n")
            f.write(f"- reported-school-name rows: {test_reported_rows}\n")
            f.write(
                "- tables direct: "
                + ",".join(sorted(set(test_tables_with_data)))
                + "\n\n"
            )

            f.write("KẾT LUẬN\n")
            f.write(
                "BASELINE_2025_2026_SOURCE_FOUND = "
                + ("YES" if baseline_found else "NO")
                + "\n"
            )
            f.write(
                "READY_TO_BUILD_RECONCILIATION = "
                + ("YES" if ready else "NO")
                + "\n"
            )
            f.write(
                "- Dữ liệu 2026-2027 hiện tại KHÔNG được dùng làm nguồn chính thức.\n"
            )
            f.write(
                "- Không tự biến dữ liệu survey/historical thành students.\n"
            )

        zip_path = ROOT / (
            f"dry_run_nguon_hoc_sinh_2025_2026_QD3805_v10_3A_{ts}.zip"
        )
        with zipfile.ZipFile(
            zip_path,
            "w",
            compression=zipfile.ZIP_DEFLATED,
        ) as zf:
            for p in sorted(out_dir.iterdir()):
                zf.write(p, arcname=p.name)

        print()
        print("=" * 124)
        print("HOÀN THÀNH DRY-RUN V10.3A")
        print("=" * 124)
        print(
            f"BASELINE 2025-2026: id={baseline_year_id} "
            f"{years[baseline_year_id]}"
        )
        print(
            f"TEST 2026-2027: id={test_year_id} "
            f"{years[test_year_id]}"
        )
        print(f"Baseline direct rows QĐ3805: {baseline_direct_rows}")
        print(f"Baseline reported-name rows: {baseline_reported_rows}")
        print(f"Test direct rows QĐ3805: {test_direct_rows}")
        print(f"Test reported-name rows: {test_reported_rows}")
        print(
            "BASELINE_2025_2026_SOURCE_FOUND: "
            + ("YES" if baseline_found else "NO")
        )
        print(
            "READY_TO_BUILD_RECONCILIATION: "
            + ("YES" if ready else "NO")
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
        print("=" * 124)
        print("ĐÃ DỪNG DRY-RUN V10.3A")
        print("=" * 124)
        print(str(exc))
        print("Database / JSON / mã nguồn: KHÔNG bị thay đổi.")
        sys.exit(2)
    except sqlite3.Error as exc:
        print()
        print("=" * 124)
        print("LỖI SQLITE TRONG V10.3A")
        print("=" * 124)
        print(repr(exc))
        print("Database / JSON / mã nguồn: KHÔNG bị thay đổi.")
        sys.exit(3)
    except Exception as exc:
        print()
        print("=" * 124)
        print("LỖI KHÔNG DỰ KIẾN TRONG V10.3A")
        print("=" * 124)
        print(repr(exc))
        print("Database / JSON / mã nguồn: KHÔNG bị thay đổi.")
        sys.exit(4)
