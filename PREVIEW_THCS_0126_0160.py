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
OUT = EXPORT_DIR / "PREVIEW_THCS_0126_0160.txt"

EXPECTED_DB_SHA = "d5d856945235caeac9bb67438f0f289a7b4eb54d53073c449099355c17df29e4"
BASE_YEAR_ID = 1
CURRENT_YEAR_ID = 2

CASES = [
    {
        "op": "QD3805-OP-0126",
        "plan_id": "PA2026-C759EC319848",
        "target": (1504, "40425532", "THCS Diễn Ngọc"),
        "sources": [
            (1502, "40425515", "THCS Diễn Bích"),
        ],
        # Chỉ tiếp nhận điểm/lớp -> GIỮ NGUYÊN, không chuyển toàn bộ trường này.
        "untouched": [
            (1583, "40425536", "THCS Hoa Quảng"),
        ],
        "expected": {
            "target_base": {"TOTAL":47,"CBQL":1,"GIAO_VIEN":42,"NHAN_VIEN":4},
            "sources_base": {"TOTAL":38,"CBQL":2,"GIAO_VIEN":33,"NHAN_VIEN":3},
            "final": {"TOTAL":85,"CBQL":3,"GIAO_VIEN":75,"NHAN_VIEN":7},
        },
        "required_plan_names": [
            "THCS Diễn Ngọc",
            "THCS Diễn Bích",
            "THCS Hoa Quảng (Diễn Hoa)",
        ],
        "policy": "GỘP TOÀN TRƯỜNG: Diễn Bích -> Diễn Ngọc. Phần nhận điểm Diễn Hoa = GIỮ NGUYÊN; KHÔNG CHẠM THCS Hoa Quảng.",
    },
    {
        "op": "QD3805-OP-0160",
        "plan_id": "PA2026-B80F91FB9CD3",
        "target": (1639, "40425518", "THCS Liên Đồng"),
        "sources": [
            (1640, "40425521", "THCS Diễn Tháp"),
            (1641, "40425538", "THCS Diễn Xuân"),
        ],
        # Chỉ tiếp nhận điểm/lớp -> GIỮ NGUYÊN, không chuyển toàn bộ trường này.
        "untouched": [
            (1580, "40425510", "THCS Thái Nguyên"),
        ],
        "expected": {
            "target_base": {"TOTAL":44,"CBQL":2,"GIAO_VIEN":39,"NHAN_VIEN":3},
            "sources_base": {"TOTAL":57,"CBQL":4,"GIAO_VIEN":48,"NHAN_VIEN":5},
            "final": {"TOTAL":101,"CBQL":6,"GIAO_VIEN":87,"NHAN_VIEN":8},
        },
        "required_plan_names": [
            "THCS Liên Đồng",
            "THCS Diễn Xuân",
            "THCS Diễn Tháp",
            "THCS Thái Nguyên (Diễn Thái)",
        ],
        "policy": "GỘP TOÀN TRƯỜNG: Diễn Tháp + Diễn Xuân -> Liên Đồng. Phần nhận điểm Diễn Thái = GIỮ NGUYÊN; KHÔNG CHẠM THCS Thái Nguyên.",
    },
]

EXCLUDED_STATUS_CODES = {"NGHI_HUU","CHUYEN_DI","THOI_VIEC","DA_NGHI"}
EXCLUDED_SOURCE_LABELS = {"Đã nghỉ hưu","Đã chuyển đi","Nghỉ hưu","Chuyển đi"}

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

def find_plan(reg, plan_id):
    if not isinstance(reg, dict):
        return None
    plans = reg.get("plans")
    if not isinstance(plans, list):
        return None
    for p in plans:
        if isinstance(p, dict) and p.get("id") == plan_id:
            return p
    return None

def school(conn, sid):
    cur = conn.execute(
        "SELECT id,commune_id,code,name,is_active,created_at FROM schools WHERE id=?",
        (sid,),
    )
    return cur.fetchone()

def staff_rows(conn, sid, year_id):
    cur = conn.execute(
        """
        SELECT *
        FROM staff_year_records
        WHERE school_id=? AND school_year_id=?
        ORDER BY staff_member_id,id
        """,
        (sid, year_id),
    )
    names = [d[0] for d in cur.description]
    return [dict(zip(names, r)) for r in cur.fetchall()]

def summary(rows):
    c = Counter(str(r.get("position_group") or "NULL") for r in rows)
    return {
        "TOTAL": len(rows),
        "CBQL": c.get("CBQL",0),
        "GIAO_VIEN": c.get("GIAO_VIEN",0),
        "NHAN_VIEN": c.get("NHAN_VIEN",0),
    }

def eligible(row):
    if int(row.get("is_active") or 0) != 1:
        return False, "is_active != 1"
    status = str(row.get("status_code") or "").strip().upper()
    label = str(row.get("source_status_label") or "").strip()
    if status in EXCLUDED_STATUS_CODES:
        return False, f"status_code={status}"
    if label in EXCLUDED_SOURCE_LABELS:
        return False, f"source_status_label={label}"
    return True, ""

