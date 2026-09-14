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
OUT = EXPORT_DIR / "PREVIEW_THCS_OP0025.txt"

EXPECTED_DB_SHA = "c7e51137abf425fababfc3b1857aa24d3056c7abbe20089f6c33f68d48c7b9b8"

PLAN_ID = "PA2026-F68F2B60851F"
OP_CODE = "QD3805-OP-0025"

TARGET_ID = 1431
TARGET_CODE = "40412512"
TARGET_NAME = "THCS Quang Trung"
TARGET_COMMUNE_ID = 1

SOURCE_ID = 1426
SOURCE_CODE = "40412505"
SOURCE_NAME = "THCS Đội Cung"
SOURCE_COMMUNE_ID = 1

BASE_YEAR_ID = 1
CURRENT_YEAR_ID = 2

EXPECTED_TARGET = {"TOTAL": 0, "CBQL": 0, "GIAO_VIEN": 0, "NHAN_VIEN": 0}
EXPECTED_SOURCE = {"TOTAL": 39, "CBQL": 1, "GIAO_VIEN": 35, "NHAN_VIEN": 3}
EXPECTED_FINAL = {"TOTAL": 39, "CBQL": 1, "GIAO_VIEN": 35, "NHAN_VIEN": 3}

EXCLUDED_STATUS_CODES = {"NGHI_HUU", "CHUYEN_DI", "THOI_VIEC", "DA_NGHI"}
EXCLUDED_SOURCE_LABELS = {"Đã nghỉ hưu", "Đã chuyển đi", "Nghỉ hưu", "Chuyển đi"}

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def load_json(path: Path):
    for enc in ("utf-8-sig", "utf-8"):
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
    return [r[1] for r in conn.execute(
        'PRAGMA table_info("%s")' % table.replace('"', '""')
    ).fetchall()]

def school(conn, sid):
    return conn.execute(
        "SELECT id,commune_id,code,name,is_active,created_at FROM schools WHERE id=?",
        (sid,)
    ).fetchone()

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
        "CBQL": c.get("CBQL", 0),
        "GIAO_VIEN": c.get("GIAO_VIEN", 0),
        "NHAN_VIEN": c.get("NHAN_VIEN", 0),
    }

def eligible(row):
    if int(row.get("is_active") or 0) != 1:
        return False, "is_active != 1"
    status = str(row.get("status_code") or "").strip().upper()
    label = str(row.get("source_status_label") or "").strip()
    if status in EXCLUDED_STATUS_CODES:
        return False, "status_code=" + status
    if label in EXCLUDED_SOURCE_LABELS:
        return False, "source_status_label=" + label
    return True, ""

def current_footprint(conn, sid):
    out = []
    for table in table_names(conn):
        c = columns(conn, table)
        if "school_id" not in c or "school_year_id" not in c:
            continue
        try:
            n = conn.execute(
                'SELECT COUNT(*) FROM "%s" WHERE school_id=? AND school_year_id=?' % table.replace('"','""'),
                (sid, CURRENT_YEAR_ID)
            ).fetchone()[0]
            if n:
                out.append((table, n))
        except sqlite3.Error:
            pass
    return out

def related(conn):
    ids = {TARGET_ID, SOURCE_ID}
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
        if r[1] == PLAN_ID or int(r[3]) in ids or bool(src & ids):
            official.append(r)

    operations = []
    for r in conn.execute(
        """
        SELECT id,target_school_id,source_school_ids_json,created_at
        FROM school_merger_operations
        ORDER BY id
        """
    ).fetchall():
        try:
            src = {int(x) for x in json.loads(r[2] or "[]")}
        except Exception:
            src = set()
        if int(r[1]) in ids or bool(src & ids):
            operations.append(r)
    return official, operations

def school_user(conn, sid):
    return conn.execute(
        """
        SELECT id,username,is_active
        FROM users
        WHERE school_id=? AND role_id=3
        ORDER BY id
        """,
        (sid,)
    ).fetchall()

