# -*- coding: utf-8 -*-
from __future__ import annotations

import csv
import hashlib
import json
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(r"C:\PhoCap")
DB = ROOT / "data" / "phocap.db"
EXPORT_DIR = ROOT / "exports"

OUT = EXPORT_DIR / "BATCH_DU_LIEU_HAU_SAP_NHAP_TOAN_TINH_06.txt"
READINESS_CSV = EXPORT_DIR / "BATCH_06_SAN_SANG_KHOA_130_XA.csv"
MANUAL_V2_CSV = EXPORT_DIR / "MANUAL_3_NGUON_TACH_DIEM_STAFF_V2.csv"

EXPECTED_DB_SHA = "fd20f8150c0dc83855b00cb6da3ed5ea7f8fd11d4ab461506836f5446591738d"

BASE_YEAR_ID = 1
CURRENT_YEAR_ID = 2

MANUAL_SPLIT = {
    1510: {
        "operation": "QD3805-OP-0191",
        "fixed_target_ids": [1509],
        "strict_name_target": "Văn Hiến",
        "note": "Nguyễn Văn Trỗi (Thịnh Sơn): chỉ phân bổ theo danh sách thực tế; điểm Hòa Sơn đi Văn Hiến, phần còn lại theo phương án đã khóa."
    },
    1522: {
        "operation": "QD3805-OP-0132/0133",
        "fixed_target_ids": [1521, 1523],
        "strict_name_target": None,
        "note": "Vạn Phong: Diễn Vạn/Diễn Phong tách về hai trường đích; không tự suy đoán từng người."
    },
    1658: {
        "operation": "QD3805-OP-0489",
        "fixed_target_ids": [1660, 1657],
        "strict_name_target": None,
        "note": "Bá-Ngọc: tách Quỳnh Bá/Quỳnh Ngọc về hai đích; không tự suy đoán từng người."
    },
}

SOURCE_CODE_TERMS = [
    "is_commune_locked",
    "is_province_locked",
    "survey_school_assignments",
    "survey_batch_lock_logs",
    "DA_GUI_XA",
    "DA_HOAN_THANH",
    "CHUAN_BI",
    "lock_school",
    "lock_commune",
    "lock_province",
    "KHÓA",
    "KHOA",
]

SKIP_DIRS = {".venv", "venv", ".git", "__pycache__", "node_modules", "backups", "exports"}

LOG = None

def log(*args):
    s = " ".join(str(x) for x in args)
    print(s)
    if LOG:
        LOG.write(s + "\n")
        LOG.flush()

def qi(name):
    return '"' + str(name).replace('"', '""') + '"'

def sha256_file(path: Path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()

def table_exists(conn, table):
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,)
    ).fetchone() is not None

def table_info(conn, table):
    return conn.execute(f"PRAGMA table_info({qi(table)})").fetchall()

def cols(conn, table):
    return [r[1] for r in table_info(conn, table)]

def school(conn, sid):
    return conn.execute(
        "SELECT id,commune_id,code,name,is_active FROM schools WHERE id=?",
        (sid,)
    ).fetchone()

def count(conn, sql, params=()):
    return int(conn.execute(sql, params).fetchone()[0])

def group_counts(conn, sql, params=()):
    return conn.execute(sql, params).fetchall()

def strict_thcs_named_candidates(conn, name_term):
    """
    Chỉ nhận trường có tên khớp VÀ có dấu vết đội ngũ THCS năm nguồn.
    Loại hoàn toàn các cơ sở MN/TH chỉ tình cờ chứa tên xã.
    """
    rows = conn.execute(
        """
        SELECT DISTINCT s.id,s.commune_id,s.code,s.name,s.is_active
        FROM schools s
        WHERE s.is_active=1
          AND s.name LIKE ?
          AND EXISTS (
              SELECT 1
              FROM staff_year_records y
              WHERE y.school_id=s.id
                AND y.school_year_id=?
                AND (
                    UPPER(COALESCE(y.source_level,''))='THCS'
                    OR UPPER(COALESCE(y.teaching_level,''))='THCS'
                )
          )
        ORDER BY s.commune_id,s.id
        """,
        (f"%{name_term}%", BASE_YEAR_ID)
    ).fetchall()
    return rows

