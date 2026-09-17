# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(r"C:\PhoCap")
DB = ROOT / "data" / "phocap.db"
OPS = ["QD3805-OP-0210", "QD3805-OP-0644"]

REGISTRY_FILES = [
    ROOT / "data" / "school_merger_registry" / "qd3805_level_lock.json",
    ROOT / "data" / "school_merger_registry" / "qd3805_thcs_resolution.json",
    ROOT / "school_merger_level_registry_qd3805_enriched_th.json",
    ROOT / "school_merger_official_registry_v2.json",
]

TEXT_HINT_FILES = [
    ROOT / "dry_run_RAM_3_THCS_0108_0210_0644.py",
    ROOT / "khao_sat_6_THCS_mapping_alias.py",
    ROOT / "tach_19_BLOCK_THCS_khoi_batch_thuan.py",
    ROOT / "tach_19_BLOCK_THCS_khoi_batch_thuan_v2.py",
    ROOT / "tach_19_BLOCK_THCS_khoi_batch_thuan_v3.py",
    ROOT / "tach_19_BLOCK_THCS_khoi_batch_thuan_v4.py",
]

CODE_RE = re.compile(r"\b\d{8}\b")
PLAN_RE = re.compile(r"PA2026-[A-Fa-f0-9]{6,}")

def load_json(path: Path):
    for enc in ("utf-8-sig", "utf-8"):
        try:
            return json.loads(path.read_text(encoding=enc))
        except Exception:
            pass
    return None

def walk_find_operation(obj, op, path="$", out=None):
    if out is None:
        out = []
    if isinstance(obj, dict):
        if str(obj.get("operation_id", "")) == op:
            out.append((path, obj))
        for k, v in obj.items():
            if isinstance(v, (dict, list)):
                walk_find_operation(v, op, f"{path}.{k}", out)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            if isinstance(v, (dict, list)):
                walk_find_operation(v, op, f"{path}[{i}]", out)
    return out

def collect_codes(obj):
    text = json.dumps(obj, ensure_ascii=False, default=str)
    return sorted(set(CODE_RE.findall(text)))

def collect_names(obj):
    names = set()
    keys = {"name", "school_name", "display_title", "target_name", "source_name"}
    def walk(x):
        if isinstance(x, dict):
            for k, v in x.items():
                if k in keys and isinstance(v, str):
                    names.add(v)
                walk(v)
        elif isinstance(x, list):
            for y in x:
                walk(y)
    walk(obj)
    return sorted(names)

def plan_candidates_from_official_registry(codes, names):
    path = ROOT / "school_merger_official_registry_v2.json"
    data = load_json(path) if path.exists() else None
    if not isinstance(data, dict):
        return []
    plans = data.get("plans")
    if not isinstance(plans, list):
        return []

    out = []
    for plan in plans:
        text = json.dumps(plan, ensure_ascii=False, default=str).lower()
        score = 0
        matched = []
        for c in codes:
            if c in text:
                score += 3
                matched.append(c)
        for n in names:
            n2 = n.lower().strip()
            if len(n2) >= 5 and n2 in text:
                score += 1
                matched.append(n)
        if score:
            pid = plan.get("id")
            if isinstance(pid, str) and PLAN_RE.fullmatch(pid):
                out.append((score, pid, sorted(set(matched)), plan))
    out.sort(key=lambda x: (-x[0], x[1]))
    return out[:10]

def read_text(path: Path):
    try:
        return path.read_text(encoding="utf-8-sig")
    except Exception:
        try:
            return path.read_text(encoding="utf-8")
        except Exception:
            return ""

def context_for(text, term, radius=25):
    lines = text.splitlines()
    out = []
    for i, line in enumerate(lines):
        if term.lower() in line.lower():
            a=max(0,i-radius)
            b=min(len(lines),i+radius+1)
            out.append((i+1, lines[a:b]))
    return out

def db_school_by_codes(conn, codes):
    if not codes:
        return []
    q = ",".join("?" for _ in codes)
    cur = conn.execute(
        f"SELECT * FROM schools WHERE code IN ({q}) ORDER BY id",
        codes
    )
    cols=[d[0] for d in cur.description]
    return [dict(zip(cols,r)) for r in cur.fetchall()]

def db_school_by_name_terms(conn, names):
    found = {}
    for name in names:
        term = name
        for prefix in ("Trường ", "PTDT Bán trú ", "PTDTBT ", "THCS "):
            if term.startswith(prefix):
                term = term[len(prefix):]
        term = term.strip()
        if len(term) < 3:
            continue
        cur = conn.execute(
            "SELECT * FROM schools WHERE name LIKE ? ORDER BY id",
            (f"%{term}%",)
        )
        cols=[d[0] for d in cur.description]
        for r in cur.fetchall():
            d=dict(zip(cols,r))
            found[d["id"]]=d
    return [found[k] for k in sorted(found)]

def staff_summary(conn, sid):
    rows = conn.execute(
        """
        SELECT school_year_id, position_group, COUNT(*)
        FROM staff_year_records
        WHERE school_id=?
        GROUP BY school_year_id, position_group
        ORDER BY school_year_id, position_group
        """,
        (sid,)
    ).fetchall()
    return rows

def users(conn, sid):
    return conn.execute(
        """
        SELECT id, username, full_name, role_id, school_id, is_active
        FROM users
        WHERE school_id=?
        ORDER BY id
        """,
        (sid,)
    ).fetchall()

