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
OUT = EXPORT_DIR / "PREVIEW_THCS_OP0172.txt"

EXPECTED_DB_SHA = "9cd85770ad9f6743c6a96d54d2cd5d3e706466433acc287f3664d0e4e44b4d5d"

PLAN_ID = "PA2026-98173E42E1D0"
OP_CODE = "QD3805-OP-0172"

TARGET = (1463, 104, "40427513", "THCS Đại Sơn")
SOURCES = [
    (1464, 104, "40427521", "THCS Trù Sơn"),
    (1465, 104, "40427522", "THCS Lê Hồng Phong"),
]

BASE_YEAR_ID = 1
CURRENT_YEAR_ID = 2

EXPECTED_TARGET = {"TOTAL":40,"CBQL":2,"GIAO_VIEN":32,"NHAN_VIEN":6}
EXPECTED_SOURCE_1464 = {"TOTAL":42,"CBQL":2,"GIAO_VIEN":36,"NHAN_VIEN":4}
EXPECTED_SOURCE_1465 = {"TOTAL":0,"CBQL":0,"GIAO_VIEN":0,"NHAN_VIEN":0}
EXPECTED_FINAL = {"TOTAL":82,"CBQL":4,"GIAO_VIEN":68,"NHAN_VIEN":10}

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
        (sid, year_id)
    )
    names = [d[0] for d in cur.description]
    return [dict(zip(names, r)) for r in cur.fetchall()]

def summary(rows):
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
    if status in EXCLUDED_STATUS_CODES:
        return False, "status_code="+status
    if label in EXCLUDED_SOURCE_LABELS:
        return False, "source_status_label="+label
    return True, ""

def current_footprint(conn, sid):
    hits = []
    for table in table_names(conn):
        c = columns(conn, table)
        if "school_id" not in c or "school_year_id" not in c:
            continue
        safe = table.replace('"','""')
        try:
            n = conn.execute(
                f'SELECT COUNT(*) FROM "{safe}" WHERE school_id=? AND school_year_id=?',
                (sid, CURRENT_YEAR_ID)
            ).fetchone()[0]
            if n:
                hits.append((table,n))
        except sqlite3.Error:
            pass
    return hits

def related(conn):
    ids = {TARGET[0]} | {x[0] for x in SOURCES}
    official = []
    for r in conn.execute(
        "SELECT id,plan_id,operation_id,target_school_id,source_school_ids_json,created_at "
        "FROM school_merger_official_executions ORDER BY id"
    ).fetchall():
        try:
            src = {int(x) for x in json.loads(r[4] or "[]")}
        except Exception:
            src = set()
        if r[1] == PLAN_ID or int(r[3]) in ids or bool(src & ids):
            official.append(r)

    operations = []
    for r in conn.execute(
        "SELECT id,target_school_id,source_school_ids_json,created_at "
        "FROM school_merger_operations ORDER BY id"
    ).fetchall():
        try:
            src = {int(x) for x in json.loads(r[2] or "[]")}
        except Exception:
            src = set()
        if int(r[1]) in ids or bool(src & ids):
            operations.append(r)
    return official, operations

def school_users(conn, sid):
    return conn.execute(
        "SELECT id,username,is_active FROM users WHERE school_id=? AND role_id=3 ORDER BY id",
        (sid,)
    ).fetchall()

def validate_school(row, expected):
    sid,cid,code,name = expected
    return bool(
        row and int(row[0]) == sid and int(row[1]) == cid
        and str(row[2]) == code and name.lower() in str(row[3]).lower()
        and int(row[4]) == 1
    )