def manual_v2_export(conn):
    log("\n" + "="*160)
    log("1. SỬA GÓI MANUAL 3 NGUỒN TÁCH ĐIỂM - LỌC ĐÍCH THCS NGHIÊM NGẶT")
    log("CHỈ XUẤT CSV - KHÔNG GHI DATABASE")
    log("="*160)

    fieldnames = [
        "operation",
        "source_school_id",
        "source_school_code",
        "source_school_name",
        "destination_options_thcs_only",
        "staff_member_id",
        "staff_code",
        "full_name",
        "position_group",
        "position_title",
        "teaching_subject",
        "status_code",
        "source_status_label",
        "target_school_id_to_fill",
        "note",
    ]
    out_rows = []

    for sid, cfg in MANUAL_SPLIT.items():
        src = school(conn, sid)
        targets = []

        for tid in cfg["fixed_target_ids"]:
            t = school(conn, tid)
            if t and int(t[4] or 0) == 1:
                targets.append(t)

        if cfg["strict_name_target"]:
            strict = strict_thcs_named_candidates(conn, cfg["strict_name_target"])
            log("STRICT_THCS_NAME_CANDIDATES", cfg["strict_name_target"], "=", strict)
            for t in strict:
                if t not in targets and int(t[0]) != sid:
                    targets.append(t)

        option_text = " | ".join(f"{t[0]}:{t[2]}:{t[3]}" for t in targets)

        staff = conn.execute(
            """
            SELECT y.staff_member_id,m.code,m.full_name,
                   y.position_group,y.position_title,y.teaching_subject,
                   y.status_code,y.source_status_label
            FROM staff_year_records y
            LEFT JOIN staff_members m ON m.id=y.staff_member_id
            WHERE y.school_id=? AND y.school_year_id=?
            ORDER BY y.position_group,m.full_name,y.staff_member_id
            """,
            (sid, BASE_YEAR_ID)
        ).fetchall()

        log("MANUAL_SOURCE =", src)
        log("DESTINATION_OPTIONS_THCS_ONLY =", targets)
        log("STAFF_ROWS =", len(staff))

        for r in staff:
            out_rows.append({
                "operation": cfg["operation"],
                "source_school_id": sid,
                "source_school_code": src[2] if src else "",
                "source_school_name": src[3] if src else "",
                "destination_options_thcs_only": option_text,
                "staff_member_id": r[0],
                "staff_code": r[1],
                "full_name": r[2],
                "position_group": r[3],
                "position_title": r[4],
                "teaching_subject": r[5],
                "status_code": r[6],
                "source_status_label": r[7],
                "target_school_id_to_fill": "",
                "note": cfg["note"],
            })

    with MANUAL_V2_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(out_rows)

    log("MANUAL_V2_CSV =", MANUAL_V2_CSV)
    log("MANUAL_V2_ROWS =", len(out_rows))
    log("IMPORTANT = Không dùng candidate MN id=680 của file V1; V2 chỉ cho phép đích có dấu vết THCS.")
    return len(out_rows)

def batch_rows(conn):
    return conn.execute(
        """
        SELECT b.id,b.school_year_id,b.commune_id,b.code,b.name,b.status,
               COALESCE(b.is_locked,0),
               COALESCE(e.is_commune_locked,0),
               COALESCE(e.is_province_locked,0)
        FROM survey_batches b
        LEFT JOIN survey_commune_execution_states e ON e.survey_batch_id=b.id
        WHERE b.school_year_id=?
        ORDER BY b.commune_id,b.id
        """,
        (CURRENT_YEAR_ID,)
    ).fetchall()

