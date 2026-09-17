# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(r"C:\PhoCap")
DB = ROOT / "data" / "phocap.db"
BACKUP_DIR = ROOT / "backups"
EXPORT_DIR = ROOT / "exports"
OUT = EXPORT_DIR / "BATCH_DU_LIEU_HAU_SAP_NHAP_TOAN_TINH_03.txt"

# Nền ngay sau Batch 02.
EXPECTED_DB_SHA = "5f7b493d346afb980d01d1c602922f689949344d6db3ab9bd122040d00b62636"

BASE_YEAR_ID = 1
CURRENT_YEAR_ID = 2
FUTURE_YEAR_ID = 8

# Hai trường Batch 02 giữ lại vì có 1 nhân sự đã có record 2026-2027 ở trường khác.
CONFLICT_SCHOOL_IDS = {101, 743}

# Năm nguồn của 5 ca tách điểm: tuyệt đối chưa tự động chuyển/rollover.
BLOCKED_MANUAL_SOURCE_IDS = {1510, 1522, 1580, 1583, 1658}

EXCLUDED_STATUS_CODES = {"NGHI_HUU", "CHUYEN_DI", "THOI_VIEC", "DA_NGHI"}
EXCLUDED_STATUS_LABELS = {"Đã nghỉ hưu", "Đã chuyển đi", "Nghỉ hưu", "Chuyển đi"}

LOG = None

def log(*args):
    s = " ".join(str(x) for x in args)
    print(s)
    if LOG:
        LOG.write(s + "\n")
        LOG.flush()

def fail(msg):
    raise RuntimeError(msg)

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

