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
RESOLUTION = ROOT / "data" / "school_merger_registry" / "qd3805_thcs_resolution.json"
LEVEL_LOCK = ROOT / "data" / "school_merger_registry" / "qd3805_level_lock.json"

BACKUP_DIR = ROOT / "backups"
EXPORT_DIR = ROOT / "exports"
OUT = EXPORT_DIR / "BATCH_THCS_OP0203_VA_7_PHUONG_AN_CON_LAI.txt"

EXPECTED_DB_SHA = "1723e12a3d06d8f52b7b899174d5040bc4937ab84564e0f4d51b009586d8ce22"
PREVIEW_FINGERPRINT = "affb01c0fb695888b04fa1f70eaf039fd5806970cd8537a8ca91e0a10e1f8ed3"

PLAN_ID = "PA2026-16141F34ACBC"
OFFICIAL_OPERATION_CODE = "QD3805-OP-0203"

SURVIVOR_ID = 1712
SURVIVOR_COMMUNE_ID = 103
SURVIVOR_CODE = "40427524"
OLD_NAME = "THCS Kim Đồng"
NEW_NAME = "THCS Lê Hồng Phong"

PROTECTED_IDS = [1465, 1551]
EXCLUDED_MEMBER_ID = 42021

BASE_YEAR_ID = 1
CURRENT_YEAR_ID = 2

EXPECTED_BASE = {"TOTAL":58,"CBQL":1,"GIAO_VIEN":50,"NHAN_VIEN":7}
EXPECTED_FINAL = {"TOTAL":57,"CBQL":1,"GIAO_VIEN":49,"NHAN_VIEN":7}

REMAINING = {
    "QD3805-OP-0132": "SPLIT_SOURCE_REVIEW_NO_WHOLE_SCHOOL_ENGINE",
    "QD3805-OP-0133": "SPLIT_SOURCE_REVIEW_NO_WHOLE_SCHOOL_ENGINE",
    "QD3805-OP-0153": "SPLIT_SOURCE_REVIEW_NO_WHOLE_SCHOOL_ENGINE",
    "QD3805-OP-0191": "SPLIT_SOURCE_REVIEW_NO_WHOLE_SCHOOL_ENGINE",
    "QD3805-OP-0489": "SPLIT_SOURCE_REVIEW_NO_WHOLE_SCHOOL_ENGINE",
    "QD3805-OP-0486": "KEEP_NO_DB_WRITE",
    "QD3805-OP-0490": "KEEP_NO_DB_WRITE",
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
    return '"' + str(name).replace('"','""') + '"'

def sha256_file(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1024*1024), b""):
            h.update(b)
    return h.hexdigest()

def load_json(path):
    if not path.exists():
        return None
    for enc in ("utf-8-sig","utf-8"):
        try:
            return json.loads(path.read_text(encoding=enc))
        except Exception:
            pass
    return None

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
        for i,n in enumerate(names):
            v = r[i]
            if isinstance(v,(bytes,bytearray)):
                v = {"__blob_sha256__": hashlib.sha256(bytes(v)).hexdigest()}
            d[n] = v
        rows.append(d)
    return hashlib.sha256(
        json.dumps(rows,ensure_ascii=False,sort_keys=True,default=str).encode("utf-8")
    ).hexdigest()

def school(conn, sid):
    cur = conn.execute("SELECT * FROM schools WHERE id=?", (sid,))
    r = cur.fetchone()
    if r is None:
        return None
    names = [d[0] for d in cur.description]
    return dict(zip(names,r))

def staff_rows(conn, sid, year_id):
    cur = conn.execute(
        "SELECT * FROM staff_year_records WHERE school_id=? AND school_year_id=? ORDER BY staff_member_id,id",
        (sid,year_id)
    )
    names=[d[0] for d in cur.description]
    return [dict(zip(names,r)) for r in cur.fetchall()]

