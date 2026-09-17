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
REGISTRY = ROOT / "school_merger_official_registry_v2.json"
LOG_PATH = EXPORT_DIR / "COMMIT_THCS_OP0210.txt"

EXPECTED_DB_SHA = "3837441007286585e4eb28e9e9246a9f33fe339efc09c4b1e8f4fb048db89e70"

PLAN_ID = "PA2026-0104708B7153"
OFFICIAL_OPERATION_CODE = "QD3805-OP-0210"
PREVIEW_FINGERPRINT = "0639c542be6c846f8fdd8364a771358b2d985b17af0cbbdcb283b7d60385555e"

SOURCE_ID = 1733
SOURCE_CODE = "40427505"
SOURCE_NAME = "THCS Thượng Sơn"

TARGET_ID = 1734
TARGET_CODE = "40427510"
TARGET_NAME = "THCS Trần Phú"

COMMUNE_ID = 102
BASE_YEAR_ID = 1
CURRENT_YEAR_ID = 2

EXPECTED_SOURCE = {"TOTAL": 34, "CBQL": 2, "GIAO_VIEN": 27, "NHAN_VIEN": 5}
EXPECTED_TARGET = {"TOTAL": 55, "CBQL": 2, "GIAO_VIEN": 47, "NHAN_VIEN": 6}
EXPECTED_FINAL = {"TOTAL": 89, "CBQL": 4, "GIAO_VIEN": 74, "NHAN_VIEN": 11}

ORPHAN_NAME_TERM = "THCS Văn Hiến"

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

