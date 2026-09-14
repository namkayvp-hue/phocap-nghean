# -*- coding: utf-8 -*-
"""
DRY-RUN SAP NHAP TRUONG - XA NGHI LOC - QD 3805/QD-UBND
=========================================================

MUC DICH
- CHI DOC database SQLite.
- KHONG INSERT / UPDATE / DELETE / ALTER / CREATE trong phocap.db.
- Lap bao cao xem truoc viec sap nhap truong tai Xa Nghi Loc.
- Chi tinh du lieu nam hoc 2026-2027 de chuyen doi khi bang co school_year_id.
- Du lieu cac nam truoc duoc thong ke rieng va DE NGUYEN.
- Phat hien cac UNIQUE index co school_id co nguy co xung dot.

DAU RA
C:\\PhoCap\\dry_run_sap_nhap_3805_Nghi_Loc\\
    00_TONG_QUAN.txt
    01_ANH_XA_TRUONG.csv
    02_DU_LIEU_SE_CHUYEN_2026_2027.csv
    03_DU_LIEU_LICH_SU_GIU_NGUYEN.csv
    04_CAN_XU_LY_BANG_KHONG_CO_NAM.csv
    05_XUNG_DOT_UNIQUE.csv
    06_KIEM_TRA_TRUONG_DICH.csv
va file ZIP:
C:\\PhoCap\\dry_run_sap_nhap_3805_Nghi_Loc.zip

QUAN TRONG
Day KHONG PHAI bo chuyen doi that. Script nay khong sua database.
"""

from __future__ import annotations

import csv
import os
import shutil
import sqlite3
import sys
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

PROJECT_DIR = Path(r"C:\PhoCap")
DB_PATH = PROJECT_DIR / "data" / "phocap.db"
OUT_DIR = PROJECT_DIR / "dry_run_sap_nhap_3805_Nghi_Loc"
OUT_ZIP = PROJECT_DIR / "dry_run_sap_nhap_3805_Nghi_Loc.zip"

TARGET_SCHOOL_YEAR_LABEL = "2026-2027"
TARGET_COMMUNE_CODE = "17827"

# school_id nguon, school_id dich, ten chinh thuc sau sap xep, cap hoc, trang thai
MAPPINGS = [
    (748, 748, "Mầm non Nghi Diên", "MN", "GIU_LAM_DICH"),
    (750, 748, "Mầm non Nghi Diên", "MN", "SAP_NHAP"),
    (751, 748, "Mầm non Nghi Diên", "MN", "SAP_NHAP"),

    (747, 747, "Mầm non TT Quán Hành", "MN", "GIU_LAM_DICH"),
    (749, 747, "Mầm non TT Quán Hành", "MN", "SAP_NHAP"),

    (1178, 1178, "Tiểu học Nghi Diên", "TH", "GIU_LAM_DICH"),
    (1181, 1178, "Tiểu học Nghi Diên", "TH", "SAP_NHAP"),

    (1179, 1179, "Tiểu học Nghi Trung", "TH", "GIU_LAM_DICH"),
    (1180, 1179, "Tiểu học Nghi Trung", "TH", "SAP_NHAP"),

    (1177, 1177, "Tiểu học TT Quán Hành", "TH", "GIU_NGUYEN"),

    (1605, 1605, "THCS Nghi Diên", "THCS", "GIU_LAM_DICH"),
    (1608, 1605, "THCS Nghi Diên", "THCS", "SAP_NHAP"),

    (1606, 1606, "THCS Nghi Trung", "THCS", "GIU_LAM_DICH"),
    (1607, 1606, "THCS Nghi Trung", "THCS", "SAP_NHAP"),

    (1604, 1604, "THCS TT Quán Hành", "THCS", "GIU_NGUYEN"),
]

# Bang khong co school_year_id: chi mot so bang nen chuyen truc tiep.
# Cac bang log/quy trinh duoc danh dau REVIEW, khong tu ket luan.
NO_YEAR_POLICY = {
    "users": "MOVE_CURRENT_SCOPE",
    "account_provision_batch_items": "REVIEW",
    "survey_execution_workflow_logs": "KEEP_HISTORY_REVIEW",
    "survey_investigation_participants": "REVIEW",
    "survey_investigation_team_members": "REVIEW",
    "survey_participant_submissions": "REVIEW",
    "survey_school_assignments": "REVIEW",
    "survey_team_registration_logs": "KEEP_HISTORY_REVIEW",
    "thpt_school_references": "REVIEW",
}

