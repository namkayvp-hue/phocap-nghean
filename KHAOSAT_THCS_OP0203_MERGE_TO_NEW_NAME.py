# -*- coding: utf-8 -*-
from __future__ import annotations

import csv
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
REPORT_DIR = ROOT / "bao_cao_v13_2_2_sap_nhap_toan_tinh_20260904_102129"
REPORT_700 = REPORT_DIR / "700_DANH_SACH_NHOM_PHUONG_AN.csv"
EXPORT_DIR = ROOT / "exports"
OUT = EXPORT_DIR / "KHAOSAT_THCS_OP0203_MERGE_TO_NEW_NAME.txt"

EXPECTED_DB_SHA = "1723e12a3d06d8f52b7b899174d5040bc4937ab84564e0f4d51b009586d8ce22"

OP0203_PLAN = "PA2026-16141F34ACBC"
OP0203_COMMUNE = "Thuần Trung"
OP0203_TARGET_NAME = "THCS Lê Hồng Phong"

KIM_DONG_ID = 1712
LHP_BACH_HA_ID = 1465
LHP_HUNG_NGUYEN_ID = 1551
CURRENT_YEAR_ID = 2
BASE_YEAR_ID = 1

EXCLUDED_CODES = {"NGHI_HUU","CHUYEN_DI","THOI_VIEC","DA_NGHI"}
EXCLUDED_LABELS = {"Đã nghỉ hưu","Đã chuyển đi","Nghỉ hưu","Chuyển đi"}

