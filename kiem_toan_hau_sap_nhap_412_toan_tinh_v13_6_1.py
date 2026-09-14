# -*- coding: utf-8 -*-
r"""
V13.6.1 - KIỂM TOÁN HẬU SÁP NHẬP 412 PHƯƠNG ÁN TOÀN TỈNH
===========================================================

MỤC TIÊU
--------
Kiểm toán độc lập sau V13.6 bằng cách so sánh:
- Database hiện tại
- Backup ngay trước V13.6
- Plan JSON hiện tại
- Plan JSON backup trước V13.6

CHỈ ĐỌC
-------
- KHÔNG INSERT / UPDATE / DELETE.
- KHÔNG sửa Plan JSON.
- KHÔNG đổi trạng thái trường.
- KHÔNG thực hiện lại sáp nhập.

KIỂM TRA CHÍNH
--------------
1. Database hiện tại + backup đều integrity=ok, FK=0.
2. 6 QĐ3805 vẫn COMPLETED.
3. 412 phương án toàn tỉnh hiện COMPLETED.
4. Mapping 412 plan không đổi so với Plan JSON backup.
5. 483 trường nguồn:
   - trước V13.6 active;
   - sau V13.6 inactive.
6. Trường đích vẫn active.
7. Tài khoản:
   - CBQL/GV/NV ở source trước V13.6 phải sang đúng target;
   - login truong_* của source vẫn gắn source nhưng bị khóa.
8. Với mọi bảng có school_id + school_year_id:
   - PAST tại source phải giữ nguyên tuyệt đối (hash nội dung);
   - CURRENT/FUTURE không còn tại source.
9. school_merger_operations của batch V13.6 phải đúng 412.
10. Kết luận cuối:
    V13_6_POST_AUDIT_CLOSED=YES chỉ khi toàn bộ gate PASS.

CHẠY
----
cd C:\PhoCap
.\.venv\Scripts\python.exe .\kiem_toan_hau_sap_nhap_412_toan_tinh_v13_6_1.py
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import sqlite3
import sys
import zipfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(r"C:\PhoCap")
DB_PATH = ROOT / "data" / "phocap.db"
PLAN_FILE = ROOT / "data" / "school_merger_approved_plans.json"

BACKUP_DIR = (
    ROOT
    / "exports"
    / "backup_truoc_sap_nhap_toan_tinh_v13_6_20260904_161006"
)
BACKUP_DB = BACKUP_DIR / "phocap.db"
BACKUP_PLAN = BACKUP_DIR / "school_merger_approved_plans.json"

BATCH_BACKUP_NAME = (
    "backup_truoc_sap_nhap_toan_tinh_v13_6_20260904_161006"
)

EXPECTED_YEAR_ID = 2
EXPECTED_YEAR_CODE = "2026-2027"
EXPECTED_PROVINCE_PLANS = 412
EXPECTED_QD3805 = 6
EXPECTED_SOURCE_SCHOOLS = 483


def clean(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def qident(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def markers(n: int) -> str:
    return ",".join("?" for _ in range(n))


def connect_ro(path: Path) -> sqlite3.Connection:
    uri = path.resolve().as_uri() + "?mode=ro"
    con = sqlite3.connect(uri, uri=True, timeout=60)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA query_only=ON")
    con.execute("PRAGMA foreign_keys=ON")
    return con


def db_health(con: sqlite3.Connection) -> tuple[str, int]:
    integrity = str(
        con.execute("PRAGMA integrity_check").fetchone()[0]
    )
    fk = len(
        con.execute("PRAGMA foreign_key_check").fetchall()
    )
    return integrity, fk


def write_csv(path: Path, headers: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=headers,
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows)


def load_plan_file(path: Path) -> tuple[dict, list[dict]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    plans = [
        p for p in payload.get("plans") or []
        if isinstance(p, dict)
    ]
    return payload, plans


def stable_plan_signature(plan: dict) -> tuple:
    return (
        str(plan.get("id") or ""),
        int(plan.get("school_year_id") or 0),
        int(plan.get("commune_id") or 0),
        str(plan.get("level_code") or "").upper(),
        tuple(
            sorted(
                int(x)
                for x in plan.get("source_school_ids") or []
            )
        ),
        int(plan.get("target_school_id") or 0),
        str(plan.get("document_code") or ""),
    )


def plan_groups(
    plans: list[dict],
) -> tuple[list[dict], list[dict]]:
    qd = [
        p for p in plans
        if (
            str(p.get("id") or "").startswith("QD3805-")
            or "3805" in str(p.get("document_code") or "")
        )
    ]
    province = [
        p for p in plans
        if str(p.get("document_code") or "")
        == "NGUON-SAP-NHAP-TOAN-TINH"
    ]
    return qd, province


def build_source_target_map(plans: list[dict]) -> dict[int, int]:
    mapping: dict[int, int] = {}
    for p in plans:
        target = int(p.get("target_school_id") or 0)
        for value in p.get("source_school_ids") or []:
            source = int(value)
            if source in mapping and mapping[source] != target:
                raise RuntimeError(
                    f"source school_id={source} có 2 target khác nhau."
                )
            mapping[source] = target
    return mapping


def year_scope(con: sqlite3.Connection) -> tuple[list[int], list[int]]:
    rows = con.execute(
        "SELECT id,code,name FROM school_years ORDER BY id"
    ).fetchall()

    starts = {}
    labels = {}

    for row in rows:
        text = str(row["code"] or row["name"] or "")
        match = re.search(r"(\d{4})\D+(\d{4})", text)
        if not match:
            raise RuntimeError(
                f"Không phân loại được năm học id={row['id']}: {text!r}"
            )
        starts[int(row["id"])] = int(match.group(1))
        labels[int(row["id"])] = text

    if labels.get(EXPECTED_YEAR_ID) != EXPECTED_YEAR_CODE:
        raise RuntimeError(
            f"school_year_id=2 không còn là 2026-2027: "
            f"{labels.get(EXPECTED_YEAR_ID)!r}"
        )

    selected_start = starts[EXPECTED_YEAR_ID]
    move_ids = sorted(
        yid for yid, start in starts.items()
        if start >= selected_start
    )
    past_ids = sorted(
        yid for yid, start in starts.items()
        if start < selected_start
    )

    return move_ids, past_ids


def table_columns(
    con: sqlite3.Connection,
    table: str,
) -> list[str]:
    return [
        str(r["name"])
        for r in con.execute(
            f"PRAGMA table_info({qident(table)})"
        ).fetchall()
    ]


def year_aware_tables(con: sqlite3.Connection) -> list[str]:
    tables = [
        str(r["name"])
        for r in con.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type='table'
              AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """
        ).fetchall()
    ]

    result = []
    for table in tables:
        cols = set(table_columns(con, table))
        if {"school_id", "school_year_id"} <= cols:
            result.append(table)
    return result