def per_batch_metrics(conn, batch_id, commune_id):
    metrics = {}

    metrics["households"] = count(
        conn, "SELECT COUNT(*) FROM households WHERE commune_id=? AND is_active=1", (commune_id,)
    )
    metrics["people"] = count(
        conn,
        """
        SELECT COUNT(*)
        FROM survey_people p
        JOIN households h ON h.id=p.household_id
        WHERE h.commune_id=? AND p.is_active=1
        """,
        (commune_id,)
    )

    metrics["forms"] = count(
        conn, "SELECT COUNT(*) FROM survey_forms WHERE survey_batch_id=?", (batch_id,)
    )
    metrics["forms_completed"] = count(
        conn,
        "SELECT COUNT(*) FROM survey_forms WHERE survey_batch_id=? AND status='DA_HOAN_THANH'",
        (batch_id,)
    )
    metrics["forms_other"] = metrics["forms"] - metrics["forms_completed"]

    metrics["year_records"] = count(
        conn,
        "SELECT COUNT(*) FROM survey_person_year_records WHERE school_year_id=? AND survey_form_id IN "
        "(SELECT id FROM survey_forms WHERE survey_batch_id=?)",
        (CURRENT_YEAR_ID, batch_id)
    )

    metrics["form_investigator_links"] = count(
        conn,
        "SELECT COUNT(*) FROM survey_form_investigators WHERE survey_form_id IN "
        "(SELECT id FROM survey_forms WHERE survey_batch_id=?)",
        (batch_id,)
    )
    metrics["forms_with_exact_3_investigators"] = count(
        conn,
        """
        SELECT COUNT(*) FROM (
            SELECT f.id
            FROM survey_forms f
            LEFT JOIN survey_form_investigators i ON i.survey_form_id=f.id
            WHERE f.survey_batch_id=?
            GROUP BY f.id
            HAVING COUNT(i.id)=3
        )
        """,
        (batch_id,)
    )

    metrics["team_form_links"] = count(
        conn,
        "SELECT COUNT(*) FROM survey_investigation_team_forms WHERE survey_form_id IN "
        "(SELECT id FROM survey_forms WHERE survey_batch_id=?)",
        (batch_id,)
    )

    metrics["teams"] = count(
        conn, "SELECT COUNT(*) FROM survey_investigation_teams WHERE survey_batch_id=?", (batch_id,)
    )
    metrics["teams_sent"] = count(
        conn,
        "SELECT COUNT(*) FROM survey_investigation_teams WHERE survey_batch_id=? AND status='SENT'",
        (batch_id,)
    )
    metrics["teams_with_exact_3_members"] = count(
        conn,
        """
        SELECT COUNT(*) FROM (
            SELECT t.id
            FROM survey_investigation_teams t
            LEFT JOIN survey_investigation_team_members m ON m.team_id=t.id
            WHERE t.survey_batch_id=?
            GROUP BY t.id
            HAVING COUNT(m.id)=3
        )
        """,
        (batch_id,)
    )
    metrics["teams_with_mn_th_thcs"] = count(
        conn,
        """
        SELECT COUNT(*) FROM (
            SELECT t.id
            FROM survey_investigation_teams t
            JOIN survey_investigation_team_members m ON m.team_id=t.id
            WHERE t.survey_batch_id=?
            GROUP BY t.id
            HAVING COUNT(m.id)=3
               AND COUNT(DISTINCT UPPER(COALESCE(m.level_code,'')))=3
               AND SUM(CASE WHEN UPPER(COALESCE(m.level_code,''))='MN' THEN 1 ELSE 0 END)=1
               AND SUM(CASE WHEN UPPER(COALESCE(m.level_code,''))='TH' THEN 1 ELSE 0 END)=1
               AND SUM(CASE WHEN UPPER(COALESCE(m.level_code,''))='THCS' THEN 1 ELSE 0 END)=1
        )
        """,
        (batch_id,)
    )

    metrics["participant_submissions"] = count(
        conn, "SELECT COUNT(*) FROM survey_participant_submissions WHERE survey_batch_id=?", (batch_id,)
    )
    metrics["participant_submissions_sent"] = count(
        conn,
        "SELECT COUNT(*) FROM survey_participant_submissions WHERE survey_batch_id=? AND status='SENT'",
        (batch_id,)
    )

    metrics["school_assignments"] = count(
        conn, "SELECT COUNT(*) FROM survey_school_assignments WHERE survey_batch_id=?", (batch_id,)
    )
    metrics["school_assignments_sent"] = count(
        conn,
        "SELECT COUNT(*) FROM survey_school_assignments WHERE survey_batch_id=? AND status='DA_GUI_XA'",
        (batch_id,)
    )
    metrics["school_assignments_locked"] = count(
        conn,
        "SELECT COUNT(*) FROM survey_school_assignments WHERE survey_batch_id=? AND COALESCE(is_locked,0)=1",
        (batch_id,)
    )

    metrics["areas"] = count(
        conn,
        "SELECT COUNT(*) FROM survey_commune_areas WHERE school_year_id=? AND commune_id=? AND is_active=1",
        (CURRENT_YEAR_ID, commune_id)
    )

    metrics["import_jobs"] = count(
        conn, "SELECT COUNT(*) FROM survey_household_import_jobs WHERE survey_batch_id=?", (batch_id,)
    )
    metrics["import_jobs_updated"] = count(
        conn,
        "SELECT COUNT(*) FROM survey_household_import_jobs WHERE survey_batch_id=? AND status='DA_CAP_NHAT'",
        (batch_id,)
    )
    metrics["import_jobs_error"] = count(
        conn,
        "SELECT COUNT(*) FROM survey_household_import_jobs WHERE survey_batch_id=? AND status='LOI_DU_LIEU'",
        (batch_id,)
    )

    metrics["file_exchange_success"] = count(
        conn,
        "SELECT COUNT(*) FROM survey_file_exchange_logs WHERE survey_batch_id=? AND status='THANH_CONG'",
        (batch_id,)
    )

    return metrics

