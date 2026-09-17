# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(r"C:\PhoCap")
DB = ROOT / "data" / "phocap.db"
EXPORT_DIR = ROOT / "exports"

OUT = EXPORT_DIR / "BATCH_NGHIEP_VU_CON_LAI_TOAN_TINH_08.txt"
PLAN_JSON = EXPORT_DIR / "BATCH_NGHIEP_VU_CON_LAI_TOAN_TINH_08_PLAN.json"

# Nền ngay sau Batch 07B.
EXPECTED_DB_SHA = "8899ba224b3d88e7e66f92d67b1dd83adf76667022986c06ebc3b109863a22a2"

BASE_YEAR_ID = 1
CURRENT_YEAR_ID = 2
FUTURE_YEAR_ID = 8

MANUAL_SPLIT_SOURCE_IDS = {1510, 1522, 1658}

DOMAIN_KEYWORDS = {
    "students": ("student", "enrollment", "class"),
    "staff": ("staff", "teacher", "employee"),
    "survey": ("survey", "household", "investigation", "enumerator"),
    "comparison": ("comparison", "reconcile", "reconciliation", "doi_chieu", "followup"),
    "disability": ("disab", "khuyet", "special_circumstance"),
    "facilities": ("facility", "equipment", "csvc", "tbdh"),
    "finance": ("finance", "financial", "tai_chinh"),
    "standards": ("standard", "criterion", "criteria", "tieu_chuan"),
    "historical": ("historical", "baseline", "history_dataset"),
    "reports": ("report", "summary", "indicator", "statistic"),
}

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

def table_names(conn):
    return [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()]

def table_info(conn, table):
    return conn.execute(f"PRAGMA table_info({qi(table)})").fetchall()

def cols(conn, table):
    return [r[1] for r in table_info(conn, table)]

def count(conn, table, where="", params=()):
    sql = f"SELECT COUNT(*) FROM {qi(table)}"
    if where:
        sql += " WHERE " + where
    try:
        return int(conn.execute(sql, params).fetchone()[0])
    except sqlite3.Error:
        return None

def year_column(conn, table):
    c = cols(conn, table)
    for cand in ("school_year_id", "year_id"):
        if cand in c:
            return cand
    return None

def active_school_ids(conn):
    return [int(r[0]) for r in conn.execute(
        "SELECT id FROM schools WHERE is_active=1 ORDER BY id"
    ).fetchall()]

def classify_domain(table):
    low = table.lower()
    matches = []
    for domain, kws in DOMAIN_KEYWORDS.items():
        if any(k in low for k in kws):
            matches.append(domain)
    return matches or ["other"]

def statewide_table_profile(conn, table):
    c = cols(conn, table)
    yc = year_column(conn, table)
    profile = {
        "table": table,
        "count": count(conn, table),
        "columns": c,
        "year_column": yc,
        "domains": classify_domain(table),
    }

    if yc:
        profile["year_counts"] = {
            str(y): count(conn, table, f"{qi(yc)}=?", (y,))
            for y in (BASE_YEAR_ID, CURRENT_YEAR_ID, FUTURE_YEAR_ID)
        }

    if "school_id" in c and yc:
        active_ids = active_school_ids(conn)
        base_coverage = 0
        current_coverage = 0
        missing_y2 = []
        y2_without_y1 = []

        for sid in active_ids:
            y1 = count(conn, table, f"school_id=? AND {qi(yc)}=?", (sid, BASE_YEAR_ID)) or 0
            y2 = count(conn, table, f"school_id=? AND {qi(yc)}=?", (sid, CURRENT_YEAR_ID)) or 0
            if y1 > 0:
                base_coverage += 1
            if y2 > 0:
                current_coverage += 1
            if y1 > 0 and y2 == 0:
                missing_y2.append(sid)
            if y1 == 0 and y2 > 0:
                y2_without_y1.append(sid)

        profile["active_school_coverage"] = {
            "base_year_schools": base_coverage,
            "current_year_schools": current_coverage,
            "missing_y2_school_count": len(missing_y2),
            "missing_y2_school_ids": missing_y2[:300],
            "y2_without_y1_school_count": len(y2_without_y1),
            "y2_without_y1_school_ids": y2_without_y1[:300],
        }

    return profile

