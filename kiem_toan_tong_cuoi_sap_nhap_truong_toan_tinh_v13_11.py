# -*- coding: utf-8 -*-
r"""
V13.11 - KIỂM TOÁN TỔNG CUỐI SÁP NHẬP TRƯỜNG TOÀN TỈNH
=========================================================

ĐÂY LÀ BƯỚC ĐÓNG CUỐI CÙNG
--------------------------
Chỉ đọc, không sửa DB, không sửa Plan JSON, không chạy lại bất kỳ merger nào.

Các giai đoạn đã hoàn thành:
A. QĐ3805 Nghi Lộc:
   - 6 plan COMPLETED
   - 7 source school

B. V13.6:
   - 412 plan toàn tỉnh COMPLETED
   - 483 source school
   - hậu kiểm V13.6.1 đã PASS

C. V13.8 Quang Đồng:
   - 2 correction plan COMPLETED
   - 3 source school

D. V13.10 liên cấp:
   - 2 plan COMPLETED
   - Mường Quàng: 1150 -> 1593
   - Hữu Khuông: 1101 -> 1559
   - 2 source school
   - target CURRENT phải đồng thời TH + THCS

TỔNG:
- 422 plan COMPLETED
- 495 trường nguồn duy nhất

BACKUP DÙNG ĐỐI CHIẾU
----------------------
1. Trước V13.6:
C:\PhoCap\exports\backup_truoc_sap_nhap_toan_tinh_v13_6_20260904_161006

2. Trước V13.8:
C:\PhoCap\exports\backup_truoc_v13_8_quang_dong_20260904_190311

3. Trước V13.10:
C:\PhoCap\exports\backup_truoc_v13_10_lien_cap_20260904_191942

KIỂM TOÁN
---------
1. Registry:
   - QĐ3805 COMPLETED = 6
   - Province COMPLETED = 412
   - Quang Đồng correction COMPLETED = 2
   - Cross-level COMPLETED = 2
   - Tổng đúng 422 plan liên quan.

2. Mapping:
   - 495 source duy nhất.
   - Không source nào trùng target của một plan khác trong tập cuối,
     trừ khi mapping lịch sử đã được xử lý và không tạo chain mới.
   - Tất cả source hiện inactive.
   - Tất cả target hiện active.

3. Tài khoản:
   - Không còn CBQL/GV/NV tại 495 source.
   - 495 login truong_* của source vẫn gắn source và đều inactive.

4. CURRENT/FUTURE:
   - Không còn dòng nào tại 495 source ở mọi bảng có
     school_id + school_year_id.
   - Năm di chuyển phải đúng [2026-2027, 2027-2028] = ids [2,8].

5. PAST:
   - 412 plan: hash PAST tại source so với backup trước V13.6.
   - Quang Đồng: hash PAST tại 613,615,1230,614,1232
     so với backup trước V13.8.
   - Liên cấp: hash PAST tại 1150,1593,1101,1559
     so với backup trước V13.10.
   - PAST phải giữ nguyên tuyệt đối.

6. Tài khoản chuyển đích:
   - V13.6: từng CBQL/GV/NV trong backup phải ở đúng target hiện tại.
   - V13.8: từng CBQL/GV/NV trong backup phải ở đúng target hiện tại.
   - V13.10: nếu có CBQL/GV/NV thì phải ở đúng target hiện tại.

7. Liên cấp:
   - 1593 CURRENT có đúng TH + THCS.
   - 1559 CURRENT có đúng TH + THCS.
   - data_json TH hiện tại khớp baseline TH 2025-2026 của source.
   - data_json THCS hiện tại khớp baseline THCS 2025-2026 của target.

8. Audit operation:
   - batch V13.6 = 412
   - batch V13.8 = 2
   - batch V13.10 = 2

9. Database:
   - current integrity_check = ok
   - current foreign_key_check = 0
   - cả 3 backup integrity/FK đều PASS.

KẾT LUẬN:
FINAL_STATEWIDE_SCHOOL_MERGER_CLOSED=YES
chỉ khi toàn bộ gate PASS.

CHẠY
----
cd C:\PhoCap
.\.venv\Scripts\python.exe .\kiem_toan_tong_cuoi_sap_nhap_truong_toan_tinh_v13_11.py
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import sqlite3
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(r"C:\PhoCap")
DB_PATH = ROOT / "data" / "phocap.db"
PLAN_FILE = ROOT / "data" / "school_merger_approved_plans.json"

B6_DIR = (
    ROOT
    / "exports"
    / "backup_truoc_sap_nhap_toan_tinh_v13_6_20260904_161006"
)
B8_DIR = (
    ROOT
    / "exports"
    / "backup_truoc_v13_8_quang_dong_20260904_190311"
)
B10_DIR = (
    ROOT
    / "exports"
    / "backup_truoc_v13_10_lien_cap_20260904_191942"
)

B6_DB = B6_DIR / "phocap.db"
B8_DB = B8_DIR / "phocap.db"
B10_DB = B10_DIR / "phocap.db"

BATCH6 = "backup_truoc_sap_nhap_toan_tinh_v13_6_20260904_161006"
BATCH8 = "backup_truoc_v13_8_quang_dong_20260904_190311"
BATCH10 = "backup_truoc_v13_10_lien_cap_20260904_191942"

YEAR_ID = 2
YEAR_CODE = "2026-2027"
EXPECTED_MOVE_YEARS = [2, 8]

QD3805_EXPECTED = {
    749: 747,
    750: 748,
    751: 748,
    1181: 1178,
    1180: 1179,
    1608: 1605,
    1607: 1606,
}

QUANG_DONG_EXPECTED = {
    613: 614,
    615: 614,
    1230: 1232,
}

CROSS_LEVEL_EXPECTED = {
    1150: 1593,
    1101: 1559,
}

EXPECTED_TOTAL_PLANS = 422
EXPECTED_TOTAL_SOURCES = 495
EXPECTED_QD3805 = 6
EXPECTED_PROVINCE = 412
EXPECTED_QD_CORRECTIONS = 2
EXPECTED_CROSS_LEVEL = 2


def qident(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def markers(n: int) -> str:
    return ",".join("?" for _ in range(n))


def connect_ro(path: Path) -> sqlite3.Connection:
    uri = path.resolve().as_uri() + "?mode=ro"
    con = sqlite3.connect(uri, uri=True, timeout=90)
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
    for row in con.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type='table'
          AND name NOT LIKE 'sqlite_%'
        ORDER BY name
        """
    ).fetchall():
        table = str(row["name"])
        cols = set(table_columns(con, table))
        if {"school_id", "school_year_id"} <= cols:
            result.append(table)
    return result