def classify_row(batch_status, batch_locked, commune_locked, province_locked, m):
    reasons = []

    if province_locked:
        return "PROVINCE_LOCKED", "Đợt đã khóa cấp Sở"
    if commune_locked:
        return "COMMUNE_LOCKED", "Địa bàn đã khóa cấp xã"
    if batch_locked:
        return "BATCH_LOCKED", "survey_batches.is_locked=1"

    if m["forms"] == 0 and m["households"] == 0 and m["teams"] == 0:
        return "NO_DATA_YET", "Chưa có hộ/phiếu/tổ điều tra"

    if m["forms"] > 0 and m["forms_completed"] != m["forms"]:
        reasons.append("Còn phiếu chưa hoàn thành")
    if m["forms"] > 0 and m["forms_with_exact_3_investigators"] != m["forms"]:
        reasons.append("Phiếu chưa đủ đúng 3 điều tra viên")
    if m["teams"] > 0 and m["teams_with_exact_3_members"] != m["teams"]:
        reasons.append("Tổ chưa đủ đúng 3 thành viên")
    if m["teams"] > 0 and m["teams_with_mn_th_thcs"] != m["teams"]:
        reasons.append("Tổ chưa đủ cơ cấu MN+TH+THCS")
    if m["forms"] > 0 and m["team_form_links"] != m["forms"]:
        reasons.append("Phiếu chưa được gắn đúng 1 tổ")
    if m["school_assignments"] > 0 and m["school_assignments_sent"] != m["school_assignments"]:
        reasons.append("Còn phân công trường chưa gửi xã")

    if reasons:
        return "BLOCKED_BY_DATA", "; ".join(reasons)

    if m["school_assignments"] > 0 and m["school_assignments_sent"] == m["school_assignments"]:
        if m["forms"] > 0 and m["forms_completed"] == m["forms"]:
            return "CANDIDATE_SCHOOL_LOCK_REVIEW", "Đã gửi xã và toàn bộ phiếu hiện có hoàn thành; cần đối chiếu đúng logic source code trước khi khóa"

    if m["forms"] > 0 and m["forms_completed"] == m["forms"]:
        return "DATA_COMPLETE_NO_LOCK_ACTION", "Phiếu hoàn thành nhưng chưa đủ bằng chứng workflow để tự khóa"

    return "IN_PROGRESS_OR_SETUP", "Có dữ liệu nhưng chưa đủ điều kiện khóa"

