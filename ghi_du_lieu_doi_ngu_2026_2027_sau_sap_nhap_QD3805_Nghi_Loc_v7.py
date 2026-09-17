# -*- coding: utf-8 -*-
r"""
V7 - GHI THẬT ĐỘI NGŨ 2026-2027 SAU SÁP NHẬP QĐ 3805 - NGHI LỘC
================================================================

NGUYÊN TẮC
----------
Đội ngũ 2026-2027 của mỗi trường đích =
    đội ngũ 2025-2026 của chính trường đích
  + đội ngũ 2025-2026 của các trường nguồn nhập vào
  - hồ sơ đã có ở 2026-2027
  - người trùng theo staff_member_id
  - người nghỉ/chuyển/ngừng làm việc rõ ràng

PHẠM VI
-------
- Quản lý
- Giáo viên
- Nhân viên

KHÔNG THAY ĐỔI
---------------
- Lịch sử 2025-2026 và các năm cũ.
- Bảng staff_members.
- Tài khoản users.
- Tên trường.
- Dữ liệu lớp/học sinh (sẽ làm ở bước riêng).

AN TOÀN
-------
- Kiểm tra integrity trước khi chạy.
- Tính lại đúng kế hoạch V6.1.
- Yêu cầu đúng 333 hồ sơ còn thiếu cần tạo.
- Không có trùng staff_member_id trong union năm trước.
- Không có ứng viên chưa phân loại.
- Mô phỏng INSERT trên bản sao SQLite trong RAM trước.
- Backup database thật trước khi ghi.
- BEGIN IMMEDIATE + transaction.
- INSERT chỉ các hồ sơ còn thiếu.
- Kiểm tra tổng số và cơ cấu sau ghi.
- foreign_key_check = 0.
- integrity_check = ok.
- Lỗi trước COMMIT => ROLLBACK.

KẾT QUẢ ĐÚNG THEO V6.1
-----------------------
747 MN TT Quán Hành : 72 = QL 6 + GV 50 + NV 16
748 MN Nghi Diên     : 88 = QL 8 + GV 61 + NV 19
1178 TH Nghi Diên    : 92 = QL 4 + GV 70 + NV 18
1179 TH Nghi Trung   : 116 = QL 6 + GV 85 + NV 25
1605 THCS Nghi Diên  : 33 = QL 3 + GV 26 + NV 4
1606 THCS Nghi Trung : 56 = QL 4 + GV 47 + NV 5

CHẠY:
    cd C:\PhoCap
    .\.venv\Scripts\python.exe .\ghi_du_lieu_doi_ngu_2026_2027_sau_sap_nhap_QD3805_Nghi_Loc_v7.py
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
DB_PATH = PROJECT_ROOT / "data" / "phocap.db"
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

EXPECTED_CANDIDATES = 333
EXPECTED_BY_TARGET = {
    747: {"total": 72, "QUAN_LY": 6, "GIAO_VIEN": 50, "NHAN_VIEN": 16},
    748: {"total": 88, "QUAN_LY": 8, "GIAO_VIEN": 61, "NHAN_VIEN": 19},
    1178: {"total": 92, "QUAN_LY": 4, "GIAO_VIEN": 70, "NHAN_VIEN": 18},
    1179: {"total": 116, "QUAN_LY": 6, "GIAO_VIEN": 85, "NHAN_VIEN": 25},
    1605: {"total": 33, "QUAN_LY": 3, "GIAO_VIEN": 26, "NHAN_VIEN": 4},
    1606: {"total": 56, "QUAN_LY": 4, "GIAO_VIEN": 47, "NHAN_VIEN": 5},
}


class MigrationAbort(RuntimeError):
    pass


def qident(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def markers(n: int) -> str:
    return ",".join("?" for _ in range(n))


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone() is not None


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


def normalize(value) -> str:
    if value is None:
        return ""
    s = str(value).strip().lower()
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())


def classify_position(row: sqlite3.Row | dict) -> str:
    keys = row.keys() if hasattr(row, "keys") else row
    parts = []
    for c in (
        "position_group", "position_title", "source_level",
        "teaching_level", "source_status_label"
    ):
        if c in keys and row[c] not in (None, ""):
            parts.append(str(row[c]))
    text = " ".join(normalize(x) for x in parts)

    manager_terms = (
        "quan ly", "cbql", "hieu truong", "pho hieu truong",
        "principal", "vice principal", "management", "manager",
        "leader", "leadership", "school leader"
    )
    if any(t in text for t in manager_terms):
        return "QUAN_LY"

    employee_terms = (
        "nhan vien", "ke toan", "van thu", "thu vien", "thiet bi",
        "y te", "bao ve", "phuc vu", "cap duong", "thu quy",
        "support staff", "employee", "non teaching"
    )
    if any(t in text for t in employee_terms):
        return "NHAN_VIEN"

    teacher_terms = ("giao vien", "teacher", "teaching", "gv")
    if any(t in text for t in teacher_terms):
        return "GIAO_VIEN"

    return "CHUA_XAC_DINH"


def is_inactive(row: sqlite3.Row | dict) -> tuple[bool, str]:
    keys = row.keys() if hasattr(row, "keys") else row

    if "is_active" in keys and row["is_active"] in (0, False, "0"):
        return True, "is_active=0"

    parts = []
    for c in ("status_code", "source_status_label", "notes"):
        if c in keys and row[c] not in (None, ""):
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


def detect_year_ids(conn: sqlite3.Connection) -> tuple[int, int]:
    if not table_exists(conn, "school_years"):
        raise MigrationAbort("Không có bảng school_years.")
    cs = colset(conn, "school_years")
    label_col = next(
        (c for c in ("name", "label", "school_year", "year_name") if c in cs),
        None
    )
    if not label_col:
        raise MigrationAbort("Không xác định được cột tên năm học.")

    rows = conn.execute(
        f"SELECT id, {qident(label_col)} FROM school_years ORDER BY id"
    ).fetchall()

    previous = target = None
    for r in rows:
        label = str(r[1] or "")
        if "2025" in label and "2026" in label:
            previous = int(r[0])
        if "2026" in label and "2027" in label:
            target = int(r[0])

    if previous is None or target is None:
        raise MigrationAbort(
            f"Không xác định đủ năm học: previous={previous}, target={target}"
        )
    return previous, target


def school_names(conn: sqlite3.Connection) -> dict[int, str]:
    if not table_exists(conn, "schools"):
        return {}
    cs = colset(conn, "schools")
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


def validate_school_states(conn: sqlite3.Connection) -> None:
    cs = colset(conn, "schools")
    if "is_active" not in cs:
        raise MigrationAbort("schools không có is_active.")

    for sid in SOURCE_IDS:
        r = conn.execute(
            "SELECT is_active FROM schools WHERE id=?", (sid,)
        ).fetchone()
        if not r or r[0] != 0:
            raise MigrationAbort(
                f"Trường nguồn id={sid} phải is_active=0 trước V7."
            )

    for sid in TARGET_IDS:
        r = conn.execute(
            "SELECT is_active FROM schools WHERE id=?", (sid,)
        ).fetchone()
        if not r or r[0] != 1:
            raise MigrationAbort(
                f"Trường đích id={sid} phải is_active=1 trước V7."
            )


def build_plan(
    conn: sqlite3.Connection,
    previous_year_id: int,
    target_year_id: int,
) -> tuple[list[dict], list[dict], list[dict]]:
    if not table_exists(conn, "staff_year_records"):
        raise MigrationAbort("Không có bảng staff_year_records.")

    cs = colset(conn, "staff_year_records")
    required = {
        "id", "staff_member_id", "school_year_id", "school_id",
        "status_code", "position_group", "employment_type",
        "teaching_level", "teaching_age_group", "receives_policy",
        "qualification_level", "qualification_standard",
        "professional_standard", "is_active",
        "created_at", "updated_at",
    }
    missing = required - cs
    if missing:
        raise MigrationAbort(
            f"staff_year_records thiếu cột bắt buộc: {sorted(missing)}"
        )

    origin_schools_by_target = defaultdict(list)
    for tid in TARGET_IDS:
        origin_schools_by_target[tid].append(tid)
    for sid, tid in MERGE_MAP.items():
        origin_schools_by_target[tid].append(sid)

    plan = []
    duplicates = []
    unclassified = []

    for target_id in TARGET_IDS:
        origins = sorted(set(origin_schools_by_target[target_id]))

        prev_rows = conn.execute(
            f"SELECT * FROM staff_year_records "
            f"WHERE school_year_id=? "
            f"AND school_id IN ({markers(len(origins))}) "
            "ORDER BY school_id, id",
            [previous_year_id] + origins,
        ).fetchall()

        current_rows = conn.execute(
            "SELECT * FROM staff_year_records "
            "WHERE school_year_id=? AND school_id=?",
            (target_year_id, target_id),
        ).fetchall()

        current_by_staff = {
            int(r["staff_member_id"]): r for r in current_rows
        }

        prev_by_staff = defaultdict(list)
        for r in prev_rows:
            prev_by_staff[int(r["staff_member_id"])].append(r)

        for staff_id, rows in sorted(prev_by_staff.items()):
            if len(rows) > 1:
                duplicates.append({
                    "target_school_id": target_id,
                    "staff_member_id": staff_id,
                    "source_record_ids": ",".join(str(r["id"]) for r in rows),
                    "origin_school_ids": ",".join(str(r["school_id"]) for r in rows),
                    "count": len(rows),
                })
                continue

            r = rows[0]
            category = classify_position(r)
            inactive, reason = is_inactive(r)

            if category == "CHUA_XAC_DINH":
                unclassified.append({
                    "target_school_id": target_id,
                    "source_record_id": r["id"],
                    "staff_member_id": staff_id,
                })

            if staff_id in current_by_staff:
                action = "ALREADY_PRESENT"
            elif inactive:
                action = "KEEP_HISTORY_INACTIVE"
            else:
                action = "INSERT"

            plan.append({
                "target_school_id": target_id,
                "origin_school_id": int(r["school_id"]),
                "source_record_id": int(r["id"]),
                "staff_member_id": staff_id,
                "category": category,
                "inactive_flag": "YES" if inactive else "NO",
                "inactive_reason": reason,
                "action": action,
            })

    return plan, duplicates, unclassified


def count_current(
    conn: sqlite3.Connection,
    target_year_id: int,
) -> dict[int, dict]:
    out = {}
    for tid in TARGET_IDS:
        rows = conn.execute(
            "SELECT * FROM staff_year_records "
            "WHERE school_year_id=? AND school_id=?",
            (target_year_id, tid),
        ).fetchall()
        c = Counter(classify_position(r) for r in rows)
        out[tid] = {
            "total": len(rows),
            "QUAN_LY": c.get("QUAN_LY", 0),
            "GIAO_VIEN": c.get("GIAO_VIEN", 0),
            "NHAN_VIEN": c.get("NHAN_VIEN", 0),
            "CHUA_XAC_DINH": c.get("CHUA_XAC_DINH", 0),
        }
    return out


def validate_plan(
    conn: sqlite3.Connection,
    plan: list[dict],
    duplicates: list[dict],
    unclassified: list[dict],
    target_year_id: int,
) -> list[dict]:
    if duplicates:
        raise MigrationAbort(
            f"Có {len(duplicates)} staff_member_id trùng trong union năm trước."
        )
    if unclassified:
        raise MigrationAbort(
            f"Có {len(unclassified)} hồ sơ chưa phân loại."
        )

    candidates = [x for x in plan if x["action"] == "INSERT"]
    if len(candidates) != EXPECTED_CANDIDATES:
        raise MigrationAbort(
            f"Số ứng viên V7={len(candidates)}; expected={EXPECTED_CANDIDATES}."
        )

    current = count_current(conn, target_year_id)
    projected_report = []

    by_target_candidates = defaultdict(list)
    for x in candidates:
        by_target_candidates[int(x["target_school_id"])].append(x)

    for tid in TARGET_IDS:
        now = current[tid]
        cand = by_target_candidates[tid]
        cc = Counter(x["category"] for x in cand)

        projected = {
            "total": now["total"] + len(cand),
            "QUAN_LY": now["QUAN_LY"] + cc.get("QUAN_LY", 0),
            "GIAO_VIEN": now["GIAO_VIEN"] + cc.get("GIAO_VIEN", 0),
            "NHAN_VIEN": now["NHAN_VIEN"] + cc.get("NHAN_VIEN", 0),
        }
        expected = EXPECTED_BY_TARGET[tid]

        for key in ("total", "QUAN_LY", "GIAO_VIEN", "NHAN_VIEN"):
            if projected[key] != expected[key]:
                raise MigrationAbort(
                    f"Target {tid} projected {key}={projected[key]}, "
                    f"expected={expected[key]}."
                )

        projected_report.append({
            "target_school_id": tid,
            "current_total": now["total"],
            "current_quan_ly": now["QUAN_LY"],
            "current_giao_vien": now["GIAO_VIEN"],
            "current_nhan_vien": now["NHAN_VIEN"],
            "candidate_total": len(cand),
            "candidate_quan_ly": cc.get("QUAN_LY", 0),
            "candidate_giao_vien": cc.get("GIAO_VIEN", 0),
            "candidate_nhan_vien": cc.get("NHAN_VIEN", 0),
            "projected_total": projected["total"],
            "projected_quan_ly": projected["QUAN_LY"],
            "projected_giao_vien": projected["GIAO_VIEN"],
            "projected_nhan_vien": projected["NHAN_VIEN"],
        })

    return projected_report


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
        out.append({"name": idx_name, "columns": cols_})
    return out


def insert_one_from_source(
    conn: sqlite3.Connection,
    source_record_id: int,
    target_school_id: int,
    target_year_id: int,
) -> int:
    """
    Clone toàn bộ dữ liệu nghiệp vụ của staff_year_records từ record 2025-2026,
    chỉ thay:
      - id: tự sinh
      - school_year_id: năm 2026-2027
      - school_id: trường đích
      - created_at / updated_at: thời điểm V7
    """
    infos = columns(conn, "staff_year_records")
    all_cols = [c["name"] for c in infos]

    source = conn.execute(
        "SELECT * FROM staff_year_records WHERE id=?",
        (source_record_id,),
    ).fetchone()
    if not source:
        raise MigrationAbort(
            f"Không tìm thấy source staff_year_record id={source_record_id}."
        )

    insert_cols = []
    values = []

    for c in all_cols:
        if c == "id":
            continue

        insert_cols.append(c)
        if c == "school_year_id":
            values.append(target_year_id)
        elif c == "school_id":
            values.append(target_school_id)
        elif c in ("created_at", "updated_at"):
            values.append(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        else:
            values.append(source[c])

    sql = (
        "INSERT INTO staff_year_records ("
        + ", ".join(qident(c) for c in insert_cols)
        + ") VALUES ("
        + markers(len(insert_cols))
        + ")"
    )
    cur = conn.execute(sql, values)
    return int(cur.lastrowid)


def simulate(
    disk_conn: sqlite3.Connection,
    candidates: list[dict],
    target_year_id: int,
) -> tuple[bool, str]:
    mem = sqlite3.connect(":memory:")
    mem.row_factory = sqlite3.Row
    disk_conn.backup(mem)
    mem.execute("PRAGMA foreign_keys=ON")

    try:
        mem.execute("BEGIN")
        for x in candidates:
            insert_one_from_source(
                mem,
                int(x["source_record_id"]),
                int(x["target_school_id"]),
                target_year_id,
            )

        fk = mem.execute("PRAGMA foreign_key_check").fetchall()
        if fk:
            mem.rollback()
            return False, f"foreign_key_check có {len(fk)} lỗi"

        counts = count_current(mem, target_year_id)
        for tid, expected in EXPECTED_BY_TARGET.items():
            actual = counts[tid]
            for key in ("total", "QUAN_LY", "GIAO_VIEN", "NHAN_VIEN"):
                if actual[key] != expected[key]:
                    mem.rollback()
                    return False, (
                        f"target={tid} {key}: actual={actual[key]} "
                        f"expected={expected[key]}"
                    )

        mem.rollback()
        return True, "PASS"
    except sqlite3.Error as e:
        try:
            mem.rollback()
        except Exception:
            pass
        return False, repr(e)
    finally:
        mem.close()


def backup_database() -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / (
        f"phocap_truoc_V7_doi_ngu_QD3805_Nghi_Loc_{ts}.db"
    )

    src = sqlite3.connect(str(DB_PATH))
    dst = sqlite3.connect(str(backup_path))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()

    chk = sqlite3.connect(str(backup_path))
    try:
        result = chk.execute("PRAGMA integrity_check").fetchone()[0]
        if result != "ok":
            raise MigrationAbort(
                f"Backup V7 integrity_check={result}"
            )
    finally:
        chk.close()

    return backup_path


def write_csv(path: Path, headers: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def run() -> None:
    print("=" * 112)
    print("V7 - GHI THẬT ĐỘI NGŨ 2026-2027 SAU SÁP NHẬP QĐ 3805 - NGHI LỘC")
    print("=" * 112)

    if not DB_PATH.exists():
        raise MigrationAbort(f"Không tìm thấy database: {DB_PATH}")

    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_dir = PROJECT_ROOT / f"V7_doi_ngu_QD3805_Nghi_Loc_{ts}"
    report_dir.mkdir(parents=True, exist_ok=False)

    backup_path = None
    committed = False

    try:
        integrity_before = conn.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]
        if integrity_before != "ok":
            raise MigrationAbort(
                f"integrity_check trước V7={integrity_before}"
            )

        previous_year_id, target_year_id = detect_year_ids(conn)
        validate_school_states(conn)

        plan, duplicates, unclassified = build_plan(
            conn, previous_year_id, target_year_id
        )
        projected = validate_plan(
            conn, plan, duplicates, unclassified, target_year_id
        )

        candidates = [x for x in plan if x["action"] == "INSERT"]
        already = [x for x in plan if x["action"] == "ALREADY_PRESENT"]
        inactive = [x for x in plan if x["action"] == "KEEP_HISTORY_INACTIVE"]

        print("PRE-FLIGHT PASS")
        print(f"  Ứng viên cần tạo: {len(candidates)}")
        print(f"  Đã có 2026-2027: {len(already)}")
        print(f"  Không rollover do nghỉ/chuyển: {len(inactive)}")
        print(f"  Trùng staff_member_id: {len(duplicates)}")
        print(f"  Chưa phân loại: {len(unclassified)}")

        idx = unique_indexes(conn, "staff_year_records")
        idx_report = [
            {"index_name": x["name"], "columns": ",".join(x["columns"])}
            for x in idx
        ]

        sim_ok, sim_note = simulate(conn, candidates, target_year_id)
        if not sim_ok:
            raise MigrationAbort(
                f"Mô phỏng INSERT trên RAM thất bại: {sim_note}"
            )
        print("MÔ PHỎNG TRÊN RAM: PASS")

        write_csv(
            report_dir / "01_KE_HOACH_TRUOC_V7.csv",
            [
                "target_school_id", "origin_school_id",
                "source_record_id", "staff_member_id",
                "category", "inactive_flag", "inactive_reason", "action",
            ],
            plan,
        )
        write_csv(
            report_dir / "02_DU_KIEN_SAU_V7.csv",
            [
                "target_school_id",
                "current_total", "current_quan_ly",
                "current_giao_vien", "current_nhan_vien",
                "candidate_total", "candidate_quan_ly",
                "candidate_giao_vien", "candidate_nhan_vien",
                "projected_total", "projected_quan_ly",
                "projected_giao_vien", "projected_nhan_vien",
            ],
            projected,
        )
        write_csv(
            report_dir / "03_UNIQUE_INDEXES.csv",
            ["index_name", "columns"],
            idx_report,
        )

        backup_path = backup_database()
        print(f"BACKUP V7 OK: {backup_path}")

        conn.execute("BEGIN IMMEDIATE")

        inserted = []
        for x in candidates:
            new_id = insert_one_from_source(
                conn,
                int(x["source_record_id"]),
                int(x["target_school_id"]),
                target_year_id,
            )
            inserted.append({
                **x,
                "new_year_record_id": new_id,
            })

        if len(inserted) != EXPECTED_CANDIDATES:
            raise MigrationAbort(
                f"Đã INSERT {len(inserted)}; expected={EXPECTED_CANDIDATES}."
            )

        # Kiểm tra tuyệt đối sau INSERT trước COMMIT.
        counts_after = count_current(conn, target_year_id)
        final_report = []

        for tid in TARGET_IDS:
            actual = counts_after[tid]
            expected = EXPECTED_BY_TARGET[tid]

            for key in ("total", "QUAN_LY", "GIAO_VIEN", "NHAN_VIEN"):
                if actual[key] != expected[key]:
                    raise MigrationAbort(
                        f"Sau INSERT target={tid}, {key}={actual[key]}, "
                        f"expected={expected[key]}."
                    )

            if actual["CHUA_XAC_DINH"] != 0:
                raise MigrationAbort(
                    f"Target={tid} còn {actual['CHUA_XAC_DINH']} hồ sơ chưa phân loại."
                )

            final_report.append({
                "target_school_id": tid,
                "total": actual["total"],
                "quan_ly": actual["QUAN_LY"],
                "giao_vien": actual["GIAO_VIEN"],
                "nhan_vien": actual["NHAN_VIEN"],
                "chua_xac_dinh": actual["CHUA_XAC_DINH"],
                "result": "PASS",
            })

        # Không được có cùng staff_member_id lặp trong một target/year.
        dup_after = conn.execute(
            "SELECT school_id, staff_member_id, COUNT(*) AS n "
            "FROM staff_year_records "
            "WHERE school_year_id=? "
            f"AND school_id IN ({markers(len(TARGET_IDS))}) "
            "GROUP BY school_id, staff_member_id "
            "HAVING COUNT(*) > 1",
            [target_year_id] + list(TARGET_IDS),
        ).fetchall()
        if dup_after:
            raise MigrationAbort(
                f"Sau V7 có {len(dup_after)} staff_member_id bị trùng trong target/year."
            )

        fk = conn.execute("PRAGMA foreign_key_check").fetchall()
        if fk:
            raise MigrationAbort(
                f"foreign_key_check có {len(fk)} lỗi."
            )

        conn.commit()
        committed = True

        integrity_after = conn.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]
        if integrity_after != "ok":
            raise MigrationAbort(
                "ĐÃ COMMIT nhưng integrity_check sau V7 không ok: "
                f"{integrity_after}. Backup: {backup_path}"
            )

        names = school_names(conn)

        write_csv(
            report_dir / "10_333_HO_SO_DA_TAO.csv",
            [
                "new_year_record_id",
                "target_school_id", "origin_school_id",
                "source_record_id", "staff_member_id",
                "category", "action",
            ],
            inserted,
        )

        for r in final_report:
            r["target_school_name"] = names.get(
                int(r["target_school_id"]), ""
            )

        write_csv(
            report_dir / "11_KET_QUA_DOI_NGU_2026_2027.csv",
            [
                "target_school_id", "target_school_name",
                "total", "quan_ly", "giao_vien",
                "nhan_vien", "chua_xac_dinh", "result",
            ],
            final_report,
        )

        summary_path = report_dir / "00_KET_QUA_V7.txt"
        with summary_path.open("w", encoding="utf-8") as f:
            f.write(
                "V7 - KẾT QUẢ GHI ĐỘI NGŨ 2026-2027 SAU SÁP NHẬP QĐ 3805\n"
            )
            f.write("=" * 112 + "\n")
            f.write("STATUS = SUCCESS\n")
            f.write(f"Database: {DB_PATH}\n")
            f.write(f"Backup trước V7: {backup_path}\n")
            f.write(f"Năm trước: {previous_year_id}\n")
            f.write(f"Năm hiện hành: {target_year_id}\n\n")
            f.write(f"- Hồ sơ mới đã tạo: {len(inserted)}\n")
            f.write(f"- Hồ sơ đã có, không tạo lại: {len(already)}\n")
            f.write(f"- Hồ sơ nghỉ/chuyển, không rollover: {len(inactive)}\n")
            f.write("- Trùng staff_member_id sau V7: 0\n")
            f.write("- foreign_key_check: PASS (0 lỗi)\n")
            f.write(f"- integrity_check: {integrity_after}\n\n")

            f.write("CƠ CẤU CUỐI CÙNG\n")
            for r in final_report:
                f.write(
                    f"- {r['target_school_id']} {r['target_school_name']}: "
                    f"{r['total']} = QL {r['quan_ly']} + "
                    f"GV {r['giao_vien']} + NV {r['nhan_vien']}\n"
                )

            f.write(
                "\nLịch sử 2025-2026 không bị sửa. "
                "V7 chỉ tạo hồ sơ năm 2026-2027 còn thiếu.\n"
            )

        zip_path = PROJECT_ROOT / (
            f"V7_doi_ngu_QD3805_Nghi_Loc_KET_QUA_{ts}.zip"
        )
        with zipfile.ZipFile(
            zip_path, "w", compression=zipfile.ZIP_DEFLATED
        ) as zf:
            for p in sorted(report_dir.iterdir()):
                zf.write(p, arcname=p.name)

        print()
        print("=" * 112)
        print("V7 THÀNH CÔNG")
        print("=" * 112)
        print(f"Đã tạo {len(inserted)} hồ sơ đội ngũ 2026-2027 còn thiếu.")
        for r in final_report:
            print(
                f"{r['target_school_name']}: {r['total']} "
                f"[QL {r['quan_ly']} | GV {r['giao_vien']} | NV {r['nhan_vien']}]"
            )
        print("Trùng staff_member_id: 0")
        print("foreign_key_check: PASS")
        print("integrity_check: PASS")
        print(f"Backup V7: {backup_path}")
        print(f"ZIP kết quả: {zip_path}")
        print()
        print("GỬI LẠI ZIP KẾT QUẢ V7 CHO TÔI ĐỂ ĐỐI CHIẾU.")

    except Exception:
        if not committed:
            try:
                conn.rollback()
            except Exception:
                pass
        raise
    finally:
        conn.close()


def main() -> None:
    try:
        run()
    except MigrationAbort as e:
        print()
        print("=" * 112)
        print("V7 ĐÃ DỪNG - ĐÃ ROLLBACK NẾU CHƯA COMMIT")
        print("=" * 112)
        print(str(e))
        print("Không tiếp tục sửa database.")
        sys.exit(2)
    except sqlite3.IntegrityError as e:
        print()
        print("=" * 112)
        print("LỖI UNIQUE / FOREIGN KEY - ĐÃ ROLLBACK")
        print("=" * 112)
        print(repr(e))
        sys.exit(3)
    except sqlite3.Error as e:
        print()
        print("=" * 112)
        print("LỖI SQLITE - ĐÃ ROLLBACK NẾU CHƯA COMMIT")
        print("=" * 112)
        print(repr(e))
        sys.exit(4)
    except Exception as e:
        print()
        print("=" * 112)
        print("LỖI KHÔNG DỰ KIẾN")
        print("=" * 112)
        print(repr(e))
        print("Nếu lỗi trước COMMIT thì transaction đã rollback.")
        sys.exit(5)


if __name__ == "__main__":
    main()
