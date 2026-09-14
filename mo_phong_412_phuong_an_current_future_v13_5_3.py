# -*- coding: utf-8 -*-
r"""
V13.5.3 - MÔ PHỎNG 412 PHƯƠNG ÁN BẰNG ENGINE CURRENT + FUTURE
==============================================================

MỤC TIÊU
--------
Kiểm thử tích lũy toàn bộ 412 plan APPROVED trên đúng engine V13.5.2
trước khi cho phép sáp nhập thật.

AN TOÀN
-------
- Database thật mở READ-ONLY.
- Sao chép database thật vào RAM đúng 1 lần.
- Chỉ sửa bản RAM.
- KHÔNG sửa school_merger_approved_plans.json.
- KHÔNG đổi trạng thái plan.
- KHÔNG tạo backup DB thật vì không có thao tác ghi thật.

TỐI ƯU
------
Trong từng nhóm, mọi hậu kiểm nghiệp vụ của _apply_merge vẫn chạy.
Riêng hai full-scan PRAGMA integrity_check / foreign_key_check bên trong
mỗi nhóm được hoãn lại để tránh quét toàn DB 412 lần.
Sau khi mô phỏng xong toàn lô, V13.5.3 chạy integrity_check và
foreign_key_check THẬT một lần trên trạng thái RAM cuối cùng.

GATE PASS YÊU CẦU
-----------------
- Service SHA đúng V13.5.2.
- 6 QĐ3805 vẫn COMPLETED.
- 412 plan toàn tỉnh vẫn APPROVED.
- 412/412 nhóm mô phỏng PASS.
- Không còn CURRENT/FUTURE tại source ở mọi bảng có school_id+school_year_id.
- Dữ liệu PAST tại source không thay đổi.
- Tất cả source được inactive trong RAM.
- Không còn CBQL/GV/NV tại source; login trường nguồn không còn active.
- RAM integrity_check = ok.
- RAM foreign_key_check = 0.

CHẠY
----
cd C:\PhoCap
.\.venv\Scripts\python.exe .\mo_phong_412_phuong_an_current_future_v13_5_3.py
"""

from __future__ import annotations

import csv
import hashlib
import json
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

EXPECTED_SERVICE_SHA = (
    "414fb49a4c5f4fed7b571cc55df381678fe660cd8a675ecaa2f6fd70ebd7827a"
)
EXPECTED_PLAN_SHA = (
    "004fdaa536f8229dcfce51d02031941aa639a7cace8927e4b5cb3c86985d30cf"
)
EXPECTED_YEAR_ID = 2
EXPECTED_YEAR_CODE = "2026-2027"
EXPECTED_QD3805_COMPLETED = 6
EXPECTED_APPROVED = 412


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
    payload = json.loads(PLAN_FILE.read_text(encoding="utf-8"))
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
        and str(p.get("status") or "").upper() == "COMPLETED"
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

    if len(qd) != EXPECTED_QD3805_COMPLETED:
        raise RuntimeError(
            f"QĐ3805 COMPLETED phải =6; hiện={len(qd)}."
        )
    if len(approved) != EXPECTED_APPROVED:
        raise RuntimeError(
            f"Plan toàn tỉnh APPROVED phải =412; hiện={len(approved)}."
        )

    return payload, qd, approved


def normalize_plan_for_sort(p: dict) -> tuple:
    return (
        int(p.get("commune_id") or 0),
        str(p.get("level_code") or ""),
        int(p.get("target_school_id") or 0),
        tuple(sorted(int(x) for x in p.get("source_school_ids") or [])),
        str(p.get("id") or ""),
    )


def involved_source_ids(plans: list[dict]) -> list[int]:
    return sorted({
        int(sid)
        for p in plans
        for sid in (p.get("source_school_ids") or [])
    })


class _FakeCursor:
    def __init__(self, rows):
        self._rows = list(rows)
        self.rowcount = -1

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)


class SimulationConnection(sqlite3.Connection):
    """
    Hoãn 2 full-scan PRAGMA bên trong từng _apply_merge.
    Các SQL nghiệp vụ và hậu kiểm residual/users vẫn chạy thật trên RAM.
    """
    defer_heavy_pragmas = True

    def execute(self, sql, parameters=(), /):
        normalized = " ".join(str(sql).strip().lower().split())

        if self.defer_heavy_pragmas:
            if normalized == "pragma foreign_key_check":
                return _FakeCursor([])
            if normalized == "pragma integrity_check":
                return _FakeCursor([("ok",)])

        return super().execute(sql, parameters)


