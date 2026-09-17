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
REGISTRY = ROOT / "school_merger_official_registry_v2.json"
EXPORT_DIR = ROOT / "exports"
OUT = EXPORT_DIR / "RASOAT_THCS_OP0172_MY_SON.txt"

EXPECTED_DB_SHA = "9cd85770ad9f6743c6a96d54d2cd5d3e706466433acc287f3664d0e4e44b4d5d"
PLAN_ID = "PA2026-98173E42E1D0"
EXPECTED_COMMUNE_ID = 104

TARGET_ID = 1463
TRU_SON_ID = 1464
LHP_EMPTY_ID = 1465

SEARCH_TERMS = ["Mỹ Sơn", "My Son", "Lê Hồng Phong", "Le Hong Phong"]

def sha256_file(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()

def load_json(path):
    for enc in ("utf-8-sig", "utf-8"):
        try:
            return json.loads(path.read_text(encoding=enc))
        except Exception:
            pass
    return None

def table_names(conn):
    return [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()]

def table_info(conn, table):
    safe = table.replace('"','""')
    return conn.execute(f'PRAGMA table_info("{safe}")').fetchall()

def col_names(conn, table):
    return [r[1] for r in table_info(conn, table)]

def find_plan():
    data = load_json(REGISTRY)
    if isinstance(data, dict):
        for p in data.get("plans") or []:
            if isinstance(p, dict) and p.get("id") == PLAN_ID:
                return p
    return None

def school(conn, sid):
    return conn.execute(
        "SELECT id,commune_id,code,name,is_active,created_at FROM schools WHERE id=?",
        (sid,)
    ).fetchone()

def staff_summary(conn, sid):
    return conn.execute(
        "SELECT school_year_id,position_group,COUNT(*) "
        "FROM staff_year_records WHERE school_id=? "
        "GROUP BY school_year_id,position_group "
        "ORDER BY school_year_id,position_group",
        (sid,)
    ).fetchall()

def role3_users(conn, sid):
    return conn.execute(
        "SELECT id,username,is_active FROM users "
        "WHERE school_id=? AND role_id=3 ORDER BY id",
        (sid,)
    ).fetchall()

def related_official(conn, sid):
    out = []
    rows = conn.execute(
        "SELECT id,plan_id,operation_id,target_school_id,source_school_ids_json,created_at "
        "FROM school_merger_official_executions ORDER BY id"
    ).fetchall()
    for r in rows:
        try:
            src = {int(x) for x in json.loads(r[4] or "[]")}
        except Exception:
            src = set()
        if int(r[3]) == sid or sid in src:
            out.append(r)
    return out

def footprint(conn, sid):
    out = []
    for table in table_names(conn):
        cols = col_names(conn, table)
        if "school_id" not in cols:
            continue
        safe = table.replace('"','""')
        try:
            if "school_year_id" in cols:
                rows = conn.execute(
                    f'SELECT school_year_id,COUNT(*) FROM "{safe}" '
                    f'WHERE school_id=? GROUP BY school_year_id ORDER BY school_year_id',
                    (sid,)
                ).fetchall()
                if rows:
                    out.append((table, rows))
            else:
                n = conn.execute(
                    f'SELECT COUNT(*) FROM "{safe}" WHERE school_id=?',
                    (sid,)
                ).fetchone()[0]
                if n:
                    out.append((table, [("NO_YEAR", n)]))
        except sqlite3.Error as e:
            out.append((table, [("ERROR", repr(e))]))
    return out

def thcs_commune_104(conn):
    return conn.execute(
        "SELECT id,commune_id,code,name,is_active,created_at FROM schools "
        "WHERE commune_id=? AND (code LIKE '404275%' OR UPPER(name) LIKE '%THCS%' "
        "OR UPPER(name) LIKE '%TRUNG HỌC CƠ SỞ%') ORDER BY id",
        (EXPECTED_COMMUNE_ID,)
    ).fetchall()

def all_lhp(conn):
    return conn.execute(
        "SELECT id,commune_id,code,name,is_active,created_at FROM schools "
        "WHERE name LIKE '%Lê Hồng Phong%' OR name LIKE '%Le Hong Phong%' ORDER BY id"
    ).fetchall()

def search_text_hits(conn):
    hits = []
    preferred_names = {
        "name","school_name","old_name","new_name","notes","note",
        "source_name","target_name","display_name","full_name"
    }
    for table in table_names(conn):
        info = table_info(conn, table)
        text_cols = []
        for row in info:
            name = row[1]
            decl = str(row[2] or "").upper()
            if any(x in decl for x in ("CHAR","CLOB","TEXT")) or name.lower() in preferred_names:
                text_cols.append(name)
        if not text_cols:
            continue

        safe_table = table.replace('"','""')
        for col in text_cols:
            safe_col = col.replace('"','""')
            for term in SEARCH_TERMS:
                try:
                    rows = conn.execute(
                        f'SELECT rowid,"{safe_col}" FROM "{safe_table}" '
                        f'WHERE "{safe_col}" LIKE ? LIMIT 20',
                        (f"%{term}%",)
                    ).fetchall()
                except sqlite3.Error:
                    continue
                if rows:
                    hits.append((table, col, term, rows))
    return hits

def main():
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    print("="*150)
    print("RÀ SOÁT OP-0172 - KHÓA NGUỒN THCS LÊ HỒNG PHONG (MỸ SƠN)")
    print("CHỈ ĐỌC - KHÔNG GHI DATABASE")
    print("="*150)

    if not DB.exists():
        print("DỪNG: Không tìm thấy", DB)
        return 2

    sha = sha256_file(DB)
    print("DB_SHA =", sha)
    print("EXPECTED_DB_SHA =", EXPECTED_DB_SHA)

    conn = sqlite3.connect(DB.resolve().as_uri()+"?mode=ro", uri=True, timeout=30)
    conn.execute("PRAGMA query_only=ON")
    try:
        integ = conn.execute("PRAGMA integrity_check").fetchone()[0]
        fk = conn.execute("PRAGMA foreign_key_check").fetchall()
        print("integrity =", integ)
        print("FK =", len(fk))
        if sha != EXPECTED_DB_SHA:
            print("STOP = DB SHA đã khác nền sau OP-0025.")
            return 1
        if integ != "ok" or fk:
            print("STOP = Database health không đạt.")
            return 1

        print("\nPLAN =")
        print(json.dumps(find_plan(), ensure_ascii=False, indent=2, default=str))

        print("\nKNOWN SCHOOLS")
        for sid in (TARGET_ID, TRU_SON_ID, LHP_EMPTY_ID):
            print("\nSCHOOL =", school(conn, sid))
            print("STAFF =", staff_summary(conn, sid))
            print("ROLE3_USERS =", role3_users(conn, sid))
            print("RELATED_OFFICIAL =", related_official(conn, sid))
            print("FOOTPRINT =", footprint(conn, sid))

        print("\nALL THCS-LIKE SCHOOLS IN COMMUNE_ID=104")
        for r in thcs_commune_104(conn):
            sid = int(r[0])
            print("\nCANDIDATE =", r)
            print(" STAFF =", staff_summary(conn, sid))
            print(" ROLE3_USERS =", role3_users(conn, sid))
            print(" RELATED_OFFICIAL =", related_official(conn, sid))
            print(" FOOTPRINT =", footprint(conn, sid))

        print("\nALL SCHOOLS NAMED LÊ HỒNG PHONG")
        for r in all_lhp(conn):
            sid = int(r[0])
            print("\nLHP_CANDIDATE =", r)
            print(" STAFF =", staff_summary(conn, sid))
            print(" ROLE3_USERS =", role3_users(conn, sid))
            print(" RELATED_OFFICIAL =", related_official(conn, sid))
            print(" FOOTPRINT =", footprint(conn, sid))

        print("\nTEXT SEARCH FOR MỸ SƠN / LÊ HỒNG PHONG")
        hits = search_text_hits(conn)
        if not hits:
            print("NO_TEXT_HITS")
        else:
            for table, col, term, rows in hits:
                print(f"\nTEXT_HIT table={table} | column={col} | term={term}")
                for row in rows:
                    print(" ", row)

        print("\nCOMMUNE 104 THCS STAFF SUMMARY")
        for r in thcs_commune_104(conn):
            sid = int(r[0])
            s = staff_summary(conn, sid)
            print(sid, r[2], r[3], "=>", s)

        print("\n" + "="*150)
        print("KẾT LUẬN KỸ THUẬT")
        print("="*150)
        print("MỤC TIÊU = xác định school_id thật của THCS Lê Hồng Phong (Mỹ Sơn) có dữ liệu 2025-2026.")
        print("KHÔNG TỰ SUY ĐOÁN SOURCE/TARGET.")
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