def qident(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'

def connect_ro(path: Path) -> sqlite3.Connection:
    uri = path.resolve().as_uri() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only = ON")
    return conn

def table_names(conn: sqlite3.Connection) -> list[str]:
    return [
        r["name"]
        for r in conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    ]

def table_columns(conn: sqlite3.Connection, table: str) -> list[dict[str, Any]]:
    rows = conn.execute(f"PRAGMA table_info({qident(table)})").fetchall()
    return [
        {
            "cid": r[0],
            "name": r[1],
            "type": r[2],
            "notnull": r[3],
            "default": r[4],
            "pk": r[5],
        }
        for r in rows
    ]

def column_names(conn: sqlite3.Connection, table: str) -> list[str]:
    return [c["name"] for c in table_columns(conn, table)]

def safe_index_rows(conn: sqlite3.Connection, table: str) -> list[dict[str, Any]]:
    """Doc index an toan, ke ca expression index co name=None."""
    out = []
    try:
        idx_rows = conn.execute(f"PRAGMA index_list({qident(table)})").fetchall()
    except Exception:
        return out

    for idx in idx_rows:
        idx_name = idx[1] if len(idx) > 1 else None
        if idx_name is None:
            continue
        idx_name = str(idx_name)
        unique = int(idx[2] or 0) if len(idx) > 2 else 0

        # index_xinfo cho biet ca expression (cid=-2, name=None)
        try:
            xrows = conn.execute(f"PRAGMA index_xinfo({qident(idx_name)})").fetchall()
        except Exception:
            xrows = []

        key_parts = []
        for xr in xrows:
            # seqno, cid, name, desc, coll, key
            is_key = int(xr[5] or 0) if len(xr) > 5 else 1
            if not is_key:
                continue
            cid = xr[1] if len(xr) > 1 else None
            name = xr[2] if len(xr) > 2 else None
            if name is None:
                key_parts.append({"kind": "expression", "name": "<expression>", "cid": cid})
            else:
                key_parts.append({"kind": "column", "name": str(name), "cid": cid})

        out.append(
            {
                "name": idx_name,
                "unique": unique,
                "parts": key_parts,
            }
        )
    return out

def find_school_ref_columns(conn: sqlite3.Connection) -> list[tuple[str, str]]:
    refs = []
    for table in table_names(conn):
        cols = column_names(conn, table)
        for col in cols:
            if col == "school_id" or col == "official_school_id":
                refs.append((table, col))
    return refs

def scalar(conn: sqlite3.Connection, sql: str, params: Iterable[Any] = ()) -> Any:
    row = conn.execute(sql, tuple(params)).fetchone()
    if row is None:
        return None
    return row[0]

def find_school_year_id(conn: sqlite3.Connection) -> tuple[int, str]:
    candidates = [
        ("school_years", ["id", "name"]),
        ("school_years", ["id", "school_year"]),
        ("school_years", ["id", "label"]),
    ]
    for table, cols in candidates:
        if table not in table_names(conn):
            continue
        actual_cols = set(column_names(conn, table))
        if not set(cols).issubset(actual_cols):
            continue
        rows = conn.execute(
            f"SELECT {qident(cols[0])}, {qident(cols[1])} FROM {qident(table)}"
        ).fetchall()
        for r in rows:
            label = str(r[1] or "")
            if "2026" in label and "2027" in label:
                return int(r[0]), label

    # Thu cac cot start/end year neu co
    if "school_years" in table_names(conn):
        cols = set(column_names(conn, "school_years"))
        if {"id", "start_year", "end_year"}.issubset(cols):
            row = conn.execute(
                "SELECT id, start_year, end_year FROM school_years "
                "WHERE start_year=2026 AND end_year=2027 LIMIT 1"
            ).fetchone()
            if row:
                return int(row[0]), f"{row[1]}-{row[2]}"

    raise RuntimeError(
        "Khong tim duoc school_year_id cua nam hoc 2026-2027. "
        "DRY-RUN dung lai, KHONG sua database."
    )

def load_school(conn: sqlite3.Connection, school_id: int) -> dict[str, Any] | None:
    if "schools" not in table_names(conn):
        return None
    cols = set(column_names(conn, "schools"))
    want = ["id"]
    for c in ["code", "school_code", "name", "school_name", "active", "is_active", "commune_id"]:
        if c in cols:
            want.append(c)
    row = conn.execute(
        "SELECT " + ", ".join(qident(c) for c in want)
        + " FROM schools WHERE id=?",
        (school_id,),
    ).fetchone()
    if not row:
        return None
    return {want[i]: row[i] for i in range(len(want))}

def school_name_from_row(row: dict[str, Any] | None) -> str:
    if not row:
        return ""
    return str(row.get("name") or row.get("school_name") or "")

def school_code_from_row(row: dict[str, Any] | None) -> str:
    if not row:
        return ""
    return str(row.get("code") or row.get("school_code") or "")

def count_rows_for_school(
    conn: sqlite3.Connection,
    table: str,
    school_col: str,
    school_id: int,
    school_year_id: int | None = None,
) -> int:
    cols = set(column_names(conn, table))
    sql = f"SELECT COUNT(*) FROM {qident(table)} WHERE {qident(school_col)}=?"
    params: list[Any] = [school_id]
    if school_year_id is not None and "school_year_id" in cols:
        sql += " AND school_year_id=?"
        params.append(school_year_id)
    return int(scalar(conn, sql, params) or 0)

def count_legacy_rows_for_school(
    conn: sqlite3.Connection,
    table: str,
    school_col: str,
    school_id: int,
    target_year_id: int,
) -> int:
    cols = set(column_names(conn, table))
    if "school_year_id" not in cols:
        return 0
    sql = (
        f"SELECT COUNT(*) FROM {qident(table)} "
        f"WHERE {qident(school_col)}=? AND school_year_id<>?"
    )
    return int(scalar(conn, sql, (school_id, target_year_id)) or 0)

def sql_where_equal(columns: list[str], row: sqlite3.Row) -> tuple[str, list[Any]]:
    parts = []
    params: list[Any] = []
    for col in columns:
        val = row[col]
        if val is None:
            parts.append(f"{qident(col)} IS NULL")
        else:
            parts.append(f"{qident(col)}=?")
            params.append(val)
    return " AND ".join(parts), params

def detect_unique_conflicts(
    conn: sqlite3.Connection,
    table: str,
    school_col: str,
    source_id: int,
    target_id: int,
    target_year_id: int,
) -> list[dict[str, Any]]:
    if source_id == target_id:
        return []

    cols = set(column_names(conn, table))
    conflicts = []

    for idx in safe_index_rows(conn, table):
        if not idx["unique"]:
            continue

        parts = idx["parts"]
        part_names = [p["name"] for p in parts]
        if school_col not in part_names:
            continue

        if any(p["kind"] == "expression" for p in parts):
            conflicts.append(
                {
                    "table": table,
                    "school_column": school_col,
                    "source_school_id": source_id,
                    "target_school_id": target_id,
                    "index_name": idx["name"],
                    "risk_type": "EXPRESSION_INDEX",
                    "conflict_count": "",
                    "detail": "UNIQUE index co bieu thuc; DRY-RUN khong tu suy dien xung dot.",
                }
            )
            continue

        other_cols = [n for n in part_names if n != school_col]
        if not other_cols:
            # UNIQUE(school_id) => neu target co row thi moi source row xung dot
            source_count = count_rows_for_school(
                conn, table, school_col, source_id,
                target_year_id if "school_year_id" in cols else None
            )
            target_count = count_rows_for_school(
                conn, table, school_col, target_id,
                target_year_id if "school_year_id" in cols else None
            )
            c = source_count if source_count and target_count else 0
            if c:
                conflicts.append(
                    {
                        "table": table,
                        "school_column": school_col,
                        "source_school_id": source_id,
                        "target_school_id": target_id,
                        "index_name": idx["name"],
                        "risk_type": "DIRECT_UNIQUE",
                        "conflict_count": c,
                        "detail": "UNIQUE chi co school_id va truong dich da co du lieu.",
                    }
                )
            continue

        # Doc cac dong nguon se chuyen.
        select_cols = list(dict.fromkeys([school_col] + other_cols))
        sql = (
            "SELECT " + ", ".join(qident(c) for c in select_cols)
            + f" FROM {qident(table)} WHERE {qident(school_col)}=?"
        )
        params: list[Any] = [source_id]
        if "school_year_id" in cols:
            sql += " AND school_year_id=?"
            params.append(target_year_id)

        try:
            src_rows = conn.execute(sql, params).fetchall()
        except Exception as exc:
            conflicts.append(
                {
                    "table": table,
                    "school_column": school_col,
                    "source_school_id": source_id,
                    "target_school_id": target_id,
                    "index_name": idx["name"],
                    "risk_type": "CHECK_FAILED",
                    "conflict_count": "",
                    "detail": f"Khong the kiem tra index: {exc}",
                }
            )
            continue

        conflict_count = 0
        sample = None
        compare_cols = [c for c in other_cols if c in cols]
        for src in src_rows:
            where_other, p_other = sql_where_equal(compare_cols, src)
            q = (
                f"SELECT 1 FROM {qident(table)} WHERE {qident(school_col)}=?"
            )
            p = [target_id]
            if where_other:
                q += " AND " + where_other
                p.extend(p_other)
            q += " LIMIT 1"
            if conn.execute(q, p).fetchone():
                conflict_count += 1
                if sample is None:
                    sample = {c: src[c] for c in compare_cols}

        if conflict_count:
            conflicts.append(
                {
                    "table": table,
                    "school_column": school_col,
                    "source_school_id": source_id,
                    "target_school_id": target_id,
                    "index_name": idx["name"],
                    "risk_type": "UNIQUE_COLLISION",
                    "conflict_count": conflict_count,
                    "detail": f"Vi du khoa trung: {sample}",
                }
            )

    return conflicts

def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        fieldnames = []
        seen = set()
        for row in rows:
            for k in row.keys():
                if k not in seen:
                    seen.add(k)
                    fieldnames.append(k)

    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fieldnames})

