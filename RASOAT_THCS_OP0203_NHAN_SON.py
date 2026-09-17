# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import json
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
REGISTRY = ROOT / "school_merger_official_registry_v2.json"
EXPORT_DIR = ROOT / "exports"
OUT = EXPORT_DIR / "RASOAT_THCS_OP0203_NHAN_SON.txt"

EXPECTED_DB_SHA = "1723e12a3d06d8f52b7b899174d5040bc4937ab84564e0f4d51b009586d8ce22"

PLAN_ID = "PA2026-16141F34ACBC"
OP_CODE = "QD3805-OP-0203"

KIM_DONG_ID = 1712
KIM_DONG_CODE = "40427524"

LHP_BACH_HA_ID = 1465
LHP_HUNG_NGUYEN_ID = 1551

EXPECTED_COMMUNE_ID = 103

SEARCH_TERMS = [
    "Minh Sơn",
    "Minh Son",
    "Nhân Sơn",
    "Nhan Son",
    "Thuần Trung",
    "Thuan Trung",
    "Lê Hồng Phong",
    "Le Hong Phong",
    "Kim Đồng",
    "Kim Dong",
    "40427524",
    "40431501",
    "40427522",
]

SEARCH_FILE_SUFFIXES = {".json", ".txt", ".csv", ".py", ".md"}

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

def table_info(conn, table):
    safe = table.replace('"', '""')
    return conn.execute(f'PRAGMA table_info("{safe}")').fetchall()

def col_names(conn, table):
    return [r[1] for r in table_info(conn, table)]

def school(conn, sid):
    return conn.execute(
        "SELECT id,commune_id,code,name,is_active,created_at FROM schools WHERE id=?",
        (sid,)
    ).fetchone()

def staff_summary(conn, sid):
    return conn.execute(
        "SELECT school_year_id,position_group,COUNT(*) "
        "FROM staff_year_records WHERE school_id=? "
        "GROUP BY school_year_id,position_group ORDER BY school_year_id,position_group",
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
        c = col_names(conn, table)
        if "school_id" not in c:
            continue
        safe = table.replace('"', '""')
        try:
            if "school_year_id" in c:
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

def schools_in_commune(conn, cid):
    return conn.execute(
        "SELECT id,commune_id,code,name,is_active,created_at FROM schools "
        "WHERE commune_id=? ORDER BY id",
        (cid,)
    ).fetchall()

def all_lhp(conn):
    return conn.execute(
        "SELECT id,commune_id,code,name,is_active,created_at FROM schools "
        "WHERE name LIKE '%Lê Hồng Phong%' OR name LIKE '%Le Hong Phong%' ORDER BY id"
    ).fetchall()

def all_kim_dong(conn):
    return conn.execute(
        "SELECT id,commune_id,code,name,is_active,created_at FROM schools "
        "WHERE name LIKE '%Kim Đồng%' OR name LIKE '%Kim Dong%' ORDER BY id"
    ).fetchall()

def commune_rows(conn):
    out = []
    for table in ("communes", "administrative_units", "units"):
        if table not in table_names(conn):
            continue
        cols = col_names(conn, table)
        if "id" not in cols:
            continue
        name_col = next((c for c in ("name","commune_name","unit_name") if c in cols), None)
        if not name_col:
            continue
        safe_table = table.replace('"','""')
        safe_col = name_col.replace('"','""')
        try:
            rows = conn.execute(
                f'SELECT id,"{safe_col}" FROM "{safe_table}" ORDER BY id'
            ).fetchall()
            out.append((table, rows))
        except sqlite3.Error:
            pass
    return out

def search_db_text(conn):
    hits = []
    preferred = {
        "name","school_name","old_name","new_name","notes","note",
        "source_name","target_name","display_name","full_name",
        "commune_name","unit_name","description"
    }
    for table in table_names(conn):
        info = table_info(conn, table)
        text_cols = []
        for row in info:
            name = row[1]
            decl = str(row[2] or "").upper()
            if any(x in decl for x in ("CHAR","CLOB","TEXT")) or name.lower() in preferred:
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
                        f'WHERE "{safe_col}" LIKE ? LIMIT 12',
                        (f"%{term}%",)
                    ).fetchall()
                except sqlite3.Error:
                    continue
                if rows:
                    hits.append((table, col, term, rows))
    return hits

def search_project_files():
    """
    Chỉ đọc các file văn bản nhỏ/vừa dưới C:\PhoCap để tìm alias/mapping lịch sử.
    Bỏ qua backup, venv, git, uploads, exports để tránh log/rác lớn.
    """
    hits = []
    skip_parts = {
        ".venv", "venv", ".git", "__pycache__", "backups",
        "uploads", "static", "templates", "exports"
    }
    max_size = 5 * 1024 * 1024

    for path in ROOT.rglob("*"):
        try:
            if not path.is_file():
                continue
            rel_parts = {p.lower() for p in path.relative_to(ROOT).parts}
            if any(x.lower() in rel_parts for x in skip_parts):
                continue
            if path.suffix.lower() not in SEARCH_FILE_SUFFIXES:
                continue
            if path.stat().st_size > max_size:
                continue

            text = None
            for enc in ("utf-8-sig", "utf-8", "cp1258", "cp1252"):
                try:
                    text = path.read_text(encoding=enc)
                    break
                except Exception:
                    pass
            if text is None:
                continue

            lines = text.splitlines()
            for term in SEARCH_TERMS:
                found = []
                term_low = term.lower()
                for i, line in enumerate(lines, start=1):
                    if term_low in line.lower():
                        found.append((i, line[:500]))
                        if len(found) >= 8:
                            break
                if found:
                    hits.append((str(path), term, found))
        except Exception:
            continue
    return hits

