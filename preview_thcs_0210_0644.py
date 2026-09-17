# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(r"C:\PhoCap")
DB = ROOT / "data" / "phocap.db"
REGISTRY = ROOT / "school_merger_official_registry_v2.json"

EXPECTED_DB_SHA = "3837441007286585e4eb28e9e9246a9f33fe339efc09c4b1e8f4fb048db89e70"
BASE_YEAR_ID = 1
CURRENT_YEAR_ID = 2

CASES = [
    {
        "op": "QD3805-OP-0210",
        "plan_id": "PA2026-0104708B7153",
        "source_id": 1733,
        "source_code": "40427505",
        "source_name": "THCS Thượng Sơn",
        "target_id": 1734,
        "target_code": "40427510",
        "target_name": "THCS Trần Phú",
        "commune_id": 102,
        "expected_source": {"TOTAL":34,"CBQL":2,"GIAO_VIEN":27,"NHAN_VIEN":5},
        "expected_target": {"TOTAL":55,"CBQL":2,"GIAO_VIEN":47,"NHAN_VIEN":6},
        "expected_final": {"TOTAL":89,"CBQL":4,"GIAO_VIEN":74,"NHAN_VIEN":11},
        "plan_note": "PLAN có thêm dòng orphan THCS Văn Hiến; PREVIEW chỉ cho phép 1733 -> 1734, KHÔNG chạm Văn Hiến.",
    },
    {
        "op": "QD3805-OP-0644",
        "plan_id": "PA2026-52415E680B77",
        "source_id": 1748,
        "source_code": "40418519",
        "source_name": "THCS Yên Hòa",
        "target_id": 1747,
        "target_code": "40418511",
        "target_name": "PTDTBT THCS Yên Thắng",
        "commune_id": 32,
        "expected_source": {"TOTAL":21,"CBQL":2,"GIAO_VIEN":16,"NHAN_VIEN":3},
        "expected_target": {"TOTAL":22,"CBQL":3,"GIAO_VIEN":16,"NHAN_VIEN":3},
        "expected_final": {"TOTAL":43,"CBQL":5,"GIAO_VIEN":32,"NHAN_VIEN":6},
        "plan_note": "Khóa alias PT DTBT Yên Hòa = THCS Yên Hòa id=1748.",
    },
]

EXCLUDED_STATUS_CODES = {"NGHI_HUU","CHUYEN_DI","THOI_VIEC","DA_NGHI"}
EXCLUDED_SOURCE_LABELS = {"Đã nghỉ hưu","Đã chuyển đi","Nghỉ hưu","Chuyển đi"}

def sha256_file(path: Path) -> str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda:f.read(1024*1024),b""):
            h.update(block)
    return h.hexdigest()

def load_registry():
    if not REGISTRY.exists():
        return None
    for enc in ("utf-8-sig","utf-8"):
        try:
            return json.loads(REGISTRY.read_text(encoding=enc))
        except Exception:
            pass
    return None

def find_plan(reg, plan_id):
    if not isinstance(reg,dict):
        return None
    plans=reg.get("plans")
    if not isinstance(plans,list):
        return None
    for p in plans:
        if isinstance(p,dict) and p.get("id")==plan_id:
            return p
    return None

def school(conn,sid):
    cur=conn.execute("SELECT * FROM schools WHERE id=?",(sid,))
    row=cur.fetchone()
    if row is None:
        return None
    names=[d[0] for d in cur.description]
    return dict(zip(names,row))

def require_school(row,c,role):
    if not row:
        raise RuntimeError(f"{role}: không tìm thấy school_id={c[role.lower()+'_id']}")
    sid=c[role.lower()+"_id"]
    code=c[role.lower()+"_code"]
    name=c[role.lower()+"_name"]
    if int(row["id"])!=sid or str(row["code"])!=code:
        raise RuntimeError(f"{role}: sai id/code: {row}")
    if name.lower() not in str(row["name"]).lower():
        raise RuntimeError(f"{role}: sai tên: {row['name']}")
    if int(row["commune_id"])!=c["commune_id"]:
        raise RuntimeError(f"{role}: sai commune_id: {row['commune_id']}")
    if int(row["is_active"])!=1:
        raise RuntimeError(f"{role}: trường không active")

def staff_rows(conn,sid,year):
    cur=conn.execute(
        "SELECT * FROM staff_year_records WHERE school_id=? AND school_year_id=? ORDER BY staff_member_id,id",
        (sid,year)
    )
    names=[d[0] for d in cur.description]
    return [dict(zip(names,r)) for r in cur.fetchall()]

