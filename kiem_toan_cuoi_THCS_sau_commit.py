# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
import unicodedata
from collections import Counter
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(r"C:\PhoCap")

DB = ROOT / "data" / "phocap.db"
SERVICE = ROOT / "app" / "services" / "school_merger_level_batch_service.py"
ENGINE = ROOT / "app" / "services" / "school_merger_service.py"
ROSTER = ROOT / "data" / "school_merger_source_rosters" / "THCS_2025_2026.json"
RESOLUTION = ROOT / "data" / "school_merger_registry" / "qd3805_thcs_resolution.json"
HISTORY = ROOT / "data" / "school_merger_approved_plans.json"

EXPECTED_DB_AFTER = (
    "c6a0f2f1a08e7e80a6e89cd0edfd83961f4d87930d5b8b1f3cdae8e770f4deee"
)

EXPECTED_DB_BEFORE = (
    "882e4925fd3e39d7e097ce127612c093852075e608d3f937294135282afec75a"
)

EXPECTED_HASHES = {
    "service":
        "9104fb99c78755e9eec86d090659b3a922834ff097d7292aa4d4b29e360a27f9",
    "engine":
        "414fb49a4c5f4fed7b571cc55df381678fe660cd8a675ecaa2f6fd70ebd7827a",
    "roster":
        "926528e0ae600a6b950b459c6f8ec5c6810e69d49158d1ff3c9a3d76c0bca657",
    "resolution":
        "d9d347b19de0795553c8f047cb91a430ded63d9232ac7eda7ea069b716c2c0f4",
    "history":
        "4e2c5f044c48c57dda40fecc11f4e9f466f236aacc082f224536b1685cadb1fc",
}

BACKUP_NAME = (
    "backup_truoc_sap_nhap_toan_cap_20260911_024023_315667_THCS"
)

YEAR_ID = 2
MOVE_YEAR_IDS = [2, 8]
PAST_YEAR_IDS = [1, 3, 4, 5, 6, 7]

SOURCE_IDS = [
    1432, 1425, 1428,
    1436, 1438,
    1435,
    1452,
    1451,
    1446, 1448,
    1447,
    1405,
    1458,
    1442,
    1440,
]

TARGET_EXPECTED = {
    1430: {
        "name": "THCS Cửa Nam",
        "total": 83,
        "CBQL": 3,
        "GIAO_VIEN": 73,
        "NHAN_VIEN": 7,
    },
    1427: {
        "name": "THCS Lê Lợi",
        "total": 90,
        "CBQL": 5,
        "GIAO_VIEN": 79,
        "NHAN_VIEN": 6,
    },
    1429: {
        "name": "THCS Lê Mao",
        "total": 114,
        "CBQL": 3,
        "GIAO_VIEN": 105,
        "NHAN_VIEN": 6,
    },
    1434: {
        "name": "THCS Bến Thuỷ",
        "total": 116,
        "CBQL": 6,
        "GIAO_VIEN": 101,
        "NHAN_VIEN": 9,
    },
    1437: {
        "name": "THCS VINH TÂN",
        "total": 125,
        "CBQL": 4,
        "GIAO_VIEN": 115,
        "NHAN_VIEN": 6,
    },
    1449: {
        "name": "THCS Hà Huy Tập",
        "total": 133,
        "CBQL": 4,
        "GIAO_VIEN": 121,
        "NHAN_VIEN": 8,
    },
    1450: {
        "name": "THCS Nghi Phú",
        "total": 97,
        "CBQL": 3,
        "GIAO_VIEN": 87,
        "NHAN_VIEN": 7,
    },
    1445: {
        "name": "THCS Nghi Xuân",
        "total": 112,
        "CBQL": 6,
        "GIAO_VIEN": 93,
        "NHAN_VIEN": 13,
    },
    1444: {
        "name": "THCS Hưng Lộc",
        "total": 90,
        "CBQL": 4,
        "GIAO_VIEN": 80,
        "NHAN_VIEN": 6,
    },
    1406: {
        "name": "THCS Nghi Thủy",
        "total": 70,
        "CBQL": 4,
        "GIAO_VIEN": 60,
        "NHAN_VIEN": 6,
    },
    1457: {
        "name": "THCS Thạch Thị",
        "total": 52,
        "CBQL": 4,
        "GIAO_VIEN": 44,
        "NHAN_VIEN": 4,
    },
    1441: {
        "name": "THCS Nghi Kim",
        "total": 86,
        "CBQL": 4,
        "GIAO_VIEN": 70,
        "NHAN_VIEN": 12,
    },
    1443: {
        "name": "THCS Quán Bàu",
        "total": 125,
        "CBQL": 5,
        "GIAO_VIEN": 112,
        "NHAN_VIEN": 8,
    },
}