def canonical_value(value: Any) -> Any:
    if isinstance(value, bytes):
        return {"__bytes__": value.hex()}
    return value


def hash_rows(
    con: sqlite3.Connection,
    table: str,
    source_ids: list[int],
    year_ids: list[int],
) -> tuple[int, str]:
    if not source_ids or not year_ids:
        return 0, hashlib.sha256(b"").hexdigest()

    cols = table_columns(con, table)
    order_cols = cols[:]

    rows_total = 0
    hasher = hashlib.sha256()
    chunk_size = 600

    for start in range(0, len(source_ids), chunk_size):
        chunk = source_ids[start:start + chunk_size]

        sql = (
            f"SELECT * FROM {qident(table)} "
            f"WHERE school_id IN ({markers(len(chunk))}) "
            f"AND school_year_id IN ({markers(len(year_ids))})"
        )
        rows = con.execute(
            sql,
            [*chunk, *year_ids],
        ).fetchall()

        serialized = []
        for row in rows:
            obj = {
                col: canonical_value(row[col])
                for col in cols
            }
            serialized.append(
                json.dumps(
                    obj,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                    default=str,
                )
            )

        serialized.sort()

        for line in serialized:
            hasher.update(line.encode("utf-8"))
            hasher.update(b"\n")

        rows_total += len(serialized)

    return rows_total, hasher.hexdigest()


def count_rows_at_sources(
    con: sqlite3.Connection,
    table: str,
    source_ids: list[int],
    year_ids: list[int],
) -> int:
    if not source_ids or not year_ids:
        return 0

    total = 0
    chunk_size = 700
    for start in range(0, len(source_ids), chunk_size):
        chunk = source_ids[start:start + chunk_size]
        total += int(
            con.execute(
                f"SELECT COUNT(*) FROM {qident(table)} "
                f"WHERE school_id IN ({markers(len(chunk))}) "
                f"AND school_year_id IN ({markers(len(year_ids))})",
                [*chunk, *year_ids],
            ).fetchone()[0]
            or 0
        )
    return total


