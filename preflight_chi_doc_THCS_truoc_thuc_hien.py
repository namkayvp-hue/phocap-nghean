from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from pathlib import Path


sys.dont_write_bytecode = True

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


ROOT = Path(r"C:\PhoCap")

DB = ROOT / "data" / "phocap.db"

SERVICE = (
    ROOT
    / "app"
    / "services"
    / "school_merger_level_batch_service.py"
)

EXPECTED_DB_SHA = (
    "882e4925fd3e39d7e097ce127612c093"
    "852075e608d3f937294135282afec75a"
)

EXPECTED_SERVICE_SHA = (
    "963b8d6a280d8abef8e96486abd87d77"
    "cea289b08d2edb497647f250ed1b2af8"
)

YEAR_ID = 2
LEVEL = "THCS"


def sha256(path: Path) -> str:
    h = hashlib.sha256()

    with path.open("rb") as f:
        for block in iter(
            lambda: f.read(1024 * 1024),
            b"",
        ):
            h.update(block)

    return h.hexdigest()


def connect_ro():
    con = sqlite3.connect(
        DB.resolve().as_uri() + "?mode=ro",
        uri=True,
        timeout=90,
    )

    con.row_factory = sqlite3.Row

    con.execute(
        "PRAGMA query_only=ON"
    )

    con.execute(
        "PRAGMA foreign_keys=ON"
    )

    return con


def school_ids(items):
    result = []

    for item in items or []:

        if not isinstance(
            item,
            dict,
        ):
            continue

        try:
            sid = int(
                item.get("id")
                or 0
            )

            if sid:
                result.append(sid)

        except Exception:
            pass

    return sorted(
        set(result)
    )


print("=" * 130)
print(
    "PREFLIGHT CHI DOC TRUOC KHI THUC HIEN CHINH THUC THCS"
)
print("=" * 130)

print(
    "KHONG INSERT / UPDATE / DELETE"
)

print(
    "KHONG CHAY SAP NHAP"
)

print("=" * 130)


# ============================================================
# 1. WAL / JOURNAL GATE
# ============================================================

print()
print("=" * 130)
print("1. SERVER / WAL GATE")
print("=" * 130)


for suffix in (
    "-wal",
    "-journal",
):

    p = Path(
        str(DB) + suffix
    )

    size = (
        p.stat().st_size
        if p.exists()
        else 0
    )

    print(
        p.name,
        "=",
        size,
    )

    if size > 0:
        raise RuntimeError(
            "DUNG: "
            + p.name
            + " dang co du lieu. "
              "Hay dung Uvicorn/server hoan toan."
        )


# ============================================================
# 2. HASH GATE
# ============================================================

print()
print("=" * 130)
print("2. HASH GATE")
print("=" * 130)


db_sha = sha256(DB)
service_sha = sha256(SERVICE)

print(
    "DB      =",
    db_sha,
)

print(
    "SERVICE =",
    service_sha,
)


if db_sha != EXPECTED_DB_SHA:

    raise RuntimeError(
        "DUNG: DB da thay doi so voi nen "
        "sau khi hoan tat MN. "
        "KHONG THUC HIEN THCS."
    )


if service_sha != EXPECTED_SERVICE_SHA:

    raise RuntimeError(
        "DUNG: school_merger_level_batch_service.py "
        "da thay doi. KHONG THUC HIEN THCS."
    )


# ============================================================
# 3. DATABASE HEALTH
# ============================================================

con = connect_ro()