def qi(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def table_names(conn):
    return [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()]

def table_info(conn, table):
    return conn.execute(f"PRAGMA table_info({qi(table)})").fetchall()

def cols(conn, table):
    return [r[1] for r in table_info(conn, table)]

def school(conn, sid):
    cur = conn.execute("SELECT * FROM schools WHERE id=?", (sid,))
    row = cur.fetchone()
    if row is None:
        return None
    names = [d[0] for d in cur.description]
    return dict(zip(names, row))

def require_school(row, sid, code, name_part, active=1):
    if not row:
        fail(f"Không tìm thấy school_id={sid}")
    if int(row.get("id")) != sid:
        fail(f"Sai id trường: {row}")
    if str(row.get("code")) != code:
        fail(f"school_id={sid} sai code: {row.get('code')}")
    if name_part.lower() not in str(row.get("name", "")).lower():
        fail(f"school_id={sid} sai tên: {row.get('name')}")
    if int(row.get("commune_id")) != COMMUNE_ID:
        fail(f"school_id={sid} sai commune_id={row.get('commune_id')}")
    if int(row.get("is_active")) != active:
        fail(f"school_id={sid} sai is_active={row.get('is_active')}")

def load_registry():
    if not REGISTRY.exists():
        fail(f"Không tìm thấy registry: {REGISTRY}")
    for enc in ("utf-8-sig", "utf-8"):
        try:
            return json.loads(REGISTRY.read_text(encoding=enc))
        except Exception:
            pass
    fail("Không đọc được official registry")

def find_plan(reg):
    plans = reg.get("plans") if isinstance(reg, dict) else None
    if not isinstance(plans, list):
        fail("Registry không có plans")
    for p in plans:
        if isinstance(p, dict) and p.get("id") == PLAN_ID:
            return p
    fail(f"Không tìm thấy PLAN_ID={PLAN_ID}")

def validate_plan(plan):
    if plan.get("school_year_code") != "2026-2027":
        fail("Plan sai school_year_code")
    if plan.get("commune_excel") != "Văn Hiến":
        fail("Plan sai commune_excel")
    if plan.get("plan_text") != "THCS Trần Phú":
        fail("Plan sai plan_text")
    members = plan.get("members") or []
    names = [str(x.get("school_name", "")) for x in members if isinstance(x, dict)]
    if not any("Trần Phú" in n for n in names):
        fail("Plan thiếu THCS Trần Phú")
    if not any("Thượng Sơn" in n for n in names):
        fail("Plan thiếu THCS Thượng Sơn")
    if not any("Văn Hiến" in n for n in names):
        fail("Plan không còn dòng orphan THCS Văn Hiến để khóa chính sách KHÔNG CHẠM")

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

def summary(rows):
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

def exact_related_execution(conn):
    sids = {SOURCE_ID, TARGET_ID}
    official = []
    for r in conn.execute(
        """
        SELECT id,plan_id,operation_id,school_year_id,target_school_id,source_school_ids_json
        FROM school_merger_official_executions ORDER BY id
        """
    ).fetchall():
        try:
            arr = {int(x) for x in json.loads(r[5] or "[]")}
        except Exception:
            arr = set()
        if r[1] == PLAN_ID or int(r[4]) in sids or bool(arr & sids):
            official.append(r)

    operations = []
    for r in conn.execute(
        """
        SELECT id,school_year_id,target_school_id,source_school_ids_json
        FROM school_merger_operations ORDER BY id
        """
    ).fetchall():
        try:
            arr = {int(x) for x in json.loads(r[3] or "[]")}
        except Exception:
            arr = set()
        if int(r[2]) in sids or bool(arr & sids):
            operations.append(r)
    return official, operations

def current_year_school_rows(conn, sid):
    hits = []
    for table in table_names(conn):
        c = cols(conn, table)
        if "school_id" not in c or "school_year_id" not in c:
            continue
        try:
            n = conn.execute(
                f"SELECT COUNT(*) FROM {qi(table)} WHERE school_id=? AND school_year_id=?",
                (sid, CURRENT_YEAR_ID),
            ).fetchone()[0]
            if n:
                hits.append((table, n))
        except sqlite3.Error:
            pass
    return hits

def resolve_orphan(conn):
    cur = conn.execute(
        "SELECT id,commune_id,code,name,is_active FROM schools WHERE name LIKE ? ORDER BY id",
        (f"%{ORPHAN_NAME_TERM}%",),
    )
    rows = cur.fetchall()
    if len(rows) != 1:
        fail(f"Không khóa được duy nhất orphan {ORPHAN_NAME_TERM}: {rows}")
    return rows[0]

def snapshot_school_refs(conn, sid):
    payload = {"schools": [], "tables": {}}
    cur = conn.execute("SELECT * FROM schools WHERE id=?", (sid,))
    names = [d[0] for d in cur.description]
    payload["schools"] = [dict(zip(names, r)) for r in cur.fetchall()]

    for table in table_names(conn):
        if table == "schools":
            continue
        c = cols(conn, table)
        if "school_id" not in c:
            continue
        try:
            order = "id" if "id" in c else "rowid"
            cur = conn.execute(
                f"SELECT * FROM {qi(table)} WHERE school_id=? ORDER BY {qi(order) if order != 'rowid' else 'rowid'}",
                (sid,),
            )
            rows = cur.fetchall()
            if not rows:
                continue
            names = [d[0] for d in cur.description]
            clean = []
            for r in rows:
                d = {}
                for i, n in enumerate(names):
                    v = r[i]
                    if isinstance(v, (bytes, bytearray)):
                        v = f"<BLOB:{hashlib.sha256(bytes(v)).hexdigest()}>"
                    d[n] = v
                clean.append(d)
            payload["tables"][table] = clean
        except sqlite3.Error:
            pass

    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest(), payload

def make_backup():
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"backup_truoc_THCS_OP0210_{ts}.db"

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
        fail(f"Backup lỗi: integrity={integ}, fk={len(fk)}")
    return backup_path

def choose_actor(conn):
    row = conn.execute(
        """
        SELECT actor_user_id,actor_username,actor_full_name
        FROM school_merger_official_executions
        WHERE actor_user_id IS NOT NULL
        ORDER BY id DESC LIMIT 1
        """
    ).fetchone()
    if not row:
        fail("Không tìm thấy actor từ official execution trước")
    return row

def clone_staff(conn, base_rows):
    info = table_info(conn, "staff_year_records")
    all_columns = [r[1] for r in info]
    insert_columns = [c for c in all_columns if c != "id"]
    sql = (
        f"INSERT INTO staff_year_records ({', '.join(qi(c) for c in insert_columns)}) "
        f"VALUES ({', '.join('?' for _ in insert_columns)})"
    )
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")

    created = 0
    for row in base_rows:
        data = dict(row)
        data["school_year_id"] = CURRENT_YEAR_ID
        data["school_id"] = TARGET_ID
        if "created_at" in data:
            data["created_at"] = now
        if "updated_at" in data:
            data["updated_at"] = now
        conn.execute(sql, [data.get(c) for c in insert_columns])
        created += 1
    return created

def insert_logs(conn, actor, backup_name, summary_json):
    actor_user_id, actor_username, actor_full_name = actor
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
    src_json = json.dumps([SOURCE_ID], ensure_ascii=False)

    cur = conn.execute(
        """
        INSERT INTO school_merger_operations
        (school_year_id,target_school_id,source_school_ids_json,actor_user_id,backup_name,summary_json,created_at)
        VALUES (?,?,?,?,?,?,?)
        """,
        (CURRENT_YEAR_ID,TARGET_ID,src_json,actor_user_id,backup_name,summary_json,now),
    )
    op_id = int(cur.lastrowid)

    conn.execute(
        """
        INSERT INTO school_merger_official_executions
        (plan_id,operation_id,school_year_id,target_school_id,source_school_ids_json,
         actor_user_id,actor_username,actor_full_name,backup_name,preview_fingerprint,summary_json,created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            PLAN_ID,op_id,CURRENT_YEAR_ID,TARGET_ID,src_json,
            actor_user_id,actor_username,actor_full_name,
            backup_name,PREVIEW_FINGERPRINT,summary_json,now
        ),
    )
    return op_id

def main():
    global LOG_FH
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    LOG_FH = LOG_PATH.open("w", encoding="utf-8", newline="\n")

    log("="*150)
    log("COMMIT QD3805-OP-0210")
    log("THCS Thượng Sơn (1733) -> THCS Trần Phú (1734)")
    log("POLICY: KHÔNG CHẠM THCS VĂN HIẾN")
    log("="*150)

    if not DB.exists():
        fail(f"Không tìm thấy DB: {DB}")

    wal = DB.parent / "phocap.db-wal"
    journal = DB.parent / "phocap.db-journal"
    wal_size = wal.stat().st_size if wal.exists() else 0
    journal_size = journal.stat().st_size if journal.exists() else 0
    log("WAL_SIZE =", wal_size)
    log("JOURNAL_SIZE =", journal_size)
    if wal_size != 0 or journal_size != 0:
        fail("WAL/JOURNAL khác 0. Dừng an toàn.")

    sha_before = sha256_file(DB)
    log("DB_SHA_BEFORE =", sha_before)
    if sha_before != EXPECTED_DB_SHA:
        fail("DB SHA đã khác PREVIEW. Không COMMIT.")

    ro = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True, timeout=30)
    try:
        integ = ro.execute("PRAGMA integrity_check").fetchone()[0]
        fk = ro.execute("PRAGMA foreign_key_check").fetchall()
        log("INTEGRITY_BEFORE =", integ)
        log("FK_BEFORE =", len(fk))
        if integ != "ok" or fk:
            fail("Database health không đạt")
    finally:
        ro.close()

    backup_path = make_backup()
    backup_name = backup_path.stem
    log("BACKUP =", backup_path)
    log("BACKUP_SHA =", sha256_file(backup_path))

    conn = sqlite3.connect(str(DB), timeout=30)
    conn.execute("PRAGMA foreign_keys=ON")
    committed = False
    operation_id = None

    try:
        conn.execute("BEGIN IMMEDIATE")

        # Re-check everything inside the write transaction.
        src = school(conn, SOURCE_ID)
        tgt = school(conn, TARGET_ID)
        require_school(src, SOURCE_ID, SOURCE_CODE, SOURCE_NAME, 1)
        require_school(tgt, TARGET_ID, TARGET_CODE, TARGET_NAME, 1)

        plan = find_plan(load_registry())
        validate_plan(plan)
        log("PLAN_VALIDATION = PASS")

        official, operations = exact_related_execution(conn)
        log("RELATED_OFFICIAL =", official)
        log("RELATED_OPERATIONS =", operations)
        if official or operations:
            fail("Đã có execution liên quan source/target/plan")

        src_current = current_year_school_rows(conn, SOURCE_ID)
        tgt_current = current_year_school_rows(conn, TARGET_ID)
        log("SOURCE_CURRENT_ROWS =", src_current)
        log("TARGET_CURRENT_ROWS =", tgt_current)
        if src_current or tgt_current:
            fail("Đã có dữ liệu school_year_id=2 ở source/target ngoài trạng thái preview")

        src_rows = staff_rows(conn, SOURCE_ID, BASE_YEAR_ID)
        tgt_rows = staff_rows(conn, TARGET_ID, BASE_YEAR_ID)
        require_summary("SOURCE STAFF", summary(src_rows), EXPECTED_SOURCE)
        require_summary("TARGET STAFF", summary(tgt_rows), EXPECTED_TARGET)

        if not all(eligible(r) for r in src_rows + tgt_rows):
            fail("Có nhân sự nền bị excluded")

        mids = [int(r["staff_member_id"]) for r in src_rows + tgt_rows]
        if len(mids) != len(set(mids)):
            fail("Có staff_member_id trùng source/target")

        orphan = resolve_orphan(conn)
        orphan_id = int(orphan[0])
        log("ORPHAN_LOCKED =", orphan)
        orphan_hash_before, _ = snapshot_school_refs(conn, orphan_id)
        log("ORPHAN_SNAPSHOT_BEFORE =", orphan_hash_before)

        src_school_users = conn.execute(
            "SELECT id,username,is_active FROM users WHERE school_id=? AND role_id=3 ORDER BY id",
            (SOURCE_ID,),
        ).fetchall()
        tgt_school_users = conn.execute(
            "SELECT id,username,is_active FROM users WHERE school_id=? AND role_id=3 ORDER BY id",
            (TARGET_ID,),
        ).fetchall()
        log("SOURCE_SCHOOL_USERS =", src_school_users)
        log("TARGET_SCHOOL_USERS =", tgt_school_users)
        if len(src_school_users) != 1 or int(src_school_users[0][2]) != 1:
            fail("Tài khoản cấp trường SOURCE không đúng kỳ vọng")
        if len(tgt_school_users) != 1 or int(tgt_school_users[0][2]) != 1:
            fail("Tài khoản cấp trường TARGET không đúng kỳ vọng")

        actor = choose_actor(conn)
        log("ACTOR =", actor)

        created = clone_staff(conn, src_rows + tgt_rows)
        if created != EXPECTED_FINAL["TOTAL"]:
            fail(f"Sai số staff rollover: {created}")
        log("STAFF_ROLLOVER_CREATED =", created)

        cur = conn.execute(
            "UPDATE users SET is_active=0 WHERE school_id=? AND role_id=3 AND is_active=1",
            (SOURCE_ID,),
        )
        if cur.rowcount != 1:
            fail(f"Không khóa đúng 1 tài khoản trường nguồn: {cur.rowcount}")
        log("SOURCE_SCHOOL_LOGINS_DISABLED =", cur.rowcount)

        cur = conn.execute(
            "UPDATE schools SET is_active=0 WHERE id=? AND is_active=1",
            (SOURCE_ID,),
        )
        if cur.rowcount != 1:
            fail(f"Không deactivate đúng 1 source: {cur.rowcount}")
        log("SOURCES_DEACTIVATED =", cur.rowcount)

        summary_obj = {
            "special_execution_type": "THCS_FULL_SOURCE_MERGE_WITH_ORPHAN_EXCLUSION",
            "official_operation_code": OFFICIAL_OPERATION_CODE,
            "plan_id": PLAN_ID,
            "source_school_id": SOURCE_ID,
            "source_school_code": SOURCE_CODE,
            "source_school_name": SOURCE_NAME,
            "target_school_id": TARGET_ID,
            "target_school_code": TARGET_CODE,
            "target_school_name": TARGET_NAME,
            "orphan_policy": "DO_NOT_TOUCH_THCS_VAN_HIEN",
            "orphan_school_id": orphan_id,
            "staff_rollover_created": EXPECTED_FINAL["TOTAL"],
            "staff_rollover_by_position": {
                "CBQL": EXPECTED_FINAL["CBQL"],
                "GIAO_VIEN": EXPECTED_FINAL["GIAO_VIEN"],
                "NHAN_VIEN": EXPECTED_FINAL["NHAN_VIEN"],
            },
            "source_school_logins_disabled": 1,
            "sources_deactivated": 1,
            "users_moved": 0,
            "direct_moves": [],
            "no_year_moves": [],
            "preview_fingerprint": PREVIEW_FINGERPRINT,
        }
        summary_json = json.dumps(summary_obj, ensure_ascii=False, sort_keys=True)

        operation_id = insert_logs(conn, actor, backup_name, summary_json)
        log("MERGER_OPERATION_ID =", operation_id)

        final_rows = staff_rows(conn, TARGET_ID, CURRENT_YEAR_ID)
        require_summary("FINAL STAFF", summary(final_rows), EXPECTED_FINAL)

        if conn.execute(
            "SELECT COUNT(*) FROM staff_year_records WHERE school_id=? AND school_year_id=?",
            (SOURCE_ID, CURRENT_YEAR_ID),
        ).fetchone()[0] != 0:
            fail("SOURCE còn staff year 2")

        if int(school(conn, SOURCE_ID)["is_active"]) != 0:
            fail("SOURCE chưa inactive")
        if int(school(conn, TARGET_ID)["is_active"]) != 1:
            fail("TARGET không active")

        if conn.execute(
            "SELECT COUNT(*) FROM users WHERE school_id=? AND role_id=3 AND is_active=1",
            (SOURCE_ID,),
        ).fetchone()[0] != 0:
            fail("SOURCE school login còn active")

        orphan_hash_after, _ = snapshot_school_refs(conn, orphan_id)
        log("ORPHAN_SNAPSHOT_AFTER =", orphan_hash_after)
        if orphan_hash_after != orphan_hash_before:
            fail("ORPHAN THCS Văn Hiến bị thay đổi - ROLLBACK")

        fk2 = conn.execute("PRAGMA foreign_key_check").fetchall()
        if fk2:
            fail(f"FK lỗi trong transaction: {fk2[:10]}")

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

    # Post-verify read-only.
    ro = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True, timeout=30)
    try:
        integ = ro.execute("PRAGMA integrity_check").fetchone()[0]
        fk = ro.execute("PRAGMA foreign_key_check").fetchall()
        final = summary(staff_rows(ro, TARGET_ID, CURRENT_YEAR_ID))
        src_active = int(school(ro, SOURCE_ID)["is_active"])
        tgt_active = int(school(ro, TARGET_ID)["is_active"])
        official = ro.execute(
            """
            SELECT id,plan_id,operation_id,target_school_id,source_school_ids_json,
                   backup_name,preview_fingerprint,created_at
            FROM school_merger_official_executions
            WHERE plan_id=?
            """,
            (PLAN_ID,),
        ).fetchall()
        orphan = resolve_orphan(ro)
        orphan_hash_post, _ = snapshot_school_refs(ro, int(orphan[0]))
    finally:
        ro.close()

    log("="*150)
    log("POST VERIFY")
    log("="*150)
    log("INTEGRITY_AFTER =", integ)
    log("FK_AFTER =", len(fk))
    log("FINAL_STAFF =", json.dumps(final, ensure_ascii=False))
    log("SOURCE_IS_ACTIVE =", src_active)
    log("TARGET_IS_ACTIVE =", tgt_active)
    log("OFFICIAL_EXECUTION =", json.dumps(official, ensure_ascii=False, default=str))
    log("ORPHAN_SNAPSHOT_POST =", orphan_hash_post)

    if integ != "ok" or fk:
        fail("POST VERIFY health lỗi")
    require_summary("POST FINAL STAFF", final, EXPECTED_FINAL)
    if src_active != 0 or tgt_active != 1:
        fail("POST VERIFY source/target status sai")
    if len(official) != 1:
        fail("POST VERIFY official execution không đúng 1 dòng")
    if orphan_hash_post != orphan_hash_before:
        fail("POST VERIFY orphan THCS Văn Hiến bị thay đổi")

    log("DB_SHA_AFTER =", sha256_file(DB))
    log("="*150)
    log("COMMIT_SUCCESS = YES")
    log("PLAN_ID =", PLAN_ID)
    log("OPERATION_ID =", operation_id)
    log("SOURCE =", f"{SOURCE_ID} | {SOURCE_CODE} | {SOURCE_NAME}")
    log("TARGET =", f"{TARGET_ID} | {TARGET_CODE} | {TARGET_NAME}")
    log("ORPHAN_THCS_VAN_HIEN = KHONG_THAY_DOI")
    log("FINAL_STAFF =", json.dumps(EXPECTED_FINAL, ensure_ascii=False))
    log("BACKUP =", backup_path)
    log("="*150)

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        try:
            log("="*150)
            log("COMMIT_SUCCESS = NO")
            log("ERROR =", repr(exc))
            if DB.exists():
                log("DB_SHA_CURRENT =", sha256_file(DB))
            log("DUNG AN TOAN. KHONG TIEP TUC OP-0644.")
            log("="*150)
        finally:
            if LOG_FH:
                LOG_FH.close()
        sys.exit(1)
    else:
        if LOG_FH:
            LOG_FH.close()
