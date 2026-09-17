# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(r"C:\PhoCap")
DB = ROOT / "data" / "phocap.db"
REGISTRY = ROOT / "school_merger_official_registry_v2.json"
EXPORT_DIR = ROOT / "exports"
OUT = EXPORT_DIR / "PREVIEW_THCS_OP0203.txt"

EXPECTED_DB_SHA = "1723e12a3d06d8f52b7b899174d5040bc4937ab84564e0f4d51b009586d8ce22"

PLAN_ID = "PA2026-16141F34ACBC"
OP_CODE = "QD3805-OP-0203"

SURVIVOR_ID = 1712
SURVIVOR_COMMUNE_ID = 103
SURVIVOR_CODE = "40427524"
OLD_NAME = "THCS Kim Đồng"
NEW_NAME = "THCS Lê Hồng Phong"

MISSING_QD_MEMBER = "THCS Lê Hồng Phong (Nhân Sơn)"
PROTECTED_LHP_HUNG_NGUYEN_ID = 1551
USED_LHP_BACH_HA_ID = 1465

EXCLUDED_MEMBER_IDS = {42021}

BASE_YEAR_ID = 1
CURRENT_YEAR_ID = 2

EXPECTED_BASE = {"TOTAL":58,"CBQL":1,"GIAO_VIEN":50,"NHAN_VIEN":7}
EXPECTED_FINAL = {"TOTAL":57,"CBQL":1,"GIAO_VIEN":49,"NHAN_VIEN":7}

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()

def load_json(path: Path):
    for enc in ("utf-8-sig","utf-8"):
        try:
            return json.loads(path.read_text(encoding=enc))
        except Exception:
            pass
    return None

def find_plan():
    data = load_json(REGISTRY)
    if isinstance(data, dict):
        for p in data.get("plans") or []:
            if isinstance(p, dict) and p.get("id") == PLAN_ID:
                return p
    return None

def table_names(conn):
    return [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()]

def columns(conn, table):
    safe = table.replace('"','""')
    return [r[1] for r in conn.execute(f'PRAGMA table_info("{safe}")').fetchall()]

def school(conn, sid):
    return conn.execute(
        "SELECT id,commune_id,code,name,is_active,created_at FROM schools WHERE id=?",
        (sid,)
    ).fetchone()

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

def current_footprint(conn, sid):
    hits=[]
    for table in table_names(conn):
        c=columns(conn,table)
        if "school_id" not in c or "school_year_id" not in c:
            continue
        safe=table.replace('"','""')
        try:
            n=conn.execute(
                f'SELECT COUNT(*) FROM "{safe}" WHERE school_id=? AND school_year_id=?',
                (sid,CURRENT_YEAR_ID)
            ).fetchone()[0]
            if n:
                hits.append((table,n))
        except sqlite3.Error:
            pass
    return hits

def related(conn):
    official=[]
    for r in conn.execute(
        "SELECT id,plan_id,operation_id,target_school_id,source_school_ids_json,created_at "
        "FROM school_merger_official_executions ORDER BY id"
    ).fetchall():
        try:
            src={int(x) for x in json.loads(r[4] or "[]")}
        except Exception:
            src=set()
        if r[1]==PLAN_ID or int(r[3])==SURVIVOR_ID or SURVIVOR_ID in src:
            official.append(r)

    operations=[]
    for r in conn.execute(
        "SELECT id,target_school_id,source_school_ids_json,created_at "
        "FROM school_merger_operations ORDER BY id"
    ).fetchall():
        try:
            src={int(x) for x in json.loads(r[2] or "[]")}
        except Exception:
            src=set()
        if int(r[1])==SURVIVOR_ID or SURVIVOR_ID in src:
            operations.append(r)
    return official,operations

