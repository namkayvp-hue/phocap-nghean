# -*- coding: utf-8 -*-
"""
XÁC ĐỊNH CHÍNH XÁC PLAN_ID CỦA THCS MẬU ĐÔN - CHỈ ĐỌC

Nguồn chính:
    C:\PhoCap\school_merger_official_registry_v2.json

Mục tiêu:
- Tìm các object JSON chứa "THCS Mậu Đôn".
- Đi ngược cây JSON để tìm ancestor gần nhất có plan_id dạng PA2026-...
- In đầy đủ object ứng viên và đường dẫn JSON.
- Chỉ PASS nếu có DUY NHẤT một plan_id ứng viên phù hợp.
- KHÔNG ghi DB.
- KHÔNG sửa file registry.
"""

from __future__ import annotations

import json
import re
import sys
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

def find_registry() -> Path:
    for p in REGISTRY_CANDIDATES:
        if p.exists():
            return p
    print("DỪNG: Không tìm thấy school_merger_official_registry_v2.json")
    sys.exit(2)

def load_json(path: Path):
    for enc in ("utf-8-sig", "utf-8"):
        try:
            return json.loads(path.read_text(encoding=enc))
        except Exception:
            pass
    print("DỪNG: Không đọc được JSON registry.")
    sys.exit(3)

def scalar_text(v):
    if v is None:
        return ""
    if isinstance(v, (str, int, float, bool)):
        return str(v)
    return ""

def object_contains_term(obj, term: str) -> bool:
    term_l = term.lower()
    if isinstance(obj, dict):
        for k, v in obj.items():
            if term_l in str(k).lower():
                return True
            if isinstance(v, (dict, list)):
                if object_contains_term(v, term):
                    return True
            else:
                if term_l in scalar_text(v).lower():
                    return True
    elif isinstance(obj, list):
        for x in obj:
            if object_contains_term(x, term):
                return True
    else:
        return term_l in scalar_text(obj).lower()
    return False

def collect_plan_values_shallow(d: dict):
    plans = []
    for k, v in d.items():
        key = str(k).lower()
        if "plan" in key and isinstance(v, str) and PLAN_RE.match(v):
            plans.append((k, v))
    return plans

def collect_plan_values_recursive(obj):
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, str) and PLAN_RE.match(v):
                out.append((str(k), v))
            else:
                out.extend(collect_plan_values_recursive(v))
    elif isinstance(obj, list):
        for x in obj:
            out.extend(collect_plan_values_recursive(x))
    return out

def walk(obj, path="$", ancestors=None, hits=None):
    if ancestors is None:
        ancestors = []
    if hits is None:
        hits = []

    if isinstance(obj, dict):
        # Direct object contains exact Mậu Đôn term somewhere below.
        direct_scalar_hit = False
        for k, v in obj.items():
            if not isinstance(v, (dict, list)):
                txt = scalar_text(v)
                if SEARCH_NAME.lower() in txt.lower() or SEARCH_CODE in txt:
                    direct_scalar_hit = True

        if direct_scalar_hit:
            hits.append({
                "path": path,
                "object": obj,
                "ancestors": list(ancestors),
            })

        next_anc = ancestors + [(path, obj)]
        for k, v in obj.items():
            if isinstance(v, (dict, list)):
                walk(v, f"{path}.{k}", next_anc, hits)

    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            if isinstance(v, (dict, list)):
                walk(v, f"{path}[{i}]", ancestors, hits)

    return hits

def value_mentions_ids(obj):
    txt = json.dumps(obj, ensure_ascii=False, default=str)
    return (
        str(SOURCE_ID) in txt
        or SEARCH_CODE in txt
        or SEARCH_NAME.lower() in txt.lower()
    )

