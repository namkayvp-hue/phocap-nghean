# -*- coding: utf-8 -*-
r"""
V11.1 CHÍNH THỨC - CHỐT SÁP NHẬP QĐ 3805
==========================================

Khác V11:
- Chấp nhận 2 trạng thái hợp lệ:
  A) Còn đúng 3 lớp FUTURE 2027-2028 ở TH Nghi Hoa -> tự chuyển sang TH Nghi Trung.
  B) FUTURE residual tại source = 0 -> kiểm tra 3 lớp đã nằm đúng ở TH Nghi Trung,
     nếu đúng thì SKIP MOVE và chỉ hậu kiểm/chốt.

Không nạp học sinh baseline.
Không chạm dữ liệu học sinh test 2026-2027.
"""

from __future__ import annotations

import csv
import re
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
    750: 748,
    751: 748,
    749: 747,
    1181: 1178,
    1180: 1179,
    1608: 1605,
    1607: 1606,
}

SOURCE_IDS = sorted(MERGE_MAP)
TARGET_IDS = sorted(set(MERGE_MAP.values()))
ALL_QD_IDS = sorted(set(SOURCE_IDS) | set(TARGET_IDS))

EXPECTED = {
    "source_school_id": 1180,
    "target_school_id": 1179,
    "future_year_start": 2027,
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


def table_exists(con, table: str) -> bool:
    return con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone() is not None


def all_tables(con) -> list[str]:
    return [
        str(r[0])
        for r in con.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' "
            "ORDER BY name"
        ).fetchall()
    ]


def colset(con, table: str) -> set[str]:
    return {
        str(r[1])
        for r in con.execute(
            f"PRAGMA table_info({qident(table)})"
        ).fetchall()
    }


def scalar(con, sql: str, params=()) -> int:
    row = con.execute(sql, params).fetchone()
    return int(row[0] or 0) if row else 0


def parse_year_start(value) -> int | None:
    s = str(value or "")
    m = re.search(r"(20\d{2})\D{0,8}(20\d{2})", s)
    if not m:
        return None
    a = int(m.group(1))
    b = int(m.group(2))
    return a if b == a + 1 else None


def school_years(con) -> dict[int, dict]:
    cs = colset(con, "school_years")
    cols = [
        c for c in (
            "code", "name", "label", "school_year",
            "year_name", "start_year", "end_year"
        )
        if c in cs
    ]
    if not cols:
        raise StopInstall("Không xác định được cột năm học.")

    rows = con.execute(
        "SELECT id," + ",".join(qident(c) for c in cols)
        + " FROM school_years ORDER BY id"
    ).fetchall()

    result = {}
    for r in rows:
        joined = " | ".join(str(r[c] or "") for c in cols)
        ystart = None

        if "start_year" in cs:
            try:
                ystart = int(r["start_year"])
            except Exception:
                ystart = None

        if not ystart:
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
            "year_start": ystart,
            "temporal": temporal,
            "text": joined,
        }

    return result


def find_year_id(years, start: int) -> int:
    matches = [
        yid for yid, info in years.items()
        if info["year_start"] == start
    ]
    if len(matches) != 1:
        raise StopInstall(
            f"Không xác định duy nhất năm bắt đầu {start}: {matches}"
        )
    return matches[0]


def get_schools(con):
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


def scan_temporal_residuals(con, years):
    result = []

    for table in all_tables(con):
        cs = colset(con, table)
        if not {"school_id", "school_year_id"} <= cs:
            continue

        rows = con.execute(
            f"""
            SELECT school_id,school_year_id,COUNT(*) AS n
            FROM {qident(table)}
            WHERE school_id IN ({markers(len(SOURCE_IDS))})
            GROUP BY school_id,school_year_id
            ORDER BY school_id,school_year_id
            """,
            SOURCE_IDS,
        ).fetchall()

        for r in rows:
            yid = int(r["school_year_id"])
            info = years.get(
                yid,
                {
                    "year_start": None,
                    "temporal": "UNKNOWN",
                    "text": "",
                },
            )
            result.append({
                "table": table,
                "school_id": int(r["school_id"]),
                "school_year_id": yid,
                "year_start": info["year_start"],
                "year_text": info["text"],
                "temporal": info["temporal"],
                "rows": int(r["n"]),
            })

    return result


