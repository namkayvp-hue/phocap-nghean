# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(r"C:\PhoCap")
DB_PATH = ROOT / "data" / "phocap.db"
EXPORTS = ROOT / "exports"
STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
REPORT = EXPORTS / f"bao_cao_khao_sat_v2_4_3_1_khoa_scope_7_bieu_mn_{STAMP}.txt"

TARGET_SCHOOL_YEAR_CODE = "2026-2027"
TARGET_COMMUNE_CODE = "17827"
TARGET_SCHOOL_CODE = "40429325"

SOURCE_FILES = [
    ROOT / "app" / "routers" / "survey_summary_report.py",
    ROOT / "app" / "routers" / "pcgdmn_template_report.py",
    ROOT / "app" / "services" / "mn_report_v246.py",
]

def out(lines, text=""):
    lines.append(str(text))

def qident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'

def table_exists(conn, table):
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return bool(row)

def cols(conn, table):
    if not table_exists(conn, table):
        return []
    return [row["name"] for row in conn.execute(f"PRAGMA table_info({qident(table)})")]

def fetchone_dict(conn, sql, params=()):
    row = conn.execute(sql, params).fetchone()
    return dict(row) if row else None

def fetchall_dict(conn, sql, params=()):
    return [dict(row) for row in conn.execute(sql, params).fetchall()]

def norm(s):
    s = str(s or "").lower().strip()
    s = re.sub(r"[àáạảãâầấậẩẫăằắặẳẵ]", "a", s)
    s = re.sub(r"[èéẹẻẽêềếệểễ]", "e", s)
    s = re.sub(r"[ìíịỉĩ]", "i", s)
    s = re.sub(r"[òóọỏõôồốộổỗơờớợởỡ]", "o", s)
    s = re.sub(r"[ùúụủũưừứựửữ]", "u", s)
    s = re.sub(r"[ỳýỵỷỹ]", "y", s)
    s = s.replace("đ", "d")
    s = re.sub(r"\btruong\b", " ", s)
    s = re.sub(r"\bmam non\b", " ", s)
    s = re.sub(r"\bmn\b", " ", s)
    s = re.sub(r"\bnhom tre\b", " ", s)
    s = re.sub(r"\bnt\b", " ", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())

def year_start(code):
    try:
        return int(str(code).split("-")[0])
    except Exception:
        return None

def extract_function(path: Path, func_name: str):
    if not path.is_file():
        return []
    text = path.read_text(encoding="utf-8", errors="replace")
    raw = text.splitlines()
    start = None
    indent = None
    pat = re.compile(rf"^(\s*)(?:async\s+)?def\s+{re.escape(func_name)}\s*\(")
    for i, line in enumerate(raw):
        m = pat.match(line)
        if m:
            start = i
            indent = len(m.group(1))
            break
    if start is None:
        return []
    end = min(len(raw), start + 260)
    for j in range(start + 1, min(len(raw), start + 260)):
        line = raw[j]
        stripped = line.strip()
        if not stripped:
            continue
        lead = len(line) - len(line.lstrip())
        if lead <= indent and re.match(r"^(?:async\s+)?def\s+|^class\s+|^@router\.", line.lstrip()):
            end = j
            break
    return [(i + 1, raw[i]) for i in range(start, end)]

def safe_count(conn, table, where="", params=()):
    if not table_exists(conn, table):
        return None
    sql = f"SELECT COUNT(*) AS n FROM {qident(table)}"
    if where:
        sql += " WHERE " + where
    return conn.execute(sql, params).fetchone()["n"]

