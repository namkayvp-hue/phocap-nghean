# -*- coding: utf-8 -*-
from __future__ import annotations
import json, re, sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(r"C:\PhoCap")
REGISTRY_CANDIDATES = [
    ROOT / "school_merger_official_registry_v2.json",
    ROOT / "data" / "school_merger_registry" / "school_merger_official_registry_v2.json",
]
SEARCH_NAME = "THCS Mậu Đôn"
SEARCH_CODE = "40422510"
SOURCE_ID = 1578
TARGET_ID = 1577
TARGET_NAME = "PTDT Bán trú THCS Thạch Ngàn"
OPERATION_ID = "QD3805-OP-0108"
PLAN_RE = re.compile(r"^PA2026-[A-Fa-f0-9]{6,}$")

def find_registry():
    for p in REGISTRY_CANDIDATES:
        if p.exists():
            return p
    raise FileNotFoundError("Không tìm thấy school_merger_official_registry_v2.json")

def load_json(path):
    last = None
    for enc in ("utf-8-sig", "utf-8"):
        try:
            return json.loads(path.read_text(encoding=enc))
        except Exception as e:
            last = e
    raise RuntimeError(f"Không đọc được JSON: {last}")

def shallow_plans(d):
    out=[]
    if isinstance(d, dict):
        for k,v in d.items():
            if isinstance(v,str) and PLAN_RE.match(v):
                out.append((str(k),v))
    return out

def scalar_hit(d):
    if not isinstance(d,dict):
        return False
    for _,v in d.items():
        if isinstance(v,(dict,list)):
            continue
        s=str(v or "")
        if SEARCH_NAME.lower() in s.lower() or SEARCH_CODE in s:
            return True
    return False

def contains_term(obj, term):
    term=term.lower()
    if isinstance(obj,dict):
        return any(contains_term(v,term) for v in obj.values())
    if isinstance(obj,list):
        return any(contains_term(v,term) for v in obj)
    return term in str(obj or "").lower()

def walk(obj,path="$",ancestors=None,hits=None):
    ancestors=[] if ancestors is None else ancestors
    hits=[] if hits is None else hits
    if isinstance(obj,dict):
        if scalar_hit(obj):
            hits.append((path,obj,list(ancestors)))
        anc2=ancestors+[(path,obj)]
        for k,v in obj.items():
            if isinstance(v,(dict,list)):
                walk(v,f"{path}.{k}",anc2,hits)
    elif isinstance(obj,list):
        for i,v in enumerate(obj):
            if isinstance(v,(dict,list)):
                walk(v,f"{path}[{i}]",ancestors,hits)
    return hits

def main():
    print("="*150)
    print("XÁC ĐỊNH CHÍNH XÁC OFFICIAL PLAN_ID - THCS MẬU ĐÔN - CHỈ ĐỌC")
    print("="*150)

    registry=find_registry()
    print("REGISTRY =", registry)
    data=load_json(registry)
    hits=walk(data)

    print("\nDIRECT_HITS =", len(hits))
    candidates=[]

    for idx,(path,obj,ancs) in enumerate(hits,1):
        print("\n"+"#"*150)
        print(f"HIT #{idx} | PATH = {path}")
        print(json.dumps(obj,ensure_ascii=False,indent=2,default=str))

        local=shallow_plans(obj)
        if local:
            for k,p in local:
                candidates.append((p,path,k,"same_object"))
                print("PLAN_CANDIDATE =",p,"|",k,"| same_object")
        else:
            for apath,aobj in reversed(ancs):
                ps=shallow_plans(aobj)
                if ps:
                    print("ANCESTOR_WITH_PLAN =",apath)
                    for k,p in ps:
                        candidates.append((p,apath,k,"ancestor"))
                        print("PLAN_CANDIDATE =",p,"|",k,"| ancestor")
                    break

    branch=[]
    def scan(obj,path="$"):
        if isinstance(obj,dict):
            ps=shallow_plans(obj)
            if ps and (contains_term(obj,SEARCH_NAME) or contains_term(obj,SEARCH_CODE)):
                for k,p in ps:
                    branch.append((p,path,k))
            for k,v in obj.items():
                if isinstance(v,(dict,list)):
                    scan(v,f"{path}.{k}")
        elif isinstance(obj,list):
            for i,v in enumerate(obj):
                if isinstance(v,(dict,list)):
                    scan(v,f"{path}[{i}]")
    scan(data)

    print("\nBRANCH_CANDIDATES =",len(branch))
    for p,path,k in branch:
        print("BRANCH_PLAN =",p,"| PATH =",path,"| KEY =",k)
        candidates.append((p,path,k,"branch"))

    unique=sorted(set(x[0] for x in candidates))

    print("\n"+"="*150)
    print("KẾT LUẬN")
    print("="*150)
    print("SOURCE =",SOURCE_ID,"|",SEARCH_CODE,"|",SEARCH_NAME)
    print("TARGET =",TARGET_ID,"|",TARGET_NAME)
    print("OPERATION =",OPERATION_ID)
    print("UNIQUE_PLAN_CANDIDATES =",unique)

    if len(unique)==1:
        print("PLAN_RESOLUTION_READY = YES")
        print("OFFICIAL_PLAN_ID =",unique[0])
    else:
        print("PLAN_RESOLUTION_READY = NO")
        print("LÝ DO =", "KHÔNG TÌM THẤY PLAN_ID" if not unique else "CÓ NHIỀU PLAN_ID ỨNG VIÊN")

    print("KHÔNG GHI DATABASE.")
    print("KHÔNG SÁP NHẬP.")

if __name__=="__main__":
    try:
        main()
    except Exception as e:
        print("\n"+"!"*150)
        print("LỖI KHẢO SÁT:",repr(e))
        print("KHÔNG GHI DATABASE. KHÔNG SÁP NHẬP.")
        print("!"*150)
        sys.exit(1)
