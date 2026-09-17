# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
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
EXPORT_DIR = ROOT / "exports"
OUT = EXPORT_DIR / "KHAO_SAT_THCS_5_PHUONG_AN_GOP_CON_LAI.txt"

OPS = [
    "QD3805-OP-0025",
    "QD3805-OP-0126",
    "QD3805-OP-0160",
    "QD3805-OP-0172",
    "QD3805-OP-0203",
]

REGISTRY_FILES = [
    ROOT / "data" / "school_merger_registry" / "qd3805_level_lock.json",
    ROOT / "data" / "school_merger_registry" / "qd3805_thcs_resolution.json",
    ROOT / "school_merger_level_registry_qd3805_enriched_th.json",
    ROOT / "school_merger_official_registry_v2.json",
]

# Một số file cũ thường chứa mapping khóa tay / dry-run.
TEXT_FILES = [
    ROOT / "khao_sat_6_THCS_mapping_alias.py",
    ROOT / "dry_run_RAM_3_THCS_0108_0210_0644.py",
    ROOT / "tach_19_BLOCK_THCS_khoi_batch_thuan.py",
    ROOT / "tach_19_BLOCK_THCS_khoi_batch_thuan_v2.py",
    ROOT / "tach_19_BLOCK_THCS_khoi_batch_thuan_v3.py",
    ROOT / "tach_19_BLOCK_THCS_khoi_batch_thuan_v4.py",
]

PLAN_RE = re.compile(r"PA2026-[A-F0-9]+", re.I)
CODE_RE = re.compile(r"\b404\d{5}\b")

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()

def load_json(path: Path):
    if not path.exists():
        return None
    for enc in ("utf-8-sig", "utf-8"):
        try:
            return json.loads(path.read_text(encoding=enc))
        except Exception:
            pass
    return None

def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    for enc in ("utf-8-sig", "utf-8"):
        try:
            return path.read_text(encoding=enc)
        except Exception:
            pass
    return ""

def walk_find_op(obj, op, path="$", out=None):
    if out is None:
        out = []
    if isinstance(obj, dict):
        if str(obj.get("operation_id", "")) == op:
            out.append((path, obj))
        for k, v in obj.items():
            if isinstance(v, (dict, list)):
                walk_find_op(v, op, f"{path}.{k}", out)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            if isinstance(v, (dict, list)):
                walk_find_op(v, op, f"{path}[{i}]", out)
    return out

def context_blocks(text: str, term: str, radius=28):
    lines = text.splitlines()
    out = []
    for i, line in enumerate(lines):
        if term.lower() in line.lower():
            a = max(0, i-radius)
            b = min(len(lines), i+radius+1)
            out.append((i+1, lines[a:b]))
    return out

def collect_tokens(obj_or_text):
    if not isinstance(obj_or_text, str):
        text = json.dumps(obj_or_text, ensure_ascii=False, default=str)
    else:
        text = obj_or_text
    codes = sorted(set(CODE_RE.findall(text)))
    names = set()

    # Quoted / JSON name fields.
    for m in re.findall(r'(?:"(?:school_name|name|display_title|target_text|official_plan|source_name|target_name)"\s*:\s*"([^"]+)")', text):
        if "THCS" in m.upper() or "TRUNG HỌC CƠ SỞ" in m.upper():
            names.add(m.strip())

    for m in re.findall(r'["\']([^"\']*(?:THCS|Trung học cơ sở)[^"\']*)["\']', text, flags=re.I):
        if 3 <= len(m.strip()) <= 180:
            names.add(m.strip())

    plans = sorted(set(PLAN_RE.findall(text)))
    return codes, sorted(names), plans

def official_registry_plans():
    path = ROOT / "school_merger_official_registry_v2.json"
    data = load_json(path)
    if isinstance(data, dict) and isinstance(data.get("plans"), list):
        return data["plans"]
    return []

