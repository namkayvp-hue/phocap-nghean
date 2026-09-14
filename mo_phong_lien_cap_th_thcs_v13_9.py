# -*- coding: utf-8 -*-
r"""
V13.9 - MÔ PHỎNG ĐÚNG CẤU TRÚC LIÊN CẤP TH + THCS
===================================================

BỐI CẢNH
--------
V13.7 xác nhận hai phép sáp nhập nghiệp vụ đều chạy được, nhưng trường đích
sau mô phỏng vẫn chỉ mang level THCS vì năm 2026-2027 chưa có
school_network_year_data của cả hai cấp.

Hai trường hợp chính thức cần xử lý:
1) Mường Quàng
   TH Châu Thôn (1150) -> Trường THCS Châu Thôn (1593)

2) Hữu Khuông
   PTDTBT Tiểu học Hữu Khuông (1101)
   -> PTDTBT THCS Hữu Khuông (1559)

MỤC TIÊU V13.9
--------------
Chỉ mô phỏng RAM, KHÔNG sửa DB thật/Plan JSON.

Với mỗi trường hợp:
A. Khảo sát schema/index của school_network_year_data.
B. Giữ nguyên toàn bộ dữ liệu PAST.
C. Tạo "baseline CURRENT" cho trường đích ở năm 2026-2027:
   - một dòng TH lấy từ baseline 2025-2026 của trường nguồn;
   - một dòng THCS lấy từ baseline 2025-2026 của trường đích;
   - không sửa/ghi đè dữ liệu 2025-2026.
D. Xác nhận target levels = {TH, THCS}.
E. Chạy _apply_merge trên RAM.
F. Xác nhận sau merge:
   - target vẫn {TH, THCS};
   - source inactive;
   - target active;
   - CURRENT/FUTURE residual tại source = 0;
   - PAST hash source + target không đổi;
   - integrity=ok, FK=0.

V13.9 KHÔNG:
- tạo plan;
- đổi tên trường;
- đổi mã trường;
- chạy thật;
- đụng 412 plan đã COMPLETED;
- đụng Quang Đồng đã đóng V13.8.

CHẠY
----
cd C:\PhoCap
.\.venv\Scripts\python.exe .\mo_phong_lien_cap_th_thcs_v13_9.py
"""

from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
import sys
import time
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(r"C:\PhoCap")
DB_PATH = ROOT / "data" / "phocap.db"
PLAN_FILE = ROOT / "data" / "school_merger_approved_plans.json"
SERVICE = ROOT / "app" / "services" / "school_merger_service.py"

YEAR_ID = 2
YEAR_CODE = "2026-2027"
PREVIOUS_YEAR_ID = 1

EXPECTED_SERVICE_SHA = (
    "414fb49a4c5f4fed7b571cc55df381678fe660cd8a675ecaa2f6fd70ebd7827a"
)

