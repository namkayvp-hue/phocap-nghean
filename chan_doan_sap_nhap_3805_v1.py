from __future__ import annotations

import csv
import sqlite3
import sys
import zipfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path

PROJECT_DIR = Path(r"C:\PhoCap")
DB_PATH = PROJECT_DIR / "data" / "phocap.db"
OUT_DIR = PROJECT_DIR / "chan_doan_sap_nhap_3805"
OUT_ZIP = PROJECT_DIR / "chan_doan_sap_nhap_3805.zip"


def qident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def table_columns(conn: sqlite3.Connection, table: str) -> list[sqlite3.Row]:
    return conn.execute(f"PRAGMA table_info({qident(table)})").fetchall()


def foreign_keys(conn: sqlite3.Connection, table: str) -> list[sqlite3.Row]:
    return conn.execute(f"PRAGMA foreign_key_list({qident(table)})").fetchall()


def index_rows(conn: sqlite3.Connection, table: str) -> list[dict]:
    result: list[dict] = []
    for idx in conn.execute(f"PRAGMA index_list({qident(table)})").fetchall():
        # seq, name, unique, origin, partial
        idx_name = idx[1]
        cols = [r[2] for r in conn.execute(f"PRAGMA index_info({qident(idx_name)})").fetchall()]
        result.append({
            "name": idx_name,
            "unique": int(idx[2] or 0),
            "origin": idx[3] if len(idx) > 3 else "",
            "columns": cols,
        })
    return result


def safe_scalar(conn: sqlite3.Connection, sql: str, params=()) -> int:
    try:
        row = conn.execute(sql, params).fetchone()
        return int(row[0] or 0) if row else 0
    except Exception:
        return 0