def plan_candidates(tokens_codes, tokens_names, op_context_terms):
    out = []
    for plan in official_registry_plans():
        text = json.dumps(plan, ensure_ascii=False, default=str)
        low = text.lower()
        score = 0
        matched = []

        for c in tokens_codes:
            if c in text:
                score += 5
                matched.append(c)

        for name in tokens_names:
            n = name.lower().strip()
            if len(n) >= 5 and n in low:
                score += 2
                matched.append(name)

        # Exact operation-local names get a little boost.
        for term in op_context_terms:
            t = term.lower().strip()
            if len(t) >= 5 and t in low:
                score += 3
                matched.append(term)

        if score:
            out.append((score, plan.get("id"), sorted(set(matched)), plan))

    out.sort(key=lambda x: (-x[0], str(x[1])))
    return out[:8]

def db_schools_by_codes(conn, codes):
    if not codes:
        return []
    q = ",".join("?" for _ in codes)
    cur = conn.execute(
        f"SELECT id,commune_id,code,name,is_active,created_at FROM schools WHERE code IN ({q}) ORDER BY id",
        codes,
    )
    return cur.fetchall()

def normalize_name_term(name):
    s = name
    for prefix in (
        "Trường ",
        "PTDTBT ",
        "PTDT Bán trú ",
        "PT DTBT ",
        "THCS ",
    ):
        if s.lower().startswith(prefix.lower()):
            s = s[len(prefix):]
    # Bỏ phần mô tả sau dấu +, ->, –, (
    for sep in (" + ", " -> ", " – ", " - ", " ("):
        if sep in s:
            s = s.split(sep)[0]
    return s.strip()

def db_schools_by_names(conn, names):
    found = {}
    for name in names:
        term = normalize_name_term(name)
        if len(term) < 3:
            continue
        cur = conn.execute(
            """
            SELECT id,commune_id,code,name,is_active,created_at
            FROM schools
            WHERE name LIKE ?
            ORDER BY id
            """,
            (f"%{term}%",),
        )
        for row in cur.fetchall():
            found[int(row[0])] = row
    return [found[k] for k in sorted(found)]

def staff_summary(conn, sid):
    rows = conn.execute(
        """
        SELECT school_year_id,position_group,COUNT(*)
        FROM staff_year_records
        WHERE school_id=?
        GROUP BY school_year_id,position_group
        ORDER BY school_year_id,position_group
        """,
        (sid,),
    ).fetchall()
    return rows

def school_user(conn, sid):
    return conn.execute(
        """
        SELECT id,username,role_id,is_active
        FROM users
        WHERE school_id=? AND role_id=3
        ORDER BY id
        """,
        (sid,),
    ).fetchall()

def related_execution(conn, sid):
    official = []
    for r in conn.execute(
        """
        SELECT id,plan_id,operation_id,target_school_id,source_school_ids_json,created_at
        FROM school_merger_official_executions
        ORDER BY id
        """
    ).fetchall():
        try:
            src = {int(x) for x in json.loads(r[4] or "[]")}
        except Exception:
            src = set()
        if int(r[3]) == sid or sid in src:
            official.append(r)
    return official