def related_logs(conn, sids):
    if not sids:
        return [], []
    official = conn.execute(
        """
        SELECT id, plan_id, operation_id, school_year_id, target_school_id,
               source_school_ids_json, created_at
        FROM school_merger_official_executions
        ORDER BY id
        """
    ).fetchall()
    ops = conn.execute(
        """
        SELECT id, school_year_id, target_school_id, source_school_ids_json, created_at
        FROM school_merger_operations
        ORDER BY id
        """
    ).fetchall()

    def hit(row, target_index, src_index):
        target = int(row[target_index])
        src = str(row[src_index] or "")
        return target in sids or any(str(s) in src for s in sids)

    return (
        [r for r in official if hit(r,4,5)],
        [r for r in ops if hit(r,2,3)],
    )

def main():
    print("="*150)
    print("KHẢO SÁT 2 PHƯƠNG ÁN THCS CÒN LẠI - QD3805-OP-0210 / QD3805-OP-0644 - CHỈ ĐỌC")
    print("="*150)

    if not DB.exists():
        print("DỪNG: không tìm thấy", DB)
        sys.exit(2)

    conn = sqlite3.connect(DB.resolve().as_uri()+"?mode=ro", uri=True, timeout=30)
    conn.execute("PRAGMA query_only=ON")

    try:
        print("\nDATABASE HEALTH")
        print("integrity =", conn.execute("PRAGMA integrity_check").fetchone()[0])
        print("FK =", len(conn.execute("PRAGMA foreign_key_check").fetchall()))

        for op in OPS:
            print("\n" + "#"*150)
            print("OPERATION =", op)
            print("#"*150)

            all_codes=set()
            all_names=set()

            print("\n1. REGISTRY MATCHES")
            for path in REGISTRY_FILES:
                if not path.exists():
                    continue
                data=load_json(path)
                if data is None:
                    continue
                hits=walk_find_operation(data,op)
                if hits:
                    print("\nFILE =", path)
                    for j,(jpath,obj) in enumerate(hits,1):
                        print(f"\nMATCH #{j} | JSON_PATH = {jpath}")
                        print(json.dumps(obj,ensure_ascii=False,indent=2,default=str))
                        all_codes.update(collect_codes(obj))
                        all_names.update(collect_names(obj))

            print("\n2. TEXT CONTEXT")
            for path in TEXT_HINT_FILES:
                if not path.exists():
                    continue
                text=read_text(path)
                contexts=context_for(text,op,35)
                if contexts:
                    print("\nFILE =", path)
                    for line_no, block in contexts[:5]:
                        print("MATCH_LINE =",line_no)
                        for line in block:
                            print(line[:1400])
                        all_codes.update(CODE_RE.findall("\n".join(block)))
                        # collect quoted school-ish strings
                        for m in re.findall(r'["\']([^"\']*(?:THCS|Trung học cơ sở)[^"\']*)["\']', "\n".join(block), flags=re.I):
                            all_names.add(m)

            print("\n3. TOKENS PHÁT HIỆN")
            print("CODES =", sorted(all_codes))
            print("NAMES =", sorted(all_names))

            school_rows = db_school_by_codes(conn, sorted(all_codes))
            # add by name if codes incomplete
            extra = db_school_by_name_terms(conn, sorted(all_names))
            by_id={r["id"]:r for r in school_rows+extra}
            school_rows=[by_id[k] for k in sorted(by_id)]

            print("\n4. SCHOOLS RESOLVED")
            if not school_rows:
                print("KHÔNG RESOLVE ĐƯỢC SCHOOL.")
            for s in school_rows:
                print(json.dumps(s,ensure_ascii=False,default=str))
                print("  STAFF =", staff_summary(conn,s["id"]))
                print("  USERS =", users(conn,s["id"]))

            sids=set(int(s["id"]) for s in school_rows)
            official,operations=related_logs(conn,sids)

            print("\n5. EXISTING EXECUTION LOGS")
            print("OFFICIAL =", official)
            print("OPERATIONS =", operations)

            print("\n6. OFFICIAL PLAN CANDIDATES")
            candidates=plan_candidates_from_official_registry(sorted(all_codes), sorted(all_names))
            if not candidates:
                print("KHÔNG TÌM THẤY PLAN CANDIDATE.")
            else:
                for score,pid,matched,plan in candidates:
                    print("\nSCORE =",score)
                    print("PLAN_ID =",pid)
                    print("MATCHED =",matched)
                    print(json.dumps(plan,ensure_ascii=False,indent=2,default=str))

            print("\n7. KẾT LUẬN TẠM THỜI")
            if official:
                print("TRẠNG THÁI = CÓ OFFICIAL EXECUTION LIÊN QUAN - KHÔNG ĐƯỢC CHẠY LẠI.")
            else:
                print("TRẠNG THÁI = CHƯA THẤY OFFICIAL EXECUTION LIÊN QUAN.")
            print("CHỈ KHẢO SÁT. KHÔNG GHI DATABASE.")

        print("\n"+"="*150)
        print("KHẢO SÁT HOÀN TẤT")
        print("KHÔNG GHI DATABASE. KHÔNG SÁP NHẬP.")
        print("="*150)
    finally:
        conn.close()

if __name__=="__main__":
    main()