CASES = [
    {
        "label": "MUONG_QUANG",
        "commune_id": 10,
        "source_id": 1150,
        "target_id": 1593,
        "source_level": "TH",
        "target_level": "THCS",
        "expected_source_name": "TH Châu Thôn",
        "expected_target_name": "Trường THCS Châu Thôn",
        "expected": {
            "users_moved": 0,
            "source_school_logins_disabled": 1,
            "staff_rollover_created": 50,
            "sources_deactivated": 1,
        },
    },
    {
        "label": "HUU_KHUONG",
        "commune_id": 29,
        "source_id": 1101,
        "target_id": 1559,
        "source_level": "TH",
        "target_level": "THCS",
        "expected_source_name": "PTDTBT Tiểu học Hữu Khuông",
        "expected_target_name": "PTDTBT THCS Hữu Khuông",
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


def connect_ro() -> sqlite3.Connection:
    uri = DB_PATH.resolve().as_uri() + "?mode=ro"
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


def load_plans() -> list[dict]:
    payload = json.loads(
        PLAN_FILE.read_text(encoding="utf-8")
    )
    return [
        p for p in payload.get("plans") or []
        if isinstance(p, dict)
    ]


def verify_registry_closed(plans: list[dict]) -> dict[str, int]:
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
        if (
            str(p.get("id") or "").startswith("V13.8-QUANG-DONG-")
            and str(p.get("status") or "").upper() == "COMPLETED"
        )
    ]

    if len(qd) != 6:
        raise RuntimeError(f"QĐ3805 COMPLETED={len(qd)}, cần 6.")
    if len(province) != 412:
        raise RuntimeError(
            f"Province COMPLETED={len(province)}, cần 412."
        )
    if len(corrections) != 2:
        raise RuntimeError(
            f"V13.8 correction COMPLETED={len(corrections)}, cần 2."
        )

    return {
        "qd3805": len(qd),
        "province": len(province),
        "quang_dong_corrections": len(corrections),
    }


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


def network_schema_report(
    con: sqlite3.Connection,
) -> tuple[list[dict], list[dict]]:
    cols = [
        {
            "cid": int(r["cid"]),
            "name": str(r["name"]),
            "type": str(r["type"] or ""),
            "notnull": int(r["notnull"] or 0),
            "default": (
                str(r["dflt_value"])
                if r["dflt_value"] is not None
                else ""
            ),
            "pk": int(r["pk"] or 0),
        }
        for r in con.execute(
            'PRAGMA table_info("school_network_year_data")'
        ).fetchall()
    ]

    indexes = []
    for idx in con.execute(
        'PRAGMA index_list("school_network_year_data")'
    ).fetchall():
        name = str(idx["name"])
        index_cols = [
            str(x["name"])
            for x in con.execute(
                f"PRAGMA index_info({qident(name)})"
            ).fetchall()
        ]
        indexes.append({
            "name": name,
            "unique": int(idx["unique"] or 0),
            "origin": str(idx["origin"] or ""),
            "partial": int(idx["partial"] or 0),
            "columns": ",".join(index_cols),
        })

    required = {
        "id",
        "school_id",
        "school_year_id",
        "level_code",
        "data_json",
        "source_name",
        "imported_at",
    }
    actual = {x["name"] for x in cols}
    if not required <= actual:
        raise RuntimeError(
            "school_network_year_data thiếu cột: "
            + repr(sorted(required - actual))
        )

    # Dual-level phải không bị unique chỉ trên school_id+school_year_id.
    for idx in indexes:
        if not idx["unique"]:
            continue
        cols_idx = [
            x for x in idx["columns"].split(",")
            if x
        ]
        if (
            set(cols_idx) == {"school_id", "school_year_id"}
            and "level_code" not in cols_idx
        ):
            raise RuntimeError(
                "Schema hiện có unique school_id+school_year_id, "
                "không cho phép một trường mang đồng thời TH và THCS."
            )

    return cols, indexes


def school_info(
    con: sqlite3.Connection,
    school_id: int,
) -> dict:
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
    return dict(row)


def network_rows(
    con: sqlite3.Connection,
    school_id: int,
) -> list[dict]:
    rows = con.execute(
        """
        SELECT id,school_id,school_year_id,level_code,
               data_json,source_name,imported_at
        FROM school_network_year_data
        WHERE school_id=?
        ORDER BY school_year_id,id
        """,
        (school_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def single_network_baseline(
    con: sqlite3.Connection,
    *,
    school_id: int,
    year_id: int,
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
        (school_id, year_id, level_code.upper()),
    ).fetchall()

    if len(rows) != 1:
        raise RuntimeError(
            f"school_id={school_id}, year={year_id}, "
            f"level={level_code}: cần đúng 1 baseline; hiện={len(rows)}."
        )
    return rows[0]


def ensure_current_network_row(
    con: sqlite3.Connection,
    *,
    target_school_id: int,
    current_year_id: int,
    level_code: str,
    baseline: sqlite3.Row,
    provenance: str,
) -> str:
    existing = con.execute(
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
            current_year_id,
            level_code.upper(),
        ),
    ).fetchall()

    if len(existing) > 1:
        raise RuntimeError(
            f"Target {target_school_id} có {len(existing)} "
            f"dòng CURRENT level={level_code}; dừng."
        )

    if len(existing) == 1:
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
            current_year_id,
            level_code.upper(),
            baseline["data_json"],
            provenance,
        ),
    )
    return "CREATED_FROM_PREVIOUS_YEAR"


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

        result[table] = (
            len(lines),
            h.hexdigest(),
        )

    return result


def current_future_residual(
    con: sqlite3.Connection,
    source_id: int,
    move_year_ids: list[int],
) -> int:
    total = 0
    for table in year_aware_tables(con):
        total += int(
            con.execute(
                f"SELECT COUNT(*) FROM {qident(table)} "
                f"WHERE school_id=? "
                f"AND school_year_id IN ({markers(len(move_year_ids))})",
                [source_id, *move_year_ids],
            ).fetchone()[0]
            or 0
        )
    return total


