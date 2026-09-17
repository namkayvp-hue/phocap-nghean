# -*- coding: utf-8 -*-
r"""
DRY-RUN V6 - KIỂM TRA ĐỘI NGŨ SAU SÁP NHẬP QĐ 3805 - NGHI LỘC
===============================================================

MỤC TIÊU
--------
- CHỈ ĐỌC database hiện tại và backup trước sáp nhập.
- KHÔNG SỬA phocap.db.
- Kiểm tra toàn bộ ĐỘI NGŨ theo 3 nhóm:
    1) Cán bộ quản lý / quản lý
    2) Giáo viên
    3) Nhân viên
- Đối chiếu trường nguồn -> trường đích sau sáp nhập.
- Xác định:
    + số hồ sơ năm 2026-2027 hiện có tại trường đích;
    + số hồ sơ năm 2025-2026 của trường nguồn cần xem xét kế thừa;
    + hồ sơ nào đã có ở trường đích;
    + hồ sơ nào chưa có ở trường đích;
    + hồ sơ nào có dấu hiệu trùng;
    + hồ sơ nào nghỉ/chuyển/ngừng làm việc nếu schema có trạng thái.
- Ưu tiên khóa đối chiếu theo staff_id/person_id/employee_id.
- Nếu không có khóa ổn định thì dùng mã nhân sự; cuối cùng mới dùng họ tên chuẩn hóa.
- Tạo báo cáo để viết V7 kế thừa đội ngũ 2026-2027.

NGUYÊN TẮC HỆ THỐNG
-------------------
- Lịch sử năm cũ GIỮ NGUYÊN tại trường cũ.
- Năm học hiện hành phải GỘP/KẾ THỪA dữ liệu hợp lệ sang trường đích.
- Không tạo trùng.
- Không tự mang người đã nghỉ/chuyển/ngừng làm việc sang năm hiện hành.
- DRY-RUN V6 KHÔNG THAY ĐỔI DATABASE.

CHẠY:
    cd C:\PhoCap
    .\.venv\Scripts\python.exe .\kiem_tra_doi_ngu_sau_sap_nhap_QD3805_Nghi_Loc_v6.py

KẾT QUẢ:
    C:\PhoCap\dry_run_doi_ngu_QD3805_Nghi_Loc_v6_<timestamp>.zip
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

TARGET_YEAR_ID = 2
TARGET_YEAR_LABEL = "2026-2027"
PREVIOUS_YEAR_LABEL = "2025-2026"

MERGE_MAP = {
    750: 748,    # MN Nghi Hoa -> MN Nghi Dien
    751: 748,    # MN Nghi Van -> MN Nghi Dien
    749: 747,    # MN Nghi Trung -> MN TT Quan Hanh
    1181: 1178,  # TH Nghi Van -> TH Nghi Dien
    1180: 1179,  # TH Nghi Hoa -> TH Nghi Trung
    1608: 1605,  # THCS Nghi Van -> THCS Nghi Dien
    1607: 1606,  # THCS Nghi Hoa -> THCS Nghi Trung
}

SOURCE_IDS = tuple(sorted(MERGE_MAP))
TARGET_IDS = tuple(sorted(set(MERGE_MAP.values())))


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


def first_existing(cs: set[str], names: tuple[str, ...]) -> str | None:
    for n in names:
        if n in cs:
            return n
    return None


def normalize_text(value) -> str:
    if value is None:
        return ""
    s = str(value).strip().lower()
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())


def classify_staff(*values) -> str:
    text = " ".join(normalize_text(v) for v in values if v not in (None, ""))
    if not text:
        return "CHUA_XAC_DINH"

    # Nhân viên trước, vì có thể chứa từ "giáo vụ"...
    employee_terms = (
        "nhan vien", "ke toan", "van thu", "thu vien", "thiet bi",
        "y te", "bao ve", "phuc vu", "cap duong", "thu quy",
        "employee", "staff employee"
    )
    if any(t in text for t in employee_terms):
        return "NHAN_VIEN"

    manager_terms = (
        "hieu truong", "pho hieu truong", "can bo quan ly", "cbql",
        "principal", "vice principal", "manager", "management"
    )
    if any(t in text for t in manager_terms):
        return "QUAN_LY"

    teacher_terms = (
        "giao vien", "teacher", "gv", "giang day"
    )
    if any(t in text for t in teacher_terms):
        return "GIAO_VIEN"

    return "CHUA_XAC_DINH"


def is_inactive_status(*values) -> tuple[bool, str]:
    """
    Chỉ đánh dấu khi văn bản thể hiện khá rõ đã nghỉ/chuyển/ngừng.
    """
    text = " ".join(normalize_text(v) for v in values if v not in (None, ""))
    inactive_terms = (
        "nghi viec", "da nghi", "thoi viec", "chuyen di", "da chuyen",
        "ngung lam viec", "khong lam viec", "inactive", "resigned",
        "retired", "nghi huu", "terminated"
    )
    for t in inactive_terms:
        if t in text:
            return True, t
    return False, ""


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


def write_csv(path: Path, headers: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def school_names(conn: sqlite3.Connection) -> dict[int, str]:
    if not table_exists(conn, "schools"):
        return {}
    cs = colset(conn, "schools")
    name_col = first_existing(cs, ("name", "school_name", "ten_truong"))
    if not name_col:
        return {}
    ids = sorted(set(SOURCE_IDS) | set(TARGET_IDS))
    rows = conn.execute(
        f"SELECT id, {qident(name_col)} FROM schools "
        f"WHERE id IN ({markers(len(ids))})",
        ids,
    ).fetchall()
    return {int(r[0]): str(r[1]) for r in rows}


def detect_school_years(conn: sqlite3.Connection) -> tuple[int, int, list[dict]]:
    if not table_exists(conn, "school_years"):
        raise AuditAbort("Không có bảng school_years.")
    cs = colset(conn, "school_years")
    if "id" not in cs:
        raise AuditAbort("school_years không có id.")

    label_col = first_existing(
        cs, ("name", "label", "school_year", "year_name")
    )
    if not label_col:
        raise AuditAbort("Không xác định được cột tên năm học.")

    rows = conn.execute(
        f"SELECT id, {qident(label_col)} AS label FROM school_years ORDER BY id"
    ).fetchall()

    report = [{"id": r["id"], "label": r["label"]} for r in rows]

    target_id = None
    previous_id = None
    for r in rows:
        label = str(r["label"] or "")
        norm = label.replace("–", "-").replace("—", "-")
        if "2026" in norm and "2027" in norm:
            target_id = int(r["id"])
        if "2025" in norm and "2026" in norm:
            previous_id = int(r["id"])

    if target_id is None:
        target_id = TARGET_YEAR_ID

    if previous_id is None:
        # Nếu không tìm được bằng nhãn, lấy ID lớn nhất nhỏ hơn target.
        smaller = [int(r["id"]) for r in rows if int(r["id"]) < target_id]
        if smaller:
            previous_id = max(smaller)

    if previous_id is None:
        raise AuditAbort("Không xác định được năm học 2025-2026.")

    return target_id, previous_id, report


def detect_staff_year_table(conn: sqlite3.Connection) -> str:
    candidates = (
        "staff_year_records",
        "staff_year_record",
        "staff_records",
        "school_staff_year_records",
    )
    for t in candidates:
        if table_exists(conn, t):
            cs = colset(conn, t)
            if {"school_id", "school_year_id"} <= cs:
                return t

    # Dò rộng.
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    for r in rows:
        t = r[0]
        cs = colset(conn, t)
        if {"school_id", "school_year_id"} <= cs and (
            "staff" in t.lower()
            or "teacher" in t.lower()
            or "personnel" in t.lower()
            or "nhan_su" in t.lower()
        ):
            return t

    raise AuditAbort(
        "Không tìm thấy bảng đội ngũ có school_id + school_year_id."
    )


def detect_staff_master(
    conn: sqlite3.Connection,
    year_table: str,
) -> tuple[str | None, str | None, str | None]:
    """
    Trả về (master_table, from_col_in_year, to_col_in_master).
    """
    for fk in foreign_keys(conn, year_table):
        if fk["ref_table"] in ("schools", "school_years"):
            continue
        low = fk["ref_table"].lower()
        if any(k in low for k in ("staff", "teacher", "personnel", "employee")):
            return fk["ref_table"], fk["from_col"], fk["to_col"]

    cs = colset(conn, year_table)
    for from_col, tables in (
        ("staff_id", ("staff", "staffs")),
        ("person_id", ("staff", "staffs", "persons")),
        ("employee_id", ("staff", "staffs", "employees")),
    ):
        if from_col in cs:
            for t in tables:
                if table_exists(conn, t) and "id" in colset(conn, t):
                    return t, from_col, "id"

    return None, None, None


def build_field_map(
    conn: sqlite3.Connection,
    year_table: str,
    master_table: str | None,
) -> dict:
    ycs = colset(conn, year_table)
    mcs = colset(conn, master_table) if master_table else set()

    def pick(*names):
        for n in names:
            if n in ycs:
                return ("Y", n)
            if n in mcs:
                return ("M", n)
        return (None, None)

    return {
        "full_name": pick(
            "full_name", "fullname", "name", "staff_name", "ho_ten", "employee_name"
        ),
        "staff_code": pick(
            "staff_code", "employee_code", "person_code", "code", "ma_nhan_su"
        ),
        "position": pick(
            "position", "position_name", "job_position", "position_type",
            "chuc_vu", "vi_tri_viec_lam"
        ),
        "job_title": pick(
            "job_title", "title", "professional_title", "chuc_danh"
        ),
        "staff_type": pick(
            "staff_type", "staff_category", "personnel_type", "employee_type",
            "role", "role_name", "type"
        ),
        "status": pick(
            "status", "employment_status", "work_status", "state"
        ),
        "is_active": pick(
            "is_active", "active", "working", "is_working"
        ),
    }


def row_value(
    year_row: sqlite3.Row,
    master_row: sqlite3.Row | None,
    spec: tuple[str | None, str | None],
):
    src, col = spec
    if src == "Y" and col:
        return year_row[col]
    if src == "M" and col and master_row is not None:
        return master_row[col]
    return ""


def stable_key_info(
    year_row: sqlite3.Row,
    master_row: sqlite3.Row | None,
    year_table_cols: set[str],
    field_map: dict,
) -> tuple[str, str]:
    """
    Trả (key_type, key_value)
    """
    for c in ("staff_id", "person_id", "employee_id"):
        if c in year_table_cols and year_row[c] is not None:
            return c.upper(), str(year_row[c])

    code = row_value(year_row, master_row, field_map["staff_code"])
    if code not in (None, ""):
        return "STAFF_CODE", normalize_text(code)

    name = row_value(year_row, master_row, field_map["full_name"])
    if name not in (None, ""):
        return "NORMALIZED_NAME", normalize_text(name)

    # Cuối cùng dùng year record id nếu có, nhưng không xem là key nối năm đáng tin.
    if "id" in year_table_cols:
        return "YEAR_RECORD_ID_ONLY", str(year_row["id"])

    return "NO_KEY", ""


def fetch_master_row(
    conn: sqlite3.Connection,
    master_table: str | None,
    to_col: str | None,
    from_value,
) -> sqlite3.Row | None:
    if not master_table or not to_col or from_value is None:
        return None
    row = conn.execute(
        f"SELECT * FROM {qident(master_table)} WHERE {qident(to_col)}=? LIMIT 1",
        (from_value,),
    ).fetchone()
    return row


def extract_records(
    conn: sqlite3.Connection,
    year_table: str,
    master_table: str | None,
    from_col: str | None,
    to_col: str | None,
    field_map: dict,
    school_ids: tuple[int, ...],
    year_id: int,
) -> list[dict]:
    ycs = colset(conn, year_table)
    rows = conn.execute(
        f"SELECT * FROM {qident(year_table)} "
        f"WHERE school_id IN ({markers(len(school_ids))}) AND school_year_id=? "
        "ORDER BY school_id, id" if "id" in ycs else
        f"SELECT * FROM {qident(year_table)} "
        f"WHERE school_id IN ({markers(len(school_ids))}) AND school_year_id=? "
        "ORDER BY school_id",
        list(school_ids) + [year_id],
    ).fetchall()

    out = []
    for y in rows:
        m = None
        if master_table and from_col and from_col in ycs:
            m = fetch_master_row(
                conn, master_table, to_col, y[from_col]
            )

        key_type, key_value = stable_key_info(
            y, m, ycs, field_map
        )

        full_name = row_value(y, m, field_map["full_name"])
        staff_code = row_value(y, m, field_map["staff_code"])
        position = row_value(y, m, field_map["position"])
        job_title = row_value(y, m, field_map["job_title"])
        staff_type = row_value(y, m, field_map["staff_type"])
        status = row_value(y, m, field_map["status"])
        active_raw = row_value(y, m, field_map["is_active"])

        category = classify_staff(position, job_title, staff_type)
        inactive, inactive_reason = is_inactive_status(
            status, active_raw, position, job_title
        )
        if active_raw in (0, False, "0", "false", "False"):
            inactive = True
            if not inactive_reason:
                inactive_reason = "is_active=0"

        out.append({
            "year_record_id": y["id"] if "id" in ycs else "",
            "school_id": y["school_id"],
            "school_year_id": y["school_year_id"],
            "stable_key_type": key_type,
            "stable_key_value": key_value,
            "full_name": "" if full_name is None else str(full_name),
            "staff_code": "" if staff_code is None else str(staff_code),
            "position": "" if position is None else str(position),
            "job_title": "" if job_title is None else str(job_title),
            "staff_type": "" if staff_type is None else str(staff_type),
            "status": "" if status is None else str(status),
            "active_raw": "" if active_raw is None else str(active_raw),
            "category": category,
            "inactive_flag": "YES" if inactive else "NO",
            "inactive_reason": inactive_reason,
        })

    return out


def category_counts(rows: list[dict]) -> dict[str, int]:
    c = Counter(r["category"] for r in rows)
    return {
        "QUAN_LY": c.get("QUAN_LY", 0),
        "GIAO_VIEN": c.get("GIAO_VIEN", 0),
        "NHAN_VIEN": c.get("NHAN_VIEN", 0),
        "CHUA_XAC_DINH": c.get("CHUA_XAC_DINH", 0),
        "TOTAL": len(rows),
    }


def audit() -> None:
    print("=" * 108)
    print("DRY-RUN V6 - KIỂM TRA ĐỘI NGŨ SAU SÁP NHẬP QĐ 3805 - NGHI LỘC")
    print("=" * 108)
    print("Chế độ: CHỈ ĐỌC - KHÔNG SỬA DATABASE")

    if not CURRENT_DB.exists():
        raise AuditAbort(f"Không tìm thấy current DB: {CURRENT_DB}")

    backup_db = find_backup()
    cur = connect_ro(CURRENT_DB)
    bak = connect_ro(backup_db)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = PROJECT_ROOT / f"dry_run_doi_ngu_QD3805_Nghi_Loc_v6_{ts}"
    out_dir.mkdir(parents=True, exist_ok=False)

    try:
        int_cur = cur.execute("PRAGMA integrity_check").fetchone()[0]
        int_bak = bak.execute("PRAGMA integrity_check").fetchone()[0]
        if int_cur != "ok":
            raise AuditAbort(f"Current DB integrity_check={int_cur}")
        if int_bak != "ok":
            raise AuditAbort(f"Backup DB integrity_check={int_bak}")

        target_year_id, previous_year_id, year_rows = detect_school_years(cur)

        year_table = detect_staff_year_table(cur)
        if not table_exists(bak, year_table):
            raise AuditAbort(
                f"Backup trước sáp nhập không có bảng {year_table}."
            )

        master_table, from_col, to_col = detect_staff_master(cur, year_table)
        field_map = build_field_map(cur, year_table, master_table)

        names_cur = school_names(cur)
        names_bak = school_names(bak)

        # Hiện tại tại các target, năm 2026-2027.
        target_current = extract_records(
            cur, year_table, master_table, from_col, to_col,
            field_map, TARGET_IDS, target_year_id
        )

        # Nguồn trong backup, năm 2025-2026.
        source_previous = extract_records(
            bak, year_table, master_table, from_col, to_col,
            field_map, SOURCE_IDS, previous_year_id
        )

        # Nguồn trong backup, năm 2026-2027 nếu có.
        source_target_before = extract_records(
            bak, year_table, master_table, from_col, to_col,
            field_map, SOURCE_IDS, target_year_id
        )

        # Dữ liệu target trước sáp nhập, năm 2026-2027.
        target_current_before = extract_records(
            bak, year_table, master_table, from_col, to_col,
            field_map, TARGET_IDS, target_year_id
        )

        target_by_school = defaultdict(list)
        target_index_by_school_key = defaultdict(lambda: defaultdict(list))
        for r in target_current:
            sid = int(r["school_id"])
            target_by_school[sid].append(r)
            if r["stable_key_value"]:
                target_index_by_school_key[sid][
                    (r["stable_key_type"], r["stable_key_value"])
                ].append(r)

        source_prev_by_school = defaultdict(list)
        for r in source_previous:
            source_prev_by_school[int(r["school_id"])].append(r)

        # Kế hoạch kế thừa từng hồ sơ nguồn 2025-2026.
        inheritance = []
        duplicates = []
        for source_id, target_id in MERGE_MAP.items():
            for r in source_prev_by_school[source_id]:
                matches = []
                if r["stable_key_value"]:
                    matches = target_index_by_school_key[target_id].get(
                        (r["stable_key_type"], r["stable_key_value"]), []
                    )

                if r["inactive_flag"] == "YES":
                    action = "KEEP_HISTORY_DO_NOT_INHERIT_INACTIVE"
                    reason = (
                        f"Phát hiện trạng thái nghỉ/chuyển/ngừng: {r['inactive_reason']}"
                    )
                elif len(matches) == 0:
                    action = "CANDIDATE_INHERIT_TO_2026_2027"
                    reason = "Chưa có hồ sơ tương ứng tại trường đích năm 2026-2027."
                elif len(matches) == 1:
                    action = "ALREADY_PRESENT_AT_TARGET"
                    reason = "Đã có đúng 1 hồ sơ tương ứng tại trường đích."
                else:
                    action = "REVIEW_DUPLICATE_AT_TARGET"
                    reason = f"Có {len(matches)} hồ sơ cùng khóa tại trường đích."
                    duplicates.append({
                        "source_school_id": source_id,
                        "target_school_id": target_id,
                        "stable_key_type": r["stable_key_type"],
                        "stable_key_value": r["stable_key_value"],
                        "full_name": r["full_name"],
                        "match_count": len(matches),
                        "match_record_ids": ",".join(
                            str(x["year_record_id"]) for x in matches
                        ),
                    })

                inheritance.append({
                    **r,
                    "source_school_id": source_id,
                    "source_school_name": names_bak.get(source_id, ""),
                    "target_school_id": target_id,
                    "target_school_name": names_cur.get(target_id, ""),
                    "target_match_count": len(matches),
                    "target_match_record_ids": ",".join(
                        str(x["year_record_id"]) for x in matches
                    ),
                    "proposed_action": action,
                    "reason": reason,
                })

        # Tổng hợp theo cặp trường.
        pair_summary = []
        for source_id, target_id in MERGE_MAP.items():
            src_prev = source_prev_by_school[source_id]
            tgt_now = target_by_school[target_id]
            candidates = [
                x for x in inheritance
                if x["source_school_id"] == source_id
                and x["proposed_action"] == "CANDIDATE_INHERIT_TO_2026_2027"
            ]
            already = [
                x for x in inheritance
                if x["source_school_id"] == source_id
                and x["proposed_action"] == "ALREADY_PRESENT_AT_TARGET"
            ]
            inactive = [
                x for x in inheritance
                if x["source_school_id"] == source_id
                and x["proposed_action"] == "KEEP_HISTORY_DO_NOT_INHERIT_INACTIVE"
            ]
            review = [
                x for x in inheritance
                if x["source_school_id"] == source_id
                and x["proposed_action"] == "REVIEW_DUPLICATE_AT_TARGET"
            ]

            src_counts = category_counts(src_prev)
            tgt_counts = category_counts(tgt_now)
            cand_counts = category_counts(candidates)

            pair_summary.append({
                "source_school_id": source_id,
                "source_school_name": names_bak.get(source_id, ""),
                "target_school_id": target_id,
                "target_school_name": names_cur.get(target_id, ""),
                "source_prev_total": src_counts["TOTAL"],
                "source_prev_quan_ly": src_counts["QUAN_LY"],
                "source_prev_giao_vien": src_counts["GIAO_VIEN"],
                "source_prev_nhan_vien": src_counts["NHAN_VIEN"],
                "source_prev_chua_xac_dinh": src_counts["CHUA_XAC_DINH"],
                "target_2026_2027_total_now": tgt_counts["TOTAL"],
                "target_2026_2027_quan_ly_now": tgt_counts["QUAN_LY"],
                "target_2026_2027_giao_vien_now": tgt_counts["GIAO_VIEN"],
                "target_2026_2027_nhan_vien_now": tgt_counts["NHAN_VIEN"],
                "target_2026_2027_chua_xac_dinh_now": tgt_counts["CHUA_XAC_DINH"],
                "candidate_inherit_total": len(candidates),
                "candidate_inherit_quan_ly": cand_counts["QUAN_LY"],
                "candidate_inherit_giao_vien": cand_counts["GIAO_VIEN"],
                "candidate_inherit_nhan_vien": cand_counts["NHAN_VIEN"],
                "candidate_inherit_chua_xac_dinh": cand_counts["CHUA_XAC_DINH"],
                "already_present": len(already),
                "inactive_not_inherit": len(inactive),
                "duplicate_review": len(review),
                "projected_total_after_inherit": len(tgt_now) + len(candidates),
            })

        # Tổng hợp theo target sau khi nhận nhiều source.
        target_summary = []
        for target_id in TARGET_IDS:
            tgt_now = target_by_school[target_id]
            incoming = [
                x for x in inheritance
                if x["target_school_id"] == target_id
                and x["proposed_action"] == "CANDIDATE_INHERIT_TO_2026_2027"
            ]
            all_after = tgt_now + incoming

            now_counts = category_counts(tgt_now)
            incoming_counts = category_counts(incoming)
            after_counts = category_counts(all_after)

            target_summary.append({
                "target_school_id": target_id,
                "target_school_name": names_cur.get(target_id, ""),
                "current_total": now_counts["TOTAL"],
                "current_quan_ly": now_counts["QUAN_LY"],
                "current_giao_vien": now_counts["GIAO_VIEN"],
                "current_nhan_vien": now_counts["NHAN_VIEN"],
                "incoming_candidate_total": incoming_counts["TOTAL"],
                "incoming_quan_ly": incoming_counts["QUAN_LY"],
                "incoming_giao_vien": incoming_counts["GIAO_VIEN"],
                "incoming_nhan_vien": incoming_counts["NHAN_VIEN"],
                "projected_total": after_counts["TOTAL"],
                "projected_quan_ly": after_counts["QUAN_LY"],
                "projected_giao_vien": after_counts["GIAO_VIEN"],
                "projected_nhan_vien": after_counts["NHAN_VIEN"],
                "projected_chua_xac_dinh": after_counts["CHUA_XAC_DINH"],
            })

        # Schema reports.
        schema_year = columns(cur, year_table)
        fk_year = foreign_keys(cur, year_table)
        schema_master = columns(cur, master_table) if master_table else []

        field_map_rows = [
            {
                "logical_field": k,
                "source": v[0] or "",
                "column": v[1] or "",
            }
            for k, v in field_map.items()
        ]

        # Cổng an toàn cho V7.
        no_key = [x for x in inheritance if x["stable_key_type"] in ("NO_KEY", "YEAR_RECORD_ID_ONLY")]
        unclassified_candidates = [
            x for x in inheritance
            if x["proposed_action"] == "CANDIDATE_INHERIT_TO_2026_2027"
            and x["category"] == "CHUA_XAC_DINH"
        ]
        duplicate_review = [
            x for x in inheritance
            if x["proposed_action"] == "REVIEW_DUPLICATE_AT_TARGET"
        ]

        gate_checks = [
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
                "check": "target_year_identified",
                "result": "PASS",
                "detail": f"target_year_id={target_year_id}",
            },
            {
                "check": "previous_year_identified",
                "result": "PASS",
                "detail": f"previous_year_id={previous_year_id}",
            },
            {
                "check": "stable_key_available_for_inheritance",
                "result": "PASS" if not no_key else "FAIL",
                "detail": f"weak_or_missing_key_rows={len(no_key)}",
            },
            {
                "check": "no_duplicate_matches_at_target",
                "result": "PASS" if not duplicate_review else "FAIL",
                "detail": f"duplicate_review_rows={len(duplicate_review)}",
            },
            {
                "check": "all_candidate_rows_classified",
                "result": "PASS" if not unclassified_candidates else "FAIL",
                "detail": f"unclassified_candidates={len(unclassified_candidates)}",
            },
        ]
        safe = all(x["result"] == "PASS" for x in gate_checks)

        write_csv(
            out_dir / "80_SCHOOL_YEARS.csv",
            ["id", "label"],
            year_rows,
        )
        write_csv(
            out_dir / "81_SCHEMA_BANG_DOI_NGU_NAM.csv",
            ["cid", "name", "type", "notnull", "default", "pk"],
            schema_year,
        )
        write_csv(
            out_dir / "82_FOREIGN_KEYS_BANG_DOI_NGU_NAM.csv",
            ["id", "seq", "ref_table", "from_col", "to_col", "on_update", "on_delete"],
            fk_year,
        )
        write_csv(
            out_dir / "83_SCHEMA_BANG_NHAN_SU_GOC.csv",
            ["cid", "name", "type", "notnull", "default", "pk"],
            schema_master,
        )
        write_csv(
            out_dir / "84_FIELD_MAP_DOI_NGU.csv",
            ["logical_field", "source", "column"],
            field_map_rows,
        )
        write_csv(
            out_dir / "85_TARGET_2026_2027_HIEN_TAI.csv",
            [
                "year_record_id", "school_id", "school_year_id",
                "stable_key_type", "stable_key_value",
                "full_name", "staff_code", "position", "job_title",
                "staff_type", "status", "active_raw",
                "category", "inactive_flag", "inactive_reason",
            ],
            target_current,
        )
        write_csv(
            out_dir / "86_SOURCE_2025_2026_LICH_SU.csv",
            [
                "year_record_id", "school_id", "school_year_id",
                "stable_key_type", "stable_key_value",
                "full_name", "staff_code", "position", "job_title",
                "staff_type", "status", "active_raw",
                "category", "inactive_flag", "inactive_reason",
            ],
            source_previous,
        )
        write_csv(
            out_dir / "87_SOURCE_2026_2027_TRUOC_SAP_NHAP.csv",
            [
                "year_record_id", "school_id", "school_year_id",
                "stable_key_type", "stable_key_value",
                "full_name", "staff_code", "position", "job_title",
                "staff_type", "status", "active_raw",
                "category", "inactive_flag", "inactive_reason",
            ],
            source_target_before,
        )
        write_csv(
            out_dir / "88_TARGET_2026_2027_TRUOC_SAP_NHAP.csv",
            [
                "year_record_id", "school_id", "school_year_id",
                "stable_key_type", "stable_key_value",
                "full_name", "staff_code", "position", "job_title",
                "staff_type", "status", "active_raw",
                "category", "inactive_flag", "inactive_reason",
            ],
            target_current_before,
        )
        write_csv(
            out_dir / "89_KE_HOACH_KE_THUA_DOI_NGU.csv",
            [
                "year_record_id",
                "source_school_id", "source_school_name",
                "target_school_id", "target_school_name",
                "school_year_id",
                "stable_key_type", "stable_key_value",
                "full_name", "staff_code", "position", "job_title",
                "staff_type", "status", "active_raw",
                "category", "inactive_flag", "inactive_reason",
                "target_match_count", "target_match_record_ids",
                "proposed_action", "reason",
            ],
            inheritance,
        )
        write_csv(
            out_dir / "90_TONG_HOP_THEO_CAP_TRUONG_NGUON_DICH.csv",
            [
                "source_school_id", "source_school_name",
                "target_school_id", "target_school_name",
                "source_prev_total",
                "source_prev_quan_ly", "source_prev_giao_vien",
                "source_prev_nhan_vien", "source_prev_chua_xac_dinh",
                "target_2026_2027_total_now",
                "target_2026_2027_quan_ly_now",
                "target_2026_2027_giao_vien_now",
                "target_2026_2027_nhan_vien_now",
                "target_2026_2027_chua_xac_dinh_now",
                "candidate_inherit_total",
                "candidate_inherit_quan_ly",
                "candidate_inherit_giao_vien",
                "candidate_inherit_nhan_vien",
                "candidate_inherit_chua_xac_dinh",
                "already_present", "inactive_not_inherit",
                "duplicate_review", "projected_total_after_inherit",
            ],
            pair_summary,
        )
        write_csv(
            out_dir / "91_TONG_HOP_TRUONG_DICH_SAU_KE_THUA.csv",
            [
                "target_school_id", "target_school_name",
                "current_total", "current_quan_ly",
                "current_giao_vien", "current_nhan_vien",
                "incoming_candidate_total", "incoming_quan_ly",
                "incoming_giao_vien", "incoming_nhan_vien",
                "projected_total", "projected_quan_ly",
                "projected_giao_vien", "projected_nhan_vien",
                "projected_chua_xac_dinh",
            ],
            target_summary,
        )
        write_csv(
            out_dir / "92_TRUNG_CAN_XEM.csv",
            [
                "source_school_id", "target_school_id",
                "stable_key_type", "stable_key_value",
                "full_name", "match_count", "match_record_ids",
            ],
            duplicates,
        )
        write_csv(
            out_dir / "93_CONG_AN_TOAN_V7.csv",
            ["check", "result", "detail"],
            gate_checks,
        )

        summary = out_dir / "00_TONG_QUAN_V6.txt"
        with summary.open("w", encoding="utf-8") as f:
            f.write("DRY-RUN V6 - KIỂM TRA ĐỘI NGŨ SAU SÁP NHẬP QĐ 3805 - NGHI LỘC\n")
            f.write("=" * 108 + "\n")
            f.write("CHẾ ĐỘ: CHỈ ĐỌC - KHÔNG SỬA DATABASE\n")
            f.write(f"Current DB: {CURRENT_DB}\n")
            f.write(f"Backup DB : {backup_db}\n")
            f.write(f"Bảng đội ngũ theo năm: {year_table}\n")
            f.write(f"Bảng nhân sự gốc: {master_table or 'KHÔNG XÁC ĐỊNH'}\n")
            f.write(f"Năm đích: {target_year_id} ({TARGET_YEAR_LABEL})\n")
            f.write(f"Năm trước: {previous_year_id} ({PREVIOUS_YEAR_LABEL})\n\n")

            f.write("1. TỔNG HỢP THEO TRƯỜNG ĐÍCH\n")
            for r in target_summary:
                f.write(
                    f"- {r['target_school_id']} {r['target_school_name']}: "
                    f"hiện tại={r['current_total']} "
                    f"(QL={r['current_quan_ly']}, GV={r['current_giao_vien']}, NV={r['current_nhan_vien']}); "
                    f"dự kiến nhận thêm={r['incoming_candidate_total']} "
                    f"(QL={r['incoming_quan_ly']}, GV={r['incoming_giao_vien']}, NV={r['incoming_nhan_vien']}); "
                    f"sau kế thừa={r['projected_total']} "
                    f"(QL={r['projected_quan_ly']}, GV={r['projected_giao_vien']}, NV={r['projected_nhan_vien']}).\n"
                )

            f.write("\n2. CÁC HỒ SƠ NGUỒN 2025-2026\n")
            f.write(f"- Tổng hồ sơ lịch sử nguồn: {len(source_previous)}\n")
            f.write(
                f"- Ứng viên kế thừa: "
                f"{sum(x['proposed_action']=='CANDIDATE_INHERIT_TO_2026_2027' for x in inheritance)}\n"
            )
            f.write(
                f"- Đã có tại trường đích: "
                f"{sum(x['proposed_action']=='ALREADY_PRESENT_AT_TARGET' for x in inheritance)}\n"
            )
            f.write(
                f"- Nghỉ/chuyển/ngừng, không kế thừa tự động: "
                f"{sum(x['proposed_action']=='KEEP_HISTORY_DO_NOT_INHERIT_INACTIVE' for x in inheritance)}\n"
            )
            f.write(
                f"- Cần xem trùng: "
                f"{sum(x['proposed_action']=='REVIEW_DUPLICATE_AT_TARGET' for x in inheritance)}\n"
            )

            f.write("\n3. CỔNG AN TOÀN V7\n")
            for g in gate_checks:
                f.write(f"- [{g['result']}] {g['check']}: {g['detail']}\n")

            f.write("\nKẾT LUẬN\n")
            f.write(f"SAFE_TO_BUILD_V7 = {'YES' if safe else 'NO'}\n")
            f.write(
                "- V6 chỉ kiểm tra. Chưa tạo hồ sơ 2026-2027 mới và chưa sửa database.\n"
            )
            f.write(
                "- Sau khi xác nhận V6, V7 mới thực hiện kế thừa/gộp CBQL + giáo viên + nhân viên.\n"
            )

        zip_path = PROJECT_ROOT / (
            f"dry_run_doi_ngu_QD3805_Nghi_Loc_v6_{ts}.zip"
        )
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for p in sorted(out_dir.iterdir()):
                zf.write(p, arcname=p.name)

        print()
        print("=" * 108)
        print("HOÀN THÀNH DRY-RUN V6")
        print("=" * 108)
        print(f"Bảng đội ngũ theo năm: {year_table}")
        print(f"Bảng nhân sự gốc: {master_table or 'KHÔNG XÁC ĐỊNH'}")
        print(f"Năm trước: {previous_year_id}")
        print(f"Năm hiện hành: {target_year_id}")
        print(f"Hồ sơ nguồn 2025-2026: {len(source_previous)}")
        print(
            "Ứng viên kế thừa: "
            f"{sum(x['proposed_action']=='CANDIDATE_INHERIT_TO_2026_2027' for x in inheritance)}"
        )
        print(
            "Đã có tại target: "
            f"{sum(x['proposed_action']=='ALREADY_PRESENT_AT_TARGET' for x in inheritance)}"
        )
        print(
            "Không kế thừa do nghỉ/chuyển: "
            f"{sum(x['proposed_action']=='KEEP_HISTORY_DO_NOT_INHERIT_INACTIVE' for x in inheritance)}"
        )
        print(
            "Cần xem trùng: "
            f"{sum(x['proposed_action']=='REVIEW_DUPLICATE_AT_TARGET' for x in inheritance)}"
        )
        print(f"SAFE_TO_BUILD_V7: {'YES' if safe else 'NO'}")
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
        print("=" * 108)
        print("ĐÃ DỪNG DRY-RUN V6")
        print("=" * 108)
        print(str(e))
        print("Database KHÔNG bị thay đổi.")
        sys.exit(2)
    except sqlite3.Error as e:
        print()
        print("=" * 108)
        print("LỖI SQLITE TRONG V6")
        print("=" * 108)
        print(repr(e))
        print("Database KHÔNG bị thay đổi.")
        sys.exit(3)
    except Exception as e:
        print()
        print("=" * 108)
        print("LỖI KHÔNG DỰ KIẾN TRONG V6")
        print("=" * 108)
        print(repr(e))
        print("Database KHÔNG bị thay đổi.")
        sys.exit(4)


if __name__ == "__main__":
    main()