def main():
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    print("="*150)
    print("PREVIEW THCS QD3805-OP-0172")
    print("THCS Trù Sơn + THCS Lê Hồng Phong (Mỹ Sơn) -> THCS Đại Sơn")
    print("LƯU Ý: school_id=1465 là đúng trường THCS Lê Hồng Phong tại Bạch Hà nhưng DB hiện không có staff 2025-2026.")
    print("CHỈ ĐỌC - KHÔNG GHI DATABASE")
    print("="*150)

    if not DB.exists():
        print("DỪNG: Không tìm thấy DB", DB)
        return 2

    sha = sha256_file(DB)
    print("DB_SHA =", sha)
    print("EXPECTED_DB_SHA =", EXPECTED_DB_SHA)

    conn = sqlite3.connect(DB.resolve().as_uri()+"?mode=ro", uri=True, timeout=30)
    conn.execute("PRAGMA query_only=ON")
    try:
        reasons = []

        integ = conn.execute("PRAGMA integrity_check").fetchone()[0]
        fk = conn.execute("PRAGMA foreign_key_check").fetchall()
        print("integrity =", integ)
        print("FK =", len(fk))

        if sha != EXPECTED_DB_SHA:
            reasons.append("DB SHA khác nền sau OP-0025")
        if integ != "ok" or fk:
            reasons.append("Database health không đạt")

        plan = find_plan()
        print("\nPLAN =", json.dumps(plan, ensure_ascii=False, indent=2, default=str))
        if not plan:
            reasons.append("Không tìm thấy plan")
        else:
            if plan.get("school_year_code") != "2026-2027":
                reasons.append("Plan sai school_year_code")
            if plan.get("commune_excel") != "Bạch Hà":
                reasons.append("Plan sai commune_excel")
            if plan.get("plan_text") != "THCS Đại Sơn":
                reasons.append("Plan sai plan_text")
            if int(plan.get("target_member_index")) != 0:
                reasons.append("Plan sai target_member_index")
            names = [str(x.get("school_name","")) for x in plan.get("members") or [] if isinstance(x,dict)]
            expected_names = ["THCS Đại Sơn","THCS Lê Hồng Phong (Mỹ Sơn)","THCS Trù Sơn"]
            if names != expected_names:
                reasons.append("Plan members không đúng")

        target_row = school(conn, TARGET[0])
        print("\nTARGET =", target_row)
        if not validate_school(target_row, TARGET):
            reasons.append("Target sai id/commune/code/name/active")

        source_rows_by_id = {}
        for s in SOURCES:
            r = school(conn, s[0])
            source_rows_by_id[s[0]] = r
            print("SOURCE =", r)
            if not validate_school(r, s):
                reasons.append(f"Source {s[0]} sai id/commune/code/name/active")

        target_staff = staff_rows(conn, TARGET[0], BASE_YEAR_ID)
        src1464_staff = staff_rows(conn, 1464, BASE_YEAR_ID)
        src1465_staff = staff_rows(conn, 1465, BASE_YEAR_ID)

        print("TARGET_BASE =", json.dumps(summary(target_staff), ensure_ascii=False))
        print("SOURCE_1464_BASE =", json.dumps(summary(src1464_staff), ensure_ascii=False))
        print("SOURCE_1465_BASE =", json.dumps(summary(src1465_staff), ensure_ascii=False))
        print("EXPECTED_FINAL =", json.dumps(EXPECTED_FINAL, ensure_ascii=False))

        if summary(target_staff) != EXPECTED_TARGET:
            reasons.append("Target base staff sai")
        if summary(src1464_staff) != EXPECTED_SOURCE_1464:
            reasons.append("Source 1464 base staff sai")
        if summary(src1465_staff) != EXPECTED_SOURCE_1465:
            reasons.append("Source 1465 hiện không còn đúng trạng thái rỗng đã khảo sát")

        all_rows = target_staff + src1464_staff + src1465_staff
        excluded = []
        for r in all_rows:
            ok, why = eligible(r)
            if not ok:
                excluded.append({
                    "staff_member_id":r.get("staff_member_id"),
                    "school_id":r.get("school_id"),
                    "position_group":r.get("position_group"),
                    "status_code":r.get("status_code"),
                    "source_status_label":r.get("source_status_label"),
                    "reason":why,
                })
        print("EXCLUDED =", json.dumps(excluded, ensure_ascii=False, indent=2, default=str))
        if excluded:
            reasons.append("Có nhân sự excluded")

        mids = [int(r["staff_member_id"]) for r in all_rows]
        dup = sorted(k for k,v in Counter(mids).items() if v > 1)
        print("DUPLICATE_MEMBER_IDS =", dup)
        if dup:
            reasons.append("Có staff_member_id trùng")

        if mids:
            q = ",".join("?" for _ in mids)
            current = conn.execute(
                f"SELECT staff_member_id,school_id FROM staff_year_records "
                f"WHERE school_year_id=? AND staff_member_id IN ({q}) ORDER BY staff_member_id,school_id",
                [CURRENT_YEAR_ID] + mids
            ).fetchall()
        else:
            current = []
        print("CURRENT_YEAR_EXISTING =", current)
        if current:
            reasons.append("Có staff year=2 đã tồn tại")

        for sid in [TARGET[0]] + [x[0] for x in SOURCES]:
            fp = current_footprint(conn, sid)
            print("CURRENT_FOOTPRINT", sid, "=", fp)
            if fp:
                reasons.append(f"school_id={sid} đã có footprint year=2")

        official, operations = related(conn)
        print("RELATED_OFFICIAL =", official)
        print("RELATED_OPERATIONS =", operations)
        if official:
            reasons.append("Đã có official execution liên quan")
        if operations:
            reasons.append("Đã có merger operation liên quan")

        for sid in [TARGET[0]] + [x[0] for x in SOURCES]:
            u = school_users(conn, sid)
            print("SCHOOL_USERS", sid, "=", u)
            if len(u) != 1 or int(u[0][2]) != 1:
                reasons.append(f"school_id={sid} school login không đúng")

        final = summary(all_rows)
        print("SIMULATED_FINAL =", json.dumps(final, ensure_ascii=False))
        if final != EXPECTED_FINAL:
            reasons.append("Mô phỏng final không đúng")

        payload = {
            "op":OP_CODE,
            "plan_id":PLAN_ID,
            "target":TARGET,
            "sources":SOURCES,
            "final":EXPECTED_FINAL,
            "source_1465_staff_missing":True,
            "excluded":excluded,
            "duplicates":dup,
            "current":current,
            "official":official,
            "operations":operations,
        }
        fingerprint = hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        print("PREVIEW_FINGERPRINT =", fingerprint)

        print("\n"+"="*150)
        if reasons:
            print("PREVIEW_READY = NO")
            for r in reasons:
                print("REASON =", r)
        else:
            print("PREVIEW_READY = YES")
            print("MODEL = FULL_MERGE_WITH_ONE_SOURCE_PRESENT_BUT_NO_2025_2026_STAFF_DATA")
            print("TARGET =", TARGET)
            print("SOURCES =", SOURCES)
            print("FINAL_STAFF =", json.dumps(EXPECTED_FINAL, ensure_ascii=False))
            print("WARNING = Không tự tạo 12 lớp hoặc nhân sự cho Lê Hồng Phong (Mỹ Sơn); DB không có dữ liệu đó.")
        print("DATABASE = KHÔNG THAY ĐỔI")
        print("="*150)
        return 0
    finally:
        conn.close()

if __name__ == "__main__":
    class Tee:
        def __init__(self,*streams):
            self.streams = streams
        def write(self,data):
            for s in self.streams:
                s.write(data)
                s.flush()
        def flush(self):
            for s in self.streams:
                s.flush()

    EXPORT_DIR.mkdir(parents=True,exist_ok=True)
    with OUT.open("w",encoding="utf-8-sig",newline="\n") as f:
        old = sys.stdout
        sys.stdout = Tee(old,f)
        try:
            code = main()
        finally:
            sys.stdout = old
    sys.exit(code)
