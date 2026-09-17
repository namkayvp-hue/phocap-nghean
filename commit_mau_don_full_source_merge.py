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
LOG_PATH = EXPORT_DIR / "COMMIT_MAU_DON_FULL_SOURCE_MERGE.txt"

EXPECTED_DB_SHA = "706279fe9cd63f9f01c4c3d7637f955534280b7b745e333b0b6943c2e64aed89"

PLAN_ID = "PA2026-C1BD6766C723"
OFFICIAL_OPERATION_CODE = "QD3805-OP-0108"
PREVIEW_FINGERPRINT = "ae1a65a714af14bbdfad58c3fc442109dbc1815702393ee77baf580a817276d7"

SOURCE_ID = 1578
SOURCE_CODE = "40422510"
SOURCE_NAME = "Trường THCS Mậu Đôn"

TARGET_ID = 1577
TARGET_CODE = "40422504"
TARGET_NAME = "PTDT Bán trú THCS Thạch Ngàn"

COMMUNE_ID = 64
BASE_YEAR_ID = 1
CURRENT_YEAR_ID = 2
MOVE_YEAR_IDS = [2, 8]
PAST_YEAR_IDS = [1, 3, 4, 5, 6, 7]

EXPECTED_SOURCE_STAFF = {
    "TOTAL": 35,
    "CBQL": 3,
    "GIAO_VIEN": 30,
    "NHAN_VIEN": 2,
}
EXPECTED_TARGET_STAFF = {
    "TOTAL": 26,
    "CBQL": 3,
    "GIAO_VIEN": 20,
    "NHAN_VIEN": 3,
}
EXPECTED_FINAL = {
    "TOTAL": 61,
    "CBQL": 6,
    "GIAO_VIEN": 50,
    "NHAN_VIEN": 5,
}

EXCLUDED_STATUS_CODES = {"NGHI_HUU", "CHUYEN_DI", "THOI_VIEC", "DA_NGHI"}
EXCLUDED_SOURCE_LABELS = {"Đã nghỉ hưu", "Đã chuyển đi", "Nghỉ hưu", "Chuyển đi"}

LOG_FH = None

def log(*args):
    text = " ".join(str(x) for x in args)
    print(text)
    if LOG_FH:
        LOG_FH.write(text + "\n")
        LOG_FH.flush()

def fail(msg):
    raise RuntimeError(msg)

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            b = f.read(1024 * 1024)
            if not b:
                break
            h.update(b)
    return h.hexdigest()