def current_existing(conn, member_ids):
    if not member_ids:
        return []
    q = ",".join("?" for _ in member_ids)
    return conn.execute(
        f"""
        SELECT staff_member_id,school_id
        FROM staff_year_records
        WHERE school_year_id=? AND staff_member_id IN ({q})
        ORDER BY staff_member_id,school_id
        """,
        [CURRENT_YEAR_ID] + member_ids,
    ).fetchall()

def table_names(conn):
    return [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()]

def cols(conn, table):
    return [r[1] for r in conn.execute(f'PRAGMA table_info("{table}")').fetchall()]

def current_footprint(conn, sid):
    hits = []
    for table in table_names(conn):
        c = cols(conn, table)
        if "school_id" not in c or "school_year_id" not in c:
            continue
        try:
            n = conn.execute(
                f'SELECT COUNT(*) FROM "{table}" WHERE school_id=? AND school_year_id=?',
                (sid, CURRENT_YEAR_ID),
            ).fetchone()[0]
            if n:
                hits.append((table, n))
        except sqlite3.Error:
            pass
    return hits

def exact_related(conn, ids, plan_id):
    ids = set(ids)
    official = []
    for r in conn.execute(
        """
        SELECT id,plan_id,operation_id,school_year_id,target_school_id,source_school_ids_json,created_at
        FROM school_merger_official_executions ORDER BY id
        """
    ).fetchall():
        try:
            src = {int(x) for x in json.loads(r[5] or "[]")}
        except Exception:
            src = set()
        if r[1] == plan_id or int(r[4]) in ids or bool(src & ids):
            official.append(r)

    operations = []
    for r in conn.execute(
        """
        SELECT id,school_year_id,target_school_id,source_school_ids_json,created_at
        FROM school_merger_operations ORDER BY id
        """
    ).fetchall():
        try:
            src = {int(x) for x in json.loads(r[3] or "[]")}
        except Exception:
            src = set()
        if int(r[2]) in ids or bool(src & ids):
            operations.append(r)
    return official, operations

def school_users(conn, sid):
    return conn.execute(
        """
        SELECT id,username,role_id,is_active
        FROM users
        WHERE school_id=? AND role_id=3
        ORDER BY id
        """,
        (sid,),
    ).fetchall()

