# -*- coding: utf-8 -*-
r"""
V11 CHÍNH THỨC - CHỐT SÁP NHẬP QĐ 3805
========================================

MỤC TIÊU
--------
Khóa phần sáp nhập QĐ 3805 trong một lần chạy:

1. PRE-FLIGHT
   - integrity_check
   - foreign_key_check
   - xác định đúng năm 2026-2027 (CURRENT) và 2027-2028 (FUTURE)
   - xác nhận đúng 7 trường nguồn / 6 trường đích
   - xác nhận nguồn đã inactive, đích active
   - quét tất cả bảng có school_id + school_year_id
   - CURRENT residual tại trường nguồn phải = 0
   - FUTURE residual chỉ được phép đúng 3 lớp:
       TH Nghi Hoa (1180) -> TH Nghi Trung (1179)
       năm 2027-2028
       class id 16,17,18
       1A,1B,1C
   - kiểm tra mọi FK tham chiếu tới 3 class id này
   - kiểm tra xung đột ở trường đích

2. BACKUP
   - tạo backup DB trước sửa trong C:\PhoCap\backups

3. SỬA CHÍNH THỨC
   - giữ nguyên class id
   - giữ nguyên school_year_id
   - chỉ đổi classes.school_id:
       1180 -> 1179
     cho đúng 3 lớp FUTURE 2027-2028

4. HẬU KIỂM NGAY TRONG CÙNG LẦN CHẠY
   - CURRENT residual tại source = 0
   - FUTURE residual tại source = 0
   - 3 lớp đã thuộc TH Nghi Trung
   - integrity_check = ok
   - foreign_key_check = 0
   - 7 source school login vẫn khóa
   - CBQL/GV không bị kẹt ở source
   - không chạm dữ liệu học sinh đối chiếu 2025-2026
   - không chạm dữ liệu test học sinh 2026-2027

5. AN TOÀN
   - transaction
   - nếu lỗi trước COMMIT: rollback
   - nếu lỗi hậu kiểm sau COMMIT: restore DB từ backup bằng SQLite Backup API

KẾT LUẬN CUỐI
--------------
QD3805_MERGER_CLOSED = YES/NO

CHẠY
----
    cd C:\PhoCap
    .\.venv\Scripts\python.exe .\chot_sap_nhap_QD3805_v11.py
"""

from __future__ import annotations

import csv
import re
import shutil
import sqlite3
import sys
import zipfile
from datetime import datetime
from pathlib import Path


ROOT = Path(r"C:\PhoCap")
DB_PATH = ROOT / "data" / "phocap.db"
BACKUP_DIR = ROOT / "backups"

CURRENT_START = 2026

MERGE_MAP = {
    750: 748,    # MN Nghi Hoa -> MN Nghi Dien
    751: 748,    # MN Nghi Van -> MN Nghi Dien
    749: 747,    # MN Nghi Trung -> MN TT Quan Hanh
    1181: 1178,  # TH Nghi Van -> TH Nghi Dien
    1180: 1179,  # TH Nghi Hoa -> TH Nghi Trung
    1608: 1605,  # THCS Nghi Van -> THCS Nghi Dien
    1607: 1606,  # THCS Nghi Hoa -> THCS Nghi Trung
}

SOURCE_IDS = sorted(MERGE_MAP)
TARGET_IDS = sorted(set(MERGE_MAP.values()))
ALL_QD_IDS = sorted(set(SOURCE_IDS) | set(TARGET_IDS))

EXPECTED_FUTURE_FIX = {
    "source_school_id": 1180,
    "target_school_id": 1179,
    "year_start": 2027,
    "class_ids": [16, 17, 18],
    "class_names": ["1A", "1B", "1C"],
}


class StopInstall(RuntimeError):
    pass


