# -*- coding: utf-8 -*-
from __future__ import annotations
import json, sqlite3, sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(r"C:\PhoCap")
DB = ROOT / "data" / "phocap.db"
RESOLUTION = ROOT / "data" / "school_merger_registry" / "qd3805_thcs_resolution.json"
OFFICIAL_REGISTRY = ROOT / "school_merger_official_registry_v2.json"

KEEP_KEYWORDS = [
    "tiếp nhận điểm",
    "tiếp nhận thêm lớp",
    "tiếp nhận lớp",
    "nhận thêm lớp",
    "điểm trường",
    "tiếp nhận điểm trường",
]

def load_json(path):
    if not path.exists():
        return None
    for enc in ("utf-8-sig","utf-8"):
        try:
            return json.loads(path.read_text(encoding=enc))
        except Exception:
            pass
    return None

def plan_lookup():
    data = load_json(OFFICIAL_REGISTRY)
    out = {}
    if isinstance(data, dict) and isinstance(data.get("plans"), list):
        for p in data["plans"]:
            if isinstance(p, dict) and isinstance(p.get("id"), str):
                out[p["id"]] = p
    return out

def classify_keep(item):
    text = " ".join([
        str(item.get("display_title","")),
        str(item.get("relation_type","")),
        str(item.get("status","")),
        str(item.get("reason","")),
    ]).lower()
    return any(k in text for k in KEEP_KEYWORDS)

def completed_business_ops(conn):
    """
    Official execution table stores plan_id, not business op code.
    Map completed plan_id back to registry plans where possible.
    """
    rows = conn.execute(
        "SELECT id,plan_id,operation_id,target_school_id,source_school_ids_json,created_at "
        "FROM school_merger_official_executions ORDER BY id"
    ).fetchall()
    return rows

def main():
    print("="*150)
    print("RÀ SOÁT THCS CÒN LẠI SAU CÁC COMMIT - ÁP DỤNG QUY TẮC 'TIẾP NHẬN THÊM LỚP/ĐIỂM = GIỮ NGUYÊN'")
    print("CHỈ ĐỌC - KHÔNG GHI DATABASE - KHÔNG SỬA REGISTRY")
    print("="*150)

    if not DB.exists():
        print("DỪNG: không tìm thấy DB", DB)
        sys.exit(2)

    conn = sqlite3.connect(DB.resolve().as_uri()+"?mode=ro", uri=True, timeout=30)
    conn.execute("PRAGMA query_only=ON")
    try:
        print("\nDATABASE HEALTH")
        print("integrity =", conn.execute("PRAGMA integrity_check").fetchone()[0])
        print("FK =", len(conn.execute("PRAGMA foreign_key_check").fetchall()))

        print("\nOFFICIAL EXECUTIONS HIỆN CÓ")
        for r in completed_business_ops(conn):
            print(r)

        resolution = load_json(RESOLUTION)
        if not isinstance(resolution, dict):
            print("\nDỪNG: không đọc được qd3805_thcs_resolution.json")
            return

        specials = resolution.get("special_same_level") or []
        if not isinstance(specials, list):
            specials = []

        print("\nTỔNG SPECIAL_SAME_LEVEL =", len(specials))

        keep = []
        remaining = []
        for item in specials:
            if not isinstance(item, dict):
                continue
            if classify_keep(item):
                keep.append(item)
            else:
                remaining.append(item)

        print("\n" + "="*150)
        print("A. ĐỀ XUẤT QUY VỀ GIỮ NGUYÊN - KHÔNG CHẠY THUẬT TOÁN SÁP NHẬP")
        print("="*150)
        if not keep:
            print("KHÔNG CÓ")
        for x in keep:
            print("\nOPERATION =", x.get("operation_id"))
            print("DISPLAY_TITLE =", x.get("display_title"))
            print("RELATION_TYPE =", x.get("relation_type"))
            print("STATUS =", x.get("status"))
            print("REASON =", x.get("reason"))
            print("PROPOSED_ACTION = KEEP / GIỮ NGUYÊN")
            print("DB_ACTION = NONE")
            print("NOTE = Sau này trường tự thêm lớp, giáo viên, học sinh theo thực tế.")

        print("\n" + "="*150)
        print("B. SPECIAL CÒN LẠI KHÔNG THUỘC 'TIẾP NHẬN THÊM LỚP/ĐIỂM'")
        print("="*150)
        if not remaining:
            print("KHÔNG CÒN")
        for x in remaining:
            print("\nOPERATION =", x.get("operation_id"))
            print("DISPLAY_TITLE =", x.get("display_title"))
            print("RELATION_TYPE =", x.get("relation_type"))
            print("STATUS =", x.get("status"))
            print("REASON =", x.get("reason"))

        print("\n" + "="*150)
        print("KẾT LUẬN")
        print("="*150)
        print("KEEP_COUNT =", len(keep))
        print("OTHER_SPECIAL_COUNT =", len(remaining))
        print("DATABASE = KHÔNG THAY ĐỔI")
        print("REGISTRY = KHÔNG THAY ĐỔI")
        print("="*150)
    finally:
        conn.close()

if __name__ == "__main__":
    main()
