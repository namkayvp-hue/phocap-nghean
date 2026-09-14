from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path


sys.dont_write_bytecode = True

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


ROOT = Path(r"C:\PhoCap")

DB = ROOT / "data" / "phocap.db"

SERVICE = (
    ROOT / "app" / "services"
    / "school_merger_level_batch_service.py"
)

LOCK = (
    ROOT / "data" / "school_merger_registry"
    / "qd3805_level_lock.json"
)

RESOLUTION = (
    ROOT / "data" / "school_merger_registry"
    / "qd3805_mn_resolution.json"
)

ROSTER = (
    ROOT / "data" / "school_merger_source_rosters"
    / "MN_2025_2026.json"
)


EXPECTED = {
    "db":
        "882e4925fd3e39d7e097ce127612c093"
        "852075e608d3f937294135282afec75a",

    "service":
        "963b8d6a280d8abef8e96486abd87d77"
        "cea289b08d2edb497647f250ed1b2af8",

    "lock":
        "ad310048a4c5b239404e0902cc04fda1"
        "d73474d11a739a2ca009d2727e4390c3",

    "resolution":
        "22ca7931ec40408ced25a3bde14a9672c"
        "04e12a760a077a44bb9d65b709b1163",

    "roster":
        "ef865f74aa51c2700ceb7746d5433b63"
        "fc6a52a4e3169014ebe0e446ac441120",
}


PREVIOUS_YEAR = 1
CURRENT_YEAR = 2


def sha256(path: Path) -> str:
    h = hashlib.sha256()

    with path.open("rb") as f:
        for block in iter(
            lambda: f.read(1024 * 1024),
            b"",
        ):
            h.update(block)

    return h.hexdigest()


def norm(value) -> str:
    value = str(value or "").strip().lower()

    value = unicodedata.normalize(
        "NFD",
        value,
    )

    value = "".join(
        ch
        for ch in value
        if unicodedata.category(ch) != "Mn"
    )

    value = value.replace(
        "đ",
        "d",
    )

    return " ".join(
        re.findall(
            r"[a-z0-9]+",
            value,
        )
    )


def school_key(value) -> str:
    words = norm(value).split()

    remove = {
        "truong",
        "mam",
        "non",
        "mn",
    }

    words = [
        x
        for x in words
        if x not in remove
    ]

    return " ".join(words)


def school_match(a, b) -> bool:
    a1 = school_key(a)
    b1 = school_key(b)

    if not a1 or not b1:
        return False

    return (
        a1 == b1
        or a1 in b1
        or b1 in a1
    )


def marks(n: int) -> str:
    return ",".join(
        "?"
        for _ in range(n)
    )


def connect_ro():
    con = sqlite3.connect(
        DB.resolve().as_uri()
        + "?mode=ro",
        uri=True,
        timeout=90,
    )

    con.row_factory = sqlite3.Row
    con.execute("PRAGMA query_only=ON")
    con.execute("PRAGMA foreign_keys=ON")

    return con


def ids_from_objects(items):
    result = []

    for item in items or []:
        if not isinstance(item, dict):
            continue

        try:
            sid = int(item.get("id") or 0)

            if sid:
                result.append(sid)

        except Exception:
            pass

    return sorted(set(result))


def active_ids(
    con,
    school_ids,
    year_id,
):
    if not school_ids:
        return set()

    rows = con.execute(
        f"""
        SELECT DISTINCT staff_member_id
        FROM staff_year_records
        WHERE school_year_id=?
          AND school_id IN ({marks(len(school_ids))})
          AND is_active=1
          AND staff_member_id IS NOT NULL
        """,
        [
            year_id,
            *school_ids,
        ],
    ).fetchall()

    return {
        int(x["staff_member_id"])
        for x in rows
    }


def member_info(con, staff_id):
    row = con.execute(
        """
        SELECT
            id,
            ministry_staff_code,
            full_name,
            date_of_birth,
            is_active
        FROM staff_members
        WHERE id=?
        """,
        (staff_id,),
    ).fetchone()

    return dict(row) if row else {}


def parse_ids(value):
    try:
        raw = json.loads(str(value))
    except Exception:
        return []

    if not isinstance(raw, list):
        raw = [raw]

    result = []

    for x in raw:
        try:
            result.append(int(x))
        except Exception:
            pass

    return sorted(set(result))


print("=" * 128)
print("CHAN DOAN 36 PHUONG AN NHAN SU MN - V2.2")
print("CHI DOC - KHONG SUA DATABASE / SERVICE / REGISTRY / ROSTER")
print("=" * 128)


# ============================================================
# 1. HASH
# ============================================================

paths = {
    "db": DB,
    "service": SERVICE,
    "lock": LOCK,
    "resolution": RESOLUTION,
    "roster": ROSTER,
}

before_hash = {}


