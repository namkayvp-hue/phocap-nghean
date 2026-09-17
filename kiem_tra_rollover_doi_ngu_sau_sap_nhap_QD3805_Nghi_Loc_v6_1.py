# -*- coding: utf-8 -*-
r"""
DRY-RUN V6.1 - ROLLOVER + SÁP NHẬP ĐỘI NGŨ QĐ 3805 - NGHI LỘC
===============================================================

MỤC TIÊU
--------
Sửa đầy đủ logic của V6:

Năm 2026-2027 của TRƯỜNG ĐÍCH =
    đội ngũ 2025-2026 của chính trường đích
  + đội ngũ 2025-2026 của tất cả trường nguồn nhập vào trường đích
  - người đã có hồ sơ 2026-2027
  - người trùng (theo staff_member_id)
  - người nghỉ/chuyển/ngừng làm việc rõ ràng

Phân loại đủ:
- QUẢN LÝ
- GIÁO VIÊN
- NHÂN VIÊN

Nguồn phân loại ưu tiên:
1. position_group
2. position_title
3. source_level
4. teaching_level
5. source_status_label

DRY-RUN V6.1 CHỈ ĐỌC, KHÔNG SỬA DATABASE.

CHẠY:
    cd C:\PhoCap
    .\.venv\Scripts\python.exe .\kiem_tra_rollover_doi_ngu_sau_sap_nhap_QD3805_Nghi_Loc_v6_1.py

KẾT QUẢ:
    C:\PhoCap\dry_run_rollover_doi_ngu_QD3805_Nghi_Loc_v6_1_<timestamp>.zip
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


def cols(conn: sqlite3.Connection, table: str) -> set[str]:
    return {
        r[1]
        for r in conn.execute(f"PRAGMA table_info({qident(table)})").fetchall()
    }


def table_info(conn: sqlite3.Connection, table: str) -> list[dict]:
    rows = conn.execute(f"PRAGMA table_info({qident(table)})").fetchall()
    return [
        {
            "cid": r[0], "name": r[1], "type": r[2],
            "notnull": r[3], "default": r[4], "pk": r[5]
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


def classify_position(row: sqlite3.Row) -> str:
    parts = []
    for c in (
        "position_group", "position_title", "source_level",
        "teaching_level", "source_status_label"
    ):
        if c in row.keys() and row[c] not in (None, ""):
            parts.append(str(row[c]))
    text = " ".join(normalize(x) for x in parts)

    # Quản lý
    manager_terms = (
        "quan ly", "cbql", "hieu truong", "pho hieu truong",
        "principal", "vice principal", "management", "manager",
        "leader", "leadership", "school leader"
    )
    if any(t in text for t in manager_terms):
        return "QUAN_LY"

    # Nhân viên
    employee_terms = (
        "nhan vien", "ke toan", "van thu", "thu vien", "thiet bi",
        "y te", "bao ve", "phuc vu", "cap duong", "thu quy",
        "support staff", "employee", "non teaching"
    )
    if any(t in text for t in employee_terms):
        return "NHAN_VIEN"

    # Giáo viên
    teacher_terms = (
        "giao vien", "teacher", "teaching", "gv"
    )
    if any(t in text for t in teacher_terms):
        return "GIAO_VIEN"

    return "CHUA_XAC_DINH"


def inactive_reason(row: sqlite3.Row) -> tuple[bool, str]:
    if "is_active" in row.keys() and row["is_active"] in (0, False, "0"):
        return True, "is_active=0"

    parts = []
    for c in ("status_code", "source_status_label", "notes"):
        if c in row.keys() and row[c] not in (None, ""):
            parts.append(str(row[c]))
    text = " ".join(normalize(x) for x in parts)

    terms = (
        "nghi viec", "thoi viec", "da nghi", "nghi huu",
        "chuyen di", "da chuyen", "ngung lam viec",
        "inactive", "resigned", "retired", "terminated"
    )
    for t in terms:
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
    cs = cols(conn, "schools")
    name_col = next(
        (c for c in ("name", "school_name", "ten_truong") if c in cs),
        None
    )
    if not name_col:
        return {}
    ids = sorted(set(SOURCE_IDS) | set(TARGET_IDS))
    rows = conn.execute(
        f"SELECT id, {qident(name_col)} FROM schools "
        f"WHERE id IN ({markers(len(ids))})",
        ids,
    ).fetchall()
    return {int(r[0]): str(r[1]) for r in rows}


def detect_year_ids(conn: sqlite3.Connection) -> tuple[int, int, list[dict]]:
    if not table_exists(conn, "school_years"):
        raise AuditAbort("Không có bảng school_years.")
    cs = cols(conn, "school_years")
    label_col = next(
        (c for c in ("name", "label", "school_year", "year_name") if c in cs),
        None
    )
    if not label_col:
        raise AuditAbort("Không xác định được cột tên năm học.")

    rows = conn.execute(
        f"SELECT id, {qident(label_col)} AS label "
        "FROM school_years ORDER BY id"
    ).fetchall()

    target = None
    previous = None
    report = []
    for r in rows:
        rid = int(r["id"])
        label = str(r["label"] or "")
        report.append({"id": rid, "label": label})
        if "2026" in label and "2027" in label:
            target = rid
        if "2025" in label and "2026" in label:
            previous = rid

    if target is None or previous is None:
        raise AuditAbort(
            f"Không xác định đủ năm học: previous={previous}, target={target}"
        )
    return previous, target, report


def get_staff_member_names(conn: sqlite3.Connection) -> dict[int, dict]:
    if not table_exists(conn, "staff_members"):
        raise AuditAbort("Không có bảng staff_members.")
    cs = cols(conn, "staff_members")
    wanted = [
        c for c in (
            "id", "code", "ministry_staff_code", "full_name",
            "date_of_birth", "gender", "personal_id", "is_active"
        ) if c in cs
    ]
    rows = conn.execute(
        "SELECT " + ", ".join(qident(c) for c in wanted)
        + " FROM staff_members"
    ).fetchall()
    return {
        int(r["id"]): {c: r[c] for c in wanted}
        for r in rows
    }


def fetch_year_records(
    conn: sqlite3.Connection,
    school_ids: tuple[int, ...],
    year_id: int,
    staff_master: dict[int, dict],
) -> list[dict]:
    if not table_exists(conn, "staff_year_records"):
        raise AuditAbort("Không có bảng staff_year_records.")

    cs = cols(conn, "staff_year_records")
    required = {"id", "staff_member_id", "school_year_id", "school_id"}
    if not required <= cs:
        raise AuditAbort(
            f"staff_year_records thiếu cột: {sorted(required - cs)}"
        )

    rows = conn.execute(
        f"SELECT * FROM staff_year_records "
        f"WHERE school_id IN ({markers(len(school_ids))}) "
        "AND school_year_id=? ORDER BY school_id, id",
        list(school_ids) + [year_id],
    ).fetchall()

    out = []
    for r in rows:
        staff_id = int(r["staff_member_id"])
        m = staff_master.get(staff_id, {})
        inactive, reason = inactive_reason(r)
        category = classify_position(r)

        d = {
            "year_record_id": int(r["id"]),
            "staff_member_id": staff_id,
            "staff_code": m.get("code", ""),
            "ministry_staff_code": m.get("ministry_staff_code", ""),
            "full_name": m.get("full_name", ""),
            "date_of_birth": m.get("date_of_birth", ""),
            "gender": m.get("gender", ""),
            "school_id": int(r["school_id"]),
            "school_year_id": int(r["school_year_id"]),
            "status_code": r["status_code"] if "status_code" in r.keys() else "",
            "position_group": r["position_group"] if "position_group" in r.keys() else "",
            "position_title": r["position_title"] if "position_title" in r.keys() else "",
            "employment_type": r["employment_type"] if "employment_type" in r.keys() else "",
            "teaching_level": r["teaching_level"] if "teaching_level" in r.keys() else "",
            "teaching_subject": r["teaching_subject"] if "teaching_subject" in r.keys() else "",
            "source_level": r["source_level"] if "source_level" in r.keys() else "",
            "source_status_label": r["source_status_label"] if "source_status_label" in r.keys() else "",
            "record_is_active": r["is_active"] if "is_active" in r.keys() else "",
            "master_is_active": m.get("is_active", ""),
            "category": category,
            "inactive_flag": "YES" if inactive else "NO",
            "inactive_reason": reason,
        }
        out.append(d)
    return out


def count_categories(rows: list[dict]) -> dict:
    c = Counter(r["category"] for r in rows)
    return {
        "total": len(rows),
        "quan_ly": c.get("QUAN_LY", 0),
        "giao_vien": c.get("GIAO_VIEN", 0),
        "nhan_vien": c.get("NHAN_VIEN", 0),
        "chua_xac_dinh": c.get("CHUA_XAC_DINH", 0),
    }


def audit() -> None:
    print("=" * 110)
    print("DRY-RUN V6.1 - ROLLOVER + SÁP NHẬP ĐỘI NGŨ QĐ 3805 - NGHI LỘC")
    print("=" * 110)
    print("Chế độ: CHỈ ĐỌC - KHÔNG SỬA DATABASE")

    if not CURRENT_DB.exists():
        raise AuditAbort(f"Không tìm thấy current DB: {CURRENT_DB}")

    backup_db = find_backup()
    cur = connect_ro(CURRENT_DB)
    bak = connect_ro(backup_db)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = PROJECT_ROOT / (
        f"dry_run_rollover_doi_ngu_QD3805_Nghi_Loc_v6_1_{ts}"
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
        names_bak = school_names(bak)

        # Master dùng backup để phản ánh đúng trạng thái trước sáp nhập,
        # current để đối chiếu những hồ sơ hiện có.
        staff_master_bak = get_staff_member_names(bak)
        staff_master_cur = get_staff_member_names(cur)

        all_merger_school_ids = tuple(
            sorted(set(SOURCE_IDS) | set(TARGET_IDS))
        )

        previous_all = fetch_year_records(
            bak, all_merger_school_ids, previous_year_id, staff_master_bak
        )
        current_target = fetch_year_records(
            cur, TARGET_IDS, target_year_id, staff_master_cur
        )

        prev_by_school = defaultdict(list)
        for r in previous_all:
            prev_by_school[int(r["school_id"])].append(r)

        current_by_target = defaultdict(list)
        current_index = defaultdict(dict)
        for r in current_target:
            tid = int(r["school_id"])
            current_by_target[tid].append(r)
            current_index[tid][int(r["staff_member_id"])] = r

        # Nguồn (origin) của mỗi target gồm chính target + các source nhập vào.
        origin_schools_by_target = defaultdict(list)
        for tid in TARGET_IDS:
            origin_schools_by_target[tid].append(tid)
        for sid, tid in MERGE_MAP.items():
            origin_schools_by_target[tid].append(sid)

        plan = []
        duplicate_previous = []
        target_summary = []

        for target_id in TARGET_IDS:
            origins = sorted(set(origin_schools_by_target[target_id]))

            # Gộp previous-year theo staff_member_id.
            prev_group = defaultdict(list)
            for origin_id in origins:
                for r in prev_by_school[origin_id]:
                    prev_group[int(r["staff_member_id"])].append(r)

            for staff_id, prev_rows in sorted(prev_group.items()):
                # Nếu cùng 1 người có mặt ở >1 origin trong cùng năm trước, không tự tạo.
                if len(prev_rows) > 1:
                    duplicate_previous.append({
                        "target_school_id": target_id,
                        "target_school_name": names_cur.get(target_id, ""),
                        "staff_member_id": staff_id,
                        "full_name": prev_rows[0]["full_name"],
                        "origin_school_ids": ",".join(
                            str(x["school_id"]) for x in prev_rows
                        ),
                        "origin_record_ids": ",".join(
                            str(x["year_record_id"]) for x in prev_rows
                        ),
                        "count": len(prev_rows),
                    })
                    for r in prev_rows:
                        plan.append({
                            **r,
                            "origin_school_id": r["school_id"],
                            "origin_school_name": names_bak.get(r["school_id"], ""),
                            "target_school_id": target_id,
                            "target_school_name": names_cur.get(target_id, ""),
                            "origin_type": (
                                "TARGET_SELF"
                                if int(r["school_id"]) == target_id
                                else "MERGED_SOURCE"
                            ),
                            "current_target_record_id": "",
                            "proposed_action": "REVIEW_DUPLICATE_PREVIOUS_YEAR",
                            "reason": (
                                "Cùng staff_member_id xuất hiện ở nhiều trường "
                                "trong nhóm gộp năm 2025-2026."
                            ),
                        })
                    continue

                r = prev_rows[0]
                current = current_index[target_id].get(staff_id)

                if current is not None:
                    action = "ALREADY_PRESENT_2026_2027"
                    reason = "Đã có hồ sơ 2026-2027 tại trường đích."
                    current_id = current["year_record_id"]
                elif r["inactive_flag"] == "YES":
                    action = "KEEP_HISTORY_DO_NOT_ROLLOVER"
                    reason = (
                        "Hồ sơ năm trước thể hiện nghỉ/chuyển/ngừng: "
                        + r["inactive_reason"]
                    )
                    current_id = ""
                else:
                    action = "CANDIDATE_ROLLOVER_TO_2026_2027"
                    reason = (
                        "Hồ sơ 2025-2026 còn hoạt động và chưa có "
                        "tại trường đích năm 2026-2027."
                    )
                    current_id = ""

                plan.append({
                    **r,
                    "origin_school_id": r["school_id"],
                    "origin_school_name": names_bak.get(r["school_id"], ""),
                    "target_school_id": target_id,
                    "target_school_name": names_cur.get(target_id, ""),
                    "origin_type": (
                        "TARGET_SELF"
                        if int(r["school_id"]) == target_id
                        else "MERGED_SOURCE"
                    ),
                    "current_target_record_id": current_id,
                    "proposed_action": action,
                    "reason": reason,
                })

            candidates = [
                x for x in plan
                if x["target_school_id"] == target_id
                and x["proposed_action"] == "CANDIDATE_ROLLOVER_TO_2026_2027"
            ]
            already = [
                x for x in plan
                if x["target_school_id"] == target_id
                and x["proposed_action"] == "ALREADY_PRESENT_2026_2027"
            ]
            inactive = [
                x for x in plan
                if x["target_school_id"] == target_id
                and x["proposed_action"] == "KEEP_HISTORY_DO_NOT_ROLLOVER"
            ]
            reviews = [
                x for x in plan
                if x["target_school_id"] == target_id
                and x["proposed_action"] == "REVIEW_DUPLICATE_PREVIOUS_YEAR"
            ]

            current_rows = current_by_target[target_id]
            c_now = count_categories(current_rows)
            c_in = count_categories(candidates)

            projected_rows = current_rows + candidates
            c_after = count_categories(projected_rows)

            target_summary.append({
                "target_school_id": target_id,
                "target_school_name": names_cur.get(target_id, ""),
                "origin_school_ids": ",".join(map(str, origins)),
                "current_2026_2027_total": c_now["total"],
                "current_quan_ly": c_now["quan_ly"],
                "current_giao_vien": c_now["giao_vien"],
                "current_nhan_vien": c_now["nhan_vien"],
                "current_chua_xac_dinh": c_now["chua_xac_dinh"],
                "candidate_rollover_total": c_in["total"],
                "candidate_quan_ly": c_in["quan_ly"],
                "candidate_giao_vien": c_in["giao_vien"],
                "candidate_nhan_vien": c_in["nhan_vien"],
                "candidate_chua_xac_dinh": c_in["chua_xac_dinh"],
                "already_present": len(already),
                "inactive_not_rollover": len(inactive),
                "duplicate_review_rows": len(reviews),
                "projected_total": c_after["total"],
                "projected_quan_ly": c_after["quan_ly"],
                "projected_giao_vien": c_after["giao_vien"],
                "projected_nhan_vien": c_after["nhan_vien"],
                "projected_chua_xac_dinh": c_after["chua_xac_dinh"],
            })

        # Distinct values phục vụ xác minh mapping.
        distinct_report = []
        raw_rows = bak.execute(
            f"SELECT position_group, position_title, status_code, "
            f"employment_type, teaching_level, source_level, "
            f"source_status_label, COUNT(*) AS n "
            f"FROM staff_year_records "
            f"WHERE school_year_id=? "
            f"AND school_id IN ({markers(len(all_merger_school_ids))}) "
            f"GROUP BY position_group, position_title, status_code, "
            f"employment_type, teaching_level, source_level, source_status_label "
            f"ORDER BY n DESC",
            [previous_year_id] + list(all_merger_school_ids),
        ).fetchall()
        for r in raw_rows:
            # Tạo row giả để dùng classifier.
            category = classify_position(r)
            distinct_report.append({
                "position_group": r["position_group"],
                "position_title": r["position_title"],
                "status_code": r["status_code"],
                "employment_type": r["employment_type"],
                "teaching_level": r["teaching_level"],
                "source_level": r["source_level"],
                "source_status_label": r["source_status_label"],
                "count": r["n"],
                "classified_as": category,
            })

        candidates_all = [
            x for x in plan
            if x["proposed_action"] == "CANDIDATE_ROLLOVER_TO_2026_2027"
        ]
        unknown_candidates = [
            x for x in candidates_all
            if x["category"] == "CHUA_XAC_DINH"
        ]

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
                "check": "rollover_includes_target_self_and_merged_sources",
                "result": "PASS",
                "detail": (
                    "Mỗi target dùng previous-year của chính target "
                    "+ tất cả source nhập vào."
                ),
            },
            {
                "check": "no_duplicate_staff_in_previous_union",
                "result": "PASS" if not duplicate_previous else "FAIL",
                "detail": f"duplicate_staff={len(duplicate_previous)}",
            },
            {
                "check": "all_rollover_candidates_classified",
                "result": "PASS" if not unknown_candidates else "FAIL",
                "detail": f"unclassified_candidates={len(unknown_candidates)}",
            },
        ]
        safe = all(x["result"] == "PASS" for x in gate)

        headers_record = [
            "year_record_id", "staff_member_id", "staff_code",
            "ministry_staff_code", "full_name", "date_of_birth", "gender",
            "school_id", "school_year_id",
            "status_code", "position_group", "position_title",
            "employment_type", "teaching_level", "teaching_subject",
            "source_level", "source_status_label",
            "record_is_active", "master_is_active",
            "category", "inactive_flag", "inactive_reason",
        ]

        write_csv(
            out_dir / "100_SCHOOL_YEARS.csv",
            ["id", "label"],
            years,
        )
        write_csv(
            out_dir / "101_SCHEMA_STAFF_YEAR_RECORDS.csv",
            ["cid", "name", "type", "notnull", "default", "pk"],
            table_info(cur, "staff_year_records"),
        )
        write_csv(
            out_dir / "102_DISTINCT_POSITION_STATUS_2025_2026.csv",
            [
                "position_group", "position_title", "status_code",
                "employment_type", "teaching_level", "source_level",
                "source_status_label", "count", "classified_as",
            ],
            distinct_report,
        )
        write_csv(
            out_dir / "103_PREVIOUS_YEAR_ALL_MERGER_SCHOOLS.csv",
            headers_record,
            previous_all,
        )
        write_csv(
            out_dir / "104_CURRENT_YEAR_TARGETS.csv",
            headers_record,
            current_target,
        )
        write_csv(
            out_dir / "105_KE_HOACH_ROLLOVER_GOP_DOI_NGU.csv",
            headers_record + [
                "origin_school_id", "origin_school_name",
                "target_school_id", "target_school_name",
                "origin_type", "current_target_record_id",
                "proposed_action", "reason",
            ],
            plan,
        )
        write_csv(
            out_dir / "106_TONG_HOP_TRUONG_DICH_SAU_ROLLOVER.csv",
            [
                "target_school_id", "target_school_name", "origin_school_ids",
                "current_2026_2027_total",
                "current_quan_ly", "current_giao_vien",
                "current_nhan_vien", "current_chua_xac_dinh",
                "candidate_rollover_total",
                "candidate_quan_ly", "candidate_giao_vien",
                "candidate_nhan_vien", "candidate_chua_xac_dinh",
                "already_present", "inactive_not_rollover",
                "duplicate_review_rows",
                "projected_total", "projected_quan_ly",
                "projected_giao_vien", "projected_nhan_vien",
                "projected_chua_xac_dinh",
            ],
            target_summary,
        )
        write_csv(
            out_dir / "107_TRUNG_STAFF_MEMBER_ID_CAN_XEM.csv",
            [
                "target_school_id", "target_school_name",
                "staff_member_id", "full_name",
                "origin_school_ids", "origin_record_ids", "count",
            ],
            duplicate_previous,
        )
        write_csv(
            out_dir / "108_UNCLASSIFIED_CANDIDATES.csv",
            headers_record + [
                "origin_school_id", "origin_school_name",
                "target_school_id", "target_school_name",
                "origin_type", "proposed_action",
            ],
            unknown_candidates,
        )
        write_csv(
            out_dir / "109_CONG_AN_TOAN_V7.csv",
            ["check", "result", "detail"],
            gate,
        )

        summary = out_dir / "00_TONG_QUAN_V6_1.txt"
        with summary.open("w", encoding="utf-8") as f:
            f.write(
                "DRY-RUN V6.1 - ROLLOVER + SÁP NHẬP ĐỘI NGŨ QĐ 3805 - NGHI LỘC\n"
            )
            f.write("=" * 110 + "\n")
            f.write("CHẾ ĐỘ: CHỈ ĐỌC - KHÔNG SỬA DATABASE\n")
            f.write(f"Current DB: {CURRENT_DB}\n")
            f.write(f"Backup DB : {backup_db}\n")
            f.write(f"Năm trước: {previous_year_id} (2025-2026)\n")
            f.write(f"Năm hiện hành: {target_year_id} (2026-2027)\n\n")

            f.write("NGUYÊN TẮC ĐÃ SỬA\n")
            f.write(
                "- Target 2026-2027 = previous-year của chính target "
                "+ previous-year của source nhập vào, sau loại trùng/nghỉ/chuyển.\n\n"
            )

            f.write("TỔNG HỢP\n")
            for r in target_summary:
                f.write(
                    f"- {r['target_school_id']} {r['target_school_name']}: "
                    f"hiện tại {r['current_2026_2027_total']} "
                    f"(QL={r['current_quan_ly']}, GV={r['current_giao_vien']}, "
                    f"NV={r['current_nhan_vien']}); "
                    f"cần kế thừa {r['candidate_rollover_total']} "
                    f"(QL={r['candidate_quan_ly']}, GV={r['candidate_giao_vien']}, "
                    f"NV={r['candidate_nhan_vien']}); "
                    f"dự kiến sau gộp {r['projected_total']} "
                    f"(QL={r['projected_quan_ly']}, GV={r['projected_giao_vien']}, "
                    f"NV={r['projected_nhan_vien']}, "
                    f"chưa xác định={r['projected_chua_xac_dinh']}).\n"
                )

            f.write("\nCỔNG AN TOÀN\n")
            for g in gate:
                f.write(f"- [{g['result']}] {g['check']}: {g['detail']}\n")

            f.write("\nKẾT LUẬN\n")
            f.write(f"SAFE_TO_BUILD_V7 = {'YES' if safe else 'NO'}\n")
            f.write("- V6.1 KHÔNG thay đổi database.\n")

        zip_path = PROJECT_ROOT / (
            f"dry_run_rollover_doi_ngu_QD3805_Nghi_Loc_v6_1_{ts}.zip"
        )
        with zipfile.ZipFile(
            zip_path, "w", compression=zipfile.ZIP_DEFLATED
        ) as zf:
            for p in sorted(out_dir.iterdir()):
                zf.write(p, arcname=p.name)

        print()
        print("=" * 110)
        print("HOÀN THÀNH DRY-RUN V6.1")
        print("=" * 110)
        for r in target_summary:
            print(
                f"{r['target_school_name']}: "
                f"hiện {r['current_2026_2027_total']} + "
                f"kế thừa {r['candidate_rollover_total']} = "
                f"dự kiến {r['projected_total']} "
                f"[QL {r['projected_quan_ly']} | "
                f"GV {r['projected_giao_vien']} | "
                f"NV {r['projected_nhan_vien']} | "
                f"chưa xác định {r['projected_chua_xac_dinh']}]"
            )
        print(f"Trùng staff_member_id cần xem: {len(duplicate_previous)}")
        print(f"Ứng viên chưa phân loại: {len(unknown_candidates)}")
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
        print("=" * 110)
        print("ĐÃ DỪNG DRY-RUN V6.1")
        print("=" * 110)
        print(str(e))
        print("Database KHÔNG bị thay đổi.")
        sys.exit(2)
    except sqlite3.Error as e:
        print()
        print("=" * 110)
        print("LỖI SQLITE TRONG V6.1")
        print("=" * 110)
        print(repr(e))
        print("Database KHÔNG bị thay đổi.")
        sys.exit(3)
    except Exception as e:
        print()
        print("=" * 110)
        print("LỖI KHÔNG DỰ KIẾN TRONG V6.1")
        print("=" * 110)
        print(repr(e))
        print("Database KHÔNG bị thay đổi.")
        sys.exit(4)


if __name__ == "__main__":
    main()
