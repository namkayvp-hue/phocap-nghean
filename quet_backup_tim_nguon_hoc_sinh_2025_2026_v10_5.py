# -*- coding: utf-8 -*-
r"""
DRY-RUN V10.5 - QUÉT BACKUP TÌM NGUỒN HỌC SINH 2025-2026
===========================================================

MỤC TIÊU
--------
Quét các file database backup dưới C:\PhoCap\backups để xác định:
- Có backup nào từng chứa historical_datasets / historical_people
  của năm học 2025-2026 hay không.
- Có backup nào từng chứa students / student_enrollments hay không.
- Có thể phục hồi nguồn học sinh 2025-2026 từ backup thay vì nhập lại hay không.

CHỈ ĐỌC
-------
- Không sửa DB hiện tại.
- Không sửa backup.
- Không restore.
- Không xóa file.

CHẠY
----
    cd C:\PhoCap
    .\.venv\Scripts\python.exe .\quet_backup_tim_nguon_hoc_sinh_2025_2026_v10_5.py
"""

from __future__ import annotations

import csv
import os
import re
import sqlite3
import sys
import zipfile
from datetime import datetime
from pathlib import Path


ROOT = Path(r"C:\PhoCap")
BACKUP_DIR = ROOT / "backups"
CURRENT_DB = ROOT / "data" / "phocap.db"

DB_EXTS = {".db", ".sqlite", ".sqlite3"}