def main():
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)

    if not DB.exists():
        print("DỪNG: không tìm thấy", DB)
        return 2

    conn = sqlite3.connect(DB.resolve().as_uri() + "?mode=ro", uri=True, timeout=30)
    conn.execute("PRAGMA query_only=ON")

    try:
        print("=" * 150)
        print("KHẢO SÁT 5 PHƯƠNG ÁN THCS CÒN CÓ PHẦN GỘP TOÀN TRƯỜNG")
        print("0025 / 0126 / 0160 / 0172 / 0203")
        print("CHỈ ĐỌC - KHÔNG GHI DATABASE")
        print("=" * 150)
        print("DB_SHA =", sha256_file(DB))
        print("integrity =", conn.execute("PRAGMA integrity_check").fetchone()[0])
        print("FK =", len(conn.execute("PRAGMA foreign_key_check").fetchall()))

        for op in OPS:
            print("\n" + "#" * 150)
            print("OPERATION =", op)
            print("#" * 150)

            all_codes = set()
            all_names = set()
            all_plans = set()
            op_terms = set()

            print("\n1. REGISTRY MATCHES")
            for path in REGISTRY_FILES:
                data = load_json(path)
                if data is None:
                    continue
                hits = walk_find_op(data, op)
                if not hits:
                    continue
                print("\nFILE =", path)
                for jpath, obj in hits:
                    print("JSON_PATH =", jpath)
                    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))
                    codes, names, plans = collect_tokens(obj)
                    all_codes.update(codes)
                    all_names.update(names)
                    all_plans.update(plans)
                    for key in ("display_title","official_plan","target_text","reason"):
                        v = obj.get(key) if isinstance(obj, dict) else None
                        if isinstance(v, str):
                            op_terms.add(v)

            print("\n2. LOCAL CODE CONTEXT")
            for path in TEXT_FILES:
                text = read_text(path)
                blocks = context_blocks(text, op)
                if not blocks:
                    continue
                print("\nFILE =", path)
                for line_no, block in blocks[:4]:
                    print("MATCH_LINE =", line_no)
                    block_text = "\n".join(block)
                    print(block_text)
                    codes, names, plans = collect_tokens(block_text)
                    all_codes.update(codes)
                    all_names.update(names)
                    all_plans.update(plans)

            print("\n3. TOKENS RIÊNG CỦA OPERATION")
            print("CODES =", sorted(all_codes))
            print("NAMES =", sorted(all_names))
            print("PLAN_TOKENS =", sorted(all_plans))

            rows = {}
            for r in db_schools_by_codes(conn, sorted(all_codes)):
                rows[int(r[0])] = r
            for r in db_schools_by_names(conn, sorted(all_names)):
                rows[int(r[0])] = r

            print("\n4. SCHOOL CANDIDATES")
            for sid in sorted(rows):
                r = rows[sid]
                print(
                    f"SCHOOL = id={r[0]} | commune_id={r[1]} | code={r[2]} | "
                    f"name={r[3]} | active={r[4]}"
                )
                print("  STAFF =", staff_summary(conn, sid))
                print("  SCHOOL_USER =", school_user(conn, sid))
                print("  RELATED_OFFICIAL =", related_execution(conn, sid))

            print("\n5. OFFICIAL PLAN CANDIDATES")
            candidates = plan_candidates(sorted(all_codes), sorted(all_names), sorted(op_terms))
            if not candidates:
                print("KHÔNG TÌM THẤY")
            for score, pid, matched, plan in candidates:
                print("\nSCORE =", score)
                print("PLAN_ID =", pid)
                print("MATCHED =", matched)
                print(json.dumps(plan, ensure_ascii=False, indent=2, default=str))

            print("\n6. NHẬN ĐỊNH TẠM")
            if op in {"QD3805-OP-0126","QD3805-OP-0160"}:
                print("LOẠI = HỖN HỢP")
                print("QUY TẮC = chỉ phần GỘP TOÀN TRƯỜNG cần xác định source/target; phần tiếp nhận điểm/lớp = GIỮ NGUYÊN.")
            else:
                print("LOẠI = CẦN KHÓA SOURCE/TARGET/PLAN CHÍNH XÁC TRƯỚC KHI PREVIEW.")
            print("DB_ACTION = NONE")

        print("\n" + "=" * 150)
        print("KHẢO SÁT HOÀN TẤT")
        print("DATABASE = KHÔNG THAY ĐỔI")
        print("=" * 150)
        return 0

    finally:
        conn.close()

if __name__ == "__main__":
    class Tee:
        def __init__(self, *streams):
            self.streams = streams
        def write(self, data):
            for s in self.streams:
                s.write(data)
                s.flush()
        def flush(self):
            for s in self.streams:
                s.flush()

    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8-sig", newline="\n") as f:
        old = sys.stdout
        sys.stdout = Tee(old, f)
        try:
            code = main()
        finally:
            sys.stdout = old
    sys.exit(code)