def eligible(r):
    if int(r.get("is_active") or 0)!=1:
        return False, "is_active != 1"
    status=str(r.get("status_code") or "").strip().upper()
    label=str(r.get("source_status_label") or "").strip()
    if status in EXCLUDED_STATUS_CODES:
        return False, f"status_code={status}"
    if label in EXCLUDED_SOURCE_LABELS:
        return False, f"source_status_label={label}"
    return True,""

def summary(rows):
    c=Counter(str(r.get("position_group") or "NULL") for r in rows)
    return {
        "TOTAL":len(rows),
        "CBQL":c.get("CBQL",0),
        "GIAO_VIEN":c.get("GIAO_VIEN",0),
        "NHAN_VIEN":c.get("NHAN_VIEN",0),
    }

def exact_related_execution(conn,c):
    sids={c["source_id"],c["target_id"]}
    official=[]
    rows=conn.execute(
        """
        SELECT id,plan_id,operation_id,school_year_id,target_school_id,source_school_ids_json,created_at
        FROM school_merger_official_executions ORDER BY id
        """
    ).fetchall()
    for r in rows:
        try:
            arr={int(x) for x in json.loads(r[5] or "[]")}
        except Exception:
            arr=set()
        if r[1]==c["plan_id"] or int(r[4]) in sids or bool(arr & sids):
            official.append(r)

    ops=[]
    rows=conn.execute(
        """
        SELECT id,school_year_id,target_school_id,source_school_ids_json,created_at
        FROM school_merger_operations ORDER BY id
        """
    ).fetchall()
    for r in rows:
        try:
            arr={int(x) for x in json.loads(r[3] or "[]")}
        except Exception:
            arr=set()
        if int(r[2]) in sids or bool(arr & sids):
            ops.append(r)
    return official,ops

def current_anywhere(conn,member_ids):
    if not member_ids:
        return []
    q=",".join("?" for _ in member_ids)
    return conn.execute(
        f"""
        SELECT staff_member_id,school_id
        FROM staff_year_records
        WHERE school_year_id=? AND staff_member_id IN ({q})
        ORDER BY staff_member_id,school_id
        """,
        [CURRENT_YEAR_ID]+member_ids
    ).fetchall()

def school_users(conn,sid):
    return conn.execute(
        """
        SELECT id,username,full_name,role_id,school_id,is_active
        FROM users WHERE school_id=? ORDER BY id
        """,
        (sid,)
    ).fetchall()