def canonical(value: Any) -> Any:
    if isinstance(value, bytes):
        return {"__bytes__": value.hex()}
    return value


def hash_rows(
    con: sqlite3.Connection,
    table: str,
    school_ids: list[int],
    year_ids: list[int],
) -> tuple[int, str]:
    if not school_ids or not year_ids:
        return 0, hashlib.sha256(b"").hexdigest()

    cols = table_columns(con, table)
    lines = []
    chunk_size = 600

    for start in range(0, len(school_ids), chunk_size):
        chunk = school_ids[start:start + chunk_size]
        rows = con.execute(
            f"SELECT * FROM {qident(table)} "
            f"WHERE school_id IN ({markers(len(chunk))}) "
            f"AND school_year_id IN ({markers(len(year_ids))})",
            [*chunk, *year_ids],
        ).fetchall()

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

    return len(lines), h.hexdigest()


def past_compare(
    before: sqlite3.Connection,
    after: sqlite3.Connection,
    school_ids: list[int],
    past_ids: list[int],
    label: str,
) -> tuple[list[dict], int]:
    common = sorted(
        set(year_aware_tables(before))
        & set(year_aware_tables(after))
    )
    rows = []
    fail = 0

    for table in common:
        b_count, b_hash = hash_rows(
            before,
            table,
            school_ids,
            past_ids,
        )
        a_count, a_hash = hash_rows(
            after,
            table,
            school_ids,
            past_ids,
        )
        ok = (
            b_count == a_count
            and b_hash == a_hash
        )
        if not ok:
            fail += 1

        rows.append({
            "scope": label,
            "table": table,
            "before_count": b_count,
            "after_count": a_count,
            "before_hash": b_hash,
            "after_hash": a_hash,
            "result": "PASS" if ok else "FAIL",
        })

    return rows, fail


def year_scope(
    con: sqlite3.Connection,
) -> tuple[list[int], list[int]]:
    rows = con.execute(
        "SELECT id,code,name FROM school_years ORDER BY id"
    ).fetchall()

    starts = {}
    labels = {}

    for row in rows:
        text = str(row["code"] or row["name"] or "")
        m = re.search(r"(\d{4})\D+(\d{4})", text)
        if not m:
            raise RuntimeError(
                f"Không phân loại được năm học id={row['id']}: {text!r}"
            )
        starts[int(row["id"])] = int(m.group(1))
        labels[int(row["id"])] = text

    if labels.get(YEAR_ID) != YEAR_CODE:
        raise RuntimeError(
            f"year_id=2 không còn là {YEAR_CODE}: {labels.get(YEAR_ID)!r}"
        )

    selected = starts[YEAR_ID]
    move = sorted(
        yid for yid, start in starts.items()
        if start >= selected
    )
    past = sorted(
        yid for yid, start in starts.items()
        if start < selected
    )
    return move, past