def qident(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def markers(n: int) -> str:
    return ",".join("?" for _ in range(n))


def write_csv(path: Path, headers: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def table_exists(con: sqlite3.Connection, table: str) -> bool:
    return con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone() is not None


def all_tables(con: sqlite3.Connection) -> list[str]:
    return [
        str(r[0])
        for r in con.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' "
            "ORDER BY name"
        ).fetchall()
    ]


def colset(con: sqlite3.Connection, table: str) -> set[str]:
    return {
        str(r[1])
        for r in con.execute(
            f"PRAGMA table_info({qident(table)})"
        ).fetchall()
    }


def scalar(con: sqlite3.Connection, sql: str, params=()) -> int:
    row = con.execute(sql, params).fetchone()
    return int(row[0] or 0) if row else 0


def parse_year_start(value) -> int | None:
    s = str(value or "")
    m = re.search(r"(20\d{2})\D{0,8}(20\d{2})", s)
    if not m:
        return None
    a = int(m.group(1))
    b = int(m.group(2))
    if b == a + 1:
        return a
    return None


def school_years(con: sqlite3.Connection) -> dict[int, dict]:
    if not table_exists(con, "school_years"):
        raise StopInstall("Không có bảng school_years.")

    cs = colset(con, "school_years")
    text_cols = [
        c for c in (
            "code", "name", "label", "school_year", "year_name",
            "start_year", "end_year"
        )
        if c in cs
    ]
    if not text_cols:
        raise StopInstall("Không xác định được cột năm học.")

    select = ["id"] + [qident(c) for c in text_cols]
    rows = con.execute(
        "SELECT " + ",".join(select) + " FROM school_years ORDER BY id"
    ).fetchall()

    result = {}
    for r in rows:
        joined = " | ".join(str(r[c] or "") for c in text_cols)
        ystart = None

        if "start_year" in cs:
            try:
                val = int(r["start_year"])
                if 2000 <= val <= 2100:
                    ystart = val
            except Exception:
                pass

        if ystart is None:
            ystart = parse_year_start(joined)

        if ystart is None:
            temporal = "UNKNOWN"
        elif ystart < CURRENT_START:
            temporal = "PAST"
        elif ystart == CURRENT_START:
            temporal = "CURRENT"
        else:
            temporal = "FUTURE"

        result[int(r["id"])] = {
            "id": int(r["id"]),
            "text": joined,
            "year_start": ystart,
            "temporal": temporal,
        }
    return result


def find_year_id(years: dict[int, dict], start: int) -> int:
    matches = [
        yid for yid, y in years.items()
        if y["year_start"] == start
    ]
    if len(matches) != 1:
        raise StopInstall(
            f"Không xác định duy nhất năm bắt đầu {start}: {matches}"
        )
    return matches[0]


def get_schools(con: sqlite3.Connection) -> dict[int, dict]:
    if not table_exists(con, "schools"):
        raise StopInstall("Không có bảng schools.")

    cs = colset(con, "schools")
    name_col = next(
        (c for c in ("name", "school_name", "ten_truong") if c in cs),
        None,
    )
    if not name_col:
        raise StopInstall("Không xác định được tên trường.")

    rows = con.execute(
        f"SELECT id,{qident(name_col)} AS name,"
        + ("is_active" if "is_active" in cs else "NULL AS is_active")
        + f" FROM schools WHERE id IN ({markers(len(ALL_QD_IDS))})",
        ALL_QD_IDS,
    ).fetchall()

    return {
        int(r["id"]): {
            "name": str(r["name"] or ""),
            "is_active": r["is_active"],
        }
        for r in rows
    }


def scan_temporal_residuals(
    con: sqlite3.Connection,
    years: dict[int, dict],
) -> list[dict]:
    rows = []

    for table in all_tables(con):
        cs = colset(con, table)
        if not {"school_id", "school_year_id"} <= cs:
            continue

        sql = (
            f"SELECT school_id,school_year_id,COUNT(*) AS n "
            f"FROM {qident(table)} "
            f"WHERE school_id IN ({markers(len(SOURCE_IDS))}) "
            "GROUP BY school_id,school_year_id "
            "ORDER BY school_id,school_year_id"
        )
        for r in con.execute(sql, SOURCE_IDS).fetchall():
            yid = int(r["school_year_id"])
            y = years.get(yid, {
                "year_start": None,
                "temporal": "UNKNOWN",
                "text": "",
            })
            rows.append({
                "table": table,
                "school_id": int(r["school_id"]),
                "school_year_id": yid,
                "year_start": y["year_start"],
                "year_text": y["text"],
                "temporal": y["temporal"],
                "rows": int(r["n"]),
            })
    return rows


def get_class_rows(
    con: sqlite3.Connection,
    class_ids: list[int],
) -> list[dict]:
    rows = con.execute(
        f"""
        SELECT id,school_id,school_year_id,code,name,is_active
        FROM classes
        WHERE id IN ({markers(len(class_ids))})
        ORDER BY id
        """,
        class_ids,
    ).fetchall()
    return [
        {
            "id": int(r["id"]),
            "school_id": int(r["school_id"]),
            "school_year_id": int(r["school_year_id"]),
            "code": r["code"],
            "name": str(r["name"] or ""),
            "is_active": r["is_active"],
        }
        for r in rows
    ]


def referencing_foreign_keys(
    con: sqlite3.Connection,
    ref_table: str,
    ref_column: str = "id",
) -> list[dict]:
    result = []
    for table in all_tables(con):
        for r in con.execute(
            f"PRAGMA foreign_key_list({qident(table)})"
        ).fetchall():
            # id, seq, table, from, to, on_update, on_delete, match
            if str(r[2]) == ref_table and str(r[4]) == ref_column:
                result.append({
                    "table": table,
                    "from_column": str(r[3]),
                    "to_table": str(r[2]),
                    "to_column": str(r[4]),
                    "on_update": str(r[5]),
                    "on_delete": str(r[6]),
                })
    return result


def count_refs_to_class_ids(
    con: sqlite3.Connection,
    class_ids: list[int],
) -> list[dict]:
    refs = []
    for fk in referencing_foreign_keys(con, "classes", "id"):
        table = fk["table"]
        col = fk["from_column"]
        n = scalar(
            con,
            f"SELECT COUNT(*) FROM {qident(table)} "
            f"WHERE {qident(col)} IN ({markers(len(class_ids))})",
            class_ids,
        )
        refs.append({
            **fk,
            "rows_referencing_expected_classes": n,
        })
    return refs


def backup_db(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)

    s = sqlite3.connect(str(src))
    d = sqlite3.connect(str(dst))
    try:
        s.backup(d)
        d.commit()
    finally:
        d.close()
        s.close()

    # Verify backup.
    b = sqlite3.connect(str(dst))
    try:
        integrity = b.execute("PRAGMA integrity_check").fetchone()[0]
        fk = b.execute("PRAGMA foreign_key_check").fetchall()
        if integrity != "ok" or fk:
            raise StopInstall(
                f"Backup không đạt kiểm tra: integrity={integrity}, FK={len(fk)}"
            )
    finally:
        b.close()


def restore_db(backup: Path, target: Path) -> None:
    s = sqlite3.connect(str(backup))
    d = sqlite3.connect(str(target))
    try:
        s.backup(d)
        d.commit()
    finally:
        d.close()
        s.close()


def source_school_login_audit(con: sqlite3.Connection) -> dict:
    result = {
        "available": False,
        "locked_school_logins": None,
        "active_school_logins": None,
        "cbql_gv_at_source": None,
    }

    if not table_exists(con, "users"):
        return result

    cs = colset(con, "users")
    if not {"school_id", "is_active"} <= cs:
        return result

    result["available"] = True

    # School logins are known to start with truong_.
    if "username" in cs:
        result["locked_school_logins"] = scalar(
            con,
            f"""
            SELECT COUNT(*) FROM users
            WHERE school_id IN ({markers(len(SOURCE_IDS))})
              AND username LIKE 'truong_%'
              AND is_active=0
            """,
            SOURCE_IDS,
        )
        result["active_school_logins"] = scalar(
            con,
            f"""
            SELECT COUNT(*) FROM users
            WHERE school_id IN ({markers(len(SOURCE_IDS))})
              AND username LIKE 'truong_%'
              AND is_active=1
            """,
            SOURCE_IDS,
        )

        # Known CBQL/GV usernames.
        result["cbql_gv_at_source"] = scalar(
            con,
            f"""
            SELECT COUNT(*) FROM users
            WHERE school_id IN ({markers(len(SOURCE_IDS))})
              AND (username LIKE 'cbql.%' OR username LIKE 'gv.%')
            """,
            SOURCE_IDS,
        )

    return result


def main() -> None:
    print("=" * 130)
    print("V11 CHÍNH THỨC - CHỐT SÁP NHẬP QĐ 3805")
    print("=" * 130)

    if not DB_PATH.exists():
        raise StopInstall(f"Không tìm thấy DB: {DB_PATH}")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    backup_path = BACKUP_DIR / f"phocap_truoc_chot_QD3805_v11_{ts}.db"
    report_dir = ROOT / f"bao_cao_chot_QD3805_v11_{ts}"
    report_dir.mkdir(parents=True, exist_ok=False)
    report_zip = ROOT / f"bao_cao_chot_QD3805_v11_{ts}.zip"

    con = sqlite3.connect(str(DB_PATH))
    con.row_factory = sqlite3.Row
    committed = False
    restored = False

    try:
        print("[1/7] PRE-FLIGHT database...")
        integrity_before = con.execute("PRAGMA integrity_check").fetchone()[0]
        fk_before = con.execute("PRAGMA foreign_key_check").fetchall()

        if integrity_before != "ok":
            raise StopInstall(f"integrity_check trước sửa = {integrity_before}")
        if fk_before:
            raise StopInstall(f"foreign_key_check trước sửa = {len(fk_before)} lỗi")

        years = school_years(con)
        current_year_id = find_year_id(years, 2026)
        future_year_id = find_year_id(years, 2027)

        schools = get_schools(con)
        missing_schools = sorted(set(ALL_QD_IDS) - set(schools))
        if missing_schools:
            raise StopInstall(f"Thiếu school_id QĐ3805: {missing_schools}")

        school_state_rows = []
        school_state_errors = []

        for sid in ALL_QD_IDS:
            expected_active = 0 if sid in SOURCE_IDS else 1
            actual = schools[sid]["is_active"]
            ok = actual in (expected_active, bool(expected_active))
            if not ok:
                school_state_errors.append(
                    f"{sid} {schools[sid]['name']}: active={actual}, expected={expected_active}"
                )
            school_state_rows.append({
                "school_id": sid,
                "school_name": schools[sid]["name"],
                "role": "SOURCE" if sid in SOURCE_IDS else "TARGET",
                "is_active": actual,
                "expected_active": expected_active,
                "check": "PASS" if ok else "FAIL",
            })

        if school_state_errors:
            raise StopInstall(
                "Trạng thái trường QĐ3805 không đúng:\n- "
                + "\n- ".join(school_state_errors)
            )

        residuals_before = scan_temporal_residuals(con, years)

        current_residual = sum(
            r["rows"] for r in residuals_before
            if r["temporal"] == "CURRENT"
        )
        future_residual_rows = [
            r for r in residuals_before
            if r["temporal"] == "FUTURE"
        ]
        future_residual = sum(r["rows"] for r in future_residual_rows)
        unknown_residual = sum(
            r["rows"] for r in residuals_before
            if r["temporal"] == "UNKNOWN"
        )

        if current_residual != 0:
            raise StopInstall(
                f"CURRENT residual tại source phải = 0, hiện = {current_residual}"
            )
        if unknown_residual != 0:
            raise StopInstall(
                f"UNKNOWN-year residual tại source phải = 0, hiện = {unknown_residual}"
            )

        # Chỉ chấp nhận đúng 3 classes FUTURE.
        allowed_future_signature = [
            r for r in future_residual_rows
            if r["table"] == "classes"
            and r["school_id"] == EXPECTED_FUTURE_FIX["source_school_id"]
            and r["school_year_id"] == future_year_id
            and r["rows"] == 3
        ]

        if future_residual != 3 or len(future_residual_rows) != 1 or len(allowed_future_signature) != 1:
            raise StopInstall(
                "FUTURE residual không còn đúng tình trạng đã chốt. "
                f"total={future_residual}; detail={future_residual_rows}"
            )

        expected_class_ids = EXPECTED_FUTURE_FIX["class_ids"]
        class_rows_before = get_class_rows(con, expected_class_ids)

        if len(class_rows_before) != 3:
            raise StopInstall(
                f"Không tìm đủ 3 class id {expected_class_ids}. "
                f"Thực tế={class_rows_before}"
            )

        actual_ids = [r["id"] for r in class_rows_before]
        actual_names = [r["name"] for r in class_rows_before]

        if actual_ids != expected_class_ids:
            raise StopInstall(f"Class IDs thay đổi: {actual_ids}")

        if actual_names != EXPECTED_FUTURE_FIX["class_names"]:
            raise StopInstall(
                f"Tên lớp thay đổi: {actual_names} != {EXPECTED_FUTURE_FIX['class_names']}"
            )

        for r in class_rows_before:
            if r["school_id"] != EXPECTED_FUTURE_FIX["source_school_id"]:
                raise StopInstall(
                    f"Class {r['id']} không còn ở source 1180: {r}"
                )
            if r["school_year_id"] != future_year_id:
                raise StopInstall(
                    f"Class {r['id']} không thuộc năm 2027-2028: {r}"
                )

        # Target conflict check.
        target_conflicts = con.execute(
            f"""
            SELECT id,school_id,school_year_id,code,name
            FROM classes
            WHERE school_id=?
              AND school_year_id=?
              AND (
                    name IN ({markers(len(EXPECTED_FUTURE_FIX["class_names"]))})
                    OR id IN ({markers(len(expected_class_ids))})
              )
            ORDER BY id
            """,
            [
                EXPECTED_FUTURE_FIX["target_school_id"],
                future_year_id,
                *EXPECTED_FUTURE_FIX["class_names"],
                *expected_class_ids,
            ],
        ).fetchall()

        if target_conflicts:
            raise StopInstall(
                "Đích TH Nghi Trung đã có lớp xung đột 2027-2028: "
                + repr([dict(r) for r in target_conflicts])
            )

        class_ref_rows = count_refs_to_class_ids(con, expected_class_ids)

        # References are okay if they exist, because class IDs stay unchanged.
        # But record them so we know what follows automatically.
        print(
            f"    CURRENT residual source: {current_residual}"
        )
        print(
            f"    FUTURE residual source: {future_residual} "
            "(đúng 3 lớp TH Nghi Hoa 2027-2028)"
        )

        print("[2/7] BACKUP database...")
        backup_db(DB_PATH, backup_path)
        print(f"    Backup: {backup_path}")

        print("[3/7] GHI TRANSACTION chính thức...")
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("BEGIN IMMEDIATE")

        cur = con.execute(
            f"""
            UPDATE classes
            SET school_id=?
            WHERE school_id=?
              AND school_year_id=?
              AND id IN ({markers(len(expected_class_ids))})
            """,
            [
                EXPECTED_FUTURE_FIX["target_school_id"],
                EXPECTED_FUTURE_FIX["source_school_id"],
                future_year_id,
                *expected_class_ids,
            ],
        )

        if cur.rowcount != 3:
            con.rollback()
            raise StopInstall(
                f"UPDATE classes phải sửa đúng 3 dòng, thực tế={cur.rowcount}"
            )

        # Before commit, verify in transaction.
        moved_now = scalar(
            con,
            f"""
            SELECT COUNT(*) FROM classes
            WHERE school_id=?
              AND school_year_id=?
              AND id IN ({markers(len(expected_class_ids))})
            """,
            [
                EXPECTED_FUTURE_FIX["target_school_id"],
                future_year_id,
                *expected_class_ids,
            ],
        )
        source_left_now = scalar(
            con,
            f"""
            SELECT COUNT(*) FROM classes
            WHERE school_id=?
              AND school_year_id=?
              AND id IN ({markers(len(expected_class_ids))})
            """,
            [
                EXPECTED_FUTURE_FIX["source_school_id"],
                future_year_id,
                *expected_class_ids,
            ],
        )

        if moved_now != 3 or source_left_now != 0:
            con.rollback()
            raise StopInstall(
                f"Pre-commit check thất bại: moved={moved_now}, source_left={source_left_now}"
            )

        con.commit()
        committed = True
        print("    COMMIT: OK")

        print("[4/7] HẬU KIỂM temporal...")
        residuals_after = scan_temporal_residuals(con, years)

        current_after = sum(
            r["rows"] for r in residuals_after
            if r["temporal"] == "CURRENT"
        )
        future_after = sum(
            r["rows"] for r in residuals_after
            if r["temporal"] == "FUTURE"
        )
        unknown_after = sum(
            r["rows"] for r in residuals_after
            if r["temporal"] == "UNKNOWN"
        )

        if current_after != 0:
            raise StopInstall(f"Postcheck CURRENT residual={current_after}")
        if future_after != 0:
            raise StopInstall(f"Postcheck FUTURE residual={future_after}")
        if unknown_after != 0:
            raise StopInstall(f"Postcheck UNKNOWN residual={unknown_after}")

        class_rows_after = get_class_rows(con, expected_class_ids)
        if any(
            r["school_id"] != EXPECTED_FUTURE_FIX["target_school_id"]
            or r["school_year_id"] != future_year_id
            for r in class_rows_after
        ):
            raise StopInstall(
                f"3 lớp chưa nằm đúng đích sau commit: {class_rows_after}"
            )

        print("[5/7] HẬU KIỂM tài khoản trường...")
        account_audit = source_school_login_audit(con)

        if account_audit["available"]:
            # Exact desired state from completed QĐ3805:
            # 7 source school login accounts retained but locked.
            if account_audit["locked_school_logins"] != 7:
                raise StopInstall(
                    "Số school login khóa tại source phải = 7, hiện = "
                    f"{account_audit['locked_school_logins']}"
                )
            if account_audit["active_school_logins"] != 0:
                raise StopInstall(
                    "Còn school login active tại source: "
                    f"{account_audit['active_school_logins']}"
                )
            if account_audit["cbql_gv_at_source"] != 0:
                raise StopInstall(
                    "Còn CBQL/GV tại source: "
                    f"{account_audit['cbql_gv_at_source']}"
                )

        print("[6/7] HẬU KIỂM integrity / FK...")
        integrity_after = con.execute("PRAGMA integrity_check").fetchone()[0]
        fk_after = con.execute("PRAGMA foreign_key_check").fetchall()

        if integrity_after != "ok":
            raise StopInstall(
                f"Post integrity_check={integrity_after}"
            )
        if fk_after:
            raise StopInstall(
                f"Post foreign_key_check={len(fk_after)} lỗi"
            )

        # Student baseline/test must NOT be touched.
        student_counts = []
        for table in ("students", "student_enrollments"):
            if table_exists(con, table):
                student_counts.append({
                    "table": table,
                    "rows_after": scalar(
                        con, f"SELECT COUNT(*) FROM {qident(table)}"
                    ),
                    "note": "V11 không INSERT/UPDATE/DELETE bảng này.",
                })

        print("[7/7] GHI BÁO CÁO chốt...")

        write_csv(
            report_dir / "600_SCHOOL_STATE.csv",
            [
                "school_id", "school_name", "role", "is_active",
                "expected_active", "check",
            ],
            school_state_rows,
        )

        write_csv(
            report_dir / "601_TEMPORAL_RESIDUAL_BEFORE.csv",
            [
                "table", "school_id", "school_year_id",
                "year_start", "year_text", "temporal", "rows",
            ],
            residuals_before,
        )

        write_csv(
            report_dir / "602_CLASS_FIX_BEFORE.csv",
            [
                "id", "school_id", "school_year_id",
                "code", "name", "is_active",
            ],
            class_rows_before,
        )

        write_csv(
            report_dir / "603_CLASS_FOREIGN_KEY_REFERENCES.csv",
            [
                "table", "from_column", "to_table", "to_column",
                "on_update", "on_delete",
                "rows_referencing_expected_classes",
            ],
            class_ref_rows,
        )

        write_csv(
            report_dir / "604_CLASS_FIX_AFTER.csv",
            [
                "id", "school_id", "school_year_id",
                "code", "name", "is_active",
            ],
            class_rows_after,
        )

        write_csv(
            report_dir / "605_TEMPORAL_RESIDUAL_AFTER.csv",
            [
                "table", "school_id", "school_year_id",
                "year_start", "year_text", "temporal", "rows",
            ],
            residuals_after,
        )

        write_csv(
            report_dir / "606_STUDENT_TABLE_COUNTS_UNTOUCHED.csv",
            ["table", "rows_after", "note"],
            student_counts,
        )

        gate_rows = [
            {
                "check": "pre_integrity",
                "result": "PASS",
                "detail": str(integrity_before),
            },
            {
                "check": "pre_fk",
                "result": "PASS",
                "detail": str(len(fk_before)),
            },
            {
                "check": "current_residual_before",
                "result": "PASS",
                "detail": str(current_residual),
            },
            {
                "check": "future_residual_before",
                "result": "EXPECTED_FIX",
                "detail": str(future_residual),
            },
            {
                "check": "classes_moved_1180_to_1179",
                "result": "PASS",
                "detail": "3",
            },
            {
                "check": "current_residual_after",
                "result": "PASS",
                "detail": str(current_after),
            },
            {
                "check": "future_residual_after",
                "result": "PASS",
                "detail": str(future_after),
            },
            {
                "check": "unknown_residual_after",
                "result": "PASS",
                "detail": str(unknown_after),
            },
            {
                "check": "locked_source_school_logins",
                "result": (
                    "PASS"
                    if not account_audit["available"]
                    or account_audit["locked_school_logins"] == 7
                    else "FAIL"
                ),
                "detail": str(account_audit["locked_school_logins"]),
            },
            {
                "check": "active_source_school_logins",
                "result": (
                    "PASS"
                    if not account_audit["available"]
                    or account_audit["active_school_logins"] == 0
                    else "FAIL"
                ),
                "detail": str(account_audit["active_school_logins"]),
            },
            {
                "check": "cbql_gv_at_source",
                "result": (
                    "PASS"
                    if not account_audit["available"]
                    or account_audit["cbql_gv_at_source"] == 0
                    else "FAIL"
                ),
                "detail": str(account_audit["cbql_gv_at_source"]),
            },
            {
                "check": "post_integrity",
                "result": "PASS",
                "detail": str(integrity_after),
            },
            {
                "check": "post_fk",
                "result": "PASS",
                "detail": str(len(fk_after)),
            },
            {
                "check": "student_baseline_imported_by_v11",
                "result": "NO",
                "detail": (
                    "Đúng chủ trương mới: dữ liệu học sinh đối chiếu sẽ nạp sau theo xã/phường."
                ),
            },
            {
                "check": "QD3805_MERGER_CLOSED",
                "result": "YES",
                "detail": (
                    "CURRENT/FUTURE residual tại source = 0; "
                    "3 lớp 2027-2028 đã về TH Nghi Trung; FK/integrity PASS."
                ),
            },
        ]

        write_csv(
            report_dir / "607_GATE_V11.csv",
            ["check", "result", "detail"],
            gate_rows,
        )

        (report_dir / "00_TONG_QUAN_V11.txt").write_text(
            f"""V11 CHÍNH THỨC - CHỐT SÁP NHẬP QĐ 3805
============================================================

Backup:
{backup_path}

PRE:
- integrity = {integrity_before}
- FK errors = {len(fk_before)}
- CURRENT residual tại source = {current_residual}
- FUTURE residual tại source = {future_residual}
- FUTURE residual được phép = đúng 3 lớp TH Nghi Hoa 2027-2028

THAY ĐỔI:
- classes id 16,17,18
- giữ nguyên year = 2027-2028
- giữ nguyên class id
- giữ nguyên tên lớp 1A,1B,1C
- school_id 1180 (TH Nghi Hoa) -> 1179 (TH Nghi Trung)

POST:
- CURRENT residual tại source = {current_after}
- FUTURE residual tại source = {future_after}
- UNKNOWN residual tại source = {unknown_after}
- integrity = {integrity_after}
- FK errors = {len(fk_after)}
- locked source school logins = {account_audit["locked_school_logins"]}
- active source school logins = {account_audit["active_school_logins"]}
- CBQL/GV at source = {account_audit["cbql_gv_at_source"]}

DỮ LIỆU HỌC SINH:
- V11 KHÔNG nạp baseline học sinh 2025-2026.
- V11 KHÔNG sửa dữ liệu học sinh test 2026-2027.
- Nguồn học sinh sẽ được xây chức năng nạp riêng theo xã/phường.

QD3805_MERGER_CLOSED = YES
""",
            encoding="utf-8",
        )

        with zipfile.ZipFile(
            report_zip,
            "w",
            compression=zipfile.ZIP_DEFLATED,
        ) as zf:
            for p in sorted(report_dir.iterdir()):
                zf.write(p, arcname=p.name)

        print()
        print("=" * 130)
        print("HOÀN THÀNH V11 - QĐ3805 ĐÃ ĐƯỢC CHỐT")
        print("=" * 130)
        print("Classes moved: 3")
        print("TH Nghi Hoa -> TH Nghi Trung")
        print("Năm: 2027-2028")
        print(f"CURRENT residual source: {current_after}")
        print(f"FUTURE residual source: {future_after}")
        print(f"Integrity: {integrity_after}")
        print(f"FK errors: {len(fk_after)}")
        print("Student baseline import: KHÔNG")
        print("Student test data 2026-2027: KHÔNG CHẠM")
        print("QD3805_MERGER_CLOSED: YES")
        print(f"BACKUP: {backup_path}")
        print(f"ZIP: {report_zip}")

    except Exception as exc:
        try:
            con.rollback()
        except Exception:
            pass

        if committed and backup_path.exists():
            try:
                con.close()
            except Exception:
                pass
            restore_db(backup_path, DB_PATH)
            restored = True

        print()
        print("=" * 130)
        print("V11 DỪNG - KHÔNG CHỐT QĐ3805")
        print("=" * 130)
        print(repr(exc))
        if committed:
            print(
                "Đã có COMMIT trước khi lỗi hậu kiểm. "
                + ("ĐÃ RESTORE từ backup." if restored else "RESTORE KHÔNG THÀNH CÔNG.")
            )
        else:
            print("Chưa COMMIT thay đổi DB.")
        if backup_path.exists():
            print(f"BACKUP: {backup_path}")
        print("QD3805_MERGER_CLOSED: NO")
        sys.exit(2)

    finally:
        try:
            con.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
