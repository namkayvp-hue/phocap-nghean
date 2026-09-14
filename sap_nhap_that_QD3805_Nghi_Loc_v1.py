# -*- coding: utf-8 -*-
"""
SAP NHAP THAT QD 3805 - NGHI LOC - V1
=====================================

MUC TIEU
--------
1) Backup database truoc khi thay doi.
2) Chi chuyen du lieu NAM HOC 2026-2027 (school_year_id=2)
   tu 7 truong nguon ve 5 truong dich lien quan.
3) Chuyen pham vi 152 tai khoan users sang truong dich.
4) Chuyen dung 40 dong nghiep vu survey_* da duoc DRY-RUN V3
   truy vet chac chan thuoc nam hoc 2026-2027.
5) GIU NGUYEN du lieu cac nam cu tai truong cu.
6) GIU NGUYEN cac bang log lich su.
7) Vo hieu hoa 7 truong nguon bang schools.is_active = 0.
8) KHONG TU Y DOI TEN 8 TRUONG DAU MOI trong V1 nay.
9) Toan bo thay doi nam trong 1 TRANSACTION; neu bat ky kiem tra nao sai
   thi ROLLBACK tu dong.

DIEU KIEN AN TOAN DA KHOA TU DRY-RUN V3
---------------------------------------
- integrity_check = ok
- school_year_id=2 la Nam hoc 2026-2027
- 85 dong co school_year_id can chuyen
- 273 dong nam cu phai giu nguyen
- 152 users can chuyen
- 40 dong survey_* no-year can chuyen
- 7 dong log lich su phai giu nguyen
- mo phong UNIQUE/FK: 0 loi

CHAY TRONG POWERSHELL
---------------------
    cd C:\PhoCap
    .\.venv\Scripts\python.exe .\sap_nhap_that_QD3805_Nghi_Loc_v1.py

CHU Y
-----
- Nen dung server/ung dung truoc khi chay de tranh co nguoi ghi DB dong thoi.
- Script TU DUNG neu database da thay doi khac voi DRY-RUN V3.
- Backup nam trong C:\PhoCap\backups\
- Bao cao ket qua nam trong C:\PhoCap\sap_nhap_QD3805_Nghi_Loc_...\

V1 KHONG DOI TEN TRUONG.
"""

from __future__ import annotations

import csv
import sqlite3
import sys
import zipfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(r"C:\PhoCap")
DB_PATH = PROJECT_ROOT / "data" / "phocap.db"
BACKUP_DIR = PROJECT_ROOT / "backups"

TARGET_YEAR_ID = 2

# 7 truong nguon -> truong dich
MERGE_MAP = {
    750: 748,    # MN Nghi Hoa -> MN Nghi Dien
    751: 748,    # MN Nghi Van -> MN Nghi Dien
    749: 747,    # MN Nghi Trung -> MN TT Quan Hanh
    1181: 1178,  # TH Nghi Van -> TH Nghi Dien
    1180: 1179,  # TH Nghi Hoa -> TH Nghi Trung
    1608: 1605,  # THCS Nghi Van -> THCS Nghi Dien
    1607: 1606,  # THCS Nghi Hoa -> THCS Nghi Trung
}

SOURCE_IDS = tuple(MERGE_MAP.keys())
TARGET_IDS = tuple(sorted(set(MERGE_MAP.values())))

# Khoa an toan: DB tai thoi diem chay phai khop dung V3.
EXPECTED = {
    "direct_target_year_rows": 85,
    "direct_legacy_rows": 273,
    "users_rows": 152,
    "business_rows": 40,
    "log_rows": 7,
}

# 40 dong da duoc V3 truy vet CHAC CHAN ve school_year_id=2.
# Dung row id co dinh de khong mo rong pham vi cap nhat ngoai ket qua da kiem tra.
BUSINESS_ROW_IDS = {
    "survey_investigation_participants": [
        39, 40, 41, 42, 43, 44,
        45, 46, 47, 48, 49, 50,
        51, 52, 53, 54, 55, 56,
    ],
    "survey_investigation_team_members": [
        109, 110, 111, 112, 113, 114, 115, 116, 117,
        118, 119, 120, 121, 122, 123, 124, 125, 126,
    ],
    "survey_participant_submissions": [7, 8, 9],
    "survey_school_assignments": [16],
}