def load_plans(path: Path = PLAN_FILE) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [
        p for p in payload.get("plans") or []
        if isinstance(p, dict)
    ]


def source_target_map(
    plans: list[dict],
) -> dict[int, int]:
    result = {}
    for p in plans:
        target = int(p.get("target_school_id") or 0)
        for value in p.get("source_school_ids") or []:
            sid = int(value)
            if sid in result and result[sid] != target:
                raise RuntimeError(
                    f"source_id={sid} có hai target khác nhau."
                )
            result[sid] = target
    return result


def registry_audit(
    plans: list[dict],
) -> tuple[dict[str, int], dict[int, int], list[dict]]:
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

    qd_corr = [
        p for p in plans
        if (
            str(p.get("id") or "").startswith("V13.8-QUANG-DONG-")
            and str(p.get("status") or "").upper() == "COMPLETED"
        )
    ]

    cross = [
        p for p in plans
        if (
            str(p.get("id") or "").startswith("V13.10-")
            and str(p.get("status") or "").upper() == "COMPLETED"
        )
    ]

    counts = {
        "qd3805": len(qd),
        "province": len(province),
        "quang_dong": len(qd_corr),
        "cross_level": len(cross),
        "total_relevant": (
            len(qd)
            + len(province)
            + len(qd_corr)
            + len(cross)
        ),
    }

    if counts != {
        "qd3805": 6,
        "province": 412,
        "quang_dong": 2,
        "cross_level": 2,
        "total_relevant": 422,
    }:
        raise RuntimeError(
            f"Registry final không đúng: {counts}"
        )

    qd_map = source_target_map(qd)
    if qd_map != QD3805_EXPECTED:
        raise RuntimeError(
            f"QĐ3805 mapping thay đổi: {qd_map}"
        )

    qd_corr_map = source_target_map(qd_corr)
    if qd_corr_map != QUANG_DONG_EXPECTED:
        raise RuntimeError(
            f"Quang Đồng mapping thay đổi: {qd_corr_map}"
        )

    cross_map = source_target_map(cross)
    if cross_map != CROSS_LEVEL_EXPECTED:
        raise RuntimeError(
            f"Cross-level mapping thay đổi: {cross_map}"
        )

    for p in cross:
        if p.get("cross_level_exception") is not True:
            raise RuntimeError(
                f"{p.get('id')} thiếu cross_level_exception=true."
            )
        levels = {
            str(x).upper()
            for x in p.get("resulting_levels") or []
        }
        if levels != {"TH", "THCS"}:
            raise RuntimeError(
                f"{p.get('id')} resulting_levels={levels}."
            )

    province_map = source_target_map(province)

    all_map = {}
    for name, mapping in (
        ("QĐ3805", qd_map),
        ("Province", province_map),
        ("Quang Đồng", qd_corr_map),
        ("Cross-level", cross_map),
    ):
        for sid, tid in mapping.items():
            if sid in all_map and all_map[sid] != tid:
                raise RuntimeError(
                    f"source {sid} trùng khác target giữa các scope."
                )
            all_map[sid] = tid

    if len(all_map) != EXPECTED_TOTAL_SOURCES:
        raise RuntimeError(
            f"Tổng source duy nhất={len(all_map)}, cần 495."
        )

    rows = []
    for scope, subset in (
        ("QD3805", qd),
        ("PROVINCE_412", province),
        ("QUANG_DONG_V13_8", qd_corr),
        ("CROSS_LEVEL_V13_10", cross),
    ):
        for p in subset:
            rows.append({
                "scope": scope,
                "plan_id": p.get("id"),
                "status": p.get("status"),
                "commune_id": p.get("commune_id"),
                "level_code": p.get("level_code"),
                "source_school_ids": ",".join(
                    str(x)
                    for x in p.get("source_school_ids") or []
                ),
                "target_school_id": p.get("target_school_id"),
                "document_code": p.get("document_code"),
            })

    return counts, all_map, rows


