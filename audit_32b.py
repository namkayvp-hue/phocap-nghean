from __future__ import annotations

import hashlib
import re
import sqlite3
import sys
from pathlib import Path


def _safe_stdout() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _year_start(value: str) -> int | None:
    m = re.search(r"(\d{4})\D+(\d{4})", str(value or ""))
    if not m:
        return None
    a, b = int(m.group(1)), int(m.group(2))
    return a if b == a + 1 else None


def _resolve(con: sqlite3.Connection, school_id: int, current_name: str, target_year_id: int) -> str:
    yr = con.execute("SELECT code,name FROM school_years WHERE id=?", (target_year_id,)).fetchone()
    if not yr:
        return current_name
    target = _year_start(yr[0] or yr[1] or "")
    if target is None:
        return current_name
    rows = con.execute(
        """
        SELECT h.id,h.old_name,h.new_name,y.code,y.name
        FROM school_name_histories h
        JOIN school_years y ON y.id=h.effective_school_year_id
        WHERE h.school_id=? ORDER BY h.id
        """,
        (school_id,),
    ).fetchall()
    items=[]
    for row in rows:
        start=_year_start(row[3] or row[4] or "")
        if start is not None:
            items.append((start,row[0],row))
    if not items:
        return current_name
    items.sort(key=lambda x:(x[0],x[1]))
    past=[x for x in items if x[0] <= target]
    if past:
        return str(past[-1][2][2] or current_name)
    return str(items[0][2][1] or current_name)


def main() -> int:
    _safe_stdout()
    project = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(r"C:\PhoCap")
    db_path = project / "data" / "phocap.db"
    route = project / "app" / "routers" / "student_reconciliation_source.py"
    helper = project / "app" / "services" / "school_name_history.py"

    print("="*110)
    print("BAI 32B - READ ONLY AUDIT")
    print("="*110)
    print("DB =", db_path)
    if not db_path.exists():
        print("STOP: database not found.")
        return 2
    if not route.exists() or not helper.exists():
        print("STOP: 32B source files are missing.")
        return 3
    print("ROUTE_SHA =", _sha(route))
    print("HELPER_SHA =", _sha(helper))

    uri = db_path.resolve().as_uri() + "?mode=ro"
    con = sqlite3.connect(uri, uri=True, timeout=30)
    try:
        integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
        fk = con.execute("PRAGMA foreign_key_check").fetchall()
        print("INTEGRITY =", integrity)
        print("FK_COUNT =", len(fk))
        table = con.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='school_name_histories'"
        ).fetchone()
        print("HISTORY_TABLE =", "YES" if table else "NO")
        if not table:
            return 4

        years = con.execute("SELECT id,code,name FROM school_years").fetchall()
        years = sorted(
            [x for x in years if _year_start(x[1] or x[2] or "") is not None],
            key=lambda x:_year_start(x[1] or x[2] or ""),
        )
        histories = con.execute(
            """
            SELECT h.id,h.school_id,h.effective_school_year_id,h.old_name,h.new_name,
                   s.code,s.name,y.code
            FROM school_name_histories h
            JOIN schools s ON s.id=h.school_id
            JOIN school_years y ON y.id=h.effective_school_year_id
            ORDER BY h.id
            """
        ).fetchall()
        print("HISTORY_COUNT =", len(histories))
        print("--- RESOLUTION CHECK ---")
        for h in histories:
            hid, sid, eff_id, old_name, new_name, code, current_name, eff_code = h
            eff_start = _year_start(eff_code or "")
            previous = next((y for y in reversed(years) if _year_start(y[1] or y[2] or "") < eff_start), None) if eff_start else None
            before_name = _resolve(con,sid,current_name,previous[0]) if previous else "(none)"
            effective_name = _resolve(con,sid,current_name,eff_id)
            print(f"ID={hid} SCHOOL_ID={sid} CODE={code} EFFECTIVE={eff_code}")
            print("  OLD      =", old_name)
            print("  NEW      =", new_name)
            if previous:
                print(f"  RESOLVED {previous[1]} =", before_name)
            print(f"  RESOLVED {eff_code} =", effective_name)
            ok_before = True if not previous else (str(before_name).strip() == str(old_name).strip())
            ok_effective = str(effective_name).strip() == str(new_name).strip()
            print("  RESULT   =", "PASS" if ok_before and ok_effective else "FAIL")

        tri = con.execute("SELECT id,code,name FROM schools WHERE code='40415412' LIMIT 1").fetchone()
        print("--- TRI LE CHECK ---")
        if tri:
            hcount = con.execute("SELECT COUNT(*) FROM school_name_histories WHERE school_id=?",(tri[0],)).fetchone()[0]
            print("TRI_LE_ID =", tri[0])
            print("TRI_LE_CODE =", tri[1])
            print("TRI_LE_CURRENT_NAME =", tri[2])
            print("TRI_LE_HISTORY_COUNT =", hcount)
        else:
            print("TRI_LE = NOT FOUND")

        print("DATABASE_WRITES_THIS_RUN = 0")
        print("AUDIT32B_SUCCESS =", "YES" if integrity == "ok" and len(fk) == 0 else "NO")
    finally:
        con.close()
    print("="*110)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
