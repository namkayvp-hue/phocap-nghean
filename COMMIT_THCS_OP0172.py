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
REGISTRY = ROOT / "school_merger_official_registry_v2.json"
BACKUP_DIR = ROOT / "backups"
EXPORT_DIR = ROOT / "exports"
OUT = EXPORT_DIR / "COMMIT_THCS_OP0172.txt"

EXPECTED_DB_SHA = "9cd85770ad9f6743c6a96d54d2cd5d3e706466433acc287f3664d0e4e44b4d5d"

PLAN_ID = "PA2026-98173E42E1D0"
OFFICIAL_OPERATION_CODE = "QD3805-OP-0172"
EXECUTION_FINGERPRINT = "63d3c855a67698286046f3c712d14c80c826a26b0786dcfe93f3a8e102ee32d5"

TARGET_ID = 1463
TARGET_COMMUNE_ID = 104
TARGET_CODE = "40427513"
TARGET_NAME = "THCS Đại Sơn"

SOURCES = [
    (1464, 104, "40427521", "THCS Trù Sơn"),
    (1465, 104, "40427522", "THCS Lê Hồng Phong"),
]

EXCLUDED_MEMBER_IDS = {31442, 31566}

BASE_YEAR_ID = 1
CURRENT_YEAR_ID = 2

EXPECTED_TARGET_ALL = {"TOTAL": 40, "CBQL": 2, "GIAO_VIEN": 32, "NHAN_VIEN": 6}
EXPECTED_SOURCE_1464_ALL = {"TOTAL": 42, "CBQL": 2, "GIAO_VIEN": 36, "NHAN_VIEN": 4}
EXPECTED_SOURCE_1465_ALL = {"TOTAL": 0, "CBQL": 0, "GIAO_VIEN": 0, "NHAN_VIEN": 0}
EXPECTED_FINAL = {"TOTAL": 80, "CBQL": 4, "GIAO_VIEN": 67, "NHAN_VIEN": 9}

LOG_FH = None

def log(*args):
    s = " ".join(str(x) for x in args)
    print(s)
    if LOG_FH:
        LOG_FH.write(s + "\n")
        LOG_FH.flush()

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

def table_names(conn):
    return [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()]

def table_info(conn, table):
    return conn.execute(f"PRAGMA table_info({qi(table)})").fetchall()

def cols(conn, table):
    return [r[1] for r in table_info(conn, table)]

def load_registry():
    for enc in ("utf-8-sig", "utf-8"):
        try:
            return json.loads(REGISTRY.read_text(encoding=enc))
        except Exception:
            pass
    fail("Không đọc được official registry")

def find_plan(reg):
    for p in (reg.get("plans") or []) if isinstance(reg, dict) else []:
        if isinstance(p, dict) and p.get("id") == PLAN_ID:
            return p
    fail(f"Không tìm thấy plan {PLAN_ID}")

def validate_plan(plan):
    if plan.get("school_year_code") != "2026-2027":
        fail("Plan sai school_year_code")
    if plan.get("commune_excel") != "Bạch Hà":
        fail("Plan sai commune_excel")
    if plan.get("plan_text") != "THCS Đại Sơn":
        fail("Plan sai plan_text")
    if int(plan.get("target_member_index")) != 0:
        fail("Plan sai target_member_index")
    members = plan.get("members") or []
    names = [str(x.get("school_name", "")) for x in members if isinstance(x, dict)]
    expected = ["THCS Đại Sơn", "THCS Lê Hồng Phong (Mỹ Sơn)", "THCS Trù Sơn"]
    if names != expected:
        fail(f"Plan members sai: {names}")

def school(conn, sid):
    cur = conn.execute("SELECT * FROM schools WHERE id=?", (sid,))
    row = cur.fetchone()
    if row is None:
        return None
    names = [d[0] for d in cur.description]
    return dict(zip(names, row))