LOG_TABLES = [
    "survey_team_registration_logs",
    "survey_execution_workflow_logs",
]


class MigrationAbort(RuntimeError):
    pass


def qident(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
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


def primary_key_column(conn: sqlite3.Connection, table: str) -> str:
    pks = [c for c in columns(conn, table) if c["pk"]]
    if len(pks) == 1:
        return pks[0]["name"]
    if "id" in colset(conn, table):
        return "id"
    return "rowid"


def all_tables(conn: sqlite3.Connection) -> list[str]:
    return [
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' "
            "ORDER BY name"
        ).fetchall()
    ]


def markers(n: int) -> str:
    return ",".join("?" for _ in range(n))


def direct_year_tables(conn: sqlite3.Connection) -> list[str]:
    result = []
    for table in all_tables(conn):
        cs = colset(conn, table)
        if {"school_id", "school_year_id"} <= cs:
            result.append(table)
    return result


def no_year_school_tables_with_source_rows(conn: sqlite3.Connection) -> dict[str, int]:
    """
    Tim moi bang co school_id nhung KHONG co school_year_id
    va dang co row tro den 7 truong nguon.
    """
    out = {}
    m = markers(len(SOURCE_IDS))
    for table in all_tables(conn):
        cs = colset(conn, table)
        if "school_id" not in cs or "school_year_id" in cs:
            continue
        n = conn.execute(
            f"SELECT COUNT(*) FROM {qident(table)} "
            f"WHERE school_id IN ({m})",
            SOURCE_IDS,
        ).fetchone()[0]
        if n:
            out[table] = int(n)
    return out


def school_year_ok(conn: sqlite3.Connection) -> tuple[bool, str]:
    if not table_exists(conn, "school_years"):
        return False, "Khong co bang school_years"
    cs = colset(conn, "school_years")
    if "id" not in cs:
        return False, "school_years khong co cot id"

    label_col = None
    for c in ("name", "label", "school_year", "year_name"):
        if c in cs:
            label_col = c
            break

    if label_col:
        row = conn.execute(
            f"SELECT {qident(label_col)} FROM school_years WHERE id=?",
            (TARGET_YEAR_ID,),
        ).fetchone()
        if not row:
            return False, f"Khong tim thay school_year_id={TARGET_YEAR_ID}"
        label = str(row[0])
        return ("2026" in label and "2027" in label), label

    row = conn.execute(
        "SELECT id FROM school_years WHERE id=?",
        (TARGET_YEAR_ID,),
    ).fetchone()
    return row is not None, "Khong co cot ten nam hoc; chi kiem tra duoc ID"


def schools_ok(conn: sqlite3.Connection) -> tuple[bool, str]:
    if not table_exists(conn, "schools"):
        return False, "Khong co bang schools"
    cs = colset(conn, "schools")
    required = {"id", "is_active"}
    if not required <= cs:
        return False, f"schools thieu cot: {sorted(required - cs)}"

    ids = sorted(set(SOURCE_IDS) | set(TARGET_IDS))
    rows = conn.execute(
        f"SELECT id, is_active FROM schools WHERE id IN ({markers(len(ids))})",
        ids,
    ).fetchall()
    found = {int(r[0]): r[1] for r in rows}
    missing = [x for x in ids if x not in found]
    if missing:
        return False, f"Thieu school id: {missing}"

    bad_sources = [sid for sid in SOURCE_IDS if int(found[sid] or 0) != 1]
    bad_targets = [sid for sid in TARGET_IDS if int(found[sid] or 0) != 1]
    if bad_sources:
        return False, f"Truong nguon khong con active=1: {bad_sources}"
    if bad_targets:
        return False, f"Truong dich khong active=1: {bad_targets}"

    return True, "Tat ca school id ton tai; nguon/dich deu active=1"


