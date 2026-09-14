# -*- coding: utf-8 -*-
r"""
V13.8 - THỰC HIỆN HIỆU CHỈNH QUANG ĐỒNG SAU V13.7
===================================================

CHỈ XỬ LÝ QUANG ĐỒNG
--------------------
Từ V13.7 đã xác nhận Nhóm 626 bị parser dính nhầm một trường TH vào nhóm MN.

Nghiệp vụ đúng:
1) MN:
   Mầm non Đồng Thành (613)
   + Mầm non Quang Thành (615)
   -> Mầm non Kim Thành (614)

2) TH:
   Tiểu học Đồng Thành (1230)
   -> Tiểu học Quang Thành (1232)

Lưu ý:
- Nhóm 627 đã COMPLETED với source cũ [1231] -> 1232.
- V13.8 KHÔNG chạy lại source 1231.
- V13.8 KHÔNG đụng Mường Quàng / Hữu Khuông.
- V13.8 ghi 2 plan hiệu chỉnh riêng, không giả mạo mã văn bản chính thức.

AN TOÀN
-------
- Mặc định PREFLIGHT, không ghi.
- Khi APPLY:
  + backup DB + Plan JSON;
  + ghi 2 correction plan APPROVED;
  + chạy 2 phép trong MỘT transaction DB;
  + PAST phải giữ nguyên;
  + CURRENT/FUTURE không còn tại 613,615,1230;
  + integrity/FK phải PASS;
  + chỉ sau COMMIT mới đổi 2 correction plan thành COMPLETED.
- Nếu lỗi trước COMMIT: rollback + khôi phục Plan JSON.
- Nếu post-check DB sau COMMIT lỗi: restore DB + Plan JSON từ backup.

CHẠY PREFLIGHT
--------------
cd C:\PhoCap
.\.venv\Scripts\python.exe .\thuc_hien_hieu_chinh_quang_dong_v13_8.py

CHẠY THẬT
---------
cd C:\PhoCap
.\.venv\Scripts\python.exe .\thuc_hien_hieu_chinh_quang_dong_v13_8.py `
  --apply `
  --confirm "HIEU CHINH QUANG DONG V13.8"
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
COMMUNE_ID = 92
COMMUNE_NAME = "Xã Quang Đồng"

EXPECTED_SERVICE_SHA = (
    "414fb49a4c5f4fed7b571cc55df381678fe660cd8a675ecaa2f6fd70ebd7827a"
)

CONFIRM = "HIEU CHINH QUANG DONG V13.8"

CORRECTIONS = [
    {
        "id": "V13.8-QUANG-DONG-MN-CORRECTED",
        "level_code": "MN",
        "source_ids": [613, 615],
        "target_id": 614,
        "expected": {
            "users_moved": 60,
            "source_school_logins_disabled": 2,
            "staff_rollover_created": 6,
            "sources_deactivated": 2,
        },
        "note": (
            "Hiệu chỉnh parser Nhóm 626 từ Nguồn sáp nhập.xlsx: "
            "MN Đồng Thành + MN Quang Thành -> MN Kim Thành; "
            "loại school_id=1230 cấp TH khỏi nhóm MN."
        ),
    },
    {
        "id": "V13.8-QUANG-DONG-TH-RESIDUAL",
        "level_code": "TH",
        "source_ids": [1230],
        "target_id": 1232,
        "expected": {
            "users_moved": 0,
            "source_school_logins_disabled": 1,
            "staff_rollover_created": 36,
            "sources_deactivated": 1,
        },
        "note": (
            "Hiệu chỉnh phần TH còn thiếu sau parser: "
            "TH Đồng Thành -> TH Quang Thành. "
            "Nhóm 627 cũ [1231] -> 1232 đã COMPLETED và không chạy lại."
        ),
    },
]

EXPECTED_SCHOOLS = {
    613: ("40426324", "Mầm non Đồng Thành", "MN"),
    614: ("40426325", "Mầm non Kim Thành", "MN"),
    615: ("40426331", "Mầm non Quang Thành", "MN"),
    1230: ("40426431", "Tiểu học Đồng Thành", "TH"),
    1232: ("40426444", "Tiểu học Quang Thành", "TH"),
}


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


def load_payload() -> dict:
    payload = json.loads(PLAN_FILE.read_text(encoding="utf-8"))
    if not isinstance(payload.get("plans"), list):
        raise RuntimeError("Plan JSON không có mảng plans.")
    return payload


def plan_status_counts(payload: dict) -> tuple[int, int, int]:
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

    corrections = [
        p for p in plans
        if str(p.get("id") or "").startswith("V13.8-QUANG-DONG-")
    ]

    return len(qd), len(province), len(corrections)


def atomic_write_json(path: Path, payload: dict) -> None:
    raw = json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
    )
    json.loads(raw)

    tmp = path.with_name(path.name + ".v13_8.tmp")
    tmp.write_text(raw, encoding="utf-8")
    os.replace(tmp, path)


def add_approved_correction_plans(
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
    for item in CORRECTIONS:
        if item["id"] in existing_ids:
            raise RuntimeError(
                f"Correction plan đã tồn tại: {item['id']}"
            )

    now = datetime.now().isoformat(timespec="seconds")

    for item in CORRECTIONS:
        plans.append({
            "id": item["id"],
            "document_code": "NGUON-SAP-NHAP-TOAN-TINH-CORRECTION",
            "document_title": (
                "Hiệu chỉnh phân nhóm từ Nguồn sáp nhập.xlsx"
            ),
            "document_date": "",
            "school_year_id": YEAR_ID,
            "commune_id": COMMUNE_ID,
            "level_code": item["level_code"],
            "source_school_ids": item["source_ids"],
            "target_school_id": item["target_id"],
            "status": "APPROVED",
            "note": item["note"],
            "created_at": now,
            "created_by": {"source": "V13_8_PARSER_CORRECTION"},
            "approved_at": now,
            "approved_by": {"source": "V13_8_PARSER_CORRECTION"},
            "updated_at": now,
            "updated_by": {"source": "V13_8_PARSER_CORRECTION"},
            "approval_warnings": [],
            "correction_backup": backup_name,
        })

    cloned["version"] = max(int(cloned.get("version") or 1), 3)
    cloned["revision"] = int(cloned.get("revision") or 0) + 1
    cloned["updated_at"] = now
    return cloned


def mark_corrections_completed(
    payload: dict,
    backup_name: str,
) -> dict:
    cloned = json.loads(
        json.dumps(payload, ensure_ascii=False)
    )
    wanted = {x["id"] for x in CORRECTIONS}
    found = 0
    now = datetime.now().isoformat(timespec="seconds")

    for plan in cloned["plans"]:
        if not isinstance(plan, dict):
            continue
        if str(plan.get("id") or "") not in wanted:
            continue
        if str(plan.get("status") or "").upper() != "APPROVED":
            raise RuntimeError(
                f"{plan.get('id')} không còn APPROVED."
            )
        plan["status"] = "COMPLETED"
        plan["completed_at"] = now
        plan["completed_by"] = "V13_8_PARSER_CORRECTION"
        plan["completion_backup"] = backup_name
        plan["updated_at"] = now
        plan["updated_by"] = {"source": "V13_8_PARSER_CORRECTION"}
        found += 1

    if found != 2:
        raise RuntimeError(
            f"Chỉ tìm thấy {found}/2 correction plan."
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


def year_aware_tables(con: sqlite3.Connection) -> list[str]:
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
        cols = {
            str(r[1])
            for r in con.execute(
                f"PRAGMA table_info({qident(table)})"
            ).fetchall()
        }
        if {"school_id", "school_year_id"} <= cols:
            result.append(table)

    return result


def past_snapshot(
    con: sqlite3.Connection,
    source_ids: list[int],
    past_year_ids: list[int],
) -> dict[str, tuple[int, str]]:
    result = {}
    if not source_ids or not past_year_ids:
        return result

    for table in year_aware_tables(con):
        rows = con.execute(
            f"SELECT * FROM {qident(table)} "
            f"WHERE school_id IN ({markers(len(source_ids))}) "
            f"AND school_year_id IN ({markers(len(past_year_ids))})",
            [*source_ids, *past_year_ids],
        ).fetchall()

        cols = [
            str(r[1])
            for r in con.execute(
                f"PRAGMA table_info({qident(table)})"
            ).fetchall()
        ]

        lines = []
        for row in rows:
            obj = {
                col: (
                    row[col].hex()
                    if isinstance(row[col], bytes)
                    else row[col]
                )
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


def write_csv(path: Path, headers: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm", default="")
    args = parser.parse_args()

    print("=" * 126)
    print("V13.8 - HIỆU CHỈNH QUANG ĐỒNG")
    print("=" * 126)
    print(
        "Chế độ:",
        "APPLY THẬT" if args.apply else "PREFLIGHT - KHÔNG GHI",
    )

    for path in (DB_PATH, PLAN_FILE, SERVICE):
        if not path.exists():
            raise RuntimeError(f"Không tìm thấy: {path}")

    if sha256(SERVICE) != EXPECTED_SERVICE_SHA:
        raise RuntimeError(
            "Engine không đúng V13.5.2 đã hậu kiểm."
        )

    payload_before = load_payload()
    qd, province, correction_count = plan_status_counts(payload_before)

    if qd != 6 or province != 412:
        raise RuntimeError(
            f"Registry nền sai: QĐ3805={qd}, province={province}."
        )
    if correction_count != 0:
        raise RuntimeError(
            f"Đã có {correction_count} plan V13.8; "
            "không tự chạy lại."
        )

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

        for school_id, expected in EXPECTED_SCHOOLS.items():
            row = con.execute(
                """
                SELECT id,code,name,commune_id,is_active
                FROM schools
                WHERE id=?
                """,
                (school_id,),
            ).fetchone()
            if row is None:
                raise RuntimeError(
                    f"Không tìm thấy school_id={school_id}."
                )

            code, name, level = expected
            if str(row["code"] or "") != code:
                raise RuntimeError(
                    f"school_id={school_id} sai code."
                )
            if str(row["name"] or "") != name:
                raise RuntimeError(
                    f"school_id={school_id} sai tên: {row['name']!r}."
                )
            if int(row["commune_id"] or 0) != COMMUNE_ID:
                raise RuntimeError(
                    f"school_id={school_id} không thuộc Quang Đồng."
                )
            if int(row["is_active"] or 0) != 1:
                raise RuntimeError(
                    f"school_id={school_id} không còn active."
                )

            levels = merger._school_levels(
                con,
                school_id,
                YEAR_ID,
            )
            if levels != {level}:
                raise RuntimeError(
                    f"school_id={school_id} level={levels}, cần {{{level}}}."
                )

        # Nhóm 627 cũ phải đã COMPLETED [1231] -> 1232.
        candidates = [
            p for p in payload_before["plans"]
            if (
                isinstance(p, dict)
                and str(p.get("document_code") or "")
                == "NGUON-SAP-NHAP-TOAN-TINH"
                and "Nhóm 627 " in str(p.get("note") or "")
            )
        ]
        if len(candidates) != 1:
            raise RuntimeError(
                f"Phải tìm đúng 1 Nhóm 627; hiện={len(candidates)}."
            )
        g627 = candidates[0]
        if (
            str(g627.get("status") or "").upper() != "COMPLETED"
            or sorted(int(x) for x in g627.get("source_school_ids") or [])
            != [1231]
            or int(g627.get("target_school_id") or 0) != 1232
        ):
            raise RuntimeError(
                "Nhóm 627 không còn đúng [1231] -> 1232 COMPLETED."
            )

    print()
    print("PREFLIGHT PASS")
    print(" - QĐ3805 COMPLETED: 6")
    print(" - Province COMPLETED: 412")
    print(" - Quang Đồng MN: 613,615 -> 614")
    print(" - Quang Đồng TH residual: 1230 -> 1232")
    print(" - Nhóm 627 cũ [1231] -> 1232: giữ nguyên, không chạy lại")
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
        / f"backup_truoc_v13_8_quang_dong_{stamp}"
    )
    backup_dir.mkdir(parents=True, exist_ok=False)

    backup_db = backup_dir / "phocap.db"
    backup_plan = backup_dir / "school_merger_approved_plans.json"

    print("Đang backup DB + Plan JSON...", flush=True)
    sqlite_backup(DB_PATH, backup_db)
    shutil.copy2(PLAN_FILE, backup_plan)

    with connect_ro(backup_db) as chk:
        bi, bf = db_health(chk)
        if bi.lower() != "ok" or bf:
            raise RuntimeError(
                f"Backup DB lỗi: integrity={bi}, FK={bf}"
            )

    backup_name = backup_dir.name

    # Ghi 2 correction plan APPROVED trước transaction.
    approved_payload = add_approved_correction_plans(
        payload_before,
        backup_name,
    )
    atomic_write_json(PLAN_FILE, approved_payload)

    con = sqlite3.connect(str(DB_PATH), timeout=120)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")

    committed = False
    post_verified = False
    result_rows = []

    all_sources = [613, 615, 1230]

    try:
        con.execute("BEGIN IMMEDIATE")

        move_year_ids, past_year_ids = merger._year_scope_ids(
            con,
            YEAR_ID,
        )
        if move_year_ids != [2, 8]:
            raise RuntimeError(
                f"CURRENT+FUTURE sai: {move_year_ids}"
            )

        previous_year_id = merger._previous_year_id(
            con,
            YEAR_ID,
        )
        if previous_year_id != 1:
            raise RuntimeError(
                f"previous_year_id={previous_year_id}, cần 1."
            )

        past_before = past_snapshot(
            con,
            all_sources,
            past_year_ids,
        )

        for index, item in enumerate(CORRECTIONS, start=1):
            print(
                f"Thực hiện {index}/2: "
                f"{item['source_ids']} -> {item['target_id']}...",
                flush=True,
            )

            result = merger._apply_merge(
                con,
                selected_year_id=YEAR_ID,
                previous_year_id=previous_year_id,
                target_school_id=item["target_id"],
                source_ids=item["source_ids"],
                actor_user_id=None,
                backup_name=backup_name,
                record_audit=True,
            )

            actual = {
                "users_moved": int(result.get("users_moved") or 0),
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

            if actual != item["expected"]:
                raise RuntimeError(
                    f"{item['id']} khác mô phỏng V13.7: "
                    f"actual={actual}, expected={item['expected']}"
                )

            result_rows.append({
                "plan_id": item["id"],
                "level_code": item["level_code"],
                "source_ids": ",".join(
                    str(x) for x in item["source_ids"]
                ),
                "target_id": item["target_id"],
                **actual,
                "result": "PASS",
            })

        past_after = past_snapshot(
            con,
            all_sources,
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

        active_sources = int(
            con.execute(
                f"SELECT COUNT(*) FROM schools "
                f"WHERE id IN ({markers(len(all_sources))}) "
                "AND is_active=1",
                all_sources,
            ).fetchone()[0]
            or 0
        )
        if active_sources != 0:
            raise RuntimeError(
                f"Còn {active_sources} source active."
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
                f"Precommit DB lỗi: integrity={integrity_pre}, FK={fk_pre}"
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
                f"Postcommit DB lỗi: integrity={integrity_post}, FK={fk_post}"
            )

        post_verified = True

    except Exception:
        if not committed:
            try:
                con.rollback()
            except Exception:
                pass
            shutil.copy2(backup_plan, PLAN_FILE)
        elif not post_verified:
            con.close()
            con = None
            print(
                "Post-check DB lỗi; đang restore DB + Plan JSON...",
                flush=True,
            )
            sqlite_restore(backup_db, DB_PATH)
            shutil.copy2(backup_plan, PLAN_FILE)
        raise
    finally:
        if con is not None:
            con.close()

    # DB đã commit + post-check PASS.
    try:
        current_payload = load_payload()
        completed_payload = mark_corrections_completed(
            current_payload,
            backup_name,
        )
        atomic_write_json(PLAN_FILE, completed_payload)
    except Exception as exc:
        emergency = (
            backup_dir
            / "CAN_DONG_BO_PLAN_JSON_V13_8.txt"
        )
        emergency.write_text(
            "\n".join([
                "DATABASE V13.8 ĐÃ COMMIT VÀ POST-CHECK PASS.",
                f"Lỗi Plan JSON: {repr(exc)}",
                "KHÔNG chạy lại V13.8.",
            ]),
            encoding="utf-8",
        )
        raise RuntimeError(
            "DB đã hiệu chỉnh thành công nhưng Plan JSON chưa đồng bộ. "
            f"KHÔNG chạy lại. Xem {emergency}"
        ) from exc

    # Audit cuối.
    final_payload = load_payload()
    qd_final, province_final, correction_final = (
        plan_status_counts(final_payload)
    )

    correction_completed = [
        p for p in final_payload["plans"]
        if (
            isinstance(p, dict)
            and str(p.get("id") or "")
            in {x["id"] for x in CORRECTIONS}
            and str(p.get("status") or "").upper()
            == "COMPLETED"
        )
    ]

    with connect_ro() as final_con:
        final_integrity, final_fk = db_health(final_con)

        final_source_active = int(
            final_con.execute(
                f"SELECT COUNT(*) FROM schools "
                f"WHERE id IN ({markers(len(all_sources))}) "
                "AND is_active=1",
                all_sources,
            ).fetchone()[0]
            or 0
        )

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

    success = (
        qd_final == 6
        and province_final == 412
        and correction_final == 2
        and len(correction_completed) == 2
        and final_integrity.lower() == "ok"
        and final_fk == 0
        and final_source_active == 0
        and final_operations == 2
    )

    if not success:
        raise RuntimeError(
            "Audit cuối V13.8 chưa đạt; KHÔNG chạy lại."
        )

    report_dir = (
        ROOT
        / f"bao_cao_v13_8_quang_dong_{stamp}"
    )
    report_dir.mkdir(parents=True, exist_ok=False)

    write_csv(
        report_dir / "770_KET_QUA_2_HIEU_CHINH.csv",
        [
            "plan_id",
            "level_code",
            "source_ids",
            "target_id",
            "users_moved",
            "source_school_logins_disabled",
            "staff_rollover_created",
            "sources_deactivated",
            "result",
        ],
        result_rows,
    )

    gate_rows = [
        {"check": "qd3805_completed", "result": "PASS", "detail": "6"},
        {"check": "province_412_completed", "result": "PASS", "detail": "412"},
        {"check": "correction_plans_completed", "result": "PASS", "detail": "2"},
        {"check": "source_active_after", "result": "PASS", "detail": "0"},
        {"check": "audit_operations", "result": "PASS", "detail": "2"},
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
            "check": "V13_8_QUANG_DONG_CLOSED",
            "result": "YES",
            "detail": (
                "Quang Đồng đã hiệu chỉnh đúng thành 2 phép cùng cấp; "
                "Nhóm 627 cũ không chạy lại."
            ),
        },
    ]

    write_csv(
        report_dir / "771_GATE_V13_8.csv",
        ["check", "result", "detail"],
        gate_rows,
    )

    summary = f"""V13.8 - HIỆU CHỈNH QUANG ĐỒNG
