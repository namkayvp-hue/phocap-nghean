# -*- coding: utf-8 -*-
r"""
V13.6 - THỰC HIỆN THẬT 412 PHƯƠNG ÁN SÁP NHẬP TOÀN TỈNH
=========================================================

ĐIỀU KIỆN ĐÃ PASS Ở V13.5.3
---------------------------
- Engine V13.5.2 SHA:
  414fb49a4c5f4fed7b571cc55df381678fe660cd8a675ecaa2f6fd70ebd7827a
- Plan JSON SHA:
  004fdaa536f8229dcfce51d02031941aa639a7cace8927e4b5cb3c86985d30cf
- QĐ3805 COMPLETED: 6
- Toàn tỉnh APPROVED: 412
- Mô phỏng PASS: 412/412
- Errors: 0
- Source schools: 483
- CURRENT/FUTURE residual sau mô phỏng: 0
- PAST thay đổi: 0
- RAM integrity: ok
- RAM FK: 0

TÁC ĐỘNG DỰ KIẾN THEO MÔ PHỎNG
-------------------------------
- 483 trường nguồn -> inactive
- 5.159 tài khoản CBQL/GV/NV -> trường đích
- 483 login trường nguồn -> khóa
- 5.158 staff_year_records CURRENT -> trường đích
- 1 lớp CURRENT -> trường đích
- 18.805 staff_year_records CURRENT còn thiếu -> rollover từ 2025-2026
- PAST giữ nguyên
- FUTURE (nếu có) đi theo trường đích

AN TOÀN
-------
1. BẮT BUỘC dừng Uvicorn trước khi chạy.
2. Mặc định chỉ preflight, không ghi.
3. Khi --apply:
   - tạo backup SQLite đầy đủ + backup Plan JSON;
   - kiểm tra backup integrity/FK;
   - BEGIN IMMEDIATE;
   - chạy 412 phương án trong MỘT transaction;
   - mỗi plan vẫn chạy hậu kiểm nghiệp vụ;
   - hoãn full-scan integrity/FK trong từng plan để không quét DB 412 lần;
   - cuối toàn lô chạy integrity_check + foreign_key_check thật;
   - chỉ khi tất cả PASS mới COMMIT;
   - sau COMMIT kiểm tra DB lại;
   - ghi 412 plan thành COMPLETED;
   - 6 QĐ3805 giữ COMPLETED.
4. Nếu lỗi trước commit: rollback toàn lô.
5. Nếu post-check DB sau commit lỗi: tự restore DB từ backup.
6. Nếu chỉ ghi Plan JSON lỗi sau khi DB đã PASS:
   DB vẫn an toàn và 412 operation audit khiến trạng thái hiệu lực là COMPLETED;
   script dừng để xử lý đồng bộ Plan JSON riêng, KHÔNG chạy lại sáp nhập.

CHẠY PREFLIGHT
--------------
cd C:\PhoCap
.\.venv\Scripts\python.exe .\thuc_hien_sap_nhap_that_412_phuong_an_toan_tinh_v13_6.py

CHẠY THẬT
---------
cd C:\PhoCap
.\.venv\Scripts\python.exe .\thuc_hien_sap_nhap_that_412_phuong_an_toan_tinh_v13_6.py `
  --apply `
  --confirm "SAP NHAP THAT 412 PHUONG AN TOAN TINH"
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import time
import zipfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(r"C:\PhoCap")
DB_PATH = ROOT / "data" / "phocap.db"
PLAN_FILE = ROOT / "data" / "school_merger_approved_plans.json"
SERVICE = ROOT / "app" / "services" / "school_merger_service.py"
EXPORTS = ROOT / "exports"

EXPECTED_SERVICE_SHA = (
    "414fb49a4c5f4fed7b571cc55df381678fe660cd8a675ecaa2f6fd70ebd7827a"
)
EXPECTED_PLAN_SHA = (
    "004fdaa536f8229dcfce51d02031941aa639a7cace8927e4b5cb3c86985d30cf"
)
EXPECTED_YEAR_ID = 2
EXPECTED_YEAR_CODE = "2026-2027"
EXPECTED_QD3805 = 6
EXPECTED_APPROVED = 412
EXPECTED_SOURCE_SCHOOLS = 483

EXPECTED_SIM_USERS_MOVED = 5159
EXPECTED_SIM_LOGINS_DISABLED = 483
EXPECTED_SIM_STAFF_ROLLOVER = 18805
EXPECTED_SIM_SOURCES_DEACTIVATED = 483

CONFIRM_PHRASE = "SAP NHAP THAT 412 PHUONG AN TOAN TINH"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def clean(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def qident(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def markers(n: int) -> str:
    return ",".join("?" for _ in range(n))


def write_csv(path: Path, headers: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def load_registry() -> tuple[dict, list[dict], list[dict]]:
    payload = json.loads(
        PLAN_FILE.read_text(encoding="utf-8")
    )
    plans = [
        p for p in payload.get("plans") or []
        if isinstance(p, dict)
    ]

    qd = [
        p for p in plans
        if (
            str(p.get("id") or "").startswith("QD3805-")
            or "3805" in str(p.get("document_code") or "")
        )
    ]
    qd_completed = [
        p for p in qd
        if str(p.get("status") or "").upper() == "COMPLETED"
    ]

    approved = [
        p for p in plans
        if (
            str(p.get("document_code") or "")
            == "NGUON-SAP-NHAP-TOAN-TINH"
            and int(p.get("school_year_id") or 0) == EXPECTED_YEAR_ID
            and str(p.get("status") or "").upper() == "APPROVED"
        )
    ]

    if len(plans) != 418:
        raise RuntimeError(
            f"Registry phải có 418 plan; hiện={len(plans)}."
        )
    if len(qd) != EXPECTED_QD3805 or len(qd_completed) != EXPECTED_QD3805:
        raise RuntimeError(
            f"QĐ3805 phải đúng 6 COMPLETED; "
            f"qd={len(qd)}, completed={len(qd_completed)}."
        )
    if len(approved) != EXPECTED_APPROVED:
        raise RuntimeError(
            f"Plan toàn tỉnh APPROVED phải =412; hiện={len(approved)}."
        )

    return payload, qd_completed, approved


def plan_sort_key(p: dict) -> tuple:
    return (
        int(p.get("commune_id") or 0),
        str(p.get("level_code") or ""),
        int(p.get("target_school_id") or 0),
        tuple(
            sorted(
                int(x)
                for x in p.get("source_school_ids") or []
            )
        ),
        str(p.get("id") or ""),
    )


def source_ids_from(plans: list[dict]) -> list[int]:
    return sorted({
        int(sid)
        for p in plans
        for sid in (p.get("source_school_ids") or [])
    })


def validate_no_chaining(plans: list[dict]) -> None:
    owner: dict[int, str] = {}
    overlaps = []

    for p in plans:
        pid = str(p.get("id") or "")
        ids = {
            int(p.get("target_school_id") or 0),
            *[
                int(x)
                for x in p.get("source_school_ids") or []
            ],
        }
        ids.discard(0)

        for sid in ids:
            if sid in owner:
                overlaps.append(
                    (sid, owner[sid], pid)
                )
            else:
                owner[sid] = pid

    if overlaps:
        raise RuntimeError(
            "412 plan có trường xuất hiện ở nhiều nhóm "
            f"(source/target overlap): {overlaps[:10]}"
        )


def connect_ro(path: Path) -> sqlite3.Connection:
    uri = path.resolve().as_uri() + "?mode=ro"
    con = sqlite3.connect(
        uri,
        uri=True,
        timeout=60,
    )
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA query_only=ON")
    con.execute("PRAGMA foreign_keys=ON")
    return con


def db_health(con: sqlite3.Connection) -> tuple[str, list]:
    integrity = str(
        con.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]
    )
    fk = con.execute(
        "PRAGMA foreign_key_check"
    ).fetchall()
    return integrity, fk


def sqlite_backup(
    source_path: Path,
    target_path: Path,
) -> None:
    target_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    src = sqlite3.connect(
        str(source_path),
        timeout=60,
    )
    dst = sqlite3.connect(
        str(target_path),
        timeout=60,
    )
    try:
        src.backup(dst)
        dst.commit()
    finally:
        dst.close()
        src.close()


def sqlite_restore(
    backup_path: Path,
    db_path: Path,
) -> None:
    src = sqlite3.connect(
        str(backup_path),
        timeout=60,
    )
    dst = sqlite3.connect(
        str(db_path),
        timeout=60,
    )
    try:
        src.backup(dst)
        dst.commit()
    finally:
        dst.close()
        src.close()


class _FakeCursor:
    def __init__(self, rows):
        self._rows = list(rows)
        self.rowcount = -1

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)


class BatchConnection(sqlite3.Connection):
    """
    Trong từng _apply_merge chỉ hoãn hai full-scan PRAGMA nặng.
    Mọi kiểm tra residual, user, login, target vẫn chạy thật.
    Cuối toàn lô sẽ chạy integrity/FK thật trước commit.
    """
    defer_heavy_pragmas = True

    def execute(self, sql, parameters=(), /):
        normalized = " ".join(
            str(sql).strip().lower().split()
        )
        if self.defer_heavy_pragmas:
            if normalized == "pragma foreign_key_check":
                return _FakeCursor([])
            if normalized == "pragma integrity_check":
                return _FakeCursor([("ok",)])
        return super().execute(sql, parameters)


def real_integrity(
    con: BatchConnection,
) -> str:
    old = con.defer_heavy_pragmas
    con.defer_heavy_pragmas = False
    try:
        return str(
            con.execute(
                "PRAGMA integrity_check"
            ).fetchone()[0]
        )
    finally:
        con.defer_heavy_pragmas = old


def real_fk(
    con: BatchConnection,
) -> list:
    old = con.defer_heavy_pragmas
    con.defer_heavy_pragmas = False
    try:
        return con.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()
    finally:
        con.defer_heavy_pragmas = old


def year_aware_tables(
    con: sqlite3.Connection,
) -> list[str]:
    tables = [
        str(r[0])
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
        cols = {
            str(r[1])
            for r in con.execute(
                f"PRAGMA table_info({qident(table)})"
            ).fetchall()
        }
        if {
            "school_id",
            "school_year_id",
        } <= cols:
            result.append(table)

    return result


def grouped_year_counts(
    con: sqlite3.Connection,
    tables: list[str],
    source_ids: list[int],
    year_ids: list[int],
) -> dict[tuple[str, int], int]:
    if not source_ids or not year_ids:
        return {}

    result: dict[tuple[str, int], int] = {}
    chunk_size = 700

    for table in tables:
        totals: dict[int, int] = defaultdict(int)

        for start in range(
            0,
            len(source_ids),
            chunk_size,
        ):
            chunk = source_ids[
                start:start + chunk_size
            ]
            sql = (
                f"SELECT school_year_id,COUNT(*) "
                f"FROM {qident(table)} "
                f"WHERE school_id IN "
                f"({markers(len(chunk))}) "
                f"AND school_year_id IN "
                f"({markers(len(year_ids))}) "
                f"GROUP BY school_year_id"
            )
            rows = con.execute(
                sql,
                [*chunk, *year_ids],
            ).fetchall()

            for row in rows:
                totals[int(row[0])] += int(
                    row[1] or 0
                )

        for year_id, n in totals.items():
            result[
                (table, year_id)
            ] = n

    return result


def count_sources_active(
    con: sqlite3.Connection,
    source_ids: list[int],
) -> int:
    total = 0
    chunk_size = 700
    for start in range(
        0,
        len(source_ids),
        chunk_size,
    ):
        chunk = source_ids[
            start:start + chunk_size
        ]
        total += int(
            con.execute(
                f"SELECT COUNT(*) FROM schools "
                f"WHERE id IN "
                f"({markers(len(chunk))}) "
                "AND is_active=1",
                chunk,
            ).fetchone()[0] or 0
        )
    return total


def source_user_counts(
    con: sqlite3.Connection,
    source_ids: list[int],
) -> tuple[int, int]:
    regular = 0
    active_school_logins = 0
    chunk_size = 700

    for start in range(
        0,
        len(source_ids),
        chunk_size,
    ):
        chunk = source_ids[
            start:start + chunk_size
        ]

        regular += int(
            con.execute(
                f"SELECT COUNT(*) FROM users "
                f"WHERE school_id IN "
                f"({markers(len(chunk))}) "
                "AND username NOT LIKE 'truong_%'",
                chunk,
            ).fetchone()[0] or 0
        )

        active_school_logins += int(
            con.execute(
                f"SELECT COUNT(*) FROM users "
                f"WHERE school_id IN "
                f"({markers(len(chunk))}) "
                "AND username LIKE 'truong_%' "
                "AND is_active=1",
                chunk,
            ).fetchone()[0] or 0
        )

    return regular, active_school_logins


def validate_fast_preflight(
    approved: list[dict],
    source_ids: list[int],
) -> dict[str, Any]:
    with connect_ro(DB_PATH) as con:
        integrity, fk = db_health(con)
        if integrity.lower() != "ok" or fk:
            raise RuntimeError(
                f"DB preflight lỗi: "
                f"integrity={integrity}, FK={len(fk)}"
            )

        year = con.execute(
            "SELECT id,code FROM school_years "
            "WHERE id=?",
            (EXPECTED_YEAR_ID,),
        ).fetchone()
        if (
            year is None
            or clean(year["code"])
            != EXPECTED_YEAR_CODE
        ):
            raise RuntimeError(
                "school_year_id=2 không còn là "
                "2026-2027."
            )

        active_sources = count_sources_active(
            con,
            source_ids,
        )
        regular_users, source_logins = (
            source_user_counts(
                con,
                source_ids,
            )
        )

        # Các số này chính là trạng thái trước mô phỏng V13.5.3.
        if active_sources != EXPECTED_SOURCE_SCHOOLS:
            raise RuntimeError(
                f"Source active đã đổi từ V13.5.3: "
                f"{active_sources} != "
                f"{EXPECTED_SOURCE_SCHOOLS}"
            )
        if regular_users != EXPECTED_SIM_USERS_MOVED:
            raise RuntimeError(
                f"Số CBQL/GV/NV tại source đã đổi: "
                f"{regular_users} != "
                f"{EXPECTED_SIM_USERS_MOVED}"
            )
        if source_logins != EXPECTED_SIM_LOGINS_DISABLED:
            raise RuntimeError(
                f"Số login trường nguồn active đã đổi: "
                f"{source_logins} != "
                f"{EXPECTED_SIM_LOGINS_DISABLED}"
            )

        return {
            "integrity": integrity,
            "fk": len(fk),
            "active_sources": active_sources,
            "regular_users": regular_users,
            "source_logins": source_logins,
        }


def build_completed_payload(
    original_payload: dict,
    approved_ids: set[str],
    *,
    backup_name: str,
) -> dict:
    payload = json.loads(
        json.dumps(
            original_payload,
            ensure_ascii=False,
        )
    )
    now = datetime.now().isoformat(
        timespec="seconds"
    )
    found = 0

    for plan in payload.get("plans") or []:
        if not isinstance(plan, dict):
            continue
        pid = str(plan.get("id") or "")
        if pid not in approved_ids:
            continue

        if (
            str(plan.get("status") or "").upper()
            != "APPROVED"
        ):
            raise RuntimeError(
                f"Plan {pid} không còn APPROVED "
                "khi chuẩn bị COMPLETED."
            )

        plan["status"] = "COMPLETED"
        plan["completed_at"] = now
        plan["completed_by"] = "V13.6_BATCH"
        plan["completion_backup"] = backup_name
        plan["updated_at"] = now
        found += 1

    if found != EXPECTED_APPROVED:
        raise RuntimeError(
            f"Chỉ tìm thấy {found}/412 plan "
            "để đánh dấu COMPLETED."
        )

    payload["version"] = max(
        int(payload.get("version") or 1),
        3,
    )
    payload["revision"] = int(
        payload.get("revision") or 0
    ) + 1
    payload["updated_at"] = now
    return payload


def atomic_write_json(
    path: Path,
    payload: dict,
) -> None:
    raw = json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
    )
    json.loads(raw)

    tmp = path.with_name(
        path.name + ".v13_6.tmp"
    )
    tmp.write_text(
        raw,
        encoding="utf-8",
    )
    os.replace(
        tmp,
        path,
    )


def validate_completed_registry() -> tuple[int, int]:
    payload = json.loads(
        PLAN_FILE.read_text(encoding="utf-8")
    )
    plans = [
        p for p in payload.get("plans") or []
        if isinstance(p, dict)
    ]

    qd_completed = [
        p for p in plans
        if (
            (
                str(p.get("id") or "")
                .startswith("QD3805-")
                or "3805"
                in str(
                    p.get("document_code") or ""
                )
            )
            and str(
                p.get("status") or ""
            ).upper() == "COMPLETED"
        )
    ]

    province_completed = [
        p for p in plans
        if (
            str(
                p.get("document_code") or ""
            )
            == "NGUON-SAP-NHAP-TOAN-TINH"
            and str(
                p.get("status") or ""
            ).upper() == "COMPLETED"
        )
    ]

    if len(qd_completed) != 6:
        raise RuntimeError(
            f"QĐ3805 COMPLETED sau V13.6="
            f"{len(qd_completed)}, cần 6."
        )
    if len(province_completed) != 412:
        raise RuntimeError(
            "Plan toàn tỉnh COMPLETED sau V13.6="
            f"{len(province_completed)}, cần 412."
        )

    return (
        len(qd_completed),
        len(province_completed),
    )


def restore_db_from_backup(
    backup_db: Path,
) -> None:
    sqlite_restore(
        backup_db,
        DB_PATH,
    )
    with connect_ro(DB_PATH) as con:
        integrity, fk = db_health(con)
        if integrity.lower() != "ok" or fk:
            raise RuntimeError(
                "RESTORE DB cũng không đạt: "
                f"integrity={integrity}, "
                f"FK={len(fk)}"
            )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--apply",
        action="store_true",
    )
    parser.add_argument(
        "--confirm",
        default="",
    )
    args = parser.parse_args()

    started = time.monotonic()

    print("=" * 126)
    print(
        "V13.6 - THỰC HIỆN THẬT 412 "
        "PHƯƠNG ÁN TOÀN TỈNH"
    )
    print("=" * 126)
    print(
        "Chế độ:",
        "APPLY THẬT"
        if args.apply
        else "PREFLIGHT - KHÔNG GHI",
    )

    for p in (
        DB_PATH,
        PLAN_FILE,
        SERVICE,
    ):
        if not p.exists():
            raise RuntimeError(
                f"Không tìm thấy: {p}"
            )

    if sha256(SERVICE) != EXPECTED_SERVICE_SHA:
        raise RuntimeError(
            "Engine không đúng V13.5.2; dừng."
        )

    if sha256(PLAN_FILE) != EXPECTED_PLAN_SHA:
        raise RuntimeError(
            "Plan JSON đã thay đổi từ V13.5.3; "
            "không chạy thật."
        )

    original_payload, qd, approved = (
        load_registry()
    )
    approved = sorted(
        approved,
        key=plan_sort_key,
    )
    validate_no_chaining(
        approved
    )

    source_ids = source_ids_from(
        approved
    )
    if len(source_ids) != EXPECTED_SOURCE_SCHOOLS:
        raise RuntimeError(
            f"Source schools={len(source_ids)}, "
            f"cần {EXPECTED_SOURCE_SCHOOLS}."
        )

    preflight = validate_fast_preflight(
        approved,
        source_ids,
    )

    print()
    print("PREFLIGHT PASS")
    print(
        f" - QĐ3805 COMPLETED: {len(qd)}"
    )
    print(
        f" - Plan APPROVED: {len(approved)}"
    )
    print(
        f" - Source schools active: "
        f"{preflight['active_sources']}"
    )
    print(
        f" - CBQL/GV/NV tại source: "
        f"{preflight['regular_users']}"
    )
    print(
        f" - Login trường nguồn active: "
        f"{preflight['source_logins']}"
    )
    print(
        f" - DB integrity: "
        f"{preflight['integrity']}"
    )
    print(
        f" - DB FK errors: "
        f"{preflight['fk']}"
    )

    if not args.apply:
        print()
        print(
            "CHƯA GHI DATABASE."
        )
        print(
            "Muốn thực hiện thật, chạy với "
            "--apply và đúng câu xác nhận."
        )
        return 0

    if (
        args.confirm.strip()
        != CONFIRM_PHRASE
    ):
        raise RuntimeError(
            "Sai câu xác nhận. "
            "Database chưa bị sửa."
        )

    stamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )
    backup_dir = (
        EXPORTS
        / (
            "backup_truoc_sap_nhap_"
            f"toan_tinh_v13_6_{stamp}"
        )
    )
    backup_dir.mkdir(
        parents=True,
        exist_ok=False,
    )

    backup_db = (
        backup_dir
        / "phocap.db"
    )
    backup_plan = (
        backup_dir
        / "school_merger_approved_plans.json"
    )

    print()
    print(
        "Đang tạo backup database trước "
        "khi ghi thật...",
        flush=True,
    )

    sqlite_backup(
        DB_PATH,
        backup_db,
    )
    shutil.copy2(
        PLAN_FILE,
        backup_plan,
    )

    with connect_ro(
        backup_db
    ) as chk:
        bi, bf = db_health(
            chk
        )
        if (
            bi.lower() != "ok"
            or bf
        ):
            raise RuntimeError(
                "Backup DB không đạt: "
                f"integrity={bi}, FK={len(bf)}"
            )

    backup_meta = {
        "backup_type": (
            "automatic_before_school_merger_batch"
        ),
        "version": "V13.6",
        "created_at": datetime.now().isoformat(
            timespec="seconds"
        ),
        "school_year_id": EXPECTED_YEAR_ID,
        "school_year_code": EXPECTED_YEAR_CODE,
        "plan_count": EXPECTED_APPROVED,
        "source_school_count": len(
            source_ids
        ),
        "database_backup": str(
            backup_db
        ),
        "plan_backup": str(
            backup_plan
        ),
        "service_sha": EXPECTED_SERVICE_SHA,
        "plan_sha": EXPECTED_PLAN_SHA,
        "confirm_phrase": CONFIRM_PHRASE,
    }
    (
        backup_dir
        / "thong_tin_sap_nhap.json"
    ).write_text(
        json.dumps(
            backup_meta,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    sys.path.insert(
        0,
        str(ROOT),
    )
    from app.services import school_merger_service as merger

    con = sqlite3.connect(
        str(DB_PATH),
        timeout=120,
        factory=BatchConnection,
    )
    con.row_factory = sqlite3.Row
    con.execute(
        "PRAGMA foreign_keys=ON"
    )

    committed = False
    post_db_verified = False
    plan_updated = False

    result_rows = []
    error_rows = []
    totals_by_table: dict[
        str, int
    ] = defaultdict(int)
    total_users_moved = 0
    total_logins_disabled = 0
    total_staff_rollover = 0
    total_sources_deactivated = 0

    try:
        con.execute(
            "BEGIN IMMEDIATE"
        )

        move_year_ids, past_year_ids = (
            merger._year_scope_ids(
                con,
                EXPECTED_YEAR_ID,
            )
        )
        if move_year_ids != [2, 8]:
            raise RuntimeError(
                "CURRENT+FUTURE không còn [2,8]: "
                f"{move_year_ids}"
            )

        previous_year_id = (
            merger._previous_year_id(
                con,
                EXPECTED_YEAR_ID,
            )
        )
        if previous_year_id != 1:
            raise RuntimeError(
                "previous_year_id phải =1; "
                f"hiện={previous_year_id}"
            )

        tables = year_aware_tables(
            con
        )
        past_before = grouped_year_counts(
            con,
            tables,
            source_ids,
            past_year_ids,
        )

        total = len(
            approved
        )
        backup_name = backup_dir.name

        print()
        print(
            "BẮT ĐẦU TRANSACTION TOÀN LÔ 412 PLAN",
            flush=True,
        )

        for idx, plan in enumerate(
            approved,
            start=1,
        ):
            pid = str(
                plan.get("id") or ""
            )
            sources = sorted(
                int(x)
                for x in (
                    plan.get(
                        "source_school_ids"
                    )
                    or []
                )
            )
            target_id = int(
                plan.get(
                    "target_school_id"
                )
                or 0
            )

            if (
                idx == 1
                or idx % 10 == 0
                or idx == total
            ):
                elapsed = (
                    time.monotonic()
                    - started
                )
                print(
                    f"Thực hiện: "
                    f"{idx}/{total} plan "
                    f"| elapsed="
                    f"{elapsed:.1f}s",
                    flush=True,
                )

            savepoint = (
                f"v136_{idx}"
            )
            con.execute(
                f"SAVEPOINT {savepoint}"
            )

            try:
                result = (
                    merger._apply_merge(
                        con,
                        selected_year_id=(
                            EXPECTED_YEAR_ID
                        ),
                        previous_year_id=(
                            previous_year_id
                        ),
                        target_school_id=(
                            target_id
                        ),
                        source_ids=sources,
                        actor_user_id=None,
                        backup_name=backup_name,
                        record_audit=True,
                    )
                )
                con.execute(
                    f"RELEASE SAVEPOINT "
                    f"{savepoint}"
                )

                for item in (
                    result.get(
                        "direct_moves"
                    )
                    or []
                ):
                    table = str(
                        item.get(
                            "table"
                        )
                        or ""
                    )
                    totals_by_table[
                        table
                    ] += int(
                        item.get(
                            "rows"
                        )
                        or 0
                    )

                for item in (
                    result.get(
                        "no_year_moves"
                    )
                    or []
                ):
                    table = str(
                        item.get(
                            "table"
                        )
                        or ""
                    )
                    totals_by_table[
                        table
                    ] += int(
                        item.get(
                            "rows"
                        )
                        or 0
                    )

                users_moved = int(
                    result.get(
                        "users_moved"
                    )
                    or 0
                )
                logins_disabled = int(
                    result.get(
                        "source_school_logins_disabled"
                    )
                    or 0
                )
                rollover = int(
                    result.get(
                        "staff_rollover_created"
                    )
                    or 0
                )
                deactivated = int(
                    result.get(
                        "sources_deactivated"
                    )
                    or 0
                )

                total_users_moved += (
                    users_moved
                )
                total_logins_disabled += (
                    logins_disabled
                )
                total_staff_rollover += (
                    rollover
                )
                total_sources_deactivated += (
                    deactivated
                )

                result_rows.append({
                    "index": idx,
                    "plan_id": pid,
                    "commune_id": int(
                        plan.get(
                            "commune_id"
                        )
                        or 0
                    ),
                    "level_code": str(
                        plan.get(
                            "level_code"
                        )
                        or ""
                    ),
                    "source_school_ids": (
                        ",".join(
                            str(x)
                            for x in sources
                        )
                    ),
                    "target_school_id": (
                        target_id
                    ),
                    "result": "PASS",
                    "users_moved": (
                        users_moved
                    ),
                    "source_logins_disabled": (
                        logins_disabled
                    ),
                    "staff_rollover_created": (
                        rollover
                    ),
                    "sources_deactivated": (
                        deactivated
                    ),
                    "error": "",
                })

            except Exception as exc:
                try:
                    con.execute(
                        f"ROLLBACK TO SAVEPOINT "
                        f"{savepoint}"
                    )
                finally:
                    con.execute(
                        f"RELEASE SAVEPOINT "
                        f"{savepoint}"
                    )

                error_rows.append({
                    "index": idx,
                    "plan_id": pid,
                    "source_school_ids": (
                        ",".join(
                            str(x)
                            for x in sources
                        )
                    ),
                    "target_school_id": (
                        target_id
                    ),
                    "error": repr(
                        exc
                    ),
                })
                raise

        # Hậu kiểm toàn lô TRƯỚC COMMIT.
        past_after = grouped_year_counts(
            con,
            tables,
            source_ids,
            past_year_ids,
        )
        if past_after != past_before:
            changed = [
                key
                for key in (
                    set(past_before)
                    | set(past_after)
                )
                if int(
                    past_before.get(
                        key, 0
                    )
                )
                != int(
                    past_after.get(
                        key, 0
                    )
                )
            ]
            raise RuntimeError(
                "PAST đã thay đổi tại "
                f"{len(changed)} table/year."
            )

        move_after = grouped_year_counts(
            con,
            tables,
            source_ids,
            move_year_ids,
        )
        residual = sum(
            int(x)
            for x in move_after.values()
        )
        if residual:
            raise RuntimeError(
                "CURRENT/FUTURE còn "
                f"{residual} dòng tại source."
            )

        active_sources_after = (
            count_sources_active(
                con,
                source_ids,
            )
        )
        if active_sources_after != 0:
            raise RuntimeError(
                f"Còn {active_sources_after} "
                "source active."
            )

        (
            regular_users_after,
            active_logins_after,
        ) = source_user_counts(
            con,
            source_ids,
        )

        if regular_users_after:
            raise RuntimeError(
                f"Còn {regular_users_after} "
                "CBQL/GV/NV tại source."
            )
        if active_logins_after:
            raise RuntimeError(
                f"Còn {active_logins_after} "
                "login trường nguồn active."
            )

        operation_count = int(
            con.execute(
                "SELECT COUNT(*) "
                "FROM school_merger_operations "
                "WHERE backup_name=?",
                (backup_name,),
            ).fetchone()[0]
            or 0
        )
        if operation_count != EXPECTED_APPROVED:
            raise RuntimeError(
                "Audit operations của lô="
                f"{operation_count}, cần 412."
            )

        print(
            "Đang chạy integrity_check + "
            "foreign_key_check thật trước COMMIT...",
            flush=True,
        )
        integrity_precommit = (
            real_integrity(
                con
            )
        )
        fk_precommit = real_fk(
            con
        )

        if (
            integrity_precommit.lower()
            != "ok"
            or fk_precommit
        ):
            raise RuntimeError(
                "Hậu kiểm trước COMMIT lỗi: "
                f"integrity="
                f"{integrity_precommit}, "
                f"FK={len(fk_precommit)}"
            )

        # Kiểm tra tổng nghiệp vụ đúng mô phỏng.
        if (
            total_users_moved
            != EXPECTED_SIM_USERS_MOVED
        ):
            raise RuntimeError(
                "users_moved khác mô phỏng: "
                f"{total_users_moved} != "
                f"{EXPECTED_SIM_USERS_MOVED}"
            )
        if (
            total_logins_disabled
            != EXPECTED_SIM_LOGINS_DISABLED
        ):
            raise RuntimeError(
                "logins_disabled khác mô phỏng: "
                f"{total_logins_disabled} != "
                f"{EXPECTED_SIM_LOGINS_DISABLED}"
            )
        if (
            total_staff_rollover
            != EXPECTED_SIM_STAFF_ROLLOVER
        ):
            raise RuntimeError(
                "staff_rollover khác mô phỏng: "
                f"{total_staff_rollover} != "
                f"{EXPECTED_SIM_STAFF_ROLLOVER}"
            )
        if (
            total_sources_deactivated
            != EXPECTED_SIM_SOURCES_DEACTIVATED
        ):
            raise RuntimeError(
                "sources_deactivated khác mô phỏng: "
                f"{total_sources_deactivated} != "
                f"{EXPECTED_SIM_SOURCES_DEACTIVATED}"
            )

        con.commit()
        committed = True

        # Hậu kiểm sau COMMIT trên chính DB thật.
        con.defer_heavy_pragmas = False
        integrity_post = str(
            con.execute(
                "PRAGMA integrity_check"
            ).fetchone()[0]
        )
        fk_post = con.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()

        if (
            integrity_post.lower()
            != "ok"
            or fk_post
        ):
            raise RuntimeError(
                "DB đã COMMIT nhưng post-check lỗi: "
                f"integrity={integrity_post}, "
                f"FK={len(fk_post)}"
            )

        post_db_verified = True

    except Exception:
        if not committed:
            try:
                con.rollback()
            except Exception:
                pass
        else:
            # Chỉ restore DB nếu DB đã commit nhưng chưa vượt post-check.
            if not post_db_verified:
                con.close()
                con = None
                print(
                    "Post-check sau COMMIT không đạt. "
                    "Đang tự RESTORE DB từ backup...",
                    flush=True,
                )
                restore_db_from_backup(
                    backup_db
                )
                shutil.copy2(
                    backup_plan,
                    PLAN_FILE,
                )
        raise

    finally:
        if con is not None:
            try:
                con.close()
            except Exception:
                pass

    # DB đã COMMIT và post-check PASS. Bây giờ mới cập nhật Plan JSON.
    approved_ids = {
        str(p.get("id") or "")
        for p in approved
    }

    completed_payload = build_completed_payload(
        original_payload,
        approved_ids,
        backup_name=backup_dir.name,
    )

    try:
        atomic_write_json(
            PLAN_FILE,
            completed_payload,
        )
        qd_after, province_after = (
            validate_completed_registry()
        )
        plan_updated = True
    except Exception as exc:
        # DB đã an toàn + 412 audit operations tồn tại.
        # Không restore DB để tránh hoàn tác một migration đã được post-check.
        emergency = (
            backup_dir
            / "CAN_DONG_BO_PLAN_JSON_SAU_V13_6.txt"
        )
        emergency.write_text(
            "\n".join([
                "V13.6: DATABASE ĐÃ COMMIT VÀ POST-CHECK PASS.",
                "Nhưng bước ghi Plan JSON thất bại.",
                f"Lỗi: {repr(exc)}",
                "",
                "KHÔNG chạy lại 412 phương án.",
                "school_merger_operations đã có đủ 412 operation;",
                "trạng thái hiệu lực của engine vì vậy là COMPLETED.",
                "",
                f"Backup Plan JSON: {backup_plan}",
                f"Backup DB: {backup_db}",
            ]),
            encoding="utf-8",
        )
        raise RuntimeError(
            "DATABASE đã sáp nhập thành công và post-check PASS, "
            "nhưng ghi Plan JSON thất bại. "
            "KHÔNG CHẠY LẠI V13.6. "
            f"Xem {emergency}"
        ) from exc

    # Audit cuối cùng sau cả DB + plan.
    with connect_ro(DB_PATH) as final_con:
        final_integrity, final_fk = db_health(
            final_con
        )
        final_active_sources = (
            count_sources_active(
                final_con,
                source_ids,
            )
        )
        (
            final_regular_users,
            final_active_logins,
        ) = source_user_counts(
            final_con,
            source_ids,
        )

        # 412 operations exact theo backup_name.
        final_operations = int(
            final_con.execute(
                "SELECT COUNT(*) "
                "FROM school_merger_operations "
                "WHERE backup_name=?",
                (backup_dir.name,),
            ).fetchone()[0]
            or 0
        )

    if (
        final_integrity.lower() != "ok"
        or final_fk
        or final_active_sources != 0
        or final_regular_users != 0
        or final_active_logins != 0
        or final_operations != 412
    ):
        raise RuntimeError(
            "Audit cuối V13.6 không đạt dù DB đã commit. "
            "KHÔNG chạy lại; dùng backup và kiểm tra thủ công."
        )

    stamp_done = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )
    report_dir = (
        ROOT
        / f"bao_cao_v13_6_sap_nhap_that_412_{stamp_done}"
    )
    zip_path = (
        ROOT
        / f"bao_cao_v13_6_sap_nhap_that_412_{stamp_done}.zip"
    )
    report_dir.mkdir(
        parents=True,
        exist_ok=False,
    )

    write_csv(
        report_dir
        / "740_KET_QUA_412_PLAN.csv",
        [
            "index",
            "plan_id",
            "commune_id",
            "level_code",
            "source_school_ids",
            "target_school_id",
            "result",
            "users_moved",
            "source_logins_disabled",
            "staff_rollover_created",
            "sources_deactivated",
            "error",
        ],
        result_rows,
    )

    write_csv(
        report_dir
        / "741_LOI_THUC_HIEN.csv",
        [
            "index",
            "plan_id",
            "source_school_ids",
            "target_school_id",
            "error",
        ],
        error_rows,
    )

    write_csv(
        report_dir
        / "742_TONG_CHUYEN_THEO_BANG.csv",
        [
            "table",
            "rows_moved",
        ],
        [
            {
                "table": table,
                "rows_moved": rows,
            }
            for table, rows in sorted(
                totals_by_table.items()
            )
        ],
    )

    gate_rows = [
        {
            "check": "service_sha",
            "result": "PASS",
            "detail": EXPECTED_SERVICE_SHA,
        },
        {
            "check": "plans_executed",
            "result": "PASS",
            "detail": "412/412",
        },
        {
            "check": "users_moved",
            "result": "PASS",
            "detail": str(
                total_users_moved
            ),
        },
        {
            "check": "source_logins_disabled",
            "result": "PASS",
            "detail": str(
                total_logins_disabled
            ),
        },
        {
            "check": "staff_rollover_created",
            "result": "PASS",
            "detail": str(
                total_staff_rollover
            ),
        },
        {
            "check": "sources_deactivated",
            "result": "PASS",
            "detail": str(
                total_sources_deactivated
            ),
        },
        {
            "check": "school_merger_operations",
            "result": "PASS",
            "detail": str(
                final_operations
            ),
        },
        {
            "check": "qd3805_completed",
            "result": "PASS",
            "detail": str(
                qd_after
            ),
        },
        {
            "check": "province_completed",
            "result": "PASS",
            "detail": str(
                province_after
            ),
        },
        {
            "check": "source_active_after",
            "result": "PASS",
            "detail": str(
                final_active_sources
            ),
        },
        {
            "check": "source_regular_users_after",
            "result": "PASS",
            "detail": str(
                final_regular_users
            ),
        },
        {
            "check": "source_active_logins_after",
            "result": "PASS",
            "detail": str(
                final_active_logins
            ),
        },
        {
            "check": "db_integrity",
            "result": (
                "PASS"
                if final_integrity.lower()
                == "ok"
                else "FAIL"
            ),
            "detail": final_integrity,
        },
        {
            "check": "db_foreign_key",
            "result": (
                "PASS"
                if not final_fk
                else "FAIL"
            ),
            "detail": str(
                len(final_fk)
            ),
        },
        {
            "check": "V13_6_BATCH_MERGER_CLOSED",
            "result": "YES",
            "detail": (
                "412 phương án đã thực hiện + "
                "đánh dấu COMPLETED."
            ),
        },
    ]

    write_csv(
        report_dir
        / "743_GATE_V13_6.csv",
        [
            "check",
            "result",
            "detail",
        ],
        gate_rows,
    )

    elapsed = (
        time.monotonic()
        - started
    )

    summary = f"""V13.6 - THỰC HIỆN THẬT 412 PHƯƠNG ÁN TOÀN TỈNH
