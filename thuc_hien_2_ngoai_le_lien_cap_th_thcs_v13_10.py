# -*- coding: utf-8 -*-
r"""
V13.10 - THỰC HIỆN THẬT 2 NGOẠI LỆ LIÊN CẤP TH + THCS
========================================================

ĐÃ ĐƯỢC MÔ PHỎNG PASS Ở V13.9
------------------------------
1) MƯỜNG QUÀNG
   TH Châu Thôn (1150)
   -> Trường THCS Châu Thôn (1593)
   Sau xử lý target phải mang đồng thời: TH + THCS
   Mô phỏng:
   - users moved = 0
   - source login disabled = 1
   - staff rollover created = 50
   - source inactive = 1
   - CURRENT/FUTURE residual = 0
   - PAST unchanged = True
   - integrity = ok
   - FK = 0

2) HỮU KHUÔNG
   PTDTBT Tiểu học Hữu Khuông (1101)
   -> PTDTBT THCS Hữu Khuông (1559)
   Sau xử lý target phải mang đồng thời: TH + THCS
   Mô phỏng:
   - users moved = 0
   - source login disabled = 1
   - staff rollover created = 48
   - source inactive = 1
   - CURRENT/FUTURE residual = 0
   - PAST unchanged = True
   - integrity = ok
   - FK = 0

CÁCH BIỂU DIỄN LIÊN CẤP
-----------------------
schools không có cột "cấp học".
Hệ thống xác định cấp theo school_network_year_data.

V13.10 sẽ tạo baseline CURRENT 2026-2027 tại trường đích:
- 1 dòng TH, lấy nguyên data_json từ baseline 2025-2026 của trường TH nguồn;
- 1 dòng THCS, lấy nguyên data_json từ baseline 2025-2026 của trường THCS đích.

PAST 2025-2026 và các năm trước KHÔNG bị sửa.

PLAN REGISTRY
-------------
Tạo 2 plan nội bộ có provenance rõ ràng:
- KHÔNG giả mạo số/ký hiệu văn bản chính thức.
- document_code = NGUON-SAP-NHAP-TOAN-TINH-LIEN-CAP
- cross_level_exception = true
- source_level = TH
- resulting_levels = [TH, THCS]

AN TOÀN
-------
- Mặc định PREFLIGHT: KHÔNG GHI.
- Khi APPLY:
  1. backup toàn DB + Plan JSON;
  2. kiểm tra backup integrity/FK;
  3. ghi 2 plan ở trạng thái APPROVED;
  4. BEGIN IMMEDIATE;
  5. seed CURRENT TH+THCS tại target;
  6. chạy 2 _apply_merge trong cùng transaction;
  7. PAST hash source+target phải giữ nguyên;
  8. CURRENT/FUTURE source residual = 0;
  9. target levels phải đúng {TH, THCS};
  10. source inactive, target active;
  11. integrity/FK thật phải PASS;
  12. COMMIT;
  13. hậu kiểm DB thật;
  14. đánh dấu 2 plan COMPLETED.
- Lỗi trước COMMIT: rollback + khôi phục Plan JSON.
- Lỗi post-check sau COMMIT: restore DB + Plan JSON từ backup.
- Nếu DB đã COMMIT + post-check PASS nhưng Plan JSON lỗi:
  KHÔNG chạy lại V13.10; chỉ đồng bộ Plan JSON riêng.

CHẠY PREFLIGHT
--------------
cd C:\PhoCap
.\.venv\Scripts\python.exe .\thuc_hien_2_ngoai_le_lien_cap_th_thcs_v13_10.py

CHẠY THẬT
---------
cd C:\PhoCap
.\.venv\Scripts\python.exe .\thuc_hien_2_ngoai_le_lien_cap_th_thcs_v13_10.py `
  --apply `
  --confirm "THUC HIEN 2 NGOAI LE LIEN CAP TH THCS V13.10"
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
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(r"C:\PhoCap")
DB_PATH = ROOT / "data" / "phocap.db"
PLAN_FILE = ROOT / "data" / "school_merger_approved_plans.json"
SERVICE = ROOT / "app" / "services" / "school_merger_service.py"
EXPORTS = ROOT / "exports"

YEAR_ID = 2
YEAR_CODE = "2026-2027"
PREVIOUS_YEAR_ID = 1

EXPECTED_SERVICE_SHA = (
    "414fb49a4c5f4fed7b571cc55df381678fe660cd8a675ecaa2f6fd70ebd7827a"
)

CONFIRM = "THUC HIEN 2 NGOAI LE LIEN CAP TH THCS V13.10"

CASES = [
    {
        "id": "V13.10-MUONG-QUANG-LIEN-CAP-TH-THCS",
        "label": "MUONG_QUANG",
        "commune_id": 10,
        "source_id": 1150,
        "target_id": 1593,
        "source_level": "TH",
        "target_level": "THCS",
        "expected_source_name": "TH Châu Thôn",
        "expected_target_name": "Trường THCS Châu Thôn",
        "source_evidence": (
            'Nguồn sáp nhập.xlsx: Tiểu học Châu Thôn -> '
            '"Trường THCS Châu Thôn"; dòng kế là THCS Châu Thôn.'
        ),
        "expected": {
            "users_moved": 0,
            "source_school_logins_disabled": 1,
            "staff_rollover_created": 50,
            "sources_deactivated": 1,
        },
    },
    {
        "id": "V13.10-HUU-KHUONG-LIEN-CAP-TH-THCS",
        "label": "HUU_KHUONG",
        "commune_id": 29,
        "source_id": 1101,
        "target_id": 1559,
        "source_level": "TH",
        "target_level": "THCS",
        "expected_source_name": "PTDTBT Tiểu học Hữu Khuông",
        "expected_target_name": "PTDTBT THCS Hữu Khuông",
        "source_evidence": (
            'Nguồn sáp nhập.xlsx: PTDTBT Tiểu học Hữu Khuông -> '
            '"PTDTBT THCS Hữu Khuông"; ghi chú "Liên cấp TH&THCS".'
        ),
        "expected": {
            "users_moved": 0,
            "source_school_logins_disabled": 1,
            "staff_rollover_created": 48,
            "sources_deactivated": 1,
        },
    },
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def qident(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def markers(n: int) -> str:
    return ",".join("?" for _ in range(n))


def connect_ro(path: Path = DB_PATH) -> sqlite3.Connection:
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


def load_payload(path: Path = PLAN_FILE) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload.get("plans"), list):
        raise RuntimeError("Plan JSON không có mảng plans.")
    return payload


def registry_counts(payload: dict) -> dict[str, int]:
    plans = [p for p in payload["plans"] if isinstance(p, dict)]

    qd = [
        p for p in plans
        if (
            (
                str(p.get("id") or "").startswith("QD3805-")
                or "3805" in str(p.get("document_code") or "")
            )
            and str(p.get("status") or "").upper() == "COMPLETED"
        )
    ]

    province = [
        p for p in plans
        if (
            str(p.get("document_code") or "")
            == "NGUON-SAP-NHAP-TOAN-TINH"
            and str(p.get("status") or "").upper() == "COMPLETED"
        )
    ]

    qd_corrections = [
        p for p in plans
        if (
            str(p.get("id") or "").startswith("V13.8-QUANG-DONG-")
            and str(p.get("status") or "").upper() == "COMPLETED"
        )
    ]

    v1310 = [
        p for p in plans
        if str(p.get("id") or "").startswith("V13.10-")
    ]

    return {
        "total": len(plans),
        "qd3805_completed": len(qd),
        "province_completed": len(province),
        "quang_dong_completed": len(qd_corrections),
        "v13_10_count": len(v1310),
        "v13_10_completed": sum(
            str(p.get("status") or "").upper() == "COMPLETED"
            for p in v1310
        ),
    }


def validate_registry_base(payload: dict) -> None:
    counts = registry_counts(payload)
    if counts["qd3805_completed"] != 6:
        raise RuntimeError(
            f"QĐ3805 COMPLETED={counts['qd3805_completed']}, cần 6."
        )
    if counts["province_completed"] != 412:
        raise RuntimeError(
            f"Province COMPLETED={counts['province_completed']}, cần 412."
        )
    if counts["quang_dong_completed"] != 2:
        raise RuntimeError(
            f"Quang Đồng V13.8 COMPLETED={counts['quang_dong_completed']}, cần 2."
        )
    if counts["v13_10_count"] != 0:
        raise RuntimeError(
            f"Đã tồn tại {counts['v13_10_count']} plan V13.10; "
            "không tự chạy lại."
        )


def atomic_write_json(path: Path, payload: dict) -> None:
    raw = json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
    )
    json.loads(raw)

    tmp = path.with_name(path.name + ".v13_10.tmp")
    tmp.write_text(raw, encoding="utf-8")
    os.replace(tmp, path)


def add_approved_plans(
    payload: dict,
    backup_name: str,
) -> dict:
    cloned = json.loads(
        json.dumps(payload, ensure_ascii=False)
    )
    plans = cloned["plans"]
    existing_ids = {
        str(p.get("id") or "")
        for p in plans
        if isinstance(p, dict)
    }

    now = datetime.now().isoformat(timespec="seconds")

    for case in CASES:
        if case["id"] in existing_ids:
            raise RuntimeError(
                f"Plan đã tồn tại: {case['id']}"
            )

        plans.append({
            "id": case["id"],
            "document_code": "NGUON-SAP-NHAP-TOAN-TINH-LIEN-CAP",
            "document_title": (
                "Ngoại lệ liên cấp TH + THCS từ Nguồn sáp nhập.xlsx"
            ),
            "document_date": "",
            "school_year_id": YEAR_ID,
            "commune_id": case["commune_id"],
            "level_code": "THCS",
            "source_school_ids": [case["source_id"]],
            "target_school_id": case["target_id"],
            "status": "APPROVED",
            "note": case["source_evidence"],
            "cross_level_exception": True,
            "source_level": "TH",
            "target_original_level": "THCS",
            "resulting_levels": ["TH", "THCS"],
            "current_network_seed_from_previous_year": True,
            "created_at": now,
            "created_by": {"source": "V13_10_CROSS_LEVEL_EXCEPTION"},
            "approved_at": now,
            "approved_by": {"source": "V13_10_CROSS_LEVEL_EXCEPTION"},
            "updated_at": now,
            "updated_by": {"source": "V13_10_CROSS_LEVEL_EXCEPTION"},
            "approval_warnings": [],
            "completion_backup": None,
            "v13_10_backup": backup_name,
        })

    cloned["version"] = max(int(cloned.get("version") or 1), 3)
    cloned["revision"] = int(cloned.get("revision") or 0) + 1
    cloned["updated_at"] = now
    return cloned


def mark_plans_completed(
    payload: dict,
    backup_name: str,
) -> dict:
    cloned = json.loads(
        json.dumps(payload, ensure_ascii=False)
    )
    wanted = {case["id"] for case in CASES}
    found = 0
    now = datetime.now().isoformat(timespec="seconds")

    for plan in cloned["plans"]:
        if not isinstance(plan, dict):
            continue
        pid = str(plan.get("id") or "")
        if pid not in wanted:
            continue

        if str(plan.get("status") or "").upper() != "APPROVED":
            raise RuntimeError(
                f"{pid} không còn APPROVED."
            )

        plan["status"] = "COMPLETED"
        plan["completed_at"] = now
        plan["completed_by"] = "V13_10_CROSS_LEVEL_EXCEPTION"
        plan["completion_backup"] = backup_name
        plan["updated_at"] = now
        plan["updated_by"] = {"source": "V13_10_CROSS_LEVEL_EXCEPTION"}
        found += 1

    if found != 2:
        raise RuntimeError(
            f"Chỉ tìm thấy {found}/2 plan V13.10."
        )

    cloned["revision"] = int(cloned.get("revision") or 0) + 1
    cloned["updated_at"] = now
    return cloned


def sqlite_backup(source: Path, target: Path) -> None:
    src = sqlite3.connect(str(source), timeout=60)
    dst = sqlite3.connect(str(target), timeout=60)
    try:
        src.backup(dst)
        dst.commit()
    finally:
        dst.close()
        src.close()


def sqlite_restore(source: Path, target: Path) -> None:
    src = sqlite3.connect(str(source), timeout=60)
    dst = sqlite3.connect(str(target), timeout=60)
    try:
        src.backup(dst)
        dst.commit()
    finally:
        dst.close()
        src.close()


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


def year_aware_tables(
    con: sqlite3.Connection,
) -> list[str]:
    result = []
    rows = con.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type='table'
          AND name NOT LIKE 'sqlite_%'
        ORDER BY name
        """
    ).fetchall()

    for row in rows:
        table = str(row[0])
        cols = set(table_columns(con, table))
        if {"school_id", "school_year_id"} <= cols:
            result.append(table)

    return result