def resolve_business_year(conn: sqlite3.Connection, table: str, row_id: int) -> int | None:
    """
    Truy vet lai ngay truoc khi chuyen.
    """
    pk = primary_key_column(conn, table)

    if table == "survey_investigation_team_members":
        cs = colset(conn, table)
        if "team_id" not in cs:
            return None
        row = conn.execute(
            f"SELECT team_id FROM {qident(table)} "
            f"WHERE {qident(pk) if pk != 'rowid' else 'rowid'}=?",
            (row_id,),
        ).fetchone()
        if not row:
            return None
        team_id = row[0]
        if team_id is None or not table_exists(conn, "survey_investigation_teams"):
            return None
        tcs = colset(conn, "survey_investigation_teams")
        if "survey_batch_id" not in tcs:
            return None
        tr = conn.execute(
            "SELECT survey_batch_id FROM survey_investigation_teams WHERE id=?",
            (team_id,),
        ).fetchone()
        if not tr or tr[0] is None:
            return None
        batch_id = tr[0]
    else:
        cs = colset(conn, table)
        if "survey_batch_id" not in cs:
            return None
        row = conn.execute(
            f"SELECT survey_batch_id FROM {qident(table)} "
            f"WHERE {qident(pk) if pk != 'rowid' else 'rowid'}=?",
            (row_id,),
        ).fetchone()
        if not row or row[0] is None:
            return None
        batch_id = row[0]

    if not table_exists(conn, "survey_batches"):
        return None
    bcs = colset(conn, "survey_batches")
    if not {"id", "school_year_id"} <= bcs:
        return None
    br = conn.execute(
        "SELECT school_year_id FROM survey_batches WHERE id=?",
        (batch_id,),
    ).fetchone()
    return None if not br else br[0]


def snapshot_counts(conn: sqlite3.Connection) -> dict:
    direct_tables = direct_year_tables(conn)
    target_year_total = 0
    legacy_total = 0
    per_direct = []

    for table in direct_tables:
        for source_id, target_id in MERGE_MAP.items():
            move_n = conn.execute(
                f"SELECT COUNT(*) FROM {qident(table)} "
                "WHERE school_id=? AND school_year_id=?",
                (source_id, TARGET_YEAR_ID),
            ).fetchone()[0]
            legacy_n = conn.execute(
                f"SELECT COUNT(*) FROM {qident(table)} "
                "WHERE school_id=? AND "
                "(school_year_id IS NULL OR school_year_id<>?)",
                (source_id, TARGET_YEAR_ID),
            ).fetchone()[0]
            target_year_total += int(move_n)
            legacy_total += int(legacy_n)
            if move_n or legacy_n:
                per_direct.append({
                    "table": table,
                    "source_school_id": source_id,
                    "target_school_id": target_id,
                    "target_year_rows": int(move_n),
                    "legacy_rows": int(legacy_n),
                })

    users_total = 0
    if table_exists(conn, "users") and "school_id" in colset(conn, "users"):
        users_total = conn.execute(
            f"SELECT COUNT(*) FROM users "
            f"WHERE school_id IN ({markers(len(SOURCE_IDS))})",
            SOURCE_IDS,
        ).fetchone()[0]

    business_total = 0
    business_detail = []
    for table, row_ids in BUSINESS_ROW_IDS.items():
        if not table_exists(conn, table):
            raise MigrationAbort(f"Mat bang da kiem tra o V3: {table}")
        if "school_id" not in colset(conn, table):
            raise MigrationAbort(f"Bang {table} khong con cot school_id")
        pk = primary_key_column(conn, table)
        for row_id in row_ids:
            row = conn.execute(
                f"SELECT school_id FROM {qident(table)} "
                f"WHERE {qident(pk) if pk != 'rowid' else 'rowid'}=?",
                (row_id,),
            ).fetchone()
            if not row:
                raise MigrationAbort(
                    f"Khong tim thay {table} row_id={row_id} da co trong V3"
                )
            school_id = int(row[0]) if row[0] is not None else None
            if school_id not in MERGE_MAP:
                raise MigrationAbort(
                    f"{table} row_id={row_id} co school_id={school_id}, "
                    "khac voi trang thai V3"
                )
            year_id = resolve_business_year(conn, table, row_id)
            if year_id != TARGET_YEAR_ID:
                raise MigrationAbort(
                    f"{table} row_id={row_id} truy vet school_year_id={year_id}, "
                    f"khong con bang {TARGET_YEAR_ID}"
                )
            business_total += 1
            business_detail.append({
                "table": table,
                "row_id": row_id,
                "source_school_id": school_id,
                "target_school_id": MERGE_MAP[school_id],
                "resolved_school_year_id": year_id,
            })

    log_total = 0
    log_detail = []
    for table in LOG_TABLES:
        if not table_exists(conn, table) or "school_id" not in colset(conn, table):
            continue
        for source_id, target_id in MERGE_MAP.items():
            n = conn.execute(
                f"SELECT COUNT(*) FROM {qident(table)} WHERE school_id=?",
                (source_id,),
            ).fetchone()[0]
            if n:
                log_total += int(n)
                log_detail.append({
                    "table": table,
                    "source_school_id": source_id,
                    "target_school_id": target_id,
                    "rows": int(n),
                })

    no_year_tables = no_year_school_tables_with_source_rows(conn)

    return {
        "direct_tables": direct_tables,
        "direct_target_year_rows": target_year_total,
        "direct_legacy_rows": legacy_total,
        "direct_detail": per_direct,
        "users_rows": int(users_total),
        "business_rows": int(business_total),
        "business_detail": business_detail,
        "log_rows": int(log_total),
        "log_detail": log_detail,
        "no_year_tables": no_year_tables,
    }


