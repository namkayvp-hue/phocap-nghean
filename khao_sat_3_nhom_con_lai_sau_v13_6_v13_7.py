# -*- coding: utf-8 -*-
r"""
V13.7 - KHẢO SÁT 3 NHÓM CÒN LẠI SAU KHI ĐÓNG 412 PHƯƠNG ÁN
=============================================================

CHỈ ĐỌC / MÔ PHỎNG RAM
----------------------
- KHÔNG sửa database thật.
- KHÔNG sửa Plan JSON.
- KHÔNG đổi tên trường.
- KHÔNG thực hiện sáp nhập thật.

BỐI CẢNH ĐÃ KHÓA
----------------
V13.6.1 đã hậu kiểm:
- QĐ3805 COMPLETED 6/6
- Province COMPLETED 412/412
- 483 source đúng trạng thái
- 5.159 CBQL/GV/NV đúng target
- 483 login nguồn đúng policy
- PAST hash không đổi
- CURRENT/FUTURE residual = 0
- DB integrity=ok, FK=0

3 nhóm từng bị chặn tại V13.3.1:
1) Nhóm 346 - Mường Quàng:
   source_id=1150 (TH) -> target_id=1593 (THCS)

2) Nhóm 567 - Hữu Khuông:
   source_id=1101 (TH) -> target_id=1559 (THCS)

3) Nhóm 626 - Quang Đồng:
   source_ids=613,615,1230 -> target_id=614
   Trong đó 613,615 là MN; 1230 là TH; target 614 là MN.

ĐỐI CHIẾU TỆP NGUỒN CHO THẤY
-----------------------------
Mường Quàng:
- "Tiểu học Châu Thôn" -> "Trường THCS Châu Thôn"
- dòng kế là "THCS Châu Thôn"
=> Có dấu hiệu liên cấp TH + THCS thật.

Hữu Khuông:
- "PTDTBT Tiểu học Hữu Khuông" -> "PTDTBT THCS Hữu Khuông"
- ghi chú tại THCS: "Liên cấp TH&THCS"
=> Đây là liên cấp TH + THCS thật.

Quang Đồng:
- Mầm non Kim Thành | PA = Mầm non Kim Thành
- Mầm non Đồng Thành | trống
- Mầm non Quang Thành | trống
- Tiểu học Đồng Thành | trống
- Tiểu học Quang Thành | PA = Tiểu học Quang Thành
- Tiểu học Kim Thành | trống
=> Nhóm 626 bị dính Tiểu học Đồng Thành do ranh giới nhóm parser.
   Không nên coi đây là sáp nhập chéo MN <- TH.

V13.7 SẼ
--------
A. Xác định chính xác tên/mã/cấp hiện tại của các ID.
B. Tìm plan COMPLETED "Nhóm 627" để lấy target TH Quang Đồng đã xử lý.
C. Lập 4 phép mô phỏng độc lập trên RAM:
   - QD-MN: 613,615 -> 614
   - QD-TH-RESIDUAL: 1230 -> target của Nhóm 627
   - MQ-LIENCAP: 1150 -> 1593
   - HK-LIENCAP: 1101 -> 1559
D. Với 2 nhóm liên cấp, ghi nhận level target trước/sau mô phỏng.
E. Không tạo plan, không ghi DB.

CHẠY
----
cd C:\PhoCap
.\.venv\Scripts\python.exe .\khao_sat_3_nhom_con_lai_sau_v13_6_v13_7.py
"""

from __future__ import annotations

import csv
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

YEAR_ID = 2
YEAR_CODE = "2026-2027"