def canonical(value: Any) -> Any:
    if isinstance(value, bytes):
        return {"__bytes__": value.hex()}
    return value


def past_hashes(
    con: sqlite3.Connection,
    school_ids: list[int],
    past_year_ids: list[int],
) -> dict[str, tuple[int, str]]:
    result = {}

    for table in year_aware_tables(con):
        cols = table_columns(con, table)
        rows = con.execute(
            f"SELECT * FROM {qident(table)} "
            f"WHERE school_id IN ({markers(len(school_ids))}) "
            f"AND school_year_id IN ({markers(len(past_year_ids))})",
            [*school_ids, *past_year_ids],
        ).fetchall()

        lines = []
        for row in rows:
            obj = {
                col: canonical(row[col])
                for col in cols
            }
            lines.append(
                json.dumps(
                    obj,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                    default=str,
                )
            )
        lines.sort()

        h = hashlib.sha256()
        for line in lines:
            h.update(line.encode("utf-8"))
            h.update(b"\n")

        result[table] = (len(lines), h.hexdigest())

    return result


def current_future_residual(
    con: sqlite3.Connection,
    source_ids: list[int],
    move_year_ids: list[int],
) -> int:
    total = 0
    for table in year_aware_tables(con):
        total += int(
            con.execute(
                f"SELECT COUNT(*) FROM {qident(table)} "
                f"WHERE school_id IN ({markers(len(source_ids))}) "
                f"AND school_year_id IN ({markers(len(move_year_ids))})",
                [*source_ids, *move_year_ids],
            ).fetchone()[0]
            or 0
        )
    return total


