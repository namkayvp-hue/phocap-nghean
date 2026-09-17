# -*- coding: utf-8 -*-
"""
DRY-RUN V3 - KIEM TRA DU LIEU TUNG BAN GHI + MO PHONG SAP NHAP QD 3805 - NGHI LOC
=================================================================================
Muc tieu:
- CHI DOC database tren dia C:, KHONG SUA phocap.db.
- Truy vet CHINH XAC tung dong nghiep vu khong co school_year_id ve nam hoc.
- Mo phong TOAN BO cac UPDATE du kien tren ban sao SQLite trong RAM.
- Kiem tra UNIQUE / FOREIGN KEY sau mo phong.
- Tao "cong an toan" SAFE_TO_MIGRATE truoc khi viet bo chuyen that.

Chay PowerShell:
    cd C:\PhoCap
    .\.venv\Scripts\python.exe .\kiem_tra_sap_nhap_QD3805_Nghi_Loc_v3.py

Ket qua:
    C:\PhoCap\dry_run_sap_nhap_3805_Nghi_Loc_v3_<timestamp>.zip

QUAN TRONG:
- Script nay KHONG ghi vao C:\PhoCap\data\phocap.db.
- Ban sao de mo phong chi ton tai trong RAM va bi huy khi chuong trinh ket thuc.
"""

from __future__ import annotations

import csv
import sqlite3
import zipfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(r"C:\PhoCap")
DB_PATH = PROJECT_ROOT / "data" / "phocap.db"

TARGET_YEAR_ID = 2
TARGET_YEAR_LABEL = "Năm học 2026-2027"

# Truong NGUON -> truong DICH
MERGE_MAP = {
    750: 748,   # MN Nghi Hoa -> MN Nghi Dien
    751: 748,   # MN Nghi Van -> MN Nghi Dien
    749: 747,   # MN Nghi Trung -> MN TT Quan Hanh
    1181: 1178, # TH Nghi Van -> TH Nghi Dien
    1180: 1179, # TH Nghi Hoa -> TH Nghi Trung
    1608: 1605, # THCS Nghi Van -> THCS Nghi Dien
    1607: 1606, # THCS Nghi Hoa -> THCS Nghi Trung
}

# 8 dau moi sau sap xep va ten chinh thuc du kien.
OFFICIAL_TARGET_NAMES = {
    747: "Mầm non TT Quán Hành",
    748: "Mầm non Nghi Diên",
    1177: "Tiểu học TT Quán Hành",
    1178: "Tiểu học Nghi Diên",
    1179: "Tiểu học Nghi Trung",
    1604: "THCS TT Quán Hành",
    1605: "THCS Nghi Diên",
    1606: "THCS Nghi Trung",
}

EXPECTED_NO_YEAR_TABLES = {
    "users": "MOVE_CURRENT_SCOPE",
    "survey_investigation_participants": "TRACE_YEAR",
    "survey_investigation_team_members": "TRACE_YEAR",
    "survey_participant_submissions": "TRACE_YEAR",
    "survey_school_assignments": "TRACE_YEAR",
    "survey_team_registration_logs": "KEEP_HISTORY",
    "survey_execution_workflow_logs": "KEEP_HISTORY",
}

TRACE_TABLES = [
    "survey_investigation_participants",
    "survey_investigation_team_members",
    "survey_participant_submissions",
    "survey_school_assignments",
]

LOG_TABLES = [
    "survey_team_registration_logs",
    "survey_execution_workflow_logs",
]