def real_integrity(mem: SimulationConnection) -> str:
    old = mem.defer_heavy_pragmas
    mem.defer_heavy_pragmas = False
    try:
        return str(mem.execute("PRAGMA integrity_check").fetchone()[0])
    finally:
        mem.defer_heavy_pragmas = old


def real_fk(mem: SimulationConnection) -> list:
    old = mem.defer_heavy_pragmas
    mem.defer_heavy_pragmas = False
    try:
        return mem.execute("PRAGMA foreign_key_check").fetchall()
    finally:
        mem.defer_heavy_pragmas = old


def year_aware_tables(con: sqlite3.Connection) -> list[str]:
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
        if {"school_id", "school_year_id"} <= cols:
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

    # Chia source thành block để không phụ thuộc SQLITE_MAX_VARIABLE_NUMBER.
    chunk_size = 700

    for table in tables:
        totals: dict[int, int] = defaultdict(int)

        for start in range(0, len(source_ids), chunk_size):
            chunk = source_ids[start:start + chunk_size]

            sql = (
                f"SELECT school_year_id,COUNT(*) "
                f"FROM {qident(table)} "
                f"WHERE school_id IN ({markers(len(chunk))}) "
                f"AND school_year_id IN ({markers(len(year_ids))}) "
                f"GROUP BY school_year_id"
            )
            rows = con.execute(
                sql,
                [*chunk, *year_ids],
            ).fetchall()

            for row in rows:
                totals[int(row[0])] += int(row[1] or 0)

        for year_id, n in totals.items():
            result[(table, year_id)] = n

    return result


def active_source_count(
    con: sqlite3.Connection,
    source_ids: list[int],
) -> int:
    total = 0
    chunk_size = 700
    for start in range(0, len(source_ids), chunk_size):
        chunk = source_ids[start:start + chunk_size]
        total += int(
            con.execute(
                f"SELECT COUNT(*) FROM schools "
                f"WHERE id IN ({markers(len(chunk))}) AND is_active=1",
                chunk,
            ).fetchone()[0] or 0
        )
    return total


def source_user_counts(
    con: sqlite3.Connection,
    source_ids: list[int],
) -> tuple[int, int]:
    if not source_ids:
        return 0, 0

    regular = 0
    active_school_logins = 0
    chunk_size = 700

    for start in range(0, len(source_ids), chunk_size):
        chunk = source_ids[start:start + chunk_size]

        regular += int(
            con.execute(
                f"SELECT COUNT(*) FROM users "
                f"WHERE school_id IN ({markers(len(chunk))}) "
                "AND username NOT LIKE 'truong_%'",
                chunk,
            ).fetchone()[0] or 0
        )

        active_school_logins += int(
            con.execute(
                f"SELECT COUNT(*) FROM users "
                f"WHERE school_id IN ({markers(len(chunk))}) "
                "AND username LIKE 'truong_%' AND is_active=1",
                chunk,
            ).fetchone()[0] or 0
        )

    return regular, active_school_logins