def single_baseline(
    con: sqlite3.Connection,
    school_id: int,
    level_code: str,
) -> sqlite3.Row:
    rows = con.execute(
        """
        SELECT *
        FROM school_network_year_data
        WHERE school_id=?
          AND school_year_id=?
          AND UPPER(TRIM(level_code))=?
        ORDER BY id
        """,
        (
            school_id,
            PREVIOUS_YEAR_ID,
            level_code.upper(),
        ),
    ).fetchall()

    if len(rows) != 1:
        raise RuntimeError(
            f"Baseline school={school_id}, level={level_code}: "
            f"cần đúng 1 dòng, hiện={len(rows)}."
        )
    return rows[0]


def ensure_current_network_row(
    con: sqlite3.Connection,
    *,
    target_school_id: int,
    level_code: str,
    baseline: sqlite3.Row,
    source_name: str,
) -> str:
    rows = con.execute(
        """
        SELECT id
        FROM school_network_year_data
        WHERE school_id=?
          AND school_year_id=?
          AND UPPER(TRIM(level_code))=?
        ORDER BY id
        """,
        (
            target_school_id,
            YEAR_ID,
            level_code.upper(),
        ),
    ).fetchall()

    if len(rows) > 1:
        raise RuntimeError(
            f"Target={target_school_id}, level={level_code}: "
            f"có {len(rows)} dòng CURRENT."
        )
    if len(rows) == 1:
        return "EXISTING"

    con.execute(
        """
        INSERT INTO school_network_year_data(
            school_id,
            school_year_id,
            level_code,
            data_json,
            source_name,
            imported_at
        )
        VALUES(?,?,?,?,?,CURRENT_TIMESTAMP)
        """,
        (
            target_school_id,
            YEAR_ID,
            level_code.upper(),
            baseline["data_json"],
            source_name,
        ),
    )
    return "CREATED_FROM_2025_2026"


