# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import os
import re
import sqlite3
import sys
import traceback
import zipfile
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree as ET

PROJECT = Path(r"C:\PhoCap")
APP = PROJECT / "app"
DB = PROJECT / "data" / "phocap.db"
EXPORTS = PROJECT / "exports"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
REPORT = EXPORTS / f"bao_cao_khao_sat_v2_4_4_0_lien_cap_th_thcs_{STAMP}.txt"

REPORT_CODES = (
    "PCGD_TH_M1_2025",
    "PCGD_TH_02_2025",
    "PCGD_TH_01_GV_2025",
    "PCGD_TH_01_CSVC_2025",
    "PCGD_THCS_M1_2025",
    "PCGD_THCS_M2_2025",
    "PCGD_THCS_TK_2025",
    "PCGD_THCS_M5_2025",
    "PCGD_THCS_CSVC_2025",
)

KEYWORDS = (
    "PCGD_TH_M1_2025",
    "PCGD_TH_02_2025",
    "PCGD_THCS_M1_2025",
    "PCGD_THCS_M2_2025",
    "TH-02",
    "THCS-M2",
    "TH_02",
    "THCS_M2",
    "age6_grade1_rate",
    "age11_completed_rate",
    "age14_completed_rate",
    "age11_remaining_all_study_primary",
    "age15_18_graduated_thcs_rate",
    "age15_18_upper_program_rate",
    '["T8"]',
    '"T8"',
    '["W14"]',
    '"W14"',
    "structured_school_form",
    "school_structured_report_inputs",
    "CSVC",
    "staff",
)

SOURCE_EXTS = {".py", ".html", ".jinja2", ".j2", ".txt"}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            block = f.read(1024 * 1024)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def safe_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig", errors="replace")
    except Exception:
        return ""


def line_hits(path: Path, keywords=KEYWORDS, context=3):
    text = safe_text(path)
    if not text:
        return []
    lines = text.splitlines()
    hits = []
    seen = set()

    for i, line in enumerate(lines):
        if any(k.lower() in line.lower() for k in keywords):
            start = max(0, i - context)
            end = min(len(lines), i + context + 1)
            key = (start, end)
            if key in seen:
                continue
            seen.add(key)
            block = []
            for j in range(start, end):
                block.append(f"{j+1:05d}: {lines[j]}")
            hits.append("\n".join(block))
    return hits


def list_tables(con):
    return [
        r[0]
        for r in con.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' "
            "ORDER BY name"
        ).fetchall()
    ]


def table_columns(con, table):
    return [
        {
            "cid": row[0],
            "name": row[1],
            "type": row[2],
            "notnull": row[3],
            "default": row[4],
            "pk": row[5],
        }
        for row in con.execute(f'PRAGMA table_info("{table}")').fetchall()
    ]