def simulate_case(
    source_con: sqlite3.Connection,
    merger,
    case: dict,
) -> dict:
    mem = sqlite3.connect(":memory:")
    mem.row_factory = sqlite3.Row

    try:
        source_con.backup(mem)
        mem.execute("PRAGMA foreign_keys=ON")

        move_year_ids, past_year_ids = merger._year_scope_ids(
            mem,
            YEAR_ID,
        )
        previous_year_id = merger._previous_year_id(
            mem,
            YEAR_ID,
        )

        if move_year_ids != [2, 8]:
            raise RuntimeError(
                f"{case['label']}: CURRENT+FUTURE={move_year_ids}, cần [2,8]."
            )
        if previous_year_id != PREVIOUS_YEAR_ID:
            raise RuntimeError(
                f"{case['label']}: previous={previous_year_id}, cần 1."
            )

        source_id = int(case["source_id"])
        target_id = int(case["target_id"])

        past_before = past_hashes(
            mem,
            [source_id, target_id],
            past_year_ids,
        )

        source_levels_before = sorted(
            merger._school_levels(mem, source_id, YEAR_ID)
        )
        target_levels_before = sorted(
            merger._school_levels(mem, target_id, YEAR_ID)
        )

        # Baseline PAST của từng cấp.
        source_baseline = single_network_baseline(
            mem,
            school_id=source_id,
            year_id=PREVIOUS_YEAR_ID,
            level_code=case["source_level"],
        )
        target_baseline = single_network_baseline(
            mem,
            school_id=target_id,
            year_id=PREVIOUS_YEAR_ID,
            level_code=case["target_level"],
        )

        mem.execute("BEGIN")

        th_action = ensure_current_network_row(
            mem,
            target_school_id=target_id,
            current_year_id=YEAR_ID,
            level_code=case["source_level"],
            baseline=source_baseline,
            provenance=(
                f"V13.9-LIENCAP-{case['label']}-"
                f"{case['source_level']}-FROM-{source_id}-Y{PREVIOUS_YEAR_ID}"
            ),
        )

        thcs_action = ensure_current_network_row(
            mem,
            target_school_id=target_id,
            current_year_id=YEAR_ID,
            level_code=case["target_level"],
            baseline=target_baseline,
            provenance=(
                f"V13.9-LIENCAP-{case['label']}-"
                f"{case['target_level']}-FROM-{target_id}-Y{PREVIOUS_YEAR_ID}"
            ),
        )

        levels_after_seed = sorted(
            merger._school_levels(mem, target_id, YEAR_ID)
        )
        expected_levels = sorted(
            {
                case["source_level"],
                case["target_level"],
            }
        )
        if levels_after_seed != expected_levels:
            raise RuntimeError(
                f"{case['label']}: sau seed levels={levels_after_seed}, "
                f"cần={expected_levels}."
            )

        result = merger._apply_merge(
            mem,
            selected_year_id=YEAR_ID,
            previous_year_id=previous_year_id,
            target_school_id=target_id,
            source_ids=[source_id],
            actor_user_id=None,
            backup_name="V13.9-RAM-SIMULATION",
            record_audit=False,
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

        if actual != case["expected"]:
            raise RuntimeError(
                f"{case['label']}: kết quả khác V13.7: "
                f"actual={actual}, expected={case['expected']}."
            )

        levels_after_merge = sorted(
            merger._school_levels(mem, target_id, YEAR_ID)
        )

        source_state = int(
            mem.execute(
                "SELECT is_active FROM schools WHERE id=?",
                (source_id,),
            ).fetchone()[0]
            or 0
        )
        target_state = int(
            mem.execute(
                "SELECT is_active FROM schools WHERE id=?",
                (target_id,),
            ).fetchone()[0]
            or 0
        )

        residual = current_future_residual(
            mem,
            source_id,
            move_year_ids,
        )

        past_after = past_hashes(
            mem,
            [source_id, target_id],
            past_year_ids,
        )
        past_unchanged = past_before == past_after

        integrity = str(
            mem.execute("PRAGMA integrity_check").fetchone()[0]
        )
        fk = len(
            mem.execute("PRAGMA foreign_key_check").fetchall()
        )

        network_current = [
            dict(r)
            for r in mem.execute(
                """
                SELECT id,school_id,school_year_id,level_code,
                       data_json,source_name,imported_at
                FROM school_network_year_data
                WHERE school_id=? AND school_year_id=?
                ORDER BY level_code,id
                """,
                (target_id, YEAR_ID),
            ).fetchall()
        ]

        mem.rollback()

        passed = (
            levels_after_seed == expected_levels
            and levels_after_merge == expected_levels
            and source_state == 0
            and target_state == 1
            and residual == 0
            and past_unchanged
            and integrity.lower() == "ok"
            and fk == 0
        )

        return {
            "label": case["label"],
            "source_id": source_id,
            "target_id": target_id,
            "source_levels_before": source_levels_before,
            "target_levels_before": target_levels_before,
            "seed_source_level_action": th_action,
            "seed_target_level_action": thcs_action,
            "levels_after_seed": levels_after_seed,
            "levels_after_merge": levels_after_merge,
            **actual,
            "source_is_active_after": source_state,
            "target_is_active_after": target_state,
            "current_future_residual": residual,
            "past_unchanged": past_unchanged,
            "integrity": integrity,
            "fk": fk,
            "network_current": network_current,
            "result": "PASS" if passed else "FAIL",
            "error": "",
        }

    except Exception as exc:
        return {
            "label": case["label"],
            "source_id": case["source_id"],
            "target_id": case["target_id"],
            "source_levels_before": [],
            "target_levels_before": [],
            "seed_source_level_action": "",
            "seed_target_level_action": "",
            "levels_after_seed": [],
            "levels_after_merge": [],
            "users_moved": "",
            "source_school_logins_disabled": "",
            "staff_rollover_created": "",
            "sources_deactivated": "",
            "source_is_active_after": "",
            "target_is_active_after": "",
            "current_future_residual": "",
            "past_unchanged": False,
            "integrity": "",
            "fk": "",
            "network_current": [],
            "result": "FAIL",
            "error": repr(exc),
        }
    finally:
        mem.close()


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
    started = time.monotonic()

    print("=" * 126)
    print("V13.9 - MÔ PHỎNG LIÊN CẤP TH + THCS")
    print("=" * 126)
    print("CHỈ ĐỌC / RAM - KHÔNG SỬA DB / PLAN JSON")

    for path in (DB_PATH, PLAN_FILE, SERVICE):
        if not path.exists():
            raise RuntimeError(
                f"Không tìm thấy: {path}"
            )

    service_sha = sha256(SERVICE)
    if service_sha != EXPECTED_SERVICE_SHA:
        raise RuntimeError(
            "Engine không đúng V13.5.2 đã hậu kiểm.\n"
            f"SHA hiện={service_sha}\n"
            f"SHA cần={EXPECTED_SERVICE_SHA}"
        )

    plans = load_plans()
    registry = verify_registry_closed(plans)

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

        columns, indexes = network_schema_report(con)

        school_rows = []
        baseline_rows = []

        for case in CASES:
            source = school_info(con, case["source_id"])
            target = school_info(con, case["target_id"])

            if int(source["commune_id"] or 0) != case["commune_id"]:
                raise RuntimeError(
                    f"{case['label']}: source sai commune."
                )
            if int(target["commune_id"] or 0) != case["commune_id"]:
                raise RuntimeError(
                    f"{case['label']}: target sai commune."
                )
            if str(source["name"] or "") != case["expected_source_name"]:
                raise RuntimeError(
                    f"{case['label']}: source name={source['name']!r}."
                )
            if str(target["name"] or "") != case["expected_target_name"]:
                raise RuntimeError(
                    f"{case['label']}: target name={target['name']!r}."
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

            if source_levels != {case["source_level"]}:
                raise RuntimeError(
                    f"{case['label']}: source levels={source_levels}."
                )
            if target_levels != {case["target_level"]}:
                raise RuntimeError(
                    f"{case['label']}: target levels={target_levels}."
                )

            for role, school, levels in (
                ("SOURCE", source, source_levels),
                ("TARGET", target, target_levels),
            ):
                school_rows.append({
                    "case": case["label"],
                    "role": role,
                    "school_id": int(school["id"]),
                    "code": school["code"],
                    "name": school["name"],
                    "commune_id": int(school["commune_id"]),
                    "is_active": int(school["is_active"] or 0),
                    "levels": ",".join(sorted(levels)),
                })

            for row in network_rows(con, case["source_id"]):
                baseline_rows.append({
                    "case": case["label"],
                    "role": "SOURCE",
                    **row,
                })
            for row in network_rows(con, case["target_id"]):
                baseline_rows.append({
                    "case": case["label"],
                    "role": "TARGET",
                    **row,
                })

        simulations = []
        for case in CASES:
            print(
                f"Mô phỏng {case['label']}: "
                f"{case['source_id']} -> {case['target_id']}...",
                flush=True,
            )
            simulations.append(
                simulate_case(
                    con,
                    merger,
                    case,
                )
            )

    all_pass = all(
        row["result"] == "PASS"
        for row in simulations
    )

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_dir = (
        ROOT
        / f"bao_cao_v13_9_lien_cap_th_thcs_{stamp}"
    )
    zip_path = (
        ROOT
        / f"bao_cao_v13_9_lien_cap_th_thcs_{stamp}.zip"
    )
    report_dir.mkdir(
        parents=True,
        exist_ok=False,
    )

    write_csv(
        report_dir / "780_SCHEMA_SCHOOL_NETWORK.csv",
        [
            "cid",
            "name",
            "type",
            "notnull",
            "default",
            "pk",
        ],
        columns,
    )

    write_csv(
        report_dir / "781_INDEX_SCHOOL_NETWORK.csv",
        [
            "name",
            "unique",
            "origin",
            "partial",
            "columns",
        ],
        indexes,
    )

    write_csv(
        report_dir / "782_TRUONG_LIEN_CAP.csv",
        [
            "case",
            "role",
            "school_id",
            "code",
            "name",
            "commune_id",
            "is_active",
            "levels",
        ],
        school_rows,
    )

    write_csv(
        report_dir / "783_BASELINE_NETWORK_ROWS.csv",
        [
            "case",
            "role",
            "id",
            "school_id",
            "school_year_id",
            "level_code",
            "data_json",
            "source_name",
            "imported_at",
        ],
        baseline_rows,
    )

    sim_rows = []
    current_network_rows = []

    for row in simulations:
        sim_rows.append({
            "label": row["label"],
            "source_id": row["source_id"],
            "target_id": row["target_id"],
            "source_levels_before": ",".join(row["source_levels_before"]),
            "target_levels_before": ",".join(row["target_levels_before"]),
            "seed_source_level_action": row["seed_source_level_action"],
            "seed_target_level_action": row["seed_target_level_action"],
            "levels_after_seed": ",".join(row["levels_after_seed"]),
            "levels_after_merge": ",".join(row["levels_after_merge"]),
            "users_moved": row["users_moved"],
            "source_school_logins_disabled": (
                row["source_school_logins_disabled"]
            ),
            "staff_rollover_created": row["staff_rollover_created"],
            "sources_deactivated": row["sources_deactivated"],
            "source_is_active_after": row["source_is_active_after"],
            "target_is_active_after": row["target_is_active_after"],
            "current_future_residual": row["current_future_residual"],
            "past_unchanged": row["past_unchanged"],
            "integrity": row["integrity"],
            "fk": row["fk"],
            "result": row["result"],
            "error": row["error"],
        })

        for nrow in row["network_current"]:
            current_network_rows.append({
                "case": row["label"],
                **nrow,
            })

    write_csv(
        report_dir / "784_MO_PHONG_LIEN_CAP.csv",
        [
            "label",
            "source_id",
            "target_id",
            "source_levels_before",
            "target_levels_before",
            "seed_source_level_action",
            "seed_target_level_action",
            "levels_after_seed",
            "levels_after_merge",
            "users_moved",
            "source_school_logins_disabled",
            "staff_rollover_created",
            "sources_deactivated",
            "source_is_active_after",
            "target_is_active_after",
            "current_future_residual",
            "past_unchanged",
            "integrity",
            "fk",
            "result",
            "error",
        ],
        sim_rows,
    )

    write_csv(
        report_dir / "785_TARGET_CURRENT_NETWORK_AFTER_SIM.csv",
        [
            "case",
            "id",
            "school_id",
            "school_year_id",
            "level_code",
            "data_json",
            "source_name",
            "imported_at",
        ],
        current_network_rows,
    )

    gate_rows = [
        {
            "check": "qd3805_completed",
            "result": "PASS",
            "detail": str(registry["qd3805"]),
        },
        {
            "check": "province_412_completed",
            "result": "PASS",
            "detail": str(registry["province"]),
        },
        {
            "check": "quang_dong_v13_8_completed",
            "result": "PASS",
            "detail": str(registry["quang_dong_corrections"]),
        },
        {
            "check": "muong_quang_dual_level",
            "result": (
                "PASS"
                if simulations[0]["result"] == "PASS"
                else "FAIL"
            ),
            "detail": (
                ",".join(simulations[0]["levels_after_merge"])
                or simulations[0]["error"]
            ),
        },
        {
            "check": "huu_khuong_dual_level",
            "result": (
                "PASS"
                if simulations[1]["result"] == "PASS"
                else "FAIL"
            ),
            "detail": (
                ",".join(simulations[1]["levels_after_merge"])
                or simulations[1]["error"]
            ),
        },
        {
            "check": "READY_FOR_OFFICIAL_CROSS_LEVEL_EXECUTION",
            "result": "YES" if all_pass else "NO",
            "detail": (
                "Có thể chuẩn bị V13.10 chạy thật 2 ngoại lệ liên cấp "
                "với baseline CURRENT TH+THCS."
                if all_pass
                else "Chưa được chạy thật; xem 784_MO_PHONG_LIEN_CAP.csv."
            ),
        },
    ]

    write_csv(
        report_dir / "786_GATE_V13_9.csv",
        ["check", "result", "detail"],
        gate_rows,
    )

    elapsed = time.monotonic() - started

    summary_lines = [
        "V13.9 - MÔ PHỎNG LIÊN CẤP TH + THCS",
        "=" * 90,
        "",
        f"QĐ3805 COMPLETED = {registry['qd3805']}",
        f"Province COMPLETED = {registry['province']}",
        (
            "Quang Đồng V13.8 correction COMPLETED = "
            f"{registry['quang_dong_corrections']}"
        ),
        "",
    ]

    for row in simulations:
        summary_lines.extend([
            row["label"],
            f"- source -> target: {row['source_id']} -> {row['target_id']}",
            f"- levels trước: {row['source_levels_before']} -> {row['target_levels_before']}",
            f"- levels sau seed: {row['levels_after_seed']}",
            f"- levels sau merge: {row['levels_after_merge']}",
            f"- users moved: {row['users_moved']}",
            (
                "- source login disabled: "
                f"{row['source_school_logins_disabled']}"
            ),
            f"- staff rollover: {row['staff_rollover_created']}",
            f"- source inactive: {row['source_is_active_after'] == 0}",
            f"- CURRENT/FUTURE residual: {row['current_future_residual']}",
            f"- PAST unchanged: {row['past_unchanged']}",
            f"- integrity: {row['integrity']}",
            f"- FK: {row['fk']}",
            f"- result: {row['result']}",
            f"- error: {row['error']}",
            "",
        ])

    summary_lines.extend([
        (
            "READY_FOR_OFFICIAL_CROSS_LEVEL_EXECUTION="
            + ("YES" if all_pass else "NO")
        ),
        "",
        "Database thật: KHÔNG THAY ĐỔI.",
        "Plan JSON: KHÔNG THAY ĐỔI.",
        f"Thời gian: {elapsed:.1f}s",
    ])

    (
        report_dir / "00_TONG_QUAN_V13_9.txt"
    ).write_text(
        "\n".join(summary_lines),
        encoding="utf-8",
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
    print("HOÀN THÀNH V13.9")
    print("=" * 126)

    for row in simulations:
        print(
            f"{row['label']}: {row['result']} | "
            f"levels sau={row['levels_after_merge']} | "
            f"rollover={row['staff_rollover_created']} | "
            f"residual={row['current_future_residual']}"
        )

    print(
        "READY_FOR_OFFICIAL_CROSS_LEVEL_EXECUTION: "
        + ("YES" if all_pass else "NO")
    )
    print("Database thật: KHÔNG THAY ĐỔI")
    print("Plan JSON: KHÔNG THAY ĐỔI")
    print(f"ZIP: {zip_path}")

    return 0 if all_pass else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print()
        print("=" * 126)
        print("V13.9 DỪNG AN TOÀN")
        print("=" * 126)
        print(repr(exc))
        print("Database thật: KHÔNG THAY ĐỔI")
        print("Plan JSON: KHÔNG THAY ĐỔI")
        raise SystemExit(2)