def main():
    EXPORT_DIR.mkdir(parents=True,exist_ok=True)

    print("="*150)
    print("PREVIEW THCS QD3805-OP-0203")
    print("MERGE_TO_NEW_NAME: giữ school_id=1712, đổi tên THCS Kim Đồng -> THCS Lê Hồng Phong")
    print("Không tạo dữ liệu giả cho THCS Lê Hồng Phong (Nhân Sơn) vì DB/source roster không có school_id tương ứng.")
    print("CHỈ ĐỌC - KHÔNG GHI DATABASE")
    print("="*150)

    if not DB.exists():
        print("DỪNG: Không tìm thấy DB",DB)
        return 2

    sha=sha256_file(DB)
    print("DB_SHA =",sha)
    print("EXPECTED_DB_SHA =",EXPECTED_DB_SHA)

    conn=sqlite3.connect(DB.resolve().as_uri()+"?mode=ro",uri=True,timeout=30)
    conn.execute("PRAGMA query_only=ON")
    try:
        reasons=[]

        integ=conn.execute("PRAGMA integrity_check").fetchone()[0]
        fk=conn.execute("PRAGMA foreign_key_check").fetchall()
        print("integrity =",integ)
        print("FK =",len(fk))
        if sha!=EXPECTED_DB_SHA:
            reasons.append("DB SHA khác nền sau OP-0172")
        if integ!="ok" or fk:
            reasons.append("Database health không đạt")

        plan=find_plan()
        print("\nPLAN =",json.dumps(plan,ensure_ascii=False,indent=2,default=str))
        if not plan:
            reasons.append("Không tìm thấy plan")
        else:
            if plan.get("school_year_code")!="2026-2027":
                reasons.append("Plan sai school_year_code")
            if plan.get("commune_excel")!="Thuần Trung":
                reasons.append("Plan sai commune_excel")
            if plan.get("plan_text")!=NEW_NAME:
                reasons.append("Plan sai plan_text")
            if plan.get("action_type")!="SPECIAL":
                reasons.append("Plan không còn SPECIAL")
            if plan.get("target_member_index") is not None:
                reasons.append("Plan target_member_index không còn null")
            names=[str(x.get("school_name","")) for x in plan.get("members") or [] if isinstance(x,dict)]
            if names!=["THCS Kim Đồng (Minh Sơn)","THCS Lê Hồng Phong (Nhân Sơn)"]:
                reasons.append("Plan members không đúng")

        survivor=school(conn,SURVIVOR_ID)
        protected=school(conn,PROTECTED_LHP_HUNG_NGUYEN_ID)
        used=school(conn,USED_LHP_BACH_HA_ID)
        print("\nSURVIVOR =",survivor)
        print("PROTECTED_HUNG_NGUYEN =",protected)
        print("USED_BACH_HA =",used)

        if not survivor:
            reasons.append("Không tìm thấy survivor 1712")
        else:
            if int(survivor[1])!=SURVIVOR_COMMUNE_ID or str(survivor[2])!=SURVIVOR_CODE or str(survivor[3])!=OLD_NAME or int(survivor[4])!=1:
                reasons.append("Survivor 1712 sai commune/code/name/active")

        if not protected or int(protected[1])!=127 or str(protected[2])!="40431501" or int(protected[4])!=1:
            reasons.append("Trường Lê Hồng Phong Hưng Nguyên không đúng trạng thái bảo vệ")

        if not used or int(used[1])!=104 or str(used[2])!="40427522" or int(used[4])!=0:
            reasons.append("Trường Lê Hồng Phong Bạch Hà không đúng trạng thái đã dùng")

        collisions=conn.execute(
            "SELECT id,commune_id,code,name,is_active FROM schools WHERE commune_id=? AND name=? ORDER BY id",
            (SURVIVOR_COMMUNE_ID,NEW_NAME)
        ).fetchall()
        print("NEW_NAME_COLLISIONS_IN_COMMUNE =",collisions)
        if collisions:
            reasons.append("Đã tồn tại trường cùng tên THCS Lê Hồng Phong tại commune 103")

        history=conn.execute(
            "SELECT id,school_id,effective_school_year_id,old_name,new_name,changed_at "
            "FROM school_name_histories WHERE school_id=? ORDER BY id",
            (SURVIVOR_ID,)
        ).fetchall()
        print("SURVIVOR_NAME_HISTORY =",history)
        if history:
            reasons.append("Survivor 1712 đã có lịch sử đổi tên trước")

        base=staff_rows(conn,SURVIVOR_ID,BASE_YEAR_ID)
        print("BASE_STAFF =",json.dumps(summary(base),ensure_ascii=False))
        if summary(base)!=EXPECTED_BASE:
            reasons.append("Base staff 1712 sai")

        excluded=[]
        eligible=[]
        for r in base:
            mid=int(r.get("staff_member_id"))
            if mid in EXCLUDED_MEMBER_IDS:
                excluded.append({
                    "staff_member_id":mid,
                    "position_group":r.get("position_group"),
                    "status_code":r.get("status_code"),
                    "source_status_label":r.get("source_status_label"),
                })
            else:
                eligible.append(r)

        print("EXCLUDED =",json.dumps(excluded,ensure_ascii=False,indent=2,default=str))
        print("SIMULATED_FINAL =",json.dumps(summary(eligible),ensure_ascii=False))
        if {x["staff_member_id"] for x in excluded}!=EXCLUDED_MEMBER_IDS:
            reasons.append("Không tìm thấy đúng staff_member_id=42021")
        if len(excluded)!=1:
            reasons.append("Số excluded không đúng 1")
        else:
            x=excluded[0]
            if str(x.get("status_code") or "").strip().upper()!="NGHI_HUU" or str(x.get("source_status_label") or "").strip()!="Đã nghỉ hưu":
                reasons.append("42021 không còn NGHI_HUU / Đã nghỉ hưu")
        if summary(eligible)!=EXPECTED_FINAL:
            reasons.append("Final eligible không đúng 57")

        mids=[int(r["staff_member_id"]) for r in eligible]
        if len(mids)!=len(set(mids)):
            reasons.append("Có staff_member_id trùng")

        if mids:
            q=",".join("?" for _ in mids)
            current=conn.execute(
                f"SELECT staff_member_id,school_id FROM staff_year_records "
                f"WHERE school_year_id=? AND staff_member_id IN ({q}) ORDER BY staff_member_id,school_id",
                [CURRENT_YEAR_ID]+mids
            ).fetchall()
        else:
            current=[]
        print("CURRENT_YEAR_EXISTING =",current)
        if current:
            reasons.append("Có eligible staff đã tồn tại year=2")

        n42021=conn.execute(
            "SELECT COUNT(*) FROM staff_year_records WHERE staff_member_id=? AND school_year_id=?",
            (42021,CURRENT_YEAR_ID)
        ).fetchone()[0]
        print("EXCLUDED_42021_YEAR2_COUNT =",n42021)
        if n42021!=0:
            reasons.append("42021 đã có year=2")

        fp=current_footprint(conn,SURVIVOR_ID)
        print("SURVIVOR_CURRENT_FOOTPRINT =",fp)
        if fp:
            reasons.append("Survivor đã có footprint year=2")

        users=conn.execute(
            "SELECT id,username,is_active FROM users WHERE school_id=? AND role_id=3 ORDER BY id",
            (SURVIVOR_ID,)
        ).fetchall()
        print("SURVIVOR_ROLE3_USERS =",users)
        if len(users)!=1 or int(users[0][2])!=1:
            reasons.append("Survivor school login không đúng")

        official,operations=related(conn)
        print("RELATED_OFFICIAL =",official)
        print("RELATED_OPERATIONS =",operations)
        if official:
            reasons.append("Đã có official execution liên quan")
        if operations:
            reasons.append("Đã có merger operation liên quan")

        payload={
            "op":OP_CODE,
            "plan_id":PLAN_ID,
            "model":"MERGE_TO_NEW_NAME_SURVIVOR_EXISTING_SCHOOL",
            "survivor_school_id":SURVIVOR_ID,
            "survivor_school_code":SURVIVOR_CODE,
            "old_name":OLD_NAME,
            "new_name":NEW_NAME,
            "missing_qd_member":MISSING_QD_MEMBER,
            "missing_qd_member_db_school_id":None,
            "excluded_staff_member_ids":sorted(EXCLUDED_MEMBER_IDS),
            "final_staff":EXPECTED_FINAL,
            "official_target_school_id":SURVIVOR_ID,
            "official_source_school_ids":[],
            "protected_school_ids":[PROTECTED_LHP_HUNG_NGUYEN_ID,USED_LHP_BACH_HA_ID],
        }
        fingerprint=hashlib.sha256(
            json.dumps(payload,ensure_ascii=False,sort_keys=True,default=str).encode("utf-8")
        ).hexdigest()
        print("PREVIEW_FINGERPRINT =",fingerprint)

        print("\n"+"="*150)
        if reasons:
            print("PREVIEW_READY = NO")
            for r in reasons:
                print("REASON =",r)
        else:
            print("PREVIEW_READY = YES")
            print("MODEL = MERGE_TO_NEW_NAME_SURVIVOR_EXISTING_SCHOOL")
            print("SURVIVOR_ID =",SURVIVOR_ID)
            print("SURVIVOR_CODE =",SURVIVOR_CODE)
            print("RENAME =",OLD_NAME,"->",NEW_NAME)
            print("EXCLUDED_STAFF_MEMBER_IDS =",sorted(EXCLUDED_MEMBER_IDS))
            print("FINAL_STAFF =",json.dumps(EXPECTED_FINAL,ensure_ascii=False))
            print("SURVIVOR_LOGIN_POLICY = KEEP_ACTIVE")
            print("SURVIVOR_SCHOOL_POLICY = KEEP_ACTIVE")
            print("OFFICIAL_TARGET_SCHOOL_ID =",SURVIVOR_ID)
            print("OFFICIAL_SOURCE_SCHOOL_IDS = []")
            print("MISSING_QD_MEMBER =",MISSING_QD_MEMBER)
            print("MISSING_QD_MEMBER_POLICY = NO_FAKE_SCHOOL_NO_FAKE_STAFF_NO_FAKE_CLASS")
            print("PROTECTED_HUNG_NGUYEN_1551 = UNTOUCHED")
            print("USED_BACH_HA_1465 = UNTOUCHED")
        print("DATABASE = KHÔNG THAY ĐỔI")
        print("="*150)
        return 0
    finally:
        conn.close()

if __name__=="__main__":
    class Tee:
        def __init__(self,*streams):
            self.streams=streams
        def write(self,data):
            for s in self.streams:
                s.write(data)
                s.flush()
        def flush(self):
            for s in self.streams:
                s.flush()

    EXPORT_DIR.mkdir(parents=True,exist_ok=True)
    with OUT.open("w",encoding="utf-8-sig",newline="\n") as f:
        old=sys.stdout
        sys.stdout=Tee(old,f)
        try:
            code=main()
        finally:
            sys.stdout=old
    sys.exit(code)