def preflight_school(
    con: sqlite3.Connection,
    merger,
    case: dict,
) -> None:
    source = con.execute(
        """
        SELECT id,code,name,commune_id,is_active
        FROM schools
        WHERE id=?
        """,
        (case["source_id"],),
    ).fetchone()
    target = con.execute(
        """
        SELECT id,code,name,commune_id,is_active
        FROM schools
        WHERE id=?
        """,
        (case["target_id"],),
    ).fetchone()

    if source is None or target is None:
        raise RuntimeError(
            f"{case['label']}: thiếu source/target."
        )

    if str(source["name"] or "") != case["expected_source_name"]:
        raise RuntimeError(
            f"{case['label']}: source name={source['name']!r}."
        )
    if str(target["name"] or "") != case["expected_target_name"]:
        raise RuntimeError(
            f"{case['label']}: target name={target['name']!r}."
        )

    if int(source["commune_id"] or 0) != case["commune_id"]:
        raise RuntimeError(
            f"{case['label']}: source sai commune."
        )
    if int(target["commune_id"] or 0) != case["commune_id"]:
        raise RuntimeError(
            f"{case['label']}: target sai commune."
        )

    if int(source["is_active"] or 0) != 1:
        raise RuntimeError(
            f"{case['label']}: source không active."
        )
    if int(target["is_active"] or 0) != 1:
        raise RuntimeError(
            f"{case['label']}: target không active."
        )

    source_levels = merger._school_levels(
        con,
        case["source_id"],
        YEAR_ID,
    )
    target_levels = merger._school_levels(
        con,
        case["target_id"],
        YEAR_ID,
    )

    if source_levels != {"TH"}:
        raise RuntimeError(
            f"{case['label']}: source levels={source_levels}, cần TH."
        )
    if target_levels != {"THCS"}:
        raise RuntimeError(
            f"{case['label']}: target levels={target_levels}, cần THCS."
        )

    # V13.9 xác nhận CURRENT target chưa có hai dòng.
    for level in ("TH", "THCS"):
        n = int(
            con.execute(
                """
                SELECT COUNT(*)
                FROM school_network_year_data
                WHERE school_id=? AND school_year_id=?
                  AND UPPER(TRIM(level_code))=?
                """,
                (
                    case["target_id"],
                    YEAR_ID,
                    level,
                ),
            ).fetchone()[0]
            or 0
        )
        if n != 0:
            raise RuntimeError(
                f"{case['label']}: target đã có CURRENT level={level}; "
                "trạng thái đã khác V13.9."
            )

    # Baseline 2025-2026 bắt buộc đủ.
    single_baseline(
        con,
        case["source_id"],
        "TH",
    )
    single_baseline(
        con,
        case["target_id"],
        "THCS",
    )