def school_states(
    con: sqlite3.Connection,
    ids: list[int],
) -> dict[int, dict]:
    result = {}
    chunk_size = 700
    for start in range(0, len(ids), chunk_size):
        chunk = ids[start:start + chunk_size]
        rows = con.execute(
            f"SELECT id,code,name,commune_id,is_active "
            f"FROM schools WHERE id IN ({markers(len(chunk))})",
            chunk,
        ).fetchall()
        for row in rows:
            result[int(row["id"])] = dict(row)
    return result


def user_audit(
    before: sqlite3.Connection,
    after: sqlite3.Connection,
    mapping: dict[int, int],
) -> tuple[list[dict], list[dict]]:
    source_ids = sorted(mapping)
    regular_results = []
    login_results = []

    chunk_size = 600

    for start in range(0, len(source_ids), chunk_size):
        chunk = source_ids[start:start + chunk_size]

        before_rows = before.execute(
            f"SELECT id,username,school_id,is_active "
            f"FROM users WHERE school_id IN ({markers(len(chunk))})",
            chunk,
        ).fetchall()

        ids = [int(r["id"]) for r in before_rows]
        current_by_id = {}

        if ids:
            for j in range(0, len(ids), 700):
                id_chunk = ids[j:j + 700]
                rows = after.execute(
                    f"SELECT id,username,school_id,is_active "
                    f"FROM users WHERE id IN ({markers(len(id_chunk))})",
                    id_chunk,
                ).fetchall()
                current_by_id.update(
                    {int(r["id"]): r for r in rows}
                )

        for old in before_rows:
            uid = int(old["id"])
            username = str(old["username"] or "")
            old_school = int(old["school_id"])
            cur = current_by_id.get(uid)

            if cur is None:
                result = "FAIL"
                detail = "user_id biến mất sau sáp nhập"
            elif username.startswith("truong_"):
                ok = (
                    int(cur["school_id"] or 0) == old_school
                    and int(cur["is_active"] or 0) == 0
                )
                result = "PASS" if ok else "FAIL"
                detail = (
                    f"school {old_school}->{cur['school_id']}; "
                    f"active {old['is_active']}->{cur['is_active']}"
                )
                login_results.append({
                    "user_id": uid,
                    "username": username,
                    "source_school_id": old_school,
                    "current_school_id": (
                        int(cur["school_id"])
                        if cur["school_id"] is not None
                        else ""
                    ),
                    "current_is_active": int(cur["is_active"] or 0),
                    "result": result,
                    "detail": detail,
                })
                continue
            else:
                expected_target = mapping[old_school]
                ok = (
                    int(cur["school_id"] or 0)
                    == expected_target
                )
                result = "PASS" if ok else "FAIL"
                detail = (
                    f"school {old_school}->{cur['school_id']}; "
                    f"expected={expected_target}"
                )

            if not username.startswith("truong_"):
                regular_results.append({
                    "user_id": uid,
                    "username": username,
                    "source_school_id": old_school,
                    "expected_target_school_id": mapping[old_school],
                    "current_school_id": (
                        int(cur["school_id"])
                        if cur and cur["school_id"] is not None
                        else ""
                    ),
                    "result": result,
                    "detail": detail,
                })

    return regular_results, login_results