def main():
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    print("=" * 150)
    print("RÀ SOÁT OP-0203 - THCS KIM ĐỒNG (MINH SƠN) + LÊ HỒNG PHONG (NHÂN SƠN)")
    print("MỤC TIÊU: KHÓA ĐÚNG SOURCE/TARGET; KHÔNG TỰ SUY ĐOÁN")
    print("CHỈ ĐỌC - KHÔNG GHI DATABASE")
    print("=" * 150)

    if not DB.exists():
        print("DỪNG: Không tìm thấy", DB)
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

        if sha != EXPECTED_DB_SHA:
            print("STOP = DB SHA đã khác nền sau OP-0172.")
            return 1
        if integ != "ok" or fk:
            print("STOP = Database health không đạt.")
            return 1

        print("\nPLAN =")
        print(json.dumps(find_plan(), ensure_ascii=False, indent=2, default=str))

        print("\nKEY CANDIDATES")
        for sid in (KIM_DONG_ID, LHP_BACH_HA_ID, LHP_HUNG_NGUYEN_ID):
            print("\nSCHOOL =", school(conn, sid))
            print("STAFF =", staff_summary(conn, sid))
            print("ROLE3_USERS =", role3_users(conn, sid))
            print("RELATED_OFFICIAL =", related_official(conn, sid))
            print("FOOTPRINT =", footprint(conn, sid))

        print("\nALL SCHOOLS IN CURRENT COMMUNE_ID=103 (Thuần Trung)")
        for r in schools_in_commune(conn, EXPECTED_COMMUNE_ID):
            sid = int(r[0])
            print("\nCOMMUNE103_SCHOOL =", r)
            print(" STAFF =", staff_summary(conn, sid))
            print(" ROLE3_USERS =", role3_users(conn, sid))
            print(" RELATED_OFFICIAL =", related_official(conn, sid))

        print("\nALL SCHOOLS NAMED LÊ HỒNG PHONG")
        for r in all_lhp(conn):
            sid = int(r[0])
            print("\nLHP =", r)
            print(" STAFF =", staff_summary(conn, sid))
            print(" ROLE3_USERS =", role3_users(conn, sid))
            print(" RELATED_OFFICIAL =", related_official(conn, sid))
            print(" FOOTPRINT =", footprint(conn, sid))

        print("\nALL SCHOOLS NAMED KIM ĐỒNG")
        for r in all_kim_dong(conn):
            sid = int(r[0])
            print("\nKIM_DONG =", r)
            print(" STAFF =", staff_summary(conn, sid))
            print(" ROLE3_USERS =", role3_users(conn, sid))
            print(" RELATED_OFFICIAL =", related_official(conn, sid))

        print("\nCOMMUNE / ADMINISTRATIVE NAME ROWS MATCHING TERMS")
        for table, rows in commune_rows(conn):
            for rid, name in rows:
                text = str(name or "")
                if any(term.lower() in text.lower() for term in ("Minh Sơn","Nhân Sơn","Thuần Trung","Hưng Nguyên","Bạch Hà")):
                    print(table, "=>", (rid, name))

        print("\nDATABASE TEXT SEARCH")
        hits = search_db_text(conn)
        if not hits:
            print("NO_DB_TEXT_HITS")
        else:
            for table, col, term, rows in hits:
                print(f"\nDB_TEXT_HIT table={table} | column={col} | term={term}")
                for row in rows:
                    print(" ", row)

        print("\nPROJECT FILE SEARCH")
        file_hits = search_project_files()
        if not file_hits:
            print("NO_PROJECT_FILE_HITS")
        else:
            for path, term, rows in file_hits:
                print(f"\nFILE_HIT path={path} | term={term}")
                for lineno, line in rows:
                    print(f"  L{lineno}: {line}")

        print("\n" + "=" * 150)
        print("KẾT LUẬN KỸ THUẬT")
        print("=" * 150)
        print("LHP_BACH_HA_ID_1465_ALREADY_USED_BY_OP0172 =", related_official(conn, LHP_BACH_HA_ID))
        print("KIM_DONG_ID_1712 =", school(conn, KIM_DONG_ID))
        print("LHP_HUNG_NGUYEN_ID_1551 =", school(conn, LHP_HUNG_NGUYEN_ID))
        print("KHÔNG TỰ CHỌN 1551 làm Nhân Sơn nếu không có bằng chứng mapping/địa bàn.")
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