print()
print("=" * 128)
print("1. HASH GATE")
print("=" * 128)


for key, path in paths.items():
    got = sha256(path)

    before_hash[key] = got

    print(
        f"{key:12s} = {got}"
    )

    if got != EXPECTED[key]:
        raise RuntimeError(
            f"DUNG: hash {key} da khac nen khoa."
        )


# ============================================================
# 2. LOAD ROSTER
# ============================================================

roster_payload = json.loads(
    ROSTER.read_text(
        encoding="utf-8-sig"
    )
)

roster_rows = list(
    roster_payload.get("rows")
    or []
)

active_labels = {
    norm(x)
    for x in (
        roster_payload.get(
            "active_status_labels"
        )
        or [
            "Đang làm việc",
            "Chuyển đến",
        ]
    )
}


by_code = defaultdict(list)


for row in roster_rows:
    code = str(
        row.get("staff_code")
        or ""
    ).strip()

    if code:
        by_code[code].append(row)


print()
print("=" * 128)
print("2. ROSTER MN")
print("=" * 128)

print(
    "dataset_id          =",
    roster_payload.get("dataset_id"),
)

print(
    "rows                =",
    len(roster_rows),
)

print(
    "active_status_labels=",
    roster_payload.get(
        "active_status_labels"
    ),
)


# ============================================================
# 3. STATE ROWS
# ============================================================

from app.services import (
    school_merger_level_batch_service
    as svc
)


ctx = svc._registry_level_context("MN")

rows, counts, candidates, meta = (
    svc._state_rows(
        2,
        "MN",
    )
)


pure_ids = {
    str(x.get("operation_id") or "")
    for x in (
        ctx.get("pure_actions")
        or []
    )
}


row_map = {
    str(
        x.get(
            "qd3805_operation_id"
        )
        or ""
    ):
        dict(x)

    for x in rows

    if str(
        x.get(
            "qd3805_operation_id"
        )
        or ""
    )
}


con = connect_ro()