def main():
    lines = []
    out(lines, "=" * 124)
    out(lines, "BÀI 13B-12 V2.4.3.1 - KHẢO SÁT CHỈ ĐỌC KHÓA SCOPE/NỐI NGUỒN 7 BIỂU MẦM NON")
    out(lines, "=" * 124)
    out(lines, f"Thời gian: {datetime.now():%d/%m/%Y %H:%M:%S}")
    out(lines)
    out(lines, "NGUYÊN TẮC:")
    out(lines, "- CHỈ ĐỌC database/source.")
    out(lines, "- KHÔNG INSERT / UPDATE / DELETE.")
    out(lines, "- KHÔNG sửa source.")
    out(lines, "- KHÔNG đụng Excel điều tra 2.2.3 / 2.2.4.")
    out(lines, "- Mục tiêu: xác định chính xác vì sao scope trường/năm = 0 và nguồn nào thực sự có thể cấp cho 7 biểu.")
    out(lines)

    if not DB_PATH.is_file():
        raise FileNotFoundError(f"Không tìm thấy database: {DB_PATH}")

    uri = DB_PATH.resolve().as_uri() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    try:
        out(lines, "=" * 124)
        out(lines, "0. AN TOÀN DATABASE")
        out(lines, "=" * 124)
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        fk = conn.execute("PRAGMA foreign_key_check").fetchall()
        out(lines, f"integrity_check: {integrity}")
        out(lines, f"foreign_key_check: {len(fk)} lỗi")
        out(lines)

        sy = fetchone_dict(conn, "SELECT * FROM school_years WHERE code=?", (TARGET_SCHOOL_YEAR_CODE,))
        commune = fetchone_dict(conn, "SELECT * FROM communes WHERE code=?", (TARGET_COMMUNE_CODE,))
        school = fetchone_dict(conn, "SELECT * FROM schools WHERE code=?", (TARGET_SCHOOL_CODE,))
        out(lines, "PHẠM VI MỤC TIÊU:")
        out(lines, f"Năm học: {sy}")
        out(lines, f"Xã/phường: {commune}")
        out(lines, f"Trường: {school}")
        if not sy or not commune or not school:
            raise RuntimeError("Không khóa được năm/xã/trường mục tiêu theo mã đã khảo sát ở V2.4.3.")

        sy_id = sy["id"]
        commune_id = commune["id"]
        school_id = school["id"]
        start_year = year_start(sy["code"])
        school_norm = norm(school["name"])

        out(lines)
        out(lines, "=" * 124)
        out(lines, "I. ĐỢT ĐIỀU TRA / PHIẾU CỦA XÃ TRONG NĂM")
        out(lines, "=" * 124)
        batches = fetchall_dict(
            conn,
            """SELECT id, code, name, status, is_locked
               FROM survey_batches
               WHERE school_year_id=? AND commune_id=?
               ORDER BY id""",
            (sy_id, commune_id),
        )
        out(lines, f"Số đợt: {len(batches)}")
        batch_ids = [r["id"] for r in batches]
        for r in batches:
            n_forms = safe_count(conn, "survey_forms", "survey_batch_id=?", (r["id"],))
            out(lines, f"  {r} | forms={n_forms}")
        if batch_ids:
            ph = ",".join("?" for _ in batch_ids)
            n_people = conn.execute(
                f"""SELECT COUNT(DISTINCT p.id) AS n
                    FROM survey_people p
                    JOIN households h ON h.id=p.household_id
                    JOIN survey_forms f ON f.household_id=h.id
                    WHERE f.survey_batch_id IN ({ph}) AND p.is_active=1""",
                batch_ids,
            ).fetchone()["n"]
            out(lines, f"Đối tượng hoạt động trong các đợt: {n_people}")

        out(lines)
        out(lines, "=" * 124)
        out(lines, "II. YEAR-RECORD NĂM 2026-2027 - PHÂN BỐ SCHOOL_ID / TÊN TRƯỜNG KHAI BÁO")
        out(lines, "=" * 124)
        rows = fetchall_dict(
            conn,
            """SELECT
                   yr.id AS year_record_id,
                   yr.survey_person_id,
                   yr.school_id,
                   s.code AS school_code,
                   s.name AS school_name_linked,
                   yr.school_name_reported,
                   yr.class_name_reported,
                   yr.learning_status,
                   yr.completed_preschool_by_age,
                   yr.completed_preschool_5,
                   yr.attends_two_sessions_per_day,
                   yr.prepared_vietnamese,
                   yr.disability_status,
                   yr.disability_type,
                   p.full_name,
                   p.date_of_birth,
                   p.gender,
                   p.ethnic_group,
                   p.residency_status,
                   h.commune_id AS household_commune_id,
                   h.hamlet_name,
                   f.survey_batch_id,
                   f.form_number
               FROM survey_person_year_records yr
               JOIN survey_people p ON p.id=yr.survey_person_id
               JOIN households h ON h.id=p.household_id
               LEFT JOIN schools s ON s.id=yr.school_id
               LEFT JOIN survey_forms f ON f.id=yr.survey_form_id
               WHERE yr.school_year_id=?
               ORDER BY yr.id""",
            (sy_id,),
        )
        out(lines, f"Tổng year-record của năm: {len(rows)}")

        by_school = Counter()
        by_reported = Counter()
        by_hh_commune = Counter()
        for r in rows:
            by_school[(r["school_id"], r["school_name_linked"])] += 1
            by_reported[r["school_name_reported"] or ""] += 1
            by_hh_commune[r["household_commune_id"]] += 1

        out(lines, "Theo school_id liên kết:")
        for key, n in by_school.most_common(40):
            out(lines, f"  {key}: {n}")
        out(lines, "Theo school_name_reported:")
        for key, n in by_reported.most_common(60):
            out(lines, f"  {key!r}: {n}")
        out(lines, "Theo commune của hộ:")
        for key, n in by_hh_commune.most_common():
            out(lines, f"  commune_id={key}: {n}")

        exact_link = [r for r in rows if r["school_id"] == school_id]
        report_match = [
            r for r in rows
            if r["school_name_reported"] and norm(r["school_name_reported"]) == school_norm
        ]
        name_contains = [
            r for r in rows
            if r["school_name_reported"]
            and ("nghi hoa" in norm(r["school_name_reported"]) or "nghihoa" in norm(r["school_name_reported"]).replace(" ", ""))
        ]
        hh_scope = [r for r in rows if r["household_commune_id"] == commune_id]

        out(lines)
        out(lines, f"Liên kết chính xác school_id={school_id}: {len(exact_link)}")
        out(lines, f"Khớp chuẩn hóa school_name_reported với '{school['name']}': {len(report_match)}")
        out(lines, f"Tên khai báo có dấu vết 'Nghi Hoa': {len(name_contains)}")
        out(lines, f"Year-record thuộc hộ cư trú tại commune_id={commune_id}: {len(hh_scope)}")

        def age_of(r):
            dob = r.get("date_of_birth")
            if not dob or not start_year:
                return None
            try:
                return start_year - int(str(dob)[:4])
            except Exception:
                return None

        for label, sample in [
            ("school_id chính xác", exact_link),
            ("khớp school_name_reported", report_match),
            ("dấu vết Nghi Hoa", name_contains),
            ("hộ thuộc xã", hh_scope),
        ]:
            age_counter = Counter(age_of(r) for r in sample)
            out(lines, f"Tuổi trong nhóm {label}: {dict(sorted(age_counter.items(), key=lambda x: (999 if x[0] is None else x[0])))}")
            age_0_6 = [r for r in sample if isinstance(age_of(r), int) and 0 <= age_of(r) <= 6]
            out(lines, f"  0-6 tuổi: {len(age_0_6)}")
            for r in age_0_6[:30]:
                out(lines, "    " + repr({
                    "year_record_id": r["year_record_id"],
                    "person_id": r["survey_person_id"],
                    "full_name": r["full_name"],
                    "dob": r["date_of_birth"],
                    "age": age_of(r),
                    "school_id": r["school_id"],
                    "school_linked": r["school_name_linked"],
                    "school_reported": r["school_name_reported"],
                    "class": r["class_name_reported"],
                    "learning_status": r["learning_status"],
                    "ctgdmn": r["completed_preschool_by_age"],
                    "hoc_2_buoi": r["attends_two_sessions_per_day"],
                    "kt": r["disability_status"],
                    "form_number": r["form_number"],
                }))

        out(lines)
        out(lines, "=" * 124)
        out(lines, "III. KIỂM TRA GIAO TRƯỜNG / GIAO PHIẾU")
        out(lines, "=" * 124)
        if batch_ids:
            ph = ",".join("?" for _ in batch_ids)
            if table_exists(conn, "survey_school_assignments"):
                assigns = fetchall_dict(
                    conn,
                    f"""SELECT * FROM survey_school_assignments
                        WHERE survey_batch_id IN ({ph}) AND school_id=?""",
                    (*batch_ids, school_id),
                )
                out(lines, f"survey_school_assignments của trường: {len(assigns)}")
                for r in assigns:
                    out(lines, "  " + repr(r))
            if table_exists(conn, "survey_form_investigators"):
                n = conn.execute(
                    f"""SELECT COUNT(DISTINCT fi.survey_form_id) AS n
                        FROM survey_form_investigators fi
                        JOIN survey_forms f ON f.id=fi.survey_form_id
                        JOIN users u ON u.id=fi.user_id
                        WHERE f.survey_batch_id IN ({ph}) AND u.school_id=?""",
                    (*batch_ids, school_id),
                ).fetchone()["n"]
                out(lines, f"Số phiếu có điều tra viên thuộc trường: {n}")

        out(lines)
        out(lines, "=" * 124)
        out(lines, "IV. NGUỒN MN-01-GV / LỚP")
        out(lines, "=" * 124)
        checks = [
            ("staff_year_records", "school_id=? AND school_year_id=?", (school_id, sy_id)),
            ("school_staff_year_summaries", "school_id=? AND school_year_id=?", (school_id, sy_id)),
            ("school_mn01_gv_inputs", "school_id=? AND school_year_id=?", (school_id, sy_id)),
            ("classes", "school_id=? AND school_year_id=?", (school_id, sy_id)),
        ]
        for table, where, params in checks:
            if table_exists(conn, table):
                out(lines, f"{table} current scope: {safe_count(conn, table, where, params)}")
                grouped = []
                if "school_year_id" in cols(conn, table):
                    grouped = fetchall_dict(
                        conn,
                        f"""SELECT school_year_id, COUNT(*) AS n
                            FROM {qident(table)}
                            WHERE school_id=?
                            GROUP BY school_year_id ORDER BY school_year_id""",
                        (school_id,),
                    )
                if grouped:
                    out(lines, f"  all years: {grouped}")

        if table_exists(conn, "staff_year_records"):
            pos = fetchall_dict(
                conn,
                """SELECT position_group, teaching_level, teaching_age_group,
                          qualification_level, qualification_standard, professional_standard,
                          COUNT(*) AS n
                   FROM staff_year_records
                   WHERE school_id=? AND school_year_id=? AND is_active=1
                   GROUP BY position_group, teaching_level, teaching_age_group,
                            qualification_level, qualification_standard, professional_standard
                   ORDER BY position_group, teaching_level, teaching_age_group""",
                (school_id, sy_id),
            )
            out(lines, "Nhóm staff current scope:")
            for r in pos:
                out(lines, "  " + repr(r))

        out(lines)
        out(lines, "=" * 124)
        out(lines, "V. NGUỒN MN-01-CSVC / MN-TC / STRUCTURED DATA")
        out(lines, "=" * 124)
        tables = [
            "school_mn01_csvc_inputs",
            "school_facility_year_items",
            "finance_year_entries",
            "school_structured_report_inputs",
            "school_network_year_data",
            "school_site_year_records",
            "school_class_year_attributes",
        ]
        for table in tables:
            if not table_exists(conn, table):
                out(lines, f"{table}: KHÔNG CÓ BẢNG")
                continue
            c = cols(conn, table)
            if "school_id" in c and "school_year_id" in c:
                n_now = safe_count(conn, table, "school_id=? AND school_year_id=?", (school_id, sy_id))
                out(lines, f"{table} current scope: {n_now}")
                grp = fetchall_dict(
                    conn,
                    f"""SELECT school_year_id, COUNT(*) AS n
                        FROM {qident(table)}
                        WHERE school_id=?
                        GROUP BY school_year_id ORDER BY school_year_id""",
                    (school_id,),
                )
                out(lines, f"  all years: {grp}")
            else:
                out(lines, f"{table}: columns={c}")

        if table_exists(conn, "school_structured_report_inputs"):
            grp = fetchall_dict(
                conn,
                """SELECT school_year_id, form_code, COUNT(*) AS n
                   FROM school_structured_report_inputs
                   WHERE school_id=?
                   GROUP BY school_year_id, form_code
                   ORDER BY school_year_id, form_code""",
                (school_id,),
            )
            out(lines, "school_structured_report_inputs theo form_code:")
            for r in grp:
                out(lines, "  " + repr(r))

        if table_exists(conn, "school_network_year_data"):
            grp = fetchall_dict(
                conn,
                """SELECT school_year_id, level_code, COUNT(*) AS n
                   FROM school_network_year_data
                   WHERE school_id=?
                   GROUP BY school_year_id, level_code
                   ORDER BY school_year_id, level_code""",
                (school_id,),
            )
            out(lines, "school_network_year_data theo level_code:")
            for r in grp:
                out(lines, "  " + repr(r))
            samples = fetchall_dict(
                conn,
                """SELECT id, school_year_id, level_code, source_name, substr(data_json,1,1500) AS data_json
                   FROM school_network_year_data
                   WHERE school_id=?
                   ORDER BY school_year_id DESC, id DESC LIMIT 10""",
                (school_id,),
            )
            for r in samples:
                out(lines, "  SAMPLE " + repr(r))

        if table_exists(conn, "finance_report_values"):
            out(lines, f"finance_report_values của commune hiện tại: {safe_count(conn,'finance_report_values','commune_id=?',(commune_id,))}")
            grp = fetchall_dict(
                conn,
                """SELECT report_year, COUNT(*) AS n
                   FROM finance_report_values
                   WHERE commune_id=?
                   GROUP BY report_year ORDER BY report_year""",
                (commune_id,),
            )
            out(lines, f"  theo năm: {grp}")

        out(lines)
        out(lines, "=" * 124)
        out(lines, "VI. SOURCE QUYẾT ĐỊNH SCOPE / 7 BIỂU")
        out(lines, "=" * 124)
        funcs = {
            ROOT / "app" / "routers" / "survey_summary_report.py": [
                "_load_batches",
                "_load_person_rows",
                "_finalize_people",
                "build_report_data",
            ],
            ROOT / "app" / "routers" / "pcgdmn_template_report.py": [
                "_load_staff_report_data",
                "_write_mn01_te",
                "_write_mn02",
                "_write_mn01_gv",
                "_write_disability_sheet",
                "_write_tracking_book",
                "_blank_future_modules",
                "build_template_workbook",
            ],
        }
        for path, names in funcs.items():
            out(lines)
            out(lines, f"[SOURCE] {path}")
            out(lines, f"Tồn tại: {'CÓ' if path.is_file() else 'KHÔNG'}")
            for name in names:
                block = extract_function(path, name)
                out(lines, "-" * 100)
                out(lines, f"{name}: {'CÓ' if block else 'KHÔNG TÌM THẤY'}")
                for ln, content in block:
                    out(lines, f"{ln:05d}: {content}")

        out(lines)
        out(lines, "=" * 124)
        out(lines, "VII. KẾT LUẬN TỰ ĐỘNG")
        out(lines, "=" * 124)

        if len(exact_link) == 0 and len(report_match) > 0:
            out(lines, "KẾT LUẬN A: Có dữ liệu khai báo đúng tên trường nhưng school_id chưa liên kết.")
            out(lines, "=> V2.4.3 thật có thể dùng fallback tên trường CHỈ khi school_id trống, không ghi ngược dữ liệu.")
        elif len(exact_link) == 0 and len(name_contains) > 0:
            out(lines, "KẾT LUẬN A: Có tên trường gần khớp Nghi Hoa nhưng không khớp chuẩn hóa hoàn toàn.")
            out(lines, "=> Cần xem mẫu tên cụ thể trước khi cho phép fallback; KHÔNG tự fuzzy-match khi ghi báo cáo.")
        elif len(exact_link) == 0:
            out(lines, "KẾT LUẬN A: Không có year-record nào liên kết với Trường Mầm non Nghi Hoa trong năm 2026-2027.")
            out(lines, "=> Nếu báo cáo trường cần có trẻ, phải xác định nghiệp vụ lấy theo địa bàn điều tra hay theo tên trường khai báo; chưa được tự suy diễn.")
        else:
            out(lines, f"KẾT LUẬN A: Có {len(exact_link)} year-record liên kết chính xác với trường.")

        if safe_count(conn, "school_mn01_csvc_inputs", "school_id=? AND school_year_id=?", (school_id, sy_id)) == 0:
            out(lines, "KẾT LUẬN B: Chưa có bản ghi school_mn01_csvc_inputs cho trường/năm mục tiêu.")
        if safe_count(conn, "finance_year_entries", "school_id=? AND school_year_id=?", (school_id, sy_id)) == 0:
            out(lines, "KẾT LUẬN C: Chưa có finance_year_entries cho trường/năm mục tiêu.")
        out(lines, "KẾT LUẬN D: Không được tạo số liệu giả. Chỉ nối nguồn có thật và sửa năm/mapping sau khi khóa scope.")
        out(lines, "KẾT LUẬN E: Excel điều tra 2.2.3/2.2.4 không thuộc phạm vi sửa.")

    finally:
        conn.close()

    EXPORTS.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
    print()
    print("=" * 124)
    print("BÀI 13B-12 V2.4.3.1 - KHẢO SÁT CHỈ ĐỌC")
    print("=" * 124)
    print("ĐÃ TẠO BÁO CÁO:")
    print(REPORT)
    print()
    print("Không có source/database nào bị sửa.")
    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print()
        print("KHẢO SÁT GẶP LỖI - KHÔNG CÓ DỮ LIỆU/SOURCE NÀO BỊ SỬA.")
        print(type(exc).__name__ + ":", exc)
        raise
