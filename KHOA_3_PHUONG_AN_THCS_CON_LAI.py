# -*- coding: utf-8 -*-
from __future__ import annotations
import hashlib, json, sqlite3, sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(r"C:\PhoCap")
DB = ROOT / "data" / "phocap.db"
OFFICIAL_REGISTRY = ROOT / "school_merger_official_registry_v2.json"
LEVEL_LOCK = ROOT / "data" / "school_merger_registry" / "qd3805_level_lock.json"
RESOLUTION = ROOT / "data" / "school_merger_registry" / "qd3805_thcs_resolution.json"
EXPORT_DIR = ROOT / "exports"
OUT = EXPORT_DIR / "KHOA_3_PHUONG_AN_THCS_CON_LAI.txt"
EXPECTED_DB_SHA = "c7e51137abf425fababfc3b1857aa24d3056c7abbe20089f6c33f68d48c7b9b8"

CASES = [
    {"op":"QD3805-OP-0025","plan_id":"PA2026-F68F2B60851F","commune_excel":"Thành Vinh",
     "official_target":"THCS Quang Trung","names":["THCS Quang Trung","THCS Đội Cung"],
     "codes":["40412512","40431506","40412505","40427502"],"known_ids":[1431,1552,1426,1507]},
    {"op":"QD3805-OP-0172","plan_id":"PA2026-98173E42E1D0","commune_excel":"Bạch Hà",
     "official_target":"THCS Đại Sơn","names":["THCS Đại Sơn","THCS Lê Hồng Phong","THCS Trù Sơn"],
     "codes":["40427513","40427521","40427522","40431501"],"known_ids":[1463,1464,1465,1551]},
    {"op":"QD3805-OP-0203","plan_id":"PA2026-16141F34ACBC","commune_excel":"Thuần Trung",
     "official_target":"THCS Lê Hồng Phong","names":["THCS Kim Đồng","THCS Lê Hồng Phong"],
     "codes":["40427522","40431501"],"known_ids":[1465,1551,1712]},
]

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

def table_exists(conn, table):
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone() is not None

def columns(conn, table):
    return [r[1] for r in conn.execute('PRAGMA table_info("%s")' % table.replace('"','""')).fetchall()]

def find_plan(plan_id):
    data = load_json(OFFICIAL_REGISTRY)
    if isinstance(data, dict):
        for p in data.get("plans") or []:
            if isinstance(p, dict) and p.get("id") == plan_id:
                return p
    return None

def walk_find_op(obj, op, path="$", out=None):
    if out is None:
        out = []
    if isinstance(obj, dict):
        if str(obj.get("operation_id","")) == op:
            out.append((path,obj))
        for k,v in obj.items():
            if isinstance(v,(dict,list)):
                walk_find_op(v, op, path+"."+str(k), out)
    elif isinstance(obj, list):
        for i,v in enumerate(obj):
            if isinstance(v,(dict,list)):
                walk_find_op(v, op, "%s[%d]"%(path,i), out)
    return out

def commune_name(conn, cid):
    for table in ("communes","administrative_units","units"):
        if not table_exists(conn, table):
            continue
        c = columns(conn, table)
        if "id" not in c:
            continue
        name_col = next((x for x in ("name","commune_name","unit_name") if x in c), None)
        if not name_col:
            continue
        try:
            row = conn.execute('SELECT "%s" FROM "%s" WHERE id=?' % (name_col,table), (cid,)).fetchone()
            if row:
                return "%s:%s"%(table,row[0])
        except sqlite3.Error:
            pass
    return None

def school_by_id(conn, sid):
    return conn.execute("SELECT id,commune_id,code,name,is_active,created_at FROM schools WHERE id=?", (sid,)).fetchone()

def search_schools(conn, names, codes):
    found = {}
    if codes:
        q = ",".join("?" for _ in codes)
        for r in conn.execute("SELECT id,commune_id,code,name,is_active,created_at FROM schools WHERE code IN (%s)"%q, codes).fetchall():
            found[int(r[0])] = r
    for name in names:
        term = name.replace("THCS ","").replace("Trường ","").strip()
        if len(term) < 3:
            continue
        for r in conn.execute("SELECT id,commune_id,code,name,is_active,created_at FROM schools WHERE name LIKE ? ORDER BY id", ("%"+term+"%",)).fetchall():
            found[int(r[0])] = r
    return [found[k] for k in sorted(found)]

def staff_summary(conn, sid):
    if not table_exists(conn,"staff_year_records"):
        return []
    return conn.execute("SELECT school_year_id,position_group,COUNT(*) FROM staff_year_records WHERE school_id=? GROUP BY school_year_id,position_group ORDER BY school_year_id,position_group",(sid,)).fetchall()

def role3_users(conn, sid):
    if not table_exists(conn,"users"):
        return []
    return conn.execute("SELECT id,username,is_active FROM users WHERE school_id=? AND role_id=3 ORDER BY id",(sid,)).fetchall()

