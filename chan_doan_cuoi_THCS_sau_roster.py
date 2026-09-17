from __future__ import annotations

import difflib
import hashlib
import json
import re
import sqlite3
import sys
import unicodedata
from collections import Counter
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

ROSTER = (
    ROOT
    / "data"
    / "school_merger_source_rosters"
    / "THCS_2025_2026.json"
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

    "roster":
        "926528e0ae600a6b950b459c6f8ec5c6810e69d49158d1ff3c9a3d76c0bca657",
}


KNOWN_PRECOMPLETED = {
    "QD3805-OP-0342",
    "QD3805-OP-0343",
}


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
    text = str(value or "").strip().lower()
    text = text.replace("đ", "d")

    text = unicodedata.normalize(
        "NFD",
        text,
    )

    text = "".join(
        ch
        for ch in text
        if unicodedata.category(ch) != "Mn"
    )

    text = re.sub(
        r"[^a-z0-9]+",
        " ",
        text,
    )

    return " ".join(text.split())


def connect_ro():
    con = sqlite3.connect(
        DB.resolve().as_uri() + "?mode=ro",
        uri=True,
        timeout=90,
    )

    con.row_factory = sqlite3.Row
    con.execute("PRAGMA query_only=ON")
    con.execute("PRAGMA foreign_keys=ON")

    return con


def school_ids(items):
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


def target_id(row):

    obj = (
        row.get("target_school")
        or {}
    )

    if not isinstance(obj, dict):
        return None

    try:
        value = int(obj.get("id") or 0)

        return value or None

    except Exception:
        return None


def staff_count(
    con,
    school_id,
    year_id,
):
    if not school_id:
        return 0

    return int(
        con.execute(
            """
            SELECT COUNT(
                DISTINCT staff_member_id
            )
            FROM staff_year_records
            WHERE school_id=?
              AND school_year_id=?
              AND is_active=1
              AND staff_member_id IS NOT NULL
            """,
            (
                int(school_id),
                int(year_id),
            ),
        ).fetchone()[0]
        or 0
    )


def candidate_plan_ids(candidates):

    result = set()

    for item in candidates or []:

        if not isinstance(item, dict):
            continue

        for key in (
            "id",
            "plan_id",
        ):
            value = str(
                item.get(key)
                or ""
            )

            if value.startswith("PA"):
                result.add(value)


        plan = item.get("plan")

        if isinstance(plan, dict):

            value = str(
                plan.get("id")
                or ""
            )

            if value:
                result.add(value)

    return result


def issue_codes(audit):

    out = []

    for check in (
        audit.get("school_checks")
        or []
    ):

        if not isinstance(check, dict):
            continue

        for issue in (
            check.get("issues")
            or []
        ):

            if isinstance(issue, dict):

                out.append(
                    str(
                        issue.get("code")
                        or "NO_CODE"
                    )
                )

    return out


print("=" * 134)
print(
    "CHAN DOAN CUOI THCS SAU KHI CO ROSTER"
)
print(
    "CHI DOC - KHONG SUA DB / SERVICE / LOCK / ROSTER"
)
print("=" * 134)


# ==========================================================
# 1. HASH
# ==========================================================

before = {}

print()
print("=" * 134)
print("1. HASH GATE")
print("=" * 134)


for key, path in {
    "db": DB,
    "service": SERVICE,
    "lock": LOCK,
    "roster": ROSTER,
}.items():

    got = sha256(path)
    before[key] = got

    print(
        f"{key:12s} = {got}"
    )

    if got != EXPECTED[key]:

        raise RuntimeError(
            "DUNG: "
            + key
            + " khong dung nen da khoa."
        )


# ==========================================================
# 2. STATE
# ==========================================================

from app.services import (
    school_merger_level_batch_service
    as svc
)


ctx = svc._registry_level_context(
    "THCS"
)

rows, counts, candidates, meta = (
    svc._state_rows(
        2,
        "THCS",
    )
)

preview = (
    svc.build_level_batch_preview(
        school_year_id=2,
        level_code="THCS",
    )
)


candidate_ids = (
    candidate_plan_ids(
        candidates
    )
)


ready_rows = [
    dict(x)
    for x in rows
    if str(
        x.get("batch_state")
        or ""
    ).upper()
    == "READY"
]