try:

    # ========================================================
    # 4. XAC DINH 36 OP
    # ========================================================

    mismatch_ops = []


    for op in sorted(pure_ids):

        row = row_map[op]

        source_ids = ids_from_objects(
            row.get("source_schools")
        )

        target = (
            row.get("target_school")
            or {}
        )

        target_id = int(
            target.get("id")
            or 0
        )


        previous_raw = active_ids(
            con,
            [
                target_id,
                *source_ids,
            ],
            PREVIOUS_YEAR,
        )

        current = active_ids(
            con,
            [target_id],
            CURRENT_YEAR,
        )


        audit = (
            row.get("source_audit")
            or {}
        )


        eligible_sum = sum(
            int(
                x.get(
                    "active_db_eligible"
                )
                or 0
            )
            for x in (
                audit.get(
                    "school_checks"
                )
                or []
            )
        )


        if eligible_sum != len(current):

            mismatch_ops.append({
                "operation_id": op,
                "row": row,
                "source_ids": source_ids,
                "target_id": target_id,
                "raw_ids": previous_raw,
                "current_ids": current,
                "eligible_sum": eligible_sum,
            })


    print()
    print("=" * 128)
    print("3. TAP 36 CAN GIAI THICH")
    print("=" * 128)

    print(
        "count =",
        len(mismatch_ops),
    )


    if len(mismatch_ops) != 36:
        raise RuntimeError(
            "DUNG: khong con dung 36 operation."
        )


    # ========================================================
    # 5. OPERATION LOGS
    # ========================================================

    operation_logs = defaultdict(list)


    for log in con.execute(
        """
        SELECT
            id,
            target_school_id,
            source_school_ids_json,
            backup_name,
            summary_json,
            created_at
        FROM school_merger_operations
        WHERE school_year_id=2
        ORDER BY id
        """
    ).fetchall():

        sig = (
            int(log["target_school_id"]),
            tuple(
                parse_ids(
                    log[
                        "source_school_ids_json"
                    ]
                )
            ),
        )

        operation_logs[
            sig
        ].append(
            dict(log)
        )


    reconstruction_errors = []
    true_missing = []
    active_elsewhere_total = []
    current_extra_total = []

    operation_results = []


    # ========================================================
    # 6. PHAN TICH TUNG OP
    # ========================================================

    for item in mismatch_ops:

        op = item[
            "operation_id"
        ]

        row = item["row"]

        source_ids = item[
            "source_ids"
        ]

        target_id = item[
            "target_id"
        ]

        involved_ids = [
            target_id,
            *source_ids,
        ]

        raw_ids = item[
            "raw_ids"
        ]

        current_ids = item[
            "current_ids"
        ]

        eligible_sum = item[
            "eligible_sum"
        ]


        audit = (
            row.get("source_audit")
            or {}
        )

        checks = [
            dict(x)
            for x in (
                audit.get(
                    "school_checks"
                )
                or []
            )
            if isinstance(x, dict)
        ]

        checks_by_id = {
            int(x["school_id"]):
                x

            for x in checks

            if x.get("school_id")
        }


        previous_rows = con.execute(
            f"""
            SELECT DISTINCT
                staff_member_id,
                school_id
            FROM staff_year_records
            WHERE school_year_id=?
              AND school_id IN (
                  {marks(len(involved_ids))}
              )
              AND is_active=1
              AND staff_member_id IS NOT NULL
            """,
            [
                PREVIOUS_YEAR,
                *involved_ids,
            ],
        ).fetchall()


        eligible_ids = set()

        roster_unmatched = []


        for previous in previous_rows:

            staff_id = int(
                previous[
                    "staff_member_id"
                ]
            )

            school_id = int(
                previous[
                    "school_id"
                ]
            )

            check = checks_by_id.get(
                school_id
            )

            if check is None:
                continue


            member = member_info(
                con,
                staff_id,
            )

            code = str(
                member.get(
                    "ministry_staff_code"
                )
                or ""
            ).strip()


            roster_candidates = (
                by_code.get(code)
                or []
            )


            matched = []


            for rr in roster_candidates:

                commune_ok = (
                    not check.get(
                        "commune_name"
                    )
                    or norm(
                        rr.get(
                            "commune_name"
                        )
                    )
                    == norm(
                        check.get(
                            "commune_name"
                        )
                    )
                )

                school_ok = school_match(
                    rr.get(
                        "school_name"
                    ),
                    check.get(
                        "school_name"
                    ),
                )


                if (
                    commune_ok
                    and school_ok
                ):
                    matched.append(rr)


            active_matched = [
                rr
                for rr in matched
                if norm(
                    rr.get(
                        "status_label"
                    )
                )
                in active_labels
            ]


            if active_matched:

                eligible_ids.add(
                    staff_id
                )

            elif not matched:

                roster_unmatched.append({
                    "staff_member_id":
                        staff_id,

                    "staff_code":
                        code,

                    "school_id":
                        school_id,

                    "db_name":
                        member.get(
                            "full_name"
                        ),

                    "audit_school":
                        check.get(
                            "school_name"
                        ),

                    "audit_commune":
                        check.get(
                            "commune_name"
                        ),

                    "roster_candidates":
                        [
                            {
                                "school":
                                    x.get(
                                        "school_name"
                                    ),

                                "commune":
                                    x.get(
                                        "commune_name"
                                    ),

                                "status":
                                    x.get(
                                        "status_label"
                                    ),
                            }
                            for x
                            in roster_candidates
                        ],
                })


        recon_ok = (
            len(eligible_ids)
            == eligible_sum
        )


        if not recon_ok:

            reconstruction_errors.append({
                "operation_id":
                    op,

                "eligible_sum":
                    eligible_sum,

                "reconstructed":
                    len(
                        eligible_ids
                    ),

                "roster_unmatched":
                    roster_unmatched[:10],
            })


        missing_eligible = sorted(
            eligible_ids
            - current_ids
        )

        current_extra = sorted(
            current_ids
            - eligible_ids
        )


        missing_elsewhere = []
        missing_nowhere = []


        for staff_id in missing_eligible:

            active_rows = con.execute(
                """
                SELECT
                    school_id,
                    id
                FROM staff_year_records
                WHERE staff_member_id=?
                  AND school_year_id=?
                  AND is_active=1
                ORDER BY school_id,id
                """,
                (
                    staff_id,
                    CURRENT_YEAR,
                ),
            ).fetchall()


            elsewhere = [
                int(x["school_id"])
                for x in active_rows
                if int(
                    x["school_id"]
                )
                != target_id
            ]


            m = member_info(
                con,
                staff_id,
            )


            detail = {
                "operation_id":
                    op,

                "target_id":
                    target_id,

                "staff_member_id":
                    staff_id,

                "staff_code":
                    m.get(
                        "ministry_staff_code"
                    ),

                "full_name":
                    m.get(
                        "full_name"
                    ),

                "active_elsewhere":
                    elsewhere,
            }


            if elsewhere:

                missing_elsewhere.append(
                    detail
                )

                active_elsewhere_total.append(
                    detail
                )

            else:

                missing_nowhere.append(
                    detail
                )

                true_missing.append(
                    detail
                )


        for staff_id in current_extra:

            m = member_info(
                con,
                staff_id,
            )

            current_extra_total.append({
                "operation_id":
                    op,

                "target_id":
                    target_id,

                "staff_member_id":
                    staff_id,

                "staff_code":
                    m.get(
                        "ministry_staff_code"
                    ),

                "full_name":
                    m.get(
                        "full_name"
                    ),
            })


        sig = (
            target_id,
            tuple(source_ids),
        )

        logs = (
            operation_logs.get(sig)
            or []
        )


        log_summary = {}

        log_id = None


        if len(logs) == 1:

            log_id = logs[0]["id"]

            try:
                log_summary = json.loads(
                    logs[0][
                        "summary_json"
                    ]
                    or "{}"
                )
            except Exception:
                log_summary = {}


        result = {
            "operation_id":
                op,

            "plan_id":
                row.get("id"),

            "source_ids":
                source_ids,

            "target_id":
                target_id,

            "audit_status":
                audit.get("status"),

            "eligible_sum":
                eligible_sum,

            "eligible_reconstructed":
                len(eligible_ids),

            "reconstruction_exact":
                recon_ok,

            "current_target":
                len(current_ids),

            "current_extra_over_eligible":
                len(current_extra),

            "eligible_missing_target":
                len(missing_eligible),

            "missing_but_active_elsewhere":
                len(missing_elsewhere),

            "missing_nowhere":
                len(missing_nowhere),

            "operation_log_id":
                log_id,

            "staff_rollover_created":
                log_summary.get(
                    "staff_rollover_created"
                ),

            "staff_existing_elsewhere_skipped":
                log_summary.get(
                    "staff_existing_elsewhere_skipped"
                ),
        }


        operation_results.append(
            result
        )


    # ========================================================
    # 7. OUTPUT
    # ========================================================

    print()
    print("=" * 128)
    print("4. KET QUA 36 OP")
    print("=" * 128)


    for result in operation_results:

        print(
            json.dumps(
                result,
                ensure_ascii=False,
                default=str,
            )
        )


    print()
    print("=" * 128)
    print("5. TONG HOP IDENTITY")
    print("=" * 128)

    print(
        "36 operations                  =",
        len(operation_results),
    )

    print(
        "reconstruction mismatch ops    =",
        len(reconstruction_errors),
    )

    print(
        "eligible missing but elsewhere =",
        len(active_elsewhere_total),
    )

    print(
        "eligible missing nowhere       =",
        len(true_missing),
    )

    print(
        "current extra retained         =",
        len(current_extra_total),
    )


    if reconstruction_errors:

        print()
        print(
            "--- RECONSTRUCTION ERROR ---"
        )

        for x in reconstruction_errors:
            print(
                json.dumps(
                    x,
                    ensure_ascii=False,
                    default=str,
                )
            )


    if active_elsewhere_total:

        print()
        print(
            "--- ELIGIBLE NHUNG DANG ACTIVE O TRUONG KHAC ---"
        )

        for x in active_elsewhere_total:
            print(
                json.dumps(
                    x,
                    ensure_ascii=False,
                    default=str,
                )
            )


    if true_missing:

        print()
        print(
            "--- ELIGIBLE NHUNG KHONG CO CURRENT O BAT KY TRUONG NAO ---"
        )

        for x in true_missing:
            print(
                json.dumps(
                    x,
                    ensure_ascii=False,
                    default=str,
                )
            )


    print()
    print("=" * 128)
    print("6. DATABASE HEALTH")
    print("=" * 128)

    integrity = str(
        con.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]
    )

    fk = len(
        con.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()
    )

    print(
        "integrity =",
        integrity,
    )

    print(
        "FK        =",
        fk,
    )