================================================================================

STATUS=SUCCESS

Năm sáp nhập:
- CURRENT: 2026-2027 / id=2
- CURRENT+FUTURE: [2,8]
- PAST: giữ nguyên

Phương án:
- QĐ3805 COMPLETED: {qd_after}
- Toàn tỉnh vừa thực hiện: 412/412
- Toàn tỉnh COMPLETED: {province_after}
- Tổng COMPLETED trong hai nhóm: {qd_after + province_after}

Trường nguồn:
- Source schools: {len(source_ids)}
- Active sau: {final_active_sources}

Tài khoản:
- CBQL/GV/NV moved: {total_users_moved}
- Login trường nguồn disabled: {total_logins_disabled}
- CBQL/GV/NV còn tại source: {final_regular_users}
- Login nguồn active còn lại: {final_active_logins}

Đội ngũ:
- staff rollover created: {total_staff_rollover}

Audit:
- school_merger_operations của batch: {final_operations}

Database:
- integrity_check: {final_integrity}
- foreign_key_check: {len(final_fk)}

Backup trước V13.6:
{backup_dir}

Database backup:
{backup_db}

Plan backup:
{backup_plan}

Thời gian:
{elapsed:.1f} giây

V13_6_BATCH_MERGER_CLOSED=YES
"""

    (
        report_dir
        / "00_TONG_QUAN_V13_6.txt"
    ).write_text(
        summary,
        encoding="utf-8",
    )

    with zipfile.ZipFile(
        zip_path,
        "w",
        compression=zipfile.ZIP_DEFLATED,
    ) as zf:
        for p in sorted(
            report_dir.iterdir()
        ):
            if p.is_file():
                zf.write(
                    p,
                    arcname=p.name,
                )

    print()
    print("=" * 126)
    print("V13.6 THÀNH CÔNG")
    print("=" * 126)
    print("412/412 plan: COMPLETED")
    print(
        f"483 source inactive: "
        f"{final_active_sources == 0}"
    )
    print(
        f"Users moved: "
        f"{total_users_moved}"
    )
    print(
        "Source school logins disabled: "
        f"{total_logins_disabled}"
    )
    print(
        "Staff rollover created: "
        f"{total_staff_rollover}"
    )
    print(
        f"Audit operations: "
        f"{final_operations}"
    )
    print(
        f"QĐ3805 COMPLETED: "
        f"{qd_after}"
    )
    print(
        "Province plans COMPLETED: "
        f"{province_after}"
    )
    print(
        f"DB integrity: "
        f"{final_integrity}"
    )
    print(
        f"DB FK errors: "
        f"{len(final_fk)}"
    )
    print(
        "V13_6_BATCH_MERGER_CLOSED: YES"
    )
    print(
        f"Backup: {backup_dir}"
    )
    print(
        f"ZIP kết quả: {zip_path}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(
            main()
        )
    except KeyboardInterrupt:
        print()
        print(
            "Đã dừng theo yêu cầu."
        )
        print(
            "Nếu đang APPLY, hãy kiểm tra "
            "terminal/backup trước khi chạy lại."
        )
        raise SystemExit(130)
    except Exception as exc:
        print()
        print("=" * 126)
        print("V13.6 DỪNG AN TOÀN")
        print("=" * 126)
        print(repr(exc))
        print(
            "Nếu lỗi xảy ra trước COMMIT: "
            "toàn lô đã rollback."
        )
        print(
            "Nếu thông báo nói DATABASE đã "
            "commit nhưng Plan JSON lỗi: "
            "KHÔNG chạy lại V13.6."
        )
        raise SystemExit(2)