def sha256_file(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()

def load_json(path):
    for enc in ("utf-8-sig","utf-8"):
        try:
            return json.loads(path.read_text(encoding=enc))
        except Exception:
            pass
    return None

def registry_plans():
    data = load_json(REGISTRY)
    if isinstance(data, dict):
        return [p for p in (data.get("plans") or []) if isinstance(p, dict)]
    return []

def plan_by_id(pid):
    for p in registry_plans():
        if p.get("id") == pid:
            return p
    return None

def school(conn, sid):
    return conn.execute(
        "SELECT id,commune_id,code,name,is_active,created_at FROM schools WHERE id=?",
        (sid,)
    ).fetchone()

def staff_rows(conn, sid, year_id):
    cur = conn.execute(
        "SELECT * FROM staff_year_records WHERE school_id=? AND school_year_id=? ORDER BY staff_member_id,id",
        (sid, year_id)
    )
    names = [d[0] for d in cur.description]
    return [dict(zip(names, r)) for r in cur.fetchall()]

def staff_summary(rows):
    c = Counter(str(r.get("position_group") or "NULL") for r in rows)
    return {
        "TOTAL":len(rows),
        "CBQL":c.get("CBQL",0),
        "GIAO_VIEN":c.get("GIAO_VIEN",0),
        "NHAN_VIEN":c.get("NHAN_VIEN",0),
    }

def eligible(row):
    if int(row.get("is_active") or 0) != 1:
        return False, "is_active != 1"
    status = str(row.get("status_code") or "").strip().upper()
    label = str(row.get("source_status_label") or "").strip()
    if status in EXCLUDED_CODES:
        return False, "status_code="+status
    if label in EXCLUDED_LABELS:
        return False, "source_status_label="+label
    return True, ""

def role3_users(conn, sid):
    return conn.execute(
        "SELECT id,username,is_active FROM users WHERE school_id=? AND role_id=3 ORDER BY id",
        (sid,)
    ).fetchall()

def official_for_plan(conn, pid):
    return conn.execute(
        """
        SELECT id,plan_id,operation_id,school_year_id,target_school_id,
               source_school_ids_json,backup_name,preview_fingerprint,
               summary_json,created_at
        FROM school_merger_official_executions
        WHERE plan_id=?
        ORDER BY id
        """,
        (pid,)
    ).fetchall()

def operation_by_id(conn, oid):
    return conn.execute(
        """
        SELECT id,school_year_id,target_school_id,source_school_ids_json,
               actor_user_id,backup_name,summary_json,created_at
        FROM school_merger_operations
        WHERE id=?
        """,
        (oid,)
    ).fetchone()

def table_names(conn):
    return [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()]

def current_footprint(conn, sid):
    hits=[]
    for table in table_names(conn):
        info=conn.execute(f'PRAGMA table_info("{table.replace(chr(34), chr(34)*2)}")').fetchall()
        cols=[r[1] for r in info]
        if "school_id" not in cols or "school_year_id" not in cols:
            continue
        try:
            n=conn.execute(
                f'SELECT COUNT(*) FROM "{table.replace(chr(34), chr(34)*2)}" WHERE school_id=? AND school_year_id=?',
                (sid,CURRENT_YEAR_ID)
            ).fetchone()[0]
            if n:
                hits.append((table,n))
        except sqlite3.Error:
            pass
    return hits

def read_csv_rows(path):
    if not path.exists():
        return [], []
    for enc in ("utf-8-sig","utf-8","cp1258","cp1252"):
        try:
            with path.open("r", encoding=enc, newline="") as f:
                reader=csv.DictReader(f)
                return reader.fieldnames or [], list(reader)
        except Exception:
            pass
    return [], []

def row_text(row):
    return " | ".join(str(v or "") for v in row.values())

def map_report_row_to_plan(row):
    vals = {str(k).lower(): str(v or "") for k,v in row.items()}
    commune = ""
    target = ""
    for k,v in vals.items():
        if "commune" in k or "xa" == k or "xã" in k:
            commune = v.strip()
        if "official_plan" in k or "target_text" in k or k in {"target","plan_text"}:
            if v.strip():
                target = v.strip()
    text = row_text(row)
    # Fallback parse from any plan by commune + target exact occurrence.
    candidates=[]
    for p in registry_plans():
        if p.get("school_year_code") != "2026-2027":
            continue
        if commune and p.get("commune_excel") != commune:
            continue
        if target and p.get("plan_text") != target:
            continue
        members=[str(m.get("school_name","")) for m in p.get("members") or [] if isinstance(m,dict)]
        score=sum(1 for m in members if m and m in text)
        candidates.append((score,p))
    if not candidates:
        return None
    candidates.sort(key=lambda x:(x[0], str(x[1].get("id"))), reverse=True)
    best=candidates[0]
    return best[1] if best[0] > 0 or (commune and target) else None

def print_execution_case(conn, label, plan):
    pid=plan.get("id")
    ex=official_for_plan(conn,pid)
    print("\n"+"-"*150)
    print("CASE =", label)
    print("PLAN_ID =", pid)
    print("COMMUNE =", plan.get("commune_excel"))
    print("PLAN_TEXT =", plan.get("plan_text"))
    print("ACTION_TYPE =", plan.get("action_type"))
    print("TARGET_MEMBER_INDEX =", plan.get("target_member_index"))
    print("MEMBERS =", json.dumps(plan.get("members"), ensure_ascii=False, default=str))
    print("OFFICIAL_EXECUTION_COUNT =", len(ex))
    for row in ex:
        print("OFFICIAL =", row)
        target_id=int(row[4])
        print("TARGET_SCHOOL_NOW =", school(conn,target_id))
        try:
            src_ids=[int(x) for x in json.loads(row[5] or "[]")]
        except Exception:
            src_ids=[]
        print("SOURCE_SCHOOLS_NOW =", [school(conn,x) for x in src_ids])
        print("OPERATION =", operation_by_id(conn,int(row[2])))

def main():
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)

    print("="*150)
    print("OP-0203 - KHẢO SÁT TIỀN LỆ MERGE_TO_NEW_NAME")
    print("MỤC TIÊU: xác định cách các phương án 'gộp sang tên mới' đã được hệ thống xử lý an toàn.")
    print("CHỈ ĐỌC - KHÔNG GHI DATABASE")
    print("="*150)

    if not DB.exists():
        print("STOP = Không tìm thấy DB")
        return 2

    sha=sha256_file(DB)
    print("DB_SHA =",sha)
    print("EXPECTED_DB_SHA =",EXPECTED_DB_SHA)
    if sha != EXPECTED_DB_SHA:
        print("STOP = DB SHA đã khác nền sau OP-0172.")
        return 1

    conn=sqlite3.connect(DB.resolve().as_uri()+"?mode=ro", uri=True, timeout=30)
    conn.execute("PRAGMA query_only=ON")
    try:
        integ=conn.execute("PRAGMA integrity_check").fetchone()[0]
        fk=conn.execute("PRAGMA foreign_key_check").fetchall()
        print("integrity =",integ)
        print("FK =",len(fk))
        if integ!="ok" or fk:
            print("STOP = Database health không đạt.")
            return 1

        print("\nOP0203 CURRENT STATE")
        p=plan_by_id(OP0203_PLAN)
        print("PLAN =",json.dumps(p,ensure_ascii=False,indent=2,default=str))
        for sid in (KIM_DONG_ID,LHP_BACH_HA_ID,LHP_HUNG_NGUYEN_ID):
            print("\nSCHOOL =",school(conn,sid))
            print("ROLE3_USERS =",role3_users(conn,sid))
            print("CURRENT_FOOTPRINT =",current_footprint(conn,sid))
            base=staff_rows(conn,sid,BASE_YEAR_ID)
            print("BASE_STAFF =",json.dumps(staff_summary(base),ensure_ascii=False))

        kim_rows=staff_rows(conn,KIM_DONG_ID,BASE_YEAR_ID)
        excluded=[]
        eligible_rows=[]
        for r in kim_rows:
            ok,why=eligible(r)
            if ok:
                eligible_rows.append(r)
            else:
                excluded.append({
                    "staff_member_id":r.get("staff_member_id"),
                    "position_group":r.get("position_group"),
                    "status_code":r.get("status_code"),
                    "source_status_label":r.get("source_status_label"),
                    "reason":why,
                })
        print("KIM_DONG_EXCLUDED =",json.dumps(excluded,ensure_ascii=False,indent=2,default=str))
        print("KIM_DONG_ELIGIBLE_FINAL =",json.dumps(staff_summary(eligible_rows),ensure_ascii=False))
        print("OP0203_EXISTING_EXECUTION =",official_for_plan(conn,OP0203_PLAN))

        print("\n"+"="*150)
        print("SEARCH COMPLETED MERGE_TO_NEW_NAME PRECEDENTS")
        print("="*150)

        headers,rows=read_csv_rows(REPORT_700)
        print("REPORT_700_EXISTS =",REPORT_700.exists())
        print("REPORT_700_HEADERS =",headers)

        merge_new=[r for r in rows if "MERGE_TO_NEW_NAME" in row_text(r)]
        print("MERGE_TO_NEW_NAME_REPORT_COUNT =",len(merge_new))

        completed_count=0
        shown=0
        for i,row in enumerate(merge_new, start=1):
            plan=map_report_row_to_plan(row)
            if not plan:
                print("\nUNMAPPED_REPORT_ROW =",row)
                continue
            ex=official_for_plan(conn,plan.get("id"))
            if ex:
                completed_count += 1
                if shown < 15:
                    print_execution_case(conn, f"REPORT_ROW_{i}", plan)
                    shown += 1

        print("COMPLETED_MERGE_TO_NEW_NAME_CASES =",completed_count)

        print("\n"+"="*150)
        print("SUMMARY_JSON SEARCH")
        print("="*150)
        keys=("NEW_NAME","RENAME","SOURCE2_IS_TARGET","SPECIAL","surviv","target_name")
        for table in ("school_merger_operations","school_merger_official_executions"):
            print("\nTABLE =",table)
            cols=[r[1] for r in conn.execute(f'PRAGMA table_info("{table}")').fetchall()]
            if "summary_json" not in cols:
                print("NO summary_json")
                continue
            rows2=conn.execute(
                f'SELECT id,summary_json FROM "{table}" WHERE summary_json IS NOT NULL ORDER BY id'
            ).fetchall()
            found=0
            for rid,s in rows2:
                text=str(s or "")
                if any(k.lower() in text.lower() for k in keys):
                    print("ROW",rid,"=>",text[:2000])
                    found+=1
                    if found>=30:
                        break
            print("MATCH_COUNT_SHOWN =",found)

        print("\n"+"="*150)
        print("RENAME-RELATED TABLES")
        print("="*150)
        for t in table_names(conn):
            low=t.lower()
            if "rename" in low or "name_history" in low or "school_name" in low:
                print("TABLE =",t)
                print("SCHEMA =",conn.execute(f'PRAGMA table_info("{t}")').fetchall())
                try:
                    print("LAST_ROWS =",conn.execute(f'SELECT * FROM "{t}" ORDER BY id DESC LIMIT 20').fetchall())
                except sqlite3.Error:
                    pass

        print("\n"+"="*150)
        print("KẾT LUẬN KỸ THUẬT")
        print("="*150)
        print("OP0203_TARGET_NAME =",OP0203_TARGET_NAME)
        print("KIM_DONG_SURVIVOR_CANDIDATE =",school(conn,KIM_DONG_ID))
        print("LHP_BACH_HA_ALREADY_USED =",official_for_plan(conn,"PA2026-98173E42E1D0"))
        print("LHP_HUNG_NGUYEN_MUST_REMAIN_UNTOUCHED =",school(conn,LHP_HUNG_NGUYEN_ID))
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