def summary(rows):
    c=Counter(str(r.get("position_group") or "NULL") for r in rows)
    return {
        "TOTAL":len(rows),
        "CBQL":c.get("CBQL",0),
        "GIAO_VIEN":c.get("GIAO_VIEN",0),
        "NHAN_VIEN":c.get("NHAN_VIEN",0),
    }

def require_summary(label, actual, expected):
    if actual != expected:
        fail(f"{label} sai: {actual} != {expected}")

def find_plan():
    data=load_json(REGISTRY)
    if isinstance(data,dict):
        for p in data.get("plans") or []:
            if isinstance(p,dict) and p.get("id")==PLAN_ID:
                return p
    fail("Không tìm thấy plan OP0203")

def validate_plan(plan):
    if plan.get("school_year_code")!="2026-2027": fail("Sai school_year_code")
    if plan.get("commune_excel")!="Thuần Trung": fail("Sai commune_excel")
    if plan.get("plan_text")!=NEW_NAME: fail("Sai plan_text")
    if plan.get("action_type")!="SPECIAL": fail("Plan không còn SPECIAL")
    if plan.get("target_member_index") is not None: fail("target_member_index không còn null")
    names=[str(x.get("school_name","")) for x in plan.get("members") or [] if isinstance(x,dict)]
    if names != ["THCS Kim Đồng (Minh Sơn)","THCS Lê Hồng Phong (Nhân Sơn)"]:
        fail(f"Plan members sai: {names}")

def exact_related(conn):
    official=[]
    for r in conn.execute(
        "SELECT id,plan_id,operation_id,target_school_id,source_school_ids_json FROM school_merger_official_executions ORDER BY id"
    ).fetchall():
        try: src={int(x) for x in json.loads(r[4] or "[]")}
        except Exception: src=set()
        if r[1]==PLAN_ID or int(r[3])==SURVIVOR_ID or SURVIVOR_ID in src:
            official.append(r)

    operations=[]
    for r in conn.execute(
        "SELECT id,target_school_id,source_school_ids_json FROM school_merger_operations ORDER BY id"
    ).fetchall():
        try: src={int(x) for x in json.loads(r[2] or "[]")}
        except Exception: src=set()
        if int(r[1])==SURVIVOR_ID or SURVIVOR_ID in src:
            operations.append(r)
    return official,operations

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