try:

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


    print()
    print("=" * 130)
    print("3. DATABASE HEALTH")
    print("=" * 130)

    print(
        "integrity =",
        integrity,
    )

    print(
        "FK        =",
        fk,
    )


    if (
        integrity.lower() != "ok"
        or fk != 0
    ):
        raise RuntimeError(
            "DUNG: database khong dat integrity/FK."
        )


    batch_logs = con.execute(
        """
        SELECT *
        FROM school_merger_level_batches
        WHERE school_year_id=?
          AND UPPER(TRIM(level_code))=?
        ORDER BY id
        """,
        (
            YEAR_ID,
            LEVEL,
        ),
    ).fetchall()


    print(
        "THCS batch logs =",
        len(batch_logs),
    )


    if batch_logs:

        print(
            json.dumps(
                [
                    dict(x)
                    for x in batch_logs
                ],
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        )


finally:
    con.close()


# ============================================================
# 4. LOAD SERVICE / REGISTRY
# ============================================================

from app.services import (
    school_merger_level_batch_service
    as svc
)


ctx = svc._registry_level_context(
    LEVEL
)

preview = (
    svc.build_level_batch_preview(
        school_year_id=YEAR_ID,
        level_code=LEVEL,
    )
)

rows, counts, candidates, meta = (
    svc._state_rows(
        YEAR_ID,
        LEVEL,
    )
)


pure_ops = list(
    ctx.get(
        "pure_actions"
    )
    or []
)

keep_ops = list(
    ctx.get(
        "keep_ops"
    )
    or []
)

special_ops = list(
    ctx.get(
        "special_ops"
    )
    or []
)

special_orphans = list(
    ctx.get(
        "special_orphans"
    )
    or []
)

unresolved = list(
    ctx.get(
        "unresolved"
    )
    or []
)


print()
print("=" * 130)
print("4. REGISTRY THCS")
print("=" * 130)

print(
    "pure_actions   =",
    len(pure_ops),
)

print(
    "keep_ops       =",
    len(keep_ops),
)

print(
    "special_ops    =",
    len(special_ops),
)

print(
    "special_orphans=",
    len(special_orphans),
)

print(
    "unresolved     =",
    len(unresolved),
)

print()

print(
    "registry summary =",
    json.dumps(
        preview.get(
            "registry_level_summary"
        ),
        ensure_ascii=False,
        default=str,
    ),
)


# ============================================================
# 5. BATCH THCS
# ============================================================

print()
print("=" * 130)
print("5. BATCH THCS")
print("=" * 130)

for key in (
    "counts",
    "candidate_count",
    "effective_ready_count",
    "effective_block_count",
    "ready_for_execution",
    "all_done",
    "batch_fingerprint",
    "previous_batch",
    "extra_blockers",
    "overlap_items",
    "missing_action_ops",
    "missing_keep_ops",
):

    print(
        f"{key:24s} =",
        preview.get(key),
    )


# ============================================================
# 6. READY CANDIDATES
# ============================================================

print()
print("=" * 130)
print("6. CAC PHUONG AN READY THCS")
print("=" * 130)


ready_rows = []

for raw in rows:

    row = dict(raw)

    state = str(
        row.get(
            "batch_state"
        )
        or ""
    ).upper()

    if state != "READY":
        continue


    op_id = str(
        row.get(
            "qd3805_operation_id"
        )
        or ""
    )

    plan_id = str(
        row.get("id")
        or ""
    )

    sources = school_ids(
        row.get(
            "source_schools"
        )
    )

    target = (
        row.get(
            "target_school"
        )
        or {}
    )

    target_id = (
        int(
            target.get("id")
            or 0
        )
        or None
    )


    item = {
        "operation_id":
            op_id,

        "plan_id":
            plan_id,

        "commune":
            row.get(
                "commune_name"
            ),

        "sources":
            [
                {
                    "id":
                        x.get("id"),

                    "code":
                        x.get("code"),

                    "name":
                        x.get("name"),
                }
                for x in (
                    row.get(
                        "source_schools"
                    )
                    or []
                )
                if isinstance(
                    x,
                    dict,
                )
            ],

        "target": {
            "id":
                target_id,

            "code":
                target.get("code"),

            "name":
                target.get("name"),
        },

        "safe_for_future_execution":
            row.get(
                "safe_for_future_execution"
            ),

        "execution_status":
            row.get(
                "execution_status"
            ),

        "source_audit_status":
            (
                row.get(
                    "source_audit"
                )
                or {}
            ).get(
                "status"
            ),

        "source_audit_pass":
            (
                row.get(
                    "source_audit"
                )
                or {}
            ).get(
                "pass"
            ),
    }


    ready_rows.append(
        item
    )


print(
    "READY count =",
    len(ready_rows),
)


for item in ready_rows:

    print(
        json.dumps(
            item,
            ensure_ascii=False,
            default=str,
        )
    )


# ============================================================
# 7. BLOCK
# ============================================================

print()
print("=" * 130)
print("7. CAC PHUONG AN BLOCK THCS")
print("=" * 130)


block_rows = []


for raw in rows:

    row = dict(raw)

    if str(
        row.get(
            "batch_state"
        )
        or ""
    ).upper() != "BLOCK":
        continue


    block_rows.append({
        "operation_id":
            row.get(
                "qd3805_operation_id"
            ),

        "plan_id":
            row.get("id"),

        "commune":
            row.get(
                "commune_name"
            ),

        "title":
            row.get(
                "official_plan"
            )
            or row.get(
                "display_title"
            ),

        "blockers":
            row.get(
                "blockers"
            )
            or (
                row.get(
                    "source_audit"
                )
                or {}
            ).get(
                "blockers"
            )
            or [],
    })


print(
    "BLOCK count =",
    len(block_rows),
)


for item in block_rows:

    print(
        json.dumps(
            item,
            ensure_ascii=False,
            default=str,
        )
    )


# ============================================================
# 8. SPECIAL - KHONG DUOC VAO BATCH THCS THUAN
# ============================================================

print()
print("=" * 130)
print("8. SPECIAL / LIEN CAP - LOAI KHOI BATCH THCS THUAN")
print("=" * 130)


for item in (
    special_ops
    + special_orphans
):

    print(
        json.dumps(
            item,
            ensure_ascii=False,
            default=str,
        )
    )


# ============================================================
# 9. Nghi Loc PRECOMPLETED
# ============================================================

print()
print("=" * 130)
print("9. KIEM TRA 2 THCS NGHI LOC DA HOAN TAT")
print("=" * 130)


for raw in rows:

    row = dict(raw)

    op = str(
        row.get(
            "qd3805_operation_id"
        )
        or ""
    )

    names = " ".join(
        str(x.get("name") or "")
        for x in (
            row.get(
                "member_schools"
            )
            or []
        )
        if isinstance(
            x,
            dict,
        )
    )


    if (
        "Nghi Hoa" in names
        or "Nghi Vạn" in names
        or "Nghi Van" in names
        or "Nghi Diên" in names
        or "Nghi Dien" in names
        or "Nghi Trung" in names
    ):

        print(
            json.dumps(
                {
                    "operation_id":
                        op,

                    "plan_id":
                        row.get("id"),

                    "state":
                        row.get(
                            "batch_state"
                        ),

                    "execution_status":
                        row.get(
                            "execution_status"
                        ),

                    "members":
                        row.get(
                            "member_schools"
                        ),

                    "sources":
                        row.get(
                            "source_schools"
                        ),

                    "target":
                        row.get(
                            "target_school"
                        ),
                },
                ensure_ascii=False,
                default=str,
            )
        )


# ============================================================
# 10. FINAL GATE
# ============================================================

print()
print("=" * 130)
print("10. KET LUAN PREFLIGHT")
print("=" * 130)


previous_batch = (
    preview.get(
        "previous_batch"
    )
)


if previous_batch is not None:

    print(
        "THCS_PREFLIGHT=STOP_ALREADY_EXECUTED"
    )

    print(
        "Cap THCS da co batch log. "
        "TUYET DOI KHONG CHAY LAI."
    )

elif int(
    preview.get(
        "effective_block_count"
    )
    or 0
) != 0:

    print(
        "THCS_PREFLIGHT=BLOCK"
    )

    print(
        "Con blocker. "
        "CHUA DUOC GHI THAT."
    )

elif not bool(
    preview.get(
        "ready_for_execution"
    )
):

    print(
        "THCS_PREFLIGHT=NOT_READY"
    )

    print(
        "Chua dat dieu kien "
        "thuc hien toan cap."
    )

elif int(
    preview.get(
        "candidate_count"
    )
    or 0
) <= 0:

    print(
        "THCS_PREFLIGHT=NO_CANDIDATE"
    )

    print(
        "Khong co phuong an moi "
        "de thuc hien."
    )

else:

    print(
        "THCS_PREFLIGHT=READY_FOR_DRY_RUN"
    )

    print(
        "So phuong an se ghi =",
        preview.get(
            "candidate_count"
        ),
    )

    print(
        "BATCH_FINGERPRINT =",
        preview.get(
            "batch_fingerprint"
        ),
    )

    print(
        "BUOC TIEP THEO: "
        "DRY-RUN RAM TOAN BO CANDIDATE THCS."
    )


# ============================================================
# 11. IMMUTABILITY
# ============================================================

print()
print("=" * 130)
print("11. FILE IMMUTABILITY")
print("=" * 130)


db_after = sha256(DB)
service_after = sha256(SERVICE)


print(
    "DB      :",
    db_sha,
    "->",
    db_after,
)

print(
    "SERVICE :",
    service_sha,
    "->",
    service_after,
)


if (
    db_after != db_sha
    or service_after
    != service_sha
):

    raise RuntimeError(
        "DUNG: file that bi thay doi "
        "trong khi preflight."
    )


print()
print(
    "PREFLIGHT CHI DOC THCS: HOAN TAT"
)

print(
    "DATABASE / SERVICE: KHONG THAY DOI"
)

print("=" * 130)