def verify_expected_no_year_tables(snapshot: dict) -> None:
    expected_tables = {
        "users",
        "survey_investigation_participants",
        "survey_investigation_team_members",
        "survey_participant_submissions",
        "survey_school_assignments",
        "survey_team_registration_logs",
        "survey_execution_workflow_logs",
    }
    actual = set(snapshot["no_year_tables"])
    extra = sorted(actual - expected_tables)
    missing = sorted(expected_tables - actual)

    if extra:
        raise MigrationAbort(
            "Phat sinh bang school_id khong co school_year_id ngoai V3: "
            + ", ".join(extra)
        )
    if missing:
        raise MigrationAbort(
            "Trang thai DB da khac V3; khong con thay cac bang/no-year co du lieu: "
            + ", ".join(missing)
        )


def verify_v3_counts(snapshot: dict) -> None:
    for key in (
        "direct_target_year_rows",
        "direct_legacy_rows",
        "users_rows",
        "business_rows",
        "log_rows",
    ):
        actual = int(snapshot[key])
        expected = int(EXPECTED[key])
        if actual != expected:
            raise MigrationAbort(
                f"Khoa an toan V3 khong khop: {key}: "
                f"expected={expected}, actual={actual}"
            )


def backup_database() -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"phocap_truoc_sap_nhap_QD3805_Nghi_Loc_{ts}.db"

    src = sqlite3.connect(str(DB_PATH))
    dst = sqlite3.connect(str(backup_path))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()

    check = sqlite3.connect(str(backup_path))
    try:
        integrity = check.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            try:
                backup_path.unlink()
            except Exception:
                pass
            raise MigrationAbort(
                f"Backup tao ra khong dat integrity_check: {integrity}"
            )
    finally:
        check.close()

    return backup_path


