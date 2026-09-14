# -*- coding: utf-8 -*-
r"""
DRY-RUN V10.8.1 - CHUẨN BỊ NẠP BASELINE HỌC SINH 2025-2026 QĐ 3805
==================================================================

NGHIỆP VỤ ĐÃ CHỐT
-----------------
- 2025-2026 là nguồn học sinh CHÍNH THỨC để đối chiếu cho 2026-2027.
- 2026-2027 hiện có chỉ là TEST, không dùng làm baseline chính thức.
- Lịch sử 2025-2026 phải giữ nguyên trường/lớp cũ.
- Khi đối chiếu 2026-2027, trường đích sau QĐ 3805 được phép nhìn baseline
  của chính trường đích + các trường nguồn đã sáp nhập vào nó.
- Không tự biến dữ liệu điều tra thành students/student_enrollments.
- Không coi mọi mã học sinh lặp là lỗi: chuyển trường trong cùng năm có thể
  tạo nhiều enrollment cho cùng một Student.

FILE NGUỒN
----------
Đặt file:
    C:\PhoCap\uploads\Nguon_HS_2025_2026_Nghi_Loc_QD3805.zip

Bên trong phải có:
    MN_Nghi_Loc_2025_2026.xlsx
    TH_Nghi_Loc_2025_2026.xlsx
    THCS_Nghi_Loc_2025_2026.xlsx

V10.8 CHỈ ĐỌC:
- Không sửa DB.
- Không sửa file nguồn.
- Không sửa mã nguồn.

KẾT QUẢ
-------
Tạo ZIP báo cáo tại C:\PhoCap\dry_run_baseline_HS_QD3805_v10_8_<timestamp>.zip
"""

from __future__ import annotations

import csv
import io
import re
import sqlite3
import sys
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path


ROOT = Path(r"C:\PhoCap")
DB_PATH = ROOT / "data" / "phocap.db"
SOURCE_DIR = ROOT / "uploads"
SOURCE_BUNDLE = SOURCE_DIR / "Nguon_HS_2025_2026_Nghi_Loc_QD3805.zip"
COMPARISON_PY = ROOT / "app" / "routers" / "student_survey_comparison.py"

FILES = {
    "MN": "MN_Nghi_Loc_2025_2026.xlsx",
    "TH": "TH_Nghi_Loc_2025_2026.xlsx",
    "THCS": "THCS_Nghi_Loc_2025_2026.xlsx",
}

# Cột theo 3 mẫu nguồn.
SOURCE_CONFIG = {
    "MN": {
        "school": "C",
        "class": "E",
        "code": "F",
        "name": "G",
        "status": "K",
    },
    "TH": {
        "school": "C",
        "class": "D",
        "code": "E",
        "name": "F",
        "status": "Q",
    },
    "THCS": {
        "school": "C",
        "class": "E",
        "code": "F",
        "name": "G",
        "status": "K",
    },
}

# QĐ 3805 - fixed source -> target.
MERGE_MAP = {
    750: 748,    # MN Nghi Hoa -> MN Nghi Dien
    751: 748,    # MN Nghi Van -> MN Nghi Dien
    749: 747,    # MN Nghi Trung -> MN TT Quan Hanh
    1181: 1178,  # TH Nghi Van -> TH Nghi Dien
    1180: 1179,  # TH Nghi Hoa -> TH Nghi Trung
    1608: 1605,  # THCS Nghi Van -> THCS Nghi Dien
    1607: 1606,  # THCS Nghi Hoa -> THCS Nghi Trung
}

TARGET_IDS = sorted(set(MERGE_MAP.values()))
SOURCE_IDS = sorted(MERGE_MAP)
QD_SCHOOL_IDS = sorted(set(SOURCE_IDS) | set(TARGET_IDS))

# Tên trong Excel -> school_id hiện tại.
EXCEL_SCHOOL_TO_ID = {
    # MN
    "Trường Mầm non Nghi Diên": 748,
    "Trường Mầm non Nghi Hoa": 750,
    "Trường Mầm non Nghi Vạn": 751,
    "Trường Mầm non TT Quán Hành": 747,
    "Trường MN Nghi Trung": 749,

    # TH
    "Trường TH Nghi Diên": 1178,
    "Trường Tiểu học Nghi Vạn": 1181,
    "Trường TH Nghi Trung": 1179,
    "Trường Tiểu học Nghi Hoa": 1180,

    # THCS
    "THCS Nghi Diên": 1605,
    "THCS Nghi Vạn": 1608,
    "THCS Nghi Trung": 1606,
    "THCS Nghi Hoa": 1607,
}