BLOCKED_GROUPS = {
    "MQ-LIENCAP": {
        "group_no": 346,
        "commune_name": "Mường Quàng",
        "source_ids": [1150],
        "target_id": 1593,
        "expected_source_levels": {"TH"},
        "expected_target_levels": {"THCS"},
        "source_evidence": (
            'Tiểu học Châu Thôn -> "Trường THCS Châu Thôn"; '
            'dòng kế: THCS Châu Thôn.'
        ),
    },
    "HK-LIENCAP": {
        "group_no": 567,
        "commune_name": "Hữu Khuông",
        "source_ids": [1101],
        "target_id": 1559,
        "expected_source_levels": {"TH"},
        "expected_target_levels": {"THCS"},
        "source_evidence": (
            'PTDTBT Tiểu học Hữu Khuông -> '
            '"PTDTBT THCS Hữu Khuông"; ghi chú: "Liên cấp TH&THCS".'
        ),
    },
    "QD-MN": {
        "group_no": 626,
        "commune_name": "Quang Đồng",
        "source_ids": [613, 615],
        "target_id": 614,
        "expected_source_levels": {"MN"},
        "expected_target_levels": {"MN"},
        "source_evidence": (
            "Mầm non Kim Thành là target; Mầm non Đồng Thành và "
            "Mầm non Quang Thành là nguồn."
        ),
    },
}