def write_csv(path: Path, headers: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def migrate() -> None:
    print("=" * 100)
    print("SAP NHAP THAT QD 3805 - NGHI LOC - V1")
    print("=" * 100)
    print(f"Database: {DB_PATH}")
    print("V1: KHONG DOI TEN TRUONG.")
    print("Nguon se duoc vo hieu hoa bang schools.is_active=0.")
    print()

    if not DB_PATH.exists():
        raise MigrationAbort(f"Khong tim thay database: {DB_PATH}")

    # PRE-FLIGHT tren ket noi doc/ghi nhung CHUA BEGIN thay doi.
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_dir = PROJECT_ROOT / f"sap_nhap_QD3805_Nghi_Loc_{ts}"
    report_dir.mkdir(parents=True, exist_ok=False)

    backup_path = None
    committed = False

    try:
        integrity_before = conn.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity_before != "ok":
            raise MigrationAbort(
                f"Database khong dat integrity_check truoc chuyen: {integrity_before}"
            )

        ok, year_note = school_year_ok(conn)
        if not ok:
            raise MigrationAbort(
                f"Khong xac nhan duoc school_year_id={TARGET_YEAR_ID} la 2026-2027. "
                f"Gia tri: {year_note}"
            )

        ok, school_note = schools_ok(conn)
        if not ok:
            raise MigrationAbort(school_note)

        before = snapshot_counts(conn)
        verify_expected_no_year_tables(before)
        verify_v3_counts(before)

        write_csv(
            report_dir / "01_TRUOC_CHUYEN_BANG_CO_NAM.csv",
            [
                "table", "source_school_id", "target_school_id",
                "target_year_rows", "legacy_rows",
            ],
            before["direct_detail"],
        )
        write_csv(
            report_dir / "02_TRUOC_CHUYEN_40_DONG_NGHIEP_VU.csv",
            [
                "table", "row_id", "source_school_id",
                "target_school_id", "resolved_school_year_id",
            ],
            before["business_detail"],
        )
        write_csv(
            report_dir / "03_TRUOC_CHUYEN_LOG_GIU_NGUYEN.csv",
            ["table", "source_school_id", "target_school_id", "rows"],
            before["log_detail"],
        )

        print("PRE-FLIGHT PASS.")
        print(
            f"  2026-2027 co school_year_id: {before['direct_target_year_rows']} dong"
        )
        print(f"  Lich su nam cu giu nguyen: {before['direct_legacy_rows']} dong")
        print(f"  users chuyen pham vi: {before['users_rows']} dong")
        print(f"  survey_* no-year chuyen: {before['business_rows']} dong")
        print(f"  log giu nguyen: {before['log_rows']} dong")

        # BACKUP truoc khi BEGIN.
        backup_path = backup_database()
        print(f"BACKUP OK: {backup_path}")

        # TRANSACTION THAT.
        conn.execute("BEGIN IMMEDIATE")

        update_log = []

        # A. Cac bang co school_id + school_year_id:
        #    chi chuyen school_year_id=2.
        moved_direct = 0
        for table in before["direct_tables"]:
            for source_id, target_id in MERGE_MAP.items():
                cur = conn.execute(
                    f"UPDATE {qident(table)} SET school_id=? "
                    "WHERE school_id=? AND school_year_id=?",
                    (target_id, source_id, TARGET_YEAR_ID),
                )
                n = max(cur.rowcount, 0)
                if n:
                    moved_direct += n
                    update_log.append({
                        "group": "DIRECT_YEAR",
                        "table": table,
                        "source_school_id": source_id,
                        "target_school_id": target_id,
                        "rows_updated": n,
                    })

        if moved_direct != EXPECTED["direct_target_year_rows"]:
            raise MigrationAbort(
                f"So dong co nam da chuyen sai: {moved_direct} "
                f"!= {EXPECTED['direct_target_year_rows']}"
            )

        # B. users: chuyen pham vi hien tai.
        moved_users = 0
        for source_id, target_id in MERGE_MAP.items():
            cur = conn.execute(
                "UPDATE users SET school_id=? WHERE school_id=?",
                (target_id, source_id),
            )
            n = max(cur.rowcount, 0)
            moved_users += n
            if n:
                update_log.append({
                    "group": "USERS",
                    "table": "users",
                    "source_school_id": source_id,
                    "target_school_id": target_id,
                    "rows_updated": n,
                })

        if moved_users != EXPECTED["users_rows"]:
            raise MigrationAbort(
                f"So users da chuyen sai: {moved_users} "
                f"!= {EXPECTED['users_rows']}"
            )

        # C. 40 dong nghiep vu no-year, dung dung row ID da V3 truy vet.
        moved_business = 0
        by_table_target = defaultdict(list)
        for item in before["business_detail"]:
            by_table_target[(item["table"], item["target_school_id"])].append(
                item["row_id"]
            )

        for (table, target_id), row_ids in by_table_target.items():
            pk = primary_key_column(conn, table)
            cur = conn.execute(
                f"UPDATE {qident(table)} SET school_id=? "
                f"WHERE {qident(pk) if pk != 'rowid' else 'rowid'} "
                f"IN ({markers(len(row_ids))})",
                [target_id] + row_ids,
            )
            n = max(cur.rowcount, 0)
            moved_business += n
            update_log.append({
                "group": "BUSINESS_NO_YEAR",
                "table": table,
                "source_school_id": "V3_ROW_IDS",
                "target_school_id": target_id,
                "rows_updated": n,
            })

        if moved_business != EXPECTED["business_rows"]:
            raise MigrationAbort(
                f"So dong survey_* no-year da chuyen sai: {moved_business} "
                f"!= {EXPECTED['business_rows']}"
            )

        # D. Vo hieu hoa 7 truong nguon.
        cur = conn.execute(
            f"UPDATE schools SET is_active=0 "
            f"WHERE id IN ({markers(len(SOURCE_IDS))}) AND is_active=1",
            SOURCE_IDS,
        )
        deactivated = max(cur.rowcount, 0)
        if deactivated != len(SOURCE_IDS):
            raise MigrationAbort(
                f"So truong nguon vo hieu hoa={deactivated}, "
                f"phai bang {len(SOURCE_IDS)}"
            )

        update_log.append({
            "group": "SCHOOLS",
            "table": "schools",
            "source_school_id": ",".join(map(str, SOURCE_IDS)),
            "target_school_id": "",
            "rows_updated": deactivated,
        })

        # POST-CHECK khi transaction CHUA COMMIT.
        # 1. Khong con dong 2026-2027 o truong nguon trong cac bang co nam.
        remaining_target_year = 0
        for table in before["direct_tables"]:
            n = conn.execute(
                f"SELECT COUNT(*) FROM {qident(table)} "
                f"WHERE school_id IN ({markers(len(SOURCE_IDS))}) "
                "AND school_year_id=?",
                list(SOURCE_IDS) + [TARGET_YEAR_ID],
            ).fetchone()[0]
            remaining_target_year += int(n)
        if remaining_target_year != 0:
            raise MigrationAbort(
                f"Con {remaining_target_year} dong 2026-2027 o truong nguon"
            )

        # 2. Du lieu nam cu tai truong nguon phai van dung 273.
        legacy_after = 0
        for table in before["direct_tables"]:
            n = conn.execute(
                f"SELECT COUNT(*) FROM {qident(table)} "
                f"WHERE school_id IN ({markers(len(SOURCE_IDS))}) "
                "AND (school_year_id IS NULL OR school_year_id<>?)",
                list(SOURCE_IDS) + [TARGET_YEAR_ID],
            ).fetchone()[0]
            legacy_after += int(n)
        if legacy_after != EXPECTED["direct_legacy_rows"]:
            raise MigrationAbort(
                f"Du lieu lich su bi thay doi: sau={legacy_after}, "
                f"truoc={EXPECTED['direct_legacy_rows']}"
            )

        # 3. Khong con users tro den truong nguon.
        remaining_users = conn.execute(
            f"SELECT COUNT(*) FROM users "
            f"WHERE school_id IN ({markers(len(SOURCE_IDS))})",
            SOURCE_IDS,
        ).fetchone()[0]
        if remaining_users != 0:
            raise MigrationAbort(
                f"Con {remaining_users} users tro den truong nguon"
            )

        # 4. 40 row ID phai nam o dung target.
        wrong_business = []
        for item in before["business_detail"]:
            table = item["table"]
            row_id = item["row_id"]
            target_id = item["target_school_id"]
            pk = primary_key_column(conn, table)
            row = conn.execute(
                f"SELECT school_id FROM {qident(table)} "
                f"WHERE {qident(pk) if pk != 'rowid' else 'rowid'}=?",
                (row_id,),
            ).fetchone()
            actual = None if not row else row[0]
            if actual != target_id:
                wrong_business.append((table, row_id, actual, target_id))
        if wrong_business:
            raise MigrationAbort(
                f"Co {len(wrong_business)} dong nghiep vu khong ve dung target"
            )

        # 5. Log lich su phai giu nguyen 7 dong tai source.
        log_after = 0
        for table in LOG_TABLES:
            if not table_exists(conn, table) or "school_id" not in colset(conn, table):
                continue
            log_after += int(conn.execute(
                f"SELECT COUNT(*) FROM {qident(table)} "
                f"WHERE school_id IN ({markers(len(SOURCE_IDS))})",
                SOURCE_IDS,
            ).fetchone()[0])
        if log_after != EXPECTED["log_rows"]:
            raise MigrationAbort(
                f"Log lich su bi thay doi: after={log_after}, "
                f"expected={EXPECTED['log_rows']}"
            )

        # 6. 7 source inactive; tat ca target van active.
        inactive_sources = conn.execute(
            f"SELECT COUNT(*) FROM schools "
            f"WHERE id IN ({markers(len(SOURCE_IDS))}) AND is_active=0",
            SOURCE_IDS,
        ).fetchone()[0]
        active_targets = conn.execute(
            f"SELECT COUNT(*) FROM schools "
            f"WHERE id IN ({markers(len(TARGET_IDS))}) AND is_active=1",
            TARGET_IDS,
        ).fetchone()[0]
        if inactive_sources != len(SOURCE_IDS):
            raise MigrationAbort(
                f"Khong du 7 truong nguon inactive: {inactive_sources}"
            )
        if active_targets != len(TARGET_IDS):
            raise MigrationAbort(
                f"Khong du truong dich active: {active_targets}/{len(TARGET_IDS)}"
            )

        # 7. FK.
        fk_rows = conn.execute("PRAGMA foreign_key_check").fetchall()
        if fk_rows:
            raise MigrationAbort(
                f"foreign_key_check co {len(fk_rows)} loi"
            )

        # Neu tat ca PASS -> COMMIT.
        conn.commit()
        committed = True

        # integrity_check sau COMMIT.
        integrity_after = conn.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity_after != "ok":
            # Da commit, khong the transaction rollback nua.
            # Backup van con nguyen de khoi phuc thu cong.
            raise MigrationAbort(
                "CANH BAO NGHIEM TRONG: da COMMIT nhung integrity_check sau "
                f"commit={integrity_after}. Backup: {backup_path}"
            )

        # Bao cao.
        write_csv(
            report_dir / "10_CAC_UPDATE_DA_THUC_HIEN.csv",
            [
                "group", "table", "source_school_id",
                "target_school_id", "rows_updated",
            ],
            update_log,
        )

        # Trang thai truong sau chuyen.
        school_rows = conn.execute(
            f"SELECT id, code, name, commune_id, is_active "
            f"FROM schools WHERE id IN "
            f"({markers(len(set(SOURCE_IDS) | set(TARGET_IDS)))}) "
            "ORDER BY id",
            sorted(set(SOURCE_IDS) | set(TARGET_IDS)),
        ).fetchall()
        school_report = [
            {
                "id": r[0],
                "code": r[1],
                "name": r[2],
                "commune_id": r[3],
                "is_active": r[4],
                "role": "SOURCE_DISABLED" if r[0] in SOURCE_IDS else "TARGET_ACTIVE",
            }
            for r in school_rows
        ]
        write_csv(
            report_dir / "11_TRANG_THAI_TRUONG_SAU_CHUYEN.csv",
            ["id", "code", "name", "commune_id", "is_active", "role"],
            school_report,
        )

        summary_path = report_dir / "00_KET_QUA_SAP_NHAP.txt"
        with summary_path.open("w", encoding="utf-8") as f:
            f.write("KET QUA SAP NHAP THAT QD 3805 - NGHI LOC - V1\n")
            f.write("=" * 90 + "\n")
            f.write("STATUS = SUCCESS\n")
            f.write(f"Database: {DB_PATH}\n")
            f.write(f"Backup: {backup_path}\n")
            f.write(f"school_year_id muc tieu: {TARGET_YEAR_ID} (2026-2027)\n\n")
            f.write(f"- Dong co nam 2026-2027 da chuyen: {moved_direct}\n")
            f.write(f"- Dong lich su nam cu giu nguyen o source: {legacy_after}\n")
            f.write(f"- users da chuyen: {moved_users}\n")
            f.write(f"- dong survey_* no-year da chuyen: {moved_business}\n")
            f.write(f"- dong log lich su giu nguyen: {log_after}\n")
            f.write(f"- truong nguon da is_active=0: {inactive_sources}\n")
            f.write(f"- truong dich van is_active=1: {active_targets}\n")
            f.write("- foreign_key_check: PASS (0 loi)\n")
            f.write(f"- integrity_check sau commit: {integrity_after}\n")
            f.write("- DOI TEN TRUONG: KHONG THUC HIEN TRONG V1\n")

        zip_path = PROJECT_ROOT / f"sap_nhap_QD3805_Nghi_Loc_KET_QUA_{ts}.zip"
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for p in sorted(report_dir.iterdir()):
                zf.write(p, arcname=p.name)

        print()
        print("=" * 100)
        print("SAP NHAP THANH CONG")
        print("=" * 100)
        print(f"Backup: {backup_path}")
        print(f"Bao cao ZIP: {zip_path}")
        print(f"Da chuyen 2026-2027: {moved_direct} dong co nam + {moved_business} dong survey_*")
        print(f"Da chuyen users: {moved_users}")
        print(f"Da giu du lieu nam cu: {legacy_after}")
        print(f"Da giu log lich su: {log_after}")
        print(f"Da vo hieu hoa {inactive_sources} truong nguon")
        print("Khong doi ten truong trong V1.")
        print("foreign_key_check: PASS")
        print("integrity_check: PASS")
        print()
        print("GUI LAI FILE ZIP KET QUA CHO TOI DE DOI CHIEU SAU SAP NHAP.")

    except Exception:
        if not committed:
            try:
                conn.rollback()
            except Exception:
                pass
        raise
    finally:
        conn.close()


def main() -> None:
    try:
        migrate()
    except MigrationAbort as e:
        print()
        print("=" * 100)
        print("DA DUNG - KHONG CHUYEN / HOAC DA ROLLBACK")
        print("=" * 100)
        print(str(e))
        print("Database goc khong duoc phep tiep tuc thay doi trong tinh huong nay.")
        print("Neu backup da duoc tao, backup van duoc giu nguyen.")
        sys.exit(2)
    except sqlite3.IntegrityError as e:
        print()
        print("=" * 100)
        print("LOI UNIQUE / FOREIGN KEY - DA ROLLBACK")
        print("=" * 100)
        print(repr(e))
        sys.exit(3)
    except sqlite3.Error as e:
        print()
        print("=" * 100)
        print("LOI SQLITE - DA ROLLBACK NEU CHUA COMMIT")
        print("=" * 100)
        print(repr(e))
        sys.exit(4)
    except Exception as e:
        print()
        print("=" * 100)
        print("LOI KHONG DU KIEN")
        print("=" * 100)
        print(repr(e))
        print("Neu loi xay ra truoc COMMIT thi transaction da rollback.")
        sys.exit(5)


if __name__ == "__main__":
    main()
