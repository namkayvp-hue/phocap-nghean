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
OUT = EXPORT_DIR / "COMMIT_THCS_OP0025.txt"

EXPECTED_DB_SHA = "c7e51137abf425fababfc3b1857aa24d3056c7abbe20089f6c33f68d48c7b9b8"

PLAN_ID = "PA2026-F68F2B60851F"
OFFICIAL_OPERATION_CODE = "QD3805-OP-0025"
PREVIEW_FINGERPRINT = "0d9e3d82ef179f78bb1266de2bf19abed0fa9a158d31a64751fc51872135e381"

TARGET_ID = 1431
TARGET_CODE = "40412512"
TARGET_NAME = "THCS Quang Trung"
TARGET_COMMUNE_ID = 1

SOURCE_ID = 1426
SOURCE_CODE = "40412505"
SOURCE_NAME = "THCS Đội Cung"
SOURCE_COMMUNE_ID = 1

BASE_YEAR_ID = 1
CURRENT_YEAR_ID = 2

EXPECTED_SOURCE = {"TOTAL":39,"CBQL":1,"GIAO_VIEN":35,"NHAN_VIEN":3}
EXPECTED_FINAL = {"TOTAL":39,"CBQL":1,"GIAO_VIEN":35,"NHAN_VIEN":3}

EXCLUDED_CODES = {"NGHI_HUU","CHUYEN_DI","THOI_VIEC","DA_NGHI"}
EXCLUDED_LABELS = {"Đã nghỉ hưu","Đã chuyển đi","Nghỉ hưu","Chuyển đi"}

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
    return '"' + str(name).replace('"','""') + '"'

def sha256_file(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024*1024), b""):
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

def load_registry():
    for enc in ("utf-8-sig","utf-8"):
        try:
            return json.loads(REGISTRY.read_text(encoding=enc))
        except Exception:
            pass
    fail("Không đọc được official registry")

def find_plan(reg):
    for p in (reg.get("plans") or []) if isinstance(reg,dict) else []:
        if isinstance(p,dict) and p.get("id") == PLAN_ID:
            return p
    fail(f"Không tìm thấy plan {PLAN_ID}")

def validate_plan(plan):
    if plan.get("school_year_code") != "2026-2027":
        fail("Plan sai school_year_code")
    if plan.get("commune_excel") != "Thành Vinh":
        fail("Plan sai commune_excel")
    if plan.get("plan_text") != "THCS Quang Trung":
        fail("Plan sai plan_text")
    if int(plan.get("target_member_index")) != 0:
        fail("Plan sai target_member_index")
    members = plan.get("members") or []
    names = [str(x.get("school_name","")) for x in members if isinstance(x,dict)]
    if names != ["THCS Quang Trung","THCS Đội Cung"]:
        fail(f"Plan members sai: {names}")

def school(conn, sid):
    cur = conn.execute("SELECT * FROM schools WHERE id=?", (sid,))
    row = cur.fetchone()
    if row is None:
        return None
    names = [d[0] for d in cur.description]
    return dict(zip(names,row))

def require_school(row, sid, commune_id, code, name_part, active=1):
    if not row:
        fail(f"Không tìm thấy school_id={sid}")
    if int(row["id"]) != sid or int(row["commune_id"]) != commune_id:
        fail(f"school_id={sid} sai id/commune")
    if str(row.get("code")) != code:
        fail(f"school_id={sid} sai code={row.get('code')}")
    if name_part.lower() not in str(row.get("name","")).lower():
        fail(f"school_id={sid} sai name={row.get('name')}")
    if int(row.get("is_active")) != active:
        fail(f"school_id={sid} sai active={row.get('is_active')}")

def staff_rows(conn, sid, year_id):
    cur = conn.execute(
        "SELECT * FROM staff_year_records WHERE school_id=? AND school_year_id=? ORDER BY staff_member_id,id",
        (sid,year_id)
    )
    names = [d[0] for d in cur.description]
    return [dict(zip(names,r)) for r in cur.fetchall()]

def summary(rows):
    c = Counter(str(r.get("position_group") or "NULL") for r in rows)
    return {
        "TOTAL":len(rows),
        "CBQL":c.get("CBQL",0),
        "GIAO_VIEN":c.get("GIAO_VIEN",0),
        "NHAN_VIEN":c.get("NHAN_VIEN",0),
    }

def require_summary(label, actual, expected):
    if actual != expected:
        fail(f"{label} sai: actual={actual}, expected={expected}")