finally:
    con.close()


# ============================================================
# 8. FILE IMMUTABILITY
# ============================================================

print()
print("=" * 128)
print("7. FILE IMMUTABILITY")
print("=" * 128)


for key, path in paths.items():

    after = sha256(path)

    print(
        key,
        ":",
        before_hash[key],
        "->",
        after,
    )

    if after != before_hash[key]:
        raise RuntimeError(
            f"DUNG: {key} da thay doi."
        )


print()
print("=" * 128)


if reconstruction_errors:

    print(
        "STAFF_36_ACCOUNTING=CHUA_KET_LUAN"
    )

    print(
        "Ly do: chua dung lai duoc identity eligible "
        "100% tu roster."
    )

elif true_missing:

    print(
        "STAFF_36_ACCOUNTING=CAN_KIEM_TRA"
    )

    print(
        "Co nguoi du dieu kien 2025-2026 "
        "nhung khong co CURRENT tai target "
        "va cung khong active o truong khac."
    )

else:

    print(
        "STAFF_36_ACCOUNTING=PASS"
    )

    print(
        "Khong co identity eligible nao bi mat."
    )

    print(
        "CURRENT extra duoc giu lai dung nguyen tac "
        "rollover chi bo sung thieu."
    )


print()
print(
    "KHONG SUA DATABASE."
)

print(
    "KHONG SUA SERVICE / REGISTRY / ROSTER."
)

print(
    "KHONG ROLLBACK."
)

print(
    "KHONG CHAY LAI SAP NHAP."
)

print("=" * 128)