def zip_directory(src: Path, dest_zip: Path) -> None:
    if dest_zip.exists():
        dest_zip.unlink()
    with zipfile.ZipFile(dest_zip, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(src.rglob("*")):
            if p.is_file():
                z.write(p, p.relative_to(src))

def main() -> int:
    print("DRY-RUN SAP NHAP TRUONG THEO QD 3805 - XA NGHI LOC")
    print("- CHI DOC database; KHONG INSERT/UPDATE/DELETE.")
    print(f"- Database: {DB_PATH}")

    if not DB_PATH.exists():
        print(f"[LOI] Khong tim thay database: {DB_PATH}")
        return 2

    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    conn = connect_ro(DB_PATH)
    try:
        year_id, year_label = find_school_year_id(conn)
        print(f"[NAM HOC] {year_label} -> school_year_id={year_id}")

        school_refs = find_school_ref_columns(conn)
        source_ids = sorted({m[0] for m in MAPPINGS})
        target_ids = sorted({m[1] for m in MAPPINGS})

        # 1. Kiem tra truong/mapping
        mapping_rows = []
        target_check_rows = []
        school_cache = {}

        for sid in sorted(set(source_ids + target_ids)):
            school_cache[sid] = load_school(conn, sid)

        missing = [sid for sid, row in school_cache.items() if row is None]
        if missing:
            raise RuntimeError(
                "Khong tim thay school_id trong database: "
                + ", ".join(map(str, missing))
            )

        for source_id, target_id, official_name, level, action in MAPPINGS:
            src = school_cache[source_id]
            dst = school_cache[target_id]
            mapping_rows.append(
                {
                    "source_school_id": source_id,
                    "source_school_code": school_code_from_row(src),
                    "source_school_name_db": school_name_from_row(src),
                    "target_school_id": target_id,
                    "target_school_code": school_code_from_row(dst),
                    "target_school_name_db": school_name_from_row(dst),
                    "official_name_after_merger": official_name,
                    "level": level,
                    "action": action,
                    "database_change_now": "NO",
                }
            )

        # Gom cac ten dich chinh thuc moi target
        by_target = {}
        for _, target_id, official_name, level, _ in MAPPINGS:
            by_target[target_id] = (official_name, level)

        for target_id in target_ids:
            dst = school_cache[target_id]
            official_name, level = by_target[target_id]
            incoming = [s for s, t, *_ in MAPPINGS if t == target_id and s != t]
            target_check_rows.append(
                {
                    "target_school_id": target_id,
                    "target_school_code": school_code_from_row(dst),
                    "target_school_name_db": school_name_from_row(dst),
                    "official_name_after_merger": official_name,
                    "level": level,
                    "incoming_source_school_ids": ",".join(map(str, incoming)),
                    "incoming_count": len(incoming),
                    "rename_needed": "YES" if school_name_from_row(dst).strip() != official_name.strip() else "NO",
                }
            )

        # 2. Dem du lieu se chuyen / lich su giu nguyen / bang khong co nam
        move_rows = []
        legacy_rows = []
        no_year_rows = []
        conflict_rows = []

        for source_id, target_id, official_name, level, action in MAPPINGS:
            if source_id == target_id:
                continue

            src_name = school_name_from_row(school_cache[source_id])
            dst_name = school_name_from_row(school_cache[target_id])

            for table, school_col in school_refs:
                cols = set(column_names(conn, table))
                total = count_rows_for_school(conn, table, school_col, source_id, None)
                if total == 0:
                    continue

                if "school_year_id" in cols:
                    current = count_rows_for_school(
                        conn, table, school_col, source_id, year_id
                    )
                    legacy = count_legacy_rows_for_school(
                        conn, table, school_col, source_id, year_id
                    )

                    if current:
                        move_rows.append(
                            {
                                "source_school_id": source_id,
                                "source_school_name": src_name,
                                "target_school_id": target_id,
                                "target_school_name_db": dst_name,
                                "official_name_after_merger": official_name,
                                "table": table,
                                "school_column": school_col,
                                "school_year_id": year_id,
                                "school_year": year_label,
                                "rows_would_move": current,
                                "rule": "MOVE_2026_2027_ONLY",
                            }
                        )

                    if legacy:
                        legacy_rows.append(
                            {
                                "source_school_id": source_id,
                                "source_school_name": src_name,
                                "table": table,
                                "school_column": school_col,
                                "rows_legacy_kept": legacy,
                                "rule": "KEEP_PRE_2026_2027_HISTORY",
                            }
                        )

                    if current:
                        conflict_rows.extend(
                            detect_unique_conflicts(
                                conn, table, school_col,
                                source_id, target_id, year_id
                            )
                        )
                else:
                    policy = NO_YEAR_POLICY.get(table, "REVIEW")
                    no_year_rows.append(
                        {
                            "source_school_id": source_id,
                            "source_school_name": src_name,
                            "target_school_id": target_id,
                            "target_school_name_db": dst_name,
                            "official_name_after_merger": official_name,
                            "table": table,
                            "school_column": school_col,
                            "rows_linked_to_source": total,
                            "policy_for_real_migration": policy,
                            "note": (
                                "Bang khong co school_year_id; KHONG tu dong chuyen trong DRY-RUN. "
                                "Bo chuyen that phai ap dung quy tac rieng."
                            ),
                        }
                    )
                    # Van kiem tra unique de bao truoc rui ro.
                    if policy == "MOVE_CURRENT_SCOPE":
                        conflict_rows.extend(
                            detect_unique_conflicts(
                                conn, table, school_col,
                                source_id, target_id, year_id
                            )
                        )

        # 3. Ghi file
        write_csv(OUT_DIR / "01_ANH_XA_TRUONG.csv", mapping_rows)
        write_csv(OUT_DIR / "02_DU_LIEU_SE_CHUYEN_2026_2027.csv", move_rows)
        write_csv(OUT_DIR / "03_DU_LIEU_LICH_SU_GIU_NGUYEN.csv", legacy_rows)
        write_csv(OUT_DIR / "04_CAN_XU_LY_BANG_KHONG_CO_NAM.csv", no_year_rows)
        write_csv(OUT_DIR / "05_XUNG_DOT_UNIQUE.csv", conflict_rows)
        write_csv(OUT_DIR / "06_KIEM_TRA_TRUONG_DICH.csv", target_check_rows)

        # Tong hop theo bang va target
        by_table_move = defaultdict(int)
        by_target_move = defaultdict(int)
        for r in move_rows:
            by_table_move[r["table"]] += int(r["rows_would_move"])
            by_target_move[int(r["target_school_id"])] += int(r["rows_would_move"])

        by_table_legacy = defaultdict(int)
        for r in legacy_rows:
            by_table_legacy[r["table"]] += int(r["rows_legacy_kept"])

        total_move = sum(by_table_move.values())
        total_legacy = sum(by_table_legacy.values())
        total_no_year = sum(int(r["rows_linked_to_source"]) for r in no_year_rows)
        conflict_count = len(conflict_rows)

        lines = []
        lines.append("DRY-RUN SAP NHAP TRUONG THEO QD 3805/QD-UBND - XA NGHI LOC")
        lines.append("=" * 92)
        lines.append("TRANG THAI: CHI DOC / KHONG SUA DATABASE")
        lines.append(f"Database: {DB_PATH}")
        lines.append(f"Nam hoc chuyen doi: {year_label} (school_year_id={year_id})")
        lines.append("")
        lines.append("NGUYEN TAC")
        lines.append("- Chi du lieu 2026-2027 cua bang co school_year_id moi du kien chuyen.")
        lines.append("- Du lieu cac nam truoc de nguyen theo truong cu.")
        lines.append("- Bang khong co school_year_id chi duoc liet ke de xem truoc; khong tu dong chuyen.")
        lines.append("- Chua doi ten truong, chua khoa truong cu, chua sua tai khoan.")
        lines.append("")
        lines.append("TONG HOP")
        lines.append(f"- Truong nguon/dich trong pham vi Nghi Loc: {len(source_ids)}")
        lines.append(f"- Dau moi sau sap xep: {len(target_ids)}")
        lines.append(f"- So dong 2026-2027 du kien chuyen (cong theo bang): {total_move}")
        lines.append(f"- So dong lich su truoc 2026-2027 se giu nguyen: {total_legacy}")
        lines.append(f"- So dong o bang khong co nam can quy tac rieng: {total_no_year}")
        lines.append(f"- So canh bao/xung dot UNIQUE phat hien: {conflict_count}")
        lines.append("")
        lines.append("DU LIEU 2026-2027 DU KIEN CHUYEN THEO BANG")
        if by_table_move:
            for table, n in sorted(by_table_move.items()):
                lines.append(f"- {table}: {n}")
        else:
            lines.append("- Khong co du lieu theo nam can chuyen.")
        lines.append("")
        lines.append("DU LIEU LICH SU GIU NGUYEN THEO BANG")
        if by_table_legacy:
            for table, n in sorted(by_table_legacy.items()):
                lines.append(f"- {table}: {n}")
        else:
            lines.append("- Khong co.")
        lines.append("")
        lines.append("CAC DAU MOI SAU SAP XEP")
        for target_id in target_ids:
            official_name, level = by_target[target_id]
            incoming = [s for s, t, *_ in MAPPINGS if t == target_id and s != t]
            lines.append(
                f"- ID {target_id}: {official_name} ({level}); "
                f"nhan tu: {', '.join(map(str, incoming)) if incoming else 'giu nguyen'}; "
                f"so dong co nam du kien nhan: {by_target_move.get(target_id, 0)}"
            )
        lines.append("")
        lines.append("KET LUAN")
        if conflict_count:
            lines.append(
                "- CO CANH BAO UNIQUE. KHONG DUOC chuyen that cho den khi xu ly het file 05_XUNG_DOT_UNIQUE.csv."
            )
        else:
            lines.append(
                "- Chua phat hien xung dot UNIQUE truc tiep trong cac dong DRY-RUN da kiem tra."
            )
        if no_year_rows:
            lines.append(
                "- Van con bang khong co school_year_id. Bo chuyen that phai co quy tac rieng cho users/log/phan cong."
            )
        lines.append("- DRY-RUN nay KHONG thay doi bat ky dong du lieu nao.")

        (OUT_DIR / "00_TONG_QUAN.txt").write_text(
            "\n".join(lines), encoding="utf-8"
        )

        zip_directory(OUT_DIR, OUT_ZIP)

        print("")
        print("=== DRY-RUN HOAN THANH ===")
        print(f"Thu muc ket qua: {OUT_DIR}")
        print(f"File gui lai ChatGPT: {OUT_ZIP}")
        print(f"So dong 2026-2027 du kien chuyen: {total_move}")
        print(f"So canh bao UNIQUE: {conflict_count}")
        print("Database phocap.db KHONG bi thay doi.")
        return 0

    except Exception as exc:
        print(f"[LOI] {type(exc).__name__}: {exc}")
        print("DRY-RUN dung lai. Database phocap.db KHONG bi thay doi.")
        return 1
    finally:
        conn.close()

if __name__ == "__main__":
    raise SystemExit(main())