def eligible(row):
    if int(row.get("is_active") or 0) != 1:
        return False
    if str(row.get("status_code") or "").strip().upper() in EXCLUDED_CODES:
        return False
    if str(row.get("source_status_label") or "").strip() in EXCLUDED_LABELS:
        return False
    return True

def current_footprint(conn, sid):
    hits=[]
    for table in table_names(conn):
        c=cols(conn,table)
        if "school_id" not in c or "school_year_id" not in c:
            continue
        try:
            n=conn.execute(
                f"SELECT COUNT(*) FROM {qi(table)} WHERE school_id=? AND school_year_id=?",
                (sid,CURRENT_YEAR_ID)
            ).fetchone()[0]
            if n:
                hits.append((table,n))
        except sqlite3.Error:
            pass
    return hits

def exact_related(conn):
    ids={TARGET_ID,SOURCE_ID}
    official=[]
    for r in conn.execute(
        "SELECT id,plan_id,operation_id,target_school_id,source_school_ids_json FROM school_merger_official_executions ORDER BY id"
    ).fetchall():
        try:
            src={int(x) for x in json.loads(r[4] or "[]")}
        except Exception:
            src=set()
        if r[1]==PLAN_ID or int(r[3]) in ids or bool(src & ids):
            official.append(r)

    operations=[]
    for r in conn.execute(
        "SELECT id,target_school_id,source_school_ids_json FROM school_merger_operations ORDER BY id"
    ).fetchall():
        try:
            src={int(x) for x in json.loads(r[2] or "[]")}
        except Exception:
            src=set()
        if int(r[1]) in ids or bool(src & ids):
            operations.append(r)
    return official,operations

def rows_hash(cur):
    names=[d[0] for d in cur.description]
    rows=[]
    for r in cur.fetchall():
        d={}
        for i,n in enumerate(names):
            v=r[i]
            if isinstance(v,(bytes,bytearray)):
                v={"__blob_sha256__":hashlib.sha256(bytes(v)).hexdigest()}
            d[n]=v
        rows.append(d)
    return hashlib.sha256(
        json.dumps(rows,ensure_ascii=False,sort_keys=True,default=str).encode("utf-8")
    ).hexdigest()

def unrelated_snapshot(conn):
    snap={}
    for table in table_names(conn):
        if table in ("school_merger_operations","school_merger_official_executions"):
            continue
        c=cols(conn,table)
        order="id" if "id" in c else "rowid"
        try:
            if table=="schools":
                cur=conn.execute(f"SELECT * FROM schools WHERE id<>? ORDER BY {qi(order)}",(SOURCE_ID,))
            elif table=="users":
                cur=conn.execute(
                    f"SELECT * FROM users WHERE NOT (school_id=? AND role_id=3) ORDER BY {qi(order)}",
                    (SOURCE_ID,)
                )
            elif table=="staff_year_records":
                cur=conn.execute(
                    f"SELECT * FROM staff_year_records WHERE NOT (school_id=? AND school_year_id=?) ORDER BY {qi(order)}",
                    (TARGET_ID,CURRENT_YEAR_ID)
                )
            else:
                cur=conn.execute(
                    f"SELECT * FROM {qi(table)} ORDER BY {qi(order) if order!='rowid' else 'rowid'}"
                )
            snap[table]=rows_hash(cur)
        except sqlite3.Error as e:
            snap[table]="ERROR:"+repr(e)
    return snap

def compare_snapshots(a,b):
    return [(k,a.get(k),b.get(k)) for k in sorted(set(a)|set(b)) if a.get(k)!=b.get(k)]

def baseline_table(conn, table):
    old_hash=rows_hash(conn.execute(f"SELECT * FROM {qi(table)} ORDER BY id"))
    max_id=conn.execute(f"SELECT COALESCE(MAX(id),0) FROM {qi(table)}").fetchone()[0]
    return old_hash,max_id

def old_rows_unchanged(conn, table, max_id, old_hash):
    return rows_hash(
        conn.execute(f"SELECT * FROM {qi(table)} WHERE id<=? ORDER BY id",(max_id,))
    ) == old_hash

def make_backup():
    BACKUP_DIR.mkdir(parents=True,exist_ok=True)
    ts=datetime.now().strftime("%Y%m%d_%H%M%S")
    path=BACKUP_DIR / f"backup_truoc_THCS_OP0025_{ts}.db"
    src=sqlite3.connect(str(DB),timeout=30)
    dst=sqlite3.connect(str(path),timeout=30)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    ro=sqlite3.connect(f"file:{path.as_posix()}?mode=ro",uri=True)
    try:
        integ=ro.execute("PRAGMA integrity_check").fetchone()[0]
        fk=ro.execute("PRAGMA foreign_key_check").fetchall()
    finally:
        ro.close()
    if integ!="ok" or fk:
        fail(f"Backup lỗi integrity={integ}, fk={len(fk)}")
    return path