EXPECTED_LEVEL_BY_ID = {
    747: "MN", 748: "MN", 749: "MN", 750: "MN", 751: "MN",
    1178: "TH", 1179: "TH", 1180: "TH", 1181: "TH",
    1605: "THCS", 1606: "THCS", 1607: "THCS", 1608: "THCS",
}

NS = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL_NS = {"p": "http://schemas.openxmlformats.org/package/2006/relationships"}


class AuditAbort(RuntimeError):
    pass


def qident(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def markers(n: int) -> str:
    return ",".join("?" for _ in range(n))


def normalize(value) -> str:
    text = str(value or "").strip().lower()
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = text.replace("đ", "d")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def write_csv(path: Path, headers: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


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


def colset(con: sqlite3.Connection, table: str) -> set[str]:
    if not table_exists(con, table):
        return set()
    return {
        str(r[1])
        for r in con.execute(f"PRAGMA table_info({qident(table)})").fetchall()
    }


def scalar(con: sqlite3.Connection, sql: str, params=()) -> int:
    row = con.execute(sql, params).fetchone()
    return int(row[0] or 0) if row else 0


def school_year_map(con: sqlite3.Connection) -> dict[int, str]:
    cs = colset(con, "school_years")
    label_col = next(
        (c for c in ("code", "name", "label", "school_year", "year_name") if c in cs),
        None,
    )
    if not label_col:
        raise AuditAbort("Không xác định được cột tên/code năm học.")
    rows = con.execute(
        f"SELECT id,{qident(label_col)} AS label FROM school_years ORDER BY id"
    ).fetchall()
    return {int(r["id"]): str(r["label"] or "") for r in rows}


def find_year_id(years: dict[int, str], start: int, end: int) -> int:
    matches = []
    for yid, label in years.items():
        if str(start) in label and str(end) in label:
            matches.append(yid)
    if len(matches) != 1:
        raise AuditAbort(
            f"Không xác định duy nhất năm {start}-{end}. Matches={matches}, years={years}"
        )
    return matches[0]


def school_map(con: sqlite3.Connection) -> dict[int, dict]:
    cs = colset(con, "schools")
    name_col = next(
        (c for c in ("name", "school_name", "ten_truong") if c in cs),
        None,
    )
    if not name_col:
        raise AuditAbort("Không xác định được cột tên trường.")
    code_col = next(
        (c for c in ("code", "school_code", "ma_truong") if c in cs),
        None,
    )
    select = [
        "id",
        f"{qident(name_col)} AS name",
        f"{qident(code_col)} AS code" if code_col else "'' AS code",
        "is_active" if "is_active" in cs else "NULL AS is_active",
        "commune_id" if "commune_id" in cs else "NULL AS commune_id",
    ]
    rows = con.execute(
        "SELECT " + ",".join(select)
        + f" FROM schools WHERE id IN ({markers(len(QD_SCHOOL_IDS))})",
        QD_SCHOOL_IDS,
    ).fetchall()
    return {
        int(r["id"]): {
            "id": int(r["id"]),
            "name": str(r["name"] or ""),
            "code": str(r["code"] or ""),
            "is_active": r["is_active"],
            "commune_id": r["commune_id"],
        }
        for r in rows
    }


def parse_xlsx_bytes(data: bytes) -> list[dict[str, str]]:
    """
    Đọc Sheet1 của XLSX bằng ZIP/XML thuần stdlib.
    Không cần openpyxl.
    """
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            root = ET.fromstring(z.read("xl/sharedStrings.xml"))
            for si in root.findall("a:si", NS):
                shared.append(
                    "".join(
                        (t.text or "")
                        for t in si.iter(
                            "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t"
                        )
                    )
                )

        workbook = ET.fromstring(z.read("xl/workbook.xml"))
        rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        rel_map = {
            r.attrib["Id"]: r.attrib["Target"]
            for r in rels.findall("p:Relationship", REL_NS)
        }

        sheet_target = None
        for s in workbook.find("a:sheets", NS):
            if s.attrib.get("name") == "Sheet1":
                rid = s.attrib[
                    "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
                ]
                sheet_target = rel_map[rid]
                break

        if not sheet_target:
            raise AuditAbort("File Excel không có Sheet1.")

        sheet_path = (
            sheet_target if sheet_target.startswith("xl/")
            else "xl/" + sheet_target
        )
        root = ET.fromstring(z.read(sheet_path))

        result = []
        for row in root.findall(".//a:sheetData/a:row", NS):
            rid = int(row.attrib["r"])
            if rid < 7:
                continue

            values = {}
            for c in row.findall("a:c", NS):
                ref = c.attrib["r"]
                m = re.match(r"([A-Z]+)", ref)
                if not m:
                    continue
                col = m.group(1)
                typ = c.attrib.get("t")
                v = c.find("a:v", NS)
                value = ""
                if v is not None:
                    raw = v.text or ""
                    if typ == "s":
                        try:
                            value = shared[int(raw)]
                        except Exception:
                            value = raw
                    else:
                        value = raw
                inline = c.find("a:is/a:t", NS)
                if inline is not None:
                    value = inline.text or ""
                values[col] = str(value or "").strip()

            if values:
                result.append(values)

        return result


def row_to_record(level: str, row: dict[str, str]) -> dict | None:
    cfg = SOURCE_CONFIG[level]
    full_name = row.get(cfg["name"], "").strip()
    code = row.get(cfg["code"], "").strip()
    school_name = row.get(cfg["school"], "").strip()
    class_name = row.get(cfg["class"], "").strip()
    status = row.get(cfg["status"], "").strip()

    if not any((full_name, code, school_name, class_name)):
        return None
    if not full_name:
        return None

    school_id = EXCEL_SCHOOL_TO_ID.get(school_name)
    return {
        "level": level,
        "student_code": code,
        "full_name": full_name,
        "school_name_excel": school_name,
        "school_id": school_id,
        "class_name": class_name,
        "status_raw": status,
    }


def main() -> None:
    print("=" * 126)
    print("DRY-RUN V10.8.1 - CHUẨN BỊ NẠP BASELINE HỌC SINH 2025-2026 QĐ3805")
    print("=" * 126)
    print("Chế độ: CHỈ ĐỌC")

    if not DB_PATH.exists():
        raise AuditAbort(f"Không tìm thấy database: {DB_PATH}")

    # V10.8.1 ưu tiên đọc trực tiếp 3 file Excel đang có trong C:\\PhoCap\\uploads.
    # Nếu không đủ 3 file thì mới thử ZIP nguồn của V10.8 cũ.
    direct_paths = {
        level: SOURCE_DIR / filename
        for level, filename in FILES.items()
    }

    direct_ready = all(path.exists() for path in direct_paths.values())

    records = []
    source_file_rows = []

    if direct_ready:
        source_mode = "DIRECT_XLSX"
        print("Nguồn: đọc trực tiếp 3 file Excel trong C:\\PhoCap\\uploads")

        for level, path in direct_paths.items():
            raw_rows = parse_xlsx_bytes(path.read_bytes())
            converted = []
            for row in raw_rows:
                rec = row_to_record(level, row)
                if rec is not None:
                    converted.append(rec)

            records.extend(converted)
            source_file_rows.append({
                "level": level,
                "file": str(path),
                "student_rows_detected": len(converted),
            })

    elif SOURCE_BUNDLE.exists():
        source_mode = "ZIP_BUNDLE"
        print(f"Nguồn: đọc ZIP {SOURCE_BUNDLE}")

        with zipfile.ZipFile(SOURCE_BUNDLE) as z:
            names = set(z.namelist())
            missing = [
                filename
                for filename in FILES.values()
                if filename not in names
            ]
            if missing:
                raise AuditAbort(
                    "ZIP nguồn thiếu file: " + ", ".join(missing)
                )

            for level, filename in FILES.items():
                raw_rows = parse_xlsx_bytes(z.read(filename))
                converted = []
                for row in raw_rows:
                    rec = row_to_record(level, row)
                    if rec is not None:
                        converted.append(rec)

                records.extend(converted)
                source_file_rows.append({
                    "level": level,
                    "file": f"{SOURCE_BUNDLE}!{filename}",
                    "student_rows_detected": len(converted),
                })

    else:
        missing_direct = [
            str(path)
            for path in direct_paths.values()
            if not path.exists()
        ]
        found_xlsx = sorted(
            p.name for p in SOURCE_DIR.glob("*.xlsx")
        ) if SOURCE_DIR.exists() else []

        raise AuditAbort(
            "Không tìm thấy đủ nguồn học sinh 2025-2026.\n"
            "V10.8.1 chấp nhận MỘT TRONG HAI cách:\n"
            "1) Có đủ 3 file Excel trực tiếp:\n"
            "   C:\\PhoCap\\uploads\\MN_Nghi_Loc_2025_2026.xlsx\n"
            "   C:\\PhoCap\\uploads\\TH_Nghi_Loc_2025_2026.xlsx\n"
            "   C:\\PhoCap\\uploads\\THCS_Nghi_Loc_2025_2026.xlsx\n"
            "HOẶC\n"
            "2) Có file ZIP:\n"
            "   C:\\PhoCap\\uploads\\Nguon_HS_2025_2026_Nghi_Loc_QD3805.zip\n\n"
            "Các file Excel còn thiếu:\n- "
            + "\n- ".join(missing_direct)
            + "\n\nCác file .xlsx hiện thấy trong uploads:\n- "
            + ("\n- ".join(found_xlsx) if found_xlsx else "(không có)")
        )

    con = connect_ro(DB_PATH)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = ROOT / f"dry_run_baseline_HS_QD3805_v10_8_1_{ts}"
    out_dir.mkdir(parents=True, exist_ok=False)

    try:
        integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
        fk = con.execute("PRAGMA foreign_key_check").fetchall()

        years = school_year_map(con)
        baseline_year_id = find_year_id(years, 2025, 2026)
        test_year_id = find_year_id(years, 2026, 2027)

        schools = school_map(con)
        if len(schools) != len(QD_SCHOOL_IDS):
            missing_ids = sorted(set(QD_SCHOOL_IDS) - set(schools))
            raise AuditAbort(f"Thiếu school_id QĐ3805 trong database: {missing_ids}")

        # Check DB school state against QD plan.
        school_rows = []
        school_problems = []
        for sid in QD_SCHOOL_IDS:
            s = schools[sid]
            expected_active = 0 if sid in SOURCE_IDS else 1
            ok = s["is_active"] in (expected_active, bool(expected_active))
            if not ok:
                school_problems.append(
                    f"school_id={sid} {s['name']} active={s['is_active']} expected={expected_active}"
                )
            school_rows.append({
                "school_id": sid,
                "school_name_db": s["name"],
                "level": EXPECTED_LEVEL_BY_ID[sid],
                "role": "SOURCE" if sid in SOURCE_IDS else "TARGET",
                "target_id": MERGE_MAP.get(sid, sid),
                "is_active": s["is_active"],
                "expected_active": expected_active,
                "check": "PASS" if ok else "FAIL",
            })

        # Filter only the QD3805 school rows from the 3 source files.
        unknown_school_rows = [
            r for r in records
            if r["school_id"] is None
        ]
        qd_records = [
            r for r in records
            if r["school_id"] in QD_SCHOOL_IDS
        ]

        # Validate level.
        level_mismatch = [
            r for r in qd_records
            if EXPECTED_LEVEL_BY_ID.get(r["school_id"]) != r["level"]
        ]

        # Counts by original school.
        by_school = Counter(r["school_id"] for r in qd_records)
        original_rows = []
        for sid in QD_SCHOOL_IDS:
            original_rows.append({
                "school_id": sid,
                "school_name_db": schools[sid]["name"],
                "level": EXPECTED_LEVEL_BY_ID[sid],
                "role": "SOURCE" if sid in SOURCE_IDS else "TARGET",
                "rows_2025_2026_source_file": by_school.get(sid, 0),
                "mapped_target_id_for_2026_2027": MERGE_MAP.get(sid, sid),
                "mapped_target_name": schools[MERGE_MAP.get(sid, sid)]["name"],
            })

        # Counts by target group.
        group_rows = []
        for target_id in TARGET_IDS:
            member_ids = sorted(
                [target_id]
                + [sid for sid, tid in MERGE_MAP.items() if tid == target_id]
            )
            subset = [r for r in qd_records if r["school_id"] in member_ids]
            codes = [r["student_code"] for r in subset if r["student_code"]]
            counts = Counter(codes)
            duplicate_codes = {code: n for code, n in counts.items() if n > 1}
            group_rows.append({
                "target_id": target_id,
                "target_name": schools[target_id]["name"],
                "level": EXPECTED_LEVEL_BY_ID[target_id],
                "baseline_school_ids": ",".join(map(str, member_ids)),
                "baseline_school_names": " | ".join(schools[sid]["name"] for sid in member_ids),
                "source_rows": len(subset),
                "nonempty_student_codes": len(codes),
                "unique_student_codes": len(counts),
                "duplicate_codes_within_target_group": len(duplicate_codes),
            })

        # Duplicate student codes across ALL Nghi Loc source rows in QD scope.
        code_rows = defaultdict(list)
        for r in qd_records:
            if r["student_code"]:
                code_rows[r["student_code"]].append(r)

        duplicate_detail = []
        for code, items in sorted(code_rows.items()):
            if len(items) <= 1:
                continue
            for r in items:
                duplicate_detail.append({
                    "student_code": code,
                    "full_name": r["full_name"],
                    "level": r["level"],
                    "school_id": r["school_id"],
                    "school_name_excel": r["school_name_excel"],
                    "school_name_db": schools[r["school_id"]]["name"],
                    "class_name": r["class_name"],
                    "status_raw": r["status_raw"],
                    "mapped_target_id": MERGE_MAP.get(r["school_id"], r["school_id"]),
                    "mapped_target_name": schools[
                        MERGE_MAP.get(r["school_id"], r["school_id"])
                    ]["name"],
                })

        # Exact duplicate enrollment key in source (same code + school + class).
        enrollment_keys = Counter(
            (
                r["student_code"],
                r["school_id"],
                normalize(r["class_name"]),
            )
            for r in qd_records
            if r["student_code"]
        )
        exact_duplicate_enrollment_keys = [
            (k, n) for k, n in enrollment_keys.items() if n > 1
        ]

        # Missing code / class.
        missing_code = [r for r in qd_records if not r["student_code"]]
        missing_class = [r for r in qd_records if not r["class_name"]]

        # Status catalog.
        status_rows = []
        status_counter = Counter(
            (r["level"], r["status_raw"]) for r in qd_records
        )
        for (level, status), n in sorted(status_counter.items()):
            status_rows.append({
                "level": level,
                "status_raw": status,
                "rows": n,
                "note": (
                    "GIỮ NGUYÊN RAW; mapping active/inactive sẽ khóa ở bước import."
                ),
            })

        # Existing DB baseline/test rows.
        db_rows = []
        for table in ("classes", "student_enrollments"):
            cs = colset(con, table)
            if {"school_id", "school_year_id"} <= cs:
                baseline_count = scalar(
                    con,
                    f"SELECT COUNT(*) FROM {qident(table)} "
                    f"WHERE school_id IN ({markers(len(QD_SCHOOL_IDS))}) "
                    "AND school_year_id=?",
                    QD_SCHOOL_IDS + [baseline_year_id],
                )
                test_count = scalar(
                    con,
                    f"SELECT COUNT(*) FROM {qident(table)} "
                    f"WHERE school_id IN ({markers(len(QD_SCHOOL_IDS))}) "
                    "AND school_year_id=?",
                    QD_SCHOOL_IDS + [test_year_id],
                )
                db_rows.append({
                    "table": table,
                    "baseline_year_id": baseline_year_id,
                    "baseline_rows_qd3805": baseline_count,
                    "test_year_id": test_year_id,
                    "test_rows_qd3805": test_count,
                })

        students_total = (
            scalar(con, "SELECT COUNT(*) FROM students")
            if table_exists(con, "students") else 0
        )

        # Existing Student.code collisions.
        source_codes = sorted({
            r["student_code"] for r in qd_records if r["student_code"]
        })
        existing_code_count = 0
        existing_code_samples = []
        if source_codes and table_exists(con, "students"):
            # Chunk SQLite IN lists.
            for start in range(0, len(source_codes), 700):
                chunk = source_codes[start:start+700]
                rows = con.execute(
                    f"SELECT id,code,full_name FROM students "
                    f"WHERE code IN ({markers(len(chunk))})",
                    chunk,
                ).fetchall()
                existing_code_count += len(rows)
                for row in rows[:50]:
                    existing_code_samples.append({
                        "student_id": row["id"],
                        "student_code": row["code"],
                        "full_name_db": row["full_name"],
                    })

        baseline_enrollment_count = 0
        if table_exists(con, "student_enrollments"):
            baseline_enrollment_count = scalar(
                con,
                f"SELECT COUNT(*) FROM student_enrollments "
                f"WHERE school_id IN ({markers(len(QD_SCHOOL_IDS))}) "
                "AND school_year_id=?",
                QD_SCHOOL_IDS + [baseline_year_id],
            )

        # Inspect comparison logic.
        comparison_text = (
            COMPARISON_PY.read_text(encoding="utf-8")
            if COMPARISON_PY.exists() else ""
        )
        uses_batch_year = (
            "StudentEnrollment.school_year_id == batch.school_year_id"
            in comparison_text
            or "StudentEnrollment.school_year_id\n        == batch.school_year_id"
            in comparison_text
        )
        has_qd_baseline_resolver = (
            "QD3805" in comparison_text
            and "baseline" in comparison_text.lower()
            and "MERGE" in comparison_text.upper()
        )

        # Gates.
        safe_source = (
            integrity == "ok"
            and not fk
            and not school_problems
            and not level_mismatch
            and not missing_code
            and not missing_class
            and not exact_duplicate_enrollment_keys
        )

        clean_import_target = baseline_enrollment_count == 0

        gate_rows = [
            {
                "check": "integrity_check",
                "result": "PASS" if integrity == "ok" else "FAIL",
                "detail": str(integrity),
            },
            {
                "check": "foreign_key_check",
                "result": "PASS" if not fk else "FAIL",
                "detail": str(len(fk)),
            },
            {
                "check": "baseline_year_2025_2026",
                "result": "PASS",
                "detail": f"id={baseline_year_id}; label={years[baseline_year_id]}",
            },
            {
                "check": "test_year_2026_2027",
                "result": "PASS",
                "detail": f"id={test_year_id}; label={years[test_year_id]}",
            },
            {
                "check": "qd_source_rows",
                "result": "INFO",
                "detail": str(len(qd_records)),
            },
            {
                "check": "qd_unique_student_codes",
                "result": "INFO",
                "detail": str(len(code_rows)),
            },
            {
                "check": "duplicate_student_codes",
                "result": "EXPECTED_TRANSFER_REVIEW" if duplicate_detail else "PASS",
                "detail": str(len({r["student_code"] for r in duplicate_detail})),
            },
            {
                "check": "exact_duplicate_enrollment_keys",
                "result": "PASS" if not exact_duplicate_enrollment_keys else "FAIL",
                "detail": str(len(exact_duplicate_enrollment_keys)),
            },
            {
                "check": "missing_student_code",
                "result": "PASS" if not missing_code else "FAIL",
                "detail": str(len(missing_code)),
            },
            {
                "check": "missing_class",
                "result": "PASS" if not missing_class else "FAIL",
                "detail": str(len(missing_class)),
            },
            {
                "check": "school_state_qd3805",
                "result": "PASS" if not school_problems else "FAIL",
                "detail": " | ".join(school_problems),
            },
            {
                "check": "baseline_enrollments_already_in_db",
                "result": "CLEAN" if clean_import_target else "REVIEW",
                "detail": str(baseline_enrollment_count),
            },
            {
                "check": "students_total_current_db",
                "result": "INFO",
                "detail": str(students_total),
            },
            {
                "check": "source_codes_already_in_students",
                "result": "INFO" if existing_code_count else "CLEAN",
                "detail": str(existing_code_count),
            },
            {
                "check": "comparison_uses_batch_current_year",
                "result": "NEEDS_PATCH" if uses_batch_year else "REVIEW",
                "detail": (
                    "Hiện route đối chiếu đang lấy StudentEnrollment theo năm của đợt điều tra."
                    if uses_batch_year
                    else "Không thấy marker chuẩn; cần kiểm tra tay."
                ),
            },
            {
                "check": "comparison_has_qd3805_baseline_scope_resolver",
                "result": "YES" if has_qd_baseline_resolver else "NO",
                "detail": (
                    "Cần bổ sung: target 2026-2027 nhìn baseline 2025-2026 của target + sources QĐ3805."
                    if not has_qd_baseline_resolver else "Đã có dấu hiệu resolver."
                ),
            },
            {
                "check": "SAFE_SOURCE_FOR_BASELINE_IMPORT",
                "result": "YES" if safe_source else "NO",
                "detail": (
                    "Nguồn đủ điều kiện kỹ thuật để xây importer; chưa ghi DB."
                ),
            },
            {
                "check": "READY_FOR_ACTUAL_IMPORT_AND_COMPARISON_PATCH",
                "result": "YES" if safe_source and clean_import_target else "NO",
                "detail": (
                    "Bước sau phải làm trong một gói có backup + transaction: "
                    "nạp baseline 2025-2026 và sửa đối chiếu dùng previous-year/QĐ3805."
                ),
            },
        ]

        for item in source_file_rows:
            item["source_mode"] = source_mode

        write_csv(
            out_dir / "500_SOURCE_FILES.csv",
            ["source_mode", "level", "file", "student_rows_detected"],
            source_file_rows,
        )
        write_csv(
            out_dir / "501_QD3805_SCHOOL_STATE.csv",
            [
                "school_id", "school_name_db", "level", "role",
                "target_id", "is_active", "expected_active", "check",
            ],
            school_rows,
        )
        write_csv(
            out_dir / "502_BASELINE_ROWS_BY_ORIGINAL_SCHOOL.csv",
            [
                "school_id", "school_name_db", "level", "role",
                "rows_2025_2026_source_file",
                "mapped_target_id_for_2026_2027", "mapped_target_name",
            ],
            original_rows,
        )
        write_csv(
            out_dir / "503_BASELINE_BY_TARGET_GROUP.csv",
            [
                "target_id", "target_name", "level",
                "baseline_school_ids", "baseline_school_names",
                "source_rows", "nonempty_student_codes",
                "unique_student_codes", "duplicate_codes_within_target_group",
            ],
            group_rows,
        )
        write_csv(
            out_dir / "504_DUPLICATE_STUDENT_CODES_TRANSFER_REVIEW.csv",
            [
                "student_code", "full_name", "level",
                "school_id", "school_name_excel", "school_name_db",
                "class_name", "status_raw",
                "mapped_target_id", "mapped_target_name",
            ],
            duplicate_detail,
        )
        write_csv(
            out_dir / "505_STATUS_CATALOG.csv",
            ["level", "status_raw", "rows", "note"],
            status_rows,
        )
        write_csv(
            out_dir / "506_DB_BASELINE_TEST_STATE.csv",
            [
                "table", "baseline_year_id", "baseline_rows_qd3805",
                "test_year_id", "test_rows_qd3805",
            ],
            db_rows,
        )
        write_csv(
            out_dir / "507_EXISTING_STUDENT_CODE_COLLISIONS_SAMPLE.csv",
            ["student_id", "student_code", "full_name_db"],
            existing_code_samples,
        )
        write_csv(
            out_dir / "508_GATE_V10_8_1.csv",
            ["check", "result", "detail"],
            gate_rows,
        )

        summary = out_dir / "00_TONG_QUAN_V10_8_1.txt"
        with summary.open("w", encoding="utf-8") as f:
            f.write(
                "DRY-RUN V10.8.1 - CHUẨN BỊ NẠP BASELINE HỌC SINH 2025-2026 QĐ3805\n"
            )
            f.write("=" * 126 + "\n")
            f.write("CHỈ ĐỌC - KHÔNG SỬA DATABASE\n\n")
            f.write(
                f"Baseline: id={baseline_year_id} {years[baseline_year_id]}\n"
            )
            f.write(
                f"Test/current: id={test_year_id} {years[test_year_id]}\n"
            )
            f.write(f"Rows nguồn thuộc QĐ3805: {len(qd_records)}\n")
            f.write(f"Unique student codes: {len(code_rows)}\n")
            f.write(
                f"Duplicate student codes cần xử lý chuyển trường: "
                f"{len({r['student_code'] for r in duplicate_detail})}\n"
            )
            f.write(
                f"Exact duplicate enrollment keys: {len(exact_duplicate_enrollment_keys)}\n"
            )
            f.write(f"Missing code: {len(missing_code)}\n")
            f.write(f"Missing class: {len(missing_class)}\n")
            f.write(
                f"Baseline enrollments hiện có trong DB: {baseline_enrollment_count}\n"
            )
            f.write(
                f"Source codes đã có trong students: {existing_code_count}\n\n"
            )

            f.write("THEO NHÓM ĐÍCH QĐ3805\n")
            for r in group_rows:
                f.write(
                    f"- {r['target_id']} {r['target_name']}: "
                    f"rows={r['source_rows']}; "
                    f"unique_codes={r['unique_student_codes']}; "
                    f"dup_codes={r['duplicate_codes_within_target_group']}; "
                    f"baseline schools={r['baseline_school_names']}\n"
                )

            f.write("\nLOGIC ĐỐI CHIẾU\n")
            f.write(
                "- comparison_uses_batch_current_year = "
                + ("YES" if uses_batch_year else "NOT_DETECTED")
                + "\n"
            )
            f.write(
                "- qd3805_baseline_scope_resolver = "
                + ("YES" if has_qd_baseline_resolver else "NO")
                + "\n"
            )
            f.write(
                "- Yêu cầu bước sau: đối chiếu 2026-2027 dùng enrollment 2025-2026; "
                "tài khoản trường đích nhìn cả target + source schools theo QĐ3805.\n"
            )

            f.write("\nKẾT LUẬN\n")
            f.write(
                "SAFE_SOURCE_FOR_BASELINE_IMPORT = "
                + ("YES" if safe_source else "NO")
                + "\n"
            )
            f.write(
                "READY_FOR_ACTUAL_IMPORT_AND_COMPARISON_PATCH = "
                + ("YES" if safe_source and clean_import_target else "NO")
                + "\n"
            )

        zip_path = ROOT / f"dry_run_baseline_HS_QD3805_v10_8_1_{ts}.zip"
        with zipfile.ZipFile(
            zip_path, "w", compression=zipfile.ZIP_DEFLATED
        ) as zf:
            for p in sorted(out_dir.iterdir()):
                zf.write(p, arcname=p.name)

        print()
        print("=" * 126)
        print("HOÀN THÀNH DRY-RUN V10.8.1")
        print("=" * 126)
        print(f"Source mode: {source_mode}")
        print(f"Baseline 2025-2026: school_year_id={baseline_year_id}")
        print(f"TEST 2026-2027: school_year_id={test_year_id}")
        print(f"Rows nguồn QĐ3805: {len(qd_records)}")
        print(f"Unique student codes: {len(code_rows)}")
        print(
            "Duplicate student codes cần review chuyển trường: "
            f"{len({r['student_code'] for r in duplicate_detail})}"
        )
        print(f"Exact duplicate enrollment keys: {len(exact_duplicate_enrollment_keys)}")
        print(f"Missing student code: {len(missing_code)}")
        print(f"Missing class: {len(missing_class)}")
        print(f"Baseline enrollments hiện có trong DB: {baseline_enrollment_count}")
        print(f"Source codes đã có trong students: {existing_code_count}")
        print(
            "COMPARISON_CURRENTLY_USES_BATCH_YEAR: "
            + ("YES" if uses_batch_year else "NOT_DETECTED")
        )
        print(
            "SAFE_SOURCE_FOR_BASELINE_IMPORT: "
            + ("YES" if safe_source else "NO")
        )
        print(
            "READY_FOR_ACTUAL_IMPORT_AND_COMPARISON_PATCH: "
            + ("YES" if safe_source and clean_import_target else "NO")
        )
        print(f"ZIP: {zip_path}")
        print("Database / file nguồn / mã nguồn: KHÔNG bị thay đổi.")

    finally:
        con.close()


if __name__ == "__main__":
    try:
        main()
    except AuditAbort as exc:
        print()
        print("=" * 126)
        print("ĐÃ DỪNG DRY-RUN V10.8.1")
        print("=" * 126)
        print(str(exc))
        print("Database / file nguồn / mã nguồn: KHÔNG bị thay đổi.")
        sys.exit(2)
    except sqlite3.Error as exc:
        print()
        print("=" * 126)
        print("LỖI SQLITE TRONG V10.8.1")
        print("=" * 126)
        print(repr(exc))
        print("Database / file nguồn / mã nguồn: KHÔNG bị thay đổi.")
        sys.exit(3)
    except Exception as exc:
        print()
        print("=" * 126)
        print("LỖI KHÔNG DỰ KIẾN TRONG V10.8.1")
        print("=" * 126)
        print(repr(exc))
        print("Database / file nguồn / mã nguồn: KHÔNG bị thay đổi.")
        sys.exit(4)