def class_counts(conn, sid):
    out=[]
    for table in ("classes","school_classes","class_configs"):
        if not table_exists(conn,table):
            continue
        c=columns(conn,table)
        if "school_id" not in c:
            continue
        try:
            if "school_year_id" in c:
                rows=conn.execute('SELECT school_year_id,COUNT(*) FROM "%s" WHERE school_id=? GROUP BY school_year_id ORDER BY school_year_id'%table,(sid,)).fetchall()
            else:
                rows=[("NO_YEAR",conn.execute('SELECT COUNT(*) FROM "%s" WHERE school_id=?'%table,(sid,)).fetchone()[0])]
            if rows:
                out.append((table,rows))
        except sqlite3.Error as e:
            out.append((table,[("ERROR",repr(e))]))
    return out

def footprint(conn, sid):
    hits=[]
    tables=[r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()]
    for table in tables:
        c=columns(conn,table)
        if "school_id" not in c:
            continue
        try:
            if "school_year_id" in c:
                rows=conn.execute('SELECT school_year_id,COUNT(*) FROM "%s" WHERE school_id=? GROUP BY school_year_id ORDER BY school_year_id'%table,(sid,)).fetchall()
                if rows:
                    hits.append((table,rows))
            else:
                n=conn.execute('SELECT COUNT(*) FROM "%s" WHERE school_id=?'%table,(sid,)).fetchone()[0]
                if n:
                    hits.append((table,[("NO_YEAR",n)]))
        except sqlite3.Error as e:
            hits.append((table,[("ERROR",repr(e))]))
    return hits

def related_exec(conn, sid):
    out=[]
    if not table_exists(conn,"school_merger_official_executions"):
        return out
    rows=conn.execute("SELECT id,plan_id,operation_id,target_school_id,source_school_ids_json,created_at FROM school_merger_official_executions ORDER BY id").fetchall()
    for r in rows:
        try:
            src={int(x) for x in json.loads(r[4] or "[]")}
        except Exception:
            src=set()
        if int(r[3])==sid or sid in src:
            out.append(r)
    return out

def main():
    EXPORT_DIR.mkdir(parents=True,exist_ok=True)
    print("="*150)
    print("KHÓA 3 PHƯƠNG ÁN THCS CÒN LẠI: OP-0025 / OP-0172 / OP-0203")
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
        integ=conn.execute("PRAGMA integrity_check").fetchone()[0]
        fk=conn.execute("PRAGMA foreign_key_check").fetchall()
        print("integrity =",integ)
        print("FK =",len(fk))
        if sha!=EXPECTED_DB_SHA:
            print("STOP = DB SHA đã khác nền sau OP-0160.")
            return 1
        if integ!="ok" or fk:
            print("STOP = Database health không đạt.")
            return 1

        level_lock=load_json(LEVEL_LOCK)
        resolution=load_json(RESOLUTION)

        for case in CASES:
            print("\n"+"#"*150)
            print("OPERATION =",case["op"])
            print("PLAN_ID =",case["plan_id"])
            print("COMMUNE_EXCEL =",case["commune_excel"])
            print("OFFICIAL_TARGET =",case["official_target"])
            print("#"*150)

            print("\nPLAN_OBJECT =")
            print(json.dumps(find_plan(case["plan_id"]),ensure_ascii=False,indent=2,default=str))

            print("\nLEVEL_LOCK_MATCHES =")
            for path,obj in walk_find_op(level_lock,case["op"]):
                print(path)
                print(json.dumps(obj,ensure_ascii=False,indent=2,default=str))

            print("\nRESOLUTION_MATCHES =")
            for path,obj in walk_find_op(resolution,case["op"]):
                print(path)
                print(json.dumps(obj,ensure_ascii=False,indent=2,default=str))

            candidates=search_schools(conn,case["names"],case["codes"])
            have={int(r[0]) for r in candidates}
            for sid in case["known_ids"]:
                if sid not in have:
                    r=school_by_id(conn,sid)
                    if r:
                        candidates.append(r)
            candidates.sort(key=lambda x:int(x[0]))

            print("\nSCHOOL_CANDIDATES =")
            for r in candidates:
                sid,cid,code,name,active,created_at=r
                print("\nSCHOOL id=%s | commune_id=%s | commune=%s | code=%s | name=%s | active=%s | created_at=%s"%(sid,cid,commune_name(conn,cid),code,name,active,created_at))
                print("  STAFF =",staff_summary(conn,sid))
                print("  CLASSES =",class_counts(conn,sid))
                print("  ROLE3_USERS =",role3_users(conn,sid))
                print("  RELATED_OFFICIAL =",related_exec(conn,sid))
                print("  FOOTPRINT =",footprint(conn,sid))

            print("\nEXACT_CODE_CANDIDATES =")
            for code in case["codes"]:
                rows=conn.execute("SELECT id,commune_id,code,name,is_active FROM schools WHERE code=? ORDER BY id",(code,)).fetchall()
                print(code,"=>",rows)

            print("\nSAME_NAME_CANDIDATES =")
            for name in case["names"]:
                term=name.replace("THCS ","").replace("Trường ","").strip()
                rows=conn.execute("SELECT id,commune_id,code,name,is_active FROM schools WHERE name LIKE ? ORDER BY id",("%"+term+"%",)).fetchall()
                print(name,"=>",rows)

            print("\nTECHNICAL_NOTE = KHÔNG TỰ CHỌN SOURCE/TARGET Ở BƯỚC NÀY.")

        print("\n"+"="*150)
        print("HOÀN TẤT KHẢO SÁT")
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