def qident(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def write_csv(path: Path, headers: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def connect_ro() -> sqlite3.Connection:
    uri = DB_PATH.resolve().as_uri() + "?mode=ro"
    con = sqlite3.connect(uri, uri=True, timeout=60)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA query_only=ON")
    con.execute("PRAGMA foreign_keys=ON")
    return con


def load_plans() -> list[dict]:
    payload = json.loads(PLAN_FILE.read_text(encoding="utf-8"))
    return [
        p for p in payload.get("plans") or []
        if isinstance(p, dict)
    ]


def effective_status(plan: dict) -> str:
    return str(plan.get("status") or "").upper()


def find_group_627(plans: list[dict]) -> dict:
    candidates = [
        p for p in plans
        if (
            str(p.get("document_code") or "")
            == "NGUON-SAP-NHAP-TOAN-TINH"
            and "Nhóm 627 " in str(p.get("note") or "")
        )
    ]

    if len(candidates) != 1:
        raise RuntimeError(
            f"Phải tìm đúng 1 plan Nhóm 627; hiện={len(candidates)}."
        )

    plan = candidates[0]
    if effective_status(plan) != "COMPLETED":
        raise RuntimeError(
            f"Nhóm 627 phải COMPLETED; hiện={effective_status(plan)}."
        )
    if str(plan.get("level_code") or "").upper() != "TH":
        raise RuntimeError(
            f"Nhóm 627 phải cấp TH; hiện={plan.get('level_code')!r}."
        )
    return plan


def school_row(con: sqlite3.Connection, school_id: int) -> dict:
    row = con.execute(
        """
        SELECT s.id,s.code,s.name,s.commune_id,s.is_active,
               c.code AS commune_code,c.name AS commune_name
        FROM schools s
        LEFT JOIN communes c ON c.id=s.commune_id
        WHERE s.id=?
        """,
        (school_id,),
    ).fetchone()
    if row is None:
        raise RuntimeError(f"Không tìm thấy school_id={school_id}.")
    return dict(row)


def table_exists(con: sqlite3.Connection, table: str) -> bool:
    return con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone() is not None


def level_codes(
    con: sqlite3.Connection,
    school_id: int,
    year_id: int,
) -> set[str]:
    if not table_exists(con, "school_network_year_data"):
        return set()

    rows = con.execute(
        """
        SELECT DISTINCT level_code
        FROM school_network_year_data
        WHERE school_id=? AND school_year_id=?
          AND level_code IS NOT NULL
        """,
        (school_id, year_id),
    ).fetchall()

    levels = {
        str(r[0]).strip().upper()
        for r in rows
        if str(r[0] or "").strip()
    }
    if levels:
        return levels

    fallback = con.execute(
        """
        SELECT MAX(school_year_id)
        FROM school_network_year_data
        WHERE school_id=? AND school_year_id<=?
        """,
        (school_id, year_id),
    ).fetchone()
    fallback_id = (
        int(fallback[0])
        if fallback and fallback[0] is not None
        else None
    )
    if fallback_id is None:
        return set()

    rows = con.execute(
        """
        SELECT DISTINCT level_code
        FROM school_network_year_data
        WHERE school_id=? AND school_year_id=?
          AND level_code IS NOT NULL
        """,
        (school_id, fallback_id),
    ).fetchall()
    return {
        str(r[0]).strip().upper()
        for r in rows
        if str(r[0] or "").strip()
    }


def summarize_school(
    con: sqlite3.Connection,
    school_id: int,
) -> dict:
    row = school_row(con, school_id)
    levels = sorted(level_codes(con, school_id, YEAR_ID))
    row["levels"] = levels

    user_count = 0
    school_login_active = 0
    if table_exists(con, "users"):
        user_count = int(
            con.execute(
                """
                SELECT COUNT(*)
                FROM users
                WHERE school_id=? AND username NOT LIKE 'truong_%'
                """,
                (school_id,),
            ).fetchone()[0]
            or 0
        )
        school_login_active = int(
            con.execute(
                """
                SELECT COUNT(*)
                FROM users
                WHERE school_id=? AND username LIKE 'truong_%' AND is_active=1
                """,
                (school_id,),
            ).fetchone()[0]
            or 0
        )

    row["regular_users"] = user_count
    row["active_school_logins"] = school_login_active

    current_rows = {}
    tables = [
        str(r[0])
        for r in con.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type='table' AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """
        ).fetchall()
    ]
    for table in tables:
        cols = {
            str(r[1])
            for r in con.execute(
                f"PRAGMA table_info({qident(table)})"
            ).fetchall()
        }
        if {"school_id", "school_year_id"} <= cols:
            n = int(
                con.execute(
                    f"""
                    SELECT COUNT(*)
                    FROM {qident(table)}
                    WHERE school_id=? AND school_year_id=?
                    """,
                    (school_id, YEAR_ID),
                ).fetchone()[0]
                or 0
            )
            if n:
                current_rows[table] = n

    row["current_rows"] = current_rows
    return row


def inspect_registry_closed(plans: list[dict]) -> tuple[int, int]:
    qd = [
        p for p in plans
        if (
            str(p.get("id") or "").startswith("QD3805-")
            or "3805" in str(p.get("document_code") or "")
        )
        and effective_status(p) == "COMPLETED"
    ]
    province = [
        p for p in plans
        if (
            str(p.get("document_code") or "")
            == "NGUON-SAP-NHAP-TOAN-TINH"
            and effective_status(p) == "COMPLETED"
        )
    ]
    if len(qd) != 6 or len(province) != 412:
        raise RuntimeError(
            f"Registry sau V13.6 không đúng: QĐ3805={len(qd)}, "
            f"province={len(province)}."
        )
    return len(qd), len(province)


def simulate_one(
    source_con: sqlite3.Connection,
    merger,
    *,
    label: str,
    source_ids: list[int],
    target_id: int,
) -> dict:
    mem = sqlite3.connect(":memory:")
    mem.row_factory = sqlite3.Row

    try:
        source_con.backup(mem)
        mem.execute("PRAGMA foreign_keys=ON")

        previous_year_id = merger._previous_year_id(mem, YEAR_ID)

        source_levels_before = {
            sid: sorted(merger._school_levels(mem, sid, YEAR_ID))
            for sid in source_ids
        }
        target_levels_before = sorted(
            merger._school_levels(mem, target_id, YEAR_ID)
        )

        mem.execute("BEGIN")
        result = merger._apply_merge(
            mem,
            selected_year_id=YEAR_ID,
            previous_year_id=previous_year_id,
            target_school_id=target_id,
            source_ids=source_ids,
            actor_user_id=None,
            backup_name="V13.7-RAM",
            record_audit=False,
        )

        target_levels_after = sorted(
            merger._school_levels(mem, target_id, YEAR_ID)
        )

        integrity = str(
            mem.execute("PRAGMA integrity_check").fetchone()[0]
        )
        fk = len(
            mem.execute("PRAGMA foreign_key_check").fetchall()
        )

        mem.rollback()

        return {
            "label": label,
            "source_ids": source_ids,
            "target_id": target_id,
            "source_levels_before": source_levels_before,
            "target_levels_before": target_levels_before,
            "target_levels_after": target_levels_after,
            "users_moved": int(result.get("users_moved") or 0),
            "source_logins_disabled": int(
                result.get("source_school_logins_disabled") or 0
            ),
            "staff_rollover_created": int(
                result.get("staff_rollover_created") or 0
            ),
            "sources_deactivated": int(
                result.get("sources_deactivated") or 0
            ),
            "integrity": integrity,
            "fk": fk,
            "result": "PASS" if integrity.lower() == "ok" and fk == 0 else "FAIL",
            "error": "",
        }

    except Exception as exc:
        return {
            "label": label,
            "source_ids": source_ids,
            "target_id": target_id,
            "source_levels_before": {},
            "target_levels_before": [],
            "target_levels_after": [],
            "users_moved": "",
            "source_logins_disabled": "",
            "staff_rollover_created": "",
            "sources_deactivated": "",
            "integrity": "",
            "fk": "",
            "result": "FAIL",
            "error": repr(exc),
        }
    finally:
        mem.close()


def main() -> int:
    started = time.monotonic()

    print("=" * 126)
    print("V13.7 - KHẢO SÁT 3 NHÓM CÒN LẠI SAU V13.6")
    print("=" * 126)
    print("CHỈ ĐỌC / MÔ PHỎNG RAM - KHÔNG SỬA DB / PLAN JSON")

    for path in (DB_PATH, PLAN_FILE):
        if not path.exists():
            raise RuntimeError(f"Không tìm thấy: {path}")

    plans = load_plans()
    qd_count, province_count = inspect_registry_closed(plans)
    group627 = find_group_627(plans)

    qd_th_target = int(group627.get("target_school_id") or 0)
    qd_th_old_sources = [
        int(x)
        for x in group627.get("source_school_ids") or []
    ]

    if qd_th_target <= 0:
        raise RuntimeError("Nhóm 627 không có target hợp lệ.")

    # Nhóm TH Quang Đồng còn thiếu source 1230.
    tests = [
        {
            "label": "QD-MN-CORRECTED",
            "source_ids": [613, 615],
            "target_id": 614,
            "kind": "SAME_LEVEL_CORRECTION",
            "official_reason": (
                "Tách school_id=1230 (TH Đồng Thành) khỏi nhóm MN bị parser dính nhầm."
            ),
        },
        {
            "label": "QD-TH-RESIDUAL",
            "source_ids": [1230],
            "target_id": qd_th_target,
            "kind": "SAME_LEVEL_RESIDUAL",
            "official_reason": (
                "Bổ sung TH Đồng Thành vào target TH của Nhóm 627 đã COMPLETED; "
                "không chạy lại source cũ Nhóm 627."
            ),
        },
        {
            "label": "MQ-LIENCAP",
            "source_ids": [1150],
            "target_id": 1593,
            "kind": "CROSS_LEVEL_OFFICIAL",
            "official_reason": BLOCKED_GROUPS["MQ-LIENCAP"]["source_evidence"],
        },
        {
            "label": "HK-LIENCAP",
            "source_ids": [1101],
            "target_id": 1559,
            "kind": "CROSS_LEVEL_OFFICIAL",
            "official_reason": BLOCKED_GROUPS["HK-LIENCAP"]["source_evidence"],
        },
    ]

    sys.path.insert(0, str(ROOT))
    from app.services import school_merger_service as merger

    school_details = []
    simulations = []

    with connect_ro() as con:
        integrity = str(
            con.execute("PRAGMA integrity_check").fetchone()[0]
        )
        fk = len(
            con.execute("PRAGMA foreign_key_check").fetchall()
        )
        if integrity.lower() != "ok" or fk:
            raise RuntimeError(
                f"DB preflight lỗi: integrity={integrity}, FK={fk}"
            )

        all_ids = sorted({
            sid
            for test in tests
            for sid in [*test["source_ids"], test["target_id"]]
        })

        for school_id in all_ids:
            info = summarize_school(con, school_id)
            school_details.append({
                "school_id": school_id,
                "code": info.get("code") or "",
                "name": info.get("name") or "",
                "commune_id": info.get("commune_id") or "",
                "commune_code": info.get("commune_code") or "",
                "commune_name": info.get("commune_name") or "",
                "is_active": int(info.get("is_active") or 0),
                "levels": ",".join(info.get("levels") or []),
                "regular_users": info.get("regular_users"),
                "active_school_logins": info.get("active_school_logins"),
                "current_rows_json": json.dumps(
                    info.get("current_rows") or {},
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            })

        # Gate trạng thái nguồn/đích trước mô phỏng.
        details_by_id = {
            int(row["school_id"]): row
            for row in school_details
        }

        for test in tests:
            for sid in test["source_ids"]:
                row = details_by_id[sid]
                if int(row["is_active"]) != 1:
                    raise RuntimeError(
                        f"{test['label']}: source {sid} không còn active."
                    )
            target_row = details_by_id[test["target_id"]]
            if int(target_row["is_active"]) != 1:
                raise RuntimeError(
                    f"{test['label']}: target {test['target_id']} không active."
                )

        # Kiểm level kỳ vọng cho 3 nhóm gốc.
        for label in ("MQ-LIENCAP", "HK-LIENCAP", "QD-MN"):
            spec = BLOCKED_GROUPS[label]
            for sid in spec["source_ids"]:
                levels = set(details_by_id[sid]["levels"].split(",")) - {""}
                if levels != spec["expected_source_levels"]:
                    raise RuntimeError(
                        f"{label}: source {sid} levels={levels}, "
                        f"expected={spec['expected_source_levels']}"
                    )
            levels = (
                set(details_by_id[spec["target_id"]]["levels"].split(",")) - {""}
            )
            if levels != spec["expected_target_levels"]:
                raise RuntimeError(
                    f"{label}: target levels={levels}, "
                    f"expected={spec['expected_target_levels']}"
                )

        # Nhóm 627 phải là TH target, source cũ đã inactive sau V13.6.
        target627_levels = (
            set(details_by_id[qd_th_target]["levels"].split(",")) - {""}
        )
        if "TH" not in target627_levels:
            raise RuntimeError(
                f"Target Nhóm 627 không còn cấp TH: {target627_levels}"
            )

        for old_sid in qd_th_old_sources:
            old = school_row(con, old_sid)
            if int(old["is_active"] or 0) != 0:
                raise RuntimeError(
                    f"Source cũ Nhóm 627 school_id={old_sid} chưa inactive."
                )

        for test in tests:
            print(
                f"Mô phỏng {test['label']}: "
                f"{test['source_ids']} -> {test['target_id']}...",
                flush=True,
            )
            sim = simulate_one(
                con,
                merger,
                label=test["label"],
                source_ids=test["source_ids"],
                target_id=test["target_id"],
            )
            sim["kind"] = test["kind"]
            sim["official_reason"] = test["official_reason"]
            simulations.append(sim)

    # Đánh giá.
    by_label = {x["label"]: x for x in simulations}

    qd_mn_ok = (
        by_label["QD-MN-CORRECTED"]["result"] == "PASS"
        and by_label["QD-MN-CORRECTED"]["target_levels_after"] == ["MN"]
    )
    qd_th_ok = (
        by_label["QD-TH-RESIDUAL"]["result"] == "PASS"
        and "TH" in by_label["QD-TH-RESIDUAL"]["target_levels_after"]
    )

    mq = by_label["MQ-LIENCAP"]
    hk = by_label["HK-LIENCAP"]

    mq_technical = (
        mq["result"] == "PASS"
        and set(mq["target_levels_after"]) >= {"TH", "THCS"}
    )
    hk_technical = (
        hk["result"] == "PASS"
        and set(hk["target_levels_after"]) >= {"TH", "THCS"}
    )

    # V13.7 không tự kết luận chạy thật liên cấp chỉ vì kỹ thuật PASS.
    ready_quang_dong = qd_mn_ok and qd_th_ok
    cross_level_technical_pass = mq_technical and hk_technical

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_dir = ROOT / f"bao_cao_v13_7_3_nhom_con_lai_{stamp}"
    zip_path = ROOT / f"bao_cao_v13_7_3_nhom_con_lai_{stamp}.zip"
    report_dir.mkdir(parents=True, exist_ok=False)

    write_csv(
        report_dir / "760_TRUONG_LIEN_QUAN.csv",
        [
            "school_id",
            "code",
            "name",
            "commune_id",
            "commune_code",
            "commune_name",
            "is_active",
            "levels",
            "regular_users",
            "active_school_logins",
            "current_rows_json",
        ],
        school_details,
    )

    sim_rows = []
    for x in simulations:
        sim_rows.append({
            "label": x["label"],
            "kind": x["kind"],
            "source_ids": ",".join(str(v) for v in x["source_ids"]),
            "target_id": x["target_id"],
            "source_levels_before": json.dumps(
                x["source_levels_before"],
                ensure_ascii=False,
                sort_keys=True,
            ),
            "target_levels_before": ",".join(x["target_levels_before"]),
            "target_levels_after": ",".join(x["target_levels_after"]),
            "users_moved": x["users_moved"],
            "source_logins_disabled": x["source_logins_disabled"],
            "staff_rollover_created": x["staff_rollover_created"],
            "sources_deactivated": x["sources_deactivated"],
            "integrity": x["integrity"],
            "fk": x["fk"],
            "result": x["result"],
            "official_reason": x["official_reason"],
            "error": x["error"],
        })

    write_csv(
        report_dir / "761_MO_PHONG_4_PHEP.csv",
        [
            "label",
            "kind",
            "source_ids",
            "target_id",
            "source_levels_before",
            "target_levels_before",
            "target_levels_after",
            "users_moved",
            "source_logins_disabled",
            "staff_rollover_created",
            "sources_deactivated",
            "integrity",
            "fk",
            "result",
            "official_reason",
            "error",
        ],
        sim_rows,
    )

    gate_rows = [
        {
            "check": "qd3805_completed",
            "result": "PASS",
            "detail": str(qd_count),
        },
        {
            "check": "province_412_completed",
            "result": "PASS",
            "detail": str(province_count),
        },
        {
            "check": "group_627_completed",
            "result": "PASS",
            "detail": (
                f"target={qd_th_target}; old_sources={qd_th_old_sources}"
            ),
        },
        {
            "check": "quang_dong_parser_correction_mn",
            "result": "PASS" if qd_mn_ok else "FAIL",
            "detail": "613,615 -> 614",
        },
        {
            "check": "quang_dong_th_residual",
            "result": "PASS" if qd_th_ok else "FAIL",
            "detail": f"1230 -> {qd_th_target}",
        },
        {
            "check": "READY_QUANG_DONG_CORRECTION",
            "result": "YES" if ready_quang_dong else "NO",
            "detail": (
                "Có thể chuẩn bị plan/batch sửa Quang Đồng theo 2 nhóm cùng cấp."
                if ready_quang_dong
                else "Chưa được sửa Quang Đồng."
            ),
        },
        {
            "check": "muong_quang_cross_level_technical",
            "result": "PASS" if mq_technical else "FAIL",
            "detail": (
                f"target levels {mq['target_levels_before']} -> "
                f"{mq['target_levels_after']}"
            ),
        },
        {
            "check": "huu_khuong_cross_level_technical",
            "result": "PASS" if hk_technical else "FAIL",
            "detail": (
                f"target levels {hk['target_levels_before']} -> "
                f"{hk['target_levels_after']}"
            ),
        },
        {
            "check": "CROSS_LEVEL_TECHNICAL_SIMULATION",
            "result": "PASS" if cross_level_technical_pass else "FAIL",
            "detail": (
                "Kỹ thuật có thể tạo target TH+THCS trong school_network_year_data; "
                "CHƯA phải phê duyệt chạy thật."
                if cross_level_technical_pass
                else "Mô phỏng kỹ thuật liên cấp chưa đạt."
            ),
        },
        {
            "check": "V13_7_READY_FOR_NEXT_STEP",
            "result": (
                "YES"
                if ready_quang_dong and cross_level_technical_pass
                else "NO"
            ),
            "detail": (
                "Bước sau: sửa Quang Đồng riêng; sau đó thiết kế ngoại lệ "
                "official cross-level cho Mường Quàng + Hữu Khuông."
                if ready_quang_dong and cross_level_technical_pass
                else "Xem gate FAIL trước khi làm tiếp."
            ),
        },
    ]

    write_csv(
        report_dir / "762_GATE_V13_7.csv",
        ["check", "result", "detail"],
        gate_rows,
    )

    elapsed = time.monotonic() - started
    summary = f"""V13.7 - KHẢO SÁT 3 NHÓM CÒN LẠI
================================================================================

DB/PLAN:
- QĐ3805 COMPLETED = {qd_count}
- Province COMPLETED = {province_count}
- Database thật = KHÔNG THAY ĐỔI
- Plan JSON = KHÔNG THAY ĐỔI

QUANG ĐỒNG:
- Nhóm 626 ban đầu bị parser dính school_id=1230 (TH) vào nhóm MN.
- Nhóm MN đúng: 613,615 -> 614
  Simulation = {by_label['QD-MN-CORRECTED']['result']}
  Target levels sau = {by_label['QD-MN-CORRECTED']['target_levels_after']}
- Nhóm 627 đã COMPLETED:
  old sources = {qd_th_old_sources}
  target = {qd_th_target}
- Phần TH còn thiếu:
  1230 -> {qd_th_target}
  Simulation = {by_label['QD-TH-RESIDUAL']['result']}
  Target levels sau = {by_label['QD-TH-RESIDUAL']['target_levels_after']}
- READY_QUANG_DONG_CORRECTION = {'YES' if ready_quang_dong else 'NO'}

MƯỜNG QUÀNG:
- 1150 -> 1593
- Đây là official cross-level TH -> THCS.
- Simulation = {mq['result']}
- Target levels: {mq['target_levels_before']} -> {mq['target_levels_after']}
- Technical linked-school result = {'PASS' if mq_technical else 'FAIL'}

HỮU KHUÔNG:
- 1101 -> 1559
- Nguồn ghi rõ: "Liên cấp TH&THCS".
- Simulation = {hk['result']}
- Target levels: {hk['target_levels_before']} -> {hk['target_levels_after']}
- Technical linked-school result = {'PASS' if hk_technical else 'FAIL'}

KẾT LUẬN:
- Quang Đồng không phải một merger MN<-TH thật; đó là lỗi ranh giới parser.
- Mường Quàng + Hữu Khuông là hai trường hợp liên cấp TH+THCS thật.
- Mô phỏng kỹ thuật liên cấp = {'PASS' if cross_level_technical_pass else 'FAIL'}.
- Chưa chạy thật liên cấp ở V13.7.

V13_7_READY_FOR_NEXT_STEP = {'YES' if ready_quang_dong and cross_level_technical_pass else 'NO'}

Thời gian = {elapsed:.1f}s
"""

    (report_dir / "00_TONG_QUAN_V13_7.txt").write_text(
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
    print("HOÀN THÀNH V13.7")
    print("=" * 126)
    print(
        "Quang Đồng corrected MN: "
        f"{by_label['QD-MN-CORRECTED']['result']}"
    )
    print(
        "Quang Đồng TH residual: "
        f"{by_label['QD-TH-RESIDUAL']['result']}"
    )
    print(
        "Mường Quàng cross-level technical: "
        + ("PASS" if mq_technical else "FAIL")
    )
    print(
        "Hữu Khuông cross-level technical: "
        + ("PASS" if hk_technical else "FAIL")
    )
    print(
        "READY_QUANG_DONG_CORRECTION: "
        + ("YES" if ready_quang_dong else "NO")
    )
    print(
        "CROSS_LEVEL_TECHNICAL_SIMULATION: "
        + ("PASS" if cross_level_technical_pass else "FAIL")
    )
    print(
        "V13_7_READY_FOR_NEXT_STEP: "
        + (
            "YES"
            if ready_quang_dong and cross_level_technical_pass
            else "NO"
        )
    )
    print("Database thật: KHÔNG THAY ĐỔI")
    print("Plan JSON: KHÔNG THAY ĐỔI")
    print(f"ZIP: {zip_path}")

    return 0 if ready_quang_dong and cross_level_technical_pass else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print()
        print("=" * 126)
        print("V13.7 DỪNG AN TOÀN")
        print("=" * 126)
        print(repr(exc))
        print("Database thật: KHÔNG THAY ĐỔI")
        print("Plan JSON: KHÔNG THAY ĐỔI")
        raise SystemExit(2)