def get_classes(con, ids):
    rows = con.execute(
        f"""
        SELECT id,school_id,school_year_id,code,name,is_active
        FROM classes
        WHERE id IN ({markers(len(ids))})
        ORDER BY id
        """,
        ids,
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


def backup_db(src: Path, dst: Path):
    dst.parent.mkdir(parents=True, exist_ok=True)

    s = sqlite3.connect(str(src))
    d = sqlite3.connect(str(dst))
    try:
        s.backup(d)
        d.commit()
    finally:
        d.close()
        s.close()

    check = sqlite3.connect(str(dst))
    try:
        integrity = check.execute("PRAGMA integrity_check").fetchone()[0]
        fk = check.execute("PRAGMA foreign_key_check").fetchall()
        if integrity != "ok" or fk:
            raise StopInstall(
                f"Backup lỗi: integrity={integrity}; FK={len(fk)}"
            )
    finally:
        check.close()


def restore_db(src: Path, dst: Path):
    s = sqlite3.connect(str(src))
    d = sqlite3.connect(str(dst))
    try:
        s.backup(d)
        d.commit()
    finally:
        d.close()
        s.close()


def account_audit(con):
    result = {
        "available": False,
        "locked_school_logins": None,
        "active_school_logins": None,
        "cbql_gv_at_source": None,
    }

    if not table_exists(con, "users"):
        return result

    cs = colset(con, "users")
    if not {"school_id", "is_active", "username"} <= cs:
        return result

    result["available"] = True

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


def main():
    print("=" * 132)
    print("V11.1 CHÍNH THỨC - CHỐT SÁP NHẬP QĐ 3805")
    print("=" * 132)

    if not DB_PATH.exists():
        raise StopInstall(f"Không tìm thấy DB: {DB_PATH}")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    backup_path = BACKUP_DIR / f"phocap_truoc_chot_QD3805_v11_1_{ts}.db"
    report_dir = ROOT / f"bao_cao_chot_QD3805_v11_1_{ts}"
    report_zip = ROOT / f"bao_cao_chot_QD3805_v11_1_{ts}.zip"
    report_dir.mkdir(parents=True, exist_ok=False)

    con = sqlite3.connect(str(DB_PATH))
    con.row_factory = sqlite3.Row

    committed = False
    restored = False
    action = "UNKNOWN"

    try:
        print("[1/6] PRE-FLIGHT...")
        integrity_before = con.execute("PRAGMA integrity_check").fetchone()[0]
        fk_before = con.execute("PRAGMA foreign_key_check").fetchall()

        if integrity_before != "ok":
            raise StopInstall(f"integrity_check={integrity_before}")
        if fk_before:
            raise StopInstall(f"foreign_key_check={len(fk_before)}")

        years = school_years(con)
        current_year_id = find_year_id(years, 2026)
        future_year_id = find_year_id(years, 2027)

        schools = get_schools(con)
        if set(schools) != set(ALL_QD_IDS):
            raise StopInstall(
                f"Thiếu school IDs: {sorted(set(ALL_QD_IDS)-set(schools))}"
            )

        school_rows = []
        for sid in ALL_QD_IDS:
            expected = 0 if sid in SOURCE_IDS else 1
            actual = schools[sid]["is_active"]
            ok = actual in (expected, bool(expected))

            school_rows.append({
                "school_id": sid,
                "school_name": schools[sid]["name"],
                "role": "SOURCE" if sid in SOURCE_IDS else "TARGET",
                "is_active": actual,
                "expected_active": expected,
                "check": "PASS" if ok else "FAIL",
            })

            if not ok:
                raise StopInstall(
                    f"School state sai: {sid} {schools[sid]['name']} "
                    f"active={actual}, expected={expected}"
                )

        residual_before = scan_temporal_residuals(con, years)

        current_before = sum(
            r["rows"] for r in residual_before
            if r["temporal"] == "CURRENT"
        )
        future_before = sum(
            r["rows"] for r in residual_before
            if r["temporal"] == "FUTURE"
        )
        unknown_before = sum(
            r["rows"] for r in residual_before
            if r["temporal"] == "UNKNOWN"
        )

        if current_before != 0:
            raise StopInstall(f"CURRENT residual={current_before}")
        if unknown_before != 0:
            raise StopInstall(f"UNKNOWN residual={unknown_before}")

        class_rows_before = get_classes(con, EXPECTED["class_ids"])

        if len(class_rows_before) != 3:
            raise StopInstall(
                f"Không tìm đủ 3 class id {EXPECTED['class_ids']}: {class_rows_before}"
            )

        actual_ids = [x["id"] for x in class_rows_before]
        actual_names = [x["name"] for x in class_rows_before]

        if actual_ids != EXPECTED["class_ids"]:
            raise StopInstall(f"Class IDs thay đổi: {actual_ids}")
        if actual_names != EXPECTED["class_names"]:
            raise StopInstall(f"Tên lớp thay đổi: {actual_names}")

        # Determine state:
        all_at_source = all(
            x["school_id"] == EXPECTED["source_school_id"]
            and x["school_year_id"] == future_year_id
            for x in class_rows_before
        )

        all_at_target = all(
            x["school_id"] == EXPECTED["target_school_id"]
            and x["school_year_id"] == future_year_id
            for x in class_rows_before
        )

        if future_before == 3 and all_at_source:
            action = "MOVE_3_CLASSES"

        elif future_before == 0 and all_at_target:
            action = "ALREADY_FIXED_SKIP_MOVE"

        else:
            raise StopInstall(
                "Trạng thái 3 lớp không thuộc một trong hai trạng thái hợp lệ. "
                f"future_before={future_before}; classes={class_rows_before}"
            )

        print(f"    CURRENT residual: {current_before}")
        print(f"    FUTURE residual: {future_before}")
        print(f"    ACTION: {action}")

        print("[2/6] BACKUP...")
        backup_db(DB_PATH, backup_path)
        print(f"    {backup_path}")

        if action == "MOVE_3_CLASSES":
            print("[3/6] CHUYỂN 3 LỚP...")
            con.execute("PRAGMA foreign_keys=ON")
            con.execute("BEGIN IMMEDIATE")

            cur = con.execute(
                f"""
                UPDATE classes
                SET school_id=?
                WHERE school_id=?
                  AND school_year_id=?
                  AND id IN ({markers(len(EXPECTED["class_ids"]))})
                """,
                [
                    EXPECTED["target_school_id"],
                    EXPECTED["source_school_id"],
                    future_year_id,
                    *EXPECTED["class_ids"],
                ],
            )

            if cur.rowcount != 3:
                con.rollback()
                raise StopInstall(
                    f"Phải sửa đúng 3 lớp, thực tế={cur.rowcount}"
                )

            con.commit()
            committed = True
            print("    COMMIT: OK")
        else:
            print("[3/6] SKIP MOVE - 3 lớp đã ở đúng TH Nghi Trung.")

        print("[4/6] HẬU KIỂM TEMPORAL...")
        residual_after = scan_temporal_residuals(con, years)

        current_after = sum(
            r["rows"] for r in residual_after
            if r["temporal"] == "CURRENT"
        )
        future_after = sum(
            r["rows"] for r in residual_after
            if r["temporal"] == "FUTURE"
        )
        unknown_after = sum(
            r["rows"] for r in residual_after
            if r["temporal"] == "UNKNOWN"
        )

        if current_after != 0:
            raise StopInstall(f"Post CURRENT residual={current_after}")
        if future_after != 0:
            raise StopInstall(f"Post FUTURE residual={future_after}")
        if unknown_after != 0:
            raise StopInstall(f"Post UNKNOWN residual={unknown_after}")

        class_rows_after = get_classes(con, EXPECTED["class_ids"])

        if not all(
            x["school_id"] == EXPECTED["target_school_id"]
            and x["school_year_id"] == future_year_id
            for x in class_rows_after
        ):
            raise StopInstall(
                f"3 lớp chưa nằm đúng đích: {class_rows_after}"
            )

        print("[5/6] HẬU KIỂM TÀI KHOẢN + DB...")
        accounts = account_audit(con)

        if accounts["available"]:
            if accounts["locked_school_logins"] != 7:
                raise StopInstall(
                    f"Locked source school logins="
                    f"{accounts['locked_school_logins']} != 7"
                )
            if accounts["active_school_logins"] != 0:
                raise StopInstall(
                    f"Active source school logins="
                    f"{accounts['active_school_logins']}"
                )
            if accounts["cbql_gv_at_source"] != 0:
                raise StopInstall(
                    f"CBQL/GV at source={accounts['cbql_gv_at_source']}"
                )

        integrity_after = con.execute("PRAGMA integrity_check").fetchone()[0]
        fk_after = con.execute("PRAGMA foreign_key_check").fetchall()

        if integrity_after != "ok":
            raise StopInstall(f"Post integrity={integrity_after}")
        if fk_after:
            raise StopInstall(f"Post FK errors={len(fk_after)}")

        student_rows = []
        for table in ("students", "student_enrollments"):
            if table_exists(con, table):
                student_rows.append({
                    "table": table,
                    "rows_after": scalar(
                        con, f"SELECT COUNT(*) FROM {qident(table)}"
                    ),
                    "note": "V11.1 không sửa bảng này.",
                })

        print("[6/6] GHI BÁO CÁO...")

        write_csv(
            report_dir / "610_SCHOOL_STATE.csv",
            [
                "school_id", "school_name", "role",
                "is_active", "expected_active", "check",
            ],
            school_rows,
        )

        write_csv(
            report_dir / "611_TEMPORAL_BEFORE.csv",
            [
                "table", "school_id", "school_year_id",
                "year_start", "year_text", "temporal", "rows",
            ],
            residual_before,
        )

        write_csv(
            report_dir / "612_CLASSES_BEFORE.csv",
            [
                "id", "school_id", "school_year_id",
                "code", "name", "is_active",
            ],
            class_rows_before,
        )

        write_csv(
            report_dir / "613_CLASSES_AFTER.csv",
            [
                "id", "school_id", "school_year_id",
                "code", "name", "is_active",
            ],
            class_rows_after,
        )

        write_csv(
            report_dir / "614_TEMPORAL_AFTER.csv",
            [
                "table", "school_id", "school_year_id",
                "year_start", "year_text", "temporal", "rows",
            ],
            residual_after,
        )

        write_csv(
            report_dir / "615_STUDENT_TABLES_UNTOUCHED.csv",
            ["table", "rows_after", "note"],
            student_rows,
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
                "check": "detected_action",
                "result": "PASS",
                "detail": action,
            },
            {
                "check": "current_residual_before",
                "result": "PASS",
                "detail": str(current_before),
            },
            {
                "check": "future_residual_before",
                "result": "PASS",
                "detail": str(future_before),
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
                "check": "classes_16_17_18_at_TH_Nghi_Trung",
                "result": "PASS",
                "detail": "1179 / 2027-2028 / 1A,1B,1C",
            },
            {
                "check": "locked_source_school_logins",
                "result": (
                    "PASS"
                    if not accounts["available"]
                    or accounts["locked_school_logins"] == 7
                    else "FAIL"
                ),
                "detail": str(accounts["locked_school_logins"]),
            },
            {
                "check": "active_source_school_logins",
                "result": (
                    "PASS"
                    if not accounts["available"]
                    or accounts["active_school_logins"] == 0
                    else "FAIL"
                ),
                "detail": str(accounts["active_school_logins"]),
            },
            {
                "check": "cbql_gv_at_source",
                "result": (
                    "PASS"
                    if not accounts["available"]
                    or accounts["cbql_gv_at_source"] == 0
                    else "FAIL"
                ),
                "detail": str(accounts["cbql_gv_at_source"]),
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
                "check": "student_baseline_imported",
                "result": "NO",
                "detail": "Sẽ nạp sau theo xã/phường.",
            },
            {
                "check": "QD3805_MERGER_CLOSED",
                "result": "YES",
                "detail": (
                    "Không còn CURRENT/FUTURE residual tại source; "
                    "3 lớp 2027-2028 ở đúng TH Nghi Trung."
                ),
            },
        ]

        write_csv(
            report_dir / "616_GATE_V11_1.csv",
            ["check", "result", "detail"],
            gate_rows,
        )

        summary = f"""V11.1 - CHỐT SÁP NHẬP QĐ3805
========================================

ACTION = {action}

PRE:
- CURRENT residual = {current_before}
- FUTURE residual = {future_before}
- integrity = {integrity_before}
- FK = {len(fk_before)}

POST:
- CURRENT residual = {current_after}
- FUTURE residual = {future_after}
- UNKNOWN residual = {unknown_after}
- integrity = {integrity_after}
- FK = {len(fk_after)}
- classes 16,17,18 = TH Nghi Trung / 2027-2028 / 1A,1B,1C

ACCOUNT:
- locked source school logins = {accounts["locked_school_logins"]}
- active source school logins = {accounts["active_school_logins"]}
- CBQL/GV at source = {accounts["cbql_gv_at_source"]}

STUDENT:
- baseline 2025-2026: KHÔNG nạp trong V11.1
- test 2026-2027: KHÔNG chạm
- sẽ xây import học sinh đối chiếu riêng theo xã/phường

QD3805_MERGER_CLOSED = YES

BACKUP:
{backup_path}
"""
        (report_dir / "00_TONG_QUAN_V11_1.txt").write_text(
            summary,
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
        print("=" * 132)
        print("HOÀN THÀNH V11.1 - QĐ3805 ĐÃ ĐƯỢC CHỐT")
        print("=" * 132)
        print(f"ACTION: {action}")
        print(f"CURRENT residual source: {current_after}")
        print(f"FUTURE residual source: {future_after}")
        print("Classes 16,17,18: TH Nghi Trung / 2027-2028 / 1A,1B,1C")
        print(f"Integrity: {integrity_after}")
        print(f"FK errors: {len(fk_after)}")
        print("Student baseline import: KHÔNG")
        print("Student test 2026-2027: KHÔNG CHẠM")
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
        print("=" * 132)
        print("V11.1 DỪNG - KHÔNG CHỐT QĐ3805")
        print("=" * 132)
        print(repr(exc))
        if committed:
            print(
                "Đã COMMIT trước khi lỗi hậu kiểm. "
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