================================================================================

STATUS=SUCCESS

MN:
613,615 -> 614
- users moved = 60
- source logins disabled = 2
- staff rollover created = 6
- sources deactivated = 2

TH:
1230 -> 1232
- users moved = 0
- source logins disabled = 1
- staff rollover created = 36
- sources deactivated = 1

Nhóm 627 cũ:
1231 -> 1232
- GIỮ NGUYÊN COMPLETED
- KHÔNG chạy lại

Registry:
- QĐ3805 COMPLETED = {qd_final}
- Province COMPLETED = {province_final}
- Correction COMPLETED = {len(correction_completed)}

Database:
- integrity = {final_integrity}
- FK = {final_fk}
- source active còn lại = {final_source_active}
- audit operations V13.8 = {final_operations}

Backup:
{backup_dir}

V13_8_QUANG_DONG_CLOSED=YES
"""

    (report_dir / "00_TONG_QUAN_V13_8.txt").write_text(
        summary,
        encoding="utf-8",
    )

    zip_path = (
        ROOT
        / f"bao_cao_v13_8_quang_dong_{stamp}.zip"
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
    print("V13.8 THÀNH CÔNG")
    print("=" * 126)
    print("Quang Đồng MN: 613,615 -> 614 COMPLETED")
    print("Quang Đồng TH: 1230 -> 1232 COMPLETED")
    print("Nhóm 627 cũ: KHÔNG chạy lại")
    print("Correction plans COMPLETED: 2")
    print(f"DB integrity: {final_integrity}")
    print(f"DB FK errors: {final_fk}")
    print("V13_8_QUANG_DONG_CLOSED: YES")
    print(f"Backup: {backup_dir}")
    print(f"ZIP: {zip_path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print()
        print("=" * 126)
        print("V13.8 DỪNG AN TOÀN")
        print("=" * 126)
        print(repr(exc))
        print(
            "Nếu lỗi nói DB đã commit nhưng Plan JSON chưa đồng bộ: "
            "KHÔNG chạy lại V13.8."
        )
        raise SystemExit(2)
