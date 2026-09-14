# -*- coding: utf-8 -*-
from __future__ import annotations

import csv
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
OUT = EXPORT_DIR / "BATCH_DU_LIEU_HAU_SAP_NHAP_TOAN_TINH_04.txt"

# Nền ngay sau Batch 03.
EXPECTED_DB_SHA = "8f91deb0f133200fe8e218c48c5a740001f21dfbe83152ff121300abdd493215"

BASE_YEAR_ID = 1
CURRENT_YEAR_ID = 2
FUTURE_YEAR_ID = 8

# Hai trường này KHÔNG phải nguồn bị giải thể.
# Đây là trường tiếp tục hoạt động/nhận thêm điểm trong các phương án đã khóa trước đó.
# Vì vậy dữ liệu đội ngũ của chính trường được phép rollover sang cùng school_id.
KEEP_CONTINUING_IDS = {1580, 1583}

# Ba nguồn còn lại thực sự cần phân bổ thủ công theo điểm/phần trường.
MANUAL_SPLIT_SOURCE_IDS = {1510, 1522, 1658}

EXCLUDED_STATUS_CODES = {"NGHI_HUU", "CHUYEN_DI", "THOI_VIEC", "DA_NGHI"}
EXCLUDED_STATUS_LABELS = {"Đã nghỉ hưu", "Đã chuyển đi", "Nghỉ hưu", "Chuyển đi"}

# Dùng cho resolver 3 nguồn còn lại.
SEARCH_TERMS = [
    "THCS Vạn Phong", "Diễn Vạn", "Diễn Phong", "THCS Diễn Kỷ", "THCS Diễn Hồng",
    "THCS Nguyễn Văn Trỗi", "Thịnh Sơn", "Hòa Sơn", "Văn Hiến", "Nguyễn Thái Nhự",
    "THCS Bá - Ngọc", "THCS Bá-Ngọc", "Quỳnh Bá", "Quỳnh Ngọc", "Quỳnh Hậu", "Quỳnh Hưng",
    "40425519", "40427516", "40421524",
]

SKIP_DIRS = {
    ".venv", "venv", ".git", "__pycache__", "backups", "exports",
    "static", "templates", "node_modules"
}

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

def table_names(conn):
    return [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()]

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
    path = BACKUP_DIR / f"backup_truoc_BATCH_DU_LIEU_04_{ts}.db"

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

def read_rows(conn, table, sid, year_id):
    cur = conn.execute(
        f"SELECT * FROM {qi(table)} WHERE school_id=? AND school_year_id=? ORDER BY id",
        (sid, year_id)
    )
    names = [d[0] for d in cur.description]
    return [dict(zip(names, r)) for r in cur.fetchall()]