def write_csv(
    path: Path,
    headers: list[str],
    rows: list[dict],
) -> None:
    with path.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as f:
        w = csv.DictWriter(
            f,
            fieldnames=headers,
            extrasaction="ignore",
        )
        w.writeheader()
        w.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm", default="")
    args = parser.parse_args()

    print("=" * 126)
    print("V13.10 - 2 NGOẠI LỆ LIÊN CẤP TH + THCS")
    print("=" * 126)
    print(
        "Chế độ:",
        "APPLY THẬT" if args.apply else "PREFLIGHT - KHÔNG GHI",
    )

    for path in (DB_PATH, PLAN_FILE, SERVICE):
        if not path.exists():
            raise RuntimeError(
                f"Không tìm thấy: {path}"
            )

    if sha256(SERVICE) != EXPECTED_SERVICE_SHA:
        raise RuntimeError(
            "Engine không đúng V13.5.2 đã hậu kiểm."
        )

    payload_before = load_payload()
    validate_registry_base(payload_before)

    sys.path.insert(0, str(ROOT))
    from app.services import school_merger_service as merger

    with connect_ro() as con:
        integrity, fk = db_health(con)
        if integrity.lower() != "ok" or fk:
            raise RuntimeError(
                f"DB preflight lỗi: integrity={integrity}, FK={fk}"
            )

        year = con.execute(
            "SELECT code FROM school_years WHERE id=?",
            (YEAR_ID,),
        ).fetchone()
        if year is None or str(year[0] or "") != YEAR_CODE:
            raise RuntimeError(
                "school_year_id=2 không còn là 2026-2027."
            )

        # Schema phải cho phép unique theo school+year+level.
        indexes = con.execute(
            'PRAGMA index_list("school_network_year_data")'
        ).fetchall()
        found_correct_unique = False
        for idx in indexes:
            if int(idx["unique"] or 0) != 1:
                continue
            idx_name = str(idx["name"])
            cols = [
                str(r["name"])
                for r in con.execute(
                    f"PRAGMA index_info({qident(idx_name)})"
                ).fetchall()
            ]
            if set(cols) == {
                "school_id",
                "school_year_id",
                "level_code",
            }:
                found_correct_unique = True

        if not found_correct_unique:
            raise RuntimeError(
                "school_network_year_data chưa có unique "
                "(school_id,school_year_id,level_code)."
            )

        for case in CASES:
            preflight_school(
                con,
                merger,
                case,
            )

    print()
    print("PREFLIGHT PASS")
    print(" - QĐ3805 COMPLETED: 6")
    print(" - Province COMPLETED: 412")
    print(" - Quang Đồng V13.8 COMPLETED: 2")
    print(" - Mường Quàng: 1150 -> 1593")
    print(" - Hữu Khuông: 1101 -> 1559")
    print(" - Cả hai target sẽ seed CURRENT: TH + THCS")
    print(" - PAST baseline lấy từ 2025-2026, không sửa PAST")
    print(" - DB integrity: ok")
    print(" - DB FK errors: 0")

    if not args.apply:
        print()
        print("Database: CHƯA THAY ĐỔI")
        print("Plan JSON: CHƯA THAY ĐỔI")
        return 0

    if args.confirm.strip() != CONFIRM:
        raise RuntimeError(
            "Sai câu xác nhận; chưa ghi gì."
        )

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = (
        EXPORTS
        / f"backup_truoc_v13_10_lien_cap_{stamp}"
    )
    backup_dir.mkdir(parents=True, exist_ok=False)

    backup_db = backup_dir / "phocap.db"
    backup_plan = backup_dir / "school_merger_approved_plans.json"
    backup_name = backup_dir.name

    print("Đang backup DB + Plan JSON...", flush=True)
    sqlite_backup(DB_PATH, backup_db)
    shutil.copy2(PLAN_FILE, backup_plan)

    with connect_ro(backup_db) as chk:
        bi, bf = db_health(chk)
        if bi.lower() != "ok" or bf:
            raise RuntimeError(
                f"Backup DB lỗi: integrity={bi}, FK={bf}"
            )

    approved_payload = add_approved_plans(
        payload_before,
        backup_name,
    )
    atomic_write_json(
        PLAN_FILE,
        approved_payload,
    )

    con = sqlite3.connect(
        str(DB_PATH),
        timeout=120,
    )
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")

    committed = False
    post_verified = False
    result_rows = []
    network_rows = []

    all_sources = [
        int(case["source_id"])
        for case in CASES
    ]
    all_involved = sorted(
        {
            int(case["source_id"])
            for case in CASES
        }
        | {
            int(case["target_id"])
            for case in CASES
        }
    )

    try:
        con.execute("BEGIN IMMEDIATE")

        move_year_ids, past_year_ids = merger._year_scope_ids(
            con,
            YEAR_ID,
        )
        previous_year_id = merger._previous_year_id(
            con,
            YEAR_ID,
        )

        if move_year_ids != [2, 8]:
            raise RuntimeError(
                f"CURRENT+FUTURE={move_year_ids}, cần [2,8]."
            )
        if previous_year_id != PREVIOUS_YEAR_ID:
            raise RuntimeError(
                f"previous_year_id={previous_year_id}, cần 1."
            )

        past_before = past_hashes(
            con,
            all_involved,
            past_year_ids,
        )

        for index, case in enumerate(CASES, start=1):
            print(
                f"Thực hiện {index}/2 {case['label']}: "
                f"{case['source_id']} -> {case['target_id']}...",
                flush=True,
            )

            source_baseline = single_baseline(
                con,
                case["source_id"],
                "TH",
            )
            target_baseline = single_baseline(
                con,
                case["target_id"],
                "THCS",
            )

            action_th = ensure_current_network_row(
                con,
                target_school_id=case["target_id"],
                level_code="TH",
                baseline=source_baseline,
                source_name=(
                    f"V13.10-LIENCAP-{case['label']}-"
                    f"TH-FROM-{case['source_id']}-Y1"
                ),
            )
            action_thcs = ensure_current_network_row(
                con,
                target_school_id=case["target_id"],
                level_code="THCS",
                baseline=target_baseline,
                source_name=(
                    f"V13.10-LIENCAP-{case['label']}-"
                    f"THCS-FROM-{case['target_id']}-Y1"
                ),
            )

            seeded_levels = merger._school_levels(
                con,
                case["target_id"],
                YEAR_ID,
            )
            if seeded_levels != {"TH", "THCS"}:
                raise RuntimeError(
                    f"{case['label']}: sau seed levels={seeded_levels}."
                )

            result = merger._apply_merge(
                con,
                selected_year_id=YEAR_ID,
                previous_year_id=previous_year_id,
                target_school_id=case["target_id"],
                source_ids=[case["source_id"]],
                actor_user_id=None,
                backup_name=backup_name,
                record_audit=True,
            )

            actual = {
                "users_moved": int(
                    result.get("users_moved") or 0
                ),
                "source_school_logins_disabled": int(
                    result.get("source_school_logins_disabled") or 0
                ),
                "staff_rollover_created": int(
                    result.get("staff_rollover_created") or 0
                ),
                "sources_deactivated": int(
                    result.get("sources_deactivated") or 0
                ),
            }

            if actual != case["expected"]:
                raise RuntimeError(
                    f"{case['label']} khác V13.9: "
                    f"actual={actual}, expected={case['expected']}"
                )

            final_levels = merger._school_levels(
                con,
                case["target_id"],
                YEAR_ID,
            )
            if final_levels != {"TH", "THCS"}:
                raise RuntimeError(
                    f"{case['label']}: target cuối levels={final_levels}."
                )

            source_active = int(
                con.execute(
                    "SELECT is_active FROM schools WHERE id=?",
                    (case["source_id"],),
                ).fetchone()[0]
                or 0
            )
            target_active = int(
                con.execute(
                    "SELECT is_active FROM schools WHERE id=?",
                    (case["target_id"],),
                ).fetchone()[0]
                or 0
            )

            if source_active != 0:
                raise RuntimeError(
                    f"{case['label']}: source chưa inactive."
                )
            if target_active != 1:
                raise RuntimeError(
                    f"{case['label']}: target không active."
                )

            result_rows.append({
                "plan_id": case["id"],
                "label": case["label"],
                "source_id": case["source_id"],
                "target_id": case["target_id"],
                "seed_th": action_th,
                "seed_thcs": action_thcs,
                "levels_after": ",".join(sorted(final_levels)),
                **actual,
                "result": "PASS",
            })

            current_rows = con.execute(
                """
                SELECT id,school_id,school_year_id,level_code,
                       data_json,source_name,imported_at
                FROM school_network_year_data
                WHERE school_id=? AND school_year_id=?
                ORDER BY level_code,id
                """,
                (
                    case["target_id"],
                    YEAR_ID,
                ),
            ).fetchall()

            for row in current_rows:
                network_rows.append({
                    "label": case["label"],
                    **dict(row),
                })

        past_after = past_hashes(
            con,
            all_involved,
            past_year_ids,
        )
        if past_before != past_after:
            changed = [
                table
                for table in set(past_before) | set(past_after)
                if past_before.get(table) != past_after.get(table)
            ]
            raise RuntimeError(
                f"PAST thay đổi tại {changed}."
            )

        residual = current_future_residual(
            con,
            all_sources,
            move_year_ids,
        )
        if residual != 0:
            raise RuntimeError(
                f"Còn {residual} CURRENT/FUTURE tại source."
            )

        operation_count = int(
            con.execute(
                """
                SELECT COUNT(*)
                FROM school_merger_operations
                WHERE backup_name=?
                """,
                (backup_name,),
            ).fetchone()[0]
            or 0
        )
        if operation_count != 2:
            raise RuntimeError(
                f"Audit operations={operation_count}, cần 2."
            )

        integrity_pre = str(
            con.execute("PRAGMA integrity_check").fetchone()[0]
        )
        fk_pre = len(
            con.execute("PRAGMA foreign_key_check").fetchall()
        )

        if integrity_pre.lower() != "ok" or fk_pre:
            raise RuntimeError(
                f"Precommit lỗi: integrity={integrity_pre}, FK={fk_pre}"
            )

        con.commit()
        committed = True

        integrity_post = str(
            con.execute("PRAGMA integrity_check").fetchone()[0]
        )
        fk_post = len(
            con.execute("PRAGMA foreign_key_check").fetchall()
        )

        if integrity_post.lower() != "ok" or fk_post:
            raise RuntimeError(
                f"Postcommit lỗi: integrity={integrity_post}, FK={fk_post}"
            )

        for case in CASES:
            levels = merger._school_levels(
                con,
                case["target_id"],
                YEAR_ID,
            )
            if levels != {"TH", "THCS"}:
                raise RuntimeError(
                    f"{case['label']}: postcommit levels={levels}."
                )

        post_verified = True

    except Exception:
        if not committed:
            try:
                con.rollback()
            except Exception:
                pass
            shutil.copy2(
                backup_plan,
                PLAN_FILE,
            )
        elif not post_verified:
            con.close()
            con = None
            print(
                "Post-check sau COMMIT lỗi; đang restore DB + Plan JSON...",
                flush=True,
            )
            sqlite_restore(
                backup_db,
                DB_PATH,
            )
            shutil.copy2(
                backup_plan,
                PLAN_FILE,
            )
        raise
    finally:
        if con is not None:
            con.close()

    # DB đã commit và post-check PASS.
    try:
        current_payload = load_payload()
        completed_payload = mark_plans_completed(
            current_payload,
            backup_name,
        )
        atomic_write_json(
            PLAN_FILE,
            completed_payload,
        )
    except Exception as exc:
        emergency = (
            backup_dir
            / "CAN_DONG_BO_PLAN_JSON_V13_10.txt"
        )
        emergency.write_text(
            "\n".join([
                "DATABASE V13.10 ĐÃ COMMIT VÀ POST-CHECK PASS.",
                f"Lỗi Plan JSON: {repr(exc)}",
                "KHÔNG chạy lại V13.10.",
                "Chỉ đồng bộ Plan JSON riêng.",
            ]),
            encoding="utf-8",
        )
        raise RuntimeError(
            "DB đã liên cấp thành công nhưng Plan JSON chưa đồng bộ. "
            f"KHÔNG chạy lại. Xem {emergency}"
        ) from exc

    final_payload = load_payload()
    final_counts = registry_counts(final_payload)

    if final_counts["v13_10_count"] != 2:
        raise RuntimeError(
            "Plan V13.10 sau cùng không đúng 2."
        )
    if final_counts["v13_10_completed"] != 2:
        raise RuntimeError(
            "Plan V13.10 COMPLETED sau cùng không đúng 2."
        )

    with connect_ro() as final_con:
        final_integrity, final_fk = db_health(final_con)

        final_operations = int(
            final_con.execute(
                """
                SELECT COUNT(*)
                FROM school_merger_operations
                WHERE backup_name=?
                """,
                (backup_name,),
            ).fetchone()[0]
            or 0
        )

        final_residual = current_future_residual(
            final_con,
            all_sources,
            [2, 8],
        )

        final_source_active = int(
            final_con.execute(
                f"SELECT COUNT(*) FROM schools "
                f"WHERE id IN ({markers(len(all_sources))}) "
                "AND is_active=1",
                all_sources,
            ).fetchone()[0]
            or 0
        )

        final_network = []
        for case in CASES:
            # Xác định trực tiếp từ current rows, không fallback.
            levels = {
                str(r[0]).strip().upper()
                for r in final_con.execute(
                    """
                    SELECT level_code
                    FROM school_network_year_data
                    WHERE school_id=? AND school_year_id=?
                    ORDER BY level_code
                    """,
                    (
                        case["target_id"],
                        YEAR_ID,
                    ),
                ).fetchall()
            }
            if levels != {"TH", "THCS"}:
                raise RuntimeError(
                    f"{case['label']}: audit cuối levels={levels}."
                )

            rows = final_con.execute(
                """
                SELECT id,school_id,school_year_id,level_code,
                       data_json,source_name,imported_at
                FROM school_network_year_data
                WHERE school_id=? AND school_year_id=?
                ORDER BY level_code,id
                """,
                (
                    case["target_id"],
                    YEAR_ID,
                ),
            ).fetchall()

            if len(rows) != 2:
                raise RuntimeError(
                    f"{case['label']}: CURRENT network rows={len(rows)}, cần 2."
                )

            for row in rows:
                final_network.append({
                    "label": case["label"],
                    **dict(row),
                })

    success = (
        final_counts["qd3805_completed"] == 6
        and final_counts["province_completed"] == 412
        and final_counts["quang_dong_completed"] == 2
        and final_counts["v13_10_completed"] == 2
        and final_integrity.lower() == "ok"
        and final_fk == 0
        and final_operations == 2
        and final_residual == 0
        and final_source_active == 0
    )

    if not success:
        raise RuntimeError(
            "Audit cuối V13.10 chưa đạt; KHÔNG chạy lại."
        )

    report_dir = (
        ROOT
        / f"bao_cao_v13_10_lien_cap_{stamp}"
    )
    report_dir.mkdir(
        parents=True,
        exist_ok=False,
    )

    write_csv(
        report_dir / "790_KET_QUA_2_LIEN_CAP.csv",
        [
            "plan_id",
            "label",
            "source_id",
            "target_id",
            "seed_th",
            "seed_thcs",
            "levels_after",
            "users_moved",
            "source_school_logins_disabled",
            "staff_rollover_created",
            "sources_deactivated",
            "result",
        ],
        result_rows,
    )

    write_csv(
        report_dir / "791_TARGET_NETWORK_CURRENT.csv",
        [
            "label",
            "id",
            "school_id",
            "school_year_id",
            "level_code",
            "data_json",
            "source_name",
            "imported_at",
        ],
        final_network,
    )

    gate_rows = [
        {
            "check": "qd3805_completed",
            "result": "PASS",
            "detail": "6",
        },
        {
            "check": "province_412_completed",
            "result": "PASS",
            "detail": "412",
        },
        {
            "check": "quang_dong_v13_8_completed",
            "result": "PASS",
            "detail": "2",
        },
        {
            "check": "cross_level_v13_10_completed",
            "result": "PASS",
            "detail": "2",
        },
        {
            "check": "muong_quang_levels",
            "result": "PASS",
            "detail": "TH,THCS",
        },
        {
            "check": "huu_khuong_levels",
            "result": "PASS",
            "detail": "TH,THCS",
        },
        {
            "check": "current_future_source_residual",
            "result": "PASS",
            "detail": str(final_residual),
        },
        {
            "check": "source_active_after",
            "result": "PASS",
            "detail": str(final_source_active),
        },
        {
            "check": "audit_operations",
            "result": "PASS",
            "detail": str(final_operations),
        },
        {
            "check": "db_integrity",
            "result": "PASS",
            "detail": final_integrity,
        },
        {
            "check": "db_fk",
            "result": "PASS",
            "detail": str(final_fk),
        },
        {
            "check": "V13_10_CROSS_LEVEL_CLOSED",
            "result": "YES",
            "detail": (
                "Mường Quàng + Hữu Khuông đã hoàn thành liên cấp TH+THCS."
            ),
        },
    ]

    write_csv(
        report_dir / "792_GATE_V13_10.csv",
        ["check", "result", "detail"],
        gate_rows,
    )

    summary = f"""V13.10 - THỰC HIỆN 2 NGOẠI LỆ LIÊN CẤP TH + THCS
================================================================================

STATUS=SUCCESS

MƯỜNG QUÀNG
- 1150 TH Châu Thôn -> 1593 Trường THCS Châu Thôn
- target CURRENT levels = TH + THCS
- users moved = 0
- source login disabled = 1
- staff rollover created = 50
- source inactive = YES

HỮU KHUÔNG
- 1101 PTDTBT Tiểu học Hữu Khuông -> 1559 PTDTBT THCS Hữu Khuông
- target CURRENT levels = TH + THCS
- users moved = 0
- source login disabled = 1
- staff rollover created = 48
- source inactive = YES

Registry:
- QĐ3805 COMPLETED = {final_counts['qd3805_completed']}
- Province COMPLETED = {final_counts['province_completed']}
- Quang Đồng V13.8 COMPLETED = {final_counts['quang_dong_completed']}
- Liên cấp V13.10 COMPLETED = {final_counts['v13_10_completed']}

Database:
- CURRENT/FUTURE residual tại 2 source = {final_residual}
- source active còn lại = {final_source_active}
- audit operations = {final_operations}
- integrity = {final_integrity}
- FK = {final_fk}

Baseline:
- CURRENT 2026-2027 TH lấy từ baseline TH 2025-2026 của source.
- CURRENT 2026-2027 THCS lấy từ baseline THCS 2025-2026 của target.
- PAST không bị sửa.

Backup:
{backup_dir}

V13_10_CROSS_LEVEL_CLOSED=YES
"""

    (
        report_dir / "00_TONG_QUAN_V13_10.txt"
    ).write_text(
        summary,
        encoding="utf-8",
    )

    zip_path = (
        ROOT
        / f"bao_cao_v13_10_lien_cap_{stamp}.zip"
    )
    with zipfile.ZipFile(
        zip_path,
        "w",
        compression=zipfile.ZIP_DEFLATED,
    ) as zf:
        for path in sorted(report_dir.iterdir()):
            if path.is_file():
                zf.write(
                    path,
                    arcname=path.name,
                )

    print()
    print("=" * 126)
    print("V13.10 THÀNH CÔNG")
    print("=" * 126)
    print("Mường Quàng: TH + THCS COMPLETED")
    print("Hữu Khuông: TH + THCS COMPLETED")
    print("Cross-level plans COMPLETED: 2")
    print(f"CURRENT/FUTURE residual: {final_residual}")
    print(f"Source active còn lại: {final_source_active}")
    print(f"Audit operations: {final_operations}")
    print(f"DB integrity: {final_integrity}")
    print(f"DB FK errors: {final_fk}")
    print("V13_10_CROSS_LEVEL_CLOSED: YES")
    print(f"Backup: {backup_dir}")
    print(f"ZIP: {zip_path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print()
        print("=" * 126)
        print("V13.10 DỪNG AN TOÀN")
        print("=" * 126)
        print(repr(exc))
        print(
            "Nếu lỗi nói DB đã commit nhưng Plan JSON chưa đồng bộ: "
            "KHÔNG chạy lại V13.10."
        )
        raise SystemExit(2)