def main() -> int:
    print("CHAN DOAN SAP NHAP TRUONG THEO QD 3805/QD-UBND")
    print("- CHI DOC database; KHONG INSERT/UPDATE/DELETE.")
    print(f"- Database: {DB_PATH}")

    if not DB_PATH.exists():
        print(f"[LOI] Khong tim thay database: {DB_PATH}")
        return 2

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for p in OUT_DIR.iterdir():
        if p.is_file():
            p.unlink()

    # Read-only SQLite connection.
    uri = DB_PATH.resolve().as_uri() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row

    try:
        if not table_exists(conn, "schools"):
            print("[LOI] Database khong co bang schools.")
            return 3

        tables = [
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()
        ]

        # School years.
        years: dict[int, str] = {}
        if table_exists(conn, "school_years"):
            cols = {r[1] for r in table_columns(conn, "school_years")}
            name_col = "name" if "name" in cols else ("school_year" if "school_year" in cols else None)
            if name_col:
                for r in conn.execute(f"SELECT id, {qident(name_col)} FROM school_years ORDER BY id"):
                    years[int(r[0])] = str(r[1] or "")

        # Communes.
        communes: dict[int, dict[str, str]] = {}
        if table_exists(conn, "communes"):
            ccols = {r[1] for r in table_columns(conn, "communes")}
            select_cols = ["id"]
            for c in ("code", "name"):
                if c in ccols:
                    select_cols.append(c)
            sql = "SELECT " + ", ".join(qident(x) for x in select_cols) + " FROM communes"
            for r in conn.execute(sql):
                d = {select_cols[i]: r[i] for i in range(len(select_cols))}
                communes[int(d["id"])] = {
                    "code": str(d.get("code") or ""),
                    "name": str(d.get("name") or ""),
                }

        # School list.
        scols = {r[1] for r in table_columns(conn, "schools")}
        wanted = [x for x in ("id", "commune_id", "code", "name", "address", "is_active") if x in scols]
        school_rows = conn.execute(
            "SELECT " + ", ".join(qident(x) for x in wanted) + " FROM schools ORDER BY commune_id, name, id"
        ).fetchall()
        schools: list[dict] = []
        for r in school_rows:
            d = {wanted[i]: r[i] for i in range(len(wanted))}
            cid = int(d.get("commune_id") or 0)
            cd = communes.get(cid, {})
            schools.append({
                "school_id": int(d["id"]),
                "school_code": str(d.get("code") or ""),
                "school_name": str(d.get("name") or ""),
                "school_active": str(d.get("is_active") if "is_active" in d else ""),
                "commune_id": cid,
                "commune_code": cd.get("code", ""),
                "commune_name": cd.get("name", ""),
                "address": str(d.get("address") or ""),
            })

        # Discover every table carrying school_id or a FK to schools.
        school_tables: list[dict] = []
        textual_school_cols: list[dict] = []
        for table in tables:
            cols_info = table_columns(conn, table)
            cols = [r[1] for r in cols_info]
            fks = foreign_keys(conn, table)
            fk_school_cols = [r[3] for r in fks if str(r[2]).lower() == "schools"]
            candidate_cols = sorted(set((["school_id"] if "school_id" in cols else []) + fk_school_cols))
            if candidate_cols:
                for col in candidate_cols:
                    total_non_null = safe_scalar(
                        conn,
                        f"SELECT COUNT(*) FROM {qident(table)} WHERE {qident(col)} IS NOT NULL",
                    )
                    orphan = 0
                    try:
                        orphan = safe_scalar(
                            conn,
                            f"SELECT COUNT(*) FROM {qident(table)} t LEFT JOIN schools s ON s.id=t.{qident(col)} "
                            f"WHERE t.{qident(col)} IS NOT NULL AND s.id IS NULL",
                        )
                    except Exception:
                        pass
                    school_tables.append({
                        "table": table,
                        "school_column": col,
                        "has_fk_to_schools": "YES" if col in fk_school_cols else "NO",
                        "has_school_year_id": "YES" if "school_year_id" in cols else "NO",
                        "rows_with_school": total_non_null,
                        "orphan_school_refs": orphan,
                        "unique_indexes_with_school": "; ".join(
                            f"{idx['name']}({','.join(idx['columns'])})"
                            for idx in index_rows(conn, table)
                            if idx["unique"] and col in idx["columns"]
                        ),
                    })

            for c in cols:
                lc = c.lower()
                if c != "school_id" and ("school" in lc or "truong" in lc):
                    textual_school_cols.append({"table": table, "column": c})

        # Count records per school/table. One wide row per school.
        table_keys = [f"{x['table']}.{x['school_column']}" for x in school_tables]
        counts: dict[int, dict[str, int]] = defaultdict(dict)
        for spec in school_tables:
            table, col = spec["table"], spec["school_column"]
            key = f"{table}.{col}"
            try:
                sql = (
                    f"SELECT {qident(col)}, COUNT(*) FROM {qident(table)} "
                    f"WHERE {qident(col)} IS NOT NULL GROUP BY {qident(col)}"
                )
                for sid, cnt in conn.execute(sql):
                    try:
                        counts[int(sid)][key] = int(cnt or 0)
                    except Exception:
                        continue
            except Exception:
                continue

        # Current-year counts where possible.
        year_table_keys: list[str] = []
        year_counts: dict[tuple[int, int], dict[str, int]] = defaultdict(dict)
        for spec in school_tables:
            if spec["has_school_year_id"] != "YES":
                continue
            table, col = spec["table"], spec["school_column"]
            key = f"{table}.{col}"
            year_table_keys.append(key)
            try:
                sql = (
                    f"SELECT {qident(col)}, school_year_id, COUNT(*) FROM {qident(table)} "
                    f"WHERE {qident(col)} IS NOT NULL GROUP BY {qident(col)}, school_year_id"
                )
                for sid, yid, cnt in conn.execute(sql):
                    if sid is None or yid is None:
                        continue
                    year_counts[(int(sid), int(yid))][key] = int(cnt or 0)
            except Exception:
                continue

        # 1) schools.csv
        schools_csv = OUT_DIR / "01_danh_sach_truong_hien_tai.csv"
        with schools_csv.open("w", newline="", encoding="utf-8-sig") as f:
            fields = list(schools[0].keys()) if schools else ["school_id", "school_name"]
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(schools)

        # 2) school-reference tables
        refs_csv = OUT_DIR / "02_cac_bang_gan_school_id.csv"
        with refs_csv.open("w", newline="", encoding="utf-8-sig") as f:
            fields = [
                "table", "school_column", "has_fk_to_schools", "has_school_year_id",
                "rows_with_school", "orphan_school_refs", "unique_indexes_with_school",
            ]
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(school_tables)

        # 3) all-time wide counts
        counts_csv = OUT_DIR / "03_so_ban_ghi_theo_truong.csv"
        with counts_csv.open("w", newline="", encoding="utf-8-sig") as f:
            base = ["school_id", "school_code", "school_name", "school_active", "commune_code", "commune_name"]
            fields = base + table_keys
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            for s in schools:
                sid = s["school_id"]
                row = {k: s.get(k, "") for k in base}
                for key in table_keys:
                    row[key] = counts.get(sid, {}).get(key, 0)
                w.writerow(row)

        # 4) year-specific long counts
        year_csv = OUT_DIR / "04_so_ban_ghi_theo_truong_va_nam.csv"
        with year_csv.open("w", newline="", encoding="utf-8-sig") as f:
            fields = ["school_id", "school_code", "school_name", "commune_name", "school_year_id", "school_year"] + year_table_keys
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            by_sid = {s["school_id"]: s for s in schools}
            keys = sorted(year_counts.keys())
            for sid, yid in keys:
                s = by_sid.get(sid, {})
                row = {
                    "school_id": sid,
                    "school_code": s.get("school_code", ""),
                    "school_name": s.get("school_name", ""),
                    "commune_name": s.get("commune_name", ""),
                    "school_year_id": yid,
                    "school_year": years.get(yid, ""),
                }
                for key in year_table_keys:
                    row[key] = year_counts[(sid, yid)].get(key, 0)
                w.writerow(row)

        # 5) textual school columns; potential caches/report fields.
        txt_csv = OUT_DIR / "05_cot_ten_truong_khac.csv"
        with txt_csv.open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=["table", "column"])
            w.writeheader()
            w.writerows(textual_school_cols)

        # 6) summary txt
        summary = OUT_DIR / "00_TONG_QUAN.txt"
        active_count = sum(1 for s in schools if str(s["school_active"]).lower() not in ("0", "false"))
        with summary.open("w", encoding="utf-8") as f:
            f.write("CHAN DOAN SAP NHAP TRUONG THEO QD 3805/QD-UBND\n")
            f.write("CHI DOC DATABASE - KHONG SUA DU LIEU\n")
            f.write(f"Thoi diem: {datetime.now():%Y-%m-%d %H:%M:%S}\n")
            f.write(f"Database: {DB_PATH}\n\n")
            f.write(f"Tong truong trong bang schools: {len(schools)}\n")
            f.write(f"Truong dang active (uoc theo is_active): {active_count}\n")
            f.write(f"So bang co school_id/FK -> schools: {len(school_tables)}\n")
            f.write(f"So cot co ten school/truong khac school_id: {len(textual_school_cols)}\n")
            f.write(f"School years: {years}\n\n")
            f.write("CAC BANG CO SCHOOL_ID / FK -> SCHOOLS:\n")
            for x in school_tables:
                f.write(
                    f"- {x['table']}.{x['school_column']}: rows={x['rows_with_school']}, "
                    f"FK={x['has_fk_to_schools']}, year={x['has_school_year_id']}, "
                    f"unique={x['unique_indexes_with_school'] or '-'}\n"
                )
            f.write("\nGHI CHU:\n")
            f.write("- File nay chi de doi chieu truoc khi sap nhap.\n")
            f.write("- Khong duoc tu y UPDATE school_id truoc khi co bang anh xa truong cu -> truong moi.\n")
            f.write("- Cac bang co unique index can xu ly xung dot khi nhieu truong sap nhap vao mot truong.\n")

        # zip outputs
        if OUT_ZIP.exists():
            OUT_ZIP.unlink()
        with zipfile.ZipFile(OUT_ZIP, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for p in sorted(OUT_DIR.iterdir()):
                if p.is_file():
                    zf.write(p, arcname=p.name)

        print("[OK] Da tao bo chan doan CHI DOC:")
        print(f"     {OUT_ZIP}")
        print("Hay gui file ZIP nay de tao bang anh xa va bo chuyen doi an toan.")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