def main():
    print("=" * 150)
    print("XÁC ĐỊNH CHÍNH XÁC OFFICIAL PLAN_ID - THCS MẬU ĐÔN - CHỈ ĐỌC")
    print("=" * 150)

    registry = find_registry()
    print("REGISTRY =", registry)

    data = load_json(registry)
    hits = walk(data)

    print("\n1. OBJECT TRỰC TIẾP CHỨA MẬU ĐÔN / MÃ TRƯỜNG")
    print("-" * 150)
    print("DIRECT_HITS =", len(hits))

    candidate_plans = []

    for idx, hit in enumerate(hits, 1):
        print("\n" + "#" * 150)
        print(f"HIT #{idx}")
        print("PATH =", hit["path"])
        print("#" * 150)
        print(json.dumps(hit["object"], ensure_ascii=False, indent=2, default=str))

        # Ưu tiên plan trong chính object, sau đó ancestor gần nhất.
        local = collect_plan_values_shallow(hit["object"])
        if local:
            for key, plan in local:
                candidate_plans.append({
                    "plan_id": plan,
                    "source": "same_object",
                    "path": hit["path"],
                    "key": key,
                })
                print("PLAN CÙNG OBJECT =", key, plan)
        else:
            for anc_path, anc_obj in reversed(hit["ancestors"]):
                plans = collect_plan_values_shallow(anc_obj)
                if plans:
                    print("ANCESTOR GẦN NHẤT CÓ PLAN =", anc_path)
                    for key, plan in plans:
                        candidate_plans.append({
                            "plan_id": plan,
                            "source": "ancestor",
                            "path": anc_path,
                            "key": key,
                        })
                        print("  ", key, "=", plan)
                    # In ancestor để con người kiểm tra.
                    print("ANCESTOR OBJECT:")
                    print(json.dumps(anc_obj, ensure_ascii=False, indent=2, default=str))
                    break

    print("\n2. TÌM CÁC OBJECT CÓ PLAN_ID VÀ CÓ MẬU ĐÔN TRONG CÙNG NHÁNH")
    print("-" * 150)

    branch_candidates = []

    def scan_branch(obj, path="$"):
        if isinstance(obj, dict):
            shallow_plans = collect_plan_values_shallow(obj)
            if shallow_plans and (
                object_contains_term(obj, SEARCH_NAME)
                or object_contains_term(obj, SEARCH_CODE)
            ):
                for k, plan in shallow_plans:
                    branch_candidates.append({
                        "plan_id": plan,
                        "path": path,
                        "key": k,
                        "object": obj,
                    })
            for k, v in obj.items():
                if isinstance(v, (dict, list)):
                    scan_branch(v, f"{path}.{k}")
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                if isinstance(v, (dict, list)):
                    scan_branch(v, f"{path}[{i}]")

    scan_branch(data)

    print("BRANCH_CANDIDATES =", len(branch_candidates))
    for i, c in enumerate(branch_candidates, 1):
        print("\n" + "-" * 150)
        print(f"BRANCH #{i}")
        print("PATH =", c["path"])
        print("PLAN =", c["key"], c["plan_id"])
        print(json.dumps(c["object"], ensure_ascii=False, indent=2, default=str))

    all_plans = []
    for c in candidate_plans:
        all_plans.append(c["plan_id"])
    for c in branch_candidates:
        all_plans.append(c["plan_id"])

    unique_plans = sorted(set(all_plans))

    print("\n3. KẾT LUẬN")
    print("-" * 150)
    print("SOURCE =", SOURCE_ID, "|", SEARCH_CODE, "|", SEARCH_NAME)
    print("TARGET =", TARGET_ID, "|", TARGET_NAME)
    print("OPERATION =", OPERATION_ID)
    print("UNIQUE_PLAN_CANDIDATES =", unique_plans)

    if len(unique_plans) == 1:
        print("PLAN_RESOLUTION_READY = YES")
        print("OFFICIAL_PLAN_ID =", unique_plans[0])
        print("BƯỚC SAU = CÓ THỂ TẠO COMMIT PACKAGE, NHƯNG CHƯA GHI DB Ở BƯỚC NÀY.")
    else:
        print("PLAN_RESOLUTION_READY = NO")
        if len(unique_plans) == 0:
            print("LÝ DO = KHÔNG TÌM THẤY PLAN_ID GẮN TRỰC TIẾP VỚI NHÁNH MẬU ĐÔN.")
        else:
            print("LÝ DO = CÓ NHIỀU PLAN_ID ỨNG VIÊN, CẦN ĐỐI CHIẾU THÊM.")

    print("\nKHÔNG SỬA REGISTRY.")
    print("KHÔNG GHI DATABASE.")
    print("KHÔNG SÁP NHẬP.")

if __name__ == "__main__":
    main()