def main():
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)

    print("="*150)
    print("PREVIEW THCS OP-0126 / OP-0160")
    print("QUY TẮC: PHẦN CHỈ TIẾP NHẬN ĐIỂM/LỚP = GIỮ NGUYÊN, KHÔNG CHẠM TRƯỜNG GIAO ĐIỂM")
    print("CHỈ ĐỌC - KHÔNG GHI DATABASE")
    print("="*150)

    if not DB.exists():
        print("DỪNG: không tìm thấy", DB)
        return 2

    sha = sha256_file(DB)
    print("DB_SHA =", sha)
    print("EXPECTED_DB_SHA =", EXPECTED_DB_SHA)

    conn = sqlite3.connect(DB.resolve().as_uri()+"?mode=ro", uri=True, timeout=30)
    conn.execute("PRAGMA query_only=ON")
    reg = load_json(REGISTRY)

    try:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        fk = conn.execute("PRAGMA foreign_key_check").fetchall()
        print("integrity =", integrity)
        print("FK =", len(fk))

        if sha != EXPECTED_DB_SHA or integrity != "ok" or fk:
            print("PREVIEW_ALL_READY = NO")
            print("LÝ DO = Nền database đã khác hoặc health không đạt.")
            return 1

        all_ready = True

        for c in CASES:
            reasons = []
            print("\n" + "#"*150)
            print("OPERATION =", c["op"])
            print("#"*150)
            print("POLICY =", c["policy"])

            plan = find_plan(reg, c["plan_id"])
            print("PLAN_ID =", c["plan_id"])
            print("PLAN_OBJECT =", json.dumps(plan, ensure_ascii=False, indent=2, default=str))

            if not plan:
                reasons.append("Không tìm thấy plan")
            else:
                members = plan.get("members") or []
                names = [str(x.get("school_name","")) for x in members if isinstance(x,dict)]
                for required in c["required_plan_names"]:
                    if required not in names:
                        reasons.append(f"Plan thiếu member: {required}")

            target_id, target_code, target_name = c["target"]
            target = school(conn, target_id)
            print("TARGET =", target)

            if not target:
                reasons.append("Không tìm thấy target")
            else:
                if str(target[2]) != target_code or target_name.lower() not in str(target[3]).lower() or int(target[4]) != 1:
                    reasons.append("Target sai id/code/name/active")

            source_rows_all = []
            source_ids = []
            for sid, code, name in c["sources"]:
                row = school(conn, sid)
                print("SOURCE =", row)
                source_ids.append(sid)
                if not row:
                    reasons.append(f"Không tìm thấy source {sid}")
                    continue
                if str(row[2]) != code or name.lower() not in str(row[3]).lower() or int(row[4]) != 1:
                    reasons.append(f"Source {sid} sai id/code/name/active")
                source_rows_all.extend(staff_rows(conn, sid, BASE_YEAR_ID))

            untouched_ids = []
            for sid, code, name in c["untouched"]:
                row = school(conn, sid)
                print("UNTOUCHED_RECEIVE_ONLY_SOURCE =", row)
                untouched_ids.append(sid)
                if not row:
                    reasons.append(f"Không tìm thấy untouched {sid}")
                    continue
                if str(row[2]) != code or name.lower() not in str(row[3]).lower() or int(row[4]) != 1:
                    reasons.append(f"Untouched {sid} sai id/code/name/active")
                print("UNTOUCHED_STAFF_BASE =", summary(staff_rows(conn, sid, BASE_YEAR_ID)))
                print("UNTOUCHED_USERS =", school_users(conn, sid))

            target_rows = staff_rows(conn, target_id, BASE_YEAR_ID)
            print("TARGET_BASE_STAFF =", json.dumps(summary(target_rows), ensure_ascii=False))
            print("SOURCES_BASE_STAFF =", json.dumps(summary(source_rows_all), ensure_ascii=False))
            print("EXPECTED_TARGET_BASE =", json.dumps(c["expected"]["target_base"], ensure_ascii=False))
            print("EXPECTED_SOURCES_BASE =", json.dumps(c["expected"]["sources_base"], ensure_ascii=False))
            print("EXPECTED_FINAL =", json.dumps(c["expected"]["final"], ensure_ascii=False))

            if summary(target_rows) != c["expected"]["target_base"]:
                reasons.append("Target base staff không đúng khảo sát")
            if summary(source_rows_all) != c["expected"]["sources_base"]:
                reasons.append("Source base staff không đúng khảo sát")

            combined = target_rows + source_rows_all
            excluded = []
            for r in combined:
                ok, why = eligible(r)
                if not ok:
                    excluded.append((r.get("staff_member_id"), r.get("school_id"), why))
            print("EXCLUDED =", excluded)
            if excluded:
                reasons.append("Có nhân sự excluded")

            member_ids = [int(r["staff_member_id"]) for r in combined]
            dup = sorted(k for k,v in Counter(member_ids).items() if v > 1)
            print("DUPLICATE_MEMBER_IDS =", dup)
            if dup:
                reasons.append("Có staff_member_id trùng")

            existing = current_existing(conn, sorted(set(member_ids)))
            print("CURRENT_YEAR_EXISTING =", existing)
            if existing:
                reasons.append("Có staff năm 2026-2027 đã tồn tại")

            involved_ids = [target_id] + source_ids
            official, operations = exact_related(conn, involved_ids, c["plan_id"])
            print("RELATED_OFFICIAL =", official)
            print("RELATED_OPERATIONS =", operations)
            if official:
                reasons.append("Đã có official execution liên quan")
            if operations:
                reasons.append("Đã có merger operation liên quan")

            for sid in involved_ids:
                fp = current_footprint(conn, sid)
                print("CURRENT_FOOTPRINT", sid, "=", fp)
                if fp:
                    reasons.append(f"school_id={sid} đã có dữ liệu year=2")

            print("TARGET_USERS =", school_users(conn, target_id))
            for sid in source_ids:
                print("SOURCE_USERS", sid, "=", school_users(conn, sid))

            expected_final = c["expected"]["final"]
            actual_final = summary(combined)
            print("SIMULATED_FINAL =", json.dumps(actual_final, ensure_ascii=False))
            if actual_final != expected_final:
                reasons.append("Tổng mô phỏng final không đúng")

            fingerprint_payload = {
                "op": c["op"],
                "plan_id": c["plan_id"],
                "target": c["target"],
                "sources": c["sources"],
                "untouched": c["untouched"],
                "expected": c["expected"],
                "policy": c["policy"],
                "duplicate_member_ids": dup,
                "current_existing": existing,
                "official": official,
                "operations": operations,
            }
            fingerprint = hashlib.sha256(
                json.dumps(fingerprint_payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
            ).hexdigest()
            print("PREVIEW_FINGERPRINT =", fingerprint)

            if reasons:
                all_ready = False
                print("PREVIEW_READY = NO")
                for r in reasons:
                    print("REASON =", r)
            else:
                print("PREVIEW_READY = YES")
                print("MODEL = FULL_SOURCE_MERGE_WITH_RECEIVE_ONLY_SCHOOL_UNTOUCHED")

        print("\n" + "="*150)
        print("PREVIEW_ALL_READY =", "YES" if all_ready else "NO")
        print("DATABASE = KHÔNG THAY ĐỔI")
        print("="*150)
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