def count_school_year(conn, table, sid, year_id):
    return int(conn.execute(
        f"SELECT COUNT(*) FROM {qi(table)} WHERE school_id=? AND school_year_id=?",
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

def tx_rollover_keep_continuing_staff(conn):
    log("\n" + "="*160)
    log("TRANSACTION A - SỬA KHÓA BẢO THỦ: ROLLOVER 2 TRƯỜNG KEEP TIẾP TỤC HOẠT ĐỘNG")
    log("="*160)

    plan = {}
    total_insert = 0

    for sid in sorted(KEEP_CONTINUING_IDS):
        s = school(conn, sid)
        if not s or int(s[4]) != 1:
            fail(f"KEEP school {sid} không active")

        y1 = read_rows(conn, "staff_year_records", sid, BASE_YEAR_ID)
        y2_here = read_rows(conn, "staff_year_records", sid, CURRENT_YEAR_ID)
        if not y1:
            fail(f"KEEP school {sid} không có staff y1")
        if y2_here:
            fail(f"KEEP school {sid} đã có staff y2, dừng tránh nhân đôi")

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

        plan[sid] = {
            "school": s,
            "y1_count": len(y1),
            "include": include,
            "excluded_status": excluded_status,
            "existing_elsewhere": existing_elsewhere,
        }
        total_insert += len(include)

        log("KEEP_SCHOOL =", s)
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
            created += clone_rows(conn, "staff_year_records", p["include"], mutate)

        if created != total_insert:
            fail(f"Created {created} != expected {total_insert}")

        if not old_rows_unchanged(conn, "staff_year_records", baseline):
            fail("Staff cũ bị thay đổi")

        for sid, p in plan.items():
            actual = count_school_year(conn, "staff_year_records", sid, CURRENT_YEAR_ID)
            if actual != len(p["include"]):
                fail(f"KEEP school {sid} y2={actual} != {len(p['include'])}")

        dups = duplicate_staff_y2(conn)
        if dups:
            fail(f"Duplicate staff y2 phát sinh: {dups[:20]}")

        fk = conn.execute("PRAGMA foreign_key_check").fetchall()
        if fk:
            fail(f"FK lỗi transaction KEEP: {fk[:20]}")

        conn.commit()
        log("KEEP_STAFF_TRANSACTION = COMMIT")
        log("KEEP_STAFF_INSERTED =", created)
        return created

    except Exception:
        conn.rollback()
        log("KEEP_STAFF_TRANSACTION = ROLLBACK")
        raise

def tx_rollover_keep_summaries(conn):
    log("\n" + "="*160)
    log("TRANSACTION B - SUMMARY CHO 2 TRƯỜNG KEEP NẾU CÓ BASELINE")
    log("="*160)

    table = "school_staff_year_summaries"
    if not table_exists(conn, table):
        log("KEEP_SUMMARY_TRANSACTION = SKIP_TABLE_NOT_FOUND")
        return 0

    safe = []
    for sid in sorted(KEEP_CONTINUING_IDS):
        y1 = count_school_year(conn, table, sid, BASE_YEAR_ID)
        y2 = count_school_year(conn, table, sid, CURRENT_YEAR_ID)
        log("KEEP_SUMMARY_FOOTPRINT", sid, "Y1=", y1, "Y2=", y2)
        if y1 == 1 and y2 == 0:
            safe.append(sid)
        elif y1 == 0 and y2 == 0:
            log("KEEP_SUMMARY_POLICY", sid, "= NO_BASELINE_NO_FAKE_ROW")
        elif y2 > 0:
            log("KEEP_SUMMARY_POLICY", sid, "= ALREADY_PRESENT")
        else:
            fail(f"Summary footprint bất thường school={sid} y1={y1} y2={y2}")

    if not safe:
        log("KEEP_SUMMARY_TRANSACTION = SKIP_NO_SAFE_ROWS")
        return 0

    baseline = old_rows_baseline(conn, table)

    conn.execute("BEGIN IMMEDIATE")
    try:
        created = 0
        for sid in safe:
            rows = read_rows(conn, table, sid, BASE_YEAR_ID)
            def mutate(d, sid=sid):
                d["school_id"] = sid
                d["school_year_id"] = CURRENT_YEAR_ID
                if "notes" in d:
                    d["notes"] = (
                        "Kế thừa dữ liệu nền 2025-2026 sang 2026-2027; "
                        "trường tiếp tục hoạt động và cập nhật số liệu năm hiện hành."
                    )
                if "updated_by_user_id" in d:
                    d["updated_by_user_id"] = None
            created += clone_rows(conn, table, rows, mutate)

        if created != len(safe):
            fail(f"Summary created {created} != {len(safe)}")
        if not old_rows_unchanged(conn, table, baseline):
            fail("Summary cũ bị thay đổi")

        fk = conn.execute("PRAGMA foreign_key_check").fetchall()
        if fk:
            fail(f"FK lỗi summary KEEP: {fk[:20]}")

        conn.commit()
        log("KEEP_SUMMARY_TRANSACTION = COMMIT")
        log("KEEP_SUMMARY_INSERTED =", created)
        return created

    except Exception:
        conn.rollback()
        log("KEEP_SUMMARY_TRANSACTION = ROLLBACK")
        raise

def db_relation_resolver(conn):
    log("\n" + "="*160)
    log("RESOLVER C - 3 NGUỒN TÁCH ĐIỂM CÒN LẠI: TÌM DỮ LIỆU PHÂN ĐIỂM/TRƯỜNG")
    log("CHỈ ĐỌC")
    log("="*160)

    source_ids = sorted(MANUAL_SPLIT_SOURCE_IDS)

    # 1) In toàn bộ schema staff để xem có cột điểm trường/site/location hay không.
    log("STAFF_YEAR_RECORDS_SCHEMA =", table_info(conn, "staff_year_records"))
    if table_exists(conn, "staff_members"):
        log("STAFF_MEMBERS_SCHEMA =", table_info(conn, "staff_members"))

    # 2) Tìm mọi bảng có khóa school/site/point/campus/class.
    candidate_tables = []
    for t in table_names(conn):
        low_cols = [c.lower() for c in cols(conn, t)]
        if (
            any(c in low_cols for c in ("school_id", "source_school_id", "target_school_id"))
            and any(
                any(k in c for k in ("site", "point", "campus", "location", "class", "diem"))
                for c in low_cols
            )
        ):
            candidate_tables.append((t, cols(conn, t)))

    log("POTENTIAL_POINT_RELATION_TABLES =", candidate_tables)

    for sid in source_ids:
        log("\n" + "-"*140)
        log("MANUAL_SOURCE =", school(conn, sid))
        rows = read_rows(conn, "staff_year_records", sid, BASE_YEAR_ID)
        log("STAFF_Y1_COUNT =", len(rows))

        # Chỉ xuất các cột không nhạy cảm.
        safe_cols = [
            c for c in cols(conn, "staff_year_records")
            if not any(x in c.lower() for x in ("password", "hash", "salt", "token"))
        ]
        preview = []
        for r in rows:
            preview.append({c: r.get(c) for c in safe_cols})
        log("STAFF_Y1_ROWS =", json.dumps(preview, ensure_ascii=False, default=str))

        for t, tcols in candidate_tables:
            # Chỉ các bảng thực sự có school_id trực tiếp mới truy vấn chắc chắn.
            if "school_id" not in tcols:
                continue
            try:
                matches = conn.execute(
                    f"SELECT * FROM {qi(t)} WHERE school_id=? LIMIT 200", (sid,)
                ).fetchall()
                if matches:
                    log("RELATED_TABLE", t, "COUNT_SHOWN=", len(matches))
                    log("RELATED_SCHEMA", t, "=", table_info(conn, t))
                    log("RELATED_ROWS", t, "=", matches[:200])
            except sqlite3.Error as e:
                log("RELATED_TABLE_ERROR", t, repr(e))

    # 3) Search tất cả cột TEXT của DB theo thuật ngữ tên điểm/trường.
    text_hits = []
    for t in table_names(conn):
        info = table_info(conn, t)
        text_cols = [
            r[1] for r in info
            if any(k in str(r[2] or "").upper() for k in ("CHAR", "TEXT", "CLOB"))
        ]
        for c in text_cols:
            for term in SEARCH_TERMS:
                try:
                    rows = conn.execute(
                        f"SELECT rowid,{qi(c)} FROM {qi(t)} "
                        f"WHERE {qi(c)} LIKE ? LIMIT 20",
                        (f"%{term}%",)
                    ).fetchall()
                except sqlite3.Error:
                    continue
                if rows:
                    text_hits.append((t, c, term, rows))
    log("DB_TEXT_HIT_GROUPS =", len(text_hits))
    for hit in text_hits[:300]:
        log("DB_TEXT_HIT =", hit)
    if len(text_hits) > 300:
        log("DB_TEXT_HIT_TRUNCATED =", len(text_hits)-300)

def iter_project_files():
    allowed = {".json", ".txt", ".csv", ".md", ".xlsx", ".xlsm"}
    for p in ROOT.rglob("*"):
        if not p.is_file():
            continue
        if any(part.lower() in SKIP_DIRS for part in p.parts):
            continue
        if p.suffix.lower() not in allowed:
            continue
        try:
            if p.stat().st_size > 30 * 1024 * 1024:
                continue
        except OSError:
            continue
        yield p

def text_file_hits(path):
    text = None
    for enc in ("utf-8-sig", "utf-8", "cp1258", "cp1252"):
        try:
            text = path.read_text(encoding=enc, errors="ignore")
            break
        except Exception:
            pass
    if text is None:
        return []
    low = text.lower()
    return [(term, low.count(term.lower())) for term in SEARCH_TERMS if term.lower() in low]

def excel_file_hits(path):
    try:
        import openpyxl
    except Exception:
        return [("__OPENPYXL_NOT_AVAILABLE__", 1)]

    hits = Counter()
    try:
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    except Exception:
        return []

    try:
        for ws in wb.worksheets:
            for row in ws.iter_rows(values_only=True):
                for v in row:
                    if v is None:
                        continue
                    s = str(v)
                    low = s.lower()
                    for term in SEARCH_TERMS:
                        if term.lower() in low:
                            hits[f"{ws.title}::{term}"] += 1
    finally:
        try:
            wb.close()
        except Exception:
            pass
    return list(hits.items())

def project_file_resolver():
    log("\n" + "="*160)
    log("RESOLVER D - TÌM SOURCE FILE/UPLOAD CÓ TÊN ĐIỂM/TRƯỜNG")
    log("CHỈ ĐỌC")
    log("="*160)

    found = []
    checked = 0
    for p in iter_project_files():
        checked += 1
        suffix = p.suffix.lower()
        if suffix in {".xlsx", ".xlsm"}:
            hits = excel_file_hits(p)
        else:
            hits = text_file_hits(p)
        if hits:
            found.append((str(p), hits))
            log("FILE_HIT =", p)
            log("HITS =", hits)

    log("PROJECT_FILES_CHECKED =", checked)
    log("PROJECT_FILES_WITH_HITS =", len(found))
    if not found:
        log("SOURCE_FILE_RESOLUTION = NO_POINT_LEVEL_SOURCE_FOUND")

def audit_remaining(conn):
    log("\n" + "="*160)
    log("AUDIT E - TRẠNG THÁI CÒN LẠI SAU BATCH 04")
    log("="*160)

    missing_staff = []
    for sid in [
        int(r[0]) for r in conn.execute(
            "SELECT id FROM schools WHERE is_active=1 ORDER BY id"
        ).fetchall()
    ]:
        y1 = count_school_year(conn, "staff_year_records", sid, BASE_YEAR_ID)
        y2 = count_school_year(conn, "staff_year_records", sid, CURRENT_YEAR_ID)
        if y1 > 0 and y2 == 0:
            missing_staff.append((sid, y1, school(conn, sid)))

    log("REMAINING_ACTIVE_SCHOOLS_Y1_STAFF_Y2_ZERO =", len(missing_staff))
    for x in missing_staff:
        log(" REMAINING_STAFF =", x)

    # Summary: phân loại đúng hơn - chỉ coi cần rollover nếu có y1 baseline.
    baseline_summary_missing = []
    no_baseline_summary = []
    if table_exists(conn, "school_staff_year_summaries"):
        for sid in [
            int(r[0]) for r in conn.execute(
                "SELECT id FROM schools WHERE is_active=1 ORDER BY id"
            ).fetchall()
        ]:
            staff2 = count_school_year(conn, "staff_year_records", sid, CURRENT_YEAR_ID)
            s1 = count_school_year(conn, "school_staff_year_summaries", sid, BASE_YEAR_ID)
            s2 = count_school_year(conn, "school_staff_year_summaries", sid, CURRENT_YEAR_ID)

            if staff2 > 0 and s2 == 0:
                if s1 > 0:
                    baseline_summary_missing.append((sid, s1, school(conn, sid)))
                else:
                    no_baseline_summary.append((sid, school(conn, sid)))

    log("SUMMARY_WITH_BASELINE_STILL_MISSING_Y2 =", len(baseline_summary_missing))
    for x in baseline_summary_missing[:100]:
        log(" SUMMARY_BASELINE_MISSING =", x)

    log("SUMMARY_NO_BASELINE_INFO_ONLY =", len(no_baseline_summary))
    log("SUMMARY_NO_BASELINE_POLICY = KHÔNG TỰ SINH; đây không phải lỗi rollover nếu năm 2025-2026 vốn không có dòng summary.")

    # CSVC/tài chính: baseline trống thì không tạo giả.
    for t in ("finance_year_entries", "school_facility_year_items"):
        if table_exists(conn, t):
            y1 = conn.execute(
                f"SELECT COUNT(*) FROM {qi(t)} WHERE school_year_id=?", (BASE_YEAR_ID,)
            ).fetchone()[0]
            y2 = conn.execute(
                f"SELECT COUNT(*) FROM {qi(t)} WHERE school_year_id=?", (CURRENT_YEAR_ID,)
            ).fetchone()[0]
            log("TABLE_POLICY", t, "Y1=", y1, "Y2=", y2, "=> NO_BASELINE_NO_FAKE_DATA")

    return missing_staff, baseline_summary_missing, no_baseline_summary

def main():
    global LOG
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    LOG = OUT.open("w", encoding="utf-8-sig", newline="\n")

    log("="*160)
    log("BATCH DỮ LIỆU HẬU SÁP NHẬP TOÀN TỈNH 04")
    log("SỬA KHÓA 2 TRƯỜNG KEEP + RESOLVE 3 NGUỒN TÁCH ĐIỂM CÒN LẠI")
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
        fail("DB SHA khác nền Batch 03")

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
        keep_staff_inserted = tx_rollover_keep_continuing_staff(conn)
        keep_summary_inserted = tx_rollover_keep_summaries(conn)

        # Từ đây chỉ đọc.
        db_relation_resolver(conn)
        project_file_resolver()
        missing_staff, baseline_summary_missing, no_baseline_summary = audit_remaining(conn)

        integ = conn.execute("PRAGMA integrity_check").fetchone()[0]
        fk = conn.execute("PRAGMA foreign_key_check").fetchall()
        dups = duplicate_staff_y2(conn)

        log("\n" + "="*160)
        log("POST VERIFY BATCH 04")
        log("="*160)
        log("INTEGRITY_AFTER =", integ)
        log("FK_AFTER =", len(fk))
        log("DUPLICATE_STAFF_Y2 =", len(dups))
        log("KEEP_STAFF_INSERTED =", keep_staff_inserted)
        log("KEEP_SUMMARY_INSERTED =", keep_summary_inserted)
        log("DB_SHA_AFTER =", sha256_file(DB))

        if integ != "ok" or fk or dups:
            fail("Post verify Batch 04 không đạt")

        remaining_ids = {int(x[0]) for x in missing_staff}
        log("REMAINING_STAFF_IDS =", sorted(remaining_ids))
        log("EXPECTED_ONLY_MANUAL_SPLIT_IDS =", sorted(MANUAL_SPLIT_SOURCE_IDS))

        if remaining_ids == MANUAL_SPLIT_SOURCE_IDS:
            log("REMAINING_STAFF_EXACTLY_3_MANUAL_SPLIT_SOURCES = YES")
        else:
            log("REMAINING_STAFF_EXACTLY_3_MANUAL_SPLIT_SOURCES = NO")

        log("BATCH_04_SUCCESS = YES")
        log("DATABASE_BACKUP =", backup)
        log("NEXT_STAGE = Dùng bằng chứng resolver trong chính file này để quyết định Batch 05 cho 3 nguồn Vạn Phong / Nguyễn Văn Trỗi / Bá-Ngọc. Nếu không có dữ liệu phân điểm đủ chắc, khóa chúng là MANUAL DATA ENTRY, không tự chia nhân sự bằng suy đoán.")
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
            log("BATCH_04_SUCCESS = NO")
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