def require_school(row, sid, commune_id, code, name_part, active=1):
    if not row:
        fail(f"Không tìm thấy school_id={sid}")
    if int(row["id"]) != sid or int(row["commune_id"]) != commune_id:
        fail(f"school_id={sid} sai id/commune")
    if str(row.get("code")) != code:
        fail(f"school_id={sid} sai code={row.get('code')}")
    if name_part.lower() not in str(row.get("name", "")).lower():
        fail(f"school_id={sid} sai name={row.get('name')}")
    if int(row.get("is_active")) != active:
        fail(f"school_id={sid} sai active={row.get('is_active')}")

def staff_rows(conn, sid, year_id):
    cur = conn.execute(
        "SELECT * FROM staff_year_records WHERE school_id=? AND school_year_id=? ORDER BY staff_member_id,id",
        (sid, year_id),
    )
    names = [d[0] for d in cur.description]
    return [dict(zip(names, r)) for r in cur.fetchall()]

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
        fail(f"{label} sai: actual={actual}, expected={expected}")

def current_footprint(conn, sid):
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

def exact_related(conn):
    ids = {TARGET_ID} | {x[0] for x in SOURCES}
    official = []
    for r in conn.execute(
        "SELECT id,plan_id,operation_id,target_school_id,source_school_ids_json FROM school_merger_official_executions ORDER BY id"
    ).fetchall():
        try:
            src = {int(x) for x in json.loads(r[4] or "[]")}
        except Exception:
            src = set()
        if r[1] == PLAN_ID or int(r[3]) in ids or bool(src & ids):
            official.append(r)

    operations = []
    for r in conn.execute(
        "SELECT id,target_school_id,source_school_ids_json FROM school_merger_operations ORDER BY id"
    ).fetchall():
        try:
            src = {int(x) for x in json.loads(r[2] or "[]")}
        except Exception:
            src = set()
        if int(r[1]) in ids or bool(src & ids):
            operations.append(r)
    return official, operations

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

def unrelated_snapshot(conn):
    snap = {}
    source_ids = [x[0] for x in SOURCES]
    for table in table_names(conn):
        if table in ("school_merger_operations", "school_merger_official_executions"):
            continue
        c = cols(conn, table)
        order = "id" if "id" in c else "rowid"
        try:
            if table == "schools":
                q = ",".join("?" for _ in source_ids)
                cur = conn.execute(
                    f"SELECT * FROM schools WHERE id NOT IN ({q}) ORDER BY {qi(order)}",
                    source_ids,
                )
            elif table == "users":
                q = ",".join("?" for _ in source_ids)
                cur = conn.execute(
                    f"SELECT * FROM users WHERE NOT (role_id=3 AND school_id IN ({q})) ORDER BY {qi(order)}",
                    source_ids,
                )
            elif table == "staff_year_records":
                cur = conn.execute(
                    f"SELECT * FROM staff_year_records WHERE NOT (school_id=? AND school_year_id=?) ORDER BY {qi(order)}",
                    (TARGET_ID, CURRENT_YEAR_ID),
                )
            else:
                cur = conn.execute(
                    f"SELECT * FROM {qi(table)} ORDER BY {qi(order) if order != 'rowid' else 'rowid'}"
                )
            snap[table] = rows_hash(cur)
        except sqlite3.Error as e:
            snap[table] = "ERROR:" + repr(e)
    return snap

def compare_snapshots(a, b):
    return [(k, a.get(k), b.get(k)) for k in sorted(set(a) | set(b)) if a.get(k) != b.get(k)]

def baseline_table(conn, table):
    old_hash = rows_hash(conn.execute(f"SELECT * FROM {qi(table)} ORDER BY id"))
    max_id = conn.execute(f"SELECT COALESCE(MAX(id),0) FROM {qi(table)}").fetchone()[0]
    return old_hash, max_id