def survey_readiness(conn):
    log("\n" + "="*160)
    log("2. MA TRẬN SẴN SÀNG KHÓA 130 XÃ/PHƯỜNG")
    log("CHỈ ĐỌC - KHÔNG TỰ KHÓA")
    log("="*160)

    rows = []
    classes = Counter()

    for b in batch_rows(conn):
        batch_id, year_id, commune_id, code, name, status, batch_locked, commune_locked, province_locked = b
        m = per_batch_metrics(conn, batch_id, commune_id)
        cls, reason = classify_row(
            status, int(batch_locked or 0), int(commune_locked or 0), int(province_locked or 0), m
        )
        classes[cls] += 1

        row = {
            "survey_batch_id": batch_id,
            "commune_id": commune_id,
            "batch_code": code,
            "batch_status": status,
            "batch_is_locked": int(batch_locked or 0),
            "commune_is_locked": int(commune_locked or 0),
            "province_is_locked": int(province_locked or 0),
            **m,
            "classification": cls,
            "reason": reason,
        }
        rows.append(row)

    with READINESS_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else [])
        if rows:
            w.writeheader()
            w.writerows(rows)

    log("READINESS_CLASS_COUNTS =", dict(classes))
    for row in rows:
        if row["classification"] != "NO_DATA_YET":
            log("READINESS_NONEMPTY =", json.dumps(row, ensure_ascii=False, default=str))

    log("READINESS_CSV =", READINESS_CSV)

    # Kiểm tra 1-1 batch ↔ execution_state.
    total_batches = len(rows)
    state_count = count(conn, "SELECT COUNT(*) FROM survey_commune_execution_states")
    distinct_state_batches = count(conn, "SELECT COUNT(DISTINCT survey_batch_id) FROM survey_commune_execution_states")
    duplicate_state_batches = group_counts(
        conn,
        "SELECT survey_batch_id,COUNT(*) FROM survey_commune_execution_states "
        "GROUP BY survey_batch_id HAVING COUNT(*)<>1 ORDER BY survey_batch_id"
    )
    log("BATCH_COUNT =", total_batches)
    log("EXECUTION_STATE_COUNT =", state_count)
    log("DISTINCT_EXECUTION_STATE_BATCHES =", distinct_state_batches)
    log("EXECUTION_STATE_DUPLICATES =", duplicate_state_batches)

    province_ready = (
        total_batches == 130
        and state_count == 130
        and count(conn, "SELECT COUNT(*) FROM survey_commune_execution_states WHERE is_commune_locked=1") == 130
    )
    log("PROVINCE_LOCK_READY_BY_STATE_ONLY =", "YES" if province_ready else "NO")
    return rows, classes

def source_code_hits():
    log("\n" + "="*160)
    log("3. RÀ SOURCE CODE ĐỂ KHÓA ĐÚNG LUỒNG TRƯỜNG → XÃ → SỞ")
    log("CHỈ ĐỌC FILE .PY/.HTML/.JS")
    log("="*160)

    roots = [ROOT / "app"]
    hits = []
    checked = 0

    for base in roots:
        if not base.exists():
            continue
        for p in base.rglob("*"):
            if not p.is_file():
                continue
            if any(part.lower() in SKIP_DIRS for part in p.parts):
                continue
            if p.suffix.lower() not in {".py", ".html", ".js", ".jinja2"}:
                continue
            try:
                if p.stat().st_size > 5 * 1024 * 1024:
                    continue
                text = p.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            checked += 1
            lines = text.splitlines()

            for i, line in enumerate(lines):
                if any(term.lower() in line.lower() for term in SOURCE_CODE_TERMS):
                    start = max(0, i - 4)
                    end = min(len(lines), i + 5)
                    snippet = "\n".join(
                        f"{j+1:05d}: {lines[j]}" for j in range(start, end)
                    )
                    hits.append((str(p.relative_to(ROOT)), i + 1, snippet))

    log("SOURCE_FILES_CHECKED =", checked)
    log("SOURCE_CODE_HIT_COUNT =", len(hits))
    for path, line_no, snippet in hits[:350]:
        log("\nSOURCE_HIT_FILE =", path, "LINE =", line_no)
        log(snippet)
    if len(hits) > 350:
        log("SOURCE_CODE_HITS_TRUNCATED =", len(hits) - 350)

    return hits