def qident(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def die(msg: str, code: int = 1) -> None:
    print(f"\nLOI: {msg}")
    raise SystemExit(code)


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


def columns(conn: sqlite3.Connection, table: str) -> list[dict]:
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


def colset(conn: sqlite3.Connection, table: str) -> set[str]:
    return {c["name"] for c in columns(conn, table)}


def all_tables(conn: sqlite3.Connection) -> list[str]:
    return [
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
    ]


def foreign_keys(conn: sqlite3.Connection, table: str) -> list[dict]:
    rows = conn.execute(f"PRAGMA foreign_key_list({qident(table)})").fetchall()
    return [
        {
            "id": r[0],
            "seq": r[1],
            "ref_table": r[2],
            "from_col": r[3],
            "to_col": r[4] or "id",
            "on_update": r[5],
            "on_delete": r[6],
        }
        for r in rows
    ]


def primary_key_column(conn: sqlite3.Connection, table: str) -> str:
    pks = [c for c in columns(conn, table) if c["pk"]]
    if len(pks) == 1:
        return pks[0]["name"]
    if "id" in colset(conn, table):
        return "id"
    return "rowid"


def write_csv(path: Path, headers: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def school_name_column(conn: sqlite3.Connection) -> str | None:
    if not table_exists(conn, "schools"):
        return None
    cs = colset(conn, "schools")
    for c in ("name", "school_name", "ten_truong"):
        if c in cs:
            return c
    return None


def school_names(conn: sqlite3.Connection) -> dict[int, str]:
    name_col = school_name_column(conn)
    if not name_col:
        return {}
    ids = sorted(set(MERGE_MAP) | set(MERGE_MAP.values()) | set(OFFICIAL_TARGET_NAMES))
    marks = ",".join("?" for _ in ids)
    rows = conn.execute(
        f"SELECT id, {qident(name_col)} FROM schools WHERE id IN ({marks})", ids
    ).fetchall()
    return {int(r[0]): str(r[1]) for r in rows}


def school_rows_for_report(conn: sqlite3.Connection) -> list[dict]:
    if not table_exists(conn, "schools"):
        return []
    cs = colset(conn, "schools")
    name_col = school_name_column(conn)
    ids = sorted(set(MERGE_MAP) | set(MERGE_MAP.values()) | set(OFFICIAL_TARGET_NAMES))
    marks = ",".join("?" for _ in ids)

    interesting = [
        c for c in (
            "id", "code", "school_code", "name", "school_name", "ten_truong",
            "level", "school_level", "education_level",
            "commune_id", "is_active", "active", "status", "deleted_at"
        ) if c in cs
    ]
    if "id" not in interesting:
        interesting.insert(0, "id")

    sql = "SELECT " + ", ".join(qident(c) for c in interesting)
    sql += f" FROM schools WHERE id IN ({marks}) ORDER BY id"

    out = []
    for row in conn.execute(sql, ids).fetchall():
        d = {interesting[i]: row[i] for i in range(len(interesting))}
        sid = int(d["id"])
        d["role_in_merger"] = (
            "SOURCE" if sid in MERGE_MAP
            else ("TARGET" if sid in OFFICIAL_TARGET_NAMES else "")
        )
        d["target_id_if_source"] = MERGE_MAP.get(sid, "")
        d["official_name_after_merger"] = OFFICIAL_TARGET_NAMES.get(sid, "")
        d["name_change_needed"] = (
            "YES"
            if sid in OFFICIAL_TARGET_NAMES and name_col
            and str(d.get(name_col, "")) != OFFICIAL_TARGET_NAMES[sid]
            else "NO"
        )
        out.append(d)
    return out


def resolve_year_from_batch(
    conn: sqlite3.Connection,
    table: str,
    row_pk,
    row: sqlite3.Row,
) -> tuple[int | None, str, str]:
    """Resolve qua survey_batch_id -> survey_batches.school_year_id."""
    if "survey_batch_id" not in row.keys():
        return None, "UNRESOLVED", "Khong co cot survey_batch_id"
    batch_id = row["survey_batch_id"]
    if batch_id is None:
        return None, "UNRESOLVED", "survey_batch_id=NULL"
    if not table_exists(conn, "survey_batches"):
        return None, "UNRESOLVED", "Khong co bang survey_batches"
    cs = colset(conn, "survey_batches")
    if "id" not in cs or "school_year_id" not in cs:
        return None, "UNRESOLVED", "survey_batches khong co id/school_year_id"
    r = conn.execute(
        "SELECT school_year_id FROM survey_batches WHERE id=?", (batch_id,)
    ).fetchone()
    if not r:
        return None, "UNRESOLVED", f"Khong tim thay survey_batch_id={batch_id}"
    return r[0], "RESOLVED", f"{table}.survey_batch_id -> survey_batches.school_year_id"


def resolve_team_member_year(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
) -> tuple[int | None, str, str, object]:
    """Resolve team_member -> survey_investigation_teams -> survey_batch."""
    if "team_id" not in row.keys():
        return None, "UNRESOLVED", "Khong co team_id", None
    team_id = row["team_id"]
    if team_id is None:
        return None, "UNRESOLVED", "team_id=NULL", None
    if not table_exists(conn, "survey_investigation_teams"):
        return None, "UNRESOLVED", "Khong co bang survey_investigation_teams", team_id

    tcols = colset(conn, "survey_investigation_teams")
    if "id" not in tcols:
        return None, "UNRESOLVED", "survey_investigation_teams khong co id", team_id

    if "school_year_id" in tcols:
        tr = conn.execute(
            "SELECT school_year_id FROM survey_investigation_teams WHERE id=?",
            (team_id,)
        ).fetchone()
        if not tr:
            return None, "UNRESOLVED", f"Khong tim thay team_id={team_id}", team_id
        return tr[0], "RESOLVED", (
            "survey_investigation_team_members.team_id -> "
            "survey_investigation_teams.school_year_id"
        ), team_id

    if "survey_batch_id" in tcols:
        tr = conn.execute(
            "SELECT survey_batch_id FROM survey_investigation_teams WHERE id=?",
            (team_id,)
        ).fetchone()
        if not tr:
            return None, "UNRESOLVED", f"Khong tim thay team_id={team_id}", team_id
        batch_id = tr[0]
        if batch_id is None:
            return None, "UNRESOLVED", f"team_id={team_id} co survey_batch_id=NULL", team_id
        if not table_exists(conn, "survey_batches"):
            return None, "UNRESOLVED", "Khong co bang survey_batches", team_id
        bcols = colset(conn, "survey_batches")
        if not {"id", "school_year_id"} <= bcols:
            return None, "UNRESOLVED", "survey_batches khong co id/school_year_id", team_id
        br = conn.execute(
            "SELECT school_year_id FROM survey_batches WHERE id=?", (batch_id,)
        ).fetchone()
        if not br:
            return None, "UNRESOLVED", f"Khong tim thay survey_batch_id={batch_id}", team_id
        return br[0], "RESOLVED", (
            "survey_investigation_team_members.team_id -> "
            "survey_investigation_teams.survey_batch_id -> "
            "survey_batches.school_year_id"
        ), team_id

    # Thu FK truc tiep tu teams den mot bang co school_year_id.
    for fk in foreign_keys(conn, "survey_investigation_teams"):
        ref = fk["ref_table"]
        if not table_exists(conn, ref):
            continue
        rcols = colset(conn, ref)
        if "school_year_id" not in rcols:
            continue
        from_col = fk["from_col"]
        to_col = fk["to_col"]
        if from_col not in tcols or to_col not in rcols:
            continue
        tr = conn.execute(
            f"SELECT {qident(from_col)} FROM survey_investigation_teams WHERE id=?",
            (team_id,)
        ).fetchone()
        if not tr:
            return None, "UNRESOLVED", f"Khong tim thay team_id={team_id}", team_id
        ref_value = tr[0]
        rr = conn.execute(
            f"SELECT school_year_id FROM {qident(ref)} WHERE {qident(to_col)}=?",
            (ref_value,)
        ).fetchone()
        if rr:
            return rr[0], "RESOLVED", (
                f"team_id -> survey_investigation_teams.{from_col} -> "
                f"{ref}.{to_col} -> school_year_id"
            ), team_id

    return None, "UNRESOLVED", (
        "Khong tim thay duong nghiep vu tin cay tu survey_investigation_teams den nam hoc"
    ), team_id


def trace_business_rows(
    conn: sqlite3.Connection,
    names: dict[int, str],
) -> tuple[list[dict], dict[str, list[dict]]]:
    all_rows: list[dict] = []
    movable_by_table: dict[str, list[dict]] = defaultdict(list)

    source_ids = sorted(MERGE_MAP)
    marks = ",".join("?" for _ in source_ids)

    for table in TRACE_TABLES:
        if not table_exists(conn, table):
            all_rows.append({
                "table": table,
                "row_id": "",
                "source_school_id": "",
                "source_school_name": "",
                "target_school_id": "",
                "target_school_name": "",
                "resolved_school_year_id": "",
                "resolution_status": "TABLE_NOT_FOUND",
                "resolution_path": "",
                "action": "BLOCK",
                "survey_batch_id": "",
                "team_id": "",
            })
            continue

        cs = colset(conn, table)
        if "school_id" not in cs:
            all_rows.append({
                "table": table,
                "row_id": "",
                "source_school_id": "",
                "source_school_name": "",
                "target_school_id": "",
                "target_school_name": "",
                "resolved_school_year_id": "",
                "resolution_status": "NO_SCHOOL_ID",
                "resolution_path": "",
                "action": "BLOCK",
                "survey_batch_id": "",
                "team_id": "",
            })
            continue

        pk = primary_key_column(conn, table)
        select_cols = [pk if pk != "rowid" else "rowid", "school_id"]
        for c in ("survey_batch_id", "team_id", "user_id", "status", "created_at"):
            if c in cs and c not in select_cols:
                select_cols.append(c)

        sql = "SELECT " + ", ".join(qident(c) if c != "rowid" else "rowid" for c in select_cols)
        sql += f" FROM {qident(table)} WHERE school_id IN ({marks}) ORDER BY school_id, {qident(pk) if pk != 'rowid' else 'rowid'}"

        rows = conn.execute(sql, source_ids).fetchall()
        for row in rows:
            row_id = row[select_cols[0]]
            source_id = int(row["school_id"])
            target_id = MERGE_MAP[source_id]

            if table == "survey_investigation_team_members":
                year_id, status, path, team_id = resolve_team_member_year(conn, row)
            else:
                year_id, status, path = resolve_year_from_batch(conn, table, row_id, row)
                team_id = row["team_id"] if "team_id" in row.keys() else None

            if status != "RESOLVED":
                action = "BLOCK_UNRESOLVED"
            elif year_id == TARGET_YEAR_ID:
                action = "MOVE_2026_2027"
            else:
                action = "KEEP_HISTORY_OTHER_YEAR"

            item = {
                "table": table,
                "row_id": row_id,
                "source_school_id": source_id,
                "source_school_name": names.get(source_id, ""),
                "target_school_id": target_id,
                "target_school_name": names.get(target_id, ""),
                "resolved_school_year_id": "" if year_id is None else year_id,
                "resolution_status": status,
                "resolution_path": path,
                "action": action,
                "survey_batch_id": row["survey_batch_id"] if "survey_batch_id" in row.keys() else "",
                "team_id": team_id if team_id is not None else "",
            }
            all_rows.append(item)
            if action == "MOVE_2026_2027":
                movable_by_table[table].append(item)

    return all_rows, movable_by_table


def find_extra_no_year_tables(conn: sqlite3.Connection) -> list[dict]:
    extras = []
    known = set(EXPECTED_NO_YEAR_TABLES)
    source_ids = sorted(MERGE_MAP)
    marks = ",".join("?" for _ in source_ids)

    for table in all_tables(conn):
        cs = colset(conn, table)
        if table in known or "school_id" not in cs or "school_year_id" in cs:
            continue
        n = conn.execute(
            f"SELECT COUNT(*) FROM {qident(table)} WHERE school_id IN ({marks})",
            source_ids
        ).fetchone()[0]
        if n:
            extras.append({
                "table": table,
                "rows_linked_to_sources": int(n),
                "status": "BLOCK_NEW_NO_YEAR_TABLE",
            })
    return extras


def direct_year_table_plan(
    conn: sqlite3.Connection,
    names: dict[int, str],
) -> tuple[list[dict], list[str]]:
    """
    Tim moi bang co school_id + school_year_id.
    Loai cac bang no-year da co quy tac rieng.
    """
    rows = []
    tables = []
    source_ids = sorted(MERGE_MAP)

    for table in all_tables(conn):
        cs = colset(conn, table)
        if not {"school_id", "school_year_id"} <= cs:
            continue
        tables.append(table)
        for source_id, target_id in MERGE_MAP.items():
            move_n = conn.execute(
                f"SELECT COUNT(*) FROM {qident(table)} "
                "WHERE school_id=? AND school_year_id=?",
                (source_id, TARGET_YEAR_ID)
            ).fetchone()[0]
            legacy_n = conn.execute(
                f"SELECT COUNT(*) FROM {qident(table)} "
                "WHERE school_id=? AND (school_year_id IS NULL OR school_year_id<>?)",
                (source_id, TARGET_YEAR_ID)
            ).fetchone()[0]
            if move_n or legacy_n:
                rows.append({
                    "table": table,
                    "source_school_id": source_id,
                    "source_school_name": names.get(source_id, ""),
                    "target_school_id": target_id,
                    "target_school_name": names.get(target_id, ""),
                    "rows_move_2026_2027": int(move_n),
                    "rows_keep_other_years": int(legacy_n),
                })
    return rows, tables


def count_users(conn: sqlite3.Connection, names: dict[int, str]) -> list[dict]:
    if not table_exists(conn, "users") or "school_id" not in colset(conn, "users"):
        return []
    out = []
    for source_id, target_id in MERGE_MAP.items():
        n = conn.execute(
            "SELECT COUNT(*) FROM users WHERE school_id=?", (source_id,)
        ).fetchone()[0]
        if n:
            out.append({
                "source_school_id": source_id,
                "source_school_name": names.get(source_id, ""),
                "target_school_id": target_id,
                "target_school_name": names.get(target_id, ""),
                "rows_move_current_scope": int(n),
            })
    return out


def count_logs(conn: sqlite3.Connection, names: dict[int, str]) -> list[dict]:
    out = []
    for table in LOG_TABLES:
        if not table_exists(conn, table) or "school_id" not in colset(conn, table):
            continue
        for source_id, target_id in MERGE_MAP.items():
            n = conn.execute(
                f"SELECT COUNT(*) FROM {qident(table)} WHERE school_id=?",
                (source_id,)
            ).fetchone()[0]
            if n:
                out.append({
                    "table": table,
                    "source_school_id": source_id,
                    "source_school_name": names.get(source_id, ""),
                    "target_school_id": target_id,
                    "target_school_name": names.get(target_id, ""),
                    "rows_keep_history": int(n),
                })
    return out


def verify_target_year(conn: sqlite3.Connection) -> tuple[bool, str]:
    if not table_exists(conn, "school_years"):
        return False, "Khong co bang school_years"
    cs = colset(conn, "school_years")
    if "id" not in cs:
        return False, "school_years khong co cot id"

    name_col = None
    for c in ("name", "label", "school_year", "year_name"):
        if c in cs:
            name_col = c
            break

    if name_col:
        r = conn.execute(
            f"SELECT {qident(name_col)} FROM school_years WHERE id=?",
            (TARGET_YEAR_ID,)
        ).fetchone()
        if not r:
            return False, f"Khong co school_year_id={TARGET_YEAR_ID}"
        label = str(r[0])
        ok = ("2026" in label and "2027" in label)
        return ok, f"school_year_id={TARGET_YEAR_ID}; label={label}"

    r = conn.execute("SELECT id FROM school_years WHERE id=?", (TARGET_YEAR_ID,)).fetchone()
    return (r is not None), f"school_year_id={TARGET_YEAR_ID}; khong co cot ten de doi chieu label"


def verify_school_ids(conn: sqlite3.Connection) -> tuple[bool, list[int]]:
    if not table_exists(conn, "schools") or "id" not in colset(conn, "schools"):
        return False, []
    ids = sorted(set(MERGE_MAP) | set(MERGE_MAP.values()) | set(OFFICIAL_TARGET_NAMES))
    marks = ",".join("?" for _ in ids)
    found = {int(r[0]) for r in conn.execute(
        f"SELECT id FROM schools WHERE id IN ({marks})", ids
    ).fetchall()}
    missing = [x for x in ids if x not in found]
    return not missing, missing


def apply_simulation(
    disk_conn: sqlite3.Connection,
    direct_year_tables: list[str],
    movable_business: dict[str, list[dict]],
) -> tuple[bool, list[dict], list[dict], dict]:
    """
    Copy DB -> RAM, sau do UPDATE tren RAM.
    Neu co UNIQUE/FK loi se bi bat o day.
    """
    mem = sqlite3.connect(":memory:")
    mem.row_factory = sqlite3.Row
    disk_conn.backup(mem)
    mem.execute("PRAGMA foreign_keys=ON")

    errors = []
    fk_errors = []
    stats = {
        "direct_year_rows_updated": 0,
        "users_updated": 0,
        "business_rows_updated": 0,
    }

    try:
        mem.execute("BEGIN")

        # 1) Moi bang co school_id + school_year_id: chi nam 2026-2027.
        for table in direct_year_tables:
            for source_id, target_id in MERGE_MAP.items():
                try:
                    cur = mem.execute(
                        f"UPDATE {qident(table)} SET school_id=? "
                        "WHERE school_id=? AND school_year_id=?",
                        (target_id, source_id, TARGET_YEAR_ID)
                    )
                    stats["direct_year_rows_updated"] += max(cur.rowcount, 0)
                except sqlite3.Error as e:
                    errors.append({
                        "stage": "DIRECT_YEAR_TABLE",
                        "table": table,
                        "source_school_id": source_id,
                        "target_school_id": target_id,
                        "error": repr(e),
                    })
                    raise

        # 2) users: chuyen pham vi hien tai.
        if table_exists(mem, "users") and "school_id" in colset(mem, "users"):
            for source_id, target_id in MERGE_MAP.items():
                try:
                    cur = mem.execute(
                        "UPDATE users SET school_id=? WHERE school_id=?",
                        (target_id, source_id)
                    )
                    stats["users_updated"] += max(cur.rowcount, 0)
                except sqlite3.Error as e:
                    errors.append({
                        "stage": "USERS",
                        "table": "users",
                        "source_school_id": source_id,
                        "target_school_id": target_id,
                        "error": repr(e),
                    })
                    raise

        # 3) Bang nghiep vu no-year: chi row da truy vet == TARGET_YEAR_ID.
        for table, items in movable_business.items():
            if not items:
                continue
            pk = primary_key_column(mem, table)
            grouped = defaultdict(list)
            for item in items:
                grouped[item["target_school_id"]].append(item["row_id"])

            for target_id, row_ids in grouped.items():
                marks = ",".join("?" for _ in row_ids)
                try:
                    cur = mem.execute(
                        f"UPDATE {qident(table)} SET school_id=? "
                        f"WHERE {qident(pk) if pk != 'rowid' else 'rowid'} IN ({marks})",
                        [target_id] + row_ids
                    )
                    stats["business_rows_updated"] += max(cur.rowcount, 0)
                except sqlite3.Error as e:
                    errors.append({
                        "stage": "BUSINESS_TRACE_TABLE",
                        "table": table,
                        "source_school_id": "",
                        "target_school_id": target_id,
                        "error": repr(e),
                    })
                    raise

        # 4) Kiem tra FK tren anh RAM sau update.
        fk_rows = mem.execute("PRAGMA foreign_key_check").fetchall()
        for r in fk_rows:
            fk_errors.append({
                "table": r[0],
                "rowid": r[1],
                "parent": r[2],
                "fkid": r[3],
            })

        if fk_errors:
            errors.append({
                "stage": "FOREIGN_KEY_CHECK",
                "table": "",
                "source_school_id": "",
                "target_school_id": "",
                "error": f"foreign_key_check co {len(fk_errors)} loi",
            })
            mem.rollback()
            return False, errors, fk_errors, stats

        mem.rollback()  # Mo phong xong, khong can commit ke ca trong RAM.
        return True, errors, fk_errors, stats

    except sqlite3.Error:
        try:
            mem.rollback()
        except Exception:
            pass
        return False, errors, fk_errors, stats
    finally:
        mem.close()


def main() -> None:
    print("=" * 96)
    print("DRY-RUN V3 - TRUY VET TUNG DONG + MO PHONG SAP NHAP QD 3805 - NGHI LOC")
    print("=" * 96)
    print(f"Database: {DB_PATH}")
    print("Che do: CHI DOC DB GOC / MO PHONG UPDATE TREN BAN SAO TRONG RAM")

    if not DB_PATH.exists():
        die(f"Khong tim thay database: {DB_PATH}")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = PROJECT_ROOT / f"dry_run_sap_nhap_3805_Nghi_Loc_v3_{ts}"
    out_dir.mkdir(parents=True, exist_ok=False)

    uri = DB_PATH.resolve().as_uri() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row

    try:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        names = school_names(conn)

        year_ok, year_note = verify_target_year(conn)
        schools_ok, missing_school_ids = verify_school_ids(conn)

        extra_no_year = find_extra_no_year_tables(conn)
        business_rows, movable_business = trace_business_rows(conn, names)
        direct_plan, direct_tables = direct_year_table_plan(conn, names)
        users_plan = count_users(conn, names)
        logs_plan = count_logs(conn, names)
        school_report = school_rows_for_report(conn)

        unresolved_business = [
            r for r in business_rows
            if r["resolution_status"] not in ("RESOLVED",)
            and r["resolution_status"] not in ("TABLE_NOT_FOUND", "NO_SCHOOL_ID")
        ]
        structural_business_errors = [
            r for r in business_rows
            if r["resolution_status"] in ("TABLE_NOT_FOUND", "NO_SCHOOL_ID")
        ]

        resolved_business = [r for r in business_rows if r["resolution_status"] == "RESOLVED"]
        business_move = [r for r in resolved_business if r["action"] == "MOVE_2026_2027"]
        business_keep = [r for r in resolved_business if r["action"] == "KEEP_HISTORY_OTHER_YEAR"]

        sim_ok, sim_errors, fk_errors, sim_stats = apply_simulation(
            conn, direct_tables, movable_business
        )

        gate_checks = [
            {
                "check": "integrity_check",
                "result": "PASS" if integrity == "ok" else "FAIL",
                "detail": str(integrity),
            },
            {
                "check": "target_school_year",
                "result": "PASS" if year_ok else "FAIL",
                "detail": year_note,
            },
            {
                "check": "all_source_target_school_ids_exist",
                "result": "PASS" if schools_ok else "FAIL",
                "detail": "OK" if schools_ok else f"Missing: {missing_school_ids}",
            },
            {
                "check": "no_new_school_id_without_school_year_table",
                "result": "PASS" if not extra_no_year else "FAIL",
                "detail": f"extra_tables={len(extra_no_year)}",
            },
            {
                "check": "business_tables_structure",
                "result": "PASS" if not structural_business_errors else "FAIL",
                "detail": f"structural_errors={len(structural_business_errors)}",
            },
            {
                "check": "all_business_rows_year_resolved",
                "result": "PASS" if not unresolved_business else "FAIL",
                "detail": (
                    f"resolved={len(resolved_business)}; unresolved={len(unresolved_business)}"
                ),
            },
            {
                "check": "simulation_update_in_ram",
                "result": "PASS" if sim_ok else "FAIL",
                "detail": (
                    f"direct_year={sim_stats['direct_year_rows_updated']}; "
                    f"users={sim_stats['users_updated']}; "
                    f"business={sim_stats['business_rows_updated']}; "
                    f"errors={len(sim_errors)}"
                ),
            },
            {
                "check": "simulation_foreign_key_check",
                "result": "PASS" if not fk_errors else "FAIL",
                "detail": f"fk_errors={len(fk_errors)}",
            },
        ]

        safe = all(r["result"] == "PASS" for r in gate_checks)

        # Bao cao chi tiet
        school_headers = []
        for r in school_report:
            for k in r.keys():
                if k not in school_headers:
                    school_headers.append(k)
        if not school_headers:
            school_headers = [
                "id", "role_in_merger", "target_id_if_source",
                "official_name_after_merger", "name_change_needed"
            ]

        write_csv(
            out_dir / "13_TRUY_VET_40_DONG_NGHIEP_VU.csv",
            [
                "table", "row_id",
                "source_school_id", "source_school_name",
                "target_school_id", "target_school_name",
                "survey_batch_id", "team_id",
                "resolved_school_year_id",
                "resolution_status", "resolution_path", "action",
            ],
            business_rows,
        )
        write_csv(
            out_dir / "14_BANG_CO_NAM_HOC_KE_HOACH_CHUYEN.csv",
            [
                "table",
                "source_school_id", "source_school_name",
                "target_school_id", "target_school_name",
                "rows_move_2026_2027", "rows_keep_other_years",
            ],
            direct_plan,
        )
        write_csv(
            out_dir / "15_USERS_CHUYEN_PHAM_VI.csv",
            [
                "source_school_id", "source_school_name",
                "target_school_id", "target_school_name",
                "rows_move_current_scope",
            ],
            users_plan,
        )
        write_csv(
            out_dir / "16_LOG_GIU_NGUYEN_LICH_SU.csv",
            [
                "table",
                "source_school_id", "source_school_name",
                "target_school_id", "target_school_name",
                "rows_keep_history",
            ],
            logs_plan,
        )
        write_csv(
            out_dir / "17_BANG_KHONG_CO_NAM_PHAT_SINH_THEM_V3.csv",
            ["table", "rows_linked_to_sources", "status"],
            extra_no_year,
        )
        write_csv(
            out_dir / "18_MO_PHONG_LOI_UPDATE.csv",
            ["stage", "table", "source_school_id", "target_school_id", "error"],
            sim_errors,
        )
        write_csv(
            out_dir / "19_MO_PHONG_FOREIGN_KEY_CHECK.csv",
            ["table", "rowid", "parent", "fkid"],
            fk_errors,
        )
        write_csv(
            out_dir / "20_CONG_AN_TOAN.csv",
            ["check", "result", "detail"],
            gate_checks,
        )
        write_csv(
            out_dir / "21_TRUONG_NGUON_DICH_CHI_TIET.csv",
            school_headers,
            school_report,
        )

        # Summary
        direct_move_total = sum(int(r["rows_move_2026_2027"]) for r in direct_plan)
        direct_keep_total = sum(int(r["rows_keep_other_years"]) for r in direct_plan)
        user_total = sum(int(r["rows_move_current_scope"]) for r in users_plan)
        log_total = sum(int(r["rows_keep_history"]) for r in logs_plan)

        summary = out_dir / "00_TONG_QUAN_V3.txt"
        with summary.open("w", encoding="utf-8") as f:
            f.write("DRY-RUN V3 - SAP NHAP TRUONG QD 3805/QD-UBND - NGHI LOC\n")
            f.write("=" * 96 + "\n")
            f.write("TRANG THAI: CHI DOC DATABASE GOC / MO PHONG UPDATE TREN RAM\n")
            f.write(f"Database: {DB_PATH}\n")
            f.write(f"Nam hoc muc tieu: {TARGET_YEAR_LABEL} (school_year_id={TARGET_YEAR_ID})\n")
            f.write(f"integrity_check: {integrity}\n\n")

            f.write("1. TRUY VET BANG NGHIEP VU KHONG CO school_year_id\n")
            f.write(f"- Tong dong nghiep vu tim thay: {len([r for r in business_rows if r.get('row_id') != ''])}\n")
            f.write(f"- Da truy vet duoc nam hoc: {len(resolved_business)}\n")
            f.write(f"- Chuyen vi thuoc 2026-2027: {len(business_move)}\n")
            f.write(f"- Giu lai vi thuoc nam khac: {len(business_keep)}\n")
            f.write(f"- Chua truy vet duoc: {len(unresolved_business)}\n")
            f.write(f"- Loi cau truc bang: {len(structural_business_errors)}\n\n")

            f.write("2. DU LIEU CO school_year_id\n")
            f.write(f"- So bang co school_id + school_year_id: {len(direct_tables)}\n")
            f.write(f"- Dong 2026-2027 du kien chuyen: {direct_move_total}\n")
            f.write(f"- Dong nam khac giu nguyen tai truong cu: {direct_keep_total}\n\n")

            f.write("3. USERS VA LOG\n")
            f.write(f"- users chuyen pham vi hien tai: {user_total}\n")
            f.write(f"- dong log giu nguyen lich su: {log_total}\n\n")

            f.write("4. MO PHONG TREN BAN SAO TRONG RAM\n")
            f.write(f"- Dong bang co nam da UPDATE thu: {sim_stats['direct_year_rows_updated']}\n")
            f.write(f"- users da UPDATE thu: {sim_stats['users_updated']}\n")
            f.write(f"- dong nghiep vu no-year da UPDATE thu: {sim_stats['business_rows_updated']}\n")
            f.write(f"- loi UPDATE/UNIQUE: {len(sim_errors)}\n")
            f.write(f"- loi FOREIGN KEY sau mo phong: {len(fk_errors)}\n\n")

            f.write("5. CONG AN TOAN\n")
            for r in gate_checks:
                f.write(f"- [{r['result']}] {r['check']}: {r['detail']}\n")

            f.write("\nKET LUAN CUOI\n")
            if safe:
                f.write("SAFE_TO_MIGRATE = YES\n")
                f.write(
                    "- V3 da du dieu kien ky thuat de viet BO CHUYEN THAT co "
                    "backup + transaction + rollback + doi chieu sau chuyen.\n"
                )
            else:
                f.write("SAFE_TO_MIGRATE = NO\n")
                f.write(
                    "- CHUA du dieu kien chuyen that. Can xu ly cac muc FAIL "
                    "trong 20_CONG_AN_TOAN.csv truoc.\n"
                )
            f.write("- DRY-RUN V3 KHONG thay doi phocap.db.\n")

        zip_path = PROJECT_ROOT / f"dry_run_sap_nhap_3805_Nghi_Loc_v3_{ts}.zip"
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for p in sorted(out_dir.iterdir()):
                zf.write(p, arcname=p.name)

        print("\nHOAN THANH DRY-RUN V3")
        print(f"SAFE_TO_MIGRATE: {'YES' if safe else 'NO'}")
        print(f"Thu muc ket qua: {out_dir}")
        print(f"ZIP gui lai de doi chieu: {zip_path}")
        print("Khong co thay doi nao duoc ghi vao phocap.db.")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