def old_rows_unchanged(conn, table, max_id, old_hash):
    return rows_hash(
        conn.execute(f"SELECT * FROM {qi(table)} WHERE id<=? ORDER BY id", (max_id,))
    ) == old_hash

def make_backup():
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = BACKUP_DIR / f"backup_truoc_THCS_OP0172_{ts}.db"
    src = sqlite3.connect(str(DB), timeout=30)
    dst = sqlite3.connect(str(path), timeout=30)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()

    ro = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    try:
        integ = ro.execute("PRAGMA integrity_check").fetchone()[0]
        fk = ro.execute("PRAGMA foreign_key_check").fetchall()
    finally:
        ro.close()
    if integ != "ok" or fk:
        fail(f"Backup lỗi integrity={integ}, fk={len(fk)}")
    return path

def choose_actor(conn):
    row = conn.execute(
        "SELECT actor_user_id,actor_username,actor_full_name "
        "FROM school_merger_official_executions "
        "WHERE actor_user_id IS NOT NULL ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if not row:
        fail("Không tìm thấy actor từ execution trước")
    return row

def clone_staff(conn, rows):
    insert_cols = [r[1] for r in table_info(conn, "staff_year_records") if r[1] != "id"]
    sql = (
        f"INSERT INTO staff_year_records ({', '.join(qi(c) for c in insert_cols)}) "
        f"VALUES ({', '.join('?' for _ in insert_cols)})"
    )
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
    for row in rows:
        d = dict(row)
        d["school_id"] = TARGET_ID
        d["school_year_id"] = CURRENT_YEAR_ID
        if "created_at" in d:
            d["created_at"] = now
        if "updated_at" in d:
            d["updated_at"] = now
        conn.execute(sql, [d.get(c) for c in insert_cols])
    return len(rows)

def insert_logs(conn, actor, backup_name, summary_json):
    uid, username, fullname = actor
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
    src_json = json.dumps([x[0] for x in SOURCES], ensure_ascii=False)

    cur = conn.execute(
        "INSERT INTO school_merger_operations "
        "(school_year_id,target_school_id,source_school_ids_json,actor_user_id,backup_name,summary_json,created_at) "
        "VALUES (?,?,?,?,?,?,?)",
        (CURRENT_YEAR_ID, TARGET_ID, src_json, uid, backup_name, summary_json, now),
    )
    op_id = int(cur.lastrowid)

    conn.execute(
        "INSERT INTO school_merger_official_executions "
        "(plan_id,operation_id,school_year_id,target_school_id,source_school_ids_json,"
        "actor_user_id,actor_username,actor_full_name,backup_name,preview_fingerprint,summary_json,created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            PLAN_ID, op_id, CURRENT_YEAR_ID, TARGET_ID, src_json,
            uid, username, fullname, backup_name,
            EXECUTION_FINGERPRINT, summary_json, now
        ),
    )
    return op_id