def count_rows(con, table):
    try:
        return int(con.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
    except Exception:
        return None


def find_relevant_tables(con):
    relevant = []
    for table in list_tables(con):
        cols = table_columns(con, table)
        colnames = " ".join(c["name"].lower() for c in cols)
        haystack = (table + " " + colnames).lower()
        score_terms = (
            "school",
            "student",
            "survey",
            "staff",
            "teacher",
            "csvc",
            "facility",
            "class",
            "structured",
            "report",
            "year",
        )
        score = sum(term in haystack for term in score_terms)
        if score >= 2 or any(
            token in table.lower()
            for token in (
                "school_structured_report_inputs",
                "school_mn01_csvc_inputs",
                "staff",
                "survey_person_year",
                "student",
                "classroom",
            )
        ):
            relevant.append((score, table, cols))
    relevant.sort(key=lambda x: (-x[0], x[1]))
    return relevant


def find_school_year(con, label="2026-2027"):
    for table in ("school_years", "school_year", "academic_years"):
        if table not in list_tables(con):
            continue
        cols = [c["name"] for c in table_columns(con, table)]
        for name_col in ("name", "label", "school_year", "code", "year"):
            if name_col in cols:
                try:
                    row = con.execute(
                        f'SELECT * FROM "{table}" WHERE "{name_col}"=? LIMIT 1',
                        (label,),
                    ).fetchone()
                    if row is not None:
                        return table, row
                except Exception:
                    pass
    return None, None


def find_schools(con):
    if "schools" not in list_tables(con):
        return []
    cols = [c["name"] for c in table_columns(con, "schools")]
    name_col = "name" if "name" in cols else None
    if not name_col:
        return []

    sql = (
        'SELECT * FROM schools '
        'WHERE lower(name) LIKE ? OR lower(name) LIKE ? '
        'ORDER BY id'
    )
    rows = con.execute(
        sql,
        ("%tiểu học%nghi ho%", "%thcs%nghi ho%"),
    ).fetchall()
    return rows


def row_to_dict(cursor, row):
    if row is None:
        return None
    return {d[0]: row[idx] for idx, d in enumerate(cursor.description)}


def dump_matching_rows(con, table, school_ids, year_ids):
    cols = [c["name"] for c in table_columns(con, table)]
    if not cols:
        return []

    clauses = []
    params = []

    if school_ids:
        for candidate in ("school_id", "schoolid"):
            if candidate in cols:
                placeholders = ",".join("?" for _ in school_ids)
                clauses.append(f'"{candidate}" IN ({placeholders})')
                params.extend(school_ids)
                break

    if year_ids:
        for candidate in ("school_year_id", "year_id", "academic_year_id"):
            if candidate in cols:
                placeholders = ",".join("?" for _ in year_ids)
                clauses.append(f'"{candidate}" IN ({placeholders})')
                params.extend(year_ids)
                break

    if not clauses:
        return []

    sql = f'SELECT * FROM "{table}" WHERE ' + " AND ".join(clauses) + " LIMIT 20"
    try:
        cur = con.execute(sql, params)
        return [
            {d[0]: row[i] for i, d in enumerate(cur.description)}
            for row in cur.fetchall()
        ]
    except Exception:
        return []


def xlsx_sheet_names(path: Path):
    names = []
    try:
        with zipfile.ZipFile(path, "r") as z:
            data = z.read("xl/workbook.xml")
            root = ET.fromstring(data)
            ns = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
            for s in root.findall(".//x:sheets/x:sheet", ns):
                names.append(s.attrib.get("name", ""))
    except Exception:
        pass
    return names


def xlsx_formula_markers(path: Path):
    markers = []
    try:
        with zipfile.ZipFile(path, "r") as z:
            for name in z.namelist():
                if not name.startswith("xl/worksheets/sheet") or not name.endswith(".xml"):
                    continue
                raw = z.read(name).decode("utf-8", errors="ignore")
                for cell in ("T8", "W14"):
                    if f'r="{cell}"' in raw:
                        idx = raw.find(f'r="{cell}"')
                        snippet = raw[max(0, idx-200): idx+500]
                        markers.append((name, cell, snippet.replace("\n", " ")))
    except Exception:
        pass
    return markers


def main():
    print("=" * 124)
    print("V2.4.4.0 - KHẢO SÁT CHỈ ĐỌC CHUỖI LIÊN CẤP TH-M1 -> TH-02 VÀ THCS-M1 -> THCS-M2")
    print("=" * 124)

    if not DB.exists():
        print("DỪNG: không tìm thấy database:", DB)
        return 2
    if not APP.exists():
        print("DỪNG: không tìm thấy thư mục app:", APP)
        return 2

    EXPORTS.mkdir(parents=True, exist_ok=True)

    db_hash_before = sha256(DB)
    lines = []
    add = lines.append

    add("=" * 124)
    add("BÁO CÁO KHẢO SÁT V2.4.4.0 - LIÊN CẤP TH / THCS")
    add("=" * 124)
    add(f"Thời gian: {datetime.now():%d/%m/%Y %H:%M:%S}")
    add(f"Project: {PROJECT}")
    add(f"Database: {DB}")
    add("Mục tiêu: khóa nguồn dữ liệu thật cho TH-02 và THCS-M2 trước khi vá.")
    add("")

    con = sqlite3.connect(str(DB))
    con.row_factory = sqlite3.Row
    try:
        con.execute("PRAGMA query_only = ON")
        integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
        fk = con.execute("PRAGMA foreign_key_check").fetchall()

        add("I. AN TOÀN DATABASE")
        add(f"integrity_check: {integrity}")
        add(f"foreign_key_check: {len(fk)} lỗi")
        add(f"SHA256 trước khảo sát: {db_hash_before}")
        add("")

        tables = list_tables(con)
        relevant = find_relevant_tables(con)

        add("II. CÁC BẢNG DỮ LIỆU LIÊN QUAN")
        for score, table, cols in relevant[:80]:
            add(f"[{table}] score={score}, rows={count_rows(con, table)}")
            add("  columns: " + ", ".join(c["name"] for c in cols))
        add("")

        year_table, year_row = find_school_year(con)
        year_ids = []
        if year_row is not None:
            year_ids.append(int(year_row["id"]) if "id" in year_row.keys() else None)
            year_ids = [x for x in year_ids if x is not None]
            add("III. NĂM HỌC TEST")
            add(f"Table: {year_table}")
            add("Row: " + repr(dict(year_row)))
        else:
            add("III. NĂM HỌC TEST")
            add("Không tự xác định được row 2026-2027.")
        add("")

        school_rows = find_schools(con)
        school_ids = []
        add("IV. TRƯỜNG TEST TÌM THẤY")
        if not school_rows:
            add("Không tự tìm thấy Trường Tiểu học Nghi Hòa / Trường THCS Nghi Hòa.")
        else:
            for row in school_rows:
                d = dict(row)
                add(repr(d))
                if d.get("id") is not None:
                    school_ids.append(int(d["id"]))
        add("")

        add("V. DỮ LIỆU THẬT CỦA CÁC BẢNG CÓ school_id/year_id")
        for _score, table, _cols in relevant:
            rows = dump_matching_rows(con, table, school_ids, year_ids)
            if not rows:
                continue
            add(f"--- {table} ---")
            for row in rows[:20]:
                add(repr(row))
        add("")

    finally:
        con.close()

    add("VI. DÒ SOURCE THEO REPORT CODE / METRIC / Ô KẾT LUẬN")
    source_files = [
        p for p in APP.rglob("*")
        if p.is_file() and p.suffix.lower() in SOURCE_EXTS
    ]

    hit_file_count = 0
    for path in sorted(source_files):
        hits = line_hits(path)
        if not hits:
            continue
        hit_file_count += 1
        add("")
        add(f"### {path.relative_to(PROJECT)}")
        for block in hits[:40]:
            add(block)
            add("---")

    add("")
    add(f"Tổng file source có hit: {hit_file_count}")
    add("")

    add("VII. REPORT REGISTRY / ROUTE ĐANG TỒN TẠI")
    for code in REPORT_CODES:
        found = []
        for path in source_files:
            text = safe_text(path)
            if code in text:
                found.append(str(path.relative_to(PROJECT)))
        add(f"{code}:")
        if found:
            for item in found:
                add("  - " + item)
        else:
            add("  - KHÔNG TÌM THẤY")
    add("")

    add("VIII. TEMPLATE XLSX CÓ TH / THCS")
    xlsx_files = list(APP.rglob("*.xlsx"))
    matched_xlsx = []
    for path in sorted(xlsx_files):
        sheets = xlsx_sheet_names(path)
        joined = " | ".join(sheets)
        if any(
            token.lower() in joined.lower()
            for token in ("TH-02", "THCS", "M2", "TH_02", "Mẫu 2")
        ) or any(
            token.lower() in path.name.lower()
            for token in ("th_02", "th-02", "thcs", "m2")
        ):
            matched_xlsx.append(path)
            add(f"{path.relative_to(PROJECT)}")
            add("  sheets: " + joined)
            for xml_name, cell, snippet in xlsx_formula_markers(path):
                add(f"  XML {xml_name} có ô {cell}: {snippet[:600]}")
    if not matched_xlsx:
        add("Không tìm thấy template XLSX theo tên/sheet TH-02 hoặc THCS-M2.")
    add("")

    add("IX. ĐIỂM KHÓA CẦN TRẢ LỜI SAU KHẢO SÁT")
    add("1. TH-02 đang lấy từng cột từ đâu? M1, DB trực tiếp hay hardcode?")
    add("2. TH-02 cột 18/19 (Đội ngũ, CSVC/TBDH) đã có nguồn hay còn trống?")
    add("3. TH-02 T8 có được cố ý để trống ở scope Trường hay bị lỗi?")
    add("4. THCS-M2 đang lấy các chỉ tiêu từ THCS-M1/THCS-TK hay tính lại?")
    add("5. THCS-M2 điều kiện bảo đảm GV/CSVC có nguồn chuyên biệt chưa?")
    add("6. THCS-M2 W14 có được cố ý để trống ở scope Trường hay bị lỗi?")
    add("7. Bảng school_structured_report_inputs đang lưu payload CSVC TH/THCS ra sao?")
    add("8. Metric evaluator xã hiện hành đang dùng đúng metric nào cho TH và THCS?")
    add("")

    db_hash_after = sha256(DB)
    add("X. XÁC NHẬN KHÔNG THAY ĐỔI DATABASE")
    add(f"SHA256 sau khảo sát : {db_hash_after}")
    add(f"SHA256 giữ nguyên   : {'ĐẠT' if db_hash_after == db_hash_before else 'KHÔNG ĐẠT'}")

    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")

    print("ĐÃ TẠO BÁO CÁO CHỈ ĐỌC:")
    print(REPORT)
    print()
    print("Không có source/database nào bị sửa.")
    print("SHA256 database giữ nguyên:", db_hash_after == db_hash_before)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        print()
        print("KHẢO SÁT GẶP LỖI, nhưng script không có lệnh ghi source/database.")
        raise