def main():
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 150)
    print("PREVIEW THCS QD3805-OP-0025")
    print("THCS Đội Cung -> THCS Quang Trung, Phường Thành Vinh")
    print("CHỈ ĐỌC - KHÔNG GHI DATABASE")
    print("=" * 150)

    if not DB.exists():
        print("DỪNG: Không tìm thấy DB", DB)
        return 2

    sha = sha256_file(DB)
    print("DB_SHA =", sha)
    print("EXPECTED_DB_SHA =", EXPECTED_DB_SHA)

    conn = sqlite3.connect(DB.resolve().as_uri() + "?mode=ro", uri=True, timeout=30)
    conn.execute("PRAGMA query_only=ON")

    try:
        integ = conn.execute("PRAGMA integrity_check").fetchone()[0]
        fk = conn.execute("PRAGMA foreign_key_check").fetchall()
        print("integrity =", integ)
        print("FK =", len(fk))

        reasons = []
        if sha != EXPECTED_DB_SHA:
            reasons.append("DB SHA khác nền sau OP-0160")
        if integ != "ok" or fk:
            reasons.append("Database health không đạt")

        plan = find_plan()
        print("\nPLAN =", json.dumps(plan, ensure_ascii=False, indent=2, default=str))
        if not plan:
            reasons.append("Không tìm thấy plan")
        else:
            if plan.get("school_year_code") != "2026-2027":
                reasons.append("Plan sai school_year_code")
            if plan.get("commune_excel") != "Thành Vinh":
                reasons.append("Plan sai commune_excel")
            if plan.get("plan_text") != "THCS Quang Trung":
                reasons.append("Plan sai plan_text")
            if int(plan.get("target_member_index")) != 0:
                reasons.append("Plan sai target_member_index")
            names = [str(x.get("school_name","")) for x in plan.get("members") or [] if isinstance(x,dict)]
            if names != ["THCS Quang Trung", "THCS Đội Cung"]:
                reasons.append("Plan members không đúng 2 trường")

        tgt = school(conn, TARGET_ID)
        src = school(conn, SOURCE_ID)
        print("\nTARGET =", tgt)
        print("SOURCE =", src)

        if not tgt:
            reasons.append("Không tìm thấy target")
        else:
            if int(tgt[1]) != TARGET_COMMUNE_ID or str(tgt[2]) != TARGET_CODE or TARGET_NAME.lower() not in str(tgt[3]).lower() or int(tgt[4]) != 1:
                reasons.append("Target sai commune/code/name/active")

        if not src:
            reasons.append("Không tìm thấy source")
        else:
            if int(src[1]) != SOURCE_COMMUNE_ID or str(src[2]) != SOURCE_CODE or SOURCE_NAME.lower() not in str(src[3]).lower() or int(src[4]) != 1:
                reasons.append("Source sai commune/code/name/active")

        target_rows = staff_rows(conn, TARGET_ID, BASE_YEAR_ID)
        source_rows = staff_rows(conn, SOURCE_ID, BASE_YEAR_ID)
        print("TARGET_BASE =", json.dumps(summary(target_rows), ensure_ascii=False))
        print("SOURCE_BASE =", json.dumps(summary(source_rows), ensure_ascii=False))
        print("EXPECTED_FINAL =", json.dumps(EXPECTED_FINAL, ensure_ascii=False))

        if summary(target_rows) != EXPECTED_TARGET:
            reasons.append("Target base staff không đúng kỳ vọng")
        if summary(source_rows) != EXPECTED_SOURCE:
            reasons.append("Source base staff không đúng kỳ vọng")

        excluded = []
        for r in target_rows + source_rows:
            ok, why = eligible(r)
            if not ok:
                excluded.append({
                    "staff_member_id": r.get("staff_member_id"),
                    "school_id": r.get("school_id"),
                    "position_group": r.get("position_group"),
                    "status_code": r.get("status_code"),
                    "source_status_label": r.get("source_status_label"),
                    "reason": why,
                })
        print("EXCLUDED =", json.dumps(excluded, ensure_ascii=False, indent=2, default=str))
        if excluded:
            reasons.append("Có nhân sự excluded")

        member_ids = [int(r["staff_member_id"]) for r in target_rows + source_rows]
        dup = sorted(x for x, n in Counter(member_ids).items() if n > 1)
        print("DUPLICATE_MEMBER_IDS =", dup)
        if dup:
            reasons.append("Có staff_member_id trùng")

        if member_ids:
            q = ",".join("?" for _ in member_ids)
            current = conn.execute(
                "SELECT staff_member_id,school_id FROM staff_year_records WHERE school_year_id=? AND staff_member_id IN (%s) ORDER BY staff_member_id,school_id" % q,
                [CURRENT_YEAR_ID] + member_ids
            ).fetchall()
        else:
            current = []
        print("CURRENT_YEAR_EXISTING =", current)
        if current:
            reasons.append("Có staff_member đã tồn tại ở year=2")

        print("TARGET_CURRENT_FOOTPRINT =", current_footprint(conn, TARGET_ID))
        print("SOURCE_CURRENT_FOOTPRINT =", current_footprint(conn, SOURCE_ID))
        if current_footprint(conn, TARGET_ID):
            reasons.append("Target đã có footprint year=2")
        if current_footprint(conn, SOURCE_ID):
            reasons.append("Source đã có footprint year=2")

        official, operations = related(conn)
        print("RELATED_OFFICIAL =", official)
        print("RELATED_OPERATIONS =", operations)
        if official:
            reasons.append("Đã có official execution liên quan")
        if operations:
            reasons.append("Đã có merger operation liên quan")

        print("TARGET_USERS =", school_user(conn, TARGET_ID))
        print("SOURCE_USERS =", school_user(conn, SOURCE_ID))
        if len(school_user(conn, TARGET_ID)) != 1 or int(school_user(conn, TARGET_ID)[0][2]) != 1:
            reasons.append("Target school login không đúng")
        if len(school_user(conn, SOURCE_ID)) != 1 or int(school_user(conn, SOURCE_ID)[0][2]) != 1:
            reasons.append("Source school login không đúng")

        final = summary(target_rows + source_rows)
        print("SIMULATED_FINAL =", json.dumps(final, ensure_ascii=False))
        if final != EXPECTED_FINAL:
            reasons.append("Mô phỏng final không đúng")

        payload = {
            "op": OP_CODE,
            "plan_id": PLAN_ID,
            "target": [TARGET_ID, TARGET_CODE, TARGET_NAME],
            "source": [SOURCE_ID, SOURCE_CODE, SOURCE_NAME],
            "final": EXPECTED_FINAL,
            "excluded": excluded,
            "duplicates": dup,
            "current": current,
            "official": official,
            "operations": operations,
        }
        fp = hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        print("PREVIEW_FINGERPRINT =", fp)

        print("\n" + "=" * 150)
        if reasons:
            print("PREVIEW_READY = NO")
            for r in reasons:
                print("REASON =", r)
        else:
            print("PREVIEW_READY = YES")
            print("MODEL = FULL_SOURCE_MERGE_TO_EMPTY_EXISTING_TARGET")
            print("SOURCE =", SOURCE_ID, SOURCE_CODE, SOURCE_NAME)
            print("TARGET =", TARGET_ID, TARGET_CODE, TARGET_NAME)
            print("FINAL_STAFF =", json.dumps(EXPECTED_FINAL, ensure_ascii=False))
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
