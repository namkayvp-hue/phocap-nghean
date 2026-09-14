from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import sys
import unicodedata
from collections import Counter
from datetime import datetime
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

LOCK = (
    ROOT
    / "data"
    / "school_merger_registry"
    / "qd3805_level_lock.json"
)

AUDIT_SERVICE = (
    ROOT
    / "app"
    / "services"
    / "school_merger_source_audit_service.py"
)

ROSTER_DIR = (
    ROOT
    / "data"
    / "school_merger_source_rosters"
)

ROSTER = (
    ROSTER_DIR
    / "THCS_2025_2026.json"
)


EXPECTED_DB_SHA = (
    "882e4925fd3e39d7e097ce127612c093"
    "852075e608d3f937294135282afec75a"
)

EXPECTED_SERVICE_SHA = (
    "963b8d6a280d8abef8e96486abd87d77"
    "cea289b08d2edb497647f250ed1b2af8"
)

EXPECTED_LOCK_SHA = (
    "ad310048a4c5b239404e0902cc04fda1"
    "d73474d11a739a2ca009d2727e4390c3"
)


PREVIOUS_YEAR_ID = 1
PREVIOUS_YEAR_CODE = "2025-2026"
LEVEL = "THCS"


INACTIVE_TOKENS = (
    "nghi viec",
    "thoi viec",
    "nghi huu",
    "chuyen di",
    "da chuyen",
    "inactive",
    "resigned",
    "retired",
    "terminated",
)


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
    text = str(
        value or ""
    ).strip().lower().replace(
        "đ",
        "d",
    )

    text = unicodedata.normalize(
        "NFD",
        text,
    )

    text = "".join(
        ch
        for ch in text
        if unicodedata.category(ch)
        != "Mn"
    )

    text = re.sub(
        r"[^a-z0-9]+",
        " ",
        text,
    )

    return " ".join(
        text.split()
    )


def is_db_inactive(row) -> bool:

    value = row[
        "record_is_active"
    ]

    if value in (
        0,
        False,
        "0",
    ):
        return True


    text = " ".join(
        norm(
            row[key]
        )
        for key in (
            "status_code",
            "source_status_label",
            "notes",
        )
        if row[key] not in (
            None,
            "",
        )
    )


    return any(
        token in text
        for token in INACTIVE_TOKENS
    )


def roster_status(row) -> str:

    if is_db_inactive(row):

        return (
            "Không hoạt động"
        )


    old = norm(
        row[
            "source_status_label"
        ]
    )


    if old == "chuyen den":

        return (
            "Chuyển đến"
        )


    return (
        "Đang làm việc"
    )