def school_state_audit(
    con: sqlite3.Connection,
    mapping: dict[int, int],
) -> tuple[list[dict], int, int]:
    source_ids = sorted(mapping)
    target_ids = sorted(set(mapping.values()))

    all_ids = sorted(set(source_ids) | set(target_ids))
    by_id = {}

    for start in range(0, len(all_ids), 700):
        chunk = all_ids[start:start + 700]
        for row in con.execute(
            f"""
            SELECT id,code,name,commune_id,is_active
            FROM schools
            WHERE id IN ({markers(len(chunk))})
            """,
            chunk,
        ).fetchall():
            by_id[int(row["id"])] = dict(row)

    rows = []
    source_fail = 0

    for sid in source_ids:
        s = by_id.get(sid)
        t = by_id.get(mapping[sid])

        ok = (
            s is not None
            and t is not None
            and int(s["is_active"] or 0) == 0
            and int(t["is_active"] or 0) == 1
        )
        if not ok:
            source_fail += 1

        rows.append({
            "source_school_id": sid,
            "source_code": s["code"] if s else "",
            "source_name": s["name"] if s else "",
            "source_is_active": (
                int(s["is_active"] or 0)
                if s else ""
            ),
            "target_school_id": mapping[sid],
            "target_code": t["code"] if t else "",
            "target_name": t["name"] if t else "",
            "target_is_active": (
                int(t["is_active"] or 0)
                if t else ""
            ),
            "result": "PASS" if ok else "FAIL",
        })

    target_inactive = sum(
        1
        for tid in target_ids
        if (
            tid not in by_id
            or int(by_id[tid]["is_active"] or 0) != 1
        )
    )

    return rows, source_fail, target_inactive


def user_current_policy(
    con: sqlite3.Connection,
    source_ids: list[int],
) -> tuple[int, int, int]:
    regular = 0
    logins = 0
    active_logins = 0

    for start in range(0, len(source_ids), 700):
        chunk = source_ids[start:start + 700]

        regular += int(
            con.execute(
                f"""
                SELECT COUNT(*)
                FROM users
                WHERE school_id IN ({markers(len(chunk))})
                  AND username NOT LIKE 'truong_%'
                """,
                chunk,
            ).fetchone()[0]
            or 0
        )

        logins += int(
            con.execute(
                f"""
                SELECT COUNT(*)
                FROM users
                WHERE school_id IN ({markers(len(chunk))})
                  AND username LIKE 'truong_%'
                """,
                chunk,
            ).fetchone()[0]
            or 0
        )

        active_logins += int(
            con.execute(
                f"""
                SELECT COUNT(*)
                FROM users
                WHERE school_id IN ({markers(len(chunk))})
                  AND username LIKE 'truong_%'
                  AND is_active=1
                """,
                chunk,
            ).fetchone()[0]
            or 0
        )

    return regular, logins, active_logins


def user_transition_audit(
    before: sqlite3.Connection,
    after: sqlite3.Connection,
    mapping: dict[int, int],
    label: str,
) -> tuple[list[dict], int]:
    source_ids = sorted(mapping)
    rows_out = []
    fail = 0

    for start in range(0, len(source_ids), 600):
        chunk = source_ids[start:start + 600]
        old_rows = before.execute(
            f"""
            SELECT id,username,school_id,is_active
            FROM users
            WHERE school_id IN ({markers(len(chunk))})
              AND username NOT LIKE 'truong_%'
            """,
            chunk,
        ).fetchall()

        user_ids = [
            int(r["id"])
            for r in old_rows
        ]
        current = {}

        for j in range(0, len(user_ids), 700):
            id_chunk = user_ids[j:j + 700]
            if not id_chunk:
                continue
            for row in after.execute(
                f"""
                SELECT id,username,school_id,is_active
                FROM users
                WHERE id IN ({markers(len(id_chunk))})
                """,
                id_chunk,
            ).fetchall():
                current[int(row["id"])] = row

        for old in old_rows:
            uid = int(old["id"])
            source = int(old["school_id"])
            expected = mapping[source]
            now = current.get(uid)

            ok = (
                now is not None
                and int(now["school_id"] or 0) == expected
            )
            if not ok:
                fail += 1

            rows_out.append({
                "scope": label,
                "user_id": uid,
                "username": old["username"],
                "source_school_id": source,
                "expected_target_school_id": expected,
                "current_school_id": (
                    int(now["school_id"])
                    if now and now["school_id"] is not None
                    else ""
                ),
                "result": "PASS" if ok else "FAIL",
            })

    return rows_out, fail


def current_future_residual(
    con: sqlite3.Connection,
    source_ids: list[int],
    move_year_ids: list[int],
) -> tuple[list[dict], int]:
    rows = []
    total = 0

    for table in year_aware_tables(con):
        n = 0
        for start in range(0, len(source_ids), 600):
            chunk = source_ids[start:start + 600]
            n += int(
                con.execute(
                    f"""
                    SELECT COUNT(*)
                    FROM {qident(table)}
                    WHERE school_id IN ({markers(len(chunk))})
                      AND school_year_id IN ({markers(len(move_year_ids))})
                    """,
                    [*chunk, *move_year_ids],
                ).fetchone()[0]
                or 0
            )

        total += n
        rows.append({
            "table": table,
            "current_future_residual": n,
            "result": "PASS" if n == 0 else "FAIL",
        })

    return rows, total