block_rows = [
    dict(x)
    for x in rows
    if str(
        x.get("batch_state")
        or ""
    ).upper()
    == "BLOCK"
]


print()
print("=" * 134)
print("2. STATE TONG")
print("=" * 134)

print(
    "counts                =",
    counts,
)

print(
    "READY rows            =",
    len(ready_rows),
)

print(
    "BLOCK rows            =",
    len(block_rows),
)

print(
    "candidate rows        =",
    len(candidates),
)

print(
    "candidate plan ids    =",
    len(candidate_ids),
)

print(
    "candidate_count       =",
    preview.get(
        "candidate_count"
    ),
)

print(
    "effective_ready_count =",
    preview.get(
        "effective_ready_count"
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
    "extra_blockers        =",
    json.dumps(
        preview.get(
            "extra_blockers"
        )
        or [],
        ensure_ascii=False,
        default=str,
    ),
)

print(
    "overlap_items         =",
    json.dumps(
        preview.get(
            "overlap_items"
        )
        or [],
        ensure_ascii=False,
        default=str,
    ),
)


# ==========================================================
# 3. READY 14
# ==========================================================

print()
print("=" * 134)
print("3. TOAN BO 14 READY")
print("=" * 134)


con = connect_ro()

try:

    for row in ready_rows:

        op = str(
            row.get(
                "qd3805_operation_id"
            )
            or ""
        )

        pid = str(
            row.get("id")
            or ""
        )

        src = school_ids(
            row.get(
                "source_schools"
            )
        )

        tgt = target_id(row)


        source_state = []

        for sid in src:

            s = con.execute(
                """
                SELECT
                    id,
                    code,
                    name,
                    is_active
                FROM schools
                WHERE id=?
                """,
                (sid,),
            ).fetchone()

            source_state.append(
                dict(s)
                if s
                else {
                    "id": sid,
                    "missing": True,
                }
            )


        target_state = None

        if tgt:

            s = con.execute(
                """
                SELECT
                    id,
                    code,
                    name,
                    is_active
                FROM schools
                WHERE id=?
                """,
                (tgt,),
            ).fetchone()

            target_state = (
                dict(s)
                if s
                else None
            )


        audit = (
            row.get(
                "source_audit"
            )
            or {}
        )


        print(
            json.dumps(
                {
                    "operation_id":
                        op,

                    "plan_id":
                        pid,

                    "commune":
                        row.get(
                            "commune_name"
                        ),

                    "is_candidate":
                        (
                            pid in candidate_ids
                            if candidate_ids
                            else None
                        ),

                    "KNOWN_PRECOMPLETED":
                        op
                        in KNOWN_PRECOMPLETED,

                    "sources":
                        source_state,

                    "target":
                        target_state,

                    "staff_2025_sources":
                        {
                            str(sid):
                                staff_count(
                                    con,
                                    sid,
                                    1,
                                )
                            for sid in src
                        },

                    "staff_2025_target":
                        staff_count(
                            con,
                            tgt,
                            1,
                        ),

                    "staff_2026_target":
                        staff_count(
                            con,
                            tgt,
                            2,
                        ),

                    "source_audit_status":
                        audit.get(
                            "status"
                        ),

                    "source_audit_pass":
                        audit.get(
                            "pass"
                        ),
                },
                ensure_ascii=False,
                default=str,
            )
        )


    # ======================================================
    # 4. BLOCK 20
    # ======================================================

    print()
    print("=" * 134)
    print("4. TOAN BO 20 BLOCK")
    print("=" * 134)


    block_category = Counter()

    unmatched_names = []


    for row in block_rows:

        op = str(
            row.get(
                "qd3805_operation_id"
            )
            or ""
        )

        audit = (
            row.get(
                "source_audit"
            )
            or {}
        )

        src = school_ids(
            row.get(
                "source_schools"
            )
        )

        tgt = target_id(row)

        action_type = str(
            row.get(
                "action_type"
            )
            or ""
        ).upper()

        match_status = str(
            row.get(
                "match_status"
            )
            or ""
        ).upper()


        checks = []

        has_null_school = False
        zero_previous_school = False


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

            sid = check.get(
                "school_id"
            )

            if sid is None:
                has_null_school = True

                unmatched_names.append({
                    "operation_id":
                        op,

                    "plan_id":
                        row.get("id"),

                    "commune":
                        row.get(
                            "commune_name"
                        ),

                    "role":
                        check.get(
                            "role"
                        ),

                    "school_name":
                        check.get(
                            "school_name"
                        ),

                    "school_code":
                        check.get(
                            "school_code"
                        ),
                })


            if (
                sid is not None
                and int(
                    check.get(
                        "db_previous_total_rows"
                    )
                    or 0
                )
                == 0
                and "MISSING_SOURCE_ROSTER"
                in [
                    str(
                        x.get("code")
                        or ""
                    )
                    for x
                    in (
                        check.get("issues")
                        or []
                    )
                    if isinstance(
                        x,
                        dict,
                    )
                ]
            ):
                zero_previous_school = True


            checks.append({
                "role":
                    check.get(
                        "role"
                    ),

                "school_id":
                    sid,

                "school_code":
                    check.get(
                        "school_code"
                    ),

                "school_name":
                    check.get(
                        "school_name"
                    ),

                "db_previous_total_rows":
                    check.get(
                        "db_previous_total_rows"
                    ),

                "active_db_eligible":
                    check.get(
                        "active_db_eligible"
                    ),

                "issues":
                    check.get(
                        "issues"
                    )
                    or [],
            })


        if op in KNOWN_PRECOMPLETED:

            category = (
                "PRECOMPLETED_KNOWN"
            )

        elif (
            action_type == "SPECIAL"
            and not src
            and tgt is None
        ):

            category = (
                "SPECIAL_NO_DIRECT_SOURCE_TARGET"
            )

        elif has_null_school:

            category = (
                "PARTIAL_WITH_UNMATCHED_SCHOOL"
            )

        elif zero_previous_school:

            category = (
                "KNOWN_DB_SCHOOL_WITH_ZERO_2025_DATA"
            )

        else:

            category = (
                "OTHER_BLOCK"
            )


        block_category[
            category
        ] += 1


        print(
            json.dumps(
                {
                    "category":
                        category,

                    "operation_id":
                        op,

                    "plan_id":
                        row.get("id"),

                    "commune":
                        row.get(
                            "commune_name"
                        ),

                    "action_type":
                        row.get(
                            "action_type"
                        ),

                    "match_status":
                        row.get(
                            "match_status"
                        ),

                    "official_plan":
                        row.get(
                            "official_plan"
                        )
                        or row.get(
                            "display_title"
                        ),

                    "member_schools":
                        row.get(
                            "member_schools"
                        ),

                    "source_ids":
                        src,

                    "target_id":
                        tgt,

                    "checks":
                        checks,

                    "blockers":
                        row.get(
                            "blockers"
                        )
                        or audit.get(
                            "blockers"
                        )
                        or [],
                },
                ensure_ascii=False,
                default=str,
            )
        )


    print()
    print("=" * 134)
    print("5. PHAN LOAI 20 BLOCK")
    print("=" * 134)

    print(
        json.dumps(
            dict(
                block_category
            ),
            ensure_ascii=False,
            indent=2,
        )
    )


    # ======================================================
    # 6. TÌM ỨNG VIÊN CHO TÊN CHƯA MATCH
    # ======================================================

    print()
    print("=" * 134)
    print("6. GOI Y DB CHO CAC TEN CHUA MATCH")
    print("=" * 134)


    all_schools = [
        dict(x)
        for x in con.execute(
            """
            SELECT
                s.id,
                s.code,
                s.name,
                s.commune_id,
                s.is_active,
                c.name AS commune_name
            FROM schools s
            LEFT JOIN communes c
              ON c.id=s.commune_id
            ORDER BY s.id
            """
        ).fetchall()
    ]


    seen_unmatched = set()


    for item in unmatched_names:

        key = (
            item[
                "operation_id"
            ],
            str(
                item[
                    "school_name"
                ]
                or ""
            ),
        )

        if key in seen_unmatched:
            continue

        seen_unmatched.add(key)


        wanted = norm(
            item[
                "school_name"
            ]
        )

        wanted_commune = norm(
            item[
                "commune"
            ]
        )


        scored = []


        for school in all_schools:

            db_name = norm(
                school[
                    "name"
                ]
            )

            if not db_name:
                continue


            ratio = (
                difflib.SequenceMatcher(
                    None,
                    wanted,
                    db_name,
                ).ratio()
            )


            if wanted_commune:

                db_commune = norm(
                    school[
                        "commune_name"
                    ]
                )

                if (
                    wanted_commune
                    == db_commune
                ):
                    ratio += 0.15


            if ratio >= 0.48:

                scored.append(
                    (
                        ratio,
                        school,
                    )
                )


        scored.sort(
            key=lambda x:
                (
                    -x[0],
                    x[1]["id"],
                )
        )


        candidates_out = []


        for score, school_obj in (
            scored[:8]
        ):

            sid = int(
                school_obj[
                    "id"
                ]
            )


            candidates_out.append({
                "score":
                    round(
                        score,
                        4,
                    ),

                "id":
                    sid,

                "code":
                    school_obj[
                        "code"
                    ],

                "name":
                    school_obj[
                        "name"
                    ],

                "commune":
                    school_obj[
                        "commune_name"
                    ],

                "is_active":
                    school_obj[
                        "is_active"
                    ],

                "staff_2025":
                    staff_count(
                        con,
                        sid,
                        1,
                    ),

                "staff_2026":
                    staff_count(
                        con,
                        sid,
                        2,
                    ),
            })


        print(
            json.dumps(
                {
                    "operation_id":
                        item[
                            "operation_id"
                        ],

                    "plan_id":
                        item[
                            "plan_id"
                        ],

                    "official_commune":
                        item[
                            "commune"
                        ],

                    "official_school_name":
                        item[
                            "school_name"
                        ],

                    "official_school_code":
                        item[
                            "school_code"
                        ],

                    "DB_CANDIDATES":
                        candidates_out,
                },
                ensure_ascii=False,
                default=str,
            )
        )


    # ======================================================
    # 7. UNRESOLVED / ORPHAN
    # ======================================================

    print()
    print("=" * 134)
    print("7. UNRESOLVED THCS")
    print("=" * 134)


    unresolved = list(
        ctx.get(
            "unresolved"
        )
        or []
    )


    print(
        "unresolved count =",
        len(unresolved),
    )


    for item in unresolved:

        print(
            json.dumps(
                item,
                ensure_ascii=False,
                default=str,
            )
        )


    # Riêng tìm THCS Nghi Hương.
    rows_nghi_huong = con.execute(
        """
        SELECT
            s.id,
            s.code,
            s.name,
            s.commune_id,
            s.is_active,
            c.name AS commune_name
        FROM schools s
        LEFT JOIN communes c
          ON c.id=s.commune_id
        WHERE TRIM(s.code)=?
           OR LOWER(s.name)
              LIKE LOWER(?)
        ORDER BY s.id
        """,
        (
            "40413505",
            "%Nghi Hương%",
        ),
    ).fetchall()


    print(
        "Nghi Huong DB =",
        json.dumps(
            [
                {
                    **dict(x),

                    "staff_2025":
                        staff_count(
                            con,
                            x["id"],
                            1,
                        ),

                    "staff_2026":
                        staff_count(
                            con,
                            x["id"],
                            2,
                        ),
                }
                for x in rows_nghi_huong
            ],
            ensure_ascii=False,
            default=str,
        ),
    )


    # ======================================================
    # 8. DB HEALTH
    # ======================================================

    print()
    print("=" * 134)
    print("8. DB HEALTH")
    print("=" * 134)


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


# ==========================================================
# 9. FILE IMMUTABILITY
# ==========================================================

print()
print("=" * 134)
print("9. FILE IMMUTABILITY")
print("=" * 134)


after = {
    "db":
        sha256(DB),

    "service":
        sha256(SERVICE),

    "lock":
        sha256(LOCK),

    "roster":
        sha256(ROSTER),
}


for key in before:

    print(
        key,
        ":",
        before[key],
        "->",
        after[key],
    )


if before != after:

    raise RuntimeError(
        "DUNG: file that da bi thay doi."
    )


print()
print("=" * 134)
print("CHAN DOAN CUOI THCS: HOAN TAT")
print("=" * 134)

print(
    "KHONG SUA DATABASE."
)

print(
    "KHONG SUA SERVICE / LOCK / ROSTER."
)

print(
    "KHONG CHAY SAP NHAP THCS."
)

print("=" * 134)