EXPECTED_PLAN_IDS = {
    "PA2026-11781F068A55",
    "PA2026-1B5A34D3C68D",
    "PA2026-1DF7D2567825",
    "PA2026-3E857A509786",
    "PA2026-440298C0FCC6",
    "PA2026-4C15EEC22C47",
    "PA2026-5766BDC4F12D",
    "PA2026-5DD3FA2B0840",
    "PA2026-5F0387B33D01",
    "PA2026-853BD99FB835",
    "PA2026-98A8AEFB7088",
    "PA2026-EA5959CE3A8C",
    "PA2026-F4E971245B82",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def qident(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def marks(n: int) -> str:
    return ",".join("?" for _ in range(n))


def ro(path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(
        path.resolve().as_uri() + "?mode=ro",
        uri=True,
        timeout=120,
    )
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA query_only=ON")
    return con


def canon(value) -> str:
    text = str(value or "").strip().upper().replace("Đ", "D")
    text = unicodedata.normalize("NFD", text)
    text = "".join(
        c for c in text
        if unicodedata.category(c) != "Mn"
    )
    text = (
        text.replace(" ", "_")
        .replace("-", "_")
        .replace("/", "_")
    )

    if text in {"CBQL", "CAN_BO_QUAN_LY", "QUAN_LY"}:
        return "CBQL"

    if text in {"GV", "GIAO_VIEN", "GIAOVIEN"}:
        return "GIAO_VIEN"

    if text in {"NV", "NHAN_VIEN", "NHANVIEN"}:
        return "NHAN_VIEN"

    return text or "KHAC"


def year_tables(con):
    result = []

    for row in con.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type='table'
          AND name NOT LIKE 'sqlite_%'
        ORDER BY name
        """
    ):
        table = str(row["name"])

        cols = {
            str(x["name"])
            for x in con.execute(
                f"PRAGMA table_info({qident(table)})"
            )
        }

        if {"school_id", "school_year_id"}.issubset(cols):
            result.append(table)

    return result


def residual(con, source_ids, year_ids):
    bad = {}

    for table in year_tables(con):
        n = int(
            con.execute(
                f"""
                SELECT COUNT(*)
                FROM {qident(table)}
                WHERE school_id IN ({marks(len(source_ids))})
                  AND school_year_id IN ({marks(len(year_ids))})
                """,
                [*source_ids, *year_ids],
            ).fetchone()[0]
            or 0
        )

        if n:
            bad[table] = n

    return bad


def staff_state(con, school_id):
    rows = con.execute(
        """
        SELECT staff_member_id, position_group
        FROM staff_year_records
        WHERE school_id=?
          AND school_year_id=?
          AND is_active=1
        """,
        (school_id, YEAR_ID),
    ).fetchall()

    groups = Counter(
        canon(x["position_group"])
        for x in rows
    )

    distinct = {
        int(x["staff_member_id"])
        for x in rows
        if x["staff_member_id"] is not None
    }

    duplicate = con.execute(
        """
        SELECT staff_member_id, COUNT(*) AS n
        FROM staff_year_records
        WHERE school_id=?
          AND school_year_id=?
          AND is_active=1
          AND staff_member_id IS NOT NULL
        GROUP BY staff_member_id
        HAVING COUNT(*) > 1
        """,
        (school_id, YEAR_ID),
    ).fetchall()

    return {
        "total": len(rows),
        "distinct": len(distinct),
        "CBQL": int(groups.get("CBQL", 0)),
        "GIAO_VIEN": int(groups.get("GIAO_VIEN", 0)),
        "NHAN_VIEN": int(groups.get("NHAN_VIEN", 0)),
        "duplicates": [
            {
                "staff_member_id": int(x["staff_member_id"]),
                "rows": int(x["n"]),
            }
            for x in duplicate
        ],
    }


def encode(v):
    if isinstance(v, bytes):
        return {"__bytes__": v.hex()}
    return v


def past_snapshot(con, school_ids):
    payload = {}

    for table in year_tables(con):
        info = con.execute(
            f"PRAGMA table_info({qident(table)})"
        ).fetchall()

        columns = [
            str(x["name"])
            for x in info
        ]

        rows = con.execute(
            f"""
            SELECT *
            FROM {qident(table)}
            WHERE school_id IN ({marks(len(school_ids))})
              AND school_year_id IN ({marks(len(PAST_YEAR_IDS))})
            """,
            [*school_ids, *PAST_YEAR_IDS],
        ).fetchall()

        normalized = []

        for row in rows:
            normalized.append(
                [encode(row[c]) for c in columns]
            )

        normalized.sort(
            key=lambda x: json.dumps(
                x,
                ensure_ascii=False,
                sort_keys=True,
                default=str,
            )
        )

        payload[table] = {
            "columns": columns,
            "rows": normalized,
        }

    raw = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")

    return hashlib.sha256(raw).hexdigest()


def find_backup_db():
    candidates = []

    bases = [
        ROOT / "backups",
        ROOT / "exports",
        ROOT / "data",
    ]

    for base in bases:
        if not base.exists():
            continue

        for p in base.rglob("*"):
            if not p.is_file():
                continue

            if BACKUP_NAME.lower() not in str(p).lower():
                continue

            try:
                if sha256(p) == EXPECTED_DB_BEFORE:
                    candidates.append(p)
            except Exception:
                pass

    if len(candidates) == 1:
        return candidates[0]

    if len(candidates) > 1:
        print("BACKUP MATCHES:")
        for p in candidates:
            print(" -", p)
        raise RuntimeError(
            "DUNG: tim thay nhieu hon 1 backup DB cung SHA."
        )

    return None


print("=" * 148)
print("KIEM TOAN CUOI SAU SAP NHAP CHINH THUC THCS")
print("CHI DOC - KHONG SUA DATABASE - KHONG CHAY SAP NHAP")
print("=" * 148)

print()
print("1. HASH GATE")
print("-" * 148)

db_sha = sha256(DB)

print("db         =", db_sha)

if db_sha != EXPECTED_DB_AFTER:
    raise RuntimeError(
        "DUNG: DB khong dung snapshot ngay sau batch THCS."
    )

for label, path in {
    "service": SERVICE,
    "engine": ENGINE,
    "roster": ROSTER,
    "resolution": RESOLUTION,
    "history": HISTORY,
}.items():

    value = sha256(path)

    print(f"{label:10s} = {value}")

    if value != EXPECTED_HASHES[label]:
        raise RuntimeError(
            f"DUNG: {label} da thay doi."
        )


print()
print("2. DATABASE HEALTH")
print("-" * 148)

con = ro(DB)

try:
    integrity = str(
        con.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]
    )

    fk = con.execute(
        "PRAGMA foreign_key_check"
    ).fetchall()

    print("integrity =", integrity)
    print("FK        =", len(fk))

    if integrity.lower() != "ok" or fk:
        raise RuntimeError(
            "DUNG: database health FAIL."
        )


    print()
    print("3. SCHOOL STATE")
    print("-" * 148)

    source_rows = con.execute(
        f"""
        SELECT id,code,name,is_active
        FROM schools
        WHERE id IN ({marks(len(SOURCE_IDS))})
        ORDER BY id
        """,
        SOURCE_IDS,
    ).fetchall()

    active_sources = [
        dict(x)
        for x in source_rows
        if bool(x["is_active"])
    ]

    print("source count  =", len(source_rows))
    print("active source =", len(active_sources))

    if len(source_rows) != 15:
        raise RuntimeError(
            "DUNG: khong tim du 15 source."
        )

    if active_sources:
        print(
            json.dumps(
                active_sources,
                ensure_ascii=False,
                indent=2,
            )
        )
        raise RuntimeError(
            "DUNG: van con source active."
        )


    target_ids = sorted(
        TARGET_EXPECTED
    )

    target_rows = con.execute(
        f"""
        SELECT id,code,name,is_active
        FROM schools
        WHERE id IN ({marks(len(target_ids))})
        ORDER BY id
        """,
        target_ids,
    ).fetchall()

    inactive_targets = [
        dict(x)
        for x in target_rows
        if not bool(x["is_active"])
    ]

    print("target count  =", len(target_rows))
    print("active target =", len(target_rows) - len(inactive_targets))

    if len(target_rows) != 13 or inactive_targets:
        raise RuntimeError(
            "DUNG: target state FAIL."
        )


    print()
    print("4. CURRENT / FUTURE RESIDUAL TAI 15 SOURCE")
    print("-" * 148)

    res = residual(
        con,
        SOURCE_IDS,
        MOVE_YEAR_IDS,
    )

    print("residual =", res)

    if res:
        raise RuntimeError(
            "DUNG: van con CURRENT/FUTURE tai source."
        )


    print()
    print("5. USER TAI 15 SOURCE")
    print("-" * 148)

    user_row = con.execute(
        f"""
        SELECT
            COUNT(*) AS all_users,
            SUM(CASE WHEN is_active=1 THEN 1 ELSE 0 END) AS active_users,
            SUM(
                CASE
                    WHEN username LIKE 'truong_%'
                     AND is_active=1
                    THEN 1 ELSE 0
                END
            ) AS active_school_logins
        FROM users
        WHERE school_id IN ({marks(len(SOURCE_IDS))})
        """,
        SOURCE_IDS,
    ).fetchone()

    users = {
        "all_users": int(user_row["all_users"] or 0),
        "active_users": int(user_row["active_users"] or 0),
        "active_school_logins":
            int(user_row["active_school_logins"] or 0),
    }

    print(users)

    if users["active_users"] != 0:
        raise RuntimeError(
            "DUNG: van con active user tai source."
        )


    print()
    print("6. CBQL / GIAO VIEN / NHAN VIEN 13 TARGET")
    print("-" * 148)

    staff_fail = []
    total = Counter()

    for school_id in target_ids:

        expected = TARGET_EXPECTED[school_id]
        actual = staff_state(
            con,
            school_id,
        )

        total["TOTAL"] += actual["total"]
        total["CBQL"] += actual["CBQL"]
        total["GIAO_VIEN"] += actual["GIAO_VIEN"]
        total["NHAN_VIEN"] += actual["NHAN_VIEN"]

        ok = (
            actual["total"] == expected["total"]
            and actual["distinct"] == expected["total"]
            and actual["CBQL"] == expected["CBQL"]
            and actual["GIAO_VIEN"] == expected["GIAO_VIEN"]
            and actual["NHAN_VIEN"] == expected["NHAN_VIEN"]
            and not actual["duplicates"]
        )

        print(
            f"{school_id} | {expected['name']} | "
            f"T={actual['total']} "
            f"CBQL={actual['CBQL']} "
            f"GV={actual['GIAO_VIEN']} "
            f"NV={actual['NHAN_VIEN']} "
            f"| {'PASS' if ok else 'FAIL'}"
        )

        if not ok:
            staff_fail.append({
                "school_id": school_id,
                "expected": expected,
                "actual": actual,
            })

    print()
    print(
        "TOTAL 13 TARGET =",
        dict(total),
    )

    if dict(total) != {
        "TOTAL": 1293,
        "CBQL": 55,
        "GIAO_VIEN": 1140,
        "NHAN_VIEN": 98,
    }:
        raise RuntimeError(
            "DUNG: tong CBQL/GV/NV khong khop dry-run."
        )

    if staff_fail:
        print(
            json.dumps(
                staff_fail,
                ensure_ascii=False,
                indent=2,
            )
        )
        raise RuntimeError(
            "DUNG: co target sai doi ngu."
        )


    print()
    print("7. CROSS-TARGET DUPLICATE STAFF")
    print("-" * 148)

    cross = con.execute(
        f"""
        SELECT
            staff_member_id,
            COUNT(DISTINCT school_id) AS school_count,
            GROUP_CONCAT(DISTINCT school_id) AS schools
        FROM staff_year_records
        WHERE school_year_id=?
          AND is_active=1
          AND staff_member_id IS NOT NULL
          AND school_id IN ({marks(len(target_ids))})
        GROUP BY staff_member_id
        HAVING COUNT(DISTINCT school_id) > 1
        ORDER BY staff_member_id
        """,
        [YEAR_ID, *target_ids],
    ).fetchall()

    print("cross-target duplicate =", len(cross))

    if cross:
        print(
            json.dumps(
                [dict(x) for x in cross],
                ensure_ascii=False,
                indent=2,
            )
        )
        raise RuntimeError(
            "DUNG: co nhan su active tai nhieu target."
        )


    print()
    print("8. NGHI HUONG + 2 PRECOMPLETED NGHI LOC")
    print("-" * 148)

    special = con.execute(
        """
        SELECT id,code,name,is_active
        FROM schools
        WHERE id IN (1408,1607,1608)
        ORDER BY id
        """
    ).fetchall()

    for row in special:
        print(dict(row))

    state_map = {
        int(x["id"]): bool(x["is_active"])
        for x in special
    }

    if state_map.get(1408) is not True:
        raise RuntimeError(
            "DUNG: THCS Nghi Huong khong con GIU NGUYEN active."
        )

    if state_map.get(1607) is not False:
        raise RuntimeError(
            "DUNG: THCS Nghi Hoa bi thay doi trang thai."
        )

    if state_map.get(1608) is not False:
        raise RuntimeError(
            "DUNG: THCS Nghi Van bi thay doi trang thai."
        )


    print()
    print("9. OFFICIAL EXECUTION / BATCH")
    print("-" * 148)

    marks13 = marks(
        len(EXPECTED_PLAN_IDS)
    )

    rows13 = con.execute(
        f"""
        SELECT DISTINCT plan_id
        FROM school_merger_official_executions
        WHERE school_year_id=?
          AND plan_id IN ({marks13})
        ORDER BY plan_id
        """,
        [
            YEAR_ID,
            *sorted(EXPECTED_PLAN_IDS),
        ],
    ).fetchall()

    actual_plan_ids = {
        str(x["plan_id"])
        for x in rows13
    }

    print(
        "official plan count =",
        len(actual_plan_ids),
    )

    if actual_plan_ids != EXPECTED_PLAN_IDS:
        raise RuntimeError(
            "DUNG: official execution khong du dung 13 plan."
        )


    from app.services import (
        school_merger_level_batch_service
        as svc
    )

    batch_table = str(
        svc.BATCH_TABLE
    )

    batch_rows = con.execute(
        f"""
        SELECT *
        FROM {qident(batch_table)}
        WHERE school_year_id=?
          AND level_code='THCS'
        ORDER BY id
        """,
        (YEAR_ID,),
    ).fetchall()

    print(
        "THCS batch count =",
        len(batch_rows),
    )

    if len(batch_rows) != 1:
        raise RuntimeError(
            "DUNG: batch THCS khong duy nhat."
        )

    batch = dict(
        batch_rows[0]
    )

    print(
        json.dumps(
            batch,
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )


    print()
    print("10. POST BATCH STATE")
    print("-" * 148)

    preview = svc.build_level_batch_preview(
        school_year_id=YEAR_ID,
        level_code="THCS",
    )

    print(
        "counts              =",
        preview.get("counts"),
    )
    print(
        "candidate_count     =",
        len(preview.get("candidates") or []),
    )
    print(
        "previous_batch      =",
        bool(preview.get("previous_batch")),
    )
    print(
        "ready_for_execution =",
        preview.get("ready_for_execution"),
    )

    if preview.get("counts") != {
        "KEEP": 36,
        "DONE": 97,
        "READY": 0,
        "BLOCK": 0,
    }:
        raise RuntimeError(
            "DUNG: post-state khong phai 36/97/0/0."
        )

    if preview.get("candidates"):
        raise RuntimeError(
            "DUNG: van con candidate sau commit."
        )

    if preview.get("previous_batch") is None:
        raise RuntimeError(
            "DUNG: khong nhan batch da hoan thanh."
        )

finally:
    con.close()


print()
print("11. PAST EXACT VOI BACKUP TRUOC COMMIT")
print("-" * 148)

backup_db = find_backup_db()

if backup_db is None:
    raise RuntimeError(
        "DUNG: chua tim thay file SQLite backup "
        "co SHA dung database truoc commit."
    )

print(
    "backup DB =",
    backup_db,
)

print(
    "backup SHA=",
    sha256(backup_db),
)

involved = sorted(
    set(
        SOURCE_IDS
        + list(TARGET_EXPECTED)
    )
)

old = ro(backup_db)
new = ro(DB)

try:
    past_before = past_snapshot(
        old,
        involved,
    )

    past_after = past_snapshot(
        new,
        involved,
    )
finally:
    old.close()
    new.close()

print(
    "PAST BEFORE =",
    past_before,
)

print(
    "PAST AFTER  =",
    past_after,
)

print(
    "PAST EXACT  =",
    past_before == past_after,
)

if past_before != past_after:
    raise RuntimeError(
        "DUNG: du lieu PAST cua 28 truong da thay doi."
    )


print()
print("12. FINAL FILE SAFETY")
print("-" * 148)

if sha256(DB) != EXPECTED_DB_AFTER:
    raise RuntimeError(
        "DUNG: DB thay doi trong luc audit."
    )

if sha256(SERVICE) != EXPECTED_HASHES["service"]:
    raise RuntimeError(
        "DUNG: service thay doi."
    )

if sha256(RESOLUTION) != EXPECTED_HASHES["resolution"]:
    raise RuntimeError(
        "DUNG: resolution thay doi."
    )

print(
    "DB SHA =",
    sha256(DB),
)

print()
print("=" * 148)
print("KIEM TOAN CUOI THCS: PASS")
print("=" * 148)
print("13 PHUONG AN THUAN     = COMMITTED")
print("15 TRUONG NGUON        = INACTIVE")
print("13 TRUONG DICH         = ACTIVE")
print("CURRENT/FUTURE SOURCE  = 0")
print("PAST                    = GIU NGUYEN EXACT")
print("CBQL 13 DICH            = 55")
print("GIAO VIEN 13 DICH       = 1140")
print("NHAN VIEN 13 DICH       = 98")
print("TONG DOI NGU            = 1293")
print("DUPLICATE STAFF         = 0")
print("NGHI HUONG              = GIU NGUYEN")
print("NGHI HOA/NGHI VAN       = KHONG CHAY LAI")
print("DATABASE HEALTH         = OK")
print("THCS BATCH              = 1")
print("OFFICIAL PLAN           = 13")
print("SAP NHAP THCS THUAN     = DA KHOA KHONG CHAY LAI")
print("=" * 148)