def operations_count(
    con: sqlite3.Connection,
    backup_name: str,
) -> int:
    return int(
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


def network_baseline_audit(
    before: sqlite3.Connection,
    after: sqlite3.Connection,
) -> tuple[list[dict], int]:
    rows = []
    fail = 0

    cases = [
        {
            "label": "MUONG_QUANG",
            "source": 1150,
            "target": 1593,
        },
        {
            "label": "HUU_KHUONG",
            "source": 1101,
            "target": 1559,
        },
    ]

    for case in cases:
        source_th = before.execute(
            """
            SELECT data_json
            FROM school_network_year_data
            WHERE school_id=? AND school_year_id=1
              AND UPPER(TRIM(level_code))='TH'
            """,
            (case["source"],),
        ).fetchall()

        target_thcs = before.execute(
            """
            SELECT data_json
            FROM school_network_year_data
            WHERE school_id=? AND school_year_id=1
              AND UPPER(TRIM(level_code))='THCS'
            """,
            (case["target"],),
        ).fetchall()

        current = after.execute(
            """
            SELECT level_code,data_json,source_name
            FROM school_network_year_data
            WHERE school_id=? AND school_year_id=2
            ORDER BY level_code
            """,
            (case["target"],),
        ).fetchall()

        current_map = {
            str(r["level_code"]).upper(): r
            for r in current
        }

        levels = set(current_map)

        ok = (
            len(source_th) == 1
            and len(target_thcs) == 1
            and levels == {"TH", "THCS"}
            and current_map["TH"]["data_json"]
            == source_th[0]["data_json"]
            and current_map["THCS"]["data_json"]
            == target_thcs[0]["data_json"]
            and str(current_map["TH"]["source_name"] or "")
            .startswith("V13.10-LIENCAP-")
            and str(current_map["THCS"]["source_name"] or "")
            .startswith("V13.10-LIENCAP-")
        )

        if not ok:
            fail += 1

        rows.append({
            "case": case["label"],
            "source_school_id": case["source"],
            "target_school_id": case["target"],
            "current_levels": ",".join(sorted(levels)),
            "th_matches_source_2025_2026": (
                len(source_th) == 1
                and "TH" in current_map
                and current_map["TH"]["data_json"]
                == source_th[0]["data_json"]
            ),
            "thcs_matches_target_2025_2026": (
                len(target_thcs) == 1
                and "THCS" in current_map
                and current_map["THCS"]["data_json"]
                == target_thcs[0]["data_json"]
            ),
            "th_source_name": (
                current_map["TH"]["source_name"]
                if "TH" in current_map
                else ""
            ),
            "thcs_source_name": (
                current_map["THCS"]["source_name"]
                if "THCS" in current_map
                else ""
            ),
            "result": "PASS" if ok else "FAIL",
        })

    return rows, fail


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
    print("=" * 126)
    print("V13.11 - KIỂM TOÁN TỔNG CUỐI SÁP NHẬP TRƯỜNG TOÀN TỈNH")
    print("=" * 126)
    print("CHỈ ĐỌC - KHÔNG SỬA DATABASE / PLAN JSON")

    required = [
        DB_PATH,
        PLAN_FILE,
        B6_DB,
        B8_DB,
        B10_DB,
    ]
    for path in required:
        if not path.exists():
            raise RuntimeError(
                f"Không tìm thấy tệp bắt buộc: {path}"
            )

    plans = load_plans()
    counts, all_map, plan_rows = registry_audit(plans)

    province_plans = [
        p for p in plans
        if (
            str(p.get("document_code") or "")
            == "NGUON-SAP-NHAP-TOAN-TINH"
            and str(p.get("status") or "").upper()
            == "COMPLETED"
        )
    ]
    province_map = source_target_map(province_plans)

    source_ids = sorted(all_map)

    with (
        connect_ro(DB_PATH) as current,
        connect_ro(B6_DB) as b6,
        connect_ro(B8_DB) as b8,
        connect_ro(B10_DB) as b10,
    ):
        current_health = db_health(current)
        b6_health = db_health(b6)
        b8_health = db_health(b8)
        b10_health = db_health(b10)

        for label, health in (
            ("CURRENT", current_health),
            ("B6", b6_health),
            ("B8", b8_health),
            ("B10", b10_health),
        ):
            if health[0].lower() != "ok" or health[1] != 0:
                raise RuntimeError(
                    f"{label} DB lỗi: integrity={health[0]}, FK={health[1]}"
                )

        move_ids, past_ids = year_scope(current)
        if move_ids != EXPECTED_MOVE_YEARS:
            raise RuntimeError(
                f"CURRENT+FUTURE ids={move_ids}, cần [2,8]."
            )

        school_rows, school_fail, target_inactive = (
            school_state_audit(
                current,
                all_map,
            )
        )

        regular_at_source, source_login_count, active_source_logins = (
            user_current_policy(
                current,
                source_ids,
            )
        )

        if source_login_count != EXPECTED_TOTAL_SOURCES:
            raise RuntimeError(
                f"Login truong_* tại 495 source={source_login_count}, "
                f"cần {EXPECTED_TOTAL_SOURCES}."
            )

        residual_rows, residual_total = current_future_residual(
            current,
            source_ids,
            move_ids,
        )

        # PAST audit - 412 source against B6.
        past6_rows, past6_fail = past_compare(
            b6,
            current,
            sorted(province_map),
            past_ids,
            "PROVINCE_412",
        )

        # PAST audit - Quang Đồng involved against B8.
        past8_rows, past8_fail = past_compare(
            b8,
            current,
            [613, 614, 615, 1230, 1232],
            past_ids,
            "QUANG_DONG_V13_8",
        )

        # PAST audit - linked involved against B10.
        past10_rows, past10_fail = past_compare(
            b10,
            current,
            [1150, 1593, 1101, 1559],
            past_ids,
            "CROSS_LEVEL_V13_10",
        )

        # User exact target transitions.
        u6_rows, u6_fail = user_transition_audit(
            b6,
            current,
            province_map,
            "PROVINCE_412",
        )
        u8_rows, u8_fail = user_transition_audit(
            b8,
            current,
            QUANG_DONG_EXPECTED,
            "QUANG_DONG_V13_8",
        )
        u10_rows, u10_fail = user_transition_audit(
            b10,
            current,
            CROSS_LEVEL_EXPECTED,
            "CROSS_LEVEL_V13_10",
        )

        linked_rows, linked_fail = network_baseline_audit(
            b10,
            current,
        )

        op6 = operations_count(current, BATCH6)
        op8 = operations_count(current, BATCH8)
        op10 = operations_count(current, BATCH10)

    all_pass = (
        counts["total_relevant"] == EXPECTED_TOTAL_PLANS
        and len(all_map) == EXPECTED_TOTAL_SOURCES
        and school_fail == 0
        and target_inactive == 0
        and regular_at_source == 0
        and source_login_count == EXPECTED_TOTAL_SOURCES
        and active_source_logins == 0
        and residual_total == 0
        and past6_fail == 0
        and past8_fail == 0
        and past10_fail == 0
        and u6_fail == 0
        and u8_fail == 0
        and u10_fail == 0
        and linked_fail == 0
        and op6 == 412
        and op8 == 2
        and op10 == 2
        and current_health == ("ok", 0)
        and b6_health == ("ok", 0)
        and b8_health == ("ok", 0)
        and b10_health == ("ok", 0)
    )

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_dir = (
        ROOT
        / f"bao_cao_v13_11_kiem_toan_tong_cuoi_{stamp}"
    )
    zip_path = (
        ROOT
        / f"bao_cao_v13_11_kiem_toan_tong_cuoi_{stamp}.zip"
    )
    report_dir.mkdir(
        parents=True,
        exist_ok=False,
    )

    write_csv(
        report_dir / "800_REGISTRY_FINAL.csv",
        [
            "scope",
            "plan_id",
            "status",
            "commune_id",
            "level_code",
            "source_school_ids",
            "target_school_id",
            "document_code",
        ],
        plan_rows,
    )

    write_csv(
        report_dir / "801_SCHOOL_STATE_FINAL.csv",
        [
            "source_school_id",
            "source_code",
            "source_name",
            "source_is_active",
            "target_school_id",
            "target_code",
            "target_name",
            "target_is_active",
            "result",
        ],
        school_rows,
    )

    write_csv(
        report_dir / "802_CURRENT_FUTURE_RESIDUAL.csv",
        [
            "table",
            "current_future_residual",
            "result",
        ],
        residual_rows,
    )

    write_csv(
        report_dir / "803_PAST_HASH_AUDIT.csv",
        [
            "scope",
            "table",
            "before_count",
            "after_count",
            "before_hash",
            "after_hash",
            "result",
        ],
        [
            *past6_rows,
            *past8_rows,
            *past10_rows,
        ],
    )

    write_csv(
        report_dir / "804_USER_TARGET_AUDIT.csv",
        [
            "scope",
            "user_id",
            "username",
            "source_school_id",
            "expected_target_school_id",
            "current_school_id",
            "result",
        ],
        [
            *u6_rows,
            *u8_rows,
            *u10_rows,
        ],
    )

    write_csv(
        report_dir / "805_LINKED_SCHOOL_NETWORK_AUDIT.csv",
        [
            "case",
            "source_school_id",
            "target_school_id",
            "current_levels",
            "th_matches_source_2025_2026",
            "thcs_matches_target_2025_2026",
            "th_source_name",
            "thcs_source_name",
            "result",
        ],
        linked_rows,
    )

    gate_rows = [
        {
            "check": "completed_plan_total",
            "result": (
                "PASS"
                if counts["total_relevant"] == EXPECTED_TOTAL_PLANS
                else "FAIL"
            ),
            "detail": str(counts["total_relevant"]),
        },
        {
            "check": "qd3805_completed",
            "result": "PASS",
            "detail": str(counts["qd3805"]),
        },
        {
            "check": "province_completed",
            "result": "PASS",
            "detail": str(counts["province"]),
        },
        {
            "check": "quang_dong_completed",
            "result": "PASS",
            "detail": str(counts["quang_dong"]),
        },
        {
            "check": "cross_level_completed",
            "result": "PASS",
            "detail": str(counts["cross_level"]),
        },
        {
            "check": "unique_source_schools",
            "result": (
                "PASS"
                if len(all_map) == EXPECTED_TOTAL_SOURCES
                else "FAIL"
            ),
            "detail": str(len(all_map)),
        },
        {
            "check": "source_school_state",
            "result": "PASS" if school_fail == 0 else "FAIL",
            "detail": f"fail={school_fail}/495",
        },
        {
            "check": "target_school_active",
            "result": "PASS" if target_inactive == 0 else "FAIL",
            "detail": str(target_inactive),
        },
        {
            "check": "regular_users_at_source",
            "result": "PASS" if regular_at_source == 0 else "FAIL",
            "detail": str(regular_at_source),
        },
        {
            "check": "source_school_login_count",
            "result": (
                "PASS"
                if source_login_count == EXPECTED_TOTAL_SOURCES
                else "FAIL"
            ),
            "detail": str(source_login_count),
        },
        {
            "check": "active_source_school_logins",
            "result": "PASS" if active_source_logins == 0 else "FAIL",
            "detail": str(active_source_logins),
        },
        {
            "check": "current_future_source_residual",
            "result": "PASS" if residual_total == 0 else "FAIL",
            "detail": str(residual_total),
        },
        {
            "check": "past_province_412",
            "result": "PASS" if past6_fail == 0 else "FAIL",
            "detail": str(past6_fail),
        },
        {
            "check": "past_quang_dong",
            "result": "PASS" if past8_fail == 0 else "FAIL",
            "detail": str(past8_fail),
        },
        {
            "check": "past_cross_level",
            "result": "PASS" if past10_fail == 0 else "FAIL",
            "detail": str(past10_fail),
        },
        {
            "check": "user_targets_province_412",
            "result": "PASS" if u6_fail == 0 else "FAIL",
            "detail": f"fail={u6_fail}/{len(u6_rows)}",
        },
        {
            "check": "user_targets_quang_dong",
            "result": "PASS" if u8_fail == 0 else "FAIL",
            "detail": f"fail={u8_fail}/{len(u8_rows)}",
        },
        {
            "check": "user_targets_cross_level",
            "result": "PASS" if u10_fail == 0 else "FAIL",
            "detail": f"fail={u10_fail}/{len(u10_rows)}",
        },
        {
            "check": "linked_network_baseline",
            "result": "PASS" if linked_fail == 0 else "FAIL",
            "detail": f"fail={linked_fail}/2",
        },
        {
            "check": "operation_batch_v13_6",
            "result": "PASS" if op6 == 412 else "FAIL",
            "detail": str(op6),
        },
        {
            "check": "operation_batch_v13_8",
            "result": "PASS" if op8 == 2 else "FAIL",
            "detail": str(op8),
        },
        {
            "check": "operation_batch_v13_10",
            "result": "PASS" if op10 == 2 else "FAIL",
            "detail": str(op10),
        },
        {
            "check": "current_db_integrity",
            "result": (
                "PASS"
                if current_health[0].lower() == "ok"
                else "FAIL"
            ),
            "detail": current_health[0],
        },
        {
            "check": "current_db_fk",
            "result": "PASS" if current_health[1] == 0 else "FAIL",
            "detail": str(current_health[1]),
        },
        {
            "check": "backup_v13_6_health",
            "result": (
                "PASS"
                if b6_health == ("ok", 0)
                else "FAIL"
            ),
            "detail": repr(b6_health),
        },
        {
            "check": "backup_v13_8_health",
            "result": (
                "PASS"
                if b8_health == ("ok", 0)
                else "FAIL"
            ),
            "detail": repr(b8_health),
        },
        {
            "check": "backup_v13_10_health",
            "result": (
                "PASS"
                if b10_health == ("ok", 0)
                else "FAIL"
            ),
            "detail": repr(b10_health),
        },
        {
            "check": "FINAL_STATEWIDE_SCHOOL_MERGER_CLOSED",
            "result": "YES" if all_pass else "NO",
            "detail": (
                "Toàn bộ sáp nhập trường đã hậu kiểm và đóng."
                if all_pass
                else "Có gate FAIL; xem báo cáo trước khi kết luận."
            ),
        },
    ]

    write_csv(
        report_dir / "806_GATE_V13_11.csv",
        ["check", "result", "detail"],
        gate_rows,
    )

    summary = f"""V13.11 - KIỂM TOÁN TỔNG CUỐI SÁP NHẬP TRƯỜNG TOÀN TỈNH
================================================================================

STATUS={'PASS' if all_pass else 'REVIEW'}

REGISTRY
- QĐ3805 COMPLETED = {counts['qd3805']}
- Province COMPLETED = {counts['province']}
- Quang Đồng V13.8 COMPLETED = {counts['quang_dong']}
- Cross-level V13.10 COMPLETED = {counts['cross_level']}
- Tổng plan COMPLETED liên quan = {counts['total_relevant']}

SCHOOL
- Tổng source school duy nhất = {len(all_map)}
- Source state fail = {school_fail}
- Target inactive = {target_inactive}

ACCOUNT
- CBQL/GV/NV còn tại source = {regular_at_source}
- Login trường nguồn = {source_login_count}
- Login trường nguồn active = {active_source_logins}

YEAR SCOPE
- CURRENT+FUTURE ids = {move_ids}
- PAST ids = {past_ids}
- CURRENT/FUTURE residual tại source = {residual_total}

PAST HASH
- Province 412 fail tables = {past6_fail}
- Quang Đồng fail tables = {past8_fail}
- Cross-level fail tables = {past10_fail}

USER TARGET
- Province 412 fail = {u6_fail}/{len(u6_rows)}
- Quang Đồng fail = {u8_fail}/{len(u8_rows)}
- Cross-level fail = {u10_fail}/{len(u10_rows)}

LINKED SCHOOL NETWORK
- Fail = {linked_fail}/2
- Mường Quàng target 1593 = TH + THCS
- Hữu Khuông target 1559 = TH + THCS

AUDIT OPERATIONS
- V13.6 batch = {op6}
- V13.8 batch = {op8}
- V13.10 batch = {op10}

DATABASE
- Current integrity = {current_health[0]}
- Current FK = {current_health[1]}
- Backup V13.6 = {b6_health}
- Backup V13.8 = {b8_health}
- Backup V13.10 = {b10_health}

FINAL_STATEWIDE_SCHOOL_MERGER_CLOSED={'YES' if all_pass else 'NO'}

Database: KHÔNG THAY ĐỔI.
Plan JSON: KHÔNG THAY ĐỔI.
"""

    (
        report_dir / "00_TONG_QUAN_V13_11.txt"
    ).write_text(
        summary,
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
    print("HOÀN THÀNH V13.11")
    print("=" * 126)
    print(f"Completed plans: {counts['total_relevant']}/422")
    print(f"Unique source schools: {len(all_map)}/495")
    print(f"Source state fail: {school_fail}")
    print(f"Target inactive: {target_inactive}")
    print(f"CBQL/GV/NV còn tại source: {regular_at_source}")
    print(f"Source school logins: {source_login_count}/495")
    print(f"Active source school logins: {active_source_logins}")
    print(f"CURRENT/FUTURE residual: {residual_total}")
    print(
        "PAST fail tables: "
        f"province={past6_fail}, "
        f"quang_dong={past8_fail}, "
        f"cross_level={past10_fail}"
    )
    print(
        "User target fail: "
        f"province={u6_fail}, "
        f"quang_dong={u8_fail}, "
        f"cross_level={u10_fail}"
    )
    print(f"Linked network fail: {linked_fail}")
    print(
        "Audit operations: "
        f"V13.6={op6}, V13.8={op8}, V13.10={op10}"
    )
    print(f"DB integrity: {current_health[0]}")
    print(f"DB FK errors: {current_health[1]}")
    print(
        "FINAL_STATEWIDE_SCHOOL_MERGER_CLOSED: "
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
        print("V13.11 DỪNG AN TOÀN")
        print("=" * 126)
        print(repr(exc))
        print("Database: KHÔNG THAY ĐỔI")
        print("Plan JSON: KHÔNG THAY ĐỔI")
        raise SystemExit(2)