def low_count_workflow_rows(conn):
    log("\n" + "="*160)
    log("4. DÒNG WORKFLOW THỰC TẾ - KHÔNG HIỂN THỊ DỮ LIỆU CÁ NHÂN")
    log("="*160)

    queries = {
        "survey_school_assignments": """
            SELECT id,survey_batch_id,school_id,status,is_locked,
                   assigned_at,submitted_at,reviewed_at,locked_at,lock_reason
            FROM survey_school_assignments ORDER BY id
        """,
        "survey_participant_submissions": """
            SELECT id,survey_batch_id,school_id,status,sent_at
            FROM survey_participant_submissions ORDER BY id
        """,
        "survey_investigation_teams": """
            SELECT id,survey_batch_id,commune_id,team_number,status,generation_code
            FROM survey_investigation_teams ORDER BY id
        """,
        "survey_execution_workflow_logs": """
            SELECT id,survey_batch_id,school_id,action,reason,form_total,completed_form_total,created_at
            FROM survey_execution_workflow_logs ORDER BY id
        """,
        "survey_batch_lock_logs": """
            SELECT id,survey_batch_id,action,reason,form_total,completed_form_total,
                   blocking_issue_total,previous_status,new_status,created_at
            FROM survey_batch_lock_logs ORDER BY id
        """,
        "survey_team_generation_logs": """
            SELECT id,survey_batch_id,commune_id,generation_code,action,team_count,
                   household_count,mn_count,th_count,thcs_count,reserve_count,created_at
            FROM survey_team_generation_logs ORDER BY id
        """,
        "survey_team_registration_logs": """
            SELECT id,survey_batch_id,school_id,action,participant_count,created_at
            FROM survey_team_registration_logs ORDER BY id
        """,
        "survey_household_import_jobs": """
            SELECT id,job_code,survey_batch_id,school_year_id,commune_id,status,stage,
                   rows_total,rows_valid,rows_error,conflict_count,
                   households_created,households_updated,people_created,people_updated
            FROM survey_household_import_jobs ORDER BY id
        """,
    }

    for name, sql in queries.items():
        if not table_exists(conn, name):
            continue
        try:
            rows = conn.execute(sql).fetchall()
        except sqlite3.Error as e:
            log(name, "QUERY_ERROR =", repr(e))
            continue
        log(name.upper(), "ROWS =", rows)

def main():
    global LOG
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    LOG = OUT.open("w", encoding="utf-8-sig", newline="\n")

    log("="*160)
    log("BATCH DỮ LIỆU HẬU SÁP NHẬP TOÀN TỈNH 06")
    log("SỬA GÓI MANUAL 3 NGUỒN + MA TRẬN KHÓA 130 XÃ + RÀ SOURCE CODE WORKFLOW")
    log("CHỈ ĐỌC DATABASE - KHÔNG GHI DB")
    log("="*160)

    sha = sha256_file(DB)
    log("DB_SHA =", sha)
    log("EXPECTED_DB_SHA =", EXPECTED_DB_SHA)
    if sha != EXPECTED_DB_SHA:
        log("STOP = DB SHA khác nền Batch 05.")
        return 1

    conn = sqlite3.connect(DB.resolve().as_uri() + "?mode=ro", uri=True, timeout=60)
    conn.execute("PRAGMA query_only=ON")

    try:
        integ = conn.execute("PRAGMA integrity_check").fetchone()[0]
        fk = conn.execute("PRAGMA foreign_key_check").fetchall()
        log("INTEGRITY =", integ)
        log("FK =", len(fk))
        if integ != "ok" or fk:
            log("STOP = Database health không đạt.")
            return 1

        manual_rows = manual_v2_export(conn)
        readiness_rows, readiness_classes = survey_readiness(conn)
        source_hits = source_code_hits()
        low_count_workflow_rows(conn)

        log("\n" + "="*160)
        log("KẾT LUẬN BATCH 06")
        log("="*160)
        log("MANUAL_V2_ROWS =", manual_rows)
        log("READINESS_ROWS =", len(readiness_rows))
        log("READINESS_CLASSES =", dict(readiness_classes))
        log("SOURCE_CODE_HITS =", len(source_hits))
        log("DB_SHA_AFTER_READ_ONLY =", sha256_file(DB))
        log("DATABASE_WRITES_THIS_RUN = 0")
        log("BATCH_06_SUCCESS = YES")
        log("NEXT_STAGE = Từ trạng thái thực tế + source code hit, tạo Batch 07 chỉ ghi các chuyển trạng thái/khóa được code hiện tại cho phép; không tự khóa 130 xã khi chưa đủ dữ liệu.")
        log("="*160)
        return 0
    finally:
        conn.close()
        if LOG:
            LOG.close()

if __name__ == "__main__":
    try:
        code = main()
    except Exception as exc:
        try:
            log("\nBATCH_06_SUCCESS = NO")
            log("ERROR =", repr(exc))
            if DB.exists():
                log("DB_SHA_CURRENT =", sha256_file(DB))
        finally:
            if LOG and not LOG.closed:
                LOG.close()
        code = 1
    sys.exit(code)