def actor(conn):
    row=conn.execute(
        """
        SELECT actor_user_id,actor_username,actor_full_name
        FROM school_merger_official_executions
        WHERE actor_user_id IS NOT NULL
        ORDER BY id DESC LIMIT 1
        """
    ).fetchone()
    if not row:
        fail("Không tìm thấy actor từ execution trước")
    return row

def clone_staff(conn, rows):
    insert_cols=[r[1] for r in table_info(conn,"staff_year_records") if r[1]!="id"]
    sql=(
        f"INSERT INTO staff_year_records ({', '.join(qi(c) for c in insert_cols)}) "
        f"VALUES ({', '.join('?' for _ in insert_cols)})"
    )
    now=datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
    for row in rows:
        d=dict(row)
        d["school_id"]=TARGET_ID
        d["school_year_id"]=CURRENT_YEAR_ID
        if "created_at" in d: d["created_at"]=now
        if "updated_at" in d: d["updated_at"]=now
        conn.execute(sql,[d.get(c) for c in insert_cols])
    return len(rows)

def insert_logs(conn, who, backup_name, summary_json):
    uid,username,fullname=who
    now=datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
    src_json=json.dumps([SOURCE_ID],ensure_ascii=False)
    cur=conn.execute(
        """
        INSERT INTO school_merger_operations
        (school_year_id,target_school_id,source_school_ids_json,actor_user_id,backup_name,summary_json,created_at)
        VALUES (?,?,?,?,?,?,?)
        """,
        (CURRENT_YEAR_ID,TARGET_ID,src_json,uid,backup_name,summary_json,now)
    )
    op_id=int(cur.lastrowid)
    conn.execute(
        """
        INSERT INTO school_merger_official_executions
        (plan_id,operation_id,school_year_id,target_school_id,source_school_ids_json,
         actor_user_id,actor_username,actor_full_name,backup_name,preview_fingerprint,summary_json,created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (PLAN_ID,op_id,CURRENT_YEAR_ID,TARGET_ID,src_json,
         uid,username,fullname,backup_name,PREVIEW_FINGERPRINT,summary_json,now)
    )
    return op_id

def main():
    global LOG_FH
    EXPORT_DIR.mkdir(parents=True,exist_ok=True)
    LOG_FH=OUT.open("w",encoding="utf-8-sig",newline="\n")

    log("="*150)
    log("COMMIT QD3805-OP-0025")
    log("THCS Đội Cung -> THCS Quang Trung, Phường Thành Vinh")
    log("="*150)

    wal=DB.parent/"phocap.db-wal"
    journal=DB.parent/"phocap.db-journal"
    wal_size=wal.stat().st_size if wal.exists() else 0
    journal_size=journal.stat().st_size if journal.exists() else 0
    log("WAL_SIZE =",wal_size)
    log("JOURNAL_SIZE =",journal_size)
    if wal_size or journal_size:
        fail("WAL/JOURNAL khác 0")

    sha=sha256_file(DB)
    log("DB_SHA_BEFORE =",sha)
    if sha!=EXPECTED_DB_SHA:
        fail("DB SHA khác PREVIEW")

    ro=sqlite3.connect(f"file:{DB.as_posix()}?mode=ro",uri=True,timeout=30)
    try:
        integ=ro.execute("PRAGMA integrity_check").fetchone()[0]
        fk=ro.execute("PRAGMA foreign_key_check").fetchall()
        log("INTEGRITY_BEFORE =",integ)
        log("FK_BEFORE =",len(fk))
        if integ!="ok" or fk:
            fail("Database health không đạt")
    finally:
        ro.close()

    backup=make_backup()
    log("BACKUP =",backup)
    log("BACKUP_SHA =",sha256_file(backup))

    conn=sqlite3.connect(str(DB),timeout=30)
    conn.execute("PRAGMA foreign_keys=ON")
    committed=False
    op_id=None

    try:
        conn.execute("BEGIN IMMEDIATE")

        require_school(
            school(conn,TARGET_ID),TARGET_ID,TARGET_COMMUNE_ID,TARGET_CODE,TARGET_NAME,1
        )
        require_school(
            school(conn,SOURCE_ID),SOURCE_ID,SOURCE_COMMUNE_ID,SOURCE_CODE,SOURCE_NAME,1
        )

        validate_plan(find_plan(load_registry()))
        log("PLAN_VALIDATION = PASS")

        official,operations=exact_related(conn)
        log("RELATED_OFFICIAL =",official)
        log("RELATED_OPERATIONS =",operations)
        if official or operations:
            fail("Đã có execution liên quan")

        for sid in (TARGET_ID,SOURCE_ID):
            fp=current_footprint(conn,sid)
            log("CURRENT_FOOTPRINT",sid,"=",fp)
            if fp:
                fail(f"school_id={sid} đã có year=2 footprint")

        target_rows=staff_rows(conn,TARGET_ID,BASE_YEAR_ID)
        source_rows=staff_rows(conn,SOURCE_ID,BASE_YEAR_ID)

        require_summary("TARGET_BASE",summary(target_rows),
                        {"TOTAL":0,"CBQL":0,"GIAO_VIEN":0,"NHAN_VIEN":0})
        require_summary("SOURCE_BASE",summary(source_rows),EXPECTED_SOURCE)

        excluded=[r for r in source_rows if not eligible(r)]
        log("EXCLUDED_COUNT =",len(excluded))
        if excluded:
            fail("Có nhân sự excluded")

        mids=[int(r["staff_member_id"]) for r in source_rows]
        if len(mids)!=len(set(mids)):
            fail("Có staff_member_id trùng")

        if mids:
            q=",".join("?" for _ in mids)
            existing=conn.execute(
                f"SELECT staff_member_id,school_id FROM staff_year_records WHERE school_year_id=? AND staff_member_id IN ({q})",
                [CURRENT_YEAR_ID]+mids
            ).fetchall()
        else:
            existing=[]
        log("CURRENT_YEAR_EXISTING =",existing)
        if existing:
            fail("Có staff year=2 đã tồn tại")

        src_users=conn.execute(
            "SELECT id,username,is_active FROM users WHERE school_id=? AND role_id=3 ORDER BY id",
            (SOURCE_ID,)
        ).fetchall()
        tgt_users=conn.execute(
            "SELECT id,username,is_active FROM users WHERE school_id=? AND role_id=3 ORDER BY id",
            (TARGET_ID,)
        ).fetchall()
        log("SOURCE_USERS =",src_users)
        log("TARGET_USERS =",tgt_users)
        if len(src_users)!=1 or int(src_users[0][2])!=1:
            fail("Source school login sai")
        if len(tgt_users)!=1 or int(tgt_users[0][2])!=1:
            fail("Target school login sai")

        unrelated_before=unrelated_snapshot(conn)
        op_old_hash,op_old_max=baseline_table(conn,"school_merger_operations")
        off_old_hash,off_old_max=baseline_table(conn,"school_merger_official_executions")

        who=actor(conn)
        log("ACTOR =",who)

        created=clone_staff(conn,source_rows)
        log("STAFF_ROLLOVER_CREATED =",created)
        if created!=EXPECTED_FINAL["TOTAL"]:
            fail("Sai số lượng rollover")

        cur=conn.execute(
            "UPDATE users SET is_active=0 WHERE school_id=? AND role_id=3 AND is_active=1",
            (SOURCE_ID,)
        )
        if cur.rowcount!=1:
            fail("Không khóa đúng 1 source login")
        log("SOURCE_SCHOOL_LOGINS_DISABLED =",cur.rowcount)

        cur=conn.execute(
            "UPDATE schools SET is_active=0 WHERE id=? AND is_active=1",
            (SOURCE_ID,)
        )
        if cur.rowcount!=1:
            fail("Không deactivate đúng 1 source")
        log("SOURCE_DEACTIVATED =",cur.rowcount)

        summary_obj={
            "special_execution_type":"THCS_FULL_SOURCE_MERGE_TO_EMPTY_EXISTING_TARGET",
            "official_operation_code":OFFICIAL_OPERATION_CODE,
            "plan_id":PLAN_ID,
            "target_school_id":TARGET_ID,
            "source_school_ids":[SOURCE_ID],
            "staff_rollover_created":EXPECTED_FINAL["TOTAL"],
            "staff_rollover_by_position":{
                "CBQL":EXPECTED_FINAL["CBQL"],
                "GIAO_VIEN":EXPECTED_FINAL["GIAO_VIEN"],
                "NHAN_VIEN":EXPECTED_FINAL["NHAN_VIEN"],
            },
            "source_school_logins_disabled":1,
            "sources_deactivated":1,
            "users_moved":0,
            "preview_fingerprint":PREVIEW_FINGERPRINT,
        }
        summary_json=json.dumps(summary_obj,ensure_ascii=False,sort_keys=True)
        op_id=insert_logs(conn,who,backup.stem,summary_json)
        log("MERGER_OPERATION_ID =",op_id)

        require_summary("FINAL_STAFF",summary(staff_rows(conn,TARGET_ID,CURRENT_YEAR_ID)),EXPECTED_FINAL)

        if conn.execute(
            "SELECT COUNT(*) FROM staff_year_records WHERE school_id=? AND school_year_id=?",
            (SOURCE_ID,CURRENT_YEAR_ID)
        ).fetchone()[0] != 0:
            fail("Source còn staff year=2")

        if int(school(conn,SOURCE_ID)["is_active"]) != 0:
            fail("Source chưa inactive")
        if int(school(conn,TARGET_ID)["is_active"]) != 1:
            fail("Target không active")

        diffs=compare_snapshots(unrelated_before,unrelated_snapshot(conn))
        log("UNRELATED_DATA_DIFFS =",diffs)
        if diffs:
            fail("Dữ liệu ngoài write-set bị thay đổi")

        if not old_rows_unchanged(conn,"school_merger_operations",op_old_max,op_old_hash):
            fail("Merger operations cũ bị thay đổi")
        if not old_rows_unchanged(conn,"school_merger_official_executions",off_old_max,off_old_hash):
            fail("Official executions cũ bị thay đổi")

        fk2=conn.execute("PRAGMA foreign_key_check").fetchall()
        if fk2:
            fail("FK lỗi trong transaction")

        conn.commit()
        committed=True
        log("TRANSACTION_COMMIT = PASS")

    except Exception:
        if not committed:
            try:
                conn.rollback()
                log("ROLLBACK = PASS")
            except Exception as e:
                log("ROLLBACK_ERROR =",repr(e))
        raise
    finally:
        conn.close()

    ro=sqlite3.connect(f"file:{DB.as_posix()}?mode=ro",uri=True,timeout=30)
    try:
        integ=ro.execute("PRAGMA integrity_check").fetchone()[0]
        fk=ro.execute("PRAGMA foreign_key_check").fetchall()
        final=summary(staff_rows(ro,TARGET_ID,CURRENT_YEAR_ID))
        src_active=int(school(ro,SOURCE_ID)["is_active"])
        tgt_active=int(school(ro,TARGET_ID)["is_active"])
        official=ro.execute(
            """
            SELECT id,plan_id,operation_id,target_school_id,source_school_ids_json,
                   backup_name,preview_fingerprint,created_at
            FROM school_merger_official_executions
            WHERE plan_id=?
            """,
            (PLAN_ID,)
        ).fetchall()
    finally:
        ro.close()

    log("="*150)
    log("POST VERIFY")
    log("="*150)
    log("INTEGRITY_AFTER =",integ)
    log("FK_AFTER =",len(fk))
    log("FINAL_STAFF =",json.dumps(final,ensure_ascii=False))
    log("SOURCE_IS_ACTIVE =",src_active)
    log("TARGET_IS_ACTIVE =",tgt_active)
    log("OFFICIAL_EXECUTION =",json.dumps(official,ensure_ascii=False,default=str))

    if integ!="ok" or fk:
        fail("Post health lỗi")
    require_summary("POST_FINAL",final,EXPECTED_FINAL)
    if src_active!=0 or tgt_active!=1:
        fail("Post source/target status sai")
    if len(official)!=1:
        fail("Official execution không đúng 1 dòng")

    log("DB_SHA_AFTER =",sha256_file(DB))
    log("="*150)
    log("COMMIT_SUCCESS = YES")
    log("PLAN_ID =",PLAN_ID)
    log("OPERATION_ID =",op_id)
    log("SOURCE =",f"{SOURCE_ID} | {SOURCE_CODE} | {SOURCE_NAME}")
    log("TARGET =",f"{TARGET_ID} | {TARGET_CODE} | {TARGET_NAME}")
    log("FINAL_STAFF =",json.dumps(EXPECTED_FINAL,ensure_ascii=False))
    log("BACKUP =",backup)
    log("="*150)

if __name__=="__main__":
    try:
        main()
    except Exception as exc:
        try:
            log("="*150)
            log("COMMIT_SUCCESS = NO")
            log("ERROR =",repr(exc))
            if DB.exists():
                log("DB_SHA_CURRENT =",sha256_file(DB))
            log("DỪNG AN TOÀN.")
            log("="*150)
        finally:
            if LOG_FH:
                LOG_FH.close()
        sys.exit(1)
    else:
        if LOG_FH:
            LOG_FH.close()