def main() -> int:
    print("=" * 126)
    print("V13.6.1 - KIỂM TOÁN HẬU SÁP NHẬP 412 TOÀN TỈNH")
    print("=" * 126)
    print("CHỈ ĐỌC - KHÔNG SỬA DATABASE / PLAN JSON")

    for path in (
        DB_PATH,
        PLAN_FILE,
        BACKUP_DB,
        BACKUP_PLAN,
    ):
        if not path.exists():
            raise RuntimeError(
                f"Không tìm thấy tệp bắt buộc: {path}"
            )

    current_payload, current_plans = load_plan_file(PLAN_FILE)
    backup_payload, backup_plans = load_plan_file(BACKUP_PLAN)

    qd_now, province_now = plan_groups(current_plans)
    qd_before, province_before = plan_groups(backup_plans)

    if len(qd_now) != EXPECTED_QD3805:
        raise RuntimeError(
            f"QĐ3805 hiện={len(qd_now)}, cần 6."
        )
    if len(province_now) != EXPECTED_PROVINCE_PLANS:
        raise RuntimeError(
            f"Province plan hiện={len(province_now)}, cần 412."
        )
    if len(province_before) != EXPECTED_PROVINCE_PLANS:
        raise RuntimeError(
            f"Province plan backup={len(province_before)}, cần 412."
        )

    current_completed = sum(
        str(p.get("status") or "").upper() == "COMPLETED"
        for p in province_now
    )
    backup_approved = sum(
        str(p.get("status") or "").upper() == "APPROVED"
        for p in province_before
    )
    qd_completed = sum(
        str(p.get("status") or "").upper() == "COMPLETED"
        for p in qd_now
    )

    current_sigs = {
        stable_plan_signature(p)
        for p in province_now
    }
    backup_sigs = {
        stable_plan_signature(p)
        for p in province_before
    }
    mapping_unchanged = current_sigs == backup_sigs

    mapping = build_source_target_map(province_now)
    source_ids = sorted(mapping)
    target_ids = sorted(set(mapping.values()))

    if len(source_ids) != EXPECTED_SOURCE_SCHOOLS:
        raise RuntimeError(
            f"Source schools={len(source_ids)}, cần 483."
        )

    with connect_ro(BACKUP_DB) as before, connect_ro(DB_PATH) as after:
        before_integrity, before_fk = db_health(before)
        after_integrity, after_fk = db_health(after)

        if before_integrity.lower() != "ok" or before_fk != 0:
            raise RuntimeError(
                f"Backup DB lỗi: integrity={before_integrity}, FK={before_fk}"
            )
        if after_integrity.lower() != "ok" or after_fk != 0:
            raise RuntimeError(
                f"Current DB lỗi: integrity={after_integrity}, FK={after_fk}"
            )

        move_ids_before, past_ids_before = year_scope(before)
        move_ids_after, past_ids_after = year_scope(after)

        if move_ids_before != [2, 8] or move_ids_after != [2, 8]:
            raise RuntimeError(
                f"CURRENT+FUTURE sai: "
                f"before={move_ids_before}, after={move_ids_after}"
            )
        if past_ids_before != past_ids_after:
            raise RuntimeError(
                "Danh sách PAST trước/sau khác nhau."
            )

        source_before = school_states(before, source_ids)
        source_after = school_states(after, source_ids)
        target_after = school_states(after, target_ids)

        school_rows = []
        source_state_fail = 0

        for sid in source_ids:
            b = source_before.get(sid)
            a = source_after.get(sid)
            ok = (
                b is not None
                and a is not None
                and int(b["is_active"] or 0) == 1
                and int(a["is_active"] or 0) == 0
            )
            if not ok:
                source_state_fail += 1

            school_rows.append({
                "source_school_id": sid,
                "source_name": (
                    a["name"] if a is not None else ""
                ),
                "target_school_id": mapping[sid],
                "before_is_active": (
                    int(b["is_active"] or 0)
                    if b is not None else ""
                ),
                "after_is_active": (
                    int(a["is_active"] or 0)
                    if a is not None else ""
                ),
                "result": "PASS" if ok else "FAIL",
            })

        target_inactive = [
            tid
            for tid in target_ids
            if (
                tid not in target_after
                or int(target_after[tid]["is_active"] or 0) != 1
            )
        ]

        regular_users, source_logins = user_audit(
            before,
            after,
            mapping,
        )
        regular_user_fail = sum(
            r["result"] != "PASS"
            for r in regular_users
        )
        source_login_fail = sum(
            r["result"] != "PASS"
            for r in source_logins
        )

        tables_before = year_aware_tables(before)
        tables_after = year_aware_tables(after)
        common_tables = sorted(
            set(tables_before) & set(tables_after)
        )

        table_rows = []
        past_fail = 0
        residual_total = 0

        for index, table in enumerate(common_tables, start=1):
            if index == 1 or index % 10 == 0 or index == len(common_tables):
                print(
                    f"Kiểm bảng năm học: {index}/{len(common_tables)} - {table}",
                    flush=True,
                )

            before_count, before_hash = hash_rows(
                before,
                table,
                source_ids,
                past_ids_before,
            )
            after_count, after_hash = hash_rows(
                after,
                table,
                source_ids,
                past_ids_after,
            )

            past_ok = (
                before_count == after_count
                and before_hash == after_hash
            )
            if not past_ok:
                past_fail += 1

            residual = count_rows_at_sources(
                after,
                table,
                source_ids,
                move_ids_after,
            )
            residual_total += residual

            table_rows.append({
                "table": table,
                "past_before_count": before_count,
                "past_after_count": after_count,
                "past_hash_before": before_hash,
                "past_hash_after": after_hash,
                "past_result": "PASS" if past_ok else "FAIL",
                "current_future_residual": residual,
                "current_future_result": (
                    "PASS" if residual == 0 else "FAIL"
                ),
            })

        operation_count = 0
        if after.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type='table'
              AND name='school_merger_operations'
            """
        ).fetchone():
            cols = set(
                table_columns(after, "school_merger_operations")
            )
            if "backup_name" in cols:
                operation_count = int(
                    after.execute(
                        """
                        SELECT COUNT(*)
                        FROM school_merger_operations
                        WHERE backup_name=?
                        """,
                        (BATCH_BACKUP_NAME,),
                    ).fetchone()[0]
                    or 0
                )

    all_pass = (
        qd_completed == 6
        and current_completed == 412
        and backup_approved == 412
        and mapping_unchanged
        and source_state_fail == 0
        and len(target_inactive) == 0
        and regular_user_fail == 0
        and source_login_fail == 0
        and past_fail == 0
        and residual_total == 0
        and operation_count == 412
        and before_integrity.lower() == "ok"
        and before_fk == 0
        and after_integrity.lower() == "ok"
        and after_fk == 0
    )

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_dir = ROOT / f"bao_cao_v13_6_1_hau_kiem_412_{stamp}"
    zip_path = ROOT / f"bao_cao_v13_6_1_hau_kiem_412_{stamp}.zip"
    report_dir.mkdir(parents=True, exist_ok=False)

    write_csv(
        report_dir / "750_TRUONG_NGUON.csv",
        [
            "source_school_id",
            "source_name",
            "target_school_id",
            "before_is_active",
            "after_is_active",
            "result",
        ],
        school_rows,
    )

    write_csv(
        report_dir / "751_TAI_KHOAN_CBQL_GV_NV.csv",
        [
            "user_id",
            "username",
            "source_school_id",
            "expected_target_school_id",
            "current_school_id",
            "result",
            "detail",
        ],
        regular_users,
    )

    write_csv(
        report_dir / "752_LOGIN_TRUONG_NGUON.csv",
        [
            "user_id",
            "username",
            "source_school_id",
            "current_school_id",
            "current_is_active",
            "result",
            "detail",
        ],
        source_logins,
    )

    write_csv(
        report_dir / "753_PAST_VA_CURRENT_FUTURE.csv",
        [
            "table",
            "past_before_count",
            "past_after_count",
            "past_hash_before",
            "past_hash_after",
            "past_result",
            "current_future_residual",
            "current_future_result",
        ],
        table_rows,
    )

    gate_rows = [
        {
            "check": "backup_db_integrity",
            "result": "PASS" if before_integrity.lower() == "ok" else "FAIL",
            "detail": before_integrity,
        },
        {
            "check": "backup_db_fk",
            "result": "PASS" if before_fk == 0 else "FAIL",
            "detail": str(before_fk),
        },
        {
            "check": "current_db_integrity",
            "result": "PASS" if after_integrity.lower() == "ok" else "FAIL",
            "detail": after_integrity,
        },
        {
            "check": "current_db_fk",
            "result": "PASS" if after_fk == 0 else "FAIL",
            "detail": str(after_fk),
        },
        {
            "check": "qd3805_completed",
            "result": "PASS" if qd_completed == 6 else "FAIL",
            "detail": str(qd_completed),
        },
        {
            "check": "province_completed",
            "result": "PASS" if current_completed == 412 else "FAIL",
            "detail": str(current_completed),
        },
        {
            "check": "backup_province_approved",
            "result": "PASS" if backup_approved == 412 else "FAIL",
            "detail": str(backup_approved),
        },
        {
            "check": "plan_mapping_unchanged",
            "result": "PASS" if mapping_unchanged else "FAIL",
            "detail": str(mapping_unchanged),
        },
        {
            "check": "source_school_state",
            "result": "PASS" if source_state_fail == 0 else "FAIL",
            "detail": f"fail={source_state_fail}/483",
        },
        {
            "check": "target_school_active",
            "result": "PASS" if not target_inactive else "FAIL",
            "detail": repr(target_inactive[:20]),
        },
        {
            "check": "regular_users_moved_exact_target",
            "result": "PASS" if regular_user_fail == 0 else "FAIL",
            "detail": f"fail={regular_user_fail}/{len(regular_users)}",
        },
        {
            "check": "source_school_logins_locked",
            "result": "PASS" if source_login_fail == 0 else "FAIL",
            "detail": f"fail={source_login_fail}/{len(source_logins)}",
        },
        {
            "check": "past_content_unchanged",
            "result": "PASS" if past_fail == 0 else "FAIL",
            "detail": f"fail_tables={past_fail}/{len(table_rows)}",
        },
        {
            "check": "current_future_source_residual",
            "result": "PASS" if residual_total == 0 else "FAIL",
            "detail": str(residual_total),
        },
        {
            "check": "school_merger_operations",
            "result": "PASS" if operation_count == 412 else "FAIL",
            "detail": str(operation_count),
        },
        {
            "check": "V13_6_POST_AUDIT_CLOSED",
            "result": "YES" if all_pass else "NO",
            "detail": (
                "Hậu kiểm 412 phương án đạt toàn bộ."
                if all_pass
                else "Có gate FAIL; chưa xử lý 3 nhóm đặc biệt."
            ),
        },
    ]

    write_csv(
        report_dir / "754_GATE_V13_6_1.csv",
        ["check", "result", "detail"],
        gate_rows,
    )

    summary = f"""V13.6.1 - KIỂM TOÁN HẬU SÁP NHẬP 412 TOÀN TỈNH