def main() -> int:
    started = time.monotonic()

    print("=" * 126)
    print("V13.5.3 - MÔ PHỎNG 412 PHƯƠNG ÁN CURRENT + FUTURE")
    print("=" * 126)
    print("DB thật: READ-ONLY")
    print("Plan JSON: KHÔNG GHI")

    for p in (DB_PATH, PLAN_FILE, SERVICE):
        if not p.exists():
            raise RuntimeError(f"Không tìm thấy: {p}")

    service_sha = sha256(SERVICE)
    if service_sha != EXPECTED_SERVICE_SHA:
        raise RuntimeError(
            "Engine không đúng V13.5.2.\n"
            f"SHA hiện={service_sha}\n"
            f"SHA cần={EXPECTED_SERVICE_SHA}"
        )

    plan_sha_before = sha256(PLAN_FILE)
    if plan_sha_before != EXPECTED_PLAN_SHA:
        raise RuntimeError(
            "Plan JSON đã thay đổi so với V13.5.2; dừng.\n"
            f"SHA hiện={plan_sha_before}\n"
            f"SHA cần={EXPECTED_PLAN_SHA}"
        )

    payload, qd, approved = load_registry()
    approved = sorted(approved, key=normalize_plan_for_sort)
    source_ids = involved_source_ids(approved)

    # Không cho source overlap giữa 412 plan.
    owner: dict[int, str] = {}
    overlaps = []
    for p in approved:
        pid = str(p.get("id") or "")
        for sid in p.get("source_school_ids") or []:
            sid = int(sid)
            if sid in owner:
                overlaps.append((sid, owner[sid], pid))
            else:
                owner[sid] = pid

    if overlaps:
        raise RuntimeError(
            f"412 plan có {len(overlaps)} source overlap nội bộ."
        )

    sys.path.insert(0, str(ROOT))
    from app.services import school_merger_service as merger

    # Kiểm tra code năm ngay trên DB thật.
    uri = DB_PATH.resolve().as_uri() + "?mode=ro"
    src = sqlite3.connect(uri, uri=True, timeout=60)
    src.row_factory = sqlite3.Row
    src.execute("PRAGMA query_only=ON")

    try:
        year = src.execute(
            "SELECT id,code,name FROM school_years WHERE id=?",
            (EXPECTED_YEAR_ID,),
        ).fetchone()
        if not year or clean(year["code"]) != EXPECTED_YEAR_CODE:
            raise RuntimeError(
                "school_year_id=2 không còn là 2026-2027."
            )

        real_integrity_before = str(
            src.execute("PRAGMA integrity_check").fetchone()[0]
        )
        real_fk_before = src.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()

        if real_integrity_before.lower() != "ok" or real_fk_before:
            raise RuntimeError(
                f"DB thật preflight lỗi: integrity={real_integrity_before}, "
                f"FK={len(real_fk_before)}"
            )

        # Sao chép đúng 1 lần vào RAM.
        print("Đang sao chép database vào RAM đúng 1 lần...", flush=True)

        mem = sqlite3.connect(
            ":memory:",
            factory=SimulationConnection,
        )
        mem.row_factory = sqlite3.Row

        try:
            src.backup(mem)
        finally:
            src.close()

        mem.execute("PRAGMA foreign_keys=ON")

        move_year_ids, past_year_ids = merger._year_scope_ids(
            mem,
            EXPECTED_YEAR_ID,
        )
        if move_year_ids != [2, 8]:
            raise RuntimeError(
                f"CURRENT+FUTURE phải [2,8]; thực tế={move_year_ids}"
            )

        previous_year_id = merger._previous_year_id(
            mem,
            EXPECTED_YEAR_ID,
        )
        if previous_year_id != 1:
            raise RuntimeError(
                f"Năm trước 2026-2027 phải id=1; thực tế={previous_year_id}"
            )

        tables = year_aware_tables(mem)

        past_before = grouped_year_counts(
            mem,
            tables,
            source_ids,
            past_year_ids,
        )
        move_before = grouped_year_counts(
            mem,
            tables,
            source_ids,
            move_year_ids,
        )

        active_sources_before = active_source_count(
            mem,
            source_ids,
        )

        result_rows = []
        error_rows = []
        totals_by_table: dict[str, int] = defaultdict(int)
        total_users_moved = 0
        total_logins_disabled = 0
        total_staff_rollover = 0
        total_sources_deactivated = 0

        mem.execute("BEGIN")

        total = len(approved)

        for idx, p in enumerate(approved, start=1):
            pid = str(p.get("id") or "")
            source_group = sorted(
                int(x)
                for x in p.get("source_school_ids") or []
            )
            target_id = int(p.get("target_school_id") or 0)

            if (
                idx == 1
                or idx % 10 == 0
                or idx == total
            ):
                elapsed = time.monotonic() - started
                print(
                    f"Mô phỏng: {idx}/{total} plan "
                    f"| elapsed={elapsed:.1f}s",
                    flush=True,
                )

            savepoint = f"v1353_{idx}"
            mem.execute(f"SAVEPOINT {savepoint}")

            try:
                result = merger._apply_merge(
                    mem,
                    selected_year_id=EXPECTED_YEAR_ID,
                    previous_year_id=previous_year_id,
                    target_school_id=target_id,
                    source_ids=source_group,
                    actor_user_id=None,
                    backup_name="V13.5.3-RAM-SIMULATION",
                    record_audit=False,
                )

                mem.execute(f"RELEASE SAVEPOINT {savepoint}")

                for item in result.get("direct_moves") or []:
                    totals_by_table[str(item.get("table") or "")] += int(
                        item.get("rows") or 0
                    )

                for item in result.get("no_year_moves") or []:
                    totals_by_table[str(item.get("table") or "")] += int(
                        item.get("rows") or 0
                    )

                total_users_moved += int(
                    result.get("users_moved") or 0
                )
                total_logins_disabled += int(
                    result.get("source_school_logins_disabled") or 0
                )
                total_staff_rollover += int(
                    result.get("staff_rollover_created") or 0
                )
                total_sources_deactivated += int(
                    result.get("sources_deactivated") or 0
                )

                result_rows.append({
                    "index": idx,
                    "plan_id": pid,
                    "commune_id": int(p.get("commune_id") or 0),
                    "level_code": str(p.get("level_code") or ""),
                    "source_school_ids": ",".join(
                        str(x) for x in source_group
                    ),
                    "target_school_id": target_id,
                    "result": "PASS",
                    "users_moved": int(
                        result.get("users_moved") or 0
                    ),
                    "source_logins_disabled": int(
                        result.get(
                            "source_school_logins_disabled"
                        ) or 0
                    ),
                    "staff_rollover_created": int(
                        result.get("staff_rollover_created") or 0
                    ),
                    "sources_deactivated": int(
                        result.get("sources_deactivated") or 0
                    ),
                    "error": "",
                })

            except Exception as exc:
                try:
                    mem.execute(
                        f"ROLLBACK TO SAVEPOINT {savepoint}"
                    )
                finally:
                    mem.execute(
                        f"RELEASE SAVEPOINT {savepoint}"
                    )

                error = repr(exc)

                result_rows.append({
                    "index": idx,
                    "plan_id": pid,
                    "commune_id": int(p.get("commune_id") or 0),
                    "level_code": str(p.get("level_code") or ""),
                    "source_school_ids": ",".join(
                        str(x) for x in source_group
                    ),
                    "target_school_id": target_id,
                    "result": "FAIL",
                    "users_moved": "",
                    "source_logins_disabled": "",
                    "staff_rollover_created": "",
                    "sources_deactivated": "",
                    "error": error,
                })

                error_rows.append({
                    "index": idx,
                    "plan_id": pid,
                    "commune_id": int(p.get("commune_id") or 0),
                    "source_school_ids": ",".join(
                        str(x) for x in source_group
                    ),
                    "target_school_id": target_id,
                    "error": error,
                })

        # Snapshot cuối trên RAM.
        past_after = grouped_year_counts(
            mem,
            tables,
            source_ids,
            past_year_ids,
        )
        move_after = grouped_year_counts(
            mem,
            tables,
            source_ids,
            move_year_ids,
        )

        active_sources_after = active_source_count(
            mem,
            source_ids,
        )

        regular_users_after, active_source_logins_after = (
            source_user_counts(mem, source_ids)
        )

        # Full DB checks thật duy nhất ở trạng thái RAM cuối.
        print(
            "Đang chạy integrity_check + foreign_key_check thật "
            "trên trạng thái RAM cuối...",
            flush=True,
        )
        ram_integrity = real_integrity(mem)
        ram_fk = real_fk(mem)

        # Không commit RAM; rollback trước khi đóng.
        mem.rollback()

    finally:
        try:
            mem.close()
        except Exception:
            pass
        try:
            src.close()
        except Exception:
            pass

    # So sánh PAST.
    past_keys = sorted(set(past_before) | set(past_after))
    past_rows = []
    past_changed = 0

    for key in past_keys:
        table, year_id = key
        before = int(past_before.get(key, 0))
        after = int(past_after.get(key, 0))
        same = before == after
        if not same:
            past_changed += 1
        past_rows.append({
            "table": table,
            "school_year_id": year_id,
            "before": before,
            "after": after,
            "result": "PASS" if same else "FAIL",
        })

    # CURRENT/FUTURE residual.
    move_keys = sorted(set(move_before) | set(move_after))
    residual_rows = []
    residual_total = 0

    for key in move_keys:
        table, year_id = key
        before = int(move_before.get(key, 0))
        after = int(move_after.get(key, 0))
        residual_total += after
        residual_rows.append({
            "table": table,
            "school_year_id": year_id,
            "before_at_source": before,
            "after_at_source": after,
            "result": "PASS" if after == 0 else "FAIL",
        })

    passed_count = sum(
        1 for r in result_rows
        if r["result"] == "PASS"
    )

    # Registry file phải tuyệt đối không đổi.
    plan_sha_after = sha256(PLAN_FILE)
    plan_unchanged = plan_sha_after == plan_sha_before

    ready_for_real_merge = (
        passed_count == EXPECTED_APPROVED
        and not error_rows
        and residual_total == 0
        and past_changed == 0
        and active_sources_after == 0
        and regular_users_after == 0
        and active_source_logins_after == 0
        and ram_integrity.lower() == "ok"
        and len(ram_fk) == 0
        and plan_unchanged
    )

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_dir = ROOT / f"bao_cao_v13_5_3_mo_phong_412_{stamp}"
    zip_path = ROOT / f"bao_cao_v13_5_3_mo_phong_412_{stamp}.zip"
    report_dir.mkdir(parents=True, exist_ok=False)

    write_csv(
        report_dir / "730_KET_QUA_412_PLAN.csv",
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
        report_dir / "731_LOI_MO_PHONG.csv",
        [
            "index",
            "plan_id",
            "commune_id",
            "source_school_ids",
            "target_school_id",
            "error",
        ],
        error_rows,
    )

    write_csv(
        report_dir / "732_TONG_CHUYEN_THEO_BANG.csv",
        ["table", "rows_moved"],
        [
            {"table": table, "rows_moved": n}
            for table, n in sorted(totals_by_table.items())
        ],
    )

    write_csv(
        report_dir / "733_PAST_GIU_NGUYEN.csv",
        [
            "table",
            "school_year_id",
            "before",
            "after",
            "result",
        ],
        past_rows,
    )

    write_csv(
        report_dir / "734_CURRENT_FUTURE_RESIDUAL.csv",
        [
            "table",
            "school_year_id",
            "before_at_source",
            "after_at_source",
            "result",
        ],
        residual_rows,
    )

    gate_rows = [
        {
            "check": "service_v13_5_2_sha",
            "result": "PASS",
            "detail": service_sha,
        },
        {
            "check": "qd3805_completed",
            "result": "PASS",
            "detail": str(len(qd)),
        },
        {
            "check": "province_approved",
            "result": "PASS",
            "detail": str(len(approved)),
        },
        {
            "check": "current_future_year_ids",
            "result": "PASS" if move_year_ids == [2, 8] else "FAIL",
            "detail": repr(move_year_ids),
        },
        {
            "check": "simulation_passed",
            "result": (
                "PASS"
                if passed_count == EXPECTED_APPROVED
                else "FAIL"
            ),
            "detail": f"{passed_count}/{EXPECTED_APPROVED}",
        },
        {
            "check": "simulation_errors",
            "result": "PASS" if not error_rows else "FAIL",
            "detail": str(len(error_rows)),
        },
        {
            "check": "past_unchanged",
            "result": "PASS" if past_changed == 0 else "FAIL",
            "detail": str(past_changed),
        },
        {
            "check": "current_future_source_residual",
            "result": "PASS" if residual_total == 0 else "FAIL",
            "detail": str(residual_total),
        },
        {
            "check": "active_sources_after",
            "result": "PASS" if active_sources_after == 0 else "FAIL",
            "detail": (
                f"before={active_sources_before}; "
                f"after={active_sources_after}"
            ),
        },
        {
            "check": "regular_users_at_source_after",
            "result": "PASS" if regular_users_after == 0 else "FAIL",
            "detail": str(regular_users_after),
        },
        {
            "check": "active_school_logins_at_source_after",
            "result": (
                "PASS"
                if active_source_logins_after == 0
                else "FAIL"
            ),
            "detail": str(active_source_logins_after),
        },
        {
            "check": "ram_integrity",
            "result": (
                "PASS"
                if ram_integrity.lower() == "ok"
                else "FAIL"
            ),
            "detail": ram_integrity,
        },
        {
            "check": "ram_foreign_key",
            "result": "PASS" if not ram_fk else "FAIL",
            "detail": str(len(ram_fk)),
        },
        {
            "check": "plan_json_unchanged",
            "result": "PASS" if plan_unchanged else "FAIL",
            "detail": plan_sha_after,
        },
        {
            "check": "READY_FOR_REAL_BATCH_MERGE",
            "result": "YES" if ready_for_real_merge else "NO",
            "detail": (
                "Có thể chuẩn bị V13.6 chạy thật toàn lô."
                if ready_for_real_merge
                else "Chưa được chạy thật; xem các gate FAIL."
            ),
        },
    ]

    write_csv(
        report_dir / "735_GATE_V13_5_3.csv",
        ["check", "result", "detail"],
        gate_rows,
    )

    elapsed = time.monotonic() - started

    summary = f"""V13.5.3 - MÔ PHỎNG 412 PHƯƠNG ÁN CURRENT + FUTURE
===============================================================================

STATUS={'PASS' if ready_for_real_merge else 'REVIEW'}

Engine SHA:
{service_sha}

Năm sáp nhập:
- CURRENT = 2026-2027 / id=2
- CURRENT+FUTURE ids = {move_year_ids}
- PAST ids = {past_year_ids}
- previous_year_id = {previous_year_id}

Registry:
- QĐ3805 COMPLETED = {len(qd)}
- Toàn tỉnh APPROVED = {len(approved)}

Mô phỏng:
- PASS = {passed_count}/{EXPECTED_APPROVED}
- Errors = {len(error_rows)}
- Source schools = {len(source_ids)}
- Source active trước = {active_sources_before}
- Source active sau = {active_sources_after}

Dữ liệu:
- CURRENT/FUTURE residual tại source = {residual_total}
- PAST count thay đổi = {past_changed}
- CBQL/GV/NV còn tại source = {regular_users_after}
- Login trường nguồn active còn lại = {active_source_logins_after}

Tổng nghiệp vụ:
- users moved = {total_users_moved}
- source school logins disabled = {total_logins_disabled}
- staff rollover created = {total_staff_rollover}
- sources deactivated = {total_sources_deactivated}

RAM cuối:
- integrity_check = {ram_integrity}
- foreign_key_check = {len(ram_fk)}

Plan JSON:
- SHA trước = {plan_sha_before}
- SHA sau   = {plan_sha_after}
- unchanged = {plan_unchanged}

Thời gian mô phỏng = {elapsed:.1f} giây

READY_FOR_REAL_BATCH_MERGE = {'YES' if ready_for_real_merge else 'NO'}

Database thật: KHÔNG THAY ĐỔI.
Plan JSON: KHÔNG THAY ĐỔI.
"""

    (report_dir / "00_TONG_QUAN_V13_5_3.txt").write_text(
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
    print("HOÀN THÀNH V13.5.3")
    print("=" * 126)
    print(f"Simulation PASS: {passed_count}/{EXPECTED_APPROVED}")
    print(f"Simulation errors: {len(error_rows)}")
    print(f"CURRENT/FUTURE residual tại source: {residual_total}")
    print(f"PAST thay đổi: {past_changed}")
    print(f"Source active sau mô phỏng: {active_sources_after}")
    print(f"CBQL/GV/NV còn tại source: {regular_users_after}")
    print(
        "Login trường nguồn active còn lại: "
        f"{active_source_logins_after}"
    )
    print(f"RAM integrity: {ram_integrity}")
    print(f"RAM FK errors: {len(ram_fk)}")
    print(
        "READY_FOR_REAL_BATCH_MERGE: "
        + ("YES" if ready_for_real_merge else "NO")
    )
    print("Database thật: KHÔNG THAY ĐỔI")
    print("Plan JSON: KHÔNG THAY ĐỔI")
    print(f"ZIP: {zip_path}")

    return 0 if ready_for_real_merge else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print()
        print("Đã dừng theo yêu cầu người dùng.")
        print("Database thật: KHÔNG THAY ĐỔI")
        print("Plan JSON: KHÔNG THAY ĐỔI")
        raise SystemExit(130)
    except Exception as exc:
        print()
        print("=" * 126)
        print("V13.5.3 DỪNG AN TOÀN")
        print("=" * 126)
        print(repr(exc))
        print("Database thật: KHÔNG THAY ĐỔI")
        print("Plan JSON: KHÔNG THAY ĐỔI")
        raise SystemExit(2)