def verify_survey_lock_state(conn):
    result = {}

    result["batch_total_y2"] = conn.execute(
        "SELECT COUNT(*) FROM survey_batches WHERE school_year_id=?",
        (CURRENT_YEAR_ID,)
    ).fetchone()[0]

    result["commune_locked"] = conn.execute(
        """
        SELECT COUNT(*)
        FROM survey_commune_execution_states es
        JOIN survey_batches b ON b.id=es.survey_batch_id
        WHERE b.school_year_id=? AND es.is_commune_locked=1
        """,
        (CURRENT_YEAR_ID,)
    ).fetchone()[0]

    result["province_locked"] = conn.execute(
        """
        SELECT COUNT(*)
        FROM survey_commune_execution_states es
        JOIN survey_batches b ON b.id=es.survey_batch_id
        WHERE b.school_year_id=? AND es.is_province_locked=1
        """,
        (CURRENT_YEAR_ID,)
    ).fetchone()[0]

    result["locked_batches"] = conn.execute(
        "SELECT COUNT(*) FROM survey_batches WHERE school_year_id=? AND is_locked=1",
        (CURRENT_YEAR_ID,)
    ).fetchone()[0]

    result["batch114"] = conn.execute(
        """
        SELECT b.id,b.status,b.is_locked,
               es.is_commune_locked,es.is_province_locked,
               es.commune_locked_by_user_id
        FROM survey_batches b
        JOIN survey_commune_execution_states es ON es.survey_batch_id=b.id
        WHERE b.id=114
        """
    ).fetchone()

    result["assignment1606"] = conn.execute(
        """
        SELECT id,status,is_locked,locked_by_user_id
        FROM survey_school_assignments
        WHERE survey_batch_id=114 AND school_id=1606
        """
    ).fetchone()

    result["workflow_logs_114"] = conn.execute(
        """
        SELECT id,action,school_id,actor_user_id,form_total,completed_form_total
        FROM survey_execution_workflow_logs
        WHERE survey_batch_id=114
        ORDER BY id
        """
    ).fetchall()

    return result

def manual_split_audit(conn):
    rows = []
    for sid in sorted(MANUAL_SPLIT_SOURCE_IDS):
        school = conn.execute(
            "SELECT id,commune_id,code,name,is_active FROM schools WHERE id=?",
            (sid,)
        ).fetchone()
        staff_y1 = conn.execute(
            "SELECT COUNT(*) FROM staff_year_records WHERE school_id=? AND school_year_id=?",
            (sid, BASE_YEAR_ID)
        ).fetchone()[0]
        staff_y2 = conn.execute(
            "SELECT COUNT(*) FROM staff_year_records WHERE school_id=? AND school_year_id=?",
            (sid, CURRENT_YEAR_ID)
        ).fetchone()[0]
        rows.append({
            "school": school,
            "staff_y1": staff_y1,
            "staff_y2": staff_y2,
        })
    return rows