================================================================================

STATUS={'PASS' if all_pass else 'REVIEW'}

Plan:
- QĐ3805 COMPLETED = {qd_completed}/6
- Province COMPLETED = {current_completed}/412
- Backup Province APPROVED = {backup_approved}/412
- Mapping unchanged = {mapping_unchanged}

School:
- Source schools = {len(source_ids)}
- Source state fail = {source_state_fail}
- Target inactive = {len(target_inactive)}

User:
- CBQL/GV/NV checked = {len(regular_users)}
- CBQL/GV/NV wrong target = {regular_user_fail}
- Source school login checked = {len(source_logins)}
- Source school login policy fail = {source_login_fail}

Year-aware data:
- Tables checked = {len(table_rows)}
- PAST content fail tables = {past_fail}
- CURRENT/FUTURE residual = {residual_total}

Audit:
- school_merger_operations batch = {operation_count}

DB:
- Backup integrity = {before_integrity}
- Backup FK = {before_fk}
- Current integrity = {after_integrity}
- Current FK = {after_fk}

V13_6_POST_AUDIT_CLOSED={'YES' if all_pass else 'NO'}

Database: KHÔNG THAY ĐỔI.
Plan JSON: KHÔNG THAY ĐỔI.
"""

    (report_dir / "00_TONG_QUAN_V13_6_1.txt").write_text(
        summary,
        encoding="utf-8",
    )

    with zipfile.ZipFile(
        zip_path,
        "w",
        compression=zipfile.ZIP_DEFLATED,
    ) as zf:
        for p in sorted(report_dir.iterdir()):
            if p.is_file():
                zf.write(p, arcname=p.name)

    print()
    print("=" * 126)
    print("HOÀN THÀNH V13.6.1")
    print("=" * 126)
    print(f"QĐ3805 COMPLETED: {qd_completed}/6")
    print(f"Province COMPLETED: {current_completed}/412")
    print(f"Source state fail: {source_state_fail}")
    print(f"Target inactive: {len(target_inactive)}")
    print(f"CBQL/GV/NV wrong target: {regular_user_fail}")
    print(f"Source login policy fail: {source_login_fail}")
    print(f"PAST content fail tables: {past_fail}")
    print(f"CURRENT/FUTURE residual: {residual_total}")
    print(f"Audit operations: {operation_count}")
    print(f"Current DB integrity: {after_integrity}")
    print(f"Current DB FK errors: {after_fk}")
    print(
        "V13_6_POST_AUDIT_CLOSED: "
        + ("YES" if all_pass else "NO")
    )
    print("Database: KHÔNG THAY ĐỔI")
    print("Plan JSON: KHÔNG THAY ĐỔI")
    print(f"ZIP: {zip_path}")

    return 0 if all_pass else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print()
        print("=" * 126)
        print("V13.6.1 DỪNG AN TOÀN")
        print("=" * 126)
        print(repr(exc))
        print("Database: KHÔNG THAY ĐỔI")
        print("Plan JSON: KHÔNG THAY ĐỔI")
        raise SystemExit(2)