def rows_hash(cur):
    names = [d[0] for d in cur.description]
    rows = []
    for r in cur.fetchall():
        d = {}
        for i, n in enumerate(names):
            v = r[i]
            if isinstance(v, (bytes, bytearray)):
                v = {"__blob_sha256__": hashlib.sha256(bytes(v)).hexdigest()}
            d[n] = v
        rows.append(d)
    return hashlib.sha256(
        json.dumps(rows, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()

def old_rows_baseline(conn, table):
    if "id" not in cols(conn, table):
        return None
    max_id = int(conn.execute(
        f"SELECT COALESCE(MAX(id),0) FROM {qi(table)}"
    ).fetchone()[0])
    h = rows_hash(conn.execute(
        f"SELECT * FROM {qi(table)} WHERE id<=? ORDER BY id", (max_id,)
    ))
    return max_id, h

def old_rows_unchanged(conn, table, baseline):
    if baseline is None:
        return True
    max_id, old_hash = baseline
    now_hash = rows_hash(conn.execute(
        f"SELECT * FROM {qi(table)} WHERE id<=? ORDER BY id", (max_id,)
    ))
    return now_hash == old_hash

def make_backup():
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = BACKUP_DIR / f"backup_truoc_BATCH_DU_LIEU_03_{ts}.db"

    src = sqlite3.connect(str(DB), timeout=60)
    dst = sqlite3.connect(str(path), timeout=60)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()

    ro = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=30)
    try:
        integ = ro.execute("PRAGMA integrity_check").fetchone()[0]
        fk = ro.execute("PRAGMA foreign_key_check").fetchall()
    finally:
        ro.close()

    if integ != "ok" or fk:
        fail(f"Backup không đạt: integrity={integ}, fk={len(fk)}")
    return path

def school(conn, sid):
    return conn.execute(
        "SELECT id,commune_id,code,name,is_active FROM schools WHERE id=?",
        (sid,)
    ).fetchone()

def active_school_ids(conn):
    return [int(r[0]) for r in conn.execute(
        "SELECT id FROM schools WHERE is_active=1 ORDER BY id"
    ).fetchall()]

def read_rows(conn, table, sid, year_id):
    cur = conn.execute(
        f"SELECT * FROM {qi(table)} "
        "WHERE school_id=? AND school_year_id=? ORDER BY id",
        (sid, year_id)
    )
    names = [d[0] for d in cur.description]
    return [dict(zip(names, r)) for r in cur.fetchall()]

def count_school_year(conn, table, sid, year_id):
    return int(conn.execute(
        f"SELECT COUNT(*) FROM {qi(table)} "
        "WHERE school_id=? AND school_year_id=?",
        (sid, year_id)
    ).fetchone()[0])

def clone_rows(conn, table, rows, mutate):
    insert_cols = [r[1] for r in table_info(conn, table) if r[1] != "id"]
    sql = (
        f"INSERT INTO {qi(table)} ({', '.join(qi(c) for c in insert_cols)}) "
        f"VALUES ({', '.join('?' for _ in insert_cols)})"
    )
    created = 0
    for row in rows:
        d = dict(row)
        mutate(d)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
        if "created_at" in d:
            d["created_at"] = now
        if "updated_at" in d:
            d["updated_at"] = now
        conn.execute(sql, [d.get(c) for c in insert_cols])
        created += 1
    return created

def status_excluded(row):
    if "is_active" in row and int(row.get("is_active") or 0) != 1:
        return True, "is_active!=1"
    status = str(row.get("status_code") or "").strip().upper()
    label = str(row.get("source_status_label") or "").strip()
    if status in EXCLUDED_STATUS_CODES:
        return True, "status_code=" + status
    if label in EXCLUDED_STATUS_LABELS:
        return True, "source_status_label=" + label
    return False, ""

def duplicate_staff_y2(conn):
    return conn.execute(
        """
        SELECT staff_member_id,COUNT(*),GROUP_CONCAT(school_id)
        FROM staff_year_records
        WHERE school_year_id=?
        GROUP BY staff_member_id
        HAVING COUNT(*)>1
        ORDER BY staff_member_id
        """,
        (CURRENT_YEAR_ID,)
    ).fetchall()

def tx_resolve_two_staff_conflicts(conn):
    log("\n" + "="*160)
    log("TRANSACTION A - HOÀN TẤT 2 TRƯỜNG STAFF CONFLICT")
    log("="*160)

    plan = {}
    total_insert = 0

    for sid in sorted(CONFLICT_SCHOOL_IDS):
        s = school(conn, sid)
        if not s or int(s[4]) != 1:
            fail(f"Conflict school {sid} không active")

        y1 = read_rows(conn, "staff_year_records", sid, BASE_YEAR_ID)
        y2_here = read_rows(conn, "staff_year_records", sid, CURRENT_YEAR_ID)
        if not y1 or y2_here:
            fail(f"Conflict school {sid} không còn đúng footprint y1>0/y2=0")

        include = []
        excluded_status = []
        existing_elsewhere = []

        for row in y1:
            mid = int(row["staff_member_id"])
            excluded, why = status_excluded(row)
            if excluded:
                excluded_status.append((mid, why))
                continue

            current = conn.execute(
                "SELECT id,school_id,position_group,status_code,source_status_label,is_active "
                "FROM staff_year_records WHERE staff_member_id=? AND school_year_id=? "
                "ORDER BY school_id,id",
                (mid, CURRENT_YEAR_ID)
            ).fetchall()

            if current:
                existing_elsewhere.append((mid, current))
                continue

            include.append(row)

        # Bắt buộc đúng đặc điểm Batch 02: ít nhất một người đã có y2 ở trường khác.
        if not existing_elsewhere:
            fail(f"School {sid} không còn conflict identity như Batch 02")

        for mid, current in existing_elsewhere:
            for r in current:
                target = school(conn, int(r[1]))
                if target is None or int(target[4]) != 1:
                    fail(f"Nhân sự {mid} đang có y2 tại trường không active: {r}")

        member_ids = [int(r["staff_member_id"]) for r in include]
        if len(member_ids) != len(set(member_ids)):
            fail(f"School {sid} có duplicate member trong y1")

        plan[sid] = {
            "school": s,
            "y1_count": len(y1),
            "insert_rows": include,
            "excluded_status": excluded_status,
            "existing_elsewhere": existing_elsewhere,
        }
        total_insert += len(include)

        log("SCHOOL =", s)
        log("Y1_COUNT =", len(y1))
        log("EXCLUDED_STATUS =", excluded_status)
        log("EXISTING_Y2_ELSEWHERE =", existing_elsewhere)
        log("WILL_INSERT =", len(include))

    baseline = old_rows_baseline(conn, "staff_year_records")

    conn.execute("BEGIN IMMEDIATE")
    try:
        created = 0
        for sid, p in plan.items():
            def mutate(d, sid=sid):
                d["school_id"] = sid
                d["school_year_id"] = CURRENT_YEAR_ID
            created += clone_rows(
                conn, "staff_year_records", p["insert_rows"], mutate
            )

        if created != total_insert:
            fail(f"Created {created} != expected {total_insert}")

        if not old_rows_unchanged(conn, "staff_year_records", baseline):
            fail("Record staff cũ bị thay đổi")

        for sid, p in plan.items():
            actual = count_school_year(
                conn, "staff_year_records", sid, CURRENT_YEAR_ID
            )
            if actual != len(p["insert_rows"]):
                fail(f"School {sid} y2 staff {actual} != {len(p['insert_rows'])}")

        dups = duplicate_staff_y2(conn)
        if dups:
            fail(f"Phát sinh duplicate staff y2: {dups[:20]}")

        fk = conn.execute("PRAGMA foreign_key_check").fetchall()
        if fk:
            fail(f"FK lỗi: {fk[:20]}")

        conn.commit()
        log("STAFF_CONFLICT_TRANSACTION = COMMIT")
        log("STAFF_CONFLICT_INSERTED =", created)
        return created

    except Exception:
        conn.rollback()
        log("STAFF_CONFLICT_TRANSACTION = ROLLBACK")
        raise

def official_target_ids(conn):
    return {
        int(r[0]) for r in conn.execute(
            "SELECT DISTINCT target_school_id "
            "FROM school_merger_official_executions "
            "WHERE school_year_id=?",
            (CURRENT_YEAR_ID,)
        ).fetchall()
        if r[0] is not None
    }

def renamed_school_ids(conn):
    if not table_exists(conn, "school_name_histories"):
        return set()
    return {
        int(r[0]) for r in conn.execute(
            "SELECT DISTINCT school_id FROM school_name_histories "
            "WHERE effective_school_year_id=?",
            (CURRENT_YEAR_ID,)
        ).fetchall()
        if r[0] is not None
    }

def tx_rollover_stable_staff_summaries(conn):
    log("\n" + "="*160)
    log("TRANSACTION B - ROLLOVER SCHOOL_STAFF_YEAR_SUMMARIES CHO TRƯỜNG ỔN ĐỊNH")
    log("="*160)

    table = "school_staff_year_summaries"
    if not table_exists(conn, table):
        log("SUMMARY_TRANSACTION = SKIP_TABLE_NOT_FOUND")
        return 0

    targets = official_target_ids(conn)
    renamed = renamed_school_ids(conn)

    log("OFFICIAL_TARGET_IDS_COUNT =", len(targets))
    log("RENAMED_SCHOOL_IDS =", sorted(renamed))
    log("BLOCKED_MANUAL_SOURCE_IDS =", sorted(BLOCKED_MANUAL_SOURCE_IDS))

    candidates = []
    excluded = Counter()

    for sid in active_school_ids(conn):
        y1 = count_school_year(conn, table, sid, BASE_YEAR_ID)
        y2 = count_school_year(conn, table, sid, CURRENT_YEAR_ID)

        if y1 == 0 or y2 > 0:
            continue
        if y1 != 1:
            excluded["Y1_NOT_EXACTLY_ONE"] += 1
            continue
        if sid in targets:
            excluded["OFFICIAL_MERGER_TARGET"] += 1
            continue
        if sid in renamed:
            excluded["RENAMED_CURRENT_YEAR"] += 1
            continue
        if sid in BLOCKED_MANUAL_SOURCE_IDS:
            excluded["MANUAL_SPLIT_SOURCE"] += 1
            continue

        candidates.append((sid, school(conn, sid)))

    log("SUMMARY_SAFE_CANDIDATES =", len(candidates))
    log("SUMMARY_EXCLUDED_COUNTER =", dict(excluded))
    for x in candidates[:100]:
        log(" SUMMARY_CANDIDATE =", x)
    if len(candidates) > 100:
        log(" SUMMARY_CANDIDATE_TRUNCATED =", len(candidates) - 100)

    if not candidates:
        log("SUMMARY_TRANSACTION = SKIP_NO_CANDIDATES")
        return 0

    baseline = old_rows_baseline(conn, table)

    conn.execute("BEGIN IMMEDIATE")
    try:
        created = 0
        for sid, _ in candidates:
            rows = read_rows(conn, table, sid, BASE_YEAR_ID)
            if len(rows) != 1:
                fail(f"School {sid} summary y1 không đúng 1")

            def mutate(d, sid=sid):
                d["school_id"] = sid
                d["school_year_id"] = CURRENT_YEAR_ID
                if "notes" in d:
                    d["notes"] = (
                        "Kế thừa dữ liệu nền 2025-2026 sang 2026-2027; "
                        "đơn vị tiếp tục cập nhật số liệu năm hiện hành."
                    )
                if "updated_by_user_id" in d:
                    # Không mạo danh người cập nhật cũ.
                    d["updated_by_user_id"] = None

            created += clone_rows(conn, table, rows, mutate)

        if created != len(candidates):
            fail(f"Summary created {created} != candidates {len(candidates)}")

        if not old_rows_unchanged(conn, table, baseline):
            fail("Summary cũ bị thay đổi")

        bad = []
        for sid, _ in candidates:
            n = count_school_year(conn, table, sid, CURRENT_YEAR_ID)
            if n != 1:
                bad.append((sid, n))
        if bad:
            fail(f"Summary y2 post count sai: {bad[:20]}")

        fk = conn.execute("PRAGMA foreign_key_check").fetchall()
        if fk:
            fail(f"FK lỗi summary: {fk[:20]}")

        conn.commit()
        log("SUMMARY_TRANSACTION = COMMIT")
        log("SUMMARY_INSERTED =", created)
        return created

    except Exception:
        conn.rollback()
        log("SUMMARY_TRANSACTION = ROLLBACK")
        raise

def audit_remaining(conn):
    log("\n" + "="*160)
    log("AUDIT SAU BATCH 03")
    log("="*160)

    # 1) Staff còn thiếu y2
    missing_staff = []
    for sid in active_school_ids(conn):
        y1 = count_school_year(conn, "staff_year_records", sid, BASE_YEAR_ID)
        y2 = count_school_year(conn, "staff_year_records", sid, CURRENT_YEAR_ID)
        if y1 > 0 and y2 == 0:
            missing_staff.append((sid, y1, school(conn, sid)))

    log("REMAINING_ACTIVE_SCHOOLS_Y1_STAFF_Y2_ZERO =", len(missing_staff))
    for x in missing_staff:
        log(" REMAINING_STAFF =", x)

    # 2) Summary còn thiếu ở những trường đã có staff y2.
    missing_summary = []
    if table_exists(conn, "school_staff_year_summaries"):
        for sid in active_school_ids(conn):
            staff2 = count_school_year(conn, "staff_year_records", sid, CURRENT_YEAR_ID)
            sum2 = count_school_year(
                conn, "school_staff_year_summaries", sid, CURRENT_YEAR_ID
            )
            if staff2 > 0 and sum2 == 0:
                missing_summary.append((sid, staff2, school(conn, sid)))

    log("REMAINING_MISSING_SUMMARY_WITH_Y2_STAFF =", len(missing_summary))
    for x in missing_summary[:200]:
        log(" REMAINING_SUMMARY =", x)
    if len(missing_summary) > 200:
        log(" REMAINING_SUMMARY_TRUNCATED =", len(missing_summary) - 200)

    # 3) Tài khoản trường: chỉ truong_*.
    account_anomalies = []
    cbql_count = 0
    for sid in active_school_ids(conn):
        rows = conn.execute(
            "SELECT id,username,is_active FROM users "
            "WHERE school_id=? AND role_id=3 ORDER BY id",
            (sid,)
        ).fetchall()
        school_accounts = [
            r for r in rows
            if int(r[2] or 0) == 1
            and str(r[1] or "").lower().startswith("truong_")
        ]
        cbql_count += sum(
            1 for r in rows
            if int(r[2] or 0) == 1
            and str(r[1] or "").lower().startswith("cbql.")
        )
        if len(school_accounts) != 1:
            account_anomalies.append((sid, school(conn, sid), rows))

    log("ACTIVE_TRUONG_ACCOUNT_ANOMALIES =", len(account_anomalies))
    log("ACTIVE_CBQL_ACCOUNTS_INFO_ONLY =", cbql_count)

    # 4) 5 nguồn tách điểm.
    manual = []
    for sid in sorted(BLOCKED_MANUAL_SOURCE_IDS):
        manual.append({
            "school": school(conn, sid),
            "staff_y1": count_school_year(
                conn, "staff_year_records", sid, BASE_YEAR_ID
            ),
            "staff_y2": count_school_year(
                conn, "staff_year_records", sid, CURRENT_YEAR_ID
            ),
            "classes_y1": count_school_year(
                conn, "classes", sid, BASE_YEAR_ID
            ) if table_exists(conn, "classes") else None,
            "classes_y2": count_school_year(
                conn, "classes", sid, CURRENT_YEAR_ID
            ) if table_exists(conn, "classes") else None,
            "enroll_y1": count_school_year(
                conn, "student_enrollments", sid, BASE_YEAR_ID
            ) if table_exists(conn, "student_enrollments") else None,
            "enroll_y2": count_school_year(
                conn, "student_enrollments", sid, CURRENT_YEAR_ID
            ) if table_exists(conn, "student_enrollments") else None,
        })
    log("MANUAL_SPLIT_SOURCE_AUDIT =", json.dumps(
        manual, ensure_ascii=False, default=str
    ))

    # 5) các bảng không có baseline thì không tự sinh.
    for t in ("finance_year_entries", "school_facility_year_items",
              "survey_person_year_records"):
        if table_exists(conn, t) and "school_year_id" in cols(conn, t):
            y1 = conn.execute(
                f"SELECT COUNT(*) FROM {qi(t)} WHERE school_year_id=?",
                (BASE_YEAR_ID,)
            ).fetchone()[0]
            y2 = conn.execute(
                f"SELECT COUNT(*) FROM {qi(t)} WHERE school_year_id=?",
                (CURRENT_YEAR_ID,)
            ).fetchone()[0]
            log("TABLE_POLICY", t, "Y1=", y1, "Y2=", y2)

    return {
        "missing_staff": missing_staff,
        "missing_summary": missing_summary,
        "account_anomalies": account_anomalies,
        "manual": manual,
    }

def main():
    global LOG
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    LOG = OUT.open("w", encoding="utf-8-sig", newline="\n")

    log("="*160)
    log("BATCH DỮ LIỆU HẬU SÁP NHẬP TOÀN TỈNH 03")
    log("HOÀN TẤT 2 STAFF CONFLICT + ROLLOVER SUMMARY CHO TRƯỜNG ỔN ĐỊNH")
    log("KHÔNG TỰ ĐỘNG XỬ LÝ 5 NGUỒN TÁCH ĐIỂM")
    log("="*160)

    wal = DB.parent / "phocap.db-wal"
    journal = DB.parent / "phocap.db-journal"
    wal_size = wal.stat().st_size if wal.exists() else 0
    journal_size = journal.stat().st_size if journal.exists() else 0
    log("WAL_SIZE =", wal_size)
    log("JOURNAL_SIZE =", journal_size)
    if wal_size or journal_size:
        fail("WAL/JOURNAL khác 0")

    sha = sha256_file(DB)
    log("DB_SHA_BEFORE =", sha)
    log("EXPECTED_DB_SHA =", EXPECTED_DB_SHA)
    if sha != EXPECTED_DB_SHA:
        fail("DB SHA khác nền Batch 02")

    ro = sqlite3.connect(
        f"file:{DB.as_posix()}?mode=ro", uri=True, timeout=30
    )
    try:
        integ = ro.execute("PRAGMA integrity_check").fetchone()[0]
        fk = ro.execute("PRAGMA foreign_key_check").fetchall()
        log("INTEGRITY_BEFORE =", integ)
        log("FK_BEFORE =", len(fk))
        if integ != "ok" or fk:
            fail("Database health không đạt")
    finally:
        ro.close()

    backup = make_backup()
    log("BACKUP =", backup)
    log("BACKUP_SHA =", sha256_file(backup))

    conn = sqlite3.connect(str(DB), timeout=60)
    conn.execute("PRAGMA foreign_keys=ON")

    try:
        staff_inserted = tx_resolve_two_staff_conflicts(conn)
        summary_inserted = tx_rollover_stable_staff_summaries(conn)
        audit = audit_remaining(conn)

        integ = conn.execute("PRAGMA integrity_check").fetchone()[0]
        fk = conn.execute("PRAGMA foreign_key_check").fetchall()
        dups = duplicate_staff_y2(conn)

        log("\n" + "="*160)
        log("POST VERIFY BATCH 03")
        log("="*160)
        log("INTEGRITY_AFTER =", integ)
        log("FK_AFTER =", len(fk))
        log("DUPLICATE_STAFF_Y2 =", len(dups))
        log("STAFF_CONFLICT_INSERTED =", staff_inserted)
        log("SUMMARY_INSERTED =", summary_inserted)
        log("DB_SHA_AFTER =", sha256_file(DB))

        if integ != "ok" or fk or dups:
            fail("Post verify Batch 03 không đạt")

        # Kỳ vọng sau khi xử lý 2 conflict chỉ còn 5 nguồn tách điểm có y1 staff nhưng y2=0.
        remaining_ids = {int(x[0]) for x in audit["missing_staff"]}
        log("REMAINING_STAFF_IDS =", sorted(remaining_ids))
        log("EXPECTED_MANUAL_SOURCE_IDS =", sorted(BLOCKED_MANUAL_SOURCE_IDS))

        if remaining_ids != BLOCKED_MANUAL_SOURCE_IDS:
            log("WARNING_REMAINING_STAFF_NOT_EXACT_MANUAL_SET = YES")
        else:
            log("REMAINING_STAFF_EXACTLY_5_MANUAL_SOURCES = YES")

        if audit["account_anomalies"]:
            log("ACCOUNT_AUDIT_PASS = NO")
        else:
            log("ACCOUNT_AUDIT_PASS = YES")

        log("BATCH_03_SUCCESS = YES")
        log("DATABASE_BACKUP =", backup)
        log("NEXT_STAGE = Batch 04: khóa 5 nguồn tách điểm bằng dữ liệu phân điểm/lớp thực tế; đồng thời hoàn thiện summary còn lại theo từng nhóm, không tự sinh CSVC/tài chính khi baseline trống.")
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
            log("\n" + "="*160)
            log("BATCH_03_SUCCESS = NO")
            log("ERROR =", repr(exc))
            if DB.exists():
                log("DB_SHA_CURRENT =", sha256_file(DB))
            log("DỪNG AN TOÀN.")
            log("="*160)
        finally:
            if LOG and not LOG.closed:
                LOG.close()
        code = 1
    sys.exit(code)