def connect_ro():
    con = sqlite3.connect(
        DB.resolve().as_uri()
        + "?mode=ro",
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


def ids_from_objects(items):

    result = set()

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
                result.add(sid)

        except Exception:
            pass

    return result


print("=" * 132)
print(
    "TAO SOURCE ROSTER THCS 2025-2026 TU DB SNAPSHOT"
)
print(
    "KHONG SUA DATABASE / SERVICE / REGISTRY"
)
print("=" * 132)


# ============================================================
# 1. KHÔNG ĐƯỢC GHI ĐÈ
# ============================================================

print()
print("=" * 132)
print("1. FILE GATE")
print("=" * 132)


if ROSTER.exists():

    print(
        "DA TON TAI:",
        ROSTER,
    )

    print(
        "SHA256 =",
        sha256(ROSTER),
    )

    raise RuntimeError(
        "DUNG: THCS_2025_2026.json "
        "da ton tai. KHONG GHI DE."
    )


print(
    "THCS roster hien tai: CHUA TON TAI"
)


# ============================================================
# 2. HASH GATE
# ============================================================

print()
print("=" * 132)
print("2. HASH GATE")
print("=" * 132)


before = {
    "db":
        sha256(DB),

    "service":
        sha256(SERVICE),

    "lock":
        sha256(LOCK),

    "audit_service":
        sha256(AUDIT_SERVICE),
}


for key, value in before.items():

    print(
        f"{key:15s} =",
        value,
    )


if before["db"] != EXPECTED_DB_SHA:

    raise RuntimeError(
        "DUNG: DB khong dung snapshot "
        "sau MN."
    )


if (
    before["service"]
    != EXPECTED_SERVICE_SHA
):

    raise RuntimeError(
        "DUNG: level batch service "
        "da thay doi."
    )


if before["lock"] != EXPECTED_LOCK_SHA:

    raise RuntimeError(
        "DUNG: level lock "
        "da thay doi."
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
    print("=" * 132)
    print("3. DATABASE HEALTH")
    print("=" * 132)

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
            "DUNG: DB integrity/FK FAIL."
        )


finally:
    con.close()


# ============================================================
# 4. LẤY PHẠM VI TRƯỜNG THCS TỪ QĐ3805
# ============================================================

from app.services import (
    school_merger_level_batch_service
    as svc
)


rows_before, counts_before, _, _ = (
    svc._state_rows(
        2,
        LEVEL,
    )
)


scope_school_ids = set()


for raw in rows_before:

    row = dict(raw)

    scope_school_ids.update(
        ids_from_objects(
            row.get(
                "member_schools"
            )
        )
    )

    scope_school_ids.update(
        ids_from_objects(
            row.get(
                "source_schools"
            )
        )
    )


    target = (
        row.get(
            "target_school"
        )
        or {}
    )


    if isinstance(
        target,
        dict,
    ):

        try:
            sid = int(
                target.get("id")
                or 0
            )

            if sid:
                scope_school_ids.add(
                    sid
                )

        except Exception:
            pass


scope_school_ids = sorted(
    scope_school_ids
)


print()
print("=" * 132)
print("4. PHAM VI QD3805 THCS")
print("=" * 132)

print(
    "state before =",
    counts_before,
)

print(
    "school IDs co the xac dinh =",
    len(
        scope_school_ids
    ),
)


if not scope_school_ids:

    raise RuntimeError(
        "DUNG: khong lay duoc "
        "school_id THCS."
    )


# ============================================================
# 5. ĐỌC DỮ LIỆU NĂM 2025-2026
# ============================================================

con = connect_ro()

try:

    placeholders = ",".join(
        "?"
        for _ in scope_school_ids
    )


    schools = [
        dict(x)
        for x in con.execute(
            f"""
            SELECT
                s.id,
                s.code,
                s.name,
                s.commune_id,
                s.is_active,
                c.name AS commune_name
            FROM schools s
            JOIN communes c
              ON c.id=s.commune_id
            WHERE s.id IN (
                {placeholders}
            )
            ORDER BY
                c.name,
                s.name,
                s.id
            """,
            scope_school_ids,
        ).fetchall()
    ]


    school_by_id = {
        int(x["id"]): x
        for x in schools
    }


    if len(
        school_by_id
    ) != len(
        scope_school_ids
    ):

        missing = sorted(
            set(
                scope_school_ids
            )
            - set(
                school_by_id
            )
        )

        raise RuntimeError(
            "DUNG: school_id khong ton tai: "
            + str(missing)
        )


    db_rows = [
        dict(x)
        for x in con.execute(
            f"""
            SELECT
                syr.id
                    AS year_record_id,

                syr.staff_member_id,
                syr.school_id,

                syr.is_active
                    AS record_is_active,

                syr.status_code,
                syr.source_status_label,
                syr.notes,

                sm.ministry_staff_code
                    AS staff_code,

                sm.full_name,
                sm.date_of_birth,

                s.code
                    AS school_code,

                s.name
                    AS school_name,

                c.name
                    AS commune_name

            FROM staff_year_records syr

            LEFT JOIN staff_members sm
              ON sm.id=syr.staff_member_id

            JOIN schools s
              ON s.id=syr.school_id

            JOIN communes c
              ON c.id=s.commune_id

            WHERE syr.school_year_id=?
              AND syr.school_id IN (
                  {placeholders}
              )

            ORDER BY
                c.name,
                s.name,
                syr.id
            """,
            [
                PREVIOUS_YEAR_ID,
                *scope_school_ids,
            ],
        ).fetchall()
    ]


finally:
    con.close()


rows_by_school = Counter(
    int(x["school_id"])
    for x in db_rows
)


empty_school_ids = [
    sid
    for sid in scope_school_ids
    if rows_by_school[
        sid
    ] == 0
]


print()
print("=" * 132)
print("5. DB SNAPSHOT 2025-2026")
print("=" * 132)

print(
    "total staff_year_records =",
    len(db_rows),
)

print(
    "schools co du lieu       =",
    len(
        rows_by_school
    ),
)

print(
    "schools khong co dong    =",
    len(
        empty_school_ids
    ),
)


for sid in empty_school_ids:

    school = school_by_id[
        sid
    ]

    print(
        "EMPTY |",
        sid,
        "|",
        school["code"],
        "|",
        school["name"],
        "|",
        school["commune_name"],
    )


# ============================================================
# 6. DỰNG ROSTER
# ============================================================

roster_rows = []

status_counts = Counter()


for raw in db_rows:

    status = roster_status(
        raw
    )

    status_counts[
        status
    ] += 1


    roster_rows.append({
        # Dùng id dòng DB làm dấu vết
        # thay cho số dòng Excel.
        "excel_row":
            int(
                raw[
                    "year_record_id"
                ]
            ),

        "commune_name":
            str(
                raw[
                    "commune_name"
                ]
                or ""
            ),

        "school_name":
            str(
                raw[
                    "school_name"
                ]
                or ""
            ),

        "staff_code":
            str(
                raw[
                    "staff_code"
                ]
                or ""
            ).strip(),

        "full_name":
            str(
                raw[
                    "full_name"
                ]
                or ""
            ).strip(),

        "date_of_birth":
            str(
                raw[
                    "date_of_birth"
                ]
                or ""
            ).strip(),

        "gender":
            "",

        "status_label":
            status,

        "position_label":
            "",

        # Các field dưới chỉ để truy vết;
        # source audit V4.3 không phụ thuộc.
        "source_db_staff_member_id":
            raw[
                "staff_member_id"
            ],

        "source_db_school_id":
            raw[
                "school_id"
            ],

        "source_db_school_code":
            raw[
                "school_code"
            ],

        "source_db_is_active":
            raw[
                "record_is_active"
            ],

        "source_db_status_code":
            raw[
                "status_code"
            ],

        "source_db_status_label":
            raw[
                "source_status_label"
            ],
    })


dataset_id = (
    "THCS-2025-2026-DB-SNAPSHOT-QD3805"
)


payload = {
    "version":
        1,

    "dataset_id":
        dataset_id,

    "level_code":
        "THCS",

    "school_year_code":
        PREVIOUS_YEAR_CODE,

    "source_file":
        "phocap.db",

    "source_sha256":
        before["db"],

    "source_sheet":
        (
            "staff_year_records "
            "JOIN staff_members "
            "JOIN schools "
            "JOIN communes"
        ),

    "header_row":
        0,

    "row_count":
        len(
            roster_rows
        ),

    "school_count":
        len(
            rows_by_school
        ),

    "active_status_labels": [
        "Đang làm việc",
        "Chuyển đến",
    ],

    "status_counts":
        dict(
            status_counts
        ),

    "source_kind":
        "INTERNAL_DB_SNAPSHOT",

    "snapshot_school_year_id":
        PREVIOUS_YEAR_ID,

    "scope_school_count":
        len(
            scope_school_ids
        ),

    "scope_school_ids":
        scope_school_ids,

    "empty_school_ids":
        empty_school_ids,

    "generated_at":
        datetime.now().isoformat(
            timespec="seconds"
        ),

    "rows":
        roster_rows,
}


# ============================================================
# 7. VALIDATE TRƯỚC KHI GHI
# ============================================================

print()
print("=" * 132)
print("6. VALIDATE ROSTER")
print("=" * 132)


if payload["level_code"] != "THCS":
    raise RuntimeError(
        "Sai level_code."
    )


if (
    payload["school_year_code"]
    != "2025-2026"
):
    raise RuntimeError(
        "Sai school_year_code."
    )


if (
    payload["row_count"]
    != len(
        payload["rows"]
    )
):
    raise RuntimeError(
        "Sai row_count."
    )


active_count = sum(
    1
    for x in roster_rows
    if x["status_label"]
    in (
        "Đang làm việc",
        "Chuyển đến",
    )
)


print(
    "dataset_id   =",
    dataset_id,
)

print(
    "row_count    =",
    len(
        roster_rows
    ),
)

print(
    "active rows  =",
    active_count,
)

print(
    "status_counts=",
    dict(
        status_counts
    ),
)


# ============================================================
# 8. GHI ATOMIC FILE MỚI
# ============================================================

print()
print("=" * 132)
print("7. TAO FILE ROSTER")
print("=" * 132)


ROSTER_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


tmp = ROSTER.with_suffix(
    ".json.tmp"
)


if tmp.exists():
    tmp.unlink()


created = False


try:

    tmp.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            default=str,
        )
        + "\n",
        encoding="utf-8",
    )


    # Đọc lại file tạm trước khi atomic replace.
    test = json.loads(
        tmp.read_text(
            encoding="utf-8"
        )
    )


    if (
        test.get(
            "dataset_id"
        )
        != dataset_id
        or test.get(
            "level_code"
        )
        != "THCS"
        or test.get(
            "school_year_code"
        )
        != "2025-2026"
        or len(
            test.get("rows")
            or []
        )
        != len(
            roster_rows
        )
    ):

        raise RuntimeError(
            "Roster tam khong dat "
            "self-check."
        )


    os.replace(
        tmp,
        ROSTER,
    )

    created = True


    print(
        "CREATED =",
        ROSTER,
    )

    print(
        "SHA256  =",
        sha256(
            ROSTER
        ),
    )


    # ========================================================
    # 9. CLEAR CACHE + KIỂM TRA SERVICE NHẬN ROSTER
    # ========================================================

    from app.services import (
        school_merger_source_audit_service
        as source_audit
    )


    if hasattr(
        source_audit,
        "_load_source_registry",
    ):

        source_audit._load_source_registry.cache_clear()


    registry_summary = (
        source_audit.source_registry_summary()
    )


    datasets = (
        registry_summary.get(
            "datasets"
        )
        or []
    )


    found_dataset = any(
        str(
            x.get(
                "dataset_id"
            )
            or ""
        )
        == dataset_id
        for x in datasets
    )


    print()
    print("=" * 132)
    print("8. SOURCE AUDIT REGISTRY")
    print("=" * 132)

    print(
        json.dumps(
            registry_summary,
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )


    if not found_dataset:

        raise RuntimeError(
            "Source audit service "
            "khong nhan THCS roster."
        )


    # ========================================================
    # 10. RERUN STATE THCS
    # ========================================================

    rows_after, counts_after, _, _ = (
        svc._state_rows(
            2,
            "THCS",
        )
    )


    issue_counts = Counter()

    remaining_blocks = []


    for raw in rows_after:

        row = dict(raw)

        if str(
            row.get(
                "batch_state"
            )
            or ""
        ).upper() != "BLOCK":

            continue


        audit = (
            row.get(
                "source_audit"
            )
            or {}
        )


        for check in (
            audit.get(
                "school_checks"
            )
            or []
        ):

            if not isinstance(
                check,
                dict,
            ):
                continue

            for issue in (
                check.get(
                    "issues"
                )
                or []
            ):

                if not isinstance(
                    issue,
                    dict,
                ):
                    continue

                code = str(
                    issue.get(
                        "code"
                    )
                    or "NO_CODE"
                )

                issue_counts[
                    code
                ] += 1


        remaining_blocks.append({
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

            "match_status":
                row.get(
                    "match_status"
                ),

            "action_type":
                row.get(
                    "action_type"
                ),

            "blockers":
                row.get(
                    "blockers"
                )
                or audit.get(
                    "blockers"
                )
                or [],
        })


    preview = (
        svc.build_level_batch_preview(
            school_year_id=2,
            level_code="THCS",
        )
    )


    print()
    print("=" * 132)
    print("9. THCS SAU KHI CO ROSTER")
    print("=" * 132)

    print(
        "counts before =",
        counts_before,
    )

    print(
        "counts after  =",
        counts_after,
    )

    print(
        "candidate_count       =",
        preview.get(
            "candidate_count"
        ),
    )

    print(
        "effective_block_count =",
        preview.get(
            "effective_block_count"
        ),
    )

    print(
        "ready_for_execution   =",
        preview.get(
            "ready_for_execution"
        ),
    )

    print(
        "ISSUE CODES =",
        json.dumps(
            dict(
                issue_counts
            ),
            ensure_ascii=False,
        ),
    )


    print()
    print(
        "REMAINING BLOCKS =",
        len(
            remaining_blocks
        ),
    )


    for item in remaining_blocks:

        print(
            json.dumps(
                item,
                ensure_ascii=False,
                default=str,
            )
        )


    # ========================================================
    # 11. FILE SAFETY
    # ========================================================

    db_after = sha256(DB)

    service_after = sha256(
        SERVICE
    )

    lock_after = sha256(
        LOCK
    )


    print()
    print("=" * 132)
    print("10. FILE SAFETY")
    print("=" * 132)

    print(
        "DB      :",
        before["db"],
        "->",
        db_after,
    )

    print(
        "SERVICE :",
        before["service"],
        "->",
        service_after,
    )

    print(
        "LOCK    :",
        before["lock"],
        "->",
        lock_after,
    )

    print(
        "ROSTER  :",
        sha256(
            ROSTER
        ),
    )


    if db_after != before["db"]:

        raise RuntimeError(
            "DUNG: DB da thay doi."
        )


    if (
        service_after
        != before[
            "service"
        ]
    ):

        raise RuntimeError(
            "DUNG: service da thay doi."
        )


    if (
        lock_after
        != before[
            "lock"
        ]
    ):

        raise RuntimeError(
            "DUNG: level lock da thay doi."
        )


except Exception:

    # Chỉ tự xóa roster nếu lỗi kỹ thuật
    # trong chính quá trình tạo/validate.
    if tmp.exists():
        tmp.unlink()


    if (
        created
        and ROSTER.exists()
    ):

        ROSTER.unlink()

        print()
        print(
            "DA TU XOA ROSTER "
            "DO VALIDATE THAT BAI."
        )


    raise


print()
print("=" * 132)
print("TAO ROSTER THCS: THANH CONG")
print("=" * 132)

print(
    "DATABASE             : KHONG THAY DOI"
)

print(
    "SERVICE              : KHONG THAY DOI"
)

print(
    "LEVEL LOCK           : KHONG THAY DOI"
)

print(
    "THCS ROSTER          : DA TAO"
)

print(
    "CHUA CHAY SAP NHAP THCS."
)

print()
print(
    "BUOC TIEP THEO:"
)

print(
    "1. XU LY CAC BLOCK CON LAI."
)

print(
    "2. KHOA OP-0342/0343 LA PRECOMPLETED."
)

print(
    "3. XU LY NGHI HUONG + CAC SPECIAL/UNMAPPED."
)

print(
    "4. DRY-RUN THCS."
)

print(
    "5. MOI THUC HIEN CHINH THUC."
)

print("=" * 132)