def main():
    global LOG
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    LOG = OUT.open("w", encoding="utf-8-sig", newline="\n")

    log("=" * 160)
    log("BATCH NGHIỆP VỤ CÒN LẠI TOÀN TỈNH 08")
    log("ĐÓNG KIỂM TRA LUỒNG KHÓA 114 + KIỂM TOÁN CÁC PHÂN HỆ DỮ LIỆU CÒN LẠI")
    log("CHỈ ĐỌC DATABASE - KHÔNG GHI DB")
    log("=" * 160)

    sha = sha256_file(DB)
    log("DB_SHA =", sha)
    log("EXPECTED_DB_SHA =", EXPECTED_DB_SHA)

    if sha != EXPECTED_DB_SHA:
        log("STOP = DB SHA khác nền sau Batch 07B.")
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

        log("\n" + "=" * 160)
        log("1. XÁC NHẬN LUỒNG KHÓA SAU BATCH 07B")
        log("=" * 160)
        survey_state = verify_survey_lock_state(conn)
        log("SURVEY_LOCK_STATE =", json.dumps(
            survey_state, ensure_ascii=False, default=str
        ))

        # Bắt buộc đúng trạng thái sau 07B.
        expected_ok = (
            survey_state["batch_total_y2"] == 130
            and survey_state["commune_locked"] == 1
            and survey_state["province_locked"] == 0
            and survey_state["locked_batches"] == 1
            and survey_state["batch114"] is not None
            and int(survey_state["batch114"][2] or 0) == 1
            and int(survey_state["batch114"][3] or 0) == 1
            and int(survey_state["batch114"][4] or 0) == 0
            and survey_state["assignment1606"] is not None
            and str(survey_state["assignment1606"][1]) == "DA_HOAN_THANH"
            and int(survey_state["assignment1606"][2] or 0) == 1
        )
        log("BATCH07B_POST_STATE_OK =", "YES" if expected_ok else "NO")
        if not expected_ok:
            log("STOP = Trạng thái khóa sau Batch 07B không đúng kỳ vọng.")
            return 1

        log("\n" + "=" * 160)
        log("2. KIỂM TRA 3 NGUỒN TÁCH ĐIỂM CÒN MANUAL")
        log("=" * 160)
        manual = manual_split_audit(conn)
        log("MANUAL_SPLIT_AUDIT =", json.dumps(
            manual, ensure_ascii=False, default=str
        ))

        log("\n" + "=" * 160)
        log("3. KIỂM TOÁN CÁC BẢNG NGHIỆP VỤ TOÀN HỆ THỐNG")
        log("=" * 160)

        profiles = []
        domain_map = defaultdict(list)

        for t in table_names(conn):
            p = statewide_table_profile(conn, t)
            profiles.append(p)
            for d in p["domains"]:
                domain_map[d].append(t)

            # Chỉ in chi tiết các bảng có liên quan nghiệp vụ.
            if p["domains"] != ["other"]:
                log("\nTABLE_PROFILE =", json.dumps(
                    p, ensure_ascii=False, default=str
                ))

        log("\n" + "=" * 160)
        log("4. TỔNG HỢP THEO PHÂN HỆ")
        log("=" * 160)
        for domain in sorted(domain_map):
            if domain == "other":
                continue
            log("DOMAIN", domain.upper(), "TABLES =", domain_map[domain])

        # Chọn các bảng có baseline y1 nhưng y2 còn trống/thiếu để Batch 09 xét riêng.
        action_candidates = []
        for p in profiles:
            yc = p.get("year_column")
            if not yc:
                continue

            yc_counts = p.get("year_counts") or {}
            y1 = yc_counts.get(str(BASE_YEAR_ID)) or 0
            y2 = yc_counts.get(str(CURRENT_YEAR_ID)) or 0

            coverage = p.get("active_school_coverage")
            missing_count = (
                coverage.get("missing_y2_school_count", 0)
                if coverage else 0
            )

            if y1 > 0 and (y2 == 0 or missing_count > 0):
                action_candidates.append({
                    "table": p["table"],
                    "domains": p["domains"],
                    "year_column": yc,
                    "y1_rows": y1,
                    "y2_rows": y2,
                    "missing_y2_school_count": missing_count,
                    "missing_y2_school_ids": (
                        coverage.get("missing_y2_school_ids", [])
                        if coverage else []
                    ),
                })

        log("\nACTION_CANDIDATES =", json.dumps(
            action_candidates, ensure_ascii=False, default=str
        ))

        plan = {
            "db_sha": sha,
            "survey_lock_state": survey_state,
            "manual_split_sources": manual,
            "domain_tables": dict(domain_map),
            "profiles": profiles,
            "action_candidates": action_candidates,
            "policy": {
                "province_lock": "KHONG_KHOA - 129 xa chua co du lieu",
                "manual_split_sources": "KHONG_TU_CHIA_NHAN_SU",
                "future_year_id_8": "CHI_QUAN_SAT_KHONG_GHI",
                "next_step": (
                    "Batch 09 chi xu ly bang co baseline va quy tac rollover "
                    "an toan; cac bang trong nhu tai chinh/CSVC khong tu tao du lieu gia."
                ),
            },
        }

        PLAN_JSON.write_text(
            json.dumps(plan, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8-sig"
        )

        log("\n" + "=" * 160)
        log("5. KẾT LUẬN")
        log("=" * 160)
        log("ACTION_CANDIDATE_COUNT =", len(action_candidates))
        log("PLAN_JSON =", PLAN_JSON)
        log("DATABASE_WRITES_THIS_RUN = 0")
        log("DB_SHA_AFTER_READ_ONLY =", sha256_file(DB))
        log("BATCH_08_SUCCESS = YES")
        log(
            "NEXT_STAGE = Dùng ACTION_CANDIDATES để tạo Batch 09 theo nhóm lớn: "
            "đối chiếu/học sinh, dữ liệu lịch sử, khuyết tật, CSVC-TBDH, tài chính, "
            "tiêu chuẩn và báo cáo; chỉ ghi những bảng có quy tắc rollover rõ ràng."
        )
        log("=" * 160)

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
            log("\nBATCH_08_SUCCESS = NO")
            log("ERROR =", repr(exc))
            if DB.exists():
                log("DB_SHA_CURRENT =", sha256_file(DB))
        finally:
            if LOG and not LOG.closed:
                LOG.close()
        code = 1
    sys.exit(code)