def main():
    global LOG_FH
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    LOG_FH = OUT.open("w", encoding="utf-8-sig", newline="\n")

    log("="*150)
    log("COMMIT QD3805-OP-0172")
    log("THCS Trù Sơn + THCS Lê Hồng Phong (Mỹ Sơn) -> THCS Đại Sơn")
    log("LOẠI rollover staff_member_id=31442 và 31566 vì CHUYEN_DI / Đã chuyển đi")
    log("="*150)

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
    if sha != EXPECTED_DB_SHA:
        fail("DB SHA khác nền đã rà")

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

    backup = make_backup()
    log("BACKUP =", backup)
    log("BACKUP_SHA =", sha256_file(backup))

    conn = sqlite3.connect(str(DB), timeout=30)
    conn.execute("PRAGMA foreign_keys=ON")
    committed = False
    op_id = None

    try:
        conn.execute("BEGIN IMMEDIATE")

        require_school(
            school(conn, TARGET_ID), TARGET_ID, TARGET_COMMUNE_ID, TARGET_CODE, TARGET_NAME, 1
        )
        for sid, cid, code, name in SOURCES:
            require_school(school(conn, sid), sid, cid, code, name, 1)

        validate_plan(find_plan(load_registry()))
        log("PLAN_VALIDATION = PASS")

        official, operations = exact_related(conn)
        log("RELATED_OFFICIAL =", official)
        log("RELATED_OPERATIONS =", operations)
        if official or operations:
            fail("Đã có execution liên quan")

        for sid in [TARGET_ID] + [x[0] for x in SOURCES]:
            fp = current_footprint(conn, sid)
            log("CURRENT_FOOTPRINT", sid, "=", fp)
            if fp:
                fail(f"school_id={sid} đã có footprint year=2")

        target_all = staff_rows(conn, TARGET_ID, BASE_YEAR_ID)
        src1464_all = staff_rows(conn, 1464, BASE_YEAR_ID)
        src1465_all = staff_rows(conn, 1465, BASE_YEAR_ID)

        require_summary("TARGET_ALL", summary(target_all), EXPECTED_TARGET_ALL)
        require_summary("SOURCE_1464_ALL", summary(src1464_all), EXPECTED_SOURCE_1464_ALL)
        require_summary("SOURCE_1465_ALL", summary(src1465_all), EXPECTED_SOURCE_1465_ALL)

        combined_all = target_all + src1464_all + src1465_all

        excluded_rows = [
            r for r in combined_all
            if int(r.get("staff_member_id")) in EXCLUDED_MEMBER_IDS
        ]
        if len(excluded_rows) != 2:
            fail(f"Không tìm thấy đúng 2 excluded member: {len(excluded_rows)}")

        excluded_ids = {int(r.get("staff_member_id")) for r in excluded_rows}
        if excluded_ids != EXCLUDED_MEMBER_IDS:
            fail(f"Excluded IDs sai: {excluded_ids}")

        for r in excluded_rows:
            if str(r.get("status_code") or "").strip().upper() != "CHUYEN_DI":
                fail(f"Member {r.get('staff_member_id')} không còn CHUYEN_DI")
            if str(r.get("source_status_label") or "").strip() != "Đã chuyển đi":
                fail(f"Member {r.get('staff_member_id')} không còn 'Đã chuyển đi'")

        eligible_rows = [
            r for r in combined_all
            if int(r.get("staff_member_id")) not in EXCLUDED_MEMBER_IDS
        ]
        require_summary("FINAL_ELIGIBLE", summary(eligible_rows), EXPECTED_FINAL)

        for mid in sorted(EXCLUDED_MEMBER_IDS):
            n = conn.execute(
                "SELECT COUNT(*) FROM staff_year_records WHERE staff_member_id=? AND school_year_id=?",
                (mid, CURRENT_YEAR_ID)
            ).fetchone()[0]
            log("EXCLUDED_MEMBER_YEAR2_BEFORE", mid, "=", n)
            if n != 0:
                fail(f"Excluded member {mid} đã có year=2")

        mids = [int(r["staff_member_id"]) for r in eligible_rows]
        if len(mids) != len(set(mids)):
            fail("Có staff_member_id trùng trong eligible rows")

        if mids:
            q = ",".join("?" for _ in mids)
            existing = conn.execute(
                f"SELECT staff_member_id,school_id FROM staff_year_records "
                f"WHERE school_year_id=? AND staff_member_id IN ({q})",
                [CURRENT_YEAR_ID] + mids,
            ).fetchall()
        else:
            existing = []
        log("CURRENT_YEAR_EXISTING =", existing)
        if existing:
            fail("Có staff year=2 đã tồn tại")

        for sid in [TARGET_ID] + [x[0] for x in SOURCES]:
            users = conn.execute(
                "SELECT id,username,is_active FROM users WHERE school_id=? AND role_id=3 ORDER BY id",
                (sid,)
            ).fetchall()
            log("SCHOOL_USERS", sid, "=", users)
            if len(users) != 1 or int(users[0][2]) != 1:
                fail(f"school_id={sid} school login không đúng")

        unrelated_before = unrelated_snapshot(conn)
        op_old_hash, op_old_max = baseline_table(conn, "school_merger_operations")
        off_old_hash, off_old_max = baseline_table(conn, "school_merger_official_executions")

        actor = choose_actor(conn)
        log("ACTOR =", actor)

        created = clone_staff(conn, eligible_rows)
        log("STAFF_ROLLOVER_CREATED =", created)
        if created != EXPECTED_FINAL["TOTAL"]:
            fail("Sai số lượng staff rollover")

        disabled = 0
        for sid, _, _, _ in SOURCES:
            cur = conn.execute(
                "UPDATE users SET is_active=0 WHERE school_id=? AND role_id=3 AND is_active=1",
                (sid,)
            )
            if cur.rowcount != 1:
                fail(f"Không khóa đúng 1 source login school_id={sid}")
            disabled += cur.rowcount
        log("SOURCE_SCHOOL_LOGINS_DISABLED =", disabled)

        deactivated = 0
        for sid, _, _, _ in SOURCES:
            cur = conn.execute(
                "UPDATE schools SET is_active=0 WHERE id=? AND is_active=1",
                (sid,)
            )
            if cur.rowcount != 1:
                fail(f"Không deactivate đúng 1 source school_id={sid}")
            deactivated += cur.rowcount
        log("SOURCES_DEACTIVATED =", deactivated)

        summary_obj = {
            "special_execution_type":"THCS_FULL_MERGE_WITH_EMPTY_SOURCE_AND_TRANSFERRED_STAFF_EXCLUDED",
            "official_operation_code":OFFICIAL_OPERATION_CODE,
            "plan_id":PLAN_ID,
            "target_school_id":TARGET_ID,
            "source_school_ids":[x[0] for x in SOURCES],
            "empty_source_school_id":1465,
            "excluded_staff_member_ids":sorted(EXCLUDED_MEMBER_IDS),
            "excluded_reason":"CHUYEN_DI / Đã chuyển đi",
            "staff_rollover_created":EXPECTED_FINAL["TOTAL"],
            "staff_rollover_by_position":{
                "CBQL":EXPECTED_FINAL["CBQL"],
                "GIAO_VIEN":EXPECTED_FINAL["GIAO_VIEN"],
                "NHAN_VIEN":EXPECTED_FINAL["NHAN_VIEN"],
            },
            "source_school_logins_disabled":2,
            "sources_deactivated":2,
            "users_moved":0,
            "execution_fingerprint":EXECUTION_FINGERPRINT,
        }
        summary_json = json.dumps(summary_obj, ensure_ascii=False, sort_keys=True)
        op_id = insert_logs(conn, actor, backup.stem, summary_json)
        log("MERGER_OPERATION_ID =", op_id)

        require_summary(
            "FINAL_STAFF",
            summary(staff_rows(conn, TARGET_ID, CURRENT_YEAR_ID)),
            EXPECTED_FINAL,
        )

        for mid in sorted(EXCLUDED_MEMBER_IDS):
            n = conn.execute(
                "SELECT COUNT(*) FROM staff_year_records WHERE staff_member_id=? AND school_year_id=?",
                (mid, CURRENT_YEAR_ID)
            ).fetchone()[0]
            if n != 0:
                fail(f"Excluded member {mid} bị rollover nhầm")

        for sid, _, _, _ in SOURCES:
            n = conn.execute(
                "SELECT COUNT(*) FROM staff_year_records WHERE school_id=? AND school_year_id=?",
                (sid, CURRENT_YEAR_ID)
            ).fetchone()[0]
            if n != 0:
                fail(f"Source {sid} còn staff year=2")

        if int(school(conn, TARGET_ID)["is_active"]) != 1:
            fail("Target không active")
        for sid, _, _, _ in SOURCES:
            if int(school(conn, sid)["is_active"]) != 0:
                fail(f"Source {sid} chưa inactive")

        diffs = compare_snapshots(unrelated_before, unrelated_snapshot(conn))
        log("UNRELATED_DATA_DIFFS =", diffs)
        if diffs:
            fail("Dữ liệu ngoài write-set bị thay đổi")

        if not old_rows_unchanged(conn, "school_merger_operations", op_old_max, op_old_hash):
            fail("Merger operations cũ bị thay đổi")
        if not old_rows_unchanged(conn, "school_merger_official_executions", off_old_max, off_old_hash):
            fail("Official executions cũ bị thay đổi")

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
            except Exception as e:
                log("ROLLBACK_ERROR =", repr(e))
        raise
    finally:
        conn.close()

    ro = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True, timeout=30)
    try:
        integ = ro.execute("PRAGMA integrity_check").fetchone()[0]
        fk = ro.execute("PRAGMA foreign_key_check").fetchall()
        final = summary(staff_rows(ro, TARGET_ID, CURRENT_YEAR_ID))
        target_active = int(school(ro, TARGET_ID)["is_active"])
        source_active = {sid:int(school(ro, sid)["is_active"]) for sid,_,_,_ in SOURCES}
        excluded_current = {
            mid:ro.execute(
                "SELECT COUNT(*) FROM staff_year_records WHERE staff_member_id=? AND school_year_id=?",
                (mid, CURRENT_YEAR_ID)
            ).fetchone()[0]
            for mid in sorted(EXCLUDED_MEMBER_IDS)
        }
        official = ro.execute(
            "SELECT id,plan_id,operation_id,target_school_id,source_school_ids_json,"
            "backup_name,preview_fingerprint,created_at "
            "FROM school_merger_official_executions WHERE plan_id=?",
            (PLAN_ID,)
        ).fetchall()
    finally:
        ro.close()

    log("="*150)
    log("POST VERIFY")
    log("="*150)
    log("INTEGRITY_AFTER =", integ)
    log("FK_AFTER =", len(fk))
    log("FINAL_STAFF =", json.dumps(final, ensure_ascii=False))
    log("TARGET_IS_ACTIVE =", target_active)
    log("SOURCE_ACTIVE =", source_active)
    log("EXCLUDED_MEMBER_YEAR2_COUNT =", excluded_current)
    log("OFFICIAL_EXECUTION =", json.dumps(official, ensure_ascii=False, default=str))

    if integ != "ok" or fk:
        fail("Post health lỗi")
    require_summary("POST_FINAL", final, EXPECTED_FINAL)
    if target_active != 1:
        fail("Post target status sai")
    if any(v != 0 for v in source_active.values()):
        fail("Post source status sai")
    if any(v != 0 for v in excluded_current.values()):
        fail("Post excluded member bị rollover")
    if len(official) != 1:
        fail("Official execution không đúng 1 dòng")

    log("DB_SHA_AFTER =", sha256_file(DB))
    log("="*150)
    log("COMMIT_SUCCESS = YES")
    log("PLAN_ID =", PLAN_ID)
    log("OPERATION_ID =", op_id)
    log("TARGET =", f"{TARGET_ID} | {TARGET_CODE} | {TARGET_NAME}")
    for sid, _, code, name in SOURCES:
        log("SOURCE =", f"{sid} | {code} | {name}")
    log("EXCLUDED_STAFF_MEMBER_IDS =", sorted(EXCLUDED_MEMBER_IDS))
    log("FINAL_STAFF =", json.dumps(EXPECTED_FINAL, ensure_ascii=False))
    log("BACKUP =", backup)
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
            log("DỪNG AN TOÀN.")
            log("="*150)
        finally:
            if LOG_FH:
                LOG_FH.close()
        sys.exit(1)
    else:
        if LOG_FH:
            LOG_FH.close()