def unrelated_snapshot(conn):
    snap={}
    for table in table_names(conn):
        if table in ("school_merger_operations","school_merger_official_executions"):
            continue
        c=cols(conn,table)
        order="id" if "id" in c else "rowid"
        try:
            if table=="schools":
                cur=conn.execute(f"SELECT * FROM schools WHERE id<>? ORDER BY {qi(order)}",(SURVIVOR_ID,))
            elif table=="staff_year_records":
                cur=conn.execute(
                    f"SELECT * FROM staff_year_records WHERE NOT (school_id=? AND school_year_id=?) ORDER BY {qi(order)}",
                    (SURVIVOR_ID,CURRENT_YEAR_ID)
                )
            elif table=="school_name_histories":
                cur=conn.execute(
                    f"SELECT * FROM school_name_histories WHERE school_id<>? ORDER BY {qi(order)}",
                    (SURVIVOR_ID,)
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

def old_rows_unchanged(conn,table,max_id,old_hash):
    return rows_hash(
        conn.execute(f"SELECT * FROM {qi(table)} WHERE id<=? ORDER BY id",(max_id,))
    ) == old_hash

def make_backup():
    BACKUP_DIR.mkdir(parents=True,exist_ok=True)
    ts=datetime.now().strftime("%Y%m%d_%H%M%S")
    path=BACKUP_DIR/f"backup_truoc_THCS_OP0203_{ts}.db"
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

def choose_actor(conn):
    r=conn.execute(
        "SELECT actor_user_id,actor_username,actor_full_name "
        "FROM school_merger_official_executions WHERE actor_user_id IS NOT NULL "
        "ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if not r: fail("Không tìm thấy actor")
    return r

def clone_staff(conn, rows):
    insert_cols=[r[1] for r in table_info(conn,"staff_year_records") if r[1]!="id"]
    sql=(
        f"INSERT INTO staff_year_records ({', '.join(qi(c) for c in insert_cols)}) "
        f"VALUES ({', '.join('?' for _ in insert_cols)})"
    )
    now=datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
    for row in rows:
        d=dict(row)
        d["school_id"]=SURVIVOR_ID
        d["school_year_id"]=CURRENT_YEAR_ID
        if "created_at" in d: d["created_at"]=now
        if "updated_at" in d: d["updated_at"]=now
        conn.execute(sql,[d.get(c) for c in insert_cols])
    return len(rows)

def insert_logs(conn,actor,backup_name,summary_json):
    uid,username,fullname=actor
    now=datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
    src_json="[]"

    cur=conn.execute(
        "INSERT INTO school_merger_operations "
        "(school_year_id,target_school_id,source_school_ids_json,actor_user_id,backup_name,summary_json,created_at) "
        "VALUES (?,?,?,?,?,?,?)",
        (CURRENT_YEAR_ID,SURVIVOR_ID,src_json,uid,backup_name,summary_json,now)
    )
    op_id=int(cur.lastrowid)

    conn.execute(
        "INSERT INTO school_merger_official_executions "
        "(plan_id,operation_id,school_year_id,target_school_id,source_school_ids_json,"
        "actor_user_id,actor_username,actor_full_name,backup_name,preview_fingerprint,summary_json,created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (PLAN_ID,op_id,CURRENT_YEAR_ID,SURVIVOR_ID,src_json,
         uid,username,fullname,backup_name,PREVIEW_FINGERPRINT,summary_json,now)
    )
    return op_id

def recursive_matches(obj, needle, path="$"):
    out=[]
    if isinstance(obj,dict):
        blob=json.dumps(obj,ensure_ascii=False,default=str)
        if needle in blob:
            out.append((path,obj))
        for k,v in obj.items():
            if isinstance(v,(dict,list)):
                out.extend(recursive_matches(v,needle,f"{path}.{k}"))
    elif isinstance(obj,list):
        for i,v in enumerate(obj):
            if isinstance(v,(dict,list)):
                out.extend(recursive_matches(v,needle,f"{path}[{i}]"))
    return out

def extract_candidate_ids(obj):
    found=set()
    def walk(x,key=""):
        if isinstance(x,dict):
            for k,v in x.items():
                kl=str(k).lower()
                if isinstance(v,int) and ("school" in kl or kl.endswith("_id")):
                    if 1 <= v <= 100000:
                        found.add(v)
                elif isinstance(v,list) and ("source" in kl or "school" in kl):
                    for z in v:
                        if isinstance(z,int) and 1 <= z <= 100000:
                            found.add(z)
                if isinstance(v,(dict,list)):
                    walk(v,k)
        elif isinstance(x,list):
            for v in x:
                if isinstance(v,(dict,list)):
                    walk(v,key)
    walk(obj)
    return sorted(found)

def school_brief(conn,sid):
    r=conn.execute(
        "SELECT id,commune_id,code,name,is_active FROM schools WHERE id=?",(sid,)
    ).fetchone()
    if not r:
        return None
    staff=conn.execute(
        "SELECT school_year_id,position_group,COUNT(*) FROM staff_year_records "
        "WHERE school_id=? GROUP BY school_year_id,position_group ORDER BY school_year_id,position_group",
        (sid,)
    ).fetchall()
    users=conn.execute(
        "SELECT id,username,is_active FROM users WHERE school_id=? AND role_id=3 ORDER BY id",
        (sid,)
    ).fetchall()
    return {"school":r,"staff":staff,"role3":users}

def official_related_to_ids(conn, ids):
    out=[]
    ids=set(ids)
    for r in conn.execute(
        "SELECT id,plan_id,operation_id,target_school_id,source_school_ids_json,created_at "
        "FROM school_merger_official_executions ORDER BY id"
    ).fetchall():
        try: src={int(x) for x in json.loads(r[4] or "[]")}
        except Exception: src=set()
        if int(r[3]) in ids or bool(src & ids):
            out.append(r)
    return out

def audit_remaining(conn):
    log("\n"+"="*150)
    log("BƯỚC 2 - RÀ SOÁT GỘP 7 PHƯƠNG ÁN CÒN LẠI (CHỈ ĐỌC)")
    log("="*150)

    docs = {
        "OFFICIAL_REGISTRY": load_json(REGISTRY),
        "THCS_RESOLUTION": load_json(RESOLUTION),
        "LEVEL_LOCK": load_json(LEVEL_LOCK),
    }

    for op,policy in REMAINING.items():
        log("\n"+"-"*150)
        log("OP =",op)
        log("POLICY =",policy)

        candidate_ids=set()
        total_matches=0

        for label,data in docs.items():
            if data is None:
                log(label,"= FILE_NOT_FOUND_OR_UNREADABLE")
                continue
            matches=recursive_matches(data,op)
            total_matches += len(matches)
            log(label,"MATCH_COUNT =",len(matches))
            for p,obj in matches[:10]:
                log(label,"PATH =",p)
                text=json.dumps(obj,ensure_ascii=False,default=str)
                log(label,"OBJECT =",text[:12000])
                candidate_ids.update(extract_candidate_ids(obj))

        # Nếu op code không nằm trực tiếp trong registry, thử tìm theo object resolution chứa plan_id,
        # rồi lấy plan object tương ứng.
        if candidate_ids:
            log("CANDIDATE_SCHOOL_IDS =",sorted(candidate_ids))
        else:
            log("CANDIDATE_SCHOOL_IDS = []")

        for sid in sorted(candidate_ids):
            brief=school_brief(conn,sid)
            if brief:
                log("SCHOOL_BRIEF",sid,"=",json.dumps(brief,ensure_ascii=False,default=str))

        rel=official_related_to_ids(conn,candidate_ids) if candidate_ids else []
        log("RELATED_OFFICIAL =",rel)

        if policy=="KEEP_NO_DB_WRITE":
            log("DECISION_RULE = KEEP: không chuyển dữ liệu, không khóa tài khoản, không deactivate trường, không tạo merger operation.")
        else:
            log("DECISION_RULE = SPLIT_SOURCE: không dùng whole-school engine; cần khóa chính xác nguồn nào chấm dứt và phần nào chỉ nhận thêm lớp/điểm trường.")

        if total_matches==0:
            log("AUDIT_STATUS = NEEDS_TARGETED_LOOKUP")
        else:
            log("AUDIT_STATUS = COLLECTED")

    log("\nREMAINING_DATABASE_POLICY = KHÔNG GHI DB CHO 7 PHƯƠNG ÁN TRONG BƯỚC RÀ SOÁT NÀY.")

def commit_op0203():
    global LOG
    EXPORT_DIR.mkdir(parents=True,exist_ok=True)
    LOG=OUT.open("w",encoding="utf-8-sig",newline="\n")

    log("="*150)
    log("BATCH THCS: COMMIT OP-0203 + RÀ SOÁT 7 PHƯƠNG ÁN CÒN LẠI")
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
    log("EXPECTED_DB_SHA =",EXPECTED_DB_SHA)
    if sha!=EXPECTED_DB_SHA:
        fail("DB SHA khác nền PREVIEW OP0203")

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

        s=school(conn,SURVIVOR_ID)
        if not s:
            fail("Không tìm thấy survivor 1712")
        if int(s["commune_id"])!=SURVIVOR_COMMUNE_ID or str(s["code"])!=SURVIVOR_CODE or str(s["name"])!=OLD_NAME or int(s["is_active"])!=1:
            fail(f"Survivor sai khóa: {s}")

        # Bảo vệ tuyệt đối 2 trường trùng tên ở địa bàn khác.
        p1465=school(conn,1465)
        p1551=school(conn,1551)
        if not p1465 or int(p1465["commune_id"])!=104 or int(p1465["is_active"])!=0:
            fail("Protected 1465 sai trạng thái")
        if not p1551 or int(p1551["commune_id"])!=127 or int(p1551["is_active"])!=1:
            fail("Protected 1551 sai trạng thái")

        collision=conn.execute(
            "SELECT id FROM schools WHERE commune_id=? AND name=? AND id<>?",
            (SURVIVOR_COMMUNE_ID,NEW_NAME,SURVIVOR_ID)
        ).fetchall()
        if collision:
            fail(f"Va chạm tên mới trong commune 103: {collision}")

        history=conn.execute(
            "SELECT id FROM school_name_histories WHERE school_id=?",(SURVIVOR_ID,)
        ).fetchall()
        if history:
            fail("Survivor đã có lịch sử đổi tên")

        validate_plan(find_plan())

        official,operations=exact_related(conn)
        log("RELATED_OFFICIAL =",official)
        log("RELATED_OPERATIONS =",operations)
        if official or operations:
            fail("Đã có execution liên quan survivor/plan")

        fp=current_footprint(conn,SURVIVOR_ID)
        log("CURRENT_FOOTPRINT =",fp)
        if fp:
            fail("Survivor đã có year=2 footprint")

        base=staff_rows(conn,SURVIVOR_ID,BASE_YEAR_ID)
        require_summary("BASE_STAFF",summary(base),EXPECTED_BASE)

        excluded=[r for r in base if int(r.get("staff_member_id"))==EXCLUDED_MEMBER_ID]
        if len(excluded)!=1:
            fail("Không tìm thấy đúng 1 nhân sự 42021")
        ex=excluded[0]
        if str(ex.get("status_code") or "").strip().upper()!="NGHI_HUU":
            fail("42021 không còn NGHI_HUU")
        if str(ex.get("source_status_label") or "").strip()!="Đã nghỉ hưu":
            fail("42021 không còn 'Đã nghỉ hưu'")

        eligible=[r for r in base if int(r.get("staff_member_id"))!=EXCLUDED_MEMBER_ID]
        require_summary("ELIGIBLE_FINAL",summary(eligible),EXPECTED_FINAL)

        mids=[int(r["staff_member_id"]) for r in eligible]
        if len(mids)!=len(set(mids)):
            fail("Có staff_member_id trùng")
        q=",".join("?" for _ in mids)
        existing=conn.execute(
            f"SELECT staff_member_id,school_id FROM staff_year_records "
            f"WHERE school_year_id=? AND staff_member_id IN ({q})",
            [CURRENT_YEAR_ID]+mids
        ).fetchall()
        log("CURRENT_YEAR_EXISTING =",existing)
        if existing:
            fail("Có staff year=2 đã tồn tại")

        n42021=conn.execute(
            "SELECT COUNT(*) FROM staff_year_records WHERE staff_member_id=? AND school_year_id=?",
            (EXCLUDED_MEMBER_ID,CURRENT_YEAR_ID)
        ).fetchone()[0]
        if n42021!=0:
            fail("42021 đã có year=2")

        users=conn.execute(
            "SELECT id,username,is_active FROM users WHERE school_id=? AND role_id=3 ORDER BY id",
            (SURVIVOR_ID,)
        ).fetchall()
        log("SURVIVOR_USERS =",users)
        if len(users)!=1 or int(users[0][2])!=1:
            fail("Survivor school login sai")

        unrelated_before=unrelated_snapshot(conn)
        op_old_hash,op_old_max=baseline_table(conn,"school_merger_operations")
        off_old_hash,off_old_max=baseline_table(conn,"school_merger_official_executions")
        hist_old_hash,hist_old_max=baseline_table(conn,"school_name_histories")

        actor=choose_actor(conn)
        log("ACTOR =",actor)

        created=clone_staff(conn,eligible)
        log("STAFF_ROLLOVER_CREATED =",created)
        if created!=57:
            fail("Sai số staff rollover")

        # Đổi tên đúng school_id, không đổi mã trường, không đổi commune, không khóa tài khoản.
        cur=conn.execute(
            "UPDATE schools SET name=? WHERE id=? AND name=? AND code=? AND commune_id=? AND is_active=1",
            (NEW_NAME,SURVIVOR_ID,OLD_NAME,SURVIVOR_CODE,SURVIVOR_COMMUNE_ID)
        )
        if cur.rowcount!=1:
            fail("Không đổi tên đúng 1 survivor")
        log("SCHOOL_RENAMED =",cur.rowcount)

        uid,username,fullname=actor
        now=datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
        conn.execute(
            "INSERT INTO school_name_histories "
            "(school_id,effective_school_year_id,old_name,new_name,changed_at,changed_by_user_id) "
            "VALUES (?,?,?,?,?,?)",
            (SURVIVOR_ID,CURRENT_YEAR_ID,OLD_NAME,NEW_NAME,now,uid)
        )
        log("SCHOOL_NAME_HISTORY_CREATED = 1")

        summary_obj={
            "special_execution_type":"THCS_MERGE_TO_NEW_NAME_SURVIVOR_EXISTING_SCHOOL",
            "official_operation_code":OFFICIAL_OPERATION_CODE,
            "plan_id":PLAN_ID,
            "school_year_id":CURRENT_YEAR_ID,
            "target_school_id":SURVIVOR_ID,
            "target_school_code":SURVIVOR_CODE,
            "target_school_old_name":OLD_NAME,
            "target_school_name":NEW_NAME,
            "rename_effective_school_year_id":CURRENT_YEAR_ID,
            "source_school_ids":[],
            "missing_qd_member":"THCS Lê Hồng Phong (Nhân Sơn)",
            "missing_qd_member_policy":"NO_FAKE_SCHOOL_NO_FAKE_STAFF_NO_FAKE_CLASS",
            "excluded_staff_member_ids":[EXCLUDED_MEMBER_ID],
            "excluded_reason":"NGHI_HUU / Đã nghỉ hưu",
            "staff_rollover_created":57,
            "staff_rollover_by_position":{"CBQL":1,"GIAO_VIEN":49,"NHAN_VIEN":7},
            "survivor_school_login_kept_active":1,
            "survivor_school_kept_active":1,
            "protected_school_ids":PROTECTED_IDS,
            "preview_fingerprint":PREVIEW_FINGERPRINT,
        }
        summary_json=json.dumps(summary_obj,ensure_ascii=False,sort_keys=True)
        op_id=insert_logs(conn,actor,backup.stem,summary_json)
        log("MERGER_OPERATION_ID =",op_id)

        # Post-transaction checks before COMMIT.
        s2=school(conn,SURVIVOR_ID)
        if str(s2["name"])!=NEW_NAME or str(s2["code"])!=SURVIVOR_CODE or int(s2["is_active"])!=1:
            fail("Survivor sau đổi tên sai")

        require_summary(
            "FINAL_STAFF",
            summary(staff_rows(conn,SURVIVOR_ID,CURRENT_YEAR_ID)),
            EXPECTED_FINAL
        )

        n42021_after=conn.execute(
            "SELECT COUNT(*) FROM staff_year_records WHERE staff_member_id=? AND school_year_id=?",
            (EXCLUDED_MEMBER_ID,CURRENT_YEAR_ID)
        ).fetchone()[0]
        if n42021_after!=0:
            fail("42021 bị rollover nhầm")

        users_after=conn.execute(
            "SELECT id,username,is_active FROM users WHERE school_id=? AND role_id=3 ORDER BY id",
            (SURVIVOR_ID,)
        ).fetchall()
        if users_after!=users:
            fail("Tài khoản survivor bị thay đổi")

        # Protected rows phải nguyên trạng.
        if school(conn,1465)!=p1465 or school(conn,1551)!=p1551:
            fail("Protected school bị thay đổi")

        diffs=compare_snapshots(unrelated_before,unrelated_snapshot(conn))
        log("UNRELATED_DATA_DIFFS =",diffs)
        if diffs:
            fail("Dữ liệu ngoài write-set bị thay đổi")

        if not old_rows_unchanged(conn,"school_merger_operations",op_old_max,op_old_hash):
            fail("Merger operations cũ bị thay đổi")
        if not old_rows_unchanged(conn,"school_merger_official_executions",off_old_max,off_old_hash):
            fail("Official executions cũ bị thay đổi")
        if not old_rows_unchanged(conn,"school_name_histories",hist_old_max,hist_old_hash):
            fail("School name history cũ bị thay đổi")

        fk2=conn.execute("PRAGMA foreign_key_check").fetchall()
        if fk2:
            fail(f"FK lỗi trong transaction: {fk2[:10]}")

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

    # Post verify rồi mới audit 7 phương án còn lại.
    ro=sqlite3.connect(f"file:{DB.as_posix()}?mode=ro",uri=True,timeout=30)
    try:
        integ=ro.execute("PRAGMA integrity_check").fetchone()[0]
        fk=ro.execute("PRAGMA foreign_key_check").fetchall()
        final=summary(staff_rows(ro,SURVIVOR_ID,CURRENT_YEAR_ID))
        s=school(ro,SURVIVOR_ID)
        users=ro.execute(
            "SELECT id,username,is_active FROM users WHERE school_id=? AND role_id=3 ORDER BY id",
            (SURVIVOR_ID,)
        ).fetchall()
        official=ro.execute(
            "SELECT id,plan_id,operation_id,target_school_id,source_school_ids_json,"
            "backup_name,preview_fingerprint,created_at "
            "FROM school_merger_official_executions WHERE plan_id=?",
            (PLAN_ID,)
        ).fetchall()
        hist=ro.execute(
            "SELECT id,school_id,effective_school_year_id,old_name,new_name,changed_at,changed_by_user_id "
            "FROM school_name_histories WHERE school_id=? ORDER BY id",
            (SURVIVOR_ID,)
        ).fetchall()

        log("\n"+"="*150)
        log("POST VERIFY OP-0203")
        log("="*150)
        log("INTEGRITY_AFTER =",integ)
        log("FK_AFTER =",len(fk))
        log("SURVIVOR_AFTER =",json.dumps(s,ensure_ascii=False,default=str))
        log("FINAL_STAFF =",json.dumps(final,ensure_ascii=False))
        log("SURVIVOR_USERS_AFTER =",users)
        log("NAME_HISTORY =",hist)
        log("OFFICIAL_EXECUTION =",json.dumps(official,ensure_ascii=False,default=str))
        log("DB_SHA_AFTER_OP0203 =",sha256_file(DB))

        if integ!="ok" or fk: fail("Post health lỗi")
        require_summary("POST_FINAL",final,EXPECTED_FINAL)
        if str(s["name"])!=NEW_NAME or int(s["is_active"])!=1: fail("Post survivor sai")
        if len(official)!=1: fail("Official execution không đúng 1 dòng")
        if len(hist)!=1: fail("Name history không đúng 1 dòng")

        log("COMMIT_OP0203_SUCCESS = YES")
        log("OPERATION_ID =",op_id)

        audit_remaining(ro)

    finally:
        ro.close()

    log("\n"+"="*150)
    log("BATCH_SUCCESS = YES")
    log("OP0203 = COMMITTED")
    log("7_REMAINING = AUDITED_READ_ONLY")
    log("DATABASE_WRITES_FOR_REMAINING_7 = 0")
    log("BACKUP =",backup)
    log("="*150)

def main():
    global LOG
    try:
        commit_op0203()
    except Exception as exc:
        try:
            log("\n"+"="*150)
            log("BATCH_SUCCESS = NO")
            log("ERROR =",repr(exc))
            if DB.exists():
                log("DB_SHA_CURRENT =",sha256_file(DB))
            log("DỪNG AN TOÀN.")
            log("="*150)
        finally:
            if LOG:
                LOG.close()
        return 1
    else:
        if LOG:
            LOG.close()
        return 0

if __name__=="__main__":
    sys.exit(main())