def qident(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def write_csv(path: Path, headers: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def connect_ro(path: Path):
    uri = path.resolve().as_uri() + "?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    con.row_factory = sqlite3.Row
    return con


def table_exists(con, table: str) -> bool:
    return con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone() is not None


def colset(con, table: str) -> set[str]:
    if not table_exists(con, table):
        return set()
    return {
        str(r[1])
        for r in con.execute(f"PRAGMA table_info({qident(table)})").fetchall()
    }


def scalar(con, sql: str, params=()) -> int:
    row = con.execute(sql, params).fetchone()
    return int(row[0] or 0) if row else 0


def year_map(con) -> dict[int, str]:
    if not table_exists(con, "school_years"):
        return {}
    cs = colset(con, "school_years")
    label_col = next(
        (x for x in ("name", "label", "school_year", "year_name", "code") if x in cs),
        None,
    )
    if not label_col:
        return {}
    rows = con.execute(
        f"SELECT id,{qident(label_col)} AS label FROM school_years ORDER BY id"
    ).fetchall()
    return {int(r["id"]): str(r["label"] or "") for r in rows}


def baseline_year_id(con) -> int | None:
    years = year_map(con)
    matches = []
    for yid, label in years.items():
        if re.search(r"2025\D*2026", label):
            matches.append(yid)
    return matches[0] if len(matches) == 1 else None


def count_historical_2025(con, year_id: int | None) -> tuple[int, int, int]:
    """
    Returns: datasets, households linked to 2025 dataset, people linked to 2025 dataset
    """
    if year_id is None or not table_exists(con, "historical_datasets"):
        return 0, 0, 0

    ds_cols = colset(con, "historical_datasets")
    if "school_year_id" not in ds_cols:
        return 0, 0, 0

    dataset_ids = [
        int(r[0])
        for r in con.execute(
            "SELECT id FROM historical_datasets WHERE school_year_id=?",
            (year_id,),
        ).fetchall()
    ]
    ds_count = len(dataset_ids)

    if not dataset_ids:
        return ds_count, 0, 0

    marks = ",".join("?" for _ in dataset_ids)

    hh_count = 0
    if table_exists(con, "historical_households") and "dataset_id" in colset(con, "historical_households"):
        hh_count = scalar(
            con,
            f"SELECT COUNT(*) FROM historical_households WHERE dataset_id IN ({marks})",
            dataset_ids,
        )

    people_count = 0
    if table_exists(con, "historical_people") and "dataset_id" in colset(con, "historical_people"):
        people_count = scalar(
            con,
            f"SELECT COUNT(*) FROM historical_people WHERE dataset_id IN ({marks})",
            dataset_ids,
        )

    return ds_count, hh_count, people_count


def count_direct_year(con, table: str, year_id: int | None) -> int:
    if year_id is None or not table_exists(con, table):
        return 0
    cs = colset(con, table)
    if "school_year_id" not in cs:
        return 0
    return scalar(
        con,
        f"SELECT COUNT(*) FROM {qident(table)} WHERE school_year_id=?",
        (year_id,),
    )


def inspect_db(path: Path) -> dict:
    result = {
        "file": str(path),
        "file_name": path.name,
        "size_mb": round(path.stat().st_size / (1024 * 1024), 3),
        "modified": datetime.fromtimestamp(path.stat().st_mtime).isoformat(sep=" ", timespec="seconds"),
        "open_status": "ERROR",
        "integrity_check": "",
        "baseline_year_id": "",
        "baseline_year_label": "",
        "historical_datasets_2025_2026": 0,
        "historical_households_2025_2026": 0,
        "historical_people_2025_2026": 0,
        "students_total": 0,
        "student_enrollments_total": 0,
        "student_enrollments_2025_2026": 0,
        "classes_2025_2026": 0,
        "recoverable_baseline": "NO",
        "note": "",
    }

    con = None
    try:
        con = connect_ro(path)
        result["open_status"] = "OK"

        try:
            integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
        except Exception as exc:
            integrity = f"ERROR:{exc}"
        result["integrity_check"] = str(integrity)

        years = year_map(con)
        yid = baseline_year_id(con)
        result["baseline_year_id"] = "" if yid is None else yid
        result["baseline_year_label"] = years.get(yid, "") if yid is not None else ""

        ds, hh, hp = count_historical_2025(con, yid)
        result["historical_datasets_2025_2026"] = ds
        result["historical_households_2025_2026"] = hh
        result["historical_people_2025_2026"] = hp

        if table_exists(con, "students"):
            result["students_total"] = scalar(con, "SELECT COUNT(*) FROM students")

        if table_exists(con, "student_enrollments"):
            result["student_enrollments_total"] = scalar(
                con, "SELECT COUNT(*) FROM student_enrollments"
            )
            result["student_enrollments_2025_2026"] = count_direct_year(
                con, "student_enrollments", yid
            )

        result["classes_2025_2026"] = count_direct_year(
            con, "classes", yid
        )

        recoverable = (
            int(result["historical_people_2025_2026"]) > 0
            or int(result["student_enrollments_2025_2026"]) > 0
            or int(result["students_total"]) > 0
        )
        result["recoverable_baseline"] = "YES" if recoverable else "NO"

    except Exception as exc:
        result["note"] = repr(exc)
    finally:
        if con is not None:
            con.close()

    return result


def main() -> None:
    print("=" * 122)
    print("DRY-RUN V10.5 - QUÉT BACKUP TÌM NGUỒN HỌC SINH 2025-2026")
    print("=" * 122)
    print("Chế độ: CHỈ ĐỌC - KHÔNG RESTORE")

    if not BACKUP_DIR.exists():
        print(f"Không tìm thấy thư mục backup: {BACKUP_DIR}")
        sys.exit(2)

    candidates = []
    for path in BACKUP_DIR.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() in DB_EXTS:
            candidates.append(path)

    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = ROOT / f"dry_run_tim_nguon_2025_2026_trong_backup_v10_5_{ts}"
    out_dir.mkdir(parents=True, exist_ok=False)

    rows = []
    for i, path in enumerate(candidates, start=1):
        print(f"[{i}/{len(candidates)}] {path.name}")
        rows.append(inspect_db(path))

    recoverable = [
        r for r in rows if r["recoverable_baseline"] == "YES"
    ]

    # Sort recoverable with strongest evidence first.
    recoverable.sort(
        key=lambda r: (
            int(r["historical_people_2025_2026"]),
            int(r["student_enrollments_2025_2026"]),
            int(r["students_total"]),
            r["modified"],
        ),
        reverse=True,
    )

    headers = [
        "file", "file_name", "size_mb", "modified",
        "open_status", "integrity_check",
        "baseline_year_id", "baseline_year_label",
        "historical_datasets_2025_2026",
        "historical_households_2025_2026",
        "historical_people_2025_2026",
        "students_total",
        "student_enrollments_total",
        "student_enrollments_2025_2026",
        "classes_2025_2026",
        "recoverable_baseline",
        "note",
    ]

    write_csv(
        out_dir / "470_ALL_BACKUPS.csv",
        headers,
        rows,
    )

    write_csv(
        out_dir / "471_BACKUPS_CO_NGUON_2025_2026.csv",
        headers,
        recoverable,
    )

    gate_rows = [
        {
            "check": "backup_database_files_scanned",
            "result": "INFO",
            "detail": str(len(rows)),
        },
        {
            "check": "backups_with_recoverable_2025_2026",
            "result": "FOUND" if recoverable else "NO_DATA",
            "detail": str(len(recoverable)),
        },
        {
            "check": "BASELINE_2025_2026_FOUND_IN_BACKUP",
            "result": "YES" if recoverable else "NO",
            "detail": (
                recoverable[0]["file"]
                if recoverable
                else "Không tìm thấy nguồn học sinh 2025-2026 trong backup database."
            ),
        },
        {
            "check": "NEXT_STEP",
            "result": "RECOVER_FROM_BACKUP" if recoverable else "NEED_SOURCE_FILE",
            "detail": (
                "Chưa restore. Cần dry-run trích xuất đúng dữ liệu 2025-2026 từ backup tốt nhất."
                if recoverable
                else "Cần cung cấp/import lại file nguồn học sinh 2025-2026 chính thức."
            ),
        },
    ]

    write_csv(
        out_dir / "472_GATE_V10_5.csv",
        ["check", "result", "detail"],
        gate_rows,
    )

    summary = out_dir / "00_TONG_QUAN_V10_5.txt"
    with summary.open("w", encoding="utf-8") as f:
        f.write("DRY-RUN V10.5 - QUÉT BACKUP TÌM NGUỒN HỌC SINH 2025-2026\n")
        f.write("=" * 122 + "\n")
        f.write("CHỈ ĐỌC - KHÔNG RESTORE\n\n")
        f.write(f"Số DB backup đã quét: {len(rows)}\n")
        f.write(f"Số backup có nguồn 2025-2026 khả dụng: {len(recoverable)}\n\n")

        if recoverable:
            f.write("BACKUP TỐT NHẤT\n")
            best = recoverable[0]
            for k in headers:
                f.write(f"- {k}: {best.get(k, '')}\n")
            f.write("\nBASELINE_2025_2026_FOUND_IN_BACKUP = YES\n")
            f.write("NEXT_STEP = DRY_RUN_RECOVER_BASELINE_FROM_BACKUP\n")
        else:
            f.write("BASELINE_2025_2026_FOUND_IN_BACKUP = NO\n")
            f.write("NEXT_STEP = NEED_SOURCE_FILE_2025_2026\n")

    zip_path = ROOT / f"dry_run_tim_nguon_2025_2026_trong_backup_v10_5_{ts}.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(out_dir.iterdir()):
            zf.write(p, arcname=p.name)

    print()
    print("=" * 122)
    print("HOÀN THÀNH DRY-RUN V10.5")
    print("=" * 122)
    print(f"Backup DB đã quét: {len(rows)}")
    print(f"Backup có nguồn 2025-2026: {len(recoverable)}")
    print(
        "BASELINE_2025_2026_FOUND_IN_BACKUP: "
        + ("YES" if recoverable else "NO")
    )
    if recoverable:
        best = recoverable[0]
        print(f"Backup tốt nhất: {best['file']}")
        print(f"historical_people 2025-2026: {best['historical_people_2025_2026']}")
        print(f"student_enrollments 2025-2026: {best['student_enrollments_2025_2026']}")
        print(f"students total: {best['students_total']}")
    print(f"ZIP: {zip_path}")
    print("Không có database nào bị thay đổi.")


if __name__ == "__main__":
    main()