def main():
    print("="*150)
    print("PREVIEW 2 PHƯƠNG ÁN THCS: OP-0210 / OP-0644 - CHỈ ĐỌC")
    print("="*150)

    if not DB.exists():
        print("DỪNG: không tìm thấy DB")
        sys.exit(2)

    sha=sha256_file(DB)
    print("DB_SHA =",sha)
    print("EXPECTED_DB_SHA =",EXPECTED_DB_SHA)

    conn=sqlite3.connect(DB.resolve().as_uri()+"?mode=ro",uri=True,timeout=30)
    conn.execute("PRAGMA query_only=ON")
    reg=load_registry()

    try:
        integ=conn.execute("PRAGMA integrity_check").fetchone()[0]
        fk=conn.execute("PRAGMA foreign_key_check").fetchall()
        print("integrity =",integ)
        print("FK =",len(fk))
        if sha!=EXPECTED_DB_SHA or integ!="ok" or fk:
            print("PREVIEW_ALL_READY = NO")
            print("LÝ DO = DB SHA/health không đúng nền hậu kiểm Mậu Đôn.")
            return

        all_ready=True

        for c in CASES:
            print("\n"+"#"*150)
            print("OPERATION =",c["op"])
            print("#"*150)

            reasons=[]
            src=school(conn,c["source_id"])
            tgt=school(conn,c["target_id"])
            print("SOURCE =",json.dumps(src,ensure_ascii=False,default=str))
            print("TARGET =",json.dumps(tgt,ensure_ascii=False,default=str))

            try:
                require_school(src,c,"SOURCE")
                require_school(tgt,c,"TARGET")
            except Exception as e:
                reasons.append(str(e))

            plan=find_plan(reg,c["plan_id"])
            print("\nPLAN_ID =",c["plan_id"])
            print("PLAN_OBJECT =",json.dumps(plan,ensure_ascii=False,indent=2,default=str))
            print("PLAN_NOTE =",c["plan_note"])
            if not plan:
                reasons.append("Không tìm thấy plan trong official registry")

            # Chốt hình dạng plan theo từng case.
            if c["op"]=="QD3805-OP-0210":
                if not plan or plan.get("commune_excel")!="Văn Hiến":
                    reasons.append("OP-0210 plan sai commune")
                members=(plan or {}).get("members") or []
                names=[str(x.get("school_name","")) for x in members if isinstance(x,dict)]
                if not any("Trần Phú" in x for x in names) or not any("Thượng Sơn" in x for x in names):
                    reasons.append("OP-0210 plan thiếu Trần Phú/Thượng Sơn")
                if not any("Văn Hiến" in x for x in names):
                    reasons.append("OP-0210 không thấy orphan Văn Hiến để khóa KHÔNG CHẠM")
                print("ORPHAN_POLICY = THCS Văn Hiến: KHÔNG CHẠM trong execution OP-0210.")
            else:
                if not plan or plan.get("commune_excel")!="Yên Hòa":
                    reasons.append("OP-0644 plan sai commune")
                members=(plan or {}).get("members") or []
                names=[str(x.get("school_name","")) for x in members if isinstance(x,dict)]
                if not any("Yên Thắng" in x for x in names) or not any("Yên Hòa" in x for x in names):
                    reasons.append("OP-0644 plan thiếu Yên Thắng/Yên Hòa")

            src_rows=staff_rows(conn,c["source_id"],BASE_YEAR_ID)
            tgt_rows=staff_rows(conn,c["target_id"],BASE_YEAR_ID)

            print("\nSOURCE_STAFF =",json.dumps(summary(src_rows),ensure_ascii=False))
            print("TARGET_STAFF =",json.dumps(summary(tgt_rows),ensure_ascii=False))
            print("EXPECTED_SOURCE =",json.dumps(c["expected_source"],ensure_ascii=False))
            print("EXPECTED_TARGET =",json.dumps(c["expected_target"],ensure_ascii=False))
            print("EXPECTED_FINAL =",json.dumps(c["expected_final"],ensure_ascii=False))

            if summary(src_rows)!=c["expected_source"]:
                reasons.append("SOURCE staff không đúng kỳ vọng")
            if summary(tgt_rows)!=c["expected_target"]:
                reasons.append("TARGET staff không đúng kỳ vọng")

            excluded=[]
            combined=[]
            for origin,rows in (("SOURCE",src_rows),("TARGET",tgt_rows)):
                for r in rows:
                    ok,why=eligible(r)
                    if ok:
                        rr=dict(r); rr["_origin"]=origin; combined.append(rr)
                    else:
                        excluded.append((origin,r.get("staff_member_id"),why))
            print("EXCLUDED =",excluded)
            if excluded:
                reasons.append("Có staff bị excluded")

            mids=[int(r["staff_member_id"]) for r in combined]
            dup=sorted(k for k,v in Counter(mids).items() if v>1)
            print("DUPLICATE_MEMBER_IDS =",dup)
            if dup:
                reasons.append("Có staff_member_id trùng source/target")

            existing=current_anywhere(conn,sorted(set(mids)))
            print("CURRENT_YEAR_EXISTING =",existing)
            if existing:
                reasons.append("Có staff năm 2026-2027 đã tồn tại")

            off,ops=exact_related_execution(conn,c)
            print("EXACT_OFFICIAL_EXECUTIONS =",off)
            print("EXACT_MERGER_OPERATIONS =",ops)
            if off:
                reasons.append("Đã có official execution liên quan chính xác source/target/plan")
            if ops:
                reasons.append("Đã có merger operation liên quan chính xác source/target")

            print("SOURCE_USERS =",school_users(conn,c["source_id"]))
            print("TARGET_USERS =",school_users(conn,c["target_id"]))

            payload={
                "op":c["op"],
                "plan_id":c["plan_id"],
                "source_id":c["source_id"],
                "target_id":c["target_id"],
                "source_summary":summary(src_rows),
                "target_summary":summary(tgt_rows),
                "expected_final":c["expected_final"],
                "duplicate_member_ids":dup,
                "current_existing":existing,
                "exact_official":off,
                "exact_operations":ops,
                "plan_note":c["plan_note"],
            }
            fingerprint=hashlib.sha256(
                json.dumps(payload,ensure_ascii=False,sort_keys=True,default=str).encode("utf-8")
            ).hexdigest()
            print("PREVIEW_FINGERPRINT =",fingerprint)

            if reasons:
                all_ready=False
                print("PREVIEW_READY = NO")
                for r in reasons:
                    print("REASON =",r)
            else:
                print("PREVIEW_READY = YES")
                print("MODEL = FULL_SOURCE_MERGE_TO_EXISTING_TARGET")
                print("SOURCE =",c["source_id"],"|",c["source_code"],"|",c["source_name"])
                print("TARGET =",c["target_id"],"|",c["target_code"],"|",c["target_name"])

        print("\n"+"="*150)
        print("PREVIEW_ALL_READY =", "YES" if all_ready else "NO")
        print("DATABASE = KHÔNG THAY ĐỔI")
        print("KHÔNG SÁP NHẬP")
        print("="*150)

    finally:
        conn.close()

if __name__=="__main__":
    main()