def qi(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'

def table_info(conn, table):
    return conn.execute(f"PRAGMA table_info({qi(table)})").fetchall()

def table_names(conn):
    return [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()]

def cols(conn, table):
    return [r[1] for r in table_info(conn, table)]

def school(conn, sid):
    cur = conn.execute("SELECT * FROM schools WHERE id=?", (sid,))
    row = cur.fetchone()
    if row is None:
        return None
    names = [d[0] for d in cur.description]
    return dict(zip(names, row))

def require_school(row, sid, code, name_part, active):
    if not row:
        fail(f"Không tìm thấy school_id={sid}")
    if str(row.get("code")) != code:
        fail(f"school_id={sid} sai code: {row.get('code')}")
    if name_part.lower() not in str(row.get("name", "")).lower():
        fail(f"school_id={sid} sai tên: {row.get('name')}")
    if int(row.get("commune_id")) != COMMUNE_ID:
        fail(f"school_id={sid} sai commune_id")
    if int(row.get("is_active")) != active:
        fail(f"school_id={sid} sai is_active: {row.get('is_active')}")

def staff_rows(conn, sid, year_id):
    cur = conn.execute(
        "SELECT * FROM staff_year_records WHERE school_id=? AND school_year_id=? ORDER BY staff_member_id,id",
        (sid, year_id),
    )
    names = [d[0] for d in cur.description]
    return [dict(zip(names, r)) for r in cur.fetchall()]

def eligible(row):
    if int(row.get("is_active") or 0) != 1:
        return False
    status = str(row.get("status_code") or "").strip().upper()
    label = str(row.get("source_status_label") or "").strip()
    if status in EXCLUDED_STATUS_CODES:
        return False
    if label in EXCLUDED_SOURCE_LABELS:
        return False
    return True

def summarize(rows):
    c = Counter(str(r.get("position_group") or "NULL") for r in rows)
    return {
        "TOTAL": len(rows),
        "CBQL": c.get("CBQL", 0),
        "GIAO_VIEN": c.get("GIAO_VIEN", 0),
        "NHAN_VIEN": c.get("NHAN_VIEN", 0),
    }

def require_summary(label, actual, expected):
    if actual != expected:
        fail(f"{label} không khớp. actual={actual} expected={expected}")

def json_list_contains_source(text, sid):
    try:
        arr = json.loads(text or "[]")
        return int(sid) in [int(x) for x in arr]
    except Exception:
        return str(sid) in str(text or "")

def related_official_rows(conn):
    rows = conn.execute(
        """
        SELECT id, plan_id, operation_id, target_school_id, source_school_ids_json
        FROM school_merger_official_executions
        ORDER BY id
        """
    ).fetchall()
    out = []
    for r in rows:
        rid, plan, opid, target, src_json = r
        if (
            plan == PLAN_ID
            or int(target) in (SOURCE_ID, TARGET_ID)
            or json_list_contains_source(src_json, SOURCE_ID)
            or json_list_contains_source(src_json, TARGET_ID)
        ):
            out.append(r)
    return out

def related_operation_rows(conn):
    rows = conn.execute(
        """
        SELECT id, target_school_id, source_school_ids_json
        FROM school_merger_operations
        ORDER BY id
        """
    ).fetchall()
    out = []
    for r in rows:
        rid, target, src_json = r
        if (
            int(target) in (SOURCE_ID, TARGET_ID)
            or json_list_contains_source(src_json, SOURCE_ID)
            or json_list_contains_source(src_json, TARGET_ID)
        ):
            out.append(r)
    return out

def current_year_school_rows(conn, sid):
    hits = []
    for table in table_names(conn):
        c = cols(conn, table)
        if "school_id" not in c or "school_year_id" not in c:
            continue
        try:
            n = conn.execute(
                f"SELECT COUNT(*) FROM {qi(table)} WHERE school_id=? AND school_year_id IN (?,?)",
                (sid, MOVE_YEAR_IDS[0], MOVE_YEAR_IDS[1]),
            ).fetchone()[0]
            if n:
                hits.append((table, n))
        except sqlite3.Error:
            pass
    return hits

def make_backup():
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"backup_truoc_THCS_Mau_Don_full_source_{ts}.db"

    src = sqlite3.connect(str(DB), timeout=30)
    dst = sqlite3.connect(str(backup_path), timeout=30)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()

    check = sqlite3.connect(f"file:{backup_path.as_posix()}?mode=ro", uri=True)
    try:
        integ = check.execute("PRAGMA integrity_check").fetchone()[0]
        fk = check.execute("PRAGMA foreign_key_check").fetchall()
    finally:
        check.close()

    if integ != "ok" or fk:
        fail(f"Backup không đạt: integrity={integ} fk={len(fk)}")

    return backup_path

def choose_actor(conn):
    row = conn.execute(
        """
        SELECT actor_user_id, actor_username, actor_full_name
        FROM school_merger_official_executions
        WHERE actor_user_id IS NOT NULL
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()
    if not row:
        fail("Không tìm thấy actor hợp lệ từ official execution trước để ghi nhật ký nhất quán.")
    return row

def clone_staff_to_current(conn, base_rows):
    info = table_info(conn, "staff_year_records")
    all_columns = [r[1] for r in info]
    insert_columns = [c for c in all_columns if c != "id"]

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")

    sql = (
        f"INSERT INTO staff_year_records "
        f"({', '.join(qi(c) for c in insert_columns)}) "
        f"VALUES ({', '.join('?' for _ in insert_columns)})"
    )

    created = 0
    for row in base_rows:
        data = dict(row)
        data["school_year_id"] = CURRENT_YEAR_ID
        data["school_id"] = TARGET_ID
        if "created_at" in data:
            data["created_at"] = now
        if "updated_at" in data:
            data["updated_at"] = now

        values = [data.get(c) for c in insert_columns]
        conn.execute(sql, values)
        created += 1

    return created

def verify_before(conn):
    src = school(conn, SOURCE_ID)
    tgt = school(conn, TARGET_ID)
    require_school(src, SOURCE_ID, SOURCE_CODE, "Mậu Đôn", 1)
    require_school(tgt, TARGET_ID, TARGET_CODE, "Thạch Ngàn", 1)

    off = related_official_rows(conn)
    ops = related_operation_rows(conn)
    if off:
        fail(f"Đã có official execution liên quan: {off}")
    if ops:
        fail(f"Đã có merger operation liên quan: {ops}")

    src_rows = staff_rows(conn, SOURCE_ID, BASE_YEAR_ID)
    tgt_rows = staff_rows(conn, TARGET_ID, BASE_YEAR_ID)

    if not all(eligible(r) for r in src_rows):
        fail("Nguồn có nhân sự nền không hợp lệ theo rule preview.")
    if not all(eligible(r) for r in tgt_rows):
        fail("Đích có nhân sự nền không hợp lệ theo rule preview.")

    require_summary("SOURCE STAFF", summarize(src_rows), EXPECTED_SOURCE_STAFF)
    require_summary("TARGET STAFF", summarize(tgt_rows), EXPECTED_TARGET_STAFF)

    combined = src_rows + tgt_rows
    member_ids = [int(r["staff_member_id"]) for r in combined]
    if len(member_ids) != len(set(member_ids)):
        fail("Có staff_member_id trùng giữa source và target.")

    placeholders = ",".join("?" for _ in member_ids)
    existing = conn.execute(
        f"""
        SELECT staff_member_id, school_id
        FROM staff_year_records
        WHERE school_year_id=? AND staff_member_id IN ({placeholders})
        """,
        [CURRENT_YEAR_ID] + member_ids,
    ).fetchall()
    if existing:
        fail(f"Đã có nhân sự năm hiện hành ở nơi khác: {existing[:20]}")

    src_current = current_year_school_rows(conn, SOURCE_ID)
    tgt_current = current_year_school_rows(conn, TARGET_ID)
    if src_current:
        fail(f"Nguồn đã có dữ liệu năm hiện hành: {src_current}")
    if tgt_current:
        fail(f"Đích đã có dữ liệu năm hiện hành: {tgt_current}")

    src_school_users = conn.execute(
        "SELECT id, username, is_active FROM users WHERE school_id=? AND role_id=3 ORDER BY id",
        (SOURCE_ID,),
    ).fetchall()
    tgt_school_users = conn.execute(
        "SELECT id, username, is_active FROM users WHERE school_id=? AND role_id=3 ORDER BY id",
        (TARGET_ID,),
    ).fetchall()

    if len(src_school_users) != 1 or int(src_school_users[0][2]) != 1:
        fail(f"Tài khoản trường nguồn không đúng kỳ vọng: {src_school_users}")
    if len(tgt_school_users) != 1 or int(tgt_school_users[0][2]) != 1:
        fail(f"Tài khoản trường đích không đúng kỳ vọng: {tgt_school_users}")

    return combined

def insert_operation_and_official(conn, actor, backup_name, summary_json):
    actor_user_id, actor_username, actor_full_name = actor
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
    source_json = json.dumps([SOURCE_ID], ensure_ascii=False)

    cur = conn.execute(
        """
        INSERT INTO school_merger_operations
        (
            school_year_id,
            target_school_id,
            source_school_ids_json,
            actor_user_id,
            backup_name,
            summary_json,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            CURRENT_YEAR_ID,
            TARGET_ID,
            source_json,
            actor_user_id,
            backup_name,
            summary_json,
            now,
        ),
    )
    operation_id = int(cur.lastrowid)

    conn.execute(
        """
        INSERT INTO school_merger_official_executions
        (
            plan_id,
            operation_id,
            school_year_id,
            target_school_id,
            source_school_ids_json,
            actor_user_id,
            actor_username,
            actor_full_name,
            backup_name,
            preview_fingerprint,
            summary_json,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            PLAN_ID,
            operation_id,
            CURRENT_YEAR_ID,
            TARGET_ID,
            source_json,
            actor_user_id,
            actor_username,
            actor_full_name,
            backup_name,
            PREVIEW_FINGERPRINT,
            summary_json,
            now,
        ),
    )

    return operation_id

def verify_inside_transaction(conn, operation_id):
    final_rows = staff_rows(conn, TARGET_ID, CURRENT_YEAR_ID)
    require_summary("FINAL CURRENT STAFF", summarize(final_rows), EXPECTED_FINAL)

    if conn.execute(
        "SELECT COUNT(*) FROM staff_year_records WHERE school_id=? AND school_year_id=?",
        (SOURCE_ID, CURRENT_YEAR_ID),
    ).fetchone()[0] != 0:
        fail("Nguồn còn staff năm hiện hành.")

    src = school(conn, SOURCE_ID)
    tgt = school(conn, TARGET_ID)
    require_school(src, SOURCE_ID, SOURCE_CODE, "Mậu Đôn", 0)
    require_school(tgt, TARGET_ID, TARGET_CODE, "Thạch Ngàn", 1)

    active_src_login = conn.execute(
        "SELECT COUNT(*) FROM users WHERE school_id=? AND role_id=3 AND is_active=1",
        (SOURCE_ID,),
    ).fetchone()[0]
    if active_src_login != 0:
        fail("Tài khoản trường nguồn vẫn active.")

    if conn.execute(
        "SELECT COUNT(*) FROM school_merger_official_executions WHERE plan_id=? AND operation_id=?",
        (PLAN_ID, operation_id),
    ).fetchone()[0] != 1:
        fail("Official execution không được ghi đúng 1 dòng.")

    fk = conn.execute("PRAGMA foreign_key_check").fetchall()
    if fk:
        fail(f"foreign_key_check lỗi trong transaction: {fk[:10]}")

def post_verify():
    conn = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True, timeout=30)
    try:
        integ = conn.execute("PRAGMA integrity_check").fetchone()[0]
        fk = conn.execute("PRAGMA foreign_key_check").fetchall()
        final_rows = staff_rows(conn, TARGET_ID, CURRENT_YEAR_ID)
        final_summary = summarize(final_rows)
        source_active = school(conn, SOURCE_ID)["is_active"]
        target_active = school(conn, TARGET_ID)["is_active"]
        official = conn.execute(
            """
            SELECT id, plan_id, operation_id, target_school_id, source_school_ids_json,
                   backup_name, preview_fingerprint, created_at
            FROM school_merger_official_executions
            WHERE plan_id=?
            """,
            (PLAN_ID,),
        ).fetchall()
        return integ, fk, final_summary, source_active, target_active, official
    finally:
        conn.close()

def main():
    global LOG_FH
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    LOG_FH = LOG_PATH.open("w", encoding="utf-8", newline="\n")

    log("=" * 150)
    log("COMMIT THCS MAU DON -> PTDT BAN TRU THCS THACH NGAN")
    log("MODEL = THCS_MAU_DON_FULL_SOURCE_MERGE")
    log("PLAN_ID =", PLAN_ID)
    log("OPERATION_CODE =", OFFICIAL_OPERATION_CODE)
    log("=" * 150)

    if not DB.exists():
        fail(f"Không tìm thấy DB: {DB}")

    wal = DB.parent / "phocap.db-wal"
    journal = DB.parent / "phocap.db-journal"
    wal_size = wal.stat().st_size if wal.exists() else 0
    journal_size = journal.stat().st_size if journal.exists() else 0
    log("WAL_SIZE =", wal_size)
    log("JOURNAL_SIZE =", journal_size)
    if wal_size != 0 or journal_size != 0:
        fail("Có WAL/JOURNAL khác 0. Dừng để tránh ghi khi DB đang bận.")

    sha_before = sha256_file(DB)
    log("DB_SHA_BEFORE =", sha_before)
    if sha_before != EXPECTED_DB_SHA:
        fail("DB SHA đã thay đổi so với PREVIEW. KHÔNG COMMIT.")

    # Health + backup
    ro = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True, timeout=30)
    try:
        integ = ro.execute("PRAGMA integrity_check").fetchone()[0]
        fk = ro.execute("PRAGMA foreign_key_check").fetchall()
        log("INTEGRITY_BEFORE =", integ)
        log("FK_BEFORE =", len(fk))
        if integ != "ok" or fk:
            fail("Database health không đạt trước COMMIT.")
    finally:
        ro.close()

    backup_path = make_backup()
    backup_sha = sha256_file(backup_path)
    backup_name = backup_path.stem
    log("BACKUP =", backup_path)
    log("BACKUP_SHA =", backup_sha)

    conn = sqlite3.connect(str(DB), timeout=30)
    conn.execute("PRAGMA foreign_keys=ON")

    committed = False
    operation_id = None

    try:
        conn.execute("BEGIN IMMEDIATE")

        base_rows = verify_before(conn)
        log("PRECHECK = PASS")
        log("BASE_SOURCE_ROWS =", EXPECTED_SOURCE_STAFF["TOTAL"])
        log("BASE_TARGET_ROWS =", EXPECTED_TARGET_STAFF["TOTAL"])

        actor = choose_actor(conn)
        log("ACTOR_USER_ID =", actor[0])
        log("ACTOR_USERNAME =", actor[1])
        log("ACTOR_FULL_NAME =", actor[2])

        created = clone_staff_to_current(conn, base_rows)
        if created != EXPECTED_FINAL["TOTAL"]:
            fail(f"Số staff rollover tạo ra sai: {created}")
        log("STAFF_ROLLOVER_CREATED =", created)

        # Disable only the school-level login of the source.
        cur = conn.execute(
            "UPDATE users SET is_active=0 WHERE school_id=? AND role_id=3 AND is_active=1",
            (SOURCE_ID,),
        )
        if cur.rowcount != 1:
            fail(f"Số tài khoản trường nguồn bị khóa sai: {cur.rowcount}")
        log("SOURCE_SCHOOL_LOGINS_DISABLED =", cur.rowcount)

        cur = conn.execute(
            "UPDATE schools SET is_active=0 WHERE id=? AND is_active=1",
            (SOURCE_ID,),
        )
        if cur.rowcount != 1:
            fail(f"Không deactivate đúng 1 source school: {cur.rowcount}")
        log("SOURCES_DEACTIVATED =", cur.rowcount)

        summary = {
            "special_execution_type": "THCS_FULL_SOURCE_MERGE",
            "official_operation_code": OFFICIAL_OPERATION_CODE,
            "source_school_id": SOURCE_ID,
            "source_school_code": SOURCE_CODE,
            "source_school_name": SOURCE_NAME,
            "target_school_id": TARGET_ID,
            "target_school_code": TARGET_CODE,
            "target_school_name": TARGET_NAME,
            "move_year_ids": MOVE_YEAR_IDS,
            "past_year_ids": PAST_YEAR_IDS,
            "direct_moves": [],
            "no_year_moves": [],
            "audit_logs_kept": [],
            "users_moved": 0,
            "source_school_logins_disabled": 1,
            "staff_rollover_created": EXPECTED_FINAL["TOTAL"],
            "staff_rollover_by_position": {
                "CBQL": EXPECTED_FINAL["CBQL"],
                "GIAO_VIEN": EXPECTED_FINAL["GIAO_VIEN"],
                "NHAN_VIEN": EXPECTED_FINAL["NHAN_VIEN"],
            },
            "staff_existing_elsewhere_skipped": 0,
            "sources_deactivated": 1,
            "preview_fingerprint": PREVIEW_FINGERPRINT,
        }
        summary_json = json.dumps(summary, ensure_ascii=False, sort_keys=True)

        operation_id = insert_operation_and_official(
            conn, actor, backup_name, summary_json
        )
        log("MERGER_OPERATION_ID =", operation_id)

        verify_inside_transaction(conn, operation_id)
        log("VERIFY_INSIDE_TRANSACTION = PASS")

        conn.commit()
        committed = True
        log("TRANSACTION_COMMIT = PASS")

    except Exception:
        if not committed:
            try:
                conn.rollback()
                log("ROLLBACK = PASS")
            except Exception as rb:
                log("ROLLBACK_ERROR =", repr(rb))
        raise
    finally:
        conn.close()

    integ, fk, final_summary, source_active, target_active, official = post_verify()

    log("=" * 150)
    log("POST VERIFY")
    log("=" * 150)
    log("INTEGRITY_AFTER =", integ)
    log("FK_AFTER =", len(fk))
    log("FINAL_STAFF_SUMMARY =", json.dumps(final_summary, ensure_ascii=False))
    log("SOURCE_IS_ACTIVE =", source_active)
    log("TARGET_IS_ACTIVE =", target_active)
    log("OFFICIAL_EXECUTION =", json.dumps(official, ensure_ascii=False, default=str))

    if integ != "ok" or fk:
        fail("POST VERIFY database health lỗi.")
    require_summary("POST FINAL STAFF", final_summary, EXPECTED_FINAL)
    if int(source_active) != 0 or int(target_active) != 1:
        fail("POST VERIFY trạng thái source/target sai.")
    if len(official) != 1:
        fail("POST VERIFY official execution không đúng 1 dòng.")

    sha_after = sha256_file(DB)
    log("DB_SHA_AFTER =", sha_after)

    log("=" * 150)
    log("COMMIT_SUCCESS = YES")
    log("PLAN_ID =", PLAN_ID)
    log("OPERATION_ID =", operation_id)
    log("SOURCE =", f"{SOURCE_ID} | {SOURCE_CODE} | {SOURCE_NAME}")
    log("TARGET =", f"{TARGET_ID} | {TARGET_CODE} | {TARGET_NAME}")
    log("FINAL_STAFF =", json.dumps(EXPECTED_FINAL, ensure_ascii=False))
    log("BACKUP =", str(backup_path))
    log("DATABASE_INTEGRITY = ok")
    log("FOREIGN_KEY_ERRORS = 0")
    log("=" * 150)

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        try:
            log("=" * 150)
            log("COMMIT_SUCCESS = NO")
            log("ERROR =", repr(exc))
            if DB.exists():
                log("DB_SHA_CURRENT =", sha256_file(DB))
            log("KHONG TIEP TUC. KIEM TRA FILE LOG VA BACKUP.")
            log("=" * 150)
        finally:
            if LOG_FH:
                LOG_FH.close()
        sys.exit(1)
    else:
        if LOG_FH:
            LOG_FH.close()
